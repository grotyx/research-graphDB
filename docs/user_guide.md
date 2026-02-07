# Spine GraphRAG v7.14.29 - User Guide

## Overview

Spine GraphRAG is an advanced knowledge augmented generation system for spine surgery research. It uses Neo4j as a unified graph and vector database (HNSW 3072d) with LLM-based reasoning (Claude Haiku 4.5) to provide evidence-based answers to medical questions.

**Version**: 7.14.29
**Last Updated**: 2026-01-26

### Key Features (v7.14+)

- **Neo4j 통합 저장소**: Graph + Vector (OpenAI 3072d) 단일 DB
- **10개 MCP 도구**: Claude Desktop/Code 연동
- **PubMed 자동 보완**: 로컬 검색 부족 시 PubMed 자동 검색
- **참고문헌 포맷팅**: 7개 스타일 (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **학술 작성 가이드**: 9개 EQUATOR 체크리스트 (STROBE, CONSORT, PRISMA 등)
- **DOI 전문 조회**: Unpaywall/PMC Open Access 연동
- **SSE 서버**: 웹 클라이언트 실시간 연동

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
cd /Users/sangminpark/Desktop/rag_research

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Neo4j
docker-compose up -d

# 4. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Verify Installation

```bash
# Initialize Neo4j schema
python scripts/init_neo4j.py

# Check Neo4j connection
docker logs neo4j-spine
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
  - Model: claude-haiku-4-5-20241022 (default)
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

1. **Configure MCP Server** (in Claude Desktop settings):

```json
{
  "mcpServers": {
    "medical-kag": {
      "command": "python",
      "args": ["-m", "src.medical_mcp.medical_kag_server"],
      "cwd": "/Users/sangminpark/Desktop/rag_research",
      "env": {
        "ANTHROPIC_API_KEY": "your-api-key",
        "NEO4J_URI": "bolt://localhost:7687"
      }
    }
  }
}
```

2. **Restart Claude Desktop**

3. **Verify Tools**: Type in Claude: "What MCP tools are available?"

### Available Tools

#### 1. search_papers
Search papers in vector database.

**Usage**:
```
Claude, search for papers about "OLIF for lumbar stenosis"
```

**Response**:
```
Found 8 papers:
1. Smith et al. (2024) - "OLIF for degenerative lumbar stenosis" (score: 0.89)
2. Lee et al. (2023) - "Oblique lumbar interbody fusion outcomes" (score: 0.85)
...
```

#### 2. process_paper
Extract metadata from PDF.

**Usage**:
```
Claude, process the PDF at /Users/sangminpark/Desktop/papers/tlif_study.pdf
```

**Response**:
```
✅ Processed successfully:
- Title: TLIF for Lumbar Stenosis: A Randomized Trial
- Authors: Smith J, Doe A
- Evidence Level: 1b
- Interventions: TLIF, PLIF (comparison)
- Outcomes: Fusion Rate (92% vs 85%, p=0.001), VAS (2.3 vs 4.5, p<0.001)
```

#### 3. get_paper_info
Retrieve detailed paper information.

**Usage**:
```
Claude, get details for paper PMID_12345
```

#### 4. graph_search
Natural language Graph search.

**Usage**:
```
Claude, use graph search to find evidence that OLIF improves VAS
```

**Response**:
```
Found 3 Graph evidence:
1. OLIF → VAS: improved to 2.3 vs 4.5 control (p=0.001, Level 1b)
2. OLIF → VAS: reduction of 3.8 points (95% CI: 2.5-5.1, p<0.001, Level 1b)
3. OLIF → VAS: improved (p=0.02, Level 2a)

Conclusion: Strong evidence (3/3 studies significant)
```

#### 5. get_intervention_hierarchy
Get intervention taxonomy.

**Usage**:
```
Claude, show me the hierarchy for TLIF
```

**Response**:
```
Parents:
- Interbody Fusion
- Fusion Surgery

Siblings (same level):
- PLIF (Posterior Lumbar Interbody Fusion)
- ALIF (Anterior Lumbar Interbody Fusion)
- OLIF (Oblique Lumbar Interbody Fusion)
- LLIF (Lateral Lumbar Interbody Fusion)

Children: None (TLIF is a specific technique)
```

#### 6. find_evidence
Find Intervention → Outcome evidence.

**Usage**:
```
Claude, find evidence that TLIF improves fusion rate
```

#### 7. compare_interventions
Compare two interventions.

**Usage**:
```
Claude, compare TLIF vs PLIF on fusion rate
```

**Response**:
```
Comparison: TLIF vs PLIF on Fusion Rate

TLIF:
- 3 studies
- Average p-value: 0.003
- 3/3 statistically significant
- Mean fusion rate: 91.2%

PLIF:
- 4 studies
- Average p-value: 0.015
- 4/4 statistically significant
- Mean fusion rate: 88.5%

Recommendation: TLIF shows slightly higher fusion rate (2.7% difference)
but not statistically significant between them (p=0.08)
```

#### 8. detect_conflicts
Find contradictory results.

**Usage**:
```
Claude, check if there are conflicting results about OLIF and complication rate
```

#### 9. synthesize_answer
Generate evidence-based answer.

**Usage**:
```
Claude, synthesize an answer: "Is UBE effective for lumbar disc herniation?"
```

**Response**:
```
Based on Level 1b-2a evidence (5 studies):

Answer: Yes, UBE is effective for lumbar disc herniation.

Evidence:
- Pain reduction (VAS): 4.2 point improvement (p<0.001)
- Functional improvement (ODI): 25.3 point improvement (p<0.001)
- Complication rate: 2.1% (lower than open surgery 5.4%, p=0.02)
- Return to work: 6.2 weeks vs 8.5 weeks open (p=0.01)

Confidence: 0.82 (High - based on multiple RCTs)

Citations:
1. Kim et al. (2024). UBE for LDH: RCT. Spine, 49(3), 234-241.
2. Park et al. (2023). UBE vs open discectomy. JBJS, 105(8), 567-574.
...
```

#### 10. query_snomed
Link to SNOMED-CT concepts (if SNOMED integration enabled).

**Usage**:
```
Claude, find SNOMED code for lumbar stenosis
```

---

## Reference & Writing Tools

### 참고문헌 포맷팅 (v7.14.20+)

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

### 학술 논문 작성 가이드 (v7.14.20+)

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

### PubMed 연동 (v7.14.23+)

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
docker logs neo4j-spine
```

#### 2. PDF Processing Fails

**Symptom**: "Failed to extract metadata from PDF"

**Possible Causes**:
- PDF is scanned image (no text layer)
- PDF is corrupted
- Gemini API quota exceeded

**Solution**:
```bash
# Check if PDF has text
pdftotext test.pdf output.txt
cat output.txt  # Should show text

# Check Gemini API key
echo $GEMINI_API_KEY

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
- ChromaDB not optimized

**Solution**:
```bash
# Re-initialize Neo4j indexes
python scripts/init_neo4j.py

# Check Neo4j query performance
# (Neo4j Browser: http://localhost:7474)
# Run EXPLAIN on slow queries

# Optimize ChromaDB
# - Reduce top_k to 5
# - Use tier1 search only
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
