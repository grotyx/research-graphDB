"""Tests for SQLite to Neo4j migration script."""

import asyncio
import pytest
import tempfile
import sqlite3
from pathlib import Path

from knowledge.paper_graph import PaperGraph, PaperNode, PaperRelation, RelationType, PICOSummary
from graph.neo4j_client import Neo4jClient

# Add scripts to path
import sys
scripts_path = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from migrate_sqlite_to_neo4j import SQLiteToNeo4jMigrator


@pytest.fixture
async def sample_sqlite_db():
    """Create a temporary SQLite database with sample data."""
    # Create temp database
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_db.name
    temp_db.close()

    # Initialize graph (PaperGraph doesn't support async context manager)
    graph = PaperGraph(db_path)
    await graph.initialize()

    # Add sample papers
    paper1 = PaperNode(
        paper_id="test_001",
        title="TLIF vs PLIF for Lumbar Stenosis",
        authors=["Smith J", "Jones K"],
        year=2023,
        journal="Spine",
        doi="10.1097/test001",
        pmid="12345678",
        evidence_level="1b",
        abstract_summary="RCT comparing TLIF and PLIF for lumbar stenosis.",
        pico_summary=PICOSummary(
            population="Patients with lumbar stenosis",
            intervention="TLIF",
            comparison="PLIF",
            outcome="VAS, Fusion rate"
        ),
        main_findings=["TLIF showed better fusion rate", "No difference in VAS"],
        keywords=["TLIF", "PLIF", "stenosis"]
    )

    paper2 = PaperNode(
        paper_id="test_002",
        title="UBE for Lumbar Disc Herniation",
        authors=["Park SM", "Kim JH"],
        year=2024,
        journal="J Neurosurg Spine",
        doi="10.3171/test002",
        pmid="87654321",
        evidence_level="2b",
        abstract_summary="Prospective cohort study of UBE for disc herniation.",
        main_findings=["UBE effective for LDH", "Low complication rate"],
    )

    paper3 = PaperNode(
        paper_id="test_003",
        title="Scoliosis Correction with PSO",
        authors=["Lee DH", "Choi YS"],
        year=2022,
        journal="Eur Spine J",
        evidence_level="3",
        abstract_summary="Case series of PSO for adult scoliosis.",
    )

    await graph.add_paper(paper1)
    await graph.add_paper(paper2)
    await graph.add_paper(paper3)

    # Add relations
    await graph.add_relation(PaperRelation(
        source_id="test_002",
        target_id="test_001",
        relation_type=RelationType.CITES,
        confidence=1.0,
        evidence="Paper 2 cites Paper 1 in introduction",
        detected_by="citation_extraction"
    ))

    await graph.add_relation(PaperRelation(
        source_id="test_002",
        target_id="test_001",
        relation_type=RelationType.SUPPORTS,
        confidence=0.8,
        evidence="Both show fusion is effective",
        detected_by="llm_analysis"
    ))

    await graph.add_relation(PaperRelation(
        source_id="test_003",
        target_id="test_001",
        relation_type=RelationType.SIMILAR_TOPIC,
        confidence=0.6,
        evidence="Both about spinal surgery",
        detected_by="pico_similarity"
    ))

    await graph.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink()


@pytest.mark.asyncio
async def test_convert_paper():
    """Test paper conversion from SQLite to Neo4j format."""
    migrator = SQLiteToNeo4jMigrator()

    sqlite_paper = PaperNode(
        paper_id="test_001",
        title="TLIF for Lumbar Stenosis",
        authors=["Smith J"],
        year=2023,
        journal="Spine",
        doi="10.1097/test",
        pmid="12345",
        evidence_level="1b",
        abstract_summary="RCT of TLIF for stenosis.",
    )

    neo4j_paper = migrator._convert_paper(sqlite_paper)

    assert neo4j_paper.paper_id == "test_001"
    assert neo4j_paper.title == "TLIF for Lumbar Stenosis"
    assert neo4j_paper.authors == ["Smith J"]
    assert neo4j_paper.year == 2023
    assert neo4j_paper.journal == "Spine"
    assert neo4j_paper.doi == "10.1097/test"
    assert neo4j_paper.pmid == "12345"
    assert neo4j_paper.evidence_level == "1b"
    assert neo4j_paper.abstract == "RCT of TLIF for stenosis."


@pytest.mark.asyncio
async def test_infer_sub_domain():
    """Test sub-domain inference."""
    migrator = SQLiteToNeo4jMigrator()

    # Deformity
    paper1 = PaperNode(
        paper_id="test_001",
        title="Scoliosis correction with osteotomy",
        abstract_summary="Adult scoliosis patients underwent PSO.",
    )
    assert migrator._infer_sub_domain(paper1) == "Deformity"

    # Trauma
    paper2 = PaperNode(
        paper_id="test_002",
        title="Burst fracture treatment",
        abstract_summary="Vertebral burst fractures were stabilized.",
    )
    assert migrator._infer_sub_domain(paper2) == "Trauma"

    # Tumor
    paper3 = PaperNode(
        paper_id="test_003",
        title="Spinal metastasis resection",
        abstract_summary="Metastatic tumor was removed.",
    )
    assert migrator._infer_sub_domain(paper3) == "Tumor"

    # Degenerative (default)
    paper4 = PaperNode(
        paper_id="test_004",
        title="TLIF for stenosis",
        abstract_summary="Lumbar stenosis treated with TLIF.",
    )
    assert migrator._infer_sub_domain(paper4) == "Degenerative"


@pytest.mark.asyncio
async def test_infer_study_design():
    """Test study design inference."""
    migrator = SQLiteToNeo4jMigrator()

    tests = [
        (PaperNode(paper_id="p1", title="Test 1", evidence_level="1a"), "meta-analysis"),
        (PaperNode(paper_id="p2", title="Test 2", evidence_level="1b"), "RCT"),
        (PaperNode(paper_id="p3", title="Test 3", evidence_level="2a"), "systematic-review"),
        (PaperNode(paper_id="p4", title="Test 4", evidence_level="2b"), "prospective-cohort"),
        (PaperNode(paper_id="p5", title="Test 5", evidence_level="3"), "retrospective-cohort"),
        (PaperNode(paper_id="p6", title="Test 6", evidence_level="4"), "case-series"),
        (PaperNode(paper_id="p7", title="Test 7", evidence_level="5"), "expert-opinion"),
        (PaperNode(paper_id="p8", title="Test 8", evidence_level=None), "expert-opinion"),
    ]

    for paper, expected_design in tests:
        assert migrator._infer_study_design(paper) == expected_design


@pytest.mark.asyncio
async def test_load_sqlite_papers(sample_sqlite_db):
    """Test loading papers from SQLite."""
    migrator = SQLiteToNeo4jMigrator(sqlite_db_path=sample_sqlite_db)

    papers = await migrator._load_sqlite_papers()

    assert len(papers) == 3
    assert papers[0].paper_id in ["test_001", "test_002", "test_003"]


@pytest.mark.asyncio
async def test_load_sqlite_relations(sample_sqlite_db):
    """Test loading relations from SQLite."""
    migrator = SQLiteToNeo4jMigrator(sqlite_db_path=sample_sqlite_db)

    relations = await migrator._load_sqlite_relations()

    # Should have 3 relations (CITES, SUPPORTS, SIMILAR_TOPIC)
    assert len(relations) == 3

    # Check relation types
    rel_types = {rel.relation_type for rel in relations}
    assert RelationType.CITES in rel_types
    assert RelationType.SUPPORTS in rel_types
    assert RelationType.SIMILAR_TOPIC in rel_types


@pytest.mark.asyncio
async def test_dry_run_migration(sample_sqlite_db):
    """Test dry-run migration (no actual Neo4j writes)."""
    migrator = SQLiteToNeo4jMigrator(
        sqlite_db_path=sample_sqlite_db,
        dry_run=True
    )

    stats = await migrator.migrate_all()

    # Should load papers and relations but not write to Neo4j
    assert stats.papers_loaded == 3
    assert stats.papers_migrated == 3  # Counted but not written
    assert stats.relations_loaded == 3
    # SIMILAR_TOPIC is skipped, so only 2 relations migrated
    assert stats.relations_migrated == 2

    # No errors expected in dry-run
    assert stats.papers_failed == 0
    assert stats.relations_failed == 0


@pytest.mark.asyncio
async def test_relation_mapping():
    """Test relation type mapping."""
    migrator = SQLiteToNeo4jMigrator()

    assert migrator.RELATION_MAPPING[RelationType.CITES] == "CITES"
    assert migrator.RELATION_MAPPING[RelationType.SUPPORTS] == "SUPPORTS"
    assert migrator.RELATION_MAPPING[RelationType.CONTRADICTS] == "CONTRADICTS"
    assert migrator.RELATION_MAPPING[RelationType.EXTENDS] == "SUPPORTS"
    assert migrator.RELATION_MAPPING[RelationType.REPLICATES] == "SUPPORTS"

    # SIMILAR_TOPIC should not be in mapping
    assert RelationType.SIMILAR_TOPIC not in migrator.RELATION_MAPPING


@pytest.mark.asyncio
async def test_migration_stats():
    """Test migration statistics dataclass."""
    from migrate_sqlite_to_neo4j import MigrationStats

    stats = MigrationStats()
    assert stats.papers_loaded == 0
    assert stats.papers_migrated == 0
    assert stats.errors == []

    # Update stats
    stats.papers_loaded = 10
    stats.papers_migrated = 9
    stats.papers_failed = 1

    # Check string representation
    stats_str = str(stats)
    assert "Papers" in stats_str
    assert "9" in stats_str
    assert "90.0%" in stats_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
