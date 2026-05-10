"""FAQ entries CRUD router."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from src.faq.models import FaqEntry
from admin.dependencies import get_db
from admin.schemas.faq_entries import FaqEntryCreate, FaqEntryUpdate, FaqEntryItem, FaqEntryList

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/faq-entries", tags=["FAQ Entries"])

# Lazy embedder — initialised on first use so the admin server starts fast
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from src.core.config import settings
            from src.rag.embedder import E5Embedder
            _embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
            logger.info("FAQ embedder initialised")
        except Exception as e:
            logger.warning("Could not init FAQ embedder: %s", e)
    return _embedder


def _compute_embedding(text: str) -> Optional[str]:
    emb = _get_embedder()
    if emb is None:
        return None
    try:
        vec = emb.embed_queries([text])[0]
        return json.dumps(vec.tolist())
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return None


@router.get("", response_model=FaqEntryList)
async def list_faq_entries(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = select(FaqEntry)
    if active_only:
        q = q.where(FaqEntry.active.is_(True))
    q = q.order_by(FaqEntry.created_at.desc())
    rows = db.execute(q).scalars().all()
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    return FaqEntryList(items=[FaqEntryItem.model_validate(r) for r in rows], total=total)


@router.post("", response_model=FaqEntryItem, status_code=201)
async def create_faq_entry(data: FaqEntryCreate, db: Session = Depends(get_db)):
    embedding = _compute_embedding(data.question)
    entry = FaqEntry(
        question=data.question,
        answer=data.answer,
        embedding=embedding,
        active=True,
        source_log_id=data.source_log_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return FaqEntryItem.model_validate(entry)


@router.patch("/{entry_id}", response_model=FaqEntryItem)
async def update_faq_entry(entry_id: int, data: FaqEntryUpdate, db: Session = Depends(get_db)):
    entry = db.get(FaqEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="FAQ entry not found")

    update = data.model_dump(exclude_unset=True)
    # Recompute embedding if question changed
    if "question" in update:
        update["embedding"] = _compute_embedding(update["question"])

    for k, v in update.items():
        setattr(entry, k, v)

    db.commit()
    db.refresh(entry)
    return FaqEntryItem.model_validate(entry)


@router.delete("/{entry_id}")
async def delete_faq_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FaqEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="FAQ entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "Deleted"}
