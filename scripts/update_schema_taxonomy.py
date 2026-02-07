#!/usr/bin/env python3
"""Schema, Taxonomy, SNOMED-CT 통합 업데이트 스크립트.

v7.14.2에서 추가된 신규 수술법, 별칭, SNOMED 코드를 Neo4j에 적용합니다.
주기적으로 실행하여 코드 변경사항을 데이터베이스에 반영합니다.

Usage:
    # 기본 실행 (schema + taxonomy + snomed)
    python scripts/update_schema_taxonomy.py

    # 검증만 (dry-run)
    python scripts/update_schema_taxonomy.py --dry-run

    # 강제 업데이트 (확인 없이)
    python scripts/update_schema_taxonomy.py --force

    # cron job용 (quiet mode)
    python scripts/update_schema_taxonomy.py --force --quiet

Cron 설정 예시 (매주 일요일 새벽 3시):
    0 3 * * 0 cd /path/to/rag_research && /path/to/python scripts/update_schema_taxonomy.py --force --quiet >> logs/schema_update.log 2>&1
"""

import asyncio
import argparse
import logging
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / '.env', override=True)

# Configure logging
def setup_logging(quiet: bool = False) -> logging.Logger:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


# v7.14.2 신규 Taxonomy 노드 정의
V7_14_2_TAXONOMY_UPDATES = [
    {
        "name": "Facetectomy",
        "query": """
            MERGE (facetectomy:Intervention {name: "Facetectomy"})
            SET facetectomy.category = "decompression",
                facetectomy.full_name = "Facet Joint Resection",
                facetectomy.aliases = ["Partial Facetectomy", "Medial Facetectomy", "Total Facetectomy"],
                facetectomy.snomed_code = "900000000000121",
                facetectomy.snomed_term = "Facetectomy",
                facetectomy.is_extension = true,
                facetectomy.updated_at = datetime()
            WITH facetectomy
            MATCH (open_decomp:Intervention {name: "Open Decompression"})
            MERGE (facetectomy)-[:IS_A {level: 2}]->(open_decomp)
            RETURN facetectomy.name as name, "created/updated" as status
        """,
        "parent": "Open Decompression",
        "snomed_code": "900000000000121"
    },
    {
        "name": "BELIF",
        "query": """
            MERGE (belif:Intervention {name: "BELIF"})
            SET belif.full_name = "Biportal Endoscopic Lumbar Interbody Fusion",
                belif.category = "fusion",
                belif.approach = "posterior",
                belif.is_minimally_invasive = true,
                belif.aliases = ["BE-TLIF", "BETLIF", "BE-LIF", "BELF"],
                belif.snomed_code = "900000000000119",
                belif.snomed_term = "Biportal endoscopic lumbar interbody fusion",
                belif.is_extension = true,
                belif.updated_at = datetime()
            WITH belif
            MATCH (tlif:Intervention {name: "TLIF"})
            MERGE (belif)-[:IS_A {level: 3}]->(tlif)
            RETURN belif.name as name, "created/updated" as status
        """,
        "parent": "TLIF",
        "snomed_code": "900000000000119"
    },
    {
        "name": "Stereotactic Navigation",
        "query": """
            MERGE (nav:Intervention {name: "Stereotactic Navigation"})
            SET nav.category = "navigation",
                nav.full_name = "Stereotactic Navigation-Guided Surgery",
                nav.aliases = ["Navigation", "O-arm Navigation", "CT Navigation", "CASS"],
                nav.snomed_code = "900000000000120",
                nav.snomed_term = "Stereotactic navigation-guided spine surgery",
                nav.is_extension = true,
                nav.updated_at = datetime()
            WITH nav
            MATCH (fixation:Intervention {name: "Fixation"})
            MERGE (nav)-[:IS_A {level: 1}]->(fixation)
            RETURN nav.name as name, "created/updated" as status
        """,
        "parent": "Fixation",
        "snomed_code": "900000000000120"
    }
]


async def check_neo4j_connection(logger: logging.Logger) -> bool:
    """Neo4j 연결 상태 확인."""
    try:
        from neo4j import GraphDatabase
        import os

        driver = GraphDatabase.driver(
            os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
            auth=(
                os.getenv('NEO4J_USERNAME', 'neo4j'),
                os.getenv('NEO4J_PASSWORD', 'spineGraph2024')
            )
        )

        with driver.session() as session:
            result = session.run("RETURN 1 as ping")
            result.single()

        driver.close()
        return True

    except Exception as e:
        logger.error(f"Neo4j 연결 실패: {e}")
        return False


async def get_current_state(logger: logging.Logger) -> dict:
    """현재 데이터베이스 상태 조회."""
    from neo4j import GraphDatabase
    import os

    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        auth=(
            os.getenv('NEO4J_USERNAME', 'neo4j'),
            os.getenv('NEO4J_PASSWORD', 'spineGraph2024')
        )
    )

    state = {
        "timestamp": datetime.now().isoformat(),
        "nodes": {},
        "taxonomy_nodes": [],
        "is_a_relationships": 0
    }

    with driver.session() as session:
        # 노드 통계
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] as label, count(*) as count
            ORDER BY count DESC
        """)
        for record in result:
            state["nodes"][record["label"]] = record["count"]

        # v7.14.2 Taxonomy 노드 확인
        result = session.run("""
            MATCH (i:Intervention)
            WHERE i.name IN ["BELIF", "Facetectomy", "Stereotactic Navigation"]
            OPTIONAL MATCH (i)-[:IS_A]->(parent:Intervention)
            RETURN i.name as name, i.snomed_code as snomed_code,
                   parent.name as parent, i.updated_at as updated_at
        """)
        for record in result:
            state["taxonomy_nodes"].append({
                "name": record["name"],
                "snomed_code": record["snomed_code"],
                "parent": record["parent"],
                "updated_at": str(record["updated_at"]) if record["updated_at"] else None
            })

        # IS_A 관계 수
        result = session.run("""
            MATCH ()-[r:IS_A]->()
            RETURN count(r) as count
        """)
        state["is_a_relationships"] = result.single()["count"]

    driver.close()
    return state


async def apply_taxonomy_updates(logger: logging.Logger, dry_run: bool = False) -> dict:
    """v7.14.2 Taxonomy 업데이트 적용."""
    from neo4j import GraphDatabase
    import os

    results = {
        "applied": [],
        "skipped": [],
        "errors": []
    }

    if dry_run:
        logger.info("🔍 Dry-run 모드: 실제 변경 없이 검증만 수행")
        for update in V7_14_2_TAXONOMY_UPDATES:
            logger.info(f"  [DRY-RUN] {update['name']} → {update['parent']} (SNOMED: {update['snomed_code']})")
            results["applied"].append(update["name"])
        return results

    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        auth=(
            os.getenv('NEO4J_USERNAME', 'neo4j'),
            os.getenv('NEO4J_PASSWORD', 'spineGraph2024')
        )
    )

    with driver.session() as session:
        for update in V7_14_2_TAXONOMY_UPDATES:
            try:
                result = session.run(update["query"])
                record = result.single()
                if record:
                    logger.info(f"  ✅ {update['name']}: {record['status']}")
                    results["applied"].append(update["name"])
                else:
                    logger.warning(f"  ⚠️ {update['name']}: 부모 노드 없음 ({update['parent']})")
                    results["skipped"].append(update["name"])
            except Exception as e:
                logger.error(f"  ❌ {update['name']}: {e}")
                results["errors"].append({"name": update["name"], "error": str(e)})

    driver.close()
    return results


async def run_schema_init(logger: logging.Logger, dry_run: bool = False) -> bool:
    """스키마 초기화 스크립트 실행."""
    if dry_run:
        logger.info("🔍 [DRY-RUN] init_neo4j.py 실행 예정")
        return True

    import subprocess

    script_path = project_root / "scripts" / "init_neo4j.py"

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            env={**dict(__import__('os').environ), "PYTHONPATH": str(project_root / "src")},
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )

        if result.returncode == 0:
            logger.info("✅ init_neo4j.py 실행 완료")
            return True
        else:
            logger.error(f"❌ init_neo4j.py 실행 실패:\n{result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("❌ init_neo4j.py 타임아웃 (5분 초과)")
        return False
    except Exception as e:
        logger.error(f"❌ init_neo4j.py 실행 오류: {e}")
        return False


async def verify_updates(logger: logging.Logger) -> dict:
    """업데이트 결과 검증."""
    from neo4j import GraphDatabase
    import os

    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        auth=(
            os.getenv('NEO4J_USERNAME', 'neo4j'),
            os.getenv('NEO4J_PASSWORD', 'spineGraph2024')
        )
    )

    verification = {
        "success": True,
        "details": []
    }

    with driver.session() as session:
        for update in V7_14_2_TAXONOMY_UPDATES:
            result = session.run(f"""
                MATCH (i:Intervention {{name: "{update['name']}"}})
                OPTIONAL MATCH (i)-[:IS_A]->(parent:Intervention)
                RETURN i.name as name, i.snomed_code as snomed_code,
                       i.full_name as full_name, parent.name as parent
            """)
            record = result.single()

            if record:
                check = {
                    "name": record["name"],
                    "snomed_code": record["snomed_code"],
                    "parent": record["parent"],
                    "expected_parent": update["parent"],
                    "expected_snomed": update["snomed_code"],
                    "valid": record["parent"] == update["parent"] and record["snomed_code"] == update["snomed_code"]
                }
                verification["details"].append(check)

                if not check["valid"]:
                    verification["success"] = False
                    logger.warning(f"  ⚠️ {update['name']}: 검증 실패")
                else:
                    logger.info(f"  ✅ {update['name']}: 검증 통과")
            else:
                verification["success"] = False
                verification["details"].append({
                    "name": update["name"],
                    "error": "노드 없음"
                })
                logger.error(f"  ❌ {update['name']}: 노드가 존재하지 않음")

    driver.close()
    return verification


async def main(args: argparse.Namespace) -> int:
    """메인 실행 함수."""
    logger = setup_logging(args.quiet)

    logger.info("=" * 60)
    logger.info("Schema, Taxonomy, SNOMED-CT 통합 업데이트")
    logger.info(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. Neo4j 연결 확인
    logger.info("\n[1/5] Neo4j 연결 확인...")
    if not await check_neo4j_connection(logger):
        logger.error("Neo4j 연결 실패. 스크립트를 종료합니다.")
        return 1
    logger.info("✅ Neo4j 연결 성공")

    # 2. 현재 상태 확인
    logger.info("\n[2/5] 현재 데이터베이스 상태 확인...")
    before_state = await get_current_state(logger)
    logger.info(f"  - Intervention 노드: {before_state['nodes'].get('Intervention', 0)}개")
    logger.info(f"  - IS_A 관계: {before_state['is_a_relationships']}개")
    logger.info(f"  - v7.14.2 노드: {len(before_state['taxonomy_nodes'])}개 존재")

    # 3. 사용자 확인 (--force가 아닌 경우)
    if not args.force and not args.dry_run:
        print("\n업데이트를 진행하시겠습니까? [y/N] ", end="")
        confirm = input().strip().lower()
        if confirm != 'y':
            logger.info("사용자가 취소했습니다.")
            return 0

    # 4. 스키마 초기화 실행
    logger.info("\n[3/5] 스키마 초기화 (init_neo4j.py)...")
    if not await run_schema_init(logger, args.dry_run):
        if not args.dry_run:
            logger.error("스키마 초기화 실패")
            return 1

    # 5. v7.14.2 Taxonomy 업데이트
    logger.info("\n[4/5] v7.14.2 Taxonomy 업데이트 적용...")
    update_results = await apply_taxonomy_updates(logger, args.dry_run)
    logger.info(f"  - 적용: {len(update_results['applied'])}개")
    logger.info(f"  - 스킵: {len(update_results['skipped'])}개")
    logger.info(f"  - 오류: {len(update_results['errors'])}개")

    # 6. 검증
    if not args.dry_run:
        logger.info("\n[5/5] 업데이트 검증...")
        verification = await verify_updates(logger)

        if verification["success"]:
            logger.info("✅ 모든 업데이트 검증 통과")
        else:
            logger.warning("⚠️ 일부 검증 실패 - 상세 내용 확인 필요")

    # 7. 결과 요약
    logger.info("\n" + "=" * 60)
    logger.info("업데이트 완료")
    logger.info("=" * 60)

    if not args.dry_run:
        after_state = await get_current_state(logger)
        logger.info(f"  - Intervention 노드: {before_state['nodes'].get('Intervention', 0)} → {after_state['nodes'].get('Intervention', 0)}")
        logger.info(f"  - IS_A 관계: {before_state['is_a_relationships']} → {after_state['is_a_relationships']}")

    # 8. 로그 파일로 결과 저장
    if not args.dry_run:
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"schema_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "before_state": before_state,
            "after_state": after_state,
            "update_results": update_results,
            "verification": verification if not args.dry_run else None
        }

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"\n📝 상세 로그: {log_file}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Schema, Taxonomy, SNOMED-CT 통합 업데이트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    # 대화형 실행
    python scripts/update_schema_taxonomy.py

    # 검증만 (변경 없음)
    python scripts/update_schema_taxonomy.py --dry-run

    # 자동 실행 (cron용)
    python scripts/update_schema_taxonomy.py --force --quiet
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 없이 검증만 수행"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="확인 없이 강제 실행"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="최소 출력 (cron용)"
    )

    args = parser.parse_args()

    try:
        exit_code = asyncio.run(main(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n오류: {e}")
        sys.exit(1)
