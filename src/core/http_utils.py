"""Shared HTTP utilities for async request handling.

Provides a reusable async retry wrapper for httpx requests
with exponential backoff.
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def async_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = 3,
    backoff_base: int = 2,
    **kwargs,
) -> httpx.Response:
    """Async retry wrapper for httpx requests.

    Args:
        client: httpx AsyncClient instance
        method: HTTP method ('get', 'post', etc.)
        url: Request URL
        max_retries: Maximum number of attempts
        backoff_base: Base for exponential backoff
        **kwargs: Additional arguments passed to the request method

    Returns:
        httpx.Response

    Raises:
        Last exception if all retries fail
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            response = await getattr(client, method)(url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min(backoff_base ** attempt, 30)
                logger.warning(
                    f"HTTP request failed (attempt {attempt + 1}/{max_retries}): {e}, "
                    f"retrying in {wait}s"
                )
                await asyncio.sleep(wait)
    raise last_error
