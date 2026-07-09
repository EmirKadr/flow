import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "app/.env"), env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/flow"
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
    DEEPSEEK_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com"
    META_ANALYSIS_TIMEOUT_SECONDS: int = 120
    META_ANALYSIS_AUTO_START: bool = False
    META_ANALYSIS_MAX_VIDEO_BYTES: int = 256 * 1024 * 1024
    META_ANALYSIS_MAX_CONCURRENCY: int = 1
    META_ANALYSIS_START_DELAY_SECONDS: float = 30.0
    META_ANALYSIS_SPACING_SECONDS: float = 15.0
    META_LABEL_STILL_TIME_SECONDS: float = 1.0
    # Media-lagring (videor/bilder) — strömmas alltid, hålls aldrig i sin helhet i RAM.
    MEDIA_STORE_BACKEND: str = "filesystem"
    MEDIA_STORE_ROOT: str = ""  # tom => <tempdir>/flow_media_store; i prod: monterad disk
    MEDIA_STORE_CHUNK_BYTES: int = 8 * 1024 * 1024
    META_MEDIA_RETENTION_DAYS: int = 30
    # Meta-uppladdningsgränser (publik endpoint) — klienten köar en fil i taget och backend strömmar chunks.
    MAX_META_UPLOAD_FILES: int = 6
    MAX_META_UPLOAD_FILE_BYTES: int = 96 * 1024 * 1024
    MAX_META_UPLOAD_BATCH_BYTES: int = 192 * 1024 * 1024
    META_UPLOAD_RATE_LIMIT_PER_MINUTE: int = 0
    DATA_SOURCE_API_BASE_URL: str = ""
    DATA_SOURCE_API_KEY: str = ""
    DATA_SOURCE_API_CLIENT: str = ""
    DATA_SOURCE_API_KEY_HEADER: str = ""
    DATA_SOURCE_API_CLIENT_HEADER: str = ""
    DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE: str = ""
    DATA_SOURCE_TIMEOUT_SECONDS: float = 30
    DATA_SOURCE_VERIFY_SSL: bool = True
    DATA_SOURCE_CA_BUNDLE: str = ""
    DATA_SOURCE_MAX_ROWS: int = 1000
    DATA_SOURCE_CATALOG_PATH: str = ""
    DATA_SOURCE_CATALOG_JSON: str = ""
    PUBLIC_DPAK_LINK_TOKEN: str = ""
    PUBLIC_DPAK_DEFAULT_BUSINESS_CODE: str = "STIGAMO"
    PUBLIC_DPAK_LIVE_PICK_VIEW: str = "v_ask_pick_log_full"
    PUBLIC_DPAK_ARCHIVE_PICK_VIEW: str = "dblog_pick_log"
    PUBLIC_DPAK_START_DATE: str = "2025-07-01"
    PUBLIC_DPAK_END_DATE: str = "2026-07-01"
    PUBLIC_DPAK_CHUNK_DAYS: int = 14
    PUBLIC_DPAK_COMPANY_CODES: str = "MG"
    PUBLIC_DPAK_PICK_ZONE_CODES: str = "R"
    PUBLIC_DPAK_ARCHIVE_DUCKDB: str = ""
    PUBLIC_DPAK_PREFER_ARCHIVE_DUCKDB: bool = True
    PUBLIC_DPAK_API_RETRIES: int = 4
    PUBLIC_DPAK_API_RETRY_DELAY_SECONDS: float = 10.0
    PUBLIC_DPAK_INSERT_BATCH_SIZE: int = 500
    PUBLIC_DPAK_FACT_INSERT_BATCH_SIZE: int = 20000
    PUBLIC_DPAK_DB_WRITE_RETRIES: int = 3
    PUBLIC_DPAK_SUPPORT_DIR: str = ""
    DEMO_USER_PASSWORD: str = "demo1234"
    DEMO_SESSION_MAX_AGE_HOURS: float = 6.0
    RENDER_API_KEY: str = ""
    RENDER_API_BASE_URL: str = "https://api.render.com/v1"
    RENDER_SERVICE_ID: str = ""
    RENDER_WEB_SERVICE_ID: str = ""
    RENDER_OWNER_ID: str = ""
    RENDER_WORKSPACE_ID: str = ""
    RENDER_POSTGRES_ID: str = ""
    RENDER_DATABASE_ID: str = ""
    HEALTHCHECK_PUBLIC_URL: str = ""
    TRACKING_ALLOW_VALUE_SAMPLES: bool = False
    ALLOCATION_OBSERVATIONS_STARTUP_SYNC: bool = False
    ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS: float = 180.0
    ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS: float = 30.0

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
