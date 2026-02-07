# Conflict Detector - Module Specification

## Overview

동일 주제에 대한 연구들 간의 상반된 결과를 탐지하고 분석하는 모듈입니다.

## Module Info

| 항목 | 값 |
|------|-----|
| **파일 위치** | `src/solver/conflict_detector.py` |
| **테스트 위치** | `tests/solver/test_conflict_detector.py` |
| **의존성** | `stats_parser.py`, `pico_extractor.py` |
| **개발 Phase** | Phase 2 (Phase 1 완료 후) |

## Input/Output

### Input

```python
@dataclass
class StudyResult:
    """단일 연구 결과."""
    study_id: str
    title: str
    pico: PICOOutput                    # PICO 정보
    statistics: list[StatisticResult]   # 통계 결과
    evidence_level: EvidenceLevel       # 근거 수준
    year: int
    sample_size: int | None = None

@dataclass
class ConflictInput:
    """충돌 탐지 입력."""
    studies: list[StudyResult]          # 비교할 연구들
    topic: str | None = None            # 검색 주제 (선택)
```

### Output

```python
class ConflictType(Enum):
    """충돌 유형."""
    DIRECTION = "direction"           # 효과 방향 상충 (positive vs negative)
    MAGNITUDE = "magnitude"           # 효과 크기 상충 (strong vs weak)
    SIGNIFICANCE = "significance"     # 유의성 상충 (significant vs not)
    SAFETY = "safety"                 # 안전성 상충

class ConflictSeverity(Enum):
    """충돌 심각도."""
    HIGH = "high"       # 결론에 큰 영향
    MEDIUM = "medium"   # 일부 조건에서 다름
    LOW = "low"         # 경미한 차이

@dataclass
class ConflictPair:
    """충돌 쌍."""
    study_a: StudyResult
    study_b: StudyResult
    conflict_type: ConflictType
    severity: ConflictSeverity

    # 충돌 상세
    outcome: str                      # 충돌하는 결과 변수
    stat_a: StatisticResult           # 연구 A 통계
    stat_b: StatisticResult           # 연구 B 통계

    # 분석
    possible_reasons: list[str]       # 가능한 원인
    recommendation: str               # 권장 결론

@dataclass
class ConflictOutput:
    """충돌 탐지 결과."""
    conflicts: list[ConflictPair]
    has_conflicts: bool
    conflict_summary: str

    # 메타 분석
    consensus_direction: EffectDirection | None  # 다수 연구 방향
    recommended_conclusion: str
    confidence: float                            # 결론 신뢰도
```

## Detection Algorithm

### 1. PICO Similarity Check

먼저 비교 가능한 연구인지 확인:

```python
def _is_comparable(self, study_a: StudyResult, study_b: StudyResult) -> bool:
    """두 연구가 비교 가능한지 확인."""

    pico_a = study_a.pico
    pico_b = study_b.pico

    # Population 유사성
    pop_similar = self._calculate_similarity(
        pico_a.population, pico_b.population
    ) > 0.5

    # Intervention 유사성
    int_similar = self._calculate_similarity(
        pico_a.intervention, pico_b.intervention
    ) > 0.6

    # Outcome 유사성 (가장 중요)
    out_similar = self._calculate_similarity(
        pico_a.outcome, pico_b.outcome
    ) > 0.5

    return pop_similar and int_similar and out_similar
```

### 2. Effect Direction Comparison

```python
def _detect_direction_conflict(
    self,
    stat_a: StatisticResult,
    stat_b: StatisticResult
) -> bool:
    """효과 방향 충돌 탐지."""

    # 둘 다 유의한 경우만 진정한 충돌
    if not (stat_a.is_significant and stat_b.is_significant):
        return False

    # 방향이 반대면 충돌
    if stat_a.effect_direction == EffectDirection.POSITIVE and \
       stat_b.effect_direction == EffectDirection.NEGATIVE:
        return True

    if stat_a.effect_direction == EffectDirection.NEGATIVE and \
       stat_b.effect_direction == EffectDirection.POSITIVE:
        return True

    return False
```

### 3. Effect Magnitude Comparison

```python
def _detect_magnitude_conflict(
    self,
    stat_a: StatisticResult,
    stat_b: StatisticResult
) -> bool:
    """효과 크기 충돌 탐지."""

    # 같은 방향이지만 크기가 크게 다른 경우
    if stat_a.effect_direction != stat_b.effect_direction:
        return False  # 방향 충돌은 별도 처리

    # HR/OR/RR의 경우
    if stat_a.stat_type == stat_b.stat_type:
        ratio = max(stat_a.value, stat_b.value) / min(stat_a.value, stat_b.value)

        # 2배 이상 차이나면 크기 충돌
        if ratio > 2.0:
            return True

        # CI가 겹치지 않으면 충돌
        if stat_a.ci and stat_b.ci:
            if stat_a.ci.upper < stat_b.ci.lower or \
               stat_b.ci.upper < stat_a.ci.lower:
                return True

    return False
```

### 4. Significance Conflict

```python
def _detect_significance_conflict(
    self,
    stat_a: StatisticResult,
    stat_b: StatisticResult
) -> bool:
    """유의성 충돌 탐지 (한쪽만 유의)."""

    if stat_a.is_significant is None or stat_b.is_significant is None:
        return False

    # 한쪽만 유의한 경우
    return stat_a.is_significant != stat_b.is_significant
```

### 5. Conflict Reason Analysis

```python
def _analyze_conflict_reasons(
    self,
    study_a: StudyResult,
    study_b: StudyResult
) -> list[str]:
    """충돌 원인 분석."""

    reasons = []

    # 1. Evidence Level 차이
    if study_a.evidence_level != study_b.evidence_level:
        reasons.append(
            f"Evidence level difference: {study_a.evidence_level.value} vs {study_b.evidence_level.value}"
        )

    # 2. Sample size 차이
    if study_a.sample_size and study_b.sample_size:
        ratio = max(study_a.sample_size, study_b.sample_size) / \
                min(study_a.sample_size, study_b.sample_size)
        if ratio > 3:
            reasons.append(
                f"Sample size difference: {study_a.sample_size} vs {study_b.sample_size}"
            )

    # 3. Population 차이
    pop_diff = self._compare_populations(study_a.pico, study_b.pico)
    if pop_diff:
        reasons.append(f"Population difference: {pop_diff}")

    # 4. 시간 차이
    year_diff = abs(study_a.year - study_b.year)
    if year_diff > 5:
        reasons.append(
            f"Publication year gap: {year_diff} years ({study_a.year} vs {study_b.year})"
        )

    # 5. Comparison 차이
    comp_diff = self._compare_comparisons(study_a.pico, study_b.pico)
    if comp_diff:
        reasons.append(f"Comparison difference: {comp_diff}")

    if not reasons:
        reasons.append("No obvious methodological differences identified")

    return reasons
```

## Algorithm

```python
class ConflictDetector:
    """연구 간 충돌 탐지기."""

    def detect(self, input_data: ConflictInput) -> ConflictOutput:
        """충돌 탐지."""

        conflicts = []
        studies = input_data.studies

        # 1. 모든 연구 쌍 비교
        for i, study_a in enumerate(studies):
            for study_b in studies[i+1:]:

                # 비교 가능한지 확인
                if not self._is_comparable(study_a, study_b):
                    continue

                # 각 outcome별로 충돌 확인
                pair_conflicts = self._compare_studies(study_a, study_b)
                conflicts.extend(pair_conflicts)

        # 2. 충돌 심각도 평가
        for conflict in conflicts:
            conflict.severity = self._assess_severity(conflict)

        # 3. Consensus 방향 결정
        consensus = self._determine_consensus(studies)

        # 4. 권장 결론 생성
        recommendation = self._generate_recommendation(
            conflicts, consensus, studies
        )

        return ConflictOutput(
            conflicts=conflicts,
            has_conflicts=len(conflicts) > 0,
            conflict_summary=self._summarize_conflicts(conflicts),
            consensus_direction=consensus,
            recommended_conclusion=recommendation,
            confidence=self._calculate_confidence(conflicts, studies)
        )

    def _generate_recommendation(
        self,
        conflicts: list[ConflictPair],
        consensus: EffectDirection,
        studies: list[StudyResult]
    ) -> str:
        """권장 결론 생성."""

        if not conflicts:
            return "Studies show consistent results. Conclusions can be drawn with high confidence."

        # Evidence Level 기준 최고 연구
        best_evidence = min(studies, key=lambda s: s.evidence_level.value)

        # RCT가 있으면 RCT 우선
        rcts = [s for s in studies if "1" in s.evidence_level.value]

        if rcts:
            if consensus == EffectDirection.POSITIVE:
                return f"Despite some conflicting results, high-quality evidence (Level 1) supports a beneficial effect. Recommend following RCT findings."
            elif consensus == EffectDirection.NEGATIVE:
                return f"High-quality evidence suggests potential harm. Caution advised."
            else:
                return f"Mixed results even among RCTs. Further research needed."

        return f"Conflicting results with limited high-quality evidence. Consider patient-specific factors."
```

## Test Cases

### 필수 테스트

```python
class TestConflictDetector:

    def test_detect_direction_conflict(self):
        """방향 충돌 탐지."""
        study_a = StudyResult(
            study_id="A",
            title="Study A",
            pico=mock_pico("diabetes", "metformin", "placebo", "HbA1c"),
            statistics=[StatisticResult(
                stat_type=StatisticType.HAZARD_RATIO,
                value=0.75,
                effect_direction=EffectDirection.POSITIVE,
                is_significant=True
            )],
            evidence_level=EvidenceLevel.LEVEL_1B,
            year=2020
        )

        study_b = StudyResult(
            study_id="B",
            title="Study B",
            pico=mock_pico("diabetes", "metformin", "placebo", "HbA1c"),
            statistics=[StatisticResult(
                stat_type=StatisticType.HAZARD_RATIO,
                value=1.25,
                effect_direction=EffectDirection.NEGATIVE,
                is_significant=True
            )],
            evidence_level=EvidenceLevel.LEVEL_2A,
            year=2019
        )

        result = detector.detect(ConflictInput(studies=[study_a, study_b]))

        assert result.has_conflicts == True
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == ConflictType.DIRECTION

    def test_detect_magnitude_conflict(self):
        """크기 충돌 탐지."""
        # HR 0.5 vs HR 0.9 (같은 방향, 큰 차이)
        study_a = make_study("A", hr=0.5)
        study_b = make_study("B", hr=0.9)

        result = detector.detect(ConflictInput(studies=[study_a, study_b]))

        # 같은 방향이지만 크기 차이
        assert any(c.conflict_type == ConflictType.MAGNITUDE for c in result.conflicts)

    def test_no_conflict_consistent_results(self):
        """일관된 결과는 충돌 없음."""
        study_a = make_study("A", hr=0.75, significant=True)
        study_b = make_study("B", hr=0.80, significant=True)

        result = detector.detect(ConflictInput(studies=[study_a, study_b]))

        assert result.has_conflicts == False

    def test_conflict_reason_analysis(self):
        """충돌 원인 분석."""
        study_a = StudyResult(
            study_id="A",
            pico=mock_pico("elderly diabetes", "metformin", "placebo", "mortality"),
            statistics=[make_stat(hr=0.6)],
            evidence_level=EvidenceLevel.LEVEL_1B,
            year=2020,
            sample_size=5000
        )

        study_b = StudyResult(
            study_id="B",
            pico=mock_pico("young diabetes", "metformin", "placebo", "mortality"),
            statistics=[make_stat(hr=1.1)],
            evidence_level=EvidenceLevel.LEVEL_2A,
            year=2015,
            sample_size=200
        )

        result = detector.detect(ConflictInput(studies=[study_a, study_b]))

        # 원인 분석 포함
        assert len(result.conflicts[0].possible_reasons) > 0
        assert any("Population" in r for r in result.conflicts[0].possible_reasons)
        assert any("Sample size" in r for r in result.conflicts[0].possible_reasons)

    def test_recommend_higher_evidence(self):
        """높은 근거 수준 우선 권장."""
        rct = make_study("RCT", hr=0.7, evidence=EvidenceLevel.LEVEL_1B)
        cohort = make_study("Cohort", hr=1.2, evidence=EvidenceLevel.LEVEL_2B)

        result = detector.detect(ConflictInput(studies=[rct, cohort]))

        assert "RCT" in result.recommended_conclusion or "Level 1" in result.recommended_conclusion
```

### Edge Cases

```python
def test_incomparable_studies(self):
    """비교 불가능한 연구들."""
    diabetes_study = make_study("A", pico=mock_pico("diabetes", "metformin", ...))
    cancer_study = make_study("B", pico=mock_pico("lung cancer", "chemotherapy", ...))

    result = detector.detect(ConflictInput(studies=[diabetes_study, cancer_study]))

    # 다른 주제는 충돌 아님
    assert result.has_conflicts == False

def test_single_study(self):
    """연구가 하나뿐인 경우."""
    result = detector.detect(ConflictInput(studies=[make_study("A")]))

    assert result.has_conflicts == False

def test_all_non_significant(self):
    """모든 결과가 비유의한 경우."""
    study_a = make_study("A", hr=0.9, significant=False)
    study_b = make_study("B", hr=1.1, significant=False)

    result = detector.detect(ConflictInput(studies=[study_a, study_b]))

    # 둘 다 비유의하면 심각한 충돌 아님
    assert not result.has_conflicts or result.conflicts[0].severity == ConflictSeverity.LOW
```

## Integration Points

### Dependencies
- `stats_parser.py`: 통계 결과 구조
- `pico_extractor.py`: PICO 유사성 비교

### Used By
- `medical_reasoner` (Subagent): 추론 시 충돌 확인
- `paper_writer` (Subagent): 상충 연구 섹션 작성
- `conflict_analyzer` (Subagent): 충돌 분석 보고서

### Configuration

```yaml
# config/config.yaml
conflict_detector:
  pico_similarity_threshold: 0.5
  magnitude_ratio_threshold: 2.0
  require_both_significant: true
```

## Development Notes

1. **PICO 비교**: 정확한 비교 위해 의미적 유사도 사용 (향후 임베딩 기반)
2. **다중 Outcome**: 각 outcome별로 별도 충돌 확인
3. **우선순위**: Direction > Significance > Magnitude 순으로 심각
4. **메타 분석 참조**: 기존 메타 분석이 있으면 그 결론 참조
