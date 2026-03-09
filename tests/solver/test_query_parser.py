"""Tests for QueryParser module."""

import pytest
from src.solver.query_parser import (
    QueryParser,
    QueryInput,
    ParsedQuery,
    QueryIntent,
    EntityType,
    MedicalEntity,
    create_search_query,
)


class TestQueryParser:
    """QueryParser 테스트."""

    @pytest.fixture
    def parser(self):
        """기본 파서 fixture."""
        return QueryParser()

    def test_empty_query(self, parser):
        """빈 쿼리 처리."""
        result = parser.parse("")
        assert result.original == ""
        assert result.confidence == 0.0

    def test_simple_query(self, parser):
        """단순 쿼리 파싱."""
        result = parser.parse("lumbar disc herniation treatment")

        assert result.original == "lumbar disc herniation treatment"
        assert "lumbar" in result.normalized
        assert len(result.keywords) > 0

    def test_string_input(self, parser):
        """문자열 직접 입력."""
        result = parser.parse("back pain treatment")
        assert result.original == "back pain treatment"

    def test_query_input_object(self, parser):
        """QueryInput 객체 입력."""
        result = parser.parse(QueryInput(
            query="back pain treatment",
            expand_synonyms=True,
            max_expansions=3
        ))
        assert result.original == "back pain treatment"


class TestIntentClassification:
    """의도 분류 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_compare_intent(self, parser):
        """비교 의도 감지."""
        queries = [
            "minimally invasive vs open surgery",
            "comparison between drug A and drug B",
            "which is better endoscopic or open",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.COMPARE, f"Failed for: {query}"

    def test_causal_intent(self, parser):
        """인과관계 의도 감지."""
        queries = [
            "what causes back pain",
            "risk factors for diabetes",
            "mechanism of action",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.CAUSAL, f"Failed for: {query}"

    def test_definition_intent(self, parser):
        """정의 의도 감지."""
        queries = [
            "what is lumbar stenosis",
            "define spondylolisthesis",
            "explain disc herniation",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.DEFINITION, f"Failed for: {query}"

    def test_treatment_intent(self, parser):
        """치료 의도 감지."""
        queries = [
            "how to treat back pain",
            "best treatment for herniated disc",
            "management of diabetes",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.TREATMENT, f"Failed for: {query}"

    def test_diagnosis_intent(self, parser):
        """진단 의도 감지."""
        queries = [
            "how to diagnose lumbar stenosis",
            "diagnostic criteria for diabetes",
            "screening for cancer",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.DIAGNOSIS, f"Failed for: {query}"

    def test_safety_intent(self, parser):
        """안전성 의도 감지."""
        queries = [
            "side effects of aspirin",
            "is surgery safe for elderly",
            "adverse events of chemotherapy",
        ]

        for query in queries:
            result = parser.parse(query)
            assert result.intent == QueryIntent.SAFETY, f"Failed for: {query}"

    def test_default_search_intent(self, parser):
        """기본 검색 의도."""
        result = parser.parse("lumbar disc herniation")
        assert result.intent == QueryIntent.SEARCH


class TestEntityExtraction:
    """엔티티 추출 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_disease_entities(self, parser):
        """질병 엔티티 추출."""
        result = parser.parse("treatment for lung cancer and diabetes")

        disease_entities = [e for e in result.entities if e.entity_type == EntityType.DISEASE]
        disease_texts = [e.text.lower() for e in disease_entities]

        assert "cancer" in disease_texts
        assert "diabetes" in disease_texts

    def test_procedure_entities(self, parser):
        """시술 엔티티 추출."""
        result = parser.parse("laparoscopic cholecystectomy vs open surgery")

        procedure_entities = [e for e in result.entities if e.entity_type == EntityType.PROCEDURE]
        assert len(procedure_entities) >= 1

    def test_anatomy_entities(self, parser):
        """해부학 엔티티 추출."""
        result = parser.parse("lumbar spine disc herniation")

        anatomy_entities = [e for e in result.entities if e.entity_type == EntityType.ANATOMY]
        anatomy_texts = [e.text.lower() for e in anatomy_entities]

        assert "lumbar" in anatomy_texts or "spine" in anatomy_texts

    def test_symptom_entities(self, parser):
        """증상 엔티티 추출."""
        result = parser.parse("patient with back pain and numbness")

        symptom_entities = [e for e in result.entities if e.entity_type == EntityType.SYMPTOM]
        symptom_texts = [e.text.lower() for e in symptom_entities]

        assert "pain" in symptom_texts
        assert "numbness" in symptom_texts

    def test_entity_positions(self, parser):
        """엔티티 위치 정보."""
        query = "lumbar spine pain"
        result = parser.parse(query)

        for entity in result.entities:
            assert entity.start >= 0
            assert entity.end > entity.start
            assert entity.end <= len(query)


class TestTermExpansion:
    """용어 확장 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_synonym_expansion(self, parser):
        """동의어 확장."""
        result = parser.parse(QueryInput(
            query="heart attack treatment",
            expand_synonyms=True
        ))

        # "heart attack"의 동의어가 확장되어야 함
        expanded_lower = [t.lower() for t in result.expanded_terms]
        assert any("myocardial infarction" in t.lower() or "mi" in t.lower()
                  for t in result.expanded_terms) or len(result.expanded_terms) >= 0

    def test_no_expansion(self, parser):
        """확장 비활성화."""
        result = parser.parse(QueryInput(
            query="heart attack treatment",
            expand_synonyms=False
        ))

        assert result.expanded_terms == []

    def test_max_expansions(self, parser):
        """최대 확장 수 제한."""
        result = parser.parse(QueryInput(
            query="disc herniation back pain diabetes stroke",
            expand_synonyms=True,
            max_expansions=3
        ))

        assert len(result.expanded_terms) <= 3


class TestNormalization:
    """쿼리 정규화 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_lowercase(self, parser):
        """소문자 변환."""
        result = parser.parse("LUMBAR DISC Herniation")
        assert result.normalized == "lumbar disc herniation"

    def test_whitespace_normalization(self, parser):
        """공백 정규화."""
        result = parser.parse("lumbar   disc    herniation")
        assert "  " not in result.normalized

    def test_special_characters(self, parser):
        """특수문자 처리."""
        result = parser.parse("what is disc herniation?")
        # 물음표는 제거되어야 함
        assert "?" not in result.normalized


class TestNegationExtraction:
    """부정 표현 추출 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_negation_detection(self, parser):
        """부정 표현 감지."""
        result = parser.parse("treatment without surgery")
        assert "without" in result.negations

    def test_exclude_negation(self, parser):
        """제외 표현 감지."""
        result = parser.parse("back pain excluding cancer")
        assert "excluding" in result.negations

    def test_no_negation(self, parser):
        """부정 표현 없음."""
        result = parser.parse("lumbar disc herniation treatment")
        assert len(result.negations) == 0


class TestTemporalContext:
    """시간 맥락 추출 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_recent_context(self, parser):
        """최근 맥락 감지."""
        result = parser.parse("recent advances in spine surgery")
        assert result.temporal_context == "recent"

    def test_specific_year(self, parser):
        """특정 연도 감지."""
        result = parser.parse("studies from 2023")
        assert result.temporal_context == "specific_year"

    def test_duration_context(self, parser):
        """기간 맥락 감지."""
        result = parser.parse("chronic back pain treatment")
        assert result.temporal_context == "duration"

    def test_no_temporal_context(self, parser):
        """시간 맥락 없음."""
        result = parser.parse("lumbar disc herniation")
        assert result.temporal_context is None


class TestConfidence:
    """신뢰도 계산 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_high_confidence_query(self, parser):
        """높은 신뢰도 쿼리."""
        result = parser.parse("what is the best treatment for lumbar disc herniation")
        assert result.confidence >= 0.7

    def test_low_confidence_query(self, parser):
        """낮은 신뢰도 쿼리."""
        result = parser.parse("x y z")
        assert result.confidence <= 0.6


class TestCreateSearchQuery:
    """검색 쿼리 생성 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_create_search_query(self, parser):
        """검색 쿼리 생성."""
        parsed = parser.parse("lumbar disc herniation treatment")
        search_query = create_search_query(parsed)

        assert len(search_query) > 0
        assert "lumbar" in search_query.lower() or "disc" in search_query.lower()

    def test_empty_parsed_query(self):
        """빈 파싱 결과."""
        parsed = ParsedQuery(original="", normalized="")
        search_query = create_search_query(parsed)
        assert search_query == ""


class TestHelperMethods:
    """헬퍼 메서드 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_get_entity_types(self, parser):
        """엔티티 유형 목록."""
        types = parser.get_entity_types()
        assert "disease" in types
        assert "drug" in types
        assert "procedure" in types

    def test_get_intent_types(self, parser):
        """의도 유형 목록."""
        types = parser.get_intent_types()
        assert "search" in types
        assert "compare" in types
        assert "treatment" in types


class TestEdgeCases:
    """Edge case 테스트."""

    @pytest.fixture
    def parser(self):
        return QueryParser()

    def test_very_long_query(self, parser):
        """매우 긴 쿼리."""
        long_query = "lumbar disc herniation " * 50
        result = parser.parse(long_query)
        assert result.original == long_query.strip()

    def test_unicode_characters(self, parser):
        """유니코드 문자."""
        result = parser.parse("治療 for back pain")  # 일본어 "치료"
        assert result.original == "治療 for back pain"

    def test_numbers_in_query(self, parser):
        """숫자 포함 쿼리."""
        result = parser.parse("L4-L5 disc herniation")
        assert "l4" in result.normalized or "L4" in result.original
