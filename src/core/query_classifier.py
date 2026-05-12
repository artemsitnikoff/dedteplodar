"""Classify incoming queries to route them to the right handler."""
from __future__ import annotations

import re
from enum import Enum


class QueryType(str, Enum):
    FAQ_COMPANY = "FAQ_COMPANY"    # contacts, hours, delivery, warranty, payment
    FAQ_DEALER  = "FAQ_DEALER"     # store / dealer in a specific city
    RAG_PRODUCT = "RAG_PRODUCT"    # product specs, installation, comparison


# Patterns that indicate company FAQ (not product)
_FAQ_COMPANY_PATTERNS = [
    r"\bгарантия\b",
    r"\bвозврат\b",
    r"\bобмен\b",
    r"\bдоставк",         # доставка, доставить
    r"\bдоставляет",
    r"\bоплат",           # оплата, оплатить
    r"\bрассрочк",
    r"\bхалва\b",
    r"\bяндекс\s*сплит\b",
    r"\bт[\-\s]*банк\b",
    r"\bсбербанк\b",
    r"\bкред[и]",         # кредит
    r"\bтелефон\b",
    r"\bзвон[и]",         # звонить
    r"\bгорячая\s*линия\b",
    r"\bинтернет[\s\-]*магазин\b",
    r"\bкогда\s+работает\b",
    r"\bрежим\s+работы\b",
    r"\bчасы\s+работы\b",
    r"\bзавод\b",         # где завод, где производят
    r"\bновосибирск\b",   # about the city/factory
    r"\bоснован\b",
    r"\bпроизвод[и]",     # производит, производство
    r"\bо\s+компании\b",
    r"\bо\s+теплодар\b",
    r"\bkto\b",
    r"\bосновател",
    r"\bвернуть\b",
]

# Patterns that indicate dealer / store lookup
# NOTE: no trailing \b on Russian words — inflections (магазины, дилерах, адресами…)
_FAQ_DEALER_PATTERNS = [
    r"\bмагазин",         # магазин, магазины, магазинов, магазинах
    r"\bдилер",           # дилер, дилеры, дилерах, дилерами
    r"\bпартнёр",         # партнёр, партнёры, партнёрах
    r"\bпартнер",
    r"\bкупить\b.*\bгород",
    # "где [можно/лучше/удобно/...] купить" — optional adverb between где/купить
    r"\bгде\s+(?:\w+\s+){0,2}купить\b",
    r"\bгде\s+(?:\w+\s+){0,2}найти\b",
    r"\bгде\s+(?:\w+\s+){0,2}заказать\b",
    r"\bгде\s+(?:\w+\s+){0,2}приобрести\b",
    r"\bгде\s+(?:\w+\s+){0,2}посмотреть\b",
    r"\bадрес",           # адрес, адреса, адресов
    r"\bнаход[и]",        # находится, находятся
    r"\bсамовывоз",
    r"\bвыдача\b.*\bпункт",
    r"\bпункт\s+выдачи\b",
    r"\bпри[её]мный\s+пункт",
    r"\bсервисный\s*центр",
    r"\bавторизован",
    r"\bасц\b",
    r"\bесть\s+ли\s+у\s+вас\b.*\bв\b",  # есть ли у вас в [городе]
    r"\bв\s+каком\s+(городе|магазин)",   # в каком городе, в каком магазине
    r"\bкакие\b.*\b(магазин|дилер|партнёр|партнер)",  # какие магазины/дилеры
]

_RE_COMPANY = [re.compile(p, re.I) for p in _FAQ_COMPANY_PATTERNS]
_RE_DEALER  = [re.compile(p, re.I) for p in _FAQ_DEALER_PATTERNS]

# If any of these match, force RAG_PRODUCT regardless of company/dealer patterns.
# Catches questions like "гарантия на Спутник-3" or "доставка Куппера".
_RAG_OVERRIDE_PATTERNS = [
    # Known product families (sample names from the catalog)
    r"\bспутник\b",
    r"\bкуппер\b",
    r"\bкузбасс\b",
    r"\bкаскад\b",
    r"\bрусь\b",
    r"\bсахара\b",
    r"\bсибирь\b",
    r"\bтамань\b",
    r"\bбылина\b",
    r"\bутёс\b",  r"\bутес\b",
    r"\bпанорама\b",
    r"\bпрофи\b",
    r"\bтарий\b",
    r"\bметеор\b",
    r"\bвертикаль\b",
    r"\bпечурка\b",
    r"\bкадриль\b",
    r"\bтанго\b",
    r"\bрумба\b",
    r"\bсиеста\b",
    r"\bкомпар\b",
    r"\bтоп[\-\s]?драйв\b",
    r"\bтоп[\-\s]?модель\b",
    # Generic product nouns
    r"\bкамин\b",
    r"\bпечь\b",  r"\bпечи\b",  r"\bпечей\b",
    r"\bкотёл\b", r"\bкотел\b", r"\bкотлы\b", r"\bкотла\b",
    r"\bкаменк",  # каменка, каменки
    r"\bэлектрокотел", r"\bэлектрокотл",
    r"\bбойлер\b",
    r"\bтэн\b",
    r"\bовк\b",   # ОВК серия котлов
    # Model-number patterns:
    #  - letter + dash + digit  → Спутник-3, ОВК-9, Куппер-14
    r"[а-яёА-ЯЁa-zA-Z]-\d",
]

# Case-sensitive patterns — must NOT use re.I, otherwise "доставка 30 дней"
# matches a model-name heuristic. Capitalized RU word + space + 2+ digits.
_RAG_OVERRIDE_CASE_PATTERNS = [
    r"\b[А-ЯЁ][а-яё]{2,}\s+\d{2,}\b",  # "Норма 26", "Метеор 150", "Утёс 100"
]

_RE_RAG_OVERRIDE = [re.compile(p, re.I) for p in _RAG_OVERRIDE_PATTERNS]
_RE_RAG_OVERRIDE_CASE = [re.compile(p) for p in _RAG_OVERRIDE_CASE_PATTERNS]


_WHERE_PURCHASE_RE = re.compile(
    r"\bгде\s+(?:\w+\s+){0,3}"
    r"(купить|найти|заказать|приобрест|посмотреть|выбрать|забрать)",
    re.IGNORECASE,
)


def classify(query: str) -> QueryType:
    """Classify query into FAQ_COMPANY | FAQ_DEALER | RAG_PRODUCT."""
    q = query.strip()

    # Strict dealer intent FIRST — "где [можно/...] купить + известный город"
    # beats every other signal, including RAG_OVERRIDE's generic "печь/котёл".
    # The user explicitly asked WHERE; product nouns are just inventory.
    if _WHERE_PURCHASE_RE.search(q) and _mentions_known_dealer_city(q):
        return QueryType.FAQ_DEALER

    # If query mentions a specific product/model → always RAG, even if company
    # keywords (гарантия, доставка…) are also present.
    for pat in _RE_RAG_OVERRIDE:
        if pat.search(q):
            return QueryType.RAG_PRODUCT
    for pat in _RE_RAG_OVERRIDE_CASE:
        if pat.search(q):
            return QueryType.RAG_PRODUCT

    # COMPANY first — more specific; prevents "интернет-магазин" / "завод" matching DEALER
    for pat in _RE_COMPANY:
        if pat.search(q):
            return QueryType.FAQ_COMPANY

    for pat in _RE_DEALER:
        if pat.search(q):
            return QueryType.FAQ_DEALER

    # Looser fallback: any purchase-intent + known dealer city, no "где" needed
    # (covers "купить в Краснодаре", "заказать в Самаре").
    if _has_purchase_intent(q) and _mentions_known_dealer_city(q):
        return QueryType.FAQ_DEALER

    return QueryType.RAG_PRODUCT


_PURCHASE_INTENT_RE = re.compile(
    r"\b(купить|приобрест|заказать|найти|посмотреть|выбрать|забрать|самовывоз|покупк)",
    re.IGNORECASE,
)


def _has_purchase_intent(query: str) -> bool:
    return bool(_PURCHASE_INTENT_RE.search(query))


def _mentions_known_dealer_city(query: str) -> bool:
    """True if the query mentions a city that exists in our dealers DB.

    Late import + lazy lookup so the classifier module stays cheap to import
    in tests / standalone tooling.
    """
    try:
        from src.core.dealer_lookup import find_dealers
        # _extract_city lives in answer_generator; replicate the simplest case
        # here: take any "в <CapWord>" or known multi-word city pattern.
        m = re.search(r"\bв\s+([А-ЯЁа-яёA-Za-z][а-яёa-z\-]+(?:[\s-][А-ЯЁА-яёa-z][а-яёa-z\-]+)?)", query)
        if not m:
            return False
        matched_city, shops = find_dealers(m.group(1))
        return bool(matched_city and shops)
    except Exception:
        return False
