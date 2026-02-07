# Terminology Update Plan v7.14

> **Date**: 2025-12-25
> **Status**: In Progress
> **Based on**: 151 논문 분석 결과

---

## 1. 개요

논문 데이터 분석 결과, 동일 수술법/질환이 다양한 이름으로 추출되어 정규화가 필요합니다.

**문제**: 278개 "고유" 용어 → 실제 ~50-60개 고유 수술법
**원인**: 별칭 누락, 케이스 불일치, 동의어 미등록

---

## 2. 용어 통합 계획

### 2.1 Interventions (수술법) 별칭 추가

#### UBE 계열 통합
```
정규화 대상: UBE
├── BED (Biportal Endoscopic Discectomy) ← 신규 추가
├── Biportal Endoscopic Discectomy ← 신규 추가
├── BESS (기존)
├── Biportal Endoscopy (기존)
└── ... (기존 별칭)
```

#### BELIF 계열 통합
```
정규화 대상: BELIF
├── BE-TLIF ← 신규 추가 (같은 수술법)
├── Biportal Endoscopic TLIF ← 신규 추가
├── BE-LIF (기존)
├── Biportal endoscopic lumbar interbody fusion (기존)
└── BELF (기존)
```

#### Decompression 계열 통합
```
정규화 대상: Decompression Surgery
├── Decompression (기존)
├── decompression ← 케이스 정규화
├── Neural decompression (기존)
├── Neural Decompression ← 케이스 정규화
├── Spinal decompression ← 신규 추가
└── 감압술 (기존)
```

#### Laminectomy 계열 통합
```
정규화 대상: Laminectomy
├── Decompressive laminectomy ← 신규 추가
├── Open laminectomy (기존)
├── laminectomy ← 케이스 정규화
├── 척추판 절제술 (기존)
└── 후궁 절제술 (기존)
```

### 2.2 신규 수술법 추가

| 수술법 | 카테고리 | SNOMED 코드 | 별칭 |
|-------|---------|------------|------|
| Stereotactic Navigation | Navigation/Robotics | 900000000000122 | Navigation-guided, O-arm navigation, CT navigation |

### 2.3 Outcomes (결과변수) 추가

| Outcome | SNOMED 코드 | 별칭 |
|---------|------------|------|
| Serum CPK | 900000000000311 | CPK, Creatine kinase, CK level |
| Scar Quality | 900000000000312 | Wound cosmesis, Scar appearance |
| Postoperative Drainage | 900000000000313 | Drainage volume |

### 2.4 Complications (합병증) 추가

| Complication | SNOMED 코드 | 별칭 |
|--------------|------------|------|
| Wound Dehiscence | 900000000000503 | Wound breakdown, Dehiscence |
| Recurrent Disc Herniation | 900000000000504 | Recurrent herniated disc, Re-herniation |
| Epidural Hematoma | 900000000000505 | Postoperative epidural hematoma |

---

## 3. 수정 대상 파일

| 파일 | 수정 내용 |
|-----|---------|
| `src/graph/entity_normalizer.py` | INTERVENTION_ALIASES, OUTCOME_ALIASES 추가 |
| `src/ontology/spine_snomed_mappings.py` | SPINE_OUTCOME_SNOMED, SPINE_INTERVENTION_SNOMED 추가 |
| `docs/CHANGELOG.md` | v7.14 변경사항 기록 |
| `docs/GRAPH_SCHEMA.md` | 업데이트된 스키마 반영 |

---

## 4. 변경 이력

- [x] 계획 문서 작성 (2025-12-25)
- [x] entity_normalizer.py 업데이트 (2025-12-25)
  - UBE: BED, Biportal Endoscopic Discectomy 추가
  - BELIF: BE-TLIF, Biportal Endoscopic TLIF 추가
  - Laminectomy: 케이스 변형 및 동의어 추가
  - Decompression Surgery: 케이스 변형 및 동의어 추가
- [x] spine_snomed_mappings.py 업데이트 (2025-12-25)
  - SYNONYM_GROUPS: BED→UBE, BELIF/BE-TLIF, Decompression, Laminectomy 그룹 추가
  - BELIF SNOMED 코드 추가 (900000000000119)
  - Stereotactic Navigation 추가 (900000000000120)
  - Serum CPK, Scar Quality, Postoperative Drainage 추가
  - Wound Dehiscence, Recurrent Disc Herniation, Epidural Hematoma 추가
- [x] CHANGELOG.md 업데이트 (2025-12-25)
- [x] CLAUDE.md 버전 업데이트: 7.13 → 7.14
- [ ] 테스트 실행
