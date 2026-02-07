"""PDF 추가 예제.

이 스크립트는 Medical KAG 시스템에 PDF를 추가하는 방법을 보여줍니다.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from medical_mcp.medical_kag_server import MedicalKAGServer


async def main():
    """PDF 추가 예제."""

    # 1. 환경 변수 확인
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️  GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   export GEMINI_API_KEY='your-api-key-here'")
        print("   또는 .env 파일에 GEMINI_API_KEY=your-key 추가")
        print()
        print("   LLM 없이 규칙 기반으로 진행합니다...")
        enable_llm = False
    else:
        print("✅ GEMINI_API_KEY 확인됨")
        enable_llm = True

    # 2. 서버 초기화
    print("\n📚 Medical KAG 서버 초기화 중...")
    server = MedicalKAGServer(
        data_dir="./data",
        enable_llm=enable_llm
    )

    # 3. PDF 파일 경로 (예시)
    # 실제 사용시 본인의 PDF 경로로 변경하세요
    pdf_path = "/path/to/your/paper.pdf"

    # 예시: 현재 디렉토리의 PDF 찾기
    example_pdfs = list(Path(".").glob("*.pdf"))
    if example_pdfs:
        pdf_path = str(example_pdfs[0])
        print(f"📄 발견된 PDF: {pdf_path}")

    # 4. PDF 추가 (실제 파일이 있을 때만)
    if Path(pdf_path).exists():
        print(f"\n📥 PDF 추가 중: {pdf_path}")

        result = await server.add_pdf(
            file_path=pdf_path,
            metadata={
                "title": "논문 제목 (선택사항)",
                "authors": ["저자1", "저자2"],
                "year": 2024,
                "journal": "Journal Name"
            }
        )

        print("\n✅ 결과:")
        print(f"   - Document ID: {result.get('document_id')}")
        print(f"   - Chunks: {result.get('chunk_count')}")
        print(f"   - LLM 처리: {result.get('llm_processed', False)}")

        if "sections" in result:
            print(f"   - 섹션: {result['sections']}")

        if "pico" in result:
            print(f"   - PICO: {result['pico']}")
    else:
        print(f"\n⚠️  PDF 파일이 없습니다: {pdf_path}")
        print("   실제 PDF 경로로 수정 후 실행하세요.")

    # 5. 검색 예시
    print("\n🔍 검색 예시:")
    print("   search_result = await server.search('metformin diabetes')")

    # 6. 통계 확인
    stats = await server.get_stats()
    print(f"\n📊 현재 상태:")
    print(f"   - 총 문서 수: {stats.get('document_count', 0)}")
    print(f"   - 총 청크 수: {stats.get('chunk_count', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
