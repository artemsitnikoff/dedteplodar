"""State machine for Bitrix24 dialogs (see models.B24Session).

Rules:
- `touch()` on every client message: create the row if missing; if the Open
  Line session id (from `entityId = livechat|<line>|<session>|<user>`) has
  changed, a new dialog started (operator finished the previous one) → back
  to `bot`; if `operator` state is older than the TTL → back to `bot` as a
  safety net (Bitrix doesn't tell us when the operator closes the session).
- `mark_bot_turn()` after each generated answer keeps the consecutive-error
  counter for the auto-escalation trigger.
- `mark_handoff()` after a successful transfer; `reset_to_bot()` on
  ONIMBOTV2JOINCHAT (the bot is re-attached at the start of a new session).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.core.database import SessionLocal
from src.b24.models import STATUS_BOT, STATUS_OPERATOR, B24Session
from src.b24.webhook import B24Event

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Naive UTC, matching how query_logs.ts is stored (datetime.utcnow semantics)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(slots=True)
class SessionState:
    chat_id: int
    status: str
    bot_turns: int
    consecutive_errors: int
    line_session_id: str | None
    handoff_reason: str | None
    is_new_dialog: bool = False


def parse_entity_id(entity_id: str) -> tuple[str | None, str | None]:
    """``livechat|13|19165|515`` → (line_id ``"13"``, line_session_id ``"19165"``)."""
    parts = (entity_id or "").split("|")
    line = parts[1] if len(parts) > 1 and parts[1] else None
    sess = parts[2] if len(parts) > 2 and parts[2] else None
    return line, sess


def touch(ev: B24Event, *, operator_ttl_minutes: int) -> SessionState:
    now = _utcnow()
    line_id, line_session_id = parse_entity_id(ev.entity_id)
    is_new = False
    with SessionLocal() as s:
        row = s.get(B24Session, ev.chat_id)
        if row is None:
            row = B24Session(
                chat_id=ev.chat_id, dialog_id=ev.dialog_id, line_id=line_id,
                line_session_id=line_session_id, user_id=ev.user_id, user_name=ev.user_name,
                status=STATUS_BOT, created_at=now,
            )
            s.add(row)
            is_new = True
        else:
            if line_session_id and row.line_session_id and line_session_id != row.line_session_id:
                logger.info("[b24] chat=%s new open-line session %s (was %s) — back to bot",
                            ev.chat_id, line_session_id, row.line_session_id)
                _reset(row)
                is_new = True
            elif (
                row.status == STATUS_OPERATOR and row.handoff_at
                and now - row.handoff_at > timedelta(minutes=operator_ttl_minutes)
            ):
                logger.info("[b24] chat=%s operator state expired (ttl=%dmin) — back to bot",
                            ev.chat_id, operator_ttl_minutes)
                _reset(row)
            if line_session_id:
                row.line_session_id = line_session_id
            if line_id:
                row.line_id = line_id
            if ev.dialog_id:
                row.dialog_id = ev.dialog_id
            if ev.user_id:
                row.user_id = ev.user_id
            if ev.user_name:
                row.user_name = ev.user_name
        if ev.message_id:
            row.last_message_id = ev.message_id
        row.updated_at = now
        s.commit()
        return SessionState(
            chat_id=row.chat_id, status=row.status, bot_turns=row.bot_turns,
            consecutive_errors=row.consecutive_errors, line_session_id=row.line_session_id,
            handoff_reason=row.handoff_reason, is_new_dialog=is_new,
        )


def _reset(row: B24Session) -> None:
    row.status = STATUS_BOT
    row.bot_turns = 0
    row.consecutive_errors = 0
    row.handoff_reason = None
    row.handoff_at = None


def mark_bot_turn(chat_id: int, *, error: bool) -> int:
    """Count a generated answer; return the new consecutive-error count."""
    with SessionLocal() as s:
        row = s.get(B24Session, chat_id)
        if row is None:
            return 1 if error else 0
        row.bot_turns += 1
        row.consecutive_errors = row.consecutive_errors + 1 if error else 0
        row.updated_at = _utcnow()
        s.commit()
        return row.consecutive_errors


def mark_handoff(chat_id: int, reason: str) -> None:
    with SessionLocal() as s:
        row = s.get(B24Session, chat_id)
        if row is None:
            return
        row.status = STATUS_OPERATOR
        row.handoff_reason = reason[:64]
        row.handoff_at = _utcnow()
        row.updated_at = row.handoff_at
        s.commit()


def reset_to_bot(chat_id: int | None) -> None:
    if not chat_id:
        return
    with SessionLocal() as s:
        row = s.get(B24Session, chat_id)
        if row is None:
            return
        _reset(row)
        row.updated_at = _utcnow()
        s.commit()


def get_status(chat_id: int) -> str | None:
    with SessionLocal() as s:
        row = s.get(B24Session, chat_id)
        return row.status if row else None
