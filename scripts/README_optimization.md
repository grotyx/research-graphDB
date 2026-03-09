# Neo4j Optimization Scripts

This directory contains scripts for optimizing Neo4j query performance through index management and benchmarking.

## Scripts Overview

### 1. optimize_neo4j.py

Comprehensive Neo4j index optimization tool that analyzes, creates, and validates indexes.

**Features**:
- Analyze current index state and identify gaps
- Create composite indexes for multi-property queries
- Create full-text indexes for natural language search
- Create relationship property indexes
- Profile common query patterns
- Generate optimization reports

**Usage**:

```bash
# Analyze current indexes (no changes)
python scripts/optimize_neo4j.py --analyze

# Create recommended indexes
python scripts/optimize_neo4j.py --create-indexes

# Profile common queries
python scripts/optimize_neo4j.py --profile-queries

# Full optimization workflow (analyze + create + profile)
python scripts/optimize_neo4j.py --full
```

**Output**:
- Console logs with detailed analysis
- Report saved to `data/optimization_report.txt`

### 2. benchmark_queries.py

Query performance benchmarking tool with before/after comparison.

**Features**:
- Benchmark 15 common query patterns across 6 categories
- Statistical analysis (mean, median, stddev, min, max)
- Before/after comparison
- Category-based performance breakdown
- Identify slowest queries

**Usage**:

```bash
# Run benchmark (5 iterations per query)
python scripts/benchmark_queries.py

# More iterations for accuracy
python scripts/benchmark_queries.py --iterations 10

# Compare with previous results
python scripts/benchmark_queries.py --compare data/benchmark_results.json
```

**Output**:
- Console summary with top slowest/fastest queries
- JSON results saved to `data/benchmark_results.json`

## Recommended Workflow

### Initial Setup (First Time)

1. **Baseline Benchmark**:
   ```bash
   python scripts/benchmark_queries.py --iterations 10
   ```
   This creates `data/benchmark_results.json` as baseline.

2. **Analyze Current State**:
   ```bash
   python scripts/optimize_neo4j.py --analyze
   ```
   Review recommended indexes in the report.

3. **Create Indexes**:
   ```bash
   python scripts/optimize_neo4j.py --create-indexes
   ```
   This creates all recommended indexes (safe, uses IF NOT EXISTS).

4. **Benchmark Again**:
   ```bash
   python scripts/benchmark_queries.py --iterations 10 --compare data/benchmark_results.json
   ```
   Compare performance improvements.

### Ongoing Monitoring

Run benchmarks periodically to detect performance regressions:

```bash
# Weekly benchmark
python scripts/benchmark_queries.py --iterations 5

# Monthly full optimization check
python scripts/optimize_neo4j.py --full
```

## Index Types

### Composite Indexes

Optimize multi-property filtering:

- `Paper(sub_domain, evidence_level)` - Common in list_papers()
- `Paper(year, sub_domain)` - Temporal analysis
- `Intervention(name, category)` - Categorization queries
- `Intervention(category, approach)` - Approach filtering
- `Outcome(name, type)` - Type-based queries

**Expected Improvement**: 2-5x speedup for filtered queries

### Full-Text Indexes

Enable natural language search:

- `paper_text_search` - Paper.title + Paper.abstract
- `pathology_search` - Pathology.name + Pathology.description
- `intervention_search` - Intervention.name + Intervention.full_name

**Expected Improvement**: 10-100x speedup for text search

**Usage Example**:
```cypher
CALL db.index.fulltext.queryNodes("paper_text_search", "lumbar stenosis surgery")
YIELD node, score
RETURN node.title, score
ORDER BY score DESC
LIMIT 10
```

### Relationship Indexes

Optimize relationship property filtering:

- `AFFECTS.p_value` - Statistical filtering (p < 0.05)
- `AFFECTS.is_significant` - Significance flag
- `AFFECTS.direction` - Improvement direction
- `STUDIES.is_primary` - Primary pathology
- `INVESTIGATES.is_comparison` - Comparative studies

**Expected Improvement**: 3-10x speedup for statistical filtering

## Benchmark Categories

### 1. Hierarchy Traversal (3 queries)
- TLIF ancestors (IS_A relationship traversal)
- UBE children (reverse hierarchy)
- All fusion types enumeration

### 2. Evidence Search (3 queries)
- VAS improvements with significance
- All significant effects (p<0.05)
- TLIF outcomes aggregation

### 3. Conflict Detection (2 queries)
- OLIF contradictions
- All contradictory findings

### 4. Paper Filtering (3 queries)
- Degenerative RCTs
- High-quality evidence (1a, 1b)
- Recent deformity studies

### 5. Relationship Traversal (2 queries)
- Lumbar stenosis treatment paths
- Paper citation networks

### 6. Aggregate Queries (2 queries)
- Intervention evidence counts
- Papers by sub-domain statistics

## Performance Targets

Based on typical graph sizes (100-10,000 papers):

| Query Type | Target Time | With Indexes |
|------------|-------------|--------------|
| Single node lookup | <5ms | <2ms |
| Hierarchy traversal | <20ms | <10ms |
| Evidence search | <50ms | <15ms |
| Conflict detection | <100ms | <30ms |
| Paper filtering | <30ms | <10ms |
| Aggregate queries | <100ms | <40ms |

## Troubleshooting

### Indexes Not Created

**Error**: "Failed to create index: already exists"
- **Solution**: This is expected and safe. The script uses IF NOT EXISTS.

**Error**: "Syntax error near 'CREATE INDEX'"
- **Solution**: Requires Neo4j 5.0+. Check version with `CALL dbms.components()`.

### Slow Queries After Optimization

**Possible Causes**:
1. Indexes still building (check `SHOW INDEXES` for state)
2. Query not using indexes (check with `EXPLAIN` or `PROFILE`)
3. Cold cache (first query after restart is slower)

**Solutions**:
```cypher
-- Check index state
SHOW INDEXES
YIELD name, state, populationPercent
WHERE state <> 'ONLINE'

-- Warm up indexes
MATCH (n:Paper) RETURN count(n)
MATCH (n:Intervention) RETURN count(n)
MATCH ()-[r:AFFECTS]->() RETURN count(r)
```

### Benchmark Variance

High standard deviation in benchmark results:
- Increase iterations: `--iterations 20`
- Run during off-peak hours
- Check for background processes
- Restart Neo4j to clear cache

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Neo4j Performance Test

on: [push, pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Start Neo4j
        run: docker-compose up -d neo4j

      - name: Run Benchmark
        run: |
          python scripts/benchmark_queries.py --iterations 5

      - name: Check Performance
        run: |
          # Fail if average query time > 100ms
          python -c "
          import json
          results = json.load(open('data/benchmark_results.json'))
          avg_time = results['total_time_ms'] / len(results['benchmarks'])
          assert avg_time < 100, f'Performance regression: {avg_time}ms'
          "
```

## Advanced Usage

### Custom Query Benchmarking

Edit `benchmark_queries.py` and add to `_get_benchmark_queries()`:

```python
(
    "Your Query Name",
    "your_category",
    """
    MATCH (n:YourNode)
    WHERE n.property = 'value'
    RETURN n
    """
)
```

### Custom Index Creation

Edit `optimize_neo4j.py` or add directly in Neo4j:

```cypher
-- Custom composite index
CREATE INDEX your_custom_idx IF NOT EXISTS
FOR (n:YourNode)
ON (n.prop1, n.prop2)

-- Custom relationship index
CREATE INDEX your_rel_idx IF NOT EXISTS
FOR ()-[r:YOUR_REL]-()
ON (r.your_property)
```

## References

- [Neo4j Index Documentation](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Performance Tuning](https://neo4j.com/docs/operations-manual/current/performance/)
- [Spine GraphRAG TRD](../docs/TRD_v3_GraphRAG.md)
- [Tasks v3](../docs/Tasks_v3_GraphRAG.md)

## Support

For issues or questions:
1. Check Neo4j logs: `docker-compose logs neo4j`
2. Verify environment variables in `.env`
3. Review optimization report in `data/optimization_report.txt`
4. Check Tasks document for Phase 6.2.1 notes
