# Spine GraphRAG MCP 사용 가이드

> Claude Desktop/Code에서 척추 의학 논문 검색 및 분석을 위한 MCP 도구 사용법

**Version**: 1.23.2 | **Last Updated**: 2026-02-17

---

## 빠른 시작

### 1. MCP 서버 설정 (stdio 모드)

Claude Desktop 또는 프로젝트의 `.mcp.json`:

```json
{
  "mcpServers": {
    "medical-kag": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "medical_mcp.medical_kag_server"],
      "cwd": "/path/to/rag_research",
      "env": {
        "PYTHONPATH": "/path/to/rag_research/src",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

### 2. SSE / Streamable HTTP 모드 (HTTP 접속, 멀티유저 지원)

여러 클라이언트가 동시에 접속해야 하는 경우 SSE 또는 Streamable HTTP 모드를 사용합니다.

```bash
# SSE 서버 실행
python -m medical_mcp.sse_server --port 8000

# Streamable HTTP 모드 (v1.20.0+)
python -m medical_mcp.medical_kag_server --transport streamable-http --port 8000

# 또는 래퍼 스크립트
python scripts/run_mcp_sse.py --port 8000
```

**SSE Endpoints**:

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/sse` | GET | SSE 연결 (`?user=<id>` 멀티유저) |
| `/messages` | POST | MCP 메시지 처리 |
| `/health` | GET | 연결 통계 포함 상태 확인 |
| `/ping` | GET | 간단한 생존 확인 |
| `/tools` | GET | MCP 도구 목록 |
| `/reset` | POST | 서버 캐시 초기화 (재연결 시) |
| `/restart` | POST | Neo4j 연결 재설정 |

**멀티유저 접속**:

```bash
# URL 파라미터
curl http://localhost:8000/sse?user=kim

# HTTP 헤더
curl -H "X-User-ID: kim" http://localhost:8000/sse
```

### 3. Neo4j 실행 확인

```bash
docker-compose up -d
docker logs spine_graphrag_neo4j  # "Started." 확인
```

### 4. 도구 확인

Claude에게: "사용 가능한 MCP 도구를 알려줘"

---

## 10개 MCP 도구 상세 가이드

### 1. document - 문서 관리

PDF/텍스트 논문을 추가하고 관리합니다.

#### 주요 액션

| Action | 설명 | 예시 |
|--------|------|------|
| `add_pdf` | PDF 논문 추가 (v1.5 파이프라인) | "이 PDF 논문을 추가해줘" |
| `add_json` | JSON 파일로 논문 추가 | "이 JSON 파일로 논문을 추가해줘" |
| `list` | 저장된 논문 목록 조회 | "저장된 논문 목록 보여줘" |
| `delete` | 논문 삭제 | "논문 ID xxx 삭제해줘" |
| `export` | 논문 데이터 내보내기 | "논문 xxx를 JSON으로 내보내줘" |
| `reset` | 데이터베이스 초기화 | "DB 초기화해줘" |
| `prepare_prompt` | EXTRACTION_PROMPT + PDF 텍스트 반환 (v1.17.0: 전체 스키마) | Claude Code 병렬 처리용 |
| `stats` | 문서 통계 조회 (논문 수, 분포 등) | "문서 통계를 보여줘" |
| `summarize` | 논문 요약 생성 (`paper_id`, `style` 파라미터) | "논문 xxx를 요약해줘" |

#### 사용 예시

```
# PDF 논문 추가
"document 도구로 /Users/me/papers/tlif_study.pdf 를 추가해줘"

# 결과
✅ 처리 완료: tlif_study.pdf
- 제목: TLIF for Lumbar Stenosis: A Randomized Trial
- 저자: Smith J, Doe A
- 연도: 2024
- 근거 수준: 1b (RCT)
- 수술법: TLIF, PLIF
- 결과변수: Fusion Rate, VAS, ODI
```

#### Claude Code 병렬 PDF 처리 (v1.17.0)

원격 MCP 서버에서 로컬 PDF에 접근할 수 없을 때, Claude Code가 직접 PDF를 읽고 처리하는 워크플로우:

```
# 1. PDF에서 프롬프트 준비 (MCP 서버 내부와 동일한 EXTRACTION_PROMPT 사용)
"document 도구 prepare_prompt 액션으로 논문.pdf 의 프롬프트를 준비해줘"

# 2. Claude Code에서 PDF 직접 읽기 (Read 도구)
# 3. EXTRACTION_PROMPT 스키마로 JSON 추출
# 4. store_paper로 DB 저장

"analyze 도구 store_paper 액션으로 저장해줘:
- title, year, authors, journal...
- chunks: [{content: '본문텍스트', section_type: 'methods', tier: 'tier1', ...}]
→ MCP 서버가 자동으로 OpenAI 임베딩 생성 + Neo4j 저장"
```

**병렬 처리**: PDF 10개를 Task agent로 동시 처리 → store_paper 개별 호출

#### 문서 통계 및 요약 (v1.20.0)

```
# 문서 통계
"document 도구 stats 액션으로 현재 문서 통계를 보여줘"

# 결과
📊 문서 통계:
- 총 논문 수: 215개
- 연도별 분포: 2020(32), 2021(45), 2022(52), 2023(48), 2024(38)
- 근거 수준별: Level 1(28), Level 2(95), Level 3(72), Level 4(20)

# 논문 요약
"document 도구 summarize 액션으로 논문 pubmed_12345678을 요약해줘"

# style 파라미터 지정
"document 도구 summarize 액션으로 논문 xxx를 brief 스타일로 요약해줘"
```

---

### 2. search - 검색 및 추론

논문과 근거를 다양한 방법으로 검색합니다.

#### 주요 액션

| Action | 설명 | 사용 상황 |
|--------|------|----------|
| `search` | 벡터 검색 (의미 기반) | 일반적인 키워드 검색 |
| `graph` | 그래프 검색 (관계 기반) | 수술법-결과 관계 검색 |
| `adaptive` | 통합 검색 (벡터+그래프) | 종합적인 검색이 필요할 때 |
| `evidence` | 근거 검색 | 특정 수술법의 효과 근거 찾기 |
| `reason` | 추론 기반 답변 | 질문에 대한 종합 답변 |
| `clinical_recommend` | 임상 치료 추천 (`patient_context`, `intervention` 파라미터) | 환자 맥락 기반 치료 추천 |

#### 사용 예시

```
# 벡터 검색
"OLIF 수술 결과에 대해 검색해줘"

# 근거 검색
"search 도구로 OLIF가 VAS를 개선하는 근거를 찾아줘"

# 결과
📊 근거 발견 (3건):
1. Smith 2024 (Level 1b): VAS 6.2→2.3 (p=0.001)
2. Lee 2023 (Level 1b): VAS 3.8점 감소 (p<0.001)
3. Park 2023 (Level 2a): 대조군 대비 2.1점 개선 (p=0.02)

결론: OLIF는 VAS 개선에 효과적 (신뢰도: 0.87)

# 임상 치료 추천 (v1.20.0)
"search 도구 clinical_recommend 액션으로 다음 환자에게 적합한 치료를 추천해줘:
- patient_context: 65세 여성, L4-5 퇴행성 전방전위증, ODI 52
- intervention: OLIF"

# 결과
🏥 임상 치료 추천:
환자: 65세 여성, L4-5 퇴행성 전방전위증
추천 수술: OLIF (근거 수준 2a, 3건 연구)
- 기대 효과: ODI 52→24 (평균 54% 개선)
- 대안: MIS-TLIF (Level 1b 근거 보유)
- 주의사항: 골다공증 여부 확인 필요
```

---

### 3. pubmed - PubMed/DOI 연동

PubMed에서 논문을 검색하고 가져옵니다. DOI로도 논문을 조회할 수 있습니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `search` | PubMed 검색 |
| `bulk_search` | 대량 검색 |
| `hybrid_search` | PubMed + 로컬 DB 통합 검색 |
| `import_citations` | 인용 정보 가져오기 |
| `import_by_pmids` | PMID로 논문 가져오기 |
| `fetch_by_doi` | DOI로 논문 조회 (전문 포함) |
| `doi_metadata` | DOI 메타데이터만 조회 |
| `import_by_doi` | DOI로 논문 임포트 |
| `get_abstract_only` | 초록만 조회 |
| `upgrade_pdf` | PDF에 PubMed 메타데이터 추가 |
| `get_stats` | 통계 조회 |

#### 사용 예시

```
# PubMed 검색
"pubmed에서 'TLIF AND lumbar stenosis AND 2023:2024[Date]' 검색해줘"

# PMID로 가져오기
"PMID 12345678, 23456789 논문을 가져와서 저장해줘"

# DOI로 조회 (v1.14+)
"pubmed 도구로 DOI 10.1016/j.spinee.2024.01.001 논문 조회해줘"

# 결과
📥 가져오기 완료:
1. PMID 12345678: TLIF outcomes in elderly patients (2024)
2. PMID 23456789: Comparison of TLIF vs PLIF (2023)
```

---

### 4. analyze - 텍스트 분석

텍스트나 초록을 분석하거나, 미리 분석된 데이터를 저장합니다.

> **v1.17.0**: PDF 업로드 시 PMC/Unpaywall 전문을 우선 시도 (Open Access 논문 비용 절감). `store_paper`로 chunks 포함 저장 시 임베딩 자동 생성.
>
> **v1.18.0**: `store_paper` 호출 시 **PubMed enrichment 자동 수행** (PMID/DOI/저널/저자 보강). DOI가 있으면 `analyzed_*` → `pubmed_*` paper_id 자동 업그레이드. Outcome 노드 생성 정상화.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `text` | 텍스트/초록 LLM 분석 |
| `store_paper` | 사전 분석된 논문 데이터 저장 |

#### 사용 예시

```
# 텍스트 분석
"analyze 도구로 이 초록을 분석해줘: [초록 내용]"

# 사전 분석 데이터 저장
"analyze 도구의 store_paper 액션으로 다음 논문을 저장해줘:
- 제목: TLIF vs PLIF Study
- 연도: 2024
- 수술법: TLIF, PLIF
- 결과: VAS 2.3 (p=0.001), 융합률 92%"
```

---

### 5. graph - 그래프 탐색

논문 간 관계와 근거 체인을 탐색합니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `relations` | 논문의 관계 조회 |
| `evidence_chain` | 주장에 대한 근거 체인 |
| `compare` | 여러 논문 비교 |
| `clusters` | 관련 논문 클러스터 |
| `multi_hop` | Neo4j 기반 멀티홉 추론 (v1.20.0: 재연결) |
| `draft_citations` | 인용 문구 초안 생성 |
| `build_relations` | 논문 간 SIMILAR_TOPIC 관계 자동 구축 (v1.14.16+) |
| `infer_relations` | 관계 추론 (`rule_name`, `intervention`, `outcome`, `pathology`, `paper_id` 파라미터) |

#### 사용 예시

```
# 근거 체인
"graph 도구로 'OLIF가 TLIF보다 출혈이 적다'는 주장의 근거 체인을 찾아줘"

# 인용 초안
"graph 도구로 'lumbar stenosis treatment' 주제의 Introduction용 인용 초안 만들어줘"

# 결과
📝 인용 초안 (Introduction):
Lumbar stenosis는 노인 인구에서 흔한 퇴행성 질환으로, 다양한 수술적 치료
옵션이 보고되어 왔다 [1,2]. 최근 최소침습 수술법인 OLIF가 주목받고 있으며
[3], 여러 연구에서 기존 수술법 대비 우수한 결과를 보고하였다 [4,5].

# 관계 추론 (v1.20.0)
"graph 도구 infer_relations 액션으로 OLIF와 Fusion Rate 간 관계를 추론해줘"
# 파라미터: rule_name, intervention, outcome, pathology, paper_id

# 멀티홉 추론 (v1.20.0: Neo4j 기반 재연결)
"graph 도구 multi_hop 액션으로 'OLIF → Fusion Rate → 재수술률' 경로를 추론해줘"
```

---

### 6. conflict - 충돌 탐지

상충되는 연구 결과를 찾고 근거를 종합합니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `find` | 주제별 충돌 탐지 |
| `detect` | 수술법-결과별 충돌 탐지 |
| `synthesize` | GRADE 기반 근거 종합 |

#### 사용 예시

```
# 충돌 탐지
"conflict 도구로 OLIF 합병증률에 대한 상충 연구가 있는지 확인해줘"

# 결과
⚠️ 충돌 발견:
- Kim 2024: 합병증률 2.1% (고볼륨 센터)
- Lee 2023: 합병증률 8.5% (저볼륨 센터)
- 원인: 술자 경험 및 센터 볼륨 차이

# 근거 종합
"conflict 도구로 OLIF의 VAS 개선 효과에 대해 근거를 종합해줘"
```

---

### 7. intervention - 수술법 분석

수술법의 계층 구조와 비교 분석을 수행합니다. v1.14.6에서 IS_A 계층이 확장되었습니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `hierarchy` | 수술법 계층 구조 |
| `hierarchy_with_direction` | 방향별 계층 조회 (ancestors/descendants/both) |
| `compare` | 두 수술법 비교 |
| `comparable` | 비교 가능한 수술법 목록 |

#### 계층 구조 (v1.14.6 업데이트)

**Decompression Surgery** (21개 하위 수술법)
```
Decompression Surgery
├─ Open Decompression
│  ├─ Discectomy
│  ├─ Laminectomy
│  ├─ Laminotomy
│  ├─ Foraminotomy
│  └─ Posterior Cervical Foraminotomy
├─ Endoscopic Surgery
│  ├─ PELD, FELD, UBE, PSLD
│  └─ Endoscopic Decompression
├─ Laminoplasty
└─ Microscopic Surgery
   └─ MED, Microdecompression
```

**Fusion Surgery** (22개 하위 수술법)
```
Fusion Surgery
├─ Interbody Fusion
│  ├─ TLIF → MIS-TLIF, BELIF
│  ├─ PLIF, ALIF, LLIF, OLIF
│  └─ CCF (Cervical Cage Fusion)
├─ Posterolateral Fusion
│  ├─ Posterior Instrumented Fusion
│  └─ PLF
├─ Posterior Cervical Fusion
├─ Lumbar Fusion
└─ Spinopelvic Fusion
```

**신규 상위 카테고리**
- Tumor Surgery: Vertebrectomy, Separation Surgery
- Conservative Treatment: Physical therapy, Bracing
- Injection Therapy: PRP Injection
- Radiation Therapy: SBRT, SABR

#### 사용 예시

```
# 계층 구조 (Discectomy가 이제 검색됨!)
"intervention 도구로 Discectomy의 계층 구조를 보여줘"

# 결과
📊 Discectomy 계층 구조:
상위: Open Decompression → Decompression Surgery
동급: Laminectomy, Laminotomy, Foraminotomy

# 비교
"intervention 도구로 TLIF vs PLIF를 융합률 기준으로 비교해줘"

# 결과
📈 TLIF vs PLIF (Fusion Rate):
TLIF: 91.2% (3건 RCT, p=0.003)
PLIF: 88.5% (4건 RCT, p=0.015)
차이: 2.7% (통계적 유의성 없음, p=0.08)
```

---

### 8. extended - 확장 엔티티

환자 코호트, 추적관찰, 비용, 품질 지표를 조회합니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `patient_cohorts` | 환자 코호트 정보 |
| `followup` | 추적관찰 기간 정보 |
| `cost` | 비용 분석 정보 |
| `quality_metrics` | 연구 품질 지표 |

#### 사용 예시

```
# 환자 코호트
"extended 도구로 OLIF 연구들의 환자 코호트 정보를 조회해줘"

# 추적관찰
"extended 도구로 24개월 이상 추적관찰한 연구들을 찾아줘"

# 품질 지표
"extended 도구로 GRADE 평가가 high인 연구들을 조회해줘"
```

---

### 9. reference - 참고문헌 포맷팅

다양한 저널 스타일로 참고문헌을 생성합니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `format` | 단일 논문 참고문헌 포맷팅 |
| `format_multiple` | 여러 논문 일괄 포맷팅 |
| `list_styles` | 사용 가능한 스타일 목록 |
| `set_journal_style` | 저널 스타일 설정 |
| `add_custom_style` | 커스텀 스타일 추가 |
| `preview` | 포맷 미리보기 |

#### 지원 스타일

| 스타일 | 설명 | 저널 예시 |
|--------|------|----------|
| `vancouver` | 숫자 인용 | 대부분의 의학 저널 |
| `ama` | AMA 스타일 | JAMA |
| `apa` | APA 7th | 심리학, 사회과학 |
| `jbjs` | JBJS 스타일 | Journal of Bone & Joint Surgery |
| `spine` | Spine 저널 스타일 | Spine |
| `nlm` | NLM 스타일 | PubMed 기반 |
| `harvard` | 저자-연도 스타일 | 일반 학술지 |

#### 사용 예시

```
# 단일 논문 포맷팅
"reference 도구로 논문 xxx를 Spine 저널 스타일로 포맷해줘"

# 여러 논문 포맷팅
"reference 도구로 OLIF 관련 논문들을 Vancouver 스타일로 번호 매겨서 포맷해줘"

# 결과
📚 참고문헌 (Vancouver):
1. Smith J, Doe A, Lee K. TLIF for lumbar stenosis: A randomized trial.
   Spine. 2024;49(2):123-130.
2. Park S, Kim H. OLIF outcomes in degenerative spondylolisthesis.
   J Neurosurg Spine. 2023;38(4):456-463.

# BibTeX 내보내기
"reference 도구로 논문 xxx를 BibTeX 형식으로 내보내줘"
```

---

### 10. writing_guide - 논문 작성 가이드

학술 논문 작성 지침과 체크리스트를 제공합니다.

#### 주요 액션

| Action | 설명 |
|--------|------|
| `section_guide` | 섹션별 작성 가이드 |
| `checklist` | EQUATOR 체크리스트 |
| `expert` | 전문가 정보 |
| `response_template` | 응답 템플릿 |
| `draft_response` | 리뷰어 응답 초안 |
| `analyze_comments` | 리뷰어 코멘트 분석 |
| `all_guides` | 전체 가이드 통합 조회 |

#### 지원 체크리스트

| 체크리스트 | 연구 유형 |
|-----------|----------|
| `strobe` | 관찰 연구 (코호트, 환자-대조군, 단면) |
| `consort` | 무작위 대조 시험 (RCT) |
| `prisma` | 체계적 문헌고찰, 메타분석 |
| `care` | 증례 보고 |
| `stard` | 진단 정확도 연구 |
| `spirit` | 임상시험 프로토콜 |
| `moose` | 관찰 연구 메타분석 |
| `tripod` | 예측 모델 연구 |
| `cheers` | 경제성 분석 |

#### 사용 예시

```
# 섹션별 가이드
"writing_guide 도구로 Methods 섹션 작성 가이드를 보여줘"

# 체크리스트
"writing_guide 도구로 RCT 논문을 위한 CONSORT 체크리스트를 보여줘"

# 결과
📋 CONSORT 체크리스트 (RCT):
□ Title: 제목에 'randomized'/'randomised' 포함
□ Abstract: 구조화된 초록, 중재/대조군/결과 명시
□ Introduction: 연구 목적 및 가설 명시
□ Methods:
  □ 무작위 배정 방법
  □ 눈가림 (환자/평가자/통계가)
  □ 표본 크기 산정 근거
  □ 1차/2차 결과변수 정의
...

# 리비전 응답 초안
"writing_guide 도구로 이 리뷰어 코멘트에 대한 응답 초안을 작성해줘: [코멘트 내용]"
```

---

## MCP 프로토콜 확장 기능 (v1.20.0)

### Tool Annotations

각 MCP 도구에 동작 힌트가 추가되어 클라이언트가 도구의 특성을 사전에 파악할 수 있습니다.

| Annotation | 설명 | 예시 |
|------------|------|------|
| `readOnly` | 읽기 전용 (데이터 변경 없음) | search, graph.relations |
| `destructive` | 파괴적 작업 (데이터 삭제/변경) | document.delete, document.reset |
| `idempotent` | 멱등성 (반복 호출해도 동일 결과) | document.list, reference.list_styles |
| `openWorld` | 외부 시스템 접근 | pubmed.search, pubmed.fetch_by_doi |

### MCP Resources

`paper://` URI 스킴을 통해 논문 데이터를 MCP 리소스로 직접 접근할 수 있습니다.

| URI 패턴 | 설명 |
|----------|------|
| `paper://list` | 저장된 논문 목록 조회 |
| `paper://{paper_id}` | 특정 논문 메타데이터 조회 |

```
# 리소스 접근 예시
"paper://list 리소스에서 논문 목록을 가져와줘"
"paper://pubmed_12345678 리소스에서 메타데이터를 확인해줘"
```

### MCP Prompts

사전 정의된 프롬프트 템플릿으로 일관된 분석을 수행할 수 있습니다.

| 프롬프트 | 설명 | 파라미터 |
|---------|------|---------|
| `compare_interventions` | 수술법 비교 분석 템플릿 | `intervention_a`, `intervention_b` |
| `evidence_summary` | 근거 요약 보고서 템플릿 | `intervention`, `outcome` (선택) |
| `paper_review` | 논문 리뷰 템플릿 | `paper_id` |

### Streamable HTTP Transport

SSE 모드 외에 Streamable HTTP Transport를 사용할 수 있습니다.

```bash
# Streamable HTTP 모드 실행
python -m medical_mcp.medical_kag_server --transport streamable-http --port 8000

# SSE 모드 (기존)
python -m medical_mcp.sse_server --port 8000
```

Streamable HTTP는 SSE 대비 양방향 스트리밍을 지원하며, 대규모 응답 처리에 유리합니다.

---

## PubMed 임포트 시 Fulltext 조회 순서

PubMed에서 논문을 임포트할 때 자동으로 fulltext를 찾습니다:

```
1순위: PMC Open Access (BioC API)
   └── PMID로 PMC 전문 조회
2순위: DOI/Unpaywall (자동 fallback)
   └── DOI로 Crossref + Unpaywall 조회
   └── OA 상태: gold, green, hybrid, bronze
3순위: Abstract만 저장
   └── 위 방법 모두 실패 시
```

DOI와 메타데이터는 자동으로 Neo4j에 저장됩니다.

---

## 실전 사용 시나리오

### 시나리오 1: 새 논문 추가 및 분석

```
1. "document 도구로 /Users/me/papers/new_study.pdf 추가해줘"
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
| 4 | 전문가 의견 | 매우 낮음 |

### Outcome 타입 분류 (v1.14.6)

검색 시 Outcome 타입으로 필터링할 수 있습니다.

| 타입 | 예시 | 방향 |
|------|------|------|
| `clinical` | VAS, NRS, Pain | lower_is_better |
| `functional` | ODI, NDI, JOA, EQ-5D, SF-36 | lower/higher |
| `radiological` | Fusion Rate, Cobb Angle, SVA | varies |
| `complication` | Dural Tear, Infection, Reoperation | lower_is_better |
| `operative` | Blood Loss, Operation Time, LOS | lower_is_better |
| `model_performance` | AUC, Accuracy, Sensitivity | higher_is_better |

### Pathology 카테고리 분류 (v1.14.6)

| 카테고리 | 예시 |
|---------|------|
| `degenerative` | Lumbar Stenosis, DDD, Myelopathy, Radiculopathy |
| `deformity` | Scoliosis, PJK, DJK, Sagittal Imbalance |
| `tumor` | Spinal Metastasis, Primary Tumor |
| `trauma` | Compression Fracture, Burst Fracture |
| `infection` | Spondylodiscitis, Epidural Abscess |
| `instability` | Atlantoaxial Instability, Pseudarthrosis |
| `metabolic` | Osteoporosis, Ankylosing Spondylitis |

### 충돌 결과 처리

1. 근거 수준 확인 (높은 수준 우선)
2. 표본 크기 비교 (큰 표본 우선)
3. p-value 확인 (낮을수록 강력)
4. 최신성 고려 (최근 연구 참조)
5. 연구 환경 차이 분석 (환자군, 술자 경험 등)

---

## 문제 해결

### MCP 연결 실패

```bash
# Neo4j 실행 확인
docker ps | grep neo4j

# Neo4j 재시작
docker-compose restart neo4j

# 수동 테스트
PYTHONPATH=./src python3 -c "from medical_mcp import medical_kag_server; print('OK')"
```

### 검색 결과 없음

- 데이터베이스에 논문이 있는지 확인: `document list`
- 검색어 구체화
- 다른 검색 타입 시도 (search → adaptive → graph)

### 느린 응답

- `top_k` 값 줄이기 (기본 10 → 5)
- 특정 수술법/결과변수로 범위 좁히기
- Neo4j 인덱스 확인

---

## 현재 그래프 통계 (v1.14.9)

```
📊 노드 수:
   - Paper: 212개 (+5 인용 논문)
   - Intervention: 237개 (79개 IS_A 관계)
   - Pathology: 172개 (44% 분류됨)
   - Outcome: 619개 (41% 분류됨)
   - Chunk: 3,543개
   - Anatomy: 92개

🔗 관계 수:
   - HAS_CHUNK: 3,543개
   - AFFECTS (수술→결과): 3,033개
   - INVESTIGATES (논문→수술): 395개
   - STUDIES (논문→질환): 352개
   - IS_A (수술 계층): 79개
   - CAUSES (수술→합병증): 67개
   - CITES (인용): 5개 (v1.14.9 신규)
```

---

## 관련 문서

- [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) - 노드/관계 스키마
- [TERMINOLOGY_ONTOLOGY.md](TERMINOLOGY_ONTOLOGY.md) - 용어체계/온톨로지 가이드
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 문제 해결 가이드
- [developer_guide.md](developer_guide.md) - 개발자 가이드
- [CHANGELOG.md](CHANGELOG.md) - 버전 히스토리
