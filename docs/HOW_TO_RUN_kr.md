# Spine GraphRAG 실행 가이드

## 1. 사전 요구사항

- Docker Desktop
- Git
- Node.js (원격 접속 시 필요)

---

## 2. Docker로 실행 (권장)

Neo4j + MCP 서버를 한 번에 실행합니다.

### 2.1 최초 설정

```bash
git clone https://github.com/grotyx/medical_kag.git
cd medical_kag
cp .env.example .env
# .env에 ANTHROPIC_API_KEY, OPENAI_API_KEY 입력
```

### 2.2 실행

```bash
docker-compose up -d
```

### 2.3 상태 확인

```bash
docker-compose ps
# spine_graphrag_neo4j   Up (healthy)
# spine_graphrag_mcp     Up
```

- Neo4j 브라우저: http://localhost:7474 (neo4j / spineGraph2024)
- MCP 서버: http://localhost:7777/health

### 2.4 Claude Desktop/Code 연결

프로젝트 루트에 `.mcp.json` 생성:

```json
{
  "mcpServers": {
    "medical-kag": {
      "type": "sse",
      "url": "http://localhost:7777/sse"
    }
  }
}
```

### 2.5 코드 수정 후 반영

소스 코드가 바인드 마운트되어 있어 호스트에서 바로 편집 가능합니다.
Python 코드 수정 후:

```bash
docker-compose restart mcp
```

> 상세 내용: [DEPLOYMENT.md](DEPLOYMENT.md) 참조

---

## 3. 로컬 실행 (Docker 없이)

### 3.1 Neo4j 시작

```bash
docker-compose up -d neo4j
```

### 3.2 Python 환경

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 스키마 초기화 (최초 1회)

```bash
PYTHONPATH=./src python scripts/init_neo4j.py
```

### 3.4 MCP 서버 실행

**로컬 stdio 모드** - VSCode/Cursor에서 `.mcp.json` 설정으로 자동 실행. 별도 실행 불필요.

**SSE 모드 (수동 실행):**

```bash
PYTHONPATH=./src python -m medical_mcp.sse_server --host 0.0.0.0 --port 7777
```

**백그라운드 실행:**

```bash
PYTHONPATH=./src nohup python -m medical_mcp.sse_server --port 7777 > sse_server.log 2>&1 &
```

**서버 종료:**

```bash
pkill -f "medical_mcp.sse_server"
```

---

## 4. 외부 클라이언트 설정

### 4.1 Claude Desktop / Claude Code (Windows)

`%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "medical-kag": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://sangmin.me:7777/sse?user=system", "--allow-http"]
    }
  }
}
```

### 4.2 Cursor / VSCode (원격)

프로젝트 `.mcp.json` 또는 사용자 설정에 추가:
```json
{
  "mcpServers": {
    "medical-kag": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://sangmin.me:7777/sse?user=system", "--allow-http"]
    }
  }
}
```

> **참고**: Node.js가 설치되어 있어야 `npx` 명령이 작동합니다.

---

## 5. 서버 상태 확인

| 엔드포인트 | 용도 |
|-----------|------|
| http://sangmin.me:7777/health | 서버 상태 확인 |
| http://sangmin.me:7777/tools | 사용 가능한 도구 목록 |
| http://sangmin.me:7777/users | 등록된 사용자 목록 |

---

## 6. 사용자별 접속

URL 파라미터로 사용자 지정 가능:
- `?user=system` - 관리자 (모든 문서 접근)
- `?user=kim` - 일반 사용자
- `?user=park` - 일반 사용자
- `?user=lee` - 일반 사용자

예시:
```
http://sangmin.me:7777/sse?user=kim
```

---

## 7. 트러블슈팅

### Neo4j 연결 실패
```bash
docker-compose ps          # 컨테이너 상태 확인
docker-compose logs neo4j  # 로그 확인
docker-compose restart     # 재시작
```

### SSE 서버 오류
```bash
cat sse_server.log         # 로그 확인
pkill -f "medical_mcp"     # 프로세스 강제 종료
```

### 포트 충돌
```bash
lsof -i :7777              # 포트 사용 프로세스 확인
kill -9 <PID>              # 프로세스 종료
```

---

## 8. 설정 파일 위치

| 파일 | 용도 |
|------|------|
| `.mcp.json` | 로컬 MCP 설정 (stdio) |
| `.mcp.remote.json` | 원격 MCP 설정 (SSE) |
| `.env` | 환경변수 (API 키, DB 설정) |
| `docker-compose.yml` | Neo4j 컨테이너 설정 |

---

## 9. 스키마 확장 가이드

스키마, Taxonomy, SNOMED 코드는 언제든 추가 가능합니다. 기존 데이터에 영향 없음.

> **상세 가이드**: [docs/SCHEMA_UPDATE_GUIDE.md](docs/SCHEMA_UPDATE_GUIDE.md) 참조

### 9.1 Claude Code 프롬프트 (권장)

Claude Code에서 아래 프롬프트를 실행하면 전체 업데이트 과정을 자동으로 수행합니다:

```
Schema, Taxonomy, SNOMED-CT 전체 업데이트를 실행해줘.
docs/SCHEMA_UPDATE_GUIDE.md의 8.1 프롬프트 참조해서 진행해줘.
```

**분석만 수행 (변경 없음):**
```
Neo4j 데이터베이스와 추출된 논문 데이터를 분석해서
Schema, Taxonomy, SNOMED-CT 업데이트가 필요한 항목을 정리해줘.
```

**Neo4j 업데이트만:**
```
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --force
```

### 9.2 관련 파일

| 파일 | 용도 |
|------|------|
| `src/graph/types/schema.py` | 스키마 정의 (노드, 인덱스, Taxonomy, SNOMED) |
| `src/graph/entity_normalizer.py` | 용어 정규화 (별칭 → 정규 이름) |
| `src/ontology/spine_snomed_mappings.py` | SNOMED-CT 코드 매핑 |
| `scripts/init_neo4j.py` | 스키마 초기화 스크립트 |
| `scripts/update_schema_taxonomy.py` | 통합 업데이트 스크립트 |

### 9.3 새 Pathology/Intervention/Outcome 추가

`schema.py`의 `get_init_taxonomy_cypher()` 메서드에 추가:

```cypher
// 새 질환 추가
MERGE (:Pathology {name: 'Cauda Equina Syndrome', category: 'neurological', description: 'Emergency condition'})

// 새 수술 추가
MERGE (:Intervention {name: 'OLIF', category: 'fusion', description: 'Oblique Lumbar Interbody Fusion'})

// 새 결과변수 추가
MERGE (:Outcome {name: 'JOA Score', category: 'functional', unit: 'points', direction: 'higher_is_better'})
```

### 9.4 SNOMED 코드 추가

`schema.py`의 `get_enrich_snomed_cypher()` 메서드에 추가:

```cypher
MATCH (p:Pathology {name: 'Cauda Equina Syndrome'})
SET p.snomed_code = '192970008', p.snomed_term = 'Cauda equina syndrome'
```

### 9.5 변경사항 적용

```bash
# 스키마 재초기화 (기존 데이터 유지, 새 항목만 추가)
./.venv/bin/python scripts/init_neo4j.py

# 또는 통합 업데이트 스크립트 사용 (권장)
PYTHONPATH=./src python3 scripts/update_schema_taxonomy.py --force

# 또는 Neo4j Browser에서 직접 Cypher 실행
# http://localhost:7474
```

### 9.6 IS_A 계층 관계 추가

수술 기법 간 계층 관계 정의:

```cypher
MATCH (child:Intervention {name: 'OLIF'})
MATCH (parent:Intervention {name: 'Interbody Fusion'})
MERGE (child)-[:IS_A]->(parent)
```

---

## 10. 임베딩 설정

| 항목 | 값 |
|------|-----|
| 모델 | OpenAI text-embedding-3-large |
| 차원 | 3072 |
| 벡터 인덱스 | Neo4j HNSW |

> **주의**: 임베딩 모델 변경 시 기존 데이터 재임베딩 필요 (차원이 다르면 호환 안됨)
