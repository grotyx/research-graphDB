#!/usr/bin/env python3
"""Reindex Paper-Entity Relationships from Extracted JSON Files.

This script reads extracted JSON files from data/extracted/ and rebuilds
all Paper-Entity relationships in Neo4j:
- Paper → Pathology (STUDIES)
- Paper → Intervention (INVESTIGATES)
- Paper → Anatomy (INVOLVES)
- Intervention → Outcome (AFFECTS)

Usage:
    python scripts/reindex_relationships.py [--dry-run] [--limit N] [--paper-id ID]

Options:
    --dry-run       Show what would be done without making changes
    --limit N       Process only first N papers
    --paper-id ID   Process specific paper only
    --force         Rebuild even if relationships exist
"""

import asyncio
import json
import os
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from graph.neo4j_client import Neo4jClient
from graph.relationship_builder import RelationshipBuilder, SpineMetadata, ExtractedOutcome
from graph.entity_normalizer import EntityNormalizer


@dataclass
class ReindexStats:
    """Reindexing statistics."""
    total_papers: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0

    studies_created: int = 0
    investigates_created: int = 0
    involves_created: int = 0
    affects_created: int = 0

    def __str__(self) -> str:
        return f"""
=== Reindex Statistics ===
Papers: {self.processed}/{self.total_papers} processed, {self.skipped} skipped, {self.errors} errors

Relationships Created:
  - STUDIES (Paper→Pathology): {self.studies_created}
  - INVESTIGATES (Paper→Intervention): {self.investigates_created}
  - INVOLVES (Paper→Anatomy): {self.involves_created}
  - AFFECTS (Intervention→Outcome): {self.affects_created}

Total Relationships: {self.studies_created + self.investigates_created + self.involves_created + self.affects_created}
"""


def convert_to_extracted_outcome(outcome_dict: dict) -> ExtractedOutcome:
    """Convert outcome dict to ExtractedOutcome dataclass."""
    return ExtractedOutcome(
        name=outcome_dict.get('name', ''),
        category=outcome_dict.get('category', ''),
        baseline=outcome_dict.get('baseline', ''),
        final=outcome_dict.get('final', ''),
        value=outcome_dict.get('value', ''),
        value_intervention=outcome_dict.get('value_intervention', ''),
        value_control=outcome_dict.get('value_control', ''),
        value_difference=outcome_dict.get('value_difference', ''),
        p_value=outcome_dict.get('p_value', ''),
        effect_size=outcome_dict.get('effect_size', ''),
        confidence_interval=outcome_dict.get('confidence_interval', ''),
        is_significant=outcome_dict.get('is_significant', False),
        direction=outcome_dict.get('direction', ''),
        timepoint=outcome_dict.get('timepoint', ''),
    )


def parse_json_to_graph_metadata(data: dict) -> tuple[str, SpineMetadata, dict]:
    """Parse extracted JSON to SpineMetadata.

    Returns:
        Tuple of (paper_id, SpineMetadata, paper_metadata)
    """
    metadata = data.get('metadata', {})
    spine_meta = data.get('spine_metadata', {})

    # Get paper_id
    paper_id = metadata.get('paper_id', '')
    if not paper_id:
        # Try to construct from PMID or DOI
        pmid = metadata.get('pmid', '')
        doi = metadata.get('doi', '')
        if pmid:
            paper_id = f"pubmed_{pmid}"
        elif doi:
            paper_id = f"doi_{doi.replace('/', '_')}"

    # Parse pathologies (handle both 'pathology' and 'pathologies')
    pathologies = spine_meta.get('pathologies', [])
    if not pathologies:
        pathology = spine_meta.get('pathology', [])
        if isinstance(pathology, str):
            pathologies = [pathology] if pathology else []
        elif isinstance(pathology, list):
            pathologies = pathology

    # Parse anatomy levels
    anatomy_levels = spine_meta.get('anatomy_levels', [])
    if not anatomy_levels:
        anatomy_level = spine_meta.get('anatomy_level', '')
        anatomy_region = spine_meta.get('anatomy_region', '')
        if anatomy_level:
            anatomy_levels.append(anatomy_level)
        if anatomy_region and anatomy_region != anatomy_level:
            anatomy_levels.append(anatomy_region)

    # Parse interventions
    interventions = spine_meta.get('interventions', [])
    if isinstance(interventions, str):
        interventions = [interventions] if interventions else []

    # Parse outcomes
    outcomes_raw = spine_meta.get('outcomes', [])
    outcomes = []
    for o in outcomes_raw:
        if isinstance(o, dict) and o.get('name'):
            outcomes.append(o)

    # Parse complications (can also create relationships)
    complications = spine_meta.get('complications', [])

    # Create SpineMetadata
    graph_meta = SpineMetadata(
        sub_domain=spine_meta.get('sub_domain', 'Unknown'),
        sub_domains=spine_meta.get('sub_domains', []),
        anatomy_levels=anatomy_levels,
        interventions=interventions,
        pathologies=pathologies,
        outcomes=outcomes,
        surgical_approach=spine_meta.get('surgical_approach', []),
        main_conclusion=spine_meta.get('main_conclusion', ''),
        patient_cohorts=spine_meta.get('patient_cohorts', []),
        followups=spine_meta.get('followups', []),
        costs=spine_meta.get('costs', []),
        quality_metrics=spine_meta.get('quality_metrics', []),
    )

    return paper_id, graph_meta, metadata


async def check_paper_exists(client: Neo4jClient, paper_id: str) -> bool:
    """Check if paper exists in Neo4j."""
    result = await client.run_query(
        "MATCH (p:Paper {paper_id: $paper_id}) RETURN p.paper_id",
        {"paper_id": paper_id}
    )
    return len(result) > 0


async def get_existing_relationship_count(client: Neo4jClient, paper_id: str) -> dict:
    """Get count of existing relationships for a paper."""
    result = await client.run_query("""
        MATCH (p:Paper {paper_id: $paper_id})
        OPTIONAL MATCH (p)-[s:STUDIES]->()
        OPTIONAL MATCH (p)-[inv:INVESTIGATES]->()
        OPTIONAL MATCH (p)-[i:INVOLVES]->()
        RETURN
            count(DISTINCT s) as studies,
            count(DISTINCT inv) as investigates,
            count(DISTINCT i) as involves
    """, {"paper_id": paper_id})

    if result:
        return {
            'studies': result[0]['studies'],
            'investigates': result[0]['investigates'],
            'involves': result[0]['involves']
        }
    return {'studies': 0, 'investigates': 0, 'involves': 0}


async def create_paper_if_not_exists(client: Neo4jClient, paper_id: str, metadata: dict) -> bool:
    """Create Paper node if it doesn't exist."""
    exists = await check_paper_exists(client, paper_id)
    if exists:
        return False

    # Create paper node - only set non-empty DOI to avoid constraint violations
    doi = metadata.get('doi', '')
    # Skip invalid DOI values that would cause constraint violations
    if doi and doi.lower() in ['not provided', 'not provided in text', 'not specified',
                                'not specified in provided text', 'unknown', 'not provided in excerpt', '']:
        doi = None  # Don't set DOI if it's a placeholder value

    await client.run_query("""
        MERGE (p:Paper {paper_id: $paper_id})
        SET p.title = $title,
            p.year = $year,
            p.journal = $journal,
            p.pmid = $pmid,
            p.evidence_level = $evidence_level,
            p.created_at = datetime()
    """ + (" SET p.doi = $doi" if doi else ""), {
        "paper_id": paper_id,
        "title": metadata.get('title', ''),
        "year": metadata.get('year', 0),
        "journal": metadata.get('journal', ''),
        "pmid": metadata.get('pmid', ''),
        "doi": doi,
        "evidence_level": metadata.get('evidence_level', ''),
    })
    return True


async def reindex_paper(
    client: Neo4jClient,
    builder: RelationshipBuilder,
    paper_id: str,
    graph_meta: SpineMetadata,
    metadata: dict,
    dry_run: bool = False,
    force: bool = False
) -> dict:
    """Reindex relationships for a single paper.

    Returns:
        Dict with counts of created relationships
    """
    result = {
        'studies': 0,
        'investigates': 0,
        'involves': 0,
        'affects': 0,
        'skipped': False,
        'error': None
    }

    try:
        # Check if paper exists, create if not
        if not await check_paper_exists(client, paper_id):
            if dry_run:
                print(f"  [DRY-RUN] Would create Paper node: {paper_id}")
            else:
                await create_paper_if_not_exists(client, paper_id, metadata)

        # Check existing relationships
        if not force:
            existing = await get_existing_relationship_count(client, paper_id)
            if existing['studies'] > 0 or existing['investigates'] > 0 or existing['involves'] > 0:
                result['skipped'] = True
                return result

        # Create STUDIES relationships (Paper → Pathology)
        if graph_meta.pathologies:
            if dry_run:
                print(f"  [DRY-RUN] Would create STUDIES: {graph_meta.pathologies}")
                result['studies'] = len(graph_meta.pathologies)
            else:
                count = await builder.create_studies_relations(paper_id, graph_meta.pathologies)
                result['studies'] = count

        # Create INVESTIGATES relationships (Paper → Intervention)
        if graph_meta.interventions:
            if dry_run:
                print(f"  [DRY-RUN] Would create INVESTIGATES: {graph_meta.interventions}")
                result['investigates'] = len(graph_meta.interventions)
            else:
                count = await builder.create_investigates_relations(paper_id, graph_meta.interventions)
                result['investigates'] = count

        # Create INVOLVES relationships (Paper → Anatomy)
        if graph_meta.anatomy_levels:
            if dry_run:
                print(f"  [DRY-RUN] Would create INVOLVES: {graph_meta.anatomy_levels}")
                result['involves'] = len(graph_meta.anatomy_levels)
            else:
                count = await builder.create_involves_relations(paper_id, graph_meta.anatomy_levels)
                result['involves'] = count

        # Create AFFECTS relationships (Intervention → Outcome)
        if graph_meta.interventions and graph_meta.outcomes:
            outcomes = [convert_to_extracted_outcome(o) for o in graph_meta.outcomes if o.get('name')]

            if outcomes:
                for intervention in graph_meta.interventions:
                    if dry_run:
                        print(f"  [DRY-RUN] Would create AFFECTS: {intervention} → {[o.name for o in outcomes]}")
                        result['affects'] += len(outcomes)
                    else:
                        count = await builder.create_affects_relations(intervention, outcomes, paper_id)
                        result['affects'] += count

    except Exception as e:
        result['error'] = str(e)

    return result


async def main():
    parser = argparse.ArgumentParser(description='Reindex Paper-Entity relationships')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--limit', type=int, default=0, help='Process only first N papers')
    parser.add_argument('--paper-id', type=str, help='Process specific paper ID')
    parser.add_argument('--force', action='store_true', help='Rebuild even if relationships exist')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    # Setup paths
    extracted_dir = Path(__file__).parent.parent / "data" / "extracted"
    if not extracted_dir.exists():
        print(f"Error: {extracted_dir} does not exist")
        sys.exit(1)

    # Get JSON files
    json_files = sorted(extracted_dir.glob("*.json"))
    if args.limit > 0:
        json_files = json_files[:args.limit]

    stats = ReindexStats(total_papers=len(json_files))

    print(f"Found {len(json_files)} JSON files in {extracted_dir}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Force rebuild: {args.force}")
    print()

    # Initialize Neo4j client
    client = Neo4jClient()

    try:
        if not args.dry_run:
            await client.connect()
            print("Connected to Neo4j")

        # Initialize relationship builder
        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer)

        # Process each JSON file
        for i, json_file in enumerate(json_files, 1):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                paper_id, graph_meta, metadata = parse_json_to_graph_metadata(data)

                if not paper_id:
                    paper_id = json_file.stem  # Use filename as fallback

                # Filter by paper_id if specified
                if args.paper_id and paper_id != args.paper_id:
                    continue

                if args.verbose or args.dry_run:
                    print(f"[{i}/{len(json_files)}] Processing: {paper_id}")
                    print(f"  Pathologies: {graph_meta.pathologies}")
                    print(f"  Interventions: {graph_meta.interventions}")
                    print(f"  Anatomy: {graph_meta.anatomy_levels}")
                    print(f"  Outcomes: {len(graph_meta.outcomes)}")

                # Reindex
                result = await reindex_paper(
                    client, builder, paper_id, graph_meta, metadata,
                    dry_run=args.dry_run, force=args.force
                )

                if result.get('error'):
                    stats.errors += 1
                    print(f"  ERROR: {result['error']}")
                elif result.get('skipped'):
                    stats.skipped += 1
                    if args.verbose:
                        print(f"  Skipped (already has relationships)")
                else:
                    stats.processed += 1
                    stats.studies_created += result['studies']
                    stats.investigates_created += result['investigates']
                    stats.involves_created += result['involves']
                    stats.affects_created += result['affects']

                    if args.verbose:
                        print(f"  Created: STUDIES={result['studies']}, INVESTIGATES={result['investigates']}, "
                              f"INVOLVES={result['involves']}, AFFECTS={result['affects']}")

            except json.JSONDecodeError as e:
                stats.errors += 1
                print(f"  JSON Error in {json_file.name}: {e}")
            except Exception as e:
                stats.errors += 1
                print(f"  Error processing {json_file.name}: {e}")

        print(stats)

    finally:
        if not args.dry_run:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
