# ── stage 1: dependências ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

# ── stage 2: runtime ──────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Cria usuário sem privilégios
RUN addgroup --system app && adduser --system --ingroup app app

# Copia venv
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copia código
COPY src/ ./src/
COPY data/ ./data/

# Diretórios com permissão de escrita
RUN mkdir -p data/audio data/reports && chown -R app:app /app

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import src.core.config; src.core.config.get_settings()" || exit 1

CMD ["python", "-m", "src.bot.main"]
