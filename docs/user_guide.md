# Spine GraphRAG v1.24.0 - User Guide

## Overview

Spine GraphRAG is an advanced knowledge augmented generation system for spine surgery research. It uses Neo4j as a unified graph and vector database (HNSW 3072d) with LLM-based reasoning (Claude Haiku 4.5) to provide evidence-based answers to medical questions.

**Version**: 1.24.0
**Last Updated**: 2026-02-17

### Key Features

- **Neo4j 통합 저장소**: Graph + Vector (OpenAI 3072d HNSW) 단일 DB
- **10개 MCP 도구**: Claude Desktop/Code 연동 (Docker SSE 서버)
- **PubMed + DOI 3단계 Fallback**: PubMed → Crossref/DOI → Basic 순서로 항상 서지 보강
- **Crossref 서지 검색**: DOI 없이 제목+저자로 논문 검색
- **인용 논문 항상 저장**: 모든 enrichment 실패 시에도 Paper 노드 생성
- **참고문헌 포맷팅**: 7개 스타일 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)
- **DOI 전문 조회**: Crossref + Unpaywall API로 전문 자동 조회
- **SNOMED-CT 패턴 매핑**: 패턴 기반 자동 매칭 60.6% 커버리지
- **SSE 서버**: Docker 컨테이너 기반 MCP 서비스

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Web UI Walkthrough](#web-ui-walkthrough)
3. [MCP Tools Usage with Claude](#mcp-tools-usage-with-claude)
4. [Reference & Writing Tools](#reference--writing-tools)
5. [Common Queries and Examples](#common-queries-and-examples)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- Docker Desktop (for Neo4j)
- Python 3.10+
- Anthropic API Key (Claude Haiku 4.5)

### Installation

```bash
# 1. Clone repository
cd /Users/sangminpark/Documents/rag_research

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Neo4j + MCP Server
docker-compose up -d

# 4. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY, OPENAI_API_KEY
```

### Verify Installation

```bash
# Initialize Neo4j schema
python scripts/init_neo4j.py

# Check Neo4j connection
docker logs spine_graphrag_neo4j
# Should see "Started."

# Start Web UI
streamlit run web/app.py
```

---

## Web UI Walkthrough

Access the Web UI at `http://localhost:8501`

### 1. Documents Page (📄 Documents)

Upload and process medical papers.

**Features**:
- PDF upload with drag-and-drop
- Automatic metadata extraction (Claude Haiku 4.5)
- Sub-domain classification (Degenerative/Deformity/Trauma/Tumor/Basic Science)
- Entity extraction (Interventions, Outcomes, Pathologies)
- Graph relationship building

**Usage**:

1. Click "Browse files" or drag PDF
2. Wait for processing (30-60 seconds per paper)
3. Review extracted metadata:
   - Title, Authors, Year
   - Study Design, Evidence Level
   - Sub-domain, Interventions, Outcomes
4. Click "Save to Database" to store in Neo4j (Graph + Vector unified)

**Example Output**:
```
✅ Successfully processed: TLIF_vs_PLIF_2024.pdf

📊 Metadata:
- Title: Comparison of TLIF and PLIF for Lumbar Stenosis
- Authors: Smith J, Doe A, Lee K
- Year: 2024
- Evidence Level: 1b (RCT)
- Sub-domain: Degenerative

🔬 Extracted Entities:
- Interventions: TLIF, PLIF
- Outcomes: Fusion Rate, VAS, ODI
- Pathologies: Lumbar Stenosis

📈 Graph Relationships Created:
- 2 INVESTIGATES (Paper → Intervention)
- 1 STUDIES (Paper → Pathology)
- 6 AFFECTS (Intervention → Outcome)
```

### 2. Search Page (🔍 Search)

Query the knowledge base.

**Features**:
- Natural language queries (Korean/English)
- Hybrid search (Graph + Vector)
- Evidence-based answers with citations
- Confidence scoring
- Conflict detection

**Search Types**:

**A. Evidence Search**
```
Query: "OLIF가 VAS 개선에 효과적인가?"

Response:
근거: Level 1b 연구 3건에 따르면 OLIF는 VAS를 유의미하게 개선합니다.

통계:
- Smith et al. (2024): VAS 6.2 → 2.3 (p=0.001)
- Lee et al. (2023): VAS 감소 3.8점 (95% CI: 2.5-5.1, p<0.001)
- Park et al. (2023): Control 대비 2.1점 더 개선 (p=0.02)

결론: OLIF는 VAS 개선에 효과적 (신뢰도: 0.87)
```

**B. Comparison Search**
```
Query: "TLIF vs PLIF 융합률 비교"

Response:
TLIF: 평균 융합률 91.2% (3건의 RCT)
PLIF: 평균 융합률 88.5% (4건의 RCT)

통계적 차이: 2.7% (p=0.08, NS)

결론: 융합률은 통계적으로 유의미한 차이 없음
```

**C. Hierarchy Search**
```
Query: "내시경 수술의 종류"

Response:
Endoscopic Surgery
├── UBE (Unilateral Biportal Endoscopic)
├── FELD (Full-Endoscopic Lumbar Discectomy)
├── PSLD (Percutaneous Stenoscopic Lumbar Decompression)
└── MED (Microendoscopic Discectomy)
```

### 3. Knowledge Graph Page (📊 Knowledge Graph)

Visualize graph relationships.

**Features**:
- Interactive graph visualization
- Filter by node type (Paper, Intervention, Outcome, Pathology)
- Expand/collapse relationships
- Export graph data

**Example Use Cases**:

1. **Explore Intervention Taxonomy**:
   - Select "Intervention" node type
   - Click "TLIF" node
   - See parent (Interbody Fusion) and siblings (PLIF, ALIF)

2. **Find Evidence for Outcome**:
   - Select "Outcome" node type
   - Click "Fusion Rate"
   - See all interventions with AFFECTS relationships
   - Filter by p-value < 0.05

3. **Paper Citation Network**:
   - Select "Paper" node type
   - Click paper node
   - See CITES, SUPPORTS, CONTRADICTS relationships

### 4. Draft Assistant Page (✍️ Draft Assistant)

Generate literature review sections.

**Features**:
- Topic-based evidence gathering
- Automatic citation formatting (APA)
- Conflict highlighting
- Evidence level summary

**Usage**:

1. Enter topic: "OLIF effectiveness for degenerative spondylolisthesis"
2. Select evidence levels: 1a, 1b, 2a
3. Select max papers: 10
4. Click "Generate Draft"

**Example Output**:
```markdown
## OLIF Effectiveness for Degenerative Spondylolisthesis

### Evidence Summary
Based on 5 high-quality studies (Level 1a-1b), OLIF demonstrates...

### Clinical Outcomes
**Pain Improvement (VAS)**:
- Smith et al. (2024) reported VAS reduction from 6.2 to 2.3 (p<0.001)
- Lee et al. (2023) showed similar improvement (3.8 point reduction, p<0.001)

**Fusion Rate**:
- Meta-analysis by Park et al. (2024) showed 92% fusion rate
- Individual RCTs ranged from 88-95%

### Limitations
- Follow-up periods varied (12-24 months)
- No long-term (>5 year) data available

### References
Smith J, Doe A, Lee K. (2024). OLIF for degenerative spondylolisthesis: A randomized controlled trial. Spine, 49(2), 123-130.
...
```

### 5. PubMed Page (🔬 PubMed)

Search and import papers from PubMed.

**Features**:
- PubMed API integration
- Bulk import
- Automatic metadata extraction
- Deduplication

**Usage**:

1. Enter PubMed query: "TLIF[Title] AND 2020:2024[Date]"
2. Click "Search PubMed"
3. Review results (title, authors, PMID)
4. Select papers to import
5. Click "Import Selected"

### 6. Settings Page (⚙️ Settings)

Configure system settings.

**Configuration Options**:

- **LLM Settings**:
  - Model: claude-haiku-4-5-20251001 (default)
  - Temperature: 0.1 (conservative) to 1.0 (creative)
  - Max output tokens: 8192

- **Search Settings**:
  - Top K results: 10
  - Graph weight: 0.6
  - Vector weight: 0.4
  - Min p-value threshold: 0.05

- **Graph Settings**:
  - Neo4j URI: bolt://localhost:7687
  - Auto-initialize schema: Yes/No

---

## MCP Tools Usage with Claude

Spine GraphRAG provides 10 MCP tools for use with Claude Desktop/API.

### Setup

MCP 서버는 Docker 컨테이너로 실행되며, SSE (Server-Sent Events) 방식으로 연결합니다.

1. **Docker로 MCP 서버 시작**:
```bash
cd /Users/sangminpark/Documents/rag_research
docker-compose up -d
```

2. **Configure MCP Server** (in Claude Desktop/Code settings):

```json
{
  "mcpServers": {
    "medical-kag": {
      "type": "sse",
      "url": "http://localhost:7777/sse"
    }
  }
}
```

3. **Restart Claude Desktop/Code**

4. **Verify Tools**: Type in Claude: "What MCP tools are available?"

### Available Tools (10개)

#### 1. document - 문서 관리

PDF/텍스트 논문을 추가하고 관리합니다.

| Action | 설명 |
|--------|------|
| `add_pdf` | PDF 논문 추가 |
| `add_json` | JSON 파일로 논문 추가 |
| `list` | 저장된 논문 목록 조회 |
| `stats` | 문서 통계 조회 |
| `summarize` | 논문 요약 생성 |
| `delete` | 논문 삭제 |
| `export` | 논문 데이터 내보내기 |
| `reset` | 데이터베이스 초기화 |
| `prepare_prompt` | PDF 분석 프롬프트 준비 |

**Usage**:
```
"document 도구로 /path/to/tlif_study.pdf 를 추가해줘"
```

#### 2. search - 검색 및 추론

| Action | 설명 |
|--------|------|
| `search` | 벡터 검색 (의미 기반) |
| `graph` | 그래프 검색 (관계 기반) |
| `adaptive` | 통합 검색 (벡터+그래프) |
| `evidence` | 근거 검색 |
| `reason` | 추론 기반 답변 |
| `clinical_recommend` | 환자 맥락 기반 임상 치료 추천 |

**Usage**:
```
"search 도구로 OLIF가 VAS 개선에 효과적인가 검색해줘"
```

#### 3. pubmed - PubMed/DOI 연동

PubMed에서 논문을 검색하고 가져옵니다. v1.16에서 DOI/Crossref fallback이 추가되었습니다.

| Action | 설명 |
|--------|------|
| `search` | PubMed 검색 |
| `bulk_search` | 대량 검색 |
| `hybrid_search` | PubMed + 로컬 통합 검색 |
| `import_by_pmids` | PMID로 논문 가져오기 (가장 효율적) |
| `import_citations` | 인용 정보 가져오기 |
| `fetch_by_doi` | DOI로 논문 조회 (전문 포함) |
| `doi_metadata` | DOI 메타데이터만 조회 |
| `import_by_doi` | DOI로 논문 임포트 |
| `upgrade_pdf` | PDF에 PubMed 메타데이터 추가 |
| `get_abstract_only` | 초록만 가져오기 |
| `get_stats` | 통계 조회 |

**Usage**:
```
"pubmed에서 'TLIF AND lumbar stenosis AND 2023:2024[Date]' 검색해줘"
"PMID 12345678, 23456789 논문을 가져와서 저장해줘"
"pubmed 도구로 DOI 10.1016/j.spinee.2024.01.001 논문 조회해줘"
```

#### 4. analyze - 텍스트 분석

| Action | 설명 |
|--------|------|
| `text` | 텍스트/초록 LLM 분석 |
| `store_paper` | 사전 분석된 논문 데이터 저장 |

**Usage**:
```
"analyze 도구로 이 초록을 분석해줘: [초록 내용]"
```

#### 5. graph - 그래프 탐색

| Action | 설명 |
|--------|------|
| `relations` | 논문의 관계 조회 |
| `evidence_chain` | 주장에 대한 근거 체인 |
| `compare` | 여러 논문 비교 |
| `clusters` | 관련 논문 클러스터 |
| `multi_hop` | 멀티홉 추론 |
| `draft_citations` | 인용 문구 초안 생성 |
| `build_relations` | 논문 간 SIMILAR_TOPIC 관계 자동 구축 |
| `infer_relations` | 관계 추론 (규칙 기반 논문 간 관계 추론) |

**Usage**:
```
"graph 도구로 'OLIF가 TLIF보다 출혈이 적다'는 주장의 근거 체인을 찾아줘"
"graph 도구로 'lumbar stenosis treatment' 주제의 Introduction용 인용 초안 만들어줘"
```

#### 6. conflict - 충돌 탐지

| Action | 설명 |
|--------|------|
| `find` | 주제별 충돌 탐지 |
| `detect` | 수술법-결과별 충돌 탐지 |
| `synthesize` | GRADE 기반 근거 종합 |

**Usage**:
```
"conflict 도구로 OLIF 합병증률에 대한 상충 연구가 있는지 확인해줘"
"conflict 도구로 OLIF의 VAS 개선 효과에 대해 근거를 종합해줘"
```

#### 7. intervention - 수술법 분석

| Action | 설명 |
|--------|------|
| `hierarchy` | 수술법 계층 구조 |
| `hierarchy_with_direction` | 방향별 계층 조회 (ancestors/descendants/both) |
| `compare` | 두 수술법 비교 |
| `comparable` | 비교 가능한 수술법 목록 |

**Usage**:
```
"intervention 도구로 TLIF vs PLIF를 융합률 기준으로 비교해줘"
"intervention 도구로 Discectomy의 계층 구조를 보여줘"
```

#### 8. extended - 확장 엔티티

| Action | 설명 |
|--------|------|
| `patient_cohorts` | 환자 코호트 정보 |
| `followup` | 추적관찰 기간 정보 |
| `cost` | 비용 분석 정보 |
| `quality_metrics` | 연구 품질 지표 (GRADE 등) |

#### 9. reference - 참고문헌 포맷팅

7개 저널 스타일로 참고문헌을 자동 포맷팅합니다.

**Usage**:
```
"reference 도구로 OLIF 관련 논문들을 Vancouver 스타일로 번호 매겨서 포맷해줘"
"reference 도구로 논문 xxx를 BibTeX 형식으로 내보내줘"
```

#### 10. writing_guide - 논문 작성 가이드

9개 EQUATOR 체크리스트와 섹션별 작성 가이드를 제공합니다.

| Action | 설명 |
|--------|------|
| `section_guide` | 섹션별 작성 가이드 |
| `checklist` | 연구 유형별 체크리스트 |
| `expert` | 전문가 정보 |
| `response_template` | 리비전 응답 템플릿 |
| `draft_response` | 리뷰어 코멘트 응답 초안 |
| `analyze_comments` | 리뷰어 코멘트 분석 |
| `all_guides` | 전체 가이드 통합 조회 |

**Usage**:
```
"writing_guide 도구로 RCT 논문을 위한 CONSORT 체크리스트를 보여줘"
"writing_guide 도구로 Methods 섹션 작성 가이드를 보여줘"
```

---

## Reference & Writing Tools

### 참고문헌 포맷팅 (v1.14.20+, v1.16 강화)

7개 저널 스타일로 참고문헌을 자동 포맷팅합니다.

**지원 스타일**:

| 스타일 | 설명 | 예시 |
|--------|------|------|
| `vancouver` | ICMJE 표준 (기본) | 1. Smith J, Doe A. Title. Spine. 2024;49(2):123-130. |
| `ama` | American Medical Association | Smith J, Doe A. Title. Spine. 2024;49(2):123-130. |
| `apa` | APA 7th Edition | Smith, J., & Doe, A. (2024). Title. Spine, 49(2), 123-130. |
| `jbjs` | Journal of Bone & Joint Surgery | Smith J, Doe A. Title. J Bone Joint Surg Am. 2024;106:123-30. |
| `spine` | Spine Journal | Smith J, Doe A. Title. Spine 2024;49:123-130. |
| `nlm` | National Library of Medicine | Smith J, Doe A. Title. Spine. 2024;49(2):123-130. |
| `harvard` | Harvard Style | Smith, J. and Doe, A. (2024) 'Title', Spine, 49(2), pp. 123-130. |

**MCP 사용법**:
```
Claude, reference 도구로 list_styles 실행해줘
Claude, "TLIF" 검색해서 Vancouver 스타일로 참고문헌 만들어줘
Claude, paper_id로 format 실행하고 JBJS 스타일로 변환해줘
```

**BibTeX/RIS 내보내기**:
```
Claude, reference 도구로 format_multiple 실행하고 output_format을 bibtex로 해줘
```

### 학술 논문 작성 가이드 (v1.14.20+, v1.16 유지)

9개 EQUATOR 체크리스트와 섹션별 작성 가이드를 제공합니다.

**지원 체크리스트**:

| 체크리스트 | 연구 유형 | 항목 수 |
|-----------|----------|--------|
| `strobe` | 관찰 연구 (Cohort, Case-control) | 22개 |
| `consort` | 무작위 대조 시험 (RCT) | 25개 |
| `prisma` | 체계적 문헌고찰/메타분석 | 27개 |
| `care` | 증례 보고 | 13개 |
| `stard` | 진단 정확도 연구 | 30개 |
| `spirit` | 임상시험 프로토콜 | 33개 |
| `moose` | 관찰 연구 메타분석 | 35개 |
| `tripod` | 예측 모델 연구 | 22개 |
| `cheers` | 경제성 평가 연구 | 24개 |

**MCP 사용법**:
```
Claude, writing_guide로 STROBE 체크리스트 보여줘
Claude, cohort 연구의 Methods 섹션 작성 가이드 알려줘
Claude, 리뷰어 코멘트에 대한 응답 템플릿 만들어줘
```

**섹션별 가이드**:
```
Claude, writing_guide로 section_guide 실행해서 discussion 섹션 작성법 알려줘
```

### PubMed 연동 (v1.14.23+, v1.16 DOI Fallback 추가)

**자동 보완 검색** (hybrid_search):
로컬 DB 결과가 부족할 때 PubMed를 자동으로 검색하고 임포트합니다.

```
Claude, pubmed 도구로 hybrid_search 실행해서 "OLIF outcomes" 검색해줘
```

**DOI 전문 조회**:
```
Claude, pubmed 도구로 fetch_by_doi 실행해서 10.1016/j.spinee.2024.01.001 조회해줘
```

**대량 PMID 임포트**:
```
Claude, pubmed 도구로 import_by_pmids 실행해서 ["12345678", "23456789"] 임포트해줘
```

**v1.16 서지 보강 3단계 Fallback**:

논문 임포트 및 인용 처리 시 자동으로 3단계 fallback이 적용됩니다:

| 단계 | 방법 | 신뢰도 | 설명 |
|------|------|--------|------|
| 1 | PubMed 검색 | 1.0 | PMID/제목 기반 (MeSH, publication type 포함) |
| 2 | Crossref/DOI | 0.8 | DOI 또는 제목+저자로 Crossref API 검색 |
| 3 | Basic 생성 | 0.3 | 저자+연도만으로 최소 Paper 노드 생성 |

모든 단계 실패 시에도 Paper 노드와 CITES 관계가 생성되어 인용 논문이 유실되지 않습니다.

---

## Common Queries and Examples

### Clinical Questions

**Q: What are the complications of OLIF?**
```
Search: "OLIF complications"

Expected Results:
- Complication Rate: 2-5% (Level 1a meta-analysis)
- Common complications: Vascular injury (1.2%), psoas weakness (3.1%)
- Comparison: Lower than TLIF (5-8% complication rate)
```

**Q: Is UBE suitable for elderly patients?**
```
Search: "UBE elderly patients age >65"

Expected Results:
- 3 studies focused on elderly (65-82 years)
- Similar outcomes to younger patients
- Lower complication rate (p=0.03)
- Faster recovery (p=0.01)
```

### Research Questions

**Q: What's the evidence level for OLIF effectiveness?**
```
Graph Search: "OLIF evidence level"

Expected Results:
- 2 Level 1a studies (meta-analyses)
- 8 Level 1b studies (RCTs)
- 15 Level 2a studies (cohort studies)

Conclusion: Strong evidence base
```

**Q: Are there conflicting results about PSO complication rate?**
```
Conflict Detection: "PSO complication rate conflicts"

Expected Results:
- Conflict detected: 15-30% range
- High-volume centers (Kim 2024): 15% (p<0.001)
- Low-volume centers (Lee 2023): 28% (p<0.001)

Reason: Surgeon experience and center volume
```

### Taxonomy Questions

**Q: What are all types of endoscopic spine surgery?**
```
Hierarchy Search: "Endoscopic Surgery children"

Expected Results:
Endoscopic Surgery
├── UBE (Unilateral Biportal Endoscopic)
├── FELD (Full-Endoscopic Lumbar Discectomy)
├── PSLD (Percutaneous Stenoscopic Lumbar Decompression)
└── MED (Microendoscopic Discectomy)
```

---

## Best Practices

### 1. Writing Effective Queries

**✅ Good Queries**:
- "OLIF가 VAS 개선에 효과적인가?" (specific intervention + outcome)
- "TLIF vs PLIF fusion rate comparison" (clear comparison)
- "내시경 수술의 종류" (hierarchy exploration)

**❌ Poor Queries**:
- "좋은 수술법은?" (too vague)
- "허리 수술" (no specific intervention)
- "척추" (too broad)

### 2. Interpreting Evidence Levels

- **Level 1a-1b**: Strong evidence, base clinical decisions
- **Level 2a-2b**: Moderate evidence, supportive role
- **Level 3-4**: Weak evidence, hypothesis generation

### 3. Handling Conflicts

When conflicting results appear:
1. Check evidence levels (prioritize higher levels)
2. Compare sample sizes (larger is better)
3. Check p-values (lower is stronger)
4. Consider study recency (newer may be more relevant)
5. Look for systematic differences (patient population, technique variation)

### 4. Citation Best Practices

- Always cite evidence level
- Include statistical significance
- Note conflicting results
- Provide context (patient population, follow-up duration)

---

## Troubleshooting

### Common Issues

#### 1. Neo4j Connection Error

**Symptom**: "ServiceUnavailable: Neo4j service not available"

**Solution**:
```bash
# Check Neo4j status
docker ps | grep neo4j

# Restart Neo4j
docker-compose restart neo4j

# Check logs
docker logs spine_graphrag_neo4j
```

#### 2. PDF Processing Fails

**Symptom**: "Failed to extract metadata from PDF"

**Possible Causes**:
- PDF is scanned image (no text layer)
- PDF is corrupted
- Claude API quota exceeded

**Solution**:
```bash
# Check if PDF has text
pdftotext test.pdf output.txt
cat output.txt  # Should show text

# Check Claude API key
echo $ANTHROPIC_API_KEY | head -c 20

# Use OCR for scanned PDFs
# (currently not supported - add to backlog)
```

#### 3. No Graph Results

**Symptom**: Search returns only vector results, no graph evidence

**Possible Causes**:
- No AFFECTS relationships in database
- Intervention/Outcome not normalized correctly
- Graph search query syntax error

**Solution**:
```bash
# Check graph data
python -c "
from src.graph.neo4j_client import Neo4jClient
import asyncio

async def check():
    async with Neo4jClient() as client:
        stats = await client.get_stats()
        print(stats)

asyncio.run(check())
"

# Expected output:
# {'nodes': {'Paper': 50, 'Intervention': 25, 'Outcome': 15},
#  'relationships': {'AFFECTS': 120, 'INVESTIGATES': 80}}

# If AFFECTS count is 0:
# - Reprocess papers with relationship building
```

#### 4. Low Confidence Scores

**Symptom**: All answers have confidence < 0.5

**Possible Causes**:
- Low evidence levels (mostly Level 3-4)
- Many conflicting results
- Insufficient p-value data

**Solution**:
- Import higher quality papers (Level 1a-1b)
- Focus on RCTs and meta-analyses
- Manually review conflict sources

#### 5. Slow Search Performance

**Symptom**: Search takes >5 seconds

**Possible Causes**:
- Large vector database (>1000 papers)
- Neo4j not indexed
- Neo4j memory settings too low

**Solution**:
```bash
# Re-initialize Neo4j indexes
python scripts/init_neo4j.py

# Check Neo4j query performance
# (Neo4j Browser: http://localhost:7474)
# Run EXPLAIN on slow queries

# Adjust Neo4j memory in docker-compose.yml
# NEO4J_server_memory_heap_max__size=4G
# NEO4J_server_memory_pagecache_size=1G
```

---

## Getting Help

### Documentation

- [API Documentation](api/graph_module.md) - Developer reference
- [TRD v3](TRD_v3_GraphRAG.md) - Technical design
- [NEO4J Setup](NEO4J_SETUP.md) - Database configuration

### Support

- GitHub Issues: [Report bugs or request features]
- Email: sangminpark@example.com

### Community

- Discord: [Join community] (if available)
- Discussions: [Ask questions] (if available)

---

## Next Steps

1. **Import Your Papers**: Start with 10-20 high-quality papers in your research area
2. **Explore Graph**: Use Knowledge Graph page to understand relationships
3. **Try MCP Tools**: Use Claude Desktop for natural language interaction
4. **Generate Drafts**: Use Draft Assistant for literature reviews
5. **Contribute**: Add new interventions to taxonomy, report bugs

Happy researching!
