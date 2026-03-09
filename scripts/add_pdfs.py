#!/usr/bin/env python3
"""PDF 추가 스크립트.

사용법:
    # 단일 PDF 추가
    python scripts/add_pdfs.py /path/to/paper.pdf

    # 폴더 내 모든 PDF 추가
    python scripts/add_pdfs.py /path/to/pdf_folder/

    # 여러 PDF 추가
    python scripts/add_pdfs.py paper1.pdf paper2.pdf paper3.pdf
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from medical_mcp.medical_kag_server import MedicalKAGServer


async def add_single_pdf(server: MedicalKAGServer, pdf_path: Path) -> dict:
    """단일 PDF 추가."""
    print(f"\n📄 추가 중: {pdf_path.name}")

    result = await server.add_pdf(
        file_path=str(pdf_path),
        metadata={
            "title": pdf_path.stem,  # 파일명을 제목으로
            "source": "batch_import"
        }
    )

    if result.get("success"):
        stats = result.get("stats", {})
        print(f"   ✅ 성공: {stats.get('total_chunks', 0)}개 청크")
        print(f"      - Tier1: {stats.get('tier1_chunks', 0)}")
        print(f"      - Tier2: {stats.get('tier2_chunks', 0)}")
        print(f"      - Evidence Level: {stats.get('evidence_level', 'unknown')}")
    else:
        print(f"   ❌ 실패: {result.get('error', 'Unknown error')}")

    return result


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # 서버 초기화
    print("🚀 Medical KAG 서버 초기화...")
    server = MedicalKAGServer(
        data_dir=Path(__file__).parent.parent / "data",
        enable_llm=True
    )

    # PDF 경로 수집
    pdf_paths = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_dir():
            # 폴더면 내부 PDF 모두 수집
            pdf_paths.extend(path.glob("*.pdf"))
            pdf_paths.extend(path.glob("**/*.pdf"))  # 하위 폴더 포함
        elif path.is_file() and path.suffix.lower() == ".pdf":
            pdf_paths.append(path)
        else:
            print(f"⚠️  건너뜀 (PDF 아님): {arg}")

    # 중복 제거
    pdf_paths = list(set(pdf_paths))

    if not pdf_paths:
        print("❌ 추가할 PDF 파일이 없습니다.")
        sys.exit(1)

    print(f"\n📚 총 {len(pdf_paths)}개 PDF 발견")

    # 순차적으로 추가
    success_count = 0
    fail_count = 0

    for pdf_path in sorted(pdf_paths):
        result = await add_single_pdf(server, pdf_path)
        if result.get("success"):
            success_count += 1
        else:
            fail_count += 1

    # 최종 통계
    print(f"\n{'='*50}")
    print(f"📊 완료!")
    print(f"   ✅ 성공: {success_count}개")
    print(f"   ❌ 실패: {fail_count}개")

    # 전체 DB 상태
    stats = await server.get_stats()
    print(f"\n📈 현재 DB 상태:")
    print(f"   - 총 문서: {stats.get('document_count', 0)}개")
    print(f"   - 총 청크: {stats.get('chunk_count', 0)}개")


if __name__ == "__main__":
    asyncio.run(main())
