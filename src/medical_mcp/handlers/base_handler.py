"""Base handler for Medical KAG MCP Server handlers.

Provides common functionality shared across all handlers:
- Server reference and Neo4j client access
- Standardized error handling with _safe_execute decorator
- Neo4j availability and connection guards
- Consistent response formatting
"""

import logging
import functools
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

logger = logging.getLogger("medical-kag")


class BaseHandler:
    """Base class for all MCP server handlers."""

    def __init__(self, server: "MedicalKAGServer"):
        self.server = server

    @property
    def neo4j_client(self):
        """Access Neo4j client from server (always current)."""
        return self.server.neo4j_client

    def _require_neo4j(self) -> None:
        """Check that neo4j_client is available. Raises ValueError if not."""
        if not self.neo4j_client:
            raise ValueError("Neo4j client not available")

    async def _ensure_connected(self) -> None:
        """Ensure Neo4j connection is established."""
        self._require_neo4j()
        if not self.neo4j_client._driver:
            await self.neo4j_client.connect()

    @staticmethod
    def _format_error(error: str, **kwargs) -> dict:
        """Format standardized error response."""
        result = {"success": False, "error": error}
        result.update(kwargs)
        return result

    @staticmethod
    def _format_success(data: dict, **kwargs) -> dict:
        """Format standardized success response."""
        result = {"success": True}
        result.update(data)
        result.update(kwargs)
        return result


def safe_execute(func: Callable) -> Callable:
    """Decorator for standardized error handling in handler methods.

    Wraps async handler methods with try/except, logging, and error response formatting.
    """
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except ValueError as e:
            # Expected validation errors (e.g., _require_neo4j)
            logger.warning(f"{self.__class__.__name__}.{func.__name__}: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception(f"{self.__class__.__name__}.{func.__name__} error: {e}")
            return {"success": False, "error": str(e)}
    return wrapper
