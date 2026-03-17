# Medical GraphRAG

**A Graph-based Retrieval-Augmented Generation system for medical literature, powered by Neo4j and SNOMED-CT.**

[![License](https://img.shields.io/badge/License-Research%20%26%20Personal%20Use-blue)](#license)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](#requirements)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.15%2B-blue)](#requirements)
[![Version](https://img.shields.io/badge/Version-1.26.2-orange)](#changelog)

---

## Overview

Medical GraphRAG transforms medical research papers into a structured knowledge graph, enabling evidence-based retrieval through the combination of **graph relationships** and **vector similarity search** in a single Neo4j database.

The system uses **SNOMED-CT** (Systematized Nomenclature of Medicine - Clinical Terms) as its ontology backbone. While the architecture is domain-agnostic, the **current SNOMED mappings and extraction schema are configured for spine surgery** (735 curated mappings covering procedures, pathologies, outcomes, and anatomy). Adapting to other medical specialties requires replacing the mapping and normalization files — see [Adapting to Other Specialties](#adapting-to-other-specialties) below.

### What It Does

1. **Ingests** medical papers (PDF, text, or PubMed) and extracts structured metadata using LLM
2. **Builds** a knowledge graph with entities (Pathologies, Interventions, Outcomes, Anatomical sites) and their relationships
3. **Maps** extracted entities to SNOMED-CT concepts for standardized terminology
4. **Searches** using hybrid graph + vector queries with evidence-based ranking
5. **Reasons** over the graph to find evidence chains, compare interventions, and detect conflicts

### Current Database (Spine Surgery)

| Metric | Count |
|--------|-------|
| Papers | 638 |
| Text Chunks | 9,869 |
| Pathologies | 466 |
| Interventions | 672 |
| Outcomes | 2,836 |
| Anatomy Sites | 207 |
| SNOMED Mappings | 735 |
| Total Relationships | 40,000+ |

### Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Unified Graph + Vector Store** | Neo4j HNSW index (3072d OpenAI embeddings) + graph relationships in a single database |
| **SNOMED-CT Ontology** | 735 curated SNOMED mappings with IS_A hierarchy across 4 entity types |
| **LLM-Powered Extraction** | Claude Haiku 4.5 for metadata extraction with Gemini fallback |
| **Multi-Hop Graph Traversal** | Evidence chains, intervention comparisons, best-evidence retrieval |
| **Evidence-Based Ranking** | 3-way hybrid scoring: semantic (0.4) + authority (0.3) + graph relevance (0.3) |
| **PubMed Integration** | Automatic search, download, LLM extraction, and graph building from PubMed |
| **MCP Server** | 10 tools accessible from Claude Desktop/Code via SSE/HTTP |
| **Reference Formatting** | 7 citation styles (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard) |
| **Academic Writing Guide** | 9 EQUATOR checklists (STROBE, CONSORT, PRISMA, CARE, STARD, etc.) |
| **Conflict Detection** | GRADE-based evidence synthesis and contradiction identification |

---

## Architecture

```
                    ┌─────────────────────────┐
                    │   PDF / Text / PubMed    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   LLM Metadata Extractor │
                    │   (Claude Haiku 4.5)     │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │         Neo4j Unified Store          │
              │                                      │
              │  ┌─────────┐  ┌───────────────────┐  │
              │  │  Graph   │  │   Vector Index    │  │
              │  │  Layer   │  │  (HNSW 3072d)     │  │
              │  └────┬────┘  └────────┬──────────┘  │
              │       │                │              │
              │  ┌────▼────────────────▼──────────┐  │
              │  │   Single Cypher Query           │  │
              │  │   Graph Filter + Vector Search  │  │
              │  └────────────────┬────────────────┘  │
              │                   │                    │
              │  ┌────────────────▼────────────────┐  │
              │  │   SNOMED-CT IS_A Ontology       │  │
              │  │   (735 concepts, 4 entity types)│  │
              │  └─────────────────────────────────┘  │
              └──────────────────┬──────────────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │        Hybrid Ranker                 │
              │  Semantic 0.4 + Authority 0.3        │
              │  + Graph Relevance 0.3               │
              └──────────────────────────────────────┘
```

### Graph Schema

```
(Paper) ─STUDIES──────▶ (Pathology)       # Paper studies this condition
(Paper) ─INVESTIGATES─▶ (Intervention)    # Paper investigates this procedure
(Paper) ─INVOLVES─────▶ (Anatomy)         # Paper involves this anatomy
(Paper) ─HAS_CHUNK────▶ (Chunk)           # Text chunks with embeddings

(Intervention) ─TREATS──▶ (Pathology)     # Inferred: procedure treats condition
(Intervention) ─AFFECTS─▶ (Outcome)       # With p-value, effect size, direction

(Pathology)    ─IS_A──▶ (Pathology)       # SNOMED hierarchy
(Intervention) ─IS_A──▶ (Intervention)    # SNOMED hierarchy
(Outcome)      ─IS_A──▶ (Outcome)         # SNOMED hierarchy
(Anatomy)      ─IS_A──▶ (Anatomy)         # SNOMED hierarchy
```

Each entity node carries a `snomed_code` property for standardized identification.

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Neo4j 5.15+** (Community or Enterprise)
- **API Keys**: Anthropic (Claude) + OpenAI (embeddings)

### Installation

```bash
# Clone the repository
git clone https://github.com/grotyx/research-graphDB.git
cd research-graphDB

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section below)
```

### Start Neo4j

```bash
# Option A: Docker (recommended)
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5.26-community

# Option B: docker-compose
docker-compose up -d
```

### Initialize Schema

```bash
# Wait ~30 seconds for Neo4j to start, then:
PYTHONPATH=./src python3 scripts/init_neo4j.py
```

### Run Tests

```bash
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q
```

---

## Real-World Usage Workflows

### Workflow 1: Import Papers from PubMed

The most common workflow — search PubMed, import papers, and build the knowledge graph automatically.

```python
import asyncio
from builder.pubmed_bulk_processor import PubMedBulkProcessor
from graph.neo4j_client import Neo4jClient

async def import_papers():
    neo4j = Neo4jClient()
    await neo4j.connect()
    processor = PubMedBulkProcessor(neo4j)

    # Step 1: Search PubMed
    papers = await processor.search_pubmed(
        query="minimally invasive lumbar fusion outcomes",
        max_results=20,
        year_from=2023,
    )
    print(f"Found {len(papers)} papers")

    # Step 2: Import (LLM extraction + graph building + embedding)
    results = await processor.import_papers(
        papers=papers,
        skip_existing=True,     # Skip already-imported papers
        fetch_fulltext=True,    # Try PMC → DOI → abstract fallback
        max_concurrent=5,       # Parallel processing
    )
    print(f"Imported: {results.imported}, Skipped: {results.skipped}")
    await neo4j.close()

asyncio.run(import_papers())
```

**What happens during import:**
1. Fetches paper metadata from PubMed API
2. Tries to get full text (PMC Open Access → DOI/Unpaywall → abstract only)
3. Sends text to **Claude Haiku 4.5** for structured extraction:
   - Pathologies, Interventions, Outcomes, Anatomy
   - Evidence level (1a-5), study design, PICO data
   - Statistical results (p-values, effect sizes, confidence intervals)
   - 15-25 text chunks (tier1: results/conclusion, tier2: methods/discussion)
4. Normalizes entity names and links to SNOMED-CT codes
5. Builds Neo4j graph relationships (STUDIES, INVESTIGATES, INVOLVES, AFFECTS, TREATS)
6. Generates 3072-dim OpenAI embeddings for vector search

### Workflow 2: Import a Single PDF

```bash
# Add a single PDF
PYTHONPATH=./src python3 scripts/add_pdfs.py /path/to/paper.pdf

# Batch ingest from a directory
PYTHONPATH=./src python3 scripts/batch_ingest.py /path/to/pdf/directory/
```

### Workflow 3: Import by PMID

```python
# Import specific papers by PMID
results = await processor.import_papers(
    papers=await processor.downloader.fetch_papers_batch(
        ["41464768", "41752698", "41799389"]
    ),
    skip_existing=True,
    fetch_fulltext=True,
)
```

### Workflow 4: Enrich Graph with SNOMED & Ontology

After importing papers, run these scripts to enrich the knowledge graph:

```bash
# Apply SNOMED codes to all entities (from spine_snomed_mappings.py)
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py

# Build IS_A hierarchy for all 4 entity types
PYTHONPATH=./src python3 scripts/build_ontology.py

# Normalize duplicate entities (merge case variants, aliases)
PYTHONPATH=./src python3 scripts/normalize_entities.py --dry-run  # Preview first
PYTHONPATH=./src python3 scripts/normalize_entities.py             # Apply

# Repair any isolated papers (re-analyze with LLM)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --dry-run
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --max-concurrent 5
```

### Workflow 5: Search the Knowledge Graph (Python)

```python
from solver.tiered_search import TieredSearch

search = TieredSearch(neo4j_client)

# Semantic + graph hybrid search
results = await search.search(
    query="What are the outcomes of UBE for lumbar stenosis?",
    top_k=10,
)
for r in results:
    print(f"[{r.evidence_level}] {r.title} (score: {r.score:.3f})")
    print(f"  p-value: {r.p_value}, effect: {r.effect_size}")
```

---

## MCP Server — AI-Powered Research Assistant

This system is designed as an **[MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server**, meaning it works as a **backend knowledge engine for AI assistants** like Claude Desktop, Claude Code, or any MCP-compatible client. Instead of a traditional web UI, you interact with your medical literature database through natural language conversations with Claude.

Think of it as giving Claude a **personal medical literature database** — Claude can search papers, analyze evidence, compare interventions, format references, and help write academic papers, all backed by a structured knowledge graph.

### How It Works with Claude

```
┌─────────────────┐     MCP Protocol      ┌──────────────────────┐
│  Claude Desktop  │ ◄──────────────────► │  Medical GraphRAG    │
│  or Claude Code  │    (SSE / stdio)      │  MCP Server          │
│                  │                        │                      │
│  "Compare TLIF   │  ──── search ────►   │  Neo4j Knowledge     │
│   vs PLIF for    │                       │  Graph (735 SNOMED   │
│   stenosis"      │  ◄── evidence ────   │  concepts, papers,   │
│                  │                        │  embeddings)         │
└─────────────────┘                        └──────────────────────┘
```

### Setup MCP Server

**Option A: stdio mode** (Claude Desktop / Claude Code local)
```json
// In Claude Desktop config or .mcp.json:
{
  "mcpServers": {
    "medical-graphrag": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "medical_mcp.medical_kag_server"],
      "cwd": "/path/to/research-graphDB",
      "env": {
        "PYTHONPATH": "/path/to/research-graphDB/src"
      }
    }
  }
}
```

**Option B: SSE mode** (remote access, multi-user)
```bash
PYTHONPATH=./src python3 -m medical_mcp.sse_server --port 7777
curl http://localhost:7777/health  # Verify
```

**Option C: Connect from Claude Code**
```bash
claude mcp add --transport sse medical-graphrag http://YOUR_SERVER_IP:7777/sse --scope project
```

### 10 MCP Tools

| Tool | Description | Key Actions |
|------|-------------|-------------|
| `document` | Document management | add_pdf, list, delete, summarize, stats |
| `search` | Search & reasoning | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI integration | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | Text analysis | text, store_paper |
| `graph` | Graph exploration | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | Conflict detection | find, detect, synthesize (GRADE-based) |
| `intervention` | Intervention analysis | hierarchy, compare, comparable |
| `extended` | Extended entities | patient_cohorts, followup, cost, quality_metrics |
| `reference` | Reference formatting | format, format_multiple, list_styles, preview |
| `writing_guide` | Academic writing guide | section_guide, checklist, expert, draft_response |

### Usage Examples with Claude

Once the MCP server is connected, you interact through natural language:

#### Literature Search

> **You:** "Lumbar stenosis에 대한 수술적 치료의 최신 근거를 찾아줘"
>
> **Claude:** *(uses `search` tool)* — Finds relevant papers ranked by evidence level and relevance, returns structured results with p-values, effect sizes, and evidence grades.

#### Intervention Comparison

> **You:** "TLIF vs PLIF for single-level lumbar fusion — compare outcomes"
>
> **Claude:** *(uses `graph` → compare)* — Traverses the knowledge graph to find papers studying both techniques, compares outcomes (VAS, ODI, fusion rate, complications), and synthesizes evidence.

#### PubMed Import

> **You:** "PubMed에서 'cervical disc arthroplasty long-term outcomes' 검색하고 최근 5년 논문 가져와"
>
> **Claude:** *(uses `pubmed` → search, import)* — Searches PubMed, imports papers through the full pipeline (LLM extraction → SNOMED mapping → graph → embeddings) automatically.

#### Ontology Exploration

> **You:** "UBE의 상위 카테고리와 관련 수술법을 보여줘"
>
> **Claude:** *(uses `intervention` → hierarchy)* — Shows SNOMED IS_A hierarchy: UBE → Endoscopic Spine Surgery → Minimally Invasive Surgery → Spine Surgery, with sibling techniques.

#### Evidence Conflict Detection

> **You:** "Fusion vs motion preservation에 대한 상반된 근거가 있어?"
>
> **Claude:** *(uses `conflict` → detect, synthesize)* — Identifies contradictory findings, applies GRADE framework, explains discrepancies (study design, population, follow-up).

#### Academic Writing

> **You:** "Systematic review의 Methods 섹션을 PRISMA 기준으로 가이드해줘"
>
> **Claude:** *(uses `writing_guide` → checklist)* — Provides PRISMA checklist items with specific medical writing guidance.

> **You:** "이 논문들의 참고문헌을 Spine 저널 형식으로 포맷해줘"
>
> **Claude:** *(uses `reference` → format_multiple)* — Formats all references in Spine journal style.

#### Graph Exploration

> **You:** "Cervical myelopathy → surgical treatment → outcomes의 evidence chain을 보여줘"
>
> **Claude:** *(uses `graph` → evidence_chain)* — Multi-hop traversal showing which papers treat cervical myelopathy, what interventions they use, and what outcomes they report with evidence levels.

> **You:** "데이터베이스 현황 알려줘"
>
> **Claude:** *(uses `document` → stats)* — Returns paper count, entity counts, SNOMED coverage, evidence level distribution, and graph connectivity.

See [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) for the complete tool reference.

---

## How It Works

### 1. Paper Ingestion Pipeline

When you add a paper, the system runs this pipeline:

```
PDF/Text/PubMed
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Claude Haiku 4.5 — Structured Extraction                    │
│                                                              │
│  Input: Full text or abstract                                │
│  Output:                                                     │
│    ├─ Metadata: title, authors, journal, year                │
│    ├─ Evidence: level (1a-5), study design, sample size      │
│    ├─ Entities: pathologies, interventions, outcomes, anatomy │
│    ├─ Statistics: p-values, effect sizes, CIs, significance  │
│    ├─ PICO: population, intervention, comparison, outcome    │
│    └─ Chunks: 15-25 text segments (tier1 + tier2)            │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Entity Normalization + SNOMED Linking                        │
│                                                              │
│  "UBE" → "Unilateral Biportal Endoscopy" → SNOMED:708976006│
│  "stenosis" → "Spinal Stenosis" → SNOMED:76107001          │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Neo4j Graph Construction                                     │
│                                                              │
│  Paper → STUDIES → Pathology                                 │
│  Paper → INVESTIGATES → Intervention                         │
│  Paper → INVOLVES → Anatomy                                  │
│  Intervention → AFFECTS → Outcome (with p-value, effect)     │
│  Intervention → TREATS → Pathology (inferred)                │
│  Entity → IS_A → Parent (SNOMED hierarchy)                   │
│  Chunk embeddings → HNSW vector index (3072d)                │
└─────────────────────────────────────────────────────────────┘
```

### 2. Hybrid Search

Three signals are combined for ranking:

| Signal | Weight | Source |
|--------|--------|--------|
| **Semantic similarity** | 0.4 | Cosine similarity between query and chunk embeddings |
| **Authority score** | 0.3 | Evidence level, journal impact, sample size, statistical significance |
| **Graph relevance** | 0.3 | Relationship density, ontology distance, evidence chain connectivity |

### 3. Ontology-Aware Expansion

Queries are automatically expanded using the SNOMED IS_A hierarchy:

```
Query: "fusion outcomes"
  → Expands to: ALIF, PLIF, TLIF, XLIF, OLIF, MIDLF, ...
  → Finds papers about specific fusion types, not just "fusion"
```

### 4. Evidence Chain Traversal

Multi-hop graph queries answer complex clinical questions:

```
"What interventions treat lumbar stenosis with the best outcomes?"

Paper₁ ─STUDIES→ Lumbar Stenosis   Paper₁ ─INVESTIGATES→ UBE
                                    UBE ─AFFECTS→ VAS Back (p<0.001, improved)

Paper₂ ─STUDIES→ Lumbar Stenosis   Paper₂ ─INVESTIGATES→ Laminectomy
                                    Laminectomy ─AFFECTS→ VAS Back (p<0.05, improved)

→ Ranks by evidence strength: Paper₁ (stronger p-value) > Paper₂
```

---

## SNOMED-CT Ontology

The system includes **735 curated SNOMED-CT mappings** across 4 entity types:

| Entity Type | Mapped | SNOMED Category | Examples |
|-------------|--------|-----------------|----------|
| **Intervention** | 235 | Procedure | Laminectomy, TLIF, UBE, Pedicle Screw Fixation |
| **Pathology** | 231 | Disorder / Clinical Finding | Spondylolisthesis, Disc Herniation, Stenosis |
| **Outcome** | 200 | Observable Entity | VAS, ODI, Cobb Angle, Fusion Rate, JOA Score |
| **Anatomy** | 69 | Body Structure | Cervical (C1-C7), Thoracic (T1-T12), Lumbar (L1-L5) |

### How SNOMED Mapping Works

1. **Extraction**: LLM extracts medical entities from paper text
2. **Normalization**: Entity names are normalized to canonical forms (e.g., "UBE" → "Unilateral Biportal Endoscopy")
3. **SNOMED Linking**: Normalized entities are matched to SNOMED-CT codes via curated mappings
4. **IS_A Hierarchy**: Parent-child relationships enable ontology-aware search

### Extending Mappings

Add new SNOMED mappings in `src/ontology/spine_snomed_mappings.py`:

```python
INTERVENTION_SNOMED = {
    "your_procedure": SnomedMapping(
        code="SCTID",
        display="Procedure Name",
        parent_code="PARENT_SCTID"  # for IS_A hierarchy
    ),
}
```

Then apply:
```bash
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
PYTHONPATH=./src python3 scripts/build_ontology.py
```

---

## Database Maintenance

### Data Validation (DV)

The system includes a comprehensive data validation framework (`docs/DATA_VALIDATION.md`) with 6 phases:

```bash
# Run validation checks via Cypher queries:
# Phase 1: Node integrity (required properties, orphans, duplicates)
# Phase 2: Relationship integrity (isolated papers, IS_A cycles, TREATS completeness)
# Phase 3: Embedding completeness (chunk/abstract embeddings, vector indexes)
# Phase 4: Identifiers & SNOMED (DOI/PMID, SNOMED coverage, code validity)
# Phase 5: Data quality (content quality, distribution, duplicates)
# Phase 6: Ontology integrity (IS_A hierarchy, parent_code sync)
```

### Repair Scripts

```bash
# Repair isolated papers (no graph relationships)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --dry-run
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --max-concurrent 5

# Repair missing chunks
PYTHONPATH=./src python3 scripts/repair_missing_chunks.py --dry-run

# Repair ontology integrity
PYTHONPATH=./src python3 scripts/repair_ontology.py --dry-run --entity-type Intervention

# Backfill paper summaries via LLM
PYTHONPATH=./src python3 scripts/backfill_summary.py --max-concurrent 5
```

---

## Project Structure

```
research-graphDB/
├── src/
│   ├── graph/              # Neo4j graph layer
│   │   ├── neo4j_client.py       # Connection management + DAO delegation
│   │   ├── relationship_dao.py   # Relationship CRUD (17 methods)
│   │   ├── search_dao.py         # Vector/Hybrid search (7 methods)
│   │   ├── schema_manager.py     # Schema initialization & statistics
│   │   ├── relationship_builder.py  # Paper → Graph construction
│   │   ├── entity_normalizer.py  # Term normalization + SNOMED linking
│   │   └── taxonomy_manager.py   # IS_A hierarchy management
│   │
│   ├── builder/            # Document processing pipeline
│   │   ├── unified_pdf_processor.py   # PDF/text LLM extraction (Haiku)
│   │   ├── pubmed_downloader.py       # PubMed search & download
│   │   ├── pubmed_processor.py        # PubMed paper processing
│   │   ├── pubmed_bulk_processor.py   # End-to-end import orchestrator
│   │   └── reference_formatter.py     # Citation style formatting
│   │
│   ├── solver/             # Search & reasoning
│   │   ├── tiered_search.py           # Multi-tier search orchestration
│   │   ├── hybrid_ranker.py           # 3-way evidence-based ranking
│   │   ├── graph_traversal_search.py  # Multi-hop graph traversal
│   │   ├── graph_context_expander.py  # IS_A ontology expansion
│   │   └── conflict_detector.py       # Evidence conflict detection
│   │
│   ├── llm/                # LLM clients
│   │   ├── claude_client.py   # Claude API (primary)
│   │   └── gemini_client.py   # Gemini API (fallback)
│   │
│   ├── medical_mcp/        # MCP server + handlers
│   │   ├── medical_kag_server.py  # Server facade (10 tools)
│   │   ├── sse_server.py          # SSE/HTTP transport
│   │   └── handlers/              # 11 domain handlers
│   │
│   ├── ontology/           # SNOMED-CT ontology
│   │   ├── spine_snomed_mappings.py  # 735 curated mappings (SSOT)
│   │   ├── snomed_linker.py          # Entity → SNOMED matching
│   │   ├── concept_hierarchy.py      # IS_A hierarchy operations
│   │   └── snomed_proposer.py        # LLM-based mapping suggestions
│   │
│   ├── core/               # Configuration & utilities
│   ├── cache/              # Caching layer
│   ├── orchestrator/       # Query routing & Cypher generation
│   └── external/           # PubMed/NCBI API client
│
├── scripts/                # Operations & maintenance
│   ├── init_neo4j.py              # Schema/index initialization
│   ├── add_pdfs.py                # Single PDF ingestion
│   ├── batch_ingest.py            # Bulk PubMed ingestion
│   ├── enrich_graph_snomed.py     # SNOMED code enrichment
│   ├── build_ontology.py          # IS_A hierarchy construction
│   ├── repair_ontology.py         # Ontology integrity repair
│   ├── normalize_entities.py      # Entity deduplication & cleanup
│   ├── repair_isolated_papers.py  # Orphan paper recovery
│   ├── repair_missing_chunks.py   # Missing chunk recovery
│   └── backfill_summary.py        # LLM summary backfill
│
├── evaluation/             # Benchmark framework
│   ├── metrics.py          # P@K, R@K, NDCG@10, MRR, ELA
│   ├── baselines.py        # 4 baselines (Keyword, Vector, LLM, GraphRAG)
│   └── gold_standard/      # 29 questions, 517 candidate papers
│
├── tests/                  # Test suite
├── web/                    # Streamlit UI (optional)
├── docs/                   # Documentation
└── data/styles/            # Journal citation styles
```

---

## Environment Variables

```bash
cp .env.example .env
```

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude ([get one](https://console.anthropic.com/)) |
| `OPENAI_API_KEY` | OpenAI API key for embeddings ([get one](https://platform.openai.com/api-keys)) |
| `NEO4J_URI` | Neo4j Bolt URI (default: `bolt://localhost:7687`) |
| `NEO4J_PASSWORD` | Neo4j password |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key (fallback LLM) |
| `LLM_PROVIDER` | `claude` | Primary LLM: `claude` or `gemini` |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model for extraction |
| `LLM_MAX_CONCURRENT` | `5` | Max concurrent LLM API calls (1-20) |
| `PUBMED_MAX_CONCURRENT` | `5` | Max concurrent PubMed imports (1-10) |
| `NCBI_EMAIL` | — | Required for PubMed API access |
| `NCBI_API_KEY` | — | Optional: increases PubMed rate limit |

See [`.env.example`](.env.example) for the complete configuration reference.

---

## Adapting to Other Specialties

The **architecture is domain-agnostic** — Graph+Vector search, IS_A hierarchy, hybrid ranking, and MCP tools work with any medical domain. To adapt for another specialty (e.g., cardiology, oncology):

| File to Change | What to Replace |
|---------------|-----------------|
| `src/ontology/spine_snomed_mappings.py` | SNOMED mappings for target domain |
| `src/graph/entity_normalizer.py` | Normalization categories & aliases |
| `src/graph/normalization_maps.py` | Alias dictionaries for target domain |
| `src/graph/types/enums.py` | `SpineSubDomain` → domain-specific enum |
| `src/builder/unified_pdf_processor.py` | `SpineMetadata` dataclass + LLM prompts |

See [TERMINOLOGY_ONTOLOGY.md](docs/TERMINOLOGY_ONTOLOGY.md) Section 9 for the extension guide.

---

## Documentation

| Document | Description |
|----------|-------------|
| [CHANGELOG](docs/CHANGELOG.md) | Version history |
| [PRD](docs/PRD.md) | Product requirements |
| [TRD](docs/TRD_v3_GraphRAG.md) | Technical design reference |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | Node/relationship schema |
| [TERMINOLOGY_ONTOLOGY](docs/TERMINOLOGY_ONTOLOGY.md) | Ontology & terminology system |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP tool usage guide |
| [NEO4J_SETUP](docs/NEO4J_SETUP.md) | Neo4j setup instructions |
| [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | Common issues & solutions |
| [Developer Guide](docs/developer_guide.md) | Development guide |

---

## Requirements

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Python | >=3.10 | Runtime |
| anthropic | >=0.40.0 | Claude LLM API |
| openai | >=1.0.0 | Embeddings (text-embedding-3-large) |
| neo4j | >=5.15.0 | Graph database driver |
| pymupdf | >=1.23.0 | PDF text extraction |
| mcp | >=1.8.0 | Model Context Protocol server |
| httpx | >=0.24.0 | Async HTTP client |
| pydantic | >=2.0.0 | Data validation |
| google-genai | >=1.0.0 | *(optional)* Gemini fallback LLM |

---

## Author

**Professor Sang-Min Park, M.D., Ph.D.**

Department of Orthopaedic Surgery, Seoul National University Bundang Hospital, Seoul National University College of Medicine

[https://sangmin.me/](https://sangmin.me/)

---

## License

This project is provided for **research and personal use only**.
Commercial use requires prior written consent from the copyright holder.

See [LICENSE](LICENSE) for details.

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## Acknowledgments

- **SNOMED International** for the SNOMED-CT terminology system
- **Neo4j** for the graph database platform
- **Anthropic** for Claude AI
- **OpenAI** for embedding models
