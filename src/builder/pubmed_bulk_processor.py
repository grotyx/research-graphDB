"""PubMed Bulk Processing Module (v5.3.1).

대량의 PubMed 논문을 검색하고 Neo4j에 임포트하는 기능을 제공합니다.
v5.3부터 Neo4j Vector Index만 사용합니다.
v5.3.1부터 OpenAI text-embedding-3-large (3072d)를 기본 임베딩으로 사용합니다.

D-009: 내부 로직은 pubmed_downloader.py와 pubmed_processor.py로 분리.
이 모듈은 두 모듈을 조합하는 Facade로 동작합니다.

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
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

try:
    from builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
    from builder.pmc_fulltext_fetcher import PMCFullTextFetcher
    from builder.unified_pdf_processor import UnifiedPDFProcessor
    from builder.doi_fulltext_fetcher import DOIFulltextFetcher
    from builder.pubmed_downloader import PubMedDownloader, build_search_query
    from builder.pubmed_processor import (
        PubMedPaperProcessor, AbstractChunk,
        infer_evidence_level, build_chunk_metadata,
        split_section_text, parse_structured_abstract,
    )
    from external.pubmed_client import PubMedClient
    from graph.relationship_builder import RelationshipBuilder
    from graph.entity_normalizer import EntityNormalizer
    from core.exceptions import ProcessingError, ErrorCode
    DOI_FETCHER_AVAILABLE = True
except ImportError:
    try:
        from src.builder.pubmed_enricher import BibliographicMetadata, PubMedEnricher
        from src.builder.pmc_fulltext_fetcher import PMCFullTextFetcher
        from src.builder.unified_pdf_processor import UnifiedPDFProcessor
        from src.builder.doi_fulltext_fetcher import DOIFulltextFetcher
        from src.builder.pubmed_downloader import PubMedDownloader, build_search_query
        from src.builder.pubmed_processor import (
            PubMedPaperProcessor, AbstractChunk,
            infer_evidence_level, build_chunk_metadata,
            split_section_text, parse_structured_abstract,
        )
        from src.external.pubmed_client import PubMedClient
        from src.graph.relationship_builder import RelationshipBuilder
        from src.graph.entity_normalizer import EntityNormalizer
        from src.core.exceptions import ProcessingError, ErrorCode
        DOI_FETCHER_AVAILABLE = True
    except ImportError:
        DOI_FETCHER_AVAILABLE = False
        DOIFulltextFetcher = None
        UnifiedPDFProcessor = None
        EntityNormalizer = None

if TYPE_CHECKING:
    from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes (backward-compatible re-exports)
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


# =============================================================================
# Main Processor Class (Facade)
# =============================================================================

class PubMedBulkProcessor:
    """PubMed 대량 처리기.

    Neo4j에 PubMed 논문을 대량으로 임포트합니다.
    내부적으로 PubMedDownloader (API/검색)와 PubMedPaperProcessor (처리/변환)에 위임합니다.

    Example:
        processor = PubMedBulkProcessor(neo4j_client)

        # Search and preview
        papers = await processor.search_pubmed("spine fusion", max_results=20)
        logger.info(f"Found {len(papers)} papers")

        # Import selected papers
        results = await processor.import_papers(papers[:10])
        logger.info(f"Imported {results.imported} papers")
    """

    # Paper ID prefix for PubMed-only papers
    PUBMED_PAPER_PREFIX = "pubmed_"

    # v5.3.1: Use OpenAI text-embedding-3-large (3072 dimensions)
    EMBEDDING_MODEL = "text-embedding-3-large"
    EMBEDDING_DIM = 3072

    def __init__(
        self,
        neo4j_client: "Neo4jClient",
        pubmed_email: Optional[str] = None,
        pubmed_api_key: Optional[str] = None,
        embedding_generator=None,
        enable_fulltext: bool = True,
        vision_processor: Optional[UnifiedPDFProcessor] = None,
        entity_normalizer: Optional[EntityNormalizer] = None,
    ):
        """PubMedBulkProcessor 초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            pubmed_email: NCBI 이메일 (권장)
            pubmed_api_key: NCBI API 키 (rate limit 향상)
            embedding_generator: 임베딩 생성기 (None이면 OpenAI 자동 생성)
            enable_fulltext: PMC Open Access 전문 가져오기 활성화 (기본 True)
            vision_processor: LLM 처리기 (None이면 자동 생성)
            entity_normalizer: 엔티티 정규화기 (None이면 자동 생성)
        """
        self.neo4j = neo4j_client
        self.pubmed_client = PubMedClient(email=pubmed_email, api_key=pubmed_api_key)
        self.pubmed_enricher = PubMedEnricher(email=pubmed_email, api_key=pubmed_api_key)

        # PMC Full Text Fetcher for Open Access papers
        self.enable_fulltext = enable_fulltext
        self.pmc_fetcher = PMCFullTextFetcher() if enable_fulltext else None

        # DOI Fulltext Fetcher (Crossref + Unpaywall)
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
                logger.error(f"OpenAI embedding initialization failed: {e}", exc_info=True)
                logger.error("OPENAI_API_KEY must be set - MedTE fallback removed (dimension mismatch)")
                raise ProcessingError(message=f"OpenAI embedding required (3072d index): {e}", error_code=ErrorCode.PROC_EMBEDDING_FAILED)

        # LLM processor for text analysis
        self.vision_processor = vision_processor
        if vision_processor is None:
            try:
                self.vision_processor = UnifiedPDFProcessor()
                logger.info("UnifiedPDFProcessor initialized for text/abstract LLM processing")
            except Exception as e:
                logger.warning(f"Failed to initialize UnifiedPDFProcessor: {e}")
                self.vision_processor = None

        # Entity normalizer
        self.entity_normalizer = entity_normalizer or EntityNormalizer()

        # Relationship builder
        self.relationship_builder = RelationshipBuilder(neo4j_client, self.entity_normalizer)

        # D-009: Delegate to focused modules
        self._downloader = PubMedDownloader(
            pubmed_client=self.pubmed_client,
            pubmed_enricher=self.pubmed_enricher,
            neo4j_client=neo4j_client,
        )
        self._processor = PubMedPaperProcessor(
            neo4j_client=neo4j_client,
            embedding_generator=self.embedding_generator,
            vision_processor=self.vision_processor,
            entity_normalizer=self.entity_normalizer,
            relationship_builder=self.relationship_builder,
        )

        logger.info(f"PubMedBulkProcessor initialized (fulltext={enable_fulltext}, llm_processing={self.vision_processor is not None})")

    # =========================================================================
    # Search Methods (delegate to PubMedDownloader)
    # =========================================================================

    async def search_pubmed(
        self,
        query: str,
        max_results: int = 50,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> list[BibliographicMetadata]:
        """PubMed에서 논문 검색."""
        return await self._downloader.search_pubmed(
            query, max_results=max_results,
            year_from=year_from, year_to=year_to,
            publication_types=publication_types,
        )

    def _build_search_query(
        self,
        base_query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> str:
        """검색 쿼리 구성."""
        return build_search_query(base_query, year_from, year_to, publication_types)

    async def _fetch_papers_batch(
        self,
        pmids: list[str],
        batch_size: int = 5,
    ) -> list[BibliographicMetadata]:
        """논문 상세 정보를 배치로 가져오기."""
        return await self._downloader.fetch_papers_batch(pmids, batch_size)

    async def _fetch_single_paper(self, pmid: str) -> BibliographicMetadata:
        """단일 논문 상세 정보 가져오기."""
        return await self._downloader.fetch_single_paper(pmid)

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
        owner: str = "system",
        shared: bool = True,
    ) -> BulkImportSummary:
        """PubMed 논문들을 Neo4j에 임포트."""
        summary = BulkImportSummary(total_papers=len(papers))

        # Batch duplicate check
        papers_to_import = papers
        if skip_existing:
            pmids = [p.pmid for p in papers if p.pmid]
            existing_pmids = await self._downloader.check_existing_papers_batch(pmids)

            if existing_pmids:
                papers_to_import = []
                for paper in papers:
                    if paper.pmid and paper.pmid in existing_pmids:
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

        if not papers_to_import:
            logger.info("All papers already exist, nothing to import")
            return summary

        effective_skip_existing = False if skip_existing else skip_existing

        if max_concurrent <= 1:
            for paper in papers_to_import:
                result = await self._import_with_error_handling(
                    paper, effective_skip_existing, source, fetch_fulltext, owner, shared
                )
                self._update_summary(summary, result)
        else:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def import_with_semaphore(paper: BibliographicMetadata) -> PubMedImportResult:
                async with semaphore:
                    return await self._import_with_error_handling(
                        paper, effective_skip_existing, source, fetch_fulltext, owner, shared
                    )

            logger.info(f"Starting parallel import: {len(papers_to_import)} papers, max_concurrent={max_concurrent}")

            results = await asyncio.gather(
                *[import_with_semaphore(paper) for paper in papers_to_import],
                return_exceptions=False
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
        owner: str = "system",
        shared: bool = True,
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
            logger.error(f"Error importing paper {paper.pmid}: {e}", exc_info=True)
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
        owner: str = "system",
        shared: bool = True,
    ) -> PubMedImportResult:
        """단일 논문 임포트."""
        pmid = paper.pmid or ""
        paper_id = f"{self.PUBMED_PAPER_PREFIX}{pmid}"

        # Check for existing paper
        if skip_existing and pmid:
            existing = await self._downloader.check_existing_paper(pmid)
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

        # Create Neo4j Paper node
        neo4j_created = await self._processor.create_paper_node(paper)

        # Try to fetch full text
        chunks_created = 0
        has_fulltext = False
        pmcid = ""
        llm_processed = False
        extracted_data: Optional[dict] = None

        # === Step 1: Try PMC (Open Access) ===
        if fetch_fulltext and self.pmc_fetcher and pmid:
            try:
                pmc_result = await self.pmc_fetcher.fetch_fulltext(pmid)
                if pmc_result.has_full_text:
                    has_fulltext = True
                    pmcid = pmc_result.pmcid or ""
                    logger.info(f"[PMC] Full text fetched for PMID {pmid} (PMCID: {pmcid})")

                    if self.vision_processor:
                        try:
                            chunks_created, llm_processed, extracted_data = await self._processor.process_fulltext_with_llm(
                                paper_id=paper_id, paper=paper, fulltext=pmc_result,
                                owner=owner, shared=shared,
                            )
                        except Exception as e:
                            logger.warning(f"LLM processing failed for {pmid}, falling back to simple chunking: {e}")

                    if not llm_processed:
                        chunks_created = await self._processor.chunk_fulltext(
                            paper_id=paper_id, fulltext=pmc_result,
                            metadata=build_chunk_metadata(paper),
                        )
            except Exception as e:
                logger.warning(f"Failed to fetch PMC full text for {pmid}: {e}")

        # === Step 2: Try DOI/Unpaywall if PMC failed ===
        if not has_fulltext and fetch_fulltext and self.doi_fetcher and paper.doi:
            try:
                doi_result = await self.doi_fetcher.fetch(
                    paper.doi, download_pdf=False, fetch_pmc=False,
                )
                if doi_result.has_full_text and doi_result.full_text:
                    has_fulltext = True
                    fulltext_source = f"unpaywall ({doi_result.metadata.oa_status if doi_result.metadata else 'unknown'})"
                    logger.info(f"[Unpaywall] Full text fetched for DOI {paper.doi} ({fulltext_source})")

                    if self.vision_processor:
                        try:
                            chunks_created, llm_processed, extracted_data = await self._processor.process_text_with_llm(
                                paper_id=paper_id, paper=paper, text=doi_result.full_text,
                                owner=owner, shared=shared,
                            )
                        except Exception as e:
                            logger.warning(f"LLM processing failed for DOI {paper.doi}: {e}")

                    if not llm_processed:
                        chunks_created = await self._processor.chunk_text(
                            paper_id=paper_id, text=doi_result.full_text,
                            metadata=build_chunk_metadata(paper),
                        )
                elif doi_result.metadata and doi_result.metadata.pdf_url:
                    logger.info(f"[Unpaywall] PDF URL available but not fetched: {doi_result.metadata.pdf_url[:50]}...")
            except Exception as e:
                logger.warning(f"Failed to fetch via DOI/Unpaywall for {paper.doi}: {e}")

        # === Step 3: Fallback to abstract ===
        if not has_fulltext and paper.abstract:
            if self.vision_processor:
                try:
                    chunks_created, llm_processed, extracted_data = await self._processor.process_abstract_with_llm(
                        paper_id=paper_id, paper=paper, owner=owner, shared=shared,
                    )
                except Exception as e:
                    logger.warning(f"LLM abstract processing failed for {pmid}, falling back to simple chunking: {e}")
                    llm_processed = False

            if not self.vision_processor or not llm_processed:
                chunks_created = await self._processor.chunk_abstract(
                    paper_id=paper_id, abstract=paper.abstract,
                    metadata=build_chunk_metadata(paper),
                )

        # JSON 저장
        if llm_processed and extracted_data:
            await self._processor.save_extracted_json(paper, extracted_data)

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

    # =========================================================================
    # Citation Import (delegate to PubMedDownloader)
    # =========================================================================

    async def import_from_citations(
        self,
        paper_id: str,
        min_confidence: float = 0.7,
        owner: str = "system",
        shared: bool = True,
    ) -> BulkImportSummary:
        """기존 논문의 important citations에서 PubMed 논문 임포트."""
        logger.info(f"Importing citations from paper: {paper_id}")

        citations = await self._downloader.get_important_citations(paper_id)

        if not citations:
            logger.info(f"No important citations found for paper: {paper_id}")
            return BulkImportSummary()

        logger.info(f"Found {len(citations)} citations to search")

        found_papers = await self._downloader.search_citation_papers(citations, min_confidence)

        logger.info(f"Found {len(found_papers)} papers from citations")

        if found_papers:
            return await self.import_papers(
                found_papers, skip_existing=True, source="citation",
                owner=owner, shared=shared,
            )

        return BulkImportSummary()

    async def _get_important_citations(self, paper_id: str) -> list[dict]:
        """Neo4j에서 논문의 important citations 가져오기."""
        return await self._downloader.get_important_citations(paper_id)

    # =========================================================================
    # Neo4j Paper Node (delegate to PubMedPaperProcessor)
    # =========================================================================

    async def create_paper_node(self, metadata: BibliographicMetadata) -> bool:
        """PubMed 메타데이터로 Neo4j Paper 노드 생성."""
        return await self._processor.create_paper_node(metadata)

    def _infer_evidence_level(self, publication_types: list[str]) -> str:
        """Publication types에서 근거 수준 추론."""
        return infer_evidence_level(publication_types)

    # =========================================================================
    # Chunking (delegate to PubMedPaperProcessor)
    # =========================================================================

    async def chunk_abstract(self, paper_id: str, abstract: str, metadata: dict) -> int:
        """초록을 청크로 분할하여 Neo4j에 저장."""
        return await self._processor.chunk_abstract(paper_id, abstract, metadata)

    async def chunk_fulltext(self, paper_id: str, fulltext, metadata: dict) -> int:
        """PMC 전문을 청크로 분할하여 Neo4j에 저장."""
        return await self._processor.chunk_fulltext(paper_id, fulltext, metadata)

    async def chunk_text(self, paper_id: str, text: str, metadata: dict) -> int:
        """일반 텍스트를 청크로 분할하여 Neo4j에 저장."""
        return await self._processor.chunk_text(paper_id, text, metadata)

    # =========================================================================
    # Duplicate Detection (delegate to PubMedDownloader)
    # =========================================================================

    async def _check_existing_paper(self, pmid: str) -> Optional[str]:
        """기존 논문 확인 (PMID로)."""
        return await self._downloader.check_existing_paper(pmid)

    async def _check_existing_papers_batch(self, pmids: list[str]) -> dict[str, str]:
        """여러 PMID의 중복 여부를 한 번에 확인."""
        return await self._downloader.check_existing_papers_batch(pmids)

    async def check_existing_by_doi(self, doi: str) -> Optional[str]:
        """DOI로 기존 논문 확인."""
        return await self._downloader.check_existing_by_doi(doi)

    # =========================================================================
    # Paper Upgrade (delegate to PubMedPaperProcessor)
    # =========================================================================

    async def upgrade_with_pdf(self, paper_id: str, pdf_result: dict) -> dict:
        """PubMed-only Paper를 PDF 데이터로 업그레이드."""
        return await self._processor.upgrade_with_pdf(paper_id, pdf_result)

    async def _delete_paper_chunks(self, paper_id: str) -> int:
        """논문의 기존 청크 삭제."""
        return await self._processor.delete_paper_chunks(paper_id)

    # =========================================================================
    # Utility Methods (delegate to PubMedPaperProcessor)
    # =========================================================================

    async def get_abstract_only_papers(self, limit: int = 100) -> list[dict]:
        """초록만 있는 논문 목록 조회."""
        return await self._processor.get_abstract_only_papers(limit)

    async def get_import_statistics(self) -> dict:
        """임포트 통계 조회."""
        return await self._processor.get_import_statistics()

    def _build_chunk_metadata(self, paper: BibliographicMetadata) -> dict:
        """청크용 메타데이터 구성."""
        return build_chunk_metadata(paper)

    def _split_section_text(self, text: str, max_chars: int = 1500) -> list[str]:
        """긴 섹션 텍스트를 여러 청크로 분할."""
        return split_section_text(text, max_chars)

    def _parse_structured_abstract(self, paper_id: str, abstract: str, metadata: dict) -> list:
        """구조화된 초록 파싱."""
        return parse_structured_abstract(paper_id, abstract, metadata)

    async def _save_extracted_json(self, paper: BibliographicMetadata, extracted_data: dict) -> Optional[str]:
        """LLM에서 추출된 데이터를 JSON 파일로 저장."""
        return await self._processor.save_extracted_json(paper, extracted_data)
