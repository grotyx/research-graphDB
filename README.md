# Spine GraphRAG System

**Version**: 1.25.0 | **Status**: Production Ready

Neo4j 기반 GraphRAG 시스템으로, 척추 수술 분야의 의학 논문을 구조화된 지식 그래프로 구축하고 근거 기반 검색을 지원합니다.

## Architecture

```
PDF/Text → Claude Haiku → SpineMetadata Extraction
                              ↓
              Neo4j (Graph + Vector Unified)
              ├── Graph: Paper, Pathology, Intervention, Outcome, Anatomy
              ├── Vector: HNSW Index (3072d OpenAI embeddings)
              ├── Ontology: SNOMED-CT IS_A hierarchy (653 mappings)
              └── Single Cypher Query: Graph Filter + Vector Search
                              ↓
              Hybrid Ranker (Semantic 0.4 + Authority 0.3 + Graph 0.3)
```

## Key Features

- **Neo4j 단일 저장소**: Graph + Vector (HNSW 3072d) 통합 검색
- **SNOMED-CT 온톨로지**: 653개 매핑 (I:204, P:188, O:194, A:67), 4개 엔티티 IS_A 계층
- **Claude Haiku 4.5 기반** PDF/텍스트 분석 + Gemini 폴백
- **다중 홉 그래프 순회**: Evidence chain, Intervention 비교, Best evidence 검색
- **Evidence-based Ranking**: p-value, effect size, evidence level 기반 3-way 랭킹
- **PubMed 서지 자동 보강**: PubMed → Crossref/DOI → Basic 3단계 Fallback
- **10개 MCP 도구**: Claude Desktop/Code SSE 연동
- **참고문헌 포맷팅**: 7개 스타일 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)
- **22개 문서 유형 지원**: Zotero/EndNote 호환
- **3,741 tests** (unit + integration)

## Quick Start

```bash
# 1. 환경 설정
cp .env.example .env
# .env에 ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD 설정

# 2. Neo4j 시작
docker-compose up -d

# 3. 스키마 초기화 (Neo4j 기동 후 30초 대기)
python scripts/init_neo4j.py

# 4. Web UI 실행
streamlit run web/app.py

# 5. 테스트
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q
```

## MCP Server (SSE Mode)

Claude Code/Desktop에서 원격 접속 가능한 SSE 서버:

```bash
# SSE 서버 시작 (포트 7777)
PYTHONPATH=./src python3 -m medical_mcp.sse_server --host 0.0.0.0 --port 7777

# Health check
curl http://localhost:7777/health
```

### 클라이언트 연결

```bash
# Claude Code에서 MCP 서버 추가
claude mcp add --transport sse medical-kag-remote http://YOUR_SERVER_IP:7777/sse --scope project
```

### 등록된 사용자

| User ID | 역할 |
|---------|------|
| system | admin (모든 문서 접근) |
| kim | user |
| park | user |
| lee | user |

특정 사용자로 접속: `http://YOUR_SERVER_IP:7777/sse?user=system`

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

## Project Structure

```
rag_research/
├── src/
│   ├── graph/           # Neo4j 그래프 레이어 (client, DAOs, schema, taxonomy)
│   ├── builder/         # PDF/PubMed 처리 파이프라인
│   ├── solver/          # 검색/추론 (tiered_search, hybrid_ranker, graph_traversal)
│   ├── llm/             # LLM 클라이언트 (Claude, Gemini)
│   ├── medical_mcp/     # MCP 서버 + 11개 도메인 핸들러
│   ├── core/            # 설정/로깅/예외/임베딩
│   ├── cache/           # 캐싱 (query, embedding, semantic)
│   ├── ontology/        # SNOMED-CT 온톨로지 (653개 매핑)
│   ├── orchestrator/    # 쿼리 라우팅/Cypher 생성
│   └── external/        # 외부 API (PubMed)
├── web/                 # Streamlit UI
├── scripts/             # 운영 스크립트 (init, repair, enrich)
├── tests/               # 테스트 (3,741 tests)
└── docs/                # 문서
```

## Environment Variables

```bash
# .env.example 참조
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
LLM_MAX_CONCURRENT=5              # LLM 동시 호출 수 (1-20)
PUBMED_MAX_CONCURRENT=5           # PubMed 동시 처리 수 (1-10)
```

## Documentation

| 문서 | 용도 |
|------|------|
| [CHANGELOG](docs/CHANGELOG.md) | 버전 히스토리 |
| [PRD](docs/PRD.md) | 요구사항 정의서 |
| [TRD](docs/TRD_v3_GraphRAG.md) | 기술 사양서 |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | 노드/관계 스키마 |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP 도구 사용 가이드 |
| [QC_CHECKLIST](docs/QC_CHECKLIST.md) | 품질 검증 체크리스트 |

## License

Private repository - All rights reserved.
