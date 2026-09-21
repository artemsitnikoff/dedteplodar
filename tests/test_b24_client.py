import asyncio
import json

import httpx
import pytest

import src.b24.client as client_mod
from src.b24.client import B24Client, B24Error


def make_client(handler):
    return B24Client("https://teplodar.bitrix24.ru/rest/", "tok", transport=httpx.MockTransport(handler))


def test_send_message_posts_json_with_auth_and_returns_id():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"id": 789, "uuidMap": {}}, "time": {}})

    msg_id = asyncio.run(make_client(handler).send_message(511, "chat19167", "[b]hi[/b]", [{"TEXT": "x"}]))
    assert msg_id == 789
    assert seen["url"] == "https://teplodar.bitrix24.ru/rest/imbot.v2.Chat.Message.send"
    assert seen["body"]["auth"] == "tok"
    assert seen["body"]["botId"] == 511 and seen["body"]["dialogId"] == "chat19167"
    assert seen["body"]["fields"]["message"] == "[b]hi[/b]"
    assert seen["body"]["fields"]["keyboard"] == [{"TEXT": "x"}]


def test_update_message_and_keyboard_removal():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"result": True}})

    ok = asyncio.run(make_client(handler).update_message(511, 789, "new text", "N"))
    assert ok is True
    assert seen["body"]["messageId"] == 789
    assert seen["body"]["fields"] == {"message": "new text", "keyboard": "N"}


def test_error_envelope_raises_without_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": "ACCESS_DENIED", "error_description": "Bot is not in chat"})

    with pytest.raises(B24Error) as ei:
        asyncio.run(make_client(handler).send_message(511, "chat1", "x"))
    assert ei.value.code == "ACCESS_DENIED" and len(calls) == 1


def test_retries_on_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr(client_mod, "_RETRY_BACKOFF_S", 0)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"result": {"id": 1}})

    assert asyncio.run(make_client(handler).send_message(511, "chat1", "x")) == 1
    assert len(calls) == 3


def test_transport_errors_exhaust_retries(monkeypatch):
    monkeypatch.setattr(client_mod, "_RETRY_BACKOFF_S", 0)

    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        asyncio.run(make_client(handler).call("imbot.v2.Chat.Message.send", {}))


def test_requires_endpoint_and_token():
    with pytest.raises(ValueError):
        B24Client("", "tok")
    with pytest.raises(ValueError):
        B24Client("https://x/rest/", "")


def test_open_line_session_methods_param_shapes():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"result": True})

    c = make_client(handler)
    assert asyncio.run(c.session_operator(19167)) is True
    assert asyncio.run(c.session_transfer(19167, "queue7")) is True
    assert asyncio.run(c.session_transfer(19167, 42, leave=True)) is True
    assert asyncio.run(c.session_finish(19167)) is True
    paths = [p for p, _ in seen]
    assert paths == [
        "/rest/imopenlines.bot.session.operator",
        "/rest/imopenlines.bot.session.transfer",
        "/rest/imopenlines.bot.session.transfer",
        "/rest/imopenlines.bot.session.finish",
    ]
    assert seen[0][1] == {"CHAT_ID": 19167, "auth": "tok"}
    assert seen[1][1] == {"CHAT_ID": 19167, "TRANSFER_ID": "queue7", "LEAVE": "N", "auth": "tok"}
    assert seen[2][1]["TRANSFER_ID"] == "42" and seen[2][1]["LEAVE"] == "Y"
