"""Paper Relationship Graph.

**DEPRECATED**: This module is deprecated as of v5.2.
Use Neo4j-based graph storage (`src/graph/`) instead.

Legacy SQLite-based storage for paper nodes and their relationships.
Supports:
- Paper metadata storage
- Citation relationships
- Support/conflict relationships
- Topic similarity relationships

Migration Path:
- Use `src/graph/spine_schema.py` for node/relationship definitions
- Use `src/graph/neo4j_client.py` for graph operations
- Paper-to-Paper relations now managed in Neo4j (SUPPORTS, CONTRADICTS, etc.)
"""

import warnings

warnings.warn(
    "paper_graph.py is deprecated. Use Neo4j-based graph storage (src/graph/) instead.",
    DeprecationWarning,
    stacklevel=2
)

import json
import sqlite3
import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from pathlib import Path


class RelationType(Enum):
    """논문 관계 유형."""
    CITES = "cites"                    # A가 B를 인용
    CITED_BY = "cited_by"              # A가 B에 의해 인용됨
    SUPPORTS = "supports"              # A가 B의 결과를 지지
    CONTRADICTS = "contradicts"        # A가 B의 결과와 상충
    SIMILAR_TOPIC = "similar_topic"    # A와 B가 유사한 주제
    EXTENDS = "extends"                # A가 B의 연구를 확장
    REPLICATES = "replicates"          # A가 B의 연구를 재현


@dataclass
class PICOSummary:
    """논문 전체 PICO 요약."""
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparison: Optional[str] = None
    outcome: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "PICOSummary":
        return cls(
            population=data.get("population"),
            intervention=data.get("intervention"),
            comparison=data.get("comparison"),
            outcome=data.get("outcome"),
        )


@dataclass
class PaperNode:
    """논문 노드.

    Attributes:
        paper_id: 고유 논문 식별자
        title: 논문 제목
        authors: 저자 목록
        year: 출판 연도
        abstract_summary: LLM 생성 초록 요약
        pico_summary: 논문 전체 PICO 요소
        main_findings: 주요 발견 목록
        evidence_level: 근거 수준 (1a, 1b, 2a, 2b, 3, 4)
        keywords: 키워드 목록
        embedding: 논문 임베딩 벡터 (검색용)
    """
    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    abstract_summary: str = ""
    pico_summary: Optional[PICOSummary] = None
    main_findings: list[str] = field(default_factory=list)
    evidence_level: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    embedding: Optional[list[float]] = None

    # 메타데이터
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class PaperRelation:
    """논문 간 관계.

    Attributes:
        source_id: 소스 논문 ID
        target_id: 타겟 논문 ID
        relation_type: 관계 유형
        confidence: 관계 신뢰도 (0.0-1.0)
        evidence: 관계 근거 설명
        detected_by: 탐지 방법 (citation_extraction, llm_analysis, pico_similarity)
    """
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = 0.0
    evidence: str = ""
    detected_by: str = ""
    created_at: Optional[str] = None


class PaperGraph:
    """SQLite 기반 논문 관계 그래프.

    논문 노드와 관계를 저장하고 쿼리하는 기능을 제공합니다.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize PaperGraph.

        Args:
            db_path: SQLite 데이터베이스 경로. None이면 인메모리 DB 사용.
        """
        self.db_path = db_path or ":memory:"
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """동기 연결 가져오기."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    async def initialize(self) -> None:
        """데이터베이스 초기화."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            conn = self._get_connection()

            # 논문 노드 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors_json TEXT,
                    year INTEGER,
                    abstract_summary TEXT,
                    pico_json TEXT,
                    main_findings_json TEXT,
                    evidence_level TEXT,
                    keywords_json TEXT,
                    embedding_json TEXT,
                    journal TEXT,
                    doi TEXT,
                    pmid TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 관계 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    evidence TEXT,
                    detected_by TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES papers(paper_id),
                    FOREIGN KEY (target_id) REFERENCES papers(paper_id),
                    UNIQUE(source_id, target_id, relation_type)
                )
            """)

            # 인덱스 생성
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relations_source
                ON relations(source_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relations_target
                ON relations(target_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relations_type
                ON relations(relation_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_year
                ON papers(year)
            """)

            conn.commit()
            self._initialized = True

    async def add_paper(self, paper: PaperNode) -> None:
        """논문 노드 추가.

        Args:
            paper: 추가할 논문 노드
        """
        await self.initialize()

        async with self._lock:
            conn = self._get_connection()

            pico_json = None
            if paper.pico_summary:
                pico_json = json.dumps(paper.pico_summary.to_dict())

            conn.execute("""
                INSERT OR REPLACE INTO papers (
                    paper_id, title, authors_json, year, abstract_summary,
                    pico_json, main_findings_json, evidence_level, keywords_json,
                    embedding_json, journal, doi, pmid, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                paper.paper_id,
                paper.title,
                json.dumps(paper.authors) if paper.authors else None,
                paper.year,
                paper.abstract_summary,
                pico_json,
                json.dumps(paper.main_findings) if paper.main_findings else None,
                paper.evidence_level,
                json.dumps(paper.keywords) if paper.keywords else None,
                json.dumps(paper.embedding) if paper.embedding else None,
                paper.journal,
                paper.doi,
                paper.pmid,
            ))
            conn.commit()

    async def get_paper(self, paper_id: str) -> Optional[PaperNode]:
        """논문 노드 조회.

        Args:
            paper_id: 논문 ID

        Returns:
            PaperNode 또는 None
        """
        await self.initialize()

        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_paper(row)

    async def list_papers(
        self,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        evidence_level: Optional[str] = None,
        limit: int = 100
    ) -> list[PaperNode]:
        """논문 목록 조회.

        Args:
            year_min: 최소 출판 연도
            year_max: 최대 출판 연도
            evidence_level: 근거 수준 필터
            limit: 최대 반환 개수

        Returns:
            PaperNode 목록
        """
        await self.initialize()

        query = "SELECT * FROM papers WHERE 1=1"
        params: list = []

        if year_min is not None:
            query += " AND year >= ?"
            params.append(year_min)
        if year_max is not None:
            query += " AND year <= ?"
            params.append(year_max)
        if evidence_level:
            query += " AND evidence_level = ?"
            params.append(evidence_level)

        query += " ORDER BY year DESC LIMIT ?"
        params.append(limit)

        conn = self._get_connection()
        cursor = conn.execute(query, params)

        return [self._row_to_paper(row) for row in cursor.fetchall()]

    async def add_relation(self, relation: PaperRelation) -> None:
        """관계 추가.

        Args:
            relation: 추가할 관계
        """
        await self.initialize()

        async with self._lock:
            conn = self._get_connection()

            conn.execute("""
                INSERT OR REPLACE INTO relations (
                    source_id, target_id, relation_type, confidence,
                    evidence, detected_by
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                relation.source_id,
                relation.target_id,
                relation.relation_type.value,
                relation.confidence,
                relation.evidence,
                relation.detected_by,
            ))
            conn.commit()

    async def get_relations(
        self,
        paper_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both"  # "outgoing", "incoming", "both"
    ) -> list[PaperRelation]:
        """논문의 관계 목록 조회.

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형 필터 (None이면 전체)
            direction: 방향 ("outgoing", "incoming", "both")

        Returns:
            PaperRelation 목록
        """
        await self.initialize()

        conn = self._get_connection()
        relations = []

        # Outgoing relations
        if direction in ("outgoing", "both"):
            query = "SELECT * FROM relations WHERE source_id = ?"
            params: list = [paper_id]
            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type.value)

            cursor = conn.execute(query, params)
            relations.extend([self._row_to_relation(row) for row in cursor.fetchall()])

        # Incoming relations
        if direction in ("incoming", "both"):
            query = "SELECT * FROM relations WHERE target_id = ?"
            params = [paper_id]
            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type.value)

            cursor = conn.execute(query, params)
            relations.extend([self._row_to_relation(row) for row in cursor.fetchall()])

        return relations

    async def find_supporting_papers(
        self,
        paper_id: str,
        min_confidence: float = 0.5
    ) -> list[tuple[PaperNode, float]]:
        """지지하는 논문 찾기.

        Args:
            paper_id: 기준 논문 ID
            min_confidence: 최소 신뢰도

        Returns:
            (PaperNode, confidence) 튜플 목록
        """
        await self.initialize()

        conn = self._get_connection()

        # 이 논문을 지지하는 논문들 (supports 관계의 source)
        cursor = conn.execute("""
            SELECT p.*, r.confidence
            FROM papers p
            JOIN relations r ON p.paper_id = r.source_id
            WHERE r.target_id = ?
              AND r.relation_type = ?
              AND r.confidence >= ?
            ORDER BY r.confidence DESC
        """, (paper_id, RelationType.SUPPORTS.value, min_confidence))

        results = []
        for row in cursor.fetchall():
            paper = self._row_to_paper(row)
            confidence = row["confidence"]
            results.append((paper, confidence))

        return results

    async def find_contradicting_papers(
        self,
        paper_id: str,
        min_confidence: float = 0.5
    ) -> list[tuple[PaperNode, float]]:
        """상충하는 논문 찾기.

        Args:
            paper_id: 기준 논문 ID
            min_confidence: 최소 신뢰도

        Returns:
            (PaperNode, confidence) 튜플 목록
        """
        await self.initialize()

        conn = self._get_connection()

        # 양방향 모두 확인 (A가 B와 상충하면 B도 A와 상충)
        cursor = conn.execute("""
            SELECT p.*, r.confidence
            FROM papers p
            JOIN relations r ON (
                (p.paper_id = r.source_id AND r.target_id = ?)
                OR (p.paper_id = r.target_id AND r.source_id = ?)
            )
            WHERE r.relation_type = ?
              AND r.confidence >= ?
              AND p.paper_id != ?
            ORDER BY r.confidence DESC
        """, (paper_id, paper_id, RelationType.CONTRADICTS.value, min_confidence, paper_id))

        results = []
        seen = set()
        for row in cursor.fetchall():
            pid = row["paper_id"]
            if pid in seen:
                continue
            seen.add(pid)
            paper = self._row_to_paper(row)
            confidence = row["confidence"]
            results.append((paper, confidence))

        return results

    async def find_similar_papers(
        self,
        paper_id: str,
        top_k: int = 5,
        min_confidence: float = 0.3
    ) -> list[tuple[PaperNode, float]]:
        """유사한 논문 찾기.

        Args:
            paper_id: 기준 논문 ID
            top_k: 반환할 최대 개수
            min_confidence: 최소 유사도

        Returns:
            (PaperNode, similarity) 튜플 목록
        """
        await self.initialize()

        conn = self._get_connection()

        cursor = conn.execute("""
            SELECT p.*, r.confidence
            FROM papers p
            JOIN relations r ON (
                (p.paper_id = r.source_id AND r.target_id = ?)
                OR (p.paper_id = r.target_id AND r.source_id = ?)
            )
            WHERE r.relation_type = ?
              AND r.confidence >= ?
              AND p.paper_id != ?
            ORDER BY r.confidence DESC
            LIMIT ?
        """, (
            paper_id, paper_id,
            RelationType.SIMILAR_TOPIC.value,
            min_confidence, paper_id, top_k
        ))

        results = []
        seen = set()
        for row in cursor.fetchall():
            pid = row["paper_id"]
            if pid in seen:
                continue
            seen.add(pid)
            paper = self._row_to_paper(row)
            confidence = row["confidence"]
            results.append((paper, confidence))

        return results

    async def get_citation_network(
        self,
        paper_id: str,
        depth: int = 2
    ) -> dict:
        """인용 네트워크 조회.

        Args:
            paper_id: 기준 논문 ID
            depth: 탐색 깊이

        Returns:
            네트워크 정보 딕셔너리 {
                "center": PaperNode,
                "cites": [(PaperNode, depth), ...],
                "cited_by": [(PaperNode, depth), ...]
            }
        """
        await self.initialize()

        center = await self.get_paper(paper_id)
        if not center:
            return {"center": None, "cites": [], "cited_by": []}

        cites = []
        cited_by = []

        # BFS로 인용 네트워크 탐색
        visited = {paper_id}

        # Outgoing citations (이 논문이 인용한 것들)
        queue = [(paper_id, 0)]
        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue

            relations = await self.get_relations(
                current_id,
                relation_type=RelationType.CITES,
                direction="outgoing"
            )

            for rel in relations:
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    paper = await self.get_paper(rel.target_id)
                    if paper:
                        cites.append((paper, current_depth + 1))
                        queue.append((rel.target_id, current_depth + 1))

        # Incoming citations (이 논문을 인용한 것들)
        visited = {paper_id}
        queue = [(paper_id, 0)]
        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue

            relations = await self.get_relations(
                current_id,
                relation_type=RelationType.CITED_BY,
                direction="outgoing"
            )

            for rel in relations:
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    paper = await self.get_paper(rel.target_id)
                    if paper:
                        cited_by.append((paper, current_depth + 1))
                        queue.append((rel.target_id, current_depth + 1))

        return {
            "center": center,
            "cites": cites,
            "cited_by": cited_by,
        }

    async def get_stats(self) -> dict:
        """그래프 통계 조회."""
        await self.initialize()

        conn = self._get_connection()

        paper_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

        # 관계 유형별 카운트
        relation_types = {}
        cursor = conn.execute("""
            SELECT relation_type, COUNT(*) as cnt
            FROM relations
            GROUP BY relation_type
        """)
        for row in cursor.fetchall():
            relation_types[row["relation_type"]] = row["cnt"]

        return {
            "paper_count": paper_count,
            "relation_count": relation_count,
            "relation_types": relation_types,
        }

    async def close(self) -> None:
        """데이터베이스 연결 종료."""
        if self._connection:
            self._connection.close()
            self._connection = None
            self._initialized = False

    def _row_to_paper(self, row: sqlite3.Row) -> PaperNode:
        """Row를 PaperNode로 변환."""
        pico_summary = None
        if row["pico_json"]:
            pico_data = json.loads(row["pico_json"])
            pico_summary = PICOSummary.from_dict(pico_data)

        return PaperNode(
            paper_id=row["paper_id"],
            title=row["title"],
            authors=json.loads(row["authors_json"]) if row["authors_json"] else [],
            year=row["year"],
            abstract_summary=row["abstract_summary"] or "",
            pico_summary=pico_summary,
            main_findings=json.loads(row["main_findings_json"]) if row["main_findings_json"] else [],
            evidence_level=row["evidence_level"],
            keywords=json.loads(row["keywords_json"]) if row["keywords_json"] else [],
            embedding=json.loads(row["embedding_json"]) if row["embedding_json"] else None,
            journal=row["journal"],
            doi=row["doi"],
            pmid=row["pmid"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_relation(self, row: sqlite3.Row) -> PaperRelation:
        """Row를 PaperRelation으로 변환."""
        return PaperRelation(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=RelationType(row["relation_type"]),
            confidence=row["confidence"],
            evidence=row["evidence"] or "",
            detected_by=row["detected_by"] or "",
            created_at=row["created_at"],
        )
