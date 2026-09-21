import asyncio
from types import SimpleNamespace

import pytest

import admin.services.b24_service as svc
from src.b24 import sessions
from src.b24.client import B24Error
from src.b24.models import STATUS_BOT, STATUS_OPERATOR, B24Session
from src.b24.webhook import B24Event
from src.core.database import SessionLocal
from tests.test_b24_webhook import message_add_payload


class FakeClient:
    """Records REST calls; flags simulate portal-side failures."""
    instances = []
    fail_update = False
    transfer_error: Exception | None = None

    def __init__(self, endpoint, token, **kw):
        self.endpoint, self.token, self.calls = endpoint, token, []
        self._next_id = 100
        FakeClient.instances.append(self)

    async def send_message(self, bot_id, dialog_id, text, keyboard=None, **kw):
        self._next_id += 1
        self.calls.append(("send", bot_id, dialog_id, text, keyboard))
        return self._next_id

    async def update_message(self, bot_id, message_id, text=None, keyboard=None):
        self.calls.append(("update", bot_id, message_id, text, keyboard))
        if FakeClient.fail_update:
            raise RuntimeError("ACCESS_DENIED")
        return True

    async def session_operator(self, chat_id):
        self.calls.append(("operator", chat_id))
        if FakeClient.transfer_error:
            raise FakeClient.transfer_error
        return True

    async def session_transfer(self, chat_id, transfer_id, *, leave=False):
        self.calls.append(("transfer", chat_id, transfer_id, leave))
        if FakeClient.transfer_error:
            raise FakeClient.transfer_error
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
    FakeClient.fail_update = False
    FakeClient.transfer_error = None
    svc._seen_message_ids.clear()
    with SessionLocal() as s:
        s.query(B24Session).delete()
        s.commit()
    gen = FakeGenerator()
    logged, judged, feedback = [], [], []

    async def fake_get_generator():
        return gen

    monkeypatch.setattr(svc, "B24Client", FakeClient)
    monkeypatch.setattr(svc, "get_eval_generator", fake_get_generator)
    monkeypatch.setattr(svc, "save_query_log", lambda **kw: logged.append(kw) or len(logged))
    monkeypatch.setattr(svc, "set_feedback", lambda log_id, fb, note=None: feedback.append((log_id, fb)))
    monkeypatch.setattr(svc, "spawn_judge", lambda *a, **kw: judged.append(a))
    monkeypatch.setattr(svc.settings, "b24_transfer_to", "")
    monkeypatch.setattr(svc.settings, "b24_max_consecutive_errors", 2)
    return {"gen": gen, "logged": logged, "judged": judged, "feedback": feedback}


def event(**overrides) -> B24Event:
    return B24Event.from_payload(message_add_payload(**overrides))


def run(ev):
    asyncio.run(svc.handle_event(ev))


def calls():
    return [c for cl in FakeClient.instances for c in cl.calls]


# ── answering ─────────────────────────────────────────────────────────────

def test_happy_path_placeholder_then_edit(env):
    run(event())
    client = FakeClient.instances[0]
    assert client.endpoint == "https://teplodar.bitrix24.ru/rest/" and client.token.startswith("6c5baa6a")
    assert [c[0] for c in client.calls] == ["send", "update"]
    send, upd = client.calls
    assert send[1] == 511 and send[2] == "chat19167" and send[3] == svc.PLACEHOLDER_TEXT and send[4] is None
    assert upd[2] == 101
    assert upd[3] == "[b]Русь-12 Л[/b] подойдёт\nhttps://teplodar.ru/x_y/"
    assert upd[4][0]["TEXT"] == svc.OPERATOR_REQUEST_TEXT and upd[4][0]["ACTION"] == "SEND"
    q, uid = env["gen"].calls[0]
    assert q == "посоветуйте печь для бани на 14 кубов" and uid < 0
    log = env["logged"][0]
    assert log["user_id"] == uid and log["username"] == "b24:Гость#515"
    assert log["query_type"] == "RAG_PRODUCT" and log["bot_message_id"] == 101
    assert env["judged"] == [(1, q, env["gen"].answer)]
    assert sessions.get_status(19167) == STATUS_BOT


def test_falls_back_to_send_when_edit_fails(env):
    FakeClient.fail_update = True
    run(event())
    kinds = [c[0] for c in FakeClient.instances[0].calls]
    assert kinds == ["send", "update", "send"]
    assert FakeClient.instances[0].calls[-1][3].startswith("[b]Русь-12 Л[/b]")


def test_duplicate_delivery_is_ignored(env):
    run(event())
    run(event())
    assert len(FakeClient.instances) == 1 and len(env["gen"].calls) == 1


def test_generator_failure_sends_fallback_without_escalating_first_time(env):
    env["gen"].fail = True
    run(event())
    c = FakeClient.instances[0].calls
    assert c[-1][0] == "update" and c[-1][3] == svc.FALLBACK_TEXT
    assert env["logged"][0]["query_type"] == "ERROR" and env["judged"] == []
    assert "operator" not in [x[0] for x in c] and sessions.get_status(19167) == STATUS_BOT


def test_long_text_mentioning_operator_is_still_a_question(env):
    text = "Оператор на горячей линии сказал, что печь Русь-12 подходит на 14 кубов, это правда?"
    run(event(**{"data.message.text": text}))
    assert len(env["gen"].calls) == 1


def test_journal_identity_is_stable_per_chat():
    a = svc.journal_identity(event())
    b = svc.journal_identity(event(**{"data.message.id": "999", "data.message.text": "другой"}))
    c = svc.journal_identity(event(**{"data.message.chatId": "20000", "data.chat.id": "20000"}))
    assert a[0] == b[0] != c[0] and a[0] < 0


# ── escalation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["Позвать оператора", "позовите оператора", "нужен живой человек", "менеджера пожалуйста"])
def test_operator_request_transfers_and_silences_bot(env, text):
    run(event(**{"data.message.text": text}))
    assert env["gen"].calls == []
    assert calls() == [("operator", 19167), ("send", 511, "chat19167", svc.TRANSFER_TEXT, None)]
    assert env["logged"][0]["query_type"] == "OPERATOR" and env["feedback"] == [(1, "operator")]
    assert sessions.get_status(19167) == STATUS_OPERATOR
    # next client message in the same session: bot must not answer
    run(event(**{"data.message.id": "2", "data.message.text": "а вы кто?"}))
    assert len(FakeClient.instances) == 1 and env["gen"].calls == []


@pytest.mark.parametrize("text", [
    "когда отгрузят мой заказ?", "где мой заказ №12345", "статус заказа 777", "печь пришла бракованная",
    "хочу вернуть деньги за котёл", "у меня рекламация по Русь-12",
])
def test_personal_order_goes_straight_to_operator(env, text):
    run(event(**{"data.message.text": text}))
    assert env["gen"].calls == [] and calls()[0] == ("operator", 19167)
    assert sessions.get_status(19167) == STATUS_OPERATOR


@pytest.mark.parametrize("text", ["какие сроки доставки заказа?", "можно ли оплатить заказ картой", "как заказать печь"])
def test_generic_order_questions_are_answered_by_bot(env, text):
    run(event(**{"data.message.text": text}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_BOT


def test_transfer_to_queue_when_configured(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_transfer_to", "queue7")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert calls()[0] == ("transfer", 19167, "queue7", False)
    assert sessions.get_status(19167) == STATUS_OPERATOR


def test_transfer_failure_keeps_bot_and_gives_hotline(env):
    FakeClient.transfer_error = B24Error("OPERATOR_WRONG", "no operators")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert calls()[-1] == ("send", 511, "chat19167", svc.TRANSFER_FAILED_TEXT, None)
    assert sessions.get_status(19167) == STATUS_BOT


def test_already_with_operator_counts_as_success(env):
    FakeClient.transfer_error = B24Error("WRONG_CHAT", "Operator is not a bot")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert calls()[-1][3] == svc.TRANSFER_TEXT and sessions.get_status(19167) == STATUS_OPERATOR


def test_consecutive_errors_escalate(env):
    env["gen"].fail = True
    run(event(**{"data.message.id": "1"}))
    assert "operator" not in [c[0] for c in calls()]
    run(event(**{"data.message.id": "2", "data.message.text": "ещё раз"}))
    kinds = [c[0] for c in calls()]
    assert kinds.count("operator") == 1 and kinds[-1] == "send"
    assert calls()[-1][3] == svc.TRANSFER_TEXT
    assert sessions.get_status(19167) == STATUS_OPERATOR
    # the escalation caused by errors is not logged as a separate OPERATOR turn
    assert [l["query_type"] for l in env["logged"]] == ["ERROR", "ERROR"]


def test_new_line_session_resumes_bot_after_handoff(env):
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert sessions.get_status(19167) == STATUS_OPERATOR
    run(event(**{"data.message.id": "9", "data.message.text": "а есть печь на 20 кубов?",
                 "data.chat.entityId": "livechat|13|20001|515"}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_BOT


def test_join_chat_resets_state(env):
    run(event(**{"data.message.text": "Позвать оператора"}))
    join = event(**{"event": "ONIMBOTV2JOINCHAT", "data.message.text": ""})
    run(join)
    assert sessions.get_status(19167) == STATUS_BOT
    run(event(**{"data.message.id": "10", "data.message.text": "вопрос"}))
    assert len(env["gen"].calls) == 1
