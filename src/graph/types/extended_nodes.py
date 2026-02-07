"""Spine Graph Extended Node Types (v7.x).

This module contains extended entity node types for the Spine GraphRAG system.
These nodes supplement the core nodes (Paper, Pathology, Intervention, Outcome)
with additional entities for comprehensive medical knowledge representation.

Extended node types include:
- ConceptNode: Educational concepts from textbooks
- TechniqueNode: Surgical techniques (DEPRECATED - use InterventionNode)
- RecommendationNode: Clinical guideline recommendations
- InstrumentNode: Surgical instruments (DEPRECATED - use ImplantNode)
- ImplantNode: Implants and devices (consolidated with InstrumentNode)
- ComplicationNode: Surgical complications
- DrugNode: Pharmacological agents
- SurgicalStepNode: Surgical procedure steps (DEPRECATED - use InterventionNode)
- OutcomeMeasureNode: Standardized outcome measurement tools
- RadiographicParameterNode: Radiographic and alignment parameters
- PredictionModelNode: ML/AI prediction models
- RiskFactorNode: Patient risk factors
- PatientCohortNode: Patient cohort characteristics
- FollowUpNode: Follow-up timepoint data
- CostNode: Healthcare cost analysis data
- QualityMetricNode: Study quality assessment metrics

Author: Spine GraphRAG Team
Version: 7.2
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConceptNode:
    """개념 노드 (교과서/교육용 - v7.1).

    Neo4j Label: Concept

    교과서, 백과사전, 교육 자료에서 추출한 핵심 개념.
    예: "Sagittal Balance", "Motion Segment", "Fusion Biology"

    Relationships:
        - (Paper)-[:DEFINES]->(Concept)
        - (Concept)-[:RELATED_TO]->(Concept)
        - (Concept)-[:APPLIES_TO]->(Pathology|Intervention)
    """
    name: str  # Sagittal Balance, Motion Segment
    category: str = ""  # biomechanics, anatomy, physiology, pathophysiology
    definition: str = ""  # 정의 텍스트
    importance: str = ""  # clinical, theoretical, both
    keywords: list[str] = field(default_factory=list)
    snomed_code: str = ""
    aliases: list[str] = field(default_factory=list)

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "definition": self.definition[:1000] if self.definition else "",
            "importance": self.importance,
            "keywords": self.keywords[:10],
            "snomed_code": self.snomed_code,
            "aliases": self.aliases[:10],
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "ConceptNode":
        return cls(
            name=record.get("name", ""),
            category=record.get("category", ""),
            definition=record.get("definition", ""),
            importance=record.get("importance", ""),
            keywords=record.get("keywords", []),
            snomed_code=record.get("snomed_code", ""),
            aliases=record.get("aliases", []),
        )


@dataclass
class TechniqueNode:
    """수술 테크닉 노드 (v7.1).

    Neo4j Label: Technique

    DEPRECATED: This node type is deprecated in favor of InterventionNode.technique_description
    and InterventionNode.surgical_steps fields. Use InterventionNode with the extended fields instead.

    nt)
    """
    name: str  # Rod Contouring, Pedicle Screw Insertion
    description: str = ""  # 테크닉 설명
    intervention: str = ""  # 관련 수술 (TLIF, OLIF 등)
    difficulty_level: str = ""  # basic, intermediate, advanced
    pearls: list[str] = field(default_factory=list)  # 수술 팁
    pitfalls: list[str] = field(default_factory=list)  # 주의사항
    video_link: str = ""  # 관련 영상 링크

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "description": self.description[:2000] if self.description else "",
            "intervention": self.intervention,
            "difficulty_level": self.difficulty_level,
            "pearls": self.pearls[:10],
            "pitfalls": self.pitfalls[:10],
            "video_link": self.video_link,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "TechniqueNode":
        return cls(
            name=record.get("name", ""),
            description=record.get("description", ""),
            intervention=record.get("intervention", ""),
            difficulty_level=record.get("difficulty_level", ""),
            pearls=record.get("pearls", []),
            pitfalls=record.get("pitfalls", []),
            video_link=record.get("video_link", ""),
        )


@dataclass
class RecommendationNode:
    """권고사항 노드 (가이드라인용 - v7.1).

    Neo4j Label: Recommendation

    임상 가이드라인의 권고사항.
    예: "Strong recommendation for surgical decompression in severe stenosis"

    Relationships:
        - (Paper)-[:RECOMMENDS]->(Recommendation)
        - (Recommendation)-[:FOR_PATHOLOGY]->(Pathology)
        - (Recommendation)-[:SUGGESTS_INTERVENTION]->(Intervention)
    """
    name: str  # 권고사항 요약
    full_text: str = ""  # 전체 권고사항 텍스트
    grade: str = ""  # A, B, C, D, I (Insufficient)
    strength: str = ""  # strong, moderate, weak, conditional
    evidence_level: str = ""  # high, moderate, low, very_low
    source_guideline: str = ""  # NASS 2020, AAOS 2019
    target_population: str = ""  # 대상 환자군
    interventions: list[str] = field(default_factory=list)  # 관련 수술/치료
    pathologies: list[str] = field(default_factory=list)  # 관련 질환

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name[:200] if self.name else "",
            "full_text": self.full_text[:2000] if self.full_text else "",
            "grade": self.grade,
            "strength": self.strength,
            "evidence_level": self.evidence_level,
            "source_guideline": self.source_guideline,
            "target_population": self.target_population[:500] if self.target_population else "",
            "interventions": self.interventions[:10],
            "pathologies": self.pathologies[:10],
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "RecommendationNode":
        return cls(
            name=record.get("name", ""),
            full_text=record.get("full_text", ""),
            grade=record.get("grade", ""),
            strength=record.get("strength", ""),
            evidence_level=record.get("evidence_level", ""),
            source_guideline=record.get("source_guideline", ""),
            target_population=record.get("target_population", ""),
            interventions=record.get("interventions", []),
            pathologies=record.get("pathologies", []),
        )


@dataclass
class InstrumentNode:
    """수술 기구 노드 (v7.1).

    ⚠️ DEPRECATED: Use ImplantNode with device_type="instrument" instead.
    This class is maintained for backward compatibility only.

    Neo4j Label: Instrument

    수술에 사용되는 기구.
    예: "Kerrison Rongeur", "High-speed Drill", "Endoscope"

    Relationships:
        - (Intervention)-[:USES_INSTRUMENT]->(Instrument)
        - (Technique)-[:REQUIRES]->(Instrument)
    """
    name: str  # Kerrison Rongeur, High-speed Drill
    category: str = ""  # cutting, grasping, retracting, visualization
    manufacturer: str = ""  # 제조사
    description: str = ""  # 설명
    usage: str = ""  # 용도
    image_url: str = ""  # 이미지 링크

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "description": self.description[:500] if self.description else "",
            "usage": self.usage[:500] if self.usage else "",
            "image_url": self.image_url,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "InstrumentNode":
        return cls(
            name=record.get("name", ""),
            category=record.get("category", ""),
            manufacturer=record.get("manufacturer", ""),
            description=record.get("description", ""),
            usage=record.get("usage", ""),
            image_url=record.get("image_url", ""),
        )


@dataclass
class ImplantNode:
    """임플란트/기기 통합 노드 (v7.1 - Consolidated with InstrumentNode).

    Neo4j Label: Implant (alias: Device)

    척추 수술에 사용되는 임플란트 및 수술 기구를 통합한 노드.
    예: "Pedicle Screw", "PEEK Cage", "Artificial Disc", "Kerrison Rongeur"

    Relationships:
        - (Intervention)-[:USES_DEVICE]->(Implant)
        - (Implant)-[:INDICATED_FOR]->(Pathology)
    """
    name: str  # Pedicle Screw, PEEK Cage, Kerrison Rongeur

    # Device Type Classification (NEW in v7.1)
    device_type: str = "implant"  # "implant" | "instrument" | "consumable"

    # Implant-specific fields
    implant_category: str = ""  # screw, cage, rod, plate, disc, graft (renamed from 'category')
    material: str = ""  # titanium, PEEK, cobalt-chrome, stainless_steel

    # Instrument-specific fields (NEW in v7.1)
    instrument_category: str = ""  # cutting, grasping, retracting, visualization, power

    # Device properties
    is_permanent: bool = True  # Implant stays in body (vs temporary instrument)
    is_reusable: bool = False  # Instrument reusability (NEW in v7.1)

    # Regulatory information
    fda_status: str = ""  # approved, 510k, pma, investigational
    fda_clearance_year: int = 0
    fda_product_code: str = ""
    gmdn_code: str = ""  # Global Medical Device Nomenclature (NEW in v7.1)

    # Commercial information
    manufacturer: str = ""  # Medtronic, DePuy, Stryker
    product_name: str = ""  # Specific product name (NEW in v7.1)

    # Clinical usage
    indicated_for: list[str] = field(default_factory=list)  # ["lumbar fusion", "cervical fixation"]
    contraindicated_for: list[str] = field(default_factory=list)  # NEW in v7.1

    # Biomechanical properties
    elastic_modulus: str = ""  # "114 GPa for titanium" (NEW in v7.1)

    # General information
    description: str = ""  # 설명
    usage: str = ""  # 용도 (from InstrumentNode)
    image_url: str = ""  # 이미지 링크 (from InstrumentNode)

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "device_type": self.device_type,
            "implant_category": self.implant_category,
            "material": self.material,
            "instrument_category": self.instrument_category,
            "is_permanent": self.is_permanent,
            "is_reusable": self.is_reusable,
            "fda_status": self.fda_status,
            "fda_clearance_year": self.fda_clearance_year,
            "fda_product_code": self.fda_product_code,
            "gmdn_code": self.gmdn_code,
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "indicated_for": self.indicated_for[:20],  # Limit array size
            "contraindicated_for": self.contraindicated_for[:20],
            "elastic_modulus": self.elastic_modulus,
            "description": self.description[:500] if self.description else "",
            "usage": self.usage[:500] if self.usage else "",
            "image_url": self.image_url,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "ImplantNode":
        return cls(
            name=record.get("name", ""),
            device_type=record.get("device_type", "implant"),
            implant_category=record.get("implant_category", ""),
            material=record.get("material", ""),
            instrument_category=record.get("instrument_category", ""),
            is_permanent=record.get("is_permanent", True),
            is_reusable=record.get("is_reusable", False),
            fda_status=record.get("fda_status", ""),
            fda_clearance_year=record.get("fda_clearance_year", 0),
            fda_product_code=record.get("fda_product_code", ""),
            gmdn_code=record.get("gmdn_code", ""),
            manufacturer=record.get("manufacturer", ""),
            product_name=record.get("product_name", ""),
            indicated_for=record.get("indicated_for", []),
            contraindicated_for=record.get("contraindicated_for", []),
            elastic_modulus=record.get("elastic_modulus", ""),
            description=record.get("description", ""),
            usage=record.get("usage", ""),
            image_url=record.get("image_url", ""),
        )


@dataclass
class ComplicationNode:
    """합병증 노드 (v7.1).

    Neo4j Label: Complication

    수술 관련 합병증.
    예: "Dural Tear", "Screw Malposition", "Adjacent Segment Disease"

    Relationships:
        - (Intervention)-[:CAUSES]->(Complication)
        - (Paper)-[:REPORTS_COMPLICATION]->(Complication)
    """
    name: str  # Dural Tear, Screw Malposition
    category: str = ""  # intraoperative, early_postop, late_postop
    severity: str = ""  # minor, major, catastrophic
    incidence_range: str = ""  # "0.5-3%" 범위
    prevention: str = ""  # 예방법
    management: str = ""  # 대처법
    snomed_code: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "incidence_range": self.incidence_range,
            "prevention": self.prevention[:500] if self.prevention else "",
            "management": self.management[:500] if self.management else "",
            "snomed_code": self.snomed_code,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "ComplicationNode":
        return cls(
            name=record.get("name", ""),
            category=record.get("category", ""),
            severity=record.get("severity", ""),
            incidence_range=record.get("incidence_range", ""),
            prevention=record.get("prevention", ""),
            management=record.get("management", ""),
            snomed_code=record.get("snomed_code", ""),
        )


@dataclass
class DrugNode:
    """약물 노드 (v7.1).

    Neo4j Label: Drug

    척추 치료에 사용되는 약물.
    예: "Methylprednisolone", "Tranexamic Acid", "BMP-2"

    Relationships:
        - (Paper)-[:INVESTIGATES_DRUG]->(Drug)
        - (Drug)-[:TREATS]->(Pathology)
        - (Drug)-[:USED_WITH]->(Intervention)
    """
    name: str  # Methylprednisolone, Tranexamic Acid
    generic_name: str = ""  # 일반명
    brand_names: list[str] = field(default_factory=list)  # 상품명
    category: str = ""  # steroid, analgesic, bone_graft, antibiotic
    mechanism: str = ""  # 작용 기전
    indications: list[str] = field(default_factory=list)  # 적응증
    contraindications: list[str] = field(default_factory=list)  # 금기
    rxnorm_code: str = ""  # RxNorm 코드

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "generic_name": self.generic_name,
            "brand_names": self.brand_names[:5],
            "category": self.category,
            "mechanism": self.mechanism[:500] if self.mechanism else "",
            "indications": self.indications[:10],
            "contraindications": self.contraindications[:10],
            "rxnorm_code": self.rxnorm_code,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "DrugNode":
        return cls(
            name=record.get("name", ""),
            generic_name=record.get("generic_name", ""),
            brand_names=record.get("brand_names", []),
            category=record.get("category", ""),
            mechanism=record.get("mechanism", ""),
            indications=record.get("indications", []),
            contraindications=record.get("contraindications", []),
            rxnorm_code=record.get("rxnorm_code", ""),
        )


@dataclass
class SurgicalStepNode:
    """수술 단계 노드 (v7.1).

    Neo4j Label: SurgicalStep

    DEPRECATED: This node type is deprecated in favor of InterventionNode.surgical_steps field.
    Use InterventionNode with the surgical_steps list field instead:
    surgical_steps = [{"step": 1, "name": "...", "description": "...", "duration_minutes": ...}]

    nt)
    """
    name: str  # Exposure, Decompression
    intervention: str = ""  # 관련 수술
    step_number: int = 0  # 순서
    description: str = ""  # 상세 설명
    duration_minutes: int = 0  # 예상 시간
    critical_points: list[str] = field(default_factory=list)  # 주의사항
    instruments: list[str] = field(default_factory=list)  # 필요 기구

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "intervention": self.intervention,
            "step_number": self.step_number,
            "description": self.description[:1000] if self.description else "",
            "duration_minutes": self.duration_minutes,
            "critical_points": self.critical_points[:10],
            "instruments": self.instruments[:10],
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "SurgicalStepNode":
        return cls(
            name=record.get("name", ""),
            intervention=record.get("intervention", ""),
            step_number=record.get("step_number", 0),
            description=record.get("description", ""),
            duration_minutes=record.get("duration_minutes", 0),
            critical_points=record.get("critical_points", []),
            instruments=record.get("instruments", []),
        )


@dataclass
class OutcomeMeasureNode:
    """Patient-Reported & Clinical Outcome Measures (v7.1).

    Neo4j Label: OutcomeMeasure

    VAS, ODI, SF-36, NDI, PROMIS, JOA 등 표준화된 결과 측정 도구.
    기존 OutcomeNode와 별개로 "측정 도구" 자체를 표현.

    Examples:
        - ODI (Oswestry Disability Index): 0-100 scale, lower is better
        - VAS (Visual Analog Scale): 0-100mm, lower is better
        - SF-36 PCS: 0-100, higher is better

    Relationships:
        - (Outcome)-[:MEASURED_BY]->(OutcomeMeasure)
        - (Paper)-[:USES_MEASURE]->(OutcomeMeasure)
    """
    name: str  # ODI, VAS, SF-36, PROMIS-29
    full_name: str = ""  # Oswestry Disability Index
    category: str = ""  # patient_reported, clinical, functional, radiographic

    # Measurement Properties
    scale_min: float = 0.0  # 최소값 (e.g., 0)
    scale_max: float = 100.0  # 최대값 (e.g., 100)
    direction: str = ""  # higher_is_better, lower_is_better
    unit: str = ""  # points, %, mm

    # Interpretation
    mcid: float = 0.0  # Minimal Clinically Important Difference
    mcid_range: str = ""  # "12-17 points"
    interpretation_guide: str = ""  # "0-20: Minimal disability, 21-40: Moderate..."

    # Validity
    domains_measured: list[str] = field(default_factory=list)  # ["pain", "function", "quality_of_life"]
    validated_for: list[str] = field(default_factory=list)  # ["lumbar", "cervical", "deformity"]
    average_completion_time: int = 0  # seconds

    # References
    original_citation: str = ""  # "Fairbank et al., 1980"
    snomed_code: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name[:500] if self.full_name else "",
            "category": self.category,
            "scale_min": self.scale_min,
            "scale_max": self.scale_max,
            "direction": self.direction,
            "unit": self.unit[:50] if self.unit else "",
            "mcid": self.mcid,
            "mcid_range": self.mcid_range[:100] if self.mcid_range else "",
            "interpretation_guide": self.interpretation_guide[:1000] if self.interpretation_guide else "",
            "domains_measured": self.domains_measured[:20],
            "validated_for": self.validated_for[:20],
            "average_completion_time": self.average_completion_time,
            "original_citation": self.original_citation[:500] if self.original_citation else "",
            "snomed_code": self.snomed_code[:50] if self.snomed_code else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "OutcomeMeasureNode":
        return cls(
            name=record.get("name", ""),
            full_name=record.get("full_name", ""),
            category=record.get("category", ""),
            scale_min=record.get("scale_min", 0.0),
            scale_max=record.get("scale_max", 100.0),
            direction=record.get("direction", ""),
            unit=record.get("unit", ""),
            mcid=record.get("mcid", 0.0),
            mcid_range=record.get("mcid_range", ""),
            interpretation_guide=record.get("interpretation_guide", ""),
            domains_measured=record.get("domains_measured", []),
            validated_for=record.get("validated_for", []),
            average_completion_time=record.get("average_completion_time", 0),
            original_citation=record.get("original_citation", ""),
            snomed_code=record.get("snomed_code", ""),
        )


@dataclass
class RadiographicParameterNode:
    """Spine Radiographic/Sagittal Balance Parameters (v7.1).

    Neo4j Label: RadioParameter

    PI, LL, PT, SS, SVA, Cobb Angle 등 방사선학적 지표.

    Examples:
        - PI (Pelvic Incidence): Fixed parameter, 40-65° normal
        - LL (Lumbar Lordosis): Positional, 40-60° normal
        - SVA (Sagittal Vertical Axis): <50mm normal

    Relationships:
        - (Paper)-[:REPORTS_PARAMETER]->(RadioParameter)
        - (RadioParameter)-[:CORRELATES]->(OutcomeMeasure)
        - (RadioParameter)-[:MODIFIED_BY]->(Intervention)
    """
    name: str  # PI, LL, SVA, Cobb Angle
    full_name: str = ""  # Pelvic Incidence, Lumbar Lordosis
    category: str = ""  # pelvic, spinal, cervical, alignment

    # Measurement Properties
    unit: str = ""  # degrees, mm
    normal_range: str = ""  # "40-65°" for PI
    measurement_method: str = ""  # "From S1 endplate to femoral head center"

    # Clinical Significance
    is_fixed_parameter: bool = False  # PI is fixed, PT/SS are positional
    correlates_with: list[str] = field(default_factory=list)  # ["LL", "PT", "ODI"]
    clinical_threshold: str = ""  # "PI-LL mismatch >10° associated with poor outcomes"

    # Classification Systems
    roussouly_type: str = ""  # "Type 1-4" for spine types
    srs_schwab_modifier: str = ""  # "0, +, ++" for SVA

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name[:500] if self.full_name else "",
            "category": self.category,
            "unit": self.unit[:50] if self.unit else "",
            "normal_range": self.normal_range[:200] if self.normal_range else "",
            "measurement_method": self.measurement_method[:1000] if self.measurement_method else "",
            "is_fixed_parameter": self.is_fixed_parameter,
            "correlates_with": self.correlates_with[:20],
            "clinical_threshold": self.clinical_threshold[:500] if self.clinical_threshold else "",
            "roussouly_type": self.roussouly_type[:100] if self.roussouly_type else "",
            "srs_schwab_modifier": self.srs_schwab_modifier[:100] if self.srs_schwab_modifier else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "RadiographicParameterNode":
        return cls(
            name=record.get("name", ""),
            full_name=record.get("full_name", ""),
            category=record.get("category", ""),
            unit=record.get("unit", ""),
            normal_range=record.get("normal_range", ""),
            measurement_method=record.get("measurement_method", ""),
            is_fixed_parameter=record.get("is_fixed_parameter", False),
            correlates_with=record.get("correlates_with", []),
            clinical_threshold=record.get("clinical_threshold", ""),
            roussouly_type=record.get("roussouly_type", ""),
            srs_schwab_modifier=record.get("srs_schwab_modifier", ""),
        )


@dataclass
class PredictionModelNode:
    """Machine Learning Prediction Model (v7.1).

    Neo4j Label: PredictionModel

    예측 모델 연구에서 사용된 ML/AI 모델 정보.

    Examples:
        - "XGBoost for Pseudarthrosis Prediction" (AUC=0.85)
        - "Random Forest for 30-day Readmission" (Accuracy=0.78)

    Relationships:
        - (Paper)-[:DEVELOPS_MODEL]->(PredictionModel)
        - (PredictionModel)-[:PREDICTS]->(Outcome)
        - (PredictionModel)-[:USES_FEATURE]->(RiskFactor)
    """
    name: str  # "XGBoost for Pseudarthrosis Prediction"
    model_type: str = ""  # logistic_regression, random_forest, xgboost, neural_network, svm

    # Task
    prediction_target: str = ""  # "Pseudarthrosis", "30-day readmission"
    prediction_type: str = ""  # binary_classification, multiclass, regression, survival

    # Performance Metrics
    auc: float = 0.0  # Area Under ROC Curve
    accuracy: float = 0.0  # Accuracy
    sensitivity: float = 0.0  # Sensitivity / Recall
    specificity: float = 0.0  # Specificity
    ppv: float = 0.0  # Positive Predictive Value
    npv: float = 0.0  # Negative Predictive Value
    f1_score: float = 0.0  # F1 Score
    c_index: float = 0.0  # Concordance Index (survival)

    # Features
    top_features: list[str] = field(default_factory=list)  # ["albumin", "platelet_count", "tumor_histology"]
    total_features: int = 0  # Total number of features used
    feature_importance_method: str = ""  # SHAP, permutation, gini

    # Validation
    validation_type: str = ""  # internal, external, cross_validation, temporal
    training_size: int = 0
    validation_size: int = 0
    external_cohort: str = ""  # External validation dataset name

    # Calibration
    calibration_method: str = ""  # Platt scaling, isotonic regression
    brier_score: float = 0.0

    # Source
    source_paper_id: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "model_type": self.model_type,
            "prediction_target": self.prediction_target[:500] if self.prediction_target else "",
            "prediction_type": self.prediction_type,
            "auc": self.auc,
            "accuracy": self.accuracy,
            "sensitivity": self.sensitivity,
            "specificity": self.specificity,
            "ppv": self.ppv,
            "npv": self.npv,
            "f1_score": self.f1_score,
            "c_index": self.c_index,
            "top_features": self.top_features[:50],
            "total_features": self.total_features,
            "feature_importance_method": self.feature_importance_method[:200] if self.feature_importance_method else "",
            "validation_type": self.validation_type,
            "training_size": self.training_size,
            "validation_size": self.validation_size,
            "external_cohort": self.external_cohort[:500] if self.external_cohort else "",
            "calibration_method": self.calibration_method[:200] if self.calibration_method else "",
            "brier_score": self.brier_score,
            "source_paper_id": self.source_paper_id[:100] if self.source_paper_id else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "PredictionModelNode":
        return cls(
            name=record.get("name", ""),
            model_type=record.get("model_type", ""),
            prediction_target=record.get("prediction_target", ""),
            prediction_type=record.get("prediction_type", ""),
            auc=record.get("auc", 0.0),
            accuracy=record.get("accuracy", 0.0),
            sensitivity=record.get("sensitivity", 0.0),
            specificity=record.get("specificity", 0.0),
            ppv=record.get("ppv", 0.0),
            npv=record.get("npv", 0.0),
            f1_score=record.get("f1_score", 0.0),
            c_index=record.get("c_index", 0.0),
            top_features=record.get("top_features", []),
            total_features=record.get("total_features", 0),
            feature_importance_method=record.get("feature_importance_method", ""),
            validation_type=record.get("validation_type", ""),
            training_size=record.get("training_size", 0),
            validation_size=record.get("validation_size", 0),
            external_cohort=record.get("external_cohort", ""),
            calibration_method=record.get("calibration_method", ""),
            brier_score=record.get("brier_score", 0.0),
            source_paper_id=record.get("source_paper_id", ""),
        )


@dataclass
class RiskFactorNode:
    """Patient Risk Factor (v7.1).

    Neo4j Label: RiskFactor

    수술 결과에 영향을 미치는 위험 요인.

    Examples:
        - "Diabetes" (OR=2.5, modifiable)
        - "Age > 65" (HR=1.8, non-modifiable)
        - "BMI > 30" (RR=2.1, modifiable)

    Relationships:
        - (Paper)-[:HAS_RISK_FACTOR]->(RiskFactor)
        - (PredictionModel)-[:USES_FEATURE]->(RiskFactor)
        - (RiskFactor)-[:INCREASES_RISK]->(Complication)
    """
    name: str  # "Diabetes", "Smoking", "BMI > 30"
    category: str = ""  # demographic, comorbidity, lifestyle, surgical, radiographic

    # Measurement
    variable_type: str = ""  # binary, continuous, categorical, ordinal
    unit: str = ""  # kg/m², years, pack-years
    threshold: str = ""  # ">30" for BMI obesity

    # Evidence
    evidence_level: str = ""  # Grade A, B, C (NASS guidelines)
    associated_outcomes: list[str] = field(default_factory=list)  # ["infection", "pseudarthrosis", "readmission"]

    # Effect Size (typical from literature)
    typical_or: float = 0.0  # Odds Ratio
    typical_hr: float = 0.0  # Hazard Ratio
    typical_rr: float = 0.0  # Relative Risk

    # Modifiability
    is_modifiable: bool = False  # Can be changed (smoking vs age)
    optimization_strategy: str = ""  # "Smoking cessation 4 weeks prior to surgery"

    # Coding
    snomed_code: str = ""
    mesh_term: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "variable_type": self.variable_type,
            "unit": self.unit[:50] if self.unit else "",
            "threshold": self.threshold[:200] if self.threshold else "",
            "evidence_level": self.evidence_level,
            "associated_outcomes": self.associated_outcomes[:30],
            "typical_or": self.typical_or,
            "typical_hr": self.typical_hr,
            "typical_rr": self.typical_rr,
            "is_modifiable": self.is_modifiable,
            "optimization_strategy": self.optimization_strategy[:1000] if self.optimization_strategy else "",
            "snomed_code": self.snomed_code[:50] if self.snomed_code else "",
            "mesh_term": self.mesh_term[:200] if self.mesh_term else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "RiskFactorNode":
        return cls(
            name=record.get("name", ""),
            category=record.get("category", ""),
            variable_type=record.get("variable_type", ""),
            unit=record.get("unit", ""),
            threshold=record.get("threshold", ""),
            evidence_level=record.get("evidence_level", ""),
            associated_outcomes=record.get("associated_outcomes", []),
            typical_or=record.get("typical_or", 0.0),
            typical_hr=record.get("typical_hr", 0.0),
            typical_rr=record.get("typical_rr", 0.0),
            is_modifiable=record.get("is_modifiable", False),
            optimization_strategy=record.get("optimization_strategy", ""),
            snomed_code=record.get("snomed_code", ""),
            mesh_term=record.get("mesh_term", ""),
        )


@dataclass
class PatientCohortNode:
    """Patient Cohort Characteristics (v7.2).

    Neo4j Label: PatientCohort

    연구 대상 환자군의 인구통계학적, 임상적 특성.

    Examples:
        - "n=150, age 65±8, 60% female"
        - "Propensity-matched cohort: n=200 per group"
        - "Adult deformity patients, Cobb >30°"

    Relationships:
        - (Paper)-[:HAS_COHORT]->(PatientCohort)
        - (PatientCohort)-[:TREATED_WITH]->(Intervention)
    """
    name: str  # "Study Cohort", "Intervention Group", "Control Group"
    cohort_type: str = ""  # intervention, control, total, propensity_matched

    # Sample Size
    sample_size: int = 0  # n=150
    male_count: int = 0
    female_count: int = 0
    female_percentage: float = 0.0

    # Demographics
    mean_age: float = 0.0  # years
    age_sd: float = 0.0  # standard deviation
    age_range: str = ""  # "45-80"
    mean_bmi: float = 0.0  # kg/m²
    bmi_sd: float = 0.0

    # Clinical Characteristics
    diagnosis: str = ""  # Primary diagnosis (e.g., "lumbar stenosis")
    inclusion_criteria: list[str] = field(default_factory=list)
    exclusion_criteria: list[str] = field(default_factory=list)

    # Comorbidities
    diabetes_percentage: float = 0.0
    hypertension_percentage: float = 0.0
    smoker_percentage: float = 0.0
    asa_score_mean: float = 0.0  # ASA Physical Status (1-5)
    cci_mean: float = 0.0  # Charlson Comorbidity Index

    # Surgical History
    prior_surgery_percentage: float = 0.0
    revision_case_percentage: float = 0.0

    # Baseline Clinical Scores
    baseline_vas: float = 0.0  # VAS pain score
    baseline_odi: float = 0.0  # ODI score
    baseline_joa: float = 0.0  # JOA score

    # Source
    source_paper_id: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "cohort_type": self.cohort_type,
            "sample_size": self.sample_size,
            "male_count": self.male_count,
            "female_count": self.female_count,
            "female_percentage": self.female_percentage,
            "mean_age": self.mean_age,
            "age_sd": self.age_sd,
            "age_range": self.age_range[:50] if self.age_range else "",
            "mean_bmi": self.mean_bmi,
            "bmi_sd": self.bmi_sd,
            "diagnosis": self.diagnosis[:500] if self.diagnosis else "",
            "inclusion_criteria": self.inclusion_criteria[:20],
            "exclusion_criteria": self.exclusion_criteria[:20],
            "diabetes_percentage": self.diabetes_percentage,
            "hypertension_percentage": self.hypertension_percentage,
            "smoker_percentage": self.smoker_percentage,
            "asa_score_mean": self.asa_score_mean,
            "cci_mean": self.cci_mean,
            "prior_surgery_percentage": self.prior_surgery_percentage,
            "revision_case_percentage": self.revision_case_percentage,
            "baseline_vas": self.baseline_vas,
            "baseline_odi": self.baseline_odi,
            "baseline_joa": self.baseline_joa,
            "source_paper_id": self.source_paper_id,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "PatientCohortNode":
        return cls(
            name=record.get("name", ""),
            cohort_type=record.get("cohort_type", ""),
            sample_size=record.get("sample_size", 0),
            male_count=record.get("male_count", 0),
            female_count=record.get("female_count", 0),
            female_percentage=record.get("female_percentage", 0.0),
            mean_age=record.get("mean_age", 0.0),
            age_sd=record.get("age_sd", 0.0),
            age_range=record.get("age_range", ""),
            mean_bmi=record.get("mean_bmi", 0.0),
            bmi_sd=record.get("bmi_sd", 0.0),
            diagnosis=record.get("diagnosis", ""),
            inclusion_criteria=record.get("inclusion_criteria", []),
            exclusion_criteria=record.get("exclusion_criteria", []),
            diabetes_percentage=record.get("diabetes_percentage", 0.0),
            hypertension_percentage=record.get("hypertension_percentage", 0.0),
            smoker_percentage=record.get("smoker_percentage", 0.0),
            asa_score_mean=record.get("asa_score_mean", 0.0),
            cci_mean=record.get("cci_mean", 0.0),
            prior_surgery_percentage=record.get("prior_surgery_percentage", 0.0),
            revision_case_percentage=record.get("revision_case_percentage", 0.0),
            baseline_vas=record.get("baseline_vas", 0.0),
            baseline_odi=record.get("baseline_odi", 0.0),
            baseline_joa=record.get("baseline_joa", 0.0),
            source_paper_id=record.get("source_paper_id", ""),
        )


@dataclass
class FollowUpNode:
    """Follow-Up Timepoint Data (v7.2).

    Neo4j Label: FollowUp

    추적 관찰 시점별 결과 데이터.

    Examples:
        - "6-month follow-up: VAS 2.3, ODI 18%"
        - "2-year minimum follow-up: 95% fusion rate"
        - "Final follow-up (mean 38 months): No progression"

    Relationships:
        - (Paper)-[:HAS_FOLLOWUP]->(FollowUp)
        - (FollowUp)-[:REPORTS_OUTCOME]->(Outcome)
    """
    name: str  # "6-month", "1-year", "2-year", "Final"
    timepoint_months: int = 0  # 6, 12, 24, etc.
    timepoint_type: str = ""  # fixed, minimum, mean, final

    # Follow-up Statistics
    mean_followup_months: float = 0.0  # Mean follow-up duration
    followup_sd: float = 0.0  # Standard deviation
    followup_range: str = ""  # "12-60 months"
    completeness_rate: float = 0.0  # % of patients with data at this timepoint
    lost_to_followup: int = 0  # Number of patients lost

    # Clinical Outcomes at Timepoint
    vas_score: float = 0.0
    vas_improvement: float = 0.0  # Change from baseline
    odi_score: float = 0.0
    odi_improvement: float = 0.0
    joa_score: float = 0.0
    joa_recovery_rate: float = 0.0
    sf36_pcs: float = 0.0
    sf36_mcs: float = 0.0

    # Radiographic Outcomes
    fusion_rate: float = 0.0  # %
    cage_subsidence_rate: float = 0.0  # %
    adjacent_segment_disease_rate: float = 0.0  # %

    # Complications at Timepoint
    complication_rate: float = 0.0
    reoperation_rate: float = 0.0
    revision_rate: float = 0.0

    # Patient Satisfaction
    satisfaction_rate: float = 0.0  # %
    return_to_work_rate: float = 0.0  # %
    return_to_work_weeks: float = 0.0  # Mean weeks to return

    # Source
    source_paper_id: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "timepoint_months": self.timepoint_months,
            "timepoint_type": self.timepoint_type,
            "mean_followup_months": self.mean_followup_months,
            "followup_sd": self.followup_sd,
            "followup_range": self.followup_range[:100] if self.followup_range else "",
            "completeness_rate": self.completeness_rate,
            "lost_to_followup": self.lost_to_followup,
            "vas_score": self.vas_score,
            "vas_improvement": self.vas_improvement,
            "odi_score": self.odi_score,
            "odi_improvement": self.odi_improvement,
            "joa_score": self.joa_score,
            "joa_recovery_rate": self.joa_recovery_rate,
            "sf36_pcs": self.sf36_pcs,
            "sf36_mcs": self.sf36_mcs,
            "fusion_rate": self.fusion_rate,
            "cage_subsidence_rate": self.cage_subsidence_rate,
            "adjacent_segment_disease_rate": self.adjacent_segment_disease_rate,
            "complication_rate": self.complication_rate,
            "reoperation_rate": self.reoperation_rate,
            "revision_rate": self.revision_rate,
            "satisfaction_rate": self.satisfaction_rate,
            "return_to_work_rate": self.return_to_work_rate,
            "return_to_work_weeks": self.return_to_work_weeks,
            "source_paper_id": self.source_paper_id,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "FollowUpNode":
        return cls(
            name=record.get("name", ""),
            timepoint_months=record.get("timepoint_months", 0),
            timepoint_type=record.get("timepoint_type", ""),
            mean_followup_months=record.get("mean_followup_months", 0.0),
            followup_sd=record.get("followup_sd", 0.0),
            followup_range=record.get("followup_range", ""),
            completeness_rate=record.get("completeness_rate", 0.0),
            lost_to_followup=record.get("lost_to_followup", 0),
            vas_score=record.get("vas_score", 0.0),
            vas_improvement=record.get("vas_improvement", 0.0),
            odi_score=record.get("odi_score", 0.0),
            odi_improvement=record.get("odi_improvement", 0.0),
            joa_score=record.get("joa_score", 0.0),
            joa_recovery_rate=record.get("joa_recovery_rate", 0.0),
            sf36_pcs=record.get("sf36_pcs", 0.0),
            sf36_mcs=record.get("sf36_mcs", 0.0),
            fusion_rate=record.get("fusion_rate", 0.0),
            cage_subsidence_rate=record.get("cage_subsidence_rate", 0.0),
            adjacent_segment_disease_rate=record.get("adjacent_segment_disease_rate", 0.0),
            complication_rate=record.get("complication_rate", 0.0),
            reoperation_rate=record.get("reoperation_rate", 0.0),
            revision_rate=record.get("revision_rate", 0.0),
            satisfaction_rate=record.get("satisfaction_rate", 0.0),
            return_to_work_rate=record.get("return_to_work_rate", 0.0),
            return_to_work_weeks=record.get("return_to_work_weeks", 0.0),
            source_paper_id=record.get("source_paper_id", ""),
        )


@dataclass
class CostNode:
    """Healthcare Cost Analysis Data (v7.2).

    Neo4j Label: Cost

    의료 비용 분석 데이터.

    Examples:
        - "Total hospital cost: $45,000 (TLIF) vs $38,000 (MIS-TLIF)"
        - "90-day episode cost: $52,000"
        - "QALY gained: 0.15 at $32,000/QALY"

    Relationships:
        - (Paper)-[:REPORTS_COST]->(Cost)
        - (Cost)-[:ASSOCIATED_WITH]->(Intervention)
    """
    name: str  # "Hospital Cost", "90-day Episode Cost", "Total Cost"
    cost_type: str = ""  # direct, indirect, total, incremental, opportunity

    # Cost Values (USD)
    mean_cost: float = 0.0
    cost_sd: float = 0.0
    median_cost: float = 0.0
    cost_range: str = ""  # "$35,000-$65,000"
    currency: str = "USD"
    cost_year: int = 0  # Year of cost data for inflation adjustment

    # Cost Components
    hospital_cost: float = 0.0
    surgeon_fee: float = 0.0
    anesthesia_fee: float = 0.0
    implant_cost: float = 0.0
    rehabilitation_cost: float = 0.0
    readmission_cost: float = 0.0
    revision_cost: float = 0.0

    # Length of Stay
    los_days: float = 0.0  # Mean length of stay
    los_sd: float = 0.0
    icu_days: float = 0.0

    # Cost-Effectiveness Metrics
    qaly_gained: float = 0.0  # Quality-Adjusted Life Year
    icer: float = 0.0  # Incremental Cost-Effectiveness Ratio ($/QALY)
    icer_threshold_met: bool = False  # Below willingness-to-pay threshold
    willingness_to_pay: float = 0.0  # $/QALY threshold used

    # Comparative Analysis
    comparison_intervention: str = ""  # What was compared
    cost_difference: float = 0.0  # Intervention - Control
    cost_savings: float = 0.0  # If negative = savings

    # Time Horizon
    analysis_perspective: str = ""  # payer, hospital, societal
    time_horizon: str = ""  # 30-day, 90-day, 1-year, lifetime

    # Source
    source_paper_id: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "cost_type": self.cost_type,
            "mean_cost": self.mean_cost,
            "cost_sd": self.cost_sd,
            "median_cost": self.median_cost,
            "cost_range": self.cost_range[:100] if self.cost_range else "",
            "currency": self.currency,
            "cost_year": self.cost_year,
            "hospital_cost": self.hospital_cost,
            "surgeon_fee": self.surgeon_fee,
            "anesthesia_fee": self.anesthesia_fee,
            "implant_cost": self.implant_cost,
            "rehabilitation_cost": self.rehabilitation_cost,
            "readmission_cost": self.readmission_cost,
            "revision_cost": self.revision_cost,
            "los_days": self.los_days,
            "los_sd": self.los_sd,
            "icu_days": self.icu_days,
            "qaly_gained": self.qaly_gained,
            "icer": self.icer,
            "icer_threshold_met": self.icer_threshold_met,
            "willingness_to_pay": self.willingness_to_pay,
            "comparison_intervention": self.comparison_intervention[:200] if self.comparison_intervention else "",
            "cost_difference": self.cost_difference,
            "cost_savings": self.cost_savings,
            "analysis_perspective": self.analysis_perspective,
            "time_horizon": self.time_horizon[:100] if self.time_horizon else "",
            "source_paper_id": self.source_paper_id,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "CostNode":
        return cls(
            name=record.get("name", ""),
            cost_type=record.get("cost_type", ""),
            mean_cost=record.get("mean_cost", 0.0),
            cost_sd=record.get("cost_sd", 0.0),
            median_cost=record.get("median_cost", 0.0),
            cost_range=record.get("cost_range", ""),
            currency=record.get("currency", "USD"),
            cost_year=record.get("cost_year", 0),
            hospital_cost=record.get("hospital_cost", 0.0),
            surgeon_fee=record.get("surgeon_fee", 0.0),
            anesthesia_fee=record.get("anesthesia_fee", 0.0),
            implant_cost=record.get("implant_cost", 0.0),
            rehabilitation_cost=record.get("rehabilitation_cost", 0.0),
            readmission_cost=record.get("readmission_cost", 0.0),
            revision_cost=record.get("revision_cost", 0.0),
            los_days=record.get("los_days", 0.0),
            los_sd=record.get("los_sd", 0.0),
            icu_days=record.get("icu_days", 0.0),
            qaly_gained=record.get("qaly_gained", 0.0),
            icer=record.get("icer", 0.0),
            icer_threshold_met=record.get("icer_threshold_met", False),
            willingness_to_pay=record.get("willingness_to_pay", 0.0),
            comparison_intervention=record.get("comparison_intervention", ""),
            cost_difference=record.get("cost_difference", 0.0),
            cost_savings=record.get("cost_savings", 0.0),
            analysis_perspective=record.get("analysis_perspective", ""),
            time_horizon=record.get("time_horizon", ""),
            source_paper_id=record.get("source_paper_id", ""),
        )


@dataclass
class QualityMetricNode:
    """Study Quality Assessment Metrics (v7.2).

    Neo4j Label: QualityMetric

    연구 품질 평가 지표.

    Examples:
        - GRADE: High quality for RCT
        - MINORS: 18/24 for non-randomized study
        - Cochrane Risk of Bias: Low risk

    Relationships:
        - (Paper)-[:HAS_QUALITY_METRIC]->(QualityMetric)
    """
    name: str  # "GRADE", "MINORS", "Newcastle-Ottawa", "Cochrane ROB"
    assessment_tool: str = ""  # Full name of the tool

    # Overall Score
    overall_score: float = 0.0  # Numeric score if applicable
    max_score: float = 0.0  # Maximum possible score
    score_percentage: float = 0.0  # score/max_score * 100
    overall_rating: str = ""  # high, moderate, low, very_low (GRADE)

    # GRADE-specific Fields
    grade_certainty: str = ""  # high, moderate, low, very_low
    grade_downgrade_reasons: list[str] = field(default_factory=list)  # ["risk of bias", "imprecision"]
    grade_upgrade_reasons: list[str] = field(default_factory=list)  # ["large effect", "dose-response"]

    # Risk of Bias Domains (Cochrane ROB 2.0)
    rob_randomization: str = ""  # low, some concerns, high
    rob_deviations: str = ""  # Deviations from intended interventions
    rob_missing_data: str = ""  # Missing outcome data
    rob_measurement: str = ""  # Measurement of outcome
    rob_selection: str = ""  # Selection of reported result
    rob_overall: str = ""  # Overall risk of bias

    # MINORS-specific Fields (for non-randomized studies)
    minors_score: int = 0  # 0-24 scale
    minors_items: list[dict] = field(default_factory=list)  # [{"item": "Clear aim", "score": 2}]

    # Newcastle-Ottawa Scale (for cohort/case-control)
    nos_selection: int = 0  # 0-4 stars
    nos_comparability: int = 0  # 0-2 stars
    nos_outcome: int = 0  # 0-3 stars
    nos_total: int = 0  # 0-9 stars

    # Jadad Score (for RCTs)
    jadad_score: int = 0  # 0-5
    jadad_randomization: int = 0
    jadad_blinding: int = 0
    jadad_withdrawals: int = 0

    # Meta-analysis specific (AMSTAR)
    amstar_score: int = 0  # 0-16
    amstar_rating: str = ""  # high, moderate, low, critically_low

    # General Assessment
    strengths: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    assessor_notes: str = ""

    # Source
    source_paper_id: str = ""
    assessment_date: str = ""  # ISO date

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "assessment_tool": self.assessment_tool[:200] if self.assessment_tool else "",
            "overall_score": self.overall_score,
            "max_score": self.max_score,
            "score_percentage": self.score_percentage,
            "overall_rating": self.overall_rating,
            "grade_certainty": self.grade_certainty,
            "grade_downgrade_reasons": self.grade_downgrade_reasons[:10],
            "grade_upgrade_reasons": self.grade_upgrade_reasons[:10],
            "rob_randomization": self.rob_randomization,
            "rob_deviations": self.rob_deviations,
            "rob_missing_data": self.rob_missing_data,
            "rob_measurement": self.rob_measurement,
            "rob_selection": self.rob_selection,
            "rob_overall": self.rob_overall,
            "minors_score": self.minors_score,
            "minors_items": self.minors_items[:15],
            "nos_selection": self.nos_selection,
            "nos_comparability": self.nos_comparability,
            "nos_outcome": self.nos_outcome,
            "nos_total": self.nos_total,
            "jadad_score": self.jadad_score,
            "jadad_randomization": self.jadad_randomization,
            "jadad_blinding": self.jadad_blinding,
            "jadad_withdrawals": self.jadad_withdrawals,
            "amstar_score": self.amstar_score,
            "amstar_rating": self.amstar_rating,
            "strengths": self.strengths[:10],
            "limitations": self.limitations[:10],
            "assessor_notes": self.assessor_notes[:1000] if self.assessor_notes else "",
            "source_paper_id": self.source_paper_id,
            "assessment_date": self.assessment_date,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "QualityMetricNode":
        return cls(
            name=record.get("name", ""),
            assessment_tool=record.get("assessment_tool", ""),
            overall_score=record.get("overall_score", 0.0),
            max_score=record.get("max_score", 0.0),
            score_percentage=record.get("score_percentage", 0.0),
            overall_rating=record.get("overall_rating", ""),
            grade_certainty=record.get("grade_certainty", ""),
            grade_downgrade_reasons=record.get("grade_downgrade_reasons", []),
            grade_upgrade_reasons=record.get("grade_upgrade_reasons", []),
            rob_randomization=record.get("rob_randomization", ""),
            rob_deviations=record.get("rob_deviations", ""),
            rob_missing_data=record.get("rob_missing_data", ""),
            rob_measurement=record.get("rob_measurement", ""),
            rob_selection=record.get("rob_selection", ""),
            rob_overall=record.get("rob_overall", ""),
            minors_score=record.get("minors_score", 0),
            minors_items=record.get("minors_items", []),
            nos_selection=record.get("nos_selection", 0),
            nos_comparability=record.get("nos_comparability", 0),
            nos_outcome=record.get("nos_outcome", 0),
            nos_total=record.get("nos_total", 0),
            jadad_score=record.get("jadad_score", 0),
            jadad_randomization=record.get("jadad_randomization", 0),
            jadad_blinding=record.get("jadad_blinding", 0),
            jadad_withdrawals=record.get("jadad_withdrawals", 0),
            amstar_score=record.get("amstar_score", 0),
            amstar_rating=record.get("amstar_rating", ""),
            strengths=record.get("strengths", []),
            limitations=record.get("limitations", []),
            assessor_notes=record.get("assessor_notes", ""),
            source_paper_id=record.get("source_paper_id", ""),
            assessment_date=record.get("assessment_date", ""),
        )
