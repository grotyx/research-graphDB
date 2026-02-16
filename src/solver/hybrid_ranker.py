"""Hybrid Ranker - Graph + Vector Search Integration.

Neo4j Graph 검색 결과와 Vector 검색 결과를 통합하여
최종 랭킹을 생성하는 모듈.

Enhanced with graceful degradation and error handling.

v5.3: Neo4j Vector Index 통합
- use_neo4j_hybrid=True: Neo4j hybrid_search() 사용 (그래프+벡터 통합 쿼리, 권장)

v1.0: Evidence-based Ranking (SIMPLIFIED)
- Remove: p-value/effect size scoring
- Add: Study design weight, recency boost, sample size boost, citation boost
- Formula: 60% semantic + 40% authority (evidence + design + recency + citations)
- Non-research document support

v1.14.12: ChromaDB 제거
- Neo4j Vector Index가 유일한 벡터 저장소
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from .graph_result import GraphEvidence, GraphSearchResult, PaperNode

# ChromaDB removed in v1.14.12 — Neo4j Vector Index is the only vector store
VectorSearchResult = None  # type: ignore

# Optional Neo4j import (graceful fallback)
try:
    from ..graph.neo4j_client import Neo4jClient
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Neo4jClient = None

# Optional error handling import
try:
    from ..core.error_handler import Neo4jConnectionError
except ImportError:
    Neo4jConnectionError = Exception

# CypherGenerator for query parsing
try:
    from ..orchestrator.cypher_generator import CypherGenerator
    CYPHER_GENERATOR_AVAILABLE = True
except ImportError:
    CYPHER_GENERATOR_AVAILABLE = False
    CypherGenerator = None

logger = logging.getLogger(__name__)


# ============================================================================
# v1.0 Evidence-based Ranking Configuration
# ============================================================================

# Scoring Formula Constants (v1.0)
DEFAULT_SEMANTIC_WEIGHT: float = 0.6    # Semantic score weight in final formula
DEFAULT_AUTHORITY_WEIGHT: float = 0.4   # Authority score weight in final formula
KEY_FINDING_BOOST: float = 1.2          # Boost multiplier for key findings
STATISTICS_BOOST: float = 1.1           # Boost multiplier for results with statistics
DIRECTION_IMPROVED_BOOST: float = 1.2   # Direction boost for improved outcomes
DIRECTION_WORSENED_BOOST: float = 0.8   # Direction boost for worsened outcomes
DIRECTION_UNCHANGED_BOOST: float = 0.9  # Direction boost for unchanged outcomes

# Evidence Level Weights (OCEBM hierarchy)
EVIDENCE_LEVEL_WEIGHTS = {
    "1a": 1.00,   # Systematic review/Meta-analysis
    "1b": 0.90,   # RCT
    "2a": 0.80,   # Cohort study
    "2b": 0.70,   # Case-control
    "3": 0.50,    # Case series
    "4": 0.30,    # Expert opinion
    "5": 0.10,    # Unknown/Not applicable
}

# Study Design Weights (from PRD Section 7.2)
STUDY_DESIGN_WEIGHTS = {
    "Meta-Analysis": 1.0,
    "Systematic Review": 1.0,
    "Randomized Controlled Trial": 0.9,
    "Clinical Trial": 0.85,
    "Comparative Study": 0.75,
    "Cohort Studies": 0.7,
    "Case-Control Studies": 0.65,
    "Observational Study": 0.6,
    "Case Reports": 0.4,
    "Review": 0.5,
}

# Source Credibility for Non-Research Documents (from PRD Section 7.4)
SOURCE_CREDIBILITY = {
    # Medical organizations
    "WHO": 1.0,
    "CDC": 1.0,
    "NIH": 1.0,
    # Professional societies
    "AAOS": 0.95,
    "NASS": 0.95,
    # Academic institutions
    "edu": 0.85,
    # Medical websites
    "MedlinePlus": 0.8,
    "Mayo Clinic": 0.85,
    # General websites
    "wikipedia.org": 0.6,
    "medium.com": 0.5,
    # Unknown
    "default": 0.4,
}

# Deprecated (v1.0) - kept for reference
# SIGNIFICANCE_BOOST = 1.5  # Removed: No longer using p-value


# ============================================================================
# Helper Functions for v1.0 Scoring
# ============================================================================

def get_evidence_weight(paper: PaperNode) -> float:
    """Get evidence level weight.

    Args:
        paper: PaperNode with evidence_level field

    Returns:
        Weight value (0.1-1.0)
    """
    if paper.evidence_level:
        return EVIDENCE_LEVEL_WEIGHTS.get(paper.evidence_level, 0.1)

    # Fallback based on document type
    doc_type = getattr(paper, 'document_type', None)
    if doc_type == "JOURNAL_ARTICLE":
        return 0.50  # Assume Level 3 if unknown
    else:
        return 0.30  # Non-research documents


def get_study_design_weight(publication_types: Optional[list[str]]) -> float:
    """Get weight from publication types.

    Args:
        publication_types: List of MeSH publication types

    Returns:
        Weight value (0.4-1.0), uses highest weight if multiple types
    """
    if not publication_types:
        return 0.5  # Default

    # Use highest weight if multiple types
    weights = [STUDY_DESIGN_WEIGHTS.get(pt, 0.5) for pt in publication_types]
    return max(weights)


def get_sample_size_boost(sample_size: Optional[int]) -> float:
    """Boost score based on sample size (logarithmic scaling).

    Args:
        sample_size: Number of participants/samples

    Returns:
        Boost multiplier (1.0-1.3)
    """
    if not sample_size or sample_size < 10:
        return 1.0  # No boost

    # Logarithmic scaling
    if sample_size >= 1000:
        return 1.3
    elif sample_size >= 500:
        return 1.25
    elif sample_size >= 100:
        return 1.15
    elif sample_size >= 50:
        return 1.1
    else:
        return 1.05


def get_recency_boost(year: int, current_year: Optional[int] = None) -> float:
    """Boost recent publications.

    Args:
        year: Publication year
        current_year: Current year (defaults to 2025)

    Returns:
        Boost multiplier (0.9-1.2)
    """
    if not current_year:
        current_year = datetime.now().year

    age = current_year - year

    if age <= 2:
        return 1.2      # Very recent (last 2 years)
    elif age <= 5:
        return 1.1      # Recent (3-5 years)
    elif age <= 10:
        return 1.0      # Moderate (6-10 years)
    else:
        return 0.9      # Older (>10 years)


def get_citation_boost(citation_count: Optional[int]) -> float:
    """Boost highly cited papers (logarithmic scaling).

    Args:
        citation_count: Number of citations

    Returns:
        Boost multiplier (1.0-1.3)
    """
    if not citation_count or citation_count < 5:
        return 1.0

    # Logarithmic scaling
    if citation_count >= 100:
        return 1.3
    elif citation_count >= 50:
        return 1.2
    elif citation_count >= 20:
        return 1.15
    elif citation_count >= 10:
        return 1.1
    else:
        return 1.05


def get_source_credibility(source: Optional[str]) -> float:
    """Get credibility weight for non-research documents.

    Args:
        source: Source name (website, publisher, organization)

    Returns:
        Credibility score (0.4-1.0)
    """
    if not source:
        return SOURCE_CREDIBILITY["default"]

    source_lower = source.lower()

    # Check exact matches
    for key, value in SOURCE_CREDIBILITY.items():
        if key.lower() in source_lower:
            return value

    # Check domain patterns
    if ".edu" in source_lower:
        return SOURCE_CREDIBILITY["edu"]

    return SOURCE_CREDIBILITY["default"]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class HybridResult:
    """Hybrid 검색 결과.

    Graph와 Vector 검색 결과를 통합한 최종 결과.

    Attributes:
        result_type: "graph" 또는 "vector"
        score: 최종 점수 (0~1)
        content: 텍스트 내용
        source_id: 출처 ID (paper_id 또는 chunk_id)
        metadata: 추가 메타데이터

        # Graph-specific
        evidence: GraphEvidence 객체 (graph인 경우)
        paper: PaperNode 객체 (graph인 경우)

        # Vector-specific
        vector_result: VectorSearchResult 객체 (vector인 경우)
    """
    result_type: str  # "graph" or "vector"
    score: float
    content: str
    source_id: str
    metadata: dict = field(default_factory=dict)

    # Graph-specific
    evidence: Optional[GraphEvidence] = None
    paper: Optional[PaperNode] = None

    # Vector-specific
    vector_result: Optional[VectorSearchResult] = None

    def get_evidence_text(self) -> str:
        """근거 텍스트 생성.

        Returns:
            사람이 읽을 수 있는 근거 설명
        """
        if self.result_type == "graph" and self.evidence:
            return self.evidence.get_display_text()
        elif self.result_type == "vector" and self.vector_result:
            # Vector 결과는 요약 또는 전체 내용
            if self.vector_result.summary:
                return self.vector_result.summary
            return self.content[:200] + "..." if len(self.content) > 200 else self.content
        return ""

    def get_citation(self) -> str:
        """인용 정보 생성.

        Returns:
            논문 인용 문자열
        """
        if self.result_type == "graph" and self.paper:
            return self.paper.get_citation()
        elif self.result_type == "vector" and self.vector_result:
            return f"{self.vector_result.title} ({self.vector_result.publication_year})"
        return ""


# ============================================================================
# Main Ranker Class
# ============================================================================

class HybridRanker:
    """Graph + Vector 통합 랭커 (v1.0).

    Neo4j Graph 검색 결과와 ChromaDB Vector 검색 결과를 통합하여
    최종 랭킹을 생성.

    v1.0 Changes:
    - Remove: p-value/effect size scoring
    - Add: Study design weight, recency boost, sample size boost
    - New formula: 60% semantic + 40% authority

    검색 흐름 (기본):
        1. Graph Search: 구조적 근거 추출 (Intervention → Outcome 관계)
        2. Vector Search: 의미적 유사도 검색 (ChromaDB)
        3. Hybrid Ranking: 통합 점수 계산 및 정렬
        4. Result Merging: 중복 제거 및 최종 결과 반환

    검색 흐름 (v5.3 - Neo4j Hybrid):
        1. Neo4j hybrid_search(): 그래프 필터링 + 벡터 검색 통합 쿼리
        2. 단일 트랜잭션으로 처리 (더 빠른 응답)

    점수 계산 (v1.0):
        - Authority 점수: Evidence Level × Study Design × Sample Size × Recency × Citations
        - Semantic 점수: Vector Similarity × Metadata Boosts
        - 최종 점수 = 0.6 × Semantic + 0.4 × Authority
    """

    def __init__(
        self,
        vector_db: Optional[object] = None,  # deprecated (ChromaDB removed in v1.14.12)
        neo4j_client: Optional["Neo4jClient"] = None,
        use_neo4j_hybrid: bool = False
    ) -> None:
        """초기화.

        Args:
            vector_db: deprecated (ChromaDB removed in v1.14.12)
            neo4j_client: Neo4j 클라이언트 (선택적)
            use_neo4j_hybrid: Neo4j 통합 hybrid_search 사용 여부 (v5.3)
        """
        self.vector_db = vector_db
        self.neo4j_client: Optional["Neo4jClient"] = neo4j_client
        self.use_neo4j_hybrid: bool = use_neo4j_hybrid and neo4j_client is not None

        if neo4j_client is None:
            logger.warning("Neo4j client not provided. Graph search disabled.")
            self.use_neo4j_hybrid = False

        if self.use_neo4j_hybrid:
            logger.info("HybridRanker: Using Neo4j integrated hybrid search (v5.3)")

        if vector_db is None and not self.use_neo4j_hybrid:
            logger.warning("Vector DB not provided and Neo4j hybrid not enabled. Vector search will be unavailable.")

    async def search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4,
        min_p_value: float = 0.05,
        evidence_levels: Optional[list[str]] = None,
        graph_filters: Optional[dict] = None
    ) -> list[HybridResult]:
        """Hybrid 검색 수행.

        Args:
            query: 검색 쿼리 (자연어)
            query_embedding: 쿼리 임베딩 (MedTE: 768d, OpenAI: 3072d)
            top_k: 반환할 결과 수
            graph_weight: Graph 결과 가중치 (0~1)
            vector_weight: Vector 결과 가중치 (0~1)
            min_p_value: [DEPRECATED v1.0] 유의성 임계값 (no longer used)
            evidence_levels: 허용할 근거 수준 (예: ["1a", "1b", "2a"])
            graph_filters: 그래프 필터 (v5.3 - Neo4j hybrid용)
                - intervention: Intervention 이름
                - pathology: Pathology 이름
                - min_year: 최소 연도

        Returns:
            통합 점수 기준 정렬된 HybridResult 목록
        """
        # v5.3: Neo4j 통합 Hybrid Search 사용
        if self.use_neo4j_hybrid:
            return await self._neo4j_hybrid_search(
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
                graph_weight=graph_weight,
                vector_weight=vector_weight,
                evidence_levels=evidence_levels,
                graph_filters=graph_filters
            )

        # 기존 방식: Graph + Vector 분리 검색
        # 1. Graph Search (if available) with graceful degradation
        graph_results: list[HybridResult] = []
        graph_degraded = False

        if self.neo4j_client and NEO4J_AVAILABLE:
            try:
                graph_search_result = await self._graph_search(
                    query, min_p_value, evidence_levels
                )
                graph_results = self._score_graph_results(graph_search_result)
                logger.info(f"Graph search: {len(graph_results)} results")
            except Neo4jConnectionError as e:
                logger.warning(f"Graph search unavailable: {e}. Falling back to vector-only.")
                graph_degraded = True
            except Exception as e:
                logger.error(f"Graph search failed: {e}. Falling back to vector-only.", exc_info=True)
                graph_degraded = True

        # 2. Vector Search with error handling
        vector_results: list[HybridResult] = []
        vector_degraded = False

        # v1.15: vector_db None guard 추가
        if self.vector_db is None:
            logger.info("Vector DB not available, skipping vector search")
            vector_degraded = True
        else:
            try:
                vector_search_results = self.vector_db.search_all(
                    query_embedding=query_embedding,
                    top_k=top_k * 2,  # 여유있게 검색
                    tier1_weight=1.0,
                    tier2_weight=0.7
                )
                vector_results = self._score_vector_results(vector_search_results)
                logger.info(f"Vector search: {len(vector_results)} results")
            except Exception as e:
                logger.error(f"Vector search failed: {e}", exc_info=True)
                vector_degraded = True

            # If both failed, return empty results with warning
            if graph_degraded or not graph_results:
                logger.error("Both Graph and Vector search failed. Returning empty results.")
                return []

        # 3. Merge and Rank
        merged_results = self._merge_results(
            graph_results, vector_results, graph_weight, vector_weight
        )

        # 4. Sort by final score
        merged_results.sort(key=lambda r: r.score, reverse=True)

        return merged_results[:top_k]

    async def _graph_search(
        self,
        query: str,
        min_p_value: float,  # DEPRECATED v1.0
        evidence_levels: Optional[list[str]]
    ) -> GraphSearchResult:
        """Graph 검색 수행.

        Args:
            query: 검색 쿼리
            min_p_value: [DEPRECATED v1.0] p-value 임계값 (no longer used in scoring)
            evidence_levels: 근거 수준 필터

        Returns:
            GraphSearchResult 객체
        """
        # Initialize CypherGenerator for query parsing
        cypher_gen = None
        if CYPHER_GENERATOR_AVAILABLE and CypherGenerator:
            try:
                cypher_gen = CypherGenerator()
            except Exception as e:
                logger.warning(f"Failed to initialize CypherGenerator: {e}")

        # Extract entities from query
        interventions: list[str] = []
        outcomes: list[str] = []
        pathologies: list[str] = []
        intent = "evidence_search"

        if cypher_gen:
            try:
                entities = cypher_gen.extract_entities(query)
                interventions = entities.get("interventions", [])
                outcomes = entities.get("outcomes", [])
                pathologies = entities.get("pathologies", [])
                intent = entities.get("intent", "evidence_search")
                logger.debug(f"Extracted entities: {entities}")
            except Exception as e:
                logger.warning(f"Entity extraction failed: {e}")

        evidences: list[GraphEvidence] = []
        paper_nodes: list[PaperNode] = []
        papers_dict: dict[str, PaperNode] = {}

        # Build Cypher query based on extracted entities
        if interventions and outcomes:
            # Intervention → Outcome search
            # v1.15: WHERE 절을 MATCH와 OPTIONAL MATCH 사이로 이동 (결과 누락 방지)
            cypher = """
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
            WHERE (a.is_significant = true OR a.p_value < $min_p_value)
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            RETURN i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.value_control as value_control,
                   a.p_value as p_value,
                   a.effect_size as effect_size,
                   a.confidence_interval as confidence_interval,
                   a.is_significant as is_significant,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id,
                   p.paper_id as paper_id,
                   p.title as paper_title,
                   p.year as paper_year,
                   p.journal as paper_journal,
                   p.evidence_level as evidence_level
            ORDER BY a.p_value ASC
            LIMIT 50
            """
            for intervention in interventions:
                for outcome in outcomes:
                    try:
                        results = await self.neo4j_client.run_query(
                            cypher,
                            {
                                "intervention": intervention,
                                "outcome": outcome,
                                "min_p_value": min_p_value
                            }
                        )
                        for row in results:
                            ev_level = row.get("evidence_level", "5") or "5"
                            if evidence_levels and ev_level not in evidence_levels:
                                continue
                            evidences.append(GraphEvidence(
                                intervention=row.get("intervention", intervention),
                                outcome=row.get("outcome", outcome),
                                value=str(row.get("value", "")),
                                source_paper_id=row.get("source_paper_id", ""),
                                evidence_level=ev_level,
                                p_value=row.get("p_value"),
                                effect_size=str(row.get("effect_size", "")),
                                confidence_interval=str(row.get("confidence_interval", "")),
                                is_significant=row.get("is_significant", False),
                                direction=row.get("direction", ""),
                                value_control=str(row.get("value_control", ""))
                            ))
                            # Collect paper info
                            pid = row.get("paper_id")
                            if pid and pid not in papers_dict:
                                papers_dict[pid] = PaperNode(
                                    paper_id=pid,
                                    title=row.get("paper_title", ""),
                                    year=row.get("paper_year", 0) or 0,
                                    journal=row.get("paper_journal", ""),
                                    evidence_level=ev_level
                                )
                    except Exception as e:
                        logger.error(f"Graph query error for {intervention}->{outcome}: {e}", exc_info=True)

        elif interventions:
            # Search for intervention's all outcomes
            # v1.15: WHERE 절을 MATCH와 OPTIONAL MATCH 사이로 이동 (결과 누락 방지)
            cypher = """
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome)
            WHERE (a.is_significant = true OR a.p_value < $min_p_value)
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            RETURN i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.p_value as p_value,
                   a.effect_size as effect_size,
                   a.is_significant as is_significant,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id,
                   p.paper_id as paper_id,
                   p.title as paper_title,
                   p.evidence_level as evidence_level
            ORDER BY a.p_value ASC
            LIMIT 50
            """
            for intervention in interventions:
                try:
                    results = await self.neo4j_client.run_query(
                        cypher,
                        {"intervention": intervention, "min_p_value": min_p_value}
                    )
                    for row in results:
                        ev_level = row.get("evidence_level", "5") or "5"
                        if evidence_levels and ev_level not in evidence_levels:
                            continue
                        evidences.append(GraphEvidence(
                            intervention=row.get("intervention", intervention),
                            outcome=row.get("outcome", ""),
                            value=str(row.get("value", "")),
                            source_paper_id=row.get("source_paper_id", ""),
                            evidence_level=ev_level,
                            p_value=row.get("p_value"),
                            effect_size=str(row.get("effect_size", "")),
                            is_significant=row.get("is_significant", False),
                            direction=row.get("direction", "")
                        ))
                        pid = row.get("paper_id")
                        if pid and pid not in papers_dict:
                            papers_dict[pid] = PaperNode(
                                paper_id=pid,
                                title=row.get("paper_title", ""),
                                evidence_level=ev_level
                            )
                except Exception as e:
                    logger.error(f"Graph query error for {intervention}: {e}", exc_info=True)

        elif outcomes:
            # Search for outcome's all interventions
            # v1.15: WHERE 절을 MATCH와 OPTIONAL MATCH 사이로 이동 (결과 누락 방지)
            cypher = """
            MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: $outcome})
            WHERE (a.is_significant = true OR a.p_value < $min_p_value)
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            RETURN i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.p_value as p_value,
                   a.is_significant as is_significant,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id,
                   p.paper_id as paper_id,
                   p.title as paper_title,
                   p.evidence_level as evidence_level
            ORDER BY a.p_value ASC
            LIMIT 50
            """
            for outcome in outcomes:
                try:
                    results = await self.neo4j_client.run_query(
                        cypher,
                        {"outcome": outcome, "min_p_value": min_p_value}
                    )
                    for row in results:
                        ev_level = row.get("evidence_level", "5") or "5"
                        if evidence_levels and ev_level not in evidence_levels:
                            continue
                        evidences.append(GraphEvidence(
                            intervention=row.get("intervention", ""),
                            outcome=row.get("outcome", outcome),
                            value=str(row.get("value", "")),
                            source_paper_id=row.get("source_paper_id", ""),
                            evidence_level=ev_level,
                            p_value=row.get("p_value"),
                            is_significant=row.get("is_significant", False),
                            direction=row.get("direction", "")
                        ))
                        pid = row.get("paper_id")
                        if pid and pid not in papers_dict:
                            papers_dict[pid] = PaperNode(
                                paper_id=pid,
                                title=row.get("paper_title", ""),
                                evidence_level=ev_level
                            )
                except Exception as e:
                    logger.error(f"Graph query error for {outcome}: {e}", exc_info=True)

        elif pathologies:
            # Search for pathology's interventions
            cypher = """
            MATCH (i:Intervention)-[:TREATS]->(path:Pathology {name: $pathology})
            OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WHERE a IS NULL OR a.is_significant = true
            RETURN DISTINCT i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.p_value as p_value,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id,
                   p.paper_id as paper_id,
                   p.title as paper_title,
                   p.evidence_level as evidence_level
            LIMIT 50
            """
            for pathology in pathologies:
                try:
                    results = await self.neo4j_client.run_query(
                        cypher,
                        {"pathology": pathology}
                    )
                    for row in results:
                        if row.get("outcome"):
                            ev_level = row.get("evidence_level", "5") or "5"
                            evidences.append(GraphEvidence(
                                intervention=row.get("intervention", ""),
                                outcome=row.get("outcome", ""),
                                value=str(row.get("value", "")),
                                source_paper_id=row.get("source_paper_id", ""),
                                evidence_level=ev_level,
                                p_value=row.get("p_value"),
                                direction=row.get("direction", "")
                            ))
                        pid = row.get("paper_id")
                        if pid and pid not in papers_dict:
                            papers_dict[pid] = PaperNode(
                                paper_id=pid,
                                title=row.get("paper_title", ""),
                                evidence_level=row.get("evidence_level", "5") or "5"
                            )
                except Exception as e:
                    logger.error(f"Graph query error for {pathology}: {e}", exc_info=True)

        else:
            # Fallback: search recent papers with outcomes
            cypher = """
            MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WHERE a.is_significant = true
            RETURN i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.p_value as p_value,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id,
                   p.paper_id as paper_id,
                   p.title as paper_title,
                   p.evidence_level as evidence_level
            ORDER BY p.year DESC
            LIMIT 30
            """
            try:
                results = await self.neo4j_client.run_query(cypher)
                for row in results:
                    ev_level = row.get("evidence_level", "5") or "5"
                    evidences.append(GraphEvidence(
                        intervention=row.get("intervention", ""),
                        outcome=row.get("outcome", ""),
                        value=str(row.get("value", "")),
                        source_paper_id=row.get("source_paper_id", ""),
                        evidence_level=ev_level,
                        p_value=row.get("p_value"),
                        direction=row.get("direction", "")
                    ))
                    pid = row.get("paper_id")
                    if pid and pid not in papers_dict:
                        papers_dict[pid] = PaperNode(
                            paper_id=pid,
                            title=row.get("paper_title", ""),
                            evidence_level=ev_level
                        )
            except Exception as e:
                logger.error(f"Graph fallback query error: {e}", exc_info=True)

        paper_nodes = list(papers_dict.values())

        logger.info(
            f"Graph search complete: {len(evidences)} evidences, "
            f"{len(paper_nodes)} papers, intent={intent}"
        )

        return GraphSearchResult(
            evidences=evidences,
            paper_nodes=paper_nodes,
            query_type=intent
        )

    def _score_graph_results(self, graph_result: GraphSearchResult) -> list[HybridResult]:
        """Graph 검색 결과 점수화 (v1.0).

        v1.0 Changes:
        - REMOVED: P-value scoring, effect size scoring, significance boost
        - ADDED: Evidence-based authority scoring

        점수 계산 (NEW):
            1. Evidence Level Weight (0.1~1.0)
            2. Base score from evidence level (backward compatible)
            3. Note: Full authority scoring applied in vector results

        Args:
            graph_result: GraphSearchResult 객체

        Returns:
            점수가 계산된 HybridResult 목록
        """
        results: list[HybridResult] = []

        # 논문 정보를 딕셔너리로 변환
        papers_dict = {p.paper_id: p for p in graph_result.paper_nodes}

        for evidence in graph_result.evidences:
            # 1. Evidence Level Weight (primary scoring)
            evidence_weight = EVIDENCE_LEVEL_WEIGHTS.get(
                evidence.evidence_level, 0.1
            )

            # v1.0: Simplified scoring - evidence level is the primary signal
            # Direction matters (improved > unchanged > worsened)
            direction_boost = 1.0
            if evidence.direction == "improved":
                direction_boost = DIRECTION_IMPROVED_BOOST
            elif evidence.direction == "worsened":
                direction_boost = DIRECTION_WORSENED_BOOST
            elif evidence.direction == "unchanged":
                direction_boost = DIRECTION_UNCHANGED_BOOST

            # Final Score (simplified)
            final_score = evidence_weight * direction_boost

            # Normalize to 0~1
            final_score = min(final_score, 1.0)

            # Get paper info
            paper = papers_dict.get(evidence.source_paper_id)

            results.append(HybridResult(
                result_type="graph",
                score=final_score,
                content=evidence.get_display_text(),
                source_id=evidence.source_paper_id,
                evidence=evidence,
                paper=paper,
                metadata={
                    # DEPRECATED fields (kept for backward compatibility)
                    "p_value": evidence.p_value,
                    "is_significant": evidence.is_significant,
                    # Active fields
                    "evidence_level": evidence.evidence_level,
                    "direction": evidence.direction,
                    "intervention": evidence.intervention,
                    "outcome": evidence.outcome,
                }
            ))

        return results

    def _score_vector_results(
        self, vector_results: list[VectorSearchResult]
    ) -> list[HybridResult]:
        """Vector 검색 결과 점수화 (v1.0).

        v1.0 Changes:
        - NEW: Authority score calculation (evidence + design + recency + sample + citations)
        - Formula: 60% semantic + 40% authority

        점수 계산:
            1. Base Semantic Score: ChromaDB similarity score
            2. Evidence Level Boost
            3. Key Finding Boost: 1.2x if is_key_finding
            4. Statistics Boost: 1.1x if has_statistics
            5. Authority Score: Study design, recency, sample size, citations
            6. Final: 0.6 × semantic + 0.4 × authority

        Args:
            vector_results: VectorSearchResult 목록

        Returns:
            점수가 계산된 HybridResult 목록
        """
        results: list[HybridResult] = []

        for vr in vector_results:
            # 1. Base Semantic Score (ChromaDB similarity)
            semantic_score = vr.score

            # 2. Evidence Level Boost
            evidence_weight = EVIDENCE_LEVEL_WEIGHTS.get(vr.evidence_level, 0.1)
            semantic_score *= (0.5 + 0.5 * evidence_weight)

            # 3. Key Finding Boost
            if vr.is_key_finding:
                semantic_score *= KEY_FINDING_BOOST

            # 4. Statistics Boost
            if vr.has_statistics:
                semantic_score *= STATISTICS_BOOST

            # 5. Calculate Authority Score (v1.0)
            authority_score = self._calculate_authority_score_from_metadata(vr)

            # 6. Combine: semantic + authority (weighted)
            final_score = DEFAULT_SEMANTIC_WEIGHT * semantic_score + DEFAULT_AUTHORITY_WEIGHT * authority_score

            # Normalize to 0~1
            final_score = min(final_score, 1.0)

            results.append(HybridResult(
                result_type="vector",
                score=final_score,
                content=vr.content,
                source_id=vr.chunk_id,
                vector_result=vr,
                metadata={
                    "tier": vr.tier,
                    "section": vr.section,
                    "evidence_level": vr.evidence_level,
                    "is_key_finding": vr.is_key_finding,
                    "has_statistics": vr.has_statistics,
                    "semantic_score": semantic_score,
                    "authority_score": authority_score,
                    "ranking_version": "v1.0",
                }
            ))

        return results

    def _calculate_authority_score_from_metadata(self, vr: VectorSearchResult) -> float:
        """Calculate authority score from vector result metadata (v1.0).

        Args:
            vr: VectorSearchResult with metadata

        Returns:
            Authority score (0.0-1.0+)
        """
        # Extract paper metadata from vector result
        # Note: VectorSearchResult may not have all fields, use safe defaults

        # Evidence weight (primary)
        evidence_weight = EVIDENCE_LEVEL_WEIGHTS.get(vr.evidence_level, 0.1)

        # Study design weight (from publication_types if available)
        publication_types = getattr(vr, 'publication_types', None)
        design_weight = get_study_design_weight(publication_types)

        # Recency boost
        year = getattr(vr, 'publication_year', None)
        recency_boost = get_recency_boost(year) if year else 1.0

        # Sample size boost (if available)
        sample_size = getattr(vr, 'sample_size', None)
        sample_boost = get_sample_size_boost(sample_size)

        # Citation boost (if available)
        citation_count = getattr(vr, 'citation_count', None)
        citation_boost = get_citation_boost(citation_count)

        # Combined authority score
        authority_score = (
            evidence_weight
            * design_weight
            * sample_boost
            * recency_boost
            * citation_boost
        )

        return authority_score

    async def _neo4j_hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        graph_weight: float,
        vector_weight: float,
        evidence_levels: Optional[list[str]],
        graph_filters: Optional[dict]
    ) -> list[HybridResult]:
        """Neo4j 통합 Hybrid Search (v5.3 + v1.0).

        Neo4j의 hybrid_search() 메서드를 사용하여
        그래프 필터링 + 벡터 검색을 단일 쿼리로 수행.

        v1.0: Updated scoring with authority metrics.

        Args:
            query: 검색 쿼리 (자연어)
            query_embedding: 쿼리 임베딩 (MedTE: 768d, OpenAI: 3072d)
            top_k: 반환할 결과 수
            graph_weight: Graph 점수 가중치
            vector_weight: Vector 점수 가중치
            evidence_levels: 허용할 근거 수준
            graph_filters: 그래프 필터

        Returns:
            HybridResult 목록
        """
        if not self.neo4j_client:
            logger.warning("Neo4j client not available for hybrid search")
            return []

        try:
            # 그래프 필터에 evidence_levels 추가
            filters = graph_filters.copy() if graph_filters else {}
            if evidence_levels:
                filters["evidence_levels"] = evidence_levels

            # Neo4j hybrid_search 호출
            raw_results = await self.neo4j_client.hybrid_search(
                embedding=query_embedding,
                graph_filters=filters,
                top_k=top_k,
                graph_weight=graph_weight,
                vector_weight=vector_weight
            )

            logger.info(f"Neo4j hybrid search: {len(raw_results)} results")

            # 결과 변환 (v1.0 scoring)
            results: list[HybridResult] = []
            for raw in raw_results:
                # Evidence Level 가중치 계산
                evidence_level = raw.get("evidence_level", "5") or "5"
                evidence_weight = EVIDENCE_LEVEL_WEIGHTS.get(evidence_level, 0.1)

                # Key finding 부스트
                kf_boost = KEY_FINDING_BOOST if raw.get("is_key_finding", False) else 1.0

                # v1.0: Calculate authority score from paper metadata
                paper_year = raw.get("paper_year", 0)
                publication_types = raw.get("publication_types", [])

                design_weight = get_study_design_weight(publication_types)
                recency_boost = get_recency_boost(paper_year) if paper_year else 1.0

                # Semantic score (from Neo4j vector similarity)
                semantic_score = raw.get("score", 0.0) * kf_boost

                # Authority score
                authority_score = evidence_weight * design_weight * recency_boost

                # Combined: semantic + authority (weighted)
                final_score = DEFAULT_SEMANTIC_WEIGHT * semantic_score + DEFAULT_AUTHORITY_WEIGHT * authority_score
                final_score = min(final_score, 1.0)

                results.append(HybridResult(
                    result_type="hybrid",
                    score=final_score,
                    content=raw.get("content", ""),
                    source_id=raw.get("chunk_id", ""),
                    metadata={
                        "paper_id": raw.get("paper_id", ""),
                        "paper_title": raw.get("paper_title", ""),
                        "tier": raw.get("tier", ""),
                        "section": raw.get("section", ""),
                        "evidence_level": evidence_level,
                        "is_key_finding": raw.get("is_key_finding", False),
                        "vector_score": raw.get("score", 0.0),
                        "graph_score": raw.get("graph_score", 0.0),
                        "semantic_score": semantic_score,
                        "authority_score": authority_score,
                        "backend": "neo4j_hybrid",
                        "ranking_version": "v1.0",
                    }
                ))

            # 점수순 정렬
            results.sort(key=lambda r: r.score, reverse=True)

            return results[:top_k]

        except Exception as e:
            logger.error(f"Neo4j hybrid search failed: {e}", exc_info=True)
            # Fallback to traditional search
            logger.info("Falling back to traditional Graph search")
            self.use_neo4j_hybrid = False  # 일시적으로 비활성화

            # 기존 방식으로 재시도
            graph_results: list[HybridResult] = []
            try:
                graph_search_result = await self._graph_search(
                    query, 0.05, evidence_levels
                )
                graph_results = self._score_graph_results(graph_search_result)
            except Exception as ge:
                logger.warning(f"Graph search also failed: {ge}")

            vector_results: list[HybridResult] = []
            try:
                vector_search_results = self.vector_db.search_all(
                    query_embedding=query_embedding,
                    top_k=top_k * 2,
                    tier1_weight=1.0,
                    tier2_weight=0.7
                )
                vector_results = self._score_vector_results(vector_search_results)
            except Exception as ve:
                logger.warning(f"Vector search also failed: {ve}")

            if not graph_results and not vector_results:
                return []

            merged = self._merge_results(
                graph_results, vector_results, graph_weight, vector_weight
            )
            merged.sort(key=lambda r: r.score, reverse=True)
            return merged[:top_k]

    def _merge_results(
        self,
        graph_results: list[HybridResult],
        vector_results: list[HybridResult],
        graph_weight: float,
        vector_weight: float
    ) -> list[HybridResult]:
        """Graph + Vector 결과 병합.

        가중치 적용:
            - Graph 결과: score *= graph_weight
            - Vector 결과: score *= vector_weight

        중복 제거:
            - 같은 논문(paper_id)에서 온 결과는 점수가 높은 것만 유지

        Args:
            graph_results: Graph 결과 목록
            vector_results: Vector 결과 목록
            graph_weight: Graph 가중치
            vector_weight: Vector 가중치

        Returns:
            병합된 HybridResult 목록
        """
        # 1. 가중치 적용 (use copies to avoid mutating input scores)
        weighted_graph = []
        for gr in graph_results:
            weighted_score = gr.score * graph_weight
            weighted_graph.append(HybridResult(
                result_type=gr.result_type,
                score=weighted_score,
                content=gr.content,
                source_id=gr.source_id,
                metadata=gr.metadata,
                evidence=gr.evidence,
                paper=gr.paper,
                vector_result=gr.vector_result,
            ))

        weighted_vector = []
        for vr in vector_results:
            weighted_score = vr.score * vector_weight
            weighted_vector.append(HybridResult(
                result_type=vr.result_type,
                score=weighted_score,
                content=vr.content,
                source_id=vr.source_id,
                metadata=vr.metadata,
                evidence=vr.evidence,
                paper=vr.paper,
                vector_result=vr.vector_result,
            ))

        # 2. 병합
        all_results = weighted_graph + weighted_vector

        # 3. 중복 제거 (같은 source_id는 점수 높은 것만)
        deduped: dict[str, HybridResult] = {}
        for result in all_results:
            source_id = result.source_id
            if source_id not in deduped or result.score > deduped[source_id].score:
                deduped[source_id] = result

        return list(deduped.values())

    def get_stats(self) -> dict[str, Any]:
        """통계 정보 반환.

        Returns:
            Vector DB 통계 및 Graph DB 연결 상태
        """
        stats: dict[str, Any] = {
            "vector_db": self.vector_db.get_stats() if self.vector_db else None,
            "graph_db_available": self.neo4j_client is not None,
            "neo4j_hybrid_enabled": self.use_neo4j_hybrid,  # v5.3
            "search_backend": "neo4j_hybrid" if self.use_neo4j_hybrid else "neo4j_cypher",
            "ranking_version": "v1.0",  # NEW
        }

        return stats


# ============================================================================
# Usage Example
# ============================================================================

async def example_usage() -> None:
    """Hybrid Ranker 사용 예시 (v1.0).

    Neo4j hybrid search를 사용합니다 (v1.14.12: ChromaDB 제거됨).
    """
    from ..graph.neo4j_client import Neo4jClient

    # Neo4j 클라이언트 초기화
    neo4j_client = Neo4jClient()
    await neo4j_client.connect()

    # Hybrid Ranker 초기화 (Neo4j hybrid search)
    ranker: HybridRanker = HybridRanker(
        neo4j_client=neo4j_client,
        use_neo4j_hybrid=True,
    )

    # 검색 쿼리 (embedding은 별도 생성 필요)
    query: str = "What are effective interventions for reducing PJK in ASD surgery?"
    query_embedding: list[float] = [0.0] * 3072  # placeholder

    # Hybrid 검색 (v1.0 evidence-based ranking)
    results: list[HybridResult] = await ranker.search(
        query=query,
        query_embedding=query_embedding,
        top_k=10,
        graph_weight=0.6,
        vector_weight=0.4,
    )

    # 결과 출력
    for i, result in enumerate(results, 1):
        print(f"{i}. [{result.result_type}] Score: {result.score:.3f}")
        print(f"   {result.get_evidence_text()}")

    await neo4j_client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
