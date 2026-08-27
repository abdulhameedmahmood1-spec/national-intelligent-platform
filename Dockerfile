FROM python:3.12-slim

WORKDIR /opt/render/project/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
