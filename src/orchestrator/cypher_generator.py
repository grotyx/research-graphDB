"""Cypher Query Generator.

자연어 쿼리를 Neo4j Cypher 쿼리로 변환.
- 엔티티 추출 (수술법, 질환, 결과변수)
- 의도 분석 (검색, 비교, 계층 탐색)
- Cypher 쿼리 생성
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

# Flexible imports for compatibility
try:
    from src.graph.entity_normalizer import EntityNormalizer, get_normalizer
    from src.graph.spine_schema import CypherTemplates
except ImportError:
    from graph.entity_normalizer import EntityNormalizer, get_normalizer
    from graph.spine_schema import CypherTemplates

logger = logging.getLogger(__name__)


@dataclass
class QueryIntent:
    """쿼리 의도."""
    intent_type: str  # evidence_search, comparison, hierarchy, conflict
    confidence: float = 0.0
    description: str = ""


@dataclass
class ExtractedEntities:
    """추출된 엔티티."""
    interventions: list[str]
    pathologies: list[str]
    outcomes: list[str]
    anatomy: list[str]
    sub_domain: Optional[str] = None


class CypherGenerator:
    """자연어 쿼리를 Cypher로 변환.

    사용 예:
        generator = CypherGenerator()
        entities = generator.extract_entities("OLIF가 VAS 개선에 효과적인가?")
        cypher = generator.generate(query, entities)
    """

    def __init__(self, normalizer: Optional[EntityNormalizer] = None):
        """초기화.

        Args:
            normalizer: 엔티티 정규화기 (None이면 기본 사용)
        """
        self.normalizer = normalizer or get_normalizer()

        # 의도 감지 패턴
        self.intent_patterns = {
            "evidence_search": [
                r"효과적",
                r"효과가",
                r"개선",
                r"치료",
                r"결과",
                r"effective",
                r"improve",
                r"treatment",
                r"outcome"
            ],
            "comparison": [
                r"비교",
                r"차이",
                r"vs",
                r"versus",
                r"compare",
                r"difference"
            ],
            "hierarchy": [
                r"종류",
                r"분류",
                r"계층",
                r"하위",
                r"상위",
                r"type",
                r"category",
                r"hierarchy",
                r"parent",
                r"child"
            ],
            "conflict": [
                r"논란",
                r"상충",
                r"일치하지",
                r"inconsistent",
                r"conflicting",
                r"controversial"
            ]
        }

    def extract_entities(self, query: str) -> dict:
        """자연어 쿼리에서 엔티티 추출.

        Args:
            query: 사용자 쿼리

        Returns:
            추출된 엔티티 딕셔너리

        Example:
            Input: "OLIF가 VAS 개선에 효과적인가?"
            Output: {
                "interventions": ["OLIF"],
                "outcomes": ["VAS"],
                "pathologies": [],
                "intent": "evidence_search"
            }
        """
        # 수술법 추출
        interventions = self.normalizer.extract_and_normalize_interventions(query)
        intervention_names = [r.normalized for r in interventions]

        # 결과변수 추출
        outcomes = self.normalizer.extract_and_normalize_outcomes(query)
        outcome_names = [r.normalized for r in outcomes]

        # 질환명 추출 (간단한 패턴 매칭)
        pathologies = []
        for pathology, aliases in self.normalizer.PATHOLOGY_ALIASES.items():
            all_terms = [pathology] + aliases
            for term in all_terms:
                if re.search(r'\b' + re.escape(term.lower()) + r'\b', query.lower()):
                    pathologies.append(pathology)
                    break

        # 의도 감지
        intent = self._detect_intent(query)

        # 해부학적 위치 추출 (간단한 패턴)
        anatomy = self._extract_anatomy(query)

        # Sub-domain 추출 (키워드 기반)
        sub_domain = self._extract_subdomain(query)

        return {
            "interventions": intervention_names,
            "outcomes": outcome_names,
            "pathologies": list(set(pathologies)),
            "anatomy": anatomy,
            "sub_domain": sub_domain,
            "intent": intent.intent_type,
            "intent_confidence": intent.confidence
        }

    def _detect_intent(self, query: str) -> QueryIntent:
        """쿼리 의도 감지."""
        query_lower = query.lower()
        scores = {}

        for intent_type, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    score += 1
            scores[intent_type] = score

        # 가장 높은 점수의 의도
        if not scores or max(scores.values()) == 0:
            return QueryIntent(
                intent_type="evidence_search",
                confidence=0.5,
                description="Default to evidence search"
            )

        best_intent = max(scores.keys(), key=lambda k: scores[k])
        max_score = scores[best_intent]
        total_patterns = len(self.intent_patterns[best_intent])

        return QueryIntent(
            intent_type=best_intent,
            confidence=min(max_score / total_patterns, 1.0),
            description=f"Detected {best_intent} intent"
        )

    def _extract_anatomy(self, query: str) -> list[str]:
        """해부학적 위치 추출."""
        anatomy = []

        # 요추 (L1-L5)
        lumbar_matches = re.findall(r'L\d+-?\d*', query, re.IGNORECASE)
        anatomy.extend(lumbar_matches)

        # 경추 (C1-C7)
        cervical_matches = re.findall(r'C\d+-?\d*', query, re.IGNORECASE)
        anatomy.extend(cervical_matches)

        # 흉추 (T1-T12)
        thoracic_matches = re.findall(r'T\d+-?\d*', query, re.IGNORECASE)
        anatomy.extend(thoracic_matches)

        return list(set(anatomy))

    def _extract_subdomain(self, query: str) -> Optional[str]:
        """척추 하위도메인 추출."""
        query_lower = query.lower()

        subdomain_keywords = {
            "Degenerative": ["퇴행", "협착", "탈출", "협착증", "stenosis", "herniation", "degenerative"],
            "Deformity": ["변형", "측만", "후만", "AIS", "ASD", "deformity", "scoliosis", "kyphosis"],
            "Trauma": ["외상", "골절", "fracture", "trauma", "burst"],
            "Tumor": ["종양", "전이", "tumor", "metastasis"],
        }

        for subdomain, keywords in subdomain_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return subdomain

        return None

    def generate(self, query: str, entities: dict) -> tuple[str, dict]:
        """자연어 쿼리를 파라미터화된 Cypher로 변환 (v1.15 보안 강화).

        Args:
            query: 사용자 쿼리
            entities: extract_entities()로 추출된 엔티티

        Returns:
            (Cypher 쿼리 문자열, 파라미터 딕셔너리) 튜플

        Example:
            Input: "OLIF가 VAS 개선에 효과적인가?"
            Output: ("MATCH (i:Intervention {name: $intervention})...", {"intervention": "OLIF"})
        """
        intent = entities.get("intent", "evidence_search")
        interventions = entities.get("interventions", [])
        outcomes = entities.get("outcomes", [])
        pathologies = entities.get("pathologies", [])

        # 의도별 Cypher 생성
        if intent == "evidence_search":
            return self._generate_evidence_search(interventions, outcomes, pathologies)

        elif intent == "comparison":
            return self._generate_comparison(interventions, outcomes)

        elif intent == "hierarchy":
            return self._generate_hierarchy(interventions)

        elif intent == "conflict":
            return self._generate_conflict(interventions, outcomes)

        else:
            # 기본: 근거 검색
            return self._generate_evidence_search(interventions, outcomes, pathologies)

    def _generate_evidence_search(
        self,
        interventions: list[str],
        outcomes: list[str],
        pathologies: list[str]
    ) -> tuple[str, dict]:
        """근거 기반 검색 Cypher 생성 (파라미터화)."""
        if interventions and outcomes:
            # Intervention → Outcome 검색
            return ("""
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
            WHERE a.is_significant = true
            RETURN i.name as intervention,
                   o.name as outcome,
                   a.value as value,
                   a.value_control as value_control,
                   a.p_value as p_value,
                   a.direction as direction,
                   a.source_paper_id as source_paper_id
            ORDER BY a.p_value ASC
            LIMIT 20
            """, {"intervention": interventions[0], "outcome": outcomes[0]})

        elif pathologies and not interventions:
            # Pathology → Intervention 검색
            return ("""
            MATCH (i:Intervention)-[:TREATS]->(path:Pathology {name: $pathology})
            OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
            WHERE a.is_significant = true
            RETURN i.name as intervention,
                   i.full_name as full_name,
                   collect(DISTINCT {outcome: o.name, value: a.value, p_value: a.p_value}) as outcomes
            LIMIT 20
            """, {"pathology": pathologies[0]})

        elif outcomes and not interventions:
            # Outcome → Intervention 검색
            return ("""
            MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: $outcome})
            WHERE a.is_significant = true AND a.direction = 'improved'
            RETURN i.name as intervention,
                   a.value as value,
                   a.p_value as p_value,
                   a.source_paper_id as source_paper_id
            ORDER BY a.p_value ASC
            LIMIT 20
            """, {"outcome": outcomes[0]})

        elif interventions and not outcomes:
            # v1.14.18: Intervention만 있는 경우 → 해당 수술법 관련 논문 검색
            # IS_A 계층을 통해 하위 수술법도 포함
            return ("""
            MATCH (target:Intervention {name: $intervention})
            OPTIONAL MATCH (child:Intervention)-[:IS_A*1..2]->(target)
            WITH COLLECT(DISTINCT target.name) + COLLECT(DISTINCT child.name) AS intervention_names
            MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
            WHERE i.name IN intervention_names
            RETURN DISTINCT p.paper_id as paper_id,
                   p.title as title,
                   p.year as year,
                   p.journal as journal,
                   p.sub_domain as sub_domain,
                   p.study_design as study_design
            ORDER BY p.year DESC
            LIMIT 20
            """, {"intervention": interventions[0]})

        else:
            # 기본: 검색어 기반 제목/초록 검색 (v1.14.18)
            return ("""
            MATCH (p:Paper)
            WHERE toLower(p.title) CONTAINS toLower($search_term)
               OR toLower(p.abstract) CONTAINS toLower($search_term)
            RETURN p.paper_id as paper_id,
                   p.title as title,
                   p.year as year,
                   p.evidence_level as evidence_level
            ORDER BY p.year DESC
            LIMIT 20
            """, {})

    def _generate_comparison(
        self,
        interventions: list[str],
        outcomes: list[str]
    ) -> tuple[str, dict]:
        """수술법 비교 Cypher 생성 (파라미터화)."""
        if len(interventions) >= 2 and outcomes:
            # 두 수술법의 동일 결과변수 비교
            return ("""
            MATCH (i1:Intervention {name: $intervention1})-[a1:AFFECTS]->(o:Outcome {name: $outcome})
            MATCH (i2:Intervention {name: $intervention2})-[a2:AFFECTS]->(o)
            WHERE a1.is_significant = true AND a2.is_significant = true
            RETURN i1.name as intervention1,
                   i2.name as intervention2,
                   o.name as outcome,
                   a1.value as value1,
                   a2.value as value2,
                   a1.p_value as p_value1,
                   a2.p_value as p_value2,
                   a1.source_paper_id as paper1,
                   a2.source_paper_id as paper2
            """, {"intervention1": interventions[0], "intervention2": interventions[1], "outcome": outcomes[0]})

        elif interventions:
            # 한 수술법의 모든 결과 조회
            return ("""
            MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome)
            WHERE a.is_significant = true
            RETURN o.name as outcome,
                   a.value as value,
                   a.p_value as p_value,
                   a.direction as direction
            ORDER BY a.p_value ASC
            """, {"intervention": interventions[0]})

        else:
            return ("MATCH (n) RETURN n LIMIT 0", {})

    def _generate_hierarchy(self, interventions: list[str]) -> tuple[str, dict]:
        """계층 탐색 Cypher 생성 (파라미터화)."""
        if interventions:
            return ("""
            MATCH (i:Intervention {name: $intervention})
            OPTIONAL MATCH path1 = (i)-[:IS_A*1..5]->(parent:Intervention)
            OPTIONAL MATCH path2 = (child:Intervention)-[:IS_A*1..3]->(i)
            RETURN i.name as name,
                   i.full_name as full_name,
                   i.category as category,
                   collect(DISTINCT parent.name) as parents,
                   collect(DISTINCT child.name) as children
            """, {"intervention": interventions[0]})
        else:
            # 최상위 카테고리 조회
            return ("""
            MATCH (i:Intervention)
            WHERE NOT (i)-[:IS_A]->()
            RETURN i.name as name,
                   i.category as category
            ORDER BY i.name
            """, {})

    def _generate_conflict(
        self,
        interventions: list[str],
        outcomes: list[str]
    ) -> tuple[str, dict]:
        """상충 결과 탐지 Cypher 생성 (파라미터화)."""
        if interventions and outcomes:
            return ("""
            MATCH (i:Intervention {name: $intervention})-[a1:AFFECTS]->(o:Outcome {name: $outcome})
            MATCH (i)-[a2:AFFECTS]->(o)
            WHERE a1.direction <> a2.direction
              AND a1.is_significant = true AND a2.is_significant = true
              AND a1.source_paper_id <> a2.source_paper_id
            RETURN i.name as intervention,
                   o.name as outcome,
                   a1.direction as direction1,
                   a2.direction as direction2,
                   a1.value as value1,
                   a2.value as value2,
                   a1.p_value as p_value1,
                   a2.p_value as p_value2,
                   a1.source_paper_id as paper1,
                   a2.source_paper_id as paper2
            """, {"intervention": interventions[0], "outcome": outcomes[0]})

        elif interventions:
            # 한 수술법의 모든 상충 검색
            return ("""
            MATCH (i:Intervention {name: $intervention})-[a1:AFFECTS]->(o:Outcome)
            MATCH (i)-[a2:AFFECTS]->(o)
            WHERE a1.direction <> a2.direction
              AND a1.is_significant = true AND a2.is_significant = true
              AND a1.source_paper_id <> a2.source_paper_id
            RETURN o.name as outcome,
                   a1.direction as direction1,
                   a2.direction as direction2,
                   a1.source_paper_id as paper1,
                   a2.source_paper_id as paper2
            """, {"intervention": interventions[0]})

        else:
            return ("MATCH (n) RETURN n LIMIT 0", {})



# 사용 예시
if __name__ == "__main__":
    generator = CypherGenerator()

    # 예시 쿼리
    queries = [
        "OLIF가 VAS 개선에 효과적인가?",
        "Lumbar Stenosis 치료에 사용되는 수술법은?",
        "TLIF와 PLIF를 Fusion Rate로 비교해줘",
        "Fusion Surgery의 종류는?",
        "OLIF가 간접 감압에 효과적인지 논란이 있는가?"
    ]

    for query in queries:
        print(f"\n쿼리: {query}")
        entities = generator.extract_entities(query)
        print(f"엔티티: {entities}")

        cypher = generator.generate(query, entities)
        print(f"Cypher:\n{cypher}")
