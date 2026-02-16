"""Tests for graph/types/relationships.py — Relationship dataclasses.

Tests cover:
- Dataclass instantiation with valid data
- Default values
- to_neo4j_properties() method
- from_neo4j_record() class method (round-trip serialization)
- Edge cases: empty strings, None values, boundary values
- Enum usage in CitesRelationship and PaperRelationship
"""

from datetime import datetime

import pytest

from graph.types.relationships import (
    StudiesRelation,
    HasChunkRelation,
    LocatedAtRelation,
    InvestigatesRelation,
    TreatsRelation,
    AffectsRelation,
    IsARelation,
    PaperRelation,
    CitesRelationship,
    PaperRelationship,
    CausesRelation,
    HasRiskFactorRelation,
    PredictsRelation,
    CorrelatesRelation,
    UsesDeviceRelation,
    HasCohortRelation,
    TreatedWithRelation,
    HasFollowUpRelation,
    ReportsOutcomeAtRelation,
    ReportsCostRelation,
    CostAssociatedWithRelation,
    HasQualityMetricRelation,
)
from graph.types.enums import CitationContext, PaperRelationType


# ============================================================================
# Basic Relationships
# ============================================================================

class TestStudiesRelation:
    def test_instantiation(self):
        r = StudiesRelation(source_paper_id="P001", target_pathology="Lumbar Stenosis")
        assert r.source_paper_id == "P001"
        assert r.target_pathology == "Lumbar Stenosis"

    def test_default_is_primary(self):
        r = StudiesRelation(source_paper_id="P001", target_pathology="DDD")
        assert r.is_primary is True

    def test_override_is_primary(self):
        r = StudiesRelation(source_paper_id="P001", target_pathology="DDD", is_primary=False)
        assert r.is_primary is False


class TestHasChunkRelation:
    def test_instantiation(self):
        r = HasChunkRelation(paper_id="P001", chunk_id="C001")
        assert r.paper_id == "P001"
        assert r.chunk_id == "C001"

    def test_default_chunk_index(self):
        r = HasChunkRelation(paper_id="P001", chunk_id="C001")
        assert r.chunk_index == 0

    def test_custom_chunk_index(self):
        r = HasChunkRelation(paper_id="P001", chunk_id="C005", chunk_index=4)
        assert r.chunk_index == 4


class TestLocatedAtRelation:
    def test_instantiation(self):
        r = LocatedAtRelation(pathology_name="Lumbar Stenosis", anatomy_name="L4")
        assert r.pathology_name == "Lumbar Stenosis"
        assert r.anatomy_name == "L4"


class TestInvestigatesRelation:
    def test_instantiation(self):
        r = InvestigatesRelation(paper_id="P001", intervention_name="TLIF")
        assert r.paper_id == "P001"
        assert r.intervention_name == "TLIF"

    def test_default_is_comparison(self):
        r = InvestigatesRelation(paper_id="P001", intervention_name="TLIF")
        assert r.is_comparison is False

    def test_comparison_study(self):
        r = InvestigatesRelation(paper_id="P001", intervention_name="TLIF", is_comparison=True)
        assert r.is_comparison is True


# ============================================================================
# TreatsRelation (with to_neo4j_properties and from_neo4j_record)
# ============================================================================

class TestTreatsRelation:
    def test_instantiation_minimal(self):
        r = TreatsRelation(intervention_name="TLIF", pathology_name="Spondylolisthesis")
        assert r.intervention_name == "TLIF"
        assert r.pathology_name == "Spondylolisthesis"
        assert r.indication == ""

    def test_defaults(self):
        r = TreatsRelation(intervention_name="X", pathology_name="Y")
        assert r.contraindication == ""
        assert r.indication_level == ""
        assert r.source_guideline == ""

    def test_to_neo4j_properties(self):
        r = TreatsRelation(
            intervention_name="ACDF",
            pathology_name="Cervical Stenosis",
            indication="Myelopathy",
            contraindication="Severe osteoporosis",
            indication_level="strong",
            source_guideline="NASS 2020",
        )
        props = r.to_neo4j_properties()
        assert props["indication"] == "Myelopathy"
        assert props["contraindication"] == "Severe osteoporosis"
        assert props["indication_level"] == "strong"
        assert props["source_guideline"] == "NASS 2020"

    def test_to_neo4j_truncates_long_values(self):
        long_text = "x" * 1000
        r = TreatsRelation(
            intervention_name="A", pathology_name="B",
            indication=long_text,
            contraindication=long_text,
            source_guideline=long_text,
        )
        props = r.to_neo4j_properties()
        assert len(props["indication"]) == 500
        assert len(props["contraindication"]) == 500
        assert len(props["source_guideline"]) == 200

    def test_from_neo4j_record(self):
        record = {
            "indication": "Radiculopathy",
            "contraindication": "",
            "indication_level": "moderate",
            "source_guideline": "AO 2019",
        }
        r = TreatsRelation.from_neo4j_record(record, "UBE", "LDH")
        assert r.intervention_name == "UBE"
        assert r.pathology_name == "LDH"
        assert r.indication == "Radiculopathy"
        assert r.indication_level == "moderate"

    def test_from_neo4j_record_missing_keys(self):
        r = TreatsRelation.from_neo4j_record({}, "X", "Y")
        assert r.indication == ""
        assert r.contraindication == ""


# ============================================================================
# AffectsRelation
# ============================================================================

class TestAffectsRelation:
    def test_instantiation(self):
        r = AffectsRelation(
            intervention_name="TLIF",
            outcome_name="VAS",
            source_paper_id="P001",
        )
        assert r.intervention_name == "TLIF"
        assert r.outcome_name == "VAS"
        assert r.source_paper_id == "P001"

    def test_defaults(self):
        r = AffectsRelation(intervention_name="X", outcome_name="Y", source_paper_id="P")
        assert r.value == ""
        assert r.baseline is None
        assert r.final is None
        assert r.p_value is None
        assert r.is_significant is False
        assert r.direction == ""
        assert r.category == ""
        assert r.timepoint == ""

    def test_to_neo4j_properties_full(self):
        r = AffectsRelation(
            intervention_name="UBE", outcome_name="ODI", source_paper_id="P002",
            value="32.5", baseline=55.0, final=32.5,
            p_value=0.001, effect_size="0.8", confidence_interval="95% CI: 28-37",
            is_significant=True, direction="improved",
            category="functional", timepoint="1yr",
        )
        props = r.to_neo4j_properties()
        assert props["source_paper_id"] == "P002"
        assert props["value"] == "32.5"
        assert props["baseline"] == 55.0
        assert props["final"] == 32.5
        assert props["p_value"] == 0.001
        assert props["is_significant"] is True
        assert props["direction"] == "improved"
        assert props["category"] == "functional"
        assert props["timepoint"] == "1yr"

    def test_to_neo4j_properties_preserves_none(self):
        r = AffectsRelation(intervention_name="X", outcome_name="Y", source_paper_id="P")
        props = r.to_neo4j_properties()
        assert props["baseline"] is None
        assert props["final"] is None
        assert props["p_value"] is None


# ============================================================================
# IsARelation
# ============================================================================

class TestIsARelation:
    def test_instantiation(self):
        r = IsARelation(child_name="TLIF", parent_name="Interbody Fusion")
        assert r.child_name == "TLIF"
        assert r.parent_name == "Interbody Fusion"

    def test_default_level(self):
        r = IsARelation(child_name="A", parent_name="B")
        assert r.level == 1

    def test_custom_level(self):
        r = IsARelation(child_name="MIS-TLIF", parent_name="TLIF", level=3)
        assert r.level == 3


# ============================================================================
# PaperRelation (Legacy)
# ============================================================================

class TestPaperRelation:
    def test_instantiation(self):
        r = PaperRelation(
            source_paper_id="P001",
            target_paper_id="P002",
            relation_type="supports",
        )
        assert r.source_paper_id == "P001"
        assert r.target_paper_id == "P002"
        assert r.relation_type == "supports"

    def test_defaults(self):
        r = PaperRelation(source_paper_id="A", target_paper_id="B", relation_type="cites")
        assert r.confidence == 0.0
        assert r.evidence == ""
        assert r.conflict_point == ""


# ============================================================================
# CitesRelationship (with Enum, to_neo4j, from_neo4j)
# ============================================================================

class TestCitesRelationship:
    def test_instantiation_minimal(self):
        r = CitesRelationship(citing_paper_id="P001", cited_paper_id="P002")
        assert r.citing_paper_id == "P001"
        assert r.cited_paper_id == "P002"

    def test_default_context(self):
        r = CitesRelationship(citing_paper_id="P001", cited_paper_id="P002")
        assert r.context == CitationContext.BACKGROUND

    def test_custom_context(self):
        r = CitesRelationship(
            citing_paper_id="P001", cited_paper_id="P002",
            context=CitationContext.SUPPORTS_RESULT,
        )
        assert r.context == CitationContext.SUPPORTS_RESULT

    def test_to_neo4j_properties(self):
        r = CitesRelationship(
            citing_paper_id="P001", cited_paper_id="P002",
            context=CitationContext.COMPARISON,
            section="discussion",
            citation_text="Consistent with our results...",
            confidence=0.85,
            detected_by="llm_extraction",
        )
        props = r.to_neo4j_properties()
        assert props["context"] == "comparison"
        assert props["section"] == "discussion"
        assert props["confidence"] == 0.85
        assert props["detected_by"] == "llm_extraction"
        assert "created_at" in props

    def test_to_neo4j_truncates_long_text(self):
        long_text = "x" * 1000
        r = CitesRelationship(
            citing_paper_id="P1", cited_paper_id="P2",
            citation_text=long_text,
            importance_reason=long_text,
        )
        props = r.to_neo4j_properties()
        assert len(props["citation_text"]) == 500
        assert len(props["importance_reason"]) == 500

    def test_from_neo4j_record(self):
        record = {
            "context": "supports_result",
            "section": "results",
            "citation_text": "Study X showed...",
            "importance_reason": "Key supporting evidence",
            "outcome_comparison": "VAS",
            "direction_match": True,
            "confidence": 0.9,
            "detected_by": "llm_extraction",
            "created_at": datetime(2025, 1, 1),
        }
        r = CitesRelationship.from_neo4j_record(record, "P001", "P002")
        assert r.citing_paper_id == "P001"
        assert r.cited_paper_id == "P002"
        assert r.context == CitationContext.SUPPORTS_RESULT
        assert r.section == "results"
        assert r.direction_match is True
        assert r.confidence == 0.9

    def test_from_neo4j_record_invalid_context_fallback(self):
        record = {"context": "unknown_context_value"}
        r = CitesRelationship.from_neo4j_record(record, "P1", "P2")
        assert r.context == CitationContext.BACKGROUND

    def test_from_neo4j_record_empty(self):
        r = CitesRelationship.from_neo4j_record({}, "P1", "P2")
        assert r.context == CitationContext.BACKGROUND
        assert r.section == ""
        assert r.confidence == 0.0


# ============================================================================
# PaperRelationship (Unified - v3.1+)
# ============================================================================

class TestPaperRelationship:
    def test_instantiation(self):
        r = PaperRelationship(
            source_paper_id="P001",
            target_paper_id="P002",
            relation_type=PaperRelationType.SUPPORTS,
        )
        assert r.source_paper_id == "P001"
        assert r.relation_type == PaperRelationType.SUPPORTS

    def test_defaults(self):
        r = PaperRelationship(
            source_paper_id="A", target_paper_id="B",
            relation_type=PaperRelationType.CITES,
        )
        assert r.confidence == 0.0
        assert r.evidence == ""
        assert r.detected_by == ""
        assert r.created_at is None

    def test_to_neo4j_properties(self):
        r = PaperRelationship(
            source_paper_id="P1", target_paper_id="P2",
            relation_type=PaperRelationType.CONTRADICTS,
            confidence=0.75, evidence="Conflicting results on VAS",
            detected_by="llm",
        )
        props = r.to_neo4j_properties()
        assert props["confidence"] == 0.75
        assert props["evidence"] == "Conflicting results on VAS"
        assert props["detected_by"] == "llm"
        assert "created_at" in props

    def test_to_neo4j_truncates_evidence(self):
        long_evidence = "x" * 2000
        r = PaperRelationship(
            source_paper_id="P1", target_paper_id="P2",
            relation_type=PaperRelationType.SUPPORTS,
            evidence=long_evidence,
        )
        props = r.to_neo4j_properties()
        assert len(props["evidence"]) == 1000

    def test_from_neo4j_record(self):
        record = {
            "confidence": 0.88,
            "evidence": "Similar findings for ODI improvement",
            "detected_by": "embedding",
            "created_at": datetime(2025, 6, 15),
        }
        r = PaperRelationship.from_neo4j_record(record, "P1", "P2", "EXTENDS")
        assert r.source_paper_id == "P1"
        assert r.target_paper_id == "P2"
        assert r.relation_type == PaperRelationType.EXTENDS
        assert r.confidence == 0.88
        assert r.detected_by == "embedding"

    def test_from_neo4j_record_all_types(self):
        for rel_type in PaperRelationType:
            r = PaperRelationship.from_neo4j_record({}, "A", "B", rel_type.name)
            assert r.relation_type == rel_type


# ============================================================================
# v1.1 Relationships
# ============================================================================

class TestCausesRelation:
    def test_instantiation(self):
        r = CausesRelation(
            intervention_name="TLIF",
            complication_name="Dural Tear",
            source_paper_id="P001",
        )
        assert r.intervention_name == "TLIF"
        assert r.complication_name == "Dural Tear"

    def test_defaults(self):
        r = CausesRelation(intervention_name="X", complication_name="Y", source_paper_id="P")
        assert r.incidence_rate == 0.0
        assert r.incidence_ci == ""
        assert r.surgery_type == ""
        assert r.timing == ""

    def test_to_neo4j_properties(self):
        r = CausesRelation(
            intervention_name="OLIF", complication_name="Cage Subsidence",
            source_paper_id="P003", incidence_rate=0.125,
            timing="early",
        )
        props = r.to_neo4j_properties()
        assert props["incidence_rate"] == 0.125
        assert props["timing"] == "early"
        assert props["source_paper_id"] == "P003"

    def test_from_neo4j_record(self):
        record = {
            "source_paper_id": "P005",
            "incidence_rate": 0.05,
            "timing": "late",
            "surgery_type": "primary",
        }
        r = CausesRelation.from_neo4j_record(record, "UBE", "Nerve Injury")
        assert r.intervention_name == "UBE"
        assert r.complication_name == "Nerve Injury"
        assert r.incidence_rate == 0.05
        assert r.surgery_type == "primary"

    def test_from_neo4j_record_empty(self):
        r = CausesRelation.from_neo4j_record({}, "X", "Y")
        assert r.source_paper_id == ""
        assert r.incidence_rate == 0.0


class TestHasRiskFactorRelation:
    def test_instantiation(self):
        r = HasRiskFactorRelation(
            paper_id="P001", risk_factor_name="BMI > 30",
            outcome_affected="Complication Rate",
        )
        assert r.paper_id == "P001"
        assert r.risk_factor_name == "BMI > 30"

    def test_defaults(self):
        r = HasRiskFactorRelation(paper_id="P", risk_factor_name="X", outcome_affected="Y")
        assert r.odds_ratio == 0.0
        assert r.hazard_ratio == 0.0
        assert r.relative_risk == 0.0
        assert r.p_value == 0.0
        assert r.is_independent is False
        assert r.adjusted_for == []

    def test_to_neo4j_properties(self):
        r = HasRiskFactorRelation(
            paper_id="P1", risk_factor_name="Age > 70",
            outcome_affected="PJK",
            odds_ratio=2.5, p_value=0.01, is_independent=True,
            adjusted_for=["BMI", "Smoking"],
        )
        props = r.to_neo4j_properties()
        assert props["odds_ratio"] == 2.5
        assert props["p_value"] == 0.01
        assert props["is_independent"] is True
        assert props["adjusted_for"] == ["BMI", "Smoking"]

    def test_from_neo4j_record(self):
        record = {
            "outcome_affected": "Reoperation",
            "odds_ratio": 3.2,
            "is_independent": True,
            "adjusted_for": ["Age", "BMI"],
        }
        r = HasRiskFactorRelation.from_neo4j_record(record, "P001", "Diabetes")
        assert r.odds_ratio == 3.2
        assert r.is_independent is True
        assert r.adjusted_for == ["Age", "BMI"]


class TestPredictsRelation:
    def test_instantiation(self):
        r = PredictsRelation(
            model_name="PJK Predictor",
            outcome_name="PJK",
            source_paper_id="P001",
        )
        assert r.model_name == "PJK Predictor"

    def test_defaults(self):
        r = PredictsRelation(model_name="M", outcome_name="O", source_paper_id="P")
        assert r.auc == 0.0
        assert r.accuracy == 0.0
        assert r.sensitivity == 0.0
        assert r.specificity == 0.0
        assert r.optimal_threshold == 0.5

    def test_to_neo4j_properties(self):
        r = PredictsRelation(
            model_name="M", outcome_name="O", source_paper_id="P",
            auc=0.85, accuracy=0.8, sensitivity=0.82, specificity=0.88,
        )
        props = r.to_neo4j_properties()
        assert props["auc"] == 0.85
        assert props["accuracy"] == 0.8

    def test_from_neo4j_record(self):
        record = {"source_paper_id": "P1", "auc": 0.92, "optimal_threshold": 0.6}
        r = PredictsRelation.from_neo4j_record(record, "Model1", "Outcome1")
        assert r.auc == 0.92
        assert r.optimal_threshold == 0.6


class TestCorrelatesRelation:
    def test_instantiation(self):
        r = CorrelatesRelation(
            parameter_name="PI-LL mismatch",
            outcome_measure_name="ODI",
        )
        assert r.parameter_name == "PI-LL mismatch"

    def test_defaults(self):
        r = CorrelatesRelation(parameter_name="X", outcome_measure_name="Y")
        assert r.r_value == 0.0
        assert r.p_value == 0.0
        assert r.source_paper_id == ""
        assert r.correlation_type == ""

    def test_to_neo4j_properties(self):
        r = CorrelatesRelation(
            parameter_name="SVA", outcome_measure_name="ODI",
            r_value=0.65, p_value=0.001, correlation_type="positive",
        )
        props = r.to_neo4j_properties()
        assert props["r_value"] == 0.65
        assert props["correlation_type"] == "positive"

    def test_from_neo4j_record(self):
        record = {"r_value": -0.45, "p_value": 0.02, "correlation_type": "negative"}
        r = CorrelatesRelation.from_neo4j_record(record, "PT", "SRS-22")
        assert r.r_value == -0.45
        assert r.correlation_type == "negative"


class TestUsesDeviceRelation:
    def test_instantiation(self):
        r = UsesDeviceRelation(intervention_name="TLIF", device_name="PEEK Cage")
        assert r.intervention_name == "TLIF"
        assert r.device_name == "PEEK Cage"

    def test_defaults(self):
        r = UsesDeviceRelation(intervention_name="X", device_name="Y")
        assert r.usage_type == ""
        assert r.is_required is True

    def test_to_neo4j_properties(self):
        r = UsesDeviceRelation(
            intervention_name="X", device_name="Y",
            usage_type="primary", is_required=False,
        )
        props = r.to_neo4j_properties()
        assert props["usage_type"] == "primary"
        assert props["is_required"] is False

    def test_from_neo4j_record(self):
        record = {"usage_type": "adjunct", "is_required": False}
        r = UsesDeviceRelation.from_neo4j_record(record, "ALIF", "Titanium Cage")
        assert r.usage_type == "adjunct"
        assert r.is_required is False


# ============================================================================
# v1.2 Relationships
# ============================================================================

class TestHasCohortRelation:
    def test_instantiation(self):
        r = HasCohortRelation(paper_id="P001", cohort_name="UBE Group")
        assert r.paper_id == "P001"

    def test_defaults(self):
        r = HasCohortRelation(paper_id="P", cohort_name="C")
        assert r.is_primary is True
        assert r.role == ""

    def test_to_neo4j_properties(self):
        r = HasCohortRelation(paper_id="P1", cohort_name="Control", role="control")
        props = r.to_neo4j_properties()
        assert props["role"] == "control"

    def test_from_neo4j_record(self):
        record = {"is_primary": False, "role": "comparison"}
        r = HasCohortRelation.from_neo4j_record(record, "P1", "Cohort A")
        assert r.is_primary is False
        assert r.role == "comparison"


class TestTreatedWithRelation:
    def test_instantiation(self):
        r = TreatedWithRelation(cohort_name="Group A", intervention_name="TLIF")
        assert r.cohort_name == "Group A"

    def test_defaults(self):
        r = TreatedWithRelation(cohort_name="C", intervention_name="I")
        assert r.source_paper_id == ""
        assert r.n_patients == 0

    def test_to_neo4j_properties(self):
        r = TreatedWithRelation(
            cohort_name="C", intervention_name="ALIF",
            source_paper_id="P1", n_patients=45,
        )
        props = r.to_neo4j_properties()
        assert props["n_patients"] == 45

    def test_from_neo4j_record(self):
        record = {"source_paper_id": "P2", "n_patients": 120}
        r = TreatedWithRelation.from_neo4j_record(record, "Group B", "OLIF")
        assert r.n_patients == 120


class TestHasFollowUpRelation:
    def test_instantiation(self):
        r = HasFollowUpRelation(paper_id="P001", followup_name="6-month")
        assert r.followup_name == "6-month"

    def test_defaults(self):
        r = HasFollowUpRelation(paper_id="P", followup_name="F")
        assert r.is_primary_endpoint is False

    def test_to_neo4j_properties(self):
        r = HasFollowUpRelation(paper_id="P1", followup_name="Final", is_primary_endpoint=True)
        props = r.to_neo4j_properties()
        assert props["is_primary_endpoint"] is True


class TestReportsOutcomeAtRelation:
    def test_instantiation(self):
        r = ReportsOutcomeAtRelation(followup_name="1yr", outcome_name="VAS")
        assert r.followup_name == "1yr"
        assert r.outcome_name == "VAS"

    def test_defaults(self):
        r = ReportsOutcomeAtRelation(followup_name="F", outcome_name="O")
        assert r.source_paper_id == ""
        assert r.value == ""
        assert r.baseline_value == ""
        assert r.improvement == ""

    def test_to_neo4j_truncates(self):
        long_val = "x" * 200
        r = ReportsOutcomeAtRelation(
            followup_name="F", outcome_name="O",
            value=long_val, baseline_value=long_val, improvement=long_val,
        )
        props = r.to_neo4j_properties()
        assert len(props["value"]) == 100
        assert len(props["baseline_value"]) == 100
        assert len(props["improvement"]) == 100


class TestReportsCostRelation:
    def test_instantiation(self):
        r = ReportsCostRelation(paper_id="P001", cost_name="Total Cost")
        assert r.paper_id == "P001"

    def test_defaults(self):
        r = ReportsCostRelation(paper_id="P", cost_name="C")
        assert r.is_primary_analysis is False

    def test_to_neo4j_properties(self):
        r = ReportsCostRelation(paper_id="P1", cost_name="C", is_primary_analysis=True)
        props = r.to_neo4j_properties()
        assert props["is_primary_analysis"] is True


class TestCostAssociatedWithRelation:
    def test_instantiation(self):
        r = CostAssociatedWithRelation(cost_name="Implant Cost", intervention_name="TLIF")
        assert r.cost_name == "Implant Cost"

    def test_defaults(self):
        r = CostAssociatedWithRelation(cost_name="C", intervention_name="I")
        assert r.source_paper_id == ""
        assert r.cost_value == 0.0

    def test_to_neo4j_properties(self):
        r = CostAssociatedWithRelation(
            cost_name="C", intervention_name="I",
            source_paper_id="P1", cost_value=15000.50,
        )
        props = r.to_neo4j_properties()
        assert props["cost_value"] == 15000.50

    def test_from_neo4j_record(self):
        record = {"source_paper_id": "P2", "cost_value": 25000.0}
        r = CostAssociatedWithRelation.from_neo4j_record(record, "Cost1", "ACDF")
        assert r.cost_value == 25000.0


class TestHasQualityMetricRelation:
    def test_instantiation(self):
        r = HasQualityMetricRelation(paper_id="P001", metric_name="GRADE")
        assert r.metric_name == "GRADE"

    def test_defaults(self):
        r = HasQualityMetricRelation(paper_id="P", metric_name="M")
        assert r.assessed_by == ""
        assert r.assessment_type == ""

    def test_to_neo4j_properties(self):
        r = HasQualityMetricRelation(
            paper_id="P1", metric_name="MINORS",
            assessed_by="reviewer", assessment_type="independent",
        )
        props = r.to_neo4j_properties()
        assert props["assessed_by"] == "reviewer"
        assert props["assessment_type"] == "independent"

    def test_from_neo4j_record(self):
        record = {"assessed_by": "author", "assessment_type": "self"}
        r = HasQualityMetricRelation.from_neo4j_record(record, "P1", "Newcastle-Ottawa")
        assert r.assessed_by == "author"
        assert r.assessment_type == "self"
