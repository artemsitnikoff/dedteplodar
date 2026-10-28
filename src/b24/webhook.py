"""Parsing and verification of Bitrix24 imbot v2 webhook events.

Bitrix24 delivers events as ``application/x-www-form-urlencoded`` built with
PHP's ``http_build_query``: nested keys look like ``data[message][text]`` and
every scalar arrives as a string (``"0"``/``"1"`` for booleans, ``""`` for
null). This module turns that into a nested dict and a typed ``B24Event``.

Pure functions, no FastAPI / DB imports — easy to unit-test with the captured
payload in BITRIX24.md (appendix A).
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

# Keys whose values must never reach logs.
SECRET_KEYS = frozenset({"access_token", "refresh_token", "application_token", "botToken"})

EVENT_MESSAGE_ADD = "ONIMBOTV2MESSAGEADD"
EVENT_COMMAND_ADD = "ONIMBOTV2COMMANDADD"
EVENT_JOIN_CHAT = "ONIMBOTV2JOINCHAT"
ENTITY_TYPE_OPEN_LINES = "LINES"

# Wazzup (the WhatsApp/Max connector) copies into the Open Line what a manager
# typed on the company phone, and its own notices — authored by the *client*
# user, told apart only by a marker line (seen on the live portal 2026-10-08):
#   "=== Исходящее сообщение, автор: Телефон ===\n<manager's text>"
#   "=== SYSTEM WZ === Пропущенный звонок от клиента."
# A reply with a quote puts ">>quoted\n \n \n" in front, hence MULTILINE.
_WZ_OUTGOING_RE = re.compile(r"^===\s*Исходящее сообщение\b", re.MULTILINE)
_WZ_SYSTEM_RE = re.compile(r"^===\s*SYSTEM WZ\s*===", re.MULTILINE)


def parse_php_form(body: bytes | str) -> dict[str, Any]:
    """Decode a PHP-style form body into a nested dict.

    ``a[b][c]=1&a[d]=2`` → ``{"a": {"b": {"c": "1"}, "d": "2"}}``.
    Numeric segments stay string keys (``{"0": ...}``) — Bitrix payloads we
    care about are all associative, and this keeps the shape predictable.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    result: dict[str, Any] = {}
    for key, value in parse_qsl(body, keep_blank_values=True):
        head, _, rest = key.partition("[")
        parts = [head] + [p.rstrip("]") for p in rest.split("[")] if rest else [head]
        cursor = result
        for part in parts[:-1]:
            nxt = cursor.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cursor[part] = nxt
            cursor = nxt
        cursor[parts[-1]] = value
    return result


def mask_secrets(obj: Any) -> Any:
    """Return a deep copy with token-like values shortened to ``head…tail``."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in SECRET_KEYS and isinstance(v, str) and len(v) > 12:
                out[k] = f"{v[:6]}…{v[-4:]}"
            else:
                out[k] = mask_secrets(v)
        return out
    if isinstance(obj, list):
        return [mask_secrets(v) for v in obj]
    return obj


def verify_application_token(payload: dict[str, Any], expected: str) -> bool:
    """Constant-time check of the top-level ``auth[application_token]``.

    Only the envelope token proves the request came from our portal; the
    copy under ``data[bot][auth]`` is the bot's own credential set.
    """
    if not expected:
        return False
    got = _dig(payload, "auth", "application_token")
    return isinstance(got, str) and secrets.compare_digest(got, expected)


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    for p in path:
        if not isinstance(obj, dict) or p not in obj:
            return default
        obj = obj[p]
    return obj


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class B24Event:
    """The subset of an imbot v2 event we act on (all events share the envelope)."""

    event: str
    ts: int | None
    # bot + credentials for callbacks (fresh access_token in every event)
    bot_id: int | None
    bot_code: str
    access_token: str
    client_endpoint: str
    # message (ONIMBOTV2MESSAGEADD / COMMANDADD)
    message_id: int | None
    chat_id: int | None
    dialog_id: str
    text: str
    # chat
    entity_type: str
    entity_id: str
    chat_name: str
    # author
    user_id: int | None
    user_name: str
    author_is_bot: bool
    author_is_employee: bool
    language: str

    @property
    def is_message(self) -> bool:
        return self.event == EVENT_MESSAGE_ADD

    @property
    def is_join(self) -> bool:
        return self.event == EVENT_JOIN_CHAT

    @property
    def is_open_line(self) -> bool:
        return self.entity_type == ENTITY_TYPE_OPEN_LINES

    @property
    def via_wazzup(self) -> bool:
        """A WhatsApp/Max line run through Wazzup (``wz_<channel>_…|<line>|…``).
        Wazzup relays text only: Bitrix24 keyboards never reach the client."""
        return self.entity_id.startswith("wz_")

    @property
    def is_outgoing_echo(self) -> bool:
        """A manager's message sent from the company phone, echoed by Wazzup as the client's."""
        return bool(_WZ_OUTGOING_RE.search(self.text))

    @property
    def is_connector_notice(self) -> bool:
        """A Wazzup service line («Пропущенный звонок от клиента») — nobody to answer."""
        return bool(_WZ_SYSTEM_RE.search(self.text))

    @property
    def is_staff_message(self) -> bool:
        """A person on our side spoke in the Open Line: an employee in Bitrix24 or a
        manager from the phone. The dialog is in human hands from here on."""
        return (
            self.is_message
            and self.is_open_line
            and not self.author_is_bot
            and (self.author_is_employee or self.is_outgoing_echo)
        )

    @property
    def should_answer(self) -> bool:
        """A client text in an Open Line chat — not a bot, staff or connector notice."""
        return (
            self.is_message
            and self.is_open_line
            and not self.author_is_bot
            and not self.is_staff_message
            and not self.is_connector_notice
            and bool(self.text.strip())
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "B24Event":
        data = payload.get("data") or {}
        bot = data.get("bot") or {}
        bot_auth = bot.get("auth") or {}
        msg = data.get("message") or {}
        chat = data.get("chat") or {}
        user = data.get("user") or {}
        return cls(
            event=str(payload.get("event") or ""),
            ts=_to_int(payload.get("ts")),
            bot_id=_to_int(bot.get("id")),
            bot_code=str(bot.get("code") or ""),
            access_token=str(bot_auth.get("access_token") or ""),
            client_endpoint=str(bot_auth.get("client_endpoint") or ""),
            message_id=_to_int(msg.get("id")),
            chat_id=_to_int(msg.get("chatId") or msg.get("chat_id") or chat.get("id")),
            dialog_id=str(chat.get("dialogId") or ""),
            text=str(msg.get("text") or ""),
            entity_type=str(chat.get("entityType") or ""),
            entity_id=str(chat.get("entityId") or ""),
            chat_name=str(chat.get("name") or ""),
            user_id=_to_int(user.get("id")),
            user_name=" ".join(
                p for p in (user.get("firstName"), user.get("lastName")) if p
            ) or str(user.get("name") or ""),
            author_is_bot=str(user.get("bot") or "0") == "1",
            # Open Line clients are connector users (connector=1, externalAuthId=imconnector);
            # only an explicit "0" marks an employee, so a payload without the flag still gets answered.
            author_is_employee=str(user.get("connector", "1")) == "0",
            language=str(data.get("language") or ""),
        )
