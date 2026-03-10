# Medical GraphRAG

**A Graph-based Retrieval-Augmented Generation system for medical literature, powered by Neo4j and SNOMED-CT.**

[![License](https://img.shields.io/badge/License-Research%20%26%20Personal%20Use-blue)](#license)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](#requirements)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.15%2B-blue)](#requirements)

---

## Overview

Medical GraphRAG transforms medical research papers into a structured knowledge graph, enabling evidence-based retrieval through the combination of **graph relationships** and **vector similarity search** in a single Neo4j database.

The system uses **SNOMED-CT** (Systematized Nomenclature of Medicine - Clinical Terms) as its ontology backbone. While the architecture is domain-agnostic, the **current SNOMED mappings and extraction schema are configured for spine surgery** (696 curated mappings covering procedures, pathologies, outcomes, and anatomy). Adapting to other medical specialties requires replacing the mapping and normalization files — see [Adapting to Other Specialties](#adapting-to-other-specialties) below.

### What It Does

1. **Ingests** medical papers (PDF or text) and extracts structured metadata using LLM
2. **Builds** a knowledge graph with entities (Pathologies, Interventions, Outcomes, Anatomical sites) and their relationships
3. **Maps** extracted entities to SNOMED-CT concepts for standardized terminology
4. **Searches** using hybrid graph + vector queries with evidence-based ranking
5. **Reasons** over the graph to find evidence chains, compare interventions, and detect conflicts

### Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Unified Graph + Vector Store** | Neo4j HNSW index (3072d OpenAI embeddings) + graph relationships in a single database |
| **SNOMED-CT Ontology** | 696 curated SNOMED mappings with IS_A hierarchy across 4 entity types |
| **LLM-Powered Extraction** | Claude Haiku 4.5 for metadata extraction with Gemini fallback |
| **Multi-Hop Graph Traversal** | Evidence chains, intervention comparisons, best-evidence retrieval |
| **Evidence-Based Ranking** | 3-way hybrid scoring: semantic (0.4) + authority (0.3) + graph relevance (0.3) |
| **PubMed Integration** | Automatic bibliographic enrichment via PubMed, Crossref, and DOI |
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
              │  │   (696 concepts, 4 entity types)│  │
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
(Paper) ──TREATS──▶ (Pathology)
(Paper) ──USES────▶ (Intervention)
(Paper) ──MEASURES▶ (Outcome)
(Paper) ──TARGETS─▶ (Anatomy)
(Paper) ──HAS_CHUNK▶ (Chunk)        # text chunks with embeddings

(Pathology)    ──IS_A──▶ (Pathology)     # SNOMED hierarchy
(Intervention) ──IS_A──▶ (Intervention)  # SNOMED hierarchy
(Outcome)      ──IS_A──▶ (Outcome)       # SNOMED hierarchy
(Anatomy)      ──IS_A──▶ (Anatomy)       # SNOMED hierarchy
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

You can run Neo4j using Docker or install it natively.

**Option A: Docker**
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5.26-community
```

**Option B: Native installation**

Follow the [Neo4j Installation Guide](https://neo4j.com/docs/operations-manual/current/installation/).

### Initialize Schema

```bash
# Wait ~30 seconds for Neo4j to start, then initialize indexes and constraints
PYTHONPATH=./src python3 scripts/init_neo4j.py
```

### Ingest Papers

```bash
# Add a single PDF
PYTHONPATH=./src python3 scripts/add_pdfs.py /path/to/paper.pdf

# Batch ingest from a directory
PYTHONPATH=./src python3 scripts/batch_ingest.py /path/to/pdf/directory/

# Import from PubMed by PMID
# (uses the MCP pubmed tool or scripts)
```

### Run Tests

```bash
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q
```

---

## MCP Server

The system exposes 10 tools via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), allowing AI assistants like Claude to interact with the knowledge graph.

### Start the Server

```bash
# Start MCP server on port 7777
PYTHONPATH=./src python3 -m medical_mcp.sse_server --host 0.0.0.0 --port 7777

# Verify it's running
curl http://localhost:7777/health
```

### Connect from Claude Code

```bash
claude mcp add --transport sse medical-graphrag http://YOUR_SERVER_IP:7777/sse --scope project
```

### Available Tools

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

---

## SNOMED-CT Ontology

The system includes **696 curated SNOMED-CT mappings** across 4 entity types:

| Entity Type | Count | SNOMED Hierarchy | Examples |
|-------------|-------|------------------|----------|
| **Intervention** | 218 | Procedure | Laminectomy, Spinal Fusion, Discectomy |
| **Pathology** | 214 | Clinical Finding / Disorder | Spondylolisthesis, Herniated Disc, Stenosis |
| **Outcome** | 195 | Observable Entity | Pain Score (VAS), Disability Index, Fusion Rate |
| **Anatomy** | 69 | Body Structure | Cervical Spine, Lumbar Vertebra, Spinal Cord |

### How SNOMED Mapping Works

1. **Extraction**: LLM extracts medical entities from paper text
2. **Normalization**: Entity names are normalized to canonical forms (e.g., "UBE" → "Unilateral Biportal Endoscopy")
3. **SNOMED Linking**: Normalized entities are matched to SNOMED-CT codes via curated mappings
4. **IS_A Hierarchy**: Parent-child relationships enable ontology-aware search (e.g., searching "Fusion" also finds "ALIF", "PLIF", "TLIF")

### Extending Mappings

Add new SNOMED mappings in `src/ontology/spine_snomed_mappings.py`:

```python
# In the appropriate mapping dictionary:
INTERVENTION_SNOMED = {
    "your_procedure": SnomedMapping(
        code="SCTID",
        display="Procedure Name",
        parent_code="PARENT_SCTID"  # for IS_A hierarchy
    ),
}
```

Then run the enrichment script:
```bash
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
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
│   │   ├── unified_pdf_processor.py  # PDF/text unified processing
│   │   ├── pubmed_downloader.py      # PubMed search & download
│   │   ├── pubmed_processor.py       # PubMed paper LLM processing
│   │   └── reference_formatter.py    # Citation style formatting
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
│   │   ├── spine_snomed_mappings.py  # 696 curated mappings (SSOT)
│   │   ├── snomed_linker.py          # Entity → SNOMED matching
│   │   ├── concept_hierarchy.py      # IS_A hierarchy operations
│   │   └── snomed_proposer.py        # LLM-based mapping suggestions
│   │
│   ├── core/               # Configuration & utilities
│   │   ├── config.py       # Settings management
│   │   ├── exceptions.py   # Error hierarchy
│   │   └── embedding.py    # OpenAI embedding client
│   │
│   ├── cache/              # Caching layer
│   │   ├── cache_manager.py     # Cache orchestration
│   │   ├── query_cache.py       # Query result caching
│   │   └── embedding_cache.py   # Embedding vector caching
│   │
│   ├── orchestrator/       # Query routing
│   │   ├── query_pattern_router.py  # Query type classification
│   │   └── cypher_generator.py      # Dynamic Cypher generation
│   │
│   └── external/           # External APIs
│       └── pubmed_client.py  # PubMed/NCBI API client
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
├── tests/                  # Test suite (3,700+ tests)
├── docs/                   # Documentation
├── config/                 # Configuration files
└── data/styles/            # Journal citation styles
```

---

## Environment Variables

Create a `.env` file from the template:

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
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model to use |
| `LLM_MAX_CONCURRENT` | `5` | Max concurrent LLM API calls (1-20) |
| `PUBMED_MAX_CONCURRENT` | `5` | Max concurrent PubMed imports (1-10) |
| `NCBI_EMAIL` | — | Required for PubMed API access |
| `NCBI_API_KEY` | — | Optional: increases PubMed rate limit |
| `SNOMED_API_URL` | `https://snowstorm.ihtsdotools.org` | SNOMED-CT terminology server |
| `MCP_ADMIN_KEY` | — | Admin API key for MCP server endpoints |
| `MCP_MAX_CONNECTIONS` | `20` | Max concurrent MCP connections |

See [`.env.example`](.env.example) for the complete configuration reference.

---

## How It Works

### 1. Paper Ingestion

When you add a paper (PDF or text), the system:

1. Extracts text from PDF using PyMuPDF
2. Sends text to Claude Haiku for structured metadata extraction
3. Extracts: title, authors, journal, year, evidence level, study type, pathologies, interventions, outcomes, anatomy, statistical results
4. Normalizes entity names and links to SNOMED-CT codes
5. Creates graph nodes and relationships in Neo4j
6. Generates text chunks with OpenAI embeddings for vector search

### 2. Search & Retrieval

The hybrid search combines three signals:

- **Semantic similarity** (weight: 0.4): Vector cosine similarity between query and chunk embeddings
- **Authority score** (weight: 0.3): Evidence level, journal impact, sample size, statistical significance
- **Graph relevance** (weight: 0.3): Relationship density, ontology distance, evidence chain connectivity

### 3. Ontology-Aware Expansion

When searching for a concept, the system automatically expands queries using the SNOMED IS_A hierarchy:

```
Query: "fusion outcomes"
  → Expands to: ALIF, PLIF, TLIF, XLIF, OLIF, Lateral Fusion, ...
  → Finds papers about specific fusion types, not just those mentioning "fusion"
```

### 4. Evidence Chain Traversal

Multi-hop graph queries can answer complex questions:

```
"What interventions treat lumbar stenosis with the best outcomes?"

Paper₁ ──TREATS──▶ Lumbar Stenosis
Paper₁ ──USES────▶ Laminectomy
Paper₁ ──MEASURES▶ Pain Reduction (p<0.001)

Paper₂ ──TREATS──▶ Lumbar Stenosis
Paper₂ ──USES────▶ Fusion
Paper₂ ──MEASURES▶ Pain Reduction (p<0.05)

→ Ranks by evidence strength: Paper₁ (stronger p-value) > Paper₂
```

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

### Runtime

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

### Optional

| Dependency | Version | Purpose |
|-----------|---------|---------|
| google-genai | >=1.0.0 | Gemini fallback LLM |
| sentence-transformers | >=2.2.0 | Local embedding models |

---

## Current Domain: Spine Surgery

This release comes pre-configured with **696 SNOMED-CT mappings for spine surgery**, covering:

- **218 Interventions**: TLIF, UBE, OLIF, Laminectomy, Osteotomy, Pedicle Screw Fixation, etc.
- **214 Pathologies**: Lumbar Stenosis, Disc Herniation, Scoliosis, Cervical Myelopathy, etc.
- **195 Outcomes**: VAS, ODI, Cobb Angle, Fusion Rate, JOA Score, etc.
- **69 Anatomy**: Cervical (C1-C7), Thoracic (T1-T12), Lumbar (L1-L5), Sacral regions

The extraction schema (`SpineMetadata`), normalization categories, and LLM prompts are all tuned for spine surgery literature.

### Adapting to Other Specialties

The **architecture is domain-agnostic** — Graph+Vector search, IS_A hierarchy, hybrid ranking, and MCP tools work with any medical domain. To adapt for another specialty (e.g., cardiology, oncology):

| File to Change | What to Replace |
|---------------|-----------------|
| `src/ontology/spine_snomed_mappings.py` | SNOMED mappings for target domain |
| `src/graph/entity_normalizer.py` | Normalization categories & aliases |
| `src/graph/types/enums.py` | `SpineSubDomain` → domain-specific enum |
| `src/builder/unified_pdf_processor.py` | `SpineMetadata` dataclass + LLM prompts |

See [TERMINOLOGY_ONTOLOGY.md](docs/TERMINOLOGY_ONTOLOGY.md) Section 9 for the extension guide.

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
