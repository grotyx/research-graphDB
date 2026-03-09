"""Chain Builder Usage Examples.

LangChain Chain Builder 사용 예시.
"""

import asyncio
import os
from dotenv import load_dotenv

from src.orchestrator import create_chain, ChainConfig


async def example_1_simple_qa():
    """Example 1: Simple QA mode."""
    print("\n" + "=" * 80)
    print("Example 1: Simple QA Mode")
    print("=" * 80)

    # Load environment variables
    load_dotenv()

    # Create chain with default configuration
    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    # Ask a question
    query = "TLIF가 Fusion Rate 개선에 효과적인가?"
    print(f"\nQuery: {query}")

    result = await chain.invoke(query, mode="qa")

    print("\n--- Answer ---")
    print(result.answer)

    print("\n--- Sources ---")
    for i, source in enumerate(result.sources, 1):
        print(f"\n{i}. [{source.result_type.upper()}] Score: {source.score:.3f}")
        print(f"   {source.get_citation()}")
        print(f"   {source.get_evidence_text()}")

    print("\n--- Metadata ---")
    print(f"Mode: {result.metadata.get('mode')}")
    print(f"Total sources: {result.metadata.get('num_sources')}")
    print(f"Graph results: {result.metadata.get('graph_count')}")
    print(f"Vector results: {result.metadata.get('vector_count')}")


async def example_2_conflict_analysis():
    """Example 2: Conflict analysis mode."""
    print("\n" + "=" * 80)
    print("Example 2: Conflict Analysis Mode")
    print("=" * 80)

    load_dotenv()

    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    # Ask about conflicting evidence
    query = "OLIF와 TLIF의 Canal Area 개선 효과에 대한 연구 결과가 일치하는가?"
    print(f"\nQuery: {query}")

    result = await chain.invoke(query, mode="conflict")

    print("\n--- Conflict Analysis ---")
    print(result.answer)

    if result.metadata.get("conflicts"):
        print("\n⚠️  Conflicting evidence detected!")
        print(f"Number of conflicts: {result.metadata.get('num_conflicts')}")
    else:
        print("\n✅ No conflicts found")

    print("\n--- Conflicting Sources ---")
    for i, source in enumerate(result.sources, 1):
        print(f"\n{i}. {source.get_citation()}")
        print(f"   {source.get_evidence_text()}")


async def example_3_retrieval_only():
    """Example 3: Retrieval only mode."""
    print("\n" + "=" * 80)
    print("Example 3: Retrieval Only Mode")
    print("=" * 80)

    load_dotenv()

    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    # Search for relevant papers
    query = "UBE 수술법 관련 연구"
    print(f"\nQuery: {query}")

    result = await chain.invoke(query, mode="retrieval")

    print("\n--- Retrieved Sources ---")
    for i, source in enumerate(result.sources, 1):
        print(f"\n{i}. [{source.result_type.upper()}] Score: {source.score:.3f}")
        print(f"   {source.get_citation()}")

        # Show metadata
        if source.metadata:
            print(f"   Metadata:")
            for key, value in source.metadata.items():
                if value:
                    print(f"     - {key}: {value}")


async def example_4_custom_config():
    """Example 4: Custom configuration."""
    print("\n" + "=" * 80)
    print("Example 4: Custom Configuration")
    print("=" * 80)

    load_dotenv()

    # Custom configuration
    config = ChainConfig(
        gemini_model="gemini-2.5-flash-preview-05-20",
        temperature=0.0,          # Most conservative
        max_output_tokens=4096,   # Longer responses
        top_k=20,                 # More results
        graph_weight=0.8,         # Prioritize graph evidence
        vector_weight=0.2,
        min_p_value=0.01,         # More strict significance threshold
    )

    print("\nCustom Config:")
    print(f"  Model: {config.gemini_model}")
    print(f"  Temperature: {config.temperature}")
    print(f"  Top-K: {config.top_k}")
    print(f"  Graph Weight: {config.graph_weight}")
    print(f"  Vector Weight: {config.vector_weight}")

    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        config=config,
    )

    query = "PLIF vs TLIF 비교 연구 결과는?"
    print(f"\nQuery: {query}")

    result = await chain.invoke(query, mode="qa")

    print("\n--- Answer ---")
    print(result.answer)

    print(f"\n--- Retrieved {len(result.sources)} sources ---")


async def example_5_batch_processing():
    """Example 5: Batch processing multiple queries."""
    print("\n" + "=" * 80)
    print("Example 5: Batch Processing")
    print("=" * 80)

    load_dotenv()

    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    queries = [
        "TLIF의 Fusion Rate는?",
        "PLIF의 합병증은?",
        "OLIF vs LLIF 비교는?",
    ]

    print("\nProcessing queries in parallel:")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q}")

    # Parallel execution
    tasks = [chain.invoke(q, mode="qa") for q in queries]
    results = await asyncio.gather(*tasks)

    print("\n--- Results ---")
    for i, (query, result) in enumerate(zip(queries, results), 1):
        print(f"\n{i}. Query: {query}")
        print(f"   Sources: {len(result.sources)}")
        print(f"   Answer preview: {result.answer[:100]}...")


async def example_6_chain_stats():
    """Example 6: Chain statistics."""
    print("\n" + "=" * 80)
    print("Example 6: Chain Statistics")
    print("=" * 80)

    load_dotenv()

    chain = await create_chain(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    # Get statistics
    stats = chain.get_stats()

    print("\n--- Chain Configuration ---")
    config = stats.get("config", {})
    for key, value in config.items():
        print(f"  {key}: {value}")

    print("\n--- Hybrid Ranker Statistics ---")
    ranker_stats = stats.get("hybrid_ranker", {})
    print(f"  Vector DB available: {ranker_stats.get('vector_db', {})}")
    print(f"  Graph DB available: {ranker_stats.get('graph_db_available')}")


async def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("LangChain Chain Builder Examples")
    print("=" * 80)

    try:
        # Example 1: Simple QA
        await example_1_simple_qa()

        # Example 2: Conflict analysis
        await example_2_conflict_analysis()

        # Example 3: Retrieval only
        await example_3_retrieval_only()

        # Example 4: Custom configuration
        await example_4_custom_config()

        # Example 5: Batch processing
        await example_5_batch_processing()

        # Example 6: Statistics
        await example_6_chain_stats()

        print("\n" + "=" * 80)
        print("All examples completed!")
        print("=" * 80)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run all examples
    asyncio.run(main())
