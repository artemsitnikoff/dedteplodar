"""Answer generation layer: query → Claude answer using RAG + FAQ context.

Mode "cli"  — calls `claude` CLI subprocess, uses Pro subscription tokens (default).
Mode "api"  — calls Anthropic API, requires ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
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
    # Phase breakdowns — written by answer_with_meta so we can see where
    # the wall time goes per request. All in milliseconds, None if the
    # phase didn't run on this path.
    t_history_ms: int | None = None        # pulling last 3 Q&A from query_logs
    t_intent_ms: int | None = None         # Claude CLI Haiku (intent extract)
    t_retrieval_ms: int | None = None      # E5 embed + BM25 + fusion + dedup
    t_answer_ms: int | None = None         # Claude CLI final answer call
    t_answer_model: str | None = None      # which model served the final answer

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

Когда переадресовывать на оператора (НЕ пытайся отвечать сам):
• <b>Статус / оплата / отмена / изменения конкретного заказа клиента</b> — у тебя нет доступа к CRM.
  Скажи: «Это вопрос по конкретному заказу. Менеджер интернет-магазина поможет: <b>8 800 101-43-53</b> (ежедневно 9:00–20:00 по НСК, бесплатно)».
• <b>Поломка / гарантия / неисправность / монтаж</b> — нужна экспертиза сервис-инженера.
  Скажи: «По этому вопросу свяжитесь с сервисным инженером Андреем: <b>8-999-303-09-27</b> (WhatsApp/MAX, пн–пт 8:00–17:00 НСК). Пришлите ему фото или видео — поможет быстрее».
• <b>Эмоциональные жалобы</b> («не работает», «верните деньги», «ужас», «обман») — НЕ оправдывайся и не споришь.
  Скажи: «Мне жаль, что так получилось. Я переадресую вас оператору: <b>8 800 101-43-53</b>».
• <b>Out-of-scope</b> (печь для бассейна, выхлоп электрогенератора, отопление >450 м², заваривание швов) — честно говори «такое решение не из нашей линейки» и направляй на 8 800 775-03-07.
• <b>Юрлица, отказные письма, договора с НДС, сертификаты для газовщиков</b> → менеджер 8 800 101-43-53.

Когда модели нет в каталоге:
• Если упоминают <b>Тайгинку, Русь-22, Сиесту-25</b> или иную снятую модель — честно сообщи «модель снята с производства», предложи аналог только если он есть в контексте, иначе перенаправь на сервис.

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


_COMPARISON_FRAME_RE = re.compile(
    r"\b(и|vs|versus|или|против|между|чем|от|отлич\w*|сравн\w*|разниц\w*|лучше)\b",
    re.IGNORECASE,
)


def _target_strip_re(t: str) -> str:
    """Regex for a target name that also catches Russian declension endings.

    "Сахара" must strip "Сахары"/"Сахаре" too (genitive/etc.), or the competing
    name survives in the per-target query. Model codes with digits/hyphens
    ("Куппер-12") don't decline — match them verbatim.
    """
    t = t.strip()
    if re.search(r"[\d\-\s]", t):          # "Куппер-12", "Куппер ОВК 9" — no declension
        return re.escape(t) + r"\w*"
    if len(t) >= 4:                        # single word — match stem + any ending
        return re.escape(t[:-1]) + r"\w*"
    return re.escape(t) + r"\w*"


def _strip_comparison_frame(query: str, targets: list[str]) -> str:
    """Strip the compared product names + comparison connectors from a query.

    A comparison query ("чем Русь отличается от Сахары") names BOTH products,
    so a per-target retrieval built as f"{target} {query}" stays polluted by the
    competing name and the higher-scoring family drowns the other out (measured:
    Русь pages = 0 in the top-12 for "Сравнение печей Русь и Сахара…"). Removing
    every target name (incl. declensions) and the comparison words leaves a
    neutral frame ("печей характеристики") that we then prefix with a single
    target, so each family is retrieved on its own merits (measured: 6 Русь +
    6 Сахара pages).
    """
    out = query
    for t in sorted(targets, key=len, reverse=True):
        if t.strip():
            out = re.sub(_target_strip_re(t), " ", out, flags=re.IGNORECASE)
    out = _COMPARISON_FRAME_RE.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


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


_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)


def _md_to_html(text: str) -> str:
    """Convert any residual Markdown to Telegram HTML as a safety net.

    URLs are protected from markdown processing first — `_` and `*` inside
    URLs (e.g. https://teplodar.ru/catalog/detail/kaskad_12_t/) would
    otherwise be eaten by the italic/bold regexes (`_12_` → `<i>12</i>`),
    silently corrupting links.
    """
    # 1) Stash URLs behind placeholders so markdown rules can't touch them.
    placeholders: list[str] = []
    def _stash(match: re.Match) -> str:
        placeholders.append(match.group(0))
        # \x00 is illegal in our outputs (we only emit text) — safe sentinel.
        return f"\x00U{len(placeholders) - 1}\x00"
    text = _URL_RE.sub(_stash, text)

    # 2) Apply markdown → HTML conversions on the URL-free text.
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

    # 3) Restore URLs verbatim.
    for i, url in enumerate(placeholders):
        text = text.replace(f"\x00U{i}\x00", url)
    return text


_LINK_INTENT_RE = re.compile(
    r"\b(ссылк\w*|url|линк\w*|адрес\s+страниц\w*|на\s+сайт\w*|где\s+(?:купить|посмотреть|найти|заказать)|покажи\s+на\s+сайте)\b",
    re.IGNORECASE,
)


def _user_wants_link(query: str) -> bool:
    """True if the user is explicitly asking for a product URL."""
    return bool(_LINK_INTENT_RE.search(query))


def _enrich_chunks_with_product_urls(session: Session, results: list[SearchResult]) -> None:
    """Inject product URL into each chunk_text so the LLM can cite real links.

    The chunker doesn't include URL in chunk_text (and a full re-index takes hours),
    so we patch chunks at query-time. Only called when the user explicitly asks for
    a link — otherwise URLs would pollute every product answer.
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


def _format_history_for_prompt(history: list[dict] | None) -> str | None:
    """Render dialog turns for the final answer prompt. None if empty."""
    if not history:
        return None
    lines = []
    for turn in history:
        role = "Пользователь" if turn.get("role") == "user" else "Бот"
        content = (turn.get("content") or "").strip()
        if len(content) > 600:
            content = content[:600] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


_CHUNK_CAP_CHARS = 700  # ~175 tokens; keeps head+tail of each retrieved chunk


def _truncate_chunk_text(text: str, max_chars: int = _CHUNK_CAP_CHARS) -> str:
    """Smart truncate that preserves both ends of a chunk.

    Catalog chunks tend to have product name + intro at the start and
    technical params (kW, kg, prices, parilka volume) at the end. A naive
    `[:N]` drops the params; a tail-only cut loses the model name. We
    keep both, joined with "...", so the LLM sees enough to identify the
    product AND its key spec values.
    """
    if len(text) <= max_chars:
        return text
    head_n = (max_chars * 2) // 3   # 2/3 to head — name + description
    tail_n = max_chars - head_n - 3  # rest to tail, minus "..." separator
    return text[:head_n].rstrip() + "..." + text[-tail_n:].lstrip()


def _build_full_prompt(
    query: str,
    chunks: list[SearchResult],
    dealer_block: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Combine system prompt + (optional) FAQ + history + RAG chunks +
    (optional) dealer info + current user query.

    Note: the static `_FAQ_TEXT` block is only included when no RAG chunks
    were retrieved (FAQ_COMPANY path). For RAG_PRODUCT queries the chunks
    already provide what the LLM needs, and the company FAQ is noise that
    inflates the prompt by ~400 tokens for nothing.
    """
    parts = [_SYSTEM_PROMPT, ""]
    if not chunks:
        parts.extend([_FAQ_TEXT, ""])
    history_block = _format_history_for_prompt(history)
    if history_block:
        parts.append(
            "Предыдущие сообщения в диалоге (для понимания контекста):\n"
            f"{history_block}\n"
        )
    if chunks:
        fragments = "\n\n".join(
            f"[{i+1}] (тип: {c.chunk_type})\n{_truncate_chunk_text(c.chunk_text.strip())}"
            for i, c in enumerate(chunks)
        )
        parts.append(f"Фрагменты из базы знаний:\n{fragments}\n")
    if dealer_block:
        parts.append(f"Информация о магазинах в городе:\n{dealer_block}\n")
    parts.append(f"Текущий вопрос пользователя: {query}")
    return "\n".join(parts)


def _call_cli_stream(
    prompt: str,
    cli_path: str = "claude",
    model: str = "",
) -> Iterator[str]:
    """Stream Claude CLI output chunk-by-chunk via Popen.

    Why: `subprocess.run(...).stdout` blocks for the whole inference. With
    a 20-token-per-second model that's 15-20 s before the user sees ANY
    text — Telegram shows "typing…" the whole time. Streaming via Popen
    surfaces the first words within 1-2 s of model start.

    Output is plain text (CLI's `--output-format text` flushes
    progressively as the model generates). Each `read1` returns whatever
    bytes are currently available up to the buffer size.
    """
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    args = [
        cli_path,
        "--print",
        "--output-format", "text",
        "--no-session-persistence",
        "--tools", "",
    ]
    if model:
        args += ["--model", model]

    from ..core.claude_cli import claude_cli_slot
    t_sub = time.monotonic()
    first_chunk_at: float | None = None
    total_bytes = 0
    rc: int | None = None
    # Capture stderr eagerly inside the `with` block — by the time we
    # raise on rc!=0 below, the proc pipes may already be closed by
    # gc / TemporaryDirectory teardown.
    stderr_data = b""
    with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_answer_") as cwd:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            bufsize=0,
        )
        if not (proc.stdin and proc.stdout and proc.stderr):
            raise RuntimeError("Popen failed to attach all pipes")
        try:
            proc.stdin.write(prompt.encode())
            proc.stdin.close()
            while True:
                # With bufsize=0 stdout is raw FileIO (no BufferedReader,
                # no `read1`). FileIO.read(N) does one os.read syscall:
                # returns up to N bytes when ANY arrive, b"" on EOF — the
                # exact streaming semantics we want.
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                total_bytes += len(chunk)
                yield chunk.decode("utf-8", errors="replace")
            proc.wait(timeout=10)
            rc = proc.returncode
            if rc != 0:
                # Bounded read — guard against a buggy/hostile CLI dumping
                # megabytes of stderr; we only log the first 300 chars.
                stderr_data = proc.stderr.read(65536)
        except Exception as exc:
            # Kill FIRST, then read stderr. `proc.stderr.read()` on a
            # live process can block until EOF (the pipe stays open as
            # long as the child holds its write-end). Killing forces
            # the kernel to close the write-end, after which `.read()`
            # returns whatever is buffered + b"" — never hangs.
            try:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass  # zombie, best we can do
                if proc.stderr:
                    try:
                        stderr_data = proc.stderr.read(65536)
                    except Exception:
                        pass
            except Exception:
                pass  # kill itself failed — keep stderr_data as-is (b"")
            logger.warning(
                "[answer-cli-stream] subprocess aborted: %s — stderr=%r",
                exc, stderr_data[:300],
            )
            raise
        finally:
            if proc.poll() is None:
                proc.kill()

    total_s = time.monotonic() - t_sub
    ttfb_ms = int((first_chunk_at - t_sub) * 1000) if first_chunk_at else None
    logger.info(
        "[answer-cli-stream] model=%s rc=%s ttfb=%sms total=%.2fs bytes=%d",
        model or "(default)", rc, ttfb_ms if ttfb_ms is not None else "—",
        total_s, total_bytes,
    )
    if rc != 0:
        err = stderr_data.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"claude CLI (code {rc}): {err}")
    if total_bytes == 0:
        raise RuntimeError("claude CLI returned empty response")


def _call_cli(prompt: str, cli_path: str = "claude", model: str = "") -> str:
    """Call Claude CLI subprocess. Uses Pro subscription via OAuth token.

    `model` is forwarded as `--model <...>`. Empty string = CLI default.
    """
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    args = [
        cli_path,
        "--print",
        "--output-format", "text",
        "--no-session-persistence",
        "--tools", "",
    ]
    if model:
        args += ["--model", model]

    from ..core.claude_cli import claude_cli_slot
    t_sub = time.monotonic()
    with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_answer_") as cwd:
        result = subprocess.run(
            args,
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            timeout=120,
        )
    logger.info(
        "[answer-cli] model=%s subprocess=%.2fs rc=%d",
        model or "(default)", time.monotonic() - t_sub, result.returncode,
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
        model: str = "claude-sonnet-4-6",
        reformulation_model: str = "claude-haiku-4-5-20251001",
        top_k: int = 5,
        faq_matcher=None,
    ):
        self.retriever = retriever
        self.mode = mode
        self.cli_path = cli_path
        self.answer_model = model            # forwarded to --model in CLI mode
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

    def _answer_model_label(self) -> str:
        """Short label of the model that served the final answer (for logs/footer)."""
        if self.mode == "api":
            return getattr(self, "_model", "api")
        return self.answer_model or "cli-default"

    def answer(self, session: Session, query: str) -> str:
        answer, _ = self.answer_with_meta(session, query)
        return answer

    def answer_with_meta(
        self,
        session: Session,
        query: str,
        user_id: int | None = None,
        on_chunk=None,
        history: list[dict] | None = None,
        on_phase=None,
    ) -> tuple[str, AnswerMeta]:
        """Return (answer_text, metadata).

        Pipeline:
          1. Pull last 3 Q&A turns for this user from query_logs (within 30
             minutes) to resolve anaphora ("первая", "она", "та").
          2. Single Haiku call → Intent envelope (classify + FAQ match +
             reformulate-with-history-context + city + wants_link + listing).
          3. If intent.faq_match_id → return that FAQ answer.
          4. Otherwise route by intent.intent to the right handler.
          5. Fallback to legacy regex/cosine pipeline if Haiku fails.

        `history` (web chat) — if provided (even []), it is used verbatim and
        the per-user DB lookup is skipped; the web client already holds the
        thread, so there's no 30-minute window. `None` keeps the Telegram
        behaviour (pull from query_logs by user_id).

        `on_phase(name)` — optional progress callback fired at phase
        boundaries ("intent" | "retrieval" | "answer") so a streaming caller
        can show what the pipeline is doing while Claude CLI (which doesn't
        stream tokens) produces the answer in one block.
        """
        from .intent_extractor import extract_intent
        from src.logs.queries import get_recent_dialog

        t0 = time.monotonic()

        t_history_start = time.monotonic()
        if history is None:
            history = get_recent_dialog(user_id) if user_id else []
        t_history_ms = int((time.monotonic() - t_history_start) * 1000)

        faq_entries = self.faq_matcher._entries if self.faq_matcher else []
        if on_phase:
            on_phase("intent")
        t_intent_start = time.monotonic()
        intent = extract_intent(
            query,
            faq_entries,
            cli_path=self.cli_path,
            model=self.reformulation_model,
            history=history,
        )
        t_intent_ms = int((time.monotonic() - t_intent_start) * 1000)
        logger.info("[timing] history=%dms intent=%dms", t_history_ms, t_intent_ms)

        if intent is None:
            # LLM failed — degrade to the old code path so the user still gets an answer.
            answer, meta = self._answer_legacy(session, query, t0)
            meta.t_history_ms = t_history_ms
            meta.t_intent_ms = t_intent_ms
            return answer, meta

        # 1) FAQ match takes precedence
        if intent.faq_match_id is not None and self.faq_matcher:
            entry = self.faq_matcher._entries[intent.faq_match_id]
            meta = AnswerMeta(query_type="FAQ_EXACT", top_score=1.0)
            meta.t_history_ms = t_history_ms
            meta.t_intent_ms = t_intent_ms
            meta.latency_ms = int((time.monotonic() - t0) * 1000)
            return entry.answer, meta

        # 2) Routed handlers — they take pre-extracted data from `intent`
        if intent.intent == "FAQ_DEALER":
            answer, meta = self._handle_dealer_meta(query, city_hint=intent.city)
        elif intent.intent == "FAQ_COMPANY":
            if on_phase:
                on_phase("answer")
            t_ans_start = time.monotonic()
            answer = self._stream_collect(
                self._call_claude(query, chunks=[], history=history),
                on_chunk,
            )
            meta = AnswerMeta(query_type="FAQ_COMPANY")
            meta.t_answer_ms = int((time.monotonic() - t_ans_start) * 1000)
            meta.t_answer_model = self._answer_model_label()
        else:
            answer, meta = self._handle_rag_meta(
                session, query, intent=intent, history=history,
                on_chunk=on_chunk, on_phase=on_phase,
            )

        meta.t_history_ms = t_history_ms
        meta.t_intent_ms = t_intent_ms
        meta.latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[timing] total=%dms (history=%dms intent=%dms retrieval=%sms answer=%sms model=%s)",
            meta.latency_ms, meta.t_history_ms, meta.t_intent_ms,
            meta.t_retrieval_ms if meta.t_retrieval_ms is not None else "—",
            meta.t_answer_ms if meta.t_answer_ms is not None else "—",
            meta.t_answer_model or "—",
        )
        return answer, meta

    def _answer_legacy(self, session: Session, query: str, t0: float) -> tuple[str, AnswerMeta]:
        """Fallback path used when the LLM intent extractor errors out."""
        if self.faq_matcher:
            match = self.faq_matcher.find(query)
            if match:
                meta = AnswerMeta(query_type="FAQ_EXACT", top_score=match.score)
                meta.latency_ms = int((time.monotonic() - t0) * 1000)
                return match.answer, meta

        qtype = classify(query)
        logger.debug(f"[legacy {self.mode}] {qtype.value} | {query[:60]}")
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

    def _handle_dealer_meta(self, query: str, city_hint: str | None = None) -> tuple[str, AnswerMeta]:
        # Intent extractor already normalises the city to nominative case; use
        # it if provided, otherwise fall back to the regex extractor.
        city = city_hint or _extract_city(query)
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

    def _stream_collect(self, iterator: Iterator[str], on_chunk=None) -> str:
        """Consume a streaming-text iterator, fanning each delta to `on_chunk`
        if provided, and return the full text with markdown→HTML applied.

        Markdown rendering is applied to the FULL string at the end so
        partially-streamed bold/italic markers don't get garbled in
        intermediate previews. Telegram permits us to edit the message
        once more after streaming completes."""
        parts: list[str] = []
        for delta in iterator:
            parts.append(delta)
            if on_chunk is not None:
                try:
                    on_chunk(delta)
                except Exception as cb_exc:
                    logger.warning("on_chunk callback failed: %s", cb_exc)
        return _md_to_html("".join(parts))

    def _handle_rag_meta(self, session: Session, query: str, intent=None, history=None, on_chunk=None, on_phase=None) -> tuple[str, AnswerMeta]:
        if on_phase:
            on_phase("retrieval")
        t_ret_start = time.monotonic()
        # Use the LLM-reformulated query if intent extractor produced one,
        # otherwise call the legacy reformulator (used by the fallback path).
        if intent and intent.reformulated_query:
            retrieval_query = intent.reformulated_query
        else:
            retrieval_query = reformulate(query, self.cli_path, self.reformulation_model)

        # Listing flag from intent (LLM decided) or legacy regex fallback.
        is_listing = (
            intent.is_listing if intent
            else (_is_listing_query(query) or _is_listing_query(retrieval_query))
        )
        k = _LISTING_TOP_K if is_listing else self.top_k

        # Fan out retrieval for compound queries:
        # - comparison ("Русь vs Сахара") — one search per product family,
        #   otherwise top-k ranks chunks of one family and the other vanishes
        # - kW range ("12-15 кВт")        — one search per value
        # - plain query                   — one search
        comparison_targets = (intent.comparison_targets if intent else []) or []
        sub_queries = _expand_kw_range(retrieval_query)

        if comparison_targets:
            all_results: list[SearchResult] = []
            per_k = max(k, 6)
            seen_ids: set[int] = set()
            # Neutral frame with every compared name + comparison words removed,
            # so each per-target search isn't dominated by the other family.
            frame = _strip_comparison_frame(retrieval_query, comparison_targets)
            for target in comparison_targets:
                target_query = f"{target} {frame}".strip()
                for r in self.retriever.search(session, target_query, k=per_k):
                    if r.id not in seen_ids:
                        seen_ids.add(r.id)
                        all_results.append(r)
            results = _dedup_by_product(all_results, limit=_LISTING_TOP_K)
        elif len(sub_queries) > 1:
            all_results: list[SearchResult] = []
            per_k = max(k, 6)
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

        # Always inject product URLs into chunks — the LLM should know what
        # link goes with which product even if the user didn't explicitly
        # ask for one. Previously we gated on `wants_link`, which made the
        # bot reply "ссылки нет в базе" when the user was *correcting* a
        # URL ("у тебя неправильная ссылка") — Haiku correctly classified
        # that as not-asking-for-a-link, but the bot then had no link to
        # confirm. Token cost: ~12 chars per chunk = negligible vs answer.
        # `wants_link` is still read so the LLM's intent envelope stays
        # complete and logs/footer can show what was detected.
        wants_link = intent.wants_link if intent else _user_wants_link(query)
        _enrich_chunks_with_product_urls(session, results)

        # Compound merge: if the user named a city, inject the dealer block
        # so one RAG answer covers both "что за товар" and "где купить".
        dealer_block: str | None = None
        matched_city: str | None = None
        shops: list = []
        city = (intent.city if intent else None) or _extract_city(query)
        if city:
            matched_city, shops = find_dealers(city)
            if matched_city and shops:
                dealer_block = format_dealer_reply(city)

        t_retrieval_ms = int((time.monotonic() - t_ret_start) * 1000)

        meta = AnswerMeta(
            query_type=QueryType.RAG_PRODUCT.value,
            top_score=results[0].score if results else None,
            chunks_used=len(results),
            reformulated_query=retrieval_query if retrieval_query != query else None,
            city=matched_city if dealer_block else None,
            shops_count=len(shops) if dealer_block else 0,
            t_retrieval_ms=t_retrieval_ms,
        )
        # Answer uses the original query so the LLM sees natural language
        if on_phase:
            on_phase("answer")
        t_ans_start = time.monotonic()
        answer = self._stream_collect(
            self._call_claude(query, chunks=results, dealer_block=dealer_block, history=history),
            on_chunk,
        )
        meta.t_answer_ms = int((time.monotonic() - t_ans_start) * 1000)
        meta.t_answer_model = self._answer_model_label()
        logger.info(
            "[timing] retrieval=%dms answer=%dms",
            meta.t_retrieval_ms, meta.t_answer_ms,
        )
        return answer, meta

    # ─────────────────────────────────────────────── LLM dispatch

    def _call_claude(
        self, query: str, chunks: list[SearchResult],
        dealer_block: str | None = None,
        history: list[dict] | None = None,
    ) -> Iterator[str]:
        if self.mode == "cli":
            yield from self._call_cli_mode(query, chunks, dealer_block, history)
        else:
            yield from self._call_api_mode(query, chunks, dealer_block, history)

    def _call_cli_mode(
        self, query: str, chunks: list[SearchResult],
        dealer_block: str | None = None,
        history: list[dict] | None = None,
    ) -> Iterator[str]:
        prompt = _build_full_prompt(query, chunks, dealer_block, history)
        # Stream raw text deltas. Markdown→HTML conversion is applied by
        # the caller AFTER streaming completes (Telegram needs the full
        # message before parse_mode=HTML can be rendered safely).
        yield from _call_cli_stream(prompt, self.cli_path, self.answer_model)

    def _call_api_mode(
        self, query: str, chunks: list[SearchResult],
        dealer_block: str | None = None,
        history: list[dict] | None = None,
    ) -> Iterator[str]:
        user_content = query
        if chunks:
            fragments = "\n\n".join(
                f"[{i+1}] (тип: {c.chunk_type})\n{c.chunk_text.strip()}"
                for i, c in enumerate(chunks)
            )
            user_content = f"Фрагменты из базы знаний:\n{fragments}\n\nВопрос: {query}"
        if dealer_block:
            user_content = f"Информация о магазинах в городе:\n{dealer_block}\n\n{user_content}"
        history_block = _format_history_for_prompt(history)
        if history_block:
            user_content = (
                f"Предыдущие сообщения в диалоге (для понимания контекста):\n"
                f"{history_block}\n\n{user_content}"
            )

        with self._api_client.messages.stream(
            model=self._model,
            max_tokens=512,
            system=self._system_blocks,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for text in stream.text_stream:
                yield text
