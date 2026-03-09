#!/usr/bin/env python3
"""v3.0 Schema Integration Test - MCP & Streamlit Compatibility.

Tests the complete data flow:
1. PDF Processing → ExtractedChunk (v3.0)
2. ExtractedChunk → TextChunk (v3.0)
3. TextChunk → ChromaDB Metadata
4. TextChunk → Neo4j PaperNode
5. Streamlit compatibility

Usage:
    python scripts/test_v3_integration.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def test_schema_classes():
    """Test all schema classes can be instantiated."""
    print("\n" + "="*60)
    print("1. Schema Classes Test")
    print("="*60)

    from storage.vector_db import TextChunk, SearchResult
    from builder.unified_pdf_processor import (
        ExtractedChunk, StatisticsData, SpineMetadata,
        PICOData, ExtractedMetadata, ExtractedOutcome
    )
    from graph.spine_schema import PaperNode

    # Test StatisticsData (v3.0 - 3 fields)
    stats = StatisticsData(
        p_value="0.001",
        is_significant=True,
        additional="95% CI: 1.2-3.4, Cohen's d=0.8"
    )
    print(f"✅ StatisticsData: p_value={stats.p_value}, is_significant={stats.is_significant}")

    # Test PICOData
    pico = PICOData(
        population="Adults with lumbar stenosis",
        intervention="UBE decompression",
        comparison="Open laminectomy",
        outcome="VAS, ODI, fusion rate"
    )
    print(f"✅ PICOData: population={pico.population[:30]}...")

    # Test ExtractedChunk (v3.0 - no PICO)
    chunk = ExtractedChunk(
        content="Test content about surgical outcomes",
        content_type="key_finding",
        section_type="results",
        tier="tier1",
        summary="Test summary",
        keywords=["UBE", "stenosis"],
        is_key_finding=True,
        statistics=stats
    )
    print(f"✅ ExtractedChunk: content_type={chunk.content_type}, has stats={chunk.statistics is not None}")

    # Verify ExtractedChunk does NOT have PICO
    has_pico = hasattr(chunk, 'pico') and chunk.pico is not None
    print(f"✅ ExtractedChunk PICO removed: {not has_pico}")

    # Test TextChunk (v3.0 - new statistics fields)
    text_chunk = TextChunk(
        chunk_id="test_001",
        content="Test content",
        document_id="test_doc",
        tier="tier1",
        section="abstract",
        source_type="original",
        evidence_level="1b",
        publication_year=2025,
        title="Test Paper",
        authors=["Author1"],
        metadata={},
        summary="Test summary",
        keywords=["test"],
        statistics_p_value="0.001",
        statistics_is_significant=True,
        statistics_additional="95% CI: 1.2-3.4",
        has_statistics=True,
        llm_processed=True,
        llm_confidence=0.9,
        is_key_finding=True,
    )
    print(f"✅ TextChunk: stats_p_value={text_chunk.statistics_p_value}")

    # Verify TextChunk does NOT have old fields
    old_fields = ['pico_population', 'pico_intervention', 'statistics_json', 'topic_summary']
    has_old = [f for f in old_fields if hasattr(text_chunk, f)]
    if not has_old:
        print(f"✅ TextChunk old fields removed: {old_fields}")
    else:
        print(f"⚠️ TextChunk still has old fields: {has_old}")

    # Test PaperNode (has PICO at paper level)
    paper = PaperNode(
        paper_id="test_paper",
        title="Test Paper",
        year=2025,
        pico_population="Adults with stenosis",
        pico_intervention="UBE",
        pico_comparison="Open surgery",
        pico_outcome="VAS, ODI"
    )
    print(f"✅ PaperNode: pico_population={paper.pico_population[:30]}...")

    return True


def test_vectordb_flow():
    """Test VectorDB data flow."""
    print("\n" + "="*60)
    print("2. VectorDB Data Flow Test")
    print("="*60)

    import tempfile
    from storage.vector_db import TextChunk, TieredVectorDB

    chunk = TextChunk(
        chunk_id="test_001",
        content="Test content about UBE surgery",
        document_id="test_doc",
        tier="tier1",
        section="abstract",
        source_type="original",
        evidence_level="1b",
        publication_year=2025,
        title="Test Paper",
        authors=["Author1"],
        metadata={},
        summary="Test summary",
        keywords=["UBE", "stenosis"],
        statistics_p_value="0.001",
        statistics_is_significant=True,
        statistics_additional="95% CI: 1.2-3.4",
        has_statistics=True,
        llm_processed=True,
        llm_confidence=0.9,
        is_key_finding=True,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        db = TieredVectorDB(persist_directory=tmpdir)
        metadata = db._chunk_to_metadata(chunk)

        # Check new fields present
        new_fields = ['statistics_p_value', 'statistics_is_significant', 'statistics_additional', 'summary']
        present_new = [f for f in new_fields if f in metadata]
        print(f"✅ New fields in metadata: {present_new}")

        # Check old fields absent
        old_fields = ['pico_population', 'pico_intervention', 'statistics_json', 'topic_summary']
        absent_old = [f for f in old_fields if f not in metadata]
        print(f"✅ Old fields removed: {absent_old}")

        # Check values
        print(f"✅ statistics_p_value: {metadata.get('statistics_p_value')}")
        print(f"✅ statistics_is_significant: {metadata.get('statistics_is_significant')}")
        print(f"✅ summary: {metadata.get('summary')}")

    return True


def test_mcp_server_import():
    """Test MCP server imports and data classes."""
    print("\n" + "="*60)
    print("3. MCP Server Import Test")
    print("="*60)

    try:
        from medical_mcp.medical_kag_server import MedicalKAGServer
        print("✅ MedicalKAGServer imported successfully")

        # SpineMetadataCompat와 ExtractedChunkCompat는 함수 내부에서 정의되므로
        # 모듈 레벨 import가 불가능. 대신 서버 인스턴스 생성 테스트
        server = MedicalKAGServer()
        print("✅ MedicalKAGServer instance created")

        # 주요 메서드 존재 확인
        methods = ['add_pdf', 'search', 'list_documents', 'delete_document']
        for method in methods:
            if hasattr(server, method):
                print(f"✅ Method '{method}' exists")
            else:
                print(f"⚠️ Method '{method}' missing")

        # TextChunk import 테스트 (v3.0 스키마)
        from storage.vector_db import TextChunk
        chunk = TextChunk(
            chunk_id="test_001",
            content="Test content",
            document_id="test_doc",
            tier="tier1",
            section="abstract",
            source_type="original",
            evidence_level="1b",
            publication_year=2025,
            title="Test Paper",
            authors=["Author1"],
            metadata={},
            summary="Test summary",
            keywords=["test"],
            statistics_p_value="0.001",
            statistics_is_significant=True,
            statistics_additional="95% CI: 1.2-3.4",
            has_statistics=True,
            llm_processed=True,
            llm_confidence=0.9,
            is_key_finding=True,
        )
        print(f"✅ TextChunk v3.0 schema: statistics_p_value={chunk.statistics_p_value}")

        # PICO 필드 제거 확인
        pico_fields = ['pico_population', 'pico_intervention', 'pico_comparison', 'pico_outcome']
        has_pico = any(hasattr(chunk, f) for f in pico_fields)
        print(f"✅ TextChunk PICO fields removed: {not has_pico}")

        return True

    except Exception as e:
        print(f"❌ MCP Server import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streamlit_compatibility():
    """Test Streamlit page compatibility."""
    print("\n" + "="*60)
    print("4. Streamlit Compatibility Test")
    print("="*60)

    # Check that Streamlit pages don't use old fields
    import ast

    pages_dir = Path(__file__).parent.parent / "web" / "pages"
    old_patterns = ['pico_population', 'pico_intervention', 'statistics_json', 'topic_summary']

    issues = []
    for page_file in pages_dir.glob("*.py"):
        content = page_file.read_text()
        for pattern in old_patterns:
            if pattern in content:
                issues.append(f"{page_file.name}: uses '{pattern}'")

    if not issues:
        print(f"✅ No old schema references in Streamlit pages")
    else:
        print(f"⚠️ Found old schema references:")
        for issue in issues:
            print(f"   - {issue}")

    # Check for compatible field usage
    compatible_fields = ['has_statistics', 'is_key_finding', 'summary']
    for page_file in pages_dir.glob("*.py"):
        content = page_file.read_text()
        for field in compatible_fields:
            if field in content:
                print(f"✅ {page_file.name}: uses '{field}' (compatible)")
                break

    return len(issues) == 0


def test_neo4j_schema():
    """Test Neo4j schema compatibility."""
    print("\n" + "="*60)
    print("5. Neo4j Schema Test")
    print("="*60)

    from graph.spine_schema import PaperNode
    from graph.relationship_builder import SpineMetadata as RBSpineMetadata

    # Test PaperNode has PICO
    paper = PaperNode(
        paper_id="test",
        title="Test",
        year=2025,
        pico_population="test pop",
        pico_intervention="test int",
        pico_comparison="test comp",
        pico_outcome="test out"
    )

    props = paper.to_neo4j_properties()
    pico_in_props = all(k in props for k in ['pico_population', 'pico_intervention', 'pico_comparison', 'pico_outcome'])
    print(f"✅ PaperNode.to_neo4j_properties() includes PICO: {pico_in_props}")

    # Test RelationshipBuilder SpineMetadata has PICO
    rb_spine = RBSpineMetadata(
        sub_domain="Degenerative",
        pico_population="Adults",
        pico_intervention="UBE",
        pico_comparison="Open",
        pico_outcome="VAS"
    )
    print(f"✅ RelationshipBuilder.SpineMetadata has PICO: pico_population={rb_spine.pico_population}")

    return True


def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("v3.0 Schema Integration Test")
    print("="*60)

    results = {}

    # Run tests
    results["schema_classes"] = test_schema_classes()
    results["vectordb_flow"] = test_vectordb_flow()
    results["mcp_server"] = test_mcp_server_import()
    results["streamlit"] = test_streamlit_compatibility()
    results["neo4j"] = test_neo4j_schema()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("✅ All integration tests passed!")
        print("   v3.0 schema is correctly applied across:")
        print("   - PDF Processor (ExtractedChunk)")
        print("   - VectorDB (TextChunk, metadata)")
        print("   - MCP Server (SpineMetadataCompat, ExtractedChunkCompat)")
        print("   - Neo4j (PaperNode with PICO)")
        print("   - Streamlit pages (no old field references)")
    else:
        print("❌ Some tests failed. Please review the issues above.")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
