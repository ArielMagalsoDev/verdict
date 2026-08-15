import time

from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().sqlalchemy_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def session_scope():
    return SessionLocal()


def init_db(retries: int = 5, delay: float = 0.5) -> None:
    """Creates all tables (no migrations directory — this is a demo app; see
    README). The web and worker containers both call this on startup, which
    races on a genuinely fresh database: two connections can both decide a
    table is missing and issue CREATE TABLE concurrently, and one loses with
    a duplicate-object error. Retrying a few times is simpler and just as
    correct as coordinating startup order between two Compose services."""
    from . import models  # noqa: F401

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            Base.metadata.create_all(engine)
            return
        except DBAPIError as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    if last_exc:
        raise last_exc
