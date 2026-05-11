"""Pipeline API router for background tasks and statistics."""

import time
import uuid
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, select, distinct

from src.products.models import Product, Category
from src.documents.models import Document
from src.rag.models import Chunk
from admin.dependencies import get_db
from admin.schemas.pipeline import PipelineStats, TaskStatus, TaskStartResponse

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# In-memory storage for background tasks
_tasks: Dict[str, Dict[str, Any]] = {}

# Simple time-based cache for stats
_stats_cache: Optional[Dict[str, Any]] = None
_stats_cache_timestamp: float = 0
_STATS_CACHE_TTL = 20  # seconds


def _get_stats_cached(db: Session) -> PipelineStats:
    """Get pipeline stats with TTL cache."""
    global _stats_cache, _stats_cache_timestamp

    now = time.time()
    if _stats_cache and (now - _stats_cache_timestamp) < _STATS_CACHE_TTL:
        return PipelineStats(**_stats_cache)

    # Cache miss - compute fresh stats
    products_count = db.execute(select(func.count(Product.id))).scalar()
    categories_count = db.execute(select(func.count(Category.id))).scalar()
    documents_count = db.execute(select(func.count(Document.id))).scalar()
    chunks_count = db.execute(select(func.count(Chunk.id))).scalar()

    # Get unique index versions
    index_versions_result = db.execute(
        select(distinct(Chunk.index_version)).where(Chunk.index_version.is_not(None))
    ).scalars().all()
    index_versions = list(index_versions_result)

    # Use MAX(id) instead of MAX(created_at) for better performance
    # (assumes id is auto-incrementing and correlates with time)
    last_chunk_id = db.execute(
        select(func.max(Chunk.id))
    ).scalar()

    # If we have chunks, get the created_at of the latest chunk by id
    last_indexed = None
    if last_chunk_id:
        last_chunk = db.execute(
            select(Chunk.created_at).where(Chunk.id == last_chunk_id)
        ).scalar_one_or_none()
        last_indexed = last_chunk.isoformat() if last_chunk else None

    # Cache the result
    _stats_cache = {
        "products": products_count,
        "categories": categories_count,
        "documents": documents_count,
        "chunks": chunks_count,
        "index_versions": index_versions,
        "last_indexed": last_indexed,
    }
    _stats_cache_timestamp = now

    return PipelineStats(**_stats_cache)


def _cleanup_old_tasks():
    """Remove tasks older than 1 hour."""
    global _tasks
    now = time.time()
    cutoff = now - 3600  # 1 hour ago

    to_remove = []
    for task_id, task_info in _tasks.items():
        # Check if task is old (we'll use a simple heuristic based on process state)
        process = task_info.get("process")
        if process and process.poll() is not None:  # Process finished
            # If we can't determine age precisely, remove finished tasks after some time
            # This is a simple cleanup - in production you might want to store timestamps
            to_remove.append(task_id)

    # Remove old finished tasks (keep recent for status queries)
    if len(to_remove) > 10:  # Keep some recent ones
        for task_id in to_remove[:-5]:  # Remove all but last 5
            del _tasks[task_id]


@router.get("/stats", response_model=PipelineStats)
async def get_pipeline_stats(db: Session = Depends(get_db)):
    """Get database statistics (cached)."""
    return _get_stats_cached(db)


@router.post("/import-yml", response_model=TaskStartResponse)
async def import_yml(file: UploadFile = File(...)):
    """Upload YML file and start import process."""
    if not file.filename.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail="Only XML/YML files are allowed")

    # Save uploaded file
    upload_path = PROJECT_ROOT / "base" / "upload_latest.xml"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    with open(upload_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Generate task ID
    task_id = str(uuid.uuid4())

    # Start background process
    try:
        script_path = PROJECT_ROOT / "scripts" / "ingest_yml.py"
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Store task info
        _tasks[task_id] = {
            "process": process,
            "status": "running",
            "script": "ingest_yml.py",
            "returncode": None,
            "stderr": None,
        }

        return TaskStartResponse(task_id=task_id, status="started")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start import: {str(e)}")


@router.post("/rebuild-index", response_model=TaskStartResponse)
async def rebuild_index():
    """Start index rebuild process."""
    # Generate task ID
    task_id = str(uuid.uuid4())

    try:
        script_path = PROJECT_ROOT / "scripts" / "build_index.py"
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Store task info
        _tasks[task_id] = {
            "process": process,
            "status": "running",
            "script": "build_index.py",
            "returncode": None,
            "stderr": None,
        }

        return TaskStartResponse(task_id=task_id, status="started")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start rebuild: {str(e)}")


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get background task status."""
    # Cleanup old tasks periodically
    _cleanup_old_tasks()

    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = _tasks[task_id]
    process = task_info["process"]

    # Check if process is still running
    if process.poll() is None:
        # Still running
        return TaskStatus(
            task_id=task_id,
            status="running",
            returncode=None,
            stderr=None,
        )
    else:
        # Process finished
        returncode = process.returncode
        _, stderr = process.communicate()

        # Update task info
        task_info["status"] = "done" if returncode == 0 else "failed"
        task_info["returncode"] = returncode
        task_info["stderr"] = stderr[-1000:] if stderr else None  # Last 1000 chars

        return TaskStatus(
            task_id=task_id,
            status=task_info["status"],
            returncode=returncode,
            stderr=task_info["stderr"],
        )