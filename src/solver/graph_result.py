"""Graph Search Result Data Structures.

Graph 검색 결과를 표현하는 데이터 구조 정의.
Neo4j에서 추출된 근거(Evidence)와 논문 정보 포함.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GraphEvidence:
    """Graph에서 추출된 근거.

    Intervention → Outcome 관계의 통계적 근거를 표현.
    Neo4j AFFECTS 관계에서 추출됨.

    Attributes:
        intervention: 수술법/치료법 이름 (정규화된 형태)
        outcome: 결과 변수 이름 (VAS, ODI, Fusion Rate 등)
        value: 측정값 (예: "85.2%", "2.3 points")
        value_control: 대조군 값 (비교 연구인 경우)
        p_value: 통계적 유의성 (0~1)
        effect_size: 효과 크기 (예: "Cohen's d=0.8")
        confidence_interval: 신뢰 구간 (예: "95% CI: 0.5-0.9")
        is_significant: 통계적으로 유의한지 (p < 0.05)
        direction: 효과 방향 (improved, worsened, unchanged)
        source_paper_id: 출처 논문 ID
        evidence_level: 연구 근거 수준 (1a, 1b, 2a, 2b, 3, 4, 5)
    """
    intervention: str
    outcome: str
    value: str
    source_paper_id: str
    evidence_level: str = "5"

    # 통계 정보
    p_value: Optional[float] = None
    effect_size: str = ""
    confidence_interval: str = ""
    is_significant: bool = False

    # 방향성
    direction: str = ""  # improved, worsened, unchanged

    # 비교 연구
    value_control: str = ""

    def get_display_text(self) -> str:
        """화면 표시용 텍스트 생성.

        Returns:
            근거를 읽기 쉬운 형태로 변환한 문자열

        Example:
            "TLIF improved Fusion Rate to 92% (p=0.001)"
        """
        parts = [f"{self.intervention} {self.direction} {self.outcome}"]

        if self.value:
            parts.append(f"to {self.value}")

        if self.value_control:
            parts.append(f"vs {self.value_control}")

        if self.p_value is not None:
            parts.append(f"(p={self.p_value:.3f})")
        elif self.is_significant:
            parts.append("(p<0.05)")

        return " ".join(parts)


@dataclass
class PaperNode:
    """논문 노드 정보.

    Neo4j Paper 노드에서 추출된 메타데이터.

    Attributes:
        paper_id: 논문 고유 ID
        title: 논문 제목
        authors: 저자 목록
        year: 출판 연도
        journal: 저널명
        doi: DOI
        pmid: PubMed ID
        sub_domain: 척추 하위 도메인 (Degenerative, Deformity, Trauma, Tumor)
        study_design: 연구 설계 (RCT, Retrospective, Meta-analysis 등)
        evidence_level: 근거 수준 (1a~5)
        sample_size: 표본 크기
        follow_up_months: 추적 기간(개월)
    """
    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    journal: str = ""
    doi: str = ""
    pmid: str = ""
    sub_domain: str = ""
    study_design: str = ""
    evidence_level: str = "5"
    sample_size: int = 0
    follow_up_months: int = 0

    def get_citation(self) -> str:
        """인용 형식 생성.

        Returns:
            APA 스타일 인용 문자열

        Example:
            "Kim et al. (2024). Title. Journal."
        """
        if not self.authors:
            author_str = "Unknown"
        elif len(self.authors) == 1:
            author_str = self.authors[0]
        else:
            # 첫 저자 + et al.
            first_author = self.authors[0].split()[-1]  # Last name
            author_str = f"{first_author} et al."

        return f"{author_str} ({self.year}). {self.title}. {self.journal}."


@dataclass
class InterventionHierarchy:
    """수술법 계층 정보.

    Intervention 노드의 IS_A 관계를 통해 구축된 계층 구조.

    Attributes:
        intervention: 현재 수술법
        parent: 상위 카테고리 (없으면 None)
        children: 하위 수술법 목록
        level: 계층 깊이 (0=최상위)
        category: 분류 (fusion, decompression, fixation 등)
        aliases: 동의어 목록
    """
    intervention: str
    level: int = 0
    parent: Optional[str] = None
    children: list[str] = field(default_factory=list)
    category: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class GraphSearchResult:
    """Graph 검색 결과.

    Neo4j Cypher 쿼리의 전체 결과를 포함하는 컨테이너.

    Attributes:
        evidences: 추출된 근거 목록
        paper_nodes: 관련 논문 노드 목록
        intervention_hierarchy: 수술법 계층 정보 (선택적)
        query_type: 쿼리 유형 (evidence_search, intervention_hierarchy 등)
    """
    evidences: list[GraphEvidence] = field(default_factory=list)
    paper_nodes: list[PaperNode] = field(default_factory=list)
    intervention_hierarchy: dict[str, InterventionHierarchy] = field(default_factory=dict)
    query_type: str = "evidence_search"

    def get_unique_papers(self) -> list[str]:
        """고유한 논문 ID 목록 반환.

        Returns:
            중복 제거된 논문 ID 리스트
        """
        return list({e.source_paper_id for e in self.evidences})

    def filter_by_significance(self, min_p_value: float = 0.05) -> "GraphSearchResult":
        """통계적으로 유의한 근거만 필터링.

        Args:
            min_p_value: p-value 임계값 (기본값: 0.05)

        Returns:
            필터링된 새 GraphSearchResult 객체
        """
        filtered_evidences = [
            e for e in self.evidences
            if e.is_significant or (e.p_value is not None and e.p_value < min_p_value)
        ]

        return GraphSearchResult(
            evidences=filtered_evidences,
            paper_nodes=self.paper_nodes,
            intervention_hierarchy=self.intervention_hierarchy,
            query_type=self.query_type
        )

    def group_by_outcome(self) -> dict[str, list[GraphEvidence]]:
        """Outcome별로 근거 그룹화.

        Returns:
            {outcome_name: [GraphEvidence, ...]} 형태의 딕셔너리
        """
        groups: dict[str, list[GraphEvidence]] = {}
        for evidence in self.evidences:
            outcome = evidence.outcome
            if outcome not in groups:
                groups[outcome] = []
            groups[outcome].append(evidence)
        return groups

    def get_summary(self) -> str:
        """검색 결과 요약.

        Returns:
            통계 요약 문자열
        """
        total = len(self.evidences)
        significant = sum(1 for e in self.evidences if e.is_significant)
        papers = len(self.get_unique_papers())

        return (
            f"Found {total} evidences from {papers} papers. "
            f"{significant} statistically significant."
        )
