# Spine GraphRAG v7.14.15 - Quick Reference Card

> 빠른 참조를 위한 핵심 명령어 및 사용법

---

## 1. 환경 설정

```bash
# Neo4j 시작
docker-compose up -d

# 30초 대기 후 스키마 초기화
python scripts/init_neo4j.py

# Web UI 시작
streamlit run web/app.py

# MCP 서버 시작
python -m src.medical_mcp

# Paper-Entity 관계 재색인 (검색 문제 시)
python scripts/reindex_relationships.py --force
```

## 2. 기본 검색 (UnifiedSearchPipeline)

```python
from src.solver.unified_pipeline import UnifiedSearchPipeline, SearchOptions

# 초기화
pipeline = UnifiedSearchPipeline(neo4j_client, vector_db, llm_client)

# 기본 검색
result = await pipeline.search("TLIF outcomes for lumbar stenosis")

# 옵션 검색
options = SearchOptions(
    graph_weight=0.6,      # Graph 비중
    vector_weight=0.4,     # Vector 비중
    top_k=10,
    include_evidence=True,
    detect_conflicts=True
)
result = await pipeline.search("Compare TLIF vs UBE", options=options)

# 결과
print(result.answer)
print(result.evidence)
print(result.conflicts)
```

## 3. Advanced RAG 모듈

### 3.1 Agentic RAG (ReAct 패턴)

```python
from src.solver.agentic_rag import AgentOrchestrator, AgentConfig

config = AgentConfig(max_iterations=10, confidence_threshold=0.7)
orchestrator = AgentOrchestrator(neo4j, vector_db, llm, config=config)

# 자동 멀티에이전트 검색
response = await orchestrator.solve("Compare surgical outcomes")

print(response.answer)
print(response.reasoning_chain)  # ReAct steps
```

### 3.2 GraphRAG 2.0 (커뮤니티 기반)

```python
from src.solver.graph_rag_v2 import GraphRAGPipeline

pipeline = GraphRAGPipeline(neo4j, llm)

# 인덱스 구축 (최초 1회)
await pipeline.build_index()

# Global Search (넓은 범위)
result = await pipeline.global_search("Spine surgery overview")

# Local Search (특정 엔티티)
result = await pipeline.local_search("TLIF complications", max_hops=2)

# Hybrid Search
result = await pipeline.hybrid_search("Compare approaches", global_weight=0.4)
```

### 3.3 RAPTOR (트리 구조 검색)

```python
from src.solver.raptor import RAPTORPipeline, RetrievalStrategy

pipeline = RAPTORPipeline(vector_db, llm)

# 문서 인덱싱
await pipeline.index_documents(documents)

# Collapsed (가장 빠름)
result = await pipeline.search("What is TLIF?",
    strategy=RetrievalStrategy.COLLAPSED)

# Tree Traversal (가장 정확)
result = await pipeline.search("Compare techniques",
    strategy=RetrievalStrategy.TREE_TRAVERSAL)

# Adaptive (자동 선택)
result = await pipeline.search("Surgical outcomes",
    strategy=RetrievalStrategy.ADAPTIVE)
```

### 3.4 Multi-hop Reasoning (다단계 추론)

```python
from src.solver.multi_hop_reasoning import MultiHopReasoner, MultiHopConfig

config = MultiHopConfig(max_hops=5, parallel_execution=True)
reasoner = MultiHopReasoner(search_fn, llm, config=config)

# 복잡한 쿼리 다단계 추론
result = await reasoner.reason(
    "What is the safest fusion technique for elderly patients with stenosis?"
)

print(result.answer)
for step in result.reasoning_chain.steps:
    print(f"Hop {step.hop_number}: {step.sub_query}")
```

## 4. 유틸리티 모듈

### 4.1 Evidence Synthesizer (근거 합성)

```python
from src.solver.evidence_synthesizer import EvidenceSynthesizer

synthesizer = EvidenceSynthesizer()
synthesis = await synthesizer.synthesize(
    intervention="TLIF",
    outcome="VAS",
    evidence_list=evidences
)

print(synthesis.grade_level)  # HIGH, MODERATE, LOW
print(synthesis.pooled_effect)
print(synthesis.recommendation)
```

### 4.2 Conflict Detector (상충 탐지)

```python
from src.solver.conflict_detector import ConflictDetector, ConflictSeverity
from src.solver.conflict_summary import ConflictSummaryGenerator

detector = ConflictDetector()
conflicts = await detector.detect(
    intervention="TLIF",
    outcome="VAS"
)

for conflict in conflicts:
    print(f"Severity: {conflict.severity}")  # IntEnum (CRITICAL=4, HIGH=3, ...)
    print(f"Papers: {conflict.conflicting_papers}")
    print(f"Summary:\n{conflict.summary}")  # Auto-generated

# Custom summary generation
generator = ConflictSummaryGenerator()
brief = generator.generate_brief(conflict)  # One-line summary
json_data = generator.generate_json_summary(conflict)  # JSON-serializable
```

### 4.3 Evidence Level Classifier (근거 수준 분류)

```python
from src.builder.evidence_classifier import (
    EvidenceLevelClassifier,
    EvidenceLevel,
    get_evidence_level_from_publication_type  # Legacy helper
)

classifier = EvidenceLevelClassifier()

# From PubMed publication types (가장 정확)
result = classifier.classify(
    publication_types=["Randomized Controlled Trial"]
)
print(f"Level: {result.level.value}")    # "1b"
print(f"Confidence: {result.confidence}") # 1.0
print(f"Reason: {result.reason}")
print(f"Matched: {result.matched_terms}")

# From study design text
result = classifier.classify(
    study_design="retrospective cohort analysis"
)
print(f"Level: {result.level.value}")  # "2b"

# From title (lowest confidence)
result = classifier.classify(
    title="Meta-analysis of TLIF outcomes"
)
print(f"Level: {result.level.value}")  # "1a"

# Combined classification (highest evidence wins)
result = classifier.classify(
    publication_types=["Clinical Trial"],
    study_design="randomized controlled",
    title="RCT comparing TLIF vs PLIF"
)

# Legacy API (backward compatible)
level = get_evidence_level_from_publication_type(["Meta-Analysis"])
print(level)  # "1a"

# Evidence level comparison
if EvidenceLevel.LEVEL_1A > EvidenceLevel.LEVEL_2B:
    print("Meta-analysis is stronger than cohort study")
```

### 4.4 PubMed Enricher (서지 정보 강화)

```python
from src.builder.pubmed_enricher import PubMedEnricher, enrich_paper_metadata

# 초기화
enricher = PubMedEnricher(email="your@email.com")

# DOI로 검색 (가장 정확)
result = await enricher.enrich_by_doi("10.1016/j.spinee.2023.01.001")

# 제목으로 검색 (fallback)
result = await enricher.enrich_by_title(
    title="TLIF vs PLIF outcomes",
    authors=["Kim JH"],
    year=2023
)

# 자동 검색 (PMID → DOI → Title 순)
result = await enricher.auto_enrich(
    title="Comparison of TLIF and PLIF",
    doi="10.1016/j.spinee.2023.01.001",
    authors=["Kim JH"]
)

if result:
    print(f"PMID: {result.pmid}")
    print(f"MeSH Terms: {result.mesh_terms}")
    print(f"Publication Types: {result.publication_types}")
    print(f"Confidence: {result.confidence:.2f}")

# Publication type에서 근거 수준 추론
evidence_level = enricher.get_evidence_level_from_publication_type(
    result.publication_types
)
print(f"Evidence Level: {evidence_level}")  # "1b" for RCT
```

### 4.5 Direction Determiner (방향성 판단)

```python
from src.solver.direction_determiner import DirectionDeterminer

determiner = DirectionDeterminer()
direction = determiner.determine(
    outcome="VAS",
    change=-2.3  # 감소
)

print(direction)  # "improved" (VAS는 낮을수록 좋음)
```

## 5. 설정 파일

```yaml
# config/config.yaml

# Neo4j 설정
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "spine_graph_2024"
  database: "neo4j"

# LLM 설정
llm:
  model: "gemini-2.5-flash-preview-05-20"
  temperature: 0.1
  max_tokens: 8192

# Advanced RAG 설정
agentic_rag:
  max_iterations: 10
  confidence_threshold: 0.7

graph_rag_v2:
  resolution: 1.0
  max_levels: 3

raptor:
  cluster_method: "gmm"
  max_levels: 3

multi_hop:
  max_hops: 5
  parallel_execution: true
```

## 6. MCP 도구 (Claude Desktop)

### 기본 도구
| 도구 | 설명 |
|------|------|
| `add_pdf` | PDF 업로드 및 처리 |
| `search` | 하이브리드 검색 |
| `list_documents` | 문서 목록 조회 |
| `delete_document` | 문서 삭제 |
| `search_pubmed` | PubMed 검색 |

### v3.1 신규 도구
| 도구 | 설명 |
|------|------|
| `adaptive_search` | 쿼리 유형별 최적화 검색 |
| `synthesize_evidence` | GRADE 기반 근거 합성 |
| `detect_conflicts` | 연구 결과 상충 탐지 |
| `get_intervention_hierarchy` | 수술법 계층 조회 |
| `get_comparable_interventions` | 비교 가능 수술법 조회 |

## 7. 테스트 실행

```bash
# 전체 테스트
PYTHONPATH=./src pytest tests/ -v

# Advanced RAG 테스트만
PYTHONPATH=./src pytest tests/solver/test_agentic_rag.py -v
PYTHONPATH=./src pytest tests/solver/test_graph_rag_v2.py -v
PYTHONPATH=./src pytest tests/solver/test_raptor.py -v
PYTHONPATH=./src pytest tests/solver/test_multi_hop.py -v

# 특정 모듈 테스트
PYTHONPATH=./src pytest tests/solver/ -k "adaptive" -v
```

## 8. 문제 해결

| 문제 | 해결 방법 |
|------|----------|
| Neo4j 연결 실패 | `docker-compose restart neo4j` |
| Louvain 에러 | `pip install python-louvain` |
| Import 에러 | `export PYTHONPATH=./src` |
| LLM timeout | config에서 `timeout: 120` 설정 |
| Memory 부족 | `batch_size` 감소 |
| Evidence 검색 결과 없음 | `python scripts/reindex_relationships.py --force` |
| VectorDB required 에러 | v7.14.15에서 자동 fallback (MCP 재시작) |
| p_value 비교 에러 | v7.14.15에서 수정됨 (MCP 재시작) |

---

**Full Documentation**: [docs/api/advanced_rag.md](api/advanced_rag.md)
**Development Status**: [docs/Development_Status_v3.md](Development_Status_v3.md)

---

*Last Updated: 2026-01-13 (v7.14.15)*
