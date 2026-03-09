"""Unified chunk models for Spine GraphRAG System.

This module provides a unified chunk representation system to eliminate
duplication across the codebase. All chunk-related classes should use
these base models.

Version: 1.0 (2025-12-05)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

from core.exceptions import ProcessingError, ErrorCode


# =============================================================================
# Enums
# =============================================================================

class ChunkTier(Enum):
    """Chunk tier classification."""
    TIER1 = "tier1"  # Core: Abstract, Results, Conclusion
    TIER2 = "tier2"  # Supporting: Introduction, Methods, Discussion


class SectionType(Enum):
    """Document section types."""
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    OTHER = "other"


class SourceType(Enum):
    """Content source type."""
    ORIGINAL = "original"
    CITATION = "citation"
    BACKGROUND = "background"
    UNKNOWN = "unknown"


class ContentType(Enum):
    """Content type classification."""
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    KEY_FINDING = "key_finding"


class EvidenceLevel(Enum):
    """Oxford CEBM evidence levels."""
    LEVEL_1A = "1a"  # Systematic review of RCTs
    LEVEL_1B = "1b"  # Individual RCT
    LEVEL_2A = "2a"  # Systematic review of cohort studies
    LEVEL_2B = "2b"  # Individual cohort / low-quality RCT
    LEVEL_2C = "2c"  # Outcomes research
    LEVEL_3A = "3a"  # Systematic review of case-control studies
    LEVEL_3B = "3b"  # Individual case-control study
    LEVEL_4 = "4"    # Case series
    LEVEL_5 = "5"    # Expert opinion


# =============================================================================
# Base Chunk Model
# =============================================================================

@dataclass
class ChunkBase:
    """Base chunk model with common fields.

    All chunk types should either use this directly or extend it.
    """
    # Identity
    chunk_id: str
    content: str
    document_id: str

    # Classification
    tier: str = "tier2"  # tier1 or tier2
    section: str = "other"
    content_type: str = "text"
    source_type: str = "original"

    # Location
    page_number: Optional[int] = None
    char_start: int = 0
    char_end: int = 0

    # Metadata
    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    publication_year: int = 0
    evidence_level: str = "5"

    # Semantic info
    topic_summary: str = ""
    keywords: list[str] = field(default_factory=list)
    is_key_finding: bool = False

    # Additional metadata (flexible)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_tier1(self) -> bool:
        """Check if this is a Tier 1 chunk."""
        return self.tier.lower() == "tier1"

    def is_tier2(self) -> bool:
        """Check if this is a Tier 2 chunk."""
        return self.tier.lower() == "tier2"

    def get_tier_enum(self) -> ChunkTier:
        """Get tier as enum."""
        return ChunkTier.TIER1 if self.is_tier1() else ChunkTier.TIER2

    def get_section_enum(self) -> SectionType:
        """Get section as enum."""
        try:
            return SectionType(self.section.lower())
        except (ValueError, AttributeError):
            return SectionType.OTHER

    def get_source_enum(self) -> SourceType:
        """Get source type as enum."""
        try:
            return SourceType(self.source_type.lower())
        except (ValueError, AttributeError):
            return SourceType.UNKNOWN

    def get_content_enum(self) -> ContentType:
        """Get content type as enum."""
        try:
            return ContentType(self.content_type.lower())
        except (ValueError, AttributeError):
            return ContentType.TEXT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "document_id": self.document_id,
            "tier": self.tier,
            "section": self.section,
            "content_type": self.content_type,
            "source_type": self.source_type,
            "page_number": self.page_number,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "title": self.title,
            "authors": self.authors,
            "publication_year": self.publication_year,
            "evidence_level": self.evidence_level,
            "topic_summary": self.topic_summary,
            "keywords": self.keywords,
            "is_key_finding": self.is_key_finding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkBase":
        """Create from dictionary."""
        return cls(
            chunk_id=data.get("chunk_id", ""),
            content=data.get("content", ""),
            document_id=data.get("document_id", ""),
            tier=data.get("tier", "tier2"),
            section=data.get("section", "other"),
            content_type=data.get("content_type", "text"),
            source_type=data.get("source_type", "original"),
            page_number=data.get("page_number"),
            char_start=data.get("char_start", 0),
            char_end=data.get("char_end", 0),
            title=data.get("title"),
            authors=data.get("authors", []),
            publication_year=data.get("publication_year", 0),
            evidence_level=data.get("evidence_level", "5"),
            topic_summary=data.get("topic_summary", ""),
            keywords=data.get("keywords", []),
            is_key_finding=data.get("is_key_finding", False),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Tier-Specific Models
# =============================================================================

@dataclass
class Tier1Chunk(ChunkBase):
    """Tier 1 chunk (core sections: abstract, results, conclusion).

    These chunks contain the most important information and are
    searched first in tiered retrieval.
    """
    def __post_init__(self):
        """Ensure tier is set to tier1."""
        self.tier = "tier1"


@dataclass
class Tier2Chunk(ChunkBase):
    """Tier 2 chunk (supporting sections: intro, methods, discussion).

    These chunks provide context and detailed methodology.
    """
    def __post_init__(self):
        """Ensure tier is set to tier2."""
        self.tier = "tier2"


# =============================================================================
# Extended Models (for specific use cases)
# =============================================================================

@dataclass
class PICOData:
    """PICO framework data."""
    population: str = ""
    intervention: str = ""
    comparison: str = ""
    outcome: str = ""


@dataclass
class StatisticsData:
    """Statistical data."""
    p_values: list[str] = field(default_factory=list)
    effect_sizes: list[str] = field(default_factory=list)
    confidence_intervals: list[str] = field(default_factory=list)
    sample_sizes: list[str] = field(default_factory=list)
    odds_ratios: list[str] = field(default_factory=list)
    hazard_ratios: list[str] = field(default_factory=list)


@dataclass
class RichChunk(ChunkBase):
    """Extended chunk with PICO and statistics.

    Used when detailed extraction (PICO, statistics) is needed.
    Typically produced by LLM-based extractors.
    """
    # PICO elements
    pico: Optional[PICOData] = None

    # Statistics
    statistics: Optional[StatisticsData] = None
    has_statistics: bool = False

    # Processing metadata
    llm_processed: bool = False
    llm_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "pico": {
                "population": self.pico.population if self.pico else "",
                "intervention": self.pico.intervention if self.pico else "",
                "comparison": self.pico.comparison if self.pico else "",
                "outcome": self.pico.outcome if self.pico else "",
            } if self.pico else None,
            "statistics": {
                "p_values": self.statistics.p_values if self.statistics else [],
                "effect_sizes": self.statistics.effect_sizes if self.statistics else [],
                "confidence_intervals": self.statistics.confidence_intervals if self.statistics else [],
                "sample_sizes": self.statistics.sample_sizes if self.statistics else [],
                "odds_ratios": self.statistics.odds_ratios if self.statistics else [],
                "hazard_ratios": self.statistics.hazard_ratios if self.statistics else [],
            } if self.statistics else None,
            "has_statistics": self.has_statistics,
            "llm_processed": self.llm_processed,
            "llm_confidence": self.llm_confidence,
        })
        return base_dict


# =============================================================================
# Unified Chunk (adapter for any tier)
# =============================================================================

@dataclass
class UnifiedChunk(ChunkBase):
    """Unified chunk that can represent any tier.

    This is the recommended model for most use cases. It automatically
    handles tier classification and provides convenience methods.
    """

    @classmethod
    def create_tier1(
        cls,
        chunk_id: str,
        content: str,
        document_id: str,
        section: str = "abstract",
        **kwargs
    ) -> "UnifiedChunk":
        """Create a Tier 1 chunk."""
        return cls(
            chunk_id=chunk_id,
            content=content,
            document_id=document_id,
            tier="tier1",
            section=section,
            **kwargs
        )

    @classmethod
    def create_tier2(
        cls,
        chunk_id: str,
        content: str,
        document_id: str,
        section: str = "methods",
        **kwargs
    ) -> "UnifiedChunk":
        """Create a Tier 2 chunk."""
        return cls(
            chunk_id=chunk_id,
            content=content,
            document_id=document_id,
            tier="tier2",
            section=section,
            **kwargs
        )

    def upgrade_tier(self) -> None:
        """Upgrade to Tier 1 (if this contains key findings)."""
        if self.is_key_finding and self.is_tier2():
            self.tier = "tier1"

    def downgrade_tier(self) -> None:
        """Downgrade to Tier 2."""
        if self.is_tier1():
            self.tier = "tier2"


# =============================================================================
# Factory Functions
# =============================================================================

def create_chunk(
    chunk_id: str,
    content: str,
    document_id: str,
    tier: str = "tier2",
    section: str = "other",
    **kwargs
) -> ChunkBase:
    """Factory function to create appropriate chunk type.

    Args:
        chunk_id: Unique chunk identifier
        content: Chunk text content
        document_id: Parent document ID
        tier: Tier classification (tier1 or tier2)
        section: Section type
        **kwargs: Additional fields

    Returns:
        ChunkBase instance
    """
    if tier.lower() == "tier1":
        return Tier1Chunk(
            chunk_id=chunk_id,
            content=content,
            document_id=document_id,
            section=section,
            **kwargs
        )
    else:
        return Tier2Chunk(
            chunk_id=chunk_id,
            content=content,
            document_id=document_id,
            section=section,
            **kwargs
        )


def create_unified_chunk(
    chunk_id: str,
    content: str,
    document_id: str,
    tier: str = "tier2",
    **kwargs
) -> UnifiedChunk:
    """Factory function to create unified chunk.

    Args:
        chunk_id: Unique chunk identifier
        content: Chunk text content
        document_id: Parent document ID
        tier: Tier classification
        **kwargs: Additional fields

    Returns:
        UnifiedChunk instance
    """
    return UnifiedChunk(
        chunk_id=chunk_id,
        content=content,
        document_id=document_id,
        tier=tier,
        **kwargs
    )


# =============================================================================
# Conversion Utilities
# =============================================================================

def convert_to_base_chunk(chunk: Any) -> ChunkBase:
    """Convert any chunk-like object to ChunkBase.

    Args:
        chunk: Chunk object (TextChunk, ExtractedChunk, ChunkInfo, etc.)

    Returns:
        ChunkBase instance

    Raises:
        ValueError: If chunk cannot be converted
    """
    if isinstance(chunk, ChunkBase):
        return chunk

    # Handle dict-like objects
    if isinstance(chunk, dict):
        return ChunkBase.from_dict(chunk)

    # Handle dataclass-like objects with attributes
    # Check for either standard field names or alternate field names
    has_chunk_id = hasattr(chunk, 'chunk_id') or hasattr(chunk, 'id')
    has_content = hasattr(chunk, 'content') or hasattr(chunk, 'text')
    has_doc_id = hasattr(chunk, 'document_id')

    if (has_chunk_id and has_content) or (has_chunk_id and has_doc_id):
        return ChunkBase(
            chunk_id=getattr(chunk, 'chunk_id', getattr(chunk, 'id', '')),
            content=getattr(chunk, 'content', getattr(chunk, 'text', '')),
            document_id=getattr(chunk, 'document_id', ''),
            tier=getattr(chunk, 'tier', 'tier2'),
            section=getattr(chunk, 'section', getattr(chunk, 'section_type', 'other')),
            content_type=getattr(chunk, 'content_type', 'text'),
            source_type=getattr(chunk, 'source_type', 'original'),
            page_number=getattr(chunk, 'page_number', getattr(chunk, 'page_num', None)),
            char_start=getattr(chunk, 'char_start', getattr(chunk, 'start_char', 0)),
            char_end=getattr(chunk, 'char_end', getattr(chunk, 'end_char', 0)),
            title=getattr(chunk, 'title', None),
            authors=getattr(chunk, 'authors', []),
            publication_year=getattr(chunk, 'publication_year', 0),
            evidence_level=getattr(chunk, 'evidence_level', '5'),
            topic_summary=getattr(chunk, 'topic_summary', ''),
            keywords=getattr(chunk, 'keywords', []),
            is_key_finding=getattr(chunk, 'is_key_finding', False),
        )

    raise ProcessingError(message=f"Cannot convert {type(chunk)} to ChunkBase", error_code=ErrorCode.PROC_UNKNOWN)


# =============================================================================
# Compatibility Aliases (for gradual migration)
# =============================================================================

# These can be used for backward compatibility during migration
TextChunk = ChunkBase  # Alias for vector_db.py
ChunkInfo = ChunkBase  # Alias for tiered_search.py
