"""Spine Graph Schema Enums Module.

척추 수술 특화 그래프 스키마의 모든 열거형 정의.
- 도메인 분류: SpineSubDomain
- 근거 수준: EvidenceLevel
- 연구 설계: StudyDesign
- 결과변수: OutcomeType
- 수술 분류: InterventionCategory
- 논문 관계: PaperRelationType
- 문서 유형: DocumentType
- 엔티티 카테고리: EntityCategory
- 인용 컨텍스트: CitationContext
"""

import re
from enum import Enum


class SpineSubDomain(Enum):
    """척추 하위 도메인."""
    DEGENERATIVE = "Degenerative"
    DEFORMITY = "Deformity"
    TRAUMA = "Trauma"
    TUMOR = "Tumor"
    BASIC_SCIENCE = "Basic Science"


class EvidenceLevel(Enum):
    """근거 수준 (Oxford Centre for Evidence-Based Medicine).

    9-level scale used across study_classifier, models, tiered_search, multi_factor_ranker.
    """
    LEVEL_1A = "1a"  # Meta-analysis of RCTs
    LEVEL_1B = "1b"  # Individual RCT
    LEVEL_2A = "2a"  # Systematic review of cohort studies
    LEVEL_2B = "2b"  # Individual cohort study
    LEVEL_2C = "2c"  # Outcomes research
    LEVEL_3A = "3a"  # Systematic review of case-control studies
    LEVEL_3B = "3b"  # Individual case-control study
    LEVEL_4 = "4"    # Case series
    LEVEL_5 = "5"    # Expert opinion


class StudyDesign(Enum):
    """연구 설계 유형."""
    META_ANALYSIS = "meta-analysis"
    SYSTEMATIC_REVIEW = "systematic-review"
    RCT = "RCT"
    PROSPECTIVE_COHORT = "prospective-cohort"
    RETROSPECTIVE_COHORT = "retrospective-cohort"
    CASE_CONTROL = "case-control"
    CASE_SERIES = "case-series"
    CASE_REPORT = "case-report"
    EXPERT_OPINION = "expert-opinion"
    CROSS_SECTIONAL = "cross-sectional"
    OTHER = "other"


# ---------------------------------------------------------------------------
# study_design normalization — maps all known variant forms to canonical values
# ---------------------------------------------------------------------------

# Canonical values are the StudyDesign enum .value strings above.
# This mapping handles underscore/hyphen variants, abbreviations, long forms,
# and the values produced by study_classifier.py, study_type_detector.py,
# classify_papers.py, and free-form LLM outputs.

_STUDY_DESIGN_ALIAS_MAP: dict[str, str] = {
    # ── meta-analysis ──
    "meta-analysis": "meta-analysis",
    "meta_analysis": "meta-analysis",
    "meta analysis": "meta-analysis",
    "metaanalysis": "meta-analysis",
    "pooled analysis": "meta-analysis",
    "pooled_analysis": "meta-analysis",

    # ── systematic-review ──
    "systematic-review": "systematic-review",
    "systematic_review": "systematic-review",
    "systematic review": "systematic-review",
    "scoping review": "systematic-review",
    "scoping_review": "systematic-review",
    "literature review": "systematic-review",
    "literature_review": "systematic-review",

    # ── RCT ──
    "rct": "RCT",
    "randomized": "RCT",
    "randomised": "RCT",
    "randomized_controlled_trial": "RCT",
    "randomised_controlled_trial": "RCT",
    "randomized controlled trial": "RCT",
    "randomised controlled trial": "RCT",
    "randomized trial": "RCT",
    "randomised trial": "RCT",
    "randomized clinical trial": "RCT",
    "controlled trial": "RCT",
    "controlled_trial": "RCT",
    "double-blind": "RCT",
    "double_blind": "RCT",
    "single-blind": "RCT",
    "single_blind": "RCT",

    # ── prospective-cohort ──
    "prospective-cohort": "prospective-cohort",
    "prospective_cohort": "prospective-cohort",
    "prospective cohort": "prospective-cohort",
    "prospective study": "prospective-cohort",
    "prospective_study": "prospective-cohort",
    "longitudinal": "prospective-cohort",
    "longitudinal study": "prospective-cohort",
    "longitudinal_study": "prospective-cohort",
    "follow-up study": "prospective-cohort",
    "follow_up_study": "prospective-cohort",

    # ── retrospective-cohort ──
    "retrospective-cohort": "retrospective-cohort",
    "retrospective_cohort": "retrospective-cohort",
    "retrospective cohort": "retrospective-cohort",
    "retrospective": "retrospective-cohort",
    "retrospective study": "retrospective-cohort",
    "retrospective_study": "retrospective-cohort",
    "retrospective review": "retrospective-cohort",
    "retrospective_review": "retrospective-cohort",
    "chart review": "retrospective-cohort",
    "chart_review": "retrospective-cohort",
    "medical record": "retrospective-cohort",

    # ── cohort (ambiguous → retrospective-cohort as safer default) ──
    "cohort": "retrospective-cohort",
    "cohort study": "retrospective-cohort",
    "cohort_study": "retrospective-cohort",

    # ── case-control ──
    "case-control": "case-control",
    "case_control": "case-control",
    "case control": "case-control",
    "case-control study": "case-control",
    "case_control_study": "case-control",

    # ── case-series ──
    "case-series": "case-series",
    "case_series": "case-series",
    "case series": "case-series",

    # ── case-report ──
    "case-report": "case-report",
    "case_report": "case-report",
    "case report": "case-report",
    "single case": "case-report",
    "single_case": "case-report",

    # ── expert-opinion ──
    "expert-opinion": "expert-opinion",
    "expert_opinion": "expert-opinion",
    "expert opinion": "expert-opinion",
    "editorial": "expert-opinion",
    "commentary": "expert-opinion",
    "letter": "expert-opinion",
    "perspective": "expert-opinion",
    "viewpoint": "expert-opinion",
    "guideline": "expert-opinion",

    # ── cross-sectional ──
    "cross-sectional": "cross-sectional",
    "cross_sectional": "cross-sectional",
    "cross sectional": "cross-sectional",
    "survey": "cross-sectional",

    # ── non-randomized / observational (NOT RCT) ──
    "non-randomized": "other",
    "non_randomized": "other",
    "non randomized": "other",
    "non-randomised": "other",
    "non-randomized single-arm": "other",
    "non-randomized multi-arm": "other",
    "non-randomised single-arm": "other",
    "non-randomised multi-arm": "other",
    "single-arm": "other",
    "single_arm": "other",
    "multi-arm": "other",
    "multi_arm": "other",
    "observational": "other",

    # ── other ──
    "other": "other",
    "unknown": "other",
}


def normalize_study_design(raw: str) -> str:
    """Normalize a study_design string to a canonical StudyDesign value.

    Maps variant forms (underscore, hyphen, long-form, abbreviation) to
    the canonical enum values defined in StudyDesign.

    Args:
        raw: Raw study_design string from LLM output, PubMed, or user input.

    Returns:
        Canonical study_design string (one of StudyDesign enum values),
        or empty string if input is empty/None.
    """
    if not raw:
        return ""

    key = raw.strip().lower()
    if not key:
        return ""

    # Direct lookup
    canonical = _STUDY_DESIGN_ALIAS_MAP.get(key)
    if canonical:
        return canonical

    # Check if already a valid canonical value (case-insensitive for "RCT")
    canonical_values = {sd.value.lower(): sd.value for sd in StudyDesign}
    if key in canonical_values:
        return canonical_values[key]

    # Check for negation patterns FIRST — "non-randomized" is NOT RCT
    if re.search(r'\bnon[\-_\s]?randomi[sz]ed\b', key):
        return "other"

    # Substring fallback for compound descriptions like "multi-center randomized trial"
    # Priority order: meta-analysis > systematic-review > RCT > cohort > case-control > case-series > case-report > cross-sectional > expert-opinion
    _SUBSTRING_PRIORITY = [
        ("meta-analysis", "meta-analysis"),
        ("meta analysis", "meta-analysis"),
        ("metaanalysis", "meta-analysis"),
        ("systematic review", "systematic-review"),
        ("systematic_review", "systematic-review"),
        ("randomized", "RCT"),
        ("randomised", "RCT"),
        ("rct", "RCT"),
        ("prospective cohort", "prospective-cohort"),
        ("prospective_cohort", "prospective-cohort"),
        ("retrospective cohort", "retrospective-cohort"),
        ("retrospective_cohort", "retrospective-cohort"),
        ("case-control", "case-control"),
        ("case_control", "case-control"),
        ("case control", "case-control"),
        ("cross-sectional", "cross-sectional"),
        ("cross_sectional", "cross-sectional"),
        ("cross sectional", "cross-sectional"),
        ("case series", "case-series"),
        ("case_series", "case-series"),
        ("case report", "case-report"),
        ("case_report", "case-report"),
        ("retrospective", "retrospective-cohort"),
        ("prospective", "prospective-cohort"),
        ("cohort", "retrospective-cohort"),
        ("expert opinion", "expert-opinion"),
        ("editorial", "expert-opinion"),
    ]
    for substr, canonical_val in _SUBSTRING_PRIORITY:
        if substr in key:
            return canonical_val

    # Unrecognized — return "other"
    return "other"


class OutcomeType(Enum):
    """결과변수 유형."""
    CLINICAL = "clinical"        # VAS, ODI, JOA
    RADIOLOGICAL = "radiological"  # Fusion rate, Cobb angle
    FUNCTIONAL = "functional"    # Return to work, ADL
    COMPLICATION = "complication"  # Infection, revision


class InterventionCategory(Enum):
    """수술 분류."""
    FUSION = "fusion"
    DECOMPRESSION = "decompression"
    FIXATION = "fixation"
    OSTEOTOMY = "osteotomy"
    TUMOR_RESECTION = "tumor_resection"
    VERTEBROPLASTY = "vertebroplasty"
    MOTION_PRESERVATION = "motion_preservation"
    NAVIGATION = "navigation"
    OTHER = "other"


class PaperRelationType(Enum):
    """논문 간 관계 유형 (from SQLite paper_graph.py).

    논문 간 지적 관계를 표현하는 관계 타입.
    인용 분석, 연구 결과 비교, 주제 클러스터링에 사용.
    """
    SUPPORTS = "SUPPORTS"           # 지지하는 관계 (결과가 일치)
    CONTRADICTS = "CONTRADICTS"     # 상충하는 관계 (결과가 반대)
    SIMILAR_TOPIC = "SIMILAR_TOPIC" # 유사 주제 (임베딩 기반)
    EXTENDS = "EXTENDS"             # 확장 연구 (후속 연구)
    CITES = "CITES"                 # 인용 관계 (직접 인용)
    REPLICATES = "REPLICATES"       # 재현 연구 (같은 질문, 다른 데이터)


class DocumentType(Enum):
    """문서 유형 (Zotero item types 기반, v6.0).

    다양한 인용 가능 자료 유형을 지원합니다.
    각 유형별로 필수/선택 필드가 다릅니다.

    Reference: https://www.zotero.org/support/kb/item_types_and_fields
    """
    # === 학술 출판물 ===
    JOURNAL_ARTICLE = "journal-article"      # 학술 논문 (default)
    BOOK = "book"                            # 책
    BOOK_SECTION = "book-section"            # 책의 장/챕터
    CONFERENCE_PAPER = "conference-paper"    # 학회 논문
    THESIS = "thesis"                        # 학위 논문 (PhD, MSc, MD)
    REPORT = "report"                        # 보고서 (기술, 연구, 백서)
    PREPRINT = "preprint"                    # 프리프린트 (arXiv, medRxiv)

    # === 참고 자료 ===
    ENCYCLOPEDIA_ARTICLE = "encyclopedia-article"  # 백과사전 항목
    DICTIONARY_ENTRY = "dictionary-entry"          # 사전 항목

    # === 뉴스/미디어 ===
    NEWSPAPER_ARTICLE = "newspaper-article"  # 신문 기사
    MAGAZINE_ARTICLE = "magazine-article"    # 잡지 기사
    BLOG_POST = "blog-post"                  # 블로그 포스트
    WEBPAGE = "webpage"                      # 웹페이지

    # === 기술/데이터 ===
    DATASET = "dataset"                      # 데이터셋
    SOFTWARE = "software"                    # 소프트웨어
    PATENT = "patent"                        # 특허
    STANDARD = "standard"                    # 표준 문서 (ISO, KS)

    # === 기타 ===
    PRESENTATION = "presentation"            # 발표 자료
    VIDEO = "video"                          # 동영상 (YouTube, Vimeo)
    INTERVIEW = "interview"                  # 인터뷰
    LETTER = "letter"                        # 편지/서신
    MANUSCRIPT = "manuscript"                # 원고
    DOCUMENT = "document"                    # 일반 문서 (기타)


class EntityCategory(Enum):
    """확장 엔티티 카테고리 (v1.1).

    문서 유형에 따른 엔티티 분류.
    """
    # 기본 (모든 문서)
    INTERVENTION = "intervention"
    PATHOLOGY = "pathology"
    ANATOMY = "anatomy"
    OUTCOME = "outcome"

    # 교과서/교육용
    CONCEPT = "concept"
    DEFINITION = "definition"
    TECHNIQUE = "technique"

    # 가이드라인용
    RECOMMENDATION = "recommendation"
    INDICATION = "indication"
    CONTRAINDICATION = "contraindication"

    # 수술 기법 문서용
    INSTRUMENT = "instrument"
    IMPLANT = "implant"
    SURGICAL_STEP = "surgical_step"

    # 약물/합병증
    DRUG = "drug"
    COMPLICATION = "complication"

    # v1.1: 결과 측정치 및 예측 모델
    OUTCOME_MEASURE = "outcome_measure"
    RADIO_PARAMETER = "radiographic_parameter"
    PREDICTION_MODEL = "prediction_model"
    RISK_FACTOR = "risk_factor"


class CitationContext(Enum):
    """인용 컨텍스트 유형 (인용이 논문에서 어떤 역할을 하는지).

    중요한 인용만 추출하여 저장할 때 사용.
    - SUPPORTS_RESULT: 본 연구 결과를 지지하는 선행 연구
    - CONTRADICTS_RESULT: 본 연구 결과와 상반되는 선행 연구
    - METHODOLOGICAL: 방법론적 참고
    - BACKGROUND: 배경 지식 제공
    - COMPARISON: 직접 비교 대상
    """
    SUPPORTS_RESULT = "supports_result"  # 유사한 결과를 보고한 연구
    CONTRADICTS_RESULT = "contradicts_result"  # 반대 결과를 보고한 연구
    METHODOLOGICAL = "methodological"  # 방법론 참고
    BACKGROUND = "background"  # 배경 문헌
    COMPARISON = "comparison"  # 직접 비교 대상
