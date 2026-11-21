FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py .

ENV PORT=8002
EXPOSE 8002

CMD ["python", "runner.py"]
