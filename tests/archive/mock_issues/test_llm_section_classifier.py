"""LLM Section Classifier 테스트."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.builder.llm_section_classifier import (
    LLMSectionClassifier,
    SectionBoundary,
    SECTION_TIERS,
    ClassificationError
)
from src.builder.section_classifier import SectionClassifier
from src.llm.gemini_client import GeminiClient, GeminiConfig


class TestSectionBoundary:
    """SectionBoundary 테스트."""

    def test_creation(self):
        """기본 생성 테스트."""
        boundary = SectionBoundary(
            section_type="abstract",
            start_char=0,
            end_char=500,
            confidence=0.95,
            tier=1
        )
        assert boundary.section_type == "abstract"
        assert boundary.start_char == 0
        assert boundary.end_char == 500
        assert boundary.confidence == 0.95
        assert boundary.tier == 1

    def test_optional_heading(self):
        """선택적 헤딩 테스트."""
        boundary = SectionBoundary(
            section_type="methods",
            start_char=500,
            end_char=1000,
            confidence=0.9,
            tier=2,
            heading="Materials and Methods"
        )
        assert boundary.heading == "Materials and Methods"


class TestSectionTiers:
    """Tier 매핑 테스트."""

    def test_tier1_sections(self):
        """Tier 1 섹션 확인."""
        assert SECTION_TIERS["abstract"] == 1
        assert SECTION_TIERS["results"] == 1
        assert SECTION_TIERS["conclusion"] == 1

    def test_tier2_sections(self):
        """Tier 2 섹션 확인."""
        assert SECTION_TIERS["introduction"] == 2
        assert SECTION_TIERS["methods"] == 2
        assert SECTION_TIERS["discussion"] == 2
        assert SECTION_TIERS["references"] == 2


class TestLLMSectionClassifier:
    """LLMSectionClassifier 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.fixture
    def classifier(self, mock_gemini_client):
        """테스트용 분류기."""
        return LLMSectionClassifier(
            gemini_client=mock_gemini_client,
            fallback_classifier=SectionClassifier()
        )

    @pytest.mark.asyncio
    async def test_classify_standard_paper(self, classifier, mock_gemini_client):
        """표준 구조 논문 분류."""
        text = """Abstract
This study investigates the effects of treatment X on condition Y.

Introduction
Background information about the topic...

Methods
We conducted a randomized controlled trial...

Results
The primary outcome showed significant improvement...

Discussion
Our findings suggest that treatment X is effective...

Conclusion
In summary, we found that treatment X provides benefits...

References
1. Smith et al. (2020)
2. Jones et al. (2021)
"""
        mock_gemini_client.generate_json.return_value = {
            "sections": [
                {"section_type": "abstract", "start_char": 0, "end_char": 80, "confidence": 0.95},
                {"section_type": "introduction", "start_char": 80, "end_char": 140, "confidence": 0.90},
                {"section_type": "methods", "start_char": 140, "end_char": 200, "confidence": 0.92},
                {"section_type": "results", "start_char": 200, "end_char": 280, "confidence": 0.93},
                {"section_type": "discussion", "start_char": 280, "end_char": 360, "confidence": 0.88},
                {"section_type": "conclusion", "start_char": 360, "end_char": 440, "confidence": 0.91},
                {"section_type": "references", "start_char": 440, "end_char": len(text), "confidence": 0.95}
            ]
        }

        sections = await classifier.classify(text)

        assert len(sections) >= 1
        # 첫 섹션은 abstract이어야 함
        assert sections[0].section_type == "abstract"
        assert sections[0].tier == 1

    @pytest.mark.asyncio
    async def test_classify_empty_text(self, classifier):
        """빈 텍스트 처리."""
        sections = await classifier.classify("")
        assert len(sections) == 0

    @pytest.mark.asyncio
    async def test_classify_whitespace_only(self, classifier):
        """공백만 있는 텍스트 처리."""
        sections = await classifier.classify("   \n\n   ")
        assert len(sections) == 0

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, classifier, mock_gemini_client):
        """LLM 실패 시 Fallback."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        text = """Abstract
This is a test abstract.

Methods
These are the methods used.

Results
These are the results.
"""
        sections = await classifier.classify(text, use_fallback=True)

        # Fallback 결과 확인
        assert len(sections) >= 1

    @pytest.mark.asyncio
    async def test_no_fallback_returns_other(self, classifier, mock_gemini_client):
        """Fallback 없이 실패 시 'other' 반환."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        text = "Some random text without clear sections."
        sections = await classifier.classify(text, use_fallback=False)

        assert len(sections) == 1
        assert sections[0].section_type == "other"

    def test_validate_sections_overlap(self, classifier):
        """겹치는 섹션 보정."""
        sections = [
            SectionBoundary("abstract", 0, 150, 0.9, 1),
            SectionBoundary("methods", 100, 300, 0.8, 2),  # 겹침
        ]
        validated = classifier.validate_sections(sections, 300)

        # 겹침 해결됨
        assert validated[0].end_char <= validated[1].start_char

    def test_validate_sections_fills_gaps(self, classifier):
        """빈 영역 채우기."""
        sections = [
            SectionBoundary("abstract", 100, 200, 0.9, 1),  # 앞에 빈 영역
        ]
        validated = classifier.validate_sections(sections, 300)

        # 앞쪽 빈 영역이 채워짐
        assert validated[0].start_char == 0
        # 뒤쪽 빈 영역도 채워짐
        assert validated[-1].end_char == 300

    def test_validate_sections_merges_short(self, classifier):
        """짧은 섹션 병합."""
        sections = [
            SectionBoundary("abstract", 0, 200, 0.9, 1),
            SectionBoundary("methods", 200, 250, 0.8, 2),  # 50자, 너무 짧음
            SectionBoundary("results", 250, 500, 0.85, 1),
        ]
        validated = classifier.validate_sections(sections, 500)

        # 짧은 섹션이 병합됨
        assert len(validated) < 3

    def test_is_valid_result_empty(self, classifier):
        """빈 결과 검증."""
        assert classifier._is_valid_result([], 100) is False

    def test_is_valid_result_low_coverage(self, classifier):
        """낮은 커버리지 검증."""
        sections = [
            SectionBoundary("abstract", 0, 50, 0.9, 1),  # 50% 미만 커버리지
        ]
        assert classifier._is_valid_result(sections, 200) is False

    def test_is_valid_result_valid(self, classifier):
        """유효한 결과 검증."""
        sections = [
            SectionBoundary("abstract", 0, 100, 0.9, 1),
            SectionBoundary("methods", 100, 200, 0.85, 2),
        ]
        assert classifier._is_valid_result(sections, 200) is True

    def test_estimate_boundaries(self, classifier):
        """경계 추정 테스트."""
        text = """Abstract
Content here...

Methods
More content...

Results
Final content...
"""
        boundaries = classifier._estimate_boundaries(text)

        # 시작(0)과 끝이 포함되어야 함
        assert 0 in boundaries
        assert len(text) in boundaries
        # 최소 2개 이상의 경계
        assert len(boundaries) >= 2

    def test_split_into_paragraphs(self, classifier):
        """단락 분할 테스트."""
        text = """First paragraph content.

Second paragraph content.

Third paragraph content."""

        paragraphs = classifier._split_into_paragraphs(text)

        assert len(paragraphs) == 3
        assert paragraphs[0]["text"] == "First paragraph content."
        assert paragraphs[1]["text"] == "Second paragraph content."

    @pytest.mark.asyncio
    async def test_tier_assignment(self, classifier, mock_gemini_client):
        """Tier 올바르게 할당."""
        mock_gemini_client.generate_json.return_value = {
            "sections": [
                {"section_type": "abstract", "start_char": 0, "end_char": 100, "confidence": 0.9},
                {"section_type": "results", "start_char": 100, "end_char": 200, "confidence": 0.9},
                {"section_type": "discussion", "start_char": 200, "end_char": 300, "confidence": 0.9},
            ]
        }

        text = "A" * 300
        sections = await classifier.classify(text)

        for s in sections:
            expected_tier = SECTION_TIERS.get(s.section_type, 2)
            assert s.tier == expected_tier


class TestLLMSectionClassifierIntegration:
    """통합 테스트 (실제 API 없이)."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_full_paper_classification(self, mock_gemini_client):
        """전체 논문 분류 흐름."""
        classifier = LLMSectionClassifier(
            gemini_client=mock_gemini_client
        )

        paper_text = """ABSTRACT
Background: Type 2 diabetes is a major health concern.
Methods: We conducted a systematic review.
Results: We found 50 relevant studies.
Conclusion: Early intervention is key.

INTRODUCTION
Diabetes affects millions worldwide. The prevalence has been increasing
steadily over the past decades. This systematic review aims to...

METHODS
Search Strategy: We searched PubMed, MEDLINE, and Cochrane.
Inclusion criteria: RCTs published between 2010-2023.
Data extraction: Two reviewers independently extracted data.

RESULTS
Study Selection: Of 500 identified studies, 50 met inclusion criteria.
Primary Outcome: The pooled effect size was 0.45 (95% CI: 0.30-0.60).
Secondary Outcomes: Quality of life improved significantly.

DISCUSSION
Our findings suggest that intervention X is effective for type 2 diabetes.
This is consistent with previous meta-analyses. However, heterogeneity
was high, suggesting the need for further research.

Limitations: We only included English language publications.
Strengths: Comprehensive search strategy and robust methodology.

CONCLUSION
In conclusion, intervention X shows promise for diabetes management.
Further research is needed to optimize treatment protocols.

REFERENCES
1. Smith J, et al. Diabetes Care. 2020;43(1):100-110.
2. Johnson A, et al. Lancet. 2021;398:500-510.
"""

        mock_gemini_client.generate_json.return_value = {
            "sections": [
                {"section_type": "abstract", "start_char": 0, "end_char": 200, "confidence": 0.95, "heading": "ABSTRACT"},
                {"section_type": "introduction", "start_char": 200, "end_char": 400, "confidence": 0.92, "heading": "INTRODUCTION"},
                {"section_type": "methods", "start_char": 400, "end_char": 650, "confidence": 0.94, "heading": "METHODS"},
                {"section_type": "results", "start_char": 650, "end_char": 900, "confidence": 0.93, "heading": "RESULTS"},
                {"section_type": "discussion", "start_char": 900, "end_char": 1200, "confidence": 0.90, "heading": "DISCUSSION"},
                {"section_type": "conclusion", "start_char": 1200, "end_char": 1350, "confidence": 0.91, "heading": "CONCLUSION"},
                {"section_type": "references", "start_char": 1350, "end_char": len(paper_text), "confidence": 0.95, "heading": "REFERENCES"},
            ]
        }

        sections = await classifier.classify(paper_text)

        # 모든 주요 섹션이 식별되어야 함
        section_types = [s.section_type for s in sections]
        assert "abstract" in section_types
        assert "methods" in section_types
        assert "results" in section_types

        # Tier 1 섹션 확인
        tier1_sections = [s for s in sections if s.tier == 1]
        tier1_types = [s.section_type for s in tier1_sections]
        assert "abstract" in tier1_types or "results" in tier1_types or "conclusion" in tier1_types
