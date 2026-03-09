"""Tests for Response Generator module."""

import pytest
from src.solver.response_generator import (
    ResponseGenerator,
    GeneratorInput,
    FormattedResponse,
    ResponseFormat,
    Citation,
    EvidenceItem,
    ConflictSummary,
    format_citation_apa,
    format_citation_vancouver,
)


def make_mock_results(count: int = 5) -> list[dict]:
    """테스트용 Mock 결과 생성."""
    results = [
        {
            "text": "Minimally invasive surgery shows better outcomes for lumbar disc herniation.",
            "document_id": "doc_1",
            "title": "RCT of Spine Surgery",
            "authors": ["Kim JS", "Park SM"],
            "publication_year": 2023,
            "journal": "Spine Journal",
            "evidence_level": "1b",
            "source_type": "original",
            "score": 0.95,
            "section": "results"
        },
        {
            "text": "Open surgery has higher complication rates compared to minimally invasive approaches.",
            "document_id": "doc_2",
            "title": "Comparative Analysis Study",
            "authors": ["Lee JH", "Choi WK", "Park YS"],
            "publication_year": 2022,
            "journal": "Neurosurgery",
            "evidence_level": "2a",
            "source_type": "original",
            "score": 0.88,
            "section": "conclusion"
        },
        {
            "text": "Previous studies reported similar findings (Smith et al., 2020).",
            "document_id": "doc_3",
            "title": "Systematic Review",
            "authors": ["Brown A"],
            "publication_year": 2021,
            "journal": "BMJ",
            "evidence_level": "1a",
            "source_type": "citation",
            "score": 0.75,
            "section": "discussion"
        },
        {
            "text": "Case series of 50 patients showed improvement in pain scores.",
            "document_id": "doc_4",
            "title": "Case Series Report",
            "authors": ["Zhang W", "Liu X"],
            "publication_year": 2022,
            "journal": "JBJS",
            "evidence_level": "4",
            "source_type": "original",
            "score": 0.70,
            "section": "results"
        },
        {
            "text": "Expert opinion suggests conservative treatment first.",
            "document_id": "doc_5",
            "title": "Expert Commentary",
            "authors": ["Expert MD"],
            "publication_year": 2019,
            "journal": "Lancet",
            "evidence_level": "5",
            "source_type": "background",
            "score": 0.60,
            "section": "discussion"
        },
    ]
    return results[:count]


class TestResponseGeneratorBasic:
    """Response Generator 기본 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_empty_results(self, generator):
        """빈 결과 처리."""
        result = generator.generate("test query", [])

        assert result.total_evidence == 0
        assert result.confidence == 0.0
        assert "No relevant evidence" in result.summary

    def test_string_input(self, generator):
        """문자열 입력."""
        results = make_mock_results(3)
        response = generator.generate("spine surgery outcomes", results)

        assert response.total_evidence == 3
        assert response.summary != ""

    def test_generator_input_object(self, generator):
        """GeneratorInput 객체 입력."""
        results = make_mock_results(3)
        input_obj = GeneratorInput(
            query="spine surgery outcomes",
            ranked_results=results,
            format=ResponseFormat.MARKDOWN
        )
        response = generator.generate(input_obj)

        assert response.total_evidence == 3
        assert response.markdown != ""


class TestCitationExtraction:
    """인용 추출 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_citations_extracted(self, generator):
        """인용 추출."""
        results = make_mock_results(5)
        response = generator.generate("test", results)

        # 원본 우선이므로 3개 원본만 추출
        assert len(response.citations) >= 1

    def test_citation_fields(self, generator):
        """인용 필드."""
        results = make_mock_results(3)
        response = generator.generate("test", results)

        if response.citations:
            citation = response.citations[0]
            assert citation.citation_id != ""
            assert citation.source_title != ""
            assert citation.evidence_level != ""

    def test_prefer_original_sources(self, generator):
        """원본 소스 우선."""
        results = make_mock_results(5)
        response = generator.generate("test", results)

        # 첫 인용은 원본이어야 함
        if response.citations:
            assert response.citations[0].source_type == "original"

    def test_max_citations_limit(self, generator):
        """최대 인용 수 제한."""
        results = make_mock_results(5)
        input_obj = GeneratorInput(
            query="test",
            ranked_results=results,
            max_citations=2
        )
        response = generator.generate(input_obj)

        assert len(response.citations) <= 2


class TestEvidenceCategories:
    """근거 수준별 분류 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_evidence_categorized(self, generator):
        """근거 분류."""
        results = make_mock_results(5)
        response = generator.generate("test", results)

        # 근거 수준별 딕셔너리
        assert isinstance(response.evidence_by_level, dict)
        assert len(response.evidence_by_level) > 0

    def test_high_quality_category(self, generator):
        """고품질 근거 분류."""
        results = make_mock_results(5)
        response = generator.generate("test", results)

        # Level 1 근거가 있어야 함
        high_quality = response.evidence_by_level.get("High Quality (Level 1)", [])
        assert len(high_quality) >= 1

    def test_evidence_item_structure(self, generator):
        """근거 항목 구조."""
        results = make_mock_results(3)
        response = generator.generate("test", results)

        for level_name, items in response.evidence_by_level.items():
            for item in items:
                assert isinstance(item, EvidenceItem)
                assert item.content != ""
                assert isinstance(item.citation, Citation)


class TestMarkdownGeneration:
    """마크다운 생성 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_markdown_generated(self, generator):
        """마크다운 생성."""
        results = make_mock_results(3)
        response = generator.generate("spine surgery outcomes", results)

        assert response.markdown != ""
        assert "#" in response.markdown  # 제목

    def test_markdown_sections(self, generator):
        """마크다운 섹션."""
        results = make_mock_results(3)
        response = generator.generate("spine surgery outcomes", results)

        assert "Summary" in response.markdown
        assert "Evidence" in response.markdown
        assert "References" in response.markdown

    def test_markdown_confidence(self, generator):
        """마크다운 신뢰도."""
        results = make_mock_results(3)
        response = generator.generate("spine surgery outcomes", results)

        assert "Confidence" in response.markdown


class TestPlainTextGeneration:
    """일반 텍스트 생성 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_plain_text_generated(self, generator):
        """일반 텍스트 생성."""
        results = make_mock_results(3)
        response = generator.generate("test", results)

        assert response.plain_text != ""

    def test_plain_text_sections(self, generator):
        """일반 텍스트 섹션."""
        results = make_mock_results(3)
        response = generator.generate("test", results)

        assert "SUMMARY" in response.plain_text
        assert "EVIDENCE" in response.plain_text
        assert "REFERENCES" in response.plain_text


class TestConflictHandling:
    """상충 결과 처리 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_conflict_formatted(self, generator):
        """상충 결과 포맷팅."""
        results = make_mock_results(3)
        conflicts = {
            "topic": "Surgical approach effectiveness",
            "description": "Studies show conflicting results",
            "positive_findings": ["Better outcomes with MIS"],
            "negative_findings": ["No significant difference"],
            "possible_reasons": ["Different patient populations"],
            "recommendation": "Consider individual patient factors"
        }

        input_obj = GeneratorInput(
            query="test",
            ranked_results=results,
            conflicts=conflicts
        )
        response = generator.generate(input_obj)

        assert response.conflicts is not None
        assert response.conflicts.topic == "Surgical approach effectiveness"

    def test_conflict_in_markdown(self, generator):
        """상충 결과 마크다운."""
        results = make_mock_results(3)
        conflicts = {
            "topic": "Treatment effectiveness",
            "description": "Conflicting evidence found",
            "positive_findings": ["Study A shows benefit"],
            "negative_findings": ["Study B shows no benefit"],
            "possible_reasons": ["Different methods"],
            "recommendation": "More research needed"
        }

        input_obj = GeneratorInput(
            query="test",
            ranked_results=results,
            conflicts=conflicts
        )
        response = generator.generate(input_obj)

        assert "Conflict" in response.markdown


class TestReasoningIntegration:
    """추론 결과 통합 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_reasoning_answer_used(self, generator):
        """추론 답변 사용."""

        class MockReasoning:
            answer = "This is the reasoned answer based on evidence."
            confidence = 0.85

        results = make_mock_results(3)
        input_obj = GeneratorInput(
            query="test",
            ranked_results=results,
            reasoning=MockReasoning()
        )
        response = generator.generate(input_obj)

        assert "reasoned answer" in response.summary

    def test_reasoning_confidence_used(self, generator):
        """추론 신뢰도 사용."""

        class MockReasoning:
            answer = "Test answer"
            confidence = 0.85

        results = make_mock_results(3)
        input_obj = GeneratorInput(
            query="test",
            ranked_results=results,
            reasoning=MockReasoning()
        )
        response = generator.generate(input_obj)

        assert response.confidence == 0.85


class TestConfiguration:
    """설정 테스트."""

    def test_default_config(self):
        """기본 설정."""
        generator = ResponseGenerator()
        assert generator.prefer_original is True
        assert generator.show_evidence_level is True

    def test_custom_config(self):
        """커스텀 설정."""
        config = {
            "prefer_original": False,
            "show_evidence_level": False,
            "show_source_type": False
        }
        generator = ResponseGenerator(config=config)

        assert generator.prefer_original is False
        assert generator.show_evidence_level is False


class TestCitationFormatters:
    """인용 형식 함수 테스트."""

    def test_apa_single_author(self):
        """APA 단일 저자."""
        citation = Citation(
            citation_id="[1]",
            source_title="Spine Surgery Outcomes",
            authors=["Kim JS"],
            publication_year=2023,
            journal="Spine Journal"
        )

        apa = format_citation_apa(citation)

        assert "Kim JS" in apa
        assert "2023" in apa
        assert "Spine Surgery Outcomes" in apa

    def test_apa_multiple_authors(self):
        """APA 다중 저자."""
        citation = Citation(
            citation_id="[1]",
            source_title="Study Title",
            authors=["Kim JS", "Park SM", "Lee JH"],
            publication_year=2023
        )

        apa = format_citation_apa(citation)

        assert "et al" in apa

    def test_vancouver_format(self):
        """Vancouver 형식."""
        citation = Citation(
            citation_id="[1]",
            source_title="Study Title",
            authors=["Kim JS", "Park SM"],
            publication_year=2023,
            journal="Spine Journal"
        )

        vancouver = format_citation_vancouver(citation, 1)

        assert "1." in vancouver
        assert "Kim JS" in vancouver
        assert "Study Title" in vancouver


class TestEdgeCases:
    """Edge case 테스트."""

    @pytest.fixture
    def generator(self):
        return ResponseGenerator()

    def test_single_result(self, generator):
        """단일 결과."""
        single = make_mock_results(1)
        response = generator.generate("test", single)

        assert response.total_evidence == 1
        assert len(response.citations) >= 1

    def test_missing_fields(self, generator):
        """필드 누락."""
        results = [
            {"text": "Content only", "score": 0.5}
        ]
        response = generator.generate("test", results)

        assert response.total_evidence == 1

    def test_very_long_content(self, generator):
        """긴 콘텐츠."""
        results = [
            {
                "text": "x" * 1000,
                "document_id": "doc_1",
                "title": "Test",
                "evidence_level": "1b",
                "source_type": "original",
                "score": 0.9
            }
        ]
        response = generator.generate("test", results)

        # 콘텐츠가 자연스럽게 잘림
        assert response.total_evidence == 1

    def test_special_characters_in_query(self, generator):
        """특수문자 쿼리."""
        results = make_mock_results(3)
        response = generator.generate("spine surgery? (MIS vs open)", results)

        assert response.markdown != ""

    def test_unicode_content(self, generator):
        """유니코드 콘텐츠."""
        results = [
            {
                "text": "척추 수술 결과 분석",
                "document_id": "doc_1",
                "title": "한국어 연구",
                "evidence_level": "2b",
                "source_type": "original",
                "score": 0.8
            }
        ]
        response = generator.generate("척추 수술", results)

        assert response.total_evidence == 1
        assert "한국어" in response.markdown or "척추" in response.plain_text
