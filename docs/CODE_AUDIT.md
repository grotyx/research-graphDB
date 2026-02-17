# Spine GraphRAG - Code Audit (CA) 체크리스트

> **목적**: 코드 품질, 보안, 성능, 설계를 심층 분석하여 기술 부채와 리스크를 사전 탐지
> **대상**: 주요 기능 완성 후, 릴리스 전, 또는 분기별 정기 점검
> **실행**: Claude Code에서 프롬프트 복사 → 붙여넣기로 실행
> **관계**: QC(일관성 점검)와 상호보완 — QC는 "문서와 설정이 맞는가", CA는 "코드가 건강한가"

---

## Quick Start

```
docs/CODE_AUDIT.md의 전체 CA를 실행해줘. 병렬로 처리 가능한 항목은 병렬로 진행해줘.
```

부분 실행:

```
docs/CODE_AUDIT.md의 Phase 1만 실행해줘.
docs/CODE_AUDIT.md의 Phase 3만 실행해줘.
```

## Scan Mode (기본)

스캔은 **보고 전용(Report-Only)** 모드로 실행됩니다:
1. 모든 체크를 실행하고 결과를 보고 템플릿으로 출력
2. "Known Accepted Issues" 목록에 있는 항목은 ✅(억제)로 표시하고 건너뜀
3. 신규 발견 항목은 "CA Deferred Items" 또는 즉시 수정 대상으로 분류
4. **어떤 파일도 수정하지 않음** — 수정은 별도 "Fix" 단계에서 수행

**수정 워크플로우** (4단계):
```
Step 1: SCAN   → "CA 스캔해줘" (보고만, 수정 없음)
Step 2: TRIAGE → 사용자가 각 이슈를 즉시수정/deferred/허용으로 분류
Step 3: FIX    → "CA Phase 2의 print 이슈를 수정해줘" (지정된 항목만)
Step 4: VERIFY → "CA Phase 2만 재스캔해줘" (수정 확인)
```

---

## QC vs CA 비교

| 구분 | QC (Quality Control) | CA (Code Audit) |
|------|---------------------|-----------------|
| 초점 | 문서/설정 일관성 | 코드 품질/설계/보안 |
| 빈도 | 매 버전 릴리스 | 분기별 또는 주요 기능 완성 후 |
| 소요 | 3-5분 | 10-20분 |
| 수정 | 즉시 수정 (문서 업데이트) | 계획 수립 후 점진적 개선 |

---

## Phase 1: 보안 점검 (병렬 실행)

> 외부 입력 처리, 인증 정보, 인젝션 방어를 점검합니다.

### 1.1 Cypher 인젝션 방어

Neo4j 쿼리가 파라미터화되어 있는지 확인합니다. f-string으로 직접 값을 삽입하면 인젝션 위험이 있습니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 Cypher 쿼리 보안을 점검해줘:

1. f-string 안에 MATCH, MERGE, CREATE, SET, DELETE, WHERE가 포함된 패턴 검색
   (예: f"MATCH (n {{id: '{variable}'}})") — 이것은 인젝션 위험
2. 정상 패턴 확인: $param 형태의 파라미터 바인딩 사용 여부
3. orchestrator/cypher_generator.py에서 동적 쿼리 생성 부분 집중 확인

파라미터 바인딩 없이 변수를 직접 삽입하는 곳이 있으면 파일:라인과 함께 알려줘.
```

### 1.2 API 키 노출 방지

API 키가 로그, 에러 메시지, 응답에 노출되지 않는지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 API 키 노출 위험을 점검해줘:

1. api_key, password, secret, token 필드가 포함된 dataclass/dict를 찾고,
   해당 클래스에 __repr__ 또는 __str__이 키를 마스킹하는지 확인
2. logger.error(), logger.exception()에서 config 객체나 dict를
   통째로 출력하는 패턴 검색 (키 노출 위험)
3. except 블록에서 str(e) 또는 repr(e)로 에러 메시지에 키가 포함될 수 있는 경우

위험 패턴이 발견되면 파일:라인과 권장 수정 방향을 알려줘.
```

### 1.3 파일 작업 안전성

PDF 파싱 등 파일 작업이 안전하게 처리되는지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 파일 작업 안전성을 점검해줘:

1. fitz.open() (PyMuPDF) 호출이 try-finally 또는 context manager로 감싸져 있는지
2. open() 호출이 with 문으로 감싸져 있는지
3. tempfile 사용 시 cleanup이 보장되는지 (finally 또는 delete=True)
4. 사용자 입력 파일 경로에 path traversal 방어가 있는지
   (예: "../../../etc/passwd" 같은 경로 차단)

위험 패턴이 발견되면 파일:라인과 함께 알려줘.
```

### 1.4 외부 입력 검증

MCP 도구로 들어오는 외부 입력의 검증/살균을 확인합니다.

**Claude Code 프롬프트:**
```
src/medical_mcp/ 디렉토리에서 입력 검증을 점검해줘:

1. MCP 도구의 arguments에서 사용자 입력을 받는 부분을 식별
2. 각 입력에 대해:
   - 타입 검증이 있는지 (str인지, int인지 등)
   - 길이 제한이 있는지 (매우 긴 입력 방어)
   - 필수/선택 구분이 명확한지
3. DOI, PMID 등 식별자 입력에 포맷 검증이 있는지
   (예: DOI는 10.xxx/xxx 패턴, PMID는 숫자만)

검증이 없거나 부족한 입력 필드를 목록으로 알려줘.
```

---

## Phase 2: 에러 처리 & 관측성 (병렬 실행)

> 에러 처리 품질과 디버깅 용이성을 점검합니다.

### 2.1 Silent Exception 탐지

에러를 삼키는(swallowing) 패턴을 찾습니다. 이는 버그를 숨기는 주요 원인입니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 silent exception 패턴을 찾아줘:

1. "except Exception" 또는 "except BaseException" 뒤에 pass만 있는 경우
2. "except Exception as e" 뒤에 logger 호출 없이 continue/pass/return하는 경우
3. "except:" (bare except) 패턴

각 패턴에 대해 파일:라인을 보여주고, 다음으로 분류해줘:
- CRITICAL: 비즈니스 로직에서 에러 삼킴 (데이터 손실 위험)
- WARNING: 정리/cleanup 코드에서 에러 삼킴 (허용 가능하지만 로깅 권장)
- OK: 의도적인 fallback 패턴 (정상)
```

### 2.2 에러 전파 일관성

커스텀 예외 계층(`core/exceptions.py`)이 실제로 사용되는지 확인합니다.

**Claude Code 프롬프트:**
```
에러 처리 일관성을 점검해줘:

1. core/exceptions.py에 정의된 예외 클래스 목록을 추출
2. src/ 전체에서 이 예외들의 raise/except 사용 빈도를 각각 세기
3. 반대로, 직접 raise Exception("...") 또는 raise ValueError("...")를
   사용하는 곳 검색 — 커스텀 예외 대신 generic exception을 쓰는 곳

커스텀 예외가 정의되어 있지만 사용되지 않는 것,
또는 커스텀 예외 대신 generic exception을 쓰는 곳을 목록으로 알려줘.
```

### 2.3 로깅 품질

로깅이 일관되고 디버깅에 유용한지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 로깅 품질을 점검해줘:

1. print() 사용 현황 (tests/, scripts/ 제외, src/ 내부만)
   - print(f"...", file=sys.stderr) 패턴 포함
   - 총 개수와 상위 5개 파일

2. 로깅 레벨 적절성:
   - logger.debug()에 비즈니스 중요 정보가 있는 경우 (WARNING 이상이어야 할 것)
   - logger.error()에 스택 트레이스 없는 경우 (exc_info=True 누락)

3. 구조화 로깅:
   - 로그 메시지에 context 정보가 포함되는지 (paper_id, operation 등)
   - 단순 "Error occurred" 같은 정보 없는 메시지가 있는지

주요 개선 필요 파일을 우선순위로 알려줘.
```

### 2.4 재시도 & 회복 패턴

외부 서비스 호출(LLM, Neo4j, PubMed)에 재시도/타임아웃이 있는지 확인합니다.

**Claude Code 프롬프트:**
```
외부 서비스 호출의 회복 패턴을 점검해줘:

1. LLM 호출 (anthropic, google.generativeai):
   - 타임아웃 설정이 있는지
   - Rate limit (429) 에러 재시도가 있는지
   - 최대 재시도 횟수와 backoff 전략

2. Neo4j 호출 (neo4j driver):
   - 연결 풀 설정이 있는지
   - 트랜잭션 재시도가 있는지
   - 연결 끊김 시 복구 로직

3. HTTP 호출 (PubMed, DOI resolver 등):
   - requests 타임아웃 설정
   - 재시도 로직
   - 연결 오류 처리

각 서비스별로 현재 상태와 개선점을 알려줘.
```

---

## Phase 3: 성능 & 효율성 (병렬 실행)

> 리소스 사용, 쿼리 효율, 동시성 처리를 점검합니다.

### 3.1 N+1 쿼리 패턴

반복문 안에서 DB/API를 개별 호출하는 N+1 패턴을 찾습니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 N+1 쿼리 패턴을 점검해줘:

1. for/while 루프 안에서 await db.execute, session.run, client.run_query 등
   DB 호출이 있는 패턴 검색
2. for 루프 안에서 await client.generate (LLM 호출) 패턴 검색
   — asyncio.gather로 배치 처리해야 하는 곳
3. for 루프 안에서 requests.get/post (HTTP 호출) 패턴 검색

각 패턴에 대해:
- 파일:라인
- 현재 코드의 의도 (제한된 반복인지, 무제한인지)
- 배치 처리로 개선 가능한지 여부
를 알려줘.
```

### 3.2 메모리 효율성

대량 데이터 처리 시 메모리 문제를 일으킬 수 있는 패턴을 찾습니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 메모리 효율성을 점검해줘:

1. 큰 리스트/딕셔너리를 한 번에 메모리에 올리는 패턴:
   - list(cursor.fetchall()) 또는 [row for row in cursor] 같은 전체 로딩
   - 대량 JSON을 통째로 json.loads하는 경우

2. PDF 처리 시 전체 페이지를 메모리에 올리는지:
   - fitz.open() 후 전체 페이지 텍스트를 리스트로 수집하는지
   - 페이지별 스트리밍 처리를 하는지

3. 캐시 크기 제한:
   - dict를 캐시로 사용하는 경우 maxsize 제한이 있는지
   - LRU/TTL eviction이 구현되어 있는지

잠재적 메모리 이슈 파일:라인과 개선 방향을 알려줘.
```

### 3.3 동시성 & 스레드 안전

비동기 코드와 전역 상태의 안전성을 점검합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 동시성 안전을 점검해줘:

1. 전역 변수(모듈 레벨 변수)가 async 함수에서 수정되는 패턴 검색
   - 예: 모듈 레벨 dict/list에 값을 추가하는 경우
   - _global_*, _instance 등의 전역 변수

2. 싱글톤 패턴의 스레드 안전:
   - ConfigManager, Neo4jClient 등 싱글톤의 초기화가
     race condition에 안전한지 (Lock 사용 여부)

3. asyncio.gather에서 공유 자원 접근:
   - 여러 코루틴이 같은 dict/list를 동시에 수정하는 경우
   - Neo4j 세션을 여러 코루틴이 공유하는 경우

위험도별로 분류해서 알려줘.
```

### 3.4 중복 연산 탐지

같은 작업을 반복하는 비효율적 패턴을 찾습니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 중복 연산 패턴을 점검해줘:

1. 동일한 Neo4j 쿼리를 여러 번 실행하는 패턴:
   - 같은 paper_id로 Paper 노드를 반복 조회
   - 같은 조건으로 MATCH를 반복 실행

2. 임베딩 중복 생성:
   - 같은 텍스트에 대해 임베딩을 여러 번 생성하는 경우
   - 임베딩 캐시가 활용되고 있는지

3. LLM 호출 중복:
   - 같은 프롬프트로 LLM을 여러 번 호출하는 경우
   - LLM 캐시(llm/cache.py)가 실제로 연동되어 있는지

중복이 발견되면 파일:라인과 예상 절약 효과를 알려줘.
```

---

## Phase 4: 설계 & 구조 (병렬 실행)

> 코드 복잡도, 모듈 응집도, 확장성을 평가합니다.

### 4.1 God Object / God File 탐지

단일 파일이 너무 많은 책임을 지고 있는지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 과대 파일을 점검해줘:

1. 1000줄 이상인 .py 파일 목록 (archive/ 제외)
   - 파일명, 줄 수, class 수, def 수를 표로 보여줘

2. 각 과대 파일에 대해:
   - 단일 class가 50개 이상 메서드를 가지는지
   - 파일 내 class가 서로 다른 도메인 책임을 가지는지

3. 분리 권장 사항:
   - 어떤 책임 단위로 분리하면 좋을지 간단히 제안

특히 medical_kag_server.py 집중 분석해줘.
```

### 4.2 코드 중복 탐지

유사한 코드 블록이 여러 곳에 반복되는지 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리에서 코드 중복을 점검해줘:

1. medical_mcp/handlers/ 내 10개 핸들러 파일을 읽고:
   - 공통 패턴 (에러 처리, 로깅, 입력 검증)이 각 파일에 반복되는지
   - BaseHandler 추출이 가능한 공통 코드량 추정

2. cache/ 디렉토리의 3개 캐시 구현 비교:
   - query_cache.py, embedding_cache.py, semantic_cache.py
   - TTL 관리, hit 추적, 만료 정리 등 중복 로직 식별

3. builder/ 디렉토리의 추출기(extractor) 패턴 비교:
   - metadata_extractor.py, entity_extractor.py 등
   - 공통 입출력 패턴이 있는지

각 중복에 대해 추정 중복 줄 수와 리팩토링 방향을 알려줘.
```

### 4.3 의존성 방향 점검

모듈 간 의존성이 깔끔한지 (순환 의존, 역방향 참조 등) 확인합니다.

**Claude Code 프롬프트:**
```
src/ 디렉토리의 모듈 의존성을 점검해줘:

1. 순환 import 탐지:
   - 각 디렉토리(graph, builder, solver, medical_mcp, core, llm, cache, ontology)에서
     import 문을 추출
   - A→B→A 형태의 순환 의존이 있는지 확인

2. 계층 위반 탐지 (의존성 방향):
   - core/ → 다른 모듈 참조 (core는 최하위 계층이므로 위반)
   - solver/ → builder/ 참조 (같은 계층이므로 주의)
   - medical_mcp/ → 모든 모듈 참조 (최상위이므로 정상)

3. 지연 import(lazy import) 사용 현황:
   - 함수 내부에서 import하는 패턴
   - 순환 참조 회피를 위한 것인지, 성능 최적화인지 구분

순환 의존이나 계층 위반이 있으면 파일:라인과 개선 방향을 알려줘.
```

### 4.4 확장성 평가

새 기능 추가 시 변경해야 하는 파일 수를 추정합니다.

**Claude Code 프롬프트:**
```
이 프로젝트의 확장성을 평가해줘. 다음 시나리오 각각에 대해
변경이 필요한 파일 목록과 변경량을 추정해줘:

1. "새 MCP 도구 추가" — 예: paper_compare 도구
   - 몇 개 파일을 수정해야 하는지
   - 새로 만들어야 하는 파일

2. "새 노드 타입 추가" — 예: Instrument (수술 도구) 노드
   - schema, relationship_builder, entity_normalizer, docs 등

3. "새 LLM 프로바이더 추가" — 예: OpenAI GPT
   - llm/ 디렉토리 구조가 플러그인 방식인지
   - 인터페이스/프로토콜이 정의되어 있는지

각 시나리오에서 Open-Closed Principle(확장에 열림, 수정에 닫힘)이
지켜지는지 평가해줘.
```

---

## Phase 5: 테스트 품질 (병렬 실행)

> 테스트 커버리지, 테스트 설계, 테스트 격리를 점검합니다.

### 5.1 테스트 커버리지 분석

어떤 모듈에 테스트가 있고 없는지 매핑합니다.

**Claude Code 프롬프트:**
```
테스트 커버리지를 분석해줘:

1. src/ 하위 각 .py 파일(archive/ 제외)에 대해
   대응하는 테스트 파일이 tests/에 존재하는지 매핑
   - 형식: src/module/file.py → tests/module/test_file.py (있음/없음)

2. 커버리지 요약:
   - 테스트 있는 모듈 수 / 전체 모듈 수
   - 500줄 이상인데 테스트가 없는 파일 목록 (위험도 높음)

3. 테스트 밀도:
   - 테스트 줄 수 / 소스 줄 수 비율
   - 이상적으로 0.5 이상 (테스트가 소스의 50% 이상)

테스트 추가가 가장 시급한 Top 5 모듈을 우선순위로 알려줘.
```

### 5.2 테스트 격리 점검

테스트 간 상태 오염이 없는지 확인합니다.

**Claude Code 프롬프트:**
```
tests/ 디렉토리에서 테스트 격리를 점검해줘:

1. 전역 상태 수정:
   - os.environ을 수정하는 테스트가 fixture에서 복원하는지
   - 싱글톤(_instance)을 리셋하는 테스트가 teardown에서 복원하는지
   - 파일 시스템에 쓰는 테스트가 cleanup하는지

2. 테스트 순서 의존:
   - conftest.py에서 session-scope fixture가 다른 테스트에 영향을 주는지
   - 특정 순서로만 통과하는 테스트가 있는지 (이전 세션에서 발견된 이슈 재확인)

3. Mock 범위:
   - patch가 함수/메서드 수준으로 적절히 제한되어 있는지
   - 모듈 수준 patch가 다른 테스트에 누출되는 경우

문제가 발견되면 파일:라인과 수정 방향을 알려줘.
```

### 5.3 테스트 설계 품질

테스트가 실제 동작을 검증하는지, 구현 세부사항에 결합되지 않는지 확인합니다.

**Claude Code 프롬프트:**
```
tests/ 디렉토리에서 테스트 설계 품질을 점검해줘:

1. 과도한 모킹:
   - 하나의 테스트에서 3개 이상 mock/patch를 사용하는 경우
   - 모든 외부 의존성을 mock하여 아무것도 검증하지 못하는 테스트

2. 엣지 케이스 커버리지:
   - 빈 입력, None 입력, 매우 긴 입력에 대한 테스트 유무
   - 에러 경로 테스트 (네트워크 실패, 타임아웃, 잘못된 응답 등)

3. Assertion 품질:
   - assert True 또는 assert result (단순 truthy 체크)만 있는 테스트
   - 구체적인 값을 검증하지 않는 테스트

개선이 필요한 테스트를 우선순위로 알려줘.
```

---

## Phase 6: 의존성 & 환경 (병렬 실행)

> 외부 패키지, 호환성, 빌드 설정을 점검합니다.

### 6.1 의존성 선언 완전성

코드에서 import하는 패키지가 모두 pyproject.toml에 선언되어 있는지 확인합니다.

**Claude Code 프롬프트:**
```
의존성 선언 완전성을 점검해줘:

1. src/ 디렉토리의 모든 import 문에서 서드파티 패키지 목록 추출
   (표준 라이브러리와 프로젝트 내부 모듈 제외)

2. pyproject.toml의 [project.dependencies]와 비교

3. 코드에서 사용하지만 선언되지 않은 패키지 목록
4. 선언되었지만 코드에서 사용하지 않는 패키지 목록

누락된 의존성은 설치 환경에 따라 런타임 에러를 일으킬 수 있으므로
위험도와 함께 알려줘.
```

### 6.2 의존성 버전 호환

주요 패키지의 최소 버전이 실제 사용 기능과 맞는지 확인합니다.

**Claude Code 프롬프트:**
```
주요 의존성 버전 호환을 점검해줘:

1. pyproject.toml에서 버전 제약이 ">="만 있고 상한이 없는 패키지:
   - 메이저 버전 업데이트 시 breaking change 위험 평가

2. 주요 패키지 호환성:
   - neo4j 드라이버: 코드에서 사용하는 API가 지정된 최소 버전에 존재하는지
   - anthropic: 사용하는 메서드가 최소 버전에서 지원되는지
   - mcp: 프로토콜 버전 호환성

3. Python 버전:
   - pyproject.toml의 python 버전 제약
   - 코드에서 사용하는 Python 3.10+ 기능 (match-case, TypeAlias 등) 확인

호환성 위험이 있는 항목을 알려줘.
```

---

## CA 결과 보고 템플릿

```markdown
# Code Audit Report - vX.Y.Z (YYYY-MM-DD)

## Phase 1: 보안 점검
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 1.1 Cypher 인젝션 | ✅/⚠️/❌ | |
| 1.2 API 키 노출 | ✅/⚠️/❌ | |
| 1.3 파일 작업 | ✅/⚠️/❌ | |
| 1.4 입력 검증 | ✅/⚠️/❌ | |

## Phase 2: 에러 처리 & 관측성
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 2.1 Silent Exception | ✅/⚠️/❌ | 개수: |
| 2.2 예외 일관성 | ✅/⚠️/❌ | |
| 2.3 로깅 품질 | ✅/⚠️/❌ | print 수: |
| 2.4 재시도 패턴 | ✅/⚠️/❌ | |

## Phase 3: 성능 & 효율성
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 3.1 N+1 쿼리 | ✅/⚠️/❌ | 개수: |
| 3.2 메모리 효율 | ✅/⚠️/❌ | |
| 3.3 동시성 안전 | ✅/⚠️/❌ | |
| 3.4 중복 연산 | ✅/⚠️/❌ | |

## Phase 4: 설계 & 구조
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 4.1 God Object | ✅/⚠️/❌ | 1000줄+ 파일 수: |
| 4.2 코드 중복 | ✅/⚠️/❌ | 추정 중복 줄 수: |
| 4.3 의존성 방향 | ✅/⚠️/❌ | 순환: |
| 4.4 확장성 | ✅/⚠️/❌ | |

## Phase 5: 테스트 품질
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 5.1 커버리지 | ✅/⚠️/❌ | 비율: X/Y 모듈 |
| 5.2 격리 | ✅/⚠️/❌ | |
| 5.3 설계 품질 | ✅/⚠️/❌ | |

## Phase 6: 의존성 & 환경
| 항목 | 상태 | 발견 사항 |
|------|------|----------|
| 6.1 선언 완전성 | ✅/⚠️/❌ | 누락: |
| 6.2 버전 호환 | ✅/⚠️/❌ | |

## 위험도별 조치 사항

### 🔴 CRITICAL (즉시 수정)
- [ ] 항목

### 🟡 HIGH (다음 스프린트)
- [ ] 항목

### 🟢 MEDIUM (점진적 개선)
- [ ] 항목

### ℹ️ LOW (참고/모니터링)
- [ ] 항목

## Deferred Items (이번 CA에서 미수정)
> 대규모 아키텍처 변경, 설계 리팩토링 등 즉시 수정이 어려운 항목.
> 반드시 하단 "CA Deferred Items" 섹션에 D-XXX 형식으로 등록할 것.

- [ ] D-XXX: 항목 설명 (Phase X.Y, 심각도, 예상 규모)
```

---

## 부록: 병렬 실행 구조

```
Phase 1 (병렬)         Phase 2 (병렬)         Phase 3 (병렬)
├─ 1.1 Cypher 인젝션   ├─ 2.1 Silent Exception ├─ 3.1 N+1 쿼리
├─ 1.2 API 키 노출     ├─ 2.2 예외 일관성      ├─ 3.2 메모리 효율
├─ 1.3 파일 작업       ├─ 2.3 로깅 품질        ├─ 3.3 동시성 안전
└─ 1.4 입력 검증       └─ 2.4 재시도 패턴      └─ 3.4 중복 연산

Phase 4 (병렬)         Phase 5 (병렬)         Phase 6 (병렬)
├─ 4.1 God Object      ├─ 5.1 커버리지         ├─ 6.1 선언 완전성
├─ 4.2 코드 중복       ├─ 5.2 격리             └─ 6.2 버전 호환
├─ 4.3 의존성 방향     └─ 5.3 설계 품질
└─ 4.4 확장성
```

**예상 소요 시간:** 전체 약 10-20분 (병렬 실행 시)

---

## CA Known Accepted Issues (억제 목록)

> 설계 의도이거나 현재 허용하기로 결정한 항목. 스캔 시 이 항목은 ✅(억제)로 표시합니다.
> 항목 추가/제거 시 날짜와 사유를 기록하세요.

| ID | Check | 설명 | 허용 사유 | 등록일 |
|----|-------|------|----------|--------|
| CA-A-001 | 2.1 | cleanup/fallback 코드의 silent exception | 의도적 fallback 패턴, WARNING 로깅됨 | 2026-02-16 |
| CA-A-002 | 2.3 | `scripts/`, `__main__` 블록 내 print() (~110건) | 의도적: CLI 도구의 stdout 출력 | 2026-02-16 |
| CA-A-003 | 3.1 | LLM 호출 루프 (asyncio.gather 사용 불가한 순차 의존 케이스) | 각 호출이 이전 결과에 의존하여 병렬화 불가 | 2026-02-16 |

---

## CA Scan History (실행 이력)

| 일자 | 버전 | 신규 발견 | 해소 | 잔여 Deferred | 잔여 Accepted | 비고 |
|------|------|----------|------|--------------|--------------|------|
| 2026-02-16 | v1.23.0 | 0 | 2 | 0 | 3 | D-009 (monolith 분해), D-010 (테스트 +250) 해소 |
| 2026-02-16 | v1.22.0 | 2 | 5 | 2 | 3 | Cleanup Sprint: print→logger 9건, TODO, stubs, allowlist, aiohttp 해소. D-009~D-010 신규 등록 |
| 2026-02-16 | v1.22.0 | 0 | 4 | 0 | 3 | D-005~D-008 전체 해소 (팀에이전트 실행) |
| 2026-02-16 | v1.21.0 | 8 | 4 | 4 | 3 | D-001~D-004 해소, D-005~D-008 잔여 |

---

## CA Deferred Items (미수정 항목 추적)

> CA 실행 후 즉시 수정하지 못하는 대규모 아키텍처 변경, 설계 리팩토링 등을 여기에 기록합니다.
> 각 항목에 발견 버전, 예상 난이도, 우선순위를 명시하여 추후 스프린트에서 계획적으로 해소합니다.

### 작성 규칙

1. CA 실행 후 수정하지 못한 항목은 반드시 이 섹션에 추가
2. 해소 시 `상태`를 ✅로 변경하고 해소 버전을 기입
3. 분기별 CA 시 이전 미수정 항목의 진행 상황도 함께 점검

### 현재 미수정 항목

#### D-011: Test Coverage Expansion Phase 2

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.23.0 (CA-NEW-007, 2026-02-17) |
| **Phase** | 5.1 커버리지 |
| **심각도** | Medium |
| **상태** | Open |
| **설명** | 39 modules >= 300 lines lack dedicated test files. Current module coverage is 50% (53/105). |
| **Top 5 Priority Modules** | 1. `src/builder/unified_pdf_processor.py` (1879 lines) / 2. `src/medical_mcp/handlers/writing_guide_handler.py` (1221 lines) / 3. `src/builder/important_citation_processor.py` (1114 lines) / 4. `src/medical_mcp/sse_server.py` (753 lines) / 5. `src/builder/citation_context_extractor.py` (732 lines) |
| **예상 규모** | Large (multi-session) |

### 해소 완료 항목

#### D-009: pubmed_bulk_processor.py 분해 (Monolith Decomposition)

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.22.0 (Cleanup Sprint 2026-02-16) |
| **해소 버전** | v1.23.0 (2026-02-16) |
| **Phase** | 4.1 God Object |
| **상태** | ✅ 해소 |
| **결과** | 462줄 → 3 모듈 분리: `pubmed_downloader.py`(~250줄, PubMedDownloader), `pubmed_processor.py`(~580줄, PubMedPaperProcessor), `pubmed_bulk_processor.py`(~340줄, thin facade). 기존 API 100% 호환. 46개 신규 테스트. |

#### D-010: 테스트 커버리지 확장 (builder/ & solver/)

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.22.0 (Cleanup Sprint 2026-02-16) |
| **해소 버전** | v1.23.0 (2026-02-16) |
| **Phase** | 5.1 커버리지 |
| **상태** | ✅ 해소 |
| **결과** | +250 tests (2342→2592). 4개 신규 확장 테스트: tiered_search(~490줄), hybrid_ranker(~430줄), conflict_detector(~380줄), pdf_processor(~530줄). |

#### Cleanup Sprint v1.22.0 개별 수정 항목 (CA Deferred 외)

| 항목 | 내용 | 해소 버전 |
|------|------|----------|
| print→logger 전환 (9건) | cypher_generator.py 3건, pubmed_enricher.py 3건, pubmed_bulk_processor.py 3건 → logger 전환 | v1.22.0 |
| TODO 해소: reasoner.py line 613 | 해당 TODO 구현 완료 | v1.22.0 |
| Stubs 정리: relationship_builder.py lines 28-100 | 미사용 스텁 코드 삭제 | v1.22.0 |
| pubmed_handler allowlist 추가 | 외부 입력 검증용 allowlist 적용 | v1.22.0 |
| aiohttp 상한 버전 추가 | pyproject.toml에 aiohttp 상한 bound 설정 | v1.22.0 |

#### D-005: Neo4jClient God Object 분리

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.21.0 (CA 2026-02-16) |
| **해소 버전** | v1.22.0 (2026-02-16) |
| **Phase** | 4.1 God Object |
| **상태** | ✅ 해소 |
| **결과** | Composition + Delegation 패턴으로 3개 DAO 추출: `RelationshipDAO`(17 methods), `SearchDAO`(7 methods), `SchemaManager`(4 methods). Neo4jClient에 backward-compatible delegation 유지. |

#### D-006: core/text_chunker.py 계층 위반

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.21.0 (CA 2026-02-16) |
| **해소 버전** | v1.22.0 (2026-02-16) |
| **Phase** | 4.3 의존성 방향 |
| **상태** | ✅ 해소 |
| **결과** | `TieredTextChunker`를 `core/text_chunker.py` → `builder/tiered_text_chunker.py`로 이동. core→builder lazy import 제거, top-level import 전환. |

#### D-007: 테스트 커버리지 확장 (37.9% → 60%+)

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.21.0 (CA 2026-02-16) |
| **해소 버전** | v1.22.0 (2026-02-16) |
| **Phase** | 5.1 커버리지 |
| **상태** | ✅ 해소 |
| **결과** | +530 tests (1830→2360). 20개 신규 테스트 파일: Phase 1(schema, relationships, text_chunker, error_handler, enums, bounded_cache), Phase 2(writing_guide, metadata_extractor, entity_extractor, snomed_api_client, stats_parser, graph_search, section_chunker, citation_context), Phase 3(pdf_processor, citation_processor, multi_hop_reasoning, pubmed_handler, pdf_handler, graph_handler). |

#### D-008: ValueError → 커스텀 예외 전환

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.21.0 (CA 2026-02-16) |
| **해소 버전** | v1.22.0 (2026-02-16) |
| **Phase** | 2.2 예외 일관성 |
| **상태** | ✅ 해소 |
| **결과** | 36건 `raise ValueError/RuntimeError` → `ValidationError`(18), `ProcessingError`(8), `LLMError`(5), `Neo4jError`(1) 전환. `except` 사이트 5곳 업데이트. graph/, builder/, solver/, ontology/, core/, medical_mcp/ 전체 적용. |

#### D-001: MedicalKAGServer God Object 분해

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.19.1 (CA 2026-02-16) |
| **해소 버전** | v1.19.3 (2026-02-16) |
| **Phase** | 4.1 God Object |
| **상태** | ✅ 해소 |
| **결과** | 7,178줄 → 3,982줄 (-45%). Tool Registry 패턴 도입(420줄 if/elif → 10개 dispatcher), 중복 메서드 ~50개 삭제, DOI 메서드 핸들러 이관, rest_api.py 핸들러 라우팅 수정 |

#### D-002: BaseHandler 추출 (핸들러 공통 패턴)

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.19.1 (CA 2026-02-16) |
| **해소 버전** | v1.19.3 (2026-02-16) |
| **Phase** | 4.2 코드 중복 |
| **상태** | ✅ 해소 |
| **결과** | BaseHandler 클래스 생성 (neo4j_client property, _require_neo4j, _ensure_connected, safe_execute 데코레이터). 11개 핸들러 BaseHandler 상속 전환 |

#### D-003: 테스트 커버리지 확장 (31% → 50%+)

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.19.1 (CA 2026-02-16) |
| **해소 버전** | v1.19.3 (2026-02-16) |
| **Phase** | 5.1 커버리지 |
| **상태** | ✅ 해소 |
| **결과** | 228개 테스트 추가 (5개 신규 테스트 파일). reference_formatter(57), spine_snomed_mappings(44), core_nodes(31), extended_nodes(39), clinical_reasoning_engine(57). 총 1,424 테스트 통과 |

#### D-004: print() → logger 전환

| 항목 | 내용 |
|------|------|
| **발견 버전** | v1.19.1 (CA 2026-02-16) |
| **해소 버전** | v1.19.3 (2026-02-16) |
| **Phase** | 2.3 로깅 품질 |
| **상태** | ✅ 해소 |
| **결과** | medical_kag_server.py 모듈 레벨 print(stderr) 22건 → logger.warning/info 전환. 데모/예제 파일(244건)은 의도적 유지 |
