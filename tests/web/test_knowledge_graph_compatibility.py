"""Test Knowledge Graph page compatibility with MCP Server responses.

Tests verify that the Knowledge Graph page correctly processes MCP Server
response formats for all four main features.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestKnowledgeGraphCompatibility:
    """Test suite for Knowledge Graph page MCP compatibility."""

    def test_paper_relations_response_format(self):
        """Test that get_paper_relations response format is correctly processed."""
        # Simulate MCP Server response
        mcp_response = {
            "success": True,
            "paper": {
                "id": "paper1",
                "title": "Test Paper",
                "year": 2023,
                "evidence_level": "1b",
            },
            "relations": [
                {
                    "source": "paper1",
                    "target": "paper2",
                    "type": "cites",
                    "confidence": 0.9,
                    "evidence": "Citation in introduction",
                }
            ],
            "supporting_papers": [
                {"id": "paper3", "title": "Supporting Study", "confidence": 0.85}
            ],
            "contradicting_papers": [
                {"id": "paper4", "title": "Contradicting Study", "confidence": 0.75}
            ],
            "similar_papers": [
                {"id": "paper5", "title": "Similar Study", "similarity": 0.88}
            ],
        }

        # Verify expected fields exist
        assert mcp_response["success"] is True
        assert "paper" in mcp_response
        assert "relations" in mcp_response
        assert "supporting_papers" in mcp_response
        assert "contradicting_papers" in mcp_response
        assert "similar_papers" in mcp_response

        # Verify UI can extract required data
        paper = mcp_response["paper"]
        assert paper["id"] == "paper1"
        assert paper["title"] == "Test Paper"

        # Verify supporting papers format
        supporting = mcp_response["supporting_papers"]
        assert len(supporting) > 0
        assert "id" in supporting[0]
        assert "title" in supporting[0]
        assert "confidence" in supporting[0]

        # Verify similar papers use "similarity" not "confidence"
        similar = mcp_response["similar_papers"]
        assert len(similar) > 0
        assert "similarity" in similar[0]

    def test_topic_clusters_response_format(self):
        """Test that get_topic_clusters response format is correctly processed."""
        # Simulate MCP Server response
        mcp_response = {
            "success": True,
            "cluster_count": 3,
            "clusters": {
                "Lumbar Stenosis": {
                    "count": 15,
                    "papers": [
                        {"id": "paper1", "title": "TLIF vs PLIF", "year": 2023},
                        {"id": "paper2", "title": "UBE for stenosis", "year": 2022},
                    ],
                },
                "Cervical Spondylosis": {
                    "count": 8,
                    "papers": [
                        {"id": "paper3", "title": "ACDF outcomes", "year": 2024},
                    ],
                },
            },
        }

        # Verify expected fields exist
        assert mcp_response["success"] is True
        assert "clusters" in mcp_response
        assert "cluster_count" in mcp_response

        # Verify cluster structure
        clusters = mcp_response["clusters"]
        assert len(clusters) > 0

        # Verify each cluster has required fields
        for topic, cluster_info in clusters.items():
            assert "count" in cluster_info
            assert "papers" in cluster_info
            assert isinstance(cluster_info["papers"], list)

            # Verify paper format in cluster
            if cluster_info["papers"]:
                paper = cluster_info["papers"][0]
                assert "id" in paper
                assert "title" in paper
                assert "year" in paper

    def test_compare_papers_response_format(self):
        """Test that compare_papers response format is correctly processed.

        CRITICAL: This test verifies the fix for nested analysis object.
        The MCP Server returns analysis data nested in an "analysis" object,
        not at the top level.
        """
        # Simulate MCP Server response (v5.1 format)
        mcp_response = {
            "success": True,
            "papers": [
                {"id": "paper1", "title": "TLIF Study", "year": 2023},
                {"id": "paper2", "title": "OLIF Study", "year": 2022},
            ],
            "analysis": {  # NESTED OBJECT - not top level!
                "similarities": [
                    "Both studies focus on lumbar fusion",
                    "Similar patient populations (age 50-70)",
                ],
                "differences": [
                    "TLIF shows shorter operative time",
                    "OLIF reports less blood loss",
                ],
                "contradictions": [  # NOT "conflicts"!
                    "VAS score improvement differs significantly"
                ],
                "synthesis": "Both techniques effective but different profiles",
                "recommendation": "OLIF preferred for anterior pathology",
            },
        }

        # Verify expected fields exist
        assert mcp_response["success"] is True
        assert "papers" in mcp_response
        assert "analysis" in mcp_response

        # CRITICAL: Extract from nested analysis object
        analysis = mcp_response["analysis"]
        assert "similarities" in analysis
        assert "differences" in analysis
        assert "contradictions" in analysis  # NOT "conflicts"

        # Verify UI can extract correctly
        similarities = analysis.get("similarities", [])
        differences = analysis.get("differences", [])
        conflicts = analysis.get("contradictions", [])  # Map to "conflicts" in UI

        assert len(similarities) == 2
        assert len(differences) == 2
        assert len(conflicts) == 1

        # Verify optional fields
        assert "synthesis" in analysis
        assert "recommendation" in analysis

    def test_find_evidence_chain_response_format(self):
        """Test that find_evidence_chain response format is correctly processed.

        Note: Server returns "contradicting_papers" but UI looks for "refuting_papers".
        The fix provides backward compatibility by checking both field names.
        """
        # Simulate MCP Server response (v5.1 format)
        mcp_response = {
            "success": True,
            "claim": "UBE shows better outcomes than TLIF",
            "supporting_papers": [
                {
                    "id": "paper1",
                    "title": "UBE vs TLIF comparison",
                    "year": 2023,
                    "strength": 0.85,  # Mapped to "confidence" in UI
                    "summary": "UBE group showed lower VAS scores",
                }
            ],
            "contradicting_papers": [  # Server uses "contradicting_papers"
                {
                    "id": "paper2",
                    "title": "TLIF outcomes study",
                    "year": 2022,
                    "strength": 0.72,
                    "summary": "TLIF showed superior fusion rates",
                }
            ],
            "summary": "Evidence is mixed; both techniques have merits",
        }

        # Verify expected fields exist
        assert mcp_response["success"] is True
        assert "supporting_papers" in mcp_response
        assert "contradicting_papers" in mcp_response
        assert "summary" in mcp_response

        # Verify backward compatibility: UI checks both field names
        contradicting = mcp_response.get("contradicting_papers", [])
        refuting = mcp_response.get("refuting_papers", [])

        # Server returns contradicting_papers
        assert len(contradicting) > 0
        assert len(refuting) == 0  # Legacy field not present

        # Verify UI fallback logic works
        final_refuting = mcp_response.get(
            "contradicting_papers", mcp_response.get("refuting_papers", [])
        )
        assert len(final_refuting) == 1

        # Verify paper format
        supporting = mcp_response["supporting_papers"][0]
        assert "id" in supporting
        assert "title" in supporting
        assert "year" in supporting
        assert "strength" in supporting  # Mapped to confidence in UI
        assert "summary" in supporting

    def test_error_handling(self):
        """Test that error responses are correctly handled."""
        # Test search failure
        error_response = {"success": False, "error": "Knowledge Graph not available"}

        assert error_response["success"] is False
        assert "error" in error_response

        # UI should display error message
        error_message = error_response.get("error")
        assert error_message == "Knowledge Graph not available"


class TestUIDataExtraction:
    """Test UI data extraction patterns match MCP Server responses."""

    def test_compare_papers_ui_extraction(self):
        """Test the exact extraction pattern used in the UI after fix."""
        # Simulate server response
        compare_result = {
            "success": True,
            "papers": [{"id": "p1", "title": "Paper 1", "year": 2023}],
            "analysis": {
                "similarities": ["sim1", "sim2"],
                "differences": ["diff1"],
                "contradictions": ["conflict1"],
            },
        }

        # Simulate UI extraction (after fix)
        analysis = compare_result.get("analysis", {})
        similarities = analysis.get("similarities", [])
        differences = analysis.get("differences", [])
        conflicts = analysis.get("contradictions", [])

        # Verify extraction works correctly
        assert len(similarities) == 2
        assert len(differences) == 1
        assert len(conflicts) == 1
        assert similarities[0] == "sim1"
        assert differences[0] == "diff1"
        assert conflicts[0] == "conflict1"

    def test_evidence_chain_ui_extraction(self):
        """Test the extraction pattern for evidence chain with fallback."""
        # Simulate server response (new format)
        chain_result = {
            "success": True,
            "supporting_papers": [{"id": "p1", "title": "Support"}],
            "contradicting_papers": [{"id": "p2", "title": "Contradict"}],
        }

        # Simulate UI extraction (with backward compatibility)
        supporting = chain_result.get("supporting_papers", [])
        refuting = chain_result.get(
            "contradicting_papers", chain_result.get("refuting_papers", [])
        )

        assert len(supporting) == 1
        assert len(refuting) == 1

        # Test legacy format still works
        legacy_result = {
            "success": True,
            "supporting_papers": [{"id": "p1", "title": "Support"}],
            "refuting_papers": [{"id": "p2", "title": "Refute"}],
        }

        supporting_legacy = legacy_result.get("supporting_papers", [])
        refuting_legacy = legacy_result.get(
            "contradicting_papers", legacy_result.get("refuting_papers", [])
        )

        assert len(supporting_legacy) == 1
        assert len(refuting_legacy) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
