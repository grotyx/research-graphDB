"""Relationship Reasoner.

**DEPRECATED**: This module is deprecated as of v5.2.
Paper-to-Paper relationships are now managed in Neo4j.

Legacy LLM-based inference of relationships between papers.
Enhanced with embedding-based similarity and PageRank-based confidence scoring.

v3.2: Added graph-based confidence scoring using PageRank and centrality metrics.
v5.2: Deprecated in favor of Neo4j native relationship management.

Migration Path:
- Paper relationships now created via `src/graph/relationship_builder.py`
- Citation extraction via `src/builder/important_citation_processor.py`
- Conflict detection via `src/solver/conflict_detector.py`
"""

import warnings

warnings.warn(
    "relationship_reasoner.py is deprecated. Use Neo4j-based relationship management instead.",
    DeprecationWarning,
    stacklevel=2
)

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from typing import Union
from llm import LLMClient, ClaudeClient, GeminiClient
from core.bounded_cache import BoundedCache
from core.embedding import EmbeddingGenerator, cosine_similarity
from .paper_graph import PaperGraph, PaperNode, PaperRelation, RelationType, PICOSummary

logger = logging.getLogger(__name__)


@dataclass
class RelationshipAnalysis:
    """관계 분석 결과."""
    relation_type: RelationType
    confidence: float
    evidence: str
    reasoning: str


@dataclass
class SimilarityScore:
    """유사도 점수 상세."""
    pico_embedding_sim: float
    keyword_embedding_sim: float
    title_embedding_sim: float
    combined: float
    method: str  # "embedding" or "text"


@dataclass
class GraphCentralityScore:
    """그래프 기반 중심성 점수.

    Attributes:
        pagerank: PageRank 점수 (0-1, 높을수록 중요)
        degree_centrality: Degree Centrality (연결 수 기반)
        betweenness: Betweenness Centrality (경로 중심성)
        combined: 가중 평균 중심성 점수
    """
    pagerank: float = 0.0
    degree_centrality: float = 0.0
    betweenness: float = 0.0
    combined: float = 0.0


class PageRankScorer:
    """PageRank 기반 논문 중요도 점수 계산기.

    그래프 구조에서 논문의 중요도를 계산하여 confidence 점수 보정에 사용.
    """

    def __init__(self):
        self._graph: Optional[nx.DiGraph] = None
        self._pagerank_cache = BoundedCache(maxsize=200)
        self._centrality_cache = BoundedCache(maxsize=200)
        self._is_dirty: bool = True

    def build_graph(self, papers: list[PaperNode], relations: list[PaperRelation]) -> None:
        """논문과 관계로부터 그래프 구축.

        Args:
            papers: 논문 노드 목록
            relations: 논문 간 관계 목록
        """
        self._graph = nx.DiGraph()

        # 노드 추가
        for paper in papers:
            self._graph.add_node(
                paper.paper_id,
                title=paper.title,
                year=paper.year
            )

        # 엣지 추가 (관계 유형별 가중치)
        edge_weights = {
            RelationType.SUPPORTS: 1.2,
            RelationType.CONTRADICTS: 1.0,
            RelationType.EXTENDS: 1.5,
            RelationType.SIMILAR_TOPIC: 0.8,
            RelationType.CITES: 1.3,
            RelationType.REPLICATES: 1.4,
        }

        for rel in relations:
            weight = edge_weights.get(rel.relation_type, 1.0) * rel.confidence
            self._graph.add_edge(
                rel.source_id,
                rel.target_id,
                weight=weight,
                relation_type=rel.relation_type.value
            )

        self._is_dirty = True
        self._pagerank_cache.clear()
        self._centrality_cache.clear()

    def _compute_centralities(self) -> None:
        """모든 중심성 지표 계산."""
        if not self._graph or not self._is_dirty:
            return

        if len(self._graph.nodes()) == 0:
            return

        try:
            # PageRank 계산
            pagerank = nx.pagerank(self._graph, weight='weight', alpha=0.85)
            self._pagerank_cache.clear()
            for nid, score in pagerank.items():
                self._pagerank_cache.set(nid, score)

            # Degree Centrality (undirected로 변환해서 계산)
            undirected = self._graph.to_undirected()
            degree_cent = nx.degree_centrality(undirected)

            # Betweenness Centrality
            betweenness = nx.betweenness_centrality(undirected, weight='weight')

            # 정규화 및 캐시 저장
            max_pr = max(pagerank.values()) if pagerank else 1.0
            max_dc = max(degree_cent.values()) if degree_cent else 1.0
            max_bt = max(betweenness.values()) if betweenness else 1.0

            for node_id in self._graph.nodes():
                pr = pagerank.get(node_id, 0.0) / max_pr if max_pr > 0 else 0.0
                dc = degree_cent.get(node_id, 0.0) / max_dc if max_dc > 0 else 0.0
                bt = betweenness.get(node_id, 0.0) / max_bt if max_bt > 0 else 0.0

                # Combined: PageRank 50%, Degree 30%, Betweenness 20%
                combined = (pr * 0.5) + (dc * 0.3) + (bt * 0.2)

                self._centrality_cache.set(node_id, GraphCentralityScore(
                    pagerank=pr,
                    degree_centrality=dc,
                    betweenness=bt,
                    combined=combined
                ))

            self._is_dirty = False

        except Exception as e:
            logger.warning(f"Failed to compute centralities: {e}")
            self._is_dirty = False

    def get_paper_centrality(self, paper_id: str) -> GraphCentralityScore:
        """논문의 중심성 점수 반환.

        Args:
            paper_id: 논문 ID

        Returns:
            GraphCentralityScore (없으면 기본값 반환)
        """
        if self._is_dirty:
            self._compute_centralities()

        return self._centrality_cache.get(
            paper_id,
            GraphCentralityScore()
        )

    def adjust_confidence(
        self,
        base_confidence: float,
        source_id: str,
        target_id: str
    ) -> float:
        """중심성 기반 confidence 보정.

        Args:
            base_confidence: 기본 confidence 점수 (임베딩/LLM 기반)
            source_id: 소스 논문 ID
            target_id: 타겟 논문 ID

        Returns:
            보정된 confidence (0.0 ~ 1.0)
        """
        source_score = self.get_paper_centrality(source_id)
        target_score = self.get_paper_centrality(target_id)

        # 두 논문의 평균 중심성으로 boost 계산
        avg_centrality = (source_score.combined + target_score.combined) / 2

        # Boost factor: 0.9 ~ 1.1 (중심성에 따라 최대 10% 조정)
        boost = 0.9 + (avg_centrality * 0.2)

        adjusted = base_confidence * boost

        # 범위 제한
        return max(0.0, min(1.0, adjusted))

    @property
    def node_count(self) -> int:
        """그래프의 노드 수."""
        return len(self._graph.nodes()) if self._graph else 0

    @property
    def edge_count(self) -> int:
        """그래프의 엣지 수."""
        return len(self._graph.edges()) if self._graph else 0


class RelationshipReasoner:
    """논문 간 관계 추론기.

    Embedding 기반 PICO 유사도와 LLM 분석을 결합하여 논문 간 관계를 추론합니다.
    """

    # 핵심 의학 용어 (키워드 추출 보강용)
    CORE_MEDICAL_TERMS = {
        # Surgical approaches
        "endoscopic", "biportal", "uniportal", "microscopic", "minimally invasive",
        "open", "percutaneous", "arthroscopic", "laparoscopic",
        # Spine procedures
        "discectomy", "laminectomy", "laminotomy", "foraminotomy", "fusion",
        "decompression", "corpectomy", "nucleoplasty",
        # Spine conditions
        "stenosis", "herniation", "spondylolisthesis", "scoliosis", "kyphosis",
        "disc", "vertebral", "lumbar", "cervical", "thoracic", "sacral",
        # Study types
        "randomized", "controlled", "prospective", "retrospective", "cohort",
        "meta-analysis", "systematic review", "rct",
        # Outcomes
        "odi", "vas", "sf-36", "eq-5d", "joa", "outcomes", "complications",
    }

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        paper_graph: Optional[PaperGraph] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        pagerank_scorer: Optional[PageRankScorer] = None,
        gemini_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None  # 하위 호환성
    ):
        """Initialize reasoner.

        Args:
            llm_client: LLM API 클라이언트 (Claude 또는 Gemini)
            paper_graph: 논문 그래프
            embedding_generator: 임베딩 생성기 (None이면 자동 생성)
            pagerank_scorer: PageRank 기반 점수 계산기 (None이면 자동 생성)
            gemini_client: (Deprecated) 하위 호환성을 위한 파라미터, llm_client 사용 권장
        """
        # 하위 호환성: gemini_client가 전달되면 llm_client로 사용
        client = llm_client or gemini_client
        self.llm = client
        self.gemini = self.llm  # 하위 호환성 속성
        self.graph = paper_graph
        self._embedder = embedding_generator
        self._embedding_cache = BoundedCache(maxsize=1000)
        self._pagerank_scorer = pagerank_scorer or PageRankScorer()
        self._graph_initialized = False

    @property
    def embedder(self) -> EmbeddingGenerator:
        """Lazy loading of embedding generator."""
        if self._embedder is None:
            self._embedder = EmbeddingGenerator()
        return self._embedder

    @property
    def pagerank_scorer(self) -> PageRankScorer:
        """PageRank scorer 반환."""
        return self._pagerank_scorer

    async def initialize_graph_metrics(self) -> None:
        """그래프 중심성 지표 초기화.

        기존 논문과 관계로부터 PageRank 등 중심성 지표를 계산합니다.
        새 논문 분석 전에 호출하면 confidence 점수가 더 정확해집니다.
        """
        if not self.graph or self._graph_initialized:
            return

        try:
            papers = await self.graph.list_papers(limit=1000)
            relations = []

            # 모든 논문의 관계 수집
            for paper in papers:
                paper_relations = await self.graph.get_relations(paper.paper_id)
                relations.extend(paper_relations)

            # 중복 제거
            seen = set()
            unique_relations = []
            for rel in relations:
                key = (rel.source_id, rel.target_id, rel.relation_type.value)
                if key not in seen:
                    seen.add(key)
                    unique_relations.append(rel)

            self._pagerank_scorer.build_graph(papers, unique_relations)
            self._graph_initialized = True

            logger.info(
                f"Initialized graph metrics: {self._pagerank_scorer.node_count} nodes, "
                f"{self._pagerank_scorer.edge_count} edges"
            )

        except Exception as e:
            logger.warning(f"Failed to initialize graph metrics: {e}")

    def _get_embedding(self, text: str) -> list[float]:
        """캐시된 임베딩 반환."""
        if not text:
            return []

        cache_key = text[:200]  # 캐시 키는 앞부분만
        cached = self._embedding_cache.get(cache_key)
        if cached is None:
            cached = self.embedder.embed(text)
            self._embedding_cache.set(cache_key, cached)
        return cached

    async def analyze_support_conflict(
        self,
        paper_a: PaperNode,
        paper_b: PaperNode
    ) -> Optional[PaperRelation]:
        """두 논문의 결과가 상충/지지하는지 분석.

        Args:
            paper_a: 첫 번째 논문
            paper_b: 두 번째 논문

        Returns:
            PaperRelation 또는 None (관계 없음)
        """
        if not self.gemini:
            return self._analyze_with_rules(paper_a, paper_b)

        try:
            return await self._analyze_with_llm(paper_a, paper_b)
        except Exception as e:
            logger.warning(f"LLM analysis failed, falling back to rules: {e}")
            return self._analyze_with_rules(paper_a, paper_b)

    async def _analyze_with_llm(
        self,
        paper_a: PaperNode,
        paper_b: PaperNode
    ) -> Optional[PaperRelation]:
        """LLM으로 관계 분석."""
        prompt = f"""Analyze the relationship between these two research papers.

Paper A:
- Title: {paper_a.title}
- Abstract Summary: {paper_a.abstract_summary}
- Main Findings: {', '.join(paper_a.main_findings) if paper_a.main_findings else 'Not specified'}
- PICO:
  * Population: {paper_a.pico_summary.population if paper_a.pico_summary else 'Not specified'}
  * Intervention: {paper_a.pico_summary.intervention if paper_a.pico_summary else 'Not specified'}
  * Comparison: {paper_a.pico_summary.comparison if paper_a.pico_summary else 'Not specified'}
  * Outcome: {paper_a.pico_summary.outcome if paper_a.pico_summary else 'Not specified'}

Paper B:
- Title: {paper_b.title}
- Abstract Summary: {paper_b.abstract_summary}
- Main Findings: {', '.join(paper_b.main_findings) if paper_b.main_findings else 'Not specified'}
- PICO:
  * Population: {paper_b.pico_summary.population if paper_b.pico_summary else 'Not specified'}
  * Intervention: {paper_b.pico_summary.intervention if paper_b.pico_summary else 'Not specified'}
  * Comparison: {paper_b.pico_summary.comparison if paper_b.pico_summary else 'Not specified'}
  * Outcome: {paper_b.pico_summary.outcome if paper_b.pico_summary else 'Not specified'}

Determine if these papers:
1. "supports" - Paper A's findings support Paper B's conclusions
2. "contradicts" - Paper A's findings contradict Paper B's conclusions
3. "similar_topic" - Papers study similar topics but findings are not directly comparable
4. "extends" - Paper A extends or builds upon Paper B's research
5. "no_relation" - Papers are unrelated

Return JSON:
{{
  "relation_type": "supports|contradicts|similar_topic|extends|no_relation",
  "confidence": 0.0-1.0,
  "evidence": "Brief explanation of the key comparison points",
  "reasoning": "Detailed reasoning for the classification"
}}"""

        response = await self.gemini.generate_json(prompt, {
            "type": "OBJECT",
            "properties": {
                "relation_type": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "evidence": {"type": "STRING"},
                "reasoning": {"type": "STRING"}
            },
            "required": ["relation_type", "confidence", "evidence"]
        })

        rel_type_str = response.get("relation_type", "no_relation")
        if rel_type_str == "no_relation":
            return None

        rel_type_map = {
            "supports": RelationType.SUPPORTS,
            "contradicts": RelationType.CONTRADICTS,
            "similar_topic": RelationType.SIMILAR_TOPIC,
            "extends": RelationType.EXTENDS,
        }

        rel_type = rel_type_map.get(rel_type_str)
        if not rel_type:
            return None

        # LLM confidence에 PageRank 기반 보정 적용
        base_confidence = response.get("confidence", 0.5)
        adjusted_confidence = self._pagerank_scorer.adjust_confidence(
            base_confidence,
            paper_a.paper_id,
            paper_b.paper_id
        )

        return PaperRelation(
            source_id=paper_a.paper_id,
            target_id=paper_b.paper_id,
            relation_type=rel_type,
            confidence=adjusted_confidence,
            evidence=response.get("evidence", ""),
            detected_by="llm_analysis+pagerank",
        )

    def _analyze_with_rules(
        self,
        paper_a: PaperNode,
        paper_b: PaperNode
    ) -> Optional[PaperRelation]:
        """규칙 기반 관계 분석 (embedding + PageRank 기반)."""
        similarity = self.calculate_similarity(paper_a, paper_b)

        if similarity.combined >= 0.5:
            # Embedding similarity에 PageRank 기반 보정 적용
            adjusted_confidence = self._pagerank_scorer.adjust_confidence(
                similarity.combined,
                paper_a.paper_id,
                paper_b.paper_id
            )

            # 중심성 점수 가져오기 (evidence에 포함)
            source_centrality = self._pagerank_scorer.get_paper_centrality(paper_a.paper_id)
            target_centrality = self._pagerank_scorer.get_paper_centrality(paper_b.paper_id)

            return PaperRelation(
                source_id=paper_a.paper_id,
                target_id=paper_b.paper_id,
                relation_type=RelationType.SIMILAR_TOPIC,
                confidence=adjusted_confidence,
                evidence=f"PICO sim: {similarity.pico_embedding_sim:.2f}, "
                        f"KW sim: {similarity.keyword_embedding_sim:.2f}, "
                        f"Title sim: {similarity.title_embedding_sim:.2f}, "
                        f"PageRank boost: {source_centrality.pagerank:.2f}/{target_centrality.pagerank:.2f}",
                detected_by=f"embedding+pagerank_{similarity.method}",
            )

        return None

    def calculate_similarity(
        self,
        paper_a: PaperNode,
        paper_b: PaperNode
    ) -> SimilarityScore:
        """Embedding 기반 유사도 계산.

        Args:
            paper_a: 첫 번째 논문
            paper_b: 두 번째 논문

        Returns:
            SimilarityScore with detailed breakdown
        """
        # 1. PICO 텍스트 생성 및 임베딩 유사도
        pico_text_a = self._pico_to_text(paper_a.pico_summary)
        pico_text_b = self._pico_to_text(paper_b.pico_summary)

        if pico_text_a and pico_text_b:
            emb_a = self._get_embedding(pico_text_a)
            emb_b = self._get_embedding(pico_text_b)
            pico_sim = cosine_similarity(emb_a, emb_b) if emb_a and emb_b else 0.0
        else:
            pico_sim = 0.0

        # 2. 키워드 임베딩 유사도 (확장된 키워드 포함)
        keywords_a = self._extract_enhanced_keywords(paper_a)
        keywords_b = self._extract_enhanced_keywords(paper_b)

        if keywords_a and keywords_b:
            kw_text_a = " ".join(keywords_a)
            kw_text_b = " ".join(keywords_b)
            emb_kw_a = self._get_embedding(kw_text_a)
            emb_kw_b = self._get_embedding(kw_text_b)
            keyword_sim = cosine_similarity(emb_kw_a, emb_kw_b) if emb_kw_a and emb_kw_b else 0.0
        else:
            keyword_sim = 0.0

        # 3. 제목 임베딩 유사도
        if paper_a.title and paper_b.title:
            title_emb_a = self._get_embedding(paper_a.title)
            title_emb_b = self._get_embedding(paper_b.title)
            title_sim = cosine_similarity(title_emb_a, title_emb_b) if title_emb_a and title_emb_b else 0.0
        else:
            title_sim = 0.0

        # 4. Combined similarity (가중 평균)
        # PICO 40%, Keywords 30%, Title 30%
        combined = (pico_sim * 0.4) + (keyword_sim * 0.3) + (title_sim * 0.3)

        return SimilarityScore(
            pico_embedding_sim=pico_sim,
            keyword_embedding_sim=keyword_sim,
            title_embedding_sim=title_sim,
            combined=combined,
            method="embedding"
        )

    def _pico_to_text(self, pico: Optional[PICOSummary]) -> str:
        """PICO를 검색 가능한 텍스트로 변환."""
        if not pico:
            return ""

        parts = []
        if pico.population:
            parts.append(f"Population: {pico.population}")
        if pico.intervention:
            parts.append(f"Intervention: {pico.intervention}")
        if pico.comparison:
            parts.append(f"Comparison: {pico.comparison}")
        if pico.outcome:
            parts.append(f"Outcome: {pico.outcome}")

        return ". ".join(parts)

    def _extract_enhanced_keywords(self, paper: PaperNode) -> list[str]:
        """향상된 키워드 추출 (핵심 의학 용어 포함).

        기존 키워드 + 제목/PICO에서 핵심 의학 용어 추출
        """
        keywords = set()

        # 1. 기존 키워드 추가
        if paper.keywords:
            keywords.update(k.lower() for k in paper.keywords)

        # 2. 제목에서 핵심 용어 추출
        if paper.title:
            title_lower = paper.title.lower()
            for term in self.CORE_MEDICAL_TERMS:
                if term in title_lower:
                    keywords.add(term)

        # 3. PICO에서 핵심 용어 추출
        if paper.pico_summary:
            pico_text = self._pico_to_text(paper.pico_summary).lower()
            for term in self.CORE_MEDICAL_TERMS:
                if term in pico_text:
                    keywords.add(term)

        # 4. Abstract에서 핵심 용어 추출
        if paper.abstract_summary:
            abstract_lower = paper.abstract_summary.lower()
            for term in self.CORE_MEDICAL_TERMS:
                if term in abstract_lower:
                    keywords.add(term)

        return list(keywords)

    def _calculate_keyword_similarity(
        self,
        keywords_a: list[str],
        keywords_b: list[str]
    ) -> float:
        """키워드 유사도 계산 (Jaccard) - fallback용."""
        if not keywords_a or not keywords_b:
            return 0.0

        set_a = set(k.lower() for k in keywords_a)
        set_b = set(k.lower() for k in keywords_b)

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        if union == 0:
            return 0.0

        return intersection / union

    async def analyze_new_paper_relations(
        self,
        new_paper: PaperNode,
        max_comparisons: int = 20,
        min_similarity: float = 0.3
    ) -> list[PaperRelation]:
        """새 논문과 기존 논문들의 관계 분석.

        Embedding + PageRank 기반 유사도로 후보를 필터링하고 LLM으로 상세 분석.

        Args:
            new_paper: 새로 추가된 논문
            max_comparisons: 최대 비교 횟수
            min_similarity: 최소 유사도 (이 이상인 것만 LLM 분석)

        Returns:
            생성된 PaperRelation 목록
        """
        if not self.graph:
            return []

        # PageRank 등 그래프 메트릭 초기화 (첫 호출 시에만 계산)
        await self.initialize_graph_metrics()

        # 기존 논문 목록 가져오기
        existing_papers = await self.graph.list_papers(limit=100)
        existing_papers = [p for p in existing_papers if p.paper_id != new_paper.paper_id]

        if not existing_papers:
            logger.info("No existing papers to compare with")
            return []

        # Embedding 기반 유사도로 후보 필터링
        candidates = []
        for paper in existing_papers:
            similarity = self.calculate_similarity(new_paper, paper)

            logger.debug(
                f"Similarity with {paper.paper_id[:30]}...: "
                f"PICO={similarity.pico_embedding_sim:.3f}, "
                f"KW={similarity.keyword_embedding_sim:.3f}, "
                f"Title={similarity.title_embedding_sim:.3f}, "
                f"Combined={similarity.combined:.3f}"
            )

            if similarity.combined >= min_similarity:
                candidates.append((paper, similarity))

        logger.info(
            f"Found {len(candidates)} candidate papers "
            f"(similarity >= {min_similarity}) out of {len(existing_papers)}"
        )

        # 유사도 높은 순으로 정렬
        candidates.sort(key=lambda x: x[1].combined, reverse=True)
        candidates = candidates[:max_comparisons]

        # 관계 분석 (LLM 사용 가능하면 LLM, 아니면 규칙 기반)
        relations = []
        for paper, similarity in candidates:
            logger.info(
                f"Analyzing relation with: {paper.title[:50]}... "
                f"(similarity: {similarity.combined:.3f})"
            )

            relation = await self.analyze_support_conflict(new_paper, paper)
            if relation:
                relations.append(relation)
                if self.graph:
                    await self.graph.add_relation(relation)
                logger.info(
                    f"Found relation: {relation.relation_type.value} "
                    f"(confidence: {relation.confidence:.2f})"
                )

        return relations

    async def find_similar_papers(
        self,
        paper: PaperNode,
        top_k: int = 5,
        min_similarity: float = 0.3
    ) -> list[tuple[PaperNode, SimilarityScore]]:
        """유사 논문 찾기.

        Args:
            paper: 기준 논문
            top_k: 반환할 최대 논문 수
            min_similarity: 최소 유사도

        Returns:
            [(PaperNode, SimilarityScore), ...] 유사도 높은 순
        """
        if not self.graph:
            return []

        all_papers = await self.graph.list_papers(limit=1000)
        all_papers = [p for p in all_papers if p.paper_id != paper.paper_id]

        similarities = []
        for other in all_papers:
            score = self.calculate_similarity(paper, other)
            if score.combined >= min_similarity:
                similarities.append((other, score))

        # 유사도 높은 순 정렬
        similarities.sort(key=lambda x: x[1].combined, reverse=True)

        return similarities[:top_k]

    async def cluster_by_topic(
        self,
        min_cluster_size: int = 2,
        similarity_threshold: float = 0.5
    ) -> dict[str, list[str]]:
        """PICO 기반 논문 클러스터링.

        Args:
            min_cluster_size: 최소 클러스터 크기
            similarity_threshold: 유사도 임계값

        Returns:
            {cluster_name: [paper_id, ...]} 딕셔너리
        """
        if not self.graph:
            return {}

        papers = await self.graph.list_papers(limit=1000)
        if len(papers) < 2:
            return {}

        # 간단한 클러스터링: 첫 번째 키워드 기반
        clusters: dict[str, list[str]] = {}

        for paper in papers:
            # 확장된 키워드 사용
            enhanced_keywords = self._extract_enhanced_keywords(paper)

            if enhanced_keywords:
                # 가장 중요한 키워드를 클러스터 키로 사용
                key = enhanced_keywords[0].lower()
            elif paper.pico_summary and paper.pico_summary.intervention:
                # PICO intervention을 클러스터 키로
                key = paper.pico_summary.intervention.lower().split()[0]
            else:
                key = "uncategorized"

            if key not in clusters:
                clusters[key] = []
            clusters[key].append(paper.paper_id)

        # 최소 크기 미만 클러스터 제거
        clusters = {k: v for k, v in clusters.items() if len(v) >= min_cluster_size}

        return clusters

    async def reason_multi_hop(
        self,
        question: str,
        start_paper_id: Optional[str] = None,
        max_hops: int = 3
    ) -> dict:
        """여러 논문을 연결하는 추론.

        Args:
            question: 추론할 질문
            start_paper_id: 시작 논문 ID (None이면 전체에서 검색)
            max_hops: 최대 홉 수

        Returns:
            {
                "answer": str,
                "reasoning_chain": [{"paper": PaperNode, "contribution": str}, ...],
                "confidence": float
            }
        """
        if not self.graph or not self.gemini:
            return {
                "answer": "Multi-hop reasoning requires both PaperGraph and Gemini client",
                "reasoning_chain": [],
                "confidence": 0.0
            }

        # 시작점 결정
        if start_paper_id:
            start_paper = await self.graph.get_paper(start_paper_id)
            if not start_paper:
                return {
                    "answer": f"Paper not found: {start_paper_id}",
                    "reasoning_chain": [],
                    "confidence": 0.0
                }
            papers = [start_paper]

            # 관련 논문 추가
            relations = await self.graph.get_relations(start_paper_id)
            for rel in relations:
                related_id = rel.target_id if rel.source_id == start_paper_id else rel.source_id
                related_paper = await self.graph.get_paper(related_id)
                if related_paper:
                    papers.append(related_paper)
        else:
            papers = await self.graph.list_papers(limit=20)

        if not papers:
            return {
                "answer": "No papers available for reasoning",
                "reasoning_chain": [],
                "confidence": 0.0
            }

        # LLM으로 추론
        papers_context = "\n\n".join([
            f"Paper {i+1}: {p.title}\n"
            f"Summary: {p.abstract_summary}\n"
            f"Findings: {', '.join(p.main_findings) if p.main_findings else 'Not specified'}\n"
            f"Year: {p.year or 'Unknown'}"
            for i, p in enumerate(papers[:10])
        ])

        prompt = f"""Based on the following research papers, answer the question by connecting findings across multiple papers.

Papers:
{papers_context}

Question: {question}

Provide a comprehensive answer that:
1. Synthesizes findings from multiple papers
2. Shows how one paper's findings relate to another's
3. Notes any conflicts or agreements between papers

Return JSON:
{{
  "answer": "Your synthesized answer",
  "reasoning_chain": [
    {{"paper_index": 1, "contribution": "How this paper contributes to the answer"}},
    {{"paper_index": 2, "contribution": "How this paper contributes"}}
  ],
  "confidence": 0.0-1.0
}}"""

        try:
            response = await self.gemini.generate_json(prompt, {
                "type": "OBJECT",
                "properties": {
                    "answer": {"type": "STRING"},
                    "reasoning_chain": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "paper_index": {"type": "INTEGER"},
                                "contribution": {"type": "STRING"}
                            }
                        }
                    },
                    "confidence": {"type": "NUMBER"}
                }
            })

            # 인덱스를 실제 논문으로 변환
            chain = []
            for item in response.get("reasoning_chain", []):
                idx = item.get("paper_index", 1) - 1
                if 0 <= idx < len(papers):
                    chain.append({
                        "paper": papers[idx],
                        "contribution": item.get("contribution", "")
                    })

            return {
                "answer": response.get("answer", ""),
                "reasoning_chain": chain,
                "confidence": response.get("confidence", 0.5)
            }

        except Exception as e:
            logger.warning(f"Multi-hop reasoning failed: {e}")
            return {
                "answer": f"Error during reasoning: {str(e)}",
                "reasoning_chain": [],
                "confidence": 0.0
            }

    async def find_evidence_chain(
        self,
        claim: str,
        max_papers: int = 5
    ) -> dict:
        """주장을 뒷받침하는 논문 체인 찾기.

        Args:
            claim: 검증할 주장
            max_papers: 최대 논문 수

        Returns:
            {
                "supporting_papers": [(PaperNode, evidence_strength), ...],
                "contradicting_papers": [(PaperNode, evidence_strength), ...],
                "summary": str
            }
        """
        if not self.graph or not self.gemini:
            return {
                "supporting_papers": [],
                "contradicting_papers": [],
                "summary": "Evidence chain finding requires both PaperGraph and Gemini client"
            }

        papers = await self.graph.list_papers(limit=50)
        if not papers:
            return {
                "supporting_papers": [],
                "contradicting_papers": [],
                "summary": "No papers available"
            }

        # LLM으로 논문 평가
        papers_context = "\n".join([
            f"{i+1}. {p.title} ({p.year or 'Year unknown'}): {p.abstract_summary[:200]}..."
            for i, p in enumerate(papers[:20])
        ])

        prompt = f"""Evaluate how each paper relates to this claim:

Claim: "{claim}"

Papers:
{papers_context}

For each relevant paper, determine if it:
- Supports the claim (provides evidence for it)
- Contradicts the claim (provides evidence against it)
- Is neutral/irrelevant

Return JSON:
{{
  "evaluations": [
    {{"paper_index": 1, "stance": "supports|contradicts|neutral", "strength": 0.0-1.0, "reason": "brief reason"}}
  ],
  "summary": "Overall assessment of evidence"
}}"""

        try:
            response = await self.gemini.generate_json(prompt, {
                "type": "OBJECT",
                "properties": {
                    "evaluations": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "paper_index": {"type": "INTEGER"},
                                "stance": {"type": "STRING"},
                                "strength": {"type": "NUMBER"},
                                "reason": {"type": "STRING"}
                            }
                        }
                    },
                    "summary": {"type": "STRING"}
                }
            })

            supporting = []
            contradicting = []

            for eval_item in response.get("evaluations", []):
                idx = eval_item.get("paper_index", 1) - 1
                if idx < 0 or idx >= len(papers):
                    continue

                paper = papers[idx]
                strength = eval_item.get("strength", 0.5)
                stance = eval_item.get("stance", "neutral")

                if stance == "supports" and strength > 0.3:
                    supporting.append((paper, strength))
                elif stance == "contradicts" and strength > 0.3:
                    contradicting.append((paper, strength))

            # 강도 순으로 정렬
            supporting.sort(key=lambda x: x[1], reverse=True)
            contradicting.sort(key=lambda x: x[1], reverse=True)

            return {
                "supporting_papers": supporting[:max_papers],
                "contradicting_papers": contradicting[:max_papers],
                "summary": response.get("summary", "")
            }

        except Exception as e:
            logger.warning(f"Evidence chain finding failed: {e}")
            return {
                "supporting_papers": [],
                "contradicting_papers": [],
                "summary": f"Error: {str(e)}"
            }

    async def compare_papers(
        self,
        paper_ids: list[str]
    ) -> dict:
        """여러 논문 비교 분석.

        Args:
            paper_ids: 비교할 논문 ID 목록

        Returns:
            비교 분석 결과
        """
        if not self.graph or not self.gemini:
            return {"error": "Comparison requires both PaperGraph and Gemini client"}

        papers = []
        for pid in paper_ids:
            paper = await self.graph.get_paper(pid)
            if paper:
                papers.append(paper)

        if len(papers) < 2:
            return {"error": "At least 2 papers required for comparison"}

        papers_context = "\n\n".join([
            f"Paper {i+1}: {p.title}\n"
            f"Year: {p.year or 'Unknown'}\n"
            f"Summary: {p.abstract_summary}\n"
            f"Findings: {', '.join(p.main_findings) if p.main_findings else 'Not specified'}\n"
            f"PICO - P: {p.pico_summary.population if p.pico_summary else 'N/A'}, "
            f"I: {p.pico_summary.intervention if p.pico_summary else 'N/A'}, "
            f"C: {p.pico_summary.comparison if p.pico_summary else 'N/A'}, "
            f"O: {p.pico_summary.outcome if p.pico_summary else 'N/A'}"
            for i, p in enumerate(papers)
        ])

        prompt = f"""Compare the following research papers comprehensively:

{papers_context}

Analyze:
1. Similarities in methodology, population, intervention
2. Differences in findings and conclusions
3. Contradictions or conflicts
4. Overall synthesis

Return JSON:
{{
  "similarities": ["similarity 1", "similarity 2"],
  "differences": ["difference 1", "difference 2"],
  "contradictions": ["contradiction 1"],
  "synthesis": "Overall synthesis of findings",
  "recommendation": "Which paper(s) provide stronger evidence and why"
}}"""

        try:
            response = await self.gemini.generate_json(prompt, {
                "type": "OBJECT",
                "properties": {
                    "similarities": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "differences": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "contradictions": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "synthesis": {"type": "STRING"},
                    "recommendation": {"type": "STRING"}
                }
            })

            return {
                "papers": [{"id": p.paper_id, "title": p.title, "year": p.year} for p in papers],
                "analysis": response
            }

        except Exception as e:
            logger.warning(f"Paper comparison failed: {e}")
            return {"error": str(e)}
