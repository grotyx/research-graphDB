"""Tests for SNOMED Enricher module.

Covers:
- generate_snomed_update_queries(): dynamic Cypher generation
- update_snomed_for_entity_type(): SNOMED code application with normalizer
- backfill_treats_relations(): TREATS relationship backfill (dry-run and live)
- parse_segment_range(): multi-segment spine level parsing
- split_compound_anatomy(): compound anatomy string splitting
- cleanup_anatomy_nodes(): anatomy node cleanup pipeline
- generate_coverage_report(): SNOMED coverage statistics
- Error handling: invalid entity types, invalid labels, empty data
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional

from graph.snomed_enricher import (
    generate_snomed_update_queries,
    update_snomed_for_entity_type,
    backfill_treats_relations,
    parse_segment_range,
    split_compound_anatomy,
    cleanup_anatomy_nodes,
    generate_coverage_report,
    UpdateResult,
    TreatsBackfillResult,
    AnatomyCleanupResult,
    ENTITY_TYPE_CONFIG,
    SPINE_LEVELS,
    NON_SPECIFIC_ANATOMY,
    DIRECTION_ONLY_ANATOMY,
)
from core.exceptions import ValidationError


# =====================================================================
# Mock normalizer result
# =====================================================================

@dataclass
class MockNormResult:
    """Mock normalizer result."""
    canonical: str = "Lumbar Fusion"
    snomed_code: Optional[str] = "387713003"
    snomed_term: Optional[str] = "Lumbar fusion"
    confidence: float = 0.95
    method: str = "exact_match"


@dataclass
class MockNormResultNoMatch:
    canonical: str = ""
    snomed_code: Optional[str] = None
    snomed_term: Optional[str] = None
    confidence: float = 0.0
    method: str = "none"


@dataclass
class MockNormResultLowConfidence:
    canonical: str = "Some Term"
    snomed_code: Optional[str] = "999999"
    snomed_term: Optional[str] = "Some SNOMED term"
    confidence: float = 0.5  # below default threshold of 0.8
    method: str = "fuzzy"


# =====================================================================
# parse_segment_range() tests
# =====================================================================

class TestParseSegmentRange:
    """Tests for parse_segment_range()."""

    def test_simple_same_region(self):
        result = parse_segment_range("L4-5")
        assert result == ["L4-5"]

    def test_multi_segment_same_region(self):
        result = parse_segment_range("L2-4")
        assert result == ["L2-3", "L3-4"]

    def test_explicit_region_prefix(self):
        result = parse_segment_range("C3-C6")
        assert result == ["C3-4", "C4-5", "C5-6"]

    def test_cross_region(self):
        result = parse_segment_range("T12-L2")
        assert result == ["T12-L1", "L1-2"]

    def test_single_segment(self):
        """L4-5 is a single segment pair."""
        result = parse_segment_range("L4-5")
        assert len(result) == 1

    def test_invalid_range_returns_empty(self):
        result = parse_segment_range("invalid")
        assert result == []

    def test_empty_string(self):
        result = parse_segment_range("")
        assert result == []

    def test_reversed_range_returns_empty(self):
        """L5-2 is backwards, should return empty."""
        result = parse_segment_range("L5-2")
        assert result == []

    def test_same_level_returns_empty(self):
        """L4-4 is same level, start_idx == end_idx."""
        result = parse_segment_range("L4-4")
        assert result == []

    def test_cervical_range(self):
        result = parse_segment_range("C1-3")
        assert result == ["C1-2", "C2-3"]

    def test_thoracic_range(self):
        result = parse_segment_range("T10-12")
        assert result == ["T10-11", "T11-12"]

    def test_sacral_range(self):
        result = parse_segment_range("S1-2")
        assert result == ["S1-2"]

    def test_with_dash_variant(self):
        """En-dash should also be handled."""
        result = parse_segment_range("L2\u20134")
        assert result == ["L2-3", "L3-4"]

    def test_case_insensitive(self):
        result = parse_segment_range("l2-4")
        assert result == ["L2-3", "L3-4"]

    def test_invalid_level_not_in_spine(self):
        """C8 doesn't exist in standard spine."""
        result = parse_segment_range("C8-9")
        assert result == []


# =====================================================================
# split_compound_anatomy() tests
# =====================================================================

class TestSplitCompoundAnatomy:
    """Tests for split_compound_anatomy()."""

    def test_comma_separated(self):
        result = split_compound_anatomy("L4-5, L5-S1")
        assert result == ["L4-5", "L5-S1"]

    def test_semicolon_separated(self):
        result = split_compound_anatomy("L4-5; L5-S1")
        assert result == ["L4-5", "L5-S1"]

    def test_and_separated(self):
        result = split_compound_anatomy("L4-5 and L5-S1")
        assert result == ["L4-5", "L5-S1"]

    def test_single_item(self):
        result = split_compound_anatomy("L4-5")
        assert result == ["L4-5"]

    def test_multiple_commas(self):
        result = split_compound_anatomy("L3-4, L4-5, L5-S1")
        assert result == ["L3-4", "L4-5", "L5-S1"]

    def test_empty_string(self):
        result = split_compound_anatomy("")
        assert result == []

    def test_whitespace_handling(self):
        result = split_compound_anatomy("  L4-5 ,  L5-S1  ")
        assert result == ["L4-5", "L5-S1"]


# =====================================================================
# generate_snomed_update_queries() tests
# =====================================================================

class TestGenerateSnomedUpdateQueries:
    """Tests for generate_snomed_update_queries()."""

    def test_generates_queries(self):
        queries = generate_snomed_update_queries(batch_size=100)
        assert len(queries) > 0
        for query, params in queries:
            assert "UNWIND $items" in query
            assert "items" in params
            assert len(params["items"]) > 0

    def test_batch_size_creates_multiple_batches(self):
        # Use a very small batch size to ensure multiple batches
        queries = generate_snomed_update_queries(batch_size=5)
        assert len(queries) > 4  # With 4 entity types and many mappings

    def test_each_batch_has_valid_data(self):
        queries = generate_snomed_update_queries(batch_size=50)
        for query, params in queries:
            for item in params["items"]:
                assert "name" in item
                assert "snomed_code" in item
                assert "snomed_term" in item
                assert "snomed_is_extension" in item

    def test_query_contains_correct_labels(self):
        queries = generate_snomed_update_queries(batch_size=1000)
        labels_found = set()
        for query, params in queries:
            for label in ["Intervention", "Pathology", "Outcome", "Anatomy"]:
                if f"(n:{label}" in query:
                    labels_found.add(label)
        assert labels_found == {"Intervention", "Pathology", "Outcome", "Anatomy"}


# =====================================================================
# update_snomed_for_entity_type() tests
# =====================================================================

class TestUpdateSnomedForEntityType:
    """Tests for update_snomed_for_entity_type()."""

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self):
        client = MagicMock()
        normalizer = MagicMock()
        with pytest.raises(ValidationError):
            await update_snomed_for_entity_type(client, "invalid_type", normalizer)

    @pytest.mark.asyncio
    async def test_all_already_mapped(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"cnt": 10}],   # total
            [{"cnt": 10}],   # already mapped
            [],              # missing nodes (empty)
        ])
        normalizer = MagicMock()

        result = await update_snomed_for_entity_type(client, "intervention", normalizer)
        assert result.entity_type == "intervention"
        assert result.total_nodes == 10
        assert result.already_mapped == 10
        assert result.newly_mapped == 0

    @pytest.mark.asyncio
    async def test_update_with_matches(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"cnt": 5}],    # total
            [{"cnt": 2}],    # already mapped
            [{"name": "TLIF"}, {"name": "PLIF"}, {"name": "Unknown Procedure"}],
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_intervention = MagicMock(side_effect=[
            MockNormResult(canonical="TLIF", snomed_code="123456", snomed_term="TLIF"),
            MockNormResult(canonical="PLIF", snomed_code="789012", snomed_term="PLIF"),
            MockNormResultNoMatch(),
        ])

        result = await update_snomed_for_entity_type(client, "intervention", normalizer)
        assert result.newly_mapped == 2
        assert result.no_mapping_found == 1
        assert "Unknown Procedure" in result.unmapped_names
        client.run_write_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_dry_run_no_write(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"cnt": 5}],
            [{"cnt": 2}],
            [{"name": "TLIF"}],
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_intervention = MagicMock(return_value=MockNormResult())

        result = await update_snomed_for_entity_type(
            client, "intervention", normalizer, dry_run=True
        )
        assert result.newly_mapped == 1
        client.run_write_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_skipped(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"cnt": 3}],
            [{"cnt": 0}],
            [{"name": "FuzzyTerm"}, {"name": "GoodTerm"}],
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_intervention = MagicMock(side_effect=[
            MockNormResultLowConfidence(),
            MockNormResult(),
        ])

        result = await update_snomed_for_entity_type(
            client, "intervention", normalizer, min_confidence=0.8
        )
        assert result.low_confidence_skipped == 1
        assert result.newly_mapped == 1
        assert len(result.low_confidence_names) == 1

    @pytest.mark.asyncio
    async def test_pathology_entity_type(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"cnt": 2}],
            [{"cnt": 1}],
            [{"name": "Stenosis"}],
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_pathology = MagicMock(return_value=MockNormResult(
            snomed_code="P001", snomed_term="Lumbar Stenosis"
        ))

        result = await update_snomed_for_entity_type(client, "pathology", normalizer)
        assert result.entity_type == "pathology"
        assert result.newly_mapped == 1


# =====================================================================
# backfill_treats_relations() tests
# =====================================================================

class TestBackfillTreatsRelations:
    """Tests for backfill_treats_relations()."""

    @pytest.mark.asyncio
    async def test_dry_run(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            # review_ids
            [{"review_ids": ["review_1"]}],
            # count query (pairs)
            [
                {"intervention": "TLIF", "pathology": "Stenosis", "evidence": 5},
                {"intervention": "PLIF", "pathology": "DDD", "evidence": 3},
            ],
            # existing TREATS count
            [{"cnt": 1}],
        ])

        result = await backfill_treats_relations(client, dry_run=True)
        assert result.total_pairs == 2
        assert result.excluded_review_papers == 1
        assert result.already_existed == 1
        assert result.newly_created == 1  # 2 total - 1 existing
        assert len(result.top_pairs) == 2

    @pytest.mark.asyncio
    async def test_live_run(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            # review_ids
            [{"review_ids": []}],
            # merge results
            [
                {"intervention": "TLIF", "pathology": "Stenosis", "evidence": 5},
                {"intervention": "PLIF", "pathology": "DDD", "evidence": 3},
            ],
        ])

        result = await backfill_treats_relations(client, dry_run=False)
        assert result.total_pairs == 2
        assert result.newly_created == 2
        assert len(result.top_pairs) == 2

    @pytest.mark.asyncio
    async def test_no_review_papers(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [{"review_ids": []}],
            [{"intervention": "TLIF", "pathology": "Stenosis", "evidence": 3}],
        ])

        result = await backfill_treats_relations(client, dry_run=False)
        assert result.excluded_review_papers == 0

    @pytest.mark.asyncio
    async def test_empty_review_result(self):
        client = MagicMock()
        client.run_query = AsyncMock(side_effect=[
            [],  # empty review query result
            [],  # empty merge result
        ])

        result = await backfill_treats_relations(client, dry_run=False)
        assert result.excluded_review_papers == 0
        assert result.total_pairs == 0


# =====================================================================
# cleanup_anatomy_nodes() tests
# =====================================================================

class TestCleanupAnatomyNodes:
    """Tests for cleanup_anatomy_nodes()."""

    @pytest.mark.asyncio
    async def test_non_specific_flagged(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "Multi-level", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.flagged_non_specific == 1
        client.run_write_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_direction_only_flagged(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "anterior", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.flagged_direction_only == 1

    @pytest.mark.asyncio
    async def test_compound_split(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "L4-5, L5-S1", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.split_compound == 1
        assert "L4-5" in result.segments_created
        assert "L5-S1" in result.segments_created

    @pytest.mark.asyncio
    async def test_range_split(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "L2-4", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.split_range == 1
        assert "L2-3" in result.segments_created
        assert "L3-4" in result.segments_created

    @pytest.mark.asyncio
    async def test_normal_node_with_snomed(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "L4-5", "snomed_code": "263572003", "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.already_clean == 1

    @pytest.mark.asyncio
    async def test_normal_node_gets_snomed_from_normalizer(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "L4-5", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_anatomy = MagicMock(return_value=MockNormResult(
            snomed_code="263572003", snomed_term="L4-5 level"
        ))

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.normalized == 1
        client.run_write_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_node_no_snomed_match(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "L4-5", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()
        normalizer.normalize_anatomy = MagicMock(return_value=MockNormResultNoMatch())

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.already_clean == 1

    @pytest.mark.asyncio
    async def test_dry_run_no_writes(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "Multi-level", "snomed_code": None, "quality_flag": None},
            {"name": "L2-4", "snomed_code": None, "quality_flag": None},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer, dry_run=True)
        assert result.flagged_non_specific == 1
        assert result.split_range == 1
        client.run_write_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_flagged_non_specific_skipped(self):
        """Node already flagged as non_specific should not be reflagged."""
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[
            {"name": "Multi-level", "snomed_code": None, "quality_flag": "non_specific"},
        ])
        client.run_write_query = AsyncMock()

        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.flagged_non_specific == 0
        client.run_write_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_anatomy_nodes(self):
        client = MagicMock()
        client.run_query = AsyncMock(return_value=[])
        normalizer = MagicMock()

        result = await cleanup_anatomy_nodes(client, normalizer)
        assert result.total_anatomy == 0


# =====================================================================
# generate_coverage_report() tests
# =====================================================================

class TestGenerateCoverageReport:
    """Tests for generate_coverage_report()."""

    @pytest.mark.asyncio
    async def test_coverage_report(self):
        client = MagicMock()

        # Build mock responses: for each entity type (4x), then TREATS, then flags
        entity_responses = []
        for _ in range(4):
            entity_responses.append([{"total": 100, "mapped": 80}])
        entity_responses.append([{"cnt": 50}])  # TREATS
        entity_responses.append([{"flag": "non_specific", "cnt": 5}])  # flags

        client.run_query = AsyncMock(side_effect=entity_responses)

        report = await generate_coverage_report(client)

        assert "intervention" in report
        assert "pathology" in report
        assert "outcome" in report
        assert "anatomy" in report
        assert report["intervention"]["total"] == 100
        assert report["intervention"]["mapped"] == 80
        assert report["intervention"]["coverage_pct"] == 80.0
        assert report["treats_count"] == 50
        assert report["anatomy_flags"]["non_specific"] == 5

    @pytest.mark.asyncio
    async def test_coverage_report_empty_db(self):
        client = MagicMock()

        entity_responses = []
        for _ in range(4):
            entity_responses.append([{"total": 0, "mapped": 0}])
        entity_responses.append([{"cnt": 0}])  # TREATS
        entity_responses.append([])  # flags

        client.run_query = AsyncMock(side_effect=entity_responses)

        report = await generate_coverage_report(client)
        assert report["intervention"]["coverage_pct"] == 0.0
        assert report["treats_count"] == 0
        assert report["anatomy_flags"] == {}


# =====================================================================
# Data class tests
# =====================================================================

class TestDataClasses:
    """Tests for result data classes."""

    def test_update_result_defaults(self):
        r = UpdateResult(entity_type="intervention")
        assert r.total_nodes == 0
        assert r.unmapped_names == []
        assert r.low_confidence_names == []

    def test_treats_backfill_result_defaults(self):
        r = TreatsBackfillResult()
        assert r.total_pairs == 0
        assert r.top_pairs == []

    def test_anatomy_cleanup_result_defaults(self):
        r = AnatomyCleanupResult()
        assert r.total_anatomy == 0
        assert r.segments_created == []


# =====================================================================
# SPINE_LEVELS and constant tests
# =====================================================================

class TestConstants:
    """Tests for module-level constants."""

    def test_spine_levels_order(self):
        assert SPINE_LEVELS[0] == "C1"
        assert SPINE_LEVELS[-1] == "S2"
        assert "L5" in SPINE_LEVELS
        assert "T12" in SPINE_LEVELS

    def test_spine_levels_count(self):
        # C1-C7 (7) + T1-T12 (12) + L1-L5 (5) + S1-S2 (2) = 26
        assert len(SPINE_LEVELS) == 26

    def test_non_specific_anatomy_values(self):
        assert "Multi-level" in NON_SPECIFIC_ANATOMY
        assert "Not specified" in NON_SPECIFIC_ANATOMY

    def test_direction_only_anatomy_values(self):
        assert "anterior" in DIRECTION_ONLY_ANATOMY
        assert "Posterior" in DIRECTION_ONLY_ANATOMY

    def test_entity_type_config_has_all_types(self):
        assert "intervention" in ENTITY_TYPE_CONFIG
        assert "pathology" in ENTITY_TYPE_CONFIG
        assert "outcome" in ENTITY_TYPE_CONFIG
        assert "anatomy" in ENTITY_TYPE_CONFIG
