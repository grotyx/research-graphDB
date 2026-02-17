"""PDF Processing Handler for Medical KAG Server.

This module provides PDF/text processing functionality extracted from the main
MedicalKAGServer class for better modularity and maintainability.

Handles:
- PDF ingestion (add_pdf)
- Text analysis (analyze_text)
- PDF metadata extraction
- Document ID generation
"""

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute
from medical_mcp.handlers.utils import generate_document_id, get_abstract_from_sections, determine_tier
from core.exceptions import ProcessingError, ExtractionError

# Import SpineMetadata with alias for backward compatibility
try:
    from graph.relationship_builder import SpineMetadata as GraphSpineMetadata
except ImportError:
    GraphSpineMetadata = None

logger = logging.getLogger(__name__)


class PDFHandler(BaseHandler):
    """Handles PDF and text processing operations."""

    def __init__(self, server: "MedicalKAGServer"):
        """Initialize PDFHandler.

        Args:
            server: Reference to MedicalKAGServer instance for accessing
                   neo4j_client, relationship_builder, processors, etc.
        """
        super().__init__(server)

    # ========================================================================
    # Main PDF Processing Methods
    # ========================================================================

    async def add_pdf(
        self,
        file_path: str,
        metadata: Optional[dict] = None,
        use_vision: bool = True
    ) -> dict:
        """PDF 논문 추가.

        v1.5 업데이트: v1.0 Simplified Pipeline을 기본으로 사용합니다.
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹
        - 조건부 엔티티 추출 (의학 콘텐츠만)
        - Important Citation 자동 처리

        Args:
            file_path: PDF 파일 경로
            metadata: 추가 메타데이터
            use_vision: 통합 PDF 프로세서 사용 여부 (레거시, True: 권장)

        Returns:
            처리 결과 딕셔너리
        """
        path = Path(file_path).resolve()

        # v1.15: Path traversal 방지 — 허용 디렉토리 검증
        allowed_dirs = [
            Path(self.server.project_root / "data").resolve() if hasattr(self.server, 'project_root') else None,
            Path.cwd().resolve(),
        ]
        if not any(d and str(path).startswith(str(d)) for d in allowed_dirs if d):
            logger.warning(f"Path traversal attempt blocked: {file_path}")
            return {"success": False, "error": "접근 불가: 허용된 디렉토리 외부 경로입니다"}

        if not path.exists():
            return {"success": False, "error": f"파일 없음: {file_path}"}

        if not path.suffix.lower() == ".pdf":
            return {"success": False, "error": "PDF 파일이 아닙니다"}

        try:
            # Unified PDF Processor (primary)
            if use_vision and self.server.vision_processor is not None:
                logger.info("Using Unified PDF processor")
                return await self.server._process_with_vision(path, metadata)

            # Fallback: 기존 멀티스텝 파이프라인
            logger.info("Using multi-step pipeline")
            return await self.server._process_with_legacy_pipeline(path, metadata)

        except (ProcessingError, ExtractionError) as e:
            logger.error(f"Processing/extraction error adding PDF: {e}", exc_info=True)
            return {"success": False, "error": f"Processing error: {str(e)}"}
        except Exception as e:
            logger.exception(f"Error adding PDF: {e}")
            return {"success": False, "error": str(e)}

    async def analyze_text(
        self,
        text: str,
        title: str,
        pmid: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """텍스트(논문 초록/본문)를 직접 분석하여 Neo4j에 저장.

        Claude Code에서 논문 텍스트를 붙여넣고 분석 → 관계 구축 → 청크 저장을
        한 번에 수행합니다. PDF 없이 텍스트만으로 지식 그래프 구축이 가능합니다.

        v1.5 업데이트: v1.0 Simplified Pipeline을 기본으로 사용합니다.
        - 22개 문서 유형 자동 감지
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹 (15-25 chunks)
        - 조건부 엔티티 추출 (의학 콘텐츠만)

        Args:
            text: 분석할 텍스트 (논문 초록 또는 본문, 최소 100자 이상)
            title: 논문 제목
            pmid: PubMed ID (선택, 없으면 자동 생성)
            metadata: 추가 메타데이터 (year, journal, authors, doi 등)

        Returns:
            분석 결과 및 저장 통계
        """
        # Delegate to server implementation
        return await self.server.analyze_text(text, title, pmid, metadata)

    def _extract_pdf_metadata(self, path: Path, text: str) -> dict:
        """PDF에서 메타데이터 추출 (저자, 연도, 제목, 저널).

        Args:
            path: PDF 파일 경로
            text: 추출된 텍스트

        Returns:
            메타데이터 딕셔너리 (authors, year, title, journal, first_author)
        """
        metadata = {
            "authors": [],
            "year": 0,
            "title": "",
            "journal": "",
            "first_author": ""
        }

        try:
            import fitz

            doc = fitz.open(str(path))
            try:
                # 1. PDF 내장 메타데이터에서 추출 시도
                pdf_meta = doc.metadata
                if pdf_meta:
                    if pdf_meta.get("title"):
                        metadata["title"] = pdf_meta["title"]
                    if pdf_meta.get("author"):
                        authors = pdf_meta["author"].split(",")
                        metadata["authors"] = [a.strip() for a in authors if a.strip()]
                    if pdf_meta.get("creationDate"):
                        # D:20210315... 형식
                        date_str = pdf_meta["creationDate"]
                        year_match = re.search(r"D:(\d{4})", date_str)
                        if year_match:
                            metadata["year"] = int(year_match.group(1))
            finally:
                doc.close()

            # 2. 텍스트에서 연도 추출 (메타데이터에 없는 경우)
            if metadata["year"] == 0:
                # 일반적인 논문 연도 패턴: (2020), 2020;, Published: 2020
                year_patterns = [
                    r'(?:published|received|accepted)[:\s]*(?:\w+\s+)?(\d{4})',
                    r'©?\s*(\d{4})\s+(?:Elsevier|Springer|Wiley|BMJ|JAMA)',
                    r'\b(20[0-2]\d)\b',  # 2000-2029
                    r'\b(19[89]\d)\b',   # 1980-1999
                ]
                for pattern in year_patterns:
                    match = re.search(pattern, text[:3000], re.IGNORECASE)
                    if match:
                        metadata["year"] = int(match.group(1))
                        break

            # 3. 텍스트에서 저자 추출 (첫 페이지에서)
            if not metadata["authors"]:
                first_page = text[:2000]
                # 일반적인 저자 패턴: Name1, Name2, and Name3
                # Kim JS, Park SM, Lee JH
                author_patterns = [
                    r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)?(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)?){0,5})',
                    r'([A-Z][a-z]+\s+[A-Z]{1,2}(?:\s*,\s*[A-Z][a-z]+\s+[A-Z]{1,2}){0,5})',
                ]
                for pattern in author_patterns:
                    match = re.search(pattern, first_page, re.MULTILINE)
                    if match:
                        author_str = match.group(1)
                        authors = re.split(r',\s*|\s+and\s+', author_str)
                        metadata["authors"] = [a.strip() for a in authors if a.strip() and len(a.strip()) > 2]
                        break

            # 4. 텍스트에서 제목 추출 (없는 경우)
            if not metadata["title"]:
                # 첫 줄들에서 긴 문장을 제목으로 간주
                lines = text[:1500].split('\n')
                for line in lines[:10]:
                    line = line.strip()
                    # 제목 특성: 10-200자, 숫자로 시작하지 않음, 특수문자 적음
                    if 10 < len(line) < 200 and not line[0].isdigit():
                        if not re.search(r'[©®™]|Vol\.|Issue|doi:', line, re.IGNORECASE):
                            metadata["title"] = line
                            break

            # 5. 첫 번째 저자 추출
            if metadata["authors"]:
                first = metadata["authors"][0]
                # "Kim JS" -> "Kim", "John Smith" -> "Smith"
                parts = first.split()
                if len(parts) >= 1:
                    # 한국식: 성이 앞, 서양식: 성이 뒤
                    if len(parts[0]) <= 3:  # 짧으면 성
                        metadata["first_author"] = parts[0]
                    else:
                        metadata["first_author"] = parts[-1]

        except Exception as e:
            logger.warning(f"Metadata extraction error: {e}")

        # Fallback: 파일명에서 정보 추출
        if not metadata["title"]:
            metadata["title"] = path.stem

        return metadata

    def _extract_pdf_text(self, path: Path) -> str:
        """PDF에서 텍스트 추출.

        Args:
            path: PDF 파일 경로

        Returns:
            추출된 텍스트 또는 빈 문자열
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            try:
                text = ""
                for page in doc:
                    text += page.get_text()
                return text
            finally:
                doc.close()
        except ImportError:
            logger.warning("PyMuPDF not available, using placeholder")
            return f"[Placeholder text from {path.name}]"
        except Exception as e:
            logger.error(f"PDF extraction error: {e}", exc_info=True)
            return ""

    def _classify_sections(self, text: str) -> list[dict]:
        """섹션 분류.

        Args:
            text: 텍스트

        Returns:
            섹션 정보 리스트
        """
        # Check if builder is available
        try:
            from builder.section_classifier import SectionInput

            if hasattr(self.server, 'section_classifier'):
                try:
                    result = self.server.section_classifier.classify(SectionInput(text=text))
                    return [{
                        "section": result.section,
                        "tier": f"tier{result.tier}",
                        "content": text,
                        "confidence": result.confidence,
                        "evidence": result.evidence
                    }]
                except Exception as e:
                    logger.warning(f"Section classification error: {e}")
        except ImportError:
            logger.debug("Section classifier not available")

        # Default sections
        return [{"section": "full_text", "tier": "tier1", "content": text}]

    def _detect_citations(self, text: str) -> list[dict]:
        """인용 감지.

        Args:
            text: 텍스트

        Returns:
            인용 정보 리스트
        """
        # Check if builder is available
        try:
            from builder.citation_detector import CitationInput

            if hasattr(self.server, 'citation_detector'):
                try:
                    result = self.server.citation_detector.detect(CitationInput(text=text))
                    return [{
                        "source_type": result.source_type.value if hasattr(result.source_type, 'value') else str(result.source_type),
                        "confidence": result.confidence,
                        "original_ratio": result.original_ratio,
                        "citations": [
                            {
                                "marker": c.citation_marker,
                                "authors": c.authors,
                                "year": c.year
                            }
                            for c in result.citations
                        ]
                    }]
                except Exception as e:
                    logger.warning(f"Citation detection error: {e}")
        except ImportError:
            logger.debug("Citation detector not available")

        return [{"source_type": "original", "content": text}]

    def _classify_study(self, text: str) -> Optional[dict]:
        """연구 설계 분류.

        Args:
            text: 텍스트

        Returns:
            연구 설계 정보 또는 None
        """
        # Check if builder is available
        try:
            from builder.study_classifier import StudyInput

            if hasattr(self.server, 'study_classifier'):
                try:
                    result = self.server.study_classifier.classify(StudyInput(text=text))
                    return {
                        "design": result.study_type.value if hasattr(result, 'study_type') else "unknown",
                        "evidence_level": result.evidence_level.value if hasattr(result, 'evidence_level') else "5"
                    }
                except Exception as e:
                    logger.warning(f"Study classification error: {e}")
        except ImportError:
            logger.debug("Study classifier not available")

        return None

    # ========================================================================
    # PDF Preparation and Analysis Methods
    # ========================================================================

    async def prepare_pdf_prompt(self, file_path: str) -> dict:
        """PDF에서 텍스트를 추출하고 분석용 프롬프트를 반환합니다.

        Claude 앱에서 직접 PDF를 분석할 수 있도록 프롬프트를 생성합니다.
        LLM API 호출 없이 PDF 텍스트만 추출하여 반환합니다.

        워크플로우:
        1. prepare_pdf_prompt → 프롬프트 + PDF 텍스트 반환
        2. Claude 앱에서 직접 분석 수행
        3. add_json으로 결과 저장

        Args:
            file_path: PDF 파일의 절대 경로

        Returns:
            프롬프트와 PDF 텍스트가 포함된 딕셔너리
        """
        import fitz  # pymupdf

        path = Path(file_path)

        if not path.exists():
            return {"success": False, "error": f"파일 없음: {file_path}"}

        if not path.suffix.lower() == ".pdf":
            return {"success": False, "error": "PDF 파일이 아닙니다"}

        try:
            # PDF 텍스트 추출
            doc = fitz.open(str(path))
            try:
                total_pages = len(doc)
                full_text = ""
                for page_num, page in enumerate(doc, 1):
                    page_text = page.get_text()
                    if page_text.strip():
                        full_text += f"\n--- PAGE {page_num} ---\n{page_text}"
            finally:
                doc.close()

            if not full_text.strip():
                return {"success": False, "error": "PDF에서 텍스트를 추출할 수 없습니다."}

            # JSON 스키마 및 프롬프트 생성
            extraction_prompt = '''You are a medical research paper analyst specializing in spine surgery literature.
Analyze the following PDF text and extract ALL important information in a structured JSON format.

## JSON SCHEMA

{
  "metadata": {
    "title": "Paper title",
    "authors": ["Author 1", "Author 2"],
    "year": 2024,
    "journal": "Journal name",
    "doi": "",
    "pmid": "",
    "abstract": "Complete original abstract text (REQUIRED)",
    "study_type": "meta-analysis/systematic-review/RCT/prospective-cohort/retrospective-cohort/case-control/case-series/case-report/expert-opinion",
    "study_design": "randomized/non-randomized/single-arm/multi-arm",
    "evidence_level": "1a/1b/2a/2b/3/4/5",
    "sample_size": 100,
    "centers": "single-center/multi-center",
    "blinding": "none/single-blind/double-blind/open-label"
  },
  "spine_metadata": {
    "sub_domain": "Degenerative/Deformity/Trauma/Tumor/Infection/Basic Science",
    "anatomy_level": "L4-5",
    "anatomy_region": "cervical/thoracic/lumbar/sacral/thoracolumbar/lumbosacral",
    "pathology": ["Disease 1", "Disease 2"],
    "interventions": ["Surgery 1", "Surgery 2"],
    "comparison_type": "vs_conventional/vs_other_mis/vs_conservative/single_arm",
    "follow_up_months": 24,
    "main_conclusion": "Brief conclusion in 1-2 sentences",
    "outcomes": [
      {
        "name": "VAS",
        "category": "pain/function/radiologic/complication/satisfaction/quality_of_life",
        "baseline": 7.2,
        "final": 2.1,
        "value_intervention": "2.1 ± 0.8",
        "value_control": "3.5 ± 1.2",
        "value_difference": "-1.4",
        "p_value": "0.001",
        "confidence_interval": "95% CI: -2.1 to -0.7",
        "effect_size": "Cohen's d = 0.8",
        "timepoint": "preop/postop/1mo/3mo/6mo/1yr/2yr/final",
        "is_significant": true,
        "direction": "improved/worsened/unchanged"
      }
    ],
    "complications": [
      {
        "name": "Dural tear",
        "incidence_intervention": "2.5%",
        "incidence_control": "4.1%",
        "p_value": "0.35",
        "severity": "minor/major/revision_required"
      }
    ]
  },
  "important_citations": [
    {
      "authors": ["Kim", "Park"],
      "year": 2023,
      "context": "supports_result/contradicts_result/comparison",
      "section": "discussion/results/introduction",
      "citation_text": "Original sentence containing the citation",
      "importance_reason": "Why this citation is important",
      "outcome_comparison": "VAS/ODI/fusion_rate",
      "direction_match": true
    }
  ],
  "chunks": [
    {
      "content": "Chunk text content (200-500 chars for text, complete for tables)",
      "content_type": "text/table/figure/key_finding",
      "section_type": "abstract/introduction/methods/results/discussion/conclusion",
      "tier": "tier1/tier2",
      "is_key_finding": false,
      "topic_summary": "One sentence summary",
      "keywords": ["keyword1", "keyword2"],
      "pico": {
        "population": "",
        "intervention": "",
        "comparison": "",
        "outcome": ""
      },
      "statistics": {
        "p_values": [],
        "effect_sizes": [],
        "confidence_intervals": []
      }
    }
  ]
}

## CRITICAL INSTRUCTIONS

1. **METADATA**: Extract title, authors, year, journal, DOI, PMID, abstract (REQUIRED)
2. **EVIDENCE LEVEL**: 1a=Meta-analysis, 1b=RCT, 2a=Cohort review, 2b=Cohort, 3=Case-control, 4=Case series, 5=Expert opinion
3. **SPINE METADATA**: Extract sub_domain, anatomy, pathology, interventions, outcomes with ALL statistics
4. **CHUNKS**: Create 15-25 chunks (tier1=abstract/results/conclusion, tier2=intro/methods/discussion)
5. **TABLES**: Extract COMPLETE table data - DO NOT summarize or omit any rows
6. **STATISTICS**: Extract exact p-values, CIs, effect sizes - these are CRITICAL
7. **CITATIONS**: Extract important citations that support/contradict results

Return ONLY valid JSON, no additional text.'''

            # 사용자 안내 메시지
            usage_guide = """
## 사용 방법

아래 프롬프트와 PDF 텍스트를 복사하여 Claude 앱에서 분석하세요.
분석 결과로 받은 JSON을 `add_json` 도구로 저장할 수 있습니다.

### 방법 1: 직접 복사-붙여넣기
1. 아래 "prompt" 내용을 Claude 앱에 붙여넣기
2. "pdf_text" 내용을 이어서 붙여넣기
3. Claude의 JSON 응답을 파일로 저장
4. `add_json` 도구로 저장: add_json(file_path="저장한파일.json")

### 방법 2: JSON 파일 직접 저장
분석 후 JSON을 data/extracted/ 폴더에 저장하면 add_json으로 로드 가능.

### JSON 저장 시 주의사항
- 파일명: {년도}_{저자}_{제목}.json 형식 권장
- 인코딩: UTF-8
- 형식: 위 스키마를 정확히 따를 것
"""

            return {
                "success": True,
                "file_name": path.name,
                "text_length": len(full_text),
                "page_count": total_pages,
                "usage_guide": usage_guide,
                "prompt": extraction_prompt,
                "pdf_text": full_text,
                "next_step": "Claude 앱에서 분석 후 add_json으로 결과 저장"
            }

        except Exception as e:
            logger.exception(f"Error preparing PDF prompt: {e}")
            return {"success": False, "error": str(e)}

    async def store_analyzed_paper(
        self,
        title: str,
        abstract: str,
        year: int,
        interventions: list[str],
        outcomes: list[dict],
        pathologies: Optional[list[str]] = None,
        anatomy_levels: Optional[list[str]] = None,
        authors: Optional[list[str]] = None,
        journal: Optional[str] = None,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        evidence_level: Optional[str] = None,
        study_design: Optional[str] = None,
        sample_size: Optional[int] = None,
        summary: Optional[str] = None,
        sub_domain: Optional[str] = None,
        chunks: Optional[list[dict]] = None,
        patient_cohorts: Optional[list[dict]] = None,
        followups: Optional[list[dict]] = None,
        costs: Optional[list[dict]] = None,
        quality_metrics: Optional[list[dict]] = None,
    ) -> dict:
        """미리 분석된 논문 데이터를 Neo4j에 저장합니다.

        Claude Desktop 또는 Claude Code에서 PDF/텍스트를 직접 분석한 후,
        추출된 데이터를 이 도구로 전달하여 Neo4j에 저장합니다.
        LLM API 호출 없이 저장만 수행합니다.

        사용 시나리오:
        1. Claude Desktop에서 PDF 첨부 → 분석 → 이 도구로 저장
        2. Claude Code에서 텍스트 분석 → 이 도구로 저장
        3. PubMed에서 가져온 데이터 분석 → 이 도구로 저장

        Args:
            title: 논문 제목 (필수)
            abstract: 초록 또는 본문 요약 (필수)
            year: 출판년도 (필수)
            interventions: 수술법/중재 목록 (필수), 예: ["TLIF", "PLIF"]
            outcomes: 결과변수 목록 (필수), 예: [{"name": "ODI", "value": "28.5", "p_value": 0.001, "direction": "improved"}]
            pathologies: 질환 목록, 예: ["Lumbar Stenosis", "Spondylolisthesis"]
            anatomy_levels: 해부학적 위치, 예: ["L4-L5", "L5-S1"]
            authors: 저자 목록, 예: ["Kim J", "Park S"]
            journal: 저널명
            doi: DOI
            pmid: PubMed ID
            evidence_level: 근거 수준 ("1a", "1b", "2a", "2b", "3", "4", "5")
            study_design: 연구 설계 ("RCT", "Cohort", "Case-Control" 등)
            sample_size: 샘플 크기
            summary: 700+ word 종합 요약
            sub_domain: 척추 하위 도메인 ("Degenerative", "Deformity", "Trauma" 등)
            chunks: 청크 목록, 예: [{"content": "...", "section_type": "results", "tier": 1}]
            patient_cohorts: v1.2 환자 코호트 데이터
            followups: v1.2 추적관찰 데이터
            costs: v1.2 비용 분석 데이터
            quality_metrics: v1.2 품질 평가 데이터

        Returns:
            저장 결과 (paper_id, nodes_created, relationships_created 등)
        """
        from datetime import datetime

        # 1. 입력 검증
        if not title:
            return {"success": False, "error": "title은 필수입니다."}
        if not abstract or len(abstract) < 50:
            return {"success": False, "error": "abstract은 최소 50자 이상 필요합니다."}
        if not year or year < 1900 or year > 2100:
            return {"success": False, "error": "year는 1900-2100 사이여야 합니다."}
        if not interventions:
            return {"success": False, "error": "interventions 목록은 필수입니다."}
        if not outcomes:
            return {"success": False, "error": "outcomes 목록은 필수입니다."}

        # 2. Paper ID 생성
        if pmid:
            paper_id = f"pubmed_{pmid}"
        else:
            short_uuid = str(uuid.uuid4())[:8]
            paper_id = f"analyzed_{short_uuid}"

        logger.info(f"Storing pre-analyzed paper: {title[:50]}... (paper_id={paper_id})")

        # 3. Neo4j 연결 확인
        if not self.server.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        if not self.server.relationship_builder:
            return {"success": False, "error": "RelationshipBuilder not initialized"}

        # 4. PubMed enrichment (v1.18: store_paper에도 추가)
        pubmed_metadata = None
        pubmed_enriched = False
        if hasattr(self.server, 'pubmed_enricher') and self.server.pubmed_enricher and (doi or title):
            try:
                logger.info(f"[store_paper/handler] PubMed enrichment for: {title[:50]}...")
                pubmed_metadata = await self.server.pubmed_enricher.auto_enrich(
                    title=title, authors=authors or [], year=year, journal=journal, doi=doi
                )
                if pubmed_metadata:
                    pubmed_enriched = True
                    if not pmid and pubmed_metadata.pmid:
                        pmid = pubmed_metadata.pmid
                    if not doi and pubmed_metadata.doi:
                        doi = pubmed_metadata.doi
                    if not authors and pubmed_metadata.authors:
                        authors = pubmed_metadata.authors
                    if (not journal or journal == "Unknown") and pubmed_metadata.journal:
                        journal = pubmed_metadata.journal
                    if not evidence_level and pubmed_metadata.publication_types:
                        inferred = self.server.pubmed_enricher.get_evidence_level_from_publication_type(
                            pubmed_metadata.publication_types
                        )
                        if inferred:
                            evidence_level = inferred
            except Exception as e:
                logger.warning(f"[store_paper/handler] PubMed enrichment failed: {e}")

        # PMID가 확보되면 paper_id 재생성
        if pmid and paper_id.startswith("analyzed_"):
            paper_id = f"pubmed_{pmid}"

        # 5. GraphSpineMetadata 생성
        try:
            # GraphSpineMetadata imported at module level from relationship_builder

            # outcomes 형식 변환 (모든 필드 유지, v1.18)
            formatted_outcomes = []
            for o in outcomes:
                if isinstance(o, dict):
                    outcome_dict = dict(o)
                    if not outcome_dict.get("name"):
                        logger.warning(f"[store_paper/handler] Outcome with empty name, skipping: {o}")
                        continue
                    formatted_outcomes.append(outcome_dict)
                elif o:
                    formatted_outcomes.append({"name": str(o)})

            graph_spine_meta = GraphSpineMetadata(
                sub_domain=sub_domain or "Unknown",
                sub_domains=[sub_domain] if sub_domain else [],
                anatomy_levels=anatomy_levels if anatomy_levels is not None else [],
                interventions=interventions,
                pathologies=pathologies or [],
                outcomes=formatted_outcomes,
                surgical_approach=[],
                pico_population=None,
                pico_intervention=interventions[0] if interventions else None,
                pico_comparison=interventions[1] if len(interventions) > 1 else None,
                pico_outcome=", ".join([o.get("name", "") for o in formatted_outcomes if o.get("name")]),
                main_conclusion=summary[:500] if summary else None,
                summary=summary or "",
                processing_version="v1.3_store_analyzed",
                # v1.2 Extended entities
                patient_cohorts=patient_cohorts or [],
                followups=followups or [],
                costs=costs or [],
                quality_metrics=quality_metrics or [],
            )

            # 6. RelationshipBuilder로 Neo4j에 저장 (v1.5: 멀티유저 지원)
            from dataclasses import dataclass, field as df

            # ExtractedMetadata 호환 객체 생성
            @dataclass
            class ExtractedMetaCompat:
                title: str = ""
                authors: list = df(default_factory=list)
                year: int = 0
                journal: str = ""
                doi: str = ""
                pmid: str = ""
                study_type: str = ""
                study_design: str = ""
                evidence_level: str = ""
                sample_size: int = 0
                centers: str = ""
                blinding: str = ""
                abstract: str = ""
                spine: Any = None

            meta_compat = ExtractedMetaCompat(
                title=title,
                authors=authors or [],
                year=year,
                journal=journal or "Unknown",
                doi=doi or "",  # v1.18: None 방지
                pmid=pmid or "",
                study_design=study_design or "",
                evidence_level=evidence_level or "unknown",
                sample_size=sample_size or 0,
                abstract=abstract,
                spine=graph_spine_meta,
            )

            neo4j_result = await self.server.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=meta_compat,
                spine_metadata=graph_spine_meta,
                chunks=[],  # store_analyzed_data는 청크 별도 처리
                owner=self.server.current_user,
                shared=True
            )

            logger.info(f"Neo4j relationships built: {neo4j_result.nodes_created} nodes, {neo4j_result.relationships_created} relationships")

        except (ProcessingError, ExtractionError) as e:
            logger.error(f"Processing/extraction error during Neo4j storage: {e}", exc_info=True)
            return {"success": False, "error": f"Processing error: {str(e)}"}
        except Exception as e:
            logger.exception(f"Neo4j storage failed: {e}")
            return {"success": False, "error": f"Neo4j 저장 실패: {str(e)}"}

        # 6. 청크 저장 (선택)
        chunks_created = 0
        if chunks and self.server.neo4j_client:
            try:
                from core.embedding import OpenAIEmbeddingGenerator

                embedding_gen = OpenAIEmbeddingGenerator()

                # 청크 텍스트 추출 (content/text/summary 필드 호환)
                def _extract_chunk_text(c: dict) -> str:
                    return c.get("content") or c.get("text") or c.get("summary") or ""

                chunk_texts = [_extract_chunk_text(c) for c in chunks if _extract_chunk_text(c)]

                if chunk_texts:
                    # v1.14.3: 기존 Chunk 삭제 (중복 방지)
                    await self.server._delete_existing_chunks(paper_id)

                    # 임베딩 생성
                    embeddings = embedding_gen.embed_batch(chunk_texts)

                    # Neo4j에 청크 저장
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                        chunk_id = f"{paper_id}_chunk_{i}"

                        chunk_content = _extract_chunk_text(chunk)
                        # tier: "tier1"/"tier2" 문자열 또는 1/2 정수 모두 호환
                        tier_raw = chunk.get("tier", "tier2")
                        chunk_tier = 1 if str(tier_raw) in ("tier1", "1") else 2
                        chunk_section = chunk.get("section_type", "body")

                        await self.server.neo4j_client.run_query(
                            """
                            MATCH (p:Paper {paper_id: $paper_id})
                            CREATE (c:Chunk {
                                chunk_id: $chunk_id,
                                content: $content,
                                tier: $tier,
                                section: $section,
                                embedding: $embedding
                            })
                            CREATE (p)-[:HAS_CHUNK]->(c)
                            """,
                            {
                                "paper_id": paper_id,
                                "chunk_id": chunk_id,
                                "content": chunk_content,
                                "tier": chunk_tier,
                                "section": chunk_section,
                                "embedding": embedding
                            }
                        )
                        chunks_created += 1

                    logger.info(f"Stored {chunks_created} chunks with embeddings to Neo4j")

            except Exception as e:
                logger.warning(f"Chunk storage failed: {e}")

        # 7. 결과 반환
        return {
            "success": True,
            "paper_id": paper_id,
            "title": title,
            "processing_method": "store_analyzed_paper",
            "pubmed_enriched": pubmed_enriched,
            "stored_metadata": {
                "title": title,
                "year": year,
                "journal": journal,
                "authors": authors,
                "doi": doi,
                "pmid": pmid,
                "evidence_level": evidence_level,
                "study_design": study_design,
                "sample_size": sample_size,
                "sub_domain": sub_domain,
                "interventions": interventions,
                "pathologies": pathologies,
                "anatomy_levels": anatomy_levels,
                "outcomes_count": len(formatted_outcomes),
            },
            "neo4j_result": {
                "nodes_created": neo4j_result.nodes_created if neo4j_result else 0,
                "relationships_created": neo4j_result.relationships_created if neo4j_result else 0,
                "warnings": neo4j_result.warnings if neo4j_result else [],
            },
            "stats": {
                "abstract_length": len(abstract),
                "chunks_created": chunks_created,
                "storage_backend": "neo4j",
                "v72_entities": {
                    "patient_cohorts": len(patient_cohorts) if patient_cohorts else 0,
                    "followups": len(followups) if followups else 0,
                    "costs": len(costs) if costs else 0,
                    "quality_metrics": len(quality_metrics) if quality_metrics else 0,
                }
            }
        }
