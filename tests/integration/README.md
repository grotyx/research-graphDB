# Integration Test Suite

Comprehensive integration testing suite for Spine GraphRAG v3.0.

## Overview

This suite tests the complete pipeline from PDF processing to response generation, including:
- End-to-End pipeline testing
- Real-world scenario validation
- Performance benchmarking
- Component integration

## Test Structure

```
tests/integration/
├── conftest.py                  # Shared fixtures
├── test_e2e_pipeline.py         # End-to-End tests
├── test_scenarios.py            # Scenario-based tests
├── test_performance.py          # Performance benchmarks
└── README.md                    # This file

tests/fixtures/
├── sample_papers.py             # Sample data
├── mock_neo4j_responses.py      # Mock Neo4j responses
└── __init__.py
```

## Test Categories

### 1. E2E Pipeline Tests (`test_e2e_pipeline.py`)

Tests complete data flow through the system:

- **TestE2EPipeline**: Full pipeline with QA/retrieval/conflict modes
- **TestPDFToGraphPipeline**: PDF processing → Graph storage
- **TestGraphToSearchPipeline**: Graph queries → Search results
- **TestHybridSearchPipeline**: Graph + Vector hybrid search
- **TestResponseGenerationPipeline**: Hybrid results → LLM response
- **TestPipelineIntegration**: Real service integration tests (skip by default)

### 2. Scenario Tests (`test_scenarios.py`)

Real-world usage scenarios:

1. **Scenario 1**: Find evidence for TLIF effectiveness on fusion rate
2. **Scenario 2**: Compare UBE vs Open surgery for VAS improvement
3. **Scenario 3**: Get intervention hierarchy for Endoscopic Surgery
4. **Scenario 4**: Detect conflicting results for OLIF outcomes

Each scenario tests:
- Entity extraction
- Hybrid search
- Result ranking
- Response quality

### 3. Performance Tests (`test_performance.py`)

Performance benchmarks and metrics:

- **Query response times**: Single/multiple query latency
- **Search latency**: Graph vs Vector search timing
- **Ranking performance**: Varying data sizes (10/100/1000 results)
- **Throughput**: Concurrent query handling
- **Memory usage**: Result object footprint

## Running Tests

### Install Dependencies

```bash
pip install pytest pytest-asyncio pytest-mock
```

### Run All Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/integration/ --cov=src --cov-report=html

# Run only fast tests (exclude slow benchmarks)
pytest tests/integration/ -v -m "not slow"
```

### Run Specific Test Files

```bash
# E2E pipeline tests
pytest tests/integration/test_e2e_pipeline.py -v

# Scenario tests
pytest tests/integration/test_scenarios.py -v

# Performance benchmarks
pytest tests/integration/test_performance.py -v
```

### Run Specific Test Classes

```bash
# Test specific scenario
pytest tests/integration/test_scenarios.py::TestScenario1_TLIFFusionEvidence -v

# Test performance metrics
pytest tests/integration/test_performance.py::TestQueryResponseTime -v
```

### Run with Markers

```bash
# Run only integration tests
pytest -v -m integration

# Run only benchmark tests
pytest -v -m benchmark

# Run slow tests (performance benchmarks)
pytest -v -m slow

# Exclude slow tests
pytest -v -m "not slow"
```

## Test Markers

Tests use pytest markers for categorization:

- `@pytest.mark.integration`: Integration test requiring multiple components
- `@pytest.mark.asyncio`: Async test (requires pytest-asyncio)
- `@pytest.mark.slow`: Slow-running test (>1 second)
- `@pytest.mark.benchmark`: Performance benchmark test

## Expected Test Results

### Coverage

- **Total tests**: ~40 integration tests
- **E2E tests**: ~15 tests
- **Scenario tests**: ~12 tests
- **Performance tests**: ~13 tests

### Execution Time

- **Fast mode** (no slow): ~5-10 seconds
- **Full suite**: ~30-60 seconds
- **With real services**: ~2-5 minutes (requires Neo4j + ChromaDB)

### Success Criteria

All tests should pass with mocked dependencies:
- ✅ E2E pipeline: Query → Retrieval → Response
- ✅ Scenarios: Entity extraction → Search → Ranking
- ✅ Performance: Latency < thresholds, throughput > baselines

## Test Data

### Sample Papers

Located in `tests/fixtures/sample_papers.py`:

- TLIF RCT (Evidence Level 1b)
- UBE vs Open comparative study (2b)
- OLIF Meta-analysis (1a)
- ASD Cohort study (2a)
- Vertebroplasty Case series (3)

### Mock Responses

Located in `tests/fixtures/mock_neo4j_responses.py`:

- Paper query responses
- Intervention hierarchy
- Effective interventions
- Conflicting results
- Graph statistics

## Integration with Real Services

### Skip Real Service Tests by Default

Tests requiring actual Neo4j/ChromaDB are marked with `@pytest.mark.skip`:

```python
@pytest.mark.skip(reason="Requires actual Neo4j instance")
async def test_full_pipeline_with_real_services():
    ...
```

### Run with Real Services

To test with actual databases:

1. Start Neo4j:
```bash
docker-compose up -d neo4j
```

2. Set environment variables:
```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=your_password
export GEMINI_API_KEY=your_api_key
```

3. Remove skip marker and run:
```bash
pytest tests/integration/test_e2e_pipeline.py::TestPipelineIntegration -v
```

## Performance Benchmarks

### Typical Results (Mocked)

```
Query Times:
  Mean:   120-150ms
  Median: 110-130ms
  P95:    180-200ms

Graph Search:
  Mean:   15-25ms
  Median: 15-20ms

Vector Search:
  Mean:   25-35ms
  Median: 25-30ms

Hybrid Search:
  Mean:   40-60ms
  Median: 40-50ms

Throughput:
  10 concurrent queries: 20-30 queries/sec
```

### Generate Performance Report

```bash
pytest tests/integration/test_performance.py::TestLatencyReport -v -s
```

This will output a detailed performance report with all metrics.

## Troubleshooting

### Import Errors

If you see import errors:

```bash
# Ensure src/ is in PYTHONPATH
export PYTHONPATH=/path/to/project:$PYTHONPATH

# Or install in development mode
pip install -e .
```

### Async Warnings

If you see `RuntimeWarning: coroutine was never awaited`:

- Ensure all async functions use `await`
- Check that `@pytest.mark.asyncio` is present

### Mock Failures

If mocks aren't working:

- Verify mock paths match actual import paths
- Check that `spec=` parameter matches interface
- Use `AsyncMock` for async methods

## Contributing

When adding new integration tests:

1. Add fixtures to `tests/fixtures/`
2. Use appropriate markers (`@pytest.mark.integration`, etc.)
3. Mock external services (Neo4j, Gemini API)
4. Document expected behavior
5. Add to relevant test class

## CI/CD Integration

For continuous integration:

```yaml
# .github/workflows/test.yml
- name: Run integration tests
  run: |
    pytest tests/integration/ -v -m "not slow" --cov=src
```

This runs fast integration tests only, skipping slow benchmarks.

## References

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Project TRD](../../docs/TRD_v3_GraphRAG.md)
- [Project Tasks](../../docs/Tasks_v3_GraphRAG.md)
