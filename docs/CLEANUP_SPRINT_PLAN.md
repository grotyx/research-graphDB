# Cleanup Sprint 실행 계획서

> **목적**: QC/CA/DV 스캔에서 발견된 모든 Open Issues를 팀에이전트 모드로 병렬 해결
> **실행 방법**: Claude Code에서 `docs/CLEANUP_SPRINT_PLAN.md의 Agent X를 실행해줘` 프롬프트 사용
> **대상 이슈**: QC-001~005, DV-001~002 (총 7개 Open Issues)
> **예상 소요**: 병렬 실행 시 ~1시간

---

## 이슈 → Agent 매핑

| Issue ID | 설명 | Agent |
|----------|------|-------|
| QC-004 | ChromaDB 잔재 참조 44곳 | Agent 1 |
| QC-005 | 죽은 코드 파일 5개 | Agent 1 |
| QC-001 | 6개 문서 버전 불일치 | Agent 2 |
| QC-002 | CLAUDE.md Dependencies 불일치 | Agent 2 |
| QC-003 | DEPLOYMENT.md SNOMED 수치/경로 오류 | Agent 2 |
| DV-001 | secondary entity 정규화 누락 (재발 방지) | Agent 3 |
| DV-002 | snomed_enricher Anatomy MERGE 정규화 누락 | Agent 3 |

추가로, CA에서 발견된 print→logger, TODO 정리도 Agent 4에서 수행.

---

## Agent 1: Dead Code Purge (QC-004, QC-005)

### 개요

| 항목 | 내용 |
|------|------|
| **대상 이슈** | QC-004 (ChromaDB 잔재), QC-005 (죽은 파일) |
| **목표** | 미사용 코드/참조 완전 제거 |
| **영향 범위** | solver/*.py, builder/pubmed_bulk_processor.py, medical_mcp/*.py, orchestrator/ |

### 작업 목록

**1. 죽은 파일 삭제 (5개):**
- `src/medical_mcp/server.py` — 402줄, zero importers, ChromaDB 직접 참조
- `src/solver/raptor.py` — ~800줄, zero importers
- `tests/solver/test_raptor.py` — raptor.py 테스트 (소스 삭제 시 함께 제거)
- `src/orchestrator/chain_builder.py` — zero importers
- `src/orchestrator/response_synthesizer.py` — zero importers

**2. ChromaDB 잔재 정리:**

| 파일 | 작업 | 예상 변경 |
|------|------|----------|
| `src/solver/unified_pipeline.py` | `vector_db` 파라미터 제거 + chroma 주석 정리 + TODO(line 622) 제거 | ~10줄 |
| `src/solver/hybrid_ranker.py` | `vector_db` 파라미터 제거 + chroma docstring 정리 | ~15줄 |
| `src/solver/tiered_search.py` | chroma 주석/docstring 정리 | ~5줄 |
| `src/solver/agentic_rag.py` | `vector_db` 파라미터 제거 | ~4줄 |
| `src/builder/pubmed_bulk_processor.py` | chroma 주석 정리 + print→logger (lines 196,200,462) | ~10줄 |
| `src/medical_mcp/medical_kag_server.py` | chroma 주석/docstring 정리 | ~8줄 |
| `src/medical_mcp/handlers/pubmed_handler.py` | `vector_db=None` 전달 제거 | ~6줄 |
| `src/medical_mcp/handlers/search_handler.py` | chroma 주석 정리 | ~3줄 |

**3. storage/ deprecation:**
- re-export는 유지 (consumer 5개로 많음), deprecation 경고만 정리

### 주의사항
- `relationship_builder.py`는 건드리지 않음 (Agent 3 담당)
- `pubmed_enricher.py`는 건드리지 않음 (Agent 4 담당)
- `vector_db` 파라미터 제거 시 caller도 함께 수정

### 완료 기준
- [ ] 죽은 파일 5개 삭제
- [ ] ChromaDB 참조 0건 (src/ 내)
- [ ] `vector_db` 파라미터 0건
- [ ] 전체 테스트 통과

---

## Agent 2: Doc Sync (QC-001, QC-002, QC-003)

### 개요

| 항목 | 내용 |
|------|------|
| **대상 이슈** | QC-001 (버전 불일치), QC-002 (Dependencies), QC-003 (DEPLOYMENT.md) |
| **목표** | 모든 문서를 v1.21.2 코드 기준으로 동기화 |
| **영향 범위** | docs/ 6개 파일 + CLAUDE.md |

### 작업 목록

**1. 버전 번호 업데이트 (6개 문서):**

| 파일 | 현재 | 변경 |
|------|------|------|
| `docs/DEPLOYMENT.md` | 1.20.1 | → 1.21.2 |
| `docs/NEO4J_SETUP.md` | 1.20.1 | → 1.21.2 |
| `docs/user_guide.md` | 1.20.1 | → 1.21.2 |
| `docs/MCP_USAGE_GUIDE.md` | 1.20.1 | → 1.21.2 |
| `docs/developer_guide.md` | 1.19.4 | → 1.21.2 |
| `docs/SYSTEM_VALIDATION.md` | 1.17.0 | → 1.21.2 |

**2. DEPLOYMENT.md 내용 수정:**
- SNOMED 수치: 414 → 447 (I:144→168, P:120→125, O:104→108)
- entity_normalizer.py 위치: `ontology/` → `graph/`
- tar 파일명 + 검증 스크립트 하드코딩 버전 → 1.21.2

**3. CLAUDE.md Dependencies 동기화 (pyproject.toml 기준):**

| 패키지 | CLAUDE.md (현재) | pyproject.toml (정답) |
|--------|-----------------|---------------------|
| `openai` | `>=1.0.0,<2.0.0` | `>=1.0.0,<3.0.0` |
| `neo4j` | `>=5.15.0,<6.0.0` | `>=5.15.0,<7.0.0` |
| `google-genai` | `>=1.0.0` | `>=1.0.0,<2.0.0` |
| `mcp` | `>=1.0.0,<2.0.0` | `>=1.8.0,<2.0.0` |
| `sentence-transformers` | main deps | optional [ml] |

**4. 기타:**
- `docs/user_guide.md`: "(v1.17)" 레이블 업데이트
- `CLAUDE.md`: `schema.py` → `graph/types/schema.py` 경로 수정

### 주의사항
- 코드 파일(.py)은 건드리지 않음 (문서만)
- pyproject.toml은 이미 올바름 — 수정하지 않음
- src/__init__.py도 이미 1.21.2 — 수정하지 않음

### 완료 기준
- [ ] 모든 문서 버전 = 1.21.2
- [ ] DEPLOYMENT.md SNOMED 수치 정확
- [ ] CLAUDE.md Dependencies = pyproject.toml 일치
- [ ] QC Phase 1 재스캔 시 불일치 0건

---

## Agent 3: Data Prevention (DV-001, DV-002)

### 개요

| 항목 | 내용 |
|------|------|
| **대상 이슈** | DV-001 (secondary entity 정규화), DV-002 (Anatomy MERGE 정규화) |
| **목표** | DB에 비정규화 데이터가 들어가는 코드 경로를 차단하여 재발 방지 |
| **영향 범위** | graph/relationship_builder.py, graph/snomed_enricher.py, tests/ |

### 작업 목록

**1. secondary entity 정규화 추가 (`relationship_builder.py`):**

현재 Pathology/Intervention/Outcome/Anatomy만 `EntityNormalizer`로 정규화됨.
아래 8개 타입에 최소한의 정규화(trim + title case) 적용:

| 타입 | MERGE 위치 | 현재 상태 |
|------|-----------|----------|
| RiskFactor | ~line 2077 | raw name 사용 |
| Complication | ~line 2141 | raw name 사용 |
| RadioParameter | ~line 2205 | raw name 사용 |
| PredictionModel | ~line 2306 | raw name 사용 |
| PatientCohort | MERGE 시 | raw name 사용 |
| FollowUp | MERGE 시 | raw name 사용 |
| Cost | MERGE 시 | raw name 사용 |
| QualityMetric | MERGE 시 | raw name 사용 |

구현:
```python
def _normalize_secondary_entity(self, name: str) -> str:
    """Normalize secondary entity names (trim + title case)."""
    if not name:
        return name
    normalized = name.strip()
    # Title case but preserve acronyms (e.g., "BMI", "VAS")
    if not normalized.isupper():
        normalized = normalized[0].upper() + normalized[1:]
    return normalized
```

**2. snomed_enricher.py Anatomy MERGE 정규화:**
- lines 515-516, 541-542: segment 분리 후 `EntityNormalizer.normalize_anatomy()` 호출 추가

**3. 방어적 테스트 추가 (재발 방지):**
- `tests/graph/test_relationship_builder.py`:
  - "dural tear" vs "Dural Tear" → 같은 정규화 결과
  - RiskFactor " obesity " → "Obesity" (trim + capitalize)
- `tests/graph/test_snomed_enricher.py`:
  - Anatomy segment 정규화 테스트

### 주의사항
- Agent 1의 stubs 정리와 파일이 겹침 → Agent 3은 정규화 로직만 추가 (stubs 건드리지 않음)
- title case 적용 시 의학 약어(BMI, VAS, MRI 등) 보존 주의

### 완료 기준
- [ ] 8개 secondary entity 타입에 정규화 적용
- [ ] snomed_enricher Anatomy MERGE에 정규화 적용
- [ ] 방어적 테스트 추가 및 통과
- [ ] 전체 테스트 통과

---

## Agent 4: Code Quality (CA 관련)

### 개요

| 항목 | 내용 |
|------|------|
| **목표** | 프로덕션 코드의 print→logger 전환, TODO 해결, stubs 정리 |
| **영향 범위** | orchestrator/cypher_generator.py, builder/pubmed_enricher.py, solver/reasoner.py, graph/relationship_builder.py (stubs) |

### 작업 목록

**1. print() → logger 전환 (5곳):**

| 파일 | 라인 | 현재 | 변경 |
|------|------|------|------|
| `orchestrator/cypher_generator.py` | 460 | print(debug) | logger.debug() |
| `orchestrator/cypher_generator.py` | 462 | print(debug) | logger.debug() |
| `orchestrator/cypher_generator.py` | 465 | print(debug) | logger.debug() |
| `builder/pubmed_enricher.py` | 204-205 | print(info) | logger.info() |
| `builder/pubmed_enricher.py` | 843 | print(info) | logger.info() |

> pubmed_bulk_processor.py의 print() 3곳은 Agent 1이 처리 (같은 파일의 chroma 정리와 함께)

**2. TODO 해결 (2곳):**

| 파일 | 라인 | TODO 내용 | 조치 |
|------|------|----------|------|
| `solver/unified_pipeline.py` | 622 | "NLP-based extraction" | Agent 1이 처리 (같은 파일의 chroma 정리와 함께) |
| `solver/reasoner.py` | 613 | "상충 감지 로직" | conflict_detector.py 이미 존재 → 주석 제거 또는 연결 |

**3. relationship_builder.py stubs 정리 (lines 28-100):**
- `CitationInfo`, `CitationType` fallback stubs → 직접 정의로 전환
- `ExtractedMetadata` 등 → builder 모듈에서 import 가능하면 전환, 불가하면 독립 정의 유지

### 주의사항
- Agent 3도 relationship_builder.py를 수정함 → Agent 4는 lines 28-100 (stubs)만 담당, Agent 3은 MERGE 부분만 담당
- logger가 이미 해당 파일에 정의되어 있는지 확인 후 추가

### 완료 기준
- [ ] src/ 내 프로덕션 경로 print() 0건 (scripts/, __main__ 제외)
- [ ] 해결 가능한 TODO 0건
- [ ] fallback stubs → 직접 정의/import 전환
- [ ] 전체 테스트 통과

---

## 실행 순서

```
┌──────────────────────────────────────────────────┐
│ 4개 에이전트 병렬 실행                              │
│                                                  │
│  Agent 1: Dead Code (QC-004,005)  ──┐            │
│  Agent 2: Doc Sync (QC-001~003)   ──┼── 병렬     │
│  Agent 3: Data Prevention (DV-001,002) ─┤        │
│  Agent 4: Code Quality (CA 관련)    ──┘          │
│                                                  │
│  → 전체 테스트 실행                                │
│  → QC/DV Open Issues 상태 업데이트 (✅ 해소)       │
│  → 커밋                                          │
└──────────────────────────────────────────────────┘
```

### 파일 충돌 방지 매핑

| Agent | 담당 파일 (독점) |
|-------|----------------|
| 1 | solver/*.py, builder/pubmed_bulk_processor.py, medical_mcp/*.py, orchestrator/chain_builder.py, orchestrator/response_synthesizer.py |
| 2 | docs/*.md, CLAUDE.md |
| 3 | graph/relationship_builder.py (MERGE 부분), graph/snomed_enricher.py, tests/graph/ |
| 4 | orchestrator/cypher_generator.py, builder/pubmed_enricher.py, solver/reasoner.py, graph/relationship_builder.py (stubs 부분 lines 28-100만) |

> Agent 3과 4가 relationship_builder.py를 공유하지만, 수정 범위가 명확히 분리됨 (Agent 3: MERGE 정규화 ~line 2000+, Agent 4: stubs ~line 28-100)

### 완료 후 검증

```
1. PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q
2. QC Phase 1 재스캔 → 버전/문서 불일치 0건
3. QC Phase 2 재스캔 → ChromaDB 참조 0건, print 0건
4. DV Phase 4.6 재스캔 → Normalizer 커버리지 확인
```
