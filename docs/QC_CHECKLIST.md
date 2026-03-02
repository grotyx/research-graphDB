# Spine GraphRAG - QC (Quality Control) 체크리스트

> **목적**: 코드와 문서의 일관성 유지, 오류 사전 탐지, 릴리스 품질 보증
> **대상**: 버전 업데이트, 기능 추가/수정 후 반드시 실행
> **실행**: Claude Code에서 프롬프트 복사 → 붙여넣기로 실행

---

## QC / CA / DV 관계

| 체크리스트 | 대상 | 질문 | 실행 빈도 | 소요 |
|-----------|------|------|----------|------|
| **QC** | 문서/설정/인프라 | "문서가 코드와 맞는가?" | 매 릴리스 | 3-5분 |
| **CA** | 소스 코드 | "코드가 건강한가?" | 분기별 | 10-20분 |
| **DV** | Neo4j DB | "데이터가 완전한가?" | 임포트 후 / 주간 | 3-5분 |

---

## Quick Start

아래 프롬프트를 Claude Code에 붙여넣으면 전체 QC를 자동 실행합니다:

```
docs/QC_CHECKLIST.md의 전체 QC를 실행해줘. 병렬로 처리 가능한 항목은 병렬로 진행해줘.
```

부분 실행도 가능합니다:

```
docs/QC_CHECKLIST.md의 Phase 1만 실행해줘.
docs/QC_CHECKLIST.md의 Phase 2만 실행해줘.
docs/QC_CHECKLIST.md의 Phase 3만 실행해줘.
docs/QC_CHECKLIST.md의 Phase 4만 실행해줘.
docs/QC_CHECKLIST.md의 Phase 5만 실행해줘.
```

## Scan Mode (기본)

스캔은 **보고 전용(Report-Only)** 모드로 실행됩니다:
1. 모든 체크를 실행하고 결과를 보고 템플릿으로 출력
2. "Known Accepted Issues" 목록에 있는 항목은 ✅(억제)로 표시하고 건너뜀
3. 신규 발견 항목은 "Open Issues" 섹션에 등록 제안
4. **어떤 파일도 수정하지 않음** — 수정은 별도 "Fix" 단계에서 수행

**수정 워크플로우** (4단계):
```
Step 1: SCAN   → "QC 스캔해줘" (보고만, 수정 없음)
Step 2: TRIAGE → 사용자가 각 이슈를 수정/보류/허용으로 분류
Step 3: FIX    → "QC-001, QC-003을 수정해줘" (지정된 항목만)
Step 4: VERIFY → "QC Phase 1만 재스캔해줘" (수정 확인)
```

---

## Phase 1: 버전 & 문서 일관성 (병렬 실행)

> 아래 5개 체크를 **모두 병렬로** 실행합니다.

### 1.1 버전 번호 동기화

모든 파일의 버전이 동일한지 확인합니다.

**체크 대상 파일:**

| 파일 | 버전 위치 |
|------|----------|
| `src/__init__.py` | `__version__ = "X.Y.Z"` (Source of Truth) |
| `pyproject.toml` | `version = "X.Y.Z"` |
| `CLAUDE.md` | `**Version**: X.Y.Z` |
| `.env.example` | `# Version: X.Y.Z` |
| `docs/CHANGELOG.md` | 최상단 버전 항목 |
| `docs/DEPLOYMENT.md` | 상단 버전 테이블 |
| `docs/NEO4J_SETUP.md` | 상단 Version 태그 |
| `docs/user_guide.md` | 상단 버전 정보 |
| `docs/PRD.md` | 버전 정보 |

**Claude Code 프롬프트:**
```
다음 파일들에서 버전 번호를 추출해서 일치하는지 비교해줘 (병렬로 읽기):
- src/__init__.py (__version__)
- pyproject.toml (version)
- CLAUDE.md (Version)
- .env.example (Version 주석)
- docs/CHANGELOG.md (최상단 버전)
- docs/DEPLOYMENT.md (버전 테이블)
- docs/NEO4J_SETUP.md (Version 태그)
- docs/user_guide.md (버전 정보)
- docs/PRD.md (버전 정보)

불일치하는 항목이 있으면 보고만 해줘 (수정하지 말 것). src/__init__.py를 Source of Truth로 비교.
```

### 1.2 문서 참조 무결성

CLAUDE.md에 나열된 문서가 실제로 존재하는지, 삭제된 문서 참조가 남아있지 않은지 확인합니다.

**Claude Code 프롬프트:**
```
CLAUDE.md에서 참조하는 모든 문서 파일 경로를 추출하고,
각 파일이 실제로 존재하는지 확인해줘.
존재하지 않는 파일 참조가 있으면 알려줘.
```

### 1.3 MCP 도구 이름 일관성

MCP 서버 코드의 실제 도구 이름과 문서의 도구 이름이 일치하는지 확인합니다.

**체크 대상:**

| 소스 | 파일 |
|------|------|
| 실제 도구 정의 | `src/medical_mcp/medical_kag_server.py` (`name=` 패턴) |
| 사용자 가이드 | `docs/user_guide.md` |
| MCP 가이드 | `docs/MCP_USAGE_GUIDE.md` |

**Claude Code 프롬프트:**
```
src/medical_mcp/medical_kag_server.py에서 name="..." 패턴으로 등록된
MCP 도구 이름과 각 도구의 action 목록을 추출하고, 아래 문서들과 비교해줘:
- docs/user_guide.md
- docs/MCP_USAGE_GUIDE.md
도구 이름 또는 action이 불일치하는 항목이 있으면 알려줘.
```

### 1.4 SNOMED 매핑 통계 일관성

코드의 실제 SNOMED 매핑 수와 문서에 기재된 수가 일치하는지 확인합니다.

**Claude Code 프롬프트:**
```
다음을 병렬로 확인해줘:
1. src/ontology/spine_snomed_mappings.py에서 각 딕셔너리의 실제 엔트리 수 세기
   (SPINE_INTERVENTION_SNOMED, SPINE_PATHOLOGY_SNOMED, SPINE_OUTCOME_SNOMED, SPINE_ANATOMY_SNOMED)
2. CLAUDE.md에 기재된 SNOMED 매핑 수
3. docs/TERMINOLOGY_ONTOLOGY.md에 기재된 매핑 수
4. docs/GRAPH_SCHEMA.md에 기재된 매핑 수
5. docs/DEPLOYMENT.md에 기재된 SNOMED 매핑 수

실제 코드 수와 문서 수가 다르면 보고만 해줘 (수정하지 말 것).
```

### 1.5 Docker/인프라 설정 일관성

docker-compose.yml의 설정과 문서의 기재 사항이 일치하는지 확인합니다.

**Claude Code 프롬프트:**
```
docker-compose.yml의 서비스 설정(포트, 이미지 버전, 환경변수)과
아래 문서들의 기재 사항을 비교해줘:
- docs/HOW_TO_RUN_kr.md
- docs/DEPLOYMENT.md
- docs/NEO4J_SETUP.md
불일치하는 항목이 있으면 알려줘.
```

---

## Phase 2: 코드 품질 (병렬 실행)

> 아래 5개 체크를 **모두 병렬로** 실행합니다.

### 2.1 테스트 실행

전체 테스트 스위트를 실행하여 기능 정상 동작을 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive -v --tb=short 2>&1 | tail -50
```

**기대 결과:** 모든 테스트 PASSED (현재 1400+ 테스트)

### 2.2 Import 오류 체크

모든 주요 모듈이 정상적으로 import 되는지 확인합니다.

**Claude Code 프롬프트:**
```
아래 명령어를 실행해서 주요 모듈 import 오류가 없는지 확인해줘:

PYTHONPATH=./src python3 -c "
modules = [
    'graph.neo4j_client',
    'graph.relationship_builder',
    'graph.entity_normalizer',
    'graph.taxonomy_manager',
    'builder.unified_pdf_processor',
    'builder.pubmed_enricher',
    'builder.reference_formatter',
    'builder.doi_fulltext_fetcher',
    'builder.important_citation_processor',
    'solver.tiered_search',
    'solver.hybrid_ranker',
    'solver.conflict_detector',
    'ontology.spine_snomed_mappings',
    'ontology.snomed_linker',
    'core.config',
    'core.embedding',
    'medical_mcp.medical_kag_server',
]
failed = []
for m in modules:
    try:
        __import__(m)
    except Exception as e:
        failed.append(f'{m}: {e}')
if failed:
    print('FAILED imports:')
    for f in failed: print(f'  {f}')
else:
    print(f'All {len(modules)} modules imported OK')
"
```

### 2.3 Bare Except 및 안티패턴 탐지

코드 품질 이슈를 검사합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 다음 안티패턴을 검색해줘 (병렬로):
1. bare except (except: 만 있고 Exception 타입 없는 것)
2. print() 문 (로깅 대신 print 사용)
3. TODO/FIXME/HACK 주석
4. 하드코딩된 API 키 패턴 (sk-ant-, sk-proj- 등)

각 항목별 파일:라인 목록을 보여줘.
print()는 scripts/와 tests/ 제외하고 src/ 내부만 확인해줘.
```

### 2.4 Deprecated 참조 체크

제거된 모듈이나 레거시 참조가 남아있지 않은지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 다음 deprecated 참조를 검색해줘 (병렬로):
1. "chromadb" 또는 "ChromaDB" 참조 (제거됨)
2. "chroma_client" 참조 (제거됨)
3. storage 모듈의 직접 사용 (deprecated)
4. "gemini" import (llm/gemini_client.py 자체는 제외, 다른 모듈에서의 직접 참조)

각 항목별 파일:라인 목록을 보여줘.
정상적인 fallback/호환성 코드는 제외하고 실제 문제만 보고해줘.
```

### 2.5 Type Hint 커버리지

주요 public 함수에 type hint가 있는지 확인합니다.

**Claude Code 프롬프트:**
```
src/graph/neo4j_client.py, src/builder/unified_pdf_processor.py,
src/solver/tiered_search.py, src/medical_mcp/medical_kag_server.py
에서 def로 시작하는 public 메서드 중 return type hint가 없는 것을 찾아줘.
(__로 시작하는 private 메서드는 제외)
```

---

## Phase 3: 인프라 & 런타임 (순차 실행)

> 이 Phase는 실제 서비스 의존성이 있으므로 **순차적으로** 실행합니다.

### 3.1 Docker 서비스 상태

```bash
cd /Users/sangminpark/Documents/rag_research
docker-compose ps
```

**기대 결과:** neo4j, mcp 컨테이너 모두 `Up (healthy)`

### 3.2 Neo4j 연결 및 스키마 확인

```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    # 연결 확인
    r = s.run('RETURN 1 AS ok')
    print('Connection:', 'OK' if r.single()['ok'] == 1 else 'FAIL')

    # 노드 수 확인
    r = s.run('MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC LIMIT 10')
    print('Node counts:')
    for rec in r:
        print(f'  {rec[\"label\"]}: {rec[\"cnt\"]}')

    # 인덱스 확인
    r = s.run('SHOW INDEXES YIELD name, type RETURN name, type ORDER BY name')
    print('Indexes:')
    for rec in r:
        print(f'  {rec[\"name\"]} ({rec[\"type\"]})')
driver.close()
"
```

### 3.3 임베딩 설정 확인

```bash
cd /Users/sangminpark/Documents/rag_research
PYTHONPATH=./src python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY', '')
anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')
print(f'OpenAI API Key: {\"SET\" if api_key else \"MISSING\"} ({api_key[:10]}...)')
print(f'Anthropic API Key: {\"SET\" if anthropic_key else \"MISSING\"} ({anthropic_key[:10]}...)')
"
```

### 3.4 MCP 서버 Health Check

MCP 서버 상태를 확인하고, 반환 버전이 `src/__init__.py`와 일치하는지 검증합니다.

**Claude Code 프롬프트:**
```
다음을 순차적으로 실행해줘:
1. curl -s http://localhost:7777/health 로 MCP 상태 확인
2. 반환된 JSON의 "version" 필드를 src/__init__.py의 __version__과 비교
3. 불일치하면 docker-compose restart mcp 후 재확인

버전이 다르면 Docker 컨테이너가 오래된 코드를 사용 중이라는 의미이므로
재시작으로 해결되는지 확인해줘.
```

---

## Phase 4: 문서 내용 품질 (병렬 실행)

> 아래 3개 체크를 **모두 병렬로** 실행합니다.

### 4.1 CHANGELOG 최신 버전 항목 확인

**Claude Code 프롬프트:**
```
docs/CHANGELOG.md의 최상단 버전 항목을 읽고:
1. 버전 번호가 src/__init__.py와 일치하는지
2. 날짜가 합리적인지 (미래 날짜가 아닌지)
3. 변경 내용이 실제 코드 변경과 매칭되는지 (최근 5개 git 커밋과 비교)
확인해줘.
```

### 4.2 스키마 문서 vs 실제 코드

**Claude Code 프롬프트:**
```
다음을 비교해줘:
1. docs/GRAPH_SCHEMA.md에 정의된 노드 타입과 관계 타입
2. src/graph/types/schema.py 코드에 정의된 실제 스키마
누락되거나 불일치하는 항목이 있으면 알려줘.
```

### 4.3 Taxonomy 문서 vs 실제 코드

**Claude Code 프롬프트:**
```
다음을 비교해줘:
1. docs/TERMINOLOGY_ONTOLOGY.md에 기재된 Intervention taxonomy 항목 수
2. src/graph/types/schema.py의 get_init_taxonomy_cypher()에 정의된 실제 taxonomy 항목 수
3. src/graph/entity_normalizer.py의 별칭 매핑 수
누락되거나 불일치하는 항목이 있으면 알려줘.
```

---

## Phase 5: 의존성 & 설정 (병렬 실행)

> CA Phase 6(심층 의존성 분석)과 달리, 빠른 헬스체크 수준의 검증입니다.

### 5.1 패키지 의존성 상태

설치된 패키지에 깨진 의존성이 없는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
pip check 2>&1 | head -20
```

**기대 결과:** `No broken requirements found.` 또는 무시 가능한 경고만

### 5.2 환경변수 완전성

`src/core/config.py`에서 참조하는 환경변수가 `.env.example`에 모두 기재되어 있는지 확인합니다.

**Claude Code 프롬프트:**
```
다음을 비교해줘:
1. src/core/config.py에서 os.getenv() 또는 os.environ[]로 참조하는 환경변수 목록 추출
2. .env.example에 기재된 환경변수 목록 추출
3. config.py에서 사용하지만 .env.example에 누락된 변수가 있으면 알려줘

누락된 환경변수는 새 환경 배포 시 설정 실패를 일으킬 수 있으므로 반드시 확인해줘.
```

### 5.3 Git 상태 확인

릴리스 전 커밋되지 않은 변경사항이 없는지 확인합니다.

**명령어:**
```bash
cd /Users/sangminpark/Documents/rag_research
echo "=== Uncommitted Changes ==="
git status --short | head -20

echo ""
echo "=== Untracked Files (src/ docs/ only) ==="
git ls-files --others --exclude-standard src/ docs/ | head -10

echo ""
echo "=== Last 3 Commits ==="
git log --oneline -3
```

**기대 결과:**
- 릴리스 전: 커밋되지 않은 변경 = 0
- 개발 중: 변경사항이 있어도 의도된 것인지 확인

---

## QC 결과 보고 템플릿

```markdown
# QC Report - vX.Y.Z (YYYY-MM-DD)

## Phase 1: 버전 & 문서 일관성
| 항목 | 상태 | 비고 |
|------|------|------|
| 1.1 버전 동기화 | ✅/❌ | |
| 1.2 문서 참조 무결성 | ✅/❌ | |
| 1.3 MCP 도구 이름 | ✅/❌ | |
| 1.4 SNOMED 통계 | ✅/❌ | |
| 1.5 Docker 설정 | ✅/❌ | |

## Phase 2: 코드 품질
| 항목 | 상태 | 비고 |
|------|------|------|
| 2.1 테스트 | ✅ X passed / ❌ X failed | |
| 2.2 Import 체크 | ✅/❌ | |
| 2.3 안티패턴 | ✅/❌ | 개수: |
| 2.4 Deprecated 참조 | ✅/❌ | |
| 2.5 Type Hints | ✅/❌ | |

## Phase 3: 인프라 & 런타임
| 항목 | 상태 | 비고 |
|------|------|------|
| 3.1 Docker 상태 | ✅/❌ | |
| 3.2 Neo4j 연결 | ✅/❌ | 노드 수: |
| 3.3 API 키 | ✅/❌ | |
| 3.4 MCP Health | ✅/❌ | version: |

## Phase 4: 문서 내용 품질
| 항목 | 상태 | 비고 |
|------|------|------|
| 4.1 CHANGELOG | ✅/❌ | |
| 4.2 스키마 문서 | ✅/❌ | |
| 4.3 Taxonomy 문서 | ✅/❌ | |

## Phase 5: 의존성 & 설정
| 항목 | 상태 | 비고 |
|------|------|------|
| 5.1 패키지 의존성 | ✅/❌ | |
| 5.2 환경변수 완전성 | ✅/❌ | |
| 5.3 Git 상태 | ✅/⚠️ | |

## Phase 6: 온톨로지 일관성
| 항목 | 상태 | 비고 |
|------|------|------|
| 6.1 parent_code ↔ IS_A 동기화 | ✅/❌ | |
| 6.2 IS_A 루트 노드 존재 | ✅/❌ | |
| 6.3 SNOMED 검색 사용 | ✅/❌ | |
| 6.4 4-타입 확장 검증 | ✅/❌ | |
| 6.5 graph_relevance_score | ✅/❌ | |
| 6.6 tiered_search SNOMED enrichment | ✅/❌ | |
| 6.7 SNOMED↔normalizer 동기화 | ✅/❌ | orphan: / 충돌: |

## 조치 사항
- [ ] (수정 필요한 항목 나열)

## 억제된 항목 (Known Accepted)
| Check | 억제 ID | 설명 |
|-------|---------|------|
| (해당 항목) | QC-A-XXX | (Known Accepted 사유) |
```

---

## 부록: 병렬 실행 구조

```
Phase 1 (병렬)          Phase 2 (병렬)          Phase 3 (순차)       Phase 4 (병렬)       Phase 5 (병렬)
├─ 1.1 버전 동기화      ├─ 2.1 테스트 실행      ├─ 3.1 Docker       ├─ 4.1 CHANGELOG    ├─ 5.1 pip check
├─ 1.2 문서 참조        ├─ 2.2 Import 체크      ├─ 3.2 Neo4j        ├─ 4.2 스키마 문서   ├─ 5.2 환경변수
├─ 1.3 MCP 도구 이름    ├─ 2.3 안티패턴         ├─ 3.3 API 키       └─ 4.3 Taxonomy     └─ 5.3 Git 상태
├─ 1.4 SNOMED 통계      ├─ 2.4 Deprecated       └─ 3.4 MCP Health
└─ 1.5 Docker 설정      └─ 2.5 Type Hints       Phase 6 (병렬)
                                                 ├─ 6.1 parent_code ↔ IS_A
                                                 ├─ 6.2 IS_A 루트 노드
                                                 ├─ 6.3 SNOMED 검색 사용
                                                 ├─ 6.4 4-타입 확장
                                                 ├─ 6.5 graph_relevance
                                                 ├─ 6.6 tiered_search SNOMED
                                                 └─ 6.7 SNOMED↔normalizer 동기화
```

**예상 소요 시간:** 전체 약 3-5분 (병렬 실행 시)

---

## Phase 6: 온톨로지 일관성 (병렬 실행)

> 4-Entity IS_A 계층 및 SNOMED 온톨로지의 코드-문서-런타임 일관성을 검증합니다.
> **v1.24.0** 신규 추가: Ontology Redesign에 따른 코드/문서 일관성 체크

### 6.1 spine_snomed_mappings.py parent_code ↔ Neo4j IS_A 동기화

SNOMED 매핑의 parent_code 정의와 Neo4j IS_A 관계가 일치하는지 확인합니다.

**Claude Code 프롬프트:**
```
다음을 확인해줘:
1. src/ontology/spine_snomed_mappings.py에서 parent_code가 있는 엔트리 수 (Pathology, Outcome, Anatomy)
2. src/graph/types/schema.py의 get_init_entity_taxonomy_cypher()에서 생성하는 IS_A 쿼리 수
3. 두 숫자가 일치하는지 비교
불일치하면 보고만 해줘 (수정하지 말 것).
```

### 6.2 엔티티 타입별 IS_A 루트 노드 존재 확인

4개 엔티티 타입 모두 루트 노드가 정의되어 있는지 확인합니다.

**Claude Code 프롬프트:**
```
src/ontology/spine_snomed_mappings.py에서 parent_code가 없는(=루트) 엔트리를 각
딕셔너리(SPINE_INTERVENTION_SNOMED, SPINE_PATHOLOGY_SNOMED, SPINE_OUTCOME_SNOMED,
SPINE_ANATOMY_SNOMED)별로 찾아서 보고해줘.
각 엔티티 타입에 최소 1개의 루트가 있어야 합니다.
```

### 6.3 검색 파이프라인 SNOMED 코드 사용 검증

검색 모듈이 SNOMED 코드를 활용하는지 확인합니다.

**Claude Code 프롬프트:**
```
다음 파일들에서 SNOMED 관련 코드 사용을 확인해줘 (병렬로):
1. src/solver/tiered_search.py에서 snomed 관련 참조 (snomed_code, IS_A 등)
2. src/graph/search_dao.py에서 IS_A expansion 관련 코드
3. src/solver/hybrid_ranker.py에서 graph_relevance_score 관련 코드
4. src/orchestrator/query_parser.py에서 SNOMED enrichment 코드
각 파일에서 SNOMED/IS_A 활용 여부를 보고해줘.
```

### 6.4 graph_context_expander 4-타입 확장 검증

그래프 확장 모듈이 4개 엔티티 타입 모두를 지원하는지 확인합니다.

**Claude Code 프롬프트:**
```
src/solver/graph_context_expander.py에서:
1. expand_by_ontology 메서드가 4개 엔티티 타입을 지원하는지
2. expand_pathology_up/down, expand_outcome_up/down, expand_anatomy_up/down 메서드가 존재하는지
3. Intervention 확장 메서드가 존재하는지
각 메서드의 존재 여부와 시그니처를 보고해줘.
```

### 6.5 hybrid_ranker graph_relevance_score 통합 확인

하이브리드 랭커가 graph_relevance_score를 반영하는지 확인합니다.

**Claude Code 프롬프트:**
```
src/solver/hybrid_ranker.py에서:
1. 랭킹 공식에 graph_relevance_score가 포함되어 있는지
2. semantic/authority/graph 3-way 공식의 가중치 합이 1.0인지
3. GRAPH_SCHEMA.md의 Hybrid Ranking Algorithm 문서와 실제 코드가 일치하는지
확인해서 보고해줘.
```

### 6.6 tiered_search SNOMED enrichment 확인

검색 파이프라인이 엔티티를 SNOMED ID로 자동 보강하는지 확인합니다.

**Claude Code 프롬프트:**
```
src/solver/tiered_search.py에서:
1. SNOMED 관련 import 또는 참조가 있는지
2. 엔티티를 snomed_id로 enrichment하는 코드가 있는지
3. entity_normalizer를 활용하여 엔티티를 정규화하는 코드가 있는지
확인해서 보고해줘.
```

### 6.7 SNOMED ↔ entity_normalizer 별칭 동기화

> **v1.24.x 추가**: SNOMED 매핑 확장 시 entity_normalizer 별칭이 누락되면 SNOMED 룩업 체인이 끊어짐.
> 룩업 체인: `text → normalizer canonical → SNOMED dict.get(canonical)` — canonical이 SNOMED key와 불일치하면 미매핑.

spine_snomed_mappings.py의 SNOMED 키가 entity_normalizer.py의 reverse map에서 도달 가능한지 확인합니다.

**Claude Code 프롬프트:**
```
다음을 확인해줘:
1. src/ontology/spine_snomed_mappings.py에서 4개 딕셔너리의 모든 키(key) 목록 추출
2. src/graph/entity_normalizer.py에서 4개 ALIASES 딕셔너리의 모든 canonical 이름 목록 추출
3. SNOMED 키 중 normalizer canonical에 없는 "orphan" 키 수를 엔티티 타입별로 보고
   (leaf 개념 orphan 허용, root/intermediate 개념은 이미 하위 canonical의 alias로 커버될 수 있음)
4. reverse_map last-write-wins 충돌 탐지: 같은 lowercase alias가 2개 이상의 canonical에 등록된 경우 보고
   (나중에 정의된 canonical이 이전 매핑을 덮어쓰므로 의도치 않은 재매핑 발생 가능)

보고만 해줘 (수정하지 말 것).
```

**주의사항:**
- `_build_reverse_map`은 last-write-wins 방식 — 뒤에 정의된 canonical이 같은 lowercase alias를 덮어씀
- 신규 canonical 추가 시 기존 alias 매핑이 의도치 않게 변경될 수 있음 (예: PJK↔PJF, DJK↔DJF 충돌)
- orphan 키는 0이 이상적이나, taxonomy root/intermediate 노드는 허용 가능

---

## QC Known Accepted Issues (억제 목록)

> 설계 의도이거나 현재 허용하기로 결정한 항목. 스캔 시 이 항목은 ✅(억제)로 표시합니다.
> 항목 추가/제거 시 날짜와 사유를 기록하세요.

| ID | Check | 설명 | 허용 사유 | 등록일 |
|----|-------|------|----------|--------|
| QC-A-001 | 2.3 | `scripts/`, `__main__` 블록 내 print() 사용 (~110건) | 의도적: CLI 도구의 stdout 출력 | 2026-02-16 |
| QC-A-002 | 2.3 | TODO/FIXME 주석 | CA deferred items(D-005~D-008)로 별도 추적 | 2026-02-16 |
| ~~QC-A-003~~ | 2.1 | `test_pubmed_enricher::test_enrich_paper_metadata` 실패 | ~~기존 알려진 이슈~~ → **v1.23.0에서 수정 완료** (assertion 강화) | 2026-02-16 |

---

## QC Open Issues (미해결 항목 추적)

> 스캔에서 발견되었으나 아직 수정하지 않은 항목.
> 상태: 🔴 신규 | 🟡 보류(deferred) | ✅ 해소

### 작성 규칙
1. 스캔 후 발견된 진짜 문제만 등록 (Known Accepted 항목 제외)
2. 해소 시 상태를 ✅로 변경하고 해소 버전 기입
3. 다음 스캔 시 이전 미해결 항목 상태도 함께 점검

### 현재 미해결

| ID | Check | 심각도 | 설명 | 발견 버전 | 상태 |
|----|-------|--------|------|----------|------|
| QC-2024-003 | 1.3 (Doc headers) | Info | TROUBLESHOOTING.md, SCHEMA_UPDATE_GUIDE.md — 운영 문서로 버전 헤더 없음 (의도적 허용 가능) | v1.24.0 | 🟡 보류 |

### 해소 완료

| ID | Check | 심각도 | 설명 | 발견 버전 | 해소 버전 | 상태 |
|----|-------|--------|------|----------|----------|------|
| QC-2026-001 | 1.1 | Low | DEPLOYMENT.md 4곳에 v1.24.0 잔존 (tar/scp/verify 명령) | v1.25.0 | v1.25.0 | ✅ v1.25.0으로 수정 |
| QC-2026-002 | 2.5 | Low | medical_kag_server.py type hint 67% (4개 untyped public method: main, list_resources, read_resource, list_prompts) | v1.25.0 | v1.25.0 | ✅ return type hint 추가 |
| QC-2026-003 | 3.4 | Medium | MCP Docker 컨테이너 version 1.24.0 ↔ 소스 1.25.0 불일치 | v1.25.0 | v1.25.0 | ✅ docker-compose restart mcp |
| QC-2026-004 | 6.7 | Low | 31개 orphan SNOMED 키 (IS_A 루트/카테고리 노드) entity_normalizer에 미등록 | v1.25.0 | v1.25.0 | ✅ 30개 canonical 추가 (P:14, O:12, A:1, I:0, alias 3개) |
| QC-2025-001 | 1.2 | Medium | CLAUDE.md에서 참조하는 CA_DEFERRED_PLAN.md, CLEANUP_SPRINT_PLAN.md 파일 미존재 | v1.24.1 | v1.24.1 | ✅ CLAUDE.md에서 참조 제거 |
| QC-2025-002 | 3.4 | Medium | MCP Docker 컨테이너 v1.23.4 ↔ 소스 v1.24.0 불일치 | v1.24.1 | v1.24.1 | ✅ docker-compose restart mcp |
| QC-2025-003 | 1.4 | Low | GRAPH_SCHEMA.md "매핑 통계 (v1.23.4)" 버전 라벨 미갱신 | v1.24.1 | v1.24.1 | ✅ v1.24.0으로 수정 |
| QC-2025-004 | 1.4 | Low | TERMINOLOGY_ONTOLOGY.md "I:11, P:10, O:8, A:5" 합계 오류(34≠32) | v1.24.1 | v1.24.1 | ✅ I:+10, P:+10, O:+7, A:+5로 수정 |
| QC-2025-005 | 4.1 | Low | CHANGELOG 최상단 항목에 버전 번호 없음 | v1.24.1 | v1.24.1 | ✅ v1.24.1 라벨 추가 |
| QC-2025-006 | 1.3 | Low | search 도구 best_evidence/evidence_chain/compare_interventions 미기재 | v1.24.1 | v1.24.1 | ✅ user_guide.md, MCP_USAGE_GUIDE.md에 추가 |
| QC-2025-007 | 6.6 | Info | QC 체크리스트에 query_parser.py 참조 (미존재) | v1.24.1 | v1.24.1 | ✅ tiered_search.py로 수정 |
| QC-2024-008 | 1.4 | Medium | SNOMED 매핑 확장 후 GRAPH_SCHEMA.md, DEPLOYMENT.md 통계 미갱신 (621→653) | v1.24.x | v1.24.x | ✅ 3곳 수정 (GRAPH_SCHEMA 통계표, DEPLOYMENT 3행) |
| QC-2024-001 | 1.4 | Medium | DEPLOYMENT.md SNOMED 통계 구버전 잔존 (592→621) | v1.24.0 | v1.24.0 | ✅ DEPLOYMENT.md line 19 수정 |
| QC-2024-002 | 1.3 | Low | TRD_v3_GraphRAG.md 버전 헤더 미갱신 (1.19.4) | v1.24.0 | v1.24.0 | ✅ 버전 1.24.0으로 갱신 |
| QC-2024-004 | 4.2 | Low | TERMINOLOGY_ONTOLOGY.md root 카운트 오류 (P:7→12, O:8→11) | v1.24.0 | v1.24.0 | ✅ 수치 수정 |
| QC-2024-006 | 3.1 | Low | .gitignore에 data/pdf/, data/extracted/ 미포함 | v1.24.0 | v1.24.0 | ✅ .gitignore에 추가 |
| QC-2024-007 | 4.2 | Low | TERMINOLOGY_ONTOLOGY.md IS_A 행 Intervention-only 기재 | v1.24.0 | v1.24.0 | ✅ 4-entity IS_A로 수정 |
| QC-NEW-004 | 2.2 | Low | `cache.cache_manager` import 실패 (상대 import `..llm.cache`). 절대 import로 전환 | v1.23.4 | v1.23.4 | ✅ semantic_cache.py, cache_manager.py import 수정 |
| QC-NEW-005 | 5.2 | Low | `PUBMED_API_KEY`/`PUBMED_EMAIL` vs `NCBI_API_KEY`/`NCBI_EMAIL` 네이밍 불일치 | v1.23.4 | v1.23.4 | ✅ medical_kag_server.py에 NCBI 우선 fallback 적용 |
| QC-001 | 1.1 | Medium | 6개 문서 버전 불일치 (DEPLOYMENT, NEO4J_SETUP, user_guide, MCP_USAGE_GUIDE, developer_guide, SYSTEM_VALIDATION) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-002 | 1.1 | Low | CLAUDE.md Dependencies 섹션 pyproject.toml과 불일치 (openai, neo4j, google-genai, mcp, sentence-transformers) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-003 | 1.1 | Low | DEPLOYMENT.md SNOMED 수치 불일치 (414→447) + entity_normalizer.py 경로 오류 | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-004 | 2.4 | Medium | ChromaDB/chroma 잔재 참조 44곳 (solver/, builder/, medical_mcp/) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-005 | 2.4 | Medium | 죽은 코드 파일 6개 (server.py, raptor.py, chain_builder.py, response_synthesizer.py, test_raptor.py + orphaned test) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-NEW-1 | 3.4 | Low | MCP Docker 컨테이너 버전 불일치 | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 (재시작, v1.22.0 반영) |
| QC-NEW-2 | 1.1 | Low | .env.example 버전 미갱신 | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-NEW-3 | 1.1 | Low | TERMINOLOGY_ONTOLOGY.md 버전 미갱신 | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 |
| QC-NEW-4 | 2.2 | Low | chain_builder import 오류 (모듈 삭제됨) | v1.21.2 | v1.22.0 | ✅ Cleanup Sprint v1.22.0에서 해결 (파일 자체 삭제) |

---

## QC Scan History (실행 이력)

| 일자 | 버전 | 신규 발견 | 해소 | 잔여 Open | 잔여 Accepted | 비고 |
|------|------|----------|------|----------|--------------|------|
| 2026-03-02 | v1.25.0 | 4 | 4 | 1 | 2 | QC-2026-001~004 발견 및 전체 해소. 001: DEPLOYMENT.md v1.24.0→v1.25.0, 002: type hints 추가, 003: MCP Docker restart, 004: 30개 orphan SNOMED canonical 추가 |
| 2026-02-28 | v1.24.1 | 7 | 7 | 1 | 2 | QC-2025-001~007 발견 및 전체 해소. 001: CLAUDE.md 참조 제거, 002: MCP Docker 재시작, 003: GRAPH_SCHEMA 버전 라벨, 004: TERMINOLOGY 합계, 005: CHANGELOG 버전, 006: search action 문서화, 007: query_parser→tiered_search |
| 2026-02-28 | v1.24.0 | 7 | 5 | 2 | 2 | 7건 발견: QC-2024-001(DEPLOYMENT SNOMED), 002(TRD 버전), 003(운영문서 버전), 004(TERMINOLOGY root), 005(미커밋), 006(.gitignore), 007(IS_A 행). 5건 즉시 수정(001,002,004,006,007). 003 보류, 005 커밋 대기. |
| 2026-02-17 | v1.23.4 | 2 | 2 | 0 | 2 | QC-NEW-004~005 발견 및 즉시 수정 (cache import, env var naming) |
| 2026-02-17 | v1.23.4 | 3 | 3 | 0 | 2 | QC-NEW-001~003 발견 및 즉시 수정 (버전 동기화, SNOMED 카운트) |
| 2026-02-16 | v1.23.0 | 0 | 1 | 0 | 2 | QC-A-003 해소 (test assertion 강화) |
| 2026-02-16 | v1.22.0 | 4 | 9 | 0 | 3 | Cleanup Sprint: QC-001~005 + NEW-1~4 전체 해소 |
| 2026-02-16 | v1.21.2 | 5 | 0 | 5 | 3 | 초기 등록 |
