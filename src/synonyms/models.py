"""Synonym dictionary — fuzzy-match terms users say to canonical names
the catalog actually knows. Edited from the admin UI, loaded by the bot
on a short polling interval (same pattern as FaqMatcher).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, engine


class Synonym(Base):
    """One synonym rule: when the user says `term`, treat it as `canonical`.

    Examples:
      term=Трус двенадцать  canonical=Русь-12               category=model
      term=билетная горелка canonical=пеллетная горелка     category=component
      term=Тайгинка         canonical=Сахара-24 ЛК          category=discontinued
    """

    __tablename__ = "synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    canonical: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    # model | component | discontinued | general
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        server_default=func.now(), nullable=False,
    )


# Create the table on import — safe (checkfirst=True)
Base.metadata.create_all(bind=engine, checkfirst=True)
