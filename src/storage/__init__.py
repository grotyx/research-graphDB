"""Storage modules for Medical KAG System.

⚠️ DEPRECATED: v5.3 (2025-12-18)
================================
이 모듈은 더 이상 사용되지 않습니다.
v5.3부터 Neo4j Vector Index가 유일한 벡터 저장소입니다.

마이그레이션 가이드:
    대신 src/graph/neo4j_client.py를 사용하세요.

v7.14.12: ChromaDB 완전 제거
    TextChunk, SearchFilters는 하위 호환성을 위해 유지.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Tier(Enum):
    """검색 계층."""
    TIER1 = "tier1"  # 핵심: Abstract, Results, Conclusion
    TIER2 = "tier2"  # 상세: Introduction, Methods, Discussion


class SourceType(Enum):
    """출처 유형."""
    ORIGINAL = "original"
    CITATION = "citation"
    BACKGROUND = "background"


@dataclass
class TextChunk:
    """텍스트 청크 (v7.14.12: 하위 호환성 유지).

    Note: 이 클래스는 레거시 코드 호환성을 위해 유지됩니다.
    새 코드에서는 Neo4j의 Chunk 노드를 직접 사용하세요.
    """
    chunk_id: str
    content: str
    document_id: str
    tier: str  # "tier1" or "tier2"
    section: str
    source_type: str  # "original", "citation", "background"
    evidence_level: str = "5"
    publication_year: int = 0
    page_num: int = 0
    title: str = ""
    authors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # LLM 추출 메타데이터
    summary: str = ""
    keywords: list[str] = field(default_factory=list)

    # 통계 정보
    statistics_p_value: str = ""
    statistics_is_significant: bool = False
    statistics_additional: str = ""
    has_statistics: bool = False

    # 처리 메타데이터
    llm_processed: bool = False
    llm_confidence: float = 0.0

    # 추가 LLM 메타데이터
    is_key_finding: bool = False
    medical_terms: list[str] = field(default_factory=list)


@dataclass
class SearchFilters:
    """검색 필터 (v7.14.12: 하위 호환성 유지)."""
    source_types: Optional[list[str]] = None
    evidence_levels: Optional[list[str]] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    sections: Optional[list[str]] = None
    document_ids: Optional[list[str]] = None


@dataclass
class SearchResult:
    """검색 결과 (v7.14.12: 하위 호환성 유지)."""
    chunk_id: str
    content: str
    document_id: str
    score: float
    tier: str
    section: str
    source_type: str
    evidence_level: str
    publication_year: int
    title: str
    metadata: dict = field(default_factory=dict)
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    is_key_finding: bool = False
    statistics_p_value: str = ""
    statistics_is_significant: bool = False
    statistics_additional: str = ""
    has_statistics: bool = False
    llm_confidence: float = 0.0


# 하위 호환성을 위한 helper 함수
def create_text_chunk(
    chunk_id: str,
    content: str,
    document_id: str,
    tier: str,
    section: str,
    source_type: str = "original",
    evidence_level: str = "5",
    publication_year: int = 0,
    title: str = "",
    **kwargs
) -> TextChunk:
    """TextChunk 생성 헬퍼 함수."""
    return TextChunk(
        chunk_id=chunk_id,
        content=content,
        document_id=document_id,
        tier=tier,
        section=section,
        source_type=source_type,
        evidence_level=evidence_level,
        publication_year=publication_year,
        title=title,
        metadata=kwargs
    )


__all__ = [
    "TextChunk",
    "SearchResult",
    "SearchFilters",
    "Tier",
    "SourceType",
    "create_text_chunk",
]
