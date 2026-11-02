# The app image: code, config, DESIGN.md (the About page) and 1 serve bundle.
# The bundle lives under $SIS_DATA, outside the repo, so it comes in as a named build context:
#   docker build --build-context bundle="$SIS_DATA/serve/<version>" -t sis .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY sis ./sis
COPY config ./config
COPY DESIGN.md ./
RUN uv sync --frozen --no-dev

COPY --from=bundle . /app/bundle

ENV PATH="/app/.venv/bin:$PATH" \
    SIS_BUNDLE_DIR=/app/bundle \
    SIS_DATA=/app/data \
    DUCKDB_MEMORY_LIMIT=512MB \
    DUCKDB_THREADS=2
EXPOSE 8000
# Fly terminates TLS at its proxy; trust its X-Forwarded-Proto so url_for() builds https URLs
# (without it the stylesheet link is http:// and the browser blocks it as mixed content).
CMD ["uvicorn", "sis.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
