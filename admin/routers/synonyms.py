"""Admin CRUD for the synonym dictionary."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from admin.dependencies import get_db
from admin.schemas.synonyms import (
    SynonymCreate, SynonymList, SynonymOut, SynonymUpdate,
)
from src.synonyms.models import Synonym

router = APIRouter(prefix="/synonyms", tags=["Synonyms"])


@router.get("", response_model=SynonymList)
async def list_synonyms(
    category: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = select(Synonym)
    if category:
        q = q.where(Synonym.category == category)
    if active is not None:
        q = q.where(Synonym.active.is_(active))
    if search:
        s = search.lower()
        q = q.where(
            func.lower(Synonym.term).contains(s)
            | func.lower(Synonym.canonical).contains(s)
        )

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(Synonym.category, Synonym.term)).scalars().all()
    return SynonymList(items=[SynonymOut.model_validate(r) for r in rows], total=total)


@router.post("", response_model=SynonymOut, status_code=201)
async def create_synonym(payload: SynonymCreate, db: Session = Depends(get_db)):
    row = Synonym(
        term=payload.term.strip(),
        canonical=payload.canonical.strip(),
        category=payload.category,
        note=payload.note,
        active=payload.active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SynonymOut.model_validate(row)


@router.put("/{syn_id}", response_model=SynonymOut)
async def update_synonym(syn_id: int, payload: SynonymUpdate, db: Session = Depends(get_db)):
    row = db.get(Synonym, syn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Synonym not found")
    data = payload.model_dump(exclude_unset=True)
    for key, val in data.items():
        if isinstance(val, str):
            val = val.strip()
        setattr(row, key, val)
    db.commit()
    db.refresh(row)
    return SynonymOut.model_validate(row)


@router.delete("/{syn_id}", status_code=204)
async def delete_synonym(syn_id: int, db: Session = Depends(get_db)):
    row = db.get(Synonym, syn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Synonym not found")
    db.delete(row)
    db.commit()


@router.post("/reload", status_code=204)
async def force_reload():
    """Reload synonym cache.

    NOTE: this only reloads the admin process's own SynonymStore singleton.
    The bot runs in a separate process and polls the DB every 10 seconds —
    new/edited synonyms reach Telegram users within ≤10s automatically,
    regardless of this endpoint. Kept for symmetry / future use (e.g. if
    we add an admin-side feature that also reads synonyms).
    """
    from src.synonyms.store import get_synonym_store
    get_synonym_store().reload()
