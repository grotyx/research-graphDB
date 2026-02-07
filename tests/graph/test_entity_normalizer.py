"""Tests for entity_normalizer module.

Tests for:
- Intervention normalization (aliases)
- Outcome normalization
- Pathology normalization
- Text extraction
- Confidence scores
"""

import pytest

from src.graph.entity_normalizer import (
    EntityNormalizer,
    NormalizationResult,
    get_normalizer,
)


class TestNormalizationResult:
    """Test NormalizationResult dataclass."""

    def test_normalization_result_creation(self):
        """Test creating NormalizationResult."""
        result = NormalizationResult(
            original="BESS",
            normalized="UBE",
            confidence=1.0,
            matched_alias="BESS"
        )

        assert result.original == "BESS"
        assert result.normalized == "UBE"
        assert result.confidence == 1.0
        assert result.matched_alias == "BESS"


class TestEntityNormalizer:
    """Test EntityNormalizer class."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer instance."""
        return EntityNormalizer()

    # ========================================================================
    # Intervention Normalization Tests
    # ========================================================================

    def test_intervention_normalization_ube_variations(self, normalizer):
        """Test UBE variations normalize to UBE."""
        test_cases = [
            "UBE",
            "BESS",
            "Biportal",
            "Unilateral Biportal Endoscopic",
            "Biportal Endoscopic",
            "Biportal Endoscopy",
        ]

        for term in test_cases:
            result = normalizer.normalize_intervention(term)
            assert result.normalized == "UBE", f"Failed for: {term}"
            assert result.confidence >= 1.0

    def test_intervention_normalization_feld_variations(self, normalizer):
        """Test FELD variations normalize to FELD."""
        test_cases = [
            "FELD",
            # Note: PELD is a separate canonical term (Percutaneous Endoscopic Lumbar Discectomy)
            # FELD = Full Endoscopic Lumbar Discectomy - different procedure
            "FEID",
            "Full-Endoscopic Lumbar Discectomy",
            "Full Endoscopic Lumbar Discectomy",
        ]

        for term in test_cases:
            result = normalizer.normalize_intervention(term)
            assert result.normalized == "FELD", f"Failed for: {term}"

    def test_intervention_normalization_fusion_techniques(self, normalizer):
        """Test fusion technique normalization."""
        test_cases = {
            "TLIF": ["TLIF", "Transforaminal Lumbar Interbody Fusion"],
            "PLIF": ["PLIF", "Posterior Lumbar Interbody Fusion"],
            "ALIF": ["ALIF", "Anterior Lumbar Interbody Fusion"],
            "OLIF": ["OLIF", "Oblique Lumbar Interbody Fusion", "OLIF51"],
            "LLIF": ["LLIF", "XLIF", "DLIF", "Lateral Lumbar Interbody Fusion"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_intervention(term)
                assert result.normalized == expected, f"Failed for: {term} -> {expected}"

    def test_intervention_normalization_osteotomy(self, normalizer):
        """Test osteotomy normalization."""
        test_cases = {
            "SPO": ["SPO", "Smith-Petersen Osteotomy", "Ponte Osteotomy"],
            "PSO": ["PSO", "Pedicle Subtraction Osteotomy"],
            "VCR": ["VCR", "Vertebral Column Resection"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_intervention(term)
                assert result.normalized == expected

    def test_intervention_normalization_case_insensitive(self, normalizer):
        """Test case-insensitive matching."""
        test_cases = [
            "ube", "UBE", "Ube", "uBe",
            "tlif", "TLIF", "Tlif",
        ]

        for term in test_cases:
            result = normalizer.normalize_intervention(term)
            assert result.confidence >= 1.0

    def test_intervention_normalization_unknown_term(self, normalizer):
        """Test unknown intervention returns original."""
        result = normalizer.normalize_intervention("Unknown Surgery XYZ")

        assert result.normalized == "Unknown Surgery XYZ"
        assert result.confidence == 0.0

    def test_intervention_normalization_empty_string(self, normalizer):
        """Test empty string handling."""
        result = normalizer.normalize_intervention("")

        assert result.normalized == ""
        assert result.confidence == 0.0

    def test_intervention_normalization_partial_match(self, normalizer):
        """Test partial matching with confidence scoring."""
        # "Biportal Endoscopic Surgery" should match "Biportal Endoscopic"
        result = normalizer.normalize_intervention("Biportal Endoscopic Surgery")

        # Should match with high confidence
        assert result.normalized == "UBE"
        assert result.confidence > 0.5

    # ========================================================================
    # Outcome Normalization Tests
    # ========================================================================

    def test_outcome_normalization_vas_variations(self, normalizer):
        """Test VAS variations."""
        test_cases = [
            "VAS",
            "Visual Analog Scale",
            "Visual Analogue Scale",
            "Pain Score",
            "VAS score",
        ]

        for term in test_cases:
            result = normalizer.normalize_outcome(term)
            assert result.normalized == "VAS", f"Failed for: {term}"

    def test_outcome_normalization_clinical_scores(self, normalizer):
        """Test clinical score normalization."""
        test_cases = {
            "ODI": ["ODI", "Oswestry Disability Index", "Oswestry Score"],
            "JOA": ["JOA", "Japanese Orthopaedic Association", "JOA Score"],
            "NDI": ["NDI", "Neck Disability Index"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_outcome(term)
                assert result.normalized == expected

    def test_outcome_normalization_radiological(self, normalizer):
        """Test radiological outcome normalization."""
        test_cases = {
            "SVA": ["SVA", "Sagittal Vertical Axis", "C7 SVA"],
            "PI-LL": ["PI-LL", "PI-LL Mismatch", "PI minus LL"],
            "Cobb Angle": ["Cobb Angle", "Cobb angle", "Scoliosis angle"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_outcome(term)
                assert result.normalized == expected

    def test_outcome_normalization_fusion_complications(self, normalizer):
        """Test fusion and complication outcomes."""
        test_cases = {
            "Fusion Rate": ["Fusion Rate", "Solid fusion rate", "Bony fusion"],
            "Complication Rate": ["Complication Rate", "Adverse events"],
            "PJK": ["PJK", "Proximal Junctional Kyphosis"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_outcome(term)
                assert result.normalized == expected

    def test_outcome_normalization_quality_of_life(self, normalizer):
        """Test QoL outcome normalization."""
        test_cases = {
            "EQ-5D": ["EQ-5D", "EuroQol 5D", "EQ5D"],
            "SF-36": ["SF-36", "Short Form 36", "SF36"],
            "SRS-22": ["SRS-22", "Scoliosis Research Society 22"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_outcome(term)
                assert result.normalized == expected

    # ========================================================================
    # Pathology Normalization Tests
    # ========================================================================

    def test_pathology_normalization_lumbar_conditions(self, normalizer):
        """Test lumbar pathology normalization."""
        test_cases = {
            "Lumbar Stenosis": ["Lumbar Stenosis", "LSS", "Spinal Stenosis"],
            "Lumbar Disc Herniation": ["LDH", "HNP", "Herniated Nucleus Pulposus", "HIVD"],
            "Spondylolisthesis": ["Spondylolisthesis", "Degenerative Spondylolisthesis"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_pathology(term)
                assert result.normalized == expected

    def test_pathology_normalization_deformity(self, normalizer):
        """Test deformity pathology normalization."""
        test_cases = {
            "Degenerative Scoliosis": ["De Novo Scoliosis", "Adult Degenerative Scoliosis"],
            "AIS": ["AIS", "Adolescent Idiopathic Scoliosis"],
            "ASD": ["ASD", "Adult Spinal Deformity"],
            "Kyphosis": ["Kyphosis", "Thoracic Kyphosis"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_pathology(term)
                assert result.normalized == expected

    def test_pathology_normalization_trauma_tumor(self, normalizer):
        """Test trauma and tumor pathology normalization."""
        test_cases = {
            "Burst Fracture": ["Burst Fracture", "Vertebral Burst Fracture"],
            "Compression Fracture": ["VCF", "Vertebral Compression Fracture"],
            "Spinal Metastasis": ["Spine Metastasis", "Vertebral Metastasis"],
        }

        for expected, terms in test_cases.items():
            for term in terms:
                result = normalizer.normalize_pathology(term)
                assert result.normalized == expected

    # ========================================================================
    # Text Extraction Tests
    # ========================================================================

    def test_extract_interventions_from_text(self, normalizer):
        """Test extracting interventions from text."""
        text = "Comparison of TLIF and OLIF for treatment of lumbar stenosis"

        results = normalizer.extract_and_normalize_interventions(text)

        # Should find both TLIF and OLIF
        assert len(results) >= 2
        normalized_names = [r.normalized for r in results]
        assert "TLIF" in normalized_names
        assert "OLIF" in normalized_names

    def test_extract_interventions_multiple_aliases(self, normalizer):
        """Test extracting with multiple aliases in text."""
        text = "UBE technique (also known as BESS or Biportal Endoscopic) was performed"

        results = normalizer.extract_and_normalize_interventions(text)

        # Should find UBE only once (deduplication)
        assert len(results) == 1
        assert results[0].normalized == "UBE"

    def test_extract_interventions_case_insensitive(self, normalizer):
        """Test extraction is case-insensitive."""
        text = "tlif and plif procedures"

        results = normalizer.extract_and_normalize_interventions(text)

        normalized_names = [r.normalized for r in results]
        assert "TLIF" in normalized_names
        assert "PLIF" in normalized_names

    def test_extract_interventions_no_matches(self, normalizer):
        """Test extraction with no matches."""
        text = "This is a test with no surgical terms"

        results = normalizer.extract_and_normalize_interventions(text)

        assert len(results) == 0

    def test_extract_outcomes_from_text(self, normalizer):
        """Test extracting outcomes from text."""
        text = "VAS and ODI scores improved significantly. Fusion rate was 92%."

        results = normalizer.extract_and_normalize_outcomes(text)

        # Should find VAS, ODI, Fusion Rate
        normalized_names = [r.normalized for r in results]
        assert "VAS" in normalized_names
        assert "ODI" in normalized_names
        assert "Fusion Rate" in normalized_names

    def test_extract_outcomes_deduplication(self, normalizer):
        """Test outcome extraction deduplication."""
        text = "VAS score and Visual Analog Scale both improved"

        results = normalizer.extract_and_normalize_outcomes(text)

        # Should find VAS only once
        assert len(results) == 1
        assert results[0].normalized == "VAS"

    # ========================================================================
    # Utility Methods Tests
    # ========================================================================

    def test_normalize_all(self, normalizer):
        """Test normalize_all method."""
        text = "TLIF"

        results = normalizer.normalize_all(text)

        assert "intervention" in results
        assert "outcome" in results
        assert "pathology" in results

        # TLIF should match as intervention
        assert results["intervention"].normalized == "TLIF"
        assert results["intervention"].confidence >= 1.0

        # Should not match as outcome or pathology
        assert results["outcome"].confidence == 0.0
        assert results["pathology"].confidence == 0.0

    def test_get_all_aliases_intervention(self, normalizer):
        """Test getting all aliases for intervention."""
        aliases = normalizer.get_all_aliases("UBE", entity_type="intervention")

        assert "BESS" in aliases
        assert "Biportal" in aliases
        assert "Unilateral Biportal Endoscopic" in aliases

    def test_get_all_aliases_outcome(self, normalizer):
        """Test getting all aliases for outcome."""
        aliases = normalizer.get_all_aliases("VAS", entity_type="outcome")

        assert "Visual Analog Scale" in aliases
        assert "Pain Score" in aliases

    def test_get_all_aliases_pathology(self, normalizer):
        """Test getting all aliases for pathology."""
        aliases = normalizer.get_all_aliases("Lumbar Stenosis", entity_type="pathology")

        assert "LSS" in aliases
        assert "Spinal Stenosis" in aliases

    def test_get_all_aliases_unknown(self, normalizer):
        """Test get_all_aliases with unknown type."""
        aliases = normalizer.get_all_aliases("Test", entity_type="unknown")

        assert aliases == []

    def test_get_all_aliases_not_found(self, normalizer):
        """Test get_all_aliases with non-existent entity."""
        aliases = normalizer.get_all_aliases("NonExistent", entity_type="intervention")

        assert aliases == []

    # ========================================================================
    # Internal Logic Tests
    # ========================================================================

    def test_build_reverse_map(self, normalizer):
        """Test internal reverse map construction."""
        # Check intervention reverse map
        assert "ube" in normalizer._intervention_reverse
        assert normalizer._intervention_reverse["ube"] == "UBE"
        assert normalizer._intervention_reverse["bess"] == "UBE"

    def test_confidence_exact_match(self, normalizer):
        """Test confidence is 1.0 for exact matches."""
        result = normalizer.normalize_intervention("TLIF")
        assert result.confidence == 1.0

    def test_confidence_partial_match(self, normalizer):
        """Test confidence calculation for partial matches."""
        # Longer text containing the alias
        result = normalizer.normalize_intervention("TLIF Surgery Procedure")

        # Should match with reduced confidence
        assert result.confidence > 0.5
        assert result.confidence < 1.0

    def test_matched_alias_tracking(self, normalizer):
        """Test matched_alias is recorded."""
        result = normalizer.normalize_intervention("BESS")

        assert result.normalized == "UBE"
        assert result.matched_alias == "BESS"


class TestGetNormalizer:
    """Test singleton get_normalizer function."""

    def test_get_normalizer_singleton(self):
        """Test get_normalizer returns same instance."""
        normalizer1 = get_normalizer()
        normalizer2 = get_normalizer()

        assert normalizer1 is normalizer2

    def test_get_normalizer_works(self):
        """Test get_normalizer returns working instance."""
        normalizer = get_normalizer()

        result = normalizer.normalize_intervention("TLIF")
        assert result.normalized == "TLIF"


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_whitespace_handling(self, normalizer):
        """Test whitespace is handled correctly."""
        result = normalizer.normalize_intervention("  TLIF  ")
        assert result.normalized == "TLIF"

    def test_special_characters(self, normalizer):
        """Test handling of special characters."""
        # Should not break
        result = normalizer.normalize_intervention("TLIF-surgery")
        assert result.confidence >= 0.0

    def test_very_long_text(self, normalizer):
        """Test handling of very long text."""
        long_text = "TLIF " * 1000
        results = normalizer.extract_and_normalize_interventions(long_text)

        # Should still work and deduplicate
        assert len(results) == 1
        assert results[0].normalized == "TLIF"

    def test_unicode_handling(self, normalizer):
        """Test unicode text handling."""
        text = "척추 fusion with TLIF"
        results = normalizer.extract_and_normalize_interventions(text)

        # Should still find TLIF
        assert len(results) >= 1
        assert "TLIF" in [r.normalized for r in results]


class TestKoreanSupport:
    """Test Korean language support."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    # ========================================================================
    # Korean Intervention Tests
    # ========================================================================

    def test_korean_intervention_normalization(self, normalizer):
        """Test Korean intervention terms."""
        test_cases = {
            # Note: "Fusion Surgery" is the canonical term, "Spinal Fusion" is an alias
            "척추 유합술": "Fusion Surgery",
            "내시경 수술": "UBE",
            # Note: "Decompression Surgery" is the canonical term
            "감압술": "Decompression Surgery",
            "후방 유합술": "PLIF",
            "경추간공 유합술": "TLIF",
        }

        for korean_term, expected in test_cases.items():
            result = normalizer.normalize_intervention(korean_term)
            assert result.normalized == expected, f"Failed for: {korean_term}"
            assert result.confidence == 1.0

    def test_korean_pathology_normalization(self, normalizer):
        """Test Korean pathology terms."""
        test_cases = {
            "요추 협착증": "Lumbar Stenosis",
            "척추관 협착증": "Lumbar Stenosis",
            "추간판 탈출증": "Lumbar Disc Herniation",
            "허리 디스크": "Lumbar Disc Herniation",
            "척추 전위증": "Spondylolisthesis",
        }

        for korean_term, expected in test_cases.items():
            result = normalizer.normalize_pathology(korean_term)
            assert result.normalized == expected, f"Failed for: {korean_term}"
            assert result.confidence == 1.0

    # ========================================================================
    # Korean Particle Handling Tests
    # ========================================================================

    def test_korean_particles_with_english_acronyms(self, normalizer):
        """Test English acronyms with Korean particles."""
        test_cases = {
            "TLIF가": "TLIF",
            "OLIF와": "OLIF",
            "UBE를": "UBE",
            "MED의": "MED",
            "PLIF에": "PLIF",
        }

        for term_with_particle, expected in test_cases.items():
            result = normalizer.normalize_intervention(term_with_particle)
            assert result.normalized == expected, f"Failed for: {term_with_particle}"
            assert result.confidence >= 0.9  # Slightly lower for particle cases

    def test_particle_stripping_normalization(self, normalizer):
        """Test particle stripping in normalization."""
        # Test internal particle stripping
        result = normalizer.normalize_intervention("내시경 수술을")
        assert result.normalized == "UBE"
        assert result.confidence >= 0.9

    # ========================================================================
    # Mixed Korean/English Extraction Tests
    # ========================================================================

    def test_extract_from_mixed_korean_english(self, normalizer):
        """Test extraction from mixed Korean/English text."""
        text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"

        interventions = normalizer.extract_and_normalize_interventions(text)
        pathologies = normalizer.extract_and_normalize_pathologies(text)

        # Should find both interventions
        intervention_names = [r.normalized for r in interventions]
        assert "TLIF" in intervention_names
        assert "OLIF" in intervention_names

        # Should find pathology
        pathology_names = [r.normalized for r in pathologies]
        assert "Lumbar Stenosis" in pathology_names

    def test_extract_korean_interventions_with_particles(self, normalizer):
        """Test extracting Korean terms with particles."""
        test_texts = [
            ("TLIF가 효과적", ["TLIF"]),
            ("OLIF와 PLIF 비교", ["OLIF", "PLIF"]),
            ("내시경 수술을 시행", ["UBE"]),
        ]

        for text, expected_interventions in test_texts:
            results = normalizer.extract_and_normalize_interventions(text)
            found = [r.normalized for r in results]
            for expected in expected_interventions:
                assert expected in found, f"Failed to find {expected} in {text}"

    def test_extract_pure_korean_text(self, normalizer):
        """Test extraction from pure Korean text."""
        text = "척추 유합술과 내시경 수술 비교"

        results = normalizer.extract_and_normalize_interventions(text)
        found = [r.normalized for r in results]

        # Note: "Fusion Surgery" is the canonical term for "척추 유합술"
        assert "Fusion Surgery" in found
        assert "UBE" in found

    # ========================================================================
    # Korean Word Boundary Tests
    # ========================================================================

    def test_korean_word_boundaries(self, normalizer):
        """Test Korean text doesn't use ASCII word boundaries."""
        # Korean text should match without requiring word boundaries
        text = "척추유합술"  # No space
        result = normalizer.normalize_intervention(text)

        # Should still match (partial match)
        assert result.confidence > 0.5 or result.normalized != text

    def test_mixed_spacing_korean(self, normalizer):
        """Test Korean terms with various spacing."""
        test_cases = [
            "척추 유합술",
            "척추유합술",
        ]

        for term in test_cases:
            result = normalizer.normalize_intervention(term)
            # At least one should match perfectly
            # Note: "Fusion Surgery" is the canonical term
            if term == "척추 유합술":
                assert result.normalized == "Fusion Surgery"

    # ========================================================================
    # Korean Deduplication Tests
    # ========================================================================

    def test_korean_deduplication(self, normalizer):
        """Test Korean and English aliases deduplicate properly."""
        text = "척추 유합술 Spinal Fusion TLIF"

        results = normalizer.extract_and_normalize_interventions(text)

        # Should find TLIF and one fusion technique
        # (Spinal Fusion is normalized from Korean or English, but deduplicated)
        assert len(results) >= 2
        found = [r.normalized for r in results]
        assert "TLIF" in found

    # ========================================================================
    # Korean Edge Cases
    # ========================================================================

    def test_korean_with_numbers(self, normalizer):
        """Test Korean text with numbers."""
        text = "요추 4-5번 추간판 탈출증"

        results = normalizer.extract_and_normalize_pathologies(text)
        found = [r.normalized for r in results]

        assert "Lumbar Disc Herniation" in found

    def test_korean_particles_comprehensive(self, normalizer):
        """Test comprehensive particle handling."""
        particles_to_test = ["가", "이", "를", "을", "와", "과", "의", "에"]

        for particle in particles_to_test:
            term = f"TLIF{particle}"
            result = normalizer.normalize_intervention(term)
            assert result.normalized == "TLIF", f"Failed for particle: {particle}"
            assert result.confidence >= 0.9

    def test_korean_anatomy_terms(self, normalizer):
        """Test Korean anatomy term recognition."""
        # While not directly tested in normalization,
        # these should be handled correctly in text
        text = "요추 협착증"  # Lumbar stenosis

        result = normalizer.normalize_pathology(text)
        assert result.normalized == "Lumbar Stenosis"
