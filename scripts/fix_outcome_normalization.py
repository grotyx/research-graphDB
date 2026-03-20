"""Outcome 정규화 스크립트 — 3,565개 → ~400개로 병합.

Step 1: 현재 Outcome 목록 추출
Step 2: LLM으로 canonical 매핑 생성 (dry-run)
Step 3: 사용자 검수 후 병합 실행

Usage:
    PYTHONPATH=./src python3 scripts/fix_outcome_normalization.py --step 1  # 목록 추출
    PYTHONPATH=./src python3 scripts/fix_outcome_normalization.py --step 2  # 매핑 생성 (dry-run)
    PYTHONPATH=./src python3 scripts/fix_outcome_normalization.py --step 3  # 병합 실행
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def step1_extract_outcomes():
    """Step 1: 현재 Outcome 목록 추출."""
    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    rows = await neo4j.run_query("""
        MATCH (o:Outcome)
        OPTIONAL MATCH (o)<-[r:AFFECTS]-()
        RETURN o.name AS name, count(r) AS affects_count, o.snomed_code AS snomed
        ORDER BY affects_count DESC
    """)

    outcomes = [{"name": r["name"], "count": r["affects_count"], "snomed": r.get("snomed")} for r in rows]

    output_path = Path("data/outcome_list.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(outcomes, f, indent=2, ensure_ascii=False)

    logger.info(f"Extracted {len(outcomes)} outcomes → {output_path}")
    logger.info(f"Top 10: {[o['name'] for o in outcomes[:10]]}")
    logger.info(f"1편 이하: {sum(1 for o in outcomes if o['count'] <= 1)}")

    await neo4j.__aexit__(None, None, None)


async def step2_generate_mapping():
    """Step 2: LLM으로 canonical 매핑 생성.

    이 단계는 Claude Code에서 Agent로 실행하는 것이 좋습니다.
    data/outcome_list.json → data/outcome_canonical_map.json
    """
    if not Path("data/outcome_list.json").exists():
        logger.error("data/outcome_list.json 없음. step 1 먼저 실행하세요.")
        return

    with open("data/outcome_list.json") as f:
        outcomes = json.load(f)

    # 병합 규칙 (rule-based — LLM 보완 전)
    canonical_map = {}
    rules = {
        # VAS variants → VAS
        "vas back": "VAS Back",
        "vas leg": "VAS Leg",
        "vas neck": "VAS Neck",
        "vas arm": "VAS Arm",
        "visual analog": "VAS",
        # ODI variants
        "oswestry": "ODI",
        # Fusion variants
        "fusion rate": "Fusion Rate",
        "bony union": "Fusion Rate",
        "solid fusion": "Fusion Rate",
        "pseudarthrosis": "Pseudarthrosis Rate",
        # ROM variants
        "range of motion": "ROM",
        "rom -": "ROM",
        "crom": "Cervical ROM",
        # Complication variants
        "complication rate": "Complication Rate",
        "overall complication": "Complication Rate",
        "adverse event": "Complication Rate",
        # Common measures
        "blood loss": "Blood Loss",
        "operative time": "Operative Time",
        "operation time": "Operative Time",
        "hospital stay": "Hospital Stay",
        "length of stay": "Hospital Stay",
        "reoperation": "Reoperation Rate",
        "revision": "Revision Rate",
        # Study-specific → remove
        "auc -": "_REMOVE",
        "auroc -": "_REMOVE",
        "ml accuracy": "_REMOVE",
        "mean absolute error": "_REMOVE",
        "xp-bodypart": "_REMOVE",
        "cxp-projection": "_REMOVE",
    }

    merged = 0
    removed = 0
    for o in outcomes:
        name = o["name"]
        lower = name.lower()
        matched = False
        for pattern, canonical in rules.items():
            if pattern in lower and name != canonical:
                if canonical == "_REMOVE":
                    canonical_map[name] = "_REMOVE"
                    removed += 1
                else:
                    canonical_map[name] = canonical
                    merged += 1
                matched = True
                break

    output_path = Path("data/outcome_canonical_map.json")
    with open(output_path, "w") as f:
        json.dump(canonical_map, f, indent=2, ensure_ascii=False)

    logger.info(f"Rule-based mapping: {merged} merges, {removed} removals → {output_path}")
    logger.info(f"남은 Outcome: {len(outcomes) - merged - removed} (LLM 추가 매핑 필요)")
    logger.info(f"")
    logger.info(f"다음 단계: Claude Code Agent로 나머지 매핑 생성")
    logger.info(f"  또는 교수님이 data/outcome_canonical_map.json 검수 후 step 3 실행")


async def step3_merge_outcomes():
    """Step 3: canonical 매핑에 따라 Neo4j에서 Outcome 병합."""
    if not Path("data/outcome_canonical_map.json").exists():
        logger.error("data/outcome_canonical_map.json 없음. step 2 먼저 실행하세요.")
        return

    with open("data/outcome_canonical_map.json") as f:
        canonical_map = json.load(f)

    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    merged = 0
    removed = 0
    errors = 0

    for old_name, canonical in canonical_map.items():
        if canonical == "_REMOVE":
            # 고아 Outcome 삭제
            try:
                await neo4j.run_write_query(
                    "MATCH (o:Outcome {name: $name}) DETACH DELETE o",
                    {"name": old_name},
                )
                removed += 1
            except Exception as e:
                logger.warning(f"Delete failed for {old_name}: {e}")
                errors += 1
        else:
            # 관계 이전 + 기존 노드 삭제
            try:
                # 1. canonical 노드 생성 (없으면)
                await neo4j.run_write_query(
                    "MERGE (o:Outcome {name: $name})",
                    {"name": canonical},
                )
                # 2. AFFECTS 관계 이전
                await neo4j.run_write_query("""
                    MATCH (old:Outcome {name: $old_name})<-[r:AFFECTS]-(i:Intervention)
                    MATCH (new:Outcome {name: $new_name})
                    MERGE (i)-[:AFFECTS]->(new)
                """, {"old_name": old_name, "new_name": canonical})
                # 3. IS_A 관계 이전
                await neo4j.run_write_query("""
                    MATCH (old:Outcome {name: $old_name})-[r:IS_A]->(parent)
                    MATCH (new:Outcome {name: $new_name})
                    MERGE (new)-[:IS_A]->(parent)
                """, {"old_name": old_name, "new_name": canonical})
                # 4. 기존 노드 삭제
                await neo4j.run_write_query(
                    "MATCH (o:Outcome {name: $name}) DETACH DELETE o",
                    {"name": old_name},
                )
                merged += 1
            except Exception as e:
                logger.warning(f"Merge failed for {old_name} → {canonical}: {e}")
                errors += 1

    logger.info(f"Merged: {merged}, Removed: {removed}, Errors: {errors}")

    # 결과 확인
    count = await neo4j.run_query("MATCH (o:Outcome) RETURN count(o) as c")
    logger.info(f"Outcome 노드 수: {count[0]['c']}")

    await neo4j.__aexit__(None, None, None)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()

    if args.step == 1:
        await step1_extract_outcomes()
    elif args.step == 2:
        await step2_generate_mapping()
    elif args.step == 3:
        await step3_merge_outcomes()


if __name__ == "__main__":
    asyncio.run(main())
