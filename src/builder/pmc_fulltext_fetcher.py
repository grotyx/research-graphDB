"""PMC Full Text Fetcher.

Fetches full text from PubMed Central (PMC) for Open Access papers.
Uses the BioC API to retrieve structured full text content.

API Documentation: https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/
"""

import logging
import httpx
from dataclasses import dataclass, field
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)


async def _async_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = 3,
    backoff_base: int = 2,
    **kwargs,
) -> httpx.Response:
    """Async retry wrapper for httpx requests.

    Args:
        client: httpx AsyncClient instance
        method: HTTP method ('get', 'post', etc.)
        url: Request URL
        max_retries: Maximum number of attempts
        backoff_base: Base for exponential backoff
        **kwargs: Additional arguments passed to the request method

    Returns:
        httpx.Response

    Raises:
        Last exception if all retries fail
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            response = await getattr(client, method)(url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min(backoff_base ** attempt, 30)
                logger.warning(
                    f"HTTP request failed (attempt {attempt + 1}/{max_retries}): {e}, "
                    f"retrying in {wait}s"
                )
                await asyncio.sleep(wait)
    raise last_error


@dataclass
class PMCSection:
    """A section from the full text."""

    section_type: str  # e.g., "INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL"
    title: str
    text: str

    def to_dict(self) -> dict:
        return {
            "section_type": self.section_type,
            "title": self.title,
            "text": self.text,
        }


@dataclass
class PMCFullText:
    """Full text content from PMC."""

    pmid: str
    pmcid: Optional[str] = None
    title: str = ""
    abstract: str = ""
    sections: list[PMCSection] = field(default_factory=list)
    is_open_access: bool = False

    @property
    def has_full_text(self) -> bool:
        """Check if full text sections are available."""
        return len(self.sections) > 0

    @property
    def full_text(self) -> str:
        """Get concatenated full text."""
        parts = []
        if self.abstract:
            parts.append(f"Abstract: {self.abstract}")
        for section in self.sections:
            if section.title:
                parts.append(f"\n{section.title}:\n{section.text}")
            else:
                parts.append(section.text)
        return "\n\n".join(parts)

    def get_section(self, section_type: str) -> Optional[PMCSection]:
        """Get a specific section by type."""
        for section in self.sections:
            if section.section_type.upper() == section_type.upper():
                return section
        return None

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "title": self.title,
            "abstract": self.abstract,
            "sections": [s.to_dict() for s in self.sections],
            "is_open_access": self.is_open_access,
            "has_full_text": self.has_full_text,
        }


class PMCFullTextFetcher:
    """Fetches full text from PMC Open Access subset.

    Uses the BioC API which provides structured full text for
    Open Access papers in PubMed Central.

    Example:
        fetcher = PMCFullTextFetcher()
        result = await fetcher.fetch_fulltext("12345678")
        if result.has_full_text:
            print(result.full_text)
    """

    # BioC API endpoint for PMC Open Access
    BIOC_API_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{identifier}/unicode"

    # Section type mapping (BioC infons to standard names)
    SECTION_TYPE_MAP = {
        "front": "FRONT",
        "abstract": "ABSTRACT",
        "intro": "INTRO",
        "introduction": "INTRO",
        "background": "INTRO",
        "methods": "METHODS",
        "materials and methods": "METHODS",
        "materials & methods": "METHODS",
        "patients and methods": "METHODS",
        "subjects and methods": "METHODS",
        "study design": "METHODS",
        "results": "RESULTS",
        "findings": "RESULTS",
        "discussion": "DISCUSS",
        "conclusions": "CONCL",
        "conclusion": "CONCL",
        "summary": "CONCL",
        "acknowledgments": "ACK",
        "acknowledgements": "ACK",
        "references": "REF",
        "supplementary": "SUPP",
        "supplement": "SUPP",
        "appendix": "SUPP",
    }

    def __init__(self, timeout: float = 30.0):
        """Initialize fetcher.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _normalize_section_type(self, section_name: str) -> str:
        """Normalize section type to standard name."""
        if not section_name:
            return "OTHER"

        section_lower = section_name.lower().strip()

        # Check direct mapping
        if section_lower in self.SECTION_TYPE_MAP:
            return self.SECTION_TYPE_MAP[section_lower]

        # Check partial matches
        for key, value in self.SECTION_TYPE_MAP.items():
            if key in section_lower or section_lower in key:
                return value

        return "OTHER"

    def _parse_bioc_response(self, data: dict | list, pmid: str) -> PMCFullText:
        """Parse BioC JSON response into PMCFullText.

        Args:
            data: BioC JSON response (can be list of collections or dict)
            pmid: Original PMID

        Returns:
            PMCFullText object with parsed content
        """
        result = PMCFullText(pmid=pmid, is_open_access=True)

        # Handle list response (BioC API returns list of collections)
        if isinstance(data, list):
            if not data:
                result.is_open_access = False
                return result
            data = data[0]  # Get the first collection

        # Get documents from response
        documents = data.get("documents", [])
        if not documents:
            result.is_open_access = False
            return result

        doc = documents[0]

        # Process passages (sections)
        passages = doc.get("passages", [])

        # Extract PMCID - first try doc.infons, then first passage infons
        doc_infons = doc.get("infons", {})
        result.pmcid = doc_infons.get("pmcid") or doc_infons.get("pmc")

        # If not found in doc infons, check first passage infons (BioC API format)
        if not result.pmcid and passages:
            first_passage_infons = passages[0].get("infons", {})
            result.pmcid = (
                first_passage_infons.get("article-id_pmc") or
                first_passage_infons.get("pmcid") or
                first_passage_infons.get("pmc")
            )
        current_section_texts = {}  # section_type -> list of texts

        for passage in passages:
            passage_infons = passage.get("infons", {})
            section_type = passage_infons.get("section_type", "")
            section_title = passage_infons.get("section", "") or passage_infons.get("title", "")
            text = passage.get("text", "").strip()

            if not text:
                continue

            # Handle title (can be type="title" or section_type="TITLE")
            if not result.title and (
                passage_infons.get("type") == "title" or
                section_type.upper() == "TITLE"
            ):
                result.title = text
                continue

            # Handle abstract
            if section_type.lower() == "abstract" or passage_infons.get("type") == "abstract":
                if result.abstract:
                    result.abstract += " " + text
                else:
                    result.abstract = text
                continue

            # Normalize section type
            normalized_type = self._normalize_section_type(section_type or section_title)

            # Skip references and front matter for main content
            if normalized_type in ("REF", "FRONT", "ACK"):
                continue

            # Accumulate text by section type
            if normalized_type not in current_section_texts:
                current_section_texts[normalized_type] = {
                    "title": section_title,
                    "texts": []
                }
            current_section_texts[normalized_type]["texts"].append(text)

        # Create sections from accumulated texts
        section_order = ["INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL", "OTHER", "SUPP"]

        for section_type in section_order:
            if section_type in current_section_texts:
                section_data = current_section_texts[section_type]
                combined_text = " ".join(section_data["texts"])

                # Only include sections with meaningful content
                if len(combined_text) > 50:
                    result.sections.append(PMCSection(
                        section_type=section_type,
                        title=section_data["title"],
                        text=combined_text
                    ))

        return result

    async def fetch_fulltext(self, pmid: str) -> PMCFullText:
        """Fetch full text for a paper by PMID.

        Args:
            pmid: PubMed ID

        Returns:
            PMCFullText object (check has_full_text to see if successful)
        """
        result = PMCFullText(pmid=pmid)

        try:
            client = await self._get_client()
            url = self.BIOC_API_URL.format(identifier=pmid)

            logger.debug(f"Fetching PMC full text for PMID {pmid}")
            try:
                response = await _async_request_with_retry(
                    client, "get", url,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Not in PMC Open Access - this is normal for non-OA papers
                    logger.debug(f"PMID {pmid} not in PMC Open Access subset")
                    return result
                logger.warning(f"PMC API error for PMID {pmid}: {e.response.status_code}")
                return result
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"Timeout/connection error fetching PMC full text for PMID {pmid}: {e}")
                return result

            # Check content type - PMC may return HTML error page instead of JSON
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                logger.debug(f"PMID {pmid} not in PMC Open Access (non-JSON response)")
                return result

            try:
                data = response.json()
            except Exception as json_err:
                logger.debug(f"PMID {pmid} not in PMC Open Access (invalid JSON: {json_err})")
                return result

            result = self._parse_bioc_response(data, pmid)

            if result.has_full_text:
                logger.info(
                    f"Fetched full text for PMID {pmid} (PMCID: {result.pmcid}): "
                    f"{len(result.sections)} sections"
                )

            return result

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching PMC full text for PMID {pmid}")
            return result
        except Exception as e:
            logger.error(f"Error fetching PMC full text for PMID {pmid}: {e}", exc_info=True)
            return result

    async def fetch_fulltext_batch(
        self,
        pmids: list[str],
        concurrency: int = 3,
        delay: float = 0.5,
    ) -> dict[str, PMCFullText]:
        """Fetch full text for multiple papers.

        Args:
            pmids: List of PubMed IDs
            concurrency: Max concurrent requests
            delay: Delay between requests (to respect rate limits)

        Returns:
            Dict mapping PMID to PMCFullText
        """
        results = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_limit(pmid: str) -> tuple[str, PMCFullText]:
            async with semaphore:
                result = await self.fetch_fulltext(pmid)
                await asyncio.sleep(delay)  # Rate limiting
                return pmid, result

        tasks = [fetch_with_limit(pmid) for pmid in pmids]

        for coro in asyncio.as_completed(tasks):
            pmid, result = await coro
            results[pmid] = result

        # Log summary
        oa_count = sum(1 for r in results.values() if r.has_full_text)
        logger.info(f"PMC batch fetch complete: {oa_count}/{len(pmids)} papers have full text")

        return results

    async def check_open_access(self, pmid: str) -> bool:
        """Quick check if a paper is in PMC Open Access.

        Args:
            pmid: PubMed ID

        Returns:
            True if paper is Open Access in PMC
        """
        result = await self.fetch_fulltext(pmid)
        return result.has_full_text


# Convenience function for one-off fetches
async def fetch_pmc_fulltext(pmid: str) -> PMCFullText:
    """Fetch PMC full text for a single paper.

    Args:
        pmid: PubMed ID

    Returns:
        PMCFullText object
    """
    fetcher = PMCFullTextFetcher()
    try:
        return await fetcher.fetch_fulltext(pmid)
    finally:
        await fetcher.close()
