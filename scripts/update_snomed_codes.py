#!/usr/bin/env python3
"""Update SNOMED codes for existing Intervention nodes in Neo4j.

This script uses EntityNormalizer to look up SNOMED codes from
spine_snomed_mappings.py and updates all Intervention nodes in Neo4j.

Usage:
    python scripts/update_snomed_codes.py

    # Dry run (show what would be updated)
    python scripts/update_snomed_codes.py --dry-run
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient
from graph.entity_normalizer import EntityNormalizer


async def get_interventions_without_snomed(client: Neo4jClient) -> list[dict]:
    """Get all Intervention nodes without SNOMED codes."""
    query = """
    MATCH (i:Intervention)
    WHERE i.snomed_code IS NULL OR i.snomed_code = ''
    RETURN i.name as name, i.category as category
    ORDER BY i.name
    """
    return await client.run_query(query)


async def get_all_interventions(client: Neo4jClient) -> list[dict]:
    """Get all Intervention nodes."""
    query = """
    MATCH (i:Intervention)
    RETURN i.name as name, i.category as category,
           i.snomed_code as snomed_code, i.snomed_term as snomed_term
    ORDER BY i.name
    """
    return await client.run_query(query)


async def update_intervention_snomed(
    client: Neo4jClient,
    name: str,
    snomed_code: str,
    snomed_term: str,
    category: str = None
) -> bool:
    """Update SNOMED code for a single Intervention node."""
    query = """
    MATCH (i:Intervention {name: $name})
    SET i.snomed_code = $snomed_code,
        i.snomed_term = $snomed_term
    """
    params = {
        "name": name,
        "snomed_code": snomed_code,
        "snomed_term": snomed_term
    }

    # Optionally update category if provided
    if category:
        query = """
        MATCH (i:Intervention {name: $name})
        SET i.snomed_code = $snomed_code,
            i.snomed_term = $snomed_term,
            i.category = COALESCE(i.category, $category)
        """
        params["category"] = category

    query += " RETURN i.name as name"

    try:
        result = await client.run_write_query(query, params)
        return len(result) > 0
    except Exception as e:
        print(f"  ❌ Error updating {name}: {e}")
        return False


async def main(dry_run: bool = False):
    """Main function to update SNOMED codes."""
    print("=" * 60)
    print("SNOMED-CT Code Update Script")
    print("=" * 60)

    # Initialize components
    normalizer = EntityNormalizer()

    async with Neo4jClient() as client:
        # Get current statistics
        all_interventions = await get_all_interventions(client)
        without_snomed = await get_interventions_without_snomed(client)

        total = len(all_interventions)
        with_snomed = total - len(without_snomed)

        print(f"\n📊 Current Statistics:")
        print(f"   Total Interventions: {total}")
        print(f"   With SNOMED code: {with_snomed} ({with_snomed/total*100:.1f}%)")
        print(f"   Without SNOMED code: {len(without_snomed)} ({len(without_snomed)/total*100:.1f}%)")

        if not without_snomed:
            print("\n✅ All interventions already have SNOMED codes!")
            return

        # Process each intervention without SNOMED
        print(f"\n🔍 Looking up SNOMED codes for {len(without_snomed)} interventions...")
        print("-" * 60)

        updated = 0
        not_found = 0

        for item in without_snomed:
            name = item["name"]

            # Normalize and get SNOMED
            norm_result = normalizer.normalize_intervention(name)

            if norm_result.snomed_code:
                print(f"  ✅ {name}")
                print(f"     → Normalized: {norm_result.normalized}")
                print(f"     → SNOMED: {norm_result.snomed_code} ({norm_result.snomed_term})")

                if not dry_run:
                    success = await update_intervention_snomed(
                        client,
                        name,
                        norm_result.snomed_code,
                        norm_result.snomed_term,
                        norm_result.category
                    )
                    if success:
                        updated += 1
                else:
                    updated += 1
            else:
                print(f"  ⚠️  {name} - No SNOMED mapping found")
                not_found += 1

        # Summary
        print("\n" + "=" * 60)
        print("📈 Summary:")
        if dry_run:
            print(f"   Would update: {updated}")
        else:
            print(f"   Updated: {updated}")
        print(f"   No mapping found: {not_found}")

        # Final statistics
        if not dry_run:
            all_interventions = await get_all_interventions(client)
            without_snomed = await get_interventions_without_snomed(client)

            total = len(all_interventions)
            with_snomed = total - len(without_snomed)

            print(f"\n📊 New Statistics:")
            print(f"   Total Interventions: {total}")
            print(f"   With SNOMED code: {with_snomed} ({with_snomed/total*100:.1f}%)")
            print(f"   Without SNOMED code: {len(without_snomed)} ({len(without_snomed)/total*100:.1f}%)")

        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update SNOMED codes for Intervention nodes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
