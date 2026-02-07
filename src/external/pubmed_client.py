"""PubMed integration module for Medical KAG system.

This module provides integration with the NCBI PubMed E-utilities API
for searching and retrieving medical literature.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import asyncio
import time
import xml.etree.ElementTree as ET

import aiohttp
import requests


class PubMedError(Exception):
    """Base exception for PubMed operations."""
    pass


class APIError(PubMedError):
    """API request failed."""
    pass


class RateLimitError(PubMedError):
    """Rate limit exceeded."""
    pass


@dataclass
class PaperMetadata:
    """Metadata for a PubMed paper.

    Attributes:
        pmid: PubMed ID
        title: Paper title
        authors: List of author names
        year: Publication year
        journal: Journal name
        abstract: Abstract text
        mesh_terms: Medical Subject Headings terms
        doi: Digital Object Identifier (optional)
        publication_types: List of publication types
    """
    pmid: str
    title: str
    authors: List[str]
    year: int
    journal: str
    abstract: str
    mesh_terms: List[str]
    doi: Optional[str] = None
    publication_types: List[str] = None

    def __post_init__(self):
        if self.publication_types is None:
            self.publication_types = []


class PubMedClient:
    """Client for NCBI PubMed E-utilities API.

    Provides methods to search PubMed and retrieve paper metadata.
    Implements rate limiting to comply with NCBI usage guidelines.
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    RATE_LIMIT_DELAY = 0.34  # ~3 requests per second

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize PubMed client.

        Args:
            email: Contact email (recommended by NCBI)
            api_key: NCBI API key (optional, increases rate limit to 10/sec)
        """
        self.email = email
        self.api_key = api_key
        self.last_request_time = 0.0

        # Update rate limit if API key provided
        if api_key:
            self.RATE_LIMIT_DELAY = 0.1  # 10 requests per second with API key

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - time_since_last)

        self.last_request_time = time.time()

    def _build_params(self, **kwargs) -> dict:
        """Build request parameters with email and API key if available."""
        params = kwargs.copy()
        if self.email:
            params['email'] = self.email
        if self.api_key:
            params['api_key'] = self.api_key
        return params

    def search(self, query: str, max_results: int = 10, retmode: str = "json") -> List[str]:
        """Search PubMed for papers matching the query.

        Args:
            query: PubMed search query (supports PubMed syntax)
            max_results: Maximum number of results to return
            retmode: Return mode ("json" or "xml")

        Returns:
            List of PubMed IDs (PMIDs)

        Raises:
            APIError: If the API request fails
            RateLimitError: If rate limit is exceeded
        """
        self._rate_limit()

        url = f"{self.BASE_URL}esearch.fcgi"
        params = self._build_params(
            db="pubmed",
            term=query,
            retmax=max_results,
            retmode=retmode
        )

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise APIError(f"Search request failed: {e}")

        if retmode == "json":
            data = response.json()
            result = data.get("esearchresult", {})
            pmids = result.get("idlist", [])
            return pmids
        else:
            # Parse XML response
            root = ET.fromstring(response.text)
            pmids = [id_elem.text for id_elem in root.findall(".//Id")]
            return pmids

    def fetch_abstract(self, pmid: str) -> str:
        """Fetch abstract text for a given PMID.

        Args:
            pmid: PubMed ID

        Returns:
            Abstract text

        Raises:
            APIError: If the API request fails
        """
        details = self.fetch_paper_details(pmid)
        return details.abstract

    def fetch_paper_details(self, pmid: str) -> PaperMetadata:
        """Fetch full metadata for a given PMID.

        Args:
            pmid: PubMed ID

        Returns:
            PaperMetadata object with full details

        Raises:
            APIError: If the API request fails
        """
        self._rate_limit()

        url = f"{self.BASE_URL}efetch.fcgi"
        params = self._build_params(
            db="pubmed",
            id=pmid,
            retmode="xml"
        )

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise APIError(f"Fetch request failed: {e}")

        return self._parse_pubmed_xml(response.text, pmid)

    def _parse_pubmed_xml(self, xml_text: str, pmid: str) -> PaperMetadata:
        """Parse PubMed XML response into PaperMetadata.

        Args:
            xml_text: XML response from efetch
            pmid: PubMed ID

        Returns:
            PaperMetadata object
        """
        root = ET.fromstring(xml_text)
        article = root.find(".//PubmedArticle")

        if article is None:
            raise APIError(f"No article found for PMID {pmid}")

        # Extract title
        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else "Unknown"

        # Extract authors
        authors = []
        author_list = article.findall(".//Author")
        for author in author_list:
            last_name = author.find("LastName")
            fore_name = author.find("ForeName")
            if last_name is not None:
                name = last_name.text
                if fore_name is not None:
                    name = f"{fore_name.text} {name}"
                authors.append(name)

        # Extract year
        year = 0
        pub_date = article.find(".//PubDate/Year")
        if pub_date is not None:
            try:
                year = int(pub_date.text)
            except (ValueError, AttributeError):
                pass

        # If year not found in PubDate, try MedlineDate
        if year == 0:
            medline_date = article.find(".//PubDate/MedlineDate")
            if medline_date is not None and medline_date.text:
                # Extract first 4 digits as year
                import re
                match = re.search(r'\d{4}', medline_date.text)
                if match:
                    year = int(match.group())

        # Extract journal
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else "Unknown"

        # Extract abstract
        abstract_parts = []
        abstract_texts = article.findall(".//Abstract/AbstractText")
        for abstract_text in abstract_texts:
            label = abstract_text.get("Label", "")
            text = abstract_text.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Extract MeSH terms
        mesh_terms = []
        mesh_headings = article.findall(".//MeshHeading/DescriptorName")
        for mesh in mesh_headings:
            if mesh.text:
                mesh_terms.append(mesh.text)

        # Extract DOI
        doi = None
        article_ids = article.findall(".//ArticleId")
        for article_id in article_ids:
            if article_id.get("IdType") == "doi":
                doi = article_id.text
                break

        # Extract publication types
        publication_types = []
        pub_type_elems = article.findall(".//PublicationType")
        for pub_type in pub_type_elems:
            if pub_type.text:
                publication_types.append(pub_type.text)

        return PaperMetadata(
            pmid=pmid,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            abstract=abstract,
            mesh_terms=mesh_terms,
            doi=doi,
            publication_types=publication_types
        )

    async def search_async(self, query: str, max_results: int = 10) -> List[str]:
        """Async version of search.

        Args:
            query: PubMed search query
            max_results: Maximum number of results

        Returns:
            List of PMIDs
        """
        url = f"{self.BASE_URL}esearch.fcgi"
        params = self._build_params(
            db="pubmed",
            term=query,
            retmax=max_results,
            retmode="json"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status != 200:
                    raise APIError(f"Search request failed with status {response.status}")
                data = await response.json()
                result = data.get("esearchresult", {})
                return result.get("idlist", [])

    async def fetch_paper_details_async(self, pmid: str) -> PaperMetadata:
        """Async version of fetch_paper_details.

        Args:
            pmid: PubMed ID

        Returns:
            PaperMetadata object
        """
        url = f"{self.BASE_URL}efetch.fcgi"
        params = self._build_params(
            db="pubmed",
            id=pmid,
            retmode="xml"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status != 200:
                    raise APIError(f"Fetch request failed with status {response.status}")
                xml_text = await response.text()
                return self._parse_pubmed_xml(xml_text, pmid)

    async def fetch_batch_async(self, pmids: List[str]) -> List[PaperMetadata]:
        """Fetch multiple papers concurrently.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of PaperMetadata objects
        """
        tasks = [self.fetch_paper_details_async(pmid) for pmid in pmids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        papers = []
        for result in results:
            if isinstance(result, PaperMetadata):
                papers.append(result)
            elif isinstance(result, Exception):
                # Log error but continue
                print(f"Error fetching paper: {result}")

        return papers
