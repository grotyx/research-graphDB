# Spine GraphRAG Troubleshooting

> **Version**: 1.25.0 | **Last Updated**: 2026-03-02

## MCP 연결 끊김 & 재연결 (SSE 원격 접속)

### 증상
- Claude Code/Desktop에서 MCP 도구 호출 시 "connection closed" 또는 "server disconnected" 에러
- 장시간 대기 후 도구 호출 실패
- SSE 연결이 중간에 끊김

### 원인
| 원인 | 설명 |
|------|------|
| **유휴 타임아웃** | 서버 `CONNECTION_TIMEOUT` (기본 1시간) 이후 연결 종료 |
| **네트워크 장비** | 방화벽/프록시/NAT가 유휴 TCP 연결 끊음 (보통 5-15분) |
| **Neo4j 풀 만료** | 장시간 유휴 후 DB 연결 풀 만료 → 도구 호출 에러 |

### 재연결 방법

#### 방법 1: Claude Code에서 MCP 재연결
```bash
# Claude Code 터미널에서 MCP 서버 상태 확인
curl http://YOUR_SERVER_IP:7777/health

# MCP 서버 목록 확인 및 재연결
claude mcp list
claude mcp remove medical-kag-remote
claude mcp add --transport sse medical-kag-remote http://YOUR_SERVER_IP:7777/sse --scope project

# 또는 Claude Code에서 /mcp 명령으로 재연결
/mcp
```

#### 방법 2: 서버 측 Neo4j 연결 초기화
```bash
# Neo4j 연결만 재설정 (서버 재시작 불필요)
curl -X POST http://YOUR_SERVER_IP:7777/restart

# 서버 캐시 전체 초기화
curl -X POST http://YOUR_SERVER_IP:7777/reset
```

#### 방법 3: 서버 재시작
```bash
# 로컬 서버 재시작
pkill -f "sse_server" && PYTHONPATH=./src nohup python3 -m medical_mcp.sse_server --host 0.0.0.0 --port 7777 > logs/sse_server.log 2>&1 &

# Docker 서버 재시작
docker-compose restart mcp
```

### 연결 안정성 설정

서버 실행 시 타임아웃/heartbeat 조정:
```bash
# 긴 세션용 (heartbeat 15초, 타임아웃 2시간)
PYTHONPATH=./src python3 -m medical_mcp.sse_server \
  --host 0.0.0.0 --port 7777 \
  --heartbeat 15 --timeout 7200
```

### 서버 상태 확인
```bash
# Health check (연결 수, 유휴 시간 확인)
curl http://YOUR_SERVER_IP:7777/health | python3 -m json.tool

# Ping (서버 생존 확인)
curl http://YOUR_SERVER_IP:7777/ping
```

---

## Neo4j Connection Issues

```bash
# Check Neo4j status
docker ps | grep neo4j

# Restart Neo4j
docker-compose restart neo4j

# View logs
docker logs spine_graphrag_neo4j

# Access browser (after 30 seconds)
open http://localhost:7474
# Credentials: neo4j / <see .env NEO4J_PASSWORD>
```

## Common Errors

### 1. ServiceUnavailable: Neo4j service not available
- Wait 30 seconds after `docker-compose up` for full initialization
- Check logs: `docker logs spine_graphrag_neo4j`
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

### 12. Paper DOI is NULL in Neo4j (v1.18.0에서 수정됨)

**증상:** `store_paper` 또는 PDF 임포트 후 Neo4j에서 DOI가 NULL

**원인 (v1.14.23~v1.17.0):** `sanitize_doi()`의 `invalid_patterns` 리스트에 빈 문자열 `""` 포함.
Python에서 `"" in "any_string"`은 항상 `True`를 반환하므로 **모든 DOI**가 거부됨.

**해결:** v1.18.0으로 업데이트. 이전 버전에서 NULL DOI가 된 논문은 PubMed API로 복구 가능:
```cypher
// NULL DOI 논문 확인
MATCH (p:Paper) WHERE p.doi IS NULL OR p.doi = '' RETURN p.paper_id, p.title
```

### 13. Outcome 노드가 생성되지 않음 (v1.18.0에서 수정됨)

**증상:** 논문 임포트 후 Outcome 노드 및 AFFECTS 관계 없음

**원인:** `store_paper`에서 outcome dict를 5개 필드만 복사하여 나머지 데이터 손실 + `pdf_handler.py`에서 `pico_outcomes` 오타 (올바른 필드: `pico_outcome`)

**해결:** v1.18.0으로 업데이트 + MCP 서버 재시작

### 14. 고립 Paper — 관계(STUDIES/INVESTIGATES/INVOLVES) 누락 (v1.19.4에서 복구 스크립트 추가)

**증상:** DV 체크 2.1에서 고립 Paper 발견. 논문에 Chunk/임베딩은 있지만 엔티티 관계가 없음.

**원인:** PubMed 임포트 시 LLM 추출 단계가 실패/스킵되어 SpineMetadata가 생성되지 않음. RelationshipBuilder가 호출되지 않아 STUDIES, INVESTIGATES, INVOLVES 관계 미생성.

**해결:**
```bash
# 전체 고립 논문 자동 복구 (Claude Haiku로 abstract 재분석)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --max-concurrent 5

# 특정 논문만 복구
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --paper-ids "pubmed_12345"

# Dry-run (DB 변경 없이 추출 결과만 확인)
PYTHONPATH=./src python3 scripts/repair_isolated_papers.py --dry-run
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
