# Spine GraphRAG Schema

## Node Types

### Core Nodes

| Node | Key Properties | Description |
|------|----------------|-------------|
| Paper | paper_id, title, year, evidence_level, sub_domain | 논문 |
| Pathology | name, category, snomed_code, snomed_term | 질환 |
| Anatomy | level, region, snomed_code, snomed_term | 해부학적 위치 |
| Intervention | name, category, aliases, snomed_code, snomed_term | 수술법 |
| Outcome | name, category, unit, snomed_code, snomed_term | 결과 변수 |
| Chunk | chunk_id, paper_id, tier, section, evidence_level, embedding | 논문 텍스트 청크 (벡터 임베딩 포함) |

### v7.1 Extended Entity Nodes

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

### v7.2 Extended Nodes

| Node | Key Properties | Description |
|------|----------------|-------------|
| PatientCohort | name, cohort_type, sample_size, mean_age | 환자 코호트 |
| FollowUp | name, timepoint_months, completeness_rate | 추적관찰 시점 |
| Cost | name, cost_type, mean_cost, qaly_gained, icer | 의료비용 |
| QualityMetric | name, assessment_tool, overall_score | 연구품질평가 |

## Relationship Types

### Core Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| STUDIES | Paper → Pathology | is_primary | 논문이 연구하는 질환 |
| INVOLVES | Paper → Anatomy | | 논문이 다루는 해부학적 위치 |
| LOCATED_AT | Pathology → Anatomy | | 질환의 해부학적 위치 *(Planned)* |
| INVESTIGATES | Paper → Intervention | is_comparison | 논문이 조사하는 수술법 |
| AFFECTS | Intervention → Outcome | value, p_value, effect_size, is_significant | 수술법의 결과 영향 |
| TREATS | Intervention → Pathology | indication, source_paper_id | 수술법이 치료하는 질환 (v7.16.1 구현) |
| IS_A | Intervention → Intervention | | Taxonomy 계층 관계 |
| HAS_CHUNK | Paper → Chunk | | 논문의 텍스트 청크 |

### Paper-to-Paper Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| CITES | Paper → Paper | | 인용 관계 |
| SUPPORTS | Paper → Paper | confidence | 결과를 지지하는 관계 |
| CONTRADICTS | Paper → Paper | confidence | 결과가 상충하는 관계 |
| SIMILAR_TOPIC | Paper ↔ Paper | confidence | 유사 주제 관계 (양방향) |
| EXTENDS | Paper → Paper | confidence | 후속/확장 연구 관계 |
| REPLICATES | Paper → Paper | confidence | 재현 연구 관계 |

### v7.1 Extended Relationships

| Relationship | Start → End | Key Properties | Description |
|--------------|-------------|----------------|-------------|
| CAUSES | Intervention → Complication | | 수술로 인한 합병증 |
| HAS_RISK_FACTOR | Paper → RiskFactor | | 논문에서 식별된 위험인자 |
| PREDICTS | PredictionModel → Outcome | | 예측 모델의 타겟 결과 |
| USES_FEATURE | PredictionModel → RiskFactor | | 예측 모델이 사용하는 변수 |
| CORRELATES | RadioParameter → OutcomeMeasure | | 영상 파라미터와 결과의 상관관계 |
| USES_DEVICE | Intervention → Implant | | 수술에 사용되는 임플란트 |
| MEASURED_BY | Outcome → OutcomeMeasure | | 결과 측정 도구 *(Planned)* |

### v7.2 Extended Relationships

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
│   │   └── BELIF (BE-TLIF) ← v7.14.2 추가
│   └── Posterolateral Fusion
├── Decompression Surgery
│   ├── Open Decompression
│   │   ├── Laminectomy, Laminotomy, Foraminotomy
│   │   └── Facetectomy ← v7.14.2 추가
│   └── Endoscopic Surgery
│       └── UBE (Biportal), FELD, PELD, MED
├── Fixation
│   ├── Pedicle Screw, Lateral Mass Screw
│   └── Stereotactic Navigation ← v7.14.2 추가
├── Motion Preservation
│   └── ADR, Dynamic Stabilization
└── Osteotomy
    └── SPO, PSO, VCR
```

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

# Graph Score (구조화된 근거)
evidence_weight = EVIDENCE_LEVEL_WEIGHTS[level]
p_score = 1.0 - p_value if p_value < 0.05 else 0.0
significance_boost = 1.5 if is_significant else 1.0
graph_score = evidence_weight * (1.0 + p_score) * significance_boost

# Vector Score (시맨틱 관련성)
evidence_boost = 0.5 + 0.5 * evidence_weight
vector_score = similarity * evidence_boost

# Combined Score
final_score = 0.6 * graph_score + 0.4 * vector_score
```

## Neo4j Vector Index

- **Index**: `chunk_embedding_index`, `paper_abstract_index`
- **Dimensions**: 3072 (OpenAI text-embedding-3-large)
- **Algorithm**: HNSW (M=16, efConstruction=200)
- **Similarity**: Cosine

## SNOMED-CT Terminology Integration (v7.14.2)

모든 엔티티 노드 (Intervention, Pathology, Outcome, Anatomy)에 SNOMED-CT 코드가 자동으로 부여됩니다.

### 매핑 통계

| Category | Total | Official SNOMED | Extension Codes |
|----------|-------|-----------------|-----------------|
| Intervention | 122 | 44 | 78 |
| Pathology | 84 | 55 | 29 |
| Outcome | 68 | 19 | 49 |
| Anatomy | 30 | 24 | 6 |
| **Total** | **304** | **142** | **162** |

### 주요 매핑 카테고리

#### Interventions

- Fusion Surgery: TLIF, PLIF, ALIF, OLIF, LLIF/XLIF, BELIF (v7.14.2)
- Decompression: Laminectomy, Discectomy, Foraminotomy, Facetectomy (v7.14.2)
- Endoscopic: UBE/BESS, FELD, PELD, MED
- Navigation: Stereotactic Navigation (v7.14.2)
- Osteotomy: SPO, PSO, VCR

#### Pathologies

- Degenerative: Stenosis, Disc Herniation, DDD, Spondylolisthesis
- Deformity: Scoliosis, Kyphosis, PJK, DJK (v7.14.1)
- Trauma: Fracture, Dislocation
- Tumor: Metastatic, Primary spinal tumor
- Neurological: Cervical Myelopathy, Radiculopathy (v7.14.1)
- Instability: Segmental Instability, Adjacent Segment Disease (v7.14.1)
- Comorbidities: Diabetes Mellitus

#### Outcomes

- Pain: VAS, NRS, ODI
- Function: JOA, mJOA, NDI, SF-36, EQ-5D
- Complications: SSI (Superficial/Deep), Dural Tear, Reoperation, Epidural Hematoma (v7.14)
- Radiographic: Fusion Rate, Lordosis, SVA
- Lab: Serum CPK (v7.14)
- Wound: Scar Quality, Postoperative Drainage, Wound Dehiscence (v7.14)

#### Anatomy

- Regions: Cervical, Thoracic, Lumbar, Sacral
- Levels: C1-C7, T1-T12, L1-L5, S1-S5
- Structures: Disc, Facet, Pedicle, Lamina

### Extension Codes (900000000000xxx)

SNOMED-CT에 아직 등록되지 않은 최신 수술법이나 척추 특이적 개념:

```text
# Interventions (900000000001xx)
UBE (Unilateral Biportal Endoscopy): 900000000000105
OLIF (Oblique Lumbar Interbody Fusion): 900000000000101
BELIF (Biportal Endoscopic LIF): 900000000000119
Stereotactic Navigation: 900000000000120
Facetectomy: 900000000000121 (v7.14.2)

# Pathologies (900000000002xx)
Adjacent Segment Disease: 900000000000208
Segmental Instability: 900000000000206
DJK (Distal Junctional Kyphosis): 900000000000207

# Outcomes (900000000003xx)
VAS Leg: 900000000000302
Serum CPK: 900000000000311
Scar Quality: 900000000000312
Postoperative Drainage: 900000000000313

# Findings (900000000005xx)
Wound Dehiscence: 900000000000503
Recurrent Disc Herniation: 900000000000504
Epidural Hematoma: 900000000000505
```

### SSI 분류 (v7.11)

| Type | SNOMED Code | Description |
|------|-------------|-------------|
| Infection Rate | 128601007 | 일반 수술 부위 감염 |
| Superficial SSI | 433202001 | 피부/피하조직 (표재성) |
| Deep SSI | 433201008 | 근육/임플란트 (심부) |

### 소스 파일

- `src/ontology/spine_snomed_mappings.py`: 전체 매핑 정의
- `src/ontology/entity_normalizer.py`: 정규화 및 SNOMED 코드 조회
