import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# The tests point this at a throwaway database (see tests/conftest.py).
DATABASE_URL = os.environ.get("MRP_DATABASE_URL", "sqlite:///./mrp.db")

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
