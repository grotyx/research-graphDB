# CA Deferred Items 실행 계획서

> **목적**: D-005~D-008 아키텍처 리팩토링을 팀에이전트 모드로 병렬 실행하기 위한 계획서
> **실행 방법**: Claude Code에서 `docs/CA_DEFERRED_PLAN.md의 D-XXX를 팀에이전트 모드로 실행해줘` 프롬프트 사용
> **예상 소요**: 항목별 30분~2시간, 전체 병렬 실행 시 ~2시간
> **실행 결과**: ✅ v1.22.0에서 전체 완료 (2026-02-16). 2360 tests passed, 0 failed.

---

## D-005: Neo4jClient God Object 분리

### 개요

| 항목 | 내용 |
|------|------|
| **현재 상태** | `Neo4jClient` 1,641줄, 52 메서드 — CRUD/검색/관계/스키마/임베딩/통계 혼재 |
| **목표** | 책임별 3개 DAO 클래스 추출, Neo4jClient는 연결/쿼리 + 위임 패턴으로 축소 |
| **전략** | Composition + Delegation — 기존 API 유지하면서 내부 분리 (하위 호환성 보장) |
| **영향 범위** | neo4j_client.py (주), 외부 호출자는 변경 불필요 (delegation 유지) |

### 추출 대상

| 새 클래스 | 메서드 수 | 줄 수 | 책임 |
|-----------|----------|-------|------|
| `RelationshipDAO` | 17 | ~584 | Entity 관계 생성 (STUDIES, TREATS 등) + Paper-to-Paper 관계 (SUPPORTS, CONTRADICTS, CITES) |
| `SearchDAO` | 7 | ~205 | Vector/Hybrid 검색 + Intervention 계층 쿼리 |
| `SchemaManager` | 4 | ~168 | 스키마 초기화 + 통계 + DB 클리어 |

### 팀에이전트 구성 (3 에이전트)

**Agent 1: RelationshipDAO 추출**
```
파일: src/graph/neo4j_client.py (읽기 + 수정)
      src/graph/relationship_dao.py (신규 생성)

작업:
1. src/graph/relationship_dao.py 생성
   - class RelationshipDAO(__init__에서 run_query, run_write_query 콜백 수신)
   - neo4j_client.py에서 Group H + I 메서드 17개 이동:
     create_studies_relation, create_investigates_relation, create_affects_relation,
     create_treats_relation, create_involves_relation, create_paper_relation,
     create_supports_relation, create_contradicts_relation, create_cites_relation,
     get_paper_relations, get_related_papers, get_supporting_papers,
     get_contradicting_papers, get_similar_papers, get_citing_papers,
     get_cited_papers, delete_paper_relation, update_paper_relation_confidence

2. neo4j_client.py에서:
   - __init__에 self.relationships = RelationshipDAO(self.run_query, self.run_write_query) 추가
   - 기존 메서드를 1줄 delegation으로 변경:
     async def create_studies_relation(self, ...): return await self.relationships.create_studies_relation(...)
   - delegation 메서드에 # TODO: deprecated, use client.relationships.method() 주석 추가

주의: 외부 호출자(relationship_builder.py, graph_handler.py)는 변경하지 않음
```

**Agent 2: SearchDAO 추출**
```
파일: src/graph/neo4j_client.py (읽기 + 수정)
      src/graph/search_dao.py (신규 생성)

작업:
1. src/graph/search_dao.py 생성
   - class SearchDAO(__init__에서 run_query 콜백 + session 컨텍스트매니저 수신)
   - Group G + J 메서드 7개 이동:
     vector_search_chunks, hybrid_search,
     get_intervention_hierarchy, get_intervention_children,
     search_effective_interventions, search_interventions_for_pathology,
     find_conflicting_results

2. neo4j_client.py에서:
   - __init__에 self.search = SearchDAO(self.run_query, self.session) 추가
   - 기존 메서드를 1줄 delegation으로 변경

주의: 외부 호출자(tiered_search, hybrid_ranker, search_handler 등)는 변경하지 않음
```

**Agent 3: SchemaManager 추출 + 테스트**
```
파일: src/graph/neo4j_client.py (읽기 + 수정)
      src/graph/schema_manager.py (신규 생성)

작업:
1. src/graph/schema_manager.py 생성
   - class SchemaManager(__init__에서 run_query, run_write_query 콜백 수신)
   - Group C + K 메서드 4개 이동:
     initialize_schema, get_stats, clear_database, clear_all_including_taxonomy

2. neo4j_client.py에서:
   - __init__에 self.schema = SchemaManager(self.run_query, self.run_write_query) 추가
   - 기존 메서드를 1줄 delegation으로 변경

3. 전체 테스트 실행하여 regression 없음 확인
```

### 완료 기준
- [x] neo4j_client.py 줄 수 1,641 → ~800 (delegation 메서드 포함)
- [x] 3개 신규 파일 생성 (relationship_dao.py, search_dao.py, schema_manager.py)
- [x] 기존 API 100% 하위 호환 (delegation 패턴)
- [x] 2,360 테스트 전체 통과

---

## D-006: core/text_chunker.py 계층 위반 해소

### 개요

| 항목 | 내용 |
|------|------|
| **현재 상태** | `core/text_chunker.py`의 `TieredTextChunker`가 `builder/section_classifier`, `builder/citation_detector` lazy import |
| **목표** | core → builder 의존 제거 |
| **전략** | 모듈 분리 — `TieredTextChunker`를 `builder/`로 이동 |
| **영향 범위** | 3개 파일 import 변경 |

### 팀에이전트 구성 (1 에이전트)

**단일 Agent 실행** (소규모 작업)
```
작업:
1. src/builder/tiered_text_chunker.py 신규 생성
   - src/core/text_chunker.py에서 TieredTextChunker, TieredChunkOutput 클래스 이동
   - TextChunker, Chunk 등 base 클래스는 core/text_chunker.py에 유지
   - builder 내부이므로 section_classifier, citation_detector import를 top-level로 이동 가능

2. src/core/text_chunker.py에서 TieredTextChunker, TieredChunkOutput 삭제

3. Import 변경 (3파일):
   - src/builder/llm_semantic_chunker.py:16 → from builder.tiered_text_chunker import TieredTextChunker
   - src/medical_mcp/medical_kag_server.py:76 → from builder.tiered_text_chunker import TieredTextChunker
   - src/core/__init__.py:4 → TieredTextChunker export 제거 (또는 builder에서 re-export)

4. 테스트 실행
```

### 완료 기준
- [x] core/text_chunker.py에 builder/ import 0건
- [x] TieredTextChunker가 builder/ 내에서 정상 작동
- [x] 2,360 테스트 전체 통과

---

## D-007: 테스트 커버리지 확장 (37.9% → 60%+)

### 개요

| 항목 | 내용 |
|------|------|
| **현재 상태** | 39/103 모듈 테스트 존재, 밀도 0.32 |
| **목표** | 60%+ 모듈 커버리지 (~62/103), 밀도 0.5+ |
| **전략** | Easy → Medium → Hard 순으로 3 Phase 실행 |
| **예상 신규 테스트**: ~20-25개 파일 |

### Phase 1: Easy Wins (순수 로직, 외부 의존 없음) — 6개 파일

| # | 소스 파일 | 줄 수 | 테스트 파일 | 포인트 |
|---|-----------|-------|------------|--------|
| 1 | `graph/types/schema.py` | 2,067 | `tests/graph/test_schema.py` | 상수/딕셔너리 검증, Cypher 템플릿 구문 확인 |
| 2 | `graph/types/relationships.py` | 948 | `tests/graph/test_relationships.py` | dataclass 생성, 유효성 검증, enum 값 |
| 3 | `core/text_chunker.py` | 658 | `tests/core/test_text_chunker.py` | 청킹 알고리즘, 빈 입력, 긴 텍스트, 오버랩 |
| 4 | `core/error_handler.py` | 683 | `tests/core/test_error_handler.py` | CircuitBreaker 상태 전이, retry 로직, fallback |
| 5 | `graph/types/enums.py` | 179 | `tests/graph/test_enums.py` | enum 값, 변환 메서드 |
| 6 | `core/bounded_cache.py` | 37 | `tests/core/test_bounded_cache.py` | maxsize, eviction |

### Phase 2: Medium (Mock 필요하지만 테스트 가능) — 8개 파일

| # | 소스 파일 | 줄 수 | 테스트 파일 | Mock 대상 |
|---|-----------|-------|------------|-----------|
| 7 | `handlers/writing_guide_handler.py` | 1,221 | `tests/medical_mcp/test_writing_guide.py` | Neo4j (BaseHandler) |
| 8 | `builder/metadata_extractor.py` | 1,353 | `tests/builder/test_metadata_extractor.py` | LLM client |
| 9 | `builder/entity_extractor.py` | 877 | `tests/builder/test_entity_extractor.py` | LLM client |
| 10 | `ontology/snomed_api_client.py` | 706 | `tests/ontology/test_snomed_api_client.py` | httpx (HTTP) |
| 11 | `builder/stats_parser.py` | 529 | `tests/builder/test_stats_parser.py` | LLM client |
| 12 | `solver/graph_search.py` | 659 | `tests/solver/test_graph_search.py` | Neo4j client |
| 13 | `builder/section_chunker.py` | 692 | `tests/builder/test_section_chunker.py` | LLM client |
| 14 | `builder/citation_context_extractor.py` | 731 | `tests/builder/test_citation_context.py` | LLM client |

### Phase 3: Hard (통합 테스트, 다중 의존) — 6개 파일

| # | 소스 파일 | 줄 수 | 테스트 파일 | 주요 난점 |
|---|-----------|-------|------------|-----------|
| 15 | `builder/unified_pdf_processor.py` | 1,878 | `tests/builder/test_pdf_processor.py` | LLM + 파일 I/O + async |
| 16 | `builder/important_citation_processor.py` | 1,114 | `tests/builder/test_citation_processor.py` | LLM + Neo4j |
| 17 | `solver/multi_hop_reasoning.py` | 988 | `tests/solver/test_multi_hop_reasoning.py` | Neo4j + LLM + 복합 로직 |
| 18 | `handlers/pubmed_handler.py` | 982 | `tests/medical_mcp/test_pubmed_handler.py` | PubMed API + Neo4j |
| 19 | `handlers/pdf_handler.py` | 858 | `tests/medical_mcp/test_pdf_handler.py` | 파일 I/O + LLM + Neo4j |
| 20 | `handlers/graph_handler.py` | 830 | `tests/medical_mcp/test_graph_handler.py` | Neo4j 중심 |

### 팀에이전트 구성

**Phase 1 실행 (3 에이전트 병렬)**
```
Agent 1: schema.py + relationships.py 테스트 작성
Agent 2: text_chunker.py + error_handler.py 테스트 작성
Agent 3: enums.py + bounded_cache.py 테스트 작성
```

**Phase 2 실행 (4 에이전트 병렬)**
```
Agent 1: writing_guide_handler.py + metadata_extractor.py 테스트
Agent 2: entity_extractor.py + snomed_api_client.py 테스트
Agent 3: stats_parser.py + graph_search.py 테스트
Agent 4: section_chunker.py + citation_context_extractor.py 테스트
```

**Phase 3 실행 (3 에이전트 병렬)**
```
Agent 1: unified_pdf_processor.py + important_citation_processor.py 테스트
Agent 2: multi_hop_reasoning.py + pubmed_handler.py 테스트
Agent 3: pdf_handler.py + graph_handler.py 테스트
```

### 완료 기준
- [x] Phase 1: +6 테스트 파일
- [x] Phase 2: +8 테스트 파일
- [x] Phase 3: +6 테스트 파일
- [x] 전체 2,360 테스트 통과

---

## D-008: ValueError → 커스텀 예외 전환

### 개요

| 항목 | 내용 |
|------|------|
| **현재 상태** | 33개 `raise ValueError` + 3개 `raise RuntimeError` → generic 예외 사용 |
| **목표** | 커스텀 예외 계층(`ValidationError`, `ProcessingError`, `LLMError` 등) 활용 |
| **전략** | 모듈별 점진적 전환, raise와 except 동시 수정 |
| **주의**: `int()`, `float()` 파싱의 `except ValueError`는 변경하지 않음 (Python 내장 사용) |

### 전환 매핑

| 대상 예외 | 건수 | 대상 파일 |
|-----------|------|-----------|
| `ValidationError` | 18 | neo4j_client(7), snomed_enricher(3), inference_rules(2), pubmed_enricher(2), spine_snomed_mappings(1), agentic_rag(2), unified_pipeline(1) |
| `ProcessingError` | 8 | section_chunker(2), summary_generator(1), batch_processor(3), models(1), reference_handler(1) |
| `LLMError` | 5 | unified_pdf_processor(2), citation_context_extractor(2), summary_generator(1) |
| `Neo4jError` | 1 | base_handler(1) |

### except 수정 필요 사이트 (5곳)

| 파일 | 현재 | 변경 후 |
|------|------|---------|
| `handlers/base_handler.py:67` | `except ValueError` | `except (ValueError, Neo4jError)` |
| `builder/pubmed_enricher.py:335` | `except ValueError` | `except ValidationError` |
| `builder/pubmed_enricher.py:479` | `except ValueError` | `except ValidationError` |
| `medical_mcp/server.py:283` | `except ValueError` | `except (ValueError, ValidationError)` |
| `handlers/graph_handler.py:785` | `except ValueError` | `except (ValueError, ValidationError)` |

### 팀에이전트 구성 (3 에이전트)

**Agent 1: graph/ 모듈 (11건)**
```
파일:
- src/graph/neo4j_client.py — 7건 → ValidationError (VAL_INVALID_VALUE)
- src/graph/snomed_enricher.py — 3건 → ValidationError (VAL_INVALID_VALUE)
- src/graph/inference_rules.py — 2건 → ValidationError (VAL_INVALID_VALUE, VAL_MISSING_FIELD)

각 파일 상단에 from core.exceptions import ValidationError, ErrorCode 추가
raise ValueError("msg") → raise ValidationError(message="msg", error_code=ErrorCode.VAL_INVALID_VALUE)
```

**Agent 2: builder/ 모듈 (16건)**
```
파일:
- src/builder/pubmed_enricher.py — 2건 → ValidationError + except 2곳 수정
- src/builder/section_chunker.py — 2건 → ProcessingError
- src/builder/summary_generator.py — 1 ValueError → ProcessingError, 1 RuntimeError → LLMError
- src/builder/batch_processor.py — 3건 → ProcessingError
- src/builder/unified_pdf_processor.py — 2건 → LLMError
- src/builder/citation_context_extractor.py — 2건 → LLMError
- src/builder/pubmed_bulk_processor.py — 1 RuntimeError → ProcessingError

각 파일 상단에 필요한 import 추가
```

**Agent 3: 나머지 모듈 (9건 + except 3곳)**
```
파일:
- src/ontology/spine_snomed_mappings.py — 1건 → ValidationError
- src/core/models.py — 1건 → ProcessingError
- src/core/config.py — 2건 → ValidationError
- src/solver/agentic_rag.py — 2건 → ValidationError
- src/solver/unified_pipeline.py — 1건 → ValidationError
- src/medical_mcp/handlers/base_handler.py — 1건 → Neo4jError + except 수정
- src/medical_mcp/handlers/reference_handler.py — 1 RuntimeError → ProcessingError
- src/medical_mcp/medical_kag_server.py — 1건 → ValidationError
- src/medical_mcp/server.py — except ValueError → except (ValueError, ValidationError)
- src/medical_mcp/handlers/graph_handler.py — except ValueError → except (ValueError, ValidationError)
```

### 완료 기준
- [x] `raise ValueError` 0건 (프로젝트 코드, int()/float() 파싱 제외)
- [x] `raise RuntimeError` 0건
- [x] 커스텀 예외 사용률 100%
- [x] except 사이트 5곳 업데이트
- [x] 2,360 테스트 전체 통과

---

## 실행 순서 권장

```
Phase A (독립 실행 가능, 병렬):
├── D-006: text_chunker 분리 (~30분, 1 에이전트)
├── D-008: 예외 전환 (~1시간, 3 에이전트)
└── D-007 Phase 1: Easy 테스트 (~1시간, 3 에이전트)

Phase B (D-005는 단독 실행 권장):
└── D-005: Neo4jClient 분리 (~1.5시간, 3 에이전트)

Phase C (D-005 완료 후):
├── D-007 Phase 2: Medium 테스트 (~1.5시간, 4 에이전트)
└── D-007 Phase 3: Hard 테스트 (~2시간, 3 에이전트)
```

> D-005(Neo4jClient 분리)와 D-007(테스트 작성)은 같은 파일을 건드릴 수 있으므로 순차 실행 권장.
> D-006, D-008은 D-005와 파일 충돌이 적어 병렬 실행 가능.
