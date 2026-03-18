# Spine GraphRAG 용어체계 및 온톨로지 가이드

> **Version**: 1.30.0
> **Last Updated**: 2026-03-17
> **Maintainer**: Spine GraphRAG Development Team

## 목차

1. [개요](#1-개요)
2. [Neo4j 그래프 스키마](#2-neo4j-그래프-스키마)
3. [Intervention Taxonomy](#3-intervention-taxonomy)
4. [Multi-Entity IS_A Hierarchy](#4-multi-entity-is_a-hierarchy-v1240)
5. [SNOMED-CT 통합](#5-snomed-ct-통합)
6. [Entity Normalizer](#6-entity-normalizer)
7. [Synonym Groups](#7-synonym-groups)
8. [통계 및 커버리지](#8-통계-및-커버리지)
9. [확장 가이드](#9-확장-가이드)
10. [온톨로지 진화 워크플로우](#10-온톨로지-진화-워크플로우-v1240)

---

## 1. 개요

Spine GraphRAG 시스템은 척추 수술 분야의 의학 용어를 구조화하고 표준화하기 위해 다층 온톨로지 시스템을 사용합니다.

### 1.1 핵심 구성요소

| 구성요소 | 파일 위치 | 역할 |
|----------|-----------|------|
| **Graph Schema** | `src/graph/types/schema.py` | Neo4j 노드/관계 정의, 인덱스, 제약조건 |
| **Taxonomy Manager** | `src/graph/taxonomy_manager.py` | IS_A 계층 탐색, 동적 확장 |
| **SNOMED Mappings** | `src/ontology/spine_snomed_mappings.py` | SNOMED-CT 코드 매핑 |
| **Entity Normalizer** | `src/graph/entity_normalizer.py` | 용어 정규화, 별칭 매핑 |

### 1.2 아키텍처 다이어그램

```text
User Query (자연어)
        ↓
┌───────────────────────┐
│   Query Parser        │  ← 엔티티 추출 (4타입: I/P/O/A)
│   + SNOMED Enrichment │     snomed_id 자동 부여
└───────────────────────┘
        ↓
┌───────────────────────┐
│   Entity Normalizer   │  ← 용어 정규화 (UBE↔BESS, 한국어↔영어)
│   + SNOMED Lookup     │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  GraphContextExpander │  ← IS_A 관계로 4개 엔티티 타입 계층 확장
│  + IS_A Expansion     │     Intervention, Pathology, Outcome, Anatomy
└───────────────────────┘
        ↓
┌───────────────────────┐
│   Neo4j Graph Query   │  ← graph_filters (plural) + snomed_codes
│   + Vector Search     │     INVESTIGATES|STUDIES|INVOLVES|AFFECTS
│   + ontology_distance │     0=직접 매칭, 1=1홉 IS_A, 2=2홉 IS_A
└───────────────────────┘
        ↓
┌───────────────────────┐
│   3-Way Ranking       │  ← 0.4×semantic + 0.3×authority + 0.3×graph_relevance
│   (ontology-aware)    │     graph_relevance에 ontology_distance 반영
└───────────────────────┘
```

---

## 2. Neo4j 그래프 스키마

### 2.1 노드 타입 (Node Labels)

#### 2.1.1 Core Nodes (6개)

| 노드 | 주요 속성 | 설명 |
|------|-----------|------|
| **Paper** | paper_id, title, year, evidence_level, sub_domain, study_design, summary | 논문 메타데이터 |
| **Pathology** | name, category, snomed_code, snomed_term, aliases | 질환/병리 |
| **Anatomy** | name, region, level, snomed_code, snomed_term | 해부학적 위치 |
| **Intervention** | name, full_name, category, approach, is_minimally_invasive, snomed_code | 수술법/시술 |
| **Outcome** | name, type, unit, direction, snomed_code | 결과변수 |
| **Chunk** | chunk_id, paper_id, content, embedding, section, tier, evidence_level, is_key_finding | 텍스트 청크 |

#### 2.1.2 Extended Nodes (v7.x, 14개)

| 노드 | 주요 속성 | 설명 |
|------|-----------|------|
| **Concept** | name, definition | 교육적 개념 |
| **Recommendation** | name, grade, source | 임상 가이드라인 권고 |
| **Implant** | name, device_type, manufacturer | 임플란트/의료기기 |
| **Complication** | name, category, severity | 합병증 |
| **Drug** | name, class, mechanism | 약물 |
| **SurgicalStep** | name, sequence, description | 수술 단계 (deprecated) |
| **OutcomeMeasure** | name, category, scale_range | 결과 측정 도구 |
| **RadioParameter** | name, category, normal_range | 방사선 측정 파라미터 |
| **PredictionModel** | name, prediction_target, auc | 예측 모델 |
| **RiskFactor** | name, category, odds_ratio | 위험 인자 |
| **PatientCohort** | name, cohort_type, sample_size, mean_age | 환자 코호트 |
| **FollowUp** | name, timepoint_months, completeness_rate | 추적관찰 시점 |
| **Cost** | name, cost_type, mean_cost, qaly_gained | 의료비용 |
| **QualityMetric** | name, assessment_tool, overall_score | 연구 품질 평가 |

### 2.2 관계 타입 (Relationship Types)

#### 2.2.1 Core Relationships (10개)

| 관계 | 시작 → 끝 | 주요 속성 | 설명 |
|------|-----------|-----------|------|
| STUDIES | Paper → Pathology | is_primary | 논문이 연구하는 질환 |
| INVOLVES | Paper → Anatomy | - | 논문이 다루는 해부학적 위치 |
| INVESTIGATES | Paper → Intervention | is_comparison | 논문이 조사하는 수술법 |
| TREATS | Intervention → Pathology | indication, contraindication | 수술법의 치료 대상 |
| AFFECTS | Intervention → Outcome | value, p_value, effect_size, is_significant, direction | 수술법의 결과 영향 |
| IS_A | Entity → Entity (same type) | level | **Taxonomy 계층** (Intervention, Pathology, Outcome, Anatomy 4개 타입) |
| HAS_CHUNK | Paper → Chunk | - | 논문의 텍스트 청크 |
| CITES | Paper → Paper | context, section, citation_text, confidence | 인용 관계 |
| SUPPORTS | Paper → Paper | confidence, evidence | 결과 지지 관계 |
| CONTRADICTS | Paper → Paper | confidence, evidence | 결과 상충 관계 |

#### 2.2.2 Extended Relationships (v7.x)

| 관계 | 시작 → 끝 | 설명 |
|------|-----------|------|
| SIMILAR_TOPIC | Paper ↔ Paper | 유사 주제 |
| EXTENDS | Paper → Paper | 후속 연구 |
| REPLICATES | Paper → Paper | 재현 연구 |
| CAUSES | Intervention → Complication | 합병증 유발 |
| HAS_RISK_FACTOR | Paper → RiskFactor | 위험 인자 보고 |
| PREDICTS | PredictionModel → Outcome | 예측 대상 |
| USES_FEATURE | PredictionModel → RiskFactor | 예측 모델 피처 |
| CORRELATES | RadioParameter → OutcomeMeasure | 상관관계 |
| USES_DEVICE | Intervention → Implant | 사용 기기 |
| HAS_COHORT | Paper → PatientCohort | 연구 코호트 |
| TREATED_WITH | PatientCohort → Intervention | 코호트 치료법 |
| HAS_FOLLOWUP | Paper → FollowUp | 추적관찰 |
| REPORTS_OUTCOME | FollowUp → Outcome | 추적시점 결과 |
| REPORTS_COST | Paper → Cost | 비용 보고 |
| ASSOCIATED_WITH | Cost → Intervention | 비용 관련 시술 |
| HAS_QUALITY_METRIC | Paper → QualityMetric | 연구 품질 |

### 2.3 인덱스 구성

#### 2.3.1 단순 속성 인덱스 (40개)

```cypher
-- Paper 인덱스
CREATE INDEX paper_paper_id_idx FOR (n:Paper) ON (n.paper_id)
CREATE INDEX paper_doi_idx FOR (n:Paper) ON (n.doi)
CREATE INDEX paper_pmid_idx FOR (n:Paper) ON (n.pmid)
CREATE INDEX paper_year_idx FOR (n:Paper) ON (n.year)
CREATE INDEX paper_evidence_level_idx FOR (n:Paper) ON (n.evidence_level)
CREATE INDEX paper_sub_domain_idx FOR (n:Paper) ON (n.sub_domain)

-- Entity 인덱스 (SNOMED 코드 포함)
CREATE INDEX pathology_snomed_code_idx FOR (n:Pathology) ON (n.snomed_code)
CREATE INDEX intervention_snomed_code_idx FOR (n:Intervention) ON (n.snomed_code)
CREATE INDEX outcome_snomed_code_idx FOR (n:Outcome) ON (n.snomed_code)
```

#### 2.3.2 복합 인덱스 (5개)

```cypher
CREATE INDEX paper_composite_sub_domain_evidence_level_idx
  FOR (n:Paper) ON (n.sub_domain, n.evidence_level)

CREATE INDEX intervention_composite_name_category_idx
  FOR (n:Intervention) ON (n.name, n.category)
```

#### 2.3.3 전문 검색 인덱스 (3개)

```cypher
CREATE FULLTEXT INDEX paper_text_search FOR (n:Paper)
  ON EACH [n.title, n.abstract, n.abstract_summary, n.main_conclusion,
           n.pico_population, n.pico_intervention, n.pico_comparison, n.pico_outcome]

CREATE FULLTEXT INDEX pathology_search FOR (n:Pathology) ON EACH [n.name, n.description]
CREATE FULLTEXT INDEX intervention_search FOR (n:Intervention) ON EACH [n.name, n.full_name]
```

#### 2.3.4 벡터 인덱스 (2개)

```cypher
-- Chunk 임베딩 (3072차원, OpenAI text-embedding-3-large)
CREATE VECTOR INDEX chunk_embedding_index FOR (c:Chunk) ON (c.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}

-- Paper Abstract 임베딩
CREATE VECTOR INDEX paper_abstract_index FOR (p:Paper) ON (p.abstract_embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}
```

#### 2.3.5 관계 속성 인덱스 (10개)

```cypher
CREATE INDEX affects_p_value_idx FOR ()-[r:AFFECTS]-() ON (r.p_value)
CREATE INDEX affects_is_significant_idx FOR ()-[r:AFFECTS]-() ON (r.is_significant)
CREATE INDEX affects_direction_idx FOR ()-[r:AFFECTS]-() ON (r.direction)
CREATE INDEX supports_confidence_idx FOR ()-[r:SUPPORTS]-() ON (r.confidence)
```

---

## 3. Intervention Taxonomy

### 3.1 계층 구조 개요

Intervention 노드는 `IS_A` 관계를 통해 5단계 계층 구조를 형성합니다.

```text
Level 0 (Root)
└── Level 1 (Category)
    └── Level 2 (Subcategory)
        └── Level 3 (Technique)
            └── Level 4 (Variant)
```

### 3.2 완전한 Taxonomy 트리

```text
SPINE SURGERY (Root - v1.21.0)
├── ├── FUSION SURGERY
│   ├── Interbody Fusion
│   │   ├── TLIF (Transforaminal Lumbar Interbody Fusion)
│   │   │   ├── MIS-TLIF (Minimally Invasive TLIF)
│   │   │   └── BELIF (Biportal Endoscopic Lumbar Interbody Fusion)
│   │   ├── PLIF (Posterior Lumbar Interbody Fusion)
│   │   ├── ALIF (Anterior Lumbar Interbody Fusion)
│   │   ├── OLIF (Oblique Lumbar Interbody Fusion)
│   │   │   └── OLIF51, OLIF25, ATP
│   │   ├── LLIF (Lateral Lumbar Interbody Fusion)
│   │   │   └── XLIF, DLIF
│   │   ├── ACDF (Anterior Cervical Discectomy and Fusion)
│   │   └── MIDLF (Midline Lumbar Interbody Fusion)
│   ├── Posterolateral Fusion (PLF)
│   │   └── CBT Fusion (Cortical Bone Trajectory)
│   └── Posterior Cervical Fusion (PCF)
│       ├── C1-C2 Fusion (Atlantoaxial Fusion)
│       └── Occipitocervical Fusion
│
├── DECOMPRESSION SURGERY
│   ├── Endoscopic Surgery
│   │   ├── UBE (Unilateral Biportal Endoscopic)
│   │   │   └── BESS, BED, Biportal
│   │   ├── FELD (Full-Endoscopic Lumbar Discectomy)
│   │   ├── PELD (Percutaneous Endoscopic Lumbar Discectomy)
│   │   ├── FESS (Full Endoscopic Spinal Surgery)
│   │   └── PSLD (Percutaneous Stenoscopic Lumbar Decompression)
│   ├── Microscopic Surgery
│   │   ├── MED (Microendoscopic Discectomy)
│   │   └── Microdecompression
│   └── Open Decompression
│       ├── Laminectomy
│       ├── Laminotomy
│       ├── Foraminotomy
│       ├── UBD (Unilateral Bilateral Decompression)
│       ├── Over-the-top Decompression
│       └── Facetectomy
│
├── MOTION PRESERVATION
│   ├── ADR (Artificial Disc Replacement)
│   │   └── TDR, cTDR, lTDR
│   ├── Dynamic Stabilization
│   └── Interspinous Device
│       └── IPD, ISD, X-STOP
│
├── OSTEOTOMY
│   ├── SPO (Smith-Petersen Osteotomy)
│   │   └── Ponte Osteotomy
│   ├── PSO (Pedicle Subtraction Osteotomy)
│   ├── VCR (Vertebral Column Resection)
│   └── COWO (Three-Column Osteotomy)
│
├── FIXATION
│   ├── Pedicle Screw Fixation
│   ├── Lateral Mass Screw Fixation
│   └── Stereotactic Navigation
│
└── VERTEBRAL AUGMENTATION
    ├── PVP (Percutaneous Vertebroplasty)
    └── PKP (Percutaneous Kyphoplasty)
```

> **v1.21.0**: "Spine Surgery" (SNOMED: 122465003) 노드를 단일 루트로 추가. 기존 22개 카테고리가 모두 IS_A → Spine Surgery 관계를 형성.

### 3.3 Taxonomy Manager 사용법

```python
from src.graph.taxonomy_manager import TaxonomyManager
from src.graph.neo4j_client import Neo4jClient

async with Neo4jClient() as client:
    manager = TaxonomyManager(client)

    # 1. 상위 항목 조회
    parents = await manager.get_parent_interventions("TLIF")
    # → ["Interbody Fusion", "Fusion Surgery"]

    # 2. 하위 항목 조회
    children = await manager.get_child_interventions("Interbody Fusion")
    # → ["TLIF", "PLIF", "ALIF", "OLIF", "LLIF", "ACDF", "MIDLF"]

    # 3. 공통 조상 찾기
    ancestor = await manager.find_common_ancestor("TLIF", "PLIF")
    # → "Interbody Fusion"

    # 4. 유사 수술법 찾기
    similar = await manager.get_similar_interventions("TLIF", max_distance=2)
    # → [{"name": "PLIF", "distance": 2, "common_ancestor": "Interbody Fusion"}]

    # 5. Taxonomy 유효성 검증
    issues = await manager.validate_taxonomy()
    # → {"orphans": [], "cycles": [], "warnings": []}
```

---

## 4. Multi-Entity IS_A Hierarchy (v1.24.0)

> **Ontology Redesign**: IS_A 관계가 Intervention에서 4개 엔티티 타입 전체로 확장되었습니다.

### 4.1 4-Entity IS_A 개요

| Entity Type | Root Concept | SNOMED Code | Root Type | Children |
|-------------|-------------|-------------|-----------|----------|
| **Intervention** | Spine Surgery | 122465003 | Official | 6 categories |
| **Pathology** | 12 root nodes* | various | Mixed | per-domain |
| **Outcome** | 11 root nodes* | 900000000000653-660 | Extension | per-category |
| **Anatomy** | Spine | 900000000000665 | Extension | 7 regions |

> *Pathology, Outcome는 단일 루트가 아닌 도메인별 루트 노드를 가집니다.

### 4.2 Pathology 계층 구조

```text
Degenerative Spine Disease (49049000)
├── Spinal Stenosis (76107001)
│   ├── Lumbar Stenosis (18347007)
│   ├── Cervical Stenosis (427371002)
│   ├── Central Canal Stenosis (900000000000261)
│   └── Foraminal Stenosis (900000000000260)
├── Disc Herniation (76107001)
│   ├── Lumbar Disc Herniation (76107001)
│   └── Cervical Disc Herniation (735681009)
├── DDD (77547008)
├── Spondylolisthesis (274152003)
│   ├── Degenerative Spondylolisthesis (25631001)
│   └── Isthmic Spondylolisthesis (203646006)
└── Adjacent Segment Disease (900000000000208)

Spinal Deformity (900000000000642)
├── Scoliosis (298382003)
│   ├── Adolescent Idiopathic Scoliosis (203645005)
│   └── Degenerative Scoliosis (203639008)
├── Kyphosis (414564002)
├── Sagittal Imbalance (900000000000202)
└── Flat Back Syndrome (900000000000250)

Spinal Trauma (900000000000643)
├── Spinal Fracture (207938004)
│   └── Osteoporotic Compression Fracture (240200007)
└── Spinal Cord Injury (90584004)

Spinal Neoplasm (126070001)
├── Metastatic Spine Tumor (94225005)
└── Intradural Tumor (900000000000203)

Postoperative Complication (900000000000647)
├── Mechanical Complication (900000000000648)
│   ├── Proximal Junctional Failure (900000000000234)
│   ├── Cage Subsidence (900000000000501)
│   └── Implant Failure (900000000000249)
├── Infection Complication (900000000000649)
│   └── SSI (128601007)
└── Neurological Complication (900000000000650)
    └── Dural Tear (39827005)
```

### 4.3 Outcome 계층 구조

```text
Pain Outcome (900000000000653)
├── VAS (273903006)
│   ├── VAS Back (900000000000301)
│   └── VAS Leg (900000000000302)
├── NRS (1137229006)
└── Pain Score (900000000000661)

Functional Outcome (900000000000654)
├── ODI (273545004)
├── NDI (273547007)
├── JOA (900000000000303)
├── mJOA (900000000000304)
└── SRS-22 (900000000000309)

Quality of Life Outcome (900000000000655)
├── EQ-5D (736534008)
├── SF-36 (445537008)
└── SF-12 (900000000000310)

Radiological Outcome (900000000000656)
├── Alignment Parameter (900000000000662)
│   ├── Cobb Angle (252495004)
│   ├── SVA (900000000000307)
│   ├── PI-LL (900000000000308)
│   └── Pelvic Tilt (900000000000316)
├── Fusion Rate (900000000000306)
└── Lordosis (900000000000315)

Complication Outcome (900000000000657)
├── Infection Rate (128601007)
├── Reoperation Rate (900000000000317)
└── Dural Tear Rate (900000000000319)

Surgical Efficiency Outcome (900000000000658)
├── Operation Time (900000000000305)
├── Blood Loss (900000000000320)
└── Hospital Stay (900000000000321)

Neurological Outcome (900000000000659)
├── Motor Recovery (900000000000663)
└── Sensory Recovery (900000000000664)
```

### 4.4 Anatomy 계층 구조

```text
Spine (900000000000665)
├── Cervical (122494005)
│   ├── C1 (14806007)
│   ├── C2 (39976000)
│   ├── C3-C7 (individual codes)
│   ├── C5-6 Disc (900000000000405)
│   └── C6-7 Disc (900000000000406)
├── Thoracic (122495006)
│   ├── T1 (48694002)
│   ├── T10-T12 (individual codes)
│   └── Thoracolumbar Junction (900000000000400)
├── Lumbar (122496007)
│   ├── L1-L5 (individual codes)
│   ├── L3-4 Disc (900000000000404)
│   ├── L4-5 Disc (900000000000402)
│   └── L5-S1 Disc (900000000000403)
├── Sacral (699698002)
│   ├── S1 (181844004)
│   └── S2 (900000000000413)
├── Lumbosacral (264940005)
├── Cervicothoracic (900000000000401)
└── Thoracolumbar (900000000000400)
```

### 4.5 parent_code → Neo4j IS_A 구체화 (Materialization)

```text
[Source of Truth]
spine_snomed_mappings.py
  SPINE_PATHOLOGY_SNOMED["Lumbar Stenosis"] = SNOMEDMapping(
      code="18347007",
      parent_code="76107001",  # Spinal Stenosis
      ...
  )
           ↓
[Schema Init]
schema.py: get_init_entity_taxonomy_cypher()
  → code_to_name lookup: "76107001" → "Spinal Stenosis"
  → generates: MERGE (Lumbar Stenosis)-[:IS_A]->(Spinal Stenosis)
           ↓
[Runtime Import]
relationship_builder.py: _auto_create_is_a_relation()
  → On paper import, auto-creates IS_A from parent_code
           ↓
[Batch Repair]
scripts/build_ontology.py --force
scripts/repair_ontology.py --force
  → Retroactively apply missing IS_A relationships
```

---

## 5. SNOMED-CT 통합

### 5.1 개요

SNOMED-CT(Systematized Nomenclature of Medicine Clinical Terms)는 의료 용어의 국제 표준입니다.
Spine GraphRAG는 모든 엔티티에 SNOMED-CT 코드를 매핑하여 상호운용성을 확보합니다.

### 5.2 매핑 구조

```python
@dataclass
class SNOMEDMapping:
    code: str                    # SNOMED-CT Concept ID (SCTID)
    term: str                    # 선호 용어
    semantic_type: SNOMEDSemanticType  # PROCEDURE, DISORDER, BODY_STRUCTURE, OBSERVABLE_ENTITY, FINDING
    synonyms: list[str]          # 동의어 목록
    parent_code: str             # 상위 개념 코드
    is_extension: bool           # True = 확장 코드 (공식 코드 미등록)
    abbreviations: list[str]     # 약어 목록
    korean_term: str             # 한국어 번역
    notes: str                   # 참고 사항
```

### 5.3 Extension Code 시스템

SNOMED-CT에 아직 등록되지 않은 최신 척추 수술법은 확장 코드를 사용합니다.

```text
Extension Namespace: 900000000000
├── 900000000001xx: Procedures (수술법, 100-199)
├── 900000000002xx: Disorders (질환, 200-299)
├── 900000000003xx: Observable Entities (측정값, 300-399)
├── 900000000004xx: Body Structures (해부학, 400-499)
├── 900000000005xx: Findings (소견, 500-599)
├── 900000000006xx: Procedures Extended (수술법 확장, 600-699) ← v1.21.0 추가
├── 900000000007xx: Procedures Extended 2 (수술법 확장2, 700-799) ← v1.24.x 추가
├── 900000000008xx: Observable Extended (측정값 확장, 800-899) ← v1.24.x 추가
└── 900000000009xx: Disorders Extended (질환 확장, 900-949) ← v1.24.x 추가
```

> **v1.21.0 추가**: `procedure_ext` 범위(600-699)는 기존 procedure(100-199) 범위가 고갈됨에 따라 도입되었습니다. 주로 Fixation, Osteotomy 하위 기법의 세분화된 변형에 사용됩니다.
>
> **v1.24.x 추가**: `procedure_ext2`(700-799), `observable_ext`(800-899), `disorder_ext`(900-949) 범위가 추가되었습니다. 32개 신규 SNOMED 개념(I:+10, P:+10, O:+7, A:+5) 수용을 위해 도입.

### 5.4 주요 SNOMED 매핑

#### 5.4.1 Interventions (수술법)

| 수술법 | SNOMED Code | 공식/확장 |
|--------|-------------|-----------|
| **Spine Surgery** (Root) | 122465003 | Official |
| Fusion Surgery | 174765004 | Official |
| TLIF | 447764006 | Official |
| PLIF | 87031008 | Official |
| ALIF | 426294006 | Official |
| LLIF | 450436003 | Official |
| ACDF | 112728004 | Official |
| Laminectomy | 387731002 | Official |
| Foraminotomy | 11585007 | Official |
| PVP | 392010000 | Official |
| PKP | 429616001 | Official |
| **UBE/BESS** | 900000000000105 | **Extension** |
| **OLIF** | 900000000000101 | **Extension** |
| **MIS-TLIF** | 900000000000102 | **Extension** |
| **FELD** | 900000000000106 | **Extension** |
| **PELD** | 900000000000107 | **Extension** |
| **BELIF** | 900000000000119 | **Extension** |

#### 5.4.2 Pathologies (질환)

| 질환 | SNOMED Code | 공식/확장 |
|------|-------------|-----------|
| Lumbar Stenosis | 18347007 | Official |
| Cervical Stenosis | 427371002 | Official |
| Lumbar Disc Herniation | 76107001 | Official |
| DDD | 77547008 | Official |
| Spondylolisthesis | 274152003 | Official |
| Compression Fracture | 207938004 | Official |
| Cervical Myelopathy | 230529002 | Official |
| **Sagittal Imbalance** | 900000000000202 | **Extension** |
| **Adjacent Segment Disease** | 900000000000208 | **Extension** |

#### 5.4.3 Outcomes (결과변수)

| 결과변수 | SNOMED Code | 공식/확장 |
|----------|-------------|-----------|
| VAS | 273903006 | Official |
| NRS | 1137229006 | Official |
| ODI | 273545004 | Official |
| NDI | 273547007 | Official |
| EQ-5D | 736534008 | Official |
| SF-36 | 445537008 | Official |
| Cobb Angle | 252495004 | Official |
| **JOA** | 900000000000303 | **Extension** |
| **mJOA** | 900000000000304 | **Extension** |
| **SVA** | 900000000000307 | **Extension** |
| **Fusion Rate** | 900000000000306 | **Extension** |
| **Cage Subsidence** | 900000000000501 | **Extension** |

#### 5.4.4 Anatomy (해부학)

| 해부학 | SNOMED Code | 공식/확장 |
|--------|-------------|-----------|
| Cervical | 122494005 | Official |
| Thoracic | 122495006 | Official |
| Lumbar | 122496007 | Official |
| C1 (Atlas) | 14806007 | Official |
| C2 (Axis) | 39976000 | Official |
| L1-L5 | 181839006-181843005 | Official |
| S1 | 181844004 | Official |
| **L4-5 Disc** | 900000000000402 | **Extension** |
| **L5-S1 Disc** | 900000000000403 | **Extension** |

### 5.5 SNOMED 조회 API

```python
from src.ontology.spine_snomed_mappings import (
    get_snomed_for_intervention,
    get_snomed_for_pathology,
    get_snomed_for_outcome,
    get_snomed_for_anatomy,
    comprehensive_search,
    get_all_synonyms,
)

# 1. 직접 조회
mapping = get_snomed_for_intervention("TLIF")
# → SNOMEDMapping(code="447764006", term="Transforaminal lumbar interbody fusion", ...)

# 2. 포괄적 검색 (동의어, 관련 수술법 포함)
result = comprehensive_search("BESS")
# → {
#     "canonical_term": "UBE",
#     "exact_match": SNOMEDMapping(...),
#     "synonyms": ["UBE", "BESS", "UBESS", "Biportal Endoscopy", ...],
#     "related": [("PELD", mapping), ("FELD", mapping)],
#     "korean_term": "일측 양방향 내시경 척추 수술"
# }

# 3. 모든 동의어 가져오기
synonyms = get_all_synonyms("XLIF")
# → ["XLIF", "LLIF", "DLIF", "Lateral Lumbar Interbody Fusion", ...]
```

### 5.6 검색 파이프라인 통합 (v1.24.0)

SNOMED 코드와 IS_A 계층이 3개 검색 경로 모두에서 실제 활용됩니다.

#### 5.6.1 검색 경로별 SNOMED 연결

| 검색 경로 | SNOMED 소스 | 전달 대상 |
|-----------|-------------|----------|
| **tiered_search** | `entity.snomed_id` + `ParsedQuery.snomed_codes` fallback | `neo4j_client.hybrid_search(snomed_codes=...)` |
| **adaptive_search** (MCP) | `QueryParser.parse()` → `entity.snomed_id` | `neo4j_client.hybrid_search(graph_filters=..., snomed_codes=...)` |
| **unified_pipeline** | `get_snomed_for_*()` 4개 함수 lookup | `hybrid_ranker.search(snomed_codes=...)` |

#### 5.6.2 4개 엔티티 IS_A 확장 → Graph Filters

`tiered_search.py`에서 `GraphContextExpander.expand_by_ontology()`를 호출하여 4개 엔티티 타입 모두 IS_A 확장 후 plural 필터로 전달:

| 엔티티 | singular key | plural key | Neo4j 관계 | Cypher 패턴 |
|--------|-------------|-----------|-----------|------------|
| Intervention | `intervention` | `interventions` | INVESTIGATES | `(p)-[:INVESTIGATES]->(int:Intervention) WHERE int.name IN $interventions` |
| Pathology | `pathology` | `pathologies` | STUDIES | `(p)-[:STUDIES]->(path:Pathology) WHERE path.name IN $pathologies` |
| Outcome | `outcome` | `outcomes` | AFFECTS (via Intervention) | `(p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(out:Outcome) WHERE out.name IN $outcomes` |
| Anatomy | `anatomy` | `anatomies` | INVOLVES | `(p)-[:INVOLVES]->(anat:Anatomy) WHERE anat.name IN $anatomies` |

#### 5.6.3 ontology_distance 스코어링

`search_dao.py` SNOMED 분기에서 4개 관계 경로를 탐색하여 `ontology_distance`를 계산:

```cypher
-- 직접 매칭 (Intervention, Pathology, Anatomy)
OPTIONAL MATCH (p)-[:INVESTIGATES|STUDIES|INVOLVES]->(direct_target)
WHERE direct_target.snomed_code IN $snomed_codes OR IS_A 매칭

-- 2홉 매칭 (Outcome: Paper → Intervention → Outcome)
OPTIONAL MATCH (p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(outcome_target:Outcome)
WHERE outcome_target.snomed_code IN $snomed_codes OR IS_A 매칭

-- COALESCE → ontology_distance 계산
CASE
    WHEN target IS NULL THEN null      -- 매칭 없음
    WHEN target.snomed_code IN $snomed_codes THEN 0  -- 직접 매칭
    WHEN 1-hop IS_A THEN 1             -- 부모/자식 1단계
    ELSE 2                             -- 2단계 이상
END as ontology_distance
```

| ontology_distance | 의미 | graph_relevance 점수 |
|:-:|------|:--:|
| 0 | SNOMED 직접 매칭 | 1.0 |
| 1 | IS_A 1홉 (부모/자식) | 0.7 |
| 2 | IS_A 2홉 | 0.4 |
| null | 매칭 없음 | 0.2 (기본값) |

최종 스코어: `final_score = 0.4 × semantic + 0.3 × authority + 0.3 × graph_relevance`

---

## 6. Entity Normalizer

### 6.1 개요

Entity Normalizer는 다양한 형태의 의학 용어를 표준화된 형태로 정규화합니다.

### 6.2 주요 기능

1. **별칭 매핑**: UBE ↔ BESS ↔ Biportal ↔ 내시경 수술
2. **한국어 지원**: 요추 협착증 ↔ Lumbar Stenosis
3. **조사 처리**: "TLIF가", "OLIF를" → "TLIF", "OLIF"
4. **Fuzzy Matching**: 오타 교정 (RapidFuzz 사용)
5. **SNOMED 자동 링크**: 정규화 결과에 SNOMED 코드 포함

### 6.3 사용법

```python
from src.graph.entity_normalizer import EntityNormalizer

normalizer = EntityNormalizer()

# 1. 수술법 정규화
result = normalizer.normalize_intervention("Biportal Endoscopic")
# → NormalizationResult(
#     original="Biportal Endoscopic",
#     normalized="UBE",
#     confidence=1.0,
#     method="exact",
#     snomed_code="900000000000105",
#     snomed_term="Unilateral biportal endoscopic spine surgery"
# )

# 2. 한국어 정규화
result = normalizer.normalize_intervention("내시경 수술")
# → NormalizationResult(normalized="UBE", confidence=1.0, ...)

# 3. 조사 제거
result = normalizer.normalize_intervention("TLIF가")
# → NormalizationResult(normalized="TLIF", confidence=0.95, ...)

# 4. 텍스트에서 추출 및 정규화
text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"
interventions = normalizer.extract_and_normalize_interventions(text)
# → [NormalizationResult(normalized="TLIF", ...), NormalizationResult(normalized="OLIF", ...)]
```

### 6.4 NormalizationResult 구조

```python
@dataclass
class NormalizationResult:
    original: str       # 원본 텍스트
    normalized: str     # 정규화된 이름
    confidence: float   # 신뢰도 (0.0 ~ 1.0)
    matched_alias: str  # 매칭된 별칭
    method: str         # "exact", "token", "fuzzy", "none"
    snomed_code: str    # SNOMED-CT 코드
    snomed_term: str    # SNOMED-CT 용어
    category: str       # 수술법 카테고리
```

### 6.5 별칭 매핑 현황 (일부)

```python
INTERVENTION_ALIASES = {
    "UBE": ["BESS", "Biportal", "BED", "내시경 수술", "양측 내시경", ...],
    "BELIF": ["BE-TLIF", "BETLIF", "Endo-TLIF", "UBE-TLIF", ...],
    "TLIF": ["Transforaminal Lumbar Interbody Fusion", "경추간공 유합술", ...],
    "OLIF": ["ATP", "OLIF51", "OLIF25", "측방 유합술", ...],
    "LLIF": ["XLIF", "DLIF", "외측 유합술", ...],
    # ... 70+ 수술법
}

PATHOLOGY_ALIASES = {
    "Lumbar Stenosis": ["LSS", "요추 협착증", "Central Stenosis", ...],
    "Lumbar Disc Herniation": ["LDH", "HNP", "HIVD", "추간판 탈출증", ...],
    # ... 25+ 질환
}

OUTCOME_ALIASES = {
    "VAS": ["Visual Analog Scale", "Pain Score", ...],
    "ODI": ["Oswestry Disability Index", ...],
    # ... 30+ 결과변수
}

# v1.16.0: 해부학 위치 별칭 (신규)
ANATOMY_ALIASES = {
    "Cervical": ["C-spine", "cervical spine", "경추"],
    "Lumbar": ["L-spine", "lumbar spine", "요추"],
    "C5-6": ["C5-C6", "C5/6", "C5/C6", "C5-C6 disc"],
    "L4-5": ["L4-L5", "L4/5", "L4/L5", "L4-L5 disc"],
    # ... 33개 매핑 (영역, 척추 레벨, 디스크 레벨, 한국어)
}
```

### 6.6 normalize_anatomy() (v1.16.0)

해부학 위치를 정규화하고 SNOMED 코드를 자동 첨부합니다.

```python
# 해부학 위치 정규화
result = normalizer.normalize_anatomy("L-spine")
# → NormalizationResult(normalized="Lumbar", snomed_code="122496007")

result = normalizer.normalize_anatomy("C5-C6")
# → NormalizationResult(normalized="C5-6", snomed_code="900000000000405")

result = normalizer.normalize_anatomy("요추")
# → NormalizationResult(normalized="Lumbar", snomed_code="122496007")
```

**지원 카테고리:**
- **영역**: Cervical, Thoracic, Lumbar, Sacral, Lumbosacral, Cervicothoracic, Thoracolumbar
- **척추 레벨**: C1-C7, T1, T10-T12, L1-L5, S1-S2
- **디스크 레벨**: L4-5, L5-S1, L3-4, C5-6, C6-7
- **한국어**: 경추, 흉추, 요추, 천추

---

## 7. Synonym Groups

### 7.1 완전 동의어 그룹

같은 수술법의 다른 이름들로, 검색 시 모두 동일하게 처리됩니다.

```python
SYNONYM_GROUPS = [
    # UBE/Biportal 계열
    {"UBE", "BESS", "UBESS", "Biportal Endoscopy", "BED",
     "Unilateral Biportal Endoscopy", "Biportal Endoscopic Discectomy"},

    # LLIF/XLIF 계열
    {"LLIF", "XLIF", "DLIF", "Lateral Lumbar Interbody Fusion",
     "Extreme Lateral Interbody Fusion", "Direct Lateral Interbody Fusion"},

    # OLIF/ATP 계열
    {"OLIF", "ATP", "OLIF25", "OLIF51", "Oblique Lumbar Interbody Fusion"},

    # BELIF/BE-TLIF 계열
    {"BELIF", "BE-TLIF", "BETLIF", "BE-LIF", "BELF",
     "Biportal Endoscopic TLIF", "Biportal Endoscopic Lumbar Interbody Fusion"},

    # PELD 계열
    {"PELD", "TELD", "TF-PELD", "Percutaneous Endoscopic Lumbar Discectomy"},

    # 질환 동의어
    {"HNP", "HIVD", "LDH", "Lumbar Disc Herniation", "Disc Prolapse"},
    {"LSS", "Lumbar Stenosis", "Lumbar Spinal Stenosis", "Central Stenosis"},
    {"DCM", "CSM", "Cervical Myelopathy", "Degenerative Cervical Myelopathy"},
    {"Sciatica", "Lumbar Radiculopathy", "Radicular pain"},

    # 합병증 동의어
    {"ASD", "ASDis", "ASDeg", "Adjacent Segment Disease", "Adjacent Level Disease"},

    # v1.21.0: PJK/PJF를 별도 개념으로 분리
    # PJK (Proximal Junctional Kyphosis): Outcome/방사선 측정값 (900000000000375)
    # PJF (Proximal Junctional Failure): Pathology/임상 실패 (900000000000234)
    {"PJK", "Proximal Junctional Kyphosis"},
    {"PJF", "Proximal Junctional Failure"},
]
```

### 7.2 관련 수술법 (Related Terms)

같은 카테고리지만 접근법이 다른 수술법으로, 검색 시 "관련 수술법"으로 표시됩니다.

```python
RELATED_TERMS = {
    "LLIF": ["OLIF", "ALIF"],      # Lateral vs Oblique vs Anterior
    "OLIF": ["LLIF", "ALIF"],
    "ALIF": ["LLIF", "OLIF"],

    "UBE": ["PELD", "FELD", "MED"], # 내시경 수술 간 관련
    "PELD": ["UBE", "FELD", "MED"],
    "FELD": ["UBE", "PELD", "MED"],

    "TLIF": ["MIS-TLIF", "PLIF", "ALIF"],
    "MIS-TLIF": ["TLIF", "UBE"],

    "SPO": ["PSO", "VCR"],          # Osteotomy 간 관련
    "PSO": ["SPO", "VCR"],
    "VCR": ["SPO", "PSO"],
}
```

---

## 8. 통계 및 커버리지

### 8.1 전체 매핑 통계 (v1.24.x)

#### 소스 매핑 (spine_snomed_mappings.py)

| 카테고리 | 전체 | 공식 SNOMED | 확장 코드 | 커버리지 |
|----------|------|-------------|-----------|----------|
| Interventions | 235 | 53 | 165 | 24.3% |
| Pathologies | 231 | 73 | 141 | 34.1% |
| Outcomes | 200 | 38 | 157 | 19.5% |
| Anatomy | 69 | 29 | 40 | 42.0% |
| **Total** | **735** | **193** | **503** | **27.7%** |

#### Neo4j 실제 커버리지

| 카테고리 | 매핑/전체 | 커버리지 |
|----------|-----------|----------|
| Intervention | 190/466 | 40.8% |
| Pathology | 115/294 | 39.1% |
| Outcome | 385/1874 | 20.5% |
| Anatomy | 163/183 | 89.1% |

> **v1.14.15 변경사항**: SNOMED 중복 제거 및 정리, 공식 코드 전환 (Wound Dehiscence → 225553008)
>
> **v1.15.0 변경사항**: `entity_normalizer.py` OUTCOME_ALIASES/PATHOLOGY_ALIASES 딕셔너리 중복 키 5건 merge — SF-12(5개 alias 복원), Cervical Myelopathy(4개), PJK(1개), DJK, Adjacent Segment Disease(2개). Python dict 중복 키는 마지막 값만 유지되므로 이전 alias가 손실되고 있었음.
>
> **v1.16.1 변경사항**:
> - Intervention SNOMED 4건 추가 (COWO, Open Decompression, Over-the-top Decompression, UBD)
> - Anatomy SNOMED 3건 추가 (S2, T10, T11) — 공식 SNOMED 코드
> - TREATS 관계 생성 코드 구현 (Intervention → Pathology)
> - ANATOMY_ALIASES 딕셔너리 신규 추가 (33개 매핑)
> - Schema 노드 26개에 대한 INTERVENTION_ALIASES 추가
> - normalize_anatomy() 메서드 추가
>
> **v1.16.2 변경사항**:
> - SNOMED 매핑 대폭 확장: 147 → 304개 (I:+72, P:+51, O:+34)
> - entity_normalizer.py 16개 alias 갭 수정 (CES, DM, SSI 등)
> - 공식 SNOMED 코드 49건 추가 (Laminoplasty, OPLL, ESI, Schwannoma 등)
> - 확장 코드 108건 추가 (척추 수술 특화 용어)
>
> **v1.21.0 변경사항**:
> - SNOMED 매핑 확장: 414 → 438개 (I:+23, P:+1)
> - Extension Code 범위 추가: `procedure_ext` (600-699)
> - **SNOMED 중복 전면 해결**: Intervention 29→0, Pathology 3→0, Anatomy 23→0
> - IS_A 루트 단일화: "Spine Surgery" (122465003) 추가, 22개 카테고리 → IS_A → Spine Surgery
> - Fusion Surgery 코드 변경: 122465003 → 174765004 (Spine Surgery에 122465003 할당)
> - PJK/PJF 분리: PJK = Outcome (900000000000375), PJF = Pathology (900000000000234)
> - Entity Normalizer 4개 카테고리 별칭 대폭 확대
> - Summary 필드 추가 (Paper 노드, LLM 생성 700자 요약)
>
> **v1.21.2 변경사항**:
> - SNOMED 매핑 확장: 438 → 446 → 465개 (I:+1, P:+3, O:+4; v1.23.1: I:+3, P:+3, O:+10, A:+3)
> - Neo4j 고빈도 미매핑 엔티티 별칭 추가: Intervention 9개, Pathology 11개, Outcome 17개 canonical 확장
> - 신규 Outcome canonical 3개: ROM, Functional Recovery, PROMs
> - 공식 SNOMED 5건 추가 (Pseudarthrosis, Low Back Pain, Spinal Cord Compression, Bone Graft, Heterotopic Ossification)
> - 확장 코드 4건 추가 (Central Canal Stenosis, Mortality, Functional Recovery, PROMs)
> - Neo4j SNOMED 커버리지: I 40.8%, P 39.1%, O 20.5%, A 89.1%

### 8.2 확장 코드 필요 항목

#### Interventions (25개)
- UBE/BESS (Biportal Endoscopy)
- OLIF (Oblique LIF)
- MIS-TLIF (Minimally Invasive TLIF)
- MIDLF (Midline LIF)
- CBT Fusion
- FELD, PELD, FESS, PSLD
- MED, Microdecompression
- SPO, PSO, VCR
- Lateral Mass Screw
- Motion Preservation, Dynamic Stabilization, Interspinous Device
- BELIF, Stereotactic Navigation
- Facetectomy (v1.14.2)
- COWO, Open Decompression, Over-the-top Decompression, UBD (v1.16.1)

#### Pathologies (6개)
- Adult Spinal Deformity
- Sagittal Imbalance
- Intradural Tumor
- Segmental Instability
- DJK (Distal Junctional Kyphosis)
- Adjacent Segment Disease (구분)

#### Outcomes (20개)
- VAS Back, VAS Leg
- JOA, mJOA
- SRS-22
- Fusion Rate
- Cage Subsidence
- SVA, PT, PI-LL
- Reoperation Rate, ASD Reoperation Rate
- PJK (Proximal Junctional Kyphosis)
- Serum CPK, Scar Quality, Postoperative Drainage
- Recurrent Disc Herniation, Epidural Hematoma
- C5 Palsy (v1.14.3)

### 8.3 통계 조회 API

```python
from src.ontology.spine_snomed_mappings import get_mapping_statistics, get_coverage_report

stats = get_mapping_statistics()
# → {
#     "total_mappings": 438,
#     "interventions": 167,
#     "pathologies": 121,
#     "outcomes": 104,
#     "anatomy": 46,
#     "official_snomed_codes": 159,
#     "extension_codes_needed": 279,
#     "coverage_percent": 36.3
# }

report = get_coverage_report()
# → 카테고리별 상세 분석
```

---

## 9. 확장 가이드

### 9.1 새 수술법 추가

#### Step 1: SNOMED 매핑 추가 (spine_snomed_mappings.py)

```python
SPINE_INTERVENTION_SNOMED["New Technique"] = SNOMEDMapping(
    code="900000000000126",  # 다음 확장 코드
    term="New surgical technique description",
    semantic_type=SNOMEDSemanticType.PROCEDURE,
    parent_code="386638009",  # 상위 개념 코드
    is_extension=True,
    synonyms=["Alias1", "Alias2"],
    abbreviations=["NT", "NewTech"],
    korean_term="새로운 수술법",
    notes="Description of the technique",
)
```

#### Step 2: Entity Normalizer 별칭 추가 (entity_normalizer.py)

```python
INTERVENTION_ALIASES["New Technique"] = [
    "NT", "NewTech", "Alias1", "Alias2", "새로운 수술법"
]
```

#### Step 3: Taxonomy 관계 추가 (schema.py의 get_init_taxonomy_cypher)

```cypher
MERGE (nt:Intervention {name: 'New Technique',
                        full_name: 'Full Name of New Technique',
                        category: 'decompression',
                        is_minimally_invasive: true})
MERGE (nt)-[:IS_A {level: 2}]->(parent)
```

#### Step 4: SNOMED Enrichment 추가 (schema.py의 get_enrich_snomed_cypher)

```cypher
MATCH (i:Intervention {name: 'New Technique'})
SET i.snomed_code = '900000000000121',
    i.snomed_term = 'New surgical technique description'
```

### 9.2 동의어 그룹 추가

```python
# spine_snomed_mappings.py
SYNONYM_GROUPS.append({
    "Term1", "Term2", "Term3", "한국어 용어"
})
```

### 9.3 관련 수술법 추가

```python
# spine_snomed_mappings.py
RELATED_TERMS["New Technique"] = ["Related1", "Related2"]
RELATED_TERMS["Related1"].append("New Technique")
RELATED_TERMS["Related2"].append("New Technique")
```

### 9.4 공식 SNOMED 코드 업데이트

SNOMED-CT에 새 코드가 등록되면:

1. `is_extension=False`로 변경
2. 공식 코드로 `code` 업데이트
3. Extension Code Range 재사용 가능

```python
# 기존
"UBE": SNOMEDMapping(code="900000000000105", is_extension=True, ...)

# 업데이트 후 (공식 코드 등록 시)
"UBE": SNOMEDMapping(code="1234567890", is_extension=False, ...)
```

---

## 10. 온톨로지 진화 워크플로우 (v1.24.0)

> 새 논문 임포트 시 미등록 용어가 발견되면 LLM 기반 SNOMED 매핑을 자동 제안하는 워크플로우입니다.

### 10.1 전체 파이프라인

```text
[1] Paper Import (unified_pdf_processor)
    ↓
[2] Entity Extraction (LLM)
    ↓
[3] Entity Normalization (entity_normalizer)
    ├── Match found → use existing mapping
    └── No match → record to _unregistered_terms
                    ↓
[4] Unregistered Term Collection
    ↓  (after build_from_paper)
[5] SNOMEDProposer.propose_mapping()
    ├── LLM identifies closest parent concept
    ├── Generates extension code
    └── Rates confidence
                    ↓
[6] Confidence Check
    ├── >= 0.9: Auto-apply → update spine_snomed_mappings.py
    ├── 0.7-0.89: Queue for user approval
    └── < 0.7: Queue for manual review
                    ↓
[7] Apply Mapping
    ├── Add to spine_snomed_mappings.py (SNOMED dict)
    ├── Add to entity_normalizer.py (aliases)
    └── Create Neo4j IS_A relationship
```

### 10.2 SNOMEDProposer API

```python
from ontology.snomed_proposer import SNOMEDProposer

proposer = SNOMEDProposer(llm_client)

# Single term proposal
proposal = await proposer.propose_mapping(
    term="MISS-TLIF",
    entity_type="intervention",
    context="Minimally invasive single-stage TLIF technique"
)
# → SNOMEDProposal(
#     proposed_parent_name="MIS-TLIF",
#     proposed_code="900000000000xxx",
#     confidence=0.85,
#     auto_apply=False,
#     ...
# )

# Batch proposal from unregistered terms
from graph.entity_normalizer import EntityNormalizer
normalizer = EntityNormalizer()
unregistered = normalizer.get_unregistered_terms()
proposals = await proposer.batch_propose(unregistered)
```

### 10.3 Confidence Thresholds

| Confidence | Action | Rationale |
|-----------|--------|-----------|
| >= 0.9 | Auto-apply + log to review queue | Clear synonym/variant of existing concept |
| 0.7-0.89 | User approval needed | Probable match but needs human verification |
| < 0.7 | Manual review required | Novel concept or ambiguous mapping |

### 10.4 Extension Code Allocation

새 매핑이 추가될 때 다음 사용 가능한 extension code가 자동 할당됩니다.

```text
Entity Type      Primary Range        Extended Range
Intervention     900000000001xx       900000000006xx
Pathology        900000000002xx       -
Outcome          900000000003xx       -
Anatomy          900000000004xx       -
Finding          900000000005xx       -
```

### 10.5 관련 모듈

| 모듈 | 역할 |
|------|------|
| `entity_normalizer.py` | `_record_unregistered_term()`, `get_unregistered_terms()` |
| `snomed_proposer.py` | LLM 기반 SNOMED 매핑 제안 |
| `relationship_builder.py` | `build_from_paper()` 후 미등록 용어 로그 |
| `spine_snomed_mappings.py` | SNOMED 매핑 Single Source of Truth |
| `repair_ontology.py` | 누락된 IS_A/SNOMED 일괄 복구 |

---

## 부록: 소스 파일 참조

| 파일 | 라인 수 | 설명 |
|------|---------|------|
| [src/graph/types/schema.py](../src/graph/types/schema.py) | ~1,400 | 스키마, 인덱스, Cypher 템플릿 |
| [src/graph/types/core_nodes.py](../src/graph/types/core_nodes.py) | ~500 | Core 노드 정의 |
| [src/graph/types/extended_nodes.py](../src/graph/types/extended_nodes.py) | ~1,000 | Extended 노드 정의 |
| [src/graph/types/relationships.py](../src/graph/types/relationships.py) | ~300 | 관계 정의 |
| [src/graph/types/enums.py](../src/graph/types/enums.py) | ~200 | Enum 정의 |
| [src/graph/taxonomy_manager.py](../src/graph/taxonomy_manager.py) | ~440 | Taxonomy 관리 |
| [src/ontology/spine_snomed_mappings.py](../src/ontology/spine_snomed_mappings.py) | ~5,190 | SNOMED 매핑 |
| [src/graph/entity_normalizer.py](../src/graph/entity_normalizer.py) | ~3,550 | 용어 정규화 + 미등록 용어 수집 |
| [src/ontology/snomed_proposer.py](../src/ontology/snomed_proposer.py) | ~300 | LLM 기반 SNOMED 매핑 제안 |
| [scripts/repair_ontology.py](../scripts/repair_ontology.py) | ~400 | 온톨로지 무결성 복구 |
| [scripts/build_ontology.py](../scripts/build_ontology.py) | ~200 | IS_A 계층 일괄 적용 |

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.24.x | 2026-02-28 | SNOMED 매핑 확장 621→653개 (I:+10, P:+10, O:+7, A:+5), Extension 범위 추가 (procedure_ext2 700-799, observable_ext 800-899, disorder_ext 900-949), 166개 orphan key entity_normalizer 동기화, ~280 alias 추가, synonym overlap 정리 |
| 1.24.0 | 2026-02-28 | 4-Entity IS_A Hierarchy 문서화 (Section 4), 온톨로지 진화 워크플로우 (Section 10), SNOMEDProposer 추가, repair_ontology.py 추가, DV Phase 6/QC Phase 6 신설 |
| 1.21.0 | 2026-02-16 | IS_A 루트 단일화 (Spine Surgery), SNOMED 중복 전면 해결 (I:29→0, P:3→0, A:23→0), Extension range 추가 (procedure_ext 600-699), PJK/PJF 분리, Normalizer 4개 카테고리 대폭 확대, Summary 필드 추가, TREATS paper_count 재계산 |
| 1.14.1 | 2025-01-01 | 최초 문서 작성, 전체 시스템 분석 |
| 7.14 | 2024-12 | BELIF, BED, Stereotactic Navigation 추가 |
| 7.11 | 2024-11 | SSI 분류 (Superficial/Deep) 추가 |
| 4.3 | 2024-09 | SNOMED Extension Code 시스템 도입 |
