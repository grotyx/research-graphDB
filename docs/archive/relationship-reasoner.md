# Relationship Reasoner Specification

## Overview

Gemini LLM을 사용하여 논문 간 관계를 추론합니다 (상충/지지, 주제 연결, 멀티홉 추론).

### 목적
- 두 논문의 연구 결과가 상충하는지 지지하는지 분석
- 새 논문 추가 시 기존 논문들과의 관계 자동 분석
- 주제별 논문 클러스터링 (LLM 기반)
- 여러 논문을 연결하는 멀티홉 추론

### 입출력 요약
- **입력**: 논문 쌍 또는 질문
- **출력**: 관계 정보, 클러스터, 추론 체인

---

## Data Structures

### RelationshipResult

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RelationshipResult:
    """관계 분석 결과."""
    source_id: str
    target_id: str
    relation_type: str           # supports, contradicts, similar_topic, extends, neutral
    confidence: float            # 0.0 ~ 1.0
    evidence: str                # 관계 근거 설명
    key_similarities: List[str]  # 유사한 점
    key_differences: List[str]   # 다른 점

    # PICO 비교 결과
    pico_comparison: Optional[dict] = None  # {P: similar/different, I: ..., C: ..., O: ...}

    def to_paper_relation(self) -> PaperRelation:
        """PaperRelation으로 변환."""
        return PaperRelation(
            source_id=self.source_id,
            target_id=self.target_id,
            relation_type=self.relation_type,
            confidence=self.confidence,
            evidence=self.evidence,
            detected_by="llm_analysis"
        )
```

### TopicCluster

```python
@dataclass
class TopicCluster:
    """주제 클러스터."""
    cluster_id: str
    topic_name: str              # LLM이 생성한 주제명
    topic_description: str       # 주제 설명
    paper_ids: List[str]         # 포함된 논문 ID
    central_paper_id: str        # 중심 논문
    keywords: List[str]          # 클러스터 키워드
    pico_summary: Optional[PICOElements] = None  # 클러스터 공통 PICO
```

### MultiHopResult

```python
@dataclass
class ReasoningStep:
    """추론 단계."""
    step_number: int
    paper_id: str
    paper_title: str
    finding: str                 # 이 논문에서의 발견
    connection: str              # 다음 단계로의 연결 설명

@dataclass
class MultiHopResult:
    """멀티홉 추론 결과."""
    question: str
    answer: str
    confidence: float
    reasoning_chain: List[ReasoningStep]
    supporting_papers: List[str]
    contradicting_papers: List[str]
    limitations: str
```

---

## Interface

### RelationshipReasoner

```python
class RelationshipReasoner:
    """LLM 기반 논문 관계 추론기."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        paper_graph: PaperGraph,
        config: dict = None
    ):
        """초기화.

        Args:
            gemini_client: Gemini API 클라이언트
            paper_graph: 논문 그래프 DB
            config: 설정
                - pico_similarity_threshold: PICO 유사도 임계값 (기본: 0.5)
                - analyze_all_similar: 모든 유사 쌍 분석 (정확도 우선)
        """

    # ==================== 상충/지지 분석 ====================

    async def analyze_support_conflict(
        self,
        paper_a_id: str,
        paper_b_id: str
    ) -> RelationshipResult:
        """두 논문의 결과가 상충/지지하는지 분석.

        Args:
            paper_a_id: 첫 번째 논문 ID
            paper_b_id: 두 번째 논문 ID

        Returns:
            RelationshipResult
        """

    async def analyze_new_paper_relations(
        self,
        new_paper_id: str,
        analyze_all: bool = True  # 정확도 우선
    ) -> List[RelationshipResult]:
        """새 논문과 기존 논문들의 관계 분석.

        Args:
            new_paper_id: 새 논문 ID
            analyze_all: 모든 유사 쌍 분석 여부

        Returns:
            RelationshipResult 목록
        """

    # ==================== 주제 클러스터링 ====================

    async def cluster_by_topic(
        self,
        method: str = "llm"  # "llm", "pico", "embedding"
    ) -> List[TopicCluster]:
        """논문 주제 클러스터링.

        Args:
            method: 클러스터링 방법
                - "llm": LLM이 주제 분류
                - "pico": PICO 유사도 기반
                - "embedding": 임베딩 유사도 기반

        Returns:
            TopicCluster 목록
        """

    async def assign_topic(
        self,
        paper_id: str,
        existing_clusters: List[TopicCluster] = None
    ) -> str:
        """논문을 주제 클러스터에 할당.

        Returns:
            할당된 cluster_id (새 클러스터면 새로 생성)
        """

    # ==================== 멀티홉 추론 ====================

    async def reason_multi_hop(
        self,
        question: str,
        start_paper_id: str = None,
        max_hops: int = 3
    ) -> MultiHopResult:
        """여러 논문을 연결하는 추론.

        Args:
            question: 질문
            start_paper_id: 시작 논문 (선택)
            max_hops: 최대 홉 수

        Returns:
            MultiHopResult
        """

    # ==================== 유틸리티 ====================

    async def find_similar_papers_for_analysis(
        self,
        paper_id: str,
        threshold: float = 0.5
    ) -> List[str]:
        """분석 대상 유사 논문 찾기.

        PICO, 키워드, 임베딩 유사도 종합.
        """

    async def compare_findings(
        self,
        paper_ids: List[str]
    ) -> dict:
        """여러 논문의 발견 비교.

        Returns:
            {
                "consensus": [공통 발견],
                "conflicts": [(paper_a, paper_b, 상충 내용)],
                "unique": {paper_id: [고유 발견]}
            }
        """
```

---

## LLM Prompt Templates

### 상충/지지 분석 - System Prompt

```python
SUPPORT_CONFLICT_SYSTEM = """You are a medical research evidence analyst.

Your task is to compare two medical research papers and determine if their findings support or contradict each other.

Analysis criteria:
1. PICO alignment: Do they study similar populations, interventions, and outcomes?
2. Findings comparison: Are the conclusions similar or different?
3. Effect direction: Do effects go in the same direction?
4. Statistical significance: Are results both significant? In same direction?
5. Methodology differences: Could methods explain different results?

Relationship types:
- "supports": Similar findings that reinforce each other
- "contradicts": Conflicting findings that disagree
- "extends": One study extends/builds on the other
- "neutral": Related but neither supporting nor contradicting

Be rigorous and evidence-based in your assessment.
"""
```

### 상충/지지 분석 - User Prompt

```python
SUPPORT_CONFLICT_USER = """Compare these two medical papers and determine their relationship.

Paper A ({paper_a_id}):
- Title: {title_a}
- Year: {year_a}
- Summary: {summary_a}
- PICO:
  - Population: {pico_a_p}
  - Intervention: {pico_a_i}
  - Comparison: {pico_a_c}
  - Outcome: {pico_a_o}
- Main Findings: {findings_a}
- Evidence Level: {evidence_a}

Paper B ({paper_b_id}):
- Title: {title_b}
- Year: {year_b}
- Summary: {summary_b}
- PICO:
  - Population: {pico_b_p}
  - Intervention: {pico_b_i}
  - Comparison: {pico_b_c}
  - Outcome: {pico_b_o}
- Main Findings: {findings_b}
- Evidence Level: {evidence_b}

Analyze:
1. relation_type: "supports", "contradicts", "extends", or "neutral"
2. confidence: 0.0-1.0
3. evidence: Detailed explanation of why you determined this relationship
4. key_similarities: List of similar aspects
5. key_differences: List of different aspects
6. pico_comparison: For each PICO element, is it "similar", "different", or "not_comparable"
"""
```

### 주제 클러스터링 - System Prompt

```python
TOPIC_CLUSTER_SYSTEM = """You are a medical research topic classification expert.

Your task is to organize medical papers into coherent topic clusters based on their research focus.

Clustering principles:
1. Papers in same cluster should address similar clinical questions
2. Group by disease/condition, intervention type, or patient population
3. Consider PICO alignment
4. Create meaningful, specific topic names
5. A paper can fit in only ONE primary cluster
"""
```

### 주제 클러스터링 - User Prompt

```python
TOPIC_CLUSTER_USER = """Organize these medical papers into topic clusters.

Papers:
{papers_list}

For each cluster, provide:
1. topic_name: Concise, descriptive name (e.g., "Lumbar Fusion Outcomes")
2. topic_description: 1-2 sentence description
3. paper_ids: List of papers in this cluster
4. central_paper_id: Most representative paper
5. keywords: 5-10 keywords for this topic
6. common_pico: Shared PICO elements if any

Aim for 3-10 clusters depending on paper diversity.
"""
```

### 멀티홉 추론 - System Prompt

```python
MULTIHOP_SYSTEM = """You are a medical research synthesis expert.

Your task is to answer questions by connecting evidence from multiple research papers in a logical chain.

Reasoning approach:
1. Start with relevant papers
2. Build a logical chain: Paper A shows X, Paper B extends to Y, Paper C confirms Z
3. Identify supporting and contradicting evidence
4. Synthesize a comprehensive answer
5. Acknowledge limitations and uncertainties

Be rigorous: cite specific papers for each claim.
"""
```

### 멀티홉 추론 - User Prompt

```python
MULTIHOP_USER = """Answer this question by synthesizing evidence from multiple papers.

Question: {question}

Available papers:
{papers_info}

{start_context}

Provide:
1. answer: Direct answer to the question
2. confidence: 0.0-1.0
3. reasoning_chain: Step-by-step reasoning with paper citations
4. supporting_papers: Papers that support the answer
5. contradicting_papers: Papers with conflicting evidence
6. limitations: What the evidence doesn't cover
"""
```

### Output JSON Schemas

```python
SUPPORT_CONFLICT_SCHEMA = {
    "type": "object",
    "properties": {
        "relation_type": {
            "type": "string",
            "enum": ["supports", "contradicts", "extends", "neutral"]
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "string"},
        "key_similarities": {
            "type": "array",
            "items": {"type": "string"}
        },
        "key_differences": {
            "type": "array",
            "items": {"type": "string"}
        },
        "pico_comparison": {
            "type": "object",
            "properties": {
                "P": {"type": "string", "enum": ["similar", "different", "not_comparable"]},
                "I": {"type": "string", "enum": ["similar", "different", "not_comparable"]},
                "C": {"type": "string", "enum": ["similar", "different", "not_comparable"]},
                "O": {"type": "string", "enum": ["similar", "different", "not_comparable"]}
            }
        }
    },
    "required": ["relation_type", "confidence", "evidence"]
}

TOPIC_CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_name": {"type": "string"},
                    "topic_description": {"type": "string"},
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "central_paper_id": {"type": "string"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "common_pico": {
                        "type": ["object", "null"]
                    }
                },
                "required": ["topic_name", "paper_ids"]
            }
        }
    },
    "required": ["clusters"]
}

MULTIHOP_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning_chain": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_number": {"type": "integer"},
                    "paper_id": {"type": "string"},
                    "finding": {"type": "string"},
                    "connection": {"type": "string"}
                }
            }
        },
        "supporting_papers": {
            "type": "array",
            "items": {"type": "string"}
        },
        "contradicting_papers": {
            "type": "array",
            "items": {"type": "string"}
        },
        "limitations": {"type": "string"}
    },
    "required": ["answer", "confidence", "reasoning_chain"]
}
```

---

## Implementation Notes

### 유사 논문 필터링 (정확도 우선)

```python
async def find_similar_papers_for_analysis(
    self,
    paper_id: str,
    threshold: float = 0.5  # 정확도 우선: 낮은 임계값
) -> List[str]:
    """분석 대상 유사 논문 찾기."""
    paper = await self.paper_graph.get_paper(paper_id)
    if not paper:
        return []

    all_papers = await self.paper_graph.list_papers()
    similar = []

    for other in all_papers:
        if other.paper_id == paper_id:
            continue

        # 종합 유사도 계산
        score = self._calculate_combined_similarity(paper, other)

        if score >= threshold:
            similar.append((other.paper_id, score))

    # 유사도 순 정렬
    similar.sort(key=lambda x: x[1], reverse=True)

    return [p[0] for p in similar]

def _calculate_combined_similarity(
    self,
    paper_a: PaperNode,
    paper_b: PaperNode
) -> float:
    """종합 유사도 계산."""
    scores = []

    # 1. PICO 유사도
    if paper_a.pico_summary and paper_b.pico_summary:
        pico_sim = self._calculate_pico_similarity(
            paper_a.pico_summary, paper_b.pico_summary
        )
        scores.append(("pico", pico_sim, 0.4))  # 가중치 40%

    # 2. 키워드 유사도
    if paper_a.keywords and paper_b.keywords:
        kw_a = set(k.lower() for k in paper_a.keywords)
        kw_b = set(k.lower() for k in paper_b.keywords)
        if kw_a or kw_b:
            kw_sim = len(kw_a & kw_b) / len(kw_a | kw_b)
            scores.append(("keyword", kw_sim, 0.3))  # 가중치 30%

    # 3. 임베딩 유사도
    if paper_a.embedding and paper_b.embedding:
        emb_sim = self._cosine_similarity(paper_a.embedding, paper_b.embedding)
        scores.append(("embedding", emb_sim, 0.3))  # 가중치 30%

    if not scores:
        return 0.0

    # 가중 평균
    total_weight = sum(s[2] for s in scores)
    weighted_sum = sum(s[1] * s[2] for s in scores)

    return weighted_sum / total_weight if total_weight > 0 else 0.0
```

### 새 논문 관계 분석

```python
async def analyze_new_paper_relations(
    self,
    new_paper_id: str,
    analyze_all: bool = True
) -> List[RelationshipResult]:
    """새 논문과 기존 논문 관계 분석."""
    # 유사 논문 찾기
    similar_ids = await self.find_similar_papers_for_analysis(
        new_paper_id,
        threshold=0.5 if analyze_all else 0.7
    )

    if not similar_ids:
        return []

    # 병렬 분석
    tasks = [
        self.analyze_support_conflict(new_paper_id, other_id)
        for other_id in similar_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 에러 필터링
    valid_results = [
        r for r in results
        if isinstance(r, RelationshipResult)
    ]

    # 의미있는 관계만 (neutral 제외 또는 높은 신뢰도)
    significant_results = [
        r for r in valid_results
        if r.relation_type != "neutral" or r.confidence > 0.8
    ]

    return significant_results
```

### LLM 기반 주제 클러스터링

```python
async def cluster_by_topic(
    self,
    method: str = "llm"
) -> List[TopicCluster]:
    """LLM 기반 주제 클러스터링."""
    papers = await self.paper_graph.list_papers()

    if len(papers) < 2:
        return []

    if method == "llm":
        return await self._cluster_with_llm(papers)
    elif method == "pico":
        return await self._cluster_by_pico(papers)
    else:
        return await self._cluster_by_embedding(papers)

async def _cluster_with_llm(
    self,
    papers: List[PaperNode]
) -> List[TopicCluster]:
    """LLM으로 클러스터링."""
    # 논문 정보 포맷
    papers_list = "\n".join([
        f"- {p.paper_id}: {p.title} ({p.year})\n"
        f"  Summary: {p.abstract_summary}\n"
        f"  Keywords: {', '.join(p.keywords[:5])}"
        for p in papers
    ])

    result = await self.gemini.generate_json(
        prompt=TOPIC_CLUSTER_USER.format(papers_list=papers_list),
        schema=TOPIC_CLUSTER_SCHEMA,
        system=TOPIC_CLUSTER_SYSTEM
    )

    clusters = []
    for i, c in enumerate(result["clusters"]):
        cluster = TopicCluster(
            cluster_id=f"cluster_{i:03d}",
            topic_name=c["topic_name"],
            topic_description=c.get("topic_description", ""),
            paper_ids=c["paper_ids"],
            central_paper_id=c.get("central_paper_id", c["paper_ids"][0]),
            keywords=c.get("keywords", [])
        )
        clusters.append(cluster)

    return clusters
```

### 멀티홉 추론

```python
async def reason_multi_hop(
    self,
    question: str,
    start_paper_id: str = None,
    max_hops: int = 3
) -> MultiHopResult:
    """멀티홉 추론."""
    # 관련 논문 수집
    if start_paper_id:
        # 시작 논문에서 관련 논문 탐색
        related_ids = await self._expand_from_paper(start_paper_id, max_hops)
        papers = [await self.paper_graph.get_paper(pid) for pid in related_ids]
        papers = [p for p in papers if p]
        start_context = f"Start from paper: {start_paper_id}"
    else:
        # 질문 키워드로 논문 검색
        search_results = await self.paper_graph.search_papers(question, top_k=10)
        papers = [p for p, _ in search_results]
        start_context = ""

    if not papers:
        return MultiHopResult(
            question=question,
            answer="No relevant papers found to answer this question.",
            confidence=0.0,
            reasoning_chain=[],
            supporting_papers=[],
            contradicting_papers=[],
            limitations="No papers available for analysis."
        )

    # 논문 정보 포맷
    papers_info = "\n\n".join([
        f"Paper {p.paper_id}:\n"
        f"- Title: {p.title}\n"
        f"- Year: {p.year}\n"
        f"- Summary: {p.abstract_summary}\n"
        f"- Main Findings: {'; '.join(p.main_findings[:3])}"
        for p in papers[:10]  # 최대 10개
    ])

    result = await self.gemini.generate_json(
        prompt=MULTIHOP_USER.format(
            question=question,
            papers_info=papers_info,
            start_context=start_context
        ),
        schema=MULTIHOP_SCHEMA,
        system=MULTIHOP_SYSTEM
    )

    # 추론 체인 변환
    chain = [
        ReasoningStep(
            step_number=step["step_number"],
            paper_id=step["paper_id"],
            paper_title=self._get_paper_title(step["paper_id"], papers),
            finding=step["finding"],
            connection=step.get("connection", "")
        )
        for step in result.get("reasoning_chain", [])
    ]

    return MultiHopResult(
        question=question,
        answer=result["answer"],
        confidence=result["confidence"],
        reasoning_chain=chain,
        supporting_papers=result.get("supporting_papers", []),
        contradicting_papers=result.get("contradicting_papers", []),
        limitations=result.get("limitations", "")
    )
```

---

## Test Cases

### 단위 테스트

```python
import pytest

class TestRelationshipReasoner:
    @pytest.fixture
    def reasoner(self, mock_gemini_client, mock_paper_graph):
        return RelationshipReasoner(
            gemini_client=mock_gemini_client,
            paper_graph=mock_paper_graph
        )

    @pytest.mark.asyncio
    async def test_analyze_support(self, reasoner, mock_paper_graph):
        """지지 관계 분석."""
        # 유사한 결과를 보이는 두 논문 설정
        paper_a = PaperNode(
            "pa", "Early Surgery Benefits", ["Kim"], 2020,
            "Early surgery shows 85% success rate",
            main_findings=["Early intervention improves outcomes"]
        )
        paper_b = PaperNode(
            "pb", "Timing of Surgery", ["Park"], 2021,
            "Our study confirms early surgery benefits",
            main_findings=["Early surgery has 80% success"]
        )

        mock_paper_graph.get_paper.side_effect = lambda x: paper_a if x == "pa" else paper_b

        result = await reasoner.analyze_support_conflict("pa", "pb")

        assert result.relation_type == "supports"
        assert result.confidence > 0.7

    @pytest.mark.asyncio
    async def test_analyze_contradiction(self, reasoner, mock_paper_graph):
        """상충 관계 분석."""
        paper_a = PaperNode(
            "pa", "Surgery is Effective", ["Kim"], 2020,
            "Surgery shows significant benefit",
            main_findings=["Surgery is recommended"]
        )
        paper_b = PaperNode(
            "pb", "Conservative Treatment Preferred", ["Lee"], 2021,
            "Conservative treatment shows similar outcomes",
            main_findings=["Surgery shows no benefit over conservative"]
        )

        mock_paper_graph.get_paper.side_effect = lambda x: paper_a if x == "pa" else paper_b

        result = await reasoner.analyze_support_conflict("pa", "pb")

        assert result.relation_type == "contradicts"

    @pytest.mark.asyncio
    async def test_cluster_by_topic(self, reasoner, mock_paper_graph):
        """주제 클러스터링."""
        papers = [
            PaperNode("p1", "Lumbar Fusion A", ["A"], 2020, "Lumbar fusion study",
                     keywords=["lumbar", "fusion"]),
            PaperNode("p2", "Lumbar Fusion B", ["B"], 2021, "Another fusion study",
                     keywords=["lumbar", "spine", "fusion"]),
            PaperNode("p3", "Cervical Disc", ["C"], 2020, "Cervical disc study",
                     keywords=["cervical", "disc"]),
        ]
        mock_paper_graph.list_papers.return_value = papers

        clusters = await reasoner.cluster_by_topic(method="llm")

        # 최소 1개 클러스터
        assert len(clusters) >= 1
        # 유사 논문은 같은 클러스터
        lumbar_cluster = next(
            (c for c in clusters if "lumbar" in c.topic_name.lower()),
            None
        )
        if lumbar_cluster:
            assert "p1" in lumbar_cluster.paper_ids
            assert "p2" in lumbar_cluster.paper_ids

    @pytest.mark.asyncio
    async def test_multi_hop_reasoning(self, reasoner, mock_paper_graph):
        """멀티홉 추론."""
        papers = [
            PaperNode("p1", "Initial Study", ["A"], 2018,
                     "First observation of technique",
                     main_findings=["Technique is feasible"]),
            PaperNode("p2", "Follow-up Study", ["B"], 2020,
                     "Long-term follow-up",
                     main_findings=["Long-term outcomes are good"]),
        ]
        mock_paper_graph.search_papers.return_value = [(p, 0.9) for p in papers]

        result = await reasoner.reason_multi_hop(
            "What are the long-term outcomes of this technique?"
        )

        assert result.answer
        assert len(result.reasoning_chain) > 0
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_analyze_new_paper_relations(self, reasoner, mock_paper_graph):
        """새 논문 관계 분석."""
        new_paper = PaperNode("new", "New Study", ["Kim"], 2024, "New findings")
        existing = [
            PaperNode("e1", "Existing 1", ["A"], 2020, "Related study"),
            PaperNode("e2", "Existing 2", ["B"], 2021, "Another study"),
        ]

        mock_paper_graph.get_paper.return_value = new_paper
        mock_paper_graph.list_papers.return_value = [new_paper] + existing

        results = await reasoner.analyze_new_paper_relations("new")

        # 분석 결과 반환
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_compare_findings(self, reasoner, mock_paper_graph):
        """발견 비교."""
        papers = [
            PaperNode("p1", "Study 1", ["A"], 2020, "S1",
                     main_findings=["Finding A", "Finding B"]),
            PaperNode("p2", "Study 2", ["B"], 2021, "S2",
                     main_findings=["Finding A", "Finding C"]),
        ]
        mock_paper_graph.get_paper.side_effect = lambda x: papers[0] if x == "p1" else papers[1]

        result = await reasoner.compare_findings(["p1", "p2"])

        assert "consensus" in result
        assert "conflicts" in result
        assert "unique" in result
```

---

## Dependencies

- `src/llm/gemini_client.py` - GeminiClient
- `src/knowledge/paper_graph.py` - PaperGraph, PaperNode, PaperRelation
- `src/builder/llm_metadata_extractor.py` - PICOElements

---

## Configuration

```yaml
# config.yaml
relationship_reasoner:
  # 유사도 임계값
  pico_similarity_threshold: 0.5   # 정확도 우선: 낮은 임계값
  analyze_all_similar: true         # 모든 유사 쌍 분석

  # 클러스터링
  clustering:
    default_method: "llm"
    min_cluster_size: 2
    max_clusters: 10

  # 멀티홉 추론
  multi_hop:
    max_hops: 3
    max_papers_per_query: 10

  # 가중치
  similarity_weights:
    pico: 0.4
    keyword: 0.3
    embedding: 0.3
```
