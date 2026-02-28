# Technical Requirements Document v3 - Spine GraphRAG

> **버전**: 1.24.0 (문서 버전 동기화)
> **이전 버전**: [TRD_v2_LLM.md](TRD_v2_LLM.md)
> **최종 수정**: 2026-02-28
> **대상 도메인**: General Spine Surgery (Degenerative, Deformity, Trauma, Tumor)
>
> **⚠️ v5.2 변경사항**: SQLite (`paper_graph.db`) 완전 제거. 모든 Paper-to-Paper 관계는 Neo4j에서 관리.
> - (SQLite 완전 제거됨, v5.2)

---

## 1. 개요

### 1.1 변경 배경

v2.3 시스템(LLM 기반 KAG)에서 **Neo4j Graph DB 기반 GraphRAG**로 전환:

| 항목 | v2.3 (이전) | v3.0 (현재) |
|------|------------|-------------|
| **Graph Storage** | ~~SQLite (paper_graph.py)~~ **(v5.2에서 제거됨)** | **Neo4j** (네이티브 그래프 DB) |
| **Vector Storage** | ~~ChromaDB~~ **(v1.14.12에서 제거됨)** | **Neo4j Vector Index** (HNSW, 3072d) |
| **검색 방식** | Vector 중심 | **Hybrid (Graph + Vector)** |
| **도메인** | 의학 논문 일반 | **척추 수술 특화** |
| **관계 표현** | 평면적 (supports/contradicts) | **계층적 수술법 Taxonomy** |
| **추론** | LLM 직접 추론 | **Graph Traversal + LLM 검증** |

### 1.2 핵심 가치

1. **구조적 추론 강화**: PICO → 수술법 → 결과의 인과관계를 Graph로 명시적 표현
2. **수술법 계층화**: `TLIF → Interbody Fusion → Fusion Surgery` 관계 표현
3. **상충 결과 탐지**: Graph 관계의 p-value 속성으로 논문 간 비교 용이
4. **도메인 특화**: 척추 수술에 최적화된 스키마 (Sub-domain, Anatomy Level)

### 1.3 대상 규모

| 항목 | 값 |
|------|-----|
| 논문 수 | ~100-500개 |
| Sub-domains | Degenerative, Deformity, Trauma, Tumor, Basic Science |
| 문서당 비용 | ~$0.03-0.08 (Graph 관계 분석 포함) |
| 총 예상 비용 | ~$10-15 |

---

## 2. 시스템 아키텍처

### 2.1 Hybrid Retrieval System

```
┌─────────────────────────────────────────────────────────────────────┐
│         Claude Haiku 4.5 PDF Processor (v1.14+)                      │
│     (기본: Haiku, 폴백: Sonnet, Gemini도 지원)                        │
├─────────────────────────────────────────────────────────────────────┤
│  - LLM_PROVIDER: "claude" (기본) 또는 "gemini"                       │
│  - 기본 모델: claude-haiku-4-5-20251001                              │
│  - 폴백 모델: claude-sonnet-4-5-20250929 (토큰 초과 시)              │
│  - max_output_tokens: 8,192 (Haiku) / 16,384 (Sonnet)                │
│  ★ 핵심 기능:                                                        │
│    • PDF Vision 처리 (이미지 기반 추출)                              │
│    • 표 데이터 구조화 (TableData)                                    │
│    • 그림/차트 AI 해석 (FigureData)                                  │
│    • 합병증 데이터 추출 (ComplicationData)                           │
│    • Sub-domain 분류, Anatomy Level 추출                             │
│    • 콘텐츠 타입별 분류 (text, table, figure, key_finding)           │
│    • 자동 폴백: Haiku → Sonnet (토큰 초과 시)                        │
└─────────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Neo4j (Graph + Vector 통합)                             │
├─────────────────────────────────────────────────────────────────────┤
│ ▸ 구조적 지식 (Graph):                                               │
│   - Paper, Pathology, Anatomy, Intervention, Outcome nodes         │
│   - Relationships: STUDIES, TREATS, AFFECTS, IS_A                  │
│   - Properties: p_value, effect_size, confidence_interval          │
│                                                                     │
│ ▸ 벡터 검색 (Vector Index):                                         │
│   - HNSW Index (3072d OpenAI embeddings)                           │
│   - Paper.abstract_embedding                                       │
│   - Chunk.embedding (text, table, figure 콘텐츠)                    │
│   - 단일 Cypher 쿼리로 Graph Filter + Vector Search 통합            │
└─────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LangChain Orchestrator (신규)                     │
├─────────────────────────────────────────────────────────────────────┤
│  - LLM과 DB 간 데이터 흐름 제어                                       │
│  - Query → Cypher 변환                                               │
│  - Graph 결과 + Vector 결과 통합                                      │
│  - Response 생성                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 모듈 구조 (v3.0)

```
src/
├── llm/                              # LLM 통합 레이어 (유지)
│   ├── __init__.py
│   ├── gemini_client.py              # Gemini API 클라이언트
│   ├── prompts.py                    # 프롬프트 템플릿
│   └── cache.py                      # 결과 캐싱 (SQLite)
│
├── builder/                          # 지식 구축 모듈 (확장)
│   ├── gemini_vision_processor.py    # Vision PDF 처리기
│   ├── spine_domain_classifier.py    # ★ 신규: 척추 하위도메인 분류
│   ├── llm_section_classifier.py     # LLM 섹션 분류기
│   ├── llm_semantic_chunker.py       # LLM 의미 청킹
│   ├── llm_metadata_extractor.py     # 메타데이터 추출기 (확장)
│   ├── doi_fulltext_fetcher.py       # ★ v1.13: DOI/Unpaywall 전문 조회
│   └── pmc_fulltext_fetcher.py       # PMC Open Access 전문 조회
│
├── graph/                            # ★ 신규: Neo4j 그래프 레이어
│   ├── __init__.py
│   ├── neo4j_client.py               # Neo4j 연결 관리 + DAO 위임 (v1.22.0 분리)
│   ├── relationship_dao.py           # ★ v1.22.0: 관계 CRUD (17 methods, Neo4jClient에서 추출)
│   ├── search_dao.py                 # ★ v1.22.0: Vector/Hybrid 검색 (7 methods)
│   ├── schema_manager.py             # ★ v1.22.0: 스키마 초기화/통계/클리어 (4 methods)
│   ├── spine_schema.py               # 척추 그래프 스키마
│   ├── entity_normalizer.py          # 용어 정규화 (UBE↔BESS↔Biportal)
│   ├── relationship_builder.py       # 관계 구축
│   └── taxonomy_manager.py           # 수술법 계층 관리
│
├── knowledge/                        # 논문 관계 (마이그레이션)
│   ├── __init__.py
│   ├── paper_graph.py                # SQLite → Neo4j 마이그레이션 대상
│   ├── citation_extractor.py
│   └── relationship_reasoner.py      # Graph 기반으로 확장
│
├── solver/                           # 검색/추론 모듈 (확장)
│   ├── query_parser.py               # 자연어 → Cypher 변환
│   ├── tiered_search.py              # 계층적 검색 (유지)
│   ├── graph_search.py               # ★ 신규: Graph 검색
│   ├── hybrid_ranker.py              # ★ 신규: Graph+Vector 통합 랭킹
│   ├── multi_factor_ranker.py
│   ├── reasoner.py                   # Graph 추론 연동
│   ├── conflict_detector.py
│   └── response_generator.py
│
├── storage/                          # (Deprecated - v1.14.12)
│   ├── vector_db.py                  # ~~ChromaDB~~ (v1.14.12에서 제거됨)
│   └── graph_db.py                   # ~~Neo4j 래퍼~~ (neo4j_client.py로 대체됨)
│
├── orchestrator/                     # ★ 신규: LangChain 통합
│   ├── __init__.py
│   ├── chain_builder.py              # LangChain 체인 구성
│   ├── cypher_generator.py           # 자연어 → Cypher
│   └── response_synthesizer.py       # 통합 응답 생성
│
├── external/                         # 외부 API
│   └── pubmed_client.py
│
└── medical_mcp/                      # MCP 서버
    ├── medical_kag_server.py         # MCP 서버 메인 (Facade)
    └── handlers/                     # ★ v1.14: 11개 도메인별 핸들러 + utils
        ├── base_handler.py           # BaseHandler 공통 클래스 + safe_execute 데코레이터
        ├── pdf_handler.py            # PDF/텍스트 분석, 저장
        ├── graph_handler.py          # 수술법 계층, 논문 관계
        ├── search_handler.py         # 하이브리드 검색 (v1.14.18: intervention 검색 강화)
        ├── reasoning_handler.py      # 추론, 상충 탐지
        ├── clinical_data_handler.py  # 환자 코호트, 비용 분석
        ├── document_handler.py       # 문서 CRUD, 내보내기
        ├── pubmed_handler.py         # PubMed 검색/임포트 + DOI Fallback
        ├── citation_handler.py       # 인용 기반 초안
        ├── json_handler.py           # JSON 임포트
        ├── reference_handler.py      # ★ v1.9: 참고문헌 포맷팅 (7가지 스타일)
        ├── writing_guide_handler.py  # ★ v1.12: 학술 논문 작성 가이드 (9개 체크리스트)
        └── utils.py                  # 공유 유틸리티

web/                                   # Web UI (확장)
├── app.py
├── pages/
│   ├── 1_📄_Documents.py
│   ├── 2_🔍_Search.py                # Hybrid 검색 UI
│   ├── 3_📊_Knowledge_Graph.py       # Neo4j 시각화
│   ├── 4_✍️_Draft_Assistant.py       # 논문 작성 보조 (Graph 연동)
│   ├── 5_⚙️_Settings.py
│   ├── 6_🔬_PubMed.py
│   └── 7_🦴_Spine_Explorer.py        # ★ 신규: 척추 도메인 탐색
└── ...
```

### 2.3 MCP Server 아키텍처 (v1.19.3-1.19.4 리팩토링)

v1.19.3-1.19.4에서 `MedicalKAGServer`의 대규모 리팩토링을 수행하여 **Facade 패턴** + **BaseHandler 상속** + **Tool Registry** 구조로 전환했습니다.

#### 2.3.1 BaseHandler 패턴

모든 11개 핸들러가 `BaseHandler`를 상속합니다:

```python
class BaseHandler:
    """모든 핸들러의 공통 베이스 클래스."""
    def __init__(self, server: "MedicalKAGServer"):
        self.server = server

    @property
    def neo4j_client(self):
        """서버의 Neo4j 클라이언트에 접근."""
        return self.server.neo4j_client

    async def _require_neo4j(self) -> None:
        """Neo4j 연결 필수 확인. 미연결 시 에러."""
        ...

    async def _ensure_connected(self) -> None:
        """Neo4j 연결 확인 후 자동 연결 시도."""
        ...
```

`safe_execute` 데코레이터: 핸들러 메서드의 예외를 일관되게 처리하고 에러 응답을 표준화합니다.

```python
@safe_execute("operation_name")
async def handle_something(self, arguments: dict) -> list[TextContent]:
    ...
```

#### 2.3.2 Tool Registry 패턴

기존 420줄 `if/elif` 체인을 **딕셔너리 기반 디스패치**로 교체:

```python
class MedicalKAGServer:
    def _init_tool_dispatchers(self):
        self._tool_dispatchers: dict[str, Callable] = {
            "analyze_document":    self._dispatch_pdf,
            "search_papers":       self._dispatch_search,
            "explore_graph":       self._dispatch_graph,
            "reasoning":           self._dispatch_reasoning,
            "clinical_data":       self._dispatch_clinical,
            "manage_documents":    self._dispatch_document,
            "pubmed":              self._dispatch_pubmed,
            "citation_draft":      self._dispatch_citation,
            "import_json":         self._dispatch_json,
            "reference_format":    self._dispatch_reference,
        }

    async def call_tool(self, name: str, arguments: dict):
        dispatcher = self._tool_dispatchers.get(name)
        if dispatcher:
            return await dispatcher(arguments)
        raise ValueError(f"Unknown tool: {name}")
```

10개의 `_dispatch_*` 함수가 각 도메인 핸들러로 요청을 라우팅합니다.

#### 2.3.3 Server as Facade

`MedicalKAGServer`는 이제 **Facade** 역할만 수행합니다 (3,982줄, 기존 7,178줄에서 축소):

| 역할 | 설명 |
|------|------|
| **설정 관리** | Neo4j 연결, LLM 클라이언트, 환경 변수 |
| **핸들러 인스턴스 관리** | 11개 핸들러 초기화 및 생명주기 |
| **공유 상태** | `neo4j_client`, `_get_user_filter_clause()` 등 핸들러가 공유하는 리소스 |
| **도구 라우팅** | `_tool_dispatchers` 딕셔너리를 통한 요청 디스패치 |

모든 도메인 로직은 개별 핸들러(`handlers/`)에 위치하며, 핸들러는 `self.server`를 통해 공유 리소스에 접근합니다.

---

## 3. Neo4j Graph Schema

### 3.1 Node Types (엔티티)

```cypher
// 1. Paper - 논문 메타데이터
(:Paper {
    paper_id: STRING,           // 고유 ID
    title: STRING,
    authors: [STRING],
    year: INTEGER,
    journal: STRING,
    doi: STRING,
    pmid: STRING,
    sub_domain: STRING,         // Degenerative, Deformity, Trauma, Tumor, Basic Science
    study_design: STRING,       // RCT, Retrospective, Meta-analysis 등
    evidence_level: STRING,     // 1a, 1b, 2a, 2b, 3, 4
    sample_size: INTEGER,
    follow_up_months: INTEGER,
    created_at: DATETIME
})

// 2. Pathology - 질환/진단
(:Pathology {
    name: STRING,               // Lumbar Stenosis, AIS, Spondylolisthesis
    category: STRING,           // degenerative, deformity, trauma, tumor
    icd10_code: STRING,         // 선택적
    description: STRING
})

// 3. Anatomy - 해부학적 위치
(:Anatomy {
    name: STRING,               // L4-5, C5-6, Thoracolumbar junction
    region: STRING,             // cervical, thoracic, lumbar, sacral
    level_count: INTEGER        // 수술 레벨 수
})

// 4. Intervention - 수술/치료법
(:Intervention {
    name: STRING,               // TLIF, OLIF, UBE, Laminectomy
    full_name: STRING,          // 전체 이름
    category: STRING,           // fusion, decompression, fixation, etc.
    approach: STRING,           // anterior, posterior, lateral
    is_minimally_invasive: BOOLEAN,
    aliases: [STRING]           // 동의어 목록
})

// 5. Outcome - 결과변수
(:Outcome {
    name: STRING,               // Fusion Rate, VAS, ODI, JOA, SVA
    type: STRING,               // clinical, radiological, functional
    unit: STRING,               // %, points, mm
    direction: STRING           // higher_is_better, lower_is_better
})
```

### 3.2 Relationship Types (관계)

```cypher
// 논문 → 질환 연구
(Paper)-[:STUDIES {
    primary: BOOLEAN            // 주 연구 대상 여부
}]->(Pathology)

// 질환 → 해부학 위치
(Pathology)-[:LOCATED_AT]->(Anatomy)

// 논문 → 수술법 조사
(Paper)-[:INVESTIGATES {
    is_comparison: BOOLEAN      // 비교 연구 여부
}]->(Intervention)

// 수술법 → 질환 치료
(Intervention)-[:TREATS {
    indication: STRING          // 적응증
}]->(Pathology)

// 수술법 → 결과 (핵심 추론 경로)
(Intervention)-[:AFFECTS {
    source_paper: STRING,       // 출처 논문 ID
    value: STRING,              // 측정값 (예: "85.2%")
    value_control: STRING,      // 대조군 값 (있는 경우)
    p_value: FLOAT,             // 통계적 유의성
    effect_size: STRING,        // 효과 크기
    confidence_interval: STRING,// 95% CI
    is_significant: BOOLEAN,
    direction: STRING           // improved, worsened, unchanged
}]->(Outcome)

// 수술법 계층 구조 (Taxonomy)
(Intervention)-[:IS_A {
    level: INTEGER              // 계층 깊이
}]->(Intervention)
// 예: (TLIF)-[:IS_A]->(Interbody Fusion)-[:IS_A]->(Fusion Surgery)
//     (PSLD)-[:IS_A]->(Endoscopic Surgery)-[:IS_A]->(Decompression)

// 논문 간 관계
(Paper)-[:CITES]->(Paper)
(Paper)-[:SUPPORTS {
    confidence: FLOAT,
    evidence: STRING
}]->(Paper)
(Paper)-[:CONTRADICTS {
    confidence: FLOAT,
    evidence: STRING,
    conflict_point: STRING
}]->(Paper)
```

### 3.3 수술법 Taxonomy 예시

```cypher
// Fusion Surgery Hierarchy
CREATE (fusion:Intervention {name: "Fusion Surgery", category: "fusion"})
CREATE (ibf:Intervention {name: "Interbody Fusion", category: "fusion"})
CREATE (plf:Intervention {name: "Posterolateral Fusion", category: "fusion"})

CREATE (tlif:Intervention {name: "TLIF", full_name: "Transforaminal Lumbar Interbody Fusion"})
CREATE (plif:Intervention {name: "PLIF", full_name: "Posterior Lumbar Interbody Fusion"})
CREATE (alif:Intervention {name: "ALIF", full_name: "Anterior Lumbar Interbody Fusion"})
CREATE (olif:Intervention {name: "OLIF", full_name: "Oblique Lumbar Interbody Fusion"})
CREATE (llif:Intervention {name: "LLIF", full_name: "Lateral Lumbar Interbody Fusion"})

CREATE (ibf)-[:IS_A {level: 1}]->(fusion)
CREATE (plf)-[:IS_A {level: 1}]->(fusion)
CREATE (tlif)-[:IS_A {level: 2}]->(ibf)
CREATE (plif)-[:IS_A {level: 2}]->(ibf)
CREATE (alif)-[:IS_A {level: 2}]->(ibf)
CREATE (olif)-[:IS_A {level: 2}]->(ibf)
CREATE (llif)-[:IS_A {level: 2}]->(ibf)

// Decompression Surgery Hierarchy
CREATE (decomp:Intervention {name: "Decompression Surgery", category: "decompression"})
CREATE (endo:Intervention {name: "Endoscopic Surgery", category: "decompression", is_minimally_invasive: true})
CREATE (open:Intervention {name: "Open Surgery", category: "decompression"})

CREATE (ube:Intervention {name: "UBE", full_name: "Unilateral Biportal Endoscopic", aliases: ["BESS", "Biportal"]})
CREATE (feld:Intervention {name: "FELD", full_name: "Full-Endoscopic Lumbar Discectomy"})
CREATE (psld:Intervention {name: "PSLD", full_name: "Percutaneous Stenoscopic Lumbar Decompression"})

CREATE (endo)-[:IS_A {level: 1}]->(decomp)
CREATE (open)-[:IS_A {level: 1}]->(decomp)
CREATE (ube)-[:IS_A {level: 2}]->(endo)
CREATE (feld)-[:IS_A {level: 2}]->(endo)
CREATE (psld)-[:IS_A {level: 2}]->(endo)
```

---

## 4. 데이터 흐름

### 4.1 논문 처리 파이프라인 (v2.0 확장 + Neo4j 자동 통합)

```
PDF 입력
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│          Gemini 2.5 Flash PDF Processor v2.0 (확장)                  │
├─────────────────────────────────────────────────────────────────────┤
│  기존 추출:                                                          │
│  - 텍스트, 섹션, 청크, 메타데이터, PICO, 통계, 키워드                 │
│                                                                      │
│  ★ v2.0 신규 추출:                                                   │
│  - 구조화된 표 데이터 (TableData: headers, rows, markdown)           │
│  - 그림/차트 AI 해석 (FigureData: type, description, key_findings)  │
│  - 합병증 데이터 (ComplicationData: name, incidence, severity)       │
│  - 콘텐츠 타입별 분류 (text, table, figure, key_finding)             │
│                                                                      │
│  ★ 척추 특화 메타데이터 (SpineMetadata 확장):                        │
│  - sub_domain: Degenerative | Deformity | Trauma | Tumor            │
│  - anatomy_level: "L4-5", "C5-7", "T10-L2"                          │
│  - interventions: ["TLIF", "PLIF"]                                  │
│  - outcomes: [{name, value, p_value, is_significant, direction}]    │
│  - complications: [{name, incidence, severity}]                     │
│  - follow_up_period: "24 months"                                    │
│  - main_conclusion: "핵심 결론 1문장"                                │
└─────────────────────────────────────────────────────────────────────┘
    │
    ├───────────────────┬──────────────────────┬─────────────────────┐
    ▼                   ▼                      ▼                     ▼
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐  ┌──────────────┐
│ Neo4j       │  │ Neo4j Graph     │  │ Entity         │  │ Relationship │
│ Vector Index│  │ (Structure)     │  │ Normalizer     │  │ Builder      │
├─────────────┤  ├─────────────────┤  ├────────────────┤  ├──────────────┤
│ Chunk 임베딩 │  │ ★ 자동 생성:     │  │ 용어 통일:      │  │ ★ 신규 통합:  │
│ (3072d)     │  │                 │  │ UBE ↔ BESS    │  │ PDF 업로드 시 │
│ HNSW 검색    │  │ 1. Paper 노드   │  │ Biportal      │  │ Neo4j에 자동  │
│ 표/그림 포함  │  │ 2. STUDIES →    │  │               │  │ 관계 구축:    │
│             │  │    Pathology    │  │ TLIF, PLIF    │  │              │
│             │  │ 3. INVESTIGATES │  │ OLIF, etc     │  │ - Paper →    │
│             │  │    → Intervention│  │               │  │   Pathology  │
│             │  │ 4. AFFECTS →    │  │ VAS, ODI      │  │ - Paper →    │
│             │  │    Outcome      │  │ JOA, etc      │  │   Intervention│
│             │  │    (with stats) │  │               │  │ - Intervention│
│             │  │                 │  │               │  │   → Outcome  │
└─────────────┘  └─────────────────┘  └────────────────┘  └──────────────┘
                         │                                        │
                         └────────────────────────────────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────────────────┐
                                 │  Relationship Reasoner (확장)        │
                                 ├─────────────────────────────────────┤
                                 │  1. 기존 논문과 PICO/키워드 유사도    │
                                 │  2. Graph 기반 관계 탐색             │
                                 │  3. LLM으로 supports/contradicts 판정 │
                                 │  4. 관계 저장 (Neo4j)                │
                                 └─────────────────────────────────────┘
```

### 4.1.1 서지 보강 파이프라인 (v1.16.0 — PubMed + DOI Fallback)

논문 처리 시 서지 정보를 항상 3단계 fallback 체인으로 보강합니다.

```
PDF/Text 메타데이터 (DOI, Title, Authors)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: PubMed Enrichment (confidence: 1.0)                    │
│  - PMID, DOI, MeSH Terms, Publication Types, Abstract           │
│  - source: "pubmed"                                             │
│  → 성공 시 → Paper 노드 생성 + 임베딩                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 실패 시
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: DOI/Crossref Fallback (confidence: 0.8)                │
│  A. DOI 직접 조회: doi_fulltext_fetcher.get_metadata_only()      │
│  B. Crossref 서지 검색: search_by_bibliographic(title, authors)  │
│  - DOI, Title, Authors, Journal, Year, Abstract                 │
│  - source: "crossref"                                           │
│  → BibliographicMetadata.from_doi_metadata() 변환               │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 실패 시
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Basic Citation (confidence: 0.3)                       │
│  - Title, Authors, Year만으로 최소 Paper 노드 생성               │
│  - source: "citation_basic"                                     │
│  - MeSH terms, keywords 없음                                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Paper 노드 + CITES 관계 항상 생성 (어떤 경우든)
```

**적용 범위**:

- `medical_kag_server.py`: PDF/텍스트 처리 시 PubMed → DOI fallback
- `important_citation_processor.py`: 인용 논문 처리 시 3단계 fallback 체인
- `doi_fulltext_fetcher.py`: Crossref API `query.bibliographic` 검색
- `pubmed_enricher.py`: `DOIMetadata → BibliographicMetadata` 변환

### 4.2 검색 파이프라인 (Hybrid)

```
사용자 쿼리: "ASD 수술에서 PJK 예방 전략은?"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Query Parser (확장)                               │
├─────────────────────────────────────────────────────────────────────┤
│  1. 의도 파악: evidence_search (근거 기반 검색)                       │
│  2. 엔티티 추출:                                                     │
│     - Pathology: "ASD" (Adult Spinal Deformity)                     │
│     - Outcome: "PJK" (Proximal Junctional Kyphosis)                 │
│     - Intent: "prevention strategies"                               │
│  3. Cypher 쿼리 생성                                                 │
└─────────────────────────────────────────────────────────────────────┘
    │
    ├─────────────────────┬────────────────────────┐
    ▼                     ▼                        ▼
┌─────────────────┐ ┌─────────────────────┐ ┌──────────────────────┐
│ Graph Search    │ │ Vector Search       │ │ Context Retrieval    │
├─────────────────┤ ├─────────────────────┤ ├──────────────────────┤
│ Cypher:         │ │ Neo4j Vector Index: │ │ Graph Traversal:     │
│ MATCH           │ │ - HNSW 검색 (3072d) │ │ - Paper-Chunk 관계   │
│ (i:Intervention)│ │ - "ASD" 관련 청크    │ │ - Discussion 섹션     │
│ -[a:AFFECTS]->  │ │ - Semantic 유사도    │ │ - Background 정보     │
│ (o:Outcome      │ │   기반 검색          │ │                      │
│  {name:"PJK"})  │ │                     │ │                      │
│ WHERE           │ │                     │ │                      │
│ a.direction =   │ │                     │ │                      │
│ 'improved'      │ │                     │ │                      │
│ RETURN i, a, o  │ │                     │ │                      │
└─────────────────┘ └─────────────────────┘ └──────────────────────┘
    │                     │                        │
    └─────────────────────┴────────────────────────┘
                          │
                          ▼
                 ┌─────────────────────────────────────┐
                 │       Hybrid Ranker (신규)           │
                 ├─────────────────────────────────────┤
                 │  1. Graph 결과 (구조화된 근거):       │
                 │     - Intervention → Outcome 관계   │
                 │     - p-value, effect size          │
                 │  2. Vector 결과 (문맥):              │
                 │     - 설명, 배경, 논의               │
                 │  3. 통합 점수 계산                   │
                 │  4. Evidence Level 가중치           │
                 └─────────────────────────────────────┘
                          │
                          ▼
                 ┌─────────────────────────────────────┐
                 │    Response Generator (확장)         │
                 ├─────────────────────────────────────┤
                 │  Graph 근거 + Vector 문맥 통합        │
                 │                                      │
                 │  "ASD 수술의 PJK 발생률을 줄이기 위해  │
                 │  다양한 시도가 있었습니다.            │
                 │                                      │
                 │  [Graph 근거] 연구 A에 따르면         │
                 │  Tethering은 PJK 발생률을 15%까지    │
                 │  낮췄으며 (p=0.02)                   │
                 │                                      │
                 │  [Vector 문맥] 이는 후방 인대 복합체를 │
                 │  보존하기 때문입니다..."              │
                 └─────────────────────────────────────┘
```

---

## 5. Gemini Vision Processor v2.0 상세

### 5.1 주요 변경사항

#### 5.1.1 토큰 최적화
- **full_text 필드 제거**: 전체 텍스트 저장 제거로 토큰 사용량 30-50% 절감
- **청크 기반 접근**: 구조화된 청크만 저장하여 효율성 향상

#### 5.1.2 신규 데이터 클래스

```python
@dataclass
class TableData:
    """표 데이터 구조화."""
    table_id: str           # Table 1, Table 2, etc.
    caption: str            # 표 제목
    headers: list[str]      # 컬럼 헤더
    rows: list[list[str]]   # 2차원 데이터 배열
    markdown: str           # 마크다운 형식 표
    interpretation: str     # AI가 해석한 표의 의미

@dataclass
class FigureData:
    """그림/차트 데이터."""
    figure_id: str              # Figure 1, Fig. 2, etc.
    caption: str                # 그림 제목
    figure_type: str            # chart, xray, mri, flowchart, kaplan_meier, etc.
    description: str            # AI가 해석한 그림 내용
    key_findings: list[str]     # 그림에서 추출한 핵심 발견

@dataclass
class ComplicationData:
    """합병증 데이터."""
    name: str                   # dural tear, infection, nerve injury, etc.
    incidence_intervention: str # 시술군 발생률
    incidence_control: str      # 대조군 발생률
    p_value: str               # 통계적 유의성
    severity: str              # minor, major, revision_required
```

#### 5.1.3 ExtractedChunk 확장

```python
@dataclass
class ExtractedChunk:
    """추출된 청크 v2.0."""
    content: str
    content_type: str          # ★ 신규: text, table, figure, key_finding
    section_type: str
    tier: str

    # ★ 신규 필드
    table_data: Optional[TableData] = None      # 표 청크인 경우
    figure_data: Optional[FigureData] = None    # 그림 청크인 경우

    # 기존 필드
    topic_summary: str = ""
    keywords: list[str] = field(default_factory=list)
    is_key_finding: bool = False
    pico: Optional[PICOData] = None
    statistics: Optional[StatisticsData] = None
```

#### 5.1.4 SpineMetadata 확장

```python
@dataclass
class SpineMetadata:
    """척추 특화 메타데이터 v2.0."""
    # 기존 필드
    sub_domain: str
    pathology: list[str]
    anatomy_level: str
    interventions: list[str]
    outcomes: list[ExtractedOutcome]

    # ★ v2.0 신규 필드
    complications: list[ComplicationData] = field(default_factory=list)
    follow_up_period: str = ""              # "24 months", "minimum 1 year"
    sample_size: int = 0
    main_conclusion: str = ""               # 논문의 핵심 결론 1문장
```

#### 5.1.5 ExtractedOutcome 확장

```python
@dataclass
class ExtractedOutcome:
    """추출된 결과변수 (확장)."""
    name: str
    category: str = ""          # pain, function, radiologic, complication, satisfaction

    # ★ 결과값 (v2.0 확장)
    value_intervention: str = ""
    value_control: str = ""
    value_difference: str = ""

    # ★ 통계 (v2.0 확장)
    p_value: str = ""
    confidence_interval: str = ""
    effect_size: str = ""

    # ★ 시점 (v2.0 신규)
    timepoint: str = ""         # preop, postop, 1mo, 6mo, 1yr, final

    # ★ 해석 (v2.0 신규)
    is_significant: bool = False
    direction: str = ""         # improved, worsened, unchanged
```

#### 5.1.6 JSON Schema 개선

**Enum 필드에서 빈 문자열 제거**:
- Gemini API 호환성을 위해 모든 enum 필드에서 빈 문자열(`""`) 제거
- 필수 값 없이 선택적 분류 가능하도록 `"not-applicable"`, `"other"` 추가

```python
# Before (v1.x)
"direction": {
    "type": "STRING",
    "enum": ["improved", "worsened", "unchanged", ""]  # 빈 문자열 문제
}

# After (v2.0)
"direction": {
    "type": "STRING",
    "enum": ["improved", "worsened", "unchanged", "not-applicable"]
}
```

### 5.2 Neo4j 자동 통합 (MCP Server)

#### 5.2.1 통합 아키텍처

PDF 업로드 시 다음이 자동 실행됩니다:

```python
# medical_kag_server.py의 add_pdf 도구
async def add_pdf(pdf_path: str):
    # 1. Claude Haiku Vision 처리
    result = await processor.process_pdf(pdf_path)

    # 2. Neo4j에 벡터 + 그래프 자동 구축
    if neo4j_client:
        # SpineMetadata 추론
        spine_metadata = _infer_spine_metadata_from_chunks(
            result.metadata,
            result.chunks
        )

        # RelationshipBuilder 호출
        await relationship_builder.build_from_paper(
            paper_id=doc_id,
            metadata=result.metadata,
            spine_metadata=spine_metadata,
            chunks=result.chunks
        )
```

#### 5.2.2 _infer_spine_metadata_from_chunks() 함수

Vision processor가 SpineMetadata를 완전히 추출하지 못한 경우를 위한 폴백 로직:

```python
def _infer_spine_metadata_from_chunks(
    metadata: ExtractedMetadata,
    chunks: list[ExtractedChunk]
) -> GraphSpineMetadata:
    """청크에서 척추 메타데이터 추론.

    Vision processor의 spine 메타데이터를 우선 사용하고,
    부족한 부분은 청크의 keywords, PICO에서 추출.
    """
    # 1. Vision processor 메타데이터 우선 사용
    spine = metadata.spine if hasattr(metadata, 'spine') else None

    # 2. 청크에서 추가 정보 추출
    interventions = set()
    pathologies = set()
    outcomes = []
    anatomy_levels = set()

    for chunk in chunks:
        # 키워드 매칭 (알려진 수술법/질환 목록 사용)
        if chunk.keywords:
            for kw in chunk.keywords:
                if matches_intervention(kw):
                    interventions.add(normalize_name(kw))
                if matches_pathology(kw):
                    pathologies.add(normalize_name(kw))

        # PICO에서 추출
        if chunk.pico and chunk.pico.intervention:
            interventions.update(extract_interventions(chunk.pico.intervention))

        # Anatomy levels 정규표현식 추출
        levels = re.findall(r'\b([LCT]\d+(?:-[LCT]?\d+)?)\b', chunk.content)
        anatomy_levels.update(levels)

    return GraphSpineMetadata(
        sub_domain=spine.sub_domain if spine else "",
        anatomy_levels=list(anatomy_levels)[:5],
        pathologies=list(pathologies)[:5],
        interventions=list(interventions)[:5],
        outcomes=outcomes[:10]
    )
```

#### 5.2.3 Import 경로 호환성

MCP 서버와 다양한 실행 환경 호환을 위한 try/except 절대 import:

```python
# relationship_builder.py
try:
    from src.builder.gemini_vision_processor import (
        ExtractedMetadata,
        ExtractedChunk,
        PICOData,
        StatisticsData,
    )
except ImportError:
    try:
        from builder.gemini_vision_processor import (
            ExtractedMetadata,
            ExtractedChunk,
            PICOData,
            StatisticsData,
        )
    except ImportError:
        # Fallback: define minimal stubs
        ExtractedMetadata = None
        ExtractedChunk = None
```

#### 5.2.4 RelationshipBuilder 통합 과정

```python
# relationship_builder.py
async def build_from_paper(
    paper_id: str,
    metadata: ExtractedMetadata,
    spine_metadata: SpineMetadata,
    chunks: list[ExtractedChunk]
) -> BuildResult:
    """논문으로부터 전체 그래프 구축."""

    # 1. Paper 노드 생성
    await create_paper_node(paper_id, metadata, spine_metadata)

    # 2. Paper → Pathology (STUDIES) 관계
    await create_studies_relations(paper_id, spine_metadata.pathologies)

    # 3. Paper → Intervention (INVESTIGATES) 관계
    await create_investigates_relations(paper_id, spine_metadata.interventions)

    # 4. Intervention → Outcome (AFFECTS) 관계 (통계 포함)
    outcomes = _extract_outcomes_from_chunks(chunks, spine_metadata)
    for intervention in spine_metadata.interventions:
        await create_affects_relations(intervention, outcomes, paper_id)

    # 5. Intervention → Taxonomy 연결 (IS_A 관계)
    for intervention in spine_metadata.interventions:
        await link_intervention_to_taxonomy(intervention)
```

### 5.3 수정된 파일 목록

| 파일 | 변경 사항 |
|------|----------|
| `src/builder/gemini_vision_processor.py` | v2.0 업그레이드: full_text 제거, TableData/FigureData/ComplicationData 추가, SpineMetadata 확장 |
| `src/graph/relationship_builder.py` | Import 경로 호환성 개선 (try/except 절대 import) |
| `src/medical_mcp/medical_kag_server.py` | Neo4j 자동 통합: _infer_spine_metadata_from_chunks() 추가, RelationshipBuilder 호출 |
| `src/solver/graph_search.py` | (기존 파일 유지) |
| `src/orchestrator/cypher_generator.py` | (기존 파일 유지) |
| `src/orchestrator/__init__.py` | (기존 파일 유지) |

---

## 6. 척추 특화 기능

### 6.1 Sub-domain 분류 스키마

```python
SPINE_SUBDOMAIN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "sub_domain": {
            "type": "STRING",
            "enum": ["Degenerative", "Deformity", "Trauma", "Tumor", "Basic Science"],
            "description": "척추 질환의 주요 분류"
        },
        "pathology": {
            "type": "STRING",
            "description": "구체적 질환명 (예: Lumbar Stenosis, AIS, Burst Fracture)"
        },
        "anatomy_level": {
            "type": "STRING",
            "description": "수술 레벨 (예: L4-5, C5-6, T10-L2)"
        },
        "interventions": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "수술법 목록 (정규화된 이름)"
        },
        "outcomes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "value_intervention": {"type": "STRING"},
                    "value_control": {"type": "STRING"},
                    "p_value": {"type": "STRING"}
                }
            }
        }
    },
    "required": ["sub_domain", "pathology", "anatomy_level", "interventions"]
}
```

### 6.2 도메인별 중요 변수

```yaml
Degenerative:
  primary_outcomes:
    - VAS (back, leg)
    - ODI
    - Fusion Rate
    - Complication Rate
  secondary_outcomes:
    - EQ-5D
    - SF-36
    - Reoperation Rate

Deformity:
  primary_outcomes:
    - Cobb Angle (correction)
    - SVA (Sagittal Vertical Axis)
    - PI-LL mismatch
    - PJK incidence
  secondary_outcomes:
    - SRS-22
    - ODI
    - Pseudoarthrosis Rate

Trauma:
  primary_outcomes:
    - Kyphotic Angle
    - Neurological Recovery (ASIA grade)
    - Fusion Rate
  secondary_outcomes:
    - VAS
    - Hardware Failure Rate

Tumor:
  primary_outcomes:
    - Survival Rate
    - Local Recurrence
    - Neurological Status
  secondary_outcomes:
    - Quality of Life
    - Ambulatory Status
```

### 6.3 용어 정규화 매핑

```python
INTERVENTION_ALIASES = {
    # Endoscopic techniques
    "UBE": ["BESS", "Biportal", "Unilateral Biportal Endoscopic", "Biportal Endoscopic"],
    "FELD": ["PELD", "FEID", "Full-Endoscopic Discectomy"],

    # Fusion techniques
    "TLIF": ["Transforaminal Interbody Fusion", "TLIF surgery"],
    "OLIF": ["Oblique Interbody Fusion", "OLIF51", "ATP approach"],
    "LLIF": ["XLIF", "DLIF", "Lateral Interbody Fusion"],

    # Deformity correction
    "VCR": ["Vertebral Column Resection"],
    "PSO": ["Pedicle Subtraction Osteotomy"],
    "SPO": ["Smith-Petersen Osteotomy", "Ponte Osteotomy"],
}

OUTCOME_ALIASES = {
    "VAS": ["Visual Analog Scale", "Pain Score"],
    "ODI": ["Oswestry Disability Index", "Oswestry Score"],
    "JOA": ["Japanese Orthopaedic Association", "JOA Score"],
    "SVA": ["Sagittal Vertical Axis", "C7 Plumb Line"],
}
```

---

## 7. 코드 마이그레이션 계획

### 7.1 유지 모듈 (변경 없음)

```
src/llm/claude_client.py           # Claude API 클라이언트 유지
src/llm/gemini_client.py           # Gemini API 클라이언트 유지
src/cache/llm_cache.py             # 캐싱 유지
src/external/pubmed_client.py      # PubMed 유지
src/builder/unified_pdf_processor.py  # PDF 처리 유지 (스키마 확장)
```

### 7.2 확장 모듈

| 기존 모듈 | 변경 사항 |
|----------|----------|
| `builder/gemini_vision_processor.py` | Sub-domain, Anatomy 추출 추가 |
| `builder/llm_metadata_extractor.py` | 수술법/결과 정규화 추가 |
| `knowledge/relationship_reasoner.py` | Neo4j 연동 |
| `solver/query_parser.py` | Cypher 생성 추가 |
| `solver/reasoner.py` | Graph 추론 연동 |
| `medical_mcp/medical_kag_server.py` | 신규 도구 추가 |

### 7.3 신규 모듈

| 모듈 | 역할 |
|------|------|
| `graph/neo4j_client.py` | Neo4j 연결 관리 |
| `graph/spine_schema.py` | 그래프 스키마 정의 |
| `graph/entity_normalizer.py` | 용어 정규화 |
| `graph/relationship_builder.py` | 관계 구축 |
| `graph/taxonomy_manager.py` | 수술법 계층 관리 |
| `solver/graph_search.py` | Graph 검색 |
| `solver/hybrid_ranker.py` | 통합 랭킹 |
| `orchestrator/chain_builder.py` | LangChain 체인 |
| `orchestrator/cypher_generator.py` | Cypher 생성 |

### 7.4 삭제/대체 모듈

| 모듈 | 상태 |
|------|------|
| `knowledge/paper_graph.py` | **v5.2에서 deprecated** - Neo4j로 완전 마이그레이션 완료 |

---

## 8. 의존성

### 8.1 requirements.txt (현재 v1.19.4)

```
# Neo4j (Single Store)
neo4j>=5.15.0                     # Neo4j Python Driver (Graph + Vector)

# LLM Integration
anthropic>=0.40.0                 # Claude Haiku 4.5 / Sonnet (Primary)
openai>=1.0.0                     # OpenAI Embeddings (text-embedding-3-large)
google-genai>=1.0.0               # Gemini API (google.genai)

# PDF Processing
PyMuPDF>=1.23.0

# Web / HTTP
requests>=2.31.0
aiohttp>=3.9.0

# 기본 의존성
pydantic>=2.0
python-dotenv>=1.0.0
nest-asyncio>=1.6.0               # Async event loop nesting
```

**주의**: ~~chromadb>=0.4.0~~ (v1.14.12에서 제거됨)

### 8.2 인프라 요구사항

```yaml
# Neo4j 설정 (docker-compose.yml)
services:
  neo4j:
    image: neo4j:5.26-community
    ports:
      - "7474:7474"    # Browser
      - "7687:7687"    # Bolt
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_PLUGINS=["apoc"]
    volumes:
      - neo4j_data:/data

# 또는 Neo4j Aura (클라우드) 사용 가능
```

---

## 9. 활용 시나리오

### 9.1 근거 기반 논문 작성

**요청**: "Introduction 작성해줘. 주제는 ASD 수술에서 PJK 예방 전략이야."

**시스템 동작**:
1. Graph에서 `(Intervention)-[:AFFECTS {direction:'improved'}]->(Outcome {name:'PJK'})` 검색
2. Vector DB에서 관련 논문들의 Background 문단 검색
3. 통합:

```
성인 척추 변형 수술의 주요 합병증인 PJK를 줄이기 위해 다양한
시도가 있었습니다.

[Graph 근거] 연구 A에 따르면 Tethering은 PJK 발생률을 15%까지
낮췄으며(p=0.02),

[Vector 문맥] 이는 후방 인대 복합체를 보존하기 때문입니다...
```

### 9.2 상충 결과 분석

**요청**: "OLIF가 간접 감압에 효과적인가? 논란이 되는 부분은?"

**시스템 동작**:
1. Graph에서 `(OLIF)-[:AFFECTS]->(Canal Area)` 관계 검색
2. p_value < 0.05 논문(효과 있음)과 그렇지 않은 논문 분류
3. 분석:

```
[효과 있음] 대다수 연구는 유의한 면적 증가를 보고합니다.
- Study A: 35% 증가 (p<0.001)
- Study B: 28% 증가 (p=0.003)

[제한적 효과] 심한 협착증 환자군에서는:
- Study C: 12% 증가 (p=0.08, NS)
- 환자 선택 기준이 중요한 것으로 보입니다.
```

### 9.3 수술법 계층 탐색

**요청**: "Fusion 수술의 종류와 각각의 적응증을 알려줘"

**시스템 동작**:
```cypher
MATCH (fusion:Intervention {name: 'Fusion Surgery'})<-[:IS_A*1..3]-(sub)
OPTIONAL MATCH (sub)-[:TREATS]->(path:Pathology)
RETURN sub.name, sub.full_name, collect(path.name) as indications
ORDER BY sub.name
```

---

## 10. 개발 로드맵

### Phase 1: Pilot (1-2주)
- [ ] 척추 분야별 대표 논문 5개 선정
- [ ] Gemini 파싱 테스트 (Sub-domain, Anatomy)
- [ ] Neo4j 로컬 설치 및 기본 스키마 생성

### Phase 2: Graph Construction (2-4주)
- [ ] `neo4j_client.py` 구현
- [ ] `entity_normalizer.py` 구현 (용어 통일)
- [ ] 기존 논문 50-100개 마이그레이션
- [ ] Taxonomy 초기 데이터 입력

### Phase 3: Hybrid Search (4-6주)
- [ ] `graph_search.py` 구현
- [ ] `cypher_generator.py` 구현
- [ ] `hybrid_ranker.py` 구현
- [ ] 기존 solver 모듈 연동

### Phase 4: Application (6-8주)
- [ ] Web UI 확장 (Spine Explorer)
- [ ] 논문 작성 보조 기능 연동
- [ ] MCP 서버 신규 도구 추가
- [ ] 전체 테스트 및 최적화

---

## 11. v3.1 Reasoning & Intelligence 로드맵 (계획)

> **상태**: 계획 단계 | **목표 완료**: 4주

### 11.1 개요

v3.0 시스템을 기반으로 추론 능력과 지능형 기능을 강화하는 업그레이드입니다.
온톨로지 기반 추론 패턴을 Neo4j/Cypher로 구현하고, 최신 RAG 기술을 통합합니다.

#### 핵심 목표

| 목표 | 설명 | 기대 효과 |
|------|------|----------|
| **퍼지 매칭** | Entity Normalizer 개선 | 용어 인식률 95%+ |
| **Cypher 추론** | 그래프 기반 논리 추론 | Ontology 수준의 추론 |
| **상충 탐지** | 연구 결과 갈등 자동 탐지 | 근거 신뢰성 향상 |
| **근거 합성** | 메타분석 수준 요약 | 종합적 의사결정 지원 |

### 11.2 Phase 1: 코드 품질 개선 (1주)

#### 11.2.1 Entity Normalizer 퍼지 매칭

**현재 문제점**:
```python
# entity_normalizer.py - 현재 구현
# 단순 substring 매칭 사용
if alias_lower in text_lower or text_lower in alias_lower:
    ratio = min(len(text_lower), len(alias_lower)) / max(...)
```

**개선 방향**:
```python
# ★ 신규: Edit Distance 기반 퍼지 매칭
from rapidfuzz import fuzz, process

class EnhancedEntityNormalizer:
    """개선된 퍼지 매칭 Entity Normalizer."""

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._alias_map = self._build_comprehensive_alias_map()

    def normalize_intervention(self, text: str) -> NormalizationResult:
        """퍼지 매칭으로 수술법 정규화."""
        # 1. 정확 매칭 우선
        if exact := self._exact_match(text):
            return NormalizationResult(exact, confidence=1.0, method="exact")

        # 2. 토큰 기반 매칭 (단어 순서 무관)
        if token := self._token_match(text):
            return NormalizationResult(token.canonical, token.confidence, method="token")

        # 3. Edit Distance 매칭
        if fuzzy := self._fuzzy_match(text):
            return NormalizationResult(fuzzy.canonical, fuzzy.confidence, method="fuzzy")

        return NormalizationResult(text, confidence=0.0, method="none")

    def _fuzzy_match(self, text: str) -> Optional[FuzzyResult]:
        """rapidfuzz 기반 유사도 매칭."""
        all_aliases = list(self._alias_map.keys())
        matches = process.extract(text, all_aliases, scorer=fuzz.WRatio, limit=3)

        if matches and matches[0][1] >= self.threshold * 100:
            alias, score, _ = matches[0]
            return FuzzyResult(
                canonical=self._alias_map[alias],
                confidence=score / 100,
                matched_alias=alias
            )
        return None

    def _token_match(self, text: str) -> Optional[TokenResult]:
        """토큰 기반 매칭 (단어 순서 무관).

        예: "Transforaminal Interbody Lumbar Fusion" ↔ "Lumbar Interbody Fusion Transforaminal"
        """
        text_tokens = set(self._tokenize(text))
        best_match = None
        best_overlap = 0

        for alias, canonical in self._alias_map.items():
            alias_tokens = set(self._tokenize(alias))
            overlap = len(text_tokens & alias_tokens) / max(len(text_tokens), len(alias_tokens))

            if overlap > best_overlap and overlap >= 0.7:
                best_overlap = overlap
                best_match = TokenResult(canonical, overlap, alias)

        return best_match

# 커버해야 할 변형 예시
EXTENDED_ALIASES = {
    "TLIF": [
        "TLIF", "T-LIF", "Trans-LIF",
        "Transforaminal Lumbar Interbody Fusion",
        "Transforaminal Interbody Fusion",
        "Trans-foraminal LIF",
        "transforaminal lumbar fusion",  # 대소문자 무관
    ],
    "UBE": [
        "UBE", "U.B.E.", "Uniportal Biportal Endoscopic",
        "Biportal Endoscopic", "BESS", "B.E.S.S.",
        "Biportal Endoscopic Spine Surgery",
        "Unilateral Biportal", "bi-portal endoscopic",
    ],
    # ... 더 많은 변형
}
```

**의존성 추가**:
```
# requirements.txt
rapidfuzz>=3.0.0          # 퍼지 매칭
python-Levenshtein>=0.23  # 성능 최적화
```

#### 11.2.2 Direction Determination 개선

**현재 문제점**:
- outcome 값이 있어도 direction이 빈 문자열로 추출되는 경우 존재
- "higher_is_better" / "lower_is_better" 기준이 하드코딩됨

**개선 방향**:
```python
# direction_determiner.py (신규 모듈)

class DirectionDeterminer:
    """결과 방향 결정 로직."""

    # 결과변수별 해석 규칙
    OUTCOME_RULES = {
        # Pain scores (lower is better)
        "VAS": {"direction_logic": "lower_is_better", "scale": [0, 10]},
        "NRS": {"direction_logic": "lower_is_better", "scale": [0, 10]},

        # Function scores (higher is better for most)
        "ODI": {"direction_logic": "lower_is_better", "scale": [0, 100]},
        "JOA": {"direction_logic": "higher_is_better", "scale": [0, 29]},
        "SF-36": {"direction_logic": "higher_is_better", "scale": [0, 100]},

        # Radiologic (context-dependent)
        "fusion_rate": {"direction_logic": "higher_is_better", "unit": "%"},
        "subsidence": {"direction_logic": "lower_is_better", "unit": "mm"},
        "lordosis": {"direction_logic": "context_dependent"},  # 교정량에 따라

        # Complications (lower is better)
        "complication_rate": {"direction_logic": "lower_is_better"},
        "revision_rate": {"direction_logic": "lower_is_better"},
    }

    def determine_direction(
        self,
        outcome_name: str,
        value_intervention: str,
        value_control: Optional[str],
        p_value: Optional[float]
    ) -> str:
        """결과 방향 결정.

        Returns:
            "improved" | "worsened" | "unchanged" | "unknown"
        """
        rule = self._get_rule(outcome_name)

        if rule["direction_logic"] == "context_dependent":
            return self._determine_context_dependent(outcome_name, value_intervention, value_control)

        # 대조군 비교가 있는 경우
        if value_control:
            return self._compare_with_control(rule, value_intervention, value_control, p_value)

        # 단일 값인 경우 (pre/post 비교 등)
        return self._assess_single_value(rule, value_intervention)
```

#### 11.2.3 Hybrid Ranker 동적 가중치

**개선 방향**:
```python
class AdaptiveHybridRanker:
    """쿼리 유형에 따른 동적 가중치 조정."""

    QUERY_TYPE_WEIGHTS = {
        "evidence_search": {"graph": 0.7, "vector": 0.3},  # 근거 중심
        "explanation": {"graph": 0.3, "vector": 0.7},      # 설명 중심
        "comparison": {"graph": 0.6, "vector": 0.4},       # 비교 연구
        "overview": {"graph": 0.4, "vector": 0.6},         # 개요/배경
    }

    def rank(self, query_type: str, graph_results: list, vector_results: list) -> list:
        weights = self.QUERY_TYPE_WEIGHTS.get(query_type, {"graph": 0.5, "vector": 0.5})
        # ... 동적 가중치 적용
```

### 11.3 Phase 2: 핵심 기능 추가 (2주)

#### 11.3.1 Conflict Detector 구현

**목적**: 동일 수술법-결과에 대한 상충 연구 자동 탐지

**구현 방식**: Rule-based (LLM 불필요)

```python
# conflict_detector.py (신규 모듈)

@dataclass
class ConflictResult:
    """상충 탐지 결과."""
    intervention: str
    outcome: str
    supporting_papers: list[PaperEvidence]
    contradicting_papers: list[PaperEvidence]
    conflict_type: str  # "direction", "significance", "magnitude"
    confidence: float
    resolution_suggestion: str

class ConflictDetector:
    """연구 결과 상충 탐지기."""

    async def detect_conflicts(
        self,
        intervention: str,
        outcome: str
    ) -> list[ConflictResult]:
        """특정 수술법-결과 조합의 상충 연구 탐지."""

        # 1. Graph에서 모든 관련 AFFECTS 관계 조회
        cypher = """
        MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
        MATCH (p:Paper)-[:INVESTIGATES]->(i)
        RETURN p.paper_id, p.title, p.evidence_level, p.sample_size,
               a.value, a.p_value, a.direction, a.is_significant
        """
        results = await self.neo4j.run_query(cypher, {
            "intervention": intervention,
            "outcome": outcome
        })

        # 2. 결과 그룹화 (방향별)
        improved = [r for r in results if r["direction"] == "improved" and r["is_significant"]]
        worsened = [r for r in results if r["direction"] == "worsened" and r["is_significant"]]
        unchanged = [r for r in results if r["direction"] == "unchanged" or not r["is_significant"]]

        # 3. 상충 탐지 규칙
        conflicts = []

        # 방향 상충 (improved vs worsened)
        if improved and worsened:
            conflicts.append(ConflictResult(
                intervention=intervention,
                outcome=outcome,
                supporting_papers=self._to_evidence(improved),
                contradicting_papers=self._to_evidence(worsened),
                conflict_type="direction",
                confidence=self._calculate_conflict_confidence(improved, worsened),
                resolution_suggestion=self._suggest_resolution(improved, worsened)
            ))

        return conflicts

    def _calculate_conflict_confidence(self, group_a: list, group_b: list) -> float:
        """상충 신뢰도 계산.

        높은 근거 수준 연구들이 상충하면 신뢰도 높음.
        """
        avg_level_a = np.mean([self._level_to_score(r["evidence_level"]) for r in group_a])
        avg_level_b = np.mean([self._level_to_score(r["evidence_level"]) for r in group_b])
        return (avg_level_a + avg_level_b) / 2

    def _suggest_resolution(self, group_a: list, group_b: list) -> str:
        """상충 해결 제안 생성."""
        # 샘플 크기, 연구 설계, 환자군 차이 분석
        # ...
        return "Consider patient selection criteria and follow-up duration differences."
```

#### 11.3.2 Cypher 추론 규칙 구현

**목적**: Graph Traversal 기반 논리 추론

```cypher
// 1. 전이적 관계 추론 (Transitive Inference)
// "A treats B, B causes C" → "A may prevent/cause C"
MATCH (i:Intervention)-[:TREATS]->(p:Pathology)-[:CAUSES]->(c:Complication)
RETURN i.name AS intervention, c.name AS complication,
       "indirect_prevention" AS relationship_type

// 2. 비교 가능한 수술법 추론
// 같은 상위 카테고리 + 같은 적응증 → 비교 가능
MATCH (i1:Intervention)-[:IS_A]->(parent)<-[:IS_A]-(i2:Intervention)
MATCH (i1)-[:TREATS]->(p:Pathology)<-[:TREATS]-(i2)
WHERE i1 <> i2
RETURN i1.name, i2.name, parent.name AS category, p.name AS indication,
       "comparable_interventions" AS relationship_type

// 3. 근거 수준 기반 추천
// 동일 적응증에서 가장 높은 근거 수준의 수술법
MATCH (i:Intervention)-[a:AFFECTS {is_significant: true}]->(o:Outcome)
MATCH (p:Paper {evidence_level: '1a'})-[:INVESTIGATES]->(i)
WHERE a.direction = 'improved'
WITH i, o, count(p) AS high_level_studies
ORDER BY high_level_studies DESC
RETURN i.name, o.name, high_level_studies

// 4. 합병증 위험 체인 추론
MATCH path = (i:Intervention)-[:MAY_CAUSE*1..3]->(c:Complication)
WHERE c.severity = 'major'
RETURN i.name, [n IN nodes(path) | n.name] AS risk_chain,
       length(path) AS chain_length
```

#### 11.3.3 Evidence Synthesizer 구현

**목적**: 메타분석 수준의 근거 합성

**구현 방식**: Hybrid (Rule + LLM)

```python
# evidence_synthesizer.py (신규 모듈)

@dataclass
class SynthesisResult:
    """근거 합성 결과."""
    intervention: str
    outcome: str
    pooled_effect: Optional[float]
    confidence_interval: tuple[float, float]
    heterogeneity: float  # I² statistic
    evidence_quality: str  # GRADE: high/moderate/low/very_low
    narrative_summary: str  # LLM 생성
    forest_plot_data: list[dict]

class EvidenceSynthesizer:
    """근거 합성기."""

    async def synthesize(
        self,
        intervention: str,
        outcome: str
    ) -> SynthesisResult:
        """모든 관련 연구의 근거 합성."""

        # 1. Graph에서 관련 AFFECTS 관계 조회 (Rule-based)
        studies = await self._fetch_studies(intervention, outcome)

        # 2. 정량적 합성 가능 여부 확인
        if self._can_pool_quantitatively(studies):
            # Rule-based 메타분석 계산
            pooled = self._calculate_pooled_effect(studies)
            ci = self._calculate_confidence_interval(studies)
            heterogeneity = self._calculate_i_squared(studies)
        else:
            pooled, ci, heterogeneity = None, (None, None), None

        # 3. GRADE 평가 (Rule-based)
        grade = self._assess_grade(studies, heterogeneity)

        # 4. 서술적 요약 (LLM-based)
        narrative = await self._generate_narrative_summary(
            intervention, outcome, studies, pooled, grade
        )

        return SynthesisResult(
            intervention=intervention,
            outcome=outcome,
            pooled_effect=pooled,
            confidence_interval=ci,
            heterogeneity=heterogeneity,
            evidence_quality=grade,
            narrative_summary=narrative,
            forest_plot_data=self._prepare_forest_plot(studies)
        )

    async def _generate_narrative_summary(self, ...):
        """LLM으로 서술적 요약 생성."""
        prompt = f"""
        Synthesize the following evidence for {intervention} → {outcome}:

        Studies: {json.dumps(studies_data)}
        Pooled Effect: {pooled}
        GRADE: {grade}

        Generate a 2-3 sentence clinical summary in academic style.
        """
        return await self.llm.generate(prompt)
```

### 11.4 Phase 3: 고급 기능 (1주 / 선택적)

#### 11.4.1 Agentic RAG

**구현 방향**: Multi-step 추론 Agent

```python
# agentic_rag.py

class SpineRAGAgent:
    """다단계 추론 Agent."""

    def __init__(self):
        self.tools = [
            HybridSearchTool(self.neo4j),  # Graph + Vector 통합
            ConflictDetectorTool(self.conflict_detector),
            EvidenceSynthesizerTool(self.synthesizer),
        ]
        self.planner = QueryPlanner(self.llm)

    async def reason(self, query: str, max_steps: int = 5) -> AgentResult:
        """다단계 추론 실행."""

        # 1. 쿼리 분해 (LLM)
        sub_queries = await self.planner.decompose(query)

        # 2. 각 sub-query 실행 (Tool Selection)
        results = []
        for sq in sub_queries:
            tool = self._select_tool(sq)
            result = await tool.execute(sq)
            results.append(result)

            # 중간 결과 기반 추가 쿼리 생성
            if follow_up := self._needs_follow_up(result):
                additional = await self.planner.generate_follow_up(sq, result)
                sub_queries.extend(additional)

        # 3. 결과 종합 (LLM)
        final_answer = await self._synthesize_results(query, results)

        return AgentResult(
            answer=final_answer,
            reasoning_steps=results,
            sources=self._extract_sources(results)
        )
```

#### 11.4.2 Citation Network Analysis

**구현 방향**: 인용 관계 기반 영향력 분석

```python
# citation_analyzer.py

class CitationAnalyzer:
    """인용 네트워크 분석기."""

    async def find_influential_papers(self, topic: str, top_k: int = 10) -> list[Paper]:
        """주제별 영향력 있는 논문 탐색."""
        cypher = """
        MATCH (p:Paper)-[:CITES]->(cited:Paper)
        WHERE p.title CONTAINS $topic OR cited.title CONTAINS $topic
        WITH cited, count(p) AS citation_count
        ORDER BY citation_count DESC
        LIMIT $top_k
        RETURN cited, citation_count
        """
        return await self.neo4j.run_query(cypher, {"topic": topic, "top_k": top_k})

    async def trace_knowledge_evolution(self, intervention: str) -> KnowledgeTimeline:
        """특정 수술법의 지식 발전 추적."""
        cypher = """
        MATCH path = (early:Paper)-[:CITES*1..5]->(recent:Paper)
        WHERE early.year < recent.year
        AND (early)-[:INVESTIGATES]->(:Intervention {name: $intervention})
        AND (recent)-[:INVESTIGATES]->(:Intervention {name: $intervention})
        RETURN path, early.year AS start_year, recent.year AS end_year
        ORDER BY length(path) DESC
        """
        return await self.neo4j.run_query(cypher, {"intervention": intervention})
```

### 11.5 Phase 4: 최신 기술 통합 (선택적)

#### 11.5.1 GraphRAG 2.0 (Microsoft)

**핵심 개념**: Community Detection + Hierarchical Summarization

```python
# graphrag_community.py

from neo4j.graph import Graph
import networkx as nx
from community import community_louvain

class GraphRAGCommunity:
    """Microsoft GraphRAG 스타일 커뮤니티 탐지."""

    async def build_communities(self) -> dict:
        """논문/수술법 커뮤니티 구축."""

        # 1. Neo4j → NetworkX 변환
        G = await self._export_to_networkx()

        # 2. Louvain Community Detection
        partition = community_louvain.best_partition(G)

        # 3. 커뮤니티별 요약 생성 (LLM)
        community_summaries = {}
        for community_id in set(partition.values()):
            members = [n for n, c in partition.items() if c == community_id]
            summary = await self._summarize_community(members)
            community_summaries[community_id] = summary

        return community_summaries
```

#### 11.5.2 RAPTOR (Stanford)

**핵심 개념**: Hierarchical Recursive Summarization

```python
# raptor_summarizer.py

class RAPTORSummarizer:
    """RAPTOR 스타일 계층적 요약."""

    async def build_hierarchy(self, chunks: list[str]) -> SummaryTree:
        """청크 → 계층적 요약 트리 구축."""

        # Level 0: 원본 청크
        current_level = chunks
        tree = [current_level]

        # 재귀적 요약 (2-3 레벨)
        while len(current_level) > 1:
            # 유사 청크 클러스터링
            clusters = self._cluster_chunks(current_level)

            # 클러스터별 요약
            summaries = []
            for cluster in clusters:
                summary = await self._summarize_cluster(cluster)
                summaries.append(summary)

            tree.append(summaries)
            current_level = summaries

        return SummaryTree(tree)
```

### 11.6 추론 구현 요약

| 기능 | LLM 필요 여부 | 구현 방식 |
|------|-------------|----------|
| Entity Normalizer 퍼지 매칭 | ❌ | rapidfuzz 라이브러리 |
| Direction Determination | ❌ | Rule-based 로직 |
| Hybrid Ranker 동적 가중치 | ❌ | 쿼리 분류 규칙 |
| Conflict Detection | ❌ | Cypher 쿼리 + 규칙 |
| Cypher Inference Rules | ❌ | 순수 Cypher |
| Evidence Synthesis (정량) | ❌ | 통계 계산 |
| Evidence Synthesis (서술) | ✅ | LLM 요약 |
| Agentic RAG | ✅ | LLM 쿼리 분해/종합 |
| GraphRAG Community | ✅ | LLM 커뮤니티 요약 |
| RAPTOR | ✅ | LLM 계층적 요약 |

### 11.7 파일 변경 계획

#### 신규 파일

| 파일 경로 | 역할 |
|----------|------|
| `src/graph/enhanced_normalizer.py` | 퍼지 매칭 Entity Normalizer |
| `src/solver/direction_determiner.py` | 결과 방향 결정 로직 |
| `src/solver/adaptive_ranker.py` | 동적 가중치 Hybrid Ranker |
| `src/solver/conflict_detector.py` | 상충 연구 탐지 |
| `src/solver/evidence_synthesizer.py` | 근거 합성 |
| `src/solver/agentic_rag.py` | 다단계 추론 Agent (선택적) |
| `src/solver/citation_analyzer.py` | 인용 네트워크 분석 (선택적) |

#### 수정 파일

| 파일 경로 | 변경 사항 |
|----------|----------|
| `src/graph/entity_normalizer.py` | rapidfuzz 통합, alias 확장 |
| `src/solver/hybrid_ranker.py` | 동적 가중치 지원 |
| `src/medical_mcp/medical_kag_server.py` | 신규 도구 추가 |
| `requirements.txt` | rapidfuzz, scipy 추가 |

### 11.8 의존성 추가

```
# requirements.txt - v3.1 추가
rapidfuzz>=3.0.0          # 퍼지 문자열 매칭
python-Levenshtein>=0.23  # Levenshtein 최적화
scipy>=1.11.0             # 통계 계산 (메타분석)
networkx>=3.0             # 그래프 분석 (선택적)
python-louvain>=0.16      # 커뮤니티 탐지 (선택적)
```

---

## 12. 보안 설계 (v1.15.0)

### 12.1 Cypher Injection 방지

모든 사용자 입력이 포함되는 Cypher 쿼리는 **파라미터화**되어야 합니다.

```python
# ❌ 취약: f-string 삽입
query = f"MATCH (i:Intervention {{name: '{user_input}'}}) RETURN i"

# ✅ 안전: $param 파라미터화
query = "MATCH (i:Intervention {name: $intervention}) RETURN i"
params = {"intervention": user_input}
result = await client.run_query(query, params)
```

**적용 범위**:

- `cypher_generator.py`: 모든 `generate()` / `_generate_*` 메서드 → `tuple[str, dict]` 반환
- `medical_kag_server.py`: `_get_user_filter_clause()` → `tuple[str, dict]` 반환 (v1.19.4: 핸들러에서 `self.server._get_user_filter_clause()` 로 BaseHandler 위임 접근)
- `search_handler.py`: 파라미터를 `run_query()`에 전달

### 12.2 Path Traversal 방지

MCP 파일 처리 핸들러는 허용된 디렉토리 외부 접근을 차단합니다.

```python
path = Path(file_path).resolve()
allowed_dirs = [Path(project_root / "data").resolve(), Path.cwd().resolve()]
if not any(str(path).startswith(str(d)) for d in allowed_dirs if d):
    raise ValueError("접근 불가: 허용된 디렉토리 외부 경로")
```

**적용 범위**: `pdf_handler.py`, `json_handler.py`

### 12.3 XSS 방지

Streamlit `unsafe_allow_html=True` 사용 시 모든 외부 데이터에 `html.escape()` 적용.

**적용 범위**: `web/app.py`, PubMed Import, Knowledge Graph 페이지

### 12.4 권한 검증

- `delete_document`: 문서 소유자 또는 system 사용자만 삭제 가능
- `reset_database`: system 사용자만 실행 가능

---

## 13. 참고 문헌

1. Edge, D., et al. (2024). "From Local to Global: A Graph RAG Approach to Query-Focused Summarization." arXiv:2404.16130. (Microsoft GraphRAG)

2. Jin, B., et al. (2025). "MedGraphRAG: Evidence-based Medical Large Language Model via Graph Retrieval-Augmented Generation." arXiv.

3. Karpel, D., et al. (2024). "Large Language Models for Spinal Surgery: A Review." Global Spine Journal.

4. Neo4j Documentation: https://neo4j.com/docs/

5. LangChain Documentation: https://python.langchain.com/docs/
