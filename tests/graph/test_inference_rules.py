"""Tests for Inference Rules module.

Test coverage:
- Transitive hierarchy rules
- Comparability rules
- Evidence aggregation rules
- Conflict detection rules
- Inference engine API
"""
from core.exceptions import ValidationError

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.graph.inference_rules import (
    InferenceRule,
    InferenceRuleType,
    InferenceEngine,
    TRANSITIVE_HIERARCHY,
    TRANSITIVE_DESCENDANTS,
    TRANSITIVE_TREATMENT,
    COMPARABLE_SIBLINGS,
    COMPARABLE_BY_CATEGORY,
    COMPARISON_PAPERS,
    AGGREGATE_EVIDENCE,
    AGGREGATE_EVIDENCE_BY_PATHOLOGY,
    COMBINED_OUTCOMES,
    CONFLICT_DETECTION,
    CROSS_INTERVENTION_CONFLICTS,
    INDIRECT_TREATMENT,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4jClient."""
    client = AsyncMock()
    client.run_query = AsyncMock()
    return client


@pytest.fixture
def inference_engine(mock_neo4j_client):
    """InferenceEngine with mocked client."""
    return InferenceEngine(mock_neo4j_client)


# ============================================================================
# Test InferenceRule
# ============================================================================

def test_inference_rule_creation():
    """Test InferenceRule creation."""
    rule = InferenceRule(
        name="test_rule",
        rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
        description="Test rule",
        cypher_template="MATCH (n) WHERE n.id = $id RETURN n",
        parameters=["id"],
        confidence_weight=0.9,
    )

    assert rule.name == "test_rule"
    assert rule.rule_type == InferenceRuleType.TRANSITIVE_HIERARCHY
    assert rule.confidence_weight == 0.9
    assert "id" in rule.parameters


def test_inference_rule_generate_cypher():
    """Test Cypher generation with parameters."""
    rule = InferenceRule(
        name="test_rule",
        rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
        description="Test",
        cypher_template="MATCH (n {name: $intervention}) RETURN n",
        parameters=["intervention"],
    )

    cypher = rule.generate_cypher(intervention="TLIF")
    assert "$intervention" in cypher  # Neo4j parameter syntax
    assert "MATCH" in cypher


def test_inference_rule_missing_parameters():
    """Test error when required parameters are missing."""
    rule = InferenceRule(
        name="test_rule",
        rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
        description="Test",
        cypher_template="MATCH (n {name: $intervention}) RETURN n",
        parameters=["intervention"],
    )

    with pytest.raises(ValidationError, match="Missing required parameters"):
        rule.generate_cypher()


def test_inference_rule_validate_result():
    """Test result validation."""
    rule = TRANSITIVE_HIERARCHY

    assert rule.validate_result([]) is True
    assert rule.validate_result([{"ancestor": "Fusion"}]) is True
    assert rule.validate_result("invalid") is False


# ============================================================================
# Test Predefined Rules
# ============================================================================

def test_transitive_hierarchy_rule():
    """Test TRANSITIVE_HIERARCHY rule."""
    assert TRANSITIVE_HIERARCHY.name == "transitive_hierarchy"
    assert TRANSITIVE_HIERARCHY.rule_type == InferenceRuleType.TRANSITIVE_HIERARCHY
    assert "intervention" in TRANSITIVE_HIERARCHY.parameters
    assert TRANSITIVE_HIERARCHY.confidence_weight == 1.0

    # Note: Cypher templates use $parameter (Neo4j style), not {parameter}
    # So generate_cypher() will NOT substitute the value
    cypher = TRANSITIVE_HIERARCHY.cypher_template
    assert "$intervention" in cypher  # Check parameter placeholder
    assert "IS_A" in cypher
    assert "ancestor" in cypher.lower()


def test_transitive_descendants_rule():
    """Test TRANSITIVE_DESCENDANTS rule."""
    assert TRANSITIVE_DESCENDANTS.rule_type == InferenceRuleType.TRANSITIVE_HIERARCHY
    assert "intervention" in TRANSITIVE_DESCENDANTS.parameters

    cypher = TRANSITIVE_DESCENDANTS.cypher_template
    assert "$intervention" in cypher
    assert "descendant" in cypher.lower()


def test_transitive_treatment_rule():
    """Test TRANSITIVE_TREATMENT rule."""
    assert TRANSITIVE_TREATMENT.rule_type == InferenceRuleType.TRANSITIVE_TREATMENT
    assert TRANSITIVE_TREATMENT.confidence_weight == 0.8  # Inferred

    cypher = TRANSITIVE_TREATMENT.cypher_template
    assert "$intervention" in cypher
    assert "TREATS" in cypher


def test_comparable_siblings_rule():
    """Test COMPARABLE_SIBLINGS rule."""
    assert COMPARABLE_SIBLINGS.rule_type == InferenceRuleType.COMPARABLE_SIBLINGS
    assert "intervention" in COMPARABLE_SIBLINGS.parameters

    cypher = COMPARABLE_SIBLINGS.cypher_template
    assert "$intervention" in cypher
    assert "sibling" in cypher.lower()


def test_comparable_by_category_rule():
    """Test COMPARABLE_BY_CATEGORY rule."""
    assert COMPARABLE_BY_CATEGORY.confidence_weight == 0.7  # Broader

    cypher = COMPARABLE_BY_CATEGORY.cypher_template
    assert "$intervention" in cypher
    assert "category" in cypher.lower()


def test_comparison_papers_rule():
    """Test COMPARISON_PAPERS rule."""
    assert COMPARISON_PAPERS.rule_type == InferenceRuleType.COMPARISON_PAPERS

    cypher = COMPARISON_PAPERS.cypher_template
    assert "$intervention" in cypher
    assert "INVESTIGATES" in cypher


def test_aggregate_evidence_rule():
    """Test AGGREGATE_EVIDENCE rule."""
    assert AGGREGATE_EVIDENCE.rule_type == InferenceRuleType.AGGREGATE_EVIDENCE
    assert "intervention" in AGGREGATE_EVIDENCE.parameters
    assert "outcome" in AGGREGATE_EVIDENCE.parameters

    cypher = AGGREGATE_EVIDENCE.cypher_template
    assert "$intervention" in cypher
    assert "$outcome" in cypher
    assert "AFFECTS" in cypher


def test_aggregate_evidence_by_pathology_rule():
    """Test AGGREGATE_EVIDENCE_BY_PATHOLOGY rule."""
    assert "pathology" in AGGREGATE_EVIDENCE_BY_PATHOLOGY.parameters

    cypher = AGGREGATE_EVIDENCE_BY_PATHOLOGY.cypher_template
    assert "$intervention" in cypher
    assert "$pathology" in cypher
    assert "TREATS" in cypher


def test_combined_outcomes_rule():
    """Test COMBINED_OUTCOMES rule."""
    assert COMBINED_OUTCOMES.confidence_weight == 1.0  # Direct evidence

    cypher = COMBINED_OUTCOMES.cypher_template
    assert "$intervention" in cypher
    assert "AFFECTS" in cypher


def test_conflict_detection_rule():
    """Test CONFLICT_DETECTION rule."""
    assert CONFLICT_DETECTION.rule_type == InferenceRuleType.CONFLICT_DETECTION
    assert "intervention" in CONFLICT_DETECTION.parameters
    assert "outcome" in CONFLICT_DETECTION.parameters

    cypher = CONFLICT_DETECTION.cypher_template
    assert "$intervention" in cypher
    assert "$outcome" in cypher
    assert "direction" in cypher.lower()


def test_cross_intervention_conflicts_rule():
    """Test CROSS_INTERVENTION_CONFLICTS rule."""
    cypher = CROSS_INTERVENTION_CONFLICTS.cypher_template
    assert "$outcome" in cypher
    assert "i1.name < i2.name" in cypher  # Prevent duplicates


def test_indirect_treatment_rule():
    """Test INDIRECT_TREATMENT rule."""
    assert INDIRECT_TREATMENT.rule_type == InferenceRuleType.INDIRECT_TREATMENT
    assert INDIRECT_TREATMENT.confidence_weight == 0.7  # Indirect

    cypher = INDIRECT_TREATMENT.cypher_template
    assert "$pathology" in cypher
    assert "TREATS" in cypher


# ============================================================================
# Test InferenceEngine
# ============================================================================

def test_inference_engine_initialization(inference_engine):
    """Test InferenceEngine initialization."""
    assert inference_engine.client is not None
    assert len(inference_engine.rules) > 0
    assert "transitive_hierarchy" in inference_engine.rules


def test_inference_engine_load_rules(inference_engine):
    """Test rule loading."""
    rules = inference_engine.rules

    # Check all predefined rules are loaded
    expected_rules = [
        "transitive_hierarchy",
        "transitive_descendants",
        "transitive_treatment",
        "comparable_siblings",
        "comparable_by_category",
        "comparison_papers",
        "aggregate_evidence",
        "aggregate_evidence_by_pathology",
        "combined_outcomes",
        "conflict_detection",
        "cross_intervention_conflicts",
        "indirect_treatment",
    ]

    for rule_name in expected_rules:
        assert rule_name in rules


def test_inference_engine_get_rule(inference_engine):
    """Test get_rule method."""
    rule = inference_engine.get_rule("transitive_hierarchy")
    assert rule is not None
    assert rule.name == "transitive_hierarchy"

    # Non-existent rule
    assert inference_engine.get_rule("non_existent") is None


def test_inference_engine_list_rules(inference_engine):
    """Test list_rules method."""
    # All rules
    all_rules = inference_engine.list_rules()
    assert len(all_rules) > 0

    # Filter by type
    hierarchy_rules = inference_engine.list_rules(
        rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY
    )
    assert len(hierarchy_rules) >= 2  # At least transitive_hierarchy and descendants

    conflict_rules = inference_engine.list_rules(
        rule_type=InferenceRuleType.CONFLICT_DETECTION
    )
    assert len(conflict_rules) >= 2


@pytest.mark.asyncio
async def test_execute_rule(mock_neo4j_client, inference_engine):
    """Test execute_rule method."""
    mock_neo4j_client.run_query.return_value = [
        {"ancestor": "Interbody Fusion", "distance": 1},
        {"ancestor": "Fusion Surgery", "distance": 2},
    ]

    results = await inference_engine.execute_rule(
        "transitive_hierarchy",
        intervention="TLIF"
    )

    assert len(results) == 2
    assert results[0]["ancestor"] == "Interbody Fusion"
    assert results[0]["distance"] == 1

    # Verify client was called
    mock_neo4j_client.run_query.assert_called_once()


@pytest.mark.asyncio
async def test_execute_rule_unknown_rule(inference_engine):
    """Test execute_rule with unknown rule."""
    with pytest.raises(ValidationError, match="Unknown rule"):
        await inference_engine.execute_rule("unknown_rule")


@pytest.mark.asyncio
async def test_get_ancestors(mock_neo4j_client, inference_engine):
    """Test get_ancestors method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "ancestor": "Interbody Fusion",
            "full_name": "Interbody Fusion",
            "category": "fusion",
            "distance": 1,
            "path_nodes": ["TLIF", "Interbody Fusion"],
        },
        {
            "ancestor": "Fusion Surgery",
            "full_name": "Spinal Fusion Surgery",
            "category": "fusion",
            "distance": 2,
            "path_nodes": ["TLIF", "Interbody Fusion", "Fusion Surgery"],
        },
    ]

    ancestors = await inference_engine.get_ancestors("TLIF")

    assert len(ancestors) == 2
    assert ancestors[0]["ancestor"] == "Interbody Fusion"
    assert ancestors[0]["distance"] == 1
    assert ancestors[1]["ancestor"] == "Fusion Surgery"
    assert ancestors[1]["distance"] == 2


@pytest.mark.asyncio
async def test_get_descendants(mock_neo4j_client, inference_engine):
    """Test get_descendants method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "descendant": "TLIF",
            "full_name": "Transforaminal Lumbar Interbody Fusion",
            "category": "fusion",
            "distance": 1,
        },
        {
            "descendant": "MIS-TLIF",
            "full_name": "Minimally Invasive TLIF",
            "category": "fusion",
            "distance": 2,
        },
    ]

    descendants = await inference_engine.get_descendants("Interbody Fusion")

    assert len(descendants) == 2
    assert descendants[0]["descendant"] == "TLIF"


@pytest.mark.asyncio
async def test_get_comparable_interventions_strict(mock_neo4j_client, inference_engine):
    """Test get_comparable_interventions with strict=True."""
    mock_neo4j_client.run_query.return_value = [
        {
            "comparable": "PLIF",
            "full_name": "Posterior Lumbar Interbody Fusion",
            "category": "fusion",
            "approach": "posterior",
            "is_minimally_invasive": False,
            "shared_category": "Interbody Fusion",
        },
    ]

    comparable = await inference_engine.get_comparable_interventions("TLIF", strict=True)

    assert len(comparable) == 1
    assert comparable[0]["comparable"] == "PLIF"
    assert comparable[0]["shared_category"] == "Interbody Fusion"


@pytest.mark.asyncio
async def test_get_comparable_interventions_broad(mock_neo4j_client, inference_engine):
    """Test get_comparable_interventions with strict=False."""
    # First call: siblings
    mock_neo4j_client.run_query.side_effect = [
        [{"comparable": "PLIF", "shared_category": "Interbody Fusion"}],
        [{"comparable": "ALIF", "shared_category": "fusion"}],
    ]

    comparable = await inference_engine.get_comparable_interventions("TLIF", strict=False)

    assert len(comparable) == 2
    assert {item["comparable"] for item in comparable} == {"PLIF", "ALIF"}


@pytest.mark.asyncio
async def test_infer_treatments(mock_neo4j_client, inference_engine):
    """Test infer_treatments method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "pathology": "Lumbar Stenosis",
            "pathology_category": "degenerative",
            "via_intervention": "Interbody Fusion",
            "hierarchy_distance": 1,
        },
    ]

    treatments = await inference_engine.infer_treatments("TLIF")

    assert len(treatments) == 1
    assert treatments[0]["pathology"] == "Lumbar Stenosis"
    assert treatments[0]["via_intervention"] == "Interbody Fusion"


@pytest.mark.asyncio
async def test_find_comparison_studies(mock_neo4j_client, inference_engine):
    """Test find_comparison_studies method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": "paper_001",
            "title": "TLIF vs PLIF comparison",
            "year": 2023,
            "evidence_level": "2a",
            "compared_with": ["PLIF", "ALIF"],
            "num_comparisons": 2,
        },
    ]

    papers = await inference_engine.find_comparison_studies("TLIF")

    assert len(papers) == 1
    assert papers[0]["paper_id"] == "paper_001"
    assert "PLIF" in papers[0]["compared_with"]


@pytest.mark.asyncio
async def test_aggregate_evidence(mock_neo4j_client, inference_engine):
    """Test aggregate_evidence method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "direction": "improved",
            "value": "85.2%",
            "value_control": "78.3%",
            "p_value": 0.001,
            "effect_size": "1.23",
            "significant": True,
            "source_paper": "paper_001",
            "hierarchy_distance": 0,
        },
        {
            "intervention": "Interbody Fusion",
            "direction": "improved",
            "value": "82.0%",
            "p_value": 0.01,
            "significant": True,
            "source_paper": "paper_002",
            "hierarchy_distance": 1,
        },
    ]

    evidence = await inference_engine.aggregate_evidence("TLIF", "Fusion Rate")

    assert len(evidence) == 2
    assert evidence[0]["intervention"] == "TLIF"
    assert evidence[0]["hierarchy_distance"] == 0  # Direct
    assert evidence[1]["hierarchy_distance"] == 1  # Inferred


@pytest.mark.asyncio
async def test_aggregate_evidence_by_pathology(mock_neo4j_client, inference_engine):
    """Test aggregate_evidence_by_pathology method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "outcome": "VAS",
            "outcome_type": "clinical",
            "direction": "improved",
            "value": "2.3",
            "p_value": 0.001,
            "source_paper": "paper_001",
            "hierarchy_distance": 0,
        },
    ]

    evidence = await inference_engine.aggregate_evidence_by_pathology(
        "TLIF",
        "Lumbar Stenosis"
    )

    assert len(evidence) == 1
    assert evidence[0]["outcome"] == "VAS"


@pytest.mark.asyncio
async def test_get_all_outcomes(mock_neo4j_client, inference_engine):
    """Test get_all_outcomes method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "outcome": "VAS",
            "outcome_type": "clinical",
            "unit": "points",
            "desired_direction": "lower_is_better",
            "evidence_list": [
                {
                    "value": "2.3",
                    "p_value": 0.001,
                    "direction": "improved",
                    "is_significant": True,
                    "paper_id": "paper_001",
                    "evidence_level": "2b",
                }
            ],
        },
    ]

    outcomes = await inference_engine.get_all_outcomes("TLIF")

    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "VAS"
    assert len(outcomes[0]["evidence_list"]) == 1


@pytest.mark.asyncio
async def test_detect_conflicts(mock_neo4j_client, inference_engine):
    """Test detect_conflicts method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "outcome": "VAS",
            "direction1": "improved",
            "value1": "2.3",
            "p_value1": 0.001,
            "paper1": "paper_001",
            "direction2": "worsened",
            "value2": "5.2",
            "p_value2": 0.01,
            "paper2": "paper_002",
        },
    ]

    conflicts = await inference_engine.detect_conflicts("TLIF", "VAS")

    assert len(conflicts) == 1
    assert conflicts[0]["direction1"] == "improved"
    assert conflicts[0]["direction2"] == "worsened"
    assert conflicts[0]["paper1"] != conflicts[0]["paper2"]


@pytest.mark.asyncio
async def test_detect_cross_intervention_conflicts(mock_neo4j_client, inference_engine):
    """Test detect_cross_intervention_conflicts method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention1": "TLIF",
            "intervention2": "PLIF",
            "outcome": "VAS",
            "direction1": "improved",
            "value1": "2.3",
            "p_value1": 0.001,
            "paper1": "paper_001",
            "direction2": "unchanged",
            "value2": "4.5",
            "p_value2": 0.5,
            "paper2": "paper_002",
        },
    ]

    conflicts = await inference_engine.detect_cross_intervention_conflicts("VAS")

    assert len(conflicts) == 1
    assert conflicts[0]["intervention1"] == "TLIF"
    assert conflicts[0]["intervention2"] == "PLIF"


@pytest.mark.asyncio
async def test_find_indirect_treatments(mock_neo4j_client, inference_engine):
    """Test find_indirect_treatments method."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "full_name": "Transforaminal Lumbar Interbody Fusion",
            "via_intervention": "Interbody Fusion",
            "hierarchy_distance": 1,
        },
    ]

    indirect = await inference_engine.find_indirect_treatments("Lumbar Stenosis")

    assert len(indirect) == 1
    assert indirect[0]["intervention"] == "TLIF"
    assert indirect[0]["hierarchy_distance"] == 1


# ============================================================================
# Integration Tests (require real Neo4j)
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_transitive_hierarchy():
    """Integration test: transitive hierarchy with real Neo4j."""
    from src.graph.neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Test TLIF ancestors
            ancestors = await engine.get_ancestors("TLIF")
            assert len(ancestors) > 0
            ancestor_names = [a["ancestor"] for a in ancestors]
            assert "Interbody Fusion" in ancestor_names
            assert "Fusion Surgery" in ancestor_names

            # Test Fusion Surgery descendants
            descendants = await engine.get_descendants("Fusion Surgery")
            assert len(descendants) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_comparability():
    """Integration test: comparability analysis."""
    from src.graph.neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Test TLIF comparable interventions (strict)
            comparable = await engine.get_comparable_interventions("TLIF", strict=True)
            comparable_names = [c["comparable"] for c in comparable]
            assert "PLIF" in comparable_names or "ALIF" in comparable_names

            # Test broad comparability
            comparable_broad = await engine.get_comparable_interventions("TLIF", strict=False)
            assert len(comparable_broad) >= len(comparable)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_evidence_aggregation():
    """Integration test: evidence aggregation."""
    from src.graph.neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Get all outcomes for TLIF
            outcomes = await engine.get_all_outcomes("TLIF")
            # May be empty if no data, but should not error
            assert isinstance(outcomes, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
