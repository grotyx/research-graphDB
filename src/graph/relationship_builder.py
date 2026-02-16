"""Relationship Builder for Neo4j Graph.

논문 데이터에서 Neo4j 관계 구축.
- Paper → Pathology (STUDIES)
- Paper → Intervention (INVESTIGATES)
- Intervention → Outcome (AFFECTS with statistics)
- Intervention → Intervention (IS_A taxonomy)
- Paper → Paper (SUPPORTS, CONTRADICTS, CITES, SIMILAR_TOPIC)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .neo4j_client import Neo4jClient
from .entity_normalizer import EntityNormalizer, NormalizationResult
from .spine_schema import (
    PaperNode, SpineSubDomain, EvidenceLevel, StudyDesign,
    # v1.1 new types
    OutcomeMeasureNode, RadiographicParameterNode, PredictionModelNode, RiskFactorNode,
    CausesRelation, HasRiskFactorRelation, PredictsRelation, CorrelatesRelation, UsesDeviceRelation,
    ComplicationNode,
)

# Citation types (knowledge.citation_extractor removed in v1.20.0)
from enum import Enum


class CitationType(Enum):
    """Citation relationship type between papers."""
    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    NEUTRAL = "neutral"
    BACKGROUND = "background"
    METHODOLOGICAL = "methodological"


@dataclass
class CitationInfo:
    """Citation information extracted from paper references."""
    cited_title: Optional[str] = None
    cited_authors: list[str] = field(default_factory=list)
    cited_year: Optional[int] = None
    citation_context: str = ""
    citation_type: CitationType = CitationType.NEUTRAL
    citation_text: str = ""
    confidence: float = 0.0

# Vision processor types
try:
    from builder.gemini_vision_processor import (
        ExtractedMetadata,
        ExtractedChunk,
        PICOData,
        StatisticsData,
    )
except ImportError:
    # Fallback: define minimal stub classes for type hints
    from typing import Any as _Any

    @dataclass
    class ExtractedMetadata:
        """Stub for type hints when vision processor not available."""
        title: str = ""
        authors: list[str] = field(default_factory=list)
        year: int = 0
        journal: str = ""
        doi: str = ""
        study_design: str = ""
        evidence_level: str = "5"
        sample_size: int = 0
        follow_up_months: int = 0

    @dataclass
    class ExtractedChunk:
        """Stub for type hints when vision processor not available."""
        section: str = ""
        content: str = ""
        tier: int = 2

    @dataclass
    class PICOData:
        """Stub for type hints when vision processor not available."""
        population: str = ""
        intervention: str = ""
        comparison: str = ""
        outcome: str = ""

    @dataclass
    class StatisticsData:
        """Stub for type hints when vision processor not available."""
        measure: str = ""
        value: Optional[_Any] = None
        p_value: Optional[float] = None
        effect_size: str = ""

logger = logging.getLogger(__name__)


def sanitize_doi(doi: Optional[str]) -> Optional[str]:
    """DOI 값을 정제하여 반환.

    Placeholder 값이나 유효하지 않은 DOI는 None으로 변환합니다.

    Args:
        doi: 원본 DOI 문자열

    Returns:
        유효한 DOI 또는 None
    """
    if not doi:
        return None

    doi_lower = doi.lower().strip()

    # Placeholder 패턴 필터링
    invalid_patterns = [
        "not provided",
        "n/a",
        "none",
        "null",
        "unknown",
        "unavailable",
        "pending",
    ]

    for pattern in invalid_patterns:
        if pattern in doi_lower:
            return None

    # DOI 형식 검증 (10.으로 시작해야 함)
    if not doi.strip().startswith("10."):
        return None

    return doi.strip()


# ===== Cypher Queries for v1.1 New Relationships =====

CREATE_RISK_FACTOR_CYPHER = '''
MERGE (rf:RiskFactor {name: $name})
ON CREATE SET rf.category = $category, rf.variable_type = $variable_type
RETURN rf
'''

CREATE_HAS_RISK_FACTOR_REL_CYPHER = '''
MATCH (p:Paper {paper_id: $paper_id})
MATCH (rf:RiskFactor {name: $risk_factor_name})
MERGE (p)-[r:HAS_RISK_FACTOR]->(rf)
ON CREATE SET
    r.odds_ratio = $odds_ratio,
    r.hazard_ratio = $hazard_ratio,
    r.p_value = $p_value,
    r.outcome_affected = $outcome_affected
RETURN r
'''

CREATE_COMPLICATION_CYPHER = '''
MERGE (c:Complication {name: $name})
ON CREATE SET c.category = $category, c.severity = $severity
RETURN c
'''

CREATE_CAUSES_REL_CYPHER = '''
MATCH (i:Intervention {name: $intervention_name})
MATCH (c:Complication {name: $complication_name})
MERGE (i)-[r:CAUSES]->(c)
ON CREATE SET r.incidence_rate = $incidence_rate, r.source_paper_id = $source_paper_id
RETURN r
'''

CREATE_RADIO_PARAMETER_CYPHER = '''
MERGE (rp:RadioParameter {name: $name})
ON CREATE SET rp.category = $category, rp.unit = $unit
RETURN rp
'''

CREATE_OUTCOME_MEASURE_CYPHER = '''
MERGE (om:OutcomeMeasure {name: $name})
ON CREATE SET om.category = $category, om.unit = $unit
RETURN om
'''

CREATE_CORRELATES_REL_CYPHER = '''
MATCH (rp:RadioParameter {name: $radio_param_name})
MATCH (om:OutcomeMeasure {name: $outcome_measure_name})
MERGE (rp)-[r:CORRELATES]->(om)
ON CREATE SET r.r_value = $r_value, r.p_value = $p_value, r.source_paper_id = $source_paper_id
RETURN r
'''

CREATE_PREDICTION_MODEL_CYPHER = '''
MERGE (pm:PredictionModel {name: $name})
ON CREATE SET
    pm.model_type = $model_type,
    pm.auc = $auc,
    pm.accuracy = $accuracy,
    pm.sensitivity = $sensitivity,
    pm.specificity = $specificity,
    pm.features = $features,
    pm.source_paper_id = $source_paper_id
RETURN pm
'''

CREATE_PREDICTS_REL_CYPHER = '''
MATCH (pm:PredictionModel {name: $model_name})
MATCH (o:Outcome {name: $outcome_name})
MERGE (pm)-[r:PREDICTS]->(o)
ON CREATE SET r.auc = $auc, r.accuracy = $accuracy
RETURN r
'''

CREATE_USES_FEATURE_REL_CYPHER = '''
MATCH (pm:PredictionModel {name: $model_name})
MATCH (rf:RiskFactor {name: $risk_factor_name})
MERGE (pm)-[r:USES_FEATURE]->(rf)
ON CREATE SET r.importance = $importance
RETURN r
'''

CREATE_USES_DEVICE_REL_CYPHER = '''
MATCH (i:Intervention {name: $intervention_name})
MATCH (impl:Implant {name: $implant_name})
MERGE (i)-[r:USES_DEVICE]->(impl)
ON CREATE SET r.frequency = $frequency, r.source_paper_id = $source_paper_id
RETURN r
'''


# ===== Cypher Queries for v1.2 New Relationships =====

CREATE_PATIENT_COHORT_CYPHER = '''
MERGE (pc:PatientCohort {name: $name, source_paper_id: $source_paper_id})
ON CREATE SET
    pc.cohort_type = $cohort_type,
    pc.sample_size = $sample_size,
    pc.mean_age = $mean_age,
    pc.age_sd = $age_sd,
    pc.female_percentage = $female_percentage,
    pc.diagnosis = $diagnosis
RETURN pc
'''

CREATE_HAS_COHORT_REL_CYPHER = '''
MATCH (p:Paper {paper_id: $paper_id})
MATCH (pc:PatientCohort {name: $cohort_name, source_paper_id: $paper_id})
MERGE (p)-[r:HAS_COHORT]->(pc)
ON CREATE SET r.is_primary = $is_primary, r.role = $role
RETURN r
'''

CREATE_TREATED_WITH_REL_CYPHER = '''
MATCH (pc:PatientCohort {name: $cohort_name, source_paper_id: $source_paper_id})
MATCH (i:Intervention {name: $intervention_name})
MERGE (pc)-[r:TREATED_WITH]->(i)
ON CREATE SET r.n_patients = $n_patients, r.source_paper_id = $source_paper_id
RETURN r
'''

CREATE_FOLLOWUP_CYPHER = '''
MERGE (fu:FollowUp {name: $name, source_paper_id: $source_paper_id})
ON CREATE SET
    fu.timepoint_months = $timepoint_months,
    fu.timepoint_type = $timepoint_type,
    fu.mean_followup_months = $mean_followup_months,
    fu.completeness_rate = $completeness_rate
RETURN fu
'''

CREATE_HAS_FOLLOWUP_REL_CYPHER = '''
MATCH (p:Paper {paper_id: $paper_id})
MATCH (fu:FollowUp {name: $followup_name, source_paper_id: $paper_id})
MERGE (p)-[r:HAS_FOLLOWUP]->(fu)
ON CREATE SET r.is_primary_endpoint = $is_primary_endpoint
RETURN r
'''

CREATE_REPORTS_OUTCOME_REL_CYPHER = '''
MATCH (fu:FollowUp {name: $followup_name, source_paper_id: $source_paper_id})
MATCH (o:Outcome {name: $outcome_name})
MERGE (fu)-[r:REPORTS_OUTCOME]->(o)
ON CREATE SET r.value = $value, r.improvement = $improvement, r.source_paper_id = $source_paper_id
RETURN r
'''

CREATE_COST_CYPHER = '''
MERGE (c:Cost {name: $name, source_paper_id: $source_paper_id})
ON CREATE SET
    c.cost_type = $cost_type,
    c.mean_cost = $mean_cost,
    c.currency = $currency,
    c.qaly_gained = $qaly_gained,
    c.icer = $icer
RETURN c
'''

CREATE_REPORTS_COST_REL_CYPHER = '''
MATCH (p:Paper {paper_id: $paper_id})
MATCH (c:Cost {name: $cost_name, source_paper_id: $paper_id})
MERGE (p)-[r:REPORTS_COST]->(c)
ON CREATE SET r.is_primary_analysis = $is_primary_analysis
RETURN r
'''

CREATE_COST_ASSOCIATED_WITH_REL_CYPHER = '''
MATCH (c:Cost {name: $cost_name, source_paper_id: $source_paper_id})
MATCH (i:Intervention {name: $intervention_name})
MERGE (c)-[r:ASSOCIATED_WITH]->(i)
ON CREATE SET r.cost_value = $cost_value, r.source_paper_id = $source_paper_id
RETURN r
'''

CREATE_QUALITY_METRIC_CYPHER = '''
MERGE (qm:QualityMetric {name: $name, source_paper_id: $source_paper_id})
ON CREATE SET
    qm.assessment_tool = $assessment_tool,
    qm.overall_score = $overall_score,
    qm.max_score = $max_score,
    qm.overall_rating = $overall_rating,
    qm.grade_certainty = $grade_certainty
RETURN qm
'''

CREATE_HAS_QUALITY_METRIC_REL_CYPHER = '''
MATCH (p:Paper {paper_id: $paper_id})
MATCH (qm:QualityMetric {name: $metric_name, source_paper_id: $paper_id})
MERGE (p)-[r:HAS_QUALITY_METRIC]->(qm)
ON CREATE SET r.assessed_by = $assessed_by, r.assessment_type = $assessment_type
RETURN r
'''


@dataclass
class SpineMetadata:
    """척추 특화 메타데이터.

    Vision processor가 추출한 척추 관련 정보.

    v1.0 변경사항:
    - summary: 700+ word comprehensive summary
    - processing_version: Pipeline version tracking
    - citation_count: Optional citation metrics
    - PICO fields: Deprecated but kept for backward compatibility

    v3.2 변경사항:
    - sub_domains: 다중 분류 지원 (list)
    - surgical_approach: 수술 접근법 (list)

    v3.0 변경사항:
    - PICO 필드 추가 (chunk에서 이동)
    """
    # 분류 (v3.2: 다중 선택 가능)
    sub_domains: list[str] = field(default_factory=list)  # ["Degenerative", "Revision"]
    sub_domain: str = ""  # deprecated, sub_domains 사용 권장

    # 수술 접근법 (v3.2: 다중 선택 가능)
    surgical_approach: list[str] = field(default_factory=list)  # ["Endoscopic", "Minimally Invasive"]

    anatomy_levels: list[str] = field(default_factory=list)  # ["L4-5", "C5-6"]
    pathologies: list[str] = field(default_factory=list)  # ["Lumbar Stenosis", "AIS"]
    interventions: list[str] = field(default_factory=list)  # ["TLIF", "UBE"]
    outcomes: list[dict] = field(default_factory=list)  # [{name, value, p_value}]
    main_conclusion: str = ""  # 핵심 결론 1문장

    # v1.0 New fields
    summary: str = ""             # 700+ word comprehensive summary
    processing_version: str = ""  # "v1.0" for new pipeline
    citation_count: int = 0       # Number of citations (optional)

    # PICO (v3.0 - chunk에서 이동, v1.0에서 deprecated)
    pico_population: str = ""     # 연구 대상
    pico_intervention: str = ""   # 중재
    pico_comparison: str = ""     # 비교 대상
    pico_outcome: str = ""        # 결과 변수

    # v1.2 Extended entity fields
    patient_cohorts: list[dict] = field(default_factory=list)  # [{name, cohort_type, sample_size, mean_age, ...}]
    followups: list[dict] = field(default_factory=list)  # [{name, timepoint_months, completeness_rate, ...}]
    costs: list[dict] = field(default_factory=list)  # [{name, cost_type, mean_cost, currency, ...}]
    quality_metrics: list[dict] = field(default_factory=list)  # [{name, assessment_tool, overall_score, ...}]


@dataclass
class ExtractedOutcome:
    """추출된 결과변수 (Unified Schema v4.0).

    Claude와 Gemini PDF 처리기 모두 지원.
    - Claude: baseline, final 형식
    - Gemini: value_intervention, value_control 형식
    """
    name: str
    # === 결과값 (여러 형식 지원) ===
    value: str = ""                          # 단일 값 또는 요약값
    baseline: Optional[float] = None          # Claude 형식: 수술 전 값
    final: Optional[float] = None             # Claude 형식: 최종값
    value_intervention: str = ""              # Gemini 형식: 중재군 값
    value_control: str = ""                   # Gemini 형식: 대조군 값
    value_difference: str = ""                # 차이값
    # === 통계 정보 ===
    p_value: Optional[float] = None
    effect_size: str = ""
    confidence_interval: str = ""
    is_significant: bool = False
    # === 메타데이터 ===
    direction: str = ""                       # improved, worsened, unchanged
    category: str = ""                        # pain, function, radiologic, complication
    timepoint: str = ""                       # preop, postop, 6mo, 1yr, 2yr, final


@dataclass
class BuildResult:
    """관계 구축 결과."""
    paper_id: str
    nodes_created: int
    relationships_created: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PaperRelationResult:
    """논문 관계 구축 결과."""
    relations_created: int
    matched_citations: list[tuple[CitationInfo, str]] = field(default_factory=list)
    unmatched_citations: list[CitationInfo] = field(default_factory=list)
    similarity_relations: int = 0


# --- v1.20.0: LLM Entity Classification ---

_CLASSIFY_ENTITY_PROMPT = """You are a spine surgery terminology expert.

Term: "{entity_text}"
Type: {entity_type}

Is this term a synonym/variant of any canonical concept below?

{candidates}

Respond JSON only:
{{"match": "canonical_name_or_null", "confidence": 0.0-1.0, "reason": "brief"}}

Rules:
- confidence >= 0.9: definite match (same medical concept, different wording)
- confidence 0.7-0.89: probable match (closely related but uncertain)
- confidence < 0.7 or match=null: genuinely different concept
- Do NOT force-match unrelated concepts. When in doubt, return null."""


async def classify_unmatched_entity(
    entity_text: str,
    entity_type: str,
    candidates: list[str],
    llm_client,
) -> tuple[str, float] | None:
    """Claude Haiku로 미매칭 엔티티를 기존 canonical에 분류.

    Args:
        entity_text: 정규화 실패한 원본 텍스트
        entity_type: 엔티티 유형
        candidates: rapidfuzz로 사전 필터링된 후보 목록 (최대 30개)
        llm_client: LLM 클라이언트 인스턴스

    Returns:
        (canonical_name, confidence) 또는 None (매칭 없음/신규 개념)
    """
    if not llm_client or not candidates:
        return None

    prompt = _CLASSIFY_ENTITY_PROMPT.format(
        entity_text=entity_text,
        entity_type=entity_type,
        candidates="\n".join(f"- {c}" for c in candidates[:30]),
    )

    schema = {
        "type": "object",
        "properties": {
            "match": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["match", "confidence", "reason"],
    }

    try:
        result = await llm_client.generate_json(prompt, schema)
        matched = result.get("match")
        confidence = float(result.get("confidence", 0.0))

        if matched and confidence >= 0.85 and matched in candidates:
            logger.info(
                f"LLM classify: '{entity_text}' → '{matched}' "
                f"(conf={confidence:.2f})"
            )
            return (matched, confidence)

        return None
    except Exception as e:
        logger.warning(f"LLM classify failed for '{entity_text}': {e}")
        return None


class RelationshipBuilder:
    """논문 데이터에서 Neo4j 관계 구축.

    사용 예:
        builder = RelationshipBuilder(neo4j_client, normalizer)
        result = await builder.build_from_paper(
            paper_id="paper_001",
            metadata=extracted_metadata,
            spine_metadata=spine_metadata,
            chunks=chunks
        )
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        normalizer: EntityNormalizer,
        llm_client=None,
    ) -> None:
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            normalizer: 엔티티 정규화기
            llm_client: LLM 클라이언트 (v1.20.0: 미매칭 엔티티 LLM 폴백용)
        """
        self.client: Neo4jClient = neo4j_client
        self.normalizer: EntityNormalizer = normalizer
        self.llm_client = llm_client
        self._llm_call_count: int = 0
        self._llm_call_limit: int = 10

    async def _normalize_with_fallback(
        self,
        text: str,
        entity_type: str,
    ) -> NormalizationResult:
        """5단계 정규화 + LLM 폴백.

        Flow:
        1. normalize_X(text) -> confidence > 0 이면 즉시 반환
        2. LLM client 없거나 rate limit 초과 -> 원본 반환
        3. _get_candidate_canonicals()로 후보 30개 추출
        4. classify_unmatched_entity() LLM 호출
        5. 매칭 성공 -> register_dynamic_alias() + 재정규화
        6. 매칭 실패 -> 원본 반환 (기존 동작)
        """
        normalize_fn = getattr(self.normalizer, f"normalize_{entity_type}")
        result = normalize_fn(text)

        if result.confidence > 0.0:
            return result

        # LLM 폴백 조건 체크
        if not self.llm_client:
            return result
        if entity_type not in ("intervention", "outcome", "pathology"):
            return result  # anatomy는 패턴 기반으로 충분
        if self._llm_call_count >= self._llm_call_limit:
            return result

        self._llm_call_count += 1

        candidates = self.normalizer._get_candidate_canonicals(
            text, entity_type, top_k=30
        )
        if not candidates:
            return result

        llm_result = await classify_unmatched_entity(
            entity_text=text,
            entity_type=entity_type,
            candidates=candidates,
            llm_client=self.llm_client,
        )

        if llm_result:
            canonical, confidence = llm_result
            self.normalizer.register_dynamic_alias(
                entity_type=entity_type,
                alias=text,
                canonical=canonical,
            )
            # 재정규화 (이제 alias가 등록되었으므로 exact match됨)
            result = normalize_fn(text)
            result.method = f"llm_classified+{result.method}"
            return result

        return result

    async def build_from_paper(
        self,
        paper_id: str,
        metadata: "ExtractedMetadata",
        spine_metadata: SpineMetadata,
        chunks: list["ExtractedChunk"],
        build_paper_relations: bool = True,
        owner: str = "system",  # v1.5: 소유자 ID
        shared: bool = True     # v1.5: 공유 여부
    ) -> BuildResult:
        """논문으로부터 전체 그래프 구축.

        Args:
            paper_id: 논문 ID
            metadata: 추출된 메타데이터
            spine_metadata: 척추 특화 메타데이터
            chunks: 추출된 청크 목록
            build_paper_relations: 논문 간 관계도 구축할지 여부
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)

        Returns:
            BuildResult
        """
        result: BuildResult = BuildResult(paper_id=paper_id, nodes_created=0, relationships_created=0)

        # v1.20.0: 논문당 LLM 폴백 호출 카운터 리셋
        self._llm_call_count = 0

        try:
            # 1. Paper 노드 생성
            await self.create_paper_node(paper_id, metadata, spine_metadata, owner=owner, shared=shared)
            result.nodes_created += 1
            logger.info(f"Created Paper node: {paper_id}")

            # 2. Paper → Pathology (STUDIES) 관계
            if spine_metadata.pathologies:
                studies_count = await self.create_studies_relations(
                    paper_id, spine_metadata.pathologies
                )
                result.relationships_created += studies_count
                logger.info(f"Created {studies_count} STUDIES relations")
            else:
                result.warnings.append("No pathologies found")

            # 3. Paper → Anatomy (INVOLVES) 관계
            if spine_metadata.anatomy_levels:
                involves_count = await self.create_involves_relations(
                    paper_id, spine_metadata.anatomy_levels
                )
                result.relationships_created += involves_count
                logger.info(f"Created {involves_count} INVOLVES relations")
            else:
                result.warnings.append("No anatomy levels found")

            # 4. Paper → Intervention (INVESTIGATES) 관계
            if spine_metadata.interventions:
                investigates_count = await self.create_investigates_relations(
                    paper_id, spine_metadata.interventions
                )
                result.relationships_created += investigates_count
                logger.info(f"Created {investigates_count} INVESTIGATES relations")
            else:
                result.warnings.append("No interventions found")

            # 4.5. Intervention → Pathology (TREATS) 관계
            if spine_metadata.interventions and spine_metadata.pathologies:
                treats_count = await self.create_treats_relations(
                    paper_id, spine_metadata.interventions, spine_metadata.pathologies
                )
                result.relationships_created += treats_count
                logger.info(f"Created {treats_count} TREATS relations")

            # 5. Intervention → Outcome (AFFECTS) 관계 (통계 포함)
            outcomes = self._extract_outcomes_from_chunks(chunks, spine_metadata)
            if outcomes:
                for intervention in spine_metadata.interventions:
                    affects_count = await self.create_affects_relations(
                        intervention, outcomes, paper_id
                    )
                    result.relationships_created += affects_count
                logger.info(f"Created AFFECTS relations for {len(outcomes)} outcomes")
            else:
                result.warnings.append("No outcomes with statistics found")

            # 6. Intervention → Taxonomy 연결
            for intervention in spine_metadata.interventions:
                linked = await self.link_intervention_to_taxonomy(intervention)
                if linked:
                    logger.debug(f"Linked {intervention} to taxonomy")
                else:
                    result.warnings.append(f"Could not link {intervention} to taxonomy")

            # 7. v1.1 New Relationships
            # Risk factors (if present in metadata)
            if hasattr(spine_metadata, 'risk_factors') and spine_metadata.risk_factors:
                rf_count = await self._create_risk_factor_relationships(
                    paper_id, spine_metadata.risk_factors
                )
                result.relationships_created += rf_count
                logger.info(f"Created {rf_count} HAS_RISK_FACTOR relations")

            # Complications (extract from outcomes or chunks)
            for intervention in spine_metadata.interventions:
                complications = self._extract_complications_from_chunks(chunks, intervention)
                if complications:
                    comp_count = await self._create_complication_relationships(
                        intervention, complications, paper_id
                    )
                    result.relationships_created += comp_count
                    logger.info(f"Created {comp_count} CAUSES relations for {intervention}")

            # Radiographic correlations (if present in metadata)
            if hasattr(spine_metadata, 'radiographic_correlations') and spine_metadata.radiographic_correlations:
                corr_count = await self._create_radiographic_relationships(
                    spine_metadata.radiographic_correlations, paper_id
                )
                result.relationships_created += corr_count
                logger.info(f"Created {corr_count} CORRELATES relations")

            # Prediction models (if present in metadata)
            if hasattr(spine_metadata, 'prediction_models') and spine_metadata.prediction_models:
                model_count = await self._create_prediction_model_relationships(
                    spine_metadata.prediction_models, paper_id
                )
                result.relationships_created += model_count
                logger.info(f"Created {model_count} prediction models")

            # Implant usage (if present in metadata)
            for intervention in spine_metadata.interventions:
                if hasattr(spine_metadata, 'implants') and spine_metadata.implants:
                    implant_count = await self._create_uses_device_relationships(
                        intervention, spine_metadata.implants, paper_id
                    )
                    result.relationships_created += implant_count
                    logger.info(f"Created {implant_count} USES_DEVICE relations for {intervention}")

            # 8. v1.2 New Relationships
            # Patient Cohorts
            if hasattr(spine_metadata, 'patient_cohorts') and spine_metadata.patient_cohorts:
                cohort_count = await self._create_cohort_relationships(
                    paper_id, spine_metadata.patient_cohorts
                )
                result.relationships_created += cohort_count
                logger.info(f"Created {cohort_count} HAS_COHORT relations")

            # Follow-up timepoints
            if hasattr(spine_metadata, 'followups') and spine_metadata.followups:
                followup_count = await self._create_followup_relationships(
                    paper_id, spine_metadata.followups
                )
                result.relationships_created += followup_count
                logger.info(f"Created {followup_count} HAS_FOLLOWUP relations")

            # Cost data
            if hasattr(spine_metadata, 'costs') and spine_metadata.costs:
                cost_count = await self._create_cost_relationships(
                    paper_id, spine_metadata.costs
                )
                result.relationships_created += cost_count
                logger.info(f"Created {cost_count} REPORTS_COST relations")

            # Quality metrics
            if hasattr(spine_metadata, 'quality_metrics') and spine_metadata.quality_metrics:
                qm_count = await self._create_quality_metric_relationships(
                    paper_id, spine_metadata.quality_metrics
                )
                result.relationships_created += qm_count
                logger.info(f"Created {qm_count} HAS_QUALITY_METRIC relations")

            # 9. Paper → Paper 관계 구축 (optional)
            if build_paper_relations:
                try:
                    # 기존 논문 목록 조회 (최근 100개) - 관계 정보 포함
                    existing_papers = await self.client.get_all_papers_with_relations(limit=100)

                    # 메타데이터를 딕셔너리로 변환
                    metadata_dict = {
                        "title": metadata.title,
                        "authors": metadata.authors,
                        "year": metadata.year,
                        "journal": metadata.journal,
                        "doi": metadata.doi,
                        "abstract": getattr(metadata, "abstract", ""),
                        "pathologies": spine_metadata.pathologies,
                        "interventions": spine_metadata.interventions,
                        "anatomy_levels": spine_metadata.anatomy_levels,
                        "sub_domain": spine_metadata.sub_domain,
                        "sub_domains": getattr(spine_metadata, 'sub_domains', []) or [],
                        "surgical_approach": getattr(spine_metadata, 'surgical_approach', []) or [],
                    }

                    # 유사도 기반 관계 구축
                    similarity_count = await self.build_similarity_relations(
                        paper_id, metadata_dict, existing_papers
                    )
                    result.relationships_created += similarity_count
                    logger.info(f"Created {similarity_count} SIMILAR_TOPIC relations")

                    # 인용 기반 관계 구축 (chunks에서 인용 추출)
                    # Note: 실제 인용 추출은 citation_extractor를 통해 수행됨
                    # 여기서는 인터페이스만 제공
                    logger.debug("Citation-based relations should be built via citation_extractor")

                except Exception as e:
                    logger.warning(f"Failed to build paper relations: {e}")
                    result.warnings.append(f"Paper relations error: {str(e)}")

        except Exception as e:
            logger.error(f"Build error for {paper_id}: {e}", exc_info=True)
            result.errors.append(str(e))

        return result

    async def create_paper_node(
        self,
        paper_id: str,
        metadata: "ExtractedMetadata",
        spine_metadata: SpineMetadata,
        owner: str = "system",  # v1.5: 소유자 ID
        shared: bool = True     # v1.5: 공유 여부
    ) -> None:
        """Paper 노드 생성.

        Args:
            paper_id: 논문 ID
            metadata: 추출된 메타데이터
            spine_metadata: 척추 특화 메타데이터
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)
        """
        # v3.2: sub_domains 우선, 없으면 sub_domain에서 생성
        sub_domains = getattr(spine_metadata, 'sub_domains', []) or []
        sub_domain = getattr(spine_metadata, 'sub_domain', '') or ""
        if not sub_domains and sub_domain:
            sub_domains = [sub_domain]

        paper: PaperNode = PaperNode(
            paper_id=paper_id,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            journal=metadata.journal,
            doi=sanitize_doi(metadata.doi),  # v1.14.23: DOI placeholder 필터링
            pmid=getattr(metadata, 'pmid', '') or "",
            # v3.2: 다중 분류 지원
            sub_domain=sub_domain or (sub_domains[0] if sub_domains else ""),
            sub_domains=sub_domains,
            surgical_approach=getattr(spine_metadata, 'surgical_approach', []) or [],
            study_type=getattr(metadata, 'study_type', '') or "",
            study_design=getattr(metadata, 'study_design', '') or "",
            evidence_level=metadata.evidence_level,
            sample_size=getattr(metadata, 'sample_size', 0) or 0,
            centers=getattr(metadata, 'centers', '') or "",
            blinding=getattr(metadata, 'blinding', '') or "",
            follow_up_months=getattr(spine_metadata, 'follow_up_months', 0) or 0,
            abstract=getattr(metadata, 'abstract', '') or "",
            main_conclusion=getattr(spine_metadata, 'main_conclusion', '') or "",
            # v1.0 New fields
            summary=getattr(spine_metadata, 'summary', '') or "",
            processing_version=getattr(spine_metadata, 'processing_version', '') or "",
            citation_count=getattr(spine_metadata, 'citation_count', 0) or 0,
            # PICO (v3.0 - spine_metadata에서 매핑, v1.0에서 deprecated)
            pico_population=getattr(spine_metadata, 'pico_population', '') or "",
            pico_intervention=getattr(spine_metadata, 'pico_intervention', '') or "",
            pico_comparison=getattr(spine_metadata, 'pico_comparison', '') or "",
            pico_outcome=getattr(spine_metadata, 'pico_outcome', '') or "",
            # v1.5: 멀티유저 지원
            owner=owner,
            shared=shared,
        )

        await self.client.create_paper(paper)

    async def create_studies_relations(
        self,
        paper_id: str,
        pathologies: list[str]
    ) -> int:
        """Paper → Pathology (STUDIES) 관계 생성.

        v1.9: SNOMED-CT 코드 지원 추가

        Args:
            paper_id: 논문 ID
            pathologies: 질환명 목록

        Returns:
            생성된 관계 수
        """
        count = 0

        # 중첩 리스트 평탄화 및 문자열 변환
        flat_pathologies = []
        for item in pathologies:
            if isinstance(item, list):
                # 중첩 리스트인 경우 평탄화
                flat_pathologies.extend([str(p) for p in item if p])
            elif item:
                flat_pathologies.append(str(item))

        for idx, pathology in enumerate(flat_pathologies):
            # 정규화 (SNOMED 코드 포함, v1.20.0: LLM 폴백)
            norm_result = await self._normalize_with_fallback(pathology, "pathology")
            pathology_name = norm_result.normalized

            # 첫 번째를 primary로 설정
            is_primary = (idx == 0)

            try:
                await self.client.create_studies_relation(
                    paper_id=paper_id,
                    pathology_name=pathology_name,
                    is_primary=is_primary,
                    snomed_code=norm_result.snomed_code if norm_result.snomed_code else None,
                    snomed_term=norm_result.snomed_term if norm_result.snomed_term else None
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to create STUDIES relation for {pathology_name}: {e}")

        return count

    async def create_involves_relations(
        self,
        paper_id: str,
        anatomy_levels: list[str]
    ) -> int:
        """Paper → Anatomy (INVOLVES) 관계 생성.

        Args:
            paper_id: 논문 ID
            anatomy_levels: 해부학적 위치 목록 (예: ["L4-5", "Lumbar"])

        Returns:
            생성된 관계 수
        """
        count = 0

        # 중첩 리스트 평탄화 및 문자열 변환
        flat_anatomy = []
        for item in anatomy_levels:
            if isinstance(item, list):
                flat_anatomy.extend([str(a) for a in item if a])
            elif item:
                flat_anatomy.append(str(item))

        for anatomy in flat_anatomy:
            if not anatomy:
                continue

            # 정규화 (SNOMED 코드 포함) — v1.19.5
            norm_result = self.normalizer.normalize_anatomy(anatomy)
            anatomy_name = norm_result.normalized

            # 레벨과 영역 추출
            level, region = self._parse_anatomy_level(anatomy_name)

            try:
                await self.client.create_involves_relation(
                    paper_id=paper_id,
                    anatomy_name=anatomy_name,
                    level=level,
                    region=region,
                    snomed_code=norm_result.snomed_code if norm_result.snomed_code else None,
                    snomed_term=norm_result.snomed_term if norm_result.snomed_term else None,
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to create INVOLVES relation for {anatomy}: {e}")

        return count

    def _parse_anatomy_level(self, anatomy: str) -> tuple[str, str]:
        """해부학적 위치에서 레벨과 영역 추출.

        Args:
            anatomy: 해부학적 위치 문자열 (예: "L4-5", "Cervical", "C5-C6")

        Returns:
            (level, region) 튜플
        """
        anatomy_lower = anatomy.lower()

        # 레벨 결정
        if any(x in anatomy_lower for x in ["l1", "l2", "l3", "l4", "l5", "lumbar"]):
            level = "lumbar"
        elif any(x in anatomy_lower for x in ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "cervical"]):
            level = "cervical"
        elif any(x in anatomy_lower for x in ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10", "t11", "t12", "thoracic"]):
            level = "thoracic"
        elif any(x in anatomy_lower for x in ["s1", "s2", "s3", "s4", "s5", "sacral"]):
            level = "sacral"
        else:
            level = ""

        # 영역은 원본 그대로 사용
        region = anatomy

        return level, region

    async def create_investigates_relations(
        self,
        paper_id: str,
        interventions: list[str]
    ) -> int:
        """Paper → Intervention (INVESTIGATES) 관계 생성.

        Args:
            paper_id: 논문 ID
            interventions: 수술법 목록

        Returns:
            생성된 관계 수
        """
        count = 0

        # 중첩 리스트 평탄화 및 문자열 변환
        flat_interventions = []
        for item in interventions:
            if isinstance(item, list):
                flat_interventions.extend([str(i) for i in item if i])
            elif item:
                flat_interventions.append(str(item))

        for intervention in flat_interventions:
            # 정규화 (SNOMED 코드 포함, v1.20.0: LLM 폴백)
            norm_result = await self._normalize_with_fallback(intervention, "intervention")
            intervention_name = norm_result.normalized

            try:
                await self.client.create_investigates_relation(
                    paper_id=paper_id,
                    intervention_name=intervention_name,
                    is_comparison=False,  # 추후 PICO의 comparison에서 판단
                    category=norm_result.category if norm_result.category else None,
                    snomed_code=norm_result.snomed_code if norm_result.snomed_code else None,
                    snomed_term=norm_result.snomed_term if norm_result.snomed_term else None
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to create INVESTIGATES relation for {intervention_name}: {e}")

        return count

    async def create_treats_relations(
        self,
        paper_id: str,
        interventions: list[str],
        pathologies: list[str]
    ) -> int:
        """Intervention → Pathology (TREATS) 관계 생성.

        논문에서 추출된 수술법-질환 쌍에 대해 TREATS 관계를 생성.
        v1.16.1: TREATS 관계 구현.

        Args:
            paper_id: 출처 논문 ID
            interventions: 수술법 목록
            pathologies: 질환 목록

        Returns:
            생성된 관계 수
        """
        count = 0

        # 리스트 평탄화
        flat_interventions = []
        for item in interventions:
            if isinstance(item, list):
                flat_interventions.extend([str(i) for i in item if i])
            elif item:
                flat_interventions.append(str(item))

        flat_pathologies = []
        for item in pathologies:
            if isinstance(item, list):
                flat_pathologies.extend([str(p) for p in item if p])
            elif item:
                flat_pathologies.append(str(item))

        for intervention in flat_interventions:
            norm_intervention = await self._normalize_with_fallback(intervention, "intervention")
            intervention_name = norm_intervention.normalized

            for pathology in flat_pathologies:
                norm_pathology = await self._normalize_with_fallback(pathology, "pathology")
                pathology_name = norm_pathology.normalized

                try:
                    await self.client.create_treats_relation(
                        intervention_name=intervention_name,
                        pathology_name=pathology_name,
                        source_paper_id=paper_id,
                    )
                    count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to create TREATS relation "
                        f"{intervention_name} -> {pathology_name}: {e}"
                    )

        return count

    async def create_affects_relations(
        self,
        intervention: str,
        outcomes: list[ExtractedOutcome],
        paper_id: str
    ) -> int:
        """Intervention → Outcome (AFFECTS) 관계 생성 (통계 포함).

        Claude와 Gemini PDF 처리기 결과 모두 지원 (Unified Schema v4.0).
        v1.9: SNOMED-CT 코드 지원 추가

        Args:
            intervention: 수술법 이름
            outcomes: 결과변수 목록
            paper_id: 출처 논문 ID

        Returns:
            생성된 관계 수
        """
        count = 0

        # 수술법 정규화 (v1.20.0: LLM 폴백)
        norm_intervention = await self._normalize_with_fallback(intervention, "intervention")
        intervention_name = norm_intervention.normalized

        for outcome in outcomes:
            # 결과변수 정규화 (SNOMED 코드 포함, v1.20.0: LLM 폴백)
            norm_outcome = await self._normalize_with_fallback(outcome.name, "outcome")
            outcome_name = norm_outcome.normalized

            try:
                await self.client.create_affects_relation(
                    intervention_name=intervention_name,
                    outcome_name=outcome_name,
                    source_paper_id=paper_id,
                    # 기본 값
                    value=outcome.value,
                    value_control=outcome.value_control,
                    p_value=outcome.p_value,
                    effect_size=outcome.effect_size,
                    confidence_interval=outcome.confidence_interval,
                    is_significant=outcome.is_significant,
                    direction=outcome.direction,
                    # v4.0 추가 필드
                    baseline=outcome.baseline,
                    final=outcome.final,
                    value_intervention=outcome.value_intervention,
                    value_difference=outcome.value_difference,
                    category=outcome.category,
                    timepoint=outcome.timepoint,
                    # v1.9: SNOMED 코드
                    snomed_code=norm_outcome.snomed_code if norm_outcome.snomed_code else None,
                    snomed_term=norm_outcome.snomed_term if norm_outcome.snomed_term else None
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to create AFFECTS relation for {outcome_name}: {e}")

        return count

    async def link_intervention_to_taxonomy(self, intervention_name: str) -> bool:
        """수술법을 Taxonomy에 연결.

        IS_A 관계를 통해 수술법 계층에 연결.
        이미 initialize_schema()에서 생성된 taxonomy 노드에 연결.
        Taxonomy에 없는 경우 유사한 수술법을 찾아 자동으로 IS_A 관계 생성.

        Args:
            intervention_name: 수술법 이름 (정규화 필요)

        Returns:
            성공 여부
        """
        try:
            # 정규화
            norm_result = self.normalizer.normalize_intervention(intervention_name)
            canonical_name = norm_result.normalized

            # Taxonomy에 이미 존재하는지 확인
            hierarchy = await self.client.get_intervention_hierarchy(canonical_name)

            if hierarchy:
                logger.debug(f"{canonical_name} already in taxonomy")
                return True

            # Taxonomy에 없는 경우 - 유사한 수술법 찾아서 자동 연결
            logger.info(f"{canonical_name} not in taxonomy - attempting auto-link")

            # 카테고리 기반 부모 결정
            parent_intervention = self._determine_parent_intervention(canonical_name, norm_result)

            if parent_intervention:
                # IS_A 관계 생성
                query = """
                MERGE (child:Intervention {name: $child_name})
                ON CREATE SET child.created_at = datetime(),
                              child.category = $category,
                              child.auto_linked = true
                WITH child
                MATCH (parent:Intervention {name: $parent_name})
                MERGE (child)-[r:IS_A]->(parent)
                ON CREATE SET r.auto_generated = true,
                              r.created_at = datetime()
                RETURN child.name as child, parent.name as parent
                """
                result = await self.client.run_query(
                    query,
                    {
                        "child_name": canonical_name,
                        "parent_name": parent_intervention,
                        "category": norm_result.category or "unknown"
                    },
                    fetch_all=False
                )

                if result:
                    logger.info(f"Auto-linked {canonical_name} -> IS_A -> {parent_intervention}")
                    return True

            logger.warning(f"Could not auto-link {canonical_name} to taxonomy")
            return False

        except Exception as e:
            logger.error(f"Failed to link {intervention_name} to taxonomy: {e}", exc_info=True)
            return False

    def _determine_parent_intervention(self, intervention_name: str, norm_result) -> Optional[str]:
        """수술법의 부모 카테고리 결정.

        Args:
            intervention_name: 정규화된 수술법 이름
            norm_result: 정규화 결과 (category 포함)

        Returns:
            부모 수술법 이름 또는 None
        """
        # 카테고리별 기본 부모 매핑
        category_parent_map = {
            "fusion": "Fusion Surgery",
            "interbody_fusion": "Interbody Fusion",
            "decompression": "Decompression Surgery",
            "endoscopic": "Endoscopic Surgery",
            "microscopic": "Microscopic Surgery",
            "motion_preservation": "Motion Preservation Surgery",
            "fixation": "Fixation",
            "osteotomy": "Osteotomy Surgery",
            "augmentation": "Vertebral Augmentation",
        }

        # 이름 패턴 기반 부모 결정
        name_lower = intervention_name.lower()

        # 특정 패턴 매칭
        if any(kw in name_lower for kw in ["fusion", "tlif", "plif", "alif", "olif", "llif", "acdf"]):
            if any(kw in name_lower for kw in ["tlif", "plif", "alif", "olif", "llif"]):
                return "Interbody Fusion"
            return "Fusion Surgery"

        if any(kw in name_lower for kw in ["ube", "bess", "biportal", "endoscop", "feld", "peld"]):
            return "Endoscopic Surgery"

        if any(kw in name_lower for kw in ["microscop", "med", "microdecompression"]):
            return "Microscopic Surgery"

        if any(kw in name_lower for kw in ["laminectomy", "laminotomy", "foraminotomy", "decompression"]):
            return "Decompression Surgery"

        if any(kw in name_lower for kw in ["disc replacement", "adr", "dynamic stabiliz"]):
            return "Motion Preservation Surgery"

        if any(kw in name_lower for kw in ["screw", "fixation", "instrumentation"]):
            return "Fixation"

        if any(kw in name_lower for kw in ["osteotomy", "pso", "spo", "vcr"]):
            return "Osteotomy Surgery"

        if any(kw in name_lower for kw in ["vertebroplasty", "kyphoplasty", "pvp", "pkp", "augmentation"]):
            return "Vertebral Augmentation"

        # 카테고리 기반 폴백
        category = getattr(norm_result, "category", None)
        if category and category in category_parent_map:
            return category_parent_map[category]

        return None

    def _extract_outcomes_from_chunks(
        self,
        chunks: list["ExtractedChunk"],
        spine_metadata: SpineMetadata
    ) -> list[ExtractedOutcome]:
        """청크에서 결과변수 추출.

        Results 섹션의 통계 데이터를 우선적으로 추출.

        Args:
            chunks: 추출된 청크 목록
            spine_metadata: 척추 메타데이터 (outcomes 포함)

        Returns:
            ExtractedOutcome 목록
        """
        outcomes: list[ExtractedOutcome] = []

        # 1. spine_metadata의 outcomes 사용 (이미 추출된 데이터)
        for outcome_item in spine_metadata.outcomes:
            # Handle both dict and string types (v1.7 fix)
            if isinstance(outcome_item, str):
                outcome_dict = {"name": outcome_item}
            elif isinstance(outcome_item, dict):
                outcome_dict = outcome_item
            else:
                logger.warning(f"Unexpected outcome type: {type(outcome_item)}, skipping")
                continue

            # p_value 파싱 (문자열 또는 숫자 처리)
            raw_p = outcome_dict.get("p_value")
            p_val = self._parse_p_value_from_any(raw_p)

            # is_significant 결정
            is_sig = outcome_dict.get("is_significant", False)
            if not is_sig and p_val is not None:
                is_sig = p_val < 0.05

            # baseline/final 파싱 (Claude 형식)
            baseline = self._parse_float_value(outcome_dict.get("baseline"))
            final = self._parse_float_value(outcome_dict.get("final"))

            outcomes.append(ExtractedOutcome(
                name=outcome_dict.get("name", ""),
                # === 결과값 (여러 형식 지원) ===
                value=str(outcome_dict.get("value", "")),
                baseline=baseline,
                final=final,
                value_intervention=str(outcome_dict.get("value_intervention", "")),
                value_control=str(outcome_dict.get("value_control", "")),
                value_difference=str(outcome_dict.get("value_difference", "")),
                # === 통계 정보 ===
                p_value=p_val,
                effect_size=str(outcome_dict.get("effect_size", "")),
                confidence_interval=str(outcome_dict.get("confidence_interval", "")),
                is_significant=is_sig,
                # === 메타데이터 ===
                direction=outcome_dict.get("direction", "") or self._determine_direction(outcome_dict),
                category=str(outcome_dict.get("category", "")),
                timepoint=str(outcome_dict.get("timepoint", ""))
            ))

        # 2. 청크의 statistics에서 추가 추출 (results 섹션 우선)
        for chunk in chunks:
            # Support both ExtractedChunk objects and dict (from LLM text processing)
            # v1.14.27: None 값 처리
            if isinstance(chunk, dict):
                section_type = chunk.get("section_type") or ""
                statistics = chunk.get("statistics") or {}
                keywords = chunk.get("keywords") or []
            else:
                section_type = getattr(chunk, "section_type", "")
                statistics = getattr(chunk, "statistics", None)
                keywords = getattr(chunk, "keywords", []) or []

            if section_type == "results" and statistics:
                # statistics가 dict인 경우 처리 (dict 또는 객체 모두 지원)
                # v1.14: p_values (list) 와 p_value (string) 모두 지원
                if isinstance(statistics, dict):
                    p_values = statistics.get("p_values") or []
                    if not p_values:
                        p_value_str = statistics.get("p_value") or ""
                        if p_value_str:
                            p_values = [p_value_str]
                else:
                    p_values = getattr(statistics, "p_values", []) or []
                    if not p_values:
                        p_value_str = getattr(statistics, "p_value", "")
                        if p_value_str:
                            p_values = [p_value_str]

                # p-value가 있는 청크에서 결과변수 추론
                if p_values and keywords:
                    # keywords에서 결과변수 찾기
                    for keyword in keywords:
                        norm_outcome = self.normalizer.normalize_outcome(keyword)
                        if norm_outcome.confidence > 0.5:
                            # 이미 추가되지 않은 경우만
                            if not any(o.name == norm_outcome.normalized for o in outcomes):
                                # p-value 파싱
                                p_val = self._parse_p_value(p_values[0]) if p_values else None

                                outcomes.append(ExtractedOutcome(
                                    name=norm_outcome.normalized,
                                    p_value=p_val,
                                    is_significant=p_val < 0.05 if p_val else False,
                                    direction="improved"  # 추후 개선 필요
                                ))

        logger.debug(f"Extracted {len(outcomes)} outcomes from chunks")
        return outcomes

    def _determine_direction(self, outcome_dict: dict[str, Any]) -> str:
        """결과 방향 결정 (개선/악화/변화없음).

        baseline/final 또는 value_intervention/value_control 값을 비교하여
        실제 변화 방향을 결정합니다. 값이 없는 경우 is_significant 기반으로 추정.

        Args:
            outcome_dict: 결과 딕셔너리

        Returns:
            "improved", "worsened", "unchanged"
        """
        # 이미 direction이 지정된 경우
        direction = outcome_dict.get("direction", "")
        if direction and direction in ["improved", "worsened", "unchanged"]:
            return direction

        # outcome 이름으로 "낮을수록 좋은" 지표인지 판단
        outcome_name = outcome_dict.get("name", "").lower()
        lower_is_better = self._is_lower_better_outcome(outcome_name)

        # 1. baseline/final 값 비교 (Claude 형식)
        baseline = self._parse_float_value(outcome_dict.get("baseline"))
        final = self._parse_float_value(outcome_dict.get("final"))

        if baseline is not None and final is not None:
            diff = final - baseline
            if abs(diff) < 0.001:  # 거의 변화 없음
                return "unchanged"
            if lower_is_better:
                return "improved" if diff < 0 else "worsened"
            else:
                return "improved" if diff > 0 else "worsened"

        # 2. value_intervention/value_control 비교 (Gemini 형식)
        val_intervention = self._parse_float_value(outcome_dict.get("value_intervention"))
        val_control = self._parse_float_value(outcome_dict.get("value_control"))

        if val_intervention is not None and val_control is not None:
            diff = val_intervention - val_control
            if abs(diff) < 0.001:
                return "unchanged"
            if lower_is_better:
                return "improved" if diff < 0 else "worsened"
            else:
                return "improved" if diff > 0 else "worsened"

        # 3. effect_size 기반 판단
        effect_size = self._parse_float_value(outcome_dict.get("effect_size"))
        if effect_size is not None:
            if abs(effect_size) < 0.1:
                return "unchanged"
            # effect_size 양수 = intervention이 더 좋음 (일반적 관례)
            if lower_is_better:
                return "improved" if effect_size < 0 else "worsened"
            else:
                return "improved" if effect_size > 0 else "worsened"

        # 4. p_value + is_significant 기반 폴백 (값 비교 불가 시)
        raw_p = outcome_dict.get("p_value")
        p_value = self._parse_p_value_from_any(raw_p)

        is_sig = outcome_dict.get("is_significant", False)
        if p_value is not None and p_value < 0.05:
            is_sig = True

        if is_sig:
            # 유의미하지만 방향 불확실 - 기본적으로 improved 가정
            return "improved"
        else:
            return "unchanged"

    def _is_lower_better_outcome(self, outcome_name: str) -> bool:
        """낮을수록 좋은 결과변수인지 판단.

        Args:
            outcome_name: 결과변수 이름 (소문자)

        Returns:
            낮을수록 좋으면 True
        """
        # 낮을수록 좋은 지표들
        lower_better_keywords = [
            "vas", "nrs", "pain", "odi", "ndi", "oswestry", "disability",
            "blood loss", "ebl", "operative time", "operation time", "surgery time",
            "hospital stay", "los", "length of stay", "complication", "reoperation",
            "revision", "failure", "pseudarthrosis", "nonunion", "infection",
            "dural tear", "nerve injury", "mortality", "morbidity"
        ]

        for keyword in lower_better_keywords:
            if keyword in outcome_name:
                return True

        return False

    def _parse_p_value_from_any(self, raw_p: Any) -> Optional[float]:
        """p-value를 다양한 형식에서 파싱.

        Args:
            raw_p: 문자열, 숫자, 또는 None

        Returns:
            파싱된 p-value 또는 None
        """
        if raw_p is None:
            return None

        # 이미 숫자인 경우
        if isinstance(raw_p, (int, float)):
            if 0 <= raw_p <= 1:
                return float(raw_p)
            return None

        # 문자열인 경우
        if isinstance(raw_p, str):
            return self._parse_p_value(raw_p)

        return None

    def _parse_float_value(self, raw_val: Any) -> Optional[float]:
        """숫자값을 다양한 형식에서 파싱.

        Args:
            raw_val: 문자열, 숫자, 또는 None

        Returns:
            파싱된 float 또는 None
        """
        if raw_val is None:
            return None

        # 이미 숫자인 경우
        if isinstance(raw_val, (int, float)):
            return float(raw_val)

        # 문자열인 경우
        if isinstance(raw_val, str):
            try:
                # 숫자만 추출 (예: "7.2", "7.2 ± 1.5")
                match = re.search(r'^([\d.]+)', raw_val.strip())
                if match:
                    return float(match.group(1))
            except (ValueError, AttributeError):
                pass

        return None

    def _parse_p_value(self, p_str: str) -> Optional[float]:
        """p-value 문자열 파싱.

        Args:
            p_str: "p=0.001", "p<0.05", "0.023" 등

        Returns:
            파싱된 p-value 또는 None
        """
        if not p_str:
            return None

        try:
            p_str_lower = p_str.lower().strip()

            # "p=0.001" 형식
            match = re.search(r'p\s*=\s*([0-9.]+)', p_str_lower)
            if match:
                return float(match.group(1))

            # "p<0.05" 또는 "<0.001" 형식
            match = re.search(r'[p]?\s*<\s*([0-9.]+)', p_str_lower)
            if match:
                return float(match.group(1))

            # "p>0.05" 형식 (비유의미)
            match = re.search(r'p\s*>\s*([0-9.]+)', p_str_lower)
            if match:
                return float(match.group(1))

            # 숫자만 있는 경우 (예: "0.023")
            match = re.search(r'^([0-9.]+)$', p_str.strip())
            if match:
                val = float(match.group(1))
                # 0~1 범위 검증
                if 0 <= val <= 1:
                    return val

            # 문장 내 숫자 추출
            match = re.search(r'([0-9.]+)', p_str)
            if match:
                val = float(match.group(1))
                if 0 <= val <= 1:
                    return val

            return None
        except Exception as e:
            logger.warning(f"Failed to parse p-value: {p_str} - {e}")
            return None

    async def build_paper_relations_from_citations(
        self,
        paper_id: str,
        citations: list[CitationInfo],
        existing_papers: list[dict]
    ) -> PaperRelationResult:
        """인용 정보에서 논문 관계 구축.

        Args:
            paper_id: 현재 논문 ID
            citations: 추출된 인용 정보 목록
            existing_papers: 기존 논문 목록 (매칭용)

        Returns:
            PaperRelationResult with matched/unmatched citations
        """
        result = PaperRelationResult(relations_created=0)

        for citation in citations:
            try:
                # 인용을 기존 논문과 매칭
                target_paper_id = await self.match_citation_to_paper(citation, existing_papers)

                if target_paper_id:
                    # 관계 생성 성공
                    created = await self.build_relation_from_citation(
                        paper_id, target_paper_id, citation
                    )
                    if created:
                        result.matched_citations.append((citation, target_paper_id))
                        result.relations_created += 1
                        logger.debug(
                            f"Matched citation: {citation.citation_text} → {target_paper_id}"
                        )
                else:
                    result.unmatched_citations.append(citation)
                    logger.debug(f"Unmatched citation: {citation.citation_text}")

            except Exception as e:
                logger.warning(f"Error building relation from citation: {e}")
                result.unmatched_citations.append(citation)

        logger.info(
            f"Citation matching: {len(result.matched_citations)} matched, "
            f"{len(result.unmatched_citations)} unmatched"
        )
        return result

    async def match_citation_to_paper(
        self,
        citation: CitationInfo,
        existing_papers: list[dict]
    ) -> Optional[str]:
        """인용을 기존 논문과 매칭.

        매칭 기준:
        1. 저자 첫 번째 성 + 연도 일치
        2. 제목 유사도 (있는 경우)

        Args:
            citation: 인용 정보
            existing_papers: 기존 논문 목록

        Returns:
            매칭된 논문 ID 또는 None
        """
        if not citation.cited_authors or not citation.cited_year:
            return None

        first_author = citation.cited_authors[0].lower()

        for paper in existing_papers:
            # 연도 매칭
            if paper.get("year") != citation.cited_year:
                continue

            # 저자 매칭 (첫 저자 성이 포함되는지)
            paper_authors = paper.get("authors", [])
            if not paper_authors:
                continue

            # 논문 저자 문자열에 인용 저자가 포함되는지 확인
            paper_authors_str = " ".join(str(a) for a in paper_authors).lower()
            if first_author not in paper_authors_str:
                continue

            # 제목이 있다면 유사도 확인 (optional)
            if citation.cited_title and paper.get("title"):
                title_similarity = self._calculate_title_similarity(
                    citation.cited_title, paper["title"]
                )
                if title_similarity > 0.6:
                    return paper.get("paper_id")
            else:
                # 저자 + 연도만으로 매칭
                return paper.get("paper_id")

        return None

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """제목 유사도 계산 (간단한 토큰 기반).

        Args:
            title1: 제목 1
            title2: 제목 2

        Returns:
            0.0 ~ 1.0 범위의 유사도
        """
        # 간단한 토큰 기반 Jaccard 유사도
        tokens1 = set(title1.lower().split())
        tokens2 = set(title2.lower().split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    async def build_relation_from_citation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        citation: CitationInfo
    ) -> bool:
        """인용에서 관계 생성.

        CitationType에 따라:
        - SUPPORTING → SUPPORTS
        - CONTRASTING → CONTRADICTS
        - METHODOLOGICAL → CITES
        - BACKGROUND → CITES
        - NEUTRAL → CITES

        Args:
            source_paper_id: 출처 논문 ID
            target_paper_id: 대상 논문 ID
            citation: 인용 정보

        Returns:
            성공 여부
        """
        try:
            # CitationType에 따라 관계 타입 결정
            if citation.citation_type == CitationType.SUPPORTING:
                await self.client.create_supports_relation(
                    source_paper_id=source_paper_id,
                    target_paper_id=target_paper_id,
                    evidence=citation.citation_context,
                    confidence=citation.confidence
                )
            elif citation.citation_type == CitationType.CONTRASTING:
                await self.client.create_contradicts_relation(
                    source_paper_id=source_paper_id,
                    target_paper_id=target_paper_id,
                    evidence=citation.citation_context,
                    confidence=citation.confidence
                )
            else:
                # NEUTRAL, BACKGROUND, METHODOLOGICAL → CITES
                await self.client.create_cites_relation(
                    source_paper_id=source_paper_id,
                    target_paper_id=target_paper_id,
                    citation_text=citation.citation_text,
                    context=citation.citation_context
                )

            return True

        except Exception as e:
            logger.error(
                f"Failed to create relation from citation "
                f"({source_paper_id} → {target_paper_id}): {e}"
            )
            return False

    async def build_similarity_relations(
        self,
        paper_id: str,
        paper_metadata: dict,
        existing_papers: list[dict],
        min_similarity: float = 0.5
    ) -> int:
        """유사도 기반 관계 구축.

        PICO, 키워드, 제목 유사도로 SIMILAR_TOPIC 관계 생성.

        Args:
            paper_id: 현재 논문 ID
            paper_metadata: 현재 논문 메타데이터
            existing_papers: 기존 논문 목록
            min_similarity: 최소 유사도 임계값

        Returns:
            생성된 관계 수
        """
        count = 0

        # 현재 논문의 특징 추출 (중첩 리스트 평탄화)
        current_pathologies = self._flatten_to_set(paper_metadata.get("pathologies", []))
        current_interventions = self._flatten_to_set(paper_metadata.get("interventions", []))
        current_anatomy = self._flatten_to_set(paper_metadata.get("anatomy_levels", []))
        current_sub_domain = paper_metadata.get("sub_domain", "")

        for other_paper in existing_papers:
            # 자기 자신은 제외
            if other_paper.get("paper_id") == paper_id:
                continue

            # 유사도 계산
            similarity = self._calculate_paper_similarity(
                paper_metadata, other_paper
            )

            if similarity >= min_similarity:
                try:
                    # SIMILAR_TOPIC 관계 생성 (create_paper_relation 사용)
                    await self.client.create_paper_relation(
                        source_paper_id=paper_id,
                        target_paper_id=other_paper["paper_id"],
                        relation_type="SIMILAR_TOPIC",
                        confidence=similarity,
                        evidence=f"Similarity score: {similarity:.2f}",
                        detected_by="similarity_calculation"
                    )
                    count += 1
                    logger.debug(
                        f"Created SIMILAR_TOPIC: {paper_id} ↔ {other_paper['paper_id']} "
                        f"(similarity: {similarity:.2f})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to create SIMILAR_TOPIC relation: {e}"
                    )

        return count

    def _calculate_paper_similarity(
        self,
        paper1: dict,
        paper2: dict
    ) -> float:
        """논문 간 유사도 계산 (v3.2 업데이트).

        다음 요소들을 고려:
        - Sub-domain 겹침 (25%) - v3.2: sub_domains 리스트 지원
        - Surgical approach 겹침 (10%) - v3.2: 새 필드
        - Pathology 겹침 (25%)
        - Intervention 겹침 (25%)
        - Anatomy 겹침 (15%)

        Args:
            paper1: 논문 1 메타데이터
            paper2: 논문 2 메타데이터

        Returns:
            0.0 ~ 1.0 범위의 유사도
        """
        score = 0.0

        # 1. Sub-domain 겹침 (25%) - v3.2: sub_domains 리스트 우선 사용
        domains1 = self._flatten_to_set(paper1.get("sub_domains", []))
        domains2 = self._flatten_to_set(paper2.get("sub_domains", []))
        # 하위호환성: sub_domains가 없으면 sub_domain 사용
        if not domains1 and paper1.get("sub_domain"):
            domains1 = {paper1["sub_domain"]}
        if not domains2 and paper2.get("sub_domain"):
            domains2 = {paper2["sub_domain"]}
        if domains1 and domains2:
            jaccard = len(domains1 & domains2) / len(domains1 | domains2)
            score += 0.25 * jaccard

        # 2. Surgical approach 겹침 (10%) - v3.2
        approach1 = self._flatten_to_set(paper1.get("surgical_approach", []))
        approach2 = self._flatten_to_set(paper2.get("surgical_approach", []))
        if approach1 and approach2:
            jaccard = len(approach1 & approach2) / len(approach1 | approach2)
            score += 0.10 * jaccard

        # 3. Pathology 겹침 (25%) - 중첩 리스트 평탄화
        pathologies1 = self._flatten_to_set(paper1.get("pathologies", []))
        pathologies2 = self._flatten_to_set(paper2.get("pathologies", []))
        if pathologies1 and pathologies2:
            jaccard = len(pathologies1 & pathologies2) / len(pathologies1 | pathologies2)
            score += 0.25 * jaccard

        # 4. Intervention 겹침 (25%) - 중첩 리스트 평탄화
        interventions1 = self._flatten_to_set(paper1.get("interventions", []))
        interventions2 = self._flatten_to_set(paper2.get("interventions", []))
        if interventions1 and interventions2:
            jaccard = len(interventions1 & interventions2) / len(interventions1 | interventions2)
            score += 0.25 * jaccard

        # 5. Anatomy 겹침 (15%) - 중첩 리스트 평탄화
        anatomy1 = self._flatten_to_set(paper1.get("anatomy_levels", []))
        anatomy2 = self._flatten_to_set(paper2.get("anatomy_levels", []))
        if anatomy1 and anatomy2:
            jaccard = len(anatomy1 & anatomy2) / len(anatomy1 | anatomy2)
            score += 0.15 * jaccard

        return score

    def _extract_complications_from_chunks(
        self,
        chunks: list["ExtractedChunk"],
        intervention: str
    ) -> list[dict[str, Any]]:
        """Extract complications from chunks for a specific intervention.

        Looks for complication mentions in results/discussion sections.

        Args:
            chunks: List of extracted chunks
            intervention: Intervention name to find complications for

        Returns:
            List of complication dicts with keys: name, category, severity, incidence_rate
        """
        complications = []

        # Common complication keywords
        complication_keywords = [
            "complication", "adverse event", "infection", "dural tear",
            "nerve injury", "hardware failure", "pseudarthrosis",
            "adjacent segment", "cerebrospinal fluid leak", "CSF leak",
            "wound complication", "hematoma", "deep vein thrombosis", "DVT"
        ]

        for chunk in chunks:
            # Support both ExtractedChunk objects and dict
            if isinstance(chunk, dict):
                section_type = chunk.get("section_type", "")
                content = chunk.get("content", "")
                keywords = chunk.get("keywords", [])
            else:
                section_type = getattr(chunk, "section_type", "")
                content = getattr(chunk, "content", "")
                keywords = getattr(chunk, "keywords", []) or []

            # Only process results/discussion/methods sections
            if section_type not in ["results", "discussion", "methods"]:
                continue

            content_lower = content.lower()

            # Check if this chunk mentions the intervention
            if intervention.lower() not in content_lower:
                continue

            # Look for complication mentions
            for comp_keyword in complication_keywords:
                if comp_keyword in content_lower:
                    # Extract complication name (simplified extraction)
                    # In production, this should use more sophisticated NER/extraction

                    # Try to extract incidence rate if present
                    incidence_rate = ""
                    # Pattern: X% or X/Y or X out of Y
                    rate_match = re.search(r'(\d+\.?\d*)\s*%', content)
                    if rate_match:
                        incidence_rate = f"{rate_match.group(1)}%"

                    # Determine severity based on keywords
                    severity = ""
                    if any(s in content_lower for s in ["major", "severe", "serious"]):
                        severity = "severe"
                    elif any(s in content_lower for s in ["minor", "mild"]):
                        severity = "mild"
                    else:
                        severity = "moderate"

                    # Determine category
                    category = ""
                    if any(c in content_lower for c in ["surgical", "operative", "intraoperative"]):
                        category = "surgical"
                    elif any(c in content_lower for c in ["hardware", "implant", "screw"]):
                        category = "hardware"
                    else:
                        category = "medical"

                    complications.append({
                        "name": comp_keyword.title(),
                        "category": category,
                        "severity": severity,
                        "incidence_rate": incidence_rate
                    })

        # Deduplicate by name
        seen_names = set()
        unique_complications = []
        for comp in complications:
            if comp["name"] not in seen_names:
                seen_names.add(comp["name"])
                unique_complications.append(comp)

        return unique_complications

    def _flatten_to_set(self, items: list) -> set[str]:
        """중첩 리스트를 평탄화하여 set으로 변환.

        Args:
            items: 리스트 (중첩 가능)

        Returns:
            평탄화된 문자열 set
        """
        result = set()
        for item in items:
            if isinstance(item, list):
                # 중첩 리스트인 경우 재귀적으로 평탄화
                for sub_item in item:
                    if sub_item:
                        result.add(str(sub_item))
            elif item:
                result.add(str(item))
        return result

    # ===== Secondary Entity Normalization =====

    def _normalize_secondary_entity(self, name: str) -> str:
        """Normalize secondary entity names (trim + capitalize first letter).

        Preserves all-uppercase acronyms (e.g., BMI, VAS, MRI).

        Args:
            name: Raw entity name from LLM extraction.

        Returns:
            Normalized name with leading/trailing whitespace removed
            and first letter capitalized (unless all-uppercase acronym).
        """
        if not name:
            return name
        normalized = name.strip()
        if not normalized:
            return normalized
        # Preserve all-caps acronyms
        if not normalized.isupper():
            normalized = normalized[0].upper() + normalized[1:]
        return normalized

    # ===== v1.1 New Relationship Methods =====

    async def _create_risk_factor_relationships(
        self,
        paper_id: str,
        risk_factors: list[dict[str, Any]]
    ) -> int:
        """Create RiskFactor nodes and HAS_RISK_FACTOR relationships.

        Args:
            paper_id: Paper ID
            risk_factors: List of risk factor dicts with keys:
                - name: Risk factor name
                - category: Optional category (demographic, clinical, radiographic)
                - variable_type: Optional type (binary, continuous, categorical)
                - odds_ratio: Optional odds ratio
                - hazard_ratio: Optional hazard ratio
                - p_value: Optional p-value
                - outcome_affected: Optional outcome name

        Returns:
            Number of relationships created
        """
        if not risk_factors:
            return 0

        items = []
        for rf_dict in risk_factors:
            name = rf_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)
            items.append({
                "name": name,
                "category": rf_dict.get("category", ""),
                "variable_type": rf_dict.get("variable_type", ""),
                "odds_ratio": rf_dict.get("odds_ratio"),
                "hazard_ratio": rf_dict.get("hazard_ratio"),
                "p_value": rf_dict.get("p_value"),
                "outcome_affected": rf_dict.get("outcome_affected", ""),
            })

        if not items:
            return 0

        try:
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (rf:RiskFactor {name: item.name})
                ON CREATE SET rf.category = item.category, rf.variable_type = item.variable_type
                WITH rf, item
                MATCH (p:Paper {paper_id: $paper_id})
                MERGE (p)-[r:HAS_RISK_FACTOR]->(rf)
                ON CREATE SET
                    r.odds_ratio = item.odds_ratio,
                    r.hazard_ratio = item.hazard_ratio,
                    r.p_value = item.p_value,
                    r.outcome_affected = item.outcome_affected
                """,
                {"items": items, "paper_id": paper_id}
            )
            return len(items)
        except Exception as e:
            logger.warning(f"Failed to create risk factor relationships: {e}")
            return 0

    async def _create_complication_relationships(
        self,
        intervention_name: str,
        complications: list[dict[str, Any]],
        paper_id: str
    ) -> int:
        """Create Complication nodes and CAUSES relationships.

        Args:
            intervention_name: Intervention name
            complications: List of complication dicts with keys:
                - name: Complication name
                - category: Optional category (surgical, medical, hardware)
                - severity: Optional severity (mild, moderate, severe)
                - incidence_rate: Optional incidence rate (e.g., "5.2%")
            paper_id: Source paper ID

        Returns:
            Number of relationships created
        """
        if not complications:
            return 0

        # Normalize intervention name
        norm_intervention = self.normalizer.normalize_intervention(intervention_name)
        intervention_name = norm_intervention.normalized

        items = []
        for comp_dict in complications:
            name = comp_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)
            items.append({
                "name": name,
                "category": comp_dict.get("category", ""),
                "severity": comp_dict.get("severity", ""),
                "incidence_rate": comp_dict.get("incidence_rate", ""),
            })

        if not items:
            return 0

        try:
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (c:Complication {name: item.name})
                ON CREATE SET c.category = item.category, c.severity = item.severity
                WITH c, item
                MATCH (i:Intervention {name: $intervention_name})
                MERGE (i)-[r:CAUSES]->(c)
                ON CREATE SET r.incidence_rate = item.incidence_rate, r.source_paper_id = $source_paper_id
                """,
                {"items": items, "intervention_name": intervention_name, "source_paper_id": paper_id}
            )
            return len(items)
        except Exception as e:
            logger.warning(f"Failed to create complication relationships: {e}")
            return 0

    async def _create_radiographic_relationships(
        self,
        correlations: list[dict[str, Any]],
        paper_id: str
    ) -> int:
        """Create RadioParameter, OutcomeMeasure nodes and CORRELATES relationships.

        Args:
            correlations: List of correlation dicts with keys:
                - radio_parameter: Radiographic parameter name (e.g., "Pelvic Incidence")
                - outcome_measure: Outcome measure name (e.g., "ODI")
                - r_value: Correlation coefficient
                - p_value: P-value
                - radio_category: Optional category (sagittal, coronal, axial)
                - radio_unit: Optional unit (degrees, mm)
                - outcome_category: Optional category (pain, function)
                - outcome_unit: Optional unit
            paper_id: Source paper ID

        Returns:
            Number of relationships created
        """
        if not correlations:
            return 0

        items = []
        for corr_dict in correlations:
            radio_param = corr_dict.get("radio_parameter")
            outcome_measure = corr_dict.get("outcome_measure")
            if not radio_param or not outcome_measure:
                continue
            radio_param = self._normalize_secondary_entity(radio_param)
            items.append({
                "radio_param": radio_param,
                "radio_category": corr_dict.get("radio_category", ""),
                "radio_unit": corr_dict.get("radio_unit", ""),
                "outcome_measure": outcome_measure,
                "outcome_category": corr_dict.get("outcome_category", ""),
                "outcome_unit": corr_dict.get("outcome_unit", ""),
                "r_value": corr_dict.get("r_value"),
                "p_value": corr_dict.get("p_value"),
            })

        if not items:
            return 0

        try:
            # Step 1: Create RadioParameter nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (rp:RadioParameter {name: item.radio_param})
                ON CREATE SET rp.category = item.radio_category, rp.unit = item.radio_unit
                """,
                {"items": items}
            )

            # Step 2: Create OutcomeMeasure nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (om:OutcomeMeasure {name: item.outcome_measure})
                ON CREATE SET om.category = item.outcome_category, om.unit = item.outcome_unit
                """,
                {"items": items}
            )

            # Step 3: Create CORRELATES relationships
            await self.client.run_query(
                """
                UNWIND $items AS item
                MATCH (rp:RadioParameter {name: item.radio_param})
                MATCH (om:OutcomeMeasure {name: item.outcome_measure})
                MERGE (rp)-[r:CORRELATES]->(om)
                ON CREATE SET r.r_value = item.r_value, r.p_value = item.p_value, r.source_paper_id = $source_paper_id
                """,
                {"items": items, "source_paper_id": paper_id}
            )
            return len(items)
        except Exception as e:
            logger.warning(f"Failed to create radiographic relationships: {e}")
            return 0

    async def _create_prediction_model_relationships(
        self,
        models: list[dict[str, Any]],
        paper_id: str
    ) -> int:
        """Create PredictionModel nodes and PREDICTS/USES_FEATURE relationships.

        Args:
            models: List of prediction model dicts with keys:
                - name: Model name
                - model_type: Type (logistic_regression, random_forest, neural_network, etc.)
                - auc: AUC value
                - accuracy: Accuracy value
                - sensitivity: Sensitivity value
                - specificity: Specificity value
                - features: List of feature (risk factor) names
                - predicted_outcome: Outcome name that is predicted
            paper_id: Source paper ID

        Returns:
            Number of models created
        """
        if not models:
            return 0

        model_items = []
        predict_items = []
        feature_items = []

        for model_dict in models:
            model_name = model_dict.get("name")
            if not model_name:
                continue
            model_name = self._normalize_secondary_entity(model_name)

            features = model_dict.get("features", [])
            model_items.append({
                "name": model_name,
                "model_type": model_dict.get("model_type", ""),
                "auc": model_dict.get("auc"),
                "accuracy": model_dict.get("accuracy"),
                "sensitivity": model_dict.get("sensitivity"),
                "specificity": model_dict.get("specificity"),
                "features": features,
            })

            predicted_outcome = model_dict.get("predicted_outcome")
            if predicted_outcome:
                predict_items.append({
                    "model_name": model_name,
                    "outcome_name": predicted_outcome,
                    "auc": model_dict.get("auc"),
                    "accuracy": model_dict.get("accuracy"),
                })

            for feature in features:
                if feature:
                    feature_items.append({
                        "model_name": model_name,
                        "feature_name": feature,
                    })

        if not model_items:
            return 0

        try:
            # Step 1: Create PredictionModel nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (pm:PredictionModel {name: item.name})
                ON CREATE SET
                    pm.model_type = item.model_type,
                    pm.auc = item.auc,
                    pm.accuracy = item.accuracy,
                    pm.sensitivity = item.sensitivity,
                    pm.specificity = item.specificity,
                    pm.features = item.features,
                    pm.source_paper_id = $source_paper_id
                """,
                {"items": model_items, "source_paper_id": paper_id}
            )

            # Step 2: Create PREDICTS relationships
            if predict_items:
                await self.client.run_query(
                    """
                    UNWIND $items AS item
                    MATCH (pm:PredictionModel {name: item.model_name})
                    MATCH (o:Outcome {name: item.outcome_name})
                    MERGE (pm)-[r:PREDICTS]->(o)
                    ON CREATE SET r.auc = item.auc, r.accuracy = item.accuracy
                    """,
                    {"items": predict_items}
                )

            # Step 3: Create RiskFactor nodes and USES_FEATURE relationships
            if feature_items:
                await self.client.run_query(
                    """
                    UNWIND $items AS item
                    MERGE (rf:RiskFactor {name: item.feature_name})
                    ON CREATE SET rf.category = '', rf.variable_type = ''
                    WITH rf, item
                    MATCH (pm:PredictionModel {name: item.model_name})
                    MERGE (pm)-[r:USES_FEATURE]->(rf)
                    ON CREATE SET r.importance = null
                    """,
                    {"items": feature_items}
                )

            return len(model_items)
        except Exception as e:
            logger.warning(f"Failed to create prediction model relationships: {e}")
            return 0

    async def _create_uses_device_relationships(
        self,
        intervention_name: str,
        implants: list[dict[str, Any]],
        paper_id: str
    ) -> int:
        """Create USES_DEVICE relationships between Intervention and Implant.

        Args:
            intervention_name: Intervention name
            implants: List of implant dicts with keys:
                - name: Implant name
                - frequency: Optional usage frequency (e.g., "80% of cases")
            paper_id: Source paper ID

        Returns:
            Number of relationships created
        """
        if not implants:
            return 0

        # Normalize intervention name
        norm_intervention = self.normalizer.normalize_intervention(intervention_name)
        intervention_name = norm_intervention.normalized

        items = []
        for implant_dict in implants:
            implant_name = implant_dict.get("name")
            if not implant_name:
                continue
            items.append({
                "implant_name": implant_name,
                "frequency": implant_dict.get("frequency", ""),
            })

        if not items:
            return 0

        try:
            await self.client.run_query(
                """
                UNWIND $items AS item
                MATCH (i:Intervention {name: $intervention_name})
                MATCH (impl:Implant {name: item.implant_name})
                MERGE (i)-[r:USES_DEVICE]->(impl)
                ON CREATE SET r.frequency = item.frequency, r.source_paper_id = $source_paper_id
                """,
                {"items": items, "intervention_name": intervention_name, "source_paper_id": paper_id}
            )
            return len(items)
        except Exception as e:
            logger.warning(f"Failed to create USES_DEVICE relationships for {intervention_name}: {e}")
            return 0

    # ===== v1.2 New Relationship Methods =====

    async def _create_cohort_relationships(
        self,
        paper_id: str,
        cohorts: list[dict[str, Any]]
    ) -> int:
        """Create PatientCohort nodes and HAS_COHORT relationships.

        Args:
            paper_id: Paper ID
            cohorts: List of cohort dicts with keys:
                - name: Cohort name (e.g., "Intervention Group", "Control Group")
                - cohort_type: Type (intervention, control, total, propensity_matched)
                - sample_size: Number of patients
                - mean_age: Mean age
                - age_sd: Age standard deviation
                - female_percentage: Percentage of female patients
                - diagnosis: Primary diagnosis
                - intervention_name: Optional intervention for TREATED_WITH relation

        Returns:
            Number of relationships created
        """
        if not cohorts:
            return 0

        cohort_items = []
        treated_with_items = []

        for cohort_dict in cohorts:
            name = cohort_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)

            role = cohort_dict.get("cohort_type", "")
            is_primary = cohort_dict.get("cohort_type") == "total" or len(cohorts) == 1
            cohort_items.append({
                "name": name,
                "cohort_type": role,
                "sample_size": cohort_dict.get("sample_size", 0),
                "mean_age": cohort_dict.get("mean_age", 0.0),
                "age_sd": cohort_dict.get("age_sd", 0.0),
                "female_percentage": cohort_dict.get("female_percentage", 0.0),
                "diagnosis": cohort_dict.get("diagnosis", ""),
                "is_primary": is_primary,
                "role": role,
            })

            intervention_name = cohort_dict.get("intervention_name")
            if intervention_name:
                norm_intervention = self.normalizer.normalize_intervention(intervention_name)
                treated_with_items.append({
                    "cohort_name": name,
                    "intervention_name": norm_intervention.normalized,
                    "n_patients": cohort_dict.get("sample_size", 0),
                })

        if not cohort_items:
            return 0

        try:
            # Step 1: Create PatientCohort nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (pc:PatientCohort {name: item.name, source_paper_id: $paper_id})
                ON CREATE SET
                    pc.cohort_type = item.cohort_type,
                    pc.sample_size = item.sample_size,
                    pc.mean_age = item.mean_age,
                    pc.age_sd = item.age_sd,
                    pc.female_percentage = item.female_percentage,
                    pc.diagnosis = item.diagnosis
                """,
                {"items": cohort_items, "paper_id": paper_id}
            )

            # Step 2: Create HAS_COHORT relationships
            await self.client.run_query(
                """
                UNWIND $items AS item
                MATCH (p:Paper {paper_id: $paper_id})
                MATCH (pc:PatientCohort {name: item.name, source_paper_id: $paper_id})
                MERGE (p)-[r:HAS_COHORT]->(pc)
                ON CREATE SET r.is_primary = item.is_primary, r.role = item.role
                """,
                {"items": cohort_items, "paper_id": paper_id}
            )

            # Step 3: Create TREATED_WITH relationships
            if treated_with_items:
                await self.client.run_query(
                    """
                    UNWIND $items AS item
                    MATCH (pc:PatientCohort {name: item.cohort_name, source_paper_id: $paper_id})
                    MATCH (i:Intervention {name: item.intervention_name})
                    MERGE (pc)-[r:TREATED_WITH]->(i)
                    ON CREATE SET r.n_patients = item.n_patients, r.source_paper_id = $paper_id
                    """,
                    {"items": treated_with_items, "paper_id": paper_id}
                )

            return len(cohort_items)
        except Exception as e:
            logger.warning(f"Failed to create cohort relationships: {e}")
            return 0

    async def _create_followup_relationships(
        self,
        paper_id: str,
        followups: list[dict[str, Any]]
    ) -> int:
        """Create FollowUp nodes and HAS_FOLLOWUP relationships.

        Args:
            paper_id: Paper ID
            followups: List of follow-up dicts with keys:
                - name: Timepoint name (e.g., "6-month", "1-year", "Final")
                - timepoint_months: Months from baseline
                - timepoint_type: Type (scheduled, final, minimum)
                - mean_followup_months: Mean follow-up duration
                - completeness_rate: Follow-up completion rate
                - is_primary_endpoint: Whether this is the primary endpoint
                - outcomes: Optional list of {outcome_name, value, improvement} for REPORTS_OUTCOME

        Returns:
            Number of relationships created
        """
        if not followups:
            return 0

        fu_items = []
        outcome_items = []

        for fu_dict in followups:
            name = fu_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)

            fu_items.append({
                "name": name,
                "timepoint_months": fu_dict.get("timepoint_months", 0),
                "timepoint_type": fu_dict.get("timepoint_type", ""),
                "mean_followup_months": fu_dict.get("mean_followup_months", 0.0),
                "completeness_rate": fu_dict.get("completeness_rate", 0.0),
                "is_primary_endpoint": fu_dict.get("is_primary_endpoint", False),
            })

            # Flatten outcomes for this followup
            outcomes_at_fu = fu_dict.get("outcomes", [])
            for outcome_dict in outcomes_at_fu:
                outcome_name = outcome_dict.get("outcome_name")
                if not outcome_name:
                    continue
                outcome_items.append({
                    "followup_name": name,
                    "outcome_name": outcome_name,
                    "value": outcome_dict.get("value"),
                    "improvement": outcome_dict.get("improvement", ""),
                })

        if not fu_items:
            return 0

        try:
            # Step 1: Create FollowUp nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (fu:FollowUp {name: item.name, source_paper_id: $paper_id})
                ON CREATE SET
                    fu.timepoint_months = item.timepoint_months,
                    fu.timepoint_type = item.timepoint_type,
                    fu.mean_followup_months = item.mean_followup_months,
                    fu.completeness_rate = item.completeness_rate
                """,
                {"items": fu_items, "paper_id": paper_id}
            )

            # Step 2: Create HAS_FOLLOWUP relationships
            await self.client.run_query(
                """
                UNWIND $items AS item
                MATCH (p:Paper {paper_id: $paper_id})
                MATCH (fu:FollowUp {name: item.name, source_paper_id: $paper_id})
                MERGE (p)-[r:HAS_FOLLOWUP]->(fu)
                ON CREATE SET r.is_primary_endpoint = item.is_primary_endpoint
                """,
                {"items": fu_items, "paper_id": paper_id}
            )

            # Step 3: Create REPORTS_OUTCOME relationships
            if outcome_items:
                await self.client.run_query(
                    """
                    UNWIND $items AS item
                    MATCH (fu:FollowUp {name: item.followup_name, source_paper_id: $paper_id})
                    MATCH (o:Outcome {name: item.outcome_name})
                    MERGE (fu)-[r:REPORTS_OUTCOME]->(o)
                    ON CREATE SET r.value = item.value, r.improvement = item.improvement, r.source_paper_id = $paper_id
                    """,
                    {"items": outcome_items, "paper_id": paper_id}
                )

            return len(fu_items)
        except Exception as e:
            logger.warning(f"Failed to create followup relationships: {e}")
            return 0

    async def _create_cost_relationships(
        self,
        paper_id: str,
        costs: list[dict[str, Any]]
    ) -> int:
        """Create Cost nodes and REPORTS_COST relationships.

        Args:
            paper_id: Paper ID
            costs: List of cost dicts with keys:
                - name: Cost analysis name (e.g., "Direct Hospital Cost", "Total Cost")
                - cost_type: Type (direct, indirect, total, incremental)
                - mean_cost: Mean cost value
                - currency: Currency (USD, EUR, KRW)
                - qaly_gained: QALY gained (for cost-utility analysis)
                - icer: Incremental cost-effectiveness ratio
                - is_primary_analysis: Whether this is primary economic analysis
                - intervention_name: Optional for ASSOCIATED_WITH relation

        Returns:
            Number of relationships created
        """
        if not costs:
            return 0

        cost_items = []
        associated_items = []

        for cost_dict in costs:
            name = cost_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)

            cost_items.append({
                "name": name,
                "cost_type": cost_dict.get("cost_type", ""),
                "mean_cost": cost_dict.get("mean_cost", 0.0),
                "currency": cost_dict.get("currency", "USD"),
                "qaly_gained": cost_dict.get("qaly_gained", 0.0),
                "icer": cost_dict.get("icer", 0.0),
                "is_primary_analysis": cost_dict.get("is_primary_analysis", True),
            })

            intervention_name = cost_dict.get("intervention_name")
            if intervention_name:
                norm_intervention = self.normalizer.normalize_intervention(intervention_name)
                associated_items.append({
                    "cost_name": name,
                    "intervention_name": norm_intervention.normalized,
                    "cost_value": cost_dict.get("mean_cost", 0.0),
                })

        if not cost_items:
            return 0

        try:
            # Step 1: Create Cost nodes
            await self.client.run_query(
                """
                UNWIND $items AS item
                MERGE (c:Cost {name: item.name, source_paper_id: $paper_id})
                ON CREATE SET
                    c.cost_type = item.cost_type,
                    c.mean_cost = item.mean_cost,
                    c.currency = item.currency,
                    c.qaly_gained = item.qaly_gained,
                    c.icer = item.icer
                """,
                {"items": cost_items, "paper_id": paper_id}
            )

            # Step 2: Create REPORTS_COST relationships
            await self.client.run_query(
                """
                UNWIND $items AS item
                MATCH (p:Paper {paper_id: $paper_id})
                MATCH (c:Cost {name: item.name, source_paper_id: $paper_id})
                MERGE (p)-[r:REPORTS_COST]->(c)
                ON CREATE SET r.is_primary_analysis = item.is_primary_analysis
                """,
                {"items": cost_items, "paper_id": paper_id}
            )

            # Step 3: Create ASSOCIATED_WITH relationships
            if associated_items:
                await self.client.run_query(
                    """
                    UNWIND $items AS item
                    MATCH (c:Cost {name: item.cost_name, source_paper_id: $paper_id})
                    MATCH (i:Intervention {name: item.intervention_name})
                    MERGE (c)-[r:ASSOCIATED_WITH]->(i)
                    ON CREATE SET r.cost_value = item.cost_value, r.source_paper_id = $paper_id
                    """,
                    {"items": associated_items, "paper_id": paper_id}
                )

            return len(cost_items)
        except Exception as e:
            logger.warning(f"Failed to create cost relationships: {e}")
            return 0

    async def _create_quality_metric_relationships(
        self,
        paper_id: str,
        quality_metrics: list[dict[str, Any]]
    ) -> int:
        """Create QualityMetric nodes and HAS_QUALITY_METRIC relationships.

        Args:
            paper_id: Paper ID
            quality_metrics: List of quality metric dicts with keys:
                - name: Assessment name (e.g., "GRADE Assessment", "MINORS Score")
                - assessment_tool: Tool name (GRADE, MINORS, NOS, Jadad, AMSTAR, Cochrane ROB)
                - overall_score: Numeric score
                - max_score: Maximum possible score
                - overall_rating: Qualitative rating (high, moderate, low, very low)
                - grade_certainty: GRADE certainty level
                - assessed_by: Who performed the assessment
                - assessment_type: Type (self, external, consensus)

        Returns:
            Number of relationships created
        """
        count = 0

        for qm_dict in quality_metrics:
            name = qm_dict.get("name")
            if not name:
                continue
            name = self._normalize_secondary_entity(name)

            try:
                # Create QualityMetric node
                await self.client.run_query(
                    CREATE_QUALITY_METRIC_CYPHER,
                    {
                        "name": name,
                        "source_paper_id": paper_id,
                        "assessment_tool": qm_dict.get("assessment_tool", ""),
                        "overall_score": qm_dict.get("overall_score", 0.0),
                        "max_score": qm_dict.get("max_score", 0.0),
                        "overall_rating": qm_dict.get("overall_rating", ""),
                        "grade_certainty": qm_dict.get("grade_certainty", ""),
                    }
                )

                # Create HAS_QUALITY_METRIC relationship
                await self.client.run_query(
                    CREATE_HAS_QUALITY_METRIC_REL_CYPHER,
                    {
                        "paper_id": paper_id,
                        "metric_name": name,
                        "assessed_by": qm_dict.get("assessed_by", ""),
                        "assessment_type": qm_dict.get("assessment_type", ""),
                    }
                )

                count += 1

            except Exception as e:
                logger.warning(f"Failed to create quality metric {name}: {e}")

        return count


# 사용 예시
async def example_usage() -> None:
    """사용 예시."""
    from .neo4j_client import Neo4jClient
    from .entity_normalizer import EntityNormalizer
    from ..builder.gemini_vision_processor import (
        ExtractedMetadata,
        ExtractedChunk,
        PICOData,
        StatisticsData
    )

    # 클라이언트 초기화
    async with Neo4jClient() as client:
        await client.initialize_schema()

        normalizer: EntityNormalizer = EntityNormalizer()
        builder: RelationshipBuilder = RelationshipBuilder(client, normalizer)

        # 테스트 데이터
        metadata = ExtractedMetadata(
            title="TLIF vs PLIF for Lumbar Stenosis",
            authors=["Author A", "Author B"],
            year=2024,
            journal="Spine",
            doi="10.1234/test",
            study_type="RCT",
            evidence_level="1b"
        )

        spine_metadata = SpineMetadata(
            sub_domain="Degenerative",
            anatomy_levels=["L4-5"],
            pathologies=["Lumbar Stenosis"],
            interventions=["TLIF", "PLIF"],
            outcomes=[
                {"name": "Fusion Rate", "value": "92%", "p_value": 0.01},
                {"name": "VAS", "value": "2.3", "p_value": 0.001}
            ]
        )

        chunks = [
            ExtractedChunk(
                content="Fusion rate was 92% in TLIF group vs 85% in PLIF group (p=0.01).",
                section_type="results",
                tier="tier1",
                is_key_finding=True,
                keywords=["Fusion Rate", "TLIF", "PLIF"],
                statistics=StatisticsData(p_values=["p=0.01"])
            )
        ]

        # 관계 구축
        result = await builder.build_from_paper(
            paper_id="test_001",
            metadata=metadata,
            spine_metadata=spine_metadata,
            chunks=chunks
        )

        print(f"Build Result:")
        print(f"  Nodes created: {result.nodes_created}")
        print(f"  Relationships created: {result.relationships_created}")
        print(f"  Warnings: {result.warnings}")
        print(f"  Errors: {result.errors}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
