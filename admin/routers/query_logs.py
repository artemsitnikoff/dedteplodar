"""Query logs API router."""

from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, select, desc

from src.logs.models import QueryLog
from admin.dependencies import get_db
from admin.schemas.query_logs import QueryLogList, QueryLogItem

router = APIRouter(prefix="/journal", tags=["Journal"])


@router.get("", response_model=QueryLogList)
async def list_query_logs(
    query_type: Optional[str] = Query(None),
    feedback: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List query logs with filtering and pagination."""
    q = select(QueryLog)

    if query_type:
        q = q.where(QueryLog.query_type == query_type)
    if feedback == "none":
        q = q.where(QueryLog.feedback.is_(None))
    elif feedback:
        q = q.where(QueryLog.feedback == feedback)
    if search:
        q = q.where(func.lower(QueryLog.question).contains(search.lower()))

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()

    offset = (page - 1) * per_page
    rows = db.execute(
        q.order_by(desc(QueryLog.ts)).offset(offset).limit(per_page)
    ).scalars().all()

    return QueryLogList(
        items=[QueryLogItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{log_id}/context", response_model=List[QueryLogItem])
async def get_dialog_context(
    log_id: int,
    limit: int = Query(3, ge=1, le=10),
    window_minutes: int = Query(30, ge=1, le=240),
    db: Session = Depends(get_db),
):
    """Return up to `limit` previous Q&A turns from the same user_id
    within `window_minutes` before this log entry. Used by the Journal
    detail panel to show what the user asked before this turn.
    """
    target = db.get(QueryLog, log_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Log entry not found")
    if not target.user_id:
        return []

    cutoff = target.ts - timedelta(minutes=window_minutes)
    prev = db.execute(
        select(QueryLog)
        .where(QueryLog.user_id == target.user_id)
        .where(QueryLog.id != target.id)
        .where(QueryLog.ts < target.ts)
        .where(QueryLog.ts >= cutoff)
        .order_by(desc(QueryLog.ts))
        .limit(limit)
    ).scalars().all()

    # Return oldest first so the UI reads top-down like a chat thread
    return [QueryLogItem.model_validate(r) for r in reversed(prev)]
