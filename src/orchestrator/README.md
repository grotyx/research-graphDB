# Orchestrator Module

LangChain 기반 쿼리 오케스트레이션 및 응답 생성 모듈.

## Overview

이 모듈은 LangChain을 활용하여 Neo4j Graph + Vector 하이브리드 검색과 Gemini LLM 기반 응답 생성을 통합합니다.

> **Note**: v1.14.12부터 ChromaDB가 제거되고 Neo4j Vector Index가 유일한 벡터 저장소입니다.

```
User Query
    ↓
CypherGenerator (Entity Extraction)
    ↓
HybridRetriever (Graph + Vector Search)
    ↓
Context Formatting
    ↓
LangChain + Gemini LLM
    ↓
Evidence-based Answer
```

## Components

### 1. chain_builder.py

**SpineGraphChain**: 메인 오케스트레이션 클래스

```python
from src.orchestrator import SpineGraphChain, create_chain

# 체인 생성
chain = await create_chain(
    neo4j_uri="bolt://localhost:7687",
    gemini_api_key=os.getenv("GEMINI_API_KEY"),
)

# QA 모드 실행
result = await chain.invoke(
    "OLIF가 VAS 개선에 효과적인가?",
    mode="qa"
)

print(result.answer)
for source in result.sources:
    print(f"- {source.get_citation()}")
```

**Chain Types**:

1. **QA Chain**: 증거 기반 질의응답
   - Mode: `"qa"`
   - Output: Answer + Sources + Metadata
   - Use case: 특정 질문에 대한 근거 기반 답변

2. **Conflict Chain**: 상충 결과 분석
   - Mode: `"conflict"`
   - Output: Conflict Analysis + Conflicting Sources
   - Use case: 연구 간 상반된 결과 분석

3. **Retrieval Chain**: 검색만 수행
   - Mode: `"retrieval"`
   - Output: Sources only (no LLM)
   - Use case: 관련 논문 및 근거 검색

### 2. cypher_generator.py

**CypherGenerator**: 자연어 → Cypher 변환

```python
from src.orchestrator import CypherGenerator

generator = CypherGenerator()

# 엔티티 추출
entities = generator.extract_entities(
    "OLIF가 VAS 개선에 효과적인가?"
)
# Returns: {
#     "interventions": ["OLIF"],
#     "outcomes": ["VAS"],
#     "pathologies": [],
#     "intent": "evidence_search"
# }

# Cypher 생성
cypher = generator.generate(query, entities)
# Returns: Cypher query for OLIF → VAS relationship
```

**Intent Types**:
- `evidence_search`: Intervention → Outcome 효과 검색
- `comparison`: 두 수술법 비교
- `hierarchy`: 수술법 계층 구조 탐색
- `conflict`: 상충 결과 탐지

### 3. response_synthesizer.py

**ResponseSynthesizer**: 하이브리드 결과 합성

```python
from src.orchestrator.response_synthesizer import ResponseSynthesizer

synthesizer = ResponseSynthesizer()

response = await synthesizer.synthesize(
    query="Is TLIF effective?",
    hybrid_results=results,
    max_evidences=5
)

print(response.answer)
print(f"Confidence: {response.confidence_score:.2f}")
```

## Configuration

### ChainConfig

```python
from src.orchestrator import ChainConfig

config = ChainConfig(
    gemini_model="gemini-2.5-flash-preview-05-20",
    temperature=0.1,            # LLM creativity (낮을수록 보수적)
    max_output_tokens=8192,     # 최대 응답 길이
    top_k=10,                   # 검색 결과 수
    graph_weight=0.6,           # Graph 결과 가중치
    vector_weight=0.4,          # Vector 결과 가중치
    min_p_value=0.05,           # 유의성 임계값
)

chain = SpineGraphChain(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    config=config,
    api_key=api_key,
)
```

### Environment Variables

`.env` 파일:
```bash
# Gemini API
GEMINI_API_KEY=your_api_key_here

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

## Usage Examples

### Example 1: Simple QA

```python
import asyncio
from src.orchestrator import create_chain

async def main():
    chain = await create_chain()

    result = await chain.invoke(
        "TLIF와 PLIF의 Fusion Rate 비교 결과는?",
        mode="qa"
    )

    print("Answer:", result.answer)
    print(f"Sources: {len(result.sources)}")

asyncio.run(main())
```

### Example 2: Conflict Analysis

```python
result = await chain.invoke(
    "OLIF의 Canal Area 개선 효과에 대한 논란은?",
    mode="conflict"
)

if result.metadata.get("conflicts"):
    print("Conflicting evidence detected!")
    print(result.answer)
```

### Example 3: Retrieval Only

```python
result = await chain.invoke(
    "UBE 관련 최신 연구",
    mode="retrieval"
)

for source in result.sources:
    print(f"[{source.result_type}] {source.get_citation()}")
    print(f"  Score: {source.score:.3f}")
    print(f"  {source.get_evidence_text()}")
```

### Example 4: Custom Configuration

```python
from src.orchestrator import ChainConfig

config = ChainConfig(
    top_k=20,              # 더 많은 결과
    graph_weight=0.8,      # Graph 결과 우선
    vector_weight=0.2,
    temperature=0.0,       # 가장 보수적
)

chain = await create_chain(config=config)
```

## Prompt Templates

### RETRIEVAL_QA_PROMPT

증거 기반 질의응답을 위한 시스템 프롬프트:

```python
"""You are a spine surgery research assistant specializing in evidence-based medicine.

Guidelines:
1. Base your answer ONLY on the provided evidence
2. Always cite the source papers (paper_id or title)
3. Distinguish between:
   - Graph Evidence: Statistical results (p-values, effect sizes)
   - Vector Evidence: Background information and discussion
4. If evidence is conflicting, explain both sides
5. If evidence is insufficient, say so clearly

Evidence Levels:
- 1a: Meta-analysis of RCTs (highest quality)
- 1b: Randomized Controlled Trial
- 2a: Cohort study
- 2b: Case-control study
- 3: Case series
- 4: Expert opinion (lowest quality)
"""
```

### CONFLICTING_EVIDENCE_PROMPT

상충 결과 분석을 위한 프롬프트:

```python
"""You are analyzing conflicting evidence from multiple studies.

Your task is to:
1. Identify key differences in study designs
2. Explain possible reasons for conflicting results
3. Provide a balanced summary
4. Recommend which evidence to trust based on:
   - Evidence level (1a > 1b > 2a > 2b > 3 > 4)
   - Sample size
   - Statistical significance (p-value)
   - Study recency
"""
```

## Integration with Other Modules

### Graph Module

```python
from src.graph import Neo4jClient
from src.solver import GraphSearch

# Neo4j client used by chain
neo4j_client = Neo4jClient()
await neo4j_client.connect()

# Graph search operations
graph_search = GraphSearch(neo4j_client)
results = await graph_search.search_interventions_for_outcome("VAS")
```

### Solver Module

```python
from src.solver import HybridRanker

# Hybrid ranker combines Graph + Vector
ranker = HybridRanker(
    vector_db=vector_db,
    neo4j_client=neo4j_client
)

results = await ranker.search(
    query="OLIF effectiveness",
    query_embedding=embedding,
    graph_weight=0.6,
    vector_weight=0.4
)
```

## Testing

```bash
# Run all orchestrator tests
pytest tests/orchestrator/

# Run specific test file
pytest tests/orchestrator/test_chain_builder.py

# Run with coverage
pytest tests/orchestrator/ --cov=src/orchestrator

# Run integration tests (requires services)
pytest tests/orchestrator/ -m integration
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    SpineGraphChain                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   QA Chain   │  │Conflict Chain│  │Retrieval Chain│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │             │
│         └──────────────────┴──────────────────┘             │
│                          │                                  │
│                  ┌───────▼────────┐                         │
│                  │HybridRetriever │                         │
│                  └───────┬────────┘                         │
│                          │                                  │
│         ┌────────────────┴────────────────┐                 │
│         │                                 │                 │
│  ┌──────▼────────┐              ┌────────▼────────┐        │
│  │CypherGenerator│              │  HybridRanker   │        │
│  │(Entity Extract)│              │ (Graph+Vector) │        │
│  └───────────────┘              └────────┬────────┘        │
│                                           │                 │
│                          ┌────────────────┴────────────┐    │
│                          │                             │    │
│                   ┌──────▼──────┐            ┌────────▼────┐│
│                   │ GraphSearch │            │  VectorDB   ││
│                   │  (Neo4j)    │            │(Neo4j HNSW) ││
│                   └─────────────┘            └─────────────┘│
└─────────────────────────────────────────────────────────────┘
                          │
                   ┌──────▼──────┐
                   │   Gemini    │
                   │     LLM     │
                   └─────────────┘
```

## API Reference

### SpineGraphChain

**Methods**:
- `build_retrieval_chain() -> Runnable`: 검색 체인 구축
- `build_qa_chain() -> Runnable`: QA 체인 구축
- `build_conflict_chain() -> Runnable`: 상충 분석 체인 구축
- `invoke(query: str, mode: str) -> ChainOutput`: 체인 실행
- `get_stats() -> dict`: 통계 정보

**Attributes**:
- `neo4j_client: Neo4jClient`
- `vector_db: TieredVectorDB`
- `config: ChainConfig`
- `llm: ChatGoogleGenerativeAI`
- `retriever: HybridRetriever`

### HybridRetriever

**Methods**:
- `ainvoke(query: str) -> list[HybridResult]`: 비동기 검색
- `invoke(query: str) -> list[HybridResult]`: 동기 검색

### CypherGenerator

**Methods**:
- `extract_entities(query: str) -> dict`: 엔티티 추출
- `generate(query: str, entities: dict) -> str`: Cypher 생성

## Performance Considerations

### Caching

LangChain은 자동으로 일부 결과를 캐싱합니다. 추가 캐싱을 위해:

```python
from langchain.cache import InMemoryCache
from langchain.globals import set_llm_cache

set_llm_cache(InMemoryCache())
```

### Parallel Execution

Multiple queries can be processed in parallel:

```python
queries = [
    "TLIF effectiveness?",
    "PLIF complications?",
    "OLIF vs LLIF comparison?"
]

tasks = [chain.invoke(q, mode="qa") for q in queries]
results = await asyncio.gather(*tasks)
```

### Token Optimization

Reduce token usage:

```python
config = ChainConfig(
    top_k=5,              # 적은 결과
    max_output_tokens=2048,  # 짧은 응답
)
```

## Troubleshooting

### Common Issues

1. **LangChain import errors**
   ```bash
   pip install langchain langchain-google-genai langchain-community
   ```

2. **Gemini API errors**
   - Check API key validity
   - Verify rate limits
   - Check quota usage

3. **Neo4j connection errors**
   - Ensure Neo4j is running
   - Check URI and credentials
   - Verify network connectivity

4. **Empty results**
   - Check if data is indexed
   - Verify entity extraction
   - Review query parameters

### Debug Mode

Enable verbose logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("src.orchestrator")
logger.setLevel(logging.DEBUG)
```

## Future Enhancements

- [ ] Response streaming for long answers
- [ ] Multi-turn conversation support
- [ ] Chain-of-thought reasoning
- [ ] Self-correction mechanisms
- [ ] Advanced caching strategies
- [ ] Batch processing optimizations

## References

- [LangChain Documentation](https://python.langchain.com/)
- [Gemini API](https://ai.google.dev/docs)
- [Neo4j Cypher](https://neo4j.com/docs/cypher-manual/)
- [Neo4j Vector Index](https://neo4j.com/docs/cypher-manual/current/indexes-for-vector-search/)
