# Spine GraphRAG Troubleshooting

## Neo4j Connection Issues

```bash
# Check Neo4j status
docker ps | grep neo4j

# Restart Neo4j
docker-compose restart neo4j

# View logs
docker logs neo4j-spine

# Access browser (after 30 seconds)
open http://localhost:7474
# Credentials: neo4j / spine_graph_2024
```

## Common Errors

### 1. ServiceUnavailable: Neo4j service not available
- Wait 30 seconds after `docker-compose up` for full initialization
- Check logs: `docker logs neo4j-spine`
- Verify credentials in .env

### 2. Neo4j Vector Index not found
- Ensure Neo4j 5.26+ is running
- Initialize vector indexes: `python scripts/init_neo4j.py`
- Check indexes: `CALL db.indexes()` in Neo4j Browser

### 3. Import Error: No module named 'src'
- Set PYTHONPATH: `export PYTHONPATH=./src`
- Or use: `python -m pytest tests/`

### 4. Graph returns no results
- Initialize schema: `python scripts/init_neo4j.py`
- Check taxonomy: `MATCH (i:Intervention) RETURN count(i)`
- Expected: >20 interventions

### 5. RuntimeError: Task got Future attached to a different loop
- Streamlit에서 async Neo4j 사용 시 발생
- 해결: `web/utils/graph_utils.py`의 `SyncNeo4jClient` 사용

### 6. LLM API Errors
- Check ANTHROPIC_API_KEY in .env
- Verify API quota
- Check network connection

### 7. TypeError: '<' not supported between 'NoneType' and 'float'

- p_value가 None 또는 문자열 (`"<0.001"`)일 때 발생
- v1.14.15에서 수정됨: p_value 안전 파싱 적용
- MCP 서버 재시작 필요

### 8. VectorDB is required for adaptive_search

- ChromaDB가 제거된 환경에서 발생
- v1.14.15에서 수정됨: graph_search로 자동 fallback
- MCP 서버 재시작 필요

### 9. Evidence Search 결과 없음

- Paper-Entity 관계 부족일 가능성
- 재색인 실행: `python scripts/reindex_relationships.py --force`
- Taxonomy 기반 검색 확인 (TLIF → MIS-TLIF, BELIF 포함)

### 10. Vector Dimension Mismatch (v1.14.26)

**오류 메시지:**

```text
Index query vector has 768 dimensions, but indexed vectors have 3072
```

**원인:** Neo4j 벡터 인덱스(3072d)와 검색 임베딩(768d) 차원 불일치

**해결:**

1. `OPENAI_API_KEY` 환경변수 설정 확인
2. MCP 서버 재시작
3. v1.14.26 이상 버전 사용 (MedTE 768d 폴백 제거됨)

### 11. OPENAI_API_KEY not set (v1.14.26)

**오류 메시지:**

```text
OPENAI_API_KEY not set - required for vector search (3072d index)
OpenAI embedding required (3072d index)
```

**원인:** 벡터 검색/임포트에 OpenAI 임베딩 필수 (v1.14.26+)

**해결:**

```bash
# .env 파일에 추가
OPENAI_API_KEY=sk-...

# 또는 환경변수로 설정
export OPENAI_API_KEY=sk-...
```

## Testing

### Unit Tests

```bash
# All tests
pytest

# Specific module
pytest tests/graph/
pytest tests/builder/

# With coverage
pytest --cov=src --cov-report=html
```

### Manual Testing

**Neo4j Schema**:
```cypher
// Check taxonomy
MATCH (i:Intervention) RETURN i.name, i.category LIMIT 10

// Check relationships
MATCH (i:Intervention)-[:IS_A]->(parent)
RETURN i.name, parent.name

// Check indexes
CALL db.indexes()
```

**Entity Normalization**:
```python
from src.graph.entity_normalizer import EntityNormalizer

normalizer = EntityNormalizer()
result = normalizer.normalize_intervention("Biportal Endoscopic")
print(result.normalized)  # Expected: UBE
```

## Performance Tuning

### Neo4j Optimization

```cypher
// Query profiling
PROFILE
MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
WHERE a.is_significant = true
RETURN i, o
```

### Neo4j Vector Index
- Reduce top_k for production (5-10 recommended)
- Use graph filters before vector search
- Single Cypher query for hybrid search

### LLM Optimization
- Use response caching
- Batch PDF processing (asyncio.gather)
- Lower temperature for deterministic results (0.1)
