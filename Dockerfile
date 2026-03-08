FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY main.py /app/main.py
COPY main_api.py /app/main_api.py
COPY config.yaml /app/config.yaml

RUN python -m pip install --upgrade pip \
    && pip install .

FROM base AS dev

RUN pip install ".[dev]"

FROM base AS runtime

CMD ["python", "main_api.py"]
