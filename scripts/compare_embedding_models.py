#!/usr/bin/env python3
"""임베딩 모델 비교 스크립트.

PubMed 검색 결과를 기반으로 MedTE vs OpenAI 임베딩 모델을 비교합니다.

Usage:
    python scripts/compare_embedding_models.py

Requirements:
    - ANTHROPIC_API_KEY (for LLM processing)
    - OPENAI_API_KEY (for OpenAI embeddings)
    - NCBI_EMAIL (optional, for PubMed)
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EmbeddingResult:
    """임베딩 결과."""
    chunk_id: str
    content: str
    medte_embedding: list[float] = field(default_factory=list)
    openai_embedding: list[float] = field(default_factory=list)
    section: str = ""
    is_key_finding: bool = False


@dataclass
class PaperData:
    """논문 데이터."""
    pmid: str
    title: str
    abstract: str
    year: int
    journal: str
    authors: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)
    embeddings: list[EmbeddingResult] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """비교 결과."""
    query: str
    medte_results: list[tuple[str, float]]  # (chunk_id, similarity)
    openai_results: list[tuple[str, float]]
    overlap_at_k: dict[int, float] = field(default_factory=dict)  # k: overlap ratio


# =============================================================================
# Embedding Generators
# =============================================================================

class MedTEEmbedding:
    """MedTE 임베딩 생성기 (768차원)."""

    MODEL_NAME = "MohammadKhodadad/MedTE-cl15-step-8000"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        print(f"Loading MedTE model: {self.MODEL_NAME}")
        self.model = SentenceTransformer(self.MODEL_NAME)
        self.model.eval()
        print(f"MedTE loaded: {self.model.get_sentence_embedding_dimension()} dimensions")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트를 임베딩."""
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


class OpenAIEmbedding:
    """OpenAI 임베딩 생성기 (text-embedding-3-large: 3072차원)."""

    MODEL_NAME = "text-embedding-3-large"

    def __init__(self):
        import openai
        self.client = openai.OpenAI()
        print(f"OpenAI embedding model: {self.MODEL_NAME}")

    def embed(self, texts: list[str], batch_size: int = 20) -> list[list[float]]:
        """텍스트를 임베딩."""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            print(f"  OpenAI embedding batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")

            response = self.client.embeddings.create(
                input=batch,
                model=self.MODEL_NAME
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @property
    def dimension(self) -> int:
        return 3072


# =============================================================================
# PubMed Search
# =============================================================================

async def search_pubmed(
    query: str,
    year: int,
    max_results: int = 20
) -> list[PaperData]:
    """PubMed에서 논문 검색."""
    from external.pubmed_client import PubMedClient

    email = os.getenv("NCBI_EMAIL")
    api_key = os.getenv("NCBI_API_KEY")

    client = PubMedClient(email=email, api_key=api_key)

    # 쿼리 구성 (연도 필터 포함)
    full_query = f'{query} AND {year}[PDAT]'
    print(f"\nSearching PubMed: {full_query}")

    # PMID 검색
    pmids = client.search(full_query, max_results=max_results)
    print(f"Found {len(pmids)} papers")

    if not pmids:
        return []

    # 상세 정보 가져오기
    papers = []
    for i, pmid in enumerate(pmids):
        try:
            print(f"  Fetching [{i+1}/{len(pmids)}] PMID: {pmid}")
            details = client.fetch_paper_details(pmid)

            paper = PaperData(
                pmid=details.pmid,
                title=details.title,
                abstract=details.abstract,
                year=details.year,
                journal=details.journal,
                authors=details.authors,
                mesh_terms=details.mesh_terms
            )
            papers.append(paper)

            # Rate limiting
            await asyncio.sleep(0.35)

        except Exception as e:
            print(f"  Error fetching {pmid}: {e}")
            continue

    return papers


# =============================================================================
# Text Processing (Simple Chunking)
# =============================================================================

def create_chunks_from_paper(paper: PaperData) -> list[dict]:
    """논문에서 청크 생성 (단순 방식).

    LLM 없이 구조화된 초록에서 직접 청크를 생성합니다.
    """
    chunks = []

    # 전체 초록을 하나의 청크로
    if paper.abstract:
        chunks.append({
            "chunk_id": f"pubmed_{paper.pmid}_abstract_full",
            "content": paper.abstract,
            "section": "abstract",
            "is_key_finding": True,
        })

    # 구조화된 초록 파싱 시도
    import re
    section_patterns = [
        (r"(?i)BACKGROUND[:\s]*", "background"),
        (r"(?i)OBJECTIVE[S]?[:\s]*", "objective"),
        (r"(?i)METHOD[S]?[:\s]*", "methods"),
        (r"(?i)RESULT[S]?[:\s]*", "results"),
        (r"(?i)CONCLUSION[S]?[:\s]*", "conclusions"),
    ]

    # 섹션 위치 찾기
    found_sections = []
    for pattern, section_name in section_patterns:
        for match in re.finditer(pattern, paper.abstract):
            found_sections.append((match.start(), match.end(), section_name))

    found_sections.sort(key=lambda x: x[0])

    # 섹션별 청크 생성
    if len(found_sections) >= 2:
        for i, (start, end, section_name) in enumerate(found_sections):
            if i + 1 < len(found_sections):
                next_start = found_sections[i + 1][0]
                content = paper.abstract[end:next_start].strip()
            else:
                content = paper.abstract[end:].strip()

            if content and len(content) > 30:
                chunks.append({
                    "chunk_id": f"pubmed_{paper.pmid}_{section_name}",
                    "content": content,
                    "section": section_name,
                    "is_key_finding": section_name in ["results", "conclusions"],
                })

    return chunks


# =============================================================================
# Similarity Calculation
# =============================================================================

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """코사인 유사도 계산."""
    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def search_similar(
    query_embedding: list[float],
    embeddings: list[EmbeddingResult],
    embedding_type: str,  # "medte" or "openai"
    top_k: int = 10
) -> list[tuple[str, float]]:
    """유사한 청크 검색."""
    results = []

    for emb_result in embeddings:
        if embedding_type == "medte":
            vec = emb_result.medte_embedding
        else:
            vec = emb_result.openai_embedding

        if not vec:
            continue

        similarity = cosine_similarity(query_embedding, vec)
        results.append((emb_result.chunk_id, similarity))

    # 유사도 순으로 정렬
    results.sort(key=lambda x: x[1], reverse=True)

    return results[:top_k]


def calculate_overlap(
    results1: list[tuple[str, float]],
    results2: list[tuple[str, float]],
    k_values: list[int] = [3, 5, 10]
) -> dict[int, float]:
    """두 결과의 overlap 계산."""
    overlap = {}

    for k in k_values:
        set1 = {r[0] for r in results1[:k]}
        set2 = {r[0] for r in results2[:k]}

        if len(set1) == 0 or len(set2) == 0:
            overlap[k] = 0.0
        else:
            intersection = len(set1 & set2)
            overlap[k] = intersection / k

    return overlap


# =============================================================================
# Main Comparison Logic
# =============================================================================

async def run_comparison(
    query: str = "biportal endoscopic interbody fusion",
    year: int = 2025,
    max_papers: int = 20,
    test_queries: list[str] = None
):
    """임베딩 모델 비교 실행."""

    print("=" * 70)
    print("Embedding Model Comparison: MedTE vs OpenAI")
    print("=" * 70)

    # 1. PubMed 검색
    print("\n[Phase 1] PubMed Search")
    papers = await search_pubmed(query, year, max_papers)

    if not papers:
        print("No papers found. Exiting.")
        return

    print(f"\nRetrieved {len(papers)} papers")

    # 2. 청크 생성
    print("\n[Phase 2] Creating Chunks")
    all_chunks = []
    for paper in papers:
        chunks = create_chunks_from_paper(paper)
        paper.chunks = chunks
        all_chunks.extend(chunks)
        print(f"  {paper.pmid}: {len(chunks)} chunks - {paper.title[:50]}...")

    print(f"\nTotal chunks: {len(all_chunks)}")

    # 3. 임베딩 생성
    print("\n[Phase 3] Generating Embeddings")

    # 청크 텍스트 추출
    chunk_texts = [c["content"] for c in all_chunks]

    # MedTE 임베딩
    print("\n3.1. MedTE Embeddings (768d)")
    medte_model = MedTEEmbedding()
    medte_embeddings = medte_model.embed(chunk_texts)
    print(f"  Generated {len(medte_embeddings)} embeddings")

    # OpenAI 임베딩
    print("\n3.2. OpenAI Embeddings (3072d)")
    try:
        openai_model = OpenAIEmbedding()
        openai_embeddings = openai_model.embed(chunk_texts)
        print(f"  Generated {len(openai_embeddings)} embeddings")
    except Exception as e:
        print(f"  OpenAI embedding failed: {e}")
        print("  Continuing with MedTE only...")
        openai_embeddings = [[] for _ in chunk_texts]

    # EmbeddingResult 객체 생성
    embedding_results = []
    for i, chunk in enumerate(all_chunks):
        result = EmbeddingResult(
            chunk_id=chunk["chunk_id"],
            content=chunk["content"],
            medte_embedding=medte_embeddings[i] if i < len(medte_embeddings) else [],
            openai_embedding=openai_embeddings[i] if i < len(openai_embeddings) else [],
            section=chunk.get("section", ""),
            is_key_finding=chunk.get("is_key_finding", False)
        )
        embedding_results.append(result)

    # 4. 검색 품질 비교
    print("\n[Phase 4] Search Quality Comparison")

    # 테스트 쿼리
    if test_queries is None:
        test_queries = [
            "biportal endoscopic spine surgery outcomes",
            "lumbar fusion complications",
            "minimally invasive decompression",
            "endoscopic discectomy results",
            "spine surgery clinical outcomes",
        ]

    comparison_results = []

    for test_query in test_queries:
        print(f"\n  Query: '{test_query}'")

        # 쿼리 임베딩 생성
        medte_query_emb = medte_model.embed([test_query])[0]

        try:
            openai_query_emb = openai_model.embed([test_query])[0]
        except:
            openai_query_emb = []

        # 검색 수행
        medte_results = search_similar(medte_query_emb, embedding_results, "medte", top_k=10)

        if openai_query_emb:
            openai_results = search_similar(openai_query_emb, embedding_results, "openai", top_k=10)
        else:
            openai_results = []

        # Overlap 계산
        if openai_results:
            overlap = calculate_overlap(medte_results, openai_results, [3, 5, 10])
        else:
            overlap = {}

        comparison = ComparisonResult(
            query=test_query,
            medte_results=medte_results,
            openai_results=openai_results,
            overlap_at_k=overlap
        )
        comparison_results.append(comparison)

        # 결과 출력
        print(f"    MedTE Top-3:")
        for chunk_id, score in medte_results[:3]:
            print(f"      [{score:.4f}] {chunk_id}")

        if openai_results:
            print(f"    OpenAI Top-3:")
            for chunk_id, score in openai_results[:3]:
                print(f"      [{score:.4f}] {chunk_id}")

            print(f"    Overlap: @3={overlap.get(3, 0):.2%}, @5={overlap.get(5, 0):.2%}, @10={overlap.get(10, 0):.2%}")

    # 5. 요약 통계
    print("\n" + "=" * 70)
    print("Summary Statistics")
    print("=" * 70)

    print(f"\nTotal papers: {len(papers)}")
    print(f"Total chunks: {len(all_chunks)}")
    print(f"MedTE dimension: {medte_model.dimension}")
    print(f"OpenAI dimension: 3072" if openai_embeddings[0] else "OpenAI: N/A")

    if comparison_results and comparison_results[0].openai_results:
        avg_overlap = {
            k: np.mean([c.overlap_at_k.get(k, 0) for c in comparison_results])
            for k in [3, 5, 10]
        }
        print(f"\nAverage Overlap across queries:")
        print(f"  @3:  {avg_overlap[3]:.2%}")
        print(f"  @5:  {avg_overlap[5]:.2%}")
        print(f"  @10: {avg_overlap[10]:.2%}")

    # 6. 결과 저장
    output_dir = Path(__file__).parent.parent / "data" / "embedding_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"comparison_{timestamp}.json"

    output_data = {
        "query": query,
        "year": year,
        "timestamp": timestamp,
        "papers_count": len(papers),
        "chunks_count": len(all_chunks),
        "papers": [
            {
                "pmid": p.pmid,
                "title": p.title,
                "year": p.year,
                "journal": p.journal,
                "chunks_count": len(p.chunks)
            }
            for p in papers
        ],
        "comparison_results": [
            {
                "query": c.query,
                "medte_top10": c.medte_results,
                "openai_top10": c.openai_results,
                "overlap": c.overlap_at_k
            }
            for c in comparison_results
        ]
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")

    return comparison_results


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    asyncio.run(run_comparison())
