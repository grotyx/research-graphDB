#!/usr/bin/env python3
"""Fix NULL category Interventions in Neo4j.

This script:
1. Finds all Intervention nodes with NULL category
2. Uses EntityNormalizer to determine the correct category
3. Updates the nodes in Neo4j

Usage:
    python scripts/fix_intervention_categories.py [--dry-run]

Options:
    --dry-run: Show what would be updated without making changes
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neo4j import GraphDatabase
from dotenv import load_dotenv
from graph.entity_normalizer import EntityNormalizer


def main(dry_run: bool = False):
    """Fix NULL category Interventions."""
    # Load environment
    load_dotenv()

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # Initialize normalizer
    normalizer = EntityNormalizer()

    try:
        with driver.session(database=database) as session:
            # Step 1: Find all Interventions with NULL category
            print("\n" + "=" * 60)
            print("Finding Interventions with NULL category...")
            print("=" * 60)

            result = session.run("""
                MATCH (i:Intervention)
                WHERE i.category IS NULL
                RETURN i.name AS name
                ORDER BY name
            """)

            null_interventions = [record["name"] for record in result]
            print(f"\nFound {len(null_interventions)} Interventions with NULL category")

            if not null_interventions:
                print("No interventions to fix!")
                return

            # Step 2: Normalize each and determine category
            print("\n" + "=" * 60)
            print("Analyzing interventions...")
            print("=" * 60)

            updates = []
            unmapped = []

            for name in null_interventions:
                result = normalizer.normalize_intervention(name)

                if result.category:
                    updates.append({
                        "original": name,
                        "normalized": result.normalized,
                        "category": result.category,
                        "confidence": result.confidence,
                        "method": result.method
                    })
                    print(f"  ✓ {name}")
                    print(f"    → Normalized: {result.normalized}")
                    print(f"    → Category: {result.category}")
                    print(f"    → Confidence: {result.confidence:.2f} ({result.method})")
                else:
                    unmapped.append({
                        "name": name,
                        "normalized": result.normalized,
                        "confidence": result.confidence
                    })
                    print(f"  ✗ {name} (no category mapping)")
                    print(f"    → Normalized: {result.normalized}")

            # Step 3: Apply updates (if not dry-run)
            print("\n" + "=" * 60)
            print(f"Summary: {len(updates)} can be updated, {len(unmapped)} unmapped")
            print("=" * 60)

            if dry_run:
                print("\n[DRY RUN] No changes made. Run without --dry-run to apply.")
                return

            if not updates:
                print("\nNo updates to apply.")
                return

            print(f"\nApplying {len(updates)} updates...")

            updated_count = 0
            for update in updates:
                try:
                    # Update category for the intervention
                    session.run("""
                        MATCH (i:Intervention {name: $name})
                        SET i.category = $category
                        RETURN i
                    """, {
                        "name": update["original"],
                        "category": update["category"]
                    })
                    updated_count += 1
                    print(f"  ✓ Updated: {update['original']} → {update['category']}")
                except Exception as e:
                    print(f"  ✗ Failed to update {update['original']}: {e}")

            print(f"\n✓ Successfully updated {updated_count} Interventions")

            # Step 4: Show remaining NULL categories
            print("\n" + "=" * 60)
            print("Verification: Remaining NULL categories")
            print("=" * 60)

            result = session.run("""
                MATCH (i:Intervention)
                WHERE i.category IS NULL
                RETURN i.name AS name, COUNT{(i)<-[:INVESTIGATES]-()} AS paper_count
                ORDER BY paper_count DESC
            """)

            remaining = list(result)
            if remaining:
                print(f"\n{len(remaining)} Interventions still have NULL category:")
                for record in remaining:
                    print(f"  - {record['name']} ({record['paper_count']} papers)")
                print("\nConsider adding these to INTERVENTION_CATEGORIES in entity_normalizer.py")
            else:
                print("\n✓ All Interventions now have categories!")

            # Step 5: Show category distribution
            print("\n" + "=" * 60)
            print("Category Distribution (AFFECTS relationships)")
            print("=" * 60)

            result = session.run("""
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE i.category IS NOT NULL
                RETURN i.category AS category, COUNT(*) AS count
                ORDER BY count DESC
            """)

            for record in result:
                print(f"  {record['category']}: {record['count']} relationships")

    finally:
        driver.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
