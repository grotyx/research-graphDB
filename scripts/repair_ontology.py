#!/usr/bin/env python3
"""Repair ontology integrity issues in Neo4j graph.

Validates and repairs ontology-related data quality issues:
1. Missing IS_A relationships (from parent_code in SNOMED mappings)
2. Missing SNOMED codes on nodes that have matching names
3. TREATS backfill for Intervention+Pathology pairs found in papers
4. AFFECTS statistics summary (candidates for LLM re-extraction)
5. Cross-label IS_A detection and cleanup

Usage:
    # Dry-run (issues reported only)
    PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run

    # Execute repairs
    PYTHONPATH=./src python3 scripts/repair_ontology.py --force

    # Specific entity type
    PYTHONPATH=./src python3 scripts/repair_ontology.py --entity-type Pathology --force

    # Report current state
    PYTHONPATH=./src python3 scripts/repair_ontology.py report
"""

import asyncio
import argparse
import logging
import re
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from graph.neo4j_client import Neo4jClient
from graph.entity_normalizer import EntityNormalizer
from ontology.spine_snomed_mappings import (
    SPINE_INTERVENTION_SNOMED,
    SPINE_PATHOLOGY_SNOMED,
    SPINE_OUTCOME_SNOMED,
    SPINE_ANATOMY_SNOMED,
    SNOMEDMapping,
)

logger = logging.getLogger(__name__)

ENTITY_CONFIGS: dict[str, dict[str, "SNOMEDMapping"]] = {
    "Intervention": SPINE_INTERVENTION_SNOMED,
    "Pathology": SPINE_PATHOLOGY_SNOMED,
    "Outcome": SPINE_OUTCOME_SNOMED,
    "Anatomy": SPINE_ANATOMY_SNOMED,
}


def setup_logging(quiet: bool = False):
    """Configure logging."""
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_separator(title: str):
    """Print section separator."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def repair_missing_is_a(
    client: Neo4jClient,
    entity_type: str | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """Repair missing IS_A relationships using SNOMED parent_code.

    Args:
        client: Neo4j client
        entity_type: Specific entity type (None for all)
        dry_run: If True, only report

    Returns:
        {"repaired": int, "skipped": int, "errors": int}
    """
    print_separator("Repair Missing IS_A Relationships")
    stats = {"repaired": 0, "skipped": 0, "errors": 0}

    configs = ENTITY_CONFIGS
    if entity_type:
        configs = {entity_type: ENTITY_CONFIGS[entity_type]}

    for label, mapping_dict in configs.items():
        code_to_name: dict[str, str] = {}
        for name, m in mapping_dict.items():
            code_to_name[m.code] = name

        missing = []
        for name, m in mapping_dict.items():
            if not m.parent_code:
                continue
            parent_name = code_to_name.get(m.parent_code)
            if not parent_name:
                continue

            # Check if IS_A already exists
            query = f"""
            OPTIONAL MATCH (child:{label} {{name: $child_name}})-[:IS_A]->(parent:{label} {{name: $parent_name}})
            RETURN count(*) > 0 AS exists
            """
            result = await client.run_query(
                query, {"child_name": name, "parent_name": parent_name}
            )
            if result and result[0].get("exists"):
                continue

            # Check that child node actually exists in Neo4j
            check_query = f"MATCH (n:{label} {{name: $name}}) RETURN count(n) > 0 AS exists"
            result = await client.run_query(check_query, {"name": name})
            if not result or not result[0].get("exists"):
                stats["skipped"] += 1
                continue

            missing.append((name, parent_name))

        print(f"\n  {label}: {len(missing)} missing IS_A relationships")

        if dry_run:
            for child, parent in missing[:10]:
                print(f"    [DRY-RUN] Would create: {child} -[:IS_A]-> {parent}")
            if len(missing) > 10:
                print(f"    ... and {len(missing) - 10} more")
            stats["skipped"] += len(missing)
        else:
            for child, parent in missing:
                try:
                    repair_query = f"""
                    MERGE (child:{label} {{name: $child_name}})
                    MERGE (parent:{label} {{name: $parent_name}})
                    MERGE (child)-[r:IS_A]->(parent)
                    ON CREATE SET r.auto_generated = true,
                                  r.source = 'repair_ontology',
                                  r.created_at = datetime()
                    RETURN child.name AS child, parent.name AS parent
                    """
                    await client.run_write_query(
                        repair_query,
                        {"child_name": child, "parent_name": parent},
                    )
                    stats["repaired"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"Failed IS_A repair {child} -> {parent}: {e}")

    return stats


async def repair_missing_snomed(
    client: Neo4jClient,
    entity_type: str | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """Add missing SNOMED codes to nodes with matching names.

    Args:
        client: Neo4j client
        entity_type: Specific entity type (None for all)
        dry_run: If True, only report

    Returns:
        {"repaired": int, "skipped": int, "errors": int}
    """
    print_separator("Repair Missing SNOMED Codes")
    stats = {"repaired": 0, "skipped": 0, "errors": 0}

    configs = ENTITY_CONFIGS
    if entity_type:
        configs = {entity_type: ENTITY_CONFIGS[entity_type]}

    for label, mapping_dict in configs.items():
        # Find nodes without SNOMED that have a matching name
        query = f"""
        MATCH (n:{label})
        WHERE (n.snomed_code IS NULL OR n.snomed_code = '')
        RETURN n.name AS name
        ORDER BY n.name
        """
        result = await client.run_query(query)
        if not result:
            print(f"\n  {label}: All nodes have SNOMED codes")
            continue

        # Build name lookup (case-insensitive)
        name_lower_to_mapping: dict[str, tuple[str, SNOMEDMapping]] = {}
        for canonical, m in mapping_dict.items():
            name_lower_to_mapping[canonical.lower()] = (canonical, m)
            for syn in m.synonyms:
                name_lower_to_mapping[syn.lower()] = (canonical, m)
            for abbr in m.abbreviations:
                name_lower_to_mapping[abbr.lower()] = (canonical, m)

        candidates = []
        for rec in result:
            node_name = rec["name"]
            match = name_lower_to_mapping.get(node_name.lower())
            if match:
                canonical, m = match
                candidates.append((node_name, m.code, m.term))

        print(f"\n  {label}: {len(candidates)} nodes can be enriched with SNOMED")

        if dry_run:
            for name, code, term in candidates[:10]:
                print(f"    [DRY-RUN] {name} -> snomed_code={code}, snomed_term={term}")
            if len(candidates) > 10:
                print(f"    ... and {len(candidates) - 10} more")
            stats["skipped"] += len(candidates)
        else:
            for name, code, term in candidates:
                try:
                    update_query = f"""
                    MATCH (n:{label} {{name: $name}})
                    SET n.snomed_code = $code, n.snomed_term = $term
                    RETURN n.name AS updated
                    """
                    await client.run_write_query(
                        update_query,
                        {"name": name, "code": code, "term": term},
                    )
                    stats["repaired"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"Failed SNOMED repair for {name}: {e}")

    return stats


async def backfill_treats(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Auto-create TREATS for Intervention+Pathology pairs found in papers.

    Finds papers that INVESTIGATES an Intervention and STUDIES a Pathology
    but the Intervention has no TREATS relationship to that Pathology.

    Args:
        client: Neo4j client
        dry_run: If True, only report

    Returns:
        {"repaired": int, "skipped": int, "errors": int}
    """
    print_separator("Backfill TREATS Relationships")
    stats = {"repaired": 0, "skipped": 0, "errors": 0}

    # Find missing TREATS: Intervention investigated + Pathology studied but no TREATS
    query = """
    MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention),
          (p)-[:STUDIES]->(path:Pathology)
    WHERE NOT (i)-[:TREATS]->(path)
    WITH i.name AS intervention, path.name AS pathology,
         collect(DISTINCT p.paper_id) AS paper_ids,
         count(DISTINCT p) AS paper_count
    WHERE paper_count >= 1
    RETURN intervention, pathology, paper_ids, paper_count
    ORDER BY paper_count DESC
    """
    result = await client.run_query(query)

    if not result:
        print("\n  No missing TREATS relationships found")
        return stats

    print(f"\n  Found {len(result)} missing TREATS relationships")

    if dry_run:
        for rec in result[:15]:
            i = rec["intervention"]
            p = rec["pathology"]
            cnt = rec["paper_count"]
            print(f"    [DRY-RUN] {i} -[:TREATS]-> {p} (from {cnt} paper(s))")
        if len(result) > 15:
            print(f"    ... and {len(result) - 15} more")
        stats["skipped"] = len(result)
    else:
        for rec in result:
            intervention = rec["intervention"]
            pathology = rec["pathology"]
            paper_ids = rec["paper_ids"]
            paper_count = rec["paper_count"]

            try:
                create_query = """
                MATCH (i:Intervention {name: $intervention})
                MATCH (path:Pathology {name: $pathology})
                MERGE (i)-[r:TREATS]->(path)
                ON CREATE SET r.source_paper_ids = $paper_ids,
                              r.paper_count = $paper_count,
                              r.source = 'repair_ontology',
                              r.created_at = datetime()
                RETURN i.name AS i, path.name AS p
                """
                await client.run_write_query(
                    create_query,
                    {
                        "intervention": intervention,
                        "pathology": pathology,
                        "paper_ids": paper_ids,
                        "paper_count": paper_count,
                    },
                )
                stats["repaired"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(
                    f"Failed TREATS backfill {intervention} -> {pathology}: {e}"
                )

    return stats


# Timepoint/qualifier regex for outcome variant stripping
_TIMEPOINT_RE = re.compile(
    r'^(.+?)\s+(?:\d+[\s-]*(?:months?|years?|weeks?|mo|yr|[mM])\b|'
    r'(?:pre|post)[-\s]?(?:op(?:erative)?)|'
    r'(?:final|latest|last)\s+follow[- ]?up|'
    r'(?:at\s+)?(?:discharge|baseline|follow[- ]?up))',
    re.IGNORECASE,
)


async def repair_outcome_variant_is_a(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Link Outcome variant nodes to their canonical parent via IS_A.

    Many Outcome nodes include timepoint qualifiers (e.g. "VAS Back 6 months",
    "ODI 1 year") that prevent them from being connected to the canonical
    Outcome node.  This function:
      1. Finds Outcome nodes without any IS_A relationship.
      2. Normalizes each name via EntityNormalizer.normalize_outcome().
      3. Falls back to a timepoint regex strip if normalization fails.
      4. Creates (variant)-[:IS_A]->(canonical) if the canonical exists in Neo4j.
      5. Copies snomed_code/snomed_term from canonical to variant when missing.

    Args:
        client: Neo4j client
        dry_run: If True, only report

    Returns:
        {"repaired": int, "skipped": int, "errors": int}
    """
    print_separator("Repair Outcome Variant IS_A")
    stats = {"repaired": 0, "skipped": 0, "errors": 0}

    # 1. Find Outcome nodes without IS_A
    query = """
    MATCH (o:Outcome)
    WHERE NOT (o)-[:IS_A]->(:Outcome)
    RETURN o.name AS name
    ORDER BY o.name
    """
    result = await client.run_query(query)
    if not result:
        print("  All Outcome nodes already have IS_A relationships")
        return stats

    orphan_names = [r["name"] for r in result if r["name"]]
    print(f"  Found {len(orphan_names)} Outcome nodes without IS_A")

    # 2. Build set of canonical Outcome names in Neo4j
    canon_query = """
    MATCH (o:Outcome)
    RETURN DISTINCT o.name AS name
    """
    canon_result = await client.run_query(canon_query)
    neo4j_names = {r["name"] for r in canon_result if r["name"]}
    neo4j_names_lower = {n.lower(): n for n in neo4j_names}

    normalizer = EntityNormalizer()

    to_link: list[tuple[str, str]] = []  # (variant_name, canonical_name)

    for name in orphan_names:
        # 3a. Try EntityNormalizer
        nr = normalizer.normalize_outcome(name)
        if nr.confidence > 0 and nr.normalized.lower() != name.lower():
            canonical = nr.normalized
            # Check canonical exists in Neo4j
            actual = neo4j_names_lower.get(canonical.lower())
            if actual and actual.lower() != name.lower():
                to_link.append((name, actual))
                continue

        # 3b. Fallback: timepoint regex
        m = _TIMEPOINT_RE.match(name)
        if m:
            stripped = m.group(1).strip()
            if stripped and stripped.lower() != name.lower():
                # Try normalizer on stripped form
                nr2 = normalizer.normalize_outcome(stripped)
                if nr2.confidence > 0:
                    actual = neo4j_names_lower.get(nr2.normalized.lower())
                    if actual and actual.lower() != name.lower():
                        to_link.append((name, actual))
                        continue
                # Direct match on stripped form
                actual = neo4j_names_lower.get(stripped.lower())
                if actual and actual.lower() != name.lower():
                    to_link.append((name, actual))
                    continue

        stats["skipped"] += 1

    print(f"  Matched {len(to_link)} variants to canonical Outcome nodes")
    print(f"  Unmatched: {stats['skipped']}")

    if dry_run:
        for variant, canonical in to_link[:20]:
            print(f"    [DRY-RUN] {variant} -[:IS_A]-> {canonical}")
        if len(to_link) > 20:
            print(f"    ... and {len(to_link) - 20} more")
        stats["skipped"] += len(to_link)
    else:
        for variant, canonical in to_link:
            try:
                repair_query = """
                MATCH (v:Outcome {name: $variant})
                MATCH (c:Outcome {name: $canonical})
                MERGE (v)-[r:IS_A]->(c)
                ON CREATE SET r.auto_generated = true,
                              r.source = 'repair_outcome_variant',
                              r.created_at = datetime()
                WITH v, c
                WHERE (v.snomed_code IS NULL OR v.snomed_code = '')
                      AND c.snomed_code IS NOT NULL AND c.snomed_code <> ''
                SET v.snomed_code = c.snomed_code,
                    v.snomed_term = c.snomed_term
                RETURN v.name AS variant, c.name AS canonical
                """
                await client.run_write_query(
                    repair_query,
                    {"variant": variant, "canonical": canonical},
                )
                stats["repaired"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Failed Outcome IS_A repair {variant} -> {canonical}: {e}")

    return stats


async def report_affects_stats(client: Neo4jClient) -> None:
    """Report AFFECTS relationships with missing statistics.

    Logs candidates for potential LLM re-extraction.
    """
    print_separator("AFFECTS Statistics Report")

    query = """
    MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
    WITH count(r) AS total,
         sum(CASE WHEN r.p_value IS NOT NULL THEN 1 ELSE 0 END) AS has_pval,
         sum(CASE WHEN r.effect_size IS NOT NULL AND r.effect_size <> ''
              AND r.effect_size <> 'not_reported' THEN 1 ELSE 0 END) AS has_es,
         sum(CASE WHEN r.is_significant IS NOT NULL THEN 1 ELSE 0 END) AS has_sig
    RETURN total, has_pval, has_es, has_sig
    """
    result = await client.run_query(query)
    if result:
        r = result[0]
        total = r["total"]
        print(f"  Total AFFECTS: {total}")
        print(f"  With p_value:      {r['has_pval']}/{total} "
              f"({r['has_pval']/total*100:.1f}%)" if total > 0 else "")
        print(f"  With effect_size:  {r['has_es']}/{total} "
              f"({r['has_es']/total*100:.1f}%)" if total > 0 else "")
        print(f"  With is_significant: {r['has_sig']}/{total} "
              f"({r['has_sig']/total*100:.1f}%)" if total > 0 else "")

    # Find papers with AFFECTS missing stats for re-extraction candidates
    query2 = """
    MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)-[r:AFFECTS]->(o:Outcome)
    WHERE r.p_value IS NULL AND r.effect_size IS NULL
    WITH p.paper_id AS paper_id, p.title AS title,
         count(r) AS missing_stats_count
    ORDER BY missing_stats_count DESC
    LIMIT 10
    RETURN paper_id, title, missing_stats_count
    """
    result2 = await client.run_query(query2)
    if result2:
        print(f"\n  Top candidates for LLM re-extraction:")
        for rec in result2:
            print(f"    {rec['paper_id']}: {rec['missing_stats_count']} AFFECTS "
                  f"without stats - {(rec['title'] or '')[:60]}")


async def generate_report(client: Neo4jClient):
    """Generate comprehensive ontology integrity report."""
    print_separator("Ontology Integrity Report")

    # IS_A per entity type
    for label in sorted(ENTITY_CONFIGS.keys()):
        query = f"""
        MATCH (n:{label})
        WITH count(n) AS total
        OPTIONAL MATCH (child:{label})-[r:IS_A]->(parent:{label})
        WITH total, count(r) AS isa_count,
             count(DISTINCT child) AS children_with_parent
        RETURN total, isa_count, children_with_parent
        """
        result = await client.run_query(query)
        if result:
            r = result[0]
            total = r["total"]
            isa = r["isa_count"]
            with_parent = r["children_with_parent"]
            pct = (with_parent / total * 100) if total > 0 else 0
            print(f"\n  {label}:")
            print(f"    Total nodes:       {total}")
            print(f"    IS_A relationships: {isa}")
            print(f"    With IS_A parent:  {with_parent} ({pct:.1f}%)")

    # SNOMED coverage
    print_separator("SNOMED Coverage")
    for label in sorted(ENTITY_CONFIGS.keys()):
        query = f"""
        MATCH (n:{label})
        WITH count(n) AS total,
             sum(CASE WHEN n.snomed_code IS NOT NULL AND n.snomed_code <> ''
                      THEN 1 ELSE 0 END) AS with_snomed
        RETURN total, with_snomed
        """
        result = await client.run_query(query)
        if result:
            r = result[0]
            total = r["total"]
            ws = r["with_snomed"]
            pct = (ws / total * 100) if total > 0 else 0
            print(f"  {label}: {ws}/{total} ({pct:.1f}%)")

    # Cycle detection
    print_separator("Cycle Detection")
    for label in sorted(ENTITY_CONFIGS.keys()):
        query = f"""
        MATCH path = (n:{label})-[:IS_A*2..10]->(n)
        RETURN count(path) AS cnt
        """
        result = await client.run_query(query)
        cnt = result[0]["cnt"] if result else 0
        status = "OK" if cnt == 0 else f"CYCLES FOUND: {cnt}"
        print(f"  {label}: {status}")

    # AFFECTS statistics
    await report_affects_stats(client)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Repair ontology integrity issues in Neo4j graph"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="repair",
        choices=["repair", "report"],
        help="Command to execute (default: repair)",
    )
    parser.add_argument(
        "--entity-type",
        choices=sorted(ENTITY_CONFIGS.keys()),
        help="Process specific entity type only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show issues without fixing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Execute repairs (required for repair command)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress info logs",
    )

    args = parser.parse_args()
    setup_logging(args.quiet)

    if args.command == "repair" and not args.dry_run and not args.force:
        print("Error: Use --dry-run or --force to execute.")
        print("  --dry-run: Preview issues without fixing")
        print("  --force: Execute repairs against Neo4j")
        sys.exit(1)

    dry_run = not args.force

    async with Neo4jClient() as client:
        if args.command == "report":
            await generate_report(client)
            return

        # Run repairs
        total_stats = {"repaired": 0, "skipped": 0, "errors": 0}

        # 1. Missing IS_A
        s = await repair_missing_is_a(client, args.entity_type, dry_run)
        for k in total_stats:
            total_stats[k] += s[k]

        # 2. Missing SNOMED codes
        s = await repair_missing_snomed(client, args.entity_type, dry_run)
        for k in total_stats:
            total_stats[k] += s[k]

        # 3. TREATS backfill (only if no entity_type filter)
        if not args.entity_type:
            s = await backfill_treats(client, dry_run)
            for k in total_stats:
                total_stats[k] += s[k]

        # 4. Outcome variant IS_A backfill
        if not args.entity_type or args.entity_type == "Outcome":
            s = await repair_outcome_variant_is_a(client, dry_run)
            for k in total_stats:
                total_stats[k] += s[k]

        # 5. AFFECTS stats report (always report-only)
        await report_affects_stats(client)

        # Summary
        print_separator("Summary")
        mode = "DRY-RUN" if dry_run else "EXECUTED"
        print(f"  Mode: {mode}")
        print(f"  Repaired: {total_stats['repaired']}")
        print(f"  Skipped:  {total_stats['skipped']}")
        print(f"  Errors:   {total_stats['errors']}")

        if dry_run and total_stats["skipped"] > 0:
            print(f"\n  To apply repairs, run with --force")


if __name__ == "__main__":
    asyncio.run(main())
