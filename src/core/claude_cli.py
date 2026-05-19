"""Cross-process Claude CLI concurrency limiter.

Bot, admin (eval workers) and any script may all call `claude --print`
subprocesses against the same Pro OAuth account. Each process has its own
asyncio.Semaphore at best — nothing coordinates across processes. Under a
traffic spike the total concurrent CLI count fans out and the Pro account
starts 429-ing.

Solution: a slot pool implemented as N lock files. Each CLI call wraps
its `subprocess.run` in `with claude_cli_slot():`, which polls all N
slots with `fcntl.flock(LOCK_EX | LOCK_NB)` until one succeeds. We
intentionally avoid blocking `LOCK_EX` on a single slot — that would
serialise all waiters FIFO on `slot_0` while `slot_1..N-1` could be
idle (and a stuck holder would block the whole bot indefinitely).

The OS releases the flock automatically when the holding fd is closed
(or the process dies), so crashed processes never leak slots.

Slots live in `settings.claude_cli_slots_dir` (default `/tmp/...` —
host-local on purpose so multi-host deployments don't accidentally
serialise through a shared NFS file).

If the slots directory cannot be created (read-only FS, perms), we
log loudly and yield without rate-limiting rather than crash the
calling code — the Claude CLI itself will still error out on 429,
which is preferable to taking the whole bot down.
"""

from __future__ import annotations

import fcntl
import logging
import time
from contextlib import contextmanager
from typing import Iterator

from src.core.config import settings

logger = logging.getLogger(__name__)

# How long to back off between full passes over the slot pool.
# 100 ms keeps wake-up jitter low for a typical 1–5 s Claude call while
# capping syscall overhead at ~10 passes/sec/waiter under contention.
_POLL_INTERVAL_SEC = 0.1


@contextmanager
def claude_cli_slot() -> Iterator[None]:
    """Acquire one of N global Claude CLI slots, then yield it.

    Polls all N slots non-blockingly each iteration so a free slot is
    picked up immediately instead of waiting FIFO on slot_0. Pure stdlib
    (`fcntl.flock`), no extra deps. POSIX-only (Linux + macOS).

    Slot is released on context-manager exit OR process death.
    """
    slots_dir = settings.claude_cli_slots_dir
    cap = max(1, settings.claude_cli_max_concurrent)

    try:
        slots_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Read-only /tmp, perms mismatch, etc. — degrade gracefully:
        # let the call through unbounded. Claude CLI will surface 429s
        # at the API layer; taking the bot down for a /tmp issue is worse.
        logger.error("Claude CLI slot dir %s unavailable (%s) — running uncapped", slots_dir, e)
        yield
        return

    waited_first = False
    while True:
        any_opened = False
        for i in range(cap):
            slot_path = slots_dir / f"slot_{i}"
            try:
                # "a" — append-mode keeps file content (an empty placeholder),
                # avoids the truncating write that "w" emits on every call.
                f = open(slot_path, "a")
            except OSError as e:
                logger.warning("Cannot open slot file %s (%s) — skipping", slot_path, e)
                continue
            any_opened = True
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            # Got it.
            try:
                yield
            finally:
                f.close()  # closing the fd releases the flock
            return

        # If we couldn't even OPEN a single slot file (perms flipped, FDs
        # exhausted, FS went read-only mid-flight), don't spin forever —
        # log once and degrade to uncapped. Better to risk a Claude 429
        # than to hang every CLI call indefinitely.
        if not any_opened:
            logger.error(
                "Claude CLI: cannot open any slot file in %s — running uncapped",
                slots_dir,
            )
            yield
            return

        if not waited_first:
            logger.info("Claude CLI: all %d slots busy, polling…", cap)
            waited_first = True
        time.sleep(_POLL_INTERVAL_SEC)
