"""Analyse Mango Office call transcripts and turn them into:
  - mango_analysis/classified.jsonl     — per-call structured analysis
  - mango_analysis/themes_report.md     — top topics + frequencies + sample phrasings
  - mango_analysis/faq_candidates.json  — ready-to-paste Q/A pairs for admin
  - mango_analysis/test_dataset.json    — real client questions for eval runs
  - mango_analysis/bot_gap_report.md    — where the bot is likely to fail

Pipeline:
  1. Parse every mango/*.html into a Conversation dict.
  2. Drop trivially short calls (< MIN_DURATION sec or < MIN_TURNS turns).
  3. Classify each remaining call with Opus via Claude CLI subprocess
     (parallel workers, incremental writes — safe to interrupt).
  4. Aggregate with one final Opus call: rank topics, draft FAQ
     candidates, pick test-dataset questions.

All LLM calls go through Claude CLI (Pro-subscription OAuth, no API key).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core.config import settings
from src.core.claude_token import ensure_fresh_token_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("analyze_calls")

ROOT = Path(__file__).parent.parent
MANGO_DIR = ROOT / "mango"
OUT_DIR = ROOT / "mango_analysis"
CLASSIFIED_PATH = OUT_DIR / "classified.jsonl"

MIN_DURATION = 60       # sec — calls shorter than this rarely have real content
MIN_TURNS = 4           # each side must speak at least twice
WORKERS = 2             # parallel CLI subprocesses (each pegs a core ~30s)
LLM_TIMEOUT = 120       # one Opus call

_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)


# ────────────────────────────────────────────────────────────────── data classes

@dataclass
class Turn:
    role: str          # "client" | "operator"
    time: str          # "12:41:52"
    text: str


@dataclass
class Conversation:
    file: str
    ts: str            # ISO date+time
    operator: str
    client_phone: str
    duration_sec: int
    turns: list[Turn]

    def flat_dialog(self) -> str:
        """Render the dialog as plain text for the LLM prompt."""
        return "\n".join(
            f"[{t.time}] {('Клиент' if t.role == 'client' else 'Оператор')}: {t.text}"
            for t in self.turns
        )


# ────────────────────────────────────────────────────────────────── 1. parse HTML

_DURATION_RE = re.compile(r"(\d+)\s*сек|(\d+)\s*мин\s*(\d+)?\s*сек?")


def _parse_duration(s: str) -> int:
    """Mango variants: `15 сек`, `11:39 сек` (mm:ss), `2 мин 30 сек`, `1 мин`."""
    s = s.strip().lower()
    # 1. mm:ss form, with optional trailing "сек"/"мин"
    m = re.match(r"^\s*(\d+):(\d{1,2})\b", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # 2. word form
    minutes = 0
    seconds = 0
    m = re.search(r"(\d+)\s*мин", s)
    if m:
        minutes = int(m.group(1))
    m = re.search(r"(\d+)\s*сек", s)
    if m:
        seconds = int(m.group(1))
    return minutes * 60 + seconds


_DATE_MONTH_RU = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def _parse_ts(s: str) -> str:
    """`10.May.2026 12:41:51` → `2026-05-10 12:41:51`."""
    m = re.match(r"(\d+)\.(\w+)\.(\d+)\s+([\d:]+)", s.strip())
    if not m:
        return s.strip()
    day, mon, year, time_ = m.groups()
    mon_num = _DATE_MONTH_RU.get(mon, mon)
    return f"{year}-{mon_num}-{day.zfill(2)} {time_}"


def parse_html(path: Path) -> Optional[Conversation]:
    """Read one Mango HTML transcript. Returns None on parse failure."""
    try:
        html = path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("read failed %s: %s", path.name, e)
        return None

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("|", strip=True)

    # Meta block
    operator = ""
    phone = ""
    duration_sec = 0
    ts = ""

    # We can also grab them from the table structure
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if not cells:
            continue
        head = cells[0].lower()
        if "запись разговоров" in head:
            # "Запись разговоров 10.May.2026 12:41:51"
            ts = _parse_ts(head.replace("запись разговоров", "").strip())
        elif "кто звонил" in head:
            operator = cells[-1].strip()
        elif "с кем говорил" in head:
            phone = cells[-1].strip()
        elif "длительность" in head:
            duration_sec = _parse_duration(cells[-1])

    # Dialog turns — rows with first cell == Клиент / Сотрудник
    turns: list[Turn] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        role_raw = cells[0].get_text(strip=True).lower()
        if role_raw not in ("клиент", "сотрудник"):
            continue
        time_raw = cells[1].get_text(strip=True)
        text_raw = cells[2].get_text(" ", strip=True)
        if not text_raw:
            continue
        turns.append(Turn(
            role="client" if role_raw == "клиент" else "operator",
            time=time_raw,
            text=text_raw,
        ))

    if not turns:
        return None

    return Conversation(
        file=path.name,
        ts=ts,
        operator=operator,
        client_phone=phone,
        duration_sec=duration_sec,
        turns=turns,
    )


# ────────────────────────────────────────────────────────────────── 2. filter

def is_meaningful(c: Conversation) -> bool:
    if c.duration_sec < MIN_DURATION:
        return False
    if len(c.turns) < MIN_TURNS:
        return False
    # Both sides must have spoken
    roles = {t.role for t in c.turns}
    if roles != {"client", "operator"}:
        return False
    return True


# ────────────────────────────────────────────────────────────────── 3. classify (Opus via CLI)

_CLASSIFY_PROMPT = """Ты — аналитик звонков техподдержки компании «Теплодар» (печи, котлы, камины).
Прочитай транскрибацию одного звонка (там бывают ошибки автоматического распознавания речи — \
например «Интернет, магазин, тепло, да» = «Интернет-магазин Теплодар»; домысли смысл) \
и верни СТРОГО JSON со следующими полями:

{{
  "topic": "<тема одной фразой>",
  "category": "consultation" | "order_status" | "complaint" | "warranty" | "delivery" | "dealer" | "spare_parts" | "callback" | "other",
  "client_questions": ["<реальные вопросы клиента, как он их формулировал>"],
  "operator_answers": ["<главные ответы оператора>"],
  "products_mentioned": ["<упомянутые модели/серии: Русь-12, Куппер, и т.д.>"],
  "outcome": "<коротко: чем закончился разговор — записали на консультацию, оформили заказ, отказали, и т.д.>",
  "bot_could_answer": true | false,
  "bot_could_answer_reason": "<одной фразой почему да/нет>",
  "notable_phrasing": "<если есть нестандартная формулировка клиента — приведи; иначе null>"
}}

ВАЖНО:
- topic — конкретно, не «вопрос про печь», а «подбор печи для парилки 12 м³».
- bot_could_answer=true если вопрос про каталог, характеристики, наличие, цены, доставку, гарантию (то что есть в базе знаний и FAQ). false если: статус КОНКРЕТНОГО заказа клиента, разбор поломки, спор по гарантии, callback-ы.
- НЕ выдумывай продукты/факты которых нет в звонке.
- Верни ТОЛЬКО JSON, без markdown-fence, без объяснений.

Транскрибация:
{dialog}

JSON:"""


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def classify_one(conv: Conversation, cli_path: str, model: str) -> dict:
    """Run one Opus subprocess and parse JSON. Returns analysis dict + meta."""
    ensure_fresh_token_sync()

    prompt = _CLASSIFY_PROMPT.format(dialog=conv.flat_dialog()[:15000])

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    args = [cli_path, "--print", "--output-format", "text",
            "--no-session-persistence",
            "--disallowed-tools", _DISALLOWED_TOOLS]
    if model:
        args += ["--model", model]

    from src.core.claude_cli import claude_cli_slot
    t0 = time.monotonic()
    try:
        with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_analyze_") as cwd:
            result = subprocess.run(
                args, input=prompt.encode(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=cwd, timeout=LLM_TIMEOUT,
            )
            raw = result.stdout.decode().strip()
    except Exception as e:
        return {"file": conv.file, "error": f"subprocess: {e}"}

    elapsed = round(time.monotonic() - t0, 1)
    if result.returncode != 0 or not raw:
        return {"file": conv.file, "error": "no_output", "elapsed_s": elapsed}

    m = _JSON_BLOCK_RE.search(raw)
    if not m:
        return {"file": conv.file, "error": "no_json", "raw": raw[:300], "elapsed_s": elapsed}

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"file": conv.file, "error": f"bad_json: {e}", "raw": raw[:300], "elapsed_s": elapsed}

    data["file"] = conv.file
    data["ts"] = conv.ts
    data["operator"] = conv.operator
    data["duration_sec"] = conv.duration_sec
    data["elapsed_s"] = elapsed
    return data


# ────────────────────────────────────────────────────────────────── 4. aggregate (Opus)

_AGGREGATE_PROMPT = """Ты — продуктовый аналитик. Тебе дана разметка {n} звонков техподдержки Теплодара.

Каждая строка — JSON с полями topic, category, client_questions, operator_answers, \
products_mentioned, outcome, bot_could_answer, notable_phrasing.

РАЗМЕЧЕННЫЕ ЗВОНКИ (jsonl):
{classified_jsonl}

Сделай следующий анализ. Верни СТРОГО JSON в формате:

{{
  "themes_report": "<markdown-отчёт: топ-20 тем с частотой, типичные формулировки клиентов, как оператор обычно отвечает>",
  "faq_candidates": [
    {{
      "question": "<вопрос как часто задают, в литературной форме>",
      "answer": "<оптимальный ответ — синтез того что отвечают операторы, HTML-теги <b>...</b> можно использовать>",
      "frequency": "<сколько раз встретилась тема>",
      "category": "consultation|delivery|warranty|..."
    }},
    ...
  ],
  "test_dataset": [
    {{
      "question": "<реальный вопрос клиента — формулировка из звонка>",
      "expected_topic": "<тема>",
      "expected_type": "RAG_PRODUCT|FAQ_COMPANY|FAQ_DEALER",
      "source_file": "<имя HTML файла>"
    }},
    ...
  ],
  "bot_gap_report": "<markdown: где бот сейчас не справится. Группировать по типам gap'ов: 'нет данных в каталоге', 'нужен статус заказа', 'эмоциональный отказ — нужен человек', и т.д. С примерами цитат.>"
}}

ОГРАНИЧЕНИЯ:
- faq_candidates: 20-30 самых частых и обобщённых вопросов
- test_dataset: 50 РЕАЛЬНЫХ вопросов из звонков (с разнообразием по темам)
- В themes_report и bot_gap_report — markdown, **жирный** для подзаголовков
- Без markdown-fence вокруг JSON, без объяснений до/после

JSON:"""


def aggregate(classified: list[dict], cli_path: str, model: str) -> dict:
    """One big Opus call to produce the four artifacts."""
    ensure_fresh_token_sync()

    # Trim each classified entry so the prompt fits — keep only essential fields
    trimmed = []
    for c in classified:
        if c.get("error"):
            continue
        trimmed.append({
            "file": c.get("file"),
            "topic": c.get("topic"),
            "category": c.get("category"),
            "client_questions": c.get("client_questions", [])[:5],
            "operator_answers": c.get("operator_answers", [])[:3],
            "products_mentioned": c.get("products_mentioned", []),
            "outcome": c.get("outcome"),
            "bot_could_answer": c.get("bot_could_answer"),
            "notable_phrasing": c.get("notable_phrasing"),
        })

    jsonl = "\n".join(json.dumps(t, ensure_ascii=False) for t in trimmed)
    prompt = _AGGREGATE_PROMPT.format(n=len(trimmed), classified_jsonl=jsonl)

    log.info("Aggregator prompt size: %.1f KB", len(prompt) / 1024)

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    args = [cli_path, "--print", "--output-format", "text",
            "--no-session-persistence",
            "--disallowed-tools", _DISALLOWED_TOOLS]
    if model:
        args += ["--model", model]

    from src.core.claude_cli import claude_cli_slot
    t0 = time.monotonic()
    with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_aggregate_") as cwd:
        result = subprocess.run(
            args, input=prompt.encode(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=cwd, timeout=600,
        )
        raw = result.stdout.decode().strip()
    log.info("Aggregator returned in %.1fs (rc=%s)", time.monotonic() - t0, result.returncode)

    if result.returncode != 0 or not raw:
        raise RuntimeError(f"aggregator failed: rc={result.returncode} stderr={result.stderr.decode()[:300]}")

    m = _JSON_BLOCK_RE.search(raw)
    if not m:
        raise RuntimeError(f"aggregator: no JSON block in output: {raw[:500]}")

    return json.loads(m.group(0))


# ────────────────────────────────────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="run only first N meaningful calls (0 = all)")
    ap.add_argument("--skip-classify", action="store_true", help="skip classify, only aggregate from existing classified.jsonl")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--model", type=str, default=settings.claude_model or "", help="Claude model — empty = CLI default (Opus)")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    cli_path = settings.claude_cli_path

    if not args.skip_classify:
        # 1. Parse
        files = sorted(MANGO_DIR.glob("*.html"))
        log.info("Found %d HTML files", len(files))
        convs: list[Conversation] = []
        for p in files:
            c = parse_html(p)
            if c is None:
                continue
            convs.append(c)
        log.info("Parsed %d conversations", len(convs))

        # 2. Filter
        meaningful = [c for c in convs if is_meaningful(c)]
        log.info("Meaningful (≥%ds, ≥%d turns): %d / %d",
                 MIN_DURATION, MIN_TURNS, len(meaningful), len(convs))
        if args.limit:
            meaningful = meaningful[: args.limit]
            log.info("Limited to %d", len(meaningful))

        # 3. Classify in parallel — incremental writes
        write_lock = threading.Lock()
        # Wipe previous run
        if CLASSIFIED_PATH.exists():
            CLASSIFIED_PATH.unlink()
        completed = 0
        total = len(meaningful)
        t_start = time.monotonic()
        results: list[dict] = []

        def _do(c: Conversation) -> dict:
            return classify_one(c, cli_path, args.model)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(_do, c): c for c in meaningful}
            for fut in as_completed(futs):
                completed += 1
                c = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"file": c.file, "error": f"exec: {e}"}
                results.append(res)
                with write_lock:
                    with CLASSIFIED_PATH.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(res, ensure_ascii=False) + "\n")
                if completed % 10 == 0 or completed == total:
                    elapsed = time.monotonic() - t_start
                    rate = completed / elapsed if elapsed else 0
                    eta = (total - completed) / rate if rate else 0
                    log.info("%d/%d classified — %.1fs elapsed, ETA %.0fs",
                             completed, total, elapsed, eta)
    else:
        # Load existing
        results = []
        with CLASSIFIED_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
        log.info("Loaded %d classified entries from %s", len(results), CLASSIFIED_PATH)

    # 4. Aggregate
    ok = [r for r in results if not r.get("error")]
    log.info("Aggregating %d/%d successful classifications", len(ok), len(results))
    agg = aggregate(ok, cli_path, args.model)

    # 5. Persist artifacts
    (OUT_DIR / "themes_report.md").write_text(agg.get("themes_report", ""), encoding="utf-8")
    (OUT_DIR / "faq_candidates.json").write_text(
        json.dumps(agg.get("faq_candidates", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "test_dataset.json").write_text(
        json.dumps(agg.get("test_dataset", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "bot_gap_report.md").write_text(agg.get("bot_gap_report", ""), encoding="utf-8")
    log.info("Wrote artifacts to %s", OUT_DIR)


if __name__ == "__main__":
    main()
