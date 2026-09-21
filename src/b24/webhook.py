"""Parsing and verification of Bitrix24 imbot v2 webhook events.

Bitrix24 delivers events as ``application/x-www-form-urlencoded`` built with
PHP's ``http_build_query``: nested keys look like ``data[message][text]`` and
every scalar arrives as a string (``"0"``/``"1"`` for booleans, ``""`` for
null). This module turns that into a nested dict and a typed ``B24Event``.

Pure functions, no FastAPI / DB imports — easy to unit-test with the captured
payload in BITRIX24.md (appendix A).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

# Keys whose values must never reach logs.
SECRET_KEYS = frozenset({"access_token", "refresh_token", "application_token", "botToken"})

EVENT_MESSAGE_ADD = "ONIMBOTV2MESSAGEADD"
EVENT_COMMAND_ADD = "ONIMBOTV2COMMANDADD"
ENTITY_TYPE_OPEN_LINES = "LINES"


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
    language: str

    @property
    def is_message(self) -> bool:
        return self.event == EVENT_MESSAGE_ADD

    @property
    def is_open_line(self) -> bool:
        return self.entity_type == ENTITY_TYPE_OPEN_LINES

    @property
    def should_answer(self) -> bool:
        """A client text in an Open Line chat, not authored by a bot."""
        return (
            self.is_message
            and self.is_open_line
            and not self.author_is_bot
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
            language=str(data.get("language") or ""),
        )
