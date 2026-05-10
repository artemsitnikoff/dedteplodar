"""Common dependencies for admin API."""

from typing import Generator
from sqlalchemy.orm import Session

from src.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()