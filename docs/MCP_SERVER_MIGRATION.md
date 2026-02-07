# MCP Server Migration Guide

새 Mac으로 Spine GraphRAG MCP 서버를 이전하기 위한 설치 가이드입니다.

## 1. 시스템 요구사항

| 항목 | 최소 요구사항 | 권장 |
|------|--------------|------|
| macOS | 12.0 (Monterey) 이상 | 14.0 (Sonoma) 이상 |
| RAM | 8GB | 16GB 이상 |
| Storage | 20GB | 50GB 이상 |
| Python | 3.10 | 3.12 |

---

## 2. 필수 소프트웨어 설치

### 2.1 Homebrew 설치
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2.2 Python 설치
```bash
brew install python@3.12

# 버전 확인
python3 --version  # Python 3.12.x
```

### 2.3 Docker Desktop 설치
```bash
# 다운로드: https://www.docker.com/products/docker-desktop/
# 또는 Homebrew로 설치
brew install --cask docker

# 설치 후 Docker Desktop 실행 필요
```

### 2.4 Git 설치
```bash
brew install git
```

---

## 3. 프로젝트 복사

### 3.1 전체 프로젝트 폴더 복사
```bash
# 원본 Mac에서 압축
cd /Users/sangminpark/Desktop
zip -r rag_research.zip rag_research

# 새 Mac으로 복사 후 압축 해제
unzip rag_research.zip -d ~/Desktop/
```

### 3.2 필수 폴더 구조
```
rag_research/
├── src/                    # 소스 코드 (필수)
│   ├── medical_mcp/       # MCP 서버 메인
│   ├── graph/             # Neo4j 그래프 레이어
│   ├── builder/           # PDF 처리
│   ├── solver/            # 검색 모듈
│   └── llm/               # LLM 클라이언트
├── web/                   # Streamlit UI
├── data/                  # 데이터 (선택)
│   ├── extracted/         # 추출된 JSON (권장)
│   └── pdf/               # 원본 PDF
├── docker-compose.yml     # Neo4j 설정 (필수)
├── requirements.txt       # 의존성 (필수)
├── .env                   # 환경변수 (필수)
└── tests/                 # 테스트
```

---

## 4. Python 가상환경 설정

```bash
cd ~/Desktop/rag_research

# 가상환경 생성
python3 -m venv .venv

# 활성화
source .venv/bin/activate

# pip 업그레이드
pip install --upgrade pip
```

---

## 5. 의존성 설치

### 5.1 기본 의존성
```bash
pip install -r requirements.txt
```

### 5.2 주요 패키지 목록

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `mcp` | >=1.0.0 | MCP 서버 프레임워크 |
| `anthropic` | >=0.40.0 | Claude API (Haiku/Sonnet) |
| `neo4j` | >=5.15.0 | Neo4j 드라이버 |
| `sentence-transformers` | >=2.2.0 | 임베딩 생성 |
| `torch` | >=2.0.0 | PyTorch (임베딩용) |
| `streamlit` | >=1.28.0 | Web UI |
| `PyMuPDF` | >=1.23.0 | PDF 파싱 |

### 5.3 scispaCy 모델 설치 (선택사항)
```bash
pip install scispacy spacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz
```

---

## 6. 환경변수 설정

### 6.1 `.env` 파일 생성/수정
```bash
# .env 파일 위치: ~/Desktop/rag_research/.env

# LLM Provider
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-api03-...  # 본인 키로 교체
OPENAI_API_KEY=sk-proj-...          # OpenAI 임베딩용

# Claude 모델 설정
CLAUDE_MODEL=claude-haiku-4-5-20251001
CLAUDE_FALLBACK_MODEL=claude-sonnet-4-5-20250929

# Neo4j 설정
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=spineGraph2024
NEO4J_DATABASE=neo4j

# PubMed API (논문 메타데이터용)
NCBI_EMAIL=your-email@example.com
NCBI_API_KEY=your-ncbi-api-key
```

### 6.2 API 키 발급처

| API | 발급처 |
|-----|--------|
| Anthropic | https://console.anthropic.com/ |
| OpenAI | https://platform.openai.com/api-keys |
| NCBI (PubMed) | https://www.ncbi.nlm.nih.gov/account/settings/ |

---

## 7. Neo4j 데이터베이스 설정

### 7.1 Docker로 Neo4j 실행
```bash
cd ~/Desktop/rag_research

# Neo4j 시작 (백그라운드)
docker-compose up -d

# 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f neo4j
```

### 7.2 Neo4j 접속 확인
- **Browser**: http://localhost:7474
- **Bolt**: bolt://localhost:7687
- **계정**: neo4j / spineGraph2024

### 7.3 스키마 초기화 (30초 대기 후)
```bash
cd ~/Desktop/rag_research
source .venv/bin/activate
python scripts/init_neo4j.py
```

---

## 8. 데이터 마이그레이션 (선택)

### 8.1 Neo4j 데이터 백업/복원

**원본 Mac에서 백업:**
```bash
# Neo4j 컨테이너 중지
docker-compose stop neo4j

# 볼륨 백업
docker run --rm \
  -v spine_graphrag_neo4j_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar cvf /backup/neo4j_data.tar /data

# 다시 시작
docker-compose start neo4j
```

**새 Mac에서 복원:**
```bash
# 새 Mac에서 먼저 docker-compose up -d 실행 후 중지
docker-compose stop neo4j

# 볼륨 복원
docker run --rm \
  -v spine_graphrag_neo4j_data:/data \
  -v $(pwd)/backup:/backup \
  alpine sh -c "cd / && tar xvf /backup/neo4j_data.tar"

# 다시 시작
docker-compose start neo4j
```

### 8.2 extracted JSON 복사 (권장)
`data/extracted/` 폴더를 복사하면 PDF 재처리 없이 재임베딩 가능

---

## 9. MCP 서버 실행 테스트

### 9.1 직접 실행 테스트
```bash
cd ~/Desktop/rag_research
source .venv/bin/activate

# Medical KAG 서버 테스트
PYTHONPATH=./src python -m medical_mcp
```

### 9.2 Streamlit Web UI 테스트
```bash
streamlit run web/app.py
# 브라우저에서 http://localhost:8501 접속
```

### 9.3 테스트 실행
```bash
PYTHONPATH=./src pytest tests/ -v
```

---

## 10. Claude Code 연동 설정

### 10.1 Claude Code 설정 파일
`~/.claude.json` 또는 프로젝트 `.claude/settings.json`에 추가:

```json
{
  "mcpServers": {
    "medical-kag": {
      "command": "/Users/[username]/Desktop/rag_research/.venv/bin/python",
      "args": ["-m", "medical_mcp"],
      "cwd": "/Users/[username]/Desktop/rag_research/src",
      "env": {
        "PYTHONPATH": "/Users/[username]/Desktop/rag_research/src"
      }
    }
  }
}
```

> `[username]`을 새 Mac의 사용자 이름으로 변경

---

## 11. 체크리스트

설치 완료 후 확인:

- [ ] Python 3.10+ 설치됨
- [ ] Docker Desktop 실행 중
- [ ] Neo4j 컨테이너 실행 중 (`docker-compose ps`)
- [ ] Neo4j 브라우저 접속 가능 (http://localhost:7474)
- [ ] `.env` 파일에 API 키 설정됨
- [ ] `pip install -r requirements.txt` 성공
- [ ] `PYTHONPATH=./src python -m medical_mcp` 에러 없음
- [ ] `streamlit run web/app.py` 정상 실행
- [ ] 테스트 통과 (`pytest tests/`)

---

## 12. 트러블슈팅

### Docker 시작 안 됨
```bash
# Docker Desktop 실행 확인
open -a Docker

# 30초 대기 후 재시도
docker-compose up -d
```

### Neo4j 연결 실패
```bash
# 컨테이너 로그 확인
docker-compose logs neo4j

# 포트 사용 확인
lsof -i :7474
lsof -i :7687
```

### Python 패키지 설치 실패
```bash
# pip 업그레이드
pip install --upgrade pip

# 개별 설치
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers
```

### MCP 서버 시작 실패
```bash
# PYTHONPATH 확인
export PYTHONPATH=~/Desktop/rag_research/src
python -c "from medical_mcp import main; print('OK')"
```

---

## 13. 파일 크기 참고

| 항목 | 예상 크기 |
|------|----------|
| `src/` | ~5MB |
| `.venv/` | ~3GB (재설치 권장) |
| `data/pdf/` | 가변 |
| `data/extracted/` | ~10MB |
| Neo4j 볼륨 | ~500MB |

> `.venv/` 폴더는 복사하지 말고 새로 생성하는 것을 권장합니다.

---

## 14. 빠른 설치 스크립트

모든 과정을 자동화한 스크립트:

```bash
#!/bin/bash
# install.sh

set -e

echo "=== Spine GraphRAG MCP Server Installation ==="

# 1. 가상환경
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성
pip install --upgrade pip
pip install -r requirements.txt

# 3. Neo4j
docker-compose up -d

# 4. 30초 대기
echo "Waiting for Neo4j startup..."
sleep 30

# 5. 스키마 초기화
python scripts/init_neo4j.py

# 6. 테스트
PYTHONPATH=./src pytest tests/ -v --tb=short

echo "=== Installation Complete ==="
echo "Run: streamlit run web/app.py"
```

실행:
```bash
chmod +x install.sh
./install.sh
```
