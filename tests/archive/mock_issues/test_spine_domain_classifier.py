"""Tests for Spine Domain Classifier.

척추 도메인 분류 및 정규화 테스트.
"""

import pytest
from dataclasses import dataclass, field

from src.builder.spine_domain_classifier import (
    SpineDomainClassifier,
    NormalizedIntervention,
    NormalizedOutcome,
    NormalizedPathology,
    ClassifiedSpineData,
)
from src.builder.gemini_vision_processor import (
    ExtractedMetadata,
    SpineMetadata,
    ExtractedOutcome,
)


# Mock EntityNormalizer (graph 모듈이 없을 때)
@dataclass
class MockNormalizationResult:
    original: str
    normalized: str
    confidence: float = 1.0
    matched_alias: str = ""


class MockEntityNormalizer:
    """테스트용 Mock Normalizer."""

    INTERVENTION_MAP = {
        "biportal": "UBE",
        "bess": "UBE",
        "tlif": "TLIF",
        "transforaminal fusion": "TLIF",
        "olif": "OLIF",
    }

    OUTCOME_MAP = {
        "visual analog scale": "VAS",
        "vas": "VAS",
        "oswestry": "ODI",
        "odi": "ODI",
    }

    PATHOLOGY_MAP = {
        "lumbar stenosis": "Lumbar Stenosis",
        "stenosis": "Lumbar Stenosis",
        "scoliosis": "Degenerative Scoliosis",
    }

    def normalize_intervention(self, text: str) -> MockNormalizationResult:
        text_lower = text.lower()
        normalized = self.INTERVENTION_MAP.get(text_lower, text)
        confidence = 1.0 if text_lower in self.INTERVENTION_MAP else 0.0
        return MockNormalizationResult(text, normalized, confidence)

    def normalize_outcome(self, text: str) -> MockNormalizationResult:
        text_lower = text.lower()
        normalized = self.OUTCOME_MAP.get(text_lower, text)
        confidence = 1.0 if text_lower in self.OUTCOME_MAP else 0.0
        return MockNormalizationResult(text, normalized, confidence)

    def normalize_pathology(self, text: str) -> MockNormalizationResult:
        text_lower = text.lower()
        normalized = self.PATHOLOGY_MAP.get(text_lower, text)
        confidence = 1.0 if text_lower in self.PATHOLOGY_MAP else 0.0
        return MockNormalizationResult(text, normalized, confidence)

    def get_all_aliases(self, canonical: str, entity_type: str) -> list[str]:
        if entity_type == "intervention" and canonical == "UBE":
            return ["BESS", "Biportal", "Unilateral Biportal Endoscopic"]
        if entity_type == "intervention" and canonical == "TLIF":
            return ["Transforaminal Interbody Fusion", "Transforaminal Fusion"]
        return []

    def extract_and_normalize_interventions(self, text: str) -> list[MockNormalizationResult]:
        results = []
        text_lower = text.lower()
        if "tlif" in text_lower:
            results.append(MockNormalizationResult("TLIF", "TLIF", 1.0))
        if "olif" in text_lower:
            results.append(MockNormalizationResult("OLIF", "OLIF", 1.0))
        return results

    def extract_and_normalize_outcomes(self, text: str) -> list[MockNormalizationResult]:
        results = []
        text_lower = text.lower()
        if "vas" in text_lower:
            results.append(MockNormalizationResult("VAS", "VAS", 1.0))
        if "odi" in text_lower:
            results.append(MockNormalizationResult("ODI", "ODI", 1.0))
        return results


class TestSpineDomainClassifier:
    """SpineDomainClassifier 테스트."""

    @pytest.fixture
    def mock_normalizer(self):
        return MockEntityNormalizer()

    @pytest.fixture
    def classifier(self, mock_normalizer):
        return SpineDomainClassifier(normalizer=mock_normalizer)

    def test_classify_and_normalize_basic(self, classifier):
        """기본 분류 및 정규화 테스트."""
        # Given
        spine_meta = SpineMetadata(
            sub_domain="Degenerative",
            pathology="Lumbar Stenosis",
            anatomy_level="L4-5",
            interventions=["TLIF", "BESS"],
            outcomes=[
                ExtractedOutcome(
                    name="VAS",
                    value_intervention="2.1",
                    value_control="5.3",
                    p_value="0.001"
                ),
                ExtractedOutcome(
                    name="ODI",
                    value_intervention="15",
                    value_control="35",
                    p_value="<0.001"
                ),
            ]
        )

        metadata = ExtractedMetadata(
            title="Test Paper",
            authors=["Author A"],
            year=2024,
            spine=spine_meta
        )

        # When
        result = classifier.classify_and_normalize(metadata)

        # Then
        assert result.sub_domain == "Degenerative"
        assert result.pathology.normalized == "Lumbar Stenosis"
        assert result.anatomy_level == "L4-5"
        assert len(result.interventions) == 2
        assert result.interventions[0].normalized == "TLIF"
        assert result.interventions[1].normalized == "UBE"  # BESS → UBE
        assert len(result.outcomes) == 2
        assert result.outcomes[0].normalized == "VAS"
        assert result.outcomes[0].value_intervention == "2.1"
        assert result.outcomes[0].p_value == "0.001"

    def test_anatomy_level_validation(self, classifier):
        """Anatomy Level 정규화 테스트."""
        # L4-L5 → L4-5
        assert classifier._validate_anatomy_level("L4-L5") == "L4-5"
        assert classifier._validate_anatomy_level("C5-C6") == "C5-6"
        assert classifier._validate_anatomy_level("l4-5") == "L4-5"
        assert classifier._validate_anatomy_level("  L4-5  ") == "L4-5"

    def test_extract_from_text(self, classifier):
        """텍스트로부터 추출 테스트."""
        # Given
        text = "Comparison of TLIF and OLIF for L4-5 stenosis. VAS and ODI improved."

        # When
        result = classifier.extract_from_text(text, sub_domain="Degenerative")

        # Then
        assert result.sub_domain == "Degenerative"
        assert len(result.interventions) == 2
        assert "TLIF" in [i.normalized for i in result.interventions]
        assert "OLIF" in [i.normalized for i in result.interventions]
        assert len(result.outcomes) == 2
        assert "VAS" in [o.normalized for o in result.outcomes]
        assert "ODI" in [o.normalized for o in result.outcomes]
        assert result.anatomy_level == "L4-5"

    def test_extract_anatomy_from_text(self, classifier):
        """텍스트에서 해부학 레벨 추출 테스트."""
        # Given
        texts = [
            "Surgery at L4-5 level",
            "C5-6 discectomy performed",
            "Fusion from L4 to L5",
            "T10-L2 instrumentation",
        ]

        # When/Then
        assert "L4-5" in classifier._extract_anatomy_from_text(texts[0])
        assert "C5-6" in classifier._extract_anatomy_from_text(texts[1])
        assert "L4-5" in classifier._extract_anatomy_from_text(texts[2])
        assert "T10-L2" in classifier._extract_anatomy_from_text(texts[3])

    def test_empty_data_handling(self, classifier):
        """빈 데이터 처리 테스트."""
        # Given
        spine_meta = SpineMetadata()
        metadata = ExtractedMetadata(
            title="Test",
            authors=[],
            year=2024,
            spine=spine_meta
        )

        # When
        result = classifier.classify_and_normalize(metadata)

        # Then
        assert result.sub_domain == "Not Applicable"
        assert result.pathology.normalized == ""
        assert result.anatomy_level == ""
        assert len(result.interventions) == 0
        assert len(result.outcomes) == 0

    def test_intervention_aliases(self, classifier):
        """수술법 별칭 테스트."""
        # Given
        spine_meta = SpineMetadata(
            sub_domain="Degenerative",
            pathology="",
            anatomy_level="",
            interventions=["BESS", "Biportal"],
            outcomes=[]
        )
        metadata = ExtractedMetadata(spine=spine_meta)

        # When
        result = classifier.classify_and_normalize(metadata)

        # Then
        # 모두 UBE로 정규화되어야 함
        assert len(result.interventions) == 2
        assert all(i.normalized == "UBE" for i in result.interventions)
        assert len(result.interventions[0].aliases) > 0


class TestWithoutNormalizer:
    """Normalizer 없이 동작 테스트."""

    def test_classifier_without_normalizer(self):
        """Normalizer 없이도 동작하는지 확인."""
        # Given
        classifier = SpineDomainClassifier(normalizer=None)
        spine_meta = SpineMetadata(
            sub_domain="Degenerative",
            pathology="Stenosis",
            anatomy_level="L4-5",
            interventions=["TLIF"],
            outcomes=[
                ExtractedOutcome(name="VAS", value_intervention="2.0")
            ]
        )
        metadata = ExtractedMetadata(spine=spine_meta)

        # When
        result = classifier.classify_and_normalize(metadata)

        # Then - 정규화 없이 원본 그대로 반환
        assert result.sub_domain == "Degenerative"
        assert result.pathology.normalized == "Stenosis"
        assert result.interventions[0].normalized == "TLIF"
        assert result.outcomes[0].normalized == "VAS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
