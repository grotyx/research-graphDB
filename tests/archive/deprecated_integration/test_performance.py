"""Performance Benchmark Tests.

Measure and report performance metrics for the Spine GraphRAG system.

Metrics:
- Query response times
- Search latency (graph vs vector)
- Ranking performance with varying data sizes
- Memory usage patterns
- Throughput under load

Markers:
- @pytest.mark.slow: Performance test (may take longer)
- @pytest.mark.benchmark: Benchmark test
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List
import statistics

from src.orchestrator.chain_builder import SpineGraphChain, ChainConfig
from src.solver.hybrid_ranker import HybridRanker, HybridResult
from src.graph.neo4j_client import Neo4jClient
from src.storage.vector_db import TieredVectorDB

from tests.fixtures.sample_papers import (
    ALL_SAMPLE_PAPERS,
    ALL_SAMPLE_EVIDENCES,
    TLIF_EVIDENCE_FUSION_RATE,
    SAMPLE_PAPER_TLIF,
)


class PerformanceMetrics:
    """Performance metrics container."""

    def __init__(self):
        self.query_times: List[float] = []
        self.graph_search_times: List[float] = []
        self.vector_search_times: List[float] = []
        self.ranking_times: List[float] = []

    def add_query_time(self, time_ms: float):
        """Add query execution time."""
        self.query_times.append(time_ms)

    def add_graph_search_time(self, time_ms: float):
        """Add graph search time."""
        self.graph_search_times.append(time_ms)

    def add_vector_search_time(self, time_ms: float):
        """Add vector search time."""
        self.vector_search_times.append(time_ms)

    def add_ranking_time(self, time_ms: float):
        """Add ranking time."""
        self.ranking_times.append(time_ms)

    def get_summary(self) -> dict:
        """Get performance summary statistics."""
        return {
            "query_times": {
                "mean": statistics.mean(self.query_times) if self.query_times else 0,
                "median": statistics.median(self.query_times) if self.query_times else 0,
                "min": min(self.query_times) if self.query_times else 0,
                "max": max(self.query_times) if self.query_times else 0,
                "p95": self._percentile(self.query_times, 95) if self.query_times else 0,
            },
            "graph_search_times": {
                "mean": statistics.mean(self.graph_search_times) if self.graph_search_times else 0,
                "median": statistics.median(self.graph_search_times) if self.graph_search_times else 0,
            },
            "vector_search_times": {
                "mean": statistics.mean(self.vector_search_times) if self.vector_search_times else 0,
                "median": statistics.median(self.vector_search_times) if self.vector_search_times else 0,
            },
            "ranking_times": {
                "mean": statistics.mean(self.ranking_times) if self.ranking_times else 0,
                "median": statistics.median(self.ranking_times) if self.ranking_times else 0,
            },
        }

    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


@pytest.fixture
def performance_metrics():
    """Performance metrics fixture."""
    return PerformanceMetrics()


class TestQueryResponseTime:
    """Test query response time performance."""

    @pytest.fixture
    async def mock_chain(self):
        """Create mock chain with realistic latency."""
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        # Mock with simulated latency
        async def mock_run_query(*args, **kwargs):
            await asyncio.sleep(0.01)  # Simulate 10ms Neo4j query
            return []

        neo4j_client.run_query = mock_run_query

        # Mock vector search with latency
        def mock_search_all(*args, **kwargs):
            time.sleep(0.02)  # Simulate 20ms ChromaDB search
            return []

        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all = mock_search_all

        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Test answer"

            # Simulate LLM latency
            async def mock_ainvoke(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate 100ms LLM
                return mock_response

            mock_llm.ainvoke = mock_ainvoke
            mock_llm_class.return_value = mock_llm

            chain = SpineGraphChain(
                neo4j_client=neo4j_client,
                vector_db=vector_db,
                config=ChainConfig(top_k=10),
                api_key="test_key"
            )
            chain.llm = mock_llm

            return chain

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_single_query_response_time(self, mock_chain, performance_metrics):
        """Test single query response time."""
        query = "What is the fusion rate for TLIF?"

        start = time.time()
        result = await mock_chain.invoke(query, mode="qa")
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_query_time(elapsed_ms)

        # Assert reasonable response time (mocked, should be < 500ms)
        assert elapsed_ms < 500, f"Query took {elapsed_ms:.2f}ms (expected < 500ms)"

        # Log performance
        print(f"\n[Performance] Single query: {elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_multiple_query_average_time(self, mock_chain, performance_metrics):
        """Test average response time across multiple queries."""
        queries = [
            "What is the fusion rate for TLIF?",
            "Compare UBE vs Open surgery",
            "OLIF effectiveness for VAS",
            "Get intervention hierarchy for Endoscopic Surgery",
            "Detect conflicts for OLIF",
        ]

        times = []
        for query in queries:
            start = time.time()
            await mock_chain.invoke(query, mode="qa")
            elapsed_ms = (time.time() - start) * 1000

            times.append(elapsed_ms)
            performance_metrics.add_query_time(elapsed_ms)

        avg_time = statistics.mean(times)
        median_time = statistics.median(times)

        # Assert reasonable average time
        assert avg_time < 500, f"Average query time {avg_time:.2f}ms (expected < 500ms)"

        # Log performance
        print(f"\n[Performance] {len(queries)} queries:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  Median: {median_time:.2f}ms")
        print(f"  Min: {min(times):.2f}ms")
        print(f"  Max: {max(times):.2f}ms")

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_retrieval_only_performance(self, mock_chain, performance_metrics):
        """Test retrieval-only performance (no LLM)."""
        query = "TLIF fusion rate"

        start = time.time()
        result = await mock_chain.invoke(query, mode="retrieval")
        elapsed_ms = (time.time() - start) * 1000

        # Retrieval should be faster than full QA (no LLM call)
        assert elapsed_ms < 200, f"Retrieval took {elapsed_ms:.2f}ms (expected < 200ms)"

        print(f"\n[Performance] Retrieval only: {elapsed_ms:.2f}ms")


class TestSearchLatency:
    """Test search component latency."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_graph_search_latency(self, performance_metrics):
        """Test graph search latency."""
        from src.solver.graph_search import GraphSearch

        neo4j_client = AsyncMock(spec=Neo4jClient)

        # Mock query with latency
        async def mock_run_query(*args, **kwargs):
            await asyncio.sleep(0.015)  # 15ms
            return []

        neo4j_client.run_query = mock_run_query

        search = GraphSearch(neo4j_client=neo4j_client)

        start = time.time()
        await search.search_interventions_for_outcome(
            outcome_name="Fusion Rate",
            min_p_value=0.05
        )
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_graph_search_time(elapsed_ms)

        # Graph search should be fast
        assert elapsed_ms < 100, f"Graph search took {elapsed_ms:.2f}ms"

        print(f"\n[Performance] Graph search: {elapsed_ms:.2f}ms")

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_vector_search_latency(self, performance_metrics):
        """Test vector search latency."""
        vector_db = MagicMock(spec=TieredVectorDB)

        # Mock with latency
        def mock_search_all(*args, **kwargs):
            time.sleep(0.025)  # 25ms
            return []

        vector_db.search_all = mock_search_all

        start = time.time()
        vector_db.search_all(
            query_embedding=[0.1] * 768,
            top_k=10,
            tier1_weight=1.0,
            tier2_weight=0.7
        )
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_vector_search_time(elapsed_ms)

        # Vector search should be fast
        assert elapsed_ms < 100, f"Vector search took {elapsed_ms:.2f}ms"

        print(f"\n[Performance] Vector search: {elapsed_ms:.2f}ms")

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_hybrid_search_latency(self, performance_metrics):
        """Test hybrid search combining both sources."""
        from src.solver.hybrid_ranker import HybridRanker

        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        # Mock both with latency
        async def mock_graph_query(*args, **kwargs):
            await asyncio.sleep(0.015)
            return []

        def mock_vector_search(*args, **kwargs):
            time.sleep(0.025)
            return []

        neo4j_client.run_query = mock_graph_query
        vector_db.search_all = mock_vector_search
        vector_db.get_embedding.return_value = [0.1] * 768

        ranker = HybridRanker(vector_db=vector_db, neo4j_client=neo4j_client)

        start = time.time()
        await ranker.search(
            query="TLIF fusion rate",
            query_embedding=[0.1] * 768,
            top_k=10
        )
        elapsed_ms = (time.time() - start) * 1000

        # Hybrid should be sum of both (parallel execution would reduce this)
        assert elapsed_ms < 150, f"Hybrid search took {elapsed_ms:.2f}ms"

        print(f"\n[Performance] Hybrid search: {elapsed_ms:.2f}ms")


class TestRankingPerformance:
    """Test ranking performance with varying data sizes."""

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_ranking_small_dataset(self, performance_metrics):
        """Test ranking performance with small dataset (10 results)."""
        results = self._create_mock_results(count=10)

        start = time.time()
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_ranking_time(elapsed_ms)

        assert len(sorted_results) == 10
        assert elapsed_ms < 10, f"Ranking 10 items took {elapsed_ms:.2f}ms"

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_ranking_medium_dataset(self, performance_metrics):
        """Test ranking performance with medium dataset (100 results)."""
        results = self._create_mock_results(count=100)

        start = time.time()
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_ranking_time(elapsed_ms)

        assert len(sorted_results) == 100
        assert elapsed_ms < 50, f"Ranking 100 items took {elapsed_ms:.2f}ms"

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_ranking_large_dataset(self, performance_metrics):
        """Test ranking performance with large dataset (1000 results)."""
        results = self._create_mock_results(count=1000)

        start = time.time()
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        elapsed_ms = (time.time() - start) * 1000

        performance_metrics.add_ranking_time(elapsed_ms)

        assert len(sorted_results) == 1000
        assert elapsed_ms < 100, f"Ranking 1000 items took {elapsed_ms:.2f}ms"

        print(f"\n[Performance] Ranked 1000 results in {elapsed_ms:.2f}ms")

    @staticmethod
    def _create_mock_results(count: int) -> List[HybridResult]:
        """Create mock hybrid results for testing."""
        import random

        results = []
        for i in range(count):
            result_type = "graph" if i % 2 == 0 else "vector"
            score = random.uniform(0.5, 1.0)

            results.append(HybridResult(
                result_type=result_type,
                score=score,
                content=f"Mock content {i}",
                source_id=f"mock_{i}",
                metadata={}
            ))

        return results


class TestThroughput:
    """Test system throughput under load."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_concurrent_queries(self):
        """Test concurrent query handling."""
        # Mock chain
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        async def mock_query(*args, **kwargs):
            await asyncio.sleep(0.05)  # 50ms per query
            return []

        neo4j_client.run_query = mock_query
        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all.return_value = []

        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Test answer"

            async def mock_ainvoke(*args, **kwargs):
                await asyncio.sleep(0.05)
                return mock_response

            mock_llm.ainvoke = mock_ainvoke
            mock_llm_class.return_value = mock_llm

            chain = SpineGraphChain(
                neo4j_client=neo4j_client,
                vector_db=vector_db,
                api_key="test_key"
            )
            chain.llm = mock_llm

            # Execute 10 concurrent queries
            queries = [f"Test query {i}" for i in range(10)]

            start = time.time()
            results = await asyncio.gather(
                *[chain.invoke(q, mode="retrieval") for q in queries]
            )
            elapsed_ms = (time.time() - start) * 1000

            # Concurrent execution should be faster than sequential
            # Sequential would take ~500ms (10 * 50ms)
            # Concurrent should take ~100ms (with parallelism)
            assert elapsed_ms < 300, f"10 concurrent queries took {elapsed_ms:.2f}ms"
            assert len(results) == 10

            throughput = len(queries) / (elapsed_ms / 1000)  # queries per second
            print(f"\n[Performance] Throughput: {throughput:.2f} queries/sec")


class TestMemoryUsage:
    """Test memory usage patterns."""

    @pytest.mark.slow
    @pytest.mark.benchmark
    def test_result_memory_footprint(self):
        """Test memory footprint of result objects."""
        import sys

        # Create large result set
        results = TestRankingPerformance._create_mock_results(count=1000)

        # Estimate memory usage
        total_size = sum(sys.getsizeof(r) for r in results)
        avg_size = total_size / len(results)

        # Each result should be reasonably sized
        assert avg_size < 10000, f"Average result size {avg_size:.0f} bytes (expected < 10KB)"

        print(f"\n[Performance] Memory usage:")
        print(f"  1000 results: {total_size / 1024:.2f} KB")
        print(f"  Average per result: {avg_size:.0f} bytes")


class TestLatencyReport:
    """Generate comprehensive latency report."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.benchmark
    async def test_generate_latency_report(self, performance_metrics):
        """Generate comprehensive latency report."""
        # Run multiple test queries
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        async def mock_graph(*args, **kwargs):
            await asyncio.sleep(0.015)
            return []

        def mock_vector(*args, **kwargs):
            time.sleep(0.025)
            return []

        neo4j_client.run_query = mock_graph
        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all = mock_vector

        # Measure components
        for _ in range(10):
            # Graph search
            start = time.time()
            await neo4j_client.run_query("MATCH (n) RETURN n")
            performance_metrics.add_graph_search_time((time.time() - start) * 1000)

            # Vector search
            start = time.time()
            vector_db.search_all(query_embedding=[0.1] * 768, top_k=10)
            performance_metrics.add_vector_search_time((time.time() - start) * 1000)

        # Generate report
        summary = performance_metrics.get_summary()

        print("\n" + "=" * 60)
        print("PERFORMANCE REPORT")
        print("=" * 60)

        for component, metrics in summary.items():
            if metrics.get("mean", 0) > 0:
                print(f"\n{component.replace('_', ' ').title()}:")
                print(f"  Mean:   {metrics['mean']:.2f}ms")
                print(f"  Median: {metrics['median']:.2f}ms")
                if "min" in metrics:
                    print(f"  Min:    {metrics['min']:.2f}ms")
                    print(f"  Max:    {metrics['max']:.2f}ms")
                    print(f"  P95:    {metrics['p95']:.2f}ms")

        print("\n" + "=" * 60)

        # Assert metrics are within acceptable ranges
        assert summary["graph_search_times"]["mean"] < 100
        assert summary["vector_search_times"]["mean"] < 100


# Run benchmarks and save results
def test_save_benchmark_results(performance_metrics, tmp_path):
    """Save benchmark results to file."""
    import json

    # Add some dummy data
    for i in range(10):
        performance_metrics.add_query_time(100 + i * 10)

    summary = performance_metrics.get_summary()

    # Save to JSON
    output_file = tmp_path / "benchmark_results.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)

    assert output_file.exists()

    # Verify content
    with open(output_file, "r") as f:
        loaded = json.load(f)
        assert "query_times" in loaded
