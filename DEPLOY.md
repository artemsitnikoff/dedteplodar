# Деплой Teplodarbot

Два сервиса в одном `docker-compose`:
- **bot** — Telegram-бот (`main_bot.py`), без публичных портов
- **admin** — FastAPI + Vue SPA (вебморда) на `:8001`

Оба делят:
- `./base` — база знаний (SQLite, эмбеддинги, PDF, FAQ)
- `./data` — **shared с ArkadiyJarvis** (Claude OAuth-токен `data/.claude_token.json`)
- `hf_cache` — кэш HuggingFace (named volume)

## Требования к серверу

- Docker + Docker Compose
- ~5 ГБ свободно (E5 модель ~1 ГБ, индекс эмбеддингов, PDF-ы)
- Доступ к `api.telegram.org`, `huggingface.co`, `api.anthropic.com`

## Первоначальная установка

### 1. Клонировать и настроить .env

```bash
git clone <repo> teplodarbot
cd teplodarbot
cp .env.example .env
nano .env   # минимум: BOT_TOKEN, OPERATOR_CHAT_ID, CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_REFRESH_TOKEN
```

### 2. Перенести базу знаний с Mac (папка base/)

```bash
# На Mac:
scp base/teplodar.db                  user@server:~/teplodarbot/base/
scp base/embeddings_e5-base-v1.npy    user@server:~/teplodarbot/base/
scp base/metadata_e5-base-v1.pkl      user@server:~/teplodarbot/base/
scp base/company_faq.yaml             user@server:~/teplodarbot/base/
scp base/dealers.yaml                 user@server:~/teplodarbot/base/
scp -r base/pdfs                      user@server:~/teplodarbot/base/  # большие
```

### 3. Настроить shared data/ с ArkadiyJarvis

Если ArkadiyJarvis уже запущен на сервере — просто укажи один и тот же путь к `data/`:

```bash
# Если teplodarbot рядом с ArkadiyJarvis:
ln -s ~/ArkadyJarvis/data ~/teplodarbot/data
# или просто создай папку и скопируй токен:
mkdir -p data
cp ~/ArkadyJarvis/data/.claude_token.json data/ 2>/dev/null || true
```

### 4. Запустить

```bash
docker compose up -d --build
```

Первый запуск долгий (~3–5 мин: сборка образа + загрузка HF модели в кэш).

После старта `init_token_file()` автоматически прочитает `CLAUDE_CODE_OAUTH_TOKEN` /
`CLAUDE_REFRESH_TOKEN` из `.env` и сохранит в `data/.claude_token.json` (если файла ещё нет).
Дальше токен обновляется автоматически перед каждым запросом к Claude CLI.

### 5. Проверка

```bash
curl localhost:8001/health
docker compose logs -f bot
docker compose logs -f admin
```

Вебморда: `http://server:8001` (или поставь nginx сверху).

## Обновление

```bash
cd ~/teplodarbot && git pull && docker compose up -d --build
```

## Полезные команды

```bash
docker compose logs -f bot          # логи бота
docker compose logs -f admin        # логи админки
docker compose restart bot          # рестарт без пересборки
docker compose down                 # остановить всё
docker compose ps                   # статус
docker compose exec bot bash        # шелл в боте
```

## Бэкап

База знаний в `./base/`:

```bash
scp user@server:~/teplodarbot/base/teplodar.db ./backup_$(date +%Y%m%d).db
```

Claude-токен в `./data/.claude_token.json` — его трогать не нужно (автообновляется).

## Структура томов

```
base/
  teplodar.db               # SQLite: товары, чанки, журнал запросов, FAQ
  embeddings_e5-base-v1.npy # векторный индекс
  metadata_e5-base-v1.pkl   # метаданные чанков
  company_faq.yaml           # FAQ компании
  dealers.yaml               # дилерская сеть
  pdfs/                      # PDF инструкции
  feedback.jsonl             # лог обратной связи от пользователей

data/                        # shared с ArkadiyJarvis
  .claude_token.json         # Claude OAuth токен (автообновляется)
```
