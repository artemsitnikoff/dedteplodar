"""SQLAlchemy model for Bitrix24 Open Line dialog state.

One row per Bitrix chat (= one client ↔ line dialog). The bot needs to know
whether a human operator has taken the dialog over so it stays silent, and
when a *new* Open Line session starts on the same chat so it can resume.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, engine
from src.core.migrations import register_schema_probe

STATUS_BOT = "bot"            # bot answers
STATUS_OPERATOR = "operator"  # handed off — bot is silent
STATUS_CLOSED = "closed"      # session finished (reserved)


class B24Session(Base):
    __tablename__ = "b24_sessions"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # data[message][chatId]
    dialog_id: Mapped[str] = mapped_column(String(32), nullable=False)  # "chat19167"
    line_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)          # entityId part 2
    line_session_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # entityId part 3
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_BOT)
    bot_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    handoff_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    handoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


_schema_ok = False
try:
    Base.metadata.create_all(bind=engine, tables=[B24Session.__table__], checkfirst=True)
    _schema_ok = True
except Exception:
    import logging
    logging.getLogger(__name__).exception("b24_sessions schema init failed")

register_schema_probe("b24_sessions", lambda: _schema_ok)
