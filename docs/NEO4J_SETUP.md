# Neo4j Setup Guide for Spine GraphRAG

> **Version**: 1.27.0 | **Last Updated**: 2026-03-02

Complete setup guide for Neo4j graph database infrastructure. Since v1.14+, Neo4j serves as the **unified storage** for both graph relationships and vector embeddings (HNSW index).

## Prerequisites

- Docker and Docker Compose installed
- Python 3.10+
- Project dependencies installed (`pip install -r requirements.txt`)

## Quick Start

### 1. Start Neo4j Container

```bash
cd /Users/sangminpark/Documents/rag_research
docker-compose up -d
```

This starts:
- Neo4j 5.26 Community Edition
- HTTP interface on port 7474 (browser UI)
- Bolt protocol on port 7687 (database connection)
- APOC plugin pre-configured

### 2. Wait for Container to be Ready

```bash
# Check container status
docker-compose ps

# Watch logs until ready
docker-compose logs -f neo4j
# Look for: "Started."
# Press Ctrl+C to exit logs
```

### 3. Initialize Database Schema

```bash
python scripts/init_neo4j.py
```

This will:
- Create constraints (unique IDs)
- Create indexes (for fast lookups)
- Load intervention taxonomy (surgery hierarchy)
- Load common outcomes (VAS, ODI, etc.)
- Load pathologies (Lumbar Stenosis, AIS, etc.)

**Expected output:**
```
==========================================
Neo4j Initialization for Spine GraphRAG System
==========================================

[1/4] Connecting to Neo4j...
✅ Connected successfully

[2/4] Testing connection...
✅ Connection OK

[3/4] Initializing schema...
✅ Schema initialized successfully

[4/4] Checking graph statistics...

📊 Graph Statistics:
  Nodes:
    - Intervention: 25
    - Outcome: 12
    - Pathology: 10
  Relationships:
    - IS_A: 16

✅ Initialization Complete!
```

### 4. Access Neo4j Browser

Open http://localhost:7474 in your web browser.

**Login:**
- Username: `neo4j`
- Password: `<.env의 NEO4J_PASSWORD>`

## Configuration

### Environment Variables (.env)

```bash
# Neo4j Configuration — .env.example을 복사하여 사용
# cp .env.example .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
```

### Docker Compose Configuration

File: `/Users/sangminpark/Documents/rag_research/docker-compose.yml`

Key settings:
- **Image**: neo4j:5.26-community
- **Ports**: 7474 (HTTP), 7687 (Bolt)
- **APOC**: Enabled with full permissions
- **Memory**:
  - Heap: 512MB initial, 2GB max
  - Page cache: 512MB
- **Volumes**: Persistent data storage

## Testing the Setup

### Test 1: Connection Test

```bash
python -c "
import asyncio
from src.graph.neo4j_client import Neo4jClient

async def test():
    async with Neo4jClient() as client:
        result = await client.run_query('RETURN 1 as test')
        print(f'✅ Connection OK: {result}')

asyncio.run(test())
"
```

### Test 2: View Intervention Hierarchy

In Neo4j Browser (http://localhost:7474), run:

```cypher
// View TLIF hierarchy
MATCH (i:Intervention {name: 'TLIF'})
OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
RETURN i, path
```

### Test 3: View All Outcomes

```cypher
MATCH (o:Outcome)
RETURN o.name as outcome,
       o.type as type,
       o.unit as unit,
       o.direction as direction
ORDER BY o.type, o.name
```

### Test 4: View Pathologies

```cypher
MATCH (p:Pathology)
RETURN p.name as pathology,
       p.category as category,
       p.description as description
ORDER BY p.category, p.name
```

## Schema Overview

### Node Types

1. **Paper** - Research papers
   - Properties: paper_id, title, authors, year, journal, DOI, PMID
   - Metadata: sub_domain, study_design, evidence_level

2. **Pathology** - Diseases/diagnoses
   - Properties: name, category, icd10_code, description, aliases

3. **Anatomy** - Anatomical locations
   - Properties: name, region (cervical/thoracic/lumbar/sacral), level_count

4. **Intervention** - Surgical procedures
   - Properties: name, full_name, category, approach, is_minimally_invasive

5. **Outcome** - Clinical outcomes
   - Properties: name, type, unit, direction

### Relationship Types

1. **STUDIES** - (Paper)-[:STUDIES]->(Pathology)
2. **LOCATED_AT** - (Pathology)-[:LOCATED_AT]->(Anatomy)
3. **INVESTIGATES** - (Paper)-[:INVESTIGATES]->(Intervention)
4. **TREATS** - (Intervention)-[:TREATS]->(Pathology)
5. **AFFECTS** - (Intervention)-[:AFFECTS]->(Outcome)
   - Properties: value, p_value, effect_size, is_significant, direction
6. **IS_A** - (Intervention)-[:IS_A]->(Intervention) - Hierarchy
7. **CITES** - (Paper)-[:CITES]->(Paper)
8. **SUPPORTS** - (Paper)-[:SUPPORTS]->(Paper)
9. **CONTRADICTS** - (Paper)-[:CONTRADICTS]->(Paper)

## Pre-loaded Taxonomy Data

### Intervention Hierarchy

```
Fusion Surgery
├── Interbody Fusion
│   ├── TLIF (Transforaminal Lumbar Interbody Fusion)
│   ├── PLIF (Posterior Lumbar Interbody Fusion)
│   ├── ALIF (Anterior Lumbar Interbody Fusion)
│   ├── OLIF (Oblique Lumbar Interbody Fusion)
│   ├── LLIF/XLIF (Lateral Lumbar Interbody Fusion)
│   └── ACDF (Anterior Cervical Discectomy and Fusion)
└── Posterolateral Fusion

Decompression Surgery
├── Endoscopic Surgery
│   ├── UBE (Unilateral Biportal Endoscopic)
│   ├── FELD (Full-Endoscopic Lumbar Discectomy)
│   └── PSLD (Percutaneous Stenoscopic Lumbar Decompression)
├── Microscopic Surgery
│   └── MED (Microendoscopic Discectomy)
└── Open Decompression
    └── Laminectomy

Osteotomy (Deformity Correction)
├── SPO (Smith-Petersen Osteotomy)
├── PSO (Pedicle Subtraction Osteotomy)
└── VCR (Vertebral Column Resection)
```

### Outcomes

**Clinical:**
- VAS (Visual Analog Scale, 0-10 points)
- ODI (Oswestry Disability Index, %)
- JOA (Japanese Orthopaedic Association Score)

**Radiological:**
- Fusion Rate (%)
- Cobb Angle (degrees)
- SVA (Sagittal Vertical Axis, mm)
- PI-LL (PI-LL Mismatch, degrees)

**Functional:**
- EQ-5D
- SF-36
- SRS-22

**Complications:**
- Complication Rate (%)
- Reoperation Rate (%)
- PJK (Proximal Junctional Kyphosis, %)

### Pathologies

**Degenerative:**
- Lumbar Stenosis
- Lumbar Disc Herniation
- Spondylolisthesis
- Degenerative Scoliosis

**Deformity:**
- AIS (Adolescent Idiopathic Scoliosis)
- ASD (Adult Spinal Deformity)
- Kyphosis

**Trauma:**
- Burst Fracture
- Compression Fracture

**Tumor:**
- Spinal Metastasis

## Maintenance Commands

### View Database Statistics

```bash
python scripts/init_neo4j.py
```

### Reset Database (Delete All Data)

```bash
python scripts/init_neo4j.py --reset
```

**WARNING:** This deletes all data! You'll need to re-initialize.

### Verify APOC Plugin

```bash
python scripts/init_neo4j.py --verify-apoc
```

### Stop Neo4j

```bash
docker-compose down
```

### Stop and Remove Data (Fresh Start)

```bash
docker-compose down -v
```

**WARNING:** This deletes all data volumes!

## Troubleshooting

### Connection Refused Error

**Problem:** Can't connect to Neo4j

**Solution:**
```bash
# Check if container is running
docker-compose ps

# Restart container
docker-compose restart neo4j

# Check logs
docker-compose logs -f neo4j
```

### Authentication Failed

**Problem:** Wrong password

**Solution:** Make sure `.env`에 올바른 비밀번호가 설정되어 있는지 확인:
```
NEO4J_PASSWORD=<docker-compose.yml의 NEO4J_AUTH와 동일>
```

### APOC Not Available

**Problem:** APOC functions don't work

**Solution:**
```bash
# Rebuild container with APOC
docker-compose down
docker-compose up -d --force-recreate

# Verify APOC
python scripts/init_neo4j.py --verify-apoc
```

### Memory Issues

**Problem:** Neo4j crashes or slow performance

**Solution:** Edit `docker-compose.yml`:
```yaml
environment:
  - NEO4J_server_memory_heap_max__size=4g  # Increase from 2g
  - NEO4J_server_memory_pagecache_size=1g  # Increase from 512m
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

## Next Steps

After successful setup:

1. **Add Test Data**
   - Process 5 test papers (Task 1.3.1)
   - Verify graph relationships

2. **Test Search Queries**
   - Intervention hierarchy lookup
   - Outcome-based searches
   - Pathology-intervention mapping

3. **Integrate with Existing Pipeline**
   - Connect PDF processor to Neo4j
   - Hybrid search (Vector + Graph)
   - Response generation with graph context

## Resources

- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [APOC User Guide](https://neo4j.com/labs/apoc/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)

## Support

For issues:
1. Check Docker logs: `docker-compose logs neo4j`
2. Verify environment variables in `.env`
3. Test connection with `scripts/init_neo4j.py`
4. Review `scripts/README.md` for common issues
