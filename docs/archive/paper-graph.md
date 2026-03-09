# Paper Graph Specification

> ⚠️ **DEPRECATED (v5.2)**: 이 문서는 더 이상 사용되지 않는 SQLite 기반 `paper_graph.py` 모듈에 대한 스펙입니다.
>
> **v5.2 변경사항**: SQLite `paper_graph.db`가 제거되고, 모든 Paper-to-Paper 관계는 **Neo4j**에서 관리됩니다.
>
> **새로운 구현 참조**:
> - [Graph Module API](../api/graph_module.md) - Neo4j 기반 그래프 API
> - [SQLITE_REMOVAL_SUMMARY.md](../SQLITE_REMOVAL_SUMMARY.md) - 마이그레이션 가이드
> - `src/graph/neo4j_client.py` - Paper 관계 조회 메서드
> - `src/graph/relationship_builder.py` - Paper → Graph 구축

---

## Overview (Legacy)

~~SQLite 기반 논문 관계 그래프로, 논문 간의 인용, 상충/지지, 주제 유사성 관계를 저장하고 쿼리합니다.~~

**이 모듈은 v5.2에서 deprecated 되었습니다. Neo4j 기반 구현을 사용하세요.**

### 목적
- 논문 수준 메타데이터 저장 (요약, PICO, 주요 발견)
- 논문 간 관계 저장 및 쿼리
- 인용 네트워크 탐색
- 상충/지지 관계 조회
- 주제별 논문 클러스터링

### 입출력 요약
- **입력**: 논문 메타데이터, 관계 정보
- **출력**: 논문 목록, 관계 목록, 네트워크 구조

---

## Data Structures

### PaperNode

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class PaperNode:
    """논문 노드."""
    paper_id: str                      # 고유 ID (파일명 기반)
    title: str
    authors: List[str]
    year: int
    abstract_summary: str              # LLM 생성 요약 (2-3문장)
    pico_summary: Optional[PICOElements] = None  # 논문 전체 PICO
    main_findings: List[str] = field(default_factory=list)  # 주요 발견 (3-5개)
    evidence_level: str = "unknown"    # 1a, 1b, 2a, 2b, 3, 4, unknown
    keywords: List[str] = field(default_factory=list)
    embedding: List[float] = field(default_factory=list)  # 논문 임베딩

    # 메타데이터
    source_file: str = ""              # 원본 PDF 경로
    chunk_count: int = 0               # 청크 수
    created_at: datetime = None
    updated_at: datetime = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract_summary": self.abstract_summary,
            "pico_summary": self.pico_summary.to_dict() if self.pico_summary else None,
            "main_findings": self.main_findings,
            "evidence_level": self.evidence_level,
            "keywords": self.keywords,
            "chunk_count": self.chunk_count
        }
```

### PaperRelation

```python
@dataclass
class PaperRelation:
    """논문 간 관계."""
    source_id: str                     # 출발 논문 ID
    target_id: str                     # 도착 논문 ID
    relation_type: str                 # 관계 유형
    confidence: float                  # 신뢰도 (0.0 ~ 1.0)
    evidence: str                      # 관계 근거 설명
    detected_by: str                   # 감지 방법

    # 메타데이터
    created_at: datetime = None

    # 관계 유형
    RELATION_TYPES = {
        "cites": "인용 관계",
        "supports": "지지 관계 (유사한 결과)",
        "contradicts": "상충 관계 (다른 결과)",
        "similar_topic": "유사 주제",
        "extends": "확장 연구",
        "replicates": "재현 연구"
    }

    # 감지 방법
    DETECTION_METHODS = {
        "citation_extraction": "PDF에서 인용 추출",
        "llm_analysis": "LLM 관계 분석",
        "pico_similarity": "PICO 유사도",
        "embedding_similarity": "임베딩 유사도",
        "manual": "수동 입력"
    }
```

---

## Interface

### PaperGraph

```python
class PaperGraph:
    """SQLite 기반 논문 관계 그래프."""

    def __init__(self, db_path: str = "data/paper_graph.db"):
        """초기화.

        Args:
            db_path: SQLite DB 파일 경로
        """

    async def initialize(self) -> None:
        """DB 스키마 초기화."""

    # ==================== 노드 관리 ====================

    async def add_paper(self, paper: PaperNode) -> None:
        """논문 추가.

        Args:
            paper: 추가할 논문 노드

        Raises:
            DuplicateError: 이미 존재하는 paper_id
        """

    async def get_paper(self, paper_id: str) -> Optional[PaperNode]:
        """논문 조회.

        Args:
            paper_id: 논문 ID

        Returns:
            PaperNode 또는 None
        """

    async def update_paper(self, paper: PaperNode) -> None:
        """논문 업데이트.

        Args:
            paper: 업데이트할 논문 (paper_id로 식별)
        """

    async def delete_paper(self, paper_id: str) -> None:
        """논문 삭제 (관련 관계도 삭제).

        Args:
            paper_id: 삭제할 논문 ID
        """

    async def list_papers(
        self,
        year_from: int = None,
        year_to: int = None,
        evidence_level: str = None,
        keyword: str = None,
        limit: int = 100
    ) -> List[PaperNode]:
        """논문 목록 조회.

        Args:
            year_from: 시작 연도
            year_to: 종료 연도
            evidence_level: 근거 수준 필터
            keyword: 키워드 필터
            limit: 최대 반환 수

        Returns:
            PaperNode 목록
        """

    async def search_papers(
        self,
        query: str,
        top_k: int = 10
    ) -> List[tuple[PaperNode, float]]:
        """논문 검색 (키워드 + 임베딩).

        Returns:
            (PaperNode, relevance_score) 튜플 목록
        """

    # ==================== 관계 관리 ====================

    async def add_relation(self, relation: PaperRelation) -> None:
        """관계 추가.

        Args:
            relation: 추가할 관계
        """

    async def get_relations(
        self,
        paper_id: str,
        relation_type: str = None,
        direction: str = "both"  # "outgoing", "incoming", "both"
    ) -> List[PaperRelation]:
        """논문의 관계 조회.

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형 필터
            direction: 관계 방향

        Returns:
            PaperRelation 목록
        """

    async def delete_relations(
        self,
        paper_id: str,
        relation_type: str = None
    ) -> int:
        """논문의 관계 삭제.

        Returns:
            삭제된 관계 수
        """

    async def relation_exists(
        self,
        source_id: str,
        target_id: str,
        relation_type: str = None
    ) -> bool:
        """관계 존재 여부 확인."""

    # ==================== 분석 쿼리 ====================

    async def find_supporting_papers(
        self,
        paper_id: str,
        min_confidence: float = 0.5
    ) -> List[tuple[PaperNode, float]]:
        """지지 논문 찾기.

        Returns:
            (PaperNode, confidence) 튜플 목록
        """

    async def find_contradicting_papers(
        self,
        paper_id: str,
        min_confidence: float = 0.5
    ) -> List[tuple[PaperNode, float]]:
        """상충 논문 찾기."""

    async def find_similar_papers(
        self,
        paper_id: str,
        top_k: int = 5,
        method: str = "embedding"  # "embedding", "pico", "keyword"
    ) -> List[tuple[PaperNode, float]]:
        """유사 논문 찾기."""

    async def get_citation_network(
        self,
        paper_id: str,
        depth: int = 2,
        direction: str = "both"
    ) -> dict:
        """인용 네트워크 조회.

        Returns:
            {
                "center": PaperNode,
                "nodes": [PaperNode, ...],
                "edges": [PaperRelation, ...],
                "depth_map": {paper_id: depth, ...}
            }
        """

    async def get_topic_clusters(
        self,
        method: str = "keyword"  # "keyword", "pico", "embedding"
    ) -> dict[str, List[str]]:
        """주제별 논문 클러스터.

        Returns:
            {topic_name: [paper_id, ...], ...}
        """

    async def find_conflicts(
        self,
        min_confidence: float = 0.7
    ) -> List[tuple[PaperNode, PaperNode, PaperRelation]]:
        """모든 상충 관계 찾기.

        Returns:
            (paper_a, paper_b, relation) 튜플 목록
        """

    # ==================== 통계 ====================

    async def get_stats(self) -> dict:
        """그래프 통계.

        Returns:
            {
                "total_papers": int,
                "total_relations": int,
                "relations_by_type": {type: count, ...},
                "papers_by_year": {year: count, ...},
                "papers_by_evidence": {level: count, ...}
            }
        """
```

---

## SQLite Schema

```sql
-- 논문 테이블
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,  -- JSON array
    year INTEGER NOT NULL,
    abstract_summary TEXT,
    pico_summary TEXT,      -- JSON object
    main_findings TEXT,     -- JSON array
    evidence_level TEXT DEFAULT 'unknown',
    keywords TEXT,          -- JSON array
    embedding BLOB,         -- numpy array serialized
    source_file TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_evidence ON papers(evidence_level);

-- 관계 테이블
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence TEXT,
    detected_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id, relation_type)
);

CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_relations_type ON relations(relation_type);

-- 주제 클러스터 테이블 (캐시용)
CREATE TABLE IF NOT EXISTS topic_clusters (
    cluster_id TEXT PRIMARY KEY,
    topic_name TEXT NOT NULL,
    paper_ids TEXT NOT NULL,  -- JSON array
    method TEXT NOT NULL,     -- keyword, pico, embedding
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FTS (Full-Text Search) for papers
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    paper_id,
    title,
    abstract_summary,
    keywords,
    content='papers',
    content_rowid='rowid'
);

-- Triggers for FTS sync
CREATE TRIGGER papers_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(paper_id, title, abstract_summary, keywords)
    VALUES (new.paper_id, new.title, new.abstract_summary, new.keywords);
END;

CREATE TRIGGER papers_ad AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, paper_id, title, abstract_summary, keywords)
    VALUES ('delete', old.paper_id, old.title, old.abstract_summary, old.keywords);
END;

CREATE TRIGGER papers_au AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, paper_id, title, abstract_summary, keywords)
    VALUES ('delete', old.paper_id, old.title, old.abstract_summary, old.keywords);
    INSERT INTO papers_fts(paper_id, title, abstract_summary, keywords)
    VALUES (new.paper_id, new.title, new.abstract_summary, new.keywords);
END;
```

---

## Implementation Notes

### 임베딩 저장/로드

```python
import numpy as np

def _serialize_embedding(self, embedding: List[float]) -> bytes:
    """임베딩을 바이트로 직렬화."""
    return np.array(embedding, dtype=np.float32).tobytes()

def _deserialize_embedding(self, data: bytes) -> List[float]:
    """바이트에서 임베딩 복원."""
    return np.frombuffer(data, dtype=np.float32).tolist()
```

### 인용 네트워크 BFS 탐색

```python
async def get_citation_network(
    self,
    paper_id: str,
    depth: int = 2,
    direction: str = "both"
) -> dict:
    """BFS로 인용 네트워크 탐색."""
    from collections import deque

    center = await self.get_paper(paper_id)
    if not center:
        return {"center": None, "nodes": [], "edges": [], "depth_map": {}}

    visited = {paper_id: 0}
    nodes = [center]
    edges = []
    queue = deque([(paper_id, 0)])

    while queue:
        current_id, current_depth = queue.popleft()

        if current_depth >= depth:
            continue

        # 관계 조회
        relations = await self.get_relations(
            current_id,
            relation_type="cites",
            direction=direction
        )

        for rel in relations:
            # 다음 노드 결정
            next_id = rel.target_id if rel.source_id == current_id else rel.source_id

            edges.append(rel)

            if next_id not in visited:
                visited[next_id] = current_depth + 1
                next_paper = await self.get_paper(next_id)
                if next_paper:
                    nodes.append(next_paper)
                    queue.append((next_id, current_depth + 1))

    return {
        "center": center,
        "nodes": nodes,
        "edges": edges,
        "depth_map": visited
    }
```

### PICO 유사도 계산

```python
def _calculate_pico_similarity(
    self,
    pico_a: PICOElements,
    pico_b: PICOElements
) -> float:
    """PICO 유사도 계산 (0.0 ~ 1.0)."""
    if not pico_a or not pico_b:
        return 0.0

    score = 0.0
    count = 0

    for field in ["population", "intervention", "comparison", "outcome"]:
        val_a = getattr(pico_a, field)
        val_b = getattr(pico_b, field)

        if val_a and val_b:
            # 간단한 텍스트 유사도 (Jaccard)
            words_a = set(val_a.lower().split())
            words_b = set(val_b.lower().split())
            if words_a or words_b:
                jaccard = len(words_a & words_b) / len(words_a | words_b)
                score += jaccard
                count += 1

    return score / count if count > 0 else 0.0
```

---

## Test Cases

### 단위 테스트

```python
import pytest

class TestPaperGraph:
    @pytest.fixture
    async def graph(self, tmp_path):
        db_path = tmp_path / "test_graph.db"
        graph = PaperGraph(str(db_path))
        await graph.initialize()
        yield graph

    @pytest.fixture
    def sample_paper(self):
        return PaperNode(
            paper_id="paper001",
            title="Test Paper",
            authors=["Smith, J.", "Kim, Y."],
            year=2023,
            abstract_summary="This is a test paper.",
            evidence_level="1b",
            keywords=["spine", "surgery"]
        )

    @pytest.mark.asyncio
    async def test_add_and_get_paper(self, graph, sample_paper):
        """논문 추가 및 조회."""
        await graph.add_paper(sample_paper)
        retrieved = await graph.get_paper("paper001")

        assert retrieved is not None
        assert retrieved.title == "Test Paper"
        assert retrieved.year == 2023

    @pytest.mark.asyncio
    async def test_add_relation(self, graph):
        """관계 추가."""
        # 두 논문 추가
        paper1 = PaperNode("p1", "Paper 1", ["A"], 2020, "Summary 1")
        paper2 = PaperNode("p2", "Paper 2", ["B"], 2021, "Summary 2")
        await graph.add_paper(paper1)
        await graph.add_paper(paper2)

        # 관계 추가
        relation = PaperRelation(
            source_id="p2",
            target_id="p1",
            relation_type="cites",
            confidence=1.0,
            evidence="Reference [1]",
            detected_by="citation_extraction"
        )
        await graph.add_relation(relation)

        # 관계 조회
        relations = await graph.get_relations("p2", relation_type="cites")
        assert len(relations) == 1
        assert relations[0].target_id == "p1"

    @pytest.mark.asyncio
    async def test_find_supporting_papers(self, graph):
        """지지 논문 찾기."""
        # 세 논문 추가
        for i in range(3):
            paper = PaperNode(f"p{i}", f"Paper {i}", ["A"], 2020+i, f"Summary {i}")
            await graph.add_paper(paper)

        # 지지 관계 추가
        await graph.add_relation(PaperRelation(
            "p1", "p0", "supports", 0.8, "Similar findings", "llm_analysis"
        ))
        await graph.add_relation(PaperRelation(
            "p2", "p0", "supports", 0.9, "Confirms results", "llm_analysis"
        ))

        # 지지 논문 찾기
        supporting = await graph.find_supporting_papers("p0")

        assert len(supporting) == 2
        # 신뢰도 순 정렬 확인
        assert supporting[0][1] >= supporting[1][1]

    @pytest.mark.asyncio
    async def test_citation_network(self, graph):
        """인용 네트워크 탐색."""
        # 체인 형태의 인용: p0 <- p1 <- p2
        for i in range(3):
            await graph.add_paper(
                PaperNode(f"p{i}", f"Paper {i}", ["A"], 2020+i, f"Summary {i}")
            )

        await graph.add_relation(PaperRelation(
            "p1", "p0", "cites", 1.0, "Ref", "citation_extraction"
        ))
        await graph.add_relation(PaperRelation(
            "p2", "p1", "cites", 1.0, "Ref", "citation_extraction"
        ))

        # depth=2로 조회
        network = await graph.get_citation_network("p0", depth=2)

        assert len(network["nodes"]) == 3
        assert network["depth_map"]["p0"] == 0
        assert network["depth_map"]["p1"] == 1
        assert network["depth_map"]["p2"] == 2

    @pytest.mark.asyncio
    async def test_delete_paper_cascades(self, graph):
        """논문 삭제시 관계도 삭제."""
        # 논문과 관계 추가
        await graph.add_paper(PaperNode("p1", "Paper 1", ["A"], 2020, "S1"))
        await graph.add_paper(PaperNode("p2", "Paper 2", ["B"], 2021, "S2"))
        await graph.add_relation(PaperRelation(
            "p2", "p1", "cites", 1.0, "Ref", "citation_extraction"
        ))

        # p1 삭제
        await graph.delete_paper("p1")

        # 관계도 삭제됨 확인
        relations = await graph.get_relations("p2")
        assert len(relations) == 0

    @pytest.mark.asyncio
    async def test_search_papers(self, graph):
        """논문 검색."""
        await graph.add_paper(PaperNode(
            "p1", "Spine Surgery Outcomes",
            ["A"], 2020, "Study about spine surgery",
            keywords=["spine", "surgery", "outcomes"]
        ))

        results = await graph.search_papers("spine surgery")
        assert len(results) >= 1
        assert results[0][0].paper_id == "p1"

    @pytest.mark.asyncio
    async def test_get_stats(self, graph):
        """통계 조회."""
        # 데이터 추가
        for i in range(5):
            await graph.add_paper(
                PaperNode(f"p{i}", f"Paper {i}", ["A"], 2020+i, f"S{i}")
            )

        stats = await graph.get_stats()

        assert stats["total_papers"] == 5
        assert stats["papers_by_year"][2020] == 1
```

---

## Dependencies

- `aiosqlite>=0.19.0`
- `numpy` (임베딩 직렬화)
- `src/builder/llm_metadata_extractor.py` - PICOElements

---

## Configuration

```yaml
# config.yaml
paper_graph:
  db_path: "data/paper_graph.db"

  # 유사도 임계값
  similarity:
    pico_threshold: 0.5      # PICO 유사도 임계값
    embedding_threshold: 0.7  # 임베딩 유사도 임계값

  # 인용 네트워크
  citation_network:
    max_depth: 3             # 최대 탐색 깊이
    max_nodes: 100           # 최대 노드 수

  # 클러스터링
  clustering:
    method: "keyword"        # keyword, pico, embedding
    min_cluster_size: 2
```
