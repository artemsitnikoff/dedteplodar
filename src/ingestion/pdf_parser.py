"""PDF document parser and text extractor."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.config import settings
from ..core.database import get_session
from ..documents.models import Document, DocumentType
from .pdf_utils import get_pdf_path, extract_text_from_pdf, clean_text

logger = logging.getLogger(__name__)


class PDFParser:
    """Parser for PDF documents."""

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


    async def parse_document(self, document_id: int, document_url: str, document_title: str) -> bool:
        """Parse a single PDF document."""
        try:
            # Download PDF
            pdf_path = await self.download_pdf(document_url)
            if not pdf_path:
                return False

            # Extract text
            full_text = extract_text_from_pdf(pdf_path)

            # Update document in database
            for session in get_session():
                db_document = session.get(Document, document_id)
                if db_document:
                    db_document.full_text = full_text
                    db_document.char_count = len(full_text) if full_text else 0
                    db_document.fetched_at = datetime.utcnow()

                session.commit()

            if full_text:
                logger.info(f"Parsed document {document_id} ({document_title}): {len(full_text)} characters")
            else:
                logger.warning(f"No text extracted from document {document_id} ({document_title})")

            return True

        except Exception as e:
            logger.error(f"Error parsing document {document_id} ({document_url}): {e}")
            return False

    async def parse_pdfs(self, limit: Optional[int] = None) -> dict:
        """Parse multiple PDF documents."""
        # Get documents to parse - extract data first
        document_data = []
        for session in get_session():
            query = session.query(Document.id, Document.source_url, Document.title).filter(
                Document.doc_type == DocumentType.PDF,
                Document.full_text.is_(None)
            )

            if limit:
                query = query.limit(limit)

            document_data = [(d.id, d.source_url, d.title or "Untitled") for d in query.all()]

        if not document_data:
            logger.info("No PDF documents to parse")
            return {'total': 0, 'success': 0, 'failed': 0, 'empty': 0}

        logger.info(f"Starting to parse {len(document_data)} PDF documents")

        success_count = 0
        failed_count = 0
        empty_count = 0

        # Process documents sequentially to avoid overwhelming the server
        for document_id, document_url, document_title in document_data:
            try:
                success = await self.parse_document(document_id, document_url, document_title)
                if success:
                    # Check if text was actually extracted
                    for session in get_session():
                        db_doc = session.get(Document, document_id)
                        if db_doc and db_doc.full_text and db_doc.char_count > 0:
                            success_count += 1
                        else:
                            empty_count += 1
                else:
                    failed_count += 1

                # Rate limiting
                await asyncio.sleep(settings.rate_limit_delay)

            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}")
                failed_count += 1

        result = {
            'total': len(document_data),
            'success': success_count,
            'failed': failed_count,
            'empty': empty_count
        }

        logger.info(f"PDF parsing completed: {result}")
        return result