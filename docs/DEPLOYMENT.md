# Spine GraphRAG v1.29.0 - Deployment Guide

다른 컴퓨터로 프로젝트를 이전하기 위한 가이드입니다.

## 버전 정보

| 항목 | 값 |
|------|-----|
| **Version** | 1.29.0 |
| **Date** | 2026-03-02 |
| **SNOMED Mappings** | 735개 (I:235, P:231, O:200, A:69) + 패턴 매핑 |
| **Storage** | Neo4j (Graph + Vector 통합, ChromaDB 완전 제거) |

### 주요 기능

- **PubMed + DOI 3단계 Fallback**: PubMed → Crossref/DOI → Basic 순서로 항상 서지 보강
- **Crossref 서지 검색**: DOI 없이 제목+저자로 논문 검색
- **인용 논문 항상 저장**: 모든 enrichment 실패 시에도 Paper 노드 생성
- **SNOMED-CT 매핑**: 735개 매핑 (I:235, P:231, O:200, A:69)
- **Neo4j Vector Index**: HNSW 3072d 통합 그래프+벡터 검색
- **Academic Writing Guide**: 9개 EQUATOR 체크리스트 지원
- **DOI Fulltext Fetcher**: Crossref + Unpaywall API로 전문 자동 조회
- **Auto Normalizer Expansion**: 3계층 자동 별칭 확장 (v1.20.0)
- **Clinical Recommend**: 환자 맥락 기반 치료 추천 (v1.20.0)

## 필수 요구사항

| 항목 | 최소 버전 | 권장 | 비고 |
|------|----------|------|------|
| Python | 3.10+ | 3.11 | Type hints 필수 |
| Docker | 20.10+ | 24.0+ | Neo4j 컨테이너 |
| RAM | 8GB | 16GB | Neo4j + LLM |
| Storage | 10GB | 20GB | Neo4j + PDF |

## 프로젝트 구조

```
rag_research/
├── src/                        # 소스 코드 ⭐필수
│   ├── builder/               # PDF/텍스트 처리, 인용 분석
│   ├── graph/                 # Neo4j 클라이언트, 관계 빌더, 정규화 엔진
│   │   └── entity_normalizer.py      # 정규화 엔진
│   ├── ontology/              # SNOMED-CT 매핑 (735개)
│   │   └── spine_snomed_mappings.py  # 전체 매핑 정의
│   ├── medical_mcp/           # MCP 서버 (10개 통합 도구)
│   ├── solver/                # 검색/추론 모듈
│   ├── llm/                   # Claude/Gemini 클라이언트
│   └── storage/               # 저장소 추상화
├── web/                        # Streamlit UI ⭐필수
├── docs/                       # 문서 📖권장
│   ├── CHANGELOG.md           # 버전 히스토리
│   ├── GRAPH_SCHEMA.md        # Neo4j 스키마
│   ├── DEPLOYMENT.md          # 이 문서
│   └── ...
├── tests/                      # 테스트 ⚪선택
├── scripts/                    # 유틸리티 ⚪선택
├── config/                     # 설정 파일 ⭐필수
├── data/                       # 데이터 폴더
│   ├── extracted/             # JSON 추출 결과 ⚪선택
│   └── pdf/                   # 원본 PDF ⚪선택
├── .env.example                # 환경변수 템플릿 ⭐필수
├── docker-compose.yml          # Neo4j 컨테이너 ⭐필수
├── pyproject.toml              # Python 의존성 ⭐필수
├── requirements.txt            # pip 의존성 ⭐필수
├── config.yaml                 # 앱 설정 ⭐필수
└── CLAUDE.md                   # 프로젝트 규칙 📖권장
```

## 배포 단계

### Step 1: 파일 복사

```bash
# 방법 1: rsync (권장 - 불필요한 파일 제외)
rsync -avz --progress \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='logs/' \
  --exclude='data/chromadb/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  /path/to/rag_research/ user@newserver:~/rag_research/

# 방법 2: tar 압축 후 전송
cd /path/to
tar --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
    --exclude='logs' \
    -czvf rag_research_v1.27.0.tar.gz rag_research/

scp rag_research_v1.27.0.tar.gz user@newserver:~/

# 새 서버에서 압축 해제
ssh user@newserver "cd ~ && tar -xzvf rag_research_v1.27.0.tar.gz"
```

### Step 2: Python 환경 설정

```bash
cd ~/rag_research

# 가상환경 생성
python3 -m venv .venv

# 활성화
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt

# 또는 editable 모드로 설치
pip install -e .
```

### Step 3: 환경변수 설정

```bash
# 템플릿 복사
cp .env.example .env

# 편집
nano .env  # 또는 vim, code 등
```

**필수 API 키:**

| 변수 | 용도 | 발급처 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Claude LLM (PDF 분석, 엔티티 추출) | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | Embeddings (text-embedding-3-large) | [platform.openai.com](https://platform.openai.com/api-keys) |

**선택 API 키:**

| 변수 | 용도 | 발급처 |
|------|------|--------|
| `GEMINI_API_KEY` | Fallback LLM | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `NCBI_API_KEY` | PubMed 검색 (rate limit 향상) | [ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/account/settings/) |

### Step 4: Neo4j 시작

```bash
# Docker Compose로 Neo4j 시작
docker-compose up -d

# 상태 확인
docker-compose ps

# 로그 확인 (Started. 메시지 확인)
docker-compose logs -f neo4j
```

**Neo4j 브라우저:** http://localhost:7474

| 항목 | 값 |
|------|-----|
| Username | `neo4j` |
| Password | `<.env의 NEO4J_PASSWORD>` |

### Step 5: 스키마 초기화

```bash
# Neo4j 시작 후 30초 대기 (초기화 시간)
sleep 30

# 스키마 및 인덱스 생성
python scripts/init_neo4j.py
```

또는 Python에서 직접:

```python
import asyncio
from src.graph.neo4j_client import Neo4jClient

async def init():
    client = Neo4jClient()
    await client.connect()
    await client.initialize_schema()
    await client.close()
    print('✅ Schema initialized!')

asyncio.run(init())
```

### Step 6: 애플리케이션 실행

```bash
# Streamlit Web UI
streamlit run web/app.py

# 포트 지정
streamlit run web/app.py --server.port 8501

# 외부 접속 허용
streamlit run web/app.py --server.address 0.0.0.0
```

**접속:** http://localhost:8501

## 검증 체크리스트

```bash
#!/bin/bash
# 저장: verify_deployment.sh
# 실행: bash verify_deployment.sh

echo "=== Spine GraphRAG v1.27.0 Deployment Verification ==="

# 1. Python 환경
echo -e "\n[1/5] Python Environment"
python --version
pip show anthropic neo4j streamlit | grep -E "^(Name|Version)"

# 2. Neo4j 연결
echo -e "\n[2/5] Neo4j Connection"
python -c "
import os; from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    r = s.run('RETURN 1')
    print('✅ Neo4j OK')
driver.close()
"

# 3. SNOMED 매핑
echo -e "\n[3/5] SNOMED Mappings"
python -c "
import sys; sys.path.insert(0, 'src')
from ontology.spine_snomed_mappings import *
print(f'Intervention: {len(SPINE_INTERVENTION_SNOMED)}')
print(f'Pathology: {len(SPINE_PATHOLOGY_SNOMED)}')
print(f'Outcome: {len(SPINE_OUTCOME_SNOMED)}')
print(f'Anatomy: {len(SPINE_ANATOMY_SNOMED)}')
total = len(SPINE_INTERVENTION_SNOMED) + len(SPINE_PATHOLOGY_SNOMED) + len(SPINE_OUTCOME_SNOMED) + len(SPINE_ANATOMY_SNOMED)
print(f'Total: {total}')

# v1.20 entries
dm = SPINE_PATHOLOGY_SNOMED.get('Diabetes Mellitus')
ssi_s = SPINE_OUTCOME_SNOMED.get('Superficial Surgical Site Infection')
ssi_d = SPINE_OUTCOME_SNOMED.get('Deep Surgical Site Infection')
if dm and ssi_s and ssi_d:
    print('✅ v1.20 entries OK')
else:
    print('❌ v1.20 entries MISSING')
"

# 4. LLM 연결
echo -e "\n[4/5] Claude API"
python -c "
import os
from anthropic import Anthropic
client = Anthropic()
r = client.messages.create(
    model='claude-haiku-4-5-20251001',
    max_tokens=10,
    messages=[{'role': 'user', 'content': 'Hi'}]
)
print('✅ Claude API OK')
"

# 5. 버전 확인
echo -e "\n[5/5] Version Check"
grep "Version" CLAUDE.md | head -1

echo -e "\n=== Verification Complete ==="
```

## 데이터 마이그레이션 (선택)

### Neo4j 데이터 백업/복원

```bash
# === 소스 서버에서 백업 ===
# Neo4j 중지 (데이터 일관성)
docker-compose stop neo4j

# 백업 생성
docker run --rm \
  -v rag_research_neo4j_data:/data \
  -v $(pwd):/backup \
  neo4j:5.26-community \
  neo4j-admin database dump neo4j --to-path=/backup/

# 백업 파일 전송
scp neo4j.dump user@newserver:~/rag_research/

# === 대상 서버에서 복원 ===
# Neo4j 중지
docker-compose stop neo4j

# 복원
docker run --rm \
  -v rag_research_neo4j_data:/data \
  -v $(pwd):/backup \
  neo4j:5.26-community \
  neo4j-admin database load neo4j --from-path=/backup/neo4j.dump --overwrite-destination

# Neo4j 시작
docker-compose start neo4j
```

### data/extracted/ JSON 파일

```bash
# JSON 추출 결과 복사 (선택 - 재생성 가능)
rsync -avz data/extracted/ user@newserver:~/rag_research/data/extracted/
```

## 트러블슈팅

### Neo4j 연결 오류

```bash
# 포트 확인
netstat -an | grep 7687
lsof -i :7687

# Docker 상태
docker-compose ps
docker-compose logs neo4j | tail -50

# 재시작
docker-compose restart neo4j
```

### Import 오류

```bash
# PYTHONPATH 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# .bashrc에 영구 추가
echo 'export PYTHONPATH="${PYTHONPATH}:~/rag_research/src"' >> ~/.bashrc
source ~/.bashrc
```

### 메모리 부족

```yaml
# docker-compose.yml 수정
environment:
  - NEO4J_server_memory_heap_initial__size=1G
  - NEO4J_server_memory_heap_max__size=4G
  - NEO4J_server_memory_pagecache_size=1G
```

### API 키 오류

```bash
# 환경변수 확인
echo $ANTHROPIC_API_KEY | head -c 20
echo $OPENAI_API_KEY | head -c 10

# .env 로드 확인
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('ANTHROPIC:', os.getenv('ANTHROPIC_API_KEY', 'NOT SET')[:20])
print('OPENAI:', os.getenv('OPENAI_API_KEY', 'NOT SET')[:10])
"
```

## Quick Start (한 줄 요약)

```bash
# 새 서버에서 전체 설정 (API 키는 수동 입력 필요)
cd ~/rag_research && \
python3 -m venv .venv && source .venv/bin/activate && \
pip install -r requirements.txt && \
cp .env.example .env && \
echo "Edit .env with your API keys, then run:" && \
echo "docker-compose up -d && sleep 30 && python scripts/init_neo4j.py && streamlit run web/app.py"
```

## Git 듀얼 리모트 운영 (Private + Public)

하나의 로컬 폴더에서 Private/Public 두 GitHub repo를 동시에 관리합니다.

### 리모트 구성

| 리모트 | 용도 | URL |
|--------|------|-----|
| `origin` | Private (전체 히스토리) | `https://github.com/grotyx/medical_kag.git` |
| `public` | Public (깨끗한 히스토리) | `https://github.com/grotyx/research-graphDB.git` |

### 브랜치 구성

| 브랜치 | 용도 |
|--------|------|
| `main` | 일상 개발 브랜치. `origin`(private)에 push |
| `public-release` | public repo 전용 orphan 브랜치. `public` remote에 push |

### 일상 작업 흐름 (Private만)

평소에는 `main` 브랜치에서 작업하고 private repo에만 push합니다.

```bash
# 평소 작업
git add <files>
git commit -m "변경 내용"
git push origin main
```

### Public 업데이트 (필요할 때만)

버전 릴리스, 주요 기능 추가 등 공개할 때만 실행합니다.

```bash
# Step 1: public-release 브랜치로 전환
git checkout public-release

# Step 2: main의 최신 코드 전체를 가져오기
git checkout main -- .

# Step 3: public에 포함하면 안 되는 파일 제거
git rm --cached -r --ignore-unmatch \
  user-claude.md \
  .claude/ \
  data/extracted/ \
  2>/dev/null

# Step 4: public용 .gitignore 적용 (개인 파일 제외 항목 추가)
# .gitignore에 user-claude.md, .claude/ 가 없으면 임시 추가
grep -q "user-claude.md" .gitignore || echo -e "\n# Personal/Claude config\nuser-claude.md\n.claude/" >> .gitignore
git add .gitignore

# Step 5: 커밋 & push
git add -A
git commit -m "Update to vX.Y.Z: 변경 요약"
git push public public-release:main

# Step 6: main 브랜치로 복귀
git checkout main

# Step 7: .gitignore 원복 (orphan에서 수정한 경우)
git checkout -- .gitignore
```

### 주의사항

- **절대로 `main` 브랜치를 `public` remote에 push하지 마세요** — 과거 히스토리(비밀번호 포함)가 노출됩니다
- Public에는 반드시 `public-release` 브랜치만 push
- `data/extracted/` (논문 JSON), `user-claude.md`, `.claude/`는 public에 올리지 않음
- `.env`는 양쪽 모두 `.gitignore`로 제외됨 (안전)

### 빠른 참조 (한 줄 명령)

```bash
# Public 업데이트 전체를 한 번에 실행
git checkout public-release && \
git checkout main -- . && \
git rm --cached -r --ignore-unmatch user-claude.md .claude/ data/extracted/ 2>/dev/null; \
grep -q "user-claude.md" .gitignore || echo -e "\n# Personal/Claude config\nuser-claude.md\n.claude/" >> .gitignore; \
git add -A && \
git commit -m "Update to vX.Y.Z" && \
git push public public-release:main && \
git checkout main && \
git checkout -- .gitignore
```

### 리모트 확인

```bash
git remote -v
# origin  https://github.com/grotyx/medical_kag.git (fetch)
# origin  https://github.com/grotyx/medical_kag.git (push)
# public  https://github.com/grotyx/research-graphDB.git (fetch)
# public  https://github.com/grotyx/research-graphDB.git (push)
```

---

## 관련 문서

| 문서 | 용도 |
|------|------|
| [CHANGELOG.md](CHANGELOG.md) | 버전 히스토리 |
| [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md) | Neo4j 스키마, SNOMED 매핑 |
| [NEO4J_SETUP.md](NEO4J_SETUP.md) | Neo4j 상세 설정 |
| [user_guide.md](user_guide.md) | 사용자 가이드 |
| [developer_guide.md](developer_guide.md) | 개발자 가이드 |
