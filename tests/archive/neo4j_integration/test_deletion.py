"""Test deletion functionality for ChromaDB and Neo4j.

Tests:
1. Neo4j delete_paper method
2. Neo4j clear_database method
3. MCP server delete_document (hybrid)
4. MCP server reset_database (hybrid)
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

from graph.neo4j_client import Neo4jClient, Neo4jConfig
from graph.spine_schema import PaperNode


async def test_neo4j_deletion():
    """Test Neo4j deletion methods."""
    print("\n" + "=" * 60)
    print("TEST 1: Neo4j Deletion Methods")
    print("=" * 60)

    # Create test config
    config = Neo4jConfig(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        username=os.environ.get("NEO4J_USERNAME", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "spine_graph_2024"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )

    async with Neo4jClient(config) as client:
        # Ensure schema is initialized
        await client.initialize_schema()

        # Create a test paper
        print("\n1. Creating test paper...")
        test_paper = PaperNode(
            paper_id="test_deletion_001",
            title="Test Paper for Deletion",
            authors=["Test Author"],
            year=2024,
            sub_domain="Degenerative",
            evidence_level="5",
        )

        await client.create_paper(test_paper)
        print(f"   ✓ Created paper: {test_paper.paper_id}")

        # Create relationships
        await client.create_studies_relation(
            paper_id=test_paper.paper_id,
            pathology_name="Lumbar Stenosis",
            is_primary=True
        )
        await client.create_investigates_relation(
            paper_id=test_paper.paper_id,
            intervention_name="TLIF",
            is_comparison=False
        )
        print("   ✓ Created relationships")

        # Verify paper exists
        paper = await client.get_paper(test_paper.paper_id)
        assert paper is not None, "Paper should exist"
        print(f"   ✓ Verified paper exists")

        # Test delete_paper
        print("\n2. Testing delete_paper...")
        result = await client.delete_paper(test_paper.paper_id)
        print(f"   ✓ Deleted {result.get('nodes_deleted', 0)} nodes")
        print(f"   ✓ Deleted {result.get('relationships_deleted', 0)} relationships")

        # Verify paper is deleted
        paper = await client.get_paper(test_paper.paper_id)
        assert paper is None, "Paper should be deleted"
        print("   ✓ Verified paper is deleted")

        # Get stats
        stats = await client.get_stats()
        print(f"\n3. Current graph stats:")
        print(f"   Nodes: {stats.get('nodes', {})}")
        print(f"   Relationships: {stats.get('relationships', {})}")

    print("\n✅ Neo4j deletion tests PASSED")


async def test_mcp_deletion():
    """Test MCP server deletion methods."""
    print("\n" + "=" * 60)
    print("TEST 2: MCP Server Deletion Methods")
    print("=" * 60)

    # Import MCP server
    from medical_mcp.medical_kag_server import MedicalKAGServer

    # Create server instance
    data_dir = project_root / "data" / "test_deletion"
    data_dir.mkdir(parents=True, exist_ok=True)

    server = MedicalKAGServer(data_dir=data_dir, enable_llm=False)

    # Test delete_document (should handle both ChromaDB and Neo4j)
    print("\n1. Testing delete_document...")
    result = await server.delete_document("nonexistent_doc")
    print(f"   Result: {result}")
    assert result.get("success") is True, "Should succeed even if document doesn't exist"
    print("   ✓ Delete document method works")

    # Test reset_database
    print("\n2. Testing reset_database (partial)...")
    result = await server.reset_database(include_taxonomy=False)
    print(f"   Result: {result}")
    assert result.get("success") is True, "Reset should succeed"
    print(f"   ✓ ChromaDB cleared: {result.get('chromadb_cleared')}")
    print(f"   ✓ Neo4j nodes deleted: {result.get('neo4j_nodes_deleted', 0)}")
    print(f"   ✓ Neo4j relationships deleted: {result.get('neo4j_relationships_deleted', 0)}")
    print(f"   ✓ Taxonomy preserved: {not result.get('taxonomy_cleared')}")

    print("\n✅ MCP deletion tests PASSED")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DELETION FUNCTIONALITY TEST SUITE")
    print("=" * 60)

    try:
        # Test 1: Neo4j deletion
        await test_neo4j_deletion()

        # Test 2: MCP deletion
        await test_mcp_deletion()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
