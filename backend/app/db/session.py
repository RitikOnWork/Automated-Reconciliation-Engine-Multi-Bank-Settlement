from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Production-grade engine configurations with connection pool tuning
engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,       # Detect disconnects and recycle connections
    pool_size=10,             # Keep up to 10 connections open
    max_overflow=20,          # Allow temporary burst up to 30 connections
    pool_recycle=3600,        # Recycle connections every hour to avoid stale states
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Generator:
    """
    FastAPI dependency yielding a thread-safe scoped database session.
    Automatically handles session closing on request teardown.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
