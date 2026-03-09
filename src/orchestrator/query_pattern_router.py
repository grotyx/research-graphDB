"""Query Pattern Router for Spine Surgery Knowledge Graph.

자연어 질의를 분류하고 적절한 Cypher 쿼리 템플릿으로 라우팅.

Supported patterns:
- TREATMENT_COMPARISON: "A vs B for condition"
- PATIENT_SPECIFIC: "elderly patients", "age > 70"
- INDICATION_QUERY: "indications", "적응증"
- OUTCOME_RATE: "발생률", "rate", "incidence"
- EVIDENCE_FILTER: "RCT", "meta-analysis", "근거"
- GENERAL: Default fallback

Example:
    >>> router = QueryPatternRouter()
    >>> parsed = router.parse_query("UBE vs MIS-TLIF for elderly lumbar stenosis")
    >>> parsed.pattern
    QueryPattern.TREATMENT_COMPARISON
    >>> parsed.comparison_pair
    ('UBE', 'MIS-TLIF')
    >>> cypher, params = router.route_to_cypher(parsed)
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class QueryPattern(Enum):
    """질의 패턴 유형."""
    TREATMENT_COMPARISON = "treatment_comparison"
    PATIENT_SPECIFIC = "patient_specific"
    INDICATION_QUERY = "indication_query"
    OUTCOME_RATE = "outcome_rate"
    EVIDENCE_FILTER = "evidence_filter"
    GENERAL = "general"


@dataclass
class ParsedQuery:
    """파싱된 질의.

    Attributes:
        original_query: 원본 질의 문자열
        pattern: 분류된 쿼리 패턴
        confidence: 분류 신뢰도 (0.0-1.0)
        interventions: 추출된 수술법 목록
        pathologies: 추출된 질환 목록
        outcomes: 추출된 결과 변수 목록
        comparison_pair: 비교 대상 수술법 쌍 (TREATMENT_COMPARISON용)
        age_group: 연령군 (PATIENT_SPECIFIC용)
        min_age: 최소 연령 (PATIENT_SPECIFIC용)
        max_age: 최대 연령 (PATIENT_SPECIFIC용)
        evidence_levels: 요청된 근거 수준 목록 (EVIDENCE_FILTER용)
    """
    original_query: str
    pattern: QueryPattern
    confidence: float = 0.0

    # Extracted entities
    interventions: list[str] = field(default_factory=list)
    pathologies: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)

    # Pattern-specific
    comparison_pair: Optional[tuple[str, str]] = None  # For TREATMENT_COMPARISON
    age_group: str = ""                             # For PATIENT_SPECIFIC: pediatric, adult, elderly
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    evidence_levels: list[str] = field(default_factory=list)  # For EVIDENCE_FILTER


class QueryPatternRouter:
    """질의 패턴 분류 및 라우팅.

    자연어 질의를 분석하여 6가지 패턴 중 하나로 분류하고,
    해당 패턴에 적합한 Cypher 쿼리 템플릿을 생성합니다.

    Attributes:
        normalizer: 선택적 EntityNormalizer (용어 정규화용)

    Example:
        >>> router = QueryPatternRouter()
        >>> parsed = router.parse_query("고령 환자에서 UBE의 합병증 발생률은?")
        >>> parsed.pattern
        QueryPattern.OUTCOME_RATE
        >>> parsed.age_group
        'elderly'
        >>> cypher, params = router.route_to_cypher(parsed)
    """

    # Pattern detection keywords (Korean + English)
    # NOTE: All patterns are matched case-insensitively
    COMPARISON_KEYWORDS = [
        r'\bvs\b', r'\bversus\b', r'비교', r'차이', r'어떤\s*게?\s*(좋|나)',
        r'compared\s+to', r'better.*or', r'or.*better'
    ]

    PATIENT_KEYWORDS = [
        r'고령', r'elderly', r'노인', r'young', r'pediatric', r'소아',
        r'[><]\s*\d+\s*세', r'age\s*[><]\s*\d+', r'\d+세\s*(이상|이하|환자)',
        r'patients?\s*[><]\s*\d+', r'years?\s*old'
    ]

    INDICATION_KEYWORDS = [
        r'적응증', r'\bindication', r'contraindication', r'금기',
        r'언제', r'when\s+to', r'criteria'
    ]

    OUTCOME_RATE_KEYWORDS = [
        r'발생률', r'\brate\b', r'incidence', r'prevalence', r'비율',
        r'얼마나', r'how\s+(?:often|many|much)'
    ]

    # Evidence keywords - use lookahead/lookbehind to handle Korean adjacency
    # RCT(?![a-zA-Z]) matches RCT not followed by ASCII letter (handles RCT가)
    EVIDENCE_KEYWORDS = [
        r'RCT(?![a-zA-Z])', r'(?<![a-zA-Z])RCT', r'randomized', r'meta-analysis',
        r'systematic\s+review', r'근거', r'evidence\s+level', r'level\s+\d'
    ]

    # Strong evidence indicators (high weight)
    STRONG_EVIDENCE_KEYWORDS = [
        r'RCT(?![a-zA-Z])', r'(?<![a-zA-Z])RCT',
        r'meta-analysis', r'systematic\s+review'
    ]

    # Intervention patterns (common spine surgery terms)
    # Use lookahead to handle Korean adjacency (e.g., "UBE에")
    INTERVENTION_PATTERNS = [
        r'(UBE|BESS|Biportal)(?![a-zA-Z])',
        r'(TLIF|PLIF|ALIF|OLIF|LLIF|XLIF)(?![a-zA-Z])',
        r'(MIS-?TLIF|Open\s*TLIF)',
        r'(Laminectomy|Laminotomy|Foraminotomy)',
        r'(ACDF|PCDF|CDR|ADR)(?![a-zA-Z])',
        r'(PSO|VCR|SPO|Osteotomy)',
        r'\b(Fusion|Decompression|Fixation)\b',
        r'(내시경|감압술|유합술|고정술)',
    ]

    # Pathology patterns
    PATHOLOGY_PATTERNS = [
        r'(lumbar|cervical|thoracic)\s*(stenosis|협착)',
        r'(요추|경추|흉추)\s*(협착|탈출|전방전위)',
        r'(disc\s*herniation|디스크\s*탈출|HNP|HIVD)',
        r'(spondylolisthesis|전방전위)',
        r'(scoliosis|측만|변형)',
        r'(감염|infection|spondylodiscitis)',
        r'(stenosis|협착증)',
    ]

    # Outcome patterns
    OUTCOME_PATTERNS = [
        r'\b(VAS|ODI|JOA|NDI|EQ-5D|SF-36)\b',
        r'(fusion\s*rate|유합률)',
        r'(complication|합병증)',
        r'(subsidence|침강)',
        r'(reoperation|재수술)',
        r'(dural\s*tear|경막\s*손상)',
    ]

    def __init__(self, entity_normalizer=None):
        """Initialize router.

        Args:
            entity_normalizer: Optional EntityNormalizer for entity normalization
        """
        self.normalizer = entity_normalizer

    def classify_query(self, query: str) -> tuple[QueryPattern, float]:
        """Classify query into a pattern.

        각 패턴별 키워드 매칭 점수를 계산하여 가장 높은 점수의 패턴을 선택합니다.

        Args:
            query: Natural language query

        Returns:
            Tuple of (QueryPattern, confidence)
            - QueryPattern: 분류된 패턴
            - confidence: 분류 신뢰도 (0.0-1.0)
        """
        query_lower = query.lower()

        scores = {
            QueryPattern.TREATMENT_COMPARISON: 0.0,
            QueryPattern.PATIENT_SPECIFIC: 0.0,
            QueryPattern.INDICATION_QUERY: 0.0,
            QueryPattern.OUTCOME_RATE: 0.0,
            QueryPattern.EVIDENCE_FILTER: 0.0,
        }

        # === 1. Check for strong evidence indicators FIRST (high priority) ===
        # Check in BOTH original (for RCT) and lowercase (for meta-analysis)
        for pattern in self.STRONG_EVIDENCE_KEYWORDS:
            if re.search(pattern, query) or re.search(pattern, query_lower):
                scores[QueryPattern.EVIDENCE_FILTER] += 2.0  # High weight

        # === 2. Score COMPARISON (but only if explicit comparison keywords) ===
        for pattern in self.COMPARISON_KEYWORDS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                scores[QueryPattern.TREATMENT_COMPARISON] += 1.0

        # === 3. Score PATIENT_SPECIFIC ===
        for pattern in self.PATIENT_KEYWORDS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                scores[QueryPattern.PATIENT_SPECIFIC] += 1.0

        # === 4. Score INDICATION_QUERY ===
        for pattern in self.INDICATION_KEYWORDS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                scores[QueryPattern.INDICATION_QUERY] += 1.0

        # === 5. Score OUTCOME_RATE ===
        for pattern in self.OUTCOME_RATE_KEYWORDS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                scores[QueryPattern.OUTCOME_RATE] += 1.0

        # === 6. Score remaining EVIDENCE keywords ===
        for pattern in self.EVIDENCE_KEYWORDS:
            # Search both original and lowercase
            if re.search(pattern, query) or re.search(pattern, query_lower):
                scores[QueryPattern.EVIDENCE_FILTER] += 0.5  # Lower weight for non-strong

        # Find best match
        max_score = max(scores.values())
        if max_score == 0:
            return QueryPattern.GENERAL, 0.5

        best_pattern = max(scores, key=scores.get)
        confidence = min(max_score / 3.0, 1.0)  # Normalize confidence

        return best_pattern, confidence

    def extract_entities(self, query: str) -> dict:
        """Extract entities from query.

        정규표현식을 사용하여 수술법, 질환, 결과 변수를 추출합니다.

        Args:
            query: Natural language query

        Returns:
            Dict with interventions, pathologies, outcomes
            - interventions: 추출된 수술법 목록
            - pathologies: 추출된 질환 목록
            - outcomes: 추출된 결과 변수 목록
        """
        entities = {
            "interventions": [],
            "pathologies": [],
            "outcomes": []
        }

        # Extract interventions
        for pattern in self.INTERVENTION_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and match not in entities["interventions"]:
                    entities["interventions"].append(match)

        # Extract pathologies
        for pattern in self.PATHOLOGY_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = " ".join(m for m in match if m)
                if match and match not in entities["pathologies"]:
                    entities["pathologies"].append(match)

        # Extract outcomes
        for pattern in self.OUTCOME_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and match not in entities["outcomes"]:
                    entities["outcomes"].append(match)

        return entities

    def extract_age_info(self, query: str) -> tuple[str, Optional[int], Optional[int]]:
        """Extract age-related information from query.

        연령군 키워드 및 명시적 연령 범위를 추출합니다.

        Args:
            query: Natural language query

        Returns:
            Tuple of (age_group, min_age, max_age)
            - age_group: "pediatric", "adult", "elderly" 중 하나
            - min_age: 최소 연령 (명시된 경우)
            - max_age: 최대 연령 (명시된 경우)
        """
        query_lower = query.lower()
        age_group = ""
        min_age = None
        max_age = None

        # Age group keywords
        if any(kw in query_lower for kw in ["고령", "elderly", "노인", ">65", ">70"]):
            age_group = "elderly"
            min_age = 65
        elif any(kw in query_lower for kw in ["소아", "pediatric", "young", "<18"]):
            age_group = "pediatric"
            max_age = 18
        elif any(kw in query_lower for kw in ["성인", "adult"]):
            age_group = "adult"
            min_age = 18
            max_age = 65

        # Explicit age extraction: "70세 이상", ">70", "age > 70"
        age_match = re.search(r'[>≥]\s*(\d+)\s*세?', query)
        if age_match:
            min_age = int(age_match.group(1))

        age_match = re.search(r'[<≤]\s*(\d+)\s*세?', query)
        if age_match:
            max_age = int(age_match.group(1))

        return age_group, min_age, max_age

    def extract_evidence_levels(self, query: str) -> list[str]:
        """Extract requested evidence levels.

        질의에서 요청된 근거 수준을 추출합니다.

        Args:
            query: Natural language query

        Returns:
            List of evidence level codes (e.g., ["1a", "1b"])
        """
        query_lower = query.lower()
        levels = []

        if any(kw in query_lower for kw in ["rct", "randomized", "무작위"]):
            levels.extend(["1a", "1b"])
        if any(kw in query_lower for kw in ["meta-analysis", "systematic review", "메타분석"]):
            levels.append("1a")
        if any(kw in query_lower for kw in ["cohort", "코호트"]):
            levels.extend(["2a", "2b"])

        return list(set(levels)) if levels else ["1a", "1b", "2a", "2b"]  # Default to high-quality

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse and classify a query.

        질의를 분석하여 패턴 분류, 엔티티 추출, 메타데이터 추출을 수행합니다.

        Args:
            query: Natural language query

        Returns:
            ParsedQuery with pattern, entities, and metadata
        """
        pattern, confidence = self.classify_query(query)
        entities = self.extract_entities(query)

        parsed = ParsedQuery(
            original_query=query,
            pattern=pattern,
            confidence=confidence,
            interventions=entities["interventions"],
            pathologies=entities["pathologies"],
            outcomes=entities["outcomes"]
        )

        # Pattern-specific extraction
        if pattern == QueryPattern.TREATMENT_COMPARISON:
            # Try to extract comparison pair
            if len(parsed.interventions) >= 2:
                parsed.comparison_pair = (parsed.interventions[0], parsed.interventions[1])

        elif pattern == QueryPattern.PATIENT_SPECIFIC:
            age_group, min_age, max_age = self.extract_age_info(query)
            parsed.age_group = age_group
            parsed.min_age = min_age
            parsed.max_age = max_age

        elif pattern == QueryPattern.EVIDENCE_FILTER:
            parsed.evidence_levels = self.extract_evidence_levels(query)

        logger.info(
            f"Parsed query: pattern={pattern.value}, confidence={confidence:.2f}, "
            f"interventions={parsed.interventions}, pathologies={parsed.pathologies}"
        )

        return parsed

    def get_cypher_template(self, pattern: QueryPattern) -> str:
        """Get Cypher template for a pattern.

        각 패턴에 최적화된 Cypher 쿼리 템플릿을 반환합니다.

        Args:
            pattern: Query pattern

        Returns:
            Cypher query template string
        """
        templates = {
            QueryPattern.TREATMENT_COMPARISON: """
                MATCH (path:Pathology)
                WHERE path.name IN $pathology_variants
                MATCH (i1:Intervention)-[:TREATS]->(path)
                MATCH (i2:Intervention)-[:TREATS]->(path)
                WHERE i1.name IN $intervention1_variants
                  AND i2.name IN $intervention2_variants
                OPTIONAL MATCH (i1)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2)
                RETURN i1.name as intervention1, i2.name as intervention2,
                       o.name as outcome, a1.value as value1, a2.value as value2,
                       a1.p_value as p1, a2.p_value as p2
                ORDER BY a1.p_value ASC
                LIMIT 50
            """,

            QueryPattern.PATIENT_SPECIFIC: """
                MATCH (p:Paper)
                WHERE ($age_group = '' OR p.patient_age_group = $age_group)
                   OR ($min_age IS NOT NULL AND p.mean_age >= $min_age)
                   OR ($max_age IS NOT NULL AND p.mean_age <= $max_age)
                MATCH (p)-[:INVESTIGATES]->(i:Intervention)
                WHERE i.name IN $intervention_variants
                OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
                WHERE o.type = $outcome_type OR $outcome_type = ''
                RETURN p.title, p.year, p.patient_age_group, p.mean_age,
                       i.name as intervention, o.name as outcome,
                       a.value, a.is_significant
                ORDER BY p.evidence_level ASC, p.year DESC
                LIMIT 50
            """,

            QueryPattern.INDICATION_QUERY: """
                MATCH (path:Pathology)
                WHERE path.name IN $pathology_variants
                MATCH (i:Intervention)-[t:TREATS]->(path)
                WHERE t.indication IS NOT NULL AND t.indication <> ''
                RETURN i.name as intervention, i.category,
                       t.indication, t.contraindication, t.indication_level
                ORDER BY t.indication_level DESC
            """,

            QueryPattern.OUTCOME_RATE: """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE i.name IN $intervention_variants
                  AND o.name IN $outcome_variants
                WITH i, o, collect(a) as affects_list
                RETURN
                  i.name as intervention,
                  o.name as outcome,
                  size(affects_list) as study_count,
                  [a IN affects_list | {
                    paper: a.source_paper_id,
                    value: a.value,
                    p_value: a.p_value,
                    direction: a.direction
                  }][..10] as studies
            """,

            QueryPattern.EVIDENCE_FILTER: """
                MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
                WHERE i.name IN $intervention_variants
                  AND p.evidence_level IN $evidence_levels
                RETURN p.paper_id, p.title, p.year, p.evidence_level,
                       p.sample_size, p.study_design, i.name as intervention
                ORDER BY
                  CASE p.evidence_level
                    WHEN '1a' THEN 1 WHEN '1b' THEN 2
                    WHEN '2a' THEN 3 WHEN '2b' THEN 4
                    ELSE 5
                  END,
                  p.year DESC
                LIMIT 50
            """,

            QueryPattern.GENERAL: """
                MATCH (p:Paper)
                WHERE p.title CONTAINS $search_term
                   OR ANY(kw IN p.key_findings WHERE kw CONTAINS $search_term)
                OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
                OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
                RETURN p.title, p.year, p.evidence_level,
                       collect(DISTINCT i.name) as interventions,
                       collect(DISTINCT path.name) as pathologies
                ORDER BY p.year DESC
                LIMIT 30
            """
        }

        return templates.get(pattern, templates[QueryPattern.GENERAL])

    def route_to_cypher(
        self,
        parsed: ParsedQuery,
        expanded_context: Optional[dict] = None
    ) -> tuple[str, dict]:
        """Route parsed query to Cypher with parameters.

        파싱된 질의를 Cypher 쿼리와 파라미터로 변환합니다.

        Args:
            parsed: ParsedQuery from parse_query()
            expanded_context: Optional expanded context from GraphContextExpander
                - expanded_interventions: 확장된 수술법 목록
                - expanded_pathologies: 확장된 질환 목록
                - expanded_outcomes: 확장된 결과 변수 목록

        Returns:
            Tuple of (cypher_query, parameters)
            - cypher_query: 실행 가능한 Cypher 쿼리 문자열
            - parameters: Cypher 쿼리 파라미터 딕셔너리
        """
        template = self.get_cypher_template(parsed.pattern)
        expanded_context = expanded_context or {}

        # Build parameters based on pattern
        params = {
            "search_term": parsed.original_query[:100],
        }

        # Use expanded interventions if available, otherwise original
        intervention_variants = expanded_context.get(
            "expanded_interventions",
            parsed.interventions
        )
        pathology_variants = expanded_context.get(
            "expanded_pathologies",
            parsed.pathologies
        )
        outcome_variants = expanded_context.get(
            "expanded_outcomes",
            parsed.outcomes
        )

        params["intervention_variants"] = intervention_variants or [""]
        params["pathology_variants"] = pathology_variants or [""]
        params["outcome_variants"] = outcome_variants or [""]

        # Pattern-specific parameters
        if parsed.pattern == QueryPattern.TREATMENT_COMPARISON:
            if parsed.comparison_pair:
                params["intervention1_variants"] = [parsed.comparison_pair[0]]
                params["intervention2_variants"] = [parsed.comparison_pair[1]]
            else:
                params["intervention1_variants"] = intervention_variants[:1] or [""]
                params["intervention2_variants"] = intervention_variants[1:2] or [""]

        elif parsed.pattern == QueryPattern.PATIENT_SPECIFIC:
            params["age_group"] = parsed.age_group or ""
            params["min_age"] = parsed.min_age
            params["max_age"] = parsed.max_age
            params["outcome_type"] = ""  # Can be filtered later

        elif parsed.pattern == QueryPattern.EVIDENCE_FILTER:
            params["evidence_levels"] = parsed.evidence_levels or ["1a", "1b"]

        return template.strip(), params
