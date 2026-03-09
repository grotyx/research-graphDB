#!/usr/bin/env python3
"""Neo4j 5.26 Vector Index PoC (Proof of Concept).

Neo4j에서 직접 벡터 검색을 수행하는 PoC 스크립트.
현재 ChromaDB에 저장된 임베딩을 Neo4j로 마이그레이션하고,
그래프 + 벡터 통합 쿼리를 테스트합니다.

Usage:
    python scripts/poc_neo4j_vector.py --check      # 기능 확인
    python scripts/poc_neo4j_vector.py --create     # 벡터 인덱스 생성
    python scripts/poc_neo4j_vector.py --migrate    # 청크 마이그레이션
    python scripts/poc_neo4j_vector.py --test       # 통합 쿼리 테스트
    python scripts/poc_neo4j_vector.py --benchmark  # ChromaDB vs Neo4j 비교
"""

import asyncio
import argparse
import time
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from neo4j import AsyncGraphDatabase


# =============================================================================
# Configuration
# =============================================================================

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# 의료 특화 임베딩 모델 (MedTE)
EMBEDDING_DIM = 768  # MohammadKhodadad/MedTE-cl15-step-8000
EMBEDDING_MODEL = "MohammadKhodadad/MedTE-cl15-step-8000"
VECTOR_INDEX_NAME = "chunk_embedding_index"
PAPER_VECTOR_INDEX = "paper_abstract_index"


@dataclass
class VectorSearchResult:
    """벡터 검색 결과."""
    node_id: str
    content: str
    score: float
    metadata: dict


# =============================================================================
# Neo4j Vector Client
# =============================================================================

class Neo4jVectorClient:
    """Neo4j 5.26 Vector Index 클라이언트."""

    def __init__(self):
        self._driver = None

    async def connect(self):
        """연결."""
        self._driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    async def close(self):
        """연결 종료."""
        if self._driver:
            await self._driver.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def run_query(self, cypher: str, params: dict = None) -> list[dict]:
        """Cypher 쿼리 실행."""
        async with self._driver.session(database=NEO4J_DATABASE) as session:
            result = await session.run(cypher, params or {})
            return [dict(record) async for record in result]

    # -------------------------------------------------------------------------
    # 1. 기능 확인
    # -------------------------------------------------------------------------

    async def check_vector_support(self) -> dict:
        """Neo4j 5.26 벡터 기능 지원 확인."""
        info = {
            "version": "",
            "vector_procedures": [],
            "genai_procedures": [],
            "existing_indexes": []
        }

        # 버전 확인
        result = await self.run_query("CALL dbms.components() YIELD versions RETURN versions[0] as version")
        if result:
            info["version"] = result[0]["version"]

        # 벡터 프로시저 확인
        result = await self.run_query("""
            SHOW PROCEDURES YIELD name
            WHERE name STARTS WITH 'db.index.vector'
            RETURN collect(name) as procedures
        """)
        if result:
            info["vector_procedures"] = result[0]["procedures"]

        # GenAI 프로시저 확인
        result = await self.run_query("""
            SHOW PROCEDURES YIELD name
            WHERE name STARTS WITH 'genai'
            RETURN collect(name) as procedures
        """)
        if result:
            info["genai_procedures"] = result[0]["procedures"]

        # 기존 벡터 인덱스 확인
        result = await self.run_query("""
            SHOW INDEXES YIELD name, type, labelsOrTypes, properties
            WHERE type = 'VECTOR'
            RETURN name, labelsOrTypes, properties
        """)
        info["existing_indexes"] = result

        return info

    # -------------------------------------------------------------------------
    # 2. 벡터 인덱스 생성
    # -------------------------------------------------------------------------

    async def create_chunk_vector_index(self) -> bool:
        """Chunk 노드용 벡터 인덱스 생성."""
        try:
            # Chunk 노드 존재 확인 (없으면 생성 필요)
            await self.run_query(f"""
                CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
                FOR (c:Chunk)
                ON c.embedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_DIM},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            print(f"✅ Created vector index: {VECTOR_INDEX_NAME}")
            return True
        except Exception as e:
            print(f"❌ Failed to create index: {e}")
            return False

    async def create_paper_vector_index(self) -> bool:
        """Paper 노드 abstract용 벡터 인덱스 생성."""
        try:
            await self.run_query(f"""
                CREATE VECTOR INDEX {PAPER_VECTOR_INDEX} IF NOT EXISTS
                FOR (p:Paper)
                ON p.abstract_embedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_DIM},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            print(f"✅ Created vector index: {PAPER_VECTOR_INDEX}")
            return True
        except Exception as e:
            print(f"❌ Failed to create index: {e}")
            return False

    # -------------------------------------------------------------------------
    # 3. 데이터 마이그레이션 (ChromaDB → Neo4j)
    # -------------------------------------------------------------------------

    async def migrate_chunks_from_chromadb(self, limit: int = 100) -> int:
        """ChromaDB에서 청크 마이그레이션.

        ChromaDB의 청크를 Neo4j Chunk 노드로 복사.
        """
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            print("❌ ChromaDB not installed")
            return 0

        # ChromaDB 연결
        chroma_path = Path(__file__).parent.parent / "data" / "chromadb"
        if not chroma_path.exists():
            print(f"❌ ChromaDB path not found: {chroma_path}")
            return 0

        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False)
        )

        migrated = 0

        for tier in ["tier1", "tier2"]:
            try:
                collection = client.get_collection(f"medical_papers_{tier}")
            except Exception:
                print(f"⚠️ Collection medical_papers_{tier} not found")
                continue

            # 청크 가져오기
            results = collection.get(
                include=["embeddings", "documents", "metadatas"],
                limit=limit
            )

            if not results["ids"]:
                continue

            print(f"📦 Migrating {len(results['ids'])} chunks from {tier}...")

            for i, chunk_id in enumerate(results["ids"]):
                content = results["documents"][i] if results["documents"] else ""
                embedding = results["embeddings"][i] if results["embeddings"] else None
                metadata = results["metadatas"][i] if results["metadatas"] else {}

                if not embedding:
                    continue

                # Neo4j에 Chunk 노드 생성
                await self.run_query("""
                    MERGE (c:Chunk {chunk_id: $chunk_id})
                    SET c.content = $content,
                        c.embedding = $embedding,
                        c.tier = $tier,
                        c.document_id = $document_id,
                        c.section = $section,
                        c.evidence_level = $evidence_level,
                        c.is_key_finding = $is_key_finding
                """, {
                    "chunk_id": chunk_id,
                    "content": content[:5000],  # 내용 제한
                    "embedding": embedding,
                    "tier": tier,
                    "document_id": metadata.get("document_id", ""),
                    "section": metadata.get("section", ""),
                    "evidence_level": metadata.get("evidence_level", "5"),
                    "is_key_finding": metadata.get("is_key_finding", False)
                })

                # Paper와 연결
                if metadata.get("document_id"):
                    await self.run_query("""
                        MATCH (c:Chunk {chunk_id: $chunk_id})
                        MATCH (p:Paper {paper_id: $paper_id})
                        MERGE (p)-[:HAS_CHUNK]->(c)
                    """, {
                        "chunk_id": chunk_id,
                        "paper_id": metadata.get("document_id")
                    })

                migrated += 1

        print(f"✅ Migrated {migrated} chunks to Neo4j")
        return migrated

    async def add_paper_embeddings(self) -> int:
        """Paper 노드에 abstract 임베딩 추가."""
        from core.embedding import EmbeddingGenerator

        # MedTE 의료 특화 모델 사용
        embedder = EmbeddingGenerator(model_name=EMBEDDING_MODEL)

        # abstract가 있는 Paper 노드 조회
        papers = await self.run_query("""
            MATCH (p:Paper)
            WHERE p.abstract IS NOT NULL
              AND p.abstract <> ''
              AND p.abstract_embedding IS NULL
            RETURN p.paper_id as paper_id, p.abstract as abstract
            LIMIT 100
        """)

        if not papers:
            print("⚠️ No papers to embed (all already have embeddings or no abstract)")
            return 0

        print(f"📦 Embedding {len(papers)} paper abstracts...")

        for paper in papers:
            embedding = embedder.embed(paper["abstract"])

            await self.run_query("""
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
            """, {
                "paper_id": paper["paper_id"],
                "embedding": embedding
            })

        print(f"✅ Added embeddings to {len(papers)} papers")
        return len(papers)

    # -------------------------------------------------------------------------
    # 4. 벡터 검색
    # -------------------------------------------------------------------------

    async def vector_search_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10
    ) -> list[VectorSearchResult]:
        """청크 벡터 검색."""
        results = await self.run_query("""
            CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
            YIELD node, score
            RETURN node.chunk_id as chunk_id,
                   node.content as content,
                   node.document_id as document_id,
                   node.tier as tier,
                   node.section as section,
                   node.evidence_level as evidence_level,
                   score
            ORDER BY score DESC
        """, {
            "index_name": VECTOR_INDEX_NAME,
            "top_k": top_k,
            "embedding": query_embedding
        })

        return [
            VectorSearchResult(
                node_id=r["chunk_id"],
                content=r["content"],
                score=r["score"],
                metadata={
                    "document_id": r["document_id"],
                    "tier": r["tier"],
                    "section": r["section"],
                    "evidence_level": r["evidence_level"]
                }
            )
            for r in results
        ]

    async def vector_search_papers(
        self,
        query_embedding: list[float],
        top_k: int = 10
    ) -> list[VectorSearchResult]:
        """Paper abstract 벡터 검색."""
        results = await self.run_query("""
            CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
            YIELD node, score
            RETURN node.paper_id as paper_id,
                   node.title as title,
                   node.abstract as abstract,
                   node.year as year,
                   node.evidence_level as evidence_level,
                   node.sub_domain as sub_domain,
                   score
            ORDER BY score DESC
        """, {
            "index_name": PAPER_VECTOR_INDEX,
            "top_k": top_k,
            "embedding": query_embedding
        })

        return [
            VectorSearchResult(
                node_id=r["paper_id"],
                content=r["abstract"] or "",
                score=r["score"],
                metadata={
                    "title": r["title"],
                    "year": r["year"],
                    "evidence_level": r["evidence_level"],
                    "sub_domain": r["sub_domain"]
                }
            )
            for r in results
        ]

    # -------------------------------------------------------------------------
    # 5. 그래프 + 벡터 통합 쿼리 (핵심 기능!)
    # -------------------------------------------------------------------------

    async def hybrid_search(
        self,
        query_embedding: list[float],
        intervention: Optional[str] = None,
        evidence_levels: Optional[list[str]] = None,
        top_k: int = 10
    ) -> list[dict]:
        """그래프 필터링 + 벡터 검색 통합.

        Neo4j 단독 DB의 핵심 장점:
        - 그래프 관계로 필터링 후 벡터 검색
        - 단일 트랜잭션에서 처리
        - ChromaDB + Neo4j 조합보다 효율적
        """
        # 동적 필터 조건 구성
        where_clauses = []
        params = {
            "index_name": PAPER_VECTOR_INDEX,
            "top_k": top_k * 3,  # 필터링 후 top_k 보장을 위해 여유있게
            "embedding": query_embedding
        }

        if intervention:
            where_clauses.append("(p)-[:INVESTIGATES]->(:Intervention {name: $intervention})")
            params["intervention"] = intervention

        if evidence_levels:
            where_clauses.append("p.evidence_level IN $evidence_levels")
            params["evidence_levels"] = evidence_levels

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # 통합 쿼리: 벡터 검색 + 그래프 필터링 + 관계 정보 포함
        cypher = f"""
            CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
            YIELD node as p, score
            {where_clause}

            // 관련 Intervention 조회
            OPTIONAL MATCH (p)-[inv:INVESTIGATES]->(i:Intervention)

            // 관련 Outcome 조회 (AFFECTS 통계 포함)
            OPTIONAL MATCH (i)-[aff:AFFECTS]->(o:Outcome)
            WHERE aff.paper_id = p.paper_id

            RETURN p.paper_id as paper_id,
                   p.title as title,
                   p.year as year,
                   p.evidence_level as evidence_level,
                   p.sub_domain as sub_domain,
                   score,
                   collect(DISTINCT i.name) as interventions,
                   collect(DISTINCT {{
                       outcome: o.name,
                       value: aff.value,
                       p_value: aff.p_value,
                       is_significant: aff.is_significant
                   }}) as outcomes
            ORDER BY score DESC
            LIMIT $final_k
        """
        params["final_k"] = top_k

        results = await self.run_query(cypher, params)
        return results

    async def find_similar_papers_with_evidence(
        self,
        paper_id: str,
        top_k: int = 5
    ) -> list[dict]:
        """특정 논문과 유사한 논문 + 근거 수준 비교.

        그래프 + 벡터의 시너지:
        - 벡터: 내용 유사성
        - 그래프: 근거 수준, 수술법, 결과 비교
        """
        # 먼저 해당 논문의 임베딩 가져오기
        paper_data = await self.run_query("""
            MATCH (p:Paper {paper_id: $paper_id})
            RETURN p.abstract_embedding as embedding,
                   p.title as title,
                   p.evidence_level as evidence_level
        """, {"paper_id": paper_id})

        if not paper_data or not paper_data[0].get("embedding"):
            return []

        embedding = paper_data[0]["embedding"]
        source_level = paper_data[0]["evidence_level"]

        # 유사 논문 검색 + 그래프 정보
        results = await self.run_query("""
            CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
            YIELD node as p, score
            WHERE p.paper_id <> $paper_id

            // 공통 Intervention 찾기
            OPTIONAL MATCH (source:Paper {paper_id: $paper_id})-[:INVESTIGATES]->(common_int:Intervention)<-[:INVESTIGATES]-(p)

            // 결과 비교
            OPTIONAL MATCH (common_int)-[aff1:AFFECTS]->(o:Outcome)
            WHERE aff1.paper_id = $paper_id
            OPTIONAL MATCH (common_int)-[aff2:AFFECTS]->(o)
            WHERE aff2.paper_id = p.paper_id

            RETURN p.paper_id as paper_id,
                   p.title as title,
                   p.year as year,
                   p.evidence_level as evidence_level,
                   score as similarity,
                   collect(DISTINCT common_int.name) as common_interventions,
                   collect(DISTINCT {{
                       outcome: o.name,
                       source_value: aff1.value,
                       target_value: aff2.value,
                       source_significant: aff1.is_significant,
                       target_significant: aff2.is_significant
                   }}) as outcome_comparisons
            ORDER BY score DESC
            LIMIT $top_k
        """, {
            "index_name": PAPER_VECTOR_INDEX,
            "top_k": top_k + 1,  # 자기 자신 제외
            "embedding": embedding,
            "paper_id": paper_id
        })

        # 근거 수준 비교 정보 추가
        for r in results:
            r["evidence_comparison"] = self._compare_evidence_levels(
                source_level, r["evidence_level"]
            )

        return results

    def _compare_evidence_levels(self, source: str, target: str) -> str:
        """근거 수준 비교."""
        level_order = {"1a": 1, "1b": 2, "2a": 3, "2b": 4, "3": 5, "4": 6, "5": 7}
        source_rank = level_order.get(source, 7)
        target_rank = level_order.get(target, 7)

        if target_rank < source_rank:
            return "higher_evidence"
        elif target_rank > source_rank:
            return "lower_evidence"
        else:
            return "same_evidence"


# =============================================================================
# Benchmark: ChromaDB vs Neo4j Vector
# =============================================================================

async def benchmark_comparison(client: Neo4jVectorClient, iterations: int = 10):
    """ChromaDB vs Neo4j Vector 성능 비교."""
    from core.embedding import EmbeddingGenerator

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        print("❌ ChromaDB not installed")
        return

    # MedTE 의료 특화 모델 사용
    embedder = EmbeddingGenerator(model_name=EMBEDDING_MODEL)

    # 테스트 쿼리
    test_queries = [
        "lumbar stenosis decompression outcomes",
        "TLIF fusion rates complications",
        "UBE endoscopic surgery learning curve",
        "cervical myelopathy surgical treatment",
        "spine surgery patient satisfaction"
    ]

    # ChromaDB 연결
    chroma_path = Path(__file__).parent.parent / "data" / "chromadb"
    chroma_client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False)
    )

    try:
        collection = chroma_client.get_collection("medical_papers_tier1")
    except Exception as e:
        print(f"⚠️ ChromaDB collection not found: {e}")
        return

    print("\n" + "=" * 60)
    print("📊 BENCHMARK: ChromaDB vs Neo4j Vector Index")
    print("=" * 60)

    chromadb_times = []
    neo4j_times = []

    for query in test_queries:
        embedding = embedder.embed(query)

        # ChromaDB 검색
        start = time.perf_counter()
        for _ in range(iterations):
            collection.query(
                query_embeddings=[embedding],
                n_results=10
            )
        chromadb_time = (time.perf_counter() - start) / iterations
        chromadb_times.append(chromadb_time)

        # Neo4j Vector 검색
        start = time.perf_counter()
        for _ in range(iterations):
            await client.vector_search_chunks(embedding, top_k=10)
        neo4j_time = (time.perf_counter() - start) / iterations
        neo4j_times.append(neo4j_time)

        print(f"\n🔍 Query: {query[:40]}...")
        print(f"   ChromaDB: {chromadb_time*1000:.2f}ms")
        print(f"   Neo4j:    {neo4j_time*1000:.2f}ms")

    print("\n" + "-" * 60)
    print("📈 SUMMARY")
    print("-" * 60)
    avg_chromadb = sum(chromadb_times) / len(chromadb_times)
    avg_neo4j = sum(neo4j_times) / len(neo4j_times)
    print(f"Average ChromaDB: {avg_chromadb*1000:.2f}ms")
    print(f"Average Neo4j:    {avg_neo4j*1000:.2f}ms")

    if avg_neo4j < avg_chromadb:
        speedup = avg_chromadb / avg_neo4j
        print(f"🚀 Neo4j is {speedup:.1f}x faster!")
    else:
        slowdown = avg_neo4j / avg_chromadb
        print(f"⚠️ Neo4j is {slowdown:.1f}x slower (but offers graph integration)")

    # 통합 쿼리 테스트
    print("\n" + "-" * 60)
    print("🔗 HYBRID QUERY TEST (Graph + Vector)")
    print("-" * 60)

    embedding = embedder.embed("lumbar fusion outcomes")

    # 순수 벡터
    start = time.perf_counter()
    pure_results = await client.vector_search_papers(embedding, top_k=10)
    pure_time = time.perf_counter() - start

    # 그래프+벡터 통합
    start = time.perf_counter()
    hybrid_results = await client.hybrid_search(
        embedding,
        intervention="TLIF",
        evidence_levels=["1a", "1b", "2a"],
        top_k=10
    )
    hybrid_time = time.perf_counter() - start

    print(f"Pure Vector Search: {pure_time*1000:.2f}ms ({len(pure_results)} results)")
    print(f"Hybrid (Graph+Vector): {hybrid_time*1000:.2f}ms ({len(hybrid_results)} results)")
    print("\n💡 Hybrid 쿼리는 그래프 필터링 + 벡터 검색을 단일 트랜잭션에서 수행")


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Neo4j 5.26 Vector Index PoC")
    parser.add_argument("--check", action="store_true", help="Check vector support")
    parser.add_argument("--create", action="store_true", help="Create vector indexes")
    parser.add_argument("--migrate", action="store_true", help="Migrate chunks from ChromaDB")
    parser.add_argument("--embed-papers", action="store_true", help="Add embeddings to Paper nodes")
    parser.add_argument("--test", action="store_true", help="Test vector search")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark ChromaDB vs Neo4j")
    parser.add_argument("--all", action="store_true", help="Run all steps")

    args = parser.parse_args()

    async with Neo4jVectorClient() as client:

        # 1. 기능 확인
        if args.check or args.all:
            print("\n" + "=" * 60)
            print("🔍 CHECKING NEO4J VECTOR SUPPORT")
            print("=" * 60)
            info = await client.check_vector_support()
            print(f"Version: {info['version']}")
            print(f"Vector Procedures: {info['vector_procedures']}")
            print(f"GenAI Procedures: {info['genai_procedures']}")
            print(f"Existing Vector Indexes: {info['existing_indexes']}")

        # 2. 인덱스 생성
        if args.create or args.all:
            print("\n" + "=" * 60)
            print("📦 CREATING VECTOR INDEXES")
            print("=" * 60)
            await client.create_chunk_vector_index()
            await client.create_paper_vector_index()

        # 3. 데이터 마이그레이션
        if args.migrate or args.all:
            print("\n" + "=" * 60)
            print("📦 MIGRATING CHUNKS FROM CHROMADB")
            print("=" * 60)
            await client.migrate_chunks_from_chromadb(limit=500)

        # 4. Paper 임베딩 추가
        if args.embed_papers or args.all:
            print("\n" + "=" * 60)
            print("📦 ADDING PAPER EMBEDDINGS")
            print("=" * 60)
            await client.add_paper_embeddings()

        # 5. 테스트
        if args.test or args.all:
            print("\n" + "=" * 60)
            print("🧪 TESTING VECTOR SEARCH")
            print("=" * 60)

            from core.embedding import EmbeddingGenerator
            # MedTE 의료 특화 모델 사용
            embedder = EmbeddingGenerator(model_name=EMBEDDING_MODEL)

            query = "lumbar stenosis surgical treatment outcomes"
            embedding = embedder.embed(query)

            print(f"\n🔍 Query: {query}")

            # Paper 검색
            results = await client.vector_search_papers(embedding, top_k=5)
            print(f"\n📄 Paper Search Results ({len(results)}):")
            for r in results:
                print(f"  - [{r.score:.3f}] {r.metadata.get('title', r.node_id)[:60]}...")

            # 하이브리드 검색
            hybrid_results = await client.hybrid_search(
                embedding,
                evidence_levels=["1a", "1b", "2a", "2b"],
                top_k=5
            )
            print(f"\n🔗 Hybrid Search Results ({len(hybrid_results)}):")
            for r in hybrid_results:
                print(f"  - [{r['score']:.3f}] {r['title'][:50]}... | L{r['evidence_level']} | {r['interventions']}")

        # 6. 벤치마크
        if args.benchmark or args.all:
            await benchmark_comparison(client)

    print("\n✅ PoC completed!")


if __name__ == "__main__":
    asyncio.run(main())
