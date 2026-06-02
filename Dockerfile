FROM python:3.11-slim AS base

WORKDIR /app

# Make the source tree importable regardless of how a process is launched.
# `python -m app.main` works via cwd, but `python scripts/run_signal_engine.py`
# puts /app/scripts on sys.path (not /app), so `import app.*` would fail.
# Pinning PYTHONPATH=/app fixes both entrypoints without an editable install.
ENV PYTHONPATH=/app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["python", "-m", "app.main"]
