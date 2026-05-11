"""Answer generation layer: query → Claude answer using RAG + FAQ context.

Mode "cli"  — calls `claude` CLI subprocess, uses Pro subscription tokens (default).
Mode "api"  — calls Anthropic API, requires ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml
from sqlalchemy.orm import Session

from ..core.dealer_lookup import find_dealers, format_dealer_reply
from ..core.query_classifier import QueryType, classify
from .hybrid_retriever import HybridRetriever
from .query_reformulator import reformulate
from .simple_retriever import SearchResult


@dataclass
class AnswerMeta:
    query_type: str                        # "RAG_PRODUCT" | "FAQ_COMPANY" | "FAQ_DEALER"
    top_score: float | None = None         # hybrid retrieval score for top-1 chunk
    chunks_used: int = 0                   # number of RAG chunks fed to LLM
    city: str | None = None                # matched city (DEALER queries)
    shops_count: int = 0                   # shops found (DEALER queries)
    reformulated_query: str | None = None  # query after reformulation (RAG only)
    latency_ms: int | None = None          # total generation time (retrieval + LLM)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "base"
_FAQ_FILE = _DATA_DIR / "company_faq.yaml"

_SYSTEM_PROMPT = """\
Ты — консультант интернет-магазина «Теплодар» (teplodar.ru).
Теплодар производит печи для бани, отопительные печи, камины и котлы «Куппер» с 1997 года.
Завод находится в Новосибирске.

Правила ответа:
• Отвечай на русском языке, кратко и по делу.
• Опирайся только на информацию из контекста. Не выдумывай факты, модели, цифры.
• Если информации в контексте недостаточно — честно скажи об этом и предложи обратиться на teplodar.ru или по телефону 8 800 775-03-07.
• Не упоминай, что у тебя есть «контекст» или «фрагменты». Просто отвечай как живой консультант.
• Если вопрос о конкретном городе и магазинах — сначала узнай город, если он не назван.
• Используй числа и характеристики из контекста дословно — не округляй и не меняй.
• Если вопрос требует перечисления (список моделей, все варианты, какие есть и т.п.) — перечисли ВСЕ подходящие из контекста, не сокращай список.
• Ответ — не более 200 слов для обычных вопросов; для перечислений — столько, сколько нужно.
• Если в контексте к товару есть строка "Ссылка: https://teplodar.ru/…" — ОБЯЗАТЕЛЬНО приведи эту ссылку в ответе. Никогда не пиши «у меня нет ссылки», если строка «Ссылка:» присутствует в контексте.

Форматирование (ОБЯЗАТЕЛЬНО — ответ отображается в Telegram):
• Жирный текст: <b>текст</b> — НЕ используй **текст**
• Курсив: <i>текст</i> — НЕ используй *текст*
• Код/артикул: <code>текст</code> — НЕ используй `текст`
• Списки: обычные дефисы (- пункт) без каких-либо тегов
• НЕ используй Markdown-разметку вообще (никаких **, *, #, __)
• Пример правильного жирного: купить <b>Кузбасс-14 ТК</b> за 46 970 руб.
"""


def _load_faq_text() -> str:
    try:
        data = yaml.safe_load(_FAQ_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ""

    lines: list[str] = ["=== СПРАВОЧНИК КОМПАНИИ ==="]

    company = data.get("company", {})
    lines.append(f"Компания: {company.get('name','')}, основана {company.get('founded','')}, Новосибирск.")

    contacts = data.get("contacts", {})
    hl = contacts.get("hot_line", {})
    os_ = contacts.get("online_store", {})
    lines.append(f"Горячая линия завода: {hl.get('phone','')} ({hl.get('hours','')}) — бесплатно.")
    lines.append(f"Интернет-магазин: {os_.get('phone','')} ({os_.get('hours','')}), WhatsApp.")

    delivery = data.get("delivery", {})
    lines.append(f"Доставка: {delivery.get('main_rule','').strip()}")
    lines.append(f"Самовывоз: {delivery.get('self_pickup','')}")

    payment = data.get("payment", {})
    methods = [m["name"] for m in payment.get("methods", [])]
    installment = [f"{i['name']} {i['terms']}" for i in payment.get("installment", [])]
    lines.append(f"Оплата: {', '.join(methods)}.")
    lines.append(f"Рассрочка: {'; '.join(installment)}.")

    warranty = data.get("warranty", {})
    lines.append(f"Гарантия: {warranty.get('general','')}.")

    rp = data.get("return_policy", {}).get("good_quality", {})
    lines.append(f"Возврат: {rp.get('period','')} — {rp.get('conditions','').strip()}")

    own = data.get("own_stores", {})
    for s in own.get("stores", []):
        lines.append(
            f"Фирменный магазин Новосибирск: {s['address']}, "
            f"{s.get('hours_weekdays','')}, сб {s.get('hours_saturday','')}, "
            f"тел. {', '.join(s.get('phones',[]))}."
        )

    return "\n".join(lines)


_FAQ_TEXT = _load_faq_text()


_LISTING_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\bвсе\b.*\b(модел|печ|котл|камин|вариант)",
        r"\b(модел|печ|котл|камин|вариант).*\bвсе\b",
        r"\bсписок\b",
        r"\bперечисл",
        r"\bкакие\s+(есть|бывают|модел|печ|котл)",
        r"\bдай\s+(список|все\b|перечень)",
        r"\bвсе\s+(модел|вариант|серии|типы|что\s+есть)",
        r"\bмодельный\s+ряд\b",
        r"\bчто\s+(есть|имеется)\s+(в\s+наличии|из)",
        r"\b(что|какие)\s+.*\bналичи",
        r"\bвсе.*\bмощност",
        r"\bмощност.*\bвсе\b",
    ]
]

_LISTING_TOP_K = 15  # fetch more chunks for listing queries

_KW_RANGE_RE = re.compile(
    r"(\d+)\s*[-–—]\s*(\d+)\s*к[вВ][тТ]"   # "12-15 кВт" / "12–15 кВт"
    r"|от\s+(\d+)\s+до\s+(\d+)\s*к[вВ][тТ]",  # "от 12 до 15 кВт"
    re.I,
)


def _is_listing_query(query: str) -> bool:
    return any(p.search(query) for p in _LISTING_PATTERNS)


def _expand_kw_range(query: str) -> list[str]:
    """If query contains a kW range, return one query per kW value; else return [query]."""
    m = _KW_RANGE_RE.search(query)
    if not m:
        return [query]
    lo = int(m.group(1) or m.group(3))
    hi = int(m.group(2) or m.group(4))
    if hi - lo > 20:  # sanity — don't explode for huge ranges
        return [query]
    # Replace the range in the original query with each individual value
    return [
        _KW_RANGE_RE.sub(f"{kw} кВт", query, count=1)
        for kw in range(lo, hi + 1)
    ]


def _dedup_by_product(results: list[SearchResult], limit: int | None = None) -> list[SearchResult]:
    """Keep best-scoring chunk per product_id; preserve non-product chunks as-is."""
    seen: dict[int, SearchResult] = {}
    out: list[SearchResult] = []
    for r in results:
        if r.product_id is None:
            out.append(r)
            continue
        if r.product_id not in seen or r.score > seen[r.product_id].score:
            seen[r.product_id] = r
    product_chunks = sorted(seen.values(), key=lambda x: x.score, reverse=True)
    merged = product_chunks + out
    return merged[:limit] if limit else merged


def _extract_city(query: str) -> str | None:
    """Extract city name from query. Tries several patterns in order."""
    # 1. "в [городе]" — most common, handles inflections: в красноярске, в Красноярске
    m = re.search(
        r"\bв\s+([А-ЯЁа-яёA-Za-z][а-яёa-z\-]+(?:[\s-][А-ЯЁА-яёa-z][а-яёa-z\-]+)?)",
        query,
    )
    if m:
        return m.group(1)

    # 2. Capital word next to trigger words: "магазины Красноярск", "Красноярск дилеры"
    m = re.search(
        r"(?:магазин\w*|дилер\w*|партнёр\w*|адрес\w*)\s+([А-ЯЁ][а-яё\-]+(?:\s[А-ЯЁ][а-яё\-]+)?)",
        query, re.I,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"([А-ЯЁ][а-яё\-]+(?:\s[А-ЯЁ][а-яё\-]+)?)\s+(?:магазин\w*|дилер\w*|партнёр\w*)",
        query,
    )
    if m:
        return m.group(1)

    return None


def _md_to_html(text: str) -> str:
    """Convert any residual Markdown to Telegram HTML as a safety net."""
    # **bold** → <b>bold</b>  (must run before single-star)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    # *italic* (lone stars, not already converted)
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)
    # __bold__ alternative
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    # _italic_
    text = re.sub(r"_([^_\n]+?)_", r"<i>\1</i>", text)
    # `code`
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    # ### Heading → <b>Heading</b>
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    return text


def _enrich_chunks_with_product_urls(session: Session, results: list[SearchResult]) -> None:
    """Inject product URL into each chunk_text so the LLM can cite real links.

    The chunker doesn't include URL in chunk_text (and a full re-index takes hours),
    so we patch chunks at query-time by batch-loading URLs for all product_ids present.
    """
    from sqlalchemy import select
    from src.products.models import Product

    pids = {r.product_id for r in results if r.product_id}
    if not pids:
        return

    rows = session.execute(
        select(Product.id, Product.url).where(Product.id.in_(pids))
    ).all()
    url_by_pid = {pid: url for pid, url in rows if url}

    for r in results:
        if r.product_id and r.product_id in url_by_pid:
            url = url_by_pid[r.product_id]
            if url not in r.chunk_text:
                r.chunk_text = f"{r.chunk_text}\nСсылка: {url}"


def _build_full_prompt(query: str, chunks: list[SearchResult]) -> str:
    """Combine system prompt + FAQ + RAG chunks + user query into one string for CLI."""
    parts = [_SYSTEM_PROMPT, "", _FAQ_TEXT, ""]
    if chunks:
        fragments = "\n\n".join(
            f"[{i+1}] (тип: {c.chunk_type})\n{c.chunk_text.strip()}"
            for i, c in enumerate(chunks)
        )
        parts.append(f"Фрагменты из базы знаний:\n{fragments}\n")
    parts.append(f"Вопрос: {query}")
    return "\n".join(parts)


_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,"
    "WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)


def _call_cli(prompt: str, cli_path: str = "claude") -> str:
    """Call Claude CLI subprocess. Uses Pro subscription via OAuth token."""
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    result = subprocess.run(
        [
            cli_path,
            "--print",
            "--output-format", "text",
            "--no-session-persistence",
            "--disallowed-tools", _DISALLOWED_TOOLS,
        ],
        input=prompt.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd="/tmp",
        timeout=120,
    )
    if result.returncode != 0:
        err = (result.stderr.decode().strip() or result.stdout.decode().strip())[:300]
        raise RuntimeError(f"claude CLI (code {result.returncode}): {err}")
    text = result.stdout.decode().strip()
    if not text:
        raise RuntimeError("claude CLI returned empty response")
    return text


class AnswerGenerator:
    """End-to-end: query → routed answer (FAQ / dealer / RAG+LLM).

    mode="cli"  — uses `claude` CLI (Pro subscription tokens, no API key)
    mode="api"  — uses Anthropic Python SDK (requires ANTHROPIC_API_KEY)
    """

    def __init__(
        self,
        retriever: HybridRetriever,
        mode: str = "cli",
        cli_path: str = "claude",
        model: str = "claude-opus-4-7",
        reformulation_model: str = "claude-haiku-4-5-20251001",
        top_k: int = 5,
        faq_matcher=None,
    ):
        self.retriever = retriever
        self.mode = mode
        self.cli_path = cli_path
        self.reformulation_model = reformulation_model
        self.top_k = top_k
        self.faq_matcher = faq_matcher

        if mode == "api":
            import anthropic
            self._api_client = anthropic.Anthropic()
            self._system_blocks = [
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT + "\n\n" + _FAQ_TEXT,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            self._model = model

    # ─────────────────────────────────────────────── public

    def answer(self, session: Session, query: str) -> str:
        answer, _ = self.answer_with_meta(session, query)
        return answer

    def answer_with_meta(self, session: Session, query: str) -> tuple[str, AnswerMeta]:
        """Return (answer_text, metadata). Use this when you need retrieval info."""
        t0 = time.monotonic()

        # Fast path: check hand-curated FAQ first (no LLM call)
        if self.faq_matcher:
            match = self.faq_matcher.find(query)
            if match:
                meta = AnswerMeta(query_type="FAQ_EXACT", top_score=match.score)
                meta.latency_ms = int((time.monotonic() - t0) * 1000)
                return match.answer, meta

        qtype = classify(query)
        logger.debug(f"[{self.mode}] {qtype.value} | {query[:60]}")

        if qtype == QueryType.FAQ_DEALER:
            answer, meta = self._handle_dealer_meta(query)
        elif qtype == QueryType.FAQ_COMPANY:
            answer = "".join(self._call_claude(query, chunks=[]))
            meta = AnswerMeta(query_type=qtype.value)
        else:
            answer, meta = self._handle_rag_meta(session, query)

        meta.latency_ms = int((time.monotonic() - t0) * 1000)
        return answer, meta

    def stream(self, session: Session, query: str) -> Iterator[str]:
        answer, _ = self.answer_with_meta(session, query)
        yield answer

    # ─────────────────────────────────────────────── handlers

    def _handle_dealer_meta(self, query: str) -> tuple[str, AnswerMeta]:
        city = _extract_city(query)
        meta = AnswerMeta(query_type=QueryType.FAQ_DEALER.value, city=city)
        if city:
            matched_city, shops = find_dealers(city)
            meta.city = matched_city or city
            meta.shops_count = len(shops)
            return format_dealer_reply(city), meta
        return (
            "Подскажите, пожалуйста, ваш город — я найду ближайшие магазины с адресами и телефонами.",
            meta,
        )

    def _handle_rag_meta(self, session: Session, query: str) -> tuple[str, AnswerMeta]:
        # Reformulate colloquial query into retrieval-optimised form
        retrieval_query = reformulate(query, self.cli_path, self.reformulation_model)

        is_listing = _is_listing_query(query) or _is_listing_query(retrieval_query)
        k = _LISTING_TOP_K if is_listing else self.top_k

        # Expand kW range ("12-15 кВт") into per-value queries and merge results
        sub_queries = _expand_kw_range(retrieval_query)
        if len(sub_queries) > 1:
            all_results: list[SearchResult] = []
            per_k = max(k, 6)  # at least 6 per sub-query
            seen_ids: set[int] = set()
            for sq in sub_queries:
                for r in self.retriever.search(session, sq, k=per_k):
                    if r.id not in seen_ids:
                        seen_ids.add(r.id)
                        all_results.append(r)
            results = _dedup_by_product(all_results, limit=_LISTING_TOP_K)
        else:
            results = self.retriever.search(session, retrieval_query, k=k)
            if is_listing:
                results = _dedup_by_product(results, limit=_LISTING_TOP_K)

        _enrich_chunks_with_product_urls(session, results)

        meta = AnswerMeta(
            query_type=QueryType.RAG_PRODUCT.value,
            top_score=results[0].score if results else None,
            chunks_used=len(results),
            reformulated_query=retrieval_query if retrieval_query != query else None,
        )
        # Answer uses the original query so the LLM sees natural language
        answer = "".join(self._call_claude(query, chunks=results))
        return answer, meta

    # ─────────────────────────────────────────────── LLM dispatch

    def _call_claude(self, query: str, chunks: list[SearchResult]) -> Iterator[str]:
        if self.mode == "cli":
            yield from self._call_cli_mode(query, chunks)
        else:
            yield from self._call_api_mode(query, chunks)

    def _call_cli_mode(self, query: str, chunks: list[SearchResult]) -> Iterator[str]:
        prompt = _build_full_prompt(query, chunks)
        yield _md_to_html(_call_cli(prompt, self.cli_path))

    def _call_api_mode(self, query: str, chunks: list[SearchResult]) -> Iterator[str]:
        user_content = query
        if chunks:
            fragments = "\n\n".join(
                f"[{i+1}] (тип: {c.chunk_type})\n{c.chunk_text.strip()}"
                for i, c in enumerate(chunks)
            )
            user_content = f"Фрагменты из базы знаний:\n{fragments}\n\nВопрос: {query}"

        with self._api_client.messages.stream(
            model=self._model,
            max_tokens=512,
            system=self._system_blocks,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for text in stream.text_stream:
                yield text
