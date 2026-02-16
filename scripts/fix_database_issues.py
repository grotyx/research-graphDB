#!/usr/bin/env python3
"""데이터베이스 문제 수정 스크립트.

시스템 점검에서 발견된 문제들을 수정합니다:
1. Taxonomy 보강 - 미연결 Intervention들을 적절한 카테고리에 연결
2. SNOMED Enrichment - SNOMED 코드 일괄 적용
3. Paper Abstract 임베딩 생성
4. Pathology 카테고리 정비

Usage:
    python scripts/fix_database_issues.py
    python scripts/fix_database_issues.py --skip-embeddings
    python scripts/fix_database_issues.py --dry-run
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_file = project_root / '.env'
load_dotenv(env_file, override=True)

from src.graph.neo4j_client import Neo4jClient, Neo4jConfig
from src.graph.spine_schema import SpineGraphSchema

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def fix_taxonomy(client: Neo4jClient, dry_run: bool = False) -> dict:
    """Taxonomy 보강 - 미연결 Intervention들을 적절한 카테고리에 연결.

    Args:
        client: Neo4j 클라이언트
        dry_run: True면 실제 변경 없이 예상 결과만 출력

    Returns:
        수정 결과 통계
    """
    logger.info("\n" + "=" * 60)
    logger.info("📊 [1/4] Taxonomy 보강")
    logger.info("=" * 60)

    stats = {"success": 0, "failed": 0, "queries": 0}

    # 수정 전 상태 확인
    orphan_query = """
    MATCH (i:Intervention)
    WHERE NOT (i)-[:IS_A]->(:Intervention)
      AND NOT (i)<-[:IS_A]-(:Intervention)
    RETURN count(i) as orphan_count
    """

    result = await client.run_query(orphan_query, fetch_all=False)
    orphan_count_before = result[0]["orphan_count"] if result else 0
    logger.info(f"   미연결 Intervention 노드: {orphan_count_before}개")

    if dry_run:
        logger.info("   [DRY-RUN] 변경 사항 없음")
        return stats

    # Taxonomy 수정 쿼리 실행
    queries = SpineGraphSchema.get_fix_orphan_interventions_cypher()
    stats["queries"] = len(queries)

    for i, query in enumerate(queries, 1):
        try:
            await client.run_write_query(query)
            stats["success"] += 1
            logger.info(f"   ✅ Taxonomy batch {i}/{len(queries)} 적용됨")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"   ⚠️ Taxonomy batch {i} 실패: {e}")

    # 수정 후 상태 확인
    result = await client.run_query(orphan_query, fetch_all=False)
    orphan_count_after = result[0]["orphan_count"] if result else 0

    logger.info(f"\n   📈 결과: {orphan_count_before}개 → {orphan_count_after}개 (감소: {orphan_count_before - orphan_count_after}개)")

    return stats


async def fix_snomed(client: Neo4jClient, dry_run: bool = False) -> dict:
    """SNOMED 코드 일괄 적용.

    Args:
        client: Neo4j 클라이언트
        dry_run: True면 실제 변경 없이 예상 결과만 출력

    Returns:
        수정 결과 통계
    """
    logger.info("\n" + "=" * 60)
    logger.info("🏥 [2/4] SNOMED Enrichment")
    logger.info("=" * 60)

    stats = {"success": 0, "failed": 0, "queries": 0}

    # 수정 전 SNOMED 커버리지 확인
    coverage_query = """
    MATCH (i:Intervention)
    WITH count(i) as total_int,
         count(CASE WHEN i.snomed_code IS NOT NULL AND i.snomed_code <> '' THEN 1 END) as snomed_int
    MATCH (p:Pathology)
    WITH total_int, snomed_int, count(p) as total_path,
         count(CASE WHEN p.snomed_code IS NOT NULL AND p.snomed_code <> '' THEN 1 END) as snomed_path
    MATCH (o:Outcome)
    WITH total_int, snomed_int, total_path, snomed_path, count(o) as total_out,
         count(CASE WHEN o.snomed_code IS NOT NULL AND o.snomed_code <> '' THEN 1 END) as snomed_out
    MATCH (a:Anatomy)
    RETURN total_int, snomed_int, total_path, snomed_path, total_out, snomed_out,
           count(a) as total_anat,
           count(CASE WHEN a.snomed_code IS NOT NULL AND a.snomed_code <> '' THEN 1 END) as snomed_anat
    """

    result = await client.run_query(coverage_query, fetch_all=False)
    if result:
        r = result[0]
        logger.info(f"   수정 전 SNOMED 커버리지:")
        logger.info(f"     - Intervention: {r['snomed_int']}/{r['total_int']} ({100*r['snomed_int']/max(r['total_int'],1):.1f}%)")
        logger.info(f"     - Pathology: {r['snomed_path']}/{r['total_path']} ({100*r['snomed_path']/max(r['total_path'],1):.1f}%)")
        logger.info(f"     - Outcome: {r['snomed_out']}/{r['total_out']} ({100*r['snomed_out']/max(r['total_out'],1):.1f}%)")
        logger.info(f"     - Anatomy: {r['snomed_anat']}/{r['total_anat']} ({100*r['snomed_anat']/max(r['total_anat'],1):.1f}%)")

    if dry_run:
        logger.info("   [DRY-RUN] 변경 사항 없음")
        return stats

    # SNOMED enrichment 쿼리 실행
    queries = SpineGraphSchema.get_enrich_snomed_cypher()
    stats["queries"] = len(queries)

    for i, (query, params) in enumerate(queries, 1):
        try:
            await client.run_write_query(query, params)
            stats["success"] += 1
            logger.info(f"   ✅ SNOMED batch {i}/{len(queries)} 적용됨")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"   ⚠️ SNOMED batch {i} 실패: {e}")

    # 수정 후 커버리지 확인
    result = await client.run_query(coverage_query, fetch_all=False)
    if result:
        r = result[0]
        logger.info(f"\n   📈 수정 후 SNOMED 커버리지:")
        logger.info(f"     - Intervention: {r['snomed_int']}/{r['total_int']} ({100*r['snomed_int']/max(r['total_int'],1):.1f}%)")
        logger.info(f"     - Pathology: {r['snomed_path']}/{r['total_path']} ({100*r['snomed_path']/max(r['total_path'],1):.1f}%)")
        logger.info(f"     - Outcome: {r['snomed_out']}/{r['total_out']} ({100*r['snomed_out']/max(r['total_out'],1):.1f}%)")
        logger.info(f"     - Anatomy: {r['snomed_anat']}/{r['total_anat']} ({100*r['snomed_anat']/max(r['total_anat'],1):.1f}%)")

    return stats


async def fix_pathology_categories(client: Neo4jClient, dry_run: bool = False) -> dict:
    """Pathology 카테고리 정비.

    Args:
        client: Neo4j 클라이언트
        dry_run: True면 실제 변경 없이 예상 결과만 출력

    Returns:
        수정 결과 통계
    """
    logger.info("\n" + "=" * 60)
    logger.info("🦴 [3/4] Pathology 카테고리 정비")
    logger.info("=" * 60)

    stats = {"success": 0, "failed": 0, "queries": 0}

    # 수정 전 상태 확인
    uncategorized_query = """
    MATCH (p:Pathology)
    WHERE p.category IS NULL OR p.category = ''
    RETURN count(p) as uncategorized_count
    """

    result = await client.run_query(uncategorized_query, fetch_all=False)
    uncategorized_before = result[0]["uncategorized_count"] if result else 0
    logger.info(f"   카테고리 없는 Pathology 노드: {uncategorized_before}개")

    if dry_run:
        logger.info("   [DRY-RUN] 변경 사항 없음")
        return stats

    # Pathology 카테고리 수정 쿼리 실행
    queries = SpineGraphSchema.get_fix_orphan_pathologies_cypher()
    stats["queries"] = len(queries)

    for i, query in enumerate(queries, 1):
        try:
            await client.run_write_query(query)
            stats["success"] += 1
            logger.info(f"   ✅ Pathology batch {i}/{len(queries)} 적용됨")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"   ⚠️ Pathology batch {i} 실패: {e}")

    # 수정 후 상태 확인
    result = await client.run_query(uncategorized_query, fetch_all=False)
    uncategorized_after = result[0]["uncategorized_count"] if result else 0

    logger.info(f"\n   📈 결과: {uncategorized_before}개 → {uncategorized_after}개 (감소: {uncategorized_before - uncategorized_after}개)")

    return stats


async def generate_paper_embeddings(client: Neo4jClient, dry_run: bool = False) -> dict:
    """Paper Abstract 임베딩 생성.

    Args:
        client: Neo4j 클라이언트
        dry_run: True면 실제 변경 없이 예상 결과만 출력

    Returns:
        수정 결과 통계
    """
    logger.info("\n" + "=" * 60)
    logger.info("📝 [4/4] Paper Abstract 임베딩 생성")
    logger.info("=" * 60)

    stats = {"success": 0, "failed": 0, "total": 0}

    # 임베딩 없는 Paper 확인
    check_query = """
    MATCH (p:Paper)
    WHERE p.abstract IS NOT NULL AND p.abstract <> ''
      AND (p.abstract_embedding IS NULL OR size(p.abstract_embedding) = 0)
    RETURN count(p) as need_embedding
    """

    result = await client.run_query(check_query, fetch_all=False)
    need_embedding = result[0]["need_embedding"] if result else 0
    stats["total"] = need_embedding
    logger.info(f"   임베딩 필요한 Paper: {need_embedding}개")

    if need_embedding == 0:
        logger.info("   ✅ 모든 Paper에 임베딩이 있거나 abstract가 없습니다.")
        return stats

    if dry_run:
        logger.info("   [DRY-RUN] 변경 사항 없음")
        return stats

    # 임베딩 생성
    try:
        import os
        from openai import OpenAI
        import time

        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # 임베딩 없는 모든 Paper 조회
        papers_query = """
        MATCH (p:Paper)
        WHERE p.abstract IS NOT NULL AND p.abstract <> ''
          AND (p.abstract_embedding IS NULL OR size(p.abstract_embedding) = 0)
        RETURN p.paper_id as paper_id, p.abstract as abstract, p.title as title
        ORDER BY p.paper_id
        """

        papers = await client.run_query(papers_query)
        total_papers = len(papers)
        logger.info(f"   총 {total_papers}개 Paper에 임베딩 생성 시작...")

        batch_size = 20  # 배치당 처리 수
        for i, paper in enumerate(papers, 1):
            try:
                # OpenAI 임베딩 생성
                response = openai_client.embeddings.create(
                    model="text-embedding-3-large",
                    input=paper["abstract"][:8000],  # 최대 길이 제한
                    dimensions=3072
                )

                embedding = response.data[0].embedding

                # Neo4j에 임베딩 저장
                update_query = """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """

                await client.run_write_query(
                    update_query,
                    {"paper_id": paper["paper_id"], "embedding": embedding}
                )

                stats["success"] += 1

                # 진행 상황 출력 (10개마다)
                if i % 10 == 0 or i == total_papers:
                    logger.info(f"   ✅ 진행: {i}/{total_papers} ({100*i/total_papers:.1f}%)")

                # Rate limiting: 배치마다 잠시 대기
                if i % batch_size == 0 and i < total_papers:
                    time.sleep(0.5)

            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"   ⚠️ {paper['paper_id']} 실패: {e}")

        logger.info(f"\n   📈 결과: 성공 {stats['success']}개, 실패 {stats['failed']}개")

    except ImportError:
        logger.warning("   ⚠️ OpenAI 패키지가 설치되지 않았습니다. pip install openai")
        stats["failed"] = need_embedding
    except Exception as e:
        logger.error(f"   ❌ 임베딩 생성 실패: {e}")
        stats["failed"] = need_embedding

    return stats


async def main(args) -> None:
    """메인 함수."""
    logger.info("=" * 80)
    logger.info("🔧 데이터베이스 문제 수정 스크립트")
    logger.info("=" * 80)

    if args.dry_run:
        logger.info("🔍 [DRY-RUN 모드] 실제 변경 없이 예상 결과만 출력합니다.\n")

    config = Neo4jConfig.from_env()
    logger.info(f"Neo4j: {config.uri}")

    total_stats = {
        "taxonomy": {"success": 0, "failed": 0},
        "snomed": {"success": 0, "failed": 0},
        "pathology": {"success": 0, "failed": 0},
        "embeddings": {"success": 0, "failed": 0},
    }

    try:
        async with Neo4jClient(config) as client:
            # 1. Taxonomy 보강
            stats = await fix_taxonomy(client, args.dry_run)
            total_stats["taxonomy"] = stats

            # 2. SNOMED Enrichment
            stats = await fix_snomed(client, args.dry_run)
            total_stats["snomed"] = stats

            # 3. Pathology 카테고리 정비
            stats = await fix_pathology_categories(client, args.dry_run)
            total_stats["pathology"] = stats

            # 4. Paper Abstract 임베딩 생성 (선택적)
            if not args.skip_embeddings:
                stats = await generate_paper_embeddings(client, args.dry_run)
                total_stats["embeddings"] = stats
            else:
                logger.info("\n📝 [4/4] Paper Abstract 임베딩 생성 - 스킵됨 (--skip-embeddings)")

            # 최종 결과 요약
            logger.info("\n" + "=" * 80)
            logger.info("📊 최종 결과 요약")
            logger.info("=" * 80)

            for task, stats in total_stats.items():
                if stats.get("queries", 0) > 0 or stats.get("total", 0) > 0:
                    success = stats.get("success", 0)
                    failed = stats.get("failed", 0)
                    status = "✅" if failed == 0 else "⚠️"
                    logger.info(f"   {status} {task}: 성공 {success}, 실패 {failed}")

            logger.info("\n✅ 수정 완료!")

    except Exception as e:
        logger.error(f"\n❌ 수정 실패: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="데이터베이스 문제 수정 스크립트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 없이 예상 결과만 출력"
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Paper Abstract 임베딩 생성 스킵"
    )

    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("\n\n사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n오류: {e}")
        sys.exit(1)
