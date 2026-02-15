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

from enum import Enum


class SpineSubDomain(Enum):
    """척추 하위 도메인."""
    DEGENERATIVE = "Degenerative"
    DEFORMITY = "Deformity"
    TRAUMA = "Trauma"
    TUMOR = "Tumor"
    BASIC_SCIENCE = "Basic Science"


class EvidenceLevel(Enum):
    """근거 수준 (Oxford Centre for Evidence-Based Medicine)."""
    LEVEL_1A = "1a"  # Meta-analysis of RCTs
    LEVEL_1B = "1b"  # Individual RCT
    LEVEL_2A = "2a"  # Systematic review of cohort studies
    LEVEL_2B = "2b"  # Individual cohort study
    LEVEL_3 = "3"    # Case-control study
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
    OTHER = "other"


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
