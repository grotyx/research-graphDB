"""Tests for RelationshipDAO module.

Tests relationship CRUD operations extracted from Neo4jClient:
- Entity relations: STUDIES, INVESTIGATES, AFFECTS, TREATS, INVOLVES
- Paper-to-paper relations: SUPPORTS, CONTRADICTS, CITES, SIMILAR_TOPIC, EXTENDS, REPLICATES
- Convenience wrappers for specific relation types
- Getter methods for querying relations
- Validation: invalid relation types, confidence range
- Error handling: Neo4j failures
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from graph.relationship_dao import RelationshipDAO, _VALID_PAPER_RELATION_TYPES
from core.exceptions import ValidationError, ErrorCode


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_run_query():
    """Mock run_query callable."""
    return AsyncMock(return_value=[])


@pytest.fixture
def mock_run_write_query():
    """Mock run_write_query callable."""
    return AsyncMock(return_value={"relationships_created": 1, "properties_set": 0})


@pytest.fixture
def dao(mock_run_query, mock_run_write_query):
    """RelationshipDAO with mocked query functions."""
    return RelationshipDAO(
        run_query=mock_run_query,
        run_write_query=mock_run_write_query,
    )


# ===========================================================================
# Test: Entity Relations - STUDIES
# ===========================================================================

class TestStudiesRelation:
    """Test create_studies_relation method."""

    @pytest.mark.asyncio
    async def test_create_studies_basic(self, dao, mock_run_write_query):
        """Create basic STUDIES relation."""
        result = await dao.create_studies_relation(
            paper_id="paper_001",
            pathology_name="Lumbar Stenosis",
        )

        mock_run_write_query.assert_called_once()
        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["paper_id"] == "paper_001"
        assert params["pathology_name"] == "Lumbar Stenosis"
        assert params["is_primary"] is True

    @pytest.mark.asyncio
    async def test_create_studies_with_snomed(self, dao, mock_run_write_query):
        """Create STUDIES relation with SNOMED codes."""
        await dao.create_studies_relation(
            paper_id="paper_001",
            pathology_name="Stenosis",
            is_primary=False,
            snomed_code="76107001",
            snomed_term="Spinal stenosis"
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["snomed_code"] == "76107001"
        assert params["snomed_term"] == "Spinal stenosis"
        assert params["is_primary"] is False


# ===========================================================================
# Test: Entity Relations - INVESTIGATES
# ===========================================================================

class TestInvestigatesRelation:
    """Test create_investigates_relation method."""

    @pytest.mark.asyncio
    async def test_create_investigates_basic(self, dao, mock_run_write_query):
        """Create basic INVESTIGATES relation."""
        await dao.create_investigates_relation(
            paper_id="paper_001",
            intervention_name="TLIF",
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["paper_id"] == "paper_001"
        assert params["intervention_name"] == "TLIF"
        assert params["is_comparison"] is False

    @pytest.mark.asyncio
    async def test_create_investigates_comparison(self, dao, mock_run_write_query):
        """Create INVESTIGATES relation for comparison group."""
        await dao.create_investigates_relation(
            paper_id="paper_001",
            intervention_name="Conservative Treatment",
            is_comparison=True,
            category="Non-surgical"
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["is_comparison"] is True
        assert params["category"] == "Non-surgical"

    @pytest.mark.asyncio
    async def test_create_investigates_with_snomed(self, dao, mock_run_write_query):
        """Create INVESTIGATES relation with SNOMED codes."""
        await dao.create_investigates_relation(
            paper_id="paper_001",
            intervention_name="TLIF",
            snomed_code="609588009",
            snomed_term="Transforaminal lumbar interbody fusion"
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["snomed_code"] == "609588009"


# ===========================================================================
# Test: Entity Relations - AFFECTS
# ===========================================================================

class TestAffectsRelation:
    """Test create_affects_relation method."""

    @pytest.mark.asyncio
    async def test_create_affects_basic(self, dao, mock_run_write_query):
        """Create basic AFFECTS relation."""
        await dao.create_affects_relation(
            intervention_name="TLIF",
            outcome_name="VAS Score",
            source_paper_id="paper_001",
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["intervention_name"] == "TLIF"
        assert params["outcome_name"] == "VAS Score"
        assert params["properties"]["source_paper_id"] == "paper_001"

    @pytest.mark.asyncio
    async def test_create_affects_with_statistics(self, dao, mock_run_write_query):
        """Create AFFECTS relation with statistical details."""
        await dao.create_affects_relation(
            intervention_name="TLIF",
            outcome_name="VAS Score",
            source_paper_id="paper_001",
            value="3.2",
            value_control="5.1",
            p_value=0.001,
            effect_size="1.2",
            confidence_interval="0.8-1.6",
            is_significant=True,
            direction="improvement",
        )

        call_args = mock_run_write_query.call_args
        props = call_args[0][1]["properties"]
        assert props["value"] == "3.2"
        assert props["value_control"] == "5.1"
        assert props["p_value"] == 0.001
        assert props["is_significant"] is True
        assert props["direction"] == "improvement"

    @pytest.mark.asyncio
    async def test_create_affects_with_all_params(self, dao, mock_run_write_query):
        """Create AFFECTS relation with all parameters."""
        await dao.create_affects_relation(
            intervention_name="TLIF",
            outcome_name="ODI",
            source_paper_id="paper_001",
            baseline=45.0,
            final=22.0,
            value_intervention="22.5",
            value_difference="-23.0",
            category="Functional",
            timepoint="12 months",
            snomed_code="443721000",
            snomed_term="ODI score"
        )

        call_args = mock_run_write_query.call_args
        props = call_args[0][1]["properties"]
        assert props["baseline"] == 45.0
        assert props["final"] == 22.0
        assert props["timepoint"] == "12 months"
        assert call_args[0][1]["snomed_code"] == "443721000"


# ===========================================================================
# Test: Entity Relations - TREATS
# ===========================================================================

class TestTreatsRelation:
    """Test create_treats_relation method."""

    @pytest.mark.asyncio
    async def test_create_treats_basic(self, dao, mock_run_write_query):
        """Create basic TREATS relation."""
        await dao.create_treats_relation(
            intervention_name="TLIF",
            pathology_name="Spondylolisthesis",
            source_paper_id="paper_001",
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["intervention_name"] == "TLIF"
        assert params["pathology_name"] == "Spondylolisthesis"

    @pytest.mark.asyncio
    async def test_create_treats_with_indication(self, dao, mock_run_write_query):
        """Create TREATS relation with indication details."""
        await dao.create_treats_relation(
            intervention_name="TLIF",
            pathology_name="Stenosis",
            source_paper_id="paper_001",
            indication="Grade I-II spondylolisthesis with stenosis",
            contraindication="Severe osteoporosis",
            indication_level="strong",
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["indication_level"] == "strong"
        assert "osteoporosis" in params["contraindication"].lower()

    @pytest.mark.asyncio
    async def test_create_treats_truncates_long_indication(self, dao, mock_run_write_query):
        """Long indication text should be truncated to 500 chars."""
        long_text = "x" * 1000
        await dao.create_treats_relation(
            intervention_name="TLIF",
            pathology_name="Stenosis",
            indication=long_text,
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert len(params["indication"]) == 500


# ===========================================================================
# Test: Entity Relations - INVOLVES
# ===========================================================================

class TestInvolvesRelation:
    """Test create_involves_relation method."""

    @pytest.mark.asyncio
    async def test_create_involves_basic(self, dao, mock_run_write_query):
        """Create basic INVOLVES relation."""
        await dao.create_involves_relation(
            paper_id="paper_001",
            anatomy_name="Lumbar Spine",
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["paper_id"] == "paper_001"
        assert params["anatomy_name"] == "Lumbar Spine"

    @pytest.mark.asyncio
    async def test_create_involves_with_level(self, dao, mock_run_write_query):
        """Create INVOLVES relation with level and region."""
        await dao.create_involves_relation(
            paper_id="paper_001",
            anatomy_name="Lumbar Spine",
            level="L4-L5",
            region="Posterior",
            snomed_code="122496003",
            snomed_term="Lumbar region of spine"
        )

        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["level"] == "L4-L5"
        assert params["region"] == "Posterior"
        assert params["snomed_code"] == "122496003"


# ===========================================================================
# Test: Paper-to-Paper Relations
# ===========================================================================

class TestPaperRelations:
    """Test create_paper_relation and related methods."""

    @pytest.mark.asyncio
    async def test_create_paper_relation_supports(self, dao, mock_run_write_query):
        """Create SUPPORTS paper relation."""
        result = await dao.create_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
            confidence=0.85,
            evidence="Both studies show fusion superiority",
        )

        assert result is True
        mock_run_write_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_paper_relation_contradicts(self, dao, mock_run_write_query):
        """Create CONTRADICTS paper relation."""
        result = await dao.create_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="CONTRADICTS",
            confidence=0.7,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_relation_type(self, dao):
        """Invalid relation_type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            await dao.create_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="INVALID_TYPE",
            )

        assert exc_info.value.error_code == ErrorCode.VAL_INVALID_VALUE

    @pytest.mark.asyncio
    async def test_invalid_confidence_above_1(self, dao):
        """Confidence > 1.0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            await dao.create_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
                confidence=1.5,
            )

    @pytest.mark.asyncio
    async def test_invalid_confidence_below_0(self, dao):
        """Confidence < 0.0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            await dao.create_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
                confidence=-0.1,
            )

    @pytest.mark.asyncio
    async def test_paper_relation_neo4j_error(self, dao, mock_run_write_query):
        """Neo4j error should propagate."""
        mock_run_write_query.side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            await dao.create_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
            )

    @pytest.mark.asyncio
    async def test_paper_relation_no_matches(self, dao, mock_run_write_query):
        """When no papers match, relationships_created=0 and properties_set=0."""
        mock_run_write_query.return_value = {"relationships_created": 0, "properties_set": 0}

        result = await dao.create_paper_relation(
            source_paper_id="nonexistent_1",
            target_paper_id="nonexistent_2",
            relation_type="SUPPORTS",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_paper_relation_merge_existing(self, dao, mock_run_write_query):
        """MERGE on existing relation should set properties."""
        mock_run_write_query.return_value = {"relationships_created": 0, "properties_set": 3}

        result = await dao.create_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
            confidence=0.9,
        )

        assert result is True  # properties_set > 0


# ===========================================================================
# Test: Convenience Wrappers
# ===========================================================================

class TestConvenienceWrappers:
    """Test convenience wrapper methods."""

    @pytest.mark.asyncio
    async def test_create_supports_relation(self, dao, mock_run_write_query):
        """create_supports_relation wrapper."""
        result = await dao.create_supports_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            evidence="Supporting evidence text",
            confidence=0.8,
        )

        assert result is True
        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["detected_by"] == "citation_parser"

    @pytest.mark.asyncio
    async def test_create_contradicts_relation(self, dao, mock_run_write_query):
        """create_contradicts_relation wrapper."""
        result = await dao.create_contradicts_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            confidence=0.6,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_create_cites_relation(self, dao, mock_run_write_query):
        """create_cites_relation wrapper."""
        result = await dao.create_cites_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            citation_text="[1] Smith et al. 2024",
            context="In the introduction section",
        )

        assert result is True
        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert params["confidence"] == 1.0  # CITES always 1.0

    @pytest.mark.asyncio
    async def test_create_cites_without_context(self, dao, mock_run_write_query):
        """create_cites_relation without context."""
        result = await dao.create_cites_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            citation_text="[1]",
        )

        assert result is True
        call_args = mock_run_write_query.call_args
        params = call_args[0][1]
        assert "Context:" not in params["evidence"]


# ===========================================================================
# Test: Getter Methods
# ===========================================================================

class TestGetterMethods:
    """Test relation getter methods."""

    @pytest.mark.asyncio
    async def test_get_paper_relations_outgoing(self, dao, mock_run_query):
        """Get outgoing relations."""
        mock_run_query.return_value = [
            {"relation_type": "SUPPORTS", "confidence": 0.9}
        ]

        results = await dao.get_paper_relations(
            paper_id="paper_001",
            direction="outgoing"
        )

        assert len(results) == 1
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_paper_relations_incoming(self, dao, mock_run_query):
        """Get incoming relations."""
        await dao.get_paper_relations(
            paper_id="paper_001",
            direction="incoming"
        )

        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_paper_relations_both(self, dao, mock_run_query):
        """Get both directions."""
        await dao.get_paper_relations(
            paper_id="paper_001",
            direction="both"
        )

        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_paper_relations_invalid_direction(self, dao):
        """Invalid direction should raise ValidationError."""
        with pytest.raises(ValidationError):
            await dao.get_paper_relations(
                paper_id="paper_001",
                direction="invalid"
            )

    @pytest.mark.asyncio
    async def test_get_paper_relations_with_type_filter(self, dao, mock_run_query):
        """Type filter should be included in query."""
        await dao.get_paper_relations(
            paper_id="paper_001",
            relation_types=["SUPPORTS", "CONTRADICTS"],
            direction="outgoing"
        )

        mock_run_query.assert_called_once()
        # Check that relation types are in the query
        query_str = mock_run_query.call_args[0][0]
        assert "SUPPORTS" in query_str
        assert "CONTRADICTS" in query_str

    @pytest.mark.asyncio
    async def test_get_related_papers(self, dao, mock_run_query):
        """Get related papers by type."""
        mock_run_query.return_value = [
            {"target": {"paper_id": "paper_002"}, "confidence": 0.8}
        ]

        results = await dao.get_related_papers(
            paper_id="paper_001",
            relation_type="SUPPORTS",
            min_confidence=0.5,
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_related_papers_invalid_type(self, dao):
        """Invalid relation type should raise ValidationError."""
        with pytest.raises(ValidationError):
            await dao.get_related_papers(
                paper_id="paper_001",
                relation_type="INVALID",
            )

    @pytest.mark.asyncio
    async def test_get_supporting_papers(self, dao, mock_run_query):
        """get_supporting_papers convenience method."""
        await dao.get_supporting_papers("paper_001", limit=5)
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_contradicting_papers(self, dao, mock_run_query):
        """get_contradicting_papers convenience method."""
        await dao.get_contradicting_papers("paper_001")
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_similar_papers(self, dao, mock_run_query):
        """get_similar_papers convenience method."""
        await dao.get_similar_papers("paper_001")
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_citing_papers(self, dao, mock_run_query):
        """get_citing_papers (incoming CITES)."""
        await dao.get_citing_papers("paper_001")
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cited_papers(self, dao, mock_run_query):
        """get_cited_papers (outgoing CITES)."""
        await dao.get_cited_papers("paper_001")
        mock_run_query.assert_called_once()


# ===========================================================================
# Test: Management Methods
# ===========================================================================

class TestManagementMethods:
    """Test delete and update methods."""

    @pytest.mark.asyncio
    async def test_delete_paper_relation(self, dao, mock_run_write_query):
        """Delete existing relation."""
        mock_run_write_query.return_value = {"relationships_deleted": 1}

        result = await dao.delete_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_paper_relation_not_found(self, dao, mock_run_write_query):
        """Delete non-existent relation returns False."""
        mock_run_write_query.return_value = {"relationships_deleted": 0}

        result = await dao.delete_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_paper_relation_invalid_type(self, dao):
        """Delete with invalid relation type raises ValidationError."""
        with pytest.raises(ValidationError):
            await dao.delete_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="INVALID",
            )

    @pytest.mark.asyncio
    async def test_delete_paper_relation_neo4j_error(self, dao, mock_run_write_query):
        """Delete with Neo4j error should propagate."""
        mock_run_write_query.side_effect = Exception("Connection lost")

        with pytest.raises(Exception, match="Connection lost"):
            await dao.delete_paper_relation(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
            )

    @pytest.mark.asyncio
    async def test_update_confidence(self, dao, mock_run_write_query):
        """Update relation confidence."""
        mock_run_write_query.return_value = {"properties_set": 2}

        result = await dao.update_paper_relation_confidence(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
            new_confidence=0.95,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_update_confidence_not_found(self, dao, mock_run_write_query):
        """Update non-existent relation returns False."""
        mock_run_write_query.return_value = {"properties_set": 0}

        result = await dao.update_paper_relation_confidence(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type="SUPPORTS",
            new_confidence=0.95,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_confidence_invalid_type(self, dao):
        """Update with invalid relation type raises ValidationError."""
        with pytest.raises(ValidationError):
            await dao.update_paper_relation_confidence(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="INVALID",
                new_confidence=0.5,
            )

    @pytest.mark.asyncio
    async def test_update_confidence_out_of_range(self, dao):
        """Update with confidence out of range raises ValidationError."""
        with pytest.raises(ValidationError):
            await dao.update_paper_relation_confidence(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
                new_confidence=1.5,
            )

    @pytest.mark.asyncio
    async def test_update_confidence_neo4j_error(self, dao, mock_run_write_query):
        """Update with Neo4j error should propagate."""
        mock_run_write_query.side_effect = Exception("Timeout")

        with pytest.raises(Exception, match="Timeout"):
            await dao.update_paper_relation_confidence(
                source_paper_id="paper_001",
                target_paper_id="paper_002",
                relation_type="SUPPORTS",
                new_confidence=0.5,
            )


# ===========================================================================
# Test: Valid Relation Types
# ===========================================================================

class TestValidRelationTypes:
    """Test valid paper relation types constant."""

    def test_all_expected_types(self):
        """All expected relation types should be present."""
        expected = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
        assert _VALID_PAPER_RELATION_TYPES == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rel_type", [
        "SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"
    ])
    async def test_all_valid_types_accepted(self, dao, mock_run_write_query, rel_type):
        """All valid relation types should be accepted."""
        result = await dao.create_paper_relation(
            source_paper_id="paper_001",
            target_paper_id="paper_002",
            relation_type=rel_type,
        )
        # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
