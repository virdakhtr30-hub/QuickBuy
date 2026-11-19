
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir flask "psycopg[binary]" pika

COPY app.py consumer.py ./

EXPOSE 5003

CMD ["python", "app.py"]
