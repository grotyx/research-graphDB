---
name: pubmed-import
description: PubMed 검색 → 결과 확인 → Sonnet 병렬 추출 → Neo4j 임포트. MCP/API 없이 Claude Code CLI에서 직접 처리.
user_invocable: true
---

# PubMed Import Skill

PubMed에서 논문을 검색하고, Claude Code CLI의 Sonnet subagent로 병렬 추출하여 Neo4j에 임포트합니다.
Haiku API 대신 Claude Code 내장 Sonnet을 사용하므로 API 비용이 없습니다.

## 워크플로우

```
Step 1: SEARCH  — PubMed 검색 + 결과 표시
Step 2: SELECT  — 사용자가 임포트할 논문 선택
Step 3: FETCH   — Abstract + Fulltext 다운로드 (PMC/DOI)
Step 4: EXTRACT — Sonnet subagent로 병렬 구조화 추출 (Haiku와 동일 프롬프트)
Step 5: VALIDATE — ChunkValidator로 chunk 품질 검증
Step 6: IMPORT  — Neo4j 그래프 구축 + Contextual Embedding + SNOMED 매핑
```

## 사용법

```
/pubmed-import                     # 대화형 모드 (검색어 입력)
/pubmed-import lumbar fusion UBE   # 직접 검색
/pubmed-import --pmids 41464768,41752698  # PMID로 직접 임포트
```

## 실행 방법

### Step 1: SEARCH

사용자가 검색어를 제공하면 (또는 args에서 파싱), PubMed API로 검색합니다.

```bash
cd /Users/sangminpark/Documents/rag_research
export NEO4J_PASSWORD=spineGraph2024
PYTHONPATH=./src python3 -c "
from external.pubmed_client import PubMedClient
client = PubMedClient()
pmids = client.search('USER_QUERY', max_results=20)
# fetch details for each pmid
details = client.fetch_paper_details(pmids)
for d in details:
    print(f'PMID: {d.pmid} | {d.year} | {d.title[:80]}')
    print(f'  Journal: {d.journal} | DOI: {d.doi}')
    print(f'  Abstract: {(d.abstract or \"\")[:150]}...')
    print()
"
```

결과를 사용자에게 번호와 함께 표시합니다. 사용자가 선택하도록 합니다.

### Step 2: SELECT

사용자 선택을 받습니다. 예: "1,3,5,7" 또는 "all" 또는 "1-10"

### Step 3: FETCH (Abstract + Fulltext)

선택된 논문의 abstract와 fulltext를 가져옵니다:

```bash
PYTHONPATH=./src python3 << 'SCRIPT'
import asyncio
from builder.pmc_fulltext_fetcher import PMCFullTextFetcher
from builder.doi_fulltext_fetcher import DOIFulltextFetcher

async def fetch(pmids, dois):
    pmc = PMCFullTextFetcher()
    results = await pmc.fetch_fulltext_batch(pmids, concurrency=3)
    # DOI fallback for papers without PMC fulltext
    doi_fetcher = DOIFulltextFetcher()
    for doi in dois_without_pmc:
        result = await doi_fetcher.fetch(doi, fetch_pmc=False)
    return results

asyncio.run(fetch(selected_pmids, selected_dois))
SCRIPT
```

**Fulltext 저장**: fulltext를 받은 논문은 `data/fulltext/{pmid}.txt`에 저장합니다:
```python
import os
os.makedirs('data/fulltext', exist_ok=True)
with open(f'data/fulltext/{pmid}.txt', 'w') as f:
    f.write(fulltext)
```

### Step 4: EXTRACT (Sonnet 병렬 처리)

**핵심**: 각 논문을 별도의 Sonnet subagent로 병렬 처리합니다.

각 subagent에게 전달할 내용:
1. 추출 프롬프트 (아래 EXTRACTION_PROMPT 전문)
2. 논문 텍스트 (fulltext 또는 abstract)
3. 논문 메타데이터 (PMID, DOI, title, authors, journal, year)

**Agent 호출 패턴**:
```
Agent(
  model="sonnet",
  prompt="""
아래 논문을 분석하여 구조화된 JSON을 추출해주세요.

## 논문 정보
- PMID: {pmid}
- Title: {title}
- DOI: {doi}

## 논문 텍스트
{paper_text}

## 추출 지시사항
{EXTRACTION_PROMPT}

위 JSON 스키마에 맞춰 추출 결과를 JSON으로 반환해주세요.
반드시 유효한 JSON만 반환하세요. JSON 외의 텍스트는 포함하지 마세요.
""",
  description="Extract paper: {pmid}"
)
```

**병렬 처리**: 최대 5개씩 Sonnet agent를 동시에 실행합니다.
각 agent의 결과(JSON)를 파싱하여 `data/extracted/{year}_{author}_{title}.json`에 저장합니다.

### Step 5: VALIDATE (Chunk 품질 검증)

추출된 chunks를 ChunkValidator로 검증합니다:

```python
from builder.chunk_validator import ChunkValidator

validator = ChunkValidator()
validated_chunks = validator.validate_chunks(
    chunks=data.get('chunks', []),
    embeddings=None  # 임베딩 전이므로 dedup은 Step 6 이후 별도 실행
)
data['chunks'] = validated_chunks
stats = validator.get_validation_stats()
print(f"Validated: {stats['total_input']}→{stats['total_output']} chunks "
      f"(rejected: {stats['rejected_short']}, demoted: {stats['demoted_tier']})")
```

### Step 6: IMPORT (Neo4j 구축 + Contextual Embedding)

추출된 JSON을 Neo4j에 임포트합니다:

```bash
PYTHONPATH=./src python3 << 'SCRIPT'
import asyncio, json, os
from dotenv import load_dotenv
load_dotenv()

from graph.neo4j_client import Neo4jClient
from graph.relationship_builder import RelationshipBuilder
from core.embedding import OpenAIEmbeddingGenerator, apply_context_prefix

async def import_paper(extracted_json_path):
    neo4j = Neo4jClient()
    await neo4j.connect()
    builder = RelationshipBuilder(neo4j)
    embedder = OpenAIEmbeddingGenerator()

    with open(extracted_json_path) as f:
        data = json.load(f)

    # 1. Build graph relationships (uses UNWIND batch queries)
    paper_data = data.get('metadata', {})
    result = await builder.build_from_paper(data)

    # 2. Apply contextual embedding prefix to chunks
    chunks = data.get('chunks', [])
    title = paper_data.get('title', '')
    year = paper_data.get('year', '')
    contents = [c['content'] for c in chunks]
    sections = [c.get('section', '') for c in chunks]

    # Prepend "[title | section | year] " to each chunk for contextual embedding
    prefixed_contents = apply_context_prefix(
        contents=contents,
        title=title,
        sections=sections,
        year=year
    )

    # 3. Generate embeddings (OpenAI text-embedding-3-large, 3072d)
    embeddings = await embedder.embed_batch(prefixed_contents)

    # 4. Store chunks with embeddings in Neo4j
    paper_id = paper_data.get('paper_id', '')
    for i, chunk in enumerate(chunks):
        await neo4j.run_query(
            """MERGE (c:Chunk {chunk_id: $chunk_id})
               SET c.content = $content, c.embedding = $embedding,
                   c.paper_id = $paper_id, c.tier = $tier,
                   c.evidence_level = $evidence_level
               WITH c
               MATCH (p:Paper {paper_id: $paper_id})
               MERGE (p)-[:HAS_CHUNK]->(c)""",
            {
                "chunk_id": f"{paper_id}_chunk_{i}",
                "content": chunk['content'],
                "embedding": embeddings[i],
                "paper_id": paper_id,
                "tier": chunk.get('tier', 'tier2'),
                "evidence_level": data.get('metadata', {}).get('evidence_level', '4')
            }
        )

    await neo4j.close()
    return result

asyncio.run(import_paper('data/extracted/file.json'))
SCRIPT
```

## Post-Import: SNOMED 매핑 + TREATS 백필

임포트 후 반드시 실행:

```bash
# SNOMED 코드 적용 + IS_A 계층 구축
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py

# TREATS 관계 백필 (paper_count 갱신)
PYTHONPATH=./src python3 -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv()
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    r = s.run('''
        MATCH (i:Intervention)-[t:TREATS]->(p:Pathology)
        WITH i, p, t, size([(i)<-[:INVESTIGATES]-(paper:Paper)-[:STUDIES]->(p) | paper]) AS actual
        WHERE t.paper_count <> actual
        SET t.paper_count = actual
        RETURN count(*) AS updated
    ''')
    print(f'TREATS paper_count updated: {r.single()[\"updated\"]}')
driver.close()
"
```

## EXTRACTION_PROMPT

Sonnet subagent에게 전달할 추출 프롬프트는 `src/builder/unified_pdf_processor.py`의
`_EXTRACTION_PROMPT_BASE` (line 411-776)을 그대로 사용합니다.

프롬프트를 로드하는 방법:
```python
import sys; sys.path.insert(0, 'src')
from builder.unified_pdf_processor import EXTRACTION_PROMPT
```

## 전문(Fulltext) 저장

fulltext를 받은 논문은 `data/fulltext/` 디렉토리에 저장합니다:
- 파일명: `{pmid}.txt` (예: `41464768.txt`)
- 포맷: plain text (섹션 구분 포함)
- PMC fulltext와 DOI fulltext 모두 저장

## 주의사항

1. **임베딩은 OpenAI API 필요**: chunk embedding(3072d)은 OpenAI API를 사용합니다. 이 부분은 API 호출이 필요합니다.
2. **Contextual Prefix 자동 적용**: v1.27.0부터 chunk 임베딩 시 `[title | section | year]` prefix가 자동 적용됩니다.
3. **기존 논문 중복 체크**: 임포트 전에 Neo4j에서 PMID/DOI 중복을 확인합니다.
4. **JSON 검증**: Sonnet 출력이 유효한 JSON인지 파싱 검증합니다.
5. **ChunkValidator**: 추출 후 chunk 품질 검증 (길이 필터, tier 강등, 통계 검증).
6. **SNOMED 매핑**: 임포트 후 `scripts/enrich_graph_snomed.py` 실행 필수.
7. **TREATS 백필**: 새 논문 추가 후 paper_count 갱신 필수.
