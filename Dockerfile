FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY database/ ./database/

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser

USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]