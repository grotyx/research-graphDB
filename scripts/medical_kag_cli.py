#!/usr/bin/env python3
"""Medical KAG CLI - 명령줄 인터페이스.

사용법:
    python scripts/medical_kag_cli.py add /path/to/paper.pdf
    python scripts/medical_kag_cli.py add /path/to/folder/
    python scripts/medical_kag_cli.py search "metformin diabetes"
    python scripts/medical_kag_cli.py list
    python scripts/medical_kag_cli.py stats
    python scripts/medical_kag_cli.py delete <document_id>
"""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from medical_mcp.medical_kag_server import MedicalKAGServer

# 전역 서버 인스턴스
_server = None


def get_server() -> MedicalKAGServer:
    global _server
    if _server is None:
        _server = MedicalKAGServer(
            data_dir=Path(__file__).parent.parent / "data",
            enable_llm=True
        )
    return _server


async def cmd_add(args):
    """PDF 추가."""
    if not args:
        print("❌ PDF 경로를 입력하세요")
        return

    server = get_server()
    pdf_paths = []

    for arg in args:
        path = Path(arg)
        if path.is_dir():
            pdf_paths.extend(path.glob("*.pdf"))
            pdf_paths.extend(path.glob("**/*.pdf"))
        elif path.is_file() and path.suffix.lower() == ".pdf":
            pdf_paths.append(path)

    pdf_paths = list(set(pdf_paths))

    if not pdf_paths:
        print("❌ PDF 파일을 찾을 수 없습니다")
        return

    print(f"📚 {len(pdf_paths)}개 PDF 추가 중...")

    for pdf_path in sorted(pdf_paths):
        print(f"  📄 {pdf_path.name}...", end=" ")
        result = await server.add_pdf(str(pdf_path))
        if result.get("success"):
            chunks = result.get("stats", {}).get("total_chunks", 0)
            print(f"✅ ({chunks} chunks)")
        else:
            print(f"❌ {result.get('error', 'Error')}")


async def cmd_search(args):
    """검색."""
    if not args:
        print("❌ 검색어를 입력하세요")
        return

    query = " ".join(args)
    server = get_server()

    print(f"🔍 검색: {query}\n")
    result = await server.search(query, top_k=5)

    if not result.get("success"):
        print(f"❌ 검색 실패: {result.get('error')}")
        return

    results = result.get("results", [])
    if not results:
        print("검색 결과 없음")
        return

    for i, r in enumerate(results, 1):
        print(f"[{i}] {r.get('document_id', 'Unknown')} (score: {r.get('score', 0):.3f})")
        print(f"    섹션: {r.get('section', 'N/A')} | 근거수준: {r.get('evidence_level', 'N/A')}")
        content = r.get("content", "")[:200]
        print(f"    {content}...")
        print()


async def cmd_list(args):
    """문서 목록."""
    server = get_server()
    result = await server.list_documents()

    if not result.get("success"):
        print(f"❌ 오류: {result.get('error')}")
        return

    docs = result.get("documents", [])
    if not docs:
        print("저장된 문서가 없습니다")
        return

    print(f"📚 총 {len(docs)}개 문서:\n")
    for doc in docs:
        print(f"  • {doc.get('document_id', 'Unknown')}")
        print(f"    청크: {doc.get('chunk_count', 0)}개")
        if doc.get('metadata'):
            meta = doc['metadata']
            if meta.get('title'):
                print(f"    제목: {meta['title']}")
            if meta.get('year'):
                print(f"    연도: {meta['year']}")
        print()


async def cmd_stats(args):
    """통계."""
    server = get_server()
    result = await server.get_stats()

    print("📊 Medical KAG 통계\n")
    print(f"  문서 수: {result.get('document_count', 0)}")
    print(f"  청크 수: {result.get('chunk_count', 0)}")
    print(f"  Tier1 청크: {result.get('tier1_count', 0)}")
    print(f"  Tier2 청크: {result.get('tier2_count', 0)}")


async def cmd_delete(args):
    """문서 삭제."""
    if not args:
        print("❌ 문서 ID를 입력하세요")
        return

    doc_id = args[0]
    server = get_server()

    confirm = input(f"정말 '{doc_id}'를 삭제하시겠습니까? (y/N): ")
    if confirm.lower() != 'y':
        print("취소됨")
        return

    result = await server.delete_document(doc_id)
    if result.get("success"):
        print(f"✅ 삭제됨: {result.get('deleted_chunks', 0)}개 청크")
    else:
        print(f"❌ 삭제 실패: {result.get('error')}")


async def cmd_draft(args):
    """인용 검색."""
    if not args:
        print("❌ 주제를 입력하세요")
        print("   예: python medical_kag_cli.py draft '당뇨병 치료'")
        return

    topic = " ".join(args)
    server = get_server()

    print(f"📝 '{topic}'에 대한 인용 검색 중...\n")
    result = await server.draft_with_citations(topic, section_type="introduction")

    if not result.get("success"):
        print(f"❌ 오류: {result.get('error')}")
        return

    citations = result.get("citations", [])
    if not citations:
        print("관련 논문을 찾지 못했습니다")
        return

    print(result.get("message", ""))
    print("\n" + "="*50 + "\n")

    for c in citations:
        print(f"[{c.get('citation_number')}] {c.get('citation_key')}")
        print(f"    📊 근거수준: {c.get('evidence_level', 'N/A')}")
        print(f"    💡 활용: {c.get('usage_suggestion', '')}")
        print(f"    📄 내용: {c.get('content_summary', '')[:150]}...")
        print()

    print("="*50)
    print("\n📚 참고문헌:")
    for ref in result.get("references", []):
        authors = ", ".join(ref.get("authors", []))
        print(f"  [{ref.get('number')}] {authors} ({ref.get('year')}). {ref.get('title')}")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n명령어:")
        print("  add <path>     - PDF 추가")
        print("  search <query> - 검색")
        print("  list           - 문서 목록")
        print("  stats          - 통계")
        print("  delete <id>    - 문서 삭제")
        print("  draft <topic>  - 인용 검색")
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "add": cmd_add,
        "search": cmd_search,
        "list": cmd_list,
        "stats": cmd_stats,
        "delete": cmd_delete,
        "draft": cmd_draft,
    }

    if cmd in commands:
        await commands[cmd](args)
    else:
        print(f"❌ 알 수 없는 명령어: {cmd}")
        print("   사용 가능: add, search, list, stats, delete, draft")


if __name__ == "__main__":
    asyncio.run(main())
