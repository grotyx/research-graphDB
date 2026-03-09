# Spine GraphRAG Web UI

Interactive Streamlit-based web interface for the Spine GraphRAG system.

## Features

### 🦴 Spine Explorer
- **Intervention Taxonomy Browser**: Explore spine surgery interventions in hierarchical tree view
- **Sunburst Visualization**: Interactive radial chart of intervention categories
- **Evidence Summary**: Click interventions to view outcomes with statistical evidence
- **Search**: Find interventions by name, category, or aliases

### 🔍 Hybrid Search
- **Three Search Modes**:
  - 🤖 **Question Answering**: LLM-generated answers with evidence citations
  - 🔍 **Evidence Retrieval**: Raw graph + vector evidence without LLM
  - ⚔️ **Conflict Analysis**: Detect and explain contradictory findings

- **Three Search Types**:
  - **Hybrid (Recommended)**: Combines Graph + Vector (default: 60% graph, 40% vector)
  - **Graph Only**: Structured evidence from Neo4j (Intervention → Outcome)
  - **Vector Only**: Semantic similarity search from ChromaDB

- **Advanced Options**:
  - Adjustable graph/vector weights
  - Top-k results configuration
  - Min p-value threshold

### 🔗 Graph Network
- **Intervention-Outcome Network**: Interactive visualization of relationships
  - Square nodes: Interventions (size proportional to paper count)
  - Circle nodes: Outcomes
  - Edge colors: Green (improved), Red (worsened), Gray (unchanged)
  - Edge thickness: Significant (p<0.05) vs non-significant

- **Paper Citation Network**: Visualize paper-to-paper citation relationships
- **Graph Statistics**: Node/relationship counts, evidence level distribution

### 📄 Other Pages
- **Documents**: Upload and process PDF papers
- **Knowledge Graph**: Original paper relationship visualization
- **Draft Assistant**: LLM-assisted writing with evidence
- **PubMed**: Search and import papers from PubMed
- **Settings**: System configuration

## Prerequisites

1. **Neo4j Database** (required for Graph features):
   ```bash
   # Start Neo4j with docker-compose
   docker-compose up -d neo4j

   # Verify Neo4j is running
   curl http://localhost:7474
   ```

2. **Environment Variables** (`.env` file):
   ```bash
   # Claude API
   ANTHROPIC_API_KEY=your_api_key_here

   # Neo4j
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=password
   NEO4J_DATABASE=neo4j
   ```

3. **Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the UI

### Option 1: Main Dashboard
```bash
# From project root
streamlit run web/app.py
```

This opens the main dashboard with navigation to all pages.

### Option 2: Specific Page
```bash
# Spine Explorer
streamlit run web/pages/7_🦴_Spine_Explorer.py

# Hybrid Search
streamlit run web/pages/2_🔍_Search.py

# Graph Network
streamlit run web/pages/8_🔗_Graph_Network.py
```

### Access
Open browser to: http://localhost:8501

## Usage Examples

### Example 1: Browse Intervention Taxonomy
1. Go to **🦴 Spine Explorer** page
2. Browse the tree view to see intervention hierarchy
3. Click on any intervention to view evidence summary
4. See outcomes grouped by direction (improved/worsened)

### Example 2: Ask a Clinical Question
1. Go to **🔍 Hybrid Search** page
2. Select **🤖 Question Answering (QA)** mode
3. Enter query: "Is OLIF effective for improving fusion rate?"
4. Click **🔍 Search**
5. View LLM-generated answer with evidence citations

### Example 3: Compare Interventions
1. Go to **🔍 Hybrid Search** page
2. Enter query: "Compare TLIF vs PLIF for fusion rate"
3. Select **Graph Only** search type (for quantitative evidence)
4. Review statistical evidence from graph relationships

### Example 4: Detect Conflicts
1. Go to **🔍 Hybrid Search** page
2. Select **⚔️ Conflict Analysis** mode
3. Enter query about a controversial topic
4. View conflicting findings with explanations

### Example 5: Visualize Knowledge Graph
1. Go to **🔗 Graph Network** page
2. Select **Intervention-Outcome** tab
3. Filter by specific intervention or outcome
4. Explore interactive network visualization
5. Hover over nodes/edges for details

## Architecture

```
web/
├── app.py                          # Main dashboard
├── pages/
│   ├── 1_📄_Documents.py          # PDF upload
│   ├── 2_🔍_Search.py             # Hybrid search (ENHANCED)
│   ├── 3_📊_Knowledge_Graph.py    # Original KG visualization
│   ├── 4_✍️_Draft_Assistant.py   # Writing assistant
│   ├── 5_⚙️_Settings.py          # System settings
│   ├── 6_🔬_PubMed.py             # PubMed integration
│   ├── 7_🦴_Spine_Explorer.py     # NEW: Taxonomy browser
│   └── 8_🔗_Graph_Network.py      # NEW: Neo4j visualization
├── utils/
│   ├── server_bridge.py           # MCP server connection
│   ├── graph_utils.py             # NEW: Neo4j utilities
│   └── chain_bridge.py            # NEW: SpineGraphChain wrapper
└── README.md                       # This file
```

## Key Components

### Graph Utilities (`utils/graph_utils.py`)
- `get_neo4j_client()`: Singleton Neo4j connection
- `get_intervention_tree()`: Fetch taxonomy hierarchy
- `get_paper_network()`: Citation network data
- `create_network_graph()`: NetworkX + Plotly visualization

### Chain Bridge (`utils/chain_bridge.py`)
- `hybrid_search()`: Wrapper for SpineGraphChain retrieval
- `ask_question()`: Wrapper for QA/Conflict analysis
- Cached with `@st.cache_resource` for performance

## Troubleshooting

### Neo4j Connection Failed
```
⚠️ Neo4j not available. Please ensure Neo4j is running.
```

**Solution**:
1. Check if Neo4j container is running:
   ```bash
   docker ps | grep neo4j
   ```

2. Start Neo4j if not running:
   ```bash
   docker-compose up -d neo4j
   ```

3. Verify connection:
   ```bash
   curl http://localhost:7474
   ```

4. Check environment variables in `.env`

### LLM API Errors
```
Error creating SpineGraphChain: ...
```

**Solution**:
1. Verify `ANTHROPIC_API_KEY` in `.env`
2. Check API quota and billing
3. Test API key:
   ```python
   from anthropic import Anthropic
   client = Anthropic(api_key="your_key")
   ```

### No Data in UI
**Solution**:
1. Load some papers first via **📄 Documents** page
2. Check if papers were processed successfully
3. Verify ChromaDB data exists in `data/chromadb/`
4. For graph features, ensure data is in Neo4j:
   ```cypher
   MATCH (n) RETURN count(n)
   ```

## Performance Tips

1. **Caching**: UI uses Streamlit caching for Neo4j client and chain instances
2. **Filters**: Use filters to limit graph visualization to specific areas
3. **Batch Size**: Adjust max_papers in Paper Network to control visualization complexity
4. **Weights**: Fine-tune graph/vector weights based on your use case

## Development

### Adding New Pages
1. Create file in `web/pages/` with naming convention: `N_emoji_Name.py`
2. Follow existing page structure (imports, config, main function)
3. Use `utils/server_bridge.py` for server access
4. Use `utils/chain_bridge.py` for hybrid search

### Updating Visualizations
- Modify graph creation in `utils/graph_utils.py`
- Use Plotly for interactive charts
- NetworkX for graph layout algorithms

## Related Documentation

- [TRD_v3_GraphRAG.md](../docs/TRD_v3_GraphRAG.md) - Technical requirements
- [Tasks_v3_GraphRAG.md](../docs/Tasks_v3_GraphRAG.md) - Implementation tasks
- [CLAUDE.md](../CLAUDE.md) - Project overview

## Support

For issues or questions:
1. Check Neo4j logs: `docker logs neo4j`
2. Check Streamlit logs in terminal
3. Review error messages in UI
4. Consult documentation in `docs/`
