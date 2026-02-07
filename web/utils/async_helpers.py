"""Async Helpers for Streamlit.

Streamlit 환경에서 비동기 함수를 실행하기 위한 헬퍼 함수들.
모든 페이지에서 이 모듈을 import하여 사용하세요.
"""

import asyncio
from typing import TypeVar, Coroutine, Any

T = TypeVar('T')


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run async function in Streamlit.

    Streamlit의 이벤트 루프와 충돌을 피하기 위해
    새로운 이벤트 루프를 생성하여 코루틴을 실행합니다.

    Args:
        coro: 실행할 코루틴

    Returns:
        코루틴의 실행 결과

    Example:
        ```python
        from utils.async_helpers import run_async

        result = run_async(server.list_documents())
        ```
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_async_with_timeout(coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
    """Run async function with timeout.

    Args:
        coro: 실행할 코루틴
        timeout: 타임아웃 (초, 기본값 30초)

    Returns:
        코루틴의 실행 결과

    Raises:
        asyncio.TimeoutError: 타임아웃 초과 시
    """
    async def with_timeout():
        return await asyncio.wait_for(coro, timeout=timeout)

    return run_async(with_timeout())
