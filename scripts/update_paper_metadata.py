#!/usr/bin/env python3
"""Update Paper node metadata from extracted JSON files.

JSON 파일의 metadata/spine_metadata를 Neo4j Paper 노드에 업데이트합니다.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient, Neo4jConfig
from graph.types.enums import normalize_study_design

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_metadata_from_json(json_path: Path) -> Optional[Dict[str, Any]]:
    """JSON 파일에서 메타데이터 추출."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        metadata = data.get('metadata', {})
        spine_metadata = data.get('spine_metadata', {})

        # Paper ID 추출 (파일명에서)
        paper_id = json_path.stem

        # 업데이트할 필드들
        updates = {
            'paper_id': paper_id,
            'title': metadata.get('title'),
            'study_design': normalize_study_design(metadata.get('study_design') or metadata.get('study_type') or ""),
            'evidence_level': metadata.get('evidence_level'),
            'sample_size': metadata.get('sample_size'),
            'sub_domain': spine_metadata.get('sub_domain'),
            'anatomy_level': spine_metadata.get('anatomy_level'),
            'anatomy_region': spine_metadata.get('anatomy_region'),
            'follow_up_months': spine_metadata.get('follow_up_months'),
        }

        # None 값 제거
        updates = {k: v for k, v in updates.items() if v is not None}

        return updates if len(updates) > 1 else None  # paper_id만 있으면 None

    except Exception as e:
        logger.error(f"Error reading {json_path}: {e}")
        return None


async def update_paper_in_neo4j(client: Neo4jClient, updates: Dict[str, Any]) -> bool:
    """Neo4j Paper 노드 업데이트 (title로 매칭)."""
    paper_id = updates.pop('paper_id')
    title = updates.get('title')

    if not updates or not title:
        return False

    # SET 절 구성
    set_clauses = []
    for key, value in updates.items():
        if key == 'title':
            continue  # title은 매칭용, 업데이트 대상 아님
        if isinstance(value, str):
            set_clauses.append(f"p.{key} = ${key}")
        elif isinstance(value, (int, float)):
            set_clauses.append(f"p.{key} = ${key}")

    if not set_clauses:
        return False

    # Title의 첫 50자로 매칭 (대소문자 무시)
    title_prefix = title[:50].lower() if len(title) > 50 else title.lower()

    query = f"""
    MATCH (p:Paper)
    WHERE toLower(p.title) STARTS WITH $title_prefix
    SET {', '.join(set_clauses)}
    RETURN p.paper_id as updated_id
    """

    try:
        params = {'title_prefix': title_prefix}
        # title 제외한 나머지 params 추가
        for k, v in updates.items():
            if k != 'title':
                params[k] = v
        result = await client.run_query(query, params)
        return len(result) > 0
    except Exception as e:
        logger.error(f"Error updating paper with title '{title[:30]}...': {e}")
        return False


async def main():
    """메인 실행."""
    extracted_dir = Path(__file__).parent.parent / "data" / "extracted"

    if not extracted_dir.exists():
        logger.error(f"Directory not found: {extracted_dir}")
        return

    json_files = list(extracted_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} JSON files")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    async with Neo4jClient() as client:
        for json_path in json_files:
            updates = extract_metadata_from_json(json_path)

            if updates is None:
                skipped_count += 1
                continue

            paper_id = updates.get('paper_id', json_path.stem)

            if await update_paper_in_neo4j(client, updates.copy()):
                updated_count += 1
                if updated_count % 50 == 0:
                    logger.info(f"Updated {updated_count} papers...")
            else:
                error_count += 1

    logger.info(f"\n=== Update Complete ===")
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Skipped (no metadata): {skipped_count}")
    logger.info(f"Errors: {error_count}")


if __name__ == "__main__":
    asyncio.run(main())
