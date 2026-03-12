"""Tests for graph/types/enums.py — all enum classes."""

import pytest

from graph.types.enums import (
    CitationContext,
    DocumentType,
    EntityCategory,
    EvidenceLevel,
    InterventionCategory,
    OutcomeType,
    PaperRelationType,
    SpineSubDomain,
    StudyDesign,
    normalize_study_design,
)


# ── SpineSubDomain ──────────────────────────────────────────────

class TestSpineSubDomain:
    def test_members(self):
        expected = {"DEGENERATIVE", "DEFORMITY", "TRAUMA", "TUMOR", "BASIC_SCIENCE"}
        assert {m.name for m in SpineSubDomain} == expected

    def test_values(self):
        assert SpineSubDomain.DEGENERATIVE.value == "Degenerative"
        assert SpineSubDomain.BASIC_SCIENCE.value == "Basic Science"

    def test_lookup_by_value(self):
        assert SpineSubDomain("Deformity") is SpineSubDomain.DEFORMITY

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            SpineSubDomain("nonexistent")


# ── EvidenceLevel ───────────────────────────────────────────────

class TestEvidenceLevel:
    def test_member_count(self):
        assert len(EvidenceLevel) == 9

    def test_values(self):
        assert EvidenceLevel.LEVEL_1A.value == "1a"
        assert EvidenceLevel.LEVEL_1B.value == "1b"
        assert EvidenceLevel.LEVEL_2A.value == "2a"
        assert EvidenceLevel.LEVEL_2B.value == "2b"
        assert EvidenceLevel.LEVEL_2C.value == "2c"
        assert EvidenceLevel.LEVEL_3A.value == "3a"
        assert EvidenceLevel.LEVEL_3B.value == "3b"
        assert EvidenceLevel.LEVEL_4.value == "4"
        assert EvidenceLevel.LEVEL_5.value == "5"

    def test_lookup_by_value(self):
        assert EvidenceLevel("1a") is EvidenceLevel.LEVEL_1A

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            EvidenceLevel("6")


# ── StudyDesign ─────────────────────────────────────────────────

class TestStudyDesign:
    def test_member_count(self):
        assert len(StudyDesign) == 11

    def test_selected_values(self):
        assert StudyDesign.META_ANALYSIS.value == "meta-analysis"
        assert StudyDesign.RCT.value == "RCT"
        assert StudyDesign.CROSS_SECTIONAL.value == "cross-sectional"
        assert StudyDesign.OTHER.value == "other"

    def test_lookup_by_value(self):
        assert StudyDesign("RCT") is StudyDesign.RCT

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            StudyDesign("randomized")


# -- normalize_study_design ---------------------------------------------------

class TestNormalizeStudyDesign:
    """Tests for normalize_study_design() variant mapping."""

    # --- Empty / None ---
    @pytest.mark.parametrize("raw", ["", "  ", None])
    def test_empty_returns_empty(self, raw):
        assert normalize_study_design(raw or "") == ""

    # --- Canonical pass-through ---
    @pytest.mark.parametrize("canonical", [sd.value for sd in StudyDesign])
    def test_canonical_passthrough(self, canonical):
        assert normalize_study_design(canonical) == canonical

    # --- Underscore variants (study_classifier.py style) ---
    @pytest.mark.parametrize("raw,expected", [
        ("meta_analysis", "meta-analysis"),
        ("systematic_review", "systematic-review"),
        ("rct", "RCT"),
        ("case_control", "case-control"),
        ("case_series", "case-series"),
        ("case_report", "case-report"),
        ("expert_opinion", "expert-opinion"),
        ("cross_sectional", "cross-sectional"),
    ])
    def test_underscore_variants(self, raw, expected):
        assert normalize_study_design(raw) == expected

    # --- Space variants ---
    @pytest.mark.parametrize("raw,expected", [
        ("meta analysis", "meta-analysis"),
        ("case control", "case-control"),
        ("case series", "case-series"),
        ("case report", "case-report"),
        ("expert opinion", "expert-opinion"),
        ("cross sectional", "cross-sectional"),
        ("systematic review", "systematic-review"),
    ])
    def test_space_variants(self, raw, expected):
        assert normalize_study_design(raw) == expected

    # --- Long-form variants ---
    @pytest.mark.parametrize("raw,expected", [
        ("randomized controlled trial", "RCT"),
        ("randomised controlled trial", "RCT"),
        ("randomized_controlled_trial", "RCT"),
        ("randomized", "RCT"),
        ("randomised", "RCT"),
        ("controlled trial", "RCT"),
        ("double-blind", "RCT"),
    ])
    def test_rct_variants(self, raw, expected):
        assert normalize_study_design(raw) == expected

    # --- classify_papers.py style ---
    @pytest.mark.parametrize("raw,expected", [
        ("meta_analysis", "meta-analysis"),
        ("systematic_review", "systematic-review"),
        ("randomized", "RCT"),
        ("cohort", "retrospective-cohort"),
        ("case_control", "case-control"),
        ("retrospective", "retrospective-cohort"),
        ("case_series", "case-series"),
        ("cross_sectional", "cross-sectional"),
    ])
    def test_classify_papers_values(self, raw, expected):
        assert normalize_study_design(raw) == expected

    # --- Cohort variants ---
    @pytest.mark.parametrize("raw,expected", [
        ("prospective cohort", "prospective-cohort"),
        ("retrospective cohort", "retrospective-cohort"),
        ("prospective_cohort", "prospective-cohort"),
        ("retrospective_cohort", "retrospective-cohort"),
        ("cohort study", "retrospective-cohort"),
        ("cohort_study", "retrospective-cohort"),
        ("longitudinal", "prospective-cohort"),
        ("longitudinal study", "prospective-cohort"),
    ])
    def test_cohort_variants(self, raw, expected):
        assert normalize_study_design(raw) == expected

    # --- Substring fallback for compound strings ---
    def test_compound_randomized(self):
        assert normalize_study_design("multi-center randomized trial") == "RCT"

    def test_compound_meta(self):
        assert normalize_study_design("systematic review and meta-analysis") == "meta-analysis"

    # --- Unknown falls to "other" ---
    def test_unknown_maps_to_other(self):
        assert normalize_study_design("unknown") == "other"

    def test_gibberish_maps_to_other(self):
        assert normalize_study_design("something_totally_unexpected") == "other"

    # --- Non-randomized should NOT map to RCT ---
    @pytest.mark.parametrize("raw", [
        "non-randomized",
        "non_randomized",
        "non randomized",
        "non-randomised",
        "non-randomized single-arm",
        "non-randomized multi-arm",
    ])
    def test_non_randomized_is_not_rct(self, raw):
        assert normalize_study_design(raw) == "other"

    # --- Single-arm / multi-arm ---
    @pytest.mark.parametrize("raw", ["single-arm", "multi-arm", "single_arm", "multi_arm"])
    def test_arm_variants_are_other(self, raw):
        assert normalize_study_design(raw) == "other"

    # --- Case insensitivity ---
    def test_case_insensitive(self):
        assert normalize_study_design("META-ANALYSIS") == "meta-analysis"
        assert normalize_study_design("Rct") == "RCT"
        assert normalize_study_design("RETROSPECTIVE") == "retrospective-cohort"


# ── OutcomeType ─────────────────────────────────────────────────

class TestOutcomeType:
    def test_members(self):
        expected = {"CLINICAL", "RADIOLOGICAL", "FUNCTIONAL", "COMPLICATION"}
        assert {m.name for m in OutcomeType} == expected

    def test_values(self):
        assert OutcomeType.CLINICAL.value == "clinical"
        assert OutcomeType.RADIOLOGICAL.value == "radiological"


# ── InterventionCategory ────────────────────────────────────────

class TestInterventionCategory:
    def test_member_count(self):
        assert len(InterventionCategory) == 9

    def test_values(self):
        assert InterventionCategory.FUSION.value == "fusion"
        assert InterventionCategory.MOTION_PRESERVATION.value == "motion_preservation"
        assert InterventionCategory.OTHER.value == "other"

    def test_lookup_by_value(self):
        assert InterventionCategory("osteotomy") is InterventionCategory.OSTEOTOMY


# ── PaperRelationType ───────────────────────────────────────────

class TestPaperRelationType:
    def test_member_count(self):
        assert len(PaperRelationType) == 6

    def test_all_values_uppercase(self):
        for member in PaperRelationType:
            assert member.value == member.value.upper()

    def test_selected_values(self):
        assert PaperRelationType.SUPPORTS.value == "SUPPORTS"
        assert PaperRelationType.CONTRADICTS.value == "CONTRADICTS"
        assert PaperRelationType.CITES.value == "CITES"
        assert PaperRelationType.REPLICATES.value == "REPLICATES"


# ── DocumentType ────────────────────────────────────────────────

class TestDocumentType:
    def test_member_count(self):
        assert len(DocumentType) == 23

    def test_default_journal_article(self):
        assert DocumentType.JOURNAL_ARTICLE.value == "journal-article"

    def test_categories_present(self):
        # Spot-check one member from each category
        assert DocumentType.BOOK.value == "book"
        assert DocumentType.ENCYCLOPEDIA_ARTICLE.value == "encyclopedia-article"
        assert DocumentType.NEWSPAPER_ARTICLE.value == "newspaper-article"
        assert DocumentType.DATASET.value == "dataset"
        assert DocumentType.PRESENTATION.value == "presentation"

    def test_lookup_by_value(self):
        assert DocumentType("preprint") is DocumentType.PREPRINT


# ── EntityCategory ──────────────────────────────────────────────

class TestEntityCategory:
    def test_member_count(self):
        assert len(EntityCategory) == 19

    def test_basic_entities(self):
        basics = {"INTERVENTION", "PATHOLOGY", "ANATOMY", "OUTCOME"}
        assert basics.issubset({m.name for m in EntityCategory})

    def test_v11_entities(self):
        v11 = {"OUTCOME_MEASURE", "RADIO_PARAMETER", "PREDICTION_MODEL", "RISK_FACTOR"}
        assert v11.issubset({m.name for m in EntityCategory})

    def test_lookup_by_value(self):
        assert EntityCategory("drug") is EntityCategory.DRUG


# ── CitationContext ─────────────────────────────────────────────

class TestCitationContext:
    def test_member_count(self):
        assert len(CitationContext) == 5

    def test_values(self):
        assert CitationContext.SUPPORTS_RESULT.value == "supports_result"
        assert CitationContext.CONTRADICTS_RESULT.value == "contradicts_result"
        assert CitationContext.METHODOLOGICAL.value == "methodological"
        assert CitationContext.BACKGROUND.value == "background"
        assert CitationContext.COMPARISON.value == "comparison"

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            CitationContext("unknown")


# ── Cross-cutting enum properties ───────────────────────────────

class TestEnumGeneral:
    @pytest.mark.parametrize("enum_cls", [
        SpineSubDomain, EvidenceLevel, StudyDesign, OutcomeType,
        InterventionCategory, PaperRelationType, DocumentType,
        EntityCategory, CitationContext,
    ])
    def test_no_duplicate_values(self, enum_cls):
        values = [m.value for m in enum_cls]
        assert len(values) == len(set(values)), f"Duplicate values in {enum_cls.__name__}"

    @pytest.mark.parametrize("enum_cls", [
        SpineSubDomain, EvidenceLevel, StudyDesign, OutcomeType,
        InterventionCategory, PaperRelationType, DocumentType,
        EntityCategory, CitationContext,
    ])
    def test_str_representation(self, enum_cls):
        for member in enum_cls:
            # str() should contain the class name
            assert enum_cls.__name__ in str(member)

    @pytest.mark.parametrize("enum_cls", [
        SpineSubDomain, EvidenceLevel, StudyDesign, OutcomeType,
        InterventionCategory, PaperRelationType, DocumentType,
        EntityCategory, CitationContext,
    ])
    def test_identity_equality(self, enum_cls):
        """Enum members accessed by name and value should be identical."""
        for member in enum_cls:
            assert enum_cls(member.value) is member
