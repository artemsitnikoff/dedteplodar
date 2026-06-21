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
# Claude CLI reads auth from here on direct invocation. Setting only the
# CLAUDE_CODE_OAUTH_TOKEN env var is NOT enough — the CLI reports
# "Not logged in" and exits 1. Mirror the token into this native store.
CLI_CREDENTIALS_FILE = Path.home() / ".claude" / "credentials.json"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
REFRESH_BUFFER_MS = 600_000  # refresh 10 min before expiry

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
                "expiresAt": int(data.get("expires_at", 0)),
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
    """Refresh token if needed. Thread-safe, blocking. Use in sync/subprocess context."""
    with _sync_lock:
        data = _load()
        now_ms = time.time() * 1000

        if data.get("expires_at", 0) > now_ms + REFRESH_BUFFER_MS:
            if data.get("access_token"):
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
                # Usual path here: the token was refreshed by another service
                # sharing data/.claude_token.json, so _do_refresh/_save isn't
                # hit — sync the CLI credential store ourselves.
                _sync_cli_credentials(data)
            return

        new_data = _do_refresh(data)  # _save() inside also syncs CLI creds
        if new_data:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = new_data["access_token"]
        elif data.get("access_token"):
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
            _sync_cli_credentials(data)


async def ensure_fresh_token() -> None:
    """Async variant — use from async context."""
    async with _get_async_lock():
        data = _load()
        now_ms = time.time() * 1000

        if data.get("expires_at", 0) > now_ms + REFRESH_BUFFER_MS:
            if data.get("access_token"):
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
                _sync_cli_credentials(data)
            return

        new_data = await asyncio.to_thread(_do_refresh, data)  # _save() syncs CLI creds
        if new_data:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = new_data["access_token"]
        elif data.get("access_token"):
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
            _sync_cli_credentials(data)
