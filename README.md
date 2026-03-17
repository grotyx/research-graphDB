# Spine GraphRAG System

**Version**: 1.29.0 | **Status**: Production Ready

Neo4j 기반 GraphRAG 시스템으로, 척추 수술 분야의 의학 논문을 구조화된 지식 그래프로 구축하고 근거 기반 검색을 지원합니다.

## Architecture

```
PDF/Text → Claude Haiku → SpineMetadata Extraction
                              ↓
              Neo4j (Graph + Vector Unified)
              ├── Graph: Paper, Pathology, Intervention, Outcome, Anatomy
              ├── Vector: HNSW Index (3072d OpenAI embeddings)
              ├── Ontology: SNOMED-CT IS_A hierarchy (735 mappings)
              └── Hybrid Search: Multi-Vector + Graph Filter
                              ↓
              Hybrid Ranker (Dynamic Weights by Query Type)
              ├── Comparison: graph 0.5 + authority 0.3 + semantic 0.2
              ├── Evidence:   authority 0.5 + semantic 0.3 + graph 0.2
              ├── Mechanism:  semantic 0.6 + graph 0.2 + authority 0.2
              └── Default:    semantic 0.4 + authority 0.3 + graph 0.3
```

## Key Features

### Retrieval
- **Neo4j 단일 저장소**: Graph + Vector (HNSW 3072d) 통합 검색
- **Multi-Vector Retrieval**: Chunk + Paper abstract 임베딩 RRF 융합
- **Contextual Embedding Prefix**: `[title | section | year]` prefix로 chunk 맥락 반영
- **Cross-Encoder Reranker**: Cohere rerank-v3.5 기반 re-ranking (optional)
- **HyDE**: 가상 답변 임베딩으로 복잡한 질문 검색 개선
- **Dynamic Weights**: 쿼리 유형별 자동 가중치 조정 (comparison/evidence/mechanism)

### Reasoning
- **Agentic RAG**: 복잡한 질문을 하위 질문으로 분해 → 병렬 검색 → 통합 추론
- **Evidence Synthesis**: 가중 평균 효과 크기, I² 이질성 검정, Forest plot 데이터
- **GRADE 기반 충돌 탐지**: 상충하는 연구 결과 자동 식별 및 해결

### Knowledge Graph
- **SNOMED-CT 온톨로지**: 735개 매핑 (I:235, P:231, O:200, A:69), 4개 엔티티 IS_A 계층
- **다중 홉 그래프 순회**: Evidence chain, Intervention 비교, Best evidence 검색
- **Evidence-based Ranking**: p-value, effect size, evidence level 기반 랭킹

### Integration
- **Claude Haiku 4.5** PDF/텍스트 분석 + Gemini 폴백
- **PubMed 서지 자동 보강**: PubMed → Crossref/DOI → Basic 3단계 Fallback
- **10개 MCP 도구**: Claude Desktop/Code SSE 연동
- **참고문헌 포맷팅**: 7개 스타일 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)

### Quality Assurance
- **4,065 tests** (unit + integration)
- **RAGAS 평가**: Faithfulness, Answer Relevancy, Context Precision/Recall, Citation Fidelity
- **3-tier QA**: QC (문서), CA (코드, 9.5/10), DV (데이터)
- **Chunk Quality Validation**: 길이 필터, tier 강등, 통계 검증, 근접 중복 탐지

## Quick Start

```bash
# 1. 환경 설정
cp .env.example .env
# .env에 ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD 설정

# 2. Neo4j 시작
docker-compose up -d

# 3. 스키마 초기화 (Neo4j 기동 후 30초 대기)
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. 테스트
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. Web UI
streamlit run web/app.py
```

## Paper Import (PubMed)

```bash
# PubMed 검색 + 임포트 (Claude Code CLI)
/pubmed-import lumbar fusion outcomes

# PMID로 직접 임포트
/pubmed-import --pmids 41464768,41752698

# 임포트 후 SNOMED 매핑 + TREATS 백필
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## MCP Server

Claude Code/Desktop에서 원격 접속 가능한 SSE 서버:

```bash
# Docker로 시작 (포트 7777)
docker-compose up -d

# Health check
curl http://localhost:7777/health
# {"status": "healthy", "version": "1.29.0"}

# Claude Code에서 연결
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

## 10개 MCP 도구

| 도구 | 설명 | 주요 액션 |
|------|------|----------|
| `document` | 문서 관리 | add_pdf, list, delete, summarize, stats |
| `search` | 검색/추론 | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI 연동 | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | 텍스트 분석 | text, store_paper |
| `graph` | 그래프 탐색 | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | 충돌 탐지 | find, detect, synthesize (GRADE 기반) |
| `intervention` | 수술법 분석 | hierarchy, compare, comparable |
| `extended` | 확장 엔티티 | patient_cohorts, followup, cost, quality_metrics |
| `reference` | 참고문헌 포맷팅 | format, format_multiple, list_styles, preview |
| `writing_guide` | 논문 작성 가이드 | section_guide, checklist, expert, draft_response |

## Operational Scripts

| Script | Description |
|--------|-------------|
| `scripts/init_neo4j.py` | Neo4j 스키마/인덱스 초기화 |
| `scripts/enrich_graph_snomed.py` | SNOMED 코드 적용 + TREATS 백필 |
| `scripts/repair_isolated_papers.py` | 고립 논문 복구 (LLM 재분석) |
| `scripts/repair_missing_chunks.py` | HAS_CHUNK 누락 Paper 복구 |
| `scripts/build_ontology.py` | IS_A 계층 일괄 구축 |
| `scripts/normalize_entities.py` | 엔티티 정규화 (중복 병합) |
| `scripts/backfill_paper_embeddings.py` | Paper abstract 임베딩 배치 생성 |
| `scripts/neo4j_backup.py` | Neo4j 백업/복구/정리 |

## Project Structure

```
rag_research/
├── src/
│   ├── graph/           # Neo4j 그래프 레이어 (client, DAOs, schema, taxonomy)
│   ├── builder/         # PDF/PubMed 처리 (chunk_validator, pubmed_processor)
│   ├── solver/          # 검색/추론 (tiered_search, hybrid_ranker, agentic_rag, evidence_synthesizer)
│   ├── llm/             # LLM 클라이언트 (Claude, Gemini)
│   ├── medical_mcp/     # MCP 서버 + 11개 도메인 핸들러
│   ├── core/            # 설정/로깅/예외/임베딩/캐시
│   ├── cache/           # 캐싱 (query, embedding, semantic)
│   ├── ontology/        # SNOMED-CT 온톨로지 (735개 매핑)
│   ├── orchestrator/    # 쿼리 라우팅/Cypher 생성
│   └── external/        # 외부 API (PubMed)
├── evaluation/          # 벤치마크 (metrics, baselines, RAGAS, gold_standard)
├── scripts/             # 운영 스크립트
├── web/                 # Streamlit UI
├── tests/               # 4,065 tests
└── docs/                # 문서 (PRD, TRD, CHANGELOG 등)
```

## Environment Variables

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

## Documentation

| 문서 | 용도 |
|------|------|
| [CHANGELOG](docs/CHANGELOG.md) | 버전 히스토리 |
| [PRD](docs/PRD.md) | 요구사항 정의서 |
| [TRD](docs/TRD_v3_GraphRAG.md) | 기술 사양서 |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | 노드/관계 스키마 |
| [TERMINOLOGY_ONTOLOGY](docs/TERMINOLOGY_ONTOLOGY.md) | 용어체계/온톨로지 |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP 도구 사용 가이드 |
| [ROADMAP](docs/ROADMAP.md) | 개선 로드맵 |
| [QC_CHECKLIST](docs/QC_CHECKLIST.md) | 품질 검증 체크리스트 |
| [CODE_AUDIT](docs/CODE_AUDIT.md) | 코드 감사 체크리스트 |

## Author

**Professor Sang-Min Park, M.D., Ph.D.**

Department of Orthopaedic Surgery, Seoul National University Bundang Hospital, Seoul National University College of Medicine

[https://sangmin.me/](https://sangmin.me/)

## License

This project is provided for **research and personal use only**.

See [LICENSE](LICENSE) for details.
