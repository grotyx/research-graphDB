# Response Synthesizer Specification

## Overview

ResponseSynthesizer는 Hybrid 검색 결과(Graph + Vector)를 통합하여 학술적/임상적 질문에 대한 근거 기반 답변을 생성하는 모듈입니다.

**Module**: `src/orchestrator/response_synthesizer.py`
**Version**: 3.0
**Last Updated**: 2025-12-04

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   HybridResult List                          │
│         (Graph Evidence + Vector Contexts)                   │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              ResponseSynthesizer                             │
│                                                               │
│  1. Format Graph Evidence (statistics, p-values)            │
│  2. Format Vector Context (background text)                 │
│  3. Generate Citations (APA format)                         │
│  4. Detect Conflicts (contradictory results)                │
│  5. Calculate Confidence (evidence quality)                 │
│  6. LLM Synthesis (Gemini) or Template                      │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              SynthesizedResponse                             │
│                                                               │
│  - answer: Natural language answer                          │
│  - evidence_summary: Statistical summary                    │
│  - supporting_papers: Citations                             │
│  - confidence_score: 0~1                                    │
│  - conflicts: Contradictory findings                        │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. SynthesizedResponse

통합 응답 결과를 담는 데이터 클래스.

```python
@dataclass
class SynthesizedResponse:
    answer: str                       # LLM 생성 자연어 답변
    evidence_summary: str             # 핵심 통계 요약
    supporting_papers: list[str]      # APA 형식 인용 목록
    confidence_score: float           # 0~1 신뢰도 점수
    conflicts: list[str]              # 상충 결과 설명
    graph_evidences: list[str]        # 포맷된 Graph 근거
    vector_contexts: list[str]        # 포맷된 Vector 문맥
    metadata: dict                    # 추가 메타데이터
```

### 2. ResponseSynthesizer

메인 클래스. Hybrid 결과를 통합하여 답변 생성.

```python
class ResponseSynthesizer:
    def __init__(
        self,
        llm_client: Optional[GeminiClient] = None,
        use_llm_synthesis: bool = True
    ):
        """초기화.

        Args:
            llm_client: Gemini LLM 클라이언트
            use_llm_synthesis: LLM 사용 여부 (False면 템플릿만)
        """
```

## Main Methods

### synthesize()

Hybrid 검색 결과를 통합하여 최종 답변 생성.

```python
async def synthesize(
    self,
    query: str,
    hybrid_results: list[HybridResult],
    max_evidences: int = 5,
    max_contexts: int = 3
) -> SynthesizedResponse:
    """Hybrid 검색 결과 통합.

    Args:
        query: 원본 질문
        hybrid_results: HybridRanker 결과 목록
        max_evidences: 최대 Graph 근거 수
        max_contexts: 최대 Vector 문맥 수

    Returns:
        SynthesizedResponse 객체
    """
```

**처리 흐름**:
1. Graph vs Vector 분리
2. Graph Evidence 포맷팅
3. Vector Context 포맷팅
4. Citation 생성
5. Conflict Detection
6. Confidence Score 계산
7. Evidence Summary 생성
8. LLM 기반 답변 생성 (또는 템플릿)

### format_graph_evidence()

Graph 근거를 읽기 쉬운 형태로 포맷팅.

```python
def format_graph_evidence(
    self,
    graph_results: list[HybridResult]
) -> list[str]:
    """Graph 근거 포맷팅.

    Returns:
        포맷된 근거 문자열 목록

    Example:
        ["TLIF improved Fusion Rate to 92% vs 85% (p=0.001, Level 1b)",
         "OLIF improved VAS by 3.2 points (95% CI: 2.1-4.3, p<0.001)"]
    """
```

**포맷 구조**:
```
{Intervention} {direction} {Outcome} to {value} [vs {control}] ({statistics}, Level {level})
```

**통계 정보 포함**:
- p-value (정확한 값 또는 p<0.05)
- Effect size (Cohen's d, Odds Ratio 등)
- Confidence interval (95% CI)
- Evidence level (1a~5)

### format_vector_context()

Vector 문맥을 배경 정보로 포맷팅.

```python
def format_vector_context(
    self,
    vector_results: list[HybridResult]
) -> list[str]:
    """Vector 문맥 포맷팅.

    Returns:
        포맷된 문맥 문자열 목록

    Example:
        ["Introduction: TLIF is a minimally invasive fusion technique...",
         "Discussion: Long-term outcomes show sustained improvement..."]
    """
```

**포맷 구조**:
```
{Section}: {summary or content[:200]} [Contains statistics]
```

### generate_citations()

APA 형식 논문 인용 생성 (중복 제거).

```python
def generate_citations(
    self,
    hybrid_results: list[HybridResult]
) -> list[str]:
    """논문 인용 생성.

    Returns:
        인용 문자열 목록

    Example:
        ["Kim et al. (2024). OLIF for ASD. Spine.",
         "Lee et al. (2023). TLIF outcomes. J Neurosurg."]
    """
```

**인용 형식**:
- Single author: "Kim (2024). Title. Journal."
- Multiple authors: "Kim et al. (2024). Title. Journal."
- Graph 결과: PaperNode.get_citation() 사용
- Vector 결과: "{title} ({year})" 형식

### summarize_conflicts()

상충 결과 탐지 및 설명.

```python
def summarize_conflicts(
    self,
    graph_results: list[HybridResult]
) -> list[str]:
    """상충 결과 요약.

    Returns:
        갈등 설명 문자열 목록

    Example:
        ["Conflicting results for TLIF → PJK:
          improved (Paper paper_001) vs worsened (Paper paper_002)"]
    """
```

**탐지 로직**:
1. Intervention-Outcome 쌍으로 그룹화
2. 각 그룹 내 direction이 다른 경우 conflict 판정
3. 각 direction별 대표 논문 표시

## Confidence Calculation

근거 품질 기반 신뢰도 점수 계산.

```python
def _calculate_confidence(
    self,
    hybrid_results: list[HybridResult]
) -> float:
    """신뢰도 점수 계산.

    고려 요소:
    - Base score (HybridRanker 점수)
    - Evidence Level boost (1a/1b: 1.2x, 2a/2b: 1.0x, 기타: 0.8x)
    - Statistical significance boost (1.1x)

    Returns:
        0~1 사이의 신뢰도 점수
    """
```

**점수 계산**:
```
score = base_score * evidence_boost * significance_boost
evidence_boost = {1a/1b: 1.2, 2a/2b: 1.0, 기타: 0.8}
significance_boost = {significant: 1.1, 기타: 1.0}
final = mean(scores) (normalized to 0~1)
```

## LLM Synthesis

Gemini를 활용한 자연어 답변 생성.

```python
async def _synthesize_with_llm(
    self,
    query: str,
    graph_evidences: list[str],
    vector_contexts: list[str],
    conflicts: list[str]
) -> str:
    """LLM 기반 답변 생성.

    프롬프트 구조:
    - Question
    - Graph Evidence (통계 결과)
    - Vector Context (배경 정보)
    - Conflicting Results (상충 결과)
    - Instructions (답변 가이드라인)
    """
```

**프롬프트 요소**:
1. **Question**: 원본 질문
2. **Graph Evidence**: 통계 결과 (bulleted list)
3. **Vector Context**: 배경 정보 (bulleted list)
4. **Conflicting Results**: 상충 결과 설명
5. **Instructions**:
   - Directly address the question
   - Cite specific evidence with statistics
   - Acknowledge conflicts
   - Use academic/clinical language
   - Indicate evidence quality

**Fallback**:
- LLM 실패 시 `_template_answer()` 사용
- 템플릿 기반 구조화된 답변 생성

## Evidence Level Descriptions

```python
EVIDENCE_LEVEL_DESCRIPTIONS = {
    "1a": "Level 1a (Meta-analysis/Systematic Review) - Highest quality evidence",
    "1b": "Level 1b (RCT) - High quality evidence",
    "2a": "Level 2a (Cohort Study) - Moderate quality evidence",
    "2b": "Level 2b (Case-Control Study) - Moderate quality evidence",
    "3": "Level 3 (Case Series) - Low quality evidence",
    "4": "Level 4 (Expert Opinion) - Very low quality evidence",
    "5": "Level 5 (Ungraded) - Evidence level not assessed",
}
```

## Usage Examples

### Basic Usage

```python
from src.orchestrator import ResponseSynthesizer
from src.solver.hybrid_ranker import HybridRanker

# 1. Hybrid 검색 수행
ranker = HybridRanker(vector_db=vector_db, neo4j_client=neo4j_client)
hybrid_results = await ranker.search(
    query="Is TLIF effective for fusion?",
    query_embedding=embedding,
    top_k=10
)

# 2. 응답 생성
synthesizer = ResponseSynthesizer()
response = await synthesizer.synthesize(
    query="Is TLIF effective for fusion?",
    hybrid_results=hybrid_results,
    max_evidences=5,
    max_contexts=3
)

# 3. 결과 출력
print("Answer:", response.answer)
print("Confidence:", response.confidence_score)
print("\nSupporting Papers:")
for citation in response.supporting_papers:
    print(f"  - {citation}")
```

### Template-Only Mode

```python
# LLM 없이 템플릿만 사용
synthesizer = ResponseSynthesizer(use_llm_synthesis=False)

response = await synthesizer.synthesize(
    query="What are the outcomes of TLIF?",
    hybrid_results=hybrid_results
)
```

### Custom LLM Client

```python
from src.llm.gemini_client import GeminiClient, GeminiConfig

# Custom Gemini 설정
config = GeminiConfig(
    temperature=0.2,
    max_output_tokens=4096
)
llm_client = GeminiClient(config=config)

# Synthesizer 초기화
synthesizer = ResponseSynthesizer(llm_client=llm_client)
```

## Output Examples

### Example 1: Single Evidence

**Input**:
```python
query = "Is TLIF effective for fusion?"
hybrid_results = [
    HybridResult(
        result_type="graph",
        evidence=GraphEvidence(
            intervention="TLIF",
            outcome="Fusion Rate",
            value="92%",
            value_control="85%",
            p_value=0.001,
            is_significant=True,
            direction="improved",
            evidence_level="1b"
        ),
        paper=PaperNode(title="TLIF Study", year=2024)
    )
]
```

**Output**:
```python
SynthesizedResponse(
    answer="Based on Level 1b evidence, TLIF is effective for improving fusion rate. A randomized controlled trial showed TLIF improved fusion rate to 92% compared to 85% in the control group (p=0.001), indicating statistically significant superiority.",
    evidence_summary="1 graph evidences found, 1 statistically significant. Evidence levels: 1×Level 1b.",
    supporting_papers=["Kim et al. (2024). TLIF Study. Spine."],
    confidence_score=0.95,
    conflicts=[],
    graph_evidences=["TLIF improved Fusion Rate to 92% vs 85% (p=0.001, Level 1b)"],
    vector_contexts=[],
    metadata={"graph_count": 1, "vector_count": 0, "total_papers": 1}
)
```

### Example 2: Conflicting Evidence

**Input**:
```python
query = "Does TLIF affect PJK risk?"
hybrid_results = [
    HybridResult(evidence=GraphEvidence(intervention="TLIF", outcome="PJK", direction="improved", ...)),
    HybridResult(evidence=GraphEvidence(intervention="TLIF", outcome="PJK", direction="worsened", ...))
]
```

**Output**:
```python
SynthesizedResponse(
    answer="Evidence regarding TLIF's effect on PJK risk is conflicting. One study showed improved outcomes (15%, Level 1b), while another reported worsened outcomes (25%, Level 2a). This discrepancy may be due to differences in patient selection, follow-up duration, or surgical technique.",
    conflicts=["Conflicting results for TLIF → PJK: improved (Paper paper_001) vs worsened (Paper paper_002)"],
    confidence_score=0.65,
    ...
)
```

## Integration with Hybrid Ranker

```python
# Complete workflow
from src.orchestrator import ResponseSynthesizer
from src.solver.hybrid_ranker import HybridRanker
from src.storage.vector_db import TieredVectorDB
from src.graph.neo4j_client import Neo4jClient

# 1. Initialize components
vector_db = TieredVectorDB(persist_directory="./data/chromadb")
neo4j_client = Neo4jClient(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)

# 2. Hybrid search
ranker = HybridRanker(vector_db=vector_db, neo4j_client=neo4j_client)
hybrid_results = await ranker.search(
    query="What are effective interventions for ASD?",
    query_embedding=vector_db.get_embedding("What are effective interventions for ASD?"),
    top_k=10,
    graph_weight=0.6,
    vector_weight=0.4
)

# 3. Synthesize response
synthesizer = ResponseSynthesizer()
response = await synthesizer.synthesize(
    query="What are effective interventions for ASD?",
    hybrid_results=hybrid_results
)

# 4. Present to user
print(f"Answer (Confidence: {response.confidence_score:.2f}):")
print(response.answer)
print(f"\nEvidence: {response.evidence_summary}")
if response.conflicts:
    print("\nNote: Some conflicting results were found:")
    for conflict in response.conflicts:
        print(f"  - {conflict}")
```

## Performance Considerations

### Token Usage

- **Graph evidence formatting**: ~50 tokens per evidence
- **Vector context formatting**: ~100-200 tokens per context
- **LLM synthesis prompt**: ~500-1000 tokens
- **LLM response**: ~300-800 tokens
- **Total per query**: ~1000-3000 tokens

### Caching

LLM responses are cached by default:
- Cache key includes query + evidences + contexts
- Reduces API costs for repeated queries
- Configurable via `use_cache` parameter

### Optimization Tips

1. **Limit evidences**: Use `max_evidences=5` to control token usage
2. **Limit contexts**: Use `max_contexts=3` for background only
3. **Template mode**: Set `use_llm_synthesis=False` for fast, no-cost responses
4. **Batch queries**: Pre-cache common queries during off-peak hours

## Error Handling

### LLM Failures

```python
try:
    response = await synthesizer.synthesize(query, results)
except Exception as e:
    logger.error(f"Synthesis failed: {e}")
    # Automatic fallback to template
```

### Empty Results

```python
response = await synthesizer.synthesize(query, [])
# Returns:
# answer: "No direct evidence found in the knowledge base."
# confidence_score: 0.0
```

## Testing

Unit tests available in `tests/orchestrator/test_response_synthesizer.py`:

```bash
pytest tests/orchestrator/test_response_synthesizer.py -v
```

**Test coverage**:
- Graph evidence formatting
- Vector context formatting
- Citation generation
- Conflict detection (with/without conflicts)
- Confidence calculation
- Evidence summary generation
- Template-based synthesis

## Future Enhancements

1. **Multi-turn conversation**: Support follow-up questions
2. **Evidence ranking**: Prioritize high-quality evidence in answer
3. **Visual formatting**: Generate tables, charts for statistics
4. **Custom prompts**: Allow user-defined synthesis instructions
5. **Language support**: Korean answer generation
6. **Explanation**: Generate evidence reasoning chains

## References

- PRD: `docs/PRD.md`
- TRD: `docs/TRD_v3_GraphRAG.md`
- HybridRanker: `src/solver/hybrid_ranker.py`
- GraphEvidence: `src/solver/graph_result.py`
- GeminiClient: `src/llm/gemini_client.py`
