# External Data Sources Module

This module provides integration with external medical literature databases and APIs for the Medical KAG system.

## PubMed Client

The `pubmed_client.py` module provides a Python client for the NCBI PubMed E-utilities API, enabling programmatic access to millions of biomedical research papers.

### Features

- **Search PubMed**: Query the database using PubMed's search syntax
- **Fetch Metadata**: Retrieve comprehensive paper details including:
  - Title, authors, journal, publication year
  - Abstract text
  - MeSH (Medical Subject Headings) terms
  - DOI and publication types
- **Async Support**: Batch operations with aiohttp for improved performance
- **Rate Limiting**: Automatic compliance with NCBI usage guidelines
- **Error Handling**: Robust exception handling for API errors

### Quick Start

```python
from external.pubmed_client import PubMedClient

# Initialize client
client = PubMedClient(email="your.email@example.com")

# Search for papers
pmids = client.search("spine surgery endoscopic", max_results=10)

# Fetch paper details
for pmid in pmids:
    paper = client.fetch_paper_details(pmid)
    print(f"{paper.title} ({paper.year})")
    print(f"Abstract: {paper.abstract[:200]}...")
```

### Async Usage

For better performance with multiple papers:

```python
import asyncio
from external.pubmed_client import PubMedClient

async def fetch_papers():
    client = PubMedClient(email="your.email@example.com")

    # Search
    pmids = await client.search_async("cervical spine", max_results=20)

    # Fetch all in parallel
    papers = await client.fetch_batch_async(pmids)

    return papers

papers = asyncio.run(fetch_papers())
```

### Advanced Search

PubMed supports powerful search syntax:

```python
# Search by title
client.search("spine[Title] AND surgery[Title]")

# Filter by publication type
client.search("(randomized controlled trial[PT]) AND spine")

# Use MeSH terms
client.search("cervical spine[MeSH] AND complications[MeSH]")

# Filter by date
client.search("spine surgery AND 2023[PDAT]")
```

### Rate Limits

- **Without API key**: 3 requests per second
- **With API key**: 10 requests per second

Get your free API key at: https://www.ncbi.nlm.nih.gov/account/

```python
client = PubMedClient(
    email="your.email@example.com",
    api_key="your_api_key_here"
)
```

### API Reference

#### PubMedClient

**Methods:**

- `search(query: str, max_results: int = 10) -> List[str]`
  - Search PubMed and return PMIDs

- `fetch_paper_details(pmid: str) -> PaperMetadata`
  - Fetch complete metadata for a paper

- `fetch_abstract(pmid: str) -> str`
  - Fetch just the abstract text

- `search_async(query: str, max_results: int = 10) -> List[str]`
  - Async version of search

- `fetch_paper_details_async(pmid: str) -> PaperMetadata`
  - Async version of fetch_paper_details

- `fetch_batch_async(pmids: List[str]) -> List[PaperMetadata]`
  - Fetch multiple papers in parallel

#### PaperMetadata

**Attributes:**

- `pmid: str` - PubMed ID
- `title: str` - Paper title
- `authors: List[str]` - List of authors
- `year: int` - Publication year
- `journal: str` - Journal name
- `abstract: str` - Full abstract text
- `mesh_terms: List[str]` - MeSH terms
- `doi: str` - Digital Object Identifier (optional)
- `publication_types: List[str]` - Publication type classifications

### Error Handling

```python
from external.pubmed_client import PubMedClient, APIError, RateLimitError

client = PubMedClient()

try:
    pmids = client.search("spine surgery")
    papers = [client.fetch_paper_details(pmid) for pmid in pmids]
except APIError as e:
    print(f"API request failed: {e}")
except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
```

### Integration with Medical KAG

The PubMed client can be used to:

1. **Seed the knowledge base** with relevant medical literature
2. **Expand search results** with external papers
3. **Validate references** mentioned in documents
4. **Enrich metadata** with MeSH terms and publication types

Example integration:

```python
# Search PubMed for papers related to a query
pmids = client.search(user_query, max_results=20)

# Fetch abstracts for indexing
papers = await client.fetch_batch_async(pmids)

# Index in the KAG system
for paper in papers:
    # Extract PICO elements
    pico = pico_extractor.extract(paper.abstract)

    # Classify study type
    study_type = study_classifier.classify(paper.publication_types)

    # Add to knowledge graph
    kg.add_paper(paper, pico=pico, study_type=study_type)
```

### Testing

Run the test suite:

```bash
PYTHONPATH=./src python -m pytest tests/external/test_pubmed_client.py -v
```

See example usage:

```bash
python examples/pubmed_example.py
```

### Dependencies

- `requests>=2.31.0` - HTTP library for synchronous requests
- `aiohttp>=3.9.0` - Async HTTP library for batch operations
- Python 3.10+

### References

- [NCBI E-utilities Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [PubMed Search Tips](https://pubmed.ncbi.nlm.nih.gov/help/)
- [MeSH Database](https://www.ncbi.nlm.nih.gov/mesh/)
