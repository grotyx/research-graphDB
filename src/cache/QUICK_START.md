# Cache Module - Quick Start Guide

## 5-Minute Setup

### 1. Initialize Cache Manager

```python
from src.cache.cache_manager import CacheManager, CacheConfig

# Use default config
manager = CacheManager()

# Or with custom config
config = CacheConfig(
    query_cache_size=1000,
    query_cache_ttl=3600,
    semantic_threshold=0.85
)
manager = CacheManager(config=config, data_dir="data")
```

### 2. Wrap Your Components

```python
from src.cache.integration_example import (
    CachedNeo4jClient,
    CachedHybridRanker,
    CachedEmbeddingModel
)

# Wrap Neo4j client
from src.graph.neo4j_client import Neo4jClient
neo4j = Neo4jClient()
cached_neo4j = CachedNeo4jClient(neo4j, manager.cypher_cache)

# Wrap embedding model
from src.core.embedding import get_embedding_model
model = get_embedding_model()
cached_model = CachedEmbeddingModel(model, manager.embedding_cache)

# Wrap hybrid ranker
from src.solver.hybrid_ranker import HybridRanker
ranker = HybridRanker(vector_db, cached_neo4j)
cached_ranker = CachedHybridRanker(ranker, manager.query_cache)
```

### 3. Use Normally

```python
# Neo4j queries - automatically cached
result = await cached_neo4j.run_query("MATCH (n:Paper) RETURN n LIMIT 10")

# Text embeddings - automatically cached
embedding = cached_model.encode("lumbar stenosis")

# Search results - automatically cached
results = await cached_ranker.search(query, embedding, top_k=10)
```

### 4. Monitor Performance

```bash
# View statistics
python scripts/manage_cache.py stats

# Output:
# [Query Cache]
#   Entries: 320
#   Hits: 450
#   Misses: 50
#   Hit Rate: 90.00%
#
# [Embedding Cache]
#   Entries: 1250
#   Hit Rate: 95.50%
```

## Common Operations

### Warm Up Caches

```bash
# Pre-populate with common queries/terms
python scripts/manage_cache.py warmup
```

### Clear Caches

```bash
# Clear all
python scripts/manage_cache.py clear --type all --force

# Clear specific cache
python scripts/manage_cache.py clear --type query --force
python scripts/manage_cache.py clear --type embedding --force
```

### Cleanup Expired Entries

```bash
python scripts/manage_cache.py cleanup
```

### Monitor in Real-Time

```bash
python scripts/manage_cache.py monitor --interval 10
```

## Configuration

Edit `config/cache_config.yaml`:

```yaml
cache:
  enabled: true  # Master switch

query_cache:
  enabled: true
  max_size: 1000
  ttl_seconds: 3600  # 1 hour

embedding_cache:
  enabled: true
  ttl_days: 30

semantic_cache:
  enabled: true
  similarity_threshold: 0.85
```

## Cache Invalidation

After data updates:

```python
# Invalidate affected caches
await manager.invalidate_on_data_update(
    node_label="Paper",      # Node type updated
    operation="summarize"    # LLM operation to invalidate
)
```

## Performance Tips

1. **Enable warmup** - Pre-populate on startup
2. **Monitor hit rates** - Aim for >80%
3. **Adjust TTLs** - Balance freshness vs performance
4. **Use batch operations** - More efficient than individual calls
5. **Clear on schema changes** - After major updates

## Troubleshooting

### Low hit rate

```python
# Check stats
stats = manager.get_all_stats()
print(stats["query_cache"]["hit_rate"])

# Solutions:
# - Increase cache size
# - Increase TTL
# - Enable warmup
```

### High memory usage

```bash
# Clear caches
python scripts/manage_cache.py clear --type all --force

# Reduce cache sizes in config/cache_config.yaml
query_cache:
  max_size: 500  # Reduce from 1000
```

### Stale data

```python
# Invalidate after updates
await manager.invalidate_on_data_update(node_label="Paper")

# Or reduce TTL in config
query_cache:
  ttl_seconds: 1800  # 30 minutes instead of 1 hour
```

## API Reference

### CacheManager

```python
manager.query_cache          # QueryCache instance
manager.cypher_cache         # CypherQueryCache instance
manager.embedding_cache      # EmbeddingCache instance
manager.semantic_cache       # SemanticCache instance

manager.get_all_stats()      # Get statistics from all caches
manager.cleanup_all()        # Clean expired entries
manager.clear_all()          # Clear all caches
manager.warmup(...)          # Warm up caches
```

### QueryCache

```python
cache.get(key)               # Get cached value
cache.set(key, value)        # Set cached value
cache.invalidate(key)        # Invalidate specific entry
cache.invalidate_pattern(pattern)  # Invalidate by pattern
cache.cleanup_expired()      # Remove expired entries
cache.get_stats()            # Get cache statistics
```

### EmbeddingCache

```python
cache.get(text, model_name)  # Get cached embedding
cache.set(text, embedding, model_name)  # Set embedding
cache.get_batch(texts, model_name)      # Batch get
cache.set_batch(dict, model_name)       # Batch set
cache.warmup(terms, embed_fn)           # Warm up cache
cache.get_stats()            # Get statistics
```

## Full Example

```python
import asyncio
from src.cache.cache_manager import CacheManager
from src.cache.integration_example import *

async def main():
    # 1. Initialize
    manager = CacheManager()

    # 2. Wrap components
    neo4j = Neo4jClient()
    cached_neo4j = CachedNeo4jClient(neo4j, manager.cypher_cache)

    # 3. Warm up
    await manager.warmup(neo4j_client=cached_neo4j)

    # 4. Use with caching
    result = await cached_neo4j.run_query("MATCH (n:Paper) RETURN count(n)")

    # 5. Check stats
    stats = manager.get_all_stats()
    print(f"Hit rate: {stats['query_cache']['hit_rate']}")

    # 6. Cleanup
    manager.cleanup_all()

if __name__ == "__main__":
    asyncio.run(main())
```

## Next Steps

- Read full documentation: `src/cache/README.md`
- See integration examples: `src/cache/integration_example.py`
- Customize config: `config/cache_config.yaml`
- Run tests: `pytest tests/cache/ -v`

## Support

For issues or questions:
- Check `src/cache/README.md` for detailed docs
- Review `src/cache/integration_example.py` for usage patterns
- See `docs/Tasks_v3_GraphRAG.md` Phase 6.2.2 for implementation details
