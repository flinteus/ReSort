from typing import Annotated
from uuid import UUID

from anyio import CapacityLimiter
from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth import Database, current_session
from app.core.config import settings
from app.models.photo import Photo
from app.models.user import AuthSession
from app.schemas.photo import PhotoResponse
from app.services.photos import save_photo

router = APIRouter(prefix="/photos", tags=["photos"])
Authenticated = Annotated[AuthSession, Depends(current_session)]
# Bound decoded pixel buffers, independently of the default worker thread pool.
upload_workers = CapacityLimiter(2)


def owned_photo(photo_id: UUID, user_id: int, db, *, lock: bool = False) -> Photo:
    query = select(Photo).where(Photo.id == str(photo_id), Photo.user_id == user_id)
    if lock:
        query = query.with_for_update()
    photo = db.scalar(query)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@router.post("", response_model=PhotoResponse, status_code=201, openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "additionalProperties": False,
        "properties": {"file": {"type": "string", "format": "binary"}},
    }}}},
})
async def upload_photo(request: Request, db: Database, session: Authenticated):
    # Authenticate before multipart parsing. Keep all temporary uploads in this context.
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "multipart/form-data":
        raise HTTPException(status_code=415, detail="Expected multipart/form-data")
    try:
        async with request.form(max_files=1, max_fields=0, max_part_size=settings.max_photo_bytes) as form:
            upload = form.get("file")
            if len(form.multi_items()) != 1 or not isinstance(upload, UploadFile):
                raise HTTPException(status_code=422, detail="Exactly one file field named 'file' is required")
            return await run_sync(save_photo, upload, session.user_id, db, limiter=upload_workers)
    except StarletteHTTPException as exc:
        if exc.status_code == 400 and exc.detail == "Upload too large":
            raise HTTPException(status_code=413, detail="Upload too large") from None
        raise


@router.get("/{photo_id}", response_model=PhotoResponse)
def photo_metadata(photo_id: UUID, db: Database, session: Authenticated):
    return owned_photo(photo_id, session.user_id, db)


@router.get("/{photo_id}/content")
def photo_content(photo_id: UUID, db: Database, session: Authenticated):
    photo = owned_photo(photo_id, session.user_id, db)
    try:
        data = (settings.photo_storage_dir / f"{photo.id}.jpg").read_bytes()
    except OSError:
        raise HTTPException(status_code=503, detail="Photo storage unavailable") from None
    return Response(data, media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{photo.id}.jpg"',
    })


@router.delete("/{photo_id}", status_code=204)
def delete_photo(photo_id: UUID, db: Database, session: Authenticated):
    photo = owned_photo(photo_id, session.user_id, db, lock=True)
    try:
        (settings.photo_storage_dir / f"{photo.id}.jpg").unlink(missing_ok=True)
    except OSError:
        raise HTTPException(status_code=503, detail="Photo storage unavailable") from None
    db.delete(photo)
    db.commit()
    return Response(status_code=204)
