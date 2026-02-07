# Release Notes v7.14.12 ~ v7.14.14

**Release Date**: 2025-12-31
**Status**: Production Ready

---

## 주요 변경 사항 요약

### 1. ChromaDB 완전 제거 (v7.14.12)

Neo4j Vector Index가 **유일한** 벡터 저장소입니다.

| 항목 | 이전 | 이후 |
|------|------|------|
| Vector Store | ChromaDB + Neo4j | **Neo4j Only** |
| SearchBackend | CHROMADB, NEO4J | **NEO4J** |
| 의존성 | chromadb 패키지 필요 | 불필요 |

**삭제된 파일**:
- `src/core/vector_db.py` - ChromaDB VectorDBManager
- `src/storage/vector_db.py` - TieredVectorDB (984줄)
- `tests/storage/test_vector_db.py`

**하위 호환성 유지**:
- `TextChunk`, `SearchFilters` 클래스는 `src/storage/__init__.py`에서 유지
- 기존 import 문 변경 불필요: `from storage import TextChunk`

---

### 2. MCP Search 향상 (v7.14.11 ~ v7.14.12)

#### Entity Normalization 적용
```
"endoscopic TLIF" → "BELIF"
"UBE-TLIF" → "BELIF"
"fusion rate" → "Fusion Rate"
```

#### Endoscopic 키워드 확장 검색
"Endoscopic" 검색 시 모든 내시경 수술 variants 자동 포함:

| 키워드 | 포함 수술법 |
|--------|-------------|
| Endoscopic | UBE, BELIF, FESS, PELD, MED, FELD, BE-, Biportal |

**예시**:
```json
{
  "action": "evidence",
  "intervention": "Endoscopic TLIF",
  "outcome": "Fusion Rate"
}
```
→ **8개 결과**: UBE, BELIF, PELD, MED의 Fusion Rate 데이터

#### IS_A Hierarchy 지원
- 상위 intervention 검색 시 하위 intervention 자동 포함
- 예: "Fusion Surgery" → TLIF, PLIF, ALIF, OLIF 등 모든 Fusion 수술 포함

---

### 3. Taxonomy 구조 개선 (v7.14.12 ~ v7.14.13)

| 지표 | 이전 | 이후 |
|------|------|------|
| Orphan Intervention | 164개 | **22개** |
| IS_A 관계 | 기본 | **+152개** |

**신규 카테고리 (7개)**:
- `AI/ML-Based Tools`: ML, Radiomics, SegFormer, YOLO 등
- `Digital Therapeutics`: VR 장치, SaMD, Biofeedback 등
- `Robotic Surgery`: Mazor X 등 로봇 수술
- `Bariatric Surgery`: 비만 수술
- `Minimally Invasive Surgery`: MIS 통합 카테고리
- `Other Surgical Procedures`: 기타 수술
- `Outcome Assessment`: 결과 측정 연구

---

### 4. SNOMED-CT 매핑 확장 (v7.14.13 ~ v7.14.14)

**전체 커버리지: 60.6%** (이전 ~15%)

| 엔티티 | 이전 | 이후 | 증가 |
|--------|------|------|------|
| **Anatomy** | 24.8% | **87.2%** | +62.4%p |
| **Pathology** | 20.2% | **66.1%** | +45.9%p |
| **Outcome** | 4.9% | **60.0%** | +55.1%p |
| **Intervention** | 19.9% | **46.6%** | +26.7%p |

**패턴 매핑 방식**:
```
"VAS back pain" → VAS 패턴 → SNOMED:273903006
"L4-L5 disc herniation" → Herniation 패턴 → SNOMED:76107001
```

---

### 5. Paper Abstract 임베딩 (v7.14.12)

- `neo4j_client.create_paper()`: abstract_embedding 자동 생성
- PDF/PubMed 추가 시 자동 임베딩
- 기존 237개 Paper 일괄 생성 (99.6% 커버리지)

---

## 수정된 주요 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/storage/__init__.py` | TextChunk, SearchFilters 하위 호환성 유지 |
| `src/solver/tiered_search.py` | SearchBackend.CHROMADB 제거 |
| `src/medical_mcp/handlers/search_handler.py` | Entity Normalization, Endoscopic 확장 검색 |
| `src/graph/entity_normalizer.py` | 정규화 로직 |
| `src/graph/neo4j_client.py` | abstract_embedding 자동 생성 |
| `src/graph/spine_snomed_mappings.py` | SNOMED-CT 매핑 (128개) |

---

## 신규 스크립트

| 스크립트 | 용도 |
|----------|------|
| `scripts/fix_database_issues.py` | 데이터베이스 정비 (임베딩, Taxonomy, SNOMED) |
| `scripts/enhance_taxonomy_snomed.py` | Taxonomy/SNOMED 일괄 강화 |

---

## Breaking Changes

1. **ChromaDB 제거**
   - `from core.vector_db import VectorDBManager` → 삭제됨
   - `from storage.vector_db import TieredVectorDB` → 삭제됨
   - `SearchBackend.CHROMADB` → 삭제됨

2. **권장 마이그레이션**
   ```python
   # 이전
   from storage.vector_db import TieredVectorDB

   # 이후 - Neo4j만 사용
   from graph.neo4j_client import Neo4jClient
   ```

---

## 테스트

```bash
# 모듈 import 테스트
PYTHONPATH=./src python3 -c "
from storage import TextChunk, SearchFilters
from solver.tiered_search import SearchBackend
print('SearchBackend:', [b.value for b in SearchBackend])
"

# MCP Search 테스트
# action: evidence, intervention: "Endoscopic TLIF", outcome: "Fusion Rate"
```

---

## 다음 버전 계획

- [ ] SNOMED-CT 커버리지 80% 달성
- [ ] Outcome 계층 구조 추가 (IS_A 관계)
- [ ] 검색 결과 캐싱
