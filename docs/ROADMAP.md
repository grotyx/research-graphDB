# Spine GraphRAG - 개선 로드맵

> **Version**: 1.27.0 | **Updated**: 2026-03-17
> **목적**: 시스템 보완사항, 개선 방향, 기술 부채를 우선순위별로 정리
> **상태**: 🔴 미착수 | 🟡 진행중 | ✅ 완료 | ⏸️ 보류

---

## 1. Retrieval 품질 개선

현재 시스템은 LLM semantic chunking + 3-way hybrid ranking + SNOMED ontology expansion을 사용.
아래 기법들로 retrieval precision/recall을 더 높일 수 있음.

### 1.1 Contextual Embedding Prefix (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | chunk별 독립 임베딩. chunk가 어느 논문/섹션에서 왔는지 임베딩에 미반영 |
| **개선** | chunk content 앞에 `"[{title} | {section} | {year}] "` prefix를 붙인 뒤 임베딩 |
| **효과** | Anthropic contextual retrieval 논문 기준 retrieval failure 49% 감소 |
| **난이도** | 낮음 (임베딩 생성 시 prefix 추가만) |
| **비용** | 기존 chunk 재임베딩 필요 (OpenAI API 비용) |

**구현 방향:**
```python
# core/embedding.py 또는 pubmed_processor.py
def embed_chunk_with_context(chunk_content, title, section, year):
    prefixed = f"[{title} | {section} | {year}] {chunk_content}"
    return embed(prefixed)
```

**상태:** ✅ 완료 (v1.27.0)

---

### 1.2 Cross-Encoder Reranker (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | 3-way hybrid ranking (semantic 0.4 + authority 0.3 + graph 0.3). Cross-encoder 없음 |
| **개선** | 초기 검색 top-30 → cross-encoder rerank → top-10 반환 |
| **효과** | NDCG@10 10-20% 개선 기대 (벡터 유사도의 false positive 제거) |
| **난이도** | 낮음 (API 한 줄 추가 또는 로컬 모델) |
| **옵션** | (A) Cohere Rerank API, (B) `bge-reranker-v2` 로컬, (C) Jina Reranker |

**구현 방향:**
```python
# solver/hybrid_ranker.py에 추가
async def rerank(self, query: str, results: list, top_k: int = 10):
    # Option A: Cohere
    response = cohere_client.rerank(query=query, documents=[r.content for r in results], top_n=top_k)
    # Option B: Local
    scores = cross_encoder.predict([(query, r.content) for r in results])
    return sorted(zip(results, scores), key=lambda x: x[1], reverse=True)[:top_k]
```

**상태:** ✅ 완료 (v1.27.0) — `solver/reranker.py` 신규, Cohere rerank-v3.5, graceful fallback

---

### 1.3 HyDE (Hypothetical Document Embedding) (중간)

| 항목 | 내용 |
|------|------|
| **현재** | query를 직접 임베딩하여 검색 |
| **개선** | query → LLM이 가상 답변 생성 → 가상 답변을 임베딩하여 검색 |
| **효과** | 복잡한 질문(비교, 메커니즘)에서 검색 정확도 향상. 단순 키워드 질문엔 효과 적음 |
| **난이도** | 중간 (LLM 호출 1회 추가) |
| **비용** | 검색마다 LLM 호출 1회 (Haiku로 충분) |

**상태:** ✅ 완료 (v1.27.0) — `use_hyde=True`로 활성화, Haiku 가상답변 생성

---

### 1.4 Late Chunking (낮음)

| 항목 | 내용 |
|------|------|
| **현재** | LLM이 생성한 chunk를 개별 임베딩 |
| **개선** | 전체 문서를 long-context 모델로 한번에 임베딩 → chunk 경계에서 pooling |
| **효과** | 각 chunk 임베딩에 문서 전체 맥락 반영 |
| **난이도** | 높음 (LLM chunking과 구조적 호환 어려움, 별도 파이프라인 필요) |
| **판단** | 1.1 Contextual Prefix로 대부분의 효과를 얻을 수 있어 **우선순위 낮음** |

**상태:** ⏸️ 보류 (1.1로 대체 가능)

---

### 1.5 Multi-Vector Retrieval (중간)

| 항목 | 내용 |
|------|------|
| **현재** | chunk 임베딩 1개 + paper abstract 임베딩 1개 |
| **개선** | chunk 임베딩 + paper summary 임베딩 + entity name 임베딩을 **함께** 검색 |
| **효과** | 다른 granularity에서의 매칭으로 recall 증가 |
| **난이도** | 중간 (추가 벡터 인덱스 + 결과 병합) |

**상태:** 🔴 미착수

---

## 2. Reasoning & Intelligence 고도화

### 2.1 Hybrid Ranker 동적 가중치 (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | 고정 가중치: semantic 0.4 + authority 0.3 + graph 0.3 |
| **개선** | 쿼리 유형별 동적 조정 |
| **효과** | comparison 쿼리, mechanism 쿼리, evidence 쿼리에 따라 최적 검색 전략 |

```
comparison 쿼리 ("TLIF vs UBE"):  graph 0.6 + semantic 0.2 + authority 0.2
evidence 쿼리 ("Level 1 evidence for"): authority 0.5 + semantic 0.3 + graph 0.2
mechanism 쿼리 ("how does fusion work"): semantic 0.6 + graph 0.3 + authority 0.1
```

**상태:** ✅ 완료 (v1.27.0) — `QUERY_TYPE_WEIGHTS` 4개 프로필, `get_weights_for_query_type()`, `search(query_type=)` 파라미터 추가
**관련 파일:** `solver/hybrid_ranker.py`, `orchestrator/query_pattern_router.py`

---

### 2.2 Evidence Synthesis 강화 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | GRADE 기반 conflict detection, 기본 synthesis |
| **개선** | 가중 평균 효과 크기 계산, 이질성 검정(I²), forest plot 데이터 생성 |
| **효과** | 메타분석 수준의 근거 종합 자동화 |

**상태:** 🔴 미착수
**관련 파일:** `solver/conflict_detector.py`, `solver/evidence_synthesizer.py`

---

### 2.3 Agentic RAG (중간)

| 항목 | 내용 |
|------|------|
| **현재** | 단일 검색 → 결과 반환 |
| **개선** | 복잡한 질문을 하위 질문으로 분해 → 각각 검색 → 결과 통합 추론 |
| **효과** | "50세 여성, L4-5 stenosis + DM, 최적 수술법은?" 같은 다단계 질문 처리 |

**상태:** 🔴 미착수 (`solver/agentic_rag.py` 골격 존재, 1,606줄)
**관련 파일:** `solver/agentic_rag.py`, `orchestrator/query_pattern_router.py`

---

### 2.4 Citation Network Analysis (낮음)

| 항목 | 내용 |
|------|------|
| **현재** | CITES 관계 4건만 (minimal) |
| **개선** | 인용 관계 대규모 구축 → 핵심 논문 탐지, 연구 동향 추적 |

**상태:** ⏸️ 보류 (인용 데이터 수집이 선행되어야 함)

---

## 3. Chunking & Embedding 개선

### 3.1 Chunk Quality Validation (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | LLM이 생성한 chunk를 검증 없이 저장 |
| **개선** | chunk 길이, 통계 포함 여부, 중복 여부를 자동 검증 |
| **효과** | 품질 낮은 chunk 필터링으로 검색 precision 향상 |

**구현 방향:**
- 30자 미만 chunk 필터링 (현재 있음)
- 200자 미만 tier1 chunk → tier2로 강등
- 동일 paper 내 chunk간 cosine similarity > 0.95 → 중복 제거
- statistics 없는 results chunk → key_finding=false로 수정

**상태:** ✅ 완료 (v1.27.0) — `builder/chunk_validator.py` 신규, ChunkValidator(길이필터, tier강등, 통계검증, 중복탐지)

---

### 3.2 Embedding 모델 업그레이드 (낮음)

| 항목 | 내용 |
|------|------|
| **현재** | OpenAI text-embedding-3-large (3072d) |
| **옵션** | Voyage-3 (의학 도메인 강점), Cohere embed-v4, OpenAI 후속 모델 |
| **판단** | 현재 모델이 충분히 강력. 벤치마크 결과 비교 후 판단 |

**상태:** ⏸️ 보류

---

## 4. Data Quality & Coverage

### 4.1 SNOMED Normalizer 동기화 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | 51개 orphan SNOMED 키가 normalizer에 미등록, 76건 reverse_map 충돌 |
| **개선** | orphan 키를 normalization_maps.py에 추가, 충돌 건 검토/해소 |
| **효과** | entity 정규화 커버리지 향상 → 검색 시 더 정확한 매칭 |

**상태:** ✅ 완료 (v1.27.0) — I+17, P+17, O+5 canonical 추가, 51 orphans 해소

---

### 4.2 IS_A 계층 확장 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | IS_A 커버리지: I:52%, P:49%, O:83%, A:34% |
| **개선** | SNOMED 매핑 추가 → parent_code 정의 → build_ontology 실행 |
| **효과** | ontology-aware search의 범위 확대 |

**상태:** 🟡 점진적 개선 중 (DV-NEW-015)

---

### 4.3 Taxonomy 리프 노드 논문 임포트 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | 36개 리프 노드에 Paper 미연결 (v1.26.1에서 57→36 개선) |
| **개선** | 나머지 36개에 대해 PubMed 검색 + 임포트 |
| **효과** | 모든 taxonomy 노드가 실제 데이터와 연결 |

**상태:** 🟡 진행중 (20편 임포트 완료, 36개 잔여)

---

## 5. 코드 품질 & 아키텍처

### 5.1 tiered_search.py sync-in-async (완료)

> v1.26.2에서 해소: `loop.run_until_complete()` → proper `async/await`. RuntimeWarning 41→10.

**상태:** ✅ 완료 (CA-NEW-001)

---

### 5.2 medical_kag_server.py 크기 (낮음)

| 항목 | 내용 |
|------|------|
| **현재** | 3,744줄 (52 메서드). D-001/D-012에서 7,178→3,744줄로 축소 |
| **개선** | 추가 분리 (helper 메서드 → 별도 유틸 모듈) |
| **판단** | 기능 추가 없는 순수 리팩토링이므로 **우선순위 낮음** |

**상태:** ⏸️ 보류 (CA-NEW-003, D-012 후속)

---

### 5.3 llm ↔ cache 순환 의존 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | `cache/cache_manager.py`가 `llm.cache`를 직접 import |
| **개선** | `llm/cache.py` → `core/llm_cache.py`로 이동 또는 lazy import |

**상태:** 🔴 미착수 (CA-NEW-005)
**관련 파일:** `cache/cache_manager.py`, `cache/semantic_cache.py`, `llm/cache.py`

---

### 5.4 테스트 커버리지 확대 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | 3,802 tests, 67% 파일 커버리지. 대형 무테스트 파일 24개 |
| **우선순위** | `unified_pdf_processor.py`(1,907줄), `core/embedding.py`(517줄), `search_dao.py`(348줄) |

**상태:** ✅ 완료 (v1.27.0) — 127개 신규 테스트 (embedding 51, search_dao 35, pdf_processor 41). 3,929 tests total

---

### 5.5 MCP 입력 검증 강화 (완료)

> v1.26.2에서 해소: `BaseHandler.validate_string_length/validate_list_length` 추가.

**상태:** ✅ 완료 (CA-NEW-002)

---

## 6. Evaluation & Benchmark

### 6.1 Gold Standard Annotation (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | 29개 질문, 517편 후보 논문 생성 완료. 전문가 annotation 미완료 |
| **개선** | 전문가 annotation → relevance 판정 (relevant/partially/irrelevant) |
| **효과** | 정량적 벤치마크 실행 가능 (P@K, NDCG, MRR) |

**상태:** 🟡 진행중 (annotation sheet 생성 완료, 판정 작업 대기)

---

### 6.2 Baseline 벤치마크 실행 (높음 ⭐)

| 항목 | 내용 |
|------|------|
| **현재** | B1(Keyword), B2(Vector), B3(LLM Direct), B4(GraphRAG) 코드 완성 |
| **개선** | Gold Standard annotation 완료 후 4개 baseline 벤치마크 실행 + 결과 분석 |
| **효과** | 논문에 정량적 결과 포함 가능 |

**상태:** 🔴 미착수 (6.1 annotation 완료 후)
**관련 파일:** `evaluation/benchmark.py`, `evaluation/baselines.py`

---

### 6.3 RAGAS End-to-End 평가 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | Retrieval 메트릭만 구현 |
| **개선** | RAGAS 기반 답변 품질 평가: Faithfulness, Answer Relevancy, Context Precision, Citation Fidelity |
| **효과** | 시스템 전체 성능(검색 + 생성) 평가 |

**상태:** 🔴 미착수

---

## 7. 인프라 & 운영

### 7.1 pubmed-import 스킬 고도화 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | 스킬 정의 완료, PubMed 검색/fulltext 다운로드/Sonnet 추출 파이프라인 설계 |
| **개선** | 실제 Sonnet subagent 병렬 추출 워크플로우 end-to-end 검증, JSON 검증 로직 추가 |

**상태:** 🟡 진행중

---

### 7.2 Neo4j 백업 & 복구 (낮음)

| 항목 | 내용 |
|------|------|
| **현재** | Docker volume 기반 (수동 백업) |
| **개선** | 자동 일일 백업 스크립트, 복구 절차 문서화 |

**상태:** 🔴 미착수

---

### 7.3 pdf_handler Path Traversal 방어 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | MCP pdf_handler가 파일 경로를 직접 받지만 path traversal (`../`) 방어 없음 |
| **개선** | `resolve().is_relative_to(base_dir)` 패턴 적용 |
| **난이도** | 낮음 |

**상태:** ✅ 완료 (v1.27.0) — `validate_file_path()` 강화, `prepare_pdf_prompt()` 적용
**관련 파일:** `src/medical_mcp/handlers/pdf_handler.py`, `src/medical_mcp/handlers/base_handler.py`

---

### 7.4 relationship_builder N+1 배치화 (중간)

| 항목 | 내용 |
|------|------|
| **현재** | `relationship_builder.py`에 7개 N+1 sequential DB write 패턴 |
| **개선** | `UNWIND` 배치 쿼리 또는 `asyncio.gather()` 병렬화 |
| **효과** | 대량 임포트 시 2-5x 속도 개선 |

**상태:** ✅ 완료 (v1.27.0) — 5개 N+1 패턴 UNWIND 배치화, `_batch_create_is_a_relations()` 헬퍼 추가
**관련 파일:** `src/graph/relationship_builder.py`

---

## 우선순위 요약

### 즉시 (Impact ⬆️, Effort ⬇️)

| # | 항목 | 효과 | 난이도 |
|---|------|------|--------|
| 1 | ~~1.1 Contextual Embedding Prefix~~ | ~~retrieval 49% 개선~~ | ✅ v1.27.0 |
| 2 | ~~1.2 Cross-Encoder Reranker~~ | ~~NDCG 10-20% 개선~~ | ✅ v1.27.0 |
| 3 | ~~1.3 HyDE~~ | ~~복잡 쿼리 개선~~ | ✅ v1.27.0 |
| 4 | ~~4.1 SNOMED Normalizer 동기화~~ | ~~정규화 품질~~ | ✅ v1.27.0 |
| 5 | **6.1 Gold Standard Annotation** | 논문용 정량 결과 | 중간 (수작업) |

### 다음 스프린트 (Impact ⬆️, Effort ➡️)

| # | 항목 | 효과 | 난이도 |
|---|------|------|--------|
| 6 | ~~2.1 Hybrid Ranker 동적 가중치~~ | ~~쿼리별 최적화~~ | ✅ v1.27.0 |
| 7 | **6.2 Baseline 벤치마크** | 논문 데이터 | 중간 |
| 8 | ~~3.1 Chunk Quality Validation~~ | ~~precision 향상~~ | ✅ v1.27.0 |

### 장기 (Impact ⬆️, Effort ⬆️)

| # | 항목 | 효과 | 난이도 |
|---|------|------|--------|
| 9 | **2.3 Agentic RAG** | 다단계 추론 | 높음 |
| 10 | **2.2 Evidence Synthesis 강화** | 메타분석 자동화 | 높음 |
| 11 | **6.3 RAGAS 평가** | 전체 시스템 평가 | 중간 |
| 12 | ~~5.4 테스트 커버리지~~ | ~~코드 품질~~ | ✅ v1.27.0 |

---

## 관련 문서

| 문서 | 역할 |
|------|------|
| [PRD.md](PRD.md) | 요구사항 정의 (v3.1 계획 포함) |
| [CODE_AUDIT.md](CODE_AUDIT.md) | CA Deferred Items |
| [DATA_VALIDATION.md](DATA_VALIDATION.md) | DV Open Issues |
| [PUBLICATION_PLAN.md](PUBLICATION_PLAN.md) | 논문 출판 계획 |
| [QC_CHECKLIST.md](QC_CHECKLIST.md) | QC Known Accepted |

---

*Last updated: 2026-03-17 by v1.27.0 QA 스캔 + ROADMAP 5개 항목 구현 완료 (2.1, 3.1, 5.4, 7.3, 7.4)*
