"""Writing Guide Handler for Medical KAG Server.

This module provides comprehensive academic paper writing assistance:
- Section-specific writing guides (Introduction, Methods, Results, Discussion)
- Study type checklists (STROBE, CONSORT, PRISMA, CARE, etc.)
- Expert agent system for collaborative paper writing
- Revision and response letter support
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute

logger = logging.getLogger(__name__)


class StudyType(Enum):
    """Study types with corresponding checklists."""
    RCT = "rct"                      # CONSORT
    COHORT = "cohort"                # STROBE
    CASE_CONTROL = "case_control"    # STROBE
    CROSS_SECTIONAL = "cross_sectional"  # STROBE
    CASE_SERIES = "case_series"      # CARE
    CASE_REPORT = "case_report"      # CARE
    SYSTEMATIC_REVIEW = "systematic_review"  # PRISMA
    META_ANALYSIS = "meta_analysis"  # PRISMA
    DIAGNOSTIC = "diagnostic"        # STARD
    PROGNOSTIC = "prognostic"        # TRIPOD
    QUALITATIVE = "qualitative"      # COREQ
    ANIMAL = "animal"                # ARRIVE


class ExpertRole(Enum):
    """Expert roles in the writing team."""
    CLINICIAN = "clinician"          # Dr. Clinician - Clinical context
    METHODOLOGIST = "methodologist"  # Dr. Methodologist - Methods & Results
    STATISTICIAN = "statistician"    # Dr. Statistician - Statistical rigor
    EDITOR = "editor"                # Dr. Editor - Final polish


@dataclass
class SectionGuide:
    """Writing guide for a manuscript section."""
    section: str
    description: str
    structure: List[str]
    word_limit: Optional[int]
    tips: List[str]
    common_mistakes: List[str]
    example_phrases: Dict[str, List[str]]


@dataclass
class ChecklistItem:
    """Single checklist item."""
    number: str
    item: str
    description: str
    section: str  # Where to report (title, abstract, methods, etc.)


@dataclass
class Checklist:
    """Complete checklist for a study type."""
    name: str
    full_name: str
    study_type: str
    url: str
    items: List[ChecklistItem]


# ============================================================================
# SECTION WRITING GUIDES
# ============================================================================

SECTION_GUIDES: Dict[str, SectionGuide] = {
    "introduction": SectionGuide(
        section="Introduction",
        description="연구 배경, 문제 제기, 연구 목적을 간결하게 제시",
        structure=[
            "1단락: 연구 주제의 일반적 배경 (왜 중요한가?)",
            "2단락: 현재 알려진 사실과 지식의 격차 (무엇이 부족한가?)",
            "3단락: 이 연구의 필요성과 가설 (왜 이 연구가 필요한가?)",
            "4단락: 연구 목적 명시 (무엇을 밝히고자 하는가?)",
        ],
        word_limit=400,
        tips=[
            "3-4개 문단으로 구성 (400 단어 이내)",
            "일반적인 것에서 구체적인 것으로 진행 (funnel approach)",
            "각 문단의 첫 문장은 해당 문단의 주제를 명확히",
            "마지막 문단에 연구 목적/가설을 명확히 기술",
            "최신 문헌을 인용하여 배경 설명 (최근 5년 내)",
            "KAG DB에서 관련 근거 검색 후 없으면 PubMed 검색",
        ],
        common_mistakes=[
            "너무 긴 서론 (500단어 초과)",
            "연구 목적이 불명확",
            "문헌 인용 없이 주장만 나열",
            "연구 가설과 목적의 혼동",
            "일반적 배경이 너무 길고 구체적 격차가 부족",
        ],
        example_phrases={
            "background": [
                "Lumbar degenerative disease is one of the most common conditions...",
                "Over the past decade, minimally invasive techniques have gained popularity...",
                "The prevalence of ... has increased significantly...",
            ],
            "knowledge_gap": [
                "However, the comparative effectiveness of ... remains unclear.",
                "Despite numerous studies, there is no consensus on...",
                "Limited data exist regarding the long-term outcomes of...",
            ],
            "rationale": [
                "Therefore, a well-designed comparative study is needed to...",
                "To address this gap, we conducted...",
                "Given the conflicting evidence, we hypothesized that...",
            ],
            "objective": [
                "The aim of this study was to compare...",
                "We sought to determine whether...",
                "The purpose of this study was to evaluate...",
            ],
        },
    ),

    "methods": SectionGuide(
        section="Materials and Methods",
        description="연구 설계, 대상자, 중재, 결과변수, 통계분석 기술",
        structure=[
            "Study Design: 연구 유형 명시 (RCT, cohort, case-control 등)",
            "Participants: 대상자 선정/제외 기준, 모집 방법, 기간",
            "Intervention/Exposure: 중재 또는 노출 요인 상세 기술",
            "Outcomes: 일차/이차 결과변수 정의",
            "Variables: 공변량, 교란변수 정의",
            "Data Collection: 자료 수집 방법, 측정 도구",
            "Statistical Analysis: 통계 방법, 소프트웨어, 유의수준",
            "Ethical Considerations: IRB 승인, 동의서",
        ],
        word_limit=None,  # No strict limit, depends on complexity
        tips=[
            "체크리스트(STROBE/CONSORT 등)에 따라 누락 없이 기술",
            "재현 가능하도록 충분히 상세하게 작성",
            "통계 방법은 결과변수 유형에 맞게 선택",
            "일차 결과변수를 명확히 정의",
            "Sample size calculation 근거 제시 (RCT의 경우)",
            "Blinding, randomization 방법 명시 (해당시)",
        ],
        common_mistakes=[
            "통계 방법과 결과변수 불일치",
            "Sample size 근거 누락",
            "결과변수 정의 불명확",
            "선정/제외 기준 불완전",
            "공변량 보정 근거 부족",
            "IRB 승인 정보 누락",
        ],
        example_phrases={
            "study_design": [
                "This retrospective cohort study was conducted at...",
                "We performed a randomized controlled trial...",
                "This was a multicenter prospective study...",
            ],
            "participants": [
                "Patients were included if they met the following criteria:...",
                "Exclusion criteria were:...",
                "A total of N patients were enrolled between...",
            ],
            "statistics": [
                "Continuous variables were compared using...",
                "Categorical variables were analyzed with...",
                "A p-value < 0.05 was considered statistically significant.",
                "All analyses were performed using...",
            ],
        },
    ),

    "results": SectionGuide(
        section="Results",
        description="연구 결과를 객관적으로 제시 (해석 없이)",
        structure=[
            "Participant Flow: 대상자 수, 탈락자 수, 최종 분석 대상",
            "Baseline Characteristics: 기저 특성 (Table 1)",
            "Primary Outcome: 일차 결과변수 분석 결과",
            "Secondary Outcomes: 이차 결과변수 분석 결과",
            "Subgroup Analyses: 하위군 분석 (해당시)",
            "Adverse Events: 부작용, 합병증 (해당시)",
        ],
        word_limit=None,
        tips=[
            "Subtitle을 사용하여 결과를 구조화",
            "Table/Figure와 본문 내용이 과도하게 중복되지 않게",
            "단, Key finding은 본문에서도 강조 가능",
            "숫자 제시 시 정확한 통계치 포함 (95% CI, p-value)",
            "결과 해석은 Discussion에서 (Results는 객관적 기술만)",
            "CONSORT flow diagram 등 적절한 Figure 활용",
        ],
        common_mistakes=[
            "Table/Figure 내용을 그대로 반복",
            "통계적 유의성만 강조 (임상적 의미 무시)",
            "결과 해석을 Results에 포함",
            "p-value만 제시 (effect size, CI 누락)",
            "논리적 순서 없이 결과 나열",
        ],
        example_phrases={
            "participant_flow": [
                "Of the N patients screened, N met the inclusion criteria...",
                "After excluding N patients, N were included in the final analysis.",
            ],
            "baseline": [
                "Baseline characteristics were similar between groups (Table 1).",
                "The mean age was X ± Y years, and N (%)% were male.",
            ],
            "primary_outcome": [
                "The primary outcome of ... was significantly different between groups (X vs Y, p=0.001).",
                "Patients in the intervention group showed a mean improvement of...",
            ],
            "statistics": [
                "The difference was statistically significant (mean difference: X, 95% CI: Y-Z, p<0.001).",
                "After adjusting for confounders, the association remained significant (OR: X, 95% CI: Y-Z).",
            ],
        },
    ),

    "discussion": SectionGuide(
        section="Discussion",
        description="결과 해석, 선행연구 비교, 임상적 의의, 한계점",
        structure=[
            "1단락: 주요 발견 요약 (Main key points)",
            "2-4단락: 각 주요 결과의 해석 + 선행연구 비교",
            "5단락: 임상적/연구적 의의 (So what?)",
            "마지막 단락: 연구의 강점과 한계점 (Limitations)",
        ],
        word_limit=None,
        tips=[
            "첫 문단에서 주요 발견을 간결하게 요약",
            "각 결과를 선행연구와 비교하며 해석",
            "일치하는 연구와 상반되는 연구 모두 언급",
            "결과의 임상적 의미를 명확히",
            "한계점은 인정하되, 강점도 함께 언급",
            "과도한 추측이나 과장된 주장 피하기",
        ],
        common_mistakes=[
            "Results를 그대로 반복",
            "선행연구 비교 없이 해석만 나열",
            "한계점을 너무 길게 기술",
            "결과를 과대해석",
            "임상적 의의 누락",
        ],
        example_phrases={
            "summary": [
                "In this study, we found that...",
                "Our results demonstrate that...",
                "The key finding of this study was...",
            ],
            "comparison": [
                "Our findings are consistent with those of Smith et al., who reported...",
                "In contrast to previous studies, we observed...",
                "Similar results were reported by...",
            ],
            "interpretation": [
                "These results suggest that...",
                "One possible explanation for this finding is...",
                "The observed difference may be attributed to...",
            ],
            "limitations": [
                "This study has several limitations. First,...",
                "The retrospective nature of this study limits...",
                "Despite these limitations, our study has several strengths...",
            ],
        },
    ),

    "conclusion": SectionGuide(
        section="Conclusion",
        description="연구의 핵심 결론과 임상적 의의",
        structure=[
            "주요 발견 1-2문장으로 요약",
            "임상적/연구적 함의 제시",
            "향후 연구 방향 제안 (선택적)",
        ],
        word_limit=150,
        tips=[
            "간결하게 (150 단어 이내)",
            "새로운 정보 추가하지 않음",
            "과장된 표현 피하기",
            "연구 목적에 대한 답변 형태로 작성",
        ],
        common_mistakes=[
            "너무 길게 작성",
            "새로운 데이터나 분석 포함",
            "지나친 일반화",
            "결과를 초과하는 주장",
        ],
        example_phrases={
            "conclusion": [
                "In conclusion, our study demonstrates that...",
                "Based on these findings, we conclude that...",
                "These results suggest that ... may be a viable option for...",
            ],
            "implication": [
                "These findings have important implications for...",
                "Clinicians should consider... when treating...",
                "Further studies are needed to confirm...",
            ],
        },
    ),

    "figure_legend": SectionGuide(
        section="Figure Legends",
        description="그림에 대한 설명",
        structure=[
            "Figure 제목 (간결하게)",
            "그림 내용 설명",
            "약어 정의",
            "통계적 유의성 표기 설명 (* p<0.05 등)",
        ],
        word_limit=None,
        tips=[
            "Figure만 보고도 이해할 수 있도록",
            "모든 약어 정의 포함",
            "통계 표기법 설명",
            "Figure 번호 순서대로 정리",
        ],
        common_mistakes=[
            "약어 정의 누락",
            "너무 간략한 설명",
            "본문 없이는 이해 불가능한 설명",
        ],
        example_phrases={
            "legend": [
                "Figure 1. Flowchart of patient selection. A total of...",
                "Figure 2. Comparison of outcomes between groups. Data are presented as mean ± SD. *p<0.05.",
                "Abbreviations: VAS, visual analog scale; ODI, Oswestry Disability Index.",
            ],
        },
    ),
}


# ============================================================================
# STUDY TYPE CHECKLISTS
# ============================================================================

def get_strobe_checklist() -> Checklist:
    """STROBE checklist for observational studies."""
    return Checklist(
        name="STROBE",
        full_name="Strengthening the Reporting of Observational Studies in Epidemiology",
        study_type="Observational (Cohort, Case-control, Cross-sectional)",
        url="https://www.strobe-statement.org/",
        items=[
            ChecklistItem("1", "Title and abstract", "(a) study design, (b) informative abstract", "title/abstract"),
            ChecklistItem("2", "Background/rationale", "Scientific background and rationale", "introduction"),
            ChecklistItem("3", "Objectives", "State specific objectives, including hypotheses", "introduction"),
            ChecklistItem("4", "Study design", "Present key elements of study design", "methods"),
            ChecklistItem("5", "Setting", "Setting, locations, dates of recruitment/exposure/follow-up", "methods"),
            ChecklistItem("6", "Participants", "Eligibility criteria, sources, selection methods", "methods"),
            ChecklistItem("7", "Variables", "Clearly define outcomes, exposures, predictors, confounders", "methods"),
            ChecklistItem("8", "Data sources/measurement", "For each variable, describe sources and methods", "methods"),
            ChecklistItem("9", "Bias", "Describe any efforts to address potential sources of bias", "methods"),
            ChecklistItem("10", "Study size", "Explain how study size was arrived at", "methods"),
            ChecklistItem("11", "Quantitative variables", "Explain how quantitative variables were handled", "methods"),
            ChecklistItem("12", "Statistical methods", "Describe all statistical methods", "methods"),
            ChecklistItem("13", "Participants", "Report numbers at each stage of study", "results"),
            ChecklistItem("14", "Descriptive data", "Characteristics of participants, missing data", "results"),
            ChecklistItem("15", "Outcome data", "Report numbers of outcome events or summary measures", "results"),
            ChecklistItem("16", "Main results", "Unadjusted and adjusted estimates with precision", "results"),
            ChecklistItem("17", "Other analyses", "Report other analyses done (subgroup, sensitivity)", "results"),
            ChecklistItem("18", "Key results", "Summarize key results with reference to objectives", "discussion"),
            ChecklistItem("19", "Limitations", "Discuss limitations, sources of bias", "discussion"),
            ChecklistItem("20", "Interpretation", "Cautious overall interpretation of results", "discussion"),
            ChecklistItem("21", "Generalizability", "Discuss the generalizability of results", "discussion"),
            ChecklistItem("22", "Funding", "Give source of funding and role of funders", "other"),
        ],
    )


def get_consort_checklist() -> Checklist:
    """CONSORT checklist for RCTs."""
    return Checklist(
        name="CONSORT",
        full_name="Consolidated Standards of Reporting Trials",
        study_type="Randomized Controlled Trial",
        url="https://www.consort-statement.org/",
        items=[
            ChecklistItem("1a", "Title", "Identified as a randomised trial in the title", "title"),
            ChecklistItem("1b", "Abstract", "Structured summary of trial design, methods, results, conclusions", "abstract"),
            ChecklistItem("2a", "Background", "Scientific background and explanation of rationale", "introduction"),
            ChecklistItem("2b", "Objectives", "Specific objectives or hypotheses", "introduction"),
            ChecklistItem("3a", "Trial design", "Description of trial design", "methods"),
            ChecklistItem("3b", "Changes to methods", "Important changes to methods after trial commencement", "methods"),
            ChecklistItem("4a", "Participants", "Eligibility criteria for participants", "methods"),
            ChecklistItem("4b", "Settings", "Settings and locations where data were collected", "methods"),
            ChecklistItem("5", "Interventions", "The interventions for each group with sufficient details", "methods"),
            ChecklistItem("6a", "Outcomes", "Completely defined pre-specified primary and secondary outcomes", "methods"),
            ChecklistItem("6b", "Changes to outcomes", "Any changes to trial outcomes after the trial commenced", "methods"),
            ChecklistItem("7a", "Sample size", "How sample size was determined", "methods"),
            ChecklistItem("7b", "Interim analyses", "When applicable, explanation of any interim analyses", "methods"),
            ChecklistItem("8a", "Randomisation sequence", "Method used to generate the random allocation sequence", "methods"),
            ChecklistItem("8b", "Randomisation type", "Type of randomisation; details of any restriction", "methods"),
            ChecklistItem("9", "Allocation concealment", "Mechanism used to implement the allocation sequence", "methods"),
            ChecklistItem("10", "Implementation", "Who generated sequence, enrolled participants, assigned participants", "methods"),
            ChecklistItem("11a", "Blinding", "If done, who was blinded after assignment to interventions", "methods"),
            ChecklistItem("11b", "Similarity of interventions", "If relevant, description of the similarity of interventions", "methods"),
            ChecklistItem("12a", "Statistical methods", "Statistical methods used to compare groups for primary and secondary outcomes", "methods"),
            ChecklistItem("12b", "Additional analyses", "Methods for additional analyses (subgroup, adjusted)", "methods"),
            ChecklistItem("13a", "Participant flow", "For each group, numbers randomly assigned, received treatment, analysed", "results"),
            ChecklistItem("13b", "Losses and exclusions", "For each group, losses and exclusions after randomisation, with reasons", "results"),
            ChecklistItem("14a", "Recruitment", "Dates defining periods of recruitment and follow-up", "results"),
            ChecklistItem("14b", "Stopped early", "Why the trial ended or was stopped", "results"),
            ChecklistItem("15", "Baseline data", "A table showing baseline demographic and clinical characteristics", "results"),
            ChecklistItem("16", "Numbers analysed", "For each group, number of participants included in each analysis", "results"),
            ChecklistItem("17a", "Outcomes and estimation", "For each primary and secondary outcome, results for each group", "results"),
            ChecklistItem("17b", "Binary outcomes", "For binary outcomes, presentation of both absolute and relative effect sizes", "results"),
            ChecklistItem("18", "Ancillary analyses", "Results of any other analyses performed", "results"),
            ChecklistItem("19", "Harms", "All important harms or unintended effects in each group", "results"),
            ChecklistItem("20", "Limitations", "Trial limitations, addressing sources of potential bias", "discussion"),
            ChecklistItem("21", "Generalisability", "Generalisability of the trial findings", "discussion"),
            ChecklistItem("22", "Interpretation", "Interpretation consistent with results, balancing benefits and harms", "discussion"),
            ChecklistItem("23", "Registration", "Registration number and name of trial registry", "other"),
            ChecklistItem("24", "Protocol", "Where the full trial protocol can be accessed", "other"),
            ChecklistItem("25", "Funding", "Sources of funding and other support", "other"),
        ],
    )


def get_prisma_checklist() -> Checklist:
    """PRISMA checklist for systematic reviews."""
    return Checklist(
        name="PRISMA",
        full_name="Preferred Reporting Items for Systematic Reviews and Meta-Analyses",
        study_type="Systematic Review / Meta-Analysis",
        url="https://www.prisma-statement.org/",
        items=[
            ChecklistItem("1", "Title", "Identify the report as a systematic review, meta-analysis, or both", "title"),
            ChecklistItem("2", "Abstract", "Structured summary", "abstract"),
            ChecklistItem("3", "Rationale", "Describe rationale in context of what is known", "introduction"),
            ChecklistItem("4", "Objectives", "Provide explicit statement of questions being addressed (PICOS)", "introduction"),
            ChecklistItem("5", "Protocol", "Indicate if a review protocol exists", "methods"),
            ChecklistItem("6", "Eligibility criteria", "Specify study characteristics (PICOS) and report characteristics", "methods"),
            ChecklistItem("7", "Information sources", "Describe all information sources searched with dates", "methods"),
            ChecklistItem("8", "Search", "Present full electronic search strategy for at least one database", "methods"),
            ChecklistItem("9", "Study selection", "State the process for selecting studies", "methods"),
            ChecklistItem("10", "Data collection", "Describe method of data extraction and any confirmation", "methods"),
            ChecklistItem("11", "Data items", "List and define all variables for which data were sought", "methods"),
            ChecklistItem("12", "Risk of bias", "Describe methods used for assessing risk of bias", "methods"),
            ChecklistItem("13", "Summary measures", "State the principal summary measures (risk ratio, difference)", "methods"),
            ChecklistItem("14", "Synthesis of results", "Describe the methods of handling data and combining results", "methods"),
            ChecklistItem("15", "Risk of bias across studies", "Specify any assessment of risk of bias across studies", "methods"),
            ChecklistItem("16", "Additional analyses", "Describe methods of additional analyses (sensitivity, meta-regression)", "methods"),
            ChecklistItem("17", "Study selection", "Give numbers of studies screened, assessed, included with reasons for exclusions", "results"),
            ChecklistItem("18", "Study characteristics", "Present characteristics of each study with citations", "results"),
            ChecklistItem("19", "Risk of bias within studies", "Present data on risk of bias of each study", "results"),
            ChecklistItem("20", "Results of individual studies", "For all outcomes, present simple summary data and effect estimates with CIs", "results"),
            ChecklistItem("21", "Synthesis of results", "Present results of each meta-analysis done, including CIs", "results"),
            ChecklistItem("22", "Risk of bias across studies", "Present results of any assessment of risk of bias across studies", "results"),
            ChecklistItem("23", "Additional analysis", "Give results of additional analyses (sensitivity, meta-regression)", "results"),
            ChecklistItem("24", "Summary of evidence", "Summarize the main findings including strength of evidence", "discussion"),
            ChecklistItem("25", "Limitations", "Discuss limitations at study and outcome level", "discussion"),
            ChecklistItem("26", "Conclusions", "Provide a general interpretation of results and implications", "discussion"),
            ChecklistItem("27", "Funding", "Describe sources of funding", "funding"),
        ],
    )


def get_care_checklist() -> Checklist:
    """CARE checklist for case reports."""
    return Checklist(
        name="CARE",
        full_name="CAse REport Guidelines",
        study_type="Case Report / Case Series",
        url="https://www.care-statement.org/",
        items=[
            ChecklistItem("1", "Title", "The words 'case report' should appear in the title", "title"),
            ChecklistItem("2", "Keywords", "2 to 5 keywords that identify diagnoses or interventions", "abstract"),
            ChecklistItem("3a", "Abstract - Background", "What is unique about this case?", "abstract"),
            ChecklistItem("3b", "Abstract - Case presentation", "Main symptoms, findings, diagnoses, interventions, outcomes", "abstract"),
            ChecklistItem("3c", "Abstract - Conclusions", "Main take-away lessons from this case", "abstract"),
            ChecklistItem("4", "Introduction", "Briefly summarize the background, including references to similar cases", "introduction"),
            ChecklistItem("5a", "Patient information", "De-identified patient information", "case_presentation"),
            ChecklistItem("5b", "Primary concerns", "Chief complaints of the patient", "case_presentation"),
            ChecklistItem("5c", "Medical history", "Past medical, surgical, family, social history", "case_presentation"),
            ChecklistItem("5d", "Physical examination", "Key findings from the physical examination", "case_presentation"),
            ChecklistItem("6", "Clinical findings", "Describe the relevant clinical findings", "case_presentation"),
            ChecklistItem("7", "Timeline", "A timeline of important events", "case_presentation"),
            ChecklistItem("8", "Diagnostic assessment", "Methods and findings for diagnostic workup", "case_presentation"),
            ChecklistItem("9", "Therapeutic intervention", "Types of intervention and how administered", "case_presentation"),
            ChecklistItem("10", "Follow-up and outcomes", "Summary of clinical course and any adverse events", "case_presentation"),
            ChecklistItem("11a", "Discussion - Strengths and limitations", "Discuss strengths and limitations of managing this case", "discussion"),
            ChecklistItem("11b", "Discussion - Literature", "Reference relevant medical literature", "discussion"),
            ChecklistItem("11c", "Discussion - Rationale", "Explain the rationale for conclusions drawn", "discussion"),
            ChecklistItem("11d", "Discussion - Lessons", "What are the main take-away messages from this case?", "discussion"),
            ChecklistItem("12", "Patient perspective", "When appropriate, share the patient's perspective on their care", "other"),
            ChecklistItem("13", "Informed consent", "Did the patient provide informed consent?", "other"),
        ],
    )


def get_stard_checklist() -> Checklist:
    """STARD checklist for diagnostic accuracy studies."""
    return Checklist(
        name="STARD",
        full_name="Standards for Reporting of Diagnostic Accuracy Studies",
        study_type="Diagnostic Accuracy Study",
        url="https://www.equator-network.org/reporting-guidelines/stard/",
        items=[
            ChecklistItem("1", "Title", "Identification as a study of diagnostic accuracy (recommend MeSH 'sensitivity and specificity')", "title"),
            ChecklistItem("2", "Abstract", "Structured abstract with study design, methods, results, conclusions", "abstract"),
            ChecklistItem("3", "Scientific background", "Scientific and clinical background, including intended use and clinical role of index test", "introduction"),
            ChecklistItem("4", "Objectives", "Study objectives and hypotheses", "introduction"),
            ChecklistItem("5", "Study design", "Whether data collection was planned before index test and reference standard (prospective vs retrospective)", "methods"),
            ChecklistItem("6", "Participants", "Eligibility criteria (inclusion/exclusion)", "methods"),
            ChecklistItem("7", "Sampling", "On what basis potentially eligible participants were identified", "methods"),
            ChecklistItem("8", "Participant recruitment", "Where and when potentially eligible participants were identified", "methods"),
            ChecklistItem("9", "Sample size", "Whether participants formed a consecutive, random, or convenience series", "methods"),
            ChecklistItem("10a", "Index test", "Index test, in sufficient detail to allow replication", "methods"),
            ChecklistItem("10b", "Reference standard", "Reference standard, in sufficient detail to allow replication", "methods"),
            ChecklistItem("11", "Test execution", "Rationale for choosing the reference standard (if alternatives exist)", "methods"),
            ChecklistItem("12a", "Blinding", "Whether clinical information was available to performers of index test", "methods"),
            ChecklistItem("12b", "Blinding reference", "Whether clinical information was available to assessors of reference standard", "methods"),
            ChecklistItem("13a", "Analysis", "Methods for estimating or comparing measures of diagnostic accuracy", "methods"),
            ChecklistItem("13b", "Handling indeterminate", "How indeterminate index test or reference standard results were handled", "methods"),
            ChecklistItem("13c", "Missing data", "How missing data on the index test and reference standard were handled", "methods"),
            ChecklistItem("14", "Flow diagram", "Flow diagram of participants (screened, eligible, included, excluded)", "results"),
            ChecklistItem("15", "Baseline characteristics", "Baseline demographic and clinical characteristics of participants", "results"),
            ChecklistItem("16", "Distribution of disease", "Distribution of severity of disease in those with the target condition", "results"),
            ChecklistItem("17", "Time interval", "Time interval between index test and reference standard", "results"),
            ChecklistItem("18", "Cross tabulation", "Cross tabulation of results from index test and reference standard", "results"),
            ChecklistItem("19", "Estimates of accuracy", "Estimates of diagnostic accuracy with confidence intervals", "results"),
            ChecklistItem("20", "Adverse events", "Any adverse events from performing the index test or reference standard", "results"),
            ChecklistItem("21", "Limitations", "Study limitations including sources of potential bias, statistical uncertainty", "discussion"),
            ChecklistItem("22", "Implications", "Implications for practice, including intended use and clinical role", "discussion"),
            ChecklistItem("23", "Registration", "Registration number and name of registry", "other"),
            ChecklistItem("24", "Protocol", "Where the full study protocol can be accessed", "other"),
            ChecklistItem("25", "Funding", "Sources of funding and other support", "other"),
        ],
    )


def get_spirit_checklist() -> Checklist:
    """SPIRIT checklist for clinical trial protocols."""
    return Checklist(
        name="SPIRIT",
        full_name="Standard Protocol Items: Recommendations for Interventional Trials",
        study_type="Clinical Trial Protocol",
        url="https://www.spirit-statement.org/",
        items=[
            ChecklistItem("1", "Title", "Descriptive title identifying study design, population, interventions, acronym", "title"),
            ChecklistItem("2a", "Trial registration", "Trial identifier and registry name", "admin"),
            ChecklistItem("2b", "Protocol version", "Date and version identifier", "admin"),
            ChecklistItem("3", "Funding", "Sources and types of financial, material, and other support", "admin"),
            ChecklistItem("4", "Roles and responsibilities", "Names, affiliations, roles of protocol contributors", "admin"),
            ChecklistItem("5a", "Sponsor contact", "Name and contact information for the trial sponsor", "admin"),
            ChecklistItem("5b", "Sponsor role", "Role of study sponsor and funders in study design, analysis, publication", "admin"),
            ChecklistItem("5c", "Investigator access", "Composition of coordinating centre and trial steering committee", "admin"),
            ChecklistItem("5d", "Data access", "Composition of data monitoring committee, interim analyses, stopping rules", "admin"),
            ChecklistItem("6a", "Background", "Description of research question and justification", "introduction"),
            ChecklistItem("6b", "Choice of comparators", "Explanation for choice of comparators", "introduction"),
            ChecklistItem("7", "Objectives", "Specific objectives or hypotheses", "introduction"),
            ChecklistItem("8", "Trial design", "Description of trial design including type and allocation ratio", "methods"),
            ChecklistItem("9", "Participants", "Eligibility criteria (inclusion and exclusion)", "methods"),
            ChecklistItem("10", "Interventions", "Interventions for each group with sufficient detail to allow replication", "methods"),
            ChecklistItem("11a", "Primary outcome", "Primary outcome completely defined (domain, measurement, analysis metric)", "methods"),
            ChecklistItem("11b", "Secondary outcomes", "Secondary outcomes completely defined", "methods"),
            ChecklistItem("12", "Participant timeline", "Time schedule of enrolment, interventions, and assessments", "methods"),
            ChecklistItem("13", "Sample size", "Estimated number of participants needed with explanation of assumptions", "methods"),
            ChecklistItem("14", "Recruitment", "Strategies for achieving adequate participant enrolment", "methods"),
            ChecklistItem("15", "Assignment of interventions", "Who will generate the allocation sequence, enrol, assign participants", "methods"),
            ChecklistItem("16a", "Blinding", "Who will be blinded after assignment to interventions, how", "methods"),
            ChecklistItem("16b", "Emergency unblinding", "Procedure for revealing participant's allocated intervention", "methods"),
            ChecklistItem("17a", "Data collection methods", "Plans for assessment and collection of outcome, baseline, other data", "methods"),
            ChecklistItem("17b", "Participant retention", "Plans to promote participant retention and complete follow-up", "methods"),
            ChecklistItem("18a", "Data management", "Plans for data entry, coding, security, and storage", "methods"),
            ChecklistItem("18b", "Data sharing", "Processes to promote data quality", "methods"),
            ChecklistItem("19", "Statistical methods", "Statistical methods for analysing primary and secondary outcomes", "methods"),
            ChecklistItem("20a", "Data monitoring", "Composition of data monitoring committee and its role", "methods"),
            ChecklistItem("20b", "Interim analysis", "Description of any interim analyses and stopping guidelines", "methods"),
            ChecklistItem("20c", "Harms", "Plans for collecting, assessing, reporting, and managing adverse events", "methods"),
            ChecklistItem("21a", "Auditing", "Frequency and procedures for auditing trial conduct", "methods"),
            ChecklistItem("22", "Research ethics approval", "Plans for seeking ethics approval", "ethics"),
            ChecklistItem("23", "Protocol amendments", "Plans for communicating important protocol modifications", "ethics"),
            ChecklistItem("24", "Consent", "Who will obtain informed consent and how", "ethics"),
            ChecklistItem("25", "Confidentiality", "How personal information will be collected, shared, maintained", "ethics"),
            ChecklistItem("26a", "Ancillary studies", "Plans for ancillary studies using collected data", "ethics"),
            ChecklistItem("31", "Dissemination policy", "Plans for investigators and sponsors to communicate trial results", "dissemination"),
            ChecklistItem("32", "Appendices", "Informed consent materials and other related documents", "appendices"),
        ],
    )


def get_moose_checklist() -> Checklist:
    """MOOSE checklist for meta-analyses of observational studies."""
    return Checklist(
        name="MOOSE",
        full_name="Meta-analysis Of Observational Studies in Epidemiology",
        study_type="Meta-Analysis of Observational Studies",
        url="https://www.equator-network.org/reporting-guidelines/meta-analysis-of-observational-studies-in-epidemiology-a-proposal-for-reporting-moose-group/",
        items=[
            ChecklistItem("1", "Background", "Problem definition", "reporting_background"),
            ChecklistItem("2", "Hypothesis", "Hypothesis statement", "reporting_background"),
            ChecklistItem("3", "Study outcome", "Description of study outcome(s)", "reporting_background"),
            ChecklistItem("4", "Type of exposure", "Type of exposure or intervention used", "reporting_background"),
            ChecklistItem("5", "Study designs", "Type of study designs used", "reporting_background"),
            ChecklistItem("6", "Study population", "Study population", "reporting_background"),
            ChecklistItem("7", "Qualifications", "Qualifications of searchers", "reporting_search"),
            ChecklistItem("8", "Search strategy", "Search strategy including time period, key words", "reporting_search"),
            ChecklistItem("9", "Databases", "Databases and registries searched", "reporting_search"),
            ChecklistItem("10", "Software", "Search software used", "reporting_search"),
            ChecklistItem("11", "Hand searching", "Use of hand searching (journals, conference abstracts)", "reporting_search"),
            ChecklistItem("12", "Bibliography searching", "List of citations located and those excluded with reasons", "reporting_search"),
            ChecklistItem("13", "Contact authors", "Method of addressing articles published in multiple languages", "reporting_search"),
            ChecklistItem("14", "Unpublished data", "Method of handling abstracts and unpublished studies", "reporting_search"),
            ChecklistItem("15", "Description of relevance", "Description of relevance or appropriateness of studies", "reporting_methods"),
            ChecklistItem("16", "Quantitative synthesis", "Rationale for selection and coding of data", "reporting_methods"),
            ChecklistItem("17", "Quality assessment", "Documentation of how data were classified and coded", "reporting_methods"),
            ChecklistItem("18", "Comparability assessment", "Assessment of confounding, study quality, heterogeneity", "reporting_methods"),
            ChecklistItem("19", "Statistical methods", "Assessment of heterogeneity using statistical tests", "reporting_methods"),
            ChecklistItem("20", "Sensitivity analyses", "Description of statistical methods", "reporting_methods"),
            ChecklistItem("21", "Subgroup analyses", "Provision of appropriate tables and graphics", "reporting_methods"),
            ChecklistItem("22", "Graphic representation", "Graphic summarizing individual study estimates and overall", "reporting_results"),
            ChecklistItem("23", "Table of studies", "Table giving descriptive information for each study", "reporting_results"),
            ChecklistItem("24", "Reporting bias", "Results of sensitivity testing (e.g., subgroup analysis)", "reporting_results"),
            ChecklistItem("25", "Heterogeneity results", "Indication of statistical uncertainty of findings", "reporting_results"),
            ChecklistItem("26", "Quantitative results", "Quantitative assessment of bias (e.g., publication bias)", "reporting_discussion"),
            ChecklistItem("27", "Justification", "Justification for exclusion (e.g., language, quality threshold)", "reporting_discussion"),
            ChecklistItem("28", "Sources of support", "Assessment of quality of included studies", "reporting_discussion"),
            ChecklistItem("29", "Alternative explanations", "Consideration of alternative explanations for observed results", "reporting_discussion"),
            ChecklistItem("30", "Generalization", "Generalization of conclusions", "reporting_discussion"),
            ChecklistItem("31", "Future research", "Guidelines for future research", "reporting_discussion"),
            ChecklistItem("32", "Limitations", "Disclosure of funding source", "reporting_discussion"),
        ],
    )


def get_tripod_checklist() -> Checklist:
    """TRIPOD checklist for prediction model studies."""
    return Checklist(
        name="TRIPOD",
        full_name="Transparent Reporting of a multivariable prediction model for Individual Prognosis Or Diagnosis",
        study_type="Prediction Model Development/Validation",
        url="https://www.tripod-statement.org/",
        items=[
            ChecklistItem("1", "Title", "Identify the study as developing/validating a prediction model, target population, outcome", "title"),
            ChecklistItem("2", "Abstract", "Provide a summary of objectives, study design, setting, participants, sample size, predictors, outcome, statistical analysis, results, conclusions", "abstract"),
            ChecklistItem("3a", "Background", "Explain the medical context and rationale for developing/validating the prediction model", "introduction"),
            ChecklistItem("3b", "Objectives", "Specify the objectives, including whether the study describes development or validation, or both", "introduction"),
            ChecklistItem("4a", "Source of data", "Describe the study design or source of data (cohort, RCT, registry)", "methods"),
            ChecklistItem("4b", "Dates", "Specify the key study dates, including start and end of accrual", "methods"),
            ChecklistItem("5a", "Participants", "Specify key elements of the study setting", "methods"),
            ChecklistItem("5b", "Eligibility criteria", "Describe eligibility criteria for participants", "methods"),
            ChecklistItem("5c", "Treatment", "Give details of treatments received, if relevant", "methods"),
            ChecklistItem("6a", "Outcome", "Clearly define the outcome that is predicted, including how and when assessed", "methods"),
            ChecklistItem("6b", "Actions triggered", "Report any actions to blind assessment of the outcome to be predicted", "methods"),
            ChecklistItem("7a", "Predictors", "Clearly define all predictors, including how and when measured", "methods"),
            ChecklistItem("7b", "Predictor assessment", "Report any actions to blind assessment of predictors for the outcome", "methods"),
            ChecklistItem("8", "Sample size", "Explain how the study size was arrived at", "methods"),
            ChecklistItem("9", "Missing data", "Describe how missing data were handled with details of imputation method", "methods"),
            ChecklistItem("10a", "Statistical methods - development", "Describe how predictors were handled in the analyses", "methods"),
            ChecklistItem("10b", "Statistical methods - modeling", "Specify type of model, all model-building procedures, and method for internal validation", "methods"),
            ChecklistItem("10c", "Model performance", "For validation, describe how the predictions were calculated", "methods"),
            ChecklistItem("10d", "Model performance measures", "Specify all measures used to assess model performance and how calculated", "methods"),
            ChecklistItem("10e", "Model updating", "Describe any model updating (recalibration) arising from validation", "methods"),
            ChecklistItem("11", "Risk groups", "Provide details on how risk groups were created, if done", "methods"),
            ChecklistItem("12", "Development vs validation", "For validation, identify differences from development data in setting, eligibility, outcome, predictors", "methods"),
            ChecklistItem("13a", "Participants", "Describe flow of participants including number with missing data", "results"),
            ChecklistItem("13b", "Participant characteristics", "Describe characteristics of participants including number of outcomes", "results"),
            ChecklistItem("14a", "Model development", "Specify number of participants and outcomes in each analysis", "results"),
            ChecklistItem("14b", "Model specification", "If done, report unadjusted associations between predictors and outcome", "results"),
            ChecklistItem("15a", "Full model", "Present the full prediction model to allow predictions for individuals", "results"),
            ChecklistItem("15b", "Model coefficients", "Explain how to use the prediction model", "results"),
            ChecklistItem("16", "Model performance", "Report performance measures with confidence intervals", "results"),
            ChecklistItem("17", "Model updating", "If done, report the results from any model updating", "results"),
            ChecklistItem("18", "Limitations", "Discuss any limitations of the study", "discussion"),
            ChecklistItem("19a", "Interpretation", "For validation, give an overall interpretation of the results", "discussion"),
            ChecklistItem("19b", "Implications", "Discuss the potential clinical use of the model and implications for future research", "discussion"),
            ChecklistItem("20", "Supplementary information", "Provide information about the availability of supplementary resources", "other"),
            ChecklistItem("21", "Funding", "Give the source of funding and role of funders", "other"),
        ],
    )


def get_cheers_checklist() -> Checklist:
    """CHEERS checklist for health economic evaluations."""
    return Checklist(
        name="CHEERS",
        full_name="Consolidated Health Economic Evaluation Reporting Standards",
        study_type="Health Economic Evaluation",
        url="https://www.equator-network.org/reporting-guidelines/cheers/",
        items=[
            ChecklistItem("1", "Title", "Identify the study as an economic evaluation and specify the interventions compared", "title"),
            ChecklistItem("2", "Abstract", "Provide a structured summary including objectives, perspective, setting, methods, results, conclusions", "abstract"),
            ChecklistItem("3", "Background and objectives", "Give context for the study and state the study question and its relevance to health policy or practice", "introduction"),
            ChecklistItem("4", "Health economic analysis plan", "Indicate whether a health economic analysis plan was developed", "methods"),
            ChecklistItem("5", "Study population", "Describe characteristics of the study population, including reasons for inclusion/exclusion", "methods"),
            ChecklistItem("6", "Setting and location", "Provide relevant aspects of the system in which the decision needs to be made", "methods"),
            ChecklistItem("7", "Comparators", "Describe the interventions or strategies being compared and why they were chosen", "methods"),
            ChecklistItem("8", "Perspective", "State the perspective(s) of the analysis and why chosen", "methods"),
            ChecklistItem("9", "Time horizon", "State the time horizon(s) used for costs and outcomes and why appropriate", "methods"),
            ChecklistItem("10", "Discount rate", "Report the discount rate(s) used for costs and outcomes and why chosen", "methods"),
            ChecklistItem("11", "Selection of outcomes", "Describe what outcomes were used as the measure(s) of benefit", "methods"),
            ChecklistItem("12", "Measurement of outcomes", "Describe how outcomes used to capture benefit were measured", "methods"),
            ChecklistItem("13", "Valuation of outcomes", "Describe the population and methods used to measure and value outcomes", "methods"),
            ChecklistItem("14", "Measurement and valuation of resources and costs", "Describe how costs were valued", "methods"),
            ChecklistItem("15", "Currency, price date, and conversion", "Report the dates of estimated resource quantities and unit costs", "methods"),
            ChecklistItem("16", "Rationale and description of model", "If a model was used, describe and give reasons for the specific type", "methods"),
            ChecklistItem("17", "Analytics and assumptions", "Describe any methods for analysing or statistically transforming data", "methods"),
            ChecklistItem("18", "Characterizing heterogeneity", "Describe any methods used to characterize heterogeneity", "methods"),
            ChecklistItem("19", "Characterizing distributional effects", "Describe approaches used to characterize distributional effects", "methods"),
            ChecklistItem("20", "Characterizing uncertainty", "Describe the methods used to characterize uncertainty", "methods"),
            ChecklistItem("21", "Approach to engagement with patients and others", "Describe any engagement with patients and others affected", "methods"),
            ChecklistItem("22", "Study parameters", "Report all analytic inputs: values, ranges, references, probability distributions", "results"),
            ChecklistItem("23", "Summary of main results", "Report mean values for the main categories of costs and outcomes", "results"),
            ChecklistItem("24", "Effect of uncertainty", "Describe effects of uncertainty on findings, varying parameters", "results"),
            ChecklistItem("25", "Effect of engagement with patients and others", "Report how engagement affected the study", "results"),
            ChecklistItem("26", "Study findings, limitations, generalizability, and current knowledge", "Report key findings, limitations, ethical/equity considerations, generalizability", "discussion"),
            ChecklistItem("27", "Source of funding", "Describe how the study was funded and the role of the funder", "other"),
            ChecklistItem("28", "Conflicts of interest", "Report authors' conflicts of interest according to journal policy", "other"),
        ],
    )


CHECKLISTS: Dict[str, Checklist] = {
    "strobe": get_strobe_checklist(),
    "consort": get_consort_checklist(),
    "prisma": get_prisma_checklist(),
    "care": get_care_checklist(),
    "stard": get_stard_checklist(),
    "spirit": get_spirit_checklist(),
    "moose": get_moose_checklist(),
    "tripod": get_tripod_checklist(),
    "cheers": get_cheers_checklist(),
}

STUDY_TYPE_TO_CHECKLIST: Dict[str, str] = {
    # CONSORT
    "rct": "consort",
    "randomized_controlled_trial": "consort",
    # STROBE
    "cohort": "strobe",
    "case_control": "strobe",
    "cross_sectional": "strobe",
    "observational": "strobe",
    # CARE
    "case_series": "care",
    "case_report": "care",
    # PRISMA (RCT 메타분석)
    "systematic_review": "prisma",
    "meta_analysis": "prisma",
    # STARD
    "diagnostic": "stard",
    "diagnostic_accuracy": "stard",
    # SPIRIT
    "protocol": "spirit",
    "clinical_trial_protocol": "spirit",
    # MOOSE (관찰 연구 메타분석)
    "observational_meta_analysis": "moose",
    "meta_analysis_observational": "moose",
    # TRIPOD
    "prediction": "tripod",
    "prognostic": "tripod",
    "prediction_model": "tripod",
    # CHEERS
    "economic": "cheers",
    "cost_effectiveness": "cheers",
    "health_economic": "cheers",
}


# ============================================================================
# EXPERT AGENT DEFINITIONS
# ============================================================================

EXPERT_AGENTS: Dict[str, Dict[str, Any]] = {
    "clinician": {
        "name": "Dr. Clinician",
        "title": "Senior Clinical Expert (20+ years)",
        "role": "Clinical Content & Interpretation",
        "responsibilities": [
            "Provides clinical rationale and context",
            "Drafts Introduction section",
            "Develops Discussion section with clinical implications",
            "Identifies knowledge gaps",
            "Ensures clinical relevance",
        ],
        "sections": ["introduction", "discussion"],
        "focus": "Clinical experience, patient outcomes, practical implications",
    },
    "methodologist": {
        "name": "Dr. Methodologist",
        "title": "Research Design Expert (20+ years)",
        "role": "Study Design & Data Organization",
        "responsibilities": [
            "Designs and writes Materials and Methods section",
            "Structures patient selection criteria",
            "Organizes intervention description",
            "Develops Results section from data",
            "Ensures reproducibility",
        ],
        "sections": ["methods", "results"],
        "focus": "Research methodology, study design, outcome measures",
    },
    "statistician": {
        "name": "Dr. Statistician",
        "title": "Biostatistician (10+ years)",
        "role": "Statistical Rigor & Validation",
        "responsibilities": [
            "Selects appropriate statistical tests",
            "Validates Results section accuracy",
            "Reviews effect sizes, CIs, p-values",
            "Addresses biases and limitations",
            "Performs additional analyses as needed",
        ],
        "sections": ["methods", "results"],
        "focus": "Statistical accuracy, power analysis, methodological validity",
    },
    "editor": {
        "name": "Dr. Editor",
        "title": "Senior Expert & Editor-in-Chief (30+ years)",
        "role": "Manuscript Refinement & Quality Assurance",
        "responsibilities": [
            "Refines and polishes entire manuscript",
            "Ensures logical flow between sections",
            "Strengthens Conclusion",
            "Drafts response letter to reviewers",
            "Final quality check",
        ],
        "sections": ["all"],
        "focus": "Academic writing, manuscript coherence, publication standards",
    },
}


# ============================================================================
# REVISION RESPONSE TEMPLATES
# ============================================================================

RESPONSE_TEMPLATES: Dict[str, str] = {
    "agree": """We thank the reviewer for this insightful comment. We have revised the manuscript accordingly. {changes}""",

    "partially_agree": """We appreciate this valuable suggestion. While we agree that {agreement}, we believe {disagreement} because {reason}. However, we have added {addition} to address this concern. [Page X, Lines Y-Z]""",

    "respectfully_disagree": """We thank the reviewer for raising this important point. After careful consideration, we respectfully maintain our original interpretation because {justification}. However, we have added a statement acknowledging this in the Discussion section. [Page X, Lines Y-Z]""",

    "cannot_perform": """We appreciate this suggestion for additional analysis. Unfortunately, {reason}. We have acknowledged this as a limitation in our revised Discussion. We believe this limitation does not fundamentally alter our conclusions because {justification}.""",

    "clarification": """We thank the reviewer for this comment. We apologize for the confusion. We have clarified this point in the revised manuscript. {clarification} [Page X, Lines Y-Z]""",
}


class WritingGuideHandler(BaseHandler):
    """Handles academic paper writing guidance and assistance."""

    def __init__(self, server: "MedicalKAGServer"):
        """Initialize Writing Guide handler.

        Args:
            server: Parent MedicalKAGServer instance for accessing clients
        """
        super().__init__(server)

    async def get_section_guide(
        self,
        section: str,
        study_type: Optional[str] = None,
        include_examples: bool = True,
    ) -> Dict[str, Any]:
        """Get writing guide for a specific section.

        Args:
            section: Section name (introduction, methods, results, discussion, conclusion)
            study_type: Study type for checklist reference
            include_examples: Whether to include example phrases

        Returns:
            Section guide with structure, tips, and examples
        """
        section_lower = section.lower().replace(" ", "_")

        if section_lower not in SECTION_GUIDES:
            return {
                "success": False,
                "error": f"Unknown section: {section}. Available: {list(SECTION_GUIDES.keys())}",
            }

        guide = SECTION_GUIDES[section_lower]

        result = {
            "success": True,
            "section": guide.section,
            "description": guide.description,
            "structure": guide.structure,
            "word_limit": guide.word_limit,
            "tips": guide.tips,
            "common_mistakes": guide.common_mistakes,
        }

        if include_examples:
            result["example_phrases"] = guide.example_phrases

        # Add relevant checklist items if study type provided
        if study_type and study_type.lower() in STUDY_TYPE_TO_CHECKLIST:
            checklist_name = STUDY_TYPE_TO_CHECKLIST[study_type.lower()]
            checklist = CHECKLISTS.get(checklist_name)
            if checklist:
                section_items = [
                    {"number": item.number, "item": item.item, "description": item.description}
                    for item in checklist.items
                    if section_lower in item.section.lower() or item.section.lower() in section_lower
                ]
                if section_items:
                    result["checklist_items"] = section_items
                    result["checklist_name"] = checklist.name

        return result

    async def get_checklist(
        self,
        study_type: Optional[str] = None,
        checklist_name: Optional[str] = None,
        section_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get appropriate checklist for study type.

        Args:
            study_type: Type of study (rct, cohort, case_control, etc.)
            checklist_name: Direct checklist name (strobe, consort, prisma, care)
            section_filter: Filter items by section (methods, results, etc.)

        Returns:
            Checklist with all items
        """
        # Determine which checklist to use
        if checklist_name:
            name = checklist_name.lower()
        elif study_type:
            name = STUDY_TYPE_TO_CHECKLIST.get(study_type.lower())
            if not name:
                return {
                    "success": False,
                    "error": f"Unknown study type: {study_type}. Available: {list(STUDY_TYPE_TO_CHECKLIST.keys())}",
                }
        else:
            return {
                "success": False,
                "error": "Provide either study_type or checklist_name",
                "available_study_types": list(STUDY_TYPE_TO_CHECKLIST.keys()),
                "available_checklists": list(CHECKLISTS.keys()),
            }

        checklist = CHECKLISTS.get(name)
        if not checklist:
            return {
                "success": False,
                "error": f"Unknown checklist: {name}. Available: {list(CHECKLISTS.keys())}",
            }

        items = checklist.items
        if section_filter:
            items = [i for i in items if section_filter.lower() in i.section.lower()]

        return {
            "success": True,
            "checklist": {
                "name": checklist.name,
                "full_name": checklist.full_name,
                "study_type": checklist.study_type,
                "url": checklist.url,
            },
            "items": [
                {
                    "number": item.number,
                    "item": item.item,
                    "description": item.description,
                    "section": item.section,
                }
                for item in items
            ],
            "total_items": len(items),
        }

    async def get_expert_info(
        self,
        expert: Optional[str] = None,
        section: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get information about expert agents.

        Args:
            expert: Specific expert (clinician, methodologist, statistician, editor)
            section: Get expert(s) responsible for a section

        Returns:
            Expert information and responsibilities
        """
        if expert:
            expert_lower = expert.lower()
            if expert_lower not in EXPERT_AGENTS:
                return {
                    "success": False,
                    "error": f"Unknown expert: {expert}. Available: {list(EXPERT_AGENTS.keys())}",
                }
            agent = EXPERT_AGENTS[expert_lower]
            return {
                "success": True,
                "expert": agent,
            }

        if section:
            section_lower = section.lower()
            responsible = []
            for key, agent in EXPERT_AGENTS.items():
                if "all" in agent["sections"] or section_lower in agent["sections"]:
                    responsible.append({"id": key, **agent})
            return {
                "success": True,
                "section": section,
                "responsible_experts": responsible,
            }

        # Return all experts
        return {
            "success": True,
            "experts": {key: agent for key, agent in EXPERT_AGENTS.items()},
        }

    async def get_response_template(
        self,
        response_type: str,
    ) -> Dict[str, Any]:
        """Get template for responding to reviewer comments.

        Args:
            response_type: Type of response (agree, partially_agree, respectfully_disagree, etc.)

        Returns:
            Response template with placeholders
        """
        response_type_lower = response_type.lower().replace(" ", "_")

        if response_type_lower not in RESPONSE_TEMPLATES:
            return {
                "success": False,
                "error": f"Unknown response type: {response_type}",
                "available_types": list(RESPONSE_TEMPLATES.keys()),
            }

        return {
            "success": True,
            "response_type": response_type_lower,
            "template": RESPONSE_TEMPLATES[response_type_lower],
            "usage_guide": self._get_response_usage_guide(response_type_lower),
        }

    def _get_response_usage_guide(self, response_type: str) -> str:
        """Get usage guide for response type."""
        guides = {
            "agree": "Use when you fully accept the reviewer's suggestion and make the requested change.",
            "partially_agree": "Use when you agree with part of the comment but have valid reasons for not fully implementing it.",
            "respectfully_disagree": "Use when you have strong justification for maintaining your original position.",
            "cannot_perform": "Use when the requested analysis or change is not possible due to data or design limitations.",
            "clarification": "Use when the reviewer misunderstood something that needs clarification.",
        }
        return guides.get(response_type, "")

    async def draft_response_letter(
        self,
        reviewer_comments: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Draft response letter structure for reviewer comments.

        Args:
            reviewer_comments: List of {"reviewer": "1", "comment": "..."}

        Returns:
            Structured response letter template
        """
        grouped = {}
        for item in reviewer_comments:
            reviewer = item.get("reviewer", "Unknown")
            if reviewer not in grouped:
                grouped[reviewer] = []
            grouped[reviewer].append(item.get("comment", ""))

        response_structure = {
            "header": """Dear Editor and Reviewers,

We thank the reviewers for their constructive comments, which have significantly improved our manuscript. Below, we provide point-by-point responses to each comment. Reviewer comments are in **bold**, and our responses follow in regular text. All changes in the manuscript are highlighted in yellow (or tracked).

---
""",
            "reviewers": [],
            "footer": """---

We hope these revisions address all concerns satisfactorily. We remain available for any further clarification.

Sincerely,
[Authors]
""",
        }

        for reviewer, comments in grouped.items():
            reviewer_section = {
                "reviewer": f"Reviewer #{reviewer}",
                "comments": [],
            }
            for i, comment in enumerate(comments, 1):
                reviewer_section["comments"].append({
                    "number": i,
                    "original_comment": comment,
                    "response_placeholder": "[Your response here]",
                    "changes_placeholder": "[Page X, Lines Y-Z]",
                })
            response_structure["reviewers"].append(reviewer_section)

        return {
            "success": True,
            "response_letter": response_structure,
            "tips": [
                "Always thank reviewers for their comments",
                "Be specific with page and line references",
                "Quote revised text in responses",
                "Never be defensive - remain professional",
                "Address every comment, even minor ones",
            ],
        }

    async def analyze_reviewer_comments(
        self,
        comments: List[str],
    ) -> Dict[str, Any]:
        """Categorize and prioritize reviewer comments.

        Args:
            comments: List of reviewer comments

        Returns:
            Categorized comments with suggested actions
        """
        categorized = {
            "major_concerns": [],
            "minor_concerns": [],
            "statistical_issues": [],
            "writing_issues": [],
            "additional_data_requests": [],
        }

        # Keywords for categorization
        major_keywords = ["major", "concern", "flaw", "significant", "important", "fundamental", "serious"]
        statistical_keywords = ["statistical", "p-value", "sample size", "power", "analysis", "test", "CI", "confidence"]
        writing_keywords = ["clarity", "unclear", "confusing", "grammar", "typo", "writing", "language"]
        data_keywords = ["additional", "subgroup", "sensitivity", "more data", "table", "figure", "analysis"]

        for comment in comments:
            comment_lower = comment.lower()

            if any(kw in comment_lower for kw in statistical_keywords):
                categorized["statistical_issues"].append(comment)
            elif any(kw in comment_lower for kw in data_keywords):
                categorized["additional_data_requests"].append(comment)
            elif any(kw in comment_lower for kw in writing_keywords):
                categorized["writing_issues"].append(comment)
            elif any(kw in comment_lower for kw in major_keywords):
                categorized["major_concerns"].append(comment)
            else:
                categorized["minor_concerns"].append(comment)

        return {
            "success": True,
            "categorized_comments": categorized,
            "summary": {
                "major_concerns": len(categorized["major_concerns"]),
                "minor_concerns": len(categorized["minor_concerns"]),
                "statistical_issues": len(categorized["statistical_issues"]),
                "writing_issues": len(categorized["writing_issues"]),
                "additional_data_requests": len(categorized["additional_data_requests"]),
                "total": len(comments),
            },
            "priority_order": [
                "major_concerns",
                "statistical_issues",
                "additional_data_requests",
                "minor_concerns",
                "writing_issues",
            ],
        }

    async def get_all_guides(self) -> Dict[str, Any]:
        """Get overview of all available writing guides and resources.

        Returns:
            Complete list of available guides, checklists, and experts
        """
        return {
            "success": True,
            "sections": list(SECTION_GUIDES.keys()),
            "checklists": {
                name: {
                    "full_name": checklist.full_name,
                    "study_type": checklist.study_type,
                    "item_count": len(checklist.items),
                }
                for name, checklist in CHECKLISTS.items()
            },
            "study_type_to_checklist": STUDY_TYPE_TO_CHECKLIST,
            "experts": {
                key: {"name": agent["name"], "role": agent["role"]}
                for key, agent in EXPERT_AGENTS.items()
            },
            "response_templates": list(RESPONSE_TEMPLATES.keys()),
            "usage_examples": {
                "get_section_guide": 'get_section_guide(section="introduction", study_type="cohort")',
                "get_checklist": 'get_checklist(study_type="rct")',
                "get_expert_info": 'get_expert_info(section="methods")',
                "get_response_template": 'get_response_template(response_type="partially_agree")',
            },
        }
