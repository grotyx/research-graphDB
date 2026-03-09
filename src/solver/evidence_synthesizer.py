"""Evidence Synthesizer for Meta-Analysis Level Evidence Synthesis.

메타 분석 수준의 근거 종합 모듈.
- 다수 논문의 결과 통합
- 통계적 유의성 평가
- GRADE 방법론 기반 근거 수준 평가
- 이질성(heterogeneity) 분석
- 자연어 요약 생성

v1.14.11: 검색 시 Entity Normalization 및 IS_A hierarchy 지원
- 입력 용어를 정규화하여 정확한 매칭
- IS_A 관계를 통해 하위 intervention도 포함

사용 예:
    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)
        result = await synthesizer.synthesize(
            intervention="TLIF",
            outcome="VAS"
        )
        print(f"Direction: {result.direction}")
        print(f"Strength: {result.strength.value}")
        print(f"GRADE: {result.grade_rating}")
"""

import asyncio
import logging
import math
import re
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Entity normalizer for search term expansion
try:
    from graph.entity_normalizer import get_normalizer
    NORMALIZER_AVAILABLE = True
except ImportError:
    try:
        from src.graph.entity_normalizer import get_normalizer
        NORMALIZER_AVAILABLE = True
    except ImportError:
        NORMALIZER_AVAILABLE = False
        get_normalizer = None

try:
    from core.exceptions import ValidationError
except ImportError:
    try:
        from ..core.exceptions import ValidationError
    except ImportError:
        ValidationError = ValueError  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class EvidenceStrength(Enum):
    """근거의 강도."""
    STRONG = "strong"              # Multiple high-quality studies agree
    MODERATE = "moderate"          # Mixed quality or limited studies
    WEAK = "weak"                  # Low quality or conflicting
    INSUFFICIENT = "insufficient"  # Not enough data


class HeterogeneityLevel(Enum):
    """이질성 수준."""
    LOW = "low"          # I² < 25%
    MODERATE = "moderate"  # 25% ≤ I² < 75%
    HIGH = "high"        # I² ≥ 75%


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EvidenceItem:
    """개별 근거 항목."""
    paper_id: str
    title: str
    year: int
    evidence_level: str  # 1a, 1b, 2a, 2b, 3, 4, 5
    value: float  # 측정값
    value_control: Optional[float] = None  # 대조군 값
    p_value: Optional[float] = None
    direction: str = ""  # improved, worsened, unchanged
    is_significant: bool = False
    sample_size: int = 0

    @property
    def effect_size(self) -> Optional[float]:
        """효과 크기 (intervention - control)."""
        if self.value_control is not None:
            return self.value - self.value_control
        return None

    @property
    def weight(self) -> float:
        """근거 수준 기반 가중치."""
        return EVIDENCE_WEIGHTS.get(self.evidence_level, 0.1)


@dataclass
class PooledEffect:
    """통합 효과."""
    mean: float
    std: float
    ci_low: float  # 95% CI lower bound
    ci_high: float  # 95% CI upper bound
    n_studies: int

    def to_str(self) -> str:
        """문자열 표현."""
        return f"{self.mean:.2f} ± {self.std:.2f} (95% CI: {self.ci_low:.2f} to {self.ci_high:.2f})"


@dataclass
class SynthesisResult:
    """근거 종합 결과."""
    intervention: str
    outcome: str
    direction: str  # "improved", "worsened", "mixed", "unchanged"
    strength: EvidenceStrength
    paper_count: int
    supporting_papers: list[str] = field(default_factory=list)
    opposing_papers: list[str] = field(default_factory=list)
    effect_summary: str = ""  # e.g., "VAS improved by 3.2 ± 1.1 points"
    confidence_interval: Optional[tuple[float, float]] = None
    heterogeneity: str = "low"  # "low", "moderate", "high"
    grade_rating: str = "D"  # "A", "B", "C", "D"
    recommendation: str = ""

    # 상세 정보
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    pooled_effect: Optional[PooledEffect] = None

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "intervention": self.intervention,
            "outcome": self.outcome,
            "direction": self.direction,
            "strength": self.strength.value,
            "paper_count": self.paper_count,
            "supporting_papers": self.supporting_papers,
            "opposing_papers": self.opposing_papers,
            "effect_summary": self.effect_summary,
            "confidence_interval": self.confidence_interval,
            "heterogeneity": self.heterogeneity,
            "grade_rating": self.grade_rating,
            "recommendation": self.recommendation,
        }


# =============================================================================
# Constants
# =============================================================================

# Evidence level weights (Oxford CEBM)
EVIDENCE_WEIGHTS = {
    "1a": 1.0,   # Meta-analysis of RCTs
    "1b": 0.9,   # Individual RCT
    "2a": 0.7,   # Systematic review of cohort studies
    "2b": 0.6,   # Individual cohort study
    "3": 0.4,    # Case-control study
    "4": 0.2,    # Case series
    "5": 0.1,    # Expert opinion / unknown
}

# GRADE quality starting points
GRADE_STARTING_QUALITY = {
    "1a": "high",
    "1b": "high",
    "2a": "moderate",
    "2b": "moderate",
    "3": "low",
    "4": "very_low",
    "5": "very_low",
}


# =============================================================================
# Evidence Synthesizer
# =============================================================================

class EvidenceSynthesizer:
    """근거 종합기.

    다수 논문의 결과를 통합하여 메타 분석 수준의 근거를 제공합니다.
    """

    def __init__(self, neo4j_client, llm_client=None):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            llm_client: LLM 클라이언트 (optional, 자연어 요약용)
        """
        self.neo4j = neo4j_client
        self.llm = llm_client

    async def synthesize(
        self,
        intervention: str,
        outcome: str,
        min_papers: int = 1
    ) -> SynthesisResult:
        """근거 종합.

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름
            min_papers: 최소 논문 수 (기본값: 1)

        Returns:
            SynthesisResult 객체
        """
        logger.info(f"Synthesizing evidence: {intervention} → {outcome}")

        # 1. Gather all evidence from Neo4j
        evidence_items = await self._gather_evidence(intervention, outcome)

        if len(evidence_items) < min_papers:
            logger.warning(f"Insufficient evidence: {len(evidence_items)} papers (min: {min_papers})")
            return SynthesisResult(
                intervention=intervention,
                outcome=outcome,
                direction="insufficient",
                strength=EvidenceStrength.INSUFFICIENT,
                paper_count=len(evidence_items),
                effect_summary=f"Only {len(evidence_items)} study(ies) found",
                grade_rating="D",
                recommendation="Insufficient evidence to make a recommendation.",
                evidence_items=evidence_items,
            )

        # 2. Calculate pooled effect (if possible)
        pooled_effect = self._calculate_pooled_effect(evidence_items)

        # 3. Assess heterogeneity
        heterogeneity = self._assess_heterogeneity(evidence_items)

        # 4. Determine direction
        direction = self._determine_direction(evidence_items)

        # 5. Separate supporting and opposing papers
        supporting, opposing = self._separate_papers(evidence_items, direction)

        # 6. Determine evidence strength
        strength = self._determine_strength(evidence_items, heterogeneity)

        # 7. Calculate GRADE rating
        grade_rating = self._calculate_grade(evidence_items, strength, heterogeneity)

        # 8. Generate effect summary
        effect_summary = self._generate_effect_summary(
            intervention, outcome, pooled_effect, evidence_items
        )

        # 9. Generate recommendation
        recommendation = self._generate_recommendation(
            intervention, outcome, direction, strength, grade_rating, pooled_effect
        )

        # 10. Create result
        result = SynthesisResult(
            intervention=intervention,
            outcome=outcome,
            direction=direction,
            strength=strength,
            paper_count=len(evidence_items),
            supporting_papers=supporting,
            opposing_papers=opposing,
            effect_summary=effect_summary,
            confidence_interval=(pooled_effect.ci_low, pooled_effect.ci_high) if pooled_effect else None,
            heterogeneity=heterogeneity,
            grade_rating=grade_rating,
            recommendation=recommendation,
            evidence_items=evidence_items,
            pooled_effect=pooled_effect,
        )

        logger.info(
            f"Synthesis complete: {result.direction} (strength: {result.strength.value}, "
            f"GRADE: {result.grade_rating}, papers: {result.paper_count})"
        )

        return result

    async def _gather_evidence(self, intervention: str, outcome: str) -> list[EvidenceItem]:
        """Neo4j에서 근거 수집.

        v1.14.11: Entity Normalization 및 IS_A hierarchy 지원
        - 입력 용어를 정규화하여 DB의 정규화된 이름과 매칭
        - IS_A 관계를 통해 하위 intervention도 검색에 포함
        - Outcome도 정규화하여 매칭

        Args:
            intervention: 수술법 이름 (정규화 전)
            outcome: 결과변수 이름 (정규화 전)

        Returns:
            EvidenceItem 리스트
        """
        # 1. Normalize intervention and outcome names
        normalized_intervention = intervention
        normalized_outcome = outcome

        if NORMALIZER_AVAILABLE and get_normalizer:
            try:
                normalizer = get_normalizer()

                # Normalize intervention
                int_result = normalizer.normalize_intervention(intervention)
                if int_result and int_result.normalized:
                    normalized_intervention = int_result.normalized
                    if normalized_intervention != intervention:
                        logger.info(f"Normalized intervention: '{intervention}' -> '{normalized_intervention}'")

                # Normalize outcome
                out_result = normalizer.normalize_outcome(outcome)
                if out_result and out_result.normalized:
                    normalized_outcome = out_result.normalized
                    if normalized_outcome != outcome:
                        logger.info(f"Normalized outcome: '{outcome}' -> '{normalized_outcome}'")
            except Exception as e:
                logger.warning(f"Entity normalization failed: {e}")

        # 2. Expanded Cypher query with IS_A hierarchy support
        # This query includes the intervention itself AND all descendants via IS_A relationship
        cypher = """
        // Find target intervention and all its descendants via IS_A relationship
        MATCH (target:Intervention {name: $intervention})
        OPTIONAL MATCH (child:Intervention)-[:IS_A*1..3]->(target)
        WITH COLLECT(DISTINCT target) + COLLECT(DISTINCT child) AS interventions

        // For each intervention, find outcomes
        UNWIND interventions AS i
        WITH i WHERE i IS NOT NULL
        MATCH (i)-[a:AFFECTS]->(o:Outcome {name: $outcome})
        MATCH (p:Paper)-[:INVESTIGATES]->(i)
        WHERE a.source_paper_id = p.paper_id
        RETURN
            p.paper_id as paper_id,
            p.title as title,
            p.evidence_level as evidence_level,
            p.year as year,
            p.sample_size as sample_size,
            a.value as value,
            a.value_control as value_control,
            a.p_value as p_value,
            a.direction as direction,
            a.is_significant as is_significant,
            i.name as matched_intervention
        ORDER BY p.evidence_level, p.year DESC
        """

        records = await self.neo4j.run_query(
            cypher,
            {"intervention": normalized_intervention, "outcome": normalized_outcome}
        )

        # 3. If no results with hierarchy, try fallback with just the normalized name
        if not records:
            logger.info(f"No results with hierarchy, trying direct match")
            fallback_cypher = """
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
            MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WHERE a.source_paper_id = p.paper_id
            RETURN
                p.paper_id as paper_id,
                p.title as title,
                p.evidence_level as evidence_level,
                p.year as year,
                p.sample_size as sample_size,
                a.value as value,
                a.value_control as value_control,
                a.p_value as p_value,
                a.direction as direction,
                a.is_significant as is_significant,
                i.name as matched_intervention
            ORDER BY p.evidence_level, p.year DESC
            """
            records = await self.neo4j.run_query(
                fallback_cypher,
                {"intervention": normalized_intervention, "outcome": normalized_outcome}
            )

        # 4. If still no results, try fuzzy matching on outcome name
        if not records:
            logger.info(f"No results, trying fuzzy outcome match")
            fuzzy_cypher = """
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome)
            WHERE toLower(o.name) CONTAINS toLower($outcome_partial)
               OR toLower($outcome_partial) CONTAINS toLower(o.name)
            MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WHERE a.source_paper_id = p.paper_id
            RETURN
                p.paper_id as paper_id,
                p.title as title,
                p.evidence_level as evidence_level,
                p.year as year,
                p.sample_size as sample_size,
                a.value as value,
                a.value_control as value_control,
                a.p_value as p_value,
                a.direction as direction,
                a.is_significant as is_significant,
                i.name as matched_intervention,
                o.name as matched_outcome
            ORDER BY p.evidence_level, p.year DESC
            LIMIT 50
            """
            # Extract key words from outcome for partial matching
            outcome_partial = normalized_outcome.split()[0] if ' ' in normalized_outcome else normalized_outcome
            records = await self.neo4j.run_query(
                fuzzy_cypher,
                {"intervention": normalized_intervention, "outcome_partial": outcome_partial}
            )

        evidence_items = []
        for record in records:
            # Parse value (문자열 → 숫자 변환)
            # v1.14.11: value가 없어도 direction/is_significant 정보로 근거 수집
            value = 0.0
            value_control = None

            try:
                value_str = record.get("value", "")
                if value_str:
                    value = self._parse_numeric_value(value_str)

                value_control_str = record.get("value_control", "")
                if value_control_str:
                    value_control = self._parse_numeric_value(value_control_str)

            except (ValueError, TypeError, ValidationError) as e:
                # Value parsing failed, but we can still use direction/significance
                logger.debug(f"Could not parse value: {e}, using default 0.0")

            evidence_items.append(
                EvidenceItem(
                    paper_id=record.get("paper_id", ""),
                    title=record.get("title", ""),
                    year=record.get("year", 0),
                    evidence_level=record.get("evidence_level", "5"),
                    value=value,
                    value_control=value_control,
                    p_value=record.get("p_value"),
                    direction=record.get("direction", ""),
                    is_significant=record.get("is_significant", False),
                    sample_size=record.get("sample_size", 0),
                )
            )

        logger.info(f"Gathered {len(evidence_items)} evidence items")
        return evidence_items

    def _parse_numeric_value(self, value_str: str) -> float:
        """숫자 값 파싱.

        "3.2 ± 1.1" → 3.2
        "85.2%" → 85.2
        "4.5 points" → 4.5

        Args:
            value_str: 값 문자열

        Returns:
            숫자 값
        """
        if not value_str:
            raise ValidationError("Empty value string")

        # Remove common suffixes
        value_str = value_str.replace("%", "").replace("points", "").strip()

        # Extract first number (before ±)
        match = re.search(r"[-+]?\d*\.?\d+", value_str)
        if match:
            return float(match.group())

        raise ValidationError(f"Could not parse numeric value: {value_str}")

    def _calculate_pooled_effect(self, evidence: list[EvidenceItem]) -> Optional[PooledEffect]:
        """통합 효과 계산.

        가중 평균 및 95% CI 계산.

        Args:
            evidence: 근거 항목 리스트

        Returns:
            PooledEffect 또는 None
        """
        if not evidence:
            return None

        # Extract values and weights
        values = [item.value for item in evidence]
        weights = [item.weight for item in evidence]

        # Calculate total weight (prevent division by zero)
        total_weight = sum(weights)
        if total_weight <= 0:
            logger.warning("Total weight is zero or negative, using uniform weights")
            total_weight = len(weights)
            weights = [1.0] * len(weights)

        # Weighted mean
        weighted_mean = sum(v * w for v, w in zip(values, weights)) / total_weight

        # Weighted standard deviation (clamp variance to prevent negative due to float errors)
        variance = sum(w * (v - weighted_mean) ** 2 for v, w in zip(values, weights)) / total_weight
        variance = max(0.0, variance)  # Clamp to non-negative
        std = math.sqrt(variance)

        # 95% CI (z = 1.96 for 95%)
        n = len(evidence)
        if n <= 0:
            logger.warning("No evidence items, returning default pooled effect")
            return PooledEffect(mean=0.0, std=0.0, ci_low=0.0, ci_high=0.0, n_studies=0)
        se = std / math.sqrt(n)
        ci_low = weighted_mean - 1.96 * se
        ci_high = weighted_mean + 1.96 * se

        return PooledEffect(
            mean=weighted_mean,
            std=std,
            ci_low=ci_low,
            ci_high=ci_high,
            n_studies=n,
        )

    def _assess_heterogeneity(self, evidence: list[EvidenceItem]) -> str:
        """이질성 평가.

        I² 통계량 계산 (간이 버전).

        Args:
            evidence: 근거 항목 리스트

        Returns:
            "low", "moderate", "high"
        """
        if len(evidence) < 2:
            return "low"

        # Calculate variance of effect sizes
        values = [item.value for item in evidence]
        mean_value = statistics.mean(values)
        variance = statistics.variance(values)

        # Calculate coefficient of variation (CV)
        if mean_value == 0:
            cv = 0
        else:
            cv = (math.sqrt(variance) / abs(mean_value)) * 100

        # I² approximation: CV를 이용한 간이 계산
        # CV < 10% → low heterogeneity
        # 10% ≤ CV < 30% → moderate
        # CV ≥ 30% → high

        if cv < 10:
            return "low"
        elif cv < 30:
            return "moderate"
        else:
            return "high"

    def _determine_direction(self, evidence: list[EvidenceItem]) -> str:
        """전체 방향 결정.

        Args:
            evidence: 근거 항목 리스트

        Returns:
            "improved", "worsened", "mixed", "unchanged"
        """
        if not evidence:
            return "insufficient"

        # Count directions
        improved_count = sum(1 for item in evidence if item.direction == "improved")
        worsened_count = sum(1 for item in evidence if item.direction == "worsened")
        unchanged_count = sum(1 for item in evidence if item.direction == "unchanged")

        total = len(evidence)

        # Majority rule with threshold
        if improved_count >= total * 0.7:
            return "improved"
        elif worsened_count >= total * 0.7:
            return "worsened"
        elif unchanged_count >= total * 0.7:
            return "unchanged"
        else:
            return "mixed"

    def _separate_papers(
        self, evidence: list[EvidenceItem], majority_direction: str
    ) -> tuple[list[str], list[str]]:
        """Supporting vs Opposing 논문 분리.

        Args:
            evidence: 근거 항목 리스트
            majority_direction: 주 방향

        Returns:
            (supporting_papers, opposing_papers) 튜플
        """
        supporting = []
        opposing = []

        for item in evidence:
            if item.direction == majority_direction:
                supporting.append(f"{item.paper_id} ({item.title[:50]}...)")
            else:
                opposing.append(f"{item.paper_id} ({item.title[:50]}..., direction: {item.direction})")

        return supporting, opposing

    def _determine_strength(
        self,
        evidence: list[EvidenceItem],
        heterogeneity: str
    ) -> EvidenceStrength:
        """근거 강도 결정.

        기준:
        - 연구 수
        - 근거 수준
        - 방향의 일관성
        - 통계적 유의성
        - 이질성

        Args:
            evidence: 근거 항목 리스트
            heterogeneity: 이질성 수준

        Returns:
            EvidenceStrength
        """
        n = len(evidence)

        # Check high-quality studies (1a, 1b)
        high_quality_count = sum(
            1 for item in evidence if item.evidence_level in ["1a", "1b"]
        )

        # Check significant results
        significant_count = sum(1 for item in evidence if item.is_significant)
        significant_ratio = significant_count / n if n > 0 else 0

        # Check consistency
        directions = [item.direction for item in evidence]
        most_common_direction = max(set(directions), key=directions.count)
        consistency = directions.count(most_common_direction) / n if n > 0 else 0

        # Determine strength
        # STRONG: Multiple high-quality RCTs (>=2) with consistent results OR 5+ studies
        if ((n >= 3 and high_quality_count >= 2 and consistency >= 0.8 and heterogeneity == "low") or
            (n >= 5 and high_quality_count >= 2 and consistency >= 0.8)):
            return EvidenceStrength.STRONG
        # MODERATE: At least 1 RCT or good significant ratio
        elif n >= 3 and (high_quality_count >= 1 or significant_ratio >= 0.5) and consistency >= 0.6:
            return EvidenceStrength.MODERATE
        # WEAK: Some evidence but low quality or inconsistent
        elif n >= 1 and (consistency >= 0.5 or significant_ratio >= 0.3):
            return EvidenceStrength.WEAK
        else:
            return EvidenceStrength.INSUFFICIENT

    def _calculate_grade(
        self,
        evidence: list[EvidenceItem],
        strength: EvidenceStrength,
        heterogeneity: str
    ) -> str:
        """GRADE 등급 계산.

        GRADE methodology:
        - A: High quality - Multiple RCTs with consistent results
        - B: Moderate - RCTs with limitations or consistent observational
        - C: Low - Observational studies
        - D: Very low - Case series or conflicting evidence

        Args:
            evidence: 근거 항목 리스트
            strength: 근거 강도
            heterogeneity: 이질성 수준

        Returns:
            "A", "B", "C", "D"
        """
        if not evidence:
            return "D"

        # Get highest evidence level
        evidence_levels = [item.evidence_level for item in evidence]
        highest_level = min(evidence_levels)  # "1a" < "1b" < "2a" ...

        # Starting quality
        quality = GRADE_STARTING_QUALITY.get(highest_level, "very_low")

        # Downgrade for heterogeneity
        if heterogeneity == "high":
            quality = self._downgrade_quality(quality, 2)
        elif heterogeneity == "moderate":
            quality = self._downgrade_quality(quality, 1)

        # Downgrade for inconsistency
        if strength == EvidenceStrength.WEAK:
            quality = self._downgrade_quality(quality, 1)
        elif strength == EvidenceStrength.INSUFFICIENT:
            quality = self._downgrade_quality(quality, 2)

        # Map to letter grade
        grade_mapping = {
            "high": "A",
            "moderate": "B",
            "low": "C",
            "very_low": "D",
        }

        return grade_mapping.get(quality, "D")

    def _downgrade_quality(self, quality: str, levels: int) -> str:
        """GRADE 품질 다운그레이드.

        Args:
            quality: 현재 품질 수준
            levels: 다운그레이드 레벨 수

        Returns:
            다운그레이드된 품질 수준
        """
        quality_levels = ["very_low", "low", "moderate", "high"]
        current_idx = quality_levels.index(quality) if quality in quality_levels else 0
        new_idx = max(0, current_idx - levels)
        return quality_levels[new_idx]

    def _generate_effect_summary(
        self,
        intervention: str,
        outcome: str,
        pooled_effect: Optional[PooledEffect],
        evidence: list[EvidenceItem]
    ) -> str:
        """효과 요약 생성.

        Args:
            intervention: 수술법
            outcome: 결과변수
            pooled_effect: 통합 효과
            evidence: 근거 항목 리스트

        Returns:
            효과 요약 문자열
        """
        if not evidence:
            return "No evidence available"

        if pooled_effect is None:
            # Fallback: simple mean
            mean_value = statistics.mean([item.value for item in evidence])
            return f"{outcome}: {mean_value:.2f} points (from {len(evidence)} studies)"

        # Determine improvement or worsening
        directions = [item.direction for item in evidence]
        most_common = max(set(directions), key=directions.count)

        if most_common == "improved":
            verb = "improved by"
        elif most_common == "worsened":
            verb = "worsened by"
        else:
            verb = "changed by"

        return (
            f"{outcome} {verb} {abs(pooled_effect.mean):.2f} ± {pooled_effect.std:.2f} points "
            f"(95% CI: {pooled_effect.ci_low:.2f} to {pooled_effect.ci_high:.2f}, "
            f"n={pooled_effect.n_studies} studies)"
        )

    def _generate_recommendation(
        self,
        intervention: str,
        outcome: str,
        direction: str,
        strength: EvidenceStrength,
        grade: str,
        pooled_effect: Optional[PooledEffect]
    ) -> str:
        """권고사항 생성.

        Args:
            intervention: 수술법
            outcome: 결과변수
            direction: 방향
            strength: 근거 강도
            grade: GRADE 등급
            pooled_effect: 통합 효과

        Returns:
            권고사항 문자열
        """
        # Base recommendation
        if direction == "improved" and strength == EvidenceStrength.STRONG:
            rec = f"{intervention} is STRONGLY RECOMMENDED for improving {outcome} (GRADE {grade})."
        elif direction == "improved" and strength == EvidenceStrength.MODERATE:
            rec = f"{intervention} is CONDITIONALLY RECOMMENDED for improving {outcome} (GRADE {grade})."
        elif direction == "improved" and strength == EvidenceStrength.WEAK:
            rec = f"{intervention} MAY improve {outcome}, but evidence is limited (GRADE {grade})."
        elif direction == "worsened":
            rec = f"{intervention} may worsen {outcome}. Use with caution (GRADE {grade})."
        elif direction == "mixed":
            rec = f"Evidence for {intervention} on {outcome} is CONFLICTING. Further research needed (GRADE {grade})."
        elif direction == "unchanged":
            rec = f"{intervention} shows no significant effect on {outcome} (GRADE {grade})."
        else:
            rec = f"Insufficient evidence for {intervention} on {outcome} (GRADE {grade})."

        # Add effect size context if available
        if pooled_effect and direction in ["improved", "worsened"]:
            effect_magnitude = abs(pooled_effect.mean)
            if effect_magnitude > 3.0:  # Clinically significant for VAS/ODI
                rec += " Effect size is CLINICALLY SIGNIFICANT."
            elif effect_magnitude > 1.0:
                rec += " Effect size is MODERATE."
            else:
                rec += " Effect size is SMALL."

        return rec

    async def generate_summary(self, result: SynthesisResult) -> str:
        """자연어 요약 생성.

        Args:
            result: SynthesisResult 객체

        Returns:
            자연어 요약 문자열
        """
        if self.llm:
            # Use LLM for natural language (future enhancement)
            return await self._llm_summary(result)
        else:
            # Rule-based template
            return f"""
═══════════════════════════════════════════════════════════════
Evidence Synthesis: {result.intervention} → {result.outcome}
═══════════════════════════════════════════════════════════════

📊 DIRECTION: {result.direction.upper()}
🔬 STRENGTH: {result.strength.value.upper()} (GRADE {result.grade_rating})
📚 STUDIES: {result.paper_count} papers analyzed

📈 EFFECT: {result.effect_summary}
🔀 HETEROGENEITY: {result.heterogeneity.upper()}

✅ SUPPORTING ({len(result.supporting_papers)}):
{self._format_papers(result.supporting_papers)}

❌ OPPOSING ({len(result.opposing_papers)}):
{self._format_papers(result.opposing_papers)}

💡 RECOMMENDATION:
{result.recommendation}

═══════════════════════════════════════════════════════════════
"""

    def _format_papers(self, papers: list[str], max_display: int = 5) -> str:
        """논문 목록 포맷팅.

        Args:
            papers: 논문 목록
            max_display: 최대 표시 개수

        Returns:
            포맷팅된 문자열
        """
        if not papers:
            return "  (None)"

        display = papers[:max_display]
        lines = [f"  - {paper}" for paper in display]

        if len(papers) > max_display:
            lines.append(f"  ... and {len(papers) - max_display} more")

        return "\n".join(lines)

    async def _llm_summary(self, result: SynthesisResult) -> str:
        """LLM 기반 자연어 요약 (future enhancement).

        Args:
            result: SynthesisResult 객체

        Returns:
            자연어 요약
        """
        # Placeholder for LLM integration
        logger.info("LLM summary not yet implemented, using template")
        return await self.generate_summary(result)


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_weighted_mean(values: list[float], weights: list[float]) -> float:
    """가중 평균 계산.

    Args:
        values: 값 리스트
        weights: 가중치 리스트

    Returns:
        가중 평균
    """
    if not values or not weights or len(values) != len(weights):
        raise ValidationError("values and weights must have same length")

    total_weight = sum(weights)
    if total_weight <= 0:
        # Fallback to simple average if all weights are zero
        return sum(values) / len(values) if values else 0.0

    return sum(v * w for v, w in zip(values, weights)) / total_weight


def calculate_i_squared(effect_sizes: list[float], variances: list[float]) -> float:
    """I² 통계량 계산 (이질성 측정).

    I² = ((Q - df) / Q) * 100

    Args:
        effect_sizes: 효과 크기 리스트
        variances: 분산 리스트

    Returns:
        I² 값 (0-100)
    """
    if len(effect_sizes) < 2:
        return 0.0

    # Q statistic (Cochran's Q)
    n = len(effect_sizes)
    weights = [1 / v if v > 0 else 0 for v in variances]
    weighted_mean = calculate_weighted_mean(effect_sizes, weights)

    q = sum(w * (es - weighted_mean) ** 2 for es, w in zip(effect_sizes, weights))
    df = n - 1

    if q <= df:
        return 0.0

    i_squared = ((q - df) / q) * 100
    return max(0.0, min(100.0, i_squared))


# =============================================================================
# Example Usage
# =============================================================================

async def example_usage():
    """사용 예시."""
    # Mock Neo4j client (실제로는 Neo4jClient 사용)
    from src.graph.neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        # Example 1: TLIF vs VAS
        result = await synthesizer.synthesize(
            intervention="TLIF",
            outcome="VAS"
        )

        print(await synthesizer.generate_summary(result))

        # Example 2: UBE vs ODI
        result2 = await synthesizer.synthesize(
            intervention="UBE",
            outcome="ODI"
        )

        print(await synthesizer.generate_summary(result2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())
