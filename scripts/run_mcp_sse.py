#!/usr/bin/env python3
"""Medical KAG MCP Server - SSE Mode (Wrapper).

이 스크립트는 src/medical_mcp/sse_server.py의 래퍼입니다.
전체 기능(멀티유저, 연결 관리, 재연결 등)은 sse_server.py에서 제공합니다.

Usage:
    # 권장: sse_server.py 직접 실행
    python -m medical_mcp.sse_server --port 8000

    # 또는 이 스크립트 사용 (동일 기능)
    python scripts/run_mcp_sse.py --port 8000

Options:
    --host      Host to bind to (default: 0.0.0.0)
    --port      Port to bind to (default: 8000)
    --heartbeat Heartbeat interval in seconds (default: 30)
    --timeout   Connection timeout in seconds (default: 300)

Endpoints:
    GET  /sse         - SSE connection (add ?user=<id> for multi-user)
    POST /messages    - MCP message handling
    GET  /health      - Health check with connection stats
    GET  /ping        - Simple ping
    GET  /tools       - List available MCP tools
    GET  /users       - List registered users
    POST /users/add   - Add new user (admin only)
    GET  /connections - Connection statistics
    POST /reset       - Reset server cache (reconnection support)
    POST /restart     - Restart Neo4j connection

Multi-User Support:
    1. URL parameter: /sse?user=kim
    2. HTTP header: X-User-ID: kim
    3. Default: system (all document access)

Version: 1.14.28 (Unified SSE Server)
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[SSE Server] .env loaded from: {env_path}")
except ImportError:
    print("[SSE Server] python-dotenv not installed")


def main():
    """Run SSE server using medical_mcp.sse_server."""
    # Import and run the main SSE server
    from medical_mcp.sse_server import main as sse_main
    asyncio.run(sse_main())


if __name__ == "__main__":
    main()
