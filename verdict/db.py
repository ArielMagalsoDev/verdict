from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().sqlalchemy_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def session_scope():
    return SessionLocal()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
