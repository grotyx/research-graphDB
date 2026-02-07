"""Knowledge module for paper relationship graph.

**DEPRECATED**: This module is deprecated as of v5.2.
Use Neo4j-based graph storage (`src/graph/`) instead.

This module provides legacy SQLite-based functionality:
- PaperGraph: SQLite-based paper relationship storage (deprecated)
- CitationExtractor: LLM-based citation extraction (deprecated)
- RelationshipReasoner: LLM-based relationship inference (deprecated)

Migration Path:
- Use `src/graph/` for Neo4j-based graph operations
- Use `src/builder/important_citation_processor.py` for citation extraction
- Use `src/solver/conflict_detector.py` for conflict analysis
"""

import warnings

warnings.warn(
    "src/knowledge module is deprecated. Use Neo4j-based graph storage (src/graph/) instead.",
    DeprecationWarning,
    stacklevel=2
)

# Deprecated imports - kept for backward compatibility
from .paper_graph import (
    PaperNode,
    PaperRelation,
    RelationType,
    PaperGraph,
)
from .citation_extractor import (
    CitationInfo,
    CitationType,
    LLMCitationExtractor,
)
from .relationship_reasoner import (
    RelationshipReasoner,
)

__all__ = [
    # Paper Graph (deprecated)
    "PaperNode",
    "PaperRelation",
    "RelationType",
    "PaperGraph",
    # Citation Extractor (deprecated)
    "CitationInfo",
    "CitationType",
    "LLMCitationExtractor",
    # Relationship Reasoner (deprecated)
    "RelationshipReasoner",
]
