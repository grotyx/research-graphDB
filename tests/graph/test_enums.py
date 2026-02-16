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
        assert len(EvidenceLevel) == 7

    def test_values(self):
        assert EvidenceLevel.LEVEL_1A.value == "1a"
        assert EvidenceLevel.LEVEL_1B.value == "1b"
        assert EvidenceLevel.LEVEL_2A.value == "2a"
        assert EvidenceLevel.LEVEL_2B.value == "2b"
        assert EvidenceLevel.LEVEL_3.value == "3"
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
        assert len(StudyDesign) == 10

    def test_selected_values(self):
        assert StudyDesign.META_ANALYSIS.value == "meta-analysis"
        assert StudyDesign.RCT.value == "RCT"
        assert StudyDesign.OTHER.value == "other"

    def test_lookup_by_value(self):
        assert StudyDesign("RCT") is StudyDesign.RCT

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            StudyDesign("randomized")


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
        assert len(InterventionCategory) == 8

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
