# Scripts

Utility scripts for Spine GraphRAG system.

## Neo4j Setup

### 1. Start Neo4j Docker Container

```bash
# From project root
cd /Users/sangminpark/Desktop/rag_research
docker-compose up -d
```

Check container status:
```bash
docker-compose ps
docker-compose logs neo4j
```

### 2. Initialize Schema

```bash
# Initialize schema, indexes, and taxonomy
python scripts/init_neo4j.py

# Skip taxonomy data
python scripts/init_neo4j.py --skip-taxonomy

# Verify APOC plugin
python scripts/init_neo4j.py --verify-apoc
```

### 3. Access Neo4j Browser

Open http://localhost:7474 in your browser.

**Login credentials:**
- Username: `neo4j`
- Password: `spineGraph2024`

### 4. Test Queries

```cypher
// View all nodes
MATCH (n) RETURN n LIMIT 25

// View intervention hierarchy
MATCH (i:Intervention {name: 'TLIF'})-[:IS_A*]->(parent)
RETURN i, parent

// View all outcomes
MATCH (o:Outcome) RETURN o

// View pathologies
MATCH (p:Pathology) RETURN p
```

## Troubleshooting

### Connection Refused

```bash
# Check if container is running
docker-compose ps

# Restart container
docker-compose restart neo4j

# View logs
docker-compose logs -f neo4j
```

### Reset Database

**WARNING: This deletes all data!**

```bash
python scripts/init_neo4j.py --reset
```

### Environment Variables

Make sure `.env` file has:
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=spineGraph2024
NEO4J_DATABASE=neo4j
```

## Docker Commands

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Stop and remove volumes (data will be lost!)
docker-compose down -v

# View logs
docker-compose logs -f neo4j

# Access Neo4j shell
docker-compose exec neo4j cypher-shell -u neo4j -p spineGraph2024
```
