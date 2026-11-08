import io
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.models.photo import Photo
from test_auth import auth_client, headers, register_and_login  # noqa: F401


@pytest.fixture
def photo_client(auth_client, tmp_path, monkeypatch):
    client, db = auth_client
    _, _, tokens = register_and_login(client)
    client.headers.update(headers(tokens))
    monkeypatch.setattr(settings, "photo_storage_dir", tmp_path / "private")
    return client, db


def picture(format="JPEG", size=(40, 20), **options):
    image = Image.new("RGB", size, "green")
    stream = io.BytesIO()
    image.save(stream, format=format, **options)
    return stream.getvalue()


def upload(client, data=None, filename="photo.jpg", mime="image/jpeg"):
    return client.post("/api/v1/photos", files={"file": (filename, picture() if data is None else data, mime)})


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_upload_read_delete(photo_client, format):
    client, db = photo_client
    response = upload(client, picture(format), filename="../../outside.exe", mime="application/octet-stream")
    assert response.status_code == 201
    metadata = response.json()
    photo_id = metadata["id"]
    assert set(metadata) == {"id", "width", "height", "size_bytes", "created_at"}
    assert len(list(settings.photo_storage_dir.iterdir())) == 1
    stored = settings.photo_storage_dir / f"{photo_id}.jpg"
    assert stored.stat().st_mode & 0o777 == 0o600
    assert client.get(f"/api/v1/photos/{photo_id}").json() == metadata
    content = client.get(f"/api/v1/photos/{photo_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/jpeg"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["cache-control"] == "private, no-store"
    assert len(content.content) == metadata["size_bytes"]
    with Image.open(io.BytesIO(content.content)) as clean:
        assert clean.format == "JPEG"
        assert clean.size == (40, 20)
    assert client.delete(f"/api/v1/photos/{photo_id}").status_code == 204
    assert not stored.exists()
    assert db.scalar(select(func.count()).select_from(Photo)) == 0
    assert client.get(f"/api/v1/photos/{photo_id}").status_code == 404


def test_metadata_removed_and_orientation_preserved(photo_client):
    client, _ = photo_client
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private location and comment"
    result = upload(client, picture(exif=exif)).json()
    assert (result["width"], result["height"]) == (20, 40)
    response = client.get(f"/api/v1/photos/{result['id']}/content")
    assert b"private location" not in response.content
    with Image.open(io.BytesIO(response.content)) as clean:
        assert not clean.getexif()
        assert "icc_profile" not in clean.info


def test_access_is_private(photo_client):
    client, _ = photo_client
    photo_id = upload(client).json()["id"]
    _, _, other_tokens = register_and_login(client)
    client.headers.update(headers(other_tokens))
    for path in [f"/api/v1/photos/{photo_id}", f"/api/v1/photos/{photo_id}/content"]:
        assert client.get(path).status_code == 404
    assert client.delete(f"/api/v1/photos/{photo_id}").status_code == 404
    del client.headers["Authorization"]
    assert upload(client).status_code == 401
    assert client.get(f"/api/v1/photos/{photo_id}/content").status_code == 401


@pytest.mark.parametrize("data", [b"", b"not a photo", b'<svg xmlns="http://www.w3.org/2000/svg"/>', picture("GIF"), picture()[:50]])
def test_invalid_image_rejected(photo_client, data):
    client, db = photo_client
    assert upload(client, data).status_code == 415
    assert db.scalar(select(func.count()).select_from(Photo)) == 0
    assert not settings.photo_storage_dir.exists()


def test_animation_rejected(photo_client):
    client, _ = photo_client
    stream = io.BytesIO()
    first = Image.new("RGB", (10, 10), "red")
    first.save(stream, format="PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")])
    assert upload(client, stream.getvalue()).status_code == 415


def test_file_size_and_pixel_limits(photo_client, monkeypatch):
    client, _ = photo_client
    monkeypatch.setattr(settings, "max_photo_bytes", 1024)
    assert upload(client, b"x" * 1025).status_code == 413
    monkeypatch.setattr(settings, "max_photo_pixels", 10)
    assert upload(client).status_code == 413


def test_streamed_body_limit(photo_client, monkeypatch):
    client, _ = photo_client
    monkeypatch.setattr(settings, "max_photo_bytes", 1024)
    def chunks():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="photo.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        for _ in range(80):
            yield b"x" * 1024
        yield b"\r\n--boundary--\r\n"
    response = client.post("/api/v1/photos", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=boundary"})
    assert response.status_code == 413


def test_envelope_limit_and_form_contract(photo_client, monkeypatch):
    client, _ = photo_client
    monkeypatch.setattr(settings, "max_photo_bytes", 1024)
    assert upload(client, b"x" * 70000).status_code == 413
    assert client.post("/api/v1/photos", json={"file": "test"}).status_code == 415
    assert client.post("/api/v1/photos", files={"wrong": ("photo.jpg", picture())}).status_code == 422
    assert client.post("/api/v1/photos", files=[("file", ("a.jpg", picture())), ("file", ("b.jpg", picture()))]).status_code == 400


def test_quota_and_unknown_id(photo_client, monkeypatch):
    client, _ = photo_client
    monkeypatch.setattr(settings, "max_photos_per_user", 1)
    assert upload(client).status_code == 201
    assert upload(client).status_code == 409
    assert client.get(f"/api/v1/photos/{uuid4()}").status_code == 404
    assert client.get("/api/v1/photos/invalid-id").status_code == 422


def test_failed_commit_removes_file(photo_client, monkeypatch):
    client, db = photo_client
    def fail():
        raise RuntimeError("Simulated database failure")
    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError, match="Simulated"):
        upload(client)
    assert list(settings.photo_storage_dir.iterdir()) == []


def test_large_image_is_resized(photo_client):
    client, _ = photo_client
    result = upload(client, picture(size=(3000, 1000))).json()
    assert result["width"] == 2048
    assert 680 <= result["height"] <= 684


def test_missing_stored_file_is_service_error(photo_client):
    client, _ = photo_client
    photo_id = upload(client).json()["id"]
    (settings.photo_storage_dir / f"{photo_id}.jpg").unlink()
    response = client.get(f"/api/v1/photos/{photo_id}/content")
    assert response.status_code == 503
    assert "private" not in response.text
    assert client.delete(f"/api/v1/photos/{photo_id}").status_code == 204
