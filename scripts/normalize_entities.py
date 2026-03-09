#!/usr/bin/env python3
"""Normalize entities in Neo4j graph.

Post-import normalization for entity names:
1. Case duplicate merge (keep SNOMED canonical or higher-edge variant)
2. Garbage/placeholder node cleanup
3. Outcome variant IS_A linking (study-specific, group/subgroup, timepoint)
4. Brand/non-domain Outcome removal

Usage:
    # Dry-run (report only)
    PYTHONPATH=./src python3 scripts/normalize_entities.py --dry-run

    # Execute normalization
    PYTHONPATH=./src python3 scripts/normalize_entities.py --force

    # Specific phase only
    PYTHONPATH=./src python3 scripts/normalize_entities.py --force --phase case-merge
    PYTHONPATH=./src python3 scripts/normalize_entities.py --force --phase garbage
    PYTHONPATH=./src python3 scripts/normalize_entities.py --force --phase outcome-variants
    PYTHONPATH=./src python3 scripts/normalize_entities.py --force --phase outcome-brands

    # Report current state
    PYTHONPATH=./src python3 scripts/normalize_entities.py report
"""

import asyncio
import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from graph.neo4j_client import Neo4jClient
from graph.entity_normalizer import EntityNormalizer

logger = logging.getLogger(__name__)


# ============================================================================
# PATTERNS
# ============================================================================

# Garbage/placeholder patterns for Anatomy
ANATOMY_GARBAGE_RE = re.compile(
    r"(?i)^(not\s+(specified|applicable|explicitly|specifically|stated)|"
    r"single[- ]level$|^spinal$|not-applicable)",
)

# Garbage/placeholder patterns for Pathology/Intervention
PLACEHOLDER_RE = re.compile(
    r"(?i)(not\s+specified|non-specific|unspecified|"
    r"type not specified|not explicitly stated|"
    r"specific procedures not detailed|"
    r"presumed\s+degenerative)",
)

# Brand/digital therapeutic patterns (not spine surgery domain)
BRAND_PATTERNS = [
    "Daylight", "Rejoyn", "EndeavorRx", "Sleepio", "Somryst",
    "reSET-O", "reSET®", "EaseVRx", "MamaLift", "Freespira",
    "Canary Breathing",
]

# Study-specific outcome patterns
STUDY_SPECIFIC_RE = re.compile(
    r"^(.+?)\s*-\s*\w+[\w\s]*\bet\s+al\.",
    re.IGNORECASE,
)

# Group/Subgroup/Cohort patterns
GROUP_RE = re.compile(
    r"^(.+?)\s*(?:-\s+.*)?(?:\(Group\s+\w+\)|Subgroup|cohort)",
    re.IGNORECASE,
)


def print_separator(title: str):
    """Print section separator."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ============================================================================
# PHASE 1: Case Duplicate Merge
# ============================================================================

async def merge_case_duplicates(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Merge entities with case-only differences.

    Keeps the variant with more edges, or SNOMED canonical name.
    Transfers all relationships from the duplicate to the canonical.
    """
    print_separator("Phase 1: Case Duplicate Merge")
    stats = {"merged": 0, "skipped": 0, "errors": 0}

    for label in ["Intervention", "Pathology", "Outcome", "Anatomy"]:
        query = f"""
        MATCH (n:{label})
        WITH toLower(n.name) AS lower_name, collect(n) AS nodes
        WHERE size(nodes) > 1
        UNWIND nodes AS node
        OPTIONAL MATCH (node)-[r]-()
        WITH lower_name, node.name AS name, node.snomed_code AS snomed,
             count(r) AS edges
        ORDER BY lower_name,
                 CASE WHEN snomed IS NOT NULL THEN 0 ELSE 1 END,
                 edges DESC
        WITH lower_name, collect({{name: name, edges: edges, snomed: snomed}}) AS variants
        RETURN lower_name, variants
        """
        result = await client.run_query(query)
        if not result:
            continue

        groups = [r for r in result]
        if not groups:
            continue

        print(f"\n  {label}: {len(groups)} duplicate groups")

        for rec in groups:
            variants = rec["variants"]
            keep = variants[0]  # highest priority (SNOMED first, then edges)
            to_delete = variants[1:]

            if dry_run:
                print(f"    [DRY-RUN] Keep: \"{keep['name']}\" ({keep['edges']}e)")
                for v in to_delete:
                    print(f"              Delete: \"{v['name']}\" ({v['edges']}e)")
                stats["skipped"] += len(to_delete)
            else:
                for v in to_delete:
                    try:
                        await _merge_nodes(client, label, v["name"], keep["name"])
                        stats["merged"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(f"Merge failed {v['name']} -> {keep['name']}: {e}")

    return stats


async def _merge_nodes(
    client: Neo4jClient,
    label: str,
    delete_name: str,
    keep_name: str,
) -> None:
    """Transfer all relationships from delete_name to keep_name, then delete."""
    # Relationship types to transfer (label-specific)
    rel_configs = {
        "Intervention": [
            ("MATCH (p:Paper)-[:INVESTIGATES]->($old) WHERE NOT (p)-[:INVESTIGATES]->($new) "
             "MERGE (p)-[:INVESTIGATES]->($new)"),
            ("MATCH ($old)-[r:AFFECTS]->(o:Outcome) WHERE NOT ($new)-[:AFFECTS]->(o) "
             "CREATE ($new)-[r2:AFFECTS]->(o) SET r2 = properties(r)"),
            ("MATCH ($old)-[:TREATS]->(p:Pathology) WHERE NOT ($new)-[:TREATS]->(p) "
             "MERGE ($new)-[:TREATS]->(p)"),
        ],
        "Pathology": [
            ("MATCH (p:Paper)-[:STUDIES]->($old) WHERE NOT (p)-[:STUDIES]->($new) "
             "MERGE (p)-[:STUDIES]->($new)"),
            ("MATCH (i:Intervention)-[:TREATS]->($old) WHERE NOT (i)-[:TREATS]->($new) "
             "MERGE (i)-[:TREATS]->($new)"),
            ("MATCH ($old)-[:INVOLVES]->(a:Anatomy) WHERE NOT ($new)-[:INVOLVES]->(a) "
             "MERGE ($new)-[:INVOLVES]->(a)"),
        ],
        "Outcome": [
            ("MATCH (i:Intervention)-[r:AFFECTS]->($old) WHERE NOT (i)-[:AFFECTS]->($new) "
             "CREATE (i)-[r2:AFFECTS]->($new) SET r2 = properties(r)"),
        ],
        "Anatomy": [
            ("MATCH (p:Pathology)-[:INVOLVES]->($old) WHERE NOT (p)-[:INVOLVES]->($new) "
             "MERGE (p)-[:INVOLVES]->($new)"),
            ("MATCH (i:Intervention)-[:APPLIED_TO]->($old) WHERE NOT (i)-[:APPLIED_TO]->($new) "
             "MERGE (i)-[:APPLIED_TO]->($new)"),
        ],
    }

    for tmpl in rel_configs.get(label, []):
        query = tmpl.replace(
            "$old", f"(old:{label} {{name: $old_name}})"
        ).replace(
            "$new", f"(new:{label} {{name: $new_name}})"
        )
        # Simple approach: use direct parameterized query
        cypher = f"""
        MATCH (old:{label} {{name: $old_name}}), (new:{label} {{name: $new_name}})
        WITH old, new
        """ + tmpl.replace("$old", "old").replace("$new", "new")
        await client.run_write_query(
            cypher, {"old_name": delete_name, "new_name": keep_name}
        )

    # Transfer IS_A both directions
    await client.run_write_query(f"""
        MATCH (old:{label} {{name: $old_name}}), (new:{label} {{name: $new_name}})
        WITH old, new
        MATCH (old)-[:IS_A]->(parent) WHERE parent <> new AND NOT (new)-[:IS_A]->(parent)
        MERGE (new)-[:IS_A]->(parent)
    """, {"old_name": delete_name, "new_name": keep_name})

    await client.run_write_query(f"""
        MATCH (old:{label} {{name: $old_name}}), (new:{label} {{name: $new_name}})
        WITH old, new
        MATCH (child)-[:IS_A]->(old) WHERE child <> new AND NOT (child)-[:IS_A]->(new)
        MERGE (child)-[:IS_A]->(new)
    """, {"old_name": delete_name, "new_name": keep_name})

    # Copy SNOMED if needed
    await client.run_write_query(f"""
        MATCH (old:{label} {{name: $old_name}}), (new:{label} {{name: $new_name}})
        WHERE (new.snomed_code IS NULL OR new.snomed_code = '')
              AND old.snomed_code IS NOT NULL
        SET new.snomed_code = old.snomed_code, new.snomed_term = old.snomed_term
    """, {"old_name": delete_name, "new_name": keep_name})

    # Delete old
    await client.run_write_query(
        f"MATCH (n:{label} {{name: $name}}) DETACH DELETE n",
        {"name": delete_name},
    )


# ============================================================================
# PHASE 2: Garbage/Placeholder Cleanup
# ============================================================================

async def cleanup_garbage(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Remove garbage/placeholder nodes with low connectivity."""
    print_separator("Phase 2: Garbage/Placeholder Cleanup")
    stats = {"deleted": 0, "skipped": 0}

    for label, pattern_re, max_edges in [
        ("Anatomy", ANATOMY_GARBAGE_RE, 10),
        ("Pathology", PLACEHOLDER_RE, 10),
        ("Intervention", PLACEHOLDER_RE, 10),
    ]:
        query = f"MATCH (n:{label}) RETURN n.name AS name"
        result = await client.run_query(query)
        if not result:
            continue

        to_delete = []
        for rec in result:
            name = rec["name"]
            if name and pattern_re.search(name):
                # Check edges
                edge_result = await client.run_query(
                    f"MATCH (n:{label} {{name: $name}})-[r]-() RETURN count(r) AS edges",
                    {"name": name},
                )
                edges = edge_result[0]["edges"] if edge_result else 0
                if edges <= max_edges:
                    to_delete.append((name, edges))

        if to_delete:
            print(f"\n  {label}: {len(to_delete)} garbage nodes")
            for name, edges in to_delete:
                if dry_run:
                    print(f"    [DRY-RUN] Delete: \"{name}\" ({edges}e)")
                    stats["skipped"] += 1
                else:
                    await client.run_write_query(
                        f"MATCH (n:{label} {{name: $name}}) DETACH DELETE n",
                        {"name": name},
                    )
                    stats["deleted"] += 1
                    print(f"    Deleted: \"{name}\" ({edges}e)")

    return stats


# ============================================================================
# PHASE 3: Outcome Variant IS_A Linking
# ============================================================================

async def link_outcome_variants(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Link Outcome variants to canonical parents via IS_A.

    Handles:
    - Study-specific: "Fusion rate - Kim et al. PLIF" -> "Fusion Rate"
    - Group/Subgroup: "ODI (Group A)" -> "ODI"
    - Dash-qualified: "VAS Back - 6 months" -> "VAS Back"
    - Parenthetical: "Complication Rate (UBE)" -> "Complication Rate"
    """
    print_separator("Phase 3: Outcome Variant IS_A Linking")
    stats = {"linked": 0, "skipped": 0}

    normalizer = EntityNormalizer()

    # Find Outcomes without IS_A
    result = await client.run_query("""
        MATCH (o:Outcome)
        WHERE NOT (o)-[:IS_A]->(:Outcome)
        RETURN o.name AS name ORDER BY o.name
    """)
    if not result:
        print("  All Outcomes have IS_A relationships")
        return stats

    orphan_names = [r["name"] for r in result if r["name"]]
    print(f"  Found {len(orphan_names)} Outcomes without IS_A")

    # Build Neo4j name lookup
    canon_result = await client.run_query(
        "MATCH (o:Outcome) RETURN DISTINCT o.name AS name"
    )
    neo4j_names_lower = {r["name"].lower(): r["name"] for r in canon_result if r["name"]}

    to_link: list[tuple[str, str]] = []

    for name in orphan_names:
        canonical = _extract_base_outcome(name, normalizer, neo4j_names_lower)
        if canonical and canonical.lower() != name.lower():
            to_link.append((name, canonical))
        else:
            stats["skipped"] += 1

    print(f"  Matched: {len(to_link)}, Unmatched: {stats['skipped']}")

    if dry_run:
        for variant, canonical in to_link[:20]:
            print(f"    [DRY-RUN] {variant[:50]} -> {canonical}")
        if len(to_link) > 20:
            print(f"    ... and {len(to_link) - 20} more")
        stats["skipped"] += len(to_link)
    else:
        for variant, canonical in to_link:
            try:
                await client.run_write_query("""
                    MATCH (v:Outcome {name: $variant}), (c:Outcome {name: $canonical})
                    MERGE (v)-[r:IS_A]->(c)
                    ON CREATE SET r.auto_generated = true, r.source = 'normalize_entities'
                    WITH v, c
                    WHERE (v.snomed_code IS NULL OR v.snomed_code = '')
                          AND c.snomed_code IS NOT NULL AND c.snomed_code <> ''
                    SET v.snomed_code = c.snomed_code, v.snomed_term = c.snomed_term
                """, {"variant": variant, "canonical": canonical})
                stats["linked"] += 1
            except Exception as e:
                logger.warning(f"IS_A link failed {variant} -> {canonical}: {e}")

    return stats


def _extract_base_outcome(
    name: str,
    normalizer: EntityNormalizer,
    neo4j_names_lower: dict[str, str],
) -> str | None:
    """Extract base outcome name from a qualified variant.

    Tries multiple strategies:
    1. EntityNormalizer qualifier stripping
    2. Study-specific regex (et al.)
    3. Group/Subgroup regex
    4. Dash-separator extraction
    5. Parenthetical extraction
    """
    # 1. EntityNormalizer
    nr = normalizer.normalize_outcome(name)
    if nr.confidence > 0 and nr.normalized.lower() != name.lower():
        actual = neo4j_names_lower.get(nr.normalized.lower())
        if actual and actual.lower() != name.lower():
            return actual

    # 2. Study-specific (et al.)
    m = STUDY_SPECIFIC_RE.match(name)
    if m:
        base = m.group(1).strip()
        actual = neo4j_names_lower.get(base.lower())
        if actual and actual.lower() != name.lower():
            return actual

    # 3. Group/Subgroup
    # Pattern: "Base (Group X)"
    m = re.match(r"^(.+?)\s*\(Group\s+\w+\)", name)
    if m:
        base = m.group(1).strip()
        actual = neo4j_names_lower.get(base.lower())
        if actual:
            return actual

    # Pattern: "Base - ... Subgroup/cohort"
    m = re.match(r"^(.+?)\s*-\s+.*(?:Subgroup|cohort)", name, re.I)
    if m:
        base = m.group(1).strip()
        actual = neo4j_names_lower.get(base.lower())
        if actual:
            return actual

    # 4. Dash-separator: "Base - qualifier"
    m = re.match(r"^(.+?)\s*-\s+", name)
    if m:
        base = m.group(1).strip()
        if len(base) >= 3:
            actual = neo4j_names_lower.get(base.lower())
            if actual and actual.lower() != name.lower():
                return actual

    # 5. Parenthetical: "Base (qualifier)"
    m = re.match(r"^(.+?)\s*\(", name)
    if m:
        base = m.group(1).strip()
        if len(base) >= 3:
            actual = neo4j_names_lower.get(base.lower())
            if actual and actual.lower() != name.lower():
                return actual

    # 6. Timepoint regex
    timepoint_re = re.compile(
        r"^(.+?)\s+(?:\d+[\s-]*(?:months?|years?|weeks?|mo|yr|[mM])\b|"
        r"(?:pre|post)[-\s]?(?:op(?:erative)?)|"
        r"(?:final|latest|last)\s+follow[- ]?up|"
        r"(?:at\s+)?(?:discharge|baseline|follow[- ]?up))",
        re.IGNORECASE,
    )
    m = timepoint_re.match(name)
    if m:
        stripped = m.group(1).strip()
        if stripped and stripped.lower() != name.lower():
            actual = neo4j_names_lower.get(stripped.lower())
            if actual:
                return actual
            # Try normalizer on stripped
            nr2 = normalizer.normalize_outcome(stripped)
            if nr2.confidence > 0:
                actual = neo4j_names_lower.get(nr2.normalized.lower())
                if actual:
                    return actual

    return None


# ============================================================================
# PHASE 4: Brand/Non-domain Outcome Removal
# ============================================================================

async def remove_brand_outcomes(
    client: Neo4jClient,
    dry_run: bool = True,
) -> dict[str, int]:
    """Remove non-spine-surgery Outcomes (digital therapeutics, brand names)."""
    print_separator("Phase 4: Brand/Non-domain Outcome Removal")
    stats = {"deleted": 0, "skipped": 0}

    for brand in BRAND_PATTERNS:
        result = await client.run_query(
            "MATCH (o:Outcome) WHERE o.name CONTAINS $brand "
            "RETURN o.name AS name",
            {"brand": brand},
        )
        if not result:
            continue

        for rec in result:
            if dry_run:
                print(f"    [DRY-RUN] Delete: \"{rec['name'][:60]}\"")
                stats["skipped"] += 1
            else:
                await client.run_write_query(
                    "MATCH (o:Outcome {name: $name}) DETACH DELETE o",
                    {"name": rec["name"]},
                )
                stats["deleted"] += 1

    return stats


# ============================================================================
# REPORT
# ============================================================================

async def generate_report(client: Neo4jClient):
    """Report entity normalization status."""
    print_separator("Entity Normalization Report")

    for label in ["Intervention", "Pathology", "Outcome", "Anatomy"]:
        # Case duplicates
        dup_result = await client.run_query(f"""
            MATCH (n:{label})
            WITH toLower(n.name) AS lower_name, collect(n) AS nodes
            WHERE size(nodes) > 1
            RETURN count(lower_name) AS groups, sum(size(nodes) - 1) AS extras
        """)
        dup = dup_result[0] if dup_result else {"groups": 0, "extras": 0}

        # Garbage
        total_result = await client.run_query(f"MATCH (n:{label}) RETURN count(n) AS c")
        total = total_result[0]["c"] if total_result else 0

        # IS_A coverage
        isa_result = await client.run_query(f"""
            MATCH (n:{label})
            WITH count(n) AS total
            OPTIONAL MATCH (c:{label})-[:IS_A]->(:{label})
            WITH total, count(DISTINCT c) AS with_isa
            RETURN total, with_isa
        """)
        isa = isa_result[0] if isa_result else {"total": 0, "with_isa": 0}
        pct = (isa["with_isa"] / isa["total"] * 100) if isa["total"] else 0

        print(f"\n  {label}: {total} total")
        print(f"    Case duplicates: {dup['groups']} groups ({dup['extras']} extras)")
        print(f"    IS_A coverage:   {isa['with_isa']}/{isa['total']} ({pct:.1f}%)")


# ============================================================================
# MAIN
# ============================================================================

PHASES = {
    "case-merge": merge_case_duplicates,
    "garbage": cleanup_garbage,
    "outcome-variants": link_outcome_variants,
    "outcome-brands": remove_brand_outcomes,
}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Normalize entities in Neo4j graph"
    )
    parser.add_argument(
        "command", nargs="?", default="normalize",
        choices=["normalize", "report"],
        help="Command (default: normalize)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    parser.add_argument("--force", action="store_true", help="Execute changes")
    parser.add_argument(
        "--phase", choices=list(PHASES.keys()),
        help="Run specific phase only",
    )
    parser.add_argument("--quiet", "-q", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.command == "normalize" and not args.dry_run and not args.force:
        print("Error: Use --dry-run or --force.")
        sys.exit(1)

    dry_run = not args.force

    async with Neo4jClient() as client:
        if args.command == "report":
            await generate_report(client)
            return

        total = {"merged": 0, "deleted": 0, "linked": 0, "skipped": 0, "errors": 0}

        phases_to_run = [args.phase] if args.phase else list(PHASES.keys())

        for phase_name in phases_to_run:
            phase_fn = PHASES[phase_name]
            result = await phase_fn(client, dry_run)
            for k, v in result.items():
                total[k] = total.get(k, 0) + v

        # Summary
        print_separator("Summary")
        print(f"  Mode: {'DRY-RUN' if dry_run else 'EXECUTED'}")
        for k, v in total.items():
            if v > 0:
                print(f"  {k.capitalize()}: {v}")

        if dry_run and any(total.get(k, 0) > 0 for k in ["skipped"]):
            print(f"\n  To apply, run with --force")


if __name__ == "__main__":
    asyncio.run(main())
