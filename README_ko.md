# Spine GraphRAG

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md) | [中文](README_zh.md) | [Español](README_es.md)

**Version**: 1.32.0 | **Status**: Production Ready

Neo4j 기반 GraphRAG 시스템으로, 척추 수술 분야의 의학 논문을 구조화된 지식 그래프로 구축하고 근거 기반 검색을 지원합니다.

- **1,030편** 척추 수술 논문 인덱싱
- **735개** SNOMED-CT 개념 매핑 (Intervention: 235, Pathology: 231, Outcome: 200, Anatomy: 69)
- **4,065+** 자동화 테스트
- **10개** MCP 도구 (Claude Desktop/Code 연동)

---

## 아키텍처

```
PDF/Text --> Claude Haiku 4.5 --> SpineMetadata Extraction
                                    |
                  Neo4j (단일 저장소: Graph + Vector 통합)
                  +-- Graph: Paper, Pathology, Intervention, Outcome, Anatomy
                  +-- Vector: HNSW Index (3072d OpenAI embeddings)
                  +-- Ontology: SNOMED-CT IS_A 계층 (735개 매핑)
                  +-- Hybrid Search: Multi-Vector + Graph Filter
                                    |
                  B4 GraphRAG Pipeline (v20, 8단계)
                  +-- 1. HyDE (가상 문서 임베딩)
                  +-- 2. Tiered Hybrid Search (Graph + Vector, 5배 다양성)
                  +-- 3. LLM Reranker (Claude Haiku)
                  +-- 4. Multi-Vector Search (abstract 임베딩, 3배)
                  +-- 5. IS_A Expansion (pathology + 키워드 필터)
                  +-- 6. Graph Traversal Summary (근거 체인)
                  +-- 7. Graph Hint (시스템 프롬프트 주입)
                  +-- 8. 정량적 답변 생성
```

## 주요 기능

### 검색 (Retrieval)

- **Neo4j 단일 저장소**: Graph + Vector (HNSW 3072d) 통합 검색
- **HyDE**: 가상 답변 임베딩으로 복잡한 임상 질문 검색 개선
- **LLM Reranker**: Claude Haiku 기반 chunk-level relevance 재평가
- **Multi-Vector Retrieval**: Chunk + Paper abstract 임베딩 융합 (논문 다양성 확보)
- **Contextual Embedding Prefix**: `[title | section | year]` prefix로 chunk 맥락 반영
- **Direct Search Keyword Filter**: off-topic 논문 자동 제거

### 지식 그래프

- **SNOMED-CT 온톨로지**: 4개 엔티티 타입에 걸쳐 735개 매핑 및 IS_A 계층
- **IS_A Expansion**: pathology-aware + 키워드 필터로 관련 sibling 논문 보충
- **다중 홉 그래프 순회**: Evidence chain, Intervention 비교, shared/unique outcome 분석
- **Evidence-based Ranking**: p-value, effect size, evidence level 기반 랭킹
- **Graph Hint**: 시스템 프롬프트에 intervention-pathology 관계 1줄 요약

### 추론 (Reasoning)

- **정량 데이터 추출 프롬프트**: p-values, ORs, CIs, 발생률 등 구체적 수치 추출 강조
- **Agentic RAG**: 복잡한 질문을 하위 질문으로 분해 후 병렬 검색 및 통합 추론
- **Evidence Synthesis**: 가중 평균 효과 크기, I-squared 이질성 검정
- **GRADE 기반 충돌 탐지**: 상충하는 연구 결과 자동 식별

### 임포트 파이프라인

- **Claude Haiku 4.5** PDF/텍스트 분석 + Gemini 폴백
- **PubMed 서지 자동 보강**: PubMed, Crossref/DOI, Basic 3단계 Fallback
- **Entity Normalization**: 280+ alias 매핑, SNOMED-CT 자동 링크
- **Chunk Validation**: 길이 필터, tier 강등, 통계 검증, 근접 중복 탐지

### 연동

- **10개 MCP 도구**: Claude Desktop/Code SSE 연동
- **참고문헌 포맷팅**: 7개 스타일 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)

---

## 빠른 시작

```bash
# 1. 환경 설정
cp .env.example .env
# .env에 ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD 설정

# 2. Neo4j 시작
docker-compose up -d

# 3. 스키마 초기화 (Neo4j 기동 후 약 30초 대기)
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. 테스트 실행
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. Web UI 실행
streamlit run web/app.py
```

## 논문 임포트 (PubMed)

```bash
# PubMed 검색 + 임포트 (Claude Code CLI)
/pubmed-import lumbar fusion outcomes

# PMID로 직접 임포트
/pubmed-import --pmids 41464768,41752698

# SNOMED 매핑 + TREATS 백필
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## MCP 서버

```bash
# Docker로 시작 (포트 7777)
docker-compose up -d

# 상태 확인
curl http://localhost:7777/health

# Claude Code에서 연결
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

### 10개 MCP 도구

| 도구 | 설명 | 주요 액션 |
|------|------|----------|
| `document` | 문서 관리 | add_pdf, list, delete, summarize, stats |
| `search` | 검색/추론 | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI 연동 | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | 텍스트 분석 | text, store_paper |
| `graph` | 그래프 탐색 | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | 충돌 탐지 | find, detect, synthesize (GRADE 기반) |
| `intervention` | 수술법 분석 | hierarchy, compare, comparable |
| `extended` | 확장 엔티티 조회 | patient_cohorts, followup, cost, quality_metrics |
| `reference` | 참고문헌 포맷팅 | format, format_multiple, list_styles, preview |
| `writing_guide` | 논문 작성 가이드 | section_guide, checklist, expert, draft_response |

## 운영 스크립트

| 스크립트 | 설명 |
|---------|------|
| `scripts/init_neo4j.py` | Neo4j 스키마/인덱스 초기화 |
| `scripts/enrich_graph_snomed.py` | SNOMED 코드 적용 + TREATS 백필 |
| `scripts/repair_isolated_papers.py` | 고립 논문 복구 (LLM 재분석) |
| `scripts/repair_missing_chunks.py` | HAS_CHUNK 누락 Paper 복구 |
| `scripts/build_ontology.py` | IS_A 계층 일괄 구축 |
| `scripts/normalize_entities.py` | 엔티티 정규화 (중복 병합) |
| `scripts/backfill_paper_embeddings.py` | Paper abstract 임베딩 배치 생성 |

## 프로젝트 구조

```
rag_research/
+-- src/
|   +-- graph/           # Neo4j 그래프 레이어 (client, DAOs, schema, taxonomy)
|   +-- builder/         # PDF/PubMed 처리 (chunk_validator, pubmed_processor)
|   +-- solver/          # 검색/추론 (tiered_search, hybrid_ranker, reranker, graph_traversal)
|   +-- llm/             # LLM 클라이언트 (Claude, Gemini)
|   +-- medical_mcp/     # MCP 서버 + 11개 도메인 핸들러
|   +-- core/            # 설정/로깅/예외/임베딩/캐시
|   +-- cache/           # 캐싱 (query, embedding, semantic)
|   +-- ontology/        # SNOMED-CT 온톨로지 (735개 매핑)
|   +-- orchestrator/    # 쿼리 라우팅/Cypher 생성
|   +-- external/        # 외부 API (PubMed)
+-- evaluation/          # 벤치마크 프레임워크
+-- scripts/             # 운영 스크립트
+-- web/                 # Streamlit UI
+-- tests/               # 4,065+ 테스트
+-- docs/                # 문서
```

## 환경 변수

```bash
# .env.example 참조
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large, 3072d)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
LLM_MAX_CONCURRENT=5              # LLM 동시 호출 수 (1-20)
PUBMED_MAX_CONCURRENT=5           # PubMed 동시 처리 수 (1-10)
EMBEDDING_CONTEXTUAL_PREFIX=true  # Contextual embedding prefix 활성화
```

## 문서

| 문서 | 용도 |
|------|------|
| [CHANGELOG](docs/CHANGELOG.md) | 버전 히스토리 |
| [PRD](docs/PRD.md) | 요구사항 정의서 |
| [TRD](docs/TRD_v3_GraphRAG.md) | 기술 사양서 |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | 노드/관계 스키마 |
| [TERMINOLOGY_ONTOLOGY](docs/TERMINOLOGY_ONTOLOGY.md) | 용어체계/온톨로지 |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP 도구 사용 가이드 |
| [ROADMAP](docs/ROADMAP.md) | 개선 로드맵 |

## 저자

**박상민 교수, M.D., Ph.D.**

서울대학교 의과대학 정형외과학교실, 서울대학교 분당서울대학교병원 정형외과

[https://sangmin.me/](https://sangmin.me/)

## 라이선스

본 프로젝트는 **연구 및 개인 사용 목적으로만** 제공됩니다. 상업적 사용은 사전 서면 동의 없이 허용되지 않습니다.

자세한 내용은 [LICENSE](LICENSE)를 참조하십시오.

Copyright (c) 2024-2026 Sangmin Park
