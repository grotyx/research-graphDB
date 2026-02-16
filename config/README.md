# Configuration System Quick Reference

## Files in This Directory

- **config.yaml** - Main configuration file (edit this to change system behavior)

## Quick Start

### 1. View Current Configuration

```bash
cat config/config.yaml
```

### 2. Edit Configuration

```bash
# Open in your editor
vim config/config.yaml
# Or
code config/config.yaml
```

### 3. Set Environment Variables

```bash
# Required
export GEMINI_API_KEY="your_api_key_here"

# Optional (config.yaml has defaults)
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_PASSWORD="<your-password>"
```

### 4. Use in Python Code

```python
from src.core.config import get_config

# Get full config
config = get_config()

# Access settings
print(config.neo4j.uri)
print(config.llm.model)
print(config.normalization.fuzzy_threshold)
```

## Common Configuration Tasks

### Change Neo4j Connection

```yaml
# config.yaml
neo4j:
  uri: bolt://your-server:7687
  username: your_username
  password: your_password
  database: your_database
```

### Tune Normalization Thresholds

```yaml
# config.yaml
normalization:
  fuzzy_threshold: 0.90        # Higher = stricter matching
  token_overlap_threshold: 0.85
  word_boundary_confidence: 0.98
```

### Adjust Search Behavior

```yaml
# config.yaml
search:
  default_top_k: 20           # Return more results
  tier1_boost: 2.0            # Increase tier 1 preference
```

### Change Hybrid Ranking Weights

```yaml
# config.yaml
ranker:
  default_graph_weight: 0.7   # Prefer graph results
  default_vector_weight: 0.3  # vs vector results
  significance_boost: 2.0     # Boost significant findings
```

### Modify LLM Settings

```yaml
# config.yaml
llm:
  model: gemini-2.5-flash-preview-05-20
  temperature: 0.0            # More deterministic
  max_tokens: 4096            # Shorter responses
  timeout: 30                 # Faster timeout
```

### Enable Debug Mode

```yaml
# config.yaml
logging:
  level: DEBUG                # Show all logs

development:
  debug: true                 # Enable debug features
```

## Environment-Specific Configs

### Development

```yaml
# config.yaml
neo4j:
  uri: ${NEO4J_URI:bolt://localhost:7687}

development:
  debug: true
  test_mode: false
```

```bash
# .env
NEO4J_URI=bolt://localhost:7687
GEMINI_API_KEY=dev_key
```

### Production

```yaml
# config.yaml (same file)
neo4j:
  uri: ${NEO4J_URI:bolt://production:7687}

development:
  debug: false
  test_mode: false
```

```bash
# .env (production server)
NEO4J_URI=bolt://production-server:7687
GEMINI_API_KEY=production_key
```

## Testing Configuration Changes

```bash
# Run tests to verify config works
python -m pytest tests/core/test_config.py -v

# Test with custom config
python -c "
from src.core.config import get_config
config = get_config()
print(f'Neo4j: {config.neo4j.uri}')
print(f'LLM: {config.llm.model}')
print(f'Fuzzy threshold: {config.normalization.fuzzy_threshold}')
"
```

## Configuration Validation

Before deploying, validate your config:

```python
from src.core.config import get_config

try:
    config = get_config()
    print("✓ Configuration loaded successfully")
    print(f"  Neo4j: {config.neo4j.uri}")
    print(f"  LLM: {config.llm.model}")
except Exception as e:
    print(f"✗ Configuration error: {e}")
```

## Common Mistakes

### ❌ Wrong: Hardcoded values in code

```python
threshold = 0.85  # Hardcoded!
```

### ✅ Right: Use config

```python
from src.core.config import get_threshold
threshold = get_threshold("fuzzy_threshold")
```

### ❌ Wrong: Missing environment variable

```yaml
api_key: ${GEMINI_API_KEY}  # No default!
```

### ✅ Right: Provide default

```yaml
api_key: ${GEMINI_API_KEY:default_value}
```

### ❌ Wrong: Load config in loop

```python
for item in items:
    config = get_config()  # Loads every iteration!
```

### ✅ Right: Load once

```python
config = get_config()  # Load once
for item in items:
    threshold = config.normalization.fuzzy_threshold
```

## Troubleshooting

### Config file not found

```
FileNotFoundError: config.yaml not found
```

**Solution**: Ensure `config/config.yaml` exists in project root.

### Environment variable not resolved

```yaml
uri: ${NEO4J_URI}  # Returns empty string
```

**Solution**: Either set environment variable OR provide default:
```yaml
uri: ${NEO4J_URI:bolt://localhost:7687}
```

### Import error

```
ImportError: cannot import name 'get_config'
```

**Solution**: Set PYTHONPATH:
```bash
export PYTHONPATH=./src
```

## Documentation

- **Full Documentation**: [CONFIG_SYSTEM.md](../docs/CONFIG_SYSTEM.md)
- **Implementation Summary**: [CONFIG_IMPLEMENTATION_SUMMARY.md](../docs/CONFIG_IMPLEMENTATION_SUMMARY.md)
- **Module API**: [src/core/config.py](../src/core/config.py)

## Support

For questions or issues:
1. Check [CONFIG_SYSTEM.md](../docs/CONFIG_SYSTEM.md) for detailed docs
2. Review [CONFIG_IMPLEMENTATION_SUMMARY.md](../docs/CONFIG_IMPLEMENTATION_SUMMARY.md) for examples
3. Run tests: `pytest tests/core/test_config.py -v`

## Version

**Config Version**: 3.1
**Last Updated**: 2025-12-05
