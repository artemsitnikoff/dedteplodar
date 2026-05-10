"""OCR parser for PDF documents with image content."""

import asyncio
import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import ocrmypdf
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.config import settings
from ..core.database import get_session
from ..documents.models import Document, DocumentType
from .pdf_utils import get_pdf_path, extract_text_from_pdf

logger = logging.getLogger(__name__)


class OCRParser:
    """OCR parser for PDF documents with image content."""

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            headers={'User-Agent': settings.user_agent},
            follow_redirects=True
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.HTTPStatusError,
        )),
        reraise=True,
    )
    async def _fetch_pdf_bytes(self, url: str) -> tuple[bytes, str]:
        """Fetch PDF bytes with retries on transient network errors."""
        if not self.client:
            raise RuntimeError("Parser not initialized")
        response = await self.client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get('content-type', '').lower()

    async def download_pdf(self, url: str) -> Optional[Path]:
        """Download PDF file if not already cached."""
        pdf_path = get_pdf_path(url)

        # Check if already downloaded
        if pdf_path.exists():
            logger.debug(f"PDF already cached: {pdf_path}")
            return pdf_path

        try:
            logger.debug(f"Downloading PDF: {url}")
            content, content_type = await self._fetch_pdf_bytes(url)

            # Check if response is actually PDF
            if 'application/pdf' not in content_type:
                logger.warning(f"URL {url} does not return PDF content (got {content_type})")
                return None

            # Save PDF
            with open(pdf_path, 'wb') as f:
                f.write(content)

            logger.info(f"Downloaded PDF: {pdf_path} ({len(content)} bytes)")
            return pdf_path

        except Exception as e:
            logger.error(f"Error downloading PDF {url} after retries: {e}")
            return None

    async def perform_ocr(self, input_pdf: Path) -> Optional[Path]:
        """Perform OCR on PDF and return path to OCR'd version."""
        # Create temp OCR output file
        url_hash = input_pdf.stem  # Remove .pdf extension
        ocr_path = input_pdf.parent / f"{url_hash}_ocr.pdf"

        try:
            logger.debug(f"Starting OCR on {input_pdf}")

            # Run OCR in thread to avoid blocking async loop
            await asyncio.to_thread(
                ocrmypdf.ocr,
                str(input_pdf),
                str(ocr_path),
                language=['rus', 'eng'],
                deskew=True,
                force_ocr=True,
                skip_text=False,
                progress_bar=False,
            )

            logger.info(f"OCR completed: {ocr_path}")
            return ocr_path

        except ocrmypdf.PriorOcrFoundError:
            logger.info(f"PDF {input_pdf} already contains OCR text")
            return input_pdf  # Return original if already has OCR
        except ocrmypdf.EncryptedPdfError:
            logger.error(f"PDF {input_pdf} is encrypted, cannot perform OCR")
            return None
        except ocrmypdf.UnsupportedImageFormatError:
            logger.error(f"PDF {input_pdf} contains unsupported image formats")
            return None
        except Exception as e:
            logger.error(f"OCR failed for {input_pdf}: {e}")
            return None

    async def process_document(self, document_id: int, document_url: str, document_title: str) -> bool:
        """Process a single document with OCR."""
        try:
            # Get or download PDF
            pdf_path = get_pdf_path(document_url)
            if not pdf_path.exists():
                pdf_path = await self.download_pdf(document_url)
                if not pdf_path:
                    logger.error(f"Failed to download PDF for document {document_id}")
                    return False

            # Perform OCR
            ocr_pdf_path = await self.perform_ocr(pdf_path)
            if not ocr_pdf_path:
                logger.error(f"OCR failed for document {document_id}")
                return False

            # Extract text from OCR'd PDF
            full_text = extract_text_from_pdf(ocr_pdf_path)

            # Update document in database
            for session in get_session():
                db_document = session.get(Document, document_id)
                if db_document:
                    db_document.full_text = full_text
                    db_document.char_count = len(full_text) if full_text else 0
                    db_document.fetched_at = datetime.utcnow()

                session.commit()

            if full_text:
                logger.info(f"OCR processed document {document_id} ({document_title}): {len(full_text)} characters")
            else:
                logger.warning(f"No text extracted from OCR'd document {document_id} ({document_title})")

            # Clean up temporary OCR file if different from original
            if ocr_pdf_path != pdf_path and ocr_pdf_path.exists():
                try:
                    ocr_pdf_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to clean up temp OCR file {ocr_pdf_path}: {e}")

            return True

        except Exception as e:
            logger.error(f"Error processing document {document_id} ({document_url}): {e}")
            return False

    async def process_empty_pdfs(
        self,
        all_empty: bool = False,
        limit: Optional[int] = None
    ) -> dict:
        """Process empty PDF documents with OCR."""

        # Build query for empty documents
        for session in get_session():
            query = session.query(Document.id, Document.source_url, Document.title).filter(
                Document.doc_type == DocumentType.PDF,
                Document.char_count == 0
            )

            if not all_empty:
                # Filter for likely useful documents (manuals, instructions, etc.)
                title_filters = [
                    Document.title.like('%уководство%'),
                    Document.title.like('%нструкция%'),
                    Document.title.like('РЭ%'),
                    Document.title.like('%аспорт%'),
                    Document.title.like('%хема%'),
                ]
                from sqlalchemy import or_
                query = query.filter(or_(*title_filters))

            if limit:
                query = query.limit(limit)

            document_data = [(d.id, d.source_url, d.title or "Untitled") for d in query.all()]

        if not document_data:
            logger.info("No empty PDF documents found for OCR processing")
            return {'total': 0, 'success': 0, 'failed': 0, 'chars_extracted': 0}

        logger.info(f"Starting OCR processing of {len(document_data)} empty PDF documents")

        success_count = 0
        failed_count = 0
        total_chars = 0

        # Process documents sequentially to avoid overwhelming resources
        for document_id, document_url, document_title in document_data:
            try:
                success = await self.process_document(document_id, document_url, document_title)
                if success:
                    success_count += 1
                    # Get character count
                    for session in get_session():
                        db_doc = session.get(Document, document_id)
                        if db_doc and db_doc.char_count:
                            total_chars += db_doc.char_count
                else:
                    failed_count += 1

                # Rate limiting - OCR is resource intensive
                await asyncio.sleep(2.0)

            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}")
                failed_count += 1

        result = {
            'total': len(document_data),
            'success': success_count,
            'failed': failed_count,
            'chars_extracted': total_chars,
            'avg_chars': total_chars // success_count if success_count > 0 else 0
        }

        logger.info(f"OCR processing completed: {result}")
        return result