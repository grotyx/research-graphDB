# Medical Knowledge Graph (KAG) 논문 관리 프로젝트

> Medical KAG MCP 서버를 활용한 척추 의학 논문 등록, 검색, 분석 시스템

**Version**: 1.25.0 | **Last Updated**: 2026-03-02 | **주요 분야**: 척추 수술, 내시경 수술, 척추 질환

### Key Features (v1.25)

- **Neo4j 통합 저장소**: Graph + Vector (3072d HNSW) 단일 DB (ChromaDB 완전 제거)
- **SNOMED-CT 온톨로지**: 696개 매핑 (I:218, P:214, O:195, A:69), 4개 엔티티 IS_A 계층
- **10개 MCP 도구**: Claude Desktop/Code 연동
- **PubMed + DOI 3단계 Fallback**: PubMed → Crossref/DOI → Basic 순서로 항상 서지 보강
- **store_paper 자동 PubMed enrichment** (v1.18+): 저장 시 PMID/DOI/저널/저자 자동 보강
- **store_paper JSON 저장** (v1.23.3+): 분석 결과를 `data/extracted/` JSON으로 자동 저장 (복구/디버깅용)
- **임상 치료 추천** (v1.20+): 환자 맥락 기반 search clinical_recommend 액션
- **참고문헌 포맷팅**: 7개 스타일 + 커스텀 스타일 지원 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)
- **DOI 전문 조회**: Crossref + Unpaywall API로 전문 자동 조회
- **SSE / Streamable HTTP 서버**: Docker 또는 로컬 실행 MCP 서비스
- **PMC-first PDF 최적화**: Open Access 논문은 PMC/Unpaywall 전문 우선 → Vision API 비용 절감
- **Claude Code 병렬 처리**: PDF 직접 읽기 → EXTRACTION_PROMPT 추출 → store_paper 저장
- **Neo4jClient 3-DAO 아키텍처** (v1.22+): RelationshipDAO, SearchDAO, SchemaManager 분리
- **PubMed 모듈 분해** (v1.23): PubMedDownloader + PubMedProcessor + Facade 3-모듈 구조
- **Revision Surgery Taxonomy** (v1.23.2+): Revision Surgery + 3개 하위시술 IS_A 계층 추가
- **Docker 로그 영속화** (v1.23.3+): `./logs:/app/logs` 바인드 마운트로 컨테이너 재시작 시에도 로그 보존

#### v1.24~1.25 신규 기능

- **SNOMED-CT IS_A 온톨로지** (v1.24.0): 4개 엔티티 타입 전체에 IS_A 계층 구축 — Pathology(188), Outcome(194), Anatomy(67), Intervention(204)
- **다중 홉 그래프 순회** (v1.24.0): evidence chain 추적, intervention 비교, best evidence 검색 (graph_traversal_search.py)
- **3-way 하이브리드 랭킹** (v1.24.0): semantic 0.4 + authority 0.3 + graph_relevance 0.3
- **IS_A 확장 검색** (v1.24.0): 4개 엔티티 쿼리 시 상위/하위 개념 자동 확장 (graph_context_expander.py)
- **LLM 기반 SNOMED 제안** (v1.24.0): 미등록 용어에 대한 SNOMED 매핑 자동 제안 (snomed_proposer.py)
- **SNOMED 매핑 확장** (v1.24.1): 621 → 653개 (+32 신규, alias 280개 추가)
- **대규모 성능 최적화** (v1.25.0): SIMILAR_TOPIC batch write, LIMIT before OPTIONAL MATCH, Fulltext index
- **Chunk→Entity MENTIONS** (v1.25.0): Chunk에서 entity 이름 매칭 → 직접 MENTIONS 관계 생성
- **Intervention→Anatomy APPLIED_TO** (v1.25.0): 수술법↔해부 부위 직접 연결 (Paper 경유 불필요)
- **IS_A expansion 병렬화** (v1.25.0): asyncio.gather() 동시 확장으로 검색 속도 향상
- **테스트 커버리지 확장** (v1.25.0): 2,722 → 3,741 tests (37% 증가, 20개 모듈 1,019 tests 신규)

---

## 논문 등록 워크플로우

### 1단계: 검색 (30개 단위)
```yaml
검색_단위: 30개  # PubMed 검색 시 한 번에 30개 정도 검색
max_results: 50   # 필요시 최대 50개까지 가능
```

### 2단계: 필터링 (품질 기준)
검색 결과에서 저장할 논문 선별:
- **근거 수준**: RCT(1b), 메타분석(1a), 코호트(2a/2b) 우선
- **저널 IF**: 상위 저널 (Spine, JBJS, Neurosurgery 등) 우선
- **Abstract 필수**: abstract 없는 논문은 저장하지 않음

### 3단계: 임포트 (10개 배치)
```yaml
배치_크기: 10개  # 임포트 시 10개 단위로 처리
안정적_처리: 5-8개  # 에러 발생 시 더 작은 배치로
```

### 4단계: 분석 및 저장
```yaml
full_text_우선: PDF가 있으면 full text 기준 분석
abstract_fallback: PDF 없으면 abstract 기준 분석
no_abstract_skip: abstract도 없으면 저장하지 않음
```

---

## 병렬 처리 전략

### 병렬 가능 작업
- 여러 PMID 동시 검색
- 여러 검색 쿼리 동시 실행
- **analyze 도구 병렬 호출** (Claude Code에서 여러 논문 동시 분석 가능)

### 순차 처리 필요
- PDF 등록 → 분석
- 충돌 탐지 → 합성
- 근거 체인 구축

### analyze 도구 vs API
```yaml
analyze_도구:
  장점: Claude Code에서 직접 제어, 결과 즉시 확인
  단점: 순차 처리 (한 번에 하나씩)
  권장: 소량 논문 (<10개) 또는 세밀한 분석 필요 시

API_사용:
  장점: 병렬 처리 가능, 대량 처리에 효율적
  단점: 별도 설정 필요
  권장: 대량 논문 (>10개) 일괄 처리 시
```

---

## 10개 MCP 도구 상세 가이드

### 1. document - 문서 관리

PDF/텍스트 논문을 추가하고 관리합니다.

| Action | 설명 | 사용 예시 |
|--------|------|----------|
| `add_pdf` | PDF 논문 추가 (v7 파이프라인) | "이 PDF 논문을 추가해줘" |
| `add_json` | JSON 파일로 논문 추가 | "이 JSON 파일로 논문을 추가해줘" |
| `list` | 저장된 논문 목록 조회 | "저장된 논문 목록 보여줘" |
| `delete` | 논문 삭제 | "논문 ID xxx 삭제해줘" |
| `export` | 논문 데이터 내보내기 | "논문 xxx를 JSON으로 내보내줘" |
| `stats` | 문서 통계 조회 (논문 수, 분포 등) | "문서 통계를 보여줘" |
| `summarize` | 논문 요약 생성 | "논문 xxx를 요약해줘" |
| `prepare_prompt` | EXTRACTION_PROMPT + PDF 텍스트 반환 | Claude Code 병렬 처리용 |
| `reset` | 데이터베이스 초기화 | "DB 초기화해줘" |

**사용 예시**:
```
"document 도구로 /path/to/tlif_study.pdf 를 추가해줘"

# 결과
✅ 처리 완료: tlif_study.pdf
- 제목: TLIF for Lumbar Stenosis
- 근거 수준: 1b (RCT)
- 수술법: TLIF, PLIF
- 결과변수: Fusion Rate, VAS, ODI
```

---

### 2. search - 검색 및 추론

논문과 근거를 다양한 방법으로 검색합니다.

| Action | 설명 | 사용 상황 |
|--------|------|----------|
| `search` | 벡터 검색 (의미 기반) | 일반적인 키워드 검색 |
| `graph` | 그래프 검색 (관계 기반) | 수술법-결과 관계 검색 |
| `adaptive` | 통합 검색 (벡터+그래프) | 종합적인 검색 |
| `evidence` | 근거 검색 | 특정 수술법의 효과 근거 |
| `reason` | 추론 기반 답변 | 질문에 대한 종합 답변 |
| `clinical_recommend` | 임상 치료 추천 (v1.20+) | 환자 맥락 기반 치료 추천 |

**사용 예시**:
```
# 근거 검색
"search 도구로 OLIF가 VAS를 개선하는 근거를 찾아줘"

# 결과
📊 근거 발견 (3건):
1. Smith 2024 (Level 1b): VAS 6.2→2.3 (p=0.001)
2. Lee 2023 (Level 1b): VAS 3.8점 감소 (p<0.001)
결론: OLIF는 VAS 개선에 효과적 (신뢰도: 0.87)

# 임상 치료 추천 (v1.20+)
"search 도구 clinical_recommend 액션으로 다음 환자에게 적합한 치료를 추천해줘:
- patient_context: 65세 여성, L4-5 퇴행성 전방전위증, ODI 52
- intervention: OLIF"
```

---

### 3. pubmed - PubMed/DOI 연동

PubMed에서 논문을 검색하고 가져옵니다. DOI로도 논문을 조회할 수 있습니다.

| Action | 설명 |
|--------|------|
| `search` | PubMed 검색 |
| `bulk_search` | 대량 검색 |
| `hybrid_search` | PubMed + 로컬 DB 통합 검색 (v1.20+) |
| `import_by_pmids` | PMID로 논문 가져오기 (**가장 효율적**) |
| `import_citations` | 인용 정보 가져오기 |
| `fetch_by_doi` | DOI로 논문 조회 (전문 포함) |
| `doi_metadata` | DOI 메타데이터만 조회 |
| `import_by_doi` | DOI로 논문 임포트 |
| `upgrade_pdf` | PDF에 PubMed 메타데이터 추가 |
| `get_abstract_only` | 초록만 가져오기 |
| `get_stats` | 통계 조회 |

**사용 예시**:
```
# PubMed 검색
"pubmed에서 'TLIF AND lumbar stenosis AND 2023:2024[Date]' 검색해줘"

# PMID로 가져오기 (10개 단위 배치)
"PMID 12345678, 23456789 논문을 가져와서 저장해줘"

# DOI로 조회
"pubmed 도구로 DOI 10.1016/j.spinee.2024.01.001 논문 조회해줘"
```

---

### 4. analyze - 텍스트 분석

텍스트나 초록을 분석하거나, 미리 분석된 데이터를 저장합니다.

> **v1.18+**: `store_paper` 호출 시 **PubMed enrichment 자동 수행** (PMID/DOI/저널/저자 보강). DOI가 있으면 `analyzed_*` → `pubmed_*` paper_id 자동 업그레이드.

| Action | 설명 |
|--------|------|
| `text` | 텍스트/초록 LLM 분석 |
| `store_paper` | 사전 분석된 논문 데이터 저장 (v1.18+: PubMed 자동 보강) |

**사용 예시**:
```
"analyze 도구로 이 초록을 분석해줘: [초록 내용]"
```

---

### 5. graph - 그래프 탐색

논문 간 관계와 근거 체인을 탐색합니다.

| Action | 설명 |
|--------|------|
| `relations` | 논문의 관계 조회 |
| `evidence_chain` | 주장에 대한 근거 체인 (v1.24+: 다중 홉 그래프 순회) |
| `compare` | 여러 논문 비교 |
| `clusters` | 관련 논문 클러스터 |
| `multi_hop` | 멀티홉 추론 (v1.20+: Neo4j 기반) |
| `draft_citations` | **인용 문구 초안 생성** |
| `build_relations` | SIMILAR_TOPIC 관계 자동 구축 (v1.14.16+) |
| `infer_relations` | 관계 추론 (rule_name, intervention, outcome 등) |

**사용 예시**:
```
# 근거 체인
"graph 도구로 'OLIF가 TLIF보다 출혈이 적다'는 주장의 근거 체인을 찾아줘"

# 인용 초안 (논문 작성용)
"graph 도구로 'lumbar stenosis treatment' 주제의 Introduction용 인용 초안 만들어줘"
```

---

### 6. conflict - 충돌 탐지

상충되는 연구 결과를 찾고 근거를 종합합니다.

| Action | 설명 |
|--------|------|
| `find` | 주제별 충돌 탐지 |
| `detect` | 수술법-결과별 충돌 탐지 |
| `synthesize` | **GRADE 기반 근거 종합** |

**사용 예시**:
```
# 충돌 탐지
"conflict 도구로 OLIF 합병증률에 대한 상충 연구가 있는지 확인해줘"

# 근거 종합
"conflict 도구로 OLIF의 VAS 개선 효과에 대해 근거를 종합해줘"
```

---

### 7. intervention - 수술법 분석

수술법의 계층 구조와 비교 분석을 수행합니다.

| Action | 설명 |
|--------|------|
| `hierarchy` | 수술법 계층 구조 |
| `hierarchy_with_direction` | 방향별 계층 조회 (ancestors/descendants/both) |
| `compare` | 두 수술법 비교 |
| `comparable` | 비교 가능한 수술법 목록 |

#### 계층 구조

**Decompression Surgery** (21개 하위 수술법)
```
Decompression Surgery
├─ Open Decompression
│  ├─ Discectomy, Laminectomy, Laminotomy, Foraminotomy
│  └─ Posterior Cervical Foraminotomy
├─ Endoscopic Surgery
│  ├─ PELD, FELD, UBE, PSLD
│  └─ Endoscopic Decompression
├─ Laminoplasty
└─ Microscopic Surgery (MED, Microdecompression)
```

**Fusion Surgery** (22개 하위 수술법)
```
Fusion Surgery
├─ Interbody Fusion
│  ├─ TLIF → MIS-TLIF, BELIF
│  ├─ PLIF, ALIF, LLIF, OLIF
│  └─ CCF (Cervical Cage Fusion)
├─ Posterolateral Fusion (PLF)
├─ Posterior Cervical Fusion
└─ Spinopelvic Fusion
```

**신규 상위 카테고리**
- Tumor Surgery: Vertebrectomy, Separation Surgery
- Conservative Treatment: Physical therapy, Bracing
- Injection Therapy: PRP Injection
- Radiation Therapy: SBRT, SABR

**사용 예시**:
```
# 계층 구조
"intervention 도구로 Discectomy의 계층 구조를 보여줘"

# 비교
"intervention 도구로 TLIF vs PLIF를 융합률 기준으로 비교해줘"

# 결과
📈 TLIF vs PLIF (Fusion Rate):
TLIF: 91.2% (3건 RCT)
PLIF: 88.5% (4건 RCT)
차이: 2.7% (p=0.08)
```

---

### 8. extended - 확장 엔티티

환자 코호트, 추적관찰, 비용, 품질 지표를 조회합니다.

| Action | 설명 |
|--------|------|
| `patient_cohorts` | 환자 코호트 정보 |
| `followup` | 추적관찰 기간 정보 |
| `cost` | 비용 분석 정보 |
| `quality_metrics` | 연구 품질 지표 (GRADE 등) |

---

### 9. reference - 참고문헌 포맷팅

다양한 저널 스타일로 참고문헌을 생성합니다.

| Action | 설명 |
|--------|------|
| `format` | 단일 논문 참고문헌 포맷팅 |
| `format_multiple` | 여러 논문 일괄 포맷팅 |
| `list_styles` | 사용 가능한 스타일 목록 |
| `set_journal_style` | 저널 스타일 설정 |
| `add_custom_style` | 커스텀 스타일 추가 |
| `preview` | 포맷 미리보기 |

| 스타일 | 설명 | 저널 예시 |
|--------|------|----------|
| `vancouver` | ICMJE 표준 (숫자 인용, 기본값) | 대부분의 의학 저널 |
| `ama` | American Medical Association | JAMA |
| `apa` | APA 7th Edition | 심리학, 사회과학 |
| `jbjs` | Journal of Bone & Joint Surgery | J Bone Joint Surg |
| `spine` | Spine Journal 스타일 | Spine |
| `nlm` | National Library of Medicine | PubMed 기반 |
| `harvard` | Harvard 저자-연도 스타일 | 일반 학술지 |

**사용 예시**:
```
# 여러 논문 포맷팅
"reference 도구로 OLIF 관련 논문들을 Vancouver 스타일로 번호 매겨서 포맷해줘"

# 커스텀 스타일 추가
"reference 도구 add_custom_style로 Neurosurgery 저널 스타일을 추가해줘"

# BibTeX 내보내기
"reference 도구로 논문 xxx를 BibTeX 형식으로 내보내줘"
```

---

### 10. writing_guide - 논문 작성 가이드

학술 논문 작성 지침과 체크리스트를 제공합니다.

| 체크리스트 | 연구 유형 | 항목 수 |
|-----------|----------|--------|
| `strobe` | 관찰 연구 (코호트, 환자-대조군, 단면) | 22개 |
| `consort` | 무작위 대조 시험 (RCT) | 25개 |
| `prisma` | 체계적 문헌고찰, 메타분석 | 27개 |
| `care` | 증례 보고 | 13개 |
| `stard` | 진단 정확도 연구 | 30개 |
| `spirit` | 임상시험 프로토콜 | 33개 |
| `moose` | 관찰 연구 메타분석 | 35개 |
| `tripod` | 예측 모델 연구 | 22개 |
| `cheers` | 경제성 평가 연구 | 24개 |

| Action | 설명 |
|--------|------|
| `section_guide` | 섹션별 작성 가이드 |
| `checklist` | 연구 유형별 체크리스트 |
| `expert` | 전문가 정보 (clinician, methodologist, statistician, editor) |
| `response_template` | 리비전 응답 템플릿 |
| `draft_response` | 리뷰어 코멘트 응답 초안 |
| `analyze_comments` | 리뷰어 코멘트 분석 |
| `all_guides` | 전체 가이드 통합 조회 |

**사용 예시**:
```
# 섹션별 가이드
"writing_guide 도구로 Methods 섹션 작성 가이드를 보여줘"

# 체크리스트
"writing_guide 도구로 RCT 논문을 위한 CONSORT 체크리스트를 보여줘"

# 리비전 응답
"writing_guide 도구로 이 리뷰어 코멘트에 대한 응답 초안을 작성해줘"
```

---

## 실전 사용 시나리오

### 시나리오 1: 새 논문 추가 및 분석
```
1. "document 도구로 /path/to/new_study.pdf 추가해줘"
2. "search 도구로 방금 추가한 논문과 관련된 기존 연구들을 찾아줘"
3. "graph 도구로 이 논문의 관계를 보여줘"
```

### 시나리오 2: 문헌 검토 작성
```
1. "search 도구로 'OLIF degenerative spondylolisthesis' 검색해줘"
2. "conflict 도구로 OLIF 효과에 대한 상충 결과가 있는지 확인해줘"
3. "reference 도구로 검색된 논문들을 Vancouver 스타일로 포맷해줘"
4. "graph 도구로 Introduction용 인용 초안을 만들어줘"
```

### 시나리오 3: 수술법 비교 분석
```
1. "intervention 도구로 TLIF vs PLIF를 융합률 기준으로 비교해줘"
2. "search 도구로 두 수술법의 합병증 비교 근거를 찾아줘"
3. "conflict 도구로 synthesize 액션으로 근거를 종합해줘"
```

### 시나리오 4: 논문 작성 지원
```
1. "writing_guide 도구로 cohort 연구용 STROBE 체크리스트 보여줘"
2. "writing_guide 도구로 Results 섹션 작성 가이드 보여줘"
3. "reference 도구로 인용할 논문들을 Spine 저널 스타일로 포맷해줘"
```

### 시나리오 5: 대량 논문 등록 (30개 검색 → 10개 배치)
```
1. "pubmed에서 'UBE spine 2024' 30개 검색해줘"
2. "검색 결과에서 RCT, 메타분석, 상위 저널 논문 위주로 필터링해줘"
3. "abstract 있는 논문만 선별해서 처음 10개 import_by_pmids로 가져와줘"
4. "document list로 등록 확인"
5. "다음 10개 PMID 가져오기" (반복)
6. "full text PDF 있는 논문은 upgrade_pdf로 업그레이드"
```

### 시나리오 6: 온톨로지 기반 심화 검색 (v1.24+)
```
1. "search evidence로 'Endoscopic Surgery'의 Complication Rate 근거를 찾아줘"
   → IS_A 확장: UBE, PELD, FELD, PSLD 등 하위 수술법 자동 포함
2. "graph evidence_chain으로 'Fusion Surgery가 Nonunion에 효과적인가' 확인해줘"
   → 다중 홉 그래프 순회: TLIF, PLIF, ALIF, OLIF 등 하위 시술 전체 탐색
3. "intervention compare로 UBE vs MED 비교해줘"
   → SNOMED 기반 정확한 엔티티 매칭 + IS_A 계층 참조
```

---

## 팁 & 모범 사례

### 효과적인 검색 쿼리

**좋은 예시**:
- "OLIF가 VAS 개선에 효과적인가?" (수술법 + 결과변수)
- "TLIF vs PLIF fusion rate comparison" (명확한 비교)
- "2020년 이후 UBE 합병증 연구" (시간 범위 + 주제)

**피해야 할 예시**:
- "좋은 수술법은?" (너무 모호함)
- "허리 수술" (구체적이지 않음)
- "척추" (너무 광범위함)

### 근거 수준 해석

| Level | 설명 | 신뢰도 |
|-------|------|--------|
| 1a | 메타분석 | 매우 높음 |
| 1b | RCT | 높음 |
| 2a | 코호트 연구 | 중간 |
| 2b | 환자-대조군 연구 | 중간-낮음 |
| 3 | 증례 시리즈 | 낮음 |
| 4 | 증례 보고 | 낮음 |
| 5 | 전문가 의견 | 매우 낮음 |

### 충돌 결과 처리 우선순위
1. **근거 수준** 확인 (높은 수준 우선)
2. **표본 크기** 비교 (큰 표본 우선)
3. **p-value** 확인 (낮을수록 강력)
4. **최신성** 고려 (최근 연구 참조)
5. **연구 환경** 차이 분석 (환자군, 술자 경험 등)

### PubMed 임포트 시 Fulltext 조회 순서

PubMed에서 논문을 임포트할 때 자동으로 fulltext를 찾습니다:
```
1순위: PMC Open Access (BioC API) - PMID로 PMC 전문 조회
2순위: DOI/Unpaywall (자동 fallback) - OA 상태: gold, green, hybrid, bronze
3순위: Abstract만 저장 - 위 방법 모두 실패 시
```

### 서지 보강 3단계 Fallback

인용 논문 및 PDF 처리 시 서지 정보를 단계적으로 보강합니다:
```
Step 1: PubMed 검색 (PMID/제목 기반) → confidence: 1.0
Step 2: Crossref/DOI 검색 (DOI 또는 제목+저자) → confidence: 0.8
Step 3: 기본 정보 생성 (저자+연도만) → confidence: 0.3
→ 어떤 경우든 Paper 노드 + CITES 관계 생성 (인용 논문 유실 방지)
```

### Outcome 타입 분류

| 타입 | 예시 | 방향 |
|------|------|------|
| `clinical` | VAS, NRS, Pain | lower_is_better |
| `functional` | ODI, NDI, JOA, EQ-5D, SF-36 | lower/higher |
| `radiological` | Fusion Rate, Cobb Angle, SVA | varies |
| `complication` | Dural Tear, Infection, Reoperation | lower_is_better |
| `operative` | Blood Loss, Operation Time, LOS | lower_is_better |
| `model_performance` | AUC, Accuracy, Sensitivity | higher_is_better |

### Pathology 카테고리 분류

| 카테고리 | 예시 |
|---------|------|
| `degenerative` | Lumbar Stenosis, DDD, Myelopathy, Radiculopathy |
| `deformity` | Scoliosis, PJK, DJK, Sagittal Imbalance |
| `tumor` | Spinal Metastasis, Primary Tumor |
| `trauma` | Compression Fracture, Burst Fracture |
| `infection` | Spondylodiscitis, Epidural Abscess |
| `instability` | Atlantoaxial Instability, Pseudarthrosis |
| `metabolic` | Osteoporosis, Ankylosing Spondylitis |

---

## 논문 등록 최적 패턴

### 패턴 1: PubMed 검색 후 임포트 (권장)
```
1. pubmed search: 키워드로 검색 → PMID 목록 획득
2. pubmed import_by_pmids: 10개씩 배치 임포트
3. document list: 등록 확인
```

### 패턴 2: PDF 파일 직접 등록
```
1. document add_pdf: PDF 경로로 등록
   - document_type: "journal-article" (선택적)
2. document list: 등록 확인
```

### 패턴 3: 기존 논문 PDF 업그레이드
```
1. document list: 초록만 있는 논문 확인 (chunk_count=0)
2. pubmed upgrade_pdf: PDF 경로와 paper_id 지정
```

### 패턴 4: Full text 직접 제공 시 (analyze 도구 사용)

사용자가 full text 파일(PDF, MD, 링크 등)이나 폴더를 직접 제공하는 경우:

```
1. 파일/폴더 내용 확인
2. analyze 도구로 **하나씩 순차 처리** (병렬 처리 시 에러 발생)
   - action: text
   - text: [full text 내용]
3. 각 논문 처리 완료 후 다음 논문 진행
4. document list: 등록 확인
```

**주의**: analyze 도구는 반드시 **순차 처리**해야 합니다. 여러 논문을 동시에 처리하면 에러가 발생합니다.

### 패턴 5: Claude Code 병렬 PDF 처리

원격 MCP 서버에서 로컬 PDF에 접근할 수 없을 때, Claude Code가 직접 처리:

```
1. document prepare_prompt: EXTRACTION_PROMPT + 사용법 확인 (반드시 먼저 호출!)
2. Claude Code: PDF 직접 Read (Read 도구)
3. EXTRACTION_PROMPT 스키마로 JSON 추출 (Claude Opus가 직접 수행)
4. analyze store_paper: chunks 포함 저장 → MCP 서버가 임베딩 생성 + Neo4j 저장
```

**병렬 처리**: 10개 PDF를 Task agent로 동시 처리 가능
**장점**: 원격 서버 없이도 동일한 추출 품질, Vision API 불필요

#### 청크 생성 필수 규칙 (store_paper 호출 시 반드시 준수)

**목표: 15-25개 청크** (5-8개는 부족! 반드시 15개 이상 생성할 것)

| content_type | 개수 | tier | 크기 | 설명 |
|-------------|------|------|------|------|
| `text` | 8-12개 | tier2 | 200-500자 | abstract, intro, methods, discussion, conclusion 각각 1-3개로 분할 |
| `key_finding` | 5-8개 | tier1 | 200-500자 | Results의 통계 포함 핵심 결과 (is_key_finding=true) |
| `table` | 2-4개 | tier1 | 200-500자 | 표 내러티브 요약 ("Table 1 shows...") |
| `figure` | 2-3개 | tier2 | 200-500자 | 그림 서술적 설명 5-8문장 |

**각 청크 필수 필드:**
```json
{
  "content": "본문 텍스트 200-500자 (필수!)",
  "content_type": "text/table/figure/key_finding",
  "section_type": "abstract/introduction/methods/results/discussion/conclusion",
  "tier": "tier1 또는 tier2",
  "is_key_finding": false,
  "summary": "한줄 요약",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "statistics": {"p_value": "0.001", "is_significant": true}
}
```

**주의사항:**
- Methods 섹션도 2-3개 청크로 분할 (study design, surgical technique, outcome measures)
- Results 섹션의 각 outcome별로 별도 key_finding 청크 생성
- 긴 섹션(>500자)은 반드시 분할할 것

---

## 주의사항

### 저장 규칙
- **Abstract 필수**: abstract 없는 논문은 저장하지 않음
- **Full text 우선**: PDF 있으면 full text 기준, 없으면 abstract 기준 분석
- **품질 필터링**: RCT, 메타분석, 상위 저널 논문 우선 저장

### 배치 처리 규칙
- **검색**: 30개 단위로 검색 (max 50개)
- **임포트**: 10개 단위로 배치 처리 (안정성 위해)
- **에러 시**: 5-8개로 줄여서 재시도

### 문서 유형 (document_type)
```yaml
journal-article: 학술논문
thesis: 학위논문
conference-paper: 학회발표
book: 책
book-section: 챕터
case-report: 증례보고
```

---

## 폴더 구조
```
00. EndNote/
├── Libraries/           # EndNote 라이브러리 (기존 PDF 저장소)
│   ├── [주제별].Data/
│   │   └── PDF/        # 논문 PDF 파일
├── Outputs/             # 출력 파일
└── CLAUDE.md           # 이 파일
```

---

## MCP 연결 끊김 시 재연결

원격 SSE 접속 시 장시간 유휴 또는 네트워크 이슈로 연결이 끊길 수 있습니다.

### 재연결 방법
```bash
# 1. 서버 생존 확인
curl http://YOUR_SERVER_IP:7777/ping

# 2. Claude Code에서 MCP 재연결
claude mcp remove medical-kag-remote
claude mcp add --transport sse medical-kag-remote http://YOUR_SERVER_IP:7777/sse --scope project

# 3. Neo4j 연결만 재설정 (서버 재시작 불필요)
curl -X POST http://YOUR_SERVER_IP:7777/restart

# 4. 서버 전체 재시작 (최후 수단)
# 서버 PC에서: docker-compose restart mcp
```

---

## 빠른 참조 명령어

```bash
# 논문 현황 확인
mcp__medical-kag__document action=list

# 키워드 검색
mcp__medical-kag__search action=search query="biportal endoscopy"

# 수술법 비교
mcp__medical-kag__intervention action=compare intervention1="UBE" intervention2="MED"

# 근거 합성
mcp__medical-kag__conflict action=synthesize intervention="lumbar fusion"

# 인용 생성
mcp__medical-kag__reference action=format_multiple paper_ids=["id1","id2"] style="vancouver"

# 논문 작성 가이드
mcp__medical-kag__writing_guide action=checklist checklist_name="consort"
```
