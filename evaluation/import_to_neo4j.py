"""Import papers with extracted entities into Neo4j.

Bypasses LLM pipeline — uses pre-extracted entities from Claude Code CLI.

Usage:
    PYTHONPATH=./src:. python3 evaluation/import_to_neo4j.py
    PYTHONPATH=./src:. python3 evaluation/import_to_neo4j.py --dry-run
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent


async def import_papers(dry_run: bool = False) -> dict:
    """Import papers + entities into Neo4j."""
    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    from dotenv import load_dotenv

    load_dotenv()
    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    # Load paper data and entities
    papers_by_pmid = {}
    with open(EVAL_DIR / "import_selected.json") as f:
        for p in json.load(f):
            papers_by_pmid[p["pmid"]] = p

    entities_files = ["entities_bs.json", "entities_tr.json", "entities_tu.json"]
    all_entities = []
    for ef in entities_files:
        path = EVAL_DIR / ef
        if path.exists():
            with open(path) as f:
                all_entities.extend(json.load(f))
            logger.info("Loaded %s: %d entries", ef, len(all_entities))
        else:
            logger.warning("Entity file not found: %s", ef)

    entities_by_pmid = {e["pmid"]: e for e in all_entities}

    # Check existing PMIDs
    existing = set()
    rows = await neo4j.run_query(
        "MATCH (p:Paper) WHERE p.pmid IS NOT NULL RETURN p.pmid AS pmid"
    )
    for r in rows:
        if r.get("pmid"):
            existing.add(str(r["pmid"]))

    stats = {"papers": 0, "skipped": 0, "entities": 0, "relations": 0, "embeddings": 0}

    for pmid, paper in papers_by_pmid.items():
        if str(pmid) in existing:
            logger.info("SKIP (exists): %s - %s", pmid, paper["title"][:60])
            stats["skipped"] += 1
            continue

        ent = entities_by_pmid.get(str(pmid), {})
        if not ent:
            logger.warning("No entities for PMID %s, importing paper only", pmid)

        paper_id = f"pubmed_{pmid}"
        sub_domain = paper.get("sub_domain", "Unknown")
        study_design = ent.get("study_design", "Other")
        evidence_level = ent.get("evidence_level", "5")

        if dry_run:
            intv = ent.get("interventions", [])
            path = ent.get("pathologies", [])
            outc = ent.get("outcomes", [])
            anat = ent.get("anatomy", [])
            logger.info(
                "DRY-RUN: %s | %s | I:%d P:%d O:%d A:%d | %s | EL:%s",
                pmid, paper["title"][:50], len(intv), len(path),
                len(outc), len(anat), study_design, evidence_level,
            )
            stats["papers"] += 1
            continue

        # 1. Create Paper node
        props = {
            "paper_id": paper_id,
            "title": paper["title"],
            "authors": paper.get("authors", ""),
            "year": int(paper["year"]) if paper.get("year") else 0,
            "journal": paper.get("journal", ""),
            "doi": paper.get("doi", ""),
            "pmid": str(pmid),
            "abstract": (paper.get("abstract") or "")[:2000],
            "mesh_terms": paper.get("mesh_terms", [])[:20],
            "publication_types": paper.get("publication_types", [])[:10],
            "evidence_level": evidence_level,
            "study_design": study_design,
            "sub_domain": sub_domain,
            "source": "pubmed",
            "is_abstract_only": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        await neo4j.run_write_query(
            "MERGE (p:Paper {paper_id: $paper_id}) SET p += $props",
            {"paper_id": paper_id, "props": props},
        )
        stats["papers"] += 1

        # 2. Generate abstract embedding (OpenAI)
        abstract = paper.get("abstract", "")
        if abstract and len(abstract.strip()) > 100:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                resp = client.embeddings.create(
                    model="text-embedding-3-large",
                    input=abstract[:8000],
                    dimensions=3072,
                )
                embedding = resp.data[0].embedding
                await neo4j.run_write_query(
                    "MATCH (p:Paper {paper_id: $pid}) SET p.abstract_embedding = $emb",
                    {"pid": paper_id, "emb": embedding},
                )
                stats["embeddings"] += 1
            except Exception as e:
                logger.warning("Embedding failed for %s: %s", paper_id, e)

        # 3. Create entity nodes + relationships
        for intervention in ent.get("interventions", []):
            await _merge_entity_and_link(
                neo4j, paper_id, "Intervention", intervention, "INVESTIGATES"
            )
            stats["entities"] += 1

        for pathology in ent.get("pathologies", []):
            await _merge_entity_and_link(
                neo4j, paper_id, "Pathology", pathology, "INVESTIGATES"
            )
            # Also create STUDIES relationship
            await neo4j.run_write_query(
                """
                MATCH (p:Paper {paper_id: $pid})
                MERGE (path:Pathology {name: $name})
                MERGE (p)-[:STUDIES]->(path)
                """,
                {"pid": paper_id, "name": pathology},
            )
            stats["entities"] += 1
            stats["relations"] += 1

        for outcome in ent.get("outcomes", []):
            await _merge_entity_and_link(
                neo4j, paper_id, "Outcome", outcome, "INVESTIGATES"
            )
            stats["entities"] += 1

        for anatomy in ent.get("anatomy", []):
            await _merge_entity_and_link(
                neo4j, paper_id, "Anatomy", anatomy, "INVESTIGATES"
            )
            stats["entities"] += 1

        # 4. TREATS relationships (intervention → pathology)
        for intervention in ent.get("interventions", []):
            for pathology in ent.get("pathologies", []):
                await neo4j.run_write_query(
                    """
                    MERGE (i:Intervention {name: $int_name})
                    MERGE (path:Pathology {name: $path_name})
                    MERGE (i)-[t:TREATS]->(path)
                    ON CREATE SET t.paper_count = 1
                    ON MATCH SET t.paper_count = t.paper_count + 1
                    """,
                    {"int_name": intervention, "path_name": pathology},
                )
                stats["relations"] += 1

        # 5. AFFECTS relationships (intervention → outcome)
        for intervention in ent.get("interventions", []):
            for outcome in ent.get("outcomes", []):
                await neo4j.run_write_query(
                    """
                    MERGE (i:Intervention {name: $int_name})
                    MERGE (o:Outcome {name: $out_name})
                    MERGE (i)-[a:AFFECTS]->(o)
                    ON CREATE SET a.paper_count = 1
                    ON MATCH SET a.paper_count = a.paper_count + 1
                    """,
                    {"int_name": intervention, "out_name": outcome},
                )
                stats["relations"] += 1

        logger.info(
            "Imported: %s | I:%d P:%d O:%d A:%d | %s",
            paper_id,
            len(ent.get("interventions", [])),
            len(ent.get("pathologies", [])),
            len(ent.get("outcomes", [])),
            len(ent.get("anatomy", [])),
            paper["title"][:50],
        )

    await neo4j.__aexit__(None, None, None)
    return stats


async def _merge_entity_and_link(
    neo4j, paper_id: str, label: str, name: str, rel_type: str
):
    """Create entity node and link to paper."""
    cypher = f"""
    MATCH (p:Paper {{paper_id: $pid}})
    MERGE (e:{label} {{name: $name}})
    MERGE (p)-[:{rel_type}]->(e)
    """
    await neo4j.run_write_query(cypher, {"pid": paper_id, "name": name})


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    stats = await import_papers(dry_run=args.dry_run)
    print(f"\n{'DRY-RUN ' if args.dry_run else ''}Import complete:")
    print(f"  Papers: {stats['papers']} (skipped: {stats['skipped']})")
    print(f"  Entities: {stats['entities']}")
    print(f"  Relations: {stats['relations']}")
    print(f"  Embeddings: {stats['embeddings']}")


if __name__ == "__main__":
    asyncio.run(main())
