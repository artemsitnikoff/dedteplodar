"""Dealer lookup from pre-scraped dealers.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

DEALERS_FILE = Path(__file__).parent.parent.parent / "base" / "dealers.yaml"
SITE_URL = "https://www.teplodar.ru/contacts/"


@dataclass
class Shop:
    name: str
    city: str
    address: str
    phones: list[str]
    work_time: str
    site: Optional[str]
    is_own_store: bool
    is_service: bool


@lru_cache(maxsize=1)
def _load_dealers() -> dict:
    return yaml.safe_load(DEALERS_FILE.read_text(encoding="utf-8"))


def _normalize(s: str) -> str:
    return re.sub(r"[\s\-]+", " ", s.lower().strip())


def find_dealers(city: str) -> tuple[str, list[Shop]]:
    """Find dealers for a city. Returns (matched_city_name, shops).

    Tries: exact match → prefix match → substring match.
    Returns ('', []) if nothing found.
    """
    data = _load_dealers()
    cities: dict[str, list] = data.get("cities", {})
    q = _normalize(city)

    # 1. Exact match (case-insensitive)
    for key in cities:
        if _normalize(key) == q:
            return key, _parse_shops(key, cities[key])

    # 2. Prefix match
    for key in cities:
        if _normalize(key).startswith(q) or q.startswith(_normalize(key)):
            return key, _parse_shops(key, cities[key])

    # 3. Substring match
    for key in cities:
        if q in _normalize(key) or _normalize(key) in q:
            return key, _parse_shops(key, cities[key])

    return "", []


def _parse_shops(city: str, raw: list) -> list[Shop]:
    shops = []
    for s in raw:
        shops.append(Shop(
            name=s.get("name", ""),
            city=city,
            address=s.get("address", ""),
            phones=s.get("phones", []),
            work_time=s.get("work_time", "").replace("&nbsp;", " ").strip(),
            site=s.get("site"),
            is_own_store=bool(s.get("own_store")),
            is_service=bool(s.get("service_center")),
        ))
    return shops


def format_dealer_reply(city: str) -> str:
    """Return a ready-to-send reply for a given city.

    If city not found — returns a message explaining this
    and suggesting to check the website or use the online store.
    """
    matched_city, shops = find_dealers(city)

    if not shops:
        return (
            f"К сожалению, в городе «{city}» дилеров «Теплодар» нет в нашей базе. "
            f"Возможно, вы сможете найти ближайший магазин на {SITE_URL} — "
            f"выберите ваш регион. Также доступен заказ через интернет-магазин "
            f"с бесплатной доставкой по России (при наличии печи или котла в заказе)."
        )

    lines = [f"Магазины «Теплодар» в городе {matched_city}:\n"]
    for i, s in enumerate(shops, 1):
        badge = ""
        if s.is_own_store:
            badge = " ★ фирменный"
        elif s.is_service:
            badge = " 🔧 сервис"

        lines.append(f"{i}. {s.name}{badge}")
        lines.append(f"   Адрес: {s.address}")
        if s.phones:
            lines.append(f"   Тел.: {', '.join(s.phones)}")
        if s.work_time:
            lines.append(f"   Режим: {s.work_time}")
        if s.site:
            lines.append(f"   Сайт: {s.site}")
        lines.append("")

    lines.append(f"Полный список по региону и карта: {SITE_URL}")
    return "\n".join(lines)


def list_cities() -> list[str]:
    """Return sorted list of all cities with dealers."""
    data = _load_dealers()
    return sorted(data.get("cities", {}).keys())


def get_meta() -> dict:
    return _load_dealers().get("meta", {})
