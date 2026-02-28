# Schema, Taxonomy, SNOMED-CT 업데이트 가이드

> **버전**: v1.24.0 | **최종 수정**: 2026-02-28

이 문서는 Spine GraphRAG 시스템의 스키마, Taxonomy, SNOMED-CT 코드를 업데이트하는 전체 과정을 설명합니다.

---

## 1. 개요

### 업데이트 범위

| 구성 요소 | 설명 | 소스 파일 |
|----------|------|----------|
| **Schema** | Neo4j 노드/관계 제약조건, 인덱스 | `src/graph/types/schema.py` |
| **Taxonomy** | 4개 엔티티 IS_A 계층 구조 | `src/graph/types/schema.py`, `src/graph/taxonomy_manager.py` |
| **SNOMED-CT** | 의학 용어 코드 매핑 (Single Source of Truth) | `src/ontology/spine_snomed_mappings.py` |
| **SNOMED Enricher** | SNOMED 업데이트, TREATS 백필, Anatomy 정리 | `src/graph/snomed_enricher.py` |
| **Entity Normalizer** | 용어 정규화 (별칭 → 정규 이름) | `src/graph/entity_normalizer.py` |
| **Ontology Builder** | parent_code 기반 IS_A 계층 일괄 구축 | `scripts/build_ontology.py` |
| **Ontology Repairer** | 온톨로지 무결성 수복 (IS_A/SNOMED/TREATS) | `scripts/repair_ontology.py` |
| **SNOMED Proposer** | 미등록 용어 LLM 매핑 제안 | `src/ontology/snomed_proposer.py` |

### IS_A 계층 구조 (v1.24.0)

v1.24.0부터 4개 엔티티 타입 모두에 IS_A 계층이 적용됩니다:

| 엔티티 타입 | IS_A 루트 수 | 총 IS_A 관계 | 소스 |
|------------|-------------|-------------|------|
| Intervention | ~15 | 기존 Taxonomy + SNOMED parent_code | `schema.py` + `build_ontology.py` |
| Pathology | ~12 | SNOMED parent_code 기반 | `build_ontology.py` |
| Outcome | ~11 | SNOMED parent_code 기반 | `build_ontology.py` |
| Anatomy | ~5 | SNOMED parent_code + region 기반 | `build_ontology.py` |

### 업데이트 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  1. 코드 수정 (Python 파일)                                   │
│     ├── entity_normalizer.py: 별칭 추가                      │
│     ├── spine_snomed_mappings.py: SNOMED 코드 추가           │
│     └── schema.py: Taxonomy MERGE 쿼리 추가                  │
│     (※ SNOMED Cypher는 자동 생성 — 수동 추가 불필요)          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Neo4j 초기화 스크립트 실행                                │
│     python scripts/init_neo4j.py                            │
│     ├── 제약조건/인덱스 생성                                  │
│     ├── Taxonomy 노드 MERGE                                  │
│     └── SNOMED enrichment 쿼리 실행 (자동 생성)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 통합 보강 스크립트 실행                                    │
│     python scripts/enrich_graph_snomed.py --force            │
│     ├── Anatomy 정리 (다분절 범위 분리, 비특이적 플래그)      │
│     ├── SNOMED 코드 적용 (4개 엔티티 타입)                    │
│     ├── TREATS 관계 백필 (리뷰논문 필터)                      │
│     └── 커버리지 리포트 출력                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 온톨로지 계층 구축 (v1.24.0)                              │
│     python scripts/build_ontology.py --force                 │
│     ├── Pathology IS_A 계층 구축 (parent_code 기반)          │
│     ├── Outcome IS_A 계층 구축 (parent_code 기반)            │
│     ├── Anatomy IS_A 계층 구축 (parent_code 기반)            │
│     └── IS_A 관계 통계 리포트                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 온톨로지 무결성 수복 (선택, v1.24.0)                      │
│     python scripts/repair_ontology.py --dry-run              │
│     ├── IS_A 누락 관계 복구                                   │
│     ├── SNOMED 코드 누락 노드 보강                            │
│     ├── TREATS backfill                                       │
│     └── 순환 참조 / 중복 감지                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  6. 검증                                                     │
│     ├── SNOMED 커버리지 확인 (report 명령)                    │
│     ├── IS_A 관계 수 확인 (4개 엔티티 타입)                   │
│     ├── TREATS 관계 수 확인                                   │
│     └── 온톨로지 무결성 검증 (repair_ontology report)         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 수동 업데이트 방법

### Step 1: Neo4j Docker 확인

```bash
# Docker 컨테이너 상태 확인
docker-compose ps

# 실행 중이 아니면 시작
docker-compose up -d

# 약 30초 대기 후 다음 단계 진행
```

### Step 2: 스키마 초기화

```bash
# 프로젝트 루트에서 실행
PYTHONPATH=./src python3 scripts/init_neo4j.py
```

**출력 예시:**
```
[1/4] Connecting to Neo4j...
✅ Connected successfully
[2/4] Testing connection...
✅ Connection OK
[3/4] Initializing schema...
   - Creating constraints...
   - Creating indexes...
   - Loading taxonomy data...
✅ Schema initialized successfully
[4/5] Enriching with SNOMED codes...
   - SNOMED batch 1/9 applied
   ...
✅ SNOMED codes enriched
```

### Step 3: SNOMED/TREATS/Anatomy 통합 보강

```bash
# 먼저 dry-run으로 미리보기
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --dry-run

# 문제없으면 실제 실행
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --force
```

이 스크립트는 다음을 순서대로 수행합니다:
1. **Anatomy 정리**: 다분절 범위 분리 (L2-4 → L2-3, L3-4), 비특이적 용어 플래그
2. **SNOMED 적용**: 4개 엔티티 타입 (Intervention, Pathology, Outcome, Anatomy)에 SNOMED 코드 적용
3. **TREATS 백필**: Paper→Intervention + Paper→Pathology 패턴으로 TREATS 관계 자동 생성
4. **커버리지 리포트**: 매핑 현황 출력

### Step 4: 온톨로지 IS_A 계층 구축 (v1.24.0)

```bash
# Dry-run (쿼리 확인만)
PYTHONPATH=./src python3 scripts/build_ontology.py --dry-run

# 실행
PYTHONPATH=./src python3 scripts/build_ontology.py --force

# 특정 엔티티 타입만
PYTHONPATH=./src python3 scripts/build_ontology.py --entity-type Pathology --force

# IS_A 리포트
PYTHONPATH=./src python3 scripts/build_ontology.py report
```

### Step 5: 온톨로지 무결성 수복 (선택)

```bash
# Dry-run (이슈 리포트만)
PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run

# 수복 실행
PYTHONPATH=./src python3 scripts/repair_ontology.py --force

# 특정 엔티티 타입만
PYTHONPATH=./src python3 scripts/repair_ontology.py --entity-type Pathology --force

# 현재 상태 리포트
PYTHONPATH=./src python3 scripts/repair_ontology.py report
```

### Step 6: 검증

```bash
# 방법 1: 통합 리포트 (권장)
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py report

# 방법 2: 온톨로지 리포트
PYTHONPATH=./src python3 scripts/build_ontology.py report

# 방법 3: Neo4j Browser에서 직접 확인
# http://localhost:7474

# SNOMED 커버리지
# MATCH (n) WHERE n:Intervention OR n:Pathology OR n:Outcome OR n:Anatomy
# WITH labels(n)[0] as label, count(n) as total,
#      sum(CASE WHEN n.snomed_code IS NOT NULL THEN 1 ELSE 0 END) as mapped
# RETURN label, total, mapped, round(100.0*mapped/total, 1) as pct

# IS_A 계층 (4개 엔티티 타입)
# MATCH (n)-[:IS_A]->(parent)
# RETURN labels(n)[0] as type, count(*) as is_a_count
# ORDER BY is_a_count DESC

# TREATS 관계 수
# MATCH ()-[r:TREATS]->() RETURN count(r)
```

---

## 3. 자동화 (Cron Job)

### 매주 일요일 새벽 3시 실행

```bash
# crontab 편집
crontab -e

# 다음 줄 추가 (통합 보강 스크립트)
0 3 * * 0 cd /Users/sangminpark/Documents/rag_research && PYTHONPATH=./src /usr/bin/python3 scripts/enrich_graph_snomed.py --force --quiet >> logs/snomed_enrich.log 2>&1

# 온톨로지 계층 (월 1회, 매월 1일)
0 4 1 * * cd /Users/sangminpark/Documents/rag_research && PYTHONPATH=./src /usr/bin/python3 scripts/build_ontology.py --force >> logs/build_ontology.log 2>&1
```

### Launchd (macOS 권장)

`~/Library/LaunchAgents/com.spine-graphrag.snomed-enrich.plist` 파일 생성:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.spine-graphrag.snomed-enrich</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/sangminpark/Documents/rag_research/scripts/enrich_graph_snomed.py</string>
        <string>--force</string>
        <string>--quiet</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/sangminpark/Documents/rag_research</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/sangminpark/Documents/rag_research/src</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/sangminpark/Documents/rag_research/logs/snomed_enrich.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/sangminpark/Documents/rag_research/logs/snomed_enrich_error.log</string>
</dict>
</plist>
```

Launchd 활성화:

```bash
# 로드
launchctl load ~/Library/LaunchAgents/com.spine-graphrag.snomed-enrich.plist

# 상태 확인
launchctl list | grep spine-graphrag

# 즉시 실행 (테스트)
launchctl start com.spine-graphrag.snomed-enrich

# 언로드 (비활성화)
launchctl unload ~/Library/LaunchAgents/com.spine-graphrag.snomed-enrich.plist
```

---

## 4. 스크립트 옵션

### enrich_graph_snomed.py (통합 보강)

SNOMED 코드 적용, TREATS 관계 백필, Anatomy 정리를 하나의 통합 CLI로 실행합니다.

```bash
# 전체 파이프라인 (dry-run)
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --dry-run

# 전체 파이프라인 (실행)
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --force

# 개별 단계
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py snomed --dry-run
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py treats --dry-run
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py anatomy-cleanup --dry-run
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py report
```

| 명령 | 설명 |
|-----|------|
| `all` (기본) | anatomy-cleanup → snomed → treats → report 전체 실행 |
| `snomed` | 4개 엔티티 타입에 SNOMED 코드 적용 |
| `treats` | TREATS 관계 백필 (리뷰논문 필터 포함) |
| `anatomy-cleanup` | 다분절 범위 분리, 비특이적 용어 플래그 |
| `report` | 커버리지 리포트 출력 |

| 옵션 | 설명 |
|-----|------|
| `--dry-run` | 변경 없이 미리보기 |
| `--force`, `-f` | 확인 없이 실행 |
| `--quiet`, `-q` | 최소 출력 |

### build_ontology.py (v1.24.0, IS_A 계층 구축)

spine_snomed_mappings.py의 parent_code를 기반으로 IS_A 계층을 Neo4j에 적용합니다.

```bash
# Dry-run
PYTHONPATH=./src python3 scripts/build_ontology.py --dry-run

# 실행
PYTHONPATH=./src python3 scripts/build_ontology.py --force

# 특정 엔티티 타입만
PYTHONPATH=./src python3 scripts/build_ontology.py --entity-type Pathology --force

# 리포트
PYTHONPATH=./src python3 scripts/build_ontology.py report
```

| 옵션 | 설명 |
|-----|------|
| `--dry-run` | 변경 없이 쿼리 확인 |
| `--force`, `-f` | 확인 없이 실행 |
| `--entity-type TYPE` | 특정 엔티티 타입만 (Intervention, Pathology, Outcome, Anatomy) |
| `report` | IS_A 현황 리포트 |

### repair_ontology.py (v1.24.0, 온톨로지 수복)

온톨로지 무결성 이슈를 감지하고 수복합니다.

```bash
# Dry-run
PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run

# 실행
PYTHONPATH=./src python3 scripts/repair_ontology.py --force

# 특정 엔티티 타입만
PYTHONPATH=./src python3 scripts/repair_ontology.py --entity-type Pathology --force

# 리포트
PYTHONPATH=./src python3 scripts/repair_ontology.py report
```

| 옵션 | 설명 |
|-----|------|
| `--dry-run` | 이슈 리포트만 (수복하지 않음) |
| `--force`, `-f` | 확인 없이 수복 실행 |
| `--entity-type TYPE` | 특정 엔티티 타입만 |
| `report` | 현재 상태 리포트 |

### update_schema_taxonomy.py

| 옵션 | 설명 |
|-----|------|
| `--dry-run` | 실제 변경 없이 검증만 수행 |
| `--force`, `-f` | 확인 없이 강제 실행 |
| `--quiet`, `-q` | 최소 출력 (cron용) |

### init_neo4j.py

| 옵션 | 설명 |
|-----|------|
| `--skip-taxonomy` | Taxonomy 데이터 로드 스킵 |
| `--skip-snomed` | SNOMED-CT 코드 보강 스킵 |
| `--reset` | 데이터베이스 초기화 (모든 데이터 삭제) |
| `--verify-apoc` | APOC 플러그인 설치 확인 |

---

## 5. 신규 수술법/용어 추가 방법

### 5.1 별칭 추가 (entity_normalizer.py)

```python
# src/graph/entity_normalizer.py

INTERVENTION_ALIASES = {
    # 기존 항목에 별칭 추가
    "UBE": [
        "BESS", "Biportal", "UBE discectomy",
        "BED",  # 신규 추가
        "Biportal Endoscopic Discectomy",  # 신규 추가
    ],

    # 신규 수술법 추가
    "New Surgery": [
        "new surgery",
        "NS",
        "Novel Procedure",
    ],
}
```

### 5.2 SNOMED 코드 추가 (spine_snomed_mappings.py)

```python
# src/ontology/spine_snomed_mappings.py

SPINE_INTERVENTION_SNOMED = {
    # 신규 수술법 SNOMED 매핑
    "New Surgery": SNOMEDMapping(
        code="900000000000XXX",  # Extension 코드
        term="New Surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # 부모 SNOMED 코드
        is_extension=True,
        synonyms=["NS", "Novel Procedure"],
        abbreviations=["NS"],
        korean_term="신규 수술",
        notes="설명",
    ),
}
```

### 5.3 Taxonomy 추가 (schema.py)

```python
# src/graph/types/schema.py - get_init_taxonomy_cypher()

# Taxonomy MERGE 추가
MERGE (new_surgery:Intervention {
    name: 'New Surgery',
    full_name: 'Novel Surgical Procedure',
    category: 'decompression',
    aliases: ['NS', 'Novel Procedure']
})
MERGE (new_surgery)-[:IS_A {level: 2}]->(parent_node)
```

### 5.4 SNOMED Enrichment (자동)

`schema.py:get_enrich_snomed_cypher()`는 `spine_snomed_mappings.py`의 621개 매핑으로부터 **자동 생성**됩니다.
`spine_snomed_mappings.py`에 매핑을 추가하면 `init_neo4j.py` 실행 시 자동으로 Cypher가 생성됩니다.

> **참고**: 수동으로 `schema.py`에 SNOMED 쿼리를 추가할 필요가 없습니다.

### 5.5 IS_A 계층 자동 반영 (v1.24.0)

`spine_snomed_mappings.py`에 `parent_code`를 지정하면 `build_ontology.py` 실행 시 IS_A 관계가 자동 생성됩니다:

```python
# parent_code가 지정된 매핑 → build_ontology.py가 IS_A 자동 생성
"Lumbar Stenosis": SNOMEDMapping(
    code="900000000000250",
    parent_code="900000000000248",  # Spinal Stenosis
    ...
)
# → Neo4j: (Lumbar Stenosis)-[:IS_A]->(Spinal Stenosis) 자동 생성
```

### 5.6 미등록 용어 자동 감지 (v1.24.0)

논문 임포트 시 `entity_normalizer.py`에 등록되지 않은 용어가 발견되면:

1. **자동 감지**: relationship_builder가 미등록 용어를 큐에 저장
2. **LLM 제안**: `snomed_proposer.py`가 SNOMED 매핑을 자동 제안
3. **자동/수동 분류**: confidence ≥ 0.9 → 자동 적용, 0.7-0.9 → 사용자 승인, < 0.7 → 수동 검토

---

## 6. 문제 해결

### Neo4j 연결 실패

```bash
# Docker 상태 확인
docker-compose ps

# Neo4j 로그 확인
docker-compose logs neo4j

# Neo4j 재시작
docker-compose restart neo4j
```

### 패키지 누락

```bash
# neo4j 패키지 설치
pip3 install neo4j

# 의존성 전체 설치
pip3 install -r requirements.txt
```

### IS_A 순환 참조 감지 (v1.24.0)

```bash
# repair_ontology.py가 순환 참조를 감지하고 리포트
PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run

# Neo4j에서 직접 확인
# MATCH path = (n)-[:IS_A*2..5]->(n) RETURN path LIMIT 10
```

### 온톨로지 계층 불일치

```bash
# 온톨로지 리포트 확인
PYTHONPATH=./src python3 scripts/build_ontology.py report

# repair_ontology.py로 수복
PYTHONPATH=./src python3 scripts/repair_ontology.py --force
```

---

## 7. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|-----|------|----------|
| 2026-02-28 | v1.24.0 | 4개 엔티티 IS_A 계층, build_ontology.py/repair_ontology.py/snomed_proposer.py 추가, graph_traversal_search.py 검색, SNOMED 621개 |
| 2026-02-14 | v1.16.3 | 통합 스크립트 enrich_graph_snomed.py, schema.py SNOMED 동적 생성, TREATS 백필, Anatomy 정리 |
| 2025-12-26 | v1.14.2 | Facetectomy, BELIF, Stereotactic Navigation 추가 |
| 2025-12-25 | v1.14.1 | 별칭 대폭 확장 (150+ 신규) |
| 2025-12-25 | v1.14 | BED→UBE, BE-TLIF→BELIF 통합 |

---

## 8. Claude Code 프롬프트

아래 프롬프트를 Claude Code에서 실행하면 전체 업데이트 과정을 자동으로 수행합니다.

### 8.1 전체 업데이트 프롬프트 (권장)

```
Schema, Taxonomy, SNOMED-CT, Ontology 전체 업데이트를 실행해줘.

다음 순서로 진행해줘:

1. **현재 상태 분석**
   - Neo4j Docker 상태 확인 (docker-compose ps)
   - enrich_graph_snomed.py report로 현재 SNOMED 커버리지 확인
   - build_ontology.py report로 IS_A 계층 현황 확인
   - data/extracted/ 폴더의 JSON 파일에서 추출된 용어 분석
   - 매핑되지 않은 용어 목록 추출

2. **갭 분석**
   - entity_normalizer.py의 ALIASES와 비교
   - spine_snomed_mappings.py의 SNOMED 매핑과 비교
   - 누락된 별칭, SNOMED 코드 식별

3. **코드 업데이트** (필요시)
   - entity_normalizer.py: 누락된 별칭 추가
   - spine_snomed_mappings.py: 누락된 SNOMED 매핑 추가 (parent_code 포함)
   - schema.py: Taxonomy MERGE 쿼리 추가 (SNOMED Cypher는 자동 생성)

4. **Neo4j 업데이트**
   - init_neo4j.py 실행 (스키마 + Taxonomy + SNOMED 기본 적용)
   - enrich_graph_snomed.py --force (Anatomy 정리 + SNOMED + TREATS + 리포트)
   - build_ontology.py --force (4개 엔티티 IS_A 계층 구축)

5. **검증**
   - enrich_graph_snomed.py report 실행
   - build_ontology.py report 실행
   - repair_ontology.py --dry-run 실행 (이슈 확인)

6. **문서 업데이트**
   - CHANGELOG.md 업데이트
   - CLAUDE.md 버전 업데이트
```

### 8.2 분석만 수행 (변경 없음)

```
Neo4j 데이터베이스와 추출된 논문 데이터를 분석해서
Schema, Taxonomy, SNOMED-CT, Ontology 업데이트가 필요한 항목을 정리해줘.

다음을 확인해줘:
1. data/extracted/ 폴더의 JSON 파일에서 추출된 interventions, outcomes, pathologies 목록
2. 현재 entity_normalizer.py에 등록된 별칭과 비교
3. spine_snomed_mappings.py에 등록된 SNOMED 매핑과 비교
4. Neo4j DB의 현재 노드 상태 및 IS_A 계층 현황
5. repair_ontology.py --dry-run으로 무결성 이슈 확인

결과를 표로 정리해줘:
- 매핑된 용어 수 / 비율
- IS_A 계층 커버리지 (4개 엔티티 타입별)
- 누락된 용어 목록
- 추천하는 별칭 추가 사항
```

### 8.3 Neo4j 업데이트만 실행

```
Neo4j 데이터베이스에 최신 스키마, SNOMED, Ontology를 적용해줘.

다음 명령어를 순서대로 실행해줘:
1. docker-compose ps (Neo4j 상태 확인)
2. PYTHONPATH=./src python3 scripts/init_neo4j.py (스키마 + Taxonomy)
3. PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --dry-run (미리보기)
4. PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --force (실행)
5. PYTHONPATH=./src python3 scripts/build_ontology.py --dry-run (IS_A 미리보기)
6. PYTHONPATH=./src python3 scripts/build_ontology.py --force (IS_A 구축)
7. PYTHONPATH=./src python3 scripts/build_ontology.py report (검증)
```

### 8.4 신규 수술법 추가

```
새로운 수술법 "[수술명]"을 시스템에 추가해줘.

다음 정보를 바탕으로:
- 정규 이름: [정규 이름]
- 별칭: [별칭1], [별칭2], ...
- 카테고리: fusion / decompression / endoscopic / fixation / osteotomy
- 부모 수술법: [부모 Taxonomy 노드 이름]
- SNOMED 코드: [코드 또는 "extension 코드 필요"]

다음 파일들을 업데이트해줘:
1. src/graph/entity_normalizer.py - INTERVENTION_ALIASES에 별칭 추가
2. src/ontology/spine_snomed_mappings.py - SNOMED 매핑 추가 (parent_code 포함)
3. src/graph/types/schema.py - Taxonomy MERGE 쿼리 추가

그리고 Neo4j 업데이트도 실행해줘:
1. init_neo4j.py (Taxonomy + SNOMED 기본 적용)
2. enrich_graph_snomed.py --force (통합 보강)
3. build_ontology.py --force (IS_A 계층 구축)
```

### 8.5 주기적 점검 프롬프트

```
Spine GraphRAG 시스템의 용어 정규화 및 온톨로지 상태를 점검해줘.

1. **매핑률 확인**
   - enrich_graph_snomed.py report 실행
   - Intervention, Pathology, Outcome, Anatomy 각각의 SNOMED 커버리지

2. **IS_A 계층 확인**
   - build_ontology.py report 실행
   - 4개 엔티티 타입별 IS_A 관계 수

3. **무결성 확인**
   - repair_ontology.py --dry-run 실행
   - 이슈가 있으면 자동 수복 실행

4. **최근 추가된 논문 분석**
   - data/extracted/에서 최근 7일 내 생성된 JSON 파일 확인
   - 새로 등장한 용어가 있는지 확인

5. **업데이트 필요 여부 판단**
   - 매핑률이 70% 미만인 카테고리가 있으면 알려줘
   - IS_A 누락이 있으면 알려줘
   - 신규 용어가 3개 이상 발견되면 알려줘

6. **권장 조치**
   - 업데이트가 필요하면 구체적인 추가 항목 제시
   - 필요없으면 "현재 상태 양호" 보고
```

### 8.6 버전 업그레이드 프롬프트

```
Spine GraphRAG를 v[현재버전]에서 v[새버전]으로 업그레이드 준비해줘.

다음을 수행해줘:
1. 현재 버전의 모든 변경사항이 Neo4j에 적용되었는지 확인
   - enrich_graph_snomed.py report 실행
   - build_ontology.py report 실행
2. CHANGELOG.md에 새 버전 섹션 추가 (내용은 비워둠)
3. CLAUDE.md 버전 업데이트
4. 버전 파일 동기화 (src/__init__.py, pyproject.toml, .env.example)
5. 업그레이드 준비 완료 확인
```

---

## 9. 프롬프트 사용 팁

### 단계별 실행 권장

복잡한 업데이트는 한 번에 실행하지 말고 단계별로 실행하세요:

1. 먼저 **분석 프롬프트** (8.2)로 현재 상태 파악
2. 분석 결과를 검토한 후 **업데이트 결정**
3. **전체 업데이트 프롬프트** (8.1) 또는 **부분 업데이트** 실행
4. **검증** 수행

### 안전한 테스트

```bash
# 먼저 dry-run으로 테스트
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --dry-run
PYTHONPATH=./src python3 scripts/build_ontology.py --dry-run
PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run

# 문제없으면 실제 실행
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py --force
PYTHONPATH=./src python3 scripts/build_ontology.py --force
```

### 롤백 방법

Neo4j 데이터는 MERGE를 사용하므로 기존 데이터가 삭제되지 않습니다.
문제 발생 시 잘못 추가된 노드만 삭제하면 됩니다:

```cypher
// 특정 노드 삭제 (신중하게!)
MATCH (i:Intervention {name: "잘못된노드"})
DETACH DELETE i

// 잘못된 IS_A 관계 삭제
MATCH (n:Pathology {name: "X"})-[r:IS_A]->(parent:Pathology {name: "Y"})
DELETE r
```

---

## 10. 관련 문서

- [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) - 스키마 전체 정의
- [TERMINOLOGY_ONTOLOGY.md](TERMINOLOGY_ONTOLOGY.md) - SNOMED-CT 매핑 상세
- [DATA_VALIDATION.md](DATA_VALIDATION.md) - 데이터 무결성 검증 (Phase 6: Ontology Integrity)
- [CHANGELOG.md](CHANGELOG.md) - 전체 변경 이력
