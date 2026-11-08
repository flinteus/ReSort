from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.auth import router as auth_router
from app.api.v1.sorting import router as sorting_router
from app.api.v1.photos import router as photos_router
from app.middleware.upload_limit import UploadLimitMiddleware
from app.api.v1.collection_points import router as collection_points_router
from app.api.v1.progress import router as progress_router
from app.core.config import settings
from app.db.dependecy import get_db

app = FastAPI(title=settings.app_name)
app.add_middleware(UploadLimitMiddleware)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(sorting_router, prefix="/api/v1")
app.include_router(photos_router, prefix="/api/v1")
app.include_router(collection_points_router, prefix="/api/v1")
app.include_router(progress_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok", "database": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
