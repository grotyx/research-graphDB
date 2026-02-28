# Ontology-Based GraphRAG 전면 재설계 계획

> **Version**: 1.24.0 (target)
> **작성일:** 2026-02-28
> **기존 데이터 전략:** 그래프 보강 (기존 데이터 유지, 온톨로지 관계 소급 적용)
> **실행 방식:** 팀 에이전트 모드 (4개 에이전트 협업)

## Context

현재 Spine GraphRAG 시스템은 "GraphRAG"라고 불리지만, 실제로는 **Vector RAG + 간단한 그래프 필터링**에 불과하다.

**핵심 문제:**
1. **저장 불완전:** Intervention만 IS_A 계층이 있고, Pathology/Outcome/Anatomy는 완전 평면 구조
2. **SNOMED 미활용:** 592개 매핑이 저장만 되고 검색에 활용되지 않음 (parent_code → Neo4j IS_A 변환 없음)
3. **검색 미활용:** TREATS/AFFECTS 관계가 있지만 검색 시 그래프 순회를 하지 않음 (이름 문자열 매칭만)
4. **통계 부실:** AFFECTS 관계의 p_value/effect_size가 대부분 NULL
5. **QC 미비:** 온톨로지 무결성 검증 체계 없음

**목표:**
SNOMED-CT 온톨로지 계층을 Neo4j 그래프에 구축하고, 검색 시 다중 홉 그래프 순회를 통해 관계 체인 기반 추론이 가능한 진정한 GraphRAG 시스템으로 전환한다.

---

## Phase 1: 온톨로지 계층 구축 (Graph Construction)

| Sub-task | 파일 | 내용 |
|----------|------|------|
| 1-1 | `taxonomy_manager.py` | 4개 엔티티 IS_A 관리, `build_ontology_from_snomed()` |
| 1-2 | `spine_snomed_mappings.py` | Pathology parent_code 보완 |
| 1-3 | `spine_snomed_mappings.py` | Outcome parent_code 보완 |
| 1-4 | `spine_snomed_mappings.py` | Anatomy parent_code 보완 |
| 1-5 | `schema.py` | P/O/A IS_A 초기화 추가 |
| 1-6 | `scripts/build_ontology.py` | IS_A 일괄 구축 스크립트 (신규) |

## Phase 2: Import 파이프라인 재설계

| Sub-task | 파일 | 내용 |
|----------|------|------|
| 2-1 | `relationship_builder.py` | IS_A 자동 연결, TREATS/AFFECTS 강화 |
| 2-2 | `unified_pdf_processor.py` | 통계값 추출 프롬프트 강화 |
| 2-3 | `entity_normalizer.py` | parent_code 반환, 미등록 용어 감지 |
| 2-4 | `relationship_builder.py` | TREATS/AFFECTS 자동 생성 강화 |

## Phase 3: 검색 파이프라인 재설계

| Sub-task | 파일 | 내용 |
|----------|------|------|
| 3-1 | `graph_context_expander.py` | 4개 엔티티 IS_A 확장 |
| 3-2 | `graph_traversal_search.py` | 다중 홉 그래프 순회 검색 (신규) |
| 3-3 | `search_dao.py` | SNOMED 필터, IS_A 확장 쿼리 |
| 3-4 | `hybrid_ranker.py` | graph_relevance_score 추가 |
| 3-5 | `query_parser.py` | use_snomed=True, snomed_code 전달 |

## Phase 4: QC/Validation 재설계

| Sub-task | 파일 | 내용 |
|----------|------|------|
| 4-1 | `DATA_VALIDATION.md` | Phase 4: Ontology Integrity 추가 |
| 4-2 | `scripts/repair_ontology.py` | 온톨로지 수복 스크립트 (신규) |
| 4-3 | `QC_CHECKLIST.md` | Phase 6: Ontology Consistency 추가 |

## Phase 5: 온톨로지 진화

| Sub-task | 파일 | 내용 |
|----------|------|------|
| 5-1 | `entity_normalizer.py`, `relationship_builder.py` | 미등록 용어 감지 & 보고 |
| 5-2 | `snomed_proposer.py` | LLM 기반 SNOMED 매핑 제안 (신규) |
| 5-3 | Integration | 온톨로지 업데이트 워크플로우 |

---

## 실행 의존성

```
Phase 1 (ontology-builder) ─── 단독 실행
    ↓
Phase 2 (import-redesigner) ←─ Phase 1 완료 필요
Phase 3 (search-redesigner) ←─ Phase 1 완료 필요 (Phase 2와 병렬)
    ↓
Phase 4-5 (qc-designer) ←──── Phase 1, 2, 3 모두 완료 필요
```
