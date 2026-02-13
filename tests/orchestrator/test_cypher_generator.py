"""Tests for CypherGenerator v7.15 QC.

Verifies:
1. generate() returns tuple[str, dict] (parameterized queries)
2. All generated Cypher uses $param syntax, never f-strings with user input
3. Each intent type (evidence_search, comparison, hierarchy, conflict) produces
   correct Cypher structure
4. Edge cases: empty entities, missing fields, fallback behavior
"""

import pytest
import re

from src.orchestrator.cypher_generator import (
    CypherGenerator,
    QueryIntent,
    ExtractedEntities,
)


class TestGenerateReturnType:
    """Verify generate() returns tuple[str, dict] for all intent paths."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_evidence_search_returns_tuple(self, generator):
        """evidence_search intent produces (str, dict) tuple."""
        entities = {
            "intent": "evidence_search",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        result = generator.generate("OLIF VAS", entities)
        assert isinstance(result, tuple), "generate() must return a tuple"
        assert len(result) == 2, "tuple must have exactly 2 elements"
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_comparison_returns_tuple(self, generator):
        """comparison intent produces (str, dict) tuple."""
        entities = {
            "intent": "comparison",
            "interventions": ["TLIF", "PLIF"],
            "outcomes": ["Fusion Rate"],
            "pathologies": [],
        }
        result = generator.generate("TLIF vs PLIF", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_hierarchy_returns_tuple(self, generator):
        """hierarchy intent produces (str, dict) tuple."""
        entities = {
            "intent": "hierarchy",
            "interventions": ["Fusion Surgery"],
            "outcomes": [],
            "pathologies": [],
        }
        result = generator.generate("Fusion Surgery types", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_conflict_returns_tuple(self, generator):
        """conflict intent produces (str, dict) tuple."""
        entities = {
            "intent": "conflict",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        result = generator.generate("OLIF VAS conflict", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_empty_entities_returns_tuple(self, generator):
        """Empty entities still produce (str, dict) tuple with fallback query."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": [],
            "pathologies": [],
        }
        result = generator.generate("", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)
        assert "MATCH" in cypher
        assert "LIMIT" in cypher

    def test_pathology_only_returns_tuple(self, generator):
        """Pathology-only search returns (str, dict) tuple."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": [],
            "pathologies": ["Lumbar Stenosis"],
        }
        result = generator.generate("Lumbar Stenosis treatment", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_outcome_only_returns_tuple(self, generator):
        """Outcome-only search returns (str, dict) tuple."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        result = generator.generate("VAS improvement", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_intervention_only_returns_tuple(self, generator):
        """Intervention-only search returns (str, dict) tuple."""
        entities = {
            "intent": "evidence_search",
            "interventions": ["TLIF"],
            "outcomes": [],
            "pathologies": [],
        }
        result = generator.generate("TLIF papers", entities)
        assert isinstance(result, tuple)
        cypher, params = result
        assert isinstance(cypher, str)
        assert isinstance(params, dict)


class TestParameterizedQuerySecurity:
    """Verify all generated Cypher uses $param syntax, never f-string injection."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def _assert_no_inline_values(self, cypher: str, params: dict):
        """Assert that parameter values do not appear as inline strings in the Cypher.

        If params contain e.g. {"intervention": "OLIF"}, the Cypher must NOT contain
        the literal 'OLIF' in a string position like {name: 'OLIF'}. It should use
        {name: $intervention} instead.
        """
        for key, value in params.items():
            if isinstance(value, str) and len(value) > 2:
                # Check that the value is not inline in a property match
                # e.g., {name: 'OLIF'} is BAD; {name: $intervention} is GOOD
                pattern = rf"\{{[^}}]*:\s*['\"]" + re.escape(value) + rf"['\"][^}}]*\}}"
                assert not re.search(pattern, cypher), (
                    f"Inline value '{value}' found in Cypher property match. "
                    f"Should use $param syntax. Query:\n{cypher}"
                )

    def _assert_uses_dollar_params(self, cypher: str, params: dict):
        """Assert that for each key in params, the Cypher uses $key syntax."""
        for key in params:
            assert f"${key}" in cypher, (
                f"Parameter ${key} not found in Cypher query. "
                f"All user-provided values must be parameterized.\nQuery:\n{cypher}"
            )

    def test_evidence_search_parameterized(self, generator):
        """evidence_search uses $intervention and $outcome parameters."""
        entities = {
            "intent": "evidence_search",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("OLIF VAS", entities)

        assert "intervention" in params
        assert "outcome" in params
        assert params["intervention"] == "OLIF"
        assert params["outcome"] == "VAS"
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_comparison_parameterized(self, generator):
        """comparison uses $intervention1, $intervention2, $outcome parameters."""
        entities = {
            "intent": "comparison",
            "interventions": ["TLIF", "PLIF"],
            "outcomes": ["Fusion Rate"],
            "pathologies": [],
        }
        cypher, params = generator.generate("TLIF vs PLIF fusion", entities)

        assert "intervention1" in params
        assert "intervention2" in params
        assert "outcome" in params
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_hierarchy_parameterized(self, generator):
        """hierarchy uses $intervention parameter."""
        entities = {
            "intent": "hierarchy",
            "interventions": ["TLIF"],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("TLIF hierarchy", entities)

        assert "intervention" in params
        assert params["intervention"] == "TLIF"
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_conflict_parameterized(self, generator):
        """conflict uses $intervention and $outcome parameters."""
        entities = {
            "intent": "conflict",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("OLIF VAS conflict", entities)

        assert "intervention" in params
        assert "outcome" in params
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_pathology_search_parameterized(self, generator):
        """Pathology-only search uses $pathology parameter."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": [],
            "pathologies": ["Lumbar Stenosis"],
        }
        cypher, params = generator.generate("Lumbar Stenosis surgery", entities)

        assert "pathology" in params
        assert params["pathology"] == "Lumbar Stenosis"
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_outcome_only_parameterized(self, generator):
        """Outcome-only search uses $outcome parameter."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("VAS improvement", entities)

        assert "outcome" in params
        assert params["outcome"] == "VAS"
        self._assert_uses_dollar_params(cypher, params)
        self._assert_no_inline_values(cypher, params)

    def test_malicious_input_not_injected(self, generator):
        """Verify that malicious input in entity values cannot inject Cypher."""
        malicious_value = "OLIF' OR 1=1 //"
        entities = {
            "intent": "evidence_search",
            "interventions": [malicious_value],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("test", entities)

        # The malicious value must be in params, NOT in the Cypher string
        assert params.get("intervention") == malicious_value
        assert malicious_value not in cypher


class TestEvidenceSearchCypher:
    """Test evidence_search intent Cypher structure."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_intervention_plus_outcome(self, generator):
        """Intervention + Outcome produces AFFECTS pattern."""
        entities = {
            "intent": "evidence_search",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("OLIF VAS", entities)

        assert "MATCH" in cypher
        assert "Intervention" in cypher
        assert "AFFECTS" in cypher
        assert "Outcome" in cypher
        assert "is_significant" in cypher
        assert "$intervention" in cypher
        assert "$outcome" in cypher

    def test_pathology_only_search(self, generator):
        """Pathology-only produces TREATS pattern."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": [],
            "pathologies": ["Lumbar Stenosis"],
        }
        cypher, params = generator.generate("Lumbar Stenosis surgery", entities)

        assert "MATCH" in cypher
        assert "TREATS" in cypher
        assert "Pathology" in cypher
        assert "$pathology" in cypher

    def test_outcome_only_search(self, generator):
        """Outcome-only produces reverse AFFECTS pattern with direction."""
        entities = {
            "intent": "evidence_search",
            "interventions": [],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("VAS improvement", entities)

        assert "MATCH" in cypher
        assert "AFFECTS" in cypher
        assert "Outcome" in cypher
        assert "direction" in cypher
        assert "$outcome" in cypher

    def test_intervention_only_search(self, generator):
        """Intervention-only returns papers via INVESTIGATES and IS_A hierarchy."""
        entities = {
            "intent": "evidence_search",
            "interventions": ["TLIF"],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("TLIF papers", entities)

        assert "MATCH" in cypher
        assert "Intervention" in cypher
        assert "$intervention" in cypher
        # Should include IS_A traversal for child interventions
        assert "IS_A" in cypher


class TestComparisonCypher:
    """Test comparison intent Cypher structure."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_two_interventions_with_outcome(self, generator):
        """Two interventions + outcome produces double MATCH AFFECTS pattern."""
        entities = {
            "intent": "comparison",
            "interventions": ["TLIF", "PLIF"],
            "outcomes": ["Fusion Rate"],
            "pathologies": [],
        }
        cypher, params = generator.generate("TLIF vs PLIF fusion", entities)

        assert "MATCH" in cypher
        assert "$intervention1" in cypher
        assert "$intervention2" in cypher
        assert "$outcome" in cypher
        assert params["intervention1"] == "TLIF"
        assert params["intervention2"] == "PLIF"
        assert params["outcome"] == "Fusion Rate"

    def test_single_intervention_comparison_fallback(self, generator):
        """Single intervention in comparison intent still produces valid query."""
        entities = {
            "intent": "comparison",
            "interventions": ["TLIF"],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("TLIF comparison", entities)

        assert isinstance(cypher, str)
        assert "MATCH" in cypher
        assert "$intervention" in cypher

    def test_no_interventions_comparison(self, generator):
        """No interventions in comparison returns minimal query."""
        entities = {
            "intent": "comparison",
            "interventions": [],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("compare", entities)

        assert isinstance(cypher, str)
        assert "MATCH" in cypher
        assert "LIMIT 0" in cypher


class TestHierarchyCypher:
    """Test hierarchy intent Cypher structure."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_hierarchy_with_intervention(self, generator):
        """Hierarchy query with an intervention produces IS_A traversal."""
        entities = {
            "intent": "hierarchy",
            "interventions": ["Fusion Surgery"],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("Fusion Surgery types", entities)

        assert "IS_A" in cypher
        assert "$intervention" in cypher
        assert "parent" in cypher.lower() or "child" in cypher.lower()
        assert params["intervention"] == "Fusion Surgery"

    def test_hierarchy_without_intervention(self, generator):
        """Hierarchy without intervention returns top-level categories."""
        entities = {
            "intent": "hierarchy",
            "interventions": [],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("types of surgery", entities)

        assert "MATCH" in cypher
        assert "Intervention" in cypher
        # No IS_A outgoing edge means top-level
        assert "NOT" in cypher or "IS_A" in cypher


class TestConflictCypher:
    """Test conflict intent Cypher structure."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_conflict_with_intervention_and_outcome(self, generator):
        """Conflict with intervention + outcome detects divergent directions."""
        entities = {
            "intent": "conflict",
            "interventions": ["OLIF"],
            "outcomes": ["VAS"],
            "pathologies": [],
        }
        cypher, params = generator.generate("OLIF VAS conflict", entities)

        assert "direction" in cypher
        assert "$intervention" in cypher
        assert "$outcome" in cypher
        # Must compare two different AFFECTS relationships
        assert "a1" in cypher and "a2" in cypher
        assert "source_paper_id" in cypher

    def test_conflict_with_intervention_only(self, generator):
        """Conflict with intervention-only searches all outcomes for conflicts."""
        entities = {
            "intent": "conflict",
            "interventions": ["OLIF"],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("OLIF conflict", entities)

        assert "direction" in cypher
        assert "$intervention" in cypher
        assert params["intervention"] == "OLIF"

    def test_conflict_no_entities(self, generator):
        """Conflict with no entities returns minimal fallback."""
        entities = {
            "intent": "conflict",
            "interventions": [],
            "outcomes": [],
            "pathologies": [],
        }
        cypher, params = generator.generate("conflict", entities)

        assert "MATCH" in cypher
        assert "LIMIT 0" in cypher


class TestIntentDetectionIntegration:
    """Test extract_entities -> generate round-trip for each intent."""

    @pytest.fixture
    def generator(self):
        return CypherGenerator()

    def test_evidence_search_roundtrip(self, generator):
        """Evidence search query round-trip."""
        entities = generator.extract_entities("OLIF가 VAS 개선에 효과적인가?")
        assert entities["intent"] == "evidence_search"
        cypher, params = generator.generate("OLIF가 VAS 개선에 효과적인가?", entities)
        assert isinstance(cypher, str)
        assert isinstance(params, dict)
        assert len(params) > 0

    def test_comparison_roundtrip(self, generator):
        """Comparison query round-trip."""
        entities = generator.extract_entities("TLIF와 PLIF를 비교해줘")
        assert entities["intent"] == "comparison"
        cypher, params = generator.generate("TLIF와 PLIF를 비교해줘", entities)
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_hierarchy_roundtrip(self, generator):
        """Hierarchy query round-trip."""
        entities = generator.extract_entities("Endoscopic surgery의 종류는?")
        assert entities["intent"] == "hierarchy"
        cypher, params = generator.generate("Endoscopic surgery의 종류는?", entities)
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_conflict_roundtrip(self, generator):
        """Conflict query round-trip produces direction comparison."""
        entities = generator.extract_entities("OLIF의 간접 감압 효과에 대한 논란이 있는가?")
        assert entities["intent"] == "conflict"
        cypher, params = generator.generate(
            "OLIF의 간접 감압 효과에 대한 논란이 있는가?", entities
        )
        assert isinstance(cypher, str)
        assert isinstance(params, dict)
        assert "direction" in cypher


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
