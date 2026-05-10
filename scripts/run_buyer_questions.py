#!/usr/bin/env python3
"""Run 25 buyer questions through RAG and produce a scoring table."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.rag.embedder import E5Embedder
from src.rag.simple_retriever import SimpleRetriever
from src.products.models import Product
from src.documents.models import Document
from src.core.database import SessionLocal


QUESTIONS = [
    # Подбор
    ("Подбор", "Посоветуйте печь для бани на 14 кубов"),
    ("Подбор", "Какой котёл нужен для дома 100 квадратов"),
    ("Подбор", "Хочу печь-камин для дачи, чтобы и грелась и готовить можно"),
    ("Подбор", "Подберите дровяную печь для парилки на 4 человека"),
    ("Подбор", "Что лучше выбрать на пеллетах или на дровах"),
    # Характеристики
    ("Характеристики", "Сколько весит печь Кадриль"),
    ("Характеристики", "Какой диаметр дымохода у Метеор-150"),
    ("Характеристики", "Можно ли в Куппере топить углём"),
    ("Характеристики", "Сколько прогревает печь Сахара"),
    ("Характеристики", "Чем отличается Русь-12 от Русь-18"),
    # Установка
    ("Установка", "Как первый раз растопить новую печь"),
    ("Установка", "Нужен ли фундамент под печь Кадриль"),
    ("Установка", "Как часто чистить дымоход"),
    ("Установка", "Можно ли установить печь у деревянной стены"),
    ("Установка", "Как заземлить пульт ПУ-ВН-10"),
    # Комплектация
    ("Комплектация", "Что входит в комплект печи для бани"),
    ("Комплектация", "Подойдёт ли дымоход 115 к котлу Куппер"),
    ("Комплектация", "Какие запчасти есть на Куппер ПРО"),
    # О компании (нет в базе!)
    ("О компании", "Где находится ваш магазин"),
    ("О компании", "Когда вы работаете"),
    ("О компании", "Доставляете ли в Красноярск"),
    ("О компании", "Какой телефон для заказа"),
    ("О компании", "Есть ли ваш дилер в Екатеринбурге"),
    ("О компании", "Можно ли купить в рассрочку"),
    ("О компании", "Какая гарантия на котлы Куппер"),
]


def shorten(text: str, n: int = 60) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def describe_top(result, session) -> str:
    if result.chunk_type == "product":
        prod = session.get(Product, result.product_id) if result.product_id else None
        return f"Товар: {prod.name}" if prod else f"product#{result.product_id}"
    if result.chunk_type == "pdf":
        doc = session.get(Document, result.document_id) if result.document_id else None
        prod = session.get(Product, result.product_id) if result.product_id else None
        prefix = doc.title if doc else f"doc#{result.document_id}"
        if prod:
            prefix += f" → {prod.name}"
        return f"PDF: {prefix}"
    return f"{result.chunk_type}#{result.id}"


def main():
    logging.basicConfig(level=logging.WARNING)

    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = SimpleRetriever(
        embedder=embedder,
        index_version=settings.index_version,
    )

    print(f"\n{'='*120}")
    print(f"{'#':<3} {'Категория':<14} {'Score':<7} {'Вопрос':<55} Топ-1 результат")
    print(f"{'='*120}")

    with SessionLocal() as session:
        for i, (cat, q) in enumerate(QUESTIONS, 1):
            results = retriever.search(session, q, k=1)
            if not results:
                print(f"{i:<3} {cat:<14} {'—':<7} {shorten(q, 55):<55} — нет результатов —")
                continue
            top = results[0]
            score_str = f"{top.score:.3f}"
            mark = "✓" if top.score >= 0.85 else ("~" if top.score >= 0.80 else "✗")
            print(
                f"{i:<3} {cat:<14} {score_str:<7} {shorten(q, 55):<55} "
                f"{mark} {shorten(describe_top(top, session), 60)}"
            )

    print(f"{'='*120}\n")
    print("Легенда score: ✓ ≥0.85 (релевантно) | ~ 0.80–0.85 (терпимо) | ✗ <0.80 (слабо)\n")


if __name__ == "__main__":
    main()
