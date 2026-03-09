"""Medical KAG MCP Server entry point.

python -m medical_mcp 으로 실행 가능하게 함.
"""

import asyncio
from .medical_kag_server import main

if __name__ == "__main__":
    asyncio.run(main())
