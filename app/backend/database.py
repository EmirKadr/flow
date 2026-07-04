from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def _normalize_url(url: str) -> str:
    # Vissa hostar ger postgres:// — SQLAlchemy 2 vill ha postgresql+psycopg://
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


# pool_pre_ping kostar en extra DB-rundresa ("SELECT 1") på VARJE request —
# ~37 ms mot Azure SQL från k8s (uppmätt 2026-07-04). pool_recycle=1500 håller
# anslutningarna yngre än Azure-gatewayens 30-minuters idle-timeout, vilket
# ger samma skydd mot döda anslutningar utan per-request-skatten.
engine = create_engine(_normalize_url(settings.DATABASE_URL), pool_recycle=1500)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
