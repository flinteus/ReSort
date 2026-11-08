from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ReSort"
    photo_storage_dir: Path = Path("data/photos")
    max_photo_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_photo_pixels: int = Field(default=20_000_000, ge=1, le=20_000_000)
    max_photos_per_user: int = Field(default=100, ge=1, le=1000)
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    database_url: SecretStr
    jwt_secret_key: SecretStr = Field(min_length=32)


settings = Settings()
