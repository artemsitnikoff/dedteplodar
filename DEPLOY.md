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
            # Bitrix24 (если включаем вебхук): B24_APPLICATION_TOKEN, B24_BOT_ID — см. BITRIX24.md
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

ArkadiyJarvis на проде живёт в **`/var/www/ArkadiyJarvis`**. Папка `data/` внутри teplodarbot должна быть симлинком на data ArkadiyJarvis — НЕ создавай `mkdir data`, иначе будут два независимых OAuth-токена и они затрут друг друга при рефреше.

```bash
# Симлинк на data ArkadiyJarvis (сделать ОДИН раз при первом деплое):
ln -s /var/www/ArkadiyJarvis/data ./data

# Проверить, что симлинк работает и токен виден:
ls -la data/.claude_token.json
```

Если ArkadiyJarvis ещё не задеплоен — поднимай его первым (он первичный держатель токена), потом симлинкуй сюда.

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
curl localhost:8001/api/v1/b24/events   # вебхук Bitrix24, без auth → {"ok":true,...}
docker compose logs -f bot
docker compose logs -f admin
```

Вебморда: `http://server:8001` (или поставь nginx сверху).

## Обновление

```bash
cd ~/teplodarbot && git pull && docker compose up -d --build
```

## Синхронизация каталога с сайтом (cron)

Товары приходят из YML-фида сайта (`YANDEX_YML_URL` в `.env`, ссылка от контент-менеджера
Теплодара; Битрикс пересобирает файл сам). `scripts/sync_catalog.py` скачивает фид, добавляет
новые товары, читает их страницы и PDF и **инкрементально** обновляет индекс (минуты, а не
3 часа полной пересборки). Бот и админка подхватывают новый индекс сами, без рестарта.

Ставится на хост (не в контейнер), один раз после деплоя:

```bash
crontab -e
# каждую ночь в 04:30
30 4 * * * /var/www/dedteplodar/scripts/cron/sync_catalog.sh
```

Лог — `logs/catalog_sync.log`, итог прилетает в Telegram в `OPERATOR_CHAT_ID`, последний
прогон виден в админке на странице «Конвейер» (там же кнопка «Обновить каталог сейчас»).

Ручной запуск и проверка:

```bash
docker compose exec admin python scripts/sync_catalog.py --dry-run   # только показать разницу
docker compose exec admin python scripts/sync_catalog.py             # полный цикл
docker compose exec admin python scripts/sync_catalog.py --file base/upload_latest.xml  # из файла
```

Первый запуск на старой базе: индекс должен уже существовать (`embeddings_*.npy`), иначе
скрипт попросит `python scripts/build_index.py --rebuild`. Защита от битого фида: если в
фиде меньше половины активных товаров (`CATALOG_SYNC_MIN_RATIO`), ничего не меняется.

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
