"""Chunk Quality Validation Module.

Validates and filters LLM-generated chunks before embedding/storage.
Implements ROADMAP item 3.1: Chunk Quality Validation.

Validation rules:
1. Length filter: chunks < 30 chars -> reject
2. Tier demotion: tier1 chunks < 200 chars -> demote to tier2
3. Near-duplicate detection: cosine similarity > 0.95 within same paper -> flag shorter
4. Statistics check: results/findings chunks without numbers -> key_finding=False

Usage:
    # During import pipeline (after LLM chunk generation, before embedding)
    validator = ChunkValidator()
    validated = validator.validate_chunks(chunks_data)

    # With embeddings (enables near-duplicate detection)
    validated = validator.validate_chunks(chunks_data, embeddings=embeddings)

    # Get stats
    stats = validator.get_validation_stats()

Integration points (do NOT modify these files):
    - pubmed_processor.py: call after LLM chunk generation in _store_llm_chunks()
      and process_fulltext_with_llm(), before embedding generation
    - Can also be used standalone for auditing existing chunks
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MIN_CHUNK_LENGTH = 30
"""Minimum chunk length in characters. Chunks shorter than this are rejected."""

TIER1_MIN_LENGTH = 200
"""Minimum length for tier1 chunks. Shorter tier1 chunks are demoted to tier2."""

DUPLICATE_SIMILARITY_THRESHOLD = 0.95
"""Cosine similarity threshold for near-duplicate detection within a paper."""

# Section types that should contain statistics for key_finding=True
STATS_SECTIONS = frozenset({
    "results", "findings", "outcomes", "result", "finding", "outcome",
})

# Pattern to detect numbers/statistics in text
_STATS_PATTERN = re.compile(
    r"""
    \d+\.?\d*\s*%                  # percentages: 45.2%
    | p\s*[<>=]\s*0?\.\d+          # p-values: p<0.05, p = 0.001
    | (?:OR|RR|HR|CI|SD|SE)\s*     # statistical abbreviations
      [=:]\s*\d                    #   followed by number
    | \d+\.\d+\s*±\s*\d            # mean ± SD: 3.2 ± 1.1
    | \d+\s*/\s*\d+                # fractions: 23/45
    | \(\s*\d+\.?\d*\s*[-–]\s*     # confidence intervals: (1.2-3.4)
      \d+\.?\d*\s*\)
    | n\s*=\s*\d+                  # sample size: n=42
    | \d+\.\d{2,}                  # decimal numbers with 2+ places
    """,
    re.IGNORECASE | re.VERBOSE,
)


# =============================================================================
# Validation Result
# =============================================================================

@dataclass
class ValidationStats:
    """Accumulated statistics from chunk validation runs."""

    total_input: int = 0
    rejected_short: int = 0
    demoted_tier: int = 0
    flagged_duplicate: int = 0
    cleared_key_finding: int = 0
    total_output: int = 0

    def to_dict(self) -> dict:
        """Convert to plain dict for JSON serialization."""
        return {
            "total_input": self.total_input,
            "rejected_short": self.rejected_short,
            "demoted_tier": self.demoted_tier,
            "flagged_duplicate": self.flagged_duplicate,
            "cleared_key_finding": self.cleared_key_finding,
            "total_output": self.total_output,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self.total_input = 0
        self.rejected_short = 0
        self.demoted_tier = 0
        self.flagged_duplicate = 0
        self.cleared_key_finding = 0
        self.total_output = 0


# =============================================================================
# ChunkValidator
# =============================================================================

class ChunkValidator:
    """Validates and filters LLM-generated chunks.

    Each chunk dict is expected to have at least:
        - content (str): chunk text
        - tier (str): "tier1" or "tier2"
        - section_type (str): e.g. "results", "methods", "abstract"
        - is_key_finding (bool): whether this is a key finding

    After validation, each chunk gets a 'validation_notes' list[str] field
    describing any modifications made.

    Args:
        min_length: Minimum chunk length in chars (default 30).
        tier1_min_length: Minimum length for tier1 (default 200).
        dedup_threshold: Cosine similarity threshold for duplicates (default 0.95).
    """

    def __init__(
        self,
        min_length: int = MIN_CHUNK_LENGTH,
        tier1_min_length: int = TIER1_MIN_LENGTH,
        dedup_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD,
    ) -> None:
        self.min_length = min_length
        self.tier1_min_length = tier1_min_length
        self.dedup_threshold = dedup_threshold
        self._stats = ValidationStats()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def validate_chunks(
        self,
        chunks: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> list[dict]:
        """Validate and filter a list of chunk dicts.

        Applies all validation rules in order:
        1. Length filter (reject < min_length)
        2. Tier demotion (tier1 < tier1_min_length -> tier2)
        3. Statistics check (results chunks without stats -> key_finding=False)
        4. Near-duplicate detection (if embeddings provided)

        Args:
            chunks: List of chunk dicts from LLM processing.
                Required keys: 'content', 'tier'.
                Optional keys: 'section_type', 'is_key_finding'.
            embeddings: Optional list of embedding vectors (same length as chunks).
                If provided, enables near-duplicate detection.

        Returns:
            Filtered and modified list of chunk dicts. Each dict gets a
            'validation_notes' field (list[str]) documenting changes.

        Raises:
            ValueError: If embeddings length doesn't match chunks length.
        """
        if embeddings is not None and len(embeddings) != len(chunks):
            raise ValueError(
                f"embeddings length ({len(embeddings)}) != chunks length ({len(chunks)})"
            )

        self._stats.total_input += len(chunks)

        # Step 1-3: per-chunk validation (length, tier, stats)
        validated: list[dict] = []
        valid_embeddings: list[list[float]] = []

        for i, chunk in enumerate(chunks):
            chunk = dict(chunk)  # shallow copy to avoid mutating input
            chunk.setdefault("validation_notes", [])

            content = chunk.get("content", "")

            # Rule 1: Length filter
            if not content or len(content) < self.min_length:
                self._stats.rejected_short += 1
                logger.debug(
                    "Chunk rejected: too short (%d chars)", len(content)
                )
                continue

            # Rule 2: Tier demotion
            tier = chunk.get("tier", "tier2")
            if tier == "tier1" and len(content) < self.tier1_min_length:
                chunk["tier"] = "tier2"
                chunk["validation_notes"].append(
                    f"tier1->tier2: content too short ({len(content)} chars < {self.tier1_min_length})"
                )
                self._stats.demoted_tier += 1

            # Rule 3: Statistics check for results/findings sections
            section = chunk.get("section_type", "other").lower()
            is_key = chunk.get("is_key_finding", False)
            if is_key and section in STATS_SECTIONS:
                if not _has_statistics(content):
                    chunk["is_key_finding"] = False
                    chunk["validation_notes"].append(
                        "key_finding cleared: results/findings section without statistics"
                    )
                    self._stats.cleared_key_finding += 1

            validated.append(chunk)
            if embeddings is not None:
                valid_embeddings.append(embeddings[i])

        # Step 4: Near-duplicate detection (requires embeddings)
        if valid_embeddings and len(valid_embeddings) == len(validated):
            validated = self._deduplicate(validated, valid_embeddings)

        self._stats.total_output += len(validated)

        if self._stats.rejected_short or self._stats.demoted_tier or self._stats.flagged_duplicate:
            logger.info(
                "Chunk validation: %d->%d (rejected=%d, demoted=%d, dedup=%d, stats_cleared=%d)",
                self._stats.total_input,
                self._stats.total_output,
                self._stats.rejected_short,
                self._stats.demoted_tier,
                self._stats.flagged_duplicate,
                self._stats.cleared_key_finding,
            )

        return validated

    def get_validation_stats(self) -> dict:
        """Get accumulated validation statistics.

        Returns:
            Dict with counts: total_input, rejected_short, demoted_tier,
            flagged_duplicate, cleared_key_finding, total_output.
        """
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset accumulated validation statistics."""
        self._stats.reset()

    # -----------------------------------------------------------------
    # Internal Methods
    # -----------------------------------------------------------------

    def _deduplicate(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> list[dict]:
        """Remove near-duplicate chunks within the same paper.

        For each pair with cosine similarity > threshold, the shorter chunk
        is flagged for removal.

        Args:
            chunks: Validated chunk dicts.
            embeddings: Corresponding embedding vectors.

        Returns:
            Deduplicated list of chunk dicts.
        """
        n = len(chunks)
        if n < 2:
            return chunks

        remove_indices: set[int] = set()

        for i in range(n):
            if i in remove_indices:
                continue
            for j in range(i + 1, n):
                if j in remove_indices:
                    continue

                sim = _cosine_similarity(embeddings[i], embeddings[j])
                if sim > self.dedup_threshold:
                    # Remove the shorter chunk
                    len_i = len(chunks[i].get("content", ""))
                    len_j = len(chunks[j].get("content", ""))
                    victim = j if len_j <= len_i else i
                    remove_indices.add(victim)
                    self._stats.flagged_duplicate += 1

                    # Annotate the kept chunk
                    kept = i if victim == j else j
                    chunks[kept].setdefault("validation_notes", []).append(
                        f"near-duplicate removed (sim={sim:.3f}): kept this, removed chunk at index {victim}"
                    )
                    logger.debug(
                        "Near-duplicate detected (sim=%.3f): keeping idx=%d (%d chars), removing idx=%d (%d chars)",
                        sim, kept, len(chunks[kept].get("content", "")),
                        victim, len(chunks[victim].get("content", "")),
                    )

        if remove_indices:
            chunks = [c for idx, c in enumerate(chunks) if idx not in remove_indices]

        return chunks


# =============================================================================
# Helper Functions
# =============================================================================

def _has_statistics(text: str) -> bool:
    """Check if text contains statistical data (numbers, p-values, etc.).

    Args:
        text: Chunk content to check.

    Returns:
        True if text contains recognizable statistical patterns.
    """
    return bool(_STATS_PATTERN.search(text))


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Uses pure Python to avoid extra dependencies (numpy not required).
    For normalized vectors (OpenAI embeddings), this is equivalent to dot product.

    Args:
        vec1: First embedding vector.
        vec2: Second embedding vector.

    Returns:
        Cosine similarity in [-1, 1].
    """
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))

    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0

    return dot / (mag1 * mag2)
