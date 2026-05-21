"""Perf diagnostic: rebuild the exact prompts the bot sends and time the CLI on each.

Usage (inside the bot container):
    docker compose exec bot python scripts/perf_diagnose.py
    docker compose exec bot python scripts/perf_diagnose.py --query "своя строка вопроса"

Outputs:
  * /tmp/prompt_intent.txt  — full intent-extractor prompt (Haiku target)
  * /tmp/prompt_answer.txt  — full answer prompt with real RAG chunks
  * stdout: prompt sizes (chars / tokens approx) and CLI elapsed for each

Why: production logs show intent=22s and answer=32s on Pro CLI. Baseline
`claude --print` on a 4-byte prompt is 3s/6s, so the inflation is prompt-
size driven. This script proves it by running the actual fat prompts
through the CLI directly, without the bot's streaming / threading layers.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Make `src.*` and `bot.*` importable when running from /app inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.core.claude_token import ensure_fresh_token_sync
from src.core.database import SessionLocal
from src.faq.matcher import FaqMatcher
from src.rag.answer_generator import _SYSTEM_PROMPT, _FAQ_TEXT, _build_full_prompt
from src.rag.embedder import E5Embedder
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.intent_extractor import _PROMPT as INTENT_PROMPT_TPL, _format_history


DEFAULT_QUERY = "Какую печь мне взять в баню, где парилка 12 м3, подскажи лучшие варианты"


def _approx_tokens(text: str) -> int:
    """Rough token estimate for cyrillic-heavy text: ~3.5 chars/token."""
    return len(text) // 4 if text.isascii() else int(len(text) / 3.5)


def _time_cli(prompt: str, model: str, label: str) -> None:
    """Run `claude --print` with the prompt, time it, print result + duration."""
    ensure_fresh_token_sync()
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    args = [
        settings.claude_cli_path, "--print",
        "--output-format", "text",
        "--no-session-persistence",
        "--model", model,
    ]
    print(f"\n=== {label} (model={model}) ===")
    print(f"prompt size: {len(prompt):,} chars  (≈{_approx_tokens(prompt):,} tokens)")
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            args, input=prompt.encode(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=180,
        )
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after 180s")
        return
    elapsed = time.monotonic() - t0
    out = result.stdout.decode(errors="replace").strip()
    err = result.stderr.decode(errors="replace").strip()
    print(f"elapsed: {elapsed:.2f}s  rc={result.returncode}  out_bytes={len(out)}")
    if result.returncode != 0:
        print(f"STDERR: {err[:300]}")
    print(f"answer (first 300 chars):\n  {out[:300]}{'...' if len(out)>300 else ''}")


def build_intent_prompt(query: str) -> str:
    """Replay the same FAQ list + empty history that the bot constructs."""
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    matcher = FaqMatcher(
        embedder=embedder,
        cli_path=settings.claude_cli_path,
        llm_model=settings.claude_reformulation_model,
    )
    faq_entries = matcher._entries

    faq_list = "\n".join(
        f"{i + 1}. {e.question.strip()}" for i, e in enumerate(faq_entries)
    ) or "(нет записей)"

    return INTENT_PROMPT_TPL.format(
        faq_list=faq_list,
        history_block=_format_history(None),
        query=query.strip(),
    )


def build_answer_prompt(query: str, top_k: int = 10) -> str:
    """Run real RAG retrieval and assemble the answer prompt exactly as the bot does."""
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = HybridRetriever(
        embedder=embedder,
        index_version=settings.index_version,
        data_dir="base",
        product_boost=settings.product_boost,
    )
    with SessionLocal() as session:
        chunks = retriever.search(session, query, k=top_k)
    print(f"  retrieved {len(chunks)} chunks; "
          f"chunk text lengths: {[len(c.chunk_text) for c in chunks]}")
    return _build_full_prompt(query, chunks, dealer_block=None, history=None)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", default=DEFAULT_QUERY)
    p.add_argument("--skip-cli", action="store_true",
                   help="just dump prompts to /tmp, don't call the CLI")
    p.add_argument("--top-k", type=int, default=10)
    args = p.parse_args()

    print(f"Query: {args.query!r}")
    print(f"SYSTEM_PROMPT: {len(_SYSTEM_PROMPT)} chars (~{_approx_tokens(_SYSTEM_PROMPT)} tokens)")
    print(f"FAQ_TEXT:      {len(_FAQ_TEXT)} chars (~{_approx_tokens(_FAQ_TEXT)} tokens)")
    print(f"INTENT_PROMPT_TPL: {len(INTENT_PROMPT_TPL)} chars "
          f"(~{_approx_tokens(INTENT_PROMPT_TPL)} tokens)")

    print("\n--- Building intent prompt ---")
    intent_prompt = build_intent_prompt(args.query)
    Path("/tmp/prompt_intent.txt").write_text(intent_prompt, encoding="utf-8")
    print(f"saved → /tmp/prompt_intent.txt  ({len(intent_prompt):,} chars)")

    print("\n--- Building answer prompt (with real RAG) ---")
    answer_prompt = build_answer_prompt(args.query, top_k=args.top_k)
    Path("/tmp/prompt_answer.txt").write_text(answer_prompt, encoding="utf-8")
    print(f"saved → /tmp/prompt_answer.txt  ({len(answer_prompt):,} chars)")

    if args.skip_cli:
        print("\n[--skip-cli] not calling CLI. Use `cat /tmp/prompt_*.txt` to inspect.")
        return 0

    haiku = settings.claude_reformulation_model or "claude-haiku-4-5-20251001"
    sonnet = settings.claude_model or "claude-sonnet-4-6"

    _time_cli(intent_prompt, haiku, "INTENT (Haiku)")
    _time_cli(answer_prompt, sonnet, "ANSWER (Sonnet)")

    print("\n--- Summary ---")
    print("If both elapsed values are close to the production [timing] numbers,")
    print("the bot's wrapper isn't to blame — the prompts themselves are heavy.")
    print("Trim _FAQ_TEXT inclusion, cap chunk_text, shrink history → big wins.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
