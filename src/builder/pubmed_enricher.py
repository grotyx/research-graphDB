"""PubMed Bibliographic Enrichment Module.

PDF 처리 시 PubMed에서 서지 정보를 자동으로 가져와 메타데이터를 강화합니다.

Usage:
    enricher = PubMedEnricher()

    # DOI로 검색 (가장 정확)
    metadata = await enricher.enrich_by_doi("10.1016/j.spinee.2023.01.001")

    # 제목으로 검색 (fallback)
    metadata = await enricher.enrich_by_title("TLIF vs PLIF outcomes")

    # 자동 검색 (DOI → Title 순서로 시도)
    metadata = await enricher.auto_enrich(title="...", doi="...")
"""

from __future__ import annotations

import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any, TypeVar, TYPE_CHECKING
from datetime import datetime
import logging

try:
    from external.pubmed_client import PubMedClient, PaperMetadata, PubMedError, APIError
    from builder.evidence_classifier import EvidenceLevelClassifier, get_evidence_level_from_publication_type
    from core.exceptions import ValidationError, ErrorCode
except ImportError:
    from src.external.pubmed_client import PubMedClient, PaperMetadata, PubMedError, APIError
    from src.builder.evidence_classifier import EvidenceLevelClassifier, get_evidence_level_from_publication_type
    from src.core.exceptions import ValidationError, ErrorCode

if TYPE_CHECKING:
    from builder.doi_fulltext_fetcher import DOIMetadata

logger = logging.getLogger(__name__)

# Type variable for generic async wrapper
T = TypeVar('T')

# Maximum allowed query length to prevent abuse
MAX_QUERY_LENGTH = 500
# Characters that could be dangerous in queries
DANGEROUS_CHARS_PATTERN = re.compile(r'[<>;\'"\\`\x00-\x1f]')


@dataclass
class BibliographicMetadata:
    """서지 정보 데이터 클래스.

    PubMed에서 가져온 표준화된 서지 정보를 저장합니다.

    Attributes:
        pmid: PubMed ID
        doi: Digital Object Identifier
        title: 논문 제목 (PubMed 표준화)
        authors: 저자 목록 (LastName FirstName 형식)
        journal: 저널명 (전체 이름)
        journal_abbrev: 저널 약어 (ISO 표준)
        year: 출판 연도
        month: 출판 월 (optional)
        volume: 권 번호
        issue: 호 번호
        pages: 페이지 범위
        abstract: 초록 전문
        mesh_terms: MeSH 용어 목록 (의학 주제 분류)
        keywords: 저자 키워드
        publication_types: 출판 유형 (RCT, Review, Meta-Analysis 등)
        language: 출판 언어
        affiliation: 제1저자 소속 기관
        citation_count: 인용 횟수 (available if fetched)
        enriched_at: 서지 정보 수집 시각
        source: 데이터 출처 ("pubmed")
        confidence: 매칭 신뢰도 (0.0 ~ 1.0)
    """
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    journal_abbrev: str = ""
    year: int = 0
    month: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    abstract: str = ""
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    publication_types: List[str] = field(default_factory=list)
    language: str = "eng"
    affiliation: Optional[str] = None
    citation_count: Optional[int] = None
    enriched_at: Optional[datetime] = None
    source: str = "pubmed"
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "pmid": self.pmid,
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "journal_abbrev": self.journal_abbrev,
            "year": self.year,
            "month": self.month,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "abstract": self.abstract,
            "mesh_terms": self.mesh_terms,
            "keywords": self.keywords,
            "publication_types": self.publication_types,
            "language": self.language,
            "affiliation": self.affiliation,
            "citation_count": self.citation_count,
            "enriched_at": self.enriched_at.isoformat() if self.enriched_at else None,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_pubmed(cls, paper: PaperMetadata, confidence: float = 1.0) -> BibliographicMetadata:
        """PaperMetadata에서 BibliographicMetadata 생성."""
        return cls(
            pmid=paper.pmid,
            doi=paper.doi,
            title=paper.title,
            authors=paper.authors,
            journal=paper.journal,
            year=paper.year,
            abstract=paper.abstract,
            mesh_terms=paper.mesh_terms,
            publication_types=paper.publication_types or [],
            enriched_at=datetime.now(),
            source="pubmed",
            confidence=confidence,
        )

    @classmethod
    def from_doi_metadata(cls, doi_meta: DOIMetadata, confidence: float = 0.8) -> BibliographicMetadata:
        """DOIMetadata에서 BibliographicMetadata 생성.

        Crossref/Unpaywall 기반 메타데이터를 BibliographicMetadata 형식으로 변환합니다.
        PubMed 데이터에 비해 mesh_terms, publication_types 등이 부재합니다.

        Args:
            doi_meta: DOIFulltextFetcher에서 가져온 DOIMetadata
            confidence: 매칭 신뢰도 (기본 0.8, PubMed 1.0보다 낮음)

        Returns:
            BibliographicMetadata
        """
        return cls(
            pmid=doi_meta.pmid,
            doi=doi_meta.doi,
            title=doi_meta.title,
            authors=doi_meta.authors,
            journal=doi_meta.journal,
            year=doi_meta.year or 0,
            volume=doi_meta.volume or None,
            issue=doi_meta.issue or None,
            pages=doi_meta.pages or None,
            abstract=doi_meta.abstract,
            mesh_terms=[],
            keywords=doi_meta.subjects if doi_meta.subjects else [],
            publication_types=[],
            citation_count=doi_meta.cited_by_count if doi_meta.cited_by_count else None,
            enriched_at=datetime.now(),
            source="crossref",
            confidence=confidence,
        )


class PubMedEnricher:
    """PubMed 서지 정보 강화 클래스.

    PDF에서 추출한 메타데이터를 PubMed의 표준 서지 정보로 강화합니다.

    검색 우선순위:
    1. DOI로 검색 (가장 정확)
    2. PMID로 검색 (직접 조회)
    3. Title + Author로 검색 (fallback)

    Example:
        enricher = PubMedEnricher(email="your@email.com")

        # DOI로 검색
        result = await enricher.enrich_by_doi("10.1016/j.spinee.2023.01.001")

        # 자동 검색
        result = await enricher.auto_enrich(
            title="Comparison of TLIF and PLIF",
            authors=["Kim", "Park"],
            doi="10.1016/j.spinee.2023.01.001"
        )

        if result:
            print(f"PMID: {result.pmid}")
            print(f"MeSH: {result.mesh_terms}")
    """

    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """PubMedEnricher 초기화.

        Args:
            email: NCBI 권장 연락처 이메일
            api_key: NCBI API 키 (rate limit 향상)
            timeout: API 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수
        """
        self.client = PubMedClient(email=email, api_key=api_key)
        self.timeout = timeout
        self.max_retries = max_retries
        # Log initialization without exposing API key
        logger.info(
            f"PubMedEnricher initialized (email={email or 'not set'}, "
            f"api_key={'***' if api_key else 'not set'}, timeout={timeout}s)"
        )

    async def _run_client_method(
        self,
        method: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """PubMed 클라이언트 메서드를 비동기적으로 실행 (타임아웃 보호).

        모든 동기 PubMedClient 호출을 래핑하여:
        1. 비동기 실행 (asyncio.to_thread)
        2. 타임아웃 보호 (asyncio.wait_for)

        Args:
            method: 실행할 PubMedClient 메서드
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            메서드 실행 결과

        Raises:
            asyncio.TimeoutError: 타임아웃 초과 시
        """
        return await asyncio.wait_for(
            asyncio.to_thread(method, *args, **kwargs),
            timeout=self.timeout
        )

    def _sanitize_query_input(self, query: str) -> str:
        """쿼리 입력 검증 및 정제.

        잠재적으로 위험한 문자를 제거하고 길이를 제한합니다.

        Args:
            query: 원본 쿼리 문자열

        Returns:
            정제된 쿼리 문자열

        Raises:
            ValueError: 쿼리가 비어있거나 너무 긴 경우
        """
        if not query or not query.strip():
            raise ValidationError(message="Query cannot be empty", error_code=ErrorCode.VAL_INVALID_VALUE)

        # 위험한 문자 제거
        sanitized = DANGEROUS_CHARS_PATTERN.sub('', query)

        # 길이 제한
        if len(sanitized) > MAX_QUERY_LENGTH:
            logger.warning(
                f"Query truncated from {len(sanitized)} to {MAX_QUERY_LENGTH} chars"
            )
            sanitized = sanitized[:MAX_QUERY_LENGTH]

        # 앞뒤 공백 제거
        sanitized = sanitized.strip()

        if not sanitized:
            raise ValidationError(message="Query contains only invalid characters", error_code=ErrorCode.VAL_INVALID_VALUE)

        return sanitized

    async def enrich_by_doi(self, doi: str) -> Optional[BibliographicMetadata]:
        """DOI로 PubMed 서지 정보 조회.

        DOI는 논문의 고유 식별자이므로 가장 정확한 검색 방법입니다.

        Args:
            doi: Digital Object Identifier (예: "10.1016/j.spinee.2023.01.001")

        Returns:
            BibliographicMetadata 또는 None (검색 실패 시)
        """
        if not doi:
            return None

        # DOI 정규화 (https://doi.org/ 제거)
        doi = self._normalize_doi(doi)

        try:
            # 입력 검증
            sanitized_doi = self._sanitize_query_input(doi)

            # DOI로 PubMed 검색 (타임아웃 보호 적용)
            query = f"{sanitized_doi}[DOI]"
            pmids = await self._run_client_method(
                self.client.search, query, max_results=1
            )

            if not pmids:
                logger.debug(f"No PubMed results for DOI: {sanitized_doi}")
                return None

            pmid = pmids[0]
            paper = await self._run_client_method(
                self.client.fetch_paper_details, pmid
            )

            logger.info(f"PubMed enrichment successful: DOI={sanitized_doi}, PMID={pmid}")
            return BibliographicMetadata.from_pubmed(paper, confidence=1.0)

        except asyncio.TimeoutError:
            logger.warning(f"PubMed DOI search timed out after {self.timeout}s: {doi}")
            return None
        except ValidationError as e:
            logger.warning(f"Invalid DOI input: {e}")
            return None
        except PubMedError as e:
            logger.warning(f"PubMed DOI search failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in DOI search: {e}", exc_info=True)
            return None

    async def enrich_by_pmid(self, pmid: str) -> Optional[BibliographicMetadata]:
        """PMID로 PubMed 서지 정보 조회.

        Args:
            pmid: PubMed ID (예: "12345678")

        Returns:
            BibliographicMetadata 또는 None
        """
        if not pmid:
            return None

        # PMID 정규화 (숫자만 추출)
        pmid = re.sub(r'\D', '', str(pmid))

        if not pmid:
            return None

        try:
            # 타임아웃 보호 적용
            paper = await self._run_client_method(
                self.client.fetch_paper_details, pmid
            )
            logger.info(f"PubMed enrichment successful: PMID={pmid}")
            return BibliographicMetadata.from_pubmed(paper, confidence=1.0)

        except asyncio.TimeoutError:
            logger.warning(f"PubMed PMID fetch timed out after {self.timeout}s: {pmid}")
            return None
        except PubMedError as e:
            logger.warning(f"PubMed PMID fetch failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in PMID fetch: {e}", exc_info=True)
            return None

    async def enrich_by_title(
        self,
        title: str,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None
    ) -> Optional[BibliographicMetadata]:
        """제목으로 PubMed 서지 정보 조회.

        DOI가 없는 경우의 fallback 검색 방법입니다.
        제목이 정확히 일치하는지 확인하여 신뢰도를 결정합니다.

        Args:
            title: 논문 제목
            authors: 저자 목록 (선택, 검색 정확도 향상)
            year: 출판 연도 (선택, 검색 정확도 향상)
            journal: 저널명 (선택, 검색 정확도 향상)

        Returns:
            BibliographicMetadata 또는 None
        """
        if not title or len(title) < 10:
            return None

        try:
            # 입력 검증
            sanitized_title = self._sanitize_query_input(title)

            # 검색 쿼리 구성
            query_parts = [f'"{sanitized_title}"[Title]']

            # 저자 추가 (첫 번째 저자만)
            if authors and len(authors) > 0:
                first_author = self._extract_last_name(authors[0])
                if first_author:
                    # 저자명도 검증
                    try:
                        sanitized_author = self._sanitize_query_input(first_author)
                        query_parts.append(f"{sanitized_author}[Author]")
                    except ValidationError:
                        pass  # 잘못된 저자명은 무시

            # 연도 추가
            if year:
                try:
                    year_int = int(year)
                    if year_int > 1900:
                        query_parts.append(f"{year_int}[PDAT]")
                except (ValueError, TypeError):
                    pass  # Invalid year format, skip

            # 저널 추가
            if journal:
                try:
                    sanitized_journal = self._sanitize_query_input(journal)
                    query_parts.append(f'"{sanitized_journal}"[Journal]')
                except ValidationError:
                    pass  # 잘못된 저널명은 무시

            query = " AND ".join(query_parts)
            logger.debug(f"PubMed title search query: {query}")

            # 검색 실행 (타임아웃 보호)
            pmids = await self._run_client_method(
                self.client.search, query, max_results=5
            )

            if not pmids:
                # 엄격한 검색 실패 시 제목만으로 재검색
                query = f'"{sanitized_title}"[Title]'
                pmids = await self._run_client_method(
                    self.client.search, query, max_results=5
                )

            if not pmids:
                logger.debug(f"No PubMed results for title: {sanitized_title[:50]}...")
                return None

            # 첫 번째 결과 가져오기 (타임아웃 보호)
            paper = await self._run_client_method(
                self.client.fetch_paper_details, pmids[0]
            )

            # 제목 유사도 계산
            confidence = self._calculate_title_similarity(title, paper.title)

            if confidence < 0.7:
                logger.warning(
                    f"Low confidence match: query='{title[:50]}...' vs "
                    f"result='{paper.title[:50]}...' (confidence={confidence:.2f})"
                )

            logger.info(f"PubMed enrichment by title: PMID={paper.pmid}, confidence={confidence:.2f}")
            return BibliographicMetadata.from_pubmed(paper, confidence=confidence)

        except asyncio.TimeoutError:
            logger.warning(f"PubMed title search timed out after {self.timeout}s")
            return None
        except ValidationError as e:
            logger.warning(f"Invalid title input: {e}")
            return None
        except PubMedError as e:
            logger.warning(f"PubMed title search failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in title search: {e}", exc_info=True)
            return None

    async def auto_enrich(
        self,
        title: Optional[str] = None,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        doi: Optional[str] = None,
        pmid: Optional[str] = None
    ) -> Optional[BibliographicMetadata]:
        """자동 서지 정보 강화.

        우선순위:
        1. PMID (직접 조회)
        2. DOI (고유 식별자)
        3. Title + Authors (텍스트 검색)

        Args:
            title: 논문 제목
            authors: 저자 목록
            year: 출판 연도
            journal: 저널명
            doi: DOI
            pmid: PubMed ID

        Returns:
            BibliographicMetadata 또는 None
        """
        # 1. PMID로 직접 조회
        if pmid:
            result = await self.enrich_by_pmid(pmid)
            if result:
                return result

        # 2. DOI로 검색
        if doi:
            result = await self.enrich_by_doi(doi)
            if result:
                return result

        # 3. Title로 검색
        if title:
            result = await self.enrich_by_title(
                title=title,
                authors=authors,
                year=year,
                journal=journal
            )
            if result:
                return result

        logger.info("PubMed enrichment failed: no valid identifiers")
        return None

    async def enrich_batch(
        self,
        papers: List[dict],
        batch_size: int = 10,
        delay: float = 0.5
    ) -> List[Optional[BibliographicMetadata]]:
        """여러 논문의 서지 정보를 일괄 강화.

        Args:
            papers: 논문 정보 리스트 [{"title": ..., "doi": ..., ...}, ...]
            batch_size: 동시 요청 수
            delay: 배치 간 딜레이 (초)

        Returns:
            BibliographicMetadata 리스트 (None 포함 가능)
        """
        results = []

        for i in range(0, len(papers), batch_size):
            batch = papers[i:i + batch_size]

            # 배치 내 동시 처리
            tasks = [
                self.auto_enrich(
                    title=p.get("title"),
                    authors=p.get("authors"),
                    year=p.get("year"),
                    journal=p.get("journal"),
                    doi=p.get("doi"),
                    pmid=p.get("pmid")
                )
                for p in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning(f"Batch enrichment error: {result}")
                    results.append(None)
                else:
                    results.append(result)

            # Rate limiting
            if i + batch_size < len(papers):
                await asyncio.sleep(delay)

        return results

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _normalize_doi(self, doi: str) -> str:
        """DOI 정규화.

        다양한 DOI 형식을 표준 형식으로 변환합니다.
        - https://doi.org/10.1016/... → 10.1016/...
        - doi:10.1016/... → 10.1016/...
        """
        if not doi:
            return ""

        doi = doi.strip()

        # URL 형식 제거
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)

        # doi: 접두사 제거
        doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)

        return doi.strip()

    def _extract_last_name(self, author: str) -> str:
        """저자명에서 성(Last Name) 추출.

        다양한 저자명 형식을 처리합니다:
        - "Kim JH" → "Kim"
        - "John H. Kim" → "Kim"
        - "Kim, John H." → "Kim"
        """
        if not author:
            return ""

        author = author.strip()

        # "Kim, John" 형식
        if "," in author:
            return author.split(",")[0].strip()

        # "John Kim" 또는 "Kim JH" 형식
        parts = author.split()
        if len(parts) >= 2:
            # 마지막 부분이 이니셜인지 확인
            if len(parts[-1]) <= 3 and parts[-1].isupper():
                return parts[0]  # "Kim JH" → "Kim"
            else:
                return parts[-1]  # "John Kim" → "Kim"

        return parts[0] if parts else ""

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """두 제목의 유사도 계산 (0.0 ~ 1.0).

        Jaccard similarity를 사용합니다.
        """
        if not title1 or not title2:
            return 0.0

        # 정규화
        def normalize(s):
            s = s.lower()
            s = re.sub(r'[^\w\s]', ' ', s)
            return set(s.split())

        words1 = normalize(title1)
        words2 = normalize(title2)

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def get_evidence_level_from_publication_type(
        self,
        publication_types: List[str]
    ) -> Optional[str]:
        """Publication type에서 근거 수준 추정.

        PubMed의 publication_types를 기반으로 근거 수준을 추정합니다.
        내부적으로 EvidenceLevelClassifier를 사용합니다.

        Args:
            publication_types: PubMed publication types 목록

        Returns:
            근거 수준 ("1a", "1b", "2a", "2b", "3", "4") 또는 None
        """
        return get_evidence_level_from_publication_type(publication_types)


    # =========================================================================
    # Citation Search Methods (v3.2+ Important Citations)
    # =========================================================================

    async def search_cited_paper(
        self,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
        title_keywords: Optional[str] = None,
        journal: Optional[str] = None,
        max_results: int = 5
    ) -> List[BibliographicMetadata]:
        """인용 정보로 PubMed에서 논문 검색.

        Discussion에서 추출한 인용 정보(저자, 연도)로 원본 논문을 찾습니다.

        Args:
            authors: 저자 성씨 목록 (예: ["Kim", "Park"])
            year: 출판 연도
            title_keywords: 제목에 포함된 키워드 (선택)
            journal: 저널명 (선택)
            max_results: 최대 결과 수

        Returns:
            BibliographicMetadata 목록 (빈 리스트 가능)

        Example:
            results = await enricher.search_cited_paper(
                authors=["Kim"],
                year=2023,
                title_keywords="TLIF lumbar fusion"
            )
        """
        if not authors and not title_keywords:
            logger.warning("Citation search requires at least authors or title_keywords")
            return []

        try:
            query_parts = []

            # 저자 추가 (첫 번째 저자)
            if authors and len(authors) > 0:
                first_author = authors[0]
                try:
                    sanitized_author = self._sanitize_query_input(first_author)
                    query_parts.append(f"{sanitized_author}[Author]")
                except ValidationError:
                    pass

            # 연도 추가
            if year:
                try:
                    year_int = int(year)
                    if 1900 < year_int < 2100:
                        query_parts.append(f"{year_int}[PDAT]")
                except (ValueError, TypeError):
                    pass  # Invalid year format, skip

            # 제목 키워드 추가
            if title_keywords:
                try:
                    sanitized_keywords = self._sanitize_query_input(title_keywords)
                    # 키워드를 단어별로 분리하여 AND 검색
                    keywords = sanitized_keywords.split()[:5]  # 최대 5개 키워드
                    keyword_query = " AND ".join([f"{kw}[Title]" for kw in keywords])
                    query_parts.append(f"({keyword_query})")
                except ValidationError:
                    pass

            # 저널 추가
            if journal:
                try:
                    sanitized_journal = self._sanitize_query_input(journal)
                    query_parts.append(f'"{sanitized_journal}"[Journal]')
                except ValidationError:
                    pass

            if not query_parts:
                logger.warning("No valid query parts for citation search")
                return []

            query = " AND ".join(query_parts)
            logger.debug(f"Citation search query: {query}")

            # 검색 실행
            pmids = await self._run_client_method(
                self.client.search, query, max_results=max_results
            )

            if not pmids:
                logger.debug(f"No PubMed results for citation query: {query}")
                return []

            # 결과 가져오기
            results = []
            for pmid in pmids:
                try:
                    paper = await self._run_client_method(
                        self.client.fetch_paper_details, pmid
                    )
                    # 저자+연도 매칭 신뢰도 계산
                    confidence = self._calculate_citation_match_confidence(
                        authors=authors,
                        year=year,
                        paper=paper
                    )
                    metadata = BibliographicMetadata.from_pubmed(paper, confidence=confidence)
                    results.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to fetch paper details for PMID {pmid}: {e}")
                    continue

            # 신뢰도 순으로 정렬
            results.sort(key=lambda x: x.confidence, reverse=True)

            logger.info(f"Citation search found {len(results)} papers")
            return results

        except asyncio.TimeoutError:
            logger.warning(f"Citation search timed out after {self.timeout}s")
            return []
        except Exception as e:
            logger.error(f"Citation search error: {e}", exc_info=True)
            return []

    async def search_and_enrich_citation(
        self,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
        title: Optional[str] = None,
        journal: Optional[str] = None,
        min_confidence: float = 0.7
    ) -> Optional[BibliographicMetadata]:
        """인용 정보로 가장 일치하는 논문 하나를 찾아 반환.

        search_cited_paper의 결과 중 신뢰도가 가장 높고
        min_confidence 이상인 논문만 반환합니다.

        Args:
            authors: 저자 성씨 목록
            year: 출판 연도
            title: 논문 제목 (부분 일치)
            journal: 저널명
            min_confidence: 최소 신뢰도 (기본 0.7)

        Returns:
            BibliographicMetadata 또는 None (매칭 실패 시)

        Example:
            cited_paper = await enricher.search_and_enrich_citation(
                authors=["Kim"],
                year=2023,
                min_confidence=0.8
            )
            if cited_paper:
                print(f"Found: {cited_paper.title}")
        """
        results = await self.search_cited_paper(
            authors=authors,
            year=year,
            title_keywords=title,
            journal=journal,
            max_results=3
        )

        if not results:
            return None

        # 가장 높은 신뢰도 결과
        best_match = results[0]

        if best_match.confidence >= min_confidence:
            logger.info(
                f"Citation match found: '{best_match.title[:50]}...' "
                f"(PMID={best_match.pmid}, confidence={best_match.confidence:.2f})"
            )
            return best_match
        else:
            logger.debug(
                f"Best citation match below threshold: "
                f"confidence={best_match.confidence:.2f} < {min_confidence}"
            )
            return None

    def _calculate_citation_match_confidence(
        self,
        authors: Optional[List[str]],
        year: Optional[int],
        paper: PaperMetadata
    ) -> float:
        """인용 정보와 PubMed 결과의 매칭 신뢰도 계산.

        Args:
            authors: 검색에 사용한 저자 목록
            year: 검색에 사용한 연도
            paper: PubMed 결과

        Returns:
            신뢰도 (0.0 ~ 1.0)
        """
        score = 0.0
        max_score = 0.0

        # 연도 일치 (40%)
        if year:
            max_score += 0.4
            if paper.year == year:
                score += 0.4
            elif abs(paper.year - year) == 1:  # 1년 차이 허용
                score += 0.2

        # 저자 일치 (60%)
        if authors:
            max_score += 0.6
            paper_authors_lower = [a.lower() for a in paper.authors]

            # 각 검색 저자에 대해 확인
            matching_authors = 0
            for search_author in authors:
                search_lower = search_author.lower()
                # PubMed 저자 목록에서 검색 저자 포함 여부
                for paper_author in paper_authors_lower:
                    if search_lower in paper_author or paper_author.startswith(search_lower):
                        matching_authors += 1
                        break

            if len(authors) > 0:
                author_ratio = matching_authors / len(authors)
                score += 0.6 * author_ratio

        if max_score == 0:
            return 0.5  # 정보 없으면 중간값

        return score / max_score


# Convenience function
async def enrich_paper_metadata(
    title: Optional[str] = None,
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    email: Optional[str] = None
) -> Optional[BibliographicMetadata]:
    """논문 메타데이터 강화 편의 함수.

    Args:
        title: 논문 제목
        doi: DOI
        pmid: PubMed ID
        authors: 저자 목록
        year: 출판 연도
        email: NCBI 연락처 이메일

    Returns:
        BibliographicMetadata 또는 None

    Example:
        metadata = await enrich_paper_metadata(
            doi="10.1016/j.spinee.2023.01.001"
        )
    """
    enricher = PubMedEnricher(email=email)
    return await enricher.auto_enrich(
        title=title,
        doi=doi,
        pmid=pmid,
        authors=authors,
        year=year
    )
