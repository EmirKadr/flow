import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/bemanning"
    SECRET_KEY: str = "dev-only-change-me"
    ENVIRONMENT: str = "development"
    SUPER_USER_USERNAMES: str = "emikad,mikhal"
    EXCEL_API_TOKEN: str = ""
    PRODUCTIVITY_REFERENCE_DIR: str = ""
    PRODUCTIVITY_DATA_DIR: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def super_user_usernames(self) -> set[str]:
        configured = ",".join(
            value
            for value in (
                self.SUPER_USER_USERNAMES,
                os.getenv("SUPER" "_ADMIN_USERNAMES", ""),
            )
            if value
        )
        return {
            username.strip().lower()
            for username in configured.split(",")
            if username.strip()
        }


settings = Settings()
