# Orchestrator Module API Documentation

## Overview

The Orchestrator module provides LangChain-based hybrid search orchestration, combining Neo4j Graph search with ChromaDB Vector search and Gemini LLM-based response synthesis.

**Module Path**: `src/src/orchestrator/`

**Key Components**:
- `chain_builder.py` - LangChain chain orchestration
- `cypher_generator.py` - Natural language to Cypher conversion
- `response_synthesizer.py` - Evidence-based answer generation

---

## chain_builder.py

LangChain-based hybrid search and QA chain construction.

### Data Classes

#### `ChainConfig`

Configuration for chain behavior.

```python
@dataclass
class ChainConfig:
    gemini_model: str = "gemini-2.5-flash-preview-05-20"
    temperature: float = 0.1
    max_output_tokens: int = 8192
    top_k: int = 10
    graph_weight: float = 0.6  # Graph evidence importance
    vector_weight: float = 0.4  # Vector evidence importance
    min_p_value: float = 0.05  # Significance threshold
```

#### `ChainInput`

Input to chain.

```python
@dataclass
class ChainInput:
    query: str
    chat_history: list[dict] = None
    filters: dict = None
```

#### `ChainOutput`

Output from chain.

```python
@dataclass
class ChainOutput:
    answer: str
    sources: list[HybridResult]
    cypher_query: str = ""
    graph_results: list[dict] = None
    vector_results: list[VectorSearchResult] = None
    metadata: dict = None
```

### `HybridRetriever`

Custom retriever combining Graph + Vector search.

**Initialization**:

```python
retriever = HybridRetriever(
    hybrid_ranker=hybrid_ranker,
    cypher_generator=cypher_generator,
    top_k=10,
    graph_weight=0.6,
    vector_weight=0.4
)
```

**Methods**:

```python
async def ainvoke(self, query: str) -> list[HybridResult]:
    """Async search execution.

    Process:
        1. Extract entities using CypherGenerator
        2. Generate query embedding
        3. Execute hybrid search (Graph + Vector)
        4. Return ranked results
    """

def invoke(self, query: str) -> list[HybridResult]:
    """Sync wrapper for async search."""
```

**Example**:

```python
results = await retriever.ainvoke("OLIF가 VAS 개선에 효과적인가?")
# Returns: list[HybridResult] with graph and vector evidence
```

### Prompt Templates

#### `RETRIEVAL_QA_PROMPT`

System prompt for evidence-based QA.

```python
RETRIEVAL_QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a spine surgery research assistant...

    Guidelines:
    1. Base your answer ONLY on the provided evidence
    2. Always cite the source papers
    3. Distinguish between Graph Evidence (statistics) and Vector Evidence (text)
    4. If evidence is conflicting, explain both sides
    5. If evidence is insufficient, say so clearly

    Evidence Levels:
    - 1a: Meta-analysis of RCTs (highest quality)
    - 1b: Randomized Controlled Trial
    - 2a: Cohort study
    - 2b: Case-control study
    - 3: Case series
    - 4: Expert opinion (lowest quality)
    """),
    ("human", "Question: {question}\n\nEvidence:\n{context}\n\nAnswer:")
])
```

#### `CONFLICTING_EVIDENCE_PROMPT`

Prompt for conflict analysis.

```python
CONFLICTING_EVIDENCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Analyze conflicting evidence from multiple studies.

    Your task:
    1. Identify key differences in study designs
    2. Explain possible reasons for conflicting results
    3. Provide a balanced summary
    4. Recommend which evidence to trust based on evidence level, sample size, p-value, recency
    """),
    ("human", "Question: {question}\n\nConflicting Evidence:\n{context}\n\nAnalysis:")
])
```

### `SpineGraphChain`

Main LangChain orchestration class.

**Initialization**:

```python
chain = SpineGraphChain(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    config=ChainConfig(
        graph_weight=0.6,
        vector_weight=0.4
    ),
    api_key=os.getenv("GEMINI_API_KEY")
)
```

**Chain Building Methods**:

```python
def build_retrieval_chain(self):
    """Build hybrid retrieval pipeline (no LLM)."""

def build_qa_chain(self):
    """Build QA chain with evidence-based prompting."""

def build_conflict_chain(self):
    """Build conflict analysis chain."""
```

**Main Invocation**:

```python
async def invoke(
    self,
    query: str,
    mode: str = "qa"  # "qa", "conflict", "retrieval"
) -> ChainOutput:
    """Execute chain in specified mode.

    Modes:
        - qa: Question answering with evidence
        - conflict: Conflict analysis
        - retrieval: Retrieval only (no LLM)

    Returns:
        ChainOutput with answer, sources, metadata
    """
```

**Internal Methods**:

```python
def _format_context(self, results: list[HybridResult]) -> str:
    """Format HybridResults for LLM input."""

def _detect_conflicts(
    self, graph_results: list[HybridResult]
) -> list[dict]:
    """Find contradictory Graph evidence."""
```

**Example Usage**:

```python
# Create chain
chain = await create_chain(
    neo4j_uri="bolt://localhost:7687",
    chromadb_path="./data/chromadb",
    gemini_api_key=os.getenv("GEMINI_API_KEY")
)

# QA mode
result = await chain.invoke(
    "OLIF가 VAS 개선에 효과적인가?",
    mode="qa"
)
print(result.answer)
print(f"Sources: {len(result.sources)}")

# Conflict analysis mode
result = await chain.invoke(
    "OLIF와 TLIF의 Fusion Rate 비교 결과가 일치하는가?",
    mode="conflict"
)
print(result.answer)

# Retrieval only mode
result = await chain.invoke(
    "TLIF 관련 연구 검색",
    mode="retrieval"
)
print(f"Retrieved {len(result.sources)} sources")
```

### Factory Function

```python
async def create_chain(
    neo4j_uri: str,
    chromadb_path: str,
    gemini_api_key: str,
    config: Optional[ChainConfig] = None
) -> SpineGraphChain:
    """Create and initialize SpineGraphChain.

    Args:
        neo4j_uri: Neo4j connection URI
        chromadb_path: ChromaDB storage path
        gemini_api_key: Gemini API key
        config: Chain configuration (optional)

    Returns:
        Initialized SpineGraphChain
    """
```

---

## cypher_generator.py

Natural language to Cypher query conversion.

### Data Classes

#### `QueryIntent`

Detected query intent.

```python
@dataclass
class QueryIntent:
    intent_type: str  # evidence_search, comparison, hierarchy, conflict
    confidence: float = 0.0
    description: str = ""
```

#### `ExtractedEntities`

Entities extracted from query.

```python
@dataclass
class ExtractedEntities:
    interventions: list[str]
    pathologies: list[str]
    outcomes: list[str]
    anatomy: list[str]
    sub_domain: Optional[str] = None
```

### `CypherGenerator`

Converts natural language queries to Cypher.

**Initialization**:

```python
generator = CypherGenerator(normalizer=EntityNormalizer())
```

**Intent Patterns**:

```python
intent_patterns = {
    "evidence_search": [
        r"효과적", r"효과가", r"개선", r"치료", r"결과",
        r"effective", r"improve", r"treatment", r"outcome"
    ],
    "comparison": [
        r"비교", r"차이", r"vs", r"versus", r"compare", r"difference"
    ],
    "hierarchy": [
        r"종류", r"분류", r"계층", r"type", r"category", r"hierarchy"
    ],
    "conflict": [
        r"논란", r"상충", r"일치하지", r"inconsistent", r"conflicting"
    ]
}
```

**Main Methods**:

```python
def extract_entities(self, query: str) -> dict:
    """Extract entities from natural language query.

    Returns:
        {
            "interventions": list[str],
            "outcomes": list[str],
            "pathologies": list[str],
            "anatomy": list[str],
            "sub_domain": str,
            "intent": str,
            "intent_confidence": float
        }
    """

def generate(self, query: str, entities: dict) -> tuple[str, dict]:
    """Generate parameterized Cypher query from natural language.

    Args:
        query: User query
        entities: Entities from extract_entities()

    Returns:
        Tuple of (cypher_query, params) — Cypher injection 방지를 위해
        엔티티 값은 $param으로 파라미터화됨 (v1.15.0)
    """
```

**Internal Methods**:

```python
def _detect_intent(self, query: str) -> QueryIntent:
    """Detect query intent using pattern matching."""

def _extract_anatomy(self, query: str) -> list[str]:
    """Extract anatomical locations (L1-L5, C1-C7, T1-T12)."""

def _extract_subdomain(self, query: str) -> Optional[str]:
    """Extract spine sub-domain (Degenerative, Deformity, Trauma, Tumor)."""

def _generate_evidence_search(
    self, interventions: list[str], outcomes: list[str], pathologies: list[str]
) -> tuple[str, dict]:
    """Generate evidence search Cypher with parameters."""

def _generate_comparison(
    self, interventions: list[str], outcomes: list[str]
) -> tuple[str, dict]:
    """Generate comparison Cypher with parameters."""

def _generate_hierarchy(self, interventions: list[str]) -> tuple[str, dict]:
    """Generate hierarchy traversal Cypher with parameters."""

def _generate_conflict(
    self, interventions: list[str], outcomes: list[str]
) -> tuple[str, dict]:
    """Generate conflict detection Cypher with parameters."""
```

**Example Usage**:

```python
generator = CypherGenerator()

# Extract entities
query = "OLIF가 VAS 개선에 효과적인가?"
entities = generator.extract_entities(query)
# {
#     "interventions": ["OLIF"],
#     "outcomes": ["VAS"],
#     "pathologies": [],
#     "intent": "evidence_search"
# }

# Generate parameterized Cypher (v1.15.0: returns tuple)
cypher, params = generator.generate(query, entities)
# cypher: """
# MATCH (i:Intervention {name: $intervention})-[a:AFFECTS]->(o:Outcome {name: $outcome})
# WHERE a.is_significant = true
# RETURN i.name, o.name, a.value, a.p_value, a.source_paper_id
# ORDER BY a.p_value
# """
# params: {"intervention": "OLIF", "outcome": "VAS"}

# Comparison query
query = "TLIF vs PLIF 융합률 비교"
entities = generator.extract_entities(query)
cypher, params = generator.generate(query, entities)
# Returns parameterized Cypher for comparing TLIF and PLIF on Fusion Rate

# Hierarchy query
query = "TLIF의 상위 수술법은?"
entities = generator.extract_entities(query)
cypher, params = generator.generate(query, entities)
# Returns parameterized Cypher for traversing IS_A relationships
```

**Intent Detection Examples**:

| Query | Detected Intent | Confidence |
|-------|----------------|------------|
| "OLIF가 VAS 개선에 효과적인가?" | evidence_search | 0.75 |
| "TLIF와 PLIF 비교" | comparison | 1.0 |
| "내시경 수술의 종류" | hierarchy | 0.66 |
| "OLIF 연구 결과가 일치하는가?" | conflict | 0.5 |

---

## response_synthesizer.py

Evidence-based answer generation from hybrid search results.

### Data Classes

#### `SynthesizedResponse`

Integrated response with evidence.

```python
@dataclass
class SynthesizedResponse:
    answer: str  # Main natural language answer
    evidence_summary: str  # Core statistics summary
    supporting_papers: list[str]  # APA citations
    confidence_score: float  # 0~1 based on evidence quality
    conflicts: list[str]  # Conflicting findings explained

    # Detailed information
    graph_evidences: list[str]  # Formatted statistical evidence
    vector_contexts: list[str]  # Background information
    metadata: dict  # Additional stats
```

### Evidence Level Descriptions

```python
EVIDENCE_LEVEL_DESCRIPTIONS = {
    "1a": "Level 1a (Meta-analysis/Systematic Review) - Highest quality",
    "1b": "Level 1b (RCT) - High quality",
    "2a": "Level 2a (Cohort Study) - Moderate quality",
    "2b": "Level 2b (Case-Control Study) - Moderate quality",
    "3": "Level 3 (Case Series) - Low quality",
    "4": "Level 4 (Expert Opinion) - Very low quality",
    "5": "Level 5 (Ungraded) - Not assessed"
}
```

### `ResponseSynthesizer`

Synthesizes evidence-based answers.

**Initialization**:

```python
synthesizer = ResponseSynthesizer(
    llm_client=GeminiClient(),
    use_llm_synthesis=True  # False for template-only mode
)
```

**Main Method**:

```python
async def synthesize(
    self,
    query: str,
    hybrid_results: list[HybridResult],
    max_evidences: int = 5,
    max_contexts: int = 3
) -> SynthesizedResponse:
    """Synthesize answer from hybrid search results.

    Process:
        1. Separate Graph vs Vector results
        2. Format Graph evidence (statistics, p-values)
        3. Format Vector context (background, discussion)
        4. Generate citations (APA style)
        5. Detect conflicts
        6. Calculate confidence score
        7. Generate LLM-based answer (or template)

    Args:
        query: Original question
        hybrid_results: Results from HybridRanker
        max_evidences: Max Graph evidence to include
        max_contexts: Max Vector contexts to include

    Returns:
        SynthesizedResponse with answer and metadata
    """
```

**Formatting Methods**:

```python
def format_graph_evidence(
    self, graph_results: list[HybridResult]
) -> list[str]:
    """Format Graph evidence with statistics.

    Example Output:
        [
            "TLIF improved Fusion Rate to 92% vs 85% (p=0.001, Level 1b)",
            "OLIF improved VAS by 3.2 points (95% CI: 2.1-4.3, p<0.001)"
        ]
    """

def format_vector_context(
    self, vector_results: list[HybridResult]
) -> list[str]:
    """Format Vector context for background.

    Example Output:
        [
            "Background: TLIF is a minimally invasive fusion technique...",
            "Discussion: Long-term outcomes show sustained improvement..."
        ]
    """

def generate_citations(
    self, hybrid_results: list[HybridResult]
) -> list[str]:
    """Generate APA-style citations.

    Example Output:
        [
            "Smith J, et al. (2024). TLIF for Lumbar Stenosis. Spine, 49(2), 123-130.",
            "Doe A, et al. (2023). OLIF outcomes. JBJS, 105(5), 456-465."
        ]
    """

def summarize_conflicts(
    self, graph_results: list[HybridResult]
) -> list[str]:
    """Detect and explain conflicting results.

    Example Output:
        [
            "Conflict: TLIF → Fusion Rate - Smith (2024) showed improvement (p=0.001), "
            "but Doe (2023) found no significant difference (p=0.12)"
        ]
    """
```

**Internal Methods**:

```python
def _calculate_confidence(
    self, hybrid_results: list[HybridResult]
) -> float:
    """Calculate confidence score (0~1).

    Factors:
        - Evidence level weights (1a=1.0, 5=0.1)
        - Statistical significance (p-value)
        - Number of supporting studies
        - Conflicts (reduce confidence)
    """

def _create_evidence_summary(
    self, graph_results: list[HybridResult], vector_results: list[HybridResult]
) -> str:
    """Create concise evidence summary."""

async def _synthesize_with_llm(
    self,
    query: str,
    graph_evidences: list[str],
    vector_contexts: list[str],
    conflicts: list[str]
) -> str:
    """Generate natural language answer using Gemini LLM."""

def _template_answer(
    self, query: str, graph_evidences: list[str], vector_contexts: list[str]
) -> str:
    """Generate template-based answer (no LLM)."""
```

**Example Usage**:

```python
synthesizer = ResponseSynthesizer()

# Synthesize answer
response = await synthesizer.synthesize(
    query="Is TLIF effective for improving fusion rate?",
    hybrid_results=hybrid_results,
    max_evidences=5,
    max_contexts=3
)

print(response.answer)
# "Based on Level 1b evidence, TLIF significantly improves fusion rates.
#  Smith et al. (2024) reported 92% fusion rate vs 85% control (p=0.001).
#  This is supported by meta-analysis data showing similar outcomes..."

print(f"Confidence: {response.confidence_score:.2f}")
# "Confidence: 0.87"

print("Evidence Summary:", response.evidence_summary)
# "3 high-quality studies (Level 1a-1b) support TLIF effectiveness.
#  Average fusion rate: 91.3% (range: 88-94%). All studies showed
#  statistical significance (p<0.01)."

print("Citations:", response.supporting_papers)
# ["Smith J, et al. (2024)...", "Doe A, et al. (2023)..."]

if response.conflicts:
    print("Conflicts:", response.conflicts)
    # ["Minor conflict: follow-up duration varies (12-24 months)"]
```

**Confidence Scoring**:

```python
# Evidence Level Weights
WEIGHTS = {
    "1a": 1.0,  # Meta-analysis
    "1b": 0.9,  # RCT
    "2a": 0.8,  # Cohort
    "2b": 0.7,  # Case-control
    "3": 0.5,   # Case series
    "4": 0.3,   # Expert opinion
    "5": 0.1    # Ungraded
}

# Confidence Formula
confidence = (
    avg_evidence_weight * 0.5 +
    significance_ratio * 0.3 +
    (1 - conflict_ratio) * 0.2
)
```

---

## Integration Example

Complete workflow using all orchestrator components:

```python
from src.graph.neo4j_client import Neo4jClient
from src.storage.vector_db import TieredVectorDB
from src.orchestrator.chain_builder import create_chain
from src.orchestrator.cypher_generator import CypherGenerator
from src.orchestrator.response_synthesizer import ResponseSynthesizer

async def complete_workflow():
    # 1. Initialize chain
    chain = await create_chain(
        neo4j_uri="bolt://localhost:7687",
        chromadb_path="./data/chromadb",
        gemini_api_key=os.getenv("GEMINI_API_KEY")
    )

    # 2. Execute QA chain
    query = "OLIF가 VAS 개선에 효과적인가?"
    result = await chain.invoke(query, mode="qa")

    print("=== Answer ===")
    print(result.answer)

    print("\n=== Sources ===")
    for source in result.sources[:3]:
        print(f"- {source.source_id} (score: {source.final_score:.3f})")

    print("\n=== Metadata ===")
    print(f"Graph results: {result.metadata.get('graph_count', 0)}")
    print(f"Vector results: {result.metadata.get('vector_count', 0)}")

    # 3. Conflict analysis
    conflict_query = "OLIF와 TLIF의 Fusion Rate 비교 결과가 일치하는가?"
    conflict_result = await chain.invoke(conflict_query, mode="conflict")

    print("\n=== Conflict Analysis ===")
    print(conflict_result.answer)

# Run
asyncio.run(complete_workflow())
```

---

## Best Practices

### 1. Use Appropriate Modes

```python
# Evidence search → QA mode
result = await chain.invoke("TLIF가 효과적인가?", mode="qa")

# Detect conflicts → Conflict mode
result = await chain.invoke("연구 결과가 일치하는가?", mode="conflict")

# Just retrieve → Retrieval mode
result = await chain.invoke("TLIF 관련 논문", mode="retrieval")
```

### 2. Configure Weights

```python
# Prefer Graph evidence (statistical)
config = ChainConfig(graph_weight=0.7, vector_weight=0.3)

# Prefer Vector context (background)
config = ChainConfig(graph_weight=0.4, vector_weight=0.6)

# Balanced
config = ChainConfig(graph_weight=0.5, vector_weight=0.5)
```

### 3. Handle Conflicts

```python
response = await synthesizer.synthesize(query, hybrid_results)

if response.conflicts:
    print("⚠️ Conflicting evidence found:")
    for conflict in response.conflicts:
        print(f"  - {conflict}")

    # Lower confidence when conflicts exist
    if response.confidence_score < 0.6:
        print("⚠️ Low confidence due to conflicts")
```

### 4. Validate Generated Cypher

```python
generator = CypherGenerator()
entities = generator.extract_entities(query)

# Validate extracted entities
if not entities["interventions"] and not entities["outcomes"]:
    print("⚠️ No medical entities extracted - query may be too vague")

# Check intent confidence
if entities["intent_confidence"] < 0.5:
    print(f"⚠️ Low intent confidence: {entities['intent']}")
```

---

## Testing

### Unit Tests

```bash
pytest tests/orchestrator/test_chain_builder.py
pytest tests/orchestrator/test_cypher_generator.py
pytest tests/orchestrator/test_response_synthesizer.py
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_end_to_end_qa():
    chain = await create_chain(...)

    result = await chain.invoke("TLIF 효과는?", mode="qa")

    assert result.answer
    assert len(result.sources) > 0
    assert result.metadata["graph_count"] > 0
```

---

## Related Documentation

- [Graph Module API](graph_module.md) - Neo4j operations
- [TRD v3 GraphRAG](../TRD_v3_GraphRAG.md) - Technical requirements
- [User Guide](../user_guide.md) - End-user documentation
