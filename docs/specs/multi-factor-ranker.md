# Multi-factor Ranker - Module Specification

## Overview

검색 결과를 다중 요소(의미 유사도, Evidence Level, 최신성, 섹션 Tier, 인용 유형)로 랭킹하는 모듈입니다.

## Module Info

| 항목 | 값 |
|------|-----|
| **파일 위치** | `src/solver/multi_factor_ranker.py` |
| **테스트 위치** | `tests/solver/test_multi_factor_ranker.py` |
| **의존성** | 모든 메타데이터 모듈 (간접) |
| **개발 Phase** | Phase 3 (Phase 2 완료 후) |

## Input/Output

### Input

```python
@dataclass
class SearchResult:
    """단일 검색 결과."""
    chunk_id: str
    document_id: str
    text: str

    # 검색 점수
    semantic_score: float           # 벡터 유사도 (0.0~1.0)
    graph_score: float | None       # 그래프 검색 점수 (있으면)

    # 메타데이터
    tier: int                       # 1 또는 2
    section: str                    # abstract, results 등
    source_type: SourceType         # original, citation, background
    evidence_level: EvidenceLevel   # 1a ~ 5
    publication_year: int

    # 선택적
    pico: PICOOutput | None = None
    statistics: list[StatisticResult] | None = None

@dataclass
class RankInput:
    """랭킹 입력."""
    results: list[SearchResult]
    query: str                          # 원본 쿼리
    current_year: int = 2024            # 현재 연도 (최신성 계산용)
    weights: dict | None = None         # 커스텀 가중치
```

### Output

```python
@dataclass
class RankedResult:
    """랭킹된 결과."""
    result: SearchResult

    # 최종 점수
    final_score: float
    rank: int

    # 요소별 점수
    semantic_score: float
    evidence_score: float
    recency_score: float
    tier_score: float
    source_type_score: float

    # 점수 설명
    score_explanation: dict[str, str]

@dataclass
class RankOutput:
    """랭킹 결과."""
    ranked_results: list[RankedResult]
    total_results: int

    # 통계
    top_evidence_levels: list[EvidenceLevel]  # 상위 결과의 Evidence Level
    source_type_distribution: dict[str, int]
    tier_distribution: dict[int, int]
```

## Scoring Factors

### 1. Semantic Similarity Score (기본 검색 점수)

```python
def _calculate_semantic_score(self, result: SearchResult) -> float:
    """의미적 유사도 점수."""
    # 벡터 검색 점수 그대로 사용 (이미 0~1 정규화됨)
    score = result.semantic_score

    # 그래프 점수가 있으면 결합
    if result.graph_score is not None:
        # 벡터 70% + 그래프 30%
        score = 0.7 * result.semantic_score + 0.3 * result.graph_score

    return score
```

### 2. Evidence Level Score

```python
EVIDENCE_SCORES = {
    EvidenceLevel.LEVEL_1A: 1.0,   # Meta-analysis
    EvidenceLevel.LEVEL_1B: 0.95,  # RCT
    EvidenceLevel.LEVEL_2A: 0.8,   # SR of cohort
    EvidenceLevel.LEVEL_2B: 0.7,   # Cohort
    EvidenceLevel.LEVEL_2C: 0.65,  # Outcomes research
    EvidenceLevel.LEVEL_3A: 0.55,  # SR of case-control
    EvidenceLevel.LEVEL_3B: 0.5,   # Case-control
    EvidenceLevel.LEVEL_4: 0.35,   # Case series
    EvidenceLevel.LEVEL_5: 0.2,    # Expert opinion
}

def _calculate_evidence_score(self, result: SearchResult) -> float:
    """Evidence Level 점수."""
    return EVIDENCE_SCORES.get(result.evidence_level, 0.2)
```

### 3. Recency Score (시간 가중치)

```python
def _calculate_recency_score(
    self,
    result: SearchResult,
    current_year: int,
    half_life: float = 5.0
) -> float:
    """최신성 점수 (지수 감쇠)."""

    age = current_year - result.publication_year

    if age <= 0:
        return 1.0

    # 지수 감쇠: half_life 년 후 점수 50%
    # score = 0.5 ^ (age / half_life)
    score = 0.5 ** (age / half_life)

    # 최소 점수 보장 (너무 오래되어도 0이 되지 않음)
    return max(score, 0.1)
```

### 4. Section Tier Score

```python
TIER_SCORES = {
    1: 1.0,   # 핵심 섹션 (Abstract, Results, Conclusion)
    2: 0.7,   # 상세 섹션 (Introduction, Methods, Discussion)
}

def _calculate_tier_score(self, result: SearchResult) -> float:
    """섹션 Tier 점수."""
    return TIER_SCORES.get(result.tier, 0.7)
```

### 5. Source Type Score (원본 vs 인용)

```python
SOURCE_SCORES = {
    SourceType.ORIGINAL: 1.0,     # 원본 연구 결과
    SourceType.CITATION: 0.6,     # 다른 논문 인용
    SourceType.BACKGROUND: 0.4,   # 배경 지식
}

def _calculate_source_type_score(self, result: SearchResult) -> float:
    """출처 유형 점수."""
    return SOURCE_SCORES.get(result.source_type, 0.5)
```

## Algorithm

```python
class MultiFactorRanker:
    """다중 요소 랭커."""

    DEFAULT_WEIGHTS = {
        "semantic": 0.30,      # 의미 유사도
        "evidence": 0.25,      # Evidence Level
        "recency": 0.15,       # 최신성
        "tier": 0.15,          # 섹션 Tier
        "source_type": 0.15,   # 원본/인용
    }

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.weights = self.config.get("weights", self.DEFAULT_WEIGHTS)
        self.half_life = self.config.get("half_life_years", 5.0)

    def rank(self, input_data: RankInput) -> RankOutput:
        """검색 결과 랭킹."""

        # 커스텀 가중치 적용
        weights = input_data.weights or self.weights

        ranked = []
        for result in input_data.results:
            # 각 요소별 점수 계산
            scores = {
                "semantic": self._calculate_semantic_score(result),
                "evidence": self._calculate_evidence_score(result),
                "recency": self._calculate_recency_score(
                    result, input_data.current_year, self.half_life
                ),
                "tier": self._calculate_tier_score(result),
                "source_type": self._calculate_source_type_score(result),
            }

            # 가중 합계
            final_score = sum(
                scores[factor] * weights[factor]
                for factor in scores
            )

            # 점수 설명 생성
            explanation = self._generate_explanation(scores, weights)

            ranked.append(RankedResult(
                result=result,
                final_score=final_score,
                rank=0,  # 나중에 할당
                semantic_score=scores["semantic"],
                evidence_score=scores["evidence"],
                recency_score=scores["recency"],
                tier_score=scores["tier"],
                source_type_score=scores["source_type"],
                score_explanation=explanation
            ))

        # 점수순 정렬
        ranked.sort(key=lambda x: x.final_score, reverse=True)

        # 순위 할당
        for i, item in enumerate(ranked):
            item.rank = i + 1

        # 통계 계산
        top_evidence = [r.result.evidence_level for r in ranked[:10]]
        source_dist = self._count_source_types(ranked)
        tier_dist = self._count_tiers(ranked)

        return RankOutput(
            ranked_results=ranked,
            total_results=len(ranked),
            top_evidence_levels=top_evidence,
            source_type_distribution=source_dist,
            tier_distribution=tier_dist
        )

    def _generate_explanation(
        self,
        scores: dict,
        weights: dict
    ) -> dict[str, str]:
        """점수 설명 생성."""
        explanation = {}

        for factor, score in scores.items():
            weight = weights[factor]
            contribution = score * weight

            if factor == "semantic":
                explanation[factor] = f"Relevance: {score:.2f} (contributes {contribution:.2f})"
            elif factor == "evidence":
                explanation[factor] = f"Evidence quality: {score:.2f} (contributes {contribution:.2f})"
            elif factor == "recency":
                explanation[factor] = f"Recency: {score:.2f} (contributes {contribution:.2f})"
            elif factor == "tier":
                explanation[factor] = f"Section importance: {score:.2f} (contributes {contribution:.2f})"
            elif factor == "source_type":
                explanation[factor] = f"Original content: {score:.2f} (contributes {contribution:.2f})"

        return explanation
```

## Weight Presets

용도에 따른 가중치 프리셋:

```python
WEIGHT_PRESETS = {
    # 최신 연구 중심
    "recent_research": {
        "semantic": 0.25,
        "evidence": 0.20,
        "recency": 0.30,
        "tier": 0.15,
        "source_type": 0.10,
    },

    # 고품질 근거 중심
    "high_evidence": {
        "semantic": 0.25,
        "evidence": 0.35,
        "recency": 0.10,
        "tier": 0.15,
        "source_type": 0.15,
    },

    # 원본 결과 중심
    "original_only": {
        "semantic": 0.30,
        "evidence": 0.20,
        "recency": 0.15,
        "tier": 0.10,
        "source_type": 0.25,
    },

    # 핵심 정보 중심
    "core_content": {
        "semantic": 0.30,
        "evidence": 0.20,
        "recency": 0.10,
        "tier": 0.25,
        "source_type": 0.15,
    },

    # 균형 (기본값)
    "balanced": {
        "semantic": 0.30,
        "evidence": 0.25,
        "recency": 0.15,
        "tier": 0.15,
        "source_type": 0.15,
    }
}
```

## Test Cases

### 필수 테스트

```python
class TestMultiFactorRanker:

    def test_rank_by_evidence_level(self):
        """Evidence Level이 높은 결과가 상위."""
        results = [
            make_result("A", semantic=0.9, evidence=EvidenceLevel.LEVEL_4),
            make_result("B", semantic=0.9, evidence=EvidenceLevel.LEVEL_1B),
            make_result("C", semantic=0.9, evidence=EvidenceLevel.LEVEL_2A),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={"semantic": 0.3, "evidence": 0.7, "recency": 0, "tier": 0, "source_type": 0}
        ))

        # Evidence Level 순서
        assert output.ranked_results[0].result.chunk_id == "B"  # Level 1b
        assert output.ranked_results[1].result.chunk_id == "C"  # Level 2a
        assert output.ranked_results[2].result.chunk_id == "A"  # Level 4

    def test_rank_by_recency(self):
        """최신 논문이 상위."""
        results = [
            make_result("old", year=2015),
            make_result("recent", year=2023),
            make_result("mid", year=2019),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            current_year=2024,
            weights={"semantic": 0, "evidence": 0, "recency": 1, "tier": 0, "source_type": 0}
        ))

        assert output.ranked_results[0].result.chunk_id == "recent"
        assert output.ranked_results[2].result.chunk_id == "old"

    def test_rank_original_over_citation(self):
        """원본 콘텐츠가 인용보다 상위."""
        results = [
            make_result("citation", source_type=SourceType.CITATION),
            make_result("original", source_type=SourceType.ORIGINAL),
            make_result("background", source_type=SourceType.BACKGROUND),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={"semantic": 0, "evidence": 0, "recency": 0, "tier": 0, "source_type": 1}
        ))

        assert output.ranked_results[0].result.chunk_id == "original"
        assert output.ranked_results[2].result.chunk_id == "background"

    def test_tier1_over_tier2(self):
        """Tier 1 (핵심)이 Tier 2보다 상위."""
        results = [
            make_result("methods", tier=2, section="methods"),
            make_result("results", tier=1, section="results"),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={"semantic": 0, "evidence": 0, "recency": 0, "tier": 1, "source_type": 0}
        ))

        assert output.ranked_results[0].result.chunk_id == "results"

    def test_combined_ranking(self):
        """복합 랭킹 (모든 요소 조합)."""
        results = [
            # 최신 + 높은 근거 + 원본
            make_result("best", semantic=0.8, evidence=EvidenceLevel.LEVEL_1B,
                       year=2023, tier=1, source_type=SourceType.ORIGINAL),
            # 오래됨 + 낮은 근거 + 인용
            make_result("worst", semantic=0.9, evidence=EvidenceLevel.LEVEL_4,
                       year=2010, tier=2, source_type=SourceType.CITATION),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            current_year=2024
        ))

        # semantic 점수가 낮아도 다른 요소가 좋으면 상위
        assert output.ranked_results[0].result.chunk_id == "best"

    def test_score_explanation(self):
        """점수 설명 포함."""
        results = [make_result("A")]

        output = ranker.rank(RankInput(results=results, query="test"))

        explanation = output.ranked_results[0].score_explanation
        assert "semantic" in explanation
        assert "evidence" in explanation
```

### Edge Cases

```python
def test_empty_results(self):
    """빈 결과."""
    output = ranker.rank(RankInput(results=[], query="test"))
    assert output.total_results == 0

def test_custom_weights(self):
    """커스텀 가중치."""
    results = [make_result("A")]

    custom_weights = {
        "semantic": 1.0,
        "evidence": 0,
        "recency": 0,
        "tier": 0,
        "source_type": 0,
    }

    output = ranker.rank(RankInput(
        results=results,
        query="test",
        weights=custom_weights
    ))

    # semantic만 고려
    assert output.ranked_results[0].final_score == output.ranked_results[0].semantic_score
```

## Integration Points

### Dependencies
- 모든 메타데이터 모듈의 출력 구조 (간접 의존)

### Used By
- `tiered_search.py`: 검색 결과 랭킹
- MCP `search` 도구: 최종 결과 정렬

### Configuration

```yaml
# config/config.yaml
multi_factor_ranker:
  weights:
    semantic: 0.30
    evidence: 0.25
    recency: 0.15
    tier: 0.15
    source_type: 0.15
  half_life_years: 5
  preset: "balanced"  # 또는 "high_evidence", "recent_research" 등
```

## Development Notes

1. **가중치 합계**: 항상 1.0이 되도록 정규화
2. **성능**: 대량 결과도 빠르게 처리 (복잡도 O(n log n))
3. **확장성**: 새 요소 추가 시 가중치만 조정
4. **설명 가능성**: 각 점수의 기여도를 명확히 표시
5. **프리셋**: 용도별 프리셋으로 쉬운 설정
