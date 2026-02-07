#!/usr/bin/env python3
"""Classify unclassified papers by sub_domain and study_design.

제목과 초록을 기반으로 sub_domain과 study_design을 자동 분류합니다.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sub-domain 분류 키워드
SUB_DOMAIN_KEYWORDS = {
    "Degenerative": [
        "disc herniation", "stenosis", "spondylolisthesis", "degenerative",
        "disc disease", "radiculopathy", "myelopathy", "sciatica",
        "discectomy", "decompression", "laminectomy", "fusion",
        "interbody", "ACDF", "TLIF", "PLIF", "ALIF", "LLIF", "OLIF",
        "UBE", "endoscopic", "minimally invasive", "MIS",
        "lumbar", "cervical", "thoracic", "spine surgery"
    ],
    "Deformity": [
        "scoliosis", "kyphosis", "deformity", "curvature",
        "sagittal", "coronal", "spinal alignment", "adult spinal deformity",
        "ASD", "adolescent idiopathic", "congenital"
    ],
    "Trauma": [
        "fracture", "trauma", "burst", "compression fracture",
        "vertebral fracture", "dislocation", "instability",
        "spinal cord injury", "SCI", "traumatic"
    ],
    "Tumor": [
        "tumor", "tumour", "metastatic", "metastasis", "cancer",
        "oncologic", "malignant", "neoplasm", "spinal tumor",
        "vertebral tumor", "intradural"
    ],
    "Infection": [
        "infection", "spondylodiscitis", "osteomyelitis", "abscess",
        "pyogenic", "tuberculous", "septic", "discitis"
    ],
    "Basic Science": [
        "biomechanical", "cadaveric", "in vitro", "cell",
        "molecular", "tissue engineering", "stem cell",
        "deep learning", "machine learning", "artificial intelligence",
        "segmentation", "imaging", "MRI", "CT scan"
    ]
}

# Study design 분류 키워드
STUDY_DESIGN_KEYWORDS = {
    "meta_analysis": [
        "meta-analysis", "meta analysis", "systematic review and meta",
        "pooled analysis", "bayesian meta"
    ],
    "systematic_review": [
        "systematic review", "literature review", "scoping review"
    ],
    "randomized": [
        "randomized", "randomised", "RCT", "controlled trial",
        "prospective randomized", "double-blind", "single-blind"
    ],
    "cohort": [
        "cohort", "prospective study", "longitudinal", "follow-up study"
    ],
    "case_control": [
        "case-control", "case control", "matched"
    ],
    "retrospective": [
        "retrospective", "chart review", "medical record"
    ],
    "case_series": [
        "case series", "case report", "single case"
    ],
    "cross_sectional": [
        "cross-sectional", "cross sectional", "survey"
    ]
}


def classify_sub_domain(title: str, abstract: str) -> Optional[str]:
    """제목과 초록으로 sub_domain 분류."""
    text = f"{title} {abstract}".lower()

    scores = {}
    for domain, keywords in SUB_DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[domain] = score

    if not scores:
        return None

    # 가장 높은 점수의 domain 반환
    return max(scores, key=scores.get)


def classify_study_design(title: str, abstract: str) -> Optional[str]:
    """제목과 초록으로 study_design 분류."""
    text = f"{title} {abstract}".lower()

    # 우선순위대로 체크
    for design, keywords in STUDY_DESIGN_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return design

    return None


async def get_unclassified_papers(client: Neo4jClient) -> list:
    """분류되지 않은 논문 조회."""
    query = """
    MATCH (p:Paper)
    WHERE p.sub_domain IS NULL OR p.sub_domain = '' OR p.sub_domain = 'Unknown'
       OR p.study_design IS NULL OR p.study_design = ''
    RETURN p.paper_id as paper_id,
           p.title as title,
           p.abstract as abstract,
           p.sub_domain as sub_domain,
           p.study_design as study_design
    """
    return await client.run_query(query)


async def update_paper_classification(
    client: Neo4jClient,
    paper_id: str,
    sub_domain: Optional[str],
    study_design: Optional[str]
) -> bool:
    """논문 분류 업데이트."""
    set_clauses = []
    params = {"paper_id": paper_id}

    if sub_domain:
        set_clauses.append("p.sub_domain = $sub_domain")
        params["sub_domain"] = sub_domain

    if study_design:
        set_clauses.append("p.study_design = $study_design")
        params["study_design"] = study_design

    if not set_clauses:
        return False

    query = f"""
    MATCH (p:Paper {{paper_id: $paper_id}})
    SET {', '.join(set_clauses)}
    RETURN p.paper_id as updated
    """

    result = await client.run_query(query, params)
    return len(result) > 0


async def main():
    """메인 실행."""
    async with Neo4jClient() as client:
        # 분류되지 않은 논문 조회
        papers = await get_unclassified_papers(client)
        logger.info(f"Found {len(papers)} papers to classify")

        sub_domain_updated = 0
        study_design_updated = 0

        for paper in papers:
            paper_id = paper["paper_id"]
            title = paper.get("title") or ""
            abstract = paper.get("abstract") or ""
            current_sub_domain = paper.get("sub_domain")
            current_study_design = paper.get("study_design")

            new_sub_domain = None
            new_study_design = None

            # sub_domain 분류 필요 여부
            if not current_sub_domain or current_sub_domain in ["", "Unknown"]:
                new_sub_domain = classify_sub_domain(title, abstract)

            # study_design 분류 필요 여부
            if not current_study_design or current_study_design == "":
                new_study_design = classify_study_design(title, abstract)

            # 업데이트 실행
            if new_sub_domain or new_study_design:
                success = await update_paper_classification(
                    client, paper_id, new_sub_domain, new_study_design
                )
                if success:
                    if new_sub_domain:
                        sub_domain_updated += 1
                    if new_study_design:
                        study_design_updated += 1

        logger.info(f"\n=== Classification Complete ===")
        logger.info(f"sub_domain updated: {sub_domain_updated}")
        logger.info(f"study_design updated: {study_design_updated}")


if __name__ == "__main__":
    asyncio.run(main())
