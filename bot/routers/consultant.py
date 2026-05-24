"""Main Q&A handler with feedback buttons."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


class BadFeedback(StatesGroup):
    waiting_for_note = State()  # user pressed 👎, we're waiting for the explanation

from src.core.config import settings
from collections import OrderedDict

from sqlalchemy import update

from src.core.database import SessionLocal
from src.logs.models import QueryLog
from src.rag.answer_generator import AnswerGenerator, AnswerMeta
from src.synonyms.store import get_synonym_store

logger = logging.getLogger("teplodarbot")
router = Router()

_FEEDBACK_LOG = Path("base/feedback.jsonl")
_FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)

# Bounded LRU: bot_msg_id → entry. Evicts oldest beyond the cap so a long-
# running bot can't leak memory from inactive chats.
_MSG_STORE_MAX = 2000
_msg_store: "OrderedDict[int, dict]" = OrderedDict()


def _msg_store_set(key: int, entry: dict) -> None:
    _msg_store[key] = entry
    _msg_store.move_to_end(key)
    while len(_msg_store) > _MSG_STORE_MAX:
        _msg_store.popitem(last=False)


# Background-task registry — must hold strong refs to asyncio.Task objects,
# otherwise the event loop's weak reference lets the GC collect tasks before
# they finish (documented anti-pattern, Python issue 88831).
_background_tasks: set[asyncio.Task] = set()

# Bounded parallelism for the judge — avoids DoS-ing ourselves with concurrent
# Claude CLI subprocesses on a traffic spike. ~2 keeps Pro rate-limits sane
# and matches eval workers.
#
# NOTE: this semaphore is per-process. Bot, admin and eval-workers each have
# their own — under heavy load the total concurrent Claude CLI subprocess
# count is bot_cap (2) + admin eval workers (4) + N answer-generation calls.
# If Pro 429s become frequent, replace with a file-lock or posix_ipc named
# semaphore in `src/core/claude_token.py`.
_judge_semaphore: asyncio.Semaphore | None = None  # lazily inited on first use


def _get_judge_semaphore() -> asyncio.Semaphore:
    global _judge_semaphore
    if _judge_semaphore is None:
        _judge_semaphore = asyncio.Semaphore(2)
    return _judge_semaphore


_generator: AnswerGenerator | None = None


def init_generator(gen: AnswerGenerator) -> None:
    global _generator
    _generator = gen


def _feedback_kb(bot_msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍", callback_data=f"fb:good:{bot_msg_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"fb:bad:{bot_msg_id}"),
        ],
        [
            InlineKeyboardButton(text="🆘 Позвать оператора", callback_data=f"fb:operator:{bot_msg_id}"),
        ],
    ])


BOT_VERSION = "1.3.2"


def _debug_footer(meta: AnswerMeta) -> str:
    """Debug block at the bottom of each bot answer."""
    qtype_short = {
        "RAG_PRODUCT": "RAG",
        "FAQ_COMPANY": "О компании",
        "FAQ_DEALER":  "Дилер",
        "FAQ_EXACT":   "FAQ",
    }.get(meta.query_type, meta.query_type)

    parts = [f"v{BOT_VERSION}", f"<code>{qtype_short}</code>"]

    if meta.query_type == "RAG_PRODUCT":
        if meta.top_score is not None:
            score_emoji = "🟢" if meta.top_score >= 0.85 else ("🟡" if meta.top_score >= 0.80 else "🔴")
            parts.append(f"{score_emoji} score <code>{meta.top_score:.3f}</code>")
        parts.append(f"chunks <code>{meta.chunks_used}</code>")

    elif meta.query_type == "FAQ_DEALER":
        if meta.city:
            parts.append(f"🏙 <code>{meta.city}</code>")
        if meta.shops_count:
            parts.append(f"🏪 <code>{meta.shops_count}</code> маг.")
        elif meta.city:
            parts.append("❓ не найден")

    if meta.latency_ms is not None:
        parts.append(f"⏱ <code>{meta.latency_ms / 1000:.1f}с</code>")

    line = "\n\n<i>🔧 " + " · ".join(parts) + "</i>"

    # Per-phase timing breakdown — collapses to nothing if no phase ran.
    timing_bits: list[str] = []
    if meta.t_intent_ms is not None:
        timing_bits.append(f"intent <code>{meta.t_intent_ms}мс</code>")
    if meta.t_retrieval_ms is not None:
        timing_bits.append(f"ret <code>{meta.t_retrieval_ms}мс</code>")
    if meta.t_answer_ms is not None:
        timing_bits.append(f"ans <code>{meta.t_answer_ms}мс</code>")
    if meta.t_answer_model:
        timing_bits.append(f"model <code>{meta.t_answer_model}</code>")
    if timing_bits:
        line += "\n<i>⏲ " + " · ".join(timing_bits) + "</i>"

    if meta.reformulated_query:
        short = meta.reformulated_query[:90] + ("…" if len(meta.reformulated_query) > 90 else "")
        line += f"\n<i>🔍 <code>{short}</code></i>"

    return line


def _log_feedback(entry: dict) -> None:
    try:
        with open(_FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Feedback log write failed: %s", e)


def _save_query_log(user_id: int, username: str, question: str, answer: str, meta: AnswerMeta, bot_message_id: int | None = None) -> int | None:
    """Persist query to DB, return row id."""
    try:
        with SessionLocal() as s:
            row = QueryLog(
                user_id=user_id,
                username=username or None,
                question=question,
                answer=answer,
                query_type=meta.query_type,
                top_score=meta.top_score,
                chunks_used=meta.chunks_used or None,
                city=meta.city or None,
                reformulated_query=meta.reformulated_query or None,
                bot_message_id=bot_message_id,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.id
    except Exception as e:
        logger.warning("Query log write failed: %s", e)
        return None


def _get_log_entry(bot_msg_id: int) -> dict:
    """Get entry from memory store or fall back to DB lookup."""
    entry = _msg_store.get(bot_msg_id)
    if entry:
        # Refresh LRU position — active conversations shouldn't get evicted
        # while idle chats are sitting near the front of the OrderedDict.
        _msg_store.move_to_end(bot_msg_id)
        return entry
    # Bot was restarted — recover from DB
    try:
        with SessionLocal() as s:
            from sqlalchemy import select
            row = s.execute(
                select(QueryLog).where(QueryLog.bot_message_id == bot_msg_id)
            ).scalar_one_or_none()
            if row:
                recovered = {
                    "log_id": row.id,
                    "question": row.question,
                    "answer": row.answer,
                    "user_id": row.user_id,
                    "username": row.username or "",
                    "meta": {"query_type": row.query_type},
                }
                # Cache recovery so subsequent feedback clicks on the same
                # message don't hit the DB again.
                _msg_store_set(bot_msg_id, recovered)
                return recovered
    except Exception as e:
        logger.warning("DB fallback for feedback failed: %s", e)
    return {}


async def _judge_in_background(log_id: int, question: str, answer: str) -> None:
    """Run the LLM-as-judge after the user already got the response.

    Bound by a global semaphore so a traffic spike doesn't fan out into N
    parallel Claude CLI subprocesses. Updates ONLY usefulness_* columns
    via explicit UPDATE so a concurrent user-feedback write (👍/👎) on the
    same row doesn't race-overwrite. Failures swallowed — best effort.
    """
    try:
        async with _get_judge_semaphore():
            from src.eval.judge import judge_answer
            # Off the event loop — subprocess call to Claude CLI is blocking
            verdict = await asyncio.to_thread(
                judge_answer, question, answer,
                settings.claude_cli_path,
                settings.claude_reformulation_model,  # Haiku
            )
            if not verdict:
                return
            with SessionLocal() as s:
                # Targeted UPDATE: do NOT load the row through ORM and re-emit
                # every column — feedback / feedback_note might have been
                # written by another transaction during the ~2s judge call.
                stmt = (
                    update(QueryLog)
                    .where(QueryLog.id == log_id)
                    .values(
                        usefulness_score=verdict["score"],
                        usefulness_verdict=verdict["verdict"],
                    )
                )
                s.execute(stmt)
                s.commit()
        logger.info(
            "Judge log=%s score=%d (%s)",
            log_id, verdict["score"], verdict["verdict"][:80],
        )
    except Exception as e:
        logger.warning("Background judge failed for log=%s: %s", log_id, e)


def _set_feedback_in_log(log_id: int | None, feedback: str, note: str | None = None) -> None:
    if log_id is None:
        return
    try:
        with SessionLocal() as s:
            row = s.get(QueryLog, log_id)
            if row:
                row.feedback = feedback
                if note is not None:
                    row.feedback_note = note
                s.commit()
    except Exception as e:
        logger.warning("Feedback update failed: %s", e)


async def _typing_loop(bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        await asyncio.sleep(4)


# Telegram edit_message_text rate-limits at roughly 1/sec per chat. We
# throttle intermediate edits to a slightly longer interval so streaming
# can't hit the rate-limit ceiling. Telegram also caps a single message at
# 4096 chars — we leave headroom for the debug footer and "…" indicator.
_STREAM_EDIT_INTERVAL_SEC = 1.2
_TELEGRAM_MSG_MAX = 3800


async def _run_generator_streaming(
    query: str,
    user_id: int,
    on_delta,
) -> tuple[str, AnswerMeta]:
    """Run the (blocking) generator in a thread, forwarding text deltas
    back to the async event loop via `on_delta(text)` — which is a thread-
    safe scheduling closure that the caller built around `call_soon_threadsafe`.
    """
    def _worker() -> tuple[str, AnswerMeta]:
        with SessionLocal() as session:
            return _generator.answer_with_meta(
                session, query, user_id=user_id, on_chunk=on_delta,
            )
    return await asyncio.to_thread(_worker)


@router.message(StateFilter(None), F.text)
async def handle_question(message: Message) -> None:
    if _generator is None:
        await message.answer("⏳ Бот ещё загружается, попробуйте через несколько секунд.")
        return

    query = message.text.strip()
    if not query:
        return

    # Substitute admin-managed synonyms before anything else — fuzzy terms
    # like "трус двенадцать" → "Русь-12" or "билетная горелка" → "пеллетная
    # горелка" become canonical before the intent extractor sees them, so
    # retrieval and FAQ matching work as intended.
    canonical_query = get_synonym_store().apply(query)
    if canonical_query != query:
        logger.info("Synonyms applied: %r → %r", query, canonical_query)
        query = canonical_query

    # Send placeholder immediately so the user sees something within 100ms
    # while intent extraction (Haiku ~3-5s) runs.
    bot_msg = await message.answer("⏳ <i>Готовлю ответ…</i>", reply_markup=_feedback_kb(0))

    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(_typing_loop(message.bot, message.chat.id, stop_event))

    # Stream-bridge: worker thread pushes deltas through call_soon_threadsafe
    # to the asyncio.Queue we drain in this coroutine.
    loop = asyncio.get_running_loop()
    delta_queue: asyncio.Queue = asyncio.Queue()

    def _on_delta_threadsafe(delta: str) -> None:
        loop.call_soon_threadsafe(delta_queue.put_nowait, delta)

    gen_task = asyncio.create_task(
        _run_generator_streaming(query, message.from_user.id, _on_delta_threadsafe),
    )

    # Drain deltas while generator runs; edit message periodically.
    accumulated_raw = ""
    last_edit_at = 0.0
    try:
        while not gen_task.done() or not delta_queue.empty():
            try:
                delta = await asyncio.wait_for(delta_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            accumulated_raw += delta
            now = loop.time()
            if now - last_edit_at >= _STREAM_EDIT_INTERVAL_SEC:
                preview = accumulated_raw
                if len(preview) > _TELEGRAM_MSG_MAX:
                    preview = preview[-_TELEGRAM_MSG_MAX:]
                try:
                    await bot_msg.edit_text(preview + " ▌", parse_mode=None)
                    last_edit_at = now
                except Exception as e:
                    # TelegramBadRequest (message-not-modified, parse errors) etc.
                    logger.debug("intermediate edit failed: %s", e)

        answer, meta = await gen_task
        # No final drain needed — `answer` is the authoritative text
        # (assembled by `_stream_collect` from the same deltas via the
        # parts list), and the final `bot_msg.edit_text(full_text)` below
        # replaces the preview entirely. `accumulated_raw` is only used
        # for the intermediate "▌"-suffixed previews while streaming.
    except Exception as e:
        logger.error("Generator error: %s", e, exc_info=True)
        answer = (
            "Извините, не удалось получить ответ. Попробуйте ещё раз или позвоните нам:\n"
            "<b>8 800 775-03-07</b> (бесплатно, ежедневно 10:00–21:00 МСК)"
        )
        meta = AnswerMeta(query_type="ERROR")
    finally:
        stop_event.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    full_text = answer + _debug_footer(meta)
    # Final edit — full HTML-rendered text, real keyboard.
    try:
        await bot_msg.edit_text(full_text, reply_markup=_feedback_kb(bot_msg.message_id))
    except Exception as e:
        logger.warning("final edit failed (%s) — sending as new message", e)
        # New message gets NO keyboard until we know its real message_id —
        # a placeholder `_feedback_kb(0)` would mean clicks during the
        # gap between send and edit_reply_markup hit a dead lookup. Send
        # without keyboard first, then attach with the correct id.
        bot_msg = await message.answer(full_text)
        try:
            await bot_msg.edit_reply_markup(reply_markup=_feedback_kb(bot_msg.message_id))
        except Exception as e2:
            logger.warning("fallback keyboard re-bind failed: %s", e2)

    log_id = _save_query_log(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        question=query,
        answer=answer,
        meta=meta,
        bot_message_id=bot_msg.message_id,
    )

    # Fire-and-forget LLM judge — user already received the answer, this
    # adds a usefulness score to the journal row in the background.
    # Strong-ref the task in _background_tasks so Python's GC doesn't drop
    # it before completion (anti-pattern: bare create_task without ref).
    if log_id and answer and meta.query_type != "ERROR":
        task = asyncio.create_task(_judge_in_background(log_id, query, answer))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    _msg_store_set(bot_msg.message_id, {
        "user_id": message.from_user.id,
        "username": message.from_user.username or "",
        "question": query,
        "answer": answer,
        "log_id": log_id,
        "meta": {
            "query_type": meta.query_type,
            "top_score": meta.top_score,
            "chunks_used": meta.chunks_used,
            "city": meta.city,
            "shops_count": meta.shops_count,
        },
    })


@router.callback_query(F.data.startswith("fb:good:"))
async def handle_good(callback: CallbackQuery) -> None:
    bot_msg_id = int(callback.data.split(":")[-1])
    entry = _get_log_entry(bot_msg_id)
    _set_feedback_in_log(entry.get("log_id"), "good")
    _log_feedback({
        "ts": datetime.now().isoformat(),
        "type": "good",
        "user_id": callback.from_user.id,
        "question": entry.get("question", ""),
        "answer": entry.get("answer", ""),
        "meta": entry.get("meta", {}),
    })
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("👍 Спасибо за оценку!", show_alert=False)
    logger.info("Feedback GOOD user=%s q=%r", callback.from_user.id, entry.get("question", "")[:60])


@router.callback_query(F.data.startswith("fb:bad:"))
async def handle_bad(callback: CallbackQuery, state: FSMContext) -> None:
    bot_msg_id = int(callback.data.split(":")[-1])
    entry = _get_log_entry(bot_msg_id)
    _set_feedback_in_log(entry.get("log_id"), "bad")
    _log_feedback({
        "ts": datetime.now().isoformat(),
        "type": "bad",
        "user_id": callback.from_user.id,
        "question": entry.get("question", ""),
        "answer": entry.get("answer", ""),
        "meta": entry.get("meta", {}),
    })
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    logger.info("Feedback BAD user=%s q=%r", callback.from_user.id, entry.get("question", "")[:60])

    # Enter FSM: wait for the user to type why the answer was bad.
    await state.set_state(BadFeedback.waiting_for_note)
    await state.update_data(log_id=entry.get("log_id"), question=entry.get("question", ""))
    await callback.message.answer(
        "👎 Спасибо за оценку! Подскажите, пожалуйста:\n"
        "• <b>Что не так</b> с ответом?\n"
        "• <b>Что нужно было ответить</b> по вашему мнению?\n\n"
        "Можно одним сообщением. Или напишите /skip — пропустить.",
    )


@router.message(BadFeedback.waiting_for_note, F.text == "/skip")
async def handle_bad_skip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, пропустили. Спасибо за оценку!")


@router.message(BadFeedback.waiting_for_note, F.text)
async def handle_bad_note(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    log_id = data.get("log_id")
    note = (message.text or "").strip()[:4000]
    _set_feedback_in_log(log_id, "bad", note=note)
    _log_feedback({
        "ts": datetime.now().isoformat(),
        "type": "bad_note",
        "user_id": message.from_user.id,
        "log_id": log_id,
        "question": data.get("question", ""),
        "note": note,
    })
    await state.clear()
    await message.answer("Спасибо! Передал команде — постараемся улучшить.")
    logger.info("Feedback NOTE user=%s log=%s note=%r", message.from_user.id, log_id, note[:80])


@router.callback_query(F.data.startswith("fb:operator:"))
async def handle_operator(callback: CallbackQuery) -> None:
    bot_msg_id = int(callback.data.split(":")[-1])
    entry = _get_log_entry(bot_msg_id)
    _set_feedback_in_log(entry.get("log_id"), "operator")
    _log_feedback({
        "ts": datetime.now().isoformat(),
        "type": "operator",
        "user_id": callback.from_user.id,
        "question": entry.get("question", ""),
    })

    if settings.operator_chat_id:
        user = callback.from_user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
        username = f"@{user.username}" if user.username else f"id:{user.id}"
        notify_text = (
            f"🆘 <b>Запрос оператора</b>\n\n"
            f"👤 {name} ({username})\n"
            f"❓ Вопрос: {entry.get('question', '—')}"
        )
        try:
            await callback.bot.send_message(settings.operator_chat_id, notify_text)
        except Exception as e:
            logger.warning("Failed to notify operator chat: %s", e)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🆘 <b>Запрос принят.</b>\n\n"
        "Оператор свяжется с вами в ближайшее время.\n\n"
        "Если срочно — звоните прямо сейчас:\n"
        "📞 <b>8 800 775-03-07</b> (бесплатно, ежедн. 10:00–21:00 МСК)\n"
        "📞 <b>8 800 101-43-53</b> — интернет-магазин (ежедн. 9:00–20:00 МСК)"
    )
    await callback.answer()
    logger.info("Operator requested user=%s q=%r", callback.from_user.id, entry.get("question", "")[:60])
