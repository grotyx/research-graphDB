"""Tests for Reasoner module."""

import pytest
from src.solver.reasoner import (
    Reasoner,
    ReasonerInput,
    ReasoningResult,
    ReasoningType,
    ConfidenceLevel,
    Evidence,
    ReasoningStep,
    create_reasoning_summary,
)


def make_mock_evidence(count: int = 5) -> list[dict]:
    """테스트용 Mock 검색 결과 생성."""
    results = [
        {
            "text": "Minimally invasive surgery shows better outcomes for lumbar disc herniation.",
            "document_id": "doc_1",
            "title": "RCT of Spine Surgery",
            "evidence_level": "1b",
            "source_type": "original",
            "score": 0.95,
            "chunk_id": "chunk_1",
            "section": "results",
            "publication_year": 2023
        },
        {
            "text": "Open surgery has higher complication rates compared to minimally invasive approaches.",
            "document_id": "doc_2",
            "title": "Comparative Analysis",
            "evidence_level": "2a",
            "source_type": "original",
            "score": 0.88,
            "chunk_id": "chunk_2",
            "section": "conclusion",
            "publication_year": 2022
        },
        {
            "text": "Previous studies reported similar findings (Smith et al., 2020).",
            "document_id": "doc_3",
            "title": "Cohort Study Review",
            "evidence_level": "2b",
            "source_type": "citation",
            "score": 0.75,
            "chunk_id": "chunk_3",
            "section": "discussion",
            "publication_year": 2021
        },
        {
            "text": "Case series of 50 patients showed improvement in pain scores.",
            "document_id": "doc_4",
            "title": "Case Series Report",
            "evidence_level": "4",
            "source_type": "original",
            "score": 0.70,
            "chunk_id": "chunk_4",
            "section": "results",
            "publication_year": 2022
        },
        {
            "text": "Expert opinion suggests conservative treatment first.",
            "document_id": "doc_5",
            "title": "Expert Commentary",
            "evidence_level": "5",
            "source_type": "background",
            "score": 0.60,
            "chunk_id": "chunk_5",
            "section": "discussion",
            "publication_year": 2019
        },
    ]
    return results[:count]


class TestReasonerBasic:
    """Reasoner 기본 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_empty_results(self, reasoner):
        """빈 결과 처리."""
        result = reasoner.reason("test query", [])

        assert result.confidence == 0.0
        assert result.confidence_level == ConfidenceLevel.UNCERTAIN
        assert len(result.evidence) == 0
        assert "No evidence" in result.answer

    def test_string_input(self, reasoner):
        """문자열 입력."""
        results = make_mock_evidence(3)
        result = reasoner.reason("spine surgery outcomes", results)

        assert result.answer != ""
        assert len(result.evidence) == 3

    def test_reasoner_input_object(self, reasoner):
        """ReasonerInput 객체 입력."""
        results = make_mock_evidence(3)
        input_obj = ReasonerInput(
            query="spine surgery outcomes",
            search_results=results,
            max_hops=3
        )
        result = reasoner.reason(input_obj)

        assert result.answer != ""
        assert len(result.evidence) == 3


class TestReasoningTypes:
    """추론 유형 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    @pytest.fixture
    def mock_evidence(self):
        return make_mock_evidence(5)

    def test_comparison_type(self, reasoner, mock_evidence):
        """비교 추론 유형."""
        result = reasoner.reason("minimally invasive vs open surgery", mock_evidence)
        assert result.reasoning_type == ReasoningType.COMPARISON

    def test_causal_type(self, reasoner, mock_evidence):
        """인과관계 추론 유형."""
        result = reasoner.reason("what causes back pain", mock_evidence)
        assert result.reasoning_type == ReasoningType.CAUSAL

    def test_synthesis_type(self, reasoner, mock_evidence):
        """종합 추론 유형 (다중 근거)."""
        result = reasoner.reason("spine surgery outcomes", mock_evidence)
        # 5개 근거 → SYNTHESIS
        assert result.reasoning_type == ReasoningType.SYNTHESIS

    def test_direct_type(self, reasoner):
        """직접 추론 유형 (단일 근거)."""
        single_evidence = make_mock_evidence(1)
        result = reasoner.reason("spine surgery", single_evidence)
        assert result.reasoning_type == ReasoningType.DIRECT


class TestConfidenceCalculation:
    """신뢰도 계산 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_high_confidence_with_quality_evidence(self, reasoner):
        """고품질 근거로 높은 신뢰도."""
        high_quality = [
            {
                "text": "RCT shows clear benefit.",
                "document_id": "doc_1",
                "title": "RCT Study",
                "evidence_level": "1b",
                "source_type": "original",
                "score": 0.95,
                "publication_year": 2023
            },
            {
                "text": "Meta-analysis confirms findings.",
                "document_id": "doc_2",
                "title": "Meta-analysis",
                "evidence_level": "1a",
                "source_type": "original",
                "score": 0.92,
                "publication_year": 2023
            },
            {
                "text": "Another RCT with similar results.",
                "document_id": "doc_3",
                "title": "RCT Study 2",
                "evidence_level": "1b",
                "source_type": "original",
                "score": 0.90,
                "publication_year": 2022
            },
        ]

        result = reasoner.reason("treatment effectiveness", high_quality)

        # High quality evidence should give higher confidence
        assert result.confidence >= 0.6
        assert result.confidence_level in [ConfidenceLevel.HIGH, ConfidenceLevel.MODERATE]

    def test_low_confidence_with_weak_evidence(self, reasoner):
        """저품질 근거로 낮은 신뢰도."""
        low_quality = [
            {
                "text": "Expert opinion suggests...",
                "document_id": "doc_1",
                "title": "Expert Commentary",
                "evidence_level": "5",
                "source_type": "background",
                "score": 0.50,
                "publication_year": 2015
            },
        ]

        result = reasoner.reason("treatment options", low_quality)

        # Low quality evidence should give lower confidence
        assert result.confidence <= 0.5
        assert result.confidence_level in [ConfidenceLevel.LOW, ConfidenceLevel.UNCERTAIN]

    def test_confidence_levels(self, reasoner):
        """신뢰도 수준 경계."""
        # Test confidence level boundaries
        assert reasoner._get_confidence_level(0.9) == ConfidenceLevel.HIGH
        assert reasoner._get_confidence_level(0.8) == ConfidenceLevel.HIGH
        assert reasoner._get_confidence_level(0.7) == ConfidenceLevel.MODERATE
        assert reasoner._get_confidence_level(0.6) == ConfidenceLevel.MODERATE
        assert reasoner._get_confidence_level(0.5) == ConfidenceLevel.LOW
        assert reasoner._get_confidence_level(0.3) == ConfidenceLevel.UNCERTAIN


class TestReasoningSteps:
    """추론 단계 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_reasoning_steps_created(self, reasoner):
        """추론 단계 생성."""
        evidence = make_mock_evidence(5)
        result = reasoner.reason("spine surgery", evidence)

        assert len(result.reasoning_path) > 0
        assert all(isinstance(step, ReasoningStep) for step in result.reasoning_path)

    def test_max_hops_respected(self, reasoner):
        """최대 홉 수 준수."""
        evidence = make_mock_evidence(5)

        # Max 2 hops
        input_obj = ReasonerInput(
            query="spine surgery",
            search_results=evidence,
            max_hops=2
        )
        result = reasoner.reason(input_obj)

        assert len(result.reasoning_path) <= 2

    def test_step_has_evidence(self, reasoner):
        """각 단계에 근거 포함."""
        evidence = make_mock_evidence(5)
        result = reasoner.reason("spine surgery", evidence)

        # First step should have evidence
        first_step = result.reasoning_path[0]
        assert first_step.step_number == 1
        assert len(first_step.evidence_used) > 0


class TestEvidenceExtraction:
    """근거 추출 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_extract_from_dict(self, reasoner):
        """딕셔너리에서 근거 추출."""
        dict_results = make_mock_evidence(3)
        result = reasoner.reason("test", dict_results)

        assert len(result.evidence) == 3
        assert all(isinstance(e, Evidence) for e in result.evidence)

    def test_evidence_fields(self, reasoner):
        """근거 필드 확인."""
        dict_results = make_mock_evidence(1)
        result = reasoner.reason("test", dict_results)

        evidence = result.evidence[0]
        assert evidence.content != ""
        assert evidence.source_id != ""
        assert evidence.evidence_level != ""
        assert evidence.source_type != ""

    def test_evidence_levels_preserved(self, reasoner):
        """근거 수준 보존."""
        dict_results = make_mock_evidence(5)
        result = reasoner.reason("test", dict_results)

        evidence_levels = [e.evidence_level for e in result.evidence]
        assert "1b" in evidence_levels
        assert "2a" in evidence_levels


class TestExplanationGeneration:
    """설명 생성 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_explanation_included(self, reasoner):
        """설명 포함."""
        evidence = make_mock_evidence(3)
        input_obj = ReasonerInput(
            query="spine surgery",
            search_results=evidence,
            include_explanation=True
        )
        result = reasoner.reason(input_obj)

        assert result.explanation != ""
        assert "evidence" in result.explanation.lower()

    def test_no_explanation(self, reasoner):
        """설명 제외."""
        evidence = make_mock_evidence(3)
        input_obj = ReasonerInput(
            query="spine surgery",
            search_results=evidence,
            include_explanation=False
        )
        result = reasoner.reason(input_obj)

        assert result.explanation == ""


class TestAnswerGeneration:
    """답변 생성 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_answer_generated(self, reasoner):
        """답변 생성."""
        evidence = make_mock_evidence(3)
        result = reasoner.reason("spine surgery outcomes", evidence)

        assert result.answer != ""
        assert len(result.answer) > 20

    def test_answer_includes_evidence_count(self, reasoner):
        """답변에 근거 수 포함."""
        evidence = make_mock_evidence(5)
        result = reasoner.reason("spine surgery", evidence)

        # Answer should mention evidence count
        assert "5 sources" in result.answer or "5" in result.answer


class TestEvidenceWeighting:
    """근거 가중치 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_evidence_hierarchy(self, reasoner):
        """근거 수준 계층."""
        hierarchy = reasoner.EVIDENCE_HIERARCHY
        assert hierarchy.index("1a") < hierarchy.index("2a")
        assert hierarchy.index("2a") < hierarchy.index("3a")
        assert hierarchy.index("3a") < hierarchy.index("4")

    def test_evidence_weights(self, reasoner):
        """근거 가중치."""
        weights = reasoner.EVIDENCE_WEIGHTS
        assert weights["1a"] > weights["2a"]
        assert weights["2a"] > weights["3a"]
        assert weights["3a"] > weights["4"]
        assert weights["4"] > weights["5"]

    def test_source_weights(self, reasoner):
        """출처 가중치."""
        weights = reasoner.SOURCE_WEIGHTS
        assert weights["original"] > weights["citation"]
        assert weights["citation"] > weights["background"]


class TestConfiguration:
    """설정 테스트."""

    def test_default_config(self):
        """기본 설정."""
        reasoner = Reasoner()
        assert reasoner.min_evidence_for_high == 3
        assert reasoner.recency_bonus == 0.05

    def test_custom_config(self):
        """커스텀 설정."""
        config = {
            "min_evidence_for_high": 5,
            "recency_bonus": 0.1,
            "current_year": 2025
        }
        reasoner = Reasoner(config=config)

        assert reasoner.min_evidence_for_high == 5
        assert reasoner.recency_bonus == 0.1
        assert reasoner.current_year == 2025


class TestCreateReasoningSummary:
    """요약 생성 테스트."""

    def test_summary_format(self):
        """요약 형식."""
        result = ReasoningResult(
            answer="Test answer for spine surgery outcomes.",
            evidence=[
                Evidence(
                    content="Test content",
                    source_id="doc_1",
                    source_title="Test Title",
                    evidence_level="1b",
                    source_type="original",
                    relevance_score=0.9
                )
            ],
            confidence=0.85,
            confidence_level=ConfidenceLevel.HIGH,
            explanation="Test explanation",
            reasoning_path=[
                ReasoningStep(
                    step_number=1,
                    description="Test step",
                    evidence_used=[],
                    intermediate_conclusion="Test conclusion",
                    confidence=0.8
                )
            ],
            reasoning_type=ReasoningType.SYNTHESIS,
            supporting_count=1,
            contradicting_count=0
        )

        summary = create_reasoning_summary(result)

        assert "Answer:" in summary
        assert "Confidence:" in summary
        assert "0.85" in summary
        assert "high" in summary.lower()
        assert "Evidence:" in summary
        assert "1 sources" in summary


class TestEdgeCases:
    """Edge case 테스트."""

    @pytest.fixture
    def reasoner(self):
        return Reasoner()

    def test_single_evidence(self, reasoner):
        """단일 근거."""
        single = make_mock_evidence(1)
        result = reasoner.reason("test", single)

        assert len(result.evidence) == 1
        assert result.reasoning_type == ReasoningType.DIRECT

    def test_many_evidence(self, reasoner):
        """다수 근거."""
        many = make_mock_evidence(5) * 3  # 15개
        result = reasoner.reason("test", many)

        assert len(result.evidence) == 15
        assert result.reasoning_type == ReasoningType.SYNTHESIS

    def test_very_long_query(self, reasoner):
        """긴 쿼리."""
        evidence = make_mock_evidence(3)
        long_query = "what is the best treatment for " * 10
        result = reasoner.reason(long_query, evidence)

        assert result.answer != ""

    def test_special_characters_in_query(self, reasoner):
        """특수문자 쿼리."""
        evidence = make_mock_evidence(3)
        result = reasoner.reason("spine surgery? (minimally invasive)", evidence)

        assert result.answer != ""
