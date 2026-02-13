"""Universal Metadata Extractor (v7.0).

Citation-ready metadata extraction for all document types.
Supports 22 document types with type-specific fields and APA 7th citation formatting.

Based on PRD: docs/PRD_v7_SIMPLIFIED_PIPELINE.md
Unified Document Schema: docs/UNIFIED_DOCUMENT_SCHEMA.md

Usage:
    extractor = MetadataExtractor()

    # Extract from text/PDF content
    metadata = await extractor.extract(
        text=pdf_text,
        document_type=DocumentType.JOURNAL_ARTICLE,
        url="https://pubmed.ncbi.nlm.nih.gov/12345/"
    )

    # Format citation
    citation = extractor.format_citation_apa(metadata)
"""

import re
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any

from llm import LLMClient, LLMConfig
from builder.document_type_detector import DocumentType
from graph.spine_schema import EvidenceLevel

logger = logging.getLogger(__name__)


# =============================================================================
# Core Metadata (All Document Types)
# =============================================================================

@dataclass
class CoreMetadata:
    """모든 문서 유형에 공통 필수 메타데이터.

    Tier 1: 모든 문서에 필요한 핵심 인용 정보.
    """
    # Required fields
    title: str
    authors: list[str]
    year: int
    document_type: DocumentType
    source: str  # Journal, Publisher, Website, etc.

    # Access metadata
    access_date: datetime = field(default_factory=datetime.now)
    language: str = "en"
    url: Optional[str] = None

    def validate(self) -> list[str]:
        """필수 필드 검증.

        Returns:
            비어있는 필수 필드 목록
        """
        errors = []
        if not self.title:
            errors.append("title is required")
        if not self.authors:
            errors.append("authors is required (use ['Unknown'] if unavailable)")
        if not self.year:
            errors.append("year is required")
        if not self.source:
            errors.append("source is required")
        return errors


# =============================================================================
# Type-Specific Metadata Classes
# =============================================================================

@dataclass
class JournalArticleMetadata(CoreMetadata):
    """학술 논문 메타데이터.

    APA Citation: Authors. (Year). Title. Journal, Volume(Issue), pages. https://doi.org/xxx
    """
    # Journal-specific (Tier 2)
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmc_id: Optional[str] = None

    # Domain-specific (Tier 3)
    evidence_level: Optional[EvidenceLevel] = None
    publication_types: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    abstract: Optional[str] = None


@dataclass
class BookMetadata(CoreMetadata):
    """책/북챕터 메타데이터.

    APA Citation:
    - Full book: Authors. (Year). Title (edition). Publisher.
    - Book section: Authors. (Year). Chapter title. In Editors (Eds.), Book title (edition, pages). Publisher.
    """
    # Book-specific (Tier 2)
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None  # Chapter title (for book sections)
    chapter_number: Optional[int] = None
    pages: Optional[str] = None  # Chapter page range
    editors: list[str] = field(default_factory=list)
    place: Optional[str] = None  # Publication location

    # Domain-specific (Tier 3)
    abstract: Optional[str] = None


@dataclass
class WebpageMetadata(CoreMetadata):
    """웹페이지/블로그 메타데이터.

    APA Citation: Authors. (Year, Month Day). Title. Website Title. URL
    """
    # Webpage-specific (Tier 2)
    website_title: Optional[str] = None
    publication_date: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    archive_url: Optional[str] = None  # Wayback Machine
    content_type: Optional[str] = None  # "blog", "news", "documentation"


@dataclass
class NewspaperMetadata(CoreMetadata):
    """신문 기사 메타데이터.

    APA Citation: Authors. (Year, Month Day). Title. Publication, page.
    """
    # Newspaper-specific (Tier 2)
    publication: Optional[str] = None  # Newspaper name
    publication_date: Optional[datetime] = None
    section: Optional[str] = None  # e.g., "Health", "Science"
    page: Optional[str] = None


@dataclass
class PatentMetadata(CoreMetadata):
    """특허 메타데이터.

    APA Citation: Inventors. (Year). Title (Patent No. XXXXXXX). Patent Office.
    """
    # Patent-specific (Tier 2)
    patent_number: Optional[str] = None
    filing_date: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    assignee: Optional[str] = None  # Company/organization
    patent_office: str = "USPTO"  # USPTO, EPO, KIPO, etc.
    classification: list[str] = field(default_factory=list)  # IPC/CPC codes
    abstract: Optional[str] = None


@dataclass
class PreprintMetadata(CoreMetadata):
    """프리프린트 메타데이터.

    APA Citation: Authors. (Year). Title [Preprint]. Repository. https://doi.org/xxx
    """
    # Preprint-specific (Tier 2)
    repository: Optional[str] = None  # e.g., "arXiv", "medRxiv"
    preprint_id: Optional[str] = None  # e.g., "2103.12345"
    version: Optional[str] = None
    submission_date: Optional[datetime] = None
    doi: Optional[str] = None
    license: Optional[str] = None  # e.g., "CC-BY-4.0"
    peer_review_status: str = "not peer-reviewed"

    # Domain-specific (Tier 3)
    abstract: Optional[str] = None


@dataclass
class ConferencePaperMetadata(CoreMetadata):
    """학회 논문 메타데이터.

    APA Citation: Authors. (Year). Title. In Proceedings Title (pages). Publisher.
    """
    # Conference-specific (Tier 2)
    conference_name: Optional[str] = None
    conference_location: Optional[str] = None
    conference_date: Optional[datetime] = None
    proceedings_title: Optional[str] = None
    publisher: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None


# Union type for all metadata
DocumentMetadata = (
    JournalArticleMetadata
    | BookMetadata
    | WebpageMetadata
    | NewspaperMetadata
    | PatentMetadata
    | PreprintMetadata
    | ConferencePaperMetadata
)


# =============================================================================
# Metadata Extractor Class
# =============================================================================

class MetadataExtractor:
    """Universal metadata extraction for all document types.

    Combines rule-based parsing with LLM-based extraction:
    - Rule-based: DOI, PMID, ISBN, patent numbers, URLs
    - LLM-based: When structure is ambiguous or missing

    Ensures citation-ready metadata for all document types.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        """Initialize extractor.

        Args:
            llm_client: LLM client for fallback extraction (optional)
        """
        self.llm = llm_client or LLMClient(
            config=LLMConfig(temperature=0.1)
        )

    async def extract(
        self,
        text: str,
        document_type: DocumentType,
        url: Optional[str] = None,
        filename: Optional[str] = None
    ) -> DocumentMetadata:
        """문서 유형에 맞는 메타데이터 추출.

        Args:
            text: 문서 전문 텍스트 (PDF 추출 또는 웹 페이지 내용)
            document_type: 감지된 문서 유형
            url: 원본 URL (있는 경우)
            filename: 파일명 (있는 경우)

        Returns:
            DocumentMetadata (type-specific dataclass)

        Raises:
            ValueError: If required fields cannot be extracted
        """
        # Document type별 추출 함수 매핑
        extractors = {
            DocumentType.JOURNAL_ARTICLE: self._extract_journal_article,
            DocumentType.BOOK: self._extract_book,
            DocumentType.BOOK_SECTION: self._extract_book_section,
            DocumentType.WEBPAGE: self._extract_webpage,
            DocumentType.BLOG_POST: self._extract_webpage,  # Same as webpage
            DocumentType.NEWSPAPER_ARTICLE: self._extract_newspaper,
            DocumentType.PATENT: self._extract_patent,
            DocumentType.PREPRINT: self._extract_preprint,
            DocumentType.CONFERENCE_PAPER: self._extract_conference_paper,
        }

        extractor = extractors.get(document_type)
        if extractor:
            metadata = await extractor(text, url, filename)
        else:
            # 지원하지 않는 타입: CoreMetadata만 추출
            metadata = await self._extract_core(text, document_type, url, filename)

        # 검증
        errors = metadata.validate()
        if errors:
            logger.warning(f"Metadata validation warnings: {errors}")

        return metadata

    # =========================================================================
    # Core Extraction (Common to All Types)
    # =========================================================================

    async def _extract_core(
        self,
        text: str,
        document_type: DocumentType,
        url: Optional[str] = None,
        filename: Optional[str] = None
    ) -> CoreMetadata:
        """핵심 메타데이터 추출 (모든 타입 공통).

        Args:
            text: 문서 텍스트
            document_type: 문서 유형
            url: URL
            filename: 파일명

        Returns:
            CoreMetadata with required fields
        """
        # Rule-based extraction first
        title = self._extract_title_rule_based(text) or filename or "Untitled"
        authors = self._extract_authors_rule_based(text)
        year = self._extract_year_rule_based(text) or datetime.now().year
        source = self._infer_source(text, url, document_type)

        # LLM fallback if title/authors empty
        if not authors or title == "Untitled":
            llm_result = await self._extract_core_llm(text, document_type)
            if not authors:
                authors = llm_result.get("authors", ["Unknown"])
            if title == "Untitled":
                title = llm_result.get("title", "Untitled")

        return CoreMetadata(
            title=title,
            authors=authors,
            year=year,
            document_type=document_type,
            source=source,
            url=url,
            access_date=datetime.now(),
            language=self._detect_language(text)
        )

    async def _extract_core_llm(
        self,
        text: str,
        document_type: DocumentType
    ) -> dict[str, Any]:
        """LLM 기반 핵심 메타데이터 추출.

        Args:
            text: 문서 텍스트 (첫 2000자)
            document_type: 문서 유형

        Returns:
            dict with title, authors, year
        """
        prompt = f"""
Extract bibliographic metadata from the following {document_type.value} text.

REQUIRED:
- title: Full document title
- authors: List of author names (format: "Last, F.")
- year: Publication year (integer)

TEXT (first 2000 characters):
{text[:2000]}

Return JSON:
{{
    "title": "...",
    "authors": ["Last1, F.", "Last2, G."],
    "year": 2023
}}
"""

        try:
            response = await self.llm.generate(prompt)
            # v7.15: JSON 추출/repair — LLM이 markdown 블록으로 감싸는 경우 처리
            text = response if isinstance(response, str) else str(response)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            result = json.loads(text.strip())
            return result
        except Exception as e:
            logger.warning(f"LLM core extraction failed: {e}")
            return {"title": "Untitled", "authors": ["Unknown"], "year": datetime.now().year}

    # =========================================================================
    # Journal Article Extraction
    # =========================================================================

    async def _extract_journal_article(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> JournalArticleMetadata:
        """학술 논문 메타데이터 추출."""
        # Core metadata
        core = await self._extract_core(text, DocumentType.JOURNAL_ARTICLE, url, filename)

        # Journal-specific fields (rule-based)
        doi = self._extract_doi(text)
        pmid = self._extract_pmid(text)
        pmc_id = self._extract_pmc_id(text)

        # Extract journal info
        journal_info = self._extract_journal_info_rule_based(text)

        # LLM fallback for missing fields
        if not journal_info.get("journal") or not doi:
            llm_result = await self._extract_journal_llm(text)
            journal_info = {**journal_info, **llm_result}

        return JournalArticleMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=journal_info.get("journal", core.source),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Journal-specific
            journal=journal_info.get("journal"),
            volume=journal_info.get("volume"),
            issue=journal_info.get("issue"),
            pages=journal_info.get("pages"),
            doi=doi,
            pmid=pmid,
            pmc_id=pmc_id,
            # Domain-specific
            evidence_level=self._infer_evidence_level(text),
            publication_types=self._extract_publication_types(text),
            mesh_terms=self._extract_mesh_terms(text),
            abstract=self._extract_abstract(text)
        )

    async def _extract_journal_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 저널 정보 추출."""
        prompt = f"""
Extract journal article metadata from this text.

REQUIRED:
- journal: Journal name
- volume: Volume number (if available)
- issue: Issue number (if available)
- pages: Page range (e.g., "123-145")

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "journal": "...",
    "volume": "...",
    "issue": "...",
    "pages": "..."
}}
"""

        try:
            response = await self.llm.generate(prompt)
            return json.loads(response)
        except Exception as e:
            logger.warning(f"LLM journal extraction failed: {e}")
            return {}

    # =========================================================================
    # Book Extraction
    # =========================================================================

    async def _extract_book(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> BookMetadata:
        """책 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.BOOK, url, filename)

        # Book-specific fields
        isbn = self._extract_isbn(text)
        book_info = await self._extract_book_llm(text)

        return BookMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=book_info.get("publisher", core.source),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Book-specific
            publisher=book_info.get("publisher"),
            isbn=isbn,
            edition=book_info.get("edition"),
            editors=book_info.get("editors", []),
            place=book_info.get("place")
        )

    async def _extract_book_section(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> BookMetadata:
        """북챕터 메타데이터 추출 (Book과 유사하지만 chapter 추가)."""
        book_meta = await self._extract_book(text, url, filename)

        # Chapter-specific
        chapter_info = await self._extract_chapter_llm(text)
        book_meta.chapter = chapter_info.get("chapter")
        book_meta.chapter_number = chapter_info.get("chapter_number")
        book_meta.pages = chapter_info.get("pages")

        return book_meta

    async def _extract_book_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 책 정보 추출."""
        prompt = f"""
Extract book metadata from this text.

REQUIRED:
- publisher: Publisher name
- edition: Edition (e.g., "2nd ed.", "Revised")
- place: Publication location (city)
- editors: List of editor names (if applicable)

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "publisher": "...",
    "edition": "...",
    "place": "...",
    "editors": ["Editor1", "Editor2"]
}}
"""

        try:
            response = await self.llm.generate(prompt)
            return json.loads(response)
        except Exception as e:
            logger.warning(f"LLM book extraction failed: {e}")
            return {}

    async def _extract_chapter_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 챕터 정보 추출."""
        prompt = f"""
Extract book chapter metadata from this text.

REQUIRED:
- chapter: Chapter title
- chapter_number: Chapter number (integer)
- pages: Page range (e.g., "45-78")

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "chapter": "...",
    "chapter_number": 5,
    "pages": "45-78"
}}
"""

        try:
            response = await self.llm.generate(prompt)
            return json.loads(response)
        except Exception as e:
            logger.warning(f"LLM chapter extraction failed: {e}")
            return {}

    # =========================================================================
    # Webpage Extraction
    # =========================================================================

    async def _extract_webpage(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> WebpageMetadata:
        """웹페이지 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.WEBPAGE, url, filename)

        # Webpage-specific
        webpage_info = await self._extract_webpage_llm(text, url)

        return WebpageMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=webpage_info.get("website_title", core.source),
            url=url or core.url,
            access_date=core.access_date,
            language=core.language,
            # Webpage-specific
            website_title=webpage_info.get("website_title"),
            publication_date=webpage_info.get("publication_date"),
            last_modified=webpage_info.get("last_modified"),
            content_type=webpage_info.get("content_type")
        )

    async def _extract_webpage_llm(self, text: str, url: Optional[str]) -> dict[str, Any]:
        """LLM 기반 웹페이지 정보 추출."""
        prompt = f"""
Extract webpage metadata from this text.

URL: {url or "Not provided"}

REQUIRED:
- website_title: Name of website/blog
- publication_date: When content was published (ISO format)
- content_type: "blog", "news", "documentation", "medical", etc.

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "website_title": "...",
    "publication_date": "2023-06-15T00:00:00",
    "content_type": "blog"
}}
"""

        try:
            response = await self.llm.generate(prompt)
            result = json.loads(response)
            # Parse datetime if present
            if result.get("publication_date"):
                result["publication_date"] = datetime.fromisoformat(result["publication_date"])
            return result
        except Exception as e:
            logger.warning(f"LLM webpage extraction failed: {e}")
            return {}

    # =========================================================================
    # Newspaper Extraction
    # =========================================================================

    async def _extract_newspaper(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> NewspaperMetadata:
        """신문 기사 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.NEWSPAPER_ARTICLE, url, filename)

        # Newspaper-specific
        newspaper_info = await self._extract_newspaper_llm(text)

        return NewspaperMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=newspaper_info.get("publication", core.source),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Newspaper-specific
            publication=newspaper_info.get("publication"),
            publication_date=newspaper_info.get("publication_date"),
            section=newspaper_info.get("section"),
            page=newspaper_info.get("page")
        )

    async def _extract_newspaper_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 신문 정보 추출."""
        prompt = f"""
Extract newspaper article metadata from this text.

REQUIRED:
- publication: Newspaper name
- publication_date: Article date (ISO format)
- section: Section name (e.g., "Health", "Science")
- page: Page number

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "publication": "...",
    "publication_date": "2023-06-15T00:00:00",
    "section": "Health",
    "page": "A12"
}}
"""

        try:
            response = await self.llm.generate(prompt)
            result = json.loads(response)
            if result.get("publication_date"):
                result["publication_date"] = datetime.fromisoformat(result["publication_date"])
            return result
        except Exception as e:
            logger.warning(f"LLM newspaper extraction failed: {e}")
            return {}

    # =========================================================================
    # Patent Extraction
    # =========================================================================

    async def _extract_patent(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> PatentMetadata:
        """특허 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.PATENT, url, filename)

        # Patent-specific (rule-based)
        patent_number = self._extract_patent_number(text)

        # LLM for additional info
        patent_info = await self._extract_patent_llm(text)

        return PatentMetadata(
            # Core
            title=core.title,
            authors=patent_info.get("inventors", core.authors),
            year=core.year,
            document_type=core.document_type,
            source=patent_info.get("patent_office", "USPTO"),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Patent-specific
            patent_number=patent_number or patent_info.get("patent_number"),
            filing_date=patent_info.get("filing_date"),
            publication_date=patent_info.get("publication_date"),
            assignee=patent_info.get("assignee"),
            patent_office=patent_info.get("patent_office", "USPTO"),
            classification=patent_info.get("classification", []),
            abstract=self._extract_abstract(text)
        )

    async def _extract_patent_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 특허 정보 추출."""
        prompt = f"""
Extract patent metadata from this text.

REQUIRED:
- patent_number: Patent number (e.g., "US11123456B2")
- inventors: List of inventor names
- assignee: Company/organization
- patent_office: USPTO, EPO, KIPO, etc.
- filing_date: Filing date (ISO format)
- publication_date: Publication date (ISO format)
- classification: IPC/CPC codes

TEXT (first 2000 characters):
{text[:2000]}

Return JSON:
{{
    "patent_number": "...",
    "inventors": ["Name1", "Name2"],
    "assignee": "...",
    "patent_office": "USPTO",
    "filing_date": "2021-03-15T00:00:00",
    "publication_date": "2023-06-01T00:00:00",
    "classification": ["A61B17/00"]
}}
"""

        try:
            response = await self.llm.generate(prompt)
            result = json.loads(response)
            # Parse datetimes
            if result.get("filing_date"):
                result["filing_date"] = datetime.fromisoformat(result["filing_date"])
            if result.get("publication_date"):
                result["publication_date"] = datetime.fromisoformat(result["publication_date"])
            return result
        except Exception as e:
            logger.warning(f"LLM patent extraction failed: {e}")
            return {}

    # =========================================================================
    # Preprint Extraction
    # =========================================================================

    async def _extract_preprint(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> PreprintMetadata:
        """프리프린트 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.PREPRINT, url, filename)

        # Preprint-specific
        doi = self._extract_doi(text)
        preprint_info = await self._extract_preprint_llm(text, url)

        return PreprintMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=preprint_info.get("repository", core.source),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Preprint-specific
            repository=preprint_info.get("repository"),
            preprint_id=preprint_info.get("preprint_id"),
            version=preprint_info.get("version"),
            submission_date=preprint_info.get("submission_date"),
            doi=doi,
            license=preprint_info.get("license"),
            peer_review_status=preprint_info.get("peer_review_status", "not peer-reviewed"),
            abstract=self._extract_abstract(text)
        )

    async def _extract_preprint_llm(self, text: str, url: Optional[str]) -> dict[str, Any]:
        """LLM 기반 프리프린트 정보 추출."""
        prompt = f"""
Extract preprint metadata from this text.

URL: {url or "Not provided"}

REQUIRED:
- repository: "arXiv", "bioRxiv", "medRxiv", "SSRN", etc.
- preprint_id: ID number (e.g., "2103.12345")
- version: Version number (e.g., "v1", "v2")
- submission_date: Date (ISO format)
- license: License type (e.g., "CC-BY-4.0")

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "repository": "arXiv",
    "preprint_id": "2103.12345",
    "version": "v1",
    "submission_date": "2023-03-15T00:00:00",
    "license": "CC-BY-4.0"
}}
"""

        try:
            response = await self.llm.generate(prompt)
            result = json.loads(response)
            if result.get("submission_date"):
                result["submission_date"] = datetime.fromisoformat(result["submission_date"])
            return result
        except Exception as e:
            logger.warning(f"LLM preprint extraction failed: {e}")
            return {}

    # =========================================================================
    # Conference Paper Extraction
    # =========================================================================

    async def _extract_conference_paper(
        self,
        text: str,
        url: Optional[str],
        filename: Optional[str]
    ) -> ConferencePaperMetadata:
        """학회 논문 메타데이터 추출."""
        core = await self._extract_core(text, DocumentType.CONFERENCE_PAPER, url, filename)

        # Conference-specific
        doi = self._extract_doi(text)
        isbn = self._extract_isbn(text)
        conf_info = await self._extract_conference_llm(text)

        return ConferencePaperMetadata(
            # Core
            title=core.title,
            authors=core.authors,
            year=core.year,
            document_type=core.document_type,
            source=conf_info.get("conference_name", core.source),
            url=core.url,
            access_date=core.access_date,
            language=core.language,
            # Conference-specific
            conference_name=conf_info.get("conference_name"),
            conference_location=conf_info.get("conference_location"),
            conference_date=conf_info.get("conference_date"),
            proceedings_title=conf_info.get("proceedings_title"),
            publisher=conf_info.get("publisher"),
            pages=conf_info.get("pages"),
            doi=doi,
            isbn=isbn
        )

    async def _extract_conference_llm(self, text: str) -> dict[str, Any]:
        """LLM 기반 학회 정보 추출."""
        prompt = f"""
Extract conference paper metadata from this text.

REQUIRED:
- conference_name: Full conference name
- conference_location: Location (city, country)
- conference_date: Date (ISO format)
- proceedings_title: Title of proceedings
- publisher: Publisher name
- pages: Page range

TEXT (first 1500 characters):
{text[:1500]}

Return JSON:
{{
    "conference_name": "...",
    "conference_location": "New York, USA",
    "conference_date": "2023-06-15T00:00:00",
    "proceedings_title": "...",
    "publisher": "...",
    "pages": "123-145"
}}
"""

        try:
            response = await self.llm.generate(prompt)
            result = json.loads(response)
            if result.get("conference_date"):
                result["conference_date"] = datetime.fromisoformat(result["conference_date"])
            return result
        except Exception as e:
            logger.warning(f"LLM conference extraction failed: {e}")
            return {}

    # =========================================================================
    # Rule-based Helper Functions
    # =========================================================================

    def _extract_title_rule_based(self, text: str) -> Optional[str]:
        """제목 추출 (규칙 기반)."""
        # Look for title in first 500 characters
        lines = text[:500].split("\n")
        for line in lines:
            line = line.strip()
            # Title is usually first non-empty line or after "Title:" marker
            if line and len(line) > 10 and not line.startswith("http"):
                return line
        return None

    def _extract_authors_rule_based(self, text: str) -> list[str]:
        """저자 추출 (규칙 기반)."""
        # Look for author patterns in first 1000 characters
        text_snippet = text[:1000]

        # Pattern: "Author1, Author2, and Author3"
        author_match = re.search(
            r"(?:by|authors?:)\s*([A-Z][a-z]+(?: [A-Z][a-z]+)*(?:,? and [A-Z][a-z]+(?: [A-Z][a-z]+)*)*)",
            text_snippet,
            re.IGNORECASE
        )
        if author_match:
            author_text = author_match.group(1)
            authors = re.split(r",? and |, ", author_text)
            return [a.strip() for a in authors if a.strip()]

        return []

    def _extract_year_rule_based(self, text: str) -> Optional[int]:
        """연도 추출 (규칙 기반)."""
        # Look for year patterns in first 1000 characters
        text_snippet = text[:1000]

        # Pattern: 4-digit year (2000-2099)
        year_matches = re.findall(r'\b(20[0-2]\d)\b', text_snippet)
        if year_matches:
            # Return most recent year
            return max(int(y) for y in year_matches)

        return None

    def _extract_doi(self, text: str) -> Optional[str]:
        """DOI 추출."""
        match = re.search(r'10\.\d{4,}/[^\s]+', text)
        return match.group(0) if match else None

    def _extract_pmid(self, text: str) -> Optional[str]:
        """PMID 추출."""
        match = re.search(r'PMID:\s*(\d+)', text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_pmc_id(self, text: str) -> Optional[str]:
        """PMCID 추출."""
        match = re.search(r'PMCID?:\s*(PMC\d+)', text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_isbn(self, text: str) -> Optional[str]:
        """ISBN 추출."""
        match = re.search(r'ISBN[:\s-]*([\d-]+)', text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_patent_number(self, text: str) -> Optional[str]:
        """특허 번호 추출."""
        match = re.search(r'[A-Z]{2}\d{7,}[A-Z]?\d?', text)
        return match.group(0) if match else None

    def _extract_journal_info_rule_based(self, text: str) -> dict[str, str]:
        """저널 정보 추출 (규칙 기반)."""
        info = {}

        # Volume, Issue, Pages pattern: "45(12):1234-1245"
        match = re.search(r'(\d+)\((\d+)\):(\d+-\d+)', text)
        if match:
            info["volume"] = match.group(1)
            info["issue"] = match.group(2)
            info["pages"] = match.group(3)

        return info

    def _extract_abstract(self, text: str) -> Optional[str]:
        """초록 추출."""
        # Look for "ABSTRACT" section
        match = re.search(
            r'ABSTRACT[:\s]+(.*?)(?=\n\n[A-Z]|\n\nINTRODUCTION|\Z)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            abstract = match.group(1).strip()
            # Limit length
            return abstract[:2000]
        return None

    def _infer_source(
        self,
        text: str,
        url: Optional[str],
        document_type: DocumentType
    ) -> str:
        """소스 추론 (journal, publisher, website)."""
        if url:
            # Extract domain as source
            domain = url.split("//")[-1].split("/")[0]
            return domain.replace("www.", "")

        # Default by type
        type_sources = {
            DocumentType.JOURNAL_ARTICLE: "Unknown Journal",
            DocumentType.BOOK: "Unknown Publisher",
            DocumentType.WEBPAGE: "Unknown Website",
            DocumentType.NEWSPAPER_ARTICLE: "Unknown Publication",
            DocumentType.PATENT: "USPTO",
        }
        return type_sources.get(document_type, "Unknown")

    def _detect_language(self, text: str) -> str:
        """언어 감지 (간단한 휴리스틱)."""
        # Check for Korean characters
        if re.search(r'[가-힣]', text[:500]):
            return "ko"
        # Default to English
        return "en"

    def _infer_evidence_level(self, text: str) -> Optional[EvidenceLevel]:
        """근거 수준 추론 (Study design keywords)."""
        text_lower = text.lower()

        if "meta-analysis" in text_lower or "systematic review" in text_lower:
            return EvidenceLevel.LEVEL_1A
        if "randomized controlled trial" in text_lower or "rct" in text_lower:
            return EvidenceLevel.LEVEL_1B
        if "cohort study" in text_lower or "prospective" in text_lower:
            return EvidenceLevel.LEVEL_2B
        if "case-control" in text_lower:
            return EvidenceLevel.LEVEL_3
        if "case series" in text_lower or "case report" in text_lower:
            return EvidenceLevel.LEVEL_4

        return None

    def _extract_publication_types(self, text: str) -> list[str]:
        """Publication types 추출."""
        types = []
        text_lower = text.lower()

        type_keywords = {
            "Meta-Analysis": ["meta-analysis", "meta analysis"],
            "Systematic Review": ["systematic review"],
            "Randomized Controlled Trial": ["randomized controlled trial", "rct"],
            "Clinical Trial": ["clinical trial"],
            "Cohort Studies": ["cohort study", "cohort studies"],
            "Case Reports": ["case report", "case series"],
        }

        for pub_type, keywords in type_keywords.items():
            if any(kw in text_lower for kw in keywords):
                types.append(pub_type)

        return types

    def _extract_mesh_terms(self, text: str) -> list[str]:
        """MeSH terms 추출 (규칙 기반 - 제한적)."""
        # Look for "MeSH:" or "Keywords:" section
        mesh_match = re.search(
            r'(?:MeSH|Keywords?):\s*(.*?)(?=\n\n|\Z)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if mesh_match:
            terms_text = mesh_match.group(1)
            # Split by comma or semicolon
            terms = re.split(r'[,;]', terms_text)
            return [t.strip() for t in terms if t.strip()]
        return []

    # =========================================================================
    # APA 7th Citation Formatting
    # =========================================================================

    def format_citation_apa(self, metadata: DocumentMetadata) -> str:
        """APA 7th Edition 인용 형식 생성.

        Args:
            metadata: DocumentMetadata (any type)

        Returns:
            APA citation string
        """
        if isinstance(metadata, JournalArticleMetadata):
            return self._format_journal_apa(metadata)
        elif isinstance(metadata, BookMetadata):
            if metadata.chapter:
                return self._format_book_section_apa(metadata)
            else:
                return self._format_book_apa(metadata)
        elif isinstance(metadata, WebpageMetadata):
            return self._format_webpage_apa(metadata)
        elif isinstance(metadata, NewspaperMetadata):
            return self._format_newspaper_apa(metadata)
        elif isinstance(metadata, PatentMetadata):
            return self._format_patent_apa(metadata)
        elif isinstance(metadata, PreprintMetadata):
            return self._format_preprint_apa(metadata)
        elif isinstance(metadata, ConferencePaperMetadata):
            return self._format_conference_apa(metadata)
        else:
            # Generic format
            return self._format_generic_apa(metadata)

    def _format_journal_apa(self, meta: JournalArticleMetadata) -> str:
        """Journal Article APA citation."""
        # Authors. (Year). Title. Journal, Volume(Issue), pages. https://doi.org/xxx
        authors = self._format_authors_apa(meta.authors)

        citation = f"{authors} ({meta.year}). {meta.title}."

        if meta.journal:
            citation += f" {meta.journal}"
            if meta.volume:
                citation += f", {meta.volume}"
                if meta.issue:
                    citation += f"({meta.issue})"
            if meta.pages:
                citation += f", {meta.pages}"

        citation += "."

        if meta.doi:
            citation += f" https://doi.org/{meta.doi}"
        elif meta.url:
            citation += f" {meta.url}"

        return citation

    def _format_book_apa(self, meta: BookMetadata) -> str:
        """Book APA citation."""
        # Authors. (Year). Title (edition). Publisher.
        authors = self._format_authors_apa(meta.authors)

        citation = f"{authors} ({meta.year}). {meta.title}"

        if meta.edition:
            citation += f" ({meta.edition})"

        citation += "."

        if meta.publisher:
            citation += f" {meta.publisher}."

        return citation

    def _format_book_section_apa(self, meta: BookMetadata) -> str:
        """Book Section APA citation."""
        # Authors. (Year). Chapter title. In Editors (Eds.), Book title (edition, pages). Publisher.
        authors = self._format_authors_apa(meta.authors)

        citation = f"{authors} ({meta.year}). {meta.chapter}. In "

        if meta.editors:
            editors = self._format_authors_apa(meta.editors)
            citation += f"{editors} (Eds.), "

        citation += f"{meta.title}"

        if meta.edition or meta.pages:
            citation += " ("
            if meta.edition:
                citation += meta.edition
            if meta.pages:
                if meta.edition:
                    citation += ", "
                citation += f"pp. {meta.pages}"
            citation += ")"

        citation += "."

        if meta.publisher:
            citation += f" {meta.publisher}."

        return citation

    def _format_webpage_apa(self, meta: WebpageMetadata) -> str:
        """Webpage APA citation."""
        # Authors. (Year, Month Day). Title. Website Title. URL
        authors = self._format_authors_apa(meta.authors)

        # Format date
        if meta.publication_date:
            date_str = meta.publication_date.strftime("%Y, %B %d")
        else:
            date_str = str(meta.year)

        citation = f"{authors} ({date_str}). {meta.title}."

        if meta.website_title:
            citation += f" {meta.website_title}."

        if meta.url:
            citation += f" {meta.url}"

        return citation

    def _format_newspaper_apa(self, meta: NewspaperMetadata) -> str:
        """Newspaper APA citation."""
        # Authors. (Year, Month Day). Title. Publication, page.
        authors = self._format_authors_apa(meta.authors)

        if meta.publication_date:
            date_str = meta.publication_date.strftime("%Y, %B %d")
        else:
            date_str = str(meta.year)

        citation = f"{authors} ({date_str}). {meta.title}."

        if meta.publication:
            citation += f" {meta.publication}"
            if meta.page:
                citation += f", {meta.page}"
            citation += "."

        if meta.url:
            citation += f" {meta.url}"

        return citation

    def _format_patent_apa(self, meta: PatentMetadata) -> str:
        """Patent APA citation."""
        # Inventors. (Year). Title (Patent No. XXXXXXX). Patent Office.
        inventors = self._format_authors_apa(meta.authors)

        citation = f"{inventors} ({meta.year}). {meta.title}"

        if meta.patent_number:
            citation += f" ({meta.patent_office} Patent No. {meta.patent_number})"

        citation += f". {meta.patent_office}."

        return citation

    def _format_preprint_apa(self, meta: PreprintMetadata) -> str:
        """Preprint APA citation."""
        # Authors. (Year). Title [Preprint]. Repository. https://doi.org/xxx
        authors = self._format_authors_apa(meta.authors)

        citation = f"{authors} ({meta.year}). {meta.title} [Preprint]."

        if meta.repository:
            citation += f" {meta.repository}."

        if meta.doi:
            citation += f" https://doi.org/{meta.doi}"
        elif meta.url:
            citation += f" {meta.url}"

        return citation

    def _format_conference_apa(self, meta: ConferencePaperMetadata) -> str:
        """Conference Paper APA citation."""
        # Authors. (Year). Title. In Proceedings Title (pages). Publisher.
        authors = self._format_authors_apa(meta.authors)

        citation = f"{authors} ({meta.year}). {meta.title}."

        if meta.proceedings_title:
            citation += f" In {meta.proceedings_title}"
            if meta.pages:
                citation += f" (pp. {meta.pages})"
            citation += "."

        if meta.publisher:
            citation += f" {meta.publisher}."

        if meta.doi:
            citation += f" https://doi.org/{meta.doi}"
        elif meta.url:
            citation += f" {meta.url}"

        return citation

    def _format_generic_apa(self, meta: CoreMetadata) -> str:
        """Generic APA citation."""
        authors = self._format_authors_apa(meta.authors)
        citation = f"{authors} ({meta.year}). {meta.title}. {meta.source}."
        if meta.url:
            citation += f" {meta.url}"
        return citation

    def _format_authors_apa(self, authors: list[str]) -> str:
        """APA 스타일 저자 포맷팅.

        Rules:
        - 1 author: Smith, J.
        - 2 authors: Smith, J., & Jones, A.
        - 3+ authors: Smith, J., Jones, A., & Brown, K.

        Args:
            authors: List of author names

        Returns:
            Formatted author string
        """
        if not authors:
            return "Unknown"

        if len(authors) == 1:
            return authors[0]
        elif len(authors) == 2:
            return f"{authors[0]}, & {authors[1]}"
        else:
            return ", ".join(authors[:-1]) + f", & {authors[-1]}"
