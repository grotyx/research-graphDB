"""PubMed Bulk Processing Module (v5.3.1).

대량의 PubMed 논문을 검색하고 Neo4j에 임포트하는 기능을 제공합니다.
v5.3부터 ChromaDB가 제거되고 Neo4j Vector Index만 사용합니다.
v5.3.1부터 OpenAI text-embedding-3-large (3072d)를 기본 임베딩으로 사용합니다.

Two main scenarios:
- Scenario A: Import papers from important citations in existing papers
- Scenario B: Bulk search and import from PubMed queries

Usage:
    processor = PubMedBulkProcessor(neo4j_client)

    # Scenario B: Search and import
    results = await processor.search_pubmed("lumbar fusion outcomes", max_results=50)
    import_results = await processor.import_papers(results)

    # Scenario A: Import from citations
    import_results = await processor.import_from_citations(paper_id="paper_123")

    # Upgrade with PDF
    upgrade_result = await processor.upgrade_with_pdf(paper_id="pubmed_12345678", pdf_path="paper.pdf")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

try:
    from builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
    from builder.pmc_fulltext_fetcher import PMCFullTextFetcher, PMCFullText
    from builder.unified_pdf_processor import UnifiedPDFProcessor, ProcessorResult, ExtractedMetadata
    from builder.doi_fulltext_fetcher import DOIFulltextFetcher, DOIFullText
    from external.pubmed_client import PubMedClient, PaperMetadata, PubMedError
    from graph.spine_schema import PaperNode
    from graph.relationship_builder import RelationshipBuilder, SpineMetadata
    from graph.entity_normalizer import EntityNormalizer
    from core.embedding import EmbeddingGenerator
    from storage import TextChunk
    DOI_FETCHER_AVAILABLE = True
except ImportError:
    try:
        from src.builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
        from src.builder.pmc_fulltext_fetcher import PMCFullTextFetcher, PMCFullText
        from src.builder.unified_pdf_processor import UnifiedPDFProcessor, ProcessorResult, ExtractedMetadata
        from src.builder.doi_fulltext_fetcher import DOIFulltextFetcher, DOIFullText
        from src.external.pubmed_client import PubMedClient, PaperMetadata, PubMedError
        from src.graph.spine_schema import PaperNode
        from src.graph.relationship_builder import RelationshipBuilder, SpineMetadata
        from src.graph.entity_normalizer import EntityNormalizer
        from src.core.embedding import EmbeddingGenerator
        from src.storage import TextChunk
        DOI_FETCHER_AVAILABLE = True
    except ImportError:
        DOI_FETCHER_AVAILABLE = False
        DOIFulltextFetcher = None
        DOIFullText = None
        UnifiedPDFProcessor = None
        EntityNormalizer = None

if TYPE_CHECKING:
    from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PubMedImportResult:
    """PubMed 논문 임포트 결과.

    Attributes:
        paper_id: 생성된 paper ID (pubmed_{pmid} 형식)
        pmid: PubMed ID
        title: 논문 제목
        neo4j_created: Neo4j Paper 노드 생성 여부
        chunks_created: 생성된 청크 수
        source: 임포트 소스 ("citation" | "search")
        is_abstract_only: 초록만 있는 논문 여부
        has_fulltext: PMC에서 전문을 가져왔는지 여부
        pmcid: PubMed Central ID (있는 경우)
        skipped: 스킵된 경우 True
        skip_reason: 스킵 사유
        error: 에러 메시지 (있는 경우)
    """
    paper_id: str
    pmid: str
    title: str
    neo4j_created: bool = False
    chunks_created: int = 0
    source: str = "search"  # "citation" | "search"
    is_abstract_only: bool = True
    has_fulltext: bool = False
    pmcid: str = ""
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "paper_id": self.paper_id,
            "pmid": self.pmid,
            "title": self.title,
            "neo4j_created": self.neo4j_created,
            "chunks_created": self.chunks_created,
            "source": self.source,
            "is_abstract_only": self.is_abstract_only,
            "has_fulltext": self.has_fulltext,
            "pmcid": self.pmcid,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass
class BulkImportSummary:
    """대량 임포트 요약.

    Attributes:
        total_papers: 총 처리 논문 수
        imported: 성공적으로 임포트된 수
        skipped: 스킵된 수
        failed: 실패한 수
        total_chunks: 총 생성된 청크 수
        fulltext_count: PMC에서 전문을 가져온 논문 수
        results: 개별 임포트 결과 목록
    """
    total_papers: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    total_chunks: int = 0
    fulltext_count: int = 0
    results: list[PubMedImportResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "total_papers": self.total_papers,
            "imported": self.imported,
            "skipped": self.skipped,
            "failed": self.failed,
            "total_chunks": self.total_chunks,
            "fulltext_count": self.fulltext_count,
            "results": [r.to_dict() for r in self.results],
        }


@dataclass
class AbstractChunk:
    """초록에서 생성된 청크.

    Attributes:
        chunk_id: 청크 ID
        content: 청크 내용
        section: 섹션 (background, methods, results, conclusions, full)
        metadata: 메타데이터
    """
    chunk_id: str
    content: str
    section: str = "abstract"
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Main Processor Class
# =============================================================================

class PubMedBulkProcessor:
    """PubMed 대량 처리기.

    Neo4j에 PubMed 논문을 대량으로 임포트합니다.
    v5.3부터 ChromaDB가 제거되고 Neo4j Vector Index만 사용합니다.

    Example:
        processor = PubMedBulkProcessor(neo4j_client)

        # Search and preview
        papers = await processor.search_pubmed("spine fusion", max_results=20)
        print(f"Found {len(papers)} papers")

        # Import selected papers
        results = await processor.import_papers(papers[:10])
        print(f"Imported {results.imported} papers")
    """

    # Paper ID prefix for PubMed-only papers
    PUBMED_PAPER_PREFIX = "pubmed_"

    # v5.3.1: Use OpenAI text-embedding-3-large (3072 dimensions)
    EMBEDDING_MODEL = "text-embedding-3-large"
    EMBEDDING_DIM = 3072

    def __init__(
        self,
        neo4j_client: "Neo4jClient",
        vector_db: "VectorDB" = None,  # v5.3: Optional (deprecated, use Neo4j)
        pubmed_email: Optional[str] = None,
        pubmed_api_key: Optional[str] = None,
        embedding_generator=None,  # OpenAIEmbeddingGenerator or EmbeddingGenerator
        enable_fulltext: bool = True,
        vision_processor: Optional[UnifiedPDFProcessor] = None,
        entity_normalizer: Optional[EntityNormalizer] = None,
    ):
        """PubMedBulkProcessor 초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            vector_db: (Deprecated) ChromaDB 벡터 저장소 - v5.3에서 Neo4j Vector Index 사용
            pubmed_email: NCBI 이메일 (권장)
            pubmed_api_key: NCBI API 키 (rate limit 향상)
            embedding_generator: 임베딩 생성기 (None이면 OpenAI 자동 생성)
            enable_fulltext: PMC Open Access 전문 가져오기 활성화 (기본 True)
            vision_processor: LLM 처리기 (None이면 자동 생성)
            entity_normalizer: 엔티티 정규화기 (None이면 자동 생성)
        """
        self.neo4j = neo4j_client
        self.vector_db = vector_db  # v5.3: May be None (deprecated)
        self.pubmed_client = PubMedClient(email=pubmed_email, api_key=pubmed_api_key)
        self.pubmed_enricher = PubMedEnricher(email=pubmed_email, api_key=pubmed_api_key)

        # PMC Full Text Fetcher for Open Access papers
        self.enable_fulltext = enable_fulltext
        self.pmc_fetcher = PMCFullTextFetcher() if enable_fulltext else None

        # DOI Fulltext Fetcher (Crossref + Unpaywall) for non-PMC papers
        self.doi_fetcher = DOIFulltextFetcher() if DOI_FETCHER_AVAILABLE and enable_fulltext else None

        # v5.3.1: Use OpenAI embeddings (3072 dimensions)
        if embedding_generator is not None:
            self.embedding_generator = embedding_generator
        else:
            try:
                from core.embedding import OpenAIEmbeddingGenerator
                self.embedding_generator = OpenAIEmbeddingGenerator()
                logger.info(f"OpenAI Embedding initialized: {self.EMBEDDING_MODEL} ({self.EMBEDDING_DIM}d)")
            except Exception as e:
                # v1.14.26: MedTE 폴백 제거 (768d는 3072d 인덱스와 호환 불가)
                logger.error(f"OpenAI embedding initialization failed: {e}")
                logger.error("OPENAI_API_KEY must be set - MedTE fallback removed (dimension mismatch)")
                raise RuntimeError(f"OpenAI embedding required (3072d index): {e}")

        # LLM processor for text analysis (PMC full text + Abstract)
        # Always initialize for Abstract LLM processing even if enable_fulltext=False
        self.vision_processor = vision_processor
        if vision_processor is None:
            try:
                self.vision_processor = UnifiedPDFProcessor()
                logger.info("UnifiedPDFProcessor initialized for text/abstract LLM processing")
            except Exception as e:
                logger.warning(f"Failed to initialize UnifiedPDFProcessor: {e}")
                self.vision_processor = None

        # Entity normalizer for relationship building
        self.entity_normalizer = entity_normalizer or EntityNormalizer()

        # Relationship builder for Neo4j graph
        self.relationship_builder = RelationshipBuilder(neo4j_client, self.entity_normalizer)

        logger.info(f"PubMedBulkProcessor initialized (fulltext={enable_fulltext}, llm_processing={self.vision_processor is not None})")

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

        Example:
            # Basic search
            papers = await processor.search_pubmed("lumbar fusion")

            # With filters
            papers = await processor.search_pubmed(
                "spine surgery outcomes",
                max_results=100,
                year_from=2020,
                year_to=2024,
                publication_types=["Randomized Controlled Trial"]
            )
        """
        # Build query with filters
        full_query = self._build_search_query(
            query,
            year_from=year_from,
            year_to=year_to,
            publication_types=publication_types,
        )

        logger.info(f"Searching PubMed: {full_query[:100]}...")

        try:
            # Search for PMIDs
            pmids = await asyncio.to_thread(
                self.pubmed_client.search,
                full_query,
                max_results=min(max_results, 500),
            )

            if not pmids:
                logger.info("No PubMed results found")
                return []

            logger.info(f"Found {len(pmids)} PMIDs, fetching details...")

            # Fetch paper details in batches
            papers = await self._fetch_papers_batch(pmids)

            logger.info(f"Retrieved {len(papers)} paper details")
            return papers

        except PubMedError as e:
            logger.error(f"PubMed search error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in PubMed search: {e}")
            raise

    def _build_search_query(
        self,
        base_query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> str:
        """검색 쿼리 구성."""
        parts = [base_query]

        # Year filter
        if year_from and year_to:
            parts.append(f"({year_from}:{year_to}[PDAT])")
        elif year_from:
            parts.append(f"({year_from}:3000[PDAT])")
        elif year_to:
            parts.append(f"(1900:{year_to}[PDAT])")

        # Publication type filter
        if publication_types:
            type_queries = [f'"{pt}"[PT]' for pt in publication_types]
            parts.append(f"({' OR '.join(type_queries)})")

        return " AND ".join(parts)

    async def _fetch_papers_batch(
        self,
        pmids: list[str],
        batch_size: int = 5,  # Reduced for PubMed rate limiting (10 req/sec with API key)
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

            # Fetch batch with small delay between requests
            batch_results = []
            for pmid in batch:
                try:
                    result = await self._fetch_single_paper(pmid)
                    batch_results.append(result)
                except Exception as e:
                    logger.warning(f"Failed to fetch paper {pmid}: {e}")
                # Small delay between individual requests (0.15s = ~6-7 req/sec)
                await asyncio.sleep(0.15)

            results.extend(batch_results)

            # Rate limiting between batches (1 second)
            if i + batch_size < len(pmids):
                await asyncio.sleep(1.0)

        return results

    async def _fetch_single_paper(self, pmid: str) -> BibliographicMetadata:
        """단일 논문 상세 정보 가져오기."""
        paper = await asyncio.to_thread(
            self.pubmed_client.fetch_paper_details, pmid
        )
        return BibliographicMetadata.from_pubmed(paper, confidence=1.0)

    # =========================================================================
    # Import Methods
    # =========================================================================

    async def import_papers(
        self,
        papers: list[BibliographicMetadata],
        skip_existing: bool = True,
        source: str = "search",
        fetch_fulltext: bool = True,
        max_concurrent: int = 1,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> BulkImportSummary:
        """PubMed 논문들을 Neo4j에 임포트. (v5.3: Neo4j Vector Index 사용)

        v1.14.24: LLM 처리 전에 배치 중복 체크를 수행하여 효율성 향상

        Args:
            papers: 임포트할 논문 목록
            skip_existing: 기존 논문 스킵 여부 (기본 True)
            source: 임포트 소스 ("search" | "citation")
            fetch_fulltext: PMC에서 Open Access 전문 가져오기 (기본 True)
            max_concurrent: 최대 동시 처리 수 (기본 1=순차, 3-5 권장)
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)

        Returns:
            BulkImportSummary with import results

        Example:
            papers = await processor.search_pubmed("spine fusion")
            # 순차 처리 (기본)
            results = await processor.import_papers(papers, skip_existing=True)
            # 병렬 처리 (3개 동시)
            results = await processor.import_papers(papers, max_concurrent=3)
            # 특정 사용자 소유로 임포트
            results = await processor.import_papers(papers, owner="kim", shared=False)
            print(f"Imported {results.imported} / {results.total_papers} papers")
        """
        import asyncio

        summary = BulkImportSummary(total_papers=len(papers))

        # v1.14.24: LLM 처리 전에 배치 중복 체크 (DB 쿼리 1회로 모든 중복 확인)
        papers_to_import = papers
        if skip_existing:
            pmids = [p.pmid for p in papers if p.pmid]
            existing_pmids = await self._check_existing_papers_batch(pmids)

            if existing_pmids:
                # 중복 논문 분리
                papers_to_import = []
                for paper in papers:
                    if paper.pmid and paper.pmid in existing_pmids:
                        # 이미 존재하는 논문 - LLM 처리 없이 바로 스킵
                        summary.results.append(PubMedImportResult(
                            paper_id=existing_pmids[paper.pmid],
                            pmid=paper.pmid or "",
                            title=paper.title,
                            skipped=True,
                            skip_reason="Already exists (batch check)",
                            source=source,
                        ))
                        summary.skipped += 1
                    else:
                        papers_to_import.append(paper)

                logger.info(
                    f"Batch duplicate check: {summary.skipped} skipped, "
                    f"{len(papers_to_import)} papers to import"
                )

        # 임포트할 논문이 없으면 바로 반환
        if not papers_to_import:
            logger.info("All papers already exist, nothing to import")
            return summary

        # v1.14.24: 배치 중복 체크 후에는 skip_existing=False (이미 걸러냄)
        effective_skip_existing = False if skip_existing else skip_existing

        if max_concurrent <= 1:
            # 순차 처리 (기존 방식)
            for paper in papers_to_import:
                result = await self._import_with_error_handling(
                    paper, effective_skip_existing, source, fetch_fulltext, owner, shared
                )
                self._update_summary(summary, result)
        else:
            # 병렬 처리 (Semaphore로 동시 처리 수 제한)
            semaphore = asyncio.Semaphore(max_concurrent)

            async def import_with_semaphore(paper: BibliographicMetadata) -> PubMedImportResult:
                async with semaphore:
                    return await self._import_with_error_handling(
                        paper, effective_skip_existing, source, fetch_fulltext, owner, shared
                    )

            logger.info(f"Starting parallel import: {len(papers_to_import)} papers, max_concurrent={max_concurrent}")

            # 모든 논문 병렬 처리
            results = await asyncio.gather(
                *[import_with_semaphore(paper) for paper in papers_to_import],
                return_exceptions=False  # 예외는 _import_with_error_handling에서 처리
            )

            for result in results:
                self._update_summary(summary, result)

        logger.info(
            f"Import complete: {summary.imported} imported, "
            f"{summary.skipped} skipped, {summary.failed} failed, "
            f"{summary.fulltext_count} with full text"
        )
        return summary

    async def _import_with_error_handling(
        self,
        paper: BibliographicMetadata,
        skip_existing: bool,
        source: str,
        fetch_fulltext: bool,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> PubMedImportResult:
        """에러 핸들링이 포함된 단일 논문 임포트."""
        try:
            return await self._import_single_paper(
                paper,
                skip_existing=skip_existing,
                source=source,
                fetch_fulltext=fetch_fulltext,
                owner=owner,
                shared=shared,
            )
        except Exception as e:
            logger.error(f"Error importing paper {paper.pmid}: {e}")
            return PubMedImportResult(
                paper_id="",
                pmid=paper.pmid or "",
                title=paper.title,
                error=str(e),
            )

    def _update_summary(self, summary: BulkImportSummary, result: PubMedImportResult):
        """Summary 업데이트 헬퍼."""
        summary.results.append(result)
        if result.skipped:
            summary.skipped += 1
        elif result.error:
            summary.failed += 1
        else:
            summary.imported += 1
            summary.total_chunks += result.chunks_created
            if result.has_fulltext:
                summary.fulltext_count += 1

    async def _import_single_paper(
        self,
        paper: BibliographicMetadata,
        skip_existing: bool,
        source: str,
        fetch_fulltext: bool = True,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> PubMedImportResult:
        """단일 논문 임포트."""
        pmid = paper.pmid or ""
        paper_id = f"{self.PUBMED_PAPER_PREFIX}{pmid}"

        # Check for existing paper
        if skip_existing and pmid:
            existing = await self._check_existing_paper(pmid)
            if existing:
                logger.debug(f"Skipping existing paper: {pmid}")
                return PubMedImportResult(
                    paper_id=existing,
                    pmid=pmid,
                    title=paper.title,
                    skipped=True,
                    skip_reason="Already exists",
                    source=source,
                )

        # Create Neo4j Paper node (basic, will be updated if LLM processing succeeds)
        neo4j_created = await self.create_paper_node(paper)

        # Try to fetch full text from PMC (Open Access)
        chunks_created = 0
        has_fulltext = False
        pmcid = ""
        fulltext_source = ""
        llm_processed = False
        extracted_data: Optional[dict] = None

        # === Step 1: Try PMC (Open Access) ===
        if fetch_fulltext and self.pmc_fetcher and pmid:
            try:
                pmc_result = await self.pmc_fetcher.fetch_fulltext(pmid)
                if pmc_result.has_full_text:
                    has_fulltext = True
                    pmcid = pmc_result.pmcid or ""
                    fulltext_source = "pmc"
                    logger.info(f"[PMC] Full text fetched for PMID {pmid} (PMCID: {pmcid})")

                    # Try LLM-based processing (same as PDF processing)
                    if self.vision_processor:
                        try:
                            chunks_created, llm_processed, extracted_data = await self._process_fulltext_with_llm(
                                paper_id=paper_id,
                                paper=paper,
                                fulltext=pmc_result,
                                owner=owner,
                                shared=shared,
                            )
                        except Exception as e:
                            logger.warning(f"LLM processing failed for {pmid}, falling back to simple chunking: {e}")

                    # Fallback to simple chunking if LLM processing failed
                    if not llm_processed:
                        chunks_created = await self.chunk_fulltext(
                            paper_id=paper_id,
                            fulltext=pmc_result,
                            metadata=self._build_chunk_metadata(paper),
                        )
            except Exception as e:
                logger.warning(f"Failed to fetch PMC full text for {pmid}: {e}")

        # === Step 2: Try DOI/Unpaywall if PMC failed ===
        if not has_fulltext and fetch_fulltext and self.doi_fetcher and paper.doi:
            try:
                doi_result = await self.doi_fetcher.fetch(
                    paper.doi,
                    download_pdf=False,  # PDF 다운로드 없이 텍스트만
                    fetch_pmc=False,     # PMC는 이미 시도함
                )
                if doi_result.has_full_text and doi_result.full_text:
                    has_fulltext = True
                    fulltext_source = f"unpaywall ({doi_result.metadata.oa_status if doi_result.metadata else 'unknown'})"
                    logger.info(f"[Unpaywall] Full text fetched for DOI {paper.doi} ({fulltext_source})")

                    # Process with LLM
                    if self.vision_processor:
                        try:
                            chunks_created, llm_processed, extracted_data = await self._process_text_with_llm(
                                paper_id=paper_id,
                                paper=paper,
                                text=doi_result.full_text,
                                owner=owner,
                                shared=shared,
                            )
                        except Exception as e:
                            logger.warning(f"LLM processing failed for DOI {paper.doi}: {e}")

                    # Fallback to simple chunking
                    if not llm_processed:
                        chunks_created = await self.chunk_text(
                            paper_id=paper_id,
                            text=doi_result.full_text,
                            metadata=self._build_chunk_metadata(paper),
                        )
                elif doi_result.metadata and doi_result.metadata.pdf_url:
                    # PDF URL이 있지만 텍스트 추출이 안 된 경우 로그만 남김
                    logger.info(f"[Unpaywall] PDF URL available but not fetched: {doi_result.metadata.pdf_url[:50]}...")
            except Exception as e:
                logger.warning(f"Failed to fetch via DOI/Unpaywall for {paper.doi}: {e}")

        # === Step 3: Fallback to abstract if no full text ===
        if not has_fulltext and paper.abstract:
            # Try LLM-based abstract processing (extracts relationships like PDF)
            if self.vision_processor:
                try:
                    chunks_created, llm_processed, extracted_data = await self._process_abstract_with_llm(
                        paper_id=paper_id,
                        paper=paper,
                        owner=owner,
                        shared=shared,
                    )
                except Exception as e:
                    logger.warning(f"LLM abstract processing failed for {pmid}, falling back to simple chunking: {e}")
                    llm_processed = False

            # Fallback to simple chunking if LLM processing failed or not available
            if not self.vision_processor or not llm_processed:
                chunks_created = await self.chunk_abstract(
                    paper_id=paper_id,
                    abstract=paper.abstract,
                    metadata=self._build_chunk_metadata(paper),
                )

        # JSON 저장 (LLM 처리 성공 시)
        if llm_processed and extracted_data:
            await self._save_extracted_json(paper, extracted_data)

        return PubMedImportResult(
            paper_id=paper_id,
            pmid=pmid,
            title=paper.title,
            neo4j_created=neo4j_created,
            chunks_created=chunks_created,
            source=source,
            is_abstract_only=not has_fulltext,
            has_fulltext=has_fulltext,
            pmcid=pmcid,
        )

    async def _process_fulltext_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        fulltext: PMCFullText,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> tuple[int, bool, Optional[dict]]:
        """PMC 전문을 LLM으로 처리하고 Neo4j 관계를 구축.

        PDF 처리와 동일한 방식으로 PICO, Outcomes, Interventions 등을 추출합니다.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            fulltext: PMC 전문 데이터
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)

        Returns:
            (chunks_created, success, extracted_data) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        # PMC 전문을 텍스트로 변환
        full_text = fulltext.full_text
        if not full_text or len(full_text) < 500:
            logger.warning(f"Full text too short for LLM processing: {len(full_text)} chars")
            return 0, False, None

        logger.info(f"Processing PMC full text with LLM ({len(full_text)} chars)")

        # LLM 처리
        result: ProcessorResult = await self.vision_processor.process_text(
            text=full_text,
            title=paper.title,
            source="pmc",
        )

        if not result.success:
            logger.warning(f"LLM text processing failed: {result.error}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from LLM processing")
            return 0, False, None

        logger.info(f"LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        # 추출된 데이터에서 메타데이터와 청크 파싱 (v1.14.27: None 값 처리)
        metadata_dict = extracted_data.get("metadata") or {}
        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        # Neo4j 관계 구축 (PDF 처리와 동일)
        try:
            # SpineMetadata 생성 (relationship_builder.py에 정의됨)
            # anatomy_level을 list로 변환
            anatomy_level = spine_meta.get("anatomy_level", "")
            anatomy_levels = [anatomy_level] if anatomy_level else []

            # pathology를 pathologies로 변환 (list 형식)
            pathology = spine_meta.get("pathology", [])
            pathologies = pathology if isinstance(pathology, list) else [pathology] if pathology else []

            # outcomes 추출
            all_outcomes = spine_meta.get("outcomes", [])

            # v5.3.3: sub_domains (list) 지원 추가
            # LLM은 sub_domains (list)를 반환하지만, 하위호환성을 위해 sub_domain (string)도 지원
            sub_domains = spine_meta.get("sub_domains", []) or []
            sub_domain = spine_meta.get("sub_domain", "") or ""
            if not sub_domains and sub_domain:
                sub_domains = [sub_domain]
            if sub_domains and not sub_domain:
                sub_domain = sub_domains[0]

            # surgical_approach (list) 추출
            surgical_approach = spine_meta.get("surgical_approach", []) or []

            # PICO 파싱: LLM은 중첩 형식 {"pico": {"population": ...}} 또는 플랫 형식 {"pico_population": ...}을 반환할 수 있음
            pico = spine_meta.get("pico", {}) or {}
            pico_population = pico.get("population", "") or spine_meta.get("pico_population", "")
            pico_intervention = pico.get("intervention", "") or spine_meta.get("pico_intervention", "")
            pico_comparison = pico.get("comparison", "") or spine_meta.get("pico_comparison", "")
            pico_outcome = pico.get("outcome", "") or spine_meta.get("pico_outcome", "")

            graph_spine_meta = SpineMetadata(
                sub_domains=sub_domains,
                sub_domain=sub_domain,
                surgical_approach=surgical_approach,
                anatomy_levels=anatomy_levels,
                pathologies=pathologies,
                interventions=spine_meta.get("interventions", []),
                outcomes=all_outcomes,
                main_conclusion=spine_meta.get("main_conclusion", ""),
                pico_population=pico_population,
                pico_intervention=pico_intervention,
                pico_comparison=pico_comparison,
                pico_outcome=pico_outcome,
            )

            # ExtractedMetadata 객체 생성 (build_from_paper가 객체를 기대함)
            # Note: BibliographicMetadata doesn't have evidence_level, infer from publication_types
            inferred_evidence = self._infer_evidence_level(paper.publication_types)
            extracted_metadata = ExtractedMetadata(
                title=metadata_dict.get("title", paper.title) or paper.title,
                authors=metadata_dict.get("authors", list(paper.authors)) or list(paper.authors),
                year=metadata_dict.get("year", paper.year) or paper.year,
                journal=metadata_dict.get("journal", paper.journal) or paper.journal,
                doi=metadata_dict.get("doi", paper.doi) or paper.doi,
                pmid=paper.pmid or "",
                abstract=paper.abstract or "",
                study_type=metadata_dict.get("study_type", ""),
                study_design=metadata_dict.get("study_design", ""),
                evidence_level=metadata_dict.get("evidence_level") or inferred_evidence or "5",
                sample_size=metadata_dict.get("sample_size", 0) or 0,
                centers=metadata_dict.get("centers", ""),
                blinding=metadata_dict.get("blinding", ""),
            )

            # RelationshipBuilder로 Neo4j 관계 구축 (v1.5: 멀티유저 지원)
            build_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=extracted_metadata,
                spine_metadata=graph_spine_meta,
                chunks=chunks_data,
                owner=owner,
                shared=shared,
            )

            logger.info(
                f"Neo4j relationships built: {build_result.nodes_created} nodes, "
                f"{build_result.relationships_created} relations"
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships: {e}")

        # Neo4j에 청크 저장 (v5.3: Neo4j Vector Index 사용)
        chunks_created = await self._store_llm_chunks(
            paper_id=paper_id,
            paper=paper,
            chunks_data=chunks_data,
            pmcid=fulltext.pmcid or "",
        )

        return chunks_created, True, extracted_data

    async def _process_abstract_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> tuple[int, bool, Optional[dict]]:
        """Abstract를 LLM으로 분석하고 Neo4j 관계를 구축.

        Full text가 없는 경우에도 abstract에서 가능한 정보를 추출합니다:
        - Sub-domain, anatomy level
        - Interventions, pathologies
        - Outcomes (상세 통계 제외)
        - PICO 요소

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)

        Returns:
            (chunks_created, success) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        abstract = paper.abstract
        if not abstract or len(abstract) < 100:
            logger.debug(f"Abstract too short for LLM processing: {len(abstract) if abstract else 0} chars")
            return 0, False, None

        logger.info(f"Processing abstract with LLM ({len(abstract)} chars)")

        # LLM 처리 (process_text 사용)
        result: ProcessorResult = await self.vision_processor.process_text(
            text=abstract,
            title=paper.title,
            source="pubmed_abstract",
        )

        if not result.success:
            logger.warning(f"LLM abstract processing failed: {result.error}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from abstract LLM processing")
            return 0, False, None

        logger.info(f"Abstract LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        # 추출된 데이터에서 메타데이터와 청크 파싱 (v1.14.27: None 값 처리)
        metadata_dict = extracted_data.get("metadata") or {}
        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        # Neo4j 관계 구축 (PDF/Full text 처리와 동일)
        try:
            # anatomy_level을 list로 변환
            anatomy_level = spine_meta.get("anatomy_level", "")
            anatomy_levels = [anatomy_level] if anatomy_level else []

            # pathology를 pathologies로 변환
            pathology = spine_meta.get("pathology", [])
            pathologies = pathology if isinstance(pathology, list) else [pathology] if pathology else []

            # outcomes 추출
            all_outcomes = spine_meta.get("outcomes", [])

            # v5.3.3: sub_domains (list) 지원 추가
            # LLM은 sub_domains (list)를 반환하지만, 하위호환성을 위해 sub_domain (string)도 지원
            sub_domains = spine_meta.get("sub_domains", []) or []
            sub_domain = spine_meta.get("sub_domain", "") or ""
            if not sub_domains and sub_domain:
                sub_domains = [sub_domain]
            if sub_domains and not sub_domain:
                sub_domain = sub_domains[0]

            # surgical_approach (list) 추출
            surgical_approach = spine_meta.get("surgical_approach", []) or []

            # PICO 파싱: LLM은 중첩 형식 {"pico": {"population": ...}} 또는 플랫 형식 {"pico_population": ...}을 반환할 수 있음
            pico = spine_meta.get("pico", {}) or {}
            pico_population = pico.get("population", "") or spine_meta.get("pico_population", "")
            pico_intervention = pico.get("intervention", "") or spine_meta.get("pico_intervention", "")
            pico_comparison = pico.get("comparison", "") or spine_meta.get("pico_comparison", "")
            pico_outcome = pico.get("outcome", "") or spine_meta.get("pico_outcome", "")

            graph_spine_meta = SpineMetadata(
                sub_domains=sub_domains,
                sub_domain=sub_domain,
                surgical_approach=surgical_approach,
                anatomy_levels=anatomy_levels,
                pathologies=pathologies,
                interventions=spine_meta.get("interventions", []),
                outcomes=all_outcomes,
                main_conclusion=spine_meta.get("main_conclusion", ""),
                pico_population=pico_population,
                pico_intervention=pico_intervention,
                pico_comparison=pico_comparison,
                pico_outcome=pico_outcome,
            )

            # ExtractedMetadata 객체 생성
            # Note: BibliographicMetadata doesn't have evidence_level, infer from publication_types
            inferred_evidence = self._infer_evidence_level(paper.publication_types)
            extracted_metadata = ExtractedMetadata(
                title=metadata_dict.get("title", paper.title) or paper.title,
                authors=metadata_dict.get("authors", list(paper.authors)) or list(paper.authors),
                year=metadata_dict.get("year", paper.year) or paper.year,
                journal=metadata_dict.get("journal", paper.journal) or paper.journal,
                doi=metadata_dict.get("doi", paper.doi) or paper.doi,
                pmid=paper.pmid or "",
                abstract=abstract,
                study_type=metadata_dict.get("study_type", ""),
                study_design=metadata_dict.get("study_design", ""),
                evidence_level=metadata_dict.get("evidence_level") or inferred_evidence or "5",
                sample_size=metadata_dict.get("sample_size", 0) or 0,
                centers=metadata_dict.get("centers", ""),
                blinding=metadata_dict.get("blinding", ""),
            )

            # RelationshipBuilder로 Neo4j 관계 구축 (v1.5: 멀티유저 지원)
            build_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=extracted_metadata,
                spine_metadata=graph_spine_meta,
                chunks=chunks_data,
                owner=owner,
                shared=shared,
            )

            logger.info(
                f"Neo4j relationships built from abstract: {build_result.nodes_created} nodes, "
                f"{build_result.relationships_created} relations"
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships from abstract: {e}")

        # 청크 저장 (abstract에서 추출된 청크 또는 abstract 자체)
        if chunks_data:
            chunks_created = await self._store_llm_chunks(
                paper_id=paper_id,
                paper=paper,
                chunks_data=chunks_data,
                pmcid="",  # Abstract-only는 PMCID 없음
            )
        else:
            # LLM이 청크를 생성하지 않은 경우, abstract 자체를 청크로 저장
            chunks_created = await self.chunk_abstract(
                paper_id=paper_id,
                abstract=abstract,
                metadata=self._build_chunk_metadata(paper),
            )

        return chunks_created, True, extracted_data

    async def _store_llm_chunks(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        chunks_data: list[dict],
        pmcid: str,
    ) -> int:
        """LLM에서 추출된 청크를 Neo4j에 저장. (v5.3: Neo4j Vector Index 사용)

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            chunks_data: LLM에서 추출된 청크 목록
            pmcid: PubMed Central ID

        Returns:
            저장된 청크 수
        """
        if not chunks_data:
            return 0

        text_chunks = []
        base_metadata = self._build_chunk_metadata(paper)

        for idx, chunk_dict in enumerate(chunks_data):
            content = chunk_dict.get("content", "")
            if not content or len(content) < 30:
                continue

            section_type = chunk_dict.get("section_type", "other")
            tier = chunk_dict.get("tier", "tier2")
            content_type = chunk_dict.get("content_type", "text")

            chunk_id = f"{paper_id}_{section_type}_{idx}"

            # 통계 정보 추출 (v1.14.27: None 값 처리)
            stats = chunk_dict.get("statistics") or {}

            text_chunks.append(TextChunk(
                chunk_id=chunk_id,
                content=content,
                document_id=paper_id,
                tier=tier,
                section=section_type,
                source_type="pmc_llm",
                evidence_level=base_metadata.get("evidence_level", "5"),
                publication_year=base_metadata.get("publication_year", 0),
                page_num=0,
                title=base_metadata.get("title", ""),
                authors=base_metadata.get("authors", []),
                metadata={
                    **base_metadata,
                    "source": "pmc_fulltext_llm",
                    "pmcid": pmcid,
                    "is_abstract_only": False,
                    "content_type": content_type,
                    "summary": chunk_dict.get("summary", ""),
                    "is_key_finding": chunk_dict.get("is_key_finding", False),
                    "p_value": stats.get("p_value", ""),
                    "is_significant": stats.get("is_significant", False),
                },
            ))

        if not text_chunks:
            return 0

        # Generate embeddings
        contents = [c.content for c in text_chunks]
        embeddings = self.embedding_generator.embed_batch(contents)

        # v5.3: Store chunks in Neo4j (ChromaDB deprecated)
        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)

        tier1_count = sum(1 for c in text_chunks if c.tier == "tier1")
        tier2_count = sum(1 for c in text_chunks if c.tier == "tier2")
        logger.info(f"Stored {total_added} chunks from LLM processing (tier1: {tier1_count}, tier2: {tier2_count})")
        return total_added

    async def _process_text_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        text: str,
        owner: str = "system",
        shared: bool = True,
    ) -> tuple[int, bool, Optional[dict]]:
        """일반 텍스트(DOI/Unpaywall 등)를 LLM으로 처리.

        _process_abstract_with_llm과 동일한 방식이지만, 더 긴 텍스트도 처리 가능.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            text: 처리할 전문 텍스트
            owner: 소유자 ID
            shared: 공유 여부

        Returns:
            (chunks_created, success, extracted_data) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        if not text or len(text) < 100:
            logger.debug(f"Text too short for LLM processing: {len(text) if text else 0} chars")
            return 0, False, None

        logger.info(f"[DOI/Unpaywall] Processing text with LLM ({len(text)} chars)")

        # LLM 처리
        result: ProcessorResult = await self.vision_processor.process_text(
            text=text,
            title=paper.title,
            source="doi_fulltext",
        )

        if not result.success:
            logger.warning(f"LLM text processing failed: {result.error}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from text LLM processing")
            return 0, False, None

        logger.info(f"Text LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        # Neo4j 관계 구축 (_process_abstract_with_llm과 동일 로직)
        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        try:
            anatomy_level = spine_meta.get("anatomy_level", "")
            anatomy_levels = [anatomy_level] if anatomy_level else []

            pathology = spine_meta.get("pathology", [])
            pathologies = pathology if isinstance(pathology, list) else [pathology] if pathology else []

            sub_domains = spine_meta.get("sub_domains", []) or []
            sub_domain = spine_meta.get("sub_domain", "") or ""
            if not sub_domains and sub_domain:
                sub_domains = [sub_domain]
            if sub_domains and not sub_domain:
                sub_domain = sub_domains[0]

            surgical_approach = spine_meta.get("surgical_approach", []) or []

            pico = spine_meta.get("pico", {}) or {}
            pico_population = pico.get("population", "") or spine_meta.get("pico_population", "")
            pico_intervention = pico.get("intervention", "") or spine_meta.get("pico_intervention", "")
            pico_comparison = pico.get("comparison", "") or spine_meta.get("pico_comparison", "")
            pico_outcome = pico.get("outcome", "") or spine_meta.get("pico_outcome", "")

            graph_spine_meta = SpineMetadata(
                sub_domains=sub_domains,
                sub_domain=sub_domain,
                surgical_approach=surgical_approach,
                anatomy_levels=anatomy_levels,
                pathologies=pathologies,
                interventions=spine_meta.get("interventions", []),
                outcomes=spine_meta.get("outcomes", []),
                main_conclusion=spine_meta.get("main_conclusion", ""),
                pico_population=pico_population,
                pico_intervention=pico_intervention,
                pico_comparison=pico_comparison,
                pico_outcome=pico_outcome,
                summary=spine_meta.get("summary", "") or extracted_data.get("metadata", {}).get("abstract", ""),
                owner=owner,
                shared=shared,
            )

            await self.relationship_builder.build_relationships(
                paper_id=paper_id,
                metadata=graph_spine_meta,
                title=paper.title,
                abstract=paper.abstract or "",
                year=paper.year,
                journal=paper.journal,
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships: {e}")

        # 청크 저장
        chunks_created = await self._store_llm_chunks(
            paper_id=paper_id,
            paper=paper,
            chunks_data=chunks_data,
            pmcid="",  # DOI/Unpaywall은 PMCID 없음
        )

        return chunks_created, True, extracted_data

    async def chunk_text(
        self,
        paper_id: str,
        text: str,
        metadata: dict,
    ) -> int:
        """일반 텍스트를 청크로 분할하여 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            text: 전문 텍스트
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not text or not text.strip():
            return 0

        # 텍스트를 단락으로 분할
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        # 너무 짧은 단락은 합치기
        chunks_content = []
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) < 1500:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks_content.append(current_chunk)
                current_chunk = para

        if current_chunk:
            chunks_content.append(current_chunk)

        if not chunks_content:
            chunks_content = [text[:3000]]  # 분할 실패 시 처음 3000자

        # TextChunk 생성
        text_chunks = []
        for idx, content in enumerate(chunks_content):
            chunk_id = f"{paper_id}_text_{idx}"
            text_chunk = TextChunk(
                chunk_id=chunk_id,
                content=content,
                document_id=paper_id,
                tier="tier2",
                section="fulltext",
                source_type="doi_fulltext",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **metadata,
                    "source": "doi_fulltext",
                    "is_abstract_only": False,
                },
            )
            text_chunks.append(text_chunk)

        # 임베딩 생성 및 저장
        contents = [c.content for c in text_chunks]
        embeddings = self.embedding_generator.embed_batch(contents)

        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        logger.debug(f"Added {total_added} text chunks for paper {paper_id}")
        return total_added

    async def import_from_citations(
        self,
        paper_id: str,
        min_confidence: float = 0.7,
        owner: str = "system",   # v1.5: 소유자 ID
        shared: bool = True,     # v1.5: 공유 여부
    ) -> BulkImportSummary:
        """기존 논문의 important citations에서 PubMed 논문 임포트.

        Args:
            paper_id: 원본 논문 ID (citations 추출 대상)
            min_confidence: 최소 매칭 신뢰도 (기본 0.7)
            owner: 소유자 ID (v1.5 멀티유저 지원)
            shared: 공유 여부 (v1.5 멀티유저 지원)

        Returns:
            BulkImportSummary with import results

        Example:
            # Import cited papers from an existing paper
            results = await processor.import_from_citations(
                paper_id="paper_abc123",
                min_confidence=0.8
            )
        """
        logger.info(f"Importing citations from paper: {paper_id}")

        # Get paper's important citations from Neo4j
        citations = await self._get_important_citations(paper_id)

        if not citations:
            logger.info(f"No important citations found for paper: {paper_id}")
            return BulkImportSummary()

        logger.info(f"Found {len(citations)} citations to search")

        # Search PubMed for each citation
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

        logger.info(f"Found {len(found_papers)} papers from citations")

        # Import found papers (v1.5: 멀티유저 지원)
        if found_papers:
            return await self.import_papers(
                found_papers,
                skip_existing=True,
                source="citation",
                owner=owner,
                shared=shared,
            )

        return BulkImportSummary()

    async def _get_important_citations(self, paper_id: str) -> list[dict]:
        """Neo4j에서 논문의 important citations 가져오기."""
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        RETURN p.important_citations AS citations
        """
        try:
            result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})
            if result and result[0].get("citations"):
                citations = result[0]["citations"]
                # Parse citations if stored as JSON string
                if isinstance(citations, str):
                    import json
                    return json.loads(citations)
                return citations
        except Exception as e:
            logger.error(f"Error fetching citations: {e}")
        return []

    # =========================================================================
    # Neo4j Paper Node Creation
    # =========================================================================

    async def create_paper_node(
        self,
        metadata: BibliographicMetadata,
    ) -> bool:
        """PubMed 메타데이터로 Neo4j Paper 노드 생성.

        Args:
            metadata: PubMed 서지 정보

        Returns:
            성공 여부
        """
        paper_id = f"{self.PUBMED_PAPER_PREFIX}{metadata.pmid}"

        # Build PaperNode properties
        properties = {
            "paper_id": paper_id,
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "journal": metadata.journal,
            "journal_abbrev": metadata.journal_abbrev,
            "doi": metadata.doi or "",
            "pmid": metadata.pmid or "",
            "abstract": metadata.abstract[:2000] if metadata.abstract else "",
            "mesh_terms": metadata.mesh_terms[:20],
            "publication_types": metadata.publication_types[:10],
            "evidence_level": self._infer_evidence_level(metadata.publication_types),
            "source": "pubmed",
            "is_abstract_only": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        cypher = """
        MERGE (p:Paper {paper_id: $paper_id})
        SET p += $properties
        RETURN p.paper_id AS paper_id
        """

        try:
            result = await self.neo4j.run_query(cypher, {
                "paper_id": paper_id,
                "properties": properties,
            })
            logger.debug(f"Created/updated Paper node: {paper_id}")

            # Abstract 임베딩 자동 생성 (v1.14.12)
            if metadata.abstract and len(metadata.abstract.strip()) > 0:
                await self._generate_abstract_embedding(paper_id, metadata.abstract)

            return True
        except Exception as e:
            logger.error(f"Failed to create Paper node: {e}")
            return False

    async def _generate_abstract_embedding(
        self,
        paper_id: str,
        abstract: str
    ) -> bool:
        """Paper의 abstract 임베딩 생성 및 저장.

        Args:
            paper_id: Paper ID
            abstract: Abstract 텍스트

        Returns:
            성공 여부
        """
        try:
            import os
            from openai import OpenAI

            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # OpenAI 임베딩 생성 (3072차원)
            response = openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=abstract[:8000],
                dimensions=3072
            )

            embedding = response.data[0].embedding

            # Neo4j에 임베딩 저장
            await self.neo4j.run_write_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """,
                {"paper_id": paper_id, "embedding": embedding}
            )

            logger.debug(f"Abstract embedding generated for {paper_id}")
            return True

        except ImportError:
            logger.warning("OpenAI package not installed, skipping abstract embedding")
            return False
        except Exception as e:
            logger.warning(f"Failed to generate abstract embedding for {paper_id}: {e}")
            return False

    def _infer_evidence_level(self, publication_types: list[str]) -> str:
        """Publication types에서 근거 수준 추론."""
        types_lower = [pt.lower() for pt in publication_types]

        if any("meta-analysis" in pt for pt in types_lower):
            return "1a"
        elif any("systematic review" in pt for pt in types_lower):
            return "1a"
        elif any("randomized controlled trial" in pt for pt in types_lower):
            return "1b"
        elif any("clinical trial" in pt for pt in types_lower):
            return "2b"
        elif any("cohort" in pt for pt in types_lower):
            return "2b"
        elif any("case-control" in pt for pt in types_lower):
            return "3"
        elif any("case report" in pt for pt in types_lower):
            return "4"
        elif any("review" in pt for pt in types_lower):
            return "5"

        return "5"  # Default: Expert opinion / Unknown

    # =========================================================================
    # Abstract Chunking
    # =========================================================================

    async def chunk_abstract(
        self,
        paper_id: str,
        abstract: str,
        metadata: dict,
    ) -> int:
        """초록을 청크로 분할하여 Neo4j에 저장. (v5.3: Neo4j Vector Index 사용)

        Args:
            paper_id: Paper ID
            abstract: 초록 텍스트
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not abstract or not abstract.strip():
            return 0

        # Parse structured abstract (BACKGROUND, METHODS, RESULTS, CONCLUSIONS)
        chunks = self._parse_structured_abstract(paper_id, abstract, metadata)

        if not chunks:
            # Unstructured abstract - single chunk
            chunk_id = f"{paper_id}_abstract_0"
            chunks = [AbstractChunk(
                chunk_id=chunk_id,
                content=abstract.strip(),
                section="abstract",
                metadata=metadata,
            )]

        # Generate embeddings
        contents = [c.content for c in chunks]
        embeddings = self.embedding_generator.embed_batch(contents)

        # Convert AbstractChunk to TextChunk for vector_db
        text_chunks = []
        for chunk in chunks:
            text_chunk = TextChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                document_id=paper_id,
                tier="tier1",
                section=chunk.section,
                source_type="pubmed",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **chunk.metadata,
                    "source": "pubmed",
                    "is_abstract_only": True,
                },
            )
            text_chunks.append(text_chunk)

        # v5.3: Store chunks in Neo4j (ChromaDB deprecated)
        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        logger.debug(f"Added {total_added} chunks for paper {paper_id}")
        return total_added

    async def chunk_fulltext(
        self,
        paper_id: str,
        fulltext: "PMCFullText",
        metadata: dict,
    ) -> int:
        """PMC 전문을 청크로 분할하여 Neo4j에 저장. (v5.3: Neo4j Vector Index 사용)

        Args:
            paper_id: Paper ID
            fulltext: PMCFullText 객체 (전문 섹션 포함)
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not fulltext.has_full_text:
            return 0

        text_chunks = []

        # Add abstract as first chunk (tier1)
        if fulltext.abstract:
            chunk_id = f"{paper_id}_abstract_0"
            text_chunks.append(TextChunk(
                chunk_id=chunk_id,
                content=fulltext.abstract.strip(),
                document_id=paper_id,
                tier="tier1",
                section="abstract",
                source_type="pmc",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **metadata,
                    "source": "pmc_fulltext",
                    "pmcid": fulltext.pmcid or "",
                    "is_abstract_only": False,
                },
            ))

        # Add each section as chunks
        section_tier_map = {
            "INTRO": "tier2",
            "METHODS": "tier2",
            "RESULTS": "tier1",  # Results are important for retrieval
            "DISCUSS": "tier1",  # Discussion contains key insights
            "CONCL": "tier1",  # Conclusions are critical
            "OTHER": "tier2",
            "SUPP": "tier2",
        }

        for idx, section in enumerate(fulltext.sections):
            section_text = section.text.strip()
            if not section_text or len(section_text) < 50:
                continue

            tier = section_tier_map.get(section.section_type, "tier2")
            section_label = section.section_type.lower()

            # Split long sections into multiple chunks (max ~1500 chars each)
            chunks = self._split_section_text(section_text, max_chars=1500)

            for chunk_idx, chunk_text in enumerate(chunks):
                chunk_id = f"{paper_id}_{section_label}_{idx}_{chunk_idx}"
                text_chunks.append(TextChunk(
                    chunk_id=chunk_id,
                    content=chunk_text,
                    document_id=paper_id,
                    tier=tier,
                    section=section_label,
                    source_type="pmc",
                    evidence_level=metadata.get("evidence_level", "5"),
                    publication_year=metadata.get("publication_year", 0),
                    page_num=0,
                    title=metadata.get("title", ""),
                    authors=metadata.get("authors", []),
                    metadata={
                        **metadata,
                        "source": "pmc_fulltext",
                        "pmcid": fulltext.pmcid or "",
                        "is_abstract_only": False,
                        "section_title": section.title,
                    },
                ))

        if not text_chunks:
            return 0

        # Generate embeddings
        contents = [c.content for c in text_chunks]
        embeddings = self.embedding_generator.embed_batch(contents)

        # v5.3: Store chunks in Neo4j (ChromaDB deprecated)
        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        return total_added

    async def _store_chunks_to_neo4j(
        self,
        paper_id: str,
        text_chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> int:
        """청크를 Neo4j에 저장 (v5.3: ChromaDB 대체).

        Args:
            paper_id: Paper ID
            text_chunks: TextChunk 리스트
            embeddings: 임베딩 벡터 리스트

        Returns:
            저장된 청크 수
        """
        if not text_chunks:
            return 0

        try:
            from graph.spine_schema import ChunkNode

            chunk_nodes = []
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings)):
                chunk_node = ChunkNode(
                    chunk_id=chunk.chunk_id,
                    paper_id=paper_id,
                    content=chunk.content,
                    embedding=embedding,
                    tier=chunk.tier,
                    section=chunk.section,
                    evidence_level=getattr(chunk, 'evidence_level', "5"),
                    is_key_finding=getattr(chunk, 'is_key_finding', False),
                    page_num=getattr(chunk, 'page_num', 0),
                    chunk_index=i,
                )
                chunk_nodes.append(chunk_node)

            # Store in Neo4j
            result = await self.neo4j.create_chunks_batch(paper_id, chunk_nodes)
            created_count = result.get("created_count", len(chunk_nodes))

            tier1_count = sum(1 for c in text_chunks if c.tier == "tier1")
            tier2_count = sum(1 for c in text_chunks if c.tier == "tier2")
            logger.info(f"Neo4j Chunks: {created_count} stored with {len(embeddings[0]) if embeddings else 0}-dim embeddings (tier1: {tier1_count}, tier2: {tier2_count})")

            return created_count
        except Exception as e:
            logger.error(f"Failed to store chunks in Neo4j: {e}")
            return 0

    def _split_section_text(self, text: str, max_chars: int = 1500) -> list[str]:
        """긴 섹션 텍스트를 여러 청크로 분할.

        Args:
            text: 원본 텍스트
            max_chars: 청크당 최대 문자 수

        Returns:
            분할된 청크 리스트
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    def _parse_structured_abstract(
        self,
        paper_id: str,
        abstract: str,
        metadata: dict,
    ) -> list[AbstractChunk]:
        """구조화된 초록 파싱."""
        chunks = []

        # Common section labels in structured abstracts
        section_patterns = [
            (r"(?i)\bBACKGROUND[:\s]*", "background"),
            (r"(?i)\bOBJECTIVE[S]?[:\s]*", "objective"),
            (r"(?i)\bMETHOD[S]?[:\s]*", "methods"),
            (r"(?i)\bRESULT[S]?[:\s]*", "results"),
            (r"(?i)\bCONCLUSION[S]?[:\s]*", "conclusions"),
            (r"(?i)\bPURPOSE[:\s]*", "purpose"),
            (r"(?i)\bSETTING[:\s]*", "setting"),
            (r"(?i)\bPATIENTS?[:\s]*", "patients"),
            (r"(?i)\bINTERVENTION[S]?[:\s]*", "intervention"),
            (r"(?i)\bMAIN OUTCOME[S]?[:\s]*", "outcomes"),
        ]

        # Try to split by section labels
        sections = []
        current_pos = 0
        found_sections = []

        for pattern, section_name in section_patterns:
            for match in re.finditer(pattern, abstract):
                found_sections.append((match.start(), match.end(), section_name))

        # Sort by position
        found_sections.sort(key=lambda x: x[0])

        if len(found_sections) >= 2:
            # Structured abstract detected
            for i, (start, end, section_name) in enumerate(found_sections):
                if i + 1 < len(found_sections):
                    next_start = found_sections[i + 1][0]
                    content = abstract[end:next_start].strip()
                else:
                    content = abstract[end:].strip()

                if content:
                    chunk_id = f"{paper_id}_abstract_{len(chunks)}"
                    chunks.append(AbstractChunk(
                        chunk_id=chunk_id,
                        content=content,
                        section=section_name,
                        metadata=metadata,
                    ))

        return chunks

    def _build_chunk_metadata(self, paper: BibliographicMetadata) -> dict:
        """청크용 메타데이터 구성."""
        return {
            "paper_id": f"{self.PUBMED_PAPER_PREFIX}{paper.pmid}",
            "title": paper.title,
            "authors": paper.authors[:3] if paper.authors else [],  # First 3 authors
            "year": paper.year,
            "journal": paper.journal,
            "pmid": paper.pmid,
            "doi": paper.doi,
            "mesh_terms": paper.mesh_terms[:5],  # First 5 MeSH terms
            "is_abstract_only": True,
            "source": "pubmed",
        }

    async def _save_extracted_json(
        self,
        paper: BibliographicMetadata,
        extracted_data: dict,
    ) -> Optional[str]:
        """LLM에서 추출된 데이터를 JSON 파일로 저장.

        PDF 처리와 동일하게 data/extracted/ 폴더에 JSON 파일을 저장합니다.
        v5.3.4: PubMed 서지 메타데이터를 병합하여 저장합니다.

        Args:
            paper: 서지 메타데이터 (PubMed에서 가져온 정보)
            extracted_data: LLM에서 추출된 데이터

        Returns:
            저장된 파일 경로 또는 None (실패 시)
        """
        try:
            extracted_dir = Path("data/extracted")
            extracted_dir.mkdir(parents=True, exist_ok=True)

            # v5.3.4: PubMed 서지 메타데이터를 extracted_data["metadata"]에 병합
            # LLM은 spine_metadata만 추출하고 서지 정보는 추출하지 않으므로
            # PubMed에서 가져온 paper 정보를 병합해야 함
            if "metadata" not in extracted_data:
                extracted_data["metadata"] = {}

            metadata = extracted_data["metadata"]

            # PubMed 서지 정보 병합 (빈 값만 채움)
            if not metadata.get("title"):
                metadata["title"] = paper.title or ""
            if not metadata.get("authors"):
                metadata["authors"] = list(paper.authors) if paper.authors else []
            if not metadata.get("year"):
                metadata["year"] = paper.year
            if not metadata.get("journal"):
                metadata["journal"] = paper.journal or ""
            if not metadata.get("doi"):
                metadata["doi"] = paper.doi or ""
            if not metadata.get("pmid"):
                metadata["pmid"] = paper.pmid or ""
            if not metadata.get("abstract"):
                metadata["abstract"] = paper.abstract or ""

            # 추가 PubMed 메타데이터
            if not metadata.get("mesh_terms") and paper.mesh_terms:
                metadata["mesh_terms"] = list(paper.mesh_terms)
            if not metadata.get("publication_types") and paper.publication_types:
                metadata["publication_types"] = list(paper.publication_types)
            if not metadata.get("journal_abbrev") and paper.journal_abbrev:
                metadata["journal_abbrev"] = paper.journal_abbrev

            # 파일명 생성 (논문 제목 기반) - PDF 처리와 동일한 형식
            title = paper.title or "unknown"
            safe_title = "".join(c for c in title[:50] if c.isalnum() or c in " -_").strip()
            safe_title = safe_title.replace(" ", "_")

            # 저자명 추출
            first_author = "unknown"
            if paper.authors:
                first_author_name = paper.authors[0] if paper.authors else "unknown"
                # 성만 추출 (마지막 단어)
                first_author = first_author_name.split()[-1] if first_author_name else "unknown"

            year = paper.year or 0
            json_filename = f"{year}_{first_author}_{safe_title}.json"

            json_path = extracted_dir / json_filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)

            logger.info(f"PubMed extracted JSON saved: {json_path}")
            return str(json_path)

        except Exception as e:
            logger.warning(f"Failed to save extracted JSON: {e}")
            return None

    # =========================================================================
    # Duplicate Detection
    # =========================================================================

    async def _check_existing_paper(self, pmid: str) -> Optional[str]:
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
        paper_id = f"{self.PUBMED_PAPER_PREFIX}{pmid}"

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

    async def _check_existing_papers_batch(self, pmids: list[str]) -> dict[str, str]:
        """여러 PMID의 중복 여부를 한 번에 확인 (v1.14.24).

        LLM 처리 전에 일괄적으로 중복 체크하여 불필요한 API 호출을 방지합니다.

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
        paper_ids = [f"{self.PUBMED_PAPER_PREFIX}{pmid}" for pmid in pmids]

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

    # =========================================================================
    # Paper Upgrade (PDF Integration)
    # =========================================================================

    async def upgrade_with_pdf(
        self,
        paper_id: str,
        pdf_result: dict,
    ) -> dict:
        """PubMed-only Paper를 PDF 데이터로 업그레이드.

        기존 PubMed에서 가져온 초록 기반 데이터를
        PDF에서 추출한 전문 데이터로 업그레이드합니다.

        Args:
            paper_id: 업그레이드할 paper ID (pubmed_xxx 형식)
            pdf_result: PDF 처리 결과 (add_pdf의 결과)

        Returns:
            업그레이드 결과 딕셔너리
        """
        if not paper_id.startswith(self.PUBMED_PAPER_PREFIX):
            return {
                "success": False,
                "error": "Paper is not a PubMed-only paper",
            }

        # Get existing paper
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        RETURN p
        """
        result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})

        if not result:
            return {
                "success": False,
                "error": f"Paper not found: {paper_id}",
            }

        existing = result[0]["p"]

        # Merge metadata (keep PubMed identifiers, add PDF-extracted data)
        merge_cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        SET p.is_abstract_only = false,
            p.source = 'pdf+pubmed',
            p.updated_at = datetime(),
            p.sub_domain = COALESCE($sub_domain, p.sub_domain),
            p.study_type = COALESCE($study_type, p.study_type),
            p.evidence_level = COALESCE($evidence_level, p.evidence_level),
            p.sample_size = COALESCE($sample_size, p.sample_size),
            p.main_conclusion = COALESCE($main_conclusion, p.main_conclusion),
            p.pico_population = COALESCE($pico_population, p.pico_population),
            p.pico_intervention = COALESCE($pico_intervention, p.pico_intervention),
            p.pico_comparison = COALESCE($pico_comparison, p.pico_comparison),
            p.pico_outcome = COALESCE($pico_outcome, p.pico_outcome)
        RETURN p.paper_id AS paper_id
        """

        pdf_metadata = pdf_result.get("metadata", {})
        spine_metadata = pdf_metadata.get("spine_metadata", {})
        pico = spine_metadata.get("pico", {})

        try:
            await self.neo4j.run_query(merge_cypher, {
                "paper_id": paper_id,
                "sub_domain": spine_metadata.get("sub_domain"),
                "study_type": spine_metadata.get("study_type"),
                "evidence_level": spine_metadata.get("evidence_level"),
                "sample_size": spine_metadata.get("sample_size"),
                "main_conclusion": spine_metadata.get("main_conclusion"),
                "pico_population": pico.get("population"),
                "pico_intervention": pico.get("intervention"),
                "pico_comparison": pico.get("comparison"),
                "pico_outcome": pico.get("outcome"),
            })

            # Delete old abstract-only chunks
            await self._delete_paper_chunks(paper_id)

            return {
                "success": True,
                "paper_id": paper_id,
                "upgraded_from": "pubmed",
                "upgraded_to": "pdf+pubmed",
                "preserved_pmid": existing.get("pmid"),
                "preserved_mesh_terms": existing.get("mesh_terms"),
                "new_chunks": pdf_result.get("chunks_added", 0),
            }

        except Exception as e:
            logger.error(f"Failed to upgrade paper: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _delete_paper_chunks(self, paper_id: str) -> int:
        """논문의 기존 청크 삭제 (v5.3: Neo4j에서 삭제)."""
        try:
            # v5.3: Delete from Neo4j
            cypher = """
            MATCH (c:Chunk {paper_id: $paper_id})
            WITH c, c.chunk_id AS chunk_id
            DELETE c
            RETURN count(chunk_id) AS deleted_count
            """
            result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})
            deleted = result[0].get("deleted_count", 0) if result else 0
            logger.debug(f"Deleted {deleted} chunks for paper {paper_id} from Neo4j")
            return deleted
        except Exception as e:
            logger.warning(f"Failed to delete chunks from Neo4j: {e}")
            return 0

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_abstract_only_papers(
        self,
        limit: int = 100,
    ) -> list[dict]:
        """초록만 있는 논문 목록 조회.

        Args:
            limit: 최대 반환 수

        Returns:
            논문 정보 딕셔너리 목록
        """
        cypher = """
        MATCH (p:Paper)
        WHERE p.is_abstract_only = true
        RETURN p.paper_id AS paper_id,
               p.pmid AS pmid,
               p.title AS title,
               p.year AS year,
               p.journal AS journal,
               p.created_at AS created_at
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        try:
            result = await self.neo4j.run_query(cypher, {"limit": limit})
            return result
        except Exception as e:
            logger.error(f"Error fetching abstract-only papers: {e}")
            return []

    async def get_import_statistics(self) -> dict:
        """임포트 통계 조회."""
        cypher = """
        MATCH (p:Paper)
        WITH p.source AS source, p.is_abstract_only AS abstract_only, count(p) AS count
        RETURN source, abstract_only, count
        """
        try:
            result = await self.neo4j.run_query(cypher, {})
            stats = {
                "total_papers": 0,
                "pubmed_only": 0,
                "pdf_only": 0,
                "pdf_plus_pubmed": 0,
                "abstract_only": 0,
                "full_text": 0,
            }

            for row in result:
                count = row.get("count", 0)
                source = row.get("source")  # None for legacy papers
                abstract_only = row.get("abstract_only", False)

                stats["total_papers"] += count

                if source == "pubmed":
                    stats["pubmed_only"] += count
                elif source == "pdf" or source is None:
                    # Treat None (legacy) as PDF
                    stats["pdf_only"] += count
                elif source == "pdf+pubmed":
                    stats["pdf_plus_pubmed"] += count

                if abstract_only:
                    stats["abstract_only"] += count
                else:
                    stats["full_text"] += count

            return stats

        except Exception as e:
            logger.error(f"Error fetching import statistics: {e}")
            return {}
