# Spine GraphRAG Schema

> **Version**: 1.27.0

## Node Types

### Core Nodes

| Node | Key Properties | Description |
|------|----------------|-------------|
| Paper | paper_id, title, year, evidence_level, sub_domain, summary | 논문 |
| Pathology | name, category, snomed_code, snomed_term | 질환 |
| Anatomy | level, region, snomed_code, snomed_term | 해부학적 위치 |
| Intervention | name, category, aliases, snomed_code, snomed_term | 수술법 |
| Outcome | name, category, unit, snomed_code, snomed_term | 결과 변수 |
| Chunk | chunk_id, paper_id, tier, section, evidence_level, embedding | 논문 텍스트 청크 (벡터 임베딩 포함) |

### v1.1 Extended Entity Nodes

| Node | Key Properties | Description | Status |
|------|----------------|-------------|--------|
| Concept | name | 일반 개념 | Active |
| Technique | name | 수술 기법 | ⚠️ DEPRECATED - use InterventionNode.technique_description |
| Recommendation | name | 권고사항 | Active |
| Implant | name, device_type | 임플란트/기기 (통합됨) | Active |
| Complication | name, category | 합병증 | Active |
| Drug | name | 약물 | Active |
| SurgicalStep | name | 수술 단계 | ⚠️ DEPRECATED - use InterventionNode.surgical_steps |
| OutcomeMeasure | name, category | 결과 측정 도구 | Active |
| RadioParameter | name, category | 영상 파라미터 | Active |
| PredictionModel | name, prediction_target | 예측 모델 | Active |
| RiskFactor | name, category | 위험인자 | Active |

> **Note**: Technique, SurgicalStep, Instrument 노드는 deprecated 되었습니다. 각각 InterventionNode의 technique_description, surgical_steps 필드와 ImplantNode(device_type="instrument")를 사용하세요.

### v1.2 Extended Nodes

| Node | Key Properties | Description |
|------|----------------|-------------|
| PatientCohort | name, cohort_type, sample_size, mean_age | 환자 코호트 |
| FollowUp | name, timepoint_months, completeness_rate | 추적관찰 시점 |
| Cost | name, cost_type, mean_cost, qaly_gained, icer | 의료비용 |
| QualityMetric | name, assessment_tool, overall_score | 연구품질평가 |

## Relationship Types

### Core Relationships

| Relationship | Start → End | Key Properties | 검색 필터 | Description |
|--------------|-------------|----------------|----------|-------------|
| STUDIES | Paper → Pathology | is_primary | `pathology`/`pathologies` | 논문이 연구하는 질환 |
| INVOLVES | Paper → Anatomy | | `anatomy`/`anatomies` | 논문이 다루는 해부학적 위치 |
| LOCATED_AT | Pathology → Anatomy | | — | 질환의 해부학적 위치 *(Planned)* |
| INVESTIGATES | Paper → Intervention | is_comparison | `intervention`/`interventions` | 논문이 조사하는 수술법 |
| AFFECTS | Intervention → Outcome | value, p_value, effect_size, is_significant | `outcome`/`outcomes` (2홉: INVESTIGATES→AFFECTS) | 수술법의 결과 영향 |
| TREATS | Intervention → Pathology | indication, source_paper_ids, paper_count | — | 수술법이 치료하는 질환 (v1.16.1 구현, v1.16.4 속성 통일) |
| IS_A | Entity → Entity (same type) | auto_generated, source, created_at | SNOMED IS_A 확장 (ontology_distance 0/1/2) | Taxonomy 계층 관계 (4 entity types) |
| HAS_CHUNK | Paper → Chunk | | — | 논문의 텍스트 청크 |
| MENTIONS | Chunk → Intervention\|Pathology\|Outcome\|Anatomy | | — | 청크가 언급하는 의학 엔티티 (v1.27.0 구현) |
| APPLIED_TO | Intervention → Anatomy | | — | 수술법이 적용되는 해부학적 위치 (v1.27.0 구현) |

### Paper-to-Paper Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| CITES | Paper → Paper | | 인용 관계 |
| SUPPORTS | Paper → Paper | confidence | 결과를 지지하는 관계 |
| CONTRADICTS | Paper → Paper | confidence | 결과가 상충하는 관계 |
| SIMILAR_TOPIC | Paper ↔ Paper | confidence | 유사 주제 관계 (양방향) |
| EXTENDS | Paper → Paper | confidence | 후속/확장 연구 관계 |
| REPLICATES | Paper → Paper | confidence | 재현 연구 관계 |

### v1.1 Extended Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| CAUSES | Intervention → Complication | | 수술로 인한 합병증 |
| HAS_RISK_FACTOR | Paper → RiskFactor | | 논문에서 식별된 위험인자 |
| PREDICTS | PredictionModel → Outcome | | 예측 모델의 타겟 결과 |
| USES_FEATURE | PredictionModel → RiskFactor | | 예측 모델이 사용하는 변수 |
| CORRELATES | RadioParameter → OutcomeMeasure | | 영상 파라미터와 결과의 상관관계 |
| USES_DEVICE | Intervention → Implant | | 수술에 사용되는 임플란트 |
| MEASURED_BY | Outcome → OutcomeMeasure | | 결과 측정 도구 *(Planned)* |

### v1.2 Extended Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| HAS_COHORT | Paper → PatientCohort | | 논문의 환자 코호트 |
| TREATED_WITH | PatientCohort → Intervention | | 코호트에 적용된 수술법 |
| HAS_FOLLOWUP | Paper → FollowUp | | 논문의 추적관찰 시점 |
| REPORTS_OUTCOME | FollowUp → Outcome | | 추적관찰 시점의 결과 |
| REPORTS_COST | Paper → Cost | | 논문의 비용 분석 |
| ASSOCIATED_WITH | Cost → Intervention | | 비용 관련 수술법 |
| HAS_QUALITY_METRIC | Paper → QualityMetric | | 논문의 품질 평가 지표 |

## Intervention Taxonomy (IS_A Hierarchy)

```text
Spine Surgery
├── Fusion Surgery
│   ├── Interbody Fusion
│   │   ├── TLIF, PLIF, ALIF, OLIF, LLIF/XLIF
│   │   └── BELIF (BE-TLIF) ← v1.14.2 추가
│   └── Posterolateral Fusion
├── Decompression Surgery
│   ├── Open Decompression
│   │   ├── Laminectomy, Laminotomy, Foraminotomy
│   │   └── Facetectomy ← v1.14.2 추가
│   └── Endoscopic Surgery
│       └── UBE (Biportal), FELD, PELD, MED
├── Fixation
│   ├── Pedicle Screw, Lateral Mass Screw
│   └── Stereotactic Navigation ← v1.14.2 추가
├── Motion Preservation
│   └── ADR, Dynamic Stabilization
├── Osteotomy
│   └── SPO, PSO, VCR
└── Vertebral Augmentation
    └── PVP (Percutaneous Vertebroplasty), PKP (Balloon Kyphoplasty)
```

## 4-Entity IS_A Hierarchy (v1.24.0)

> **Ontology Redesign**: IS_A 관계가 Intervention뿐 아니라 Pathology, Outcome, Anatomy로 확장되었습니다.
> spine_snomed_mappings.py의 `parent_code`가 Neo4j IS_A 관계의 Single Source of Truth입니다.

### IS_A Relationship Properties

| Property | Type | Description |
|----------|------|-------------|
| level | int | Hierarchy depth (1 = direct child) |
| auto_generated | bool | True if created by scripts/import pipeline |
| source | string | Origin: 'build_ontology', 'repair_ontology', 'relationship_builder' |
| created_at | datetime | Creation timestamp |

### Root Concepts per Entity Type

| Entity Type | Root Concept | SNOMED Code | Children Count |
|-------------|-------------|-------------|----------------|
| **Intervention** | Spine Surgery | 122465003 | 6 category nodes |
| **Pathology** | Spinal Disease (root) | 1268926005 | 7+ category nodes |
| **Outcome** | Patient-Reported Outcome (root) | 371545006 | 5+ category nodes |
| **Anatomy** | Spinal Structure | 421060004 | 4 region nodes |

### IS_A Examples per Entity Type

#### Intervention IS_A
```text
TLIF -[:IS_A]-> Interbody Fusion -[:IS_A]-> Spine Surgery
UBE -[:IS_A]-> Endoscopic Surgery -[:IS_A]-> Decompression Surgery -[:IS_A]-> Spine Surgery
```

#### Pathology IS_A
```text
Lumbar Stenosis -[:IS_A]-> Spinal Stenosis -[:IS_A]-> Degenerative Spine Disease
Proximal Junctional Failure -[:IS_A]-> Mechanical Complication -[:IS_A]-> Postoperative Complication
Adjacent Segment Disease -[:IS_A]-> Degenerative Spine Disease
```

#### Outcome IS_A
```text
VAS Back -[:IS_A]-> VAS -[:IS_A]-> Pain Score -[:IS_A]-> Patient-Reported Outcome
ODI -[:IS_A]-> Functional Score -[:IS_A]-> Patient-Reported Outcome
Cobb Angle -[:IS_A]-> Alignment Parameter -[:IS_A]-> Radiographic Outcome
```

#### Anatomy IS_A
```text
L4-5 -[:IS_A]-> Lumbar Spine -[:IS_A]-> Spinal Structure
C5-6 -[:IS_A]-> Cervical Spine -[:IS_A]-> Spinal Structure
Facet Joint -[:IS_A]-> Spinal Structure
```

### Graph Traversal Paths

```cypher
-- 1. Find all interventions under "Endoscopic Surgery"
MATCH (i:Intervention)-[:IS_A*1..3]->(parent:Intervention {name: 'Endoscopic Surgery'})
RETURN i.name

-- 2. Find pathologies related to "Degenerative Spine Disease"
MATCH (p:Pathology)-[:IS_A*1..3]->(parent:Pathology {name: 'Degenerative Spine Disease'})
RETURN p.name

-- 3. Expand outcome hierarchy for "Pain Score"
MATCH (o:Outcome)-[:IS_A*1..3]->(parent:Outcome {name: 'Pain Score'})
RETURN o.name

-- 4. Find anatomy under "Lumbar Spine"
MATCH (a:Anatomy)-[:IS_A*1..3]->(parent:Anatomy {name: 'Lumbar Spine'})
RETURN a.name

-- 5. Evidence chain: find papers treating lumbar stenosis with any endoscopic technique
MATCH (i:Intervention)-[:IS_A*0..3]->(parent:Intervention {name: 'Endoscopic Surgery'})
MATCH (p:Paper)-[:INVESTIGATES]->(i)
MATCH (p)-[:STUDIES]->(path:Pathology)-[:IS_A*0..3]->(pParent:Pathology {name: 'Spinal Stenosis'})
RETURN p.title, i.name, path.name
```

### Materialization: parent_code to Neo4j IS_A

```text
spine_snomed_mappings.py
  parent_code: "609588000"  (Interbody Fusion code)
       ↓
  schema.py: get_init_entity_taxonomy_cypher()
       ↓
  Neo4j: (TLIF)-[:IS_A]->(Interbody Fusion)
```

Scripts for IS_A management:
- `scripts/build_ontology.py`: Batch apply IS_A from SNOMED parent_code
- `scripts/repair_ontology.py`: Repair missing IS_A, SNOMED codes, TREATS
- `relationship_builder.py`: Auto IS_A on paper import via `_auto_create_is_a_relation()`

## Hybrid Ranking Algorithm

```python
# Evidence Level Weights
EVIDENCE_LEVEL_WEIGHTS = {
    "1a": 1.0,  # Meta-analysis
    "1b": 0.9,  # RCT
    "2a": 0.8,  # Cohort
    "2b": 0.7,  # Case-control
    "3": 0.5,   # Case series
    "4": 0.3,   # Expert opinion
    "5": 0.1,   # Unknown
}

# Three-way Ranking Formula (v1.24.0)
# 1. Semantic Score (40%) - Vector similarity with evidence boost
evidence_boost = 0.5 + 0.5 * evidence_weight
semantic_score = similarity * evidence_boost

# 2. Authority Score (30%) - Evidence level and statistical significance
p_score = 1.0 - p_value if p_value < 0.05 else 0.0
significance_boost = 1.5 if is_significant else 1.0
authority_score = evidence_weight * (1.0 + p_score) * significance_boost

# 3. Graph Relevance Score (30%) - IS_A hierarchy proximity
#    Boosted when query entity matches via IS_A expansion
graph_relevance_score = compute_graph_relevance(query_entities, result_entities)

# Combined Score
final_score = 0.4 * semantic_score + 0.3 * authority_score + 0.3 * graph_relevance_score
```

> **v1.24.0 변경**: 기존 2-way (graph 60% + vector 40%)에서 3-way (semantic 40% + authority 30% + graph_relevance 30%)로 전환.
> IS_A 계층 확장으로 graph_relevance가 더 정밀해짐.

## Neo4j Vector Index

- **Index**: `chunk_embedding_index`, `paper_abstract_index`
- **Dimensions**: 3072 (OpenAI text-embedding-3-large)
- **Algorithm**: HNSW (M=16, efConstruction=200)
- **Similarity**: Cosine

## SNOMED-CT Terminology Integration (v1.14.2)

모든 엔티티 노드 (Intervention, Pathology, Outcome, Anatomy)에 SNOMED-CT 코드가 자동으로 부여됩니다.

### 매핑 통계 (v1.24.0)

| Category | Total | Official SNOMED | Extension Codes |
|----------|-------|-----------------|-----------------|
| Intervention | 218 | 53 | 165 |
| Pathology | 214 | 73 | 141 |
| Outcome | 195 | 38 | 157 |
| Anatomy | 69 | 29 | 40 |
| **Total** | **735** | **193** | **503** |

### 주요 매핑 카테고리

#### Interventions

- Fusion Surgery: TLIF, PLIF, ALIF, OLIF, LLIF/XLIF, BELIF (v1.14.2)
- Decompression: Laminectomy, Discectomy, Foraminotomy, Facetectomy (v1.14.2)
- Endoscopic: UBE/BESS, FELD, PELD, MED
- Navigation: Stereotactic Navigation (v1.14.2)
- Osteotomy: SPO, PSO, VCR

#### Pathologies

- Degenerative: Stenosis, Disc Herniation, DDD, Spondylolisthesis
- Deformity: Scoliosis, Kyphosis, PJK, DJK (v1.14.1)
- Trauma: Fracture, Dislocation
- Tumor: Metastatic, Primary spinal tumor
- Neurological: Cervical Myelopathy, Radiculopathy (v1.14.1)
- Instability: Segmental Instability, Adjacent Segment Disease (v1.14.1)
- Comorbidities: Diabetes Mellitus

#### Outcomes

- Pain: VAS, NRS, ODI
- Function: JOA, mJOA, NDI, SF-36, EQ-5D
- Complications: SSI (Superficial/Deep), Dural Tear, Reoperation, Epidural Hematoma (v1.14)
- Radiographic: Fusion Rate, Lordosis, SVA
- Lab: Serum CPK (v1.14)
- Wound: Scar Quality, Postoperative Drainage, Wound Dehiscence (v1.14)

#### Anatomy

- Regions: Cervical, Thoracic, Lumbar, Sacral
- Levels: C1-C7, T1-T12, L1-L5, S1-S5
- Structures: Disc, Facet, Pedicle, Lamina

### Extension Code Ranges

| Range | Name | Description |
|-------|------|-------------|
| 900000000001xx | procedure | Intervention 기본 범위 |
| 900000000002xx | disorder | Pathology 기본 범위 |
| 900000000003xx | observable | Outcome 기본 범위 |
| 900000000004xx | body_structure | Anatomy 기본 범위 |
| 900000000005xx | finding | 합병증/소견 범위 |
| 900000000006xx | procedure_ext | Intervention 확장 범위 (v1.21.0) |
| 9000000000064x-069x | taxonomy_root | Taxonomy 루트 노드 (v1.24.0) |
| 900000000007xx | procedure_ext2 | Intervention 확장 범위 2 (v1.24.1) |
| 900000000008xx | observable_ext | Outcome 확장 범위 (v1.24.1) |
| 9000000000090x-094x | disorder_ext | Pathology 확장 범위 (v1.24.1) |

### Extension Codes (900000000000xxx)

SNOMED-CT에 아직 등록되지 않은 최신 수술법이나 척추 특이적 개념:

```text
# Interventions (900000000001xx)
UBE (Unilateral Biportal Endoscopy): 900000000000105
OLIF (Oblique Lumbar Interbody Fusion): 900000000000101
BELIF (Biportal Endoscopic LIF): 900000000000119
Stereotactic Navigation: 900000000000120
Facetectomy: 900000000000121 (v1.14.2)

# Interventions Extended (900000000006xx) ← v1.21.0
# 기존 1xx 범위 고갈에 따른 확장 범위

# Pathologies (900000000002xx)
Adjacent Segment Disease: 900000000000208
Segmental Instability: 900000000000206
DJK (Distal Junctional Kyphosis): 900000000000207
PJF (Proximal Junctional Failure): 900000000000234 (v1.21.0)
Proximal Junctional Kyphosis: 900000000000233 (v1.21.0, 기존 PJK에서 분리)
Central Canal Stenosis: 900000000000261 (v1.21.2)

# Outcomes (900000000003xx)
VAS Leg: 900000000000302
Serum CPK: 900000000000311
Scar Quality: 900000000000312
Postoperative Drainage: 900000000000313
Mortality: 900000000000371 (v1.21.2)
Functional Recovery: 900000000000372 (v1.21.2)
PROMs: 900000000000373 (v1.21.2)

# Findings (900000000005xx)
Wound Dehiscence: 900000000000503
Recurrent Disc Herniation: 900000000000504
Epidural Hematoma: 900000000000505
```

### SSI 분류 (v1.11)

| Type | SNOMED Code | Description |
|------|-------------|-------------|
| Infection Rate | 128601007 | 일반 수술 부위 감염 |
| Superficial SSI | 433202001 | 피부/피하조직 (표재성) |
| Deep SSI | 433201008 | 근육/임플란트 (심부) |

### 소스 파일

- `src/ontology/spine_snomed_mappings.py`: 전체 매핑 정의
- `src/graph/entity_normalizer.py`: 정규화 및 SNOMED 코드 조회

---

## SNOMED CT 아키텍처 설계 (Architecture Decision Record)

> **결정 일자**: v1.24.0 | **상태**: Accepted

### 설계 선택: Embedded Properties vs Separate Ontology Layer

우리 시스템은 SNOMED CT를 통합하는 두 가지 주요 패턴 중 **"Embedded SNOMED Properties"** 방식을 채택합니다.

- **채택 방식**: 도메인 노드(Intervention, Pathology, Outcome, Anatomy)에 `snomed_code` / `snomed_term` 속성을 직접 내장
- **대안 방식**: 별도 `:SNOMED_Concept` 노드를 생성하고 엣지로 연결하는 "Separate Ontology Layer" 패턴

### 비교 테이블

| 설계 차원 | 정석 (Separate Ontology) | 우리 시스템 (Embedded Properties) |
|-----------|--------------------------|-----------------------------------|
| **SNOMED 노드** | 별도 `:SNOMED_Concept` 노드 생성 | 도메인 노드에 `snomed_code` 속성 내장 |
| **연결 방식** | `(:Entity)-[:HAS_SNOMED_CONCEPT]->(:SNOMED_Concept)` 엣지 | `snomed_code` / `snomed_term` 속성 필터 |
| **IS_A 계층** | `(:SNOMED_Concept)-[:IS_A]->(:SNOMED_Concept)` (개념 간) | `(:Intervention)-[:IS_A]->(:Intervention)` (동일 레이블 내) |
| **데이터 소스** | RF2 전체 import (36만+ 개념) | Python dict 735개 도메인 특화 매핑 |
| **검색 연동** | SNOMED_Concept 그래프 경로 탐색 | 속성 필터 + IS_A 다중 홉 확장 |

### 노드 구조 비교

#### 정석 방식 (Separate Ontology Layer)

```cypher
// SNOMED_Concept 노드가 별도 존재하고 도메인 엔티티가 엣지로 연결
(:Chunk)-[:MENTIONS]->(:Intervention {name: "TLIF"})
  -[:HAS_SNOMED_CONCEPT]->(:SNOMED_Concept {code: "447764006", term: "Transforaminal lumbar interbody fusion"})
    -[:IS_A]->(:SNOMED_Concept {code: "609588000", term: "Interbody Fusion"})
      -[:IS_A]->(:SNOMED_Concept {code: "122465003", term: "Spine Surgery"})
```

#### 우리 시스템 (Embedded Properties)

```cypher
// snomed_code/snomed_term이 도메인 노드 속성으로 내장, IS_A는 동일 레이블 내
(:Paper)-[:INVESTIGATES]->(:Intervention {
    name: "TLIF",
    snomed_code: "447764006",
    snomed_term: "Transforaminal lumbar interbody fusion"
})-[:IS_A]->(:Intervention {
    name: "Interbody Fusion",
    snomed_code: "609588000"
})-[:IS_A]->(:Intervention {
    name: "Spine Surgery",
    snomed_code: "122465003"
})
```

### 검색 쿼리 비교

#### 정석 방식: SNOMED_Concept 노드 경유

```cypher
// "Interbody Fusion" 계열 수술을 다루는 논문 조회
MATCH (sc:SNOMED_Concept {code: "609588000"})<-[:IS_A*0..2]-(child:SNOMED_Concept)
MATCH (i:Intervention)-[:HAS_SNOMED_CONCEPT]->(child)
MATCH (p:Paper)-[:INVESTIGATES]->(i)
RETURN p.title, i.name, child.term
```

#### 우리 시스템: 벡터 인덱스 + 속성 필터 + IS_A 다중 홉

```cypher
// Vector index로 청크 후보 검색 후, IS_A 계층으로 관련 논문 확장
CALL db.index.vector.queryNodes('chunk_embedding_index', 10, $query_embedding)
YIELD node AS chunk, score
MATCH (p:Paper)-[:HAS_CHUNK]->(chunk)
MATCH (p)-[:INVESTIGATES]->(i:Intervention)
WHERE i.snomed_code = "447764006"
   OR EXISTS {
       MATCH (i)-[:IS_A*1..2]->(parent:Intervention)
       WHERE parent.snomed_code = "609588000"
   }
RETURN p.title, i.name, score
ORDER BY score DESC
```

### 우리 설계의 장단점

#### 장점

| 항목 | 설명 |
|------|------|
| **단순성** | 별도 SNOMED 노드 계층 없이 도메인 노드만으로 그래프 구성 |
| **단일 저장소** | Neo4j 하나에 Graph + Vector 통합, 별도 SNOMED 트리플 스토어 불필요 |
| **도메인 특화** | 36만+ RF2 전체 대신 척추 외과 735개 핵심 개념만 관리 |
| **Vector+Graph 통합** | 벡터 유사도 검색과 IS_A 계층 탐색을 단일 Cypher 쿼리에서 처리 |

#### 단점

| 항목 | 설명 |
|------|------|
| **관계 유형 제한** | IS_A만 구현; 표준 SNOMED의 CAUSES, HAS_FINDING, HAS_BODY_STRUCTURE 미구현 |
| **Chunk↔SNOMED 직접 링크 없음** | Chunk 노드가 SNOMED 코드와 직접 연결되지 않아 청크 수준 온톨로지 필터 불가 |
| **RF2 호환성 없음** | 표준 SNOMED RF2 도구(Snowstorm 등)와 직접 통합 불가 |

#### 보완 전략

- **CAUSES 부재 보완**: `AFFECTS` 관계가 `(Intervention)-[:AFFECTS]->(Outcome)`으로 통계적 인과 연관을 표현
- **HAS_FINDING 부재 보완**: `Paper` 노드 경유 간접 연결 — `(Pathology)-[:STUDIES]->(:Paper)<-[:AFFECTS]-(:Outcome)` 경로로 소견 조회 가능
- **Chunk 정밀도 보완**: 3072차원 벡터 검색이 Chunk 수준 의미 매칭을 담당하여 SNOMED 직접 링크의 공백을 보완

### 임상 관계 매핑

표준 SNOMED CT 관계와 우리 시스템의 Paper-centric 관계 대응표:

| SNOMED 관계 | 우리 시스템 대응 | 차이 |
|-------------|----------------|------|
| `TREATS` | `(Intervention)-[:TREATS]->(Pathology)` | 동일 의미, 직접 구현 |
| `CAUSES` | `(Intervention)-[:AFFECTS]->(Outcome)` | 인과 대신 통계적 연관으로 표현 |
| `HAS_FINDING` | Paper 경유 간접: `(Pathology)<-[:STUDIES]-(:Paper)-[:INVESTIGATES]->(:Intervention)` | 직접 링크 없음, 2홉 경로 |
| `HAS_BODY_STRUCTURE` | Paper 경유 간접: `(Intervention)<-[:INVESTIGATES]-(:Paper)-[:INVOLVES]->(Anatomy)` | 직접 링크 없음, 2홉 경로 |
| `ASSOCIATED_WITH` | 미구현 (Cost↔Intervention에 동명 관계 있으나 SNOMED 의미 아님) | 미구현 |

### v1.27.0 구현 완료

다음 항목은 v1.27.0에서 구현 완료:

| 구현 항목 | 설명 | 상태 |
|-----------|------|------|
| **Chunk↔Entity MENTIONS 관계** | `(:Chunk)-[:MENTIONS]->(:Intervention\|:Pathology\|:Outcome\|:Anatomy)` 직접 링크로 청크 수준 온톨로지 필터 활성화 | 완료 |
| **Intervention→Anatomy APPLIED_TO** | `(Intervention)-[:APPLIED_TO]->(Anatomy)` 직접 관계로 HAS_BODY_STRUCTURE 의미 구현 | 완료 |
| **IS_A 확장 병렬 처리** | `build_ontology.py` 비동기 배치 처리로 대용량 IS_A 구축 속도 개선 | 완료 |
