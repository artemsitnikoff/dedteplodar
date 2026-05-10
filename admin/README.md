# Teplodar Admin API

FastAPI бэкенд для веб-администратора RAG базы знаний Теплодар.

## Структура

```
admin/
├── main.py                  # FastAPI приложение
├── dependencies.py          # Общие зависимости (get_db)
├── schemas/                 # Pydantic схемы
│   ├── products.py
│   ├── categories.py
│   ├── documents.py
│   ├── chunks.py
│   └── pipeline.py
└── routers/                 # API роутеры
    ├── products.py         # CRUD продуктов
    ├── categories.py       # Дерево категорий
    ├── documents.py        # Документы + загрузка PDF
    ├── chunks.py           # RAG чанки
    ├── faq.py             # Редактирование YAML файлов
    └── pipeline.py        # Импорт YML, ребилд индекса
```

## Запуск

```bash
# Установить зависимости
venv/bin/pip install fastapi uvicorn python-multipart

# Запустить сервер
cd /Users/artemsitnikov/claudeproject/teplodarbot
PYTHONPATH=. venv/bin/uvicorn admin.main:app --host 0.0.0.0 --port 8001 --reload
```

## API endpoints

Все эндпоинты под `/api/v1`.

### Продукты `/products`
- `GET /` — список с фильтрацией и пагинацией
- `GET /{id}` — детали со всеми параметрами и чанками
- `PATCH /{id}` — обновление полей
- `DELETE /{id}` — удаление с каскадом
- `GET /{id}/chunks` — чанки продукта

### Категории `/categories`
- `GET /tree` — иерархическое дерево
- `GET /{id}/products` — продукты категории

### Документы `/documents`
- `GET /` — список с фильтрацией
- `GET /{id}` — детали с превью текста (2000 символов)
- `DELETE /{id}` — удаление
- `POST /upload` — загрузка PDF в `data/pdfs/`

### Чанки `/chunks`
- `GET /` — список с фильтрацией по типу, продукту, версии индекса
- `GET /{id}` — полный текст чанка
- `DELETE /{id}` — удаление

### FAQ `/faq`
- `GET /company` — содержимое `data/company_faq.yaml`
- `PUT /company` — сохранение с валидацией YAML
- `GET /dealers` — содержимое `data/dealers.yaml`
- `PUT /dealers` — сохранение

### Пайплайн `/pipeline`
- `GET /stats` — статистика БД
- `POST /import-yml` — загрузка YML каталога (фоновая задача)
- `POST /rebuild-index` — перестройка индекса (фоновая задача)
- `GET /tasks/{task_id}` — статус фоновой задачи

## Документация

После запуска доступна по адресам:
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## Тест

```bash
PYTHONPATH=. venv/bin/python test_admin_api.py
```