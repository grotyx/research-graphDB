"""Document Type Detector (v7.0).

Smart auto-detection with hybrid approach for document type classification.
Supports confidence-based user confirmation when detection is uncertain.

Usage:
    detector = DocumentTypeDetector()

    # From URL
    result = detector.detect_from_url("https://pubmed.ncbi.nlm.nih.gov/12345678/")
    print(result.document_type)  # DocumentType.JOURNAL_ARTICLE
    print(result.confidence)     # 0.95

    # From PDF content
    result = detector.detect_from_content(pdf_text, filename="paper.pdf")

    # Hybrid check
    if result.needs_confirmation:
        # Ask user to confirm or select
        confirmed_type = ask_user(result.document_type, result.alternatives)
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# =============================================================================
# Document Type Enum (from spine_schema.py)
# =============================================================================

class DocumentType(Enum):
    """문서 유형 (Zotero item types 기반, v6.0)."""

    # 학술 출판물
    JOURNAL_ARTICLE = "journal-article"
    BOOK = "book"
    BOOK_SECTION = "book-section"
    CONFERENCE_PAPER = "conference-paper"
    THESIS = "thesis"
    REPORT = "report"
    PREPRINT = "preprint"

    # 뉴스/미디어
    NEWSPAPER_ARTICLE = "newspaper-article"
    MAGAZINE_ARTICLE = "magazine-article"
    BLOG_POST = "blog-post"
    WEBPAGE = "webpage"

    # 기술/데이터
    DATASET = "dataset"
    SOFTWARE = "software"
    PATENT = "patent"
    STANDARD = "standard"

    # 기타
    PRESENTATION = "presentation"
    VIDEO = "video"
    INTERVIEW = "interview"
    LETTER = "letter"
    MANUSCRIPT = "manuscript"
    DOCUMENT = "document"  # 기본값


# =============================================================================
# Detection Result
# =============================================================================

@dataclass
class DetectionResult:
    """문서 유형 감지 결과."""

    document_type: DocumentType
    confidence: float  # 0.0 ~ 1.0
    detection_method: str  # "url", "content", "filename", "pattern"
    alternatives: list[DocumentType] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # 감지에 사용된 증거

    @property
    def needs_confirmation(self) -> bool:
        """사용자 확인이 필요한지 여부."""
        return self.confidence < 0.85

    @property
    def is_confident(self) -> bool:
        """높은 신뢰도로 감지되었는지."""
        return self.confidence >= 0.85


# =============================================================================
# URL Domain Mappings
# =============================================================================

# Domain → Document Type with confidence
URL_DOMAIN_MAP: dict[str, tuple[DocumentType, float]] = {
    # Academic / Journal
    "pubmed.ncbi.nlm.nih.gov": (DocumentType.JOURNAL_ARTICLE, 0.98),
    "pmc.ncbi.nlm.nih.gov": (DocumentType.JOURNAL_ARTICLE, 0.98),
    "doi.org": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "dx.doi.org": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "scholar.google.com": (DocumentType.JOURNAL_ARTICLE, 0.70),
    "sciencedirect.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "springer.com": (DocumentType.JOURNAL_ARTICLE, 0.85),
    "link.springer.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "nature.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "wiley.com": (DocumentType.JOURNAL_ARTICLE, 0.85),
    "onlinelibrary.wiley.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "journals.lww.com": (DocumentType.JOURNAL_ARTICLE, 0.95),  # Spine journal
    "academic.oup.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "jamanetwork.com": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "nejm.org": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "thelancet.com": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "bmj.com": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "cell.com": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "plos.org": (DocumentType.JOURNAL_ARTICLE, 0.95),
    "frontiersin.org": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "mdpi.com": (DocumentType.JOURNAL_ARTICLE, 0.90),
    "researchgate.net": (DocumentType.JOURNAL_ARTICLE, 0.70),

    # Preprint
    "arxiv.org": (DocumentType.PREPRINT, 0.95),
    "biorxiv.org": (DocumentType.PREPRINT, 0.95),
    "medrxiv.org": (DocumentType.PREPRINT, 0.95),
    "ssrn.com": (DocumentType.PREPRINT, 0.90),

    # News / Media
    "nytimes.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "washingtonpost.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "theguardian.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "bbc.com": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "bbc.co.uk": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "reuters.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "apnews.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "cnn.com": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "forbes.com": (DocumentType.MAGAZINE_ARTICLE, 0.85),
    "time.com": (DocumentType.MAGAZINE_ARTICLE, 0.90),
    "newsweek.com": (DocumentType.MAGAZINE_ARTICLE, 0.90),
    "wired.com": (DocumentType.MAGAZINE_ARTICLE, 0.90),
    "economist.com": (DocumentType.MAGAZINE_ARTICLE, 0.90),

    # Korean News
    "chosun.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "donga.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "joins.com": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "hani.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "khan.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.95),
    "ytn.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "sbs.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "mbc.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.90),
    "kbs.co.kr": (DocumentType.NEWSPAPER_ARTICLE, 0.90),

    # Blog
    "medium.com": (DocumentType.BLOG_POST, 0.90),
    "substack.com": (DocumentType.BLOG_POST, 0.90),
    "wordpress.com": (DocumentType.BLOG_POST, 0.80),
    "blogger.com": (DocumentType.BLOG_POST, 0.85),
    "tistory.com": (DocumentType.BLOG_POST, 0.85),
    "naver.com": (DocumentType.BLOG_POST, 0.70),  # Could be news too
    "blog.naver.com": (DocumentType.BLOG_POST, 0.90),
    "brunch.co.kr": (DocumentType.BLOG_POST, 0.90),

    # Patent
    "patents.google.com": (DocumentType.PATENT, 0.98),
    "patentscope.wipo.int": (DocumentType.PATENT, 0.98),
    "uspto.gov": (DocumentType.PATENT, 0.98),
    "epo.org": (DocumentType.PATENT, 0.95),
    "kipris.or.kr": (DocumentType.PATENT, 0.95),

    # Dataset
    "kaggle.com": (DocumentType.DATASET, 0.90),
    "data.gov": (DocumentType.DATASET, 0.90),
    "zenodo.org": (DocumentType.DATASET, 0.80),  # Could be paper too
    "figshare.com": (DocumentType.DATASET, 0.80),
    "dataverse.harvard.edu": (DocumentType.DATASET, 0.85),

    # Software
    "github.com": (DocumentType.SOFTWARE, 0.85),
    "gitlab.com": (DocumentType.SOFTWARE, 0.85),
    "pypi.org": (DocumentType.SOFTWARE, 0.90),
    "npmjs.com": (DocumentType.SOFTWARE, 0.90),

    # Video
    "youtube.com": (DocumentType.VIDEO, 0.95),
    "youtu.be": (DocumentType.VIDEO, 0.95),
    "vimeo.com": (DocumentType.VIDEO, 0.95),

    # Book
    "books.google.com": (DocumentType.BOOK, 0.85),
    "amazon.com": (DocumentType.BOOK, 0.60),  # Could be many things
    "goodreads.com": (DocumentType.BOOK, 0.80),
}


# =============================================================================
# Content Pattern Mappings
# =============================================================================

# Regex patterns for content detection
CONTENT_PATTERNS: list[tuple[str, DocumentType, float, str]] = [
    # Journal Article indicators
    (r'\bDOI:\s*10\.\d+/', DocumentType.JOURNAL_ARTICLE, 0.90, "DOI found"),
    (r'\bPMID:\s*\d+', DocumentType.JOURNAL_ARTICLE, 0.95, "PMID found"),
    (r'\bPMCID:\s*PMC\d+', DocumentType.JOURNAL_ARTICLE, 0.95, "PMCID found"),
    (r'\babstract\b.*\b(background|objective|methods|results|conclusion)\b', DocumentType.JOURNAL_ARTICLE, 0.85, "Abstract structure"),
    (r'\b(randomized|randomised)\s+(controlled\s+)?trial\b', DocumentType.JOURNAL_ARTICLE, 0.90, "RCT mention"),
    (r'\bmeta[- ]?analysis\b', DocumentType.JOURNAL_ARTICLE, 0.90, "Meta-analysis mention"),
    (r'\bsystematic\s+review\b', DocumentType.JOURNAL_ARTICLE, 0.90, "Systematic review"),
    (r'\bprospective\s+(cohort\s+)?study\b', DocumentType.JOURNAL_ARTICLE, 0.85, "Cohort study"),
    (r'\bretrospective\s+(cohort\s+)?study\b', DocumentType.JOURNAL_ARTICLE, 0.85, "Retrospective study"),
    (r'\bp\s*[<>=]\s*0\.\d+', DocumentType.JOURNAL_ARTICLE, 0.80, "P-value found"),
    (r'\b95%\s*CI\b', DocumentType.JOURNAL_ARTICLE, 0.80, "Confidence interval"),
    (r'\bodds\s+ratio\b', DocumentType.JOURNAL_ARTICLE, 0.80, "Odds ratio"),
    (r'\bhazard\s+ratio\b', DocumentType.JOURNAL_ARTICLE, 0.80, "Hazard ratio"),

    # Book indicators
    (r'\bISBN[:\s-]*\d', DocumentType.BOOK, 0.95, "ISBN found"),
    (r'\bchapter\s+\d+\b', DocumentType.BOOK_SECTION, 0.80, "Chapter reference"),
    (r'\bpart\s+(one|two|three|i|ii|iii|\d+)\b', DocumentType.BOOK, 0.70, "Part reference"),
    (r'\bedition\b.*\b(first|second|third|\d+)\b', DocumentType.BOOK, 0.75, "Edition mention"),
    (r'\bpublished\s+by\b', DocumentType.BOOK, 0.60, "Publisher mention"),

    # Thesis indicators
    (r'\b(doctoral|ph\.?d\.?|master\'?s?)\s+(thesis|dissertation)\b', DocumentType.THESIS, 0.95, "Thesis mention"),
    (r'\bsubmitted\s+(to|in\s+partial\s+fulfillment)\b', DocumentType.THESIS, 0.85, "Thesis submission"),

    # Patent indicators
    (r'\bpatent\s*(no\.?|number|#)?\s*:?\s*[A-Z]{2}\d+', DocumentType.PATENT, 0.95, "Patent number"),
    (r'\bclaims?\s*:\s*\d+\b', DocumentType.PATENT, 0.70, "Patent claims"),
    (r'\binventor[s]?\s*:', DocumentType.PATENT, 0.80, "Inventor field"),
    (r'\bassignee\s*:', DocumentType.PATENT, 0.85, "Assignee field"),

    # Preprint indicators
    (r'\bpreprint\b', DocumentType.PREPRINT, 0.85, "Preprint mention"),
    (r'\bnot\s+peer[- ]?reviewed\b', DocumentType.PREPRINT, 0.80, "Not peer-reviewed"),
    (r'\barxiv:\d+\.\d+', DocumentType.PREPRINT, 0.95, "arXiv ID"),
    (r'\bbiorxiv\b', DocumentType.PREPRINT, 0.95, "bioRxiv mention"),
    (r'\bmedrxiv\b', DocumentType.PREPRINT, 0.95, "medRxiv mention"),

    # Conference paper
    (r'\bproceedings\s+of\b', DocumentType.CONFERENCE_PAPER, 0.85, "Proceedings mention"),
    (r'\bconference\s+on\b', DocumentType.CONFERENCE_PAPER, 0.75, "Conference mention"),
    (r'\bpresented\s+at\b', DocumentType.CONFERENCE_PAPER, 0.70, "Presented at"),

    # Report
    (r'\btechnical\s+report\b', DocumentType.REPORT, 0.90, "Technical report"),
    (r'\bwhite\s+paper\b', DocumentType.REPORT, 0.85, "White paper"),
    (r'\breport\s+no\.?\s*:?\s*\d+', DocumentType.REPORT, 0.80, "Report number"),

    # Dataset
    (r'\bdataset\b.*\b(description|documentation)\b', DocumentType.DATASET, 0.80, "Dataset description"),
    (r'\bdata\s+dictionary\b', DocumentType.DATASET, 0.85, "Data dictionary"),
]


# =============================================================================
# Filename Pattern Mappings
# =============================================================================

FILENAME_PATTERNS: list[tuple[str, DocumentType, float, str]] = [
    # Journal article
    (r'paper', DocumentType.JOURNAL_ARTICLE, 0.60, "paper in filename"),
    (r'article', DocumentType.JOURNAL_ARTICLE, 0.60, "article in filename"),
    (r'manuscript', DocumentType.JOURNAL_ARTICLE, 0.70, "manuscript in filename"),
    (r'\d{4}.*et\s*al', DocumentType.JOURNAL_ARTICLE, 0.75, "year et al pattern"),

    # Book
    (r'book', DocumentType.BOOK, 0.70, "book in filename"),
    (r'chapter', DocumentType.BOOK_SECTION, 0.80, "chapter in filename"),
    (r'textbook', DocumentType.BOOK, 0.85, "textbook in filename"),

    # Thesis
    (r'thesis', DocumentType.THESIS, 0.90, "thesis in filename"),
    (r'dissertation', DocumentType.THESIS, 0.90, "dissertation in filename"),

    # Report
    (r'report', DocumentType.REPORT, 0.70, "report in filename"),
    (r'whitepaper', DocumentType.REPORT, 0.85, "whitepaper in filename"),

    # Presentation
    (r'presentation', DocumentType.PRESENTATION, 0.85, "presentation in filename"),
    (r'slides', DocumentType.PRESENTATION, 0.85, "slides in filename"),
    (r'\.pptx?$', DocumentType.PRESENTATION, 0.95, "PowerPoint extension"),
]


# =============================================================================
# DocumentTypeDetector Class
# =============================================================================

class DocumentTypeDetector:
    """문서 유형 감지기.

    Smart auto-detection with hybrid approach:
    - URL domain mapping (highest confidence)
    - Content pattern matching
    - Filename analysis
    - Combined scoring with alternatives

    When confidence < 0.85, suggests user confirmation.
    """

    CONFIDENCE_THRESHOLD = 0.85

    def __init__(self):
        """Initialize detector."""
        self.url_map = URL_DOMAIN_MAP
        self.content_patterns = CONTENT_PATTERNS
        self.filename_patterns = FILENAME_PATTERNS

    def detect(
        self,
        url: Optional[str] = None,
        content: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> DetectionResult:
        """종합적인 문서 유형 감지.

        Args:
            url: 문서 URL
            content: 문서 내용 텍스트
            filename: 파일명

        Returns:
            DetectionResult with type, confidence, and alternatives
        """
        candidates: list[tuple[DocumentType, float, str, str]] = []

        # 1. URL 기반 감지 (가장 높은 신뢰도)
        if url:
            url_result = self._detect_from_url(url)
            if url_result:
                candidates.append((
                    url_result[0],
                    url_result[1],
                    "url",
                    url_result[2]
                ))

        # 2. 내용 기반 감지
        if content:
            content_results = self._detect_from_content(content)
            candidates.extend(content_results)

        # 3. 파일명 기반 감지
        if filename:
            filename_results = self._detect_from_filename(filename)
            candidates.extend(filename_results)

        # 후보가 없으면 기본값
        if not candidates:
            return DetectionResult(
                document_type=DocumentType.DOCUMENT,
                confidence=0.0,
                detection_method="default",
                alternatives=[DocumentType.JOURNAL_ARTICLE, DocumentType.WEBPAGE],
                evidence=["No detection patterns matched"]
            )

        # 유형별 점수 집계
        type_scores: dict[DocumentType, list[tuple[float, str, str]]] = {}
        for doc_type, conf, method, evidence in candidates:
            if doc_type not in type_scores:
                type_scores[doc_type] = []
            type_scores[doc_type].append((conf, method, evidence))

        # 최종 점수 계산 (최대값 + 보너스)
        final_scores: dict[DocumentType, float] = {}
        for doc_type, scores in type_scores.items():
            max_score = max(s[0] for s in scores)
            # 여러 증거가 있으면 보너스
            bonus = min(0.05 * (len(scores) - 1), 0.10)
            final_scores[doc_type] = min(max_score + bonus, 1.0)

        # 최고 점수 선택
        best_type = max(final_scores, key=lambda k: final_scores[k])
        best_score = final_scores[best_type]

        # 대안 목록 (2등, 3등)
        sorted_types = sorted(final_scores.items(), key=lambda x: -x[1])
        alternatives = [t for t, s in sorted_types[1:4] if s > 0.3]

        # 증거 수집
        evidence_list = []
        if best_type in type_scores:
            for conf, method, ev in type_scores[best_type]:
                evidence_list.append(f"[{method}] {ev} (conf: {conf:.2f})")

        # 주요 감지 방법 결정
        if best_type in type_scores:
            methods = [s[1] for s in type_scores[best_type]]
            primary_method = max(set(methods), key=methods.count)
        else:
            primary_method = "combined"

        return DetectionResult(
            document_type=best_type,
            confidence=best_score,
            detection_method=primary_method,
            alternatives=alternatives,
            evidence=evidence_list
        )

    def detect_from_url(self, url: str) -> DetectionResult:
        """URL만으로 감지."""
        return self.detect(url=url)

    def detect_from_content(self, content: str, filename: Optional[str] = None) -> DetectionResult:
        """내용으로 감지."""
        return self.detect(content=content, filename=filename)

    def _detect_from_url(self, url: str) -> Optional[tuple[DocumentType, float, str]]:
        """URL 도메인 기반 감지."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # www. 제거
            if domain.startswith("www."):
                domain = domain[4:]

            # 직접 매핑 확인
            if domain in self.url_map:
                doc_type, confidence = self.url_map[domain]
                return (doc_type, confidence, f"Domain: {domain}")

            # 부분 매칭 (subdomain 포함)
            for mapped_domain, (doc_type, confidence) in self.url_map.items():
                if domain.endswith(mapped_domain) or mapped_domain in domain:
                    return (doc_type, confidence * 0.9, f"Domain contains: {mapped_domain}")

            # URL 경로 분석
            path = parsed.path.lower()
            if "/article/" in path or "/paper/" in path:
                return (DocumentType.JOURNAL_ARTICLE, 0.70, "Path contains: article/paper")
            if "/blog/" in path or "/post/" in path:
                return (DocumentType.BLOG_POST, 0.70, "Path contains: blog/post")
            if "/book/" in path:
                return (DocumentType.BOOK, 0.70, "Path contains: book")
            if "/patent/" in path:
                return (DocumentType.PATENT, 0.80, "Path contains: patent")

            return None

        except Exception as e:
            logger.warning(f"URL parsing error: {e}")
            return None

    def _detect_from_content(self, content: str) -> list[tuple[DocumentType, float, str, str]]:
        """내용 패턴 기반 감지."""
        results = []
        content_lower = content.lower()

        for pattern, doc_type, confidence, evidence in self.content_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                results.append((doc_type, confidence, "content", evidence))

        return results

    def _detect_from_filename(self, filename: str) -> list[tuple[DocumentType, float, str, str]]:
        """파일명 기반 감지."""
        results = []
        filename_lower = filename.lower()

        for pattern, doc_type, confidence, evidence in self.filename_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                results.append((doc_type, confidence, "filename", evidence))

        return results

    def get_type_for_source(self, source: str) -> DocumentType:
        """소스 문자열에서 기본 유형 반환.

        Args:
            source: "pubmed", "pmc", "pdf", "url", "text" 등

        Returns:
            적절한 DocumentType
        """
        source_map = {
            "pubmed": DocumentType.JOURNAL_ARTICLE,
            "pmc": DocumentType.JOURNAL_ARTICLE,
            "pubmed_abstract": DocumentType.JOURNAL_ARTICLE,
            "pdf": DocumentType.JOURNAL_ARTICLE,  # Default, but could be book
            "url": DocumentType.WEBPAGE,
            "text": DocumentType.DOCUMENT,
        }
        return source_map.get(source.lower(), DocumentType.DOCUMENT)

    def format_for_user_confirmation(self, result: DetectionResult) -> dict:
        """사용자 확인용 포맷.

        MCP 또는 Streamlit에서 사용자에게 보여줄 형식.

        Args:
            result: DetectionResult

        Returns:
            dict with question, options, recommended
        """
        options = [result.document_type] + result.alternatives
        options_display = [
            {
                "value": t.value,
                "label": t.value.replace("-", " ").title(),
                "recommended": t == result.document_type
            }
            for t in options
        ]

        return {
            "question": "What type of document is this?",
            "detected": result.document_type.value,
            "confidence": result.confidence,
            "needs_confirmation": result.needs_confirmation,
            "options": options_display,
            "evidence": result.evidence[:3],  # Top 3 evidence
        }


# =============================================================================
# Convenience Functions
# =============================================================================

def detect_document_type(
    url: Optional[str] = None,
    content: Optional[str] = None,
    filename: Optional[str] = None,
) -> DetectionResult:
    """편의 함수: 문서 유형 감지.

    Args:
        url: 문서 URL
        content: 문서 내용
        filename: 파일명

    Returns:
        DetectionResult
    """
    detector = DocumentTypeDetector()
    return detector.detect(url=url, content=content, filename=filename)


def get_document_type_options() -> list[dict]:
    """모든 문서 유형 옵션 반환 (UI용).

    Returns:
        List of {value, label} dicts
    """
    return [
        {"value": t.value, "label": t.value.replace("-", " ").title()}
        for t in DocumentType
    ]
