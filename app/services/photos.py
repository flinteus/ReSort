import io
import warnings
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.security import utcnow
from app.models.photo import Photo
from app.models.user import User


def sanitize_image(data: bytes) -> tuple[bytes, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
                if image.width * image.height > settings.max_photo_pixels or max(image.size) > 8192:
                    raise HTTPException(status_code=413, detail="Image dimensions exceed limits")
                if getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(status_code=415, detail="Animated images are not supported")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                oriented.thumbnail((2048, 2048))
                rgba = oriented.convert("RGBA")
                # A new image carries no EXIF, ICC profile, comments, or original bytes.
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=85)
                return output.getvalue(), clean.width, clean.height
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=413, detail="Image dimensions exceed limits") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(status_code=415, detail="Invalid or unsupported image") from None


def save_photo(upload: UploadFile, user_id: int, db: Session) -> Photo:
    data = upload.file.read(settings.max_photo_bytes + 1)
    if len(data) > settings.max_photo_bytes:
        raise HTTPException(status_code=413, detail="Photo exceeds size limit")
    if not data:
        raise HTTPException(status_code=415, detail="Empty image")
    encoded, width, height = sanitize_image(data)
    # Serialize uploads for a user so parallel requests cannot bypass the quota.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    count = db.scalar(select(func.count()).select_from(Photo).where(Photo.user_id == user_id))
    if count >= settings.max_photos_per_user:
        raise HTTPException(status_code=409, detail="Photo quota reached")
    photo = Photo(id=str(uuid4()), user_id=user_id, width=width, height=height,
                  size_bytes=len(encoded), created_at=utcnow())
    root = settings.photo_storage_dir
    path = root / f"{photo.id}.jpg"
    created = False
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as output:
            created = True
            path.chmod(0o600)
            output.write(encoded)
        db.add(photo)
        db.commit()
    except Exception:
        db.rollback()
        if created:
            path.unlink(missing_ok=True)
        raise
    return photo
