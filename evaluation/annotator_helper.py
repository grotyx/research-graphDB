"""Annotator helper — generates candidate paper lists for expert annotation.

For each gold standard question, searches Neo4j to find candidate papers
that experts can then mark as relevant/not relevant.

Usage:
    PYTHONPATH=./src:. python3 evaluation/annotator_helper.py --top-k 30
    PYTHONPATH=./src:. python3 evaluation/annotator_helper.py --query-id DG-001
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GOLD_STANDARD_DIR = Path(__file__).parent / "gold_standard"


async def find_candidates_for_question(
    neo4j_client: Any,
    question: dict,
    top_k: int = 30,
) -> list[dict]:
    """Find candidate papers for a gold standard question.

    Uses multiple search strategies to maximize recall:
    1. Entity-based graph search (TREATS/AFFECTS/INVESTIGATES)
    2. Keyword search on title/abstract
    3. Vector search (if embedding available)
    """
    candidates: dict[str, dict] = {}
    entities = question.get("expected_entities", {})
    interventions = entities.get("interventions", [])
    pathologies = entities.get("pathologies", [])
    outcomes = entities.get("outcomes", [])

    # Strategy 1: Entity-based graph search
    for intervention in interventions:
        cypher = """
        MATCH (i:Intervention)<-[:INVESTIGATES]-(p:Paper)
        WHERE toLower(i.name) CONTAINS toLower($name)
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.evidence_level AS evidence_level,
               p.year AS year,
               p.study_design AS study_design,
               p.authors AS authors,
               'intervention_match' AS source
        LIMIT $limit
        """
        try:
            rows = await neo4j_client.run_query(
                cypher, {"name": intervention, "limit": top_k}
            )
            for r in rows:
                pid = r.get("paper_id", "")
                if pid and pid not in candidates:
                    candidates[pid] = r
        except Exception as e:
            logger.warning("Graph search failed for %s: %s", intervention, e)

    for pathology in pathologies:
        cypher = """
        MATCH (p:Paper)-[:INVESTIGATES]->(path:Pathology)
        WHERE toLower(path.name) CONTAINS toLower($name)
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.evidence_level AS evidence_level,
               p.year AS year,
               p.study_design AS study_design,
               p.authors AS authors,
               'pathology_match' AS source
        LIMIT $limit
        """
        try:
            rows = await neo4j_client.run_query(
                cypher, {"name": pathology, "limit": top_k}
            )
            for r in rows:
                pid = r.get("paper_id", "")
                if pid and pid not in candidates:
                    candidates[pid] = r
        except Exception as e:
            logger.warning("Graph search failed for %s: %s", pathology, e)

    # Strategy 2: Keyword search on title/abstract
    keywords = interventions + pathologies + outcomes[:2]
    for kw in keywords[:5]:
        cypher = """
        MATCH (p:Paper)
        WHERE toLower(p.title) CONTAINS toLower($keyword)
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.evidence_level AS evidence_level,
               p.year AS year,
               p.study_design AS study_design,
               p.authors AS authors,
               'keyword_match' AS source
        LIMIT $limit
        """
        try:
            rows = await neo4j_client.run_query(
                cypher, {"keyword": kw, "limit": 15}
            )
            for r in rows:
                pid = r.get("paper_id", "")
                if pid and pid not in candidates:
                    candidates[pid] = r
        except Exception as e:
            logger.warning("Keyword search failed for %s: %s", kw, e)

    # Strategy 3: TREATS relationship search (intervention → pathology)
    for intervention in interventions:
        for pathology in pathologies:
            cypher = """
            MATCH (i:Intervention)-[t:TREATS]->(path:Pathology)<-[:INVESTIGATES]-(p:Paper)
            WHERE toLower(i.name) CONTAINS toLower($int_name)
              AND toLower(path.name) CONTAINS toLower($path_name)
            RETURN DISTINCT p.paper_id AS paper_id, p.title AS title,
                   p.evidence_level AS evidence_level,
                   p.year AS year,
                   p.study_design AS study_design,
                   p.authors AS authors,
                   'treats_match' AS source
            LIMIT $limit
            """
            try:
                rows = await neo4j_client.run_query(
                    cypher,
                    {"int_name": intervention, "path_name": pathology, "limit": 15},
                )
                for r in rows:
                    pid = r.get("paper_id", "")
                    if pid and pid not in candidates:
                        candidates[pid] = r
            except Exception as e:
                logger.warning("TREATS search failed: %s", e)

    # Sort: higher evidence level first, then by year descending
    evidence_order = {"1a": 0, "1b": 1, "2a": 2, "2b": 3, "3": 4, "4": 5, "5": 6}
    result = sorted(
        candidates.values(),
        key=lambda x: (
            evidence_order.get(x.get("evidence_level", "5"), 6),
            -(int(x.get("year") or 0) if str(x.get("year", "0")).isdigit() else 0),
        ),
    )
    return result[:top_k]


async def generate_annotation_sheet(
    neo4j_client: Any,
    questions: list[dict],
    top_k: int = 30,
    query_id: str | None = None,
) -> dict:
    """Generate annotation sheet for all (or selected) questions.

    Returns a dict with candidate papers per question for expert review.
    """
    sheet = {
        "description": "Candidate papers for expert annotation",
        "instructions": (
            "For each paper, mark relevance: "
            "3=highly relevant, 2=relevant, 1=marginally relevant, 0=not relevant"
        ),
        "questions": {},
    }

    for q in questions:
        qid = q["id"]
        if query_id and qid != query_id:
            continue

        logger.info("Finding candidates for %s: %s", qid, q["question"][:60])
        candidates = await find_candidates_for_question(neo4j_client, q, top_k)

        sheet["questions"][qid] = {
            "question": q["question"],
            "domain": q.get("domain"),
            "type": q.get("type"),
            "num_candidates": len(candidates),
            "candidates": [
                {
                    "paper_id": c["paper_id"],
                    "title": c.get("title", ""),
                    "year": c.get("year"),
                    "evidence_level": c.get("evidence_level"),
                    "study_design": c.get("study_design"),
                    "authors": (c.get("authors") or "")[:80],
                    "source": c.get("source", ""),
                    "relevance": None,  # To be filled by annotator
                }
                for c in candidates
            ],
        }
        logger.info("  Found %d candidates", len(candidates))

    return sheet


async def main():
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate annotation sheet")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--query-id", type=str, help="Single query ID to process")
    parser.add_argument(
        "--output",
        type=str,
        default=str(GOLD_STANDARD_DIR / "annotation_sheet.json"),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load questions
    with open(GOLD_STANDARD_DIR / "questions.json") as f:
        data = json.load(f)
    questions = data.get("questions", data)

    # Connect to Neo4j
    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    neo4j_config = Neo4jConfig.from_env()
    neo4j_client = Neo4jClient(neo4j_config)
    await neo4j_client.__aenter__()

    try:
        sheet = await generate_annotation_sheet(
            neo4j_client, questions, args.top_k, args.query_id
        )

        with open(args.output, "w") as f:
            json.dump(sheet, f, indent=2, ensure_ascii=False)

        total = sum(
            q["num_candidates"] for q in sheet["questions"].values()
        )
        logger.info(
            "\nDone: %d questions, %d total candidates → %s",
            len(sheet["questions"]),
            total,
            args.output,
        )
    finally:
        await neo4j_client.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
