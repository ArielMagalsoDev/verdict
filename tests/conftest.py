import os
import pathlib
import tempfile

# Must run before any `verdict.*` import — db.py builds its engine from
# settings() at module import time.
DB_PATH = pathlib.Path(tempfile.gettempdir()) / "verdict_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ["RATE_LIMIT_PER_HOUR"] = "20"
os.environ["DAILY_SPEND_CAP_USD"] = "5.0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_db_file():
    if DB_PATH.exists():
        DB_PATH.unlink()
    yield
    from verdict.db import engine

    engine.dispose()
    if DB_PATH.exists():
        DB_PATH.unlink()


def _clear_all(db):
    from verdict.models import (
        AppliedChange,
        AuditEvent,
        CompanyFact,
        CrmChangeSet,
        CrmCompany,
        CrmContact,
        EvalRun,
        IdentityMatch,
        Job,
        Lead,
        OutreachDraft,
        QualificationDecision,
        RateLimitEvent,
        ResponseCache,
        SpendLedger,
    )

    for model in [
        AppliedChange,
        AuditEvent,
        CompanyFact,
        CrmChangeSet,
        OutreachDraft,
        QualificationDecision,
        IdentityMatch,
        Job,
        Lead,
        RateLimitEvent,
        ResponseCache,
        SpendLedger,
        EvalRun,
        CrmContact,
        CrmCompany,
    ]:
        db.query(model).delete()
    db.commit()


@pytest.fixture()
def db_session():
    from verdict.db import Base, engine, session_scope
    from verdict.seed import seed_crm

    Base.metadata.create_all(engine)
    with session_scope() as db:
        _clear_all(db)
        seed_crm(db)
        yield db


@pytest.fixture()
def client(db_session):
    from verdict.main import app

    with TestClient(app) as c:
        yield c
