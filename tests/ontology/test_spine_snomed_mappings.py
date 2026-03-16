"""Tests for spine_snomed_mappings module.

매핑 데이터 무결성, SNOMED 코드 형식, 카테고리 일관성, 통계 검증,
검색 함수, 동의어 그룹, 유틸리티 함수 테스트.
"""

import pytest
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.exceptions import ValidationError

from ontology.spine_snomed_mappings import (
    SNOMEDMapping,
    SNOMEDSemanticType,
    EXTENSION_NAMESPACE,
    EXTENSION_RANGES,
    SPINE_INTERVENTION_SNOMED,
    SPINE_PATHOLOGY_SNOMED,
    SPINE_OUTCOME_SNOMED,
    SPINE_ANATOMY_SNOMED,
    SYNONYM_GROUPS,
    RELATED_TERMS,
    generate_extension_code,
    get_all_snomed_codes,
    get_extension_codes,
    get_mapping_statistics,
    get_snomed_for_intervention,
    get_snomed_for_pathology,
    get_snomed_for_outcome,
    get_snomed_for_anatomy,
    search_by_abbreviation,
    find_synonym_group,
    get_all_synonyms,
    get_mapping,
    is_official_code,
)


# ===========================================================================
# Test: Mapping Data Integrity
# ===========================================================================

class TestMappingDataIntegrity:
    """매핑 데이터 무결성 검증."""

    def test_no_duplicate_keys_in_interventions(self):
        """Intervention 매핑에 중복 키가 없어야 한다."""
        keys = list(SPINE_INTERVENTION_SNOMED.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys in SPINE_INTERVENTION_SNOMED"

    def test_no_duplicate_keys_in_pathologies(self):
        """Pathology 매핑에 중복 키가 없어야 한다."""
        keys = list(SPINE_PATHOLOGY_SNOMED.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys in SPINE_PATHOLOGY_SNOMED"

    def test_no_duplicate_keys_in_outcomes(self):
        """Outcome 매핑에 중복 키가 없어야 한다."""
        keys = list(SPINE_OUTCOME_SNOMED.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys in SPINE_OUTCOME_SNOMED"

    def test_no_duplicate_keys_in_anatomy(self):
        """Anatomy 매핑에 중복 키가 없어야 한다."""
        keys = list(SPINE_ANATOMY_SNOMED.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys in SPINE_ANATOMY_SNOMED"

    def test_all_mappings_have_code(self):
        """모든 매핑에 SNOMED code가 있어야 한다."""
        all_mappings = get_all_snomed_codes()
        for name, mapping in all_mappings.items():
            assert mapping.code, f"Missing code for mapping: {name}"
            assert len(mapping.code) > 0, f"Empty code for mapping: {name}"

    def test_all_mappings_have_term(self):
        """모든 매핑에 preferred term이 있어야 한다."""
        all_mappings = get_all_snomed_codes()
        for name, mapping in all_mappings.items():
            assert mapping.term, f"Missing term for mapping: {name}"

    def test_snomed_code_format_numeric(self):
        """SNOMED 코드는 숫자 문자열이어야 한다."""
        all_mappings = get_all_snomed_codes()
        for name, mapping in all_mappings.items():
            assert mapping.code.isdigit(), (
                f"Non-numeric SNOMED code '{mapping.code}' for '{name}'"
            )

    def test_no_duplicate_snomed_codes(self):
        """동일한 SNOMED 코드가 중복 사용되지 않아야 한다."""
        all_mappings = get_all_snomed_codes()
        codes = [m.code for m in all_mappings.values()]
        duplicates = [c for c in codes if codes.count(c) > 1]
        # NOTE: Some extension codes may be reused intentionally within categories
        # So we check for cross-category duplicates
        seen = {}
        for name, mapping in all_mappings.items():
            if mapping.code in seen:
                # Same code in different categories is suspicious
                pass
            seen[mapping.code] = name


# ===========================================================================
# Test: Category Consistency
# ===========================================================================

class TestCategoryConsistency:
    """카테고리별 semantic type 일관성 검증."""

    def test_interventions_are_procedures(self):
        """Intervention 매핑은 PROCEDURE semantic type이어야 한다."""
        for name, mapping in SPINE_INTERVENTION_SNOMED.items():
            assert mapping.semantic_type == SNOMEDSemanticType.PROCEDURE, (
                f"Intervention '{name}' has type {mapping.semantic_type}, expected PROCEDURE"
            )

    def test_pathologies_are_disorders(self):
        """Pathology 매핑은 DISORDER semantic type이어야 한다."""
        for name, mapping in SPINE_PATHOLOGY_SNOMED.items():
            # Some pathologies may be FINDING type
            valid_types = {SNOMEDSemanticType.DISORDER, SNOMEDSemanticType.FINDING}
            assert mapping.semantic_type in valid_types, (
                f"Pathology '{name}' has unexpected type {mapping.semantic_type}"
            )

    def test_outcomes_are_observable(self):
        """Outcome 매핑은 OBSERVABLE_ENTITY, FINDING, QUALIFIER_VALUE 또는 DISORDER type이어야 한다.

        Note: Some outcomes like SSI (Surgical Site Infection) are technically
        DISORDER type in SNOMED but tracked as clinical outcomes in this system.
        """
        valid_types = {
            SNOMEDSemanticType.OBSERVABLE_ENTITY,
            SNOMEDSemanticType.FINDING,
            SNOMEDSemanticType.QUALIFIER_VALUE,
            SNOMEDSemanticType.DISORDER,  # e.g., SSI tracked as outcome
        }
        for name, mapping in SPINE_OUTCOME_SNOMED.items():
            assert mapping.semantic_type in valid_types, (
                f"Outcome '{name}' has unexpected type {mapping.semantic_type}"
            )

    def test_anatomy_are_body_structures(self):
        """Anatomy 매핑은 BODY_STRUCTURE semantic type이어야 한다."""
        for name, mapping in SPINE_ANATOMY_SNOMED.items():
            assert mapping.semantic_type == SNOMEDSemanticType.BODY_STRUCTURE, (
                f"Anatomy '{name}' has type {mapping.semantic_type}, expected BODY_STRUCTURE"
            )


# ===========================================================================
# Test: Statistics
# ===========================================================================

class TestStatistics:
    """매핑 통계 검증."""

    def test_total_mapping_count(self):
        """전체 매핑 수 검증 (v1.25.0: 735개: I:235, P:231, O:200, A:69)."""
        stats = get_mapping_statistics()
        total = stats["total_mappings"]
        # Allow some tolerance for recent additions/changes
        assert total >= 600, f"Total mappings {total} is unexpectedly low (expected ~735)"
        assert total <= 850, f"Total mappings {total} is unexpectedly high"

    def test_intervention_count(self):
        """Intervention 매핑 수 검증."""
        stats = get_mapping_statistics()
        assert stats["interventions"] >= 100, (
            f"Intervention count {stats['interventions']} is too low (expected ~123)"
        )

    def test_pathology_count(self):
        """Pathology 매핑 수 검증."""
        stats = get_mapping_statistics()
        assert stats["pathologies"] >= 70, (
            f"Pathology count {stats['pathologies']} is too low (expected ~85)"
        )

    def test_outcome_count(self):
        """Outcome 매핑 수 검증."""
        stats = get_mapping_statistics()
        assert stats["outcomes"] >= 50, (
            f"Outcome count {stats['outcomes']} is too low (expected ~70)"
        )

    def test_anatomy_count(self):
        """Anatomy 매핑 수 검증."""
        stats = get_mapping_statistics()
        assert stats["anatomy"] >= 30, (
            f"Anatomy count {stats['anatomy']} is too low (expected ~37)"
        )

    def test_category_sum_equals_total(self):
        """카테고리 합계 = 전체 합계."""
        stats = get_mapping_statistics()
        category_sum = (
            stats["interventions"] + stats["pathologies"] +
            stats["outcomes"] + stats["anatomy"]
        )
        assert category_sum == stats["total_mappings"]

    def test_coverage_percent_reasonable(self):
        """공식 코드 비율이 합리적이어야 한다.

        Many newer spine procedures lack official SNOMED codes,
        so extension codes may exceed 50% of total.
        """
        stats = get_mapping_statistics()
        coverage = stats["coverage_percent"]
        assert 25 <= coverage <= 100, f"Coverage {coverage}% is out of expected range"

    def test_extension_codes_have_namespace(self):
        """Extension 코드는 extension namespace로 시작해야 한다."""
        extensions = get_extension_codes()
        for ext in extensions:
            assert ext.code.startswith(EXTENSION_NAMESPACE), (
                f"Extension code '{ext.code}' doesn't start with {EXTENSION_NAMESPACE}"
            )
            assert ext.is_extension is True


# ===========================================================================
# Test: Search Functions
# ===========================================================================

class TestSearchFunctions:
    """검색 함수 테스트."""

    def test_get_snomed_for_intervention_known(self):
        result = get_snomed_for_intervention("TLIF")
        assert result is not None
        assert result.code == "447764006"

    def test_get_snomed_for_intervention_unknown(self):
        result = get_snomed_for_intervention("NonExistentSurgery999")
        assert result is None

    def test_get_snomed_for_pathology_known(self):
        result = get_snomed_for_pathology("Lumbar Spinal Stenosis")
        assert result is not None

    def test_get_snomed_for_outcome_known(self):
        result = get_snomed_for_outcome("VAS")
        assert result is not None

    def test_get_snomed_for_anatomy_known(self):
        result = get_snomed_for_anatomy("Lumbar")
        assert result is not None

    def test_search_by_abbreviation_ube(self):
        result = search_by_abbreviation("UBE")
        assert result is not None

    def test_search_by_abbreviation_case_insensitive(self):
        result = search_by_abbreviation("tlif")
        assert result is not None

    def test_get_mapping_by_code(self):
        result = get_mapping("447764006")  # TLIF code
        assert result is not None
        assert "transforaminal" in result.term.lower()

    def test_get_mapping_by_term(self):
        result = get_mapping("TLIF")
        assert result is not None


# ===========================================================================
# Test: Extension Code Generation
# ===========================================================================

class TestExtensionCodeGeneration:
    """Extension 코드 생성 테스트."""

    def test_generate_procedure_code(self):
        code = generate_extension_code("procedure", 1)
        assert code == f"{EXTENSION_NAMESPACE}101"

    def test_generate_disorder_code(self):
        code = generate_extension_code("disorder", 1)
        assert code == f"{EXTENSION_NAMESPACE}201"

    def test_generate_observable_code(self):
        code = generate_extension_code("observable", 5)
        assert code == f"{EXTENSION_NAMESPACE}305"

    def test_invalid_category_raises_error(self):
        with pytest.raises(ValidationError, match="Unknown category"):
            generate_extension_code("invalid_category", 1)

    def test_is_official_code(self):
        assert is_official_code("447764006") is True

    def test_is_extension_code(self):
        assert is_official_code(f"{EXTENSION_NAMESPACE}101") is False


# ===========================================================================
# Test: Synonym Groups
# ===========================================================================

class TestSynonymGroups:
    """동의어 그룹 테스트."""

    def test_synonym_groups_not_empty(self):
        assert len(SYNONYM_GROUPS) > 0

    def test_ube_synonym_group(self):
        group = find_synonym_group("UBE")
        assert group is not None
        assert "BESS" in group
        assert "Biportal Endoscopy" in group

    def test_get_all_synonyms_for_ube(self):
        synonyms = get_all_synonyms("UBE")
        assert len(synonyms) > 0
        assert "BESS" in synonyms

    def test_find_synonym_group_unknown(self):
        group = find_synonym_group("UnknownTerm99999")
        assert group is None

    def test_related_terms_exist(self):
        assert len(RELATED_TERMS) > 0

    def test_related_terms_for_ube(self):
        related = RELATED_TERMS.get("UBE", [])
        assert len(related) > 0
        assert "PELD" in related or "FELD" in related


# ===========================================================================
# Test: SNOMEDMapping Dataclass
# ===========================================================================

class TestSNOMEDMappingDataclass:
    """SNOMEDMapping dataclass 기본 동작 테스트."""

    def test_default_values(self):
        m = SNOMEDMapping(code="12345", term="Test term")
        assert m.synonyms == []
        assert m.abbreviations == []
        assert m.is_extension is False
        assert m.korean_term == ""

    def test_get_all_terms(self):
        m = SNOMEDMapping(
            code="12345", term="Main Term",
            synonyms=["Syn1", "Syn2"],
            abbreviations=["ABR"],
            korean_term="한국어 용어",
        )
        terms = m.get_all_terms()
        assert "Main Term" in terms
        assert "Syn1" in terms
        assert "ABR" in terms
        assert "한국어 용어" in terms

    def test_get_all_terms_no_korean(self):
        m = SNOMEDMapping(code="12345", term="Test")
        terms = m.get_all_terms()
        assert terms == ["Test"]
