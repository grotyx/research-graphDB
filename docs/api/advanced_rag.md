# Advanced RAG Modules - API Documentation

> **Version**: 7.14.15
> **Last Updated**: 2026-01-13
> **Status**: Production Ready

---

## Overview

Spine GraphRAG v7.14.15는 여러 최신 RAG(Retrieval-Augmented Generation) 기법을 구현합니다:

| Module | File | Lines | Tests | 특징 | Status |
|--------|------|-------|-------|------|--------|
| Agentic RAG | `agentic_rag.py` | 1,614 | 33 | ReAct 패턴 멀티에이전트 | ✅ Active |
| GraphRAG 2.0 | ~~`graph_rag_v2.py`~~ | 1,467 | 23 | 커뮤니티 기반 계층적 검색 | ⚠️ **Archived** |
| RAPTOR | `raptor.py` | 960 | 24 | 트리 구조 재귀적 검색 | ✅ Active |
| Multi-hop Reasoning | `multi_hop_reasoning.py` | 987 | 23 | 다단계 추론 체인 | ✅ Active |

> **Note**: GraphRAG 2.0 (Microsoft-style)은 실험적 구현으로, `src/archive/legacy_v7/graph_rag_v2.py`로 아카이브되었습니다. 프로덕션 환경에서는 현재 solver 모듈을 사용하세요.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Advanced RAG Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Agentic RAG  │  │ GraphRAG 2.0 │  │    RAPTOR    │           │
│  │   (ReAct)    │  │ (Community)  │  │   (Tree)     │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
│         └────────────┬────┴─────────────────┘                   │
│                      │                                           │
│                      ▼                                           │
│         ┌──────────────────────────┐                            │
│         │   Multi-hop Reasoning    │                            │
│         │   (Query Decomposition)  │                            │
│         └──────────────────────────┘                            │
│                      │                                           │
│                      ▼                                           │
│         ┌──────────────────────────┐                            │
│         │   UnifiedSearchPipeline  │                            │
│         │   (Orchestration Layer)  │                            │
│         └──────────────────────────┘                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Agentic RAG

ReAct (Reasoning + Acting) 패턴을 활용한 멀티에이전트 RAG 시스템입니다.

### 1.1 Core Concepts

**ReAct Pattern**: Thought → Action → Observation 사이클

```
Query: "TLIF와 UBE의 VAS 개선 효과 비교"

[Thought] 두 수술법의 VAS 결과를 비교해야 함
[Action] SearchAgent.execute(query="TLIF VAS outcomes")
[Observation] TLIF shows VAS improvement of 3.2 points...

[Thought] UBE 결과도 필요함
[Action] SearchAgent.execute(query="UBE VAS outcomes")
[Observation] UBE shows VAS improvement of 2.8 points...

[Thought] 비교 합성 필요
[Action] SynthesisAgent.execute(context=[tlif_results, ube_results])
[Observation] Comparative analysis complete...

[Final Answer] TLIF와 UBE 모두 VAS 개선 효과를 보이며...
```

### 1.2 Agent Types

| Agent | Role | Capabilities |
|-------|------|--------------|
| `SearchAgent` | 정보 검색 | Hybrid search, Neo4j query |
| `SynthesisAgent` | 정보 합성 | Evidence synthesis, Summary |
| `ValidationAgent` | 결과 검증 | Fact checking, Confidence |
| `PlanningAgent` | 계획 수립 | Query decomposition, Strategy |

### 1.3 API Reference

#### AgentOrchestrator

```python
from src.solver.agentic_rag import AgentOrchestrator, AgentConfig

# 초기화
config = AgentConfig(
    max_iterations=10,
    confidence_threshold=0.7,
    enable_planning=True,
    enable_validation=True
)

orchestrator = AgentOrchestrator(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=llm_client,
    config=config
)

# 실행
response = await orchestrator.solve(
    query="Compare TLIF and PLIF outcomes",
    context={"focus": "clinical_outcomes"}
)

# 결과
print(response.answer)
print(response.confidence)
print(response.reasoning_chain)  # ReAct steps
```

#### Individual Agents

```python
from src.solver.agentic_rag import (
    SearchAgent, SynthesisAgent,
    ValidationAgent, PlanningAgent,
    AgentTask, AgentResult
)

# SearchAgent
search_agent = SearchAgent(neo4j_client, vector_db)
task = AgentTask(
    query="TLIF complications",
    context={},
    constraints={"max_results": 10}
)
result = await search_agent.execute(task)

# SynthesisAgent
synthesis_agent = SynthesisAgent(llm_client)
task = AgentTask(
    query="Summarize findings",
    context={"documents": search_result.data}
)
synthesis_result = await synthesis_agent.execute(task)
```

### 1.4 Configuration

```yaml
# config/config.yaml
agentic_rag:
  max_iterations: 10
  confidence_threshold: 0.7
  enable_planning: true
  enable_validation: true
  memory_window: 5
  timeout_seconds: 60
```

---

## 2. GraphRAG 2.0 (Microsoft-style) ⚠️ ARCHIVED

> **⚠️ Archived**: 이 모듈은 `src/archive/legacy_v7/graph_rag_v2.py`로 아카이브되었습니다.
> 아래 코드 예시는 참고용으로만 제공되며, 프로덕션에서 사용하지 마세요.

커뮤니티 감지와 계층적 요약을 활용한 그래프 기반 RAG입니다.

### 2.1 Core Concepts

**Community Detection**: Louvain 알고리즘으로 밀접하게 연결된 노드 그룹 탐지

**Hierarchical Summarization**: 리프 → 루트 방향으로 요약 계층 구축

```
Level 2 (Root):    [Spine Surgery Overview]
                         /           \
Level 1:        [Fusion Techniques]  [Decompression]
                  /    |    \              |
Level 0 (Leaf): [TLIF] [PLIF] [ALIF]    [Laminectomy]
```

### 2.2 Search Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Global** | 상위 레벨 커뮤니티 요약 검색 | 넓은 범위 질문 |
| **Local** | 특정 엔티티 주변 탐색 | 구체적 질문 |
| **Hybrid** | Global + Local 결합 | 복합 질문 |

### 2.3 API Reference

#### GraphRAGPipeline

```python
# ⚠️ ARCHIVED - 이 import는 더 이상 작동하지 않습니다
# 참고용으로만 제공됨. 아카이브 위치: src/archive/legacy_v7/graph_rag_v2.py
from src.solver.graph_rag_v2 import (
    GraphRAGPipeline, GraphRAGConfig,
    SearchType, GraphRAGResult
)

# 초기화
config = GraphRAGConfig(
    resolution=1.0,           # Louvain resolution
    max_levels=3,             # 계층 최대 깊이
    min_community_size=3,     # 최소 커뮤니티 크기
    summarization_model="gemini-2.5-flash"
)

pipeline = GraphRAGPipeline(
    neo4j_client=neo4j_client,
    llm_client=llm_client,
    config=config
)

# 인덱스 구축 (처음 한 번)
hierarchy = await pipeline.build_index(force_rebuild=False)

# Global Search (넓은 범위)
result = await pipeline.global_search(
    query="What are the main approaches to spine surgery?",
    level=1  # 상위 레벨
)

# Local Search (특정 엔티티)
result = await pipeline.local_search(
    query="What are TLIF outcomes?",
    max_hops=2
)

# Hybrid Search
result = await pipeline.hybrid_search(
    query="Compare fusion vs decompression",
    global_weight=0.4,
    local_weight=0.6
)
```

#### Community Detection

```python
# ⚠️ ARCHIVED - 이 import는 더 이상 작동하지 않습니다
from src.solver.graph_rag_v2 import CommunityDetector

detector = CommunityDetector(neo4j_client)
hierarchy = await detector.detect_communities(
    resolution=1.0,
    min_size=3
)

# 커뮤니티 정보
for comm_id, community in hierarchy.communities.items():
    print(f"Community {comm_id}: {len(community.members)} members")
    print(f"  Level: {community.level}")
    print(f"  Members: {community.members[:5]}...")
```

### 2.4 Configuration

```yaml
# config/config.yaml
graph_rag_v2:
  resolution: 1.0
  max_levels: 3
  min_community_size: 3
  summarization_model: "gemini-2.5-flash"
  cache_summaries: true
```

---

## 3. RAPTOR (Stanford-style)

재귀적 트리 구조를 활용한 추상화 계층 검색입니다.

### 3.1 Core Concepts

**Tree Organization**: 문서를 클러스터링하여 트리 구조로 조직화

**Recursive Abstraction**: 하위 노드 요약을 상위 노드로 재귀적 추상화

```
         [Root Summary]
         /      |      \
    [Cluster1] [Cluster2] [Cluster3]
     /   \       |         /    \
  [Doc1][Doc2] [Doc3]   [Doc4][Doc5]
```

### 3.2 Retrieval Strategies

| Strategy | Description | 장점 |
|----------|-------------|------|
| **Collapsed** | 모든 레벨 동시 검색 | 빠른 검색 |
| **Tree Traversal** | 루트→리프 순차 탐색 | 정확한 검색 |
| **Adaptive** | 쿼리 복잡도에 따라 선택 | 균형잡힌 성능 |

### 3.3 API Reference

#### RAPTORPipeline

```python
from src.solver.raptor import (
    RAPTORPipeline, RAPTORConfig,
    RetrievalStrategy, RAPTORResult
)

# 초기화
config = RAPTORConfig(
    max_levels=3,
    cluster_method="gmm",     # "gmm" or "kmeans"
    min_cluster_size=2,
    max_cluster_size=10,
    summarization_ratio=0.3   # 요약 비율
)

pipeline = RAPTORPipeline(
    vector_db=vector_db,
    llm_client=llm_client,
    config=config
)

# 문서 인덱싱
await pipeline.index_documents(documents=[
    {"id": "doc1", "content": "TLIF procedure involves..."},
    {"id": "doc2", "content": "UBE technique uses..."},
    # ...
])

# Collapsed Retrieval (가장 빠름)
result = await pipeline.search(
    query="What is TLIF?",
    strategy=RetrievalStrategy.COLLAPSED,
    top_k=5
)

# Tree Traversal (가장 정확)
result = await pipeline.search(
    query="Compare surgical approaches",
    strategy=RetrievalStrategy.TREE_TRAVERSAL,
    top_k=5
)

# Adaptive (자동 선택)
result = await pipeline.search(
    query="TLIF outcomes in elderly",
    strategy=RetrievalStrategy.ADAPTIVE,
    top_k=5
)

# 컨텍스트 생성
context = await pipeline.get_context(
    query="TLIF vs PLIF",
    max_tokens=2000
)
```

#### RAPTORTree

```python
from src.solver.raptor import RAPTORTree, ClusteringEngine

# 트리 구축
tree = RAPTORTree()

# 리프 노드 추가
for doc in documents:
    tree.add_leaf(doc.id, doc.content, doc.embedding)

# 클러스터링 엔진
clustering = ClusteringEngine(method="gmm")

# 트리 빌드
await tree.build(
    clustering_engine=clustering,
    summarization_engine=summarization_engine,
    max_levels=3
)

# 레벨별 노드 조회
level_0_nodes = tree.get_nodes_at_level(0)  # 리프
level_1_nodes = tree.get_nodes_at_level(1)  # 중간
```

### 3.4 Configuration

```yaml
# config/config.yaml
raptor:
  max_levels: 3
  cluster_method: "gmm"
  min_cluster_size: 2
  max_cluster_size: 10
  summarization_ratio: 0.3
  embedding_model: "text-embedding-004"
```

---

## 4. Multi-hop Reasoning

복잡한 쿼리를 여러 단계로 분해하여 추론합니다.

### 4.1 Core Concepts

**Query Decomposition**: 복잡한 쿼리를 단순한 서브쿼리로 분해

**DAG Execution**: 의존성 그래프에 따른 병렬/순차 실행

```
Query: "What is the safest fusion technique for elderly patients with stenosis?"

Decomposition:
├── Q1: "What fusion techniques are available?" (independent)
├── Q2: "What are complications in elderly?" (independent)
├── Q3: "What is stenosis treatment?" (independent)
└── Q4: "Compare safety of techniques" (depends on Q1, Q2, Q3)

Execution Plan:
Step 1: [Q1, Q2, Q3] (parallel)
Step 2: [Q4] (sequential, after Step 1)
```

### 4.2 API Reference

#### MultiHopReasoner

```python
from src.solver.multi_hop_reasoning import (
    MultiHopReasoner, MultiHopConfig,
    ReasoningChain, SubQuery
)

# 초기화
config = MultiHopConfig(
    max_hops=5,
    parallel_execution=True,
    confidence_threshold=0.6,
    context_window=3
)

reasoner = MultiHopReasoner(
    search_fn=hybrid_search,  # 기본 검색 함수
    llm_client=llm_client,
    config=config
)

# 추론 실행
result = await reasoner.reason(
    query="Compare TLIF and UBE for lumbar stenosis in elderly patients"
)

# 결과 접근
print(result.answer)
print(result.confidence)

# 추론 체인 확인
for step in result.reasoning_chain.steps:
    print(f"Hop {step.hop_number}: {step.sub_query}")
    print(f"  Evidence: {step.evidence[:100]}...")
    print(f"  Confidence: {step.confidence}")
```

#### QueryDecomposer

```python
from src.solver.multi_hop_reasoning import QueryDecomposer

decomposer = QueryDecomposer(llm_client)

# 쿼리 분해
sub_queries = await decomposer.decompose(
    query="What are the outcomes of TLIF vs PLIF for L4-L5 stenosis?",
    max_depth=3
)

for sq in sub_queries:
    print(f"SubQuery: {sq.text}")
    print(f"  Priority: {sq.priority}")
    print(f"  Dependencies: {sq.dependencies}")
```

#### HopExecutor

```python
from src.solver.multi_hop_reasoning import HopExecutor

executor = HopExecutor(search_fn, llm_client)

# 단일 hop 실행
hop_result = await executor.execute_hop(
    sub_query=sub_query,
    context=previous_context
)

print(hop_result.evidence)
print(hop_result.confidence)
```

### 4.3 Configuration

```yaml
# config/config.yaml
multi_hop:
  max_hops: 5
  parallel_execution: true
  confidence_threshold: 0.6
  context_window: 3
  decomposition_model: "gemini-2.5-flash"
```

---

## Integration Examples

### Example 1: Complex Medical Query

```python
from src.solver.unified_pipeline import UnifiedSearchPipeline
from src.solver.agentic_rag import AgentOrchestrator
from src.solver.multi_hop_reasoning import MultiHopReasoner

# 복합 쿼리
query = """
Compare the safety and efficacy of TLIF vs UBE
for lumbar stenosis in patients over 65 years old,
considering both short-term and long-term outcomes.
"""

# 1. Multi-hop으로 쿼리 분해
reasoner = MultiHopReasoner(search_fn, llm_client)
hop_result = await reasoner.reason(query)

# 2. Agentic RAG로 추가 검증
orchestrator = AgentOrchestrator(neo4j, vector_db, llm)
validated = await orchestrator.solve(
    query=query,
    context={"hop_results": hop_result.reasoning_chain}
)

# 3. 최종 답변
print(validated.answer)
print(f"Confidence: {validated.confidence}")
```

### Example 2: Graph-based Discovery

```python
# ⚠️ NOTE: graph_rag_v2는 아카이브됨. 현재 solver 모듈 사용 권장
# from src.solver.graph_rag_v2 import GraphRAGPipeline  # ARCHIVED
from src.solver.raptor import RAPTORPipeline

# GraphRAG는 아카이브됨 - 대신 현재 검색 파이프라인 사용
# graph_rag = GraphRAGPipeline(neo4j, llm)  # ARCHIVED
# global_view = await graph_rag.global_search(
#     "Overview of minimally invasive spine surgery"
# )

# RAPTOR로 세부 문서 검색
raptor = RAPTORPipeline(vector_db, llm)
detailed = await raptor.search(
    "Specific outcomes of endoscopic techniques",
    strategy=RetrievalStrategy.TREE_TRAVERSAL
)

# 결합
combined_context = f"""
Global Overview:
{global_view.answer}

Detailed Evidence:
{detailed.context}
"""
```

---

## Performance Benchmarks

| Module | Avg Latency | Memory | Accuracy |
|--------|-------------|--------|----------|
| Agentic RAG | 2-5s | 500MB | 92% |
| GraphRAG 2.0 | 1-3s | 300MB | 88% |
| RAPTOR | 0.5-2s | 400MB | 85% |
| Multi-hop | 3-8s | 600MB | 90% |

*Tested on: M1 MacBook Pro, 16GB RAM, Neo4j 5.15, Gemini 2.5 Flash*

---

## Troubleshooting

### Common Issues

**1. "Community detection failed"**
```python
# Louvain 라이브러리 설치
pip install python-louvain

# 대안: 내장 클러스터링 사용
config = GraphRAGConfig(use_builtin_clustering=True)
```

**2. "Max iterations exceeded in Agentic RAG"**
```python
# iteration 제한 증가
config = AgentConfig(max_iterations=15)

# 또는 confidence threshold 낮춤
config = AgentConfig(confidence_threshold=0.5)
```

**3. "RAPTOR tree build timeout"**
```python
# 배치 크기 조정
config = RAPTORConfig(batch_size=50)

# 또는 레벨 수 감소
config = RAPTORConfig(max_levels=2)
```

**4. "Multi-hop decomposition empty"**
```python
# 단순 쿼리는 분해 불필요
# max_depth 조정
config = MultiHopConfig(max_hops=2)
```

---

## References

1. **ReAct**: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2022)
2. **GraphRAG**: Microsoft Research, "From Local to Global: A Graph RAG Approach" (2024)
3. **RAPTOR**: Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval" (2024)
4. **Multi-hop QA**: Yang et al., "HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering" (2018)
