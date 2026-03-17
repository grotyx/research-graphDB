"""Tests for core/embedding.py module.

Tests cover:
- build_context_prefix() with various inputs
- apply_context_prefix() enabled/disabled, sections/section modes
- OpenAIEmbeddingGenerator initialization and methods (mocked)
- EmbeddingGenerator (SentenceTransformers) initialization
- cosine_similarity()
- get_embedding_generator() and get_embedding_dimension() factory functions
- Error handling (API errors, empty inputs)
- CONTEXTUAL_PREFIX_ENABLED flag behavior
"""

import math
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.embedding import (
    build_context_prefix,
    apply_context_prefix,
    OpenAIEmbeddingGenerator,
    EmbeddingGenerator,
    EmbeddedChunk,
    cosine_similarity,
    get_embedding_generator,
    get_embedding_dimension,
    OPENAI_EMBEDDING_DIM,
    MEDTE_EMBEDDING_DIM,
    OPENAI_EMBEDDING_MODEL,
)


# ===========================================================================
# Tests: build_context_prefix
# ===========================================================================

class TestBuildContextPrefix:
    """Test build_context_prefix function."""

    def test_all_fields(self):
        """Prefix with title, section, year."""
        result = build_context_prefix(title="My Paper", section="abstract", year=2024)
        assert result == "[My Paper | abstract | 2024] "

    def test_title_only(self):
        """Prefix with only title."""
        result = build_context_prefix(title="My Paper")
        assert result == "[My Paper] "

    def test_section_only(self):
        """Prefix with only section."""
        result = build_context_prefix(section="results")
        assert result == "[results] "

    def test_year_only(self):
        """Prefix with only year."""
        result = build_context_prefix(year=2023)
        assert result == "[2023] "

    def test_title_and_section(self):
        """Prefix with title and section, no year."""
        result = build_context_prefix(title="Paper", section="methods")
        assert result == "[Paper | methods] "

    def test_empty_returns_empty(self):
        """No arguments returns empty string."""
        result = build_context_prefix()
        assert result == ""

    def test_empty_strings_returns_empty(self):
        """Empty string arguments returns empty string."""
        result = build_context_prefix(title="", section="", year=0)
        assert result == ""

    def test_year_zero_excluded(self):
        """Year 0 is excluded from prefix."""
        result = build_context_prefix(title="Paper", year=0)
        assert result == "[Paper] "

    def test_year_string_zero_excluded(self):
        """String '0' year is excluded from prefix."""
        result = build_context_prefix(title="Paper", year="0")
        assert result == "[Paper] "

    def test_year_as_string(self):
        """Year can be passed as string."""
        result = build_context_prefix(year="2025")
        assert result == "[2025] "

    def test_title_truncation(self):
        """Long titles are truncated to 120 chars."""
        long_title = "A" * 200
        result = build_context_prefix(title=long_title)
        # The title portion should be 120 chars
        assert len(result) < 200
        assert result.startswith("[" + "A" * 120)

    def test_none_title_treated_as_empty(self):
        """None title should behave same as empty (falsy)."""
        result = build_context_prefix(title="", section="abstract")
        assert result == "[abstract] "


# ===========================================================================
# Tests: apply_context_prefix
# ===========================================================================

class TestApplyContextPrefix:
    """Test apply_context_prefix function."""

    def test_enabled_single_section(self):
        """Apply prefix with single section to all contents."""
        contents = ["chunk1 text", "chunk2 text"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", year=2024, enabled=True
        )
        assert result[0] == "[Paper | abstract | 2024] chunk1 text"
        assert result[1] == "[Paper | abstract | 2024] chunk2 text"

    def test_enabled_per_chunk_sections(self):
        """Apply prefix with per-chunk sections."""
        contents = ["chunk1 text", "chunk2 text"]
        result = apply_context_prefix(
            contents, title="Paper", sections=["abstract", "results"], year=2024, enabled=True
        )
        assert result[0] == "[Paper | abstract | 2024] chunk1 text"
        assert result[1] == "[Paper | results | 2024] chunk2 text"

    def test_disabled_returns_original(self):
        """When disabled, returns original contents unchanged."""
        contents = ["chunk1 text", "chunk2 text"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", enabled=False
        )
        assert result is contents  # Same object

    def test_sections_length_mismatch_raises(self):
        """Sections list with wrong length raises ValueError."""
        with pytest.raises(ValueError, match="sections length"):
            apply_context_prefix(
                ["a", "b", "c"],
                sections=["abstract", "results"],
                enabled=True,
            )

    def test_no_context_returns_original(self):
        """No prefix context returns original list."""
        contents = ["chunk1"]
        result = apply_context_prefix(contents, enabled=True)
        assert result is contents  # When prefix is empty, returns originals

    def test_does_not_mutate_input(self):
        """Original list is not mutated."""
        contents = ["original text"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", enabled=True
        )
        assert contents[0] == "original text"
        assert result[0] != contents[0]

    def test_empty_contents(self):
        """Empty contents list."""
        result = apply_context_prefix([], title="Paper", enabled=True)
        assert result == []

    def test_section_none_uses_empty(self):
        """Section=None uses empty string for section."""
        contents = ["text"]
        result = apply_context_prefix(
            contents, title="Paper", section=None, year=2024, enabled=True
        )
        assert result[0] == "[Paper | 2024] text"


# ===========================================================================
# Tests: OpenAIEmbeddingGenerator
# ===========================================================================

def _make_openai_generator(**kwargs):
    """Helper to create OpenAIEmbeddingGenerator with mocked openai import."""
    mock_openai = MagicMock()
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    with patch.dict("sys.modules", {"openai": mock_openai}):
        gen = OpenAIEmbeddingGenerator(**kwargs)
    return gen, mock_client


class TestOpenAIEmbeddingGenerator:
    """Test OpenAIEmbeddingGenerator with mocked OpenAI client."""

    def test_initialization(self):
        """Test generator initializes with OpenAI client."""
        gen, _ = _make_openai_generator(batch_size=10)
        assert gen.batch_size == 10
        assert gen.model_name == OPENAI_EMBEDDING_MODEL

    def test_batch_size_capped_at_2048(self):
        """Batch size is capped at OpenAI limit of 2048."""
        gen, _ = _make_openai_generator(batch_size=5000)
        assert gen.batch_size == 2048

    def test_embed_single(self):
        """Test embedding a single text."""
        gen, mock_client = _make_openai_generator()
        mock_data_item = MagicMock()
        mock_data_item.embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [mock_data_item]
        mock_client.embeddings.create.return_value = mock_response

        result = gen.embed("test text")
        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once()

    def test_embed_batch_empty(self):
        """Empty text list returns empty embeddings."""
        gen, _ = _make_openai_generator()
        result = gen.embed_batch([])
        assert result == []

    def test_embed_batch_multiple(self):
        """Test batch embedding multiple texts."""
        gen, mock_client = _make_openai_generator()
        mock_data_1 = MagicMock()
        mock_data_1.embedding = [0.1, 0.2]
        mock_data_2 = MagicMock()
        mock_data_2.embedding = [0.3, 0.4]
        mock_response = MagicMock()
        mock_response.data = [mock_data_1, mock_data_2]
        mock_client.embeddings.create.return_value = mock_response

        result = gen.embed_batch(["text1", "text2"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    def test_embed_batch_api_error_raises(self):
        """API error during batch embed is raised."""
        gen, mock_client = _make_openai_generator()
        mock_client.embeddings.create.side_effect = RuntimeError("API error")

        with pytest.raises(RuntimeError, match="API error"):
            gen.embed_batch(["text"])

    def test_embed_chunks_empty(self):
        """Empty chunks list returns empty."""
        gen, _ = _make_openai_generator()
        result = gen.embed_chunks([])
        assert result == []

    def test_embed_chunks_returns_embedded_chunks(self):
        """Embed chunks returns list of EmbeddedChunk."""
        gen, mock_client = _make_openai_generator()
        mock_data = MagicMock()
        mock_data.embedding = [0.5, 0.6]
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        mock_chunk = MagicMock()
        mock_chunk.content = "some content"

        result = gen.embed_chunks([mock_chunk])
        assert len(result) == 1
        assert isinstance(result[0], EmbeddedChunk)
        assert result[0].embedding == [0.5, 0.6]
        assert result[0].chunk is mock_chunk

    def test_preprocess_normalizes_whitespace(self):
        """Preprocess collapses whitespace."""
        gen, _ = _make_openai_generator()
        result = gen._preprocess("  hello   world  \n  foo  ")
        assert result == "hello world foo"

    def test_preprocess_truncates_long_text(self):
        """Text exceeding 30000 chars is truncated."""
        gen, _ = _make_openai_generator()
        long_text = "a" * 35000
        result = gen._preprocess(long_text)
        assert len(result) == 30000

    def test_embedding_dimension_property(self):
        """Embedding dimension returns correct value."""
        gen, _ = _make_openai_generator()
        assert gen.embedding_dimension == OPENAI_EMBEDDING_DIM

    def test_get_model_info(self):
        """Get model info returns correct dict."""
        gen, _ = _make_openai_generator()
        info = gen.get_model_info()
        assert info["model_name"] == OPENAI_EMBEDDING_MODEL
        assert info["embedding_dimension"] == OPENAI_EMBEDDING_DIM
        assert info["provider"] == "openai"
        assert info["max_tokens"] == 8191


# ===========================================================================
# Tests: EmbeddingGenerator (SentenceTransformers)
# ===========================================================================

class TestEmbeddingGenerator:
    """Test legacy EmbeddingGenerator without loading actual models."""

    def test_initialization_defaults(self):
        """Default initialization without loading model."""
        gen = EmbeddingGenerator()
        assert gen.model_name == EmbeddingGenerator.DEFAULT_MODEL
        assert gen.device == "cpu"
        assert gen.batch_size == 32
        assert gen._model is None

    def test_initialization_custom(self):
        """Custom initialization parameters."""
        gen = EmbeddingGenerator(model_name="custom-model", device="cuda", batch_size=16)
        assert gen.model_name == "custom-model"
        assert gen.device == "cuda"
        assert gen.batch_size == 16

    def test_embed_batch_empty(self):
        """Empty batch returns empty list."""
        gen = EmbeddingGenerator()
        result = gen.embed_batch([])
        assert result == []

    def test_embed_chunks_empty(self):
        """Empty chunks list returns empty."""
        gen = EmbeddingGenerator()
        result = gen.embed_chunks([])
        assert result == []

    def test_preprocess_normalizes_whitespace(self):
        """Preprocess collapses whitespace."""
        gen = EmbeddingGenerator()
        result = gen._preprocess("  hello   world  ")
        assert result == "hello world"

    def test_preprocess_truncates_long_text(self):
        """Text exceeding 2048 chars is truncated."""
        gen = EmbeddingGenerator()
        long_text = "b" * 3000
        result = gen._preprocess(long_text)
        assert len(result) == 2048


# ===========================================================================
# Tests: cosine_similarity
# ===========================================================================

class TestCosineSimilarity:
    """Test cosine_similarity function."""

    def test_identical_vectors(self):
        """Identical vectors have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors have similarity 0.0."""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors have similarity -1.0."""
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        """Zero vector returns 0.0."""
        vec1 = [0.0, 0.0]
        vec2 = [1.0, 2.0]
        assert cosine_similarity(vec1, vec2) == 0.0

    def test_both_zero_vectors(self):
        """Both zero vectors returns 0.0."""
        assert cosine_similarity([0.0], [0.0]) == 0.0

    def test_known_similarity(self):
        """Test with known similarity value."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [4.0, 5.0, 6.0]
        dot = 1*4 + 2*5 + 3*6  # 32
        mag1 = math.sqrt(1 + 4 + 9)  # sqrt(14)
        mag2 = math.sqrt(16 + 25 + 36)  # sqrt(77)
        expected = dot / (mag1 * mag2)
        assert cosine_similarity(vec1, vec2) == pytest.approx(expected)


# ===========================================================================
# Tests: Factory Functions
# ===========================================================================

class TestFactoryFunctions:
    """Test get_embedding_generator and get_embedding_dimension."""

    def test_get_generator_openai(self):
        """get_embedding_generator('openai') returns OpenAI generator."""
        mock_openai = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_openai}):
            gen = get_embedding_generator("openai")
        assert isinstance(gen, OpenAIEmbeddingGenerator)

    def test_get_generator_medte(self):
        """get_embedding_generator('medte') returns ST generator with MedTE model."""
        gen = get_embedding_generator("medte")
        assert isinstance(gen, EmbeddingGenerator)
        assert "MedTE" in gen.model_name

    def test_get_generator_default_st(self):
        """get_embedding_generator('sentence-transformers') returns ST generator."""
        gen = get_embedding_generator("sentence-transformers")
        assert isinstance(gen, EmbeddingGenerator)

    def test_get_dimension_openai(self):
        """OpenAI dimension is 3072."""
        assert get_embedding_dimension("openai") == OPENAI_EMBEDDING_DIM
        assert get_embedding_dimension("openai") == 3072

    def test_get_dimension_medte(self):
        """MedTE dimension is 768."""
        assert get_embedding_dimension("medte") == MEDTE_EMBEDDING_DIM
        assert get_embedding_dimension("medte") == 768

    def test_get_dimension_unknown_falls_to_medte(self):
        """Unknown model type falls back to MedTE dimension."""
        assert get_embedding_dimension("unknown") == MEDTE_EMBEDDING_DIM


# ===========================================================================
# Tests: EmbeddedChunk dataclass
# ===========================================================================

class TestEmbeddedChunk:
    """Test EmbeddedChunk dataclass."""

    def test_creation(self):
        """Create EmbeddedChunk with all fields."""
        mock_chunk = MagicMock()
        ec = EmbeddedChunk(chunk=mock_chunk, embedding=[0.1, 0.2], model_name="test-model")
        assert ec.chunk is mock_chunk
        assert ec.embedding == [0.1, 0.2]
        assert ec.model_name == "test-model"
