# Spine GraphRAG 논문 출판 계획

> **작성일**: 2026-03-16 | **Version**: 1.0
> **프로젝트**: Spine GraphRAG (Medical KAG) v1.25.0
> **교신저자**: Prof. Sang-Min Park, SNU Bundang Hospital

---

## 1. 문헌 환경 분석 (Literature Landscape)

### 1.1 관련 논문 분류

#### Category A: KG + LLM 기반 의학 문헌 분석 (직접 경쟁)

| # | 논문 | 핵심 내용 | 우리와의 차이 |
|---|------|----------|-------------|
| 1 | Lotz 2023 — Knowledge-organizing technologies for back pain research | GPT-3 + Knowledge Graph + Similarity Graph로 LBP 문헌을 biopsychosocial 모델별 통합 분석 | **가장 유사한 선행연구**. 단, LBP에 한정, GPT-3(구형), 수술법 비교 없음, SNOMED 매핑 없음, evidence ranking 없음 |
| 2 | Cai 2026 — LEAP: LLM-Enhanced Automated Phenotyping | LLM + Sentence Transformer로 EHR에서 HPO 온톨로지 매핑 자동화 (F1 44-299%↑) | 온톨로지 매핑 방법론은 유사하나, 대상이 EHR phenotyping (문헌 검색이 아님) |

#### Category B: NLP/LLM 데이터 추출 (간접 관련)

| # | 논문 | 핵심 내용 | 관계 |
|---|------|----------|------|
| 3 | Mani 2025 — Multimodal NLP for perioperative safety | EHR + NLP(수술기록) 결합 multimodal → LOS 예측 AUC 0.91 | 데이터 추출 방법론 참고 |
| 4 | Kanani 2025 — LLM extraction of compression fractures | Llama 3.1 70B로 방사선 보고서에서 골절 추출 F1=0.91 | 프롬프트 기반 추출 비교 대상 |
| 5 | Park 2025 — LLM classification of tumor response | Llama3로 척추 MRI 보고서 종양 반응 분류 AUROC 0.94 | 의학 보고서 분류 선행 연구 |
| 6 | Mani 2023 — NLP classification of spine surgery | 동의서에서 7가지 척추 수술 유형 자동 분류 91% | entity 분류 baseline |

#### Category C: LLM 임상 의사결정 지원 (차별화 대상)

| # | 논문 | 핵심 내용 | 한계점 (우리의 기회) |
|---|------|----------|-------------------|
| 7 | Kartal 2025 — LLMs for MISS triage | GPT-5 Pro, Gemini 2.5 Pro로 MIS 수술 triage κ=0.587-0.692 | **LLM 직접 질문 방식** — 근거 없이 답변, hallucination 위험 |
| 8 | Najjar 2025 — ChatGPT vs MDT in CES | CES 수술 결정에서 ChatGPT vs MDT 88.7% 일치 | 근거 기반이 아닌 LLM 자체 지식에 의존 |
| 9 | Tuncer 2026 — AI models for spinal decisions | 다중 AI 모델의 척추 신경외과 + 물리치료 의사결정 비교 | 모델 간 비교만, 근거 합성 없음 |
| 10 | Chan 2025 — LLM-assisted SINS calculation | LLM으로 SINS 계산 ICC=0.990, 시간 83초→5초 | 단일 점수 계산에 한정 |
| 11 | Prasad 2025 — LLM for imaging in back pain | GPT-4로 영상 적절성 판단, ACR 기준과 72% 일치 | 가이드라인 준수 검증만 |

#### Category D: LLM 분류 능력 평가

| # | 논문 | 핵심 내용 | 시사점 |
|---|------|----------|--------|
| 12 | Aktan 2025 — LLM reliability in Lenke classification | Multimodal LLM Lenke 분류 κ=0.001-0.036 (전문의 0.913) | **LLM 단독 사용은 신뢰 불가** → Knowledge Graph 필요성 근거 |
| 13 | Khalsa 2026 — AI-assisted SSI risk calculator | GPT-4로 문헌 합성 → SSI 위험 점수 AUC 0.80 | 문헌 합성에 LLM 활용, 단 체계적이지 않음 |

#### Category E: AI + 척추 예측/리뷰

| # | 논문 | 핵심 내용 | 관계 |
|---|------|----------|------|
| 14 | Muthu 2026 — AI/ML in cervical myelopathy | 경추 척수증 AI/ML 예측 scoping review | 배경 문헌으로 인용 |
| 15 | Pan 2025 — AI-simplified operative reports | GPT-4로 수술 기록 환자용 간소화, 이해도 86.4 vs 73.7 | LLM의 의학 텍스트 변환 능력 입증 |

### 1.2 핵심 연구 갭 (Research Gap)

```
현재 문헌 현황:
├── LLM 직접 질문 ("ChatGPT에게 물어보기") ← 대부분의 논문 (Cat C)
│   └── 문제: 근거 없음, hallucination, 재현 불가
├── NLP 데이터 추출 (Cat B)
│   └── 문제: 추출만 하고 통합/합성 없음
├── KG + LLM 통합 (Cat A)
│   └── Lotz 2023 하나뿐, LBP에 한정
└── ★ 비어 있는 영역 ★
    ├── 체계적 Knowledge Graph + LLM + 온톨로지 + Evidence Ranking
    ├── 수술법 간 자동 비교 (evidence chain)
    └── SNOMED-CT 기반 척추 전문 온톨로지
```

**핵심 차별화**: 기존 연구 대부분이 "LLM에게 직접 질문"하는 방식인 반면,
우리 시스템은 **구조화된 Knowledge Graph에서 근거를 검색**하여 LLM에 제공하므로:
- Hallucination 방지 (모든 답변에 출처 논문 제시)
- 재현 가능 (같은 질문 → 같은 검색 결과)
- Evidence level 기반 품질 보장

---

## 2. 논문 출판 전략

### 2.1 전체 구조: 4편 논문 (핵심 집중)

```
Phase 0 (공통)     Evaluation 인프라 구축 ──────────────────────────┐
                                                                    │
Phase 1 (기반)     Paper 1: System Architecture (JMIR) ◄───────────┤
                                                                    │
Phase 2 (확장)     Paper 2: SNOMED Ontology (IJMI) ◄───────────────┤
                   Paper 3: Evidence Synthesis (Spine J) ◄─────────┤
                                                                    │
Phase 3 (응용)     Paper 4: Clinical Decision Support (NF) ◄───────┘
```

우선순위: **P1 (기반) → P3 (임상 가치 최고) → P4 (임상 현장) → P2 (자원 공개)**
P1이 나머지 3편의 인용 기반. P3가 임상적으로 가장 의미 있음.

---

## 3. Phase 0: 공통 인프라 구축 (Month 1-2)

### 3.1 Gold Standard Query-Answer Set

| 항목 | 내용 |
|------|------|
| **목표** | 전문가 검증 임상 질의-정답 세트 |
| **규모** | 100-150개 clinical question |
| **구성** | 5개 sub-domain × 20-30문항 |
| **검증** | 척추외과 전문의 2-3명 독립 평가 |

#### Sub-domain 분포

| Domain | 문항 수 | 예시 질문 |
|--------|---------|----------|
| Degenerative | 30 | "L4-5 stenosis에서 UBE vs TLIF의 ODI 개선 비교 근거는?" |
| Deformity | 25 | "AIS Lenke 1A에서 UIV 결정 시 고려할 근거는?" |
| Trauma | 25 | "흉요추부 burst fracture에서 short vs long segment fixation 근거?" |
| Tumor | 20 | "척추 전이암에서 SINS > 12일 때 수술적 치료 근거?" |
| Basic Science | 20 | "BMP-2의 cage fusion에 대한 효과 메타분석 근거?" |

#### 질문 유형 (5종)

| 유형 | 비율 | 설명 |
|------|------|------|
| T1: 단일 치료법 근거 | 25% | "ACDF의 인접분절 퇴행 발생률 근거?" |
| T2: 치료법 비교 | 30% | "CDR vs ACDF 2-level 경추 비교?" |
| T3: 합병증/예후 | 20% | "MIS-TLIF 후 cage subsidence 위험인자?" |
| T4: 해부학적 적응증 | 15% | "C5-6 myelopathy에서 anterior vs posterior 접근?" |
| T5: 최신 근거 수준 | 10% | "로봇 척추 수술의 최신 RCT 근거?" |

### 3.2 비교 Baseline 시스템

| Baseline | 방법 | 기존 논문과의 대응 |
|----------|------|-------------------|
| **B1: Keyword** | Neo4j fulltext index만 사용 | PubMed 검색과 유사 |
| **B2: Vector-only (RAG)** | 임베딩 유사도만 (semantic=1.0, authority=0, graph=0) | 일반적인 RAG 시스템 |
| **B3: LLM Direct** | Claude에게 직접 질문 (KG 없이) | Kartal 2025, Najjar 2025와 동일한 접근 |
| **B4: GraphRAG (본 시스템)** | 3-way hybrid (0.4/0.3/0.3) | **본 시스템** |

### 3.3 평가 메트릭 (v2 — RAGAS 기반 End-to-End 평가)

> **변경 근거**: 전통적 IR 메트릭(P@K, NDCG)은 전문의 annotation이 필수이며,
> 전문 DB에서는 검색 결과 대부분이 관련 있어 차별화가 어려움.
> 최신 Medical GraphRAG 논문들(Wu 2025 ACL, medRxiv 2025)은
> **End-to-End 답변 품질 평가** 방식을 사용.

#### Phase A: 자동 평가 (전문의 불필요, LLM-as-Judge)

각 baseline이 질문에 대해 **답변을 생성**하고, 그 답변의 질을 LLM이 평가:

```
질문 → [Baseline 검색 → 검색 결과 기반 답변 생성] → LLM Judge 평가

평가 대상: "검색된 논문 목록"이 아니라 "최종 답변"
```

| 메트릭 | 측정 내용 | 방법 | 스케일 |
|--------|----------|------|--------|
| **Faithfulness** | 답변의 모든 주장이 인용 논문에 근거하는가? | LLM-as-Judge (claim 분해 → 출처 대조) | 0.0-1.0 |
| **Citation Fidelity** | 인용된 논문이 실제로 해당 주장을 뒷받침하는가? | LLM이 abstract와 claim 비교 | 0.0-1.0 |
| **Answer Relevancy** | 답변이 질문에 적절히 대답하는가? | LLM-as-Judge | 0.0-1.0 |
| **Hallucination Rate** | DB에 없는 논문/사실을 인용한 비율 | 자동 검증 (PMID 존재 여부) | 0-100% |
| **Evidence Level** | 인용 논문의 평균 OCEBM 근거 수준 | 자동 계산 | 1-7 |
| **Completeness** | 중요한 포인트를 빠뜨리지 않았는가? | LLM-as-Judge | 0.0-1.0 |

참고 논문:
- Medical Graph RAG (Wu 2025, ACL): 9개 QA 벤치마크 + RAGAS
- GraphRAG for CKD (medRxiv 2025): 전문의 + LLM-as-Judge
- Agentic GraphRAG Hepatology (PMC 2025): RAGAS faithfulness 0.94
- USMLE GraphRAG (medRxiv 2025): citation fidelity 중심

#### Phase B: 전문의 평가 (소규모, 10-15개 질문)

| 메트릭 | 설명 | 스케일 |
|--------|------|--------|
| **Clinical Correctness** | 답변이 의학적으로 정확한가? | 5-point Likert |
| **Completeness** | 빠진 중요 근거가 없는가? | 5-point Likert |
| **Clinical Usefulness** | 실제 임상 결정에 도움이 되는가? | 5-point Likert |

> Phase A만으로도 Paper 1 투고 가능. Phase B를 추가하면 reviewer 설득력 강화.

### 3.4 논문 DB 확보 ✅ 완료 (2026-03-16)

| 항목 | 목표 | 실제 |
|------|------|------|
| Neo4j 내 논문 수 | 최소 500편 | **624편** ✅ |
| Degenerative | 80편+ | **384편** ✅ |
| Deformity | 80편+ | **91편** ✅ |
| Basic Science | 80편+ | **55편** (추가 필요) |
| Trauma | 80편+ | **29편** (추가 필요) |
| Tumor | 80편+ | **44편** (추가 필요) |

> 2026-03-16: PubMed에서 TR 20편, TU 20편, BS 20편 임포트 완료.
> Entity 추출은 Claude Code CLI에서 직접 수행 (Haiku API 비용 0).
> 60편 모두 summary, main_conclusion, abstract_embedding(3072d) 포함.

### 3.5 구현 현황 ✅ 완료 (2026-03-16)

```
evaluation/
├── __init__.py          # ✅
├── metrics.py           # ✅ P@K, R@K, NDCG, MRR, ELA (28 tests passed)
├── baselines.py         # ✅ B1(keyword), B2(vector), B3(LLM direct), B4(GraphRAG)
├── benchmark.py         # ✅ 벤치마크 실행기 + CLI
├── annotator_helper.py  # ✅ 후보 논문 자동 검색 (517편 생성)
├── import_to_neo4j.py   # ✅ PubMed → Neo4j 임포트
├── update_summaries.py  # ✅ Summary/conclusion Neo4j 업데이트
├── gold_standard/
│   ├── questions.json   # ✅ 29개 질문 (DG:10, DF:5, TR:5, TU:4, BS:5)
│   ├── answers.json     # ⬜ 전문의 annotation 대기 (Phase B용)
│   └── annotation_sheet.json  # ✅ 517편 후보 (전문의 검토용)
└── results/
    └── *.json           # ⬜ 실험 실행 후 저장
```

### 3.6 추가 구현 필요 (v2 평가 방식)

```
evaluation/
├── answer_generator.py  # ⬜ 각 baseline 검색 결과 → LLM 답변 생성
├── llm_judge.py         # ⬜ Faithfulness, Citation Fidelity, Relevancy 자동 평가
└── ragas_metrics.py     # ⬜ RAGAS 스타일 메트릭 계산
```

---

## 4. Phase 1: Flagship System Paper (Month 3-4)

### Paper 1: System Architecture + Performance Validation

| 항목 | 내용 |
|------|------|
| **제목(안)** | "Spine GraphRAG: A Knowledge Graph-Enhanced Retrieval-Augmented Generation System for Evidence-Based Spine Surgery Literature Synthesis" |
| **타겟 저널** | **1순위**: Journal of Medical Internet Research (JMIR, IF ~7.0) |
| | **2순위**: Journal of Biomedical Informatics (JBI, IF ~4.5) |
| | **3순위**: AMIA Annual Symposium Proceedings |
| **논문 유형** | Original Research (Systems & Methods) |

#### Positioning (vs 선행연구)

| 비교 대상 | 우리의 차별화 |
|----------|-------------|
| **Lotz 2023** (가장 유사) | LBP에 한정 vs **전 척추 영역** 포괄; GPT-3 vs Claude Haiku 4.5; 단순 그래프 vs **SNOMED-CT 온톨로지 기반 IS_A 계층**; 유사도만 vs **3-way evidence-based ranking** |
| **Cai 2026** (LEAP) | EHR phenotyping vs **문헌 검색/합성**; HPO vs **SNOMED-CT 735코드**; 단일 매핑 vs **다국어 정규화 + IS_A 확장** |
| **Cat C 논문들** (Kartal, Najjar 등) | LLM 직접 질문 vs **KG 기반 근거 검색 후 LLM 합성**; 근거 없음 vs **OCEBM 근거 수준 추적**; hallucination 위험 vs **출처 논문 명시** |
| **Aktan 2025** | LLM 단독은 κ=0.001 (Lenke 분류 실패) → **KG가 LLM의 한계를 보완한다는 근거** |

#### 실험 설계 (v2 — End-to-End 답변 품질 평가)

| 실험 | 비교 | 평가 방법 | 예상 결과 |
|------|------|----------|----------|
| **Exp 1**: End-to-End 답변 품질 | B1 vs B2 vs B3 vs **B4** | Faithfulness, Citation Fidelity, Answer Relevancy, Completeness (LLM-as-Judge) | B4 > B2 > B1 전 메트릭, B4 >> B3 (faithfulness) |
| **Exp 2**: Hallucination 비교 | B3(LLM direct) vs B4 | Hallucination Rate (자동 PMID 검증) + Citation Fidelity | B4 ≈ 0% (출처 명시), B3 > 15% |
| **Exp 3**: Evidence Level 비교 | B1 vs B2 vs B4 | 인용 논문의 평균 OCEBM 수준 (자동) | B4가 Level 1-2 논문을 더 많이 인용 |
| **Exp 4**: Ablation study | B4에서 각 요소 제거 | 동일 6개 메트릭으로 각 요소 기여도 측정 | Authority + Graph 제거 시 evidence quality/faithfulness 하락 |
| **Exp 5**: IS_A expansion 효과 | 확장 ON vs OFF | Completeness, 인용 논문 다양성 | 확장 시 더 넓은 범위의 관련 논문 인용 |
| **Exp 6**: 전문의 검증 (Phase B) | B3 vs B4 (10-15개 질문) | Clinical Correctness, Completeness, Usefulness (5점 Likert) | B4가 전문의 평가에서 유의하게 우수 |

#### Figure/Table 구성

| # | Type | 내용 |
|---|------|------|
| Fig 1 | Architecture | PDF → Claude Haiku → Neo4j (Graph+Vector) → 3-way Ranking → Answer |
| Fig 2 | Diagram | 3-way ranking formula + IS_A expansion + 답변 생성 파이프라인 |
| Fig 3 | Radar chart | 4개 baseline × 6개 메트릭 비교 (faithfulness, citation fidelity, relevancy, completeness, evidence level, hallucination) |
| Fig 4 | Bar chart | Ablation study — 각 요소 제거 시 메트릭 변화 |
| Fig 5 | Box plot | Evidence Level 분포 (baseline별) |
| Fig 6 | Example | 동일 질문에 대한 B3 vs B4 답변 비교 (hallucination 사례) |
| Table 1 | | Dataset 통계 (624편, domain 분포, entity 수, 질문 29개) |
| Table 2 | | End-to-End 답변 품질 전체 비교 (6개 메트릭 × 4개 baseline) |
| Table 3 | | Hallucination 상세 분석 — B3 vs B4 |
| Table 4 | | IS_A expansion ON/OFF 비교 |
| Table 5 | | 전문의 평가 결과 (Likert 평균, 95% CI) |

#### Introduction 핵심 논리 흐름

```
1. 척추 수술 문헌은 연간 수천 편 → 최신 근거 파악이 임상의에게 부담
2. 기존 접근법의 한계:
   a. PubMed 키워드 검색 — 의미적 검색 불가, 근거 수준 고려 없음
   b. 일반 RAG (Vector search) — 구조화된 의학 지식 반영 불가
   c. LLM 직접 질문 — hallucination, 근거 없음 (Aktan 2025: κ=0.001)
3. Knowledge Graph + LLM 통합 시도가 있으나 (Lotz 2023) LBP에 한정
4. ★ 본 연구: SNOMED-CT 온톨로지 + Evidence Ranking + Hybrid Search를
   통합한 최초의 전 척추 영역 Knowledge Graph 시스템
```

---

## 5. Phase 2: Domain-Specific Papers (Month 5-7)

### Paper 2: SNOMED-CT Ontology + Entity Normalization

| 항목 | 내용 |
|------|------|
| **제목(안)** | "A Domain-Specific SNOMED-CT Ontology for Spine Surgery: 735-Code Hierarchical Mapping with Automated Multilingual Normalization" |
| **타겟 저널** | **1순위**: International Journal of Medical Informatics (IJMI, IF ~4.7) |
| | **2순위**: Journal of Biomedical Semantics (IF ~2.3) |
| | **3순위**: Applied Clinical Informatics |
| **논문 유형** | Resource Paper / Methods |

#### Positioning

| 비교 대상 | 차별화 |
|----------|--------|
| **Cai 2026** (LEAP) | HPO 매핑 (phenotype 중심) vs **SNOMED-CT 4개 entity type** (I/P/O/A); EHR 대상 vs **문헌 대상**; 자동 매핑만 vs **IS_A 계층 + 수동 큐레이션 + LLM 제안** |
| **IHTSDO SNOMED subsets** | 범용적 vs **척추 수술 특화**; 개별 코드만 vs **IS_A parent hierarchy로 추론 지원** |
| **Mani 2023** (NLP surgery classification) | 7개 수술 유형 vs **235개 intervention 코드 + 계층** |

#### 핵심 기여

1. **735개 SNOMED-CT 매핑** (I:235, P:231, O:200, A:69) — 척추 수술 최대 규모
2. **IS_A 계층 구조** — parent_code 기반 온톨로지 추론 (depth 1-5)
3. **다국어 정규화** — 한/영 fuzzy matching, 280+ 동의어 변형
4. **LLM-based SNOMED Proposer** — 미등록 용어 자동 매핑 제안
5. **공개 자원** — CSV/JSON 형식으로 커뮤니티 배포

#### 실험 설계

| 실험 | 내용 | 메트릭 | annotation 필요? |
|------|------|--------|:---:|
| **Exp 1**: Coverage 분석 | 624편 논문에서 추출된 entity 중 SNOMED 매핑 비율 | Coverage% per entity type (I/P/O/A) | 불필요 |
| **Exp 2**: Normalization 정확도 | 200개 raw term → normalized term 자동 변환 | Precision, Recall, F1 (LLM-as-Judge로 정답 대조) | 불필요 |
| **Exp 3**: LLM Proposer 평가 | 자동 제안 SNOMED 코드의 적합성 | Acceptance rate, Precision (전문의 10분 리뷰) | 최소 |
| **Exp 4**: IS_A 구조 무결성 | Circular ref, orphan, depth 분포, 계층 일관성 | 구조적 무결성 지표 (자동 스캔) | 불필요 |
| **Exp 5**: 검색 성능 기여 | SNOMED 매핑 O/X에 따른 Paper 1 답변 품질 차이 | Faithfulness, Completeness 변화 (Paper 1 데이터 재활용) | 불필요 |

#### 공개 자원 계획 (인용 수 극대화)

```
spine-snomed-ontology/
├── mappings/
│   ├── interventions.csv    # 235 codes
│   ├── pathologies.csv      # 231 codes
│   ├── outcomes.csv         # 200 codes
│   └── anatomy.csv          # 69 codes
├── hierarchy/
│   └── is_a_relations.csv   # parent-child 관계
├── normalization/
│   └── aliases.csv          # 280+ 동의어 매핑
└── README.md                # 사용 가이드
```

---

### Paper 3: Evidence Chain + Surgical Intervention Comparison

| 항목 | 내용 |
|------|------|
| **제목(안)** | "Automated Evidence Synthesis for Spine Surgical Interventions: Knowledge Graph Traversal for Treatment Comparison and Outcome Analysis" |
| **타겟 저널** | **1순위**: Spine Journal (IF ~4.0) |
| | **2순위**: Spine (IF ~3.4) |
| | **3순위**: European Spine Journal (IF ~2.6) |
| **논문 유형** | Original Research |

> **이 논문이 가장 임상 저널에 적합하고, 독자 공감도가 높음.**
> 척추외과 전문의가 직접 체감할 수 있는 가치를 전달.

#### Positioning

| 비교 대상 | 차별화 |
|----------|--------|
| **Khalsa 2026** (SSI risk calculator) | GPT-4로 문헌 합성하여 단일 점수 → 우리는 **체계적 evidence chain 구축** |
| **Kartal 2025**, **Najjar 2025** | LLM 직접 질문 → 우리는 **KG에서 근거 추출 후 비교** |
| **기존 Systematic Review** | 수개월 소요, 수동 → 우리는 **자동 evidence chain, 분 단위** |

#### 실험 설계 (v2 — 기존 SR 대비 자동 합성 품질)

> Paper 3의 핵심: "자동 생성된 evidence chain이 기존 systematic review와 일치하는가?"
> 이 질문에 답하려면 **출판된 SR을 정답지(Gold Standard)로 사용**하면 됨.

| 실험 | 내용 | 메트릭 | annotation 필요? |
|------|------|--------|:---:|
| **Exp 1**: SR 대비 검증 | 출판된 systematic review 10편의 결론 vs 시스템 자동 비교 결과 | LLM-as-Judge: Agreement score (결론 일치도 0-1) | 불필요 |
| **Exp 2**: 수술 비교 5쌍 | TLIF vs PLIF, UBE vs MIS-TLIF, CDR vs ACDF, Laminectomy vs Laminoplasty, Short vs Long fixation | 각 비교에서 공통/고유 outcome 수, evidence level 분포 | 불필요 |
| **Exp 3**: 논문 포괄성 | 기존 SR의 reference list와 시스템 인용 논문 비교 | Overlap rate, 추가 발견 논문 수 | 불필요 |
| **Exp 4**: 전문의 평가 | 5명 전문의가 자동 비교 결과를 blind 평가 | 정확성(5점), 유용성(5점), 완전성(5점) | 필요 |
| **Exp 5**: 시간 비교 | 동일 비교를 수동으로 수행하는 시간 vs 시스템 | 소요 시간 (분) | 필요 |

> Exp 1-3은 자동 평가만으로 가능하고, Exp 4-5는 전문의 참여 필요.
> Exp 1이 가장 핵심 — "출판된 SR과 얼마나 일치하는가"가 최강의 validation.

#### Figure/Table 구성

| # | 내용 |
|---|------|
| Fig 1 | Evidence chain 도식: Intervention → TREATS → Pathology → AFFECTS → Outcome |
| Fig 2 | Case study: TLIF vs PLIF 자동 비교 결과 (shared/unique outcomes) |
| Fig 3 | 기존 SR 대비 일치도 + 추가 발견 논문 |
| Table 1 | 5쌍 수술 비교 결과 요약 (outcome별 evidence level, 방향, 효과 크기) |
| Table 2 | 전문의 평가 결과 (Likert 평균, 95% CI) |
| Table 3 | 시간 비교: 전통적 방법 vs 시스템 |

#### 핵심 메시지

> "매주 쏟아지는 척추 수술 논문을 수동으로 비교·합성하는 대신,
> Knowledge Graph 기반 시스템이 수분 내에 체계적 근거 비교를 제공하며,
> 기존 systematic review에서 누락된 근거까지 발견할 수 있다."

---

## 6. Phase 3: Application Papers (Month 8-10)

### Paper 4: Clinical Decision Support Validation

| 항목 | 내용 |
|------|------|
| **제목(안)** | "Knowledge Graph-Based Clinical Decision Support for Spine Surgery: Evidence-Grounded Recommendations versus Direct LLM Consultation" |
| **타겟 저널** | **1순위**: Neurosurgical Focus (IF ~4.1) |
| | **2순위**: World Neurosurgery (IF ~2.1) |
| **논문 유형** | Clinical Validation |
| **IRB** | 필요 (전문의 설문/인터뷰 포함) |

#### Positioning — 핵심 차별화

기존 Cat C 논문들은 모두 "LLM에게 직접 질문" → 우리는 **근거 기반 추천**:

```
기존 (Cat C):     임상 질문 → LLM → 답변 (근거 불명)
우리 (B4):        임상 질문 → KG 검색 → 근거 논문 + LLM 합성 → 답변 (출처 명시)
```

| 기존 논문 | 그 논문의 접근 | 우리의 개선 |
|----------|-------------|------------|
| Kartal 2025 (κ=0.587-0.692) | GPT/Gemini에게 MIS 적응증 질문 | **KG에서 MIS 관련 논문 검색 → 근거 수준별 정리 → 추천** |
| Najjar 2025 (κ=0.764) | ChatGPT에게 CES 수술 결정 질문 | **CES 관련 evidence chain 추출 → 결정 근거 제시** |
| Chan 2025 (ICC=0.990) | LLM으로 SINS 계산 | **계산 + 해당 점수 범위의 치료 근거까지 제공** |

#### 실험 설계 (v2 — CKD GraphRAG 논문 방식 참고)

> 참고: GraphRAG for CKD (medRxiv 2025)는 전문의 평가 + LLM-as-Judge를 조합.
> Paper 4는 Paper 1과 달리 **전문의 평가가 핵심** (임상 저널 타겟).

| 실험 | 내용 | 메트릭 | 방법 |
|------|------|--------|------|
| **Exp 1**: 임상 시나리오 30개 | 환자 정보 → B3(LLM direct) vs B4(GraphRAG) 추천 | Clinical Correctness, Specificity, Guideline Adherence | 전문의 blind 평가 (5점) |
| **Exp 2**: Hallucination 검출 | B3 vs B4의 근거 없는 추천 비율 | Hallucination Rate, Citation Fidelity | 자동 + 전문의 확인 |
| **Exp 3**: Usability study | SUS + 반구조화 인터뷰 | SUS Score, 정성적 피드백 | 전문의 10-15명 |
| **Exp 4**: 시간 효율 | 동일 시나리오에 대한 문헌 검토 시간 | 소요 시간 (분), 인용 논문 수 | 전문의 측정 |
| **참여자** | 분당서울대병원 + 1-2개 협력 기관 전문의/전공의 10-15명 | | |

#### IRB 준비

| 항목 | 내용 |
|------|------|
| 연구 유형 | 비중재 관찰 연구 (설문/인터뷰) |
| 대상자 | 척추외과 전문의/전공의 (환자 아님) |
| 리스크 | 최소 위험 (Minimal risk) |
| 예상 소요 | 신청 후 4-6주 |
| 신청 시점 | Month 6 (Paper 2-3 집필 중에 병렬 진행) |

---

### Paper 5 (보류): EQUATOR Writing Guide

> **상태**: 보류. P1-P4 완료 후 검토. Short Communication으로 빠르게 투고 가능.
> **타겟**: Research Integrity and Peer Review (IF ~3.5)
> **핵심**: 50편 논문의 EQUATOR 체크리스트 준수율 자동 평가 vs 수동 평가 일치도

### Paper 6 (보류): SpineBench Dataset

> **상태**: 보류. P1-P3 결과 데이터를 정리하여 공개 데이터셋으로 투고.
> **타겟**: Scientific Data (Nature, IF ~9.8)
> **핵심**: 질문 + SNOMED 매핑 + baseline 답변 + 평가 결과 공개. 추가 실험 불필요.

---

## 7. 타임라인 (4편 집중)

```
       M1     M2     M3     M4     M5     M6     M7     M8     M9     M10
      ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
Ph 0  │██████│██████│      │      │      │      │      │      │      │      │
      │DB 확보, Evaluation 코드, Baseline 구현                               │
      ├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
P1    │      │██████│██████│██████│ Rev  │      │      │      │      │      │
      │      │초안  │실험  │투고  │리비전│      │      │      │      │      │
      ├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
P3    │      │      │      │██████│██████│██████│ Rev  │      │      │      │
      │      │      │      │SR선정 │실험  │투고  │리비전│      │      │      │
P2    │      │      │      │      │██████│██████│ Rev  │      │      │      │
      │      │      │      │      │정리  │투고  │리비전│      │      │      │
      ├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
IRB   │      │      │      │██████│      │      │      │      │      │      │
      │      │      │      │신청  │승인  │      │      │      │      │      │
      ├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
P4    │      │      │      │      │      │██████│██████│██████│ Rev  │      │
      │      │      │      │      │      │실험  │집필  │투고  │리비전│      │
      └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘

범례: ██ = 활성 작업, Rev = 리비전 대응
```

---

## 8. 저자 구성 전략

| 역할 | P1 (System) | P2 (SNOMED) | P3 (Evidence) | P4 (CDS) |
|------|:-----------:|:-----------:|:-------------:|:---------:|
| 1저자 | **박상민** | **박상민** | 전공의A/박상민 | 전공의A |
| 공저 | 정보의학 동료 | 정보의학 | 박상민 | 다기관 공저 |
| 교신 | **박상민** | **박상민** | **박상민** | **박상민** |

#### 인력 활용 전략

- **전공의 A**: Paper 3 (Evidence Chain) 실험 + Paper 4 (CDS) 실험 주도 → 2편 참여
- **정보의학 동료**: Paper 1-2에 방법론/평가 기여
- **다기관 협력**: Paper 4에 외부 전문의 참여 → 다기관 validation

---

## 9. 예상 산출물 요약

| # | 논문 | 타겟 저널 | IF | 유형 | 핵심 실험 |
|---|------|----------|-----|------|----------|
| **P1** | System Architecture | JMIR | ~7.0 | Original | RAGAS 6메트릭 × 4 baselines × 29 queries |
| **P3** | Evidence Synthesis | Spine Journal | ~4.0 | Original | 기존 SR 10편 대비 자동 합성 검증 + 5쌍 비교 |
| **P4** | Clinical Decision Support | Neurosurg Focus | ~4.1 | Clinical | 30 시나리오 × 15 전문의 blind 평가 |
| **P2** | SNOMED Ontology | IJMI | ~4.7 | Resource | Coverage + Normalization F1 + IS_A 무결성 |

**핵심 4편** | 평균 IF ~5.0 | 교신저자 4편 확보

> P1, P3는 LLM-as-Judge로 자동 평가 중심 → 빠르게 진행 가능
> P4만 전문의 참여 필수 (IRB 필요)

---

## 10. Action Items

### ✅ 완료 (2026-03-18)

- [x] Neo4j DB 743편 확보 (638→743, 7개 주제 105편 정식 파이프라인 임포트)
- [x] `evaluation/` 프레임워크 전체 구축
- [x] `answer_generator.py` — B1~B4 답변 생성 (HyDE + LLM Reranker 적용)
- [x] `llm_judge.py` — LLM-as-Judge 자동 평가
- [x] DG-001~005 × 4 baselines 파일럿 완료 + 3개 LLM Judge 채점
- [x] Phase B 채점표 + CSV 템플릿 생성
- [x] P1 초안 v0.1 (OneDrive)
- [x] Evidence Level 정합성 수정 (study_design 기반 + Chunk 동기화)
- [x] LLM Reranker 구현 (Haiku 기반 질문 적합성 재정렬)
- [x] Query-type detection (comparison/evidence/mechanism/default)

### 다음 단계

- [ ] 29개 질문 전체 × 4 baselines 본실험 실행
- [ ] 3개 LLM Judge (GPT/Gemini/Claude) 전체 채점
- [ ] Phase B 전문의 평가 (10-15개 질문)
- [ ] P1 Results 섹션 작성 (실험 데이터 기반)
- [ ] P1 v0.2 draft 완성 → 투고 준비

### Paper 3 준비

- [ ] 비교 대상 Systematic Review 10편 선정 (각 수술 비교쌍별 2편)
- [ ] SR reference list 추출 → 시스템 결과와 overlap 비교

---

## 11. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| ~~논문 수 500편 미달~~ | ~~통계적 파워 부족~~ | ✅ 624편 확보 완료 |
| LLM-as-Judge 신뢰도 의문 | Reviewer 지적 가능 | 전문의 Phase B로 보완 + inter-judge agreement 보고 |
| JMIR 거절 | P1 지연 | JBI로 즉시 전환 (format 유사) |
| IRB 지연 | P4 일정 밀림 | P1, P2, P3, P6은 IRB 불필요 → 먼저 진행 |
| 기존 SR과 불일치 | P3 결과 약화 | 불일치 원인 분석 자체가 contribution |
| Lotz 2023 / Wu 2025 후속 논문 | 경쟁 심화 | P1 조기 투고 + 척추 수술 특화로 차별화 |
| B4가 B2를 크게 못 이김 | P1 핵심 결과 약화 | Hallucination Rate, Evidence Level에서 차별화 집중 |

---

## 12. 논문별 평가 방법 요약 (v2 — 4편 집중)

| 논문 | 핵심 평가 | 자동 비중 | 전문의 필요 |
|------|----------|:---------:|:----------:|
| **P1 (System)** | RAGAS (Faithfulness, Citation Fidelity, Relevancy) + Evidence Level + Hallucination | **90%** | 10-15문항 검증용 |
| **P3 (Evidence)** | 기존 SR 대비 Agreement (LLM-as-Judge) + 논문 overlap rate | **70%** | 전문의 5명 blind 평가 |
| **P4 (CDS)** | 전문의 blind 평가 (correctness, usefulness) + hallucination rate | **30%** | **핵심** (IRB 필요) |
| **P2 (SNOMED)** | Coverage%, Normalization F1, IS_A 무결성 (전부 자동) | **95%** | LLM Proposer 리뷰만 |

> **전략**: P1, P2는 자동 평가 중심 → 빠르게 진행.
> P3는 자동 70% + 전문의 30%. P4는 전문의 핵심 (IRB 필요, 후반 배치).

---

*최종 업데이트: 2026-03-16 (v2 — RAGAS 기반 End-to-End 평가로 전환)*
