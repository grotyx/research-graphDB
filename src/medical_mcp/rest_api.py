"""Medical KAG REST API Server.

MCP 도구들을 REST API로 제공하는 간단한 HTTP 서버.

Usage:
    python -m medical_mcp.rest_api --port 8080

Endpoints:
    GET  /health          - 서버 상태 확인
    GET  /tools           - 사용 가능한 도구 목록
    POST /tool/{name}     - 도구 실행

Example:
    curl http://localhost:8080/health
    curl http://localhost:8080/tools
    curl -X POST http://localhost:8080/tool/search \
        -H "Content-Type: application/json" \
        -d '{"query": "UBE lumbar stenosis", "top_k": 5}'
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from medical_mcp.medical_kag_server import MedicalKAGServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global server instance (protected by double-checked locking)
kag_server: MedicalKAGServer = None
_kag_server_lock = threading.Lock()


class ToolRequest(BaseModel):
    """Tool execution request."""
    class Config:
        extra = "allow"  # Allow any additional fields


def create_app() -> "FastAPI":
    """Create FastAPI application."""
    global kag_server

    app = FastAPI(
        title="Medical KAG API",
        description="Spine Surgery Knowledge Graph REST API",
        version="1.25.0"
    )

    # CORS 설정 (CORS_ORIGINS 환경변수 또는 localhost 기본값)
    cors_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8000,http://localhost:8501,http://127.0.0.1:3000,http://127.0.0.1:8000,http://127.0.0.1:8501",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-User-ID"],
    )

    @app.on_event("startup")
    async def startup():
        global kag_server
        if kag_server is None:
            with _kag_server_lock:
                if kag_server is None:
                    logger.info("Initializing Medical KAG Server...")
                    kag_server = MedicalKAGServer()
                    logger.info("Medical KAG Server initialized")

    @app.get("/health")
    async def health_check():
        """서버 상태 확인."""
        return {
            "status": "healthy",
            "server": "medical-kag",
            "neo4j_available": kag_server.neo4j_client is not None,
            "llm_enabled": getattr(kag_server, "enable_llm", False),
        }

    @app.get("/tools")
    async def list_tools():
        """사용 가능한 도구 목록."""
        tools = [
            {"name": "search", "description": "논문 검색 (query, top_k)"},
            {"name": "add_pdf", "description": "PDF 추가 (file_path)"},
            {"name": "list_documents", "description": "문서 목록 조회"},
            {"name": "get_stats", "description": "시스템 통계"},
            {"name": "pubmed_bulk_search", "description": "PubMed 대량 검색 (query, max_results, year_from, year_to)"},
            {"name": "import_papers_by_pmids", "description": "PMID로 논문 임포트 (pmids: list)"},
            {"name": "analyze_text", "description": "텍스트 직접 분석 (text, title, pmid)"},
            {"name": "get_intervention_hierarchy", "description": "수술법 계층 조회 (intervention_name)"},
            {"name": "find_conflicts", "description": "연구 결과 충돌 탐지 (topic)"},
            {"name": "get_paper_relations", "description": "논문 관계 조회 (paper_id)"},
            {"name": "compare_papers", "description": "논문 비교 (paper_ids: list)"},
        ]
        return {"tools": tools}

    @app.post("/tool/search")
    async def search(request: ToolRequest):
        """논문 검색."""
        data = request.model_dump()
        result = await kag_server.search(
            query=data.get("query", ""),
            top_k=data.get("top_k", 10),
            search_type=data.get("search_type", "hybrid"),
            tier=data.get("tier"),
            rerank=data.get("rerank", False),
        )
        return result

    @app.post("/tool/pubmed_bulk_search")
    async def pubmed_search(request: ToolRequest):
        """PubMed 대량 검색."""
        data = request.model_dump()
        if not kag_server.pubmed_handler:
            return {"success": False, "error": "PubMed handler not available"}
        result = await kag_server.pubmed_handler.pubmed_bulk_search(
            query=data.get("query", ""),
            max_results=data.get("max_results", 20),
            year_from=data.get("year_from"),
            year_to=data.get("year_to"),
            publication_types=data.get("publication_types"),
            auto_import=data.get("auto_import", False),
        )
        return result

    @app.post("/tool/import_papers_by_pmids")
    async def import_by_pmids(request: ToolRequest):
        """PMID로 논문 임포트."""
        data = request.model_dump()
        if not kag_server.pubmed_handler:
            return {"success": False, "error": "PubMed handler not available"}
        result = await kag_server.pubmed_handler.import_papers_by_pmids(
            pmids=data.get("pmids", [])
        )
        return result

    @app.post("/tool/analyze_text")
    async def analyze_text(request: ToolRequest):
        """텍스트 직접 분석."""
        data = request.model_dump()
        result = await kag_server.analyze_text(
            text=data.get("text", ""),
            title=data.get("title", ""),
            pmid=data.get("pmid"),
            metadata=data.get("metadata"),
        )
        return result

    @app.get("/tool/list_documents")
    async def list_documents():
        """문서 목록 조회."""
        if not kag_server.document_handler:
            return {"success": False, "error": "Document handler not available"}
        return await kag_server.document_handler.list_documents()

    @app.get("/tool/get_stats")
    async def get_stats():
        """시스템 통계."""
        if not kag_server.document_handler:
            return {"success": False, "error": "Document handler not available"}
        return await kag_server.document_handler.get_stats()

    @app.post("/tool/get_intervention_hierarchy")
    async def get_intervention_hierarchy(request: ToolRequest):
        """수술법 계층 조회."""
        data = request.model_dump()
        if not kag_server.graph_handler:
            return {"success": False, "error": "Graph handler not available"}
        return await kag_server.graph_handler.get_intervention_hierarchy(
            intervention_name=data.get("intervention_name", "")
        )

    @app.post("/tool/find_conflicts")
    async def find_conflicts(request: ToolRequest):
        """연구 결과 충돌 탐지."""
        data = request.model_dump()
        if not kag_server.reasoning_handler:
            return {"success": False, "error": "Reasoning handler not available"}
        return await kag_server.reasoning_handler.find_conflicts(
            topic=data.get("topic", ""),
            document_ids=data.get("document_ids"),
        )

    @app.post("/tool/get_paper_relations")
    async def get_paper_relations(request: ToolRequest):
        """논문 관계 조회."""
        data = request.model_dump()
        if not kag_server.graph_handler:
            return {"success": False, "error": "Graph handler not available"}
        return await kag_server.graph_handler.get_paper_relations(
            paper_id=data.get("paper_id", "")
        )

    @app.post("/tool/compare_papers")
    async def compare_papers(request: ToolRequest):
        """논문 비교."""
        data = request.model_dump()
        if not kag_server.reasoning_handler:
            return {"success": False, "error": "Reasoning handler not available"}
        return await kag_server.reasoning_handler.compare_papers(
            paper_ids=data.get("paper_ids", [])
        )

    return app


def main():
    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI not available. Install dependencies:")
        print("  pip install fastapi uvicorn")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Medical KAG REST API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (use 0.0.0.0 for network access)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    args = parser.parse_args()

    logger.info(f"Starting REST API server on http://{args.host}:{args.port}")
    logger.info(f"  API docs: http://{args.host}:{args.port}/docs")
    logger.info(f"  Health:   http://{args.host}:{args.port}/health")

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
