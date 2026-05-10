"""Documents API router."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select

from src.documents.models import Document, DocumentType
from src.products.models import Product
from admin.dependencies import get_db
from admin.schemas.documents import DocumentList, DocumentListItem, DocumentDetail, DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["Documents"])

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent


@router.get("", response_model=DocumentList)
async def list_documents(
    doc_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List documents with filtering and pagination."""
    query = select(Document).options(selectinload(Document.product))

    # Apply filters
    if doc_type:
        query = query.where(Document.doc_type == doc_type)

    if search:
        query = query.where(
            Document.title.contains(search) | Document.source_url.contains(search)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar()

    # Apply pagination and order by created_at desc
    offset = (page - 1) * per_page
    query = query.order_by(Document.created_at.desc()).offset(offset).limit(per_page)

    documents = db.execute(query).scalars().all()

    items = []
    for doc in documents:
        items.append(DocumentListItem(
            id=doc.id,
            product_id=doc.product_id,
            product_name=doc.product.name if doc.product else None,
            doc_type=doc.doc_type.value,
            source_url=doc.source_url,
            title=doc.title,
            char_count=doc.char_count,
            text_source=doc.text_source,
            fetched_at=doc.fetched_at,
            created_at=doc.created_at,
        ))

    return DocumentList(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document details with text preview."""
    document = db.execute(
        select(Document)
        .options(selectinload(Document.product))
        .where(Document.id == document_id)
    ).scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Truncate full_text to first 2000 characters for preview
    full_text_preview = None
    if document.full_text:
        full_text_preview = document.full_text[:2000]
        if len(document.full_text) > 2000:
            full_text_preview += "..."

    return DocumentDetail(
        id=document.id,
        product_id=document.product_id,
        product_name=document.product.name if document.product else None,
        doc_type=document.doc_type.value,
        source_url=document.source_url,
        title=document.title,
        full_text_preview=full_text_preview,
        char_count=document.char_count,
        fetched_at=document.fetched_at,
        created_at=document.created_at,
    )


@router.get("/{document_id}/text")
async def get_document_text(document_id: int, db: Session = Depends(get_db)):
    """Return full OCR/parsed text of a document."""
    document = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "title": document.title,
        "source_url": document.source_url,
        "doc_type": document.doc_type.value,
        "char_count": document.char_count,
        "has_text": bool(document.full_text),
        "text": document.full_text or "",
    }


@router.delete("/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete document."""
    document = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # If it's a PDF file, try to delete the file from disk
    if document.doc_type == DocumentType.PDF and document.source_url.startswith("file://"):
        file_path = Path(document.source_url.replace("file://", ""))
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass  # Don't fail if file can't be deleted

    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    product_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a PDF document."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Verify product exists if product_id is provided
    if product_id:
        product = db.execute(
            select(Product).where(Product.id == product_id)
        ).scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    # Ensure PDFs directory exists
    pdf_dir = PROJECT_ROOT / "base" / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # Save file to disk
    file_path = pdf_dir / file.filename
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Create document record
    document = Document(
        product_id=product_id,
        doc_type=DocumentType.PDF,
        source_url=f"file://{file_path.absolute()}",
        title=file.filename,
        char_count=None,  # Will be populated when processed
        fetched_at=None,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return DocumentUploadResponse(
        id=document.id,
        filename=file.filename,
        product_id=product_id,
        doc_type=document.doc_type.value,
        source_url=document.source_url,
    )