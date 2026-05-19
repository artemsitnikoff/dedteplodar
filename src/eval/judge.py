"""LLM-as-judge: score how useful a bot answer was to the client.

Why: formal `expected_type == actual_type` matching misses real quality
— a FAQ_DEALER answer that lists actual stores in the city the user
named is more useful than a "correct-type" FAQ_COMPANY canned reply.

The judge reads the question + bot's answer + brief catalog context
and returns:
  usefulness_score: 0–100
  verdict:          one short sentence why
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

LLM_TIMEOUT = 30  # seconds — judge call

_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)

_PROMPT = """Ты — асессор ответов AI-консультанта компании «Теплодар» (печи, котлы, камины).
Оцени, насколько ответ бота ПОЛЕЗЕН для клиента — то есть содержит ли он информацию,
которую клиент реально хотел получить.

ВОПРОС КЛИЕНТА:
{question}

ОТВЕТ БОТА:
{answer}

Критерии оценки usefulness_score:
- 90-100: точный, конкретный, по делу. Клиент получил именно то что хотел.
  Например: упомянул город → дали реальные адреса дилеров; спросил про модель → дали характеристики.
- 70-89: правильное направление, но не вся информация / расплывчато / общие фразы вместо конкретики.
- 40-69: ответ касается темы, но не отвечает на конкретный вопрос. Полу-помощь.
- 10-39: бот ушёл в сторону / переадресовал когда мог ответить сам / выдумал факты / canned "позвоните по 8-800".
- 0-9: ответ совершенно нерелевантный, или ошибка.

ВАЖНО:
- Эскалация на оператора при ЛИЧНОМ вопросе (про мой заказ / мою посылку) — это ПРАВИЛЬНО (80-95), не штрафуй.
- Эскалация на оператора при ОБЩЕМ вопросе, на который можно было ответить из FAQ/каталога — штраф (20-50).
- Если бот честно сказал «такой модели нет» при отсутствии в каталоге — это полезно (75-90).
- Если бот ВЫДУМАЛ модель/факты — резкий штраф (0-20).
- Длина ответа не важна — оценивай ПОЛЬЗУ для клиента.

Верни СТРОГО JSON без markdown-fence:
{{"score": <0-100>, "verdict": "<одна короткая фраза, до 200 символов, почему такая оценка>"}}
"""

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def judge_answer(
    question: str,
    answer: str,
    cli_path: str = "claude",
    model: str = "",
) -> Optional[dict]:
    """Return {"score": int, "verdict": str} or None on failure."""
    from src.core.claude_token import ensure_fresh_token_sync
    ensure_fresh_token_sync()

    prompt = _PROMPT.format(question=question.strip(), answer=(answer or "").strip())

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    args = [cli_path, "--print", "--output-format", "text",
            "--no-session-persistence",
            "--disallowed-tools", _DISALLOWED_TOOLS]
    if model:
        args += ["--model", model]

    from src.core.claude_cli import claude_cli_slot
    try:
        # Isolated cwd per call + global cross-process slot lock so we
        # don't fan out 20 concurrent CLI procs against the Pro account.
        with claude_cli_slot(), tempfile.TemporaryDirectory(prefix="claude_judge_") as cwd:
            result = subprocess.run(
                args, input=prompt.encode(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=cwd, timeout=LLM_TIMEOUT,
            )
            text = result.stdout.decode().strip()
    except Exception as e:
        logger.warning("judge subprocess failed: %s", e)
        return None

    if result.returncode != 0 or not text:
        logger.warning("judge returned no output (rc=%s)", result.returncode)
        return None

    m = _JSON_BLOCK_RE.search(text)
    if not m:
        logger.warning("judge: no JSON in output %r", text[:200])
        return None

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        logger.warning("judge: bad JSON (%s) — %r", e, m.group(0)[:200])
        return None

    score = data.get("score")
    verdict = data.get("verdict") or ""
    if not isinstance(score, (int, float)):
        logger.warning("judge: score not numeric: %r", score)
        return None

    score = max(0, min(100, int(score)))
    verdict = str(verdict)[:500]
    return {"score": score, "verdict": verdict}
