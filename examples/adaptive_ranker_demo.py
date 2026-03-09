"""Adaptive Hybrid Ranker Demo.

쿼리 유형에 따라 Graph/Vector 가중치를 동적으로 조정하는
AdaptiveHybridRanker의 실제 사용 예시.
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.solver.adaptive_ranker import (
    QueryType,
    QueryClassifier,
    AdaptiveHybridRanker,
    RankedResult,
)
from src.solver.graph_result import GraphEvidence, PaperNode
from src.storage.vector_db import SearchResult as VectorSearchResult


def demo_query_classification():
    """쿼리 분류 데모."""
    print("=" * 70)
    print("DEMO 1: Query Classification")
    print("=" * 70)

    classifier = QueryClassifier()

    queries = [
        ("What is the fusion rate of TLIF?", QueryType.FACTUAL),
        ("TLIF vs OLIF for stenosis", QueryType.COMPARATIVE),
        ("What treatments exist for stenosis?", QueryType.EXPLORATORY),
        ("Is TLIF effective for disc herniation?", QueryType.EVIDENCE),
        ("How is UBE performed?", QueryType.PROCEDURAL),
    ]

    print("\nQuery Type Classification:\n")
    for query, expected_type in queries:
        classified_type = classifier.classify(query)
        confidence = classifier.get_confidence(query, classified_type)

        status = "✓" if classified_type == expected_type else "✗"
        print(f"{status} Query: {query}")
        print(f"  Type: {classified_type.value} (Confidence: {confidence:.2f})")
        print()


def demo_weight_adaptation():
    """가중치 적응 데모."""
    print("\n" + "=" * 70)
    print("DEMO 2: Adaptive Weight Adjustment")
    print("=" * 70)

    from src.solver.adaptive_ranker import QUERY_TYPE_WEIGHTS

    print("\nQuery Type별 최적 가중치:\n")
    for query_type, weights in QUERY_TYPE_WEIGHTS.items():
        graph_pct = int(weights["graph"] * 100)
        vector_pct = int(weights["vector"] * 100)

        print(f"{query_type.value:12s}: Graph {graph_pct:3d}%, Vector {vector_pct:3d}%")

        # 설명
        if query_type == QueryType.FACTUAL:
            print("  → 구체적 수치/사실 정보는 Graph 선호")
        elif query_type == QueryType.COMPARATIVE:
            print("  → 비교 연구는 Graph 강력 선호 (구조화된 근거)")
        elif query_type == QueryType.EXPLORATORY:
            print("  → 넓은 범위 탐색은 Vector 선호 (시맨틱 검색)")
        elif query_type == QueryType.EVIDENCE:
            print("  → 통계적 근거는 Graph 선호 (p-value, effect size)")
        elif query_type == QueryType.PROCEDURAL:
            print("  → 절차/기술 설명은 Vector 선호 (텍스트 서술)")
        print()


def create_mock_results():
    """Mock 데이터 생성."""
    # Mock Graph Results
    graph_results = [
        {
            "paper_id": "smith2024",
            "title": "TLIF vs OLIF for Lumbar Stenosis: RCT",
            "score": 0.92,
            "evidence": GraphEvidence(
                intervention="TLIF",
                outcome="Fusion Rate",
                value="94.2%",
                source_paper_id="smith2024",
                evidence_level="1b",
                p_value=0.001,
                is_significant=True,
                direction="improved",
                value_control="87.5%"
            ),
            "paper": PaperNode(
                paper_id="smith2024",
                title="TLIF vs OLIF for Lumbar Stenosis: RCT",
                authors=["Smith J", "Lee K"],
                year=2024,
                journal="Spine",
                evidence_level="1b",
                study_design="RCT"
            )
        },
        {
            "paper_id": "kim2023",
            "title": "Endoscopic Decompression Techniques",
            "score": 0.78,
            "evidence": GraphEvidence(
                intervention="UBE",
                outcome="VAS",
                value="2.1 points",
                source_paper_id="kim2023",
                evidence_level="2a",
                p_value=0.03,
                is_significant=True,
                direction="improved"
            ),
            "paper": PaperNode(
                paper_id="kim2023",
                title="Endoscopic Decompression Techniques",
                authors=["Kim S", "Park M"],
                year=2023,
                journal="J Neurosurg Spine",
                evidence_level="2a"
            )
        }
    ]

    # Mock Vector Results
    vector_results = [
        VectorSearchResult(
            chunk_id="chunk1",
            document_id="smith2024",
            title="TLIF vs OLIF for Lumbar Stenosis: RCT",
            score=0.89,
            content="TLIF demonstrated superior fusion rate (94.2%) compared to OLIF (87.5%) at 2-year follow-up (p=0.001).",
            tier="tier1",
            section="results",
            source_type="original",
            evidence_level="1b",
            is_key_finding=True,
            has_statistics=True,
            publication_year=2024,
            summary="TLIF superior fusion rate vs OLIF"
        ),
        VectorSearchResult(
            chunk_id="chunk2",
            document_id="park2022",
            title="Minimally Invasive Spine Surgery Review",
            score=0.82,
            content="Various MIS techniques including TLIF, OLIF, and endoscopic approaches offer advantages in reducing tissue trauma...",
            tier="tier1",
            section="introduction",
            source_type="original",
            evidence_level="4",
            is_key_finding=False,
            has_statistics=False,
            publication_year=2022,
            summary="Overview of MIS techniques"
        ),
        VectorSearchResult(
            chunk_id="chunk3",
            document_id="kim2023",
            title="Endoscopic Decompression Techniques",
            score=0.75,
            content="UBE showed significant VAS improvement (2.1 points reduction, p=0.03) with minimal complications.",
            tier="tier2",
            section="discussion",
            source_type="original",
            evidence_level="2a",
            is_key_finding=True,
            has_statistics=True,
            publication_year=2023,
            summary="UBE effective for pain reduction"
        )
    ]

    return graph_results, vector_results


def demo_adaptive_ranking():
    """Adaptive Ranking 데모."""
    print("\n" + "=" * 70)
    print("DEMO 3: Adaptive Hybrid Ranking")
    print("=" * 70)

    ranker = AdaptiveHybridRanker()
    graph_results, vector_results = create_mock_results()

    test_queries = [
        "What is the fusion rate of TLIF?",  # FACTUAL
        "TLIF vs OLIF for stenosis",  # COMPARATIVE
        "What treatments exist for stenosis?",  # EXPLORATORY
    ]

    for query in test_queries:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"{'='*70}")

        results = ranker.rank(
            query=query,
            graph_results=graph_results,
            vector_results=vector_results
        )

        if results:
            first_result = results[0]
            print(f"\nQuery Type: {first_result.query_type.value}")
            print(f"Graph Weight: {first_result.metadata['graph_weight']:.0%}")
            print(f"Vector Weight: {first_result.metadata['vector_weight']:.0%}")

            print(f"\nTop 3 Results:\n")
            for i, result in enumerate(results[:3], 1):
                print(f"{i}. {result.title}")
                print(f"   Final Score: {result.final_score:.3f} "
                      f"(Graph: {result.graph_score:.3f}, Vector: {result.vector_score:.3f})")

                if result.evidence:
                    print(f"   Evidence: {result.evidence.get_display_text()}")

                print()


def demo_override_weights():
    """가중치 오버라이드 데모."""
    print("\n" + "=" * 70)
    print("DEMO 4: Override Weights for Custom Scenarios")
    print("=" * 70)

    ranker = AdaptiveHybridRanker()
    graph_results, vector_results = create_mock_results()

    query = "TLIF vs OLIF for stenosis"

    # 기본 가중치 (COMPARATIVE: Graph 80%, Vector 20%)
    print(f"\nQuery: {query}\n")

    print("1. Default Weights (COMPARATIVE):")
    results_default = ranker.rank(
        query=query,
        graph_results=graph_results,
        vector_results=vector_results
    )
    print(f"   Graph: {results_default[0].metadata['graph_weight']:.0%}, "
          f"Vector: {results_default[0].metadata['vector_weight']:.0%}")
    print(f"   Top Result Score: {results_default[0].final_score:.3f}")

    # 균형 가중치
    print("\n2. Balanced Weights (50/50):")
    results_balanced = ranker.rank(
        query=query,
        graph_results=graph_results,
        vector_results=vector_results,
        override_weights={"graph": 0.5, "vector": 0.5}
    )
    print(f"   Graph: 50%, Vector: 50%")
    print(f"   Top Result Score: {results_balanced[0].final_score:.3f}")

    # Vector 우선
    print("\n3. Vector-Preferred Weights (20/80):")
    results_vector = ranker.rank(
        query=query,
        graph_results=graph_results,
        vector_results=vector_results,
        override_weights={"graph": 0.2, "vector": 0.8}
    )
    print(f"   Graph: 20%, Vector: 80%")
    print(f"   Top Result Score: {results_vector[0].final_score:.3f}")


def demo_score_breakdown():
    """점수 분석 데모."""
    print("\n" + "=" * 70)
    print("DEMO 5: Score Breakdown Analysis")
    print("=" * 70)

    ranker = AdaptiveHybridRanker()
    graph_results, vector_results = create_mock_results()

    query = "TLIF vs OLIF for stenosis"
    print(f"\nQuery: {query}")
    print(f"Query Type: COMPARATIVE (Graph 80%, Vector 20%)\n")

    results = ranker.rank(
        query=query,
        graph_results=graph_results,
        vector_results=vector_results
    )

    print("Detailed Score Breakdown:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result.paper_id}")
        print(f"   Title: {result.title}")
        print(f"   {result.get_score_breakdown()}")

        # 가중 적용 전 점수
        print(f"   Normalized Scores - Graph: {result.graph_score:.3f}, Vector: {result.vector_score:.3f}")

        # 최종 점수 계산 과정
        weighted_graph = result.graph_score * result.metadata['graph_weight']
        weighted_vector = result.vector_score * result.metadata['vector_weight']
        print(f"   Weighted Scores - Graph: {weighted_graph:.3f} (80%), Vector: {weighted_vector:.3f} (20%)")
        print(f"   Final Score: {result.final_score:.3f} = {weighted_graph:.3f} + {weighted_vector:.3f}")
        print()


def main():
    """메인 실행."""
    print("\n" + "=" * 70)
    print("Adaptive Hybrid Ranker Demonstration")
    print("=" * 70)

    # Demo 1: Query Classification
    demo_query_classification()

    # Demo 2: Weight Adaptation
    demo_weight_adaptation()

    # Demo 3: Adaptive Ranking
    demo_adaptive_ranking()

    # Demo 4: Override Weights
    demo_override_weights()

    # Demo 5: Score Breakdown
    demo_score_breakdown()

    print("\n" + "=" * 70)
    print("Demo Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
