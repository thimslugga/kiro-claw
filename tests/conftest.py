"""Shared pytest configuration.

The DB layer holds its path at module scope, so we set it per-test here
rather than at import time. This avoids order-dependent pollution between
files that both touch the database.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_db_path(monkeypatch):
    import src.db as db

    tmp = tempfile.mktemp(suffix=".db")
    monkeypatch.setattr(db, "DB_PATH", type(db.DB_PATH)(tmp))
    yield
    if os.path.exists(tmp):
        try:
            os.unlink(tmp)
        except OSError:
            pass
