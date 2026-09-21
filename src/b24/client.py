"""Minimal async REST client for Bitrix24 bot calls.

One instance per webhook event: the event carries a fresh ``access_token``
(valid 1 h) and the portal's ``client_endpoint`` (``https://<portal>/rest/``),
so no token storage or refresh is needed. Message send/update (stage 2) and the Open Line session methods used for
escalation (stage 3) are wrapped; ``call()`` is generic for anything else.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

METHOD_MESSAGE_SEND = "imbot.v2.Chat.Message.send"
METHOD_MESSAGE_UPDATE = "imbot.v2.Chat.Message.update"
METHOD_SESSION_OPERATOR = "imopenlines.bot.session.operator"   # first free operator
METHOD_SESSION_TRANSFER = "imopenlines.bot.session.transfer"   # specific user / queue
METHOD_SESSION_FINISH = "imopenlines.bot.session.finish"

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_S = 0.5


class B24Error(Exception):
    """Bitrix24 returned an error envelope (``{"error": ..., "error_description": ...}``)."""

    def __init__(self, code: str, description: str = "", status: int | None = None):
        super().__init__(f"{code}: {description}" if description else code)
        self.code = code
        self.description = description
        self.status = status


class B24Client:
    def __init__(
        self,
        client_endpoint: str,
        access_token: str,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not client_endpoint or not access_token:
            raise ValueError("client_endpoint and access_token are required")
        self._base = client_endpoint if client_endpoint.endswith("/") else client_endpoint + "/"
        self._token = access_token
        self._timeout = timeout
        self._transport = transport

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        """POST ``{client_endpoint}{method}`` with OAuth ``auth`` in the body.

        Retries transport errors and 5xx a couple of times; 4xx and Bitrix
        error envelopes are raised immediately as ``B24Error``.
        """
        url = self._base + method
        body = {**params, "auth": self._token}
        last_exc: Exception | None = None
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                    resp = await http.post(url, json=body)
            except httpx.TransportError as e:
                last_exc = e
                logger.warning("[b24-rest] %s transport error (attempt %d/%d): %s", method, attempt, _RETRY_ATTEMPTS, e)
            else:
                if resp.status_code >= 500:
                    last_exc = B24Error("HTTP_%d" % resp.status_code, resp.text[:200], resp.status_code)
                    logger.warning("[b24-rest] %s -> %d (attempt %d/%d)", method, resp.status_code, attempt, _RETRY_ATTEMPTS)
                else:
                    return self._parse(method, resp)
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_S * attempt)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _parse(method: str, resp: httpx.Response) -> Any:
        try:
            data = resp.json()
        except ValueError:
            raise B24Error("BAD_JSON", resp.text[:200], resp.status_code)
        if isinstance(data, dict) and data.get("error"):
            raise B24Error(str(data["error"]), str(data.get("error_description") or ""), resp.status_code)
        if resp.status_code >= 400:
            raise B24Error("HTTP_%d" % resp.status_code, resp.text[:200], resp.status_code)
        return data.get("result") if isinstance(data, dict) else data

    async def send_message(
        self,
        bot_id: int,
        dialog_id: str,
        text: str,
        keyboard: list[dict[str, Any]] | None = None,
        *,
        url_preview: bool = True,
    ) -> int | None:
        """imbot.v2.Chat.Message.send → new message id (None if the portal omits it)."""
        fields: dict[str, Any] = {"message": text, "urlPreview": url_preview}
        if keyboard:
            fields["keyboard"] = keyboard
        result = await self.call(METHOD_MESSAGE_SEND, {"botId": bot_id, "dialogId": dialog_id, "fields": fields})
        if isinstance(result, dict):
            try:
                return int(result.get("id"))
            except (TypeError, ValueError):
                return None
        return None

    async def update_message(
        self,
        bot_id: int,
        message_id: int,
        text: str | None = None,
        keyboard: list[dict[str, Any]] | str | None = None,
    ) -> bool:
        """imbot.v2.Chat.Message.update — text and/or keyboard (``"N"`` removes it)."""
        fields: dict[str, Any] = {}
        if text is not None:
            fields["message"] = text
        if keyboard is not None:
            fields["keyboard"] = keyboard
        result = await self.call(METHOD_MESSAGE_UPDATE, {"botId": bot_id, "messageId": message_id, "fields": fields})
        if isinstance(result, dict):
            return bool(result.get("result", True))
        return bool(result)

    # ── Open Lines session control (scope imopenlines) ──────────────────

    async def session_operator(self, chat_id: int) -> bool:
        """Hand the dialog to the first free operator of the line."""
        result = await self.call(METHOD_SESSION_OPERATOR, {"CHAT_ID": chat_id})
        return bool(result)

    async def session_transfer(self, chat_id: int, transfer_id: str | int, *, leave: bool = False) -> bool:
        """Hand the dialog to a specific user id or ``queue<QUEUE_ID>``.

        ``leave=False`` keeps the bot in the chat as an observer until the
        operator confirms (Bitrix default); ``True`` drops it immediately.
        """
        params = {"CHAT_ID": chat_id, "TRANSFER_ID": str(transfer_id), "LEAVE": "Y" if leave else "N"}
        result = await self.call(METHOD_SESSION_TRANSFER, params)
        return bool(result)

    async def session_finish(self, chat_id: int) -> bool:
        result = await self.call(METHOD_SESSION_FINISH, {"CHAT_ID": chat_id})
        return bool(result)
