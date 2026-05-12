"""Single LLM intent extractor.

Replaces:
- src.core.query_classifier.classify
- src.faq.matcher.FaqMatcher.find
- src.rag.query_reformulator.reformulate
- _extract_city / _user_wants_link / _is_listing_query helpers in answer_generator

One Haiku call reads the user query + the full FAQ list and returns
a structured intent envelope. Down from 3 LLM calls per request to 2.

The Intent object is the single source of truth for the rest of the
answer pipeline: classifier, FAQ resolver, retrieval query, city for
dealer block, link request, listing-vs-single hint.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

LLM_TIMEOUT = 25  # seconds

_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,"
    "WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)


@dataclass
class Intent:
    """Structured intent extracted from a single LLM call."""
    intent: str                          # "RAG_PRODUCT" | "FAQ_COMPANY" | "FAQ_DEALER"
    faq_match_id: Optional[int] = None   # if non-null, just return that FAQ answer
    city: Optional[str] = None           # mentioned city (any case/declension)
    wants_link: bool = False             # user explicitly asked for a product URL
    reformulated_query: Optional[str] = None  # retrieval-optimised version for RAG
    product_mention: Optional[str] = None     # specific model the user named, if any
    is_listing: bool = False             # query asks for a list of models, not one
    comparison_targets: list[str] = None      # ["Русь", "Сахара"] when user compares — fan out retrieval

    def __post_init__(self):
        if self.comparison_targets is None:
            self.comparison_targets = []


_PROMPT = """Ты — анализатор запросов покупателя интернет-магазина «Теплодар» (печи, котлы, камины).
Прочитай вопрос пользователя и верни СТРОГО JSON со следующими полями:

{{
  "intent": "RAG_PRODUCT" | "FAQ_COMPANY" | "FAQ_DEALER",
  "faq_match_id": null | <номер из списка ниже>,
  "city": null | "<название города в именительном падеже>",
  "wants_link": true | false,
  "reformulated_query": "<технический поисковый запрос для базы знаний, 1-2 предложения>",
  "product_mention": null | "<точное название модели, упомянутой пользователем>",
  "is_listing": true | false,
  "comparison_targets": [] | ["Русь", "Сахара"]
}}

Правила:
1. **intent**:
   - "FAQ_DEALER" — пользователь спрашивает «где купить / магазины / адреса / есть ли в [городе]».
   - "FAQ_COMPANY" — общие вопросы о компании, оплате, доставке, гарантии, рассрочке, режиме работы, заводе.
   - "RAG_PRODUCT" — любой вопрос о товаре: характеристики, подбор по параметрам, сравнение.
   - **Приоритеты**: если «где купить + город» → FAQ_DEALER даже если упомянута модель. Если просто упомянута модель без покупательского намерения — RAG_PRODUCT.

2. **faq_match_id**: проверь список FAQ ниже. Если ОДНА из FAQ-записей по смыслу 1-в-1 отвечает на вопрос пользователя — верни её номер. Совпадение должно учитывать конкретные сущности: если в вопросе «Русь-12», FAQ должна быть про Русь-12, не про Былина-12. Иначе null.

3. **city**: если пользователь упомянул город (в любом склонении: «в Нижнем Тагиле», «в Краснодаре», «Москву») — верни его в именительном падеже («Нижний Тагил», «Краснодар», «Москва»). Иначе null.

4. **wants_link**: true только если пользователь явно просит ссылку, URL, адрес страницы, «покажи на сайте», «дай линк». Просто «где купить» — false.

5. **reformulated_query**: переписать вопрос в технический поисковый запрос (1-2 предложения), убрав разговорные обороты. Сохрани цифры, размеры, названия моделей дословно. Не добавляй бренды/модели, которых нет в вопросе. Если в вопросе модель — обязательно включи её.

6. **product_mention**: если пользователь явно назвал модель («Русь-12 Л», «Метеор 150», «Куппер ОВК 9») — верни как есть. Иначе null.

7. **is_listing**: true если просят «список / все модели / какие есть / варианты». Иначе false.

8. **comparison_targets**: если вопрос сравнивает несколько товаров / серий («разница X и Y», «X vs Y», «что лучше», «отличие»), верни массив их названий — например ["Русь", "Сахара"], ["Куппер-12", "Куппер-18"]. Если сравнения нет — пустой массив [].

FAQ:
{faq_list}

Вопрос пользователя: {query}

Верни ТОЛЬКО валидный JSON. Без markdown, без объяснений, без префиксов."""


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_intent(
    query: str,
    faq_entries: list,
    cli_path: str = "claude",
    model: str = "",
) -> Optional[Intent]:
    """Run one Haiku call and parse the intent envelope.

    Returns None on any failure (timeout, bad JSON, subprocess error) so
    callers can fall back to the legacy regex/cosine pipeline.
    """
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    faq_list = "\n".join(
        f"{i + 1}. {e.question.strip()}" for i, e in enumerate(faq_entries)
    ) or "(нет записей)"
    prompt = _PROMPT.format(faq_list=faq_list, query=query.strip())

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    args = [
        cli_path, "--print", "--output-format", "text",
        "--no-session-persistence",
        "--disallowed-tools", _DISALLOWED_TOOLS,
    ]
    if model:
        args += ["--model", model]

    try:
        result = subprocess.run(
            args,
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd="/tmp",
            timeout=LLM_TIMEOUT,
        )
        text = result.stdout.decode().strip()
    except Exception as exc:
        logger.warning("intent extractor subprocess failed: %s", exc)
        return None

    if result.returncode != 0 or not text:
        logger.warning("intent extractor returned no output (code=%s)", result.returncode)
        return None

    # Sometimes Claude wraps JSON in ```json ... ```. Pull the first {...} block.
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        logger.warning("intent extractor: no JSON block in output %r", text[:200])
        return None

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        logger.warning("intent extractor: bad JSON (%s) — %r", exc, m.group(0)[:200])
        return None

    intent_value = data.get("intent")
    if intent_value not in {"RAG_PRODUCT", "FAQ_COMPANY", "FAQ_DEALER"}:
        logger.warning("intent extractor: unknown intent %r", intent_value)
        return None

    faq_id = data.get("faq_match_id")
    faq_id_int: Optional[int] = None
    if isinstance(faq_id, int) and 1 <= faq_id <= len(faq_entries):
        faq_id_int = faq_id - 1  # convert to 0-based index for callers

    raw_targets = data.get("comparison_targets") or []
    comparison_targets = [str(t).strip() for t in raw_targets if str(t).strip()] if isinstance(raw_targets, list) else []

    intent = Intent(
        intent=intent_value,
        faq_match_id=faq_id_int,
        city=(data.get("city") or None),
        wants_link=bool(data.get("wants_link")),
        reformulated_query=(data.get("reformulated_query") or query).strip() or query,
        product_mention=(data.get("product_mention") or None),
        is_listing=bool(data.get("is_listing")),
        comparison_targets=comparison_targets,
    )
    logger.debug(
        "intent: %s faq=%s city=%s link=%s listing=%s product=%r",
        intent.intent, intent.faq_match_id, intent.city,
        intent.wants_link, intent.is_listing, intent.product_mention,
    )
    return intent
