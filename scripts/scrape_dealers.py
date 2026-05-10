#!/usr/bin/env python3
"""Scrape all dealers from teplodar.ru via the map API and save to YAML."""
import asyncio
import re
import json
import time
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser
import yaml

BASE_URL = "https://www.teplodar.ru"
OUT_FILE = Path(__file__).parent.parent / "data" / "dealers.yaml"


def clean_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).replace("\r\n", " ").replace("\n", " ").strip()


def get_region_options() -> list[dict]:
    """Get all region options from the contacts page."""
    r = httpx.get(f"{BASE_URL}/contacts/",
                  headers={"User-Agent": "Mozilla/5.0"},
                  follow_redirects=True, timeout=20)
    tree = HTMLParser(r.text)
    options = []
    for opt in tree.css("select option"):
        val = opt.attributes.get("value", "0")
        label = opt.text(strip=True)
        if val and val != "0" and label:
            options.append({"id": int(val), "name": label})
    return options


def fetch_shops_for_region(city_code: int, region_code: int | None = None) -> list[dict]:
    """Call the shop map API for a given cityCode."""
    params = {
        "action": "load_shop_map",
        "region": 1,
        "main": 1,
        "regionCode": region_code or city_code,
        "cityCode": city_code,
    }
    try:
        r = httpx.get(f"{BASE_URL}/ajax/",
                      params=params,
                      headers={"User-Agent": "Mozilla/5.0",
                               "X-Requested-With": "XMLHttpRequest"},
                      follow_redirects=True, timeout=15)
        data = r.json()
        items = data.get("MAP_ITEMS", {})
        if isinstance(items, dict):
            items = list(items.values())
        return items
    except Exception as e:
        print(f"  ERROR cityCode={city_code}: {e}")
        return []


def normalize_shop(item: dict, region_name: str) -> dict:
    """Normalize a raw shop dict into a clean structure."""
    phones = []
    for p in (item.get("PHONES") or []):
        ph = p.get("PHONE", "").strip()
        if ph:
            phones.append(ph)
    if not phones and item.get("PHONE"):
        phones = [item["PHONE"].strip()]

    return {
        "name": item.get("NAME", "").strip(),
        "city": item.get("SECTION_NAME", region_name).strip(),
        "address": item.get("ADDRESS", "").strip(),
        "phones": phones,
        "work_time": clean_html(item.get("WORK_TIME", "")),
        "site": item.get("SITE", "").strip() or None,
        "is_teplodar_own": bool(item.get("TEPLODAR")),
        "is_service": bool(item.get("SERVICE")),
    }


def main():
    print("Fetching region list...")
    regions = get_region_options()
    print(f"Found {len(regions)} regions")

    all_shops: dict[str, list] = {}  # city -> list of shops
    seen_ids: set[str] = set()

    for i, reg in enumerate(regions, 1):
        city_code = reg["id"]
        region_name = reg["name"]
        print(f"[{i}/{len(regions)}] {region_name} (cityCode={city_code})...", end=" ", flush=True)

        items = fetch_shops_for_region(city_code)
        new_count = 0
        for item in items:
            shop_id = item.get("ID", "")
            if shop_id in seen_ids:
                continue
            seen_ids.add(shop_id)
            shop = normalize_shop(item, region_name)
            city_key = shop["city"] or region_name
            all_shops.setdefault(city_key, []).append(shop)
            new_count += 1

        print(f"+{new_count} new shops")
        time.sleep(0.3)  # be polite

    # Build output structure
    total_shops = sum(len(v) for v in all_shops.values())
    print(f"\nTotal unique shops: {total_shops} across {len(all_shops)} cities")

    output = {
        "meta": {
            "source": "https://www.teplodar.ru/contacts/",
            "total_shops": total_shops,
            "total_cities": len(all_shops),
            "note": "Полный список можно найти на teplodar.ru/contacts/ — выберите свой регион",
        },
        "cities": {}
    }

    for city, shops in sorted(all_shops.items()):
        output["cities"][city] = []
        for s in shops:
            entry = {
                "name": s["name"],
                "address": s["address"],
                "phones": s["phones"],
            }
            if s["work_time"]:
                entry["work_time"] = s["work_time"]
            if s["site"] and s["site"] != "www.teplodar.ru":
                entry["site"] = s["site"]
            if s["is_teplodar_own"]:
                entry["own_store"] = True
            if s["is_service"]:
                entry["service_center"] = True
            output["cities"][city].append(entry)

    OUT_FILE.write_text(
        yaml.dump(output, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8"
    )
    print(f"\nSaved to {OUT_FILE}")
    print("\nTop cities by shop count:")
    for city, shops in sorted(all_shops.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"  {city}: {len(shops)} shops")


if __name__ == "__main__":
    main()
