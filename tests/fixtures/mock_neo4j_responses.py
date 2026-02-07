"""Mock Neo4j Response Data.

Mock responses for Neo4j queries to enable testing without database.
"""

from typing import List, Dict, Any


# Mock Cypher query responses
MOCK_PAPER_QUERY_RESPONSE = [
    {
        "p": {
            "paper_id": "TLIF_001",
            "title": "TLIF for Lumbar Stenosis RCT",
            "authors": ["Kim SH", "Park JY"],
            "year": 2023,
            "journal": "Spine",
            "sub_domain": "Degenerative",
            "evidence_level": "1b",
        }
    }
]

MOCK_INTERVENTION_HIERARCHY_RESPONSE = [
    {
        "parent": {
            "name": "Interbody Fusion",
            "category": "fusion",
            "full_name": "Interbody Fusion Techniques",
        },
        "levels": 1,
    },
    {
        "parent": {
            "name": "Minimally Invasive Surgery",
            "category": "approach",
            "full_name": "Minimally Invasive Spine Surgery",
        },
        "levels": 2,
    },
]

MOCK_INTERVENTION_CHILDREN_RESPONSE = [
    {
        "child": {
            "name": "TLIF",
            "full_name": "Transforaminal Lumbar Interbody Fusion",
            "category": "fusion",
            "is_minimally_invasive": True,
        }
    },
    {
        "child": {
            "name": "OLIF",
            "full_name": "Oblique Lateral Interbody Fusion",
            "category": "fusion",
            "is_minimally_invasive": True,
        }
    },
    {
        "child": {
            "name": "ALIF",
            "full_name": "Anterior Lumbar Interbody Fusion",
            "category": "fusion",
            "is_minimally_invasive": False,
        }
    },
]

MOCK_EFFECTIVE_INTERVENTIONS_RESPONSE = [
    {
        "i": {"name": "TLIF"},
        "r": {
            "value": "95.8%",
            "value_control": "88.3%",
            "p_value": 0.002,
            "is_significant": True,
            "direction": "improved",
            "source_paper_id": "TLIF_001",
        },
        "p": {
            "paper_id": "TLIF_001",
            "title": "TLIF RCT",
            "evidence_level": "1b",
        },
    },
    {
        "i": {"name": "OLIF"},
        "r": {
            "value": "94.2%",
            "p_value": 0.001,
            "is_significant": True,
            "direction": "improved",
            "source_paper_id": "OLIF_META_001",
        },
        "p": {
            "paper_id": "OLIF_META_001",
            "title": "OLIF Meta-analysis",
            "evidence_level": "1a",
        },
    },
]

MOCK_PATHOLOGY_INTERVENTIONS_RESPONSE = [
    {
        "i": {"name": "TLIF"},
        "count": 25,
        "evidence_levels": ["1b", "2a", "2b"],
    },
    {
        "i": {"name": "UBE"},
        "count": 18,
        "evidence_levels": ["2b", "3"],
    },
]

MOCK_CONFLICTING_RESULTS_RESPONSE = [
    {
        "i": {"name": "OLIF"},
        "o": {"name": "Subsidence Rate"},
        "r1": {
            "value": "8.2%",
            "direction": "unchanged",
            "is_significant": False,
            "source_paper_id": "OLIF_META_001",
        },
        "r2": {
            "value": "18.5%",
            "direction": "worsened",
            "is_significant": True,
            "source_paper_id": "OLIF_002",
        },
        "p1": {
            "paper_id": "OLIF_META_001",
            "title": "OLIF Meta-analysis",
            "evidence_level": "1a",
        },
        "p2": {
            "paper_id": "OLIF_002",
            "title": "OLIF Retrospective Study",
            "evidence_level": "2b",
        },
    }
]

MOCK_PAPER_RELATIONS_RESPONSE = [
    {
        "type": "STUDIES",
        "target": {"name": "Lumbar Stenosis"},
        "properties": {"is_primary": True},
    },
    {
        "type": "INVESTIGATES",
        "target": {"name": "TLIF"},
        "properties": {"is_comparison": False},
    },
    {
        "type": "AFFECTS",
        "target": {"name": "Fusion Rate"},
        "properties": {
            "value": "95.8%",
            "p_value": 0.002,
            "is_significant": True,
        },
    },
]

MOCK_GRAPH_STATS_RESPONSE = {
    "nodes": {
        "Paper": 150,
        "Intervention": 45,
        "Outcome": 30,
        "Pathology": 20,
    },
    "relationships": {
        "STUDIES": 180,
        "INVESTIGATES": 250,
        "AFFECTS": 420,
        "IS_A": 60,
        "TREATS": 85,
    },
}


class MockNeo4jQueryBuilder:
    """Build mock Neo4j query responses."""

    @staticmethod
    def get_paper_response(paper_id: str) -> List[Dict[str, Any]]:
        """Get mock paper query response."""
        return MOCK_PAPER_QUERY_RESPONSE

    @staticmethod
    def get_hierarchy_response(intervention: str) -> List[Dict[str, Any]]:
        """Get mock hierarchy response."""
        return MOCK_INTERVENTION_HIERARCHY_RESPONSE

    @staticmethod
    def get_children_response(intervention: str) -> List[Dict[str, Any]]:
        """Get mock children response."""
        return MOCK_INTERVENTION_CHILDREN_RESPONSE

    @staticmethod
    def get_effective_interventions_response(outcome: str) -> List[Dict[str, Any]]:
        """Get mock effective interventions response."""
        return MOCK_EFFECTIVE_INTERVENTIONS_RESPONSE

    @staticmethod
    def get_pathology_interventions_response(pathology: str) -> List[Dict[str, Any]]:
        """Get mock pathology interventions response."""
        return MOCK_PATHOLOGY_INTERVENTIONS_RESPONSE

    @staticmethod
    def get_conflicting_results_response(intervention: str) -> List[Dict[str, Any]]:
        """Get mock conflicting results response."""
        return MOCK_CONFLICTING_RESULTS_RESPONSE

    @staticmethod
    def get_paper_relations_response(paper_id: str) -> List[Dict[str, Any]]:
        """Get mock paper relations response."""
        return MOCK_PAPER_RELATIONS_RESPONSE

    @staticmethod
    def get_stats_response() -> Dict[str, Any]:
        """Get mock graph stats response."""
        return MOCK_GRAPH_STATS_RESPONSE


# Helper to create mock query results
def create_mock_query_result(
    query_type: str,
    **kwargs
) -> List[Dict[str, Any]]:
    """Create mock query result based on type.

    Args:
        query_type: Type of query (paper, hierarchy, effective, etc.)
        **kwargs: Additional parameters

    Returns:
        List of mock result dictionaries
    """
    builder = MockNeo4jQueryBuilder()

    if query_type == "paper":
        return builder.get_paper_response(kwargs.get("paper_id", ""))
    elif query_type == "hierarchy":
        return builder.get_hierarchy_response(kwargs.get("intervention", ""))
    elif query_type == "children":
        return builder.get_children_response(kwargs.get("intervention", ""))
    elif query_type == "effective":
        return builder.get_effective_interventions_response(kwargs.get("outcome", ""))
    elif query_type == "pathology":
        return builder.get_pathology_interventions_response(kwargs.get("pathology", ""))
    elif query_type == "conflicts":
        return builder.get_conflicting_results_response(kwargs.get("intervention", ""))
    elif query_type == "relations":
        return builder.get_paper_relations_response(kwargs.get("paper_id", ""))
    elif query_type == "stats":
        return builder.get_stats_response()
    else:
        return []
