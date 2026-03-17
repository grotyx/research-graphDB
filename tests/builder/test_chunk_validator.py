"""Tests for chunk_validator.py — Chunk Quality Validation Module.

Covers: length filter, tier demotion, statistics check, near-duplicate
detection, full pipeline, stats reporting, and validation_notes field.
"""

import math
import pytest

from builder.chunk_validator import (
    ChunkValidator,
    MIN_CHUNK_LENGTH,
    TIER1_MIN_LENGTH,
    DUPLICATE_SIMILARITY_THRESHOLD,
    _has_statistics,
    _cosine_similarity,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_chunk(
    content: str,
    tier: str = "tier2",
    section_type: str = "methods",
    is_key_finding: bool = False,
) -> dict:
    """Create a minimal chunk dict for testing."""
    return {
        "content": content,
        "tier": tier,
        "section_type": section_type,
        "is_key_finding": is_key_finding,
    }


def _unit_vec(dim: int, index: int) -> list[float]:
    """Return a unit vector with 1.0 at `index`, rest 0.0."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


def _near_duplicate_pair(dim: int = 10, noise: float = 0.01):
    """Return two nearly identical embedding vectors (cosine > 0.99)."""
    base = [1.0] * dim
    perturbed = [x + noise for x in base]
    return base, perturbed


# =============================================================================
# 1. Length filter tests
# =============================================================================

class TestLengthFilter:
    """Chunks shorter than MIN_CHUNK_LENGTH are rejected."""

    def test_chunk_below_min_length_rejected(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("short")]
        result = validator.validate_chunks(chunks)
        assert len(result) == 0

    def test_chunk_at_min_length_kept(self):
        validator = ChunkValidator()
        content = "a" * MIN_CHUNK_LENGTH  # exactly 30 chars
        chunks = [_make_chunk(content)]
        result = validator.validate_chunks(chunks)
        assert len(result) == 1

    def test_chunk_above_min_length_kept(self):
        validator = ChunkValidator()
        content = "a" * (MIN_CHUNK_LENGTH + 50)
        chunks = [_make_chunk(content)]
        result = validator.validate_chunks(chunks)
        assert len(result) == 1

    def test_empty_content_rejected(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("")]
        result = validator.validate_chunks(chunks)
        assert len(result) == 0

    def test_missing_content_key_rejected(self):
        validator = ChunkValidator()
        chunks = [{"tier": "tier2", "section_type": "methods"}]
        result = validator.validate_chunks(chunks)
        assert len(result) == 0


# =============================================================================
# 2. Tier demotion tests
# =============================================================================

class TestTierDemotion:
    """tier1 chunks shorter than TIER1_MIN_LENGTH are demoted to tier2."""

    def test_short_tier1_demoted_to_tier2(self):
        validator = ChunkValidator()
        content = "a" * 100  # < 200
        chunks = [_make_chunk(content, tier="tier1")]
        result = validator.validate_chunks(chunks)
        assert result[0]["tier"] == "tier2"

    def test_long_tier1_stays_tier1(self):
        validator = ChunkValidator()
        content = "a" * TIER1_MIN_LENGTH  # exactly 200
        chunks = [_make_chunk(content, tier="tier1")]
        result = validator.validate_chunks(chunks)
        assert result[0]["tier"] == "tier1"

    def test_tier2_not_double_demoted(self):
        """tier2 chunks shorter than TIER1_MIN_LENGTH stay tier2 (no further demotion)."""
        validator = ChunkValidator()
        content = "a" * 50
        chunks = [_make_chunk(content, tier="tier2")]
        result = validator.validate_chunks(chunks)
        assert result[0]["tier"] == "tier2"
        # No demotion note expected
        assert not any("tier1->tier2" in n for n in result[0].get("validation_notes", []))

    def test_demotion_counter_incremented(self):
        validator = ChunkValidator()
        content = "a" * 100
        chunks = [_make_chunk(content, tier="tier1")]
        validator.validate_chunks(chunks)
        stats = validator.get_validation_stats()
        assert stats["demoted_tier"] == 1


# =============================================================================
# 3. Statistics check tests
# =============================================================================

class TestStatisticsCheck:
    """Results/findings chunks without statistics get key_finding cleared."""

    def test_results_with_pvalue_keeps_key_finding(self):
        validator = ChunkValidator()
        content = "The treatment showed significant improvement with p < 0.05 after 6 months of follow-up."
        chunks = [_make_chunk(content, section_type="results", is_key_finding=True)]
        result = validator.validate_chunks(chunks)
        assert result[0]["is_key_finding"] is True

    def test_results_without_stats_clears_key_finding(self):
        validator = ChunkValidator()
        content = "The treatment showed some improvement in patient outcomes over time consistently."
        chunks = [_make_chunk(content, section_type="results", is_key_finding=True)]
        result = validator.validate_chunks(chunks)
        assert result[0]["is_key_finding"] is False

    def test_non_results_section_not_modified(self):
        """key_finding in non-results sections is not touched."""
        validator = ChunkValidator()
        content = "The treatment showed some improvement in patient outcomes over time consistently."
        chunks = [_make_chunk(content, section_type="methods", is_key_finding=True)]
        result = validator.validate_chunks(chunks)
        assert result[0]["is_key_finding"] is True

    def test_percentage_pattern_detected(self):
        content = "Success rate was 45% in the treatment group after the intervention period."
        assert _has_statistics(content) is True

    def test_or_hr_pattern_detected(self):
        content = "The odds ratio was OR=2.5 for the treatment group versus the control group."
        assert _has_statistics(content) is True

    def test_sample_size_pattern_detected(self):
        content = "A total of n=50 patients were included in the final analysis of the study."
        assert _has_statistics(content) is True

    def test_mean_sd_pattern_detected(self):
        content = "The mean VAS score was 3.2 \u00b1 1.1 at the final follow-up visit for all patients."
        assert _has_statistics(content) is True

    def test_fraction_pattern_detected(self):
        content = "Complications occurred in 23/45 patients during the follow-up period of one year."
        assert _has_statistics(content) is True

    def test_findings_section_also_checked(self):
        """'findings' section type should also trigger stats check."""
        validator = ChunkValidator()
        content = "The data showed clear trends in outcomes across all groups studied in the trial."
        chunks = [_make_chunk(content, section_type="findings", is_key_finding=True)]
        result = validator.validate_chunks(chunks)
        assert result[0]["is_key_finding"] is False

    def test_cleared_key_finding_counter(self):
        validator = ChunkValidator()
        content = "The treatment showed some improvement in patient outcomes over time consistently."
        chunks = [_make_chunk(content, section_type="results", is_key_finding=True)]
        validator.validate_chunks(chunks)
        stats = validator.get_validation_stats()
        assert stats["cleared_key_finding"] == 1


# =============================================================================
# 4. Near-duplicate detection tests
# =============================================================================

class TestNearDuplicateDetection:
    """Near-duplicate chunks (cosine sim > threshold) are removed."""

    def test_high_similarity_removes_shorter(self):
        validator = ChunkValidator()
        long_content = "a" * 100
        short_content = "b" * 50
        chunks = [_make_chunk(long_content), _make_chunk(short_content)]
        emb1, emb2 = _near_duplicate_pair()
        result = validator.validate_chunks(chunks, embeddings=[emb1, emb2])
        assert len(result) == 1
        assert result[0]["content"] == long_content

    def test_low_similarity_keeps_both(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("a" * 50), _make_chunk("b" * 50)]
        # Orthogonal vectors -> cosine = 0
        emb1 = _unit_vec(10, 0)
        emb2 = _unit_vec(10, 1)
        result = validator.validate_chunks(chunks, embeddings=[emb1, emb2])
        assert len(result) == 2

    def test_no_embeddings_skips_dedup(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("a" * 50), _make_chunk("a" * 50)]
        result = validator.validate_chunks(chunks, embeddings=None)
        assert len(result) == 2

    def test_single_chunk_no_dedup(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("a" * 50)]
        emb = [1.0] * 10
        result = validator.validate_chunks(chunks, embeddings=[emb])
        assert len(result) == 1

    def test_dedup_counter_incremented(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("a" * 100), _make_chunk("b" * 50)]
        emb1, emb2 = _near_duplicate_pair()
        validator.validate_chunks(chunks, embeddings=[emb1, emb2])
        stats = validator.get_validation_stats()
        assert stats["flagged_duplicate"] == 1


# =============================================================================
# 5. Full pipeline tests
# =============================================================================

class TestFullPipeline:
    """End-to-end validate_chunks with mixed inputs."""

    def test_mixed_inputs(self):
        validator = ChunkValidator()
        chunks = [
            _make_chunk("too short", tier="tier1"),              # rejected
            _make_chunk("a" * 100, tier="tier1"),                # demoted
            _make_chunk("a" * 250, tier="tier1"),                # kept as tier1
            _make_chunk("a" * 50, tier="tier2"),                 # kept as tier2
        ]
        result = validator.validate_chunks(chunks)
        assert len(result) == 3
        assert result[0]["tier"] == "tier2"   # demoted
        assert result[1]["tier"] == "tier1"   # kept
        assert result[2]["tier"] == "tier2"   # was already tier2

    def test_empty_input_list(self):
        validator = ChunkValidator()
        result = validator.validate_chunks([])
        assert result == []

    def test_all_chunks_rejected(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("x"), _make_chunk("y"), _make_chunk("")]
        result = validator.validate_chunks(chunks)
        assert len(result) == 0

    def test_embeddings_length_mismatch_raises(self):
        validator = ChunkValidator()
        chunks = [_make_chunk("a" * 50)]
        with pytest.raises(ValueError, match="embeddings length"):
            validator.validate_chunks(chunks, embeddings=[[1.0], [2.0]])


# =============================================================================
# 6. Stats reporting
# =============================================================================

class TestStatsReporting:
    """get_validation_stats returns correct counts."""

    def test_stats_after_validation(self):
        validator = ChunkValidator()
        chunks = [
            _make_chunk("short"),                                 # rejected
            _make_chunk("a" * 100, tier="tier1"),                 # demoted
            _make_chunk("a" * 250, tier="tier1"),                 # kept
        ]
        validator.validate_chunks(chunks)
        stats = validator.get_validation_stats()
        assert stats["total_input"] == 3
        assert stats["rejected_short"] == 1
        assert stats["demoted_tier"] == 1
        assert stats["total_output"] == 2

    def test_stats_accumulate_across_calls(self):
        validator = ChunkValidator()
        validator.validate_chunks([_make_chunk("short")])
        validator.validate_chunks([_make_chunk("short")])
        stats = validator.get_validation_stats()
        assert stats["total_input"] == 2
        assert stats["rejected_short"] == 2

    def test_reset_stats(self):
        validator = ChunkValidator()
        validator.validate_chunks([_make_chunk("short")])
        validator.reset_stats()
        stats = validator.get_validation_stats()
        assert stats["total_input"] == 0
        assert stats["rejected_short"] == 0


# =============================================================================
# 7. validation_notes field
# =============================================================================

class TestValidationNotes:
    """validation_notes documents modifications made to each chunk."""

    def test_demoted_chunk_has_note(self):
        validator = ChunkValidator()
        content = "a" * 100
        chunks = [_make_chunk(content, tier="tier1")]
        result = validator.validate_chunks(chunks)
        notes = result[0]["validation_notes"]
        assert len(notes) == 1
        assert "tier1->tier2" in notes[0]

    def test_unmodified_chunk_has_empty_notes(self):
        validator = ChunkValidator()
        content = "a" * 250
        chunks = [_make_chunk(content, tier="tier1")]
        result = validator.validate_chunks(chunks)
        assert result[0]["validation_notes"] == []

    def test_stats_cleared_chunk_has_note(self):
        validator = ChunkValidator()
        content = "The treatment showed some improvement in patient outcomes over time consistently."
        chunks = [_make_chunk(content, section_type="results", is_key_finding=True)]
        result = validator.validate_chunks(chunks)
        notes = result[0]["validation_notes"]
        assert any("key_finding cleared" in n for n in notes)

    def test_input_not_mutated(self):
        """Original chunk dicts should not be mutated."""
        validator = ChunkValidator()
        original = _make_chunk("a" * 100, tier="tier1")
        validator.validate_chunks([original])
        assert "validation_notes" not in original
