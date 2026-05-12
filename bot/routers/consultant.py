"""Main Q&A handler with feedback buttons."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.core.config import settings
from src.core.database import SessionLocal
from src.logs.models import QueryLog
from src.rag.answer_generator import AnswerGenerator, AnswerMeta

logger = logging.getLogger("teplodarbot")
router = Router()

_FEEDBACK_LOG = Path("base/feedback.jsonl")
_FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)

# In-memory store: bot_msg_id → {"user_id", "question", "answer", "meta", "log_id"}
_msg_store: dict[int, dict] = {}

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


BOT_VERSION = "1.1"


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
        return entry
    # Bot was restarted — recover from DB
    try:
        with SessionLocal() as s:
            from sqlalchemy import select
            row = s.execute(
                select(QueryLog).where(QueryLog.bot_message_id == bot_msg_id)
            ).scalar_one_or_none()
            if row:
                return {
                    "log_id": row.id,
                    "question": row.question,
                    "answer": row.answer,
                    "user_id": row.user_id,
                    "username": row.username or "",
                    "meta": {"query_type": row.query_type},
                }
    except Exception as e:
        logger.warning("DB fallback for feedback failed: %s", e)
    return {}


def _set_feedback_in_log(log_id: int | None, feedback: str) -> None:
    if log_id is None:
        return
    try:
        with SessionLocal() as s:
            row = s.get(QueryLog, log_id)
            if row:
                row.feedback = feedback
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


def _call_generator(query: str) -> tuple[str, AnswerMeta]:
    with SessionLocal() as session:
        return _generator.answer_with_meta(session, query)


@router.message(F.text)
async def handle_question(message: Message) -> None:
    if _generator is None:
        await message.answer("⏳ Бот ещё загружается, попробуйте через несколько секунд.")
        return

    query = message.text.strip()
    if not query:
        return

    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(_typing_loop(message.bot, message.chat.id, stop_event))

    try:
        answer, meta = await asyncio.to_thread(_call_generator, query)
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

    bot_msg = await message.answer(full_text, reply_markup=_feedback_kb(0))
    real_kb = _feedback_kb(bot_msg.message_id)
    await bot_msg.edit_reply_markup(reply_markup=real_kb)

    log_id = _save_query_log(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        question=query,
        answer=answer,
        meta=meta,
        bot_message_id=bot_msg.message_id,
    )

    _msg_store[bot_msg.message_id] = {
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
    }


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
async def handle_bad(callback: CallbackQuery) -> None:
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
    await callback.answer("👎 Спасибо! Учтём и постараемся улучшиться.", show_alert=False)
    logger.info("Feedback BAD user=%s q=%r", callback.from_user.id, entry.get("question", "")[:60])


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
