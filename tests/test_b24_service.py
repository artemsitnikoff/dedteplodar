import asyncio
from datetime import timedelta
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
    transfer_error: Exception | None = None

    def __init__(self, endpoint, token, **kw):
        self.endpoint, self.token, self.calls = endpoint, token, []
        self._next_id = 100
        FakeClient.instances.append(self)

    async def send_message(self, bot_id, dialog_id, text, keyboard=None, **kw):
        self._next_id += 1
        self.calls.append(("send", bot_id, dialog_id, text, keyboard))
        return self._next_id

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
    FakeClient.transfer_error = None
    svc._seen_message_ids.clear()
    svc._queues.clear()
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
    monkeypatch.setattr(svc.settings, "b24_debounce_seconds", 0)
    return {"gen": gen, "logged": logged, "judged": judged, "feedback": feedback}


def event(**overrides) -> B24Event:
    return B24Event.from_payload(message_add_payload(**overrides))


async def drain():
    while svc._queues:
        await asyncio.gather(*[q.task for q in svc._queues.values() if q.task])


def run(*evs):
    """Deliver events back to back (as one burst) and wait until the chat queue is answered."""
    async def go():
        for ev in evs:
            await svc.handle_event(ev)
        await drain()
    asyncio.run(go())


def calls():
    return [c for cl in FakeClient.instances for c in cl.calls]


# ── answering ─────────────────────────────────────────────────────────────

def test_happy_path_single_message(env):
    run(event())
    client = FakeClient.instances[-1]
    assert client.endpoint == "https://teplodar.bitrix24.ru/rest/" and client.token.startswith("6c5baa6a")
    # One message with the answer — no "ищу ответ…" placeholder to edit later:
    # Wazzup doesn't relay edits to WhatsApp/Max.
    [send] = calls()
    assert send[0] == "send" and send[1] == 511 and send[2] == "chat19167"
    assert send[3] == "[b]Русь-12 Л[/b] подойдёт\nhttps://teplodar.ru/x_y/"
    assert send[4][0]["TEXT"] == svc.OPERATOR_REQUEST_TEXT and send[4][0]["ACTION"] == "SEND"
    q, uid = env["gen"].calls[0]
    assert q == "посоветуйте печь для бани на 14 кубов" and uid < 0
    log = env["logged"][0]
    assert log["user_id"] == uid and log["username"] == "b24:Гость#515"
    assert log["query_type"] == "RAG_PRODUCT" and log["bot_message_id"] == 101
    assert env["judged"] == [(1, q, env["gen"].answer)]
    assert sessions.get_status(19167) == STATUS_BOT


def test_duplicate_delivery_is_ignored(env):
    run(event())
    run(event())
    assert len(env["gen"].calls) == 1 and len(calls()) == 1


def test_generator_failure_sends_fallback_without_escalating_first_time(env):
    env["gen"].fail = True
    run(event())
    c = calls()
    assert [x[0] for x in c] == ["send"] and c[0][3] == svc.FALLBACK_TEXT
    assert env["logged"][0]["query_type"] == "ERROR" and env["judged"] == []
    assert "operator" not in [x[0] for x in c] and sessions.get_status(19167) == STATUS_BOT


def test_journal_identity_is_stable_per_chat():
    a = svc.journal_identity(event())
    b = svc.journal_identity(event(**{"data.message.id": "999", "data.message.text": "другой"}))
    c = svc.journal_identity(event(**{"data.message.chatId": "20000", "data.chat.id": "20000"}))
    assert a[0] == b[0] != c[0] and a[0] < 0


# ── escalation ────────────────────────────────────────────────────────────

OPERATOR_PHRASES = [
    "Позвать оператора", "позовите оператора", "соедините с оператором", "соедини меня с оператором",
    "переключите на оператора", "хочу поговорить с человеком", "можно с живым человеком?", "нужен живой человек",
    "позовите менеджера", "свяжите с сотрудником", "переключите на поддержку", "хочу в техподдержку",
    "хочу написать в поддержку", "позвоните мне", "с кем можно поговорить?", "это бот? дайте человека",
    "свяжите с продавцом", "дайте оператора", "хочу поговорить с менеджером", "оператора!", "Менеджера?", "поддержка",
    "специалист", "Специалиста", "«специалист»", "позовите специалиста",
    "Хочу купить Русь-12 с баком, позвоните мне пожалуйста по номеру +7 900 000-00-00, удобно после 18",
]
NOT_OPERATOR_PHRASES = [
    "оператор сказал что Русь-12 подходит?", "какой оператор лучше — Русь или Сахара?",
    "у вас есть менеджер по опту?", "сколько человек нужно чтобы установить печь?",
    "можно ли заказать монтаж у ваших специалистов?", "консультант есть?", "нужен специалист по монтажу?",
    "как связаться с дилером в Сургуте?", "какие сроки доставки заказа?", "менеджер написал что печь в наличии, это так?",
    "Оператор на горячей линии сказал, что печь Русь-12 подходит на 14 кубов, это правда?",
]


@pytest.mark.parametrize("text", OPERATOR_PHRASES)
def test_is_operator_request_positive(text):
    assert svc.is_operator_request(text), text


@pytest.mark.parametrize("text", NOT_OPERATOR_PHRASES)
def test_is_operator_request_negative(text):
    assert not svc.is_operator_request(text) and not svc.is_personal_order(text), text


@pytest.mark.parametrize("text", ["Позвать оператора", "соедините с оператором", "нужен живой человек", "менеджера позовите"])
def test_operator_request_transfers_and_silences_bot(env, text):
    run(event(**{"data.message.text": text}))
    assert env["gen"].calls == []
    # the notice goes first: after the transfer the bot may lose access to the chat
    assert calls() == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]
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
    assert env["gen"].calls == [] and ("operator", 19167) in calls()
    assert sessions.get_status(19167) == STATUS_OPERATOR


@pytest.mark.parametrize("text", ["какие сроки доставки заказа?", "можно ли оплатить заказ картой", "как заказать печь"])
def test_generic_order_questions_are_answered_by_bot(env, text):
    run(event(**{"data.message.text": text}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_BOT


def test_transfer_to_queue_when_configured(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_transfer_to", "queue7")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert ("transfer", 19167, "queue7", False) in calls()
    assert sessions.get_status(19167) == STATUS_OPERATOR


def test_transfer_failure_keeps_bot_and_gives_hotline(env):
    FakeClient.transfer_error = B24Error("OPERATOR_WRONG", "no operators")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert [c[3] for c in calls() if c[0] == "send"] == [svc.TRANSFER_TEXT, svc.TRANSFER_FAILED_TEXT]
    assert sessions.get_status(19167) == STATUS_BOT


def test_already_with_operator_counts_as_success(env):
    FakeClient.transfer_error = B24Error("WRONG_CHAT", "Operator is not a bot")
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert [c[3] for c in calls() if c[0] == "send"] == [svc.TRANSFER_TEXT]
    assert sessions.get_status(19167) == STATUS_OPERATOR


def test_consecutive_errors_escalate(env):
    env["gen"].fail = True
    run(event(**{"data.message.id": "1"}))
    assert "operator" not in [c[0] for c in calls()]
    run(event(**{"data.message.id": "2", "data.message.text": "ещё раз"}))
    kinds = [c[0] for c in calls()]
    assert kinds.count("operator") == 1 and kinds[-2:] == ["send", "operator"]
    assert calls()[-2][3] == svc.TRANSFER_TEXT
    assert sessions.get_status(19167) == STATUS_OPERATOR
    # the escalation caused by errors is not logged as a separate OPERATOR turn
    assert [l["query_type"] for l in env["logged"]] == ["ERROR", "ERROR"]


def test_new_line_session_resumes_bot_after_handoff(env):
    run(event(**{"data.message.text": "Позвать оператора"}))
    assert sessions.get_status(19167) == STATUS_OPERATOR
    run(event(**{"data.message.id": "9", "data.message.text": "а есть печь на 20 кубов?",
                 "data.chat.entityId": "livechat|13|20001|515"}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_BOT


def _age_handoff(chat_id=19167, minutes=5):
    with SessionLocal() as s:
        s.get(B24Session, chat_id).handoff_at = sessions._utcnow() - timedelta(minutes=minutes)
        s.commit()


JOIN = {"event": "ONIMBOTV2JOINCHAT", "data.message.text": ""}


def test_join_chat_resets_state(env):
    run(event(**{"data.message.text": "Позвать оператора"}))
    _age_handoff()  # the operator session ended a while ago, a new one starts
    run(event(**JOIN))
    assert sessions.get_status(19167) == STATUS_BOT
    run(event(**{"data.message.id": "10", "data.message.text": "вопрос"}))
    assert len(env["gen"].calls) == 1


@pytest.mark.parametrize("opener", ["Позвать оператора", "=== Исходящее сообщение, автор: Телефон ===\nДобрый день!"])
@pytest.mark.parametrize("join_first", [True, False])
def test_client_returns_after_closed_dialog_gets_bot_either_event_order(env, monkeypatch, opener, join_first):
    # A dialog went to a human (client asked / manager wrote first), the operator
    # closed it; hours later the client writes again → new session. On Wazzup lines
    # the only new-session signal is JOINCHAT, and it often arrives AFTER the first
    # message — which used to be dropped as "still with the operator".
    run(event(**{"data.message.id": "1", "data.message.text": opener}))
    assert sessions.get_status(19167) == STATUS_OPERATOR
    _age_handoff(minutes=180)
    monkeypatch.setattr(svc.settings, "b24_debounce_seconds", 0.2)
    before = len(calls())
    question = event(**{"data.message.id": "2", "data.message.text": "а какая гарантия на Русь-12?"})

    async def go():
        if join_first:
            await svc.handle_event(event(**JOIN))
        await svc.handle_event(question)
        if not join_first:
            await asyncio.sleep(0.05)  # the join lands while the message is held
            await svc.handle_event(event(**JOIN))
        await drain()

    asyncio.run(go())
    assert [q for q, _ in env["gen"].calls] == ["а какая гарантия на Русь-12?"]
    assert [c[0] for c in calls()[before:]] == ["send"]
    assert sessions.get_status(19167) == STATUS_BOT


def test_held_message_escalates_if_new_session_starts_with_operator_request(env):
    run(event(**{"data.message.id": "1", "data.message.text": "Позвать оператора"}))
    _age_handoff(minutes=180)
    before = len(calls())
    run(event(**{"data.message.id": "2", "data.message.text": "соедините с оператором"}), event(**JOIN))
    assert env["gen"].calls == []
    assert calls()[before:] == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]


def test_message_in_open_operator_dialog_is_held_then_dropped(env):
    run(event(**{"data.message.id": "1", "data.message.text": "Позвать оператора"}))
    before = len(calls())
    run(event(**{"data.message.id": "2", "data.message.text": "соедините с оператором ещё раз"}))
    # no JOINCHAT came → still the operator's dialog: no answer, no second transfer
    assert env["gen"].calls == [] and calls()[before:] == []
    assert svc._queues == {}


@pytest.mark.parametrize("join_first", [True, False])
def test_manager_opens_new_session_bot_stays_silent_either_event_order(env, join_first):
    # Test line 2026-10-12: a manager's opening message and the new session's
    # JOINCHAT arrive in the same second, in either order. When the join came
    # second it used to reset the dialog to the bot, and the client's reply
    # ("Да, актуально") got a bot handoff message.
    opening = event(**{"data.message.id": "1", "data.message.text": WZ_OUTGOING})
    run(*([event(**JOIN), opening] if join_first else [opening, event(**JOIN)]))
    assert sessions.get_status(19167) == STATUS_OPERATOR
    run(event(**{"data.message.id": "2", "data.message.text": "Да, актуально"}))
    assert env["gen"].calls == []
    assert [c[0] for c in calls()] == ["operator"]  # only the silent queue handoff, no message


# ── layer 2: intent says needs_human ──────────────────────────────────────

def test_intent_needs_human_hands_off_instead_of_answering(env):
    gen = env["gen"]

    def answer_with_meta(session, query, user_id=None, **kw):
        gen.calls.append((query, user_id))
        return "<b>Обратитесь на горячую линию</b>", SimpleNamespace(
            query_type="FAQ_COMPANY", top_score=None, chunks_used=0, city=None, reformulated_query=None,
            t_intent_ms=1, t_retrieval_ms=None, t_answer_ms=1, t_answer_model="sonnet", needs_human=True,
        )

    gen.answer_with_meta = answer_with_meta
    # Nothing for layer 1 to catch (no staff nouns, no order words) — only Haiku reads the frustration.
    text = "Третий раз задаю вопрос, сколько это будет продолжаться?"
    assert svc.escalation_reason(text) is None
    run(event(**{"data.message.text": text}))
    c = calls()
    # the generated answer is dropped: transfer → handoff text only
    assert c == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]
    assert sessions.get_status(19167) == STATUS_OPERATOR
    assert [l["query_type"] for l in env["logged"]] == ["OPERATOR"] and env["judged"] == []


def test_intent_needs_human_false_is_normal_answer(env):
    run(event())  # FakeGenerator meta has no needs_human attribute → treated as False
    assert [x[0] for x in calls()] == ["send"]
    assert sessions.get_status(19167) == STATUS_BOT


# ── staff in the dialog: bot steps aside ──────────────────────────────────

# Real texts from the Wazzup → Max line (2026-10-08): what a manager typed on the
# company phone arrives authored by the client, with a marker line.
WZ_OUTGOING = "=== Исходящее сообщение, автор: Телефон ===\nВчера направляли Вам счет  на оплату."
WZ_OUTGOING_QUOTED = (
    ">>Нашел из наличия в своем городе\n \n \n=== Исходящее сообщение, автор: Телефон ===\nВерону?"
)


@pytest.mark.parametrize("text", [WZ_OUTGOING, WZ_OUTGOING_QUOTED])
def test_manager_message_from_phone_silences_bot(env, text):
    run(event(**{"data.message.text": text}))
    # the session goes to the line's queue, silently — nothing is sent to the client
    assert env["gen"].calls == [] and calls() == [("operator", 19167)] and env["logged"] == []
    assert sessions.get_status(19167) == STATUS_OPERATOR
    # the client's reply goes to the manager, not to the bot
    run(event(**{"data.message.id": "2", "data.message.text": "Здравствуйте, хотел вам позвонить"}))
    assert env["gen"].calls == [] and calls() == [("operator", 19167)]


def test_employee_message_in_bitrix_silences_bot(env):
    run(event(**{"data.message.text": "Время не МСК, а НСК (Новосибирск)", "data.user.id": "1",
                 "data.user.name": "Евгения", "data.user.connector": "0", "data.user.externalAuthId": "default"}))
    assert env["gen"].calls == [] and calls() == []
    assert sessions.get_status(19167) == STATUS_OPERATOR
    with SessionLocal() as s:
        row = s.get(B24Session, 19167)
        assert row.user_id is None  # the row keeps describing the client, not the employee


def test_manager_message_after_bot_answer_takes_over(env):
    run(event())
    assert len(env["gen"].calls) == 1
    run(event(**{"data.message.id": "2", "data.message.text": WZ_OUTGOING}))
    run(event(**{"data.message.id": "3", "data.message.text": "а сколько стоит доставка?"}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_OPERATOR


def test_new_line_session_resumes_bot_after_staff(env):
    run(event(**{"data.message.text": WZ_OUTGOING}))
    run(event(**{"data.message.id": "9", "data.message.text": "а есть печь на 20 кубов?",
                 "data.chat.entityId": "livechat|13|20001|515"}))
    assert len(env["gen"].calls) == 1 and sessions.get_status(19167) == STATUS_BOT


def test_answer_dropped_if_manager_stepped_in_while_generating(env):
    gen = env["gen"]
    original = gen.answer_with_meta

    def slow_answer(session, query, user_id=None, **kw):
        # the manager's phone message lands while the bot is still generating
        sessions.mark_handoff(19167, svc.REASON_STAFF)
        return original(session, query, user_id=user_id, **kw)

    gen.answer_with_meta = slow_answer
    run(event())
    assert len(gen.calls) == 1 and calls() == [] and env["logged"] == []


# ── bursts: several messages, one answer ──────────────────────────────────

def test_burst_of_messages_gets_one_answer(env):
    # chat 21393 on 2026-10-07: two messages 10 s apart got two answers, the
    # second one asking "which product?" because it never saw the first
    run(event(**{"data.message.id": "1", "data.message.text": "Сигнал КОВ-25 СКВс двухконтурный"}),
        event(**{"data.message.id": "2", "data.message.text": "добрый день есть такой?"}))
    assert [q for q, _ in env["gen"].calls] == ["Сигнал КОВ-25 СКВс двухконтурный\nдобрый день есть такой?"]
    assert [c[0] for c in calls()] == ["send"]
    assert env["logged"][0]["question"] == "Сигнал КОВ-25 СКВс двухконтурный\nдобрый день есть такой?"


def test_waits_for_the_client_to_pause(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_debounce_seconds", 0.3)

    async def go():
        await svc.handle_event(event(**{"data.message.id": "1", "data.message.text": "У меня стоит Каскад-18"}))
        await asyncio.sleep(0.1)  # client is still typing
        await svc.handle_event(event(**{"data.message.id": "2", "data.message.text": "Хотел бы подобрать новую"}))
        assert env["gen"].calls == []  # nothing answered mid-burst
        await drain()

    asyncio.run(go())
    assert [q for q, _ in env["gen"].calls] == ["У меня стоит Каскад-18\nХотел бы подобрать новую"]


def test_message_during_generation_is_answered_next_not_in_parallel(env):
    gen = env["gen"]
    original = gen.answer_with_meta
    state = {"active": 0, "max_active": 0}

    async def go():
        loop = asyncio.get_running_loop()
        second = event(**{"data.message.id": "2", "data.message.text": "а с баком есть?"})

        def answer(session, query, user_id=None, **kw):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            if len(gen.calls) == 0:
                # the client writes again while the first answer is being generated
                asyncio.run_coroutine_threadsafe(svc.handle_event(second), loop).result()
            try:
                return original(session, query, user_id=user_id, **kw)
            finally:
                state["active"] -= 1

        gen.answer_with_meta = answer
        await svc.handle_event(event())
        await drain()

    asyncio.run(go())
    assert [q for q, _ in gen.calls] == ["посоветуйте печь для бани на 14 кубов", "а с баком есть?"]
    assert state["max_active"] == 1
    assert [c[0] for c in calls()] == ["send", "send"]


def test_queued_messages_left_to_operator_after_escalation(env):
    run(event(**{"data.message.id": "1", "data.message.text": "Здравствуйте"}),
        event(**{"data.message.id": "2", "data.message.text": "где мой заказ №12345"}))
    assert env["gen"].calls == []
    assert calls() == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]


def test_queued_messages_left_to_manager_from_phone(env):
    run(event(**{"data.message.id": "1", "data.message.text": "Добрый день!"}),
        event(**{"data.message.id": "2", "data.message.text": WZ_OUTGOING}))
    assert env["gen"].calls == [] and calls() == [("operator", 19167)]


def test_queue_is_cleaned_up(env):
    run(event())
    assert svc._queues == {}


# ── manager outside Bitrix24 → session goes to the line's queue ───────────

def test_manager_from_wazzup_in_bitrix_also_goes_to_queue(env):
    run(event(**{"data.message.text": "=== Исходящее сообщение, автор: Битрикс24 (Диджитал Клаудс Интегратор) ===\nДобрый день! Нужна печь?"}))
    assert calls() == [("operator", 19167)] and env["gen"].calls == []


def test_manager_echo_uses_configured_transfer_target(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_transfer_to", "queue7")
    run(event(**{"data.message.text": WZ_OUTGOING}))
    assert calls() == [("transfer", 19167, "queue7", False)]


@pytest.mark.parametrize("error", [B24Error("WRONG_CHAT", "Operator is not a bot"), B24Error("ACCESS_DENIED"), RuntimeError("timeout")])
def test_manager_echo_never_messages_the_client_even_if_transfer_fails(env, error):
    # already with an operator / bot lost the session / network — the bot stays
    # silent either way: no "не получилось передать" text in the client's WhatsApp
    FakeClient.transfer_error = error
    run(event(**{"data.message.text": WZ_OUTGOING}))
    assert [c[0] for c in calls()] == ["operator"]
    assert sessions.get_status(19167) == STATUS_OPERATOR and env["logged"] == []


def test_every_manager_echo_retries_the_queue_handoff(env):
    # stateless on purpose: if the first attempt raced the session start, the next
    # manager message gets it into the queue; afterwards Bitrix says WRONG_CHAT
    run(event(**{"data.message.id": "1", "data.message.text": WZ_OUTGOING}))
    run(event(**{"data.message.id": "2", "data.message.text": "=== Исходящее сообщение, автор: Телефон ===\nВы тут?"}))
    assert calls() == [("operator", 19167), ("operator", 19167)]


def test_employee_writing_in_the_open_line_is_not_transferred(env):
    # the employee answers inside the Open Line — the dialog is already theirs
    run(event(**{"data.message.text": "Добрый день, чем помочь?", "data.user.id": "1", "data.user.connector": "0"}))
    assert calls() == [] and sessions.get_status(19167) == STATUS_OPERATOR


# ── Wazzup lines: a text hint instead of the button ──────────────────────

WZ_LINE = "wz_max_connec1fe2d3c4e|19|5b1c2d3e-aaaa-bbbb-cccc-0123456789ab|2577"


def wz_event(line="19", **overrides) -> B24Event:
    return event(**{"data.chat.entityId": WZ_LINE.replace("|19|", f"|{line}|"), **overrides})


def test_wazzup_line_gets_text_hint_instead_of_button(env):
    run(wz_event())
    [send] = calls()
    assert send[3] == "[b]Русь-12 Л[/b] подойдёт\nhttps://teplodar.ru/x_y/\n\n" + svc.OPERATOR_HINT
    assert send[4] is None
    # what the hint asks for works
    assert svc.escalation_reason("специалист") == svc.REASON_REQUESTED


def test_fallback_on_wazzup_line_also_carries_the_hint(env):
    env["gen"].fail = True
    run(wz_event())
    [send] = calls()
    assert send[3] == svc.FALLBACK_TEXT + "\n\n" + svc.OPERATOR_HINT and send[4] is None


def test_quoted_bot_answer_is_not_the_clients_words():
    # a reply quoting the bot's answer quotes its hint too
    quoted = f">>Котёл подойдёт. {svc.OPERATOR_HINT}\n \n \nа сколько стоит доставка в Уфу?"
    assert svc.escalation_reason(quoted) is None
    assert svc.escalation_reason(">>Котёл подойдёт.\n \n \nпозовите специалиста") == svc.REASON_REQUESTED


# ── complaints about the bot → human ─────────────────────────────────────

BOT_COMPLAINTS = [
    "там какой-то робот отписками бестолковыми со мной общается",
    "Это робот отвечает чтоли зачем мне одно и тоже сообщение в ответ",
    "Ясно переписываюсь с ботом.", "Вы меня не поняли", "вы не поняли вопрос",
    "какую-то ерунду отвечаете", "вы не понимаете что я спрашиваю",
]
NOT_BOT_COMPLAINTS = [
    "работает ли котёл без электричества?", "магазин на улице Ботанической есть?",
    "я не понял, а цена какая?", "подойдёт ли дверца от Практика 14?",
]


@pytest.mark.parametrize("text", BOT_COMPLAINTS)
def test_bot_complaint_goes_straight_to_operator(env, text):
    assert svc.escalation_reason(text) in (svc.REASON_COMPLAINT, svc.REASON_REQUESTED)
    run(wz_event(**{"data.message.text": text}))
    assert env["gen"].calls == []
    assert calls() == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]
    assert sessions.get_status(19167) == STATUS_OPERATOR


@pytest.mark.parametrize("text", NOT_BOT_COMPLAINTS)
def test_not_a_bot_complaint(text):
    assert svc.escalation_reason(text) is None


def answer_with(env, html, **meta):
    gen = env["gen"]

    def answer_with_meta(session, query, user_id=None, **kw):
        gen.calls.append((query, user_id))
        return html, SimpleNamespace(**{
            "query_type": "RAG_PRODUCT", "top_score": 0.7, "chunks_used": 3, "city": None,
            "reformulated_query": None, "t_intent_ms": None, "t_retrieval_ms": 1, "t_answer_ms": 1,
            "t_answer_model": "sonnet", **meta,
        })

    gen.answer_with_meta = answer_with_meta


def test_answer_promising_a_transfer_is_a_transfer(env):
    # intent timed out (no needs_human), the answer prompt's complaint template kicked in
    answer_with(env, "Мне жаль, что так получилось. Я переадресую вас на живого оператора: <b>8 800 101-43-53</b>")
    run(wz_event(**{"data.message.text": "почему мне никто не отвечает уже неделю"}))
    assert calls() == [("send", 511, "chat19167", svc.TRANSFER_TEXT, None), ("operator", 19167)]
    assert [l["query_type"] for l in env["logged"]] == ["OPERATOR"]


# ── «спасибо» / 👍 → no answer ────────────────────────────────────────────

ACKS = [
    "Спасибо", "Спасибо большое!)", "👍", "❤️", "Хорошо", "Понятно, спасибо.", "ок", "От души бро Спасибо",
    "Обязательно🌸 прекрасного дня", ">>Отлично! Будем рады помочь с новым заказом в любое время. Обращайтесь!\n \n \n👍",
    ">>Спасибо, и вам хороших выходных! 😊\n \n \n❤️\n>>Спасибо, и вам хороших выходных! 😊\n \n \n❤️",
]
NOT_ACKS = [
    "Да", "Нет", "Спасибо, а сколько стоит доставка?", "Здравствуйте. Спасибо", "???",
    "Хорошо сделаю на этой недели", ">>Отлично!\n \n \nа гарантия какая",
]


@pytest.mark.parametrize("text", ACKS)
def test_acknowledgement(text):
    assert svc.is_acknowledgement(text) and svc.escalation_reason(text) is None


@pytest.mark.parametrize("text", NOT_ACKS)
def test_not_acknowledgement(text):
    assert not svc.is_acknowledgement(text)


def test_thank_you_gets_no_answer(env):
    run(wz_event(**{"data.message.text": "Спасибо большое!"}))
    assert env["gen"].calls == [] and calls() == [] and env["logged"] == []
    assert sessions.get_status(19167) == STATUS_BOT


def test_thank_you_with_a_question_in_the_burst_is_answered(env):
    run(
        wz_event(**{"data.message.id": "1", "data.message.text": "Спасибо"}),
        wz_event(**{"data.message.id": "2", "data.message.text": "а доставка в Уфу сколько?"}),
    )
    assert env["gen"].calls[0][0] == "Спасибо\nа доставка в Уфу сколько?"
    assert [c[0] for c in calls()] == ["send"]


# ── the service engineer's own line ───────────────────────────────────────

ENGINEER_ANSWER = (
    "Пришлите фото и замеры детали сервисному инженеру Андрею: <b>8-999-303-09-27</b> "
    "(WhatsApp/MAX, пн–пт 8:00–17:00 НСК)."
)


def test_engineer_line_hands_off_instead_of_sending_to_the_same_number(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_engineer_lines", "19, 25")
    answer_with(env, ENGINEER_ANSWER, query_type="FAQ_EXACT")
    run(wz_event(line="19", **{"data.message.text": "Нужна жаровня для пеллетной горелки АПГ-25"}))
    assert calls() == [("send", 511, "chat19167", svc.ENGINEER_TRANSFER_TEXT, None), ("operator", 19167)]
    assert env["logged"][0]["answer"] == svc.ENGINEER_TRANSFER_TEXT
    assert sessions.get_status(19167) == STATUS_OPERATOR


def test_engineer_number_is_a_normal_answer_on_other_lines(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "b24_engineer_lines", "19,25")
    answer_with(env, ENGINEER_ANSWER, query_type="FAQ_EXACT")
    run(wz_event(line="15", **{"data.message.text": "Нужна жаровня для пеллетной горелки АПГ-25"}))
    [send] = calls()
    assert "8-999-303-09-27" in send[3] and sessions.get_status(19167) == STATUS_BOT


def test_engineer_lines_unset_change_nothing(env):
    answer_with(env, ENGINEER_ANSWER, query_type="FAQ_EXACT")
    run(wz_event(line="19", **{"data.message.text": "Нужна жаровня для пеллетной горелки АПГ-25"}))
    assert [c[0] for c in calls()] == ["send"] and sessions.get_status(19167) == STATUS_BOT
