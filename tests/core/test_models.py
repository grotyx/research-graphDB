"""Tests for unified chunk models."""

import pytest
from dataclasses import asdict

from src.core.models import (
    ChunkBase,
    Tier1Chunk,
    Tier2Chunk,
    UnifiedChunk,
    RichChunk,
    ChunkTier,
    SectionType,
    SourceType,
    ContentType,
    EvidenceLevel,
    PICOData,
    StatisticsData,
    create_chunk,
    create_unified_chunk,
    convert_to_base_chunk,
)


class TestEnums:
    """Test enum definitions."""

    def test_chunk_tier_enum(self):
        """Test ChunkTier enum."""
        assert ChunkTier.TIER1.value == "tier1"
        assert ChunkTier.TIER2.value == "tier2"

    def test_section_type_enum(self):
        """Test SectionType enum."""
        assert SectionType.ABSTRACT.value == "abstract"
        assert SectionType.RESULTS.value == "results"
        assert SectionType.CONCLUSION.value == "conclusion"

    def test_source_type_enum(self):
        """Test SourceType enum."""
        assert SourceType.ORIGINAL.value == "original"
        assert SourceType.CITATION.value == "citation"

    def test_content_type_enum(self):
        """Test ContentType enum."""
        assert ContentType.TEXT.value == "text"
        assert ContentType.TABLE.value == "table"
        assert ContentType.FIGURE.value == "figure"

    def test_evidence_level_enum(self):
        """Test EvidenceLevel enum."""
        assert EvidenceLevel.LEVEL_1A.value == "1a"
        assert EvidenceLevel.LEVEL_1B.value == "1b"
        assert EvidenceLevel.LEVEL_5.value == "5"


class TestChunkBase:
    """Test ChunkBase class."""

    def test_create_basic_chunk(self):
        """Test creating a basic chunk."""
        chunk = ChunkBase(
            chunk_id="test_001",
            content="This is test content.",
            document_id="doc_123"
        )

        assert chunk.chunk_id == "test_001"
        assert chunk.content == "This is test content."
        assert chunk.document_id == "doc_123"
        assert chunk.tier == "tier2"  # Default
        assert chunk.section == "other"  # Default

    def test_chunk_with_full_metadata(self):
        """Test chunk with complete metadata."""
        chunk = ChunkBase(
            chunk_id="test_002",
            content="Full metadata chunk",
            document_id="doc_456",
            tier="tier1",
            section="abstract",
            content_type="text",
            source_type="original",
            page_number=5,
            char_start=100,
            char_end=500,
            title="Test Paper",
            authors=["Smith, J.", "Doe, A."],
            publication_year=2024,
            evidence_level="1b",
            topic_summary="Summary of findings",
            keywords=["spine", "surgery", "outcomes"],
            is_key_finding=True,
        )

        assert chunk.tier == "tier1"
        assert chunk.section == "abstract"
        assert chunk.page_number == 5
        assert chunk.title == "Test Paper"
        assert len(chunk.authors) == 2
        assert chunk.publication_year == 2024
        assert chunk.is_key_finding is True

    def test_tier_detection(self):
        """Test tier detection methods."""
        tier1 = ChunkBase("id1", "content1", "doc1", tier="tier1")
        tier2 = ChunkBase("id2", "content2", "doc2", tier="tier2")

        assert tier1.is_tier1() is True
        assert tier1.is_tier2() is False
        assert tier2.is_tier1() is False
        assert tier2.is_tier2() is True

    def test_get_tier_enum(self):
        """Test getting tier as enum."""
        tier1 = ChunkBase("id1", "content1", "doc1", tier="tier1")
        tier2 = ChunkBase("id2", "content2", "doc2", tier="tier2")

        assert tier1.get_tier_enum() == ChunkTier.TIER1
        assert tier2.get_tier_enum() == ChunkTier.TIER2

    def test_get_section_enum(self):
        """Test getting section as enum."""
        chunk = ChunkBase("id1", "content1", "doc1", section="results")
        assert chunk.get_section_enum() == SectionType.RESULTS

    def test_get_source_enum(self):
        """Test getting source type as enum."""
        chunk = ChunkBase("id1", "content1", "doc1", source_type="citation")
        assert chunk.get_source_enum() == SourceType.CITATION

    def test_get_content_enum(self):
        """Test getting content type as enum."""
        chunk = ChunkBase("id1", "content1", "doc1", content_type="table")
        assert chunk.get_content_enum() == ContentType.TABLE

    def test_to_dict(self):
        """Test converting chunk to dictionary."""
        chunk = ChunkBase(
            chunk_id="test_003",
            content="Dict test",
            document_id="doc_789",
            tier="tier1",
            section="results"
        )

        data = chunk.to_dict()

        assert isinstance(data, dict)
        assert data["chunk_id"] == "test_003"
        assert data["content"] == "Dict test"
        assert data["document_id"] == "doc_789"
        assert data["tier"] == "tier1"
        assert data["section"] == "results"

    def test_from_dict(self):
        """Test creating chunk from dictionary."""
        data = {
            "chunk_id": "test_004",
            "content": "From dict test",
            "document_id": "doc_999",
            "tier": "tier2",
            "section": "methods",
            "page_number": 10,
        }

        chunk = ChunkBase.from_dict(data)

        assert chunk.chunk_id == "test_004"
        assert chunk.content == "From dict test"
        assert chunk.tier == "tier2"
        assert chunk.section == "methods"
        assert chunk.page_number == 10

    def test_round_trip_serialization(self):
        """Test round-trip dict conversion."""
        original = ChunkBase(
            chunk_id="test_005",
            content="Round trip",
            document_id="doc_rt",
            keywords=["test", "keywords"]
        )

        data = original.to_dict()
        restored = ChunkBase.from_dict(data)

        assert restored.chunk_id == original.chunk_id
        assert restored.content == original.content
        assert restored.keywords == original.keywords


class TestTier1Chunk:
    """Test Tier1Chunk class."""

    def test_tier1_chunk_creation(self):
        """Test Tier1Chunk enforces tier1."""
        chunk = Tier1Chunk(
            chunk_id="tier1_001",
            content="Abstract content",
            document_id="doc_abc",
            section="abstract"
        )

        assert chunk.tier == "tier1"
        assert chunk.is_tier1() is True

    def test_tier1_overrides_tier_param(self):
        """Test Tier1Chunk overrides tier parameter."""
        chunk = Tier1Chunk(
            chunk_id="tier1_002",
            content="Results content",
            document_id="doc_xyz",
            tier="tier2"  # Will be overridden
        )

        assert chunk.tier == "tier1"  # Should be forced to tier1


class TestTier2Chunk:
    """Test Tier2Chunk class."""

    def test_tier2_chunk_creation(self):
        """Test Tier2Chunk enforces tier2."""
        chunk = Tier2Chunk(
            chunk_id="tier2_001",
            content="Methods content",
            document_id="doc_def",
            section="methods"
        )

        assert chunk.tier == "tier2"
        assert chunk.is_tier2() is True

    def test_tier2_overrides_tier_param(self):
        """Test Tier2Chunk overrides tier parameter."""
        chunk = Tier2Chunk(
            chunk_id="tier2_002",
            content="Discussion content",
            document_id="doc_ghi",
            tier="tier1"  # Will be overridden
        )

        assert chunk.tier == "tier2"  # Should be forced to tier2


class TestUnifiedChunk:
    """Test UnifiedChunk class."""

    def test_create_tier1_factory(self):
        """Test Tier 1 factory method."""
        chunk = UnifiedChunk.create_tier1(
            chunk_id="unified_001",
            content="Abstract",
            document_id="doc_unified",
            section="abstract"
        )

        assert chunk.is_tier1() is True
        assert chunk.section == "abstract"

    def test_create_tier2_factory(self):
        """Test Tier 2 factory method."""
        chunk = UnifiedChunk.create_tier2(
            chunk_id="unified_002",
            content="Methods",
            document_id="doc_unified",
            section="methods"
        )

        assert chunk.is_tier2() is True
        assert chunk.section == "methods"

    def test_upgrade_tier(self):
        """Test upgrading tier."""
        chunk = UnifiedChunk(
            chunk_id="unified_003",
            content="Key finding",
            document_id="doc_upgrade",
            tier="tier2",
            is_key_finding=True
        )

        assert chunk.is_tier2() is True

        chunk.upgrade_tier()

        assert chunk.is_tier1() is True

    def test_upgrade_tier_requires_key_finding(self):
        """Test upgrade requires key_finding flag."""
        chunk = UnifiedChunk(
            chunk_id="unified_004",
            content="Regular content",
            document_id="doc_upgrade",
            tier="tier2",
            is_key_finding=False
        )

        chunk.upgrade_tier()

        assert chunk.is_tier2() is True  # Should not upgrade

    def test_downgrade_tier(self):
        """Test downgrading tier."""
        chunk = UnifiedChunk(
            chunk_id="unified_005",
            content="Content",
            document_id="doc_downgrade",
            tier="tier1"
        )

        chunk.downgrade_tier()

        assert chunk.is_tier2() is True


class TestRichChunk:
    """Test RichChunk with PICO and statistics."""

    def test_rich_chunk_with_pico(self):
        """Test RichChunk with PICO data."""
        pico = PICOData(
            population="Patients with lumbar stenosis",
            intervention="UBE decompression",
            comparison="MIS-TLIF",
            outcome="VAS score"
        )

        chunk = RichChunk(
            chunk_id="rich_001",
            content="Study comparing UBE and MIS-TLIF",
            document_id="doc_rich",
            pico=pico
        )

        assert chunk.pico is not None
        assert chunk.pico.population == "Patients with lumbar stenosis"
        assert chunk.pico.intervention == "UBE decompression"

    def test_rich_chunk_with_statistics(self):
        """Test RichChunk with statistics."""
        stats = StatisticsData(
            p_values=["0.023", "0.045"],
            effect_sizes=["0.8"],
            confidence_intervals=["95% CI: 1.2-3.4"]
        )

        chunk = RichChunk(
            chunk_id="rich_002",
            content="Statistical results",
            document_id="doc_rich",
            statistics=stats,
            has_statistics=True
        )

        assert chunk.has_statistics is True
        assert chunk.statistics is not None
        assert len(chunk.statistics.p_values) == 2

    def test_rich_chunk_to_dict(self):
        """Test RichChunk serialization."""
        pico = PICOData(population="Test population")
        stats = StatisticsData(p_values=["0.05"])

        chunk = RichChunk(
            chunk_id="rich_003",
            content="Content",
            document_id="doc_rich",
            pico=pico,
            statistics=stats,
            has_statistics=True,
            llm_processed=True,
            llm_confidence=0.95
        )

        data = chunk.to_dict()

        assert data["pico"] is not None
        assert data["pico"]["population"] == "Test population"
        assert data["statistics"] is not None
        assert data["has_statistics"] is True
        assert data["llm_confidence"] == 0.95


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_chunk_tier1(self):
        """Test create_chunk factory for tier1."""
        chunk = create_chunk(
            chunk_id="factory_001",
            content="Test content",
            document_id="doc_factory",
            tier="tier1"
        )

        assert isinstance(chunk, Tier1Chunk)
        assert chunk.is_tier1() is True

    def test_create_chunk_tier2(self):
        """Test create_chunk factory for tier2."""
        chunk = create_chunk(
            chunk_id="factory_002",
            content="Test content",
            document_id="doc_factory",
            tier="tier2"
        )

        assert isinstance(chunk, Tier2Chunk)
        assert chunk.is_tier2() is True

    def test_create_chunk_default_tier(self):
        """Test create_chunk factory default tier."""
        chunk = create_chunk(
            chunk_id="factory_003",
            content="Test content",
            document_id="doc_factory"
        )

        assert isinstance(chunk, Tier2Chunk)  # Default is tier2

    def test_create_unified_chunk(self):
        """Test create_unified_chunk factory."""
        chunk = create_unified_chunk(
            chunk_id="unified_factory",
            content="Unified content",
            document_id="doc_unified",
            tier="tier1"
        )

        assert isinstance(chunk, UnifiedChunk)
        assert chunk.is_tier1() is True


class TestConversionUtilities:
    """Test chunk conversion utilities."""

    def test_convert_from_dict(self):
        """Test converting dict to ChunkBase."""
        data = {
            "chunk_id": "convert_001",
            "content": "Test content",
            "document_id": "doc_convert",
            "tier": "tier1"
        }

        chunk = convert_to_base_chunk(data)

        assert isinstance(chunk, ChunkBase)
        assert chunk.chunk_id == "convert_001"
        assert chunk.tier == "tier1"

    def test_convert_from_chunkbase(self):
        """Test converting ChunkBase (no-op)."""
        original = ChunkBase("id1", "content1", "doc1")
        converted = convert_to_base_chunk(original)

        assert converted is original  # Should be same object

    def test_convert_from_object_with_attributes(self):
        """Test converting object with chunk attributes."""
        class FakeChunk:
            chunk_id = "fake_001"
            content = "Fake content"
            document_id = "doc_fake"
            tier = "tier2"
            section = "results"

        fake = FakeChunk()
        chunk = convert_to_base_chunk(fake)

        assert isinstance(chunk, ChunkBase)
        assert chunk.chunk_id == "fake_001"
        assert chunk.content == "Fake content"
        assert chunk.tier == "tier2"

    def test_convert_handles_alternate_field_names(self):
        """Test conversion handles alternate field names."""
        class AlternateChunk:
            id = "alt_001"  # chunk_id
            text = "Alternate text"  # content
            document_id = "doc_alt"
            section_type = "methods"  # section
            page_num = 5  # page_number

        alt = AlternateChunk()
        chunk = convert_to_base_chunk(alt)

        assert chunk.chunk_id == "alt_001"
        assert chunk.content == "Alternate text"
        assert chunk.section == "methods"
        assert chunk.page_number == 5

    def test_convert_invalid_type_raises_error(self):
        """Test converting invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot convert"):
            convert_to_base_chunk("invalid string")

    def test_convert_none_raises_error(self):
        """Test converting None raises ValueError."""
        with pytest.raises((ValueError, AttributeError)):
            convert_to_base_chunk(None)


class TestCompatibilityAliases:
    """Test backward compatibility aliases."""

    def test_textchunk_alias(self):
        """Test TextChunk alias."""
        from src.core.models import TextChunk

        chunk = TextChunk("id1", "content1", "doc1")
        assert isinstance(chunk, ChunkBase)

    def test_chunkinfo_alias(self):
        """Test ChunkInfo alias."""
        from src.core.models import ChunkInfo

        chunk = ChunkInfo("id2", "content2", "doc2")
        assert isinstance(chunk, ChunkBase)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_content(self):
        """Test chunk with empty content."""
        chunk = ChunkBase(
            chunk_id="empty_001",
            content="",
            document_id="doc_empty"
        )

        assert chunk.content == ""
        assert chunk.chunk_id == "empty_001"

    def test_none_optional_fields(self):
        """Test None values in optional fields."""
        chunk = ChunkBase(
            chunk_id="none_001",
            content="Content",
            document_id="doc_none",
            title=None,
            page_number=None
        )

        assert chunk.title is None
        assert chunk.page_number is None

    def test_empty_lists(self):
        """Test empty list fields."""
        chunk = ChunkBase(
            chunk_id="empty_list",
            content="Content",
            document_id="doc_list",
            authors=[],
            keywords=[]
        )

        assert chunk.authors == []
        assert chunk.keywords == []

    def test_case_insensitive_tier(self):
        """Test tier detection is case-insensitive."""
        chunk1 = ChunkBase("id1", "c1", "d1", tier="TIER1")
        chunk2 = ChunkBase("id2", "c2", "d2", tier="Tier1")
        chunk3 = ChunkBase("id3", "c3", "d3", tier="tier1")

        assert chunk1.is_tier1() is True
        assert chunk2.is_tier1() is True
        assert chunk3.is_tier1() is True

    def test_invalid_section_returns_other(self):
        """Test invalid section type returns OTHER."""
        chunk = ChunkBase("id1", "c1", "d1", section="invalid_section")

        section_enum = chunk.get_section_enum()
        assert section_enum == SectionType.OTHER

    def test_metadata_dict_flexibility(self):
        """Test metadata dict can hold arbitrary data."""
        chunk = ChunkBase(
            chunk_id="meta_001",
            content="Content",
            document_id="doc_meta",
            metadata={
                "custom_field": "custom_value",
                "nested": {"key": "value"},
                "number": 42
            }
        )

        assert chunk.metadata["custom_field"] == "custom_value"
        assert chunk.metadata["nested"]["key"] == "value"
        assert chunk.metadata["number"] == 42
