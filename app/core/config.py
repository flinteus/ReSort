from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ReSort"
    database_url: SecretStr
    jwt_secret_key: SecretStr = Field(min_length=32)


settings = Settings()
