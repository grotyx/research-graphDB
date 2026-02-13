"""Tests for EntityNormalizer v7.15 QC - Alias Integrity After Duplicate Key Merge.

The v7.15 QC merged duplicate dictionary keys in OUTCOME_ALIASES and
PATHOLOGY_ALIASES. Previously, Python silently discarded earlier entries
when the same key appeared twice. After the merge, ALL aliases from both
former entries must be accessible under the single canonical key.

This file tests:
1. SF-12 (Outcome) - all aliases accessible
2. Cervical Myelopathy (Pathology) - all aliases accessible, including DCM and CSM
3. PJK (Outcome + Pathology) - both dictionaries have complete alias lists
4. DJK (Pathology) - all aliases accessible
5. Adjacent Segment Disease (Pathology) - all aliases accessible, including Korean
6. General alias integrity: no data loss in normalization lookups
"""

import pytest

from src.graph.entity_normalizer import (
    EntityNormalizer,
    NormalizationResult,
    get_normalizer,
)


class TestSF12AliasIntegrity:
    """Verify SF-12 outcome aliases are all accessible after merge."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_sf12_canonical_normalization(self, normalizer):
        """SF-12 itself normalizes to SF-12."""
        result = normalizer.normalize_outcome("SF-12")
        assert result.normalized == "SF-12"
        assert result.confidence >= 1.0

    def test_sf12_short_form_alias(self, normalizer):
        """'Short Form 12' normalizes to SF-12."""
        result = normalizer.normalize_outcome("Short Form 12")
        assert result.normalized == "SF-12"
        assert result.confidence >= 1.0

    def test_sf12_no_hyphen(self, normalizer):
        """'SF12' normalizes to SF-12."""
        result = normalizer.normalize_outcome("SF12")
        assert result.normalized == "SF-12"
        assert result.confidence >= 1.0

    def test_sf12_with_score_suffix(self, normalizer):
        """'SF-12 score' normalizes to SF-12."""
        result = normalizer.normalize_outcome("SF-12 score")
        assert result.normalized == "SF-12"
        assert result.confidence > 0.5

    def test_sf12_space_variant(self, normalizer):
        """'SF 12' normalizes to SF-12."""
        result = normalizer.normalize_outcome("SF 12")
        assert result.normalized == "SF-12"
        assert result.confidence >= 1.0

    def test_sf12_lowercase(self, normalizer):
        """'sf-12' normalizes to SF-12."""
        result = normalizer.normalize_outcome("sf-12")
        assert result.normalized == "SF-12"
        assert result.confidence >= 1.0

    def test_sf12_all_aliases_in_dict(self, normalizer):
        """All expected SF-12 aliases are present in OUTCOME_ALIASES."""
        expected_aliases = ["Short Form 12", "SF12", "SF-12 score", "SF 12",
                            "sf-12", "Sf-12", "sf12"]
        actual_aliases = normalizer.OUTCOME_ALIASES.get("SF-12", [])
        for alias in expected_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from SF-12 OUTCOME_ALIASES. "
                f"Possible data loss during duplicate key merge."
            )


class TestCervicalMyelopathyAliasIntegrity:
    """Verify Cervical Myelopathy pathology aliases after merge."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_cervical_myelopathy_canonical(self, normalizer):
        """'Cervical Myelopathy' normalizes to itself."""
        result = normalizer.normalize_pathology("Cervical Myelopathy")
        assert result.normalized == "Cervical Myelopathy"
        assert result.confidence >= 1.0

    def test_dcm_alias(self, normalizer):
        """'DCM' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("DCM")
        assert result.normalized == "Cervical Myelopathy"

    def test_csm_alias(self, normalizer):
        """'CSM' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("CSM")
        assert result.normalized == "Cervical Myelopathy"

    def test_degenerative_cervical_myelopathy(self, normalizer):
        """'Degenerative cervical myelopathy' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("Degenerative cervical myelopathy")
        assert result.normalized == "Cervical Myelopathy"

    def test_cervical_spondylotic_myelopathy(self, normalizer):
        """'Cervical Spondylotic Myelopathy' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("Cervical Spondylotic Myelopathy")
        assert result.normalized == "Cervical Myelopathy"

    def test_myelopathy_short_form(self, normalizer):
        """'Myelopathy' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("Myelopathy")
        assert result.normalized == "Cervical Myelopathy"

    def test_korean_cervical_myelopathy(self, normalizer):
        """Korean term normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("경추 척수병증")
        assert result.normalized == "Cervical Myelopathy"

    def test_cervical_cord_compression(self, normalizer):
        """'Cervical cord compression' normalizes to Cervical Myelopathy."""
        result = normalizer.normalize_pathology("Cervical cord compression")
        assert result.normalized == "Cervical Myelopathy"

    def test_cervical_myelopathy_all_aliases_in_dict(self, normalizer):
        """All expected Cervical Myelopathy aliases are in PATHOLOGY_ALIASES."""
        expected_aliases = [
            "Degenerative cervical myelopathy", "degenerative cervical myelopathy",
            "DCM", "Cervical spondylotic myelopathy",
            "cervical myelopathy", "Myelopathy",
            "CSM", "Cervical Spondylotic Myelopathy",
            "Cervical cord compression", "경추 척수병증",
        ]
        actual_aliases = normalizer.PATHOLOGY_ALIASES.get("Cervical Myelopathy", [])
        for alias in expected_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from Cervical Myelopathy PATHOLOGY_ALIASES. "
                f"Possible data loss during v7.15 duplicate key merge."
            )


class TestPJKAliasIntegrity:
    """Verify PJK aliases in BOTH Outcome and Pathology dictionaries."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    # --- PJK as Outcome ---

    def test_pjk_outcome_canonical(self, normalizer):
        """PJK normalizes to PJK as outcome."""
        result = normalizer.normalize_outcome("PJK")
        assert result.normalized == "PJK"
        assert result.confidence >= 1.0

    def test_pjk_outcome_proximal_junctional_kyphosis(self, normalizer):
        """'Proximal Junctional Kyphosis' normalizes to PJK outcome."""
        result = normalizer.normalize_outcome("Proximal Junctional Kyphosis")
        assert result.normalized == "PJK"

    def test_pjk_outcome_incidence(self, normalizer):
        """'PJK incidence' normalizes to PJK outcome."""
        result = normalizer.normalize_outcome("PJK incidence")
        assert result.normalized == "PJK"

    def test_pjk_outcome_rate(self, normalizer):
        """'PJK rate' normalizes to PJK outcome."""
        result = normalizer.normalize_outcome("PJK rate")
        assert result.normalized == "PJK"

    def test_pjk_outcome_proximal_junctional_failure(self, normalizer):
        """'Proximal junctional failure' normalizes to PJK outcome."""
        result = normalizer.normalize_outcome("Proximal junctional failure")
        assert result.normalized == "PJK"

    def test_pjk_outcome_aliases_in_dict(self, normalizer):
        """PJK outcome aliases contain all expected entries."""
        expected_outcome_aliases = [
            "Proximal Junctional Kyphosis",
            "PJK incidence", "PJK rate", "Proximal junctional failure"
        ]
        actual_aliases = normalizer.OUTCOME_ALIASES.get("PJK", [])
        for alias in expected_outcome_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from PJK OUTCOME_ALIASES."
            )

    # --- PJK as Pathology ---

    def test_pjk_pathology_canonical(self, normalizer):
        """PJK normalizes to PJK as pathology."""
        result = normalizer.normalize_pathology("PJK")
        assert result.normalized == "PJK"
        assert result.confidence >= 1.0

    def test_pjk_pathology_pjf(self, normalizer):
        """'PJF' normalizes to PJK as pathology."""
        result = normalizer.normalize_pathology("PJF")
        assert result.normalized == "PJK"

    def test_pjk_pathology_junctional_kyphosis(self, normalizer):
        """'Junctional kyphosis' normalizes to PJK as pathology."""
        result = normalizer.normalize_pathology("Junctional kyphosis")
        assert result.normalized == "PJK"

    def test_pjk_pathology_korean(self, normalizer):
        """Korean PJK term normalizes correctly."""
        result = normalizer.normalize_pathology("근위부 접합부 후만")
        assert result.normalized == "PJK"

    def test_pjk_pathology_aliases_in_dict(self, normalizer):
        """PJK pathology aliases contain all expected entries (post-merge)."""
        expected_pathology_aliases = [
            "Proximal Junctional Kyphosis", "proximal junctional kyphosis",
            "PJF", "Proximal junctional failure", "proximal junctional failure",
            "Junctional kyphosis", "junctional kyphosis",
            "근위부 접합부 후만",
        ]
        actual_aliases = normalizer.PATHOLOGY_ALIASES.get("PJK", [])
        for alias in expected_pathology_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from PJK PATHOLOGY_ALIASES. "
                f"Possible data loss during v7.15 duplicate key merge."
            )


class TestDJKAliasIntegrity:
    """Verify DJK pathology aliases after merge."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_djk_canonical(self, normalizer):
        """DJK normalizes to DJK as pathology."""
        result = normalizer.normalize_pathology("DJK")
        assert result.normalized == "DJK"
        assert result.confidence >= 1.0

    def test_djk_distal_junctional_kyphosis(self, normalizer):
        """'Distal Junctional Kyphosis' normalizes to DJK."""
        result = normalizer.normalize_pathology("Distal Junctional Kyphosis")
        assert result.normalized == "DJK"

    def test_djk_lowercase(self, normalizer):
        """'distal junctional kyphosis' normalizes to DJK."""
        result = normalizer.normalize_pathology("distal junctional kyphosis")
        assert result.normalized == "DJK"

    def test_djk_failure(self, normalizer):
        """'Distal junctional failure' normalizes to DJK."""
        result = normalizer.normalize_pathology("Distal junctional failure")
        assert result.normalized == "DJK"

    def test_djk_all_aliases_in_dict(self, normalizer):
        """DJK pathology aliases contain all expected entries."""
        expected_aliases = [
            "Distal Junctional Kyphosis", "distal junctional kyphosis",
            "Distal junctional failure",
        ]
        actual_aliases = normalizer.PATHOLOGY_ALIASES.get("DJK", [])
        for alias in expected_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from DJK PATHOLOGY_ALIASES."
            )


class TestAdjacentSegmentDiseaseAliasIntegrity:
    """Verify Adjacent Segment Disease pathology aliases after merge."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_asd_pathology_canonical(self, normalizer):
        """'Adjacent Segment Disease' normalizes to itself."""
        result = normalizer.normalize_pathology("Adjacent Segment Disease")
        assert result.normalized == "Adjacent Segment Disease"
        assert result.confidence >= 1.0

    def test_asd_adjacent_segment_lowercase(self, normalizer):
        """'adjacent segment disease' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("adjacent segment disease")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_adjacent_segment_degeneration(self, normalizer):
        """'Adjacent segment degeneration' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("Adjacent segment degeneration")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_adjacent_level_disease(self, normalizer):
        """'Adjacent level disease' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("Adjacent level disease")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_radiographic(self, normalizer):
        """'Radiographic ASD' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("Radiographic ASD")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asdis(self, normalizer):
        """'ASDis' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("ASDis")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_korean(self, normalizer):
        """Korean term normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("인접분절 퇴행")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_adjacent_segment_tag(self, normalizer):
        """'ASD (Adjacent Segment)' normalizes to Adjacent Segment Disease."""
        result = normalizer.normalize_pathology("ASD (Adjacent Segment)")
        assert result.normalized == "Adjacent Segment Disease"

    def test_asd_pathology_all_aliases_in_dict(self, normalizer):
        """Adjacent Segment Disease pathology aliases contain all expected entries."""
        expected_aliases = [
            "adjacent segment disease", "ASD (Adjacent Segment)",
            "Adjacent segment degeneration", "adjacent segment degeneration",
            "Adjacent level disease", "Radiographic ASD",
            "ASDis", "인접분절 퇴행",
        ]
        actual_aliases = normalizer.PATHOLOGY_ALIASES.get("Adjacent Segment Disease", [])
        for alias in expected_aliases:
            assert alias in actual_aliases, (
                f"Alias '{alias}' missing from Adjacent Segment Disease PATHOLOGY_ALIASES. "
                f"Possible data loss during v7.15 duplicate key merge."
            )


class TestASDOutcomeVsPathologyDisambiguation:
    """Verify that 'ASD' as Outcome (complication metric) and as Pathology (deformity)
    are properly separated and each has correct aliases."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_asd_outcome_is_complication(self, normalizer):
        """ASD as outcome refers to Adjacent Segment Disease (complication metric)."""
        result = normalizer.normalize_outcome("ASD")
        # In OUTCOME_ALIASES, "ASD" is a key with aliases like "Adjacent Segment Disease"
        assert result.normalized == "ASD"

    def test_asd_pathology_is_deformity(self, normalizer):
        """ASD as pathology refers to Adult Spinal Deformity."""
        result = normalizer.normalize_pathology("ASD")
        # In PATHOLOGY_ALIASES, "ASD" is a key with aliases like "Adult Spinal Deformity"
        assert result.normalized == "ASD"

    def test_asd_outcome_aliases_complete(self, normalizer):
        """ASD outcome aliases contain adjacent segment disease terms."""
        aliases = normalizer.OUTCOME_ALIASES.get("ASD", [])
        assert "Adjacent Segment Disease" in aliases
        assert "Adjacent segment degeneration" in aliases

    def test_asd_pathology_aliases_complete(self, normalizer):
        """ASD pathology aliases contain adult spinal deformity terms."""
        aliases = normalizer.PATHOLOGY_ALIASES.get("ASD", [])
        assert "Adult Spinal Deformity" in aliases


class TestNoDuplicateKeysInDictionaries:
    """Verify that there are no duplicate keys remaining in alias dictionaries.

    Python dict does not allow true duplicate keys -- the last definition wins.
    This test catches the symptom: if aliases that belong to the canonical
    entry are missing, it means a later duplicate overwrote the first.
    """

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_outcome_alias_counts_reasonable(self, normalizer):
        """Each outcome with known aliases should have a non-trivial alias list."""
        # These were the entries that had duplicate key issues
        problematic_outcomes = {
            "SF-12": 5,   # Minimum expected alias count
            "PJK": 3,     # Minimum expected alias count
        }
        for canonical, min_count in problematic_outcomes.items():
            aliases = normalizer.OUTCOME_ALIASES.get(canonical, [])
            assert len(aliases) >= min_count, (
                f"OUTCOME_ALIASES['{canonical}'] has only {len(aliases)} aliases, "
                f"expected at least {min_count}. Possible data loss from duplicate key."
            )

    def test_pathology_alias_counts_reasonable(self, normalizer):
        """Each pathology with known aliases should have a non-trivial alias list."""
        problematic_pathologies = {
            "Cervical Myelopathy": 8,
            "PJK": 6,
            "DJK": 2,
            "Adjacent Segment Disease": 6,
        }
        for canonical, min_count in problematic_pathologies.items():
            aliases = normalizer.PATHOLOGY_ALIASES.get(canonical, [])
            assert len(aliases) >= min_count, (
                f"PATHOLOGY_ALIASES['{canonical}'] has only {len(aliases)} aliases, "
                f"expected at least {min_count}. Possible data loss from duplicate key."
            )


class TestReverseMapIntegrity:
    """Verify that the internal reverse map contains all expected aliases."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_reverse_map_for_sf12(self, normalizer):
        """SF-12 aliases are all in the outcome reverse map."""
        for alias in ["sf-12", "sf12", "short form 12", "sf 12"]:
            assert alias in normalizer._outcome_reverse, (
                f"Alias '{alias}' not found in outcome reverse map for SF-12"
            )
            assert normalizer._outcome_reverse[alias] == "SF-12"

    def test_reverse_map_for_pjk_outcome(self, normalizer):
        """PJK outcome aliases are in the outcome reverse map."""
        for alias in ["pjk", "proximal junctional kyphosis", "pjk rate"]:
            assert alias in normalizer._outcome_reverse, (
                f"Alias '{alias}' not found in outcome reverse map for PJK"
            )
            assert normalizer._outcome_reverse[alias] == "PJK"

    def test_reverse_map_for_cervical_myelopathy(self, normalizer):
        """Cervical Myelopathy aliases are in the pathology reverse map."""
        for alias in ["dcm", "csm", "cervical myelopathy", "myelopathy"]:
            assert alias in normalizer._pathology_reverse, (
                f"Alias '{alias}' not found in pathology reverse map for Cervical Myelopathy"
            )
            assert normalizer._pathology_reverse[alias] == "Cervical Myelopathy"


class TestExtractionWithMergedAliases:
    """Verify that text extraction works correctly with merged aliases."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_extract_sf12_from_text(self, normalizer):
        """Extracting SF-12 from text works after alias merge."""
        text = "Patients showed significant improvement on SF-12 physical component."
        results = normalizer.extract_and_normalize_outcomes(text)
        found = [r.normalized for r in results]
        assert "SF-12" in found

    def test_extract_cervical_myelopathy_from_text(self, normalizer):
        """Extracting Cervical Myelopathy from text works after alias merge."""
        text = "Patient presented with degenerative cervical myelopathy symptoms."
        results = normalizer.extract_and_normalize_pathologies(text)
        found = [r.normalized for r in results]
        assert "Cervical Myelopathy" in found

    def test_extract_pjk_from_text(self, normalizer):
        """Extracting PJK from text works after alias merge."""
        text = "Proximal junctional kyphosis was observed in 15% of cases."
        outcome_results = normalizer.extract_and_normalize_outcomes(text)
        pathology_results = normalizer.extract_and_normalize_pathologies(text)
        all_found = ([r.normalized for r in outcome_results] +
                     [r.normalized for r in pathology_results])
        assert "PJK" in all_found

    def test_extract_adjacent_segment_disease_from_text(self, normalizer):
        """Extracting Adjacent Segment Disease from text works after merge."""
        text = "Adjacent segment degeneration was found at the cranial level."
        results = normalizer.extract_and_normalize_pathologies(text)
        found = [r.normalized for r in results]
        assert "Adjacent Segment Disease" in found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
