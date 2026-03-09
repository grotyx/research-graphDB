"""Entity Extractor for v1.1 Universal Processing Pipeline.

Conditional medical entity extraction for research/clinical documents.
Only extracts entities when document type and content indicate medical focus.

Features:
- Keyword-based medical content detection (no LLM required)
- LLM-powered entity extraction when applicable
- Integration with EntityNormalizer for normalization
- Support for non-medical document types (skips extraction)
- v1.1: Extended entity types (risk factors, radiographic parameters, complications, prediction models)

Supported Entity Types (v1.1):
1. Interventions: Surgical procedures, treatments
2. Pathologies: Diseases, conditions
3. Outcomes: Measured results
4. Anatomy: Body structures, spinal levels
5. Risk Factors: Patient factors affecting outcomes (diabetes, smoking, BMI, etc.)
6. Radiographic Parameters: Spine alignment measurements (PI, LL, SVA, etc.)
7. Complications: Surgical complications (dural tear, SSI, pseudarthrosis, etc.)
8. Prediction Models: ML/AI models mentioned (Random Forest, XGBoost, etc.)

Usage:
    extractor = EntityExtractor()

    # Check if extraction is needed
    should_extract = await extractor.should_extract(
        document_type=DocumentType.JOURNAL_ARTICLE,
        text=full_text
    )

    # Extract entities if applicable
    if should_extract:
        entities = await extractor.extract(text, DocumentType.JOURNAL_ARTICLE)
        print(entities.interventions)  # List[ExtractedEntity]
        print(entities.pathologies)    # List[ExtractedEntity]
        print(entities.risk_factors)   # List[ExtractedEntity] (v1.1)
        print(entities.complications)  # List[ExtractedEntity] (v1.1)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

# Import document type detector
from .document_type_detector import DocumentType

# Import LLM client
from llm import LLMClient, LLMConfig

# Try to import EntityNormalizer (optional)
try:
    from graph.entity_normalizer import EntityNormalizer, NormalizationResult
    NORMALIZER_AVAILABLE = True
except ImportError:
    try:
        from ..graph.entity_normalizer import EntityNormalizer, NormalizationResult
        NORMALIZER_AVAILABLE = True
    except ImportError:
        NORMALIZER_AVAILABLE = False
        EntityNormalizer = None
        NormalizationResult = None

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ExtractedEntity:
    """Extracted medical entity.

    Attributes:
        name: Canonical entity name
        category: Entity category (e.g., "Fusion Surgery", "Degenerative")
        aliases: Alternative names found in document
        context: How entity appears in document (excerpt)
        confidence: Extraction confidence (0.0-1.0)
        snomed_code: SNOMED-CT code (v1.8)
        snomed_term: SNOMED-CT preferred term (v1.8)
    """
    name: str
    category: str = ""
    aliases: list[str] = field(default_factory=list)
    context: str = ""
    confidence: float = 1.0
    snomed_code: str = ""  # v1.8: SNOMED-CT code
    snomed_term: str = ""  # v1.8: SNOMED-CT preferred term


@dataclass
class ExtractedEntities:
    """Complete set of extracted medical entities.

    Attributes:
        interventions: Surgical procedures, treatments
        pathologies: Diseases, conditions
        outcomes: Measured results
        anatomy: Body structures, levels
        risk_factors: Patient factors that affect outcomes (v1.1)
        radiographic_parameters: Spine alignment measurements (v1.1)
        complications: Surgical complications (v1.1)
        prediction_models: ML/AI models mentioned (v1.1)
        patient_cohorts: Study population characteristics (v1.2)
        followups: Follow-up timepoints and data (v1.2)
        costs: Healthcare cost information (v1.2)
        quality_metrics: Study quality assessments (v1.2)
        is_medical_content: Whether content is medical/clinical
    """
    interventions: list[ExtractedEntity] = field(default_factory=list)
    pathologies: list[ExtractedEntity] = field(default_factory=list)
    outcomes: list[ExtractedEntity] = field(default_factory=list)
    anatomy: list[ExtractedEntity] = field(default_factory=list)
    # v1.1: New entity types
    risk_factors: list[ExtractedEntity] = field(default_factory=list)
    radiographic_parameters: list[ExtractedEntity] = field(default_factory=list)
    complications: list[ExtractedEntity] = field(default_factory=list)
    prediction_models: list[ExtractedEntity] = field(default_factory=list)
    # v1.2: Additional entity types
    patient_cohorts: list[ExtractedEntity] = field(default_factory=list)
    followups: list[ExtractedEntity] = field(default_factory=list)
    costs: list[ExtractedEntity] = field(default_factory=list)
    quality_metrics: list[ExtractedEntity] = field(default_factory=list)
    is_medical_content: bool = True


# =============================================================================
# Medical Keyword Lists
# =============================================================================

# Medical procedure/treatment terms
MEDICAL_PROCEDURE_KEYWORDS = {
    "surgery", "surgical", "operation", "procedure", "treatment", "therapy",
    "intervention", "technique", "approach", "method",
    "fusion", "decompression", "laminectomy", "discectomy", "corpectomy",
    "fixation", "instrumentation", "implant", "prosthesis",
    "endoscopic", "percutaneous", "minimally invasive", "open",
    "anterior", "posterior", "lateral", "transforaminal",
    "injection", "ablation", "stimulation", "augmentation",
    "osteotomy", "arthroplasty", "replacement", "reconstruction",
    "수술", "시술", "치료", "요법", "술식"
}

# Anatomical terms
ANATOMICAL_KEYWORDS = {
    "spine", "spinal", "vertebra", "vertebral", "disc", "disk",
    "cervical", "thoracic", "lumbar", "sacral", "coccygeal",
    "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12",
    "L1", "L2", "L3", "L4", "L5",
    "S1", "S2", "S3", "S4", "S5",
    "foramen", "foraminal", "canal", "lamina", "pedicle", "facet",
    "cord", "nerve", "root", "dura", "epidural", "intradural",
    "척추", "경추", "흉추", "요추", "천추", "추간판", "디스크"
}

# Clinical/diagnostic terms
CLINICAL_KEYWORDS = {
    "patient", "patients", "case", "cases", "cohort", "subjects",
    "diagnosis", "diagnostic", "symptom", "symptoms", "sign", "signs",
    "clinical", "hospital", "surgical", "postoperative", "preoperative",
    "outcome", "outcomes", "result", "results", "complication", "complications",
    "follow-up", "followup", "assessment", "evaluation",
    "pain", "disability", "function", "functional", "neurological",
    "radiological", "radiographic", "imaging", "MRI", "CT", "X-ray",
    "환자", "증상", "진단", "결과", "합병증", "추적"
}

# Disease/pathology terms
PATHOLOGY_KEYWORDS = {
    "stenosis", "herniation", "herniated", "degeneration", "degenerative",
    "spondylolisthesis", "scoliosis", "kyphosis", "lordosis",
    "fracture", "fractures", "trauma", "injury", "instability",
    "tumor", "cancer", "metastasis", "metastatic", "neoplasm",
    "infection", "osteomyelitis", "discitis", "abscess",
    "myelopathy", "radiculopathy", "neuropathy", "paralysis",
    "osteoporosis", "osteoporotic", "arthritis", "arthrosis",
    "협착증", "탈출증", "골절", "종양", "감염"
}

# Outcome measurement terms
OUTCOME_KEYWORDS = {
    "VAS", "ODI", "NDI", "JOA", "mJOA", "SF-36", "SF-12", "EQ-5D",
    "pain score", "disability index", "functional outcome",
    "fusion rate", "complication rate", "reoperation rate",
    "satisfaction", "improvement", "recovery",
    "Cobb angle", "lordosis", "kyphosis", "SVA", "PI-LL",
    "blood loss", "operative time", "hospital stay",
    "통증", "기능", "만족도", "유합률"
}

# Study design terms (indicates research document)
RESEARCH_KEYWORDS = {
    "study", "trial", "randomized", "randomised", "controlled",
    "prospective", "retrospective", "cohort", "case-control",
    "meta-analysis", "systematic review", "observational",
    "multicenter", "single-center", "double-blind", "placebo",
    "efficacy", "effectiveness", "comparison", "versus", "vs",
    "연구", "시험", "분석", "비교"
}

# Risk factor terms (v1.1)
RISK_FACTOR_KEYWORDS = {
    "risk factor", "predictor", "associated", "odds ratio", "hazard ratio", "relative risk",
    "diabetes", "smoking", "obesity", "BMI", "age", "frailty", "osteoporosis",
    "comorbidity", "ASA", "Charlson", "CCI", "albumin", "malnutrition",
    "위험인자", "예측인자", "당뇨", "흡연", "비만"
}

# Radiographic parameter terms (v1.1)
RADIOGRAPHIC_KEYWORDS = {
    "PI", "LL", "PT", "SS", "SVA", "Cobb angle", "sagittal balance", "pelvic incidence",
    "lumbar lordosis", "pelvic tilt", "sacral slope", "thoracic kyphosis", "T1 pelvic angle",
    "PI-LL mismatch", "alignment", "deformity", "kyphosis", "lordosis",
    "골반입사각", "요추전만", "시상면균형"
}

# Prediction model terms (v1.1)
PREDICTION_MODEL_KEYWORDS = {
    "prediction model", "predictive model", "machine learning", "ML", "AI", "artificial intelligence",
    "logistic regression", "random forest", "XGBoost", "neural network", "SVM",
    "AUC", "accuracy", "sensitivity", "specificity", "ROC", "SHAP",
    "validation", "calibration", "Brier score", "C-index",
    "예측모델", "머신러닝", "인공지능"
}

# Complication terms (v1.1)
COMPLICATION_KEYWORDS = {
    "complication", "adverse event", "dural tear", "durotomy", "CSF leak",
    "infection", "SSI", "wound", "hematoma", "neurological deficit",
    "pseudarthrosis", "nonunion", "adjacent segment", "ASD", "revision",
    "implant failure", "screw loosening", "cage subsidence",
    "합병증", "감염", "경막손상", "인접분절"
}

# Patient cohort terms (v1.2)
PATIENT_COHORT_KEYWORDS = {
    "cohort", "sample size", "n=", "patients", "subjects", "participants",
    "demographics", "age", "gender", "sex", "male", "female",
    "BMI", "comorbidities", "ASA score", "Charlson", "CCI",
    "inclusion criteria", "exclusion criteria", "eligibility",
    "propensity matched", "PSM", "1:1 matching",
    "intervention group", "control group", "study population",
    "대상환자", "연구대상", "환자군", "대조군"
}

# Follow-up terms (v1.2)
FOLLOWUP_KEYWORDS = {
    "follow-up", "followup", "FU", "follow up", "follow-up period",
    "6 months", "12 months", "24 months", "2 years", "5 years",
    "minimum follow-up", "mean follow-up", "final follow-up",
    "lost to follow-up", "dropout", "attrition",
    "6개월", "1년", "2년", "추적관찰", "추적기간"
}

# Cost/Economic terms (v1.2)
COST_KEYWORDS = {
    "cost", "hospital cost", "total cost", "direct cost", "indirect cost",
    "cost-effectiveness", "cost-utility", "ICER", "QALY", "quality-adjusted",
    "length of stay", "LOS", "readmission", "90-day episode",
    "willingness to pay", "WTP", "budget impact",
    "비용", "입원기간", "재원기간", "비용효과"
}

# Quality assessment terms (v1.2)
QUALITY_METRIC_KEYWORDS = {
    "GRADE", "quality of evidence", "certainty of evidence",
    "risk of bias", "ROB", "Cochrane", "Newcastle-Ottawa", "NOS",
    "MINORS", "Jadad", "AMSTAR", "ROBINS-I",
    "high quality", "moderate quality", "low quality", "very low quality",
    "selection bias", "performance bias", "detection bias", "attrition bias",
    "근거수준", "비뚤림위험", "문헌의질"
}


# =============================================================================
# EntityExtractor Class
# =============================================================================

class EntityExtractor:
    """Conditional medical entity extraction for v1.0 pipeline.

    Only extracts entities when:
    1. Document type is medical/research (JOURNAL_ARTICLE, BOOK, THESIS, etc.)
    2. Content contains medical terminology

    Skips extraction for:
    - WEBPAGE, BLOG_POST, NEWSPAPER (unless medical content detected)
    - PATENT, SOFTWARE, DATASET (domain-specific, not medical)
    - VIDEO, PRESENTATION (media types)
    """

    # Document types that typically require entity extraction
    MEDICAL_DOCUMENT_TYPES = [
        DocumentType.JOURNAL_ARTICLE,
        DocumentType.BOOK,
        DocumentType.BOOK_SECTION,
        DocumentType.THESIS,
        DocumentType.CONFERENCE_PAPER,
        DocumentType.REPORT,
        DocumentType.PREPRINT,
    ]

    # Document types where content determines extraction need
    CONDITIONAL_DOCUMENT_TYPES = [
        DocumentType.WEBPAGE,
        DocumentType.BLOG_POST,
        DocumentType.NEWSPAPER_ARTICLE,
        DocumentType.MAGAZINE_ARTICLE,
    ]

    # Document types to always skip
    SKIP_DOCUMENT_TYPES = [
        DocumentType.PATENT,
        DocumentType.DATASET,
        DocumentType.SOFTWARE,
        DocumentType.VIDEO,
        DocumentType.PRESENTATION,
        DocumentType.STANDARD,
        DocumentType.DOCUMENT,  # Generic/unknown
    ]

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        entity_normalizer: Optional[EntityNormalizer] = None
    ):
        """Initialize entity extractor.

        Args:
            llm_client: LLM client for entity extraction (optional)
            entity_normalizer: EntityNormalizer for term normalization (optional)
        """
        self.llm_client = llm_client or LLMClient(config=LLMConfig(temperature=0.1))

        # Initialize normalizer if available
        if NORMALIZER_AVAILABLE and entity_normalizer is None:
            try:
                self.normalizer = EntityNormalizer()
            except Exception as e:
                logger.warning(f"Failed to initialize EntityNormalizer: {e}")
                self.normalizer = None
        else:
            self.normalizer = entity_normalizer

        logger.info("EntityExtractor initialized")

    async def should_extract(
        self,
        document_type: DocumentType,
        text: str,
        min_keyword_threshold: int = 5
    ) -> bool:
        """Determine if entity extraction is applicable.

        Args:
            document_type: Document type
            text: Document text (sample or full)
            min_keyword_threshold: Minimum medical keywords to detect

        Returns:
            True if entity extraction should be performed
        """
        # Always extract for medical document types
        if document_type in self.MEDICAL_DOCUMENT_TYPES:
            logger.info(f"Document type {document_type.value} → extract entities")
            return True

        # Never extract for skip types
        if document_type in self.SKIP_DOCUMENT_TYPES:
            logger.info(f"Document type {document_type.value} → skip extraction")
            return False

        # Conditional: check if content is medical
        if document_type in self.CONDITIONAL_DOCUMENT_TYPES:
            is_medical = await self._is_medical_content(text, min_keyword_threshold)
            logger.info(
                f"Document type {document_type.value}, "
                f"medical content: {is_medical} → "
                f"{'extract' if is_medical else 'skip'}"
            )
            return is_medical

        # Default: check content
        is_medical = await self._is_medical_content(text, min_keyword_threshold)
        logger.info(f"Unknown document type, medical content: {is_medical}")
        return is_medical

    async def extract(
        self,
        text: str,
        document_type: DocumentType
    ) -> Optional[ExtractedEntities]:
        """Extract medical entities if applicable.

        Args:
            text: Document text (full or substantial portion)
            document_type: Document type

        Returns:
            ExtractedEntities or None if not applicable
        """
        # Check if extraction is needed
        should_extract = await self.should_extract(document_type, text)
        if not should_extract:
            logger.info("Entity extraction not applicable for this document")
            return ExtractedEntities(is_medical_content=False)

        # Extract entities using LLM
        try:
            entities = await self._extract_with_llm(text)
            logger.info(
                f"Extracted entities: "
                f"{len(entities.interventions)} interventions, "
                f"{len(entities.pathologies)} pathologies, "
                f"{len(entities.outcomes)} outcomes, "
                f"{len(entities.anatomy)} anatomy, "
                f"{len(entities.risk_factors)} risk_factors, "
                f"{len(entities.radiographic_parameters)} radiographic_parameters, "
                f"{len(entities.complications)} complications, "
                f"{len(entities.prediction_models)} prediction_models, "
                f"{len(entities.patient_cohorts)} patient_cohorts, "
                f"{len(entities.followups)} followups, "
                f"{len(entities.costs)} costs, "
                f"{len(entities.quality_metrics)} quality_metrics"
            )
            return entities

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}", exc_info=True)
            # Return empty but valid structure
            return ExtractedEntities(is_medical_content=True)

    async def _is_medical_content(
        self,
        text: str,
        min_keyword_threshold: int = 5
    ) -> bool:
        """Check if content is medical/clinical using keyword detection.

        No LLM required - fast keyword-based detection.

        Args:
            text: Document text
            min_keyword_threshold: Minimum keywords to consider medical

        Returns:
            True if content appears to be medical
        """
        text_lower = text.lower()

        # Count keyword matches in each category
        counts = {
            "procedure": sum(1 for kw in MEDICAL_PROCEDURE_KEYWORDS if kw in text_lower),
            "anatomy": sum(1 for kw in ANATOMICAL_KEYWORDS if kw in text_lower),
            "clinical": sum(1 for kw in CLINICAL_KEYWORDS if kw in text_lower),
            "pathology": sum(1 for kw in PATHOLOGY_KEYWORDS if kw in text_lower),
            "outcome": sum(1 for kw in OUTCOME_KEYWORDS if kw in text_lower),
            "research": sum(1 for kw in RESEARCH_KEYWORDS if kw in text_lower),
            # v1.1: New keyword categories
            "risk_factor": sum(1 for kw in RISK_FACTOR_KEYWORDS if kw in text_lower),
            "radiographic": sum(1 for kw in RADIOGRAPHIC_KEYWORDS if kw in text_lower),
            "prediction_model": sum(1 for kw in PREDICTION_MODEL_KEYWORDS if kw in text_lower),
            "complication": sum(1 for kw in COMPLICATION_KEYWORDS if kw in text_lower),
        }

        # Total keywords found
        total_keywords = sum(counts.values())

        # Require minimum threshold across categories
        if total_keywords < min_keyword_threshold:
            logger.debug(
                f"Medical content check: {total_keywords} keywords < {min_keyword_threshold} threshold"
            )
            return False

        # Require at least 2 categories
        categories_present = sum(1 for count in counts.values() if count > 0)
        if categories_present < 2:
            logger.debug(
                f"Medical content check: only {categories_present} categories present"
            )
            return False

        logger.info(
            f"Medical content detected: {total_keywords} keywords "
            f"across {categories_present} categories: {counts}"
        )
        return True

    async def _extract_with_llm(self, text: str) -> ExtractedEntities:
        """Use LLM to extract entities.

        Args:
            text: Document text

        Returns:
            ExtractedEntities with extracted information
        """
        # Truncate text if too long (use first 4000 words for extraction)
        words = text.split()
        if len(words) > 4000:
            text_sample = " ".join(words[:4000]) + "..."
            logger.info(f"Text truncated to 4000 words for entity extraction")
        else:
            text_sample = text

        prompt = f"""Extract medical entities from this document.

DOCUMENT TEXT:
{text_sample}

---

Extract the following types of entities:

1. **Interventions**: Surgical procedures, treatments, therapeutic approaches
   - Examples: TLIF, laminectomy, spinal fusion, epidural injection

2. **Pathologies**: Diseases, conditions, diagnoses
   - Examples: lumbar stenosis, disc herniation, scoliosis, spinal fracture

3. **Outcomes**: Measured results, outcome variables
   - Examples: VAS, ODI, fusion rate, complication rate, pain score

4. **Anatomy**: Anatomical structures, spinal levels
   - Examples: L4-L5, lumbar spine, cervical vertebra, neural foramina

5. **Risk Factors** (v1.1): Patient factors that affect outcomes
   - Examples: diabetes, smoking, obesity, BMI>30, age>65, frailty, osteoporosis

6. **Radiographic Parameters** (v1.1): Spine alignment measurements
   - Examples: PI, LL, SVA, Cobb angle, PI-LL mismatch, sagittal balance

7. **Complications** (v1.1): Surgical complications mentioned
   - Examples: dural tear, SSI, pseudarthrosis, ASD, screw loosening

8. **Prediction Models** (v1.1): ML/AI models if mentioned
   - Examples: Random Forest for pseudarthrosis prediction, XGBoost for complication risk

9. **Patient Cohorts** (v1.2): Study population characteristics
   - Examples: n=150, age 65±8 years, intervention group, control group, propensity-matched cohort

10. **Follow-ups** (v1.2): Follow-up timepoints and data
    - Examples: 6-month follow-up, 2-year minimum FU, final follow-up (mean 38 months)

11. **Costs** (v1.2): Healthcare cost data if mentioned
    - Examples: hospital cost $45,000, ICER $32,000/QALY, 90-day episode cost

12. **Quality Metrics** (v1.2): Study quality assessments
    - Examples: GRADE high quality, MINORS 18/24, Newcastle-Ottawa 7 stars

For each entity, provide:
- **name**: The entity name as it appears in the text
- **category**: General category (e.g., "Fusion Surgery", "Degenerative Disease", "Pain Outcome")
- **aliases**: Alternative names found in the text (if any)
- **context**: A brief excerpt showing how it's mentioned (max 100 chars)

Return results in JSON format:
{{
  "interventions": [
    {{"name": "TLIF", "category": "Fusion Surgery", "aliases": ["Transforaminal Lumbar Interbody Fusion"], "context": "comparison of TLIF and PLIF"}}
  ],
  "pathologies": [
    {{"name": "Lumbar Stenosis", "category": "Degenerative", "aliases": ["LSS"], "context": "patients with lumbar stenosis"}}
  ],
  "outcomes": [
    {{"name": "VAS", "category": "Pain", "aliases": ["Visual Analog Scale"], "context": "VAS scores at 6 months"}}
  ],
  "anatomy": [
    {{"name": "L4-L5", "category": "Lumbar", "aliases": [], "context": "single-level L4-L5 fusion"}}
  ],
  "risk_factors": [
    {{"name": "Diabetes", "category": "Comorbidity", "aliases": ["DM"], "context": "patients with diabetes mellitus"}}
  ],
  "radiographic_parameters": [
    {{"name": "PI-LL", "category": "Sagittal Alignment", "aliases": ["PI-LL mismatch"], "context": "PI-LL mismatch > 10 degrees"}}
  ],
  "complications": [
    {{"name": "Dural Tear", "category": "Intraoperative", "aliases": ["Durotomy", "CSF leak"], "context": "incidental dural tear occurred"}}
  ],
  "prediction_models": [
    {{"name": "Random Forest", "category": "Machine Learning", "aliases": ["RF"], "context": "Random Forest model with AUC 0.85"}}
  ],
  "patient_cohorts": [
    {{"name": "Intervention Group", "category": "Study Cohort", "aliases": ["Treatment arm"], "context": "n=75 patients in intervention group"}}
  ],
  "followups": [
    {{"name": "6-month", "category": "Follow-up Timepoint", "aliases": ["6mo FU"], "context": "at 6-month follow-up, VAS improved"}}
  ],
  "costs": [
    {{"name": "Hospital Cost", "category": "Direct Cost", "aliases": ["Hospitalization cost"], "context": "mean hospital cost was $45,000"}}
  ],
  "quality_metrics": [
    {{"name": "GRADE", "category": "Quality Assessment", "aliases": ["GRADE certainty"], "context": "GRADE: moderate quality evidence"}}
  ]
}}

If no entities found in a category, return empty array.
"""

        try:
            # Use LLM to extract entities as structured JSON
            response = await self.llm_client.generate(
                prompt=prompt,
                system="You are a medical information extraction assistant. "
                       "Extract entities accurately from medical documents."
            )
            response_text = response.text if hasattr(response, 'text') else str(response)

            # Parse JSON response
            response_json = self._extract_json_from_response(response_text)
            data = json.loads(response_json)

            # Convert to ExtractedEntity objects
            entities = ExtractedEntities(
                interventions=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("interventions", [])
                ],
                pathologies=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("pathologies", [])
                ],
                outcomes=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("outcomes", [])
                ],
                anatomy=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("anatomy", [])
                ],
                # v1.1: New entity types (backward compatible - use empty list if not present)
                risk_factors=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("risk_factors", [])
                ],
                radiographic_parameters=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("radiographic_parameters", [])
                ],
                complications=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("complications", [])
                ],
                prediction_models=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("prediction_models", [])
                ],
                # v1.2: Additional entity types (backward compatible)
                patient_cohorts=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("patient_cohorts", [])
                ],
                followups=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("followups", [])
                ],
                costs=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("costs", [])
                ],
                quality_metrics=[
                    ExtractedEntity(
                        name=item.get("name", ""),
                        category=item.get("category", ""),
                        aliases=item.get("aliases", []),
                        context=item.get("context", ""),
                        confidence=1.0
                    )
                    for item in data.get("quality_metrics", [])
                ],
                is_medical_content=True
            )

            # Normalize entities if normalizer available
            if self.normalizer:
                entities = self._normalize_entities(entities)

            return entities

        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}", exc_info=True)
            # Return empty entities
            return ExtractedEntities(is_medical_content=True)

    def _extract_json_from_response(self, response: str) -> str:
        """Extract JSON from LLM response (may be wrapped in markdown).

        Args:
            response: LLM response text

        Returns:
            Clean JSON string
        """
        # Try to find JSON in markdown code block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Try to find any JSON object
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json_match.group(0)

        # Return as-is
        return response

    def _normalize_entities(self, entities: ExtractedEntities) -> ExtractedEntities:
        """Normalize entity names using EntityNormalizer.

        v1.8: Also extracts and stores SNOMED-CT codes.

        Args:
            entities: Extracted entities

        Returns:
            Entities with normalized names and SNOMED codes
        """
        if not self.normalizer:
            return entities

        # Normalize interventions
        normalized_interventions = []
        for entity in entities.interventions:
            result = self.normalizer.normalize_intervention(entity.name)
            if result.confidence > 0.5:  # Only use if reasonable confidence
                entity.name = result.normalized
                if result.category:
                    entity.category = result.category
                # v1.8: Store SNOMED code
                if result.snomed_code:
                    entity.snomed_code = result.snomed_code
                    entity.snomed_term = result.snomed_term
            normalized_interventions.append(entity)

        # Normalize pathologies
        normalized_pathologies = []
        for entity in entities.pathologies:
            result = self.normalizer.normalize_pathology(entity.name)
            if result.confidence > 0.5:
                entity.name = result.normalized
                # v1.8: Store SNOMED code
                if result.snomed_code:
                    entity.snomed_code = result.snomed_code
                    entity.snomed_term = result.snomed_term
            normalized_pathologies.append(entity)

        # Normalize outcomes
        normalized_outcomes = []
        for entity in entities.outcomes:
            result = self.normalizer.normalize_outcome(entity.name)
            if result.confidence > 0.5:
                entity.name = result.normalized
                # v1.8: Store SNOMED code
                if result.snomed_code:
                    entity.snomed_code = result.snomed_code
                    entity.snomed_term = result.snomed_term
            normalized_outcomes.append(entity)

        entities.interventions = normalized_interventions
        entities.pathologies = normalized_pathologies
        entities.outcomes = normalized_outcomes

        return entities


# =============================================================================
# Convenience Functions
# =============================================================================

async def extract_medical_entities(
    text: str,
    document_type: DocumentType,
    llm_client: Optional[LLMClient] = None
) -> Optional[ExtractedEntities]:
    """Convenience function for entity extraction.

    Args:
        text: Document text
        document_type: Document type
        llm_client: Optional LLM client

    Returns:
        ExtractedEntities or None
    """
    extractor = EntityExtractor(llm_client=llm_client)
    return await extractor.extract(text, document_type)


async def is_medical_document(
    text: str,
    document_type: DocumentType,
    min_keyword_threshold: int = 5
) -> bool:
    """Check if document contains medical content.

    Args:
        text: Document text
        document_type: Document type
        min_keyword_threshold: Minimum keywords to consider medical

    Returns:
        True if medical content detected
    """
    extractor = EntityExtractor()
    return await extractor.should_extract(document_type, text, min_keyword_threshold)
