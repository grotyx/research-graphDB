#!/usr/bin/env python3
"""Entity 통합 스크립트 -- 미매핑 노드를 LLM 분류로 정리.

SNOMED 코드 없고 참조 빈도 낮은 노드를 LLM(Claude Haiku)으로 분류하여
기존 canonical 노드에 병합하거나, 신규 개념으로 유지합니다.

Usage:
    # 전체 dry-run (변경 없이 보고만)
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --dry-run

    # Outcome만 실행
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --entity-type outcome --dry-run

    # 실행 (실제 노드 병합)
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --force

    # Alias 코드 제안 생성
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --suggest-aliases --dry-run
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# .env 로드
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from graph.neo4j_client import Neo4jClient
from graph.entity_normalizer import EntityNormalizer

from graph.relationship_builder import classify_unmatched_entity

from llm import ClaudeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("consolidate_entities")


# ─────────────────────────────────────────────────────────────────────
# Neo4j 조회
# ─────────────────────────────────────────────────────────────────────

async def find_unmapped_nodes(
    client: Neo4jClient,
    label: str,
    max_refs: int = 5,
) -> list[dict]:
    """SNOMED 없고 빈도 낮은 노드 조회.

    Args:
        client: Neo4jClient 인스턴스
        label: 노드 라벨 ("Outcome" | "Intervention" | "Pathology")
        max_refs: 연결 수 상한 (빈도 낮은 것만 대상)

    Returns:
        [{"name": str, "ref_count": int}]
    """
    query = f"""
    MATCH (n:{label})
    WHERE n.snomed_code IS NULL
    OPTIONAL MATCH (n)<-[r]-()
    WITH n, count(r) AS ref_count
    WHERE ref_count <= $max_refs
    RETURN n.name AS name, ref_count
    ORDER BY ref_count ASC
    LIMIT 500
    """
    return await client.run_query(query, {"max_refs": max_refs})


# ─────────────────────────────────────────────────────────────────────
# LLM 배치 분류
# ─────────────────────────────────────────────────────────────────────

async def batch_classify(
    nodes: list[dict],
    entity_type: str,
    normalizer: EntityNormalizer,
    llm_client,
    batch_size: int = 5,
) -> list[dict]:
    """미매핑 노드를 배치로 LLM 분류.

    asyncio.gather로 배치 내 동시 처리하여 속도 최적화.

    Args:
        nodes: find_unmapped_nodes() 결과
        entity_type: "intervention" | "outcome" | "pathology"
        normalizer: EntityNormalizer 인스턴스
        llm_client: ClaudeClient 인스턴스
        batch_size: 동시 처리 수

    Returns:
        [{"name": str, "action": "merge"|"new"|"skip",
          "canonical": str|None, "confidence": float}]
    """
    results = []
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]
        tasks = []
        for node in batch:
            candidates = normalizer._get_candidate_canonicals(
                node["name"], entity_type, top_k=30
            )
            tasks.append(classify_unmatched_entity(
                entity_text=node["name"],
                entity_type=entity_type,
                candidates=candidates,
                llm_client=llm_client,
            ))

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for node, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.warning(f"Classification error for '{node['name']}': {result}")
                results.append({
                    "name": node["name"],
                    "action": "skip",
                    "canonical": None,
                    "confidence": 0.0,
                })
            elif result:
                canonical, confidence = result
                results.append({
                    "name": node["name"],
                    "action": "merge",
                    "canonical": canonical,
                    "confidence": confidence,
                })
            else:
                results.append({
                    "name": node["name"],
                    "action": "new",
                    "canonical": None,
                    "confidence": 0.0,
                })

        # 진행 상황 로깅
        processed = min(i + batch_size, len(nodes))
        logger.info(f"  Classified {processed}/{len(nodes)} nodes...")

    return results


# ─────────────────────────────────────────────────────────────────────
# 노드 병합
# ─────────────────────────────────────────────────────────────────────

# 라벨별 관계 타입 매핑 (APOC 미사용 -- 명시적 관계 이전)
_REL_CONFIG = {
    "Outcome": {
        "incoming": [("AFFECTS", "Intervention")],
        "outgoing": [("MEASURED_BY", "OutcomeMeasure")],
    },
    "Pathology": {
        "incoming": [("STUDIES", "Paper"), ("TREATS", "Intervention")],
        "outgoing": [("LOCATED_AT", "Anatomy")],
    },
    "Intervention": {
        "incoming": [("INVESTIGATES", "Paper")],
        "outgoing": [
            ("TREATS", "Pathology"),
            ("AFFECTS", "Outcome"),
            ("IS_A", "Intervention"),
            ("USES_DEVICE", "Implant"),
            ("CAUSES", "Complication"),
        ],
    },
}


async def merge_node(
    client: Neo4jClient,
    label: str,
    old_name: str,
    canonical_name: str,
    dry_run: bool = True,
) -> bool:
    """old_name 노드의 모든 관계를 canonical_name 노드로 이전 후 삭제.

    APOC 미사용 -- 관계 타입별 명시적 처리.

    Args:
        client: Neo4jClient 인스턴스
        label: 노드 라벨
        old_name: 병합 대상 (삭제될) 노드 이름
        canonical_name: 병합 목표 (유지될) canonical 노드 이름
        dry_run: True면 관계 수만 보고, 실제 변경 없음

    Returns:
        True if merge succeeded (or dry_run report done)
    """
    if dry_run:
        query = f"""
        MATCH (old:{label} {{name: $old_name}})
        OPTIONAL MATCH (old)-[r]-()
        RETURN count(r) AS rel_count
        """
        result = await client.run_query(query, {"old_name": old_name})
        rel_count = result[0]["rel_count"] if result else 0
        logger.info(f"    [DRY RUN] '{old_name}' -> '{canonical_name}' ({rel_count} relationships)")
        return rel_count > 0

    # 실제 병합: 모든 incoming/outgoing 관계 이전
    config = _REL_CONFIG.get(label, {})

    for rel_type, _other_label in config.get("incoming", []):
        await client.run_write_query(f"""
            MATCH (source)-[r:{rel_type}]->(old:{label} {{name: $old_name}})
            MATCH (canonical:{label} {{name: $canonical_name}})
            WHERE NOT (source)-[:{rel_type}]->(canonical)
            CREATE (source)-[nr:{rel_type}]->(canonical)
            SET nr = properties(r)
            DELETE r
        """, {"old_name": old_name, "canonical_name": canonical_name})

    for rel_type, _other_label in config.get("outgoing", []):
        await client.run_write_query(f"""
            MATCH (old:{label} {{name: $old_name}})-[r:{rel_type}]->(target)
            MATCH (canonical:{label} {{name: $canonical_name}})
            WHERE NOT (canonical)-[:{rel_type}]->(target)
            CREATE (canonical)-[nr:{rel_type}]->(target)
            SET nr = properties(r)
            DELETE r
        """, {"old_name": old_name, "canonical_name": canonical_name})

    # 남은 관계 삭제 + 노드 삭제
    await client.run_write_query(f"""
        MATCH (old:{label} {{name: $old_name}})
        DETACH DELETE old
    """, {"old_name": old_name})

    logger.info(f"    Merged '{old_name}' -> '{canonical_name}'")
    return True


# ─────────────────────────────────────────────────────────────────────
# Alias 코드 제안 생성
# ─────────────────────────────────────────────────────────────────────

def generate_alias_suggestions(
    classified: list[dict],
    entity_type: str,
) -> str:
    """분류 결과를 entity_normalizer.py에 추가할 코드 스니펫으로 변환.

    병합 대상으로 분류된 항목들을 canonical별로 그룹화하여
    복사-붙여넣기 가능한 Python 코드 문자열을 생성합니다.

    Args:
        classified: batch_classify() 결과
        entity_type: "intervention" | "outcome" | "pathology"

    Returns:
        복사-붙여넣기 가능한 Python 코드 문자열
    """
    merge_items = [c for c in classified if c["action"] == "merge"]
    if not merge_items:
        return f"# No merge candidates for {entity_type.upper()}_ALIASES"

    # canonical별 그룹화
    by_canonical: dict[str, list[str]] = {}
    for item in merge_items:
        by_canonical.setdefault(item["canonical"], []).append(item["name"])

    lines = [
        f"# Auto-suggested aliases for {entity_type.upper()}_ALIASES",
        f"# Generated by consolidate_entities.py",
        f"# Review each suggestion before adding to entity_normalizer.py",
        "",
    ]

    for canonical, aliases in sorted(by_canonical.items()):
        lines.append(f'"{canonical}": [')
        lines.append(f'    ...,  # existing aliases')
        for alias in sorted(aliases):
            lines.append(f'    "{alias}",  # NEW (auto-classified)')
        lines.append('],')

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# CLI 메인
# ─────────────────────────────────────────────────────────────────────

LABEL_MAP = {
    "outcome": "Outcome",
    "intervention": "Intervention",
    "pathology": "Pathology",
}


async def main():
    parser = argparse.ArgumentParser(
        description="Entity Consolidation - unmapped node cleanup via LLM classification"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only, no actual changes to Neo4j",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Actually merge nodes in Neo4j",
    )
    parser.add_argument(
        "--entity-type",
        choices=["outcome", "intervention", "pathology"],
        help="Process only this entity type (default: all three)",
    )
    parser.add_argument(
        "--suggest-aliases", action="store_true",
        help="Generate Python code snippets for permanent aliases",
    )
    parser.add_argument(
        "--max-refs", type=int, default=5,
        help="Max reference count threshold for unmapped nodes (default: 5)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5,
        help="Concurrent LLM classification batch size (default: 5)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.force:
        print("Error: specify --dry-run or --force")
        print("  --dry-run  Report without changes")
        print("  --force    Actually merge nodes")
        sys.exit(1)

    # 초기화
    logger.info("=" * 60)
    logger.info("Entity Consolidation Script")
    logger.info(f"  mode={'DRY RUN' if args.dry_run else 'FORCE (live merge)'}")
    logger.info(f"  max_refs={args.max_refs}, batch_size={args.batch_size}")
    logger.info("=" * 60)

    neo4j_client = Neo4jClient()
    await neo4j_client.connect()
    normalizer = EntityNormalizer()
    llm_client = ClaudeClient()

    entity_types = (
        [args.entity_type] if args.entity_type
        else ["outcome", "intervention", "pathology"]
    )

    start_time = time.time()
    total_merged = 0
    total_new = 0
    total_skipped = 0

    try:
        for entity_type in entity_types:
            label = LABEL_MAP[entity_type]
            print(f"\n{'=' * 60}")
            print(f"Processing {label}")
            print(f"{'=' * 60}")

            # 1. 미매핑 노드 조회
            nodes = await find_unmapped_nodes(neo4j_client, label, args.max_refs)
            print(f"Found {len(nodes)} unmapped {label} nodes (snomed_code IS NULL, refs <= {args.max_refs})")

            if not nodes:
                print(f"  No unmapped nodes. Skipping.")
                continue

            # 2. LLM 배치 분류
            classified = await batch_classify(
                nodes, entity_type, normalizer, llm_client, args.batch_size
            )

            merge_count = sum(1 for c in classified if c["action"] == "merge")
            new_count = sum(1 for c in classified if c["action"] == "new")
            skip_count = sum(1 for c in classified if c["action"] == "skip")

            print(f"  Merge candidates: {merge_count}")
            print(f"  Genuinely new:    {new_count}")
            print(f"  Skipped/errors:   {skip_count}")

            # 3. 병합 실행 (또는 dry-run 보고)
            for item in classified:
                if item["action"] == "merge":
                    await merge_node(
                        neo4j_client,
                        label,
                        item["name"],
                        item["canonical"],
                        dry_run=args.dry_run,
                    )

            if not args.dry_run:
                print(f"  Merged: {merge_count} nodes")

            total_merged += merge_count
            total_new += new_count
            total_skipped += skip_count

            # 4. Alias 코드 제안
            if args.suggest_aliases:
                suggestions = generate_alias_suggestions(classified, entity_type)
                print(f"\n--- Alias Suggestions ({entity_type}) ---")
                print(suggestions)
                print("--- End Suggestions ---\n")

    finally:
        await neo4j_client.close()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print("CONSOLIDATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total merged:  {total_merged}")
    print(f"  Total new:     {total_new}")
    print(f"  Total skipped: {total_skipped}")
    print(f"  Elapsed:       {elapsed:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
