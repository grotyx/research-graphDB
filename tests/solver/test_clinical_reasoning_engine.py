"""Tests for ClinicalReasoningEngine module.

추론 로직, 점수 계산, 금기사항 평가, 신뢰도 산출, edge case 테스트.
YAML 규칙 로드 및 LLM/Neo4j 의존성 없이 단독 실행 가능.
"""

import pytest
import yaml
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from solver.clinical_reasoning_engine import (
    ClinicalReasoningEngine,
    Contraindication,
    RiskFactor,
    InterventionScore,
    TreatmentRecommendation,
    RecommendationConfidence,
    create_reasoning_engine,
)
from solver.patient_context_parser import (
    PatientContext,
    Severity,
    AgeGroup,
    FunctionalStatus,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_rules():
    """Sample clinical rules YAML content."""
    return {
        "contraindications": [
            {
                "intervention": "ALIF",
                "condition": "vascular_disease",
                "severity": "absolute",
                "reason": "Major vessel injury risk",
                "mitigation": "",
            },
            {
                "intervention": "ALIF",
                "condition": "retroperitoneal_scarring",
                "severity": "relative",
                "reason": "Difficult access",
                "mitigation": "Consider lateral approach",
            },
            {
                "intervention": "Fusion Surgery",
                "condition": "severe_osteoporosis",
                "severity": "relative",
                "reason": "Screw pullout risk",
                "mitigation": "Consider cement augmentation",
            },
            {
                "intervention": "TLIF",
                "condition": "age > 85",
                "severity": "relative",
                "reason": "High perioperative risk",
                "mitigation": "Consider decompression alone",
            },
        ],
        "pathology_recommendations": {
            "Lumbar Spinal Stenosis": {
                "first_line": [
                    {
                        "name": "Laminectomy",
                        "indication": "Single-level decompression",
                        "evidence_level": "1b",
                    },
                    {
                        "name": "UBE",
                        "indication": "Minimally invasive decompression",
                        "evidence_level": "2a",
                    },
                ],
                "second_line": [
                    {
                        "name": "TLIF",
                        "indication": "With instability",
                        "evidence_level": "2b",
                    },
                ],
            },
        },
        "comorbidity_risk_modifiers": {
            "Diabetes": {
                "infection_risk": 2.0,
                "fusion_rate_reduction": 0.85,
            },
            "Smoking": {
                "infection_risk": 1.5,
                "fusion_rate_reduction": 0.75,
            },
            "Osteoporosis": {
                "hardware_failure": 2.5,
            },
        },
        "severity_modifiers": {
            "mild": {
                "conservative_first": True,
                "min_conservative_weeks": 12,
            },
            "moderate": {
                "conservative_first": True,
                "min_conservative_weeks": 6,
            },
            "severe": {
                "conservative_first": False,
                "urgent_if": ["CES", "progressive_motor_deficit"],
            },
        },
        "outcome_weights_by_age": {
            "young_adult": {
                "pain_relief": 0.2,
                "functional_improvement": 0.2,
                "return_to_work": 0.3,
                "long_term_durability": 0.2,
                "complication_risk": 0.1,
            },
            "elderly": {
                "pain_relief": 0.3,
                "functional_improvement": 0.3,
                "return_to_work": 0.05,
                "long_term_durability": 0.1,
                "complication_risk": 0.25,
            },
        },
        "evidence_requirements": {},
    }


@pytest.fixture
def rules_file(sample_rules, tmp_path):
    """Temporary YAML file with clinical rules."""
    rules_path = tmp_path / "clinical_rules.yaml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump(sample_rules, f, allow_unicode=True)
    return str(rules_path)


@pytest.fixture
def engine(rules_file):
    """ClinicalReasoningEngine with sample rules."""
    return ClinicalReasoningEngine(rules_path=rules_file)


@pytest.fixture
def stenosis_patient():
    """Typical lumbar stenosis patient."""
    return PatientContext(
        age=65, sex="male",
        pathology="Lumbar Spinal Stenosis",
        severity=Severity.MODERATE,
        anatomy_levels=["L4-5"],
        comorbidities=[],
        duration_months=6,
    )


@pytest.fixture
def elderly_diabetic_patient():
    """Elderly patient with comorbidities."""
    return PatientContext(
        age=78, sex="female",
        pathology="Lumbar Spinal Stenosis",
        severity=Severity.SEVERE,
        anatomy_levels=["L3-4", "L4-5"],
        comorbidities=["Diabetes", "Osteoporosis"],
        duration_months=12,
    )


@pytest.fixture
def young_patient():
    """Young adult patient."""
    return PatientContext(
        age=35, sex="male",
        pathology="Lumbar Spinal Stenosis",
        severity=Severity.MODERATE,
        anatomy_levels=["L5-S1"],
    )


@pytest.fixture
def vascular_patient():
    """Patient with vascular disease (ALIF contraindication)."""
    return PatientContext(
        age=60, sex="male",
        pathology="Lumbar Spinal Stenosis",
        severity=Severity.MODERATE,
        comorbidities=["vascular disease"],
    )


# ===========================================================================
# Test: Contraindication Dataclass
# ===========================================================================

class TestContraindication:
    """Contraindication dataclass tests."""

    def test_absolute_contraindication(self):
        ci = Contraindication(
            intervention="ALIF", condition="vascular disease",
            severity="absolute", reason="Vessel injury risk",
        )
        assert ci.is_absolute is True

    def test_relative_contraindication(self):
        ci = Contraindication(
            intervention="TLIF", condition="osteoporosis",
            severity="relative",
        )
        assert ci.is_absolute is False


# ===========================================================================
# Test: InterventionScore Dataclass
# ===========================================================================

class TestInterventionScore:
    """InterventionScore dataclass tests."""

    def test_no_contraindications(self):
        score = InterventionScore(intervention="UBE", total_score=0.8)
        assert score.has_absolute_contraindication() is False
        assert score.get_absolute_contraindications() == []
        assert score.get_relative_contraindications() == []

    def test_with_absolute_contraindication(self):
        ci = Contraindication(
            intervention="ALIF", condition="vascular disease",
            severity="absolute",
        )
        score = InterventionScore(
            intervention="ALIF", total_score=0.0,
            contraindications=[ci],
        )
        assert score.has_absolute_contraindication() is True
        assert len(score.get_absolute_contraindications()) == 1

    def test_mixed_contraindications(self):
        abs_ci = Contraindication(intervention="X", condition="A", severity="absolute")
        rel_ci = Contraindication(intervention="X", condition="B", severity="relative")
        score = InterventionScore(
            intervention="X", total_score=0.0,
            contraindications=[abs_ci, rel_ci],
        )
        assert len(score.get_absolute_contraindications()) == 1
        assert len(score.get_relative_contraindications()) == 1

    def test_total_risk_multiplier_no_factors(self):
        score = InterventionScore(intervention="T", total_score=0.5)
        assert score.get_total_risk_multiplier() == 1.0

    def test_total_risk_multiplier_with_factors(self):
        rf1 = RiskFactor(name="DM", risk_type="infection", multiplier=2.0, source="Diabetes")
        rf2 = RiskFactor(name="Smoke", risk_type="fusion", multiplier=1.5, source="Smoking")
        score = InterventionScore(
            intervention="T", total_score=0.5,
            risk_factors=[rf1, rf2],
        )
        assert score.get_total_risk_multiplier() == pytest.approx(3.0, rel=1e-6)


# ===========================================================================
# Test: TreatmentRecommendation
# ===========================================================================

class TestTreatmentRecommendation:
    """TreatmentRecommendation dataclass tests."""

    def test_get_top_recommendation_empty(self):
        rec = TreatmentRecommendation(
            patient_context=PatientContext(),
            recommended_interventions=[],
            alternative_interventions=[],
            contraindicated_interventions=[],
        )
        assert rec.get_top_recommendation() is None

    def test_get_top_recommendation(self):
        top = InterventionScore(intervention="UBE", total_score=0.9)
        alt = InterventionScore(intervention="TLIF", total_score=0.6)
        rec = TreatmentRecommendation(
            patient_context=PatientContext(),
            recommended_interventions=[top, alt],
            alternative_interventions=[],
            contraindicated_interventions=[],
        )
        assert rec.get_top_recommendation().intervention == "UBE"

    def test_get_summary_no_recommendation(self):
        rec = TreatmentRecommendation(
            patient_context=PatientContext(),
            recommended_interventions=[],
            alternative_interventions=[],
            contraindicated_interventions=[],
        )
        assert "No suitable" in rec.get_summary()

    def test_get_summary_with_recommendation(self):
        top = InterventionScore(
            intervention="UBE", total_score=0.9, evidence_level="1b",
        )
        rec = TreatmentRecommendation(
            patient_context=PatientContext(),
            recommended_interventions=[top],
            alternative_interventions=[],
            contraindicated_interventions=[],
            confidence=RecommendationConfidence.HIGH,
        )
        summary = rec.get_summary()
        assert "UBE" in summary
        assert "HIGH" in summary
        assert "Level 1b" in summary


# ===========================================================================
# Test: Engine Initialization
# ===========================================================================

class TestEngineInitialization:
    """ClinicalReasoningEngine initialization tests."""

    def test_init_with_rules_file(self, engine):
        assert engine.rules is not None
        assert len(engine.contraindications_list) > 0
        assert "Lumbar Spinal Stenosis" in engine.pathology_recommendations

    def test_init_with_missing_file(self, tmp_path):
        missing_path = str(tmp_path / "nonexistent.yaml")
        engine = ClinicalReasoningEngine(rules_path=missing_path)
        assert engine.rules == {}

    def test_factory_function(self, rules_file):
        engine = create_reasoning_engine(rules_path=rules_file)
        assert isinstance(engine, ClinicalReasoningEngine)


# ===========================================================================
# Test: Candidate Intervention Selection
# ===========================================================================

class TestCandidateSelection:
    """Candidate intervention selection tests."""

    def test_candidates_from_pathology(self, engine, stenosis_patient):
        candidates = engine._get_candidate_interventions(stenosis_patient)
        assert "Laminectomy" in candidates
        assert "UBE" in candidates
        assert "TLIF" in candidates

    def test_default_candidates_for_unknown_pathology(self, engine):
        patient = PatientContext(pathology="UnknownDisease")
        candidates = engine._get_candidate_interventions(patient)
        assert len(candidates) > 0
        assert "TLIF" in candidates  # Default list includes TLIF


# ===========================================================================
# Test: Contraindication Checking
# ===========================================================================

class TestContraindicationChecking:
    """Contraindication evaluation tests."""

    def test_absolute_contraindication_detected(self, engine, vascular_patient):
        contras = engine._check_contraindications("ALIF", vascular_patient)
        absolute = [c for c in contras if c.is_absolute]
        assert len(absolute) >= 1
        assert any("vascular" in c.condition.lower() for c in absolute)

    def test_no_contraindication_for_healthy_patient(self, engine, stenosis_patient):
        contras = engine._check_contraindications("UBE", stenosis_patient)
        assert len(contras) == 0

    def test_fusion_surgery_matching(self, engine):
        """'Fusion Surgery' rule should match TLIF, PLIF, etc."""
        patient = PatientContext(comorbidities=["severe osteoporosis"])
        contras = engine._check_contraindications("TLIF", patient)
        # Should match "Fusion Surgery" -> severe_osteoporosis
        osteo_contras = [c for c in contras if "osteoporosis" in c.condition.lower()]
        assert len(osteo_contras) >= 1

    def test_age_based_contraindication(self, engine):
        patient = PatientContext(age=90)
        contras = engine._check_contraindications("TLIF", patient)
        age_contras = [c for c in contras if "age" in c.condition.lower()]
        assert len(age_contras) >= 1


# ===========================================================================
# Test: Risk Factor Calculation
# ===========================================================================

class TestRiskFactorCalculation:
    """Risk factor calculation tests."""

    def test_no_comorbidities(self, engine, stenosis_patient):
        factors = engine._calculate_risk_factors("TLIF", stenosis_patient)
        assert len(factors) == 0

    def test_diabetes_risk_factors(self, engine, elderly_diabetic_patient):
        factors = engine._calculate_risk_factors("TLIF", elderly_diabetic_patient)
        infection_factors = [f for f in factors if f.risk_type == "infection_risk"]
        assert len(infection_factors) >= 1
        assert infection_factors[0].multiplier == 2.0

    def test_comorbidity_normalization(self, engine):
        assert engine._normalize_comorbidity_key("dm") == "Diabetes"
        assert engine._normalize_comorbidity_key("htn") == "Hypertension"
        assert engine._normalize_comorbidity_key("당뇨") == "Diabetes"
        assert engine._normalize_comorbidity_key("smoking") == "Smoking"
        assert engine._normalize_comorbidity_key("unknown") == "unknown"


# ===========================================================================
# Test: Evidence Score Calculation
# ===========================================================================

class TestEvidenceScoreCalculation:
    """Evidence score calculation tests."""

    def test_no_evidence(self, engine):
        score, supporting = engine._calculate_evidence_score("TLIF", [])
        assert score == 0.3  # Default score when no evidence
        assert supporting == []

    def test_high_level_evidence(self, engine):
        evidence = [
            {"intervention": "TLIF", "evidence_level": "1b", "is_significant": True},
        ]
        score, supporting = engine._calculate_evidence_score("TLIF", evidence)
        assert score > 0.5
        assert len(supporting) == 1

    def test_low_level_evidence(self, engine):
        evidence = [
            {"intervention": "TLIF", "evidence_level": "5", "is_significant": False},
        ]
        score, supporting = engine._calculate_evidence_score("TLIF", evidence)
        assert score < 0.5

    def test_irrelevant_evidence_ignored(self, engine):
        evidence = [
            {"intervention": "ALIF", "evidence_level": "1b", "is_significant": True},
        ]
        score, supporting = engine._calculate_evidence_score("TLIF", evidence)
        assert len(supporting) == 0
        assert score == 0.3  # No relevant evidence


# ===========================================================================
# Test: Patient Fit Calculation
# ===========================================================================

class TestPatientFitCalculation:
    """Patient fit score calculation tests."""

    def test_young_adult_fit(self, engine, young_patient):
        score = engine._calculate_patient_fit("TLIF", young_patient, [])
        assert 0.0 <= score <= 1.0

    def test_elderly_fit(self, engine, elderly_diabetic_patient):
        score = engine._calculate_patient_fit("TLIF", elderly_diabetic_patient, [])
        assert 0.0 <= score <= 1.0

    def test_unknown_age_group_defaults(self, engine):
        patient = PatientContext()  # No age
        score = engine._calculate_patient_fit("TLIF", patient, [])
        assert score == 0.5  # Default


# ===========================================================================
# Test: Full Recommendation Pipeline
# ===========================================================================

class TestRecommendPipeline:
    """Full recommend_treatment pipeline tests."""

    def test_basic_recommendation(self, engine, stenosis_patient):
        rec = engine.recommend_treatment(stenosis_patient)
        assert isinstance(rec, TreatmentRecommendation)
        assert len(rec.recommended_interventions) > 0
        assert rec.patient_summary != ""

    def test_recommendation_with_evidence(self, engine, stenosis_patient):
        evidence = [
            {"intervention": "UBE", "evidence_level": "2a",
             "is_significant": True, "outcome": "VAS", "direction": "improved"},
            {"intervention": "Laminectomy", "evidence_level": "1b",
             "is_significant": True, "outcome": "ODI", "direction": "improved"},
        ]
        rec = engine.recommend_treatment(stenosis_patient, evidence)
        assert rec.total_evidence_count == 2
        assert rec.significant_evidence_count == 2

    def test_contraindicated_separated(self, engine, vascular_patient):
        """ALIF should be contraindicated for vascular disease patient."""
        # ALIF is in default interventions when pathology is not mapped
        vascular_patient.pathology = "unknown"
        rec = engine.recommend_treatment(vascular_patient)
        contraindicated_names = [
            s.intervention for s in rec.contraindicated_interventions
        ]
        assert "ALIF" in contraindicated_names

    def test_first_line_gets_bonus(self, engine, stenosis_patient):
        assert engine._is_first_line("Laminectomy", "Lumbar Spinal Stenosis") is True
        assert engine._is_first_line("TLIF", "Lumbar Spinal Stenosis") is False

    def test_indication_info(self, engine):
        indication, level = engine._get_indication_info(
            "UBE", "Lumbar Spinal Stenosis"
        )
        assert indication == "Minimally invasive decompression"
        assert level == "2a"

    def test_empty_pathology_indication(self, engine):
        indication, level = engine._get_indication_info("TLIF", "")
        assert indication == ""
        assert level == ""


# ===========================================================================
# Test: Confidence Evaluation
# ===========================================================================

class TestConfidenceEvaluation:
    """Confidence evaluation tests."""

    def test_no_recommendations_uncertain(self, engine, stenosis_patient):
        confidence, reasons = engine._evaluate_confidence(
            stenosis_patient, [], []
        )
        assert confidence == RecommendationConfidence.UNCERTAIN

    def test_confidence_with_high_evidence(self, engine, stenosis_patient):
        top = InterventionScore(
            intervention="UBE", total_score=0.9,
            evidence_level="1b", safety_score=0.9,
        )
        evidence = [
            {"is_significant": True} for _ in range(5)
        ]
        confidence, reasons = engine._evaluate_confidence(
            stenosis_patient, [top], evidence
        )
        # With high evidence, high safety, and complete patient info
        assert confidence in [RecommendationConfidence.HIGH, RecommendationConfidence.MODERATE]

    def test_confidence_low_when_limited_info(self, engine):
        patient = PatientContext()  # No info
        top = InterventionScore(
            intervention="UBE", total_score=0.5,
            evidence_level="5", safety_score=0.4,
        )
        confidence, _ = engine._evaluate_confidence(patient, [top], [])
        assert confidence in [RecommendationConfidence.LOW, RecommendationConfidence.UNCERTAIN]


# ===========================================================================
# Test: Patient Summary Generation
# ===========================================================================

class TestPatientSummary:
    """Patient summary generation tests."""

    def test_full_summary(self, engine, stenosis_patient):
        summary = engine._generate_patient_summary(stenosis_patient)
        assert "65" in summary
        assert "Lumbar Spinal Stenosis" in summary
        assert "L4-5" in summary

    def test_empty_patient_summary(self, engine):
        patient = PatientContext()
        summary = engine._generate_patient_summary(patient)
        assert summary == "환자 정보 부족"

    def test_summary_with_comorbidities(self, engine, elderly_diabetic_patient):
        summary = engine._generate_patient_summary(elderly_diabetic_patient)
        assert "Diabetes" in summary
        assert "Osteoporosis" in summary

    def test_summary_sex_display(self, engine):
        patient = PatientContext(age=50, sex="female")
        summary = engine._generate_patient_summary(patient)
        assert "여성" in summary


# ===========================================================================
# Test: Considerations and Warnings
# ===========================================================================

class TestConsiderationsAndWarnings:
    """Considerations and warnings generation tests."""

    def test_elderly_consideration(self, engine):
        patient = PatientContext(age=80)
        considerations = engine._generate_considerations(patient, [])
        assert any("고령" in c for c in considerations)

    def test_young_consideration(self, engine):
        patient = PatientContext(age=30)
        considerations = engine._generate_considerations(patient, [])
        assert any("젊은" in c for c in considerations)

    def test_comorbidity_warning(self, engine, elderly_diabetic_patient):
        rec = engine.recommend_treatment(elderly_diabetic_patient)
        # Should have considerations about diabetes infection risk
        has_diabetes_consideration = any(
            "감염" in c or "infection" in c.lower()
            for c in rec.considerations
        )
        assert has_diabetes_consideration

    def test_relative_contraindication_warning(self, engine):
        ci = Contraindication(
            intervention="TLIF", condition="osteoporosis",
            severity="relative", mitigation="Use cement augmentation",
        )
        score = InterventionScore(
            intervention="TLIF", total_score=0.5,
            contraindications=[ci],
        )
        patient = PatientContext()
        warnings = engine._generate_warnings(patient, [score])
        assert len(warnings) >= 1
        assert "cement augmentation" in warnings[0] or "osteoporosis" in warnings[0]


# ===========================================================================
# Test: Intervention Matching
# ===========================================================================

class TestInterventionMatching:
    """Intervention name matching tests."""

    def test_exact_match(self, engine):
        assert engine._intervention_matches("ALIF", "ALIF") is True

    def test_case_insensitive_match(self, engine):
        assert engine._intervention_matches("alif", "ALIF") is True

    def test_fusion_surgery_matches_tlif(self, engine):
        assert engine._intervention_matches("TLIF", "Fusion Surgery") is True

    def test_fusion_surgery_matches_plif(self, engine):
        assert engine._intervention_matches("PLIF", "Fusion Surgery") is True

    def test_no_match(self, engine):
        assert engine._intervention_matches("UBE", "ALIF") is False


# ===========================================================================
# Test: Condition Evaluation
# ===========================================================================

class TestConditionEvaluation:
    """Condition evaluation tests."""

    def test_age_greater_than(self, engine):
        patient = PatientContext(age=90)
        assert engine._evaluate_condition("age > 85", patient) is True

    def test_age_not_greater_than(self, engine):
        patient = PatientContext(age=60)
        assert engine._evaluate_condition("age > 85", patient) is False

    def test_age_none(self, engine):
        patient = PatientContext()
        assert engine._evaluate_condition("age > 85", patient) is False

    def test_comorbidity_condition(self, engine):
        patient = PatientContext(comorbidities=["vascular disease"])
        assert engine._evaluate_condition("vascular_disease", patient) is True

    def test_unknown_condition(self, engine):
        patient = PatientContext()
        assert engine._evaluate_condition("unknown_bizarre_condition", patient) is False
