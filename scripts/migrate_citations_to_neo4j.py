"""Migrate important_citations from JSON files to Neo4j.

기존 data/extracted/*.json 파일의 important_citations를
Neo4j CITES 관계로 마이그레이션합니다.

Usage:
    PYTHONPATH=./src python3 scripts/migrate_citations_to_neo4j.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path - must be before imports
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def migrate_citations():
    """기존 JSON의 important_citations를 Neo4j로 마이그레이션."""
    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    from graph.relationship_builder import RelationshipBuilder
    from graph.entity_normalizer import EntityNormalizer
    from builder.important_citation_processor import ImportantCitationProcessor

    # Neo4j 연결 (환경변수에서 로드)
    config = Neo4jConfig.from_env()
    logger.info(f"Connecting to Neo4j: {config.uri} as {config.username}")
    client = Neo4jClient(config=config)
    await client.connect()

    # EntityNormalizer와 RelationshipBuilder
    normalizer = EntityNormalizer()
    relationship_builder = RelationshipBuilder(client, normalizer)

    # ImportantCitationProcessor
    processor = ImportantCitationProcessor(
        pubmed_email=os.getenv("NCBI_EMAIL", ""),
        pubmed_api_key=os.getenv("NCBI_API_KEY"),
        neo4j_client=client,
        relationship_builder=relationship_builder,
        min_confidence=0.7,
        max_citations=20,
        analyze_cited_abstracts=True
    )

    # JSON 파일 스캔
    extracted_dir = Path(__file__).parent.parent / "data" / "extracted"
    json_files = list(extracted_dir.glob("*.json"))

    logger.info(f"Found {len(json_files)} JSON files in {extracted_dir}")

    total_citations = 0
    total_papers_created = 0
    total_relations_created = 0
    processed_files = 0
    skipped_files = 0

    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # important_citations 확인
            citations = data.get("important_citations", [])
            if not citations:
                skipped_files += 1
                continue

            # paper_id 확인 (파일명에서 추출)
            paper_id = json_path.stem

            # 메타데이터에서 paper_id 확인
            if "metadata" in data and data["metadata"].get("pmid"):
                paper_id = f"pubmed_{data['metadata']['pmid']}"
            elif "metadata" in data and data["metadata"].get("doi"):
                doi = data["metadata"]["doi"].replace("/", "_")
                paper_id = f"doi_{doi}"

            # Neo4j에서 해당 Paper가 존재하는지 확인
            paper_check = await client.run_query(
                "MATCH (p:Paper {paper_id: $paper_id}) RETURN p.paper_id as id",
                {"paper_id": paper_id}
            )

            if not paper_check:
                logger.warning(f"Paper not found in Neo4j: {paper_id}, skipping")
                skipped_files += 1
                continue

            logger.info(f"Processing {json_path.name}: {len(citations)} citations")

            # 인용 처리
            result = await processor.process_from_integrated_citations(
                citing_paper_id=paper_id,
                citations=citations
            )

            total_citations += len(citations)
            total_papers_created += result.papers_created
            total_relations_created += result.relationships_created
            processed_files += 1

            logger.info(
                f"  -> Papers: {result.papers_created}, "
                f"Relations: {result.relationships_created}, "
                f"PubMed failures: {result.pubmed_search_failures}"
            )

        except Exception as e:
            logger.error(f"Error processing {json_path.name}: {e}")

    await client.close()

    # 결과 출력
    logger.info("=" * 60)
    logger.info("Migration Complete!")
    logger.info(f"  Files processed: {processed_files}")
    logger.info(f"  Files skipped: {skipped_files}")
    logger.info(f"  Total citations: {total_citations}")
    logger.info(f"  Papers created: {total_papers_created}")
    logger.info(f"  CITES relations: {total_relations_created}")
    logger.info("=" * 60)

    return {
        "processed_files": processed_files,
        "skipped_files": skipped_files,
        "total_citations": total_citations,
        "papers_created": total_papers_created,
        "relations_created": total_relations_created
    }


if __name__ == "__main__":
    result = asyncio.run(migrate_citations())
    print(json.dumps(result, indent=2))
