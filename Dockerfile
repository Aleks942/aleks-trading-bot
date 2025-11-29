FROM python:3.10-slim

# Создаем рабочую директорию
WORKDIR /app

# Копируем файлы
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запуск бота
CMD ["python", "bot.py"]
