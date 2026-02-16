"""Base LLM client interface for provider-agnostic usage."""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class BaseLLMClient(Protocol):
    """Protocol defining the interface for LLM clients.

    All LLM providers (Claude, Gemini, OpenAI, etc.) should implement this interface.
    Both ClaudeClient and GeminiClient satisfy this protocol.
    """

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> Any:
        """Generate text from a prompt.

        Args:
            prompt: User prompt text.
            system: Optional system prompt.
            use_cache: Whether to use LLM response cache.

        Returns:
            Provider-specific response object (ClaudeResponse or GeminiResponse).
        """
        ...

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> dict:
        """Generate structured JSON from a prompt.

        Args:
            prompt: User prompt text.
            schema: JSON schema (dict) describing the expected output structure.
            system: Optional system prompt.
            use_cache: Whether to use LLM response cache.

        Returns:
            Parsed JSON dictionary.
        """
        ...
