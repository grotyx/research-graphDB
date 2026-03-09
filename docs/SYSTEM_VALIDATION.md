# Spine GraphRAG 시스템 검증 가이드

> 시스템 전체 상태를 빠르게 점검하기 위한 프롬프트 모음

**Version**: 1.24.0 | **Last Updated**: 2026-02-28

---

## 1. 종합 검증 프롬프트 (전체 시스템)

아래 프롬프트를 복사해서 Claude에게 입력하면 전체 시스템을 한 번에 검증합니다:

```
시스템 전체 상태를 점검해줘. 아래 항목을 병렬로 확인:

1. **DB 상태**: pubmed get_stats로 논문 수, PubMed/PDF 비율 확인
2. **벡터 검색**: "lumbar fusion outcomes" 검색 (search/search)
3. **그래프 검색**: "ACDF complications" 검색 (search/graph)
4. **적응형 검색**: "cervical disc replacement vs ACDF" (search/adaptive)
5. **추론**: "What is the best treatment for lumbar stenosis?" (search/reason)
6. **Taxonomy**: TLIF 계층 구조 확인 (intervention/hierarchy)
7. **비교 가능 수술법**: ACDF의 comparable interventions (intervention/comparable)
8. **Paper Relations**: 아무 논문 하나의 relations 확인 (graph/relations)
9. **충돌 탐지**: "lumbar fusion" 주제 충돌 확인 (conflict/find)
10. **참고문헌 스타일**: 사용 가능한 스타일 목록 (reference/list_styles)
11. **작성 가이드**: STROBE 체크리스트 확인 (writing_guide/checklist)

각 항목의 성공/실패 여부와 주요 수치를 표로 정리해줘.
```

---

## 2. 검증 항목별 기대 결과

| 영역 | MCP 도구 | 정상 기준 |
|------|----------|----------|
| **DB 상태** | `pubmed/get_stats` | 논문 수 > 0, 오류 없음 |
| **벡터 검색** | `search/search` | results > 0, score > 0.5 |
| **그래프 검색** | `search/graph` | Cypher 쿼리 실행, results > 0 |
| **적응형 검색** | `search/adaptive` | vector_score + graph_score 포함 |
| **추론** | `search/reason` | confidence > 0.6, evidence_count > 0 |
| **Taxonomy** | `intervention/hierarchy` | parents/children 배열 반환 |
| **Comparable** | `intervention/comparable` | count > 0 |
| **Relations** | `graph/relations` | similar_papers 배열 존재 |
| **충돌 탐지** | `conflict/find` | studies_analyzed > 0 |
| **참고문헌** | `reference/list_styles` | 7개 기본 스타일 |
| **작성 가이드** | `writing_guide/checklist` | items > 0 |

---

## 3. 영역별 개별 검증 프롬프트

### 3.1 데이터베이스 상태

```
pubmed 도구로 get_stats 실행해줘.
전체 논문 수, PubMed/PDF 비율, 최근 추가된 논문 확인.
```

**기대 결과**:
- `total_papers`: 200+
- `pubmed_only`: PubMed에서 가져온 논문
- `pdf_only`: PDF로 추가된 논문

---

### 3.2 검색 파이프라인

```
"lumbar fusion" 키워드로 세 가지 검색을 비교해줘:
1. 벡터 검색 (search/search)
2. 그래프 검색 (search/graph)
3. 적응형 검색 (search/adaptive)

각각의 결과 수, 최고 점수, 검색 방식 차이를 표로 정리.
```

**기대 결과**:
- 벡터 검색: 의미 기반, score 0.6-0.9
- 그래프 검색: Cypher 쿼리 기반, 관계 정보 포함
- 적응형: 두 방식 통합, synthesis 포함

---

### 3.3 Taxonomy 및 계층 구조

```
다음 세 수술법의 계층 구조를 확인해줘:
1. TLIF (intervention/hierarchy)
2. ACDF (intervention/hierarchy)
3. UBE (intervention/hierarchy)

각각의 부모, 자식, 동의어(aliases)를 표로 정리.
```

**기대 결과**:
- TLIF: 부모=Interbody Fusion, 자식=MIS-TLIF, BELIF
- ACDF: 부모=Cervical Fusion
- UBE: 부모=Endoscopic Surgery, aliases=BESS

---

### 3.4 Paper Relations

```
graph 도구로 다음을 순서대로 실행:
1. build_relations (max_papers=50, min_similarity=0.4)
2. 아무 논문의 relations 확인

생성된 관계 수와 유사 논문 목록 확인.
```

**기대 결과**:
- relations_created > 0
- similar_papers 배열에 제목, 유사도 포함

---

### 3.5 추론 및 근거 검색

```
다음 질문에 대해 추론 응답을 생성해줘:
"OLIF와 TLIF 중 요추 유합술에 더 효과적인 것은?"

confidence, evidence_count, reasoning_steps 확인.
```

**기대 결과**:
- confidence > 0.7
- evidence_count > 3
- markdown_response에 참고문헌 포함

---

### 3.6 Evidence Chain

```
graph 도구로 evidence_chain 검색:
claim: "Endoscopic surgery reduces blood loss compared to open surgery"
max_papers: 5

supporting/refuting/neutral 논문 분류 확인.
```

**기대 결과**:
- total_papers > 0
- 각 논문에 intervention, outcome, direction 포함

---

### 3.7 충돌 탐지

```
conflict 도구로 다음 검사 실행:
1. find: topic="lumbar fusion"
2. detect: intervention="TLIF", outcome="fusion rate"

충돌 여부와 severity 확인.
```

**기대 결과**:
- studies_analyzed > 5
- has_conflicts: true/false
- severity: low/medium/high

---

### 3.8 참고문헌 및 작성 가이드

```
다음을 확인해줘:
1. reference/list_styles - 사용 가능한 인용 스타일
2. writing_guide/checklist - STROBE 체크리스트
3. writing_guide/checklist - CONSORT 체크리스트

각 스타일과 체크리스트 항목 수 확인.
```

**기대 결과**:
- 7개 기본 스타일: vancouver, ama, apa, jbjs, spine, nlm, harvard
- STROBE: 22개 항목 (관찰 연구)
- CONSORT: 25개 항목 (RCT)

---

## 4. CLI 테스트 명령어

### 전체 테스트 실행 (권장)

```bash
# deprecated 테스트 제외하고 실행
PYTHONPATH=./src python3 -m pytest tests/ -v --ignore=tests/archive --ignore=tests/integration

# 예상 결과 (v1.14.20 기준)
# 1228+ passed, ~50 failed (외부 API/환경 의존), 4 errors
```

### 핵심 모듈별 테스트

```bash
# 1. 그래프 모듈
PYTHONPATH=./src python3 -m pytest tests/graph/ -v

# 2. 검색/추론 모듈
PYTHONPATH=./src python3 -m pytest tests/solver/ -v

# 3. MCP 서버
PYTHONPATH=./src python3 -m pytest tests/medical_mcp/ -v

# 4. 빌더 모듈
PYTHONPATH=./src python3 -m pytest tests/builder/ -v
```

### 임포트 검증 (빠른 체크)

```bash
PYTHONPATH=./src python3 -c "
from graph.neo4j_client import Neo4jClient
from solver.tiered_search import TieredHybridSearch
from medical_mcp.medical_kag_server import MedicalKAGServer
print('Core modules import OK')
"
```

### 테스트 결과 해석

| 결과 | 의미 | 조치 |
|------|------|------|
| **1200+ passed** | 핵심 기능 정상 | - |
| **~50 failed** | 외부 API/환경 의존 | 무시 가능 |
| **SNOMED 실패** | 외부 API 연결 문제 | 네트워크 확인 |
| **Neo4j Auth 실패** | 비밀번호 불일치 | .env 확인 |
| **LLM fallback 실패** | Mock 설정 문제 | 테스트 환경 이슈 |

---

## 5. 문제 해결 체크리스트

검증 실패 시 확인할 사항:

| 증상 | 원인 | 해결 |
|------|------|------|
| Neo4j 연결 실패 | Docker 미실행 | `docker-compose up -d` |
| 검색 결과 0개 | 데이터 없음 | PDF/PubMed로 논문 추가 |
| 벡터 검색 실패 | 임베딩 없음 | OpenAI API 키 확인 |
| Relations 비어있음 | build_relations 미실행 | `graph/build_relations` 실행 |
| Taxonomy 없음 | 스키마 미초기화 | `python scripts/init_neo4j.py` |
| 추론 신뢰도 낮음 | 고품질 논문 부족 | Level 1-2 논문 추가 |

---

## 6. 빠른 상태 확인 (원라이너)

```
시스템 상태 요약: pubmed/get_stats, intervention/hierarchy(TLIF), graph/relations(아무 논문) 병렬 실행하고 핵심 수치만 알려줘.
```

---

## 관련 문서

- [MCP_USAGE_GUIDE.md](MCP_USAGE_GUIDE.md) - MCP 도구 상세 사용법
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 문제 해결 가이드
- [NEO4J_SETUP.md](NEO4J_SETUP.md) - Neo4j 설정 가이드
