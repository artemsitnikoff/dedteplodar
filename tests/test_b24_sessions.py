from datetime import timedelta

import pytest

from src.b24 import sessions
from src.b24.models import STATUS_BOT, STATUS_OPERATOR, B24Session
from src.b24.webhook import B24Event
from src.core.database import SessionLocal
from tests.test_b24_webhook import message_add_payload


@pytest.fixture(autouse=True)
def clean_table():
    with SessionLocal() as s:
        s.query(B24Session).delete()
        s.commit()


def ev(**o) -> B24Event:
    return B24Event.from_payload(message_add_payload(**o))


def test_parse_entity_id():
    assert sessions.parse_entity_id("livechat|13|19165|515") == ("13", "19165")
    assert sessions.parse_entity_id("") == (None, None)
    assert sessions.parse_entity_id("livechat") == (None, None)


def test_touch_creates_and_updates():
    st = sessions.touch(ev(), operator_ttl_minutes=60)
    assert st.status == STATUS_BOT and st.is_new_dialog and st.line_session_id == "19165"
    st2 = sessions.touch(ev(**{"data.message.id": "2"}), operator_ttl_minutes=60)
    assert not st2.is_new_dialog
    with SessionLocal() as s:
        row = s.get(B24Session, 19167)
        assert row.dialog_id == "chat19167" and row.line_id == "13" and row.user_name == "Гость"
        assert row.last_message_id == 2


def test_handoff_then_silent_then_new_session_resets():
    sessions.touch(ev(), operator_ttl_minutes=60)
    sessions.mark_handoff(19167, "requested")
    assert sessions.get_status(19167) == STATUS_OPERATOR
    st = sessions.touch(ev(**{"data.message.id": "3"}), operator_ttl_minutes=60)
    assert st.status == STATUS_OPERATOR and st.handoff_reason == "requested"
    # operator finished; the client writes again → Bitrix opens a new line session
    st = sessions.touch(ev(**{"data.message.id": "4", "data.chat.entityId": "livechat|13|19999|515"}),
                        operator_ttl_minutes=60)
    assert st.status == STATUS_BOT and st.is_new_dialog and st.line_session_id == "19999"
    assert st.bot_turns == 0 and st.consecutive_errors == 0 and st.handoff_reason is None


def test_operator_state_expires_by_ttl():
    sessions.touch(ev(), operator_ttl_minutes=60)
    sessions.mark_handoff(19167, "requested")
    with SessionLocal() as s:
        row = s.get(B24Session, 19167)
        row.handoff_at = sessions._utcnow() - timedelta(minutes=61)
        s.commit()
    st = sessions.touch(ev(**{"data.message.id": "5"}), operator_ttl_minutes=60)
    assert st.status == STATUS_BOT
    # but not before the TTL
    sessions.mark_handoff(19167, "requested")
    st = sessions.touch(ev(**{"data.message.id": "6"}), operator_ttl_minutes=60)
    assert st.status == STATUS_OPERATOR


def test_bot_turns_and_consecutive_errors():
    sessions.touch(ev(), operator_ttl_minutes=60)
    assert sessions.mark_bot_turn(19167, error=False) == 0
    assert sessions.mark_bot_turn(19167, error=True) == 1
    assert sessions.mark_bot_turn(19167, error=True) == 2
    assert sessions.mark_bot_turn(19167, error=False) == 0
    with SessionLocal() as s:
        assert s.get(B24Session, 19167).bot_turns == 4


def test_reset_to_bot_on_join():
    sessions.touch(ev(), operator_ttl_minutes=60)
    sessions.mark_handoff(19167, "errors")
    sessions.reset_to_bot(19167)
    assert sessions.get_status(19167) == STATUS_BOT
    sessions.reset_to_bot(None)      # no-op
    sessions.reset_to_bot(424242)    # unknown chat — no-op
