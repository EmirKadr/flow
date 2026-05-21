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
    MINIMAX_API_KEY: str = ""
    MINIMAX_API_URL: str = "https://api.minimax.io/v1/chat/completions"
    MINIMAX_MODEL: str = "MiniMax-M2.7"
    MINIMAX_MAX_TOKENS: int = 700
    MINIMAX_TIMEOUT_SECONDS: int = 30
    DATA_SOURCE_API_BASE_URL: str = ""
    DATA_SOURCE_API_KEY: str = ""
    DATA_SOURCE_API_CLIENT: str = ""
    DATA_SOURCE_API_KEY_HEADER: str = ""
    DATA_SOURCE_API_CLIENT_HEADER: str = ""
    DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE: str = ""
    DATA_SOURCE_TIMEOUT_SECONDS: float = 30
    DATA_SOURCE_MAX_ROWS: int = 1000
    DATA_SOURCE_CATALOG_PATH: str = ""
    DATA_SOURCE_CATALOG_JSON: str = ""

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
