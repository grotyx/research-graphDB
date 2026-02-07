# Cache Module

Comprehensive caching infrastructure for Spine GraphRAG system.

## Overview

The cache module provides multi-layer caching to improve performance:

1. **Query Cache**: LRU cache for Cypher queries
2. **Embedding Cache**: Persistent cache for text embeddings
3. **LLM Cache**: Response cache with semantic matching
4. **Semantic Cache**: Similar query matching

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CacheManager                             │
│  (Centralized cache management and coordination)             │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ QueryCache  │      │  Embedding  │      │  Semantic   │
│   (LRU)     │      │   Cache     │      │   Cache     │
│             │      │  (SQLite)   │      │ (LLM+Sim)   │
│ - Cypher    │      │             │      │             │
│ - General   │      │ - Text→Vec  │      │ - Similar   │
│ - TTL       │      │ - Persistent│      │   Queries   │
└─────────────┘      └─────────────┘      └─────────────┘
```

## Modules

### query_cache.py

LRU cache with TTL for frequent queries.

**Classes**:
- `QueryCache`: General LRU cache
- `CypherQueryCache`: Specialized for Neo4j Cypher queries

**Features**:
- LRU eviction policy
- TTL-based expiration
- Cache key generation
- Pattern-based invalidation
- Statistics tracking

**Usage**:
```python
from cache.query_cache import CypherQueryCache

cache = CypherQueryCache(max_size=1000, ttl_seconds=3600)

# Generate key
key = cache.generate_cypher_key(query, params)

# Get/Set
result = cache.get(key)
if result is None:
    result = await neo4j_client.run_query(query, params)
    cache.set(key, result)

# Statistics
stats = cache.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
```

### embedding_cache.py

Persistent SQLite cache for text embeddings.

**Features**:
- SQLite-based storage
- Text normalization
- Batch operations
- Model-specific caching
- Warmup with common terms

**Usage**:
```python
from cache.embedding_cache import EmbeddingCache

cache = EmbeddingCache(db_path="embeddings.db", ttl_days=30)

# Get/Set
embedding = cache.get(text, model_name="medbert")
if embedding is None:
    embedding = model.encode(text)
    cache.set(text, embedding, model_name="medbert")

# Batch operations
results = cache.get_batch(texts, model_name="medbert")

# Warmup
await cache.warmup(common_terms, embedding_function)
```

### semantic_cache.py

Semantic similarity matching for LLM responses.

**Features**:
- Cosine similarity matching
- Configurable threshold (default: 0.85)
- Falls back to exact match
- Operation-specific caching

**Usage**:
```python
from cache.semantic_cache import SemanticCache

cache = SemanticCache(
    llm_cache=llm_cache,
    embedding_cache=embedding_cache,
    similarity_threshold=0.85
)

# Get/Set
response = await cache.get(query, query_embedding, operation="summarize")
if response is None:
    response = await llm_generate(query)
    await cache.set(query, query_embedding, response, operation="summarize")
```

### cache_manager.py

Centralized cache management.

**Features**:
- Unified interface
- Configuration-driven
- Statistics aggregation
- Cleanup operations
- Warmup coordination

**Usage**:
```python
from cache.cache_manager import CacheManager, CacheConfig

config = CacheConfig(
    query_cache_size=1000,
    semantic_threshold=0.85
)
manager = CacheManager(config=config)

# Access caches
manager.query_cache.get(key)
manager.embedding_cache.get(text, model)
await manager.semantic_cache.get(query, embedding, operation)

# Statistics
stats = manager.get_all_stats()

# Cleanup
manager.cleanup_all()

# Invalidation
await manager.invalidate_on_data_update(node_label="Paper")
```

## Configuration

Cache behavior is controlled via `config/cache_config.yaml`:

```yaml
cache:
  enabled: true
  data_dir: "./data"

query_cache:
  enabled: true
  max_size: 1000
  ttl_seconds: 3600
  warmup_enabled: true
  warmup_queries: [...]

embedding_cache:
  enabled: true
  ttl_days: 30
  warmup_enabled: true
  warmup_terms: [...]

llm_cache:
  enabled: true
  ttl_hours: 168
  operation_ttl:
    section_classify: 720
    summarize: 168

semantic_cache:
  enabled: true
  similarity_threshold: 0.85
  max_entries_per_operation: 1000
```

## Management Script

Use `scripts/manage_cache.py` to manage caches:

```bash
# View statistics
python scripts/manage_cache.py stats

# Clear all caches
python scripts/manage_cache.py clear --type all

# Clean up expired entries
python scripts/manage_cache.py cleanup

# Warm up caches
python scripts/manage_cache.py warmup

# Monitor performance
python scripts/manage_cache.py monitor --interval 10
```

## Integration

### Neo4j Client

```python
from cache.integration_example import CachedNeo4jClient

cached_client = CachedNeo4jClient(neo4j_client, cache_manager.cypher_cache)

# Use normally - caching is transparent
result = await cached_client.run_query(query, params)
```

### Hybrid Ranker

```python
from cache.integration_example import CachedHybridRanker

cached_ranker = CachedHybridRanker(ranker, cache_manager.query_cache)

results = await cached_ranker.search(query, embedding, top_k=10)
```

### Embedding Model

```python
from cache.integration_example import CachedEmbeddingModel

cached_model = CachedEmbeddingModel(
    embedding_model, cache_manager.embedding_cache, model_name="medbert"
)

embedding = cached_model.encode(text)
```

## Performance

Expected performance improvements with caching:

| Operation | Without Cache | With Cache | Improvement |
|-----------|---------------|------------|-------------|
| Common Cypher Query | 50-100ms | 1-2ms | **50-100x** |
| Text Embedding | 10-50ms | 0.5-1ms | **20-50x** |
| LLM Response | 1-5s | 1-2ms | **500-5000x** |
| Similar Query (Semantic) | 1-5s | 1-2ms | **500-5000x** |

**Cache Hit Rates** (after warmup):
- Query Cache: 80-90%
- Embedding Cache: 95%+
- Semantic Cache: 60-70%

**Cost Savings**:
- LLM API calls: 70-80% reduction
- Embedding API calls: 90%+ reduction
- Overall latency: 30-50% reduction

## Cache Invalidation

Caches are invalidated on data updates:

```python
# After adding/updating papers
await cache_manager.invalidate_on_data_update(
    node_label="Paper",
    operation="summarize"
)

# After modifying taxonomy
await cache_manager.invalidate_on_data_update(
    node_label="Intervention"
)
```

## Statistics

Track cache performance:

```python
stats = cache_manager.get_all_stats()

# Output:
{
  "query_cache": {
    "hits": 450,
    "misses": 50,
    "hit_rate": "90.00%",
    "entries": 320,
    "evictions": 12
  },
  "embedding_cache": {
    "entries": 1250,
    "size_mb": 12.5,
    "hit_count": 3500,
    "hit_rate": "95.50%"
  },
  "semantic_cache": {
    "semantic_entries": 85,
    "semantic_operations": 4,
    "similarity_threshold": 0.85
  }
}
```

## Best Practices

1. **Enable warmup on startup**: Pre-populate caches with common queries/terms
2. **Monitor hit rates**: Adjust cache sizes and TTLs based on metrics
3. **Use appropriate TTLs**:
   - Short TTL (1 hour) for frequently changing data
   - Long TTL (7-30 days) for stable data
4. **Invalidate on updates**: Always invalidate affected caches after data modifications
5. **Configure per environment**:
   - Development: Shorter TTLs, smaller caches
   - Production: Longer TTLs, larger caches
6. **Regular cleanup**: Schedule daily cleanup of expired entries
7. **Semantic threshold tuning**: Start with 0.85, adjust based on false positive rate

## Troubleshooting

### Cache not working

Check configuration:
```python
stats = cache_manager.get_all_stats()
print(stats["config"])  # Ensure enabled=true
```

### Low hit rate

- Increase cache size
- Increase TTL
- Check if queries are parameterized consistently
- Enable warmup

### High memory usage

- Decrease cache sizes
- Decrease TTLs
- Run cleanup more frequently
- Use `clear` command to reset

### Stale data

- Decrease TTLs
- Add invalidation triggers
- Manual invalidation after updates

## Testing

Run cache tests:

```bash
# Unit tests
pytest tests/cache/test_query_cache.py -v
pytest tests/cache/test_embedding_cache.py -v
pytest tests/cache/test_semantic_cache.py -v

# Integration tests
pytest tests/integration/test_cache_integration.py -v

# Performance benchmarks
pytest tests/cache/test_cache_performance.py -v --benchmark
```

## Future Enhancements

- [ ] Redis backend for distributed caching
- [ ] Cache warming based on query logs
- [ ] Automatic TTL adjustment based on access patterns
- [ ] Cache preloading for predicted queries
- [ ] Compression for large embeddings
- [ ] Multi-level cache hierarchy (L1: memory, L2: SQLite, L3: Redis)

## References

- Configuration: `config/cache_config.yaml`
- Management: `scripts/manage_cache.py`
- Integration: `src/cache/integration_example.py`
- Tasks: `docs/Tasks_v3_GraphRAG.md` (Phase 6.2.2)
