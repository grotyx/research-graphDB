"""SNOMED-CT 통합 보강 모듈.

Neo4j 그래프의 SNOMED 코드 적용, TREATS 관계 백필, Anatomy 정리를 위한
단일 소스 오브 트루스(spine_snomed_mappings.py) 기반 동적 처리.

v1.16.3: update_snomed_codes.py + enhance_taxonomy_snomed.py 통합 대체.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ontology.spine_snomed_mappings import (
    SPINE_INTERVENTION_SNOMED,
    SPINE_PATHOLOGY_SNOMED,
    SPINE_OUTCOME_SNOMED,
    SPINE_ANATOMY_SNOMED,
    SNOMEDMapping,
)
from core.exceptions import ValidationError, ErrorCode

logger = logging.getLogger(__name__)

# =====================================================================
# 설정
# =====================================================================

ENTITY_TYPE_CONFIG: dict[str, tuple[str, dict[str, SNOMEDMapping]]] = {
    "intervention": ("Intervention", SPINE_INTERVENTION_SNOMED),
    "pathology": ("Pathology", SPINE_PATHOLOGY_SNOMED),
    "outcome": ("Outcome", SPINE_OUTCOME_SNOMED),
    "anatomy": ("Anatomy", SPINE_ANATOMY_SNOMED),
}

# 척추 레벨 순서 (C1~S2)
SPINE_LEVELS: list[str] = (
    [f"C{i}" for i in range(1, 8)]
    + [f"T{i}" for i in range(1, 13)]
    + [f"L{i}" for i in range(1, 6)]
    + [f"S{i}" for i in range(1, 3)]
)

# 비특이적 Anatomy 용어
NON_SPECIFIC_ANATOMY = {
    "Multi-level", "Multiple levels", "Multilevel", "Multisegmental",
    "Not specified", "Various", "Not reported", "N/A", "Unknown",
    "Whole spine", "Full spine",
}
# 사전 계산된 소문자 세트 (루프 내 재계산 방지)
_NON_SPECIFIC_LOWER = {s.lower() for s in NON_SPECIFIC_ANATOMY}

DIRECTION_ONLY_ANATOMY = {
    "anterior", "posterior", "lateral", "medial",
    "Anterior", "Posterior", "Lateral", "Medial",
}

# 다분절 범위 패턴: "L2-4", "L2-L4", "C3-6", "C3-C6", "T10-L2"
RANGE_PATTERN = re.compile(
    r'^([CTLS])(\d+)\s*[-–]\s*([CTLS]?)(\d+)$', re.IGNORECASE
)

# 콤마/세미콜론/and 구분 패턴: "L4-5, L5-S1", "L4-5 and L5-S1"
COMPOUND_SPLIT_PATTERN = re.compile(r'\s*[,;]\s*|\s+and\s+', re.IGNORECASE)


# =====================================================================
# 결과 데이터클래스
# =====================================================================

@dataclass
class UpdateResult:
    """SNOMED 업데이트 결과."""
    entity_type: str
    total_nodes: int = 0
    already_mapped: int = 0
    newly_mapped: int = 0
    no_mapping_found: int = 0
    low_confidence_skipped: int = 0  # v1.19.5: confidence 미달 스킵
    unmapped_names: list[str] = field(default_factory=list)
    low_confidence_names: list[str] = field(default_factory=list)  # v1.19.5


@dataclass
class TreatsBackfillResult:
    """TREATS 관계 백필 결과."""
    total_pairs: int = 0
    newly_created: int = 0
    already_existed: int = 0
    excluded_review_papers: int = 0
    top_pairs: list[tuple[str, str, int]] = field(default_factory=list)


@dataclass
class AnatomyCleanupResult:
    """Anatomy 정리 결과."""
    total_anatomy: int = 0
    flagged_non_specific: int = 0
    flagged_direction_only: int = 0
    split_compound: int = 0
    split_range: int = 0
    normalized: int = 0
    already_clean: int = 0
    segments_created: list[str] = field(default_factory=list)


# =====================================================================
# 1. Cypher 동적 생성 (schema.py 교체용)
# =====================================================================

def generate_snomed_update_queries(batch_size: int = 20) -> list[tuple[str, dict]]:
    """spine_snomed_mappings.py 기반으로 SNOMED 보강 Cypher 쿼리 동적 생성.

    파라미터 바인딩 기반: (query, params) 튜플 리스트 반환.

    Args:
        batch_size: 한 쿼리당 처리할 노드 수.

    Returns:
        (Cypher 쿼리 문자열, 파라미터 dict) 튜플 리스트.
    """
    ALLOWED_LABELS = {"Intervention", "Pathology", "Outcome", "Anatomy"}
    queries: list[tuple[str, dict]] = []

    for entity_type, (label, mapping_dict) in ENTITY_TYPE_CONFIG.items():
        if label not in ALLOWED_LABELS:
            raise ValidationError(
                message=f"Invalid label: {label}",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        items = list(mapping_dict.items())
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_data = []
            for name, m in batch:
                batch_data.append({
                    "name": name,
                    "snomed_code": m.code,
                    "snomed_term": m.term,
                    "snomed_is_extension": m.is_extension,
                })

            batch_num = i // batch_size + 1
            total_batches = (len(items) + batch_size - 1) // batch_size

            query = f"""
            UNWIND $items AS item
            CALL {{
                WITH item
                MATCH (n:{label} {{name: item.name}})
                SET n.snomed_code = item.snomed_code,
                    n.snomed_term = item.snomed_term,
                    n.snomed_is_extension = item.snomed_is_extension
            }}
            RETURN '{label} SNOMED batch {batch_num}/{total_batches} applied'
            """
            queries.append((query, {"items": batch_data}))

    return queries


# =====================================================================
# 2. SNOMED 업데이트 (4개 엔티티 타입)
# =====================================================================

async def update_snomed_for_entity_type(
    client,  # Neo4jClient
    entity_type: str,
    normalizer,  # EntityNormalizer
    dry_run: bool = False,
    min_confidence: float = 0.8,
) -> UpdateResult:
    """특정 엔티티 타입의 모든 노드에 SNOMED 코드 적용.

    전략:
    1. snomed_code가 없는 노드를 조회
    2. EntityNormalizer.normalize_{type}(name) 으로 매칭
    3. confidence >= min_confidence 인 경우만 DB SET (v1.19.5)

    Args:
        client: Neo4jClient 인스턴스
        entity_type: "intervention" | "pathology" | "outcome" | "anatomy"
        normalizer: EntityNormalizer 인스턴스
        dry_run: True이면 DB 변경 없이 결과만 반환
        min_confidence: SNOMED 코드 할당 최소 confidence (기본 0.8, v1.19.5)
    """
    if entity_type not in ENTITY_TYPE_CONFIG:
        raise ValidationError(
            message=f"Unknown entity type: {entity_type}",
            error_code=ErrorCode.VAL_INVALID_VALUE,
        )

    ALLOWED_LABELS = {"Intervention", "Pathology", "Outcome", "Anatomy"}
    label, _ = ENTITY_TYPE_CONFIG[entity_type]
    if label not in ALLOWED_LABELS:
        raise ValidationError(
            message=f"Invalid label: {label}",
            error_code=ErrorCode.VAL_INVALID_VALUE,
        )
    result = UpdateResult(entity_type=entity_type)

    # 전체 노드 수
    total_query = f"MATCH (n:{label}) RETURN count(n) as cnt"
    total_res = await client.run_query(total_query)
    result.total_nodes = total_res[0]["cnt"] if total_res else 0

    # 이미 매핑된 노드 수
    mapped_query = f"MATCH (n:{label}) WHERE n.snomed_code IS NOT NULL RETURN count(n) as cnt"
    mapped_res = await client.run_query(mapped_query)
    result.already_mapped = mapped_res[0]["cnt"] if mapped_res else 0

    # SNOMED 없는 노드 조회
    missing_query = f"""
    MATCH (n:{label})
    WHERE n.snomed_code IS NULL OR n.snomed_code = ''
    RETURN n.name as name
    ORDER BY n.name
    """
    missing_nodes = await client.run_query(missing_query)

    if not missing_nodes:
        logger.info(f"  {label}: 모든 노드에 SNOMED 코드가 있음")
        return result

    # normalize 메서드 매핑
    normalize_fn = getattr(normalizer, f"normalize_{entity_type}", None)
    if normalize_fn is None:
        logger.error(f"  EntityNormalizer에 normalize_{entity_type} 메서드 없음")
        return result

    batch_items: list[dict] = []
    for item in missing_nodes:
        name = item["name"]
        norm_result = normalize_fn(name)

        if norm_result.snomed_code:
            # v1.19.5: confidence 필터 - 낮은 신뢰도 매칭은 SNOMED 할당하지 않음
            if norm_result.confidence < min_confidence:
                result.low_confidence_skipped += 1
                result.low_confidence_names.append(
                    f"{name} → {norm_result.snomed_term} "
                    f"(conf={norm_result.confidence:.2f}, method={norm_result.method})"
                )
                logger.debug(
                    f"    SKIP (low confidence): {name} → {norm_result.snomed_code} "
                    f"(conf={norm_result.confidence:.2f}, method={norm_result.method})"
                )
                continue

            batch_items.append({
                "name": name,
                "snomed_code": norm_result.snomed_code,
                "snomed_term": norm_result.snomed_term,
            })
            result.newly_mapped += 1
            logger.debug(f"    {name} → {norm_result.snomed_code} ({norm_result.snomed_term})")
        else:
            result.no_mapping_found += 1
            result.unmapped_names.append(name)

    # Batch UNWIND: single query instead of N individual queries
    if batch_items and not dry_run:
        batch_query = f"""
        UNWIND $items AS item
        MATCH (n:{label} {{name: item.name}})
        SET n.snomed_code = item.snomed_code,
            n.snomed_term = item.snomed_term,
            n.snomed_updated_at = datetime()
        """
        await client.run_write_query(batch_query, {"items": batch_items})

    return result


# =====================================================================
# 3. TREATS 백필
# =====================================================================

async def backfill_treats_relations(
    client,  # Neo4jClient
    dry_run: bool = False,
) -> TreatsBackfillResult:
    """기존 Paper-Intervention, Paper-Pathology 관계로부터 TREATS 추론.

    로직:
        Paper→INVESTIGATES→Intervention AND Paper→STUDIES→Pathology
        ⇒ Intervention→TREATS→Pathology

    리뷰 논문 필터: Intervention 4개+ AND Pathology 4개+ 동시인 논문 제외.
    """
    result = TreatsBackfillResult()

    # 리뷰 논문 식별 (Intervention 4+ AND Pathology 4+ 인 논문)
    review_query = """
    MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
    WITH p, count(DISTINCT i) as int_count
    WHERE int_count >= 4
    MATCH (p)-[:STUDIES]->(pa:Pathology)
    WITH p, int_count, count(DISTINCT pa) as path_count
    WHERE path_count >= 4
    RETURN collect(p.paper_id) as review_ids
    """
    review_res = await client.run_query(review_query)
    review_ids = review_res[0].get("review_ids", []) if review_res else []
    result.excluded_review_papers = len(review_ids)

    if dry_run:
        # Dry-run: 생성될 관계 수만 조회
        count_query = """
        MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
        WHERE NOT p.paper_id IN $review_ids
        MATCH (p)-[:STUDIES]->(pa:Pathology)
        WITH i, pa, collect(DISTINCT p.paper_id) as paper_ids
        RETURN i.name as intervention, pa.name as pathology, size(paper_ids) as evidence
        ORDER BY evidence DESC
        """
        pairs = await client.run_query(count_query, {"review_ids": review_ids})
        result.total_pairs = len(pairs)

        # 기존 TREATS 확인
        existing_query = "MATCH ()-[r:TREATS]->() RETURN count(r) as cnt"
        existing_res = await client.run_query(existing_query)
        result.already_existed = existing_res[0]["cnt"] if existing_res else 0
        result.newly_created = max(0, result.total_pairs - result.already_existed)

        # Top 쌍
        for p in pairs[:15]:
            result.top_pairs.append((p["intervention"], p["pathology"], p["evidence"]))
    else:
        # 실제 MERGE — run_query 사용 (RETURN 결과 필요, run_write_query는 counter dict 반환)
        # NOTE: source_paper_ids (리스트)로 통일. relationship_builder.py도 동일 속성 사용.
        merge_query = """
        MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
        WHERE NOT p.paper_id IN $review_ids
        MATCH (p)-[:STUDIES]->(pa:Pathology)
        WITH i, pa, collect(DISTINCT p.paper_id) as paper_ids
        MERGE (i)-[r:TREATS]->(pa)
        ON CREATE SET
            r.inferred = true,
            r.source = 'backfill',
            r.paper_count = size(paper_ids),
            r.source_paper_ids = paper_ids,
            r.created_at = datetime()
        ON MATCH SET
            r.paper_count = size(paper_ids),
            r.source_paper_ids = paper_ids,
            r.updated_at = datetime()
        RETURN i.name as intervention, pa.name as pathology, size(paper_ids) as evidence
        ORDER BY evidence DESC
        """
        pairs = await client.run_query(merge_query, {"review_ids": review_ids})
        result.total_pairs = len(pairs)
        result.newly_created = len(pairs)

        for p in pairs[:15]:
            result.top_pairs.append((p["intervention"], p["pathology"], p["evidence"]))

    return result


# =====================================================================
# 4. Anatomy 범위 분리
# =====================================================================

def parse_segment_range(range_str: str) -> list[str]:
    """다분절 범위를 한 분절씩 분리.

    Args:
        range_str: 범위 문자열 (예: "L2-4", "C3-C6", "T10-L2")

    Returns:
        분리된 분절 리스트 (예: ["L2-3", "L3-4"])
        파싱 실패 시 빈 리스트.

    Examples:
        >>> parse_segment_range("L2-4")
        ['L2-3', 'L3-4']
        >>> parse_segment_range("C3-C6")
        ['C3-4', 'C4-5', 'C5-6']
        >>> parse_segment_range("T10-L2")
        ['T10-11', 'T11-12', 'T12-L1', 'L1-2']
        >>> parse_segment_range("L4-5")
        ['L4-5']
    """
    match = RANGE_PATTERN.match(range_str.strip())
    if not match:
        return []

    start_region = match.group(1).upper()
    start_num = int(match.group(2))
    end_region = match.group(3).upper() if match.group(3) else start_region
    end_num = int(match.group(4))

    start_level = f"{start_region}{start_num}"
    end_level = f"{end_region}{end_num}"

    # 레벨 인덱스 찾기
    try:
        start_idx = SPINE_LEVELS.index(start_level)
        end_idx = SPINE_LEVELS.index(end_level)
    except ValueError:
        return []

    if start_idx >= end_idx:
        return []

    # 연속 분절 쌍 생성
    segments: list[str] = []
    for i in range(start_idx, end_idx):
        level_a = SPINE_LEVELS[i]
        level_b = SPINE_LEVELS[i + 1]

        region_a = level_a[0]
        num_a = level_a[1:]
        region_b = level_b[0]
        num_b = level_b[1:]

        if region_a == region_b:
            # 같은 영역: "L2-3"
            segments.append(f"{region_a}{num_a}-{num_b}")
        else:
            # 교차 영역: "T12-L1"
            segments.append(f"{level_a}-{level_b}")

    return segments


def split_compound_anatomy(name: str) -> list[str]:
    """콤마/세미콜론/and로 구분된 복합 해부학 문자열을 개별 항목으로 분리.

    Args:
        name: 복합 문자열 (예: "L4-5, L5-S1", "L4-5 and L5-S1")

    Returns:
        분리된 항목 리스트.
    """
    parts = COMPOUND_SPLIT_PATTERN.split(name)
    return [p.strip() for p in parts if p.strip()]


# =====================================================================
# 5. Anatomy 정리
# =====================================================================

async def cleanup_anatomy_nodes(
    client,  # Neo4jClient
    normalizer,  # EntityNormalizer
    dry_run: bool = False,
) -> AnatomyCleanupResult:
    """Anatomy 노드 정리 및 정규화.

    처리 순서:
    1. 비특이적 용어 플래그 (Multi-level, Not specified)
    2. 방향어 플래그 (anterior, posterior)
    3. 콤마 구분 복합 문자열 분리
    4. 다분절 범위 분리 (L2-4 → L2-3, L3-4)
    5. SNOMED 코드 적용 (정상 노드)
    """
    result = AnatomyCleanupResult()

    # 전체 Anatomy 노드 조회
    all_query = """
    MATCH (a:Anatomy)
    RETURN a.name as name, a.snomed_code as snomed_code, a.quality_flag as quality_flag
    ORDER BY a.name
    """
    all_nodes = await client.run_query(all_query)
    result.total_anatomy = len(all_nodes)

    for node in all_nodes:
        name = node["name"]
        has_snomed = node["snomed_code"] is not None

        # 1. 비특이적 용어
        if name in NON_SPECIFIC_ANATOMY or name.lower() in _NON_SPECIFIC_LOWER:
            if node.get("quality_flag") != "non_specific":
                if not dry_run:
                    await client.run_write_query(
                        "MATCH (a:Anatomy {name: $name}) SET a.quality_flag = 'non_specific'",
                        {"name": name}
                    )
                result.flagged_non_specific += 1
            continue

        # 2. 방향어
        if name in DIRECTION_ONLY_ANATOMY:
            if node.get("quality_flag") != "direction_only":
                if not dry_run:
                    await client.run_write_query(
                        "MATCH (a:Anatomy {name: $name}) SET a.quality_flag = 'direction_only'",
                        {"name": name}
                    )
                result.flagged_direction_only += 1
            continue

        # 3. 콤마 구분 복합 문자열
        parts = split_compound_anatomy(name)
        if len(parts) > 1:
            all_segments: list[str] = []
            for part in parts:
                # 각 파트도 범위일 수 있음
                range_segments = parse_segment_range(part)
                if range_segments and len(range_segments) > 1:
                    all_segments.extend(range_segments)
                else:
                    all_segments.append(part)

            # DV-002: Title-case each segment before MERGE to prevent duplicates
            all_segments = [
                (s[0].upper() + s[1:] if s and not s[0].isupper() else s)
                for s in all_segments
            ]

            if not dry_run:
                # 원래 노드를 참조하는 Paper에 개별 분절 관계 생성
                for seg in all_segments:
                    await client.run_write_query(
                        """
                        MATCH (p:Paper)-[:INVOLVES]->(a:Anatomy {name: $compound})
                        MERGE (a2:Anatomy {name: $segment})
                        MERGE (p)-[:INVOLVES]->(a2)
                        """,
                        {"compound": name, "segment": seg}
                    )
                # 원래 노드에 플래그
                await client.run_write_query(
                    """
                    MATCH (a:Anatomy {name: $name})
                    SET a.quality_flag = 'compound_split',
                        a.split_into = $segments
                    """,
                    {"name": name, "segments": all_segments}
                )
            result.split_compound += 1
            result.segments_created.extend(all_segments)
            continue

        # 4. 다분절 범위 (단일 항목)
        range_segments = parse_segment_range(name)
        if range_segments and len(range_segments) > 1:
            # DV-002: Title-case each segment before MERGE to prevent duplicates
            range_segments = [
                (s[0].upper() + s[1:] if s and not s[0].isupper() else s)
                for s in range_segments
            ]
            if not dry_run:
                for seg in range_segments:
                    await client.run_write_query(
                        """
                        MATCH (p:Paper)-[:INVOLVES]->(a:Anatomy {name: $range_name})
                        MERGE (a2:Anatomy {name: $segment})
                        MERGE (p)-[:INVOLVES]->(a2)
                        """,
                        {"range_name": name, "segment": seg}
                    )
                await client.run_write_query(
                    """
                    MATCH (a:Anatomy {name: $name})
                    SET a.quality_flag = 'range_split',
                        a.split_into = $segments
                    """,
                    {"name": name, "segments": range_segments}
                )
            result.split_range += 1
            result.segments_created.extend(range_segments)
            continue

        # 5. 정상 노드 — SNOMED 적용
        if has_snomed:
            result.already_clean += 1
        else:
            norm = normalizer.normalize_anatomy(name)
            if norm and norm.snomed_code:
                if not dry_run:
                    await client.run_write_query(
                        """
                        MATCH (a:Anatomy {name: $name})
                        SET a.snomed_code = $code,
                            a.snomed_term = $term,
                            a.snomed_updated_at = datetime()
                        """,
                        {"name": name, "code": norm.snomed_code, "term": norm.snomed_term}
                    )
                result.normalized += 1
            else:
                # SNOMED 없고 매핑도 못찾은 노드 (unmapped)
                result.already_clean += 1
                logger.debug(f"  Anatomy 매핑 불가: {name}")

    return result


# =====================================================================
# 6. 커버리지 리포트
# =====================================================================

async def generate_coverage_report(client) -> dict:
    """현재 SNOMED 커버리지 리포트 생성."""
    report: dict = {}

    for entity_type, (label, mapping_dict) in ENTITY_TYPE_CONFIG.items():
        query = f"""
        MATCH (n:{label})
        WITH count(n) as total,
             sum(CASE WHEN n.snomed_code IS NOT NULL THEN 1 ELSE 0 END) as mapped
        RETURN total, mapped
        """
        res = await client.run_query(query)
        total = res[0]["total"] if res else 0
        mapped = res[0]["mapped"] if res else 0
        pct = round(100.0 * mapped / total, 1) if total > 0 else 0.0

        report[entity_type] = {
            "label": label,
            "total": total,
            "mapped": mapped,
            "unmapped": total - mapped,
            "coverage_pct": pct,
            "available_mappings": len(mapping_dict),
        }

    # TREATS 관계 수
    treats_query = "MATCH ()-[r:TREATS]->() RETURN count(r) as cnt"
    treats_res = await client.run_query(treats_query)
    report["treats_count"] = treats_res[0]["cnt"] if treats_res else 0

    # Anatomy 품질 플래그
    flag_query = """
    MATCH (a:Anatomy)
    WHERE a.quality_flag IS NOT NULL
    RETURN a.quality_flag as flag, count(a) as cnt
    """
    flag_res = await client.run_query(flag_query)
    report["anatomy_flags"] = {r["flag"]: r["cnt"] for r in flag_res} if flag_res else {}

    return report
