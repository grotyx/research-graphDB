"""Extended tests for HybridRanker module.

Covers untested branches and edge cases:
- _score_graph_results scoring logic
- HybridResult methods (get_evidence_text, get_citation)
- Helper functions boundary conditions
- get_stats with neo4j_hybrid enabled
- GraphEvidence display text
- PaperNode citation formats
- GraphSearchResult methods
"""

import pytest
from unittest.mock import MagicMock

from src.solver.hybrid_ranker import (
    HybridRanker,
    HybridResult,
    get_evidence_weight,
    get_study_design_weight,
    get_sample_size_boost,
    get_recency_boost,
    get_citation_boost,
    get_source_credibility,
    EVIDENCE_LEVEL_WEIGHTS,
    STUDY_DESIGN_WEIGHTS,
    SOURCE_CREDIBILITY,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_AUTHORITY_WEIGHT,
    KEY_FINDING_BOOST,
    STATISTICS_BOOST,
    DIRECTION_IMPROVED_BOOST,
    DIRECTION_WORSENED_BOOST,
    DIRECTION_UNCHANGED_BOOST,
)
from src.solver.graph_result import (
    GraphEvidence,
    GraphSearchResult,
    PaperNode,
    InterventionHierarchy,
)


# ============================================================================
# Test: _score_graph_results
# ============================================================================

class TestScoreGraphResults:
    """Test _score_graph_results method."""

    @pytest.fixture
    def ranker(self):
        return HybridRanker(neo4j_client=None)

    def test_score_single_evidence_improved(self, ranker):
        """Score a single improved evidence."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="2.1",
            source_paper_id="p1",
            evidence_level="1b",
            direction="improved",
        )
        paper = PaperNode(paper_id="p1", title="Test Paper", evidence_level="1b")
        graph_result = GraphSearchResult(
            evidences=[evidence],
            paper_nodes=[paper],
        )

        results = ranker._score_graph_results(graph_result)
        assert len(results) == 1
        assert results[0].result_type == "graph"
        assert results[0].evidence == evidence
        assert results[0].paper == paper
        # Score = evidence_weight(1b) * direction_boost(improved)
        # = 0.9 * 1.2 = 1.08, capped at 1.0
        assert results[0].score == 1.0

    def test_score_worsened_direction(self, ranker):
        """Worsened direction gets lower boost."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="4.5",
            source_paper_id="p1",
            evidence_level="2b",
            direction="worsened",
        )
        graph_result = GraphSearchResult(evidences=[evidence], paper_nodes=[])

        results = ranker._score_graph_results(graph_result)
        # Score = 0.7 * 0.8 = 0.56
        assert abs(results[0].score - EVIDENCE_LEVEL_WEIGHTS["2b"] * DIRECTION_WORSENED_BOOST) < 1e-6

    def test_score_unchanged_direction(self, ranker):
        """Unchanged direction gets neutral boost."""
        evidence = GraphEvidence(
            intervention="UBE",
            outcome="ODI",
            value="35%",
            source_paper_id="p1",
            evidence_level="3",
            direction="unchanged",
        )
        graph_result = GraphSearchResult(evidences=[evidence], paper_nodes=[])

        results = ranker._score_graph_results(graph_result)
        expected = EVIDENCE_LEVEL_WEIGHTS["3"] * DIRECTION_UNCHANGED_BOOST
        assert abs(results[0].score - expected) < 1e-6

    def test_score_unknown_direction(self, ranker):
        """Unknown direction gets 1.0 boost (no modification)."""
        evidence = GraphEvidence(
            intervention="PLIF",
            outcome="Fusion Rate",
            value="92%",
            source_paper_id="p1",
            evidence_level="2a",
            direction="",  # Unknown
        )
        graph_result = GraphSearchResult(evidences=[evidence], paper_nodes=[])

        results = ranker._score_graph_results(graph_result)
        expected = EVIDENCE_LEVEL_WEIGHTS["2a"] * 1.0  # No direction boost
        assert abs(results[0].score - expected) < 1e-6

    def test_score_empty_evidences(self, ranker):
        """Empty evidences returns empty results."""
        graph_result = GraphSearchResult(evidences=[], paper_nodes=[])
        results = ranker._score_graph_results(graph_result)
        assert results == []

    def test_score_multiple_evidences(self, ranker):
        """Multiple evidences scored independently."""
        evidences = [
            GraphEvidence("TLIF", "VAS", "2.1", "p1", "1a", direction="improved"),
            GraphEvidence("TLIF", "ODI", "35", "p2", "4", direction="unchanged"),
        ]
        graph_result = GraphSearchResult(evidences=evidences, paper_nodes=[])

        results = ranker._score_graph_results(graph_result)
        assert len(results) == 2
        # Level 1a improved should score higher than level 4 unchanged
        assert results[0].score > results[1].score

    def test_score_paper_not_found(self, ranker):
        """Evidence with no matching paper node."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="2.1",
            source_paper_id="p_missing",
            evidence_level="2b",
            direction="improved",
        )
        paper = PaperNode(paper_id="p_other", title="Other Paper")
        graph_result = GraphSearchResult(
            evidences=[evidence],
            paper_nodes=[paper],
        )

        results = ranker._score_graph_results(graph_result)
        assert len(results) == 1
        assert results[0].paper is None

    def test_score_metadata_fields(self, ranker):
        """Score result metadata contains expected fields."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="2.1",
            source_paper_id="p1",
            evidence_level="1b",
            p_value=0.001,
            is_significant=True,
            direction="improved",
        )
        graph_result = GraphSearchResult(evidences=[evidence], paper_nodes=[])

        results = ranker._score_graph_results(graph_result)
        meta = results[0].metadata
        assert meta["evidence_level"] == "1b"
        assert meta["direction"] == "improved"
        assert meta["intervention"] == "TLIF"
        assert meta["outcome"] == "VAS"
        assert meta["p_value"] == 0.001
        assert meta["is_significant"] is True


# ============================================================================
# Test: HybridResult methods
# ============================================================================

class TestHybridResultMethods:
    """Test HybridResult methods."""

    def test_get_evidence_text_graph(self):
        """Graph result returns evidence display text."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="2.1",
            source_paper_id="p1",
            evidence_level="1b",
            p_value=0.001,
            direction="improved",
        )
        result = HybridResult(
            result_type="graph",
            score=0.9,
            content="Graph content",
            source_id="p1",
            evidence=evidence,
        )

        text = result.get_evidence_text()
        assert "TLIF" in text
        assert "VAS" in text
        assert "improved" in text

    def test_get_evidence_text_no_evidence(self):
        """Graph result without evidence returns empty."""
        result = HybridResult(
            result_type="graph",
            score=0.9,
            content="Some content",
            source_id="p1",
        )
        assert result.get_evidence_text() == ""

    def test_get_evidence_text_non_graph_non_vector(self):
        """Non-graph, non-vector result returns empty."""
        result = HybridResult(
            result_type="hybrid",
            score=0.9,
            content="Hybrid content",
            source_id="p1",
        )
        assert result.get_evidence_text() == ""

    def test_get_citation_graph(self):
        """Graph result returns paper citation."""
        paper = PaperNode(
            paper_id="p1",
            title="TLIF Study",
            authors=["Kim JH", "Park SM"],
            year=2023,
            journal="Spine",
        )
        result = HybridResult(
            result_type="graph",
            score=0.9,
            content="Graph content",
            source_id="p1",
            paper=paper,
        )

        citation = result.get_citation()
        assert "2023" in citation
        assert "TLIF Study" in citation
        assert "Spine" in citation

    def test_get_citation_no_paper(self):
        """Graph result without paper returns empty."""
        result = HybridResult(
            result_type="graph",
            score=0.9,
            content="Graph content",
            source_id="p1",
        )
        assert result.get_citation() == ""

    def test_get_citation_non_graph_non_vector(self):
        """Non-graph, non-vector result returns empty."""
        result = HybridResult(
            result_type="hybrid",
            score=0.9,
            content="Content",
            source_id="p1",
        )
        assert result.get_citation() == ""


# ============================================================================
# Test: GraphEvidence display text
# ============================================================================

class TestGraphEvidenceDisplayText:
    """Test GraphEvidence.get_display_text method."""

    def test_basic_display(self):
        """Basic display text with value and p-value."""
        ev = GraphEvidence(
            intervention="TLIF",
            outcome="VAS",
            value="2.1",
            source_paper_id="p1",
            p_value=0.001,
            direction="improved",
        )
        text = ev.get_display_text()
        assert "TLIF improved VAS" in text
        assert "to 2.1" in text
        assert "p=0.001" in text

    def test_display_with_control(self):
        """Display text with control value."""
        ev = GraphEvidence(
            intervention="UBE",
            outcome="ODI",
            value="25%",
            value_control="40%",
            source_paper_id="p1",
            direction="improved",
        )
        text = ev.get_display_text()
        assert "vs 40%" in text

    def test_display_no_p_value_but_significant(self):
        """Display text with no p-value but significant flag."""
        ev = GraphEvidence(
            intervention="PLIF",
            outcome="Fusion Rate",
            value="95%",
            source_paper_id="p1",
            is_significant=True,
            direction="improved",
        )
        text = ev.get_display_text()
        assert "(p<0.05)" in text

    def test_display_no_p_value_not_significant(self):
        """Display text with no p-value and not significant."""
        ev = GraphEvidence(
            intervention="PLIF",
            outcome="Fusion Rate",
            value="95%",
            source_paper_id="p1",
            direction="improved",
        )
        text = ev.get_display_text()
        # No p-value info
        assert "p=" not in text


# ============================================================================
# Test: PaperNode citation formats
# ============================================================================

class TestPaperNodeCitation:
    """Test PaperNode.get_citation method."""

    def test_single_author(self):
        """Single author citation."""
        paper = PaperNode(
            paper_id="p1",
            title="TLIF Study",
            authors=["Kim JH"],
            year=2023,
            journal="Spine",
        )
        citation = paper.get_citation()
        assert "Kim JH" in citation
        assert "2023" in citation

    def test_multiple_authors(self):
        """Multiple authors use et al."""
        paper = PaperNode(
            paper_id="p1",
            title="TLIF Study",
            authors=["Kim JH", "Park SM", "Lee DY"],
            year=2023,
            journal="Spine",
        )
        citation = paper.get_citation()
        assert "et al." in citation

    def test_no_authors(self):
        """No authors shows 'Unknown'."""
        paper = PaperNode(paper_id="p1", title="Study")
        citation = paper.get_citation()
        assert "Unknown" in citation


# ============================================================================
# Test: GraphSearchResult methods
# ============================================================================

class TestGraphSearchResultMethods:
    """Test GraphSearchResult methods."""

    def test_get_unique_papers(self):
        """Get unique paper IDs from evidences."""
        evidences = [
            GraphEvidence("TLIF", "VAS", "2.1", "p1"),
            GraphEvidence("TLIF", "ODI", "35", "p1"),
            GraphEvidence("UBE", "VAS", "1.8", "p2"),
        ]
        result = GraphSearchResult(evidences=evidences)
        unique = result.get_unique_papers()
        assert len(unique) == 2
        assert "p1" in unique
        assert "p2" in unique

    def test_filter_by_significance(self):
        """Filter evidences by statistical significance."""
        evidences = [
            GraphEvidence("TLIF", "VAS", "2.1", "p1", p_value=0.001, is_significant=True),
            GraphEvidence("TLIF", "ODI", "35", "p2", p_value=0.2, is_significant=False),
            GraphEvidence("UBE", "VAS", "1.8", "p3", p_value=0.03, is_significant=True),
        ]
        result = GraphSearchResult(evidences=evidences)
        filtered = result.filter_by_significance(min_p_value=0.05)
        assert len(filtered.evidences) == 2

    def test_group_by_outcome(self):
        """Group evidences by outcome name."""
        evidences = [
            GraphEvidence("TLIF", "VAS", "2.1", "p1"),
            GraphEvidence("UBE", "VAS", "1.8", "p2"),
            GraphEvidence("TLIF", "ODI", "35", "p3"),
        ]
        result = GraphSearchResult(evidences=evidences)
        groups = result.group_by_outcome()
        assert "VAS" in groups
        assert len(groups["VAS"]) == 2
        assert "ODI" in groups
        assert len(groups["ODI"]) == 1

    def test_get_summary(self):
        """Get result summary string."""
        evidences = [
            GraphEvidence("TLIF", "VAS", "2.1", "p1", is_significant=True),
            GraphEvidence("TLIF", "ODI", "35", "p1", is_significant=False),
        ]
        result = GraphSearchResult(evidences=evidences, paper_nodes=[])
        summary = result.get_summary()
        assert "2 evidences" in summary
        assert "1 papers" in summary
        assert "1 statistically significant" in summary

    def test_empty_result(self):
        """Empty result has sensible defaults."""
        result = GraphSearchResult()
        assert result.evidences == []
        assert result.paper_nodes == []
        assert result.query_type == "evidence_search"
        assert result.get_unique_papers() == []
        assert result.group_by_outcome() == {}


# ============================================================================
# Test: InterventionHierarchy
# ============================================================================

class TestInterventionHierarchy:
    """Test InterventionHierarchy dataclass."""

    def test_defaults(self):
        """Test default values."""
        ih = InterventionHierarchy(intervention="TLIF")
        assert ih.intervention == "TLIF"
        assert ih.level == 0
        assert ih.parent is None
        assert ih.children == []
        assert ih.category == ""
        assert ih.aliases == []

    def test_with_hierarchy(self):
        """Test hierarchy with parent and children."""
        ih = InterventionHierarchy(
            intervention="MIS-TLIF",
            level=1,
            parent="TLIF",
            children=["Robot-assisted MIS-TLIF"],
            category="fusion",
        )
        assert ih.parent == "TLIF"
        assert len(ih.children) == 1


# ============================================================================
# Test: Helper functions - boundary conditions
# ============================================================================

class TestHelperBoundaryConditions:
    """Test helper functions with boundary values."""

    # Evidence weight
    def test_evidence_weight_unknown_level(self):
        """Unknown evidence level gets default 0.1."""
        paper = PaperNode(paper_id="p1", title="T", evidence_level="unknown")
        weight = get_evidence_weight(paper)
        assert weight == 0.1

    def test_evidence_weight_level_5(self):
        """Level 5 gets 0.1."""
        paper = PaperNode(paper_id="p1", title="T", evidence_level="5")
        weight = get_evidence_weight(paper)
        assert weight == 0.1

    def test_evidence_weight_none_non_journal(self):
        """None evidence + non-journal gets 0.30."""
        paper = PaperNode(paper_id="p1", title="T")
        paper.evidence_level = None
        weight = get_evidence_weight(paper)
        assert weight == 0.30

    # Study design weight
    def test_study_design_weight_empty_list(self):
        """Empty list returns 0.5."""
        assert get_study_design_weight([]) == 0.5

    def test_study_design_weight_unknown_type(self):
        """Unknown type gets default 0.5."""
        assert get_study_design_weight(["Unknown Study Type"]) == 0.5

    def test_study_design_weight_meta_analysis(self):
        """Meta-Analysis gets 1.0."""
        assert get_study_design_weight(["Meta-Analysis"]) == 1.0

    # Sample size boost
    def test_sample_size_boost_zero(self):
        """Zero sample size gets no boost."""
        assert get_sample_size_boost(0) == 1.0

    def test_sample_size_boost_negative(self):
        """Negative sample size gets no boost."""
        assert get_sample_size_boost(-10) == 1.0

    def test_sample_size_boost_boundary_10(self):
        """Exactly 10 gets 1.05."""
        assert get_sample_size_boost(10) == 1.05

    def test_sample_size_boost_boundary_50(self):
        """Exactly 50 gets 1.1."""
        assert get_sample_size_boost(50) == 1.1

    def test_sample_size_boost_boundary_100(self):
        """Exactly 100 gets 1.15."""
        assert get_sample_size_boost(100) == 1.15

    def test_sample_size_boost_boundary_500(self):
        """Exactly 500 gets 1.25."""
        assert get_sample_size_boost(500) == 1.25

    def test_sample_size_boost_boundary_1000(self):
        """Exactly 1000 gets 1.3."""
        assert get_sample_size_boost(1000) == 1.3

    # Recency boost
    def test_recency_boost_current_year(self):
        """Current year gets 1.2."""
        assert get_recency_boost(2026, current_year=2026) == 1.2

    def test_recency_boost_3_years(self):
        """3 years old gets 1.1."""
        assert get_recency_boost(2023, current_year=2026) == 1.1

    def test_recency_boost_7_years(self):
        """7 years old gets 1.0."""
        assert get_recency_boost(2019, current_year=2026) == 1.0

    def test_recency_boost_15_years(self):
        """15 years old gets 0.9."""
        assert get_recency_boost(2011, current_year=2026) == 0.9

    def test_recency_boost_no_current_year(self):
        """No current_year uses datetime.now()."""
        boost = get_recency_boost(2025)
        assert isinstance(boost, float)
        assert 0.9 <= boost <= 1.2

    # Citation boost
    def test_citation_boost_zero(self):
        """Zero citations gets 1.0."""
        assert get_citation_boost(0) == 1.0

    def test_citation_boost_boundary_5(self):
        """Exactly 5 gets 1.05."""
        assert get_citation_boost(5) == 1.05

    def test_citation_boost_boundary_10(self):
        """Exactly 10 gets 1.1."""
        assert get_citation_boost(10) == 1.1

    def test_citation_boost_boundary_20(self):
        """Exactly 20 gets 1.15."""
        assert get_citation_boost(20) == 1.15

    def test_citation_boost_boundary_50(self):
        """Exactly 50 gets 1.2."""
        assert get_citation_boost(50) == 1.2

    def test_citation_boost_boundary_100(self):
        """Exactly 100 gets 1.3."""
        assert get_citation_boost(100) == 1.3

    # Source credibility
    def test_source_credibility_who(self):
        """WHO gets 1.0."""
        assert get_source_credibility("WHO") == 1.0

    def test_source_credibility_cdc(self):
        """CDC gets 1.0."""
        assert get_source_credibility("CDC") == 1.0

    def test_source_credibility_edu_domain(self):
        """Edu domain gets 0.85."""
        assert get_source_credibility("stanford.edu") == 0.85

    def test_source_credibility_mayo_clinic(self):
        """Mayo Clinic gets 0.85."""
        assert get_source_credibility("Mayo Clinic website") == 0.85

    def test_source_credibility_case_insensitive(self):
        """Source credibility check is case insensitive."""
        assert get_source_credibility("nih research") == 1.0

    def test_source_credibility_wikipedia(self):
        """Wikipedia gets 0.6."""
        assert get_source_credibility("wikipedia.org") == 0.6


# ============================================================================
# Test: get_stats
# ============================================================================

class TestGetStats:
    """Test HybridRanker.get_stats method."""

    def test_stats_no_client(self):
        """Stats without client."""
        ranker = HybridRanker(neo4j_client=None)
        stats = ranker.get_stats()
        assert stats["graph_db_available"] is False
        assert stats["neo4j_hybrid_enabled"] is False
        assert stats["search_backend"] == "neo4j_cypher"
        assert stats["ranking_version"] == "v1.0"

    def test_stats_with_client_no_hybrid(self):
        """Stats with client but no hybrid."""
        mock_client = MagicMock()
        ranker = HybridRanker(neo4j_client=mock_client, use_neo4j_hybrid=False)
        stats = ranker.get_stats()
        assert stats["graph_db_available"] is True
        assert stats["neo4j_hybrid_enabled"] is False
        assert stats["search_backend"] == "neo4j_cypher"

    def test_stats_with_hybrid(self):
        """Stats with hybrid enabled."""
        mock_client = MagicMock()
        ranker = HybridRanker(neo4j_client=mock_client, use_neo4j_hybrid=True)
        stats = ranker.get_stats()
        assert stats["graph_db_available"] is True
        assert stats["neo4j_hybrid_enabled"] is True
        assert stats["search_backend"] == "neo4j_hybrid"


# ============================================================================
# Test: Constants validation
# ============================================================================

class TestConstants:
    """Validate module constants."""

    def test_weights_sum_to_one(self):
        """Semantic + Authority weights should sum to 1.0."""
        assert abs(DEFAULT_SEMANTIC_WEIGHT + DEFAULT_AUTHORITY_WEIGHT - 1.0) < 1e-6

    def test_evidence_level_weights_ordered(self):
        """Evidence weights are in descending order from 1a to 5."""
        order = ["1a", "1b", "2a", "2b", "3", "4", "5"]
        weights = [EVIDENCE_LEVEL_WEIGHTS[k] for k in order]
        for i in range(len(weights) - 1):
            assert weights[i] >= weights[i + 1]

    def test_direction_boosts_ordering(self):
        """Improved > unchanged > worsened boost ordering."""
        assert DIRECTION_IMPROVED_BOOST > DIRECTION_UNCHANGED_BOOST
        assert DIRECTION_UNCHANGED_BOOST > DIRECTION_WORSENED_BOOST

    def test_key_finding_boost_positive(self):
        """Key finding boost is > 1.0."""
        assert KEY_FINDING_BOOST > 1.0

    def test_statistics_boost_positive(self):
        """Statistics boost is > 1.0."""
        assert STATISTICS_BOOST > 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
