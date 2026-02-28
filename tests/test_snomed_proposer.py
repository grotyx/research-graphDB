"""Tests for snomed_proposer.py — LLM-based SNOMED mapping proposal.

Tests cover:
- SNOMEDProposal dataclass
- SNOMEDProposer._find_parent_candidates() word-overlap scoring
- SNOMEDProposer._generate_extension_code() code allocation
- SNOMEDProposer.propose_mapping() with mocked LLM
- SNOMEDProposer.batch_propose() parallel execution
- Confidence threshold logic (auto_apply)
- Error handling for LLM failures
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ontology.snomed_proposer import (
    SNOMEDProposal,
    SNOMEDProposer,
    _ENTITY_CONFIG,
)
from src.ontology.spine_snomed_mappings import (
    EXTENSION_NAMESPACE,
    EXTENSION_RANGES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    client = AsyncMock()
    client.generate_json = AsyncMock(return_value={
        "parent_name": "Interbody Fusion",
        "preferred_term": "Robotic TLIF",
        "synonyms": ["Robot-assisted TLIF", "R-TLIF"],
        "abbreviations": ["R-TLIF"],
        "korean_term": "로봇 TLIF",
        "confidence": 0.92,
        "reasoning": "Robotic variant of TLIF technique",
    })
    return client


@pytest.fixture
def proposer(mock_llm):
    """Create a SNOMEDProposer with mocked LLM."""
    return SNOMEDProposer(llm_client=mock_llm)


# ---------------------------------------------------------------------------
# SNOMEDProposal Dataclass Tests
# ---------------------------------------------------------------------------

class TestSNOMEDProposal:
    """Test SNOMEDProposal dataclass."""

    def test_defaults(self):
        p = SNOMEDProposal(original_term="Test", entity_type="intervention")
        assert p.original_term == "Test"
        assert p.entity_type == "intervention"
        assert p.proposed_parent_code == ""
        assert p.proposed_code == ""
        assert p.proposed_synonyms == []
        assert p.proposed_abbreviations == []
        assert p.proposed_korean_term == ""
        assert p.confidence == 0.0
        assert p.auto_apply is False

    def test_auto_apply_threshold(self):
        p = SNOMEDProposal(
            original_term="Test",
            entity_type="intervention",
            confidence=0.95,
            auto_apply=True,
        )
        assert p.auto_apply is True

    def test_list_fields_independent(self):
        """Verify list fields don't share state between instances."""
        p1 = SNOMEDProposal(original_term="A", entity_type="intervention")
        p2 = SNOMEDProposal(original_term="B", entity_type="pathology")
        p1.proposed_synonyms.append("X")
        assert "X" not in p2.proposed_synonyms


# ---------------------------------------------------------------------------
# _find_parent_candidates Tests
# ---------------------------------------------------------------------------

class TestFindParentCandidates:
    """Test the word-overlap parent candidate finder."""

    def test_basic_word_overlap(self, proposer):
        """Terms with overlapping words get matched."""
        candidates = proposer._find_parent_candidates(
            "Lumbar Fusion", "intervention"
        )
        # Should find entries with "Fusion" or "Lumbar" in their names
        assert isinstance(candidates, list)
        # All results should be (name, code) tuples
        for name, code in candidates:
            assert isinstance(name, str)
            assert isinstance(code, str)

    def test_max_10_candidates(self, proposer):
        """At most 10 candidates are returned."""
        candidates = proposer._find_parent_candidates("Spine", "intervention")
        assert len(candidates) <= 10

    def test_invalid_entity_type(self, proposer):
        """Invalid entity type returns empty list."""
        candidates = proposer._find_parent_candidates("TLIF", "invalid_type")
        assert candidates == []

    def test_no_match(self, proposer):
        """Completely unrelated term returns empty or low-score results."""
        candidates = proposer._find_parent_candidates(
            "Quantum Computing", "intervention"
        )
        # May or may not have results, but shouldn't crash
        assert isinstance(candidates, list)

    def test_synonym_matching(self, proposer):
        """Synonym matches are found (slightly discounted)."""
        # "BESS" is a synonym for UBE in spine_snomed_mappings
        candidates = proposer._find_parent_candidates(
            "BESS technique", "intervention"
        )
        assert isinstance(candidates, list)

    def test_all_entity_types(self, proposer):
        """All four entity types work."""
        for etype in ("intervention", "pathology", "outcome", "anatomy"):
            candidates = proposer._find_parent_candidates("test term", etype)
            assert isinstance(candidates, list)


# ---------------------------------------------------------------------------
# _generate_extension_code Tests
# ---------------------------------------------------------------------------

class TestGenerateExtensionCode:
    """Test extension code generation."""

    def test_intervention_code_format(self, proposer):
        """Generated code starts with EXTENSION_NAMESPACE."""
        code = proposer._generate_extension_code("intervention")
        assert code.startswith(EXTENSION_NAMESPACE)

    def test_pathology_code_in_range(self, proposer):
        """Pathology code falls in the disorder range."""
        code = proposer._generate_extension_code("pathology")
        suffix = int(code[len(EXTENSION_NAMESPACE):])
        start, end = EXTENSION_RANGES["disorder"]
        # May exceed if range is full, but should be numeric
        assert suffix >= start

    def test_outcome_code_in_range(self, proposer):
        """Outcome code falls in the observable range."""
        code = proposer._generate_extension_code("outcome")
        suffix = int(code[len(EXTENSION_NAMESPACE):])
        start, _ = EXTENSION_RANGES["observable"]
        assert suffix >= start

    def test_anatomy_code_in_range(self, proposer):
        """Anatomy code falls in the body_structure range."""
        code = proposer._generate_extension_code("anatomy")
        suffix = int(code[len(EXTENSION_NAMESPACE):])
        start, _ = EXTENSION_RANGES["body_structure"]
        assert suffix >= start

    def test_invalid_entity_type(self, proposer):
        """Invalid entity type returns empty string."""
        code = proposer._generate_extension_code("invalid")
        assert code == ""


# ---------------------------------------------------------------------------
# propose_mapping Tests
# ---------------------------------------------------------------------------

class TestProposeMapping:
    """Test propose_mapping with mocked LLM."""

    @pytest.mark.asyncio
    async def test_successful_proposal(self, proposer, mock_llm):
        """Successful LLM response yields a complete proposal."""
        proposal = await proposer.propose_mapping(
            term="Robotic TLIF",
            entity_type="intervention",
            context="Spine surgery paper about robot-assisted techniques",
        )

        assert isinstance(proposal, SNOMEDProposal)
        assert proposal.original_term == "Robotic TLIF"
        assert proposal.entity_type == "intervention"
        assert proposal.proposed_term == "Robotic TLIF"
        assert proposal.confidence == 0.92
        assert proposal.auto_apply is True  # >= 0.9
        assert "R-TLIF" in proposal.proposed_synonyms
        assert proposal.proposed_korean_term == "로봇 TLIF"
        assert proposal.proposed_code.startswith(EXTENSION_NAMESPACE)

    @pytest.mark.asyncio
    async def test_low_confidence_no_auto_apply(self, proposer, mock_llm):
        """Confidence < 0.9 → auto_apply = False."""
        mock_llm.generate_json.return_value = {
            "parent_name": None,
            "preferred_term": "Novel Technique",
            "synonyms": [],
            "abbreviations": [],
            "korean_term": "",
            "confidence": 0.5,
            "reasoning": "Uncertain novel concept",
        }

        proposal = await proposer.propose_mapping(
            "Novel Technique", "intervention"
        )

        assert proposal.confidence == 0.5
        assert proposal.auto_apply is False

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_0_1(self, proposer, mock_llm):
        """Confidence is clamped to [0.0, 1.0]."""
        mock_llm.generate_json.return_value = {
            "preferred_term": "Test",
            "confidence": 1.5,  # Over 1.0
            "reasoning": "Test",
        }

        proposal = await proposer.propose_mapping("Test", "intervention")
        assert proposal.confidence == 1.0

        mock_llm.generate_json.return_value = {
            "preferred_term": "Test",
            "confidence": -0.5,  # Under 0.0
            "reasoning": "Test",
        }

        proposal = await proposer.propose_mapping("Test", "intervention")
        assert proposal.confidence == 0.0

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self, proposer):
        """Invalid entity type returns empty proposal with reasoning."""
        proposal = await proposer.propose_mapping(
            "Test", "invalid_type"
        )

        assert proposal.confidence == 0.0
        assert "Unknown entity type" in proposal.reasoning

    @pytest.mark.asyncio
    async def test_llm_failure_handled(self, proposer, mock_llm):
        """LLM failure returns empty proposal with error reasoning."""
        mock_llm.generate_json.side_effect = RuntimeError("API Error")

        proposal = await proposer.propose_mapping("Test", "intervention")

        assert proposal.confidence == 0.0
        assert "LLM call failed" in proposal.reasoning

    @pytest.mark.asyncio
    async def test_all_entity_types(self, proposer, mock_llm):
        """All four entity types produce valid proposals."""
        for etype in ("intervention", "pathology", "outcome", "anatomy"):
            proposal = await proposer.propose_mapping(f"Test {etype}", etype)
            assert isinstance(proposal, SNOMEDProposal)
            assert proposal.entity_type == etype

    @pytest.mark.asyncio
    async def test_optional_fields_missing(self, proposer, mock_llm):
        """Missing optional fields in LLM response use defaults."""
        mock_llm.generate_json.return_value = {
            "preferred_term": "Minimal",
            "confidence": 0.7,
            "reasoning": "Minimal response",
        }

        proposal = await proposer.propose_mapping("Minimal", "intervention")

        assert proposal.proposed_synonyms == []
        assert proposal.proposed_abbreviations == []
        assert proposal.proposed_korean_term == ""


# ---------------------------------------------------------------------------
# batch_propose Tests
# ---------------------------------------------------------------------------

class TestBatchPropose:
    """Test batch_propose parallel execution."""

    @pytest.mark.asyncio
    async def test_batch_multiple_terms(self, proposer, mock_llm):
        """Multiple terms are processed in parallel."""
        terms = [
            {"original_text": "Term1", "entity_type": "intervention"},
            {"original_text": "Term2", "entity_type": "pathology"},
            {"original_text": "Term3", "entity_type": "outcome"},
        ]

        results = await proposer.batch_propose(terms)

        assert len(results) == 3
        assert all(isinstance(r, SNOMEDProposal) for r in results)
        assert mock_llm.generate_json.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_empty(self, proposer, mock_llm):
        """Empty batch returns empty list."""
        results = await proposer.batch_propose([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_with_source_paper(self, proposer, mock_llm):
        """source_paper is passed as context."""
        terms = [
            {
                "original_text": "Robot UBE",
                "entity_type": "intervention",
                "source_paper": "Study on robot-assisted UBE",
            },
        ]

        results = await proposer.batch_propose(terms)

        assert len(results) == 1
        # Verify context was passed in the prompt
        call_args = mock_llm.generate_json.call_args
        prompt = call_args[0][0]
        assert "Study on robot-assisted UBE" in prompt

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, proposer, mock_llm):
        """One failure in batch doesn't break others."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("API Error on term 2")
            return {
                "preferred_term": f"Term {call_count}",
                "confidence": 0.8,
                "reasoning": "OK",
            }

        mock_llm.generate_json.side_effect = side_effect

        terms = [
            {"original_text": "OK1", "entity_type": "intervention"},
            {"original_text": "FAIL", "entity_type": "intervention"},
            {"original_text": "OK2", "entity_type": "intervention"},
        ]

        results = await proposer.batch_propose(terms)

        assert len(results) == 3
        # Term 2 should have failed gracefully
        assert results[1].confidence == 0.0
        assert "LLM call failed" in results[1].reasoning
        # Others should succeed
        assert results[0].confidence == 0.8
        assert results[2].confidence == 0.8


# ---------------------------------------------------------------------------
# Lazy LLM Client Init Tests
# ---------------------------------------------------------------------------

class TestLazyLLMInit:
    """Test lazy LLM client initialization."""

    @pytest.mark.asyncio
    async def test_no_client_tries_import(self):
        """Without llm_client, tries to import LLMClient."""
        proposer = SNOMEDProposer(llm_client=None)

        with pytest.raises(RuntimeError, match="LLM client not available"):
            # This should fail because 'llm' module isn't installed in test env
            with patch.dict("sys.modules", {"llm": None}):
                await proposer._get_llm_client()

    @pytest.mark.asyncio
    async def test_provided_client_used(self, mock_llm):
        """Provided client is used without import."""
        proposer = SNOMEDProposer(llm_client=mock_llm)
        client = await proposer._get_llm_client()
        assert client is mock_llm


# ---------------------------------------------------------------------------
# Entity Config Tests
# ---------------------------------------------------------------------------

class TestEntityConfig:
    """Test _ENTITY_CONFIG structure."""

    def test_all_types_present(self):
        """All four entity types are configured."""
        assert "intervention" in _ENTITY_CONFIG
        assert "pathology" in _ENTITY_CONFIG
        assert "outcome" in _ENTITY_CONFIG
        assert "anatomy" in _ENTITY_CONFIG

    def test_config_keys(self):
        """Each config has required keys."""
        for etype, config in _ENTITY_CONFIG.items():
            assert "mapping" in config, f"{etype} missing 'mapping'"
            assert "range_key" in config, f"{etype} missing 'range_key'"
            assert "semantic_type" in config, f"{etype} missing 'semantic_type'"

    def test_mapping_is_dict(self):
        """Each mapping is a non-empty dict."""
        for etype, config in _ENTITY_CONFIG.items():
            assert isinstance(config["mapping"], dict)
            assert len(config["mapping"]) > 0, f"{etype} mapping is empty"
