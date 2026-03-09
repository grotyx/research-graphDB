"""Citation Handler for Medical KAG Server.

This module handles all citation-related operations including:
- Draft generation with automatic citations
- Citation usage suggestions
- Section-specific citation guides
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute
from medical_mcp.handlers.utils import get_abstract_from_sections, determine_tier

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 10000


class CitationHandler(BaseHandler):
    """Handles citation generation and management operations."""

    def __init__(self, server: "MedicalKAGServer"):
        """Initialize Citation handler.

        Args:
            server: Parent MedicalKAGServer instance for accessing clients
        """
        super().__init__(server)

    @safe_execute
    async def draft_with_citations(
        self,
        topic: str,
        section_type: str = "introduction",
        max_citations: int = 5,
        language: str = "korean"
    ) -> dict:
        """주제에 대해 자동으로 관련 논문을 검색하고 인용 가능한 형태로 반환.

        논문 작성 시 자동으로 DB에서 근거를 찾아 인용문과 함께 제공합니다.

        Args:
            topic: 작성할 주제 (예: "당뇨병에서 메트포르민의 효과")
            section_type: 섹션 유형 (introduction, methods, results, discussion, conclusion)
            max_citations: 최대 인용 수
            language: 출력 언어 (korean, english)

        Returns:
            인용 가능한 근거와 참고문헌 목록
        """
        if topic and len(topic) > MAX_QUERY_LENGTH:
            return {"error": f"Query too long ({len(topic)} chars). Maximum: {MAX_QUERY_LENGTH} chars."}

        # 1. 관련 논문 검색
        search_result = await self.server.search(
            query=topic,
            top_k=max_citations * 2,  # 여유있게 검색
            tier_strategy="tier1_first",
            prefer_original=True
        )

        if not search_result.get("success"):
            return {"success": False, "error": "검색 실패"}

        results = search_result.get("results", [])
        if not results:
            return {
                "success": True,
                "topic": topic,
                "message": "관련 논문을 찾지 못했습니다. 더 많은 PDF를 추가해주세요.",
                "citations": [],
                "references": []
            }

        # 2. 인용 정보 구성
        citations = []
        references = []
        seen_docs = set()

        for i, result in enumerate(results):
            if len(citations) >= max_citations:
                break

            doc_id = result.get("document_id", "")
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)

            # 메타데이터에서 저자/연도 추출 (v1.14.27: None 값 처리)
            metadata = result.get("metadata") or {}
            authors = metadata.get("authors") or ["Unknown"]
            year = metadata.get("year", "n.d.")
            title = metadata.get("title", doc_id)

            # 첫 번째 저자 성 추출
            first_author = authors[0].split()[-1] if authors else "Unknown"
            et_al = " et al." if len(authors) > 1 else ""

            # 인용 키 생성
            citation_key = f"{first_author}{et_al}, {year}"

            # 관련 내용
            content = result.get("content", "")
            section = result.get("section", "")
            evidence_level = result.get("evidence_level", "")

            citation_entry = {
                "citation_key": citation_key,
                "citation_number": i + 1,
                "content_summary": content[:500] + "..." if len(content) > 500 else content,
                "section_type": section,
                "evidence_level": evidence_level,
                "relevance_score": result.get("score", 0),
                "usage_suggestion": self._suggest_citation_usage(section_type, section, content, language)
            }
            citations.append(citation_entry)

            # 참고문헌 항목
            ref_entry = {
                "number": i + 1,
                "authors": authors,
                "year": year,
                "title": title,
                "citation_key": citation_key,
                "document_id": doc_id
            }
            references.append(ref_entry)

        # 3. 결과 구성
        if language == "korean":
            intro_text = f"'{topic}'에 대해 {len(citations)}개의 관련 논문을 찾았습니다."
        else:
            intro_text = f"Found {len(citations)} relevant papers for '{topic}'."

        return {
            "success": True,
            "topic": topic,
            "section_type": section_type,
            "message": intro_text,
            "citations": citations,
            "references": references,
            "usage_guide": self._get_citation_guide(section_type, language)
        }

    def _suggest_citation_usage(
        self,
        target_section: str,
        source_section: str,
        content: str,
        language: str
    ) -> str:
        """인용 사용 제안 생성."""
        suggestions = {
            "korean": {
                "introduction": {
                    "abstract": "배경 설명에 활용: '선행 연구에 따르면...'",
                    "results": "연구 필요성 근거로 활용: '기존 연구에서 ...가 보고되었다'",
                    "conclusion": "연구 동기 설명에 활용"
                },
                "discussion": {
                    "results": "결과 비교에 활용: '본 연구 결과는 ...와 일치한다'",
                    "abstract": "선행 연구와 비교: '...의 연구와 유사하게'",
                    "conclusion": "결론 뒷받침에 활용"
                },
                "results": {
                    "results": "유사 결과 참조: '이는 ...의 보고와 일치한다'",
                    "methods": "방법론 참조에 활용"
                }
            },
            "english": {
                "introduction": {
                    "abstract": "Use for background: 'Previous studies have shown...'",
                    "results": "Use as rationale: 'It has been reported that...'",
                    "conclusion": "Use to establish research motivation"
                },
                "discussion": {
                    "results": "Compare results: 'Our findings are consistent with...'",
                    "abstract": "Reference prior work: 'Similar to the findings of...'",
                    "conclusion": "Support conclusions"
                },
                "results": {
                    "results": "Reference similar findings: 'This is consistent with...'",
                    "methods": "Reference methodology"
                }
            }
        }

        lang_suggestions = suggestions.get(language, suggestions["english"])
        section_suggestions = lang_suggestions.get(target_section, {})
        return section_suggestions.get(source_section,
            "관련 근거로 활용 가능" if language == "korean" else "Can be used as supporting evidence")

    def _get_citation_guide(self, section_type: str, language: str) -> str:
        """섹션별 인용 가이드 반환."""
        guides = {
            "korean": {
                "introduction": """
## Introduction 작성 가이드
- 연구 배경과 필요성을 설명할 때 인용
- "...에 따르면" 또는 "...가 보고한 바와 같이" 형식 사용
- 최신 연구부터 인용하여 현재 연구 동향 설명
""",
                "methods": """
## Methods 작성 가이드
- 방법론의 근거를 제시할 때 인용
- "...의 방법을 참고하여" 형식 사용
""",
                "results": """
## Results 작성 가이드
- 결과 해석 시 비교 대상으로 인용
- "이는 ...의 결과와 일치한다" 형식 사용
""",
                "discussion": """
## Discussion 작성 가이드
- 결과를 선행 연구와 비교할 때 적극 인용
- 일치/불일치 여부와 그 이유 설명
- "본 연구 결과는 ...와 일치하며" 형식 사용
""",
                "conclusion": """
## Conclusion 작성 가이드
- 핵심 발견의 의의를 강조할 때 인용
- 향후 연구 방향 제시 시 참조
"""
            },
            "english": {
                "introduction": "Use citations to establish background and rationale.",
                "methods": "Cite methodological references.",
                "results": "Compare findings with cited studies.",
                "discussion": "Extensively compare with prior literature.",
                "conclusion": "Reinforce significance with key references."
            }
        }

        lang_guides = guides.get(language, guides["english"])
        return lang_guides.get(section_type, "")
