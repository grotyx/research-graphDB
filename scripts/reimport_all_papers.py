#!/usr/bin/env python3
"""
Reimport all extracted JSON papers to Neo4j with fixed SpineMetadata mapping.

v1.14.10: Fixes field mapping issues:
- pathology -> pathologies
- anatomy_level + anatomy_region -> anatomy_levels
- ExtractedOutcome objects -> dict

Usage:
    PYTHONPATH=./src python3 scripts/reimport_all_papers.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def reimport_all_papers():
    """Reimport all extracted JSON files to Neo4j."""

    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    from graph.relationship_builder import RelationshipBuilder, SpineMetadata
    from graph.entity_normalizer import EntityNormalizer

    # Configuration
    config = Neo4jConfig(
        uri=os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        username=os.getenv('NEO4J_USERNAME', 'neo4j'),
        password=os.getenv('NEO4J_PASSWORD', 'spineGraph2024'),
        database=os.getenv('NEO4J_DATABASE', 'neo4j')
    )

    neo4j_client = Neo4jClient(config=config)
    normalizer = EntityNormalizer()
    builder = RelationshipBuilder(neo4j_client, normalizer)

    # Find all extracted JSON files
    extracted_dir = Path(__file__).parent.parent / "data" / "extracted"
    json_files = list(extracted_dir.glob("*.json"))

    print(f"Found {len(json_files)} JSON files to process")
    print("=" * 60)

    success_count = 0
    error_count = 0
    skipped_count = 0

    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            meta = data.get('metadata', {})
            spine = data.get('spine_metadata', {})

            # Skip if no interventions or outcomes
            if not spine.get('interventions') and not spine.get('outcomes'):
                print(f"SKIP: {json_path.name} (no interventions/outcomes)")
                skipped_count += 1
                continue

            # Get paper_id from metadata or filename
            paper_id = meta.get('pmid')
            if paper_id:
                paper_id = f"pubmed_{paper_id}"
            else:
                paper_id = json_path.stem

            print(f"\nProcessing: {json_path.name}")
            print(f"  Paper ID: {paper_id}")
            print(f"  Interventions: {spine.get('interventions', [])}")
            print(f"  Outcomes: {len(spine.get('outcomes', []))}")

            # Convert outcomes from JSON to proper format
            outcomes = []
            for o in spine.get('outcomes', []):
                if isinstance(o, dict):
                    outcomes.append({
                        'name': o.get('name', ''),
                        'value': o.get('value', ''),
                        'value_intervention': o.get('value_intervention', ''),
                        'value_control': o.get('value_control', ''),
                        'p_value': o.get('p_value', ''),
                        'effect_size': o.get('effect_size', ''),
                        'confidence_interval': o.get('confidence_interval', ''),
                        'is_significant': o.get('is_significant', False),
                        'direction': o.get('direction', ''),
                        'category': o.get('category', ''),
                        'timepoint': o.get('timepoint', ''),
                    })

            # pathology -> pathologies mapping
            pathologies = spine.get('pathologies') or spine.get('pathology', [])
            if isinstance(pathologies, str):
                pathologies = [pathologies] if pathologies else []

            # anatomy_level + anatomy_region -> anatomy_levels mapping
            anatomy_levels = spine.get('anatomy_levels', [])
            if not anatomy_levels:
                anatomy_level = spine.get('anatomy_level', '')
                anatomy_region = spine.get('anatomy_region', '')
                anatomy_levels = []
                if anatomy_level:
                    anatomy_levels.append(anatomy_level)
                if anatomy_region and anatomy_region != anatomy_level:
                    anatomy_levels.append(anatomy_region)

            # Create SpineMetadata
            spine_meta = SpineMetadata(
                sub_domain=spine.get('sub_domain', 'Unknown'),
                sub_domains=spine.get('sub_domains', []),
                anatomy_levels=anatomy_levels,
                interventions=spine.get('interventions', []),
                pathologies=pathologies,
                outcomes=outcomes,
                surgical_approach=spine.get('surgical_approach', []),
                main_conclusion=spine.get('main_conclusion', ''),
                # v1.2 Extended entities
                costs=spine.get('costs', []),
                patient_cohorts=spine.get('patient_cohorts', []),
                followups=spine.get('followups', []),
                quality_metrics=spine.get('quality_metrics', []),
            )

            # Create mock metadata object
            class MockMeta:
                def __init__(self, data, spine_meta):
                    self.title = data.get('title', '')
                    self.authors = data.get('authors', [])
                    self.year = data.get('year', 0)
                    self.journal = data.get('journal', '')
                    self.doi = data.get('doi', '')
                    self.pmid = data.get('pmid', '')
                    self.evidence_level = data.get('evidence_level', '5')
                    self.abstract = data.get('abstract', '')
                    self.spine = spine_meta

            mock_meta = MockMeta(meta, spine_meta)

            # Delete existing relationships (keep Paper node)
            async with neo4j_client.session() as session:
                await session.run("""
                    MATCH (p:Paper {paper_id: $pid})-[r:INVESTIGATES|STUDIES]->()
                    DELETE r
                """, pid=paper_id)

            # Rebuild relationships
            result = await builder.build_from_paper(
                paper_id=paper_id,
                metadata=mock_meta,
                spine_metadata=spine_meta,
                chunks=[],
                owner='system',
                shared=True
            )

            print(f"  Result: {result.nodes_created} nodes, {result.relationships_created} relationships")
            success_count += 1

        except Exception as e:
            print(f"ERROR: {json_path.name} - {e}")
            error_count += 1

    await neo4j_client.close()

    print("\n" + "=" * 60)
    print(f"Reimport completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(json_files)}")


if __name__ == "__main__":
    asyncio.run(reimport_all_papers())
