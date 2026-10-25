import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# The project root is one level above this file (backend/), so mrp.db is the same
# file no matter which folder uvicorn is started from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The tests point this at a throwaway database (see tests/conftest.py).
DATABASE_URL = os.environ.get("MRP_DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'mrp.db').as_posix()}")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
