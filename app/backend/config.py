import os
import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILES = (".env", "app/.env")


def _load_env_files_into_environ(paths: tuple[str, ...]) -> None:
    """Skjut in .env-rader i os.environ for varden som inte ar deklarerade Settings-falt.

    Pydantic-settings laser bara deklarerade falt ur env_file och skriver aldrig
    tillbaka till os.environ. Dynamiskt namngivna nycklar (t.ex.
    NOEFFECT_<TENANT>_TOKEN) lases med os.getenv och blir annars osynliga lokalt.
    Riktiga OS-miljovariabler (t.ex. i k8s) skrivs aldrig over.
    """
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ[key] = value


_load_env_files_into_environ(ENV_FILES)


# Octopus ersätter #{VAR} i deploy-manifestet bara när variabeln finns definierad
# i projektet; okända platshållare lämnas ordagrant kvar och blir annars "riktiga"
# settings-värden (hände 2026-07-09: GEMINI_API_BASE_URL="#{GEMINI_API_BASE_URL}"
# fick varje meta-videoanalys att kasta ValueError).
_UNSUBSTITUTED_PLACEHOLDER = re.compile(r"#\{[^{}]*\}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _blank_unsubstituted_placeholders(cls, value: object) -> object:
        if isinstance(value, str) and _UNSUBSTITUTED_PLACEHOLDER.fullmatch(value.strip()):
            return ""
        return value

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
    # Apphjälpens interna read-only-tools (function calling i chatten).
    ASSISTANT_TOOLS_ENABLED: bool = True
    ASSISTANT_TOOLS_MAX_STEPS: int = 4
    ASSISTANT_TOOLS_MAX_CALLS_PER_STEP: int = 5
    # Behörighetsmetadata (view_id per tool) finns i registret; false = alla
    # inloggade får alla tools, true = filtrera per vybehörighet (framtida läge).
    ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS: bool = False
    NOEFFECT_MCP_URL_TEMPLATE: str = ""
    NOEFFECT_MCP_TOKEN_ENV_TEMPLATE: str = "NOEFFECT_{tenant}_TOKEN"
    NOEFFECT_MCP_TIMEOUT_SECONDS: float = 30
    MCP_LLM_PROVIDER: str = "auto"
    MCP_GEMINI_MODELS: str = "gemini-2.5-flash,gemini-2.5-pro"
    MCP_DEEPSEEK_MODELS: str = "deepseek-v4-pro,deepseek-chat,deepseek-reasoner"
    MCP_OPENAI_MODELS: str = "gpt-5.5,gpt-5.4,gpt-5.2,gpt-5,gpt-4o-mini,gpt-4o,gpt-4.1-mini,gpt-4.1,gpt-4.1-nano,o4-mini,o3-mini,o3"
    MCP_MINIMAX_MODELS: str = "MiniMax-M2.7"
    MCP_LLM_OPENAI_API_KEY: str = ""
    MCP_LLM_OPENAI_MODEL: str = "gpt-4o"
    MCP_LLM_OPENAI_API_BASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_API_BASE_URL: str = "https://api.openai.com/v1"
    META_TRANSCRIPTION_MODEL: str = "gpt-4o-transcribe"
    META_ANALYSIS_TEXT_MODEL: str = "gpt-4o-mini"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_API_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_THINKING_ENABLED: bool = False
    DEEPSEEK_REASONING_EFFORT: str = "high"
    META_ANALYSIS_TIMEOUT_SECONDS: int = 120
    META_ANALYSIS_AUTO_START: bool = False
    META_ANALYSIS_MAX_VIDEO_BYTES: int = 256 * 1024 * 1024
    META_ANALYSIS_MAX_CONCURRENCY: int = 1
    META_ANALYSIS_START_DELAY_SECONDS: float = 30.0
    META_ANALYSIS_SPACING_SECONDS: float = 15.0
    # Meta-uppladdningar ar publika/inloggningsfria och har ingen business_id att
    # slå upp tenant fran, sa Dispatchpallar-uppslaget kan inte tenant-scopa sig
    # sjalvt. Frey ar den enda verksamheten som anvander Meta idag.
    META_ANALYSIS_DATA_SOURCE_TENANT: str = "frey"
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
    # Rate limiting för inloggning: fast fönster per (användarnamn, IP).
    AUTH_LOGIN_RATE_LIMIT_ENABLED: bool = True
    AUTH_LOGIN_RATE_LIMIT_ATTEMPTS: int = 8
    AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    # Buggrapporter (experiment): 30 s DOM-inspelning från Bugg-knappen.
    BUG_REPORTS_ENABLED: bool = True
    BUG_REPORTS_RETENTION_DAYS: int = 30
    BUG_REPORTS_MAX_EVENTS_BYTES: int = 4 * 1024 * 1024
    BUG_REPORTS_RATE_LIMIT_PER_HOUR: int = 3
    DATA_SOURCE_API_BASE_URL: str = ""
    # Alternativa bas-URL:er för ASK-gatewayen. Används enbart av
    # diagnostikverktyget i Arkivstatus (superuser) för att jämföra samma
    # vyer/tenants mot t.ex. publik URL vs interna kluster-adresser. Tom => fliken markeras "ej satt".
    DATA_SOURCE_API_BASE_URL2: str = ""
    DATA_SOURCE_API_BASE_URL3: str = ""
    DATA_SOURCE_API_KEY: str = ""
    DATA_SOURCE_API_CLIENT: str = ""
    DATA_SOURCE_API_KEY_HEADER: str = ""
    DATA_SOURCE_API_CLIENT_HEADER: str = ""
    DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE: str = ""
    DATA_SOURCE_TIMEOUT_SECONDS: float = 30
    DATA_SOURCE_VERIFY_SSL: bool = True
    DATA_SOURCE_CA_BUNDLE: str = ""
    DATA_SOURCE_MAX_ROWS: int = 1000
    # Externa datakällans tak för antal rader per API-svar. När ett svar når detta
    # antal antas det vara avhugget och hämtningen delas upp i mindre datumfönster.
    DATA_SOURCE_RESPONSE_ROW_CAP: int = 50000
    DATA_SOURCE_CATALOG_PATH: str = ""
    DATA_SOURCE_CATALOG_JSON: str = ""
    # Kill-switch för ALLA externa ASK-hämtningar (arkiv-cache-seed, live-vyer,
    # diagnostikproben i Arkivstatus, Sankey/Produktivitet/Hämta data) — se
    # ExternalDataClient.fetch_data. Sträng, inte bool: en osubstituerad
    # #{DATA_SOURCE_API_FETCH_ENABLED}-platshållare blankas till "" av
    # _blank_unsubstituted_placeholders ovan, och data_source_api_fetch_enabled
    # tolkar tomt som "på" (fail-open = dagens beteende) om Octopus-variabeln
    # saknas. En bool-fält hade kraschat på den osubstituerade texten istället
    # (samma landmine som GEMINI_API_BASE_URL 2026-07-09).
    DATA_SOURCE_API_FETCH_ENABLED: str = "true"
    # Lokal arkiv-cache (DuckDB). Speglar dblog_*-arkivvyer per tenant så lokala
    # körningar av Sankey/Produktivitet/Hämta data läser historik lokalt istället
    # för via API. Endast för lokal utveckling; default av. Se wiki/local-archive-cache.md.
    ARCHIVE_CACHE_ENABLED: bool = False
    ARCHIVE_CACHE_DIR: str = ""  # tom => <compiled_data_root>/archive_cache
    ARCHIVE_CACHE_SEED_DAYS: int = 400  # hur långt bak den initiala dblog-seeden går
    ARCHIVE_CACHE_CHUNK_DAYS: int = 14  # seeden hämtas/skrivs i bitar om N dagar (återupptagningsbart)
    ARCHIVE_CACHE_EMPTY_STOP_DAYS: int = 300  # backfill stoppas nar N dagar i rad saknar rader
    # Djup-seeden (hela dblog-historiken) körs via CLI (python -m app.backend.archive_cache_cli),
    # inte vid serverstart. Serverns schemaläggare toppar bara på redan seedade vyer framåt.
    # Sätt =1 bara om du vill att servern ska göra den tunga initiala seeden vid start.
    ARCHIVE_CACHE_SEED_ON_START: bool = False
    ARCHIVE_CACHE_SEED_WORKERS: int = 5  # parallella hämtningar (vyer/tenants) i CLI-seeden
    ARCHIVE_CACHE_SYNC_HOUR: int = 0  # daglig topp-på-tid (lokal tid), 00:01 => hour 0
    ARCHIVE_CACHE_SYNC_MINUTE: int = 1
    DEMO_USER_PASSWORD: str = "demo1234"
    DEMO_SESSION_MAX_AGE_HOURS: float = 6.0
    HEALTHCHECK_PUBLIC_URL: str = ""
    TRACKING_ALLOW_VALUE_SAMPLES: bool = False
    RFID_DEVICE_TOKEN: str = ""
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "flow-web"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_HEADERS: str = ""
    OTEL_TRACES_SAMPLE_RATE: float = 0.1
    OTEL_LOGS_ENABLED: bool = False
    OTEL_LOG_LEVEL: str = "WARNING"
    OTEL_REQUEST_LOG_ENABLED: bool = False
    OTEL_SQLALCHEMY_ENABLED: bool = True
    OTEL_CONSOLE_EXPORTER: bool = False
    # Mätpunkt (inte en optimering): loggar hur många bytes de SSE-levererade
    # slutpayloaderna (Sankey - Inbound, Produktivitetsöversikt) faktiskt är, rått
    # och gzip-6-komprimerat. text/event-stream undantas från GZipMiddleware, så de
    # payloaderna har aldrig mätts. Kostar en extra json.dumps + gzip per byggd
    # rapport (rapportbygget tar sekunder, mätningen millisekunder). Sätt false för
    # att stänga av helt.
    PAYLOAD_SIZE_LOGGING_ENABLED: bool = True
    ALLOCATION_OBSERVATIONS_STARTUP_SYNC: bool = False
    ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS: float = 180.0
    ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS: float = 30.0

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def data_source_api_fetch_enabled(self) -> bool:
        raw = str(self.DATA_SOURCE_API_FETCH_ENABLED or "").strip().lower()
        return raw not in ("0", "false", "off", "no")

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
