"""Spine Graph Relationship Definitions.

This module contains all relationship (edge) dataclasses for the Spine GraphRAG system.
Relationships connect nodes in the Neo4j knowledge graph and store relational metadata.

Relationship Types:
    - Paper → Pathology: STUDIES
    - Paper → Chunk: HAS_CHUNK
    - Pathology → Anatomy: LOCATED_AT
    - Paper → Intervention: INVESTIGATES
    - Intervention → Pathology: TREATS
    - Intervention → Outcome: AFFECTS
    - Intervention → Intervention: IS_A
    - Paper → Paper: CITES, SUPPORTS, CONTRADICTS, etc.
    - Intervention → Complication: CAUSES (v7.1)
    - Paper → RiskFactor: HAS_RISK_FACTOR (v7.1)
    - PredictionModel → Outcome: PREDICTS (v7.1)
    - RadioParameter → OutcomeMeasure: CORRELATES (v7.1)
    - Intervention → Implant: USES_DEVICE (v7.1)
    - Paper → PatientCohort: HAS_COHORT (v7.2)
    - PatientCohort → Intervention: TREATED_WITH (v7.2)
    - Paper → FollowUp: HAS_FOLLOWUP (v7.2)
    - FollowUp → Outcome: REPORTS_OUTCOME (v7.2)
    - Paper → Cost: REPORTS_COST (v7.2)
    - Cost → Intervention: ASSOCIATED_WITH (v7.2)
    - Paper → QualityMetric: HAS_QUALITY_METRIC (v7.2)

Version: 7.5
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum

# Import enums from central enums module to avoid duplication
from .enums import CitationContext, PaperRelationType


# ============================================================================
# Basic Relationships
# ============================================================================

@dataclass
class StudiesRelation:
    """논문 → 질환 연구 관계.

    (Paper)-[:STUDIES]->(Pathology)
    """
    source_paper_id: str
    target_pathology: str
    is_primary: bool = True  # 주 연구 대상 여부


@dataclass
class HasChunkRelation:
    """논문 → 청크 소유 관계 (v5.3).

    (Paper)-[:HAS_CHUNK]->(Chunk)
    """
    paper_id: str
    chunk_id: str
    chunk_index: int = 0


@dataclass
class LocatedAtRelation:
    """질환 → 해부학 위치 관계.

    (Pathology)-[:LOCATED_AT]->(Anatomy)
    """
    pathology_name: str
    anatomy_name: str


@dataclass
class InvestigatesRelation:
    """논문 → 수술법 조사 관계.

    (Paper)-[:INVESTIGATES]->(Intervention)
    """
    paper_id: str
    intervention_name: str
    is_comparison: bool = False  # 비교 연구 여부


@dataclass
class TreatsRelation:
    """수술법 → 질환 치료 관계.

    (Intervention)-[:TREATS]->(Pathology)
    """
    intervention_name: str
    pathology_name: str
    indication: str = ""  # 적응증

    # === NEW: Indication Details (v4.2) ===
    contraindication: str = ""        # Contraindication
    indication_level: str = ""        # strong, moderate, weak
    source_guideline: str = ""        # Guideline source (e.g., "NASS 2020")

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "indication": self.indication[:500] if self.indication else "",
            "contraindication": self.contraindication[:500] if self.contraindication else "",
            "indication_level": self.indication_level,
            "source_guideline": self.source_guideline[:200] if self.source_guideline else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, intervention_name: str, pathology_name: str) -> "TreatsRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            intervention_name: Intervention 노드 이름
            pathology_name: Pathology 노드 이름

        Returns:
            TreatsRelation 인스턴스
        """
        return cls(
            intervention_name=intervention_name,
            pathology_name=pathology_name,
            indication=record.get("indication", ""),
            contraindication=record.get("contraindication", ""),
            indication_level=record.get("indication_level", ""),
            source_guideline=record.get("source_guideline", ""),
        )


@dataclass
class AffectsRelation:
    """수술법 → 결과 관계 (핵심 추론 경로).

    (Intervention)-[:AFFECTS]->(Outcome)

    통계 정보를 관계 속성으로 저장.

    v4.0 Enhanced:
    - baseline/final: Claude PDF 프로세서 호환
    - value_intervention/value_control: Gemini Vision 프로세서 호환
    - category: 결과 카테고리 (pain, function, radiologic 등)
    - timepoint: 측정 시점 (preop, 6mo, 1yr 등)
    """
    intervention_name: str
    outcome_name: str
    source_paper_id: str

    # === 결과값 (여러 형식 지원) ===
    value: str = ""  # 최종값 또는 단일값 (예: "85.2%")
    baseline: Optional[float] = None  # 기준값 (Claude 형식)
    final: Optional[float] = None  # 최종값 (Claude 형식)
    value_intervention: str = ""  # 중재군 값 (Gemini 형식)
    value_control: str = ""  # 대조군 값
    value_difference: str = ""  # 차이값

    # === 통계 정보 ===
    p_value: Optional[float] = None
    effect_size: str = ""
    confidence_interval: str = ""  # "95% CI: 1.2-4.3"
    is_significant: bool = False

    # === 메타데이터 ===
    direction: str = ""  # improved, worsened, unchanged
    category: str = ""  # pain, function, radiologic, complication
    timepoint: str = ""  # preop, postop, 6mo, 1yr, 2yr, final

    def to_neo4j_properties(self) -> dict:
        return {
            "source_paper_id": self.source_paper_id,
            "value": self.value,
            "baseline": self.baseline,
            "final": self.final,
            "value_intervention": self.value_intervention,
            "value_control": self.value_control,
            "value_difference": self.value_difference,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "confidence_interval": self.confidence_interval,
            "is_significant": self.is_significant,
            "direction": self.direction,
            "category": self.category,
            "timepoint": self.timepoint,
        }


@dataclass
class IsARelation:
    """수술법 계층 관계.

    (Intervention)-[:IS_A]->(Intervention)

    예: (TLIF)-[:IS_A]->(Interbody Fusion)-[:IS_A]->(Fusion Surgery)
    """
    child_name: str
    parent_name: str
    level: int = 1  # 계층 깊이


@dataclass
class PaperRelation:
    """논문 간 관계 (레거시 - 하위 호환성 유지).

    (Paper)-[:CITES|SUPPORTS|CONTRADICTS]->(Paper)

    Note: 새 코드에서는 PaperRelationship를 사용하세요.
    """
    source_paper_id: str
    target_paper_id: str
    relation_type: str  # cites, supports, contradicts
    confidence: float = 0.0
    evidence: str = ""
    conflict_point: str = ""  # contradicts인 경우


@dataclass
class CitesRelationship:
    """논문 인용 관계 (Important Citations - v3.2+).

    (Paper)-[:CITES {context, section, ...}]->(Paper)

    논문에서 중요한 인용(결과를 지지하거나 반박하는 선행 연구)을 추출하여 저장.
    인용된 논문은 PubMed 검색을 통해 Paper 노드로 생성.

    Attributes:
        citing_paper_id: 인용하는 논문 ID (required)
        cited_paper_id: 인용된 논문 ID (required, PubMed에서 검색하여 생성)
        context: 인용 컨텍스트 유형 (CitationContext)
        section: 인용이 등장한 섹션 (discussion, results, introduction, etc.)
        citation_text: 인용 문장 원문 (해당 인용이 있는 문장)
        importance_reason: 왜 중요한 인용인지 설명 (LLM 생성)
        outcome_comparison: 비교 대상 결과변수 (e.g., "VAS", "Fusion Rate")
        direction_match: 결과 방향 일치 여부 (같은 방향이면 True)
        confidence: 인용 관계 신뢰도 (0.0-1.0)
        detected_by: 탐지 방법 (llm_extraction, manual, etc.)
        created_at: 관계 생성 시각
    """
    citing_paper_id: str
    cited_paper_id: str
    context: CitationContext = CitationContext.BACKGROUND
    section: str = ""  # discussion, results, introduction, methods
    citation_text: str = ""  # 인용이 있는 문장 원문
    importance_reason: str = ""  # 왜 중요한 인용인지
    outcome_comparison: str = ""  # 비교 대상 결과변수
    direction_match: Optional[bool] = None  # 결과 방향 일치 여부
    confidence: float = 0.0
    detected_by: str = "llm_extraction"
    created_at: Optional[datetime] = None

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "context": self.context.value if isinstance(self.context, CitationContext) else self.context,
            "section": self.section,
            "citation_text": self.citation_text[:500] if self.citation_text else "",  # 길이 제한
            "importance_reason": self.importance_reason[:500] if self.importance_reason else "",
            "outcome_comparison": self.outcome_comparison,
            "direction_match": self.direction_match,
            "confidence": self.confidence,
            "detected_by": self.detected_by,
            "created_at": self.created_at or datetime.now(),
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, citing_id: str, cited_id: str) -> "CitesRelationship":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            citing_id: 인용하는 논문 ID
            cited_id: 인용된 논문 ID

        Returns:
            CitesRelationship 인스턴스
        """
        context_str = record.get("context", "background")
        try:
            context = CitationContext(context_str)
        except ValueError:
            context = CitationContext.BACKGROUND

        return cls(
            citing_paper_id=citing_id,
            cited_paper_id=cited_id,
            context=context,
            section=record.get("section", ""),
            citation_text=record.get("citation_text", ""),
            importance_reason=record.get("importance_reason", ""),
            outcome_comparison=record.get("outcome_comparison", ""),
            direction_match=record.get("direction_match"),
            confidence=record.get("confidence", 0.0),
            detected_by=record.get("detected_by", ""),
            created_at=record.get("created_at"),
        )


@dataclass
class PaperRelationship:
    """논문 간 관계 (Unified Schema - v3.1+).

    (Paper)-[:SUPPORTS|CONTRADICTS|SIMILAR_TOPIC|EXTENDS|CITES|REPLICATES]->(Paper)

    논문 간 지적 관계를 구조화하여 저장:
    - 인용 네트워크 (CITES)
    - 결과 일치/상충 (SUPPORTS, CONTRADICTS)
    - 주제 유사도 (SIMILAR_TOPIC)
    - 연구 확장/재현 (EXTENDS, REPLICATES)

    Attributes:
        source_paper_id: 시작 논문 ID (required)
        target_paper_id: 대상 논문 ID (required)
        relation_type: 관계 유형 (PaperRelationType)
        confidence: 관계 신뢰도 (0.0-1.0)
        evidence: 관계 근거 텍스트
        detected_by: 관계 탐지 방법 (llm, citation_extraction, embedding, etc.)
        created_at: 관계 생성 시각
    """
    source_paper_id: str
    target_paper_id: str
    relation_type: PaperRelationType
    confidence: float = 0.0
    evidence: str = ""
    detected_by: str = ""  # llm, citation_extraction, embedding, manual, etc.
    created_at: Optional[datetime] = None

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "confidence": self.confidence,
            "evidence": self.evidence[:1000] if self.evidence else "",  # 길이 제한
            "detected_by": self.detected_by,
            "created_at": self.created_at or datetime.now(),
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, source_id: str, target_id: str, rel_type: str) -> "PaperRelationship":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            source_id: 시작 논문 ID
            target_id: 대상 논문 ID
            rel_type: 관계 타입 문자열 (SUPPORTS, CONTRADICTS, etc.)

        Returns:
            PaperRelationship 인스턴스
        """
        return cls(
            source_paper_id=source_id,
            target_paper_id=target_id,
            relation_type=PaperRelationType[rel_type],  # 문자열 → Enum
            confidence=record.get("confidence", 0.0),
            evidence=record.get("evidence", ""),
            detected_by=record.get("detected_by", ""),
            created_at=record.get("created_at"),
        )


# ============================================================================
# v7.1: New Relationship Types (Complications, Risk Factors, Predictions)
# ============================================================================

@dataclass
class CausesRelation:
    """수술법 → 합병증 발생 관계 (v7.1).

    (Intervention)-[:CAUSES]->(Complication)

    수술법에 따른 합병증 발생률 및 위험 요인 추적.

    Attributes:
        intervention_name: 수술법 이름
        complication_name: 합병증 이름
        source_paper_id: 출처 논문 ID
        incidence_rate: 발생률 (0.0-1.0)
        incidence_ci: 발생률 신뢰구간 (예: "2.5%-7.3%")
        surgery_type: 수술 유형 (primary, revision)
        patient_population: 환자 집단 특성
        timing: 합병증 발생 시기 (intraoperative, early, late)
    """
    intervention_name: str
    complication_name: str
    source_paper_id: str
    incidence_rate: float = 0.0
    incidence_ci: str = ""
    surgery_type: str = ""  # primary, revision
    patient_population: str = ""
    timing: str = ""  # intraoperative, early, late

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "source_paper_id": self.source_paper_id,
            "incidence_rate": self.incidence_rate,
            "incidence_ci": self.incidence_ci[:100] if self.incidence_ci else "",
            "surgery_type": self.surgery_type,
            "patient_population": self.patient_population[:500] if self.patient_population else "",
            "timing": self.timing,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, intervention_name: str, complication_name: str) -> "CausesRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            intervention_name: Intervention 노드 이름
            complication_name: Complication 노드 이름

        Returns:
            CausesRelation 인스턴스
        """
        return cls(
            intervention_name=intervention_name,
            complication_name=complication_name,
            source_paper_id=record.get("source_paper_id", ""),
            incidence_rate=record.get("incidence_rate", 0.0),
            incidence_ci=record.get("incidence_ci", ""),
            surgery_type=record.get("surgery_type", ""),
            patient_population=record.get("patient_population", ""),
            timing=record.get("timing", ""),
        )


@dataclass
class HasRiskFactorRelation:
    """논문 → 위험 인자 관계 (v7.1).

    (Paper)-[:HAS_RISK_FACTOR]->(RiskFactor)

    연구에서 밝혀진 위험 인자 및 그 효과 크기 저장.

    Attributes:
        paper_id: 논문 ID
        risk_factor_name: 위험 인자 이름
        outcome_affected: 영향받는 결과 변수
        odds_ratio: Odds Ratio (OR)
        hazard_ratio: Hazard Ratio (HR)
        relative_risk: Relative Risk (RR)
        confidence_interval: 신뢰구간 (예: "1.2-4.3")
        p_value: p-value
        is_independent: 독립적 위험 인자 여부
        adjusted_for: 보정된 변수 리스트
    """
    paper_id: str
    risk_factor_name: str
    outcome_affected: str
    odds_ratio: float = 0.0
    hazard_ratio: float = 0.0
    relative_risk: float = 0.0
    confidence_interval: str = ""
    p_value: float = 0.0
    is_independent: bool = False
    adjusted_for: list[str] = field(default_factory=list)

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "outcome_affected": self.outcome_affected,
            "odds_ratio": self.odds_ratio,
            "hazard_ratio": self.hazard_ratio,
            "relative_risk": self.relative_risk,
            "confidence_interval": self.confidence_interval[:100] if self.confidence_interval else "",
            "p_value": self.p_value,
            "is_independent": self.is_independent,
            "adjusted_for": self.adjusted_for,  # Neo4j array 지원
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, paper_id: str, risk_factor_name: str) -> "HasRiskFactorRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            paper_id: Paper 노드 ID
            risk_factor_name: RiskFactor 노드 이름

        Returns:
            HasRiskFactorRelation 인스턴스
        """
        return cls(
            paper_id=paper_id,
            risk_factor_name=risk_factor_name,
            outcome_affected=record.get("outcome_affected", ""),
            odds_ratio=record.get("odds_ratio", 0.0),
            hazard_ratio=record.get("hazard_ratio", 0.0),
            relative_risk=record.get("relative_risk", 0.0),
            confidence_interval=record.get("confidence_interval", ""),
            p_value=record.get("p_value", 0.0),
            is_independent=record.get("is_independent", False),
            adjusted_for=record.get("adjusted_for", []),
        )


@dataclass
class PredictsRelation:
    """예측 모델 → 결과 예측 관계 (v7.1).

    (PredictionModel)-[:PREDICTS]->(Outcome)

    예측 모델의 성능 지표 및 임계값 저장.

    Attributes:
        model_name: 예측 모델 이름
        outcome_name: 예측 대상 결과 이름
        source_paper_id: 출처 논문 ID
        auc: Area Under the Curve (0.0-1.0)
        accuracy: 정확도 (0.0-1.0)
        sensitivity: 민감도 (0.0-1.0)
        specificity: 특이도 (0.0-1.0)
        optimal_threshold: 최적 임계값
        decision_threshold: 의사결정 임계값 설명
    """
    model_name: str
    outcome_name: str
    source_paper_id: str
    auc: float = 0.0
    accuracy: float = 0.0
    sensitivity: float = 0.0
    specificity: float = 0.0
    optimal_threshold: float = 0.5
    decision_threshold: str = ""

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "source_paper_id": self.source_paper_id,
            "auc": self.auc,
            "accuracy": self.accuracy,
            "sensitivity": self.sensitivity,
            "specificity": self.specificity,
            "optimal_threshold": self.optimal_threshold,
            "decision_threshold": self.decision_threshold[:500] if self.decision_threshold else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, model_name: str, outcome_name: str) -> "PredictsRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            model_name: PredictionModel 노드 이름
            outcome_name: Outcome 노드 이름

        Returns:
            PredictsRelation 인스턴스
        """
        return cls(
            model_name=model_name,
            outcome_name=outcome_name,
            source_paper_id=record.get("source_paper_id", ""),
            auc=record.get("auc", 0.0),
            accuracy=record.get("accuracy", 0.0),
            sensitivity=record.get("sensitivity", 0.0),
            specificity=record.get("specificity", 0.0),
            optimal_threshold=record.get("optimal_threshold", 0.5),
            decision_threshold=record.get("decision_threshold", ""),
        )


@dataclass
class CorrelatesRelation:
    """영상 매개변수 → 결과 측정치 상관관계 (v7.1).

    (RadioParameter)-[:CORRELATES]->(OutcomeMeasure)

    영상 지표와 임상 결과의 상관관계 저장.

    Attributes:
        parameter_name: 영상 매개변수 이름 (예: "PI-LL mismatch", "SVA")
        outcome_measure_name: 결과 측정치 이름 (예: "ODI", "VAS")
        r_value: 상관계수 (-1.0 to 1.0)
        p_value: p-value
        source_paper_id: 출처 논문 ID
        correlation_type: 상관관계 유형 (positive, negative)
    """
    parameter_name: str
    outcome_measure_name: str
    r_value: float = 0.0
    p_value: float = 0.0
    source_paper_id: str = ""
    correlation_type: str = ""  # positive, negative

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "r_value": self.r_value,
            "p_value": self.p_value,
            "source_paper_id": self.source_paper_id,
            "correlation_type": self.correlation_type,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, parameter_name: str, outcome_measure_name: str) -> "CorrelatesRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            parameter_name: RadioParameter 노드 이름
            outcome_measure_name: OutcomeMeasure 노드 이름

        Returns:
            CorrelatesRelation 인스턴스
        """
        return cls(
            parameter_name=parameter_name,
            outcome_measure_name=outcome_measure_name,
            r_value=record.get("r_value", 0.0),
            p_value=record.get("p_value", 0.0),
            source_paper_id=record.get("source_paper_id", ""),
            correlation_type=record.get("correlation_type", ""),
        )


@dataclass
class UsesDeviceRelation:
    """수술법 → 의료기기 사용 관계 (v7.1).

    (Intervention)-[:USES_DEVICE]->(Implant)

    수술법에서 사용되는 의료기기 및 임플란트 추적.

    Attributes:
        intervention_name: 수술법 이름
        device_name: 의료기기/임플란트 이름
        usage_type: 사용 유형 (primary, adjunct)
        is_required: 필수 여부
    """
    intervention_name: str
    device_name: str
    usage_type: str = ""  # primary, adjunct
    is_required: bool = True

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환.

        Returns:
            Neo4j 관계 속성 딕셔너리
        """
        return {
            "usage_type": self.usage_type,
            "is_required": self.is_required,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, intervention_name: str, device_name: str) -> "UsesDeviceRelation":
        """Neo4j 레코드에서 생성 (역직렬화).

        Args:
            record: Neo4j 관계 속성 딕셔너리
            intervention_name: Intervention 노드 이름
            device_name: Implant 노드 이름

        Returns:
            UsesDeviceRelation 인스턴스
        """
        return cls(
            intervention_name=intervention_name,
            device_name=device_name,
            usage_type=record.get("usage_type", ""),
            is_required=record.get("is_required", True),
        )


# ============================================================================
# v7.2: New Relationship Types (Cohort, FollowUp, Cost, Quality)
# ============================================================================

@dataclass
class HasCohortRelation:
    """논문 → 환자 코호트 관계 (v7.2).

    (Paper)-[:HAS_COHORT]->(PatientCohort)

    연구에서 포함된 환자 코호트 정보 연결.

    Attributes:
        paper_id: 논문 ID
        cohort_name: 코호트 이름 (예: "Intervention Group", "Control")
        is_primary: 주 연구 코호트 여부
        role: 코호트 역할 (intervention, control, comparison, total)
    """
    paper_id: str
    cohort_name: str
    is_primary: bool = True
    role: str = ""  # intervention, control, comparison, total

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "is_primary": self.is_primary,
            "role": self.role,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, paper_id: str, cohort_name: str) -> "HasCohortRelation":
        return cls(
            paper_id=paper_id,
            cohort_name=cohort_name,
            is_primary=record.get("is_primary", True),
            role=record.get("role", ""),
        )


@dataclass
class TreatedWithRelation:
    """환자 코호트 → 수술법 치료 관계 (v7.2).

    (PatientCohort)-[:TREATED_WITH]->(Intervention)

    코호트가 받은 수술적 치료 연결.

    Attributes:
        cohort_name: 코호트 이름
        intervention_name: 수술법 이름
        source_paper_id: 출처 논문 ID
        n_patients: 해당 수술을 받은 환자 수
    """
    cohort_name: str
    intervention_name: str
    source_paper_id: str = ""
    n_patients: int = 0

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "source_paper_id": self.source_paper_id,
            "n_patients": self.n_patients,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, cohort_name: str, intervention_name: str) -> "TreatedWithRelation":
        return cls(
            cohort_name=cohort_name,
            intervention_name=intervention_name,
            source_paper_id=record.get("source_paper_id", ""),
            n_patients=record.get("n_patients", 0),
        )


@dataclass
class HasFollowUpRelation:
    """논문 → 추적관찰 관계 (v7.2).

    (Paper)-[:HAS_FOLLOWUP]->(FollowUp)

    연구의 추적관찰 시점 데이터 연결.

    Attributes:
        paper_id: 논문 ID
        followup_name: 추적관찰 시점 이름 (예: "6-month", "Final")
        is_primary_endpoint: 주요 평가 시점 여부
    """
    paper_id: str
    followup_name: str
    is_primary_endpoint: bool = False

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "is_primary_endpoint": self.is_primary_endpoint,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, paper_id: str, followup_name: str) -> "HasFollowUpRelation":
        return cls(
            paper_id=paper_id,
            followup_name=followup_name,
            is_primary_endpoint=record.get("is_primary_endpoint", False),
        )


@dataclass
class ReportsOutcomeAtRelation:
    """추적관찰 → 결과 보고 관계 (v7.2).

    (FollowUp)-[:REPORTS_OUTCOME]->(Outcome)

    특정 추적관찰 시점에서의 결과 변수 값 연결.

    Attributes:
        followup_name: 추적관찰 시점 이름
        outcome_name: 결과 변수 이름
        source_paper_id: 출처 논문 ID
        value: 결과값 (예: "85.2%", "2.3")
        baseline_value: 기준값
        improvement: 개선 정도
    """
    followup_name: str
    outcome_name: str
    source_paper_id: str = ""
    value: str = ""
    baseline_value: str = ""
    improvement: str = ""

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "source_paper_id": self.source_paper_id,
            "value": self.value[:100] if self.value else "",
            "baseline_value": self.baseline_value[:100] if self.baseline_value else "",
            "improvement": self.improvement[:100] if self.improvement else "",
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, followup_name: str, outcome_name: str) -> "ReportsOutcomeAtRelation":
        return cls(
            followup_name=followup_name,
            outcome_name=outcome_name,
            source_paper_id=record.get("source_paper_id", ""),
            value=record.get("value", ""),
            baseline_value=record.get("baseline_value", ""),
            improvement=record.get("improvement", ""),
        )


@dataclass
class ReportsCostRelation:
    """논문 → 비용 보고 관계 (v7.2).

    (Paper)-[:REPORTS_COST]->(Cost)

    연구에서 보고된 비용 데이터 연결.

    Attributes:
        paper_id: 논문 ID
        cost_name: 비용 항목 이름
        is_primary_analysis: 주요 비용 분석 여부
    """
    paper_id: str
    cost_name: str
    is_primary_analysis: bool = False

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "is_primary_analysis": self.is_primary_analysis,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, paper_id: str, cost_name: str) -> "ReportsCostRelation":
        return cls(
            paper_id=paper_id,
            cost_name=cost_name,
            is_primary_analysis=record.get("is_primary_analysis", False),
        )


@dataclass
class CostAssociatedWithRelation:
    """비용 → 수술법 연관 관계 (v7.2).

    (Cost)-[:ASSOCIATED_WITH]->(Intervention)

    비용 데이터가 연관된 수술법 연결.

    Attributes:
        cost_name: 비용 항목 이름
        intervention_name: 수술법 이름
        source_paper_id: 출처 논문 ID
        cost_value: 비용 값 (USD)
    """
    cost_name: str
    intervention_name: str
    source_paper_id: str = ""
    cost_value: float = 0.0

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "source_paper_id": self.source_paper_id,
            "cost_value": self.cost_value,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, cost_name: str, intervention_name: str) -> "CostAssociatedWithRelation":
        return cls(
            cost_name=cost_name,
            intervention_name=intervention_name,
            source_paper_id=record.get("source_paper_id", ""),
            cost_value=record.get("cost_value", 0.0),
        )


@dataclass
class HasQualityMetricRelation:
    """논문 → 품질 평가 관계 (v7.2).

    (Paper)-[:HAS_QUALITY_METRIC]->(QualityMetric)

    연구의 품질 평가 결과 연결.

    Attributes:
        paper_id: 논문 ID
        metric_name: 품질 평가 도구 이름 (예: "GRADE", "MINORS")
        assessed_by: 평가자 (author, reviewer, external)
        assessment_type: 평가 유형 (self, independent, consensus)
    """
    paper_id: str
    metric_name: str
    assessed_by: str = ""  # author, reviewer, external
    assessment_type: str = ""  # self, independent, consensus

    def to_neo4j_properties(self) -> dict:
        """Neo4j 관계 속성 딕셔너리로 변환."""
        return {
            "assessed_by": self.assessed_by,
            "assessment_type": self.assessment_type,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict, paper_id: str, metric_name: str) -> "HasQualityMetricRelation":
        return cls(
            paper_id=paper_id,
            metric_name=metric_name,
            assessed_by=record.get("assessed_by", ""),
            assessment_type=record.get("assessment_type", ""),
        )
