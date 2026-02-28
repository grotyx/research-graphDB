#!/usr/bin/env python3
"""Neo4j 엔티티 IS_A 계층 구조 구축 스크립트.

spine_snomed_mappings.py의 parent_code를 기반으로
Intervention, Pathology, Outcome, Anatomy 엔티티의 IS_A 계층을 Neo4j에 적용합니다.

Usage:
    # Dry-run (쿼리 확인만)
    PYTHONPATH=./src python3 scripts/build_ontology.py --dry-run

    # 실행
    PYTHONPATH=./src python3 scripts/build_ontology.py --force

    # 특정 엔티티 타입만
    PYTHONPATH=./src python3 scripts/build_ontology.py --entity-type Pathology --force

    # 리포트 (현재 IS_A 현황)
    PYTHONPATH=./src python3 scripts/build_ontology.py report
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from graph.neo4j_client import Neo4jClient
from graph.types.schema import SpineGraphSchema
from graph.taxonomy_manager import VALID_ENTITY_TYPES

logger = logging.getLogger(__name__)


def setup_logging(quiet: bool = False):
    """로깅 설정."""
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_separator(title: str):
    """구분선 출력."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def build_entity_taxonomy(
    client: Neo4jClient,
    entity_type: str | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """엔티티 IS_A 계층을 Neo4j에 적용.

    Args:
        client: Neo4j 클라이언트
        entity_type: 특정 엔티티 타입만 처리 (None이면 전체)
        dry_run: True이면 쿼리만 출력

    Returns:
        {"applied": int, "skipped": int, "errors": int}
    """
    queries = SpineGraphSchema.get_init_entity_taxonomy_cypher()

    # Filter by entity type if specified
    if entity_type:
        queries = [
            (q, p) for q, p in queries if f":{entity_type}" in q
        ]

    stats = {"applied": 0, "skipped": 0, "errors": 0}
    total = len(queries)

    print(f"\nTotal IS_A relationships to apply: {total}")

    if dry_run:
        print("\n[DRY-RUN] Showing first 10 queries:")
        for i, (query, params) in enumerate(queries[:10]):
            print(f"  {i+1}. {params['child_name']} -[:IS_A]-> {params['parent_name']}")
        if total > 10:
            print(f"  ... and {total - 10} more")
        stats["skipped"] = total
        return stats

    for i, (query, params) in enumerate(queries):
        try:
            await client.run_write_query(query, params)
            stats["applied"] += 1
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i+1}/{total}")
        except Exception as e:
            stats["errors"] += 1
            logger.warning(
                f"Failed to apply IS_A: {params['child_name']} -> "
                f"{params['parent_name']}: {e}"
            )

    return stats


async def generate_report(client: Neo4jClient):
    """현재 IS_A 계층 현황 리포트."""
    print_separator("Ontology IS_A Report")

    for entity_type in sorted(VALID_ENTITY_TYPES):
        query = f"""
        MATCH (n:{entity_type})
        WITH count(n) as total
        OPTIONAL MATCH (child:{entity_type})-[r:IS_A]->(parent:{entity_type})
        WITH total, count(r) as isa_count
        RETURN total, isa_count
        """

        try:
            results = await client.run_query(query)
            if results:
                total = results[0].get("total", 0)
                isa_count = results[0].get("isa_count", 0)
                print(f"\n  {entity_type}:")
                print(f"    Total nodes: {total}")
                print(f"    IS_A relationships: {isa_count}")
        except Exception as e:
            print(f"\n  {entity_type}: Error - {e}")

    # Root nodes per entity type
    print_separator("Root Nodes (no IS_A parent)")
    for entity_type in sorted(VALID_ENTITY_TYPES):
        query = f"""
        MATCH (root:{entity_type})
        WHERE NOT (root)-[:IS_A]->(:{entity_type})
        RETURN root.name as name
        ORDER BY root.name
        LIMIT 20
        """

        try:
            results = await client.run_query(query)
            if results:
                names = [r["name"] for r in results]
                print(f"\n  {entity_type} ({len(names)} roots):")
                for name in names[:10]:
                    print(f"    - {name}")
                if len(names) > 10:
                    print(f"    ... and {len(names) - 10} more")
        except Exception as e:
            print(f"\n  {entity_type}: Error - {e}")


async def main():
    """메인 실행."""
    parser = argparse.ArgumentParser(
        description="Build ontology IS_A hierarchy in Neo4j"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="build",
        choices=["build", "report"],
        help="Command to execute (default: build)",
    )
    parser.add_argument(
        "--entity-type",
        choices=sorted(VALID_ENTITY_TYPES),
        help="Process specific entity type only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show queries without executing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Execute queries (required for build)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress info logs",
    )

    args = parser.parse_args()
    setup_logging(args.quiet)

    if args.command == "build" and not args.dry_run and not args.force:
        print("Error: Use --dry-run or --force to execute.")
        print("  --dry-run: Preview queries without executing")
        print("  --force: Execute queries against Neo4j")
        sys.exit(1)

    async with Neo4jClient() as client:
        if args.command == "report":
            await generate_report(client)
        elif args.command == "build":
            print_separator("Build Entity Ontology")
            dry_run = not args.force

            stats = await build_entity_taxonomy(
                client,
                entity_type=args.entity_type,
                dry_run=dry_run,
            )

            print_separator("Results")
            print(f"  Applied: {stats['applied']}")
            print(f"  Skipped: {stats['skipped']}")
            print(f"  Errors:  {stats['errors']}")

            if dry_run:
                print("\n  [DRY-RUN] No changes were made.")
                print("  Use --force to apply changes.")


if __name__ == "__main__":
    asyncio.run(main())
