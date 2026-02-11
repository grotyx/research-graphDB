# Spine GraphRAG - 배포 및 이전 가이드

다른 컴퓨터로 프로젝트를 이전하기 위한 가이드입니다.

## 버전 정보

| 항목 | 값 |
|------|-----|
| **Version** | 7.14.30 |
| **Date** | 2026-02-07 |
| **Storage** | Neo4j (Graph + Vector 통합) |
| **MCP 전송** | SSE (Docker) / stdio (로컬) |

---

## 아키텍처

```
docker-compose up -d
├── neo4j (Neo4j 5.26)        ← 그래프 DB + 벡터 인덱스
│   ├── 포트: 7474 (브라우저), 7687 (Bolt)
│   └── 데이터: Docker Named Volume
│
└── mcp (Python 3.12)         ← MCP 서버 (SSE 모드)
    ├── 포트: 7777
    ├── 소스: 바인드 마운트 (호스트에서 편집 가능)
    └── 데이터: 바인드 마운트

Claude Desktop/Code ──SSE──▶ localhost:7777 ──Bolt──▶ neo4j:7687
```

---

## 필수 요구사항

| 항목 | 최소 버전 | 비고 |
|------|----------|------|
| Docker Desktop | 20.10+ | Neo4j + MCP 컨테이너 |
| Git | 2.30+ | 코드 클론 |
| RAM | 8GB | Neo4j 2GB + MCP + 여유 |
| Storage | 5GB | Neo4j 데이터 + Docker 이미지 |

> Python, pip 등은 Docker 안에서 실행되므로 호스트에 설치할 필요 없음

---

## 새 컴퓨터 설정 (3단계)

### Step 1: 클론 + 환경변수

```bash
git clone https://github.com/grotyx/medical_kag.git
cd medical_kag

# 환경변수 템플릿 복사 후 API 키 입력
cp .env.example .env
```

`.env`에 입력해야 할 API 키:

| 변수 | 필수 | 용도 | 발급처 |
|------|------|------|--------|
| `ANTHROPIC_API_KEY` | **필수** | Claude LLM (PDF 분석) | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | **필수** | 임베딩 (text-embedding-3-large, 3072d) | [platform.openai.com](https://platform.openai.com/api-keys) |
| `NCBI_EMAIL` | 선택 | PubMed API 이메일 | 본인 이메일 |
| `GEMINI_API_KEY` | 선택 | Gemini 폴백 LLM | [aistudio.google.com](https://aistudio.google.com/app/apikey) |

### Step 2: 실행 (한 줄)

```bash
docker-compose up -d
```

이것만으로 Neo4j + MCP 서버가 모두 실행됩니다.
- Neo4j healthcheck 통과 후 MCP 서버가 자동 시작됩니다 (~30초).
- MCP 서버는 `http://localhost:7777`에서 대기합니다.

### Step 3: Claude Desktop/Code 연결

프로젝트 루트에 `.mcp.json` 파일 생성:

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

> 원격 접속 시: `http://<서버IP>:7777/sse?user=system`

---

## 데이터 이전

코드는 Git에 있으므로 **데이터만 옮기면** 동일한 환경이 됩니다.

### 방법 A: Neo4j 덤프 (권장)

Neo4j DB에 모든 핵심 데이터가 포함되어 있습니다:
- 논문 메타데이터, 텍스트 청크, 벡터 임베딩
- 그래프 관계 (Pathology, Intervention, Outcome, Anatomy)
- Intervention Taxonomy (IS_A 계층)
- 모든 인덱스 (HNSW 벡터 + Range)

**현재 컴퓨터에서 덤프 생성:**

```bash
# 1. 컨테이너 정지
docker stop spine_graphrag_neo4j

# 2. 덤프 생성 (~868MB)
docker run --rm \
  -v rag_research_neo4j_data:/data \
  -v $(pwd):/backup \
  neo4j:5.26-community \
  neo4j-admin database dump neo4j --to-path=/backup

# 3. 다시 시작
docker start spine_graphrag_neo4j
```

`neo4j.dump` 파일을 USB, 클라우드 등으로 복사합니다.

**새 컴퓨터에서 복원:**

```bash
cd medical_kag

# 1. Neo4j만 먼저 시작 (빈 DB 생성)
docker-compose up -d neo4j
sleep 10
docker stop spine_graphrag_neo4j

# 2. 덤프 복원
docker run --rm \
  -v rag_research_neo4j_data:/data \
  -v $(pwd):/backup \
  neo4j:5.26-community \
  neo4j-admin database load neo4j --from-path=/backup --overwrite-destination=true

# 3. 전체 시작
docker-compose up -d
```

### 방법 B: extracted JSON으로 재구축

`data/extracted/` 폴더(~12MB)만 복사하면 그래프를 처음부터 재구축할 수 있습니다.

```bash
# extracted JSON 복사
cp -r /path/to/extracted/ data/extracted/

# Neo4j 스키마 초기화 + 재임포트
docker-compose exec mcp python scripts/init_neo4j.py
docker-compose exec mcp python scripts/reimport_all_papers.py
```

> 임베딩을 새로 생성하므로 OpenAI API 비용이 발생합니다.

### 방법 C: 빈 상태에서 시작

데이터 없이 시작하고 논문을 새로 추가합니다.

```bash
docker-compose up -d
docker-compose exec mcp python scripts/init_neo4j.py
```

---

## 바인드 마운트 - 호스트에서 파일 편집

Docker 컨테이너 안의 코드와 호스트의 코드가 **동일한 폴더를 공유**합니다:

```
호스트 (내 컴퓨터)              Docker 컨테이너
┌─────────────────┐           ┌─────────────────┐
│ src/             │ ════════ │ /app/src/        │
│ config/          │ ════════ │ /app/config/     │
│ scripts/         │ ════════ │ /app/scripts/    │
│ data/extracted/  │ ════════ │ /app/data/       │
│ data/styles/     │          │   extracted/     │
│ data/pdf/        │          │   styles/        │
└─────────────────┘           └─────────────────┘
```

VSCode 등에서 파일을 수정하면 컨테이너 안에도 즉시 반영됩니다.

### 편집 가능한 주요 파일

| 편집할 것 | 호스트 경로 | 반영 시점 |
|---|---|---|
| 논문 작성 가이드 | `src/medical_mcp/handlers/writing_guide_handler.py` | 컨테이너 재시작 |
| 저널 스타일 설정 | `data/styles/journal_styles.json` | 즉시 반영 |
| 검색/추론 로직 | `src/solver/` | 컨테이너 재시작 |
| MCP 핸들러 | `src/medical_mcp/handlers/` | 컨테이너 재시작 |
| 엔티티 정규화 규칙 | `src/graph/entity_normalizer.py` | 컨테이너 재시작 |
| SNOMED 매핑 | `src/ontology/spine_snomed_mappings.py` | 컨테이너 재시작 |
| 앱 설정 | `config/config.yaml` | 컨테이너 재시작 |

**코드 수정 후 반영:**

```bash
docker-compose restart mcp
```

---

## 상태 확인

### 컨테이너 상태

```bash
docker-compose ps
```

정상 출력:
```
spine_graphrag_neo4j   Up (healthy)   7474/tcp, 7687/tcp
spine_graphrag_mcp     Up             7777/tcp
```

### MCP 서버 엔드포인트

| URL | 용도 |
|-----|------|
| http://localhost:7777/health | 서버 상태 (Neo4j 연결, 활성 사용자) |
| http://localhost:7777/ping | 서버 생존 확인 |
| http://localhost:7777/tools | 사용 가능한 MCP 도구 목록 |
| http://localhost:7777/users | 등록된 사용자 목록 |
| http://localhost:7777/connections | 현재 연결 통계 |

### Neo4j 브라우저

- URL: http://localhost:7474
- 로그인: `neo4j` / `spineGraph2024`

---

## 로컬 개발 (Docker 없이)

Docker 없이 직접 실행하려면:

```bash
# Python 가상환경
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Neo4j만 Docker로
docker-compose up -d neo4j
sleep 30

# 스키마 초기화
PYTHONPATH=./src python scripts/init_neo4j.py

# MCP 서버 (stdio 모드 - Claude Code가 자동 실행)
# .mcp.json에 stdio 설정 사용

# MCP 서버 (SSE 모드 - 수동 실행)
PYTHONPATH=./src python -m medical_mcp.sse_server --port 7777
```

---

## 트러블슈팅

### MCP 서버가 시작되지 않음

```bash
# 로그 확인
docker-compose logs mcp

# Neo4j healthcheck 대기 중일 수 있음 (최대 60초)
docker-compose logs neo4j | tail -5
```

### Neo4j 연결 오류

```bash
# 컨테이너 상태 확인
docker-compose ps

# Neo4j 로그
docker-compose logs neo4j | tail -20

# 재시작
docker-compose restart neo4j
```

### 포트 충돌

```bash
# 사용 중인 포트 확인
lsof -i :7777
lsof -i :7687

# 포트 변경: docker-compose.yml에서 수정
```

### 메모리 부족

```yaml
# docker-compose.yml에서 Neo4j 메모리 조정
environment:
  - NEO4J_server_memory_heap_max__size=1g      # 기본 2g
  - NEO4J_server_memory_pagecache_size=256m    # 기본 512m
```

### MCP 재연결

```bash
# MCP 서버 캐시 초기화
curl -X POST http://localhost:7777/reset

# Neo4j 연결 재설정
curl -X POST http://localhost:7777/restart
```

---

## 요약: 옮겨야 할 것

| 항목 | 크기 | 필수 | 방법 |
|------|------|------|------|
| 코드 | - | **필수** | `git clone` |
| `.env` | 1KB | **필수** | API 키 직접 입력 |
| `neo4j.dump` | ~868MB | 권장 | USB/클라우드 복사 |
| `data/extracted/` | ~12MB | 선택 | 재구축 시 필요 |
| `data/pdf/` | 가변 | 선택 | 원본 논문 |

## 관련 문서

| 문서 | 용도 |
|------|------|
| [HOW_TO_RUN_kr.md](HOW_TO_RUN_kr.md) | 실행 가이드 (로컬/원격) |
| [NEO4J_SETUP.md](NEO4J_SETUP.md) | Neo4j 상세 설정 |
| [MCP_USAGE_GUIDE.md](MCP_USAGE_GUIDE.md) | MCP 도구 사용법 |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 문제 해결 |
