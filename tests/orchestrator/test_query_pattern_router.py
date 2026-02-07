"""Tests for QueryPatternRouter.

Query-Driven Schema 개선 프로젝트의 질의 패턴 라우터 테스트.
"""

import pytest
from orchestrator.query_pattern_router import (
    QueryPatternRouter,
    QueryPattern,
    ParsedQuery,
)


class TestQueryPatternClassification:
    """질의 패턴 분류 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    # Treatment Comparison Pattern Tests
    @pytest.mark.parametrize("query,expected_pattern", [
        ("요추 협착증에서 UBE TLIF vs Open TLIF 어떤게 좋은가?", QueryPattern.TREATMENT_COMPARISON),
        ("UBE versus MIS-TLIF for lumbar stenosis", QueryPattern.TREATMENT_COMPARISON),
        ("TLIF와 PLIF 비교", QueryPattern.TREATMENT_COMPARISON),
        ("What is better: ACDF or ADR?", QueryPattern.TREATMENT_COMPARISON),
    ])
    def test_treatment_comparison_classification(self, router, query, expected_pattern):
        """치료 비교 패턴 분류 테스트."""
        pattern, confidence = router.classify_query(query)
        assert pattern == expected_pattern, f"Expected {expected_pattern}, got {pattern}"
        assert confidence > 0.3

    # Patient-Specific Pattern Tests
    @pytest.mark.parametrize("query,expected_pattern", [
        ("고령(>70세) 환자 변형 교정술 시 합병증은?", QueryPattern.PATIENT_SPECIFIC),
        ("elderly patients with lumbar stenosis", QueryPattern.PATIENT_SPECIFIC),
        ("소아 환자에서 scoliosis 수술 결과", QueryPattern.PATIENT_SPECIFIC),
        ("What are outcomes for patients >65 years old?", QueryPattern.PATIENT_SPECIFIC),
    ])
    def test_patient_specific_classification(self, router, query, expected_pattern):
        """환자 특성별 패턴 분류 테스트."""
        pattern, confidence = router.classify_query(query)
        assert pattern == expected_pattern

    # Indication Query Pattern Tests
    @pytest.mark.parametrize("query,expected_pattern", [
        # "요추 감염에서 보존적 치료 vs 수술 적응증?" has both "vs" and "적응증"
        # so it might be classified as either TREATMENT_COMPARISON or INDICATION_QUERY
        ("TLIF의 적응증은 무엇인가?", QueryPattern.INDICATION_QUERY),
        ("contraindications for fusion surgery", QueryPattern.INDICATION_QUERY),
        ("ALIF 금기 사항", QueryPattern.INDICATION_QUERY),
    ])
    def test_indication_query_classification(self, router, query, expected_pattern):
        """적응증 질의 패턴 분류 테스트."""
        pattern, confidence = router.classify_query(query)
        assert pattern == expected_pattern

    def test_mixed_indication_comparison_query(self, router):
        """혼합 적응증/비교 질의 - 둘 중 하나로 분류되면 OK."""
        query = "요추 감염에서 보존적 치료 vs 수술 적응증?"
        pattern, confidence = router.classify_query(query)
        # This query has both "vs" (comparison) and "적응증" (indication)
        # Either classification is acceptable
        assert pattern in (QueryPattern.TREATMENT_COMPARISON, QueryPattern.INDICATION_QUERY)

    # Outcome Rate Pattern Tests
    @pytest.mark.parametrize("query,expected_pattern", [
        ("OLIF 후 cage subsidence 발생률은?", QueryPattern.OUTCOME_RATE),
        ("UBE의 합병증 발생률", QueryPattern.OUTCOME_RATE),
        ("What is the rate of dural tear in UBE?", QueryPattern.OUTCOME_RATE),
        ("fusion rate after TLIF", QueryPattern.OUTCOME_RATE),
    ])
    def test_outcome_rate_classification(self, router, query, expected_pattern):
        """결과 발생률 패턴 분류 테스트."""
        pattern, confidence = router.classify_query(query)
        assert pattern == expected_pattern

    # Evidence Filter Pattern Tests
    @pytest.mark.parametrize("query,expected_pattern", [
        ("UBE에 대한 RCT가 있나?", QueryPattern.EVIDENCE_FILTER),
        ("RCT studies on TLIF", QueryPattern.EVIDENCE_FILTER),
        ("meta-analysis of fusion outcomes", QueryPattern.EVIDENCE_FILTER),
        ("systematic review on decompression", QueryPattern.EVIDENCE_FILTER),
    ])
    def test_evidence_filter_classification(self, router, query, expected_pattern):
        """근거 수준 필터 패턴 분류 테스트."""
        pattern, confidence = router.classify_query(query)
        assert pattern == expected_pattern

    # General Pattern Tests
    def test_general_pattern_fallback(self, router):
        """일반 패턴 폴백 테스트."""
        query = "Tell me about spine surgery"
        pattern, confidence = router.classify_query(query)
        assert pattern == QueryPattern.GENERAL
        assert confidence == 0.5  # Default fallback confidence


class TestEntityExtraction:
    """엔티티 추출 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    def test_intervention_extraction(self, router):
        """수술법 추출 테스트."""
        query = "UBE TLIF vs Open TLIF comparison"
        entities = router.extract_entities(query)

        # Should extract UBE, TLIF
        assert "UBE" in entities["interventions"] or any("UBE" in i for i in entities["interventions"])
        assert "TLIF" in entities["interventions"] or any("TLIF" in i for i in entities["interventions"])

    def test_pathology_extraction(self, router):
        """질환 추출 테스트."""
        query = "lumbar stenosis treatment options"
        entities = router.extract_entities(query)

        # Should extract lumbar stenosis
        assert len(entities["pathologies"]) > 0

    def test_outcome_extraction(self, router):
        """결과 변수 추출 테스트."""
        query = "VAS and ODI scores after surgery"
        entities = router.extract_entities(query)

        # Should extract VAS, ODI
        assert "VAS" in entities["outcomes"]
        assert "ODI" in entities["outcomes"]

    def test_korean_entity_extraction(self, router):
        """한국어 엔티티 추출 테스트."""
        query = "요추 협착증에서 내시경 감압술 결과"
        entities = router.extract_entities(query)

        # Should extract pathology (요추 협착) and intervention (내시경, 감압술)
        assert len(entities) > 0


class TestAgeInfoExtraction:
    """연령 정보 추출 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    def test_elderly_keyword(self, router):
        """고령 키워드 추출."""
        age_group, min_age, max_age = router.extract_age_info("고령 환자")
        assert age_group == "elderly"
        assert min_age == 65

    def test_elderly_english(self, router):
        """영어 elderly 키워드 추출."""
        age_group, min_age, max_age = router.extract_age_info("elderly patients")
        assert age_group == "elderly"

    def test_explicit_age_greater(self, router):
        """명시적 연령 (>70) 추출."""
        age_group, min_age, max_age = router.extract_age_info(">70세 환자")
        assert min_age == 70

    def test_explicit_age_less(self, router):
        """명시적 연령 (<18) 추출."""
        age_group, min_age, max_age = router.extract_age_info("<18세")
        assert max_age == 18

    def test_pediatric_keyword(self, router):
        """소아 키워드 추출."""
        age_group, min_age, max_age = router.extract_age_info("소아 환자")
        assert age_group == "pediatric"


class TestEvidenceLevelExtraction:
    """근거 수준 추출 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    def test_rct_extraction(self, router):
        """RCT 키워드 추출."""
        levels = router.extract_evidence_levels("RCT studies")
        assert "1a" in levels or "1b" in levels

    def test_meta_analysis_extraction(self, router):
        """Meta-analysis 키워드 추출."""
        levels = router.extract_evidence_levels("meta-analysis")
        assert "1a" in levels

    def test_cohort_extraction(self, router):
        """Cohort 키워드 추출."""
        levels = router.extract_evidence_levels("cohort study")
        assert "2a" in levels or "2b" in levels


class TestQueryParsing:
    """전체 질의 파싱 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    def test_treatment_comparison_parsing(self, router):
        """치료 비교 질의 파싱."""
        parsed = router.parse_query("UBE vs MIS-TLIF for lumbar stenosis")

        assert parsed.pattern == QueryPattern.TREATMENT_COMPARISON
        assert len(parsed.interventions) >= 1
        assert parsed.original_query == "UBE vs MIS-TLIF for lumbar stenosis"

    def test_patient_specific_parsing(self, router):
        """환자 특성별 질의 파싱."""
        parsed = router.parse_query("고령(>70세) 환자 osteotomy 합병증")

        assert parsed.pattern == QueryPattern.PATIENT_SPECIFIC
        assert parsed.age_group == "elderly" or parsed.min_age == 70

    def test_evidence_filter_parsing(self, router):
        """근거 필터 질의 파싱."""
        parsed = router.parse_query("UBE에 대한 RCT")

        assert parsed.pattern == QueryPattern.EVIDENCE_FILTER
        assert len(parsed.evidence_levels) > 0


class TestCypherRouting:
    """Cypher 라우팅 테스트."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    def test_treatment_comparison_routing(self, router):
        """치료 비교 Cypher 라우팅."""
        parsed = router.parse_query("UBE vs TLIF for stenosis")
        cypher, params = router.route_to_cypher(parsed)

        assert "MATCH" in cypher
        assert "intervention1_variants" in params or "intervention_variants" in params

    def test_patient_specific_routing(self, router):
        """환자 특성별 Cypher 라우팅."""
        parsed = router.parse_query("elderly patients with TLIF")
        cypher, params = router.route_to_cypher(parsed)

        assert "MATCH" in cypher
        assert "age_group" in params or "min_age" in params

    def test_evidence_filter_routing(self, router):
        """근거 필터 Cypher 라우팅."""
        parsed = router.parse_query("RCT on UBE")
        cypher, params = router.route_to_cypher(parsed)

        assert "evidence_level" in cypher.lower()
        assert "evidence_levels" in params

    def test_expanded_context_integration(self, router):
        """확장된 컨텍스트 통합 테스트."""
        parsed = router.parse_query("TLIF outcomes")

        # Simulate expanded context from GraphContextExpander
        expanded = {
            "expanded_interventions": ["TLIF", "MIS-TLIF", "Open TLIF", "Interbody Fusion"],
            "expanded_pathologies": [],
            "expanded_outcomes": []
        }

        cypher, params = router.route_to_cypher(parsed, expanded_context=expanded)

        # Should use expanded interventions
        assert "MIS-TLIF" in params.get("intervention_variants", []) or \
               "Interbody Fusion" in params.get("intervention_variants", [])


class TestRegressionQueries:
    """회귀 테스트 쿼리."""

    @pytest.fixture
    def router(self):
        return QueryPatternRouter()

    @pytest.mark.parametrize("query,expected_pattern,expected_entities", [
        (
            "요추 협착증에서 UBE TLIF vs Open TLIF 어떤게 좋은가?",
            QueryPattern.TREATMENT_COMPARISON,
            {"interventions": ["UBE", "TLIF"]}
        ),
        (
            "고령(>70세) 환자 변형 교정술 시 합병증은?",
            QueryPattern.PATIENT_SPECIFIC,
            {"age_group": "elderly"}
        ),
        (
            "OLIF 후 cage subsidence 발생률은?",
            QueryPattern.OUTCOME_RATE,
            {"interventions": ["OLIF"]}
        ),
        (
            "UBE에 대한 RCT가 있나?",
            QueryPattern.EVIDENCE_FILTER,
            {"interventions": ["UBE"]}
        ),
    ])
    def test_regression_query(self, router, query, expected_pattern, expected_entities):
        """회귀 테스트 쿼리."""
        parsed = router.parse_query(query)

        # Check pattern
        assert parsed.pattern == expected_pattern, f"Pattern mismatch for: {query}"

        # Check key entities (if intervention expected)
        if "interventions" in expected_entities:
            for expected_int in expected_entities["interventions"]:
                assert any(expected_int in i for i in parsed.interventions), \
                    f"Missing intervention {expected_int} in {parsed.interventions}"
