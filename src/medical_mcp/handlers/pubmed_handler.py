"""PubMed Handler for Medical KAG Server.

This module handles all PubMed-related operations including:
- Paper search and retrieval
- Bulk paper import
- Citation import
- Paper upgrade with PDF
- Statistics and monitoring
- Auto-classification of imported papers (v1.14.18)
"""

import logging
import os
import re
from typing import TYPE_CHECKING, Optional, List

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

logger = logging.getLogger(__name__)

# Allowlist for Paper property updates (CA NEW-3: prevent Cypher injection)
ALLOWED_UPDATE_FIELDS = {
    "study_design", "subdomain", "sub_domain", "evidence_level", "journal",
    "doi", "pmid", "year", "authors", "abstract", "title", "summary",
}

# Sub-domain classification keywords (v1.14.18)
SUB_DOMAIN_KEYWORDS = {
    "Degenerative": [
        "disc herniation", "stenosis", "spondylolisthesis", "degenerative",
        "disc disease", "radiculopathy", "myelopathy", "sciatica",
        "discectomy", "decompression", "laminectomy", "fusion",
        "interbody", "ACDF", "TLIF", "PLIF", "ALIF", "LLIF", "OLIF",
        "UBE", "endoscopic", "minimally invasive", "MIS",
        "lumbar", "cervical", "thoracic", "spine surgery"
    ],
    "Deformity": [
        "scoliosis", "kyphosis", "deformity", "curvature",
        "sagittal", "coronal", "spinal alignment", "adult spinal deformity",
        "ASD", "adolescent idiopathic", "congenital"
    ],
    "Trauma": [
        "fracture", "trauma", "burst", "compression fracture",
        "vertebral fracture", "dislocation", "instability",
        "spinal cord injury", "SCI", "traumatic"
    ],
    "Tumor": [
        "tumor", "tumour", "metastatic", "metastasis", "cancer",
        "oncologic", "malignant", "neoplasm", "spinal tumor"
    ],
    "Infection": [
        "infection", "spondylodiscitis", "osteomyelitis", "abscess",
        "pyogenic", "tuberculous", "septic", "discitis"
    ],
    "Basic Science": [
        "biomechanical", "cadaveric", "in vitro", "cell",
        "molecular", "tissue engineering", "stem cell",
        "deep learning", "machine learning", "segmentation"
    ]
}

STUDY_DESIGN_KEYWORDS = {
    "meta_analysis": ["meta-analysis", "meta analysis", "systematic review and meta"],
    "systematic_review": ["systematic review", "literature review", "scoping review"],
    "randomized": ["randomized", "randomised", "RCT", "controlled trial"],
    "cohort": ["cohort", "prospective study", "longitudinal"],
    "case_control": ["case-control", "case control"],
    "retrospective": ["retrospective", "chart review"],
    "case_series": ["case series", "case report"]
}

# Check PubMed bulk processor availability
try:
    from builder.pubmed_bulk_processor import PubMedBulkProcessor
    PUBMED_BULK_AVAILABLE = True
except ImportError:
    logger.warning("PubMed Bulk Processor not available")
    PUBMED_BULK_AVAILABLE = False

# DOI Fulltext Fetcher availability
try:
    from builder.doi_fulltext_fetcher import DOIFulltextFetcher
    DOI_FETCHER_AVAILABLE = True
except ImportError:
    DOI_FETCHER_AVAILABLE = False
    DOIFulltextFetcher = None


def get_max_concurrent() -> int:
    """환경변수에서 PUBMED_MAX_CONCURRENT 값을 읽어옴.

    Returns:
        최대 동시 처리 수 (1-10 범위, 기본값 5)
    """
    try:
        value = int(os.environ.get("PUBMED_MAX_CONCURRENT", "5"))
        return max(1, min(value, 10))  # 1-10 범위로 제한
    except ValueError:
        return 5


class PubMedHandler(BaseHandler):
    """Handles PubMed search, import, and management operations."""

    def __init__(self, server: "MedicalKAGServer"):
        """Initialize PubMed handler.

        Args:
            server: Parent MedicalKAGServer instance for accessing clients
        """
        super().__init__(server)
        self.pubmed_client = server.pubmed_client
        self.pubmed_enricher = server.pubmed_enricher
        self.relationship_builder = server.relationship_builder

    async def _get_fresh_neo4j_client(self):
        """Create a fresh Neo4j client to avoid event loop conflicts with Streamlit."""
        from graph.neo4j_client import Neo4jClient
        return Neo4jClient()

    def _classify_sub_domain(self, title: str, abstract: str) -> Optional[str]:
        """제목과 초록으로 sub_domain 분류 (v1.14.18)."""
        text = f"{title} {abstract}".lower()
        scores = {}
        for domain, keywords in SUB_DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[domain] = score
        return max(scores, key=scores.get) if scores else None

    def _classify_study_design(self, title: str, abstract: str) -> Optional[str]:
        """제목과 초록으로 study_design 분류 (v1.14.18)."""
        text = f"{title} {abstract}".lower()
        for design, keywords in STUDY_DESIGN_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    return design
        return None

    async def _auto_classify_papers(
        self,
        neo4j_client,
        paper_ids: List[str]
    ) -> int:
        """임포트된 논문들 자동 분류 (v1.14.18).

        Args:
            neo4j_client: Neo4j 클라이언트
            paper_ids: 분류할 논문 ID 목록

        Returns:
            분류된 논문 수
        """
        classified_count = 0

        for paper_id in paper_ids:
            try:
                # 논문 정보 조회
                result = await neo4j_client.run_query(
                    "MATCH (p:Paper {paper_id: $paper_id}) "
                    "RETURN p.title as title, p.abstract as abstract, "
                    "p.sub_domain as sub_domain, p.study_design as study_design",
                    {"paper_id": paper_id}
                )

                if not result:
                    continue

                paper = result[0]
                title = paper.get("title") or ""
                abstract = paper.get("abstract") or ""

                # 이미 분류된 경우 스킵
                current_sub_domain = paper.get("sub_domain")
                current_study_design = paper.get("study_design")

                updates = {}

                # sub_domain 분류
                if not current_sub_domain or current_sub_domain in ["", "Unknown"]:
                    new_sub_domain = self._classify_sub_domain(title, abstract)
                    if new_sub_domain:
                        updates["sub_domain"] = new_sub_domain

                # study_design 분류
                if not current_study_design or current_study_design == "":
                    new_study_design = self._classify_study_design(title, abstract)
                    if new_study_design:
                        updates["study_design"] = new_study_design

                # 업데이트 실행
                if updates:
                    safe_updates = {k: v for k, v in updates.items() if k in ALLOWED_UPDATE_FIELDS}
                    if not safe_updates:
                        logger.warning(f"Paper {paper_id}: all update keys rejected by allowlist: {list(updates.keys())}")
                        continue
                    set_clauses = ", ".join([f"p.{k} = ${k}" for k in safe_updates.keys()])
                    await neo4j_client.run_query(
                        f"MATCH (p:Paper {{paper_id: $paper_id}}) SET {set_clauses}",
                        {"paper_id": paper_id, **safe_updates}
                    )
                    classified_count += 1

            except Exception as e:
                logger.warning(f"Failed to classify paper {paper_id}: {e}")

        logger.info(f"Auto-classified {classified_count} papers")
        return classified_count

    @safe_execute
    async def search_pubmed(
        self,
        query: str,
        max_results: int = 10,
        fetch_details: bool = True
    ) -> dict:
        """PubMed에서 논문 검색.

        Args:
            query: 검색 쿼리 (PubMed 문법 지원)
            max_results: 최대 결과 수
            fetch_details: 상세 정보 가져오기 여부

        Returns:
            검색 결과 딕셔너리
        """
        if not self.pubmed_client:
            return {"success": False, "error": "PubMed client not available"}

        # Search for PMIDs
        pmids = self.pubmed_client.search(query, max_results=max_results)

        if not pmids:
            return {
                "success": True,
                "query": query,
                "total_found": 0,
                "results": []
            }

        results = []
        if fetch_details:
            # Fetch paper details
            for pmid in pmids:
                try:
                    paper = self.pubmed_client.fetch_paper_details(pmid)
                    results.append({
                        "pmid": paper.pmid,
                        "title": paper.title,
                        "authors": paper.authors[:5],  # First 5 authors
                        "year": paper.year,
                        "journal": paper.journal,
                        "abstract": paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract,
                        "mesh_terms": paper.mesh_terms[:10],
                        "doi": paper.doi,
                        "publication_types": paper.publication_types
                    })
                except Exception as e:
                    logger.warning(f"Failed to fetch PMID {pmid}: {e}")
                    results.append({"pmid": pmid, "error": str(e)})
        else:
            results = [{"pmid": pmid} for pmid in pmids]

        return {
            "success": True,
            "query": query,
            "total_found": len(pmids),
            "results": results
        }

    @safe_execute
    async def pubmed_bulk_search(
        self,
        query: str,
        max_results: int = 50,
        import_results: bool = False,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> dict:
        """PubMed 대량 검색 및 선택적 임포트.

        Args:
            query: PubMed 검색 쿼리
            max_results: 최대 결과 수 (기본 50, 최대 500)
            import_results: True면 검색 결과를 Neo4j에 자동 임포트 (v5.3)
            year_from: 시작 연도 필터
            year_to: 종료 연도 필터
            publication_types: 출판 유형 필터 (예: ["Randomized Controlled Trial", "Meta-Analysis"])

        Returns:
            검색 결과 및 임포트 결과 (선택 시)
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        # Create a fresh Neo4j client to avoid event loop conflicts
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            # Initialize processor (v5.3: Neo4j 전용)
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

                pubmed_email=os.environ.get("NCBI_EMAIL"),
                pubmed_api_key=os.environ.get("NCBI_API_KEY"),
            )

            # Search PubMed
            papers = await processor.search_pubmed(
                query=query,
                max_results=min(max_results, 500),
                year_from=year_from,
                year_to=year_to,
                publication_types=publication_types,
            )

            result = {
                "success": True,
                "query": query,
                "total_found": len(papers),
                "papers": [
                    {
                        "pmid": p.pmid,
                        "title": p.title,
                        "authors": p.authors[:3],
                        "year": p.year,
                        "journal": p.journal,
                        "abstract": p.abstract[:300] + "..." if len(p.abstract or "") > 300 else p.abstract,
                        "mesh_terms": p.mesh_terms[:5],
                        "doi": p.doi,
                        "publication_types": p.publication_types,
                    }
                    for p in papers
                ],
            }

            # Import if requested (v1.5: 멀티유저, v1.14.23: 병렬 처리)
            if import_results and papers:
                import_summary = await processor.import_papers(
                    papers,
                    skip_existing=True,
                    owner=self.server.current_user,
                    shared=True,
                    max_concurrent=get_max_concurrent(),
                )
                result["import_result"] = {
                    "imported": import_summary.imported,
                    "skipped": import_summary.skipped,
                    "failed": import_summary.failed,
                    "total_chunks": import_summary.total_chunks,
                }

            return result

    @safe_execute
    async def pubmed_import_citations(
        self,
        paper_id: str,
        min_confidence: float = 0.7,
    ) -> dict:
        """기존 논문의 important citations를 PubMed에서 검색하여 임포트.

        Args:
            paper_id: 원본 논문 ID (citations 추출 대상)
            min_confidence: 최소 매칭 신뢰도 (기본 0.7)

        Returns:
            임포트 결과
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        # Create a fresh Neo4j client to avoid event loop conflicts
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

                pubmed_email=os.environ.get("NCBI_EMAIL"),
                pubmed_api_key=os.environ.get("NCBI_API_KEY"),
            )

            # v1.5: 멀티유저 지원
            summary = await processor.import_from_citations(
                paper_id=paper_id,
                min_confidence=min_confidence,
                owner=self.server.current_user,
                shared=True,
            )

            return {
                "success": True,
                "paper_id": paper_id,
                "total_citations_processed": summary.total_papers,
                "imported": summary.imported,
                "skipped": summary.skipped,
                "failed": summary.failed,
                "total_chunks": summary.total_chunks,
                "results": [r.to_dict() for r in summary.results[:20]],  # Max 20 results
            }

    @safe_execute
    async def upgrade_paper_with_pdf(
        self,
        paper_id: str,
        pdf_path: str,
    ) -> dict:
        """PubMed-only Paper를 PDF 데이터로 업그레이드.

        기존 PubMed에서 가져온 초록 기반 데이터를
        PDF에서 추출한 전문 데이터로 업그레이드합니다.

        Args:
            paper_id: 업그레이드할 paper ID (pubmed_xxx 형식)
            pdf_path: PDF 파일 경로

        Returns:
            업그레이드 결과
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        if not paper_id.startswith("pubmed_"):
            return {"success": False, "error": "Paper is not a PubMed-only paper (must start with 'pubmed_')"}

        # First, process the PDF using add_pdf
        pdf_result = await self.server.add_pdf(pdf_path)
        if not pdf_result.get("success"):
            return {"success": False, "error": f"PDF processing failed: {pdf_result.get('error')}"}

        # Create a fresh Neo4j client to avoid event loop conflicts
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

                pubmed_email=os.environ.get("NCBI_EMAIL"),
                pubmed_api_key=os.environ.get("NCBI_API_KEY"),
            )

            upgrade_result = await processor.upgrade_with_pdf(
                paper_id=paper_id,
                pdf_result=pdf_result,
            )

            return {
                "success": upgrade_result.get("success", False),
                "paper_id": paper_id,
                "upgraded_from": upgrade_result.get("upgraded_from"),
                "upgraded_to": upgrade_result.get("upgraded_to"),
                "preserved_pmid": upgrade_result.get("preserved_pmid"),
                "new_chunks": upgrade_result.get("new_chunks", 0),
                "error": upgrade_result.get("error"),
            }

    @safe_execute
    async def get_abstract_only_papers(
        self,
        limit: int = 50,
    ) -> dict:
        """초록만 있는 논문(PubMed-only) 목록 조회.

        Args:
            limit: 최대 반환 수

        Returns:
            논문 목록
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        # Create a fresh Neo4j client to avoid event loop conflicts
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

            )

            papers = await processor.get_abstract_only_papers(limit=limit)

            return {
                "success": True,
                "count": len(papers),
                "papers": papers,
            }

    @safe_execute
    async def import_papers_by_pmids(
        self,
        pmids: list[str],
        max_concurrent: Optional[int] = None,
    ) -> dict:
        """PMID 목록으로 직접 논문 임포트.

        검색 결과에서 선택된 논문들을 직접 임포트합니다.
        재검색 없이 PMID로 직접 PubMed에서 상세 정보를 가져와 임포트합니다.

        Args:
            pmids: 임포트할 PMID 목록
            max_concurrent: 최대 동시 처리 수 (기본값: PUBMED_MAX_CONCURRENT 환경변수)
                - None: 환경변수 사용 (기본)
                - 1: 순차 처리 (가장 안전, 느림)
                - 5: 권장 (적절한 속도와 안정성)
                - 10: 최대 (빠르지만 Neo4j/LLM 부하 증가)

        Returns:
            임포트 결과 요약
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        if not pmids:
            return {"success": False, "error": "No PMIDs provided"}

        # Create a fresh Neo4j client to avoid event loop conflicts
        # when called from Streamlit via run_async()
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

                pubmed_email=os.environ.get("NCBI_EMAIL"),
                pubmed_api_key=os.environ.get("NCBI_API_KEY"),
            )

            # Fetch paper details by PMIDs
            papers = await processor._fetch_papers_batch(pmids)

            if not papers:
                return {
                    "success": False,
                    "error": "Could not fetch paper details from PubMed",
                }

            # Import the fetched papers (v1.5: 멀티유저, v1.14.23: 병렬 처리)
            # max_concurrent: None이면 환경변수에서 읽음, 아니면 1-10 범위로 제한
            if max_concurrent is None:
                safe_concurrent = get_max_concurrent()
            else:
                safe_concurrent = max(1, min(max_concurrent, 10))

            summary = await processor.import_papers(
                papers,
                source="search",
                owner=self.server.current_user,
                shared=True,
                max_concurrent=safe_concurrent,
            )

            # v1.14.18: Auto-classify imported papers
            imported_paper_ids = [f"pubmed_{pmid}" for pmid in pmids]
            classified_count = await self._auto_classify_papers(
                fresh_neo4j, imported_paper_ids
            )

            return {
                "success": True,
                "total_requested": len(pmids),
                "total_fetched": len(papers),
                "auto_classified": classified_count,
                "import_summary": summary.to_dict(),
            }

    @safe_execute
    async def get_pubmed_import_stats(self) -> dict:
        """PubMed 임포트 통계 조회.

        Returns:
            통계 정보
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        self._require_neo4j()

        # Create a fresh Neo4j client to avoid event loop conflicts
        async with await self._get_fresh_neo4j_client() as fresh_neo4j:
            processor = PubMedBulkProcessor(
                neo4j_client=fresh_neo4j,

            )

            stats = await processor.get_import_statistics()

            return {
                "success": True,
                "statistics": stats,
            }

    @safe_execute
    async def hybrid_search(
        self,
        query: str,
        local_top_k: int = 10,
        pubmed_max_results: int = 20,
        min_local_results: int = 5,
        auto_import: bool = True,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> dict:
        """하이브리드 검색: 로컬 DB 우선 + PubMed 보완 (v1.14.24).

        1. 먼저 Neo4j에서 로컬 검색 (이미 분석된 논문 활용)
        2. 로컬 결과가 min_local_results 미만이면 PubMed에서 보완 검색
        3. 새로 찾은 논문은 자동 임포트 (선택)
        4. 로컬 + PubMed 결과 통합 반환

        Args:
            query: 검색 쿼리
            local_top_k: 로컬 검색 최대 결과 수 (기본 10)
            pubmed_max_results: PubMed 검색 최대 결과 수 (기본 20)
            min_local_results: 이 수 미만이면 PubMed 보완 (기본 5)
            auto_import: True면 새 논문 자동 임포트 (기본 True)
            year_from: PubMed 검색 시작 연도
            year_to: PubMed 검색 종료 연도

        Returns:
            통합 검색 결과:
            - local_results: 로컬 DB에서 찾은 결과 (이미 분석됨)
            - pubmed_results: PubMed에서 새로 찾은 결과
            - import_summary: 자동 임포트 결과 (auto_import=True 시)
        """
        result = {
            "success": True,
            "query": query,
            "local_results": [],
            "pubmed_results": [],
            "search_strategy": "local_only",
        }

        # === Step 1: 로컬 검색 (Neo4j) ===
        local_count = 0
        if self.server.search_handler:
            try:
                local_search = await self.server.search_handler.search(
                    query=query,
                    top_k=local_top_k,
                    tier_strategy="tier1_then_tier2",
                )

                if local_search.get("success") and local_search.get("results"):
                    local_results = local_search["results"]
                    local_count = len(local_results)

                    result["local_results"] = [
                        {
                            "paper_id": r.get("document_id", ""),
                            "title": r.get("title", ""),
                            "score": r.get("final_score", r.get("score", 0)),
                            "evidence_level": r.get("evidence_level", ""),
                            "section": r.get("section", ""),
                            "snippet": (r.get("text") or "")[:300] + "..." if len(r.get("text") or "") > 300 else (r.get("text") or ""),
                            "source": "local_db",
                        }
                        for r in local_results
                    ]

                    logger.info(f"Local search found {local_count} results for: {query}")

            except Exception as e:
                logger.warning(f"Local search failed: {e}")

        # === Step 2: PubMed 보완 검색 (로컬 결과 부족 시) ===
        if local_count < min_local_results:
            result["search_strategy"] = "local_plus_pubmed"
            logger.info(
                f"Local results ({local_count}) < min ({min_local_results}), "
                f"searching PubMed for: {query}"
            )

            if not PUBMED_BULK_AVAILABLE:
                result["pubmed_error"] = "PubMed Bulk Processor not available"
                return result

            if not self.neo4j_client:
                result["pubmed_error"] = "Neo4j client not available"
                return result

            async with await self._get_fresh_neo4j_client() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    pubmed_email=os.environ.get("NCBI_EMAIL"),
                    pubmed_api_key=os.environ.get("NCBI_API_KEY"),
                )

                # PubMed 검색
                papers = await processor.search_pubmed(
                    query=query,
                    max_results=pubmed_max_results,
                    year_from=year_from,
                    year_to=year_to,
                )

                if papers:
                    result["pubmed_results"] = [
                        {
                            "pmid": p.pmid,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.year,
                            "journal": p.journal,
                            "abstract": p.abstract[:300] + "..." if len(p.abstract or "") > 300 else p.abstract,
                            "doi": p.doi,
                            "source": "pubmed",
                        }
                        for p in papers
                    ]

                    logger.info(f"PubMed search found {len(papers)} papers for: {query}")

                    # === Step 3: 자동 임포트 (선택) ===
                    if auto_import and papers:
                        import_summary = await processor.import_papers(
                            papers,
                            skip_existing=True,
                            owner=self.server.current_user,
                            shared=True,
                            max_concurrent=get_max_concurrent(),
                        )

                        result["import_summary"] = {
                            "imported": import_summary.imported,
                            "skipped": import_summary.skipped,
                            "failed": import_summary.failed,
                            "total_chunks": import_summary.total_chunks,
                        }

                        logger.info(
                            f"Auto-import: {import_summary.imported} imported, "
                            f"{import_summary.skipped} skipped"
                        )
        else:
            result["search_strategy"] = "local_only"
            logger.info(f"Local results sufficient ({local_count} >= {min_local_results})")

        result["total_results"] = len(result["local_results"]) + len(result["pubmed_results"])
        return result

    # ========================================================================
    # DOI Methods (v1.12.2+)
    # ========================================================================

    @staticmethod
    def _validate_doi(doi: str) -> bool:
        """DOI 형식 검증 (10.xxxx/... 패턴)."""
        return bool(re.match(r'^10\.\d{4,}/.+$', str(doi).strip()))

    @safe_execute
    async def fetch_by_doi(
        self,
        doi: str,
        download_pdf: bool = False,
        import_to_graph: bool = False,
    ) -> dict:
        """DOI로 논문 메타데이터 및 전문 조회.

        Args:
            doi: DOI (예: "10.1016/j.spinee.2024.01.001")
            download_pdf: PDF 다운로드 여부
            import_to_graph: 그래프에 임포트 여부

        Returns:
            조회 결과
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        if not self._validate_doi(doi):
            return {"success": False, "error": f"Invalid DOI format: '{doi}'. DOI must match pattern '10.xxxx/...'"}

        fetcher = DOIFulltextFetcher()
        try:
            result = await fetcher.fetch(
                doi=doi,
                download_pdf=download_pdf,
                fetch_pmc=True,
            )

            response = {
                "success": True,
                "doi": doi,
                "has_metadata": result.has_metadata,
                "has_fulltext": result.has_full_text,
                "source": result.source,
            }

            if result.metadata:
                response["metadata"] = {
                    "title": result.metadata.title,
                    "authors": result.metadata.authors,
                    "journal": result.metadata.journal,
                    "year": result.metadata.year,
                    "abstract": result.metadata.abstract[:500] if result.metadata.abstract else None,
                    "pmid": result.metadata.pmid,
                    "pmcid": result.metadata.pmcid,
                    "is_open_access": result.metadata.is_open_access,
                    "oa_status": result.metadata.oa_status,
                    "pdf_url": result.metadata.pdf_url,
                    "cited_by_count": result.metadata.cited_by_count,
                    "license_url": result.metadata.license_url,
                }

            if result.has_full_text:
                response["fulltext_preview"] = result.full_text[:1000] if result.full_text else None
                response["fulltext_length"] = len(result.full_text) if result.full_text else 0

            if import_to_graph and result.metadata:
                import_result = await self._import_doi_to_graph(result)
                response["import_result"] = import_result

            return response
        finally:
            await fetcher.close()

    @safe_execute
    async def get_doi_metadata(self, doi: str) -> dict:
        """DOI 메타데이터만 조회 (전문 없이).

        Args:
            doi: DOI

        Returns:
            메타데이터
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        if not self._validate_doi(doi):
            return {"success": False, "error": f"Invalid DOI format: '{doi}'. DOI must match pattern '10.xxxx/...'"}

        fetcher = DOIFulltextFetcher()
        try:
            metadata = await fetcher.get_metadata_only(doi)

            if not metadata:
                return {"success": False, "error": f"No metadata found for DOI: {doi}"}

            return {
                "success": True,
                "doi": doi,
                "metadata": {
                    "title": metadata.title,
                    "authors": metadata.authors,
                    "journal": metadata.journal,
                    "year": metadata.year,
                    "volume": metadata.volume,
                    "issue": metadata.issue,
                    "pages": metadata.pages,
                    "abstract": metadata.abstract,
                    "publisher": metadata.publisher,
                    "issn": metadata.issn,
                    "subjects": metadata.subjects,
                    "pmid": metadata.pmid,
                    "pmcid": metadata.pmcid,
                    "is_open_access": metadata.is_open_access,
                    "oa_status": metadata.oa_status,
                    "pdf_url": metadata.pdf_url,
                    "cited_by_count": metadata.cited_by_count,
                    "references_count": metadata.references_count,
                    "license_url": metadata.license_url,
                },
            }
        finally:
            await fetcher.close()

    @safe_execute
    async def import_by_doi(
        self,
        doi: str,
        fetch_fulltext: bool = True,
    ) -> dict:
        """DOI로 논문을 그래프에 임포트.

        Args:
            doi: DOI
            fetch_fulltext: 전문 조회 시도 여부

        Returns:
            임포트 결과
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        self._require_neo4j()

        if not self._validate_doi(doi):
            return {"success": False, "error": f"Invalid DOI format: '{doi}'. DOI must match pattern '10.xxxx/...'"}

        fetcher = DOIFulltextFetcher()
        try:
            result = await fetcher.fetch(
                doi=doi,
                download_pdf=False,
                fetch_pmc=fetch_fulltext,
            )

            if not result.metadata:
                return {"success": False, "error": f"No metadata found for DOI: {doi}"}

            import_result = await self._import_doi_to_graph(result)

            return {
                "success": True,
                "doi": doi,
                "import_result": import_result,
            }
        finally:
            await fetcher.close()

    async def _import_doi_to_graph(self, doi_result) -> dict:
        """DOI 결과를 그래프에 임포트 (내부 메서드).

        Args:
            doi_result: DOI fetch 결과

        Returns:
            임포트 결과
        """
        if not doi_result.metadata:
            return {"success": False, "error": "No metadata to import"}

        meta = doi_result.metadata

        # paper_id 생성 (PMID 우선, 없으면 DOI 기반)
        if meta.pmid:
            paper_id = f"pubmed_{meta.pmid}"
        else:
            safe_doi = meta.doi.replace("/", "_").replace(".", "-")
            paper_id = f"doi_{safe_doi}"

        try:
            paper_data = {
                "paper_id": paper_id,
                "title": meta.title or "Unknown",
                "authors": meta.authors or [],
                "year": meta.year or 2024,
                "journal": meta.journal or "Unknown",
                "doi": meta.doi,
                "pmid": meta.pmid,
                "abstract": meta.abstract,
                "source": "doi_import",
                "is_open_access": meta.is_open_access,
                "oa_status": meta.oa_status,
            }

            query = """
            MERGE (p:Paper {paper_id: $paper_id})
            SET p.title = $title,
                p.authors = $authors,
                p.year = $year,
                p.journal = $journal,
                p.doi = $doi,
                p.pmid = $pmid,
                p.abstract = $abstract,
                p.source = $source,
                p.is_open_access = $is_open_access,
                p.oa_status = $oa_status,
                p.created_at = datetime()
            RETURN p.paper_id as paper_id
            """
            await self.neo4j_client.run_query(query, paper_data)

            # Abstract 임베딩 자동 생성
            if meta.abstract and len(meta.abstract.strip()) > 0:
                await self.server._generate_abstract_embedding(paper_id, meta.abstract)

            text_source = "none"
            if doi_result.has_full_text and doi_result.full_text:
                text_source = "fulltext"
            elif meta.abstract:
                text_source = "abstract"

            return {
                "success": True,
                "paper_id": paper_id,
                "text_source": text_source,
                "method": "basic_metadata",
            }

        except Exception as e:
            logger.exception(f"Graph import failed: {e}")
            return {"success": False, "error": str(e)}
