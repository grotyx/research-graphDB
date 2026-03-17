#!/usr/bin/env python3
"""Import Topics 4-7 into Neo4j.

Pipeline:
  1. Fetch fulltext via PMC (save to data/fulltext/{pmid}.txt)
  2. Extract entities via Claude Sonnet (save to data/extracted/)
  3. Validate chunks via ChunkValidator
  4. Import to Neo4j (Paper nodes, relationships, embeddings, chunks)

Usage:
    PYTHONPATH=./src python3 scripts/import_topics_4to7.py
    PYTHONPATH=./src python3 scripts/import_topics_4to7.py --dry-run
    PYTHONPATH=./src python3 scripts/import_topics_4to7.py --skip-extraction
    PYTHONPATH=./src python3 scripts/import_topics_4to7.py --topic 4
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# Directories
FULLTEXT_DIR = PROJECT_ROOT / "data" / "fulltext"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

# Topic definitions
TOPICS = {
    4: {
        "file": "/tmp/import_topic4_odontoid.json",
        "name": "Odontoid Fracture",
        "sub_domain": "Trauma",
    },
    5: {
        "file": "/tmp/import_topic5_burst.json",
        "name": "Burst Fracture",
        "sub_domain": "Trauma",
    },
    6: {
        "file": "/tmp/import_topic6_tumor.json",
        "name": "SINS/Tumor",
        "sub_domain": "Tumor",
    },
    7: {
        "file": "/tmp/import_topic7_osteotomy.json",
        "name": "PSO/VCR Osteotomy",
        "sub_domain": "Deformity",
    },
}

# Evidence level mapping
EVIDENCE_MAP = {
    "Meta-Analysis": "1a",
    "Systematic Review": "1a",
    "Systematic review": "1a",
    "meta-analysis": "1a",
    "systematic-review": "1a",
    "Randomized Controlled Trial": "1b",
    "RCT": "1b",
    "Equivalence Trial": "1b",
    "Clinical Trial": "2a",
    "Clinical Trial, Phase II": "2a",
    "Prospective Cohort Study": "2a",
    "prospective-cohort": "2a",
    "Multicenter Study": "2a",
    "Retrospective Cohort Study": "2b",
    "retrospective-cohort": "2b",
    "Observational Study": "2b",
    "Comparative Study": "2b",
    "Case Series": "3",
    "case-series": "3",
    "Case Reports": "4",
    "case-report": "4",
    "Review": "4",
    "Expert Opinion": "4",
    "expert-opinion": "4",
}


def infer_evidence_level(article_types: list, title: str, extracted_level: str = "") -> str:
    """Infer evidence level from article types and title."""
    # Check extracted level first
    if extracted_level and extracted_level in ("1a", "1b", "2a", "2b", "3", "4", "5"):
        return extracted_level

    # Check article types (priority order)
    priority_order = [
        "Meta-Analysis", "Systematic Review", "Randomized Controlled Trial",
        "Equivalence Trial", "Clinical Trial, Phase II", "Clinical Trial",
        "Multicenter Study", "Observational Study", "Comparative Study",
        "Case Reports", "Review",
    ]
    for at in priority_order:
        if at in article_types:
            return EVIDENCE_MAP.get(at, "4")

    # Title fallback
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
    if "finite element" in t or "biomechan" in t or "cadaver" in t:
        return "5"

    return "4"


def infer_study_design(article_types: list, title: str) -> str:
    """Infer study design from article types and title."""
    t = title.lower()
    at_set = set(article_types)

    if "Meta-Analysis" in at_set:
        return "Meta-Analysis"
    if "Systematic Review" in at_set or "systematic review" in t:
        return "Systematic Review"
    if "Randomized Controlled Trial" in at_set or "Equivalence Trial" in at_set:
        return "Randomized Controlled Trial"
    if "randomized" in t or "randomised" in t:
        return "Randomized Controlled Trial"
    if "prospective" in t:
        return "Prospective Cohort Study"
    if "retrospective" in t:
        return "Retrospective Cohort Study"
    if "Observational Study" in at_set:
        return "Observational Study"
    if "Comparative Study" in at_set:
        return "Comparative Study"
    if "Case Reports" in at_set or "case report" in t:
        return "Case Report"
    if "Review" in at_set:
        return "Narrative Review"
    if "Clinical Trial" in at_set or "Clinical Trial, Phase II" in at_set:
        return "Clinical Trial"
    if "Multicenter Study" in at_set:
        return "Multicenter Study"

    return "Other"


# ============================================================
# Step 1: Fetch Fulltext via PMC
# ============================================================

async def fetch_fulltexts(papers: list) -> dict:
    """Fetch fulltext for papers via PMC. Returns {pmid: text}."""
    from builder.pmc_fulltext_fetcher import PMCFullTextFetcher

    fetcher = PMCFullTextFetcher()
    results = {}

    for paper in papers:
        pmid = paper["pmid"]
        cache_path = FULLTEXT_DIR / f"{pmid}.txt"

        # Check cache
        if cache_path.exists():
            text = cache_path.read_text()
            if len(text.strip()) > 100:
                results[pmid] = text
                logger.info("  [CACHED] PMID %s fulltext (%d chars)", pmid, len(text))
                continue

        # Try PMC
        try:
            ft = await fetcher.fetch_fulltext(pmid)
            if ft.has_full_text:
                text = ft.full_text
                cache_path.write_text(text)
                results[pmid] = text
                logger.info("  [PMC] PMID %s fulltext fetched (%d chars)", pmid, len(text))
            else:
                # Fall back to abstract
                abstract = paper.get("abstract", "")
                if abstract:
                    fallback_text = f"Title: {paper['title']}\n\nAbstract: {abstract}"
                    cache_path.write_text(fallback_text)
                    results[pmid] = fallback_text
                    logger.info("  [ABSTRACT] PMID %s no fulltext, using abstract (%d chars)", pmid, len(abstract))
                else:
                    logger.warning("  [SKIP] PMID %s no fulltext or abstract", pmid)
        except Exception as e:
            logger.warning("  [ERROR] PMID %s PMC fetch failed: %s", pmid, e)
            # Fall back to abstract
            abstract = paper.get("abstract", "")
            if abstract:
                fallback_text = f"Title: {paper['title']}\n\nAbstract: {abstract}"
                cache_path.write_text(fallback_text)
                results[pmid] = fallback_text
                logger.info("  [ABSTRACT] PMID %s using abstract fallback (%d chars)", pmid, len(abstract))

        await asyncio.sleep(0.3)  # Rate limit

    return results


# ============================================================
# Step 2: Extract entities via Claude Sonnet
# ============================================================

def _get_extraction_filename(paper: dict) -> str:
    """Generate filename for extracted JSON: {year}_{first_author}_{keyword}.json"""
    year = paper.get("year", "0000")
    authors = paper.get("authors", "Unknown")
    first_author = authors.split(",")[0].strip().split(" ")[-1] if authors else "Unknown"
    # Clean author name
    first_author = re.sub(r'[^a-zA-Z]', '', first_author)[:20]

    # Extract keyword from title
    title = paper.get("title", "")
    # Get first meaningful word(s)
    stop_words = {"the", "a", "an", "of", "in", "for", "and", "with", "on", "to", "by", "is", "are", "was", "were"}
    words = [w for w in re.findall(r'[A-Za-z]+', title) if w.lower() not in stop_words]
    keyword = "_".join(words[:3]) if words else "paper"
    keyword = keyword[:40]

    return f"{year}_{first_author}_{keyword}.json"


async def extract_entities_for_paper(
    paper: dict, text: str, sub_domain: str, semaphore: asyncio.Semaphore
) -> dict | None:
    """Extract entities from a single paper using Claude Sonnet."""
    import anthropic

    pmid = paper["pmid"]
    filename = _get_extraction_filename(paper)
    filepath = EXTRACTED_DIR / filename

    # Check cache
    if filepath.exists():
        try:
            with open(filepath) as f:
                data = json.load(f)
            logger.info("  [CACHED] PMID %s -> %s", pmid, filename)
            return data
        except json.JSONDecodeError:
            pass  # Re-extract if corrupted

    async with semaphore:
        try:
            # Load extraction prompt
            from builder.unified_pdf_processor import EXTRACTION_PROMPT

            # Prepare text with metadata context
            context = f"""Paper Information:
- Title: {paper['title']}
- Authors: {paper.get('authors', 'Unknown')}
- Journal: {paper.get('journal', 'Unknown')}
- Year: {paper.get('year', 'Unknown')}
- PMID: {pmid}
- DOI: {paper.get('doi', '')}
- Article Types: {', '.join(paper.get('article_types', []))}
- Sub-domain: {sub_domain}

Full Text:
{text[:30000]}"""  # Limit to ~30k chars to stay within token limits

            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            response = client.messages.create(
                model=os.getenv("CLAUDE_FALLBACK_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=8000,
                messages=[
                    {
                        "role": "user",
                        "content": f"{EXTRACTION_PROMPT}\n\n---\n\n{context}"
                    }
                ],
                temperature=0.1,
            )

            response_text = response.content[0].text

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.error("  [ERROR] PMID %s: No JSON in response", pmid)
                return None

            data = json.loads(json_match.group())

            # Inject PMID and sub_domain
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["pmid"] = pmid
            data["metadata"]["doi"] = paper.get("doi", "")

            if "spine_metadata" not in data:
                data["spine_metadata"] = {}
            data["spine_metadata"]["sub_domains"] = [sub_domain]

            # Save
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info("  [EXTRACTED] PMID %s -> %s (%d chunks)", pmid, filename, len(data.get("chunks", [])))
            return data

        except json.JSONDecodeError as e:
            logger.error("  [ERROR] PMID %s: JSON parse error: %s", pmid, e)
            return None
        except Exception as e:
            logger.error("  [ERROR] PMID %s: Extraction failed: %s", pmid, e)
            return None


async def extract_all_papers(papers: list, texts: dict, sub_domain: str) -> dict:
    """Extract entities for all papers (5 concurrent)."""
    semaphore = asyncio.Semaphore(5)
    results = {}

    tasks = []
    for paper in papers:
        pmid = paper["pmid"]
        text = texts.get(pmid, "")
        if not text:
            text = f"Title: {paper['title']}\n\nAbstract: {paper.get('abstract', '')}"
        tasks.append((pmid, extract_entities_for_paper(paper, text, sub_domain, semaphore)))

    for pmid, task in tasks:
        result = await task
        if result:
            results[pmid] = result

    return results


# ============================================================
# Step 3: Validate Chunks
# ============================================================

def validate_chunks(extracted: dict) -> dict:
    """Validate chunks using ChunkValidator. Returns stats."""
    from builder.chunk_validator import ChunkValidator

    validator = ChunkValidator()
    stats = {"total_papers": 0, "total_chunks_before": 0, "total_chunks_after": 0, "rejected": 0, "demoted": 0}

    for pmid, data in extracted.items():
        chunks = data.get("chunks", [])
        if not chunks:
            continue

        stats["total_papers"] += 1
        stats["total_chunks_before"] += len(chunks)

        validated = validator.validate_chunks(chunks)
        data["chunks"] = validated
        stats["total_chunks_after"] += len(validated)

    stats["rejected"] = stats["total_chunks_before"] - stats["total_chunks_after"]

    vstats = validator.get_validation_stats()
    stats["demoted"] = vstats.tier_demotions if hasattr(vstats, 'tier_demotions') else 0

    return stats


# ============================================================
# Step 4: Import to Neo4j
# ============================================================

async def import_to_neo4j(
    papers: list,
    extracted: dict,
    sub_domain: str,
    neo4j,
    existing_pmids: set,
    dry_run: bool = False,
) -> dict:
    """Import papers and entities into Neo4j."""
    from openai import OpenAI

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    stats = {
        "papers": 0, "skipped": 0, "entities": 0, "relations": 0,
        "chunks": 0, "embeddings": 0,
    }

    for paper in papers:
        pmid = str(paper["pmid"])
        paper_id = f"pubmed_{pmid}"

        if pmid in existing_pmids:
            logger.info("  [SKIP] PMID %s already exists", pmid)
            stats["skipped"] += 1
            continue

        data = extracted.get(pmid, {})
        spine_meta = data.get("spine_metadata", {})
        meta = data.get("metadata", {})

        # Determine study design and evidence level
        study_design = meta.get("study_type", "") or infer_study_design(
            paper.get("article_types", []), paper["title"]
        )
        evidence_level = infer_evidence_level(
            paper.get("article_types", []),
            paper["title"],
            meta.get("evidence_level", ""),
        )

        if dry_run:
            chunks = data.get("chunks", [])
            intv = spine_meta.get("interventions", [])
            path = spine_meta.get("pathology", [])
            outcomes = spine_meta.get("outcomes", [])
            logger.info(
                "  [DRY-RUN] PMID %s | %s | I:%d P:%d O:%d C:%d | %s | EL:%s",
                pmid, paper["title"][:50],
                len(intv), len(path) if isinstance(path, list) else 1,
                len(outcomes), len(chunks),
                study_design, evidence_level,
            )
            stats["papers"] += 1
            continue

        # ---- 4.1 Create Paper node ----
        abstract = paper.get("abstract", "")
        summary = spine_meta.get("summary", "") or spine_meta.get("main_conclusion", "")

        props = {
            "paper_id": paper_id,
            "title": paper["title"],
            "authors": paper.get("authors", ""),
            "year": int(paper["year"]) if paper.get("year") else 0,
            "journal": paper.get("journal", ""),
            "doi": paper.get("doi", ""),
            "pmid": pmid,
            "abstract": abstract[:2000],
            "summary": summary[:1000] if summary else "",
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
        existing_pmids.add(pmid)

        # ---- 4.2 Build entity relationships ----
        # Interventions -> INVESTIGATES
        interventions = spine_meta.get("interventions", [])
        if isinstance(interventions, str):
            interventions = [interventions]
        for intv in interventions:
            if not intv or not isinstance(intv, str):
                continue
            await neo4j.run_write_query(
                """MATCH (p:Paper {paper_id: $pid})
                   MERGE (e:Intervention {name: $name})
                   MERGE (p)-[:INVESTIGATES]->(e)""",
                {"pid": paper_id, "name": intv},
            )
            stats["entities"] += 1

        # Pathology -> STUDIES
        pathologies = spine_meta.get("pathology", [])
        if isinstance(pathologies, str):
            pathologies = [pathologies]
        for path in pathologies:
            if not path or not isinstance(path, str):
                continue
            await neo4j.run_write_query(
                """MATCH (p:Paper {paper_id: $pid})
                   MERGE (e:Pathology {name: $name})
                   MERGE (p)-[:INVESTIGATES]->(e)
                   MERGE (p)-[:STUDIES]->(e)""",
                {"pid": paper_id, "name": path},
            )
            stats["entities"] += 1
            stats["relations"] += 1

        # Outcomes -> INVESTIGATES
        outcomes = spine_meta.get("outcomes", [])
        if isinstance(outcomes, list):
            for outc in outcomes:
                outc_name = outc.get("name", "") if isinstance(outc, dict) else str(outc)
                if not outc_name:
                    continue
                await neo4j.run_write_query(
                    """MATCH (p:Paper {paper_id: $pid})
                       MERGE (e:Outcome {name: $name})
                       MERGE (p)-[:INVESTIGATES]->(e)""",
                    {"pid": paper_id, "name": outc_name},
                )
                stats["entities"] += 1

        # Anatomy
        anatomy_region = spine_meta.get("anatomy_region", "")
        if anatomy_region and isinstance(anatomy_region, str):
            await neo4j.run_write_query(
                """MATCH (p:Paper {paper_id: $pid})
                   MERGE (e:Anatomy {name: $name})
                   MERGE (p)-[:INVESTIGATES]->(e)""",
                {"pid": paper_id, "name": anatomy_region},
            )
            stats["entities"] += 1

        # ---- 4.3 TREATS relationships (Intervention -> Pathology) ----
        for intv in interventions:
            if not intv or not isinstance(intv, str):
                continue
            for path in pathologies:
                if not path or not isinstance(path, str):
                    continue
                await neo4j.run_write_query(
                    """MERGE (i:Intervention {name: $int_name})
                       MERGE (p:Pathology {name: $path_name})
                       MERGE (i)-[t:TREATS]->(p)
                       ON CREATE SET t.paper_count = 1
                       ON MATCH SET t.paper_count = t.paper_count + 1""",
                    {"int_name": intv, "path_name": path},
                )
                stats["relations"] += 1

        # ---- 4.4 AFFECTS relationships (Intervention -> Outcome) ----
        outcome_names = []
        if isinstance(outcomes, list):
            for outc in outcomes:
                name = outc.get("name", "") if isinstance(outc, dict) else str(outc)
                if name:
                    outcome_names.append(name)

        for intv in interventions:
            if not intv or not isinstance(intv, str):
                continue
            for outc_name in outcome_names:
                await neo4j.run_write_query(
                    """MERGE (i:Intervention {name: $int_name})
                       MERGE (o:Outcome {name: $out_name})
                       MERGE (i)-[a:AFFECTS]->(o)
                       ON CREATE SET a.paper_count = 1
                       ON MATCH SET a.paper_count = a.paper_count + 1""",
                    {"int_name": intv, "out_name": outc_name},
                )
                stats["relations"] += 1

        # ---- 4.5 Create Chunk nodes with embeddings ----
        chunks = data.get("chunks", [])
        for idx, chunk in enumerate(chunks):
            content = chunk.get("content", "")
            if not content or len(content.strip()) < 30:
                continue

            chunk_id = f"{paper_id}_chunk_{idx}"
            section_type = chunk.get("section_type", "unknown")
            tier = chunk.get("tier", "tier2")
            content_type = chunk.get("content_type", "text")
            is_key_finding = chunk.get("is_key_finding", False)
            summary = chunk.get("summary", "")
            keywords = chunk.get("keywords", [])

            # Generate contextual embedding
            year = paper.get("year", "")
            prefix = f"{paper['title'][:80]} | {section_type} | {year}"
            embed_text = f"{prefix}\n{content}"[:8000]

            try:
                resp = openai_client.embeddings.create(
                    model="text-embedding-3-large",
                    input=embed_text,
                    dimensions=3072,
                )
                embedding = resp.data[0].embedding
                stats["embeddings"] += 1
            except Exception as e:
                logger.warning("  Embedding failed for chunk %s: %s", chunk_id, e)
                embedding = None

            chunk_props = {
                "chunk_id": chunk_id,
                "content": content,
                "section_type": section_type,
                "content_type": content_type,
                "tier": tier,
                "is_key_finding": is_key_finding,
                "summary": summary,
                "keywords": keywords if isinstance(keywords, list) else [],
                "paper_id": paper_id,
                "created_at": datetime.now().isoformat(),
            }

            # Stats
            chunk_stats = chunk.get("statistics", {})
            if isinstance(chunk_stats, dict):
                if chunk_stats.get("p_value"):
                    chunk_props["p_value"] = str(chunk_stats["p_value"])
                if chunk_stats.get("is_significant") is not None:
                    chunk_props["is_significant"] = chunk_stats["is_significant"]

            if embedding:
                await neo4j.run_write_query(
                    """MATCH (p:Paper {paper_id: $pid})
                       MERGE (c:Chunk {chunk_id: $cid})
                       SET c += $props, c.embedding = $emb
                       MERGE (p)-[:HAS_CHUNK]->(c)""",
                    {"pid": paper_id, "cid": chunk_id, "props": chunk_props, "emb": embedding},
                )
            else:
                await neo4j.run_write_query(
                    """MATCH (p:Paper {paper_id: $pid})
                       MERGE (c:Chunk {chunk_id: $cid})
                       SET c += $props
                       MERGE (p)-[:HAS_CHUNK]->(c)""",
                    {"pid": paper_id, "cid": chunk_id, "props": chunk_props},
                )
            stats["chunks"] += 1

        # ---- 4.6 Abstract embedding on Paper node ----
        if abstract and len(abstract.strip()) > 100:
            try:
                resp = openai_client.embeddings.create(
                    model="text-embedding-3-large",
                    input=abstract[:8000],
                    dimensions=3072,
                )
                abs_embedding = resp.data[0].embedding
                await neo4j.run_write_query(
                    "MATCH (p:Paper {paper_id: $pid}) SET p.abstract_embedding = $emb",
                    {"pid": paper_id, "emb": abs_embedding},
                )
                stats["embeddings"] += 1
            except Exception as e:
                logger.warning("  Abstract embedding failed for %s: %s", paper_id, e)

        logger.info(
            "  [IMPORTED] %s | I:%d P:%d O:%d C:%d | %s | EL:%s",
            paper_id,
            len(interventions), len(pathologies),
            len(outcome_names), len(chunks),
            study_design[:20], evidence_level,
        )

    return stats


# ============================================================
# Main
# ============================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import Topics 4-7 into Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip LLM extraction (use cached)")
    parser.add_argument("--skip-fulltext", action="store_true", help="Skip PMC fulltext fetch")
    parser.add_argument("--topic", type=int, help="Process only specific topic (4-7)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Initialize Neo4j
    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    # Get existing PMIDs
    existing_pmids = set()
    try:
        rows = await neo4j.run_query(
            "MATCH (p:Paper) WHERE p.pmid IS NOT NULL RETURN p.pmid AS pmid"
        )
        for r in rows:
            if r.get("pmid"):
                existing_pmids.add(str(r["pmid"]))
        logger.info("Found %d existing papers in Neo4j", len(existing_pmids))
    except Exception as e:
        logger.warning("Could not check existing PMIDs: %s", e)

    # Determine which topics to process
    topics_to_process = [args.topic] if args.topic else [4, 5, 6, 7]

    total_stats = {
        "papers": 0, "skipped": 0, "entities": 0, "relations": 0,
        "chunks": 0, "embeddings": 0,
    }

    for topic_num in topics_to_process:
        topic = TOPICS[topic_num]
        logger.info("=" * 70)
        logger.info("TOPIC %d: %s (sub_domain: %s)", topic_num, topic["name"], topic["sub_domain"])
        logger.info("=" * 70)

        # Load papers
        with open(topic["file"]) as f:
            papers = json.load(f)
        logger.info("Loaded %d papers from %s", len(papers), topic["file"])

        # Check duplicates
        new_papers = []
        for p in papers:
            if str(p["pmid"]) in existing_pmids:
                logger.info("  [DUPLICATE] PMID %s already in Neo4j, will skip", p["pmid"])
            new_papers.append(p)  # Still include for extraction

        # Step 1: Fetch fulltext
        logger.info("\n--- Step 1: Fetch Fulltext ---")
        if args.skip_fulltext:
            logger.info("  Skipping fulltext fetch (--skip-fulltext)")
            texts = {}
            for p in papers:
                cache_path = FULLTEXT_DIR / f"{p['pmid']}.txt"
                if cache_path.exists():
                    texts[p["pmid"]] = cache_path.read_text()
                else:
                    texts[p["pmid"]] = f"Title: {p['title']}\n\nAbstract: {p.get('abstract', '')}"
        else:
            texts = await fetch_fulltexts(papers)
        logger.info("  Fulltext available for %d/%d papers", len(texts), len(papers))

        # Step 2: Extract entities
        logger.info("\n--- Step 2: Extract Entities (Sonnet) ---")
        if args.skip_extraction:
            logger.info("  Skipping extraction (--skip-extraction), loading cached...")
            extracted = {}
            for p in papers:
                filename = _get_extraction_filename(p)
                filepath = EXTRACTED_DIR / filename
                if filepath.exists():
                    try:
                        with open(filepath) as f:
                            extracted[p["pmid"]] = json.load(f)
                        logger.info("  [CACHED] PMID %s -> %s", p["pmid"], filename)
                    except json.JSONDecodeError:
                        logger.warning("  [CORRUPT] %s", filename)
        else:
            extracted = await extract_all_papers(papers, texts, topic["sub_domain"])
        logger.info("  Extracted %d/%d papers", len(extracted), len(papers))

        # Step 3: Validate chunks
        logger.info("\n--- Step 3: Validate Chunks ---")
        val_stats = validate_chunks(extracted)
        logger.info(
            "  Validated: %d papers, %d->%d chunks (rejected: %d)",
            val_stats["total_papers"],
            val_stats["total_chunks_before"],
            val_stats["total_chunks_after"],
            val_stats["rejected"],
        )

        # Step 4: Import to Neo4j
        logger.info("\n--- Step 4: Import to Neo4j ---")
        import_stats = await import_to_neo4j(
            papers, extracted, topic["sub_domain"], neo4j,
            existing_pmids, dry_run=args.dry_run,
        )

        for k, v in import_stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

        logger.info(
            "\nTopic %d complete: papers=%d, skipped=%d, entities=%d, relations=%d, chunks=%d, embeddings=%d",
            topic_num,
            import_stats["papers"], import_stats["skipped"],
            import_stats["entities"], import_stats["relations"],
            import_stats["chunks"], import_stats["embeddings"],
        )

    await neo4j.__aexit__(None, None, None)

    # Print final summary
    print("\n" + "=" * 70)
    print(f"{'DRY-RUN ' if args.dry_run else ''}IMPORT COMPLETE - ALL TOPICS")
    print("=" * 70)
    print(f"  Papers imported:    {total_stats['papers']}")
    print(f"  Papers skipped:     {total_stats['skipped']}")
    print(f"  Entities created:   {total_stats['entities']}")
    print(f"  Relations created:  {total_stats['relations']}")
    print(f"  Chunks created:     {total_stats['chunks']}")
    print(f"  Embeddings generated: {total_stats['embeddings']}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
