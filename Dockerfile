FROM python:3.10-slim

# Настройка пользователя под требования Hugging Face
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Установка зависимостей
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Копирование остальных файлов проекта
COPY --chown=user . .

# Запуск бота
CMD ["python", "bot.py"]
