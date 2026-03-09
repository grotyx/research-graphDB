"""GraphRAG 2.0 - Microsoft-style Community-based Knowledge Graph RAG.

Microsoft GraphRAG 스타일의 커뮤니티 탐지 및 계층적 요약 기반 검색.
- Community Detection: Louvain 알고리즘으로 intervention-outcome 그래프에서 커뮤니티 탐지
- Hierarchical Summarization: 각 커뮤니티를 LLM으로 요약하여 계층 구조 생성
- Global Search: 커뮤니티 요약 기반 광범위한 질문 답변
- Local Search: 엔티티 중심 세밀한 검색
- Hybrid Search: Global + Local 결합

References:
    - Microsoft GraphRAG: https://microsoft.github.io/graphrag/
    - Community Detection: Louvain algorithm
    - Map-Reduce Summarization: LLM-based hierarchical aggregation
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

import networkx as nx

try:
    import community as community_louvain  # python-louvain
    LOUVAIN_AVAILABLE = True
except ImportError:
    LOUVAIN_AVAILABLE = False
    community_louvain = None

from typing import Union
from ..graph.neo4j_client import Neo4jClient
from ..llm import LLMClient, LLMConfig, ClaudeClient, GeminiClient

logger = logging.getLogger(__name__)


class SearchType(Enum):
    """검색 타입."""
    GLOBAL = "global"  # 커뮤니티 요약 기반 광범위한 검색
    LOCAL = "local"    # 엔티티 중심 세밀한 검색
    HYBRID = "hybrid"  # 두 방식 결합


@dataclass
class Community:
    """커뮤니티 데이터 구조.

    Attributes:
        id: 커뮤니티 ID (예: "community_0", "community_1_2")
        level: 계층 레벨 (0 = leaf, 1 = mid, 2 = top)
        members: 커뮤니티 멤버 노드 목록 (intervention/outcome names)
        parent_id: 상위 커뮤니티 ID (None이면 최상위)
        summary: LLM 생성 커뮤니티 요약
        evidence_count: 포함된 근거 수 (AFFECTS 관계 수)
        avg_p_value: 평균 p-value
    """
    id: str
    level: int
    members: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    summary: str = ""
    evidence_count: int = 0
    avg_p_value: float = 1.0

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "id": self.id,
            "level": self.level,
            "members": self.members,
            "parent_id": self.parent_id,
            "summary": self.summary,
            "evidence_count": self.evidence_count,
            "avg_p_value": self.avg_p_value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Community":
        """딕셔너리에서 생성."""
        return cls(
            id=data["id"],
            level=data["level"],
            members=data.get("members", []),
            parent_id=data.get("parent_id"),
            summary=data.get("summary", ""),
            evidence_count=data.get("evidence_count", 0),
            avg_p_value=data.get("avg_p_value", 1.0),
        )


@dataclass
class CommunityHierarchy:
    """커뮤니티 계층 구조.

    Attributes:
        levels: 계층별 커뮤니티 목록 {level: [Community, ...]}
        communities: 모든 커뮤니티 {id: Community}
        graph: NetworkX 그래프 (intervention-outcome)
        max_level: 최대 계층 레벨
    """
    levels: dict[int, list[Community]] = field(default_factory=dict)
    communities: dict[str, Community] = field(default_factory=dict)
    graph: Optional[nx.Graph] = None
    max_level: int = 0

    def add_community(self, community: Community) -> None:
        """커뮤니티 추가."""
        self.communities[community.id] = community

        if community.level not in self.levels:
            self.levels[community.level] = []
        self.levels[community.level].append(community)

        if community.level > self.max_level:
            self.max_level = community.level

    def get_community(self, community_id: str) -> Optional[Community]:
        """커뮤니티 조회."""
        return self.communities.get(community_id)

    def get_communities_by_level(self, level: int) -> list[Community]:
        """레벨별 커뮤니티 조회."""
        return self.levels.get(level, [])

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (Neo4j 저장용)."""
        return {
            "max_level": self.max_level,
            "communities": {
                cid: comm.to_dict()
                for cid, comm in self.communities.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommunityHierarchy":
        """딕셔너리에서 생성."""
        hierarchy = cls(max_level=data.get("max_level", 0))

        for cid, comm_data in data.get("communities", {}).items():
            community = Community.from_dict(comm_data)
            hierarchy.add_community(community)

        return hierarchy


@dataclass
class GraphRAGResult:
    """GraphRAG 검색 결과.

    Attributes:
        answer: 최종 답변
        communities_used: 사용된 커뮤니티 목록
        evidence: 근거 정보 목록
        confidence: 신뢰도 (0-1)
        search_type: 사용된 검색 타입
        reasoning: 추론 과정 설명
    """
    answer: str
    communities_used: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    search_type: SearchType = SearchType.HYBRID
    reasoning: str = ""


class CommunityDetector:
    """커뮤니티 탐지기 (Louvain 알고리즘 기반).

    Intervention-Outcome 그래프에서 커뮤니티를 탐지하고 계층 구조를 생성합니다.
    """

    def __init__(self, neo4j_client: Neo4jClient):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
        """
        self.neo4j = neo4j_client

    async def detect_communities(
        self,
        resolution: float = 1.0,
        min_community_size: int = 3
    ) -> CommunityHierarchy:
        """커뮤니티 탐지.

        Args:
            resolution: Louvain 알고리즘 resolution (높을수록 작은 커뮤니티)
            min_community_size: 최소 커뮤니티 크기

        Returns:
            CommunityHierarchy 객체
        """
        logger.info("커뮤니티 탐지 시작...")

        # 1. Neo4j에서 그래프 데이터 가져오기
        graph_data = await self._fetch_graph_data()

        # 2. NetworkX 그래프 구축
        G = self._build_networkx_graph(graph_data)

        # 3. Louvain 커뮤니티 탐지 (여러 레벨)
        hierarchy = await self._detect_hierarchical_communities(
            G,
            resolution,
            min_community_size
        )

        # 4. 그래프 저장
        hierarchy.graph = G

        logger.info(
            f"커뮤니티 탐지 완료: {len(hierarchy.communities)}개 커뮤니티, "
            f"{hierarchy.max_level + 1}개 레벨"
        )

        return hierarchy

    async def _fetch_graph_data(self) -> dict:
        """Neo4j에서 intervention-outcome 그래프 데이터 가져오기.

        Returns:
            {"nodes": [...], "edges": [...]} 형식
        """
        query = """
        MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
        RETURN i.name as intervention, o.name as outcome,
               a.p_value as p_value, a.is_significant as is_significant,
               a.direction as direction, a.value as value,
               a.source_paper_id as source_paper
        """

        results = await self.neo4j.run_query(query)

        # 노드 추출 (중복 제거)
        interventions = set()
        outcomes = set()
        edges = []

        for record in results:
            intervention = record["intervention"]
            outcome = record["outcome"]

            interventions.add(intervention)
            outcomes.add(outcome)

            edges.append({
                "source": intervention,
                "target": outcome,
                "p_value": record.get("p_value", 1.0),
                "is_significant": record.get("is_significant", False),
                "direction": record.get("direction", ""),
                "value": record.get("value", ""),
                "source_paper": record.get("source_paper", ""),
            })

        nodes = [
            {"id": node, "type": "intervention"}
            for node in interventions
        ] + [
            {"id": node, "type": "outcome"}
            for node in outcomes
        ]

        return {"nodes": nodes, "edges": edges}

    def _build_networkx_graph(self, graph_data: dict) -> nx.Graph:
        """NetworkX 그래프 구축.

        Args:
            graph_data: {"nodes": [...], "edges": [...]}

        Returns:
            NetworkX Graph
        """
        G = nx.Graph()

        # 노드 추가
        for node in graph_data["nodes"]:
            G.add_node(node["id"], type=node["type"])

        # 엣지 추가 (가중치 = 통계적 유의성)
        for edge in graph_data["edges"]:
            # p-value가 작을수록 강한 연결 (weight = 1 - p_value)
            p_value = edge.get("p_value", 1.0)
            weight = 1.0 - p_value if p_value < 1.0 else 0.1

            # 유의성 보너스
            if edge.get("is_significant"):
                weight *= 1.5

            G.add_edge(
                edge["source"],
                edge["target"],
                weight=weight,
                p_value=p_value,
                is_significant=edge.get("is_significant", False),
                direction=edge.get("direction", ""),
            )

        logger.info(f"NetworkX 그래프 구축: {G.number_of_nodes()} 노드, {G.number_of_edges()} 엣지")

        return G

    async def _detect_hierarchical_communities(
        self,
        G: nx.Graph,
        resolution: float,
        min_size: int
    ) -> CommunityHierarchy:
        """계층적 커뮤니티 탐지.

        Args:
            G: NetworkX 그래프
            resolution: Louvain resolution
            min_size: 최소 커뮤니티 크기

        Returns:
            CommunityHierarchy
        """
        hierarchy = CommunityHierarchy()

        if not LOUVAIN_AVAILABLE:
            logger.warning("python-louvain not installed. Using simple clustering.")
            return await self._simple_clustering(G, hierarchy, min_size)

        # Louvain 알고리즘 실행
        partition = community_louvain.best_partition(
            G,
            weight='weight',
            resolution=resolution
        )

        # 커뮤니티별로 노드 그룹화
        communities_dict = defaultdict(list)
        for node, comm_id in partition.items():
            communities_dict[comm_id].append(node)

        # Level 0 커뮤니티 생성 (leaf level)
        for comm_id, members in communities_dict.items():
            if len(members) >= min_size:
                # 통계 계산
                stats = await self._compute_community_stats(G, members)

                community = Community(
                    id=f"community_L0_{comm_id}",
                    level=0,
                    members=members,
                    parent_id=None,
                    evidence_count=stats["evidence_count"],
                    avg_p_value=stats["avg_p_value"],
                )

                hierarchy.add_community(community)

        # Level 1 커뮤니티 생성 (mid-level aggregation)
        if len(hierarchy.levels.get(0, [])) > 5:
            await self._create_mid_level_communities(hierarchy, G)

        # Level 2 커뮤니티 생성 (top-level summary)
        if hierarchy.max_level > 0:
            await self._create_top_level_community(hierarchy, G)

        return hierarchy

    async def _simple_clustering(
        self,
        G: nx.Graph,
        hierarchy: CommunityHierarchy,
        min_size: int
    ) -> CommunityHierarchy:
        """Simple clustering (Louvain 없을 때 fallback).

        연결된 컴포넌트를 커뮤니티로 사용.
        """
        for i, component in enumerate(nx.connected_components(G)):
            if len(component) >= min_size:
                members = list(component)
                stats = await self._compute_community_stats(G, members)

                community = Community(
                    id=f"community_L0_{i}",
                    level=0,
                    members=members,
                    evidence_count=stats["evidence_count"],
                    avg_p_value=stats["avg_p_value"],
                )

                hierarchy.add_community(community)

        return hierarchy

    async def _compute_community_stats(
        self,
        G: nx.Graph,
        members: list[str]
    ) -> dict:
        """커뮤니티 통계 계산.

        Args:
            G: NetworkX 그래프
            members: 커뮤니티 멤버 노드 목록

        Returns:
            {"evidence_count": int, "avg_p_value": float}
        """
        # 커뮤니티 내부 엣지 추출
        subgraph = G.subgraph(members)
        edges = list(subgraph.edges(data=True))

        if not edges:
            return {"evidence_count": 0, "avg_p_value": 1.0}

        p_values = [data.get("p_value", 1.0) for _, _, data in edges]
        avg_p = sum(p_values) / len(p_values) if p_values else 1.0

        return {
            "evidence_count": len(edges),
            "avg_p_value": avg_p,
        }

    async def _create_mid_level_communities(
        self,
        hierarchy: CommunityHierarchy,
        G: nx.Graph
    ) -> None:
        """중간 레벨 커뮤니티 생성 (level 0 → level 1 aggregation)."""
        level_0_communities = hierarchy.get_communities_by_level(0)

        # 3-4개씩 묶어서 mid-level 생성
        batch_size = 4
        for i in range(0, len(level_0_communities), batch_size):
            batch = level_0_communities[i:i + batch_size]

            # 모든 멤버 합치기
            all_members = []
            for comm in batch:
                all_members.extend(comm.members)

            stats = await self._compute_community_stats(G, all_members)

            mid_comm = Community(
                id=f"community_L1_{i // batch_size}",
                level=1,
                members=all_members,
                parent_id=None,
                evidence_count=stats["evidence_count"],
                avg_p_value=stats["avg_p_value"],
            )

            hierarchy.add_community(mid_comm)

            # 하위 커뮤니티에 parent 설정
            for comm in batch:
                comm.parent_id = mid_comm.id

    async def _create_top_level_community(
        self,
        hierarchy: CommunityHierarchy,
        G: nx.Graph
    ) -> None:
        """최상위 레벨 커뮤니티 생성 (전체 요약)."""
        # 모든 레벨 1 커뮤니티 합치기
        level_1_communities = hierarchy.get_communities_by_level(1)

        all_members = []
        for comm in level_1_communities:
            all_members.extend(comm.members)

        # 중복 제거
        all_members = list(set(all_members))

        stats = await self._compute_community_stats(G, all_members)

        top_comm = Community(
            id="community_L2_0",
            level=2,
            members=all_members,
            parent_id=None,
            evidence_count=stats["evidence_count"],
            avg_p_value=stats["avg_p_value"],
        )

        hierarchy.add_community(top_comm)

        # 하위 커뮤니티에 parent 설정
        for comm in level_1_communities:
            comm.parent_id = top_comm.id


class CommunitySummarizer:
    """커뮤니티 요약 생성기 (LLM 기반).

    각 커뮤니티의 intervention-outcome 관계를 LLM으로 요약합니다.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient]
    ):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
        """
        self.neo4j = neo4j_client
        self.llm = llm_client

    async def summarize_hierarchy(
        self,
        hierarchy: CommunityHierarchy
    ) -> CommunityHierarchy:
        """계층 구조의 모든 커뮤니티 요약.

        Args:
            hierarchy: 커뮤니티 계층 구조

        Returns:
            요약이 추가된 계층 구조
        """
        logger.info("커뮤니티 요약 생성 시작...")

        # Level 0부터 순차적으로 요약 (bottom-up)
        for level in sorted(hierarchy.levels.keys()):
            communities = hierarchy.get_communities_by_level(level)

            logger.info(f"Level {level} 커뮤니티 요약 중... ({len(communities)}개)")

            # 병렬 처리
            tasks = [
                self._summarize_community(comm, hierarchy)
                for comm in communities
            ]

            await asyncio.gather(*tasks)

        logger.info("커뮤니티 요약 완료")

        return hierarchy

    async def _summarize_community(
        self,
        community: Community,
        hierarchy: CommunityHierarchy
    ) -> None:
        """단일 커뮤니티 요약.

        Args:
            community: 커뮤니티 객체
            hierarchy: 전체 계층 구조
        """
        if community.level == 0:
            # Leaf level: 실제 데이터에서 요약
            summary = await self._summarize_from_data(community)
        else:
            # Higher level: 하위 커뮤니티 요약들을 aggregation
            summary = await self._aggregate_child_summaries(community, hierarchy)

        community.summary = summary

    async def _summarize_from_data(self, community: Community) -> str:
        """데이터에서 직접 요약 생성 (Level 0).

        Args:
            community: 커뮤니티 객체

        Returns:
            요약 문자열
        """
        # 커뮤니티 멤버의 intervention-outcome 관계 조회
        members_str = ", ".join([f"'{m}'" for m in community.members])

        query = f"""
        MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
        WHERE i.name IN [{members_str}] OR o.name IN [{members_str}]
        RETURN i.name as intervention, o.name as outcome,
               a.p_value as p_value, a.is_significant as is_significant,
               a.direction as direction, a.value as value,
               a.source_paper_id as source_paper
        LIMIT 50
        """

        results = await self.neo4j.run_query(query)

        if not results:
            return f"Empty community with members: {', '.join(community.members[:5])}"

        # 요약 프롬프트 생성
        evidence_text = self._format_evidence_for_summary(results)

        prompt = f"""다음은 척추 수술 분야의 intervention-outcome 관계 데이터입니다.

커뮤니티 ID: {community.id}
멤버 수: {len(community.members)}
근거 수: {community.evidence_count}

**Evidence:**
{evidence_text}

**Task:**
이 커뮤니티의 핵심 주제와 패턴을 2-3 문장으로 요약하세요.
- 주요 intervention들의 공통점
- 주요 outcome들의 유형
- 통계적으로 유의한 관계의 방향성

**Summary:**"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research summarization expert. Provide concise, evidence-based summaries.",
            use_cache=True
        )

        return response.text.strip()

    def _format_evidence_for_summary(self, results: list[dict]) -> str:
        """근거를 요약용 텍스트로 포맷팅."""
        lines = []

        for r in results[:20]:  # 최대 20개만
            intervention = r.get("intervention", "")
            outcome = r.get("outcome", "")
            p_value = r.get("p_value", 1.0)
            direction = r.get("direction", "")
            value = r.get("value", "")

            sig = "✓" if r.get("is_significant") else "✗"

            lines.append(
                f"- {intervention} → {outcome}: {direction} "
                f"(value={value}, p={p_value:.3f}) {sig}"
            )

        return "\n".join(lines)

    async def _aggregate_child_summaries(
        self,
        community: Community,
        hierarchy: CommunityHierarchy
    ) -> str:
        """하위 커뮤니티 요약들을 aggregation (Level 1+).

        Args:
            community: 현재 커뮤니티
            hierarchy: 전체 계층 구조

        Returns:
            Aggregated 요약
        """
        # 하위 커뮤니티 찾기
        child_communities = [
            comm for comm in hierarchy.communities.values()
            if comm.parent_id == community.id
        ]

        if not child_communities:
            return f"Aggregated community with {len(community.members)} members"

        # 하위 요약들 수집
        child_summaries = [
            f"**{comm.id}**: {comm.summary}"
            for comm in child_communities
        ]

        summaries_text = "\n\n".join(child_summaries)

        prompt = f"""다음은 하위 커뮤니티들의 요약입니다.

커뮤니티 ID: {community.id}
레벨: {community.level}
하위 커뮤니티 수: {len(child_communities)}

**Child Summaries:**
{summaries_text}

**Task:**
이 하위 커뮤니티들을 통합하여 상위 레벨의 요약을 2-3 문장으로 작성하세요.
- 공통 테마와 패턴
- 주요 intervention/outcome 카테고리
- 전체적인 연구 방향성

**Aggregated Summary:**"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research summarization expert. Provide high-level thematic summaries.",
            use_cache=True
        )

        return response.text.strip()


class GlobalSearchEngine:
    """전역 검색 엔진 (커뮤니티 요약 기반).

    광범위한 질문에 대해 커뮤니티 요약들을 map-reduce 방식으로 검색합니다.
    """

    def __init__(
        self,
        hierarchy: CommunityHierarchy,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient]
    ):
        """초기화.

        Args:
            hierarchy: 커뮤니티 계층 구조
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
        """
        self.hierarchy = hierarchy
        self.llm = llm_client

    async def search(
        self,
        query: str,
        max_communities: int = 10
    ) -> GraphRAGResult:
        """전역 검색.

        Args:
            query: 검색 쿼리
            max_communities: 최대 커뮤니티 수

        Returns:
            GraphRAGResult
        """
        logger.info(f"Global search: {query}")

        # 1. 관련 커뮤니티 선택 (top-level부터 시작)
        relevant_communities = await self._select_relevant_communities(
            query,
            max_communities
        )

        if not relevant_communities:
            return GraphRAGResult(
                answer="No relevant communities found.",
                search_type=SearchType.GLOBAL,
                confidence=0.0
            )

        # 2. Map: 각 커뮤니티 요약에 대해 부분 답변 생성
        partial_answers = await self._map_communities_to_answers(
            query,
            relevant_communities
        )

        # 3. Reduce: 부분 답변들을 종합
        final_answer = await self._reduce_answers(query, partial_answers)

        return GraphRAGResult(
            answer=final_answer,
            communities_used=[c.id for c in relevant_communities],
            confidence=0.8,
            search_type=SearchType.GLOBAL,
            reasoning=f"Searched {len(relevant_communities)} communities at multiple levels"
        )

    async def _select_relevant_communities(
        self,
        query: str,
        max_count: int
    ) -> list[Community]:
        """쿼리와 관련된 커뮤니티 선택.

        Args:
            query: 검색 쿼리
            max_count: 최대 개수

        Returns:
            관련 커뮤니티 목록
        """
        # 모든 레벨의 커뮤니티 수집
        all_communities = list(self.hierarchy.communities.values())

        # 요약이 있는 커뮤니티만
        communities_with_summary = [
            c for c in all_communities if c.summary
        ]

        if not communities_with_summary:
            return []

        # LLM으로 관련성 평가 (배치 처리)
        relevance_prompt = f"""Query: {query}

다음 커뮤니티들 중 이 쿼리와 가장 관련성이 높은 것을 선택하세요.

"""

        for i, comm in enumerate(communities_with_summary[:20]):  # 최대 20개
            relevance_prompt += f"\n{i+1}. **{comm.id}** (Level {comm.level}): {comm.summary}\n"

        relevance_prompt += f"\n\n가장 관련성 높은 커뮤니티 ID {max_count}개를 쉼표로 구분하여 나열하세요 (예: community_L0_1, community_L1_0):\n"

        response = await self.llm.generate(
            prompt=relevance_prompt,
            system="You are a medical research query analyzer.",
            use_cache=False
        )

        # 결과 파싱
        selected_ids = [
            id.strip()
            for id in response.text.split(",")
        ]

        selected = [
            self.hierarchy.get_community(cid)
            for cid in selected_ids
            if self.hierarchy.get_community(cid)
        ]

        return selected[:max_count]

    async def _map_communities_to_answers(
        self,
        query: str,
        communities: list[Community]
    ) -> list[dict]:
        """각 커뮤니티 요약에 대해 부분 답변 생성 (Map).

        Args:
            query: 검색 쿼리
            communities: 커뮤니티 목록

        Returns:
            [{"community_id": str, "answer": str}, ...]
        """
        tasks = [
            self._answer_from_community(query, comm)
            for comm in communities
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        partial_answers = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Map error for community {communities[i].id}: {result}")
                continue

            partial_answers.append(result)

        return partial_answers

    async def _answer_from_community(
        self,
        query: str,
        community: Community
    ) -> dict:
        """단일 커뮤니티 요약에서 부분 답변 생성.

        Args:
            query: 쿼리
            community: 커뮤니티

        Returns:
            {"community_id": str, "answer": str}
        """
        prompt = f"""Query: {query}

Community Summary:
{community.summary}

Based on this community summary, provide a partial answer to the query.
If the community is not relevant, respond with "N/A".

Answer:"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research assistant. Provide concise answers based on evidence.",
            use_cache=True
        )

        return {
            "community_id": community.id,
            "answer": response.text.strip()
        }

    async def _reduce_answers(
        self,
        query: str,
        partial_answers: list[dict]
    ) -> str:
        """부분 답변들을 종합 (Reduce).

        Args:
            query: 쿼리
            partial_answers: 부분 답변 목록

        Returns:
            최종 답변
        """
        # N/A 제거
        valid_answers = [
            a for a in partial_answers
            if a["answer"].strip().upper() != "N/A"
        ]

        if not valid_answers:
            return "No relevant information found in the knowledge graph."

        answers_text = "\n\n".join([
            f"**From {a['community_id']}:**\n{a['answer']}"
            for a in valid_answers
        ])

        prompt = f"""Query: {query}

다음은 여러 커뮤니티에서 수집된 부분 답변들입니다:

{answers_text}

**Task:**
이 부분 답변들을 종합하여 쿼리에 대한 최종 답변을 작성하세요.
- 중복 제거
- 일관성 있는 narrative
- 근거 기반 결론

Final Answer:"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research synthesis expert. Combine multiple perspectives into a coherent answer.",
            use_cache=False
        )

        return response.text.strip()


class LocalSearchEngine:
    """로컬 검색 엔진 (엔티티 중심).

    특정 intervention/outcome에 대한 세밀한 검색.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        hierarchy: CommunityHierarchy,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient]
    ):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            hierarchy: 커뮤니티 계층 구조
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
        """
        self.neo4j = neo4j_client
        self.hierarchy = hierarchy
        self.llm = llm_client

    async def search(
        self,
        query: str,
        max_hops: int = 2
    ) -> GraphRAGResult:
        """로컬 검색.

        Args:
            query: 검색 쿼리
            max_hops: 최대 탐색 depth

        Returns:
            GraphRAGResult
        """
        logger.info(f"Local search: {query}")

        # 1. 쿼리에서 엔티티 추출
        entities = await self._extract_entities(query)

        if not entities:
            return GraphRAGResult(
                answer="No entities found in query.",
                search_type=SearchType.LOCAL,
                confidence=0.0
            )

        # 2. 엔티티 주변 서브그래프 탐색
        subgraph_data = await self._explore_entity_neighborhood(
            entities,
            max_hops
        )

        # 3. 관련 커뮤니티 찾기
        related_communities = self._find_communities_for_entities(entities)

        # 4. 답변 생성
        answer = await self._generate_local_answer(
            query,
            entities,
            subgraph_data,
            related_communities
        )

        return GraphRAGResult(
            answer=answer,
            communities_used=[c.id for c in related_communities],
            evidence=subgraph_data,
            confidence=0.9,
            search_type=SearchType.LOCAL,
            reasoning=f"Explored {len(entities)} entities with {max_hops}-hop neighborhood"
        )

    async def _extract_entities(self, query: str) -> list[str]:
        """쿼리에서 엔티티 추출 (intervention/outcome).

        Args:
            query: 검색 쿼리

        Returns:
            엔티티 목록
        """
        # 간단한 키워드 매칭 (실제로는 NER 사용 가능)
        query_lower = query.lower()

        entities = []

        # Neo4j에서 모든 intervention/outcome 이름 가져오기
        interventions_query = "MATCH (i:Intervention) RETURN i.name as name"
        outcomes_query = "MATCH (o:Outcome) RETURN o.name as name"

        interventions = await self.neo4j.run_query(interventions_query)
        outcomes = await self.neo4j.run_query(outcomes_query)

        all_entities = [r["name"] for r in interventions] + [r["name"] for r in outcomes]

        # 쿼리에 포함된 엔티티 찾기
        for entity in all_entities:
            if entity.lower() in query_lower:
                entities.append(entity)

        return entities

    async def _explore_entity_neighborhood(
        self,
        entities: list[str],
        max_hops: int
    ) -> list[dict]:
        """엔티티 주변 서브그래프 탐색.

        Args:
            entities: 엔티티 목록
            max_hops: 최대 hop 수

        Returns:
            서브그래프 데이터 (엣지 목록)
        """
        entities_str = ", ".join([f"'{e}'" for e in entities])

        query = f"""
        MATCH path = (start)-[r:AFFECTS*1..{max_hops}]-(end)
        WHERE start.name IN [{entities_str}]
        UNWIND relationships(path) as rel
        WITH DISTINCT rel, startNode(rel) as source, endNode(rel) as target
        RETURN source.name as source_name, type(rel) as rel_type, target.name as target_name,
               rel.p_value as p_value, rel.is_significant as is_significant,
               rel.direction as direction, rel.value as value
        LIMIT 50
        """

        results = await self.neo4j.run_query(query)

        return results

    def _find_communities_for_entities(
        self,
        entities: list[str]
    ) -> list[Community]:
        """엔티티가 속한 커뮤니티 찾기.

        Args:
            entities: 엔티티 목록

        Returns:
            커뮤니티 목록
        """
        communities = []

        for comm in self.hierarchy.communities.values():
            if any(e in comm.members for e in entities):
                communities.append(comm)

        return communities

    async def _generate_local_answer(
        self,
        query: str,
        entities: list[str],
        subgraph_data: list[dict],
        communities: list[Community]
    ) -> str:
        """로컬 답변 생성.

        Args:
            query: 쿼리
            entities: 추출된 엔티티
            subgraph_data: 서브그래프 데이터
            communities: 관련 커뮤니티

        Returns:
            답변
        """
        # 서브그래프 포맷팅
        subgraph_text = "\n".join([
            f"- {r['source_name']} → {r['target_name']}: {r.get('direction', '')} "
            f"(p={r.get('p_value', 1.0):.3f})"
            for r in subgraph_data[:20]
        ])

        # 커뮤니티 요약 포맷팅
        community_text = "\n".join([
            f"- **{c.id}**: {c.summary}"
            for c in communities[:5]
        ])

        prompt = f"""Query: {query}

**Identified Entities:**
{', '.join(entities)}

**Local Evidence (Entity Neighborhood):**
{subgraph_text}

**Related Community Summaries:**
{community_text}

**Task:**
Based on the local evidence and community context, provide a detailed answer to the query.
Focus on specific relationships and statistical evidence.

Answer:"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research expert. Provide evidence-based answers with specific citations.",
            use_cache=False
        )

        return response.text.strip()


class GraphRAGPipeline:
    """GraphRAG 2.0 통합 파이프라인.

    커뮤니티 탐지, 요약, 검색을 통합 관리합니다.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        llm_config: Optional[LLMConfig] = None,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None
    ):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            llm_config: LLM 설정 (None이면 기본값)
            llm_client: LLM 클라이언트 (Claude 또는 Gemini, 테스트용)
        """
        self.neo4j = neo4j_client

        if llm_client:
            self.llm = llm_client
        else:
            self.llm = LLMClient(llm_config or LLMConfig())

        self.hierarchy: Optional[CommunityHierarchy] = None
        self.detector: Optional[CommunityDetector] = None
        self.summarizer: Optional[CommunitySummarizer] = None
        self.global_search_engine: Optional[GlobalSearchEngine] = None
        self.local_search_engine: Optional[LocalSearchEngine] = None

    async def build_index(
        self,
        resolution: float = 1.0,
        min_community_size: int = 3,
        force_rebuild: bool = False
    ) -> CommunityHierarchy:
        """인덱스 구축 (커뮤니티 탐지 + 요약).

        Args:
            resolution: Louvain resolution
            min_community_size: 최소 커뮤니티 크기
            force_rebuild: 기존 인덱스 무시하고 재구축

        Returns:
            CommunityHierarchy
        """
        logger.info("GraphRAG 인덱스 구축 시작...")

        # 1. 기존 인덱스 확인
        if not force_rebuild:
            loaded = await self._load_index_from_neo4j()
            if loaded:
                logger.info("기존 인덱스 로드 완료")
                self.hierarchy = loaded
                self._initialize_search_engines()
                return self.hierarchy

        # 2. 커뮤니티 탐지
        self.detector = CommunityDetector(self.neo4j)
        self.hierarchy = await self.detector.detect_communities(
            resolution,
            min_community_size
        )

        # 3. 커뮤니티 요약 생성
        self.summarizer = CommunitySummarizer(self.neo4j, self.llm)
        self.hierarchy = await self.summarizer.summarize_hierarchy(self.hierarchy)

        # 4. Neo4j에 저장
        await self._save_index_to_neo4j(self.hierarchy)

        # 5. 검색 엔진 초기화
        self._initialize_search_engines()

        logger.info("GraphRAG 인덱스 구축 완료")

        return self.hierarchy

    def _initialize_search_engines(self) -> None:
        """검색 엔진 초기화."""
        self.global_search_engine = GlobalSearchEngine(self.hierarchy, self.llm)
        self.local_search_engine = LocalSearchEngine(self.neo4j, self.hierarchy, self.llm)

    async def global_search(
        self,
        query: str,
        max_communities: int = 10
    ) -> GraphRAGResult:
        """전역 검색 (광범위한 질문).

        Args:
            query: 검색 쿼리
            max_communities: 최대 커뮤니티 수

        Returns:
            GraphRAGResult
        """
        if not self.global_search_engine:
            raise RuntimeError("Index not built. Call build_index() first.")

        return await self.global_search_engine.search(query, max_communities)

    async def local_search(
        self,
        query: str,
        max_hops: int = 2
    ) -> GraphRAGResult:
        """로컬 검색 (세밀한 질문).

        Args:
            query: 검색 쿼리
            max_hops: 최대 탐색 depth

        Returns:
            GraphRAGResult
        """
        if not self.local_search_engine:
            raise RuntimeError("Index not built. Call build_index() first.")

        return await self.local_search_engine.search(query, max_hops)

    async def hybrid_search(
        self,
        query: str,
        max_communities: int = 10,
        max_hops: int = 2
    ) -> GraphRAGResult:
        """하이브리드 검색 (Global + Local).

        Args:
            query: 검색 쿼리
            max_communities: Global 검색 최대 커뮤니티 수
            max_hops: Local 검색 최대 depth

        Returns:
            GraphRAGResult
        """
        logger.info(f"Hybrid search: {query}")

        # 병렬 실행
        global_result, local_result = await asyncio.gather(
            self.global_search_engine.search(query, max_communities),
            self.local_search_engine.search(query, max_hops),
            return_exceptions=True
        )

        # 에러 처리
        if isinstance(global_result, Exception):
            logger.error(f"Global search error: {global_result}")
            return local_result if not isinstance(local_result, Exception) else GraphRAGResult(
                answer="Search failed.",
                search_type=SearchType.HYBRID,
                confidence=0.0
            )

        if isinstance(local_result, Exception):
            logger.error(f"Local search error: {local_result}")
            return global_result

        # 결과 결합
        combined_answer = await self._combine_results(query, global_result, local_result)

        return GraphRAGResult(
            answer=combined_answer,
            communities_used=list(set(
                global_result.communities_used + local_result.communities_used
            )),
            evidence=local_result.evidence,
            confidence=0.85,
            search_type=SearchType.HYBRID,
            reasoning=f"Global: {len(global_result.communities_used)} communities, "
                     f"Local: {len(local_result.evidence)} evidence"
        )

    async def _combine_results(
        self,
        query: str,
        global_result: GraphRAGResult,
        local_result: GraphRAGResult
    ) -> str:
        """Global과 Local 결과 결합.

        Args:
            query: 쿼리
            global_result: Global 검색 결과
            local_result: Local 검색 결과

        Returns:
            결합된 답변
        """
        prompt = f"""Query: {query}

**Global Answer (Community-level):**
{global_result.answer}

**Local Answer (Entity-level):**
{local_result.answer}

**Task:**
Combine these two perspectives into a comprehensive final answer:
- Start with high-level insights from global answer
- Add specific evidence from local answer
- Ensure coherent narrative

Final Answer:"""

        response = await self.llm.generate(
            prompt=prompt,
            system="You are a medical research synthesis expert. Combine multiple perspectives.",
            use_cache=False
        )

        return response.text.strip()

    async def _save_index_to_neo4j(self, hierarchy: CommunityHierarchy) -> None:
        """커뮤니티 인덱스를 Neo4j에 저장.

        Args:
            hierarchy: 커뮤니티 계층 구조
        """
        logger.info("커뮤니티 인덱스 저장 중...")

        # Community 노드 생성
        for comm in hierarchy.communities.values():
            query = """
            MERGE (c:Community {id: $id})
            SET c.level = $level,
                c.members = $members,
                c.parent_id = $parent_id,
                c.summary = $summary,
                c.evidence_count = $evidence_count,
                c.avg_p_value = $avg_p_value
            """

            await self.neo4j.run_write_query(query, {
                "id": comm.id,
                "level": comm.level,
                "members": comm.members,
                "parent_id": comm.parent_id,
                "summary": comm.summary,
                "evidence_count": comm.evidence_count,
                "avg_p_value": comm.avg_p_value,
            })

        # Parent-Child 관계 생성
        for comm in hierarchy.communities.values():
            if comm.parent_id:
                query = """
                MATCH (child:Community {id: $child_id})
                MATCH (parent:Community {id: $parent_id})
                MERGE (child)-[:BELONGS_TO]->(parent)
                """

                await self.neo4j.run_write_query(query, {
                    "child_id": comm.id,
                    "parent_id": comm.parent_id,
                })

        logger.info(f"커뮤니티 인덱스 저장 완료: {len(hierarchy.communities)}개")

    async def _load_index_from_neo4j(self) -> Optional[CommunityHierarchy]:
        """Neo4j에서 커뮤니티 인덱스 로드.

        Returns:
            CommunityHierarchy 또는 None
        """
        query = """
        MATCH (c:Community)
        RETURN c.id as id, c.level as level, c.members as members,
               c.parent_id as parent_id, c.summary as summary,
               c.evidence_count as evidence_count, c.avg_p_value as avg_p_value
        """

        results = await self.neo4j.run_query(query)

        if not results:
            return None

        hierarchy = CommunityHierarchy()

        for record in results:
            community = Community(
                id=record["id"],
                level=record["level"],
                members=record.get("members", []),
                parent_id=record.get("parent_id"),
                summary=record.get("summary", ""),
                evidence_count=record.get("evidence_count", 0),
                avg_p_value=record.get("avg_p_value", 1.0),
            )

            hierarchy.add_community(community)

        return hierarchy

    def get_statistics(self) -> dict:
        """인덱스 통계 반환.

        Returns:
            통계 딕셔너리
        """
        if not self.hierarchy:
            return {"status": "not_built"}

        return {
            "status": "ready",
            "total_communities": len(self.hierarchy.communities),
            "levels": {
                level: len(comms)
                for level, comms in self.hierarchy.levels.items()
            },
            "max_level": self.hierarchy.max_level,
            "graph_nodes": self.hierarchy.graph.number_of_nodes() if self.hierarchy.graph else 0,
            "graph_edges": self.hierarchy.graph.number_of_edges() if self.hierarchy.graph else 0,
        }
