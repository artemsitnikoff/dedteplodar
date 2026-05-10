#!/usr/bin/env python3
"""Side-by-side comparison: SimpleRetriever vs HybridRetriever."""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
logging.disable(logging.CRITICAL)

from src.core.config import settings
from src.core.database import SessionLocal
from src.rag.embedder import E5Embedder
from src.rag.simple_retriever import SimpleRetriever
from src.rag.hybrid_retriever import HybridRetriever

QUERIES = [
    "печь для бани на 14 кубов",
    "сколько весит Кадриль",
    "ecoMAX050",
    "как установить котёл Куппер",
    "дымоход 115 мм",
    "Сахара или Сиеста — что лучше",
    "длительное горение дров",
    "расстояние до деревянной стены",
    "Куппер 20 ПРО максимальное давление",
    "колосники для Куппера где купить",
]


def short(s, n=60):
    s = s.replace("\n", " ").strip()
    return s[:n] + "…" if len(s) > n else s


def main():
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    dense = SimpleRetriever(embedder=embedder, index_version=settings.index_version)
    hybrid = HybridRetriever(embedder=embedder, index_version=settings.index_version, alpha=0.6)

    SEP = "─" * 130
    print(f"\n{'Запрос':<40} {'Dense score':<13} {'Hybrid score':<14} Δ    Топ-1 (hybrid)")
    print(SEP)

    with SessionLocal() as session:
        for q in QUERIES:
            d_res = dense.search(session, q, k=1)
            h_res = hybrid.search(session, q, k=5)

            d_score = d_res[0].score if d_res else 0.0
            h_top = h_res[0] if h_res else None
            h_score = h_top.score if h_top else 0.0
            delta = h_score - d_score

            snippet = short(h_top.chunk_text, 55) if h_top else "—"
            print(f"{short(q,38):<40} {d_score:.3f}        {h_score:.3f}          "
                  f"{delta:+.3f}  {snippet}")

    print(SEP)
    print("\nalpha=0.6 (60% dense + 40% BM25)")
    print("Hybrid score не сравним с dense напрямую (другая шкала после fusion),")
    print("но топ-1 результат показывает что побеждает при гибриде.")


if __name__ == "__main__":
    main()
