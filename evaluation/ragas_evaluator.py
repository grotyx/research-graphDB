"""RAGAS-style End-to-End evaluation for Spine GraphRAG (ROADMAP 6.3).

Lightweight implementation of RAGAS metrics without the ragas pip package.
Uses Claude Haiku for claim extraction and relevance judgment via the
existing llm/ client.

Metrics:
  - Faithfulness: Does the answer stick to retrieved context?
  - Answer Relevancy: Is the answer relevant to the question?
  - Context Precision: Are retrieved chunks relevant and well-ranked?
  - Context Recall: Does context cover all ground truth aspects?
  - Citation Fidelity: Are paper_id citations correctly attributed? (domain-specific)

Usage:
    python -m evaluation.ragas_evaluator --question "..." --baseline B4
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ============================================================================
# LLM Protocol (for dependency injection / testing)
# ============================================================================

@runtime_checkable
class LLMProvider(Protocol):
    """Minimal LLM interface needed by RAGAS metrics."""

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> dict:
        ...

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> Any:
        ...


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class RAGASScores:
    """RAGAS evaluation scores for a single query."""

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    citation_fidelity: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "citation_fidelity": round(self.citation_fidelity, 4),
        }

    @property
    def overall(self) -> float:
        """Harmonic mean of the four core RAGAS metrics (excl. citation)."""
        scores = [
            self.faithfulness,
            self.answer_relevancy,
            self.context_precision,
            self.context_recall,
        ]
        positive = [s for s in scores if s > 0]
        if not positive:
            return 0.0
        return len(positive) / sum(1.0 / s for s in positive)


@dataclass
class RAGASResult:
    """Full RAGAS evaluation result for a query."""

    query_id: str
    question: str
    scores: RAGASScores = field(default_factory=RAGASScores)
    details: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Individual Metric Functions
# ============================================================================

async def faithfulness(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
    llm: LLMProvider,
) -> float:
    """Faithfulness: fraction of answer claims supported by the context.

    Steps:
        1. Extract atomic claims from the answer using LLM.
        2. For each claim, check if it is supported by any context chunk.
        3. Score = supported_claims / total_claims.

    Args:
        question: The original question.
        answer: The generated answer.
        contexts: List of retrieved context chunks.
        ground_truth: Not used for faithfulness, kept for API consistency.
        llm: LLM provider for claim extraction and verification.

    Returns:
        Float 0-1: fraction of claims supported by context.
    """
    if not answer or not answer.strip():
        return 0.0
    if not contexts:
        return 0.0

    # Step 1: Extract claims
    claims = await _extract_claims(answer, llm)
    if not claims:
        return 1.0  # No claims to verify = vacuously faithful

    # Step 2: Verify each claim against context
    context_text = "\n---\n".join(contexts)
    supported = await _verify_claims(claims, context_text, llm)

    return supported / len(claims)


async def answer_relevancy(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
    llm: LLMProvider,
) -> float:
    """Answer Relevancy: semantic similarity between answer and question.

    Steps:
        1. Generate N reverse questions from the answer.
        2. Compare each reverse question to the original question.
        3. Score = average similarity (LLM-judged 0-1).

    Args:
        question: The original question.
        answer: The generated answer.
        contexts: Not used directly.
        ground_truth: Not used.
        llm: LLM provider.

    Returns:
        Float 0-1: how relevant the answer is to the question.
    """
    if not answer or not answer.strip():
        return 0.0

    # Generate reverse questions
    reverse_questions = await _generate_reverse_questions(answer, llm, n=3)
    if not reverse_questions:
        return 0.0

    # Judge similarity of each reverse question to the original
    total_sim = 0.0
    for rq in reverse_questions:
        sim = await _judge_question_similarity(question, rq, llm)
        total_sim += sim

    return total_sim / len(reverse_questions)


async def context_precision(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
    llm: LLMProvider,
) -> float:
    """Context Precision: weighted precision of retrieved chunks.

    For each chunk, judge whether it is useful for answering the question.
    Higher-ranked useful chunks contribute more to the score.

    Score = sum(precision@k * is_relevant_k) / num_relevant
    where precision@k = relevant_in_top_k / k

    Args:
        question: The original question.
        answer: Not used directly.
        contexts: Ranked list of retrieved context chunks.
        ground_truth: The ground truth answer (used for relevance judgment).
        llm: LLM provider.

    Returns:
        Float 0-1: weighted precision score.
    """
    if not contexts:
        return 0.0

    # Judge relevance of each chunk
    relevance = await _judge_chunk_relevance(question, contexts, ground_truth, llm)
    if not any(relevance):
        return 0.0

    # Compute weighted precision (Average Precision style)
    num_relevant = 0
    cumulative_score = 0.0
    for k, is_rel in enumerate(relevance, 1):
        if is_rel:
            num_relevant += 1
            precision_at_k = num_relevant / k
            cumulative_score += precision_at_k

    if num_relevant == 0:
        return 0.0

    return cumulative_score / num_relevant


async def context_recall(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
    llm: LLMProvider,
) -> float:
    """Context Recall: fraction of ground truth aspects covered by context.

    Steps:
        1. Extract key aspects/facts from the ground truth answer.
        2. For each aspect, check if any context chunk covers it.
        3. Score = covered_aspects / total_aspects.

    Args:
        question: The original question.
        answer: Not used directly.
        contexts: Retrieved context chunks.
        ground_truth: The ground truth answer.
        llm: LLM provider.

    Returns:
        Float 0-1: fraction of ground truth aspects found in context.
    """
    if not ground_truth or not ground_truth.strip():
        return 0.0
    if not contexts:
        return 0.0

    # Extract aspects from ground truth
    aspects = await _extract_aspects(ground_truth, llm)
    if not aspects:
        return 1.0  # No aspects to check = vacuously complete

    # Check coverage
    context_text = "\n---\n".join(contexts)
    covered = await _check_aspect_coverage(aspects, context_text, llm)

    return covered / len(aspects)


def citation_fidelity(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
    context_paper_ids: Optional[list[str]] = None,
) -> float:
    """Citation Fidelity: fraction of cited paper_ids present in context.

    Domain-specific metric. Extracts paper_id references from the answer
    and checks if they appear in the context source paper_ids.

    This metric does NOT require LLM, it is purely string-matching.

    Args:
        question: Not used.
        answer: The generated answer, may contain paper_id references.
        contexts: Not used directly.
        ground_truth: Not used.
        context_paper_ids: List of paper_ids that the context chunks came from.

    Returns:
        Float 0-1: correct_citations / total_citations.
    """
    if not answer:
        return 0.0
    if context_paper_ids is None:
        context_paper_ids = []

    # Extract paper_id citations from answer
    cited_ids = _extract_paper_ids(answer)
    if not cited_ids:
        return 1.0  # No citations = vacuously correct

    source_set = set(context_paper_ids)
    correct = sum(1 for pid in cited_ids if pid in source_set)
    return correct / len(cited_ids)


# ============================================================================
# LLM Helper Functions
# ============================================================================

async def _extract_claims(answer: str, llm: LLMProvider) -> list[str]:
    """Extract atomic claims from an answer using LLM."""
    prompt = f"""Extract all atomic factual claims from the following answer.
Each claim should be a single, verifiable statement.

Answer:
{answer}

Return a JSON object with a "claims" key containing a list of claim strings.
Example: {{"claims": ["Claim 1", "Claim 2"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "claims": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["claims"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Extract factual claims.")
        return result.get("claims", [])
    except Exception as e:
        logger.warning("Claim extraction failed: %s", e)
        return []


async def _verify_claims(
    claims: list[str], context_text: str, llm: LLMProvider
) -> int:
    """Verify how many claims are supported by the context. Returns count."""
    prompt = f"""Given the context below, determine which of the following claims
are supported by the context.

Context:
{context_text}

Claims:
{_numbered_list(claims)}

For each claim, answer "supported" or "not_supported".
Return a JSON object with a "verdicts" key: a list of "supported" or "not_supported"
strings, one per claim in order.
Example: {{"verdicts": ["supported", "not_supported", "supported"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "verdicts": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["verdicts"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Verify claims against context.")
        verdicts = result.get("verdicts", [])
        return sum(1 for v in verdicts if "support" in v.lower() and "not" not in v.lower())
    except Exception as e:
        logger.warning("Claim verification failed: %s", e)
        return 0


async def _generate_reverse_questions(
    answer: str, llm: LLMProvider, n: int = 3
) -> list[str]:
    """Generate N questions that the answer could be answering."""
    prompt = f"""Given the following answer, generate {n} different questions
that this answer could be responding to. The questions should capture the
main topics and specifics of the answer.

Answer:
{answer}

Return a JSON object with a "questions" key containing a list of question strings.
Example: {{"questions": ["Question 1?", "Question 2?", "Question 3?"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["questions"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Generate reverse questions.")
        return result.get("questions", [])[:n]
    except Exception as e:
        logger.warning("Reverse question generation failed: %s", e)
        return []


async def _judge_question_similarity(
    original: str, reverse: str, llm: LLMProvider
) -> float:
    """Judge semantic similarity between two questions (0-1)."""
    prompt = f"""Rate the semantic similarity between these two questions on a scale of 0 to 1.
0 means completely different topics, 1 means they ask essentially the same thing.

Question A: {original}
Question B: {reverse}

Return a JSON object with a "similarity" key (float 0-1).
Example: {{"similarity": 0.85}}"""

    schema = {
        "type": "object",
        "properties": {
            "similarity": {"type": "number"},
        },
        "required": ["similarity"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Judge question similarity.")
        score = result.get("similarity", 0.0)
        return max(0.0, min(1.0, float(score)))
    except Exception as e:
        logger.warning("Similarity judgment failed: %s", e)
        return 0.0


async def _judge_chunk_relevance(
    question: str,
    contexts: list[str],
    ground_truth: str,
    llm: LLMProvider,
) -> list[bool]:
    """Judge relevance of each context chunk to the question."""
    chunks_text = ""
    for i, ctx in enumerate(contexts):
        chunks_text += f"\n[Chunk {i + 1}]: {ctx[:500]}\n"

    prompt = f"""Given the question and ground truth answer, determine if each
context chunk is useful for answering the question.

Question: {question}
Ground Truth: {ground_truth}

Context chunks:
{chunks_text}

For each chunk, answer "relevant" or "irrelevant".
Return a JSON object with a "relevance" key: a list of "relevant" or "irrelevant"
strings, one per chunk in order.
Example: {{"relevance": ["relevant", "irrelevant", "relevant"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "relevance": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["relevance"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Judge chunk relevance.")
        judgments = result.get("relevance", [])
        return [
            "relevant" in j.lower() and "irrelevant" not in j.lower()
            for j in judgments
        ]
    except Exception as e:
        logger.warning("Chunk relevance judgment failed: %s", e)
        return [False] * len(contexts)


async def _extract_aspects(ground_truth: str, llm: LLMProvider) -> list[str]:
    """Extract key factual aspects from the ground truth answer."""
    prompt = f"""Extract the key factual aspects from the following ground truth answer.
Each aspect should be a distinct piece of information that a complete answer should cover.

Ground Truth:
{ground_truth}

Return a JSON object with an "aspects" key containing a list of aspect strings.
Example: {{"aspects": ["Aspect 1", "Aspect 2"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "aspects": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["aspects"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Extract key aspects.")
        return result.get("aspects", [])
    except Exception as e:
        logger.warning("Aspect extraction failed: %s", e)
        return []


async def _check_aspect_coverage(
    aspects: list[str], context_text: str, llm: LLMProvider
) -> int:
    """Check how many aspects are covered by the context. Returns count."""
    prompt = f"""Given the context below, determine which of the following aspects
are covered (even partially) by the context.

Context:
{context_text}

Aspects:
{_numbered_list(aspects)}

For each aspect, answer "covered" or "not_covered".
Return a JSON object with a "coverage" key: a list of "covered" or "not_covered"
strings, one per aspect in order.
Example: {{"coverage": ["covered", "not_covered", "covered"]}}"""

    schema = {
        "type": "object",
        "properties": {
            "coverage": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["coverage"],
    }

    try:
        result = await llm.generate_json(prompt, schema, system="Check aspect coverage.")
        verdicts = result.get("coverage", [])
        return sum(1 for v in verdicts if "covered" in v.lower() and "not" not in v.lower())
    except Exception as e:
        logger.warning("Aspect coverage check failed: %s", e)
        return 0


# ============================================================================
# Pure helper functions (no LLM)
# ============================================================================

def _numbered_list(items: list[str]) -> str:
    """Format items as a numbered list string."""
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))


def _extract_paper_ids(text: str) -> list[str]:
    """Extract paper_id references from text.

    Matches patterns like:
      - [paper_id:abc123]
      - (paper_id: abc123)
      - paper_id=abc123
      - PMIDnnnnnnn / PMID:nnnnnnn
      - DOI references (10.xxxx/yyyy)
    """
    paper_ids: list[str] = []
    seen: set[str] = set()

    # Pattern 1: [paper_id:xxx] or (paper_id: xxx)
    for m in re.finditer(r"paper_id[:\s=]+([A-Za-z0-9_-]+)", text):
        pid = m.group(1)
        if pid not in seen:
            seen.add(pid)
            paper_ids.append(pid)

    # Pattern 2: PMID references
    for m in re.finditer(r"PMID[:\s]*(\d{6,9})", text):
        pid = f"PMID{m.group(1)}"
        if pid not in seen:
            seen.add(pid)
            paper_ids.append(pid)

    # Pattern 3: DOI references
    for m in re.finditer(r"(10\.\d{4,}/[^\s\]\)]+)", text):
        doi = m.group(1).rstrip(".,;")
        if doi not in seen:
            seen.add(doi)
            paper_ids.append(doi)

    return paper_ids


# ============================================================================
# RAGASEvaluator Class
# ============================================================================

class RAGASEvaluator:
    """Runs all RAGAS metrics and returns aggregated scores.

    Args:
        llm: LLM provider implementing generate() and generate_json().
        metrics: Optional list of metric names to run.
            Default: all five metrics.
    """

    ALL_METRICS = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "citation_fidelity",
    ]

    def __init__(
        self,
        llm: LLMProvider,
        metrics: Optional[list[str]] = None,
    ):
        self.llm = llm
        self.metrics = metrics or self.ALL_METRICS

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str = "",
        context_paper_ids: Optional[list[str]] = None,
        query_id: str = "",
    ) -> RAGASResult:
        """Evaluate a single query-answer pair.

        Args:
            question: The original question.
            answer: The generated answer.
            contexts: List of retrieved context chunks.
            ground_truth: The ground truth / reference answer.
            context_paper_ids: Paper IDs of the context chunks (for citation fidelity).
            query_id: Optional query identifier.

        Returns:
            RAGASResult with per-metric scores.
        """
        scores = RAGASScores()
        details: dict[str, Any] = {}

        if "faithfulness" in self.metrics:
            scores.faithfulness = await faithfulness(
                question, answer, contexts, ground_truth, self.llm
            )
            details["faithfulness"] = {"score": scores.faithfulness}

        if "answer_relevancy" in self.metrics:
            scores.answer_relevancy = await answer_relevancy(
                question, answer, contexts, ground_truth, self.llm
            )
            details["answer_relevancy"] = {"score": scores.answer_relevancy}

        if "context_precision" in self.metrics:
            scores.context_precision = await context_precision(
                question, answer, contexts, ground_truth, self.llm
            )
            details["context_precision"] = {"score": scores.context_precision}

        if "context_recall" in self.metrics:
            scores.context_recall = await context_recall(
                question, answer, contexts, ground_truth, self.llm
            )
            details["context_recall"] = {"score": scores.context_recall}

        if "citation_fidelity" in self.metrics:
            scores.citation_fidelity = citation_fidelity(
                question, answer, contexts, ground_truth, context_paper_ids
            )
            details["citation_fidelity"] = {"score": scores.citation_fidelity}

        return RAGASResult(
            query_id=query_id or "q0",
            question=question,
            scores=scores,
            details=details,
        )

    async def evaluate_batch(
        self,
        items: list[dict[str, Any]],
    ) -> list[RAGASResult]:
        """Evaluate a batch of query-answer pairs.

        Args:
            items: List of dicts with keys:
                question, answer, contexts, ground_truth,
                context_paper_ids (optional), query_id (optional).

        Returns:
            List of RAGASResult.
        """
        results = []
        for item in items:
            result = await self.evaluate(
                question=item["question"],
                answer=item["answer"],
                contexts=item.get("contexts", []),
                ground_truth=item.get("ground_truth", ""),
                context_paper_ids=item.get("context_paper_ids"),
                query_id=item.get("query_id", ""),
            )
            results.append(result)
        return results

    @staticmethod
    def aggregate_scores(results: list[RAGASResult]) -> dict[str, float]:
        """Compute mean scores across multiple results."""
        if not results:
            return {}

        n = len(results)
        return {
            "faithfulness": round(sum(r.scores.faithfulness for r in results) / n, 4),
            "answer_relevancy": round(sum(r.scores.answer_relevancy for r in results) / n, 4),
            "context_precision": round(sum(r.scores.context_precision for r in results) / n, 4),
            "context_recall": round(sum(r.scores.context_recall for r in results) / n, 4),
            "citation_fidelity": round(sum(r.scores.citation_fidelity for r in results) / n, 4),
            "overall": round(sum(r.scores.overall for r in results) / n, 4),
            "num_queries": n,
        }


# ============================================================================
# CLI Entry Point
# ============================================================================

async def main():
    """CLI entry point for RAGAS evaluation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="RAGAS End-to-End evaluation for Spine GraphRAG"
    )
    parser.add_argument("--question", type=str, required=True, help="Clinical question")
    parser.add_argument(
        "--baseline", type=str, default="B4",
        help="Baseline to evaluate: B1, B2, B3, B4 (default: B4)",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Number of context chunks")
    parser.add_argument(
        "--ground-truth", type=str, default="",
        help="Ground truth answer (optional)",
    )
    parser.add_argument(
        "--metrics", type=str, default="all",
        help="Comma-separated metrics or 'all'",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Initialize clients
    from core.config import get_config
    from core.embedding import EmbeddingClient
    from graph.neo4j_client import Neo4jClient
    from llm import LLMClient

    config = get_config()
    neo4j_client = Neo4jClient(config)
    await neo4j_client.__aenter__()
    embedding_client = EmbeddingClient(config)
    llm_client = LLMClient()

    try:
        # Run baseline search to get contexts
        from evaluation.baselines import (
            GraphRAGSearch,
            KeywordSearch,
            VectorOnlySearch,
        )

        baseline_map = {
            "B1": lambda: KeywordSearch(neo4j_client),
            "B2": lambda: VectorOnlySearch(neo4j_client, embedding_client),
            "B4": lambda: GraphRAGSearch(neo4j_client, embedding_client),
        }

        baseline_key = args.baseline.upper()
        if baseline_key not in baseline_map:
            logger.error("Unsupported baseline: %s (use B1, B2, B4)", baseline_key)
            return

        baseline = baseline_map[baseline_key]()
        results = await baseline.search(args.question, top_k=args.top_k)

        contexts = [r.chunk_text or r.title for r in results]
        context_paper_ids = [r.paper_id for r in results]

        # Generate answer using LLM
        context_block = "\n---\n".join(contexts)
        answer_prompt = (
            f"Based on the following evidence, answer the clinical question.\n\n"
            f"Question: {args.question}\n\n"
            f"Evidence:\n{context_block}\n\n"
            f"Provide a concise, evidence-based answer. Cite paper_ids where applicable."
        )
        answer_response = await llm_client.generate(answer_prompt)
        answer_text = answer_response.text

        # Select metrics
        metrics = (
            RAGASEvaluator.ALL_METRICS
            if args.metrics.lower() == "all"
            else args.metrics.split(",")
        )

        # Run RAGAS evaluation
        evaluator = RAGASEvaluator(llm=llm_client, metrics=metrics)
        ragas_result = await evaluator.evaluate(
            question=args.question,
            answer=answer_text,
            contexts=contexts,
            ground_truth=args.ground_truth,
            context_paper_ids=context_paper_ids,
            query_id="cli_query",
        )

        # Print results
        print("\n" + "=" * 60)
        print("RAGAS Evaluation Results")
        print("=" * 60)
        print(f"Question: {args.question}")
        print(f"Baseline: {baseline_key}")
        print(f"Contexts: {len(contexts)} chunks")
        print("-" * 60)
        for metric, score in ragas_result.scores.to_dict().items():
            print(f"  {metric:<22} {score:.4f}")
        print(f"  {'overall':<22} {ragas_result.scores.overall:.4f}")
        print("=" * 60)

    finally:
        await neo4j_client.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
