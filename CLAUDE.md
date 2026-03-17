# Spine GraphRAG System - Project Rules

## Project Overview

Spine GraphRAG는 Neo4j 그래프 데이터베이스를 사용한 단일 저장소 시스템입니다.
척추 수술 분야의 의학 논문을 처리하여 구조화된 지식 그래프를 구축하고, 근거 기반 검색을 지원합니다.

**Version**: 1.29.0 | **Status**: Production Ready
**Docs**: [PRD](docs/PRD.md) | [TRD](docs/TRD_v3_GraphRAG.md) | [Changelog](docs/CHANGELOG.md)

### Architecture (Single-Store: Neo4j Only)

```text
PDF/Text → Claude Haiku → SpineMetadata Extraction
                              ↓
              Neo4j (Graph + Vector Unified)
              ├── Graph: Paper, Pathology, Intervention, Outcome
              ├── Vector: HNSW Index (3072d OpenAI embeddings)
              └── Single Cypher Query: Graph Filter + Vector Search
                              ↓
              Hybrid Ranker (Graph 60% + Vector 40%)
```

### Domain: Spine Surgery

- **Sub-domains**: Degenerative, Deformity, Trauma, Tumor, Basic Science
- **Anatomy**: Cervical (C1-C7), Thoracic (T1-T12), Lumbar (L1-L5), Sacral, Junctional

### Key Features

- Neo4j Vector Index (HNSW) + Graph 통합 검색
- Claude Haiku 4.5 기반 PDF/텍스트 분석
- PubMed 서지 정보 자동 강화
- Intervention Taxonomy (IS_A 관계)
- Evidence-based Ranking (p-value, effect size, evidence level)
- 22개 문서 유형 지원 (Zotero/EndNote 호환)
- Reference Citation 포맷팅 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- Academic Writing Guide (9개 EQUATOR 체크리스트: STROBE, CONSORT, PRISMA, CARE, STARD, SPIRIT, MOOSE, TRIPOD, CHEERS)

## Development Rules

### Code Style

```python
# Python 3.10+, Type hints 필수, Google style docstrings
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class EvidenceLevel(Enum):
    LEVEL_1A = "1a"  # Meta-analysis
    LEVEL_1B = "1b"  # RCT
    LEVEL_2A = "2a"  # Cohort
    LEVEL_2B = "2b"  # Case-control
    LEVEL_3 = "3"    # Case series
    LEVEL_4 = "4"    # Expert opinion

@dataclass
class ClassName:
    """클래스 설명."""
    attr1: str
    attr2: Optional[int] = None
```

### LLM Integration

```python
from llm import LLMClient, LLMConfig

# Claude Haiku 4.5 (기본) + Sonnet 폴백
client = LLMClient(config=LLMConfig(temperature=0.1))
response = await client.generate(prompt, system_prompt="...")
result = await client.generate_json(prompt, schema)
```

### Neo4j Integration

```python
from neo4j import AsyncGraphDatabase

async with Neo4jClient() as client:
    await client.initialize_schema()
    # Cypher 파라미터화 (SQL injection 방지)
    result = await client.run_query(
        "MATCH (p:Paper {paper_id: $id}) RETURN p",
        {"id": paper_id}
    )
```

### Error Handling

```python
class ModuleError(Exception): pass
class ValidationError(ModuleError): pass
class LLMError(ModuleError): pass
class Neo4jError(ModuleError): pass
```

## Documentation Rules

**항상 아래 문서를 사용하고 지속적으로 업데이트할 것:**

| 문서 | 용도 | 업데이트 시점 |
|------|------|--------------|
| `docs/CHANGELOG.md` | 버전 히스토리 | 버전 변경, 기능 추가/수정 시 |
| `docs/PRD.md` | 요구사항 정의 | 새 기능 요구사항 추가 시 |
| `docs/TRD_v3_GraphRAG.md` | 기술 사양서 | 아키텍처/설계 변경 시 |
| `docs/GRAPH_SCHEMA.md` | 스키마 정의 | Node/Relationship 변경 시 |
| `docs/TERMINOLOGY_ONTOLOGY.md` | **용어체계/온톨로지** | **Schema, Taxonomy, SNOMED 변경 시** |

**규칙:**

1. 새 문서 파일을 만들지 말고 기존 문서에 추가/수정
2. CHANGELOG는 최신 버전이 상단에 오도록 작성
3. 버전 변경 시 CLAUDE.md 상단의 Version 번호도 함께 수정

## Quick Start

```bash
# 1. Neo4j 시작
docker-compose up -d

# 2. 스키마 초기화 (30초 후)
python scripts/init_neo4j.py

# 3. Web UI 실행
streamlit run web/app.py

# 4. 테스트
PYTHONPATH=./src pytest tests/
```

## Environment Variables

```bash
# .env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<see .env>
NEO4J_DATABASE=neo4j
NEO4J_BOLT_THREAD_POOL_SIZE=40  # Bolt 스레드 풀 (재시작 필요)

# PubMed Import (v1.14.23)
PUBMED_MAX_CONCURRENT=5  # 최대 동시 처리 수 (1-10)

# Concurrency (v1.23.4)
LLM_MAX_CONCURRENT=5     # LLM API 동시 호출 수 (1-20, 기본 5)
```

## Git Workflow

### 버전 체계 (Semantic Versioning)

```
1.X.Y 형식
│ │ └── Y: 패치 — 버그 수정, QA 수정, 문서 정리 (자동 올림)
│ └──── X: 마이너 — 새 기능 추가, ROADMAP 항목 구현 (자동 올림)
└────── 1: 메이저 — 대규모 아키텍처 변경 (사용자 지시 시에만 올림)
```

### 버전 올리는 기준

| 변경 유형 | 버전 | 예시 | 자동/수동 |
|-----------|------|------|-----------|
| **버그 수정** | Y +1 (패치) | `1.28.0 → 1.28.1` | 자동 |
| QA 수정 (QC/CA/DV) | Y +1 (패치) | 문서 동기화, 테스트 수정, 데이터 정리 | 자동 |
| 문서 정리 / 리팩토링 | Y +1 (패치) | Clean up, Update | 자동 |
| **새 기능 추가** | X +1 (마이너) | `1.28.1 → 1.29.0` | 자동 |
| ROADMAP 항목 구현 | X +1 (마이너) | Dynamic weights, Chunk validator | 자동 |
| 대규모 테스트 추가 (+100개 이상) | X +1 (마이너) | 핵심 모듈 테스트 커버리지 | 자동 |
| **메이저 업데이트** | 1 → 2 | 아키텍처 변경, 스키마 마이그레이션 | **사용자 지시 시에만** |

> **중요**: 메이저 버전(맨 앞 숫자)은 사용자가 명시적으로 올리라고 할 때만 변경합니다.

### 커밋 규칙

```bash
# 커밋 메시지 형식 — 버전 변경 포함
vX.Y.Z: 변경 요약 (새 기능 추가 시)

# 커밋 메시지 형식 — 버전 변경 없는 중간 커밋
Fix: 버그 수정 설명
QA scan + fix: QC/CA/DV 이슈 수정
Clean up / Update: 문서/리팩토링

# 예시
v1.29.0: HyDE + Reranker integration
v1.28.1: Fix TREATS paper_count drift, orphan chunk cleanup
Fix test failures: pubmed_bulk_processor import chain
QA scan + fix: 5 QC issues, 3 DV data fixes
Clean up redundant/outdated docs, update CLAUDE.md references
```

### 버전 변경 시 필수 업데이트 파일

버전을 올릴 때 아래 파일을 **모두** 동기화:

| 파일 | 위치 |
|------|------|
| `src/__init__.py` | `__version__ = "X.Y.Z"` (Source of Truth) |
| `pyproject.toml` | `version = "X.Y.Z"` |
| `CLAUDE.md` | `**Version**: X.Y.Z` |
| `.env.example` | `# Version: X.Y.Z` |
| `docs/CHANGELOG.md` | 최상단에 새 버전 항목 추가 |
| `docs/DEPLOYMENT.md` | 상단 버전 테이블 |
| `docs/NEO4J_SETUP.md` | 상단 Version 태그 |
| `docs/user_guide.md` | 상단 버전 정보 |
| `docs/PRD.md` | 버전 정보 |
| `docs/TERMINOLOGY_ONTOLOGY.md` | 버전 정보 |
| `docs/GRAPH_SCHEMA.md` | 버전 정보 |
| `docs/MCP_USAGE_GUIDE.md` | 버전 정보 |
| `docs/ROADMAP.md` | 상단 Version |

### 커밋 전 체크

```bash
# 테스트 실행
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 커밋 & 푸시
git add <files>
git commit -m "메시지"
git push origin main
```

### 주의사항

- `main` 브랜치에 직접 푸시 (단독 개발)
- `.env`, `data/`, `.venv/` 는 절대 커밋하지 않음 (`.gitignore`에 포함)
- 버전 변경 시 [QC 체크리스트](docs/QC_CHECKLIST.md) 실행 권장
- 시스템 python3 사용 (`/opt/homebrew/bin/python3`), .venv 없음

## Protected Data Folders

| 폴더 | 설명 |
|------|------|
| `data/extracted/` | LLM 추출 결과 JSON (재임베딩 시 재사용) |
| `data/pdf/` | 원본 PDF 파일 |
| `data/neo4j/` | Neo4j 데이터베이스 (Docker volume) |
| `data/styles/` | 저널 스타일 매핑 및 커스텀 스타일 |

## Project Structure

```text
rag_research/
├── src/
│   ├── graph/           # Neo4j 그래프 레이어 (neo4j_client, relationship_dao, search_dao, schema_manager, relationship_builder, taxonomy_manager)
│   ├── builder/         # PDF/PubMed 처리 (unified_pdf_processor, pubmed_downloader, pubmed_processor, reference_formatter)
│   ├── solver/          # 검색/추론 모듈 (tiered_search, hybrid_ranker, conflict_detector)
│   ├── llm/             # LLM 클라이언트 (claude_client, gemini_client)
│   ├── medical_mcp/     # MCP 서버 Facade + 11개 도메인 핸들러 (BaseHandler 상속)
│   ├── core/            # 설정/로깅/예외 (config, exceptions, embedding, text_chunker, bounded_cache)
│   ├── cache/           # 캐싱 (cache_manager, query_cache, embedding_cache, semantic_cache)
│   ├── knowledge/       # 지식 처리 (v1.20.0: 레거시 모듈 archive/로 이동)
│   ├── ontology/        # 온톨로지 (concept_hierarchy, snomed_linker, spine_snomed_mappings)
│   ├── orchestrator/    # 쿼리 라우팅 (query_pattern_router, cypher_generator)
│   ├── external/        # 외부 API (pubmed_client)
│   └── storage/         # (Deprecated) 하위 호환성용
├── evaluation/          # 벤치마크 프레임워크 (metrics, baselines, gold_standard)
├── web/                 # Streamlit UI
├── tests/               # 테스트
└── docs/                # 문서
```

## Key Modules

| Module | Description |
|--------|-------------|
| `neo4j_client.py` | Neo4j 연결 관리 + DAO 위임 (v1.22.0: 3 DAO 분리) |
| `relationship_dao.py` | v1.22.0: 관계 CRUD 17 methods (Neo4jClient에서 추출) |
| `search_dao.py` | v1.22.0: Vector/Hybrid 검색 7 methods |
| `schema_manager.py` | v1.22.0: 스키마 초기화/통계/클리어 4 methods |
| `unified_pdf_processor.py` | PDF/텍스트 통합 처리 |
| `pubmed_downloader.py` | v1.23.0: PubMed 검색/다운로드 (pubmed_bulk_processor에서 분리) |
| `pubmed_processor.py` | v1.23.0: PubMed 논문 LLM 처리/청크 생성 (pubmed_bulk_processor에서 분리) |
| `relationship_builder.py` | Paper → Graph 구축 |
| `entity_normalizer.py` | 용어 정규화 (UBE↔BESS), SNOMED 자동 링크 (로직만, 데이터는 normalization_maps.py) |
| `normalization_maps.py` | 정규화 매핑 데이터 (INTERVENTION/PATHOLOGY/OUTCOME/ANATOMY_ALIASES 등 8개 상수) |
| `taxonomy_manager.py` | Intervention IS_A 계층 관리 |
| `graph/snomed_enricher.py` | SNOMED 업데이트, TREATS 백필, Anatomy 정리 통합 모듈 |
| `graph/types/schema.py` | Neo4j 스키마, 인덱스, Cypher 템플릿 |
| `spine_snomed_mappings.py` | SNOMED-CT 매핑 (735개: I:235, P:231, O:200, A:69) — Single Source of Truth |
| `medical_kag_server.py` | MCP 서버 Facade (10개 도구, Tool Registry 디스패치 → 11개 핸들러) |
| `handlers/base_handler.py` | BaseHandler 공통 클래스 + safe_execute 데코레이터 |
| `solver/hybrid_ranker.py` | Evidence-based 3-way 랭킹 (semantic 0.4 + authority 0.3 + graph_relevance 0.3) |
| `solver/graph_traversal_search.py` | 다중 홉 그래프 순회 검색 (evidence chain, intervention 비교) |
| `solver/graph_context_expander.py` | 4개 엔티티 IS_A 확장 (expand_by_ontology) |
| `ontology/snomed_proposer.py` | LLM 기반 미등록 용어 SNOMED 매핑 제안 |
| `reference_formatter.py` | 참고문헌 스타일 포맷팅 |
| `writing_guide_handler.py` | 학술 논문 작성 가이드 (9개 체크리스트) |
| `doi_fulltext_fetcher.py` | DOI/Unpaywall 기반 전문 조회 |
| `pmc_fulltext_fetcher.py` | PMC Open Access 전문 조회 |
| `llm/base.py` | LLM Provider 인터페이스 (BaseLLMClient Protocol) |

### Key Scripts

| Script | Description |
|--------|-------------|
| `scripts/repair_isolated_papers.py` | 고립 논문 복구 (LLM 재분석 → 관계 구축, `--dry-run`, `--max-concurrent`, `--paper-ids` 지원) |
| `scripts/init_neo4j.py` | Neo4j 스키마/인덱스 초기화 |
| `scripts/enrich_graph_snomed.py` | SNOMED 코드 일괄 적용 + TREATS 백필 |
| `scripts/backfill_summary.py` | 기존 Paper에 LLM 생성 summary 소급 적용 |
| `scripts/repair_missing_chunks.py` | HAS_CHUNK 누락 Paper 복구 (`--dry-run`, `--paper-ids`, `--max-concurrent` 지원) |
| `scripts/build_ontology.py` | IS_A 계층 일괄 구축 (`--dry-run`, `--force`, `--entity-type`) |
| `scripts/repair_ontology.py` | 온톨로지 무결성 수복 (`--dry-run`, `--force`, `--entity-type`) |
| `scripts/normalize_entities.py` | 엔티티 정규화 (중복 병합, 쓰레기 정리, Outcome IS_A 링크, `--dry-run`, `--force`, `--phase`) |

### Evaluation Framework

| Module | Description |
|--------|-------------|
| `evaluation/metrics.py` | P@K, R@K, NDCG@10, MRR, ELA 메트릭 (28 tests) |
| `evaluation/baselines.py` | B1(Keyword), B2(Vector), B3(LLM Direct), B4(GraphRAG) |
| `evaluation/benchmark.py` | CLI 벤치마크 실행기 (`python -m evaluation.benchmark`) |
| `evaluation/annotator_helper.py` | Gold Standard 후보 논문 자동 검색 |
| `evaluation/import_to_neo4j.py` | PubMed 논문 + entity → Neo4j 임포트 |
| `evaluation/gold_standard/` | 29개 질문, 517편 후보, annotation 데이터 |

## Documentation

본 프로젝트는 계층적 문서 구조를 갖습니다. **CLAUDE.md가 오케스트라 파일**로서 모든 문서를 조율합니다.

### 핵심 문서 (5개) - 필수 동기화
| 문서 | 역할 | 업데이트 시점 |
|------|------|-------------|
| [CHANGELOG.md](docs/CHANGELOG.md) | 버전 히스토리 | 모든 버전 변경 시 |
| [PRD.md](docs/PRD.md) | 요구사항 정의서 | 새 기능 요구사항 추가 시 |
| [TRD_v3_GraphRAG.md](docs/TRD_v3_GraphRAG.md) | 기술 사양서 | 아키텍처/설계 변경 시 |
| [GRAPH_SCHEMA.md](docs/GRAPH_SCHEMA.md) | 노드/관계 스키마 | Graph 구조 변경 시 |
| [TERMINOLOGY_ONTOLOGY.md](docs/TERMINOLOGY_ONTOLOGY.md) | 용어체계/온톨로지 | Taxonomy, SNOMED 변경 시 |

### 운영 문서 (6개) - 일상 사용
| 문서 | 대상 |
|------|------|
| [MCP_USAGE_GUIDE.md](docs/MCP_USAGE_GUIDE.md) | Claude Desktop/Code 사용자 (10개 MCP 도구) |
| [SYSTEM_VALIDATION.md](docs/SYSTEM_VALIDATION.md) | 시스템 검증 프롬프트 모음 (전체 상태 점검) |
| [NEO4J_SETUP.md](docs/NEO4J_SETUP.md) | DevOps, 개발자 (설치/설정) |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 모든 사용자 (문제 해결) |
| [user_guide.md](docs/user_guide.md) | 최종 사용자 (Web UI) |
| [developer_guide.md](docs/developer_guide.md) | 개발자 (개발 가이드) |

### 논문 관리

논문 출판 **계획/진행상황**은 이 repo에, **실제 논문 원고**는 별도 폴더에서 관리:

| 위치 | 역할 |
|------|------|
| `docs/PUBLICATION_PLAN.md` | 출판 계획 + 진행상황 추적 |
| `evaluation/` | 벤치마크 코드, 질문, 데이터 |
| `/Users/sangminpark/OneDrive/03. Research/01. 진행중인 연구/medical_kag/` | **논문 원고 관리** |

```
medical_kag/                          # OneDrive 논문 폴더
├── CLAUDE.md                         # Writing guide 설정 + 4편 논문 정보
├── docs/                             # Writing guide 참고 문서
├── drafts/
│   ├── P1_System_Architecture/       # Paper 1: System (JMIR) — 초안 v0.1 완료
│   ├── P2_SNOMED_Ontology/           # Paper 2: SNOMED (IJMI)
│   ├── P3_Evidence_Synthesis/        # Paper 3: Evidence Chain (Spine J)
│   └── P4_Clinical_Decision_Support/ # Paper 4: CDS (Neurosurg Focus)
└── knowledge/, data/, scripts/, ...  # Writing guide 기본 구조
```

### 추가 참고
- [PUBLICATION_PLAN.md](docs/PUBLICATION_PLAN.md) - **논문 출판 계획 (4편 핵심, RAGAS 평가, 타임라인)**
- [ROADMAP.md](docs/ROADMAP.md) - **개선 로드맵 (Retrieval, Reasoning, Chunking, Evaluation TODO)**
- [QC_CHECKLIST.md](docs/QC_CHECKLIST.md) - **QC 체크리스트 (버전/문서/코드 일관성 검증)**
- [CODE_AUDIT.md](docs/CODE_AUDIT.md) - **Code Audit (보안/성능/설계 심층 분석)**
- [DATA_VALIDATION.md](docs/DATA_VALIDATION.md) - **Data Validation (Neo4j 데이터 무결성/완전성 검증)**
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - 배포 가이드
- [HOW_TO_RUN_kr.md](docs/HOW_TO_RUN_kr.md) - 실행 가이드 (한국어)
- [SCHEMA_UPDATE_GUIDE.md](docs/SCHEMA_UPDATE_GUIDE.md) - 스키마/Taxonomy 업데이트 절차
- `docs/specs/` - 기술 상세 명세
- `docs/api/` - API 레퍼런스

## Dependencies

```yaml
python: ">=3.10"
anthropic: ">=0.40.0,<1.0.0"     # Claude API
openai: ">=1.0.0,<3.0.0"         # Embeddings (text-embedding-3-large)
google-genai: ">=1.0.0,<2.0.0"   # Gemini API
neo4j: ">=5.15.0,<7.0.0"         # Graph DB
pymupdf: ">=1.23.0,<2.0.0"       # PDF
mcp: ">=1.8.0,<2.0.0"            # MCP Server
httpx: ">=0.24.0,<1.0.0"          # Async HTTP
pydantic: ">=2.0.0"              # Data validation
# Optional [ml]
sentence-transformers: ">=2.2.0,<4.0.0"  # pip install .[ml]
```
