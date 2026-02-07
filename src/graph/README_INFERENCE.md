# Inference Rules Module

## Overview

The Inference Rules module adds **reasoning capabilities** to the Neo4j graph database through Cypher-based inference rules. This enables:

- **Transitive relationships**: Automatically infer relationships through hierarchy (e.g., if A IS_A B and B IS_A C, then A IS_A C)
- **Intervention comparability**: Find interventions that can be meaningfully compared
- **Evidence aggregation**: Combine evidence across the intervention hierarchy
- **Conflict detection**: Identify contradictory research findings

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    InferenceEngine                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────┐     ┌──────────────────────┐        │
│  │  InferenceRule    │     │  Cypher Templates    │        │
│  │  - name           │────▶│  - $parameter syntax │        │
│  │  - rule_type      │     │  - Neo4j execution   │        │
│  │  - parameters     │     └──────────────────────┘        │
│  │  - confidence     │                                     │
│  └───────────────────┘                                     │
│                                                             │
│  ┌──────────────────────────────────────────────────┐      │
│  │         12 Predefined Rules                      │      │
│  │  • TRANSITIVE_HIERARCHY                          │      │
│  │  • TRANSITIVE_DESCENDANTS                        │      │
│  │  • TRANSITIVE_TREATMENT                          │      │
│  │  • COMPARABLE_SIBLINGS                           │      │
│  │  • COMPARABLE_BY_CATEGORY                        │      │
│  │  • COMPARISON_PAPERS                             │      │
│  │  • AGGREGATE_EVIDENCE                            │      │
│  │  • AGGREGATE_EVIDENCE_BY_PATHOLOGY               │      │
│  │  • COMBINED_OUTCOMES                             │      │
│  │  • CONFLICT_DETECTION                            │      │
│  │  • CROSS_INTERVENTION_CONFLICTS                  │      │
│  │  • INDIRECT_TREATMENT                            │      │
│  └──────────────────────────────────────────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
import asyncio
from graph.neo4j_client import Neo4jClient
from graph.inference_rules import InferenceEngine

async def main():
    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Find ancestors in hierarchy
            ancestors = await engine.get_ancestors("TLIF")
            for ancestor in ancestors:
                print(f"{ancestor['ancestor']} (distance: {ancestor['distance']})")

            # Find comparable interventions
            comparable = await engine.get_comparable_interventions("TLIF")
            for comp in comparable:
                print(f"{comp['comparable']} via {comp['shared_category']}")

            # Aggregate evidence
            evidence = await engine.aggregate_evidence("TLIF", "Fusion Rate")
            for ev in evidence:
                print(f"{ev['intervention']}: {ev['direction']} (p={ev['p_value']})")

asyncio.run(main())
```

### Demo Script

Run the comprehensive demonstration:

```bash
python scripts/demo_inference_engine.py
```

## Inference Rules

### 1. Transitive Hierarchy

**Purpose**: Find all ancestors or descendants through IS_A relationships.

**Use Case**: "What are all the parent categories of TLIF?"

```python
# Get ancestors (parents, grandparents, etc.)
ancestors = await engine.get_ancestors("TLIF")
# Result: ["Interbody Fusion", "Fusion Surgery"]

# Get descendants (children, grandchildren, etc.)
descendants = await engine.get_descendants("Fusion Surgery")
# Result: ["Interbody Fusion", "TLIF", "PLIF", "MIS-TLIF", ...]
```

**Confidence**: 1.0 (Direct relationship)

**Cypher Pattern**:
```cypher
MATCH path = (child:Intervention {name: $intervention})-[:IS_A*1..5]->(ancestor)
RETURN ancestor, length(path) as distance
```

### 2. Comparability Rules

**Purpose**: Find interventions that can be meaningfully compared.

**Use Cases**:
- "What interventions are comparable to TLIF for a study design?"
- "Find all fusion techniques with similar characteristics"

```python
# Strict: Same parent category
comparable_strict = await engine.get_comparable_interventions("TLIF", strict=True)
# Result: ["PLIF", "ALIF", "OLIF", "LLIF"] (all Interbody Fusion)

# Broad: Same category
comparable_broad = await engine.get_comparable_interventions("TLIF", strict=False)
# Result: Includes all fusion techniques

# Find comparison papers
papers = await engine.find_comparison_studies("TLIF")
# Result: Papers that compare TLIF with other interventions
```

**Confidence**:
- COMPARABLE_SIBLINGS: 0.9 (Same parent)
- COMPARABLE_BY_CATEGORY: 0.7 (Same category)

### 3. Evidence Aggregation

**Purpose**: Combine evidence across the intervention hierarchy.

**Use Cases**:
- "What's the evidence for TLIF improving Fusion Rate, including parent categories?"
- "Show all outcomes for UBE across all studies"

```python
# Aggregate by specific outcome
evidence = await engine.aggregate_evidence("TLIF", "Fusion Rate")
# Returns evidence from TLIF, Interbody Fusion, Fusion Surgery

# Aggregate by pathology
evidence_path = await engine.aggregate_evidence_by_pathology(
    "TLIF", "Lumbar Stenosis"
)
# Returns all outcomes for TLIF treating Lumbar Stenosis

# Get all outcomes
outcomes = await engine.get_all_outcomes("UBE")
# Returns all outcome measures with evidence lists
```

**Confidence**:
- Direct intervention: 1.0
- Parent (distance=1): 0.9
- Grandparent (distance=2): 0.8

### 4. Conflict Detection

**Purpose**: Identify contradictory research findings.

**Use Cases**:
- "Are there conflicting results for UBE → VAS?"
- "Which interventions disagree on the effect on ODI?"

```python
# Detect conflicts for specific intervention-outcome
conflicts = await engine.detect_conflicts("UBE", "VAS")
# Returns pairs of papers with opposite directions (improved vs worsened)

# Cross-intervention conflicts
cross_conflicts = await engine.detect_cross_intervention_conflicts("VAS")
# Returns conflicting evidence between different interventions
```

**Confidence**: 1.0 (Direct evidence comparison)

### 5. Indirect Treatment

**Purpose**: Infer treatment relationships via hierarchy.

**Use Case**: "What interventions can treat Lumbar Stenosis, including via parent categories?"

```python
# Direct + indirect treatments
indirect = await engine.find_indirect_treatments("Lumbar Stenosis")
# Returns interventions that inherit TREATS from parents

# Infer treatments for intervention
treatments = await engine.infer_treatments("TLIF")
# Returns pathologies treated by TLIF or its parents
```

**Confidence**: 0.7 (Indirect relationship)

## Rule Types

| Type | Description | Example Rules |
|------|-------------|---------------|
| `TRANSITIVE_HIERARCHY` | Transitive closure of IS_A | TRANSITIVE_HIERARCHY, TRANSITIVE_DESCENDANTS |
| `TRANSITIVE_TREATMENT` | Inherited treatment relationships | TRANSITIVE_TREATMENT, INDIRECT_TREATMENT |
| `COMPARABLE_SIBLINGS` | Comparability analysis | COMPARABLE_SIBLINGS, COMPARABLE_BY_CATEGORY |
| `COMPARISON_PAPERS` | Research comparisons | COMPARISON_PAPERS |
| `AGGREGATE_EVIDENCE` | Evidence combining | AGGREGATE_EVIDENCE, AGGREGATE_EVIDENCE_BY_PATHOLOGY, COMBINED_OUTCOMES |
| `CONFLICT_DETECTION` | Contradiction finding | CONFLICT_DETECTION, CROSS_INTERVENTION_CONFLICTS |

## Confidence Weights

Confidence weights indicate how reliable the inferred relationship is:

| Weight | Meaning | Examples |
|--------|---------|----------|
| 1.0 | Direct evidence | TRANSITIVE_HIERARCHY, COMPARISON_PAPERS, CONFLICT_DETECTION |
| 0.9 | Very high confidence | COMPARABLE_SIBLINGS, AGGREGATE_EVIDENCE |
| 0.8-0.85 | High confidence | TRANSITIVE_TREATMENT, AGGREGATE_EVIDENCE_BY_PATHOLOGY |
| 0.7 | Moderate confidence | COMPARABLE_BY_CATEGORY, INDIRECT_TREATMENT |

These weights can be used to rank or filter results based on confidence.

## Advanced Usage

### Custom Rules

Create your own inference rules:

```python
from graph.inference_rules import InferenceRule, InferenceRuleType

# Define custom rule
MY_RULE = InferenceRule(
    name="my_custom_rule",
    rule_type=InferenceRuleType.TRANSITIVE_HIERARCHY,
    description="Find interventions with same approach",
    cypher_template="""
    MATCH (i:Intervention {name: $intervention})
    MATCH (other:Intervention)
    WHERE other.approach = i.approach AND other.name <> $intervention
    RETURN other.name as similar, other.approach as approach
    """,
    parameters=["intervention"],
    confidence_weight=0.8,
)

# Use with engine
engine.rules["my_custom_rule"] = MY_RULE
results = await engine.execute_rule("my_custom_rule", intervention="TLIF")
```

### Rule Inspection

Inspect available rules:

```python
# Get specific rule
rule = engine.get_rule("transitive_hierarchy")
print(f"Confidence: {rule.confidence_weight}")
print(f"Parameters: {rule.parameters}")

# List all rules
all_rules = engine.list_rules()

# Filter by type
hierarchy_rules = engine.list_rules(InferenceRuleType.TRANSITIVE_HIERARCHY)
```

### Low-level API

Execute rules directly:

```python
# Execute any rule with parameters
results = await engine.execute_rule(
    "aggregate_evidence",
    intervention="TLIF",
    outcome="Fusion Rate"
)

# Validate parameters before execution
rule = engine.get_rule("aggregate_evidence")
try:
    cypher = rule.generate_cypher(intervention="TLIF")  # Missing 'outcome'
except ValueError as e:
    print(f"Missing parameters: {e}")
```

## Integration with Graph Search

Combine inference with graph search for powerful queries:

```python
from graph.graph_search import GraphSearch
from graph.inference_rules import InferenceEngine

async with Neo4jClient() as client:
    search = GraphSearch(client)
    engine = InferenceEngine(client)

    # 1. Find effective interventions
    results = await search.search_effective_interventions("VAS")

    # 2. For each intervention, get comparable alternatives
    for result in results:
        intervention = result['intervention']
        comparable = await engine.get_comparable_interventions(intervention)
        print(f"{intervention} is comparable to: {[c['comparable'] for c in comparable]}")

    # 3. Aggregate evidence across hierarchy
    for intervention in interventions:
        evidence = await engine.aggregate_evidence(intervention, "VAS")
        print(f"Evidence for {intervention}: {len(evidence)} studies")
```

## Performance Considerations

### Query Optimization

- **Transitive queries** are limited to 5 levels to prevent excessive computation
- **Indexes** on `name`, `category`, `approach` properties optimize rule execution
- **Distinct** and **limit** clauses reduce result set size

### Caching Strategies

For frequently used queries, consider caching:

```python
from functools import lru_cache

class CachedInferenceEngine(InferenceEngine):
    @lru_cache(maxsize=128)
    async def get_ancestors_cached(self, intervention: str):
        return await self.get_ancestors(intervention)
```

### Batch Operations

Process multiple interventions efficiently:

```python
import asyncio

interventions = ["TLIF", "PLIF", "ALIF", "OLIF"]

# Run in parallel
tasks = [
    engine.get_ancestors(intervention)
    for intervention in interventions
]
results = await asyncio.gather(*tasks)
```

## Testing

Run inference rules tests:

```bash
# Unit tests (no Neo4j required)
PYTHONPATH=./src python -m pytest tests/graph/test_inference_rules.py -v -k "not integration"

# Integration tests (requires Neo4j)
docker-compose up -d neo4j
sleep 30  # Wait for Neo4j
PYTHONPATH=./src python -m pytest tests/graph/test_inference_rules.py -v -k "integration"
```

## Examples

### Example 1: Research Design

Find comparable interventions for a systematic review:

```python
# Goal: Design a systematic review comparing fusion techniques
async def design_systematic_review(target_intervention: str):
    async with InferenceEngine(client) as engine:
        # Get comparable interventions
        comparable = await engine.get_comparable_interventions(
            target_intervention,
            strict=False
        )

        # Find existing comparison papers
        papers = await engine.find_comparison_studies(target_intervention)

        # Identify gaps
        compared_interventions = set()
        for paper in papers:
            compared_interventions.update(paper['compared_with'])

        gaps = [
            c['comparable']
            for c in comparable
            if c['comparable'] not in compared_interventions
        ]

        return {
            "target": target_intervention,
            "comparable": comparable,
            "existing_comparisons": papers,
            "research_gaps": gaps,
        }

result = await design_systematic_review("TLIF")
print(f"Research gaps: {result['research_gaps']}")
```

### Example 2: Evidence Synthesis

Synthesize evidence across hierarchy:

```python
async def synthesize_evidence(intervention: str, outcome: str):
    async with InferenceEngine(client) as engine:
        # Get aggregated evidence
        evidence = await engine.aggregate_evidence(intervention, outcome)

        # Detect conflicts
        conflicts = await engine.detect_conflicts(intervention, outcome)

        # Organize by hierarchy distance
        direct_evidence = [e for e in evidence if e['hierarchy_distance'] == 0]
        parent_evidence = [e for e in evidence if e['hierarchy_distance'] == 1]
        indirect_evidence = [e for e in evidence if e['hierarchy_distance'] > 1]

        return {
            "direct": direct_evidence,
            "parent": parent_evidence,
            "indirect": indirect_evidence,
            "conflicts": conflicts,
            "total_studies": len(evidence),
            "has_conflicts": len(conflicts) > 0,
        }

synthesis = await synthesize_evidence("TLIF", "Fusion Rate")
print(f"Direct evidence: {len(synthesis['direct'])} studies")
print(f"Conflicts detected: {synthesis['has_conflicts']}")
```

## Troubleshooting

### No results returned

**Possible causes**:
1. Taxonomy not initialized: `await client.initialize_schema()`
2. No data ingested: Upload papers via Streamlit UI
3. No relationships created: Check `relationship_builder.py` is called

**Debug**:
```python
# Check taxonomy
async with Neo4jClient() as client:
    result = await client.run_query("MATCH (i:Intervention) RETURN count(i) as count")
    print(f"Interventions: {result[0]['count']}")  # Should be >20
```

### Slow queries

**Optimize**:
1. Reduce transitive depth: Edit `*1..5` to `*1..3` in rule
2. Add LIMIT clause to rule template
3. Ensure indexes are created

## References

- **Neo4j Cypher Manual**: https://neo4j.com/docs/cypher-manual/current/
- **Graph Schema**: `src/graph/spine_schema.py`
- **Graph Search**: `src/graph/graph_search.py`
- **Relationship Builder**: `src/graph/relationship_builder.py`

## Changelog

### 2025-12-05
- Initial implementation of inference rules
- 12 predefined rules covering hierarchy, comparability, evidence, conflicts
- Comprehensive test suite
- Demo script and documentation
