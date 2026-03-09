"""Study Type Detection Examples (v6 - Archived).

Archived on: 2025-12-18

This file shows how study type detection was used in v6
to recommend appropriate effect measures for LLM extraction.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "modules"))

from study_type_detector import StudyTypeDetector, StudyType


def example_rct_detection():
    """Example: RCT detection from abstract."""
    detector = StudyTypeDetector()

    abstract = """
    This randomized controlled trial compared UBE decompression to open laminectomy
    for lumbar stenosis. Patients were randomly assigned to either UBE (n=50) or
    open surgery (n=48). Primary outcome was VAS at 1-year follow-up. Results showed
    mean VAS difference of -1.4 (95% CI: -2.1 to -0.7, p=0.001, Cohen's d = 0.8).
    """

    result = detector.detect(
        abstract=abstract,
        publication_types=["Randomized Controlled Trial"],
        mesh_terms=["Randomized Controlled Trial", "Lumbar Vertebrae", "Decompression"]
    )

    print("=== RCT Detection ===")
    print(f"Study Type: {result.study_type.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Detection Sources: {', '.join(result.detection_sources)}")
    print(f"Recommended Measures: {', '.join(result.recommended_measures)}")
    print(f"Expected: MD, SMD, Cohen_d, RR, NNT")
    print()


def example_cohort_detection():
    """Example: Cohort study detection with survival analysis."""
    detector = StudyTypeDetector()

    abstract = """
    This retrospective cohort study evaluated long-term outcomes after en bloc
    resection for spinal metastases. Cox regression analysis showed hazard ratio
    of 2.35 (95% CI: 1.42-3.89, p=0.001) for overall survival. Kaplan-Meier
    curves demonstrated median survival of 24 months.
    """

    result = detector.detect(
        abstract=abstract,
        publication_types=["Observational Study"],
        mesh_terms=["Retrospective Studies", "Cohort Studies", "Survival Analysis"]
    )

    print("=== Cohort Detection ===")
    print(f"Study Type: {result.study_type.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Detection Sources: {', '.join(result.detection_sources)}")
    print(f"Recommended Measures: {', '.join(result.recommended_measures)}")
    print(f"Expected: HR, OR, RR")
    print()


def example_meta_analysis_detection():
    """Example: Meta-analysis detection."""
    detector = StudyTypeDetector()

    abstract = """
    This systematic review and meta-analysis pooled data from 15 RCTs comparing
    endoscopic versus open decompression. The pooled SMD was -0.45 (95% CI: -0.67
    to -0.23, p<0.001) favoring endoscopic approach. Heterogeneity was moderate
    (I²=42%).
    """

    result = detector.detect(
        abstract=abstract,
        publication_types=["Meta-Analysis", "Systematic Review"],
        mesh_terms=["Meta-Analysis", "Systematic Review"]
    )

    print("=== Meta-Analysis Detection ===")
    print(f"Study Type: {result.study_type.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Detection Sources: {', '.join(result.detection_sources)}")
    print(f"Recommended Measures: {', '.join(result.recommended_measures)}")
    print(f"Expected: SMD, MD, OR, RR, HR, I2")
    print()


def example_case_control_detection():
    """Example: Case-control study detection."""
    detector = StudyTypeDetector()

    abstract = """
    This case-control study investigated risk factors for adjacent segment disease
    after lumbar fusion. Cases (n=45) with ASD were matched with controls (n=90)
    without ASD. Multivariate analysis showed odds ratio of 3.2 (95% CI: 1.8-5.6,
    p<0.001) for age >65 years.
    """

    result = detector.detect(
        abstract=abstract,
        publication_types=["Case-Control Studies"],
        mesh_terms=["Case-Control Studies"]
    )

    print("=== Case-Control Detection ===")
    print(f"Study Type: {result.study_type.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Detection Sources: {', '.join(result.detection_sources)}")
    print(f"Recommended Measures: {', '.join(result.recommended_measures)}")
    print(f"Expected: OR")
    print()


def example_prompt_enhancement():
    """Example: Enhancing LLM prompt with study type hints."""
    detector = StudyTypeDetector()

    abstract = "This randomized trial compared TLIF to ALIF for L4-5 spondylolisthesis."

    result = detector.detect(
        abstract=abstract,
        title="TLIF vs ALIF: A Randomized Trial"
    )

    base_prompt = """Analyze this paper and extract outcomes with statistical values."""

    enhanced_prompt = detector.enhance_prompt_with_study_type(base_prompt, result)

    print("=== Prompt Enhancement ===")
    print("Original Prompt:")
    print(base_prompt)
    print()
    print("Enhanced Prompt:")
    print(enhanced_prompt)
    print()


def example_unknown_detection():
    """Example: Unknown study type (no clear signals)."""
    detector = StudyTypeDetector()

    abstract = """
    This paper discusses the history and development of spine surgery techniques
    over the past century. Various approaches are reviewed.
    """

    result = detector.detect(
        abstract=abstract,
        publication_types=["Review"]  # Narrative review, not systematic
    )

    print("=== Unknown/Narrative Review ===")
    print(f"Study Type: {result.study_type.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Detection Sources: {', '.join(result.detection_sources)}")
    print(f"Recommended Measures: {', '.join(result.recommended_measures)}")
    print(f"Expected: Generic measures (MD, OR, HR, RR)")
    print()


if __name__ == "__main__":
    print("Study Type Detection Examples (v6 Archive)\n")
    print("=" * 60)
    print()

    example_rct_detection()
    example_cohort_detection()
    example_meta_analysis_detection()
    example_case_control_detection()
    example_prompt_enhancement()
    example_unknown_detection()

    print("=" * 60)
    print("\nNote: In v7.0, study type detection is simplified and")
    print("effect measures come from analysis tools, not LLM extraction.")
