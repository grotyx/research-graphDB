#!/usr/bin/env python3
"""Pilot Test Script for Phase 1.2-1.3.

Tests Neo4j graph creation with 5 sample papers covering all sub-domains:
- Degenerative
- Deformity
- Trauma
- Tumor
- Basic Science

Validates:
1. Paper node creation
2. STUDIES relationship (Paper → Pathology)
3. INVESTIGATES relationship (Paper → Intervention)
4. AFFECTS relationship (Intervention → Outcome with statistics)
5. Basic Cypher queries
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.graph.neo4j_client import Neo4jClient
from src.graph.relationship_builder import RelationshipBuilder, SpineMetadata, ExtractedOutcome
from src.graph.entity_normalizer import EntityNormalizer
from src.builder.gemini_vision_processor import ExtractedMetadata, ExtractedChunk, StatisticsData


def load_test_papers(json_path: str) -> list[dict]:
    """Load test paper data from JSON file.

    Args:
        json_path: Path to test_papers.json

    Returns:
        List of paper dictionaries
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_papers"]


def create_metadata_from_paper(paper: dict) -> ExtractedMetadata:
    """Create ExtractedMetadata from paper dict.

    Args:
        paper: Paper dictionary from JSON

    Returns:
        ExtractedMetadata object
    """
    return ExtractedMetadata(
        title=paper["title"],
        authors=paper["authors"],
        year=paper["year"],
        journal=paper["journal"],
        doi=paper["doi"],
        
        study_type=paper["study_design"],
        evidence_level=paper["evidence_level"],
        abstract=paper["abstract"],
    )


def create_spine_metadata_from_paper(paper: dict) -> SpineMetadata:
    """Create SpineMetadata from paper dict.

    Args:
        paper: Paper dictionary from JSON

    Returns:
        SpineMetadata object
    """
    meta = paper["metadata"]

    # Convert outcomes dict to ExtractedOutcome list
    outcomes = []
    for outcome_dict in meta.get("outcomes", []):
        outcomes.append({
            "name": outcome_dict["name"],
            "value": outcome_dict.get("value_intervention", ""),
            "value_control": outcome_dict.get("value_control", ""),
            "p_value": outcome_dict.get("p_value"),
            "effect_size": outcome_dict.get("effect_size", ""),
            "confidence_interval": outcome_dict.get("confidence_interval", ""),
            "is_significant": outcome_dict.get("is_significant", False),
            "direction": outcome_dict.get("direction", ""),
        })

    return SpineMetadata(
        sub_domain=paper["sub_domain"],
        anatomy_levels=meta.get("anatomy_levels", []),
        pathologies=meta.get("pathologies", []),
        interventions=meta.get("interventions", []),
        outcomes=outcomes,
    )


def create_chunks_from_paper(paper: dict) -> list[ExtractedChunk]:
    """Create minimal chunks for AFFECTS relationship.

    Args:
        paper: Paper dictionary from JSON

    Returns:
        List of ExtractedChunk objects
    """
    chunks = []

    # Create results chunk with statistics
    meta = paper["metadata"]
    if meta.get("outcomes"):
        p_values = [
            f"p={o.get('p_value', '')}" if o.get('p_value') else ""
            for o in meta["outcomes"]
            if o.get('p_value')
        ]

        chunks.append(ExtractedChunk(
            content=paper["abstract"],  # Use abstract as content
            section_type="results",
            tier="tier1",
            is_key_finding=True,
            keywords=meta.get("interventions", []) + [o["name"] for o in meta["outcomes"]],
            statistics=StatisticsData(p_values=p_values) if p_values else None,
        ))

    return chunks


async def test_paper_creation(client: Neo4jClient, builder: RelationshipBuilder, paper: dict):
    """Test creating a single paper and all relationships.

    Args:
        client: Neo4jClient instance
        builder: RelationshipBuilder instance
        paper: Paper dictionary

    Returns:
        BuildResult
    """
    print(f"\n{'='*80}")
    print(f"Testing Paper: {paper['paper_id']}")
    print(f"Title: {paper['title']}")
    print(f"Sub-domain: {paper['sub_domain']}")
    print(f"Evidence Level: {paper['evidence_level']}")
    print(f"{'='*80}")

    # Create metadata
    metadata = create_metadata_from_paper(paper)
    spine_metadata = create_spine_metadata_from_paper(paper)
    chunks = create_chunks_from_paper(paper)

    # Build graph
    result = await builder.build_from_paper(
        paper_id=paper["paper_id"],
        metadata=metadata,
        spine_metadata=spine_metadata,
        chunks=chunks,
    )

    print(f"\nBuild Result:")
    print(f"  Nodes created: {result.nodes_created}")
    print(f"  Relationships created: {result.relationships_created}")

    if result.warnings:
        print(f"  Warnings: {result.warnings}")
    if result.errors:
        print(f"  Errors: {result.errors}")

    return result


async def verify_paper_stored(client: Neo4jClient, paper_id: str):
    """Verify paper was stored correctly.

    Args:
        client: Neo4jClient instance
        paper_id: Paper ID to verify
    """
    print(f"\nVerifying paper: {paper_id}")

    # Get paper
    paper_data = await client.get_paper(paper_id)
    if paper_data:
        print(f"  ✓ Paper found: {paper_data.get('p', {}).get('title', 'N/A')}")
    else:
        print(f"  ✗ Paper not found")
        return

    # Get relationships
    relations = await client.get_paper_relations(paper_id)
    print(f"  ✓ Relationships: {len(relations)}")


async def run_sample_queries(client: Neo4jClient):
    """Run sample Cypher queries to test functionality.

    Args:
        client: Neo4jClient instance
    """
    print(f"\n{'='*80}")
    print("Running Sample Queries")
    print(f"{'='*80}")

    # 1. Count papers by sub-domain
    print("\n1. Papers by Sub-domain:")
    query = """
    MATCH (p:Paper)
    RETURN p.sub_domain as domain, count(p) as count
    ORDER BY count DESC
    """
    results = await client.run_query(query)
    for r in results:
        print(f"  {r['domain']}: {r['count']}")

    # 2. Find papers studying specific pathology
    print("\n2. Papers studying Lumbar Stenosis:")
    query = """
    MATCH (p:Paper)-[:STUDIES]->(path:Pathology {name: 'Lumbar Stenosis'})
    RETURN p.paper_id as paper_id, p.title as title
    """
    results = await client.run_query(query)
    for r in results:
        print(f"  {r['paper_id']}: {r['title'][:60]}...")

    # 3. Find interventions with significant VAS improvement
    print("\n3. Interventions with significant VAS improvement:")
    query = """
    MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: 'VAS'})
    WHERE a.is_significant = true AND a.direction = 'improved'
    RETURN i.name as intervention, a.value as value, a.p_value as p_value,
           a.source_paper_id as source
    ORDER BY a.p_value ASC
    """
    results = await client.run_query(query)
    for r in results:
        print(f"  {r['intervention']}: VAS={r['value']}, p={r['p_value']:.4f} (from {r['source']})")

    # 4. Get intervention hierarchy for TLIF
    print("\n4. Intervention hierarchy for TLIF:")
    hierarchy = await client.get_intervention_hierarchy("TLIF")
    if hierarchy:
        for h in hierarchy:
            print(f"  TLIF is a type of: {h}")

    # 5. Search effective interventions for Fusion Rate
    print("\n5. Effective interventions for Fusion Rate:")
    effective = await client.search_effective_interventions("Fusion Rate")
    for e in effective:
        print(f"  {e.get('intervention')}: {e.get('value')} (p={e.get('p_value'):.4f})")

    # 6. Find conflicting results
    print("\n6. Conflicting results (if any):")
    query = """
    MATCH (i:Intervention)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i:Intervention)
    WHERE a1.direction <> a2.direction
      AND a1.is_significant = true AND a2.is_significant = true
      AND a1.source_paper_id <> a2.source_paper_id
    RETURN i.name as intervention, o.name as outcome,
           a1.direction as dir1, a2.direction as dir2,
           a1.source_paper_id as paper1, a2.source_paper_id as paper2
    LIMIT 5
    """
    results = await client.run_query(query)
    if results:
        for r in results:
            print(f"  {r['intervention']} → {r['outcome']}: {r['dir1']} vs {r['dir2']}")
            print(f"    Papers: {r['paper1']} vs {r['paper2']}")
    else:
        print("  No conflicts detected")


async def get_graph_stats(client: Neo4jClient):
    """Get and print graph statistics.

    Args:
        client: Neo4jClient instance
    """
    print(f"\n{'='*80}")
    print("Graph Statistics")
    print(f"{'='*80}")

    stats = await client.get_stats()

    print("\nNodes:")
    for label, count in stats.get("nodes", {}).items():
        print(f"  {label}: {count}")

    print("\nRelationships:")
    for rel_type, count in stats.get("relationships", {}).items():
        print(f"  {rel_type}: {count}")


async def main():
    """Main pilot test function."""
    print("="*80)
    print("Spine GraphRAG Pilot Test - Phase 1.2-1.3")
    print("="*80)

    # Load test papers
    test_data_path = project_root / "tests" / "data" / "test_papers.json"
    print(f"\nLoading test papers from: {test_data_path}")
    papers = load_test_papers(str(test_data_path))
    print(f"Loaded {len(papers)} test papers")

    # Initialize Neo4j client
    print("\nInitializing Neo4j client...")
    async with Neo4jClient() as client:
        # Initialize schema
        print("Initializing schema (constraints, indexes, taxonomy)...")
        await client.initialize_schema()
        print("  ✓ Schema initialized")

        # Initialize components
        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer)

        # Process each paper
        print(f"\n{'='*80}")
        print("Processing Test Papers")
        print(f"{'='*80}")

        results = []
        for paper in papers:
            result = await test_paper_creation(client, builder, paper)
            results.append(result)
            await verify_paper_stored(client, paper["paper_id"])

        # Summary
        print(f"\n{'='*80}")
        print("Processing Summary")
        print(f"{'='*80}")
        total_nodes = sum(r.nodes_created for r in results)
        total_rels = sum(r.relationships_created for r in results)
        total_errors = sum(len(r.errors) for r in results)
        total_warnings = sum(len(r.warnings) for r in results)

        print(f"\nTotal nodes created: {total_nodes}")
        print(f"Total relationships created: {total_rels}")
        print(f"Total errors: {total_errors}")
        print(f"Total warnings: {total_warnings}")

        # Run sample queries
        await run_sample_queries(client)

        # Get graph statistics
        await get_graph_stats(client)

        print(f"\n{'='*80}")
        print("Pilot Test Complete!")
        print(f"{'='*80}")
        print("\nNext Steps:")
        print("1. Review Neo4j Browser: http://localhost:7474")
        print("2. Run Cypher queries to explore the graph")
        print("3. Test more complex queries and relationships")
        print("4. Proceed to Phase 2: Core Development")


if __name__ == "__main__":
    asyncio.run(main())
