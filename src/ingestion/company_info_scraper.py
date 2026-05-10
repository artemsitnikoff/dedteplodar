"""Company information scraper for Teplodar website."""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Optional, Set, Dict, NamedTuple
from urllib.parse import urljoin, urlparse, quote
import xml.etree.ElementTree as ET

import httpx
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings

logger = logging.getLogger(__name__)


class CompanyPageData(NamedTuple):
    """Data extracted from a company information page."""
    url: str
    title: str
    content: str
    char_count: int


class CompanyInfoScraper:
    """Scraper for company information pages on Teplodar website."""

    BASE_URL = "https://www.teplodar.ru"

    # Keywords to identify information pages
    INFO_PAGE_KEYWORDS = {
        'contact', 'contacts', 'about', 'delivery', 'dostavka', 'payment', 'oplata',
        'warranty', 'garantiya', 'service', 'servis', 'partners', 'dealers', 'shops',
        'firmennye-magaziny', 'magaziny', 'production', 'proizvodstvo', 'company',
        'faq', 'help', 'support', 'info', 'information'
    }

    # Content selectors to extract main content
    CONTENT_SELECTORS = [
        '.main-content',
        '#content',
        '.detail-text',
        'article',
        'main',
        '.content-area',
        '.page-content'
    ]

    # Elements to exclude from content
    EXCLUDE_SELECTORS = [
        'header', 'footer', 'nav', '.menu', '.navigation', '.breadcrumb',
        '.sidebar', 'script', 'style', '.comments', '.social', '.share',
        '.banner', '.advertisement', '.popup', '.modal'
    ]

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.discovered_urls: Set[str] = set()

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
    async def fetch_page(self, url: str) -> Optional[str]:
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
                if e.response.status_code == 404:
                    logger.warning(f"Page not found: {url}")
                    return None
                logger.warning(f"HTTP error {e.response.status_code} for {url}")
                raise
            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                raise

    def _normalize_url(self, url: str, base_url: str = BASE_URL) -> str:
        """Normalize URL to absolute form."""
        if url.startswith('http'):
            return url
        return urljoin(base_url, url)

    def _is_info_page(self, url: str) -> bool:
        """Check if URL looks like an information page."""
        url_lower = url.lower()

        # Skip product catalog pages
        if '/catalog/' in url_lower and ('/detail/' in url_lower or '/section/' in url_lower):
            return False

        # Skip media files and technical pages
        if any(ext in url_lower for ext in ['.jpg', '.png', '.pdf', '.doc', '.zip',
                                          '/upload/', '/bitrix/', '/local/']):
            return False

        # Check for info page keywords
        return any(keyword in url_lower for keyword in self.INFO_PAGE_KEYWORDS)

    async def _discover_from_main_page(self) -> Set[str]:
        """Discover information pages from main page navigation and footer."""
        logger.info("Discovering pages from main page...")

        html = await self.fetch_page(self.BASE_URL)
        if not html:
            logger.warning("Could not fetch main page")
            return set()

        parser = HTMLParser(html)
        urls = set()

        # Extract all links
        for link in parser.css('a[href]'):
            href_attr = link.attributes.get('href')
            if not href_attr:
                continue

            href = href_attr.strip()
            if not href:
                continue

            abs_url = self._normalize_url(href)

            # Check if it's an info page
            if self._is_info_page(abs_url):
                urls.add(abs_url)

        logger.info(f"Found {len(urls)} potential info pages from main page")
        return urls

    async def _discover_from_sitemap(self) -> Set[str]:
        """Discover information pages from sitemap.xml."""
        logger.info("Discovering pages from sitemap...")

        sitemap_url = f"{self.BASE_URL}/sitemap.xml"
        html = await self.fetch_page(sitemap_url)

        if not html:
            logger.info("No sitemap found")
            return set()

        urls = set()
        try:
            root = ET.fromstring(html)

            # Handle different sitemap formats
            for url_elem in root.iter():
                if url_elem.tag.endswith('loc'):
                    url = url_elem.text
                    if url and self._is_info_page(url):
                        urls.add(url)

        except ET.ParseError as e:
            logger.warning(f"Could not parse sitemap: {e}")

        logger.info(f"Found {len(urls)} potential info pages from sitemap")
        return urls

    def _extract_content(self, html: str, url: str) -> Optional[CompanyPageData]:
        """Extract clean content from HTML page."""
        parser = HTMLParser(html)

        # Get page title
        title_elem = parser.css_first('title')
        title = title_elem.text(strip=True) if title_elem else ""

        # If no title, try h1
        if not title:
            h1_elem = parser.css_first('h1')
            title = h1_elem.text(strip=True) if h1_elem else ""

        # Remove unwanted elements
        for selector in self.EXCLUDE_SELECTORS:
            for elem in parser.css(selector):
                elem.decompose()

        # Extract main content
        content = None

        # Try content selectors
        for selector in self.CONTENT_SELECTORS:
            content_elem = parser.css_first(selector)
            if content_elem:
                content = content_elem.text(strip=True)
                if content and len(content) > 500:  # Meaningful content threshold
                    break

        # Fallback: get all text from body
        if not content:
            body = parser.css_first('body')
            if body:
                content = body.text(strip=True)

        if not content or len(content) < 500:
            logger.debug(f"Page {url} has insufficient content ({len(content) if content else 0} chars)")
            return None

        # Clean up content
        content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
        content = content.strip()

        return CompanyPageData(
            url=url,
            title=title or f"Страница {urlparse(url).path}",
            content=content,
            char_count=len(content)
        )

    async def discover_pages(self, extra_urls: Optional[List[str]] = None) -> List[str]:
        """Discover all information pages."""
        logger.info("Starting page discovery...")

        urls = set()

        # Discover from main page
        main_urls = await self._discover_from_main_page()
        urls.update(main_urls)

        # Discover from sitemap
        sitemap_urls = await self._discover_from_sitemap()
        urls.update(sitemap_urls)

        # Add manually specified URLs
        if extra_urls:
            for url in extra_urls:
                normalized = self._normalize_url(url)
                if self._is_info_page(normalized):
                    urls.add(normalized)

        # Common information page paths to try
        common_paths = [
            '/contacts/', '/contact-us/', '/about/', '/company/',
            '/delivery/', '/dostavka/', '/payment/', '/oplata/',
            '/warranty/', '/garantiya/', '/service/', '/servis/',
            '/partners/', '/dealers/', '/shops/', '/firmennye-magaziny/',
            '/production/', '/proizvodstvo/', '/faq/', '/help/'
        ]

        for path in common_paths:
            url = f"{self.BASE_URL}{path}"
            if self._is_info_page(url):
                urls.add(url)

        self.discovered_urls = urls
        logger.info(f"Total discovered URLs: {len(urls)}")

        return sorted(urls)

    async def scrape_page(self, url: str) -> Optional[CompanyPageData]:
        """Scrape a single information page."""
        try:
            html = await self.fetch_page(url)
            if not html:
                return None

            return self._extract_content(html, url)

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    async def scrape_all(self, extra_urls: Optional[List[str]] = None) -> Dict[str, any]:
        """Scrape all discovered information pages."""
        # Discover pages
        urls = await self.discover_pages(extra_urls)

        if not urls:
            logger.info("No information pages discovered")
            return {'total': 0, 'success': 0, 'failed': 0, 'pages': []}

        logger.info(f"Starting to scrape {len(urls)} information pages")

        # Create tasks for concurrent scraping
        tasks = []
        for url in urls:
            task = asyncio.create_task(self.scrape_page(url))
            tasks.append(task)

        # Execute with limited concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful_pages = []
        failed_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task for {urls[i]} failed: {result}")
                failed_count += 1
            elif result is None:
                logger.warning(f"No content extracted from {urls[i]}")
                failed_count += 1
            else:
                successful_pages.append(result)
                logger.info(f"Scraped {urls[i]}: {result.char_count} chars")

        result_summary = {
            'total': len(urls),
            'success': len(successful_pages),
            'failed': failed_count,
            'pages': successful_pages
        }

        logger.info(f"Scraping completed: {result_summary}")
        return result_summary