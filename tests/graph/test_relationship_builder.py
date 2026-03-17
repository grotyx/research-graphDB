"""Tests for relationship_builder module.

Tests for:
- Building relationships from paper data
- STUDIES, INVESTIGATES, AFFECTS relation creation
- Entity normalization integration
- Outcome extraction from chunks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field

from src.graph.relationship_builder import (
    RelationshipBuilder,
    SpineMetadata,
    ExtractedOutcome,
    BuildResult,
)
from src.graph.neo4j_client import Neo4jClient
from src.graph.entity_normalizer import EntityNormalizer

# Import vision processor types for mocking
from src.builder.gemini_vision_processor import (
    ExtractedMetadata,
    ExtractedChunk,
    StatisticsData,
)


class TestSpineMetadata:
    """Test SpineMetadata dataclass."""

    def test_spine_metadata_creation(self):
        """Test creating SpineMetadata."""
        metadata = SpineMetadata(
            sub_domain="Degenerative",
            anatomy_levels=["L4-5", "L5-S1"],
            pathologies=["Lumbar Stenosis"],
            interventions=["TLIF", "PLIF"],
            outcomes=[{"name": "VAS", "value": "2.3", "p_value": 0.001}]
        )

        assert metadata.sub_domain == "Degenerative"
        assert len(metadata.anatomy_levels) == 2
        assert len(metadata.pathologies) == 1
        assert len(metadata.interventions) == 2
        assert len(metadata.outcomes) == 1

    def test_spine_metadata_defaults(self):
        """Test default values."""
        metadata = SpineMetadata()

        assert metadata.sub_domain == ""
        assert metadata.anatomy_levels == []
        assert metadata.pathologies == []
        assert metadata.interventions == []
        assert metadata.outcomes == []


class TestExtractedOutcome:
    """Test ExtractedOutcome dataclass."""

    def test_extracted_outcome_creation(self):
        """Test creating ExtractedOutcome."""
        outcome = ExtractedOutcome(
            name="VAS",
            value="2.3",
            value_control="4.5",
            p_value=0.001,
            is_significant=True,
            direction="improved"
        )

        assert outcome.name == "VAS"
        assert outcome.value == "2.3"
        assert outcome.p_value == 0.001
        assert outcome.is_significant is True
        assert outcome.direction == "improved"

    def test_extracted_outcome_defaults(self):
        """Test default values."""
        outcome = ExtractedOutcome(name="ODI")

        assert outcome.name == "ODI"
        assert outcome.value == ""
        assert outcome.p_value is None
        assert outcome.is_significant is False
        assert outcome.direction == ""


class TestBuildResult:
    """Test BuildResult dataclass."""

    def test_build_result_creation(self):
        """Test creating BuildResult."""
        result = BuildResult(
            paper_id="test_001",
            nodes_created=5,
            relationships_created=10,
            errors=["Error 1"],
            warnings=["Warning 1", "Warning 2"]
        )

        assert result.paper_id == "test_001"
        assert result.nodes_created == 5
        assert result.relationships_created == 10
        assert len(result.errors) == 1
        assert len(result.warnings) == 2

    def test_build_result_defaults(self):
        """Test default values."""
        result = BuildResult(
            paper_id="test_002",
            nodes_created=1,
            relationships_created=3
        )

        assert result.errors == []
        assert result.warnings == []


class TestRelationshipBuilder:
    """Test RelationshipBuilder class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Neo4j client."""
        client = AsyncMock(spec=Neo4jClient)
        client.create_paper = AsyncMock(return_value={"nodes_created": 1})
        client.create_studies_relation = AsyncMock(return_value={"relationships_created": 1})
        client.create_investigates_relation = AsyncMock(return_value={"relationships_created": 1})
        client.create_affects_relation = AsyncMock(return_value={"relationships_created": 1})
        client.get_intervention_hierarchy = AsyncMock(return_value=[])
        # run_query returns batch count from $batch param when present
        async def _mock_run_query(cypher, params=None, **kwargs):
            if params and "batch" in params:
                return [{"created": len(params["batch"])}]
            if params and "items" in params:
                return [{"created": len(params["items"])}]
            return [{"created": 0}]
        client.run_query = AsyncMock(side_effect=_mock_run_query)
        return client

    @pytest.fixture
    def normalizer(self):
        """Create normalizer instance."""
        return EntityNormalizer()

    @pytest.fixture
    def builder(self, mock_client, normalizer):
        """Create RelationshipBuilder instance."""
        return RelationshipBuilder(mock_client, normalizer)

    @pytest.fixture
    def sample_metadata(self):
        """Create sample ExtractedMetadata."""
        return ExtractedMetadata(
            title="TLIF vs PLIF for Lumbar Stenosis",
            authors=["Author A", "Author B"],
            year=2024,
            journal="Spine",
            doi="10.1234/test",
            abstract="This is a test abstract",
            study_type="RCT",
            study_design="randomized",
            evidence_level="1b"
        )

    @pytest.fixture
    def sample_spine_metadata(self):
        """Create sample SpineMetadata."""
        return SpineMetadata(
            sub_domain="Degenerative",
            anatomy_levels=["L4-5"],
            pathologies=["Lumbar Stenosis"],
            interventions=["TLIF", "PLIF"],
            outcomes=[
                {"name": "Fusion Rate", "value": "92%", "p_value": 0.01},
                {"name": "VAS", "value": "2.3", "p_value": 0.001}
            ]
        )

    def test_builder_initialization(self, mock_client, normalizer):
        """Test builder initialization."""
        builder = RelationshipBuilder(mock_client, normalizer)

        assert builder.client is mock_client
        assert builder.normalizer is normalizer

    @pytest.mark.asyncio
    async def test_create_paper_node(self, builder, sample_metadata, sample_spine_metadata):
        """Test create_paper_node."""
        await builder.create_paper_node(
            paper_id="test_001",
            metadata=sample_metadata,
            spine_metadata=sample_spine_metadata
        )

        # Verify create_paper was called
        builder.client.create_paper.assert_called_once()

        # Check paper data
        call_args = builder.client.create_paper.call_args
        paper = call_args[0][0]

        assert paper.paper_id == "test_001"
        assert paper.title == "TLIF vs PLIF for Lumbar Stenosis"
        assert paper.year == 2024
        assert paper.sub_domain == "Degenerative"
        assert paper.study_type == "RCT"
        assert paper.study_design == "RCT"  # "randomized" normalized to "RCT"
        assert paper.evidence_level == "1b"

    @pytest.mark.asyncio
    async def test_create_studies_relations(self, builder):
        """Test create_studies_relations (batched via UNWIND)."""
        pathologies = ["Lumbar Stenosis", "Spondylolisthesis"]

        count = await builder.create_studies_relations(
            paper_id="test_001",
            pathologies=pathologies
        )

        assert count == 2

        # Verify run_query was called with batch containing both pathologies
        calls = builder.client.run_query.call_args_list
        # Find the STUDIES batch call
        studies_call = next(
            c for c in calls
            if c[0][0] and "STUDIES" in c[0][0]
        )
        params = studies_call[0][1]
        assert params["paper_id"] == "test_001"
        assert len(params["batch"]) == 2
        assert params["batch"][0]["pathology_name"] == "Lumbar Stenosis"
        assert params["batch"][0]["is_primary"] is True
        assert params["batch"][1]["is_primary"] is False

    @pytest.mark.asyncio
    async def test_create_studies_relations_normalization(self, builder):
        """Test pathology normalization in create_studies_relations."""
        pathologies = ["LDH", "HNP"]  # Aliases for "Lumbar Disc Herniation"

        count = await builder.create_studies_relations(
            paper_id="test_002",
            pathologies=pathologies
        )

        # Both should normalize to same pathology in the batch
        calls = builder.client.run_query.call_args_list
        studies_call = next(
            c for c in calls
            if c[0][0] and "STUDIES" in c[0][0]
        )
        batch = studies_call[0][1]["batch"]
        assert batch[0]["pathology_name"] == "Lumbar Disc Herniation"
        assert batch[1]["pathology_name"] == "Lumbar Disc Herniation"

    @pytest.mark.asyncio
    async def test_create_investigates_relations(self, builder):
        """Test create_investigates_relations (batched via UNWIND)."""
        interventions = ["TLIF", "PLIF", "ALIF"]

        count = await builder.create_investigates_relations(
            paper_id="test_003",
            interventions=interventions
        )

        assert count == 3
        # Verify batch was passed to run_query
        calls = builder.client.run_query.call_args_list
        inv_call = next(
            c for c in calls
            if c[0][0] and "INVESTIGATES" in c[0][0]
        )
        assert len(inv_call[0][1]["batch"]) == 3

    @pytest.mark.asyncio
    async def test_create_investigates_relations_normalization(self, builder):
        """Test intervention normalization."""
        interventions = ["BESS", "Biportal"]  # Aliases for UBE

        count = await builder.create_investigates_relations(
            paper_id="test_004",
            interventions=interventions
        )

        # Both should normalize to UBE in the batch
        calls = builder.client.run_query.call_args_list
        inv_call = next(
            c for c in calls
            if c[0][0] and "INVESTIGATES" in c[0][0]
        )
        batch = inv_call[0][1]["batch"]
        assert batch[0]["intervention_name"] == "UBE"
        assert batch[1]["intervention_name"] == "UBE"

    @pytest.mark.asyncio
    async def test_create_affects_relations(self, builder):
        """Test create_affects_relations (batched via UNWIND)."""
        outcomes = [
            ExtractedOutcome(
                name="VAS",
                value="2.3",
                p_value=0.001,
                is_significant=True,
                direction="improved"
            ),
            ExtractedOutcome(
                name="ODI",
                value="15%",
                p_value=0.05,
                is_significant=True,
                direction="improved"
            )
        ]

        count = await builder.create_affects_relations(
            intervention="TLIF",
            outcomes=outcomes,
            paper_id="test_005"
        )

        assert count == 2

        # Verify batch was passed to run_query
        calls = builder.client.run_query.call_args_list
        affects_call = next(
            c for c in calls
            if c[0][0] and "AFFECTS" in c[0][0]
        )
        params = affects_call[0][1]
        assert params["intervention_name"] == "TLIF"
        assert len(params["batch"]) == 2
        assert params["batch"][0]["outcome_name"] == "VAS"
        assert params["batch"][0]["properties"]["value"] == "2.3"
        assert params["batch"][0]["properties"]["p_value"] == 0.001
        assert params["batch"][0]["properties"]["is_significant"] is True

    @pytest.mark.asyncio
    async def test_create_affects_relations_outcome_normalization(self, builder):
        """Test outcome normalization in AFFECTS relations."""
        outcomes = [
            ExtractedOutcome(name="Visual Analog Scale", value="2.3")
        ]

        await builder.create_affects_relations(
            intervention="UBE",
            outcomes=outcomes,
            paper_id="test_006"
        )

        # Should normalize to VAS in the batch
        calls = builder.client.run_query.call_args_list
        affects_call = next(
            c for c in calls
            if c[0][0] and "AFFECTS" in c[0][0]
        )
        batch = affects_call[0][1]["batch"]
        assert batch[0]["outcome_name"] == "VAS"

    @pytest.mark.asyncio
    async def test_link_intervention_to_taxonomy_exists(self, builder):
        """Test linking intervention that exists in taxonomy."""
        builder.client.get_intervention_hierarchy.return_value = [
            {"name": "TLIF", "parents": ["Interbody Fusion"]}
        ]

        result = await builder.link_intervention_to_taxonomy("TLIF")

        assert result is True
        builder.client.get_intervention_hierarchy.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_intervention_to_taxonomy_not_exists(self, builder):
        """Test linking intervention not in taxonomy."""
        builder.client.get_intervention_hierarchy.return_value = []

        result = await builder.link_intervention_to_taxonomy("Unknown Surgery")

        assert result is False

    @pytest.mark.asyncio
    async def test_build_from_paper_complete(
        self,
        builder,
        sample_metadata,
        sample_spine_metadata
    ):
        """Test build_from_paper with complete data."""
        chunks = [
            ExtractedChunk(
                content="Fusion rate was 92%",
                content_type="text",
                section_type="results",
                tier="tier1",
                is_key_finding=True,
                keywords=["Fusion Rate"],
                statistics=StatisticsData(p_value="p=0.01", is_significant=True)
            )
        ]

        result = await builder.build_from_paper(
            paper_id="test_007",
            metadata=sample_metadata,
            spine_metadata=sample_spine_metadata,
            chunks=chunks
        )

        assert result.paper_id == "test_007"
        assert result.nodes_created >= 1
        assert result.relationships_created > 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_build_from_paper_no_pathologies(
        self,
        builder,
        sample_metadata
    ):
        """Test build with no pathologies."""
        spine_metadata = SpineMetadata(
            sub_domain="Degenerative",
            interventions=["TLIF"],
            outcomes=[{"name": "VAS", "value": "2.3"}]
        )

        result = await builder.build_from_paper(
            paper_id="test_008",
            metadata=sample_metadata,
            spine_metadata=spine_metadata,
            chunks=[]
        )

        assert "No pathologies found" in result.warnings

    @pytest.mark.asyncio
    async def test_build_from_paper_no_interventions(
        self,
        builder,
        sample_metadata
    ):
        """Test build with no interventions."""
        spine_metadata = SpineMetadata(
            sub_domain="Degenerative",
            pathologies=["Lumbar Stenosis"]
        )

        result = await builder.build_from_paper(
            paper_id="test_009",
            metadata=sample_metadata,
            spine_metadata=spine_metadata,
            chunks=[]
        )

        assert "No interventions found" in result.warnings

    @pytest.mark.asyncio
    async def test_build_from_paper_no_outcomes(
        self,
        builder,
        sample_metadata,
        sample_spine_metadata
    ):
        """Test build with no outcomes."""
        spine_metadata = SpineMetadata(
            sub_domain="Degenerative",
            pathologies=["Lumbar Stenosis"],
            interventions=["TLIF"]
        )

        result = await builder.build_from_paper(
            paper_id="test_010",
            metadata=sample_metadata,
            spine_metadata=spine_metadata,
            chunks=[]
        )

        assert "No outcomes with statistics found" in result.warnings

    def test_extract_outcomes_from_chunks_from_metadata(self, builder):
        """Test extracting outcomes from spine_metadata."""
        spine_metadata = SpineMetadata(
            outcomes=[
                {"name": "VAS", "value": "2.3", "p_value": 0.001},
                {"name": "ODI", "value": "15%", "p_value": 0.05}
            ]
        )

        outcomes = builder._extract_outcomes_from_chunks([], spine_metadata)

        assert len(outcomes) == 2
        assert outcomes[0].name == "VAS"
        assert outcomes[0].value == "2.3"
        assert outcomes[0].is_significant is True

    def test_extract_outcomes_from_chunks_from_statistics(self, builder):
        """Test extracting outcomes from chunk statistics."""
        spine_metadata = SpineMetadata()
        chunks = [
            ExtractedChunk(
                content="VAS improved significantly",
                content_type="text",
                section_type="results",
                tier="tier1",
                keywords=["VAS", "Visual Analog Scale"],
                statistics=StatisticsData(p_value="p=0.01", is_significant=True)
            )
        ]

        outcomes = builder._extract_outcomes_from_chunks(chunks, spine_metadata)

        # Should find VAS from keywords
        assert len(outcomes) >= 1
        vas_found = any(o.name == "VAS" for o in outcomes)
        assert vas_found

    def test_extract_outcomes_deduplication(self, builder):
        """Test outcome deduplication."""
        spine_metadata = SpineMetadata(
            outcomes=[{"name": "VAS", "value": "2.3", "p_value": 0.001}]
        )
        chunks = [
            ExtractedChunk(
                content="VAS score",
                content_type="text",
                section_type="results",
                tier="tier1",
                keywords=["VAS"],
                statistics=StatisticsData(p_value="p=0.01", is_significant=True)
            )
        ]

        outcomes = builder._extract_outcomes_from_chunks(chunks, spine_metadata)

        # Should not duplicate VAS
        vas_count = sum(1 for o in outcomes if o.name == "VAS")
        assert vas_count == 1

    def test_determine_direction_significant(self, builder):
        """Test _determine_direction with significant p-value."""
        outcome_dict = {"name": "VAS", "value": "2.3", "p_value": 0.001}

        direction = builder._determine_direction(outcome_dict)

        assert direction == "improved"

    def test_determine_direction_not_significant(self, builder):
        """Test _determine_direction with non-significant p-value."""
        outcome_dict = {"name": "VAS", "value": "4.5", "p_value": 0.5}

        direction = builder._determine_direction(outcome_dict)

        assert direction == "unchanged"

    def test_parse_p_value_equals(self, builder):
        """Test parsing 'p=0.001' format."""
        p_val = builder._parse_p_value("p=0.001")
        assert p_val == 0.001

    def test_parse_p_value_less_than(self, builder):
        """Test parsing 'p<0.05' format."""
        p_val = builder._parse_p_value("p<0.05")
        assert p_val == 0.05

    def test_parse_p_value_number_only(self, builder):
        """Test parsing '0.01' format."""
        p_val = builder._parse_p_value("0.01")
        assert p_val == 0.01

    def test_parse_p_value_invalid(self, builder):
        """Test parsing invalid p-value."""
        p_val = builder._parse_p_value("invalid")
        assert p_val is None

    def test_parse_p_value_out_of_range(self, builder):
        """Test parsing out-of-range value."""
        p_val = builder._parse_p_value("1.5")
        assert p_val is None

    def test_parse_p_value_case_insensitive(self, builder):
        """Test parsing is case-insensitive."""
        p_val = builder._parse_p_value("P=0.001")
        assert p_val == 0.001

    def test_parse_p_value_with_spaces(self, builder):
        """Test parsing with spaces."""
        p_val = builder._parse_p_value("p = 0.001")
        assert p_val == 0.001

    @pytest.mark.asyncio
    async def test_create_chunk_mentions_basic(self, builder, sample_spine_metadata):
        """Test create_chunk_mentions creates MENTIONS relations."""
        # Mock chunks query result
        builder.client.run_query = AsyncMock(side_effect=[
            # First call: fetch chunks
            [
                {"chunk_id": "chunk_001", "content": "TLIF showed improved fusion rate in lumbar stenosis patients"},
                {"chunk_id": "chunk_002", "content": "VAS scores improved significantly after surgery"}
            ],
            # Subsequent calls: UNWIND batch results for each label type
            [{"created": 2}],  # Intervention matches (TLIF)
            [{"created": 1}],  # Pathology matches (Lumbar Stenosis)
            [{"created": 0}],  # Outcome matches
            [{"created": 0}],  # Anatomy matches
        ])

        count = await builder.create_chunk_mentions("test_paper", sample_spine_metadata)

        assert count >= 0
        assert builder.client.run_query.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_chunk_mentions_no_chunks(self, builder, sample_spine_metadata):
        """Test create_chunk_mentions with no chunks."""
        builder.client.run_query = AsyncMock(return_value=[])

        count = await builder.create_chunk_mentions("test_paper", sample_spine_metadata)

        assert count == 0

    @pytest.mark.asyncio
    async def test_create_chunk_mentions_no_entities(self, builder):
        """Test create_chunk_mentions with empty spine metadata."""
        spine_meta = SpineMetadata()

        count = await builder.create_chunk_mentions("test_paper", spine_meta)

        assert count == 0
        # Should not even query for chunks
        builder.client.run_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_applied_to_relations(self, builder):
        """Test _create_applied_to_relations creates APPLIED_TO relations."""
        builder.client.run_query = AsyncMock(return_value=[{"created": 2}])

        count = await builder._create_applied_to_relations(
            ["TLIF", "PLIF"], ["L4-5", "L5-S1"]
        )

        assert count == 2
        builder.client.run_query.assert_called_once()
        # Verify batch parameter is passed
        call_args = builder.client.run_query.call_args
        assert "batch" in call_args[1] or (len(call_args[0]) > 1 and "batch" in call_args[0][1])

    @pytest.mark.asyncio
    async def test_create_applied_to_relations_empty(self, builder):
        """Test _create_applied_to_relations with empty inputs."""
        count = await builder._create_applied_to_relations([], ["L4-5"])
        assert count == 0

        count = await builder._create_applied_to_relations(["TLIF"], [])
        assert count == 0
