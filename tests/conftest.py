from __future__ import annotations
import json
from pathlib import Path

import pytest

from db import init_db
from models import EarningsReport
from app import app as flask_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mem_db():
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def sample_pltr_report() -> EarningsReport:
    data = json.loads((FIXTURES / "pltr_q2_2026.json").read_text())
    return EarningsReport.model_validate(data)


@pytest.fixture(scope="session")
def sample_mrvl_report() -> EarningsReport:
    data = json.loads((FIXTURES / "mrvl_q3_2024.json").read_text())
    return EarningsReport.model_validate(data)


@pytest.fixture
def flask_client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
