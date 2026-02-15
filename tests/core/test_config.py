"""Tests for centralized configuration system.

Test coverage:
- Config file loading
- Environment variable resolution
- Type safety and validation
- Quick access helpers
- Error handling
"""

import os
import tempfile
from pathlib import Path

import pytest

from core.config import (
    Config,
    ConfigManager,
    get_config,
    get_neo4j_config,
    get_llm_config,
    get_chromadb_config,
    get_normalization_config,
    get_threshold,
    reload_config,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_config_file():
    """Create temporary config file for testing."""
    config_content = """
version: "3.1"

neo4j:
  uri: ${NEO4J_URI:bolt://test:7687}
  username: ${NEO4J_USERNAME:test_user}
  password: ${NEO4J_PASSWORD:test_pass}
  database: test_db
  max_connection_pool_size: 25

chromadb:
  path: ./test_data/chromadb
  collection_name: test_collection

llm:
  provider: gemini
  model: ${LLM_MODEL:gemini-2.5-flash}
  api_key: ${GEMINI_API_KEY:test_api_key}
  temperature: 0.2
  max_tokens: 4096
  timeout: 30
  vision:
    model: gemini-2.5-flash
    timeout: 60

normalization:
  fuzzy_threshold: 0.90
  token_overlap_threshold: 0.85

search:
  default_top_k: 20
  max_top_k: 200

ranker:
  default_graph_weight: 0.7
  default_vector_weight: 0.3
  evidence_weights:
    "1a": 1.0
    "1b": 0.9
  significance_threshold: 0.01

conflict:
  min_papers_for_conflict: 3
  significance_threshold: 0.05

cache:
  query_cache:
    enabled: true
    max_size: 500
  semantic_cache:
    similarity_threshold: 0.90

batch:
  default_batch_size: 5
  max_concurrency: 3

logging:
  level: DEBUG
  format: "%(levelname)s - %(message)s"

development:
  debug: true
  test_mode: true
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def reset_config():
    """Reset config singleton between tests and preserve environment."""
    ConfigManager._instance = None
    ConfigManager._config = None
    saved_env = dict(os.environ)
    yield
    ConfigManager._instance = None
    ConfigManager._config = None
    # Restore environment: remove any new vars, restore deleted ones
    os.environ.clear()
    os.environ.update(saved_env)


# ============================================================================
# Basic Loading Tests
# ============================================================================


def test_config_loading_from_file(temp_config_file, reset_config):
    """Test loading configuration from file."""
    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert config.version == "3.1"
    assert config.neo4j.database == "test_db"
    assert config.chromadb.collection_name == "test_collection"
    assert config.llm.temperature == 0.2


def test_singleton_pattern(temp_config_file, reset_config):
    """Test singleton pattern ensures same instance."""
    manager1 = ConfigManager()
    manager2 = ConfigManager()

    assert manager1 is manager2

    config1 = manager1.load(temp_config_file)
    config2 = manager2.load(temp_config_file)

    assert config1 is config2


def test_config_caching(temp_config_file, reset_config):
    """Test configuration is cached after first load."""
    manager = ConfigManager()

    config1 = manager.load(temp_config_file)
    config2 = manager.load()  # Should return cached

    assert config1 is config2


# ============================================================================
# Environment Variable Resolution Tests
# ============================================================================


def test_env_var_resolution_with_default(temp_config_file, reset_config):
    """Test environment variable resolution with defaults."""
    # Remove env vars so config file defaults apply (reset_config fixture restores them)
    for key in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "GEMINI_API_KEY", "LLM_MODEL"]:
        os.environ.pop(key, None)

    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert config.neo4j.uri == "bolt://test:7687"
    assert config.neo4j.username == "test_user"
    assert config.llm.api_key == "test_api_key"


def test_env_var_resolution_with_override(temp_config_file, reset_config):
    """Test environment variable override."""
    # Set override values (reset_config fixture restores originals)
    os.environ["NEO4J_URI"] = "bolt://override:7687"
    os.environ["NEO4J_USERNAME"] = "override_user"
    os.environ["GEMINI_API_KEY"] = "override_key"

    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert config.neo4j.uri == "bolt://override:7687"
    assert config.neo4j.username == "override_user"
    assert config.llm.api_key == "override_key"


def test_env_var_resolution_without_default(temp_config_file, reset_config):
    """Test environment variable without default returns empty string."""
    config_content = """
version: "3.1"
neo4j:
  uri: ${UNDEFINED_VAR}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_content)
        temp_path = f.name

    try:
        manager = ConfigManager()
        config = manager.load(temp_path)

        assert config.neo4j.uri == ""
    finally:
        Path(temp_path).unlink()


# ============================================================================
# Type Safety Tests
# ============================================================================


def test_neo4j_config_types(temp_config_file, reset_config):
    """Test Neo4j config type correctness."""
    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert isinstance(config.neo4j.uri, str)
    assert isinstance(config.neo4j.max_connection_pool_size, int)
    assert config.neo4j.max_connection_pool_size == 25


def test_llm_config_types(temp_config_file, reset_config):
    """Test LLM config type correctness."""
    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert isinstance(config.llm.temperature, float)
    assert isinstance(config.llm.max_tokens, int)
    assert config.llm.temperature == 0.2
    assert config.llm.max_tokens == 4096


def test_normalization_config_types(temp_config_file, reset_config):
    """Test normalization config type correctness."""
    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert isinstance(config.normalization.fuzzy_threshold, float)
    assert config.normalization.fuzzy_threshold == 0.90


def test_nested_config_types(temp_config_file, reset_config):
    """Test nested config (vision) type correctness."""
    manager = ConfigManager()
    config = manager.load(temp_config_file)

    assert isinstance(config.llm.vision.timeout, int)
    assert config.llm.vision.timeout == 60


# ============================================================================
# Quick Access Helper Tests
# ============================================================================


def test_get_config_helper(temp_config_file, reset_config):
    """Test get_config() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    config = get_config()
    assert config.version == "3.1"


def test_get_neo4j_config_helper(temp_config_file, reset_config):
    """Test get_neo4j_config() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    neo4j = get_neo4j_config()
    assert neo4j.database == "test_db"
    assert neo4j.max_connection_pool_size == 25


def test_get_llm_config_helper(temp_config_file, reset_config):
    """Test get_llm_config() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    llm = get_llm_config()
    assert llm.temperature == 0.2
    assert llm.max_tokens == 4096


def test_get_chromadb_config_helper(temp_config_file, reset_config):
    """Test get_chromadb_config() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    chromadb = get_chromadb_config()
    assert chromadb.collection_name == "test_collection"


def test_get_normalization_config_helper(temp_config_file, reset_config):
    """Test get_normalization_config() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    norm = get_normalization_config()
    assert norm.fuzzy_threshold == 0.90


def test_get_threshold_helper(temp_config_file, reset_config):
    """Test get_threshold() helper function."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    fuzzy = get_threshold("fuzzy_threshold")
    assert fuzzy == 0.90

    sig = get_threshold("significance_threshold")
    assert sig == 0.01

    # Test with default
    custom = get_threshold("nonexistent_threshold", default=0.5)
    assert custom == 0.5


def test_get_threshold_not_found(temp_config_file, reset_config):
    """Test get_threshold() raises error when threshold not found."""
    manager = ConfigManager()
    manager.load(temp_config_file)

    with pytest.raises(ValueError, match="not found in configuration"):
        get_threshold("nonexistent_threshold")


# ============================================================================
# Reload Tests
# ============================================================================


def test_reload_config(temp_config_file, reset_config):
    """Test config reload functionality."""
    manager = ConfigManager()
    config1 = manager.load(temp_config_file)

    # Modify config file
    with open(temp_config_file, "r") as f:
        content = f.read()
    content = content.replace("test_db", "reloaded_db")

    with open(temp_config_file, "w") as f:
        f.write(content)

    # Reload
    config2 = reload_config(temp_config_file)

    assert config1 is not config2
    assert config2.neo4j.database == "reloaded_db"


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_missing_config_file(reset_config):
    """Test error when config file not found."""
    manager = ConfigManager()

    with pytest.raises(FileNotFoundError):
        manager.load("/nonexistent/path/config.yaml")


def test_invalid_yaml(reset_config):
    """Test error when YAML is invalid."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content:\n  - [unclosed")
        temp_path = f.name

    try:
        manager = ConfigManager()
        with pytest.raises(ValueError, match="Invalid YAML"):
            manager.load(temp_path)
    finally:
        Path(temp_path).unlink()


# ============================================================================
# Default Values Tests
# ============================================================================


def test_default_config_values(reset_config):
    """Test default configuration values when sections are missing."""
    minimal_config = """
version: "3.1"
neo4j:
  uri: bolt://localhost:7687
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(minimal_config)
        temp_path = f.name

    try:
        manager = ConfigManager()
        config = manager.load(temp_path)

        # Check defaults are applied
        assert config.chromadb.collection_name == "spine_papers"
        assert config.llm.temperature == 0.1
        assert config.search.default_top_k == 10
        assert config.ranker.default_graph_weight == 0.6
    finally:
        Path(temp_path).unlink()


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_config_integration(temp_config_file, reset_config):
    """Test full configuration with all helpers."""
    # Set some env vars
    os.environ["NEO4J_PASSWORD"] = "secret_pass"
    os.environ["LLM_MODEL"] = "gemini-2.5-pro"

    try:
        manager = ConfigManager()
        manager.load(temp_config_file)

        # Test global access
        config = get_config()
        assert config.version == "3.1"

        # Test specific configs
        neo4j = get_neo4j_config()
        assert neo4j.password == "secret_pass"

        llm = get_llm_config()
        assert llm.model == "gemini-2.5-pro"

        # Test thresholds
        fuzzy = get_threshold("fuzzy_threshold")
        assert fuzzy == 0.90

        sig = get_threshold("significance_threshold")
        assert sig == 0.01

        # Test nested access
        assert llm.vision.model == "gemini-2.5-flash"

        # Test dict fields
        assert config.cache.query_cache["max_size"] == 500
        assert config.ranker.evidence_weights["1a"] == 1.0

    finally:
        del os.environ["NEO4J_PASSWORD"]
        del os.environ["LLM_MODEL"]


def test_config_usage_in_module_context(temp_config_file, reset_config):
    """Test configuration usage as it would be in actual modules."""
    # Remove env vars so config file defaults apply (reset_config fixture restores them)
    for key in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "GEMINI_API_KEY", "LLM_MODEL"]:
        os.environ.pop(key, None)

    manager = ConfigManager()
    manager.load(temp_config_file)

    # Simulate module usage
    from core.config import get_neo4j_config, get_llm_config, get_threshold

    # Module would import these and use them
    neo4j = get_neo4j_config()
    connection_string = f"{neo4j.uri}/{neo4j.database}"
    assert connection_string == "bolt://test:7687/test_db"

    llm = get_llm_config()
    model_config = {"model": llm.model, "temperature": llm.temperature}
    assert model_config["temperature"] == 0.2

    fuzzy_threshold = get_threshold("fuzzy_threshold", default=0.85)
    assert fuzzy_threshold == 0.90
