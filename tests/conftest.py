"""Тесты операций работают в отдельной схеме с малым наполнением,
рабочие данные не трогаются."""
import os

os.environ["DB_SCHEMA"] = "georgii_valiaikin_test"

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.main import app


@pytest.fixture(scope="session")
def client():
    seed.main("small")
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def authorized_client(client):
    with TestClient(app) as c:
        r = c.post("/api/login", json={"login": "librarian", "password": "library"})
        assert r.status_code == 200
        yield c
