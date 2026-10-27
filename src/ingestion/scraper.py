"""Web scraper for product pages."""

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
# selectolax ≥1.0 dropped the Modest backend; lexbor has the same API.
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..core.database import get_session
from ..products.models import Product
from ..documents.models import Document, DocumentType

logger = logging.getLogger(__name__)


def _node_text(node) -> str:
    """Visible text of a node with block boundaries kept apart. `text(strip=True)`
    glued neighbouring blocks together («ОписаниеО серии…»)."""
    text = node.text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _is_general_catalogue(pdf_url: str, link_text: str) -> bool:
    """True for the site-wide product catalogue PDF (not a product document)."""
    from urllib.parse import unquote
    text = (link_text or "").lower()
    path = unquote(pdf_url).lower()
    return "каталог" in text and "скачать" in text or ("/doc/" in path and "каталог" in path)


class ProductScraper:
    """Scraper for Teplodar product pages."""

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            headers={'User-Agent': settings.user_agent},
            follow_redirects=True
        )
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def fetch_page(self, url: str) -> str:
        """Fetch HTML page with retry logic."""
        if not self.client or not self.semaphore:
            raise RuntimeError("Scraper not initialized")

        async with self.semaphore:
            try:
                logger.debug(f"Fetching: {url}")
                response = await self.client.get(url)
                response.raise_for_status()

                # Rate limiting
                await asyncio.sleep(settings.rate_limit_delay)

                return response.text

            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error {e.response.status_code} for {url}")
                raise
            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                raise

    def extract_product_data(self, html: str, url: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
        """Extract full description and PDF links from product page HTML."""
        parser = HTMLParser(html)

        # Scripts carry the page's schema.org JSON-LD (warranty, return policy,
        # equipment lists…) — ~7k chars of JSON that otherwise ends up inside
        # the product's chunk text. Drop them (and styles) before reading text.
        for node in parser.css('script, style, noscript'):
            node.decompose()

        # Extract full description
        full_description = None

        # Try different selectors for product description
        description_selectors = [
            '.product-detail-text',
            '.detail-text',
            '.product-description',
            '.tab-content',
            '.description',
            '[id*="description"]',
            '.product-info .text'
        ]

        for selector in description_selectors:
            desc_elem = parser.css_first(selector)
            if desc_elem:
                full_description = _node_text(desc_elem)
                if full_description and len(full_description) > 50:  # Meaningful content
                    break

        # If no specific description found, try to get text from main content area
        if not full_description:
            content_area = parser.css_first('.content, .main-content, .product-info')
            if content_area:
                text_blocks = []
                for p in content_area.css('p, div.text, .description'):
                    text = _node_text(p)
                    if text and len(text) > 20:
                        text_blocks.append(text)
                full_description = ' '.join(text_blocks) if text_blocks else None

        # Extract PDF links
        pdf_links = []
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        # Look for PDF links in documentation sections
        doc_sections = parser.css('.documentation, .documents, .files, .downloads, .instructions')
        if not doc_sections:
            # Fallback to entire page
            doc_sections = [parser.root] if parser.root else []

        for section in doc_sections:
            links = section.css('a[href*=".pdf"], a[href*="/upload/"], a[href*="instruction"]')

            for link in links:
                href = link.attributes.get('href', '').strip()
                if not href:
                    continue

                # Make absolute URL
                if href.startswith('/'):
                    pdf_url = urljoin(base_url, href)
                elif href.startswith('http'):
                    pdf_url = href
                else:
                    pdf_url = urljoin(url, href)

                # Check if it's likely a PDF
                if '.pdf' in pdf_url.lower() or 'instruction' in pdf_url.lower():
                    link_text = link.text(strip=True)
                    if not link_text:
                        link_text = href.split('/')[-1]

                    # The whole-company catalogue («Скачать каталог 2025 (56 Mb)»,
                    # /doc/Каталог…pdf) is linked from every product page. It is
                    # not this product's manual: ~140k chars of other products
                    # would be indexed under the first product that linked it.
                    if _is_general_catalogue(pdf_url, link_text):
                        logger.debug(f"Skipping general catalogue PDF on {url}: {pdf_url}")
                        continue

                    pdf_links.append((pdf_url, link_text))

        # Remove duplicates
        pdf_links = list(set(pdf_links))

        logger.debug(f"Extracted from {url}: description={'Yes' if full_description else 'No'}, PDFs={len(pdf_links)}")

        return full_description, pdf_links

    async def scrape_product(self, product_id: int, product_name: str, product_url: str) -> bool:
        """Scrape a single product page."""
        try:
            html = await self.fetch_page(product_url)
            full_description, pdf_links = self.extract_product_data(html, product_url)

            # Update product in database
            for session in get_session():
                # Update product
                db_product = session.get(Product, product_id)
                if db_product:
                    db_product.scraped_html = html
                    db_product.scraped_full_description = full_description
                    db_product.scraped_at = datetime.utcnow()

                # Save PDF document records
                for pdf_url, title in pdf_links:
                    # Check if document already exists
                    existing = session.query(Document).filter(
                        Document.source_url == pdf_url
                    ).first()

                    if not existing:
                        document = Document(
                            product_id=product_id,
                            doc_type=DocumentType.PDF,
                            source_url=pdf_url,
                            title=title
                        )
                        session.add(document)

                session.commit()

            logger.info(f"Scraped product {product_id} ({product_name}): description={'Yes' if full_description else 'No'}, PDFs={len(pdf_links)}")
            return True

        except Exception as e:
            logger.error(f"Error scraping product {product_id} ({product_url}): {e}", exc_info=True)
            return False

    async def scrape_products(
        self,
        limit: Optional[int] = None,
        force: bool = False,
        product_ids: Optional[Iterable[int]] = None,
    ) -> dict:
        """Scrape multiple products.

        `product_ids` restricts the run to those products (catalog sync passes
        the ids it just inserted or whose URL changed); None = every product
        that matches the `force` / `scraped_at` filter, as before.
        """
        ids: Optional[list[int]] = None
        if product_ids is not None:
            ids = list(product_ids)
            if not ids:
                logger.info("No products to scrape")
                return {'total': 0, 'success': 0, 'failed': 0}

        # Get products to scrape - extract data first
        product_data = []
        for session in get_session():
            query = session.query(Product.id, Product.name, Product.url)

            if ids is not None:
                query = query.filter(Product.id.in_(ids))

            if not force:
                query = query.filter(Product.scraped_at.is_(None))

            if limit:
                query = query.limit(limit)

            product_data = [(p.id, p.name, p.url) for p in query.all()]

        if not product_data:
            logger.info("No products to scrape")
            return {'total': 0, 'success': 0, 'failed': 0}

        logger.info(f"Starting to scrape {len(product_data)} products")

        # Create tasks for concurrent scraping
        tasks = []
        for product_id, product_name, product_url in product_data:
            task = asyncio.create_task(self.scrape_product(product_id, product_name, product_url))
            tasks.append(task)

        # Execute with limited concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {i} failed with exception: {result}", exc_info=True)

        # Count results
        success_count = sum(1 for r in results if r is True)
        failed_count = len(results) - success_count

        result = {
            'total': len(product_data),
            'success': success_count,
            'failed': failed_count
        }

        logger.info(f"Scraping completed: {result}")
        return result