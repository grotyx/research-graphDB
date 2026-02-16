"""Reference Handler for Medical KAG Server.

논문 참고문헌 포맷팅 및 스타일 관리 핸들러.
다양한 저널 스타일 지원 및 커스텀 스타일 저장.

지원 스타일:
- vancouver: 대부분의 의학 저널 (ICMJE)
- ama: JAMA 계열
- apa: APA 7th Edition
- jbjs: Bone & Joint Journal
- spine: Spine Journal
- nlm: National Library of Medicine
- harvard: Harvard style
- bibtex: BibTeX export
- ris: RIS export (EndNote/Zotero)
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List, Dict, Any

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute
from core.exceptions import ProcessingError, ErrorCode

try:
    from builder.reference_formatter import (
        ReferenceFormatter,
        PaperReference,
        StyleConfig,
        AuthorFormatConfig,
        JournalFormatConfig,
        DateFormatConfig,
    )
    FORMATTER_AVAILABLE = True
except ImportError:
    FORMATTER_AVAILABLE = False

logger = logging.getLogger(__name__)


class ReferenceHandler(BaseHandler):
    """참고문헌 포맷팅 및 스타일 관리 핸들러."""

    def __init__(self, server: "MedicalKAGServer"):
        """초기화.

        Args:
            server: MedicalKAGServer 인스턴스
        """
        super().__init__(server)
        self._formatter: Optional[ReferenceFormatter] = None

    @property
    def formatter(self) -> ReferenceFormatter:
        """ReferenceFormatter 인스턴스 (lazy loading)."""
        if self._formatter is None:
            if not FORMATTER_AVAILABLE:
                raise ProcessingError(message="ReferenceFormatter not available", error_code=ErrorCode.PROC_UNKNOWN)
            self._formatter = ReferenceFormatter()
        return self._formatter

    @safe_execute
    async def format_reference(
        self,
        paper_id: Optional[str] = None,
        query: Optional[str] = None,
        style: str = "vancouver",
        target_journal: Optional[str] = None,
        output_format: str = "text",
    ) -> Dict[str, Any]:
        """논문 참고문헌 포맷팅.

        Args:
            paper_id: 논문 ID (data/extracted/*.json의 파일명)
            query: 검색어 (paper_id가 없을 때 사용)
            style: 스타일명 (vancouver, ama, apa, jbjs, spine, nlm, harvard)
            target_journal: 대상 저널명 (저장된 스타일 자동 적용)
            output_format: 출력 형식 (text, bibtex, ris)

        Returns:
            포맷된 참고문헌 정보
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        # 1. 논문 찾기
        paper_data = None

        if paper_id:
            paper_data = await self._load_paper_by_id(paper_id)

        if not paper_data and query:
            # 검색으로 찾기
            try:
                search_result = await self.server.search(
                    query=query,
                    top_k=1,
                    prefer_original=True
                )
                if search_result and search_result.get("success") and search_result.get("results"):
                    result = search_result["results"][0]
                    paper_id = result.get("document_id", "")
                    if paper_id:
                        paper_data = await self._load_paper_by_id(paper_id)
            except Exception as search_err:
                logger.warning(f"Search failed for query '{query}': {search_err}")
                # 검색 실패해도 paper_id로 시도한 결과가 있으면 계속 진행

        if not paper_data:
            return {
                "success": False,
                "error": f"논문을 찾을 수 없습니다: {paper_id or query}"
            }

        # 2. PaperReference 생성
        metadata = paper_data.get("metadata") or {}
        paper = PaperReference.from_metadata(metadata, paper_id or "")

        # 3. 스타일 결정
        if target_journal:
            # 저널에 매핑된 스타일 사용
            mapped_style = self.formatter.get_journal_style(target_journal)
            if mapped_style:
                style = mapped_style
                logger.info(f"Using mapped style '{style}' for journal '{target_journal}'")

        # 4. 포맷팅
        if output_format == "bibtex":
            formatted = self.formatter.to_bibtex(paper)
        elif output_format == "ris":
            formatted = self.formatter.to_ris(paper)
        else:
            formatted = self.formatter.format(paper, style=style)

        return {
            "success": True,
            "paper_id": paper_id,
            "title": metadata.get("title", ""),
            "style": style,
            "target_journal": target_journal,
            "output_format": output_format,
            "formatted_reference": formatted,
            "metadata": {
                "authors": metadata.get("authors", []),
                "year": metadata.get("year"),
                "journal": metadata.get("journal", ""),
                "doi": metadata.get("doi"),
                "pmid": metadata.get("pmid"),
            }
        }

    @safe_execute
    async def format_references(
        self,
        paper_ids: Optional[List[str]] = None,
        query: Optional[str] = None,
        max_results: int = 10,
        style: str = "vancouver",
        target_journal: Optional[str] = None,
        numbered: bool = True,
        start_number: int = 1,
        output_format: str = "text",
    ) -> Dict[str, Any]:
        """여러 논문 참고문헌 포맷팅.

        Args:
            paper_ids: 논문 ID 목록
            query: 검색어 (paper_ids가 없을 때)
            max_results: 검색 시 최대 결과 수
            style: 스타일명
            target_journal: 대상 저널명
            numbered: 번호 붙이기 여부
            start_number: 시작 번호
            output_format: 출력 형식

        Returns:
            포맷된 참고문헌 목록
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        papers = []

        if paper_ids:
            # ID로 직접 로드
            for pid in paper_ids:
                paper_data = await self._load_paper_by_id(pid)
                if paper_data:
                    # v1.14.27: None 값 처리
                    metadata = paper_data.get("metadata") or {}
                    papers.append(PaperReference.from_metadata(metadata, pid))

        elif query:
            # 검색으로 찾기
            try:
                search_result = await self.server.search(
                    query=query,
                    top_k=max_results,
                    prefer_original=True
                )
                if search_result and search_result.get("success"):
                    for result in search_result.get("results", []):
                        pid = result.get("document_id", "")
                        if not pid:
                            continue
                        paper_data = await self._load_paper_by_id(pid)
                        if paper_data:
                            metadata = paper_data.get("metadata") or {}
                            papers.append(PaperReference.from_metadata(metadata, pid))
            except Exception as search_err:
                logger.warning(f"Search failed for query '{query}': {search_err}")

        if not papers:
            return {
                "success": False,
                "error": "포맷할 논문을 찾을 수 없습니다"
            }

        # 스타일 결정
        if target_journal:
            mapped_style = self.formatter.get_journal_style(target_journal)
            if mapped_style:
                style = mapped_style

        # 포맷팅
        if output_format == "bibtex":
            formatted = "\n\n".join(self.formatter.to_bibtex(p) for p in papers)
        elif output_format == "ris":
            formatted = "\n".join(self.formatter.to_ris(p) for p in papers)
        else:
            formatted = self.formatter.format_multiple(
                papers,
                style=style,
                numbered=numbered,
                start_number=start_number,
            )

        return {
            "success": True,
            "count": len(papers),
            "style": style,
            "target_journal": target_journal,
            "output_format": output_format,
            "numbered": numbered,
            "formatted_references": formatted,
            "papers": [
                {"paper_id": p.paper_id, "title": p.title, "year": p.year}
                for p in papers
            ]
        }

    @safe_execute
    async def list_styles(self) -> Dict[str, Any]:
        """사용 가능한 스타일 목록.

        Returns:
            스타일 목록 및 저널 매핑 정보
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        styles_info = self.formatter.list_styles()

        # 상세 정보 추가
        default_styles_detail = {}
        for name in styles_info["default_styles"]:
            config = self.formatter.get_style(name)
            default_styles_detail[name] = {
                "full_name": config.name,
                "author_format": config.author.format,
                "et_al_threshold": config.author.et_al_threshold,
                "include_doi": config.include_doi,
                "journal_abbreviation": config.journal.use_abbreviation,
            }

        return {
            "success": True,
            "default_styles": default_styles_detail,
            "custom_styles": styles_info["custom_styles"],
            "journal_mappings": styles_info.get("journal_mappings_detail", {}),
            "journal_count": {
                "default": styles_info.get("default_journal_count", 0),
                "user_saved": styles_info.get("user_journal_count", 0),
            },
            "usage_examples": {
                "format_single": 'format_reference(paper_id="2025_Park_BED_vs_MD_RCT", style="vancouver")',
                "format_for_journal": 'format_reference(paper_id="...", target_journal="Spine")',
                "format_multiple": 'format_references(query="lumbar fusion", style="ama", numbered=True)',
                "export_bibtex": 'format_reference(paper_id="...", output_format="bibtex")',
            }
        }

    @safe_execute
    async def set_journal_style(
        self,
        journal_name: str,
        style_name: str,
    ) -> Dict[str, Any]:
        """저널에 스타일 매핑 설정.

        특정 저널에 사용할 스타일을 저장합니다.
        이후 target_journal 파라미터로 자동 적용됩니다.

        Args:
            journal_name: 저널명 (예: "Spine", "JBJS", "The Spine Journal")
            style_name: 스타일명 (예: "vancouver", "jbjs", "spine")

        Returns:
            설정 결과
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        # 스타일 유효성 검사
        available = self.formatter.list_styles()
        all_styles = available["default_styles"] + available["custom_styles"]

        if style_name not in all_styles:
            return {
                "success": False,
                "error": f"스타일 '{style_name}'을 찾을 수 없습니다",
                "available_styles": all_styles
            }

        # 매핑 저장
        self.formatter.set_journal_style(journal_name, style_name)

        return {
            "success": True,
            "message": f"저널 '{journal_name}'에 스타일 '{style_name}' 매핑 완료",
            "journal_name": journal_name,
            "style_name": style_name,
        }

    @safe_execute
    async def add_custom_style(
        self,
        name: str,
        base_style: str = "vancouver",
        author_et_al_threshold: int = 6,
        author_et_al_min: int = 3,
        author_initials_format: str = "no_space",
        include_doi: bool = False,
        include_pmid: bool = False,
        journal_abbreviation: bool = True,
        volume_format: str = "{volume}({issue})",
        pages_format: str = "full",
    ) -> Dict[str, Any]:
        """커스텀 스타일 추가.

        기존 스타일을 기반으로 커스텀 스타일을 생성합니다.

        Args:
            name: 새 스타일 이름
            base_style: 기반 스타일
            author_et_al_threshold: et al. 사용 저자 수 기준
            author_et_al_min: et al. 사용 시 표시할 최소 저자 수
            author_initials_format: 이니셜 형식 (no_space, space, dots)
            include_doi: DOI 포함 여부
            include_pmid: PMID 포함 여부
            journal_abbreviation: 저널 약어 사용 여부
            volume_format: 볼륨 형식
            pages_format: 페이지 형식 (full, abbreviated)

        Returns:
            생성 결과
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        # 기반 스타일 가져오기
        base = self.formatter.get_style(base_style)

        # 새 설정 생성
        config = StyleConfig(
            name=name,
            base_style=base_style,
            author=AuthorFormatConfig(
                format=base.author.format,
                separator=base.author.separator,
                et_al_threshold=author_et_al_threshold,
                et_al_min=author_et_al_min,
                et_al_text=base.author.et_al_text,
                initials_format=author_initials_format,
            ),
            title_quotes=base.title_quotes,
            title_italics=base.title_italics,
            title_period=base.title_period,
            title_case=base.title_case,
            journal=JournalFormatConfig(
                use_abbreviation=journal_abbreviation,
                italicize=base.journal.italicize,
            ),
            date=base.date,
            volume_bold=base.volume_bold,
            volume_format=volume_format,
            issue_in_parens=base.issue_in_parens,
            pages_format=pages_format,
            pages_prefix=base.pages_prefix,
            include_doi=include_doi,
            doi_format=base.doi_format,
            include_pmid=include_pmid,
            pmid_format=base.pmid_format,
        )

        # 저장
        self.formatter.add_custom_style(name, config)

        return {
            "success": True,
            "message": f"커스텀 스타일 '{name}' 생성 완료",
            "style_name": name,
            "base_style": base_style,
            "config": config.to_dict(),
        }

    @safe_execute
    async def preview_styles(
        self,
        paper_id: Optional[str] = None,
        query: Optional[str] = None,
        styles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """여러 스타일로 미리보기.

        동일 논문을 여러 스타일로 포맷하여 비교합니다.

        Args:
            paper_id: 논문 ID
            query: 검색어
            styles: 비교할 스타일 목록 (기본: 주요 스타일들)

        Returns:
            스타일별 포맷 결과
        """
        if not FORMATTER_AVAILABLE:
            return {"success": False, "error": "ReferenceFormatter not available"}

        # 논문 찾기
        paper_data = None

        if paper_id:
            paper_data = await self._load_paper_by_id(paper_id)

        if not paper_data and query:
            try:
                search_result = await self.server.search(query=query, top_k=1)
                if search_result and search_result.get("success") and search_result.get("results"):
                    result = search_result["results"][0]
                    paper_id = result.get("document_id", "")
                    if paper_id:
                        paper_data = await self._load_paper_by_id(paper_id)
            except Exception as search_err:
                logger.warning(f"Search failed for query '{query}': {search_err}")

        if not paper_data:
            return {"success": False, "error": "논문을 찾을 수 없습니다"}

        metadata = paper_data.get("metadata") or {}
        paper = PaperReference.from_metadata(metadata, paper_id or "")

        # 스타일 목록
        if not styles:
            styles = ["vancouver", "ama", "apa", "jbjs", "spine", "nlm"]

        # 각 스타일로 포맷
        previews = {}
        for style in styles:
            try:
                previews[style] = self.formatter.format(paper, style=style)
            except Exception as e:
                previews[style] = f"Error: {e}"

        # Export 형식도 추가
        previews["bibtex"] = self.formatter.to_bibtex(paper)
        previews["ris"] = self.formatter.to_ris(paper)

        return {
            "success": True,
            "paper_id": paper_id,
            "title": metadata.get("title", ""),
            "previews": previews,
        }

    def _get_extracted_dir(self) -> Optional[Path]:
        """data/extracted 폴더 경로 반환."""
        # 여러 가능한 경로 시도
        possible_paths = [
            # 1. 서버에 설정된 경로
            getattr(self.server, 'data_dir', None),
            # 2. 현재 파일 기준 상대 경로
            Path(__file__).parent.parent.parent.parent / "data" / "extracted",
            # 3. 현재 작업 디렉토리 기준
            Path.cwd() / "data" / "extracted",
            # 4. 프로젝트 루트 (src 폴더 기준)
            Path(__file__).parent.parent.parent / ".." / "data" / "extracted",
        ]

        for path in possible_paths:
            if path is None:
                continue
            if isinstance(path, str):
                path = Path(path) / "extracted"
            resolved = path.resolve()
            if resolved.exists() and resolved.is_dir():
                return resolved

        return None

    async def _load_paper_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """논문 ID로 데이터 로드."""
        if not paper_id:
            return None

        try:
            # data/extracted 폴더에서 찾기
            extracted_dir = self._get_extracted_dir()

            if not extracted_dir:
                logger.warning("Could not find data/extracted directory")
                return None

            # 파일명 변형 시도
            candidates = [
                f"{paper_id}.json",
                f"{paper_id.replace('/', '_')}.json",
                f"{paper_id.replace(' ', '_')}.json",
            ]

            for filename in candidates:
                filepath = extracted_dir / filename
                if filepath.exists():
                    with open(filepath, "r", encoding="utf-8") as f:
                        return json.load(f)

            # 파일명에 포함된 경우 검색
            for filepath in extracted_dir.glob("*.json"):
                if paper_id in filepath.stem:
                    with open(filepath, "r", encoding="utf-8") as f:
                        return json.load(f)

            return None

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON for paper {paper_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to load paper {paper_id}: {e}")
            return None
