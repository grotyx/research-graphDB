"""Tests for MultiFactorRanker module."""

import pytest
from src.solver.multi_factor_ranker import (
    MultiFactorRanker,
    SearchResult,
    RankInput,
    RankOutput,
    RankedResult,
    WeightPreset,
)
from src.builder.citation_detector import SourceType
from src.builder.study_classifier import EvidenceLevel


def make_result(
    chunk_id: str,
    semantic: float = 0.8,
    evidence: EvidenceLevel = EvidenceLevel.LEVEL_2B,
    year: int = 2020,
    tier: int = 1,
    source_type: SourceType = SourceType.ORIGINAL,
    section: str = "results",
    graph_score: float | None = None,
) -> SearchResult:
    """테스트용 SearchResult 생성 헬퍼."""
    return SearchResult(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"Sample text for {chunk_id}",
        semantic_score=semantic,
        graph_score=graph_score,
        tier=tier,
        section=section,
        source_type=source_type,
        evidence_level=evidence,
        publication_year=year,
    )


class TestMultiFactorRanker:
    """MultiFactorRanker 테스트."""

    @pytest.fixture
    def ranker(self):
        """기본 랭커 fixture."""
        return MultiFactorRanker()

    def test_empty_results(self, ranker):
        """빈 결과 처리."""
        output = ranker.rank(RankInput(results=[], query="test"))

        assert output.total_results == 0
        assert output.ranked_results == []
        assert output.top_evidence_levels == []

    def test_single_result(self, ranker):
        """단일 결과 처리."""
        results = [make_result("A")]

        output = ranker.rank(RankInput(results=results, query="test"))

        assert output.total_results == 1
        assert output.ranked_results[0].rank == 1
        assert output.ranked_results[0].result.chunk_id == "A"

    def test_rank_by_evidence_level(self, ranker):
        """Evidence Level이 높은 결과가 상위에 랭킹."""
        results = [
            make_result("A", semantic=0.9, evidence=EvidenceLevel.LEVEL_4),
            make_result("B", semantic=0.9, evidence=EvidenceLevel.LEVEL_1B),
            make_result("C", semantic=0.9, evidence=EvidenceLevel.LEVEL_2A),
        ]

        # Evidence만 고려하도록 가중치 설정
        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={
                "semantic": 0.3,
                "evidence": 0.7,
                "recency": 0,
                "tier": 0,
                "source_type": 0
            }
        ))

        # Evidence Level 순서: 1b > 2a > 4
        assert output.ranked_results[0].result.chunk_id == "B"  # Level 1b
        assert output.ranked_results[1].result.chunk_id == "C"  # Level 2a
        assert output.ranked_results[2].result.chunk_id == "A"  # Level 4

    def test_rank_by_recency(self, ranker):
        """최신 논문이 상위에 랭킹."""
        results = [
            make_result("old", year=2015),
            make_result("recent", year=2023),
            make_result("mid", year=2019),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            current_year=2024,
            weights={
                "semantic": 0,
                "evidence": 0,
                "recency": 1,
                "tier": 0,
                "source_type": 0
            }
        ))

        assert output.ranked_results[0].result.chunk_id == "recent"
        assert output.ranked_results[2].result.chunk_id == "old"

    def test_rank_original_over_citation(self, ranker):
        """원본 콘텐츠가 인용보다 상위에 랭킹."""
        results = [
            make_result("citation", source_type=SourceType.CITATION),
            make_result("original", source_type=SourceType.ORIGINAL),
            make_result("background", source_type=SourceType.BACKGROUND),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={
                "semantic": 0,
                "evidence": 0,
                "recency": 0,
                "tier": 0,
                "source_type": 1
            }
        ))

        assert output.ranked_results[0].result.chunk_id == "original"
        assert output.ranked_results[2].result.chunk_id == "background"

    def test_rank_tier1_over_tier2(self, ranker):
        """Tier 1 (핵심)이 Tier 2보다 상위에 랭킹."""
        results = [
            make_result("methods", tier=2, section="methods"),
            make_result("results", tier=1, section="results"),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={
                "semantic": 0,
                "evidence": 0,
                "recency": 0,
                "tier": 1,
                "source_type": 0
            }
        ))

        assert output.ranked_results[0].result.chunk_id == "results"

    def test_combined_ranking(self, ranker):
        """복합 랭킹 (모든 요소 조합)."""
        results = [
            # 최신 + 높은 근거 + 원본
            make_result(
                "best",
                semantic=0.8,
                evidence=EvidenceLevel.LEVEL_1B,
                year=2023,
                tier=1,
                source_type=SourceType.ORIGINAL
            ),
            # 오래됨 + 낮은 근거 + 인용
            make_result(
                "worst",
                semantic=0.9,
                evidence=EvidenceLevel.LEVEL_4,
                year=2010,
                tier=2,
                source_type=SourceType.CITATION
            ),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            current_year=2024
        ))

        # semantic 점수가 낮아도 다른 요소가 좋으면 상위
        assert output.ranked_results[0].result.chunk_id == "best"

    def test_score_explanation(self, ranker):
        """점수 설명이 포함되는지 확인."""
        results = [make_result("A")]

        output = ranker.rank(RankInput(results=results, query="test"))

        explanation = output.ranked_results[0].score_explanation
        assert "semantic" in explanation
        assert "evidence" in explanation
        assert "recency" in explanation
        assert "tier" in explanation
        assert "source_type" in explanation

    def test_custom_weights(self, ranker):
        """커스텀 가중치 적용."""
        results = [make_result("A", semantic=0.5)]

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

        # semantic만 고려되므로 final_score == semantic_score
        assert output.ranked_results[0].final_score == output.ranked_results[0].semantic_score

    def test_weight_normalization(self, ranker):
        """가중치 합이 1.0이 아닌 경우 정규화."""
        results = [make_result("A", semantic=1.0)]

        # 합이 2.0인 가중치
        custom_weights = {
            "semantic": 0.6,
            "evidence": 0.5,
            "recency": 0.3,
            "tier": 0.3,
            "source_type": 0.3,
        }

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights=custom_weights
        ))

        # 정규화 후 점수가 계산되어야 함
        assert 0 <= output.ranked_results[0].final_score <= 1.0

    def test_graph_score_combination(self, ranker):
        """그래프 점수가 있을 때 결합."""
        results = [
            make_result("with_graph", semantic=0.6, graph_score=1.0),
            make_result("without_graph", semantic=0.8, graph_score=None),
        ]

        output = ranker.rank(RankInput(
            results=results,
            query="test",
            weights={
                "semantic": 1.0,
                "evidence": 0,
                "recency": 0,
                "tier": 0,
                "source_type": 0
            }
        ))

        # with_graph: 0.7 * 0.6 + 0.3 * 1.0 = 0.72
        # without_graph: 0.8
        assert output.ranked_results[0].result.chunk_id == "without_graph"

    def test_recency_decay(self, ranker):
        """최신성 지수 감쇠 확인."""
        # 현재 연도 = 2024, half_life = 5
        result_recent = make_result("recent", year=2024)
        result_old = make_result("old", year=2019)  # 5년 전

        recent_score = ranker._calculate_recency_score(result_recent, 2024)
        old_score = ranker._calculate_recency_score(result_old, 2024)

        # 현재 연도는 1.0
        assert recent_score == 1.0
        # 5년 전은 약 0.5 (half_life = 5)
        assert 0.45 <= old_score <= 0.55

    def test_recency_minimum_score(self, ranker):
        """매우 오래된 논문도 최소 점수 보장."""
        result_ancient = make_result("ancient", year=1990)

        score = ranker._calculate_recency_score(result_ancient, 2024)

        # 최소 점수 0.1 보장
        assert score >= 0.1

    def test_statistics_distribution(self, ranker):
        """통계 분포 계산."""
        results = [
            make_result("A", tier=1, source_type=SourceType.ORIGINAL),
            make_result("B", tier=1, source_type=SourceType.ORIGINAL),
            make_result("C", tier=2, source_type=SourceType.CITATION),
        ]

        output = ranker.rank(RankInput(results=results, query="test"))

        assert output.tier_distribution == {1: 2, 2: 1}
        assert output.source_type_distribution == {"original": 2, "citation": 1}

    def test_top_evidence_levels(self, ranker):
        """상위 결과의 Evidence Level 추적."""
        results = [
            make_result("A", evidence=EvidenceLevel.LEVEL_1A),
            make_result("B", evidence=EvidenceLevel.LEVEL_2B),
            make_result("C", evidence=EvidenceLevel.LEVEL_4),
        ]

        output = ranker.rank(RankInput(results=results, query="test"))

        assert len(output.top_evidence_levels) <= 10
        assert EvidenceLevel.LEVEL_1A in output.top_evidence_levels


class TestWeightPresets:
    """가중치 프리셋 테스트."""

    def test_available_presets(self):
        """사용 가능한 프리셋 목록."""
        ranker = MultiFactorRanker()
        presets = ranker.get_available_presets()

        assert "balanced" in presets
        assert "recent_research" in presets
        assert "high_evidence" in presets
        assert "original_only" in presets
        assert "core_content" in presets

    def test_preset_weights_sum_to_one(self):
        """각 프리셋의 가중치 합이 1.0."""
        ranker = MultiFactorRanker()

        for preset in WeightPreset:
            weights = ranker.get_preset_weights(preset)
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"{preset.value} weights sum to {total}"

    def test_high_evidence_preset(self):
        """HIGH_EVIDENCE 프리셋: Evidence가 가장 높은 가중치."""
        ranker = MultiFactorRanker()
        weights = ranker.get_preset_weights(WeightPreset.HIGH_EVIDENCE)

        assert weights["evidence"] == max(weights.values())

    def test_recent_research_preset(self):
        """RECENT_RESEARCH 프리셋: Recency가 가장 높은 가중치."""
        ranker = MultiFactorRanker()
        weights = ranker.get_preset_weights(WeightPreset.RECENT_RESEARCH)

        assert weights["recency"] == max(weights.values())

    def test_original_only_preset(self):
        """ORIGINAL_ONLY 프리셋: Source type 가중치 높음."""
        ranker = MultiFactorRanker()
        weights = ranker.get_preset_weights(WeightPreset.ORIGINAL_ONLY)

        assert weights["source_type"] >= 0.25

    def test_rank_with_preset(self):
        """프리셋을 사용한 랭킹."""
        ranker = MultiFactorRanker()
        results = [
            make_result("recent", year=2023, evidence=EvidenceLevel.LEVEL_4),
            make_result("quality", year=2018, evidence=EvidenceLevel.LEVEL_1A),
        ]

        # RECENT_RESEARCH 프리셋으로 랭킹
        output = ranker.rank_with_preset(
            RankInput(results=results, query="test", current_year=2024),
            WeightPreset.RECENT_RESEARCH
        )

        # 최신성이 높으면 recent가 상위
        assert output.ranked_results[0].result.chunk_id == "recent"

        # HIGH_EVIDENCE 프리셋으로 랭킹
        output = ranker.rank_with_preset(
            RankInput(results=results, query="test", current_year=2024),
            WeightPreset.HIGH_EVIDENCE
        )

        # Evidence가 높으면 quality가 상위
        assert output.ranked_results[0].result.chunk_id == "quality"


class TestMultiFactorRankerConfig:
    """설정 기반 테스트."""

    def test_config_preset(self):
        """설정에서 프리셋 적용."""
        ranker = MultiFactorRanker(config={"preset": "high_evidence"})

        assert ranker.weights["evidence"] == max(ranker.weights.values())

    def test_config_custom_weights(self):
        """설정에서 커스텀 가중치 적용."""
        custom_weights = {
            "semantic": 0.5,
            "evidence": 0.5,
            "recency": 0,
            "tier": 0,
            "source_type": 0,
        }

        ranker = MultiFactorRanker(config={"weights": custom_weights})

        assert ranker.weights["semantic"] == 0.5
        assert ranker.weights["evidence"] == 0.5

    def test_config_half_life(self):
        """설정에서 half_life 적용."""
        ranker = MultiFactorRanker(config={"half_life_years": 10.0})

        assert ranker.half_life == 10.0

    def test_config_graph_weight(self):
        """설정에서 graph_weight 적용."""
        ranker = MultiFactorRanker(config={"graph_weight": 0.5})

        assert ranker.graph_weight == 0.5


class TestEdgeCases:
    """Edge case 테스트."""

    def test_future_publication_year(self):
        """미래 출판 연도 처리."""
        ranker = MultiFactorRanker()
        result = make_result("future", year=2030)

        score = ranker._calculate_recency_score(result, 2024)

        # 미래 연도는 1.0
        assert score == 1.0

    def test_unknown_evidence_level(self):
        """알 수 없는 Evidence Level 처리."""
        ranker = MultiFactorRanker()

        # Evidence Level이 없는 경우 기본값 사용
        score = ranker.EVIDENCE_SCORES.get(EvidenceLevel.LEVEL_5, 0.2)
        assert score == 0.2

    def test_all_same_scores(self):
        """모든 점수가 동일한 경우."""
        ranker = MultiFactorRanker()
        results = [
            make_result("A", semantic=0.8),
            make_result("B", semantic=0.8),
            make_result("C", semantic=0.8),
        ]

        output = ranker.rank(RankInput(results=results, query="test"))

        # 모두 동일 점수면 순서대로 랭킹
        assert output.total_results == 3
        assert all(r.rank in [1, 2, 3] for r in output.ranked_results)

    def test_semantic_score_bounds(self):
        """Semantic score 범위 확인."""
        ranker = MultiFactorRanker()

        # 범위 밖의 값도 처리
        result = make_result("over", semantic=1.5)
        score = ranker._calculate_semantic_score(result)
        assert 0 <= score <= 1.0

        result = make_result("under", semantic=-0.5)
        score = ranker._calculate_semantic_score(result)
        assert 0 <= score <= 1.0
