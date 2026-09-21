"""Parsing of the intent extractor's JSON (no CLI involved)."""
from types import SimpleNamespace

from src.rag.intent_extractor import _parse_intent

FAQ = [SimpleNamespace(question=f"q{i}") for i in range(5)]


def test_parses_needs_human_and_maps_faq_index():
    raw = '```json\n{"intent": "FAQ_COMPANY", "faq_match_id": 3, "city": null, "wants_link": false, ' \
          '"reformulated_query": "статус заказа", "product_mention": null, "is_listing": false, ' \
          '"comparison_targets": [], "needs_human": true}\n```'
    it = _parse_intent(raw, "когда отгрузят мой заказ", FAQ)
    assert it.intent == "FAQ_COMPANY" and it.faq_match_id == 2 and it.needs_human is True


def test_needs_human_defaults_false_when_missing():
    raw = '{"intent": "RAG_PRODUCT", "faq_match_id": null, "reformulated_query": "печь 14 м3"}'
    it = _parse_intent(raw, "печь на 14 кубов", FAQ)
    assert it.needs_human is False and it.faq_match_id is None and it.comparison_targets == []


def test_unusable_output_returns_none():
    assert _parse_intent("no json here", "q", FAQ) is None
    assert _parse_intent('{"intent": "WHATEVER"}', "q", FAQ) is None
    assert _parse_intent('{"intent": "RAG_PRODUCT", oops', "q", FAQ) is None
