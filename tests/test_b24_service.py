import asyncio
from types import SimpleNamespace

import pytest

import admin.services.b24_service as svc
from src.b24.webhook import B24Event
from tests.test_b24_webhook import message_add_payload


class FakeClient:
    """Records REST calls; `fail_update` simulates ACCESS_DENIED on edit."""
    instances = []

    def __init__(self, endpoint, token, **kw):
        self.endpoint, self.token, self.calls = endpoint, token, []
        self.fail_update = False
        self._next_id = 100
        FakeClient.instances.append(self)

    async def send_message(self, bot_id, dialog_id, text, keyboard=None, **kw):
        self._next_id += 1
        self.calls.append(("send", bot_id, dialog_id, text, keyboard))
        return self._next_id

    async def update_message(self, bot_id, message_id, text=None, keyboard=None):
        self.calls.append(("update", bot_id, message_id, text, keyboard))
        if self.fail_update:
            raise RuntimeError("ACCESS_DENIED")
        return True


class FakeGenerator:
    def __init__(self, answer="<b>Русь-12 Л</b> подойдёт<br>https://teplodar.ru/x_y/", fail=False):
        self.answer, self.fail, self.calls = answer, fail, []

    def answer_with_meta(self, session, query, user_id=None, **kw):
        self.calls.append((query, user_id))
        if self.fail:
            raise RuntimeError("cli down")
        return self.answer, SimpleNamespace(
            query_type="RAG_PRODUCT", top_score=0.8, chunks_used=3, city=None, reformulated_query=None,
            t_intent_ms=None, t_retrieval_ms=None, t_answer_ms=1, t_answer_model="sonnet",
        )


@pytest.fixture()
def env(monkeypatch):
    FakeClient.instances.clear()
    svc._seen_message_ids.clear()
    gen = FakeGenerator()
    logged, judged = [], []

    async def fake_get_generator():
        return gen

    monkeypatch.setattr(svc, "B24Client", FakeClient)
    monkeypatch.setattr(svc, "get_eval_generator", fake_get_generator)
    monkeypatch.setattr(svc, "save_query_log", lambda **kw: logged.append(kw) or 42)
    monkeypatch.setattr(svc, "spawn_judge", lambda *a, **kw: judged.append(a))
    return {"gen": gen, "logged": logged, "judged": judged}


def event(**overrides) -> B24Event:
    return B24Event.from_payload(message_add_payload(**overrides))


def test_happy_path_placeholder_then_edit(env):
    asyncio.run(svc.handle_event(event()))
    client = FakeClient.instances[0]
    assert client.endpoint == "https://teplodar.bitrix24.ru/rest/" and client.token.startswith("6c5baa6a")
    kinds = [c[0] for c in client.calls]
    assert kinds == ["send", "update"]
    send, upd = client.calls
    assert send[1] == 511 and send[2] == "chat19167" and send[3] == svc.PLACEHOLDER_TEXT and send[4] is None
    assert upd[2] == 101                                  # placeholder id from send
    assert upd[3] == "[b]Русь-12 Л[/b] подойдёт\nhttps://teplodar.ru/x_y/"
    assert upd[4][0]["TEXT"] == svc.OPERATOR_REQUEST_TEXT and upd[4][0]["ACTION"] == "SEND"
    # generator got the question + the synthetic user id (history by chat)
    q, uid = env["gen"].calls[0]
    assert q == "посоветуйте печь для бани на 14 кубов" and uid < 0
    # journal + judge
    log = env["logged"][0]
    assert log["user_id"] == uid and log["username"] == "b24:Гость#515"
    assert log["query_type"] == "RAG_PRODUCT" and log["bot_message_id"] == 101
    assert env["judged"] == [(42, q, env["gen"].answer)]


def test_falls_back_to_send_when_edit_fails(env):
    ev = event()
    # make the client fail on update
    orig_init = FakeClient.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        self.fail_update = True

    FakeClient.__init__ = init
    try:
        asyncio.run(svc.handle_event(ev))
    finally:
        FakeClient.__init__ = orig_init
    kinds = [c[0] for c in FakeClient.instances[0].calls]
    assert kinds == ["send", "update", "send"]
    assert FakeClient.instances[0].calls[-1][3].startswith("[b]Русь-12 Л[/b]")


def test_duplicate_delivery_is_ignored(env):
    asyncio.run(svc.handle_event(event()))
    asyncio.run(svc.handle_event(event()))
    assert len(FakeClient.instances) == 1 and len(env["gen"].calls) == 1


def test_generator_failure_sends_fallback(env):
    env["gen"].fail = True
    asyncio.run(svc.handle_event(event()))
    client = FakeClient.instances[0]
    assert client.calls[-1][0] == "update" and client.calls[-1][3] == svc.FALLBACK_TEXT
    assert env["logged"][0]["query_type"] == "ERROR" and env["judged"] == []


@pytest.mark.parametrize("text", ["Позвать оператора", "позовите оператора", "нужен живой человек", "менеджера пожалуйста"])
def test_operator_request_gets_stub_and_no_rag(env, text):
    asyncio.run(svc.handle_event(event(**{"data.message.text": text})))
    client = FakeClient.instances[0]
    assert env["gen"].calls == []
    assert client.calls == [("send", 511, "chat19167", svc.OPERATOR_STUB_TEXT, None)]
    assert env["logged"][0]["query_type"] == "OPERATOR"


def test_long_text_mentioning_operator_is_still_a_question(env):
    text = "Оператор на горячей линии сказал, что печь Русь-12 подходит на 14 кубов, это правда?"
    asyncio.run(svc.handle_event(event(**{"data.message.text": text})))
    assert len(env["gen"].calls) == 1


def test_journal_identity_is_stable_per_chat():
    a = svc.journal_identity(event())
    b = svc.journal_identity(event(**{"data.message.id": "999", "data.message.text": "другой"}))
    c = svc.journal_identity(event(**{"data.message.chatId": "20000", "data.chat.id": "20000"}))
    assert a[0] == b[0] != c[0] and a[0] < 0
