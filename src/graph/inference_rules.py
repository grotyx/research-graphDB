"""Inference Rules for Neo4j Graph.

이 모듈은 그래프 데이터베이스에 추론 능력을 추가합니다:
- Transitive relationships (계층 구조 추론)
- Intervention comparability (수술법 비교 가능성)
- Evidence aggregation (근거 집계)
- Conflict detection (상충 탐지)

사용 예:
    async with InferenceEngine(neo4j_client) as engine:
        # 계층 구조 조회
        ancestors = await engine.get_ancestors("TLIF")

        # 비교 가능한 수술법 찾기
        comparable = await engine.get_comparable_interventions("UBE")

        # 근거 집계
        evidence = await engine.aggregate_evidence("TLIF", "Fusion Rate")
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class InferenceRuleType(Enum):
    """추론 규칙 유형."""
    TRANSITIVE_HIERARCHY = "transitive_hierarchy"
    TRANSITIVE_TREATMENT = "transitive_treatment"
    COMPARABLE_SIBLINGS = "comparable_siblings"
    COMPARISON_PAPERS = "comparison_papers"
    AGGREGATE_EVIDENCE = "aggregate_evidence"
    CONFLICT_DETECTION = "conflict_detection"
    INDIRECT_TREATMENT = "indirect_treatment"
    COMBINED_OUTCOMES = "combined_outcomes"


@dataclass
class InferenceRule:
    """추론 규칙 기본 클래스.

    Attributes:
        name: 규칙 이름
        rule_type: 규칙 유형
        description: 규칙 설명
        cypher_template: Cypher 쿼리 템플릿
        parameters: 필수 파라미터 목록
        confidence_weight: 추론 신뢰도 가중치 (0.0 ~ 1.0)
    """
    name: str
    rule_type: InferenceRuleType
    description: str
    cypher_template: str
    parameters: list[str] = field(default_factory=list)
    confidence_weight: float = 1.0  # Direct evidence = 1.0, Inferred = < 1.0

    def generate_cypher(self, **params) -> str:
        """파라미터를 적용한 Cypher 쿼리 생성.

        Args:
            **params: 쿼리 파라미터

        Returns:
            실행 가능한 Cypher 쿼리 (파라미터는 Neo4j 드라이버가 바인딩)

        Raises:
            ValueError: 필수 파라미터 누락 시

        Note:
            Cypher 쿼리는 $parameter 구문을 사용하며, 실제 값은 Neo4j 드라이버가
            run_query()에서 파라미터로 전달합니다. 이 메서드는 검증만 수행합니다.
        """
        # 필수 파라미터 검증
        missing = [p for p in self.parameters if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")

        # Neo4j는 $parameter 구문을 사용하므로 템플릿을 그대로 반환
        # 실제 파라미터 바인딩은 run_query(cypher, params)에서 수행
        return self.cypher_template

    def validate_result(self, result: list[dict]) -> bool:
        """결과 검증 (서브클래스에서 오버라이드 가능).

        Args:
            result: Cypher 쿼리 결과

        Returns:
            유효성 여부
        """
        return isinstance(result, list)


# ============================================================================
# Transitive Relationship Rules
# ============================================================================

TRANSITIVE_HIERARCHY = InferenceRule(
    name="transitive_hierarchy",
    rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
    description="Find all ancestors/descendants in IS_A hierarchy (transitive closure)",
    cypher_template="""
    MATCH path = (child:Intervention {name: $intervention})-[:IS_A*1..5]->(ancestor:Intervention)
    RETURN ancestor.name as ancestor,
           ancestor.full_name as full_name,
           ancestor.category as category,
           length(path) as distance,
           [node in nodes(path) | node.name] as path_nodes
    ORDER BY distance ASC
    """,
    parameters=["intervention"],
    confidence_weight=1.0,
)

TRANSITIVE_DESCENDANTS = InferenceRule(
    name="transitive_descendants",
    rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
    description="Find all descendants (children) in IS_A hierarchy",
    cypher_template="""
    MATCH path = (parent:Intervention {name: $intervention})<-[:IS_A*1..5]-(descendant:Intervention)
    RETURN descendant.name as descendant,
           descendant.full_name as full_name,
           descendant.category as category,
           length(path) as distance,
           [node in nodes(path) | node.name] as path_nodes
    ORDER BY distance ASC
    """,
    parameters=["intervention"],
    confidence_weight=1.0,
)

TRANSITIVE_TREATMENT = InferenceRule(
    name="transitive_treatment",
    rule_type=InferenceRuleType.TRANSITIVE_TREATMENT,
    description="Infer treatment relationships via hierarchy (if A IS_A B and B TREATS P, then A treats P)",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[:IS_A*0..3]->(parent:Intervention)
    MATCH (parent)-[:TREATS]->(p:Pathology)
    RETURN DISTINCT p.name as pathology,
           p.category as pathology_category,
           parent.name as via_intervention,
           length([(i)-[:IS_A*]->(parent) | 1]) as hierarchy_distance
    ORDER BY hierarchy_distance ASC
    """,
    parameters=["intervention"],
    confidence_weight=0.8,  # Inferred, not direct
)

# ============================================================================
# Comparability Rules
# ============================================================================

COMPARABLE_SIBLINGS = InferenceRule(
    name="comparable_siblings",
    rule_type=InferenceRuleType.COMPARABLE_SIBLINGS,
    description="Find interventions comparable to the given one (same parent category)",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[:IS_A]->(parent:Intervention)
    MATCH (sibling:Intervention)-[:IS_A]->(parent)
    WHERE sibling.name <> $intervention
    RETURN sibling.name as comparable,
           sibling.full_name as full_name,
           sibling.category as category,
           sibling.approach as approach,
           sibling.is_minimally_invasive as is_minimally_invasive,
           parent.name as shared_category
    ORDER BY sibling.name
    """,
    parameters=["intervention"],
    confidence_weight=0.9,
)

COMPARABLE_BY_CATEGORY = InferenceRule(
    name="comparable_by_category",
    rule_type=InferenceRuleType.COMPARABLE_SIBLINGS,
    description="Find interventions in the same category (broader comparison)",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})
    MATCH (other:Intervention)
    WHERE other.name <> $intervention
      AND other.category = i.category
    RETURN other.name as comparable,
           other.full_name as full_name,
           other.approach as approach,
           other.is_minimally_invasive as is_minimally_invasive,
           i.category as shared_category
    ORDER BY other.name
    """,
    parameters=["intervention"],
    confidence_weight=0.7,
)

COMPARISON_PAPERS = InferenceRule(
    name="comparison_papers",
    rule_type=InferenceRuleType.COMPARISON_PAPERS,
    description="Find papers that compare the intervention with alternatives",
    cypher_template="""
    MATCH (p:Paper)-[:INVESTIGATES]->(i1:Intervention {name: $intervention})
    MATCH (p)-[:INVESTIGATES]->(i2:Intervention)
    WHERE i1 <> i2
    RETURN p.paper_id as paper_id,
           p.title as title,
           p.year as year,
           p.evidence_level as evidence_level,
           collect(DISTINCT i2.name) as compared_with,
           count(DISTINCT i2) as num_comparisons
    ORDER BY p.year DESC
    """,
    parameters=["intervention"],
    confidence_weight=1.0,
)

# ============================================================================
# Evidence Aggregation Rules
# ============================================================================

AGGREGATE_EVIDENCE = InferenceRule(
    name="aggregate_evidence",
    rule_type=InferenceRuleType.AGGREGATE_EVIDENCE,
    description="Aggregate outcome evidence across intervention hierarchy",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[:IS_A*0..2]->(related:Intervention)
    MATCH (related)-[a:AFFECTS]->(o:Outcome {name: $outcome})
    RETURN related.name as intervention,
           a.direction as direction,
           a.value as value,
           a.value_control as value_control,
           a.p_value as p_value,
           a.effect_size as effect_size,
           a.is_significant as significant,
           a.source_paper_id as source_paper,
           length([(i)-[:IS_A*]->(related) | 1]) as hierarchy_distance
    ORDER BY hierarchy_distance ASC, a.p_value ASC
    """,
    parameters=["intervention", "outcome"],
    confidence_weight=0.9,
)

AGGREGATE_EVIDENCE_BY_PATHOLOGY = InferenceRule(
    name="aggregate_evidence_by_pathology",
    rule_type=InferenceRuleType.AGGREGATE_EVIDENCE,
    description="Aggregate evidence for intervention-pathology combination",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[:IS_A*0..2]->(related:Intervention)
    MATCH (related)-[:TREATS]->(p:Pathology {name: $pathology})
    MATCH (related)-[a:AFFECTS]->(o:Outcome)
    WHERE a.is_significant = true
    RETURN related.name as intervention,
           o.name as outcome,
           o.type as outcome_type,
           a.direction as direction,
           a.value as value,
           a.p_value as p_value,
           a.source_paper_id as source_paper,
           length([(i)-[:IS_A*]->(related) | 1]) as hierarchy_distance
    ORDER BY hierarchy_distance ASC, o.name, a.p_value ASC
    """,
    parameters=["intervention", "pathology"],
    confidence_weight=0.85,
)

COMBINED_OUTCOMES = InferenceRule(
    name="combined_outcomes",
    rule_type=InferenceRuleType.COMBINED_OUTCOMES,
    description="Get all outcomes for an intervention across all papers",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome)
    OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
    WHERE a.source_paper_id = p.paper_id
    RETURN o.name as outcome,
           o.type as outcome_type,
           o.unit as unit,
           o.direction as desired_direction,
           collect({
               value: a.value,
               value_control: a.value_control,
               p_value: a.p_value,
               direction: a.direction,
               is_significant: a.is_significant,
               paper_id: a.source_paper_id,
               evidence_level: p.evidence_level
           }) as evidence_list
    ORDER BY o.type, o.name
    """,
    parameters=["intervention"],
    confidence_weight=1.0,
)

# ============================================================================
# Conflict Detection Rules
# ============================================================================

CONFLICT_DETECTION = InferenceRule(
    name="conflict_detection",
    rule_type=InferenceRuleType.CONFLICT_DETECTION,
    description="Detect conflicting results for the same intervention-outcome pair",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})-[a1:AFFECTS]->(o:Outcome {name: $outcome})
    MATCH (i)-[a2:AFFECTS]->(o)
    WHERE a1.source_paper_id <> a2.source_paper_id
      AND a1.direction <> a2.direction
      AND a1.is_significant = true
      AND a2.is_significant = true
    RETURN o.name as outcome,
           a1.direction as direction1,
           a1.value as value1,
           a1.p_value as p_value1,
           a1.source_paper_id as paper1,
           a2.direction as direction2,
           a2.value as value2,
           a2.p_value as p_value2,
           a2.source_paper_id as paper2
    """,
    parameters=["intervention", "outcome"],
    confidence_weight=1.0,
)

CROSS_INTERVENTION_CONFLICTS = InferenceRule(
    name="cross_intervention_conflicts",
    rule_type=InferenceRuleType.CONFLICT_DETECTION,
    description="Find conflicts between different interventions for the same outcome",
    cypher_template="""
    MATCH (i1:Intervention)-[a1:AFFECTS]->(o:Outcome {name: $outcome})
    MATCH (i2:Intervention)-[a2:AFFECTS]->(o)
    WHERE i1.name < i2.name  // Prevent duplicates
      AND a1.direction <> a2.direction
      AND a1.is_significant = true
      AND a2.is_significant = true
    RETURN i1.name as intervention1,
           i2.name as intervention2,
           o.name as outcome,
           a1.direction as direction1,
           a1.value as value1,
           a1.p_value as p_value1,
           a1.source_paper_id as paper1,
           a2.direction as direction2,
           a2.value as value2,
           a2.p_value as p_value2,
           a2.source_paper_id as paper2
    ORDER BY i1.name, i2.name
    """,
    parameters=["outcome"],
    confidence_weight=1.0,
)

# ============================================================================
# Indirect Treatment Rules
# ============================================================================

INDIRECT_TREATMENT = InferenceRule(
    name="indirect_treatment",
    rule_type=InferenceRuleType.INDIRECT_TREATMENT,
    description="Find interventions that indirectly treat a pathology via hierarchy",
    cypher_template="""
    MATCH (p:Pathology {name: $pathology})<-[:TREATS]-(parent:Intervention)
    MATCH (child:Intervention)-[:IS_A*1..3]->(parent)
    WHERE NOT (child)-[:TREATS]->(p)  // Not direct treatment
    RETURN DISTINCT child.name as intervention,
           child.full_name as full_name,
           parent.name as via_intervention,
           length([(child)-[:IS_A*]->(parent) | 1]) as hierarchy_distance
    ORDER BY hierarchy_distance ASC
    """,
    parameters=["pathology"],
    confidence_weight=0.7,
)


# ============================================================================
# Module-level functions
# ============================================================================

def get_available_rules() -> list[InferenceRule]:
    """사용 가능한 모든 추론 규칙 조회.

    Returns:
        InferenceRule 객체 리스트
    """
    return [
        TRANSITIVE_HIERARCHY,
        TRANSITIVE_DESCENDANTS,
        TRANSITIVE_TREATMENT,
        COMPARABLE_SIBLINGS,
        COMPARABLE_BY_CATEGORY,
        COMPARISON_PAPERS,
        AGGREGATE_EVIDENCE,
        AGGREGATE_EVIDENCE_BY_PATHOLOGY,
        COMBINED_OUTCOMES,
        CONFLICT_DETECTION,
        CROSS_INTERVENTION_CONFLICTS,
        INDIRECT_TREATMENT,
    ]


def get_rule_by_name(name: str) -> Optional[InferenceRule]:
    """이름으로 추론 규칙 조회.

    Args:
        name: 규칙 이름 (예: "transitive_hierarchy")

    Returns:
        InferenceRule 또는 None
    """
    rules_map = {rule.name: rule for rule in get_available_rules()}
    return rules_map.get(name)


# ============================================================================
# Inference Engine
# ============================================================================

class InferenceEngine:
    """추론 엔진.

    Neo4j 그래프에 대한 추론 기능을 제공합니다.
    - Transitive relationships
    - Comparability analysis
    - Evidence aggregation
    - Conflict detection

    사용 예:
        async with InferenceEngine(neo4j_client) as engine:
            ancestors = await engine.get_ancestors("TLIF")
            comparable = await engine.get_comparable_interventions("UBE")
    """

    def __init__(self, neo4j_client):
        """초기화.

        Args:
            neo4j_client: Neo4jClient 인스턴스
        """
        self.client = neo4j_client
        self.rules = self._load_rules()
        logger.info(f"InferenceEngine initialized with {len(self.rules)} rules")

    def _load_rules(self) -> dict[str, InferenceRule]:
        """모든 추론 규칙 로드.

        Returns:
            규칙 이름 → InferenceRule 매핑
        """
        return {
            # Transitive
            "transitive_hierarchy": TRANSITIVE_HIERARCHY,
            "transitive_descendants": TRANSITIVE_DESCENDANTS,
            "transitive_treatment": TRANSITIVE_TREATMENT,

            # Comparability
            "comparable_siblings": COMPARABLE_SIBLINGS,
            "comparable_by_category": COMPARABLE_BY_CATEGORY,
            "comparison_papers": COMPARISON_PAPERS,

            # Evidence
            "aggregate_evidence": AGGREGATE_EVIDENCE,
            "aggregate_evidence_by_pathology": AGGREGATE_EVIDENCE_BY_PATHOLOGY,
            "combined_outcomes": COMBINED_OUTCOMES,

            # Conflicts
            "conflict_detection": CONFLICT_DETECTION,
            "cross_intervention_conflicts": CROSS_INTERVENTION_CONFLICTS,

            # Indirect
            "indirect_treatment": INDIRECT_TREATMENT,
        }

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass

    # ========================================================================
    # High-level API
    # ========================================================================

    async def get_ancestors(self, intervention: str) -> list[dict]:
        """수술법의 상위 계층 조회 (Transitive closure).

        Args:
            intervention: 수술법 이름 (예: "TLIF")

        Returns:
            상위 계층 목록 (거리순 정렬)

        Example:
            >>> ancestors = await engine.get_ancestors("TLIF")
            >>> # [{"ancestor": "Interbody Fusion", "distance": 1},
            >>>  #  {"ancestor": "Fusion Surgery", "distance": 2}]
        """
        return await self.execute_rule("transitive_hierarchy", intervention=intervention)

    async def get_descendants(self, intervention: str) -> list[dict]:
        """수술법의 하위 계층 조회.

        Args:
            intervention: 수술법 이름 (예: "Fusion Surgery")

        Returns:
            하위 계층 목록 (거리순 정렬)
        """
        return await self.execute_rule("transitive_descendants", intervention=intervention)

    async def get_comparable_interventions(
        self,
        intervention: str,
        strict: bool = True
    ) -> list[dict]:
        """비교 가능한 수술법 검색.

        Args:
            intervention: 기준 수술법
            strict: True면 같은 부모만, False면 같은 카테고리 포함

        Returns:
            비교 가능한 수술법 목록
        """
        if strict:
            return await self.execute_rule("comparable_siblings", intervention=intervention)
        else:
            # 두 규칙 결합
            siblings = await self.execute_rule("comparable_siblings", intervention=intervention)
            category = await self.execute_rule("comparable_by_category", intervention=intervention)

            # 중복 제거 (siblings 우선)
            seen = {item["comparable"] for item in siblings}
            for item in category:
                if item["comparable"] not in seen:
                    siblings.append(item)
                    seen.add(item["comparable"])

            return siblings

    async def infer_treatments(self, intervention: str) -> list[dict]:
        """계층 구조를 통한 치료 관계 추론.

        Args:
            intervention: 수술법 이름

        Returns:
            치료 가능한 질환 목록 (계층 거리 포함)
        """
        return await self.execute_rule("transitive_treatment", intervention=intervention)

    async def find_comparison_studies(self, intervention: str) -> list[dict]:
        """수술법을 비교한 연구 찾기.

        Args:
            intervention: 수술법 이름

        Returns:
            비교 연구 목록
        """
        return await self.execute_rule("comparison_papers", intervention=intervention)

    async def aggregate_evidence(
        self,
        intervention: str,
        outcome: str
    ) -> list[dict]:
        """계층 구조를 통한 근거 집계.

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름

        Returns:
            집계된 근거 목록 (계층 거리, p-value 정렬)
        """
        return await self.execute_rule(
            "aggregate_evidence",
            intervention=intervention,
            outcome=outcome
        )

    async def aggregate_evidence_by_pathology(
        self,
        intervention: str,
        pathology: str
    ) -> list[dict]:
        """질환별 근거 집계.

        Args:
            intervention: 수술법 이름
            pathology: 질환 이름

        Returns:
            질환 관련 모든 결과변수 근거
        """
        return await self.execute_rule(
            "aggregate_evidence_by_pathology",
            intervention=intervention,
            pathology=pathology
        )

    async def get_all_outcomes(self, intervention: str) -> list[dict]:
        """수술법의 모든 결과변수 조회.

        Args:
            intervention: 수술법 이름

        Returns:
            결과변수별 근거 목록
        """
        return await self.execute_rule("combined_outcomes", intervention=intervention)

    async def detect_conflicts(
        self,
        intervention: str,
        outcome: str
    ) -> list[dict]:
        """상충 결과 탐지.

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름

        Returns:
            상충 근거 목록
        """
        return await self.execute_rule(
            "conflict_detection",
            intervention=intervention,
            outcome=outcome
        )

    async def detect_cross_intervention_conflicts(self, outcome: str) -> list[dict]:
        """결과변수에 대한 수술법 간 상충 탐지.

        Args:
            outcome: 결과변수 이름

        Returns:
            수술법 간 상충 목록
        """
        return await self.execute_rule(
            "cross_intervention_conflicts",
            outcome=outcome
        )

    async def find_indirect_treatments(self, pathology: str) -> list[dict]:
        """간접 치료 관계 찾기.

        Args:
            pathology: 질환 이름

        Returns:
            간접적으로 치료 가능한 수술법 목록
        """
        return await self.execute_rule("indirect_treatment", pathology=pathology)

    # ========================================================================
    # Low-level API
    # ========================================================================

    async def execute_rule(
        self,
        rule_name: str,
        **params
    ) -> list[dict]:
        """추론 규칙 실행.

        Args:
            rule_name: 규칙 이름
            **params: 규칙 파라미터

        Returns:
            쿼리 결과

        Raises:
            ValueError: 규칙을 찾을 수 없거나 파라미터 오류
        """
        if rule_name not in self.rules:
            raise ValueError(f"Unknown rule: {rule_name}")

        rule = self.rules[rule_name]

        try:
            cypher = rule.generate_cypher(**params)
            results = await self.client.run_query(cypher, params)

            if not rule.validate_result(results):
                logger.warning(f"Rule {rule_name} returned invalid results")

            logger.debug(
                f"Rule {rule_name} executed: {len(results)} results "
                f"(confidence: {rule.confidence_weight})"
            )

            return results

        except Exception as e:
            logger.error(f"Rule execution failed ({rule_name}): {e}")
            raise

    def get_rule(self, rule_name: str) -> Optional[InferenceRule]:
        """규칙 조회.

        Args:
            rule_name: 규칙 이름

        Returns:
            InferenceRule 또는 None
        """
        return self.rules.get(rule_name)

    def list_rules(
        self,
        rule_type: Optional[InferenceRuleType] = None
    ) -> list[InferenceRule]:
        """규칙 목록 조회.

        Args:
            rule_type: 필터링할 규칙 유형 (None이면 전체)

        Returns:
            InferenceRule 목록
        """
        if rule_type is None:
            return list(self.rules.values())

        return [
            rule for rule in self.rules.values()
            if rule.rule_type == rule_type
        ]


# ============================================================================
# Convenience Functions
# ============================================================================

async def test_inference_engine(neo4j_client):
    """추론 엔진 테스트 함수.

    Args:
        neo4j_client: Neo4jClient 인스턴스
    """
    async with InferenceEngine(neo4j_client) as engine:
        print("=== Testing Inference Engine ===\n")

        # 1. Hierarchy
        print("1. TLIF Ancestors:")
        ancestors = await engine.get_ancestors("TLIF")
        for a in ancestors:
            print(f"   - {a['ancestor']} (distance: {a['distance']})")

        print("\n2. Fusion Surgery Descendants:")
        descendants = await engine.get_descendants("Fusion Surgery")
        for d in descendants[:5]:  # Top 5
            print(f"   - {d['descendant']} (distance: {d['distance']})")

        # 2. Comparability
        print("\n3. Comparable to TLIF:")
        comparable = await engine.get_comparable_interventions("TLIF")
        for c in comparable:
            print(f"   - {c['comparable']} (via {c.get('shared_category', 'N/A')})")

        # 3. Evidence
        print("\n4. TLIF Evidence for Fusion Rate:")
        evidence = await engine.aggregate_evidence("TLIF", "Fusion Rate")
        for e in evidence:
            print(
                f"   - {e['intervention']}: {e['direction']} "
                f"(p={e['p_value']}, distance={e['hierarchy_distance']})"
            )

        # 4. Conflicts
        print("\n5. Conflicts for UBE + VAS:")
        conflicts = await engine.detect_conflicts("UBE", "VAS")
        if conflicts:
            for c in conflicts:
                print(
                    f"   - Paper {c['paper1']}: {c['direction1']} "
                    f"vs Paper {c['paper2']}: {c['direction2']}"
                )
        else:
            print("   No conflicts found")


if __name__ == "__main__":
    import asyncio
    from .neo4j_client import Neo4jClient

    async def main():
        async with Neo4jClient() as client:
            await client.initialize_schema()
            await test_inference_engine(client)

    asyncio.run(main())
