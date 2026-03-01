#!/usr/bin/env python3
"""고립 논문 복구 스크립트.

STUDIES/INVESTIGATES/INVOLVES 관계가 없는 논문의 abstract를
LLM(Claude Haiku)으로 재분석하여 엔티티 관계를 구축합니다.

Usage:
    PYTHONPATH=./src ./.venv/bin/python scripts/repair_isolated_papers.py
    PYTHONPATH=./src ./.venv/bin/python scripts/repair_isolated_papers.py --dry-run
    PYTHONPATH=./src ./.venv/bin/python scripts/repair_isolated_papers.py --max-concurrent 3
    PYTHONPATH=./src ./.venv/bin/python scripts/repair_isolated_papers.py --paper-ids pubmed_123,pubmed_456
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# .env 로드
from dotenv import load_dotenv
load_dotenv()

from graph.neo4j_client import Neo4jClient
from graph.relationship_builder import RelationshipBuilder, SpineMetadata as GraphSpineMetadata
from graph.entity_normalizer import EntityNormalizer
from builder.unified_pdf_processor import (
    UnifiedPDFProcessor,
    ExtractedMetadata,
)
from graph.types.enums import normalize_study_design

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("repair_isolated")


async def get_isolated_papers(neo4j_client: Neo4jClient, paper_ids: list[str] | None = None) -> list[dict]:
    """관계 없는 고립 논문 목록 조회."""
    if paper_ids:
        query = """
        MATCH (p:Paper)
        WHERE p.paper_id IN $paper_ids
        RETURN p.paper_id AS paper_id, p.title AS title, p.abstract AS abstract,
               p.study_type AS study_type, p.pmid AS pmid, p.doi AS doi,
               p.year AS year, p.journal AS journal, p.authors AS authors
        ORDER BY p.paper_id
        """
        result = await neo4j_client.run_query(query, {"paper_ids": paper_ids})
    else:
        query = """
        MATCH (p:Paper)
        WHERE NOT (p)-[:STUDIES]->()
          AND NOT (p)-[:INVESTIGATES]->()
          AND NOT (p)-[:INVOLVES]->()
        RETURN p.paper_id AS paper_id, p.title AS title, p.abstract AS abstract,
               p.study_type AS study_type, p.pmid AS pmid, p.doi AS doi,
               p.year AS year, p.journal AS journal, p.authors AS authors
        ORDER BY p.paper_id
        """
        result = await neo4j_client.run_query(query)

    papers = []
    for r in result:
        abstract = r.get("abstract", "") or ""
        if len(abstract) < 50:
            logger.warning(f"Skipping {r['paper_id']}: abstract too short ({len(abstract)} chars)")
            continue
        papers.append(dict(r))
    return papers


def parse_llm_response(extracted_data: dict, paper: dict) -> tuple[GraphSpineMetadata, ExtractedMetadata]:
    """LLM 응답을 GraphSpineMetadata + ExtractedMetadata로 변환.

    pubmed_bulk_processor._process_abstract_with_llm()의 로직을 재사용.
    """
    metadata_dict = extracted_data.get("metadata") or {}
    spine_meta = extracted_data.get("spine_metadata") or {}

    # anatomy_levels: 복수형 키 우선, 없으면 단수형 폴백
    anatomy_levels = spine_meta.get("anatomy_levels", []) or []
    if not anatomy_levels:
        anatomy_level = spine_meta.get("anatomy_level", "")
        anatomy_levels = [anatomy_level] if anatomy_level else []
    if not anatomy_levels:
        anatomy_region = spine_meta.get("anatomy_region", "")
        if anatomy_region:
            anatomy_levels = [anatomy_region]

    # pathologies: 복수형 키 우선, 없으면 단수형 폴백
    pathologies_raw = spine_meta.get("pathologies") or spine_meta.get("pathology", [])
    pathologies = pathologies_raw if isinstance(pathologies_raw, list) else [pathologies_raw] if pathologies_raw else []

    # outcomes
    all_outcomes = spine_meta.get("outcomes", [])

    # sub_domains
    sub_domains = spine_meta.get("sub_domains", []) or []
    sub_domain = spine_meta.get("sub_domain", "") or ""
    if not sub_domains and sub_domain:
        sub_domains = [sub_domain]
    if sub_domains and not sub_domain:
        sub_domain = sub_domains[0]

    # surgical_approach
    surgical_approach = spine_meta.get("surgical_approach", []) or []

    # PICO
    pico = spine_meta.get("pico", {}) or {}
    pico_population = pico.get("population", "") or spine_meta.get("pico_population", "")
    pico_intervention = pico.get("intervention", "") or spine_meta.get("pico_intervention", "")
    pico_comparison = pico.get("comparison", "") or spine_meta.get("pico_comparison", "")
    pico_outcome = pico.get("outcome", "") or spine_meta.get("pico_outcome", "")

    graph_spine_meta = GraphSpineMetadata(
        sub_domains=sub_domains,
        sub_domain=sub_domain,
        surgical_approach=surgical_approach,
        anatomy_levels=anatomy_levels,
        pathologies=pathologies,
        interventions=spine_meta.get("interventions", []),
        outcomes=all_outcomes,
        main_conclusion=spine_meta.get("main_conclusion", ""),
        pico_population=pico_population,
        pico_intervention=pico_intervention,
        pico_comparison=pico_comparison,
        pico_outcome=pico_outcome,
    )

    # ExtractedMetadata
    authors_raw = metadata_dict.get("authors", paper.get("authors")) or []
    if isinstance(authors_raw, str):
        authors_raw = [a.strip() for a in authors_raw.split(",") if a.strip()]

    extracted_metadata = ExtractedMetadata(
        title=metadata_dict.get("title", paper.get("title", "")) or paper.get("title", ""),
        authors=authors_raw,
        year=metadata_dict.get("year", paper.get("year", 0)) or paper.get("year", 0),
        journal=metadata_dict.get("journal", paper.get("journal", "")) or paper.get("journal", ""),
        doi=metadata_dict.get("doi", paper.get("doi", "")) or paper.get("doi", ""),
        pmid=paper.get("pmid", "") or "",
        abstract=paper.get("abstract", ""),
        study_type=metadata_dict.get("study_type", ""),
        study_design=normalize_study_design(metadata_dict.get("study_design", "")),
        evidence_level=metadata_dict.get("evidence_level", "5") or "5",
        sample_size=metadata_dict.get("sample_size", 0) or 0,
        centers=metadata_dict.get("centers", ""),
        blinding=metadata_dict.get("blinding", ""),
    )

    return graph_spine_meta, extracted_metadata


async def repair_single_paper(
    paper: dict,
    processor: UnifiedPDFProcessor,
    relationship_builder: RelationshipBuilder,
    dry_run: bool = False,
    save_json: bool = True,
) -> dict:
    """단일 논문 복구."""
    paper_id = paper["paper_id"]
    title = (paper.get("title") or "")[:80]
    abstract = paper.get("abstract", "")

    logger.info(f"[{paper_id}] Processing: {title}...")

    start = time.time()

    # 1. LLM으로 abstract 분석
    try:
        result = await processor.process_text(
            text=abstract,
            title=paper.get("title", ""),
            source="repair_abstract",
        )
    except Exception as e:
        logger.error(f"[{paper_id}] LLM processing failed: {e}")
        return {"paper_id": paper_id, "success": False, "error": str(e)}

    if not result.success:
        logger.warning(f"[{paper_id}] LLM extraction failed: {result.error}")
        return {"paper_id": paper_id, "success": False, "error": result.error}

    extracted_data = result.extracted_data
    if not extracted_data:
        logger.warning(f"[{paper_id}] No data extracted")
        return {"paper_id": paper_id, "success": False, "error": "No data extracted"}

    # 2. LLM 응답 파싱
    spine_meta, extracted_metadata = parse_llm_response(extracted_data, paper)

    # 추출 결과 요약
    summary = {
        "pathologies": spine_meta.pathologies,
        "interventions": spine_meta.interventions,
        "anatomy_levels": spine_meta.anatomy_levels,
        "outcomes_count": len(spine_meta.outcomes),
        "sub_domains": spine_meta.sub_domains,
        "study_type": extracted_metadata.study_type,
    }
    logger.info(f"[{paper_id}] Extracted: P={len(spine_meta.pathologies)}, "
                f"I={len(spine_meta.interventions)}, A={len(spine_meta.anatomy_levels)}, "
                f"O={len(spine_meta.outcomes)}, D={spine_meta.sub_domains}")

    if dry_run:
        logger.info(f"[{paper_id}] DRY RUN - would build relationships")
        return {"paper_id": paper_id, "success": True, "dry_run": True, "extracted": summary}

    # 3. Neo4j 관계 구축
    chunks_data = extracted_data.get("chunks") or []
    try:
        build_result = await relationship_builder.build_from_paper(
            paper_id=paper_id,
            metadata=extracted_metadata,
            spine_metadata=spine_meta,
            chunks=chunks_data,
            owner="system",
            shared=True,
        )
        logger.info(f"[{paper_id}] Built: {build_result.nodes_created} nodes, "
                     f"{build_result.relationships_created} relationships")

        if build_result.errors:
            for err in build_result.errors:
                logger.warning(f"[{paper_id}] Build error: {err}")

    except Exception as e:
        logger.error(f"[{paper_id}] Relationship building failed: {e}")
        return {"paper_id": paper_id, "success": False, "error": str(e), "extracted": summary}

    # 4. study_type 업데이트 (기존 Paper 노드에)
    if extracted_metadata.study_type:
        try:
            await relationship_builder.client.run_query(
                "MATCH (p:Paper {paper_id: $pid}) SET p.study_type = $st",
                {"pid": paper_id, "st": extracted_metadata.study_type}
            )
        except Exception as e:
            logger.warning(f"[{paper_id}] study_type update failed: {e}")

    # 5. JSON 저장
    if save_json:
        json_dir = Path("data/extracted")
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{paper_id}_repair.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"[{paper_id}] JSON save failed: {e}")

    elapsed = time.time() - start
    return {
        "paper_id": paper_id,
        "success": True,
        "nodes_created": build_result.nodes_created,
        "relationships_created": build_result.relationships_created,
        "elapsed": round(elapsed, 1),
        "extracted": summary,
    }


async def main():
    parser = argparse.ArgumentParser(description="Repair isolated papers by re-extracting entities via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Only extract, don't build relationships")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent LLM calls (1-10)")
    parser.add_argument("--paper-ids", type=str, help="Comma-separated paper IDs to repair")
    parser.add_argument("--no-save-json", action="store_true", help="Don't save extracted JSON")
    args = parser.parse_args()

    max_concurrent = max(1, min(10, args.max_concurrent))
    paper_ids = [p.strip() for p in args.paper_ids.split(",")] if args.paper_ids else None

    logger.info("=" * 60)
    logger.info("Isolated Papers Repair Script")
    logger.info(f"  dry_run={args.dry_run}, max_concurrent={max_concurrent}")
    if paper_ids:
        logger.info(f"  target papers: {paper_ids}")
    logger.info("=" * 60)

    # 초기화
    neo4j_client = Neo4jClient()
    await neo4j_client.connect()

    normalizer = EntityNormalizer()
    relationship_builder = RelationshipBuilder(neo4j_client, normalizer)
    processor = UnifiedPDFProcessor()

    try:
        # 고립 논문 조회
        papers = await get_isolated_papers(neo4j_client, paper_ids)
        logger.info(f"Found {len(papers)} isolated papers to repair")

        if not papers:
            logger.info("No isolated papers found. Nothing to do.")
            return

        # 세마포어로 동시 실행 제한
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_repair(paper):
            async with semaphore:
                return await repair_single_paper(
                    paper=paper,
                    processor=processor,
                    relationship_builder=relationship_builder,
                    dry_run=args.dry_run,
                    save_json=not args.no_save_json,
                )

        # 병렬 실행
        start_time = time.time()
        results = await asyncio.gather(*[bounded_repair(p) for p in papers], return_exceptions=True)

        # 결과 집계
        total = len(results)
        success = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failed = total - success
        total_nodes = sum(r.get("nodes_created", 0) for r in results if isinstance(r, dict))
        total_rels = sum(r.get("relationships_created", 0) for r in results if isinstance(r, dict))
        elapsed = time.time() - start_time

        logger.info("")
        logger.info("=" * 60)
        logger.info("REPAIR RESULTS")
        logger.info("=" * 60)
        logger.info(f"  Total papers:  {total}")
        logger.info(f"  Success:       {success}")
        logger.info(f"  Failed:        {failed}")
        logger.info(f"  Nodes created: {total_nodes}")
        logger.info(f"  Rels created:  {total_rels}")
        logger.info(f"  Total time:    {elapsed:.1f}s")
        logger.info("=" * 60)

        # 실패 목록 출력
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"  Exception: {r}")
            elif isinstance(r, dict) and not r.get("success"):
                logger.warning(f"  FAILED: {r.get('paper_id')} - {r.get('error')}")

        # 결과 JSON 저장
        results_path = Path("/tmp/repair_results.json")
        serializable = []
        for r in results:
            if isinstance(r, Exception):
                serializable.append({"error": str(r)})
            else:
                serializable.append(r)
        with open(results_path, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")

    finally:
        await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(main())
