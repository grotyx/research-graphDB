# Web UI Quick Start Guide

## 1. Start Neo4j

```bash
cd /Users/sangminpark/Desktop/rag_research
docker-compose up -d neo4j
```

Wait 10-15 seconds for Neo4j to start, then verify:
```bash
curl http://localhost:7474
# Should return HTML
```

## 2. Check Environment Variables

Ensure `.env` file exists in project root with:
```bash
ANTHROPIC_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
```

## 3. Start Streamlit UI

```bash
# Activate virtual environment (if using one)
source .venv/bin/activate

# Run main dashboard
streamlit run web/app.py
```

Browser will open to: http://localhost:8501

## 4. Quick Navigation

- **Home**: Dashboard with quick search
- **📄 Documents**: Upload PDFs
- **🔍 Search**: Hybrid search with QA (NEW FEATURES!)
- **🦴 Spine Explorer**: Browse intervention taxonomy (NEW!)
- **🔗 Graph Network**: Visualize relationships (NEW!)

## 5. Try These Features

### A. Browse Taxonomy
1. Click **🦴 Spine Explorer** in sidebar
2. Expand intervention categories
3. Click intervention to see evidence
4. Switch to **Sunburst** tab for visual chart

### B. Ask a Question
1. Click **🔍 Search** in sidebar
2. Select **🤖 Question Answering (QA)**
3. Enter: "Is TLIF effective for fusion rate?"
4. Click **🔍 Search**
5. View answer + evidence sources

### C. Visualize Graph
1. Click **🔗 Graph Network** in sidebar
2. Select intervention from dropdown (e.g., "TLIF")
3. See intervention-outcome relationships
4. Hover over nodes/edges for details

## Troubleshooting

**Neo4j not available?**
```bash
docker ps | grep neo4j  # Check if running
docker-compose logs neo4j  # Check logs
```

**No data showing?**
- Upload some PDFs first via **📄 Documents**
- Ensure papers are processed successfully
- Check ChromaDB exists: `ls data/chromadb/`

**API errors?**
- Verify `ANTHROPIC_API_KEY` in `.env`
- Check API quota/billing

## Next Steps

- See [README.md](README.md) for detailed documentation
- Check [../docs/Tasks_v3_GraphRAG.md](../docs/Tasks_v3_GraphRAG.md) for implementation details
- Explore all pages to discover more features!
