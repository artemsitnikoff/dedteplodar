"""Pydantic schemas for the web chat endpoint."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """One prior turn of the current thread, supplied by the web client."""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    # Stable per-tab id (localStorage). Maps to a synthetic user_id so the
    # Journal can group a session's turns. See src/logs/queries.synthetic_user_id.
    session_id: str = Field(..., min_length=1, max_length=128)
    # Last few turns (oldest first) the client already holds — used for
    # anaphora resolution. The server does NOT pull history from the DB for
    # web chat; the client owns the thread.
    history: list[ChatTurn] = Field(default_factory=list)


class ChatFeedbackRequest(BaseModel):
    log_id: int
    feedback: Literal["good", "bad"]
    # On 👎: "что не так + что нужно было ответить". Optional.
    note: Optional[str] = Field(default=None, max_length=4000)
