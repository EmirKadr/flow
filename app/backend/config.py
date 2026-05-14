from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/bemanning"
    SECRET_KEY: str = "dev-only-change-me"
    ENVIRONMENT: str = "development"
    SUPER_ADMIN_USERNAMES: str = "emikad"
    EXCEL_API_TOKEN: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def super_admin_usernames(self) -> set[str]:
        return {
            username.strip().lower()
            for username in self.SUPER_ADMIN_USERNAMES.split(",")
            if username.strip()
        }


settings = Settings()
