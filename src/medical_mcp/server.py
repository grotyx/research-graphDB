"""MCP Server for Claude Code integration with Paper RAG system."""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src directory to path
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from core.pdf_parser import PDFParser, PDFParseError
from core.web_scraper import WebScraper, URLError, NetworkError, ParseError
from core.text_chunker import TextChunker
from core.embedding import EmbeddingGenerator
from core.vector_db import VectorDBManager
from search.engine import SearchEngine, format_search_results
from core.exceptions import ValidationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(src_dir.parent / 'mcp_server.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("paper-rag")

# Initialize components
DATA_DIR = src_dir.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

pdf_parser = PDFParser()
web_scraper = WebScraper()
chunker = TextChunker(chunk_size=512, chunk_overlap=50)
embedding_gen = EmbeddingGenerator()
vector_db = VectorDBManager(
    persist_directory=str(DATA_DIR / "chroma_db"),
    collection_name="papers"
)
search_engine = SearchEngine(embedding_gen, vector_db)

# Create MCP server
server = Server("paper-rag")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="add_pdf",
            description="PDF 논문을 RAG 시스템에 추가합니다. 파일 경로를 입력하세요.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "PDF 파일의 절대 경로"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="add_web",
            description="웹페이지를 RAG 시스템에 추가합니다. URL을 입력하세요.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "웹페이지 URL"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="search",
            description="저장된 논문에서 관련 내용을 검색합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 쿼리"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "반환할 결과 수 (기본: 5)",
                        "default": 5
                    },
                    "author": {
                        "type": "string",
                        "description": "특정 저자로 필터링 (선택)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_documents",
            description="저장된 문서 목록을 보여줍니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "author": {
                        "type": "string",
                        "description": "특정 저자로 필터링 (선택)"
                    }
                }
            }
        ),
        Tool(
            name="delete_document",
            description="저장된 문서를 삭제합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "삭제할 문서 ID"
                    }
                },
                "required": ["document_id"]
            }
        ),
        Tool(
            name="get_document_info",
            description="특정 문서의 상세 정보를 보여줍니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "문서 ID"
                    }
                },
                "required": ["document_id"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        if name == "add_pdf":
            result = await add_pdf(arguments.get("file_path", ""))
        elif name == "add_web":
            result = await add_web(arguments.get("url", ""))
        elif name == "search":
            result = await search(
                arguments.get("query", ""),
                arguments.get("top_k", 5),
                arguments.get("author")
            )
        elif name == "list_documents":
            result = await list_documents(arguments.get("author"))
        elif name == "delete_document":
            result = await delete_document(arguments.get("document_id", ""))
        elif name == "get_document_info":
            result = await get_document_info(arguments.get("document_id", ""))
        else:
            result = f"알 수 없는 도구: {name}"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [TextContent(type="text", text=f"오류: {str(e)}")]


async def add_pdf(file_path: str) -> str:
    """Add a PDF file to the RAG system."""
    if not file_path:
        return "오류: 파일 경로가 필요합니다."

    path = Path(file_path)

    if not path.exists():
        return f"오류: 파일을 찾을 수 없습니다 - {file_path}"

    if not path.suffix.lower() == ".pdf":
        return f"오류: PDF 파일이 아닙니다 - {file_path}"

    try:
        # Parse PDF
        logger.info(f"Parsing PDF: {file_path}")
        parse_result = pdf_parser.parse(file_path)

        # Chunk the document
        logger.info("Chunking document...")
        chunks = chunker.chunk_document(parse_result.pages, parse_result.metadata)

        if not chunks:
            return "오류: 문서에서 텍스트를 추출할 수 없습니다."

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        embedded_chunks = embedding_gen.embed_chunks(chunks)

        # Store in vector database
        logger.info("Storing in vector database...")
        ids = vector_db.add(embedded_chunks)

        title = parse_result.metadata.title or path.name
        return f"'{title}'을(를) 추가했습니다. ({len(ids)}개 청크)"

    except PDFParseError as e:
        return f"PDF 파싱 오류: {str(e)}"
    except Exception as e:
        logger.exception("Error adding PDF")
        return f"오류: {str(e)}"


async def add_web(url: str) -> str:
    """Add a web page to the RAG system."""
    if not url:
        return "오류: URL이 필요합니다."

    try:
        # Scrape web page
        logger.info(f"Scraping URL: {url}")
        scrape_result = web_scraper.scrape(url)

        # Chunk the content
        logger.info("Chunking content...")
        chunks = chunker.chunk_web_content(scrape_result.text, scrape_result.metadata)

        if not chunks:
            return "오류: 페이지에서 텍스트를 추출할 수 없습니다."

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        embedded_chunks = embedding_gen.embed_chunks(chunks)

        # Store in vector database
        logger.info("Storing in vector database...")
        ids = vector_db.add(embedded_chunks)

        title = scrape_result.metadata.title or url
        return f"'{title}'을(를) 추가했습니다. ({len(ids)}개 청크)"

    except URLError as e:
        return f"URL 오류: {str(e)}"
    except NetworkError as e:
        return f"네트워크 오류: {str(e)}"
    except ParseError as e:
        return f"파싱 오류: {str(e)}"
    except Exception as e:
        logger.exception("Error adding web page")
        return f"오류: {str(e)}"


async def search(query: str, top_k: int = 5, author: str | None = None) -> str:
    """Search for relevant content."""
    if not query:
        return "오류: 검색어가 필요합니다."

    try:
        # Build filter
        filter_dict = None
        if author:
            filter_dict = {"document_author": {"$contains": author}}

        # Perform search
        logger.info(f"Searching: {query}")
        response = search_engine.search(query, top_k=top_k, filter=filter_dict)

        return format_search_results(response)

    except (ValueError, ValidationError) as e:
        return f"검색 오류: {str(e)}"
    except Exception as e:
        logger.exception("Error during search")
        return f"오류: {str(e)}"


async def list_documents(author: str | None = None) -> str:
    """List all stored documents."""
    try:
        documents = vector_db.list_documents()

        if not documents:
            return "저장된 문서가 없습니다."

        # Filter by author if specified
        if author:
            documents = [
                d for d in documents
                if d.author and author.lower() in d.author.lower()
            ]

        if not documents:
            return f"'{author}' 저자의 문서가 없습니다."

        lines = [f"저장된 문서 {len(documents)}개:\n"]

        for i, doc in enumerate(documents, 1):
            lines.append(f"{i}. {doc.title or doc.document_id}")

            if doc.author:
                lines.append(f"   저자: {doc.author}")

            lines.append(f"   청크: {doc.chunk_count}개")
            lines.append(f"   유형: {doc.source_type}")

            if doc.added_at:
                lines.append(f"   추가일: {doc.added_at[:10]}")

            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error listing documents")
        return f"오류: {str(e)}"


async def delete_document(document_id: str) -> str:
    """Delete a document."""
    if not document_id:
        return "오류: 문서 ID가 필요합니다."

    try:
        # Get document info first
        doc_info = vector_db.get_document_info(document_id)

        if not doc_info:
            return f"오류: 문서를 찾을 수 없습니다 - {document_id}"

        # Delete
        success = vector_db.delete(document_id)

        if success:
            title = doc_info.title or document_id
            return f"'{title}'을(를) 삭제했습니다."
        else:
            return f"오류: 삭제에 실패했습니다 - {document_id}"

    except Exception as e:
        logger.exception("Error deleting document")
        return f"오류: {str(e)}"


async def get_document_info(document_id: str) -> str:
    """Get document information."""
    if not document_id:
        return "오류: 문서 ID가 필요합니다."

    try:
        doc_info = vector_db.get_document_info(document_id)

        if not doc_info:
            return f"오류: 문서를 찾을 수 없습니다 - {document_id}"

        lines = [
            "문서 정보:",
            f"  ID: {doc_info.document_id}",
            f"  제목: {doc_info.title or '알 수 없음'}",
            f"  저자: {doc_info.author or '알 수 없음'}",
            f"  유형: {doc_info.source_type}",
            f"  청크 수: {doc_info.chunk_count}",
        ]

        if doc_info.added_at:
            lines.append(f"  추가일: {doc_info.added_at}")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Error getting document info")
        return f"오류: {str(e)}"


async def main():
    """Run the MCP server."""
    logger.info("Starting Paper RAG MCP server...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
