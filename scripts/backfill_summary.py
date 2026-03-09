"""Backfill paper summaries using LLM.

기존 Paper 노드 중 summary가 없는 것에 대해 abstract를 기반으로
LLM(Claude Haiku)으로 2-3문장 요약을 생성합니다.

Usage:
    PYTHONPATH=./src python3 scripts/backfill_summary.py
    PYTHONPATH=./src python3 scripts/backfill_summary.py --dry-run
    PYTHONPATH=./src python3 scripts/backfill_summary.py --max-concurrent 3
    PYTHONPATH=./src python3 scripts/backfill_summary.py --paper-ids "pubmed_12345,pubmed_67890"
"""

import asyncio
import argparse
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """You are a medical research summarizer specializing in spine surgery.

Given the title and abstract of a spine surgery research paper, write a comprehensive 2-3 sentence summary of the paper's key findings, methods, and conclusions.

Title: {title}
Abstract: {abstract}

Write ONLY the summary, no preamble or labels. The summary should be in English and capture:
1. What was studied (intervention/condition)
2. Key findings/results
3. Main conclusion or clinical implication"""


async def get_papers_missing_summary(driver, paper_ids=None):
    """Get papers that need summaries."""
    async with driver.session() as session:
        if paper_ids:
            result = await session.run(
                """
                MATCH (p:Paper)
                WHERE p.paper_id IN $ids
                  AND p.abstract IS NOT NULL AND size(p.abstract) > 50
                  AND (p.summary IS NULL OR p.summary = '')
                RETURN p.paper_id AS id, p.title AS title, p.abstract AS abstract
                ORDER BY p.paper_id
                """,
                ids=paper_ids,
            )
        else:
            result = await session.run(
                """
                MATCH (p:Paper)
                WHERE p.abstract IS NOT NULL AND size(p.abstract) > 50
                  AND (p.summary IS NULL OR p.summary = '')
                RETURN p.paper_id AS id, p.title AS title, p.abstract AS abstract
                ORDER BY p.paper_id
                """
            )
        return [record.data() async for record in result]


async def generate_summary(client, title: str, abstract: str) -> str:
    """Generate summary using LLM."""
    prompt = SUMMARY_PROMPT.format(title=title, abstract=abstract[:3000])
    response = await client.generate(prompt)
    return response.text.strip()


async def update_paper_summary(driver, paper_id: str, summary: str):
    """Update paper summary in Neo4j."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (p:Paper {paper_id: $pid})
            SET p.summary = $summary
            """,
            pid=paper_id,
            summary=summary,
        )


async def process_batch(driver, client, papers, semaphore, dry_run=False):
    """Process a batch of papers concurrently."""
    results = {"success": 0, "failed": 0, "skipped": 0}

    async def process_one(paper):
        async with semaphore:
            paper_id = paper["id"]
            title = paper["title"] or ""
            abstract = paper["abstract"] or ""

            if len(abstract) < 50:
                logger.info(f"  SKIP {paper_id}: abstract too short")
                results["skipped"] += 1
                return

            try:
                summary = await generate_summary(client, title, abstract)
                if dry_run:
                    logger.info(f"  DRY-RUN {paper_id}: {summary[:80]}...")
                else:
                    await update_paper_summary(driver, paper_id, summary)
                    logger.info(f"  OK {paper_id}: {summary[:80]}...")
                results["success"] += 1
            except Exception as e:
                logger.error(f"  FAIL {paper_id}: {e}")
                results["failed"] += 1

    tasks = [process_one(p) for p in papers]
    await asyncio.gather(*tasks)
    return results


async def main():
    parser = argparse.ArgumentParser(description="Backfill paper summaries using LLM")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent LLM calls")
    parser.add_argument("--paper-ids", type=str, help="Comma-separated paper IDs")
    args = parser.parse_args()

    # Import LLM client
    from llm import LLMClient, LLMConfig

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    client = LLMClient(config=LLMConfig(temperature=0.1))

    paper_ids = None
    if args.paper_ids:
        paper_ids = [pid.strip() for pid in args.paper_ids.split(",")]

    try:
        papers = await get_papers_missing_summary(driver, paper_ids)
        logger.info(f"Summary 누락 Paper: {len(papers)}개")

        if not papers:
            logger.info("모든 Paper에 summary가 있습니다.")
            return

        semaphore = asyncio.Semaphore(args.max_concurrent)
        results = await process_batch(driver, client, papers, semaphore, args.dry_run)

        logger.info(f"완료: 성공={results['success']}, 실패={results['failed']}, 스킵={results['skipped']}")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
