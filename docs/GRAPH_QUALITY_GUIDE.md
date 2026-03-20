# Graph 품질 개선 가이드

> **목적**: Outcome 정규화 + IS_A 계층 확장을 단계별로 진행
> **원칙**: 자동 실행 금지. 반드시 교수님 검수 후 적용
> **데이터 파일 위치**: `data/` 폴더

---

## 현재 문제

| 문제 | 현재 | 목표 | 영향 |
|------|:---:|:---:|------|
| Outcome 정규화 | 3,565개 (과도 분산) | ~400개 | Graph traversal 파편화 해소 |
| IS_A Intervention | 359/842 (43%) | 700+ (83%) | IS_A expansion 정상 작동 |
| IS_A Pathology | 228/520 (44%) | 400+ (77%) | 동일 |
| IS_A Anatomy | 70/230 (30%) | 180+ (78%) | 동일 |

---

## Part A: Outcome 정규화

### 진행 방법

```
Step 1: 목록 추출 (완료)
  → data/outcome_list.json (3,565개)

Step 2: 카테고리별 검수 (교수님)
  → 각 카테고리의 JSON 파일을 열고 병합 대상 결정
  → data/outcome_canonical_map.json에 매핑 작성

Step 3: 병합 실행
  → PYTHONPATH=./src python3 scripts/fix_outcome_normalization.py --step 3
```

### Step 2 상세: 카테고리별 검수

Outcome 3,565개를 한번에 보는 것은 불가능합니다.
**카테고리별로 나눠서** 하나씩 검수합니다.

#### 검수 순서 (영향도 순)

| 순서 | 카테고리 | 현재 노드 수 | 예상 병합 후 | 검수 방법 |
|:---:|----------|:---:|:---:|------|
| **1** | AUC/ML 메트릭 | 353개 | 삭제 or 10개 | AI 논문 전용 — 대부분 삭제 가능 |
| **2** | Fusion 관련 | 198개 | ~10개 | "Fusion Rate" 하나로 대부분 병합 |
| **3** | ROM 관련 | 138개 | ~5개 | ROM, Cervical ROM 정도로 |
| **4** | Pain 관련 | 124개 | ~10개 | Back Pain, Leg Pain, Neck Pain 등 |
| **5** | Complication 관련 | 68개 | ~10개 | Complication Rate + 주요 합병증 |
| **6** | ODI 관련 | 32개 | ~3개 | ODI, mODI 정도 |
| **7** | Hospital Stay | 32개 | ~2개 | Hospital Stay, ICU Stay |
| **8** | VAS 관련 | 20개 | ~5개 | VAS, VAS Back, VAS Leg, VAS Neck, VAS Arm |
| **9** | Blood Loss | 20개 | ~2개 | Blood Loss, Hidden Blood Loss |
| **10** | 나머지 | 2,580개 | ~300개 | 가장 많은 작업 |

#### 검수 프롬프트 (Claude/GPT에 사용)

각 카테고리를 처리할 때 아래 프롬프트를 사용하세요:

```
다음은 척추 수술 Knowledge Graph의 [카테고리] Outcome 목록입니다.
각 항목의 (count)는 연결된 논문 수입니다.

[목록 붙여넣기]

다음 규칙에 따라 canonical name 매핑을 만들어주세요:
1. 같은 측정 도구의 변형은 병합 (예: "VAS Back Pain Score" → "VAS Back")
2. 의미가 다른 하위 개념은 유지 (예: "VAS Back" ≠ "VAS Leg")
3. Study-specific 표현은 canonical로 (예: "SPORT Study - ODI" → "ODI")
4. 논문 1편에만 나오는 고유 표현은 "_REMOVE" 처리
5. AI/ML 메트릭 (AUC, AUROC 등)은 별도 판단 필요

JSON 형식으로 출력:
{
  "원래 이름": "canonical 이름" 또는 "_REMOVE",
  ...
}

canonical 이름이 원래 이름과 같으면 생략해주세요.
```

#### 검수 후 저장

결과를 `data/outcome_canonical_map.json`에 저장:

```json
{
  "VAS Back Pain": "VAS Back",
  "VAS Back Pain Score": "VAS Back",
  "Early Postoperative Back Pain (VAS)": "VAS Back",
  "SPORT Study - Bodily pain improvement": "_REMOVE",
  "AUC - Murata et al.": "_REMOVE",
  ...
}
```

#### 실행

```bash
# 병합 실행 (검수 완료 후에만!)
PYTHONPATH=./src python3 scripts/fix_outcome_normalization.py --step 3
```

---

## Part B: IS_A 계층 확장

### 진행 방법

```
Step 1: orphan 추출 (완료)
  → data/isa_orphans.json (Intervention 483, Pathology 292, Anatomy 160)
  → data/isa_existing_parents.json (현재 parent 목록)

Step 2: parent 매핑 검수 (교수님)
  → data/isa_parent_map.json에 매핑 작성

Step 3: IS_A 생성
  → PYTHONPATH=./src python3 scripts/fix_isa_hierarchy.py --step 3
```

### Step 2 상세: Entity별 검수

#### Intervention orphan (483개) — 우선순위 높음

상위 20개 (논문 수 기준):

| # | Intervention | 논문 수 | 제안 Parent | 교수님 확인 |
|---|-------------|:---:|------|:---:|
| 1 | ESI | 20 | Injection Therapy | ☐ |
| 2 | Pedicle screw instrumentation | 15 | Spinal Instrumentation | ☐ |
| 3 | rhBMP-2 | 14 | Bone Graft Substitute | ☐ |
| 4 | MRI | 12 | Diagnostic Imaging | ☐ |
| 5 | Spine Surgery | 10 | (최상위 — parent 불필요?) | ☐ |
| 6 | Stem Cell Therapy | 8 | Regenerative Therapy | ☐ |
| 7 | Augmented Reality Navigation | 7 | Computer-Assisted Surgery | ☐ |
| 8 | Robotic-Assisted Surgery | 6 | Computer-Assisted Surgery | ☐ |
| 9 | rhBMP-2 augmentation | 6 | Bone Graft Substitute | ☐ |
| 10 | Pedicle Screw Fixation | 6 | Spinal Instrumentation | ☐ |
| 11 | Stereotactic Radiosurgery | 5 | Radiation Therapy | ☐ |
| 12 | X-ray | 4 | Diagnostic Imaging | ☐ |
| 13 | Posterior stabilization | 4 | Spinal Instrumentation | ☐ |
| 14 | BMP | 4 | Bone Graft Substitute | ☐ |
| 15 | Percutaneous Fixation | 4 | Spinal Instrumentation | ☐ |
| 16 | ACDF | 4 | Cervical Fusion | ☐ |
| 17 | Exercise Therapy | 4 | Conservative Treatment | ☐ |
| 18 | Navigation-Assisted Surgery | 3 | Computer-Assisted Surgery | ☐ |
| 19 | Machine Learning Model | 3 | AI/ML Application | ☐ |
| 20 | Navigation-guided spine surgery | 3 | Computer-Assisted Surgery | ☐ |

#### 검수 프롬프트

```
다음은 IS_A 계층이 없는 척추 수술 Intervention 목록입니다.
각 항목에 적절한 상위 카테고리(parent)를 지정해주세요.

[목록 붙여넣기]

기존 parent 목록 (참고):
[data/isa_existing_parents.json 내용 붙여넣기]

규칙:
1. 기존 parent가 있으면 우선 사용
2. 적절한 parent가 없으면 새 parent 제안
3. 너무 일반적인 것(예: "Spine Surgery")은 parent 불필요 → "SKIP"
4. 진단 도구(MRI, X-ray)는 "Diagnostic Imaging" parent

JSON 형식:
{
  "ESI": "Injection Therapy",
  "Spine Surgery": "SKIP",
  ...
}
```

#### 검수 후 저장

`data/isa_parent_map.json`:

```json
{
  "Intervention": {
    "ESI": "Injection Therapy",
    "Pedicle screw instrumentation": "Spinal Instrumentation",
    "rhBMP-2": "Bone Graft Substitute",
    "Spine Surgery": "SKIP"
  },
  "Pathology": { ... },
  "Anatomy": { ... }
}
```

#### 실행

```bash
# IS_A 생성 (검수 완료 후에만!)
PYTHONPATH=./src python3 scripts/fix_isa_hierarchy.py --step 3
```

---

## 진행 체크리스트

### Part A: Outcome 정규화
- [x] Step 1: Outcome 목록 추출 (`data/outcome_list.json`)
- [ ] Step 2-1: AUC/ML 카테고리 검수 (353개)
- [ ] Step 2-2: Fusion 카테고리 검수 (198개)
- [ ] Step 2-3: ROM 카테고리 검수 (138개)
- [ ] Step 2-4: Pain 카테고리 검수 (124개)
- [ ] Step 2-5: Complication 카테고리 검수 (68개)
- [ ] Step 2-6~9: ODI/Hospital Stay/VAS/Blood Loss 검수
- [ ] Step 2-10: 나머지 검수 (2,580개)
- [ ] Step 3: 병합 실행
- [ ] 검증: Outcome 수 확인 (~400개 목표)

### Part B: IS_A 확장
- [x] Step 1: orphan 추출 (`data/isa_orphans.json`)
- [ ] Step 2-1: Intervention orphan 검수 (483개)
- [ ] Step 2-2: Pathology orphan 검수 (292개)
- [ ] Step 2-3: Anatomy orphan 검수 (160개)
- [ ] Step 3: IS_A 생성
- [ ] 검증: IS_A 커버리지 확인 (80%+ 목표)

### Part C: 효과 검증
- [ ] 전체 23문항 B4 재생성 (v11)
- [ ] B2 vs B4 평가
- [ ] Graph traversal 기능 재테스트 (특히 GR 질문)

---

## 주의사항

1. **반드시 검수 후 실행** — 자동 병합은 되돌리기 어려움
2. **Neo4j 백업 권장** — 병합 전 `docker exec neo4j neo4j-admin dump` 실행
3. **카테고리별 순차 진행** — 한번에 전부 하지 말고 하나씩
4. **결과 확인** — 각 Step 3 후 샘플 검증

---

*최종 업데이트: 2026-03-21*
