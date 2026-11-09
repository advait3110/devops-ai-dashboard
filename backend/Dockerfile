# ---------------------------------------------------------------
# Backend image (multi-stage).
#   docker build -t devops-ai-backend:latest ./backend      -> runtime image (~150 MB)
#   docker build --target test ./backend                     -> runs the test suite (used by CI)
# ---------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer stays cached until requirements change,
# so code edits rebuild in seconds.
COPY requirements.txt .
RUN pip install -r requirements.txt
# boto3 (~80 MB) is only installed when the AWS module is wanted:
#   docker build --build-arg INSTALL_AWS=true ...
ARG INSTALL_AWS=false
RUN if [ "$INSTALL_AWS" = "true" ]; then pip install "boto3>=1.35"; fi

# ---- test stage: only used by CI, never shipped ----------------
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install -r requirements-dev.txt
COPY app ./app
COPY tests ./tests
RUN ruff check app tests && pytest -q

# ---- runtime stage ----------------------------------------------
FROM base AS runtime
COPY app ./app
COPY main.py .

# Run as a non-root user (security best practice). When the Docker socket is
# mounted, compose adds the socket's group with group_add.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/logs \
    && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
