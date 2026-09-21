"""Bitrix24 channel — answer a client's Open Line message with the RAG pipeline.

Stage 2. Runs *after* the webhook has already returned 200 (Bitrix24 wants a
fast ack and does not guarantee redelivery). Flow per event:

  1. dedup by message id (paired deliveries were seen in the wild)
  2. "Позвать оператора" → stub reply with hotline (stage 3 will transfer)
  3. send a placeholder ("ищу ответ…") — the pipeline takes 30-40 s and a
     silent web chat looks frozen
  4. answer_with_meta() in a worker thread; history comes from query_logs by
     the synthetic user id, exactly like Telegram (30-minute window)
  5. persist the turn to query_logs (Journal, judge, history) as
     user_id = synthetic(-), username = "b24:…"
  6. edit the placeholder into the answer (+ "Позвать оператора" button);
     if the edit fails, send a new message instead
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
from src.b24.client import B24Client
from src.b24.format import html_to_bbcode
from src.b24.webhook import B24Event
from src.core.config import settings
from src.core.database import SessionLocal
from src.logs.queries import save_query_log, synthetic_user_id

logger = logging.getLogger(__name__)

OPERATOR_REQUEST_TEXT = "Позвать оператора"
PLACEHOLDER_TEXT = "Секунду, ищу ответ в базе знаний…"
FALLBACK_TEXT = (
    "Извините, не удалось получить ответ. Попробуйте ещё раз или позвоните нам:\n"
    "[b]8 800 775-03-07[/b] (бесплатно, ежедневно 10:00–21:00 МСК)"
)
# Stage 3 replaces this with a real imopenlines.bot.session.operator call.
OPERATOR_STUB_TEXT = (
    "[b]Запрос принят.[/b] Оператор подключится к диалогу.\n\n"
    "Если срочно — звоните прямо сейчас:\n"
    "[b]8 800 775-03-07[/b] (бесплатно, ежедн. 10:00–21:00 МСК)\n"
    "[b]8 800 101-43-53[/b] — интернет-магазин (ежедн. 9:00–20:00 МСК)"
)
_OPERATOR_RE = re.compile(r"\b(оператор\w*|человек\w*|менеджер\w*|живой)\b", re.IGNORECASE)

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


_SEEN_MAX = 2000
_seen_message_ids: "OrderedDict[int, None]" = OrderedDict()
_background_tasks: set[asyncio.Task] = set()


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
    if not mark_seen(ev.message_id):
        logger.info("[b24] duplicate delivery msg_id=%s chat=%s — skipped", ev.message_id, ev.chat_id)
        return

    bot_id = ev.bot_id or settings.b24_bot_id
    user_id, username = journal_identity(ev)
    try:
        client = B24Client(ev.client_endpoint, ev.access_token)
    except ValueError as e:
        logger.error("[b24] cannot build REST client for chat=%s: %s", ev.chat_id, e)
        return

    if is_operator_request(ev.text):
        logger.warning("[b24] operator requested chat=%s user=%s — transfer not implemented yet (stage 3)", ev.chat_id, username)
        save_query_log(
            question=ev.text, answer=OPERATOR_STUB_TEXT, query_type="OPERATOR",
            user_id=user_id, username=username,
        )
        await _safe_send(client, bot_id, ev.dialog_id, OPERATOR_STUB_TEXT)
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
    if log_id and answer_html and meta.query_type != "ERROR":
        spawn_judge(log_id, ev.text, answer_html, tag="b24")

    text = html_to_bbcode(answer_html) if meta.query_type != "ERROR" else answer_html
    keyboard = operator_keyboard()
    delivered = False
    if placeholder_id:
        delivered = await _safe_update(client, bot_id, placeholder_id, text, keyboard)
    if not delivered:
        delivered = (await _safe_send(client, bot_id, ev.dialog_id, text, keyboard)) is not None

    logger.info(
        "[b24] answered chat=%s log=%s type=%s delivered=%s via=%s total=%dms (intent=%s ret=%s ans=%s model=%s)",
        ev.chat_id, log_id, meta.query_type, delivered, "update" if placeholder_id and delivered else "send",
        int((time.monotonic() - t0) * 1000),
        meta.t_intent_ms, meta.t_retrieval_ms, meta.t_answer_ms, meta.t_answer_model,
    )


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
