"""Query reformulation: convert conversational user query into a retrieval-optimised form."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
Перефразируй вопрос покупателя в технический поисковый запрос для базы знаний \
по отопительному оборудованию.

Правила:
- Ответь ТОЛЬКО одним поисковым запросом, без пояснений и кавычек
- 1–2 предложения максимум
- НЕ добавляй названия брендов, моделей, серий или производителей, которых нет в вопросе
- Разговорные выражения → технические термины: \
баня/парилка → объём парилки кубических метров, кв → м², квадраты → площадь, \
долго горит → режим длительного горения, обжечь → первая растопка
- Если в вопросе про баню/парилку упоминают «котёл» — это банная печь, не котёл отопления
- Сохраняй цифры, размеры и параметры из вопроса дословно
- Сохраняй названия моделей, если они явно названы в вопросе

Вопрос покупателя: {query}
Поисковый запрос:"""


def reformulate(query: str, cli_path: str = "claude", model: str = "") -> str:
    """Return a retrieval-optimised version of the query via Claude CLI.

    Falls back to the original query on any error so retrieval is never blocked.
    Uses a fast model (Haiku by default) since this is a simple rewrite task.
    """
    from ..core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    prompt = _PROMPT_TEMPLATE.format(query=query)

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    args = [
        cli_path, "--print", "--output-format", "text",
        "--no-session-persistence",
        "--tools", "",
    ]
    if model:
        args += ["--model", model]

    from src.core.claude_cli import claude_cli_slot
    try:
        with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_reform_") as cwd:
            result = subprocess.run(
                args,
                input=prompt.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cwd,
                timeout=30,
            )
            text = result.stdout.decode().strip()
        if result.returncode == 0 and text:
            text = text.strip('"\'')
            logger.debug("Reformulated: %r → %r", query[:50], text[:80])
            return text
    except Exception as e:
        logger.warning("Reformulation failed (%s), using original query", e)

    return query
