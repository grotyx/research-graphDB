"""Example usage of the PubMed client for Medical KAG system.

This script demonstrates how to:
1. Search PubMed for papers
2. Fetch paper details (title, authors, abstract, etc.)
3. Use async methods for batch operations
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from external.pubmed_client import PubMedClient, APIError


def example_basic_search():
    """Example: Basic PubMed search."""
    print("=" * 60)
    print("Example 1: Basic Search")
    print("=" * 60)

    # Initialize client (optionally with email and API key)
    client = PubMedClient(email="your.email@example.com")

    # Search for papers about spine surgery
    try:
        pmids = client.search("spine surgery endoscopic", max_results=5)
        print(f"\nFound {len(pmids)} papers:")
        for i, pmid in enumerate(pmids, 1):
            print(f"  {i}. PMID: {pmid}")
    except APIError as e:
        print(f"Error: {e}")


def example_fetch_details():
    """Example: Fetch paper details."""
    print("\n" + "=" * 60)
    print("Example 2: Fetch Paper Details")
    print("=" * 60)

    client = PubMedClient(email="your.email@example.com")

    # First search for a paper
    try:
        pmids = client.search("spine minimally invasive surgery", max_results=1)
        if pmids:
            pmid = pmids[0]
            print(f"\nFetching details for PMID: {pmid}")

            # Fetch full details
            paper = client.fetch_paper_details(pmid)

            print(f"\nTitle: {paper.title}")
            print(f"Authors: {', '.join(paper.authors[:3])}...")
            print(f"Journal: {paper.journal}")
            print(f"Year: {paper.year}")
            print(f"DOI: {paper.doi}")
            print(f"\nMeSH Terms: {', '.join(paper.mesh_terms[:5])}")
            print(f"\nPublication Types: {', '.join(paper.publication_types)}")
            print(f"\nAbstract: {paper.abstract[:200]}...")
    except APIError as e:
        print(f"Error: {e}")


def example_fetch_abstract_only():
    """Example: Fetch just the abstract."""
    print("\n" + "=" * 60)
    print("Example 3: Fetch Abstract Only")
    print("=" * 60)

    client = PubMedClient(email="your.email@example.com")

    try:
        pmids = client.search("lumbar disc herniation", max_results=1)
        if pmids:
            pmid = pmids[0]
            print(f"\nFetching abstract for PMID: {pmid}")

            abstract = client.fetch_abstract(pmid)
            print(f"\n{abstract[:300]}...")
    except APIError as e:
        print(f"Error: {e}")


async def example_async_batch():
    """Example: Async batch fetch for better performance."""
    print("\n" + "=" * 60)
    print("Example 4: Async Batch Fetch")
    print("=" * 60)

    client = PubMedClient(email="your.email@example.com")

    try:
        # First search for multiple papers
        pmids = await client.search_async("cervical spine surgery", max_results=5)
        print(f"\nFound {len(pmids)} papers")

        # Fetch all details in parallel
        print("Fetching details for all papers (in parallel)...")
        papers = await client.fetch_batch_async(pmids)

        print(f"\nSuccessfully fetched {len(papers)} papers:\n")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title[:60]}...")
            print(f"   Year: {paper.year}, Journal: {paper.journal[:40]}")
            print()
    except APIError as e:
        print(f"Error: {e}")


def example_with_api_key():
    """Example: Using API key for higher rate limits."""
    print("\n" + "=" * 60)
    print("Example 5: Using API Key")
    print("=" * 60)

    # With API key, you can make up to 10 requests/second instead of 3
    # Get your API key from: https://www.ncbi.nlm.nih.gov/account/
    api_key = "YOUR_API_KEY_HERE"  # Replace with your actual API key

    if api_key != "YOUR_API_KEY_HERE":
        client = PubMedClient(email="your.email@example.com", api_key=api_key)
        print(f"Rate limit: {client.RATE_LIMIT_DELAY}s between requests")
        print("(0.1s with API key vs 0.34s without)")
    else:
        print("No API key provided - skipping this example")
        print("Get your key from: https://www.ncbi.nlm.nih.gov/account/")


def example_advanced_search():
    """Example: Advanced PubMed search with filters."""
    print("\n" + "=" * 60)
    print("Example 6: Advanced Search Query")
    print("=" * 60)

    client = PubMedClient(email="your.email@example.com")

    # Use PubMed's advanced search syntax
    queries = [
        "spine[Title] AND surgery[Title] AND 2023[PDAT]",  # Title + year
        "(randomized controlled trial[PT]) AND spine surgery",  # RCTs only
        "cervical spine[MeSH] AND complications[MeSH]",  # MeSH terms
    ]

    for query in queries:
        try:
            pmids = client.search(query, max_results=3)
            print(f"\nQuery: {query}")
            print(f"Results: {len(pmids)} papers found")
            if pmids:
                print(f"PMIDs: {', '.join(pmids)}")
        except APIError as e:
            print(f"Error: {e}")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("PubMed Client Examples for Medical KAG System")
    print("=" * 60)

    # Run synchronous examples
    example_basic_search()
    example_fetch_details()
    example_fetch_abstract_only()
    example_with_api_key()
    example_advanced_search()

    # Run async example
    asyncio.run(example_async_batch())

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
