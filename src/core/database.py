"""Database configuration and session management."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.engine import Engine
from typing import Generator
import sqlite3

from .config import settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


# SQLite optimization PRAGMA
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite PRAGMA settings for performance and WAL mode."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for concurrent reads/writes
        cursor.execute("PRAGMA journal_mode=WAL")
        # Normal synchronous mode (faster than FULL, safe with WAL)
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Store temp data in memory for faster operations
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Enable memory-mapped I/O (256MB)
        cursor.execute("PRAGMA mmap_size=268435456")
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Create engine with connection pooling and threading support
engine = create_engine(
    f"sqlite:///{settings.database_path}",
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "check_same_thread": False,
        "timeout": 30
    },
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session with automatic commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Legacy alias for backward compatibility
get_session = get_db


def create_tables() -> None:
    """Create all database tables."""
    # Import all models to ensure they are registered
    from src.products.models import Product, ProductParam, Category
    from src.documents.models import Document
    from src.rag.models import Chunk
    from src.logs.models import QueryLog
    from src.faq.models import FaqEntry

    Base.metadata.create_all(bind=engine)