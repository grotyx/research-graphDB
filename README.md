# Spine GraphRAG

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md) | [中文](README_zh.md) | [Español](README_es.md)

**Version**: 1.32.0 | **Status**: Production Ready

A Neo4j-based GraphRAG system for spine surgery literature. It builds a structured knowledge graph from medical papers and supports evidence-based retrieval through a unified graph-vector architecture.

- **1,030** spine surgery papers indexed
- **735** SNOMED-CT concept mappings (Intervention: 235, Pathology: 231, Outcome: 200, Anatomy: 69)
- **4,065+** automated tests
- **10** MCP tools for Claude Desktop/Code integration

---

## Architecture

```
PDF/Text --> Claude Haiku 4.5 --> SpineMetadata Extraction
                                    |
                  Neo4j (Single-Store: Graph + Vector Unified)
                  +-- Graph: Paper, Pathology, Intervention, Outcome, Anatomy
                  +-- Vector: HNSW Index (3072d OpenAI embeddings)
                  +-- Ontology: SNOMED-CT IS_A hierarchy (735 mappings)
                  +-- Hybrid Search: Multi-Vector + Graph Filter
                                    |
                  B4 GraphRAG Pipeline (v20, 8-Stage)
                  +-- 1. HyDE (Hypothetical Document Embedding)
                  +-- 2. Tiered Hybrid Search (Graph + Vector, 5x diversity)
                  +-- 3. LLM Reranker (Claude Haiku)
                  +-- 4. Multi-Vector Search (abstract embedding, 3x)
                  +-- 5. IS_A Expansion (pathology + keyword filter)
                  +-- 6. Graph Traversal Summary (evidence chain)
                  +-- 7. Graph Hint (system prompt injection)
                  +-- 8. Quantitative Answer Generation
```

## Key Features

### Retrieval

- **Neo4j Single-Store**: Unified Graph + Vector (HNSW 3072d) search in a single database
- **HyDE**: Hypothetical Document Embedding improves retrieval for complex clinical questions
- **LLM Reranker**: Claude Haiku re-evaluates chunk-level relevance after initial retrieval
- **Multi-Vector Retrieval**: Fuses chunk embeddings with paper-level abstract embeddings for diversity
- **Contextual Embedding Prefix**: `[title | section | year]` prefix encodes chunk context into embeddings
- **Direct Search Keyword Filter**: Automatic removal of off-topic papers

### Knowledge Graph

- **SNOMED-CT Ontology**: 735 mappings across 4 entity types with IS_A hierarchies
- **IS_A Expansion**: Pathology-aware sibling retrieval with keyword filtering
- **Multi-Hop Graph Traversal**: Evidence chains, intervention comparison, shared/unique outcome analysis
- **Evidence-Based Ranking**: Ranking by p-value, effect size, and evidence level
- **Graph Hint**: One-line intervention-pathology relationship summary injected into system prompt

### Reasoning

- **Quantitative Data Extraction**: Prompts emphasize extraction of p-values, odds ratios, confidence intervals, and incidence rates
- **Agentic RAG**: Complex questions decomposed into sub-queries, searched in parallel, then synthesized
- **Evidence Synthesis**: Weighted mean effect size, I-squared heterogeneity testing
- **GRADE-Based Conflict Detection**: Automatic identification of contradictory findings across studies

### Import Pipeline

- **Claude Haiku 4.5** for PDF/text analysis with Gemini fallback
- **PubMed Bibliographic Enrichment**: PubMed, Crossref/DOI, and Basic metadata with 3-tier fallback
- **Entity Normalization**: 280+ alias mappings with automatic SNOMED-CT linking
- **Chunk Validation**: Length filtering, tier demotion, statistical verification, near-duplicate detection

### Integration

- **10 MCP Tools**: SSE integration with Claude Desktop and Claude Code
- **Reference Formatting**: 7 citation styles (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **Academic Writing Guide**: 9 EQUATOR checklists (STROBE, CONSORT, PRISMA, CARE, STARD, SPIRIT, MOOSE, TRIPOD, CHEERS)

---

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Set ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD in .env

# 2. Start Neo4j
docker-compose up -d

# 3. Initialize schema (wait ~30s for Neo4j to start)
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. Run tests
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. Launch Web UI
streamlit run web/app.py
```

## Paper Import (PubMed)

```bash
# Search and import from PubMed (via Claude Code CLI)
/pubmed-import lumbar fusion outcomes

# Import by specific PMIDs
/pubmed-import --pmids 41464768,41752698

# Apply SNOMED mappings and backfill TREATS relationships
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## MCP Server

```bash
# Start with Docker (port 7777)
docker-compose up -d

# Health check
curl http://localhost:7777/health

# Connect from Claude Code
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

### 10 MCP Tools

| Tool | Description | Key Actions |
|------|-------------|-------------|
| `document` | Document management | add_pdf, list, delete, summarize, stats |
| `search` | Search and reasoning | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI integration | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | Text analysis | text, store_paper |
| `graph` | Graph exploration | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | Conflict detection | find, detect, synthesize (GRADE-based) |
| `intervention` | Surgical procedure analysis | hierarchy, compare, comparable |
| `extended` | Extended entity queries | patient_cohorts, followup, cost, quality_metrics |
| `reference` | Reference formatting | format, format_multiple, list_styles, preview |
| `writing_guide` | Academic writing guide | section_guide, checklist, expert, draft_response |

## Operational Scripts

| Script | Description |
|--------|-------------|
| `scripts/init_neo4j.py` | Initialize Neo4j schema and indexes |
| `scripts/enrich_graph_snomed.py` | Apply SNOMED codes and backfill TREATS relationships |
| `scripts/repair_isolated_papers.py` | Repair isolated papers via LLM re-analysis |
| `scripts/repair_missing_chunks.py` | Repair papers with missing HAS_CHUNK relationships |
| `scripts/build_ontology.py` | Batch-build IS_A hierarchies |
| `scripts/normalize_entities.py` | Entity normalization (merge duplicates) |
| `scripts/fix_outcome_normalization.py` | Outcome normalization |
| `scripts/fix_isa_hierarchy.py` | Expand IS_A coverage |
| `scripts/backfill_paper_embeddings.py` | Batch-generate paper abstract embeddings |

## Project Structure

```
rag_research/
+-- src/
|   +-- graph/           # Neo4j graph layer (client, DAOs, schema, taxonomy)
|   +-- builder/         # PDF/PubMed processing (chunk_validator, pubmed_processor)
|   +-- solver/          # Search/reasoning (tiered_search, hybrid_ranker, reranker, graph_traversal)
|   +-- llm/             # LLM clients (Claude, Gemini)
|   +-- medical_mcp/     # MCP server + 11 domain handlers
|   +-- core/            # Config, logging, exceptions, embeddings, cache
|   +-- cache/           # Caching (query, embedding, semantic)
|   +-- ontology/        # SNOMED-CT ontology (735 mappings)
|   +-- orchestrator/    # Query routing, Cypher generation
|   +-- external/        # External APIs (PubMed)
+-- evaluation/          # Benchmark framework (metrics, baselines, prompts)
+-- scripts/             # Operational scripts
+-- web/                 # Streamlit UI
+-- tests/               # 4,065+ tests
+-- docs/                # Documentation (PRD, TRD, CHANGELOG, etc.)
```

## Environment Variables

```bash
# See .env.example for full reference
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large, 3072d)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
LLM_MAX_CONCURRENT=5              # LLM concurrent calls (1-20)
PUBMED_MAX_CONCURRENT=5           # PubMed concurrent processing (1-10)
EMBEDDING_CONTEXTUAL_PREFIX=true  # Enable contextual embedding prefix
```

## Documentation

| Document | Purpose |
|----------|---------|
| [CHANGELOG](docs/CHANGELOG.md) | Version history |
| [PRD](docs/PRD.md) | Product requirements |
| [TRD](docs/TRD_v3_GraphRAG.md) | Technical specification |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | Node and relationship schema |
| [TERMINOLOGY_ONTOLOGY](docs/TERMINOLOGY_ONTOLOGY.md) | Terminology and ontology |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP tools usage guide |
| [ROADMAP](docs/ROADMAP.md) | Development roadmap |

## Author

**Professor Sang-Min Park, M.D., Ph.D.**

Department of Orthopaedic Surgery, Seoul National University Bundang Hospital, Seoul National University College of Medicine

[https://sangmin.me/](https://sangmin.me/)

## License

This project is provided for **research and personal use only**. Commercial use is not permitted without prior written consent.

See [LICENSE](LICENSE) for details.

Copyright (c) 2024-2026 Sangmin Park
