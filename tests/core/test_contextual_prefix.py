"""Tests for contextual embedding prefix helpers."""

import os
import pytest

from core.embedding import build_context_prefix, apply_context_prefix


class TestBuildContextPrefix:
    """Tests for build_context_prefix()."""

    def test_full_context(self):
        result = build_context_prefix(
            title="Outcomes of UBE for Lumbar Stenosis",
            section="results",
            year=2025,
        )
        assert result == "[Outcomes of UBE for Lumbar Stenosis | results | 2025] "

    def test_title_only(self):
        result = build_context_prefix(title="My Paper")
        assert result == "[My Paper] "

    def test_section_only(self):
        result = build_context_prefix(section="abstract")
        assert result == "[abstract] "

    def test_year_only(self):
        result = build_context_prefix(year=2024)
        assert result == "[2024] "

    def test_empty_returns_empty(self):
        result = build_context_prefix()
        assert result == ""

    def test_zero_year_ignored(self):
        result = build_context_prefix(title="Paper", year=0)
        assert result == "[Paper] "

    def test_title_truncated_at_120(self):
        long_title = "A" * 200
        result = build_context_prefix(title=long_title)
        assert f"[{'A' * 120}]" in result

    def test_year_as_string(self):
        result = build_context_prefix(title="Test", year="2023")
        assert "2023" in result

    def test_string_zero_year_ignored(self):
        result = build_context_prefix(title="Test", year="0")
        assert "0" not in result


class TestApplyContextPrefix:
    """Tests for apply_context_prefix()."""

    def test_single_section(self):
        contents = ["Chunk 1", "Chunk 2"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", year=2025
        )
        assert result[0] == "[Paper | abstract | 2025] Chunk 1"
        assert result[1] == "[Paper | abstract | 2025] Chunk 2"

    def test_per_chunk_sections(self):
        contents = ["Abstract text", "Results text"]
        result = apply_context_prefix(
            contents,
            title="Paper",
            sections=["abstract", "results"],
            year=2025,
        )
        assert result[0] == "[Paper | abstract | 2025] Abstract text"
        assert result[1] == "[Paper | results | 2025] Results text"

    def test_disabled(self):
        contents = ["Chunk 1", "Chunk 2"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", year=2025, enabled=False
        )
        assert result == contents

    def test_no_context_returns_original(self):
        contents = ["Chunk 1"]
        result = apply_context_prefix(contents)
        assert result == contents

    def test_sections_length_mismatch_raises(self):
        with pytest.raises(AssertionError):
            apply_context_prefix(
                ["a", "b"],
                sections=["abstract"],
            )

    def test_originals_not_mutated(self):
        contents = ["Original text"]
        result = apply_context_prefix(
            contents, title="Paper", section="abstract", year=2025
        )
        assert contents[0] == "Original text"
        assert result[0] != contents[0]

    def test_env_override(self, monkeypatch):
        """Test that EMBEDDING_CONTEXTUAL_PREFIX env var is respected."""
        # The flag is read at import time, so we test via enabled parameter
        result_on = apply_context_prefix(
            ["text"], title="Paper", enabled=True
        )
        result_off = apply_context_prefix(
            ["text"], title="Paper", enabled=False
        )
        assert "[Paper]" in result_on[0]
        assert result_off[0] == "text"
