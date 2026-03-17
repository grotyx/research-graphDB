"""Backfill Paper-level abstract embeddings.

Paper 노드 중 abstract는 있지만 abstract_embedding이 없는 것에 대해
OpenAI text-embedding-3-large로 임베딩을 생성하여 저장합니다.

Contextual prefix: "[title | Abstract | year] abstract_text"

ROADMAP #9, DV-NEW-036

Usage:
    PYTHONPATH=./src python3 scripts/backfill_paper_embeddings.py --dry-run
    PYTHONPATH=./src python3 scripts/backfill_paper_embeddings.py --max-papers 10
    PYTHONPATH=./src python3 scripts/backfill_paper_embeddings.py
"""

import asyncio
import argparse
import os
import sys
import logging
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Embedding batch size for OpenAI API calls
EMBED_BATCH_SIZE = 50


async def get_papers_missing_embedding(
    driver, max_papers: int | None = None
) -> list[dict]:
    """Find Paper nodes with abstract but no abstract_embedding."""
    query = """
        MATCH (p:Paper)
        WHERE p.abstract IS NOT NULL AND size(p.abstract) > 50
          AND p.abstract_embedding IS NULL
        RETURN p.paper_id AS paper_id,
               p.title AS title,
               p.abstract AS abstract,
               p.year AS year
        ORDER BY p.paper_id
    """
    params: dict = {}
    if max_papers:
        query += "\nLIMIT $limit"
        params["limit"] = max_papers

    async with driver.session() as session:
        result = await session.run(query, params)
        return [record.data() async for record in result]


async def store_embeddings_batch(
    driver, papers: list[dict], embeddings: list[list[float]]
) -> int:
    """Store abstract_embedding for a batch of Paper nodes via UNWIND.

    Returns the number of successfully updated papers.
    """
    rows = [
        {"paper_id": p["paper_id"], "embedding": emb}
        for p, emb in zip(papers, embeddings)
    ]
    query = """
        UNWIND $rows AS row
        MATCH (p:Paper {paper_id: row.paper_id})
        SET p.abstract_embedding = row.embedding
        RETURN count(p) AS updated
    """
    async with driver.session() as session:
        result = await session.run(query, {"rows": rows})
        record = await result.single()
        return record["updated"] if record else 0


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Paper abstract embeddings (OpenAI 3072d)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count papers only, do not generate embeddings",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=None,
        help="Max papers to process (for testing)",
    )
    args = parser.parse_args()

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        papers = await get_papers_missing_embedding(driver, args.max_papers)
        total = len(papers)
        logger.info(f"Papers with abstract but no embedding: {total}")

        if not papers:
            logger.info("All papers already have embeddings. Nothing to do.")
            return

        if args.dry_run:
            logger.info("[DRY-RUN] Would generate embeddings for %d papers.", total)
            for i, p in enumerate(papers[:10]):
                title = (p["title"] or "")[:60]
                logger.info(f"  [{i+1}] {p['paper_id']}: {title}...")
            if total > 10:
                logger.info(f"  ... and {total - 10} more")
            return

        # Lazy import: only needed for actual embedding
        from core.embedding import OpenAIEmbeddingGenerator, apply_context_prefix

        generator = OpenAIEmbeddingGenerator(batch_size=EMBED_BATCH_SIZE)
        logger.info(
            f"Using {generator.MODEL} ({generator.DIMENSION}d), "
            f"batch_size={EMBED_BATCH_SIZE}"
        )

        success = 0
        failed = 0
        t0 = time.time()

        # Process in batches
        for batch_start in range(0, total, EMBED_BATCH_SIZE):
            batch = papers[batch_start : batch_start + EMBED_BATCH_SIZE]
            batch_num = batch_start // EMBED_BATCH_SIZE + 1
            total_batches = (total + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

            # Build prefixed texts for this batch
            texts = []
            for p in batch:
                abstract = p["abstract"] or ""
                title = p["title"] or ""
                year = p["year"] or 0
                prefixed = apply_context_prefix(
                    [abstract],
                    title=title,
                    section="Abstract",
                    year=year,
                )
                texts.append(prefixed[0])

            # Generate embeddings for the batch
            try:
                embeddings = generator.embed_batch(texts)
            except Exception as e:
                logger.error(
                    f"Batch {batch_num}/{total_batches} embedding failed: {e}"
                )
                failed += len(batch)
                continue

            # Store embeddings in a single UNWIND batch
            try:
                updated = await store_embeddings_batch(driver, batch, embeddings)
                success += updated
                if updated < len(batch):
                    failed += len(batch) - updated
                    logger.warning(
                        f"Batch {batch_num}: only {updated}/{len(batch)} "
                        f"papers matched for update"
                    )
            except Exception as e:
                logger.error(
                    f"Batch {batch_num}/{total_batches} store failed: {e}"
                )
                failed += len(batch)

            # Progress logging
            processed = batch_start + len(batch)
            if processed % 10 == 0 or processed == total:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Progress: {processed}/{total} "
                    f"({processed * 100 // total}%) "
                    f"[{rate:.1f} papers/s]"
                )

        elapsed = time.time() - t0
        logger.info(
            f"Done: success={success}, failed={failed}, "
            f"elapsed={elapsed:.1f}s"
        )

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
