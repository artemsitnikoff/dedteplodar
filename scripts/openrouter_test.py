"""OpenRouter streaming smoke-test.

Goal: confirm we get token-by-token SSE streaming for Anthropic-Sonnet
through OpenRouter, measure TTFB (time-to-first-byte/token), and price
out a typical RAG answer prompt.

Usage:
    # 1) Drop OPENROUTER_API_KEY into .env (or export it)
    # 2) Inside the bot container:
    docker compose exec -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY bot \
        python scripts/openrouter_test.py

    # Custom query / model:
    docker compose exec ... bot python scripts/openrouter_test.py \
        --query "своя строка" \
        --model "anthropic/claude-sonnet-4.5"

What's measured:
  * time to first delta (TTFT) — what the user perceives as "speed"
  * per-token cadence — confirms it's actually streaming, not chunked
  * total wall time
  * usage tokens (prompt + completion) for cost projection
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# We use the OpenAI Python SDK pointed at OpenRouter — same wire format,
# simpler than rolling our own SSE parser.
try:
    from openai import OpenAI
except ImportError:
    print("openai SDK not installed. Inside container:")
    print("  pip install openai")
    sys.exit(1)


DEFAULT_QUERY = "Напиши рассказ из 200 слов о русской бане, со вступлением, кульминацией и выводом"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", default=DEFAULT_QUERY)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-tokens", type=int, default=512)
    args = p.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set. Add it to .env or export it.")
        return 1

    print(f"# query: {args.query!r}")
    print(f"# model: {args.model}")
    print(f"# max_tokens: {args.max_tokens}")
    print()

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    t0 = time.monotonic()
    stream = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "user", "content": args.query}],
        max_tokens=args.max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        extra_headers={
            # Optional — appears on the OpenRouter dashboard so you can
            # tell traffic apart from other apps using the same key.
            "HTTP-Referer": "https://teplodar-bot-perf-test",
            "X-Title": "Teplodar Stream Test",
        },
    )

    first_delta_at: float | None = None
    last_delta_at: float | None = None
    deltas_count = 0
    total_chars = 0
    usage = None

    print("--- streaming deltas ---")
    for chunk in stream:
        now = time.monotonic() - t0
        # Usage chunks come at the end with empty choices in OpenAI format.
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            if first_delta_at is None:
                first_delta_at = now
                print(f"[{now:6.3f}s] TTFT (first token): {delta.content!r}")
            deltas_count += 1
            total_chars += len(delta.content)
            last_delta_at = now
            # Print every 10th delta to avoid flooding
            if deltas_count % 10 == 0:
                print(f"[{now:6.3f}s] delta #{deltas_count:3d} "
                      f"({len(delta.content):2d}ch, total={total_chars}ch): {delta.content!r}")

    total = time.monotonic() - t0
    print()
    print("--- summary ---")
    print(f"  total wall:    {total:.2f}s")
    print(f"  TTFT:          {first_delta_at:.2f}s" if first_delta_at else "  TTFT:  no deltas")
    if last_delta_at and first_delta_at:
        gen_time = last_delta_at - first_delta_at
        tok_per_s = total_chars / gen_time / 4 if gen_time > 0 else 0
        print(f"  generation:    {gen_time:.2f}s")
        print(f"  output chars:  {total_chars}")
        print(f"  deltas:        {deltas_count}")
        print(f"  ~tok/s:        {tok_per_s:.0f}")
    if usage:
        pt = usage.prompt_tokens
        ct = usage.completion_tokens
        print(f"  usage: prompt={pt} completion={ct} total={pt + ct}")
        # Sonnet 4.5 rough pricing on OpenRouter (always check dashboard for current)
        cost_in = pt / 1_000_000 * 3.0
        cost_out = ct / 1_000_000 * 15.0
        print(f"  est cost (sonnet 4.5): ${cost_in + cost_out:.5f} "
              f"(in ${cost_in:.5f} + out ${cost_out:.5f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
