"""Common dependencies for admin API."""

# Re-export unified get_db from core
from src.core.database import get_db

__all__ = ["get_db"]