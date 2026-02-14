#!/usr/bin/env python3
"""Neo4j SNOMED-CT 통합 보강 스크립트.

spine_snomed_mappings.py (Single Source of Truth) 기반으로
Intervention, Pathology, Outcome, Anatomy 노드에 SNOMED 코드 적용,
TREATS 관계 백필, Anatomy 데이터 정리를 수행합니다.

Usage:
    # 전체 파이프라인 (dry-run)
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --dry-run

    # 전체 파이프라인 (실행)
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --force

    # 개별 단계
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py snomed --dry-run
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py treats --dry-run
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py anatomy-cleanup --dry-run
    PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py report

v1.16.3: update_snomed_codes.py + enhance_taxonomy_snomed.py 통합 대체.
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from graph.neo4j_client import Neo4jClient
from graph.entity_normalizer import EntityNormalizer
from graph.snomed_enricher import (
    ENTITY_TYPE_CONFIG,
    update_snomed_for_entity_type,
    backfill_treats_relations,
    cleanup_anatomy_nodes,
    generate_coverage_report,
)

logger = logging.getLogger(__name__)


def setup_logging(quiet: bool = False):
    """로깅 설정."""
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_separator(title: str):
    """구분선 출력."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def run_snomed(dry_run: bool = False):
    """SNOMED 코드 업데이트 (4개 엔티티 타입)."""
    print_separator("SNOMED-CT 코드 업데이트")
    normalizer = EntityNormalizer()

    async with Neo4jClient() as client:
        for entity_type in ["intervention", "pathology", "outcome", "anatomy"]:
            label = ENTITY_TYPE_CONFIG[entity_type][0]
            result = await update_snomed_for_entity_type(
                client, entity_type, normalizer, dry_run
            )

            prefix = "[DRY-RUN] " if dry_run else ""
            print(f"\n  {prefix}{label}:")
            print(f"    전체: {result.total_nodes}")
            print(f"    기존 매핑: {result.already_mapped}")
            print(f"    신규 매핑: {result.newly_mapped}")
            print(f"    매핑 불가: {result.no_mapping_found}")

            if result.unmapped_names and len(result.unmapped_names) <= 20:
                print(f"    매핑 불가 목록:")
                for name in result.unmapped_names[:20]:
                    print(f"      - {name}")


async def run_treats(dry_run: bool = False):
    """TREATS 관계 백필."""
    print_separator("TREATS 관계 백필")

    async with Neo4jClient() as client:
        result = await backfill_treats_relations(client, dry_run)

        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"\n  {prefix}결과:")
        print(f"    전체 I→P 쌍: {result.total_pairs}")
        print(f"    신규 생성: {result.newly_created}")
        print(f"    기존 유지: {result.already_existed}")
        print(f"    제외 리뷰논문: {result.excluded_review_papers}")

        if result.top_pairs:
            print(f"\n    Top {len(result.top_pairs)} 쌍 (근거 수 기준):")
            for intervention, pathology, evidence in result.top_pairs:
                print(f"      {intervention} → {pathology} ({evidence} papers)")


async def run_anatomy_cleanup(dry_run: bool = False):
    """Anatomy 데이터 정리."""
    print_separator("Anatomy 데이터 정리")
    normalizer = EntityNormalizer()

    async with Neo4jClient() as client:
        result = await cleanup_anatomy_nodes(client, normalizer, dry_run)

        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"\n  {prefix}결과:")
        print(f"    전체 Anatomy: {result.total_anatomy}")
        print(f"    비특이적 플래그: {result.flagged_non_specific}")
        print(f"    방향어 플래그: {result.flagged_direction_only}")
        print(f"    복합 분리: {result.split_compound}")
        print(f"    범위 분리: {result.split_range}")
        print(f"    SNOMED 적용: {result.normalized}")
        print(f"    정상/기존: {result.already_clean}")

        if result.segments_created:
            unique_segs = sorted(set(result.segments_created))
            print(f"\n    생성된 분절 ({len(unique_segs)}개):")
            for seg in unique_segs[:30]:
                print(f"      - {seg}")


async def run_report():
    """커버리지 리포트."""
    print_separator("SNOMED 커버리지 리포트")

    async with Neo4jClient() as client:
        report = await generate_coverage_report(client)

        print(f"\n  {'타입':<15} {'전체':>6} {'매핑':>6} {'미매핑':>6} {'커버리지':>8} {'가용 매핑':>8}")
        print(f"  {'-'*55}")

        for entity_type in ["intervention", "pathology", "outcome", "anatomy"]:
            r = report[entity_type]
            print(
                f"  {r['label']:<15} {r['total']:>6} {r['mapped']:>6} "
                f"{r['unmapped']:>6} {r['coverage_pct']:>7.1f}% {r['available_mappings']:>8}"
            )

        print(f"\n  TREATS 관계: {report['treats_count']}")

        if report["anatomy_flags"]:
            print(f"\n  Anatomy 품질 플래그:")
            for flag, cnt in report["anatomy_flags"].items():
                print(f"    {flag}: {cnt}")


async def run_full_pipeline(dry_run: bool = False):
    """전체 파이프라인: anatomy-cleanup → snomed → treats → report."""
    await run_anatomy_cleanup(dry_run)
    await run_snomed(dry_run)
    await run_treats(dry_run)
    await run_report()


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(
        description="Neo4j SNOMED-CT 통합 보강 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "snomed", "treats", "anatomy-cleanup", "report"],
        help="실행할 명령 (기본: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 미리보기")
    parser.add_argument("--force", "-f", action="store_true", help="확인 없이 실행")
    parser.add_argument("--quiet", "-q", action="store_true", help="최소 출력")

    args = parser.parse_args()
    setup_logging(args.quiet)

    dry_run = args.dry_run

    # 확인 프롬프트
    if not dry_run and not args.force and args.command != "report":
        print(f"명령: {args.command}")
        print("Neo4j 데이터를 수정합니다. 계속하시겠습니까? [y/N] ", end="")
        confirm = input().strip().lower()
        if confirm != "y":
            print("취소됨.")
            return

    command_map = {
        "all": lambda: run_full_pipeline(dry_run),
        "snomed": lambda: run_snomed(dry_run),
        "treats": lambda: run_treats(dry_run),
        "anatomy-cleanup": lambda: run_anatomy_cleanup(dry_run),
        "report": run_report,
    }

    try:
        asyncio.run(command_map[args.command]())
        print(f"\n{'=' * 60}")
        print("  완료!")
        print(f"{'=' * 60}")
    except KeyboardInterrupt:
        print("\n\n중단됨.")
        sys.exit(1)
    except Exception as e:
        error_msg = str(e)
        if "ServiceUnavailable" in error_msg or "Connection" in error_msg:
            print(f"\n❌ Neo4j 연결 실패: {error_msg}")
            print("\n문제 해결:")
            print("  1. Neo4j가 실행 중인지 확인: docker-compose ps")
            print("  2. .env 파일의 NEO4J_URI, NEO4J_PASSWORD 확인")
            print("  3. bolt://localhost:7687 접속 가능한지 확인")
        elif "Auth" in error_msg:
            print(f"\n❌ Neo4j 인증 실패: {error_msg}")
            print("\n문제 해결: .env 파일의 NEO4J_USERNAME, NEO4J_PASSWORD 확인")
        else:
            print(f"\n❌ 오류 발생: {error_msg}")
            logger.exception("상세 오류")
        sys.exit(1)


if __name__ == "__main__":
    main()
