FROM python:3.12-slim

LABEL maintainer="Spine GraphRAG Team"
LABEL version="7.16.0"
LABEL description="Spine GraphRAG MCP Server - Medical Literature Knowledge Graph"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code (also bind-mounted at runtime for editing)
COPY src/ /app/src/
COPY config/ /app/config/
COPY scripts/ /app/scripts/
COPY data/styles/ /app/data/styles/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 7777

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7777/health || exit 1

CMD ["python", "-m", "medical_mcp.sse_server", "--host", "0.0.0.0", "--port", "7777"]
