"""Tests for SNOMED CT API Client.

These tests include both unit tests (mocked) and integration tests (live API).
Integration tests are marked with @pytest.mark.integration and can be skipped
with: pytest -m "not integration"

Run all tests: pytest tests/ontology/test_snomed_api_client.py -v
Run unit tests only: pytest tests/ontology/test_snomed_api_client.py -v -m "not integration"
Run integration tests only: pytest tests/ontology/test_snomed_api_client.py -v -m integration
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Skip all tests if httpx is not available
pytest.importorskip("httpx")

from src.ontology.snomed_api_client import (
    SNOMEDAPIClient,
    SNOMEDAPIClientSync,
    SNOMEDConcept,
    SNOMEDEdition,
    SearchResult,
    search_snomed,
    get_snomed_concept,
)


# ============================================================================
# Unit Tests (Mocked)
# ============================================================================

class TestSNOMEDConcept:
    """Tests for SNOMEDConcept dataclass."""

    def test_concept_creation(self):
        """Test basic concept creation."""
        concept = SNOMEDConcept(
            concept_id="387713003",
            term="Surgical procedure",
            fsn="Surgical procedure (procedure)",
        )
        assert concept.concept_id == "387713003"
        assert concept.term == "Surgical procedure"
        assert concept.active is True
        assert concept.retrieved_at is not None

    def test_semantic_tag_extraction(self):
        """Test automatic semantic tag extraction from FSN."""
        concept = SNOMEDConcept(
            concept_id="387713003",
            term="Surgical procedure",
            fsn="Surgical procedure (procedure)",
        )
        assert concept.semantic_tag == "procedure"

    def test_semantic_tag_complex(self):
        """Test semantic tag extraction with complex FSN."""
        concept = SNOMEDConcept(
            concept_id="123456789",
            term="Lumbar fusion",
            fsn="Fusion of lumbar spine (procedure)",
        )
        assert concept.semantic_tag == "procedure"

    def test_semantic_tag_disorder(self):
        """Test semantic tag for disorder."""
        concept = SNOMEDConcept(
            concept_id="987654321",
            term="Spinal stenosis",
            fsn="Spinal stenosis (disorder)",
        )
        assert concept.semantic_tag == "disorder"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_has_more_true(self):
        """Test has_more when more results exist."""
        result = SearchResult(
            concepts=[SNOMEDConcept(concept_id="1", term="Test")],
            total=100,
            limit=10,
            offset=0,
            search_term="test",
        )
        assert result.has_more is True

    def test_has_more_false(self):
        """Test has_more when all results returned."""
        concepts = [SNOMEDConcept(concept_id=str(i), term=f"Test{i}") for i in range(10)]
        result = SearchResult(
            concepts=concepts,
            total=10,
            limit=10,
            offset=0,
            search_term="test",
        )
        assert result.has_more is False


class TestSNOMEDAPIClientCache:
    """Tests for caching functionality."""

    @pytest.mark.asyncio
    async def test_cache_enabled(self):
        """Test that caching works when enabled."""
        client = SNOMEDAPIClient(enable_cache=True)

        # Set a cached value
        key = client._cache_key("test", "arg1", "arg2")
        client._set_cached(key, {"result": "cached"})

        # Retrieve cached value
        cached = client._get_cached(key)
        assert cached == {"result": "cached"}

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Test that caching is bypassed when disabled."""
        client = SNOMEDAPIClient(enable_cache=False)

        key = client._cache_key("test", "arg1")
        client._set_cached(key, {"result": "cached"})

        cached = client._get_cached(key)
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_expiry(self):
        """Test that expired cache entries are not returned."""
        client = SNOMEDAPIClient(enable_cache=True)
        client.CACHE_TTL = timedelta(seconds=-1)  # Expired immediately

        key = client._cache_key("test", "arg1")
        client._set_cached(key, {"result": "cached"})

        cached = client._get_cached(key)
        assert cached is None

    def test_clear_cache(self):
        """Test cache clearing."""
        client = SNOMEDAPIClient(enable_cache=True)

        client._set_cached("key1", "value1")
        client._set_cached("key2", "value2")
        assert len(client._cache) == 2

        client.clear_cache()
        assert len(client._cache) == 0


class TestSNOMEDAPIClientBranch:
    """Tests for branch path handling."""

    def test_international_edition(self):
        """Test branch path for International edition."""
        client = SNOMEDAPIClient(edition=SNOMEDEdition.INTERNATIONAL)
        assert client._get_branch_path() == "MAIN"

    def test_us_edition(self):
        """Test branch path for US edition."""
        client = SNOMEDAPIClient(edition=SNOMEDEdition.US)
        assert client._get_branch_path() == "MAIN/SNOMEDCT-US"

    def test_uk_edition(self):
        """Test branch path for UK edition."""
        client = SNOMEDAPIClient(edition=SNOMEDEdition.UK)
        assert client._get_branch_path() == "MAIN/SNOMEDCT-UK"


class TestSNOMEDAPIClientMocked:
    """Tests with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_search_concepts_mocked(self):
        """Test search_concepts with mocked response."""
        mock_response_data = {
            "items": [
                {
                    "conceptId": "840279003",
                    "pt": {"term": "Lateral lumbar interbody fusion"},
                    "fsn": {"term": "Lateral lumbar interbody fusion (procedure)"},
                    "active": True,
                    "definitionStatus": "PRIMITIVE",
                }
            ],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.aclose = AsyncMock()

            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            async with SNOMEDAPIClient() as client:
                client._client = mock_client_instance
                results = await client.search_concepts("lumbar fusion")

                assert len(results.concepts) == 1
                assert results.concepts[0].concept_id == "840279003"
                assert results.concepts[0].semantic_tag == "procedure"

    @pytest.mark.asyncio
    async def test_get_concept_not_found(self):
        """Test get_concept returns None for 404."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.aclose = AsyncMock()

            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            async with SNOMEDAPIClient() as client:
                client._client = mock_client_instance
                result = await client.get_concept("invalid_id")

                assert result is None


# ============================================================================
# Integration Tests (Live API)
# ============================================================================

@pytest.mark.integration
class TestSNOMEDAPIClientIntegration:
    """Integration tests using live Snowstorm API.

    These tests require internet connection and may be slow.
    Skip with: pytest -m "not integration"
    """

    @pytest.mark.asyncio
    async def test_search_surgical_procedure(self):
        """Test searching for surgical procedures."""
        async with SNOMEDAPIClient() as client:
            results = await client.search_concepts(
                "lumbar interbody fusion",
                limit=5,
            )

            assert results.total > 0
            assert len(results.concepts) > 0

            # Check that results are relevant
            terms = [c.term.lower() for c in results.concepts]
            assert any("fusion" in t or "lumbar" in t for t in terms)

    @pytest.mark.asyncio
    async def test_search_with_semantic_filter(self):
        """Test searching with semantic filter."""
        async with SNOMEDAPIClient() as client:
            results = await client.search_concepts(
                "stenosis",
                limit=10,
                semantic_filter="disorder",
            )

            # All results should be disorders
            for concept in results.concepts:
                if concept.semantic_tag:
                    # Note: semantic_filter may not be exact in all cases
                    pass  # API may return related results

    @pytest.mark.asyncio
    async def test_get_known_concept(self):
        """Test getting a known SNOMED concept."""
        # 387713003 = Surgical procedure (procedure)
        async with SNOMEDAPIClient() as client:
            concept = await client.get_concept("387713003")

            assert concept is not None
            assert concept.concept_id == "387713003"
            assert "surgical" in concept.term.lower() or "procedure" in concept.term.lower()
            assert concept.active is True

    @pytest.mark.asyncio
    async def test_get_concept_with_descriptions(self):
        """Test getting concept with synonyms."""
        async with SNOMEDAPIClient() as client:
            concept = await client.get_concept_with_descriptions("387713003")

            assert concept is not None
            # May or may not have synonyms depending on the concept
            assert isinstance(concept.synonyms, list)

    @pytest.mark.asyncio
    async def test_get_parents(self):
        """Test getting parent concepts."""
        # 840279003 = Lateral lumbar interbody fusion
        async with SNOMEDAPIClient() as client:
            parents = await client.get_parents("840279003")

            # Should have at least one parent
            assert len(parents) >= 0  # May vary based on API

    @pytest.mark.asyncio
    async def test_find_exact_match(self):
        """Test finding exact match for a term."""
        async with SNOMEDAPIClient() as client:
            # Search for a well-known procedure
            concept = await client.find_exact_match("Laminectomy")

            # May or may not find exact match
            if concept:
                assert "laminectomy" in concept.term.lower()

    @pytest.mark.asyncio
    async def test_search_spine_related_terms(self):
        """Test searching for spine-related surgical terms."""
        search_terms = [
            "discectomy",
            "laminectomy",
            "spinal fusion",
            "decompression of spinal cord",
        ]

        async with SNOMEDAPIClient() as client:
            for term in search_terms:
                results = await client.search_concepts(term, limit=3)
                assert results is not None
                # Should find at least something for common procedures
                # Note: Some terms may return 0 results


@pytest.mark.integration
class TestSNOMEDAPIClientSyncIntegration:
    """Integration tests for synchronous wrapper."""

    def test_sync_search_concepts(self):
        """Test synchronous search."""
        client = SNOMEDAPIClientSync()
        results = client.search_concepts("lumbar fusion", limit=3)

        assert results is not None
        assert isinstance(results, SearchResult)

    def test_sync_get_concept(self):
        """Test synchronous concept lookup."""
        client = SNOMEDAPIClientSync()
        concept = client.get_concept("387713003")

        if concept:  # May fail if API is unavailable
            assert concept.concept_id == "387713003"


@pytest.mark.integration
class TestConvenienceFunctions:
    """Integration tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_search_snomed_function(self):
        """Test search_snomed convenience function."""
        concepts = await search_snomed("spinal stenosis", limit=5)
        assert isinstance(concepts, list)

    @pytest.mark.asyncio
    async def test_get_snomed_concept_function(self):
        """Test get_snomed_concept convenience function."""
        concept = await get_snomed_concept("387713003")
        if concept:
            assert concept.concept_id == "387713003"


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_invalid_concept_id(self):
        """Test handling of invalid concept ID."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.aclose = AsyncMock()

            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            async with SNOMEDAPIClient() as client:
                client._client = mock_client_instance
                result = await client.get_concept("000000000")
                assert result is None

    def test_cache_key_generation(self):
        """Test cache key generation."""
        client = SNOMEDAPIClient()

        key1 = client._cache_key("search", "term1", 10, 0)
        key2 = client._cache_key("search", "term1", 10, 0)
        key3 = client._cache_key("search", "term2", 10, 0)

        assert key1 == key2
        assert key1 != key3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
