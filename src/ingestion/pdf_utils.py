"""Common PDF utilities shared between parsers."""

import hashlib
import re
from pathlib import Path
from typing import Optional

import httpx
from pypdf import PdfReader

from ..core.config import settings


def get_pdf_path(url: str) -> Path:
    """Generate local path for PDF based on URL hash."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    pdf_dir = Path(settings.pdf_storage_path)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir / f"{url_hash}.pdf"


def extract_text_from_pdf(pdf_path: Path) -> Optional[str]:
    """Extract text from PDF file."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        reader = PdfReader(pdf_path)

        if not reader.pages:
            logger.warning(f"PDF has no pages: {pdf_path}")
            return None

        text_parts = []

        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text.strip():
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Error extracting text from page {page_num} of {pdf_path}: {e}")
                continue

        if not text_parts:
            logger.warning(f"No text extracted from PDF: {pdf_path}")
            return None

        # Join all text
        full_text = '\n\n'.join(text_parts)

        # Clean up the text
        full_text = clean_text(full_text)

        logger.debug(f"Extracted {len(full_text)} characters from {pdf_path}")
        return full_text

    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        return None


def clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    if not text:
        return ""

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Restore paragraph breaks (look for patterns like ". " followed by capital letter)
    text = re.sub(r'(\w\.) ([А-ЯA-Z][а-яa-z])', r'\1\n\n\2', text)
    text = re.sub(r'(\w:) ([А-ЯA-Z][а-яa-z])', r'\1\n\n\2', text)

    # Clean up multiple newlines
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text