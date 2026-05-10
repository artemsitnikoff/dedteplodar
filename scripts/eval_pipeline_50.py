#!/usr/bin/env python3
"""Full pipeline eval — 50 buyer questions.

Runs classifier + retriever (no LLM calls) to score retrieval quality.
Shows query_type, retrieval score, dealer match, and snippet.
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
logging.disable(logging.CRITICAL)

from src.core.config import settings
from src.core.database import SessionLocal
from src.core.dealer_lookup import find_dealers
from src.core.query_classifier import QueryType, classify
from src.rag.answer_generator import _extract_city
from src.rag.embedder import E5Embedder
from src.rag.hybrid_retriever import HybridRetriever

QUESTIONS = [
    # ── ПЕЧИ ДЛЯ БАНИ (12) ──────────────────────────────────────────────────
    ("Баня",     "Посоветуйте печь для бани 4×5 метров"),
    ("Баня",     "Какая печь для бани лучше: Русь или Былина"),
    ("Баня",     "Сколько камней вмещает каменка Кузбасс"),
    ("Баня",     "Печь для бани с выносной топкой — есть такие?"),
    ("Баня",     "Какая разница между Сахарой и Сиестой"),
    ("Баня",     "Хочу печь с панорамным стеклом для бани"),
    ("Баня",     "Деревянная баня 3×4, какую мощность печи брать"),
    ("Баня",     "Что такое ЛК в названии печи Русь-12 ЛК"),
    ("Баня",     "Можно ли топить печь для бани углём"),
    ("Баня",     "Как долго греется баня с печью Сахара-16"),
    ("Баня",     "Печь Казань — для какого объёма парилки"),
    ("Баня",     "Есть ли у вас печи для бани из нержавейки"),
    # ── КОТЛЫ КУППЕР (8) ────────────────────────────────────────────────────
    ("Котёл",    "Куппер ОК 15 — сколько квадратов отопит"),
    ("Котёл",    "Котёл Куппер — можно ли топить брикетами"),
    ("Котёл",    "В чём разница Куппер ОК и Куппер ПРО"),
    ("Котёл",    "Нужен ли циркуляционный насос для Куппера"),
    ("Котёл",    "Можно ли подключить бойлер косвенного нагрева к Купперу"),
    ("Котёл",    "Какой КПД у котла Куппер Оптима"),
    ("Котёл",    "Куппер 20 ПРО — максимальное давление в системе"),
    ("Котёл",    "Котёл Куппер мощность 15 кВт — это сколько кубов дров"),
    # ── ОТОПИТЕЛЬНЫЕ ПЕЧИ И КАМИНЫ (6) ──────────────────────────────────────
    ("Камин",    "Посоветуйте печь-камин для дачи 40 квадратов"),
    ("Камин",    "Кадриль — это отопительная или банная печь"),
    ("Камин",    "Сколько весит печь-камин Кадриль"),
    ("Камин",    "Какая мощность у отопительной печи Метеор-150"),
    ("Камин",    "Есть ли у Кадрили варочная поверхность"),
    ("Камин",    "Чем Огонь-батарея отличается от обычной печи"),
    # ── ДЫМОХОДЫ И МОНТАЖ (7) ───────────────────────────────────────────────
    ("Монтаж",   "Какой диаметр дымохода нужен для Куппер 15"),
    ("Монтаж",   "Нужен ли фундамент под печь Кадриль"),
    ("Монтаж",   "Какое расстояние от печи до деревянной стены"),
    ("Монтаж",   "Как вывести дымоход через крышу правильно"),
    ("Монтаж",   "Можно ли ставить печь на деревянный пол без плиты"),
    ("Монтаж",   "Как часто нужно чистить дымоход от сажи"),
    ("Монтаж",   "Первая растопка — как правильно обжечь новую печь"),
    # ── ХАРАКТЕРИСТИКИ И СРАВНЕНИЯ (5) ──────────────────────────────────────
    ("Характ.",  "Сколько весит Кузбасс-18"),
    ("Характ.",  "Русь-12 и Русь-18 — в чём разница кроме мощности"),
    ("Характ.",  "Что такое режим длительного горения в котле"),
    ("Характ.",  "Диаметр дымохода у Метеор-150"),
    ("Характ.",  "ecoMAX050 — что это за горелка"),
    # ── КОМПЛЕКТАЦИЯ И ЗАПЧАСТИ (4) ──────────────────────────────────────────
    ("Запчасти", "Что входит в базовый комплект печи Русь-12"),
    ("Запчасти", "Можно ли отдельно купить стекло для топки Кадрили"),
    ("Запчасти", "Подойдёт ли дымоход 115 мм к котлу Куппер 20"),
    ("Запчасти", "Где купить колосники для Куппера"),
    # ── О КОМПАНИИ (8) ──────────────────────────────────────────────────────
    ("Компания", "Есть ли у вас магазин в Красноярске"),
    ("Компания", "Как заказать печь с доставкой в Иркутск"),
    ("Компания", "Телефон горячей линии Теплодар"),
    ("Компания", "Можно ли оплатить картой Халва"),
    ("Компания", "Какая гарантия на котёл Куппер"),
    ("Компания", "Как вернуть печь если не подошла по размеру"),
    ("Компания", "Когда работает интернет-магазин Теплодар"),
    ("Компания", "Где находится завод Теплодар"),
]


def shorten(s, n=52):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def score_mark(score: float | None) -> str:
    if score is None:
        return "  —  "
    if score >= 0.85:
        return f"✓ {score:.3f}"
    if score >= 0.80:
        return f"~ {score:.3f}"
    return f"✗ {score:.3f}"


def main():
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = HybridRetriever(embedder=embedder, index_version=settings.index_version)

    SEP = "=" * 130
    HDR = f"{'#':<3} {'Кат.':<9} {'Тип':<9} {'Score':<9} {'Вопрос':<50}  Топ-1 / Город"
    print(SEP)
    print(HDR)
    print(SEP)

    stats = {"rag_ok": 0, "rag_mid": 0, "rag_bad": 0,
             "dealer_ok": 0, "dealer_no_city": 0, "dealer_not_found": 0,
             "faq": 0}

    with SessionLocal() as session:
        for i, (cat, q) in enumerate(QUESTIONS, 1):
            qtype = classify(q)

            if qtype == QueryType.RAG_PRODUCT:
                results = retriever.search(session, q, k=1)
                score = results[0].score if results else None
                snippet = shorten(results[0].chunk_text if results else "—")
                mark = score_mark(score)
                type_label = "RAG"

                if score is None or score < 0.80:
                    stats["rag_bad"] += 1
                elif score < 0.85:
                    stats["rag_mid"] += 1
                else:
                    stats["rag_ok"] += 1

                print(f"{i:<3} {cat:<9} {type_label:<9} {mark:<9} {shorten(q, 50):<50}  {snippet}")

            elif qtype == QueryType.FAQ_DEALER:
                city = _extract_city(q)
                type_label = "DEALER"
                if city:
                    matched, shops = find_dealers(city)
                    if shops:
                        detail = f"🏙 {matched} ({len(shops)} маг.)"
                        stats["dealer_ok"] += 1
                    else:
                        detail = f"❓ город «{city}» не найден в базе"
                        stats["dealer_not_found"] += 1
                else:
                    detail = "⚠️  город не извлечён из запроса"
                    stats["dealer_no_city"] += 1
                print(f"{i:<3} {cat:<9} {type_label:<9} {'✦ —':<9} {shorten(q, 50):<50}  {detail}")

            else:  # FAQ_COMPANY
                type_label = "FAQ"
                stats["faq"] += 1
                print(f"{i:<3} {cat:<9} {type_label:<9} {'✦ —':<9} {shorten(q, 50):<50}  ✦ из справочника")

    print(SEP)

    rag_total = stats["rag_ok"] + stats["rag_mid"] + stats["rag_bad"]
    dealer_total = stats["dealer_ok"] + stats["dealer_no_city"] + stats["dealer_not_found"]

    print(f"\nRAG ({rag_total} вопросов):")
    pct = lambda n: f"{n/rag_total*100:.0f}%" if rag_total else "—"
    print(f"  ✓ ≥0.85  : {stats['rag_ok']:>2} ({pct(stats['rag_ok'])})")
    print(f"  ~ 0.80–84: {stats['rag_mid']:>2} ({pct(stats['rag_mid'])})")
    print(f"  ✗ <0.80  : {stats['rag_bad']:>2} ({pct(stats['rag_bad'])})")

    print(f"\nDEALER ({dealer_total} вопросов):")
    print(f"  ✓ город + магазины: {stats['dealer_ok']:>2}")
    print(f"  ~ город не извлечён: {stats['dealer_no_city']:>2}")
    print(f"  ✗ нет в базе      : {stats['dealer_not_found']:>2}")

    print(f"\nFAQ компании: {stats['faq']} вопросов — без ретривала")
    print()
    print("Легенда: ✓ хорошо  ~ приемлемо  ✗ плохо  ✦ FAQ/DEALER (ретривал не нужен)")


if __name__ == "__main__":
    main()
