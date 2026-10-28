"""Bitrix24 channel — answer a client's Open Line message with the RAG pipeline,
hand the dialog to a human operator when the bot shouldn't (or can't) answer.

Runs *after* the webhook has already returned 200 (Bitrix24 wants a fast ack
and does not guarantee redelivery). Flow per ONIMBOTV2MESSAGEADD:

  1. dedup by message id (paired deliveries were seen in the wild)
  2. a person on our side spoke (employee in Bitrix24, or a manager on the
     company phone echoed by Wazzup) → the dialog is theirs, bot goes silent;
     for the phone case the session is also put in the line's queue, silently,
     so operators see it in Bitrix24 instead of it sitting on the bot
  3. session state (src/b24/sessions.py): if an operator has the dialog →
     stay silent; a new Open Line session on the same chat → bot again
  4. escalation before RAG: "Позвать оператора" button / "оператор…" /
     complaints about the bot ("это робот?") / personal-order phrases
     ("мой заказ", "рекламация"…) → transfer
  5. otherwise the message joins the chat's queue: messenger clients split
     one thought into several messages, so the bot waits until the client
     pauses (B24_DEBOUNCE_SECONDS) and answers them together; one answer at
     a time per chat, so the next one sees the previous turn in history.
     A burst that is only «спасибо» / 👍 gets no answer.
  6. answer_with_meta() in a worker thread (history from query_logs by the
     synthetic user id keyed on the chat) → one message with the answer +
     button (a text hint on Wazzup lines) → query_logs. No "ищу ответ…"
     placeholder: connectors (Wazzup → WhatsApp/Max) don't relay edits, so
     the client would see only that. An answer that itself calls for a human
     (intent `needs_human`, "переадресую вас…", the engineer's number on the
     engineer's own line) is not sent — transfer instead.
  7. N consecutive generation errors → transfer as well

ONIMBOTV2JOINCHAT resets the dialog to `bot` (Bitrix re-attaches the bot at
the start of a new session).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import timedelta
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
_HOTLINE = (
    "[b]8 800 775-03-07[/b] (бесплатно, ежедн. 10:00–21:00 НСК)\n"
    "[b]8 800 101-43-53[/b] — интернет-магазин (ежедн. 9:00–20:00 НСК)"
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
# Under every answer on Wazzup lines, in place of the button WhatsApp/Max never
# show (22–28.10: 308 answers, 0 presses). A lone «специалист» is caught by
# `_BARE_NOUN` below.
OPERATOR_HINT = "Чтобы позвать специалиста, напишите слово «специалист»."
ENGINEER_TRANSFER_TEXT = (
    "[b]Передаю диалог сервисному инженеру.[/b] Пришлите, пожалуйста, сюда же фото или видео и опишите, "
    "что случилось (для запчасти — модель, год выпуска и замеры). Инженер ответит здесь "
    "в рабочее время: пн–пт 8:00–17:00 НСК."
)

# ── Layer 1 of "wants a human" detection: instant, no LLM ────────────────
# Nouns that mean "human support" on their own — generic wishes are enough.
_SUPPORT_NOUN = r"(?:оператор\w*|поддержк\w*|техподдержк\w*|саппорт\w*)"
# Nouns that also occur in ordinary product questions ("менеджер по опту",
# "монтаж у ваших специалистов") — require a connect/contact verb.
_STAFF_NOUN = r"(?:менеджер\w*|сотрудник\w*|специалист\w*|консультант\w*|продавц\w*|продавец)"
_CONNECT_VERB = (
    r"(?:соедин\w*|переключ\w*|перевед\w*|переведи\w*|подключ\w*|позов\w*|позват\w*|свяж\w*|связат\w*"
    r"|дай(?:те)?|поговорит\w*|пообщат\w*|общат\w*|написат\w*|обратит\w*|позвон\w*|вызов\w*|вызв\w*)"
)
_GENERIC_WISH = r"(?:хочу|хотел\w*|нужен|нужна|нужно|надо|можно|давайте)"
_SPEECH_AFTER_NOUN = re.compile(
    rf"\b(?:{_SUPPORT_NOUN}|{_STAFF_NOUN})\s+(?:сказал\w*|говорил\w*|ответил\w*|посоветовал\w*|обещал\w*|звонил\w*|написал\w*)",
    re.IGNORECASE,
)
_SUPPORT_REQUEST = re.compile(rf"\b(?:{_CONNECT_VERB}|{_GENERIC_WISH})\b.*\b{_SUPPORT_NOUN}|\b{_SUPPORT_NOUN}\b.*\b(?:{_CONNECT_VERB}|{_GENERIC_WISH})\b", re.IGNORECASE | re.DOTALL)
_STAFF_REQUEST = re.compile(rf"\b{_CONNECT_VERB}\b.*\b{_STAFF_NOUN}|\b{_STAFF_NOUN}\b.*\b{_CONNECT_VERB}\b", re.IGNORECASE | re.DOTALL)
# "человек" is too common ("сколько человек нужно…"): only as a person to talk to.
_PERSON_REQUEST = re.compile(
    r"жив\w+\s+человек\w*|\bс\s+человеком\b|\bдай(?:те)?\s+человека\b|\bчеловека\s*[!.?…]*$|\bне\s+бот\w*\b",
    re.IGNORECASE,
)
# Phrases that mean "I want a person" without naming one — any length.
_STANDALONE_REQUEST = re.compile(
    r"\bпозвон\w*\s+мне\b|\bс\s+кем\s+(?:можно\s+|мне\s+)?(?:поговорить|связаться|пообщаться|общаться)\b"
    r"|\b(?:поговорить|пообщаться|связаться)\s+с\s+кем-(?:нибудь|то)\b|\bэто\s+бот\b",
    re.IGNORECASE,
)
# A one-word demand: «оператора!», «менеджера?», «поддержка».
_BARE_NOUN = re.compile(rf"^\W*(?:{_SUPPORT_NOUN}|{_STAFF_NOUN})\W*$", re.IGNORECASE)
_SHORT_MESSAGE = 80
# The client has given up on the bot: «это робот отвечает?», «переписываюсь с
# ботом», «отписками бестолковыми», «вы меня не поняли». Any length — the
# complaint is often tacked onto a long message.
_BOT_COMPLAINT = re.compile(
    r"\bробот\w*|\bбот(?:а|у|ом|ы)?\b|\bотписк\w*|\bбестолков\w*|\bерунд\w*|\bчушь\b"
    r"|\bменя\s+не\s+понял\w*|\bвы\s+не\s+понял\w*|\bне\s+понимаете\b",
    re.IGNORECASE,
)

# The answer prompt tells the model to say «Я переадресую вас оператору» on
# complaints. When the intent call times out there is no `needs_human`, and the
# promise was left hanging (22–28.10) — such an answer is a handoff.
_PROMISES_HANDOFF = re.compile(
    r"\b(?:переадресую|передаю|передам)\s+(?:вас|ваш\w*|диалог\w*)\b", re.IGNORECASE
)

# The service engineer's WhatsApp/Max, 8-999-303-09-27. Some Open Lines *are*
# that number (B24_ENGINEER_LINES): an answer sending the client there points at
# the chat they're already in, so the dialog goes to the line instead.
_ENGINEER_PHONE_RE = re.compile(r"303\D{0,3}09\D{0,3}27")

# A reply with a quote arrives from Wazzup as ">>quoted text\n \n \n<reply>" (a
# WhatsApp reaction too: ">>…\n \n \n👍"). The quote is someone else's words —
# often the bot's own answer, hint included — so it is dropped before matching.
_QUOTE_RE = re.compile(r"^>>(?:.*?\n[ \t]*\n[ \t]*\n|[^\n]*)", re.MULTILINE | re.DOTALL)

# «Спасибо», «Хорошо», 👍, ❤️ close a topic — no answer expected.
# «Да»/«нет» are not here: they usually answer the bot's question.
_ACK_WORDS = frozenset("""
спасибо спасибки спс благодарю благодарим большое огромное за всё все информацию помощь ответ
и вам вас тоже ок окей ok okay хорошо понятно ясно отлично супер класс ладно договорились
принято понял поняла поняли будем знать угу ага обязательно хорошего прекрасного доброго
удачного всего дня вечера от души бро
""".split())
_WORD_RE = re.compile(r"[a-zа-яё]+")

# Questions about the client's own order/complaint — no knowledge base can
# answer these, and the intent prompt already refuses FAQ matches for them.
_PERSONAL_ORDER_RE = re.compile(
    r"(\bмо(?:й|его|ему|ём|я|ей|ю|и|их)\s+заказ|\bзаказ\s*(?:№|#|номер)|\bномер\s+заказа|\bстатус\s+заказа"
    r"|\bгде\s+мо(?:й|я|и)\b|\bне\s+(?:пришл|привезл|доставил|отправил)|\bверн(?:уть|ите)\s+деньги"
    r"|\bвозврат\s+(?:денег|средств)|\bрекламац|\bбрак\b|\bбракован)",
    re.IGNORECASE,
)

REASON_REQUESTED = "requested"
REASON_COMPLAINT = "bot_complaint"
REASON_PERSONAL_ORDER = "personal_order"
REASON_ERRORS = "consecutive_errors"
REASON_INTENT = "intent_needs_human"
REASON_ANSWER_HANDOFF = "answer_promised_handoff"
REASON_ENGINEER = "engineer_line"
REASON_STAFF = "staff_replied"

# A new session's JOINCHAT may arrive after its first message; a handoff that
# message caused (manager's opening line from the phone) is younger than this.
_JOIN_KEEPS_HANDOFF = timedelta(seconds=30)

_SEEN_MAX = 2000
_seen_message_ids: "OrderedDict[int, None]" = OrderedDict()
_background_tasks: set[asyncio.Task] = set()


@dataclass(slots=True)
class _ChatQueue:
    """Client messages waiting for one combined answer, and the task answering them."""
    events: list[B24Event] = field(default_factory=list)
    last_at: float = 0.0
    task: asyncio.Task | None = None


_queues: dict[int, _ChatQueue] = {}


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


def with_operator_offer(ev: B24Event, text: str) -> tuple[str, list[dict] | None]:
    """The way to a human under an answer: the button where Bitrix24 can show
    it, a line of text on Wazzup lines (WhatsApp/Max get text only)."""
    if ev.via_wazzup:
        return f"{text}\n\n{OPERATOR_HINT}", None
    return text, operator_keyboard()


def is_operator_request(text: str) -> bool:
    """Layer 1: does the client explicitly ask for a person?

    Instant regex pass (layer 2 is the `needs_human` flag from the intent
    extractor, which costs an LLM call and fires after generation). Tuned to
    avoid handing off ordinary questions that merely *mention* staff:
    «оператор сказал…», «менеджер по опту», «сколько человек нужно…».
    """
    t = (text or "").strip()
    if not t:
        return False
    if t.casefold() == OPERATOR_REQUEST_TEXT.casefold():
        return True
    if _STANDALONE_REQUEST.search(t) or _BARE_NOUN.match(t):
        return True
    if len(t) > _SHORT_MESSAGE:
        return False
    if _SPEECH_AFTER_NOUN.search(t):
        return False
    return bool(_SUPPORT_REQUEST.search(t) or _STAFF_REQUEST.search(t) or _PERSON_REQUEST.search(t))


def is_personal_order(text: str) -> bool:
    return bool(_PERSONAL_ORDER_RE.search(text or ""))


def is_bot_complaint(text: str) -> bool:
    return bool(_BOT_COMPLAINT.search(text or ""))


def strip_quotes(text: str) -> str:
    return _QUOTE_RE.sub("", text or "").strip()


def escalation_reason(text: str) -> str | None:
    """Why this client message goes straight to a human, before any RAG."""
    own = strip_quotes(text)
    if is_operator_request(own):
        return REASON_REQUESTED
    if is_bot_complaint(own):
        return REASON_COMPLAINT
    if is_personal_order(own):
        return REASON_PERSONAL_ORDER
    return None


def is_acknowledgement(text: str) -> bool:
    """«Спасибо», «Хорошо», 👍, a reaction to the bot's message — nothing to answer."""
    own = strip_quotes(text)
    if "?" in own:
        return False
    return all(w in _ACK_WORDS for w in _WORD_RE.findall(own.casefold()))


def on_engineer_line(ev: B24Event) -> bool:
    line_id, _ = sessions.parse_entity_id(ev.entity_id)
    lines = {x.strip() for x in settings.b24_engineer_lines.split(",") if x.strip()}
    return line_id in lines


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
        if sessions.reset_to_bot(ev.chat_id, keep_handoff_newer_than=_JOIN_KEEPS_HANDOFF):
            logger.info("[b24] bot joined chat=%s dialog=%s — dialog state reset", ev.chat_id, ev.dialog_id)
        else:
            logger.info("[b24] bot joined chat=%s right after a handoff — dialog stays with the human", ev.chat_id)
        return

    if not mark_seen(ev.message_id):
        logger.info("[b24] duplicate delivery msg_id=%s chat=%s — skipped", ev.message_id, ev.chat_id)
        return

    state = sessions.touch(ev, operator_ttl_minutes=settings.b24_operator_ttl_minutes)
    if ev.is_staff_message:
        # Each staff message also restarts the operator TTL.
        sessions.mark_handoff(ev.chat_id, REASON_STAFF)
        logger.info("[b24] chat=%s staff replied (%s) — bot goes silent",
                    ev.chat_id, "employee" if ev.author_is_employee else "manager via connector")
        if ev.is_outgoing_echo:
            await _queue_for_operators(ev)
        return
    if state.status == STATUS_OPERATOR:
        # Usually a client talking to the operator — but it may be the first
        # message of a new session (operator closed the old one) whose JOINCHAT
        # is still on its way: Wazzup lines show a new session only by JOINCHAT,
        # delivered before or after this message. Hold it for the pause;
        # _answer answers only if the join has reset the dialog to the bot.
        logger.info("[b24] chat=%s is with a human (%s) — held in case a new session starts",
                    ev.chat_id, state.handoff_reason)
        _enqueue(ev)
        return

    bot_id = ev.bot_id or settings.b24_bot_id
    user_id, username = journal_identity(ev)
    try:
        client = B24Client(ev.client_endpoint, ev.access_token)
    except ValueError as e:
        logger.error("[b24] cannot build REST client for chat=%s: %s", ev.chat_id, e)
        return

    # Escalation is per message and immediate; whatever is still queued for
    # this chat is then left to the operator (see _answer's status check).
    if reason := escalation_reason(ev.text):
        await escalate(ev, client, bot_id, reason, user_id, username)
        return

    _enqueue(ev)


def _enqueue(ev: B24Event) -> None:
    q = _queues.setdefault(ev.chat_id, _ChatQueue())
    q.events.append(ev)
    q.last_at = time.monotonic()
    if q.task is None:
        q.task = asyncio.create_task(_drain_chat(ev.chat_id, q))


async def _drain_chat(chat_id: int, q: _ChatQueue) -> None:
    """Answer a chat's queue: wait for a pause, answer everything gathered,
    repeat while messages keep coming (including those sent mid-generation)."""
    try:
        while q.events:
            while (wait := q.last_at + settings.b24_debounce_seconds - time.monotonic()) > 0:
                await asyncio.sleep(wait)
            batch, q.events = q.events, []
            try:
                await _answer(batch)
            except Exception:
                logger.exception("[b24] chat=%s: answering %d message(s) failed", chat_id, len(batch))
    finally:
        q.task = None
        if _queues.get(chat_id) is q and not q.events:
            del _queues[chat_id]


async def _answer(batch: list[B24Event]) -> None:
    # The newest event carries the freshest access_token.
    ev = batch[-1]
    if len(batch) > 1:
        ev = replace(ev, text="\n".join(e.text.strip() for e in batch))
    if sessions.get_status(ev.chat_id) == STATUS_OPERATOR:
        logger.info("[b24] chat=%s is with a human — %d queued message(s) left to them", ev.chat_id, len(batch))
        return
    if len(batch) > 1:
        logger.info("[b24] chat=%s: %d messages answered together", ev.chat_id, len(batch))

    bot_id = ev.bot_id or settings.b24_bot_id
    user_id, username = journal_identity(ev)
    client = B24Client(ev.client_endpoint, ev.access_token)

    # Messages held while the chat looked human-handled skipped the instant
    # escalation checks in handle_event; for the rest this is a no-op re-check.
    for e in batch:
        if reason := escalation_reason(e.text):
            await escalate(ev, client, bot_id, reason, user_id, username)
            return
    if all(is_acknowledgement(e.text) for e in batch):
        logger.info("[b24] chat=%s: %r is a thank-you — no answer", ev.chat_id, ev.text[:80])
        return

    t0 = time.monotonic()
    try:
        generator = await get_eval_generator()

        def worker():
            with SessionLocal() as session:
                return generator.answer_with_meta(session, ev.text, user_id=user_id)

        answer_html, meta = await asyncio.to_thread(worker)
    except Exception as e:
        logger.error("[b24] answer generation failed chat=%s: %s", ev.chat_id, e, exc_info=True)
        answer_html, meta = FALLBACK_TEXT, _error_meta()

    if sessions.get_status(ev.chat_id) == STATUS_OPERATOR:
        # A manager stepped in (or the client asked for one) during the 10–60 s
        # of generation — a late bot answer would talk over them.
        logger.info("[b24] chat=%s taken over while generating — answer dropped", ev.chat_id)
        return

    is_error = meta.query_type == "ERROR"
    if not is_error and (reason := _answer_handoff_reason(ev, answer_html, meta)):
        # The generated answer is not delivered — the client gets the handoff
        # message instead.
        logger.info("[b24] chat=%s %s — handing off (unsent answer: %r)", ev.chat_id, reason, answer_html[:200])
        notice = ENGINEER_TRANSFER_TEXT if reason == REASON_ENGINEER else TRANSFER_TEXT
        await escalate(ev, client, bot_id, reason, user_id, username, notice=notice)
        return

    text = answer_html if is_error else html_to_bbcode(answer_html)
    message_id = await _safe_send(client, bot_id, ev.dialog_id, *with_operator_offer(ev, text))
    delivered = message_id is not None

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
        bot_message_id=message_id,
    )
    if log_id and answer_html and not is_error:
        spawn_judge(log_id, ev.text, answer_html, tag="b24")

    errors = sessions.mark_bot_turn(ev.chat_id, error=is_error)
    logger.info(
        "[b24] answered chat=%s log=%s type=%s delivered=%s total=%dms (intent=%s ret=%s ans=%s model=%s)",
        ev.chat_id, log_id, meta.query_type, delivered,
        int((time.monotonic() - t0) * 1000),
        meta.t_intent_ms, meta.t_retrieval_ms, meta.t_answer_ms, meta.t_answer_model,
    )
    if is_error and errors >= settings.b24_max_consecutive_errors:
        logger.warning("[b24] chat=%s: %d consecutive errors — escalating", ev.chat_id, errors)
        await escalate(ev, client, bot_id, REASON_ERRORS, user_id, username, log_turn=False)


def _answer_handoff_reason(ev: B24Event, answer_html: str, meta) -> str | None:
    """Does the generated answer itself call for a human instead of being sent?"""
    if getattr(meta, "needs_human", False):
        # Layer 2: Haiku read the question as "wants a person / own-order complaint".
        return REASON_INTENT
    if _PROMISES_HANDOFF.search(answer_html):
        return REASON_ANSWER_HANDOFF
    if on_engineer_line(ev) and _ENGINEER_PHONE_RE.search(answer_html):
        return REASON_ENGINEER
    return None


async def escalate(
    ev: B24Event,
    client: B24Client,
    bot_id: int,
    reason: str,
    user_id: int,
    username: str,
    *,
    log_turn: bool = True,
    notice: str = TRANSFER_TEXT,
) -> bool:
    """Tell the client, hand the Open Line dialog to a human, remember it.

    Returns True if Bitrix accepted the transfer. On failure the client also
    gets the hotline and the dialog stays with the bot.
    """
    if log_turn:
        log_id = save_query_log(
            question=ev.text, answer=notice, query_type="OPERATOR",
            user_id=user_id, username=username,
        )
        set_feedback(log_id, "operator")  # shows up under the Journal's 🆘 filter like Telegram

    # Say it before the transfer: once an operator picks the dialog up, the bot
    # can lose write access to the chat (ACCESS_DENIED seen on the live portal).
    await _safe_send(client, bot_id, ev.dialog_id, notice)
    ok = await _transfer(ev, client, reason)

    if ok:
        sessions.mark_handoff(ev.chat_id, reason)
        logger.info("[b24] handed off chat=%s reason=%s user=%s", ev.chat_id, reason, username)
    else:
        await _safe_send(client, bot_id, ev.dialog_id, TRANSFER_FAILED_TEXT)
    return ok


async def _transfer(ev: B24Event, client: B24Client, reason: str) -> bool:
    """Hand the Open Line session to the line's queue (or B24_TRANSFER_TO).

    True if Bitrix accepted it or the session is no longer the bot's to give.
    """
    try:
        if settings.b24_transfer_to:
            return await client.session_transfer(ev.chat_id, settings.b24_transfer_to)
        return await client.session_operator(ev.chat_id)
    except B24Error as e:
        if e.code == "WRONG_CHAT":
            # "Operator is not a bot" — the session is already with a human.
            logger.info("[b24] chat=%s already handled by an operator (%s)", ev.chat_id, e)
            return True
        logger.error("[b24] transfer failed chat=%s reason=%s: %s", ev.chat_id, reason, e)
    except Exception as e:
        logger.error("[b24] transfer failed chat=%s reason=%s: %s", ev.chat_id, reason, e)
    return False


async def _queue_for_operators(ev: B24Event) -> None:
    """A manager wrote from the phone / Wazzup, outside Bitrix24: put the session
    in the line's queue so operators see it and one can take it. Nothing goes to
    the client. Tried on every such message — stateless, so it survives the
    JOINCHAT races; once the session is no longer the bot's, Bitrix answers
    WRONG_CHAT and nothing changes."""
    try:
        client = B24Client(ev.client_endpoint, ev.access_token)
    except ValueError as e:
        logger.error("[b24] cannot build REST client for chat=%s: %s", ev.chat_id, e)
        return
    if await _transfer(ev, client, REASON_STAFF):
        logger.info("[b24] chat=%s: session put in the line queue (manager wrote outside Bitrix24)", ev.chat_id)


async def _safe_send(client: B24Client, bot_id: int, dialog_id: str, text: str, keyboard=None) -> int | None:
    try:
        return await client.send_message(bot_id, dialog_id, text, keyboard)
    except Exception as e:
        logger.error("[b24] send_message failed dialog=%s: %s", dialog_id, e)
        return None
