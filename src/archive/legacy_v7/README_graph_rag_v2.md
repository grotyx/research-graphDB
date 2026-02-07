# GraphRAG 2.0 - Microsoft-style Community-based Knowledge Graph RAG

## Overview

GraphRAG 2.0는 Microsoft의 GraphRAG 논문을 기반으로 구현한 커뮤니티 탐지 및 계층적 요약 기반 검색 시스템입니다.

**핵심 아이디어:**
- 기존 Vector RAG의 한계: 문서 단위 검색은 광범위한 주제나 전체적인 패턴을 파악하기 어려움
- GraphRAG 접근법: 지식 그래프를 커뮤니티로 분할하고 각 커뮤니티를 LLM으로 요약하여 계층 구조 생성
- Global Search: 커뮤니티 요약 기반으로 광범위한 질문에 답변 (Map-Reduce 스타일)
- Local Search: 엔티티 중심 세밀한 검색

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GraphRAG v2.0 Pipeline                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. COMMUNITY DETECTION (Louvain Algorithm)                     │
│     ┌──────────────────────────────────────┐                   │
│     │  Intervention-Outcome Graph          │                   │
│     │  ├─ Nodes: Interventions, Outcomes   │                   │
│     │  └─ Edges: AFFECTS (weighted by      │                   │
│     │            p-value significance)      │                   │
│     └──────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│     ┌──────────────────────────────────────┐                   │
│     │  Hierarchical Communities            │                   │
│     │  Level 0: Leaf communities (3-10     │                   │
│     │           members each)               │                   │
│     │  Level 1: Mid-level aggregations     │                   │
│     │           (groups of 4 L0 comms)     │                   │
│     │  Level 2: Top-level summary (all)    │                   │
│     └──────────────┬───────────────────────┘                   │
│                    │                                            │
│  2. SUMMARIZATION (LLM-based)                                   │
│                    │                                            │
│                    ▼                                            │
│     ┌──────────────────────────────────────┐                   │
│     │  Community Summaries                 │                   │
│     │  ├─ L0: Evidence-based summaries     │                   │
│     │  │      (from actual data)           │                   │
│     │  ├─ L1: Aggregated summaries         │                   │
│     │  │      (from L0 summaries)          │                   │
│     │  └─ L2: Top-level theme summary      │                   │
│     │         (from L1 summaries)          │                   │
│     └──────────────┬───────────────────────┘                   │
│                    │                                            │
│  3. SEARCH ENGINES                                              │
│     ┌──────────────┴───────────────────────┐                   │
│     │                                      │                   │
│     ▼                                      ▼                   │
│  ┌─────────────────┐           ┌──────────────────┐           │
│  │ Global Search   │           │  Local Search    │           │
│  │ (Map-Reduce)    │           │  (Entity-based)  │           │
│  │                 │           │                  │           │
│  │ 1. Select       │           │ 1. Extract       │           │
│  │    relevant     │           │    entities      │           │
│  │    communities  │           │ 2. Explore       │           │
│  │ 2. Map: Partial │           │    neighborhood  │           │
│  │    answers      │           │ 3. Find related  │           │
│  │ 3. Reduce:      │           │    communities   │           │
│  │    Aggregate    │           │ 4. Generate      │           │
│  │                 │           │    answer        │           │
│  └─────────────────┘           └──────────────────┘           │
│           │                             │                      │
│           └──────────┬──────────────────┘                      │
│                      │                                         │
│                      ▼                                         │
│           ┌──────────────────────┐                            │
│           │  Hybrid Search       │                            │
│           │  (Global + Local)    │                            │
│           └──────────────────────┘                            │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. CommunityDetector

**Purpose:** Intervention-Outcome 그래프에서 커뮤니티 탐지 및 계층 구조 생성

**Algorithm:** Louvain algorithm (python-louvain)
- 모듈성(modularity) 최대화 기반 커뮤니티 탐지
- 가중치: `weight = 1.0 - p_value` (통계적으로 강한 관계일수록 높은 가중치)
- 유의성 보너스: `is_significant = True` 엣지는 1.5배 가중치

**Output:**
- `CommunityHierarchy`: 3-레벨 계층 구조
  - Level 0: Leaf communities (실제 intervention-outcome 클러스터)
  - Level 1: Mid-level aggregations (4개씩 묶음)
  - Level 2: Top-level summary (전체 요약)

**Key Methods:**
```python
async def detect_communities(
    resolution: float = 1.0,
    min_community_size: int = 3
) -> CommunityHierarchy
```

**Parameters:**
- `resolution`: Louvain 해상도 (높을수록 작은 커뮤니티)
- `min_community_size`: 최소 커뮤니티 크기 (작은 커뮤니티 필터링)

### 2. CommunitySummarizer

**Purpose:** 각 커뮤니티를 LLM으로 요약

**Approach:**
- **Level 0 (Leaf):** 실제 데이터에서 요약 생성
  - Neo4j에서 커뮤니티 멤버의 AFFECTS 관계 조회
  - 통계적 유의성과 방향성 포함하여 요약

- **Level 1+ (Aggregation):** 하위 커뮤니티 요약들을 종합
  - Bottom-up 방식으로 계층적 요약 생성
  - 공통 테마와 패턴 추출

**Key Methods:**
```python
async def summarize_hierarchy(
    hierarchy: CommunityHierarchy
) -> CommunityHierarchy
```

**Example Summary (Level 0):**
```
"TLIF and PLIF show statistically significant improvements in VAS
and ODI scores (p<0.01), with fusion rates >85%. Both approaches
demonstrate comparable clinical outcomes for lumbar stenosis."
```

**Example Summary (Level 1):**
```
"Fusion surgery techniques (TLIF, PLIF, ALIF) consistently improve
clinical outcomes (pain, disability) and achieve high fusion rates.
Endoscopic approaches (UBE, FELD) show similar pain reduction with
potentially lower complication rates."
```

### 3. GlobalSearchEngine

**Purpose:** 광범위한 질문에 대한 전역 검색 (커뮤니티 요약 기반)

**Algorithm:** Map-Reduce 스타일
1. **Map Phase:**
   - 쿼리와 관련된 커뮤니티 선택 (LLM 기반 relevance 평가)
   - 각 커뮤니티 요약에 대해 부분 답변 생성

2. **Reduce Phase:**
   - 부분 답변들을 종합하여 최종 답변 생성
   - 중복 제거 및 일관성 있는 narrative 구성

**Use Cases:**
- "What are the most effective fusion surgeries for lumbar stenosis?"
- "How do minimally invasive techniques compare to open surgery?"
- "What are common complications in spine surgery?"

**Key Methods:**
```python
async def search(
    query: str,
    max_communities: int = 10
) -> GraphRAGResult
```

**Example Flow:**
```
Query: "What are effective treatments for lumbar stenosis?"

Selected Communities:
- community_L1_0: Fusion surgeries (TLIF, PLIF, ALIF)
- community_L1_1: Decompression surgeries (UBE, Laminectomy)
- community_L0_3: Motion preservation (ADR)

Partial Answers:
- From community_L1_0: "Fusion surgeries show 80-90% improvement..."
- From community_L1_1: "Decompression techniques achieve 70-85%..."
- From community_L0_3: "ADR preserves motion but limited evidence..."

Final Answer: "Multiple treatment approaches are effective for lumbar
stenosis. Fusion surgeries (TLIF, PLIF) demonstrate the highest success
rates (80-90%) with strong statistical evidence (p<0.001). Decompression-
only techniques like UBE offer good outcomes (70-85%) with faster
recovery. Motion preservation with ADR is an option for select patients
but has limited long-term evidence."
```

### 4. LocalSearchEngine

**Purpose:** 특정 엔티티에 대한 세밀한 검색

**Algorithm:** Entity-centric neighborhood exploration
1. 쿼리에서 intervention/outcome 엔티티 추출
2. 엔티티 주변 서브그래프 탐색 (max_hops depth)
3. 엔티티가 속한 커뮤니티 찾기
4. 로컬 근거 + 커뮤니티 컨텍스트로 답변 생성

**Use Cases:**
- "What is the effect of TLIF on VAS scores?"
- "Does UBE reduce complication rates compared to open surgery?"
- "What are the fusion rates for OLIF?"

**Key Methods:**
```python
async def search(
    query: str,
    max_hops: int = 2
) -> GraphRAGResult
```

**Example Flow:**
```
Query: "Effect of TLIF on VAS?"

Entities: ["TLIF", "VAS"]

Local Evidence (2-hop neighborhood):
- TLIF → VAS: improved (p=0.001, value=-2.3)
- TLIF → ODI: improved (p=0.002, value=-15.2)
- TLIF → Fusion Rate: 89.5% (p=0.005)

Related Communities:
- community_L0_0: "TLIF shows significant VAS improvement..."
- community_L1_0: "Fusion surgeries effective for pain..."

Answer: "TLIF significantly improves VAS scores with a mean reduction
of 2.3 points (p=0.001). This is part of a broader pattern where TLIF
consistently demonstrates positive clinical outcomes including ODI
improvement (-15.2 points) and high fusion rates (89.5%)."
```

### 5. GraphRAGPipeline

**Purpose:** 전체 파이프라인 통합 관리

**Key Methods:**

#### build_index()
```python
async def build_index(
    resolution: float = 1.0,
    min_community_size: int = 3,
    force_rebuild: bool = False
) -> CommunityHierarchy
```

**Process:**
1. Neo4j에서 기존 인덱스 확인
2. 없으면 커뮤니티 탐지 실행
3. 커뮤니티 요약 생성 (LLM)
4. Neo4j에 커뮤니티 노드 저장
5. 검색 엔진 초기화

#### global_search()
```python
async def global_search(
    query: str,
    max_communities: int = 10
) -> GraphRAGResult
```

#### local_search()
```python
async def local_search(
    query: str,
    max_hops: int = 2
) -> GraphRAGResult
```

#### hybrid_search()
```python
async def hybrid_search(
    query: str,
    max_communities: int = 10,
    max_hops: int = 2
) -> GraphRAGResult
```

**Process:**
1. Global과 Local 검색 병렬 실행
2. 두 결과를 LLM으로 결합
3. 통합된 답변 반환

## Data Structures

### Community
```python
@dataclass
class Community:
    id: str                    # "community_L0_0"
    level: int                 # 0, 1, 2
    members: list[str]         # ["TLIF", "VAS", "ODI"]
    parent_id: Optional[str]   # "community_L1_0"
    summary: str               # LLM-generated summary
    evidence_count: int        # Number of AFFECTS edges
    avg_p_value: float         # Average p-value
```

### CommunityHierarchy
```python
@dataclass
class CommunityHierarchy:
    levels: dict[int, list[Community]]  # {0: [comm0, comm1], 1: [comm_top]}
    communities: dict[str, Community]   # {"comm_id": Community}
    graph: Optional[nx.Graph]           # NetworkX graph
    max_level: int                      # Maximum level
```

### GraphRAGResult
```python
@dataclass
class GraphRAGResult:
    answer: str                    # Final answer
    communities_used: list[str]    # ["community_L0_0", ...]
    evidence: list[dict]           # Local evidence (for local search)
    confidence: float              # 0-1
    search_type: SearchType        # GLOBAL, LOCAL, HYBRID
    reasoning: str                 # Explanation of search process
```

## Usage Examples

### 1. Basic Setup

```python
import asyncio
from src.graph.neo4j_client import Neo4jClient
from src.solver.graph_rag_v2 import GraphRAGPipeline

async def main():
    # Initialize Neo4j client
    async with Neo4jClient() as neo4j:
        # Create pipeline
        pipeline = GraphRAGPipeline(neo4j)

        # Build index (community detection + summarization)
        hierarchy = await pipeline.build_index(
            resolution=1.0,
            min_community_size=3,
            force_rebuild=False  # Use cached if available
        )

        print(f"Built index with {len(hierarchy.communities)} communities")

asyncio.run(main())
```

### 2. Global Search (Exploratory Questions)

```python
async def global_search_example():
    async with Neo4jClient() as neo4j:
        pipeline = GraphRAGPipeline(neo4j)

        # Must build index first
        await pipeline.build_index()

        # Global search
        result = await pipeline.global_search(
            query="What are the most effective fusion surgeries for degenerative spine disease?",
            max_communities=10
        )

        print(f"Answer: {result.answer}")
        print(f"Communities used: {result.communities_used}")
        print(f"Confidence: {result.confidence}")
```

### 3. Local Search (Specific Questions)

```python
async def local_search_example():
    async with Neo4jClient() as neo4j:
        pipeline = GraphRAGPipeline(neo4j)
        await pipeline.build_index()

        # Local search
        result = await pipeline.local_search(
            query="What is the effect of TLIF on VAS scores in lumbar stenosis patients?",
            max_hops=2
        )

        print(f"Answer: {result.answer}")
        print(f"Evidence count: {len(result.evidence)}")
```

### 4. Hybrid Search (Best of Both Worlds)

```python
async def hybrid_search_example():
    async with Neo4jClient() as neo4j:
        pipeline = GraphRAGPipeline(neo4j)
        await pipeline.build_index()

        # Hybrid search
        result = await pipeline.hybrid_search(
            query="How does UBE compare to traditional open decompression?",
            max_communities=8,
            max_hops=2
        )

        print(f"Answer: {result.answer}")
        print(f"Search type: {result.search_type}")
        print(f"Reasoning: {result.reasoning}")
```

### 5. Index Management

```python
async def index_management():
    async with Neo4jClient() as neo4j:
        pipeline = GraphRAGPipeline(neo4j)

        # Get statistics
        stats = pipeline.get_statistics()
        print(f"Status: {stats['status']}")

        if stats['status'] == 'not_built':
            # Build new index
            await pipeline.build_index(force_rebuild=True)
        else:
            print(f"Total communities: {stats['total_communities']}")
            print(f"Levels: {stats['levels']}")
```

## Performance Optimization

### 1. Index Caching

**커뮤니티 인덱스는 Neo4j에 저장되어 재사용됩니다:**
- Community 노드로 저장 (id, level, members, summary, etc.)
- BELONGS_TO 관계로 계층 구조 표현
- `force_rebuild=False`로 기존 인덱스 재사용

**재구축이 필요한 경우:**
- 새로운 논문 추가로 그래프 구조 변경
- 요약 품질 개선 필요
- 커뮤니티 탐지 파라미터 변경

### 2. LLM Caching

**GeminiClient의 built-in caching 사용:**
- 커뮤니티 요약은 자동 캐싱 (동일 커뮤니티 재요청 시 캐시 사용)
- 부분 답변 캐싱으로 반복 쿼리 최적화

### 3. Parallel Processing

**병렬 처리 활용:**
```python
# 커뮤니티 요약 병렬 생성
tasks = [
    self._summarize_community(comm, hierarchy)
    for comm in communities
]
await asyncio.gather(*tasks)

# Global search Map phase 병렬 실행
partial_answers = await asyncio.gather(*[
    self._answer_from_community(query, comm)
    for comm in communities
])

# Hybrid search 병렬 실행
global_result, local_result = await asyncio.gather(
    self.global_search(query),
    self.local_search(query)
)
```

## Comparison: GraphRAG vs Traditional RAG

| Aspect | Traditional Vector RAG | GraphRAG 2.0 |
|--------|----------------------|--------------|
| **Query Type** | Specific questions | Both specific & exploratory |
| **Context Size** | Limited by token window | Hierarchical summaries (unbounded) |
| **Pattern Recognition** | Per-document | Community-level patterns |
| **Statistical Evidence** | May miss | Preserved in graph structure |
| **Conflicting Results** | Hard to detect | Natural via graph relationships |
| **Explanation** | Document snippets | Multi-level reasoning |
| **Scalability** | Linear with docs | Logarithmic with communities |

**Use Cases Comparison:**

| Question Type | Best Approach |
|--------------|---------------|
| "Effect of TLIF on VAS?" | **Local Search** (entity-specific) |
| "Best surgeries for stenosis?" | **Global Search** (exploratory) |
| "TLIF vs UBE comparison?" | **Hybrid Search** (specific + context) |
| "Common complications?" | **Global Search** (broad pattern) |
| "Fusion rate for OLIF?" | **Local Search** (specific metric) |

## Testing

**Run tests:**
```bash
# All GraphRAG v2 tests
pytest tests/solver/test_graph_rag_v2.py -v

# Specific test
pytest tests/solver/test_graph_rag_v2.py::test_community_detector_detect_communities -v

# With coverage
pytest tests/solver/test_graph_rag_v2.py --cov=src/solver/graph_rag_v2 --cov-report=html
```

**Test Coverage:**
- ✅ Community data structures (to_dict, from_dict)
- ✅ CommunityDetector (graph fetching, NetworkX building, Louvain)
- ✅ CommunitySummarizer (from_data, aggregate_summaries)
- ✅ GlobalSearchEngine (community selection, map-reduce)
- ✅ LocalSearchEngine (entity extraction, neighborhood exploration)
- ✅ GraphRAGPipeline (build_index, all search types)
- ✅ End-to-end workflow

**12+ Test Cases:**
1. Community creation and serialization
2. CommunityHierarchy management
3. Graph data fetching from Neo4j
4. NetworkX graph building
5. Community detection (Louvain)
6. Level 0 summarization (from data)
7. Level 1+ aggregation (from child summaries)
8. Global search (map-reduce)
9. Local search (entity-centric)
10. Hybrid search (combined)
11. Index persistence (save/load)
12. End-to-end pipeline

## Future Enhancements

### 1. Multi-Modal Communities
- Image/table 데이터를 커뮤니티 요약에 포함
- Figure-based evidence 지원

### 2. Dynamic Index Updates
- 새 논문 추가 시 incremental community update
- Full rebuild 없이 local community만 재생성

### 3. Cross-Community Reasoning
- 커뮤니티 간 관계 분석 (COMPARES 관계)
- Contradiction detection across communities

### 4. User Feedback Loop
- 답변 품질 피드백 수집
- 커뮤니티 요약 개선에 활용

### 5. Alternative Community Detection
- Spectral clustering
- Hierarchical clustering
- GNN-based community detection

## References

1. **Microsoft GraphRAG Paper:**
   - https://microsoft.github.io/graphrag/
   - "From Local to Global: A Graph RAG Approach to Query-Focused Summarization"

2. **Louvain Algorithm:**
   - Blondel et al. (2008): "Fast unfolding of communities in large networks"
   - python-louvain: https://github.com/taynaud/python-louvain

3. **NetworkX:**
   - https://networkx.org/
   - Graph algorithms and community detection

4. **Neo4j Community Detection:**
   - https://neo4j.com/docs/graph-data-science/current/algorithms/community/

## File Locations

- **Implementation:** `/Users/sangminpark/Desktop/rag_research/src/solver/graph_rag_v2.py`
- **Tests:** `/Users/sangminpark/Desktop/rag_research/tests/solver/test_graph_rag_v2.py`
- **Documentation:** `/Users/sangminpark/Desktop/rag_research/src/solver/README_graph_rag_v2.md`
- **Requirements:** `python-louvain>=0.16` added to requirements.txt
