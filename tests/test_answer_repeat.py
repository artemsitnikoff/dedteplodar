"""FAQ_EXACT must not send the same canned answer twice in one dialog."""
from types import SimpleNamespace

import pytest

ag = pytest.importorskip("src.rag.answer_generator")  # pulls torch via the retriever
from src.rag import intent_extractor  # noqa: E402
from src.rag.intent_extractor import Intent  # noqa: E402

FAQ = "Производим диаметры <b>115, 150, 200 мм</b> (внутренний)."


@pytest.fixture()
def gen(monkeypatch):
    g = ag.AnswerGenerator.__new__(ag.AnswerGenerator)
    g.cli_path, g.reformulation_model, g.mode = "claude", "haiku", "cli"
    g.faq_matcher = SimpleNamespace(
        _entries=[SimpleNamespace(id=7, question="Какие диаметры дымохода?", answer=FAQ)],
        find=lambda q: SimpleNamespace(answer=FAQ, score=0.9),
    )
    g._handle_rag_meta = lambda session, query, **kw: ("RAG", ag.AnswerMeta(query_type="RAG_PRODUCT"))
    monkeypatch.setattr(intent_extractor, "extract_intent", lambda *a, **kw: Intent(intent="RAG_PRODUCT", faq_match_id=0))
    return g


def test_first_time_the_faq_answer_is_sent(gen):
    answer, meta = gen.answer_with_meta(None, "какие диаметры у трубы?", history=[])
    assert answer == FAQ and meta.query_type == "FAQ_EXACT"


def test_same_faq_again_falls_through_to_the_routed_handler(gen):
    history = [
        {"role": "user", "content": "нужна сэндвич труба"},
        {"role": "assistant", "content": FAQ.replace(" ", "  ")},  # whitespace differences don't matter
    ]
    answer, meta = gen.answer_with_meta(None, "У меня выход с котла 160 мм, что делать?", history=history)
    assert answer == "RAG" and meta.query_type == "RAG_PRODUCT"


def test_legacy_path_skips_a_repeated_faq_too(gen, monkeypatch):
    monkeypatch.setattr(intent_extractor, "extract_intent", lambda *a, **kw: None)
    history = [{"role": "assistant", "content": FAQ}]
    answer, meta = gen.answer_with_meta(None, "печь для бани на 14 кубов", history=history)
    assert answer == "RAG" and meta.query_type == "RAG_PRODUCT"
