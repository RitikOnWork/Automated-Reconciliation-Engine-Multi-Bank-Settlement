# ==============================================================================
# Stage 1: Build Dependencies
# ==============================================================================
FROM python:3.10-slim AS builder

WORKDIR /workspace

# Prevent python from writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies for postgres and general compiling
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies in the user local directory
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ==============================================================================
# Stage 2: Runtime Runner
# ==============================================================================
FROM python:3.10-slim AS runner

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install runtime PostgreSQL client library
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed site-packages and binaries from builder stage
COPY --from=builder /root/.local /root/.local
COPY . /workspace

# Update PATH to prioritize installed binaries
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8000

# Run uvicorn server mapping standard docker ports
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
