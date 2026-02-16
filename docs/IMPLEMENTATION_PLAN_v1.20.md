# Auto Normalizer Expansion 구현 계획 (v1.20.0)

## Context

### 문제
새 논문 처리 시 Claude Haiku가 자유 텍스트로 엔티티 이름을 생성하고, EntityNormalizer 5단계 매칭이 실패하면 (confidence=0.0) 원본 그대로 Neo4j에 새 노드가 생성됨. 결과: 1,874개 Outcome 노드 중 실제 정규 개념은 ~100개.

### 근본 원인
- **설계 40%**: LLM 프롬프트에 제어 어휘 없음 → 무한한 표현 변형 생성
- **코드 40%**: Normalizer 매칭 실패 시 pass-through → 새 노드 무조건 생성
- **데이터 20%**: 척추 의학 용어의 자연적 다양성

### 해결 전략: 3단계 방어 체계
```
[Layer 1] 추출 시점    LLM 프롬프트에 canonical 용어 목록 제공
[Layer 2] 저장 시점    매칭 실패 → LLM 2차 분류 → 동적 alias 등록
[Layer 3] 사후 정리    배치 스크립트: 미매핑 노드 통합 + SNOMED 자동 할당
```

### 최신 트렌드 반영
- SNOMED CT Entity Linking Challenge (2024): 1위 팀 dictionary-based 접근 (100만+ 동의어 DB), 2위 encoder-based, 3위 LLM decoder-based
- Claude Haiku 4.5: `generate_json()` 메서드로 structured output 지원 (현재 프로젝트에서 이미 사용 중)
- RapidFuzz: `token_sort_ratio()`와 `WRatio()` → 후보 사전 필터링에 최적

---

## 팀 에이전트 구성

| 에이전트 | 역할 | 담당 파일 |
|---------|------|----------|
| **agent-layer1** | Layer 1: 추출 프롬프트 제어 어휘 | `unified_pdf_processor.py` |
| **agent-layer2** | Layer 2: LLM 폴백 + 동적 alias | `entity_normalizer.py`, `relationship_builder.py`, `medical_kag_server.py` |
| **agent-layer3** | Layer 3: 배치 정리 스크립트 | `scripts/consolidate_entities.py` (신규) |
| **agent-tests** | 테스트 작성 | `tests/test_auto_normalizer.py` (신규) |

---

## Agent 1: Layer 1 — 추출 프롬프트 제어 어휘 (agent-layer1)

### 수정 파일
`src/builder/unified_pdf_processor.py`

### Task 1.1: `_build_vocabulary_hints()` 함수 추가

**위치**: line ~360 (EXTRACTION_PROMPT 정의 전)

```python
def _build_vocabulary_hints() -> str:
    """EntityNormalizer ALIASES에서 canonical name 목록을 생성하여 프롬프트 힌트 구성.

    Returns:
        EXTRACTION_PROMPT에 추가할 vocabulary hints 문자열.
        EntityNormalizer import 실패 시 빈 문자열 반환 (graceful degradation).
    """
    try:
        from graph.entity_normalizer import EntityNormalizer
        normalizer = EntityNormalizer()

        interventions = sorted(normalizer.INTERVENTION_ALIASES.keys())
        outcomes = sorted(normalizer.OUTCOME_ALIASES.keys())
        pathologies = sorted(normalizer.PATHOLOGY_ALIASES.keys())

        return f"""

### 7. CONTROLLED VOCABULARY (CRITICAL)
When extracting entity names, PREFER these canonical names over free-text variants.
Only use a name NOT in this list if the concept is genuinely new.

**Interventions**: {', '.join(interventions)}

**Outcomes** (for outcome.name field): {', '.join(outcomes)}

**Pathologies**: {', '.join(pathologies)}

Examples of correct mapping:
- "Visual Analog Scale back pain score" → use "VAS"
- "Oswestry Disability Index score" → use "ODI"
- "Biportal endoscopic lumbar decompression" → use "UBE"
- "estimated intraoperative blood loss" → use "Blood Loss"
"""
    except Exception:
        return ""
```

### Task 1.2: EXTRACTION_PROMPT에 vocabulary hints 결합

**위치**: line 510 (현재 EXTRACTION_PROMPT 끝, `}` 닫기 후)

현재:
```python
EXTRACTION_PROMPT = """You are a medical..."""
```

변경:
```python
# 정적 프롬프트 + 동적 vocabulary hints 결합
_EXTRACTION_PROMPT_BASE = """You are a medical..."""  # 기존 전체 텍스트

EXTRACTION_PROMPT = _EXTRACTION_PROMPT_BASE + _build_vocabulary_hints()
```

### 예상 토큰 비용
- Intervention ~80개 + Outcome ~83개 + Pathology ~50개 = 약 213개 canonical names
- 프롬프트 추가: ~600 토큰 → 논문당 ~$0.0006 (Haiku 기준)

### 검증
- `EXTRACTION_PROMPT`에 vocabulary 목록이 포함되는지 확인
- 기존 추출 테스트 통과 확인

---

## Agent 2: Layer 2 — LLM 폴백 + 동적 Alias (agent-layer2)

### 수정 파일 4개

#### Task 2.1: `entity_normalizer.py` — `register_dynamic_alias()` 메서드

**위치**: EntityNormalizer 클래스 내, `__init__` 다음 (~line 1850)

```python
def register_dynamic_alias(
    self,
    entity_type: str,
    alias: str,
    canonical: str,
) -> bool:
    """런타임에 새 alias를 reverse_map에 등록 (thread-safe).

    메모리 전용 — 재시작 시 초기화됨.
    canonical이 기존 ALIASES 딕셔너리에 존재해야만 등록 가능.

    Args:
        entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
        alias: 새로 등록할 alias 문자열
        canonical: 매핑 대상 canonical 이름 (ALIASES에 존재해야 함)

    Returns:
        True if registered, False if rejected (중복/invalid canonical)
    """
    reverse_map_key = f"_{entity_type}_reverse"
    aliases_dict_key = f"{entity_type.upper()}_ALIASES"

    reverse_map = getattr(self, reverse_map_key, None)
    aliases_dict = getattr(self, aliases_dict_key, None)

    if reverse_map is None or aliases_dict is None:
        return False

    alias_lower = alias.lower().strip()

    # 이미 등록된 alias
    if alias_lower in reverse_map:
        return False

    # canonical이 ALIASES에 없으면 거부 (안전장치)
    if canonical not in aliases_dict:
        logger.warning(
            f"Dynamic alias rejected: '{canonical}' not in {entity_type} ALIASES"
        )
        return False

    # thread-safe 등록 (dict assignment는 Python GIL 하에서 atomic)
    reverse_map[alias_lower] = canonical
    logger.info(f"Dynamic alias: '{alias}' → '{canonical}' ({entity_type})")
    return True
```

#### Task 2.2: `entity_normalizer.py` — `_get_candidate_canonicals()` 메서드

**위치**: `register_dynamic_alias()` 바로 아래

```python
def _get_candidate_canonicals(
    self,
    text: str,
    entity_type: str,
    top_k: int = 30,
) -> list[str]:
    """rapidfuzz로 상위 top_k 후보 canonical names 빠르게 필터링.

    LLM 프롬프트에 포함할 후보 목록을 최소화하여 비용/정확도 최적화.

    Args:
        text: 매칭 실패한 원본 텍스트
        entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
        top_k: 반환할 최대 후보 수

    Returns:
        similarity 순 정렬된 canonical name 목록
    """
    aliases_dict = {
        "intervention": self.INTERVENTION_ALIASES,
        "outcome": self.OUTCOME_ALIASES,
        "pathology": self.PATHOLOGY_ALIASES,
        "anatomy": self.ANATOMY_ALIASES,
    }.get(entity_type, {})

    canonicals = list(aliases_dict.keys())
    if not canonicals:
        return []

    # rapidfuzz WRatio: 다양한 비율 메트릭 중 최선 자동 선택
    lower_to_original = {c.lower(): c for c in canonicals}
    results = process.extract(
        text.lower(),
        list(lower_to_original.keys()),
        scorer=fuzz.WRatio,
        limit=top_k,
    )

    return [lower_to_original[r[0]] for r in results if r[1] > 30]
```

#### Task 2.3: `relationship_builder.py` — LLM 분류 함수 + `_normalize_with_fallback()`

**위치**: RelationshipBuilder 클래스 외부 (모듈 레벨, ~line 440)

```python
# LLM 분류 프롬프트 (토큰 최소화)
_CLASSIFY_ENTITY_PROMPT = """You are a spine surgery terminology expert.

Term: "{entity_text}"
Type: {entity_type}

Is this term a synonym/variant of any canonical concept below?

{candidates}

Respond JSON only:
{{"match": "canonical_name_or_null", "confidence": 0.0-1.0, "reason": "brief"}}

Rules:
- confidence >= 0.9: definite match (same medical concept, different wording)
- confidence 0.7-0.89: probable match (closely related but uncertain)
- confidence < 0.7 or match=null: genuinely different concept
- Do NOT force-match unrelated concepts. When in doubt, return null."""


async def classify_unmatched_entity(
    entity_text: str,
    entity_type: str,
    candidates: list[str],
    llm_client,
) -> tuple[str, float] | None:
    """Claude Haiku로 미매칭 엔티티를 기존 canonical에 분류.

    Args:
        entity_text: 정규화 실패한 원본 텍스트
        entity_type: 엔티티 유형
        candidates: rapidfuzz로 사전 필터링된 후보 목록 (최대 30개)
        llm_client: ClaudeClient 인스턴스

    Returns:
        (canonical_name, confidence) 또는 None (매칭 없음/신규 개념)
    """
    if not llm_client or not candidates:
        return None

    prompt = _CLASSIFY_ENTITY_PROMPT.format(
        entity_text=entity_text,
        entity_type=entity_type,
        candidates="\n".join(f"- {c}" for c in candidates[:30]),
    )

    schema = {
        "type": "object",
        "properties": {
            "match": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["match", "confidence", "reason"],
    }

    try:
        result = await llm_client.generate_json(prompt, schema)
        matched = result.get("match")
        confidence = float(result.get("confidence", 0.0))

        if matched and confidence >= 0.85 and matched in candidates:
            logger.info(
                f"LLM classify: '{entity_text}' → '{matched}' "
                f"(conf={confidence:.2f})"
            )
            return (matched, confidence)

        return None
    except Exception as e:
        logger.warning(f"LLM classify failed for '{entity_text}': {e}")
        return None
```

**위치**: RelationshipBuilder 클래스 내부

```python
class RelationshipBuilder:
    def __init__(
        self,
        neo4j_client: Neo4jClient,
        normalizer: EntityNormalizer,
        llm_client=None,  # v1.20.0: LLM 폴백용
    ) -> None:
        self.client = neo4j_client
        self.normalizer = normalizer
        self.llm_client = llm_client
        self._llm_call_count = 0  # 논문당 rate limit
        self._llm_call_limit = 10  # 최대 LLM 호출 수/논문

    async def _normalize_with_fallback(
        self,
        text: str,
        entity_type: str,
    ) -> NormalizationResult:
        """5단계 정규화 + LLM 폴백.

        Flow:
        1. normalize_X(text) → confidence > 0 이면 즉시 반환
        2. LLM client 없거나 rate limit 초과 → 원본 반환
        3. _get_candidate_canonicals()로 후보 30개 추출
        4. classify_unmatched_entity() LLM 호출
        5. 매칭 성공 → register_dynamic_alias() + 재정규화
        6. 매칭 실패 → 원본 반환 (기존 동작)
        """
        normalize_fn = getattr(self.normalizer, f"normalize_{entity_type}")
        result = normalize_fn(text)

        if result.confidence > 0.0:
            return result

        # LLM 폴백 조건 체크
        if not self.llm_client:
            return result
        if entity_type not in ("intervention", "outcome", "pathology"):
            return result  # anatomy는 패턴 기반으로 충분
        if self._llm_call_count >= self._llm_call_limit:
            return result

        self._llm_call_count += 1

        candidates = self.normalizer._get_candidate_canonicals(
            text, entity_type, top_k=30
        )
        if not candidates:
            return result

        llm_result = await classify_unmatched_entity(
            entity_text=text,
            entity_type=entity_type,
            candidates=candidates,
            llm_client=self.llm_client,
        )

        if llm_result:
            canonical, confidence = llm_result
            self.normalizer.register_dynamic_alias(
                entity_type=entity_type,
                alias=text,
                canonical=canonical,
            )
            # 재정규화 (이제 alias가 등록되었으므로 exact match됨)
            result = normalize_fn(text)
            result.method = f"llm_classified+{result.method}"
            return result

        return result
```

#### Task 2.4: 기존 `create_*_relations` 메서드 수정

4개 메서드에서 직접 normalize 호출을 `_normalize_with_fallback()`으로 교체:

| 메서드 | 현재 호출 (line) | 변경 |
|--------|-----------------|------|
| `create_studies_relations` | `self.normalizer.normalize_pathology(pathology)` (771) | `await self._normalize_with_fallback(pathology, "pathology")` |
| `create_investigates_relations` | `self.normalizer.normalize_intervention(intervention)` (889) | `await self._normalize_with_fallback(intervention, "intervention")` |
| `create_treats_relations` | `self.normalizer.normalize_intervention/pathology` (944,948) | `await self._normalize_with_fallback(...)` |
| `create_affects_relations` | `self.normalizer.normalize_outcome(outcome.name)` (993) | `await self._normalize_with_fallback(outcome.name, "outcome")` |

**주의**: `build_from_paper()` 시작 시 `self._llm_call_count = 0` 리셋 필요 (line ~480)

#### Task 2.5: `medical_kag_server.py` — llm_client 전달

**위치**: line 544

현재:
```python
self.relationship_builder = RelationshipBuilder(
    neo4j_client=self.neo4j_client,
    normalizer=self.entity_normalizer
)
```

변경:
```python
self.relationship_builder = RelationshipBuilder(
    neo4j_client=self.neo4j_client,
    normalizer=self.entity_normalizer,
    llm_client=self.llm_client,  # v1.20.0: LLM 폴백
)
```

### 안전장치 정리

| 안전장치 | 구현 위치 | 설명 |
|---------|----------|------|
| confidence >= 0.85 | `classify_unmatched_entity()` | 낮은 신뢰도 매칭 차단 |
| canonical 검증 | `register_dynamic_alias()` | ALIASES에 없는 canonical 거부 |
| 논문당 rate limit | `_normalize_with_fallback()` | 최대 10회 LLM 호출 |
| 메모리 전용 alias | `register_dynamic_alias()` | 재시작 시 초기화 |
| graceful degradation | `_normalize_with_fallback()` | LLM 없으면 기존 동작 유지 |

---

## Agent 3: Layer 3 — 배치 정리 스크립트 (agent-layer3)

### 새 파일
`scripts/consolidate_entities.py`

### Task 3.1: 메인 스크립트 구조

```python
#!/usr/bin/env python3
"""Entity 통합 스크립트 — 미매핑 노드를 LLM 분류로 정리.

Usage:
    # 전체 dry-run (변경 없이 보고만)
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --dry-run

    # Outcome만 실행
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --entity-type outcome

    # 실행 (실제 노드 병합)
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --force

    # Alias 코드 제안 생성
    PYTHONPATH=./src python3 scripts/consolidate_entities.py --suggest-aliases
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)
```

### Task 3.2: 핵심 함수들

#### `find_unmapped_nodes()` — Neo4j에서 미매핑 노드 조회

```python
async def find_unmapped_nodes(
    client,  # Neo4jClient
    label: str,  # "Outcome" | "Intervention" | "Pathology"
    max_refs: int = 5,  # 연결 수 상한 (빈도 낮은 것만)
) -> list[dict]:
    """SNOMED 없고 빈도 낮은 노드 조회.

    Returns:
        [{"name": str, "ref_count": int, "connected_papers": list[str]}]
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
```

#### `batch_classify()` — LLM 배치 분류

```python
async def batch_classify(
    nodes: list[dict],
    entity_type: str,
    normalizer,
    llm_client,
    batch_size: int = 5,
) -> list[dict]:
    """미매핑 노드를 배치로 LLM 분류.

    동시 처리(asyncio.gather)로 속도 최적화.

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
                node["name"], entity_type, candidates, llm_client
            ))

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for node, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results.append({"name": node["name"], "action": "skip"})
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

    return results
```

#### `merge_node()` — 노드 병합 Cypher

```python
async def merge_node(
    client,
    label: str,
    old_name: str,
    canonical_name: str,
    dry_run: bool = True,
) -> bool:
    """old_name 노드의 모든 관계를 canonical_name 노드로 이전 후 삭제.

    APOC 미사용 — 관계 타입별 명시적 처리.
    """
    # 관계 타입 매핑 (label별)
    rel_config = {
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
                ("TREATS", "Pathology"), ("AFFECTS", "Outcome"),
                ("IS_A", "Intervention"), ("USES_DEVICE", "Implant"),
                ("CAUSES", "Complication"),
            ],
        },
    }

    if dry_run:
        # 관계 수만 보고
        query = f"""
        MATCH (old:{label} {{name: $old_name}})
        OPTIONAL MATCH (old)-[r]-()
        RETURN count(r) AS rel_count
        """
        result = await client.run_query(query, {"old_name": old_name})
        return result[0]["rel_count"] > 0 if result else False

    # 실제 병합: 모든 incoming/outgoing 관계 이전
    for direction, rels in [("incoming", rel_config.get(label, {}).get("incoming", [])),
                             ("outgoing", rel_config.get(label, {}).get("outgoing", []))]:
        for rel_type, other_label in rels:
            if direction == "incoming":
                await client.run_write_query(f"""
                    MATCH (source)-[r:{rel_type}]->(old:{label} {{name: $old_name}})
                    MATCH (canonical:{label} {{name: $canonical_name}})
                    WHERE NOT (source)-[:{rel_type}]->(canonical)
                    CREATE (source)-[nr:{rel_type}]->(canonical)
                    SET nr = properties(r)
                    DELETE r
                """, {"old_name": old_name, "canonical_name": canonical_name})
            else:
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

    return True
```

#### `generate_alias_suggestions()` — 영구 alias 코드 생성

```python
def generate_alias_suggestions(
    classified: list[dict],
    entity_type: str,
) -> str:
    """분류 결과를 entity_normalizer.py에 추가할 코드 스니펫으로 변환.

    Returns:
        복사-붙여넣기 가능한 Python 코드 문자열
    """
    merge_items = [c for c in classified if c["action"] == "merge"]

    # canonical별 그룹화
    by_canonical = {}
    for item in merge_items:
        by_canonical.setdefault(item["canonical"], []).append(item["name"])

    lines = [f"# Auto-suggested aliases for {entity_type.upper()}_ALIASES"]
    lines.append(f"# Generated by consolidate_entities.py")
    lines.append("")

    for canonical, aliases in sorted(by_canonical.items()):
        lines.append(f'"{canonical}": [')
        lines.append(f'    ...,  # existing aliases')
        for alias in sorted(aliases):
            lines.append(f'    "{alias}",  # NEW (auto-classified)')
        lines.append('],')

    return "\n".join(lines)
```

### Task 3.3: CLI 메인

```python
async def main():
    parser = argparse.ArgumentParser(description="Entity Consolidation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--entity-type", choices=["outcome", "intervention", "pathology"])
    parser.add_argument("--suggest-aliases", action="store_true")
    parser.add_argument("--max-refs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    if not args.dry_run and not args.force:
        print("Use --dry-run or --force")
        return

    # 초기화
    neo4j_client = Neo4jClient()
    await neo4j_client.connect()
    normalizer = EntityNormalizer()
    llm_client = ClaudeClient()  # 또는 환경변수 기반

    entity_types = [args.entity_type] if args.entity_type else ["outcome", "intervention", "pathology"]
    label_map = {"outcome": "Outcome", "intervention": "Intervention", "pathology": "Pathology"}

    for entity_type in entity_types:
        label = label_map[entity_type]
        print(f"\n{'='*60}")
        print(f"Processing {label}")
        print(f"{'='*60}")

        # 1. 미매핑 노드 조회
        nodes = await find_unmapped_nodes(neo4j_client, label, args.max_refs)
        print(f"Found {len(nodes)} unmapped {label} nodes")

        # 2. LLM 배치 분류
        classified = await batch_classify(
            nodes, entity_type, normalizer, llm_client, args.batch_size
        )

        merge_count = sum(1 for c in classified if c["action"] == "merge")
        new_count = sum(1 for c in classified if c["action"] == "new")
        print(f"  Merge candidates: {merge_count}")
        print(f"  Genuinely new: {new_count}")

        # 3. 병합 실행
        if not args.dry_run:
            for item in classified:
                if item["action"] == "merge":
                    await merge_node(
                        neo4j_client, label, item["name"], item["canonical"],
                        dry_run=False
                    )
            print(f"  Merged: {merge_count} nodes")

        # 4. Alias 코드 제안
        if args.suggest_aliases:
            suggestions = generate_alias_suggestions(classified, entity_type)
            print(f"\n{suggestions}")

    await neo4j_client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Agent 4: 테스트 작성 (agent-tests)

### 새 파일
`tests/test_auto_normalizer.py`

### Task 4.1: Layer 1 테스트

```python
class TestVocabularyHints:
    """EXTRACTION_PROMPT에 vocabulary hints가 포함되는지 테스트."""

    def test_vocabulary_hints_generated(self):
        from builder.unified_pdf_processor import _build_vocabulary_hints
        hints = _build_vocabulary_hints()
        assert "CONTROLLED VOCABULARY" in hints
        assert "VAS" in hints
        assert "TLIF" in hints
        assert "Lumbar Stenosis" in hints

    def test_extraction_prompt_includes_hints(self):
        from builder.unified_pdf_processor import EXTRACTION_PROMPT
        assert "CONTROLLED VOCABULARY" in EXTRACTION_PROMPT
```

### Task 4.2: Layer 2 테스트

```python
class TestDynamicAlias:
    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_register_valid_alias(self, normalizer):
        result = normalizer.register_dynamic_alias("outcome", "Operative Duration", "Operation Time")
        assert result is True
        # 이제 정규화 가능
        norm = normalizer.normalize_outcome("Operative Duration")
        assert norm.normalized == "Operation Time"
        assert norm.confidence == 1.0

    def test_reject_invalid_canonical(self, normalizer):
        result = normalizer.register_dynamic_alias("outcome", "foo", "NonExistent")
        assert result is False

    def test_reject_duplicate(self, normalizer):
        # "VAS score" 이미 alias에 존재
        result = normalizer.register_dynamic_alias("outcome", "VAS", "VAS")
        assert result is False

    def test_does_not_modify_static_aliases(self, normalizer):
        original_count = len(normalizer.OUTCOME_ALIASES)
        normalizer.register_dynamic_alias("outcome", "New Term ABC", "VAS")
        assert len(normalizer.OUTCOME_ALIASES) == original_count


class TestCandidatePreFiltering:
    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_returns_relevant_candidates(self, normalizer):
        candidates = normalizer._get_candidate_canonicals("Operative Duration", "outcome")
        assert "Operation Time" in candidates[:10]

    def test_top_k_limit(self, normalizer):
        candidates = normalizer._get_candidate_canonicals("test", "outcome", top_k=5)
        assert len(candidates) <= 5


class TestClassifyUnmatchedEntity:
    """LLM Mock으로 classify_unmatched_entity 테스트."""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import AsyncMock
        client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_high_confidence_match(self, mock_llm):
        mock_llm.generate_json.return_value = {
            "match": "Operation Time", "confidence": 0.95,
            "reason": "synonym"
        }
        result = await classify_unmatched_entity(
            "Operative Duration", "outcome",
            ["Operation Time", "Blood Loss"], mock_llm
        )
        assert result == ("Operation Time", 0.95)

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self, mock_llm):
        mock_llm.generate_json.return_value = {
            "match": "Blood Loss", "confidence": 0.6, "reason": "weak"
        }
        result = await classify_unmatched_entity(
            "Hemoglobin Drop", "outcome",
            ["Blood Loss", "VAS"], mock_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_genuinely_new(self, mock_llm):
        mock_llm.generate_json.return_value = {
            "match": None, "confidence": 0.0, "reason": "new concept"
        }
        result = await classify_unmatched_entity(
            "Spinal Cord Perfusion Index", "outcome",
            ["SVA", "Lordosis"], mock_llm
        )
        assert result is None


class TestNormalizeWithFallback:
    """RelationshipBuilder._normalize_with_fallback 통합 테스트."""

    @pytest.fixture
    def builder(self):
        from unittest.mock import AsyncMock
        client = AsyncMock()
        normalizer = EntityNormalizer()
        llm = AsyncMock()
        return RelationshipBuilder(client, normalizer, llm_client=llm)

    @pytest.mark.asyncio
    async def test_standard_match_no_llm(self, builder):
        """표준 정규화 성공 시 LLM 호출 없음."""
        result = await builder._normalize_with_fallback("VAS", "outcome")
        assert result.normalized == "VAS"
        assert result.confidence >= 1.0
        builder.llm_client.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_fallback_on_failure(self, builder):
        """표준 정규화 실패 시 LLM 폴백."""
        builder.llm_client.generate_json.return_value = {
            "match": "Operation Time", "confidence": 0.92, "reason": "synonym"
        }
        result = await builder._normalize_with_fallback(
            "Total surgical duration", "outcome"
        )
        assert result.normalized == "Operation Time"
        assert "llm_classified" in result.method

    @pytest.mark.asyncio
    async def test_rate_limit(self, builder):
        """논문당 LLM 호출 수 제한."""
        builder._llm_call_limit = 2
        builder.llm_client.generate_json.return_value = {
            "match": None, "confidence": 0.0, "reason": "new"
        }
        for _ in range(3):
            await builder._normalize_with_fallback("Unknown Term", "outcome")
        # 3번째 호출에서는 LLM이 호출되지 않아야 함
        assert builder.llm_client.generate_json.call_count == 2

    @pytest.mark.asyncio
    async def test_no_llm_client_graceful(self):
        """LLM client 없이도 정상 동작."""
        client = AsyncMock()
        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer, llm_client=None)
        result = await builder._normalize_with_fallback("Unknown XYZ", "outcome")
        assert result.confidence == 0.0  # 매칭 실패, 하지만 에러 없음
```

---

## 구현 순서 (팀 에이전트 병렬화)

```
Phase 1 (병렬):
  agent-layer1  → Task 1.1, 1.2 (프롬프트 수정)
  agent-layer2  → Task 2.1, 2.2 (EntityNormalizer 메서드 추가)
  agent-tests   → Task 4.1, 4.2 (Layer 1+2 테스트)

Phase 2 (순차, Layer 2가 Layer 1에 의존):
  agent-layer2  → Task 2.3, 2.4, 2.5 (LLM 분류 + fallback + 서버 연결)

Phase 3 (병렬):
  agent-layer3  → Task 3.1~3.3 (배치 스크립트)
  agent-tests   → Task 4.2 나머지 (통합 테스트)

Phase 4 (순차):
  리더           → 전체 테스트 + 문서 업데이트 + 버전 변경
```

## 검증 체크리스트

1. `PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q` → 기존 1423 + 신규 ~15개 통과
2. `PYTHONPATH=./src python3 -c "from builder.unified_pdf_processor import EXTRACTION_PROMPT; assert 'CONTROLLED VOCABULARY' in EXTRACTION_PROMPT"`
3. `PYTHONPATH=./src python3 scripts/consolidate_entities.py --dry-run` → 미매핑 노드 분류 보고서 출력
4. 실제 미매핑 Outcome 10개로 LLM 분류 정확도 수동 검증

## 버전 변경

- `v1.20.0`: Auto Normalizer Expansion (3-Layer 방어 체계)
- 동기화: `src/__init__.py`, `pyproject.toml`, `CLAUDE.md`, `.env.example`, `docs/CHANGELOG.md`
