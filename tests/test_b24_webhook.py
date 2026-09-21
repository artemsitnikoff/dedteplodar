"""Bitrix24 webhook: parser + route. Run: PYTHONPATH=. pytest tests/ -q"""
from __future__ import annotations

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.b24.webhook import B24Event, mask_secrets, parse_php_form, verify_application_token

APP_TOKEN = "c76f868e29cd35cd1a53aa76d6cacd7c"


def php_encode(obj: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Inverse of parse_php_form — mimics PHP http_build_query."""
    pairs: list[tuple[str, str]] = []
    for k, v in obj.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            pairs.extend(php_encode(v, key))
        else:
            pairs.append((key, "" if v is None else str(v)))
    return pairs


def message_add_payload(**overrides) -> dict:
    """Shape of the real ONIMBOTV2MESSAGEADD captured 2026-09-16 (BITRIX24.md, appendix A)."""
    p = {
        "event": "ONIMBOTV2MESSAGEADD",
        "event_handler_id": "111",
        "data": {
            "bot": {
                "id": "511", "code": "ai_dc_bot",
                "auth": {
                    "access_token": "6c5baa6a00929e480074814c000001ff403807fcf3893a0a5d3a05a67f8cd52b062757",
                    "expires_in": "3600", "scope": "imbot,imopenlines",
                    "domain": "teplodar.bitrix24.ru",
                    "client_endpoint": "https://teplodar.bitrix24.ru/rest/",
                    "refresh_token": "5cdad16a00929e480074814c000001ff403807896e5cec6119978bdad4bff43bbefe9e",
                    "application_token": APP_TOKEN,
                },
            },
            "message": {
                "id": "1093189", "chatId": "19167", "chat_id": "19167",
                "authorId": "515", "date": "2026-09-16T11:05:01+03:00",
                "text": "посоветуйте печь для бани на 14 кубов", "isSystem": "0",
            },
            "chat": {
                "id": "19167", "dialogId": "chat19167", "type": "lines",
                "entityType": "LINES", "entityId": "livechat|13|19165|515",
                "name": "Синий гость №7 - Demo онлайн чат с AI ботом",
            },
            "user": {"id": "515", "name": "Гость", "firstName": "Гость", "lastName": "", "bot": "0"},
            "language": "ru",
        },
        "ts": "1789545901",
        "auth": {"domain": "teplodar.bitrix24.ru", "application_token": APP_TOKEN},
    }
    for dotted, value in overrides.items():
        cur = p
        parts = dotted.split(".")
        for part in parts[:-1]:
            cur = cur[part]
        cur[parts[-1]] = value
    return p


def encode(payload: dict) -> bytes:
    return urlencode(php_encode(payload)).encode()


# ── parser ────────────────────────────────────────────────────────────────

def test_parse_php_form_roundtrip():
    payload = message_add_payload()
    assert parse_php_form(encode(payload)) == payload


def test_parse_php_form_keeps_blank_and_unicode():
    parsed = parse_php_form("a%5Bb%5D=&a%5Bc%5D=%D0%93%D0%BE%D1%81%D1%82%D1%8C&x=1")
    assert parsed == {"a": {"b": "", "c": "Гость"}, "x": "1"}


def test_event_from_real_shape():
    ev = B24Event.from_payload(message_add_payload())
    assert ev.event == "ONIMBOTV2MESSAGEADD"
    assert ev.bot_id == 511 and ev.bot_code == "ai_dc_bot"
    assert ev.chat_id == 19167 and ev.dialog_id == "chat19167"
    assert ev.message_id == 1093189
    assert ev.user_id == 515 and ev.user_name == "Гость"
    assert ev.entity_type == "LINES" and ev.entity_id == "livechat|13|19165|515"
    assert ev.client_endpoint == "https://teplodar.bitrix24.ru/rest/"
    assert ev.access_token.startswith("6c5baa6a")
    assert ev.text == "посоветуйте печь для бани на 14 кубов"
    assert ev.should_answer


@pytest.mark.parametrize("override, expect", [
    ({"data.chat.entityType": ""}, False),          # not an Open Line chat
    ({"data.user.bot": "1"}, False),                # authored by a bot
    ({"data.message.text": "   "}, False),          # empty text
    ({"event": "ONIMBOTV2JOINCHAT"}, False),        # not a message
    ({}, True),
])
def test_should_answer(override, expect):
    assert B24Event.from_payload(message_add_payload(**override)).should_answer is expect


def test_verify_application_token():
    payload = message_add_payload()
    assert verify_application_token(payload, APP_TOKEN)
    assert not verify_application_token(payload, "wrong")
    assert not verify_application_token(payload, "")
    # the copy under data[bot][auth] must not be enough on its own
    del payload["auth"]
    assert not verify_application_token(payload, APP_TOKEN)


def test_mask_secrets():
    masked = mask_secrets(message_add_payload())
    assert masked["auth"]["application_token"] == "c76f86…cd7c"
    assert masked["data"]["bot"]["auth"]["access_token"].endswith("…2757")
    assert masked["data"]["message"]["text"].startswith("посоветуйте")


# ── route ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    from admin.main import app
    from admin.routers import b24 as b24_router
    from src.core.config import settings
    monkeypatch.setattr(settings, "b24_application_token", APP_TOKEN)
    spawned = []
    monkeypatch.setattr(b24_router, "spawn_handle_event", lambda ev: spawned.append(ev))
    c = TestClient(app)  # no lifespan → no DB probe / model warm-up
    c.spawned = spawned
    return c


FORM = {"content-type": "application/x-www-form-urlencoded"}


def test_route_accepts_valid_event_without_basic_auth(client):
    r = client.post("/api/v1/b24/events", content=encode(message_add_payload()), headers=FORM)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(client.spawned) == 1 and client.spawned[0].chat_id == 19167


def test_route_does_not_spawn_for_non_line_chat(client):
    r = client.post("/api/v1/b24/events", content=encode(message_add_payload(**{"data.chat.entityType": ""})), headers=FORM)
    assert r.status_code == 200 and client.spawned == []


def test_route_probe_get(client):
    r = client.get("/api/v1/b24/events")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_route_rejects_bad_token(client):
    bad = message_add_payload(**{"auth.application_token": "nope"})
    r = client.post("/api/v1/b24/events", content=encode(bad), headers=FORM)
    assert r.status_code == 403


def test_route_fails_closed_when_unconfigured(client, monkeypatch):
    from src.core.config import settings
    monkeypatch.setattr(settings, "b24_application_token", "")
    r = client.post("/api/v1/b24/events", content=encode(message_add_payload()), headers=FORM)
    assert r.status_code == 503


def test_route_rejects_oversized_body(client):
    r = client.post("/api/v1/b24/events", content=b"x=" + b"a" * (300 * 1024), headers=FORM)
    assert r.status_code == 413


def test_other_api_routes_still_need_basic_auth(client):
    assert client.get("/api/v1/products/").status_code == 401


def test_route_spawns_for_join_chat(client):
    join = message_add_payload(**{"event": "ONIMBOTV2JOINCHAT", "data.message.text": ""})
    r = client.post("/api/v1/b24/events", content=encode(join), headers=FORM)
    assert r.status_code == 200 and len(client.spawned) == 1 and client.spawned[0].is_join
