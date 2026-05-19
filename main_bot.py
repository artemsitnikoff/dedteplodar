#!/usr/bin/env python3
"""Teplodar Telegram bot entry point.

Usage:
    python main_bot.py
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("teplodarbot")

from src.core.config import settings

if not settings.bot_token:
    logger.error("BOT_TOKEN not set in .env")
    sys.exit(1)


async def main() -> None:
    # Seed Claude OAuth token from env vars (no-op if data/.claude_token.json already exists)
    from src.core.claude_token import init_token_file
    init_token_file()

    # Touch model modules so their import-time schema init runs, then verify
    # every probe reported OK. Fail-fast here is preferable to crashing on
    # the first user query against a broken schema.
    import src.logs.models  # noqa: F401
    import src.eval.models  # noqa: F401
    from src.core.migrations import assert_schema_ready
    assert_schema_ready(expected=["query_logs", "eval"])

    # Load heavy models once at startup
    logger.info("Loading embedding model…")
    from src.rag.embedder import E5Embedder
    from src.rag.hybrid_retriever import HybridRetriever
    from src.rag.answer_generator import AnswerGenerator
    from bot.routers.consultant import init_generator

    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = HybridRetriever(
        embedder=embedder,
        index_version=settings.index_version,
        data_dir="base",
        product_boost=settings.product_boost,
    )

    from src.faq.matcher import FaqMatcher
    faq_matcher = FaqMatcher(
        embedder=embedder,
        cli_path=settings.claude_cli_path,
        llm_model=settings.claude_reformulation_model,
    )

    generator = AnswerGenerator(
        retriever=retriever,
        mode="cli",
        cli_path=settings.claude_cli_path,
        model=settings.claude_model,                       # final answer (Sonnet)
        reformulation_model=settings.claude_reformulation_model,  # intent (Haiku)
        faq_matcher=faq_matcher,
    )
    init_generator(generator)
    logger.info("Models loaded.")

    from bot.create import create_bot, create_dispatcher
    from bot.middlewares import ErrorMiddleware

    bot = create_bot()
    dp = create_dispatcher()

    dp.message.outer_middleware(ErrorMiddleware())
    dp.callback_query.outer_middleware(ErrorMiddleware())

    me = await bot.get_me()
    logger.info("Bot started: @%s (id=%s)", me.username, me.id)
    logger.info("Mode: CLI (Pro subscription)")

    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
