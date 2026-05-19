"""Idempotent migration helpers shared by all model modules.

SQLAlchemy `create_all` never alters existing tables, so each model file
that adds a new column emits an ALTER on import. Bot + admin import the
same models concurrently — both can race on the ALTER. Whichever process
loses the race gets "duplicate column" / "already exists", which we
treat as success.

Each model file also exposes a `_schema_ok` flag (set by its own init
block) so startup code can fail-fast instead of running queries against
a broken schema. Use `assert_schema_ready()` from main_bot.py /
admin/main.py before serving traffic.
"""

from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Each models module registers a probe here at import time. The probe
# returns True if its schema init succeeded, False otherwise. Startup
# code aggregates them via `assert_schema_ready()`.
_schema_probes: list[tuple[str, Callable[[], bool]]] = []


def safe_alter(conn, sql: str) -> None:
    """Execute an ALTER, swallowing 'column already exists' races.

    Re-raises any other error so genuine schema bugs surface.
    """
    try:
        conn.execute(text(sql))
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            return  # another process won the race
        raise


def register_schema_probe(name: str, probe: Callable[[], bool]) -> None:
    """Register a `() -> bool` that reports whether `name`'s schema is OK."""
    _schema_probes.append((name, probe))


def assert_schema_ready(expected: list[str] | None = None) -> None:
    """Raise RuntimeError if any registered model failed to init.

    Call at the start of `main_bot.py` and `admin/main.py` so we fail
    visibly at boot instead of crashing on the first SQL write.

    Pass `expected` to also guard against the silent failure mode where
    `assert_schema_ready()` is called before the model modules have been
    imported — empty probe list would otherwise sail through.
    """
    registered = {name for name, _ in _schema_probes}
    if expected:
        missing = [name for name in expected if name not in registered]
        if missing:
            raise RuntimeError(
                f"Schema probes not registered for: {', '.join(missing)} "
                "— make sure to `import` the model modules before calling "
                "assert_schema_ready()"
            )

    broken = [name for name, probe in _schema_probes if not probe()]
    logger.info(
        "Schema probe check: %d registered (%s), %d broken",
        len(_schema_probes),
        ", ".join(sorted(registered)),
        len(broken),
    )
    if broken:
        raise RuntimeError(
            f"DB schema not ready for modules: {', '.join(broken)} "
            "(check earlier log for the underlying SQLAlchemy error)"
        )
