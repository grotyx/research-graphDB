"""Tests for snomed_api_client module.

Tests SNOMED CT Terminology Server API client including:
- Concept dataclass creation
- Search result dataclass
- Cache management
- Basic client initialization
- Edge cases

Note: Full integration tests with httpx mocking are complex due to async/exception handling.
This test suite focuses on testable components without requiring full httpx mocking.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ontology.snomed_api_client import (
    SNOMEDConcept,
    SearchResult,
    SNOMEDEdition,
    ConceptStatus,
)

# Try to import httpx
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ===========================================================================
# Test: SNOMEDConcept
# ===========================================================================

class TestSNOMEDConcept:
    """SNOMEDConcept dataclass tests."""

    def test_create_concept(self):
        """Test creating a concept."""
        concept = SNOMEDConcept(
            concept_id="387713003",
            term="Surgical procedure",
            fsn="Surgical procedure (procedure)",
            active=True
        )

        assert concept.concept_id == "387713003"
        assert concept.term == "Surgical procedure"
        assert concept.fsn == "Surgical procedure (procedure)"
        assert concept.active is True

    def test_concept_extracts_semantic_tag(self):
        """Test semantic tag extraction from FSN."""
        concept = SNOMEDConcept(
            concept_id="387713003",
            term="Surgical procedure",
            fsn="Surgical procedure (procedure)"
        )

        assert concept.semantic_tag == "procedure"

    def test_concept_extracts_semantic_tag_disorder(self):
        """Test semantic tag extraction for disorder."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="Lumbar stenosis",
            fsn="Lumbar stenosis (disorder)"
        )

        assert concept.semantic_tag == "disorder"

    def test_concept_extracts_semantic_tag_body_structure(self):
        """Test semantic tag extraction for body structure."""
        concept = SNOMEDConcept(
            concept_id="789012",
            term="Lumbar vertebra",
            fsn="Lumbar vertebra structure (body structure)"
        )

        assert concept.semantic_tag == "body structure"

    def test_concept_default_values(self):
        """Test concept default values."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="Test"
        )

        assert concept.fsn == ""
        assert concept.active is True
        assert concept.parents == []
        assert concept.children == []
        assert concept.synonyms == []
        assert concept.source == "snowstorm"
        assert concept.retrieved_at is not None

    def test_concept_manual_semantic_tag(self):
        """Test manual semantic tag takes precedence."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="Test",
            fsn="Test (disorder)",
            semantic_tag="custom"
        )

        # Manual tag should not be overwritten
        assert concept.semantic_tag == "custom"

    def test_concept_no_semantic_tag_in_fsn(self):
        """Test concept without semantic tag in FSN."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="Test term",
            fsn="Test term"  # No semantic tag
        )

        assert concept.semantic_tag == ""

    def test_concept_with_synonyms(self):
        """Test concept with synonyms."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="TLIF",
            synonyms=["Transforaminal Lumbar Interbody Fusion", "Transforaminal fusion"]
        )

        assert len(concept.synonyms) == 2
        assert "Transforaminal Lumbar Interbody Fusion" in concept.synonyms

    def test_concept_with_parents_and_children(self):
        """Test concept with relationships."""
        concept = SNOMEDConcept(
            concept_id="123456",
            term="TLIF",
            parents=["387713003"],  # Surgical procedure
            children=["111111", "222222"]
        )

        assert len(concept.parents) == 1
        assert len(concept.children) == 2

    def test_concept_retrieved_at_auto_set(self):
        """Test retrieved_at is automatically set."""
        before = datetime.now()
        concept = SNOMEDConcept(concept_id="123", term="Test")
        after = datetime.now()

        assert concept.retrieved_at is not None
        assert before <= concept.retrieved_at <= after


# ===========================================================================
# Test: SearchResult
# ===========================================================================

class TestSearchResult:
    """SearchResult dataclass tests."""

    def test_create_search_result(self):
        """Test creating search result."""
        concepts = [
            SNOMEDConcept(concept_id="123", term="Test 1"),
            SNOMEDConcept(concept_id="456", term="Test 2")
        ]

        result = SearchResult(
            concepts=concepts,
            total=10,
            limit=2,
            offset=0,
            search_term="test",
            search_time_ms=100.5
        )

        assert len(result.concepts) == 2
        assert result.total == 10
        assert result.limit == 2
        assert result.offset == 0
        assert result.search_term == "test"
        assert result.search_time_ms == 100.5

    def test_has_more_true(self):
        """Test has_more when more results available."""
        result = SearchResult(
            concepts=[SNOMEDConcept(concept_id="123", term="Test")],
            total=10,
            limit=1,
            offset=0,
            search_term="test"
        )

        assert result.has_more is True

    def test_has_more_false(self):
        """Test has_more when no more results."""
        result = SearchResult(
            concepts=[SNOMEDConcept(concept_id="123", term="Test")],
            total=1,
            limit=1,
            offset=0,
            search_term="test"
        )

        assert result.has_more is False

    def test_has_more_with_offset(self):
        """Test has_more calculation with offset."""
        # offset=5, 3 results returned, total=10
        # offset + len = 5 + 3 = 8 < 10, so has_more=True
        result = SearchResult(
            concepts=[
                SNOMEDConcept(concept_id="1", term="T1"),
                SNOMEDConcept(concept_id="2", term="T2"),
                SNOMEDConcept(concept_id="3", term="T3"),
            ],
            total=10,
            limit=3,
            offset=5,
            search_term="test"
        )

        assert result.has_more is True

    def test_has_more_at_end(self):
        """Test has_more when at end of results."""
        # offset=7, 3 results, total=10
        # offset + len = 7 + 3 = 10, not < 10, so has_more=False
        result = SearchResult(
            concepts=[
                SNOMEDConcept(concept_id="1", term="T1"),
                SNOMEDConcept(concept_id="2", term="T2"),
                SNOMEDConcept(concept_id="3", term="T3"),
            ],
            total=10,
            limit=3,
            offset=7,
            search_term="test"
        )

        assert result.has_more is False


# ===========================================================================
# Test: SNOMEDEdition and ConceptStatus Enums
# ===========================================================================

class TestEnums:
    """Test enum classes."""

    def test_snomed_edition_values(self):
        """Test SNOMED edition enum values."""
        assert SNOMEDEdition.INTERNATIONAL.value == "MAIN"
        assert SNOMEDEdition.US.value == "MAIN/SNOMEDCT-US"
        assert SNOMEDEdition.UK.value == "MAIN/SNOMEDCT-UK"
        assert SNOMEDEdition.AU.value == "MAIN/SNOMEDCT-AU"

    def test_concept_status_values(self):
        """Test concept status enum values."""
        assert ConceptStatus.ACTIVE.value == "active"
        assert ConceptStatus.INACTIVE.value == "inactive"
        assert ConceptStatus.ALL.value == "all"


# ===========================================================================
# Test: SNOMEDAPIClient (Basic Tests)
# ===========================================================================

@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not available")
class TestSNOMEDAPIClientBasic:
    """Basic SNOMEDAPIClient tests that don't require full mocking."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient()

        assert client.base_url == SNOMEDAPIClient.DEFAULT_BASE_URL
        assert client.edition == SNOMEDEdition.INTERNATIONAL
        assert client.timeout == 30.0
        assert client.enable_cache is True

    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient(
            base_url="https://custom.example.com",
            edition=SNOMEDEdition.US,
            api_key="test-key",
            timeout=60.0,
            enable_cache=False
        )

        assert client.base_url == "https://custom.example.com"
        assert client.edition == SNOMEDEdition.US
        assert client.api_key == "test-key"
        assert client.timeout == 60.0
        assert client.enable_cache is False

    def test_branch_path_for_editions(self):
        """Test branch path generation for different editions."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client_intl = SNOMEDAPIClient(edition=SNOMEDEdition.INTERNATIONAL)
        assert client_intl._get_branch_path() == "MAIN"

        client_us = SNOMEDAPIClient(edition=SNOMEDEdition.US)
        assert client_us._get_branch_path() == "MAIN/SNOMEDCT-US"

        client_uk = SNOMEDAPIClient(edition=SNOMEDEdition.UK)
        assert client_uk._get_branch_path() == "MAIN/SNOMEDCT-UK"

    def test_cache_key_generation(self):
        """Test cache key generation."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient()

        key1 = client._cache_key("search", "term1", 10, 0)
        key2 = client._cache_key("search", "term1", 10, 0)
        key3 = client._cache_key("search", "term2", 10, 0)

        assert key1 == key2
        assert key1 != key3
        assert "search" in key1
        assert "term1" in key1

    def test_cache_expiry(self):
        """Test cache expiration."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient(enable_cache=True)

        # Set cache with expired timestamp
        expired_time = datetime.now() - timedelta(hours=25)
        client._cache["test_key"] = ("test_value", expired_time)

        # Should return None (expired)
        result = client._get_cached("test_key")
        assert result is None

    def test_cache_not_expired(self):
        """Test cache returns valid data when not expired."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient(enable_cache=True)

        # Set cache with recent timestamp
        recent_time = datetime.now() - timedelta(hours=1)
        client._cache["test_key"] = ("test_value", recent_time)

        # Should return cached value
        result = client._get_cached("test_key")
        assert result == "test_value"

    def test_cache_disabled(self):
        """Test caching when disabled."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient(enable_cache=False)

        # Set cache entry
        client._set_cached("key", "value")

        # Cache should be empty (caching disabled)
        assert len(client._cache) == 0

    def test_clear_cache(self):
        """Test cache clearing."""
        from ontology.snomed_api_client import SNOMEDAPIClient

        client = SNOMEDAPIClient(enable_cache=True)

        # Add some cache entries
        client._cache["key1"] = ("value1", datetime.now())
        client._cache["key2"] = ("value2", datetime.now())

        assert len(client._cache) == 2

        # Clear cache
        client.clear_cache()

        assert len(client._cache) == 0


# ===========================================================================
# Test: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_concept_with_empty_values(self):
        """Test concept with empty values."""
        concept = SNOMEDConcept(
            concept_id="",
            term=""
        )

        assert concept.concept_id == ""
        assert concept.term == ""
        assert concept.fsn == ""

    def test_search_result_empty(self):
        """Test empty search result."""
        result = SearchResult(
            concepts=[],
            total=0,
            limit=20,
            offset=0,
            search_term="nonexistent"
        )

        assert len(result.concepts) == 0
        assert result.total == 0
        assert result.has_more is False

    def test_concept_semantic_tag_with_multiple_parentheses(self):
        """Test semantic tag extraction with multiple parentheses in FSN."""
        # FSN with multiple parentheses - should extract the last one
        concept = SNOMEDConcept(
            concept_id="123",
            term="Test (old)",
            fsn="Test (old) term (procedure)"
        )

        assert concept.semantic_tag == "procedure"

    def test_concept_with_very_long_lists(self):
        """Test concept with many synonyms, parents, and children."""
        concept = SNOMEDConcept(
            concept_id="123",
            term="Test",
            synonyms=["Synonym " + str(i) for i in range(100)],
            parents=[str(i) for i in range(50)],
            children=[str(i) for i in range(75)]
        )

        assert len(concept.synonyms) == 100
        assert len(concept.parents) == 50
        assert len(concept.children) == 75


# ===========================================================================
# Test: Realistic Use Cases
# ===========================================================================

class TestRealisticUseCases:
    """Test realistic use cases with actual SNOMED data patterns."""

    def test_surgical_procedure_concept(self):
        """Test concept for a surgical procedure."""
        concept = SNOMEDConcept(
            concept_id="699253005",
            term="Spinal fusion procedure",
            fsn="Spinal fusion procedure (procedure)",
            active=True,
            definition_status="PRIMITIVE",
            module_id="900000000000207008",
            effective_time="20160131",
            synonyms=["Spinal fusion", "Spine fusion", "Arthrodesis of spine"]
        )

        assert concept.semantic_tag == "procedure"
        assert concept.active is True
        assert len(concept.synonyms) == 3

    def test_disorder_concept(self):
        """Test concept for a disorder."""
        concept = SNOMEDConcept(
            concept_id="76107001",
            term="Spinal stenosis",
            fsn="Spinal stenosis (disorder)",
            active=True,
            semantic_tag="disorder",
            synonyms=["Stenosis of spine", "Narrowing of spinal canal"]
        )

        assert concept.semantic_tag == "disorder"
        assert len(concept.synonyms) == 2

    def test_anatomical_structure_concept(self):
        """Test concept for an anatomical structure."""
        concept = SNOMEDConcept(
            concept_id="23962006",
            term="Lumbar vertebra",
            fsn="Lumbar vertebra structure (body structure)",
            active=True,
            synonyms=["Lumbar spine", "L-spine vertebra"]
        )

        assert concept.semantic_tag == "body structure"

    def test_search_result_pagination(self):
        """Test search result pagination scenario."""
        # First page
        page1 = SearchResult(
            concepts=[SNOMEDConcept(concept_id=str(i), term=f"Concept {i}") for i in range(20)],
            total=50,
            limit=20,
            offset=0,
            search_term="spine"
        )

        assert page1.has_more is True
        assert len(page1.concepts) == 20

        # Last page
        page3 = SearchResult(
            concepts=[SNOMEDConcept(concept_id=str(i), term=f"Concept {i}") for i in range(10)],
            total=50,
            limit=20,
            offset=40,
            search_term="spine"
        )

        assert page3.has_more is False
        assert len(page3.concepts) == 10
