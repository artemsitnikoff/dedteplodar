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
Прочитай вопрос пользователя в контексте недавнего диалога и верни СТРОГО JSON со следующими полями:

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

2. **faq_match_id**: Внимательно прочитай ВЕСЬ список FAQ ниже. Если есть запись, которая по смыслу отвечает на вопрос пользователя — верни её номер. Не нужна 100% текстовая идентичность — достаточно того, что **ответ из этой FAQ-записи был бы полезен пользователю**. Парафразы, сокращения, разговорные формулировки — всё это совпадение.

   **ИСКЛЮЧЕНИЕ 1 — личные/конкретные вопросы**: если в вопросе есть «мой / моего / моей / для меня / тот что я заказал / у меня / в моём» — это вопрос про **конкретный заказ клиента**. FAQ-матч **НЕ применяется**, верни `null` — бот эскалирует на оператора через FAQ_COMPANY.

   **ИСКЛЮЧЕНИЕ 2 — конкретика vs плейсхолдеры в FAQ**: многие FAQ-записи написаны как **шаблоны с плейсхолдерами**: «модель X», «парилка X м³», «площадью X м²», «в городе [город]», «модель Y». Их матчить **только когда юзер спрашивает буквально про методику** (без конкретики). Если в запросе есть:
   - **конкретная модель / серия** (Русь-12, Куппер ПРО 16, Метеор-150, Сахара-24, Сибирь-30, Былина, …) → ❌ null → RAG;
   - **конкретные параметры** (м², кубатура, кВт, габариты) с просьбой подобрать → ❌ null → RAG;
   - **конкретный город** (Сургут, Москва, Краснодар …) в вопросе про дилеров/магазин → ❌ null → FAQ_DEALER (intent), там dealer_lookup даст реальные адреса по YAML;

   FAQ-записи с плейсхолдерами просто слишком общие — они дают canned-ответ «назовите город / посоветую вам обратиться / у завода нет единой базы», и юзер получает беспомощный текст вместо реальной информации. Когда указана конкретика — иди по правильному маршруту (RAG для товаров, FAQ_DEALER для городов).

   Примеры (✅ матч):
   - User: «какая стоимость доставки?» / FAQ: «Какая стоимость доставки и куда вы доставляете?» → ✅ матч
   - User: «какие сроки доставки?» / FAQ: «Какие сроки доставки до моего города?» → ✅ матч (общий вопрос, FAQ — общий)
   - User: «можно с НДС оплатить?» / FAQ: «Можно ли купить котёл/печь для юридического лица по безналу?» → ✅ матч
   - User: «у вас работают в Тюмени?» / FAQ: «Есть ли у вас магазин/представитель в городе [город]?» → ✅ матч
   - User: «как считать кубатуру парилки?» / FAQ: «Какую банную печь выбрать для парилки определённого объёма?» → ✅ матч (юзер сам спрашивает про методику)

   Примеры (❌ null):
   - User: «когда отгрузят МОЙ заказ?» / FAQ: «Какие сроки доставки…» → ❌ null. Личный кейс — эскалация на менеджера.
   - User: «где сейчас МОЯ посылка?» / FAQ есть про доставку → ❌ null. Статус посылки.
   - User: «Если парилка 3х4, высота 2 м, какую газовую печь порекомендуете?» / FAQ: «Какую банную печь выбрать для парилки определённого объёма?» → ❌ null. Юзер хочет КОНКРЕТНЫЕ модели — RAG_PRODUCT.
   - User: «посоветуй котёл на 150 м²» / FAQ: «Какой котёл нужен для дома площадью X м²?» → ❌ null. Нужны конкретные модели — RAG_PRODUCT.
   - User: «Котёл Русь-18 Про в наличии есть?» / FAQ: «Есть ли модель X в наличии?» → ❌ null. Конкретная модель → RAG проверит каталог.
   - User: «сколько весит Куппер 22?» / FAQ есть про доставку моделей → ❌ null. Конкретная модель — RAG.
   - User: «В Сургуте на кольце Победы 45/1 написано Теплодар — где магазин?» / FAQ: «Есть ли у вас магазин/представитель в городе [город]?» → ❌ null. Конкретный город → FAQ_DEALER (dealer_lookup даст реальный адрес).
   - User: «у вас в Москве какие магазины?» / FAQ с плейсхолдером «[город]» → ❌ null → FAQ_DEALER.
   - User: «Расскажи о Русь-12» / FAQ: «Расскажи о Былина-12» → ❌ null (разные модели).
   - User: «как лучше прогреть баню?» / FAQ нет такой темы → ❌ null.

   Принцип: ЩЕДРО матчь общие/обезличенные/процедурные вопросы (условия, оплата, сроки, контакты, методика); СТРОГО отказывайся матчить (1) личные вопросы с «мой/моя/моего/у меня», (2) подбор конкретной модели — это RAG.

3. **city**: если пользователь упомянул город (в любом склонении: «в Нижнем Тагиле», «в Краснодаре», «Москву») — верни его в именительном падеже («Нижний Тагил», «Краснодар», «Москва»). Иначе null.

4. **wants_link**: true только если пользователь явно просит ссылку, URL, адрес страницы, «покажи на сайте», «дай линк». Просто «где купить» — false.

5. **reformulated_query**: переписать вопрос в технический поисковый запрос (1-2 предложения), убрав разговорные обороты. **СОХРАНИ дословно**: цифры, размеры, названия моделей, и тип товара (если в вопросе сказано «печь» — оставь «печь», не заменяй на «оборудование», «прибор», «устройство»). Не добавляй бренды/модели, которых нет в вопросе. Если в вопросе модель — обязательно включи её. Не добавляй смежные категории («горелка», «автоматика», «дымоход»), если их нет в вопросе.
   **ВАЖНО про контекст диалога**: если текущий вопрос содержит анафоры («первая», «эта», «такая же», «он», «она», «они», «тот», «эту», «вторая», «у неё», «к ней», «дешевле», «полегче», «и его»), РАСКРОЙ их в `reformulated_query`, подставив конкретные сущности из истории. Например: история «Какие есть Русь?» → ответ упомянул Русь-9 Л, Русь-12 Л, Русь-18 Л; текущий вопрос «сколько весит первая?» → `reformulated_query: "Сколько весит банная печь Русь-9 Л, её вес"`. Если текущий вопрос **самодостаточен** (явно новая тема, есть конкретное название) — историю игнорируй.

6. **product_mention**: если пользователь явно назвал модель («Русь-12 Л», «Метеор 150», «Куппер ОВК 9») — верни как есть. Иначе null.

7. **is_listing**: true если пользователь спрашивает что доступно в каталоге, а не конкретные характеристики одной модели. Триггеры: «список», «все модели», «какие есть», «какие у вас», «что есть», «есть ли что-нибудь / какое-нибудь», «варианты», «ассортимент», «что доступно», «подбери», «посоветуй несколько», «дай выбор». Также true для вопросов типа «есть что-то X?», «у вас бывают X?». Иначе false.

8. **comparison_targets**: если вопрос сравнивает несколько товаров / серий («разница X и Y», «X vs Y», «что лучше», «отличие»), верни массив их названий — например ["Русь", "Сахара"], ["Куппер-12", "Куппер-18"]. Если сравнения нет — пустой массив [].

FAQ:
{faq_list}

Контекст диалога (последние сообщения, oldest first):
{history_block}

Вопрос пользователя (текущий): {query}

Верни ТОЛЬКО валидный JSON. Без markdown, без объяснений, без префиксов."""


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _format_history(history: list[dict] | None) -> str:
    """Render dialog turns for the prompt. Returns '(пусто)' if no history."""
    if not history:
        return "(пусто — это первое сообщение)"
    lines = []
    for turn in history:
        role = "Пользователь" if turn.get("role") == "user" else "Бот"
        content = (turn.get("content") or "").strip()
        # Cap each turn so a single long bot answer doesn't blow the prompt
        if len(content) > 500:
            content = content[:500] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def extract_intent(
    query: str,
    faq_entries: list,
    cli_path: str = "claude",
    model: str = "",
    history: list[dict] | None = None,
) -> Optional[Intent]:
    """Run one Haiku call and parse the intent envelope.

    `history` is a list of `{role, content}` dicts (oldest first) used to
    resolve anaphora in the reformulated query. Pass [] / None for a
    stateless call.

    Returns None on any failure (timeout, bad JSON, subprocess error) so
    callers can fall back to the legacy regex/cosine pipeline.
    """
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    faq_list = "\n".join(
        f"{i + 1}. {e.question.strip()}" for i, e in enumerate(faq_entries)
    ) or "(нет записей)"

    # Log what the intent extractor actually sees — to debug "I created
    # a FAQ entry but the bot doesn't match it" issues.
    logger.info(
        "[intent] query=%r | faq_entries=%d | first_faq=%r",
        query[:80],
        len(faq_entries),
        (faq_entries[0].question[:80] if faq_entries else "(empty)"),
    )

    prompt = _PROMPT.format(
        faq_list=faq_list,
        history_block=_format_history(history),
        query=query.strip(),
    )

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

    # Always log the raw LLM response so we can see WHY a FAQ match was
    # skipped (was the JSON wrong? did the LLM pick null on purpose?).
    logger.info("[intent] LLM raw response: %s", text[:500])

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
    logger.info(
        "[intent] parsed: intent=%s faq_match_id=%s city=%s wants_link=%s listing=%s product=%r reformulated=%r",
        intent.intent, intent.faq_match_id, intent.city,
        intent.wants_link, intent.is_listing, intent.product_mention,
        (intent.reformulated_query or "")[:80],
    )
    return intent
