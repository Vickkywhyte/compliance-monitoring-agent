# Multi-stage build — Phase 10 (ADR-013)
# Stage 1: builder installs all Python dependencies into site-packages.
# Stage 2: runtime copies only the installed site-packages + app code;
#           installs CPU-only torch separately to keep the image lean.
# Image size target: < 3 GB

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency manifests first so Docker caches the deps layer
# independently of source changes.
COPY pyproject.toml requirements.lock ./
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.lock

# Copy source before editable install — src/ must exist for `pip install -e .`
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# System dependencies required by the application
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        curl \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Application code — only what is needed at runtime
COPY src/       ./src/
COPY configs/   ./configs/
COPY scripts/   ./scripts/
COPY data/kb/   ./data/kb/
COPY data/demo/ ./data/demo/
COPY data/eval/ ./data/eval/

# CPU-only torch (ADR-013): install after copying app code so the layer
# is shared across rebuilds that don't change torch.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Non-root user for defence-in-depth
RUN useradd --create-home --uid 1000 agent \
 && chown -R agent:agent /app
USER agent

EXPOSE 8000 8501

CMD ["streamlit", "run", "src/compliance_agent/dashboard/app.py", \
     "--server.port", "8501", "--server.address", "0.0.0.0"]
