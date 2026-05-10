#!/bin/bash
# Скрипт запуска админки Teplodar

echo "🚀 Запуск Teplodar Admin API..."

# Проверяем, что venv существует
if [ ! -d "venv" ]; then
    echo "❌ Виртуальное окружение venv не найдено"
    exit 1
fi

# Проверяем, что FastAPI установлен
if ! venv/bin/python -c "import fastapi" 2>/dev/null; then
    echo "📦 Установка зависимостей..."
    venv/bin/pip install fastapi uvicorn python-multipart
fi

# Устанавливаем PYTHONPATH и запускаем сервер
export PYTHONPATH="$(pwd)"

echo "🌐 Сервер будет доступен по адресу:"
echo "   http://localhost:8001"
echo "   http://localhost:8001/docs (Swagger)"
echo ""
echo "Нажмите Ctrl+C для остановки"
echo ""

# Запуск с перезагрузкой при изменениях
venv/bin/uvicorn admin.main:app --host 0.0.0.0 --port 8001 --reload