"""Multi-factor Ranker module for ranking search results by multiple criteria."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

try:
    from builder.citation_detector import SourceType
    from builder.study_classifier import EvidenceLevel
    from builder.pico_extractor import PICOOutput
    from builder.stats_parser import StatisticResult
except ImportError:
    from dataclasses import dataclass as _dataclass
    from enum import Enum as _Enum

    class SourceType(_Enum):
        ORIGINAL = "original"
        CITATION = "citation"  # Fixed: CITED → CITATION to match builder.citation_detector
        BACKGROUND = "background"
        UNKNOWN = "unknown"

    class EvidenceLevel(_Enum):
        LEVEL_1A = "1a"
        LEVEL_1B = "1b"
        LEVEL_2A = "2a"
        LEVEL_2B = "2b"
        LEVEL_2C = "2c"
        LEVEL_3A = "3a"
        LEVEL_3B = "3b"
        LEVEL_4 = "4"
        LEVEL_5 = "5"

    @_dataclass
    class PICOOutput:
        population: str = ""
        intervention: str = ""
        comparison: str = ""
        outcome: str = ""

    @_dataclass
    class StatisticResult:
        value: float = 0.0


@dataclass
class SearchResult:
    """단일 검색 결과."""
    chunk_id: str
    document_id: str
    text: str

    # 검색 점수
    semantic_score: float           # 벡터 유사도 (0.0~1.0)
    graph_score: Optional[float] = None  # 그래프 검색 점수 (있으면)

    # 메타데이터
    tier: int = 1                   # 1 또는 2
    section: str = "other"          # abstract, results 등
    source_type: SourceType = SourceType.ORIGINAL
    evidence_level: EvidenceLevel = EvidenceLevel.LEVEL_5
    publication_year: int = 2020

    # 선택적
    pico: Optional[PICOOutput] = None
    statistics: Optional[list[StatisticResult]] = None

    # 추가 메타데이터
    title: Optional[str] = None
    authors: Optional[list[str]] = None


@dataclass
class RankInput:
    """랭킹 입력."""
    results: list[SearchResult]
    query: str                          # 원본 쿼리
    current_year: int = 2024            # 현재 연도 (최신성 계산용)
    weights: Optional[dict] = None      # 커스텀 가중치


@dataclass
class RankedResult:
    """랭킹된 결과."""
    result: SearchResult

    # 최종 점수
    final_score: float = 0.0
    rank: int = 0

    # 요소별 점수
    semantic_score: float = 0.0
    evidence_score: float = 0.0
    recency_score: float = 0.0
    tier_score: float = 0.0
    source_type_score: float = 0.0

    # 점수 설명
    score_explanation: dict = field(default_factory=dict)


@dataclass
class RankOutput:
    """랭킹 결과."""
    ranked_results: list[RankedResult] = field(default_factory=list)
    total_results: int = 0

    # 통계
    top_evidence_levels: list[EvidenceLevel] = field(default_factory=list)
    source_type_distribution: dict = field(default_factory=dict)
    tier_distribution: dict = field(default_factory=dict)


class WeightPreset(Enum):
    """가중치 프리셋."""
    BALANCED = "balanced"
    RECENT_RESEARCH = "recent_research"
    HIGH_EVIDENCE = "high_evidence"
    ORIGINAL_ONLY = "original_only"
    CORE_CONTENT = "core_content"


class MultiFactorRanker:
    """다중 요소 랭커."""

    # 기본 가중치
    DEFAULT_WEIGHTS = {
        "semantic": 0.30,      # 의미 유사도
        "evidence": 0.25,      # Evidence Level
        "recency": 0.15,       # 최신성
        "tier": 0.15,          # 섹션 Tier
        "source_type": 0.15,   # 원본/인용
    }

    # 가중치 프리셋
    WEIGHT_PRESETS = {
        WeightPreset.BALANCED: {
            "semantic": 0.30,
            "evidence": 0.25,
            "recency": 0.15,
            "tier": 0.15,
            "source_type": 0.15,
        },
        WeightPreset.RECENT_RESEARCH: {
            "semantic": 0.25,
            "evidence": 0.20,
            "recency": 0.30,
            "tier": 0.15,
            "source_type": 0.10,
        },
        WeightPreset.HIGH_EVIDENCE: {
            "semantic": 0.25,
            "evidence": 0.35,
            "recency": 0.10,
            "tier": 0.15,
            "source_type": 0.15,
        },
        WeightPreset.ORIGINAL_ONLY: {
            "semantic": 0.30,
            "evidence": 0.20,
            "recency": 0.15,
            "tier": 0.10,
            "source_type": 0.25,
        },
        WeightPreset.CORE_CONTENT: {
            "semantic": 0.30,
            "evidence": 0.20,
            "recency": 0.10,
            "tier": 0.25,
            "source_type": 0.15,
        },
    }

    # Evidence Level 점수
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

    # Tier 점수
    TIER_SCORES = {
        1: 1.0,   # 핵심 섹션 (Abstract, Results, Conclusion)
        2: 0.7,   # 상세 섹션 (Introduction, Methods, Discussion)
    }

    # Source Type 점수
    SOURCE_SCORES = {
        SourceType.ORIGINAL: 1.0,     # 원본 연구 결과
        SourceType.CITATION: 0.6,     # 다른 논문 인용 (Fixed: CITED → CITATION)
        SourceType.BACKGROUND: 0.4,   # 배경 지식
    }

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - weights: 커스텀 가중치 (기본값: DEFAULT_WEIGHTS)
                - preset: 가중치 프리셋 (기본값: "balanced")
                - half_life_years: 최신성 반감기 (기본값: 5.0)
                - graph_weight: 그래프 점수 가중치 (기본값: 0.3)
        """
        self.config = config or {}

        # 프리셋 적용
        preset_name = self.config.get("preset", "balanced")
        try:
            preset = WeightPreset(preset_name)
            self.weights = self.WEIGHT_PRESETS.get(preset, self.DEFAULT_WEIGHTS).copy()
        except ValueError:
            self.weights = self.DEFAULT_WEIGHTS.copy()

        # 커스텀 가중치로 오버라이드
        if "weights" in self.config:
            self.weights.update(self.config["weights"])

        # 가중치 정규화
        self._normalize_weights()

        self.half_life = self.config.get("half_life_years", 5.0)
        self.graph_weight = self.config.get("graph_weight", 0.3)

    def _normalize_weights(self) -> None:
        """가중치 합계가 1.0이 되도록 정규화."""
        total = sum(self.weights.values())
        if total > 0 and abs(total - 1.0) > 0.001:
            for key in self.weights:
                self.weights[key] /= total

    def rank(self, input_data: RankInput) -> RankOutput:
        """검색 결과 랭킹.

        Args:
            input_data: 랭킹 입력

        Returns:
            랭킹 결과
        """
        if not input_data.results:
            return RankOutput(
                ranked_results=[],
                total_results=0,
                top_evidence_levels=[],
                source_type_distribution={},
                tier_distribution={}
            )

        # 커스텀 가중치 적용
        weights = input_data.weights if input_data.weights else self.weights

        # 가중치 정규화
        total_weight = sum(weights.values())
        if total_weight > 0 and abs(total_weight - 1.0) > 0.001:
            weights = {k: v / total_weight for k, v in weights.items()}

        ranked = []
        for result in input_data.results:
            # 각 요소별 점수 계산
            scores = {
                "semantic": self._calculate_semantic_score(result),
                "evidence": self._calculate_evidence_score(result),
                "recency": self._calculate_recency_score(
                    result, input_data.current_year
                ),
                "tier": self._calculate_tier_score(result),
                "source_type": self._calculate_source_type_score(result),
            }

            # 가중 합계
            final_score = sum(
                scores.get(factor, 0.0) * weights.get(factor, 0.0)
                for factor in scores
            )

            # 점수 설명 생성
            explanation = self._generate_explanation(scores, weights)

            ranked.append(RankedResult(
                result=result,
                final_score=round(final_score, 4),
                rank=0,  # 나중에 할당
                semantic_score=round(scores["semantic"], 4),
                evidence_score=round(scores["evidence"], 4),
                recency_score=round(scores["recency"], 4),
                tier_score=round(scores["tier"], 4),
                source_type_score=round(scores["source_type"], 4),
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

    def rank_with_preset(
        self,
        input_data: RankInput,
        preset: WeightPreset
    ) -> RankOutput:
        """프리셋을 사용하여 랭킹.

        Args:
            input_data: 랭킹 입력
            preset: 가중치 프리셋

        Returns:
            랭킹 결과
        """
        input_data.weights = self.WEIGHT_PRESETS.get(preset, self.DEFAULT_WEIGHTS)
        return self.rank(input_data)

    def _calculate_semantic_score(self, result: SearchResult) -> float:
        """의미적 유사도 점수.

        Args:
            result: 검색 결과

        Returns:
            의미 유사도 점수 (0.0~1.0)
        """
        # 벡터 검색 점수 그대로 사용 (이미 0~1 정규화됨)
        score = result.semantic_score

        # 그래프 점수가 있으면 결합
        if result.graph_score is not None:
            # 벡터 (1 - graph_weight) + 그래프 graph_weight
            vector_weight = 1.0 - self.graph_weight
            score = vector_weight * result.semantic_score + self.graph_weight * result.graph_score

        return min(1.0, max(0.0, score))

    def _calculate_evidence_score(self, result: SearchResult) -> float:
        """Evidence Level 점수.

        Args:
            result: 검색 결과

        Returns:
            Evidence Level 점수 (0.0~1.0)
        """
        # 직접 키 매칭 시도
        if result.evidence_level in self.EVIDENCE_SCORES:
            return self.EVIDENCE_SCORES[result.evidence_level]

        # 값 기반 매칭 시도 (다른 모듈에서 온 EvidenceLevel 처리)
        ev_value = result.evidence_level.value if hasattr(result.evidence_level, 'value') else str(result.evidence_level)
        for level, score in self.EVIDENCE_SCORES.items():
            if level.value == ev_value:
                return score

        return 0.2  # 기본값

    def _calculate_recency_score(
        self,
        result: SearchResult,
        current_year: int
    ) -> float:
        """최신성 점수 (지수 감쇠).

        Args:
            result: 검색 결과
            current_year: 현재 연도

        Returns:
            최신성 점수 (0.0~1.0)
        """
        age = current_year - result.publication_year

        if age <= 0:
            return 1.0

        # 지수 감쇠: half_life 년 후 점수 50%
        # score = 0.5 ^ (age / half_life)
        score = 0.5 ** (age / self.half_life)

        # 최소 점수 보장 (너무 오래되어도 0이 되지 않음)
        return max(score, 0.1)

    def _calculate_tier_score(self, result: SearchResult) -> float:
        """섹션 Tier 점수.

        Args:
            result: 검색 결과

        Returns:
            Tier 점수 (0.0~1.0)
        """
        return self.TIER_SCORES.get(result.tier, 0.7)

    def _calculate_source_type_score(self, result: SearchResult) -> float:
        """출처 유형 점수.

        Args:
            result: 검색 결과

        Returns:
            출처 유형 점수 (0.0~1.0)
        """
        # 직접 키 매칭 시도
        if result.source_type in self.SOURCE_SCORES:
            return self.SOURCE_SCORES[result.source_type]

        # 값 기반 매칭 시도 (다른 모듈에서 온 SourceType 처리)
        st_value = result.source_type.value if hasattr(result.source_type, 'value') else str(result.source_type)
        for source, score in self.SOURCE_SCORES.items():
            if source.value == st_value:
                return score

        return 0.5  # 기본값

    def _generate_explanation(
        self,
        scores: dict,
        weights: dict
    ) -> dict:
        """점수 설명 생성.

        Args:
            scores: 요소별 점수
            weights: 가중치

        Returns:
            설명 딕셔너리
        """
        explanation = {}

        for factor, score in scores.items():
            weight = weights.get(factor, 0.0)
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

    def _count_source_types(self, ranked: list[RankedResult]) -> dict:
        """출처 유형 분포 계산.

        Args:
            ranked: 랭킹된 결과

        Returns:
            출처 유형별 개수
        """
        distribution = {}
        for r in ranked:
            source = r.result.source_type.value
            distribution[source] = distribution.get(source, 0) + 1
        return distribution

    def _count_tiers(self, ranked: list[RankedResult]) -> dict:
        """Tier 분포 계산.

        Args:
            ranked: 랭킹된 결과

        Returns:
            Tier별 개수
        """
        distribution = {}
        for r in ranked:
            tier = r.result.tier
            distribution[tier] = distribution.get(tier, 0) + 1
        return distribution

    def get_available_presets(self) -> list[str]:
        """사용 가능한 프리셋 목록 반환.

        Returns:
            프리셋 이름 목록
        """
        return [p.value for p in WeightPreset]

    def get_preset_weights(self, preset: WeightPreset) -> dict:
        """프리셋의 가중치 반환.

        Args:
            preset: 프리셋

        Returns:
            가중치 딕셔너리
        """
        return self.WEIGHT_PRESETS.get(preset, self.DEFAULT_WEIGHTS).copy()


def create_ranker_from_config(config_path: str) -> MultiFactorRanker:
    """설정 파일에서 랭커 생성.

    Args:
        config_path: 설정 파일 경로

    Returns:
        MultiFactorRanker 인스턴스
    """
    import yaml

    with open(config_path, 'r') as f:
        full_config = yaml.safe_load(f)

    ranker_config = full_config.get("multi_factor_ranker", {})
    return MultiFactorRanker(ranker_config)
