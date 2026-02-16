"""Tests for GraphSearch module.

Neo4j 그래프 검색 테스트:
- Intervention → Outcome 검색
- Pathology → Intervention 검색
- Intervention hierarchy 조회
- Conflicting results 탐지
- Paper evidence 조회
- Evidence level 검색
- 정규화 (normalization)
- Edge cases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from src.solver.graph_search import (
    GraphSearch,
    GraphSearchResult,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.run_query = AsyncMock()
    return client


@pytest.fixture
def graph_search(mock_neo4j_client):
    """GraphSearch with mocked Neo4j client."""
    return GraphSearch(neo4j_client=mock_neo4j_client)


@pytest.fixture
def mock_normalizer():
    """Mock entity normalizer."""
    normalizer = MagicMock()

    # Mock normalize_intervention
    def normalize_intervention_side_effect(name):
        result = MagicMock()
        # UBE → BESS mapping
        if name.upper() == "UBE":
            result.normalized = "BESS"
            result.is_normalized = True
        else:
            result.normalized = name
            result.is_normalized = False
        return result

    normalizer.normalize_intervention = MagicMock(
        side_effect=normalize_intervention_side_effect
    )

    # Mock normalize_outcome
    def normalize_outcome_side_effect(name):
        result = MagicMock()
        # VAS → Visual Analog Scale mapping
        if name.upper() == "VAS":
            result.normalized = "Visual Analog Scale"
            result.is_normalized = True
        else:
            result.normalized = name
            result.is_normalized = False
        return result

    normalizer.normalize_outcome = MagicMock(
        side_effect=normalize_outcome_side_effect
    )

    return normalizer


# ===========================================================================
# Test: Context Manager
# ===========================================================================

class TestContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_context_manager_connect_and_close(self, mock_neo4j_client):
        """Context manager connects and closes client."""
        search = GraphSearch(neo4j_client=mock_neo4j_client)

        async with search as s:
            assert s is search
            mock_neo4j_client.connect.assert_called_once()

        # close should NOT be called if we provided the client
        mock_neo4j_client.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_owns_client(self):
        """Context manager closes client if it owns it."""
        with patch('src.solver.graph_search.Neo4jClient') as MockClient:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock()
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            search = GraphSearch()  # No client provided

            async with search:
                mock_client.connect.assert_called_once()

            # Should close because it owns the client
            mock_client.close.assert_called_once()


# ===========================================================================
# Test: search_interventions_for_outcome
# ===========================================================================

class TestSearchInterventionsForOutcome:
    """Test intervention search by outcome."""

    @pytest.mark.asyncio
    async def test_basic_search(self, graph_search, mock_neo4j_client):
        """Basic search for interventions affecting an outcome."""
        # Mock data
        mock_data = [
            {
                "intervention": "TLIF",
                "full_name": "Transforaminal Lumbar Interbody Fusion",
                "category": "Fusion",
                "value": "2.3",
                "value_control": "4.5",
                "p_value": 0.001,
                "effect_size": 0.75,
                "confidence_interval": "0.60-0.90",
                "source_paper_id": "paper_001",
                "matched_outcome": "VAS"
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved",
            limit=20
        )

        assert isinstance(result, GraphSearchResult)
        assert len(result.results) == 1
        assert result.results[0]["intervention"] == "TLIF"
        assert result.results[0]["p_value"] == 0.001
        assert result.execution_time_ms >= 0
        assert "VAS" in result.query

    @pytest.mark.asyncio
    async def test_no_results_triggers_fuzzy_search(self, graph_search, mock_neo4j_client):
        """No exact match triggers fuzzy search."""
        # First call (exact match) returns empty
        # Second call (fuzzy) returns results
        mock_neo4j_client.run_query.side_effect = [
            [],  # Exact match
            [{"intervention": "PLIF", "matched_outcome": "VAS score"}]  # Fuzzy
        ]

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved"
        )

        # Should have called run_query twice
        assert mock_neo4j_client.run_query.call_count == 2
        assert len(result.results) == 1
        assert result.results[0]["intervention"] == "PLIF"

    @pytest.mark.asyncio
    async def test_normalization_applied(self, graph_search, mock_neo4j_client, mock_normalizer):
        """Outcome name normalization is applied."""
        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', True):
            with patch('src.solver.graph_search.get_normalizer', return_value=mock_normalizer):
                graph_search._normalizer = mock_normalizer

                mock_neo4j_client.run_query.return_value = []

                await graph_search.search_interventions_for_outcome(
                    outcome_name="VAS",
                    direction="improved"
                )

                # Should normalize VAS → Visual Analog Scale
                # Check that run_query was called with normalized name
                call_args = mock_neo4j_client.run_query.call_args_list[0]
                params = call_args[0][1]
                assert params["outcome_name"] == "Visual Analog Scale"

    @pytest.mark.asyncio
    async def test_different_directions(self, graph_search, mock_neo4j_client):
        """Test different effect directions."""
        mock_neo4j_client.run_query.return_value = []

        for direction in ["improved", "worsened", "unchanged"]:
            result = await graph_search.search_interventions_for_outcome(
                outcome_name="VAS",
                direction=direction
            )

            assert direction in result.query

    @pytest.mark.asyncio
    async def test_custom_limit(self, graph_search, mock_neo4j_client):
        """Custom result limit."""
        mock_neo4j_client.run_query.return_value = []

        await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved",
            limit=50
        )

        call_args = mock_neo4j_client.run_query.call_args[0][1]
        assert call_args["limit"] == 50

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Database error")

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved"
        )

        # Should return empty results without crashing
        assert result.results == []
        assert "VAS" in result.query


# ===========================================================================
# Test: search_interventions_for_pathology
# ===========================================================================

class TestSearchInterventionsForPathology:
    """Test intervention search by pathology."""

    @pytest.mark.asyncio
    async def test_basic_search(self, graph_search, mock_neo4j_client):
        """Basic pathology search."""
        mock_data = [
            {
                "intervention": "UBE",
                "indication": "Central stenosis",
                "outcomes": [
                    {"outcome": "VAS", "value": "2.3"}
                ]
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.search_interventions_for_pathology(
            pathology_name="Lumbar Stenosis",
            limit=20
        )

        assert len(result.results) == 1
        assert result.results[0]["intervention"] == "UBE"
        assert "Lumbar Stenosis" in result.query

    @pytest.mark.asyncio
    async def test_custom_limit(self, graph_search, mock_neo4j_client):
        """Custom result limit."""
        mock_neo4j_client.run_query.return_value = []

        await graph_search.search_interventions_for_pathology(
            pathology_name="AIS",
            limit=30
        )

        call_args = mock_neo4j_client.run_query.call_args[0][1]
        assert call_args["limit"] == 30

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Query failed")

        result = await graph_search.search_interventions_for_pathology(
            pathology_name="Lumbar Stenosis"
        )

        assert result.results == []


# ===========================================================================
# Test: get_intervention_hierarchy
# ===========================================================================

class TestGetInterventionHierarchy:
    """Test intervention hierarchy retrieval."""

    @pytest.mark.asyncio
    async def test_basic_hierarchy(self, graph_search, mock_neo4j_client):
        """Basic hierarchy retrieval."""
        # Mock parent query result
        parent_data = [
            {
                "i": {
                    "name": "TLIF",
                    "full_name": "Transforaminal Lumbar Interbody Fusion",
                    "category": "Fusion",
                    "approach": "Posterior",
                    "is_minimally_invasive": False
                },
                "hierarchy": [
                    [
                        {"name": "Interbody Fusion"},
                        {"name": "Fusion Surgery"}
                    ]
                ]
            }
        ]

        # Mock children query result
        child_data = [
            {"name": "MIS-TLIF"}
        ]

        mock_neo4j_client.run_query.side_effect = [parent_data, child_data]

        hierarchy = await graph_search.get_intervention_hierarchy("TLIF")

        assert hierarchy["name"] == "TLIF"
        assert hierarchy["full_name"] == "Transforaminal Lumbar Interbody Fusion"
        assert "Interbody Fusion" in hierarchy["parents"]
        assert "MIS-TLIF" in hierarchy["children"]

    @pytest.mark.asyncio
    async def test_intervention_not_found(self, graph_search, mock_neo4j_client):
        """Intervention not found in database."""
        mock_neo4j_client.run_query.side_effect = [[], []]

        hierarchy = await graph_search.get_intervention_hierarchy("NonExistent")

        assert hierarchy["name"] == "NonExistent"
        assert hierarchy["full_name"] == ""
        assert hierarchy["parents"] == []
        assert hierarchy["children"] == []

    @pytest.mark.asyncio
    async def test_no_parents_or_children(self, graph_search, mock_neo4j_client):
        """Intervention with no hierarchy."""
        parent_data = [
            {
                "i": {
                    "name": "Custom Surgery",
                    "full_name": "Custom Surgical Procedure"
                },
                "hierarchy": []
            }
        ]

        mock_neo4j_client.run_query.side_effect = [parent_data, []]

        hierarchy = await graph_search.get_intervention_hierarchy("Custom Surgery")

        assert hierarchy["parents"] == []
        assert hierarchy["children"] == []

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Query error")

        hierarchy = await graph_search.get_intervention_hierarchy("TLIF")

        assert hierarchy["name"] == "TLIF"
        assert hierarchy["parents"] == []
        assert hierarchy["children"] == []


# ===========================================================================
# Test: find_conflicting_results
# ===========================================================================

class TestFindConflictingResults:
    """Test conflicting results detection."""

    @pytest.mark.asyncio
    async def test_conflicting_results_specific_outcome(self, graph_search, mock_neo4j_client):
        """Find conflicts for specific outcome."""
        mock_data = [
            {
                "intervention": "OLIF",
                "outcome": "Canal Area",
                "direction1": "improved",
                "direction2": "unchanged",
                "value1": "120",
                "value2": "95",
                "p_value1": 0.02,
                "p_value2": 0.45,
                "paper1": "paper_001",
                "paper2": "paper_002"
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.find_conflicting_results(
            intervention_name="OLIF",
            outcome_name="Canal Area"
        )

        assert len(result.results) == 1
        assert result.results[0]["direction1"] != result.results[0]["direction2"]

    @pytest.mark.asyncio
    async def test_conflicting_results_all_outcomes(self, graph_search, mock_neo4j_client):
        """Find conflicts across all outcomes."""
        mock_data = [
            {
                "intervention": "OLIF",
                "outcome": "VAS",
                "direction1": "improved",
                "direction2": "worsened",
                "paper1": "paper_001",
                "paper2": "paper_002"
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.find_conflicting_results(
            intervention_name="OLIF",
            outcome_name=None
        )

        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_no_conflicts(self, graph_search, mock_neo4j_client):
        """No conflicting results found."""
        mock_neo4j_client.run_query.return_value = []

        result = await graph_search.find_conflicting_results(
            intervention_name="TLIF",
            outcome_name="VAS"
        )

        assert result.results == []

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Query failed")

        result = await graph_search.find_conflicting_results(
            intervention_name="OLIF"
        )

        assert result.results == []


# ===========================================================================
# Test: get_paper_evidence
# ===========================================================================

class TestGetPaperEvidence:
    """Test paper evidence retrieval."""

    @pytest.mark.asyncio
    async def test_basic_paper_evidence(self, graph_search, mock_neo4j_client):
        """Basic paper evidence retrieval."""
        mock_data = [
            {
                "p": {
                    "paper_id": "paper_001",
                    "title": "UBE vs MIS-TLIF",
                    "year": 2024
                },
                "pathologies": ["Lumbar Stenosis"],
                "interventions": ["UBE", "MIS-TLIF"],
                "outcomes": [
                    {
                        "outcome": "VAS",
                        "value": "2.3",
                        "p_value": 0.001,
                        "direction": "improved"
                    }
                ]
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        evidence = await graph_search.get_paper_evidence("paper_001")

        assert evidence["paper"]["paper_id"] == "paper_001"
        assert "Lumbar Stenosis" in evidence["pathologies"]
        assert "UBE" in evidence["interventions"]
        assert len(evidence["outcomes"]) == 1

    @pytest.mark.asyncio
    async def test_paper_not_found(self, graph_search, mock_neo4j_client):
        """Paper not found."""
        mock_neo4j_client.run_query.return_value = []

        evidence = await graph_search.get_paper_evidence("nonexistent")

        assert evidence["paper"] is None
        assert evidence["pathologies"] == []
        assert evidence["interventions"] == []
        assert evidence["outcomes"] == []

    @pytest.mark.asyncio
    async def test_filters_empty_outcomes(self, graph_search, mock_neo4j_client):
        """Filters out outcomes without names."""
        mock_data = [
            {
                "p": {"paper_id": "paper_001"},
                "pathologies": [],
                "interventions": [],
                "outcomes": [
                    {"outcome": "VAS", "value": "2.3"},
                    {"outcome": None, "value": "3.5"},  # Should be filtered
                    {"outcome": "", "value": "1.2"}     # Should be filtered
                ]
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        evidence = await graph_search.get_paper_evidence("paper_001")

        # Should only have one valid outcome
        assert len(evidence["outcomes"]) == 1
        assert evidence["outcomes"][0]["outcome"] == "VAS"

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Query error")

        evidence = await graph_search.get_paper_evidence("paper_001")

        assert evidence["paper"] is None


# ===========================================================================
# Test: search_by_evidence_level
# ===========================================================================

class TestSearchByEvidenceLevel:
    """Test search by evidence level."""

    @pytest.mark.asyncio
    async def test_basic_evidence_search(self, graph_search, mock_neo4j_client):
        """Basic evidence level search."""
        mock_data = [
            {
                "paper_id": "paper_001",
                "title": "RCT study",
                "year": 2024,
                "journal": "Spine",
                "sub_domain": "Degenerative",
                "study_design": "RCT"
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.search_by_evidence_level(
            evidence_level="1b",
            limit=50
        )

        assert len(result.results) == 1
        assert result.results[0]["paper_id"] == "paper_001"

    @pytest.mark.asyncio
    async def test_with_sub_domain_filter(self, graph_search, mock_neo4j_client):
        """Search with sub-domain filter."""
        mock_neo4j_client.run_query.return_value = []

        await graph_search.search_by_evidence_level(
            evidence_level="1a",
            sub_domain="Deformity",
            limit=30
        )

        call_args = mock_neo4j_client.run_query.call_args[0][1]
        assert call_args["evidence_level"] == "1a"
        assert call_args["sub_domain"] == "Deformity"

    @pytest.mark.asyncio
    async def test_different_evidence_levels(self, graph_search, mock_neo4j_client):
        """Test different evidence levels."""
        mock_neo4j_client.run_query.return_value = []

        for level in ["1a", "1b", "2a", "2b", "3", "4"]:
            result = await graph_search.search_by_evidence_level(
                evidence_level=level
            )

            assert level in result.query

    @pytest.mark.asyncio
    async def test_error_handling(self, graph_search, mock_neo4j_client):
        """Graceful error handling."""
        mock_neo4j_client.run_query.side_effect = Exception("Query failed")

        result = await graph_search.search_by_evidence_level(
            evidence_level="1b"
        )

        assert result.results == []


# ===========================================================================
# Test: Normalization Methods
# ===========================================================================

class TestNormalization:
    """Test entity normalization methods."""

    def test_normalize_intervention_no_normalizer(self, graph_search):
        """Normalization returns original when normalizer unavailable."""
        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', False):
            result = graph_search._normalize_intervention("UBE")
            assert result == "UBE"

    def test_normalize_intervention_with_normalizer(self, graph_search, mock_normalizer):
        """Normalization applied when normalizer available."""
        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', True):
            with patch('src.solver.graph_search.get_normalizer', return_value=mock_normalizer):
                graph_search._normalizer = mock_normalizer

                result = graph_search._normalize_intervention("UBE")
                assert result == "BESS"

    def test_normalize_outcome_no_normalizer(self, graph_search):
        """Normalization returns original when normalizer unavailable."""
        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', False):
            result = graph_search._normalize_outcome("VAS")
            assert result == "VAS"

    def test_normalize_outcome_with_normalizer(self, graph_search, mock_normalizer):
        """Normalization applied when normalizer available."""
        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', True):
            with patch('src.solver.graph_search.get_normalizer', return_value=mock_normalizer):
                graph_search._normalizer = mock_normalizer

                result = graph_search._normalize_outcome("VAS")
                assert result == "Visual Analog Scale"

    def test_normalization_error_handling(self, graph_search, mock_normalizer):
        """Normalization errors are handled gracefully."""
        mock_normalizer.normalize_intervention.side_effect = Exception("Normalization error")

        with patch('src.solver.graph_search.NORMALIZER_AVAILABLE', True):
            with patch('src.solver.graph_search.get_normalizer', return_value=mock_normalizer):
                graph_search._normalizer = mock_normalizer

                # Should return original on error
                result = graph_search._normalize_intervention("UBE")
                assert result == "UBE"


# ===========================================================================
# Test: GraphSearchResult
# ===========================================================================

class TestGraphSearchResult:
    """Test GraphSearchResult dataclass."""

    def test_basic_creation(self):
        """Basic result creation."""
        result = GraphSearchResult(
            query="test_query",
            results=[{"key": "value"}],
            cypher_query="MATCH (n) RETURN n",
            execution_time_ms=123.45
        )

        assert result.query == "test_query"
        assert len(result.results) == 1
        assert result.execution_time_ms == 123.45

    def test_default_values(self):
        """Default values for optional fields."""
        result = GraphSearchResult(
            query="test",
            results=[]
        )

        assert result.cypher_query == ""
        assert result.execution_time_ms == 0.0


# ===========================================================================
# Test: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_query_results(self, graph_search, mock_neo4j_client):
        """Empty results from database."""
        mock_neo4j_client.run_query.return_value = []

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="NonExistent",
            direction="improved"
        )

        assert result.results == []
        assert isinstance(result.execution_time_ms, (int, float))

    @pytest.mark.asyncio
    async def test_special_characters_in_names(self, graph_search, mock_neo4j_client):
        """Special characters in search terms."""
        mock_neo4j_client.run_query.return_value = []

        # Should not crash with special characters
        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS (Visual Analog Scale)",
            direction="improved"
        )

        assert result.results == []

    @pytest.mark.asyncio
    async def test_very_long_result_list(self, graph_search, mock_neo4j_client):
        """Handle large result sets."""
        mock_data = [
            {"intervention": f"Surgery_{i}", "value": str(i)}
            for i in range(1000)
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved"
        )

        assert len(result.results) == 1000

    @pytest.mark.asyncio
    async def test_null_values_in_results(self, graph_search, mock_neo4j_client):
        """Handle null/None values in results."""
        mock_data = [
            {
                "intervention": "TLIF",
                "value": None,
                "p_value": None,
                "source_paper_id": "paper_001"
            }
        ]
        mock_neo4j_client.run_query.return_value = mock_data

        result = await graph_search.search_interventions_for_outcome(
            outcome_name="VAS",
            direction="improved"
        )

        assert len(result.results) == 1
        assert result.results[0]["value"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
