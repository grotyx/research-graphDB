"""DOI Fulltext Fetcher.

DOI를 통해 Open Access 논문의 전문(full text)을 가져옵니다.
Crossref API로 메타데이터를 조회하고, Unpaywall API로 PDF URL을 찾습니다.

APIs:
- Crossref: https://api.crossref.org/works/{DOI}
- Unpaywall: https://api.unpaywall.org/v2/{DOI}?email=xxx
"""

import logging
import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DOIMetadata:
    """DOI에서 추출한 메타데이터."""

    doi: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: Optional[int] = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    abstract: str = ""
    publisher: str = ""
    issn: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    references_count: int = 0
    cited_by_count: int = 0
    license_url: str = ""

    # Unpaywall 정보
    is_open_access: bool = False
    oa_status: str = ""  # gold, green, hybrid, bronze, closed
    pdf_url: Optional[str] = None
    oa_location: str = ""  # publisher, repository, etc.

    # PMID/PMCID (있는 경우)
    pmid: Optional[str] = None
    pmcid: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "abstract": self.abstract,
            "publisher": self.publisher,
            "issn": self.issn,
            "subjects": self.subjects,
            "references_count": self.references_count,
            "cited_by_count": self.cited_by_count,
            "license_url": self.license_url,
            "is_open_access": self.is_open_access,
            "oa_status": self.oa_status,
            "pdf_url": self.pdf_url,
            "oa_location": self.oa_location,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
        }


@dataclass
class DOIFullText:
    """DOI로 가져온 전문 결과."""

    doi: str
    metadata: Optional[DOIMetadata] = None
    full_text: str = ""
    pdf_path: Optional[str] = None
    source: str = ""  # crossref, unpaywall, pmc
    fetch_time: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def has_full_text(self) -> bool:
        return bool(self.full_text) or bool(self.pdf_path)

    @property
    def has_metadata(self) -> bool:
        return self.metadata is not None

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "full_text": self.full_text[:500] + "..." if len(self.full_text) > 500 else self.full_text,
            "full_text_length": len(self.full_text),
            "pdf_path": self.pdf_path,
            "source": self.source,
            "fetch_time": self.fetch_time.isoformat() if self.fetch_time else None,
            "has_full_text": self.has_full_text,
            "error": self.error,
        }


class DOIFulltextFetcher:
    """DOI를 통해 논문 메타데이터와 전문을 가져옵니다.

    1. Crossref API로 메타데이터 조회
    2. Unpaywall API로 Open Access PDF URL 조회
    3. PDF 다운로드 또는 PMC 전문 조회

    Example:
        fetcher = DOIFulltextFetcher(email="your@email.com")
        result = await fetcher.fetch("10.1016/j.spinee.2024.01.001")
        if result.has_full_text:
            print(result.full_text)
    """

    CROSSREF_API = "https://api.crossref.org/works/{doi}"
    UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"

    # DOI 정규화 패턴
    DOI_PATTERN = re.compile(r'10\.\d{4,}/[^\s]+')

    def __init__(
        self,
        email: str = "spine.graphrag@research.com",
        timeout: float = 30.0,
        download_dir: Optional[str] = None,
    ):
        """
        Args:
            email: API 요청 시 사용할 이메일 (polite pool 접근용)
            timeout: HTTP 요청 타임아웃 (초)
            download_dir: PDF 다운로드 디렉토리
        """
        self.email = email
        self.timeout = timeout
        self.download_dir = Path(download_dir) if download_dir else None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 가져오기."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": f"SpineGraphRAG/1.0 (mailto:{self.email})",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """HTTP 클라이언트 닫기."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def normalize_doi(self, doi: str) -> str:
        """DOI 정규화.

        다양한 형태의 DOI 입력을 표준 형태로 변환:
        - https://doi.org/10.1016/xxx -> 10.1016/xxx
        - doi:10.1016/xxx -> 10.1016/xxx
        - 10.1016/xxx -> 10.1016/xxx
        """
        doi = doi.strip()

        # URL 형태에서 DOI 추출
        if 'doi.org/' in doi:
            doi = doi.split('doi.org/')[-1]

        # doi: 접두사 제거
        if doi.lower().startswith('doi:'):
            doi = doi[4:]

        # https:// 등 제거
        if doi.startswith('http'):
            match = self.DOI_PATTERN.search(doi)
            if match:
                doi = match.group()

        return doi.strip()

    async def fetch_crossref(self, doi: str) -> Optional[DOIMetadata]:
        """Crossref API에서 메타데이터 조회.

        Args:
            doi: DOI (정규화된 형태)

        Returns:
            DOIMetadata 또는 None
        """
        try:
            client = await self._get_client()
            url = self.CROSSREF_API.format(doi=doi)
            params = {"mailto": self.email}

            logger.debug(f"Fetching Crossref metadata for DOI: {doi}")
            response = await client.get(url, params=params)

            if response.status_code == 404:
                logger.debug(f"DOI not found in Crossref: {doi}")
                return None

            if response.status_code != 200:
                logger.warning(f"Crossref API error for {doi}: {response.status_code}")
                return None

            data = response.json()
            message = data.get("message", {})

            # 저자 추출
            authors = []
            for author in message.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if family:
                    authors.append(f"{family} {given}".strip())

            # 연도 추출
            year = None
            published = message.get("published", {}) or message.get("published-print", {}) or message.get("published-online", {})
            if published:
                date_parts = published.get("date-parts", [[]])[0]
                if date_parts:
                    year = date_parts[0]

            # 초록 추출
            abstract = message.get("abstract", "")
            if abstract:
                # JATS 태그 제거
                abstract = re.sub(r'<[^>]+>', '', abstract)

            # 주제 추출
            subjects = []
            for subj in message.get("subject", []):
                subjects.append(subj)

            metadata = DOIMetadata(
                doi=doi,
                title=message.get("title", [""])[0] if message.get("title") else "",
                authors=authors,
                journal=message.get("container-title", [""])[0] if message.get("container-title") else "",
                year=year,
                volume=message.get("volume", ""),
                issue=message.get("issue", ""),
                pages=message.get("page", ""),
                abstract=abstract,
                publisher=message.get("publisher", ""),
                issn=message.get("ISSN", []),
                subjects=subjects,
                references_count=message.get("references-count", 0),
                cited_by_count=message.get("is-referenced-by-count", 0),
                license_url=message.get("license", [{}])[0].get("URL", "") if message.get("license") else "",
            )

            logger.info(f"Fetched Crossref metadata: {metadata.title[:50]}...")
            return metadata

        except Exception as e:
            logger.error(f"Error fetching Crossref for {doi}: {e}")
            return None

    async def fetch_unpaywall(self, doi: str) -> dict:
        """Unpaywall API에서 Open Access 정보 조회.

        Args:
            doi: DOI (정규화된 형태)

        Returns:
            Open Access 정보 dict
        """
        result = {
            "is_open_access": False,
            "oa_status": "closed",
            "pdf_url": None,
            "oa_location": "",
        }

        try:
            client = await self._get_client()
            url = self.UNPAYWALL_API.format(doi=doi)
            params = {"email": self.email}

            logger.debug(f"Fetching Unpaywall OA info for DOI: {doi}")
            response = await client.get(url, params=params)

            if response.status_code == 404:
                logger.debug(f"DOI not found in Unpaywall: {doi}")
                return result

            if response.status_code != 200:
                logger.warning(f"Unpaywall API error for {doi}: {response.status_code}")
                return result

            data = response.json()

            result["is_open_access"] = data.get("is_oa", False)
            result["oa_status"] = data.get("oa_status", "closed")

            # Best OA location 찾기
            best_location = data.get("best_oa_location", {})
            if best_location:
                result["pdf_url"] = best_location.get("url_for_pdf")
                result["oa_location"] = best_location.get("host_type", "")

                # PDF URL이 없으면 landing page URL 사용
                if not result["pdf_url"]:
                    result["pdf_url"] = best_location.get("url")

            # PMID/PMCID 추출
            if data.get("z_authors"):
                # z_authors에서 추가 정보 확인 (일부 응답에 포함)
                pass

            if result["is_open_access"]:
                logger.info(f"Found OA for {doi}: {result['oa_status']} via {result['oa_location']}")

            return result

        except Exception as e:
            logger.error(f"Error fetching Unpaywall for {doi}: {e}")
            return result

    async def download_pdf(self, pdf_url: str, doi: str) -> Optional[str]:
        """PDF 다운로드.

        Args:
            pdf_url: PDF URL
            doi: DOI (파일명 생성용)

        Returns:
            저장된 PDF 경로 또는 None
        """
        if not self.download_dir:
            logger.debug("No download directory configured")
            return None

        try:
            client = await self._get_client()

            logger.debug(f"Downloading PDF from: {pdf_url}")
            response = await client.get(pdf_url)

            if response.status_code != 200:
                logger.warning(f"PDF download failed: {response.status_code}")
                return None

            # 파일명 생성 (DOI의 특수문자 제거)
            safe_doi = re.sub(r'[^\w\-]', '_', doi)
            pdf_path = self.download_dir / f"{safe_doi}.pdf"

            # 디렉토리 생성
            self.download_dir.mkdir(parents=True, exist_ok=True)

            # PDF 저장
            with open(pdf_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"Downloaded PDF to: {pdf_path}")
            return str(pdf_path)

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return None

    async def fetch(
        self,
        doi: str,
        download_pdf: bool = False,
        fetch_pmc: bool = True,
    ) -> DOIFullText:
        """DOI로 논문 메타데이터와 전문 가져오기.

        Args:
            doi: DOI (다양한 형태 지원)
            download_pdf: PDF 다운로드 여부
            fetch_pmc: PMC에서 전문 가져오기 시도 여부

        Returns:
            DOIFullText 결과
        """
        doi = self.normalize_doi(doi)
        result = DOIFullText(doi=doi, fetch_time=datetime.now())

        # 1. Crossref 메타데이터 조회
        metadata = await self.fetch_crossref(doi)
        if metadata:
            result.metadata = metadata
            result.source = "crossref"
        else:
            result.metadata = DOIMetadata(doi=doi)

        # 2. Unpaywall OA 정보 조회
        oa_info = await self.fetch_unpaywall(doi)
        if result.metadata:
            result.metadata.is_open_access = oa_info["is_open_access"]
            result.metadata.oa_status = oa_info["oa_status"]
            result.metadata.pdf_url = oa_info["pdf_url"]
            result.metadata.oa_location = oa_info["oa_location"]

        # 3. PDF 다운로드 (요청된 경우)
        if download_pdf and oa_info["pdf_url"]:
            pdf_path = await self.download_pdf(oa_info["pdf_url"], doi)
            if pdf_path:
                result.pdf_path = pdf_path
                result.source = "unpaywall"

        # 4. PMC 전문 가져오기 시도 (PMID가 있는 경우)
        if fetch_pmc and result.metadata and result.metadata.pmid:
            try:
                from .pmc_fulltext_fetcher import fetch_pmc_fulltext
                pmc_result = await fetch_pmc_fulltext(result.metadata.pmid)
                if pmc_result.has_full_text:
                    result.full_text = pmc_result.full_text
                    result.source = "pmc"
                    if pmc_result.pmcid:
                        result.metadata.pmcid = pmc_result.pmcid
            except Exception as e:
                logger.debug(f"PMC fetch failed: {e}")

        return result

    async def fetch_batch(
        self,
        dois: list[str],
        concurrency: int = 3,
        delay: float = 1.0,
        download_pdf: bool = False,
    ) -> dict[str, DOIFullText]:
        """여러 DOI 일괄 조회.

        Args:
            dois: DOI 목록
            concurrency: 동시 요청 수
            delay: 요청 간 지연 (초)
            download_pdf: PDF 다운로드 여부

        Returns:
            DOI -> DOIFullText 매핑
        """
        results = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_limit(doi: str) -> tuple[str, DOIFullText]:
            async with semaphore:
                result = await self.fetch(doi, download_pdf=download_pdf)
                await asyncio.sleep(delay)
                return doi, result

        tasks = [fetch_with_limit(doi) for doi in dois]

        for coro in asyncio.as_completed(tasks):
            doi, result = await coro
            results[doi] = result

        # 요약 로그
        oa_count = sum(1 for r in results.values() if r.metadata and r.metadata.is_open_access)
        logger.info(f"DOI batch fetch complete: {oa_count}/{len(dois)} are Open Access")

        return results

    async def get_metadata_only(self, doi: str) -> Optional[DOIMetadata]:
        """메타데이터만 조회 (전문 없이).

        Args:
            doi: DOI

        Returns:
            DOIMetadata 또는 None
        """
        doi = self.normalize_doi(doi)

        # Crossref + Unpaywall 병렬 조회
        metadata_task = self.fetch_crossref(doi)
        oa_task = self.fetch_unpaywall(doi)

        metadata, oa_info = await asyncio.gather(metadata_task, oa_task)

        if metadata:
            metadata.is_open_access = oa_info["is_open_access"]
            metadata.oa_status = oa_info["oa_status"]
            metadata.pdf_url = oa_info["pdf_url"]
            metadata.oa_location = oa_info["oa_location"]

        return metadata

    async def search_by_bibliographic(
        self,
        title: str = "",
        authors: Optional[list[str]] = None,
        year: Optional[int] = None,
        max_results: int = 3,
    ) -> Optional[DOIMetadata]:
        """Crossref 서지 검색 (title + author + year).

        DOI 없이 제목/저자 정보만으로 Crossref에서 논문을 검색합니다.
        query.bibliographic 파라미터로 통합 관련성 검색을 수행합니다.

        Args:
            title: 논문 제목 또는 키워드
            authors: 저자 목록 (첫 번째 저자가 검색에 사용됨)
            year: 출판 연도 (필터링용)
            max_results: 평가할 최대 결과 수

        Returns:
            가장 관련성 높은 DOIMetadata 또는 None
        """
        if not title and not authors:
            return None

        try:
            client = await self._get_client()

            query_parts = []
            if title:
                query_parts.append(title)
            if authors:
                query_parts.append(authors[0])

            query_str = " ".join(query_parts)

            params = {
                "query.bibliographic": query_str,
                "rows": max_results,
                "mailto": self.email,
            }

            if year:
                params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"

            url = "https://api.crossref.org/works"
            logger.debug(f"Crossref bibliographic search: {query_str[:80]}")

            response = await client.get(url, params=params)

            if response.status_code != 200:
                logger.warning(f"Crossref search API error: {response.status_code}")
                return None

            data = response.json()
            items = data.get("message", {}).get("items", [])

            if not items:
                logger.debug(f"No Crossref results for: {query_str[:50]}")
                return None

            best = items[0]
            doi = best.get("DOI", "")

            if not doi:
                return None

            metadata = await self.fetch_crossref(doi)

            if metadata:
                logger.info(f"Crossref bibliographic search found: {metadata.title[:50]}... (DOI: {doi})")

            return metadata

        except Exception as e:
            logger.warning(f"Crossref bibliographic search failed: {e}")
            return None


# 편의 함수
async def fetch_by_doi(doi: str, email: str = "spine.graphrag@research.com") -> DOIFullText:
    """단일 DOI 조회.

    Args:
        doi: DOI
        email: API 요청용 이메일

    Returns:
        DOIFullText
    """
    fetcher = DOIFulltextFetcher(email=email)
    try:
        return await fetcher.fetch(doi)
    finally:
        await fetcher.close()


async def get_doi_metadata(doi: str, email: str = "spine.graphrag@research.com") -> Optional[DOIMetadata]:
    """DOI 메타데이터만 조회.

    Args:
        doi: DOI
        email: API 요청용 이메일

    Returns:
        DOIMetadata 또는 None
    """
    fetcher = DOIFulltextFetcher(email=email)
    try:
        return await fetcher.get_metadata_only(doi)
    finally:
        await fetcher.close()
