---
name: dv
description: Data Validation (DV) 스캔을 실행합니다. Neo4j 데이터베이스의 무결성, 완전성, 품질을 검증합니다. "DV 실행", "데이터 검증", "data validation" 등의 요청 시 사용합니다.
disable-model-invocation: true
user-invocable: true
argument-hint: "[phase-number|fix DV-XXX|all]"
---

# Data Validation (DV) 스킬

`docs/DATA_VALIDATION.md` 문서를 기반으로 DV 스캔을 실행합니다.

## 실행 모드

인자에 따라 동작이 달라집니다:

| 인자 | 동작 | 예시 |
|------|------|------|
| (없음) 또는 `all` | 전체 6 Phase 스캔 | `/dv` 또는 `/dv all` |
| `1` ~ `6` | 특정 Phase만 스캔 | `/dv 3` |
| `fix DV-XXX` | 특정 이슈 수복 | `/dv fix DV-NEW-015` |

## 스캔 실행 절차

### Step 1: 전제 조건 확인

```bash
docker-compose ps
```

Neo4j 컨테이너가 실행 중인지 확인합니다. 실행 중이 아니면 사용자에게 `docker-compose up -d`를 안내합니다.

### Step 2: Phase 실행

`docs/DATA_VALIDATION.md`의 해당 Phase 섹션을 읽고, 그 안의 **모든 Cypher 명령어**를 실행합니다.

**Phase 구성:**
- **Phase 1**: 노드 무결성 (1.1~1.4) — 필수 속성, 고아 노드, 중복, 현황
- **Phase 2**: 관계 무결성 (2.1~2.6) — 고립 Paper, IS_A, TREATS, AFFECTS, Taxonomy, INVOLVES
- **Phase 3**: 임베딩 & 검색 품질 (3.1~3.3) — Chunk/Paper 임베딩, 벡터 인덱스
- **Phase 4**: 식별자 & SNOMED (4.1~4.7) — DOI/PMID, SNOMED 커버리지/유효성/중복/동기화, Normalizer, **🤖 SNOMED LLM 제안**
- **Phase 5**: 데이터 품질 (5.1~5.6) — 콘텐츠, 분포, 중복 논문, Chunk, **🤖 Summary 누락**, **🤖 중복/유사 엔티티**
- **Phase 6**: 온톨로지 무결성 (6.1~6.9) — IS_A 완전성/순환/고아, SNOMED 커버리지, TREATS/AFFECTS

**병렬 실행:** 각 Phase 내의 항목들은 독립적이므로 병렬로 실행할 수 있습니다.

**🤖 LLM 항목 처리:**
- 4.7, 5.5, 5.6은 **탐지 쿼리만** 실행합니다 (LLM 호출 없음)
- LLM을 사용한 수복은 사용자가 `/dv fix` 또는 별도 요청 시에만 실행
- 탐지 결과에서 수복 필요 시 스크립트 명령어를 안내합니다

### Step 3: Known Accepted Issues 확인

`docs/DATA_VALIDATION.md`의 "DV Known Accepted Issues" 섹션을 읽고:
- 해당 항목은 ✅(억제)로 표시
- 신규 발견 항목만 보고

### Step 4: 결과 보고

`docs/DATA_VALIDATION.md`의 "DV 결과 보고 템플릿" 형식으로 결과를 출력합니다.

**보고 규칙:**
1. 각 항목의 상태: ✅ PASS / ⚠️ WARNING / ❌ FAIL
2. Known Accepted 항목은 ✅(억제)로 표시하고 사유 표기
3. 신규 발견 이슈는 DV-NEW-XXX 형식으로 등록 제안
4. 🤖 항목은 LLM 수복 가능 여부와 명령어를 안내

### Step 5: Scan History 업데이트

결과를 `docs/DATA_VALIDATION.md`의 "DV Scan History" 테이블에 추가합니다.

## Fix 모드

`/dv fix DV-NEW-XXX` 실행 시:

1. `docs/DATA_VALIDATION.md`의 Open Issues에서 해당 항목 확인
2. 항목 유형에 따라 적절한 수복 방법 실행:

| 이슈 유형 | 수복 방법 |
|-----------|----------|
| 고립 Paper | `scripts/repair_isolated_papers.py` (LLM) |
| HAS_CHUNK 누락 | `scripts/repair_missing_chunks.py` |
| Summary 누락 | `scripts/backfill_summary.py` (LLM) |
| 중복 엔티티 | `scripts/consolidate_entities.py` (LLM) |
| SNOMED 미매핑 | `snomed_proposer.py` (LLM) → 수동 검토 필요 |
| IS_A 계층 | `scripts/build_ontology.py` / `scripts/repair_ontology.py` |
| 엔티티 정규화 | `scripts/normalize_entities.py` |
| SNOMED 백필 | `scripts/enrich_graph_snomed.py` |
| TREATS 백필 | Cypher 직접 실행 (DV 문서 참조) |

3. 수복 후 해당 Phase만 재스캔하여 확인
4. Open Issues 상태 업데이트

## 주의사항

- **SCAN은 보고 전용** — 어떤 파일/데이터도 수정하지 않음
- **Fix는 사용자 요청 시에만** — 절대 자동 수복하지 않음
- **LLM 수복(🤖)은 dry-run 먼저** — 실제 적용 전 반드시 결과 확인
- **Known Accepted 항목은 건너뜀** — 억제 목록에 있으면 ✅로 표시
