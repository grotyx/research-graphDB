"""Base handler for Medical KAG MCP Server handlers.

Provides common functionality shared across all handlers:
- Server reference and Neo4j client access
- Standardized error handling with _safe_execute decorator
- Neo4j availability and connection guards
- Consistent response formatting
"""

import logging
import functools
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

from core.exceptions import Neo4jError, ValidationError, ErrorCode

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
            raise Neo4jError(message="Neo4j client not available", error_code=ErrorCode.NEO4J_CONNECTION)

    async def _ensure_connected(self) -> None:
        """Ensure Neo4j connection is established."""
        self._require_neo4j()
        if not self.neo4j_client._driver:
            await self.neo4j_client.connect()

    def validate_file_path(self, file_path: str) -> tuple[Optional[Path], Optional[dict]]:
        """Validate file path against allowed directories (path traversal defense).

        Resolves the path and checks it falls within allowed directories
        (project data dir + cwd).

        Args:
            file_path: Raw file path string to validate.

        Returns:
            (resolved_path, None) if valid, or (None, error_dict) if blocked.
        """
        path = Path(file_path).resolve()

        # v1.15: Path traversal 방지 — 허용 디렉토리 검증
        allowed_dirs = [
            Path(self.server.project_root / "data").resolve() if hasattr(self.server, 'project_root') else None,
            Path.cwd().resolve(),
        ]
        if not any(d and path.is_relative_to(d) for d in allowed_dirs if d):
            logger.warning(f"Path traversal attempt blocked: {file_path}")
            return None, {"success": False, "error": "접근 불가: 허용된 디렉토리 외부 경로입니다"}

        return path, None

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
        except (ValueError, Neo4jError, ValidationError) as e:
            # Expected validation errors (e.g., _require_neo4j)
            logger.warning(f"{self.__class__.__name__}.{func.__name__}: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception(f"{self.__class__.__name__}.{func.__name__} error: {e}")
            return {"success": False, "error": str(e)}
    return wrapper
