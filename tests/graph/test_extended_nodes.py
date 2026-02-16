"""Tests for extended_nodes module.

ConceptNode, TechniqueNode, RecommendationNode, InstrumentNode, ImplantNode,
ComplicationNode, DrugNode, SurgicalStepNode, OutcomeMeasureNode,
RadiographicParameterNode, PredictionModelNode, RiskFactorNode,
PatientCohortNode, FollowUpNode, CostNode, QualityMetricNode
dataclass 생성, 기본값 검증, to_neo4j_properties/from_neo4j_record 직렬화 테스트.
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from graph.types.extended_nodes import (
    ConceptNode,
    TechniqueNode,
    RecommendationNode,
    InstrumentNode,
    ImplantNode,
    ComplicationNode,
    DrugNode,
    SurgicalStepNode,
    OutcomeMeasureNode,
    RadiographicParameterNode,
    PredictionModelNode,
    RiskFactorNode,
    PatientCohortNode,
    FollowUpNode,
    CostNode,
    QualityMetricNode,
)


# ===========================================================================
# Test: ConceptNode
# ===========================================================================

class TestConceptNode:
    """ConceptNode dataclass tests."""

    def test_creation(self):
        node = ConceptNode(name="Sagittal Balance")
        assert node.name == "Sagittal Balance"

    def test_default_values(self):
        node = ConceptNode(name="T")
        assert node.category == ""
        assert node.definition == ""
        assert node.keywords == []
        assert node.aliases == []

    def test_to_neo4j_truncation(self):
        node = ConceptNode(name="T", definition="D" * 2000)
        props = node.to_neo4j_properties()
        assert len(props["definition"]) <= 1000

    def test_round_trip(self):
        node = ConceptNode(
            name="Motion Segment", category="biomechanics",
            definition="A functional unit of the spine",
            keywords=["disc", "facet", "ligament"],
        )
        props = node.to_neo4j_properties()
        restored = ConceptNode.from_neo4j_record(props)
        assert restored.name == "Motion Segment"
        assert restored.category == "biomechanics"
        assert "disc" in restored.keywords


# ===========================================================================
# Test: TechniqueNode (Deprecated)
# ===========================================================================

class TestTechniqueNode:
    """TechniqueNode dataclass tests (deprecated but still used)."""

    def test_creation(self):
        node = TechniqueNode(name="Rod Contouring")
        assert node.name == "Rod Contouring"

    def test_default_values(self):
        node = TechniqueNode(name="T")
        assert node.difficulty_level == ""
        assert node.pearls == []
        assert node.pitfalls == []

    def test_round_trip(self):
        node = TechniqueNode(
            name="Pedicle Screw Insertion",
            intervention="TLIF",
            difficulty_level="intermediate",
            pearls=["Use fluoroscopy"],
            pitfalls=["Medial breach"],
        )
        props = node.to_neo4j_properties()
        restored = TechniqueNode.from_neo4j_record(props)
        assert restored.name == "Pedicle Screw Insertion"
        assert restored.difficulty_level == "intermediate"


# ===========================================================================
# Test: RecommendationNode
# ===========================================================================

class TestRecommendationNode:
    """RecommendationNode dataclass tests."""

    def test_creation(self):
        node = RecommendationNode(name="Strong recommendation for decompression")
        assert node.name == "Strong recommendation for decompression"

    def test_default_values(self):
        node = RecommendationNode(name="T")
        assert node.grade == ""
        assert node.strength == ""
        assert node.interventions == []
        assert node.pathologies == []

    def test_truncation(self):
        node = RecommendationNode(
            name="N" * 500,
            full_text="F" * 5000,
        )
        props = node.to_neo4j_properties()
        assert len(props["name"]) <= 200
        assert len(props["full_text"]) <= 2000

    def test_round_trip(self):
        node = RecommendationNode(
            name="Decompression for stenosis",
            grade="A", strength="strong",
            evidence_level="high",
            source_guideline="NASS 2020",
            interventions=["Laminectomy", "UBE"],
        )
        props = node.to_neo4j_properties()
        restored = RecommendationNode.from_neo4j_record(props)
        assert restored.grade == "A"
        assert restored.source_guideline == "NASS 2020"
        assert "UBE" in restored.interventions


# ===========================================================================
# Test: ImplantNode (Consolidated)
# ===========================================================================

class TestImplantNode:
    """ImplantNode dataclass tests."""

    def test_creation(self):
        node = ImplantNode(name="Pedicle Screw")
        assert node.name == "Pedicle Screw"

    def test_default_values(self):
        node = ImplantNode(name="T")
        assert node.device_type == "implant"
        assert node.is_permanent is True
        assert node.is_reusable is False
        assert node.indicated_for == []

    def test_instrument_type(self):
        node = ImplantNode(
            name="Kerrison Rongeur",
            device_type="instrument",
            instrument_category="cutting",
            is_permanent=False,
            is_reusable=True,
        )
        assert node.device_type == "instrument"
        assert node.is_reusable is True

    def test_round_trip(self):
        node = ImplantNode(
            name="PEEK Cage", material="PEEK",
            implant_category="cage",
            fda_status="510k",
            manufacturer="Medtronic",
            indicated_for=["lumbar fusion"],
        )
        props = node.to_neo4j_properties()
        restored = ImplantNode.from_neo4j_record(props)
        assert restored.material == "PEEK"
        assert restored.fda_status == "510k"
        assert "lumbar fusion" in restored.indicated_for


# ===========================================================================
# Test: ComplicationNode
# ===========================================================================

class TestComplicationNode:
    """ComplicationNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = ComplicationNode(name="Dural Tear")
        assert node.name == "Dural Tear"
        assert node.severity == ""
        assert node.incidence_range == ""

    def test_round_trip(self):
        node = ComplicationNode(
            name="Dural Tear", category="intraoperative",
            severity="minor", incidence_range="0.5-3%",
        )
        props = node.to_neo4j_properties()
        restored = ComplicationNode.from_neo4j_record(props)
        assert restored.severity == "minor"
        assert restored.incidence_range == "0.5-3%"


# ===========================================================================
# Test: DrugNode
# ===========================================================================

class TestDrugNode:
    """DrugNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = DrugNode(name="Tranexamic Acid")
        assert node.name == "Tranexamic Acid"
        assert node.brand_names == []
        assert node.indications == []

    def test_round_trip(self):
        node = DrugNode(
            name="BMP-2", generic_name="rhBMP-2",
            category="bone_graft",
            brand_names=["InFuse"],
            indications=["lumbar fusion"],
        )
        props = node.to_neo4j_properties()
        restored = DrugNode.from_neo4j_record(props)
        assert restored.generic_name == "rhBMP-2"
        assert "InFuse" in restored.brand_names


# ===========================================================================
# Test: OutcomeMeasureNode
# ===========================================================================

class TestOutcomeMeasureNode:
    """OutcomeMeasureNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = OutcomeMeasureNode(name="ODI")
        assert node.name == "ODI"
        assert node.scale_min == 0.0
        assert node.scale_max == 100.0
        assert node.mcid == 0.0

    def test_round_trip(self):
        node = OutcomeMeasureNode(
            name="ODI", full_name="Oswestry Disability Index",
            category="patient_reported",
            direction="lower_is_better",
            mcid=12.8,
            validated_for=["lumbar", "cervical"],
        )
        props = node.to_neo4j_properties()
        restored = OutcomeMeasureNode.from_neo4j_record(props)
        assert restored.full_name == "Oswestry Disability Index"
        assert restored.mcid == 12.8
        assert "lumbar" in restored.validated_for


# ===========================================================================
# Test: RadiographicParameterNode
# ===========================================================================

class TestRadiographicParameterNode:
    """RadiographicParameterNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = RadiographicParameterNode(name="PI")
        assert node.name == "PI"
        assert node.is_fixed_parameter is False

    def test_round_trip(self):
        node = RadiographicParameterNode(
            name="PI", full_name="Pelvic Incidence",
            unit="degrees", normal_range="40-65",
            is_fixed_parameter=True,
            correlates_with=["LL", "PT"],
        )
        props = node.to_neo4j_properties()
        restored = RadiographicParameterNode.from_neo4j_record(props)
        assert restored.is_fixed_parameter is True
        assert "LL" in restored.correlates_with


# ===========================================================================
# Test: PredictionModelNode
# ===========================================================================

class TestPredictionModelNode:
    """PredictionModelNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = PredictionModelNode(name="XGBoost Pseudarthrosis")
        assert node.auc == 0.0
        assert node.top_features == []
        assert node.validation_type == ""

    def test_round_trip(self):
        node = PredictionModelNode(
            name="XGBoost Pseudarthrosis",
            model_type="xgboost",
            auc=0.85, accuracy=0.82,
            top_features=["albumin", "BMI", "smoking"],
            validation_type="external",
        )
        props = node.to_neo4j_properties()
        restored = PredictionModelNode.from_neo4j_record(props)
        assert restored.auc == 0.85
        assert "albumin" in restored.top_features


# ===========================================================================
# Test: RiskFactorNode
# ===========================================================================

class TestRiskFactorNode:
    """RiskFactorNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = RiskFactorNode(name="Diabetes")
        assert node.is_modifiable is False
        assert node.typical_or == 0.0

    def test_round_trip(self):
        node = RiskFactorNode(
            name="Smoking", category="lifestyle",
            is_modifiable=True,
            typical_or=2.5,
            optimization_strategy="Cessation 4 weeks prior",
        )
        props = node.to_neo4j_properties()
        restored = RiskFactorNode.from_neo4j_record(props)
        assert restored.is_modifiable is True
        assert restored.typical_or == 2.5


# ===========================================================================
# Test: PatientCohortNode
# ===========================================================================

class TestPatientCohortNode:
    """PatientCohortNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = PatientCohortNode(name="Study Cohort")
        assert node.sample_size == 0
        assert node.mean_age == 0.0

    def test_round_trip(self):
        node = PatientCohortNode(
            name="Intervention Group",
            cohort_type="intervention",
            sample_size=150,
            mean_age=65.3,
            female_percentage=60.0,
            baseline_vas=7.2,
        )
        props = node.to_neo4j_properties()
        restored = PatientCohortNode.from_neo4j_record(props)
        assert restored.sample_size == 150
        assert restored.mean_age == 65.3
        assert restored.baseline_vas == 7.2


# ===========================================================================
# Test: FollowUpNode
# ===========================================================================

class TestFollowUpNode:
    """FollowUpNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = FollowUpNode(name="1-year")
        assert node.timepoint_months == 0
        assert node.fusion_rate == 0.0

    def test_round_trip(self):
        node = FollowUpNode(
            name="2-year", timepoint_months=24,
            fusion_rate=95.2, vas_score=2.1,
            odi_score=18.0,
        )
        props = node.to_neo4j_properties()
        restored = FollowUpNode.from_neo4j_record(props)
        assert restored.timepoint_months == 24
        assert restored.fusion_rate == 95.2


# ===========================================================================
# Test: CostNode
# ===========================================================================

class TestCostNode:
    """CostNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = CostNode(name="Hospital Cost")
        assert node.currency == "USD"
        assert node.mean_cost == 0.0

    def test_round_trip(self):
        node = CostNode(
            name="Total Cost", cost_type="direct",
            mean_cost=45000.0, los_days=3.2,
            qaly_gained=0.15,
        )
        props = node.to_neo4j_properties()
        restored = CostNode.from_neo4j_record(props)
        assert restored.mean_cost == 45000.0
        assert restored.los_days == 3.2


# ===========================================================================
# Test: QualityMetricNode
# ===========================================================================

class TestQualityMetricNode:
    """QualityMetricNode dataclass tests."""

    def test_creation_and_defaults(self):
        node = QualityMetricNode(name="GRADE")
        assert node.overall_score == 0.0
        assert node.jadad_score == 0

    def test_round_trip(self):
        node = QualityMetricNode(
            name="MINORS", assessment_tool="MINORS Score",
            overall_score=18.0, max_score=24.0,
            score_percentage=75.0,
            limitations=["Small sample", "No blinding"],
        )
        props = node.to_neo4j_properties()
        restored = QualityMetricNode.from_neo4j_record(props)
        assert restored.overall_score == 18.0
        assert restored.max_score == 24.0
        assert "Small sample" in restored.limitations


# ===========================================================================
# Test: InstrumentNode (Deprecated)
# ===========================================================================

class TestInstrumentNode:
    """InstrumentNode dataclass tests (deprecated)."""

    def test_creation_and_defaults(self):
        node = InstrumentNode(name="High-speed Drill")
        assert node.category == ""
        assert node.manufacturer == ""

    def test_round_trip(self):
        node = InstrumentNode(
            name="Kerrison Rongeur",
            category="cutting",
            usage="Laminectomy decompression",
        )
        props = node.to_neo4j_properties()
        restored = InstrumentNode.from_neo4j_record(props)
        assert restored.name == "Kerrison Rongeur"
        assert restored.category == "cutting"


# ===========================================================================
# Test: SurgicalStepNode (Deprecated)
# ===========================================================================

class TestSurgicalStepNode:
    """SurgicalStepNode dataclass tests (deprecated)."""

    def test_creation_and_defaults(self):
        node = SurgicalStepNode(name="Exposure")
        assert node.step_number == 0
        assert node.duration_minutes == 0

    def test_round_trip(self):
        node = SurgicalStepNode(
            name="Decompression", intervention="UBE",
            step_number=3, duration_minutes=20,
            critical_points=["Protect nerve root"],
        )
        props = node.to_neo4j_properties()
        restored = SurgicalStepNode.from_neo4j_record(props)
        assert restored.step_number == 3
        assert "Protect nerve root" in restored.critical_points
