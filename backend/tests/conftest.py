"""
pytest configuration for the norman-retail-system test suite.

Adds the backend directory to sys.path so that "from app import ..." works.
Manages a single shared in-memory SQLite database for the entire test session.
"""

import os
import sys
import asyncio
from pathlib import Path

import pytest

# Ensure the backend directory is on sys.path so "from app import ..." works.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Database configuration for the entire test suite.
# We use an in-memory SQLite database so schema drift is impossible.
# This must be set BEFORE any app imports so that pydantic-settings
# picks it up.
# ---------------------------------------------------------------------------
# SQLite in-memory with shared cache so all connections see the same data.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")

# ---------------------------------------------------------------------------
# Session-scoped DB setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Create all tables once before the test session, using the current models.

    Because we use an in-memory SQLite database, there is no stale file on disk.
    Every test run starts with a fresh schema derived from ``Base.metadata``.
    Schema drift is structurally impossible.
    """
    from app.core.database import init_db, engine
    asyncio.run(init_db())
    yield
    # Dispose of the engine so connections are closed cleanly.
    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass


# Register custom markers so pytest does not warn about them.
def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")

