"""Evidence Level Classifier Module.

Publication type에서 근거 수준을 분류하는 모듈입니다.

Oxford Centre for Evidence-Based Medicine (OCEBM) 2011 Levels of Evidence 기준:
- Level 1a: Systematic reviews of RCTs with homogeneity
- Level 1b: Individual RCTs with narrow confidence interval
- Level 2a: Systematic reviews of cohort studies
- Level 2b: Individual cohort study (or low-quality RCT)
- Level 3: Case-control studies, or systematic review of case-control
- Level 4: Case series, poor-quality cohort/case-control
- Level 5: Expert opinion without explicit critical appraisal

Usage:
    classifier = EvidenceLevelClassifier()

    # From PubMed publication types
    level = classifier.classify_from_publication_types(["Randomized Controlled Trial"])
    print(level)  # "1b"

    # From study design description
    level = classifier.classify_from_study_design("retrospective cohort study")
    print(level)  # "2b"
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class EvidenceLevel(str, Enum):
    """근거 수준 (OCEBM 2011 기준).

    Numeric comparison supported: LEVEL_1A > LEVEL_1B > ... > LEVEL_5
    """
    LEVEL_1A = "1a"   # Meta-analysis, Systematic review of RCTs
    LEVEL_1B = "1b"   # Individual RCT
    LEVEL_2A = "2a"   # Systematic review of cohort studies
    LEVEL_2B = "2b"   # Individual cohort study
    LEVEL_3 = "3"     # Case-control study
    LEVEL_4 = "4"     # Case series
    LEVEL_5 = "5"     # Expert opinion, Unknown

    @property
    def score(self) -> int:
        """Get numeric score for comparison (higher = stronger evidence)."""
        scores = {
            "1a": 10,
            "1b": 9,
            "2a": 8,
            "2b": 7,
            "3": 5,
            "4": 3,
            "5": 1,
        }
        return scores.get(self.value, 1)

    @property
    def description(self) -> str:
        """Get human-readable description."""
        descriptions = {
            "1a": "Meta-analysis or Systematic Review of RCTs",
            "1b": "Randomized Controlled Trial",
            "2a": "Systematic Review of Cohort Studies",
            "2b": "Cohort Study or Low-quality RCT",
            "3": "Case-Control Study",
            "4": "Case Series",
            "5": "Expert Opinion or Unknown",
        }
        return descriptions.get(self.value, "Unknown")

    def __lt__(self, other: "EvidenceLevel") -> bool:
        return self.score < other.score

    def __le__(self, other: "EvidenceLevel") -> bool:
        return self.score <= other.score

    def __gt__(self, other: "EvidenceLevel") -> bool:
        return self.score > other.score

    def __ge__(self, other: "EvidenceLevel") -> bool:
        return self.score >= other.score


@dataclass
class ClassificationResult:
    """Evidence level classification result.

    Attributes:
        level: Classified evidence level
        confidence: Classification confidence (0.0-1.0)
        reason: Reason for classification
        matched_terms: Terms that triggered this classification
    """
    level: EvidenceLevel
    confidence: float
    reason: str
    matched_terms: List[str]


class EvidenceLevelClassifier:
    """근거 수준 분류기.

    Publication type, study design, MeSH terms 등에서 근거 수준을 추정합니다.

    Example:
        classifier = EvidenceLevelClassifier()

        # From PubMed publication types
        result = classifier.classify(publication_types=["Randomized Controlled Trial"])
        print(f"Level: {result.level.value}, Confidence: {result.confidence}")

        # From study design text
        result = classifier.classify(study_design="multi-center randomized trial")
        print(f"Level: {result.level.value}")
    """

    # Classification rules: (pattern, level, confidence)
    PUBLICATION_TYPE_RULES = [
        # Level 1a - Meta-analysis, Systematic Review
        (r"meta[\-\s]?analysis", EvidenceLevel.LEVEL_1A, 1.0),
        (r"systematic\s+review", EvidenceLevel.LEVEL_1A, 0.95),

        # Level 1b - RCT
        (r"randomized\s+controlled\s+trial", EvidenceLevel.LEVEL_1B, 1.0),
        (r"randomised\s+controlled\s+trial", EvidenceLevel.LEVEL_1B, 1.0),  # British spelling
        (r"clinical\s+trial.*randomized", EvidenceLevel.LEVEL_1B, 0.9),

        # Level 2a - Systematic review of cohorts
        (r"systematic\s+review.*cohort", EvidenceLevel.LEVEL_2A, 0.9),

        # Level 2b - Cohort study
        (r"cohort\s+stud", EvidenceLevel.LEVEL_2B, 0.9),
        (r"prospective\s+stud", EvidenceLevel.LEVEL_2B, 0.85),
        (r"retrospective\s+cohort", EvidenceLevel.LEVEL_2B, 0.85),
        (r"comparative\s+stud", EvidenceLevel.LEVEL_2B, 0.8),
        (r"controlled\s+clinical\s+trial", EvidenceLevel.LEVEL_2B, 0.85),

        # Level 3 - Case-control
        (r"case[\-\s]?control", EvidenceLevel.LEVEL_3, 0.9),

        # Level 4 - Case series
        (r"case\s+series", EvidenceLevel.LEVEL_4, 0.9),
        (r"case\s+report", EvidenceLevel.LEVEL_4, 0.85),
        (r"retrospective\s+stud", EvidenceLevel.LEVEL_4, 0.7),  # Without cohort

        # Level 5 - Review (not systematic), Editorial, Comment
        (r"^review$", EvidenceLevel.LEVEL_5, 0.7),
        (r"editorial", EvidenceLevel.LEVEL_5, 0.9),
        (r"comment", EvidenceLevel.LEVEL_5, 0.9),
        (r"letter", EvidenceLevel.LEVEL_5, 0.9),
        (r"guideline", EvidenceLevel.LEVEL_5, 0.7),  # Guidelines can vary
    ]

    STUDY_DESIGN_RULES = [
        # Level 1a
        (r"meta[\-\s]?analysis", EvidenceLevel.LEVEL_1A, 0.95),
        (r"systematic\s+review\s+(?:and|with)\s+meta", EvidenceLevel.LEVEL_1A, 0.95),
        (r"pooled\s+analysis", EvidenceLevel.LEVEL_1A, 0.8),

        # Level 1b
        (r"rct", EvidenceLevel.LEVEL_1B, 0.9),
        (r"randomi[sz]ed", EvidenceLevel.LEVEL_1B, 0.85),
        (r"double[\-\s]?blind", EvidenceLevel.LEVEL_1B, 0.8),
        (r"placebo[\-\s]?controlled", EvidenceLevel.LEVEL_1B, 0.8),
        (r"multi[\-\s]?center.*randomi", EvidenceLevel.LEVEL_1B, 0.9),

        # Level 2b
        (r"prospective\s+cohort", EvidenceLevel.LEVEL_2B, 0.9),
        (r"retrospective\s+cohort", EvidenceLevel.LEVEL_2B, 0.85),
        (r"longitudinal\s+stud", EvidenceLevel.LEVEL_2B, 0.8),
        (r"comparative\s+effectiveness", EvidenceLevel.LEVEL_2B, 0.85),
        (r"propensity[\-\s]?score", EvidenceLevel.LEVEL_2B, 0.8),

        # Level 3
        (r"case[\-\s]?control", EvidenceLevel.LEVEL_3, 0.9),
        (r"cross[\-\s]?sectional", EvidenceLevel.LEVEL_3, 0.8),

        # Level 4
        (r"case\s+series", EvidenceLevel.LEVEL_4, 0.9),
        (r"case\s+report", EvidenceLevel.LEVEL_4, 0.85),
        (r"retrospective\s+review", EvidenceLevel.LEVEL_4, 0.75),
        (r"single[\-\s]?center", EvidenceLevel.LEVEL_4, 0.6),  # Lowers confidence
    ]

    def classify(
        self,
        publication_types: Optional[List[str]] = None,
        study_design: Optional[str] = None,
        mesh_terms: Optional[List[str]] = None,
        title: Optional[str] = None
    ) -> ClassificationResult:
        """Classify evidence level from available information.

        Args:
            publication_types: PubMed publication types
            study_design: Study design description
            mesh_terms: MeSH terms
            title: Paper title

        Returns:
            ClassificationResult with level and confidence
        """
        results = []

        # 1. Classification from publication types (highest priority)
        if publication_types:
            result = self.classify_from_publication_types(publication_types)
            if result:
                result_conf = result.confidence * 1.0  # Full weight
                results.append((result, result_conf))

        # 2. Classification from study design
        if study_design:
            result = self.classify_from_study_design(study_design)
            if result:
                result_conf = result.confidence * 0.9  # Slightly lower weight
                results.append((result, result_conf))

        # 3. Classification from title (lowest priority)
        if title:
            result = self.classify_from_study_design(title)
            if result:
                result_conf = result.confidence * 0.7  # Lower weight for title
                results.append((result, result_conf))

        # No classification possible
        if not results:
            return ClassificationResult(
                level=EvidenceLevel.LEVEL_5,
                confidence=0.3,
                reason="No classifiable information available",
                matched_terms=[]
            )

        # Return highest confidence result
        best_result, best_conf = max(results, key=lambda x: (x[0].level.score, x[1]))
        best_result.confidence = best_conf

        return best_result

    def classify_from_publication_types(
        self,
        publication_types: List[str]
    ) -> Optional[ClassificationResult]:
        """Classify from PubMed publication types.

        Args:
            publication_types: List of publication types from PubMed

        Returns:
            ClassificationResult or None if no match
        """
        if not publication_types:
            return None

        combined_text = " ".join(publication_types).lower()
        matched = []

        for pattern, level, confidence in self.PUBLICATION_TYPE_RULES:
            if re.search(pattern, combined_text, re.IGNORECASE):
                matched.append((level, confidence, pattern))

        if not matched:
            return None

        # Get highest evidence level (lowest number = highest)
        best_match = max(matched, key=lambda x: (x[0].score, x[1]))
        level, confidence, pattern = best_match

        return ClassificationResult(
            level=level,
            confidence=confidence,
            reason=f"Matched publication type pattern: {pattern}",
            matched_terms=[t for t in publication_types if re.search(pattern, t.lower())]
        )

    def classify_from_study_design(
        self,
        study_design: str
    ) -> Optional[ClassificationResult]:
        """Classify from study design text.

        Args:
            study_design: Study design description

        Returns:
            ClassificationResult or None if no match
        """
        if not study_design:
            return None

        text = study_design.lower()
        matched = []

        for pattern, level, confidence in self.STUDY_DESIGN_RULES:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append((level, confidence, pattern))

        if not matched:
            return None

        # Get highest evidence level
        best_match = max(matched, key=lambda x: (x[0].score, x[1]))
        level, confidence, pattern = best_match

        # Find the actual matched text
        match = re.search(pattern, text, re.IGNORECASE)
        matched_text = match.group(0) if match else pattern

        return ClassificationResult(
            level=level,
            confidence=confidence,
            reason=f"Matched study design pattern: {pattern}",
            matched_terms=[matched_text]
        )

    def get_level_string(
        self,
        publication_types: List[str]
    ) -> Optional[str]:
        """Get evidence level as string (legacy API compatible).

        Args:
            publication_types: List of publication types

        Returns:
            Evidence level string ("1a", "1b", etc.) or None
        """
        result = self.classify_from_publication_types(publication_types)
        return result.level.value if result else None


# Convenience function for backward compatibility
def get_evidence_level_from_publication_type(
    publication_types: List[str]
) -> Optional[str]:
    """Get evidence level from publication types.

    Convenience function for backward compatibility with PubMedEnricher.

    Args:
        publication_types: List of publication types from PubMed

    Returns:
        Evidence level string ("1a", "1b", "2a", "2b", "3", "4") or None
    """
    classifier = EvidenceLevelClassifier()
    return classifier.get_level_string(publication_types)
