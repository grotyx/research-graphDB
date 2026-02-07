# Medical KAG Web UI Screenshots

## 스크린샷 캡처 방법

스크린샷을 캡처하려면 다음 단계를 따르세요:

### 1. 필수 도구 설치

```bash
pip install playwright
playwright install chromium
```

### 2. Streamlit 앱 실행

```bash
# 터미널 1
cd /Users/sangminpark/Desktop/rag_research
streamlit run web/app.py
```

### 3. 스크린샷 캡처 스크립트 실행

```bash
# 터미널 2
python scripts/capture_screenshots.py
```

## 캡처할 페이지 목록

| 파일명 | 페이지 | 설명 |
|--------|--------|------|
| `01_home.png` | Home | 메인 대시보드 |
| `02_documents.png` | Documents | PDF 문서 관리 |
| `03_search.png` | Search | 의학 문헌 검색 |
| `04_knowledge_graph.png` | Knowledge Graph | 논문 관계 그래프 |
| `05_draft_assistant.png` | Draft Assistant | 초안 작성 도우미 |
| `06_settings.png` | Settings | 시스템 설정 |

## 페이지 미리보기

### Home - 메인 대시보드

시스템 현황과 빠른 접근을 제공합니다.

**주요 기능:**
- 시스템 상태 표시 (문서 수, 청크 수)
- 빠른 검색 입력
- 최근 활동 표시

### Documents - PDF 문서 관리

PDF 논문을 업로드하고 관리합니다.

**주요 기능:**
- 드래그 앤 드롭 PDF 업로드
- 메타데이터 자동 추출
- 문서 목록 및 상세 정보

### Search - 의학 문헌 검색

저장된 논문에서 관련 내용을 검색합니다.

**주요 기능:**
- 자연어 질의 검색
- 고급 필터 (연도, 근거 수준, 섹션)
- Multi-factor 랭킹 결과

### Knowledge Graph - 논문 관계 그래프

논문 간 관계를 시각화합니다.

**주요 기능:**
- 주제 클러스터 표시
- 논문 관계 (지지, 상충, 인용)
- 상충 탐지 결과

### Draft Assistant - 초안 작성 도우미

검색 결과를 바탕으로 논문 초안을 생성합니다.

**주요 기능:**
- 주제 기반 초안 생성
- 섹션별 생성 (Introduction, Methods 등)
- 자동 인용 삽입

### Settings - 시스템 설정

시스템 상태 확인 및 설정을 관리합니다.

**주요 기능:**
- 컴포넌트 상태 표시
- 데이터베이스 통계
- 캐시 관리

## 스크린샷 업데이트 주기

- 주요 UI 변경 시 업데이트
- 새 기능 추가 시 업데이트
- 릴리스 전 최종 업데이트

## 스크린샷 사양

- 해상도: 1920x1080
- 배율: 2x (Retina)
- 형식: PNG
- 전체 페이지 캡처
