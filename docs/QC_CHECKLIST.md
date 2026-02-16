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
    'orchestrator.chain_builder',
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
└─ 1.5 Docker 설정      └─ 2.5 Type Hints
```

**예상 소요 시간:** 전체 약 3-5분 (병렬 실행 시)

---

## QC Known Accepted Issues (억제 목록)

> 설계 의도이거나 현재 허용하기로 결정한 항목. 스캔 시 이 항목은 ✅(억제)로 표시합니다.
> 항목 추가/제거 시 날짜와 사유를 기록하세요.

| ID | Check | 설명 | 허용 사유 | 등록일 |
|----|-------|------|----------|--------|
| QC-A-001 | 2.3 | `scripts/`, `__main__` 블록 내 print() 사용 (~110건) | 의도적: CLI 도구의 stdout 출력 | 2026-02-16 |
| QC-A-002 | 2.3 | TODO/FIXME 주석 | CA deferred items(D-005~D-008)로 별도 추적 | 2026-02-16 |
| QC-A-003 | 2.1 | `test_pubmed_enricher::test_enrich_paper_metadata` 실패 | 기존 알려진 이슈: BibliographicMetadata dataclass vs dict 반환 | 2026-02-16 |

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
| QC-001 | 1.1 | Medium | 6개 문서 버전 불일치 (DEPLOYMENT, NEO4J_SETUP, user_guide, MCP_USAGE_GUIDE, developer_guide, SYSTEM_VALIDATION) | v1.21.2 | 🔴 |
| QC-002 | 1.1 | Low | CLAUDE.md Dependencies 섹션 pyproject.toml과 불일치 (openai, neo4j, google-genai, mcp, sentence-transformers) | v1.21.2 | 🔴 |
| QC-003 | 1.1 | Low | DEPLOYMENT.md SNOMED 수치 불일치 (414→447) + entity_normalizer.py 경로 오류 | v1.21.2 | 🔴 |
| QC-004 | 2.4 | Medium | ChromaDB/chroma 잔재 참조 44곳 (solver/, builder/, medical_mcp/) | v1.21.2 | 🔴 |
| QC-005 | 2.4 | Medium | 죽은 코드 파일 5개 (server.py, raptor.py, chain_builder.py, response_synthesizer.py, test_raptor.py) | v1.21.2 | 🔴 |

### 해소 완료

(없음)

---

## QC Scan History (실행 이력)

| 일자 | 버전 | 신규 발견 | 해소 | 잔여 Open | 잔여 Accepted | 비고 |
|------|------|----------|------|----------|--------------|------|
| 2026-02-16 | v1.21.2 | 5 | 0 | 5 | 3 | 초기 등록 |
