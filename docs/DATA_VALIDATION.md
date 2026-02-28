# Spine GraphRAG - Data Validation (DV) 체크리스트

> **목적**: Neo4j 데이터베이스의 무결성, 완전성, 품질을 검증
> **대상**: 논문 임포트 후, 주간 정기 점검, 또는 데이터 관련 버그 수정 후
> **실행**: Claude Code에서 프롬프트 복사 → 붙여넣기로 실행
> **전제**: Docker Neo4j 컨테이너가 실행 중이어야 합니다 (`docker-compose ps`)

---

## Quick Start

```
docs/DATA_VALIDATION.md의 전체 DV를 실행해줘. 병렬로 처리 가능한 항목은 병렬로 진행해줘.
```

부분 실행:

```
docs/DATA_VALIDATION.md의 Phase 1만 실행해줘.
docs/DATA_VALIDATION.md의 Phase 3만 실행해줘.
```

## Scan Mode (기본)

스캔은 **보고 전용(Report-Only)** 모드로 실행됩니다:
1. 모든 체크를 실행하고 결과를 보고 템플릿으로 출력
2. "Known Accepted Issues" 목록에 있는 항목은 ✅(억제)로 표시하고 건너뜀
3. 신규 발견 항목은 "Open Issues" 섹션에 등록 제안
4. **어떤 파일도 수정하지 않음** — 수정은 별도 "Fix" 단계에서 수행

**수정 워크플로우** (4단계):
```
Step 1: SCAN   → "DV 스캔해줘" (보고만, 수정 없음)
Step 2: TRIAGE → 사용자가 각 이슈를 수정/보류/허용으로 분류
Step 3: FIX    → "DV-001을 수정해줘" (지정된 항목만)
Step 4: VERIFY → "DV Phase 2만 재스캔해줘" (수정 확인)
```

---

## QC / CA / DV 관계

| 체크리스트 | 대상 | 질문 | 실행 빈도 | 소요 |
|-----------|------|------|----------|------|
| **QC** | 문서/설정 | "문서가 코드와 맞는가?" | 매 릴리스 | 3-5분 |
| **CA** | 소스 코드 | "코드가 건강한가?" | 분기별 | 10-20분 |
| **DV** | Neo4j DB | "데이터가 완전한가?" | 임포트 후 / 주간 | 3-5분 |

---

## 공통 실행 패턴

모든 DV 체크는 Neo4j에 Cypher 쿼리를 실행합니다. 아래 패턴을 기본으로 사용합니다:

```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    # Cypher 쿼리 실행
    pass
driver.close()
"
```

---

## Phase 1: 노드 무결성 (병렬 실행)

> 노드의 필수 속성, 고아 노드, 중복, 전체 현황을 점검합니다.

### 1.1 필수 속성 검증

Paper와 Chunk 노드에 필수 속성이 모두 채워져 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Paper 필수 속성 검증 ===')
    r = s.run('''
        MATCH (p:Paper)
        WITH p,
            CASE WHEN p.paper_id IS NULL OR p.paper_id = '' THEN 1 ELSE 0 END AS no_id,
            CASE WHEN p.title IS NULL OR p.title = '' THEN 1 ELSE 0 END AS no_title
        WITH count(p) AS total,
            sum(no_id) AS missing_id,
            sum(no_title) AS missing_title
        RETURN total, missing_id, missing_title
    ''')
    rec = r.single()
    print(f'  총 Paper: {rec[\"total\"]}')
    print(f'  paper_id 누락: {rec[\"missing_id\"]} {\"✅\" if rec[\"missing_id\"]==0 else \"❌\"}')
    print(f'  title 누락: {rec[\"missing_title\"]} {\"✅\" if rec[\"missing_title\"]==0 else \"❌\"}')

    print()
    print('=== Chunk 필수 속성 검증 ===')
    r = s.run('''
        MATCH (c:Chunk)
        WITH c,
            CASE WHEN c.chunk_id IS NULL OR c.chunk_id = '' THEN 1 ELSE 0 END AS no_id,
            CASE WHEN c.paper_id IS NULL OR c.paper_id = '' THEN 1 ELSE 0 END AS no_paper
        WITH count(c) AS total,
            sum(no_id) AS missing_id,
            sum(no_paper) AS missing_paper
        RETURN total, missing_id, missing_paper
    ''')
    rec = r.single()
    print(f'  총 Chunk: {rec[\"total\"]}')
    print(f'  chunk_id 누락: {rec[\"missing_id\"]} {\"✅\" if rec[\"missing_id\"]==0 else \"❌\"}')
    print(f'  paper_id 누락: {rec[\"missing_paper\"]} {\"✅\" if rec[\"missing_paper\"]==0 else \"❌\"}')

    print()
    print('=== Entity 필수 속성 (name) 검증 ===')
    for label in ['Pathology', 'Anatomy', 'Intervention', 'Outcome']:
        r = s.run(f'''
            MATCH (n:{label})
            WHERE n.name IS NULL OR n.name = ''
            RETURN count(n) AS cnt
        ''')
        cnt = r.single()['cnt']
        print(f'  {label} name 누락: {cnt} {\"✅\" if cnt==0 else \"❌\"}')
driver.close()
"
```

**기대 결과:** 모든 필수 속성 누락 = 0 ✅

### 1.2 고아 노드 탐지

어떤 Paper와도 연결되지 않은 Entity 노드를 찾습니다. 정규화 오류나 삭제 잔여물일 수 있습니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 고아 노드 탐지 ===')

    # Pathology: Paper에서 STUDIES 관계 없음
    r = s.run('''
        MATCH (n:Pathology)
        WHERE NOT (n)<-[:STUDIES]-(:Paper)
        RETURN n.name AS name ORDER BY name
    ''')
    orphans = [rec['name'] for rec in r]
    print(f'Pathology 고아: {len(orphans)} {\"✅\" if len(orphans)==0 else \"⚠️\"}')
    for name in orphans[:10]: print(f'  - {name}')

    # Intervention: Paper에서 INVESTIGATES 관계 없음 (IS_A만 있는 taxonomy 노드 제외)
    r = s.run('''
        MATCH (n:Intervention)
        WHERE NOT (n)<-[:INVESTIGATES]-(:Paper)
          AND NOT (n)<-[:IS_A]-(:Intervention)
          AND NOT (n)-[:IS_A]->(:Intervention)
        RETURN n.name AS name ORDER BY name
    ''')
    orphans = [rec['name'] for rec in r]
    print(f'Intervention 고아 (taxonomy 제외): {len(orphans)} {\"✅\" if len(orphans)==0 else \"⚠️\"}')
    for name in orphans[:10]: print(f'  - {name}')

    # Outcome: Paper-Intervention AFFECTS 관계 없음
    r = s.run('''
        MATCH (n:Outcome)
        WHERE NOT ()-[:AFFECTS]->(n)
        RETURN n.name AS name ORDER BY name
    ''')
    orphans = [rec['name'] for rec in r]
    print(f'Outcome 고아: {len(orphans)} {\"✅\" if len(orphans)==0 else \"⚠️\"}')
    for name in orphans[:10]: print(f'  - {name}')

    # Chunk: Paper에서 HAS_CHUNK 관계 없음
    r = s.run('''
        MATCH (c:Chunk)
        WHERE NOT (c)<-[:HAS_CHUNK]-(:Paper)
        RETURN c.chunk_id AS id, c.paper_id AS paper_id
    ''')
    orphans = [rec for rec in r]
    print(f'Chunk 고아: {len(orphans)} {\"✅\" if len(orphans)==0 else \"❌\"}')
    for rec in orphans[:5]: print(f'  - chunk_id={rec[\"id\"]}, paper_id={rec[\"paper_id\"]}')

    # Anatomy: Paper에서 INVOLVES 관계 없음
    r = s.run('''
        MATCH (n:Anatomy)
        WHERE NOT (n)<-[:INVOLVES]-(:Paper)
        RETURN n.name AS name ORDER BY name
    ''')
    orphans = [rec['name'] for rec in r]
    print(f'Anatomy 고아: {len(orphans)} {\"✅\" if len(orphans)==0 else \"⚠️\"}')
    for name in orphans[:10]: print(f'  - {name}')
driver.close()
"
```

**기대 결과:**
- Pathology/Outcome 고아: 0 (⚠️ 있으면 정리 권장)
- Intervention 고아: taxonomy 전용 노드는 정상이므로 제외 후 0
- Chunk 고아: 0 (❌ 있으면 데이터 오류)
- Anatomy 고아: 0 (⚠️ INVOLVES 관계 없으면 해부학 검색 사각지대)

### 1.3 중복 노드 탐지

같은 이름의 엔티티가 여러 개 존재하는지 확인합니다. UNIQUE 제약이 있으므로 같은 라벨 내 중복은 불가하지만, **다른 라벨 간** 이름 충돌이나 대소문자 변형을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 동일 라벨 내 대소문자 변형 중복 ===')
    for label in ['Pathology', 'Anatomy', 'Intervention', 'Outcome']:
        r = s.run(f'''
            MATCH (n:{label})
            WITH toLower(trim(n.name)) AS normalized, collect(n.name) AS names
            WHERE size(names) > 1
            RETURN normalized, names
        ''')
        dupes = [(rec['normalized'], rec['names']) for rec in r]
        print(f'{label} 대소문자 중복: {len(dupes)} {\"✅\" if len(dupes)==0 else \"⚠️\"}')
        for norm, names in dupes[:5]:
            print(f'  - \"{norm}\": {names}')

    print()
    print('=== 라벨 간 이름 충돌 ===')
    r = s.run('''
        MATCH (a:Pathology), (b:Intervention)
        WHERE toLower(a.name) = toLower(b.name)
        RETURN a.name AS pathology, b.name AS intervention
    ''')
    conflicts = [(rec['pathology'], rec['intervention']) for rec in r]
    print(f'Pathology-Intervention 이름 충돌: {len(conflicts)} {\"✅\" if len(conflicts)==0 else \"⚠️\"}')
    for p, i in conflicts[:5]: print(f'  - Pathology=\"{p}\" vs Intervention=\"{i}\"')
driver.close()
"
```

**기대 결과:** 중복/충돌 = 0 ✅

### 1.4 노드 수 현황 (대시보드)

전체 노드/관계 수를 한눈에 확인합니다. 이전 실행 결과와 비교하여 이상 변화를 감지합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 노드 현황 ===')
    r = s.run('''
        MATCH (n)
        RETURN labels(n)[0] AS label, count(n) AS cnt
        ORDER BY cnt DESC
    ''')
    total = 0
    for rec in r:
        print(f'  {rec[\"label\"]:20s}: {rec[\"cnt\"]:>6d}')
        total += rec['cnt']
    print(f'  {\"TOTAL\":20s}: {total:>6d}')

    print()
    print('=== 관계 현황 ===')
    r = s.run('''
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(r) AS cnt
        ORDER BY cnt DESC
    ''')
    total = 0
    for rec in r:
        print(f'  {rec[\"rel_type\"]:20s}: {rec[\"cnt\"]:>6d}')
        total += rec['cnt']
    print(f'  {\"TOTAL\":20s}: {total:>6d}')
driver.close()
"
```

**기대 결과:** 숫자 확인 (이전 결과와 비교용 — 급격한 변화 시 조사 필요)

---

## Phase 2: 관계 무결성 (병렬 실행)

> Paper-Entity 관계, Taxonomy 계층, 추론 관계의 건전성을 점검합니다.

### 2.1 고립 Paper 탐지

STUDIES, INVESTIGATES, HAS_CHUNK 관계가 하나도 없는 Paper를 찾습니다. 임포트 실패 또는 관계 생성 버그를 의미합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 고립 Paper 탐지 ===')

    # 관계 전혀 없는 Paper
    r = s.run('''
        MATCH (p:Paper)
        WHERE NOT (p)-[:STUDIES]->()
          AND NOT (p)-[:INVESTIGATES]->()
          AND NOT (p)-[:HAS_CHUNK]->()
        RETURN p.paper_id AS id, p.title AS title, p.doi AS doi
        ORDER BY p.paper_id
    ''')
    isolated = [rec for rec in r]
    print(f'완전 고립 Paper (관계 0개): {len(isolated)} {\"✅\" if len(isolated)==0 else \"❌\"}')
    for rec in isolated[:10]:
        title = (rec['title'] or '')[:60]
        print(f'  - {rec[\"id\"]}: {title}...')

    print()
    # STUDIES만 없는 Paper (Pathology 추출 실패)
    r = s.run('''
        MATCH (p:Paper)
        WHERE NOT (p)-[:STUDIES]->()
          AND ((p)-[:INVESTIGATES]->() OR (p)-[:HAS_CHUNK]->())
        RETURN count(p) AS cnt
    ''')
    cnt = r.single()['cnt']
    print(f'STUDIES 누락 Paper: {cnt} {\"✅\" if cnt==0 else \"⚠️\"}')

    # HAS_CHUNK 없는 Paper (Chunk 생성 실패)
    r = s.run('''
        MATCH (p:Paper)
        WHERE NOT (p)-[:HAS_CHUNK]->()
        RETURN count(p) AS cnt
    ''')
    cnt = r.single()['cnt']
    print(f'HAS_CHUNK 누락 Paper: {cnt} {\"✅\" if cnt==0 else \"⚠️\"}')
driver.close()
"
```

**기대 결과:** 완전 고립 Paper = 0 ❌ (있으면 즉시 조사)

**복구 방법:** 고립 논문이 발견되면 `repair_isolated_papers.py` 스크립트로 복구:
```bash
# 전체 고립 논문 복구 (LLM으로 abstract 재분석 → 관계 구축)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --max-concurrent 5

# 특정 논문만 복구
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --paper-ids "pubmed_12345,pubmed_67890"

# Dry-run (실제 DB 변경 없이 추출 결과만 확인)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --dry-run
```

### 2.2 IS_A 계층 무결성

Intervention taxonomy의 IS_A 관계에 순환 참조가 없고, 루트 노드가 올바른지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== IS_A 계층 무결성 ===')

    # 순환 참조 탐지
    r = s.run('''
        MATCH path = (a:Intervention)-[:IS_A*2..10]->(b:Intervention)
        WHERE a = b
        RETURN a.name AS name, length(path) AS cycle_length
        LIMIT 10
    ''')
    cycles = [rec for rec in r]
    print(f'순환 참조: {len(cycles)} {\"✅\" if len(cycles)==0 else \"❌\"}')
    for rec in cycles: print(f'  - {rec[\"name\"]} (cycle length: {rec[\"cycle_length\"]})')

    # 루트 노드 확인 (IS_A 부모가 없는 최상위 노드)
    r = s.run('''
        MATCH (n:Intervention)
        WHERE NOT (n)-[:IS_A]->(:Intervention)
          AND (n)<-[:IS_A]-(:Intervention)
        RETURN n.name AS name ORDER BY name
    ''')
    roots = [rec['name'] for rec in r]
    print(f'IS_A 루트 노드: {len(roots)}')
    for name in roots: print(f'  - {name}')
    expected_roots = ['Spine Surgery']
    if roots == expected_roots:
        print('  루트 정상 ✅')
    else:
        print(f'  기대 루트: {expected_roots} ⚠️')

    # 계층 깊이 분포
    r = s.run('''
        MATCH path = (child:Intervention)-[:IS_A*1..10]->(root:Intervention)
        WHERE NOT (root)-[:IS_A]->(:Intervention)
        RETURN length(path) AS depth, count(*) AS cnt
        ORDER BY depth
    ''')
    print('IS_A 깊이 분포:')
    for rec in r:
        print(f'  depth {rec[\"depth\"]}: {rec[\"cnt\"]}개')
driver.close()
"
```

**기대 결과:** 순환 참조 = 0, 루트 = "Spine Surgery" 단일 노드

### 2.3 TREATS 백필 상태

Intervention→Pathology TREATS 관계가 적절히 생성되었는지 확인합니다. Paper가 Intervention을 INVESTIGATES하고 Pathology를 STUDIES하면, 해당 Intervention→Pathology에 TREATS가 있어야 합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== TREATS 백필 상태 ===')

    # 현재 TREATS 관계 수
    r = s.run('MATCH ()-[r:TREATS]->() RETURN count(r) AS cnt')
    treats_cnt = r.single()['cnt']
    print(f'현재 TREATS 관계: {treats_cnt}')

    # 백필 가능한 (아직 TREATS 없는) 조합
    r = s.run('''
        MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention),
              (p)-[:STUDIES]->(path:Pathology)
        WHERE NOT (i)-[:TREATS]->(path)
        RETURN i.name AS intervention, path.name AS pathology, count(p) AS paper_count
        ORDER BY paper_count DESC
        LIMIT 15
    ''')
    missing = [rec for rec in r]
    print(f'TREATS 미생성 조합: {len(missing)} {\"✅\" if len(missing)==0 else \"⚠️\"}')
    for rec in missing[:10]:
        print(f'  - {rec[\"intervention\"]} → {rec[\"pathology\"]} ({rec[\"paper_count\"]}편)')

    # TREATS paper_count 속성 정합성
    r = s.run('''
        MATCH (i:Intervention)-[t:TREATS]->(path:Pathology)
        OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i), (p)-[:STUDIES]->(path)
        WITH i, path, t, count(p) AS actual_count
        WHERE t.paper_count <> actual_count
        RETURN i.name AS intervention, path.name AS pathology,
               t.paper_count AS recorded, actual_count
        LIMIT 10
    ''')
    mismatches = [rec for rec in r]
    print(f'TREATS paper_count 불일치: {len(mismatches)} {\"✅\" if len(mismatches)==0 else \"⚠️\"}')
driver.close()
"
```

**기대 결과:** 미생성 조합 = 0, paper_count 불일치 = 0

### 2.4 AFFECTS 속성 완전성

Intervention→Outcome AFFECTS 관계에 근거 데이터(p_value, direction, effect_size)가 채워져 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== AFFECTS 속성 완전성 ===')

    r = s.run('''
        MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
        WITH count(r) AS total,
            sum(CASE WHEN r.p_value IS NOT NULL THEN 1 ELSE 0 END) AS has_pvalue,
            sum(CASE WHEN r.direction IS NOT NULL THEN 1 ELSE 0 END) AS has_direction,
            sum(CASE WHEN r.effect_size IS NOT NULL THEN 1 ELSE 0 END) AS has_effect,
            sum(CASE WHEN r.is_significant IS NOT NULL THEN 1 ELSE 0 END) AS has_sig
        RETURN total, has_pvalue, has_direction, has_effect, has_sig
    ''')
    rec = r.single()
    total = rec['total']
    if total > 0:
        print(f'총 AFFECTS 관계: {total}')
        print(f'  p_value 있음: {rec[\"has_pvalue\"]}/{total} ({rec[\"has_pvalue\"]*100//total}%)')
        print(f'  direction 있음: {rec[\"has_direction\"]}/{total} ({rec[\"has_direction\"]*100//total}%)')
        print(f'  effect_size 있음: {rec[\"has_effect\"]}/{total} ({rec[\"has_effect\"]*100//total}%)')
        print(f'  is_significant 있음: {rec[\"has_sig\"]}/{total} ({rec[\"has_sig\"]*100//total}%)')
    else:
        print('AFFECTS 관계 없음 ⚠️')
driver.close()
"
```

**기대 결과:** p_value, direction 비율이 높을수록 좋음 (100%는 비현실적, 50%+ 권장)

### 2.5 Taxonomy 리프 노드 Paper 연결

IS_A 계층의 리프 노드(하위 Intervention이 없는)가 실제 Paper와 연결되어 있는지 확인합니다. 연결 없는 리프 노드는 taxonomy만 있고 데이터 없는 빈 껍데기입니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Taxonomy 리프 노드 Paper 연결 ===')

    r = s.run('''
        MATCH (leaf:Intervention)-[:IS_A]->(:Intervention)
        WHERE NOT (leaf)<-[:IS_A]-(:Intervention)
          AND NOT (leaf)<-[:INVESTIGATES]-(:Paper)
        RETURN leaf.name AS name ORDER BY name
    ''')
    orphan_leaves = [rec['name'] for rec in r]
    print(f'Paper 미연결 리프 노드: {len(orphan_leaves)} {\"✅\" if len(orphan_leaves)==0 else \"⚠️\"}')
    for name in orphan_leaves: print(f'  - {name}')

    # 전체 리프 대비 비율
    r = s.run('''
        MATCH (leaf:Intervention)-[:IS_A]->(:Intervention)
        WHERE NOT (leaf)<-[:IS_A]-(:Intervention)
        RETURN count(leaf) AS total
    ''')
    total_leaves = r.single()['total']
    connected = total_leaves - len(orphan_leaves)
    pct = connected*100//total_leaves if total_leaves > 0 else 0
    print(f'리프 노드 Paper 연결률: {connected}/{total_leaves} ({pct}%)')
driver.close()
"
```

**기대 결과:** Paper 미연결 리프 노드 = 0 (⚠️ 있으면 해당 수술법 논문 임포트 권장)

### 2.6 INVOLVES (Anatomy) 관계 완전성

STUDIES/INVESTIGATES 관계는 있지만 INVOLVES (Anatomy) 관계가 없는 Paper를 찾습니다. Anatomy 연결 누락은 해부학 기반 검색의 사각지대가 됩니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== INVOLVES (Anatomy) 관계 완전성 ===')

    r = s.run('''
        MATCH (p:Paper)
        WHERE ((p)-[:STUDIES]->() OR (p)-[:INVESTIGATES]->())
          AND NOT (p)-[:INVOLVES]->(:Anatomy)
        RETURN p.paper_id AS id, p.title AS title
        ORDER BY p.paper_id
    ''')
    missing = [rec for rec in r]
    print(f'Anatomy 연결 누락 Paper: {len(missing)} {\"⚠️\" if len(missing) > 0 else \"✅\"}')
    for rec in missing[:10]:
        title = (rec['title'] or '')[:60]
        print(f'  - {rec[\"id\"]}: {title}...')

    # 전체 대비 비율
    r = s.run('''
        MATCH (p:Paper)
        WHERE (p)-[:STUDIES]->() OR (p)-[:INVESTIGATES]->()
        RETURN count(p) AS total
    ''')
    total = r.single()['total']
    connected = total - len(missing)
    pct = connected*100//total if total > 0 else 0
    print(f'Anatomy 연결률: {connected}/{total} ({pct}%)')
driver.close()
"
```

**기대 결과:** Anatomy 연결률 80%+ (일부 Basic Science 논문은 특정 해부학 위치 없을 수 있음)

---

## Phase 3: 임베딩 & 검색 품질 (병렬 실행)

> 벡터 인덱스와 임베딩 완전성을 점검합니다. 누락된 임베딩은 하이브리드 검색의 사각지대입니다.

### 3.1 Chunk 임베딩 완전성

모든 Chunk에 3072차원 임베딩이 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Chunk 임베딩 완전성 ===')

    r = s.run('''
        MATCH (c:Chunk)
        WITH count(c) AS total,
            sum(CASE WHEN c.embedding IS NOT NULL THEN 1 ELSE 0 END) AS has_embedding
        RETURN total, has_embedding, total - has_embedding AS missing
    ''')
    rec = r.single()
    total = rec['total']
    missing = rec['missing']
    pct = rec['has_embedding']*100//total if total > 0 else 0
    print(f'총 Chunk: {total}')
    print(f'임베딩 있음: {rec[\"has_embedding\"]} ({pct}%)')
    print(f'임베딩 누락: {missing} {\"✅\" if missing==0 else \"❌\"}')

    if missing > 0:
        r = s.run('''
            MATCH (c:Chunk)
            WHERE c.embedding IS NULL
            RETURN c.chunk_id AS id, c.paper_id AS paper_id, c.section AS section
            LIMIT 10
        ''')
        print('누락 Chunk 샘플:')
        for rec in r:
            print(f'  - {rec[\"id\"]} (paper: {rec[\"paper_id\"]}, section: {rec[\"section\"]})')
driver.close()
"
```

**기대 결과:** 임베딩 누락 = 0 ✅

### 3.2 Paper Abstract 임베딩 완전성

Abstract가 있는 Paper에 abstract_embedding이 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Paper Abstract 임베딩 완전성 ===')

    r = s.run('''
        MATCH (p:Paper)
        WHERE p.abstract IS NOT NULL AND p.abstract <> ''
        WITH count(p) AS has_abstract,
            sum(CASE WHEN p.abstract_embedding IS NOT NULL THEN 1 ELSE 0 END) AS has_embedding
        RETURN has_abstract, has_embedding, has_abstract - has_embedding AS missing
    ''')
    rec = r.single()
    has_abstract = rec['has_abstract']
    missing = rec['missing']
    pct = rec['has_embedding']*100//has_abstract if has_abstract > 0 else 0
    print(f'Abstract 있는 Paper: {has_abstract}')
    print(f'Abstract 임베딩 있음: {rec[\"has_embedding\"]} ({pct}%)')
    print(f'Abstract 임베딩 누락: {missing} {\"✅\" if missing==0 else \"⚠️\"}')
driver.close()
"
```

**기대 결과:** 누락 = 0 ✅ (⚠️ 있으면 재임베딩 권장)

### 3.3 벡터 인덱스 상태

Neo4j 벡터 인덱스가 정상 동작하는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 벡터 인덱스 상태 ===')

    r = s.run('''
        SHOW INDEXES
        YIELD name, type, state, populationPercent, entityType, labelsOrTypes, properties
        WHERE type = 'VECTOR'
        RETURN name, state, populationPercent, labelsOrTypes, properties
    ''')
    indexes = [rec for rec in r]
    if not indexes:
        print('벡터 인덱스 없음 ❌')
    else:
        for idx in indexes:
            state_ok = idx['state'] == 'ONLINE'
            pop_ok = idx['populationPercent'] == 100.0
            print(f'{idx[\"name\"]}:')
            print(f'  상태: {idx[\"state\"]} {\"✅\" if state_ok else \"❌\"}')
            print(f'  인덱싱: {idx[\"populationPercent\"]}% {\"✅\" if pop_ok else \"⚠️\"}')
            print(f'  대상: {idx[\"labelsOrTypes\"]}.{idx[\"properties\"]}')

    expected = ['chunk_embedding_index', 'paper_abstract_index']
    found = [idx['name'] for idx in indexes]
    for name in expected:
        if name not in found:
            print(f'{name} 인덱스 누락 ❌')
driver.close()
"
```

**기대 결과:** 2개 벡터 인덱스 ONLINE, populationPercent = 100%

---

## Phase 4: 식별자 & SNOMED & 온톨로지 (병렬 실행)

> 외부 식별자(DOI, PMID), SNOMED 매핑, 온톨로지 동기화를 점검합니다.

### 4.1 DOI / PMID 완전성

v1.18.0에서 수정된 DOI NULL 버그의 재발을 감시합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== DOI / PMID 완전성 ===')

    r = s.run('''
        MATCH (p:Paper)
        WITH count(p) AS total,
            sum(CASE WHEN p.doi IS NOT NULL AND p.doi <> '' THEN 1 ELSE 0 END) AS has_doi,
            sum(CASE WHEN p.pmid IS NOT NULL AND p.pmid <> '' THEN 1 ELSE 0 END) AS has_pmid,
            sum(CASE WHEN p.pmc_id IS NOT NULL AND p.pmc_id <> '' THEN 1 ELSE 0 END) AS has_pmc
        RETURN total, has_doi, has_pmid, has_pmc
    ''')
    rec = r.single()
    total = rec['total']
    print(f'총 Paper: {total}')
    if total > 0:
        print(f'  DOI 있음: {rec[\"has_doi\"]}/{total} ({rec[\"has_doi\"]*100//total}%)')
        print(f'  PMID 있음: {rec[\"has_pmid\"]}/{total} ({rec[\"has_pmid\"]*100//total}%)')
        print(f'  PMC ID 있음: {rec[\"has_pmc\"]}/{total} ({rec[\"has_pmc\"]*100//total}%)')

    # DOI NULL인 Paper 목록
    r = s.run('''
        MATCH (p:Paper)
        WHERE p.doi IS NULL OR p.doi = ''
        RETURN p.paper_id AS id, p.title AS title, p.pmid AS pmid
        ORDER BY p.paper_id
    ''')
    no_doi = [rec for rec in r]
    print(f'  DOI 누락 Paper: {len(no_doi)} {\"✅\" if len(no_doi)==0 else \"⚠️\"}')
    for rec in no_doi[:10]:
        title = (rec['title'] or '')[:50]
        print(f'    - {rec[\"id\"]}: {title}... (PMID: {rec[\"pmid\"]})')
driver.close()
"
```

**기대 결과:** DOI 비율 90%+, PMID 비율 90%+ (일부 preprint/thesis는 없을 수 있음)

### 4.2 SNOMED 매핑 커버리지

각 엔티티 타입별 SNOMED 코드 매핑 비율을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== SNOMED 매핑 커버리지 ===')

    for label in ['Intervention', 'Pathology', 'Outcome', 'Anatomy']:
        r = s.run(f'''
            MATCH (n:{label})
            WITH count(n) AS total,
                sum(CASE WHEN n.snomed_code IS NOT NULL AND n.snomed_code <> '' THEN 1 ELSE 0 END) AS mapped,
                sum(CASE WHEN n.snomed_is_extension = true THEN 1 ELSE 0 END) AS extension
            RETURN total, mapped, extension
        ''')
        rec = r.single()
        total = rec['total']
        mapped = rec['mapped']
        pct = mapped*100//total if total > 0 else 0
        print(f'{label}: {mapped}/{total} ({pct}%) mapped, {rec[\"extension\"]} extension')

        # 매핑 안 된 것 목록
        if total > mapped:
            r = s.run(f'''
                MATCH (n:{label})
                WHERE n.snomed_code IS NULL OR n.snomed_code = ''
                RETURN n.name AS name ORDER BY name LIMIT 10
            ''')
            unmapped = [rec['name'] for rec in r]
            for name in unmapped:
                print(f'  미매핑: {name}')
driver.close()
"
```

**기대 결과:** 매핑 비율 높을수록 좋음 (신규 엔티티는 미매핑 가능)

### 4.3 SNOMED 코드 유효성

SNOMED 코드가 올바른 형식(숫자만, 적절한 길이)인지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
from neo4j import GraphDatabase
import re
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== SNOMED 코드 유효성 ===')

    for label in ['Intervention', 'Pathology', 'Outcome', 'Anatomy']:
        r = s.run(f'''
            MATCH (n:{label})
            WHERE n.snomed_code IS NOT NULL AND n.snomed_code <> ''
            RETURN n.name AS name, n.snomed_code AS code
        ''')
        invalid = []
        for rec in r:
            code = str(rec['code'])
            # SNOMED 코드는 숫자만, 6-18자리
            if not re.match(r'^\d{6,18}$', code):
                invalid.append((rec['name'], code))
        print(f'{label} 유효하지 않은 코드: {len(invalid)} {\"✅\" if len(invalid)==0 else \"⚠️\"}')
        for name, code in invalid[:5]:
            print(f'  - {name}: \"{code}\"')
driver.close()
"
```

**기대 결과:** 유효하지 않은 코드 = 0 ✅

### 4.4 SNOMED 코드 중복 탐지

서로 다른 엔티티에 같은 SNOMED 코드가 할당되었는지 확인합니다. 같은 라벨 내 또는 라벨 간 중복 모두 점검합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== SNOMED 코드 중복 탐지 ===')

    # 같은 라벨 내 중복
    for label in ['Intervention', 'Pathology', 'Outcome', 'Anatomy']:
        r = s.run(f'''
            MATCH (a:{label}), (b:{label})
            WHERE id(a) < id(b)
              AND a.snomed_code IS NOT NULL AND a.snomed_code <> ''
              AND a.snomed_code = b.snomed_code
            RETURN a.name AS name_a, b.name AS name_b, a.snomed_code AS code
        ''')
        dupes = [rec for rec in r]
        print(f'{label} 내 SNOMED 중복: {len(dupes)} {\"✅\" if len(dupes)==0 else \"❌\"}')
        for rec in dupes[:5]:
            print(f'  - \"{rec[\"name_a\"]}\" vs \"{rec[\"name_b\"]}\" (code: {rec[\"code\"]})')

    # 라벨 간 중복
    print()
    r = s.run('''
        MATCH (a), (b)
        WHERE id(a) < id(b)
          AND a.snomed_code IS NOT NULL AND a.snomed_code <> ''
          AND a.snomed_code = b.snomed_code
          AND any(la IN labels(a) WHERE la IN ['Intervention','Pathology','Outcome','Anatomy'])
          AND any(lb IN labels(b) WHERE lb IN ['Intervention','Pathology','Outcome','Anatomy'])
          AND labels(a)[0] <> labels(b)[0]
        RETURN labels(a)[0] AS label_a, a.name AS name_a,
               labels(b)[0] AS label_b, b.name AS name_b,
               a.snomed_code AS code
    ''')
    cross = [rec for rec in r]
    print(f'라벨 간 SNOMED 중복: {len(cross)} {\"✅\" if len(cross)==0 else \"⚠️\"}')
    for rec in cross[:10]:
        print(f'  - {rec[\"label_a\"]}:\"{rec[\"name_a\"]}\" vs {rec[\"label_b\"]}:\"{rec[\"name_b\"]}\" (code: {rec[\"code\"]})')
driver.close()
"
```

**기대 결과:** 같은 라벨 내 중복 = 0, 라벨 간 중복 = 0

> **참고 (v1.21.0)**: Outcome 카테고리에서 시점/기법별 변형이 동일 SNOMED 코드를 공유하는 것은 **의도된 설계**입니다 (예: VAS Back preop / VAS Back 6mo / VAS Back final → 모두 같은 VAS Back 코드). 이는 시간 경과에 따른 동일 측정값의 변형으로, 의학적으로 별도 개념이 아닙니다.

### 4.5 Neo4j ↔ SNOMED 매핑 소스 동기화

Neo4j의 SNOMED 코드가 `spine_snomed_mappings.py` (Single Source of Truth)와 일치하는지 검증합니다. 불일치는 매핑 업데이트 후 Neo4j 반영 누락을 의미합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os, sys
sys.path.insert(0, 'src')
from neo4j import GraphDatabase
from ontology.spine_snomed_mappings import (
    SPINE_INTERVENTION_SNOMED, SPINE_PATHOLOGY_SNOMED,
    SPINE_OUTCOME_SNOMED, SPINE_ANATOMY_SNOMED
)

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Neo4j ↔ SNOMED 매핑 소스 동기화 ===')

    mapping_sources = {
        'Intervention': SPINE_INTERVENTION_SNOMED,
        'Pathology': SPINE_PATHOLOGY_SNOMED,
        'Outcome': SPINE_OUTCOME_SNOMED,
        'Anatomy': SPINE_ANATOMY_SNOMED,
    }

    for label, source_dict in mapping_sources.items():
        r = s.run(f'''
            MATCH (n:{label})
            WHERE n.snomed_code IS NOT NULL AND n.snomed_code <> ''
            RETURN n.name AS name, n.snomed_code AS code
        ''')
        neo4j_mappings = {rec['name']: str(rec['code']) for rec in r}

        # Source와 Neo4j 코드 불일치
        mismatches = []
        for name, mapping in source_dict.items():
            src_code = str(mapping.code)
            if name in neo4j_mappings and neo4j_mappings[name] != src_code:
                mismatches.append((name, src_code, neo4j_mappings[name]))

        # Neo4j에 있지만 Source에 없는 매핑
        neo4j_only = []
        for name, code in neo4j_mappings.items():
            if name not in source_dict:
                neo4j_only.append((name, code))

        print(f'{label}:')
        print(f'  코드 불일치: {len(mismatches)} {\"✅\" if len(mismatches)==0 else \"❌\"}')
        for name, src, neo in mismatches[:5]:
            print(f'    - {name}: source={src} vs neo4j={neo}')
        print(f'  Neo4j에만 있는 매핑: {len(neo4j_only)} {\"✅\" if len(neo4j_only)==0 else \"⚠️\"}')
        for name, code in neo4j_only[:5]:
            print(f'    - {name}: {code}')
driver.close()
"
```

**기대 결과:** 코드 불일치 = 0, Neo4j 전용 매핑 = 0 (있으면 source 동기화 필요)

### 4.6 Entity Normalizer 커버리지

Neo4j에 존재하는 엔티티 이름이 `entity_normalizer.py` 별칭 사전에 포함되어 있는지 확인합니다. 누락된 엔티티는 검색 시 정규화되지 않아 "투명인간"이 됩니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os, sys
sys.path.insert(0, 'src')
from neo4j import GraphDatabase
from graph.entity_normalizer import EntityNormalizer

normalizer = EntityNormalizer()
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Entity Normalizer 커버리지 ===')

    checks = [
        ('Intervention', 'normalize_intervention'),
        ('Pathology', 'normalize_pathology'),
        ('Outcome', 'normalize_outcome'),
        ('Anatomy', 'normalize_anatomy'),
    ]

    for label, method_name in checks:
        r = s.run(f'MATCH (n:{label}) RETURN n.name AS name ORDER BY name')
        names = [rec['name'] for rec in r]

        method = getattr(normalizer, method_name, None)
        if method is None:
            print(f'{label}: normalize 메서드 없음 ⚠️')
            continue

        uncovered = []
        for name in names:
            try:
                result = method(name)
                if result is None or (hasattr(result, 'confidence') and result.confidence < 0.5):
                    uncovered.append(name)
            except Exception:
                uncovered.append(name)

        covered = len(names) - len(uncovered)
        pct = covered*100//len(names) if len(names) > 0 else 0
        print(f'{label}: {covered}/{len(names)} ({pct}%) 커버')
        if uncovered:
            print(f'  미커버 ({len(uncovered)}개):')
            for name in uncovered[:10]:
                print(f'    - {name}')
            if len(uncovered) > 10:
                print(f'    ... 외 {len(uncovered)-10}개')
driver.close()
"
```

**기대 결과:** 커버리지 90%+ (신규 임포트 엔티티는 미커버 가능, 별칭 추가 권장)

---

## Phase 5: 데이터 품질 (병렬 실행)

> 콘텐츠 품질, 분포 이상, 중복을 점검합니다.

### 5.1 콘텐츠 품질

Paper의 주요 텍스트 필드가 적절하게 채워져 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Paper 콘텐츠 품질 ===')

    r = s.run('''
        MATCH (p:Paper)
        WITH count(p) AS total,
            sum(CASE WHEN p.abstract IS NOT NULL AND size(p.abstract) > 50 THEN 1 ELSE 0 END) AS has_abstract,
            sum(CASE WHEN p.year IS NOT NULL THEN 1 ELSE 0 END) AS has_year,
            sum(CASE WHEN p.evidence_level IS NOT NULL AND p.evidence_level <> '' THEN 1 ELSE 0 END) AS has_evidence,
            sum(CASE WHEN p.study_design IS NOT NULL AND p.study_design <> '' THEN 1 ELSE 0 END) AS has_design,
            sum(CASE WHEN p.authors IS NOT NULL THEN 1 ELSE 0 END) AS has_authors,
            sum(CASE WHEN p.summary IS NOT NULL AND size(p.summary) > 100 THEN 1 ELSE 0 END) AS has_summary
        RETURN total, has_abstract, has_year, has_evidence, has_design, has_authors, has_summary
    ''')
    rec = r.single()
    total = rec['total']
    print(f'총 Paper: {total}')
    if total > 0:
        for field, key in [('Abstract (50자+)', 'has_abstract'), ('Year', 'has_year'),
                           ('Evidence Level', 'has_evidence'), ('Study Design', 'has_design'),
                           ('Authors', 'has_authors'), ('Summary (100자+)', 'has_summary')]:
            val = rec[key]
            pct = val*100//total
            status = '✅' if pct >= 80 else '⚠️' if pct >= 50 else '❌'
            print(f'  {field:25s}: {val}/{total} ({pct}%) {status}')
driver.close()
"
```

**기대 결과:** Abstract, Year, Authors = 80%+ ✅

### 5.2 분포 이상 탐지

Evidence level, year, study_design의 분포를 확인합니다. 편향이나 이상값을 발견합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Evidence Level 분포 ===')
    r = s.run('''
        MATCH (p:Paper)
        WHERE p.evidence_level IS NOT NULL AND p.evidence_level <> ''
        RETURN p.evidence_level AS level, count(p) AS cnt
        ORDER BY level
    ''')
    for rec in r:
        print(f'  {rec[\"level\"]:10s}: {rec[\"cnt\"]}')

    print()
    print('=== Year 분포 ===')
    r = s.run('''
        MATCH (p:Paper)
        WHERE p.year IS NOT NULL
        RETURN p.year AS year, count(p) AS cnt
        ORDER BY year DESC
        LIMIT 15
    ''')
    for rec in r:
        print(f'  {rec[\"year\"]}: {rec[\"cnt\"]}')

    print()
    print('=== Study Design 분포 ===')
    r = s.run('''
        MATCH (p:Paper)
        WHERE p.study_design IS NOT NULL AND p.study_design <> ''
        RETURN p.study_design AS design, count(p) AS cnt
        ORDER BY cnt DESC
        LIMIT 15
    ''')
    for rec in r:
        print(f'  {rec[\"design\"]:30s}: {rec[\"cnt\"]}')
driver.close()
"
```

**기대 결과:** 분포 확인 (특정 level에 극단적 편중 시 임포트 편향 의심)

### 5.3 중복 논문 탐지

같은 DOI 또는 매우 유사한 제목을 가진 Paper가 있는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 중복 DOI 탐지 ===')
    r = s.run('''
        MATCH (p:Paper)
        WHERE p.doi IS NOT NULL AND p.doi <> ''
        WITH p.doi AS doi, collect(p.paper_id) AS paper_ids
        WHERE size(paper_ids) > 1
        RETURN doi, paper_ids
    ''')
    dupes = [rec for rec in r]
    print(f'중복 DOI: {len(dupes)} {\"✅\" if len(dupes)==0 else \"❌\"}')
    for rec in dupes[:5]:
        print(f'  - DOI: {rec[\"doi\"]} → papers: {rec[\"paper_ids\"]}')

    print()
    print('=== 유사 제목 탐지 ===')
    r = s.run('''
        MATCH (a:Paper), (b:Paper)
        WHERE id(a) < id(b)
          AND a.title IS NOT NULL AND b.title IS NOT NULL
          AND toLower(a.title) = toLower(b.title)
        RETURN a.paper_id AS id_a, b.paper_id AS id_b,
               a.title AS title
        LIMIT 10
    ''')
    similar = [rec for rec in r]
    print(f'동일 제목 (대소문자 무시): {len(similar)} {\"✅\" if len(similar)==0 else \"⚠️\"}')
    for rec in similar[:5]:
        print(f'  - {rec[\"id_a\"]} vs {rec[\"id_b\"]}: {(rec[\"title\"] or \"\")[:60]}')
driver.close()
"
```

**기대 결과:** 중복 DOI = 0, 동일 제목 = 0

### 5.4 Chunk 품질

Chunk의 tier 분포, content 품질, paper_id 정합성을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== Chunk Tier 분포 ===')
    r = s.run('''
        MATCH (c:Chunk)
        RETURN c.tier AS tier, count(c) AS cnt
        ORDER BY tier
    ''')
    for rec in r:
        print(f'  Tier {rec[\"tier\"]}: {rec[\"cnt\"]}')

    print()
    print('=== Chunk Section 분포 ===')
    r = s.run('''
        MATCH (c:Chunk)
        RETURN c.section AS section, count(c) AS cnt
        ORDER BY cnt DESC
        LIMIT 10
    ''')
    for rec in r:
        print(f'  {str(rec[\"section\"]):20s}: {rec[\"cnt\"]}')

    print()
    print('=== 빈 Chunk Content 탐지 ===')
    r = s.run('''
        MATCH (c:Chunk)
        WHERE c.content IS NULL OR c.content = ''
        RETURN count(c) AS cnt
    ''')
    cnt = r.single()['cnt']
    print(f'빈 content Chunk: {cnt} {\"✅\" if cnt==0 else \"❌\"}')

    print()
    print('=== Chunk paper_id ↔ Paper 정합성 ===')
    r = s.run('''
        MATCH (c:Chunk)
        WHERE NOT exists {
            MATCH (p:Paper {paper_id: c.paper_id})
        }
        RETURN count(c) AS cnt
    ''')
    cnt = r.single()['cnt']
    print(f'존재하지 않는 paper_id 참조: {cnt} {\"✅\" if cnt==0 else \"❌\"}')
driver.close()
"
```

**기대 결과:** 빈 content = 0, paper_id 불일치 = 0

---

## Phase 6: 온톨로지 무결성 (병렬 실행)

> 4-Entity IS_A 계층(Intervention, Pathology, Outcome, Anatomy)의 구조적 무결성을 검증합니다.
> **v1.24.0** 신규 추가: Ontology Redesign에 따른 다중 엔티티 IS_A 검증

### 6.1 IS_A 계층 완전성

모든 Pathology/Outcome/Anatomy 노드가 IS_A 부모를 가지는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== IS_A 계층 완전성 ===')
    for label in ['Pathology', 'Outcome', 'Anatomy', 'Intervention']:
        r = s.run(f'''
            MATCH (n:{label})
            WHERE NOT (n)-[:IS_A]->()
            RETURN count(n) AS orphan_count
        ''')
        orphan = r.single()['orphan_count']
        r2 = s.run(f'MATCH (n:{label}) RETURN count(n) AS total')
        total = r2.single()['total']
        r3 = s.run(f'''
            MATCH (n:{label})-[:IS_A]->()
            RETURN count(DISTINCT n) AS with_parent
        ''')
        with_parent = r3.single()['with_parent']
        pct = (with_parent / total * 100) if total > 0 else 0
        status = '✅' if pct > 80 else '⚠️' if pct > 50 else '❌'
        print(f'  {label}: {with_parent}/{total} ({pct:.1f}%) with IS_A parent {status}')
        print(f'    Orphans (no parent): {orphan}')
driver.close()
"
```

**기대 결과:** Intervention 80%+, Pathology/Outcome/Anatomy 60%+ with IS_A parent

### 6.2 IS_A 순환 참조 탐지

IS_A 관계에 순환(cycle)이 없는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== IS_A 순환 참조 탐지 ===')
    for label in ['Pathology', 'Outcome', 'Anatomy', 'Intervention']:
        r = s.run(f'''
            MATCH path = (n:{label})-[:IS_A*2..10]->(n)
            RETURN count(path) AS cycle_count,
                   collect(DISTINCT n.name)[..5] AS cycle_nodes
        ''')
        rec = r.single()
        cnt = rec['cycle_count']
        nodes = rec['cycle_nodes']
        status = '✅' if cnt == 0 else '❌'
        print(f'  {label}: {cnt} cycles {status}')
        if nodes:
            print(f'    Nodes in cycles: {nodes}')
driver.close()
"
```

**기대 결과:** 모든 엔티티 타입에서 cycle = 0

### 6.3 고아 리프 노드 탐지

IS_A 관계가 없고 Paper 연결도 없는 고립 엔티티를 식별합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== 고아 리프 노드 (IS_A 없음 + Paper 미연결) ===')
    checks = [
        ('Pathology', 'STUDIES'),
        ('Intervention', 'INVESTIGATES'),
        ('Outcome', 'AFFECTS'),
        ('Anatomy', 'INVOLVES'),
    ]
    for label, rel in checks:
        if label == 'Outcome':
            r = s.run(f'''
                MATCH (n:{label})
                WHERE NOT (n)-[:IS_A]->()
                  AND NOT ()-[:IS_A]->(n)
                  AND NOT ()-[:{rel}]->(n)
                RETURN count(n) AS cnt, collect(n.name)[..5] AS samples
            ''')
        else:
            r = s.run(f'''
                MATCH (n:{label})
                WHERE NOT (n)-[:IS_A]->()
                  AND NOT ()-[:IS_A]->(n)
                  AND NOT ()-[:{rel}]->(n)
                RETURN count(n) AS cnt, collect(n.name)[..5] AS samples
            ''')
        rec = r.single()
        cnt = rec['cnt']
        samples = rec['samples']
        status = '✅' if cnt == 0 else '⚠️'
        print(f'  {label}: {cnt} orphan leaf nodes {status}')
        if samples:
            print(f'    Samples: {samples}')
driver.close()
"
```

**기대 결과:** 고아 리프 노드 = 0 (또는 최소)

### 6.4 SNOMED 커버리지 (엔티티 타입별)

각 엔티티 타입별 SNOMED 코드 부여율을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== SNOMED 커버리지 (엔티티 타입별) ===')
    for label in ['Intervention', 'Pathology', 'Outcome', 'Anatomy']:
        r = s.run(f'''
            MATCH (n:{label})
            WITH count(n) AS total,
                 sum(CASE WHEN n.snomed_code IS NOT NULL AND n.snomed_code <> \"\" THEN 1 ELSE 0 END) AS with_snomed
            RETURN total, with_snomed,
                   CASE WHEN total > 0 THEN round(with_snomed * 100.0 / total, 1) ELSE 0 END AS pct
        ''')
        rec = r.single()
        total = rec['total']; with_s = rec['with_snomed']; pct = rec['pct']
        status = '✅' if pct > 80 else '⚠️' if pct > 40 else '❌'
        print(f'  {label}: {with_s}/{total} ({pct}%) with SNOMED {status}')
driver.close()
"
```

**기대 결과:** Anatomy 80%+, Intervention 40%+, Pathology 35%+, Outcome 20%+

### 6.5 parent_code ↔ Neo4j IS_A 일치율

spine_snomed_mappings.py의 parent_code 정의와 Neo4j IS_A 관계의 일치 여부를 검증합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
from ontology.spine_snomed_mappings import (
    SPINE_PATHOLOGY_SNOMED, SPINE_OUTCOME_SNOMED,
    SPINE_ANATOMY_SNOMED, SPINE_INTERVENTION_SNOMED,
)
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))

configs = [
    ('Pathology', SPINE_PATHOLOGY_SNOMED),
    ('Outcome', SPINE_OUTCOME_SNOMED),
    ('Anatomy', SPINE_ANATOMY_SNOMED),
    ('Intervention', SPINE_INTERVENTION_SNOMED),
]
print('=== parent_code ↔ Neo4j IS_A 일치율 ===')
with driver.session() as s:
    for label, mapping in configs:
        # Build code->name lookup
        code_to_name = {m.code: name for name, m in mapping.items()}
        expected = 0
        matched = 0
        mismatched = []
        for name, m in mapping.items():
            if not m.parent_code:
                continue
            parent_name = code_to_name.get(m.parent_code)
            if not parent_name:
                continue
            expected += 1
            r = s.run(f'''
                MATCH (child:{label} {{name: \$child}})-[:IS_A]->(parent:{label} {{name: \$parent}})
                RETURN count(*) AS cnt
            ''', {'child': name, 'parent': parent_name})
            cnt = r.single()['cnt']
            if cnt > 0:
                matched += 1
            else:
                mismatched.append(f'{name} -> {parent_name}')
        pct = (matched / expected * 100) if expected > 0 else 0
        status = '✅' if pct > 90 else '⚠️' if pct > 70 else '❌'
        print(f'  {label}: {matched}/{expected} ({pct:.1f}%) matched {status}')
        if mismatched[:3]:
            print(f'    Missing: {mismatched[:3]}')
driver.close()
"
```

**기대 결과:** 전체 90%+ 일치율

### 6.6 TREATS/AFFECTS 완전성

Intervention이 존재하지만 TREATS 또는 AFFECTS 관계가 없는 케이스를 탐지합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== TREATS/AFFECTS 완전성 ===')

    # Interventions without TREATS
    r = s.run('''
        MATCH (i:Intervention)
        WHERE NOT (i)-[:TREATS]->()
          AND (i)<-[:INVESTIGATES]-()
        RETURN count(i) AS cnt, collect(i.name)[..5] AS samples
    ''')
    rec = r.single()
    cnt = rec['cnt']; samples = rec['samples']
    print(f'  Intervention (investigated) without TREATS: {cnt}')
    if samples:
        print(f'    Samples: {samples}')

    # Interventions without AFFECTS
    r = s.run('''
        MATCH (i:Intervention)
        WHERE NOT (i)-[:AFFECTS]->()
          AND (i)<-[:INVESTIGATES]-()
        RETURN count(i) AS cnt, collect(i.name)[..5] AS samples
    ''')
    rec = r.single()
    cnt = rec['cnt']; samples = rec['samples']
    print(f'  Intervention (investigated) without AFFECTS: {cnt}')
    if samples:
        print(f'    Samples: {samples}')
driver.close()
"
```

**기대 결과:** 미연결 비율이 전체의 20% 미만

### 6.7 AFFECTS 통계 NULL 비율

AFFECTS 관계에서 p_value, effect_size 속성의 NULL 비율을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== AFFECTS 통계 NULL 비율 ===')
    r = s.run('''
        MATCH ()-[r:AFFECTS]->()
        WITH count(r) AS total,
             sum(CASE WHEN r.p_value IS NOT NULL THEN 1 ELSE 0 END) AS has_pval,
             sum(CASE WHEN r.effect_size IS NOT NULL AND r.effect_size <> \"\" AND r.effect_size <> \"not_reported\" THEN 1 ELSE 0 END) AS has_es,
             sum(CASE WHEN r.is_significant IS NOT NULL THEN 1 ELSE 0 END) AS has_sig,
             sum(CASE WHEN r.direction IS NOT NULL AND r.direction <> \"\" THEN 1 ELSE 0 END) AS has_dir
        RETURN total, has_pval, has_es, has_sig, has_dir,
               CASE WHEN total > 0 THEN round(has_pval * 100.0 / total, 1) ELSE 0 END AS pval_pct,
               CASE WHEN total > 0 THEN round(has_es * 100.0 / total, 1) ELSE 0 END AS es_pct,
               CASE WHEN total > 0 THEN round(has_sig * 100.0 / total, 1) ELSE 0 END AS sig_pct,
               CASE WHEN total > 0 THEN round(has_dir * 100.0 / total, 1) ELSE 0 END AS dir_pct
    ''')
    rec = r.single()
    total = rec['total']
    print(f'  Total AFFECTS relationships: {total}')
    print(f'  p_value present: {rec[\"has_pval\"]}/{total} ({rec[\"pval_pct\"]}%)')
    print(f'  effect_size present: {rec[\"has_es\"]}/{total} ({rec[\"es_pct\"]}%)')
    print(f'  is_significant present: {rec[\"has_sig\"]}/{total} ({rec[\"sig_pct\"]}%)')
    print(f'  direction present: {rec[\"has_dir\"]}/{total} ({rec[\"dir_pct\"]}%)')
driver.close()
"
```

**기대 결과:** p_value 30%+, effect_size 20%+, is_significant 40%+

### 6.8 SNOMED 코드 중복 탐지 (동일 코드 / 다른 이름)

같은 SNOMED 코드가 같은 엔티티 타입에서 다른 이름으로 사용되는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== SNOMED 코드 중복 (동일 코드 / 다른 이름) ===')
    for label in ['Intervention', 'Pathology', 'Outcome', 'Anatomy']:
        r = s.run(f'''
            MATCH (n:{label})
            WHERE n.snomed_code IS NOT NULL AND n.snomed_code <> \"\"
            WITH n.snomed_code AS code, collect(DISTINCT n.name) AS names
            WHERE size(names) > 1
            RETURN code, names
            ORDER BY size(names) DESC
            LIMIT 10
        ''')
        dupes = [(rec['code'], rec['names']) for rec in r]
        status = '✅' if not dupes else '⚠️'
        print(f'  {label}: {len(dupes)} duplicate SNOMED codes {status}')
        for code, names in dupes[:3]:
            print(f'    {code}: {names}')
driver.close()
"
```

**기대 결과:** 중복 SNOMED 코드 = 0 (또는 Known Accepted 목록에 포함된 의도적 공유만)

### 6.9 IS_A 경로 semantic_type 일관성

IS_A 경로에서 자식과 부모의 semantic_type이 일관적인지 확인합니다.
(예: Pathology 노드가 IS_A로 Intervention 노드를 가리키면 오류)

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    print('=== IS_A 경로 라벨 일관성 ===')
    # Check cross-label IS_A (should not exist)
    r = s.run('''
        MATCH (child)-[:IS_A]->(parent)
        WITH labels(child) AS child_labels, labels(parent) AS parent_labels,
             child.name AS child_name, parent.name AS parent_name
        WHERE NONE(l IN child_labels WHERE l IN parent_labels)
        RETURN child_name, child_labels, parent_name, parent_labels
        LIMIT 10
    ''')
    mismatches = [(rec['child_name'], rec['child_labels'], rec['parent_name'], rec['parent_labels']) for rec in r]
    status = '✅' if not mismatches else '❌'
    print(f'  Cross-label IS_A relationships: {len(mismatches)} {status}')
    for cn, cl, pn, pl in mismatches[:5]:
        print(f'    {cn} ({cl}) -[:IS_A]-> {pn} ({pl})')
driver.close()
"
```

**기대 결과:** Cross-label IS_A = 0 (모든 IS_A는 같은 라벨 내에서만 존재)

---

## DV 결과 보고 템플릿

```markdown
# Data Validation Report - vX.Y.Z (YYYY-MM-DD)

## 데이터 현황
- Paper: X개 | Chunk: X개
- Pathology: X | Intervention: X | Outcome: X | Anatomy: X

## Phase 1: 노드 무결성
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 1.1 필수 속성 | ✅/❌ | |
| 1.2 고아 노드 | ✅/⚠️ | 개수: |
| 1.3 중복 노드 | ✅/⚠️ | |
| 1.4 노드 현황 | ℹ️ | Paper: X, Chunk: X |

## Phase 2: 관계 무결성
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 2.1 고립 Paper | ✅/❌ | 개수: |
| 2.2 IS_A 계층 | ✅/❌ | 순환: |
| 2.3 TREATS 백필 | ✅/⚠️ | 미생성: |
| 2.4 AFFECTS 속성 | ✅/⚠️ | p_value 비율: X% |
| 2.5 Taxonomy 리프 | ✅/⚠️ | 미연결 리프: |
| 2.6 INVOLVES 완전성 | ✅/⚠️ | Anatomy 연결률: X% |

## Phase 3: 임베딩 & 검색 품질
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 3.1 Chunk 임베딩 | ✅/❌ | 누락: |
| 3.2 Paper 임베딩 | ✅/⚠️ | 누락: |
| 3.3 벡터 인덱스 | ✅/❌ | |

## Phase 4: 식별자 & SNOMED & 온톨로지
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 4.1 DOI/PMID | ✅/⚠️ | DOI: X%, PMID: X% |
| 4.2 SNOMED 커버리지 | ✅/⚠️ | 미매핑: |
| 4.3 SNOMED 유효성 | ✅/⚠️ | |
| 4.4 SNOMED 중복 | ✅/❌ | 라벨 내: X, 라벨 간: X |
| 4.5 SNOMED 소스 동기화 | ✅/❌ | 불일치: |
| 4.6 Normalizer 커버리지 | ✅/⚠️ | 미커버: |

## Phase 5: 데이터 품질
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 5.1 콘텐츠 품질 | ✅/⚠️ | Abstract: X% |
| 5.2 분포 이상 | ✅/⚠️ | |
| 5.3 중복 논문 | ✅/❌ | |
| 5.4 Chunk 품질 | ✅/❌ | |

## Phase 6: 온톨로지 무결성
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 6.1 IS_A 계층 완전성 | ✅/⚠️ | I:X%, P:X%, O:X%, A:X% |
| 6.2 IS_A 순환 참조 | ✅/❌ | 순환: |
| 6.3 고아 리프 노드 | ✅/⚠️ | 개수: |
| 6.4 SNOMED 커버리지 | ✅/⚠️ | |
| 6.5 parent_code ↔ IS_A 일치 | ✅/❌ | 일치율: |
| 6.6 TREATS/AFFECTS 완전성 | ✅/⚠️ | 미연결: |
| 6.7 AFFECTS 통계 NULL 비율 | ✅/⚠️ | p_value: X% |
| 6.8 SNOMED 중복 탐지 | ✅/⚠️ | |
| 6.9 IS_A 라벨 일관성 | ✅/❌ | Cross-label: |

## 조치 사항
- [ ] (수정 필요한 항목 나열)
```

---

## 부록: 병렬 실행 구조

```
Phase 1 (병렬 4개)     Phase 2 (병렬 6개)     Phase 3 (병렬 3개)
├─ 1.1 필수 속성       ├─ 2.1 고립 Paper       ├─ 3.1 Chunk 임베딩
├─ 1.2 고아 노드       ├─ 2.2 IS_A 계층        ├─ 3.2 Paper 임베딩
├─ 1.3 중복 노드       ├─ 2.3 TREATS 백필      └─ 3.3 벡터 인덱스
└─ 1.4 노드 현황       ├─ 2.4 AFFECTS 속성
                       ├─ 2.5 Taxonomy 리프     Phase 5 (병렬 4개)
Phase 4 (병렬 6개)     └─ 2.6 INVOLVES 완전성   ├─ 5.1 콘텐츠 품질
├─ 4.1 DOI/PMID                                ├─ 5.2 분포 이상
├─ 4.2 SNOMED 커버리지  Phase 6 (병렬 9개)      ├─ 5.3 중복 논문
├─ 4.3 SNOMED 유효성    ├─ 6.1 IS_A 완전성      └─ 5.4 Chunk 품질
├─ 4.4 SNOMED 중복      ├─ 6.2 IS_A 순환
├─ 4.5 SNOMED 소스 동기화├─ 6.3 고아 리프
└─ 4.6 Normalizer 커버리지├─ 6.4 SNOMED 커버리지
                        ├─ 6.5 parent_code 일치
                        ├─ 6.6 TREATS/AFFECTS
                        ├─ 6.7 AFFECTS 통계
                        ├─ 6.8 SNOMED 중복
                        └─ 6.9 IS_A 라벨 일관성
```

**예상 소요 시간:** 전체 약 3-5분 (병렬 실행 시)

---

## 부록: 관련 문서

| 문서 | 역할 |
|------|------|
| [QC_CHECKLIST.md](QC_CHECKLIST.md) | 문서/설정 일관성 점검 (17개 체크) |
| [CODE_AUDIT.md](CODE_AUDIT.md) | 코드 보안/성능/설계 심층 분석 (20개 체크) |
| [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) | Neo4j 노드/관계 스키마 정의 |
| [TERMINOLOGY_ONTOLOGY.md](TERMINOLOGY_ONTOLOGY.md) | SNOMED 매핑, Taxonomy 정의 |

---

## DV Known Accepted Issues (억제 목록)

> 설계 의도이거나 현재 허용하기로 결정한 항목. 스캔 시 이 항목은 ✅(억제)로 표시합니다.
> 항목 추가/제거 시 날짜와 사유를 기록하세요.

| ID | Check | 설명 | 허용 사유 | 등록일 |
|----|-------|------|----------|--------|
| DV-A-001 | 4.4 | Outcome SNOMED 코드 중복 (시점/기법별 변형) | 의도된 설계 v1.21.0: VAS Back preop/6mo/final → 동일 VAS Back 코드 공유 | 2026-02-16 |
| DV-A-002 | 2.5 | Taxonomy 리프 노드 Paper 미연결 | Taxonomy에 미래 논문 분류용 노드 포함 (데이터 없는 것이 정상) | 2026-02-16 |
| DV-A-003 | 2.6 | Basic Science 논문 Anatomy(INVOLVES) 미연결 | 일부 논문은 특정 해부학 위치가 없음 (예: biomechanics, cell biology) | 2026-02-16 |
| DV-A-004 | 5.2 | Evidence level 분포 편중 (retrospective 다수) | 실제 척추 수술 문헌의 자연적 분포 반영 | 2026-02-16 |
| DV-A-005 | 4.4 | Nonunion/Pseudarthrosis/Pseudoarthrosis SNOMED code sharing (58611004) | 의학적 동의어 3종 공유 — v1.24.0에서 Pseudarthrosis 신규 코드 900000000000296 부여 시도했으나 Neo4j에 구 코드(58611004) 잔존. source-Neo4j 불일치로 DV-NEW-013에 재등록 | 2026-02-16 |
| DV-A-006 | 4.4/6.8 | Intervention/Pathology/Anatomy SNOMED 코드 공유 (별칭 노드) | alias 노드들이 원본 노드와 동일 SNOMED 코드를 공유하는 것은 의도된 설계 — 별칭 정규화 이후 병합 예정 | 2026-02-28 |

---

## DV Open Issues (미해결 항목 추적)

> 스캔에서 발견되었으나 아직 수정하지 않은 항목.
> 상태: 🔴 신규 | 🟡 보류(deferred) | ✅ 해소
> **증상 vs 원인 구분**: 데이터 수정만 필요한 것(증상)과 코드 수정이 필요한 것(원인=재발 방지)을 구분

### 작성 규칙
1. 스캔 후 발견된 진짜 문제만 등록 (Known Accepted 항목 제외)
2. 각 이슈에 "증상/원인/둘다" 태그 부여
3. 해소 시 상태를 ✅로 변경하고 해소 버전 기입
4. 다음 스캔 시 이전 미해결 항목 상태도 함께 점검

### 현재 미해결

| ID | Check | 심각도 | 유형 | 설명 | 발견 버전 | 상태 |
|----|-------|--------|------|------|----------|------|
| DV-NEW-006 | 4.2/6.4 | Info | 정보 | SNOMED 커버리지 낮음 — v1.24.0 기준: Intervention 38.1%, Pathology 32.2%, Outcome 21.7% (Anatomy 86.5% OK). 신규 엔티티 폭발적 증가 영향 | v1.23.4 | 🟡 허용 (임포트 시 자연 증가) |
| DV-NEW-009 | 5.3 | Info | 정보 | 동일 제목 Paper 1쌍 (pubmed_41523539 vs pubmed_41559891) — 이중 출판, DOI 상이 | v1.23.4 | 🟡 허용 (실제 중복 아님) |
| DV-NEW-011 | 5.2 | Low | 원인 | study_design 정규화 불일치 (meta-analysis vs meta_analysis, rct vs randomized 등) — v1.24.0에서도 지속 (15종 이상 혼재) | v1.23.4 | 🟡 보류 |
| DV-NEW-012 | 1.1/5.4 | Medium | 증상 | Chunk paper_id NULL 240건 — HAS_CHUNK 관계는 있으나 paper_id 속성 미채움. 이전 수정(DV-NEW-001) 재발 또는 신규 임포트 논문 미처리 | v1.24.0 | 🔴 신규 |
| DV-NEW-013 | 4.5 | Medium | 원인 | SNOMED source↔Neo4j 코드 불일치 다수 — Intervention 1건(BMP: 900000000000622 vs 900000000000180), Pathology 5건(LDH/Discogenic LBP/Pseudarthrosis/ASD/PJK), Outcome 6건(PJK/DVT/ASD/Fluoroscopy/RBC 등). spine_snomed_mappings.py 업데이트 후 Neo4j 미반영 | v1.24.0 | 🔴 신규 |
| DV-NEW-014 | 1.3/4.4 | Medium | 증상 | 대소문자 중복 노드 재발 — Pathology 16쌍, Anatomy 6쌍, Intervention 4쌍, Outcome 5쌍. DV-NEW-003(v1.23.4)에서 Pathology 2쌍 병합 후 신규 임포트로 재발 | v1.24.0 | 🔴 신규 |
| DV-NEW-015 | 6.1 | Low | 정보 | IS_A 계층 커버리지 낮음 — Intervention 45.4%, Pathology 41.1%, Anatomy 28.4%, Outcome 7.8%. 신규 엔티티 대비 IS_A 미생성이 원인 (v1.24.0에서 403관계 추가했으나 엔티티 수 폭증) | v1.24.0 | 🟡 보류 (점진적 개선) |
| DV-NEW-016 | 6.5 | Medium | 원인 | Intervention parent_code↔IS_A 일치율 39.2% — 76건 미일치. 주요 패턴: Interbody Fusion/Posterolateral Fusion 등이 Spine Surgery 직결 대신 계층 없음. spine_snomed_mappings.py parent_code 재정의 또는 IS_A 추가 필요 | v1.24.0 | 🔴 신규 |
| DV-NEW-017 | 2.3 | Low | 증상 | TREATS paper_count 불일치 10건 — MIS-TLIF/BELIF/Discectomy/UBE 등 recorded vs actual 차이 (재스캔: 15→10). 신규 논문 임포트 후 재계산 미실행 | v1.24.0 | 🔴 신규 |
| DV-NEW-018 | 3.2 | Low | 증상 | Abstract 임베딩 누락 1건 — pubmed_39768991 (Robot-Assisted vs Navigation-Based Spine Surgery) abstract 있으나 abstract_embedding NULL | v1.24.0 | 🔴 신규 |
| DV-NEW-019 | 6.3 | Low | 정보 | 고아 리프 노드 16건 — Pathology 3건(Spinal curvature/Alignment Abnormalities/Lordosis), Intervention 10건(AI 관련 측정 도구류), Anatomy 3건(Full spine 변형). IS_A 없고 Paper 미연결 | v1.24.0 | 🟡 보류 (신규 임포트 엔티티) |
| DV-NEW-020 | 6.6 | Low | 증상 | Intervention 'Robot-assisted fusion' AFFECTS 미연결 — INVESTIGATES로 논문 연결됐으나 AFFECTS 관계 생성 안됨 | v1.24.0 | 🔴 신규 |
| DV-NEW-021 | 1.2/5.4 | Low | 증상 | 고아 test Chunk 10건 재발 — DV-NEW-002(v1.23.4)에서 삭제했으나 재생성됨. test/study/paper/integration_test/to_delete/paper_0~2/temp_doc 등 테스트 잔여물. HAS_CHUNK 미연결 | v1.24.0 | 🔴 신규 |
| DV-NEW-022 | 5.4 | Medium | 증상 | Chunk integer tier 재발 240건 — tier=1 (94건), tier=2 (146건). DV-NEW-010(v1.23.4)에서 28건 변환 후 신규 임포트에서 재발. 원인: pubmed_processor 또는 unified_pdf_processor에서 integer tier 생성 | v1.24.0 | 🔴 신규 |

### 해소 완료

| ID | Check | 심각도 | 유형 | 설명 | 발견 버전 | 해소 버전 | 상태 |
|----|-------|--------|------|------|----------|----------|------|
| DV-NEW-001 | 1.1 | Medium | 증상 | 28 Chunks paper_id NULL (7 papers) — HAS_CHUNK 역추적으로 백필 | v1.23.4 | v1.23.4 | ✅ 28건 백필 완료 |
| DV-NEW-002 | 1.2 | Low | 증상 | 10 orphan test Chunk 잔여물 — 삭제 | v1.23.4 | v1.23.4 | ✅ 10건 삭제 |
| DV-NEW-003 | 1.3 | Medium | 증상 | Pathology 대소문자 중복 2쌍 — 관계 이전 후 병합 | v1.23.4 | v1.23.4 | ✅ 2쌍 병합 완료 |
| DV-NEW-004 | 2.1 | Medium | 증상 | 고립 Paper 1건 + HAS_CHUNK 누락 2건 — repair 스크립트 실행 | v1.23.4 | v1.23.4 | ✅ 복구 완료 |
| DV-NEW-005 | 2.3 | Low | 증상 | TREATS paper_count 미설정 50건, 불일치 75건 — 전체 재계산 | v1.23.4 | v1.23.4 | ✅ 2,294건 갱신 |
| DV-NEW-007 | 4.5 | Low | 원인 | Neo4j 전용 SNOMED 7건 source 미동기화 — 6건 추가 (1건 기존 존재) | v1.23.4 | v1.23.4 | ✅ 592개로 확장 |
| DV-NEW-008 | 5.1 | Low | 정보 | authors 누락 35건, year 누락 1건 | v1.23.4 | v1.23.4 | ✅ 정보 확인 (PubMed 재fetch 권장) |
| DV-NEW-010 | 5.4 | Low | 증상 | 28 Chunks integer tier (1,2) → string (tier1,tier2) 변환 | v1.23.4 | v1.23.4 | ✅ 28건 변환 완료 |
| DV-006 | 2.1 | Medium | 증상 | HAS_CHUNK 관계 누락 Paper 6건 — `repair_missing_chunks.py` 실행으로 복구 | v1.22.0 | v1.23.4 | ✅ 6건 복구 완료 (abstract 기반 chunk 생성) |
| DV-007 | 4.5 | Low | 정보 | Neo4j 전용 SNOMED 매핑 — v1.23.1에서 19개 신규 코드 추가 (465개), 나머지 ~521건은 별칭(alias)으로 설계 의도 (Known Accepted) | v1.22.0 | v1.23.1 | ✅ 19개 신규 매핑 추가, 나머지 별칭은 설계 의도 |
| DV-001 | 4.6 | Medium | 원인 | secondary entity 8개 타입 정규화 누락 (RiskFactor, Complication 등) → 대소문자 변형 중복 가능 | v1.21.2 | v1.22.1 | ✅ Cleanup Sprint: `_normalize_secondary_entity()` 추가, 8개 타입 적용 |
| DV-002 | 1.2 | Low | 원인 | snomed_enricher.py Anatomy MERGE 시 정규화 미적용 (segment 분리 후 raw name 사용) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 코드 수정 적용 |
| DV-003 | 1.2 | Low | 증상 | 고아 테스트 Chunk 10개 (Paper 미연결) | v1.22.0 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 10건 삭제 |
| DV-004 | 1.3 | Low | 증상 | Anatomy 대소문자 중복 노드 7건 | v1.22.0 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 7건 병합 |
| DV-005 | 4.5 | Low | 원인 | SNOMED 코드 불일치 (source ↔ Neo4j) | v1.22.0 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 수정 |

---

## DV Scan History (실행 이력)

| 일자 | 버전 | 신규 발견 | 해소 | 잔여 Open | 잔여 Accepted | 비고 |
|------|------|----------|------|----------|--------------|------|
| 2026-02-28 | v1.24.0 | 2 | 0 | 14 | 6 | 전체 6 Phase 재스캔. DV-NEW-021(test chunk 재발 10건), DV-NEW-022(integer tier 재발 240건) 신규 등록. 기존 DV-NEW-012~020 모두 잔존 확인. DV-NEW-017 15→10건 보정. DB: Paper 482, Chunk 8148, Nodes 12632, Rels 27748 |
| 2026-02-28 | v1.24.0 | 9 | 0 | 12 | 6 | DV-NEW-012~020 신규 등록. SNOMED enrichment (I:201/P:130/O:491/A:186), IS_A 403건, TREATS 2688건 반영 후 스캔. DV-A-005 내용 갱신(Pseudarthrosis 코드 불일치 잔존→DV-NEW-013), DV-A-006 신규 등록(alias 노드 코드 공유 허용) |
| 2026-02-17 | v1.23.4 | 11 | 8 | 3 | 5 | DV-NEW-001~011 발견. 8건 즉시 수정 (데이터 백필, 중복 병합, SNOMED 동기화 등). 3건 보류/허용 |
| 2026-02-17 | v1.23.4 | 2 | 2 | 0 | 5 | DV-NEW-001(Anatomy snomed_code 인덱스) 즉시 수정, DV-NEW-002(TERMINOLOGY 버전 태그) 즉시 수정 |
| 2026-02-17 | v1.23.4 | 6 | 8 | 0 | 5 | DV-NEW-001~004: SNOMED 121개 추가(586개), DV-NEW-005/006: 문서 동기화, DV-006: HAS_CHUNK 6건 복구 |
| 2026-02-16 | v1.23.0 | 0 | 0 | 2 | 4 | DV-006 복구 스크립트 준비 (실행 대기) |
| 2026-02-16 | v1.22.1 | 2 | 5 | 2 | 4 | Cleanup Sprint: DV-001~005 해소, DV-006~007 신규 등록 |
| 2026-02-16 | v1.21.2 | 2 | 0 | 2 | 4 | 초기 등록 |
