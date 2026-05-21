"""Stream-test: hit `claude --output-format stream-json` and show event timing.

Usage (inside the bot container):
    docker compose exec bot python scripts/stream_test.py
    docker compose exec bot python scripts/stream_test.py --query "..."

What we want to learn:
  * Does `claude --print --output-format stream-json --verbose` emit text
    progressively (multiple assistant events with growing content) or
    just one final event at the end?
  * Are subsequent assistant events ADDITIVE (each contains new tokens
    only) or CUMULATIVE (each contains the full text so far)?
  * What's the TTFT (time-to-first-text) vs total wall time?

Both answers drive the streaming parser design — or push us to API mode.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.core.claude_token import ensure_fresh_token_sync


DEFAULT_QUERY = "Напиши рассказ из 200 слов о русской бане, со вступлением, кульминацией и выводом"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", default=DEFAULT_QUERY)
    p.add_argument("--model", default=settings.claude_model or "claude-sonnet-4-6")
    args = p.parse_args()

    ensure_fresh_token_sync()
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    cli_args = [
        settings.claude_cli_path, "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--model", args.model,
    ]
    print(f"# query: {args.query!r}")
    print(f"# model: {args.model}")
    print(f"# args:  {' '.join(cli_args)}")
    print()

    t0 = time.monotonic()
    proc = subprocess.Popen(
        cli_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
    )
    proc.stdin.write(args.query.encode())
    proc.stdin.close()

    last_text_len = 0  # for additive vs cumulative detection
    event_idx = 0
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        dt = time.monotonic() - t0
        event_idx += 1
        try:
            ev = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            print(f"[{dt:6.2f}s] #{event_idx:02d} raw: {line[:200]!r}")
            continue
        etype = ev.get("type", "?")
        if etype == "assistant":
            msg = ev.get("message", {})
            content = msg.get("content", [])
            for c in content:
                if c.get("type") == "text":
                    text = c.get("text", "") or ""
                    is_cumulative = text.startswith("") and last_text_len > 0 and len(text) > last_text_len
                    cum_marker = (
                        " [CUMULATIVE]" if len(text) >= last_text_len and last_text_len > 0
                        else " [ADDITIVE?]" if last_text_len > 0
                        else ""
                    )
                    print(f"[{dt:6.2f}s] #{event_idx:02d} assistant text "
                          f"len={len(text):5d}{cum_marker}")
                    print(f"          first 80 ch: {text[:80]!r}")
                    print(f"          last  80 ch: {text[-80:]!r}")
                    last_text_len = len(text)
        elif etype == "result":
            print(f"[{dt:6.2f}s] #{event_idx:02d} RESULT "
                  f"duration_ms={ev.get('duration_ms')} "
                  f"duration_api_ms={ev.get('duration_api_ms')} "
                  f"is_error={ev.get('is_error')}")
        else:
            short = json.dumps(ev, ensure_ascii=False)[:120]
            print(f"[{dt:6.2f}s] #{event_idx:02d} {etype}: {short}")

    rc = proc.wait()
    total = time.monotonic() - t0
    print()
    print(f"# total wall: {total:.2f}s  rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
