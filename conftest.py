"""
Test setup. Two rules the whole suite relies on:

1. Tests NEVER touch your real database. MRP_DATABASE_URL is pointed at a
   throwaway file BEFORE the app is imported, and the assert below stops the
   run if that ever stops being true.
2. Every test starts from an empty database.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="mrp-tests-"))
os.environ["MRP_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"   # must come first

import pytest
from fastapi.testclient import TestClient

from database import engine
from helpers import reset_database
from main import app

assert "mrp-tests-" in str(engine.url), "tests must never run against the real database"


@pytest.fixture()
def client():
    reset_database()
    with TestClient(app) as test_client:
        yield test_client
