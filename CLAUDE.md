# Teplodar Bot — контекст проекта

RAG-консультант по продукции компании «Теплодар» (печи, котлы, бани). Telegram-бот + админка для управления базой знаний и оценки качества ответов.

## Архитектура

- **Telegram-бот**: aiogram 3, длинные опросы (`dp.start_polling`)
- **Админка**: FastAPI (бэк) + Vue 3 SPA (фронт, Vite)
- **БД знаний**: SQLite (`base/teplodar.db`) + numpy-индексы (`base/embeddings.npy` + `base/chunk_metadata.pkl`)
- **RAG**: гибрид BM25 + dense (E5 multilingual base, 768d) с fusion `α=0.6`, мин-макс нормализация скоров
- **LLM**: Claude CLI subprocess (Pro-подписка, не API). Переформулировка запроса — Haiku 4.5 (быстро), генерация ответа — модель по умолчанию (Opus)

## Запуск (dev)

```bash
# Бот
source venv/bin/activate && python main_bot.py

# Админка (бэк, порт 8001)
./start_admin.sh
# или: uvicorn admin.main:app --host 0.0.0.0 --port 8001 --reload

# Фронт (vite, порт 5173)
cd admin/frontend && npm run dev

# Пересборка индекса
python scripts/build_index.py --rebuild
```

**Порты:**
- 8001 — admin API (бэк)
- 5173 — admin UI (vite dev server)

## Ключевые директории

- `base/` — knowledge base этого бота: SQLite, numpy index, FAQ, dealers
- `data/` — расшаренная папка с проектом ArkadiyJarvis. Содержит `data/.claude_token.json` — OAuth токен Claude CLI с авто-рефрешем
- `bot/` — aiogram-роутеры (consultant, admin)
- `admin/` — FastAPI приложение + Vue 3 SPA (`admin/frontend/`)
- `src/rag/` — embedder, chunker, retriever, indexer, answer generator
- `src/eval/` — модели для eval-датасета (`EvalRun`, `EvalResult`)
- `src/core/claude_token.py` — авто-рефреш OAuth токена (синхронная + async версии)

## Claude CLI auth

Токен хранится в `data/.claude_token.json` (расшарено с ArkadiyJarvis). При запуске `init_token_file()` подгружает токен из env (`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_REFRESH_TOKEN`), если файла нет. Перед каждым вызовом CLI вызывается `ensure_fresh_token_sync()` — рефреш одноразовый, атомарная запись.

CLI запускается с флагами: `--print --output-format text --no-session-persistence --disallowed-tools` и `cwd="/tmp"` чтобы CLI не использовал контекст текущей директории.

## Eval / Test Dataset

50 пресет-вопросов в `admin/eval_preset.py` (5 категорий: подбор×14, характеристики×11, установка×10, компания×8, дилер×7).

**Эндпоинты** (`admin/routers/eval.py`):
- `GET /eval/dataset` — все вопросы
- `POST /eval/run` — запустить прогон (BackgroundTasks, 4 воркера ThreadPoolExecutor)
- `GET /eval/runs` — список прогонов
- `GET /eval/runs/{id}` — детали с результатами
- `GET /eval/runs/{a}/compare/{b}` — сравнение двух прогонов (delta скора, type_changes)
- `DELETE /eval/runs/{id}` — удалить

UI: `admin/frontend/src/views/EvalView.vue` — три вкладки (Датасет / Запустить / История), polling каждые 3с, прогресс-бар, сравнение прогонов.

**Параллелизм**: 4 воркера = ~8-10 мин на 50 вопросов (было ~33 мин последовательно). SQLite-записи сериализуются через `threading.Lock`.

## RAG-индекс — текущее состояние

После рефакторинга (см. ниже):
- Total chunks: **2961** (было 9511)
- Product chunks: 2191
- PDF chunks: 770 (после dedup, было 7434)

**Что сделано для качества RAG:**

1. **Near-duplicate dedup PDF-чанков** (`src/rag/simple_indexer.py:_deduplicate_pdf_chunks`):
   - Жадный алгоритм по cosine similarity на E5-эмбеддингах
   - Порог `pdf_dedup_threshold=0.92` в config
   - Удаляет boilerplate (гарантия, ТБ, общие инструкции), повторяющийся в каждом руководстве
   - На текущем датасете: 6664 / 7434 PDF-чанков ушли как near-duplicates

2. **Product chunk boost** (`src/rag/hybrid_retriever.py`):
   - После fusion BM25+dense к product-чанкам добавляется `+product_boost=0.05`
   - Защищает product-результаты от затопления нормализованными PDF-скорами
   - Конфиг: `settings.product_boost`

3. **Haiku для переформулировки** (`src/rag/query_reformulator.py`):
   - Параметр `reformulation_model` передаётся в `--model`
   - По умолчанию: `claude-haiku-4-5-20251001`
   - Экономит ~15с на запрос vs Opus

## Конфиг (`src/core/config.py`)

```python
embedding_model_name = "intfloat/multilingual-e5-base"
top_k = 8
index_version = "e5-base-v1"
device = "cpu"
pdf_dedup_threshold = 0.92
product_boost = 0.05
claude_reformulation_model = "claude-haiku-4-5-20251001"
claude_cli_path = "claude"
```

## Известные проблемы / нюансы

- **Re-индексация на CPU долгая** (~3 часа на ~9к чанков). E5 на CPU = bottleneck. На GPU будет быстрее.
- **TelegramConflictError** при повторном запуске — убить старый процесс `pgrep -f main_bot.py` → `kill <pid>`.
- **`start_admin.sh` использует порт 8001** — не 8000. Vue dev-сервер ждёт API на 8001.
- **SQLite + параллельные воркеры** — все DB-записи через общий `threading.Lock` в `_eval_one`.
- **Контекстуализация PDF-чанков** — текущий `contextualized_text` содержит имя продукта, но boilerplate всё равно ловится dedup'ом, т.к. косинус повторяющегося абзаца в разных префиксах остаётся выше 0.92.

## Что осталось сделать

- Прогнать eval run 3 после рефакторинга и сравнить с runs 1 и 2 в админке (`/eval`)
- Проверить вопрос «хочу отопительную печь для дачи небольшой» — был плохой score из-за boilerplate-доминирования; должно стать лучше.
