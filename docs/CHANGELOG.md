# Spine GraphRAG Changelog

## Version History

### v1.30.0: GraphRAG Pattern 2 + Graph-specific Questions + Evaluation (2026-03-18)

- **B4 Pipeline 전면 교체**: Pattern 3 (dual merge) → **Pattern 2 (Graph Filter → Vector Rank)**
  - Entity extraction (Haiku) → Graph filtering (STUDIES/INVESTIGATES) → Vector ranking
  - Graph는 "범위 좁히기", Vector는 "순위 결정" — 역할 분리
  - GraphRAG-FI (EMNLP 2025) 방법론 참고
- **Evidence Chain 답변 형식**: Intervention→Pathology→Outcome 구조화 답변
- **PubMed fallback**: DB에 3편 미만이면 PubMed 실시간 보완
- **Graph-specific 질문 5개** (GR-001~005): multi_intervention_comparison, structured_comparison, evidence_chain, graph_traversal, comprehensive_evidence
- **BS 논문 30편 임포트**: Modic(10), Smoking(10), Stem Cell(10) → DB 773편
- **Phase B 평가표 수정**: blinding 위반 요소 제거, 시스템 정체 누출 방지
- **Blinded 평가 프레임워크**: prompt + scoring log + CSV for GPT/Gemini/Claude/PSM/PHJ

### v1.29.0 Post-Release: LLM Reranker + DB 확장 + 평가 파이프라인 (2026-03-18)

- **LLM Reranker 추가** (`solver/reranker.py`): Haiku 기반 질문 적합성 재정렬
  - Cohere 대신 기존 Anthropic API 사용 (추가 비용 없음)
  - 70편 후보 → 질문에 직접 관련된 논문만 상위로 재정렬
  - DG-003 개선: BMP/obesity MA(무관) → cage subsidence predictor(관련)로 교체
- **Query-type detection**: comparison/evidence/mechanism/default 자동 감지 → 동적 가중치
- **DB 확장**: 638 → 743편 (+105편, 7개 부족 주제 PubMed 임포트)
  - CDR/ACDF(15), Laminoplasty(15), ESI(15), Odontoid(15), Burst Fracture(15), SINS/Tumor(15), PSO/VCR(15)
  - 정식 파이프라인: Haiku 추출 + fulltext + chunk embedding + relationship builder
- **Evidence Level 수정**: study_design 기반 재분류(148편), Chunk EL 동기화(8120개)
  - 1a=1b=1.0 (RCT=MA 동등), Case Report 3→4 (OCEBM 기준)
  - search_dao.py Cypher 하드코딩 가중치도 동기화
- **평가 파이프라인**: answer_generator.py + llm_judge.py + Phase B scoring sheet
  - DG-001~005 × 4 baselines 답변 생성 + 3개 LLM Judge 채점 완료
  - B4 평균 21.3/25 (1위), B2 20.1, B3 15.2, B1 13.9

### v1.29.0 (2026-03-17)

#### New Features
- **Multi-Vector Retrieval** (ROADMAP 1.5): RRF-based chunk + paper abstract embedding fusion via `search_dao.multi_vector_search()`, `use_multi_vector=True` option
- **Agentic RAG** (ROADMAP 2.3): Clinical query decomposition (`ClinicalQueryDecomposer`), parallel sub-query execution, result aggregation (`ResultAggregator`), `agentic_solve()` pipeline
- **Evidence Synthesis Enhancement** (ROADMAP 2.2): Weighted effect size (inverse-variance, Cochrane method), I² heterogeneity test, forest plot data generation
- **Dynamic Weights Integration** (#4): `unified_pipeline.py` now passes query type to `hybrid_ranker.search(query_type=)` for query-aware ranking
- **ChunkValidator Pipeline Integration** (#5): Automatic chunk quality validation in `pubmed_processor.store_llm_chunks()` before embedding

#### Infrastructure
- **Cache Circular Dependency Fix** (ROADMAP 5.3): `llm/cache.py` → `core/llm_cache.py` canonical location, backward-compat re-export shim
- **Paper Embedding Batch Script** (#9): `scripts/backfill_paper_embeddings.py` with --dry-run, --max-papers, contextual prefix support

#### Test Coverage
- +65 new tests (3,964 → 4,029 total)
  - `test_agentic_rag_decomposer.py` (20): query decomposition, aggregation, pipeline
  - `test_evidence_synthesizer_meta.py` (32): weighted effect size, I², forest plot
  - `test_search_dao.py` (+10): multi-vector RRF fusion, dedup, partial failures
  - `test_tiered_search.py` (+4): multi-vector flag integration

### v1.28.0 (2026-03-17)

- **Hybrid Ranker Dynamic Weights** (ROADMAP 2.1): Query-type-aware weight profiles (comparison/evidence/mechanism/default) via `QUERY_TYPE_WEIGHTS` and `search(query_type=)` parameter
- **Chunk Quality Validation** (ROADMAP 3.1): New `builder/chunk_validator.py` — ChunkValidator with length filter, tier demotion, statistics check, near-duplicate detection
- **Path Traversal Defense** (ROADMAP 7.3): Enhanced `validate_file_path()` in BaseHandler, applied to all MCP file-path-accepting methods
- **N+1 Query Batching** (ROADMAP 7.4): 5 sequential DB write patterns in `relationship_builder.py` converted to Cypher UNWIND batch operations (2-5x import speedup)
- **Test Coverage**: +162 new tests (3,802 → 3,964 total)
  - `test_embedding.py` (51): contextual prefix, OpenAI generator, cosine similarity
  - `test_search_dao.py` (35): vector/hybrid search filters, delegation, edge cases
  - `test_unified_pdf_processor_core.py` (41): JSON repair, dataclasses, validation
  - `test_chunk_validator.py` (35): all 4 validation rules, full pipeline, stats
- **QA Fixes**:
  - QC: TERMINOLOGY_ONTOLOGY.md version sync, .env.example env vars (PUBMED_EMAIL/API_KEY, MCP_MAX_USER_CACHE)
  - CA: Silent exception in pubmed_processor → logger.debug (CA-NEW-003)
  - DV: Orphan test chunks cleanup, case-insensitive entity merges, TREATS paper_count recount, study_design normalization, evidence_level fix (pmid_34559764 "unknown"→"5")
- **QA Scores**:
  - QC: CLEAN (all versions synced, 3,964 tests passed)
  - CA: 9.5/10 (up from 7.7 — security, error handling, dependencies all 10/10)
  - DV: Level of Evidence consistency confirmed (638 papers, all canonical values)
- **Skill Update**: `pubmed-import` skill updated — correct class names (OpenAIEmbeddingGenerator, build_from_paper), added ChunkValidator step, contextual embedding prefix, TREATS backfill

### v1.27.0 (2026-03-17)

- **Contextual Embedding Prefix** (`core/embedding.py`, `builder/pubmed_processor.py`)
  - Chunk 임베딩 시 `[title | section | year]` prefix 추가 (Anthropic contextual retrieval 기법)
  - 비대칭 설계: chunk에만 prefix 적용, search query는 그대로
  - 환경변수 `EMBEDDING_CONTEXTUAL_PREFIX=true/false`로 on/off (기본: true)
  - 기존 chunk 영향 없음 (신규 임포트에만 적용)
- **HyDE (Hypothetical Document Embedding)** (`solver/tiered_search.py`)
  - 검색 전 LLM(Haiku)이 가상 답변 생성 → 가상 답변을 임베딩하여 검색
  - `use_hyde=True`로 활성화 (기본: false), SearchConfig에서 설정
  - 복잡한 비교/메커니즘 질문에서 검색 정확도 향상
- **Cross-Encoder Reranker** (`solver/reranker.py` 신규)
  - Cohere Rerank API (rerank-v3.5) 기반 교차 인코더 재순위
  - `use_reranker=True`로 활성화, Cohere 미설치 시 graceful fallback
  - 초기 검색 top-30 → rerank → top-10 반환
  - `pip install .[rerank]`로 Cohere 의존성 설치
- **SNOMED Normalizer 동기화** (`graph/normalization_maps.py`)
  - 51개 orphan SNOMED 키 해소: I+17, P+17, O+5 canonical 추가, 12개 기존 alias 확인
  - last-write-wins 충돌 1건 해소 (Facet Joint Degeneration)
- **테스트 +33**: contextual prefix 16, reranker 11, HyDE 7 → 총 3,802 tests

### v1.26.2 (2026-03-17)

- **QC/CA 전체 스캔 + 수정**
  - `tiered_search.py` sync-in-async 수정: `loop.run_until_complete()` → proper `async/await` (RuntimeWarning 41→10건 감소)
  - MCP 입력 길이 검증 추가: `BaseHandler.validate_string_length/validate_list_length` (query 10K, identifier 1K, list 100)
  - 7개 문서 버전 동기화 1.25.0→1.26.2, SNOMED 통계 696→735 갱신 (GRAPH_SCHEMA, TERMINOLOGY_ONTOLOGY, DEPLOYMENT)
  - MCP Docker 컨테이너 v1.25.0→v1.26.2 재시작
  - 테스트: 3,769 passed, 0 failed, warnings 41→10

### v1.26.1 (2026-03-17)

- **`/pubmed-import` 스킬 추가** (`.claude/skills/pubmed-import/`)
  - PubMed 검색 → 결과 확인 → Sonnet 병렬 추출 → Neo4j 임포트
  - Haiku API 대신 Claude Code Sonnet subagent 사용 (API 비용 무료)
  - 동일 추출 프롬프트 (`unified_pdf_processor.py` EXTRACTION_PROMPT) 활용
- **Fulltext 저장 기능** (`data/fulltext/`)
  - PMC/DOI fulltext를 `data/fulltext/{pmid}.txt`로 별도 보관
- **Taxonomy 리프 노드 연결**: PubMed 20편 임포트 → 미연결 리프 57→36개 (37% 감소)
- **DV 데이터 수복 7건**: DOI 중복 6쌍 삭제, Chunk paper_id 93건 복구, 고아 Chunk 10건 삭제, 대소문자 중복 16건 병합, study_design 26건 정규화, TREATS 74건 백필 + 3,219건 갱신, 고립 Paper 5건 복구
- **Public README 전면 개편** (`grotyx/research-graphDB`): 실전 워크플로우 5개, 파이프라인 다이어그램, DB 유지보수 섹션 추가

### v1.26.0 (2026-03-17)

- **3D Interactive Graph Visualization** (`web/pages/10_🌌_3D_Graph.py`)
  - WebGL 기반 3D force-directed graph (3d-force-graph CDN)
  - 4가지 뷰 모드: Intervention→Outcome, Ontology(IS_A), Full Graph, Paper Network
  - DAG 레이아웃, 노드 하이라이트, 파티클 애니메이션, Auto Rotate
- **Evaluation Framework** (`evaluation/`)
  - `metrics.py`: P@K, R@K, NDCG@10, MRR, ELA — 28개 유닛 테스트
  - `baselines.py`: B1(Keyword), B2(Vector), B3(LLM Direct), B4(GraphRAG)
  - Gold Standard 29개 질문, 517편 후보 논문
  - `benchmark.py`: CLI 벤치마크 실행기
- **Publication Plan** (`docs/PUBLICATION_PLAN.md`): 4편 핵심 논문 로드맵
- **PubMed 80편 신규 임포트**
  - Evaluation용 60편 (TR+20, TU+20, BS+20) + Taxonomy 리프 연결용 20편
  - DB: Paper 542 → 638, Chunk 9,022 → 9,869, 관계 33,321 → 40,076
- **SNOMED 매핑 확장**: 696 → 735개 (+39)
  - LLM Proposer 62개 후보 → 39개 적용
  - entity_normalizer 분리: 4,888줄 → 1,366줄(로직) + normalization_maps.py 3,543줄(데이터)
- **MCP Transport**: SSE → Streamable HTTP 전환 (연결 안정성 개선)
- **DV 데이터 수복 16건**
  - DOI 중복 Paper 10건 삭제, 대소문자 중복 엔티티 31쌍 병합
  - IS_A 순환 해소, TREATS 백필 141건, paper_count 갱신 6,000+건
  - Chunk paper_id 복구 307건, 고아 Chunk 30건 삭제
  - study_design 정규화 74건, tier 변환 398건
- **QC/CA/DV 전체 스캔**: 전 항목 PASS (Known Accepted 제외)
- **Taxonomy 리프 노드 개선**: 57 → 36개 미연결 (37% 감소)

### v1.25.0 Post-Release: Evaluation Framework + Publication Plan (2026-03-16)

- **논문 출판 계획 수립** (`docs/PUBLICATION_PLAN.md`): 6편 논문, 3 Phase 로드맵
  - 문헌 검색 기반 positioning (15편 관련 논문 분석)
  - v2 평가: RAGAS 기반 End-to-End 답변 품질 (Faithfulness, Citation Fidelity, Hallucination Rate)
  - 참고: Wu 2025 ACL (Medical Graph RAG), medRxiv 2025 (CKD GraphRAG)
- **Evaluation 프레임워크 구축** (`evaluation/`)
  - `metrics.py`: P@K, R@K, NDCG@10, MRR, ELA — 28개 유닛 테스트 통과
  - `baselines.py`: B1(Keyword), B2(Vector-only), B3(LLM Direct), B4(GraphRAG) 4종
  - `benchmark.py`: CLI 벤치마크 실행기 + 결과 저장
  - `annotator_helper.py`: Gold Standard 후보 논문 자동 검색
  - `import_to_neo4j.py` + `update_summaries.py`: PubMed → Neo4j 임포트 도구
- **Gold Standard 질문 29개** (`evaluation/gold_standard/questions.json`)
  - 5개 sub-domain: DG(10), DF(5), TR(5), TU(4), BS(5)
  - 5가지 유형: 비교(30%), 단일근거(25%), 합병증(20%), 적응증(15%), 최신근거(10%)
  - 517편 후보 논문 자동 생성 (`annotation_sheet.json`)
- **PubMed 60편 임포트**: TR+20, TU+20, BS+20 (최신 + top journal 위주)
  - Claude Code CLI로 entity 추출 (Haiku API 비용 0)
  - 60편 모두 summary, main_conclusion, abstract_embedding(3072d) 포함
  - Neo4j DB: 542 → 624편 (I:677, P:463, O:2833, A:208)

### v1.25.0 Post-Release: QA 전체 스캔 + SNOMED 확장 + 리팩토링 (2026-03-16)

- **SNOMED 매핑 확장**: 696 → 735개 (+39)
  - LLM SNOMED Proposer로 62개 후보 생성 → 39개 적용 (auto-apply 10 + review 29)
  - Intervention +17 (AI/ML 11, 수술재료/술기 6), Pathology +17, Outcome +5
  - IS_A 커버리지 개선: I 57.1→59.3%, P 50.7→53.1%
- **entity_normalizer.py 분리**: 4,888줄 → 1,366줄 (로직) + normalization_maps.py 3,543줄 (데이터)
- **DV 데이터 수복 9건**: 고아Chunk 5건, 중복엔티티 15쌍 병합, IS_A순환 해소, TREATS paper_count 2808건 갱신, DOI중복Paper 4건 병합, tier정규화 228건, study_design정규화 48건, TREATS백필 67건
- **QA 전체 결과**: QC 14P/1W/0F, CA 17P/4W/0F, DV 11P/10W/5F→전부 해소

### v1.25.0 Post-Release: 3D Interactive Graph Visualization (2026-03-12)

- **3D Knowledge Graph 페이지 추가** (`web/pages/10_🌌_3D_Graph.py`)
  - WebGL 기반 3D force-directed graph (3d-force-graph 라이브러리, CDN 로드)
  - 마우스 드래그 3D 회전, 스크롤 줌, 노드 클릭 카메라 포커스
  - 노드 호버 시 연결된 노드/링크만 하이라이트 (나머지 fade)
  - 링크 위 파티클 애니메이션 효과
  - 4가지 뷰 모드: Intervention→Outcome, Ontology(IS_A), Full Graph, Paper Network
  - DAG 레이아웃 지원 (top-down, bottom-up, left-right, radial)
  - 3D 스프라이트 텍스트 라벨 (on/off 토글)
  - Auto Rotate 모드, 5가지 배경 테마 선택
  - 노드 크기 = 논문 수 반영, 엣지 색상 = direction(improved/worsened)

### v1.25.0 Post-Release: MCP Transport SSE → Streamable HTTP 전환 (2026-03-04)

- **MCP Transport 전환**: SSE (long-lived stream) → Streamable HTTP (stateless HTTP POST)
  - SSE 연결 끊김 문제 근본 해결 — 프록시/NAT 타임아웃에 영향 없음
  - `docker-compose.yml`에 `command` 추가 (이미지 재빌드 불필요)
  - 클라이언트 설정: `"url": "http://host:7777/mcp"` (type/sse 경로 제거)
- **Streamable HTTP race condition 수정**: `transport.connect()` 완료 전 `handle_request()` 호출 시 `ValueError` 발생 → `asyncio.Event` 동기화 추가
- **문서 업데이트**: TROUBLESHOOTING.md MCP 섹션 전면 개정 (Streamable HTTP 가이드)

### v1.25.0: Scaling & Graph Enrichment — 6개 성능/구조 최적화 (2026-03-01)

수천 건 논문 규모 대비 성능 최적화 및 그래프 구조 확장.

#### Priority 1: Performance Optimization (3건)
- **1A. SIMILAR_TOPIC batch write**: N+1 개별 `create_paper_relation()` → UNWIND 일괄 쓰기 (relationship_builder.py)
- **1B. LIMIT before OPTIONAL MATCH**: `get_all_papers_with_relations()`에서 LIMIT을 OPTIONAL MATCH 이전으로 이동 — O(N×M) → O(limit×M) (neo4j_client.py)
- **1C. Fulltext index 활용**: `toLower(p.title) CONTAINS` → `db.index.fulltext.queryNodes('paper_text_search')` (cypher_generator.py, graph_handler.py)

#### Priority 2: Graph Structure Enrichment (3건)
- **2D. Chunk→Entity MENTIONS 관계**: Chunk에서 entity 이름 매칭 → UNWIND batch MENTIONS 생성 (relationship_builder.py, pubmed_processor.py)
- **2E. Intervention→Anatomy APPLIED_TO 관계**: Paper 경유 없이 수술법↔해부 부위 직접 연결 (relationship_builder.py, schema.py)
- **2F. IS_A expansion 병렬화**: `run_until_complete` 순차 루프 → `asyncio.gather()` 동시 확장 (tiered_search.py)

#### Documentation
- **GRAPH_SCHEMA.md**: SNOMED CT 아키텍처 설계 (Architecture Decision Record) 추가 — 정석 vs 현재 구현 비교 분석

#### Schema Changes
- New relationship: `MENTIONS` (Chunk→Intervention/Pathology/Outcome/Anatomy)
- New relationship: `APPLIED_TO` (Intervention→Anatomy)

#### Post-Release Fixes (10건)
- **CRITICAL**: `_create_applied_to_relations()` 비정규화 이름 → normalize 후 MATCH
- **CRITICAL**: `graph_traversal_search.py` `exists()` → `EXISTS { MATCH }` (Neo4j 5.x 호환)
- **CRITICAL**: `medical_kag_server.py` 동일 `exists()` → `EXISTS { MATCH }`
- **CRITICAL**: `graph_handler.compare_interventions` `server.find_evidence()` → `server.search_handler.find_evidence()`
- **HIGH**: `search_handler.adaptive_search` 필드명 `title`→`paper_title`, `score`→`final_score`
- **MEDIUM**: PDF/analyze_text 경로 `create_chunk_mentions()` 호출 추가
- **MEDIUM**: `MinimalSpineMeta` 클래스 레벨 mutable default → `__init__`
- **MEDIUM**: `analyze_text` `ExtractedMetaCompat` `study_type`/`study_design` 채움
- **LOW**: `spine: any` → `Any` 타입 어노테이션
- **LOW**: 6개 Cypher 쿼리 LIMIT 추가

#### QA Fixes — QC/CA/DV 전면 스캔 + 테스트 커버리지 확장 (2026-03-02)

**QC (Quality Control) 4건 해소:**
- QC-2026-001: `docs/DEPLOYMENT.md` 4곳 v1.24.0 → v1.25.0 버전 동기화
- QC-2026-002: `medical_kag_server.py` 4개 함수 return type hint 추가
- QC-2026-003: MCP Docker 컨테이너 재시작 (소스 바인드 마운트 반영)
- QC-2026-004: `entity_normalizer.py`에 30개 orphan SNOMED key alias 동기화

**CA (Code Audit) 3건 해소:**
- CA-NEW-001: `logger.error()` 5곳에 `exc_info=True` 추가 (pubmed_bulk_processor, pubmed_processor, unified_pdf_processor, embedding, snomed_linker)
- CA-NEW-002: LLM 클라이언트 3곳 generic `Exception` → `LLMError` (claude_client, gemini_client)
- CA-NEW-003: DOI/PMC fetcher 중복 retry 로직 → `core/http_utils.py` 공유 유틸 추출

**DV (Data Validation) 8건 해소:**
- DV-NEW-026: SNOMED enrichment 일괄 적용
- DV-NEW-027: TREATS 관계 26건 백필 + 681건 paper_count 갱신
- DV-NEW-028: Anatomy region 수복
- DV-NEW-029: IS_A 순환참조 3건 해소 (양방향 IS_A → 단방향 유지)
- DV-NEW-030: Orphan 노드 10건 IS_A 계층 연결 (3 Pathology + 7 AI Intervention)
- DV-NEW-031: Pathology-Outcome 교차 라벨 3건 → DV-A-011 허용 등록
- DV-NEW-032: SNOMED 코드 충돌 수정 (Tokuhashi Score: 341 → 808)
- DV-NEW-033: Lumbar arthrodesis SNOMED 코드 수정 (341 → 132)

**D-011: Test Coverage Expansion Phase 2 (1,019 tests 신규):**
- 20개 모듈에 대한 단위 테스트 작성 (기존 2,722 → 3,741 tests, 37% 증가)
- Batch 1: unified_pdf_processor(65), writing_guide_handler(80), important_citation_processor(42), citation_context_extractor(46)
- Batch 2: search_handler(32), sse_server(39), llm_semantic_chunker(57), batch_processor(46)
- Batch 3: doi_fulltext_fetcher(46), reasoning_handler(30), claude_client(42), snomed_enricher(56)
- Batch 4: pico_extractor(64), embedding_cache(53), relationship_dao(53), llm_metadata_extractor(62)
- Batch 5: document_handler(36), gemini_client(36), document_type_detector(92), reference_handler(42)

**신규 파일:**
- `src/core/http_utils.py`: 공유 async HTTP retry 유틸리티
- `tests/` 하위 20개 테스트 파일

### v1.24.2: Critical Bug Fixes — Import/Search/Graph 전면 검증 (2026-03-01)

22건의 버그를 수정하여 전체 파이프라인(Import → Graph Build → Search) 안정성을 확보.

#### CRITICAL Fixes (5건)
- **`medical_kag_server.py` analyze_text()**: `df` 미정의 → `field`로 수정 — `build_from_paper()` 영구 실패 해소
- **`search_dao.py` hybrid_search()**: MATCH 패턴 필터에 내장된 `WHERE`가 다중 필터 시 invalid Cypher 생성 → MATCH/WHERE 분리
- **`hybrid_ranker.py` semantic score**: `raw.get("score")` → `raw.get("vector_score")` — semantic 점수 항상 0이던 문제 수정
- **`pubmed_processor.py` process_text_with_llm()**: 존재하지 않는 `build_relationships()` → `build_from_paper()` + 올바른 ExtractedMetadata 구성
- **`json_handler.py` add_json()**: raw dict → `_ExtractedMetaCompat` dataclass — Paper 노드 생성 실패 수정

#### HIGH Fixes (8건)
- **`hybrid_ranker.py` recency boost**: `raw.get("paper_year")` → `raw.get("year")` — recency boost 영구 1.0 수정
- **`relationship_builder.py` taxonomy 이름 불일치**: `"Osteotomy Surgery"` → `"Osteotomy"`, `"Motion Preservation Surgery"` → `"Motion Preservation"` — IS_A 매칭 수정
- **`relationship_builder.py` Intervention IS_A 누락**: `create_investigates_relations()`에서 `_auto_create_is_a_relation()` 호출 추가
- **`neo4j_client.py` anatomy 필드**: `anat.level` → `anat.name` — SIMILAR_TOPIC 관계의 anatomy 데이터 수정
- **`pubmed_processor.py` delete_paper_chunks()**: `DELETE c` → `DETACH DELETE c` — HAS_CHUNK 관계 존재 시 에러 수정
- **`tiered_search.py` entity type 불일치**: `'procedure'`, `'disease'`, `'measurement'`, `'symptom'` 소문자 추가
- **`tiered_search.py` 다중 entity**: 같은 타입 entity 여러 개일 때 마지막만 유지 → list 수집으로 변경
- **`pdf_handler.py` None → ""**: SpineMetadata str 필드에 None 대신 빈 문자열 전달

#### MEDIUM Fixes (6건)
- **`pubmed_processor.py` _build_spine_metadata()**: `anatomy_levels` 복수형 키 우선 체크 추가
- **`pubmed_processor.py` _build_spine_metadata()**: `pathologies` 복수형 키 우선 체크 추가
- **`hybrid_ranker.py` WHERE 절 위치**: `a IS NULL OR a.is_significant = true` 절을 올바른 OPTIONAL MATCH 뒤로 이동
- **`relationship_builder.py` 빈 outcome 가드**: 빈 `outcome.name` 시 continue — 빈 Outcome 노드 생성 방지
- **`json_handler.py` BuildResult 직렬화**: `BuildResult` 객체 → dict 변환 후 반환

#### CA/QC/DV Fixes (QA 스캔 기반, 3건)
- **CA-NEW-001~008**: hybrid_ranker N+1→UNWIND, relationship_dao LIMIT, search_dao 에러 핸들링, entity_normalizer 크기 제한, pubmed_processor 재시도, pdf_processor 크기 체크, embedding 배치 에러, config 검증
- **QC-2025-001~006**: 버전 동기화, docstring, GRAPH_SCHEMA 확장 코드 범위, Outcome IS_A 100%, study_design 정규화
- **DV-NEW-026~032**: SNOMED enrichment, TREATS backfill, Anatomy region 수복

---

### v1.24.1: SNOMED Mapping Expansion (2026-02-28): 621→653개 매핑 확장

#### 매핑 확장 요약
- **총 매핑 수**: 621 → 653개 (+32 신규 SNOMED 개념: I:+10, P:+10, O:+7, A:+5)
- **Extension 코드 범위 확장**: `procedure_ext2`(700-799), `observable_ext`(800-899), `disorder_ext`(900-949) 신규 도입
- **Orphan key 동기화**: `spine_snomed_mappings.py`의 166개 orphaned key를 `entity_normalizer.py`에 alias로 동기화
- **Alias 대폭 추가**: ~280개 alias variation 추가로 term matching 정확도 향상
- **Synonym overlap 정리**: PCO→SPO merge, PELD/PETD split, Nonunion→Pseudarthrosis merge, ADR/CDR split
- **LLM fallback 후보 풀**: snomed_proposer.py candidate pool 30→50 확대

#### SNOMED 통계
- Interventions: 194 → 204 (+10)
- Pathologies: 178 → 188 (+10)
- Outcomes: 187 → 194 (+7)
- Anatomy: 62 → 67 (+5)

---

### v1.24.0 Post-Release Fixes (2026-02-28): 검색 파이프라인 온톨로지 실연결

#### SNOMED 코드 파이프라인 수정
- **snomed_id 속성명 수정**: `tiered_search.py`에서 `entity.snomed_code` → `entity.snomed_id` (MedicalEntity 실제 필드명)
- **ParsedQuery.snomed_codes fallback**: `tiered_search`, `adaptive_search` 모두 엔티티 개별 snomed_id 없을 시 dict fallback 추가
- **adaptive_search 온톨로지 연결**: `search_handler.py`에서 QueryParser 파싱 → graph_filters + snomed_codes 추출 → `hybrid_search()` 전달
- **unified_pipeline 온톨로지 연결**: `spine_snomed_mappings` 4개 lookup 함수로 SNOMED 코드 추출 → `hybrid_ranker.search(snomed_codes=...)` 전달

#### 4개 엔티티 IS_A 확장 완전 연결
- **tiered_search**: outcome/anatomy 엔티티 추출 + IS_A 확장 태스크 추가
- **search_dao**: outcome (`INVESTIGATES→AFFECTS`), anatomy (`INVOLVES`) singular/plural Cypher 필터 추가
- **search_handler**: adaptive_search에서 outcome/anatomy graph_filters 추출
- **unified_pipeline**: `get_snomed_for_anatomy` import + anatomy SNOMED lookup + `expanded_outcomes`/`expanded_anatomies` 저장

#### SNOMED ontology_distance 4개 엔티티 확장
- **search_dao SNOMED Cypher**: `INVESTIGATES|STUDIES` → `INVESTIGATES|STUDIES|INVOLVES` (Anatomy 직접 매칭 추가)
- **Outcome 2홉 매칭**: `(p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(outcome_target:Outcome)` 별도 OPTIONAL MATCH
- **COALESCE 로직**: `direct_target` 우선, 없으면 `outcome_target` 사용 → 통합 `ontology_distance` 계산

---

### v1.24.0 (2026-02-28): Ontology-Based GraphRAG 전면 재설계

**핵심 변경:** Vector RAG + 간단한 그래프 필터링에서 SNOMED-CT 온톨로지 기반 다중 홉 그래프 순회 + 근거 체인 추론이 가능한 진정한 GraphRAG 시스템으로 전환.

#### Phase 1: 온톨로지 계층 구축
- **SNOMED parent_code 계층 완성**: 4개 엔티티 타입 전체에 IS_A 계층 구축
  - Pathology: 178개 (166개 parent_code, 12 root concepts)
  - Outcome: 187개 (176개 parent_code, 11 root concepts)
  - Anatomy: 62개 (61개 parent_code, 1 root "Spine")
- **taxonomy_manager.py 다중 엔티티 지원**: 8개 generic methods 추가 (`get_parents`, `get_children`, `find_common_ancestor_for`, `add_to_taxonomy`, `get_entity_level`, `get_similar_entities`, `get_taxonomy_tree`, `validate_entity_taxonomy`)
- **schema.py**: `get_init_entity_taxonomy_cypher()` — 403개 IS_A Cypher 자동 생성
- **scripts/build_ontology.py** (신규): 기존 Neo4j에 IS_A 일괄 적용 (`--dry-run`, `--force`, `--entity-type`)

#### Phase 2: Import 파이프라인 재설계
- **relationship_builder.py**: Paper 임포트 시 Pathology/Outcome/Anatomy IS_A 자동 생성, review paper TREATS 필터링, AFFECTS "not_reported" 처리
- **unified_pdf_processor.py**: p_value/effect_size/CI 추출 필수화, 온톨로지 계층 기반 Outcome 카테고리 표준화
- **entity_normalizer.py**: NormalizationResult에 `parent_code`, `semantic_type` 추가, 계층 기반 fallback 정규화

#### Phase 3: 검색 파이프라인 재설계
- **graph_context_expander.py**: 4개 엔티티 타입 IS_A 확장 지원 (`expand_by_ontology`, `expand_pathology_up/down`, `expand_outcome_up/down`, `expand_anatomy_up/down`)
- **graph_traversal_search.py** (신규): 다중 홉 그래프 순회 (`traverse_evidence_chain`, `compare_interventions`, `find_best_evidence`)
- **search_dao.py**: SNOMED 코드 기반 IS_A 확장 검색 (`snomed_codes` 파라미터)
- **hybrid_ranker.py**: 3-way 랭킹 (0.4 semantic + 0.3 authority + 0.3 graph_relevance), `_calculate_graph_relevance()` 추가
- **query_parser.py**: SNOMED 활성화, 엔티티에 `snomed_id` 자동 부여

#### Phase 4-5: QC/Validation + 온톨로지 진화
- **DATA_VALIDATION.md**: Phase 6 "Ontology Integrity" 추가 (9개 검증 항목 + Cypher)
- **QC_CHECKLIST.md**: Phase 6 "Ontology Consistency" 추가 (6개 코드 레벨 검증)
- **scripts/repair_ontology.py** (신규): 온톨로지 무결성 수복 (`--dry-run`, `--force`, `--entity-type`)
- **snomed_proposer.py** (신규): LLM 기반 미등록 용어 SNOMED 매핑 제안 (confidence ≥0.9 자동, 0.7-0.9 승인, <0.7 수동)
- **entity_normalizer.py**: 미등록 용어 자동 감지 (`_unregistered_terms`, thread-safe)

#### Bug Fixes (구현 검증 후 수정)
- **C-1**: Pathology 중복 SNOMED 코드 해소 — `76107001` (Lumbar Disc Herniation → `73589001`), `58611004` (Pseudarthrosis → `900000000000296`)
- **C-2**: Osteotomy 하위 항목 parent_code 수정 — PCO/Asymmetric PSO/Posterior Column Osteotomy: `900000000000152`(En Bloc Resection) → `179097009`(Osteotomy)
- **C-3**: 미정의 parent_code 수정 — PEID/PETD: `387713003` → `386638009`(Endoscopic Surgery), MID: `50951008` → `5765005`(Decompression Surgery)
- **M-1**: Extension code range `taxonomy_root: (640, 699)` 추가
- **M-2**: `get_init_entity_taxonomy_cypher()` 미해결 parent_code 경고 로그 추가
- **M-3**: `schema_manager.py` entity taxonomy 루프 내 개별 try/except 적용
- **M-4**: Deprecated `exists(r.level)` → `r.level IS NULL` 수정
- **entity_type 화이트리스트**: `_auto_create_is_a_relation()` 입력 검증 추가
- **source_paper 키 일관성**: `_record_unregistered_term()` 단수/복수 키 통일
- **compare_interventions()**: pathology 파라미터 Cypher 쿼리에 반영
- **find_best_evidence()**: outcome_details 반환값에 포함

#### 신규 파일
| 파일 | 용도 |
|------|------|
| `scripts/build_ontology.py` | IS_A 계층 일괄 구축 |
| `scripts/repair_ontology.py` | 온톨로지 무결성 수복 |
| `src/solver/graph_traversal_search.py` | 다중 홉 그래프 순회 검색 |
| `src/ontology/snomed_proposer.py` | LLM 기반 SNOMED 매핑 제안 |
| `docs/ONTOLOGY_REDESIGN_PLAN.md` | 재설계 계획서 |

#### SNOMED 통계 (v1.24.0)
- Mappings: 696개 (I:218, P:214, O:195, A:69) — 이전 621개에서 75개 신규 개념 추가, ~280 alias 확장
- IS_A 관계: 403개 (P:166 + O:176 + A:61)
- Neo4j 적용: SNOMED 코드 매핑 + TREATS 백필 + IS_A 구축 완료

---

### v1.23.4 (2026-02-17): PMC-first 투명성 개선, MCP 타입 검증 해결, SNOMED 121개 확장, HAS_CHUNK 복구

#### QA 전체 스캔 (QC/CA/DV) — 2026-02-17
- **QC-NEW-001/002**: `user_guide.md`, `developer_guide.md` 버전 `1.23.3` → `1.23.4` 동기화
- **QC-NEW-003**: `DEPLOYMENT.md` SNOMED 카운트 `465개` → `586개` 동기화 (2곳)
- **CA-NEW-003**: `pyproject.toml` 상한 버전 추가 — pydantic `<3.0.0`, rapidfuzz `<4.0.0`, python-dotenv `<2.0.0`
- **DV-NEW-001**: `schema.py` Anatomy `snomed_code` 인덱스 추가 (Pathology/Intervention/Outcome과 대칭)
- **DV-NEW-002**: `TERMINOLOGY_ONTOLOGY.md` 섹션 7.1 헤더 `v1.23.3` → `v1.23.4`
- **CA Deferred 등록**: D-012 (medical_kag_server.py 추가 분리), D-013 (embedding_cache pickle→numpy)

#### Bug Fixes
- **MCP 타입 검증 오류 해결**: Claude Desktop이 integer/boolean/array를 string으로 전송하는 문제를 `_coerce_argument_types()`로 자동 변환 (`validate_input=False` + 타입 변환 레이어)
- **analyze_text `dataclass` NameError 수정**: `from dataclasses import dataclass, field`를 module-level로 이동
- **DV-006 해소**: HAS_CHUNK 누락 Paper 6건 복구 (`repair_missing_chunks.py` 실행)

#### Improvements
- **PMC-first 응답 투명성 개선**: `processing_method`가 실제 처리 소스를 반영 (`pmc_fulltext`, `unpaywall_fulltext`, `vision_api`)
- **`pmc_first` 섹션 추가**: PDF 등록 응답에 PMC/Unpaywall 전문 시도 결과를 상세 보고 (doi_found, pmid_found, pmc_tried, pmc_available, failure_reason 등)
- **SNOMED 매핑 121개 추가** (465 → 586): orphan alias target 전수 커버리지 확보 (I:+22, P:+33, O:+54, A:+12)
- **LLM 동시 호출 설정**: `LLM_MAX_CONCURRENT` 환경변수 추가 (1-20, 기본 5)

---

### v1.23.3 (2026-02-17): PubMed 검색 버그 수정, store_paper JSON 저장, 로그 영속화

#### 버그 수정
- `pubmed_handler.py` search_pubmed() 들여쓰기 오류 수정 — 검색 로직이 `if not self.pubmed_client:` 블록 내부에 잘못 들여쓰기되어 null 반환하던 버그

#### 기능 추가
- `store_paper` 경로(Claude Desktop/Code 분석 후 저장)에서도 `data/extracted/{년도}_{저자}_{제목}.json` 자동 저장 추가
- Docker `logs/` 바인드 마운트 추가 — 컨테이너 재시작 시에도 로그 영구 보존 (`./logs:/app/logs`)

---

### v1.23.2 (2026-02-17): QC/CA/DV 스캔 이슈 수정 + SNOMED 19개 추가 (465개), DV-007 해소

#### QC/CA 수정
- QC-NEW-001: SNOMED 매핑 수 문서 동기화 (I:171, P:127, O:118, A:49 = 465)
- CA-NEW-001: `starlette`/`uvicorn`/`fastapi` 상한 버전 `<1.0.0` 추가

#### DV 수정
- DV-NEW-002: Nonunion/Pseudarthrosis 동의어 Known Accepted (DV-A-005 등록)
- DV-NEW-003: MED 카테고리 Endoscopic → Microscopic Surgery 수정
- DV-NEW-004: Injection/Pain Management → Injection Therapy 명칭 통일 (13개 항목)
- DV-NEW-005: Revision Surgery + 3개 하위시술 taxonomy 추가
- DV-007: Neo4j 전용 SNOMED 19개 신규 코드 소스 추가 (521 별칭 Known Accepted)

#### SNOMED 매핑 확장 (446 → 465개, +19)
- Intervention +3: Injection Therapy, Vertebral Biopsy, Zoledronate
- Pathology +3: Atlantoaxial Dislocation, Osteoporosis, Psoas Abscess
- Outcome +10: Aggrecan, CSF Leakage, Deep Vein Thrombosis, Extension of Fixation, Motor Deficit, Recovery Time, SRS-Satisfaction, Sensory Deficit, Surgical Time, Symptomatic Hematoma
- Anatomy +3: Cervicosacral Spine, C2-C7, Multi-level Vertebral

---

### v1.23.1 (2026-02-17): QC/CA/DV 전체 스캔 이슈 13건 일괄 수정

#### QC 수정 (1건)
- QC-NEW-001: `CLAUDE.md` Key Modules 테이블에서 `snomed_enricher.py`를 graph/ 모듈 그룹으로 이동

#### CA 수정 (8건 수정, 1건 D-011 등록)
- CA-NEW-001: MCP 핸들러 3개에 `MAX_QUERY_LENGTH=10000` 입력 검증 추가
- CA-NEW-002: `unified_pipeline.py`, `pdf_handler.py`에 `ProcessingError`/`ExtractionError` 명시적 catch 추가
- CA-NEW-003: `logger.error()` 9곳에 `exc_info=True` 추가 (스택 트레이스 보존)
- CA-NEW-004: `hybrid_ranker.py` N+1 쿼리 → UNWIND 배치 쿼리로 리팩토링
- CA-NEW-006: `relationship_builder.py` 순환 의존성에 의도 설명 주석 추가
- CA-NEW-007: → D-011 등록 (테스트 커버리지 확장 Phase 2, 39 모듈)
- CA-NEW-008: 미사용 의존성 4개 `[optional-dependencies.legacy]`로 이동
- CA-NEW-009: 5개 패키지에 상한 버전 바운드 추가 (httpx, numpy, aiosqlite, structlog, nest-asyncio)

#### DV 수정 (3건)
- DV-NEW-001: Pathology SNOMED 코드 중복 해소 (Discogenic low back pain → 900000000000262)
- DV-NEW-002: Outcome 확장코드 2개 300번대로 이동 (ASD Reoperation Rate → 374, PJK → 375)
- DV-NEW-003: "Spine Surgery" 루트 노드 taxonomy 초기화에 추가 + entity_normalizer 카테고리 매핑 수정

#### 문서
- 13개 파일 버전 1.23.0 → 1.23.1 동기화

---

### v1.23.0 (2026-02-16): Cleanup Sprint Phase 2 — Monolith 분해, 테스트 250개 추가, 스크립트

#### D-009: pubmed_bulk_processor.py 분해 (462줄 → 3 모듈)
- `pubmed_downloader.py` (~250줄): PubMedDownloader — 검색, 배치 fetch, 인용 조회, 중복 감지
- `pubmed_processor.py` (~580줄): PubMedPaperProcessor — LLM 처리, 청크 생성, Neo4j 저장
- `pubmed_bulk_processor.py` (~340줄): Thin facade, 기존 공개 API 100% 호환
- 46개 신규 테스트 (downloader 19, processor 27)

#### D-010: 테스트 커버리지 확장 (+250 tests, 2342 → 2592)
- `test_tiered_search_extended.py` (~490줄): 검색 계층, 필터, 퓨전, RRF, fallback
- `test_hybrid_ranker_extended.py` (~430줄): 스코어링, 경계값, 통계, 상수
- `test_conflict_detector_extended.py` (~380줄): 심각도, 레거시 API, 요약 생성
- `test_pdf_processor_extended.py` (~530줄): JSON 복구, 데이터 변환, fallback

#### QC-A-003: test_pubmed_enricher 테스트 수정
- 약한 assertion (None/dict/dataclass 허용) → 정확한 BibliographicMetadata 검증으로 강화

#### DV-006: HAS_CHUNK 복구 스크립트
- `scripts/repair_missing_chunks.py` 신규: --dry-run, --paper-ids, --max-concurrent 지원
- extracted JSON 우선 로드, abstract fallback, OpenAI 임베딩

---

### v1.22.1 (2026-02-16): Cleanup Sprint — 죽은 코드 제거, 문서 동기화, 데이터 방지, 코드 품질 개선

QC/CA/DV 스캔에서 발견된 모든 Open Issues를 4-Agent 병렬 실행으로 일괄 해결.

#### Agent 1: Dead Code Purge (QC-004, QC-005)
- 죽은 파일 6개 삭제: `server.py`, `raptor.py`, `test_raptor.py`, `chain_builder.py`, `response_synthesizer.py`, `test_response_synthesizer.py`
- ChromaDB 잔재 정리: 8개 소스 + 3개 테스트 파일에서 `vector_db` 파라미터 및 chroma 참조 완전 제거
- `pubmed_bulk_processor.py`: print→logger 3곳 전환

#### Agent 2: Doc Sync (QC-001, QC-002, QC-003)
- 8개 문서 버전 1.22.x로 동기화 (DEPLOYMENT, NEO4J_SETUP, user_guide, MCP_USAGE_GUIDE, developer_guide, SYSTEM_VALIDATION, TERMINOLOGY_ONTOLOGY, .env.example)
- DEPLOYMENT.md: SNOMED 수치 414→447, entity_normalizer 경로 수정
- CLAUDE.md: Dependencies 5개 pyproject.toml과 동기화, schema.py 경로 수정

#### Agent 3: Data Prevention (DV-001, DV-002)
- `_normalize_secondary_entity()` 추가: 8개 secondary entity 타입에 trim+capitalize 정규화 적용
  (RiskFactor, Complication, RadioParameter, PredictionModel, PatientCohort, FollowUp, Cost, QualityMetric)
- `snomed_enricher.py`: Anatomy MERGE 시 compound/range split 후 title-case 정규화
- 15개 방어적 테스트 추가 (`test_secondary_normalization.py`)

#### Agent 4: Code Quality (CA 관련)
- print→logger 6곳 전환 (cypher_generator 3, pubmed_enricher 3)
- TODO 해결: reasoner.py conflict_detector 연결 주석
- relationship_builder.py stubs 정리: fallback import 제거, 직접 정의로 전환
- pubmed_handler.py: `ALLOWED_UPDATE_FIELDS` 허용목록 추가
- pyproject.toml: aiohttp 상한 `<4.0.0` 추가

#### DB 직접 수정
- DV-003: 고아 테스트 청크 10개 삭제
- DV-004: Anatomy 대소문자 중복 7쌍 병합
- DV-005: "Discogenic low back pain" SNOMED 코드 수정

---

### v1.22.0 (2026-02-16): CA Deferred Plan 실행 — Neo4jClient 분리, 예외 전환, 테스트 확장

CA Deferred Items D-005~D-008 전체 실행. 아키텍처 개선 + 테스트 커버리지 대폭 확장.

#### D-005: Neo4jClient God Object 분리 (Composition + Delegation)
- `RelationshipDAO` 추출 (17 methods → `src/graph/relationship_dao.py`)
- `SearchDAO` 추출 (7 methods → `src/graph/search_dao.py`)
- `SchemaManager` 추출 (4 methods → `src/graph/schema_manager.py`)
- Neo4jClient에 backward-compatible delegation 유지

#### D-006: TieredTextChunker 계층 위반 해소
- `core/text_chunker.py` → `builder/tiered_text_chunker.py`로 이동
- core→builder 의존성 제거 (lazy import → top-level import)

#### D-007: 테스트 커버리지 확장 (1830 → 2360, +530 tests)
- **Phase 1 (Easy)**: schema, relationships, text_chunker, error_handler, enums, bounded_cache
- **Phase 2 (Medium)**: writing_guide, metadata_extractor, entity_extractor, snomed_api_client, stats_parser, graph_search, section_chunker, citation_context
- **Phase 3 (Hard)**: pdf_processor, citation_processor, multi_hop_reasoning, pubmed_handler, pdf_handler, graph_handler

#### D-008: ValueError/RuntimeError → 커스텀 예외 전환
- 36개 `raise ValueError/RuntimeError` → `ValidationError`, `ProcessingError`, `LLMError`, `Neo4jError`
- 5개 `except ValueError` 사이트 업데이트
- 전체 모듈: graph/, builder/, solver/, ontology/, core/, medical_mcp/

---

### v1.21.2 (2026-02-16): SNOMED 커버리지 확장 — 고빈도 미매핑 별칭 추가

Neo4j 고빈도 미매핑 엔티티에 대한 선별적 별칭 추가 및 SNOMED 매핑 확장.

#### Normalizer 별칭 추가 (`entity_normalizer.py`)

| 카테고리 | 확장된 Canonical | 추가 Alias 수 | 주요 추가 항목 |
|----------|------------------|---------------|----------------|
| Intervention | 9개 | ~15 | Bone Graft, Robot-Assisted Surgery, PELD(PTED), BMP(rhBMP-2), Cage Insertion |
| Pathology | 11개 | ~25 | DDD(Lumbar Degeneration), Sagittal Imbalance(Spinopelvic malalignment), Pseudarthrosis(Failed fusion) 등 |
| Outcome | 14개 확장 + 3개 신규 | ~35 | SF-36(PCS/MCS), Fusion Rate(시점별), Screw Accuracy(Navigation/AR), ROM(신규), PROMs(신규) |

#### SNOMED 매핑 추가 (`spine_snomed_mappings.py`)

| Entity | SNOMED Code | 유형 |
|--------|-------------|------|
| Pseudarthrosis (pathology) | 58611004 | Official |
| Low Back Pain | 279039007 | Official |
| Spinal Cord Compression | 52423008 | Official |
| Bone Graft | 88834003 | Official |
| Heterotopic Ossification | 16096001 | Official |
| Central Canal Stenosis | 900000000000261 | Extension |
| Mortality | 900000000000371 | Extension |
| Functional Recovery | 900000000000372 | Extension |
| PROMs | 900000000000373 | Extension |

#### Neo4j SNOMED 커버리지 변화

| 카테고리 | v1.21.1 | v1.21.2 | 변화 |
|----------|---------|---------|------|
| Intervention | 188/466 (40.3%) | **190/466 (40.8%)** | +2 |
| Pathology | 109/294 (37.1%) | **115/294 (39.1%)** | +6 |
| Outcome | 366/1874 (19.5%) | **385/1874 (20.5%)** | +19 |
| Anatomy | 163/183 (89.1%) | 163/183 (89.1%) | — |
| **합계** | **826** | **853** | **+27** |

#### SNOMED 매핑 소스 통계 (spine_snomed_mappings.py)

| 카테고리 | 전체 | 공식 | 확장 |
|----------|------|------|------|
| Intervention | 168 | 49 | 119 |
| Pathology | 125 | 65 | 60 |
| Outcome | 108 | 26 | 82 |
| Anatomy | 46 | 24 | 22 |
| **Total** | **447** | **164** | **283** |

#### 기타
- `tests/test_auto_normalizer.py`: 정적 별칭 충돌 수정 (Operative Duration → Time in Operating Theatre)

---

### v1.21.1 (2026-02-16): Code Audit 전체 수정 완료 + 의존성 정리

CA v1.21.0 잔여 MEDIUM/LOW 항목 6건 수정.

| # | 항목 | 변경 | 파일 |
|---|------|------|------|
| 1 | **M-4: optional deps 분리** | networkx, sentence-transformers, torch → `[ml]` 그룹 이동 (설치 ~2GB 절감) | `pyproject.toml` |
| 2 | **M-5: pubmed_handler 헬퍼 추출** | 7중 Neo4jClient 재생성 → `_get_fresh_neo4j_client()` 헬퍼 | `pubmed_handler.py` |
| 3 | **M-6: MCP 핸들러 서버측 로깅** | 4곳 except 블록에 `logger.error(exc_info=True)` 추가 | 4개 파일 |
| 4 | **L-1: stdlib lazy import 정리** | 40건 함수 내 import → 모듈 top-level 이동 | 12개 파일 |
| 5 | **L-2: nest_asyncio 모듈화** | 반복 호출 → tiered_search.py 모듈 레벨 1회 적용 | `tiered_search.py` |
| 6 | **L-3: 의존성 상한 추가** | google-genai `<2.0.0`, langchain-anthropic `<1.0.0`, langchain-google-genai `<3.0.0` | `pyproject.toml` |

---

### v1.21.0 (2026-02-16): Data Validation 후속 조치 — SNOMED 정리 + Summary 백필 + 계층 구조 개선

DV v1.20.1 결과 발견된 다수 이슈의 전체 후속 조치 실행.

#### Neo4j 데이터 정리

| # | 변경 | 영향 |
|---|------|------|
| 1 | **테스트 Chunk 고아 삭제**: HAS_CHUNK 없는 10개 Chunk (test, study, paper 등) 삭제 | Chunk 무결성 ✅ |
| 2 | **IS_A 루트 단일화**: "Spine Surgery" 노드 생성 → 22개 카테고리 루트 연결 | 단일 루트 계층 |
| 3 | **TREATS paper_count 재계산**: 전체 2,245개 관계 paper_count 재산출 | 0 mismatches |
| 4 | **51개 Paper INVOLVES 복구**: 제목/abstract 키워드 매칭으로 54개 INVOLVES 관계 생성 | 48개 Paper 연결 복원 |

#### SNOMED 중복 해결

| 카테고리 | 이전 | 이후 | 방법 |
|----------|------|------|------|
| Intervention | 29 중복 코드 | **0** | IS_A 자식 코드 제거(8), 동의어 엔티티 병합(8), 대규모 그룹 코드 정리(54) |
| Pathology | 3 중복 코드 | **0** | ASD/Adjacent level disease 병합, Lumbar/Segmental instability 병합, PJF 코드 오류 수정 |
| Anatomy | 23 중복 코드 | **0** | 복합 레벨 문자열(103개)에서 코드 제거, 정규 엔티티만 유지 |
| Outcome | 25 중복 코드 | 25 (의도적) | 시점/측정 변형은 동일 코드 유지 (설계 의도) |

#### SNOMED 매핑 확장

| # | 변경 | 파일 |
|---|------|------|
| 5 | **procedure_ext 범위 추가** (600-699): Fixation 변형 16개, Osteotomy 변형 3개, C1/2 융합 등 22개 신규 매핑 | `spine_snomed_mappings.py` |
| 6 | **PJK/PJF 분리**: PJF에 독립 extension code(900000000000234) 부여 | `spine_snomed_mappings.py` |
| 7 | **Fusion Surgery 코드 변경**: 122465003 → 174765004 (Spine Surgery 루트와 구분) | `spine_snomed_mappings.py` |

#### Normalizer 커버리지 확대

| 카테고리 | Canonical 이전→이후 | Alias 이전→이후 |
|----------|---------------------|-----------------|
| Anatomy | 38 → 51 (+13) | — → +vague term 처리 |
| Pathology | 62 → 122 (+60) | 295 → 532 (+237) |
| Intervention | 120 → 146 (+26) | 570 → 680 (+110) |
| Outcome | 80 → 133 (+53) | 430 → 659 (+229) |

#### Anatomy 추출 버그 수정 (3건)

| # | 변경 | 파일 |
|---|------|------|
| 8 | `anatomy_region` 폴백: anatomy_level 비어있을 때 anatomy_region 사용 | `pubmed_bulk_processor.py` |
| 9 | `anatomy_levels` → `anatomy_level` 키 수정 | `medical_kag_server.py` |
| 10 | `anatomy_levels` None 처리 수정 | `handlers/pdf_handler.py` |

#### Summary 기능 추가

| # | 변경 | 파일 |
|---|------|------|
| 11 | LLM 추출 JSON 스키마에 `summary` 필드 추가 | `unified_pdf_processor.py` |
| 12 | SpineMetadata, SpineMetadataCompat에 summary 필드 추가 | 3개 파일 |
| 13 | **소급 적용 스크립트**: Claude Haiku로 418개 Paper summary 생성 | `scripts/backfill_summary.py` (신규) |

#### Code Audit (CA) 수정

| # | 항목 | 변경 | 파일 |
|---|------|------|------|
| 14 | **C-1: 의존성 버전 제약 불일치 수정** | neo4j `<6.0.0`→`<7.0.0`, openai `<2.0.0`→`<3.0.0` | `pyproject.toml` |
| 15 | **C-2: OpenAI 클라이언트 lazy-init** | 매 호출 재생성 → 클래스 레벨 lazy 초기화 (3곳) | `tiered_search.py`, `neo4j_client.py` |
| 16 | **C-3: 중복 임베딩 메서드 정리** | `_generate_abstract_embedding` 4중 복사 → lazy-init 통일 | `pubmed_bulk_processor.py`, `important_citation_processor.py` |
| 17 | **H-1: Server 중복 메서드 제거** | pdf_handler와 중복 5개 메서드 삭제 (~178줄), 호출 리다이렉트 | `medical_kag_server.py`, `pdf_handler.py` |
| 18 | **H-2: logger.error exc_info 누락 수정** | 21곳 `exc_info=True` 추가 | 9개 파일 |
| 19 | **H-3: Config repr 마스킹** | API 키/패스워드 `field(repr=False)` 적용 | `claude_client.py`, `gemini_client.py`, `neo4j_client.py` |
| 20 | **H-4: test_expanded_taxonomy 수정** | `return failed == 0` → `assert` 전환 (4곳) | `test_expanded_taxonomy.py` |
| 21 | **M-2: MCP 입력 상한 추가** | `top_k ≤100`, `query ≤10000` | `search_handler.py` |

---

### v1.20.1 (2026-02-16): Auto Normalizer Expansion — 3-Layer 방어 체계

엔티티 정규화 실패 시 무한 노드 생성 문제를 해결하는 3단계 방어 체계 구현.

#### Layer 1: 추출 프롬프트 제어 어휘

| # | 변경 | 파일 |
|---|------|------|
| 1 | **`_build_vocabulary_hints()`**: EntityNormalizer ALIASES에서 canonical name 목록 자동 생성 → EXTRACTION_PROMPT에 결합 | `src/builder/unified_pdf_processor.py` |

#### Layer 2: LLM 폴백 + 동적 Alias

| # | 변경 | 파일 |
|---|------|------|
| 2 | **`register_dynamic_alias()`**: 런타임 alias 등록 (thread-safe, 메모리 전용, canonical 검증) | `src/graph/entity_normalizer.py` |
| 3 | **`_get_candidate_canonicals()`**: rapidfuzz WRatio로 상위 30개 후보 필터링 | `src/graph/entity_normalizer.py` |
| 4 | **`classify_unmatched_entity()`**: Claude Haiku로 미매칭 엔티티 → 기존 canonical 분류 (confidence ≥ 0.85) | `src/graph/relationship_builder.py` |
| 5 | **`_normalize_with_fallback()`**: 5단계 정규화 실패 → LLM 폴백 (논문당 10회 제한) | `src/graph/relationship_builder.py` |
| 6 | **4개 create_*_relations 메서드**: normalize 호출을 `_normalize_with_fallback()`으로 교체 | `src/graph/relationship_builder.py` |
| 7 | **llm_client 전달**: RelationshipBuilder에 llm_client 주입 | `src/medical_mcp/medical_kag_server.py` |

#### Layer 3: 배치 정리 스크립트

| # | 변경 | 파일 |
|---|------|------|
| 8 | **`consolidate_entities.py`**: 미매핑 노드 조회 → LLM 배치 분류 → 노드 병합 + alias 코드 제안 (`--dry-run`, `--force`, `--suggest-aliases`) | `scripts/consolidate_entities.py` (신규) |

#### 테스트

| # | 변경 | 파일 |
|---|------|------|
| 9 | **24개 테스트**: Layer 1~2 전체 커버 (vocabulary hints, dynamic alias, candidate filtering, LLM classify, normalize fallback) | `tests/test_auto_normalizer.py` (신규) |

- 전체 테스트 1,447개 통과 (14 skipped, 0 failures)

---

### v1.20.0 (2026-02-16): CA 수정 + 죽은 코드 정리 + MCP 기능 노출 + MCP 프로토콜 업그레이드

4개 병렬 트랙으로 실행. CA 지적 사항 수정, 레거시 죽은 코드 제거, 미노출 기능 MCP 연결, MCP 프로토콜 최신화.

#### Track A: Code Health (CA 수정)

| # | 변경 | 파일 |
|---|------|------|
| 1 | **BoundedCache 구현**: OrderedDict 기반 LRU 캐시 (maxsize 설정 가능) | `src/core/bounded_cache.py` (신규) |
| 2 | **graph_context_expander 캐시 교체**: 무제한 dict → `BoundedCache(maxsize=500)` | `src/solver/graph_context_expander.py` |
| 3 | **relationship_reasoner 캐시 교체**: 3개 무제한 dict → BoundedCache (pagerank:200, centrality:200, embedding:1000) | `src/knowledge/relationship_reasoner.py` |
| 4 | **SNOMED N+1 배치 처리**: 개별 UPDATE 루프 → UNWIND 배치 쿼리 (1회 실행) | `src/graph/snomed_enricher.py` |
| 5 | **spacy optional dependency**: `[project.optional-dependencies]`에 `nlp = ["spacy>=3.0.0"]` 추가 | `pyproject.toml` |

#### Track B: Dead Code Cleanup

| # | 변경 | 파일 |
|---|------|------|
| 6 | **TieredVectorDB 참조 제거**: ChromaDB 제거 후 잔존 import/stub 5개 파일 정리 | `agentic_rag.py`, `unified_pipeline.py`, `hybrid_ranker.py`, `response_synthesizer.py`, `orchestrator/README.md` |
| 7 | **add_pdf_v7 alias 삭제**: enum, dispatch, 메서드, 문서에서 완전 제거 | `medical_kag_server.py`, `pdf_handler.py`, `MCP_USAGE_GUIDE.md` |
| 8 | **use_v7 파라미터 삭제**: analyze Tool schema + handler에서 제거 | `medical_kag_server.py`, `pdf_handler.py` |
| 9 | **knowledge/ 레거시 archive**: paper_graph, citation_extractor, relationship_reasoner → `archive/legacy_knowledge/` 이동 | `src/knowledge/` |

#### Track C: MCP Feature Wiring (5개 액션 신규/연결)

| # | 변경 | 파일 |
|---|------|------|
| 10 | **document.stats 등록**: 기존 `get_stats()` MCP Tool schema에 노출 | `medical_kag_server.py` |
| 11 | **graph.multi_hop 재연결**: deprecated stub → `MultiHopReasoner` (Neo4j 기반) | `reasoning_handler.py` |
| 12 | **search.clinical_recommend 신규**: `ClinicalReasoningEngine` + `PatientContextParser` MCP 노출 | `medical_kag_server.py`, `reasoning_handler.py` |
| 13 | **document.summarize 신규**: `SummaryGenerator` MCP 노출 | `medical_kag_server.py`, `document_handler.py` |
| 14 | **graph.infer_relations 신규**: `InferenceEngine` MCP 노출 | `medical_kag_server.py`, `graph_handler.py` |

#### Track D: MCP Protocol Upgrade

| # | 변경 | 파일 |
|---|------|------|
| 15 | **Streamable HTTP Transport**: SSE 외에 `--transport streamable-http` 옵션 추가 (MCP 2025-03-26 스펙) | `sse_server.py` |
| 16 | **Tool Annotations**: 10개 Tool에 readOnly/destructive/idempotent/openWorld 메타데이터 추가 | `medical_kag_server.py` |
| 17 | **MCP Resources**: `@server.list_resources()` / `@server.read_resource()` — 논문 목록/메타데이터 자동 노출 | `medical_kag_server.py` |
| 18 | **MCP Prompts**: 3개 프롬프트 템플릿 (compare_interventions, evidence_summary, paper_review) | `medical_kag_server.py` |
| 19 | **MCP SDK 버전**: `mcp>=1.0.0` → `mcp>=1.8.0` (Streamable HTTP 최소 요구) | `pyproject.toml` |

#### Track E: Integration

- 전체 테스트 1,423개 통과 (14 skipped, 0 failures)
- 버전 동기화 (5개 파일)
- 문서 업데이트

---

### v1.19.4 (2026-02-16): rest_api.py 속성명 오류 수정 + 핸들러 라우팅 정리 + 고립 논문 85건 복구

#### rest_api.py 수정

| # | 변경 | 파일 |
|---|------|------|
| 1 | **속성명 수정**: `kag_server.llm_enabled` → `getattr(kag_server, "enable_llm", False)` (런타임 AttributeError 방지) | `rest_api.py` |
| 2 | **핸들러 직접 라우팅**: 삭제된 서버 메서드 8개 참조를 핸들러 호출로 수정 (list_documents, get_stats, find_conflicts 등) | `rest_api.py` |
| 3 | **미사용 엔드포인트 제거**: `get_topic_clusters` REST 엔드포인트 삭제 | `rest_api.py` |

#### 고립 논문 85건 복구 (DV Fix)

PubMed 임포트 시 LLM 추출이 실행되지 않아 엔티티 관계(STUDIES/INVESTIGATES/INVOLVES)가 누락된 논문 85건을 복구.

| # | 변경 | 상세 |
|---|------|------|
| 4 | **복구 스크립트 신규**: Claude Haiku로 abstract 재분석 → SpineMetadata 추출 → RelationshipBuilder 관계 구축 (병렬 5 concurrent) | `scripts/repair_isolated_papers.py` |
| 5 | **85개 논문 관계 구축**: 3,057개 관계 생성 (STUDIES, INVESTIGATES, INVOLVES, TREATS, AFFECTS, CAUSES 등) | Neo4j DB |
| 6 | **비척추 논문 1건 삭제**: pubmed_41310210 (Steel Surface Defect Detection) — 오임포트 | Neo4j DB |
| 7 | **삭제 논문 1건 재임포트**: pubmed_40526022 (C2 Pelvic Angle) — 이전 세션 실수로 삭제 | Neo4j DB |
| 8 | **TREATS 백필**: 복구 후 TREATS 1,516건 (repair 중 자동 생성 포함) | Neo4j DB |

#### DV 결과 (복구 전 → 후)

| Check | Before | After |
|-------|--------|-------|
| 고립 Papers (2.1) | 85 | **0 PASS** |
| 고아 노드 (1.2) | 43 | **0 PASS** |
| IS_A 순환 (2.2) | 5 | **0 PASS** |
| Papers 총 수 | 419 | **418** (-1 비척추 삭제) |
| Nodes 총 수 | ~10,200 | **~10,700** |
| Relationships 총 수 | ~19,700 | **~22,800** |

---

### v1.19.3 (2026-02-16): Code Audit 미수정 4건 완료 — God Object 분해, BaseHandler 추출, 테스트 확대, 로깅 전환

Code Audit(CA) 미수정 4건(D-001~D-004)을 일괄 해소. MedicalKAGServer를 7,178줄에서 3,982줄로 축소 (-45%), BaseHandler 공통 패턴 추출, 테스트 228개 추가, print→logger 전환.

#### D-001: MedicalKAGServer God Object 분해 (7,178줄 → 3,982줄, -45%)

| # | 변경 | 파일 |
|---|------|------|
| 1 | **Tool Registry 패턴**: 420줄 if/elif 체인을 10개 dispatcher 함수 + 딕셔너리 디스패치로 교체 | `medical_kag_server.py` |
| 2 | **중복 메서드 ~50개 삭제**: 핸들러에 위임 완료된 메서드 제거 (get_patient_cohorts, store_analyzed_paper, reason, graph_search, DOI methods 등) | `medical_kag_server.py` |
| 3 | **DOI 메서드 핸들러 이관**: fetch_by_doi, get_doi_metadata, import_by_doi → PubMedHandler | `handlers/pubmed_handler.py` |
| 4 | **rest_api.py 핸들러 라우팅**: 제거된 서버 메서드 참조를 핸들러 직접 호출로 수정 | `rest_api.py` |

#### D-002: BaseHandler 추출 (11개 핸들러 공통 패턴)

| # | 변경 | 파일 |
|---|------|------|
| 4 | **BaseHandler 클래스 신규**: neo4j_client property, _require_neo4j(), _ensure_connected(), _format_error(), _format_success() | `handlers/base_handler.py` (신규) |
| 5 | **safe_execute 데코레이터**: try/except + 표준 에러 응답 통합 (~45개 try/except 패턴 통일) | `handlers/base_handler.py` |
| 6 | **11개 핸들러 BaseHandler 상속**: search, document, graph, reasoning, clinical_data, pubmed, pdf, json, citation, reference, writing_guide | `handlers/*.py` (11개) |

#### D-003: 테스트 커버리지 확대 (+228개 테스트)

| # | 변경 | 파일 |
|---|------|------|
| 7 | **reference_formatter 테스트**: 7개 스타일 포맷팅 + edge case 57개 | `tests/builder/test_reference_formatter.py` (신규) |
| 8 | **spine_snomed_mappings 테스트**: 데이터 무결성 + SNOMED 코드 형식 44개 | `tests/ontology/test_spine_snomed_mappings.py` (신규) |
| 9 | **core_nodes 테스트**: 생성/직렬화/검증 31개 | `tests/graph/test_core_nodes.py` (신규) |
| 10 | **extended_nodes 테스트**: 생성/직렬화/검증 39개 | `tests/graph/test_extended_nodes.py` (신규) |
| 11 | **clinical_reasoning_engine 테스트**: 추론 로직 + edge case 57개 | `tests/solver/test_clinical_reasoning_engine.py` (신규) |

#### D-004: print(stderr) → logger 전환

| # | 변경 | 파일 |
|---|------|------|
| 12 | **모듈 레벨 print 22건 → logger**: import fallback 시 print(stderr) → logger.warning/info 전환 | `medical_kag_server.py` |

#### 추가 수정 (코드 검증)

| # | 변경 | 파일 |
|---|------|------|
| 13 | **rest_api.py 속성명 수정**: `kag_server.llm_enabled` → `getattr(kag_server, "enable_llm", False)` (AttributeError 방지) | `rest_api.py` |
| 14 | **rest_api.py 핸들러 라우팅**: 삭제된 서버 메서드 8개 참조를 핸들러 직접 호출로 수정 + get_topic_clusters 엔드포인트 제거 | `rest_api.py` |

#### 테스트 결과

- **1424 passed**, 14 skipped, 1 pre-existing failure (unrelated)
- BaseHandler 변경에 따른 test_security.py 수정 포함
- rest_api.py 속성명 오류 수정 포함

---

### v1.19.2 (2026-02-16): SNOMED-CT 매핑 대규모 확장 (315 → 414개)

99개 신규 SNOMED 매핑 추가 및 EntityNormalizer SNOMED fallback 로직 개선. Neo4j 엔티티 커버리지 대폭 향상.

#### SNOMED 확장 상세

| 타입 | 이전 | 이후 | 신규 | DB 커버리지 |
|------|------|------|------|-----------|
| Intervention | 123 | 144 | +21 | 42% → 61% |
| Pathology | 85 | 120 | +35 | 51% → 86% |
| Outcome | 70 | 104 | +34 | 27% → 29% |
| Anatomy | 37 | 46 | +9 | 84% → 93% |
| **Total** | **315** | **414** | **+99** | — |

#### 주요 변경

| # | 변경 | 파일 |
|---|------|------|
| 1 | **Intervention 21개 추가**: rhBMP-2, PEID, PETD, PCO, CDA, Robot-assisted, Navigation-guided, 골이식 (자가골/동종골/DBM) 등 | `spine_snomed_mappings.py` |
| 2 | **Pathology 35개 추가**: 공식 SNOMED 8개 (Nonunion, Neurogenic claudication, HO, LBP 등) + 확장 27개 (Cage subsidence, AARF, Cage migration, C5 palsy 등) | `spine_snomed_mappings.py` |
| 3 | **Outcome 34개 추가**: 공식 5개 (Delirium, Radiculopathy, ROM, PE, Sepsis, BMD) + 확장 28개 (Screw Loosening, Rod Fracture, Opioid Consumption, Screw Accuracy 등) | `spine_snomed_mappings.py` |
| 4 | **Anatomy 9개 추가**: T2-3~T9-10 흉추 디스크 레벨 8개 + Multi-level 개념 | `spine_snomed_mappings.py` |
| 5 | **EntityNormalizer SNOMED fallback**: confidence=0 시에도 원본 텍스트로 SNOMED 직접 조회 추가 (synonym/abbreviation 매칭) | `entity_normalizer.py` |

---

### v1.19.1 (2026-02-16): Code Audit 전면 수정 — 보안, 에러 처리, 성능, 설계, 의존성

Code Audit(CA) 6개 Phase 점검 후 20개 항목을 일괄 수정. 보안 취약점 해소, 에러 처리 강화, N+1 쿼리 최적화, LLM Provider 인터페이스 도입, 의존성 선언 정상화.

#### 🔴 CRITICAL 수정

| # | 변경 | 파일 |
|---|------|------|
| 1 | **pyproject.toml 의존성 정상화**: 8개 → 29개 (누락 21개 추가, 미사용 3개 제거, 상한 추가) | `pyproject.toml` |
| 2 | **requirements.txt 동기화**: 누락 6개 추가, 미사용 4개 제거 | `requirements.txt` |
| 3 | **fitz.open() 리소스 누수 수정**: 10곳에 try/finally 추가, list comprehension 내 close() 누락 2곳 수정 | `medical_kag_server.py`, `pdf_handler.py` |
| 4 | **Silent Exception 14건 해소**: `except Exception: pass` 9건 → logger.debug 추가, silent return 5건 → logger.warning 추가 | 7개 파일 |
| 5 | **HTTP 클라이언트 retry 추가**: 4개 클라이언트에 exponential backoff 재시도 (max 3회) | `pubmed_client.py`, `doi_fulltext_fetcher.py`, `pmc_fulltext_fetcher.py`, `snomed_api_client.py` |

#### 🟡 HIGH 수정

| # | 변경 | 파일 |
|---|------|------|
| 6 | **logger.error exc_info=True 60+건 추가**: 7개 디렉토리 43+ 파일의 except 블록 내 스택 트레이스 보존 | src/ 전역 |
| 7 | **BaseLLMClient Protocol 도입**: Provider-agnostic LLM 인터페이스 (generate, generate_json) | `llm/base.py` (신규) |
| 8 | **N+1 → UNWIND 배치 쿼리**: relationship_builder 8개 메서드의 루프 내 DB 호출을 Neo4j UNWIND로 전환 | `relationship_builder.py` |
| 9 | **PMID/DOI 포맷 검증**: MCP 진입점에 regex 검증 추가 (PMID: `^\d{1,8}$`, DOI: `^10\.\d{4,}/.+$`) | `medical_kag_server.py` |

#### 🟢 MEDIUM 수정

| # | 변경 | 파일 |
|---|------|------|
| 10 | **커스텀 예외 활용**: ValueError 12건 → ValidationError, RuntimeError 2건 → ProcessingError, ValueError 2건 → LLMError 전환 | `evidence_synthesizer.py`, `raptor.py`, `claude_client.py`, `gemini_client.py`, `chain_builder.py` |
| 11 | **OpenAI 클라이언트 재사용**: _generate_abstract_embedding 3파일에서 매 호출 생성 → 클래스 레벨 lazy 초기화 | `pubmed_bulk_processor.py`, `important_citation_processor.py`, `medical_kag_server.py` |
| 12 | **Config __repr__ 마스킹**: Neo4jConfig.password='***', LLMConfig.api_key 첫 8자만 노출 | `config.py` |

#### ℹ️ LOW 수정

| # | 변경 | 파일 |
|---|------|------|
| 13 | **Path traversal 방어**: prepare_pdf_prompt()에 resolve() + allowed directory 검사 추가 | `medical_kag_server.py` |
| 14 | **SemanticCache deque 전환**: list.pop(0) O(n) → deque(maxlen=) O(1) | `semantic_cache.py` |
| 15 | **싱글톤 Lock 추가**: entity_normalizer, error_handler에 double-checked locking | `entity_normalizer.py`, `error_handler.py` |
| 16 | **QueryCache docstring 수정**: "Thread-safe" → "Not thread-safe. Single-threaded asyncio only." | `query_cache.py` |
| 17 | **Cypher 인젝션 위험 제거**: 미사용 generate_with_templates() 삭제 | `cypher_generator.py` |
| 18 | **snomed_enricher 파라미터 바인딩**: f-string escaping → $param + UNWIND 변환 | `snomed_enricher.py` |
| 19 | **동어반복 assertion 수정**: `assert x is not None or x is None` → 타입 검증 | `test_pubmed_enricher.py` |
| 20 | **ALLOWED_LABELS 검증**: snomed_enricher에서 label 변수의 화이트리스트 검증 추가 | `snomed_enricher.py` |

#### 미수정 → v1.19.3에서 완료

| 항목 | 상태 | 완료 버전 |
|------|------|----------|
| MedicalKAGServer 분해 (7,178줄 God Object) | **완료** — 3,982줄로 축소 (-44%) | v1.19.3 |
| BaseHandler 추출 (11개 핸들러 공통 패턴) | **완료** — base_handler.py + safe_execute | v1.19.3 |
| 테스트 커버리지 확대 | **완료** — +228개 테스트 (5개 신규 파일) | v1.19.3 |
| print(stderr) → logger 전환 | **완료** — 모듈 레벨 22건 전환 | v1.19.3 |

#### 테스트 결과

- **1424 passed**, 14 skipped, 1 pre-existing failure (unrelated)
- graph/ 테스트 356건 전체 통과
- solver/ 테스트 전체 통과 (ValidationError 전환 포함)
- 신규 228개 테스트 전체 통과

#### Data Validation(DV) — Neo4j 데이터 무결성 정리

DV 체크리스트 신설 및 최초 실행. 10건의 데이터 무결성 이슈 일괄 수정.

| # | 작업 | Before | After |
|---|------|--------|-------|
| 1 | DOI placeholder → NULL ("Not provided", "Unknown" 등) | 22개 | 0 |
| 2 | 중복 DOI Paper 병합 (pubmed_*/analyzed_* 이중 임포트) | 6건 | 0 |
| 3 | 대소문자 중복 엔티티 병합 (P:15, O:11, A:8, I:4) | 39개 | 0 |
| 4 | 고아 Chunk 삭제 (HAS_CHUNK 없음, 테스트 잔여 포함) | 52개 | 0 |
| 5 | 고립 Paper 삭제 (관계 0개, PubMed-only 임포트) | 11개 | 0 |
| 6 | Junk Anatomy 삭제 (추출 오류: "2", "L", "3-level)") | 96개 | 0 |
| 7 | Chunk Tier 정규화 (정수 1/2 → "tier1"/"tier2") | 114개 | 0 |
| 8 | Abstract 임베딩 백필 (OpenAI 3072d) | 105 누락 | 0 (100%) |
| 9 | DOI URL 형식 복구 (https://doi.org/10.xxx → 10.xxx) | 1개 | 복구 |

정리 후 데이터: Paper 437, Chunk 7,184, 총 노드 10,568

#### 신규 문서

| 문서 | 역할 |
|------|------|
| `docs/CODE_AUDIT.md` | Code Audit(CA) 체크리스트 — 보안/성능/설계 심층 분석 (20개 체크, 6 Phase) |
| `docs/DATA_VALIDATION.md` | Data Validation(DV) 체크리스트 — Neo4j 데이터 무결성/완전성 검증 (18개 체크, 5 Phase) |

### v1.18.0 (2026-02-15): Critical 버그 수정 — sanitize_doi, Outcome, PubMed enrichment

`sanitize_doi`가 모든 DOI를 거부하던 Critical 버그 수정, store_paper의 Outcome 노드 생성 실패 수정, PubMed enrichment 누락 보완.

#### 버그 수정

| # | 심각도 | 변경 | 파일 |
|---|--------|------|------|
| 1 | **Critical** | **sanitize_doi가 모든 DOI를 None 반환**: `invalid_patterns`에 빈 문자열 `""` 포함 → Python의 `"" in "any_string"` = True로 모든 DOI 거부됨. `""` 제거로 해결 | `relationship_builder.py` |
| 2 | **High** | **Outcome 노드 미생성**: `formatted_outcomes`가 5개 필드만 보존하여 나머지 데이터 손실. `dict(o)` 전체 복사 + 빈 name 검증으로 수정 | `medical_kag_server.py`, `pdf_handler.py` |
| 3 | **High** | **pico_outcome 오타**: `pdf_handler.py`에서 `pico_outcomes` (존재하지 않는 필드) 참조 → `pico_outcome` (단수형)으로 수정. TypeError 사일런트 캐치 해소 | `pdf_handler.py` |
| 4 | **High** | **store_paper PubMed enrichment 누락**: `analyze_text()`에만 있던 PubMed enrichment를 `store_paper`에도 추가. DOI fallback + PMID→paper_id 업그레이드 포함 | `medical_kag_server.py`, `pdf_handler.py` |
| 5 | **Medium** | **DOI null 방어**: `doi=doi` → `doi=doi or ""` 변경으로 None 전달 방지 | `medical_kag_server.py`, `pdf_handler.py` |

#### 데이터 복구

| # | 변경 |
|---|------|
| 1 | 기존 10개 논문의 NULL DOI를 PubMed API로 복구 (PMID/제목 기반 검색 + 유사도 검증) |

#### 영향 범위

- `sanitize_doi` 버그는 v1.14.23 이후 저장된 **모든 논문**에 영향
- 수정 후 신규 임포트 2건 (pubmed_39384336, pubmed_39202595) 정상 확인

### v1.17.0 (2026-02-15): PMC-first PDF 최적화 + Claude Code 병렬 처리 지원

PDF 처리 파이프라인을 개선하여 Open Access 논문의 처리 비용을 절감하고, Claude Code에서 직접 PDF를 병렬 처리할 수 있는 워크플로우를 구축.

#### 신규 기능

| # | 변경 | 파일 |
|---|------|------|
| 1 | **PMC-first PDF 최적화**: PDF 업로드 시 Vision API 전에 PMC/Unpaywall 전문을 우선 시도. Open Access 논문은 텍스트 처리로 전환하여 비용 ~60-80% 절감 | `medical_kag_server.py` |
| 2 | **DOI/PMID 경량 추출**: PyMuPDF로 첫 2페이지만 읽어 regex로 DOI/PMID 추출 (~100ms, LLM 호출 없음) | `medical_kag_server.py` |
| 3 | **prepare_prompt 전체 스키마**: 간소화 프롬프트를 `EXTRACTION_PROMPT` import로 교체. MCP 서버 내부 처리와 100% 동일한 추출 스키마 | `medical_kag_server.py` |
| 4 | **Claude Code 병렬 PDF 처리 워크플로우**: PDF Read → EXTRACTION_PROMPT로 추출 → store_paper(chunks 포함) → 임베딩 자동 생성 | `medical_kag_server.py` |

#### 버그 수정

| # | 변경 | 파일 |
|---|------|------|
| 1 | **analyze text 액션 수정**: `result.extracted_metadata` → `result.extracted_data` dict 파싱으로 변경 (AttributeError 해결) | `medical_kag_server.py` |
| 2 | **analyze text spine_metadata 수정**: `result.spine_metadata` → `_spine_dict`에서 파싱 | `medical_kag_server.py` |
| 3 | **analyze text chunks 수정**: `result.chunks` → `_extracted.get("chunks")` dict 호환 처리 | `medical_kag_server.py` |
| 4 | **chunk tier 타입 호환**: `"tier1"/"tier2"` 문자열 ↔ `1/2` 정수 자동 변환 (store_paper, analyze_text 양쪽) | `medical_kag_server.py` |
| 5 | **MCP 서버 버전 동기화**: `Server("medical-kag", version=_version)` — `src/__init__.py`에서 동적 참조 | `medical_kag_server.py` |

#### PMC-first 처리 흐름

```
PDF 업로드 → 첫 2페이지 DOI/PMID 추출 (regex)
  → DOI만 있으면 PubMed에서 PMID 확인
  → PMC BioC API 전문 시도 (구조화 텍스트)
  → 실패 시 Unpaywall 시도
  → 전문 있으면 process_text() (저비용 텍스트 처리)
  → 없으면 기존 Vision API fallback
```

#### Claude Code 병렬 처리 워크플로우

```
1. prepare_prompt → EXTRACTION_PROMPT 확인 (unified_pdf_processor와 동일)
2. Claude Code: Task agent 병렬로 PDF Read
3. EXTRACTION_PROMPT 스키마로 JSON 추출
4. store_paper(chunks=[...]) → MCP 서버가 임베딩 생성 + Neo4j 저장
```

### v1.16.4 (2026-02-14): SNOMED 보강 버그픽스 및 커버리지 확장

v1.16.3에서 발견된 Critical/High 이슈 수정 + 누락 커버리지 전면 보완. SNOMED 315개(I:123, P:85, O:70, A:37).

#### 버그 수정

| # | 심각도 | 변경 | 파일 |
|---|--------|------|------|
| 1 | **Critical** | TREATS backfill `run_write_query` → `run_query` (counter dict 대신 records 반환 필요) | `snomed_enricher.py` |
| 2 | **Critical** | `init_neo4j.py`에 `src/` sys.path 추가 (schema.py→snomed_enricher 임포트 경로 해결) | `init_neo4j.py` |
| 3 | **Critical** | `enhance_taxonomy_snomed.py` 임포트 `src.graph.*` → `graph.*` 통일 | `enhance_taxonomy_snomed.py` |
| 4 | **High** | `WITH 1 as done` → `CALL {}` 서브쿼리 (MATCH 실패 시 배치 전체 스킵 방지) | `snomed_enricher.py` |
| 5 | **High** | `get_snomed_for_*()` 4개 함수에 abbreviation 검색 추가 (`_search_mapping` 공통화) | `spine_snomed_mappings.py` |
| 6 | **Medium** | `split_compound_anatomy`에 "and" 구분자 추가, NON_SPECIFIC 소문자 세트 캐시 | `snomed_enricher.py` |
| 7 | **Medium** | `enrich_graph_snomed.py` Neo4j 연결 에러 핸들링 + 트러블슈팅 가이드 | `enrich_graph_snomed.py` |

#### 커버리지 확장

| # | 변경 | 파일 |
|---|------|------|
| 1 | 분절 레벨 SNOMED **7개** 추가 (C3-4, C4-5, C7-T1, L1-2, L2-3, T11-12, T12-L1) | `spine_snomed_mappings.py` |
| 2 | PJK를 Pathology SNOMED에 추가 (기존 Outcome에만 존재) | `spine_snomed_mappings.py` |
| 3 | Neuromuscular Scoliosis 코드 분리 (Adult Scoliosis와 중복 해소, 확장코드 할당) | `spine_snomed_mappings.py` |
| 4 | Intervention **카테고리 24건** 추가 (누락 0건 달성) | `entity_normalizer.py` |
| 5 | `update_snomed_codes.py` deprecated 표시 → `enrich_graph_snomed.py`로 대체 | `update_snomed_codes.py` |
| 6 | X-ray SNOMED 매핑 추가 (363680008) + INTERVENTION_ALIASES 추가 | `spine_snomed_mappings.py`, `entity_normalizer.py` |
| 7 | `get_snomed_code()` / `get_snomed_mapping()`에 anatomy 타입 지원 추가 | `entity_normalizer.py` |
| 8 | `backfill_treats_relations` review_ids 안전한 `.get()` 접근, cleanup null 체크 | `snomed_enricher.py` |
| 9 | `enhance_taxonomy_snomed.py` load_dotenv 경로 명시, `init_neo4j.py` import 통일 | scripts |
| 10 | Vertebrectomy 중복 코드 해소 (112730002 → 확장코드 179 분리) | `spine_snomed_mappings.py` |
| 11 | TREATS 속성 `source_paper_id` → `source_paper_ids` (리스트) 통일 | `schema.py`, `snomed_enricher.py` |
| 12 | 확장코드 갭 502-503 채움 (DVT, Screw Malposition 추가) | `spine_snomed_mappings.py` |
| 13 | 확장코드 66개에 abbreviations 추가 (I:31, P:20, O:15) | `spine_snomed_mappings.py` |

- SNOMED 통계: 304 → **315개** (I:123, P:85, O:70, A:37) — 공식 142개 + 확장 173개

### v1.16.3 (2026-02-14): SNOMED/TREATS/Anatomy 통합 보강 스크립트

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

### v1.16.0 (2026-02-14): PubMed + DOI Fallback 통합 — 항상 보강, 항상 저장

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

### v1.15.1 (2026-02-14): 런타임 안정성 및 테스트 커버리지 강화

v1.15.0 QC에서 식별된 잔여 저우선도 항목 수정 및 신규 테스트 추가.

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

### v1.15.0 (2026-02-14): 보안 강화 및 코드 품질 개선 (QC)

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
| 17 | Web footer 버전 "v5.3" → "v1.15.0"으로 업데이트 | `app.py` |

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

### v1.14.31 (2026-02-13): 26개 저널별 참고문헌 스타일 추가

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

### v1.14.30 (2026-01-27): 버그 수정 3건

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
    title=getattr(chunk, 'title', None)  # v1.14.30: title 필드 추가
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

### v1.14.29 (2026-01-26): 테스트 코드 임베딩 차원 수정

#### 테스트 코드 OpenAI 3072d 임베딩 호환 업데이트

**배경**: v1.14.26에서 MedTE 768d → OpenAI 3072d 전환이 완료되었으나, 테스트 코드의 Mock 값들이 업데이트되지 않아 테스트 실패 발생

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

### v1.14.28 (2026-01-26): SSE 서버 통합 및 코드 중복 제거

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
| `src/medical_mcp/sse_server.py` | v1.14.28 업데이트, 문서화 보강 |
| `scripts/run_mcp_sse.py` | sse_server.py 래퍼로 변환 |

---

### v1.14.27 (2026-01-26): LLM 병렬 처리 + None 값 처리 버그 수정

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

### v1.14.26 (2026-01-21): MedTE 768d → OpenAI 3072d 전면 교체

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

### v1.14.25 (2026-01-21): 자동 하이브리드 검색 + 스키마 시각화

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

### v1.14.24 (2026-01-21): PubMed 임포트 최적화 + 하이브리드 검색

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

### v1.14.23 (2026-01-21): PubMed 병렬 임포트 + 환경변수 설정 + DOI 버그 수정

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

### v1.14.22 (2026-01-20): 테스트 정리 및 버그 수정

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

### v1.14.21 (2026-01-20): Taxonomy 자동 연결 + Direction 판단 로직 개선 + 문서 일관성 수정

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
- `TERMINOLOGY_ONTOLOGY.md`: 버전 1.14.19 → 1.14.21 업데이트

**코드 변경**:
- **`relationship_builder.py`**:
  - `link_intervention_to_taxonomy()`: IS_A 관계 자동 생성 로직 추가
  - `_determine_parent_intervention()`: 카테고리/패턴 기반 부모 결정
  - `_determine_direction()`: baseline/final, effect_size 기반 판단 로직
  - `_is_lower_better_outcome()`: 결과변수 특성 판단
- **`taxonomy_manager.py`**:
  - `find_common_ancestor()`: path length 기반 최단 거리 공통 조상 쿼리

---

### v1.14.20 (2026-01-20): Evidence Chain 개선 + Search 결과 Title 추가 + 테스트 정리

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

### v1.14.19 (2026-01-18): Adaptive Search 버그 수정 + 문서 버전 동기화

**핵심 수정**:
- **Adaptive Search 버그 수정**: `hybrid_search()` 파라미터 오류 해결
  - 문제: `Neo4jClient.hybrid_search()` 호출 시 `query` 인자 대신 `embedding` 인자 필요
  - 해결: 쿼리 임베딩 생성 후 `hybrid_search(embedding=...)` 형태로 호출
  - Fallback: 임베딩 생성 실패 시 일반 tiered search로 자동 전환
- **문서 버전 동기화**: 6개 문서를 v1.14.19로 업데이트
  - `TERMINOLOGY_ONTOLOGY.md`: v1.14.15 → v1.14.19
  - `NEO4J_SETUP.md`: v1.14.15 → v1.14.19
  - `developer_guide.md`: v1.14.15 → v1.14.19
  - `user_guide.md`: v1.14.15 → v1.14.19
  - `MCP_USAGE_GUIDE.md`: v1.14.18 → v1.14.19
  - `TRD_v3_GraphRAG.md`: v1.14.18 → v1.14.19
- **CLAUDE.md 비밀번호 동기화**: `.env` 실제 설정과 일치하도록 수정
  - 비밀번호를 `.env` 환경변수로 통일

**코드 변경**:
- **`search_handler.py`** (adaptive_search 메서드):
  - 쿼리 임베딩 생성 로직 추가 (`vector_db.get_embedding()` 또는 `get_embedding_generator()`)
  - `hybrid_search(query=...)` → `hybrid_search(embedding=...)` 수정
  - 임베딩 생성 실패 시 `self.search()` fallback 추가

---

### v1.14.18 (2026-01-18): Graph Search 강화 + MCP 서버 모듈화 + 문서 동기화

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
  - Reference Formatter (v1.9), Writing Guide (v1.12) 명시

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

### v1.14.17 (2026-01-14): Neo4j Hybrid Search 통합 - 그래프+벡터 단일 쿼리

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

### v1.14.16 (2026-01-14): 검색 버그 수정 및 Paper-Paper 관계 구축 기능 추가

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

### v1.14.15 (2026-01-13): 전체 프로젝트 검증 및 정리

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
- `docs/QUICK_REFERENCE.md`: v3.1.1 → v1.14.15
- `docs/api/advanced_rag.md`: 3.1 → 1.14.15, GraphRAG 2.0 아카이브 표시 추가
- `docs/SCHEMA_UPDATE_GUIDE.md`: v1.14.2 → v1.14.15
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

### v1.14.14 (2025-12-31): SNOMED-CT 패턴 매핑 대규모 확장

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

### v1.14.13 (2025-12-31): Taxonomy & SNOMED-CT 기초 강화

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

### v1.14.12 (2025-12-31): ChromaDB 완전 제거 & Database Maintenance

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

### v1.14.11 (2025-12-31): MCP Search Entity Normalization

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

### v1.14.10 (2025-12-28): SpineMetadata Field Mapping Fix

- **SpineMetadata 필드 매핑 수정 (critical bug fix)**:
  - `unified_pdf_processor.SpineMetadata`와 `relationship_builder.SpineMetadata` 간 필드명 불일치 해결
  - `pathology` (list) → `pathologies` 매핑
  - `anatomy_level` (str) + `anatomy_region` (str) → `anatomy_levels` (list) 매핑
  - `ExtractedOutcome` 객체 → dict 변환 자동화

- **v1.2 Extended Entities 지원 완성**:
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

### v1.14.9 (2025-12-28): Citation Storage Fix

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

### v1.14.8 (2025-12-27): Graph Explorer 쿼리 개선

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

### v1.14.7 (2025-12-27): Search Fix - LangChain 의존성 제거

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

### v1.14.6 (2025-12-27): Taxonomy 정비 - Intervention/Pathology/Outcome 계층화

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

### v1.14.5 (2025-12-27): 중복 Paper/Chunk 방지

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

### v1.14.4 (2025-12-27): Enhanced Graph Visualization with vis-network.js

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

### v1.14.3 (2025-12-27): Outcome/Complication 매핑 확장

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

### v1.14.2 (2025-12-26): Schema, Taxonomy, MCP Reconnection

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
  - Extension Codes 목록 갱신 (v1.14-v1.14.2 추가분 포함)
- **수정된 파일**:
  - `src/graph/types/schema.py`
  - `src/ontology/spine_snomed_mappings.py`
  - `docs/GRAPH_SCHEMA.md`

### v1.14.1 (2025-12-25): Extended Terminology Normalization

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

### v1.14 (2025-12-25): Terminology Normalization Enhancement

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

### v1.13.1 (2025-12-25): DOI MCP Tool Integration & SSE Stability

- **MCP pubmed 도구에 DOI 기능 추가** (v1.12.2 기능 통합)
  - `fetch_by_doi`: DOI로 논문 조회 (Crossref + Unpaywall)
  - `doi_metadata`: DOI 메타데이터만 조회 (빠른 조회)
  - `import_by_doi`: DOI로 논문을 Neo4j 그래프에 임포트
- **새 메서드 추가** (`medical_kag_server.py`)
  - `fetch_by_doi()`: 전문/메타데이터 조회, 선택적 그래프 임포트
  - `get_doi_metadata()`: 메타데이터 전용 (전문 없이)
  - `import_by_doi()`: v1.5 파이프라인으로 분석 후 그래프 저장
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

### v1.13 (2025-12-25): DOI Fulltext Fetcher & PubMed Fallback Integration

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

### v1.12.1 (2025-12-24): SSE Server & Dependency Fixes

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

### v1.12 (2025-12-23): Academic Writing Guide System

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

### v1.11 (2025-12-22): SSI Classification & Comorbidity Terms

- **Surgical Site Infection (SSI) 세분화**: 표재성/심부 구분 추가
  - `Superficial Surgical Site Infection` (SNOMED: 433202001): 피부, 피하조직 감염
  - `Deep Surgical Site Infection` (SNOMED: 433201008): 근육, 임플란트 관련 감염
  - `Infection Rate` 동의어 확장: "SSI rate", "Postoperative infection" 추가
- **Comorbidities / Risk Factors 섹션 신설** (SPINE_PATHOLOGY_SNOMED):
  - `Diabetes Mellitus` (SNOMED: 73211009): 수술 부위 감염의 주요 위험인자
- **SNOMED 매핑 통계 갱신**: Pathology 28개 (+1), Outcome 27개 (+2)
- **수정된 파일**: `src/ontology/spine_snomed_mappings.py`

### v1.10 (2025-12-22): SNOMED-CT Full Entity Integration

- **SNOMED-CT 코드 전체 엔티티 지원**: Intervention, Pathology, Outcome 모든 노드에 SNOMED 코드 저장
- **Pathology (질환) SNOMED 지원 추가**:
  - `CypherTemplates.CREATE_STUDIES_RELATION`: SNOMED fallback 로직 추가
  - `neo4j_client.create_studies_relation()`: `snomed_code`, `snomed_term` 파라미터 추가
  - `relationship_builder.create_studies_relations()`: 정규화 결과에서 SNOMED 전달
- **Outcome (결과변수) SNOMED 지원 추가**:
  - `CypherTemplates.CREATE_AFFECTS_RELATION`: SNOMED fallback 로직 추가
  - `neo4j_client.create_affects_relation()`: `snomed_code`, `snomed_term` 파라미터 추가
  - `relationship_builder.create_affects_relations()`: 정규화 결과에서 SNOMED 전달
- **ExtractedEntity SNOMED 필드 추가** (v1.8 보완):
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

### v1.9 (2025-12-22): Reference Citation Formatter

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

### v1.8 (2025-12-22): Important Citations Full Analysis Pipeline

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

### v1.7 (2025-12-21): Code Quality - medical_kag_server.py Handler Integration

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

### v1.6 (2025-12-21): Code Quality - spine_schema.py Modularization

- **spine_schema.py 분할**: 4,329줄 → 7개 모듈 (최대 1,296줄)
- **새 구조**: `src/graph/types/` 패키지
  - `enums.py`: 9개 Enum (SpineSubDomain, EvidenceLevel, DocumentType 등)
  - `core_nodes.py`: 6개 핵심 Node (PaperNode, ChunkNode 등)
  - `extended_nodes.py`: 16개 확장 Node (PatientCohortNode, FollowUpNode 등)
  - `relationships.py`: 22개 Relationship 클래스
  - `schema.py`: SpineGraphSchema, CypherTemplates
- **하위 호환성**: 기존 `from graph.spine_schema import ...` 계속 동작
- **SRP 준수**: Single Responsibility Principle 적용

### v1.5 (2025-12-21): Unified Narrative Summary Pipeline
- **v1.0 Simplified Pipeline 기본 사용**: `add_pdf(use_v7=True)` 파라미터
- **통합 요약 형식**: 4개 섹션 (Background, Methodology, Key Findings, Conclusions)
- **Important Citation 자동 처리**: Discussion/Results에서 중요 인용 추출 → PubMed 검색 → CITES 관계 생성
- **Legacy Processor Deprecation**: `unified_pdf_processor.py` → `unified_processor_v7.py`

### v1.5 (2025-12-19): Multi-User Support with SSE Transport
- **다중 사용자 지원**: 라벨 기반 데이터 분리 (owner/shared 필드)
- **SSE 서버**: `python -m medical_mcp.sse_server --port 8000`
- **REST API**: FastAPI 기반 `/tool/{name}` 엔드포인트

### v1.4 (2025-12-19): MCP Tool Consolidation
- **38 Tools → 8 Tools**: Context Token ~63% 절감
- **8개 통합 도구**: document, search, pubmed, analyze, graph, conflict, intervention, extended
- **Action 기반 라우팅**: 각 도구에 `action` 파라미터로 세부 기능 선택

### v1.2 (2025-12-19): Extended Entity Schema
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
