"""Catalog sync: feed diff, apply, guard, state file, lock (no network, no torch)."""
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.database import SessionLocal, create_tables
from src.documents.models import Document
from src.ingestion import catalog_sync as cs
from src.products.models import Category, Product, ProductParam
from src.rag.models import Chunk


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    create_tables()
    with SessionLocal() as s:
        for model in (Chunk, Document, ProductParam, Product, Category):
            s.query(model).delete()
        s.commit()
    # keep state / lock / feed copies out of the repo's base/
    monkeypatch.setattr(settings, "catalog_sync_state_path", tmp_path / "state.json")
    monkeypatch.setattr(settings, "catalog_feed_path", tmp_path / "feed.xml")
    yield


def write_feed(path: Path, offers: list[dict]) -> Path:
    """offers: dicts with id, name, url, price, category, description, params."""
    items = []
    for o in offers:
        params = "".join(f'<param name="{k}">{v}</param>' for k, v in o.get("params", {}).items())
        items.append(
            f'<offer id="{o["id"]}" available="true">'
            f'<url>{o["url"]}</url><price>{o.get("price", 1000)}</price><currencyId>RUR</currencyId>'
            f'<categoryId>{o.get("category", 1)}</categoryId><name>{o["name"]}</name>'
            f'<description>{xml_escape(o.get("description", ""))}</description>{params}</offer>'
        )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><yml_catalog date="2026-10-27"><shop>'
        '<categories><category id="1">Котлы</category><category id="2" parentId="1">Котлы Альфа</category></categories>'
        f'<offers>{"".join(items)}</offers></shop></yml_catalog>',
        encoding="utf-8",
    )
    return path


BASE = [
    {"id": 10, "name": "Куппер ПРО 22", "url": "https://t.ru/kupper-pro-22/", "price": 50000,
     "params": {"Мощность": "22 кВт"}},
    {"id": 11, "name": "Куппер ОК 15", "url": "https://t.ru/kupper-ok-15/", "price": 30000},
]
ALFA = {"id": 12, "name": "Котёл Альфа 20", "url": "https://t.ru/alfa-20/", "price": 60000,
        "category": 2, "description": "Новый котёл"}


def sync_file(path, **kw):
    kw.setdefault("skip_scrape", True)
    kw.setdefault("skip_index", True)
    kw.setdefault("write_state_file", False)
    return cs.run_sync(str(path), **kw)


def active_ids():
    with SessionLocal() as s:
        return sorted(s.execute(select(Product.id).where(Product.is_active.is_(True))).scalars())


def test_first_sync_everything_is_new(tmp_path):
    feed = write_feed(tmp_path / "f.xml", BASE)
    with SessionLocal() as s:
        diff = cs.compute_diff(s, cs.parse_feed(feed)[1])
    assert sorted(diff.new) == [10, 11] and not diff.changed and not diff.missing
    r = sync_file(feed)
    assert r.status == "ok", r.error
    assert r.products_new == 2 and r.offers == 2 and r.categories == 2
    assert active_ids() == [10, 11]
    assert r.index == {"skipped": True, "reason": "--skip-index"}


def test_second_sync_detects_changed_missing_and_reactivated(tmp_path):
    sync_file(write_feed(tmp_path / "a.xml", BASE))

    # price of 10 changes, 11 disappears, Альфа appears
    changed = dict(BASE[0], price=55000)
    r = sync_file(write_feed(tmp_path / "b.xml", [changed, ALFA]))
    assert r.status == "ok", r.error
    assert (r.products_new, r.products_changed, r.products_unchanged, r.products_missing) == (1, 1, 0, 1)
    assert r.new_names == ["Котёл Альфа 20"] and r.missing_names == ["Куппер ОК 15"]
    assert active_ids() == [10, 12]
    with SessionLocal() as s:
        assert float(s.get(Product, 10).price) == 55000.0
        assert s.get(Product, 12).category_id == 2

    # same feed again → nothing changes, index would be skipped as unchanged
    r = sync_file(write_feed(tmp_path / "c.xml", [changed, ALFA]), skip_index=False)
    assert r.status == "ok", r.error
    assert r.products_changed == 0 and r.products_new == 0 and r.products_missing == 0
    assert r.index == {"skipped": True, "reason": "catalog unchanged"}

    # 11 is back → reactivated, scraped text is still there (never deleted)
    r = sync_file(write_feed(tmp_path / "d.xml", [changed, ALFA, BASE[1]]))
    assert r.products_reactivated == 1 and r.products_new == 0
    assert active_ids() == [10, 11, 12]


def test_changed_products_refresh_only_new_ones_reindex(tmp_path):
    sync_file(write_feed(tmp_path / "a.xml", BASE))
    with SessionLocal() as s:
        s.get(Product, 11).is_active = False
        s.commit()
    feed = write_feed(tmp_path / "b.xml", [dict(BASE[0], price=1), BASE[1], ALFA])
    with SessionLocal() as s:
        diff = cs.compute_diff(s, cs.parse_feed(feed)[1])
    assert diff.changed == [10] and diff.reactivated == [11] and diff.new == [12]
    assert diff.to_refresh == [10] and diff.to_reindex == [11, 12]


def test_feed_without_description_keeps_stored_text_and_is_not_a_change(tmp_path):
    sync_file(write_feed(tmp_path / "a.xml", [dict(BASE[0], description="<p>Котёл для дома<br>и дачи</p>")]))
    with SessionLocal() as s:
        assert s.get(Product, 10).description == "Котёл для дома\nи дачи"      # HTML flattened
    feed = write_feed(tmp_path / "b.xml", [BASE[0]])                           # no <description>
    with SessionLocal() as s:
        diff = cs.compute_diff(s, cs.parse_feed(feed)[1])
    assert diff.unchanged == [10] and not diff.changed
    sync_file(feed)
    with SessionLocal() as s:
        assert s.get(Product, 10).description == "Котёл для дома\nи дачи"      # upsert kept it


def test_url_change_resets_scrape_and_conflict_is_skipped(tmp_path):
    sync_file(write_feed(tmp_path / "a.xml", BASE))
    with SessionLocal() as s:
        from datetime import datetime
        p = s.get(Product, 10)
        p.scraped_at = datetime(2026, 1, 1)
        s.commit()

    moved = dict(BASE[0], url="https://t.ru/kupper-pro-22-new/")
    conflict = dict(ALFA, url=BASE[1]["url"])   # Альфа claims the URL of product 11
    feed = write_feed(tmp_path / "b.xml", [moved, BASE[1], conflict])
    with SessionLocal() as s:
        diff = cs.compute_diff(s, cs.parse_feed(feed)[1])
    assert diff.url_changed == [10] and diff.url_conflicts == [12] and diff.to_scrape == [10]

    r = sync_file(feed)
    assert r.status == "ok", r.error
    assert r.url_conflicts == 1
    with SessionLocal() as s:
        assert s.get(Product, 10).scraped_at is None
        assert s.get(Product, 10).url.endswith("-new/")
        assert s.get(Product, 12) is None      # the conflicting offer was not inserted


def test_guard_refuses_a_half_empty_feed(tmp_path):
    sync_file(write_feed(tmp_path / "a.xml", BASE + [ALFA, dict(ALFA, id=13, url="https://t.ru/x/")]))
    assert len(active_ids()) == 4
    r = sync_file(write_feed(tmp_path / "b.xml", [BASE[0]]))   # 1 of 4 → below 0.5
    assert r.status == "error" and "guard" in r.error
    assert len(active_ids()) == 4                                # nothing deactivated


def test_dry_run_writes_nothing(tmp_path):
    r = sync_file(write_feed(tmp_path / "a.xml", BASE), dry_run=True)
    assert r.status == "ok" and r.dry_run and r.products_new == 2
    assert active_ids() == []


def test_empty_feed_and_missing_file(tmp_path):
    empty = tmp_path / "e.xml"
    empty.write_text('<?xml version="1.0"?><yml_catalog><shop><offers></offers></shop></yml_catalog>')
    assert sync_file(empty).status == "error"
    assert "not found" in sync_file(tmp_path / "nope.xml").error


def test_state_file_and_summary(tmp_path):
    path = tmp_path / "s.json"
    for i in range(cs.STATE_HISTORY + 3):
        cs.write_state(cs.SyncReport(status="ok", offers=i), path)
    state = cs.read_state(path)
    assert state["last"]["offers"] == cs.STATE_HISTORY + 2
    assert len(state["history"]) == cs.STATE_HISTORY
    assert cs.read_state(tmp_path / "missing.json") == {"last": None, "history": []}

    rep = cs.SyncReport(status="ok", duration_s=12, offers=3, products_new=1, new_names=["Альфа"],
                        index={"chunks_removed": 2, "chunks_added": 5, "index_size": 100})
    text = rep.summary()
    assert "новых 1" in text and "Альфа" in text and "−2 +5" in text
    assert "упала" in cs.SyncReport(status="error", error="boom").summary()
    assert "пересобран полностью: 1275" in cs.SyncReport(status="ok", index={"full_rebuild": True, "index_size": 1275}).summary()


def test_lock_prevents_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "catalog_sync_state_path", tmp_path / "state.json")
    assert cs.is_sync_running() is False
    with cs._SyncLock(cs._lock_path()) as got:
        assert got is True
        assert cs.is_sync_running() is True
        r = cs.run_sync("whatever.xml", write_state_file=False)
        assert r.status == "skipped" and "running" in r.error
    assert cs.is_sync_running() is False


def test_looks_like_yml():
    assert cs._looks_like_yml(b'\n<?xml version="1.0"?><yml_catalog>')
    assert cs._looks_like_yml(b"<!DOCTYPE yml_catalog><yml_catalog date=")
    assert not cs._looks_like_yml(b"<html><body>Access denied")
