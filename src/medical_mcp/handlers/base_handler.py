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

    # Default limits for input validation
    MAX_STRING_LENGTH = 10000
    MAX_IDENTIFIER_LENGTH = 1000
    MAX_LIST_ITEMS = 100

    def __init__(self, server: "MedicalKAGServer"):
        self.server = server

    def validate_string_length(
        self,
        value: str,
        field_name: str,
        max_length: int = 10000,
    ) -> None:
        """Validate that a string input does not exceed the maximum length.

        Args:
            value: The string value to validate.
            field_name: Name of the field (for error messages).
            max_length: Maximum allowed length in characters.

        Raises:
            ValidationError: If the string exceeds max_length.
        """
        if value and len(value) > max_length:
            raise ValidationError(
                message=(
                    f"{field_name} too long ({len(value)} chars). "
                    f"Maximum: {max_length} chars."
                ),
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

    def validate_list_length(
        self,
        items: list,
        field_name: str,
        max_items: int = 100,
    ) -> None:
        """Validate that a list does not exceed the maximum number of items.

        Args:
            items: The list to validate.
            field_name: Name of the field (for error messages).
            max_items: Maximum allowed number of items.

        Raises:
            ValidationError: If the list exceeds max_items.
        """
        if items and len(items) > max_items:
            raise ValidationError(
                message=(
                    f"{field_name} has too many items ({len(items)}). "
                    f"Maximum: {max_items} items."
                ),
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

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

        Resolves the path and checks:
        1. No '..' components remain after resolution (traversal attempt)
        2. Path falls within allowed directories (project data dir, cwd, or home dir)

        Args:
            file_path: Raw file path string to validate.

        Returns:
            (resolved_path, None) if valid, or (None, error_dict) if blocked.
        """
        if not file_path or not file_path.strip():
            return None, {"success": False, "error": "파일 경로가 비어 있습니다"}

        raw_path = Path(file_path)
        resolved = raw_path.resolve()

        # Check 1: Reject if raw path contains '..' that escapes (compare raw vs resolved)
        # If someone passes '/data/pdf/../../etc/passwd', raw parts will contain '..'
        if ".." in raw_path.parts:
            logger.warning(f"Path traversal attempt blocked (.. component): {file_path}")
            return None, {
                "success": False,
                "error": "경로에 '..' 구성요소를 사용할 수 없습니다 (path traversal 방지)",
            }

        # Check 2: Resolved path must be within allowed directories
        allowed_dirs: list[Path] = []

        # Project data directory
        if hasattr(self.server, "project_root"):
            allowed_dirs.append(Path(self.server.project_root / "data").resolve())

        # Current working directory
        allowed_dirs.append(Path.cwd().resolve())

        # User home directory (lightweight local-MCP defense)
        home = Path.home().resolve()
        if home != Path("/").resolve():
            allowed_dirs.append(home)

        if not any(resolved.is_relative_to(d) for d in allowed_dirs):
            logger.warning(f"Path traversal attempt blocked (outside allowed dirs): {file_path}")
            return None, {
                "success": False,
                "error": "접근 불가: 허용된 디렉토리 외부 경로입니다",
            }

        return resolved, None

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
