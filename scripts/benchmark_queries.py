#!/usr/bin/env python3
"""Neo4j Query Performance Benchmark Script.

This script benchmarks common query patterns before and after optimization:
1. Hierarchy traversal (IS_A relationships)
2. Evidence search (AFFECTS with statistical filtering)
3. Conflict detection (contradictory findings)
4. Paper filtering (composite properties)
5. Text search (full-text indexes)

Usage:
    python scripts/benchmark_queries.py                    # Run benchmark
    python scripts/benchmark_queries.py --iterations 10    # More iterations for accuracy
    python scripts/benchmark_queries.py --compare before_results.json  # Compare with previous run
"""

import asyncio
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from statistics import mean, median, stdev
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_file = project_root / '.env'
load_dotenv(env_file)

from src.graph.neo4j_client import Neo4jClient, Neo4jConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class QueryBenchmark:
    """Single query benchmark result."""
    name: str
    category: str
    query: str
    iterations: int = 5
    execution_times_ms: list[float] = field(default_factory=list)
    rows_returned: list[int] = field(default_factory=list)

    @property
    def mean_time_ms(self) -> float:
        """Average execution time."""
        return mean(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def median_time_ms(self) -> float:
        """Median execution time."""
        return median(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def stddev_ms(self) -> float:
        """Standard deviation of execution time."""
        return stdev(self.execution_times_ms) if len(self.execution_times_ms) > 1 else 0.0

    @property
    def min_time_ms(self) -> float:
        """Minimum execution time."""
        return min(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def max_time_ms(self) -> float:
        """Maximum execution time."""
        return max(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def mean_rows(self) -> float:
        """Average rows returned."""
        return mean(self.rows_returned) if self.rows_returned else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "category": self.category,
            "query": self.query,
            "iterations": self.iterations,
            "mean_time_ms": round(self.mean_time_ms, 2),
            "median_time_ms": round(self.median_time_ms, 2),
            "stddev_ms": round(self.stddev_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2),
            "max_time_ms": round(self.max_time_ms, 2),
            "mean_rows": round(self.mean_rows, 1),
        }


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""
    timestamp: str
    iterations: int
    benchmarks: list[QueryBenchmark] = field(default_factory=list)

    @property
    def total_time_ms(self) -> float:
        """Total execution time across all benchmarks."""
        return sum(b.mean_time_ms for b in self.benchmarks)

    def get_by_category(self, category: str) -> list[QueryBenchmark]:
        """Get benchmarks by category."""
        return [b for b in self.benchmarks if b.category == category]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "iterations": self.iterations,
            "total_time_ms": round(self.total_time_ms, 2),
            "benchmarks": [b.to_dict() for b in self.benchmarks],
        }


class QueryBenchmarker:
    """Neo4j query performance benchmarker."""

    def __init__(self, client: Neo4jClient, iterations: int = 5):
        self.client = client
        self.iterations = iterations

    def _get_benchmark_queries(self) -> list[tuple[str, str, str]]:
        """Get list of (name, category, query) tuples to benchmark.

        Returns:
            List of benchmark queries
        """
        return [
            # Category: Hierarchy Traversal
            (
                "Hierarchy: TLIF Ancestors",
                "hierarchy",
                """
                MATCH (i:Intervention {name: 'TLIF'})
                OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
                RETURN i.name, [node IN nodes(path) | node.name] as hierarchy
                """
            ),
            (
                "Hierarchy: UBE Children",
                "hierarchy",
                """
                MATCH (parent:Intervention {name: 'Endoscopic Surgery'})<-[:IS_A*1..3]-(child:Intervention)
                RETURN child.name, child.full_name
                """
            ),
            (
                "Hierarchy: All Fusion Types",
                "hierarchy",
                """
                MATCH (parent:Intervention {name: 'Fusion Surgery'})<-[:IS_A*1..5]-(child:Intervention)
                RETURN child.name, child.category, child.approach
                ORDER BY child.name
                """
            ),

            # Category: Evidence Search
            (
                "Evidence: VAS Improvements",
                "evidence",
                """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: 'VAS'})
                WHERE a.is_significant = true AND a.direction = 'improved'
                RETURN i.name, a.value, a.p_value, a.source_paper_id
                ORDER BY a.p_value ASC
                LIMIT 20
                """
            ),
            (
                "Evidence: Significant Effects (p<0.05)",
                "evidence",
                """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE a.p_value < 0.05 AND a.is_significant = true
                RETURN i.name, o.name, a.value, a.p_value, a.direction
                LIMIT 50
                """
            ),
            (
                "Evidence: TLIF Outcomes",
                "evidence",
                """
                MATCH (i:Intervention {name: 'TLIF'})-[a:AFFECTS]->(o:Outcome)
                WHERE a.is_significant = true
                RETURN o.name, a.value, a.value_control, a.p_value, a.direction
                ORDER BY a.p_value ASC
                """
            ),

            # Category: Conflict Detection
            (
                "Conflict: OLIF Contradictions",
                "conflict",
                """
                MATCH (i1:Intervention {name: 'OLIF'})-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2:Intervention)
                WHERE a1.direction <> a2.direction
                  AND a1.is_significant = true
                  AND a2.is_significant = true
                RETURN i1.name, i2.name, o.name,
                       a1.direction as dir1, a2.direction as dir2,
                       a1.p_value as p1, a2.p_value as p2,
                       a1.source_paper_id as paper1, a2.source_paper_id as paper2
                """
            ),
            (
                "Conflict: All Contradictory Findings",
                "conflict",
                """
                MATCH (i:Intervention)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i:Intervention)
                WHERE a1.source_paper_id <> a2.source_paper_id
                  AND a1.direction <> a2.direction
                  AND a1.is_significant = true
                  AND a2.is_significant = true
                RETURN i.name, o.name,
                       count(*) as conflict_count
                GROUP BY i.name, o.name
                HAVING conflict_count > 1
                """
            ),

            # Category: Paper Filtering
            (
                "Papers: Degenerative RCTs",
                "paper_filter",
                """
                MATCH (p:Paper)
                WHERE p.sub_domain = 'Degenerative' AND p.evidence_level = '1b'
                RETURN p.paper_id, p.title, p.year, p.sample_size
                ORDER BY p.year DESC
                LIMIT 20
                """
            ),
            (
                "Papers: High-Quality Evidence (1a, 1b)",
                "paper_filter",
                """
                MATCH (p:Paper)
                WHERE p.evidence_level IN ['1a', '1b']
                RETURN p.paper_id, p.title, p.evidence_level, p.study_design
                ORDER BY p.year DESC
                LIMIT 50
                """
            ),
            (
                "Papers: Recent Deformity Studies",
                "paper_filter",
                """
                MATCH (p:Paper)
                WHERE p.sub_domain = 'Deformity' AND p.year >= 2020
                RETURN p.paper_id, p.title, p.year, p.evidence_level
                ORDER BY p.year DESC
                LIMIT 20
                """
            ),

            # Category: Relationship Traversal
            (
                "Relationships: Lumbar Stenosis Treatment Path",
                "relationship",
                """
                MATCH (p:Paper)-[:STUDIES]->(path:Pathology {name: 'Lumbar Stenosis'})
                MATCH (p)-[:INVESTIGATES]->(i:Intervention)
                MATCH (i)-[a:AFFECTS]->(o:Outcome)
                WHERE a.is_significant = true
                RETURN p.title, i.name, o.name, a.value, a.p_value
                LIMIT 20
                """
            ),
            (
                "Relationships: Paper Citation Network",
                "relationship",
                """
                MATCH (p:Paper)-[r:CITES|SUPPORTS|CONTRADICTS]->(other:Paper)
                RETURN type(r) as relation_type,
                       p.paper_id as source,
                       other.paper_id as target,
                       r.confidence as confidence
                LIMIT 50
                """
            ),

            # Category: Aggregate Queries
            (
                "Aggregate: Intervention Evidence Counts",
                "aggregate",
                """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE a.is_significant = true
                RETURN i.name,
                       count(DISTINCT o.name) as outcome_count,
                       count(*) as total_evidences,
                       avg(a.p_value) as avg_p_value
                ORDER BY total_evidences DESC
                LIMIT 20
                """
            ),
            (
                "Aggregate: Papers by Sub-domain",
                "aggregate",
                """
                MATCH (p:Paper)
                RETURN p.sub_domain,
                       count(*) as paper_count,
                       avg(p.sample_size) as avg_sample_size,
                       min(p.year) as earliest_year,
                       max(p.year) as latest_year
                GROUP BY p.sub_domain
                ORDER BY paper_count DESC
                """
            ),
        ]

    async def run_benchmark(self, name: str, category: str, query: str) -> QueryBenchmark:
        """Run single query benchmark.

        Args:
            name: Benchmark name
            category: Category
            query: Cypher query

        Returns:
            Benchmark result
        """
        benchmark = QueryBenchmark(
            name=name,
            category=category,
            query=query.strip(),
            iterations=self.iterations
        )

        logger.info(f"\n  Running: {name}")

        for i in range(self.iterations):
            try:
                start_time = time.perf_counter()
                results = await self.client.run_query(query)
                end_time = time.perf_counter()

                execution_time_ms = (end_time - start_time) * 1000
                benchmark.execution_times_ms.append(execution_time_ms)
                benchmark.rows_returned.append(len(results))

            except Exception as e:
                logger.error(f"    Iteration {i+1} failed: {e}")
                # Add large penalty for failures
                benchmark.execution_times_ms.append(999999.0)
                benchmark.rows_returned.append(0)

        logger.info(f"    Mean: {benchmark.mean_time_ms:.2f}ms")
        logger.info(f"    Median: {benchmark.median_time_ms:.2f}ms")
        logger.info(f"    Range: {benchmark.min_time_ms:.2f}-{benchmark.max_time_ms:.2f}ms")
        logger.info(f"    Rows: {benchmark.mean_rows:.1f}")

        return benchmark

    async def run_all_benchmarks(self) -> BenchmarkResults:
        """Run all benchmarks.

        Returns:
            Complete benchmark results
        """
        logger.info("=" * 80)
        logger.info("NEO4J QUERY PERFORMANCE BENCHMARK")
        logger.info("=" * 80)
        logger.info(f"\nIterations per query: {self.iterations}")

        results = BenchmarkResults(
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            iterations=self.iterations
        )

        queries = self._get_benchmark_queries()
        total = len(queries)

        for idx, (name, category, query) in enumerate(queries, 1):
            logger.info(f"\n[{idx}/{total}] Category: {category.upper()}")

            benchmark = await self.run_benchmark(name, category, query)
            results.benchmarks.append(benchmark)

        return results

    def print_summary(self, results: BenchmarkResults) -> None:
        """Print benchmark summary.

        Args:
            results: Benchmark results
        """
        logger.info("\n" + "=" * 80)
        logger.info("BENCHMARK SUMMARY")
        logger.info("=" * 80)

        # Overall stats
        logger.info(f"\nTimestamp: {results.timestamp}")
        logger.info(f"Total Queries: {len(results.benchmarks)}")
        logger.info(f"Iterations per Query: {results.iterations}")
        logger.info(f"Total Execution Time: {results.total_time_ms:.2f}ms")

        # By category
        categories = set(b.category for b in results.benchmarks)
        logger.info("\n📊 Performance by Category:\n")

        for category in sorted(categories):
            cat_benchmarks = results.get_by_category(category)
            cat_total_time = sum(b.mean_time_ms for b in cat_benchmarks)
            cat_avg_time = cat_total_time / len(cat_benchmarks)

            logger.info(f"  {category.upper()}:")
            logger.info(f"    Queries: {len(cat_benchmarks)}")
            logger.info(f"    Total Time: {cat_total_time:.2f}ms")
            logger.info(f"    Average Time: {cat_avg_time:.2f}ms")

        # Top 5 slowest queries
        logger.info("\n⚠️  Top 5 Slowest Queries:\n")
        slowest = sorted(results.benchmarks, key=lambda b: b.mean_time_ms, reverse=True)[:5]

        for idx, benchmark in enumerate(slowest, 1):
            logger.info(f"  {idx}. {benchmark.name}")
            logger.info(f"     Category: {benchmark.category}")
            logger.info(f"     Mean Time: {benchmark.mean_time_ms:.2f}ms")
            logger.info(f"     Stddev: {benchmark.stddev_ms:.2f}ms")

        # Top 5 fastest queries
        logger.info("\n✅ Top 5 Fastest Queries:\n")
        fastest = sorted(results.benchmarks, key=lambda b: b.mean_time_ms)[:5]

        for idx, benchmark in enumerate(fastest, 1):
            logger.info(f"  {idx}. {benchmark.name}")
            logger.info(f"     Category: {benchmark.category}")
            logger.info(f"     Mean Time: {benchmark.mean_time_ms:.2f}ms")

    def compare_results(
        self,
        before: BenchmarkResults,
        after: BenchmarkResults
    ) -> None:
        """Compare two benchmark results.

        Args:
            before: Results before optimization
            after: Results after optimization
        """
        logger.info("\n" + "=" * 80)
        logger.info("BENCHMARK COMPARISON")
        logger.info("=" * 80)

        logger.info(f"\nBefore: {before.timestamp}")
        logger.info(f"After:  {after.timestamp}")

        # Match benchmarks by name
        before_by_name = {b.name: b for b in before.benchmarks}
        after_by_name = {b.name: b for b in after.benchmarks}

        common_names = set(before_by_name.keys()) & set(after_by_name.keys())

        if not common_names:
            logger.warning("\nNo common benchmarks found for comparison")
            return

        logger.info(f"\nComparing {len(common_names)} common queries:\n")

        improvements = []
        regressions = []

        for name in sorted(common_names):
            before_b = before_by_name[name]
            after_b = after_by_name[name]

            time_diff_ms = after_b.mean_time_ms - before_b.mean_time_ms
            time_diff_pct = ((after_b.mean_time_ms / before_b.mean_time_ms) - 1) * 100

            if time_diff_ms < -1:  # Improved by >1ms
                improvements.append((name, before_b, after_b, time_diff_ms, time_diff_pct))
            elif time_diff_ms > 1:  # Regressed by >1ms
                regressions.append((name, before_b, after_b, time_diff_ms, time_diff_pct))

        # Print improvements
        logger.info("✅ Improvements:\n")
        if improvements:
            for name, before_b, after_b, diff_ms, diff_pct in sorted(improvements, key=lambda x: x[3]):
                logger.info(f"  {name}")
                logger.info(f"    Before: {before_b.mean_time_ms:.2f}ms")
                logger.info(f"    After:  {after_b.mean_time_ms:.2f}ms")
                logger.info(f"    Change: {diff_ms:.2f}ms ({diff_pct:+.1f}%)")
        else:
            logger.info("  (none)")

        # Print regressions
        logger.info("\n⚠️  Regressions:\n")
        if regressions:
            for name, before_b, after_b, diff_ms, diff_pct in sorted(regressions, key=lambda x: x[3], reverse=True):
                logger.info(f"  {name}")
                logger.info(f"    Before: {before_b.mean_time_ms:.2f}ms")
                logger.info(f"    After:  {after_b.mean_time_ms:.2f}ms")
                logger.info(f"    Change: {diff_ms:.2f}ms ({diff_pct:+.1f}%)")
        else:
            logger.info("  (none)")

        # Overall stats
        total_before = sum(before_by_name[n].mean_time_ms for n in common_names)
        total_after = sum(after_by_name[n].mean_time_ms for n in common_names)
        total_diff_pct = ((total_after / total_before) - 1) * 100

        logger.info("\n📊 Overall Performance:\n")
        logger.info(f"  Total Time Before: {total_before:.2f}ms")
        logger.info(f"  Total Time After:  {total_after:.2f}ms")
        logger.info(f"  Change: {total_after - total_before:.2f}ms ({total_diff_pct:+.1f}%)")


async def run_benchmark(iterations: int = 5, compare_file: Optional[str] = None) -> None:
    """Run benchmark workflow.

    Args:
        iterations: Number of iterations per query
        compare_file: Optional path to previous results for comparison
    """
    config = Neo4jConfig.from_env()

    async with Neo4jClient(config) as client:
        benchmarker = QueryBenchmarker(client, iterations=iterations)

        # Run benchmarks
        results = await benchmarker.run_all_benchmarks()

        # Print summary
        benchmarker.print_summary(results)

        # Save results
        output_file = project_root / "data" / "benchmark_results.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)

        logger.info(f"\n📄 Results saved to: {output_file}")

        # Compare with previous results if provided
        if compare_file:
            compare_path = Path(compare_file)
            if compare_path.exists():
                with open(compare_path, 'r') as f:
                    before_data = json.load(f)

                # Reconstruct BenchmarkResults from JSON
                before_results = BenchmarkResults(
                    timestamp=before_data["timestamp"],
                    iterations=before_data["iterations"]
                )
                for b_data in before_data["benchmarks"]:
                    # Reconstruct execution times (approximate from mean ± stddev)
                    mean_time = b_data["mean_time_ms"]
                    stddev = b_data.get("stddev_ms", 0)
                    exec_times = [mean_time] * before_data["iterations"]  # Simplified

                    benchmark = QueryBenchmark(
                        name=b_data["name"],
                        category=b_data["category"],
                        query=b_data["query"],
                        iterations=before_data["iterations"],
                        execution_times_ms=exec_times,
                        rows_returned=[int(b_data["mean_rows"])] * before_data["iterations"]
                    )
                    before_results.benchmarks.append(benchmark)

                benchmarker.compare_results(before_results, results)
            else:
                logger.warning(f"\nComparison file not found: {compare_file}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ BENCHMARK COMPLETE")
        logger.info("=" * 80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Neo4j Query Performance Benchmark"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per query (default: 5)"
    )
    parser.add_argument(
        "--compare",
        type=str,
        help="Path to previous results JSON for comparison"
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_benchmark(
            iterations=args.iterations,
            compare_file=args.compare
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
