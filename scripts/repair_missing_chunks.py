#!/usr/bin/env python3
"""HAS_CHUNK 관계 누락 논문 복구 스크립트.

HAS_CHUNK 관계가 없는 Paper 노드를 찾아 Chunk 노드와 임베딩을 생성합니다.

복구 전략 (우선순위):
  1. data/extracted/<paper_id>*.json 에 저장된 chunks 활용 (LLM 호출 불필요)
  2. Paper 노드의 abstract 텍스트로 단일 청크 생성

Usage:
    PYTHONPATH=./src python3 scripts/repair_missing_chunks.py
    PYTHONPATH=./src python3 scripts/repair_missing_chunks.py --dry-run
    PYTHONPATH=./src python3 scripts/repair_missing_chunks.py --max-concurrent 3
    PYTHONPATH=./src python3 scripts/repair_missing_chunks.py --paper-ids pubmed_123,pubmed_456
"""

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from graph.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("repair_missing_chunks")

# Extracted JSON directory
EXTRACTED_DIR = Path(__file__).parent.parent / "data" / "extracted"


def _init_openai():
    """OpenAI 클라이언트 초기화. 실패 시 None 반환."""
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — chunks will be created without embeddings")
            return None
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized (text-embedding-3-large)")
        return client
    except ImportError:
        logger.warning("openai package not installed — chunks will be created without embeddings")
        return None


def _get_embedding(text: str, openai_client) -> list[float] | None:
    """OpenAI 임베딩 생성. 실패 시 None."""
    if not openai_client:
        return None
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text[:8000],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


def _get_embedding_batch(texts: list[str], openai_client) -> list[list[float] | None]:
    """OpenAI 임베딩 일괄 생성."""
    if not openai_client or not texts:
        return [None] * len(texts)
    try:
        truncated = [t[:8000] for t in texts]
        response = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=truncated,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        return [None] * len(texts)


async def get_papers_without_chunks(
    neo4j_client: Neo4jClient,
    paper_ids: list[str] | None = None,
) -> list[dict]:
    """HAS_CHUNK 관계 없는 논문 조회."""
    if paper_ids:
        query = """
        MATCH (p:Paper)
        WHERE p.paper_id IN $paper_ids
          AND NOT (p)-[:HAS_CHUNK]->()
        RETURN p.paper_id AS paper_id,
               p.title AS title,
               p.abstract AS abstract,
               p.evidence_level AS evidence_level
        ORDER BY p.paper_id
        """
        result = await neo4j_client.run_query(query, {"paper_ids": paper_ids})
    else:
        query = """
        MATCH (p:Paper)
        WHERE NOT (p)-[:HAS_CHUNK]->()
          AND p.abstract IS NOT NULL AND p.abstract <> ''
        RETURN p.paper_id AS paper_id,
               p.title AS title,
               p.abstract AS abstract,
               p.evidence_level AS evidence_level
        ORDER BY p.paper_id
        """
        result = await neo4j_client.run_query(query)

    papers = []
    for r in result:
        abstract = r.get("abstract", "") or ""
        if len(abstract) < 20:
            logger.warning(f"Skipping {r['paper_id']}: abstract too short ({len(abstract)} chars)")
            continue
        papers.append(dict(r))
    return papers


def _find_extracted_json(paper_id: str) -> dict | None:
    """data/extracted/에서 paper_id에 해당하는 JSON 파일 로드.

    파일명 패턴:
      - {paper_id}.json
      - {paper_id}_repair.json
      - {anything}_{paper_id}.json (e.g., 2024_Author_Title_pubmed_12345.json)
    """
    if not EXTRACTED_DIR.exists():
        return None

    # 직접 매칭 시도
    for suffix in ("", "_repair"):
        candidate = EXTRACTED_DIR / f"{paper_id}{suffix}.json"
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("chunks"):
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read {candidate}: {e}")

    # 글로브 매칭 (paper_id가 파일명에 포함된 경우)
    for candidate in EXTRACTED_DIR.glob(f"*{paper_id}*.json"):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("chunks"):
                return data
        except (json.JSONDecodeError, OSError):
            continue

    return None


def _extract_chunk_text(chunk: dict) -> str:
    """청크에서 텍스트 추출."""
    return chunk.get("content") or chunk.get("text") or chunk.get("summary") or ""


async def repair_single_paper(
    paper: dict,
    neo4j_client: Neo4jClient,
    openai_client,
    dry_run: bool = False,
) -> dict:
    """단일 논문의 HAS_CHUNK 복구."""
    paper_id = paper["paper_id"]
    title = (paper.get("title") or "")[:80]
    abstract = paper.get("abstract", "") or ""
    evidence_level = paper.get("evidence_level") or "5"
    start = time.time()

    logger.info(f"[{paper_id}] Processing: {title}...")

    # 전략 1: 기존 extracted JSON에서 chunks 로드
    extracted_data = _find_extracted_json(paper_id)
    if extracted_data and extracted_data.get("chunks"):
        raw_chunks = extracted_data["chunks"]
        chunk_texts = [_extract_chunk_text(c) for c in raw_chunks]
        chunk_texts = [t for t in chunk_texts if t.strip()]
        source = "extracted_json"
        logger.info(f"[{paper_id}] Found {len(chunk_texts)} chunks from extracted JSON")
    else:
        # 전략 2: abstract으로 단일 청크 생성
        chunk_text = f"{paper.get('title', '')}\n\n{abstract}" if paper.get("title") else abstract
        chunk_texts = [chunk_text]
        raw_chunks = [{"tier": "tier1", "section_type": "abstract"}]
        source = "abstract"
        logger.info(f"[{paper_id}] Creating single abstract chunk")

    if not chunk_texts:
        logger.warning(f"[{paper_id}] No chunk content available")
        return {"paper_id": paper_id, "success": False, "error": "No chunk content"}

    if dry_run:
        elapsed = time.time() - start
        logger.info(f"[{paper_id}] DRY RUN — would create {len(chunk_texts)} chunks (source={source})")
        return {
            "paper_id": paper_id,
            "success": True,
            "dry_run": True,
            "chunks_count": len(chunk_texts),
            "source": source,
            "elapsed": round(elapsed, 1),
        }

    # 임베딩 생성
    embeddings = _get_embedding_batch(chunk_texts, openai_client)

    # Neo4j에 청크 + HAS_CHUNK 생성
    chunks_created = 0
    for i, (text, embedding) in enumerate(zip(chunk_texts, embeddings)):
        chunk_id = f"{paper_id}_chunk_{i}"
        tier_raw = raw_chunks[i].get("tier", "tier2") if i < len(raw_chunks) else "tier2"
        chunk_tier = 1 if str(tier_raw) in ("tier1", "1") else 2
        chunk_section = (raw_chunks[i].get("section_type", "body")
                         if i < len(raw_chunks) else "body")

        if embedding:
            query = """
            MATCH (p:Paper {paper_id: $paper_id})
            CREATE (c:Chunk {
                chunk_id: $chunk_id,
                content: $content,
                tier: $tier,
                section: $section,
                evidence_level: $evidence_level,
                embedding: $embedding
            })
            CREATE (p)-[:HAS_CHUNK]->(c)
            RETURN c.chunk_id AS created
            """
            params = {
                "paper_id": paper_id,
                "chunk_id": chunk_id,
                "content": text,
                "tier": chunk_tier,
                "section": chunk_section,
                "evidence_level": evidence_level,
                "embedding": embedding,
            }
        else:
            query = """
            MATCH (p:Paper {paper_id: $paper_id})
            CREATE (c:Chunk {
                chunk_id: $chunk_id,
                content: $content,
                tier: $tier,
                section: $section,
                evidence_level: $evidence_level
            })
            CREATE (p)-[:HAS_CHUNK]->(c)
            RETURN c.chunk_id AS created
            """
            params = {
                "paper_id": paper_id,
                "chunk_id": chunk_id,
                "content": text,
                "tier": chunk_tier,
                "section": chunk_section,
                "evidence_level": evidence_level,
            }

        try:
            result = await neo4j_client.run_query(query, params)
            if result:
                chunks_created += 1
        except Exception as e:
            logger.error(f"[{paper_id}] Chunk {i} creation failed: {e}")

    elapsed = time.time() - start
    logger.info(f"[{paper_id}] Created {chunks_created}/{len(chunk_texts)} chunks ({elapsed:.1f}s)")

    return {
        "paper_id": paper_id,
        "success": chunks_created > 0,
        "chunks_created": chunks_created,
        "chunks_total": len(chunk_texts),
        "source": source,
        "has_embeddings": embeddings[0] is not None if embeddings else False,
        "elapsed": round(elapsed, 1),
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Repair papers missing HAS_CHUNK relationships"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be done without writing to Neo4j",
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=5,
        help="Max concurrent paper processing (1-10, default 5)",
    )
    parser.add_argument(
        "--paper-ids", type=str,
        help="Comma-separated paper IDs to repair (default: all missing)",
    )
    args = parser.parse_args()

    max_concurrent = max(1, min(10, args.max_concurrent))
    paper_ids = [p.strip() for p in args.paper_ids.split(",")] if args.paper_ids else None

    logger.info("=" * 60)
    logger.info("Missing HAS_CHUNK Repair Script")
    logger.info(f"  dry_run={args.dry_run}, max_concurrent={max_concurrent}")
    if paper_ids:
        logger.info(f"  target papers: {paper_ids}")
    logger.info("=" * 60)

    # OpenAI 클라이언트 (임베딩용)
    openai_client = _init_openai()

    # Neo4j 연결
    neo4j_client = Neo4jClient()
    await neo4j_client.connect()

    try:
        papers = await get_papers_without_chunks(neo4j_client, paper_ids)
        logger.info(f"Found {len(papers)} papers missing HAS_CHUNK")

        if not papers:
            logger.info("No papers missing chunks. Nothing to do.")
            return

        # 세마포어로 동시 실행 제한
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_repair(paper):
            async with semaphore:
                return await repair_single_paper(
                    paper=paper,
                    neo4j_client=neo4j_client,
                    openai_client=openai_client,
                    dry_run=args.dry_run,
                )

        start_time = time.time()
        results = await asyncio.gather(
            *[bounded_repair(p) for p in papers],
            return_exceptions=True,
        )

        # 결과 집계
        total = len(results)
        success = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failed = total - success
        total_chunks = sum(
            r.get("chunks_created", 0)
            for r in results
            if isinstance(r, dict)
        )
        from_json = sum(
            1 for r in results
            if isinstance(r, dict) and r.get("source") == "extracted_json"
        )
        from_abstract = sum(
            1 for r in results
            if isinstance(r, dict) and r.get("source") == "abstract"
        )
        elapsed = time.time() - start_time

        logger.info("")
        logger.info("=" * 60)
        logger.info("REPAIR RESULTS")
        logger.info("=" * 60)
        logger.info(f"  Total papers:      {total}")
        logger.info(f"  Success:           {success}")
        logger.info(f"  Failed:            {failed}")
        logger.info(f"  Chunks created:    {total_chunks}")
        logger.info(f"  From JSON:         {from_json}")
        logger.info(f"  From abstract:     {from_abstract}")
        logger.info(f"  Total time:        {elapsed:.1f}s")
        logger.info("=" * 60)

        # 실패 목록
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"  Exception: {r}")
            elif isinstance(r, dict) and not r.get("success"):
                logger.warning(f"  FAILED: {r.get('paper_id')} — {r.get('error', 'unknown')}")

        # 결과 JSON 저장
        results_path = Path("/tmp/repair_missing_chunks_results.json")
        serializable = []
        for r in results:
            if isinstance(r, Exception):
                serializable.append({"error": str(r)})
            else:
                serializable.append(r)
        with open(results_path, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")

    finally:
        await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(main())
