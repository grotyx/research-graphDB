# Spine GraphRAG

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md) | [中文](README_zh.md) | [Español](README_es.md)

**Version**: 1.32.0 | **Status**: Production Ready

Sistema GraphRAG basado en Neo4j para literatura de cirugia de columna vertebral. Construye un grafo de conocimiento estructurado a partir de articulos medicos y permite la busqueda basada en evidencia.

- **1,030** articulos de cirugia de columna indexados
- **735** mapeos de conceptos SNOMED-CT (Intervention: 235, Pathology: 231, Outcome: 200, Anatomy: 69)
- **4,065+** pruebas automatizadas
- **10** herramientas MCP (integracion con Claude Desktop/Code)

---

## Arquitectura

```
PDF/Text --> Claude Haiku 4.5 --> SpineMetadata Extraction
                                    |
                  Neo4j (Almacen unico: Graph + Vector unificado)
                  +-- Graph: Paper, Pathology, Intervention, Outcome, Anatomy
                  +-- Vector: HNSW Index (3072d OpenAI embeddings)
                  +-- Ontology: SNOMED-CT IS_A jerarquia (735 mapeos)
                  +-- Hybrid Search: Multi-Vector + Graph Filter
                                    |
                  B4 GraphRAG Pipeline (v20, 8 etapas)
                  +-- 1. HyDE (Hypothetical Document Embedding)
                  +-- 2. Tiered Hybrid Search (Graph + Vector, 5x diversidad)
                  +-- 3. LLM Reranker (Claude Haiku)
                  +-- 4. Multi-Vector Search (embedding de abstract, 3x)
                  +-- 5. IS_A Expansion (pathology + filtro de palabras clave)
                  +-- 6. Graph Traversal Summary (cadena de evidencia)
                  +-- 7. Graph Hint (inyeccion de prompt del sistema)
                  +-- 8. Generacion de respuesta cuantitativa
```

## Funcionalidades principales

### Recuperacion (Retrieval)

- **Neo4j almacen unico**: Busqueda unificada Graph + Vector (HNSW 3072d)
- **HyDE**: Embedding de documento hipotetico para mejorar la busqueda de preguntas clinicas complejas
- **LLM Reranker**: Re-evaluacion de relevancia a nivel de chunk con Claude Haiku
- **Multi-Vector Retrieval**: Fusion de embeddings de chunk y abstract del articulo
- **Contextual Embedding Prefix**: Prefijo `[title | section | year]` para contexto del chunk
- **Direct Search Keyword Filter**: Eliminacion automatica de articulos fuera de tema

### Grafo de conocimiento

- **Ontologia SNOMED-CT**: 735 mapeos en 4 tipos de entidad con jerarquias IS_A
- **IS_A Expansion**: Recuperacion de articulos hermanos con filtro de palabras clave
- **Recorrido de grafo multi-salto**: Cadenas de evidencia, comparacion de intervenciones, analisis de resultados
- **Evidence-based Ranking**: Ordenamiento por valor-p, tamano del efecto y nivel de evidencia
- **Graph Hint**: Resumen de relacion intervention-pathology inyectado en el prompt del sistema

### Razonamiento

- **Extraccion de datos cuantitativos**: Enfasis en valores-p, odds ratios, intervalos de confianza y tasas de incidencia
- **Agentic RAG**: Descomposicion de preguntas complejas en subconsultas paralelas con sintesis posterior
- **Evidence Synthesis**: Tamano del efecto promedio ponderado, prueba de heterogeneidad I-squared
- **Deteccion de conflictos basada en GRADE**: Identificacion automatica de hallazgos contradictorios

### Pipeline de importacion

- **Claude Haiku 4.5** para analisis de PDF/texto con respaldo Gemini
- **Enriquecimiento bibliografico PubMed**: PubMed, Crossref/DOI y Basic con 3 niveles de respaldo
- **Entity Normalization**: 280+ mapeos de alias con vinculacion automatica SNOMED-CT
- **Chunk Validation**: Filtrado por longitud, degradacion de nivel, verificacion estadistica, deteccion de duplicados

### Integracion

- **10 herramientas MCP**: Integracion SSE con Claude Desktop y Claude Code
- **Formato de referencias**: 7 estilos (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- **Guia de escritura academica**: 9 listas de verificacion EQUATOR (STROBE, CONSORT, PRISMA, etc.)

---

## Inicio rapido

```bash
# 1. Configurar entorno
cp .env.example .env
# Establecer ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD en .env

# 2. Iniciar Neo4j
docker-compose up -d

# 3. Inicializar schema (esperar ~30s despues de iniciar Neo4j)
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. Ejecutar pruebas
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. Iniciar Web UI
streamlit run web/app.py
```

## Importacion de articulos (PubMed)

```bash
# Busqueda e importacion desde PubMed (Claude Code CLI)
/pubmed-import lumbar fusion outcomes

# Importar por PMIDs especificos
/pubmed-import --pmids 41464768,41752698

# Aplicar mapeos SNOMED + rellenar TREATS
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## Servidor MCP

```bash
# Iniciar con Docker (puerto 7777)
docker-compose up -d

# Verificacion de estado
curl http://localhost:7777/health

# Conectar desde Claude Code
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

### 10 herramientas MCP

| Herramienta | Descripcion | Acciones principales |
|-------------|-------------|---------------------|
| `document` | Gestion de documentos | add_pdf, list, delete, summarize, stats |
| `search` | Busqueda/razonamiento | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | Integracion PubMed/DOI | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | Analisis de texto | text, store_paper |
| `graph` | Exploracion de grafo | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | Deteccion de conflictos | find, detect, synthesize (basado en GRADE) |
| `intervention` | Analisis de procedimientos | hierarchy, compare, comparable |
| `extended` | Consultas extendidas | patient_cohorts, followup, cost, quality_metrics |
| `reference` | Formato de referencias | format, format_multiple, list_styles, preview |
| `writing_guide` | Guia de escritura | section_guide, checklist, expert, draft_response |

## Scripts operativos

| Script | Descripcion |
|--------|-------------|
| `scripts/init_neo4j.py` | Inicializacion de schema/indices Neo4j |
| `scripts/enrich_graph_snomed.py` | Aplicacion de codigos SNOMED + relleno TREATS |
| `scripts/repair_isolated_papers.py` | Reparacion de articulos aislados (re-analisis LLM) |
| `scripts/repair_missing_chunks.py` | Reparacion de Papers sin HAS_CHUNK |
| `scripts/build_ontology.py` | Construccion masiva de jerarquias IS_A |
| `scripts/normalize_entities.py` | Normalizacion de entidades (fusion de duplicados) |
| `scripts/backfill_paper_embeddings.py` | Generacion masiva de embeddings de abstracts |

## Estructura del proyecto

```
rag_research/
+-- src/
|   +-- graph/           # Capa de grafo Neo4j (client, DAOs, schema, taxonomy)
|   +-- builder/         # Procesamiento PDF/PubMed
|   +-- solver/          # Busqueda/razonamiento (tiered_search, hybrid_ranker, reranker)
|   +-- llm/             # Clientes LLM (Claude, Gemini)
|   +-- medical_mcp/     # Servidor MCP + 11 handlers de dominio
|   +-- core/            # Configuracion/logging/excepciones/embeddings/cache
|   +-- cache/           # Cache (query, embedding, semantic)
|   +-- ontology/        # Ontologia SNOMED-CT (735 mapeos)
|   +-- orchestrator/    # Enrutamiento de consultas/generacion Cypher
|   +-- external/        # APIs externas (PubMed)
+-- evaluation/          # Framework de benchmarks
+-- scripts/             # Scripts operativos
+-- web/                 # Streamlit UI
+-- tests/               # 4,065+ pruebas
+-- docs/                # Documentacion
```

## Variables de entorno

```bash
# Ver .env.example para referencia completa
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large, 3072d)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
LLM_MAX_CONCURRENT=5              # Llamadas LLM concurrentes (1-20)
PUBMED_MAX_CONCURRENT=5           # Procesamiento PubMed concurrente (1-10)
EMBEDDING_CONTEXTUAL_PREFIX=true  # Activar prefijo contextual de embedding
```

## Documentacion

| Documento | Proposito |
|-----------|-----------|
| [CHANGELOG](docs/CHANGELOG.md) | Historial de versiones |
| [PRD](docs/PRD.md) | Requisitos del producto |
| [TRD](docs/TRD_v3_GraphRAG.md) | Especificacion tecnica |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | Schema de nodos/relaciones |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | Guia de herramientas MCP |
| [ROADMAP](docs/ROADMAP.md) | Hoja de ruta de desarrollo |

## Autor

**Profesor Sang-Min Park, M.D., Ph.D.**

Departamento de Cirugia Ortopedica, Seoul National University Bundang Hospital, Seoul National University College of Medicine

[https://sangmin.me/](https://sangmin.me/)

## Licencia

Este proyecto se proporciona **solo para uso de investigacion y personal**. El uso comercial no esta permitido sin consentimiento previo por escrito.

Consulte [LICENSE](LICENSE) para mas detalles.

Copyright (c) 2024-2026 Sangmin Park
