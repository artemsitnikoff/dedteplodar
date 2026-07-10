# Teplodar Bot — контекст проекта

RAG-консультант по продукции компании «Теплодар» (печи, котлы, бани). Telegram-бот + админка для управления базой знаний и оценки качества ответов.

## Архитектура

- **Telegram-бот**: aiogram 3, длинные опросы (`dp.start_polling`)
- **Админка**: FastAPI (бэк) + Vue 3 SPA (фронт, Vite)
- **БД знаний**: SQLite (`base/teplodar.db`) + numpy-индексы (`base/embeddings.npy` + `base/chunk_metadata.pkl`)
- **RAG**: гибрид BM25 + dense (E5 multilingual base, 768d) с fusion `α=0.6`, мин-макс нормализация скоров
- **LLM**: Claude CLI subprocess (Pro-подписка, не API). Intent extraction (всё-в-одном) — Haiku 4.5, генерация финального ответа — **Sonnet 4.6** (раньше был Opus, переключили из-за latency). OpenRouter/API mode откладывали из-за стоимости (~$390/мес на 1k запросов/день).

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
- `data/` — расшаренная папка с проектом ArkadiyJarvis (симлинк, см. «Прод-сервер»). Исторически отсюда брался общий `data/.claude_token.json`; **с релиза 1.3.x авторизация на этот файл больше не завязана** — teplodar использует свой long-lived токен из env (см. «Claude CLI auth»)
- `bot/` — aiogram-роутеры (consultant, admin)
- `admin/` — FastAPI приложение + Vue 3 SPA (`admin/frontend/`)
- `src/rag/` — embedder, chunker, retriever, indexer, answer generator
- `src/eval/` — модели для eval-датасета (`EvalRun`, `EvalResult`)
- `src/core/claude_token.py` — авторизация Claude CLI: статик long-lived токен из env (`_static_token`), защита `expiresAt` от протухания (`_safe_expires_at`) + legacy shared-file путь

## Прод-сервер (важно)

- ArkadiyJarvis уже задеплоен на проде в **`/var/www/ArkadiyJarvis`**
- Teplodarbot живёт в **`/var/www/dedteplodar`** (исторически назвали `dedteplodar`)
- Папка `data/` внутри teplodarbot — это **симлинк** на `/var/www/ArkadiyJarvis/data`, НЕ отдельная директория (историческое совместное использование токена). ⚠️ **Авторизация Claude CLI на этот общий файл больше не завязана** — teplodar самодостаточен (свой токен в `.env`, см. «Claude CLI auth»). Симлинк оставлен как есть, но для auth не нужен.
- При первом деплое: `ln -s /var/www/ArkadiyJarvis/data /var/www/dedteplodar/data` (вместо `mkdir data`)
- В docker-compose том `./data:/app/data` корректно следует через симлинк → внутри контейнера видно содержимое ArkadiyJarvis/data
- **Деплой**: `cd /var/www/dedteplodar && git pull && docker compose up -d --build bot admin`. Первая сборка после holodnog cache ~10 мин (pip install torch+transformers). Последующие — ~30с если `requirements.txt` не менялся.
- См. `DEPLOY.md` для полного чеклиста + бэкапов.

## Claude CLI auth

**Статик long-lived токен (как у ArkadyJarvis/glafiraeuro).** teplodar самодостаточен: в `.env` лежит `CLAUDE_CODE_OAUTH_TOKEN` из `claude setup-token` (живёт ~1 год), `CLAUDE_REFRESH_TOKEN` — **пустой**. Перед каждым вызовом CLI `ensure_fresh_token_sync()` через `_static_token()` берёт токен **прямо из env** (CLI читает `CLAUDE_CODE_OAUTH_TOKEN` первым) и зеркалит в `~/.claude/credentials.json` (для прямых `docker exec`-вызовов). Общий `data/.claude_token.json` при этом **не читается** — сосед (ArkadiyJarvis), ротируя его, не может нас заблокировать.

`_safe_expires_at()`: в credentials.json никогда не пишется протухший `expiresAt` (0/прошлое → клампится на +1 год), иначе CLI ругается `Not logged in · Please run /login` даже на валидном токене. Это же чинит и legacy shared-file путь.

**Legacy-режим** (в env есть refresh-токен И токен не `sk-ant-oat01-`): `ensure_fresh_token_sync()` читает access-токен из shared-файла, teplodar сам НЕ рефрешит (одноразовые токены гонятся с Jarvis). Историческая модель, оставлена для обратной совместимости.

CLI запускается с флагами `--print --output-format text --no-session-persistence --tools "" --model <id>`. **`--tools ""` = отключить ВСЕ инструменты** (белый список, airtight — CLI при генерации ответа не имеет доступа ни к Bash/Write/Edit, ни к Web; никакого RCE). Раньше был чёрный список `--disallowed-tools <перечисление>`, который падал (exit 1) при переименовании инструмента в CLI — инцидент `MultiEdit`/`SlashCommand` уронил все вызовы; ушли на whitelist как ArkadyJarvis. Каждый вызов получает **per-call `tempfile.TemporaryDirectory(prefix="claude_*")`** как `cwd` чтобы concurrent subprocess'ы не толкались на shared `/tmp`-state.

**Cross-process semaphore** (`src/core/claude_cli.py`): file-lock slot pool (`fcntl.flock`) на N=4 слотах в `/tmp/teplodar_claude_slots/`. Бот, admin (eval workers) и скрипты делят cap чтобы не задосить Pro-аккаунт. Polling-loop с `time.sleep(0.1)` (не блокирующий `LOCK_EX`). При недоступной `/tmp` — graceful degrade на uncapped с одним ERROR-логом.

**Streaming**: `_call_cli_stream` использует `subprocess.Popen(bufsize=0)` + `proc.stdout.read(4096)` в цикле, но **Claude Code CLI в `--print` режиме не стримит токены — отдаёт ответ одним блоком в конце**. Streaming-инфраструктура (Popen/Queue/edit_message_text) зашита целиком, "▌"-индикатор по факту не появляется. Если/когда перейдём на OpenRouter/API — оно сразу заработает как задумано (см. `scripts/openrouter_test.py` и `mode="api"` skeleton в `answer_generator.py`).

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

## Веб-чат (для экспертов без Telegram)

Браузерный консультант — та же RAG-логика, что и у бота, но через HTTP. Для экспертов клиента, у которых нет Telegram.

- **URL**: чат на `/`, админка переехала на **`/admin`** (роуты Vue под префиксом `/admin`, имена роутов не менялись). Всё за тем же basic-auth, что и админка.
- **Бэкенд** (`admin/routers/chat.py`, тонкий слой поверх **того же** генератора-синглтона, что у eval — `eval_service.get_eval_generator()`):
  - `POST /api/v1/chat/stream` — SSE. Claude CLI не стримит токены, поэтому шлём события **фаз** (`intent → retrieval → answer`) пока блокирующий `answer_with_meta` крутится в `asyncio.to_thread` (мост через `asyncio.Queue` + `call_soon_threadsafe`, как в боте), затем один `done` с `answer_html` + `meta` + `log_id`.
  - `POST /api/v1/chat/feedback` — `{log_id, feedback: good|bad, note?}`.
  - Логирование: каждый ход пишется в `query_logs` (Журнал) с **синтетическим отрицательным `user_id`** из `session_id` (`src/logs/queries.synthetic_user_id`, `username="web:<short>"`) — Telegram-id положительные, не пересекаются. Группировка диалога и `/journal/{id}/context` работают как для Telegram. Фоновый LLM-judge — как у бота.
- **`answer_with_meta`** получил два обратносовместимых опц. параметра: `history` (если передан — используется напрямую, минуя `get_recent_dialog`; веб-клиент шлёт последние ~6 ходов) и `on_phase` (колбэк фаз). Бот/eval их не передают — поведение не изменилось.
- **Фронт**: `views/ChatView.vue` (одна колонка как Claude.ai/ChatGPT, без списка чатов, «Новый диалог» = новый `session_id`), `components/ChatMessage.vue` (рендер ответа через `v-html` + мини-санитайзер `utils/sanitizeHtml.js` allowlist `b,i,code,a,br` + linkify URL/телефонов; 👍/👎 + инлайн-заметка на 👎; meta-чип со score/timing). `sendChatStream` в `api/index.js` — `fetch` + `ReadableStream` (не `EventSource`: нужен POST-body; basic-auth браузер цепляет сам, same-origin).
- **Прогрев**: `admin/main.py` lifespan делает фоновый `get_eval_generator()` чтобы первый чат не ждал ~30с загрузки E5+индекса. ⚠️ Следствие — admin теперь **постоянно** держит torch+E5 в RAM (раньше грузил лениво на первом eval-прогоне). На маленьком VPS вырастет RSS.
- **Деплой**: без изменений в Docker (Dockerfile stage 1 собирает фронт). `docker compose up -d --build admin`. Бот не трогаем.

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
claude_cli_path = "claude"
claude_model = "claude-sonnet-4-6"                   # финальный ответ
claude_reformulation_model = "claude-haiku-4-5-20251001"  # intent extract
claude_cli_max_concurrent = 4                         # slot pool cap
claude_cli_slots_dir = Path("/tmp/teplodar_claude_slots")
```

## Performance / reliability — что сделано (релиз 1.3.x)

Production timing на типичный RAG-вопрос (Sonnet ответ + Haiku intent):
- До оптимизаций: total **~56с** (Opus 32с + intent 22с + retrieval 1.4с)
- После: total **~30-40с** (Sonnet ~15-20с + Haiku ~10-14с)

Что закоммитили:

1. **Sonnet 4.6 вместо Opus** + проброс `--model` в `_call_cli` (раньше параметр игнорился, CLI шёл в Opus по дефолту). −10-15с.
2. **Prompt-side оптимизации** (`src/rag/answer_generator.py`):
   - `_build_full_prompt` НЕ инжектит `_FAQ_TEXT` если есть RAG-чанки (FAQ_COMPANY-путь — chunks=[] — оставляем). −0.8с.
   - `_truncate_chunk_text(text, max_chars=700)` — smart truncate с сохранением головы (2/3) и хвоста (1/3 — ТТХ/цена). −2-3с на Sonnet.
3. **E5 query LRU cache** (`src/rag/embedder.py:_query_cache`, 1000 entries, ключ нормализован через `" ".join(t.lower().split())`). Повторные запросы — 0мс вместо 500мс.
4. **Vectorized product_boost** (`src/rag/hybrid_retriever.py`): предвычисленная `_product_mask: np.float32`, заменяет Python-loop по 2961 чанку. −30-100мс.
5. **Per-phase timing breakdown** в `AnswerMeta` (`t_history_ms`, `t_intent_ms`, `t_retrieval_ms`, `t_answer_ms`, `t_answer_model`). Показывается в Telegram-футере: `⏲ intent X · ret Y · ans Z · model sonnet-4-6`. Также в логах: `[timing] total=Xms (...)` + `[answer-cli-stream] model=... rc=... ttfb=... total=... bytes=...`.

Reliability:

6. **Cross-process Claude CLI cap** (`src/core/claude_cli.py`) — fcntl slot pool, см. выше.
7. **Schema fail-fast на boot** (`src/core/migrations.py:register_schema_probe` + `assert_schema_ready(expected=[...])`). `main_bot.py` и `admin/main.py:lifespan` вызывают перед стартом — упадём с понятным RuntimeError если миграция упала, а не на первой записи.
8. **`_safe_alter` extracted** в `src/core/migrations.py`, дедуп между `logs/models.py` и `eval/models.py`. Ловит "duplicate column" / "already exists" как success в race-сценарии (бот + admin импортируют параллельно).
9. **LRU `_msg_store`** (`bot/routers/consultant.py`, OrderedDict, MAX=2000, `move_to_end` на access) — настоящая LRU. DB-recovered entries кешируются обратно чтобы повторные feedback-клики не били БД.
10. **Telegram fallback**: если финальный `edit_text(full_text, kb)` упадёт — отправляем новое сообщение БЕЗ keyboard, потом `edit_reply_markup` с правильным `message_id`. Никакого race-окна на `_feedback_kb(0)`.

## URL handling в ответах (важно)

Был баг: бот «исправлял» ссылку `kaskad_12_t/` на `kaskad<i>12</i>t/` потому что `_md_to_html` (safety net против markdown в ответе LLM) сжирал `_12_` как italic-markdown. Фикс — `_URL_RE` стэшит все `https?://...` в плейсхолдеры ДО применения markdown-rules, потом восстанавливает verbatim.

Второй баг: URL подмешивался в product-чанки ТОЛЬКО когда `intent.wants_link=True`. Когда пользователь *исправлял* ссылку («у тебя неправильная»), Haiku корректно ставил `wants_link=False`, URL не доходил до LLM, бот честно говорил «нет ссылки в базе». Фикс — `_enrich_chunks_with_product_urls` теперь вызывается **всегда** в `_handle_rag_meta` (~125 токенов overhead, мизер). System prompt уже инструктирует «если есть `Ссылка:` — обязательно используй».

## Диагностические скрипты

- `scripts/perf_diagnose.py` — собирает реальный intent+answer промпт, дампит в `/tmp/prompt_*.txt`, замеряет CLI elapsed. Usage: `docker compose exec bot python scripts/perf_diagnose.py [--query "..."]`.
- `scripts/stream_test.py` — тестирует `--output-format stream-json` на стриминг event-by-event. Подтвердило что CLI не стримит токены.
- `scripts/openrouter_test.py` — пробный SSE-стрим через OpenRouter (нужен `OPENROUTER_API_KEY`, в проде не настроен).

## Известные проблемы / нюансы

- **Re-индексация на CPU долгая** (~3 часа на ~9к чанков). E5 на CPU = bottleneck. На GPU будет быстрее.
- **TelegramConflictError** при повторном запуске — убить старый процесс `pgrep -f main_bot.py` → `kill <pid>`. В Docker — `docker compose restart bot`.
- **`start_admin.sh` использует порт 8001** — не 8000. Vue dev-сервер ждёт API на 8001.
- **SQLite + параллельные воркеры** — все DB-записи через общий `threading.Lock` в `_eval_one`.
- **Контекстуализация PDF-чанков** — текущий `contextualized_text` содержит имя продукта, но boilerplate всё равно ловится dedup'ом, т.к. косинус повторяющегося абзаца в разных префиксах остаётся выше 0.92.
- **Streaming UX** — фейковый, ждём перехода на API mode для реальных deltas. См. секцию Claude CLI auth выше.
- **Cross-container slot pool в Docker** — `bot` и `admin` это РАЗНЫЕ контейнеры с разным `/tmp`, поэтому slot pool каждый сам себе. До 8 одновременных CLI subprocess под нагрузкой. Фикс — общий named volume на `/tmp/teplodar_claude_slots` в `docker-compose.yml`. Не сделано пока трафик не вырос.

## Что осталось / возможные дальнейшие правки

- Cross-container slot pool (общий volume в `docker-compose.yml`) — когда трафик вырастет.
- INTENT_PROMPT_TPL сейчас ~2078 токенов. Можно сжать до ~1200 → -1-2с на Haiku. Нужен eval-run чтобы убедиться что классификация не упала.
- LRU кеш intent-результатов (hash(query) → Intent). Повторяющиеся вопросы (FAQ-like) отдавали бы intent мгновенно, -10-15с.
- Если перейдём на API/OpenRouter — `mode="api"` skeleton уже есть, можно подключить prompt caching на статичный префикс (system+FAQ), ~−3-5с на cache hit.
