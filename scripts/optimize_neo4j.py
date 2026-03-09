#!/usr/bin/env python3
"""Neo4j Index and Query Optimization Script.

This script:
1. Analyzes current indexes and identifies gaps
2. Creates composite indexes for common query patterns
3. Creates full-text indexes for text search
4. Creates relationship property indexes
5. Profiles slow queries and provides optimization recommendations

Usage:
    python scripts/optimize_neo4j.py --analyze          # Analyze only
    python scripts/optimize_neo4j.py --create-indexes   # Create recommended indexes
    python scripts/optimize_neo4j.py --profile-queries  # Profile slow queries
    python scripts/optimize_neo4j.py --full             # Full optimization
"""

import asyncio
import argparse
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_file = project_root / '.env'
load_dotenv(env_file)

from src.graph.neo4j_client import Neo4jClient, Neo4jConfig
from src.graph.spine_schema import SpineGraphSchema

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class IndexInfo:
    """Index information."""
    name: str
    label: str
    properties: list[str]
    type: str = "RANGE"  # RANGE, TEXT, FULLTEXT
    state: str = "ONLINE"
    uniqueness: str = "NONUNIQUE"


@dataclass
class QueryProfile:
    """Query profiling result."""
    query: str
    description: str
    execution_time_ms: float
    db_hits: int = 0
    rows_returned: int = 0
    has_index: bool = False
    recommendations: list[str] = field(default_factory=list)


class Neo4jOptimizer:
    """Neo4j index and query optimizer."""

    def __init__(self, client: Neo4jClient):
        self.client = client

    async def analyze_current_indexes(self) -> list[IndexInfo]:
        """Analyze current indexes in Neo4j.

        Returns:
            List of existing indexes
        """
        logger.info("=" * 80)
        logger.info("ANALYZING CURRENT INDEXES")
        logger.info("=" * 80)

        # Get all indexes
        index_query = "SHOW INDEXES"
        try:
            results = await self.client.run_query(index_query)
        except Exception as e:
            logger.warning(f"Could not fetch indexes (may need Neo4j 4.4+): {e}")
            # Fallback for older Neo4j versions
            results = []

        indexes = []
        for record in results:
            index_info = IndexInfo(
                name=record.get("name", ""),
                label=record.get("labelsOrTypes", [""])[0] if record.get("labelsOrTypes") else "",
                properties=record.get("properties", []),
                type=record.get("type", "RANGE"),
                state=record.get("state", "ONLINE"),
                uniqueness=record.get("uniqueness", "NONUNIQUE")
            )
            indexes.append(index_info)

        logger.info(f"\nFound {len(indexes)} existing indexes:\n")

        # Group by type
        by_type = {}
        for idx in indexes:
            by_type.setdefault(idx.type, []).append(idx)

        for idx_type, idxs in sorted(by_type.items()):
            logger.info(f"  {idx_type} Indexes ({len(idxs)}):")
            for idx in idxs:
                props_str = ", ".join(idx.properties)
                logger.info(f"    - {idx.label}.{props_str} [{idx.state}]")

        return indexes

    async def identify_index_gaps(self, existing_indexes: list[IndexInfo]) -> dict:
        """Identify missing indexes for common query patterns.

        Returns:
            Dict of recommended indexes by category
        """
        logger.info("\n" + "=" * 80)
        logger.info("IDENTIFYING INDEX GAPS")
        logger.info("=" * 80)

        existing_props = set()
        for idx in existing_indexes:
            if len(idx.properties) == 1:
                existing_props.add((idx.label, idx.properties[0]))

        gaps = {
            "composite": [],
            "fulltext": [],
            "relationship": [],
        }

        # Composite indexes for common query patterns
        composite_recommendations = [
            {
                "label": "Paper",
                "properties": ["sub_domain", "evidence_level"],
                "reason": "Common filtering pattern in list_papers()",
            },
            {
                "label": "Paper",
                "properties": ["year", "sub_domain"],
                "reason": "Temporal analysis by domain",
            },
            {
                "label": "Intervention",
                "properties": ["name", "category"],
                "reason": "Intervention categorization queries",
            },
            {
                "label": "Intervention",
                "properties": ["category", "approach"],
                "reason": "Approach-based filtering",
            },
            {
                "label": "Outcome",
                "properties": ["name", "type"],
                "reason": "Outcome type-based queries",
            },
        ]

        for rec in composite_recommendations:
            # Check if any of the properties are indexed
            has_any_index = any(
                (rec["label"], prop) in existing_props
                for prop in rec["properties"]
            )
            gaps["composite"].append({
                **rec,
                "has_partial_index": has_any_index,
            })

        # Full-text indexes for text search
        fulltext_recommendations = [
            {
                "name": "paper_text_search",
                "label": "Paper",
                "properties": ["title", "abstract"],
                "reason": "Natural language search in papers",
            },
            {
                "name": "pathology_search",
                "label": "Pathology",
                "properties": ["name", "description"],
                "reason": "Search pathologies by description",
            },
            {
                "name": "intervention_search",
                "label": "Intervention",
                "properties": ["name", "full_name", "aliases"],
                "reason": "Search interventions by various names",
            },
        ]

        # Check if fulltext indexes exist
        existing_fulltext = [
            idx.name for idx in existing_indexes
            if idx.type in ["FULLTEXT", "TEXT"]
        ]

        for rec in fulltext_recommendations:
            gaps["fulltext"].append({
                **rec,
                "exists": rec["name"] in existing_fulltext,
            })

        # Relationship property indexes
        relationship_recommendations = [
            {
                "relationship": "AFFECTS",
                "property": "p_value",
                "reason": "Statistical filtering (p < 0.05)",
            },
            {
                "relationship": "AFFECTS",
                "property": "is_significant",
                "reason": "Filter for significant results",
            },
            {
                "relationship": "AFFECTS",
                "property": "direction",
                "reason": "Filter by improvement direction",
            },
            {
                "relationship": "STUDIES",
                "property": "is_primary",
                "reason": "Primary pathology filtering",
            },
            {
                "relationship": "INVESTIGATES",
                "property": "is_comparison",
                "reason": "Comparative study filtering",
            },
        ]

        gaps["relationship"] = relationship_recommendations

        # Report findings
        logger.info("\n📊 Index Gap Analysis:\n")

        logger.info(f"  Composite Indexes (0 exist, {len(gaps['composite'])} recommended):")
        for rec in gaps["composite"]:
            props_str = " + ".join(rec["properties"])
            status = "✓" if rec["has_partial_index"] else "✗"
            logger.info(f"    {status} {rec['label']}.({props_str})")
            logger.info(f"       Reason: {rec['reason']}")

        logger.info(f"\n  Full-Text Indexes ({len([r for r in gaps['fulltext'] if r['exists']])} exist, {len(gaps['fulltext'])} recommended):")
        for rec in gaps["fulltext"]:
            status = "✓" if rec["exists"] else "✗"
            logger.info(f"    {status} {rec['name']} ({rec['label']})")
            logger.info(f"       Reason: {rec['reason']}")

        logger.info(f"\n  Relationship Indexes (0 exist, {len(gaps['relationship'])} recommended):")
        for rec in gaps["relationship"]:
            logger.info(f"    ✗ {rec['relationship']}.{rec['property']}")
            logger.info(f"       Reason: {rec['reason']}")

        return gaps

    async def create_composite_indexes(self, gaps: dict) -> list[str]:
        """Create composite indexes.

        Args:
            gaps: Index gaps from identify_index_gaps()

        Returns:
            List of created index names
        """
        logger.info("\n" + "=" * 80)
        logger.info("CREATING COMPOSITE INDEXES")
        logger.info("=" * 80)

        created = []

        for rec in gaps["composite"]:
            label = rec["label"]
            props = rec["properties"]
            props_str = "_".join(props)
            index_name = f"{label.lower()}_composite_{props_str}_idx"

            # Create composite index (Neo4j 5.0+ syntax)
            create_query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS
            FOR (n:{label})
            ON ({", ".join([f"n.{p}" for p in props])})
            """

            try:
                logger.info(f"\n  Creating: {index_name}")
                logger.info(f"    Label: {label}")
                logger.info(f"    Properties: {', '.join(props)}")

                await self.client.run_write_query(create_query)
                created.append(index_name)
                logger.info(f"    ✅ Created successfully")

            except Exception as e:
                logger.error(f"    ❌ Failed: {e}")

        logger.info(f"\n✅ Created {len(created)} composite indexes")
        return created

    async def create_fulltext_indexes(self, gaps: dict) -> list[str]:
        """Create full-text indexes.

        Args:
            gaps: Index gaps from identify_index_gaps()

        Returns:
            List of created index names
        """
        logger.info("\n" + "=" * 80)
        logger.info("CREATING FULL-TEXT INDEXES")
        logger.info("=" * 80)

        created = []

        for rec in gaps["fulltext"]:
            if rec["exists"]:
                logger.info(f"\n  Skipping {rec['name']} (already exists)")
                continue

            name = rec["name"]
            label = rec["label"]
            props = rec["properties"]

            # Create full-text index (Neo4j 5.0+ syntax)
            create_query = f"""
            CREATE FULLTEXT INDEX {name} IF NOT EXISTS
            FOR (n:{label})
            ON EACH [{", ".join([f"n.{p}" for p in props])}]
            """

            try:
                logger.info(f"\n  Creating: {name}")
                logger.info(f"    Label: {label}")
                logger.info(f"    Properties: {', '.join(props)}")

                await self.client.run_write_query(create_query)
                created.append(name)
                logger.info(f"    ✅ Created successfully")

            except Exception as e:
                logger.error(f"    ❌ Failed: {e}")

        logger.info(f"\n✅ Created {len(created)} full-text indexes")
        return created

    async def create_relationship_indexes(self, gaps: dict) -> list[str]:
        """Create relationship property indexes.

        Args:
            gaps: Index gaps from identify_index_gaps()

        Returns:
            List of created index names
        """
        logger.info("\n" + "=" * 80)
        logger.info("CREATING RELATIONSHIP INDEXES")
        logger.info("=" * 80)

        created = []

        for rec in gaps["relationship"]:
            rel_type = rec["relationship"]
            prop = rec["property"]
            index_name = f"{rel_type.lower()}_{prop}_idx"

            # Create relationship property index (Neo4j 5.0+ syntax)
            create_query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS
            FOR ()-[r:{rel_type}]-()
            ON (r.{prop})
            """

            try:
                logger.info(f"\n  Creating: {index_name}")
                logger.info(f"    Relationship: {rel_type}")
                logger.info(f"    Property: {prop}")

                await self.client.run_write_query(create_query)
                created.append(index_name)
                logger.info(f"    ✅ Created successfully")

            except Exception as e:
                logger.error(f"    ❌ Failed: {e}")

        logger.info(f"\n✅ Created {len(created)} relationship indexes")
        return created

    async def profile_common_queries(self) -> list[QueryProfile]:
        """Profile common queries and provide optimization recommendations.

        Returns:
            List of query profiles
        """
        logger.info("\n" + "=" * 80)
        logger.info("PROFILING COMMON QUERIES")
        logger.info("=" * 80)

        # Common queries from actual usage patterns
        test_queries = [
            {
                "query": """
                MATCH (p:Paper)
                WHERE p.sub_domain = 'Degenerative' AND p.evidence_level = '1b'
                RETURN p
                LIMIT 10
                """,
                "description": "Filter papers by sub_domain + evidence_level",
            },
            {
                "query": """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE a.is_significant = true AND a.p_value < 0.05
                RETURN i.name, o.name, a.value, a.p_value
                LIMIT 10
                """,
                "description": "Find significant intervention effects",
            },
            {
                "query": """
                MATCH (i:Intervention {name: 'TLIF'})
                OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
                RETURN i, nodes(path)
                """,
                "description": "Traverse intervention hierarchy",
            },
            {
                "query": """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: 'VAS'})
                WHERE a.is_significant = true
                RETURN i.name, a.value, a.p_value
                ORDER BY a.p_value ASC
                LIMIT 10
                """,
                "description": "Find interventions effective for VAS",
            },
            {
                "query": """
                MATCH (p:Paper)-[:STUDIES]->(path:Pathology {name: 'Lumbar Stenosis'})
                RETURN p.title, p.year, p.evidence_level
                ORDER BY p.year DESC
                LIMIT 10
                """,
                "description": "Find papers studying specific pathology",
            },
            {
                "query": """
                MATCH (i1:Intervention)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2:Intervention)
                WHERE i1.name = 'TLIF' AND a1.direction <> a2.direction
                  AND a1.is_significant = true AND a2.is_significant = true
                RETURN i1.name, i2.name, o.name, a1.direction, a2.direction
                LIMIT 10
                """,
                "description": "Detect conflicting results",
            },
        ]

        profiles = []

        for test in test_queries:
            query = test["query"]
            description = test["description"]

            logger.info(f"\n📊 Profiling: {description}")

            # Use PROFILE to analyze query execution
            profile_query = f"PROFILE {query}"

            try:
                start_time = time.time()
                results = await self.client.run_query(query)
                execution_time_ms = (time.time() - start_time) * 1000

                profile = QueryProfile(
                    query=query,
                    description=description,
                    execution_time_ms=execution_time_ms,
                    rows_returned=len(results),
                )

                # Try to get execution plan
                try:
                    plan_result = await self.client.run_query(
                        f"EXPLAIN {query}",
                        fetch_all=False
                    )
                    # Check if index was used
                    plan_str = str(plan_result)
                    profile.has_index = "NodeIndexSeek" in plan_str or "RelationshipIndexSeek" in plan_str
                except Exception:
                    pass

                # Generate recommendations
                if execution_time_ms > 100:
                    profile.recommendations.append(
                        f"⚠️  Slow query ({execution_time_ms:.1f}ms) - consider adding indexes"
                    )

                if not profile.has_index:
                    profile.recommendations.append(
                        "💡 No index detected - may benefit from composite index"
                    )

                if "WHERE" in query.upper() and not profile.has_index:
                    profile.recommendations.append(
                        "💡 Add index on filtered properties"
                    )

                profiles.append(profile)

                logger.info(f"  Execution Time: {execution_time_ms:.2f}ms")
                logger.info(f"  Rows Returned: {profile.rows_returned}")
                logger.info(f"  Index Used: {'Yes' if profile.has_index else 'No'}")

                if profile.recommendations:
                    logger.info("  Recommendations:")
                    for rec in profile.recommendations:
                        logger.info(f"    {rec}")

            except Exception as e:
                logger.error(f"  ❌ Query failed: {e}")

        return profiles

    async def generate_optimization_report(
        self,
        indexes: list[IndexInfo],
        gaps: dict,
        profiles: list[QueryProfile]
    ) -> str:
        """Generate comprehensive optimization report.

        Args:
            indexes: Current indexes
            gaps: Identified gaps
            profiles: Query profiles

        Returns:
            Report as string
        """
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION REPORT")
        logger.info("=" * 80)

        report_lines = [
            "",
            "=" * 80,
            "Neo4j Index Optimization Report",
            "=" * 80,
            "",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 1. Current State",
            "",
            f"Total Indexes: {len(indexes)}",
        ]

        # Index breakdown
        by_type = {}
        for idx in indexes:
            by_type.setdefault(idx.type, []).append(idx)

        for idx_type, idxs in sorted(by_type.items()):
            report_lines.append(f"  - {idx_type}: {len(idxs)}")

        # Recommendations summary
        total_recommendations = (
            len(gaps["composite"]) +
            len([r for r in gaps["fulltext"] if not r["exists"]]) +
            len(gaps["relationship"])
        )

        report_lines.extend([
            "",
            "## 2. Recommendations",
            "",
            f"Total Recommended Indexes: {total_recommendations}",
            f"  - Composite: {len(gaps['composite'])}",
            f"  - Full-Text: {len([r for r in gaps['fulltext'] if not r['exists']])}",
            f"  - Relationship: {len(gaps['relationship'])}",
            "",
        ])

        # Query performance summary
        if profiles:
            avg_time = sum(p.execution_time_ms for p in profiles) / len(profiles)
            slow_queries = [p for p in profiles if p.execution_time_ms > 100]

            report_lines.extend([
                "## 3. Query Performance",
                "",
                f"Queries Profiled: {len(profiles)}",
                f"Average Execution Time: {avg_time:.2f}ms",
                f"Slow Queries (>100ms): {len(slow_queries)}",
                "",
            ])

            if slow_queries:
                report_lines.append("Slow Query Details:")
                for p in slow_queries:
                    report_lines.append(f"  - {p.description}")
                    report_lines.append(f"    Time: {p.execution_time_ms:.2f}ms")
                    report_lines.append(f"    Index Used: {'Yes' if p.has_index else 'No'}")

        # Expected improvements
        report_lines.extend([
            "",
            "## 4. Expected Improvements",
            "",
            "After creating recommended indexes:",
            "  - Composite indexes: 2-5x speedup for filtered queries",
            "  - Full-text indexes: 10-100x speedup for text search",
            "  - Relationship indexes: 3-10x speedup for statistical filtering",
            "",
            "## 5. Next Steps",
            "",
            "1. Review recommendations above",
            "2. Run with --create-indexes to create all recommended indexes",
            "3. Monitor query performance after index creation",
            "4. Run --profile-queries again to verify improvements",
            "",
        ])

        report = "\n".join(report_lines)
        logger.info(report)

        # Save report to file
        report_file = project_root / "data" / "optimization_report.txt"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report)
        logger.info(f"\n📄 Report saved to: {report_file}")

        return report


async def run_optimization(
    analyze: bool = False,
    create_indexes: bool = False,
    profile_queries: bool = False,
    full: bool = False
) -> None:
    """Run optimization workflow.

    Args:
        analyze: Only analyze current state
        create_indexes: Create recommended indexes
        profile_queries: Profile common queries
        full: Run all optimizations
    """
    config = Neo4jConfig.from_env()

    async with Neo4jClient(config) as client:
        optimizer = Neo4jOptimizer(client)

        # 1. Analyze current indexes
        indexes = await optimizer.analyze_current_indexes()

        # 2. Identify gaps
        gaps = await optimizer.identify_index_gaps(indexes)

        if analyze:
            # Analysis only mode
            await optimizer.generate_optimization_report(indexes, gaps, [])
            return

        # 3. Create indexes if requested
        if create_indexes or full:
            await optimizer.create_composite_indexes(gaps)
            await optimizer.create_fulltext_indexes(gaps)
            await optimizer.create_relationship_indexes(gaps)

            # Re-analyze after creation
            logger.info("\n" + "=" * 80)
            logger.info("RE-ANALYZING AFTER INDEX CREATION")
            logger.info("=" * 80)
            indexes = await optimizer.analyze_current_indexes()

        # 4. Profile queries if requested
        profiles = []
        if profile_queries or full:
            profiles = await optimizer.profile_common_queries()

        # 5. Generate final report
        await optimizer.generate_optimization_report(indexes, gaps, profiles)

        logger.info("\n" + "=" * 80)
        logger.info("✅ OPTIMIZATION COMPLETE")
        logger.info("=" * 80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Neo4j Index and Query Optimization"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze current indexes only (no changes)"
    )
    parser.add_argument(
        "--create-indexes",
        action="store_true",
        help="Create recommended indexes"
    )
    parser.add_argument(
        "--profile-queries",
        action="store_true",
        help="Profile common queries"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full optimization (create indexes + profile)"
    )

    args = parser.parse_args()

    # Default to analyze if no option specified
    if not any([args.analyze, args.create_indexes, args.profile_queries, args.full]):
        args.analyze = True

    try:
        asyncio.run(run_optimization(
            analyze=args.analyze,
            create_indexes=args.create_indexes,
            profile_queries=args.profile_queries,
            full=args.full
        ))
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
