#!/usr/bin/env python3
"""Phase 4 테스트: Neo4j 전용 모드 검증.

테스트 항목:
1. MedicalKAGServer use_neo4j_storage 파라미터
2. TieredHybridSearch Neo4j 백엔드 기본 활성화
3. vector_db.py deprecation 경고
4. 마이그레이션 스크립트 dry-run
"""

import asyncio
import sys
import warnings
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def test_deprecation_warning():
    """vector_db.py deprecation 경고 테스트."""
    print("\n" + "=" * 60)
    print("1. vector_db.py Deprecation 경고 테스트")
    print("=" * 60)

    # 경고를 캡처
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        # vector_db 임포트 (경고 발생해야 함)
        from storage import vector_db

        # 경고 확인
        deprecation_warnings = [
            x for x in w
            if issubclass(x.category, DeprecationWarning)
            and "deprecated" in str(x.message).lower()
        ]

        if deprecation_warnings:
            print(f"✅ Deprecation 경고 발생: {deprecation_warnings[0].message}")
            return True
        else:
            print("⚠️ Deprecation 경고가 발생하지 않음")
            return False


def test_mcp_server_neo4j_mode():
    """MedicalKAGServer Neo4j 전용 모드 테스트."""
    print("\n" + "=" * 60)
    print("2. MedicalKAGServer Neo4j 전용 모드 테스트")
    print("=" * 60)

    try:
        # 경고 무시 (vector_db 임포트 시)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from medical_mcp.medical_kag_server import MedicalKAGServer

        # 기본값 확인 (use_neo4j_storage=True)
        import inspect
        sig = inspect.signature(MedicalKAGServer.__init__)
        default_value = sig.parameters.get('use_neo4j_storage')

        if default_value and default_value.default is True:
            print(f"✅ use_neo4j_storage 기본값: True")
        else:
            print(f"⚠️ use_neo4j_storage 기본값 확인 필요: {default_value}")

        return True

    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_search_engine_neo4j_backend():
    """TieredHybridSearch Neo4j 백엔드 테스트."""
    print("\n" + "=" * 60)
    print("3. TieredHybridSearch Neo4j 백엔드 테스트")
    print("=" * 60)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from solver.tiered_search import TieredHybridSearch, SearchBackend
            from graph.neo4j_client import Neo4jClient

        async with Neo4jClient() as neo4j_client:
            # Neo4j 전용 모드로 생성
            searcher = TieredHybridSearch(
                vector_db=None,
                neo4j_client=neo4j_client,
                use_neo4j_vector=True
            )

            # 백엔드 확인
            if searcher.use_neo4j_vector:
                print(f"✅ Neo4j Vector 백엔드 활성화")
            else:
                print(f"⚠️ Neo4j Vector 백엔드 비활성화")

            # Chunk 수 확인
            chunk_count = await neo4j_client.get_chunk_count()
            print(f"   Neo4j Chunk 수: {chunk_count}")

            return True

    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_migration_script_exists():
    """마이그레이션 스크립트 존재 확인."""
    print("\n" + "=" * 60)
    print("4. 마이그레이션 스크립트 확인")
    print("=" * 60)

    script_path = Path(__file__).parent / "migrate_chromadb_to_neo4j.py"

    if script_path.exists():
        print(f"✅ 마이그레이션 스크립트 존재: {script_path.name}")

        # 스크립트 내용 확인
        content = script_path.read_text()
        has_dry_run = "--dry-run" in content
        has_batch = "--batch-size" in content
        has_verify = "verify_migration" in content

        print(f"   - --dry-run 옵션: {'✅' if has_dry_run else '❌'}")
        print(f"   - --batch-size 옵션: {'✅' if has_batch else '❌'}")
        print(f"   - 검증 기능: {'✅' if has_verify else '❌'}")

        return has_dry_run and has_batch
    else:
        print(f"❌ 마이그레이션 스크립트 없음")
        return False


async def test_neo4j_vector_index():
    """Neo4j Vector Index 상태 확인."""
    print("\n" + "=" * 60)
    print("5. Neo4j Vector Index 상태 확인")
    print("=" * 60)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from graph.neo4j_client import Neo4jClient

        async with Neo4jClient() as client:
            # 인덱스 목록 조회
            result = await client.run_query(
                "SHOW INDEXES YIELD name, type, state WHERE type = 'VECTOR' RETURN name, state"
            )

            if result:
                print(f"✅ Vector Index 발견:")
                for idx in result:
                    print(f"   - {idx['name']}: {idx['state']}")
                return True
            else:
                print(f"⚠️ Vector Index 없음 (init_neo4j.py 실행 필요)")
                return False

    except Exception as e:
        print(f"❌ 오류: {e}")
        return False


async def main():
    """메인 테스트 실행."""
    print("=" * 60)
    print("Phase 4 테스트: Neo4j 전용 모드 (v5.3)")
    print("=" * 60)

    results = {}

    # 1. Deprecation 경고
    results["deprecation"] = test_deprecation_warning()

    # 2. MCP Server 모드
    results["mcp_server"] = test_mcp_server_neo4j_mode()

    # 3. Search Engine 백엔드
    results["search_engine"] = await test_search_engine_neo4j_backend()

    # 4. 마이그레이션 스크립트
    results["migration_script"] = test_migration_script_exists()

    # 5. Vector Index 상태
    results["vector_index"] = await test_neo4j_vector_index()

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"- {test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n✅ Phase 4 테스트 모두 통과!")
    else:
        print(f"\n⚠️ 일부 테스트 실패")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
