"""Catalog sync: site YML feed → products → scrape/parse what's new → index.

Entry point for `scripts/sync_catalog.py` (nightly cron, admin button).
Everything heavy (E5 / torch) is imported lazily inside run_sync so the
admin app can import this module for the state endpoint without pulling
torch in at startup.

Pipeline (each step is reported in SyncReport):
  fetch    – download the feed by URL (or take a local file), keep *.prev.xml
  parse    – existing YMLParser (categories + offers, streaming lxml)
  guard    – no offers / fewer than catalog_sync_min_ratio of the active
             products → abort before touching the DB
  diff     – fingerprint offers vs products: new / changed / unchanged /
             missing (→ is_active=False) / reactivated / url_changed
  apply    – YMLParser upsert + is_active flags + scraped_at reset
  scrape   – product pages of new / url-changed products (description, PDFs)
  pdf      – text of their newly discovered PDFs
  index    – IncrementalIndexer (or a full rebuild with full_index=True)
  state    – base/catalog_sync_state.json for the admin UI; optional
             Telegram note to OPERATOR_CHAT_ID
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from src.core.config import settings
from src.core.database import SessionLocal, create_tables
from src.ingestion.yml_parser import YMLParser
from src.products.models import Product
from src.products.schemas import YMLCategory, YMLOffer

logger = logging.getLogger(__name__)

STATE_HISTORY = 20


class FeedError(RuntimeError):
    """The feed could not be fetched/parsed or failed the sanity guard."""


# ───────────────────────────────────────────────────────────── report
@dataclass
class SyncReport:
    status: str = "running"            # running | ok | error | skipped
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    source: str = ""
    feed_bytes: int = 0
    categories: int = 0
    offers: int = 0
    products_new: int = 0
    products_changed: int = 0
    products_unchanged: int = 0
    products_missing: int = 0
    products_reactivated: int = 0
    url_conflicts: int = 0
    scraped_ok: int = 0
    scraped_failed: int = 0
    pdfs_parsed: int = 0
    pdfs_failed: int = 0
    index: dict = field(default_factory=dict)
    dry_run: bool = False
    error: Optional[str] = None
    new_names: List[str] = field(default_factory=list)      # first few, for the summary
    missing_names: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        """One paragraph for logs / Telegram."""
        if self.status == "skipped":
            return f"Синхронизация каталога пропущена: {self.error}"
        if self.status == "error":
            return f"❌ Синхронизация каталога упала: {self.error}"
        parts = [
            f"✅ Каталог синхронизирован за {self.duration_s:.0f} с",
            f"в фиде {self.offers} товаров: новых {self.products_new}, изменённых {self.products_changed}, "
            f"сняты с сайта {self.products_missing}, вернулись {self.products_reactivated}",
        ]
        if self.new_names:
            parts.append("новые: " + ", ".join(self.new_names))
        if self.missing_names:
            parts.append("сняты: " + ", ".join(self.missing_names))
        if self.scraped_ok or self.scraped_failed:
            parts.append(f"страниц прочитано {self.scraped_ok}, ошибок {self.scraped_failed}")
        if self.pdfs_parsed or self.pdfs_failed:
            parts.append(f"PDF распознано {self.pdfs_parsed}, ошибок {self.pdfs_failed}")
        idx = self.index or {}
        if idx.get("skipped"):
            parts.append("индекс без изменений")
        elif idx.get("full_rebuild"):
            parts.append(f"индекс пересобран полностью: {idx.get('index_size', 0)} чанков")
        elif idx:
            parts.append(
                f"индекс: −{idx.get('chunks_removed', 0)} +{idx.get('chunks_added', 0)} чанков, "
                f"всего {idx.get('index_size', 0)}"
            )
        if self.dry_run:
            parts.append("(dry-run, в базу ничего не записано)")
        return "; ".join(parts)


# ───────────────────────────────────────────────────────────── fetch
def _looks_like_yml(head: bytes) -> bool:
    text = head.lstrip()[:400].lower()
    return text.startswith(b"<?xml") or b"<yml_catalog" in text


def fetch_feed(source: str, dest: Path, timeout: float = 120.0, attempts: int = 3) -> Path:
    """Download `source` (http/https) into `dest` atomically, keeping the
    previous copy as `<dest>.prev.xml`; a local path is returned as is."""
    if not source.lower().startswith(("http://", "https://")):
        path = Path(source)
        if not path.is_file():
            raise FeedError(f"feed file not found: {path}")
        return path

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    last_err: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
                headers={"User-Agent": settings.user_agent},
            ) as client:
                with client.stream("GET", source) as resp:
                    resp.raise_for_status()
                    size = 0
                    head = b""
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes():
                            if len(head) < 512:
                                head += chunk
                            f.write(chunk)
                            size += len(chunk)
            if size == 0 or not _looks_like_yml(head):
                raise FeedError(f"response is not a YML catalog ({size} bytes, starts with {head[:60]!r})")
            if dest.exists():
                shutil.copyfile(dest, dest.with_name(dest.stem + ".prev.xml"))
            os.replace(tmp, dest)
            logger.info("[sync] feed downloaded: %s → %s (%d bytes)", source, dest, size)
            return dest
        except FeedError:
            tmp.unlink(missing_ok=True)
            raise
        except Exception as e:  # network / HTTP — retry with backoff
            last_err = e
            tmp.unlink(missing_ok=True)
            logger.warning("[sync] feed download attempt %d/%d failed: %s", attempt, attempts, e)
            if attempt < attempts:
                time.sleep(2 ** attempt)
    raise FeedError(f"could not download feed after {attempts} attempts: {last_err}")


def parse_feed(path: Path) -> tuple[List[YMLCategory], List[YMLOffer]]:
    parser = YMLParser()
    categories = parser.parse_categories(str(path))
    offers = list(parser.parse_offers(str(path)))
    if not offers:
        raise FeedError("feed contains no offers")
    return categories, offers


# ───────────────────────────────────────────────────────────── diff
def _price(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def offer_fingerprint(offer: YMLOffer, keep_description: Optional[str] = None) -> str:
    """Hash of the fields that reach the chunk text or drive scraping.

    `keep_description` is the DB value the upsert keeps when the feed has no
    description (bot.xml carries one for a third of the offers only), so the
    comparison sees what the DB will actually hold."""
    payload = {
        "name": offer.name,
        "model": offer.model,
        "price": _price(offer.price),
        "category_id": offer.category_id,
        "description": offer.description or keep_description or None,
        "url": offer.url,
        "params": sorted((p.name, p.value) for p in offer.params),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def product_fingerprint(product: Product) -> str:
    payload = {
        "name": product.name,
        "model": product.model,
        "price": _price(product.price),
        "category_id": product.category_id,
        "description": product.description or None,
        "url": product.url,
        "params": sorted((p.name, p.value) for p in product.params),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@dataclass
class CatalogDiff:
    new: List[int] = field(default_factory=list)
    changed: List[int] = field(default_factory=list)
    unchanged: List[int] = field(default_factory=list)
    missing: List[int] = field(default_factory=list)        # active in DB, absent from feed
    reactivated: List[int] = field(default_factory=list)    # inactive in DB, back in feed
    url_changed: List[int] = field(default_factory=list)    # re-scrape these
    url_conflicts: List[int] = field(default_factory=list)  # offer url owned by another product id
    names: dict = field(default_factory=dict)               # id → name, for summaries

    @property
    def to_scrape(self) -> List[int]:
        return sorted(set(self.new) | set(self.url_changed))

    @property
    def to_reindex(self) -> List[int]:
        """Product + document chunks: rows that are not in the index yet."""
        return sorted(set(self.new) | set(self.reactivated))

    @property
    def to_refresh(self) -> List[int]:
        """Product chunk only (price / name / params changed); PDFs stay."""
        return sorted(set(self.changed) - set(self.new) - set(self.reactivated))

    @property
    def is_noop(self) -> bool:
        return not (self.new or self.changed or self.missing or self.reactivated)


def compute_diff(session: Session, offers: List[YMLOffer]) -> CatalogDiff:
    products = session.execute(
        select(Product).options(selectinload(Product.params))
    ).scalars().all()
    by_id = {p.id: p for p in products}
    url_owner = {p.url: p.id for p in products}
    diff = CatalogDiff()
    seen: set[int] = set()

    for offer in offers:
        if offer.id in seen:
            continue  # duplicate offer id in the feed — first one wins
        seen.add(offer.id)
        diff.names[offer.id] = offer.name
        owner = url_owner.get(offer.url)
        if owner is not None and owner != offer.id:
            diff.url_conflicts.append(offer.id)
            continue
        existing = by_id.get(offer.id)
        if existing is None:
            diff.new.append(offer.id)
            continue
        if not existing.is_active:
            diff.reactivated.append(offer.id)
        if existing.url != offer.url:
            diff.url_changed.append(offer.id)
        if product_fingerprint(existing) != offer_fingerprint(offer, keep_description=existing.description):
            diff.changed.append(offer.id)
        else:
            diff.unchanged.append(offer.id)

    for p in products:
        if p.id not in seen and p.is_active:
            diff.missing.append(p.id)
            diff.names[p.id] = p.name
    return diff


# ───────────────────────────────────────────────────────────── apply
def apply_feed(categories: List[YMLCategory], offers: List[YMLOffer], diff: CatalogDiff) -> None:
    """Upsert the feed (existing YMLParser) and set the sync-specific flags."""
    parser = YMLParser()
    parser.save_categories(categories)
    conflicts = set(diff.url_conflicts)
    parser.save_offers(o for o in offers if o.id not in conflicts)

    feed_ids = [o.id for o in offers if o.id not in conflicts]
    with SessionLocal() as s:
        if diff.missing:
            s.execute(update(Product).where(Product.id.in_(diff.missing)).values(is_active=False))
        if feed_ids:
            s.execute(update(Product).where(Product.id.in_(feed_ids), Product.is_active.is_(False)).values(is_active=True))
        if diff.url_changed:
            s.execute(update(Product).where(Product.id.in_(diff.url_changed)).values(scraped_at=None))
        s.commit()


# ───────────────────────────────────────────────────────────── state / notify
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_state(path: Optional[Path] = None) -> dict:
    path = path or settings.catalog_sync_state_path
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"last": None, "history": []}
    except Exception as e:  # corrupt file must not break the admin page
        logger.warning("[sync] cannot read state %s: %s", path, e)
        return {"last": None, "history": []}


def write_state(report: SyncReport, path: Optional[Path] = None) -> None:
    path = Path(path or settings.catalog_sync_state_path)
    state = read_state(path)
    entry = report.to_dict()
    history = [h for h in state.get("history", []) if isinstance(h, dict)]
    history.insert(0, entry)
    _atomic_write_text(path, json.dumps({"last": entry, "history": history[:STATE_HISTORY]}, ensure_ascii=False, indent=1))


def notify_telegram(text: str) -> bool:
    """Best-effort note to OPERATOR_CHAT_ID via the bot token; never raises."""
    if not settings.bot_token or not settings.operator_chat_id:
        logger.info("[sync] telegram notify skipped: BOT_TOKEN / OPERATOR_CHAT_ID not set")
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
            json={"chat_id": settings.operator_chat_id, "text": text[:4000]},
            timeout=10.0,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.warning("[sync] telegram notify failed: %s", e)
        return False


# ───────────────────────────────────────────────────────────── lock
class _SyncLock:
    """Non-blocking file lock: cron and the admin button must not overlap."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
        self._fh.flush()
        return True

    def __exit__(self, *exc) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()


def _lock_path() -> Path:
    return Path(settings.catalog_sync_state_path).with_name(".catalog_sync.lock")


def is_sync_running() -> bool:
    """True while a sync (cron or admin-started) holds the lock."""
    with _SyncLock(_lock_path()) as acquired:
        return not acquired


# ───────────────────────────────────────────────────────────── orchestration
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_sync(
    source: Optional[str] = None,
    *,
    dry_run: bool = False,
    skip_scrape: bool = False,
    skip_pdf: bool = False,
    skip_index: bool = False,
    full_index: bool = False,
    notify: bool = False,
    write_state_file: bool = True,
) -> SyncReport:
    """Run the whole pipeline. Never raises: the outcome is in report.status."""
    report = SyncReport(started_at=_now(), dry_run=dry_run)
    t0 = time.monotonic()
    source = source or settings.yandex_yml_url or (str(settings.yandex_yml_path) if Path(settings.yandex_yml_path).is_file() else "")
    report.source = source

    lock = _SyncLock(_lock_path())
    with lock as acquired:
        if not acquired:
            report.status, report.error = "skipped", "another sync is still running"
            report.finished_at = _now()
            logger.warning("[sync] %s", report.error)
            return report
        try:
            if not source:
                raise FeedError("no feed source: set YANDEX_YML_URL in .env or pass a file")
            _run_steps(report, source, dry_run, skip_scrape, skip_pdf, skip_index, full_index)
            report.status = "ok"
        except Exception as e:
            report.status = "error"
            report.error = f"{type(e).__name__}: {e}"
            logger.exception("[sync] failed")
        finally:
            report.finished_at = _now()
            report.duration_s = round(time.monotonic() - t0, 1)
            if write_state_file and not dry_run:
                try:
                    write_state(report)
                except Exception:
                    logger.exception("[sync] could not write state file")
            logger.info("[sync] %s", report.summary())
            if notify and (report.status != "skipped"):
                notify_telegram(report.summary())
    return report


def _run_steps(report, source, dry_run, skip_scrape, skip_pdf, skip_index, full_index) -> None:
    create_tables()

    # fetch + parse
    feed_path = fetch_feed(source, Path(settings.catalog_feed_path))
    report.feed_bytes = feed_path.stat().st_size
    categories, offers = parse_feed(feed_path)
    report.categories, report.offers = len(categories), len(offers)

    # guard + diff
    with SessionLocal() as s:
        active = s.execute(select(Product.id).where(Product.is_active.is_(True))).scalars().all()
        min_offers = int(len(active) * settings.catalog_sync_min_ratio)
        if len(offers) < min_offers:
            raise FeedError(
                f"feed has {len(offers)} offers but the DB holds {len(active)} active products "
                f"(guard: ≥{min_offers}); refusing to deactivate — check the feed"
            )
        diff = compute_diff(s, offers)

    report.products_new = len(diff.new)
    report.products_changed = len(diff.changed)
    report.products_unchanged = len(diff.unchanged)
    report.products_missing = len(diff.missing)
    report.products_reactivated = len(diff.reactivated)
    report.url_conflicts = len(diff.url_conflicts)
    report.new_names = [diff.names[i] for i in diff.new[:10]]
    report.missing_names = [diff.names[i] for i in diff.missing[:10]]
    if diff.url_conflicts:
        logger.warning(
            "[sync] %d offers skipped — their URL belongs to another product id: %s",
            len(diff.url_conflicts), diff.url_conflicts[:20],
        )
    logger.info(
        "[sync] diff: new=%d changed=%d unchanged=%d missing=%d reactivated=%d url_changed=%d",
        len(diff.new), len(diff.changed), len(diff.unchanged), len(diff.missing),
        len(diff.reactivated), len(diff.url_changed),
    )
    if dry_run:
        return

    # apply
    apply_feed(categories, offers, diff)

    # scrape new / moved product pages, then their PDFs
    scrape_ids = diff.to_scrape
    if scrape_ids and not skip_scrape:
        from src.ingestion.scraper import ProductScraper

        async def _scrape():
            async with ProductScraper() as scraper:
                return await scraper.scrape_products(limit=0, force=False, product_ids=scrape_ids)

        res = asyncio.run(_scrape())
        report.scraped_ok, report.scraped_failed = res.get("success", 0), res.get("failed", 0)

        if not skip_pdf:
            from src.ingestion.pdf_parser import PDFParser

            async def _pdfs():
                async with PDFParser() as parser:
                    return await parser.parse_pdfs(limit=None, product_ids=scrape_ids)

            res = asyncio.run(_pdfs())
            report.pdfs_parsed, report.pdfs_failed = res.get("success", 0), res.get("failed", 0)

    # index
    if skip_index:
        report.index = {"skipped": True, "reason": "--skip-index"}
        return
    if diff.is_noop and not full_index:
        report.index = {"skipped": True, "reason": "catalog unchanged"}
        return

    from src.rag.chunker import TextChunker
    from src.rag.embedder import E5Embedder

    chunker = TextChunker(
        model_name=settings.embedding_model_name,
        chunk_size_tokens=settings.chunk_size_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
    )
    embedder = E5Embedder(model_name=settings.embedding_model_name, device=settings.device)

    if full_index:
        from src.rag.simple_indexer import SimpleIndexBuilder
        builder = SimpleIndexBuilder(
            chunker=chunker, embedder=embedder, index_version=settings.index_version,
            batch_size=settings.batch_size_embedding, dedup_threshold=settings.pdf_dedup_threshold,
        )
        from src.rag.models import Chunk
        with SessionLocal() as s:
            builder.build_full_index(s, rebuild=True)
            n = s.execute(select(func.count(Chunk.id)).where(Chunk.index_version == settings.index_version)).scalar()
        report.index = {"full_rebuild": True, "index_size": int(n or 0)}
        return

    from src.rag.incremental_indexer import IncrementalIndexer
    indexer = IncrementalIndexer(
        chunker=chunker, embedder=embedder, index_version=settings.index_version,
        data_dir="base", batch_size=settings.batch_size_embedding,
        dedup_threshold=settings.pdf_dedup_threshold,
    )
    with SessionLocal() as s:
        report.index = indexer.update(
            s, reindex_ids=diff.to_reindex, remove_ids=diff.missing, refresh_ids=diff.to_refresh,
        ).to_dict()
