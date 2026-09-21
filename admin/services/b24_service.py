"""Bitrix24 channel — answer a client's Open Line message with the RAG pipeline,
hand the dialog to a human operator when the bot shouldn't (or can't) answer.

Runs *after* the webhook has already returned 200 (Bitrix24 wants a fast ack
and does not guarantee redelivery). Flow per ONIMBOTV2MESSAGEADD:

  1. dedup by message id (paired deliveries were seen in the wild)
  2. session state (src/b24/sessions.py): if an operator has the dialog →
     stay silent; a new Open Line session on the same chat → bot again
  3. escalation before RAG: "Позвать оператора" button / "оператор…" /
     personal-order phrases ("мой заказ", "рекламация"…) → transfer
  4. otherwise: placeholder ("ищу ответ…") → answer_with_meta() in a worker
     thread (history from query_logs by the synthetic user id keyed on the
     chat) → query_logs → edit the placeholder into the answer + button
  5. N consecutive generation errors → transfer as well

ONIMBOTV2JOINCHAT resets the dialog to `bot` (Bitrix re-attaches the bot at
the start of a new session).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from types import SimpleNamespace

from admin.services.eval_service import get_eval_generator
from admin.services.judge_service import spawn_judge
from src.b24 import sessions
from src.b24.client import B24Client, B24Error
from src.b24.format import html_to_bbcode
from src.b24.models import STATUS_OPERATOR
from src.b24.webhook import B24Event
from src.core.config import settings
from src.core.database import SessionLocal
from src.logs.queries import save_query_log, set_feedback, synthetic_user_id

logger = logging.getLogger(__name__)

OPERATOR_REQUEST_TEXT = "Позвать оператора"
PLACEHOLDER_TEXT = "Секунду, ищу ответ в базе знаний…"
_HOTLINE = (
    "[b]8 800 775-03-07[/b] (бесплатно, ежедн. 10:00–21:00 МСК)\n"
    "[b]8 800 101-43-53[/b] — интернет-магазин (ежедн. 9:00–20:00 МСК)"
)
FALLBACK_TEXT = (
    "Извините, не удалось получить ответ. Попробуйте ещё раз или позвоните нам:\n" + _HOTLINE
)
TRANSFER_TEXT = (
    "[b]Передаю диалог оператору.[/b] Он подключится в ближайшее время и ответит здесь же.\n\n"
    "Если срочно — звоните прямо сейчас:\n" + _HOTLINE
)
TRANSFER_FAILED_TEXT = (
    "Не получилось передать диалог оператору автоматически. Позвоните нам, и вам помогут:\n" + _HOTLINE
)

_OPERATOR_RE = re.compile(r"\b(оператор\w*|человек\w*|менеджер\w*|живой|специалист\w*)\b", re.IGNORECASE)
# Questions about the client's own order/complaint — no knowledge base can
# answer these, and the intent prompt already refuses FAQ matches for them.
_PERSONAL_ORDER_RE = re.compile(
    r"(\bмо(?:й|его|ему|ём|я|ей|ю|и|их)\s+заказ|\bзаказ\s*(?:№|#|номер)|\bномер\s+заказа|\bстатус\s+заказа"
    r"|\bгде\s+мо(?:й|я|и)\b|\bне\s+(?:пришл|привезл|доставил|отправил)|\bверн(?:уть|ите)\s+деньги"
    r"|\bвозврат\s+(?:денег|средств)|\bрекламац|\bбрак\b|\bбракован)",
    re.IGNORECASE,
)

REASON_REQUESTED = "requested"
REASON_PERSONAL_ORDER = "personal_order"
REASON_ERRORS = "consecutive_errors"

_SEEN_MAX = 2000
_seen_message_ids: "OrderedDict[int, None]" = OrderedDict()
_background_tasks: set[asyncio.Task] = set()


def _error_meta():
    """Duck-typed stand-in for the generator's meta on the failure path.

    Deliberately not imported from src.rag.answer_generator: that module
    pulls in the E5 stack (torch) at import time, and this service is
    imported by the admin router at startup.
    """
    return SimpleNamespace(
        query_type="ERROR", top_score=None, chunks_used=0, city=None, reformulated_query=None,
        t_intent_ms=None, t_retrieval_ms=None, t_answer_ms=None, t_answer_model=None,
    )


def operator_keyboard() -> list[dict]:
    """One button that sends OPERATOR_REQUEST_TEXT as the client's own message.

    ACTION=SEND needs no command registration on the portal (unlike COMMAND
    → ONIMBOTV2COMMANDADD), so the press arrives as a normal
    ONIMBOTV2MESSAGEADD and is caught by `is_operator_request`.
    """
    return [{
        "TEXT": OPERATOR_REQUEST_TEXT,
        "ACTION": "SEND",
        "ACTION_VALUE": OPERATOR_REQUEST_TEXT,
        "BG_COLOR_TOKEN": "alert",
        "DISPLAY": "LINE",
    }]


def is_operator_request(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.casefold() == OPERATOR_REQUEST_TEXT.casefold():
        return True
    # Short free-text asks like "позовите оператора" / "нужен человек".
    return len(t) <= 60 and bool(_OPERATOR_RE.search(t))


def is_personal_order(text: str) -> bool:
    return bool(_PERSONAL_ORDER_RE.search(text or ""))


def mark_seen(message_id: int | None) -> bool:
    """True the first time a message id is seen; False on a redelivery."""
    if message_id is None:
        return True
    if message_id in _seen_message_ids:
        _seen_message_ids.move_to_end(message_id)
        return False
    _seen_message_ids[message_id] = None
    while len(_seen_message_ids) > _SEEN_MAX:
        _seen_message_ids.popitem(last=False)
    return True


def journal_identity(ev: B24Event) -> tuple[int, str]:
    """(user_id, username) for query_logs.

    The chat (= one Open Line dialog) is the conversation key, so history
    lookups group by it; the username carries the human-readable bits.
    """
    user_id = synthetic_user_id(f"b24:chat{ev.chat_id}")
    name = (ev.user_name or "guest").strip()[:40]
    return user_id, f"b24:{name}#{ev.user_id or 0}"


def spawn_handle_event(ev: B24Event) -> asyncio.Task:
    task = asyncio.create_task(handle_event(ev))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def handle_event(ev: B24Event) -> None:
    if ev.is_join:
        logger.info("[b24] bot joined chat=%s dialog=%s — dialog state reset", ev.chat_id, ev.dialog_id)
        sessions.reset_to_bot(ev.chat_id)
        return

    if not mark_seen(ev.message_id):
        logger.info("[b24] duplicate delivery msg_id=%s chat=%s — skipped", ev.message_id, ev.chat_id)
        return

    state = sessions.touch(ev, operator_ttl_minutes=settings.b24_operator_ttl_minutes)
    if state.status == STATUS_OPERATOR:
        logger.info("[b24] chat=%s is with an operator (%s) — bot stays silent", ev.chat_id, state.handoff_reason)
        return

    bot_id = ev.bot_id or settings.b24_bot_id
    user_id, username = journal_identity(ev)
    try:
        client = B24Client(ev.client_endpoint, ev.access_token)
    except ValueError as e:
        logger.error("[b24] cannot build REST client for chat=%s: %s", ev.chat_id, e)
        return

    if is_operator_request(ev.text):
        await escalate(ev, client, bot_id, REASON_REQUESTED, user_id, username)
        return
    if is_personal_order(ev.text):
        await escalate(ev, client, bot_id, REASON_PERSONAL_ORDER, user_id, username)
        return

    t0 = time.monotonic()
    placeholder_id = await _safe_send(client, bot_id, ev.dialog_id, PLACEHOLDER_TEXT)

    try:
        generator = await get_eval_generator()

        def worker():
            with SessionLocal() as session:
                return generator.answer_with_meta(session, ev.text, user_id=user_id)

        answer_html, meta = await asyncio.to_thread(worker)
    except Exception as e:
        logger.error("[b24] answer generation failed chat=%s: %s", ev.chat_id, e, exc_info=True)
        answer_html, meta = FALLBACK_TEXT, _error_meta()

    is_error = meta.query_type == "ERROR"
    log_id = save_query_log(
        question=ev.text,
        answer=answer_html,
        query_type=meta.query_type,
        user_id=user_id,
        username=username,
        top_score=meta.top_score,
        chunks_used=meta.chunks_used,
        city=meta.city,
        reformulated_query=meta.reformulated_query,
        bot_message_id=placeholder_id,
    )
    if log_id and answer_html and not is_error:
        spawn_judge(log_id, ev.text, answer_html, tag="b24")

    text = answer_html if is_error else html_to_bbcode(answer_html)
    keyboard = operator_keyboard()
    delivered = False
    if placeholder_id:
        delivered = await _safe_update(client, bot_id, placeholder_id, text, keyboard)
    if not delivered:
        delivered = (await _safe_send(client, bot_id, ev.dialog_id, text, keyboard)) is not None

    errors = sessions.mark_bot_turn(ev.chat_id, error=is_error)
    logger.info(
        "[b24] answered chat=%s log=%s type=%s delivered=%s via=%s total=%dms (intent=%s ret=%s ans=%s model=%s)",
        ev.chat_id, log_id, meta.query_type, delivered, "update" if placeholder_id and delivered else "send",
        int((time.monotonic() - t0) * 1000),
        meta.t_intent_ms, meta.t_retrieval_ms, meta.t_answer_ms, meta.t_answer_model,
    )
    if is_error and errors >= settings.b24_max_consecutive_errors:
        logger.warning("[b24] chat=%s: %d consecutive errors — escalating", ev.chat_id, errors)
        await escalate(ev, client, bot_id, REASON_ERRORS, user_id, username, log_turn=False)


async def escalate(
    ev: B24Event,
    client: B24Client,
    bot_id: int,
    reason: str,
    user_id: int,
    username: str,
    *,
    log_turn: bool = True,
) -> bool:
    """Tell the client, hand the Open Line dialog to a human, remember it.

    Returns True if Bitrix accepted the transfer. On failure the client gets
    the hotline instead and the dialog stays with the bot.
    """
    if log_turn:
        log_id = save_query_log(
            question=ev.text, answer=TRANSFER_TEXT, query_type="OPERATOR",
            user_id=user_id, username=username,
        )
        set_feedback(log_id, "operator")  # shows up under the Journal's 🆘 filter like Telegram

    try:
        if settings.b24_transfer_to:
            ok = await client.session_transfer(ev.chat_id, settings.b24_transfer_to)
        else:
            ok = await client.session_operator(ev.chat_id)
    except B24Error as e:
        if e.code == "WRONG_CHAT":
            # "Operator is not a bot" — the dialog is already with a human.
            logger.info("[b24] chat=%s already handled by an operator (%s)", ev.chat_id, e)
            ok = True
        else:
            logger.error("[b24] transfer failed chat=%s reason=%s: %s", ev.chat_id, reason, e)
            ok = False
    except Exception as e:
        logger.error("[b24] transfer failed chat=%s reason=%s: %s", ev.chat_id, reason, e)
        ok = False

    if ok:
        sessions.mark_handoff(ev.chat_id, reason)
        await _safe_send(client, bot_id, ev.dialog_id, TRANSFER_TEXT)
        logger.info("[b24] handed off chat=%s reason=%s user=%s", ev.chat_id, reason, username)
    else:
        await _safe_send(client, bot_id, ev.dialog_id, TRANSFER_FAILED_TEXT)
    return ok


async def _safe_send(client: B24Client, bot_id: int, dialog_id: str, text: str, keyboard=None) -> int | None:
    try:
        return await client.send_message(bot_id, dialog_id, text, keyboard)
    except Exception as e:
        logger.error("[b24] send_message failed dialog=%s: %s", dialog_id, e)
        return None


async def _safe_update(client: B24Client, bot_id: int, message_id: int, text: str, keyboard=None) -> bool:
    try:
        return await client.update_message(bot_id, message_id, text, keyboard)
    except Exception as e:
        logger.warning("[b24] update_message failed msg=%s (falling back to send): %s", message_id, e)
        return False
