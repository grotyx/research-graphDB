"""Benchmark runner for Spine GraphRAG evaluation.

Loads gold standard questions, runs all baselines, and computes metrics.

Usage:
    python -m evaluation.benchmark --baselines B1,B2,B4 --top-k 20
    python -m evaluation.benchmark --baselines all --output results/run_001.json
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from evaluation.metrics import (
    AggregateMetrics,
    RetrievalMetrics,
    aggregate_metrics,
    evaluate_single_query,
)
from evaluation.baselines import (
    BaselineResult,
    BaselineSearch,
    GraphRAGSearch,
    KeywordSearch,
    LLMDirectSearch,
    VectorOnlySearch,
)

logger = logging.getLogger(__name__)

GOLD_STANDARD_DIR = Path(__file__).parent / "gold_standard"
RESULTS_DIR = Path(__file__).parent / "results"


# ============================================================================
# Gold Standard Data
# ============================================================================

def load_questions(path: Optional[Path] = None) -> list[dict]:
    """Load gold standard questions from JSON file."""
    if path is None:
        path = GOLD_STANDARD_DIR / "questions.json"

    if not path.exists():
        logger.error("Gold standard file not found: %s", path)
        return []

    with open(path) as f:
        data = json.load(f)

    questions = data.get("questions", data) if isinstance(data, dict) else data
    logger.info("Loaded %d gold standard questions", len(questions))
    return questions


def load_answers(path: Optional[Path] = None) -> dict[str, dict]:
    """Load expert-annotated answers.

    Returns:
        Dict mapping query_id → {
            "relevant_paper_ids": [...],
            "relevance_scores": {paper_id: score},  # optional graded
        }
    """
    if path is None:
        path = GOLD_STANDARD_DIR / "answers.json"

    if not path.exists():
        logger.error("Answers file not found: %s", path)
        return {}

    with open(path) as f:
        data = json.load(f)

    answers = data.get("answers", data) if isinstance(data, dict) else data
    if isinstance(answers, list):
        return {a["query_id"]: a for a in answers}
    return answers


# ============================================================================
# Benchmark Runner
# ============================================================================

async def run_benchmark(
    baselines: list[BaselineSearch],
    questions: list[dict],
    answers: dict[str, dict],
    top_k: int = 20,
) -> dict[str, AggregateMetrics]:
    """Run all baselines against all questions and compute metrics.

    Args:
        baselines: List of baseline search instances.
        questions: List of gold standard questions.
        answers: Expert-annotated answers keyed by query_id.
        top_k: Number of results to retrieve per query.

    Returns:
        Dict mapping baseline_name → AggregateMetrics.
    """
    all_results: dict[str, AggregateMetrics] = {}

    for baseline in baselines:
        logger.info("Running baseline: %s", baseline.name)
        per_query_metrics: list[RetrievalMetrics] = []
        query_domains: dict[str, str] = {}

        for q in questions:
            qid = q["id"]
            query_text = q["question"]
            domain = q.get("domain", "unknown")
            query_domains[qid] = domain

            # Get gold standard answer
            answer = answers.get(qid)
            if not answer:
                logger.warning("No answer for query %s, skipping", qid)
                continue

            relevant_ids = set(answer.get("relevant_paper_ids", []))
            relevance_scores = answer.get("relevance_scores")

            # Run baseline search
            try:
                results = await baseline.search(query_text, top_k=top_k)
            except Exception as e:
                logger.error("Baseline %s failed on query %s: %s", baseline.name, qid, e)
                results = []

            # Extract result data
            retrieved_ids = [r.paper_id for r in results]
            evidence_levels = [r.evidence_level for r in results]

            # Compute metrics
            metrics = evaluate_single_query(
                query_id=qid,
                retrieved_ids=retrieved_ids,
                relevant_ids=relevant_ids,
                evidence_levels=evidence_levels,
                relevance_scores=relevance_scores,
            )
            per_query_metrics.append(metrics)

            logger.info(
                "  %s | P@10=%.3f R@10=%.3f NDCG@10=%.3f MRR=%.3f",
                qid, metrics.precision_at_10, metrics.recall_at_10,
                metrics.ndcg_at_10, metrics.mrr,
            )

        # Aggregate
        agg = aggregate_metrics(baseline.name, per_query_metrics, query_domains)
        all_results[baseline.name] = agg

        logger.info(
            "=== %s === P@10=%.4f R@10=%.4f NDCG@10=%.4f MRR=%.4f ELA=%.2f",
            baseline.name,
            agg.mean_precision_at_10, agg.mean_recall_at_10,
            agg.mean_ndcg_at_10, agg.mean_mrr, agg.mean_ela,
        )

    return all_results


def save_results(
    results: dict[str, AggregateMetrics],
    output_path: Optional[Path] = None,
) -> Path:
    """Save benchmark results to JSON file."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = RESULTS_DIR / f"benchmark_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "timestamp": datetime.now().isoformat(),
        "baselines": {
            name: agg.to_dict() for name, agg in results.items()
        },
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Results saved to %s", output_path)
    return output_path


def print_comparison_table(results: dict[str, AggregateMetrics]) -> str:
    """Print a formatted comparison table of all baselines."""
    header = f"{'Baseline':<16} {'P@5':>6} {'P@10':>6} {'R@10':>6} {'NDCG@10':>8} {'MRR':>6} {'ELA':>6} {'Top5_EL':>8}"
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for name, agg in results.items():
        d = agg.to_dict()
        line = (
            f"{name:<16} "
            f"{d['P@5']:>6.4f} "
            f"{d['P@10']:>6.4f} "
            f"{d['R@10']:>6.4f} "
            f"{d['NDCG@10']:>8.4f} "
            f"{d['MRR']:>6.4f} "
            f"{d['ELA']:>6.2f} "
            f"{d['Top5_EL']:>8.2f}"
        )
        lines.append(line)

    lines.append(sep)
    table = "\n".join(lines)
    print(table)
    return table


# ============================================================================
# CLI Entry Point
# ============================================================================

async def main():
    """CLI entry point for running benchmarks."""
    import argparse

    parser = argparse.ArgumentParser(description="Spine GraphRAG Benchmark Runner")
    parser.add_argument(
        "--baselines", type=str, default="B1,B2,B4",
        help="Comma-separated baseline names: B1,B2,B3,B4 or 'all'",
    )
    parser.add_argument("--top-k", type=int, default=20, help="Top-K results per query")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--questions", type=str, help="Path to questions JSON")
    parser.add_argument("--answers", type=str, help="Path to answers JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Load data
    questions_path = Path(args.questions) if args.questions else None
    answers_path = Path(args.answers) if args.answers else None
    questions = load_questions(questions_path)
    answers = load_answers(answers_path)

    if not questions or not answers:
        logger.error("No questions or answers loaded. Exiting.")
        sys.exit(1)

    # Initialize clients
    from core.config import get_config
    from graph.neo4j_client import Neo4jClient
    from core.embedding import EmbeddingClient

    config = get_config()
    neo4j_client = Neo4jClient(config)
    await neo4j_client.__aenter__()

    embedding_client = EmbeddingClient(config)

    # Build baselines
    baseline_names = (
        {"B1", "B2", "B3", "B4"}
        if args.baselines.lower() == "all"
        else set(args.baselines.upper().split(","))
    )

    baselines: list[BaselineSearch] = []
    if "B1" in baseline_names:
        baselines.append(KeywordSearch(neo4j_client))
    if "B2" in baseline_names:
        baselines.append(VectorOnlySearch(neo4j_client, embedding_client))
    if "B3" in baseline_names:
        from llm import LLMClient
        llm_client = LLMClient(config)
        baselines.append(LLMDirectSearch(llm_client, neo4j_client))
    if "B4" in baseline_names:
        baselines.append(GraphRAGSearch(neo4j_client, embedding_client))

    try:
        # Run benchmark
        results = await run_benchmark(baselines, questions, answers, args.top_k)

        # Print and save
        print_comparison_table(results)
        output_path = Path(args.output) if args.output else None
        save_results(results, output_path)
    finally:
        await neo4j_client.__aexit__(None, None, None)
        for b in baselines:
            await b.close()


if __name__ == "__main__":
    asyncio.run(main())
