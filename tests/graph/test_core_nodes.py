"""Tests for core_nodes module.

PaperNode, ChunkNode, PathologyNode, AnatomyNode, InterventionNode, OutcomeNode
dataclass 생성, 기본값 검증, to_neo4j_properties/from_neo4j_record 직렬화 테스트.
"""

import pytest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from graph.types.core_nodes import (
    PaperNode,
    ChunkNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
)


# ===========================================================================
# Test: PaperNode
# ===========================================================================

class TestPaperNode:
    """PaperNode dataclass tests."""

    def test_minimal_creation(self):
        node = PaperNode(paper_id="p001", title="Test Paper")
        assert node.paper_id == "p001"
        assert node.title == "Test Paper"

    def test_default_values(self):
        node = PaperNode(paper_id="p001", title="Test")
        assert node.document_type == "journal-article"
        assert node.year == 0
        assert node.evidence_level == "5"
        assert node.language == "en"
        assert node.source == "pdf"
        assert node.is_abstract_only is False
        assert node.authors == []
        assert node.tags == []
        assert node.created_at is None
        assert node.owner == "system"
        assert node.shared is True

    def test_full_creation(self):
        node = PaperNode(
            paper_id="p001", title="UBE vs MIS-TLIF",
            authors=["Kim JH", "Park SM"],
            year=2024, journal="Spine", journal_abbrev="Spine",
            volume="49", issue="6", pages="100-110",
            doi="10.1097/BRS.000001234", pmid="38012345",
            study_type="RCT", evidence_level="1b",
            sample_size=150, sub_domains=["degenerative"],
            anatomy_levels=["L4-5", "L5-S1"],
        )
        assert node.authors == ["Kim JH", "Park SM"]
        assert node.study_type == "RCT"
        assert node.evidence_level == "1b"
        assert node.sample_size == 150

    def test_to_neo4j_properties(self):
        node = PaperNode(
            paper_id="p001", title="Test Paper",
            authors=["Kim JH"], year=2024,
        )
        props = node.to_neo4j_properties()
        assert props["paper_id"] == "p001"
        assert props["title"] == "Test Paper"
        assert props["authors"] == ["Kim JH"]
        assert props["year"] == 2024
        assert "created_at" in props
        assert "updated_at" in props

    def test_to_neo4j_properties_filters_none(self):
        node = PaperNode(paper_id="p001", title="Test")
        props = node.to_neo4j_properties()
        # None values should be filtered out
        for v in props.values():
            assert v is not None

    def test_to_neo4j_truncation(self):
        """Long fields should be truncated."""
        long_abstract = "A" * 5000
        node = PaperNode(paper_id="p001", title="Test", abstract=long_abstract)
        props = node.to_neo4j_properties()
        assert len(props["abstract"]) <= 2000

    def test_from_neo4j_record(self):
        record = {
            "paper_id": "p001",
            "title": "Test Paper",
            "authors": ["Kim JH"],
            "year": 2024,
            "evidence_level": "1b",
            "sub_domains": ["degenerative"],
        }
        node = PaperNode.from_neo4j_record(record)
        assert node.paper_id == "p001"
        assert node.title == "Test Paper"
        assert node.evidence_level == "1b"
        assert node.sub_domains == ["degenerative"]

    def test_from_neo4j_record_empty(self):
        node = PaperNode.from_neo4j_record({})
        assert node.paper_id == ""
        assert node.title == ""
        assert node.evidence_level == "5"
        assert node.document_type == "journal-article"

    def test_round_trip_serialization(self):
        original = PaperNode(
            paper_id="p001", title="Round Trip Test",
            authors=["Lee A", "Kim B"], year=2023,
            study_type="Cohort", evidence_level="2a",
        )
        props = original.to_neo4j_properties()
        restored = PaperNode.from_neo4j_record(props)
        assert restored.paper_id == original.paper_id
        assert restored.title == original.title
        assert restored.authors == original.authors
        assert restored.study_type == original.study_type

    def test_is_v7_processed(self):
        node = PaperNode(paper_id="p001", title="T", processing_version="v7.5")
        assert node.is_v7_processed() is True

        node2 = PaperNode(paper_id="p002", title="T", processing_version="v6.0")
        assert node2.is_v7_processed() is False

    def test_get_display_summary_with_summary(self):
        node = PaperNode(paper_id="p001", title="T", summary="Summary text")
        assert node.get_display_summary() == "Summary text"

    def test_get_display_summary_fallback_to_abstract(self):
        node = PaperNode(paper_id="p001", title="T", abstract="Abstract text")
        assert node.get_display_summary() == "Abstract text"

    def test_get_display_summary_no_data(self):
        node = PaperNode(paper_id="p001", title="T")
        assert node.get_display_summary() == "No summary available"


# ===========================================================================
# Test: ChunkNode
# ===========================================================================

class TestChunkNode:
    """ChunkNode dataclass tests."""

    def test_creation(self):
        node = ChunkNode(chunk_id="c001", paper_id="p001", content="Text")
        assert node.chunk_id == "c001"
        assert node.paper_id == "p001"
        assert node.content == "Text"

    def test_default_values(self):
        node = ChunkNode(chunk_id="c001", paper_id="p001", content="T")
        assert node.tier == "tier2"
        assert node.content_type == "text"
        assert node.evidence_level == "5"
        assert node.embedding == []
        assert node.is_key_finding is False

    def test_to_neo4j_properties(self):
        node = ChunkNode(chunk_id="c001", paper_id="p001", content="Text content")
        props = node.to_neo4j_properties()
        assert props["chunk_id"] == "c001"
        assert props["paper_id"] == "p001"
        assert props["content"] == "Text content"
        assert "created_at" in props

    def test_from_neo4j_record(self):
        record = {
            "chunk_id": "c001", "paper_id": "p001",
            "content": "Text", "tier": "tier1",
            "is_key_finding": True,
        }
        node = ChunkNode.from_neo4j_record(record)
        assert node.chunk_id == "c001"
        assert node.tier == "tier1"
        assert node.is_key_finding is True


# ===========================================================================
# Test: PathologyNode
# ===========================================================================

class TestPathologyNode:
    """PathologyNode dataclass tests."""

    def test_creation(self):
        node = PathologyNode(name="Lumbar Stenosis")
        assert node.name == "Lumbar Stenosis"

    def test_default_values(self):
        node = PathologyNode(name="Test")
        assert node.category == ""
        assert node.snomed_code == ""
        assert node.aliases == []

    def test_to_neo4j_and_back(self):
        node = PathologyNode(
            name="Lumbar Stenosis", category="degenerative",
            snomed_code="18347007", aliases=["LSS", "Central Stenosis"],
        )
        props = node.to_neo4j_properties()
        restored = PathologyNode.from_neo4j_record(props)
        assert restored.name == "Lumbar Stenosis"
        assert restored.category == "degenerative"
        assert restored.snomed_code == "18347007"
        assert restored.aliases == ["LSS", "Central Stenosis"]


# ===========================================================================
# Test: AnatomyNode
# ===========================================================================

class TestAnatomyNode:
    """AnatomyNode dataclass tests."""

    def test_creation(self):
        node = AnatomyNode(name="L4-5")
        assert node.name == "L4-5"

    def test_default_values(self):
        node = AnatomyNode(name="L4-5")
        assert node.region == ""
        assert node.level_count == 1

    def test_to_neo4j_and_back(self):
        node = AnatomyNode(name="L4-5", region="lumbar", level_count=1)
        props = node.to_neo4j_properties()
        restored = AnatomyNode.from_neo4j_record(props)
        assert restored.name == "L4-5"
        assert restored.region == "lumbar"
        assert restored.level_count == 1


# ===========================================================================
# Test: InterventionNode
# ===========================================================================

class TestInterventionNode:
    """InterventionNode dataclass tests."""

    def test_creation(self):
        node = InterventionNode(name="TLIF")
        assert node.name == "TLIF"

    def test_default_values(self):
        node = InterventionNode(name="TLIF")
        assert node.full_name == ""
        assert node.category == ""
        assert node.is_minimally_invasive is False
        assert node.surgical_steps == []
        assert node.required_implants == []
        assert node.learning_curve_cases == 0

    def test_full_creation(self):
        node = InterventionNode(
            name="UBE", full_name="Unilateral Biportal Endoscopy",
            category="decompression", approach="posterior",
            is_minimally_invasive=True,
            technique_description="Two small incisions...",
            difficulty_level="advanced",
            pearls=["Maintain clear visualization"],
            pitfalls=["Dural tear risk"],
            learning_curve_cases=30,
            surgical_steps=[{"step": 1, "name": "Exposure"}],
        )
        assert node.is_minimally_invasive is True
        assert node.difficulty_level == "advanced"
        assert len(node.pearls) == 1

    def test_to_neo4j_truncation(self):
        long_desc = "D" * 5000
        node = InterventionNode(name="TLIF", technique_description=long_desc)
        props = node.to_neo4j_properties()
        assert len(props["technique_description"]) <= 2000

    def test_to_neo4j_and_back(self):
        node = InterventionNode(
            name="TLIF", full_name="Transforaminal Lumbar Interbody Fusion",
            category="fusion", approach="posterior",
            snomed_code="447764006",
        )
        props = node.to_neo4j_properties()
        restored = InterventionNode.from_neo4j_record(props)
        assert restored.name == "TLIF"
        assert restored.snomed_code == "447764006"


# ===========================================================================
# Test: OutcomeNode
# ===========================================================================

class TestOutcomeNode:
    """OutcomeNode dataclass tests."""

    def test_creation(self):
        node = OutcomeNode(name="VAS")
        assert node.name == "VAS"

    def test_default_values(self):
        node = OutcomeNode(name="VAS")
        assert node.type == ""
        assert node.unit == ""
        assert node.direction == ""

    def test_to_neo4j_and_back(self):
        node = OutcomeNode(
            name="VAS", type="pain",
            unit="mm", direction="lower_is_better",
            description="Visual Analog Scale for pain",
        )
        props = node.to_neo4j_properties()
        restored = OutcomeNode.from_neo4j_record(props)
        assert restored.name == "VAS"
        assert restored.direction == "lower_is_better"
        assert restored.description == "Visual Analog Scale for pain"
