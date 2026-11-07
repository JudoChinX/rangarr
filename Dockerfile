FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY rangarr/ ./rangarr/
COPY config.example.yaml .

FROM gcr.io/distroless/python3-debian13

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/venv/lib/python3.13/site-packages

WORKDIR /app

COPY --from=builder /venv/lib/python3.13/site-packages /venv/lib/python3.13/site-packages
COPY --from=builder /app /app

USER nonroot

CMD ["-m", "rangarr.main"]
