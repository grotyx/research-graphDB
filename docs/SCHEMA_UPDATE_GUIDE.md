# Schema, Taxonomy, SNOMED-CT 업데이트 가이드

> **버전**: v7.14.15 | **최종 수정**: 2026-01-13

이 문서는 Spine GraphRAG 시스템의 스키마, Taxonomy, SNOMED-CT 코드를 업데이트하는 전체 과정을 설명합니다.

---

## 1. 개요

### 업데이트 범위

| 구성 요소 | 설명 | 소스 파일 |
|----------|------|----------|
| **Schema** | Neo4j 노드/관계 제약조건, 인덱스 | `src/graph/types/schema.py` |
| **Taxonomy** | Intervention 계층 구조 (IS_A 관계) | `src/graph/types/schema.py` |
| **SNOMED-CT** | 의학 용어 코드 매핑 | `src/ontology/spine_snomed_mappings.py` |
| **Entity Normalizer** | 용어 정규화 (별칭 → 정규 이름) | `src/graph/entity_normalizer.py` |

### 업데이트 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  1. 코드 수정 (Python 파일)                                   │
│     ├── entity_normalizer.py: 별칭 추가                      │
│     ├── spine_snomed_mappings.py: SNOMED 코드 추가           │
│     └── schema.py: Taxonomy MERGE 쿼리 추가                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Neo4j 초기화 스크립트 실행                                │
│     python scripts/init_neo4j.py                            │
│     ├── 제약조건/인덱스 생성                                  │
│     ├── Taxonomy 노드 MERGE                                  │
│     └── SNOMED enrichment 쿼리 실행                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. v7.14.2 추가 업데이트 적용                                │
│     python scripts/update_schema_taxonomy.py                 │
│     ├── BELIF, Facetectomy, Stereotactic Navigation 추가    │
│     └── IS_A 관계 생성                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 검증                                                     │
│     ├── 노드 존재 확인                                        │
│     ├── IS_A 관계 확인                                        │
│     └── SNOMED 코드 확인                                      │
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

### Step 3: v7.14.2 Taxonomy 업데이트

```bash
# 통합 업데이트 스크립트 실행
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py

# 또는 확인 없이 강제 실행
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --force
```

### Step 4: 검증

```bash
# Neo4j Browser에서 확인
# http://localhost:7474

# 또는 Cypher 쿼리로 확인
PYTHONPATH=./src python3 -c "
from neo4j import GraphDatabase
import os

driver = GraphDatabase.driver(
    'bolt://localhost:7687',
    auth=('neo4j', os.getenv('NEO4J_PASSWORD', 'spineGraph2024'))
)

with driver.session() as session:
    result = session.run('''
        MATCH (i:Intervention)
        WHERE i.name IN [\"BELIF\", \"Facetectomy\", \"Stereotactic Navigation\"]
        OPTIONAL MATCH (i)-[:IS_A]->(parent:Intervention)
        RETURN i.name, i.snomed_code, parent.name
    ''')
    for record in result:
        print(f'{record[0]}: SNOMED={record[1]}, Parent={record[2]}')

driver.close()
"
```

---

## 3. 자동화 (Cron Job)

### 매주 일요일 새벽 3시 실행

```bash
# crontab 편집
crontab -e

# 다음 줄 추가
0 3 * * 0 cd /Users/sangminpark/Documents/rag_research && /usr/bin/python3 scripts/update_schema_taxonomy.py --force --quiet >> logs/schema_update.log 2>&1
```

### 3일마다 실행

```bash
# crontab에 추가
0 3 */3 * * cd /Users/sangminpark/Documents/rag_research && /usr/bin/python3 scripts/update_schema_taxonomy.py --force --quiet >> logs/schema_update.log 2>&1
```

### Launchd (macOS 권장)

`~/Library/LaunchAgents/com.spine-graphrag.schema-update.plist` 파일 생성:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.spine-graphrag.schema-update</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/sangminpark/Documents/rag_research/scripts/update_schema_taxonomy.py</string>
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
    <string>/Users/sangminpark/Documents/rag_research/logs/schema_update.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/sangminpark/Documents/rag_research/logs/schema_update_error.log</string>
</dict>
</plist>
```

Launchd 활성화:

```bash
# 로드
launchctl load ~/Library/LaunchAgents/com.spine-graphrag.schema-update.plist

# 상태 확인
launchctl list | grep spine-graphrag

# 즉시 실행 (테스트)
launchctl start com.spine-graphrag.schema-update

# 언로드 (비활성화)
launchctl unload ~/Library/LaunchAgents/com.spine-graphrag.schema-update.plist
```

---

## 4. 스크립트 옵션

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

### 5.4 SNOMED Enrichment 추가 (schema.py)

```python
# src/graph/types/schema.py - get_enrich_snomed_cypher()

queries.append("""
MATCH (i:Intervention {name: 'New Surgery'})
SET i.snomed_code = '900000000000XXX',
    i.snomed_term = 'New Surgery',
    i.is_extension = true
RETURN 'New Surgery SNOMED applied'
""")
```

### 5.5 업데이트 스크립트에 추가 (update_schema_taxonomy.py)

```python
# scripts/update_schema_taxonomy.py

V7_14_2_TAXONOMY_UPDATES.append({
    "name": "New Surgery",
    "query": """
        MERGE (ns:Intervention {name: "New Surgery"})
        SET ns.full_name = "Novel Surgical Procedure",
            ns.category = "decompression",
            ns.snomed_code = "900000000000XXX",
            ns.is_extension = true
        WITH ns
        MATCH (parent:Intervention {name: "Decompression Surgery"})
        MERGE (ns)-[:IS_A {level: 2}]->(parent)
        RETURN ns.name as name, "created/updated" as status
    """,
    "parent": "Decompression Surgery",
    "snomed_code": "900000000000XXX"
})
```

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

### 스키마 초기화 실패

```bash
# Mock 모드로 실행되는 경우 neo4j 패키지 설치 필요
pip3 install neo4j

# 환경 변수 확인
cat .env | grep NEO4J
```

---

## 7. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|-----|------|----------|
| 2025-12-26 | v7.14.2 | Facetectomy, BELIF, Stereotactic Navigation 추가 |
| 2025-12-25 | v7.14.1 | 별칭 대폭 확장 (150+ 신규) |
| 2025-12-25 | v7.14 | BED→UBE, BE-TLIF→BELIF 통합 |

---

## 8. Claude Code 프롬프트

아래 프롬프트를 Claude Code에서 실행하면 전체 업데이트 과정을 자동으로 수행합니다.

### 8.1 전체 업데이트 프롬프트 (권장)

```
Schema, Taxonomy, SNOMED-CT 전체 업데이트를 실행해줘.

다음 순서로 진행해줘:

1. **현재 상태 분석**
   - Neo4j Docker 상태 확인 (docker-compose ps)
   - 현재 DB의 Intervention/Pathology/Outcome 노드 수 확인
   - data/extracted/ 폴더의 JSON 파일들에서 추출된 용어 분석
   - 매핑되지 않은 용어 목록 추출

2. **갭 분석**
   - entity_normalizer.py의 INTERVENTION_ALIASES와 비교
   - spine_snomed_mappings.py의 SNOMED 매핑과 비교
   - 누락된 별칭, SNOMED 코드 식별

3. **코드 업데이트** (필요시)
   - entity_normalizer.py: 누락된 별칭 추가
   - spine_snomed_mappings.py: 누락된 SNOMED 매핑 추가
   - schema.py: Taxonomy MERGE 쿼리 추가

4. **Neo4j 업데이트**
   - init_neo4j.py 실행
   - update_schema_taxonomy.py --force 실행

5. **검증**
   - 신규 노드 생성 확인
   - IS_A 관계 확인
   - SNOMED 코드 적용 확인

6. **문서 업데이트**
   - CHANGELOG.md 업데이트
   - CLAUDE.md 버전 업데이트
```

### 8.2 분석만 수행 (변경 없음)

```
Neo4j 데이터베이스와 추출된 논문 데이터를 분석해서
Schema, Taxonomy, SNOMED-CT 업데이트가 필요한 항목을 정리해줘.

다음을 확인해줘:
1. data/extracted/ 폴더의 JSON 파일에서 추출된 interventions, outcomes, pathologies 목록
2. 현재 entity_normalizer.py에 등록된 별칭과 비교
3. spine_snomed_mappings.py에 등록된 SNOMED 매핑과 비교
4. Neo4j DB의 현재 노드 상태

결과를 표로 정리해줘:
- 매핑된 용어 수 / 비율
- 누락된 용어 목록
- 추천하는 별칭 추가 사항
```

### 8.3 Neo4j 업데이트만 실행

```
Neo4j 데이터베이스에 최신 스키마와 Taxonomy를 적용해줘.

다음 명령어를 순서대로 실행해줘:
1. docker-compose ps (Neo4j 상태 확인)
2. PYTHONPATH=./src python3 scripts/init_neo4j.py
3. PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --force
4. 업데이트 결과 검증 (BELIF, Facetectomy, Stereotactic Navigation 확인)
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
2. src/ontology/spine_snomed_mappings.py - SNOMED 매핑 추가
3. src/graph/types/schema.py - Taxonomy MERGE 및 SNOMED enrichment 추가
4. scripts/update_schema_taxonomy.py - V7_XX_TAXONOMY_UPDATES에 추가

그리고 Neo4j 업데이트도 실행해줘.
```

### 8.5 주기적 점검 프롬프트

```
Spine GraphRAG 시스템의 용어 정규화 상태를 점검해줘.

1. **매핑률 확인**
   - Neo4j에서 SNOMED 코드가 있는 노드 비율 확인
   - Intervention, Pathology, Outcome 각각의 매핑률

2. **최근 추가된 논문 분석**
   - data/extracted/에서 최근 7일 내 생성된 JSON 파일 확인
   - 새로 등장한 용어가 있는지 확인

3. **업데이트 필요 여부 판단**
   - 매핑률이 70% 미만인 카테고리가 있으면 알려줘
   - 신규 용어가 3개 이상 발견되면 알려줘

4. **권장 조치**
   - 업데이트가 필요하면 구체적인 추가 항목 제시
   - 필요없으면 "현재 상태 양호" 보고
```

### 8.6 버전 업그레이드 프롬프트

```
Spine GraphRAG를 v7.14.2에서 v7.15로 업그레이드 준비해줘.

다음을 수행해줘:
1. 현재 버전의 모든 변경사항이 Neo4j에 적용되었는지 확인
2. CHANGELOG.md에 v7.15 섹션 추가 (내용은 비워둠)
3. CLAUDE.md 버전을 7.15로 업데이트
4. 업그레이드 준비 완료 확인
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

```
# 먼저 dry-run으로 테스트
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --dry-run

# 문제없으면 실제 실행
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --force
```

### 롤백 방법

Neo4j 데이터는 MERGE를 사용하므로 기존 데이터가 삭제되지 않습니다.
문제 발생 시 잘못 추가된 노드만 삭제하면 됩니다:

```cypher
// 특정 노드 삭제 (신중하게!)
MATCH (i:Intervention {name: "잘못된노드"})
DETACH DELETE i
```

---

## 10. 관련 문서

- [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) - 스키마 전체 정의
- [TERMINOLOGY_ONTOLOGY.md](TERMINOLOGY_ONTOLOGY.md) - SNOMED-CT 매핑 상세
- [CHANGELOG.md](CHANGELOG.md) - 전체 변경 이력
