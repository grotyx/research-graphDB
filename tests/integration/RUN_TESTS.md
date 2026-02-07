# How to Run Integration Tests

## Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Ensure you're in project root
cd /Users/sangminpark/Desktop/rag_research
```

## Quick Start

### Run All New Integration Tests

```bash
pytest tests/integration/test_hybrid_pipeline.py \
       tests/integration/test_evidence_synthesis.py \
       tests/integration/test_inference_engine.py \
       -v
```

### Run Individual Test Files

```bash
# Hybrid pipeline tests (28 tests)
pytest tests/integration/test_hybrid_pipeline.py -v

# Evidence synthesis tests (41 tests)
pytest tests/integration/test_evidence_synthesis.py -v

# Inference engine tests (38 tests)
pytest tests/integration/test_inference_engine.py -v
```

### Run Specific Test Classes

```bash
# Query classification only
pytest tests/integration/test_hybrid_pipeline.py::TestQueryClassification -v

# Evidence gathering only
pytest tests/integration/test_evidence_synthesis.py::TestEvidenceGathering -v

# Transitive hierarchy only
pytest tests/integration/test_inference_engine.py::TestTransitiveHierarchy -v
```

### Run Specific Test Methods

```bash
pytest tests/integration/test_hybrid_pipeline.py::TestQueryClassification::test_factual_queries -v
```

## Test Options

### Verbose Output

```bash
pytest tests/integration/ -v
```

### Show Print Statements

```bash
pytest tests/integration/ -v -s
```

### Stop on First Failure

```bash
pytest tests/integration/ -x
```

### Run Failed Tests Only

```bash
pytest tests/integration/ --lf
```

### Show Test Duration

```bash
pytest tests/integration/ --durations=10
```

## Coverage Reports

### HTML Coverage Report

```bash
pytest tests/integration/ \
  --cov=src/solver \
  --cov=src/graph \
  --cov-report=html

# View report
open htmlcov/index.html
```

### Terminal Coverage

```bash
pytest tests/integration/ \
  --cov=src/solver \
  --cov=src/graph \
  --cov-report=term-missing
```

### Coverage for Specific Module

```bash
# Adaptive ranker only
pytest tests/integration/test_hybrid_pipeline.py \
  --cov=src/solver/adaptive_ranker \
  --cov-report=term

# Evidence synthesizer only
pytest tests/integration/test_evidence_synthesis.py \
  --cov=src/solver/evidence_synthesizer \
  --cov-report=term

# Inference engine only
pytest tests/integration/test_inference_engine.py \
  --cov=src/graph/inference_rules \
  --cov-report=term
```

## Debugging

### Show Full Traceback

```bash
pytest tests/integration/ -v --tb=long
```

### Show Short Traceback

```bash
pytest tests/integration/ -v --tb=short
```

### Run with PDB on Failure

```bash
pytest tests/integration/ --pdb
```

### Show Warnings

```bash
pytest tests/integration/ -v -W all
```

## Markers

### Run Integration Tests Only

```bash
pytest tests/ -m integration -v
```

### Run Async Tests Only

```bash
pytest tests/ -m asyncio -v
```

## Performance

### Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run with 4 workers
pytest tests/integration/ -n 4
```

## Test Reports

### JUnit XML (for CI/CD)

```bash
pytest tests/integration/ --junitxml=test-results.xml
```

### JSON Report

```bash
# Install pytest-json-report
pip install pytest-json-report

pytest tests/integration/ --json-report --json-report-file=test-results.json
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest tests/integration/ -v --cov --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Common Issues

### Issue 1: Module Import Errors

```bash
# Solution: Set PYTHONPATH
export PYTHONPATH=/Users/sangminpark/Desktop/rag_research:$PYTHONPATH
pytest tests/integration/ -v
```

### Issue 2: Async Tests Not Running

```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check pytest.ini or pyproject.toml has:
# [tool.pytest.ini_options]
# asyncio_mode = "auto"
```

### Issue 3: Neo4j Connection Errors

These tests use mocks, so no real Neo4j needed. If you see connection errors, check:
- Tests are using `mock_neo4j_client` fixture
- Not accidentally using real Neo4jClient

### Issue 4: Missing Test Dependencies

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov
```

## Test Data

All tests use mocked data defined in fixtures:
- No real database required
- No external API calls
- Fast execution (seconds)

## Expected Output

### Successful Run

```
============================= test session starts ==============================
...
tests/integration/test_hybrid_pipeline.py::TestQueryClassification::test_factual_queries PASSED
tests/integration/test_hybrid_pipeline.py::TestQueryClassification::test_comparative_queries PASSED
...
============================== 107 passed in 2.5s ==============================
```

### Failed Tests

```
FAILED tests/integration/test_hybrid_pipeline.py::TestQueryClassification::test_evidence_queries
```

Check TEST_SUMMARY.md for known issues and fixes.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `pytest tests/integration/ -v` | Run all tests verbose |
| `pytest tests/integration/ -x` | Stop on first failure |
| `pytest tests/integration/ --lf` | Run last failed |
| `pytest tests/integration/ -k "test_factual"` | Run tests matching name |
| `pytest tests/integration/ -m asyncio` | Run async tests only |
| `pytest tests/integration/ --cov` | Generate coverage |
| `pytest tests/integration/ -n 4` | Run in parallel |

## Need Help?

See:
- TEST_SUMMARY.md - Detailed test documentation
- tests/integration/conftest.py - Shared fixtures
- pytest docs: https://docs.pytest.org/
