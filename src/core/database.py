"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from .config import settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


# Create engine
engine = create_engine(
    f"sqlite:///{settings.database_path}",
    echo=False,
    pool_pre_ping=True
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Get database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables() -> None:
    """Create all database tables."""
    # Import all models to ensure they are registered
    from src.products.models import Product, ProductParam, Category
    from src.documents.models import Document
    from src.rag.models import Chunk
    from src.logs.models import QueryLog
    from src.faq.models import FaqEntry

    Base.metadata.create_all(bind=engine)