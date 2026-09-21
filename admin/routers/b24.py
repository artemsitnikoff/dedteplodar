"""Bitrix24 webhook — entry point for client questions from an Open Line chat.

Stage 1 (this file): receive, verify, parse, log, ack. No reply yet.
Bitrix24 expects a fast HTTP 200 and does not guarantee redelivery, so the
handler must never block on the RAG pipeline; the answer will be produced in
a background task and delivered with a separate REST call (see BITRIX24.md §10).

Auth: this route is exempt from the admin basic-auth middleware (Bitrix24 can't
send our credentials). Authenticity comes from ``auth[application_token]``
compared against ``B24_APPLICATION_TOKEN``.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.b24.webhook import B24Event, mask_secrets, parse_php_form, verify_application_token
from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/b24", tags=["Bitrix24"])

# A real ONIMBOTV2MESSAGEADD is ~5 KB; 256 KiB leaves room for attachments
# while keeping the public, unauthenticated route from being a memory sink.
MAX_BODY_BYTES = 256 * 1024
_TEXT_LOG_LIMIT = 200


@router.get("/events")
async def events_probe():
    """Lets the Bitrix24 developer confirm the URL in a browser."""
    return {"ok": True, "service": "teplodar-b24-webhook", "expects": "POST form-urlencoded"}


@router.post("/events")
async def events(request: Request):
    client_ip = request.client.host if request.client else "?"

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        logger.warning("[b24] body too large (declared %s) from %s", declared, client_ip)
        return JSONResponse({"ok": False, "error": "payload too large"}, status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        logger.warning("[b24] body too large (%d bytes) from %s", len(body), client_ip)
        return JSONResponse({"ok": False, "error": "payload too large"}, status_code=413)

    if not settings.b24_application_token:
        # Fail closed and loudly: an unset secret must not silently accept traffic.
        logger.error("[b24] B24_APPLICATION_TOKEN is not configured — rejecting event from %s", client_ip)
        return JSONResponse({"ok": False, "error": "webhook not configured"}, status_code=503)

    payload = parse_php_form(body)
    if not verify_application_token(payload, settings.b24_application_token):
        logger.warning(
            "[b24] application_token mismatch from %s event=%s",
            client_ip, payload.get("event"),
        )
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    ev = B24Event.from_payload(payload)
    if ev.is_message:
        logger.info(
            "[b24] %s chat=%s dialog=%s entity=%s/%s user=%s(%r) bot=%s/%s msg_id=%s answer=%s text=%r",
            ev.event, ev.chat_id, ev.dialog_id, ev.entity_type, ev.entity_id,
            ev.user_id, ev.user_name, ev.bot_id, ev.bot_code, ev.message_id,
            ev.should_answer, ev.text[:_TEXT_LOG_LIMIT],
        )
    else:
        logger.info("[b24] %s chat=%s dialog=%s bot=%s/%s", ev.event, ev.chat_id, ev.dialog_id, ev.bot_id, ev.bot_code)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("[b24] payload=%s", json.dumps(mask_secrets(payload), ensure_ascii=False))

    # Stage 2 will hand `ev` to a background task here (RAG → reply via REST).
    return {"ok": True}
