FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc libffi-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .
RUN mkdir -p data/uploads data/processed data/chroma

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
