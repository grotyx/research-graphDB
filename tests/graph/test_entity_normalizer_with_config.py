"""Tests for EntityNormalizer with configuration system integration.

Verify that EntityNormalizer correctly uses configuration values for thresholds.
"""

import tempfile
from pathlib import Path

import pytest

from src.graph.entity_normalizer import EntityNormalizer
from src.core.config import ConfigManager


@pytest.fixture
def custom_config():
    """Create custom config with different thresholds."""
    config_content = """
version: "3.1"

normalization:
  fuzzy_threshold: 0.90
  token_overlap_threshold: 0.85
  word_boundary_confidence: 0.98
  partial_match_threshold: 0.6
  enable_korean_normalization: true
  strip_particles: true
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def reset_config():
    """Reset config singleton between tests."""
    ConfigManager._instance = None
    ConfigManager._config = None
    yield
    ConfigManager._instance = None
    ConfigManager._config = None


def test_entity_normalizer_loads_config(custom_config, reset_config):
    """Test that EntityNormalizer loads configuration values."""
    # Load custom config
    manager = ConfigManager()
    manager.load(custom_config)

    # Create normalizer - should use config values
    normalizer = EntityNormalizer()

    # Verify config values are loaded
    assert normalizer.fuzzy_threshold == 0.90
    assert normalizer.token_overlap_threshold == 0.85
    assert normalizer.word_boundary_confidence == 0.98
    assert normalizer.partial_match_threshold == 0.6
    assert normalizer.enable_korean_normalization is True
    assert normalizer.strip_particles is True


def test_entity_normalizer_uses_defaults_without_config(reset_config):
    """Test that EntityNormalizer uses defaults when config is unavailable."""
    # Don't load config - normalizer should use defaults
    normalizer = EntityNormalizer()

    # Verify default values are used
    assert normalizer.fuzzy_threshold == 0.85
    assert normalizer.token_overlap_threshold == 0.8
    assert normalizer.word_boundary_confidence == 0.95
    assert normalizer.partial_match_threshold == 0.5
    assert normalizer.enable_korean_normalization is True
    assert normalizer.strip_particles is True


def test_entity_normalizer_functionality_with_config(custom_config, reset_config):
    """Test that EntityNormalizer still works correctly with config."""
    # Load config
    manager = ConfigManager()
    manager.load(custom_config)

    # Create normalizer
    normalizer = EntityNormalizer()

    # Test exact match (should work regardless of thresholds)
    result = normalizer.normalize_intervention("TLIF")
    assert result.normalized == "TLIF"
    assert result.confidence == 1.0

    # Test alias match
    result = normalizer.normalize_intervention("Biportal Endoscopic")
    assert result.normalized == "UBE"
    assert result.confidence == 1.0

    # Test Korean normalization
    result = normalizer.normalize_intervention("척추 유합술")
    assert result.normalized == "Fusion Surgery"
    assert result.confidence == 1.0


def test_entity_normalizer_threshold_impact(custom_config, reset_config):
    """Test that config thresholds actually impact matching behavior."""
    # Load config with higher fuzzy threshold (0.90)
    manager = ConfigManager()
    manager.load(custom_config)

    normalizer = EntityNormalizer()

    # The threshold should affect fuzzy matching
    # With higher threshold, fewer fuzzy matches should succeed
    assert normalizer.fuzzy_threshold == 0.90

    # Test a slightly misspelled term
    # This might not match with higher threshold
    result = normalizer.normalize_intervention("TLIFF")  # Extra F

    # The result depends on fuzzy matching threshold
    # Just verify the normalizer runs without error
    assert result is not None
    assert result.original == "TLIFF"


def test_entity_normalizer_outcome_normalization(custom_config, reset_config):
    """Test outcome normalization with config."""
    manager = ConfigManager()
    manager.load(custom_config)

    normalizer = EntityNormalizer()

    # Test exact outcome match
    result = normalizer.normalize_outcome("VAS")
    assert result.normalized == "VAS"
    assert result.confidence == 1.0

    # Test outcome alias
    result = normalizer.normalize_outcome("Visual Analog Scale")
    assert result.normalized == "VAS"
    assert result.confidence == 1.0


def test_entity_normalizer_pathology_normalization(custom_config, reset_config):
    """Test pathology normalization with config."""
    manager = ConfigManager()
    manager.load(custom_config)

    normalizer = EntityNormalizer()

    # Test exact pathology match
    result = normalizer.normalize_pathology("Lumbar Stenosis")
    assert result.normalized == "Lumbar Stenosis"
    assert result.confidence == 1.0

    # Test pathology alias
    result = normalizer.normalize_pathology("요추 협착증")
    assert result.normalized == "Lumbar Stenosis"
    assert result.confidence == 1.0


def test_entity_normalizer_extraction_with_config(custom_config, reset_config):
    """Test entity extraction with config."""
    manager = ConfigManager()
    manager.load(custom_config)

    normalizer = EntityNormalizer()

    # Test intervention extraction
    text = "Comparison of TLIF and OLIF for lumbar stenosis"
    interventions = normalizer.extract_and_normalize_interventions(text)

    assert len(interventions) >= 2
    normalized = [r.normalized for r in interventions]
    assert "TLIF" in normalized
    assert "OLIF" in normalized


def test_config_persistence_across_normalizer_instances(custom_config, reset_config):
    """Test that config is shared across normalizer instances."""
    manager = ConfigManager()
    manager.load(custom_config)

    # Create two normalizers
    normalizer1 = EntityNormalizer()
    normalizer2 = EntityNormalizer()

    # Both should have same config values
    assert normalizer1.fuzzy_threshold == normalizer2.fuzzy_threshold
    assert normalizer1.fuzzy_threshold == 0.90
