#!/usr/bin/env python3
"""Import ESI (Degenerative) and Burst Fracture (Trauma) papers into Neo4j.

Steps per paper:
  1. Fetch fulltext via PMC (save to data/fulltext/{pmid}.txt)
  2. Extract entities via LLM (Sonnet subagent via UnifiedPDFProcessor)
  3. Validate chunks via ChunkValidator
  4. Import to Neo4j: Paper node, relationships, embeddings, chunks
  5. Set evidence_level from study_design and set sub_domain

Usage:
    cd /Users/sangminpark/Documents/rag_research
    PYTHONPATH=./src python3 scripts/import_esi_burst.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Setup
os.chdir("/Users/sangminpark/Documents/rag_research")
sys.path.insert(0, "src")

# Load .env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("import_esi_burst")

# Imports
from graph.neo4j_client import Neo4jClient, Neo4jConfig
from graph.relationship_builder import RelationshipBuilder
from graph.entity_normalizer import EntityNormalizer
from builder.unified_pdf_processor import UnifiedPDFProcessor
from builder.pubmed_processor import (
    PubMedPaperProcessor,
    PUBMED_PAPER_PREFIX,
)
from builder.pubmed_enricher import BibliographicMetadata
from builder.pmc_fulltext_fetcher import PMCFullTextFetcher
from core.embedding import OpenAIEmbeddingGenerator

# ── Study design / title -> evidence level mapping ──
def infer_el_from_title(title: str) -> str:
    t = title.lower()
    if "meta-analysis" in t or "meta analysis" in t:
        return "1a"
    if "systematic review" in t:
        return "1a"
    if "randomized" in t or "randomised" in t:
        return "1b"
    if "prospective" in t:
        return "2a"
    if "retrospective" in t:
        return "2b"
    if "case report" in t:
        return "4"
    if "case series" in t:
        return "3"
    if "finite element" in t or "biomechanical" in t:
        return "5"
    return "2b"  # default for clinical studies


# ── Tracking Stats ──
@dataclass
class ImportStats:
    papers_imported: int = 0
    papers_skipped: int = 0
    entities_created: int = 0
    relationships_created: int = 0
    chunks_created: int = 0
    embeddings_generated: int = 0
    fulltext_fetched: int = 0
    errors: list = field(default_factory=list)


# ── Fulltext fetching ──
async def fetch_fulltext_for_paper(
    fetcher: PMCFullTextFetcher,
    pmid: str,
    fulltext_dir: Path,
) -> Optional[str]:
    """Try to fetch fulltext from PMC. Returns text or None."""
    txt_path = fulltext_dir / f"{pmid}.txt"

    # Check cache
    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8")
        if len(text) > 500:
            logger.info(f"  [PMID {pmid}] Using cached fulltext ({len(text)} chars)")
            return text

    try:
        result = await fetcher.fetch_fulltext(pmid)
        if result.has_full_text and result.full_text and len(result.full_text) > 500:
            txt_path.write_text(result.full_text, encoding="utf-8")
            logger.info(f"  [PMID {pmid}] Fetched PMC fulltext ({len(result.full_text)} chars)")
            return result.full_text
        else:
            logger.info(f"  [PMID {pmid}] No PMC fulltext available")
            return None
    except Exception as e:
        logger.warning(f"  [PMID {pmid}] PMC fetch error: {e}")
        return None


# ── Check duplicate ──
async def paper_exists(neo4j: Neo4jClient, paper_id: str) -> bool:
    """Check if paper already exists in Neo4j."""
    try:
        rows = await neo4j.run_query(
            "MATCH (p:Paper {paper_id: $pid}) RETURN p.paper_id AS pid LIMIT 1",
            {"pid": paper_id},
        )
        return bool(rows)
    except Exception:
        return False


# ── Process a single paper ──
async def process_single_paper(
    paper_data: dict,
    sub_domain: str,
    neo4j: Neo4jClient,
    processor: PubMedPaperProcessor,
    fetcher: PMCFullTextFetcher,
    fulltext_dir: Path,
    extracted_dir: Path,
    stats: ImportStats,
    paper_num: int,
    total: int,
) -> bool:
    """Process and import a single paper."""
    pmid = str(paper_data["pmid"])
    title = paper_data["title"]
    paper_id = f"{PUBMED_PAPER_PREFIX}{pmid}"

    logger.info(f"\n{'='*60}")
    logger.info(f"[{paper_num}/{total}] PMID {pmid}: {title[:80]}...")
    logger.info(f"{'='*60}")

    # 1. Check duplicate
    if await paper_exists(neo4j, paper_id):
        logger.info(f"  SKIP: Paper {paper_id} already exists in Neo4j")
        stats.papers_skipped += 1
        return True

    # 2. Fetch fulltext
    fulltext = await fetch_fulltext_for_paper(fetcher, pmid, fulltext_dir)
    if fulltext:
        stats.fulltext_fetched += 1

    # 3. Build BibliographicMetadata
    # Handle authors: can be a list or a comma-separated string
    raw_authors = paper_data.get("authors", [])
    if isinstance(raw_authors, str):
        authors = [a.strip() for a in raw_authors.split(",") if a.strip()]
    else:
        authors = raw_authors

    bib_meta = BibliographicMetadata(
        pmid=pmid,
        doi=paper_data.get("doi", ""),
        title=title,
        authors=authors,
        journal=paper_data.get("journal", ""),
        journal_abbrev="",
        year=paper_data.get("year", 0),
        abstract=paper_data.get("abstract", ""),
        mesh_terms=[],
        keywords=[],
        publication_types=paper_data.get("article_types", []),
        language="eng",
    )

    # 4. Determine text to process
    text_to_process = fulltext if fulltext else paper_data.get("abstract", "")
    if not text_to_process or len(text_to_process) < 100:
        logger.warning(f"  SKIP: No sufficient text for PMID {pmid}")
        stats.errors.append(f"PMID {pmid}: No text available")
        return False

    source_type = "fulltext" if fulltext else "abstract"
    logger.info(f"  Processing {source_type} ({len(text_to_process)} chars) with LLM...")

    # 5. LLM extraction
    try:
        if fulltext:
            chunks_created, success, extracted_data = await processor.process_text_with_llm(
                paper_id=paper_id,
                paper=bib_meta,
                text=fulltext,
            )
        else:
            chunks_created, success, extracted_data = await processor.process_abstract_with_llm(
                paper_id=paper_id,
                paper=bib_meta,
            )

        if not success:
            logger.warning(f"  LLM processing failed for PMID {pmid}")
            stats.errors.append(f"PMID {pmid}: LLM processing failed")
            return False

        logger.info(f"  LLM extraction successful, {chunks_created} chunks created")
        stats.chunks_created += chunks_created
        stats.embeddings_generated += chunks_created

    except Exception as e:
        logger.error(f"  LLM processing error for PMID {pmid}: {e}")
        stats.errors.append(f"PMID {pmid}: {str(e)[:100]}")
        return False

    # 6. Set sub_domain and evidence_level on Paper node
    evidence_level = infer_el_from_title(title)
    if extracted_data:
        meta = extracted_data.get("metadata", {})
        el = meta.get("evidence_level", "")
        if el:
            evidence_level = el

    try:
        await neo4j.run_write_query(
            """
            MATCH (p:Paper {paper_id: $paper_id})
            SET p.sub_domain = $sub_domain,
                p.evidence_level = $evidence_level
            """,
            {
                "paper_id": paper_id,
                "sub_domain": sub_domain,
                "evidence_level": evidence_level,
            },
        )
        logger.info(f"  Set sub_domain={sub_domain}, evidence_level={evidence_level}")
    except Exception as e:
        logger.warning(f"  Failed to set sub_domain/evidence_level: {e}")

    # 7. Save extracted data to disk
    if extracted_data:
        first_author = authors[0].split()[-1] if authors else "Unknown"
        keyword = title.split()[0:3]
        keyword_str = "_".join(keyword)[:40].replace("/", "_").replace(":", "")
        year = paper_data.get("year", 0)
        filename = f"{year}_{first_author}_{keyword_str}.json"
        save_path = extracted_dir / filename
        try:
            save_path.write_text(
                json.dumps(extracted_data, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"  Saved extracted data -> {save_path.name}")
        except Exception as e:
            logger.warning(f"  Failed to save extracted data: {e}")

    stats.papers_imported += 1

    # Count entities from extracted_data
    if extracted_data:
        spine_meta = extracted_data.get("spine_metadata", {})
        n_entities = (
            len(spine_meta.get("pathology", spine_meta.get("pathologies", [])) or [])
            + len(spine_meta.get("interventions", []) or [])
            + len(spine_meta.get("outcomes", []) or [])
        )
        stats.entities_created += n_entities
        stats.relationships_created += n_entities  # approximate

    logger.info(f"  Successfully imported PMID {pmid}")
    return True


# ── Main ──
async def main():
    start_time = time.time()
    stats = ImportStats()

    # Directories
    fulltext_dir = Path("data/fulltext")
    extracted_dir = Path("data/extracted")
    fulltext_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    # Load topic files
    topic_files = [
        ("/tmp/remaining_topic3_esi.json", "Degenerative", "ESI (remaining)"),
        ("/tmp/remaining_topic5_burst.json", "Trauma", "Burst Fracture"),
    ]

    all_papers = []
    for path, sub_domain, topic_name in topic_files:
        with open(path) as f:
            papers = json.load(f)
        all_papers.append((papers, sub_domain, topic_name))
        logger.info(f"Loaded {len(papers)} papers from {path}")

    total_papers = sum(len(p) for p, _, _ in all_papers)
    logger.info(f"Total papers to process: {total_papers}")

    # Initialize components
    logger.info("Initializing Neo4j client...")
    neo4j = Neo4jClient(Neo4jConfig.from_env())
    await neo4j.connect()

    logger.info("Initializing embedding generator (OpenAI text-embedding-3-large, 3072d)...")
    embedding_gen = OpenAIEmbeddingGenerator(batch_size=20)

    logger.info("Initializing LLM processor (Claude Sonnet)...")
    vision_proc = UnifiedPDFProcessor()

    logger.info("Initializing entity normalizer...")
    entity_norm = EntityNormalizer()

    logger.info("Initializing relationship builder...")
    rel_builder = RelationshipBuilder(neo4j, entity_norm)

    logger.info("Initializing PubMed paper processor...")
    processor = PubMedPaperProcessor(
        neo4j_client=neo4j,
        embedding_generator=embedding_gen,
        vision_processor=vision_proc,
        entity_normalizer=entity_norm,
        relationship_builder=rel_builder,
    )

    logger.info("Initializing PMC fulltext fetcher...")
    fetcher = PMCFullTextFetcher()

    # Process each topic sequentially
    running_count = 0
    for papers, sub_domain, topic_name in all_papers:
        logger.info(f"\n{'#'*60}")
        logger.info(f"# TOPIC: {topic_name} ({len(papers)} papers, sub_domain={sub_domain})")
        logger.info(f"{'#'*60}")

        for idx, paper in enumerate(papers):
            await process_single_paper(
                paper, sub_domain, neo4j, processor, fetcher,
                fulltext_dir, extracted_dir, stats,
                running_count + idx + 1, total_papers,
            )
            # Small delay to avoid rate limits
            await asyncio.sleep(1.0)

        running_count += len(papers)

    # Close connections
    await neo4j.close()
    if hasattr(fetcher, '_client') and fetcher._client:
        await fetcher._client.aclose()

    elapsed = time.time() - start_time

    # Print final stats
    print(f"\n{'='*60}")
    print(f"  IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Time elapsed:        {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"  Papers imported:     {stats.papers_imported}")
    print(f"  Papers skipped:      {stats.papers_skipped}")
    print(f"  Fulltext fetched:    {stats.fulltext_fetched}")
    print(f"  Entities created:    {stats.entities_created}")
    print(f"  Relationships:       {stats.relationships_created}")
    print(f"  Chunks created:      {stats.chunks_created}")
    print(f"  Embeddings generated:{stats.embeddings_generated}")
    print(f"{'='*60}")
    if stats.errors:
        print(f"\n  Errors ({len(stats.errors)}):")
        for err in stats.errors:
            print(f"    - {err}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
