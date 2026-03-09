"""PubMed Download/API Module.

PubMed 검색, 논문 상세 정보 조회, 중복 확인 등 API 관련 기능을 제공합니다.
pubmed_bulk_processor.py에서 분리된 모듈입니다 (D-009).

Usage:
    downloader = PubMedDownloader(pubmed_client, pubmed_enricher, neo4j_client)
    papers = await downloader.search_pubmed("lumbar fusion", max_results=50)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

try:
    from builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
    from external.pubmed_client import PubMedClient, PubMedError
except ImportError:
    try:
        from src.builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
        from src.external.pubmed_client import PubMedClient, PubMedError
    except ImportError:
        pass

if TYPE_CHECKING:
    from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Paper ID prefix for PubMed-only papers
PUBMED_PAPER_PREFIX = "pubmed_"


class PubMedDownloader:
    """PubMed 검색 및 논문 다운로드 담당.

    PubMed API 호출, 논문 검색, 배치 조회, 중복 확인 등을 처리합니다.
    """

    def __init__(
        self,
        pubmed_client: PubMedClient,
        pubmed_enricher: PubMedEnricher,
        neo4j_client: "Neo4jClient",
    ):
        """PubMedDownloader 초기화.

        Args:
            pubmed_client: PubMed API 클라이언트
            pubmed_enricher: PubMed 서지 정보 강화기
            neo4j_client: Neo4j 클라이언트 (중복 확인용)
        """
        self.pubmed_client = pubmed_client
        self.pubmed_enricher = pubmed_enricher
        self.neo4j = neo4j_client

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search_pubmed(
        self,
        query: str,
        max_results: int = 50,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> list[BibliographicMetadata]:
        """PubMed에서 논문 검색.

        Args:
            query: 검색 쿼리 (PubMed 문법 지원)
            max_results: 최대 결과 수 (기본 50, 최대 500)
            year_from: 시작 연도 (선택)
            year_to: 종료 연도 (선택)
            publication_types: 출판 유형 필터 (선택)

        Returns:
            BibliographicMetadata 목록
        """
        full_query = build_search_query(
            query,
            year_from=year_from,
            year_to=year_to,
            publication_types=publication_types,
        )

        logger.info(f"Searching PubMed: {full_query[:100]}...")

        try:
            pmids = await asyncio.to_thread(
                self.pubmed_client.search,
                full_query,
                max_results=min(max_results, 500),
            )

            if not pmids:
                logger.info("No PubMed results found")
                return []

            logger.info(f"Found {len(pmids)} PMIDs, fetching details...")

            papers = await self.fetch_papers_batch(pmids)

            logger.info(f"Retrieved {len(papers)} paper details")
            return papers

        except PubMedError as e:
            logger.error(f"PubMed search error: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error in PubMed search: {e}", exc_info=True)
            raise

    async def fetch_papers_batch(
        self,
        pmids: list[str],
        batch_size: int = 5,
    ) -> list[BibliographicMetadata]:
        """논문 상세 정보를 배치로 가져오기.

        PubMed API 속도 제한:
        - API 키 없음: 3 req/sec
        - API 키 있음: 10 req/sec

        안전을 위해 5개씩 배치로 가져오고, 배치 간 1초 대기합니다.
        """
        results = []

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]

            batch_results = []
            for pmid in batch:
                try:
                    result = await self.fetch_single_paper(pmid)
                    batch_results.append(result)
                except Exception as e:
                    logger.warning(f"Failed to fetch paper {pmid}: {e}")
                await asyncio.sleep(0.15)

            results.extend(batch_results)

            if i + batch_size < len(pmids):
                await asyncio.sleep(1.0)

        return results

    async def fetch_single_paper(self, pmid: str) -> BibliographicMetadata:
        """단일 논문 상세 정보 가져오기."""
        paper = await asyncio.to_thread(
            self.pubmed_client.fetch_paper_details, pmid
        )
        return BibliographicMetadata.from_pubmed(paper, confidence=1.0)

    # =========================================================================
    # Citation Import
    # =========================================================================

    async def get_important_citations(self, paper_id: str) -> list[dict]:
        """Neo4j에서 논문의 important citations 가져오기."""
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        RETURN p.important_citations AS citations
        """
        try:
            result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})
            if result and result[0].get("citations"):
                citations = result[0]["citations"]
                if isinstance(citations, str):
                    return json.loads(citations)
                return citations
        except Exception as e:
            logger.error(f"Error fetching citations: {e}", exc_info=True)
        return []

    async def search_citation_papers(
        self,
        citations: list[dict],
        min_confidence: float = 0.7,
    ) -> list[BibliographicMetadata]:
        """Citation 목록에서 PubMed 논문 검색.

        Args:
            citations: citation 정보 목록
            min_confidence: 최소 매칭 신뢰도

        Returns:
            매칭된 BibliographicMetadata 목록
        """
        found_papers = []
        for citation in citations:
            try:
                paper = await self.pubmed_enricher.search_and_enrich_citation(
                    authors=citation.get("authors", []),
                    year=citation.get("year"),
                    title=citation.get("title"),
                    journal=citation.get("journal"),
                    min_confidence=min_confidence,
                )
                if paper:
                    found_papers.append(paper)
            except Exception as e:
                logger.warning(f"Failed to find citation: {e}")
        return found_papers

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    async def check_existing_paper(self, pmid: str) -> Optional[str]:
        """기존 논문 확인 (PMID로).

        Args:
            pmid: PubMed ID

        Returns:
            기존 paper_id 또는 None
        """
        cypher = """
        MATCH (p:Paper)
        WHERE p.pmid = $pmid OR p.paper_id = $paper_id
        RETURN p.paper_id AS paper_id
        LIMIT 1
        """
        paper_id = f"{PUBMED_PAPER_PREFIX}{pmid}"

        try:
            result = await self.neo4j.run_query(cypher, {
                "pmid": pmid,
                "paper_id": paper_id,
            })
            if result:
                return result[0].get("paper_id")
        except Exception as e:
            logger.warning(f"Error checking existing paper: {e}")

        return None

    async def check_existing_papers_batch(self, pmids: list[str]) -> dict[str, str]:
        """여러 PMID의 중복 여부를 한 번에 확인.

        Args:
            pmids: 확인할 PMID 목록

        Returns:
            dict[pmid, paper_id]: 이미 존재하는 논문의 PMID -> paper_id 매핑
        """
        if not pmids:
            return {}

        cypher = """
        MATCH (p:Paper)
        WHERE p.pmid IN $pmids OR p.paper_id IN $paper_ids
        RETURN p.pmid AS pmid, p.paper_id AS paper_id
        """
        paper_ids = [f"{PUBMED_PAPER_PREFIX}{pmid}" for pmid in pmids]

        try:
            result = await self.neo4j.run_query(cypher, {
                "pmids": pmids,
                "paper_ids": paper_ids,
            })
            return {row["pmid"]: row["paper_id"] for row in result if row.get("pmid")}
        except Exception as e:
            logger.warning(f"Error checking existing papers batch: {e}")
            return {}

    async def check_existing_by_doi(self, doi: str) -> Optional[str]:
        """DOI로 기존 논문 확인.

        Args:
            doi: Digital Object Identifier

        Returns:
            기존 paper_id 또는 None
        """
        if not doi:
            return None

        cypher = """
        MATCH (p:Paper {doi: $doi})
        RETURN p.paper_id AS paper_id
        LIMIT 1
        """
        try:
            result = await self.neo4j.run_query(cypher, {"doi": doi})
            if result:
                return result[0].get("paper_id")
        except Exception as e:
            logger.warning(f"Error checking paper by DOI: {e}")

        return None


# =============================================================================
# Standalone Utility Functions
# =============================================================================

def build_search_query(
    base_query: str,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    publication_types: Optional[list[str]] = None,
) -> str:
    """검색 쿼리 구성."""
    parts = [base_query]

    if year_from and year_to:
        parts.append(f"({year_from}:{year_to}[PDAT])")
    elif year_from:
        parts.append(f"({year_from}:3000[PDAT])")
    elif year_to:
        parts.append(f"(1900:{year_to}[PDAT])")

    if publication_types:
        type_queries = [f'"{pt}"[PT]' for pt in publication_types]
        parts.append(f"({' OR '.join(type_queries)})")

    return " AND ".join(parts)
