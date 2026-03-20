"""IS_A 계층 확장 스크립트 — 43% → 80%+ 커버리지.

Step 1: IS_A 없는 orphan entity 추출
Step 2: LLM으로 parent 매핑 생성 (dry-run)
Step 3: 검수 후 IS_A 관계 생성

Usage:
    PYTHONPATH=./src python3 scripts/fix_isa_hierarchy.py --step 1  # orphan 추출
    PYTHONPATH=./src python3 scripts/fix_isa_hierarchy.py --step 2  # parent 매핑 생성
    PYTHONPATH=./src python3 scripts/fix_isa_hierarchy.py --step 3  # IS_A 생성
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


async def step1_extract_orphans():
    """Step 1: IS_A 없는 orphan entity 추출."""
    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    orphans = {}
    for label in ["Intervention", "Pathology", "Anatomy"]:
        rows = await neo4j.run_query(f"""
            MATCH (n:{label})
            WHERE NOT (n)-[:IS_A]->()
            RETURN n.name AS name, size([(n)<-[:INVESTIGATES|STUDIES]-() | 1]) AS paper_count
            ORDER BY paper_count DESC
        """)
        orphans[label] = [{"name": r["name"], "papers": r["paper_count"]} for r in rows]
        logger.info(f"{label}: {len(orphans[label])} orphans")

    output_path = Path("data/isa_orphans.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(orphans, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved → {output_path}")

    # 기존 IS_A parent 목록도 추출 (매핑 시 참조)
    existing_parents = {}
    for label in ["Intervention", "Pathology", "Anatomy"]:
        rows = await neo4j.run_query(f"""
            MATCH (child:{label})-[:IS_A]->(parent:{label})
            RETURN DISTINCT parent.name AS parent, count(child) AS children
            ORDER BY children DESC
        """)
        existing_parents[label] = [{"name": r["parent"], "children": r["children"]} for r in rows]

    with open("data/isa_existing_parents.json", "w") as f:
        json.dump(existing_parents, f, indent=2, ensure_ascii=False)

    logger.info(f"Existing parents saved → data/isa_existing_parents.json")
    await neo4j.__aexit__(None, None, None)


async def step2_generate_parent_mapping():
    """Step 2: Rule-based + LLM으로 parent 매핑 생성."""
    if not Path("data/isa_orphans.json").exists():
        logger.error("data/isa_orphans.json 없음. step 1 먼저 실행하세요.")
        return

    with open("data/isa_orphans.json") as f:
        orphans = json.load(f)

    # Rule-based intervention parent 매핑
    int_rules = {
        "esi": "Injection Therapy",
        "epidural": "Injection Therapy",
        "steroid injection": "Injection Therapy",
        "nerve block": "Injection Therapy",
        "rhbmp": "Bone Graft Substitute",
        "bmp": "Bone Graft Substitute",
        "bone graft": "Bone Graft Substitute",
        "stem cell": "Regenerative Therapy",
        "msc": "Regenerative Therapy",
        "platelet": "Regenerative Therapy",
        "mri": "Diagnostic Imaging",
        "x-ray": "Diagnostic Imaging",
        "ct": "Diagnostic Imaging",
        "navigation": "Computer-Assisted Surgery",
        "augmented reality": "Computer-Assisted Surgery",
        "robotic": "Computer-Assisted Surgery",
        "robot": "Computer-Assisted Surgery",
        "machine learning": "AI/ML Application",
        "deep learning": "AI/ML Application",
        "pedicle screw": "Spinal Instrumentation",
        "fixation": "Spinal Instrumentation",
        "instrumentation": "Spinal Instrumentation",
        "cage": "Interbody Device",
        "exercise": "Conservative Treatment",
        "physical therapy": "Conservative Treatment",
        "rehabilitation": "Conservative Treatment",
        "brace": "Conservative Treatment",
        "stereotactic": "Radiation Therapy",
        "radiation": "Radiation Therapy",
        "chemotherapy": "Systemic Therapy",
        "denosumab": "Systemic Therapy",
        "embolization": "Endovascular Procedure",
    }

    parent_map = {"Intervention": {}, "Pathology": {}, "Anatomy": {}}

    for o in orphans.get("Intervention", []):
        name = o["name"]
        lower = name.lower()
        for pattern, parent in int_rules.items():
            if pattern in lower:
                parent_map["Intervention"][name] = parent
                break

    output_path = Path("data/isa_parent_map.json")
    with open(output_path, "w") as f:
        json.dump(parent_map, f, indent=2, ensure_ascii=False)

    mapped = sum(len(v) for v in parent_map.values())
    total = sum(len(v) for v in orphans.values())
    logger.info(f"Rule-based mapping: {mapped}/{total}")
    logger.info(f"Intervention mapped: {len(parent_map['Intervention'])}/{len(orphans.get('Intervention', []))}")
    logger.info(f"")
    logger.info(f"다음: Claude Code Agent로 나머지 매핑 생성, 또는 교수님 검수 후 step 3")


async def step3_create_isa():
    """Step 3: parent 매핑에 따라 IS_A 관계 생성."""
    if not Path("data/isa_parent_map.json").exists():
        logger.error("data/isa_parent_map.json 없음. step 2 먼저 실행하세요.")
        return

    with open("data/isa_parent_map.json") as f:
        parent_map = json.load(f)

    from graph.neo4j_client import Neo4jClient, Neo4jConfig

    config = Neo4jConfig.from_env()
    neo4j = Neo4jClient(config)
    await neo4j.__aenter__()

    created = 0
    errors = 0

    for label, mappings in parent_map.items():
        for child_name, parent_name in mappings.items():
            try:
                await neo4j.run_write_query(f"""
                    MERGE (parent:{label} {{name: $parent}})
                    WITH parent
                    MATCH (child:{label} {{name: $child}})
                    MERGE (child)-[:IS_A]->(parent)
                """, {"parent": parent_name, "child": child_name})
                created += 1
            except Exception as e:
                logger.warning(f"IS_A failed for {child_name} → {parent_name}: {e}")
                errors += 1

    logger.info(f"Created: {created} IS_A relations, Errors: {errors}")

    # 결과 확인
    for label in ["Intervention", "Pathology", "Anatomy"]:
        total = await neo4j.run_query(f"MATCH (n:{label}) RETURN count(n) as c")
        has_isa = await neo4j.run_query(f"MATCH (n:{label})-[:IS_A]->() RETURN count(DISTINCT n) as c")
        pct = has_isa[0]["c"] / total[0]["c"] * 100
        logger.info(f"{label}: {has_isa[0]['c']}/{total[0]['c']} ({pct:.0f}%) have IS_A")

    await neo4j.__aexit__(None, None, None)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()

    if args.step == 1:
        await step1_extract_orphans()
    elif args.step == 2:
        await step2_generate_parent_mapping()
    elif args.step == 3:
        await step3_create_isa()


if __name__ == "__main__":
    asyncio.run(main())
