#!/usr/bin/env python3
"""Create chunks for papers that only have abstracts.

초록만 있는 논문들에 대해 청크를 생성하고 임베딩합니다.
"""

import asyncio
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# OpenAI 임베딩
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available, chunks will be created without embeddings")


async def get_papers_without_chunks(client: Neo4jClient) -> List[Dict[str, Any]]:
    """청크 없는 논문 조회."""
    query = """
    MATCH (p:Paper)
    WHERE NOT (p)-[:HAS_CHUNK]->() AND p.abstract IS NOT NULL AND p.abstract <> ''
    RETURN p.paper_id as paper_id,
           p.title as title,
           p.abstract as abstract,
           p.evidence_level as evidence_level
    """
    return await client.run_query(query)


async def create_chunk_for_paper(
    client: Neo4jClient,
    paper_id: str,
    title: str,
    abstract: str,
    evidence_level: str,
    embedding: List[float] = None
) -> bool:
    """논문에 대한 청크 생성."""
    # 청크 ID 생성
    chunk_id = f"{paper_id}_abstract"

    # 청크 텍스트: 제목 + 초록
    chunk_text = f"{title}\n\n{abstract}" if title else abstract

    # 청크 노드 생성 쿼리
    if embedding:
        query = """
        MATCH (p:Paper {paper_id: $paper_id})
        CREATE (c:Chunk {
            chunk_id: $chunk_id,
            content: $content,
            tier: 1,
            source_type: 'abstract',
            evidence_level: $evidence_level,
            embedding: $embedding
        })
        CREATE (p)-[:HAS_CHUNK]->(c)
        RETURN c.chunk_id as created
        """
        params = {
            "paper_id": paper_id,
            "chunk_id": chunk_id,
            "content": chunk_text,
            "evidence_level": evidence_level or "5",
            "embedding": embedding
        }
    else:
        query = """
        MATCH (p:Paper {paper_id: $paper_id})
        CREATE (c:Chunk {
            chunk_id: $chunk_id,
            content: $content,
            tier: 1,
            source_type: 'abstract',
            evidence_level: $evidence_level
        })
        CREATE (p)-[:HAS_CHUNK]->(c)
        RETURN c.chunk_id as created
        """
        params = {
            "paper_id": paper_id,
            "chunk_id": chunk_id,
            "content": chunk_text,
            "evidence_level": evidence_level or "5"
        }

    result = await client.run_query(query, params)
    return len(result) > 0


def get_embedding(text: str, openai_client) -> List[float]:
    """OpenAI 임베딩 생성."""
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=text[:8000]  # 토큰 제한
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None


async def main():
    """메인 실행."""
    # OpenAI 클라이언트 초기화
    openai_client = None
    if OPENAI_AVAILABLE:
        import os
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            openai_client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized")
        else:
            logger.warning("OPENAI_API_KEY not set")

    async with Neo4jClient() as client:
        papers = await get_papers_without_chunks(client)
        logger.info(f"Found {len(papers)} papers without chunks")

        created_count = 0
        for paper in papers:
            paper_id = paper["paper_id"]
            title = paper.get("title") or ""
            abstract = paper.get("abstract") or ""
            evidence_level = paper.get("evidence_level")

            if not abstract:
                continue

            # 임베딩 생성
            embedding = None
            if openai_client:
                chunk_text = f"{title}\n\n{abstract}" if title else abstract
                embedding = get_embedding(chunk_text, openai_client)

            # 청크 생성
            success = await create_chunk_for_paper(
                client, paper_id, title, abstract, evidence_level, embedding
            )

            if success:
                created_count += 1
                if created_count % 10 == 0:
                    logger.info(f"Created {created_count} chunks...")

        logger.info(f"\n=== Chunk Creation Complete ===")
        logger.info(f"Chunks created: {created_count}")


if __name__ == "__main__":
    asyncio.run(main())
