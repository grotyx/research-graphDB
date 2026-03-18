"""Cross-Encoder Reranker module for search result refinement.

Supports multiple providers:
  - "cohere": Cohere Rerank API (requires cohere package + API key)
  - "llm": LLM-based reranking using Claude Haiku (uses existing Anthropic API)
  - "none": Disabled (passthrough)

v1.27.0: Initial implementation (Cohere)
v1.29.0: LLM-based reranker using Haiku for domain-aware reranking
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Optional Cohere import
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    cohere = None  # type: ignore

# Optional Anthropic import
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None  # type: ignore


class Reranker:
    """Cross-encoder reranker for improving search result relevance.

    Supports Cohere Rerank API and LLM-based reranking.

    Args:
        provider: Reranking provider ("cohere", "llm", or "none").
        model: Model name (Cohere model or Claude model).
        api_key: API key. Falls back to env vars.
    """

    def __init__(
        self,
        provider: str = "llm",
        model: str = "claude-haiku-4-5-20251001",
        api_key: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self._client = None
        self._available = False

        if provider == "none":
            logger.info("Reranker: disabled (provider='none')")
            return

        if provider == "llm":
            if not ANTHROPIC_AVAILABLE:
                logger.warning(
                    "Reranker: anthropic package not installed. "
                    "Falling back to no reranking."
                )
                return

            resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if not resolved_key:
                logger.warning("Reranker: ANTHROPIC_API_KEY not set.")
                return

            try:
                self._client = anthropic.Anthropic(api_key=resolved_key)
                self._available = True
                logger.info(f"Reranker: LLM initialized (model={model})")
            except Exception as e:
                logger.warning(f"Reranker: Failed to init Anthropic client: {e}")

        elif provider == "cohere":
            if not COHERE_AVAILABLE:
                logger.warning(
                    "Reranker: cohere package not installed. "
                    "Install with: pip install 'spine-graphrag[rerank]'. "
                    "Falling back to no reranking."
                )
                return

            resolved_key = api_key or os.environ.get("COHERE_API_KEY", "")
            if not resolved_key:
                logger.warning("Reranker: COHERE_API_KEY not set.")
                return

            try:
                self._client = cohere.ClientV2(api_key=resolved_key)
                self._available = True
                logger.info(f"Reranker: Cohere initialized (model={model})")
            except Exception as e:
                logger.warning(f"Reranker: Failed to init Cohere client: {e}")
        else:
            logger.warning(f"Reranker: Unknown provider '{provider}', disabled.")

    @property
    def is_available(self) -> bool:
        return self._available

    async def rerank(
        self,
        query: str,
        results: list,
        top_k: int = 10,
    ) -> list:
        """Rerank search results.

        Args:
            query: The original search query.
            results: List of SearchResult objects to rerank.
            top_k: Number of top results to return.

        Returns:
            Reranked list, truncated to top_k.
        """
        if not self._available or not results:
            return results[:top_k]

        if self.provider == "llm":
            return await self._rerank_llm(query, results, top_k)
        elif self.provider == "cohere":
            return await self._rerank_cohere(query, results, top_k)

        return results[:top_k]

    async def _rerank_llm(
        self, query: str, results: list, top_k: int
    ) -> list:
        """Rerank using LLM (Claude Haiku).

        Sends the query + candidate paper titles/snippets to Haiku,
        asks it to rank by relevance to the specific question.
        """
        # Build candidate list for LLM
        candidates = []
        for i, r in enumerate(results):
            text = ""
            title = ""
            if hasattr(r, "chunk") and r.chunk:
                text = getattr(r.chunk, "text", "")[:300]
                title = getattr(r.chunk, "title", "")
            if not text and hasattr(r, "content"):
                text = r.content[:300]

            candidates.append({
                "index": i,
                "title": title,
                "snippet": text[:200],
            })

        if not candidates:
            return results[:top_k]

        # Build prompt
        candidates_text = "\n".join(
            f"[{c['index']}] {c['title']}\n    {c['snippet']}"
            for c in candidates
        )

        prompt = f"""You are a spine surgery literature expert. Given a clinical question and a list of candidate papers, rank the papers by relevance to the SPECIFIC question asked.

## Clinical Question
{query}

## Candidate Papers
{candidates_text}

## Instructions
1. Consider how directly each paper answers the SPECIFIC question (not just the general topic)
2. A paper about the exact intervention/pathology comparison asked is more relevant than a tangentially related meta-analysis
3. Return ONLY a JSON array of paper indices in order of relevance (most relevant first)
4. Select the top {top_k} most relevant papers

Return format: [{{"index": 0}}, {{"index": 3}}, {{"index": 1}}, ...]
Return ONLY the JSON array, no other text."""

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Parse JSON array from response
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if not json_match:
                logger.warning("Reranker LLM: could not parse JSON, returning original")
                return results[:top_k]

            ranked_indices = json.loads(json_match.group())

            # Extract indices
            reranked = []
            seen = set()
            for item in ranked_indices:
                idx = item.get("index", item) if isinstance(item, dict) else item
                idx = int(idx)
                if 0 <= idx < len(results) and idx not in seen:
                    seen.add(idx)
                    reranked.append(results[idx])

            # Append any missing results at the end
            for i, r in enumerate(results):
                if i not in seen and len(reranked) < top_k:
                    reranked.append(r)

            logger.info(
                f"Reranker LLM: reranked {len(results)} -> {len(reranked[:top_k])} results"
            )
            return reranked[:top_k]

        except Exception as e:
            logger.warning(f"Reranker LLM: failed ({e}), returning original order")
            return results[:top_k]

    async def _rerank_cohere(
        self, query: str, results: list, top_k: int
    ) -> list:
        """Rerank using Cohere API."""
        documents = []
        for r in results:
            text = getattr(r.chunk, "text", "") if hasattr(r, "chunk") else ""
            documents.append(text)

        if not any(documents):
            return results[:top_k]

        try:
            response = self._client.rerank(
                query=query,
                documents=documents,
                top_n=min(top_k, len(documents)),
                model=self.model,
            )

            reranked = []
            for item in response.results:
                idx = item.index
                if 0 <= idx < len(results):
                    result = results[idx]
                    result.score = item.relevance_score
                    reranked.append(result)

            logger.info(
                f"Reranker Cohere: reranked {len(documents)} -> {len(reranked)} results"
            )
            return reranked

        except Exception as e:
            logger.warning(f"Reranker Cohere: failed ({e}), returning original order")
            return results[:top_k]
