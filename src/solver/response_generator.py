"""Response Generator for Medical KAG System.

검색 및 추론 결과를 자연스러운 응답으로 구성하는 모듈.
인용, 근거 수준, 상충 결과를 포함한 구조화된 응답 생성.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class ResponseFormat(Enum):
    """응답 형식."""
    PLAIN = "plain"       # 일반 텍스트
    MARKDOWN = "markdown"  # 마크다운
    JSON = "json"         # 구조화된 JSON
    HTML = "html"         # HTML


@dataclass
class Citation:
    """인용 정보."""
    citation_id: str
    source_title: str
    authors: list[str] = field(default_factory=list)
    publication_year: int = 0
    journal: str = ""
    doi: str = ""
    evidence_level: str = ""
    source_type: str = ""  # original, citation, background


@dataclass
class EvidenceItem:
    """근거 항목."""
    content: str
    citation: Citation
    relevance_score: float
    section: str = ""


@dataclass
class ConflictSummary:
    """상충 결과 요약."""
    topic: str
    description: str
    positive_findings: list[str]
    negative_findings: list[str]
    possible_reasons: list[str]
    recommendation: str


@dataclass
class FormattedResponse:
    """포맷된 응답."""
    summary: str
    evidence_by_level: dict[str, list[EvidenceItem]]
    conflicts: Optional[ConflictSummary]
    citations: list[Citation]
    markdown: str
    plain_text: str
    confidence: float
    total_evidence: int


@dataclass
class GeneratorInput:
    """Response Generator 입력."""
    query: str
    ranked_results: list[Any]  # RankedResult 또는 SearchResult
    reasoning: Optional[Any] = None  # ReasoningResult
    conflicts: Optional[Any] = None  # ConflictAnalysis
    format: ResponseFormat = ResponseFormat.MARKDOWN
    max_citations: int = 10
    include_all_evidence: bool = False


class ResponseGenerator:
    """Response Generator.

    검색 결과를 자연스러운 응답으로 구성합니다.

    주요 기능:
    - 모든 정보에 인용 추가 (원본 출처만)
    - 상충 결과 표시
    - 근거 수준별 정리
    - 다양한 출력 형식 지원
    """

    # Evidence level descriptions
    EVIDENCE_LEVEL_DESC = {
        "1a": "Systematic review of RCTs",
        "1b": "Individual RCT",
        "1c": "All or none study",
        "2a": "Systematic review of cohort studies",
        "2b": "Individual cohort study",
        "2c": "Outcomes research",
        "3a": "Systematic review of case-control studies",
        "3b": "Individual case-control study",
        "4": "Case series",
        "5": "Expert opinion"
    }

    # Evidence level groups
    EVIDENCE_GROUPS = {
        "High Quality (Level 1)": ["1a", "1b", "1c"],
        "Moderate Quality (Level 2)": ["2a", "2b", "2c"],
        "Low Quality (Level 3-4)": ["3a", "3b", "4"],
        "Expert Opinion (Level 5)": ["5"]
    }

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}

        # 설정값
        self.prefer_original = self.config.get("prefer_original", True)
        self.show_evidence_level = self.config.get("show_evidence_level", True)
        self.show_source_type = self.config.get("show_source_type", True)

    def generate(
        self,
        input_data: GeneratorInput | str,
        ranked_results: Optional[list[Any]] = None,
        **kwargs
    ) -> FormattedResponse:
        """응답 생성.

        Args:
            input_data: GeneratorInput 또는 쿼리 문자열
            ranked_results: 랭킹된 결과 (문자열 입력시 필수)
            **kwargs: 추가 옵션

        Returns:
            FormattedResponse: 포맷된 응답
        """
        # 입력 정규화
        if isinstance(input_data, str):
            input_obj = GeneratorInput(
                query=input_data,
                ranked_results=ranked_results or [],
                reasoning=kwargs.get("reasoning"),
                conflicts=kwargs.get("conflicts"),
                format=kwargs.get("format", ResponseFormat.MARKDOWN),
                max_citations=kwargs.get("max_citations", 10)
            )
        else:
            input_obj = input_data

        # 결과 없음
        if not input_obj.ranked_results:
            return self._create_empty_response(input_obj.query)

        # 1. 인용 정보 추출
        citations = self._extract_citations(
            input_obj.ranked_results,
            input_obj.max_citations
        )

        # 2. 근거 수준별 분류
        evidence_by_level = self._categorize_by_evidence_level(
            input_obj.ranked_results
        )

        # 3. 요약 생성
        summary = self._generate_summary(
            input_obj.query,
            input_obj.ranked_results,
            input_obj.reasoning
        )

        # 4. 상충 결과 처리
        conflict_summary = None
        if input_obj.conflicts:
            conflict_summary = self._format_conflicts(input_obj.conflicts)

        # 5. 신뢰도 계산
        confidence = self._calculate_response_confidence(
            input_obj.ranked_results,
            input_obj.reasoning
        )

        # 6. 마크다운 생성
        markdown = self._generate_markdown(
            query=input_obj.query,
            summary=summary,
            evidence_by_level=evidence_by_level,
            conflicts=conflict_summary,
            citations=citations,
            confidence=confidence
        )

        # 7. 일반 텍스트 생성
        plain_text = self._generate_plain_text(
            summary=summary,
            evidence_by_level=evidence_by_level,
            conflicts=conflict_summary,
            citations=citations
        )

        return FormattedResponse(
            summary=summary,
            evidence_by_level=evidence_by_level,
            conflicts=conflict_summary,
            citations=citations,
            markdown=markdown,
            plain_text=plain_text,
            confidence=confidence,
            total_evidence=len(input_obj.ranked_results)
        )

    def _extract_citations(
        self,
        results: list[Any],
        max_citations: int
    ) -> list[Citation]:
        """인용 정보 추출.

        Args:
            results: 검색 결과
            max_citations: 최대 인용 수

        Returns:
            Citation 목록
        """
        citations = []
        seen_ids = set()

        for i, result in enumerate(results):
            if len(citations) >= max_citations:
                break

            # 결과에서 정보 추출
            if hasattr(result, 'result'):
                # RankedResult
                source = result.result
            else:
                source = result

            # 문서 ID 추출
            doc_id = self._get_attr(source, ['document_id', 'source_id', 'id'], f"doc_{i}")

            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            # 원본 출처 우선
            source_type = self._get_attr(source, ['source_type'], 'background')
            if self.prefer_original and source_type != "original":
                continue

            citation = Citation(
                citation_id=f"[{len(citations) + 1}]",
                source_title=self._get_attr(source, ['title', 'source_title'], 'Unknown'),
                authors=self._get_attr(source, ['authors'], []),
                publication_year=self._get_attr(source, ['publication_year', 'year'], 0),
                journal=self._get_attr(source, ['journal'], ''),
                doi=self._get_attr(source, ['doi'], ''),
                evidence_level=self._get_attr(source, ['evidence_level'], '5'),
                source_type=source_type
            )
            citations.append(citation)

        # 원본이 부족하면 다른 출처 포함
        if len(citations) < max_citations and self.prefer_original:
            for i, result in enumerate(results):
                if len(citations) >= max_citations:
                    break

                if hasattr(result, 'result'):
                    source = result.result
                else:
                    source = result

                doc_id = self._get_attr(source, ['document_id', 'source_id', 'id'], f"doc_{i}")
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)

                citation = Citation(
                    citation_id=f"[{len(citations) + 1}]",
                    source_title=self._get_attr(source, ['title', 'source_title'], 'Unknown'),
                    authors=self._get_attr(source, ['authors'], []),
                    publication_year=self._get_attr(source, ['publication_year', 'year'], 0),
                    journal=self._get_attr(source, ['journal'], ''),
                    doi=self._get_attr(source, ['doi'], ''),
                    evidence_level=self._get_attr(source, ['evidence_level'], '5'),
                    source_type=self._get_attr(source, ['source_type'], 'background')
                )
                citations.append(citation)

        return citations

    def _categorize_by_evidence_level(
        self,
        results: list[Any]
    ) -> dict[str, list[EvidenceItem]]:
        """근거 수준별 분류.

        Args:
            results: 검색 결과

        Returns:
            근거 수준별 EvidenceItem 딕셔너리
        """
        categorized: dict[str, list[EvidenceItem]] = {}

        for group_name in self.EVIDENCE_GROUPS:
            categorized[group_name] = []

        for i, result in enumerate(results):
            # 정보 추출
            if hasattr(result, 'result'):
                source = result.result
                score = getattr(result, 'final_score', 0.5)
            else:
                source = result
                score = self._get_attr(source, ['score'], 0.5)

            content = self._get_attr(source, ['text', 'content'], '')
            evidence_level = self._get_attr(source, ['evidence_level'], '5')
            section = self._get_attr(source, ['section'], '')

            # Citation 생성
            citation = Citation(
                citation_id=f"[{i + 1}]",
                source_title=self._get_attr(source, ['title', 'source_title'], 'Unknown'),
                publication_year=self._get_attr(source, ['publication_year', 'year'], 0),
                evidence_level=evidence_level,
                source_type=self._get_attr(source, ['source_type'], 'background')
            )

            evidence_item = EvidenceItem(
                content=content[:500] if len(content) > 500 else content,
                citation=citation,
                relevance_score=score,
                section=section
            )

            # 그룹에 추가
            for group_name, levels in self.EVIDENCE_GROUPS.items():
                if evidence_level in levels:
                    categorized[group_name].append(evidence_item)
                    break
            else:
                # 매칭 안되면 마지막 그룹에 추가
                categorized["Expert Opinion (Level 5)"].append(evidence_item)

        return categorized

    def _generate_summary(
        self,
        query: str,
        results: list[Any],
        reasoning: Optional[Any]
    ) -> str:
        """요약 생성.

        Args:
            query: 질의
            results: 검색 결과
            reasoning: 추론 결과

        Returns:
            요약 문자열
        """
        # 추론 결과가 있으면 사용
        if reasoning and hasattr(reasoning, 'answer'):
            return reasoning.answer

        # 최상위 결과에서 요약 생성
        if not results:
            return "No relevant evidence found."

        top_result = results[0]
        if hasattr(top_result, 'result'):
            source = top_result.result
        else:
            source = top_result

        content = self._get_attr(source, ['text', 'content'], '')
        evidence_level = self._get_attr(source, ['evidence_level'], '5')
        level_desc = self.EVIDENCE_LEVEL_DESC.get(evidence_level, "")

        summary = f"Based on {len(results)} evidence sources"
        if level_desc:
            summary += f" (best evidence: {level_desc})"
        summary += f": {content[:300]}..."

        return summary

    def _format_conflicts(self, conflicts: Any) -> Optional[ConflictSummary]:
        """상충 결과 포맷팅.

        Args:
            conflicts: ConflictAnalysis 객체

        Returns:
            ConflictSummary 또는 None
        """
        if not conflicts:
            return None

        # ConflictAnalysis 객체 처리
        if hasattr(conflicts, 'topic'):
            return ConflictSummary(
                topic=getattr(conflicts, 'topic', ''),
                description=getattr(conflicts, 'description', ''),
                positive_findings=getattr(conflicts, 'positive_findings', []),
                negative_findings=getattr(conflicts, 'negative_findings', []),
                possible_reasons=getattr(conflicts, 'possible_reasons', []),
                recommendation=getattr(conflicts, 'recommendation', '')
            )

        # dict 처리
        if isinstance(conflicts, dict):
            return ConflictSummary(
                topic=conflicts.get('topic', ''),
                description=conflicts.get('description', ''),
                positive_findings=conflicts.get('positive_findings', []),
                negative_findings=conflicts.get('negative_findings', []),
                possible_reasons=conflicts.get('possible_reasons', []),
                recommendation=conflicts.get('recommendation', '')
            )

        return None

    def _calculate_response_confidence(
        self,
        results: list[Any],
        reasoning: Optional[Any]
    ) -> float:
        """응답 신뢰도 계산.

        Args:
            results: 검색 결과
            reasoning: 추론 결과

        Returns:
            0.0-1.0 신뢰도
        """
        if reasoning and hasattr(reasoning, 'confidence'):
            return reasoning.confidence

        if not results:
            return 0.0

        # 결과 품질 기반 계산
        scores = []
        for result in results[:5]:  # 상위 5개
            if hasattr(result, 'final_score'):
                scores.append(result.final_score)
            elif hasattr(result, 'score'):
                scores.append(result.score)
            else:
                score = self._get_attr(result, ['score'], 0.5)
                scores.append(score)

        return sum(scores) / len(scores) if scores else 0.0

    def _generate_markdown(
        self,
        query: str,
        summary: str,
        evidence_by_level: dict[str, list[EvidenceItem]],
        conflicts: Optional[ConflictSummary],
        citations: list[Citation],
        confidence: float
    ) -> str:
        """마크다운 생성.

        Args:
            query: 질의
            summary: 요약
            evidence_by_level: 근거 수준별 분류
            conflicts: 상충 요약
            citations: 인용 목록
            confidence: 신뢰도

        Returns:
            마크다운 문자열
        """
        lines = []

        # 제목
        lines.append(f"# Response to: {query}")
        lines.append("")

        # 요약
        lines.append("## Summary")
        lines.append(f"_{summary}_")
        lines.append("")
        lines.append(f"**Confidence**: {confidence:.1%}")
        lines.append("")

        # 상충 결과 (있으면)
        if conflicts:
            lines.append("## ⚠️ Conflicting Evidence")
            lines.append(f"**Topic**: {conflicts.topic}")
            lines.append("")
            lines.append(f"{conflicts.description}")
            lines.append("")

            if conflicts.positive_findings:
                lines.append("**Supporting findings:**")
                for finding in conflicts.positive_findings:
                    lines.append(f"- ✅ {finding}")
                lines.append("")

            if conflicts.negative_findings:
                lines.append("**Opposing findings:**")
                for finding in conflicts.negative_findings:
                    lines.append(f"- ❌ {finding}")
                lines.append("")

            if conflicts.recommendation:
                lines.append(f"**Recommendation**: {conflicts.recommendation}")
                lines.append("")

        # 근거 수준별
        lines.append("## Evidence by Quality Level")
        lines.append("")

        for level_name, items in evidence_by_level.items():
            if not items:
                continue

            lines.append(f"### {level_name}")
            lines.append("")

            for item in items[:3]:  # 각 레벨 최대 3개
                citation_str = item.citation.citation_id
                if self.show_evidence_level:
                    citation_str += f" (Level {item.citation.evidence_level})"
                if self.show_source_type and item.citation.source_type:
                    citation_str += f" [{item.citation.source_type}]"

                lines.append(f"- {item.content[:200]}... {citation_str}")
            lines.append("")

        # 참고문헌
        if citations:
            lines.append("## References")
            lines.append("")

            for citation in citations:
                ref_line = f"{citation.citation_id} "

                if citation.authors:
                    authors_str = ", ".join(citation.authors[:3])
                    if len(citation.authors) > 3:
                        authors_str += " et al."
                    ref_line += f"{authors_str}. "

                ref_line += f"**{citation.source_title}**"

                if citation.publication_year:
                    ref_line += f" ({citation.publication_year})"

                if citation.journal:
                    ref_line += f". _{citation.journal}_"

                if citation.evidence_level:
                    ref_line += f" [Level {citation.evidence_level}]"

                lines.append(ref_line)

            lines.append("")

        return "\n".join(lines)

    def _generate_plain_text(
        self,
        summary: str,
        evidence_by_level: dict[str, list[EvidenceItem]],
        conflicts: Optional[ConflictSummary],
        citations: list[Citation]
    ) -> str:
        """일반 텍스트 생성.

        Args:
            summary: 요약
            evidence_by_level: 근거 수준별 분류
            conflicts: 상충 요약
            citations: 인용 목록

        Returns:
            일반 텍스트 문자열
        """
        lines = []

        # 요약
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(summary)
        lines.append("")

        # 상충 (있으면)
        if conflicts:
            lines.append("CONFLICTING EVIDENCE")
            lines.append("-" * 40)
            lines.append(f"Topic: {conflicts.topic}")
            lines.append(conflicts.description)
            lines.append("")

        # 근거
        lines.append("EVIDENCE")
        lines.append("-" * 40)

        for level_name, items in evidence_by_level.items():
            if not items:
                continue

            lines.append(f"\n{level_name}:")
            for item in items[:3]:
                lines.append(f"  - {item.content[:150]}... {item.citation.citation_id}")

        lines.append("")

        # 참고문헌
        if citations:
            lines.append("REFERENCES")
            lines.append("-" * 40)

            for citation in citations:
                lines.append(
                    f"{citation.citation_id} {citation.source_title} "
                    f"({citation.publication_year}) "
                    f"[Level {citation.evidence_level}]"
                )

        return "\n".join(lines)

    def _get_attr(self, obj: Any, attrs: list[str], default: Any = None) -> Any:
        """객체에서 속성 추출.

        Args:
            obj: 대상 객체
            attrs: 속성명 목록 (우선순위)
            default: 기본값

        Returns:
            속성값 또는 기본값
        """
        for attr in attrs:
            # dict
            if isinstance(obj, dict):
                if attr in obj:
                    return obj[attr]
            # object
            elif hasattr(obj, attr):
                return getattr(obj, attr)
            # nested (chunk)
            elif hasattr(obj, 'chunk'):
                chunk = obj.chunk
                if hasattr(chunk, attr):
                    return getattr(chunk, attr)

        return default

    def _create_empty_response(self, query: str) -> FormattedResponse:
        """빈 응답 생성."""
        return FormattedResponse(
            summary="No relevant evidence found for this query.",
            evidence_by_level={},
            conflicts=None,
            citations=[],
            markdown=f"# Response to: {query}\n\nNo relevant evidence found.",
            plain_text="No relevant evidence found.",
            confidence=0.0,
            total_evidence=0
        )


def format_citation_apa(citation: Citation) -> str:
    """APA 형식 인용 생성.

    Args:
        citation: Citation 객체

    Returns:
        APA 형식 문자열
    """
    parts = []

    # Authors
    if citation.authors:
        if len(citation.authors) == 1:
            parts.append(citation.authors[0])
        elif len(citation.authors) == 2:
            parts.append(f"{citation.authors[0]} & {citation.authors[1]}")
        else:
            parts.append(f"{citation.authors[0]} et al.")

    # Year
    if citation.publication_year:
        parts.append(f"({citation.publication_year})")

    # Title
    parts.append(citation.source_title)

    # Journal
    if citation.journal:
        parts.append(f"_{citation.journal}_")

    # DOI
    if citation.doi:
        parts.append(f"https://doi.org/{citation.doi}")

    return ". ".join(parts)


def format_citation_vancouver(citation: Citation, number: int) -> str:
    """Vancouver 형식 인용 생성.

    Args:
        citation: Citation 객체
        number: 인용 번호

    Returns:
        Vancouver 형식 문자열
    """
    parts = [f"{number}."]

    # Authors
    if citation.authors:
        authors_str = ", ".join(citation.authors[:6])
        if len(citation.authors) > 6:
            authors_str += ", et al"
        parts.append(authors_str + ".")

    # Title
    parts.append(citation.source_title + ".")

    # Journal and year
    if citation.journal:
        journal_part = citation.journal
        if citation.publication_year:
            journal_part += f" {citation.publication_year}"
        parts.append(journal_part + ".")

    return " ".join(parts)
