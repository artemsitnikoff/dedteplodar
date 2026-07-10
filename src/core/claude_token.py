"""Claude OAuth token auto-refresh (sync + async).

Tokens stored in data/.claude_token.json — same file as ArkadiyJarvis
when both services share the ./data volume on the server.
Refresh tokens are single-use; writes are atomic to prevent corruption.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TOKEN_FILE = Path("data/.claude_token.json")
# Fallback mirror of the CLI's native credential store, used only by the
# LEGACY refresh-mode path below. NOT needed for a long-lived `claude
# setup-token` token — that authenticates from the CLAUDE_CODE_OAUTH_TOKEN
# env var alone (glafiraeuro proves it; the CLI reads that env var first).
CLI_CREDENTIALS_FILE = Path.home() / ".claude" / "credentials.json"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
REFRESH_BUFFER_MS = 600_000  # refresh 10 min before expiry

# A setup-token OAuth token is long-lived (~1y) but carries no expiry we can
# read from the env. The CLI rejects a credentials.json whose expiresAt is in
# the past ("Not logged in · Please run /login"), so when we mirror we must
# never write a stale stamp: clamp any 0/past value to ~1y ahead and let the
# server enforce the real expiry (a genuine 401 only if the token truly died).
_ONE_YEAR_MS = 365 * 24 * 3600 * 1000


def _safe_expires_at(raw) -> int:
    try:
        exp = int(raw)
    except (TypeError, ValueError):
        exp = 0
    now_ms = int(time.time() * 1000)
    return exp if exp > now_ms + 60_000 else now_ms + _ONE_YEAR_MS


def _static_token() -> str | None:
    """A long-lived env token to use directly (glafiraeuro-style), or None.

    `claude setup-token` yields a long-lived `sk-ant-oat01-…` token that needs
    no refresh — use it straight from the env and IGNORE the shared token file,
    so a neighbour project (ArkadiyJarvis) rotating data/.claude_token.json can
    never lock us out. Any env token with no refresh token is treated as static.
    """
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not tok:
        return None
    if tok.startswith("sk-ant-oat01") or not os.environ.get("CLAUDE_REFRESH_TOKEN", "").strip():
        return tok
    return None

# Sync lock for blocking callers (subprocess path)
_sync_lock = threading.Lock()
# Async lock for async callers
_async_lock: asyncio.Lock | None = None


def _get_async_lock() -> asyncio.Lock:
    global _async_lock
    if _async_lock is None:
        _async_lock = asyncio.Lock()
    return _async_lock


def _load() -> dict:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(TOKEN_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, TOKEN_FILE)
    _sync_cli_credentials(data)


def _sync_cli_credentials(data: dict) -> None:
    """Mirror tokens into ~/.claude/credentials.json — the Claude CLI reads
    auth from here. The CLAUDE_CODE_OAUTH_TOKEN env var alone is not enough
    (CLI reports "Not logged in" / exits 1). Format: nested claudeAiOauth.
    Mirrors ArkadiyJarvis's working pattern (shared data/.claude_token.json).
    """
    if not data.get("access_token"):
        return
    try:
        CLI_CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "claudeAiOauth": {
                "accessToken": data.get("access_token", ""),
                "refreshToken": data.get("refresh_token", ""),
                "expiresAt": _safe_expires_at(data.get("expires_at", 0)),
                "scopes": ["user:inference", "user:profile"],
            },
        }
        tmp = CLI_CREDENTIALS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, CLI_CREDENTIALS_FILE)
    except Exception as e:
        logger.warning("Could not write %s: %s", CLI_CREDENTIALS_FILE, e)


def init_token_file() -> None:
    """Seed token file from env vars on first start (if not already present)."""
    if TOKEN_FILE.exists():
        data = _load()
        if data.get("refresh_token"):
            logger.info("Claude token file exists with refresh token")
            return

    access_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    refresh_token = os.environ.get("CLAUDE_REFRESH_TOKEN", "")

    if not refresh_token:
        if access_token:
            logger.warning("CLAUDE_CODE_OAUTH_TOKEN set but no CLAUDE_REFRESH_TOKEN — token will not auto-refresh")
        return

    _save({"access_token": access_token, "refresh_token": refresh_token, "expires_at": 0})
    logger.info("Claude token file initialized from env vars")


def _do_refresh(data: dict) -> dict | None:
    """Perform HTTP refresh, return new token data or None on failure."""
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        logger.debug("No refresh token available")
        return None

    logger.info("Refreshing Claude OAuth token...")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLAUDE_OAUTH_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            result = resp.json()

        now_ms = time.time() * 1000
        expires_in = result.get("expires_in", 28800)
        new_data = {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "expires_at": now_ms + expires_in * 1000,
        }
        _save(new_data)
        logger.info("Claude token refreshed, expires in %d hours", expires_in // 3600)
        return new_data
    except Exception as e:
        logger.error("Failed to refresh Claude token: %s", e)
        return None


def ensure_fresh_token_sync() -> None:
    """Make sure the Claude CLI can authenticate. Thread-safe, blocking.

    STATIC mode (recommended): a long-lived CLAUDE_CODE_OAUTH_TOKEN from
    `claude setup-token`, no refresh token. Used straight from the env like
    glafiraeuro — the shared token file is never touched, so a neighbour
    project rotating it can't lock us out.

    LEGACY mode: consume the access token ArkadiyJarvis last wrote to the
    shared file. teplodar never refreshes it (single-use tokens race Jarvis).
    """
    tok = _static_token()
    if tok:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = tok  # re-assert for the subprocess env
        _sync_cli_credentials({"access_token": tok})  # mirror w/ safe future expiry
        return

    with _sync_lock:
        data = _load()
        access = data.get("access_token")
        if access:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = access
            _sync_cli_credentials(data)
        else:
            logger.error(
                "No CLAUDE_CODE_OAUTH_TOKEN and no access_token in %s — "
                "set a long-lived token from `claude setup-token`", TOKEN_FILE,
            )


async def ensure_fresh_token() -> None:
    """Async variant — see ensure_fresh_token_sync."""
    tok = _static_token()
    if tok:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = tok
        _sync_cli_credentials({"access_token": tok})
        return

    async with _get_async_lock():
        data = _load()
        access = data.get("access_token")
        if access:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = access
            _sync_cli_credentials(data)
        else:
            logger.error(
                "No CLAUDE_CODE_OAUTH_TOKEN and no access_token in %s — "
                "set a long-lived token from `claude setup-token`", TOKEN_FILE,
            )
