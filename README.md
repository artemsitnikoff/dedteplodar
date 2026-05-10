# Teplodar Knowledge Base Ingestion Pipeline

Система ingestion для базы знаний Telegram-бота компании "Теплодар" (печи, котлы, дымоходы).

## Установка

```bash
# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или .venv\Scripts\activate  # Windows

# Установить зависимости
pip install -e .

# Настроить переменные окружения
cp .env.example .env
```

## Запуск пайплайна

### 1. Парсинг YML каталога
```bash
python scripts/ingest_yml.py
# или с указанием файла:
# python scripts/ingest_yml.py path/to/custom.xml
```

### 2. Скрейпинг страниц товаров
```bash
# Тестовый запуск (5 товаров)
python scripts/scrape_products.py --limit 5

# Полный запуск всех неотскрейпленных товаров
python scripts/scrape_products.py --limit 0

# Принудительный перескрейп
python scripts/scrape_products.py --force
```

### 3. Парсинг PDF документов
```bash
# Тестовый запуск (5 PDF)
python scripts/parse_pdfs.py --limit 5

# Все необработанные PDF
python scripts/parse_pdfs.py --limit 0
```

## Схема базы данных

| Таблица | Назначение |
|---------|------------|
| `categories` | Иерархия категорий из YML (id, name, parent_id) |
| `products` | Товары из YML + скрейпленные данные (url, name, price, scraped_full_description, scraped_at) |
| `product_params` | Параметры товаров (топливо, материал, габариты) |
| `documents` | PDF инструкции и HTML контент (doc_type, source_url, full_text, char_count) |

## Структура проекта

```
src/
├── core/           # Общие настройки, БД, логирование
├── products/       # Модели товаров и категорий
├── documents/      # Модели документов
└── ingestion/      # Парсеры YML, HTML, PDF

scripts/            # CLI точки входа
data/               # SQLite база и кешированные PDF
```

## Что дальше

- Векторизация текстов (эмбеддинги)
- FastAPI сервис для RAG поиска
- Telegram бот интерфейс