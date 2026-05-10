#!/usr/bin/env python3
"""Interactive CLI chat with the Teplodar bot.

Usage:
  python scripts/chat.py           # CLI mode (Pro subscription)
  python scripts/chat.py --api     # API mode (requires ANTHROPIC_API_KEY)
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
logging.disable(logging.CRITICAL)

from src.core.config import settings
from src.core.database import SessionLocal
from src.rag.embedder import E5Embedder
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.answer_generator import AnswerGenerator

BANNER = """\
╔══════════════════════════════════════════════════════╗
║       Теплодар — консультант (demo)                  ║
║  Введите вопрос или 'exit' для выхода                ║
╚══════════════════════════════════════════════════════╝"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="Use Anthropic API instead of CLI")
    args = parser.parse_args()

    mode = "api" if args.api else "cli"

    print(f"Загрузка эмбеддинг-модели… (режим: {mode})", end=" ", flush=True)
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = HybridRetriever(embedder=embedder, index_version=settings.index_version)
    gen = AnswerGenerator(retriever=retriever, mode=mode)
    print("готово.")

    print(BANNER)

    with SessionLocal() as session:
        while True:
            try:
                query = input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nДо свидания!")
                break

            if not query:
                continue
            if query.lower() in ("exit", "quit", "выход"):
                print("До свидания!")
                break

            print("Бот: ", end="", flush=True)
            try:
                for chunk in gen.stream(session, query):
                    print(chunk, end="", flush=True)
            except KeyboardInterrupt:
                pass
            except Exception as e:
                print(f"\n[ошибка: {e}]")
            print()


if __name__ == "__main__":
    main()
