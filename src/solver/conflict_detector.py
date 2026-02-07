"""Conflict Detector for Spine GraphRAG.

충돌 감지기: 동일 수술법-결과 쌍에서 상충하는 연구 결과 탐지.
- 서로 다른 논문이 동일한 Intervention → Outcome에 대해 상반된 결론 보고
- Evidence level 기반 심각도 평가
- 통계적 유의성 검증
- 근거 기반 conflict 요약 생성
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional

# Import with fallback for different execution contexts
try:
    from graph.neo4j_client import Neo4jClient
    from graph.spine_schema import EvidenceLevel
    from solver.conflict_summary import ConflictSummaryGenerator
except ImportError:
    from src.graph.neo4j_client import Neo4jClient
    from src.graph.spine_schema import EvidenceLevel
    from src.solver.conflict_summary import ConflictSummaryGenerator

logger = logging.getLogger(__name__)


class ConflictSeverity(IntEnum):
    """충돌 심각도 수준.

    Evidence level과 논문 수를 고려한 충돌 심각도 분류.
    IntEnum 사용으로 직접 숫자 비교 가능.
    """
    LOW = 1        # Level 4+ 논문 간 충돌 (case series, expert opinion)
    MEDIUM = 2     # Level 3 논문 간 충돌
    HIGH = 3       # Level 2 논문 간 충돌 또는 Level 1-2 혼합
    CRITICAL = 4   # Level 1 (RCT/Meta-analysis) 논문 간 충돌

    @property
    def label(self) -> str:
        """사람이 읽을 수 있는 레이블."""
        return self.name.lower()


# Evidence level 점수 (높을수록 강력한 근거)
EVIDENCE_LEVEL_SCORES = {
    "1a": 10,  # Meta-analysis
    "1b": 9,   # RCT
    "2a": 8,   # Systematic review of cohorts
    "2b": 7,   # Individual cohort
    "3": 5,    # Case-control
    "4": 3,    # Case series
    "5": 1,    # Expert opinion/Unknown
}


@dataclass
class PaperEvidence:
    """논문별 근거 정보."""
    paper_id: str
    title: str
    evidence_level: str
    direction: str  # improved, worsened, unchanged
    value: str
    value_control: str
    p_value: Optional[float]
    is_significant: bool

    @property
    def evidence_score(self) -> int:
        """근거 수준 점수."""
        return EVIDENCE_LEVEL_SCORES.get(self.evidence_level, 1)


@dataclass
class ConflictResult:
    """충돌 탐지 결과.

    동일한 Intervention → Outcome 쌍에 대한 상충 연구 결과.
    """
    intervention: str
    outcome: str

    # 방향별 논문 분류
    papers_improved: list[PaperEvidence] = field(default_factory=list)
    papers_worsened: list[PaperEvidence] = field(default_factory=list)
    papers_unchanged: list[PaperEvidence] = field(default_factory=list)

    severity: ConflictSeverity = ConflictSeverity.LOW
    confidence: float = 0.0
    summary: str = ""

    @property
    def total_papers(self) -> int:
        """총 논문 수."""
        return len(self.papers_improved) + len(self.papers_worsened) + len(self.papers_unchanged)

    @property
    def has_significant_conflict(self) -> bool:
        """의미 있는 충돌이 있는지 (improved vs worsened).

        Returns:
            improved와 worsened 논문이 모두 존재하면 True
        """
        return len(self.papers_improved) > 0 and len(self.papers_worsened) > 0

    @property
    def conflict_ratio(self) -> float:
        """충돌 비율 (0-1).

        Returns:
            min(improved_count, worsened_count) / total_count
        """
        if self.total_papers == 0:
            return 0.0

        conflict_count = min(len(self.papers_improved), len(self.papers_worsened))
        return conflict_count / self.total_papers

    def get_highest_evidence_level(self) -> str:
        """가장 강력한 근거 수준.

        Returns:
            충돌 논문 중 가장 높은 evidence level
        """
        all_papers = self.papers_improved + self.papers_worsened + self.papers_unchanged
        if not all_papers:
            return "5"

        # Evidence level 점수가 가장 높은 것 반환
        best_level = max(all_papers, key=lambda p: p.evidence_score).evidence_level
        return best_level


# ============================================================================
# Legacy Compatibility Classes (for MCP Server backward compatibility)
# ============================================================================

class ConflictType(Enum):
    """충돌 유형 (Legacy API)."""
    CONTRADICTORY_RESULTS = "contradictory_results"
    DIFFERENT_EVIDENCE_LEVELS = "different_evidence_levels"
    INCONSISTENT_DIRECTION = "inconsistent_direction"


@dataclass
class StudyResult:
    """검색 결과 연구 정보 (Legacy API).

    MCP Server에서 검색 결과를 conflict detection에 사용하기 위한 데이터클래스.
    """
    study_id: str
    title: str
    evidence_level: str = "5"
    direction: Optional[str] = None  # improved, worsened, unchanged
    outcome_value: Optional[str] = None


@dataclass
class ConflictPair:
    """충돌 쌍 (Legacy API)."""
    study1: StudyResult
    study2: StudyResult
    conflict_type: ConflictType
    severity: ConflictSeverity


@dataclass
class ConflictInput:
    """충돌 감지 입력 (Legacy API).

    MCP Server에서 conflict detection을 위한 입력 데이터클래스.
    """
    topic: str
    studies: list = field(default_factory=list)  # List[StudyResult]


@dataclass
class ConflictOutput:
    """충돌 감지 출력 (Legacy API)."""
    has_conflicts: bool = False
    conflicts: list = field(default_factory=list)  # List[ConflictPair]
    summary: str = ""


class ConflictDetector:
    """충돌 감지기.

    Neo4j 그래프에서 AFFECTS 관계를 분석하여 상충 결과 탐지.

    사용 예:
        async with Neo4jClient() as client:
            detector = ConflictDetector(client)

            # 특정 Intervention-Outcome 충돌 검사
            conflict = await detector.detect_conflicts("TLIF", "Fusion Rate")
            if conflict and conflict.has_significant_conflict:
                print(f"Conflict severity: {conflict.severity}")
                print(conflict.summary)

            # 모든 충돌 검색
            all_conflicts = await detector.find_all_conflicts()
            for conflict in all_conflicts:
                print(f"{conflict.intervention} → {conflict.outcome}: {conflict.severity}")
    """

    def __init__(self, neo4j_client: Optional[Neo4jClient] = None):
        """초기화.

        Args:
            neo4j_client: Neo4jClient 인스턴스 (Optional for legacy mode)
        """
        self.client = neo4j_client
        self._summary_generator = ConflictSummaryGenerator()

    # =========================================================================
    # Legacy API (for MCP Server backward compatibility)
    # =========================================================================

    def detect(self, conflict_input: ConflictInput) -> ConflictOutput:
        """충돌 감지 (Legacy API).

        검색 결과 목록에서 상충 결과를 탐지합니다.
        NOTE: 이 메서드는 MCP Server 호환성을 위한 레거시 API입니다.

        Args:
            conflict_input: ConflictInput (topic, studies 포함)

        Returns:
            ConflictOutput (has_conflicts, conflicts 포함)
        """
        studies = conflict_input.studies
        if len(studies) < 2:
            return ConflictOutput(has_conflicts=False)

        conflicts = []

        # 모든 쌍에서 충돌 검사
        for i, study1 in enumerate(studies):
            for study2 in studies[i + 1:]:
                # Evidence level이 다른 경우 경고
                level1 = str(study1.evidence_level)
                level2 = str(study2.evidence_level)

                # Evidence level 차이가 큰 경우 (예: Level 1 vs Level 4)
                score1 = EVIDENCE_LEVEL_SCORES.get(level1, 1)
                score2 = EVIDENCE_LEVEL_SCORES.get(level2, 1)

                if abs(score1 - score2) >= 5:
                    # 큰 evidence level 차이
                    severity = self._determine_severity_from_levels(level1, level2)
                    conflicts.append(ConflictPair(
                        study1=study1,
                        study2=study2,
                        conflict_type=ConflictType.DIFFERENT_EVIDENCE_LEVELS,
                        severity=severity
                    ))

        return ConflictOutput(
            has_conflicts=len(conflicts) > 0,
            conflicts=conflicts,
            summary=f"Found {len(conflicts)} potential conflicts in {len(studies)} studies"
        )

    def _determine_severity_from_levels(self, level1: str, level2: str) -> ConflictSeverity:
        """두 근거 수준에서 충돌 심각도 결정."""
        score1 = EVIDENCE_LEVEL_SCORES.get(level1, 1)
        score2 = EVIDENCE_LEVEL_SCORES.get(level2, 1)
        max_score = max(score1, score2)

        if max_score >= 9:  # Level 1a/1b
            return ConflictSeverity.HIGH
        elif max_score >= 7:  # Level 2a/2b
            return ConflictSeverity.MEDIUM
        else:
            return ConflictSeverity.LOW

    async def detect_conflicts(
        self,
        intervention: str,
        outcome: str
    ) -> Optional[ConflictResult]:
        """특정 Intervention-Outcome 쌍의 충돌 탐지.

        Args:
            intervention: 수술법 이름 (예: "TLIF", "UBE")
            outcome: 결과변수 이름 (예: "VAS", "Fusion Rate")

        Returns:
            ConflictResult (충돌이 없으면 None)
        """
        # Neo4j 쿼리: Intervention → Outcome AFFECTS 관계 조회
        cypher = """
        MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
        MATCH (p:Paper)-[:INVESTIGATES]->(i)
        WHERE a.source_paper_id = p.paper_id
        RETURN
            p.paper_id as paper_id,
            p.title as title,
            p.evidence_level as evidence_level,
            a.direction as direction,
            a.value as value,
            a.value_control as value_control,
            a.p_value as p_value,
            a.is_significant as is_significant
        ORDER BY p.evidence_level ASC, p.year DESC
        """

        try:
            results = await self.client.run_query(
                cypher,
                {"intervention": intervention, "outcome": outcome}
            )
        except Exception as e:
            logger.error(f"Failed to query conflicts for {intervention} → {outcome}: {e}")
            return None

        if not results:
            logger.debug(f"No data found for {intervention} → {outcome}")
            return None

        # 결과 분류
        papers_improved = []
        papers_worsened = []
        papers_unchanged = []

        for row in results:
            evidence = PaperEvidence(
                paper_id=row.get("paper_id", ""),
                title=row.get("title", ""),
                evidence_level=row.get("evidence_level", "5"),
                direction=row.get("direction", ""),
                value=row.get("value", ""),
                value_control=row.get("value_control", ""),
                p_value=row.get("p_value"),
                is_significant=row.get("is_significant", False),
            )

            # 방향별 분류
            if evidence.direction == "improved":
                papers_improved.append(evidence)
            elif evidence.direction == "worsened":
                papers_worsened.append(evidence)
            elif evidence.direction == "unchanged":
                papers_unchanged.append(evidence)
            else:
                # direction이 비어있거나 알 수 없는 경우
                papers_unchanged.append(evidence)

        # 충돌 결과 생성
        conflict_result = ConflictResult(
            intervention=intervention,
            outcome=outcome,
            papers_improved=papers_improved,
            papers_worsened=papers_worsened,
            papers_unchanged=papers_unchanged,
        )

        # 충돌이 없으면 None 반환
        if not conflict_result.has_significant_conflict:
            logger.debug(
                f"No significant conflict for {intervention} → {outcome}: "
                f"{len(papers_improved)} improved, {len(papers_worsened)} worsened"
            )
            return None

        # 심각도 계산
        conflict_result.severity = self._calculate_severity(conflict_result)

        # 신뢰도 계산
        conflict_result.confidence = self._calculate_confidence(conflict_result)

        # 요약 생성 (ConflictSummaryGenerator 사용)
        conflict_result.summary = self._summary_generator.generate(conflict_result)

        logger.info(
            f"Conflict detected: {intervention} → {outcome} "
            f"(severity: {conflict_result.severity.label}, confidence: {conflict_result.confidence:.2f})"
        )

        return conflict_result

    async def find_all_conflicts(
        self,
        min_severity: Optional[ConflictSeverity] = None
    ) -> list[ConflictResult]:
        """모든 Intervention-Outcome 쌍에서 충돌 검색.

        Args:
            min_severity: 최소 심각도 필터 (None이면 모두 반환)

        Returns:
            충돌 결과 목록 (심각도 순 정렬)
        """
        # 1. 모든 Intervention-Outcome 쌍 조회
        cypher = """
        MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
        WITH i.name as intervention, o.name as outcome, count(DISTINCT a.source_paper_id) as paper_count
        WHERE paper_count >= 2
        RETURN intervention, outcome, paper_count
        ORDER BY paper_count DESC
        """

        try:
            pairs = await self.client.run_query(cypher)
        except Exception as e:
            logger.error(f"Failed to find intervention-outcome pairs: {e}")
            return []

        logger.info(f"Found {len(pairs)} intervention-outcome pairs with multiple papers")

        # 2. 각 쌍에 대해 충돌 검사
        conflicts = []
        for pair in pairs:
            intervention = pair["intervention"]
            outcome = pair["outcome"]

            conflict = await self.detect_conflicts(intervention, outcome)
            if conflict and conflict.has_significant_conflict:
                # 심각도 필터링
                if min_severity is None or self._compare_severity(conflict.severity, min_severity):
                    conflicts.append(conflict)

        # 심각도 순 정렬 (CRITICAL > HIGH > MEDIUM > LOW)
        conflicts.sort(key=lambda c: self._severity_sort_key(c.severity), reverse=True)

        logger.info(
            f"Found {len(conflicts)} conflicts "
            f"(total pairs: {len(pairs)})"
        )

        return conflicts

    def _calculate_severity(
        self,
        conflict: ConflictResult
    ) -> ConflictSeverity:
        """충돌 심각도 계산.

        규칙:
        - CRITICAL: Level 1 (RCT/Meta-analysis) 논문 간 충돌
        - HIGH: Level 2 논문 간 충돌 OR Level 1-2 혼합
        - MEDIUM: Level 3 논문 간 충돌
        - LOW: Level 4+ 논문 간 충돌

        Args:
            conflict: ConflictResult 객체

        Returns:
            ConflictSeverity
        """
        # 충돌하는 논문들 (improved vs worsened)
        conflict_papers = conflict.papers_improved + conflict.papers_worsened

        if not conflict_papers:
            return ConflictSeverity.LOW

        # 가장 높은 evidence level 점수
        max_score = max(p.evidence_score for p in conflict_papers)

        # 심각도 결정
        if max_score >= 9:  # Level 1a or 1b (Meta-analysis or RCT)
            return ConflictSeverity.CRITICAL
        elif max_score >= 7:  # Level 2a or 2b (Cohort)
            return ConflictSeverity.HIGH
        elif max_score >= 5:  # Level 3 (Case-control)
            return ConflictSeverity.MEDIUM
        else:  # Level 4+ (Case series, Expert opinion)
            return ConflictSeverity.LOW

    def _calculate_confidence(
        self,
        conflict: ConflictResult
    ) -> float:
        """충돌 신뢰도 계산.

        신뢰도 요인:
        1. 논문 수 (많을수록 신뢰도 높음)
        2. Evidence level (높을수록 신뢰도 높음)
        3. 통계적 유의성 (significant 논문 비율)
        4. 균형도 (improved vs worsened 비율이 비슷할수록 높음)

        Args:
            conflict: ConflictResult 객체

        Returns:
            신뢰도 (0.0-1.0)
        """
        if conflict.total_papers == 0:
            return 0.0

        # 1. 논문 수 점수 (2편=0.5, 5편=0.8, 10편+=1.0)
        paper_score = min(1.0, conflict.total_papers / 10.0)

        # 2. Evidence level 점수 (평균 evidence score / 10)
        all_papers = conflict.papers_improved + conflict.papers_worsened
        avg_evidence_score = sum(p.evidence_score for p in all_papers) / len(all_papers)
        evidence_score = avg_evidence_score / 10.0

        # 3. 통계적 유의성 점수
        significant_count = sum(1 for p in all_papers if p.is_significant)
        significance_score = significant_count / len(all_papers) if all_papers else 0.0

        # 4. 균형도 점수 (0.5에 가까울수록 1.0)
        balance_ratio = min(
            len(conflict.papers_improved),
            len(conflict.papers_worsened)
        ) / len(all_papers)
        balance_score = 1.0 - abs(0.5 - balance_ratio) * 2

        # 가중 평균
        confidence = (
            paper_score * 0.2 +
            evidence_score * 0.4 +
            significance_score * 0.3 +
            balance_score * 0.1
        )

        return round(confidence, 2)

    def _generate_summary(
        self,
        conflict: ConflictResult
    ) -> str:
        """충돌 요약 텍스트 생성.

        Args:
            conflict: ConflictResult 객체

        Returns:
            사람이 읽을 수 있는 요약
        """
        # 기본 정보
        summary_lines = [
            f"Conflict detected for {conflict.intervention} → {conflict.outcome}",
            f"Severity: {conflict.severity.label.upper()} (confidence: {conflict.confidence:.0%})",
            "",
        ]

        # Improved 논문 요약
        if conflict.papers_improved:
            summary_lines.append(
                f"Papers reporting IMPROVEMENT ({len(conflict.papers_improved)}):"
            )
            for paper in sorted(
                conflict.papers_improved,
                key=lambda p: p.evidence_score,
                reverse=True
            )[:3]:  # 상위 3개만
                sig_marker = "✓" if paper.is_significant else " "
                p_str = f"p={paper.p_value:.3f}" if paper.p_value is not None else "p=N/A"
                summary_lines.append(
                    f"  [{sig_marker}] {paper.paper_id} (Level {paper.evidence_level}, {p_str})"
                )
            if len(conflict.papers_improved) > 3:
                summary_lines.append(f"  ... and {len(conflict.papers_improved) - 3} more")
            summary_lines.append("")

        # Worsened 논문 요약
        if conflict.papers_worsened:
            summary_lines.append(
                f"Papers reporting WORSENING ({len(conflict.papers_worsened)}):"
            )
            for paper in sorted(
                conflict.papers_worsened,
                key=lambda p: p.evidence_score,
                reverse=True
            )[:3]:
                sig_marker = "✓" if paper.is_significant else " "
                p_str = f"p={paper.p_value:.3f}" if paper.p_value is not None else "p=N/A"
                summary_lines.append(
                    f"  [{sig_marker}] {paper.paper_id} (Level {paper.evidence_level}, {p_str})"
                )
            if len(conflict.papers_worsened) > 3:
                summary_lines.append(f"  ... and {len(conflict.papers_worsened) - 3} more")
            summary_lines.append("")

        # Unchanged 논문 (있는 경우)
        if conflict.papers_unchanged:
            summary_lines.append(
                f"Papers reporting NO CHANGE ({len(conflict.papers_unchanged)})"
            )
            summary_lines.append("")

        # 해석 가이드
        summary_lines.append("Interpretation:")

        if conflict.severity == ConflictSeverity.CRITICAL:
            summary_lines.append(
                "  ⚠️ High-quality evidence (RCT/Meta-analysis) shows conflicting results."
            )
            summary_lines.append(
                "  Systematic review or additional studies may be needed."
            )
        elif conflict.severity == ConflictSeverity.HIGH:
            summary_lines.append(
                "  ⚠️ Moderate-quality evidence shows conflicting results."
            )
            summary_lines.append(
                "  Consider patient characteristics and study context."
            )
        elif conflict.severity == ConflictSeverity.MEDIUM:
            summary_lines.append(
                "  ⚡ Case-control studies show conflicting results."
            )
            summary_lines.append(
                "  Higher-quality studies needed for definitive conclusion."
            )
        else:
            summary_lines.append(
                "  ℹ️ Low-quality evidence shows conflicting results."
            )
            summary_lines.append(
                "  Interpret with caution due to study design limitations."
            )

        return "\n".join(summary_lines)

    def _compare_severity(
        self,
        severity: ConflictSeverity,
        min_severity: ConflictSeverity
    ) -> bool:
        """심각도 비교 (severity >= min_severity).

        IntEnum 사용으로 직접 비교 가능.

        Args:
            severity: 비교할 심각도
            min_severity: 최소 심각도

        Returns:
            severity >= min_severity이면 True
        """
        return severity >= min_severity

    def _severity_sort_key(self, severity: ConflictSeverity) -> int:
        """심각도 정렬 키 (높을수록 심각).

        IntEnum 사용으로 값 자체가 정렬 키.

        Args:
            severity: ConflictSeverity

        Returns:
            정렬 키 (IntEnum 값)
        """
        return int(severity)


# ============================================================================
# Example Usage
# ============================================================================

async def example_usage():
    """사용 예시."""
    try:
        from graph.neo4j_client import Neo4jClient
    except ImportError:
        from src.graph.neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # 예시 1: 특정 Intervention-Outcome 충돌 검사
        print("=" * 80)
        print("Example 1: Detect conflicts for TLIF → Fusion Rate")
        print("=" * 80)

        conflict = await detector.detect_conflicts("TLIF", "Fusion Rate")

        if conflict:
            print(f"\n{conflict.summary}")
            print(f"\nConflict ratio: {conflict.conflict_ratio:.0%}")
            print(f"Total papers: {conflict.total_papers}")
            print(f"Highest evidence: Level {conflict.get_highest_evidence_level()}")
        else:
            print("No significant conflict detected.")

        # 예시 2: 모든 충돌 검색 (HIGH 이상만)
        print("\n" + "=" * 80)
        print("Example 2: Find all HIGH+ severity conflicts")
        print("=" * 80)

        all_conflicts = await detector.find_all_conflicts(
            min_severity=ConflictSeverity.HIGH
        )

        print(f"\nFound {len(all_conflicts)} high-severity conflicts:\n")

        for i, conflict in enumerate(all_conflicts[:5], 1):  # 상위 5개만
            print(f"{i}. {conflict.intervention} → {conflict.outcome}")
            print(f"   Severity: {conflict.severity.label.upper()}")
            print(f"   Papers: {len(conflict.papers_improved)} improved, "
                  f"{len(conflict.papers_worsened)} worsened")
            print(f"   Confidence: {conflict.confidence:.0%}")
            print()

        # 예시 3: 충돌 상세 분석
        if all_conflicts:
            print("=" * 80)
            print("Example 3: Detailed analysis of highest-severity conflict")
            print("=" * 80)

            top_conflict = all_conflicts[0]
            print(f"\n{top_conflict.summary}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
