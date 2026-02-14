#!/usr/bin/env python3
"""Taxonomy 및 SNOMED-CT 매핑 강화 스크립트.

v1.14.13: Orphan Intervention 노드를 적절한 parent에 연결하고 SNOMED 매핑 확장.
"""

import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src/ to path for consistent imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv()

from graph.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# TAXONOMY MAPPING - Orphan → Parent 연결
# =============================================================================

TAXONOMY_MAPPINGS: dict[str, str] = {
    # === Fusion Surgery 계열 ===
    "Craniocervical Surgery": "Fusion Surgery",
    "Lumbar arthrodesis": "Fusion Surgery",
    "Single-level lumbar fusion": "Fusion Surgery",
    "Lumbosacral instrumentation": "Fusion Surgery",
    "Operative treatment (instrumented fusion assumed)": "Fusion Surgery",
    "HCS (fusion-fusion)": "Fusion Surgery",
    "HCS (fusion-mobility)": "Fusion Surgery",

    # === Decompression Surgery 계열 ===
    "Non-instrumented decompression": "Decompression Surgery",
    "ULBD (unilateral laminotomy, bilateral decompression)": "Decompression Surgery",
    "Tubular trans-isthmus oblique decompression": "Decompression Surgery",
    "LAMP": "Decompression Surgery",  # Laminoplasty
    "Laminar reconstruction": "Decompression Surgery",
    "Transoral Approach": "Decompression Surgery",

    # === Endoscopic Surgery 계열 ===
    "Delta large-channel endoscopy": "Endoscopic Surgery",
    "PTED": "Endoscopic Surgery",  # Percutaneous Transforaminal Endoscopic Discectomy
    "TETD": "Endoscopic Surgery",  # Transforaminal Endoscopic Thoracic Discectomy
    "Endoscopic thoracic diskectomy": "Endoscopic Surgery",

    # === Microsurgery 계열 ===
    "Microsurgery": "Microscopic Surgery",
    "Tubular Retraction": "Microscopic Surgery",

    # === MIS (Minimally Invasive Surgery) 계열 ===
    "MIS": "Minimally Invasive Surgery",
    "Open approach": "Open Spine Surgery",

    # === Fixation 계열 ===
    "Dynamic rod fixation": "Fixation",
    "Rigid rod fixation": "Fixation",
    "Pelvic fixation": "Fixation",
    "plate fixation": "Fixation",
    "PPS": "Fixation",  # Percutaneous Pedicle Screw
    "Cable Anchor System": "Fixation",
    "Sublaminar Tapes": "Fixation",
    "Transverse Process Hooks": "Fixation",

    # === Vertebral Augmentation 계열 ===
    # (Vertebral Augmentation이 이미 루트이므로 유지)

    # === Osteotomy 계열 ===
    "Spinal realignment surgery": "Osteotomy",
    "ACR": "Osteotomy",  # Anterior Column Resection/Reconstruction

    # === Tumor Surgery 계열 ===
    "spinal metastases surgery": "Tumor Surgery",

    # === Revision Surgery 계열 ===
    "Hardware Removal": "Revision Surgery",

    # === Motion Preservation 계열 ===
    # (Motion Preservation이 이미 루트이므로 유지)

    # === Conservative Treatment 계열 ===
    "Medication": "Conservative Treatment",
    "Denosumab": "Conservative Treatment",
    "Zoledronate": "Conservative Treatment",
    "Palliative care": "Conservative Treatment",
    "No treatment/Placebo": "Conservative Treatment",

    # === Injection/Pain Management 계열 ===
    "RFA": "Injection Therapy",  # Radiofrequency Ablation
    "Bilateral L2 medial branch restorative neurostimulation": "Injection Therapy",

    # === Regenerative Medicine 계열 ===
    # (Regenerative Medicine이 이미 루트이므로 유지)

    # === Diagnostic 계열 ===
    "Diagnostic Imaging": "Diagnosis",
    "CROM measurement": "Diagnosis",
    "Imaging assessment": "Diagnosis",
    "Microbial culture": "Diagnosis",
    "mNGS": "Diagnosis",  # metagenomic Next Generation Sequencing
    "DRS (Diffuse Reflectance Spectroscopy)": "Diagnosis",
    "Multispectral optical imaging": "Diagnosis",
    "Vertebral biopsy": "Diagnosis",

    # === AI/ML 기반 도구 (새로운 카테고리 생성) ===
    "Machine Learning": "AI/ML-Based Tools",
    "ML screening": "AI/ML-Based Tools",
    "Predictive modeling": "AI/ML-Based Tools",
    "Risk factor analysis": "AI/ML-Based Tools",
    "Radiomics": "AI/ML-Based Tools",
    "Neural tissue segmentation": "AI/ML-Based Tools",
    "Surgical instrument segmentation": "AI/ML-Based Tools",
    "SegFormer-B0": "AI/ML-Based Tools",
    "SegFormer-B1": "AI/ML-Based Tools",
    "YOLOv11x": "AI/ML-Based Tools",
    "Two-stage framework": "AI/ML-Based Tools",

    # === Digital Therapeutics (새로운 카테고리) ===
    "SaMD (Software as a Medical Device)": "Digital Therapeutics",
    "Virtual Reality (VR) devices": "Digital Therapeutics",
    "Biofeedback devices": "Digital Therapeutics",
    "EaseVRx®": "Digital Therapeutics",
    "RelieVRx®": "Digital Therapeutics",
    "VRNT®": "Digital Therapeutics",
    "Daylight®": "Digital Therapeutics",
    "Sleepio®": "Digital Therapeutics",
    "Somryst®": "Digital Therapeutics",
    "Rejoyn®": "Digital Therapeutics",
    "Freespira®": "Digital Therapeutics",
    "Canary Breathing System®": "Digital Therapeutics",
    "MamaLift Plus®": "Digital Therapeutics",
    "Endeavor®/EndeavorRx®": "Digital Therapeutics",
    "reSET®": "Digital Therapeutics",
    "reSET-O®": "Digital Therapeutics",

    # === Robotic Surgery (새로운 카테고리) ===
    "Mazor X Stealth Edition": "Robotic Surgery",

    # === Bariatric Surgery (비척추, 그룹화) ===
    "RYGB": "Bariatric Surgery",  # Roux-en-Y Gastric Bypass
    "gastric banding": "Bariatric Surgery",
    "sleeve gastrectomy": "Bariatric Surgery",

    # === Other Surgical Procedures ===
    "Drainage": "Other Surgical Procedures",
    "Puncture": "Other Surgical Procedures",
    "Continuous wound irrigation": "Other Surgical Procedures",
    "Intermittent wound irrigation": "Other Surgical Procedures",
    "prophylactic drain tubes": "Other Surgical Procedures",
    "Intravenous tranexamic acid (TXA)": "Other Surgical Procedures",
    "Closed reduction": "Other Surgical Procedures",
    "Open reduction": "Other Surgical Procedures",
    "manual reduction": "Other Surgical Procedures",
    "Monofocal surgery": "Other Surgical Procedures",
    "Bifocal surgery": "Other Surgical Procedures",
    "Open thoracic diskectomy": "Other Surgical Procedures",
    "Genetic knockout": "Other Surgical Procedures",  # 실험적

    # === Outcome Assessment (연구용) ===
    "Various (outcome measurement study)": "Outcome Assessment",
    "HPT": "Outcome Assessment",  # Hypothesis Testing?
    "OBA": "Outcome Assessment",
    "OFA": "Outcome Assessment",
    "MBS": "Outcome Assessment",
}

# 새로 생성할 카테고리 노드
NEW_CATEGORIES = {
    "AI/ML-Based Tools": {"category": "diagnostic", "description": "Artificial Intelligence and Machine Learning based diagnostic and decision support tools"},
    "Digital Therapeutics": {"category": "conservative", "description": "Software-based therapeutic interventions (DTx)"},
    "Robotic Surgery": {"category": "surgical", "description": "Robot-assisted surgical procedures"},
    "Bariatric Surgery": {"category": "other", "description": "Weight loss surgeries (non-spine)"},
    "Other Surgical Procedures": {"category": "other", "description": "Miscellaneous surgical procedures"},
    "Outcome Assessment": {"category": "research", "description": "Outcome measurement and assessment studies"},
    "Minimally Invasive Surgery": {"category": "surgical", "description": "Minimally invasive surgical approaches"},
}


# =============================================================================
# SNOMED-CT 매핑 — spine_snomed_mappings.py (Single Source of Truth) 사용
# v1.16.3: 하드코딩 ADDITIONAL_SNOMED_MAPPINGS 제거, snomed_enricher로 위임
# =============================================================================


async def enhance_taxonomy(client: Neo4jClient) -> dict:
    """Taxonomy 구조 강화."""
    stats = {"connected": 0, "categories_created": 0, "failed": 0}

    logger.info("\n" + "=" * 60)
    logger.info("1. Taxonomy 구조 강화")
    logger.info("=" * 60)

    # 1. 새 카테고리 노드 생성
    logger.info("\n[1-1] 새 카테고리 노드 생성...")
    for cat_name, props in NEW_CATEGORIES.items():
        try:
            await client.run_write_query(
                """
                MERGE (i:Intervention {name: $name})
                ON CREATE SET
                    i.category = $category,
                    i.description = $description,
                    i.created_at = datetime()
                """,
                {"name": cat_name, "category": props["category"], "description": props["description"]}
            )
            stats["categories_created"] += 1
            logger.info(f"   ✓ 생성: {cat_name}")
        except Exception as e:
            logger.warning(f"   ✗ {cat_name} 실패: {e}")

    # 2. Orphan 노드를 parent에 연결
    logger.info(f"\n[1-2] Orphan 노드 연결 ({len(TAXONOMY_MAPPINGS)}개)...")
    for child, parent in TAXONOMY_MAPPINGS.items():
        try:
            # 먼저 child 노드가 존재하는지 확인
            exists = await client.run_query(
                "MATCH (i:Intervention {name: $name}) RETURN i.name as name",
                {"name": child}
            )

            if not exists:
                continue  # 노드가 없으면 스킵

            # IS_A 관계 생성
            result = await client.run_write_query(
                """
                MATCH (child:Intervention {name: $child})
                MERGE (parent:Intervention {name: $parent})
                MERGE (child)-[r:IS_A]->(parent)
                ON CREATE SET r.level = 1, r.created_at = datetime()
                RETURN child.name as child, parent.name as parent
                """,
                {"child": child, "parent": parent}
            )

            if result:
                stats["connected"] += 1
                logger.info(f"   ✓ {child} → {parent}")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"   ✗ {child} → {parent} 실패: {e}")

    logger.info(f"\n   📊 결과: 카테고리 생성 {stats['categories_created']}개, 연결 {stats['connected']}개, 실패 {stats['failed']}개")
    return stats


async def enhance_snomed(client: Neo4jClient) -> dict:
    """SNOMED-CT 매핑 강화.

    v1.16.3: spine_snomed_mappings.py (SSoT) 기반 snomed_enricher로 위임.
    """
    from graph.snomed_enricher import update_snomed_for_entity_type
    from graph.entity_normalizer import EntityNormalizer

    logger.info("\n" + "=" * 60)
    logger.info("2. SNOMED-CT 매핑 강화 (snomed_enricher 위임)")
    logger.info("=" * 60)

    normalizer = EntityNormalizer()
    stats = {}

    for entity_type in ["intervention", "pathology", "outcome", "anatomy"]:
        result = await update_snomed_for_entity_type(
            client, entity_type, normalizer, dry_run=False
        )
        stats[entity_type] = result.newly_mapped
        logger.info(
            f"   {entity_type}: 전체 {result.total_nodes}, "
            f"기존 {result.already_mapped}, 신규 {result.newly_mapped}, "
            f"미매핑 {result.no_mapping_found}"
        )

    return stats


async def verify_results(client: Neo4jClient):
    """결과 검증."""
    logger.info("\n" + "=" * 60)
    logger.info("3. 결과 검증")
    logger.info("=" * 60)

    # Orphan 수 확인
    orphan = await client.run_query("""
        MATCH (i:Intervention)
        WHERE NOT (i)-[:IS_A]->(:Intervention)
        RETURN count(i) as count
    """)

    # SNOMED 매핑 상태
    snomed = await client.run_query("""
        MATCH (n) WHERE n:Intervention OR n:Pathology OR n:Outcome OR n:Anatomy
        WITH labels(n)[0] as label,
             count(n) as total,
             sum(CASE WHEN n.snomed_code IS NOT NULL THEN 1 ELSE 0 END) as mapped
        RETURN label, total, mapped, round(100.0 * mapped / total, 1) as percentage
        ORDER BY label
    """)

    logger.info(f"\n   Taxonomy Orphan: {orphan[0]['count']}개")
    logger.info("\n   SNOMED-CT 매핑:")
    for s in snomed:
        logger.info(f"      {s['label']}: {s['mapped']}/{s['total']} ({s['percentage']}%)")


async def main():
    """메인 실행."""
    logger.info("=" * 60)
    logger.info("Taxonomy 및 SNOMED-CT 매핑 강화 스크립트")
    logger.info("=" * 60)

    client = Neo4jClient()
    await client.connect()

    try:
        # 1. Taxonomy 강화
        tax_stats = await enhance_taxonomy(client)

        # 2. SNOMED 강화
        snomed_stats = await enhance_snomed(client)

        # 3. 결과 검증
        await verify_results(client)

        logger.info("\n" + "=" * 60)
        logger.info("완료!")
        logger.info("=" * 60)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
