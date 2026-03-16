"""Update Neo4j Paper nodes with generated summaries.

Reads summary JSON files and updates the summary/main_conclusion
fields for papers that are missing them.

Usage:
    PYTHONPATH=./src:. python3 evaluation/update_summaries.py
    PYTHONPATH=./src:. python3 evaluation/update_summaries.py --dry-run
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
EVAL_DIR = Path(__file__).parent


async def update_summaries(dry_run: bool = False) -> dict:
    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    from dotenv import load_dotenv

    load_dotenv()
    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    # Load all summary files
    all_summaries = []
    for sf in ["summaries_bs.json", "summaries_tr.json", "summaries_tu.json"]:
        path = EVAL_DIR / sf
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                all_summaries.extend(data)
                logger.info("Loaded %s: %d entries", sf, len(data))
        else:
            logger.warning("Not found: %s", sf)

    stats = {"updated": 0, "skipped": 0, "errors": 0}

    for s in all_summaries:
        pmid = str(s.get("pmid", ""))
        summary = s.get("summary", "")
        conclusion = s.get("main_conclusion", "")

        if not pmid or not summary:
            stats["skipped"] += 1
            continue

        paper_id = f"pubmed_{pmid}"

        if dry_run:
            logger.info("DRY-RUN: %s | summary=%dchars | conclusion=%dchars",
                        paper_id, len(summary), len(conclusion))
            stats["updated"] += 1
            continue

        try:
            await neo4j.run_write_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.summary = $summary,
                    p.main_conclusion = $conclusion
                """,
                {
                    "paper_id": paper_id,
                    "summary": summary,
                    "conclusion": conclusion,
                },
            )
            stats["updated"] += 1
        except Exception as e:
            logger.error("Failed to update %s: %s", paper_id, e)
            stats["errors"] += 1

    await neo4j.__aexit__(None, None, None)
    return stats


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = await update_summaries(dry_run=args.dry_run)
    print(f"\n{'DRY-RUN ' if args.dry_run else ''}Update complete:")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
