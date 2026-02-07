"""Tests for taxonomy_manager module.

Tests for:
- get_parent_interventions
- get_child_interventions
- find_common_ancestor
- add_intervention_to_taxonomy
- get_full_taxonomy_tree
- validate_taxonomy
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.graph.taxonomy_manager import TaxonomyManager
from src.graph.neo4j_client import Neo4jClient


class TestTaxonomyManager:
    """Test TaxonomyManager class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Neo4j client."""
        client = AsyncMock(spec=Neo4jClient)
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create TaxonomyManager instance."""
        return TaxonomyManager(mock_client)

    def test_manager_initialization(self, mock_client):
        """Test manager initialization."""
        manager = TaxonomyManager(mock_client)

        assert manager.client is mock_client

    @pytest.mark.asyncio
    async def test_get_parent_interventions_with_parents(self, manager, mock_client):
        """Test get_parent_interventions with existing parents."""
        mock_client.run_query.return_value = [
            {"parents": ["Interbody Fusion", "Fusion Surgery"]}
        ]

        parents = await manager.get_parent_interventions("TLIF")

        assert len(parents) == 2
        assert "Interbody Fusion" in parents
        assert "Fusion Surgery" in parents
        mock_client.run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_parent_interventions_no_parents(self, manager, mock_client):
        """Test get_parent_interventions with no parents (root node)."""
        mock_client.run_query.return_value = [{"parents": []}]

        parents = await manager.get_parent_interventions("Fusion Surgery")

        assert parents == []

    @pytest.mark.asyncio
    async def test_get_parent_interventions_empty_result(self, manager, mock_client):
        """Test get_parent_interventions with empty result."""
        mock_client.run_query.return_value = []

        parents = await manager.get_parent_interventions("Unknown")

        assert parents == []

    @pytest.mark.asyncio
    async def test_get_parent_interventions_error(self, manager, mock_client):
        """Test get_parent_interventions with error."""
        mock_client.run_query.side_effect = Exception("Database error")

        parents = await manager.get_parent_interventions("TLIF")

        assert parents == []

    @pytest.mark.asyncio
    async def test_get_child_interventions_with_children(self, manager, mock_client):
        """Test get_child_interventions with existing children."""
        mock_client.get_intervention_children.return_value = [
            {"name": "TLIF", "full_name": "Transforaminal Lumbar Interbody Fusion"},
            {"name": "PLIF", "full_name": "Posterior Lumbar Interbody Fusion"},
            {"name": "ALIF", "full_name": "Anterior Lumbar Interbody Fusion"},
        ]

        children = await manager.get_child_interventions("Interbody Fusion")

        assert len(children) == 3
        assert "TLIF" in children
        assert "PLIF" in children
        assert "ALIF" in children

    @pytest.mark.asyncio
    async def test_get_child_interventions_no_children(self, manager, mock_client):
        """Test get_child_interventions with no children (leaf node)."""
        mock_client.get_intervention_children.return_value = []

        children = await manager.get_child_interventions("TLIF")

        assert children == []

    @pytest.mark.asyncio
    async def test_get_child_interventions_error(self, manager, mock_client):
        """Test get_child_interventions with error."""
        mock_client.get_intervention_children.side_effect = Exception("Error")

        children = await manager.get_child_interventions("Test")

        assert children == []

    @pytest.mark.asyncio
    async def test_find_common_ancestor_found(self, manager, mock_client):
        """Test find_common_ancestor with common ancestor."""
        mock_client.run_query.return_value = [
            {"common_ancestor": "Interbody Fusion"}
        ]

        ancestor = await manager.find_common_ancestor("TLIF", "PLIF")

        assert ancestor == "Interbody Fusion"
        mock_client.run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_common_ancestor_not_found(self, manager, mock_client):
        """Test find_common_ancestor with no common ancestor."""
        mock_client.run_query.return_value = [
            {"common_ancestor": None}
        ]

        ancestor = await manager.find_common_ancestor("TLIF", "Laminectomy")

        assert ancestor is None

    @pytest.mark.asyncio
    async def test_find_common_ancestor_same_intervention(self, manager, mock_client):
        """Test find_common_ancestor with same intervention."""
        mock_client.run_query.return_value = []

        ancestor = await manager.find_common_ancestor("TLIF", "TLIF")

        # Should handle gracefully
        assert ancestor is None

    @pytest.mark.asyncio
    async def test_find_common_ancestor_error(self, manager, mock_client):
        """Test find_common_ancestor with error."""
        mock_client.run_query.side_effect = Exception("Error")

        ancestor = await manager.find_common_ancestor("A", "B")

        assert ancestor is None

    @pytest.mark.asyncio
    async def test_add_intervention_to_taxonomy_success(self, manager, mock_client):
        """Test add_intervention_to_taxonomy success."""
        mock_client.run_write_query.return_value = {"nodes_created": 1}

        result = await manager.add_intervention_to_taxonomy(
            intervention="MIS-TLIF",
            parent="TLIF"
        )

        assert result is True
        mock_client.run_write_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_intervention_to_taxonomy_error(self, manager, mock_client):
        """Test add_intervention_to_taxonomy with error."""
        mock_client.run_write_query.side_effect = Exception("Error")

        result = await manager.add_intervention_to_taxonomy(
            intervention="Test",
            parent="Parent"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_full_taxonomy_tree(self, manager, mock_client):
        """Test get_full_taxonomy_tree."""
        mock_client.run_query.return_value = [
            {
                "root_name": "Fusion Surgery",
                "category": "fusion",
                "children": [
                    {"name": "TLIF", "full_name": "Transforaminal Lumbar Interbody Fusion", "category": "fusion", "approach": "posterior"},
                    {"name": "PLIF", "full_name": "Posterior Lumbar Interbody Fusion", "category": "fusion", "approach": "posterior"},
                ]
            },
            {
                "root_name": "Decompression Surgery",
                "category": "decompression",
                "children": [
                    {"name": "UBE", "full_name": "Unilateral Biportal Endoscopic", "category": "decompression", "approach": None},
                ]
            }
        ]

        tree = await manager.get_full_taxonomy_tree()

        assert "Fusion Surgery" in tree
        assert "Decompression Surgery" in tree
        assert tree["Fusion Surgery"]["category"] == "fusion"
        assert len(tree["Fusion Surgery"]["children"]) == 2
        assert "TLIF" in tree["Fusion Surgery"]["children"]

    @pytest.mark.asyncio
    async def test_get_full_taxonomy_tree_empty(self, manager, mock_client):
        """Test get_full_taxonomy_tree with empty result."""
        mock_client.run_query.return_value = []

        tree = await manager.get_full_taxonomy_tree()

        assert tree == {}

    @pytest.mark.asyncio
    async def test_get_full_taxonomy_tree_error(self, manager, mock_client):
        """Test get_full_taxonomy_tree with error."""
        mock_client.run_query.side_effect = Exception("Error")

        tree = await manager.get_full_taxonomy_tree()

        assert tree == {}

    @pytest.mark.asyncio
    async def test_get_intervention_level_leaf_node(self, manager, mock_client):
        """Test get_intervention_level for leaf node."""
        mock_client.run_query.return_value = [{"level": 2}]

        level = await manager.get_intervention_level("TLIF")

        assert level == 2

    @pytest.mark.asyncio
    async def test_get_intervention_level_root_node(self, manager, mock_client):
        """Test get_intervention_level for root node."""
        mock_client.run_query.return_value = [{"level": None}]

        level = await manager.get_intervention_level("Fusion Surgery")

        assert level == 0

    @pytest.mark.asyncio
    async def test_get_intervention_level_not_in_taxonomy(self, manager, mock_client):
        """Test get_intervention_level for node not in taxonomy."""
        mock_client.run_query.return_value = []

        level = await manager.get_intervention_level("Unknown")

        assert level == 0

    @pytest.mark.asyncio
    async def test_get_intervention_level_error(self, manager, mock_client):
        """Test get_intervention_level with error."""
        mock_client.run_query.side_effect = Exception("Error")

        level = await manager.get_intervention_level("Test")

        assert level == 0

    @pytest.mark.asyncio
    async def test_get_similar_interventions_found(self, manager, mock_client):
        """Test get_similar_interventions with results."""
        mock_client.run_query.return_value = [
            {
                "name": "PLIF",
                "full_name": "Posterior Lumbar Interbody Fusion",
                "distance": 2,
                "common_ancestor": "Interbody Fusion"
            },
            {
                "name": "ALIF",
                "full_name": "Anterior Lumbar Interbody Fusion",
                "distance": 2,
                "common_ancestor": "Interbody Fusion"
            }
        ]

        similar = await manager.get_similar_interventions("TLIF", max_distance=2)

        assert len(similar) == 2
        assert similar[0]["name"] == "PLIF"
        assert similar[0]["distance"] == 2
        assert similar[0]["common_ancestor"] == "Interbody Fusion"

    @pytest.mark.asyncio
    async def test_get_similar_interventions_none_found(self, manager, mock_client):
        """Test get_similar_interventions with no results."""
        mock_client.run_query.return_value = []

        similar = await manager.get_similar_interventions("Isolated Technique")

        assert similar == []

    @pytest.mark.asyncio
    async def test_get_similar_interventions_custom_distance(self, manager, mock_client):
        """Test get_similar_interventions with custom max_distance."""
        mock_client.run_query.return_value = []

        await manager.get_similar_interventions("TLIF", max_distance=3)

        # Check that max_distance was passed to query
        call_args = mock_client.run_query.call_args
        # call_args is (args, kwargs) tuple, we want the parameters dict in args[1]
        assert call_args[0][1]["max_distance"] == 3

    @pytest.mark.asyncio
    async def test_get_similar_interventions_error(self, manager, mock_client):
        """Test get_similar_interventions with error."""
        mock_client.run_query.side_effect = Exception("Error")

        similar = await manager.get_similar_interventions("Test")

        assert similar == []

    @pytest.mark.asyncio
    async def test_validate_taxonomy_no_issues(self, manager, mock_client):
        """Test validate_taxonomy with clean taxonomy."""
        # Mock all validation queries to return no issues
        mock_client.run_query.side_effect = [
            [],  # No orphans
            [],  # No cycles
            []   # No missing levels
        ]

        issues = await manager.validate_taxonomy()

        assert issues["orphans"] == []
        assert issues["cycles"] == []
        assert issues["warnings"] == []

    @pytest.mark.asyncio
    async def test_validate_taxonomy_orphans(self, manager, mock_client):
        """Test validate_taxonomy with orphan nodes."""
        mock_client.run_query.side_effect = [
            [{"orphan": "Orphan Node 1"}, {"orphan": "Orphan Node 2"}],  # Orphans
            [],  # No cycles
            []   # No missing levels
        ]

        issues = await manager.validate_taxonomy()

        assert len(issues["orphans"]) == 2
        assert "Orphan Node 1" in issues["orphans"]
        assert "Orphan Node 2" in issues["orphans"]

    @pytest.mark.asyncio
    async def test_validate_taxonomy_cycles(self, manager, mock_client):
        """Test validate_taxonomy with cycles."""
        mock_client.run_query.side_effect = [
            [],  # No orphans
            [{"cycle_node": "Circular Node"}],  # Cycle detected
            []   # No missing levels
        ]

        issues = await manager.validate_taxonomy()

        assert len(issues["cycles"]) == 1
        assert "Circular Node" in issues["cycles"]

    @pytest.mark.asyncio
    async def test_validate_taxonomy_missing_levels(self, manager, mock_client):
        """Test validate_taxonomy with missing level attributes."""
        mock_client.run_query.side_effect = [
            [],  # No orphans
            [],  # No cycles
            [{"missing_level": "Node A"}, {"missing_level": "Node B"}]  # Missing levels
        ]

        issues = await manager.validate_taxonomy()

        assert len(issues["warnings"]) == 2
        assert any("Node A" in w for w in issues["warnings"])
        assert any("Node B" in w for w in issues["warnings"])

    @pytest.mark.asyncio
    async def test_validate_taxonomy_all_issues(self, manager, mock_client):
        """Test validate_taxonomy with all types of issues."""
        mock_client.run_query.side_effect = [
            [{"orphan": "Orphan"}],
            [{"cycle_node": "Cycle"}],
            [{"missing_level": "Missing"}]
        ]

        issues = await manager.validate_taxonomy()

        assert len(issues["orphans"]) == 1
        assert len(issues["cycles"]) == 1
        assert len(issues["warnings"]) == 1

    @pytest.mark.asyncio
    async def test_validate_taxonomy_error(self, manager, mock_client):
        """Test validate_taxonomy with error."""
        mock_client.run_query.side_effect = Exception("Database error")

        issues = await manager.validate_taxonomy()

        assert len(issues["warnings"]) >= 1
        assert any("error" in w.lower() for w in issues["warnings"])


class TestTaxonomyManagerQueries:
    """Test that queries are properly constructed."""

    @pytest.fixture
    def mock_client(self):
        return AsyncMock(spec=Neo4jClient)

    @pytest.fixture
    def manager(self, mock_client):
        return TaxonomyManager(mock_client)

    @pytest.mark.asyncio
    async def test_get_parent_interventions_query_params(self, manager, mock_client):
        """Test get_parent_interventions passes correct parameters."""
        mock_client.run_query.return_value = [{"parents": []}]

        await manager.get_parent_interventions("TLIF")

        call_args = mock_client.run_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "TLIF" in str(params.values())
        assert "IS_A" in query

    @pytest.mark.asyncio
    async def test_find_common_ancestor_query_params(self, manager, mock_client):
        """Test find_common_ancestor passes correct parameters."""
        mock_client.run_query.return_value = [{"common_ancestor": None}]

        await manager.find_common_ancestor("TLIF", "PLIF")

        call_args = mock_client.run_query.call_args
        params = call_args[0][1]

        assert params["intervention1"] == "TLIF"
        assert params["intervention2"] == "PLIF"

    @pytest.mark.asyncio
    async def test_add_intervention_query_params(self, manager, mock_client):
        """Test add_intervention_to_taxonomy passes correct parameters."""
        mock_client.run_write_query.return_value = {"nodes_created": 1}

        await manager.add_intervention_to_taxonomy("Child", "Parent")

        call_args = mock_client.run_write_query.call_args
        params = call_args[0][1]

        assert params["intervention"] == "Child"
        assert params["parent"] == "Parent"

    @pytest.mark.asyncio
    async def test_get_similar_interventions_query_params(self, manager, mock_client):
        """Test get_similar_interventions passes correct parameters."""
        mock_client.run_query.return_value = []

        await manager.get_similar_interventions("TLIF", max_distance=3)

        call_args = mock_client.run_query.call_args
        params = call_args[0][1]

        assert params["intervention_name"] == "TLIF"
        assert params["max_distance"] == 3


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.fixture
    def mock_client(self):
        return AsyncMock(spec=Neo4jClient)

    @pytest.fixture
    def manager(self, mock_client):
        return TaxonomyManager(mock_client)

    @pytest.mark.asyncio
    async def test_empty_intervention_name(self, manager, mock_client):
        """Test with empty intervention name."""
        mock_client.run_query.return_value = []

        parents = await manager.get_parent_interventions("")

        # Should handle gracefully
        assert parents == []

    @pytest.mark.asyncio
    async def test_none_intervention_name(self, manager, mock_client):
        """Test with None intervention name."""
        mock_client.run_query.side_effect = Exception("Invalid parameter")

        parents = await manager.get_parent_interventions(None)

        # Should handle error gracefully
        assert parents == []

    @pytest.mark.asyncio
    async def test_special_characters_in_name(self, manager, mock_client):
        """Test with special characters in name."""
        mock_client.run_query.return_value = []

        parents = await manager.get_parent_interventions("Test's Surgery (Modified)")

        # Should not break
        assert isinstance(parents, list)

    @pytest.mark.asyncio
    async def test_very_long_intervention_name(self, manager, mock_client):
        """Test with very long intervention name."""
        mock_client.run_query.return_value = []

        long_name = "A" * 1000
        children = await manager.get_child_interventions(long_name)

        assert isinstance(children, list)
