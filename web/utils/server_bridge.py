"""Server Bridge - Connection to MedicalKAGServer.

Provides singleton access to the Medical KAG server instance
for all Streamlit pages.
"""

import sys
from pathlib import Path

# Load .env FIRST before any other imports
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

import streamlit as st

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


class ServerBridge:
    """Bridge to MedicalKAGServer with caching."""

    _instance = None
    _server = None

    @classmethod
    def get_instance(cls) -> "ServerBridge":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def server(self):
        """Get or create server instance."""
        if self._server is None:
            self._server = self._create_server()
        return self._server

    def _create_server(self):
        """Create MedicalKAGServer instance."""
        from medical_mcp.medical_kag_server import MedicalKAGServer

        data_dir = Path(__file__).parent.parent.parent / "data"
        return MedicalKAGServer(data_dir=data_dir, enable_llm=True)

    @property
    def is_llm_enabled(self) -> bool:
        """Check if LLM is enabled."""
        return self.server.enable_llm and self.server.llm_client is not None

    @property
    def has_knowledge_graph(self) -> bool:
        """Check if Knowledge Graph is available.

        Note: v5.2+ uses Neo4j exclusively. Legacy SQLite paper_graph is deprecated.
        This property now checks for Neo4j availability.
        """
        # v5.2: Check Neo4j client instead of deprecated paper_graph
        return hasattr(self.server, 'neo4j_client') and self.server.neo4j_client is not None

    @property
    def has_query_expansion(self) -> bool:
        """Check if query expansion is available."""
        return self.server.concept_hierarchy is not None

    # =========================================================================
    # PubMed Bulk Processing Methods (v5.1)
    # =========================================================================

    async def pubmed_bulk_search(
        self,
        query: str,
        max_results: int = 50,
        import_results: bool = False,
        year_from: int | None = None,
        year_to: int | None = None,
        publication_types: list[str] | None = None,
    ) -> dict:
        """PubMed 대량 검색."""
        return await self.server.pubmed_bulk_search(
            query=query,
            max_results=max_results,
            import_results=import_results,
            year_from=year_from,
            year_to=year_to,
            publication_types=publication_types,
        )

    async def pubmed_import_citations(
        self,
        paper_id: str,
        min_confidence: float = 0.7,
    ) -> dict:
        """기존 논문의 인용 임포트."""
        return await self.server.pubmed_import_citations(
            paper_id=paper_id,
            min_confidence=min_confidence,
        )

    async def upgrade_paper_with_pdf(
        self,
        paper_id: str,
        pdf_path: str,
    ) -> dict:
        """Abstract-only 논문을 PDF로 업그레이드."""
        return await self.server.upgrade_paper_with_pdf(
            paper_id=paper_id,
            pdf_path=pdf_path,
        )

    async def get_abstract_only_papers(
        self,
        limit: int = 50,
    ) -> dict:
        """업그레이드 가능한 논문 목록 조회."""
        return await self.server.get_abstract_only_papers(limit=limit)

    async def get_pubmed_import_stats(self) -> dict:
        """PubMed 임포트 통계 조회."""
        return await self.server.get_pubmed_import_stats()

    async def import_papers_by_pmids(
        self,
        pmids: list[str],
    ) -> dict:
        """PMID 목록으로 직접 논문 임포트."""
        return await self.server.import_papers_by_pmids(pmids=pmids)


import os

# Cache version - change this to force cache refresh
_CACHE_VERSION = "v5"  # v5.1: PubMed Bulk Processing

# Clear any stale singleton on module load
ServerBridge._instance = None
ServerBridge._server = None

@st.cache_resource
def get_server(_version: str = _CACHE_VERSION) -> ServerBridge:
    """Get cached server bridge instance.

    Uses Streamlit's cache_resource to maintain single instance
    across all pages and sessions.

    Args:
        _version: Cache version (change to bust cache)
    """
    return ServerBridge.get_instance()
