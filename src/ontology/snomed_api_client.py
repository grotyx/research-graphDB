"""SNOMED CT Terminology Server API Client.

This module provides a client for querying SNOMED CT terminology servers,
primarily the Snowstorm API from SNOMED International.

Features:
- Concept search by term
- Concept lookup by SCTID (SNOMED CT Identifier)
- Hierarchy traversal (parents/children)
- Result caching for performance
- Fallback to local mappings when API unavailable

API Documentation:
- Snowstorm: https://snowstorm.ihtsdotools.org/snowstorm/snomed-ct/swagger-ui.html
- SNOMED Browser: https://browser.ihtsdotools.org/

Version: 1.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import asyncio
import logging
import os
import re

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

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


class SNOMEDEdition(Enum):
    """SNOMED CT Edition identifiers."""
    INTERNATIONAL = "MAIN"  # International Edition
    US = "MAIN/SNOMEDCT-US"  # US Edition
    UK = "MAIN/SNOMEDCT-UK"  # UK Clinical Edition
    AU = "MAIN/SNOMEDCT-AU"  # Australian Edition


class ConceptStatus(Enum):
    """SNOMED CT concept status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ALL = "all"


@dataclass
class SNOMEDConcept:
    """A SNOMED CT concept from the terminology server."""
    concept_id: str  # SCTID
    term: str  # Preferred term (FSN or PT)
    fsn: str = ""  # Fully Specified Name
    active: bool = True
    definition_status: str = ""  # PRIMITIVE or FULLY_DEFINED
    module_id: str = ""
    effective_time: str = ""

    # Semantic information
    semantic_tag: str = ""  # e.g., "procedure", "disorder"

    # Relationships
    parents: list[str] = field(default_factory=list)  # IS_A parent SCTIDs
    children: list[str] = field(default_factory=list)  # IS_A child SCTIDs

    # Synonyms from description
    synonyms: list[str] = field(default_factory=list)

    # Source information
    source: str = "snowstorm"  # API source
    retrieved_at: Optional[datetime] = None

    def __post_init__(self):
        if self.retrieved_at is None:
            self.retrieved_at = datetime.now()

        # Extract semantic tag from FSN if available
        if self.fsn and not self.semantic_tag:
            match = re.search(r'\(([^)]+)\)$', self.fsn)
            if match:
                self.semantic_tag = match.group(1)


@dataclass
class SearchResult:
    """Search result from terminology server."""
    concepts: list[SNOMEDConcept]
    total: int
    limit: int
    offset: int
    search_term: str
    search_time_ms: float = 0.0

    @property
    def has_more(self) -> bool:
        """Check if there are more results available."""
        return self.offset + len(self.concepts) < self.total


class SNOMEDAPIClient:
    """Client for SNOMED CT Terminology Server APIs.

    Supports Snowstorm API (SNOMED International's open-source terminology server).

    Example:
        ```python
        async with SNOMEDAPIClient() as client:
            # Search for concepts
            results = await client.search_concepts("lumbar fusion")
            for concept in results.concepts:
                print(f"{concept.concept_id}: {concept.term}")

            # Get specific concept
            concept = await client.get_concept("387713003")  # Surgical procedure
            print(f"FSN: {concept.fsn}")
        ```
    """

    # Default Snowstorm public server
    DEFAULT_BASE_URL = "https://snowstorm.ihtsdotools.org/snowstorm/snomed-ct"

    # Cache TTL (time to live)
    CACHE_TTL = timedelta(hours=24)

    def __init__(
        self,
        base_url: Optional[str] = None,
        edition: SNOMEDEdition = SNOMEDEdition.INTERNATIONAL,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        enable_cache: bool = True,
    ):
        """Initialize SNOMED API client.

        Args:
            base_url: Snowstorm server URL (default: public server)
            edition: SNOMED CT edition to use
            api_key: API key if required by server
            timeout: Request timeout in seconds
            enable_cache: Enable result caching
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for SNOMED API client. "
                "Install with: pip install httpx"
            )

        self.base_url = base_url or os.getenv(
            "SNOMED_API_URL", self.DEFAULT_BASE_URL
        )
        self.edition = edition
        self.api_key = api_key or os.getenv("SNOMED_API_KEY")
        self.timeout = timeout
        self.enable_cache = enable_cache

        # Result cache: {cache_key: (result, timestamp)}
        self._cache: dict[str, tuple[any, datetime]] = {}

        # HTTP client (created in __aenter__)
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_branch_path(self) -> str:
        """Get the branch path for the current edition."""
        return self.edition.value

    def _cache_key(self, operation: str, *args) -> str:
        """Generate cache key."""
        return f"{operation}:{':'.join(str(a) for a in args)}"

    def _get_cached(self, key: str) -> Optional[any]:
        """Get cached result if valid."""
        if not self.enable_cache or key not in self._cache:
            return None

        result, timestamp = self._cache[key]
        if datetime.now() - timestamp < self.CACHE_TTL:
            return result

        # Cache expired
        del self._cache[key]
        return None

    def _set_cached(self, key: str, result: any):
        """Set cached result."""
        if self.enable_cache:
            self._cache[key] = (result, datetime.now())

    async def search_concepts(
        self,
        term: str,
        limit: int = 20,
        offset: int = 0,
        active_only: bool = True,
        semantic_filter: Optional[str] = None,
    ) -> SearchResult:
        """Search for SNOMED CT concepts by term.

        Args:
            term: Search term (supports wildcards)
            limit: Maximum results to return (max 1000)
            offset: Offset for pagination
            active_only: Only return active concepts
            semantic_filter: Filter by semantic tag (e.g., "procedure")

        Returns:
            SearchResult with matching concepts

        Example:
            ```python
            results = await client.search_concepts("lumbar interbody fusion")
            for concept in results.concepts:
                print(f"{concept.concept_id}: {concept.term} ({concept.semantic_tag})")
            ```
        """
        cache_key = self._cache_key("search", term, limit, offset, active_only, semantic_filter)
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug(f"Cache hit for search: {term}")
            return cached

        import time
        start_time = time.time()

        branch = self._get_branch_path()
        params = {
            "term": term,
            "limit": min(limit, 1000),
            "offset": offset,
            "activeFilter": str(active_only).lower(),
        }

        if semantic_filter:
            params["semanticFilter"] = semantic_filter

        try:
            response = await _async_request_with_retry(
                self._client, "get",
                f"/{branch}/concepts",
                params=params,
            )
            data = response.json()

            concepts = []
            for item in data.get("items", []):
                concept = SNOMEDConcept(
                    concept_id=item.get("conceptId", ""),
                    term=item.get("pt", {}).get("term", ""),
                    fsn=item.get("fsn", {}).get("term", ""),
                    active=item.get("active", True),
                    definition_status=item.get("definitionStatus", ""),
                    module_id=item.get("moduleId", ""),
                    effective_time=item.get("effectiveTime", ""),
                )
                concepts.append(concept)

            result = SearchResult(
                concepts=concepts,
                total=data.get("total", len(concepts)),
                limit=data.get("limit", limit),
                offset=data.get("offset", offset),
                search_term=term,
                search_time_ms=(time.time() - start_time) * 1000,
            )

            self._set_cached(cache_key, result)
            logger.info(f"SNOMED search '{term}': {len(concepts)} results in {result.search_time_ms:.1f}ms")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"SNOMED API error: {e.response.status_code} - {e.response.text}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"SNOMED API request failed: {e}", exc_info=True)
            raise

    async def get_concept(self, concept_id: str) -> Optional[SNOMEDConcept]:
        """Get a specific SNOMED CT concept by ID.

        Args:
            concept_id: SNOMED CT Identifier (SCTID)

        Returns:
            SNOMEDConcept or None if not found

        Example:
            ```python
            concept = await client.get_concept("387713003")
            print(f"{concept.fsn}")  # "Surgical procedure (procedure)"
            ```
        """
        cache_key = self._cache_key("concept", concept_id)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        branch = self._get_branch_path()

        try:
            response = await _async_request_with_retry(
                self._client, "get",
                f"/{branch}/concepts/{concept_id}",
            )
            data = response.json()

            concept = SNOMEDConcept(
                concept_id=data.get("conceptId", concept_id),
                term=data.get("pt", {}).get("term", ""),
                fsn=data.get("fsn", {}).get("term", ""),
                active=data.get("active", True),
                definition_status=data.get("definitionStatus", ""),
                module_id=data.get("moduleId", ""),
                effective_time=data.get("effectiveTime", ""),
            )

            self._set_cached(cache_key, concept)
            return concept

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"SNOMED API error: {e.response.status_code}", exc_info=True)
            raise

    async def get_concept_with_descriptions(
        self, concept_id: str
    ) -> Optional[SNOMEDConcept]:
        """Get concept with all descriptions (synonyms).

        Args:
            concept_id: SNOMED CT Identifier

        Returns:
            SNOMEDConcept with synonyms populated
        """
        concept = await self.get_concept(concept_id)
        if not concept:
            return None

        branch = self._get_branch_path()

        try:
            response = await _async_request_with_retry(
                self._client, "get",
                f"/{branch}/concepts/{concept_id}/descriptions",
            )
            data = response.json()

            synonyms = []
            for desc in data.get("items", []):
                term = desc.get("term", "")
                type_id = desc.get("typeId", "")

                # Skip FSN (900000000000003001) and include synonyms
                if type_id != "900000000000003001" and term:
                    if term not in synonyms and term != concept.term:
                        synonyms.append(term)

            concept.synonyms = synonyms
            return concept

        except Exception as e:
            logger.warning(f"Failed to get descriptions for {concept_id}: {e}", exc_info=True)
            return concept

    async def get_parents(
        self, concept_id: str, direct_only: bool = True
    ) -> list[SNOMEDConcept]:
        """Get parent concepts (IS_A relationships).

        Args:
            concept_id: SNOMED CT Identifier
            direct_only: Only return direct parents (not ancestors)

        Returns:
            List of parent concepts
        """
        branch = self._get_branch_path()

        try:
            if direct_only:
                # Get stated parents
                response = await _async_request_with_retry(
                    self._client, "get",
                    f"/{branch}/concepts/{concept_id}/parents",
                )
            else:
                # Get all ancestors
                response = await _async_request_with_retry(
                    self._client, "get",
                    f"/{branch}/concepts/{concept_id}/ancestors",
                )

            data = response.json()

            parents = []
            items = data if isinstance(data, list) else data.get("items", [])

            for item in items:
                parent = SNOMEDConcept(
                    concept_id=item.get("conceptId", ""),
                    term=item.get("pt", {}).get("term", item.get("term", "")),
                    fsn=item.get("fsn", {}).get("term", ""),
                    active=item.get("active", True),
                )
                parents.append(parent)

            return parents

        except Exception as e:
            logger.error(f"Failed to get parents for {concept_id}: {e}", exc_info=True)
            return []

    async def get_children(
        self, concept_id: str, direct_only: bool = True
    ) -> list[SNOMEDConcept]:
        """Get child concepts.

        Args:
            concept_id: SNOMED CT Identifier
            direct_only: Only return direct children (not descendants)

        Returns:
            List of child concepts
        """
        branch = self._get_branch_path()

        try:
            if direct_only:
                response = await _async_request_with_retry(
                    self._client, "get",
                    f"/{branch}/concepts/{concept_id}/children",
                )
            else:
                response = await _async_request_with_retry(
                    self._client, "get",
                    f"/{branch}/concepts/{concept_id}/descendants",
                    params={"limit": 100},
                )

            data = response.json()

            children = []
            items = data if isinstance(data, list) else data.get("items", [])

            for item in items:
                child = SNOMEDConcept(
                    concept_id=item.get("conceptId", ""),
                    term=item.get("pt", {}).get("term", item.get("term", "")),
                    fsn=item.get("fsn", {}).get("term", ""),
                    active=item.get("active", True),
                )
                children.append(child)

            return children

        except Exception as e:
            logger.error(f"Failed to get children for {concept_id}: {e}", exc_info=True)
            return []

    async def find_exact_match(self, term: str) -> Optional[SNOMEDConcept]:
        """Find an exact match for a term.

        Args:
            term: Term to search for exact match

        Returns:
            SNOMEDConcept if exact match found, None otherwise
        """
        results = await self.search_concepts(term, limit=10)

        term_lower = term.lower().strip()
        for concept in results.concepts:
            if concept.term.lower().strip() == term_lower:
                return concept
            # Check FSN without semantic tag
            fsn_term = re.sub(r'\s*\([^)]+\)$', '', concept.fsn).lower().strip()
            if fsn_term == term_lower:
                return concept

        return None

    async def verify_extension_code(
        self, extension_code: str
    ) -> tuple[bool, Optional[SNOMEDConcept]]:
        """Verify if an extension code has an official SNOMED CT equivalent.

        Args:
            extension_code: Local extension code (e.g., "900000000000101")

        Returns:
            Tuple of (has_official_code, official_concept or None)
        """
        # Import local mappings
        try:
            from src.ontology.spine_snomed_mappings import get_mapping
        except ImportError:
            from ontology.spine_snomed_mappings import get_mapping

        mapping = get_mapping(extension_code)
        if not mapping:
            return (False, None)

        # Search for official equivalent
        search_terms = [mapping.term] + (mapping.synonyms or [])

        for term in search_terms:
            concept = await self.find_exact_match(term)
            if concept and not concept.concept_id.startswith("9000000000"):
                return (True, concept)

        return (False, None)

    def clear_cache(self):
        """Clear the result cache."""
        self._cache.clear()
        logger.info("SNOMED API cache cleared")


# Synchronous wrapper for non-async contexts
class SNOMEDAPIClientSync:
    """Synchronous wrapper for SNOMEDAPIClient.

    For use in non-async contexts like Streamlit.

    Example:
        ```python
        client = SNOMEDAPIClientSync()
        results = client.search_concepts("lumbar fusion")
        ```
    """

    def __init__(self, **kwargs):
        """Initialize with same parameters as SNOMEDAPIClient."""
        self._kwargs = kwargs
        self._client: Optional[SNOMEDAPIClient] = None

    def _run_async(self, coro):
        """Run async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    async def _search_async(self, term: str, **kwargs) -> SearchResult:
        async with SNOMEDAPIClient(**self._kwargs) as client:
            return await client.search_concepts(term, **kwargs)

    async def _get_concept_async(self, concept_id: str) -> Optional[SNOMEDConcept]:
        async with SNOMEDAPIClient(**self._kwargs) as client:
            return await client.get_concept(concept_id)

    async def _get_with_descriptions_async(
        self, concept_id: str
    ) -> Optional[SNOMEDConcept]:
        async with SNOMEDAPIClient(**self._kwargs) as client:
            return await client.get_concept_with_descriptions(concept_id)

    def search_concepts(self, term: str, **kwargs) -> SearchResult:
        """Search for concepts (sync wrapper)."""
        return self._run_async(self._search_async(term, **kwargs))

    def get_concept(self, concept_id: str) -> Optional[SNOMEDConcept]:
        """Get concept by ID (sync wrapper)."""
        return self._run_async(self._get_concept_async(concept_id))

    def get_concept_with_descriptions(
        self, concept_id: str
    ) -> Optional[SNOMEDConcept]:
        """Get concept with synonyms (sync wrapper)."""
        return self._run_async(self._get_with_descriptions_async(concept_id))


# Convenience functions
async def search_snomed(term: str, limit: int = 10) -> list[SNOMEDConcept]:
    """Quick search for SNOMED concepts.

    Args:
        term: Search term
        limit: Max results

    Returns:
        List of matching concepts
    """
    async with SNOMEDAPIClient() as client:
        results = await client.search_concepts(term, limit=limit)
        return results.concepts


async def get_snomed_concept(concept_id: str) -> Optional[SNOMEDConcept]:
    """Quick lookup of a SNOMED concept.

    Args:
        concept_id: SCTID

    Returns:
        SNOMEDConcept or None
    """
    async with SNOMEDAPIClient() as client:
        return await client.get_concept(concept_id)


# CLI for testing
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python snomed_api_client.py <search_term>")
            print("       python snomed_api_client.py --concept <SCTID>")
            return

        if sys.argv[1] == "--concept" and len(sys.argv) > 2:
            concept_id = sys.argv[2]
            async with SNOMEDAPIClient() as client:
                concept = await client.get_concept_with_descriptions(concept_id)
                if concept:
                    print(f"Concept: {concept.concept_id}")
                    print(f"  Term: {concept.term}")
                    print(f"  FSN: {concept.fsn}")
                    print(f"  Semantic Tag: {concept.semantic_tag}")
                    print(f"  Active: {concept.active}")
                    if concept.synonyms:
                        print(f"  Synonyms: {', '.join(concept.synonyms)}")
                else:
                    print(f"Concept {concept_id} not found")
        else:
            term = " ".join(sys.argv[1:])
            async with SNOMEDAPIClient() as client:
                results = await client.search_concepts(term, limit=10)
                print(f"Search: '{term}' ({results.total} total, {len(results.concepts)} returned)")
                print("-" * 60)
                for concept in results.concepts:
                    print(f"{concept.concept_id}: {concept.term} ({concept.semantic_tag})")

    asyncio.run(main())
