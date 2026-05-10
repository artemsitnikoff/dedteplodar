"""Query logs API router."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
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
        q = q.where(QueryLog.question.contains(search))

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
