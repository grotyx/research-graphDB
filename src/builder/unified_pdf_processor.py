"""Unified PDF Processor v3.2.

Note: 이 모듈은 현재 메인 PDF 프로세서입니다.
- v7.5 Simplified Pipeline이 이 모듈 내에 통합되었습니다.
- 이전 unified_processor_v7.py는 src/archive/legacy_v7/로 이동되었습니다.

Features:
- 700+ word 통합 요약 (4개 섹션: Background, Methodology, Key Findings, Conclusions)
- 22개 문서 유형 자동 감지
- 섹션 기반 청킹
- 조건부 엔티티 추출 (의학 콘텐츠만)
- Important Citation 자동 처리

Usage:
    from builder.unified_pdf_processor import UnifiedPDFProcessor
    processor = UnifiedPDFProcessor(llm_client, neo4j_client)
    result = await processor.process_pdf("paper.pdf")

환경변수 기반으로 Claude/Gemini를 선택하여 PDF를 처리합니다.
gemini_vision_processor.py의 모든 dataclass를 통합하여 타입 안전 인터페이스를 제공합니다.

v3.2 Changes (다양한 연구 유형 지원):
- EffectMeasure dataclass 추가: HR, OR, RR, MD, SMD, NNT, I², Cohen's d 등 지원
- StatisticsData.effect_measure 필드 추가
- ExtractedOutcome.effect_measure 필드 추가
- 연구 유형별 적절한 효과 측정치 추출 가이드 추가
- 메타분석, 코호트, 케이스-컨트롤, 단면연구 등 다양한 연구 설계 지원

v3.1 Changes:
- sub_domains (다중 분류), surgical_approach 필드 추가

v3.0 Changes:
- PICO를 chunk-level에서 spine_metadata level로 이동
- Statistics 필드 간소화 (6개 배열 → 3개 필드)

v2.0 Changes:
- gemini_vision_processor.py의 10개 dataclass 통합
- process_pdf_typed() 메서드 추가 (타입 안전 출력)
- ImportantCitation dataclass 추가 (인용 정보)
- VisionProcessorResult 추가 (구조화된 결과)
- _dict_to_vision_result() 변환 함수 추가

v1.1 Changes:
- Haiku 우선 + Sonnet 폴백 전략 추가
- 토큰 초과 시 자동으로 더 큰 모델로 재시도
- stop_reason 감지를 통한 응답 완결성 검증

환경변수:
- LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
- CLAUDE_MODEL: Claude 모델 ID (기본값: claude-haiku-4-5-20251001)
- GEMINI_MODEL: Gemini 모델 ID (기본값: gemini-2.5-flash)
- CLAUDE_FALLBACK_MODEL: 폴백 모델 ID (기본값: claude-sonnet-4-5-20250929)
- CLAUDE_AUTO_FALLBACK: 자동 폴백 활성화 (기본값: true)

Usage:
    # 기본 사용 (dict 출력 - 기존 인터페이스)
    processor = UnifiedPDFProcessor()
    result = await processor.process_pdf("paper.pdf")

    # 타입 안전 출력 (권장)
    result = await processor.process_pdf_typed("paper.pdf")
    print(result.metadata.title)
    print(result.metadata.spine.interventions)

    # Gemini 사용
    processor = UnifiedPDFProcessor(provider="gemini")
"""

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class LLMProvider(Enum):
    """LLM 제공자."""
    CLAUDE = "claude"
    GEMINI = "gemini"


class ChunkMode(Enum):
    """청크 생성 모드."""
    FULL = "full"          # 모든 청크 (50-100개)
    BALANCED = "balanced"  # 균형 잡힌 보존 (15-25개)
    LEAN = "lean"          # 핵심만 (3-4개)


# =============================================================================
# Structured Data Classes (from gemini_vision_processor v2.1)
# =============================================================================

@dataclass
class PICOData:
    """PICO 데이터 (Patient, Intervention, Comparison, Outcome)."""
    population: str = ""
    intervention: str = ""
    comparison: str = ""
    outcome: str = ""


@dataclass
class EffectMeasure:
    """효과 측정치 (다양한 연구 유형 지원).

    v3.2 추가: HR, OR, RR, MD, SMD, NNT, I², Cohen's d 등 지원.
    """
    measure_type: str = ""  # HR, OR, RR, MD, SMD, NNT, I2, Cohen_d, r, eta2, other
    value: str = ""         # 수치값 (e.g., "2.35", "0.82")
    ci_lower: str = ""      # 95% CI 하한 (e.g., "1.42")
    ci_upper: str = ""      # 95% CI 상한 (e.g., "3.89")
    label: str = ""         # 전체 표기 (e.g., "HR 2.35 (95% CI: 1.42-3.89)")


@dataclass
class StatisticsData:
    """통계 데이터 (v3.2 다양한 연구 유형 지원).

    v3.2 변경사항:
    - effect_measure: 다양한 효과 측정치 지원 (HR, OR, RR, I², NNT 등)
    - 기존 additional 필드 유지 (하위호환성)

    지원 효과 측정치:
    - HR (Hazard Ratio): 생존분석, 코호트 연구
    - OR (Odds Ratio): 케이스-컨트롤, 메타분석
    - RR (Relative Risk): 코호트, RCT
    - MD (Mean Difference): 연속형 결과 비교
    - SMD (Standardized Mean Difference): 메타분석
    - NNT (Number Needed to Treat): 임상적 해석
    - I² (I-squared): 메타분석 이질성
    - Cohen's d: 효과 크기
    """
    p_value: str = ""           # 대표 p-value (e.g., "0.001", "<0.001")
    is_significant: bool = False  # p < 0.05 여부
    effect_measure: Optional[EffectMeasure] = None  # 효과 측정치 (v3.2)
    additional: str = ""         # 추가 통계 (e.g., "95% CI: 1.2-3.4")


# TableData, FigureData 삭제됨 (v3.0)
# - Table/Figure 내용은 content에 줄글 요약으로 통합
# - 구조화된 table_data/figure_data 대신 narrative content 사용


@dataclass
class ExtractedChunk:
    """추출된 청크 v3.0 (최적화).

    v3.0 변경사항:
    - pico 제거 → spine_metadata.pico로 이동
    - table_data/figure_data 제거 → content에 줄글 요약 통합
    - source_location, finding_type 제거
    - topic_summary → summary로 변경
    """
    content: str
    content_type: str  # text, table, figure, key_finding
    section_type: str  # abstract, introduction, methods, results, discussion, conclusion
    tier: str  # tier1, tier2

    # 메타데이터
    summary: str = ""  # 1문장 요약 (기존 topic_summary)
    keywords: list[str] = field(default_factory=list)
    is_key_finding: bool = False

    # 통계 (간소화)
    statistics: Optional[StatisticsData] = None


@dataclass
class ExtractedOutcome:
    """추출된 결과 변수 (v3.2 다양한 연구 유형 지원).

    v3.2 변경사항:
    - effect_measure: 다양한 효과 측정치 지원 (기존 effect_size 대체)
    - effect_size 하위호환성 유지
    """
    name: str  # VAS, ODI, JOA, Fusion Rate, etc.
    category: str = ""  # pain, function, radiologic, complication, satisfaction

    # 결과값
    value_intervention: str = ""
    value_control: str = ""
    value_difference: str = ""

    # 통계 (v3.2 확장)
    p_value: str = ""
    confidence_interval: str = ""
    effect_size: str = ""  # 하위호환성 (e.g., "Cohen's d = 0.8")
    effect_measure: Optional[EffectMeasure] = None  # 구조화된 효과 측정치 (v3.2)

    # 시점
    timepoint: str = ""  # preop, postop, 1mo, 6mo, 1yr, 2yr, final

    # 해석
    is_significant: bool = False
    direction: str = ""  # improved, worsened, unchanged


@dataclass
class ComplicationData:
    """합병증 데이터."""
    name: str  # dural tear, infection, nerve injury, etc.
    incidence_intervention: str = ""
    incidence_control: str = ""
    p_value: str = ""
    severity: str = ""  # minor, major, revision_required


@dataclass
class SpineMetadata:
    """척추 특화 메타데이터 v3.1.

    v3.1 변경사항:
    - sub_domain → sub_domains (다중 분류 지원)
    - surgical_approach 필드 추가 (수술 접근법)

    v3.0 변경사항:
    - pico 필드 추가 (chunk에서 이동)
    """
    # 분류 (다중 선택 가능)
    sub_domains: list[str] = field(default_factory=list)
    # Primary: Degenerative, Deformity, Trauma, Tumor, Infection, Inflammatory, Pediatric, Revision, Basic Science
    # (하위호환성을 위해 sub_domain도 유지)
    sub_domain: str = ""  # deprecated, sub_domains 사용 권장

    # 수술 접근법 (다중 선택 가능)
    surgical_approach: list[str] = field(default_factory=list)
    # Options: Endoscopic, Minimally Invasive, Open, Percutaneous, Robot-assisted, Navigation-guided, Microscopic

    pathology: list[str] = field(default_factory=list)  # 여러 병리 가능

    # 해부학
    anatomy_level: str = ""  # L4-5, C5-6, T10-L2
    anatomy_region: str = ""  # cervical, thoracic, lumbar, sacral, thoracolumbar

    # 수술
    interventions: list[str] = field(default_factory=list)
    intervention_details: str = ""  # 수술 기법 상세
    comparison_type: str = ""  # vs_conventional, vs_other_mis, vs_conservative

    # PICO (v3.0 - chunk에서 이동)
    pico: Optional[PICOData] = None

    # 결과
    outcomes: list[ExtractedOutcome] = field(default_factory=list)
    complications: list[ComplicationData] = field(default_factory=list)

    # 추적 관찰
    follow_up_period: str = ""  # e.g., "24 months", "minimum 1 year"
    sample_size: int = 0

    # 핵심 결론
    main_conclusion: str = ""


@dataclass
class ExtractedMetadata:
    """추출된 논문 메타데이터 v2.0."""
    # 기본 정보
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int = 0
    journal: str = ""
    doi: str = ""
    pmid: str = ""

    # 초록
    abstract: str = ""

    # 연구 분류
    study_type: str = ""  # meta-analysis, systematic-review, RCT, prospective-cohort, etc.
    study_design: str = ""  # randomized, non-randomized, single-arm, multi-arm
    evidence_level: str = "5"  # 1a, 1b, 2a, 2b, 3, 4, 5

    # 연구 품질
    sample_size: int = 0
    centers: str = ""  # single-center, multi-center
    blinding: str = ""  # none, single, double

    # 척추 특화
    spine: SpineMetadata = field(default_factory=SpineMetadata)


@dataclass
class ImportantCitation:
    """중요 인용 (Discussion/Results에서 추출)."""
    authors: list[str] = field(default_factory=list)
    year: int = 0
    context: str = ""  # supports_result, contradicts_result, comparison
    section: str = ""  # discussion, results, introduction
    citation_text: str = ""  # 원문 인용 문장
    importance_reason: str = ""  # 중요한 이유
    outcome_comparison: str = ""  # VAS, ODI, fusion_rate 등
    direction_match: bool = False  # 결과 방향 일치 여부


@dataclass
class VisionProcessorResult:
    """타입 안전 처리 결과 (신규 권장 인터페이스)."""
    success: bool
    metadata: ExtractedMetadata = field(default_factory=ExtractedMetadata)
    chunks: list[ExtractedChunk] = field(default_factory=list)
    important_citations: list[ImportantCitation] = field(default_factory=list)

    # 토큰 사용량
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0

    # 통계
    table_count: int = 0
    figure_count: int = 0
    key_finding_count: int = 0

    # 에러
    error: str = ""

    # Provider 정보
    provider: str = ""
    model: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""


# =============================================================================
# Legacy Result Class (하위 호환성 유지)
# =============================================================================

@dataclass
class ProcessorResult:
    """PDF 처리 결과 (dict 기반 - 기존 인터페이스)."""
    success: bool
    provider: str = ""
    model: str = ""
    extracted_data: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0
    error: Optional[str] = None
    fallback_used: bool = False  # Haiku → Sonnet 폴백 사용 여부
    fallback_reason: Optional[str] = None  # 폴백 사유


# =============================================================================
# Extraction Prompt (공통)
# =============================================================================

EXTRACTION_PROMPT = """You are a medical research paper analyst specializing in spine surgery literature.
Analyze this PDF and extract ALL important information in a structured format.

## JSON SCHEMA (v3.0 - Optimized)

{
  "metadata": {
    "title": "Paper title",
    "authors": ["Author 1", "Author 2"],
    "year": 2024,
    "journal": "Journal name",
    "doi": "",
    "pmid": "",
    "abstract": "Complete original abstract text (REQUIRED)",
    "study_type": "meta-analysis/systematic-review/RCT/prospective-cohort/retrospective-cohort/case-control/case-series/case-report/expert-opinion",
    "study_design": "randomized/non-randomized/single-arm/multi-arm",
    "evidence_level": "1a/1b/2a/2b/3/4/5",
    "sample_size": 100,
    "centers": "single-center/multi-center",
    "blinding": "none/single-blind/double-blind/open-label"
  },
  "spine_metadata": {
    "sub_domains": ["Primary domain (e.g., Degenerative)", "Secondary domain if applicable (e.g., Revision)"],
    "surgical_approach": ["Endoscopic/Minimally Invasive/Open/Percutaneous/Robot-assisted/Navigation-guided/Microscopic"],
    "anatomy_level": "L4-5",
    "anatomy_region": "cervical/thoracic/lumbar/sacral/thoracolumbar/lumbosacral",
    "pathology": ["Specific disease name (e.g., lumbar stenosis, cervical myelopathy, schwannoma)"],
    "interventions": ["Standard abbreviation (e.g., UBE, TLIF, laminectomy, ESI)"],
    "comparison_type": "vs_conventional/vs_other_mis/vs_conservative/single_arm",
    "follow_up_months": 24,
    "main_conclusion": "Brief conclusion in 1-2 sentences",
    "pico": {
      "population": "Adults 50-80 years with lumbar stenosis",
      "intervention": "UBE decompression",
      "comparison": "Open laminectomy",
      "outcome": "VAS, ODI, fusion rate"
    },
    "patient_cohorts": [
      {
        "name": "Intervention Group",
        "cohort_type": "intervention",
        "sample_size": 50,
        "mean_age": "65.2 ± 8.4",
        "female_percentage": 45.0,
        "diagnosis": "Lumbar Stenosis",
        "comorbidities": ["Diabetes", "Hypertension"],
        "ASA_score": "2.1 ± 0.5",
        "BMI": "26.3 ± 3.2"
      }
    ],
    "followups": [
      {
        "name": "1-year",
        "timepoint_months": 12,
        "completeness_rate": 95.0,
        "outcomes_at_timepoint": ["VAS", "ODI", "Fusion rate"]
      }
    ],
    "costs": [
      {
        "name": "Total Hospital Cost",
        "cost_type": "direct",
        "mean_cost": 15000,
        "currency": "USD",
        "QALY_gained": 1.2,
        "ICER": 12500,
        "LOS_days": 3.5,
        "readmission_rate": "5%"
      }
    ],
    "quality_metrics": [
      {
        "name": "MINORS Score",
        "assessment_tool": "MINORS",
        "overall_score": 18,
        "overall_rating": "moderate",
        "domain_scores": {"selection": "low", "performance": "moderate", "detection": "moderate"}
      }
    ],
    "outcomes": [
      {
        "name": "VAS",
        "category": "pain/function/radiologic/complication/satisfaction/quality_of_life/survival/event_rate",
        "baseline": 7.2,
        "final": 2.1,
        "value_intervention": "2.1 ± 0.8",
        "value_control": "3.5 ± 1.2",
        "value_difference": "-1.4",
        "p_value": "0.001",
        "confidence_interval": "95% CI: -2.1 to -0.7",
        "effect_size": "Cohen's d = 0.8",
        "effect_measure": {
          "measure_type": "HR/OR/RR/MD/SMD/NNT/I2/Cohen_d/r/other",
          "value": "2.35",
          "ci_lower": "1.42",
          "ci_upper": "3.89",
          "label": "HR 2.35 (95% CI: 1.42-3.89)"
        },
        "timepoint": "preop/postop/1mo/3mo/6mo/1yr/2yr/final",
        "is_significant": true,
        "direction": "improved/worsened/unchanged"
      }
    ],
    "complications": [
      {
        "name": "Dural tear",
        "incidence_intervention": "2.5%",
        "incidence_control": "4.1%",
        "p_value": "0.35",
        "severity": "minor/major/revision_required"
      }
    ]
  },
  "important_citations": [
    {
      "authors": ["Kim", "Park"],
      "year": 2023,
      "context": "supports_result/contradicts_result/comparison",
      "section": "discussion/results/introduction",
      "citation_text": "Original sentence containing the citation",
      "importance_reason": "Why this citation is important",
      "outcome_comparison": "VAS/ODI/fusion_rate",
      "direction_match": true
    }
  ],
  "chunks": [
    {
      "content": "Text content OR narrative summary (for tables: 'Table II shows demographics: BED 10.92±12.93 vs MD 10.32±12.55 (p=0.816), no significant baseline differences.' For figures: '5-8 sentence description of what the figure shows.')",
      "content_type": "text/table/figure/key_finding",
      "section_type": "abstract/introduction/methods/results/discussion/conclusion",
      "tier": "tier1/tier2",
      "is_key_finding": false,
      "summary": "One sentence summary of this chunk",
      "keywords": ["keyword1", "keyword2", "keyword3"],
      "statistics": {
        "p_value": "0.001",
        "is_significant": true,
        "effect_measure": {
          "measure_type": "HR/OR/RR/MD/SMD/NNT/I2/Cohen_d/r/other",
          "value": "2.35",
          "ci_lower": "1.42",
          "ci_upper": "3.89",
          "label": "HR 2.35 (95% CI: 1.42-3.89)"
        },
        "additional": "95% CI: -2.1 to -0.7"
      }
    }
  ]
}

## CRITICAL INSTRUCTIONS

### 1. METADATA EXTRACTION
- Extract complete bibliographic info: title, authors, year, journal, DOI, PMID
- **ABSTRACT**: Extract the complete original abstract text (REQUIRED - DO NOT SKIP)
- Study classification: meta-analysis, systematic-review, RCT, prospective-cohort, retrospective-cohort, case-control, case-series, case-report, expert-opinion
- Evidence level based on Oxford CEBM criteria:
  * 1a: Systematic review of RCTs
  * 1b: Individual RCT with narrow CI
  * 2a: Systematic review of cohort studies
  * 2b: Individual cohort study / low-quality RCT
  * 3: Case-control study
  * 4: Case series
  * 5: Expert opinion

### 2. SPINE-SPECIFIC METADATA (CRITICAL)
Extract ALL spine surgery related fields:

**Sub-domains** (choose ALL applicable - multiple allowed):
Primary categories (based on pathology/condition):
- Degenerative: stenosis, disc herniation, DDD, spondylolisthesis
- Deformity: scoliosis (AIS, adult, congenital, neuromuscular), kyphosis, sagittal imbalance
- Trauma: fractures, dislocations, SCI
- Tumor: primary, metastatic, intradural tumors
- Infection: spondylodiscitis, epidural abscess, TB spine
- Inflammatory: ankylosing spondylitis, RA, psoriatic arthritis
- Pediatric: Scheuermann, spondylolysis, congenital anomalies
- Revision: pseudarthrosis, adjacent segment disease, hardware failure
- Basic Science: biomechanics, tissue engineering, imaging studies

Examples of multiple sub-domains:
- UBE for degenerative stenosis → ["Degenerative"]
- Revision surgery for failed fusion → ["Degenerative", "Revision"]
- Robot-assisted TLIF → ["Degenerative"] (robot is surgical_approach)
- Pediatric scoliosis correction → ["Deformity", "Pediatric"]

**Surgical Approach** (choose ALL applicable - multiple allowed):
- Endoscopic: UBE, BESS, PELD, FELD, MED (using endoscope)
- Minimally Invasive: MIS-TLIF, tubular, small incision without endoscope
- Open: traditional open surgery, laminectomy, open fusion
- Percutaneous: percutaneous pedicle screw, vertebroplasty
- Robot-assisted: ROSA, Mazor, ExcelsiusGPS
- Navigation-guided: O-arm, CT navigation, image-guided
- Microscopic: microscope-assisted surgery

Examples:
- UBE decompression → surgical_approach: ["Endoscopic", "Minimally Invasive"]
- Robot-assisted MIS-TLIF → surgical_approach: ["Robot-assisted", "Minimally Invasive"]
- Open laminectomy → surgical_approach: ["Open"]
- Microscopic discectomy → surgical_approach: ["Microscopic", "Minimally Invasive"]

**Pathology** (be SPECIFIC - extract exact condition names):
- Cervical: myelopathy, radiculopathy, OPLL, OLF, disc herniation
- Thoracic: stenosis, disc herniation, kyphosis
- Lumbar: stenosis (central/foraminal), disc herniation, spondylolisthesis
- Tumors: hemangioma, schwannoma, meningioma, metastasis, myeloma, chordoma
- Inflammatory: AS, RA, psoriatic arthritis, SAPHO
- Congenital: Klippel-Feil, tethered cord, diastematomyelia
- Other: FBSS, synovial cyst, Modic changes

**Anatomy**:
- anatomy_level: Specific spinal levels (e.g., "L4-5", "L3-S1", "C5-6")
- anatomy_region: cervical/thoracic/lumbar/sacral/thoracolumbar/lumbosacral

**Interventions** (use standard abbreviations):
- Fusion: TLIF, PLIF, ALIF, OLIF, LLIF, ACDF, posterior fusion
- Endoscopic: UBE, BESS, PELD, FELD, MED
- Decompression: laminectomy, laminoplasty, foraminotomy, discectomy
- Osteotomy: SPO, PSO, VCR
- Augmentation: PVP, PKP, sacroplasty
- Tumor: en bloc resection, vertebrectomy, separation surgery
- Injection: ESI, facet injection, RFA, SCS
- Navigation/Robotics: robot-assisted, O-arm, CT navigation
- Revision: pseudarthrosis repair, hardware removal

**PICO** (Paper-level, in spine_metadata):
- population: Study subjects (age, diagnosis, inclusion criteria)
- intervention: Primary treatment/surgery
- comparison: Control group treatment
- outcome: Main outcome measures

**Outcomes** (extract ALL with values, p-values, timepoints, directions):
- Pain: VAS (back/leg), NRS
- Function: ODI, NDI, JOA, mJOA, EQ-5D, SF-36
- Radiological: fusion rate, lordosis, SVA, Cobb angle, disc height
- Surgical: operation time, blood loss, hospital stay
- Complications: dural tear, infection, nerve injury, reoperation
- Satisfaction: MacNab, patient satisfaction
- Oncology: survival rate, recurrence, SINS score

**Complications**: Types, incidence rates, severity
**Follow-up period** and **Main conclusion**

### 3. CHUNK EXTRACTION (Target: 15-25 chunks)

**Tier Assignment:**
- **tier1** (High Priority): Abstract, Results (key findings), Conclusion, Tables
- **tier2** (Supporting): Introduction, Methods, Discussion, Figures

**Chunk Distribution:**
- text: 8-12 chunks (abstract, intro, methods, discussion, conclusion)
- key_finding: 5-8 chunks (results with statistics)
- table: 2-4 chunks (narrative summaries)
- figure: 2-3 chunks (narrative descriptions)

**For TEXT chunks:**
- Extract summary (1 sentence)
- Extract keywords (3-5 medical terms)
- Mark is_key_finding=true for important findings
- Size: 200-500 characters

**For TABLE chunks (content_type="table", tier="tier1"):**
- Write a NARRATIVE SUMMARY in content field
- Example: "Table II shows demographics: BED group (n=47) 10.92±12.93 years, MD group (n=45) 10.32±12.55 years (p=0.816). No significant baseline differences in age, BMI, or operative levels."
- Include: table identifier, key values, p-values, interpretation
- DO NOT use structured table_data object

**For FIGURE chunks (content_type="figure", tier="tier2"):**
- Write a NARRATIVE DESCRIPTION in content field (5-8 sentences)
- Describe: what is shown, numerical values, trends, clinical significance
- Example: "Figure 3 shows Kaplan-Meier survival curves. At 2-year follow-up, the UBE group achieved 94% fusion rate compared to 89% in the conventional group. The difference was not statistically significant (p=0.24). The curves diverge at 12 months..."
- DO NOT use structured figure_data object

**For KEY_FINDING chunks:**
- Set content_type="key_finding", is_key_finding=true, tier="tier1"
- Include statistics in both content AND statistics fields
- Extract from Results section

### 4. STATISTICS FORMAT (v3.2 - Diverse Study Types Support)

**IMPORTANT: Use the appropriate effect measure based on study type:**

| Study Type | Primary Effect Measures | Examples |
|------------|------------------------|----------|
| RCT | MD, SMD, Cohen's d, RR | "MD -1.4 (95% CI: -2.1 to -0.7)", "Cohen's d = 0.8" |
| Cohort (prospective/retrospective) | HR, RR, OR | "HR 2.35 (95% CI: 1.42-3.89)" |
| Case-control | OR | "OR 3.2 (95% CI: 1.8-5.6)" |
| Cross-sectional | OR, PR (Prevalence Ratio) | "OR 1.85 (95% CI: 1.2-2.8)" |
| Meta-analysis | SMD, MD, OR, RR, I² | "SMD -0.45 (95% CI: -0.67 to -0.23), I²=42%" |
| Survival analysis | HR, Median survival | "HR 0.72 (95% CI: 0.58-0.89), median 24 months" |

**Statistics Fields:**
- **p_value**: The most representative p-value (string, e.g., "0.001", "<0.001")
- **is_significant**: Boolean (true if p < 0.05)
- **effect_measure**: Structured effect measure object:
  - measure_type: "HR/OR/RR/MD/SMD/NNT/I2/Cohen_d/r/other"
  - value: numeric value as string (e.g., "2.35")
  - ci_lower: lower 95% CI bound (e.g., "1.42")
  - ci_upper: upper 95% CI bound (e.g., "3.89")
  - label: complete formatted string (e.g., "HR 2.35 (95% CI: 1.42-3.89)")
- **additional**: Other statistics as a single string (e.g., "NNT=5, I²=42%")

### 5. IMPORTANT CITATIONS
In Discussion/Results sections, extract citations that:
- SUPPORT the study's results (similar findings from prior studies)
- CONTRADICT the study's results (different/opposing findings)
- COMPARE directly with the current study's outcomes
Extract: author surnames, year, citation_text, direction_match

### 5.5 EXTENDED ENTITY EXTRACTION (v7.2)

**Patient Cohort Data** (extract when present):
- cohort_type: "intervention", "control", "total", "propensity_matched"
- sample_size: Number of patients in each group
- mean_age: Mean age with SD (e.g., "65.2 ± 8.4")
- female_percentage: Percentage of female patients
- diagnosis: Primary diagnosis for the cohort
- comorbidities: List of comorbidities (diabetes, hypertension, etc.)
- ASA_score: ASA physical status classification
- BMI: Mean BMI if available

**Follow-Up Data** (extract timepoints):
- timepoint_name: "6-month", "1-year", "2-year", "Final"
- timepoint_months: Numeric months from baseline
- completeness_rate: Follow-up completion rate (%)
- outcomes_at_timepoint: Outcomes measured at this specific timepoint

**Cost Data** (extract from health economics studies):
- cost_type: "direct", "indirect", "total", "incremental"
- mean_cost: Mean cost value
- currency: USD, EUR, KRW, etc.
- QALY_gained: Quality-adjusted life years
- ICER: Incremental cost-effectiveness ratio
- LOS_days: Length of hospital stay (days)
- readmission_rate: 30-day/90-day readmission rate

**Quality Assessment Metrics** (extract quality ratings):
- assessment_tool: "GRADE", "MINORS", "Newcastle-Ottawa", "Jadad", "AMSTAR", "Cochrane ROB"
- overall_score: Numeric score
- overall_rating: "high", "moderate", "low", "very low"
- For GRADE: certainty level, downgrade/upgrade reasons
- For ROB: domain-specific assessments (selection, performance, detection bias)

### 6. QUALITY REQUIREMENTS
- Tables/Figures: Write narrative summaries with ALL key data points
- Statistics: Extract exact values ("0.023", "<0.001")
- Preserve exact wording for abstract and conclusions
- Mark ALL chunks containing statistical results as is_key_finding=true
- Return ONLY valid JSON, no additional text

Return valid JSON following the schema above."""


# =============================================================================
# JSON Repair Utilities
# =============================================================================

def _repair_json(text: str) -> str:
    """Attempt to repair malformed JSON from LLM output.

    Common fixes:
    - Remove trailing commas
    - Close unclosed brackets/braces
    - Fix missing/mismatched quotes
    - Handle truncated responses
    - Fix control characters
    """
    import re

    # 1. Extract JSON block from markdown
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]

    text = text.strip()

    # 2. Fix control characters (newlines, tabs) that break JSON
    # But preserve \n and \t in strings
    lines = text.split('\n')
    text = '\n'.join(line for line in lines if line.strip())

    # 3. Remove trailing commas before } or ]
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # 4. Fix missing opening quotes in arrays (e.g., 0.003" -> "0.003")
    # Pattern: comma or [ followed by value ending with quote but no opening quote
    text = re.sub(r'([\[,]\s*)(\d+\.?\d*)"', r'\1"\2"', text)

    # 5. Fix inconsistent quote usage in numeric arrays
    # Convert all p-values to strings for consistency
    def fix_p_value_array(match):
        content = match.group(1)
        # Split by comma and fix each value
        values = []
        for v in content.split(','):
            v = v.strip()
            if v:
                # Remove existing quotes and re-add
                v = v.strip('"').strip("'")
                values.append(f'"{v}"')
        return '"p_values": [' + ', '.join(values) + ']'

    text = re.sub(r'"p_values":\s*\[(.*?)\]', fix_p_value_array, text, flags=re.DOTALL)

    # 6. Count brackets to detect truncation
    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')

    # 7. Try to close truncated JSON
    if open_braces > close_braces or open_brackets > close_brackets:
        last_brace = text.rfind('}')
        last_bracket = text.rfind(']')

        if last_brace > 0 or last_bracket > 0:
            last_pos = max(last_brace, last_bracket)
            remaining = text[last_pos+1:].strip()
            if remaining and remaining not in ['}', ']', ',']:
                text = text[:last_pos+1]

        missing_braces = open_braces - text.count('}')
        missing_brackets = open_brackets - text.count(']')
        text = text + ']' * missing_brackets + '}' * missing_braces

    # 8. Try to validate
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        error_pos = e.pos if hasattr(e, 'pos') else -1
        error_msg = str(e)

        # Fix: missing comma
        if error_pos > 0 and "Expecting ',' delimiter" in error_msg:
            text = text[:error_pos] + ',' + text[error_pos:]
            try:
                json.loads(text)
                return text
            except Exception:
                pass

        # Fix: control character errors - remove problematic control chars
        if "Invalid control character" in error_msg:
            # Remove control characters except newline/tab
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
            try:
                json.loads(text)
                return text
            except Exception:
                pass

        # Return text as-is if all fixes fail
        return text


# =============================================================================
# Claude Backend
# =============================================================================

class ClaudeBackend:
    """Claude PDF 처리 백엔드."""

    # 모델별 max output tokens (Claude 4.5는 최대 64000 지원)
    MODEL_MAX_TOKENS = {
        "haiku": 64000,   # Haiku 4.5: 64000 최대
        "sonnet": 64000,  # Sonnet 4.5: 64000 최대
    }

    def __init__(self, model: Optional[str] = None):
        import anthropic

        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.model = model or os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.client = anthropic.Anthropic(api_key=self.api_key)

        logger.info(f"Claude backend initialized: model={self.model}")

    def _get_max_tokens(self, model: str) -> int:
        """모델에 맞는 max_tokens 반환."""
        model_lower = model.lower()
        if "haiku" in model_lower:
            return self.MODEL_MAX_TOKENS["haiku"]
        elif "sonnet" in model_lower:
            return self.MODEL_MAX_TOKENS["sonnet"]
        return 16384  # 기본값

    def process_pdf(self, pdf_path: Path, prompt: str, model_override: Optional[str] = None) -> dict[str, Any]:
        """PDF 처리.

        Args:
            pdf_path: PDF 파일 경로
            prompt: 추출 프롬프트
            model_override: 모델 오버라이드 (폴백 시 사용)

        Returns:
            처리 결과 딕셔너리 (success, data, stop_reason 등 포함)
        """
        import time
        start_time = time.time()

        model_to_use = model_override or self.model

        try:
            # PDF를 base64로 인코딩
            pdf_bytes = pdf_path.read_bytes()
            base64_data = base64.standard_b64encode(pdf_bytes).decode("utf-8")

            # API 호출 (streaming 사용 - 10분 이상 걸릴 수 있는 작업)
            max_tokens = self._get_max_tokens(model_to_use)
            logger.info(f"Calling Claude API with streaming: model={model_to_use}, max_tokens={max_tokens}")

            # Streaming으로 응답 수집
            collected_text = ""
            input_tokens = 0
            output_tokens = 0
            stop_reason = None

            with self.client.messages.stream(
                model=model_to_use,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64_data,
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            }
                        ]
                    }
                ],
            ) as stream:
                for text_chunk in stream.text_stream:
                    collected_text += text_chunk

                # 최종 메시지에서 메타데이터 추출
                final_message = stream.get_final_message()
                stop_reason = final_message.stop_reason
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens

            latency = time.time() - start_time

            # 토큰 초과로 응답이 잘린 경우
            if stop_reason == "max_tokens":
                logger.warning(f"Response truncated (max_tokens reached): {output_tokens} tokens")
                return {
                    "success": False,
                    "error": "max_tokens_exceeded",
                    "stop_reason": stop_reason,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency": latency,
                    "model_used": model_to_use,
                }

            # 응답 파싱 (with repair attempt)
            repaired_text = _repair_json(collected_text)

            try:
                data = json.loads(repaired_text)
            except json.JSONDecodeError as first_error:
                # If repair failed, try original text as fallback
                text = collected_text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]

                try:
                    data = json.loads(text.strip())
                except json.JSONDecodeError:
                    # Both attempts failed
                    raise first_error

            return {
                "success": True,
                "data": data,
                "stop_reason": stop_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency": latency,
                "model_used": model_to_use,
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error at position {e.pos}: {e.msg}")
            # Log context around error for debugging
            raw_text = collected_text if 'collected_text' in locals() else ''
            if hasattr(e, 'pos') and e.pos > 0 and raw_text:
                start = max(0, e.pos - 50)
                end = min(len(raw_text), e.pos + 50)
                logger.error(f"Context around error: ...{raw_text[start:end]}...")
            return {
                "success": False,
                "error": f"JSON parsing error: {e}",
                "latency": time.time() - start_time,
                "model_used": model_to_use,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency": time.time() - start_time,
                "model_used": model_to_use,
            }

    def process_text(self, text: str, prompt: str, model_override: Optional[str] = None) -> dict[str, Any]:
        """텍스트 처리 (PMC 전문 등).

        Args:
            text: 처리할 텍스트 내용
            prompt: 추출 프롬프트
            model_override: 모델 오버라이드 (폴백 시 사용)

        Returns:
            처리 결과 딕셔너리 (success, data, stop_reason 등 포함)
        """
        import time
        start_time = time.time()

        model_to_use = model_override or self.model

        try:
            # API 호출 (streaming 사용)
            max_tokens = self._get_max_tokens(model_to_use)
            logger.info(f"Calling Claude API for text processing: model={model_to_use}, max_tokens={max_tokens}")

            # Streaming으로 응답 수집
            collected_text = ""
            input_tokens = 0
            output_tokens = 0
            stop_reason = None

            with self.client.messages.stream(
                model=model_to_use,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"{prompt}\n\n---\n\n{text}"
                            }
                        ]
                    }
                ]
            ) as stream:
                for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == 'content_block_delta':
                            if hasattr(event.delta, 'text'):
                                collected_text += event.delta.text
                        elif event.type == 'message_delta':
                            if hasattr(event, 'usage'):
                                output_tokens = getattr(event.usage, 'output_tokens', 0)
                            stop_reason = getattr(event.delta, 'stop_reason', None)
                        elif event.type == 'message_start':
                            if hasattr(event.message, 'usage'):
                                input_tokens = getattr(event.message.usage, 'input_tokens', 0)

            latency = time.time() - start_time

            # Stop reason 체크 (max_tokens로 끊긴 경우)
            if stop_reason == "max_tokens":
                logger.warning(
                    f"Response truncated (stop_reason=max_tokens). "
                    f"Output tokens: {output_tokens}"
                )
                return {
                    "success": False,
                    "error": "max_tokens_exceeded",
                    "stop_reason": stop_reason,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency": latency,
                    "model_used": model_to_use,
                }

            # JSON 파싱
            try:
                data = json.loads(collected_text)
            except json.JSONDecodeError as first_error:
                # JSON 블록 추출 시도
                text_to_parse = collected_text
                if "```json" in text_to_parse:
                    text_to_parse = text_to_parse.split("```json")[1].split("```")[0]
                elif "```" in text_to_parse:
                    text_to_parse = text_to_parse.split("```")[1].split("```")[0]

                try:
                    data = json.loads(text_to_parse.strip())
                except json.JSONDecodeError:
                    raise first_error

            return {
                "success": True,
                "data": data,
                "stop_reason": stop_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency": latency,
                "model_used": model_to_use,
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return {
                "success": False,
                "error": f"JSON parsing error: {e}",
                "latency": time.time() - start_time,
                "model_used": model_to_use,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency": time.time() - start_time,
                "model_used": model_to_use,
            }


# =============================================================================
# Gemini Backend
# =============================================================================

class GeminiBackend:
    """Gemini PDF 처리 백엔드."""

    def __init__(self, model: Optional[str] = None):
        from google import genai

        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=self.api_key)

        logger.info(f"Gemini backend initialized: model={self.model}")

    async def process_pdf(self, pdf_path: Path, prompt: str) -> dict[str, Any]:
        """PDF 처리 (async)."""
        import time
        from google.genai import types

        start_time = time.time()

        try:
            # PDF 업로드
            loop = asyncio.get_event_loop()
            uploaded_file = await loop.run_in_executor(
                None,
                lambda: self.client.files.upload(file=pdf_path)
            )

            # API 호출
            pdf_part = types.Part.from_uri(
                file_uri=uploaded_file.uri,
                mime_type="application/pdf"
            )

            config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=65536,
                response_mime_type="application/json",
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[pdf_part, prompt],
                config=config,
            )

            latency = time.time() - start_time

            # 파일 삭제
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self.client.files.delete(name=uploaded_file.name)
                )
            except Exception:
                pass

            # 응답 파싱 (with repair attempt)
            repaired_text = _repair_json(response.text)

            try:
                data = json.loads(repaired_text)
            except json.JSONDecodeError as first_error:
                # If repair failed, try original text as fallback
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]

                try:
                    data = json.loads(text.strip())
                except json.JSONDecodeError:
                    raise first_error

            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

            return {
                "success": True,
                "data": data,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency": latency,
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error at position {e.pos}: {e.msg}")
            return {
                "success": False,
                "error": f"JSON parsing error: {e}",
                "latency": time.time() - start_time,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency": time.time() - start_time,
            }


# =============================================================================
# Unified PDF Processor
# =============================================================================

class UnifiedPDFProcessor:
    """통합 PDF 처리기.

    환경변수 기반으로 Claude/Gemini를 자동 선택합니다.
    Claude 사용 시 Haiku → Sonnet 자동 폴백을 지원합니다.

    환경변수:
        LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
        CLAUDE_MODEL: Claude 모델 ID (기본값: claude-haiku-4-5-20251001)
        CLAUDE_FALLBACK_MODEL: 폴백 모델 ID (기본값: claude-sonnet-4-5-20250929)
        CLAUDE_AUTO_FALLBACK: 자동 폴백 활성화 (기본값: true)
        GEMINI_MODEL: Gemini 모델 ID

    폴백 동작:
        1. Haiku로 먼저 시도 (8,192 max tokens)
        2. 토큰 초과 (stop_reason == "max_tokens") 발생 시
        3. 자동으로 Sonnet으로 재시도 (16,384 max tokens)

    Usage:
        # 환경변수 기반 자동 선택
        processor = UnifiedPDFProcessor()
        result = await processor.process_pdf("paper.pdf")

        # 특정 provider 지정
        processor = UnifiedPDFProcessor(provider="gemini")

        # 폴백 비활성화
        processor = UnifiedPDFProcessor(auto_fallback=False)
    """

    # 기본 폴백 모델
    DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        auto_fallback: Optional[bool] = None,
    ):
        """초기화.

        Args:
            provider: LLM 제공자 ("claude" 또는 "gemini"). None이면 환경변수 사용.
            model: 모델 ID. None이면 환경변수 사용.
            auto_fallback: 자동 폴백 활성화 여부. None이면 환경변수 사용.
        """
        # Provider 결정
        provider_str = provider or os.getenv("LLM_PROVIDER", "claude")
        self.provider = LLMProvider(provider_str.lower())

        # 자동 폴백 설정
        if auto_fallback is not None:
            self.auto_fallback = auto_fallback
        else:
            fallback_env = os.getenv("CLAUDE_AUTO_FALLBACK", "true").lower()
            self.auto_fallback = fallback_env in ("true", "1", "yes")

        # 폴백 모델 설정
        self.fallback_model = os.getenv("CLAUDE_FALLBACK_MODEL", self.DEFAULT_FALLBACK_MODEL)

        # Backend 초기화
        if self.provider == LLMProvider.CLAUDE:
            self._backend = ClaudeBackend(model=model)
            self.model = self._backend.model
        else:
            self._backend = GeminiBackend(model=model)
            self.model = self._backend.model

        logger.info(
            f"UnifiedPDFProcessor initialized: provider={self.provider.value}, "
            f"model={self.model}, auto_fallback={self.auto_fallback}"
        )

    async def process_pdf(
        self,
        pdf_path: str | Path,
        mode: ChunkMode = ChunkMode.BALANCED,
    ) -> ProcessorResult:
        """PDF 처리.

        Haiku로 먼저 시도하고, 토큰 초과 시 자동으로 Sonnet으로 폴백합니다.

        Args:
            pdf_path: PDF 파일 경로
            mode: 청크 생성 모드 (현재 미사용, 향후 확장용)

        Returns:
            ProcessorResult (fallback_used, fallback_reason 포함)
        """
        path = Path(pdf_path)

        if not path.exists():
            return ProcessorResult(
                success=False,
                provider=self.provider.value,
                model=self.model,
                error=f"File not found: {pdf_path}"
            )

        logger.info(f"Processing PDF: {path.name} with {self.provider.value}/{self.model}")

        # 폴백 추적 변수
        fallback_used = False
        fallback_reason = None
        model_used = self.model
        total_latency = 0.0

        # Provider에 따라 처리
        if self.provider == LLMProvider.CLAUDE:
            # 1차 시도: 기본 모델 (Haiku)
            # v7.14.27: asyncio.to_thread()로 병렬 처리 지원
            result = await asyncio.to_thread(
                self._backend.process_pdf, path, EXTRACTION_PROMPT
            )
            total_latency = result.get("latency", 0)

            # 토큰 초과로 실패한 경우 + 자동 폴백 활성화 시 → Sonnet으로 재시도
            if (not result["success"] and
                result.get("error") == "max_tokens_exceeded" and
                self.auto_fallback):

                logger.warning(
                    f"Token overflow detected ({result.get('output_tokens', 0)} tokens). "
                    f"Retrying with fallback model: {self.fallback_model}"
                )

                # 2차 시도: 폴백 모델 (Sonnet)
                # v7.14.27: asyncio.to_thread()로 병렬 처리 지원
                result = await asyncio.to_thread(
                    self._backend.process_pdf,
                    path,
                    EXTRACTION_PROMPT,
                    self.fallback_model  # model_override
                )

                fallback_used = True
                fallback_reason = f"max_tokens_exceeded (primary model output: {result.get('output_tokens', 0)} tokens)"
                model_used = self.fallback_model
                total_latency += result.get("latency", 0)

                logger.info(f"Fallback {'succeeded' if result['success'] else 'failed'}: {self.fallback_model}")
        else:
            # Gemini: 폴백 없이 직접 처리
            result = await self._backend.process_pdf(path, EXTRACTION_PROMPT)
            total_latency = result.get("latency", 0)

        # 결과 반환
        if not result["success"]:
            return ProcessorResult(
                success=False,
                provider=self.provider.value,
                model=model_used,
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                latency_seconds=total_latency,
                error=result.get("error", "Unknown error"),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )

        return ProcessorResult(
            success=True,
            provider=self.provider.value,
            model=model_used,
            extracted_data=result.get("data", {}),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            latency_seconds=total_latency,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    async def process_text(
        self,
        text: str,
        title: str = "",
        source: str = "pmc",
        mode: ChunkMode = ChunkMode.BALANCED,
    ) -> ProcessorResult:
        """텍스트 처리 (PMC 전문 등).

        PDF 처리와 동일한 LLM 추출 로직을 사용하여 텍스트에서
        구조화된 메타데이터, 청크, 아웃컴 등을 추출합니다.

        Args:
            text: 처리할 텍스트 내용 (전문)
            title: 논문 제목 (선택)
            source: 소스 타입 (pmc, abstract 등)
            mode: 청크 생성 모드

        Returns:
            ProcessorResult (PDF 처리와 동일한 형식)
        """
        if not text or not text.strip():
            return ProcessorResult(
                success=False,
                provider=self.provider.value,
                model=self.model,
                error="Empty text provided"
            )

        logger.info(f"Processing text ({len(text)} chars) with {self.provider.value}/{self.model}")

        # 텍스트 전용 프롬프트 (PDF 프롬프트 수정)
        text_prompt = EXTRACTION_PROMPT.replace(
            "Analyze this PDF and extract ALL important information",
            "Analyze this medical research paper text and extract ALL important information"
        )

        # 폴백 추적 변수
        fallback_used = False
        fallback_reason = None
        model_used = self.model
        total_latency = 0.0

        # Provider에 따라 처리
        if self.provider == LLMProvider.CLAUDE:
            # 1차 시도: 기본 모델 (Haiku)
            # v7.14.27: asyncio.to_thread()로 병렬 처리 지원
            result = await asyncio.to_thread(
                self._backend.process_text, text, text_prompt
            )
            total_latency = result.get("latency", 0)

            # 토큰 초과로 실패한 경우 + 자동 폴백 활성화 시 → Sonnet으로 재시도
            if (not result["success"] and
                result.get("error") == "max_tokens_exceeded" and
                self.auto_fallback):

                logger.warning(
                    f"Token overflow detected. Retrying with fallback model: {self.fallback_model}"
                )

                # 2차 시도: 폴백 모델 (Sonnet)
                # v7.14.27: asyncio.to_thread()로 병렬 처리 지원
                result = await asyncio.to_thread(
                    self._backend.process_text,
                    text,
                    text_prompt,
                    self.fallback_model  # model_override 위치 인자로 전달
                )

                fallback_used = True
                fallback_reason = "max_tokens_exceeded"
                model_used = self.fallback_model
                total_latency += result.get("latency", 0)

                logger.info(f"Fallback {'succeeded' if result['success'] else 'failed'}")
        else:
            # Gemini: process_text 미지원 → 에러 반환
            return ProcessorResult(
                success=False,
                provider=self.provider.value,
                model=self.model,
                error="Gemini backend does not support text processing (use PDF)"
            )

        # 결과 반환
        if not result["success"]:
            return ProcessorResult(
                success=False,
                provider=self.provider.value,
                model=model_used,
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                latency_seconds=total_latency,
                error=result.get("error", "Unknown error"),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )

        return ProcessorResult(
            success=True,
            provider=self.provider.value,
            model=model_used,
            extracted_data=result.get("data", {}),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            latency_seconds=total_latency,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    @property
    def provider_name(self) -> str:
        """현재 사용 중인 provider 이름."""
        return self.provider.value

    @property
    def model_name(self) -> str:
        """현재 사용 중인 모델 이름."""
        return self.model

    # =========================================================================
    # Type-Safe API (신규 권장 인터페이스)
    # =========================================================================

    def _dict_to_vision_result(
        self,
        data: dict,
        input_tokens: int,
        output_tokens: int,
        latency: float,
        provider: str,
        model: str,
        fallback_used: bool = False,
        fallback_reason: str = "",
    ) -> VisionProcessorResult:
        """dict 결과를 VisionProcessorResult로 변환.

        Args:
            data: LLM에서 반환된 JSON dict
            input_tokens: 입력 토큰 수
            output_tokens: 출력 토큰 수
            latency: 처리 시간 (초)
            provider: Provider 이름
            model: 모델 이름
            fallback_used: 폴백 사용 여부
            fallback_reason: 폴백 사유

        Returns:
            VisionProcessorResult 인스턴스
        """
        # 1. Metadata 파싱 (v7.14.27: None 값 처리)
        meta_dict = data.get("metadata") or {}
        spine_dict = meta_dict.get("spine_metadata") or data.get("spine_metadata") or {}

        # PICO 파싱 (v3.0 - spine_metadata에서 추출)
        pico_dict = spine_dict.get("pico")
        pico = None
        if pico_dict:
            pico = PICOData(
                population=pico_dict.get("population", ""),
                intervention=pico_dict.get("intervention", ""),
                comparison=pico_dict.get("comparison", ""),
                outcome=pico_dict.get("outcome", ""),
            )

        # Outcomes 파싱 (v3.2 확장: effect_measure 지원)
        outcomes = []
        for o in spine_dict.get("outcomes", []):
            # effect_measure 파싱 (v3.2)
            outcome_effect_measure = None
            em_dict = o.get("effect_measure")
            if em_dict and isinstance(em_dict, dict):
                outcome_effect_measure = EffectMeasure(
                    measure_type=str(em_dict.get("measure_type", "")),
                    value=str(em_dict.get("value", "")),
                    ci_lower=str(em_dict.get("ci_lower", "")),
                    ci_upper=str(em_dict.get("ci_upper", "")),
                    label=str(em_dict.get("label", "")),
                )

            outcomes.append(ExtractedOutcome(
                name=o.get("name", ""),
                category=o.get("category", ""),
                value_intervention=str(o.get("value_intervention", "")),
                value_control=str(o.get("value_control", "")),
                value_difference=str(o.get("value_difference", "")),
                p_value=str(o.get("p_value", "")),
                confidence_interval=str(o.get("confidence_interval", "")),
                effect_size=str(o.get("effect_size", "")),
                effect_measure=outcome_effect_measure,  # v3.2
                timepoint=o.get("timepoint", ""),
                is_significant=bool(o.get("is_significant", False)),
                direction=o.get("direction", ""),
            ))

        # Complications 파싱
        complications = []
        for c in spine_dict.get("complications", []):
            complications.append(ComplicationData(
                name=c.get("name", ""),
                incidence_intervention=str(c.get("incidence_intervention", "")),
                incidence_control=str(c.get("incidence_control", "")),
                p_value=str(c.get("p_value", "")),
                severity=c.get("severity", ""),
            ))

        # v3.1: sub_domains (list) + surgical_approach (list)
        # 하위호환성: sub_domain (string)도 지원
        sub_domains = spine_dict.get("sub_domains", []) or []
        sub_domain_str = spine_dict.get("sub_domain", "")
        # sub_domain이 있고 sub_domains가 비어있으면 sub_domain을 sub_domains로 변환
        if sub_domain_str and not sub_domains:
            sub_domains = [sub_domain_str]

        spine_metadata = SpineMetadata(
            sub_domains=sub_domains,
            sub_domain=sub_domain_str or (sub_domains[0] if sub_domains else ""),  # 하위호환성
            surgical_approach=spine_dict.get("surgical_approach", []) or [],
            pathology=spine_dict.get("pathology", []) or [],
            anatomy_level=spine_dict.get("anatomy_level", ""),
            anatomy_region=spine_dict.get("anatomy_region", ""),
            interventions=spine_dict.get("interventions", []) or [],
            intervention_details=spine_dict.get("intervention_details", ""),
            comparison_type=spine_dict.get("comparison_type", ""),
            pico=pico,  # v3.0: PICO 추가
            outcomes=outcomes,
            complications=complications,
            follow_up_period=str(spine_dict.get("follow_up_period", spine_dict.get("follow_up_months", ""))),
            sample_size=int(spine_dict.get("sample_size", 0) or 0),
            main_conclusion=spine_dict.get("main_conclusion", ""),
        )

        metadata = ExtractedMetadata(
            title=meta_dict.get("title", ""),
            authors=meta_dict.get("authors", []) or [],
            year=int(meta_dict.get("year", 0) or 0),
            journal=meta_dict.get("journal", ""),
            doi=meta_dict.get("doi", ""),
            pmid=meta_dict.get("pmid", ""),
            abstract=meta_dict.get("abstract", ""),
            study_type=meta_dict.get("study_type", ""),
            study_design=meta_dict.get("study_design", ""),
            evidence_level=meta_dict.get("evidence_level", "5"),
            sample_size=int(meta_dict.get("sample_size", 0) or 0),
            centers=meta_dict.get("centers", ""),
            blinding=meta_dict.get("blinding", ""),
            spine=spine_metadata,
        )

        # 2. Chunks 파싱 (v3.0 - 간소화)
        chunks = []
        table_count = 0
        figure_count = 0
        key_finding_count = 0

        for c in data.get("chunks", []):
            # Statistics 파싱 (v3.2 확장: p_value, is_significant, effect_measure, additional)
            stats_dict = c.get("statistics")
            statistics = None
            if stats_dict:
                # effect_measure 파싱 (v3.2)
                effect_measure = None
                em_dict = stats_dict.get("effect_measure")
                if em_dict and isinstance(em_dict, dict):
                    effect_measure = EffectMeasure(
                        measure_type=str(em_dict.get("measure_type", "")),
                        value=str(em_dict.get("value", "")),
                        ci_lower=str(em_dict.get("ci_lower", "")),
                        ci_upper=str(em_dict.get("ci_upper", "")),
                        label=str(em_dict.get("label", "")),
                    )

                statistics = StatisticsData(
                    p_value=str(stats_dict.get("p_value", "")),
                    is_significant=bool(stats_dict.get("is_significant", False)),
                    effect_measure=effect_measure,
                    additional=str(stats_dict.get("additional", "")),
                )

            content_type = c.get("content_type", "text")
            is_key_finding = bool(c.get("is_key_finding", False))

            # 콘텐츠 타입별 카운트
            if content_type == "table":
                table_count += 1
            elif content_type == "figure":
                figure_count += 1
            if is_key_finding:
                key_finding_count += 1

            # v3.0: PICO, table_data, figure_data, source_location, finding_type, topic_summary 제거
            chunks.append(ExtractedChunk(
                content=c.get("content", ""),
                content_type=content_type,
                section_type=c.get("section_type", ""),
                tier=c.get("tier", "tier2"),
                summary=c.get("summary", "") or c.get("topic_summary", ""),  # 하위호환: topic_summary도 지원
                keywords=c.get("keywords", []) or [],
                is_key_finding=is_key_finding,
                statistics=statistics,
            ))

        # 3. Important Citations 파싱
        important_citations = []
        for cit in data.get("important_citations", []):
            important_citations.append(ImportantCitation(
                authors=cit.get("authors", []) or [],
                year=int(cit.get("year", 0) or 0),
                context=cit.get("context", ""),
                section=cit.get("section", ""),
                citation_text=cit.get("citation_text", ""),
                importance_reason=cit.get("importance_reason", ""),
                outcome_comparison=cit.get("outcome_comparison", ""),
                direction_match=bool(cit.get("direction_match", False)),
            ))

        return VisionProcessorResult(
            success=True,
            metadata=metadata,
            chunks=chunks,
            important_citations=important_citations,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
            table_count=table_count,
            figure_count=figure_count,
            key_finding_count=key_finding_count,
            provider=provider,
            model=model,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    async def process_pdf_typed(
        self,
        pdf_path: str | Path,
        mode: ChunkMode = ChunkMode.BALANCED,
    ) -> VisionProcessorResult:
        """PDF 처리 (타입 안전 출력 - 신규 권장 인터페이스).

        기존 process_pdf()와 동일하게 동작하지만,
        dict 대신 구조화된 VisionProcessorResult를 반환합니다.

        Args:
            pdf_path: PDF 파일 경로
            mode: 청크 생성 모드

        Returns:
            VisionProcessorResult (타입 안전 dataclass)

        Example:
            processor = UnifiedPDFProcessor()
            result = await processor.process_pdf_typed("paper.pdf")

            # IDE 자동완성 지원
            print(result.metadata.title)
            print(result.metadata.spine.interventions)
            for chunk in result.chunks:
                if chunk.table_data:
                    print(chunk.table_data.markdown)
        """
        # 기존 process_pdf 호출
        raw_result = await self.process_pdf(pdf_path, mode)

        # 실패 시 에러 결과 반환
        if not raw_result.success:
            return VisionProcessorResult(
                success=False,
                error=raw_result.error or "Unknown error",
                input_tokens=raw_result.input_tokens,
                output_tokens=raw_result.output_tokens,
                latency_seconds=raw_result.latency_seconds,
                provider=raw_result.provider,
                model=raw_result.model,
                fallback_used=raw_result.fallback_used,
                fallback_reason=raw_result.fallback_reason or "",
            )

        # dict → VisionProcessorResult 변환
        return self._dict_to_vision_result(
            data=raw_result.extracted_data,
            input_tokens=raw_result.input_tokens,
            output_tokens=raw_result.output_tokens,
            latency=raw_result.latency_seconds,
            provider=raw_result.provider,
            model=raw_result.model,
            fallback_used=raw_result.fallback_used,
            fallback_reason=raw_result.fallback_reason or "",
        )


# =============================================================================
# Factory Function
# =============================================================================

def create_pdf_processor(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> UnifiedPDFProcessor:
    """PDF 프로세서 생성 팩토리 함수.

    Args:
        provider: "claude" 또는 "gemini" (None이면 환경변수 사용)
        model: 모델 ID (None이면 환경변수 사용)

    Returns:
        UnifiedPDFProcessor 인스턴스
    """
    return UnifiedPDFProcessor(provider=provider, model=model)


# =============================================================================
# Usage Example
# =============================================================================

async def example_usage():
    """사용 예시."""
    # 환경변수 기반 자동 선택 (기본: Claude Haiku + 자동 폴백)
    processor = UnifiedPDFProcessor()
    print(f"Using: {processor.provider_name} / {processor.model_name}")
    print(f"Auto-fallback: {processor.auto_fallback} → {processor.fallback_model}")

    # 특정 provider 지정
    # processor_gemini = UnifiedPDFProcessor(provider="gemini")
    # processor_sonnet = UnifiedPDFProcessor(provider="claude", model="claude-sonnet-4-5-20250929")
    # processor_no_fallback = UnifiedPDFProcessor(auto_fallback=False)

    # PDF 처리
    result = await processor.process_pdf("test.pdf")

    if result.success:
        print(f"✅ Success!")
        print(f"   Provider: {result.provider}")
        print(f"   Model: {result.model}")
        print(f"   Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out")
        print(f"   Latency: {result.latency_seconds:.2f}s")
        print(f"   Title: {result.extracted_data.get('metadata', {}).get('title', 'N/A')}")

        # 폴백 사용 여부 표시
        if result.fallback_used:
            print(f"   ⚠️ Fallback used: {result.fallback_reason}")
    else:
        print(f"❌ Error: {result.error}")
        if result.fallback_used:
            print(f"   ⚠️ Fallback was attempted but also failed")


if __name__ == "__main__":
    asyncio.run(example_usage())
