"""Pipeline API router for background tasks and statistics."""

import uuid
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any
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


@router.get("/stats", response_model=PipelineStats)
async def get_pipeline_stats(db: Session = Depends(get_db)):
    """Get database statistics."""
    # Count entities
    products_count = db.execute(select(func.count(Product.id))).scalar()
    categories_count = db.execute(select(func.count(Category.id))).scalar()
    documents_count = db.execute(select(func.count(Document.id))).scalar()
    chunks_count = db.execute(select(func.count(Chunk.id))).scalar()

    # Get unique index versions
    index_versions_result = db.execute(
        select(distinct(Chunk.index_version)).where(Chunk.index_version.is_not(None))
    ).scalars().all()
    index_versions = list(index_versions_result)

    # Get last indexed date (latest chunk created_at)
    last_chunk = db.execute(
        select(Chunk.created_at).order_by(Chunk.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    last_indexed = last_chunk.isoformat() if last_chunk else None

    return PipelineStats(
        products=products_count,
        categories=categories_count,
        documents=documents_count,
        chunks=chunks_count,
        index_versions=index_versions,
        last_indexed=last_indexed,
    )


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