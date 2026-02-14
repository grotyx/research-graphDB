# Spine GraphRAG Changelog

## Version History

### v7.16.3 (2026-02-14): SNOMED/TREATS/Anatomy 통합 보강 스크립트

파편화된 SNOMED 업데이트 스크립트들을 통합하고, TREATS 관계 백필과 Anatomy 데이터 정리 기능을 추가.

#### 통합 변경

| # | 변경 | 파일 |
|---|------|------|
| 1 | **snomed_enricher.py 신규**: 4개 엔티티 SNOMED 업데이트, TREATS 백필, Anatomy 정리, 커버리지 리포트 코어 모듈 | `src/graph/snomed_enricher.py` |
| 2 | **enrich_graph_snomed.py 신규**: 통합 CLI (all/snomed/treats/anatomy-cleanup/report 서브커맨드) | `scripts/enrich_graph_snomed.py` |
| 3 | **schema.py SNOMED 동적 생성**: 하드코딩 ~220줄 제거 → `spine_snomed_mappings.py`에서 304개 매핑 자동 생성 | `src/graph/types/schema.py` |
| 4 | **enhance_taxonomy_snomed.py 정리**: `ADDITIONAL_SNOMED_MAPPINGS` 하드코딩 ~180줄 제거, `snomed_enricher`에 위임 | `scripts/enhance_taxonomy_snomed.py` |
| 5 | **Anatomy 별칭 확장**: L2-3, L1-2, C3-4, C4-5, C7-T1, T11-12, T12-L1, Multi-level 등 9개 추가 | `src/graph/entity_normalizer.py` |

#### 핵심 기능

- **SNOMED 4개 타입 통합**: Intervention/Pathology/Outcome/Anatomy 모두 EntityNormalizer 기반 자동 매핑
- **TREATS 백필**: Paper→INVESTIGATES→Intervention + Paper→STUDIES→Pathology 패턴으로 추론, 리뷰논문 필터 (4+ I AND 4+ P 제외)
- **Anatomy 다분절 분리**: "L2-4" → ["L2-3", "L3-4"], "C3-C6" → ["C3-4", "C4-5", "C5-6"], 교차영역 "T10-L2" → ["T10-11", "T11-12", "T12-L1", "L1-2"]
- **Single Source of Truth**: `spine_snomed_mappings.py` 하나로 모든 SNOMED 매핑 관리, schema.py·enhance_taxonomy_snomed.py 하드코딩 제거

### v7.16.0 (2026-02-14): PubMed + DOI Fallback 통합 — 항상 보강, 항상 저장

PDF 처리 및 중요 인용 논문 처리 시 PubMed → DOI(Crossref/Unpaywall) → 기본정보 3단계 fallback 체인 도입.

#### 온톨로지 업데이트 (2026-02-14)

| # | 변경 | 파일 |
|---|------|------|
| 1 | **TREATS 관계 구현**: Intervention → Pathology 치료 관계 생성 (Cypher 템플릿 + neo4j_client + relationship_builder 통합) | `schema.py`, `neo4j_client.py`, `relationship_builder.py` |
| 2 | **ANATOMY_ALIASES 신규**: 33개 해부학 위치 별칭 매핑 + `normalize_anatomy()` 메서드 (SNOMED enrichment 포함) | `entity_normalizer.py` |
| 3 | **Schema 노드 alias 추가**: 26개 Intervention 노드에 정규화 별칭 추가 (Bracing, Radiotherapy, Spinopelvic fusion 등) | `entity_normalizer.py` |
| 4 | **SNOMED 매핑 7건 추가**: Intervention 4건 (COWO, Open Decompression, Over-the-top, UBD) + Anatomy 3건 (S2, T10, T11) | `spine_snomed_mappings.py` |
| 5 | **LOCATED_AT, MEASURED_BY**: 미구현 관계 → GRAPH_SCHEMA.md에 "Planned" 표기 | `GRAPH_SCHEMA.md` |

- SNOMED 통계: 140 → 147 → **304개** (I:122, P:84, O:68, A:30) — 공식 142개 + 확장 162개
- 문서 동기화: GRAPH_SCHEMA, TERMINOLOGY_ONTOLOGY, DEPLOYMENT, CLAUDE.md

#### 용어 정규화 확장 (2026-02-14)

| # | 변경 | 파일 |
|---|------|------|
| 1 | **SNOMED 전면 확장**: 147 → 304개 (I:+72, P:+51, O:+34) — 모든 normalizer alias에 SNOMED 매핑 | `spine_snomed_mappings.py` |
| 2 | **P0 alias 갭 해소**: 16개 SNOMED 엔티티에 alias 추가 (Cauda Equina, DM, Deep/Superficial SSI 등) | `entity_normalizer.py` |
| 3 | **카테고리 alias 추가**: Open Decompression, Endoscopic Surgery, Fixation 등 5개 umbrella term | `entity_normalizer.py` |
| 4 | **공식 SNOMED 코드**: Laminoplasty, ESI, RFA, CDR, OPLL, Ankylosing Spondylitis 등 63개 공식 코드 | `spine_snomed_mappings.py` |

#### 신규 기능

| # | 기능 | 파일 |
|---|------|------|
| 1 | **Crossref 서지 검색**: `search_by_bibliographic()` — DOI 없이 제목+저자로 Crossref 검색 | `doi_fulltext_fetcher.py` |
| 2 | **DOIMetadata→BibliographicMetadata 변환**: `from_doi_metadata()` 클래스 메서드 | `pubmed_enricher.py` |
| 3 | **인용 DOI Fallback 체인**: PubMed 실패 → DOI 추출/lookup → Crossref 서지 검색 → basic 노드 | `important_citation_processor.py` |
| 4 | **PDF 처리 DOI Fallback**: PubMed enrichment 실패 시 Crossref/Unpaywall으로 자동 보강 | `medical_kag_server.py` |
| 5 | **기본 인용 노드**: 모든 enrichment 실패 시에도 저자+연도로 Paper 노드 + CITES 관계 생성 | `important_citation_processor.py` |

#### 변경 사항

- `DOIFulltextFetcher`: `search_by_bibliographic(title, authors, year)` 메서드 추가
- `BibliographicMetadata`: `from_doi_metadata()` 클래스 메서드 추가 (`source="crossref"`, `confidence=0.8`)
- `ImportantCitationProcessor.__init__`: `doi_fetcher` 파라미터 추가
- `ImportantCitationProcessor._process_single_citation`: 4단계 fallback (PubMed → DOI → Crossref → Basic)
- `CitationProcessingResult`: `doi_fallback_successes`, `basic_citations_created` 필드 추가
- `MedicalKAGServer._init_components`: `self.doi_fetcher` 초기화
- `MedicalKAGServer._process_with_vision`: PubMed 실패 후 DOI fallback 추가
- `MedicalKAGServer.analyze_text`: PubMed 실패 후 DOI fallback 추가

---

### v7.15.1 (2026-02-14): 런타임 안정성 및 테스트 커버리지 강화

v7.15.0 QC에서 식별된 잔여 저우선도 항목 수정 및 신규 테스트 추가.

#### 버그 수정

| # | 이슈 | 수정 파일 |
|---|------|----------|
| 1 | **Rate Limiter Lock Contention**: `asyncio.sleep()` 중 lock 유지 → lock 해제 후 sleep, while 루프로 재검증 | `claude_client.py` |
| 2 | **Embedding Cache hit_rate 100% 버그**: `_miss_count`/`_hit_count` 미추적 → 인스턴스 변수 추가, get/get_batch에서 추적 | `embedding_cache.py` |
| 3 | **chain_builder factory 크래시**: `TieredVectorDB = None` → try/except import, `Optional[Any]` 파라미터, graceful degradation | `chain_builder.py` |

#### LOW 항목 수정

| # | 카테고리 | 수정 내용 | 파일 |
|---|---------|----------|------|
| 4 | Dead code | `with_fallback` unused import, `ERROR_HANDLER_AVAILABLE` flag, `graph_connectivity` 변수 제거 | `hybrid_ranker.py` |
| 5 | Deprecated | `storage/__init__.py`에 `DeprecationWarning` 추가 | `storage/__init__.py` |
| 6 | Magic numbers | 7개 scoring 상수 추출 (SEMANTIC_WEIGHT, KEY_FINDING_BOOST 등) | `hybrid_ranker.py` |
| 7 | Type hints | `__init__`, `_init_components`, `_init_handlers`에 `-> None` 추가 | `metadata_extractor.py`, `medical_kag_server.py` |
| 8 | Bare except | `except:` → `except Exception:` (2건) | `unified_pdf_processor.py` |
| 9 | Anti-pattern | `'x' in dir()` → `'x' in locals()` | `unified_pdf_processor.py` |
| 10 | Logging | `_LOG_MAX_BYTES`, `_LOG_BACKUP_COUNT` 상수 추출 | `medical_kag_server.py` |

#### 신규 테스트 (4개 파일)

| 테스트 파일 | 테스트 수 | 대상 모듈 |
|------------|----------|----------|
| `tests/orchestrator/test_cypher_generator.py` | ~20 | Cypher 파라미터화, $param 구문, 인텐트별 생성 |
| `tests/graph/test_entity_normalizer.py` | ~60 | 중복 키 alias 보존, SF-12/PJK/DJK/ASD 검증 |
| `tests/solver/test_hybrid_ranker.py` | ~15 | `_merge_results` immutability, scoring 로직 |
| `tests/medical_mcp/test_security.py` | ~10 | 파라미터화 쿼리, path traversal, 소유권 체크 |

---

### v7.15.0 (2026-02-14): 보안 강화 및 코드 품질 개선 (QC)

전체 코드 QC를 수행하여 보안 취약점 7건, 런타임 크래시 4건, 로직 버그 14건을 수정했습니다.
데이터베이스 스키마 변경 없음 — 코드 수준 수정만 포함.

#### P0: Security (Critical)

| # | 이슈 | 수정 파일 |
|---|------|----------|
| 1 | **Cypher Injection**: `_get_user_filter_clause`에서 사용자 입력을 f-string으로 Cypher에 직접 삽입 → `$param` 파라미터화 | `medical_kag_server.py`, `document_handler.py` |
| 2 | **Cypher Injection**: `cypher_generator.py` 전체 `_generate_*` 메서드가 엔티티 이름을 f-string으로 삽입 → 파라미터화된 `(cypher, params)` 튜플 반환으로 전환 | `cypher_generator.py`, `search_handler.py` |
| 3 | **File Path Traversal**: MCP `add_pdf`/`add_json`에서 임의 경로 접근 가능 → 허용 디렉토리 검증 추가 | `pdf_handler.py`, `json_handler.py` |
| 4 | **XSS**: Web UI에서 Neo4j/PubMed 데이터를 `unsafe_allow_html=True`로 HTML escape 없이 렌더링 → `html.escape()` 적용 | `app.py`, `2_PubMed_Import.py`, `3_Knowledge_Graph.py` |

#### P1: Runtime Crash & Logic Bug Fixes

| # | 이슈 | 수정 파일 |
|---|------|----------|
| 5 | `asyncio.run()` — 이미 실행 중인 event loop에서 `RuntimeError` → event loop 감지 후 분기 처리 | `cache_manager.py` |
| 6 | `vector_db`가 `None`일 때 `search_all()` 호출 → `AttributeError` 방지 guard 추가 | `hybrid_ranker.py` |
| 7 | `from .web_scraper import WebMetadata` — 존재하지 않는 모듈 import → 제거, `Any` 타입으로 대체 | `text_chunker.py` |
| 8 | Cypher `WHERE` 절이 `OPTIONAL MATCH` 뒤에 위치하여 유효 결과 행 누락 → `MATCH`와 `OPTIONAL MATCH` 사이로 이동 (3개 쿼리) | `hybrid_ranker.py` |
| 9 | OUTCOME/PATHOLOGY_ALIASES 딕셔너리 중복 키 — `SF-12` 등 5개 엔트리에서 alias 손실 → 중복 merge | `entity_normalizer.py` |
| 10 | `delete_document` 소유권 검증 없음 → 소유권 체크 추가 | `document_handler.py` |
| 11 | `reset_database` 권한 검증 없음 → system 사용자만 허용 | `document_handler.py` |

#### P2: Logic Bug & Quality Improvements

| # | 이슈 | 수정 파일 |
|---|------|----------|
| 12 | `max_tokens` 기본값 불일치 (dataclass 32768 vs _parse_config 8192) → 32768으로 통일 | `config.py` |
| 13 | LLM 비용 계산이 Gemini Flash 가격 사용 → Claude Haiku 4.5 가격으로 변경 | `cache.py` |
| 14 | `_process_text_with_llm`에서 `None` safety 패턴 누락 → `or {}` 패턴 적용 | `pubmed_bulk_processor.py` |
| 15 | `_merge_results`가 입력 객체의 score를 직접 변경 (mutation) → 복사본 사용 | `hybrid_ranker.py` |
| 16 | `metadata_extractor.py` LLM 응답에 JSON repair 없음 → markdown 블록 추출 로직 추가 | `metadata_extractor.py` |
| 17 | Web footer 버전 "v5.3" → "v7.15.0"으로 업데이트 | `app.py` |

#### 수정 파일 목록 (15개)

| 파일 | 수정 항목 |
|------|----------|
| `src/medical_mcp/medical_kag_server.py` | Cypher injection 방지 (파라미터화) |
| `src/medical_mcp/handlers/document_handler.py` | Cypher injection, 삭제 권한, DB reset 권한 |
| `src/medical_mcp/handlers/search_handler.py` | 파라미터화된 Cypher 호출 |
| `src/medical_mcp/handlers/pdf_handler.py` | Path traversal 방지 |
| `src/medical_mcp/handlers/json_handler.py` | Path traversal 방지 |
| `src/orchestrator/cypher_generator.py` | 전체 Cypher 생성 파라미터화 |
| `src/solver/hybrid_ranker.py` | WHERE 절 위치, vector_db guard, score mutation |
| `src/graph/entity_normalizer.py` | 5개 중복 딕셔너리 키 merge |
| `src/cache/cache_manager.py` | asyncio.run() 안전 처리 |
| `src/core/text_chunker.py` | web_scraper import 제거 |
| `src/core/config.py` | max_tokens 기본값 통일 |
| `src/llm/cache.py` | Claude Haiku 가격으로 변경 |
| `src/llm/claude_client.py` | generate_batch 에러 타입 힌트 |
| `src/builder/metadata_extractor.py` | JSON repair 로직 추가 |
| `src/builder/pubmed_bulk_processor.py` | None safety 패턴 |
| `web/app.py` | XSS 방지, 버전 업데이트 |
| `web/pages/2_📚_PubMed_Import.py` | XSS 방지 |
| `web/pages/3_📊_Knowledge_Graph.py` | XSS 방지 |

---

### v7.14.31 (2026-02-13): 26개 저널별 참고문헌 스타일 추가

#### Journal-Specific Reference Styles

**배경**: 기존에는 대부분의 저널이 generic `vancouver` 스타일에 매핑되어 있었으나, 실제로는 같은 Vancouver 기반이라도 저널마다 et al. 기준, DOI 포함 여부, 저널명 이탤릭/볼드 등이 다름

**변경 사항**:
- 26개 저널별 커스텀 `StyleConfig` 생성 (Author Guidelines 기반)
- 57개 저널명 변형(약어 포함) → 스타일 매핑 추가
- 저널명 볼드 처리 지원 추가 (JKNS)
- V7 레거시 코드 정리 (~300+ lines 삭제)
- MCP 서버 `/tools` 엔드포인트 수정
- `aiosqlite`, `google-genai` 의존성 추가

**26개 지원 저널**:

| 카테고리 | 저널 |
|----------|------|
| Spine 전문 (8) | Spine, Spine J, Eur Spine J, Global Spine J, Asian Spine J, J Neurosurg Spine, Spine Deformity, Neurospine |
| 정형외과 (8) | JBJS Am, Bone Joint J, CORR, JAAOS, J Orthop Res, Int Orthop, Clin Orthop Surg, J Orthop Surg Res |
| 신경외과 (6) | J Neurosurg, Neurosurgery, Neurosurg Focus, World Neurosurg, Oper Neurosurg, JKNS |
| 기타 (4) | Pain, J Pain, Medicine, Sci Rep |

**주요 차이점 예시**:

| 저널 | et al. 기준 | DOI | 저널명 포맷 |
|------|-----------|-----|------------|
| Spine (LWW) | 4명→3+et al | X | *이탤릭* |
| JBJS Am | 전원 표기 | X | 일반 |
| Pain (IASP) | 전원 표기 | O | Full name |
| Sci Rep (Nature) | 6명→1+et al | O | *이탤릭*, **볼드** volume |
| JKNS | 7명→6+et al | X | **볼드** |

**수정 파일**:

| 파일 | 수정 내용 |
|------|----------|
| `data/styles/journal_styles.json` | 26개 커스텀 스타일 + 57개 매핑 |
| `src/builder/reference_formatter.py` | DEFAULT_JOURNAL_MAPPINGS 업데이트, bold 지원 |
| `src/medical_mcp/medical_kag_server.py` | V7 레거시 코드 정리 |
| `src/medical_mcp/handlers/pdf_handler.py` | V7 레거시 코드 정리 |
| `src/medical_mcp/sse_server.py` | /tools 엔드포인트 수정 |
| `requirements.txt` | google-genai, aiosqlite 추가 |

---

### v7.14.30 (2026-01-27): 버그 수정 3건

#### 1. PubMed Handler Import 경로 수정

**문제**: `pubmed_handler.py`에서 잘못된 import 경로로 인해 PubMed Bulk Processor가 로드되지 않음

**수정**:
```python
# 수정 전 (잘못된 경로)
from builder.pubmed.pubmed_bulk_processor import PubMedBulkProcessor

# 수정 후 (올바른 경로)
from builder.pubmed_bulk_processor import PubMedBulkProcessor
```

#### 2. 검색 결과 title null 문제 수정

**문제**: `search_handler.py`에서 RankerSearchResult 변환 시 title 필드 누락

**수정**:
```python
# search_handler.py
converted = RankerSearchResult(
    ...
    publication_year=getattr(chunk, 'publication_year', 0),
    title=getattr(chunk, 'title', None)  # v7.14.30: title 필드 추가
)
```

#### 3. CLI Neo4j 인증 오류 수정

**문제**: CLI 스크립트에서 `.env` 파일이 자동 로드되지 않아 Neo4j 인증 실패

**수정**: `neo4j_client.py`에 dotenv 자동 로드 추가
```python
# neo4j_client.py 상단
from dotenv import load_dotenv
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
```

**수정 파일**:

| 파일 | 수정 내용 |
|------|----------|
| `src/medical_mcp/handlers/pubmed_handler.py` | import 경로 수정 |
| `src/medical_mcp/handlers/search_handler.py` | title 필드 추가 |
| `src/graph/neo4j_client.py` | .env 자동 로드 |

---

### v7.14.29 (2026-01-26): 테스트 코드 임베딩 차원 수정

#### 테스트 코드 OpenAI 3072d 임베딩 호환 업데이트

**배경**: v7.14.26에서 MedTE 768d → OpenAI 3072d 전환이 완료되었으나, 테스트 코드의 Mock 값들이 업데이트되지 않아 테스트 실패 발생

**수정 전 테스트 결과**:
- 1,107 passed, **11 failed** (768 vs 3072 차원 불일치)

**수정 후 테스트 결과**:
- 1,111 passed, **7 failed** (+4 테스트 통과)

**수정 파일**:

| 파일 | 수정 내용 |
|------|----------|
| `tests/solver/test_tiered_search.py` | `768` → `3072` (3곳) |
| `tests/solver/test_raptor.py` | `768` → `3072` (전체), `embedding_generator` mock 추가 |

**주요 변경 사항**:

```python
# 수정 전: 768차원 (MedTE)
mock.embed = MagicMock(return_value=[0.1]*768)
assert len(embedding) == 768

# 수정 후: 3072차원 (OpenAI text-embedding-3-large)
mock.embed = MagicMock(return_value=[0.1]*3072)
assert len(embedding) == 3072
```

**RAPTORRetriever 테스트 개선**:
- `embedding_generator` mock 추가하여 OpenAI API 없이도 테스트 가능
- `pipeline.retriever.embedding_generator` 직접 설정

**남은 실패 (7개)**:
- `test_config.py`: 환경변수 기본값 처리 (환경 의존)
- `test_medical_kag_server.py` (6개): 상태 의존성 (개별 실행 시 통과)

---

### v7.14.28 (2026-01-26): SSE 서버 통합 및 코드 중복 제거

#### SSE 서버 통합

**변경 전**:
- `scripts/run_mcp_sse.py`: 간소화된 SSE 서버 (기능 제한)
- `src/medical_mcp/sse_server.py`: 완전한 SSE 서버 (멀티유저, 연결 관리)
- 두 파일 간 중복 코드 및 기능 불일치

**변경 후**:
- `src/medical_mcp/sse_server.py`: **단일 최종 버전** (모든 기능 포함)
- `scripts/run_mcp_sse.py`: sse_server.py를 호출하는 **래퍼 스크립트**

**사용법 (동일)**:

```bash
# 권장: 모듈로 직접 실행
python -m medical_mcp.sse_server --port 8000

# 또는 래퍼 스크립트
python scripts/run_mcp_sse.py --port 8000
```

**SSE 서버 Endpoints**:

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/sse` | GET | SSE 연결 (`?user=<id>` 멀티유저) |
| `/messages` | POST | MCP 메시지 처리 |
| `/health` | GET | 연결 통계 포함 상태 확인 |
| `/ping` | GET | 간단한 생존 확인 |
| `/tools` | GET | MCP 도구 목록 |
| `/users` | GET | 등록된 사용자 목록 |
| `/users/add` | POST | 사용자 추가 (admin) |
| `/connections` | GET | 연결 상세 통계 |
| `/reset` | POST | 서버 캐시 초기화 |
| `/restart` | POST | Neo4j 연결 재설정 |

**수정 파일**:

| 파일 | 변경 |
|------|------|
| `src/medical_mcp/sse_server.py` | v7.14.28 업데이트, 문서화 보강 |
| `scripts/run_mcp_sse.py` | sse_server.py 래퍼로 변환 |

---

### v7.14.27 (2026-01-26): LLM 병렬 처리 + None 값 처리 버그 수정

#### 1. LLM 병렬 처리 지원 (asyncio.to_thread)

**문제**: `PUBMED_MAX_CONCURRENT=10` 설정에도 불구하고 LLM 처리가 순차적으로 실행됨

**원인**: Claude API의 `messages.stream()`이 동기 호출로, asyncio 이벤트 루프를 블로킹

**수정 파일**: `unified_pdf_processor.py` (4곳)

```python
result = await asyncio.to_thread(
    self._backend.process_pdf, path, EXTRACTION_PROMPT
)
```

**효과**: Tier 3 API 사용자 (4000 RPM) 기준 최대 5-8배 처리 속도 향상

#### 2. `.get("key", default)` None 값 처리 버그 수정

**문제**: `'NoneType' object has no attribute 'get'` 에러 발생

**원인**: `.get("key", {})` 패턴이 키가 존재하고 값이 `None`일 때 default 대신 `None` 반환

```python
# 버그: statistics=None이면 None 반환
stats = chunk_dict.get("statistics", {})

# 수정: None이면 {} 반환
stats = chunk_dict.get("statistics") or {}
```

**수정 파일** (11개):

| 파일 | 수정 위치 |
|------|----------|
| `pubmed_bulk_processor.py` | 4곳 (metadata, spine_metadata, chunks, statistics) |
| `medical_kag_server.py` | 3곳 |
| `unified_pdf_processor.py` | 1곳 |
| `json_handler.py` | 1곳 |
| `citation_handler.py` | 1곳 |
| `reference_handler.py` | 1곳 |
| `batch_processor.py` | 2곳 |
| `relationship_builder.py` | 2곳 |

---

### v7.14.26 (2026-01-21): MedTE 768d → OpenAI 3072d 전면 교체

**문제**: Neo4j 벡터 인덱스(3072d)와 MedTE 임베딩(768d) 차원 불일치로 검색 실패

**수정 내용** (MedTE 768d 사용처 전면 제거):

| 파일 | 변경 내용 |
|------|----------|
| `tiered_search.py` | MedTE 폴백 제거 → OpenAI 필수 |
| `raptor.py` | MedTE → OpenAI 변경 (2곳) |
| `pubmed_bulk_processor.py` | MedTE 폴백 제거 → 실패 시 에러 |
| `tiered_search.py:956` | Mock 768d → 3072d |
| `pubmed_handler.py` | None 처리 버그 수정 |

**오류 메시지 개선**:

```text
OPENAI_API_KEY not set - required for vector search (3072d index)
OpenAI embedding required (3072d index)
```

**영향**: `OPENAI_API_KEY` 환경변수 필수 (없으면 벡터 검색/임포트 불가)

---

### v7.14.25 (2026-01-21): 자동 하이브리드 검색 + 스키마 시각화

**1. 자동 하이브리드 검색**:

- `search action=search` 호출 시 **자동으로 하이브리드 검색** 수행
- 로컬 DB 결과가 부족하면 PubMed에서 자동 보완 + 새 논문 자동 임포트

**2. 스키마 시각화 페이지** (📐 Schema Overview):

- **17개 노드 타입**과 **20개+ 관계 타입**을 한눈에 시각화
- 각 노드/관계 타입별 인스턴스 개수 표시
- 3개 탭 구성:
  - 📊 Schema Overview: 노드/관계 전체 구조
  - 🌳 Intervention Taxonomy: IS_A 계층 트리
  - 📈 Detailed Statistics: 상세 통계 대시보드

**새 파일**:
- `web/pages/9_📐_Schema_Overview.py`: 메인 시각화 페이지
- `web/utils/schema_metadata.py`: 스키마 메타데이터 (색상, 설명, 속성)
- `web/utils/graph_utils.py`: 스키마 쿼리 함수 추가

**사용법** (기존과 동일):

```python
# 이제 search만 호출하면 자동으로 하이브리드
search action=search query="lumbar fusion outcomes"

# 로컬 검색만 원할 경우
search action=search query="..." enable_pubmed_fallback=false
```

**새 파라미터** (search action):

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `enable_pubmed_fallback` | True | PubMed 자동 보완 활성화 |
| `min_local_results` | 5 | 이 수 미만이면 PubMed 보완 |
| `pubmed_max_results` | 20 | PubMed 최대 검색 수 |
| `auto_import` | True | 새 논문 자동 임포트 |

**흐름도**:

```text
search action=search query="..."
    ↓
enable_pubmed_fallback=True?
    ├─ Yes → hybrid_search() 호출
    │         ├─ 1) 로컬 검색 (Neo4j)
    │         ├─ 2) 부족하면 PubMed 보완
    │         └─ 3) 새 논문 자동 임포트
    └─ No → 기존 로컬 검색만 수행
```

**코드 변경**:

- **`medical_kag_server.py`**:
  - search tool 스키마에 하이브리드 파라미터 추가
  - search action 핸들러에서 `enable_pubmed_fallback` 분기 처리

---

### v7.14.24 (2026-01-21): PubMed 임포트 최적화 + 하이브리드 검색

**1. 배치 중복 체크 (LLM 처리 전)**:

- 기존: 각 논문마다 개별 중복 체크 후 LLM 처리
- 개선: DB 쿼리 1회로 모든 중복 확인 → 중복 논문은 LLM 처리 없이 즉시 스킵
- 효과: LLM API 비용 절감, 임포트 시간 단축

**2. 하이브리드 검색 (hybrid_search)**:

- **로컬 우선 검색**: 먼저 Neo4j에서 이미 분석된 논문 검색
- **PubMed 보완**: 로컬 결과가 부족하면 PubMed에서 추가 검색
- **자동 임포트**: 새로 찾은 논문은 자동으로 DB에 저장

```text
[검색 흐름]
사용자 쿼리 → 1) Neo4j 검색 (기존 분석된 논문)
            → 2) 부족하면 PubMed 보완 검색
            → 3) 새 논문 자동 임포트
            → 통합 결과 반환
```

**사용법**:

```python
# MCP 도구
pubmed action=hybrid_search query="lumbar fusion outcomes"

# 파라미터
- local_top_k: 로컬 검색 최대 결과 (기본 10)
- min_local_results: 이 수 미만이면 PubMed 보완 (기본 5)
- auto_import: 새 논문 자동 임포트 (기본 True)
- max_results: PubMed 검색 최대 결과 (기본 20)
```

**코드 변경**:

- **`pubmed_bulk_processor.py`**:
  - `_check_existing_papers_batch()`: 여러 PMID 일괄 중복 체크
  - `import_papers()`: LLM 처리 전 배치 중복 체크 로직 추가

- **`pubmed_handler.py`**:
  - `hybrid_search()`: 로컬 우선 + PubMed 보완 검색

- **`medical_kag_server.py`**:
  - `hybrid_search()` 메서드 및 MCP action 추가

---

### v7.14.23 (2026-01-21): PubMed 병렬 임포트 + 환경변수 설정 + DOI 버그 수정

**핵심 기능**:

- **PubMed 병렬 처리**: `PUBMED_MAX_CONCURRENT` 환경변수로 동시 처리 수 제어
  - 기본값: 5, 범위: 1-10
  - 1: 순차 처리 (가장 안전, 느림)
  - 5: 권장 설정 (적절한 속도와 안정성)
  - 10: 최대 (빠르지만 Neo4j/LLM 부하 증가)

- **Neo4j Bolt 스레드 풀**: `NEO4J_BOLT_THREAD_POOL_SIZE` 환경변수로 설정 가능
  - 기본값: 40, 권장: `PUBMED_MAX_CONCURRENT × 4` 이상
  - 변경 후 `docker-compose up -d` 재시작 필요

**환경변수 (.env)**:

```bash
# Neo4j Configuration
NEO4J_BOLT_THREAD_POOL_SIZE=40  # Bolt 스레드 풀 (재시작 필요)

# PubMed Import Configuration
PUBMED_MAX_CONCURRENT=5  # 최대 동시 처리 수 (1-10)
```

**코드 변경**:

- **`pubmed_handler.py`**: `get_max_concurrent()` 함수 추가, 환경변수에서 기본값 읽기
- **`medical_kag_server.py`**: `max_concurrent=None`이면 환경변수 사용
- **`docker-compose.yml`**: Bolt 스레드 풀 설정 추가

**문제 해결**:

- 대량 임포트 시 Neo4j 스레드 풀 고갈 (`NoThreadsAvailable`) 문제 완화
- 하드코딩 제거, 환경변수로 유연한 설정 가능

**버그 수정 (DOI)**:

- **DOI unique constraint 충돌 해결**: "Not provided" 같은 placeholder DOI로 인한 임포트 실패
  - `paper_doi_unique` constraint 삭제, index만 유지
  - `sanitize_doi()` 함수 추가: placeholder DOI를 null로 변환
  - 기존 placeholder DOI 4건 정리

**사용 예시**:

```bash
# .env 파일에서 기본값 설정
PUBMED_MAX_CONCURRENT=5

# MCP 호출 시 기본값 사용
pubmed action=import_by_pmids pmids=["12345678", "23456789"]

# 또는 명시적으로 지정
pubmed action=import_by_pmids pmids=["12345678", "23456789"] max_concurrent=10
```

---

### v7.14.22 (2026-01-20): 테스트 정리 및 버그 수정

**테스트 결과 개선**: 31개 실패 → 7개 실패 (test isolation 문제만 남음)

**버그 수정**:

- **`relationship_builder.py`**: `p_value` (단수) 지원 추가 - `StatisticsData` 클래스 변경 대응
- **`unified_pipeline.py`**: `ConflictSeverity` IntEnum 처리 버그 수정
  - `_check_conflict_severity()`: IntEnum의 `.name` 속성 사용하여 문자열 비교

**테스트 수정**:

- `test_relationship_builder.py`: `StatisticsData(p_value=...)` 형식으로 수정
- `test_response_synthesizer.py`: Mock LLM client 직접 전달, `SearchResult` fixture 필드 추가
- `test_unified_pipeline.py`: Patch 블록 올바르게 중첩, conflict_detector 직접 mock
- `test_evidence_synthesizer.py`: Invalid value 처리 기대값 수정 (skip → 0.0 변환)
- `test_cypher_generator.py`: Text search fallback 허용
- `test_medical_kag_server.py`: ChromaDB/vector_db 제거 반영
- `test_config.py`: Import 경로 `src.core.config` → `core.config`

**테스트 아카이브**:

- `tests/archive/neo4j_integration/`: `test_evidence_synthesis.py`, `test_deletion.py`
- `tests/archive/optional_external/`: `test_vision_processor.py` (GEMINI_API_KEY 필요)

**설정 변경**:

- `pyproject.toml`: `markers = ["integration"]` 추가, `addopts = "-m 'not integration'"` 설정

**최종 테스트 현황**: 1,145 passed, 7 failed (isolation), 14 skipped, 4 deselected

---

### v7.14.21 (2026-01-20): Taxonomy 자동 연결 + Direction 판단 로직 개선 + 문서 일관성 수정

**핵심 개선**:
- **IS_A 자동 연결 기능**: 새 Intervention 발견 시 Taxonomy에 자동 연결
  - `relationship_builder.py`: `link_intervention_to_taxonomy()` 메서드 완성
  - `_determine_parent_intervention()` 추가: 패턴 매칭으로 부모 카테고리 결정
  - Fusion, Endoscopic, Decompression 등 9개 카테고리 자동 매핑
- **Direction 판단 로직 완성**: baseline/final 값 비교로 정확한 방향 결정
  - `_determine_direction()` 개선: 4단계 판단 로직 (baseline/final → intervention/control → effect_size → p-value)
  - `_is_lower_better_outcome()` 추가: VAS, ODI 등 "낮을수록 좋은" 지표 자동 인식
- **공통 조상 쿼리 개선**: 최단 거리 공통 조상 보장
  - `taxonomy_manager.py`: path length 기반 정렬로 가장 가까운 조상 반환
  - total_distance 정보 로깅 추가

**문서 수정**:
- `CLAUDE.md`: `hybrid_ranker.py` → `solver/hybrid_ranker.py` 경로 명시
- `TERMINOLOGY_ONTOLOGY.md`: 버전 7.14.19 → 7.14.21 업데이트

**코드 변경**:
- **`relationship_builder.py`**:
  - `link_intervention_to_taxonomy()`: IS_A 관계 자동 생성 로직 추가
  - `_determine_parent_intervention()`: 카테고리/패턴 기반 부모 결정
  - `_determine_direction()`: baseline/final, effect_size 기반 판단 로직
  - `_is_lower_better_outcome()`: 결과변수 특성 판단
- **`taxonomy_manager.py`**:
  - `find_common_ancestor()`: path length 기반 최단 거리 공통 조상 쿼리

---

### v7.14.20 (2026-01-20): Evidence Chain 개선 + Search 결과 Title 추가 + 테스트 정리

**핵심 개선**:
- **Evidence Chain 벡터 검색 Fallback**: 텍스트 매칭 실패 시 벡터 유사도 검색 자동 시도
  - `graph_handler.py`: `find_evidence_chain()` 메서드에 벡터 검색 fallback 추가
  - 임베딩 생성 후 `hybrid_search()`로 관련 논문 검색
- **Search 결과 Title 필드 추가**: 검색 결과에 논문 제목/연도 포함
  - `search_handler.py`: `formatted_results`에 `title`, `publication_year` 필드 추가
- **Paper Relations 일괄 구축**: 157개 SIMILAR_TOPIC 관계 생성
  - 100개 논문, 4,950개 쌍 비교, min_similarity 0.35 적용
- **테스트 정리**: 90개 실패 → 50개 실패로 개선
  - deprecated 테스트를 `tests/archive/`로 이동 (integration, chain_builder, web_ui)
  - `test_cypher_generator.py`, `test_query_parser_graphrag.py` 현재 구현에 맞게 수정
- **SYSTEM_VALIDATION.md 추가**: 시스템 검증 프롬프트 문서화

**테스트 현황**: 1,228 passed, 50 failed (외부 API 의존), 4 errors

**코드 변경**:
- `graph_handler.py`: 벡터 검색 fallback 추가
- `search_handler.py`: title, publication_year 필드 추가
- `test_cypher_generator.py`: 9개 테스트 수정
- `test_query_parser_graphrag.py`: 5개 테스트 수정

---

### v7.14.19 (2026-01-18): Adaptive Search 버그 수정 + 문서 버전 동기화

**핵심 수정**:
- **Adaptive Search 버그 수정**: `hybrid_search()` 파라미터 오류 해결
  - 문제: `Neo4jClient.hybrid_search()` 호출 시 `query` 인자 대신 `embedding` 인자 필요
  - 해결: 쿼리 임베딩 생성 후 `hybrid_search(embedding=...)` 형태로 호출
  - Fallback: 임베딩 생성 실패 시 일반 tiered search로 자동 전환
- **문서 버전 동기화**: 6개 문서를 v7.14.19로 업데이트
  - `TERMINOLOGY_ONTOLOGY.md`: v7.14.15 → v7.14.19
  - `NEO4J_SETUP.md`: v7.14.15 → v7.14.19
  - `developer_guide.md`: v7.14.15 → v7.14.19
  - `user_guide.md`: v7.14.15 → v7.14.19
  - `MCP_USAGE_GUIDE.md`: v7.14.18 → v7.14.19
  - `TRD_v3_GraphRAG.md`: v7.14.18 → v7.14.19
- **CLAUDE.md 비밀번호 동기화**: `.env` 실제 설정과 일치하도록 수정
  - `spine_graph_2024` → `spineGraph2024`

**코드 변경**:
- **`search_handler.py`** (adaptive_search 메서드):
  - 쿼리 임베딩 생성 로직 추가 (`vector_db.get_embedding()` 또는 `get_embedding_generator()`)
  - `hybrid_search(query=...)` → `hybrid_search(embedding=...)` 수정
  - 임베딩 생성 실패 시 `self.search()` fallback 추가

---

### v7.14.18 (2026-01-18): Graph Search 강화 + MCP 서버 모듈화 + 문서 동기화

**핵심 개선**:
- **Graph Search 강화**: Intervention만 있는 쿼리도 IS_A 계층 기반 검색 지원
  - `cypher_generator.py`: intervention 전용 검색 쿼리 추가 (IS_A 계층 포함)
  - `search_handler.py`: evidence_search에서 intervention only 케이스 처리
  - 기본 검색 쿼리에 title/abstract 검색 추가 (엔티티 미추출 시에도 검색 가능)
- **MCP 서버 모듈화**: medical_kag_server.py 핸들러 위임 리팩토링
  - 8,166줄 → 7,465줄 (701줄 감소, 8.6% 축소)
  - 347KB → 317KB (30KB 감소)
  - 9개 메서드를 handlers/*.py로 위임 (search, graph_search, adaptive_search, reason 등)
- **PubMed 임포트 자동 분류**: 논문 임포트 시 sub_domain, study_design 자동 분류
  - 키워드 기반 분류 알고리즘 적용
  - `import_papers_by_pmids` 메서드에 통합
  - 분류 결과를 임포트 응답에 포함 (`auto_classified` 필드)
- **TRD 문서 동기화**:
  - LLM 선택 명확화: Claude Haiku 4.5 기본, Sonnet 폴백, Gemini 지원
  - MCP 핸들러 11개로 업데이트 (reference_handler.py 추가)
  - Reference Formatter (v7.9), Writing Guide (v7.12) 명시

**분류 지원**:
- **Sub-domain**: Degenerative, Deformity, Trauma, Tumor, Infection, Basic Science
- **Study Design**: meta_analysis, systematic_review, randomized, cohort, case_control, retrospective, case_series

**코드 변경**:

- **`medical_kag_server.py`** (핸들러 위임 리팩토링):
  - `search()` → `SearchHandler.search()` 위임
  - `graph_search()` → `SearchHandler.graph_search()` 위임
  - `adaptive_search()` → `SearchHandler.adaptive_search()` 위임
  - `reason()` → `ReasoningHandler.reason()` 위임
  - `list_documents()` → `DocumentHandler.list_documents()` 위임
  - `get_stats()` → `DocumentHandler.get_stats()` 위임
  - `delete_document()` → `DocumentHandler.delete_document()` 위임
  - `reset_database()` → `DocumentHandler.reset_database()` 위임
  - `export_document()` → `DocumentHandler.export_document()` 위임
- **`cypher_generator.py`**:
  - `_generate_evidence_search()`: intervention only 케이스 추가
  - 기본 검색에 title/abstract CONTAINS 조건 추가
- **`search_handler.py`**:
  - `graph_search()`: intervention only 케이스에서 cypher_generator 쿼리 사용
  - `adaptive_search()`: Neo4j hybrid_search로 마이그레이션 (ChromaDB 제거에 따른 아키텍처 정합성 수정)
- **`pubmed_handler.py`**:
  - `_classify_sub_domain()` 메서드 추가
  - `_classify_study_design()` 메서드 추가
  - `_auto_classify_papers()` 비동기 메서드 추가

**유틸리티 스크립트 추가**:
- `scripts/classify_papers.py`: 기존 논문 일괄 분류
- `scripts/create_abstract_chunks.py`: 초록 기반 청크 생성
- `scripts/update_paper_metadata.py`: JSON 메타데이터 동기화

---

### v7.14.17 (2026-01-14): Neo4j Hybrid Search 통합 - 그래프+벡터 단일 쿼리

**핵심 개선**:
- **Neo4j Hybrid Search 통합**: TieredHybridSearch에서 Neo4j의 `hybrid_search()` 메서드를 직접 활용
  - 그래프 필터링 + 벡터 검색을 단일 Cypher 쿼리로 수행
  - 기존: 벡터 검색과 그래프 검색 분리 → RRF 병합
  - 변경: Neo4j hybrid_search()로 통합 검색 (성능 향상)
  - `SearchSource.BOTH`: vector_score + graph_score 동시 반환

**새로운 설정 옵션**:
- `use_neo4j_hybrid`: Neo4j 통합 하이브리드 검색 사용 여부 (기본값: True)
- 기본 가중치 변경: vector_weight=0.4, graph_weight=0.6 (Evidence 중심)

**코드 변경**:
- **`tiered_search.py`**:
  - `_neo4j_hybrid_search()` 메서드 추가 (라인 572-703)
  - `_search_tier()`에서 hybrid 검색 우선 사용
  - 실패 시 벡터 검색으로 자동 폴백
- **`medical_kag_server.py`**:
  - TieredHybridSearch 초기화 시 `use_neo4j_hybrid=True` 설정

**테스트 결과**:
- 검색 속도: 단일 Cypher 쿼리로 ~20% 성능 향상
- 결과 품질: Evidence level 기반 graph_score와 semantic vector_score 통합
  - Example: vector_score=0.87, graph_score=1.0 → final_score=0.94

---

### v7.14.16 (2026-01-14): 검색 버그 수정 및 Paper-Paper 관계 구축 기능 추가

**버그 수정**:
- **Adaptive Search 버그 수정**: `graph_search()`에 잘못된 `top_k` 파라미터 전달 오류 수정 → `limit` 파라미터로 변경
- **Vector Search 분석**: Neo4j Vector Index 검색이 정상 작동하나 쿼리와 문서 간 의미적 매칭 부족 확인

**새로운 기능**:
- **`build_relations` 액션 추가** (`mcp__medical-kag__graph`):
  - 논문 간 SIMILAR_TOPIC 관계 자동 구축
  - 유사도 계산: Sub-domain(25%) + Pathology(30%) + Intervention(30%) + Anatomy(15%)
  - `min_similarity` 파라미터 (기본값 0.4)로 임계값 조절 가능
  - `max_papers` 파라미터로 비교 대상 논문 수 제한

**문서 업데이트**:
- **CLAUDE.md Project Structure 확장**: 누락된 8개 디렉토리 추가
  - `src/core/`: 설정, 로깅, 예외, 임베딩, 텍스트 청킹
  - `src/cache/`: LLM, 쿼리, 임베딩, 시맨틱 캐시
  - `src/knowledge/`: 인용 추출, 논문 그래프, 관계 추론
  - `src/ontology/`: 개념 계층, SNOMED 링커
  - `src/orchestrator/`: 쿼리 패턴 라우팅, Cypher 생성
  - `src/external/`: PubMed 클라이언트
  - `src/storage/`: (Deprecated) 하위 호환성용

**코드 품질**:
- **GraphHandler 확장**: `build_paper_relations()`, `_calculate_paper_similarity()` 메서드 추가
- **스키마 업데이트**: graph 도구에 `build_relations` 액션 및 `min_similarity` 파라미터 추가

---

### v7.14.15 (2026-01-13): 전체 프로젝트 검증 및 정리

**검색 기능 개선**:

- **Evidence Search 수정**: p_value 문자열 처리 (`"<0.001"` 등) 안전하게 파싱
- **Adaptive Search Fallback**: VectorDB 없을 때 graph_search로 자동 전환
- **Taxonomy 기반 검색**: find_evidence에서 하위 intervention도 함께 검색 (TLIF → MIS-TLIF, BELIF 포함)
- **재색인 스크립트**: `scripts/reindex_relationships.py` 추가 - 4301개 관계 재구축

**코드 품질 개선**:
- **Neo4jClient 메서드 추가**: `create_supports_relation()`, `create_contradicts_relation()`, `create_cites_relation()` 3개 편의 메서드 추가
- **SNOMED 중복 코드 수정**:
  - "Wound Dehiscence" 공식 코드(225553008)로 통일
  - "Adjacent Segment Disease" Outcome에서 "ASD Reoperation Rate"로 재명명
  - **"Spinal TB" 중복 수정**: 5765005 → 186570004 (공식 SNOMED "Tuberculosis of spine")
- **reasoner.py 타입힌트 수정**: `from __future__ import annotations` 추가, `Union` import 추가
- **medical_kag_server.py 수정**: 존재하지 않는 `self.unified_processor_v7` → `self.v7_processor`로 수정
- **unified_pdf_processor.py**: 잘못된 deprecation 헤더 제거 (현재 메인 프로세서임)

**Taxonomy Alias 추가** (`schema.py`):

- **ADR**: `cTDR`, `lTDR` alias 추가 (cervical/lumbar Total Disc Replacement)
- **Interspinous Device**: `ISD`, `X-STOP` alias 추가

**버전 동기화 (전체 문서)**:
- `docs/QUICK_REFERENCE.md`: v3.1.1 → v7.14.15
- `docs/api/advanced_rag.md`: 3.1 → 7.14.15, GraphRAG 2.0 아카이브 표시 추가
- `docs/SCHEMA_UPDATE_GUIDE.md`: v7.14.2 → v7.14.15
- `docs/TERMINOLOGY_ONTOLOGY.md`: 통계 정확도 보정 (142→140 엔티티, 62.0%→62.9% 커버리지)
- `docs/GRAPH_SCHEMA.md`: Deprecated 노드 표시 추가 (Technique, SurgicalStep, Instrument)
- `docs/MCP_USAGE_GUIDE.md`: `prepare_prompt` 액션 문서화 추가

**레거시 파일 정리**:
- **아카이브된 파일** (`src/archive/legacy_v7/`):
  - `unified_processor_v7.py`: unified_pdf_processor.py로 대체됨
  - `graph_rag_v2.py`, `README_graph_rag_v2.md`: 실험적 Microsoft-style GraphRAG
- **아카이브된 스크립트/테스트** (`scripts/archive/`):
  - `test_phase3_neo4j_search.py`, `test_phase4_neo4j_only.py`: Phase 3-4 테스트
  - `test_v7_processor.py`: v7 프로세서 테스트
  - `poc_neo4j_vector.py`: POC 스크립트
  - `test_graph_rag_v2.py`: 아카이브된 graph_rag_v2.py 테스트
- **캐시 정리**: `__pycache__/` 디렉토리 정리

**SNOMED 통계 (정확한 값)**:
| 카테고리 | 전체 | 공식 | 확장 | 커버리지 |
|----------|------|------|------|----------|
| Interventions | 46 | 25 | 21 | 54.3% |
| Pathologies | 33 | 27 | 6 | 81.8% |
| Outcomes | 34 | 15 | 19 | 44.1% |
| Anatomy | 27 | 21 | 6 | 77.8% |
| **Total** | **140** | **88** | **52** | **62.9%** |

---

### v7.14.14 (2025-12-31): SNOMED-CT 패턴 매핑 대규모 확장

**SNOMED-CT 패턴 기반 자동 매핑** - 전체 커버리지 60.6% 달성:

| 엔티티 | 이전 | 이후 | 증가 |
|--------|------|------|------|
| **Anatomy** | 24.8% | **87.2%** | +62.4%p |
| **Pathology** | 20.2% | **66.1%** | +45.9%p |
| **Outcome** | 4.9% | **60.0%** | +55.1%p |
| **Intervention** | 19.9% | **46.6%** | +26.7%p |
| **전체** | ~15% | **60.6%** | +45%p |

**패턴 매핑 방식**:
- 엔티티 이름에서 키워드 패턴 매칭으로 SNOMED 코드 자동 할당
- 예: "VAS back pain" → VAS 패턴 매칭 → SNOMED:273903006
- 예: "L4-L5 disc herniation" → Herniation 패턴 → SNOMED:76107001

**매핑된 주요 카테고리**:
- **Outcome (374개 신규)**: AUC/Accuracy (ML 성능), VAS/NRS (통증), ODI/NDI (기능), Fusion Rate, Complication
- **Anatomy (73개 신규)**: 척추 레벨 (C1-S2), 구조물, 신경, 인대, 근육
- **Pathology (84개 신규)**: Stenosis, Herniation, Myelopathy, Fracture, Tumor, Infection
- **Intervention (71개 신규)**: Fusion, Decompression, Endoscopic, Fixation, Injection

---

### v7.14.13 (2025-12-31): Taxonomy & SNOMED-CT 기초 강화

**Taxonomy 구조 개선**:
- Orphan Intervention 노드 대폭 감소: 112개 → 22개 (90개 연결)
- 새로운 카테고리 7개 생성:
  - `AI/ML-Based Tools`: ML, Radiomics, SegFormer, YOLO 등 AI 기반 도구
  - `Digital Therapeutics`: VR 장치, SaMD, Biofeedback 등 DTx
  - `Robotic Surgery`: Mazor X 등 로봇 수술
  - `Bariatric Surgery`: 비만 수술 (RYGB, gastric banding 등)
  - `Other Surgical Procedures`: 기타 수술
  - `Outcome Assessment`: 결과 측정 연구
  - `Minimally Invasive Surgery`: MIS 통합 카테고리
- 97개 IS_A 관계 추가로 계층 구조 완성

**SNOMED-CT 기초 매핑**:
- 수동 매핑으로 주요 용어 ~150개 직접 매핑
- Anatomy, Intervention, Pathology, Outcome 기본 커버리지 확보

**신규 스크립트**:
- `scripts/enhance_taxonomy_snomed.py`: Taxonomy/SNOMED 일괄 강화 스크립트

---

### v7.14.12 (2025-12-31): ChromaDB 완전 제거 & Database Maintenance

**Breaking Change: ChromaDB 의존성 완전 제거**

이제 Neo4j Vector Index가 **유일한** 벡터 저장소입니다.

- **삭제된 파일**:
  - `src/core/vector_db.py`: ChromaDB VectorDBManager 삭제
  - `src/storage/vector_db.py`: TieredVectorDB 삭제
  - `src/solver/README_RAPTOR.md`, `README_multi_hop.md`, `README_unified_pipeline.md`: 레거시 문서 삭제
  - `src/cache/integration_example.py`: 레거시 예제 삭제
  - `tests/storage/test_vector_db.py`: 레거시 테스트 삭제

- **수정된 파일**:
  - `src/storage/__init__.py`: TextChunk, SearchFilters를 하위 호환성 위해 유지
  - `src/solver/tiered_search.py`: SearchBackend.CHROMADB 제거, NEO4J만 지원
  - `src/solver/hybrid_ranker.py`: ChromaDB 참조 제거
  - `src/core/config.py`, `src/core/exceptions.py`: ChromaDBConfig, ChromaDBError DEPRECATED 표시
  - `src/medical_mcp/medical_kag_server.py`: storage import 경로 수정
  - `src/builder/pubmed_bulk_processor.py`: storage import 경로 수정
  - `src/builder/gemini_vision_processor.py`: TableData, FigureData import 제거

- **Paper Abstract 임베딩 자동 생성 (신규 기능)**:
  - `neo4j_client.create_paper()`: abstract_embedding 자동 생성 (기본 활성화)
  - `pubmed_bulk_processor.create_paper_node()`: abstract_embedding 자동 생성
  - PDF 또는 PubMed에서 논문 추가 시 자동으로 abstract 임베딩 생성
  - 기존 237개 Paper에 abstract_embedding 일괄 생성 (99.6% 커버리지)

- **Taxonomy 보강**:
  - 미연결 Intervention 노드 정비: 164개 → 109개 (55개 연결)
  - 새로운 상위 카테고리 추가: AI/Algorithm, 3D Printing, Bone Grafting, Diagnostic Imaging 등
  - 패턴 기반 IS_A 관계 자동 연결 (Endoscopic, Fusion, Cage, Screw 등)

- **SNOMED Enrichment 적용**:
  - 기존 노드에 SNOMED 코드 일괄 적용 (9개 배치 쿼리)
  - 커버리지: Intervention 16.5%, Pathology 15.3%, Outcome 3.4%, Anatomy 17.9%

- **Pathology 카테고리 정비**:
  - 카테고리 없는 Pathology 노드 분류: 107개 → 104개
  - 패턴 기반 자동 분류 (Myelopathy, Radiculopathy, Scoliosis 등)

- **MCP Search 향상 - Endoscopic 키워드 확장**:
  - `find_evidence()`: "Endoscopic" 검색 시 모든 내시경 수술 variants 포함
  - 검색 대상: UBE, BELIF, FESS, PELD, MED, FELD, BE-, Biportal, Full-endoscopic
  - Entity Normalization + IS_A hierarchy 적용
  - 예: "Endoscopic TLIF + Fusion Rate" → 8개 결과 (UBE, BELIF, PELD, MED 등)

- **문서 업데이트**:
  - `TERMINOLOGY_ONTOLOGY.md`: Chunk 노드 속성명 수정 (text → content)
  - Chunk 속성 정확화: content, evidence_level, is_key_finding 추가

- **신규 스크립트**:
  - `scripts/fix_database_issues.py`: 종합 데이터베이스 정비 스크립트
    - --dry-run: 예상 결과만 출력
    - --skip-embeddings: Paper Abstract 임베딩 생성 스킵

- **수정된 파일**:
  - `src/graph/neo4j_client.py`: `create_paper()` abstract_embedding 자동 생성
  - `src/builder/pubmed_bulk_processor.py`: `_generate_abstract_embedding()` 추가

---

### v7.14.11 (2025-12-31): MCP Search Entity Normalization

- **Entity Normalization 적용 (search improvement)**:
  - 검색 쿼리 자동 정규화: "endoscopic TLIF" → "BELIF", "UBE-TLIF" → "BELIF"
  - Outcome 정규화: "fusion rate" → "Fusion Rate"
  - IS_A hierarchy를 통한 하위 intervention 포함 검색

- **evidence_synthesizer.py 개선**:
  - `_gather_evidence()`: 정규화 및 IS_A hierarchy 지원
  - Fallback 검색: fuzzy outcome 매칭 추가
  - value가 없어도 direction/is_significant로 근거 수집 가능

- **graph_search.py 개선**:
  - `_normalize_intervention()`, `_normalize_outcome()` 헬퍼 메서드 추가
  - `search_interventions_for_outcome()`: 정규화 및 fuzzy 매칭 지원
  - 대소문자 무시 검색 가능

- **entity_normalizer.py 별칭 확장**:
  - Intervention: `back surgery`, `disk surgery`, `stenosis surgery`, `척추 수술`, `디스크 수술`, `협착증 수술`
  - Outcome: `pain level`, `neck pain`, `arm pain`, `disability score`, `functional outcome`, `QOL`, `SF-12`, `pseudarthrosis`

- **수정된 파일**:
  - `src/solver/evidence_synthesizer.py`: Entity normalization, IS_A hierarchy, fuzzy matching
  - `src/solver/graph_search.py`: Intervention/Outcome 정규화 헬퍼 메서드
  - `src/graph/entity_normalizer.py`: 누락 용어 별칭 추가

---

### v7.14.10 (2025-12-28): SpineMetadata Field Mapping Fix

- **SpineMetadata 필드 매핑 수정 (critical bug fix)**:
  - `unified_pdf_processor.SpineMetadata`와 `relationship_builder.SpineMetadata` 간 필드명 불일치 해결
  - `pathology` (list) → `pathologies` 매핑
  - `anatomy_level` (str) + `anatomy_region` (str) → `anatomy_levels` (list) 매핑
  - `ExtractedOutcome` 객체 → dict 변환 자동화

- **v7.2 Extended Entities 지원 완성**:
  - `patient_cohorts`, `followups`, `costs`, `quality_metrics` 필드 그래프 저장
  - Cost-effectiveness 논문의 ICER, QALY 데이터 Neo4j 저장

- **헬퍼 함수 추가**:
  - `MedicalKAGServer._convert_to_graph_spine_metadata()`: 통합 변환 함수
  - 중복 코드 제거 및 일관된 매핑 보장

- **Graph Explorer 하이라이트 개선**:
  - 검색어 session_state 저장으로 버튼 클릭 후에도 유지
  - Clear 버튼 추가
  - `st.rerun()` 사용하여 즉시 반영

- **수정된 파일**:
  - `src/medical_mcp/medical_kag_server.py`: `_convert_to_graph_spine_metadata()` 추가
  - `src/medical_mcp/handlers/json_handler.py`: dict → SpineMetadata 변환 추가
  - `web/pages/8_🌐_Graph_Explorer.py`: 검색 UI 개선
  - `scripts/reimport_all_papers.py`: 기존 논문 재처리 스크립트 (신규)

### v7.14.9 (2025-12-28): Citation Storage Fix

- **CitationContext enum 중복 정의 수정**:
  - `types/relationships.py`에서 중복 정의 제거
  - `types/enums.py`에서 import하도록 통합
  - CITES 관계 생성 시 enum 직렬화 오류 해결

- **ImportantCitationProcessor import 수정**:
  - `GraphSpineMetadata` → `SpineMetadata` import 수정
  - 하위 호환성 alias 추가

- **Citation 마이그레이션 스크립트 추가**:
  - `scripts/migrate_citations_to_neo4j.py` 신규
  - 기존 JSON의 important_citations를 Neo4j CITES 관계로 마이그레이션
  - PubMed 검색 및 Paper 노드 자동 생성
  - 마이그레이션 결과: 5개 Paper 노드, 5개 CITES 관계 생성

- **PDF 처리 시 인용 저장 확인**:
  - `pdf_handler.py`의 `add_pdf_v7`: citation_processor 자동 호출 확인
  - `process_from_chunks()` → Discussion/Results 섹션 추출 → CITES 관계 생성

- **수정된 파일**:
  - `src/graph/types/relationships.py`: CitationContext 중복 제거
  - `src/builder/important_citation_processor.py`: SpineMetadata import 수정
  - `scripts/migrate_citations_to_neo4j.py`: 신규 마이그레이션 스크립트

### v7.14.8 (2025-12-27): Graph Explorer 쿼리 개선

- **Graph Explorer 그래프 시각화 개선**:
  - `paper_network` 쿼리 수정: CITES 대신 INVESTIGATES/STUDIES 관계 사용
  - Paper → Intervention, Paper → Pathology 네트워크 표시
  - `full_schema` 쿼리 확장: AFFECTS, IS_A, CAUSES 관계 포함

- **새로운 관계 시각화**:
  - Intervention → Outcome (AFFECTS): 방향성 및 유의성 표시
  - Intervention → Intervention (IS_A): 수술법 계층 구조
  - Pathology → Complication (CAUSES): 병리-합병증 관계

- **색상 스키마 추가**:
  - Complication 노드: #dc2626 (Dark Red)
  - Chunk 노드: #a1a1aa (Zinc)

- **SearchResult 데이터클래스 보완**:
  - `result_type` 필드 추가 (graph/vector/hybrid)
  - `metadata` 딕셔너리 필드 추가

- **수정된 파일**:
  - `web/components/vis_network.py`: 쿼리 및 색상 스키마 수정
  - `web/utils/chain_bridge.py`: SearchResult 필드 추가

### v7.14.7 (2025-12-27): Search Fix - LangChain 의존성 제거

- **chain_bridge.py 재작성**:
  - LangChain 기반 SpineGraphChain 의존성 제거
  - MedicalKAGServer + Neo4j 직접 연동으로 변경
  - OpenAI text-embedding-3-large (3072d) 임베딩 지원
  - 하이브리드 검색: 벡터 + 그래프 결합 (기본 60/40 가중치)

- **검색 기능 구현**:
  - `_neo4j_vector_search()`: Neo4j HNSW 벡터 인덱스 검색
  - `_neo4j_graph_search()`: Cypher 기반 키워드/제목 검색
  - `hybrid_search()`: 벡터 + 그래프 하이브리드 검색
  - `ask_question()`: LLM 기반 QA (Claude Haiku 4.5)

- **SearchResult 데이터클래스 추가**:
  - content, score, tier, source_type, evidence_level
  - paper_id, title, graph_score, vector_score

- **수정된 파일**:
  - `web/utils/chain_bridge.py`: 완전 재작성

### v7.14.6 (2025-12-27): Taxonomy 정비 - Intervention/Pathology/Outcome 계층화

- **Schema.py 신규 메서드 추가**:
  - `get_fix_orphan_interventions_cypher()`: 고아 Intervention 노드에 IS_A 관계 추가
  - `get_fix_orphan_pathologies_cypher()`: Pathology 노드에 카테고리 할당
  - `get_fix_orphan_outcomes_cypher()`: Outcome 노드에 타입 및 방향 할당

- **Intervention 계층 구조 정비** (79개 IS_A 관계):
  - Decompression 계층: Discectomy, Laminoplasty, Endoscopic Decompression 등
  - Fusion 계층: Lumbar Fusion, Spinopelvic Fusion, CCF 등
  - Fixation 계층: Percutaneous Pedicle Screw, Halo Traction 등
  - 신규 상위 노드: Tumor Surgery, Conservative Treatment, Injection Therapy, Radiation Therapy

- **Pathology 카테고리 정비** (76개 분류):
  - degenerative: 17개 (Myelopathy, Radiculopathy 등)
  - deformity: 14개 (PJK, DJK, Adjacent Segment 등)
  - tumor: 14개 (Metastasis 관련)
  - instability: 10개 (Atlantoaxial, Basilar Invagination 등)
  - trauma: 8개 (Fracture 관련)
  - metabolic: 8개 (Osteoporosis, Rheumatoid 등)
  - infection: 5개

- **Outcome 타입 정비** (251개 분류):
  - clinical: 25개 (VAS, NRS 등)
  - functional: 51개 (ODI, NDI, JOA, EQ-5D, SF-36 등)
  - radiological: 29개 (Fusion Rate, Subsidence, Cobb Angle 등)
  - complication: 52개 (Dural Tear, Infection, Reoperation 등)
  - operative: 28개 (Blood Loss, Operation Time, Hospital Stay 등)
  - model_performance: 66개 (AUC, Accuracy, Sensitivity 등)

- **수정된 파일**:
  - `src/graph/types/schema.py`: 3개 신규 메서드 추가

### v7.14.5 (2025-12-27): 중복 Paper/Chunk 방지

- **Paper 중복 방지 로직 추가 (medical_kag_server.py)**:
  - `_check_existing_paper_by_pmid()`: PMID로 기존 Paper 확인
  - `_check_existing_paper_by_doi()`: DOI로 기존 Paper 확인
  - `_check_existing_paper_by_title()`: 제목(대소문자 무시)으로 기존 Paper 확인
  - `_analyze_text_v7()`: 기존 Paper 있으면 해당 ID 사용 (중복 생성 방지)
  - `add_pdf_v7()`: PMID/DOI/제목 순으로 기존 Paper 확인
  - 제목 기반 해시 ID 생성 (text_<md5_hash>) - 동일 제목은 동일 ID

- **Chunk 중복 방지 로직 추가**:
  - `_delete_existing_chunks()`: Paper 재처리 시 기존 Chunk 삭제
  - 4개 위치에 적용: `_process_with_vision()`, `_analyze_text_v7()`, `_process_with_legacy_pipeline()`, `pdf_handler.py`
  - 기존 HAS_CHUNK 관계와 Chunk 노드 삭제 후 새로 생성

- **문제 해결**:
  - 동일 논문 재저장 시 중복 Paper 생성 방지
  - PMID 없는 텍스트 분석 시 매번 새 UUID 생성 문제 해결
  - Chunk 재생성 시 중복 HAS_CHUNK 관계 방지

- **수정된 파일**:
  - `src/medical_mcp/medical_kag_server.py`
  - `src/medical_mcp/handlers/pdf_handler.py`

### v7.14.4 (2025-12-27): Enhanced Graph Visualization with vis-network.js

- **vis-network.js 기반 그래프 시각화 추가**:
  - `web/components/vis_network.py`: vis-network.js HTML 컴포넌트
  - Physics 기반 인터랙티브 레이아웃 (Barnes-Hut 알고리즘)
  - 노드 클릭 시 상세 정보 패널 표시
  - 검색 결과 노드 하이라이팅 (노란색 강조, 빨간색 테두리)
  - Fit View / Toggle Physics / Reset 컨트롤 버튼
  - 노드 타입별 색상 구분 (Intervention, Outcome, Paper, Pathology 등)
  - 엣지 스타일: improved(초록), worsened(빨강), significant(실선), not-sig(점선)
- **Graph Explorer 페이지 신규 추가**:
  - `web/pages/8_🌐_Graph_Explorer.py`: 전용 그래프 탐색 페이지
  - 3가지 뷰 모드: Intervention-Outcome, Paper Network, Full Schema
  - 실시간 노드 검색 및 하이라이팅
  - 다중 필터: Intervention, Outcome, Category, Pathology
  - Physics 레이아웃 vs Hierarchical 레이아웃 선택
  - Significant only 필터 옵션
- **Search 페이지 그래프 뷰 통합**:
  - `web/pages/6_🔍_Search.py`: 검색 결과 그래프 시각화 탭 추가
  - QA 모드, Evidence 모드 모두에서 Graph View 탭 제공
  - 검색 쿼리 중심 방사형 그래프 생성
  - Intervention → Outcome 관계 시각화
- **참조 프로젝트**:
  - https://github.com/gongwon-nayeon/graphrag-demo 기반 설계
  - vis-network.js v9.1.6 CDN 사용
- **수정된 파일**:
  - `web/components/vis_network.py` (신규)
  - `web/components/__init__.py`
  - `web/pages/8_🌐_Graph_Explorer.py` (신규)
  - `web/pages/6_🔍_Search.py`

### v7.14.3 (2025-12-27): Outcome/Complication 매핑 확장

- **entity_normalizer.py 업데이트**:
  - CCF 별칭에 ACCF 추가 (Anterior Cervical Corpectomy and Fusion)
  - Epidural Hematoma 신규 추가: "Postoperative epidural hematoma", "EDH", "Hematoma"
  - C5 Palsy 신규 추가: "C5 nerve palsy", "C5 root palsy", "C5 radiculopathy"
  - Wound Dehiscence 신규 추가: "wound dehiscence", "Surgical wound dehiscence"
- **spine_snomed_mappings.py 업데이트**:
  - C5 Palsy (900000000000506): Postoperative C5 nerve palsy (Extension)
  - Wound Dehiscence (225553008): Official SNOMED code
- **Neo4j 업데이트 검증**:
  - Intervention 노드: 230개
  - IS_A 관계: 43개
  - BELIF, Facetectomy, Stereotactic Navigation 모두 IS_A 관계 검증 완료
- **추출 데이터 분석 결과**:
  - 209개 JSON 파일 분석
  - 394개 고유 Intervention, 1667개 고유 Outcome, 333개 고유 Pathology 발견
  - 주요 누락 용어 식별 및 별칭 추가 완료

### v7.14.2 (2025-12-26): Schema, Taxonomy, MCP Reconnection

- **Schema/Taxonomy 자동 업데이트 스크립트 추가**:
  - `scripts/update_schema_taxonomy.py`: 통합 업데이트 스크립트
  - `--dry-run`: 검증만 수행, `--force`: 확인 없이 실행, `--quiet`: cron용 최소 출력
  - cron/launchd 자동화 지원
  - `docs/SCHEMA_UPDATE_GUIDE.md`: 상세 사용 가이드
- **MCP SSE 서버 재연결 기능 추가** (`sse_server.py`):
  - `/reset` 엔드포인트: 서버 캐시 초기화, MCP 클라이언트 재연결 지원
  - `/restart` 엔드포인트: Neo4j 연결 재설정
  - `/ping` 엔드포인트: 서버 생존 확인 (경량)
  - 연결 실패 시 자동 복구 로직 강화
  - 사용법: `curl -X POST http://localhost:8000/reset`
- **TERMINOLOGY_ONTOLOGY.md 문서 작성**:
  - Schema, Taxonomy, SNOMED 코드 전체 분석 문서
  - 128개 엔티티 매핑 상세 (66.4% 공식, 33.6% 확장)
  - Entity Normalizer, Synonym Groups 설명
  - 확장 가이드 포함
- **Taxonomy MERGE 추가** (`schema.py`):
  - Facetectomy: Decompression Surgery → Open Decompression 하위에 추가
  - BELIF: Fusion Surgery → Interbody Fusion → TLIF 하위에 추가 (MIS technique)
  - Stereotactic Navigation: Fixation 하위에 추가
- **SNOMED Enrichment 쿼리 추가** (`schema.py`):
  - Facetectomy (900000000000121): Facet joint resection
  - BELIF (900000000000119): Biportal endoscopic lumbar interbody fusion
  - Stereotactic Navigation (900000000000120): Navigation-guided surgery
- **spine_snomed_mappings.py 업데이트**:
  - Facetectomy SNOMED 매핑 추가 (parent: 5765005 Decompression)
  - 별칭: Partial facetectomy, Medial facetectomy, Total facetectomy, Facet resection
- **GRAPH_SCHEMA.md 업데이트**:
  - Intervention Taxonomy 다이어그램 확장 (BELIF, Facetectomy, Navigation 반영)
  - 매핑 통계 갱신: 139개 총 매핑 (88 official, 51 extension)
  - Extension Codes 목록 갱신 (v7.14-v7.14.2 추가분 포함)
- **수정된 파일**:
  - `src/graph/types/schema.py`
  - `src/ontology/spine_snomed_mappings.py`
  - `docs/GRAPH_SCHEMA.md`

### v7.14.1 (2025-12-25): Extended Terminology Normalization

- **Intervention 별칭 대폭 확장** (`entity_normalizer.py`):
  - Endoscopic Decompression 신규 카테고리 추가
  - MED: "microendoscopic discectomy", "Micro-endoscopic discectomy"
  - Microdecompression: "microscopic decompression", "Microscopic lumbar decompression"
  - TLIF/PLIF/ALIF/OLIF/LLIF/ACDF: 소문자 변형 전체 추가
  - MIS-TLIF: "MI-TLIF", "Mini-TLIF"
- **Intervention 별칭 대폭 확장** (계속):
  - Generic Fusion: "Posterior fusion", "PSF", "Lumbar fusion", "interbody fusion" 등
  - UBE 변형: "UBED", "BE", "Biportal Endoscopic Surgery" 추가
  - BELIF 변형: "Endo-TLIF", "UBE-TLIF", "Endoscopic TLIF" 추가
  - Osteotomy: Generic "Osteotomy", PSO/VCR 소문자 변형 추가
  - Discectomy: "MD", "Endoscopic discectomy" 등 추가
  - Facetectomy 신규 추가
  - Percutaneous Pedicle Screw 변형 추가
- **Outcome 별칭 대폭 확장**:
  - VAS: 전체형식 "Visual Analog Scale (VAS)", 소문자 변형
  - VAS Back/Leg: "VAS Back Pain", "VAS-Back", "VAS (back)" 등
  - ODI: "Oswestry Disability Index (ODI)", "ODI (Oswestry Disability Index)" 등
  - NDI, JOA, mJOA: 전체형식 및 소문자 변형
  - Operation Time: "operative time", "Operative Time", "Operating time" 등
  - Blood Loss: "Intraoperative Blood Loss", "Total Blood Loss" 등
  - Hospital Stay: "Length of Stay", "Hospital LOS" 등
  - Complication Rate: "Postoperative complications" 등
- **Pathology 별칭 대폭 확장**:
  - Lumbar Stenosis: "lumbar spinal stenosis", "lumbar stenosis" 소문자
  - Cervical Stenosis: "cervical spondylosis", "CSM" 추가
  - Lumbar Disc Herniation: "intervertebral disc herniation", "Recurrent lumbar disc herniation"
  - DDD: "lumbar degenerative disc disease", "Intervertebral disc degeneration" 등
  - Spondylolisthesis: "degenerative spondylolisthesis", 소문자 변형
  - ASD: "Adult spinal deformity (ASD)", 전체형식 추가
  - Sagittal Imbalance: "sagittal imbalance", 소문자 변형
  - Spinal Metastasis: "Metastatic spinal disease", "metastatic spinal tumors"
- **신규 Pathology 추가**:
  - PJK: Proximal Junctional Kyphosis 및 변형
  - DJK: Distal Junctional Kyphosis
  - Adjacent Segment Disease: adjacent segment degeneration 포함
  - Cervical Myelopathy: DCM, degenerative cervical myelopathy
  - Cervical Radiculopathy, Lumbar Radiculopathy
  - Segmental Instability: Lumbar instability 포함
- **SNOMED 매핑 신규 추가** (`spine_snomed_mappings.py`):
  - Cervical Radiculopathy (267073000)
  - Lumbar Radiculopathy (128196005)
  - Segmental Instability (900000000000206)
  - DJK - Distal Junctional Kyphosis (900000000000207)
  - Adjacent Segment Disease (900000000000208)
- **SYNONYM_GROUPS 확장**:
  - Posterior fusion/PSF/PLF 그룹
  - TLIF/Transforaminal fusion 그룹
  - Sciatica/Radiculopathy 그룹
- **INTERVENTION_CATEGORIES 신규 추가**:
  - Endoscopic Decompression → Endoscopic Surgery
  - Facetectomy → Decompression Surgery
  - Osteotomy → Osteotomy
- **예상 개선도**:
  - Interventions: 11.9% → 70-75%
  - Outcomes: 1.3% → 75-85%
  - Pathologies: 6.3% → 75-80%

### v7.14 (2025-12-25): Terminology Normalization Enhancement

- **용어 정규화 강화**: 151개 논문 분석 결과 반영
  - 278개 추출 용어 → ~50-60개 고유 수술법으로 정규화
  - 동일 수술법의 다양한 표현을 통합 (별칭 확장)
- **UBE 계열 별칭 확장** (`entity_normalizer.py`):
  - BED (Biportal Endoscopic Discectomy) → UBE로 정규화
  - "Biportal Endoscopic Discectomy", "Biportal Discectomy" 추가
- **BELIF 계열 통합** (`entity_normalizer.py`, `spine_snomed_mappings.py`):
  - BE-TLIF = BELIF = BE-LIF = BELF (동일 수술법 확인)
  - 신규 SNOMED 코드: 900000000000119
- **Decompression/Laminectomy 통합**:
  - Decompression, decompression, Neural Decompression → 동일 그룹
  - Laminectomy, decompressive laminectomy → 동일 그룹
  - 케이스 변형 (대소문자) 및 부위별 변형 추가
- **신규 수술법 SNOMED 코드**:
  - Stereotactic Navigation (900000000000120): O-arm, CT navigation 포함
- **신규 Outcome SNOMED 코드**:
  - Serum CPK (900000000000311): 근육 손상 지표
  - Scar Quality (900000000000312): 상처 미용 결과
  - Postoperative Drainage (900000000000313): 배액량
- **신규 Complication SNOMED 코드**:
  - Wound Dehiscence (900000000000503): 상처 벌어짐
  - Recurrent Disc Herniation (900000000000504): 재발성 디스크 탈출
  - Epidural Hematoma (900000000000505): 경막외 혈종
- **SYNONYM_GROUPS 확장** (`spine_snomed_mappings.py`):
  - UBE 그룹에 BED 추가
  - BELIF/BE-TLIF 그룹 신규 추가
  - Decompression/Laminectomy 그룹 신규 추가
- **수정된 파일**:
  - `src/graph/entity_normalizer.py`: INTERVENTION_ALIASES 확장
  - `src/ontology/spine_snomed_mappings.py`: SYNONYM_GROUPS, SPINE_INTERVENTION_SNOMED, SPINE_OUTCOME_SNOMED 확장
  - `docs/TERMINOLOGY_UPDATE_PLAN.md`: 업데이트 계획 문서

### v7.13.1 (2025-12-25): DOI MCP Tool Integration & SSE Stability

- **MCP pubmed 도구에 DOI 기능 추가** (v7.12.2 기능 통합)
  - `fetch_by_doi`: DOI로 논문 조회 (Crossref + Unpaywall)
  - `doi_metadata`: DOI 메타데이터만 조회 (빠른 조회)
  - `import_by_doi`: DOI로 논문을 Neo4j 그래프에 임포트
- **새 메서드 추가** (`medical_kag_server.py`)
  - `fetch_by_doi()`: 전문/메타데이터 조회, 선택적 그래프 임포트
  - `get_doi_metadata()`: 메타데이터 전용 (전문 없이)
  - `import_by_doi()`: v7.5 파이프라인으로 분석 후 그래프 저장
  - `_import_doi_to_graph()`: 내부 임포트 헬퍼
- **SSE 서버 연결 안정성 개선** (`sse_server.py`)
  - `ConnectionManager` 클래스 추가: 연결 상태 추적 및 관리
  - Heartbeat 기능 추가 (기본 30초 간격)
  - 유휴 연결 자동 정리 (기본 5분 타임아웃)
  - `/connections` 엔드포인트 추가: 연결 상태 모니터링
  - MCP 서버 캐싱으로 재연결 시 빠른 응답
  - 커맨드라인 옵션: `--heartbeat`, `--timeout`
  - uvicorn `timeout_keep_alive` 설정 추가
- **PMC Fulltext Fetcher 개선** (`pmc_fulltext_fetcher.py`)
  - JSON 파싱 에러 처리 개선 (ERROR → DEBUG 레벨)
  - Content-Type 헤더 검증 추가
- **pubmed 도구 스키마 업데이트**:
  - `doi` 파라미터 추가
  - `import_to_graph`, `fetch_fulltext` 옵션 추가

### v7.13 (2025-12-25): DOI Fulltext Fetcher & PubMed Fallback Integration

- **DOI Fulltext Fetcher 추가** (`src/builder/doi_fulltext_fetcher.py`)
  - Crossref API: DOI → 메타데이터 (제목, 저자, 저널, 초록 등)
  - Unpaywall API: Open Access 상태 및 PDF URL 조회
  - OA 상태 분류: gold, green, hybrid, bronze, closed
  - 일괄 조회 지원 (`fetch_batch`)
  - PMC 전문 자동 연동 (PMID 있는 경우)
- **PubMed 임포트 Fulltext Fallback 통합** (`pubmed_bulk_processor.py`)
  - 1순위: PMC Open Access (BioC API)
  - 2순위: DOI/Unpaywall (자동 fallback)
  - 3순위: Abstract만 저장 (최종 fallback)
  - DOI는 메타데이터에 자동 저장됨
  - 별도 MCP 도구 없이 PubMed import 시 자동 적용
- **MCP 사용 가이드 추가**: `docs/MCP_USAGE_GUIDE.md`
  - Claude Desktop/Code에서 10개 MCP 도구 사용법
  - PubMed fulltext 조회 순서 설명
  - 도구별 상세 설명 및 예시
  - 실전 사용 시나리오 4가지
  - 팁, 모범 사례, 문제 해결 가이드
- **.mcp.json 수정**: `python` → `python3` (macOS 호환)
- **누락 패키지 설치 가이드 반영**:
  - `aiosqlite`, `python-dotenv`, `aiohttp`, `rapidfuzz`
  - `anthropic`, `requests`, `google-genai`, `pymupdf`

### v7.12.1 (2025-12-24): SSE Server & Dependency Fixes

- **SSE 서버 라우팅 수정**: `/messages` 엔드포인트 ASGI 오류 해결
  - `Route` → `Mount` 변경으로 SSE transport 직접 처리
  - `sse_server.py`: handle_messages 함수 제거, Mount 사용
- **PubMed Bulk Processor 수정**: `owner` 변수 미정의 오류 해결
  - `_process_fulltext_with_llm()`: `owner`, `shared` 파라미터 추가
  - 호출부에서 파라미터 전달 누락 수정
- **의존성 패키지 설치**:
  - `nest-asyncio`: Neo4j 벡터 검색 async 이벤트 루프 지원
  - `openai`: OpenAI Embeddings (text-embedding-3-large) 지원
- **requirements.txt 정리**:
  - 버전 7.12로 업데이트, 불필요한 패키지 제거
  - ChromaDB 제거 (Neo4j 벡터로 대체)
  - LangChain 관련 패키지 제거 (사용 안함)
  - `starlette`, `uvicorn` 추가 (SSE 서버용)
- **실행 가이드 문서 추가**: `실행법.md`
  - Neo4j 시작, SSE 서버 실행 명령어
  - 원격 클라이언트 설정 (Claude Desktop, Cursor)
  - 트러블슈팅 가이드
- **수정된 파일**:
  - `src/medical_mcp/sse_server.py`: Mount 라우팅
  - `src/builder/pubmed_bulk_processor.py`: owner/shared 파라미터
  - `requirements.txt`: 의존성 정리
  - `실행법.md`: 신규 문서

### v7.12 (2025-12-23): Academic Writing Guide System

- **WritingGuideHandler 추가**: 학술 논문 작성을 위한 통합 가이드 시스템
- **섹션별 작성 가이드**: 6개 섹션 (Introduction, Methods, Results, Discussion, Conclusion, Figure Legend)
  - Introduction: ~400 words, 3-4 paragraphs, 배경→문제→목적 구조
  - Methods: 체크리스트 기반, 재현 가능성 강조
  - Results: 서브타이틀 사용, 중복 회피, 표/그림 참조
  - Discussion: Key points → 문헌 비교 → 제한점 → 시사점
  - Conclusion: 객관적 요약, 과도한 일반화 주의
  - Figure Legend: 제목, 범례, 통계 정보 포함
- **연구 유형별 체크리스트**: 9개 EQUATOR Network 체크리스트 지원
  - STROBE (22항목): 관찰 연구 (Cohort, Case-Control, Cross-Sectional)
  - CONSORT (25항목): 무작위 대조군 연구 (RCT)
  - PRISMA (27항목): 체계적 문헌고찰 및 메타분석
  - CARE (13항목): 증례 보고
  - STARD (25항목): 진단 정확도 연구
  - SPIRIT (33항목): 임상시험 프로토콜
  - MOOSE (32항목): 관찰 연구 메타분석
  - TRIPOD (22항목): 예측 모델 개발/검증
  - CHEERS (28항목): 경제성 평가 연구
- **전문가 에이전트 시스템**: 4개 역할
  - Clinician: 임상적 해석, Introduction/Discussion 담당
  - Methodologist: 연구 방법론, Methods/Results 담당
  - Statistician: 통계 분석, Results/Tables 담당
  - Editor: 논문 구조, 전체 검토 담당
- **리비전 지원 기능**:
  - 응답 템플릿: Major Revision, Minor Revision, Rejection Rebuttal
  - 리뷰어 코멘트 분석: 카테고리별 분류 (Major/Minor/Technical)
  - 응답서 초안 작성: Point-by-point 형식
- **MCP Tool #10 "writing_guide"**: 7개 action 지원
  - `section_guide`: 섹션별 작성 가이드
  - `checklist`: 연구 유형별 체크리스트
  - `expert`: 전문가 정보 조회
  - `response_template`: 응답서 템플릿
  - `draft_response`: 응답서 초안 작성
  - `analyze_comments`: 리뷰어 코멘트 분석
  - `all_guides`: 전체 가이드 조회
- **새 파일**: `src/medical_mcp/handlers/writing_guide_handler.py` (~700줄)
- **수정된 파일**:
  - `src/medical_mcp/handlers/__init__.py`: WritingGuideHandler 추가
  - `src/medical_mcp/medical_kag_server.py`: Tool 등록 및 핸들러 통합

### v7.11 (2025-12-22): SSI Classification & Comorbidity Terms

- **Surgical Site Infection (SSI) 세분화**: 표재성/심부 구분 추가
  - `Superficial Surgical Site Infection` (SNOMED: 433202001): 피부, 피하조직 감염
  - `Deep Surgical Site Infection` (SNOMED: 433201008): 근육, 임플란트 관련 감염
  - `Infection Rate` 동의어 확장: "SSI rate", "Postoperative infection" 추가
- **Comorbidities / Risk Factors 섹션 신설** (SPINE_PATHOLOGY_SNOMED):
  - `Diabetes Mellitus` (SNOMED: 73211009): 수술 부위 감염의 주요 위험인자
- **SNOMED 매핑 통계 갱신**: Pathology 28개 (+1), Outcome 27개 (+2)
- **수정된 파일**: `src/ontology/spine_snomed_mappings.py`

### v7.10 (2025-12-22): SNOMED-CT Full Entity Integration

- **SNOMED-CT 코드 전체 엔티티 지원**: Intervention, Pathology, Outcome 모든 노드에 SNOMED 코드 저장
- **Pathology (질환) SNOMED 지원 추가**:
  - `CypherTemplates.CREATE_STUDIES_RELATION`: SNOMED fallback 로직 추가
  - `neo4j_client.create_studies_relation()`: `snomed_code`, `snomed_term` 파라미터 추가
  - `relationship_builder.create_studies_relations()`: 정규화 결과에서 SNOMED 전달
- **Outcome (결과변수) SNOMED 지원 추가**:
  - `CypherTemplates.CREATE_AFFECTS_RELATION`: SNOMED fallback 로직 추가
  - `neo4j_client.create_affects_relation()`: `snomed_code`, `snomed_term` 파라미터 추가
  - `relationship_builder.create_affects_relations()`: 정규화 결과에서 SNOMED 전달
- **ExtractedEntity SNOMED 필드 추가** (v7.8 보완):
  - `snomed_code`: SNOMED-CT 코드
  - `snomed_term`: SNOMED-CT 선호 용어
  - `_normalize_entities()`: 정규화 시 SNOMED 코드 저장
- **Cypher 템플릿 패턴**:
  - `COALESCE($snomed_code, existing_snomed_code)`: 파라미터 우선, 기존값 fallback
  - `ON CREATE SET` / `ON MATCH SET`: 새 노드와 기존 노드 모두 처리
- **수정된 파일**:
  - `src/graph/types/schema.py`: CREATE_STUDIES_RELATION, CREATE_AFFECTS_RELATION
  - `src/graph/neo4j_client.py`: create_studies_relation, create_affects_relation
  - `src/graph/relationship_builder.py`: create_studies_relations, create_affects_relations
  - `src/builder/entity_extractor.py`: ExtractedEntity, _normalize_entities

### v7.9 (2025-12-22): Reference Citation Formatter

- **Reference Formatter 기능 추가**: 다양한 저널 인용 스타일 지원
- **7개 기본 스타일**: Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard
- **28개 기본 저널 매핑**:
  - Spine Journals: The Spine Journal, Spine, European Spine Journal, Global Spine Journal, Asian Spine Journal
  - Orthopedic: Clinics in Orthopedic Surgery, JBJS, J Bone Joint Surg Am/Br
  - General Medical: JAMA 계열, NEJM, The Lancet, BMJ
  - Neurosurgery: J Neurosurg, J Neurosurg Spine, Neurosurgery
- **저널별 스타일 매핑**: 저널명-스타일 매핑 저장 및 자동 적용 (대소문자 무관)
- **커스텀 스타일 생성**: 기존 스타일 기반 커스터마이징
- **Export 형식**: BibTeX, RIS (EndNote/Zotero 호환)
- **새 모듈**:
  - `src/builder/reference_formatter.py`: 핵심 포맷터 (780줄)
    - `PaperReference` dataclass: 논문 메타데이터 모델
    - `StyleConfig`: 스타일 설정 dataclass
    - `ReferenceFormatter`: 포맷팅 엔진
  - `src/medical_mcp/handlers/reference_handler.py`: MCP 핸들러 (555줄)
    - `format_reference`: 단일 논문 포맷
    - `format_references`: 다중 논문 포맷 (번호 매기기)
    - `list_styles`: 사용 가능 스타일 목록
    - `set_journal_style`: 저널-스타일 매핑 저장
    - `add_custom_style`: 커스텀 스타일 추가
    - `preview_styles`: 여러 스타일로 미리보기
- **MCP Tool #9 "reference"**: 6개 action 지원
  - `format`: 단일 논문 참고문헌 포맷
  - `format_multiple`: 여러 논문 참고문헌 목록
  - `list_styles`: 스타일 목록 조회
  - `set_journal_style`: 저널별 스타일 저장
  - `add_custom_style`: 커스텀 스타일 생성
  - `preview`: 다양한 스타일로 미리보기
- **Edge Case 처리**:
  - 빈 저자/저널/페이지 처리
  - String→Int 연도 변환
  - e-pages, supplement pages 지원
  - 복합 성(Van Der Park) 처리
  - APA 스타일 이니셜 형식 (S.-M.)
- **Bugfix**: BibTeX citation key 생성 수정
  - 이전: `"Park SM"` → `@article{SM2024}` (이니셜 사용 - 잘못됨)
  - 수정: `"Park SM"` → `@article{Park2024}` (성 사용 - 올바름)
- **경로 설정 개선**: 다중 경로 폴백으로 안정성 향상
- **데이터 파일**: `data/styles/journal_styles.json` (저널 매핑 및 커스텀 스타일 저장)

### v7.8 (2025-12-22): Important Citations Full Analysis Pipeline

- **analyze_text Important Citations 복원**: `_analyze_text_v7`에 Citation Processing 단계 추가
- **인용된 논문 LLM 분석**: PubMed abstract를 EntityExtractor로 분석하여 spine_metadata 추출
- **인용 논문 전체 관계 구축**: `relationship_builder.build_from_paper()` 호출로 STUDIES, INVESTIGATES, REPORTS 관계 자동 생성
- **JSON 저장 시 important_citations 포함**: 상세 데이터 (PubMed abstract, PMID, DOI, MeSH terms 등)
- **CitationProcessingResult 확장**: `citations_data` 필드 추가 (JSON 저장용 상세 데이터)
- **ImportantCitationProcessor 업데이트**:
  - `relationship_builder` 파라미터 추가
  - `analyze_cited_abstracts` 옵션 (기본값: True)
  - `_create_cited_paper_node()`에서 abstract LLM 분석 + 관계 구축
  - 이미 존재하는 논문 중복 분석 방지
- **처리 흐름**:

  ```text
  analyze_text → 청크 생성 → Citation Processing
    → Discussion/Results에서 중요 인용 추출 (LLM)
    → PubMed 검색 (저자+연도+키워드)
    → abstract LLM 분석 (EntityExtractor)
    → relationship_builder로 전체 관계 구축
    → CITES 관계 생성
    → JSON 저장 (important_citations 포함)
  ```

### v7.7 (2025-12-21): Code Quality - medical_kag_server.py Handler Integration

- **medical_kag_server.py 핸들러 분할 및 완전 통합**: 9개 도메인별 핸들러 + 공유 유틸리티
- **새 구조**: `src/medical_mcp/handlers/` 패키지 (총 4,716줄)
  - `pdf_handler.py`: PDF/텍스트 분석, 저장 (1,109줄)
  - `graph_handler.py`: 수술법 계층, 논문 관계 (579줄)
  - `search_handler.py`: 하이브리드 검색, 그래프 검색 (519줄)
  - `reasoning_handler.py`: 추론, 상충 탐지, 근거 종합 (506줄)
  - `clinical_data_handler.py`: 환자 코호트, 추적관찰, 비용 분석 (483줄)
  - `document_handler.py`: 문서 CRUD, 내보내기 (468줄)
  - `pubmed_handler.py`: PubMed 검색/임포트 (453줄)
  - `citation_handler.py`: 인용 기반 초안 작성 (237줄)
  - `json_handler.py`: JSON 파일 임포트 (213줄)
  - `utils.py`: 공유 유틸리티 (generate_document_id 등, 110줄)
- **완전 통합**: `MedicalKAGServer._init_handlers()` 메서드로 9개 핸들러 인스턴스화
- **DRY 원칙**: 중복 코드 utils.py로 추출 (~160줄 중복 제거)
- **SRP 준수**: 도메인별 책임 분리

### v7.6 (2025-12-21): Code Quality - spine_schema.py Modularization

- **spine_schema.py 분할**: 4,329줄 → 7개 모듈 (최대 1,296줄)
- **새 구조**: `src/graph/types/` 패키지
  - `enums.py`: 9개 Enum (SpineSubDomain, EvidenceLevel, DocumentType 등)
  - `core_nodes.py`: 6개 핵심 Node (PaperNode, ChunkNode 등)
  - `extended_nodes.py`: 16개 확장 Node (PatientCohortNode, FollowUpNode 등)
  - `relationships.py`: 22개 Relationship 클래스
  - `schema.py`: SpineGraphSchema, CypherTemplates
- **하위 호환성**: 기존 `from graph.spine_schema import ...` 계속 동작
- **SRP 준수**: Single Responsibility Principle 적용

### v7.5 (2025-12-21): Unified Narrative Summary Pipeline
- **v7.0 Simplified Pipeline 기본 사용**: `add_pdf(use_v7=True)` 파라미터
- **통합 요약 형식**: 4개 섹션 (Background, Methodology, Key Findings, Conclusions)
- **Important Citation 자동 처리**: Discussion/Results에서 중요 인용 추출 → PubMed 검색 → CITES 관계 생성
- **Legacy Processor Deprecation**: `unified_pdf_processor.py` → `unified_processor_v7.py`

### v7.5 (2025-12-19): Multi-User Support with SSE Transport
- **다중 사용자 지원**: 라벨 기반 데이터 분리 (owner/shared 필드)
- **SSE 서버**: `python -m medical_mcp.sse_server --port 8000`
- **REST API**: FastAPI 기반 `/tool/{name}` 엔드포인트

### v7.4 (2025-12-19): MCP Tool Consolidation
- **38 Tools → 8 Tools**: Context Token ~63% 절감
- **8개 통합 도구**: document, search, pubmed, analyze, graph, conflict, intervention, extended
- **Action 기반 라우팅**: 각 도구에 `action` 파라미터로 세부 기능 선택

### v7.2 (2025-12-19): Extended Entity Schema
- **4 New Nodes**: PatientCohort, FollowUp, Cost, QualityMetric
- **7 New Relationships**: HAS_COHORT, TREATED_WITH, HAS_FOLLOWUP 등
- **Schema Total**: 21 Node Types, 28 Relationship Types

### v6.0 (2025-12-18): Unified Document Schema
- **22개 문서 유형**: Zotero/EndNote 호환 스키마
- **3-Tier 구조**: Core Fields → Type-Specific → Domain Extensions

### v5.3.5 (2025-12-19): analyze_text Enrichment
- **PubMed Auto Enrichment**: `analyze_text` MCP 도구에 PubMed enrichment
- **Web Search Fallback**: CrossRef API로 비의학 문서 서지 정보 검색

### v5.3 (2025-12-18): Neo4j Unified Storage
- **ChromaDB 완전 제거**: Neo4j Vector Index로 100% 전환
- **Single-Store Architecture**: 그래프+벡터 단일 저장소

### v5.2 (2025-12-17): SQLite Removal
- **아키텍처 단순화**: 3-저장소 → 2-저장소 (Neo4j + ChromaDB)
- **SQLite 제거**: Paper-to-Paper 관계를 Neo4j로 이전

### v5.1 (2025-12-17): PubMed Bulk Processing
- **대량 검색/임포트**: PubMed 검색 → 선택적 임포트
- **인용 기반 임포트**: Important Citations 자동 임포트
- **PMC Full Text**: Open Access 논문 전문 자동 수집

### v5.0 (2025-12-16): PDF Extraction Optimization
- **토큰 사용량 ~22% 절감**
- PICO를 spine_metadata level로 이동
- Statistics 필드 간소화

### v4.3 (2025-12-16): SNOMED CT Enhancement
- **커버리지 67.2%**: 82개 공식 코드, 40개 Extension 코드
- Extension 코드 체계화: 900000000000xxx 네임스페이스

### v4.2 (2025-12-16): Unified PDF Processor
- `unified_pdf_processor.py`에 10개 dataclass 통합
- `gemini_vision_processor.py` deprecated

### v4.1 (2025-12-15): Integrated Citation Extraction
- 통합 인용 추출 (단일 LLM 호출)
- LLM 비용 ~50% 절감

### v4.0 (2025-12-14): Major Refactoring
- **Claude 기본 LLM**: Haiku 4.5 + Sonnet 폴백
- Unified PaperNode 스키마
- Paper-to-Paper 관계
- Balanced Mode 청크 생성
- PageRank 기반 confidence 보정

### v3.2 (2025-12-13): SNOMED-CT + UI/UX
### v3.1 (2025-12-05): Advanced RAG + PubMed 강화
### v3.0 (2025-12-04): Neo4j Graph integration
### v2.0 (2024-12): Tiered search, ChromaDB
### v1.0 (2024-11): Basic vector search
