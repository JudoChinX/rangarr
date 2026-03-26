FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

COPY rangarr/ ./rangarr/
COPY config.example.yaml .

FROM gcr.io/distroless/python3-debian13

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/install/lib/python3.13/site-packages

WORKDIR /app

COPY --from=builder /install /install
COPY --from=builder /app /app

USER nonroot

CMD ["-m", "rangarr.main"]
