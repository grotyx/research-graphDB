# Spine GraphRAG System

A Neo4j-based GraphRAG system for spine surgery medical literature.

## Features

- Neo4j Vector Index (HNSW) + Graph integrated search
- Claude Haiku 4.5 based PDF/text analysis
- PubMed bibliographic enrichment
- Evidence-based ranking (p-value, effect size, evidence level)
- MCP Server (SSE) for Claude Code/Desktop integration

## Quick Start

```bash
# Start Neo4j
docker-compose up -d

# Initialize schema
python scripts/init_neo4j.py

# Run Web UI
streamlit run web/app.py
```

## MCP Server (SSE Mode)

외부에서 Claude Code로 접속할 수 있는 SSE 서버를 실행합니다.

### 서버 실행

```bash
# SSE 서버 시작 (포트 7777)
PYTHONPATH=./src python3 -m medical_mcp.sse_server --host 0.0.0.0 --port 7777

# 백그라운드 실행
PYTHONPATH=./src nohup python3 -m medical_mcp.sse_server --host 0.0.0.0 --port 7777 > logs/sse_server.log 2>&1 &
```

### 서버 확인

```bash
# Health check
curl http://localhost:7777/health

# Ping
curl http://localhost:7777/ping

# 사용자 목록
curl http://localhost:7777/users
```

### 클라이언트 설정 (다른 컴퓨터에서)

Claude Code에서 SSE 서버에 연결:

```bash
# MCP 서버 추가
claude mcp add --transport sse medical-kag-remote http://YOUR_SERVER_IP:7777/sse --scope project

# 또는 .mcp.json 파일 생성
echo '{
  "mcpServers": {
    "medical-kag-remote": {
      "type": "sse",
      "url": "http://YOUR_SERVER_IP:7777/sse"
    }
  }
}' > .mcp.json
```

### 등록된 사용자

| User ID | 역할 |
|---------|------|
| system | admin (모든 문서 접근) |
| kim | user |
| park | user |
| lee | user |

특정 사용자로 접속: `http://YOUR_SERVER_IP:7777/sse?user=system`

## Environment Variables

```bash
# .env.example을 복사하여 사용
cp .env.example .env
# 필수 키 설정
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
NEO4J_PASSWORD=<your-password>
```

See [docs/](docs/) for detailed documentation.
