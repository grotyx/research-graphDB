"""LLM-as-Judge evaluation for generated answers.

Evaluates answers on RAGAS-style metrics:
  - Faithfulness: claims supported by cited sources
  - Citation Fidelity: cited papers actually support the claims
  - Answer Relevancy: answer addresses the question
  - Completeness: important clinical aspects covered
  - Hallucination Rate: references not in the knowledge base
  - Evidence Level: mean OCEBM level of cited papers

Usage:
    PYTHONPATH=./src:. python3 evaluation/llm_judge.py
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)
EVAL_DIR = Path(__file__).parent

EVIDENCE_LEVEL_SCORE = {
    "1a": 7, "1b": 6, "2a": 5, "2b": 4, "3": 3, "4": 2, "5": 1, "unknown": 1,
}


@dataclass
class JudgeResult:
    """Evaluation result for a single answer."""
    query_id: str
    baseline: str
    faithfulness: float = 0.0
    citation_fidelity: float = 0.0
    answer_relevancy: float = 0.0
    completeness: float = 0.0
    hallucination_rate: float = 0.0
    evidence_level_score: float = 0.0
    num_claims: int = 0
    num_citations: int = 0
    num_hallucinated: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "baseline": self.baseline,
            "faithfulness": round(self.faithfulness, 3),
            "citation_fidelity": round(self.citation_fidelity, 3),
            "answer_relevancy": round(self.answer_relevancy, 3),
            "completeness": round(self.completeness, 3),
            "hallucination_rate": round(self.hallucination_rate, 3),
            "evidence_level_score": round(self.evidence_level_score, 2),
            "num_claims": self.num_claims,
            "num_citations": self.num_citations,
            "num_hallucinated": self.num_hallucinated,
        }


async def evaluate_answer(
    query_id: str,
    baseline: str,
    question: str,
    answer: str,
    cited_papers: list[dict],
    all_paper_ids: set[str],
    neo4j_client: Any = None,
) -> JudgeResult:
    """Evaluate a single generated answer using LLM-as-Judge."""
    result = JudgeResult(query_id=query_id, baseline=baseline)

    # 1. Hallucination Rate (automatic — check if cited papers exist in DB)
    if baseline == "B3":
        # B3 doesn't have structured citations, extract from text
        cited_refs = _extract_citation_ids_from_text(answer)
        result.num_citations = len(cited_refs)
        result.num_hallucinated = len(cited_refs)  # All are unverifiable for B3
        result.hallucination_rate = 1.0 if cited_refs else 0.0
    else:
        result.num_citations = len(cited_papers)
        hallucinated = [p for p in cited_papers if p.get("paper_id") not in all_paper_ids]
        result.num_hallucinated = len(hallucinated)
        result.hallucination_rate = len(hallucinated) / max(len(cited_papers), 1)

    # 2. Evidence Level Score (automatic)
    if cited_papers:
        el_scores = []
        for p in cited_papers:
            el = (p.get("evidence_level") or "unknown").strip().lower()
            el_scores.append(EVIDENCE_LEVEL_SCORE.get(el, 1))
        result.evidence_level_score = sum(el_scores) / len(el_scores)

    # 3. LLM-as-Judge for Faithfulness, Relevancy, Completeness, Citation Fidelity
    judge_scores = await _llm_judge_evaluate(question, answer, cited_papers)
    result.faithfulness = judge_scores.get("faithfulness", 0.0)
    result.citation_fidelity = judge_scores.get("citation_fidelity", 0.0)
    result.answer_relevancy = judge_scores.get("answer_relevancy", 0.0)
    result.completeness = judge_scores.get("completeness", 0.0)
    result.num_claims = judge_scores.get("num_claims", 0)

    return result


async def _llm_judge_evaluate(
    question: str, answer: str, cited_papers: list[dict]
) -> dict:
    """Use Claude as judge to evaluate answer quality."""
    import anthropic

    papers_context = ""
    if cited_papers:
        paper_lines = []
        for p in cited_papers:
            paper_lines.append(
                f"- [{p.get('paper_id','')}] {p.get('title','')} "
                f"(Evidence: {p.get('evidence_level','unknown')})"
            )
        papers_context = "\n".join(paper_lines)
    else:
        papers_context = "(No structured citations provided — answer based on LLM knowledge only)"

    prompt = f"""You are an expert evaluator assessing the quality of a medical literature synthesis answer.

## Clinical Question
{question}

## Generated Answer
{answer}

## Papers Cited by the System
{papers_context}

## Evaluation Instructions

Rate the answer on four dimensions. For each, provide a score from 0.0 to 1.0 and a brief justification.

1. **Faithfulness** (0.0-1.0): What proportion of claims in the answer are supported by the cited papers? Claims without citations or with fabricated citations score 0. If no papers are cited, base this on whether claims appear to be evidence-based.

2. **Citation Fidelity** (0.0-1.0): Do the cited papers actually support the specific claims attributed to them? Score based on alignment between claim and paper topic/title.

3. **Answer Relevancy** (0.0-1.0): Does the answer directly address the clinical question? Is it focused and on-topic?

4. **Completeness** (0.0-1.0): Does the answer cover the important clinical aspects? For comparison questions, are both sides compared? Are outcomes, complications, and evidence levels discussed?

Also count the number of distinct factual claims in the answer.

Respond in this exact JSON format:
```json
{{
  "faithfulness": 0.0,
  "citation_fidelity": 0.0,
  "answer_relevancy": 0.0,
  "completeness": 0.0,
  "num_claims": 0,
  "justification": "Brief explanation"
}}
```"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Parse JSON from response
        json_match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group())
            return {
                "faithfulness": float(scores.get("faithfulness", 0)),
                "citation_fidelity": float(scores.get("citation_fidelity", 0)),
                "answer_relevancy": float(scores.get("answer_relevancy", 0)),
                "completeness": float(scores.get("completeness", 0)),
                "num_claims": int(scores.get("num_claims", 0)),
            }
    except Exception as e:
        logger.error("LLM judge failed: %s", e)

    return {"faithfulness": 0, "citation_fidelity": 0, "answer_relevancy": 0, "completeness": 0, "num_claims": 0}


def _extract_citation_ids_from_text(text: str) -> list[str]:
    """Extract paper IDs or author-year citations from answer text."""
    # Match [pubmed_XXXXX] or [paper_XXXXX] patterns
    ids = re.findall(r"\[(?:pubmed_|paper_)\d+\]", text)
    # Match author-year patterns
    author_years = re.findall(r"([A-Z][a-z]+)\s+(?:et\s+al\.?\s*)?\(?(\d{4})\)?", text)
    return ids + [f"{a}_{y}" for a, y in author_years]


async def evaluate_all(
    answers_dir: Path = None,
    baselines: list[str] = None,
    neo4j_client: Any = None,
) -> dict[str, list[JudgeResult]]:
    """Evaluate all saved answers."""
    if answers_dir is None:
        answers_dir = EVAL_DIR / "results" / "answers"
    if baselines is None:
        baselines = ["B1", "B2", "B3", "B4"]

    # Get all paper IDs from Neo4j
    all_paper_ids = set()
    if neo4j_client:
        rows = await neo4j_client.run_query("MATCH (p:Paper) RETURN p.paper_id AS pid")
        all_paper_ids = {r["pid"] for r in rows if r.get("pid")}
        logger.info("Loaded %d paper IDs from Neo4j", len(all_paper_ids))

    results: dict[str, list[JudgeResult]] = {}

    for baseline in baselines:
        path = answers_dir / f"{baseline}.json"
        if not path.exists():
            logger.warning("No answers file for %s", baseline)
            continue

        with open(path) as f:
            answers = json.load(f)

        judge_results = []
        for a in answers:
            jr = await evaluate_answer(
                query_id=a["query_id"],
                baseline=baseline,
                question=a["question"],
                answer=a["answer"],
                cited_papers=a.get("cited_papers", []),
                all_paper_ids=all_paper_ids,
                neo4j_client=neo4j_client,
            )
            judge_results.append(jr)
            logger.info(
                "  %s/%s: F=%.2f CF=%.2f R=%.2f C=%.2f H=%.1f%% EL=%.1f",
                baseline, a["query_id"],
                jr.faithfulness, jr.citation_fidelity,
                jr.answer_relevancy, jr.completeness,
                jr.hallucination_rate * 100, jr.evidence_level_score,
            )

        results[baseline] = judge_results

    return results


def print_summary(results: dict[str, list[JudgeResult]]) -> str:
    """Print comparison table."""
    header = f"{'Baseline':<12} {'Faith':>6} {'CitFid':>7} {'Relev':>6} {'Compl':>6} {'Halluc%':>8} {'EvLvl':>6} {'n':>4}"
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for baseline, jrs in results.items():
        n = len(jrs)
        if n == 0:
            continue
        avg = lambda attr: sum(getattr(jr, attr) for jr in jrs) / n
        line = (
            f"{baseline:<12} "
            f"{avg('faithfulness'):>6.3f} "
            f"{avg('citation_fidelity'):>7.3f} "
            f"{avg('answer_relevancy'):>6.3f} "
            f"{avg('completeness'):>6.3f} "
            f"{avg('hallucination_rate') * 100:>7.1f}% "
            f"{avg('evidence_level_score'):>6.2f} "
            f"{n:>4}"
        )
        lines.append(line)

    lines.append(sep)
    table = "\n".join(lines)
    print(table)
    return table


def save_results(results: dict[str, list[JudgeResult]], output_path: Path = None):
    """Save judge results to JSON."""
    if output_path is None:
        output_path = EVAL_DIR / "results" / "judge_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        baseline: [jr.to_dict() for jr in jrs]
        for baseline, jrs in results.items()
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Judge results saved to %s", output_path)


# ============================================================================
# CLI
# ============================================================================

async def main():
    import argparse
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--baselines", type=str, default="B1,B2,B3,B4")
    args = parser.parse_args()

    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    try:
        baseline_names = args.baselines.upper().split(",")
        results = await evaluate_all(baselines=baseline_names, neo4j_client=neo4j)
        print_summary(results)
        save_results(results)
    finally:
        await neo4j.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
