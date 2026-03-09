# Adaptive Hybrid Ranker

Dynamic query-type-based weighting system for hybrid Graph + Vector search results.

## Overview

The **Adaptive Hybrid Ranker** automatically adjusts the Graph/Vector search weighting based on query characteristics, ensuring optimal retrieval for different information needs.

### Key Features

- **Automatic Query Classification**: 5 query types (FACTUAL, COMPARATIVE, EXPLORATORY, EVIDENCE, PROCEDURAL)
- **Dynamic Weight Adjustment**: Query-specific Graph/Vector balance
- **Min-Max Score Normalization**: Fair comparison across different scales
- **Deduplication & Merging**: Intelligent combination of overlapping results
- **Override Support**: Manual weight adjustment for custom scenarios

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Adaptive Hybrid Ranker                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Query Classification                                    │
│     ┌─────────────────────────┐                             │
│     │   QueryClassifier       │                             │
│     │  • Pattern Matching     │                             │
│     │  • Priority Resolution  │                             │
│     │  • Confidence Scoring   │                             │
│     └───────────┬─────────────┘                             │
│                 ▼                                           │
│  2. Weight Selection                                        │
│     ┌─────────────────────────┐                             │
│     │  FACTUAL → 70/30        │                             │
│     │  COMPARATIVE → 80/20    │                             │
│     │  EXPLORATORY → 40/60    │                             │
│     │  EVIDENCE → 75/25       │                             │
│     │  PROCEDURAL → 30/70     │                             │
│     └───────────┬─────────────┘                             │
│                 ▼                                           │
│  3. Score Normalization                                     │
│     ┌─────────────────────────┐                             │
│     │  Min-Max Normalization  │                             │
│     │  Graph: [0, 1]          │                             │
│     │  Vector: [0, 1]         │                             │
│     └───────────┬─────────────┘                             │
│                 ▼                                           │
│  4. Weighted Combination                                    │
│     ┌─────────────────────────┐                             │
│     │  Final Score =          │                             │
│     │  graph_weight × graph + │                             │
│     │  vector_weight × vector │                             │
│     └───────────┬─────────────┘                             │
│                 ▼                                           │
│  5. Deduplication & Ranking                                 │
│     ┌─────────────────────────┐                             │
│     │  Merge by paper_id      │                             │
│     │  Sort by final_score    │                             │
│     └─────────────────────────┘                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Query Type Classification

### Pattern-Based Classification

| Query Type | Graph Weight | Vector Weight | Use Case |
|-----------|--------------|---------------|----------|
| **FACTUAL** | 70% | 30% | Specific facts, rates, values |
| **COMPARATIVE** | 80% | 20% | Treatment comparisons, A vs B |
| **EXPLORATORY** | 40% | 60% | Broad exploration, "what exists" |
| **EVIDENCE** | 75% | 25% | Statistical evidence, efficacy |
| **PROCEDURAL** | 30% | 70% | Techniques, procedures, "how-to" |

### Classification Examples

```python
from src.solver.adaptive_ranker import QueryClassifier, QueryType

classifier = QueryClassifier()

# FACTUAL (70% Graph, 30% Vector)
assert classifier.classify("What is the fusion rate of TLIF?") == QueryType.FACTUAL

# COMPARATIVE (80% Graph, 20% Vector)
assert classifier.classify("TLIF vs OLIF for stenosis") == QueryType.COMPARATIVE

# EXPLORATORY (40% Graph, 60% Vector)
assert classifier.classify("What treatments exist for stenosis?") == QueryType.EXPLORATORY

# EVIDENCE (75% Graph, 25% Vector)
assert classifier.classify("Is TLIF effective for disc herniation?") == QueryType.EVIDENCE

# PROCEDURAL (30% Graph, 70% Vector)
assert classifier.classify("How is UBE performed?") == QueryType.PROCEDURAL
```

### Pattern Definitions

**FACTUAL Patterns:**
- `what is (the) [rate|value|percentage|incidence]`
- `how [much|many|high|low]`
- `[fusion|complication|success] rate`

**COMPARATIVE Patterns:**
- `vs.|versus`
- `compare|comparison`
- `between X and Y`
- `X or Y for`

**EXPLORATORY Patterns:**
- `what [exist|are]`
- `options for`
- `treatments for`
- `types of`

**EVIDENCE Patterns:**
- `is X [effective|beneficial]`
- `does X [work|improve]`
- `evidence for`
- `p-value|effect size`

**PROCEDURAL Patterns:**
- `how is X performed`
- `how do you perform`
- `technique for`
- `steps of`

## Usage

### Basic Usage

```python
from src.solver.adaptive_ranker import AdaptiveHybridRanker

# Initialize ranker
ranker = AdaptiveHybridRanker()

# Prepare results
graph_results = [
    {
        "paper_id": "paper1",
        "title": "TLIF vs OLIF RCT",
        "score": 0.85,
        "evidence": graph_evidence_obj,  # GraphEvidence instance
        "paper": paper_node_obj,  # PaperNode instance
    }
]

vector_results = [
    VectorSearchResult(
        chunk_id="chunk1",
        document_id="paper1",
        title="TLIF vs OLIF RCT",
        score=0.88,
        content="...",
        tier="tier1",
        section="results",
        source_type="original",
        evidence_level="1b",
        # ... other fields
    )
]

# Adaptive ranking
results = ranker.rank(
    query="TLIF vs OLIF for stenosis",
    graph_results=graph_results,
    vector_results=vector_results
)

# Access results
for result in results:
    print(f"Paper: {result.title}")
    print(f"Score: {result.final_score:.3f}")
    print(f"Type: {result.query_type.value}")
    print(f"Graph: {result.graph_score:.3f}, Vector: {result.vector_score:.3f}")
```

### Override Weights

```python
# Custom weights (50/50 balance)
results = ranker.rank(
    query="TLIF vs OLIF",
    graph_results=graph_results,
    vector_results=vector_results,
    override_weights={"graph": 0.5, "vector": 0.5}
)
```

### Query Classification Only

```python
from src.solver.adaptive_ranker import QueryClassifier

classifier = QueryClassifier()

query = "What is the fusion rate of TLIF?"
query_type = classifier.classify(query)
confidence = classifier.get_confidence(query, query_type)

print(f"Type: {query_type.value}")
print(f"Confidence: {confidence:.2f}")
# Output: Type: factual, Confidence: 0.85
```

## Score Calculation

### 1. Score Normalization

**Min-Max Normalization:**
```
normalized_score = (score - min_score) / (max_score - min_score)
```

Applied separately to Graph and Vector results to ensure fair comparison.

### 2. Weighted Combination

```
final_score = graph_weight × normalized_graph_score +
              vector_weight × normalized_vector_score
```

### 3. Example Calculation

**Query:** "TLIF vs OLIF for stenosis" (COMPARATIVE → 80% Graph, 20% Vector)

**Raw Scores:**
- Paper A: Graph = 0.85, Vector = 0.75
- Paper B: Graph = 0.72, Vector = 0.88

**Normalized Scores:**
- Paper A: Graph = 1.0, Vector = 0.0
- Paper B: Graph = 0.0, Vector = 1.0

**Final Scores:**
- Paper A: 0.8 × 1.0 + 0.2 × 0.0 = **0.80**
- Paper B: 0.8 × 0.0 + 0.2 × 1.0 = **0.20**

**Ranking:** Paper A (0.80) > Paper B (0.20)

## Data Structures

### RankedResult

```python
@dataclass
class RankedResult:
    paper_id: str
    title: str
    graph_score: float          # Normalized Graph score
    vector_score: float         # Normalized Vector score
    final_score: float          # Weighted combination
    query_type: QueryType       # Classified query type
    metadata: dict              # Contains graph_weight, vector_weight

    # Optional detailed data
    evidence: Optional[GraphEvidence] = None
    paper: Optional[PaperNode] = None
    vector_result: Optional[VectorSearchResult] = None
```

### QueryType Enum

```python
class QueryType(Enum):
    FACTUAL = "factual"
    COMPARATIVE = "comparative"
    EXPLORATORY = "exploratory"
    EVIDENCE = "evidence"
    PROCEDURAL = "procedural"
```

## Performance Considerations

### Time Complexity

- **Query Classification**: O(P × Q) where P = patterns, Q = query length
- **Score Normalization**: O(N) where N = result count
- **Deduplication**: O(N) with hash map
- **Total**: O(N) for typical workloads

### Memory Usage

- **Compiled Patterns**: ~5 KB (cached regex)
- **Results**: ~1 KB per result
- **Typical**: <100 KB for 50 results

### Optimization Tips

1. **Reuse QueryClassifier**: Patterns are pre-compiled
2. **Batch Processing**: Process multiple queries with same classifier
3. **Limit Result Count**: Use top_k to reduce normalization overhead

## Testing

### Run Tests

```bash
PYTHONPATH=/path/to/project/src python -m pytest tests/solver/test_adaptive_ranker.py -v
```

### Test Coverage

- ✓ Query classification (9 tests)
- ✓ Adaptive ranking (11 tests)
- ✓ Data structures (3 tests)
- ✓ Integration (2 tests)
- ✓ Performance (2 tests)

**Total: 27 tests, 100% passing**

## Examples

### Example 1: Medical Query Comparison

```python
# COMPARATIVE query (Graph preferred)
query = "TLIF vs OLIF for stenosis"
results = ranker.rank(query, graph_results, vector_results)
# Result: Graph 80%, Vector 20%

# PROCEDURAL query (Vector preferred)
query = "How is UBE performed?"
results = ranker.rank(query, graph_results, vector_results)
# Result: Graph 30%, Vector 70%
```

### Example 2: Score Breakdown

```python
result = results[0]
print(result.get_score_breakdown())
# Output: "Final: 0.850 (Graph: 0.920, Vector: 0.650)"

if result.evidence:
    print(result.evidence.get_display_text())
    # Output: "TLIF improved Fusion Rate to 94.2% vs 87.5% (p=0.001)"
```

### Example 3: Custom Weight Strategy

```python
# Conservative approach: Balanced weights
results = ranker.rank(
    query=query,
    graph_results=graph_results,
    vector_results=vector_results,
    override_weights={"graph": 0.5, "vector": 0.5}
)

# Aggressive Graph preference
results = ranker.rank(
    query=query,
    graph_results=graph_results,
    vector_results=vector_results,
    override_weights={"graph": 0.9, "vector": 0.1}
)
```

## Demo

Run the comprehensive demo:

```bash
python examples/adaptive_ranker_demo.py
```

**Demo includes:**
1. Query Classification examples
2. Weight Adaptation visualization
3. Adaptive Ranking comparison
4. Override Weights demonstration
5. Score Breakdown analysis

## Integration with Existing System

### HybridRanker Migration

The `AdaptiveHybridRanker` can replace `HybridRanker` with minimal changes:

```python
# Before (HybridRanker)
from src.solver.hybrid_ranker import HybridRanker

ranker = HybridRanker(vector_db, neo4j_client)
results = await ranker.search(
    query=query,
    query_embedding=embedding,
    graph_weight=0.6,
    vector_weight=0.4
)

# After (AdaptiveHybridRanker)
from src.solver.adaptive_ranker import AdaptiveHybridRanker

ranker = AdaptiveHybridRanker()
results = ranker.rank(
    query=query,
    graph_results=graph_results,
    vector_results=vector_results
    # No manual weights needed - automatic!
)
```

## Future Enhancements

### v2.0 Roadmap

1. **Machine Learning Classifier**: Replace regex with trained model
2. **Context-Aware Weights**: Adjust based on user history
3. **Multi-Modal Queries**: Handle queries with multiple types
4. **Dynamic Threshold**: Learn optimal weights from user feedback
5. **A/B Testing Framework**: Measure weight impact on relevance

### Potential Improvements

- **Fuzzy Classification**: Confidence-weighted blending
- **Domain-Specific Patterns**: Spine-specific query patterns
- **User Feedback Loop**: Learn from click-through rates
- **Ensemble Methods**: Combine multiple classification strategies

## Troubleshooting

### Issue: Incorrect Query Classification

**Solution:** Check pattern priority and add custom patterns

```python
# Add custom pattern
classifier.PATTERNS[QueryType.FACTUAL].append(r"your_custom_pattern")
```

### Issue: Unexpected Weights

**Solution:** Use override_weights for manual control

```python
results = ranker.rank(
    query=query,
    graph_results=graph_results,
    vector_results=vector_results,
    override_weights={"graph": 0.7, "vector": 0.3}
)
```

### Issue: All Scores Zero

**Solution:** Check if results are empty or scores invalid

```python
# Debug
print(f"Graph results: {len(graph_results)}")
print(f"Vector results: {len(vector_results)}")
```

## References

- **HybridRanker**: `/path/to/project/src/solver/hybrid_ranker.py`
- **GraphResult**: `/path/to/project/src/solver/graph_result.py`
- **VectorDB**: `/path/to/project/src/storage/vector_db.py`
- **Tests**: `/path/to/project/tests/solver/test_adaptive_ranker.py`

## License

Part of Spine GraphRAG System v3.0
