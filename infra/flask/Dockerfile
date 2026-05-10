FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY infra/flask/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY Atividade-3/backend/ /app/backend/
COPY Atividade-3/frontend/ /app/frontend/

WORKDIR /app/backend

EXPOSE 8181

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8181", "--access-logfile", "-", "app:app"]