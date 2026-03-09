"""Entity Normalizer for Spine Terminology.

척추 수술 관련 용어 정규화 (한국어/영어 지원).

Features:
- 수술법 별칭 매핑 (UBE ↔ BESS ↔ Biportal ↔ 내시경 수술)
- 결과변수 별칭 매핑 (VAS ↔ Visual Analog Scale)
- 질환명 정규화 (Lumbar Stenosis ↔ 요추 협착증)
- 한국어 조사 처리 (TLIF가 → TLIF, 내시경 수술을 → UBE)
- Unicode-aware 단어 경계 (한글/영문 혼용 텍스트 지원)

Korean Language Support:
- Full support for Korean medical terminology
- Automatic particle stripping (가, 이, 를, 을, 와, 과, etc.)
- Mixed Korean/English text extraction
- Unicode-aware pattern matching (no ASCII word boundaries for Korean)

Examples:
    >>> normalizer = EntityNormalizer()
    >>>
    >>> # Korean normalization
    >>> normalizer.normalize_intervention("척추 유합술")
    NormalizationResult(normalized='Spinal Fusion', confidence=1.0)
    >>>
    >>> # Particle handling
    >>> normalizer.normalize_intervention("TLIF가")
    NormalizationResult(normalized='TLIF', confidence=0.95)
    >>>
    >>> # Mixed text extraction
    >>> text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"
    >>> interventions = normalizer.extract_and_normalize_interventions(text)
    >>> [r.normalized for r in interventions]
    ['TLIF', 'OLIF']
"""

import re
import logging
import threading
from typing import Optional
from dataclasses import dataclass, field
from rapidfuzz import fuzz, process

# Import configuration system
try:
    from ..core.config import get_normalization_config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    get_normalization_config = None

# Import SNOMED mappings (try relative first, then absolute)
try:
    from ..ontology.spine_snomed_mappings import (
        get_snomed_for_intervention,
        get_snomed_for_pathology,
        get_snomed_for_outcome,
        get_snomed_for_anatomy,
        SNOMEDMapping,
    )
    SNOMED_AVAILABLE = True
except ImportError:
    try:
        # Fallback to absolute import for PYTHONPATH-based usage
        from ontology.spine_snomed_mappings import (
            get_snomed_for_intervention,
            get_snomed_for_pathology,
            get_snomed_for_outcome,
            get_snomed_for_anatomy,
            SNOMEDMapping,
        )
        SNOMED_AVAILABLE = True
    except ImportError:
        SNOMED_AVAILABLE = False
        get_snomed_for_intervention = None
        get_snomed_for_pathology = None
        get_snomed_for_outcome = None
        get_snomed_for_anatomy = None
        SNOMEDMapping = None

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """정규화 결과.

    Attributes:
        original: 원본 텍스트
        normalized: 정규화된 이름
        confidence: 신뢰도 (0.0 ~ 1.0)
        matched_alias: 매칭된 별칭
        method: 매칭 방법 ("exact", "token", "fuzzy", "none")
        snomed_code: SNOMED-CT 코드 (있는 경우)
        snomed_term: SNOMED-CT 용어 (있는 경우)
        category: 수술법 카테고리 (Intervention인 경우)
        parent_code: SNOMED parent concept code for IS_A hierarchy
        semantic_type: SNOMED semantic type (procedure, disorder, etc.)
    """
    original: str
    normalized: str
    confidence: float = 1.0
    matched_alias: str = ""
    method: str = "none"  # "exact", "token", "fuzzy", "none"
    snomed_code: str = ""
    snomed_term: str = ""
    category: str = ""
    parent_code: str = ""
    semantic_type: str = ""


class EntityNormalizer:
    """척추 용어 정규화기.

    사용 예:
        normalizer = EntityNormalizer()
        result = normalizer.normalize_intervention("Biportal Endoscopic")
        # result.normalized == "UBE"
    """

    # 수술법 별칭 매핑 (정규화된 이름 → 별칭 목록)
    INTERVENTION_ALIASES = {
        # Endoscopic techniques
        "UBE": [
            "BESS", "Biportal", "Unilateral Biportal Endoscopic",
            "Biportal Endoscopic", "Biportal Endoscopy",
            "Unilateral Biportal Endoscopy", "BESS technique",
            "Biportal endoscopic lumbar decompression",
            "Biportal endoscopic decompression",
            "Biportal endoscopic spine surgery",
            "UBE decompression", "UBE surgery",
            "내시경 수술", "양측 내시경", "척추 내시경", "양문 내시경",
            # v1.14: BED는 UBE와 동일한 수술법
            "BED", "Biportal Endoscopic Discectomy",
            "Biportal endoscopic discectomy", "Biportal Discectomy",
            # v1.14.1: UBED, BE 변형 추가
            "UBED", "Unilateral Biportal Endoscopic Decompression",
            "BE", "Biportal Endoscopic Surgery",
        ],
        "BELIF": [
            "Biportal endoscopic lumbar interbody fusion",
            "Biportal endoscopic interbody fusion",
            "BE-LIF", "BELF",
            # v1.14: BE-TLIF는 BELIF와 동일한 수술법
            "BE-TLIF", "Biportal Endoscopic TLIF",
            "Biportal endoscopic transforaminal lumbar interbody fusion",
            "BE-transforaminal lumbar interbody fusion",
            # v1.14.1: Endo-TLIF, UBE-TLIF 변형 추가
            "Endo-TLIF", "UBE-TLIF", "Endoscopic TLIF",
        ],
        "FELD": [
            "FEID", "Full-Endoscopic Lumbar Discectomy",
            "Full Endoscopic Discectomy",
            "Full Endoscopic Lumbar Discectomy"
        ],
        "PELD": [
            "Percutaneous Endoscopic Lumbar Discectomy",
            "경피적 내시경", "PELD technique",
            # v1.25.0: PTED/Transforaminal moved to PETD (distinct procedure)
            "percutaneous endoscopic discectomy",
        ],
        "FESS": [
            "Full Endoscopic Spinal Surgery",
            "Full-Endoscopic Spinal Surgery"
        ],
        "PSLD": [
            "Percutaneous Stenoscopic Lumbar Decompression",
            "Stenoscopic Decompression"
        ],
        "MED": [
            "Microendoscopic Discectomy", "Microendoscopic Decompression",
            "미세 내시경", "MED technique",
            # v1.14.1: 소문자/변형 추가
            "microendoscopic discectomy", "Micro-endoscopic discectomy",
        ],
        "Microdecompression": [
            "Microscopic Decompression", "Micro Decompression",
            # v1.14.1: 소문자/변형 추가
            "microdecompression", "microscopic decompression",
            "Microscopic lumbar decompression",
        ],
        # v1.14.1: Endoscopic Decompression 신규 추가
        "Endoscopic Decompression": [
            "endoscopic decompression", "Endoscopic lumbar decompression",
            "endoscopic lumbar decompression", "Endoscopic spinal decompression",
            "Endoscopic spine decompression",
        ],

        # Fusion techniques - Interbody
        "TLIF": [
            "Transforaminal Lumbar Interbody Fusion",
            "Transforaminal Interbody Fusion", "TLIF surgery",
            "경추간공 유합술",
            # v1.14.1: 소문자/변형 추가
            "transforaminal lumbar interbody fusion", "Transforaminal fusion",
            "transforaminal fusion",
            # v1.25.0: alias expansion
            "open TLIF", "Open TLIF", "posterior lumbar interbody fusion",
            "unilateral TLIF",
        ],
        "MIS-TLIF": [
            "Minimally Invasive TLIF", "MIS TLIF",
            "Minimally Invasive Transforaminal Lumbar Interbody Fusion",
            # v1.14.1: 소문자/변형 추가
            "minimally invasive TLIF", "MI-TLIF", "Mini-TLIF",
        ],
        "PLIF": [
            "Posterior Lumbar Interbody Fusion",
            "Posterior Interbody Fusion",
            "후방 유합술",
            # v1.14.1: 소문자/변형 추가
            "posterior lumbar interbody fusion", "posterior interbody fusion",
        ],
        "ALIF": [
            "Anterior Lumbar Interbody Fusion",
            "Anterior Interbody Fusion",
            "전방 유합술",
            # v1.14.1: 소문자/변형 추가
            "anterior lumbar interbody fusion", "Anterior fusion",
            "anterior fusion", "Anterior approach fusion",
        ],
        "OLIF": [
            "Oblique Lumbar Interbody Fusion",
            "Oblique Interbody Fusion", "ATP approach",
            "OLIF51", "OLIF25",
            "측방 유합술",
            # v1.14.1: 소문자/변형 추가
            "oblique lumbar interbody fusion", "Oblique fusion",
            "oblique fusion", "Prepsoas approach",
        ],
        "LLIF": [
            "Lateral Lumbar Interbody Fusion",
            "Lateral Interbody Fusion", "XLIF", "DLIF",
            "Extreme Lateral Interbody Fusion",
            "Direct Lateral Interbody Fusion",
            "외측 유합술",
            # v1.14.1: 소문자/변형 추가
            "lateral lumbar interbody fusion", "Lateral fusion",
            "lateral fusion", "Transpsoas approach",
        ],
        "ACDF": [
            "Anterior Cervical Discectomy and Fusion",
            "Anterior Cervical Fusion",
            "전방 경추 유합술",
            # v1.14.1: 소문자/변형 추가
            "anterior cervical discectomy and fusion",
            "Anterior cervical fusion", "anterior cervical fusion",
        ],
        "MIDLF": [
            "Midline Lumbar Interbody Fusion",
            "Midline Interbody Fusion"
        ],

        # Fusion techniques - Posterolateral
        "Posterolateral Fusion": [
            "PLF", "Posterolateral Spinal Fusion",
            # v1.14.1: Generic fusion 변형 추가
            "Posterior fusion", "posterior fusion", "PSF",
            "Posterior spinal fusion", "posterior spinal fusion",
            "Posterior lumbar fusion", "posterior lumbar fusion",
        ],
        "Posterior Cervical Fusion": [
            "PCF", "Posterior Cervical Spinal Fusion"
        ],
        "CBT Fusion": [
            "Cortical Bone Trajectory Fusion",
            "CBT", "Cortical Bone Trajectory"
        ],
        "C1-C2 Fusion": [
            "C1-2 Fusion", "Atlantoaxial Fusion"
        ],
        "Occipitocervical Fusion": [
            "Occipito-cervical Fusion", "O-C2 Fusion"
        ],

        # General Fusion
        "Fusion Surgery": [
            "Spinal Fusion", "척추 유합술", "유합 수술", "유합술",
            # v1.14.1: Generic fusion 변형 추가
            "spinal fusion", "Lumbar fusion", "lumbar fusion",
            "Cervical fusion", "cervical fusion",
            "Thoracolumbar fusion", "Long segment fusion",
            # v1.14.11: 일반 용어 추가
            "spine surgery", "back surgery", "척추 수술",
        ],
        "Interbody Fusion": [
            "Interbody Spinal Fusion",
            # v1.14.1: 소문자 및 변형 추가
            "interbody fusion", "Interbody cage fusion",
            "interbody cage fusion", "Cage fusion",
        ],

        # Osteotomy
        "SPO": [
            "Smith-Petersen Osteotomy", "Ponte Osteotomy",
            "Smith Petersen Osteotomy",
            # v1.14.1: 소문자/변형 추가
            "SPO osteotomy", "Ponte", "ponte osteotomy",
            # v1.25.0: PCO merged into SPO (same procedure)
            "PCO", "Posterior Column Osteotomy",
            "posterior column osteotomy", "Chevron osteotomy",
        ],
        "PSO": [
            "Pedicle Subtraction Osteotomy",
            # v1.14.1: 소문자/변형 추가
            "PSO osteotomy", "pedicle subtraction osteotomy",
            "Pedicle subtraction", "3-column osteotomy",
        ],
        "VCR": [
            "Vertebral Column Resection",
            # v1.14.1: 소문자/변형 추가
            "VCR osteotomy", "vertebral column resection",
            "PVCR", "Posterior VCR",
        ],
        "COWO": [
            "Three-Column Osteotomy", "3-Column Osteotomy",
            "Three Column Osteotomy"
        ],
        # v1.14.1: Generic Osteotomy 추가
        "Osteotomy": [
            "osteotomy", "Spinal osteotomy", "spinal osteotomy",
            "Corrective osteotomy", "corrective osteotomy",
        ],

        # Open procedures
        "Laminectomy": [
            "Open Laminectomy", "Decompressive Laminectomy",
            "척추판 절제술", "후궁 절제술",
            # v1.14: 케이스 변형 및 추가 동의어
            "laminectomy", "decompressive laminectomy",
            "Lumbar laminectomy", "Cervical laminectomy",
        ],
        "Laminotomy": [
            "Hemilaminotomy", "Bilateral Laminotomy",
            "편측 후궁 절제술",
            # v1.14.1: 소문자 변형 추가
            "laminotomy", "hemilaminotomy", "bilateral laminotomy",
        ],
        "Foraminotomy": [
            "Foraminal Decompression",
            "추간공 확장술",
            # v1.14.1: 소문자 변형 추가
            "foraminotomy", "foraminal decompression",
            "Lumbar foraminotomy", "Cervical foraminotomy",
        ],
        # v1.14.1: Facetectomy 신규 추가
        "Facetectomy": [
            "facetectomy", "Partial facetectomy", "partial facetectomy",
            "Medial facetectomy", "Total facetectomy", "Facet resection",
        ],
        "UBD": [
            "Unilateral Bilateral Decompression",
            "Unilateral approach Bilateral Decompression"
        ],
        "Over-the-top Decompression": [
            "Over the top Decompression", "OTT Decompression"
        ],
        "Decompression Surgery": [
            "Decompression", "감압술", "신경 감압술", "Neural Decompression",
            # v1.14: 케이스 변형 및 추가 동의어
            "decompression", "neural decompression", "Neural decompression",
            "Spinal decompression", "spinal decompression",
            "Lumbar decompression", "Cervical decompression",
            # v1.14.11: 협착증 수술 용어 추가
            "stenosis surgery", "spinal stenosis surgery",
            "협착증 수술", "척추관 협착증 수술",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Non-instrumented decompression", "Posterior lumbar decompression",
            "Degenerative spine surgery",
        ],

        # Motion Preservation
        "ADR": [
            "Artificial Disc Replacement", "TDR",
            "Total Disc Replacement", "Disc Arthroplasty",
            # v1.25.0: "TDR (Simplify Cervical Disc)" moved to CDR (cervical device)
            "lTDR", "Lumbar disc replacement", "Lumbar TDR",
        ],
        "Dynamic Stabilization": [
            "Dynamic Spinal Stabilization"
        ],
        "Interspinous Device": [
            "Interspinous Process Device", "IPD",
            "Interspinous Spacer"
        ],

        # Fixation
        "Pedicle Screw": [
            "Pedicle Screw Fixation", "PS Fixation"
        ],
        "Lateral Mass Screw": [
            "Lateral Mass Screw Fixation", "LMS Fixation"
        ],

        # Vertebroplasty/Kyphoplasty
        "PVP": [
            "Percutaneous Vertebroplasty", "Vertebroplasty",
            "Percutaneous cement augmentation", "Cement augmentation"
        ],
        "PKP": [
            "Percutaneous Kyphoplasty", "Kyphoplasty",
            "Balloon Kyphoplasty"
        ],
        "Vertebral Augmentation": [
            "Vertebral Cement Augmentation"
        ],
        "Sacroplasty": [
            "Sacral augmentation", "Sacral vertebroplasty"
        ],

        # Decompression (additional)
        "Discectomy": [
            "Total discectomy", "Partial discectomy", "Microdiscectomy",
            "Microscopic discectomy",
            # v1.14.1: 소문자/변형 추가
            "discectomy", "microdiscectomy", "MD",
            "Lumbar discectomy", "lumbar discectomy",
            "Endoscopic discectomy", "endoscopic discectomy",
            # v1.14.11: 일반 용어 추가
            "disk surgery", "disc surgery", "디스크 수술",
            "disc herniation surgery", "disk herniation surgery",
            "herniated disc surgery", "herniated disk surgery",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "sequestrectomy", "Sequestrectomy",
        ],
        "Corpectomy": [
            "Anterior corpectomy", "Cervical corpectomy", "Lumbar corpectomy"
        ],
        "Debridement": [
            "Surgical debridement", "Spinal debridement",
            "Minimally invasive microscopic debridement"
        ],

        # Posterolateral Fusion (additional)
        "Posterior Instrumented Fusion": [
            "Posterior instrumented fusion", "PIF",
            "Instrumented posterior fusion"
        ],

        # Conservative Treatment
        "Conservative Management": [
            "Conservative treatment", "Non-surgical treatment",
            "Conservative management", "Non-operative treatment"
        ],
        "Bisphosphonate": [
            "Bisphosphonate treatment", "Bisphosphonate therapy",
            "Alendronate", "Zoledronic acid"
        ],
        "Teriparatide": [
            "Teriparatide treatment", "PTH therapy", "Forteo"
        ],
        "Denosumab": [
            "Denosumab treatment", "Prolia"
        ],
        "SERM": [
            "SERM treatment", "Selective estrogen receptor modulator",
            "Raloxifene"
        ],

        # Diagnostic
        "MRI": [
            "Magnetic resonance imaging", "MR imaging"
        ],
        "CT": [
            "Computed tomography", "CT scan"
        ],
        "Bone Scintigraphy": [
            "Bone scintigraphy (Tc-99m MDP)", "Bone scan",
            "Tc-99m bone scan", "Skeletal scintigraphy"
        ],
        "X-ray": [
            "Radiography", "radiography", "X-ray imaging",
            "Plain radiograph", "Plain radiography", "Spine X-ray",
            "Plain film", "Conventional radiograph"
        ],

        # Other Surgical
        "Drainage": [
            "Surgical drainage", "Abscess drainage"
        ],
        "Hip Fracture Surgery": [
            "Hip fracture surgery", "Hip fracture fixation"
        ],
        "Cage Insertion": [
            "Large PEEK cage insertion", "PEEK cage insertion",
            "3D-printed titanium cage", "Titanium cage insertion",
            "Posterior lumbar interbody fusion with window-type 3D-printed titanium cage",
            "Posterior lumbar interbody fusion with non-window-type 3D-printed titanium cage",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "PEEK cage", "Stand-alone cage", "Standalone cage",
            "Stand-alone PEEK cage", "Cage implantation",
        ],

        # ========================================
        # Navigation & Robotics
        # ========================================
        "Robot-Assisted Surgery": [
            "Robotic surgery", "Robotic-assisted", "Robot-assisted spine surgery",
            "ROSA robot", "Mazor robot", "ExcelsiusGPS", "로봇 수술",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Robot-assisted pedicle screw placement",
            "Robotic-assisted pedicle screw placement",
            "Robot-guided pedicle screw placement",
            "Robotic pedicle screw", "Mazor X Stealth Edition",
        ],
        "Navigation-Guided Surgery": [
            "Navigation surgery", "CT navigation", "O-arm navigation",
            "O-arm guided", "Intraoperative CT", "Fluoroscopy-guided",
            "Computer-assisted surgery", "CAS", "Image-guided surgery"
        ],

        # ========================================
        # Cervical-Specific Procedures
        # ========================================
        "CDR": [
            "Cervical Disc Replacement", "Cervical ADR",
            "Cervical Artificial Disc", "Cervical TDR",
            "경추 인공디스크",
            # v1.25.0: cervical-specific aliases consolidated here
            "cTDR", "cADR", "TDR (Simplify Cervical Disc)",
        ],
        "Laminoplasty": [
            "Cervical Laminoplasty", "Open-door laminoplasty",
            "French-door laminoplasty", "Double-door laminoplasty",
            "Hirabayashi laminoplasty", "추궁성형술"
        ],
        "Posterior Cervical Foraminotomy": [
            "PCF", "Cervical foraminotomy", "Keyhole foraminotomy",
            "Posterior cervical decompression"
        ],
        "CCF": [
            "Cervical Corpectomy and Fusion", "Anterior cervical corpectomy",
            "Cervical corpectomy fusion",
            # v1.14.3: ACCF 별칭 추가
            "ACCF", "Anterior Cervical Corpectomy and Fusion",
            "Anterior cervical corpectomy and fusion",
        ],

        # ========================================
        # Revision Procedures
        # ========================================
        "Revision Surgery": [
            "Revision fusion", "Revision spine surgery", "Redo surgery",
            "Re-operation", "재수술"
        ],
        "Pseudarthrosis Repair": [
            "Nonunion repair", "Pseudarthrosis revision",
            "Failed fusion revision"
        ],
        "Hardware Removal": [
            "Implant removal", "Screw removal", "Rod removal",
            "Instrumentation removal"
        ],
        "Adjacent Segment Surgery": [
            "Adjacent segment fusion", "Adjacent level surgery",
            "Proximal junction surgery", "Distal junction surgery"
        ],

        # ========================================
        # Tumor-Specific Procedures
        # ========================================
        "En Bloc Resection": [
            "En bloc spondylectomy", "Total en bloc spondylectomy",
            "TES", "Marginal resection"
        ],
        "Vertebrectomy": [
            "Total vertebrectomy", "Partial vertebrectomy",
            "Spondylectomy"
        ],
        "Tumor Debulking": [
            "Intralesional resection", "Subtotal resection",
            "Tumor decompression"
        ],
        "Separation Surgery": [
            "Tumor separation surgery", "Circumferential decompression"
        ],

        # ========================================
        # Injection & Pain Management
        # ========================================
        "ESI": [
            "Epidural Steroid Injection", "Epidural injection",
            "Transforaminal epidural", "TFESI", "Interlaminar epidural",
            "Caudal epidural", "경막외 주사"
        ],
        "Facet Injection": [
            "Facet joint injection", "Facet block",
            "Medial branch block", "MBB", "후관절 주사"
        ],
        "RFA": [
            "Radiofrequency Ablation", "Radiofrequency neurotomy",
            "Facet rhizotomy", "Medial branch ablation",
            "고주파 열응고술"
        ],
        "SCS": [
            "Spinal Cord Stimulation", "Spinal cord stimulator",
            "Dorsal column stimulation", "척수 자극술"
        ],
        "Intrathecal Pump": [
            "ITB pump", "Intrathecal baclofen", "Intrathecal drug delivery",
            "Morphine pump"
        ],
        "Nerve Block": [
            "Selective nerve root block", "SNRB", "Root block",
            "신경 차단술"
        ],
        "Trigger Point Injection": [
            "TPI", "Muscle injection", "근육 주사"
        ],
        "PRP Injection": [
            "Platelet-rich plasma", "PRP therapy", "자가혈소판 치료"
        ],

        # ========================================
        # Minimally Invasive (Expanded)
        # ========================================
        "Tubular Discectomy": [
            "Tubular microdiscectomy", "Tubular decompression",
            "METRx discectomy"
        ],
        "Percutaneous Pedicle Screw": [
            "Percutaneous fixation", "Percutaneous instrumentation",
            "Minimally invasive fixation", "경피적 척추경 나사",
            # v1.14.1: 변형 추가
            "Percutaneous pedicle screw fixation",
            "percutaneous pedicle screw fixation",
            "Percutaneous screw", "PPS fixation",
        ],
        "MIS-OLIF": [
            "Minimally Invasive OLIF", "MIS oblique fusion"
        ],
        "MIS-LLIF": [
            "Minimally Invasive LLIF", "MIS lateral fusion",
            "Mini-open lateral"
        ],

        # ========================================
        # Deformity-Specific
        # ========================================
        "Anterior Release": [
            "Anterior spinal release", "Anterior discectomy",
            "전방 유리술"
        ],
        "MAGEC Rod": [
            "Magnetically controlled growing rod", "Growing rod",
            "MCGR", "성장봉"
        ],
        "Halo Traction": [
            "Halo-gravity traction", "Skull traction", "Halo vest",
            "Halo fixation"
        ],

        # ========================================
        # Infection-Specific
        # ========================================
        "I&D": [
            "Irrigation and Debridement", "Washout",
            "Surgical irrigation"
        ],
        "Antibiotic Spacer": [
            "Cement spacer", "PMMA spacer with antibiotics"
        ],
        "Staged Reconstruction": [
            "Two-stage reconstruction", "Staged fusion",
            "Delayed reconstruction"
        ],

        # ========================================
        # v1.16.1: Schema 노드 alias 추가 (26개)
        # ========================================
        # Radiotherapy variants
        "Radiotherapy": [
            "Radiation therapy", "Radiation treatment", "RT",
            "Spine radiation", "방사선 치료",
        ],
        "SABR": [
            "Stereotactic Ablative Body Radiotherapy",
            "Stereotactic ablative radiotherapy",
        ],
        "SBRT": [
            "Stereotactic Body Radiation Therapy",
            "Stereotactic body radiotherapy",
        ],
        "Spine Radiation Therapy": [
            "Spinal radiation", "Spinal irradiation",
        ],
        # Conservative
        "Bracing": [
            "Brace", "Spinal brace", "Orthosis", "TLSO",
            "Thoracolumbosacral orthosis", "보조기",
        ],
        "Physical therapy": [
            "Physical Therapy", "PT", "Physiotherapy",
            "물리치료", "재활치료", "Rehabilitation",
        ],
        "Antibiotic therapy": [
            "Antibiotic treatment", "IV antibiotics",
            "Antimicrobial therapy", "항생제 치료",
        ],
        # Specialized fusion
        "Anterior fusion": [
            "Anterior spinal fusion", "ASF",
        ],
        "Lumbar Fusion": [
            "Lumbar spinal fusion", "요추 유합술",
        ],
        "PTF": [
            "Posterior Thoracic Fusion",
            "Posterior thoracic spinal fusion",
        ],
        "Spinopelvic fusion": [
            "Spinopelvic fixation", "Lumbopelvic fixation",
            "Iliac fixation", "골반 고정술",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Sacropelvic fusion", "Sacropelvic fixation",
        ],
        "Craniocervical Junction Surgery": [
            "Craniocervical surgery", "CVJ surgery",
            "Craniovertebral junction surgery",
        ],
        "Craniocervical stabilization": [
            "Craniocervical fixation", "CVJ stabilization",
        ],
        # Fixation variants
        "Posterior C1-C2 screw fixation": [
            "C1-C2 screw fixation", "Harms technique",
            "C1 lateral mass C2 pedicle screw",
        ],
        "S2AI screw fixation": [
            "S2AI", "S2-alar-iliac screw", "S2 alar iliac",
            "S2AI screw",
        ],
        "Iliac screw fixation": [
            "Iliac screw", "Iliac bolt", "Iliac fixation",
        ],
        # Minimally invasive
        "BE-ULBD": [
            "Biportal Endoscopic ULBD",
            "Biportal endoscopic unilateral laminotomy bilateral decompression",
        ],
        # Other procedures
        "Intradiscal injection": [
            "Intradiscal steroid injection", "Disc injection",
            "추간판 내 주사",
        ],
        "Neuromodulation": [
            "Spinal cord neuromodulation", "신경조절술",
        ],
        "Spinal Injection Therapy": [
            "Spinal injection", "척추 주사 치료",
        ],
        "Spinal Tumor Surgery": [
            "Spine tumor surgery", "Spinal tumor resection",
            "척추 종양 수술",
        ],
        "Transnasal odontoidectomy": [
            "Transnasal odontoid resection", "Endoscopic odontoidectomy",
        ],
        "Transoral Approach": [
            "Transoral surgery", "Transoral decompression",
        ],
        "Transoral odontoidectomy": [
            "Transoral odontoid resection",
        ],
        "Open Decompression": [
            "Open decompression", "Open neural decompression",
            "Open spinal decompression", "개방 감압술",
        ],
        "Endoscopic Surgery": [
            "Endoscopic spine surgery", "Endoscopic procedure",
            "내시경 척추 수술",
        ],
        "Microscopic Surgery": [
            "Microsurgery", "Microscopic technique",
            "미세현미경 수술",
        ],
        "Fixation": [
            "Spinal fixation", "Spinal instrumentation",
            "Internal fixation", "척추 고정술",
        ],
        "Motion Preservation": [
            "Motion preservation surgery", "Non-fusion surgery",
            "Dynamic surgery", "운동 보존 수술",
        ],

        # ========================================
        # v1.20.2: Additional Intervention Aliases (coverage expansion)
        # ========================================

        # Spine surgery general terms
        "Spine Surgery": [
            "Spinal surgery", "spinal surgery", "Back surgery",
            "Spine operation", "척추 수술",
        ],

        # MIS general
        "Minimally Invasive Surgery": [
            "MIS", "Minimally invasive spine surgery", "MISS",
            "Minimally invasive procedure", "최소침습 수술",
            "minimally invasive surgery",
        ],

        # Standalone procedures often seen
        "Hemilaminectomy": [
            "hemilaminectomy", "Hemi-laminectomy",
            "Unilateral laminectomy", "편측 후궁 절제",
        ],
        "Posterior Decompression": [
            "posterior decompression", "Posterior spinal decompression",
            "후방 감압술",
        ],
        "Anterior Decompression": [
            "anterior decompression", "Anterior spinal decompression",
            "전방 감압술",
        ],
        "Circumferential Fusion": [
            "circumferential fusion", "360 fusion",
            "Combined anterior-posterior fusion",
            "360-degree fusion", "전후방 동시 유합술",
        ],
        # v1.25.0: PCO/Posterior Column Osteotomy merged into SPO (same procedure)
        "Asymmetric PSO": [
            "asymmetric PSO", "Asymmetric pedicle subtraction osteotomy",
        ],

        # Bone graft
        "Bone Graft": [
            "bone graft", "Autograft", "Allograft",
            "Bone grafting", "자가골 이식", "동종골 이식",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Bone graft",
        ],
        "BMP": [
            "Bone Morphogenetic Protein", "rhBMP-2", "BMP-2",
            "Infuse", "bone morphogenetic protein",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "rhBMP-2 augmentation", "E.BMP-2 augmentation",
            "BMP augmentation", "BMP-2 augmentation",
        ],
        "DBM": [
            "Demineralized Bone Matrix", "demineralized bone matrix",
        ],

        # Cement / Augmentation
        "Cement Augmented Screw": [
            "Cement augmented pedicle screw",
            "PMMA augmented screw", "Fenestrated screw",
            "시멘트 보강 나사",
        ],

        # Rehabilitation
        "Rehabilitation": [
            "rehabilitation", "Postoperative rehabilitation",
            "Spine rehabilitation", "재활",
        ],
        "Exercise Therapy": [
            "exercise therapy", "Therapeutic exercise",
            "Core strengthening", "Stabilization exercise",
            "운동 치료",
        ],

        # Interventional pain
        "Prolotherapy": [
            "prolotherapy", "Dextrose prolotherapy",
            "프롤로 치료",
        ],
        "Percutaneous Disc Decompression": [
            "percutaneous disc decompression",
            "Nucleoplasty", "Disc-FX", "IDET",
            "Intradiscal electrothermal therapy",
        ],
        "Endoscopic Foraminotomy": [
            "endoscopic foraminotomy",
            "Percutaneous endoscopic foraminotomy",
            "Full-endoscopic foraminotomy",
        ],

        # Monitoring
        "Intraoperative Neuromonitoring": [
            "IONM", "IOM", "Neuromonitoring",
            "Intraoperative monitoring", "수술중 신경 모니터링",
            "Electrophysiological monitoring",
        ],

        # Blood management
        "Cell Saver": [
            "cell saver", "Intraoperative cell salvage",
            "Autologous blood transfusion",
        ],
        "TXA": [
            "Tranexamic acid", "tranexamic acid",
            "TXA administration",
        ],

        # Emerging techniques
        "Endoscopic ACDF": [
            "endoscopic ACDF", "Endoscopic anterior cervical discectomy",
        ],
        "Oblique Corpectomy": [
            "oblique corpectomy", "Oblique lateral corpectomy",
        ],
        "Lateral Corpectomy": [
            "lateral corpectomy", "Mini-open corpectomy",
        ],

        # Wound management
        "Wound VAC": [
            "wound VAC", "Vacuum-assisted closure",
            "Negative pressure wound therapy", "NPWT",
        ],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync + Alias Expansion
        # ========================================

        # Endoscopic variants (SNOMED orphans)
        "PEID": [
            "Percutaneous Endoscopic Interlaminar Discectomy",
            "Interlaminar endoscopic discectomy",
            "Percutaneous endoscopic interlaminar approach",
        ],
        "PETD": [
            "Percutaneous Endoscopic Transforaminal Discectomy",
            "Transforaminal endoscopic discectomy", "TED",
            "Percutaneous endoscopic transforaminal approach",
            # v1.25.0: moved from PELD (distinct transforaminal procedure)
            "PTED", "Transforaminal PELD", "TF-PELD technique",
            "TF-PELD",
        ],
        "LE-ULBD": [
            "Lateral Endoscopic ULBD",
            "Lateral endoscopic unilateral laminotomy bilateral decompression",
        ],
        "LAMP": [
            "Laminectomy with medial facetectomy and pedicular decompression",
            "추궁절제 및 내측 관절돌기 절제술",
        ],

        # Bone graft specifics (SNOMED orphans)
        "rhBMP-2": [
            "rhBMP-2 augmentation", "BMP-2", "BMP-2 grafting",
            "rh-BMP2", "BMP augmentation", "E.BMP-2",
            "rhBMP-2/ACS", "rhBMP-2 with HA",
            "재조합 인간 골형성 단백질-2 적용",
        ],
        "Allograft bone grafting": [
            "allograft", "Structural femoral allograft",
            "bone allograft", "동종골 이식술",
        ],
        "Autograft bone grafting": [
            "autograft", "Autogenous bone graft",
            "Local autograft", "auto-iliac bone graft",
            "Bone marrow aspirate", "자가골 이식술",
        ],
        "Bone graft augmentation": [
            "Bone marrow aspirate concentrate", "BMAC",
            "골 이식 보강술",
        ],
        "Demineralized bone matrix": [
            "탈회골기질",
        ],

        # Instrumentation specifics (SNOMED orphans)
        "Pedicle screw instrumentation": [
            "Pedicle screw insertion",
            "Bilateral pedicle screw instrumentation",
            "Unilateral pedicle screw instrumentation",
            "pedicle screw and rod instrumentation",
            "척추경 나사못 기기 고정술",
        ],
        "Interbody cage implantation": [
            "cage implantation", "Interbody cage placement",
            "Interbody spacer", "PEEK interbody cage",
            "Expandable cage", "intervertebral cage",
            "추체간 케이지 삽입술",
        ],

        # Repair / Reconstruction (SNOMED orphans)
        "Dural repair": [
            "Dural closure", "Dural suture", "Duraplasty",
            "경막 수복술",
        ],
        "Posterior stabilization": [
            "Posterior instrumentation", "Posterior wiring",
            "후방 안정화술",
        ],
        "Laminar reconstruction": [
            "Laminoplasty reconstruction",
            "PEEK artificial lamina reconstruction",
            "추궁판 재건술",
        ],

        # Decompression variants (SNOMED orphans)
        "Minimally Invasive Decompression": [
            "MIS decompression", "Tubular retractor-based surgery",
            "최소 침습 감압술",
        ],
        "Flavectomy": [
            "Ligamentum flavum resection",
            "Ligamentum flavum removal",
            "Yellow ligament excision",
            "황색인대 절제술",
        ],
        "Bilateral facetectomy": [
            "bilateral facetectomy", "Bilateral facet resection",
        ],

        # Fixation variants (SNOMED orphans)
        "Pelvic fixation": [
            "Iliac fixation", "Spinopelvic fixation",
        ],
        "Dynamic rod fixation": [
            "Dynamic stabilization rod", "dynamic rod",
        ],
        "Rigid rod fixation": [
            "rigid rod fixation", "Standard rod fixation",
        ],
        "Plate fixation": [
            "plate fixation", "Spinal plate fixation",
            "Anterior plate",
        ],
        "Posterior fixation": [
            "posterior fixation", "Posterior fixation with pedicle screws",
        ],
        "Percutaneous posterior fixation": [
            "percutaneous posterior fixation",
            "Percutaneous instrumented fusion",
        ],
        "Navigation-guided fixation": [
            "navigation-guided fixation",
            "CT-guided fixation",
        ],
        "Anterior fixation": [
            "anterior fixation", "Anterior titanium plate fixation",
        ],
        "Transpedicular fixation": [
            "transpedicular fixation",
            "Transpedicular screw fixation",
        ],
        "Robot-assisted fixation": [
            "robot-assisted fixation",
            "Robot-assisted transfacet screw fixation",
        ],
        "Internal fixation": [
            "internal fixation", "Hybrid internal fixation",
        ],
        "Lateral plate fixation": [
            "lateral plate fixation", "Lateral cervical plate",
        ],
        "Translaminar facet screw fixation": [
            "translaminar facet screw",
            "Translaminar screw fixation",
        ],
        "TT fixation": [
            "Traditional trajectory", "Traditional trajectory fixation",
        ],
        "CBT fixation": [
            "Cortical bone trajectory fixation",
            "CBT screw fixation",
        ],
        "Hybrid CBT-TT fixation": [
            "hybrid CBT-TT fixation",
            "Combined CBT-TT screw fixation",
        ],

        # v1.25.0: PCO merged into SPO (see SPO entry above)
        "Facet joint osteotomy": [
            "facet joint osteotomy", "Facet osteotomy",
        ],
        "Posterior osteotomy": [
            "posterior osteotomy", "Posterior spinal osteotomy",
        ],
        "Transoral osteotomy": [
            "transoral osteotomy",
        ],

        # Fusion variants (SNOMED orphans)
        "C1/2 posterior fusion": [
            "C1-2 posterior fusion", "Atlantoaxial posterior fusion",
        ],
        "CDA": [
            "Cervical Disc Arthroplasty", "cervical disc arthroplasty",
        ],

        # Trauma (SNOMED orphans)
        "Closed reduction": [
            "Closed fracture reduction", "Manual reduction",
            "비관혈적 정복술",
        ],
        "Open reduction": [
            "Open fracture reduction", "ORIF",
            "관혈적 정복술",
        ],

        # Other (SNOMED orphans)
        "Stereotactic Navigation": [
            "Stereotactic surgery", "Stereotactic guidance",
        ],
        "Robot-assisted spine surgery": [
            "robot-assisted spine surgery",
        ],
        "Navigation-guided spine surgery": [
            "navigation-guided spine surgery",
        ],
        "Bariatric Surgery": [
            "Weight loss surgery", "Obesity surgery",
            "Sleeve gastrectomy", "RYGB", "비만 수술",
        ],
        "Injection Therapy": [
            "injection therapy", "Spinal injection",
        ],
        "Vertebral Biopsy": [
            "vertebral biopsy", "Spine biopsy",
            "CT-guided biopsy", "척추 생검",
        ],
        "Zoledronate": [
            "Zoledronic acid", "zoledronate",
            "졸레드론산",
        ],

        # ========================================
        # v1.25.0: New SNOMED Concept Aliases (Gap C)
        # ========================================
        "Expandable Cage": [
            "expandable cage", "Expandable interbody cage",
            "Expandable interbody spacer", "Articulating expandable cage",
            "확장형 케이지",
        ],
        "Zero-Profile Device": [
            "zero-profile device", "Zero-profile cage",
            "Stand-alone anterior cage", "Zero-P device",
            "제로 프로파일 디바이스",
        ],
        "Endoscopic OLIF": [
            "endoscopic OLIF", "Endo-OLIF",
            "Full-endoscopic OLIF",
            "내시경 사측방 유합술",
        ],
        "Robot-Assisted UBE": [
            "robot-assisted UBE", "RA-UBE", "Robotic UBE",
            "Robot-assisted biportal endoscopy",
            "로봇 보조 양측 내시경",
        ],
        "AR-Guided Surgery": [
            "AR-guided surgery", "AR navigation",
            "Augmented reality navigation",
            "AR-guided pedicle screw placement",
            "증강현실 가이드 수술",
        ],
        "Romosozumab": [
            "romosozumab", "Evenity",
            "Anti-sclerostin antibody", "Romosozumab treatment",
            "로모소주맙",
        ],
        "Abaloparatide": [
            "abaloparatide", "Tymlos",
            "PTHrP analog", "Abaloparatide treatment",
            "아발로파라타이드",
        ],
        "Standalone Cage": [
            "standalone cage", "Stand-alone cage",
            "Cage-only fusion", "Stand-alone PEEK cage",
            "Standalone ALIF cage", "단독 케이지",
        ],
        "3D-Printed Implant": [
            "3D-printed implant", "3D-printed titanium cage",
            "3D-printed cage", "Custom 3D implant",
            "Additive manufactured cage",
            "3D 프린팅 임플란트",
        ],
        "Endoscopic Posterior Fusion": [
            "endoscopic posterior fusion", "Endo-PLIF",
            "Endoscopic PLIF", "Full-endoscopic posterior fusion",
            "내시경 후방 유합술",
        ],
        "Percutaneous Cement Discoplasty": [
            "percutaneous cement discoplasty", "PCD",
            "Cement discoplasty", "PMMA discoplasty",
            "경피적 시멘트 추간판 성형술",
        ],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync (QC-2026-008) — Intervention
        # ========================================
        "AI-Assisted Procedure": [
            "AI-assisted procedure", "AI-assisted surgery",
            "AI-guided procedure",
        ],
        "AI-based Cobb Angle Measurement": [
            "AI-based cobb angle measurement", "AI Cobb angle",
        ],
        "Artificial Intelligence": [
            "artificial intelligence", "AI", "AI application",
        ],
        "Automated Spinopelvic Parameter Measurement": [
            "automated spinopelvic parameter measurement",
            "automated spinopelvic measurement",
        ],
        "Bone Resection": [
            "bone resection", "Bony resection",
            "Vertebral resection",
        ],
        "Cobb Angle Measurement": [
            "cobb angle measurement", "Cobb angle",
            "Cobb measurement",
        ],
        "Convolutional Neural Network": [
            "convolutional neural network", "CNN",
        ],
        "Deep Learning": [
            "deep learning", "DL", "Deep learning model",
        ],
        "Deep Learning Landmark Detection": [
            "deep learning landmark detection",
            "DL landmark detection",
        ],
        "Deep Learning Segmentation": [
            "deep learning segmentation", "DL segmentation",
            "Automated segmentation",
        ],
        "Keypoint Detection Model": [
            "keypoint detection model", "Keypoint detection",
        ],
        "Open Spine Surgery": [
            "open spine surgery", "Open surgery",
            "Open spinal surgery", "개방 척추 수술",
        ],
        "Sagittal Correction": [
            "sagittal correction", "Sagittal realignment",
            "Sagittal balance correction",
        ],
        "ULIF": [
            "Unilateral Lumbar Interbody Fusion",
            "unilateral lumbar interbody fusion",
        ],
        # Note: These SNOMED keys are already reachable as aliases of other canonicals
        # (no need for separate canonical entries — would cause last-write-wins conflicts):
        # "Posterior Column Osteotomy" → alias of SPO
    }

    # 수술법 카테고리 매핑 (정규화된 이름 → 카테고리)
    # Taxonomy hierarchy와 일치하도록 설정
    INTERVENTION_CATEGORIES = {
        # Endoscopic Surgery
        "UBE": "Endoscopic Surgery",
        "BELIF": "Endoscopic Surgery",
        "FELD": "Endoscopic Surgery",
        "PELD": "Endoscopic Surgery",
        "FESS": "Endoscopic Surgery",
        "PSLD": "Endoscopic Surgery",
        "MED": "Microscopic Surgery",
        # Interbody Fusion
        "TLIF": "Interbody Fusion",
        "MIS-TLIF": "Interbody Fusion",
        "PLIF": "Interbody Fusion",
        "ALIF": "Interbody Fusion",
        "OLIF": "Interbody Fusion",
        "LLIF": "Interbody Fusion",
        "ACDF": "Interbody Fusion",
        "MIDLF": "Interbody Fusion",
        # Posterolateral Fusion
        "Posterolateral Fusion": "Posterolateral Fusion",
        "Posterior Cervical Fusion": "Posterolateral Fusion",
        "Posterior Instrumented Fusion": "Posterolateral Fusion",
        "CBT Fusion": "Posterolateral Fusion",
        "C1-C2 Fusion": "Posterolateral Fusion",
        "Occipitocervical Fusion": "Posterolateral Fusion",
        # General Fusion
        "Fusion Surgery": "Fusion Surgery",
        "Interbody Fusion": "Interbody Fusion",
        # Osteotomy
        "SPO": "Osteotomy",
        "PSO": "Osteotomy",
        "VCR": "Osteotomy",
        "COWO": "Osteotomy",
        # Decompression Surgery
        "Laminectomy": "Decompression Surgery",
        "Laminotomy": "Decompression Surgery",
        "Foraminotomy": "Decompression Surgery",
        "UBD": "Decompression Surgery",
        "Over-the-top Decompression": "Decompression Surgery",
        "Decompression Surgery": "Decompression Surgery",
        "Microdecompression": "Decompression Surgery",
        "Discectomy": "Decompression Surgery",
        "Corpectomy": "Decompression Surgery",
        "Debridement": "Decompression Surgery",
        # Motion Preservation
        "ADR": "Motion Preservation",
        "Dynamic Stabilization": "Motion Preservation",
        "Interspinous Device": "Motion Preservation",
        # Fixation
        "Pedicle Screw": "Fixation",
        "Lateral Mass Screw": "Fixation",
        # Vertebral Augmentation
        "PVP": "Vertebral Augmentation",
        "PKP": "Vertebral Augmentation",
        "Vertebral Augmentation": "Vertebral Augmentation",
        "Sacroplasty": "Vertebral Augmentation",
        # Conservative Treatment (non-surgical)
        "Conservative Management": "Conservative Treatment",
        "Bisphosphonate": "Conservative Treatment",
        "Teriparatide": "Conservative Treatment",
        "Denosumab": "Conservative Treatment",
        "SERM": "Conservative Treatment",
        # Diagnostic
        "MRI": "Diagnostic",
        "CT": "Diagnostic",
        "Bone Scintigraphy": "Diagnostic",
        "X-ray": "Diagnostic",
        # Other Surgical
        "Drainage": "Other Surgical",
        "Hip Fracture Surgery": "Other Surgical",
        "Cage Insertion": "Other Surgical",
        # Navigation & Robotics
        "Robot-Assisted Surgery": "Navigation/Robotics",
        "Navigation-Guided Surgery": "Navigation/Robotics",
        # Cervical Surgery
        "CDR": "Motion Preservation",
        "Laminoplasty": "Decompression Surgery",
        "Posterior Cervical Foraminotomy": "Decompression Surgery",
        "CCF": "Interbody Fusion",
        # Revision Surgery
        "Revision Surgery": "Revision Surgery",
        "Pseudarthrosis Repair": "Revision Surgery",
        "Hardware Removal": "Revision Surgery",
        "Adjacent Segment Surgery": "Revision Surgery",
        # Tumor Surgery
        "En Bloc Resection": "Tumor Surgery",
        "Vertebrectomy": "Tumor Surgery",
        "Tumor Debulking": "Tumor Surgery",
        "Separation Surgery": "Tumor Surgery",
        # Injection & Pain Management
        "ESI": "Injection Therapy",
        "Facet Injection": "Injection Therapy",
        "RFA": "Injection Therapy",
        "SCS": "Injection Therapy",
        "Intrathecal Pump": "Injection Therapy",
        "Nerve Block": "Injection Therapy",
        "Trigger Point Injection": "Injection Therapy",
        "PRP Injection": "Injection Therapy",
        # Minimally Invasive (additional)
        "Tubular Discectomy": "Endoscopic Surgery",
        "Percutaneous Pedicle Screw": "Fixation",
        "MIS-OLIF": "Interbody Fusion",
        "MIS-LLIF": "Interbody Fusion",
        # Deformity-Specific
        "Anterior Release": "Osteotomy",
        "MAGEC Rod": "Fixation",
        "Halo Traction": "Fixation",
        # Infection-Specific
        "I&D": "Infection Surgery",
        "Antibiotic Spacer": "Infection Surgery",
        "Staged Reconstruction": "Infection Surgery",
        # v1.14.1: 신규 추가
        "Endoscopic Decompression": "Endoscopic Surgery",
        "Facetectomy": "Decompression Surgery",
        "Osteotomy": "Osteotomy",
        # v1.16.2: Category aliases
        "Open Decompression": "Decompression Surgery",
        "Endoscopic Surgery": "Endoscopic Surgery",
        "Microscopic Surgery": "Decompression Surgery",
        "Fixation": "Fixation",
        "Motion Preservation": "Motion Preservation",
        # v1.16.4: 누락 카테고리 24건 추가
        "Anterior fusion": "Interbody Fusion",
        "Lumbar Fusion": "Fusion Surgery",
        "PTF": "Posterolateral Fusion",
        "Spinopelvic fusion": "Fixation",
        "BE-ULBD": "Endoscopic Surgery",
        "Bracing": "Conservative Treatment",
        "Physical therapy": "Conservative Treatment",
        "Antibiotic therapy": "Conservative Treatment",
        "Neuromodulation": "Injection Therapy",
        "Intradiscal injection": "Injection Therapy",
        "Spinal Injection Therapy": "Injection Therapy",
        "Radiotherapy": "Tumor Surgery",
        "SABR": "Tumor Surgery",
        "SBRT": "Tumor Surgery",
        "Spine Radiation Therapy": "Tumor Surgery",
        "Spinal Tumor Surgery": "Tumor Surgery",
        "Craniocervical Junction Surgery": "Decompression Surgery",
        "Craniocervical stabilization": "Fixation",
        "Posterior C1-C2 screw fixation": "Fixation",
        "Iliac screw fixation": "Fixation",
        "S2AI screw fixation": "Fixation",
        "Transnasal odontoidectomy": "Decompression Surgery",
        "Transoral Approach": "Decompression Surgery",
        "Transoral odontoidectomy": "Decompression Surgery",
        # v1.20.2: New intervention categories
        # "Spine Surgery" intentionally omitted — it is the taxonomy root with no parent
        "Minimally Invasive Surgery": "Endoscopic Surgery",
        "Hemilaminectomy": "Decompression Surgery",
        "Posterior Decompression": "Decompression Surgery",
        "Anterior Decompression": "Decompression Surgery",
        "Circumferential Fusion": "Fusion Surgery",
        "Posterior Column Osteotomy": "Osteotomy",
        "Asymmetric PSO": "Osteotomy",
        "Bone Graft": "Other Surgical",
        "BMP": "Other Surgical",
        "DBM": "Other Surgical",
        "Cement Augmented Screw": "Fixation",
        "Rehabilitation": "Conservative Treatment",
        "Exercise Therapy": "Conservative Treatment",
        "Prolotherapy": "Injection Therapy",
        "Percutaneous Disc Decompression": "Injection Therapy",
        "Endoscopic Foraminotomy": "Endoscopic Surgery",
        "Intraoperative Neuromonitoring": "Diagnostic",
        "Cell Saver": "Other Surgical",
        "TXA": "Other Surgical",
        "Endoscopic ACDF": "Endoscopic Surgery",
        "Oblique Corpectomy": "Tumor Surgery",
        "Lateral Corpectomy": "Tumor Surgery",
        "Wound VAC": "Other Surgical",
        # v1.25.0: SNOMED Orphan Sync categories
        "PEID": "Endoscopic Surgery",
        "PETD": "Endoscopic Surgery",
        "LE-ULBD": "Endoscopic Surgery",
        "LAMP": "Decompression Surgery",
        "rhBMP-2": "Other Surgical",
        "Allograft bone grafting": "Other Surgical",
        "Autograft bone grafting": "Other Surgical",
        "Bone graft augmentation": "Other Surgical",
        "Demineralized bone matrix": "Other Surgical",
        "Pedicle screw instrumentation": "Fixation",
        "Interbody cage implantation": "Other Surgical",
        "Dural repair": "Other Surgical",
        "Posterior stabilization": "Fixation",
        "Laminar reconstruction": "Decompression Surgery",
        "Minimally Invasive Decompression": "Decompression Surgery",
        "Flavectomy": "Decompression Surgery",
        "Bilateral facetectomy": "Decompression Surgery",
        "Pelvic fixation": "Fixation",
        "Dynamic rod fixation": "Fixation",
        "Rigid rod fixation": "Fixation",
        "Plate fixation": "Fixation",
        "Posterior fixation": "Fixation",
        "Percutaneous posterior fixation": "Fixation",
        "Navigation-guided fixation": "Fixation",
        "Anterior fixation": "Fixation",
        "Transpedicular fixation": "Fixation",
        "Robot-assisted fixation": "Fixation",
        "Internal fixation": "Fixation",
        "Lateral plate fixation": "Fixation",
        "Translaminar facet screw fixation": "Fixation",
        "TT fixation": "Fixation",
        "CBT fixation": "Fixation",
        "Hybrid CBT-TT fixation": "Fixation",
        # PCO merged into SPO
        "Facet joint osteotomy": "Osteotomy",
        "Posterior osteotomy": "Osteotomy",
        "Transoral osteotomy": "Osteotomy",
        "C1/2 posterior fusion": "Posterolateral Fusion",
        "CDA": "Motion Preservation",
        "Closed reduction": "Other Surgical",
        "Open reduction": "Other Surgical",
        "Stereotactic Navigation": "Navigation/Robotics",
        "Robot-assisted spine surgery": "Navigation/Robotics",
        "Navigation-guided spine surgery": "Navigation/Robotics",
        "Bariatric Surgery": "Other Surgical",
        "Injection Therapy": "Injection Therapy",
        "Vertebral Biopsy": "Diagnostic",
        "Zoledronate": "Conservative Treatment",
        # v1.25.0: New SNOMED concept categories (Gap C)
        "Expandable Cage": "Other Surgical",
        "Zero-Profile Device": "Interbody Fusion",
        "Endoscopic OLIF": "Endoscopic Surgery",
        "Robot-Assisted UBE": "Endoscopic Surgery",
        "AR-Guided Surgery": "Navigation/Robotics",
        "Romosozumab": "Conservative Treatment",
        "Abaloparatide": "Conservative Treatment",
        "Standalone Cage": "Interbody Fusion",
        "3D-Printed Implant": "Other Surgical",
        "Endoscopic Posterior Fusion": "Endoscopic Surgery",
        "Percutaneous Cement Discoplasty": "Other Surgical",
        # v1.25.0: SNOMED Orphan Sync (QC-2026-008)
        "AI-Assisted Procedure": "Navigation/Robotics",
        "AI-based Cobb Angle Measurement": "Diagnostic",
        "Artificial Intelligence": "Diagnostic",
        "Automated Spinopelvic Parameter Measurement": "Diagnostic",
        "Bone Resection": "Decompression Surgery",
        "Cobb Angle Measurement": "Diagnostic",
        "Convolutional Neural Network": "Diagnostic",
        "Deep Learning": "Diagnostic",
        "Deep Learning Landmark Detection": "Diagnostic",
        "Deep Learning Segmentation": "Diagnostic",
        "Keypoint Detection Model": "Diagnostic",
        "Open Spine Surgery": "Other Surgical",
        "Sagittal Correction": "Osteotomy",
        "ULIF": "Interbody Fusion",
    }

    # 결과변수 별칭 매핑
    OUTCOME_ALIASES = {
        # Pain Outcomes
        "VAS": [
            "Visual Analog Scale", "Visual Analogue Scale",
            "Pain Score", "VAS score",
            # v1.14.1: 전체형식 및 소문자 변형
            "Visual Analog Scale (VAS)", "Visual analog scale",
            "visual analog scale", "VAS pain", "Pain VAS",
            # v1.14.11: 일반 통증 용어 추가
            "pain level", "pain intensity", "pain severity",
            # v1.20.2: 시점 변형 → base term으로 정규화
            "VAS at 6 months", "VAS at 12 months", "VAS at 1 year",
            "VAS at 2 years", "VAS at final follow-up",
            "VAS at 3 months", "VAS at 24 months",
            "Final VAS", "Postoperative VAS", "Preoperative VAS",
        ],
        "VAS Back": [
            "VAS-back", "VAS back pain", "Back VAS",
            # v1.14.1: 변형 추가
            "VAS Back Pain", "VAS-Back", "Back pain VAS",
            "VAS (back)", "VAS-BP", "Low back pain VAS",
        ],
        "VAS Leg": [
            "VAS-leg", "VAS leg pain", "Leg VAS", "VAS radicular",
            # v1.14.1: 변형 추가
            "VAS Leg Pain", "VAS-Leg", "Leg pain VAS",
            "VAS (leg)", "VAS-LP", "Radicular pain VAS",
        ],
        # v1.14.11: Neck/Arm pain 추가
        "VAS Neck": [
            "VAS-neck", "VAS neck pain", "Neck VAS",
            "VAS Neck Pain", "VAS-Neck", "Neck pain VAS",
            "VAS (neck)", "neck pain",
        ],
        "VAS Arm": [
            "VAS-arm", "VAS arm pain", "Arm VAS",
            "VAS Arm Pain", "VAS-Arm", "Arm pain VAS",
            "VAS (arm)", "arm pain",
        ],
        "NRS": [
            "Numeric Rating Scale", "Numerical Rating Scale",
            "NRS score", "Pain NRS"
        ],

        # Functional Outcomes
        "ODI": [
            "Oswestry Disability Index", "Oswestry Score",
            "ODI score", "Oswestry",
            # v1.14.1: 전체형식 및 변형
            "Oswestry Disability Index (ODI)", "ODI (Oswestry Disability Index)",
            "oswestry disability index", "Oswestry disability index",
            "Oswestry Low Back Pain Disability Questionnaire",
            # v1.20.2: 시점 변형 → base term으로 정규화
            "ODI at 6 months", "ODI at 12 months", "ODI at 1 year",
            "ODI at 2 years", "ODI at final follow-up",
            "ODI at 3 months", "ODI at 24 months",
            "Final ODI", "Postoperative ODI", "Preoperative ODI",
        ],
        "NDI": [
            "Neck Disability Index", "NDI score",
            # v1.14.1: 전체형식 및 변형
            "Neck Disability Index (NDI)", "NDI (Neck Disability Index)",
            "neck disability index", "Neck disability index",
            # v1.14.11: disability score 변형
            "disability score", "disability index",
        ],
        "JOA": [
            "Japanese Orthopaedic Association",
            "JOA Score", "JOA score",
            # v1.14.1: 변형 추가
            "JOA (Japanese Orthopaedic Association)",
            "Japanese Orthopaedic Association score",
        ],
        "mJOA": [
            "Modified JOA", "modified Japanese Orthopaedic Association",
            "mJOA score",
            # v1.14.1: 변형 추가
            "Modified Japanese Orthopaedic Association",
            "mJOA (Modified Japanese Orthopaedic Association)",
        ],
        "EQ-5D": [
            "EuroQol 5D", "EQ5D", "EQ-5D-5L", "EuroQol-5D",
            "EuroQol-5-Dimensions-5-Level", "EQ-5D-3L",
            # v1.14.11: QOL 변형 추가
            "QOL", "quality of life score",
            # 정규화된 이름의 대소문자 변형
            "eq-5d", "Eq-5d", "eq5d",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "EuroQol-5-Dimensions-5-Level (EQ-5D-5L)",
        ],
        "SF-36": [
            "Short Form 36", "SF36", "SF-36 score", "SF 36",
            # 정규화된 이름의 대소문자 변형
            "sf-36", "Sf-36", "sf36",
            # v1.21.0: Neo4j 고빈도 미매핑 추가 (PCS/MCS 변형)
            "SF-36 Physical Component Summary (PCS)",
            "SF-36 Mental Component Summary (MCS)",
            "SF-12/36 Physical Component Summary (PCS)",
            "SF-12/36 Mental Component Summary (MCS)",
            "SF-12/36 PCS", "SF-12/36 MCS",
            "SF-12/36 PCS - Lumbar Subgroup",
            "SF-12/36 PCS - Cervical Subgroup",
            "Short Form Survey Physical Component Score (SF-12/36 PCS)",
        ],
        # v1.14.11: SF-12를 별도 항목으로 분리
        # v1.15: merged duplicate entries
        "SF-12": [
            "Short Form 12", "SF12", "SF-12 score", "SF 12",
            "sf-12", "Sf-12", "sf12",
        ],
        "SRS-22": [
            "Scoliosis Research Society 22", "SRS22", "SRS-22 score"
        ],

        # Radiological Outcomes - Fusion
        "Fusion Rate": [
            "Fusion rate", "Solid fusion rate", "Bony fusion",
            "Fusion success",
            # v1.14.11: 추가 변형
            "bone fusion", "solid fusion", "fusion outcome",
            "radiographic fusion", "CT fusion",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Fusion Rate at 6 Months", "Fusion Rate at 12 Months",
            "Interbody Fusion Rate", "Interbody Fusion Rate (Primary Outcome)",
            "Fusion Rates/Clinical Outcomes",
        ],
        # v1.14.11: Pseudarthrosis 추가
        "Pseudarthrosis": [
            "pseudarthrosis", "Pseudoarthrosis", "nonunion",
            "non-union", "Nonunion", "fusion failure",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Pseudoarthrosis/Nonunion - Lumbar Level",
            "Pseudoarthrosis/Nonunion - Cervical Level",
            "Pseudoarthrosis/Nonunion - Multivariate Analysis",
            "Pseudarthrosis rate", "pseudarthrosis rate",
        ],
        "Cage Subsidence": [
            "Subsidence", "Cage migration", "Implant subsidence"
        ],

        # Radiological Outcomes - Alignment
        "Lordosis": [
            "Lumbar lordosis", "LL", "Lumbar curvature"
        ],
        "Cobb Angle": [
            "Cobb angle", "Scoliosis angle", "Curve magnitude",
            "Cobb"
        ],
        "SVA": [
            "Sagittal Vertical Axis", "C7 Plumb Line",
            "C7 SVA", "SVA distance"
        ],
        "PT": [
            "Pelvic Tilt", "PT angle"
        ],
        "PI-LL": [
            "PI-LL Mismatch", "Pelvic Incidence-Lumbar Lordosis",
            "PI minus LL", "PI-LL mismatch"
        ],

        # Complications
        "Complication Rate": [
            "Complication rate", "Adverse events", "Complications",
            "Overall complications",
            # v1.14.1: 변형 추가
            "Postoperative complications", "postoperative complications",
            "Postoperative Complications", "complication rate",
            "Total complications", "Surgical complications",
        ],
        "Dural Tear": [
            "Durotomy", "Incidental durotomy", "Dural tear rate",
            "CSF leak",
            # v1.20.2: 추가 변형
            "Dural tear incidence", "dural tear", "Dural injury",
            "CSF leakage", "Cerebrospinal fluid leak",
            "Incidental dural tear", "경막 손상",
        ],
        "Nerve Injury": [
            "Nerve root injury", "Neurological injury",
            "Nerve damage", "Radiculopathy"
        ],
        "Infection Rate": [
            "Surgical site infection", "SSI", "Infection",
            "Wound infection"
        ],
        "Reoperation Rate": [
            "Reoperation", "Revision surgery", "Revision rate"
        ],
        "ASD": [
            "Adjacent Segment Disease", "Adjacent segment degeneration",
            "ASD rate"
        ],
        "PJK": [
            "Proximal Junctional Kyphosis",
            "PJK incidence", "PJK Incidence", "PJK rate", "Proximal junctional failure"
        ],
        # v1.14.3: Epidural Hematoma, C5 Palsy 추가
        "Epidural Hematoma": [
            "Epidural hematoma", "Postoperative epidural hematoma",
            "postoperative epidural hematoma", "Spinal epidural hematoma",
            "epidural hematoma", "EDH", "Hematoma",
        ],
        "C5 Palsy": [
            "C5 palsy", "C5 nerve palsy", "C5 root palsy",
            "Postoperative C5 palsy", "C5 radiculopathy",
            "Upper limb palsy",
        ],
        "Wound Dehiscence": [
            "Wound dehiscence", "wound dehiscence", "Dehiscence",
            "Surgical wound dehiscence", "Wound breakdown",
        ],

        # ========================================
        # Surgical Outcomes
        # ========================================
        "Operation Time": [
            "Operative time", "Surgery time", "Surgical duration",
            "OR time", "수술 시간",
            # v1.14.1: 소문자/변형 추가
            "operative time", "Operative Time", "Operating time",
            "Total operative time", "total operative time",
            "Surgical time", "surgical time",
            # v1.20.2: 추가 변형
            "Procedure time", "Procedure duration",
            "Procedure elapsed minutes", "Operating room time",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Operative Duration", "operative duration",
        ],
        "Blood Loss": [
            "EBL", "Estimated blood loss", "Intraoperative blood loss",
            "출혈량",
            # v1.14.1: 변형 추가
            "Intraoperative Blood Loss", "intraoperative blood loss",
            "Total Blood Loss", "total blood loss",
            "estimated blood loss", "Blood loss",
            # v1.20.2: 추가 변형
            "Estimated Blood Loss", "Intraoperative EBL",
            "Total EBL", "추정 출혈량",
            # v1.21.0: Neo4j 비교형식 변형 정규화
            "Full-Endoscopic LIF vs MIS-TLIF - Blood Loss",
            "OLIF vs MIS-TLIF - Blood Loss",
        ],
        "Hospital Stay": [
            "Length of stay", "LOS", "Hospital length of stay",
            "Hospitalization", "재원 기간",
            # v1.14.1: 변형 추가
            "Length of Stay", "length of stay",
            "Hospital LOS", "hospital stay",
            "Postoperative hospital stay",
            # v1.21.0: Neo4j 비교형식 변형 정규화
            "Tubular vs Open Microdiscectomy - Hospital Stay",
        ],
        "Time to Ambulation": [
            "Time to walking", "Mobilization time", "보행 시작 시간"
        ],
        "Return to Work": [
            "RTW", "Work return", "Disability duration",
            "복직 시간"
        ],
        "Cost": [
            "Hospital cost", "Total cost", "Treatment cost",
            "비용",
            # v1.20.2: 추가 변형
            "Direct cost", "Indirect cost", "Total hospital cost",
            "Economic cost", "Medical cost", "총 비용",
            # v1.25.0: cost-effectiveness / QALY variants
            "QALY", "Quality-adjusted life year",
            "Cost-effectiveness", "cost-effectiveness",
            "ICER", "Incremental cost-effectiveness ratio",
            "Cost per QALY", "Economic evaluation",
        ],

        # ========================================
        # Patient Satisfaction
        # ========================================
        "MacNab": [
            "MacNab criteria", "Modified MacNab",
            "Excellent/Good rate",
            # v1.25.0: alias expansion
            "Macnab criteria", "MacNab outcome",
            "Modified Macnab criteria", "McNab criteria",
            "MacNab classification",
        ],
        "Odom": [
            "Odom criteria", "Odom classification"
        ],
        "Patient Satisfaction": [
            "Satisfaction rate", "Patient satisfaction score",
            # v1.14.11: clinical/functional outcome 매핑
            "clinical outcome", "Clinical outcome", "surgical outcome",
            "functional outcome", "functional status", "Functional outcome",
            "Satisfaction", "환자 만족도"
        ],
        "PGIC": [
            "Patient Global Impression of Change", "Global improvement"
        ],
        "NPS": [
            "Net Promoter Score", "Would recommend"
        ],

        # ========================================
        # Neurological Outcomes
        # ========================================
        "Motor Strength": [
            "Motor function", "MRC grade", "Muscle strength",
            "근력"
        ],
        "Sensory Function": [
            "Sensory deficit", "Sensory recovery", "감각"
        ],
        "ASIA Score": [
            "ASIA Impairment Scale", "AIS grade",
            "Spinal cord injury grade",
            # v1.25.0: alias expansion
            "ASIA grade", "AIS score", "ASIA Impairment Scale score",
            "ASIA motor score", "ASIA sensory score",
            "American Spinal Injury Association score",
        ],
        "Nurick Grade": [
            "Nurick myelopathy grade", "Nurick scale"
        ],

        # ========================================
        # Quality of Life
        # ========================================
        "PROMIS": [
            "PROMIS Physical Function", "PROMIS Pain Intensity",
            "PROMIS score",
            # v1.25.0: alias expansion
            "PROMIS-10", "PROMIS-29", "PROMIS Global Health",
            "PROMIS Physical Function score",
            "Patient-Reported Outcomes Measurement Information System",
        ],
        "WHOQOL": [
            "WHO Quality of Life", "WHOQOL-BREF"
        ],
        "COMI": [
            "Core Outcome Measures Index", "COMI score",
            # v1.25.0: alias expansion
            "COMI Back", "COMI Neck", "Core Outcome Measure Index",
        ],
        "Zurich Claudication": [
            "ZCQ", "Zurich Claudication Questionnaire",
            "Symptom Severity Scale", "Physical Function Scale",
            # v1.25.0: alias expansion
            "ZCQ score", "Zurich Claudication Questionnaire score",
            "Swiss Spinal Stenosis Questionnaire",
        ],

        # ========================================
        # Radiological - Additional
        # ========================================
        "Disc Height": [
            "Disc space height", "DHI", "Disc height index",
            "추간판 높이",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Intervertebral Disc Height", "intervertebral disc height",
        ],
        "Foraminal Height": [
            "Neural foraminal height", "Foramen height"
        ],
        "Canal Diameter": [
            "Spinal canal diameter", "Dural sac diameter",
            "AP diameter"
        ],
        "Segmental Angle": [
            "Segmental lordosis", "Segmental kyphosis"
        ],
        "Global Balance": [
            "C7-S1 SVA", "Global sagittal balance"
        ],
        "Coronal Balance": [
            "Coronal alignment", "C7 tilt", "Trunk shift"
        ],

        # ========================================
        # Oncology Outcomes
        # ========================================
        "Survival Rate": [
            "Overall survival", "OS", "생존율"
        ],
        "Recurrence Rate": [
            "Local recurrence", "Tumor recurrence", "재발률"
        ],
        "SINS Score": [
            "Spinal Instability Neoplastic Score"
        ],
        "Tokuhashi Score": [
            "Revised Tokuhashi", "Tokuhashi prognosis"
        ],
        "Tomita Score": [
            "Tomita surgical classification"
        ],

        # v1.16.2: SNOMED-mapped outcomes without aliases
        "Deep Surgical Site Infection": [
            "Deep SSI", "deep SSI", "Deep infection",
            "Deep wound infection", "deep wound infection", "심부 감염",
        ],
        "Superficial Surgical Site Infection": [
            "Superficial SSI", "superficial SSI", "Superficial infection",
            "Superficial wound infection", "superficial wound infection",
            "표재성 감염",
        ],
        "Recurrent Disc Herniation": [
            "Recurrent herniation", "Re-herniation",
            "recurrent disc herniation", "Disc re-herniation",
            "Same-level recurrence", "재발성 디스크",
        ],
        "Postoperative Drainage": [
            "Drainage volume", "Drain output", "Hemovac output",
            "Post-op drainage", "수술후 배액량", "배액량",
        ],
        "Serum CPK": [
            "CPK", "CK", "Creatine kinase",
            "Creatine phosphokinase", "Muscle enzyme",
            "크레아틴 키나제",
        ],
        "Scar Quality": [
            "Wound cosmesis", "Scar appearance",
            "Cosmetic outcome", "Scar assessment",
            "흉터 품질",
        ],
        "ASD Reoperation Rate": [
            "ASD reoperation", "Adjacent segment reoperation",
            "Junctional reoperation", "ASD-RR",
            "인접분절 재수술률",
        ],

        # v1.19.5: 추가 aliases — Neo4j 상위 빈도 미매핑 Outcomes
        "Pulmonary Embolism": [
            "PE", "pulmonary embolism", "Pulmonary thromboembolism",
            "Venous thromboembolism", "VTE",
        ],
        "Sepsis": [
            "sepsis", "Postoperative sepsis", "Surgical sepsis",
        ],
        "Rod Fracture": [
            "Rod fracture", "rod fracture", "Rod breakage",
            "Instrumentation failure",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Rod Fracture incidence", "rod fracture incidence",
            "Rod fracture rate",
        ],
        "Screw Loosening": [
            "screw loosening", "Pedicle screw loosening",
            "Screw pullout", "screw pullout",
        ],
        "Screw Accuracy": [
            "screw accuracy", "Screw placement accuracy",
            "Pedicle screw accuracy", "Screw malposition",
            "screw malposition",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Navigation-Assisted Pedicle Screw Accuracy",
            "Percutaneous Pedicle Screw Accuracy",
            "AR Pedicle Screw Placement Accuracy",
        ],
        "Readmission Rate": [
            "readmission rate", "30-day readmission",
            "Readmission", "Hospital readmission",
            "30-Day Readmission Rate", "재입원율",
            # v1.20.2: 추가 변형
            "30-day readmission rate", "90-day readmission",
            "90-Day Readmission Rate", "Unplanned readmission",
            "30 day readmission", "readmission",
        ],
        "RBC Transfusion": [
            "RBC Transfusion Requirement", "Blood transfusion",
            "Transfusion rate", "Packed RBC",
        ],
        "Heterotopic Ossification": [
            "heterotopic ossification", "HO",
            "Ectopic bone formation",
            # v1.21.0: Neo4j 오타 변형 추가
            "Heterotrophic Ossification", "heterotrophic ossification",
        ],
        "Osteolysis": [
            "osteolysis", "Endplate resorption",
            "Bone resorption", "Endplate Resorption",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Endplate Resorption/Osteolysis",
        ],
        "Facet Joint Violation": [
            "facet joint violation", "Facet violation",
            "FJV", "Facet breach",
        ],
        "Fluoroscopy Time": [
            "Fluoroscopic time", "Radiation exposure",
            "Fluoroscopy dose", "Fluoroscopic Scan Number",
        ],
        "Learning Curve": [
            "learning curve", "Surgical learning curve",
            "Case volume effect", "Proficiency curve",
        ],
        "Radiculopathy": [
            "radiculopathy", "Postoperative radiculopathy",
            "BMP-related radiculitis", "New radiculopathy",
        ],

        # ========================================
        # v1.20.2: Additional Outcome Aliases (coverage expansion)
        # ========================================


        # Perioperative metrics
        "Fluoroscopy Dose": [
            "fluoroscopy dose", "Radiation dose",
            "Cumulative radiation dose", "방사선 노출량",
        ],
        "Drain Duration": [
            "drain duration", "Drainage duration",
            "Duration of drainage", "배액 기간",
        ],

        # Mortality
        "Mortality": [
            "mortality", "In-hospital mortality",
            "30-day mortality", "90-day mortality",
            "Perioperative mortality", "Postoperative mortality",
            "사망률",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Mortality rate", "mortality rate",
            "In-Hospital Mortality (CKD vs Non-CKD)",
            "In-Hospital Mortality (Dialysis vs Non-Dialysis)",
        ],

        # Specific complication outcomes
        "Urinary Tract Infection": [
            "UTI", "urinary tract infection",
            "Postoperative UTI", "요로 감염",
        ],
        "Pneumonia": [
            "pneumonia", "Postoperative pneumonia",
            "Aspiration pneumonia", "폐렴",
        ],
        "Deep Vein Thrombosis": [
            "DVT", "deep vein thrombosis",
            "Postoperative DVT", "심부정맥혈전증",
        ],
        "Delirium": [
            "delirium", "Postoperative delirium",
            "POD", "수술후 섬망",
        ],
        "Dysphagia": [
            "dysphagia", "Postoperative dysphagia",
            "Swallowing difficulty", "연하곤란",
        ],
        "Dysphonia": [
            "dysphonia", "Hoarseness", "Voice change",
            "Recurrent laryngeal nerve palsy", "목소리 변화",
        ],
        "Hardware Failure": [
            "hardware failure", "Implant failure",
            "Instrumentation failure", "기기 실패",
        ],
        "Screw Misplacement": [
            "screw misplacement", "Screw malpositioning",
            "Pedicle breach", "Cortical breach",
        ],
        "Cage Migration": [
            "cage migration", "Cage retropulsion",
            "Cage displacement", "케이지 이동",
        ],
        "Wound Complication": [
            "wound complication", "Wound healing complication",
            "Wound problem", "창상 합병증",
        ],
        "Ileus": [
            "ileus", "Postoperative ileus",
            "Paralytic ileus", "장마비",
        ],
        "Vascular Injury": [
            "vascular injury", "Great vessel injury",
            "Arterial injury", "Venous injury",
            "혈관 손상",
        ],
        "Sympathetic Dysfunction": [
            "sympathetic dysfunction",
            "Sympathetic chain injury", "Retrograde ejaculation",
            "교감신경 손상",
        ],
        "Vertebral Endplate Fracture": [
            "endplate fracture", "Vertebral endplate fracture",
            "Endplate violation", "종판 골절",
        ],

        # Neurological function outcomes
        "Neurological Recovery": [
            "neurological recovery", "Neurological improvement",
            "Neurologic recovery", "신경학적 회복",
        ],
        "Neurological Deficit": [
            "neurological deficit", "Neurologic deficit",
            "New neurological deficit", "Postoperative deficit",
            "신경학적 결손",
        ],
        "Bowel/Bladder Function": [
            "bowel bladder function", "Bladder function",
            "Bowel function", "CES recovery",
            "Sphincter function", "배변/배뇨 기능",
        ],
        "Grip Strength": [
            "grip strength", "Hand grip strength",
            "Handgrip strength", "악력",
        ],
        "Walking Ability": [
            "walking ability", "Ambulation status",
            "Gait improvement", "Walking distance",
            "보행 능력",
        ],

        # Deformity correction outcomes
        "Coronal Correction": [
            "coronal correction", "Coronal Cobb correction",
            "Scoliosis correction", "Curve correction",
        ],
        "Sagittal Correction": [
            "sagittal correction", "Lordosis restoration",
            "Sagittal balance correction", "SVA correction",
        ],
        "Pelvic Incidence": [
            "pelvic incidence", "PI", "PI angle",
        ],
        "T1 Pelvic Angle": [
            "T1 pelvic angle", "TPA", "T1PA",
        ],
        "Global Tilt": [
            "global tilt", "GT", "Global tilt angle",
        ],
        "Pelvic Obliquity": [
            "pelvic obliquity", "Pelvic tilt asymmetry",
        ],
        "Thoracic Kyphosis": [
            "thoracic kyphosis", "TK", "T4-T12 kyphosis",
            "T5-T12 kyphosis",
        ],

        # Length/size measurements
        "Fusion Segment Length": [
            "fusion segment length", "Number of fused levels",
            "Fusion extent", "유합 분절 수",
        ],
        "Cage Height": [
            "cage height", "Interbody cage height",
            "Cage size", "케이지 높이",
        ],
        "Screw Length": [
            "screw length", "Pedicle screw length",
            "나사 길이",
        ],
        "Screw Diameter": [
            "screw diameter", "Pedicle screw diameter",
            "나사 직경",
        ],

        # Patient-reported outcomes (additional)
        "RMDQ": [
            "Roland-Morris Disability Questionnaire",
            "Roland Morris", "RMDQ score",
        ],
        "DASH": [
            "Disabilities of the Arm, Shoulder and Hand",
            "DASH score", "QuickDASH",
        ],
        "PHQ-9": [
            "Patient Health Questionnaire", "PHQ9",
            "PHQ-9 score", "Depression score",
        ],
        "GAD-7": [
            "Generalized Anxiety Disorder 7", "GAD7",
            "GAD-7 score", "Anxiety score",
        ],
        "Brief Pain Inventory": [
            "BPI", "Brief Pain Inventory score",
            "BPI score",
        ],
        "Pain DETECT": [
            "PainDETECT", "painDETECT", "PD-Q",
            "Pain DETECT questionnaire",
        ],
        "JOABPEQ": [
            "JOA Back Pain Evaluation Questionnaire",
            "JOABPEQ score",
        ],

        # Spine-specific imaging outcomes
        "Adjacent Disc Degeneration": [
            "adjacent disc degeneration",
            "Proximal disc degeneration", "Distal disc degeneration",
            "인접분절 디스크 퇴행",
        ],
        "Bone Mineral Density": [
            "BMD", "bone mineral density", "T-score",
            "DEXA", "DXA", "Bone density",
            "골밀도",
        ],
        "Cross-Sectional Area": [
            "CSA", "cross-sectional area",
            "Muscle CSA", "Multifidus CSA",
            "Paraspinal CSA",
        ],
        "Fatty Infiltration": [
            "fatty infiltration", "Fat infiltration",
            "Muscle fat infiltration",
            "Paraspinal fatty infiltration",
        ],

        # Lab / blood outcomes
        "CRP": [
            "C-reactive protein", "CRP level",
            "Serum CRP",
        ],
        "ESR": [
            "Erythrocyte sedimentation rate",
            "ESR level", "Sed rate",
        ],
        "Hemoglobin": [
            "hemoglobin", "Hb", "Hgb",
            "Hemoglobin level", "혈색소",
        ],
        "Albumin": [
            "albumin", "Serum albumin",
            "Albumin level", "알부민",
        ],
        "Vitamin D": [
            "vitamin D", "25-OH vitamin D",
            "25-hydroxyvitamin D", "Serum vitamin D",
            "비타민 D",
        ],

        # Resource utilization
        "ICU Stay": [
            "ICU stay", "ICU length of stay",
            "Intensive care stay", "ICU days",
            "중환자실 재원일",
        ],
        "Opioid Consumption": [
            "opioid consumption", "Narcotic use",
            "Opioid use", "Morphine equivalent",
            "MED (morphine equivalent dose)",
        ],

        # v1.21.0: Neo4j 고빈도 미매핑 신규 canonical 추가
        "ROM": [
            "Range of Motion", "range of motion", "ROM",
            "Range of Motion (ROM)", "Range of Motion (ROM) - Biomechanical",
            "Cervical ROM", "Lumbar ROM", "Segmental ROM",
            "가동 범위",
        ],
        "Functional Recovery": [
            "Functional recovery", "functional recovery",
            "Functional improvement", "Functional status improvement",
        ],
        "PROMs": [
            "Patient-Reported Outcome Measures",
            "Patient-Reported Outcome Measures (PROMs)",
            "Patient reported outcomes", "PROs",
        ],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync + Alias Expansion (Outcomes)
        # ========================================

        # SNOMED orphan — new canonicals
        "Sacral Slope": [
            "SS", "sacral slope", "Sacral slope angle",
            "천골 경사각",
        ],
        "Spinal Stiffness": [
            "spinal stiffness", "Spine stiffness",
            "Segmental stiffness", "척추 강직도",
        ],
        "Transient Thigh Symptoms": [
            "Transient psoas weakness", "Thigh numbness after XLIF",
            "Hip flexion weakness", "일과성 대퇴 증상",
        ],
        "Radiation Exposure": [
            "radiation exposure", "Intraoperative radiation",
            "수술 중 방사선 노출",
        ],
        "Overall Mechanical Complications": [
            "overall mechanical complications",
            "Mechanical failure rate",
            "Instrumentation complication rate",
            "전체 기계적 합병증률",
        ],
        "Von Mises Stress": [
            "von Mises stress", "Finite element stress",
            "Biomechanical stress", "폰 미세스 응력",
        ],
        "Complete Anatomical Reduction": [
            "Anatomical reduction rate",
            "Complete reduction rate",
            "완전 해부학적 정복률",
        ],
        "Solid Fusion": [
            "Solid arthrodesis", "Confirmed fusion",
            "견고한 유합률",
        ],
        "Intraoperative Revision Rate": [
            "intraoperative revision rate",
            "Screw repositioning rate",
            "수술 중 재삽입률",
        ],
        "Sagittal Disc Angle": [
            "sagittal disc angle", "Disc angle",
            "Interbody lordosis angle",
            "시상면 추간판 각도",
        ],
        "Endplate Damage": [
            "Endplate violation", "endplate damage",
            "Vertebral endplate preservation",
            "종판 손상",
        ],
        "BMP Complication Rate": [
            "BMP-associated complications",
            "BMP-related revision rate",
            "BMP 관련 합병증률",
        ],
        "Subsidence Measurement": [
            "Subsidence in mm", "Cage settling measurement",
            "Interbody cage subsidence measurement",
            "침하량 측정",
        ],
        "Aggrecan": [
            "aggrecan", "Aggrecan level",
        ],
        "CSF Leakage": [
            "CSF leakage", "Cerebrospinal fluid leakage",
            "CSF leak rate", "뇌척수액 누출",
        ],
        "Extension of Fixation": [
            "extension of fixation",
            "Fixation extension rate",
        ],
        "Motor Deficit": [
            "motor deficit", "Postoperative motor deficit",
            "New motor weakness", "운동 결손",
        ],
        "Recovery Time": [
            "recovery time", "Time to recovery",
            "Convalescence period", "회복 시간",
        ],
        "SRS-Satisfaction": [
            "SRS satisfaction", "SRS-22 satisfaction domain",
            "SRS satisfaction score",
        ],
        "Sensory Deficit": [
            "sensory deficit", "Postoperative sensory deficit",
            "New sensory deficit", "감각 결손",
        ],
        "Surgical Time": [
            "surgical time", "Total surgical time",
        ],
        "Symptomatic Hematoma": [
            "symptomatic hematoma",
            "Symptomatic postoperative hematoma",
        ],

        # SNOMED orphan — rate/variant aliases for existing canonicals
        # (These are separate SNOMED entries but normalize to base concepts)
        "Postoperative Delirium": [
            "postoperative delirium", "POD incidence",
        ],
        "Radiculitis": [
            "radiculitis", "BMP-related radiculitis",
            "Postoperative radiculitis",
        ],
        "Range of Motion": [
            "range of motion", "Range of motion measurement",
        ],
        "Transfusion Requirement": [
            "transfusion requirement", "Blood transfusion requirement",
        ],
        "Muscle Cross-sectional Area": [
            "muscle cross-sectional area", "Muscle CSA measurement",
        ],
        "Muscle Fat Infiltration": [
            "muscle fat infiltration",
            "Paraspinal muscle fat infiltration",
        ],
        "Adjacent Segment Degeneration": [
            "adjacent segment degeneration",
            "Proximal segment degeneration",
        ],
        "Quality of Life - SF-36": [
            "quality of life SF-36", "QoL SF-36",
        ],
        "Heterotopic Ossification Rate": [
            "heterotopic ossification rate", "HO rate",
        ],
        "Osteolysis Rate": [
            "osteolysis rate", "Bone resorption rate",
        ],
        "Cage Subsidence Rate": [
            "cage subsidence rate", "Subsidence rate",
        ],
        "Pseudarthrosis Rate": [
            "pseudarthrosis rate", "Nonunion rate",
        ],
        "SRS-22 Quality of Life Score": [
            "SRS-22 QoL", "SRS-22 quality of life",
        ],
        "Bone Mineral Density Measurement": [
            "BMD measurement", "Bone density measurement",
        ],
        # v1.25.0: PJK Incidence removed (already covered by PJK canonical)

        # Opioid Consumption SNOMED entry (reverse gap fix)
        "Opioid Consumption": [
            "opioid consumption", "Narcotic use",
            "Opioid use", "Morphine equivalent",
            "MED (morphine equivalent dose)",
        ],

        # ========================================
        # v1.25.0: New SNOMED Concept Aliases (Gap C - Outcomes)
        # ========================================
        "PROMIS-10": [
            "PROMIS-10", "PROMIS Global-10",
            "PROMIS Global Health", "PROMIS-10 전반 건강 점수",
        ],
        "QALY": [
            "Quality-adjusted life year", "Quality adjusted life year",
            "Cost per QALY", "질보정 수명년",
        ],
        "Disc Height Index": [
            "disc height index", "DHI",
            "Disc space height ratio", "Disc height ratio",
            "추간판 높이 지수",
        ],
        "Macnab Criteria": [
            "Macnab criteria", "Modified MacNab",
            "MacNab classification", "MacNab outcome",
            "McNab criteria", "맥낵 기준",
        ],
        "Timed Up and Go": [
            "Timed Up and Go", "TUG test", "TUG",
            "Timed up-and-go", "기립보행검사",
        ],
        "ICER": [
            "Incremental cost-effectiveness ratio",
            "Cost-effectiveness ratio", "Cost per QALY gained",
            "점증적 비용효과비",
        ],
        "Spinal Cord Perfusion": [
            "spinal cord perfusion", "SCPP",
            "Spinal cord perfusion pressure",
            "척수 관류",
        ],

        # ========================================
        # IS_A hierarchy root/category nodes (QC-2026-004)
        # ========================================
        "Pain Outcome": [],  # IS_A root category
        "Functional Outcome": [],  # IS_A root category
        "Quality of Life Outcome": [],  # IS_A root category
        "Radiological Outcome": [],  # IS_A root category
        "Complication Outcome": [],  # IS_A root category
        "Surgical Efficiency Outcome": [],  # IS_A root category
        "Neurological Outcome": [],  # IS_A root category
        "Patient-Reported Outcome": ["PRO", "patient-reported outcome"],
        "Biomechanical Outcome": [],  # IS_A root category
        "Laboratory Outcome": [],  # IS_A root category
        "Oncological Outcome": [],  # IS_A root category
        "Spinopelvic Parameter": ["spinopelvic parameter", "Spinopelvic alignment"],
        # Note: "PJK Incidence" SNOMED key covered by PJK aliases (last-write-wins safe)
        "Screw Malposition": ["screw malposition", "Screw malpositioning", "Pedicle breach"],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync (QC-2026-008) — Outcome
        # ========================================
        "AI/ML Performance Outcome": [
            "AI/ML performance outcome", "AI performance",
            "ML performance", "Model performance outcome",
        ],
        # Note: These SNOMED keys are already reachable as aliases of other canonicals
        # (no need for separate canonical entries — would cause last-write-wins conflicts):
        # "DVT" → alias of Deep Vein Thrombosis
        # "PJK Incidence" → alias of PJK
    }

    # 질환명 별칭 매핑
    PATHOLOGY_ALIASES = {
        # Degenerative Pathologies
        "Lumbar Stenosis": [
            "Lumbar Spinal Stenosis", "LSS", "Spinal Stenosis",
            "Central Stenosis",
            "요추 협착증", "척추관 협착증", "척추 협착증",
            # v1.14.1: 소문자 변형 추가
            "lumbar spinal stenosis", "lumbar stenosis",
            "spinal stenosis", "central stenosis",
            "Lumbar stenosis with instability",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Spinal canal narrowing", "spinal canal narrowing",
            # v1.25.0: severity/qualifier variants
            "Severe spinal stenosis", "severe lumbar stenosis",
            "Moderate spinal stenosis", "Mild spinal stenosis",
            "Degenerative lumbar spinal stenosis",
            "Multilevel lumbar stenosis",
        ],
        "Cervical Stenosis": [
            "Cervical Spinal Stenosis", "CSS",
            "경추 협착증",
            # v1.14.1: 소문자/동의어 추가
            "cervical spinal stenosis", "cervical stenosis",
            "Cervical spondylosis", "cervical spondylosis",
            "Cervical spondylotic myelopathy", "CSM",
        ],
        "Foraminal Stenosis": [
            "Lateral Stenosis", "Foraminal narrowing",
            "추간공 협착증",
            # v1.14.1: 소문자 변형 추가
            "foraminal stenosis", "lateral stenosis",
            "Lateral recess stenosis", "lateral recess stenosis",
        ],
        "Lumbar Disc Herniation": [
            "LDH", "HNP", "Herniated Nucleus Pulposus",
            "Disc Herniation", "Disc Prolapse", "HIVD",
            "추간판 탈출증", "디스크 탈출증", "허리 디스크",
            # v1.14.1: 소문자/변형 추가
            "lumbar disc herniation", "disc herniation",
            "Intervertebral disc herniation", "intervertebral disc herniation",
            "Recurrent lumbar disc herniation", "recurrent disc herniation",
            "Juvenile lumbar disc herniation",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Herniated Intervertebral Disc", "Herniated disc",
            "herniated disc", "Herniated intervertebral disc",
            "intervertebral disc disease", "Spinal disc disease",
        ],
        "Cervical Disc Herniation": [
            "CDH", "Cervical HNP", "Cervical disc prolapse",
            "경추 디스크",
            # v1.14.1: 소문자 변형 추가
            "cervical disc herniation", "cervical HNP",
        ],
        "DDD": [
            "Degenerative Disc Disease", "Disc Degeneration",
            "퇴행성 디스크",
            # v1.14.1: 소문자/변형 추가
            "degenerative disc disease", "Degenerative disc disease",
            "Lumbar degenerative disc disease", "lumbar degenerative disc disease",
            "Intervertebral disc degeneration", "intervertebral disc degeneration",
            "Lumbar degenerative disease", "lumbar degenerative disease",
            "Disc degeneration",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Lumbar Degeneration", "lumbar degeneration",
            "Discogenic low back pain", "discogenic low back pain",
        ],
        "Facet Arthropathy": [
            "Facet Joint Arthritis", "Facet Arthritis",
            "Facet joint disease",
            # v1.14.1: 소문자 변형 추가
            "facet arthropathy", "facet joint arthritis",
            "Facet hypertrophy", "facet hypertrophy",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Lumbar facet joint osteoarthritis", "FJOA",
            "Facet joint osteoarthritis",
        ],
        # v1.14.1: Cervical Myelopathy 신규 추가
        # v1.15: merged duplicate entries
        "Cervical Myelopathy": [
            "Degenerative cervical myelopathy", "degenerative cervical myelopathy",
            "DCM", "Cervical spondylotic myelopathy",
            "cervical myelopathy", "Myelopathy",
            "CSM", "Cervical Spondylotic Myelopathy",
            "Cervical cord compression", "경추 척수병증",
            # v1.20.2: 추가 변형
            "myelopathy", "Compressive myelopathy",
            "Spinal cord myelopathy", "척수병증",
        ],
        # v1.14.1: Cervical Radiculopathy 신규 추가
        "Cervical Radiculopathy": [
            "cervical radiculopathy", "Cervical radicular pain",
            "Cervical nerve root compression",
        ],
        # v1.14.1: Lumbar Radiculopathy 신규 추가
        "Lumbar Radiculopathy": [
            "lumbar radiculopathy", "Sciatica", "sciatica",
            "Lumbar radicular pain", "Radicular pain",
        ],
        # v1.14.1: Segmental Instability 신규 추가
        "Segmental Instability": [
            "segmental instability", "Lumbar instability",
            "lumbar instability", "Spinal instability",
            "spinal instability",
        ],
        "Spondylolisthesis": [
            "Degenerative Spondylolisthesis", "Isthmic Spondylolisthesis",
            "Anterolisthesis", "Slip",
            "척추 전방 전위증", "척추 전위증",
            # v1.14.1: 소문자/변형 추가
            "spondylolisthesis", "degenerative spondylolisthesis",
            "Degenerative lumbar spondylolisthesis",
            "Lumbar spondylolisthesis", "lumbar spondylolisthesis",
            # v1.25.0: grade/severity variants
            "Grade 1 spondylolisthesis", "Grade 2 spondylolisthesis",
            "Grade I spondylolisthesis", "Grade II spondylolisthesis",
            "High-grade spondylolisthesis", "Low-grade spondylolisthesis",
            "Retrolisthesis",
        ],
        "Degenerative Scoliosis": [
            "De Novo Scoliosis", "Adult Degenerative Scoliosis",
            "Degenerative Lumbar Scoliosis",
            "퇴행성 척추 측만증",
            # v1.14.1: 소문자 변형 추가
            "degenerative scoliosis", "de novo scoliosis",
            "adult degenerative scoliosis",
        ],

        # Deformity Pathologies
        "AIS": [
            "Adolescent Idiopathic Scoliosis", "Idiopathic Scoliosis",
            "청소년 특발성 측만증",
            # v1.14.1: 소문자 변형 추가
            "adolescent idiopathic scoliosis", "idiopathic scoliosis",
        ],
        "Adult Scoliosis": [
            "Adult Idiopathic Scoliosis", "성인 측만증",
            # v1.14.1: 소문자 변형 추가
            "adult scoliosis", "adult idiopathic scoliosis",
        ],
        "ASD": [
            "Adult Spinal Deformity",
            "성인 척추 변형",
            # v1.14.1: 전체형식/소문자 변형 추가
            "Adult spinal deformity (ASD)", "adult spinal deformity",
            "ASD (Adult Spinal Deformity)",
        ],
        "Flat Back": [
            "Flat Back Syndrome", "Flatback",
            "Loss of lumbar lordosis",
            # v1.14.1: 소문자 변형 추가
            "flat back syndrome", "flatback syndrome",
        ],
        "Kyphosis": [
            "Thoracic Kyphosis", "Scheuermann Kyphosis",
            "Posttraumatic Kyphosis",
            "척추 후만증", "후만 변형",
            # v1.14.1: 소문자 변형 추가
            "kyphosis", "thoracic kyphosis", "scheuermann kyphosis",
        ],
        "Sagittal Imbalance": [
            "Sagittal malalignment", "Sagittal plane imbalance",
            "시상면 불균형",
            # v1.14.1: 소문자 변형 추가
            "sagittal imbalance", "sagittal malalignment",
            "Global sagittal imbalance", "global sagittal imbalance",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Spinopelvic malalignment", "spinopelvic malalignment",
        ],
        # v1.14.1: PJK 신규 추가
        # v1.15: merged duplicate entries
        "PJK": [
            "Proximal Junctional Kyphosis", "proximal junctional kyphosis",
            "PJF", "Proximal junctional failure", "proximal junctional failure",
            "Junctional kyphosis", "junctional kyphosis",
            "근위부 접합부 후만",
            # v1.25.0: merged from Proximal Junctional Failure
            "Proximal junctional fracture", "Acute PJK failure",
            "근위부 접합부 부전", "근위부 경계부 부전",
        ],
        # v1.14.1: DJK 신규 추가
        # v1.15: merged duplicate entries
        "DJK": [
            "Distal Junctional Kyphosis", "distal junctional kyphosis",
            "Distal junctional failure", "Distal Junctional Failure",
            # v1.25.0: merged from Distal Junctional Failure
            "DJF", "Distal junctional fracture", "원위부 접합부 부전",
        ],
        # v1.14.1: Adjacent Segment Disease 신규 추가
        # v1.15: merged duplicate entries
        "Adjacent Segment Disease": [
            "adjacent segment disease", "ASD (Adjacent Segment)",
            "Adjacent segment degeneration", "adjacent segment degeneration",
            "Adjacent level disease", "Radiographic ASD",
            "ASDis", "인접분절 퇴행",
            # v1.20.2: 추가 변형
            "Adjacent segment pathology", "ASP",
            "Radiographic adjacent segment degeneration",
            "Adjacent level degeneration",
        ],

        # Trauma Pathologies
        "Compression Fracture": [
            "VCF", "Vertebral Compression Fracture",
            "Osteoporotic Fracture",
            "척추 압박 골절", "골다공증성 골절",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Vertebra plana", "vertebra plana",
        ],
        "Burst Fracture": [
            "Vertebral Burst Fracture", "Thoracolumbar Burst Fracture",
            "척추 분쇄 골절"
        ],
        "Chance Fracture": [
            "Flexion-distraction injury", "Seatbelt injury"
        ],
        "Fracture-Dislocation": [
            "Fracture dislocation", "Spinal fracture-dislocation",
            "척추 골절 탈구"
        ],

        # Tumor Pathologies
        "Primary Tumor": [
            "Primary Spinal Tumor", "Spinal neoplasm",
            "원발성 척추 종양",
            # v1.14.1: 소문자 변형 추가
            "primary spinal tumor", "spinal neoplasm",
        ],
        "Spinal Metastasis": [
            "Spine Metastasis", "Vertebral Metastasis",
            "Metastatic Spine Tumor",
            "척추 전이암", "척추 전이",
            # v1.14.1: 소문자/변형 추가
            "spinal metastasis", "spine metastasis",
            "Metastatic spinal disease", "metastatic spinal disease",
            "Metastatic spinal tumors", "metastatic spinal tumors",
            "Metastatic spine disease",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Lung cancer metastasis", "lung cancer metastasis",
        ],
        "Intradural Tumor": [
            "Intradural Spinal Tumor", "Intradural neoplasm"
        ],

        # Infection Pathologies
        "Spondylodiscitis": [
            "Spinal Infection", "Discitis", "Vertebral osteomyelitis",
            "척추 감염"
        ],
        "Epidural Abscess": [
            "Spinal Epidural Abscess", "SEA",
            "경막외 농양",
            # v1.20.2: 소문자/변형 추가
            "spinal epidural abscess", "epidural abscess",
            "Cervical epidural abscess", "Lumbar epidural abscess",
        ],
        "Spinal TB": [
            "Spinal Tuberculosis", "Pott Disease", "Pott's disease",
            "척추 결핵"
        ],
        "Pyogenic Spondylodiscitis": [
            "Pyogenic infection", "Bacterial spondylodiscitis",
            "화농성 척추염"
        ],
        "Fungal Spondylitis": [
            "Fungal spinal infection", "Aspergillus spondylitis"
        ],
        "Postoperative Infection": [
            "Surgical site infection", "SSI", "Wound infection",
            "수술 후 감염"
        ],

        # ========================================
        # Cervical-Specific Pathologies
        # ========================================
        "Cervical Radiculopathy": [
            "Cervical nerve root compression", "Cervical root pain",
            "경추 신경근병증"
        ],
        "OPLL": [
            "Ossification of Posterior Longitudinal Ligament",
            "후종인대 골화증",
            # v1.20.2: 소문자/변형 추가
            "ossification of posterior longitudinal ligament",
            "Ossification of the posterior longitudinal ligament",
            "Cervical OPLL", "Thoracic OPLL",
        ],
        "OLF": [
            "Ossification of Ligamentum Flavum", "황색인대 골화증",
            # v1.20.2: 소문자/변형 추가
            "ossification of ligamentum flavum",
            "Ossification of the ligamentum flavum",
            "OYL", "Thoracic OLF",
        ],
        "Atlantoaxial Instability": [
            "C1-C2 instability", "AAI", "환축추 불안정"
        ],
        "Os Odontoideum": [
            "Os odontoideum anomaly", "치돌기 이상"
        ],
        "Klippel-Feil Syndrome": [
            "Klippel-Feil", "Congenital cervical fusion",
            "클리펠-파일 증후군"
        ],
        "Basilar Invagination": [
            "Basilar impression", "두개저 함입증"
        ],

        # ========================================
        # Additional Degenerative Pathologies
        # ========================================
        "DISH": [
            "Diffuse Idiopathic Skeletal Hyperostosis",
            "Forestier disease", "미만성 특발성 골격 과골증"
        ],
        "Baastrup Disease": [
            "Kissing spine syndrome", "Interspinous bursitis"
        ],
        "Bertolotti Syndrome": [
            "Lumbosacral transitional vertebra", "LSTV"
        ],
        "Synovial Cyst": [
            "Facet cyst", "Juxta-articular cyst", "활막낭종",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Lumbar synovial facet cyst", "lumbar synovial facet cyst",
        ],
        "Tarlov Cyst": [
            "Perineural cyst", "Sacral nerve root cyst"
        ],
        "Modic Changes": [
            "Modic type 1", "Modic type 2", "Modic type 3",
            "Endplate changes"
        ],
        "Failed Back Surgery Syndrome": [
            "FBSS", "Post-laminectomy syndrome",
            "척추수술후 증후군"
        ],

        # ========================================
        # Tumor-Specific Pathologies (Expanded)
        # ========================================
        "Hemangioma": [
            "Vertebral hemangioma", "Spinal hemangioma",
            "척추 혈관종"
        ],
        "Giant Cell Tumor": [
            "GCT", "Osteoclastoma", "거대세포종"
        ],
        "Osteoblastoma": [
            "Osteoid osteoma", "Benign osteoblastoma"
        ],
        "Ewing Sarcoma": [
            "Ewing's sarcoma", "PNET"
        ],
        "Multiple Myeloma": [
            "Plasmacytoma", "Plasma cell neoplasm",
            "다발성 골수종"
        ],
        "Chordoma": [
            "Sacral chordoma", "Clival chordoma", "척삭종"
        ],
        "Schwannoma": [
            "Spinal schwannoma", "Neurilemmoma", "신경초종"
        ],
        "Meningioma": [
            "Spinal meningioma", "Intradural meningioma",
            "수막종"
        ],
        "Ependymoma": [
            "Spinal ependymoma", "Myxopapillary ependymoma"
        ],
        "Neurofibroma": [
            "Spinal neurofibroma", "Neurofibromatosis"
        ],
        "Osteosarcoma": [
            "Spinal osteosarcoma", "골육종"
        ],
        "Chondrosarcoma": [
            "Spinal chondrosarcoma", "연골육종"
        ],

        # ========================================
        # Inflammatory/Rheumatologic Pathologies
        # ========================================
        "Ankylosing Spondylitis": [
            "AS", "Bamboo spine", "Marie-Strümpell disease",
            "강직성 척추염"
        ],
        "Rheumatoid Arthritis": [
            "RA", "Cervical RA", "류마티스 관절염"
        ],
        "Psoriatic Arthritis": [
            "Psoriatic spondylitis", "PsA", "건선성 관절염"
        ],
        "Reactive Arthritis": [
            "Reiter syndrome", "반응성 관절염"
        ],
        "Enteropathic Arthritis": [
            "IBD-associated spondylitis", "Crohn's spine"
        ],
        "SAPHO Syndrome": [
            "Synovitis, Acne, Pustulosis, Hyperostosis, Osteitis"
        ],

        # ========================================
        # Deformity (Expanded)
        # ========================================
        "Congenital Scoliosis": [
            "Congenital spinal deformity", "Hemivertebra",
            "선천성 측만증"
        ],
        "Neuromuscular Scoliosis": [
            "NM scoliosis", "Muscular dystrophy scoliosis",
            "신경근육성 측만증"
        ],
        "Syndromic Scoliosis": [
            "Marfan scoliosis", "Ehlers-Danlos scoliosis"
        ],
        "Junctional Kyphosis": [
            "Thoracolumbar kyphosis", "TL kyphosis"
        ],
        "Post-laminectomy Kyphosis": [
            "Post-surgical kyphosis", "수술후 후만"
        ],

        # ========================================
        # Trauma (Expanded)
        # ========================================
        "SCIWORA": [
            "Spinal Cord Injury Without Radiographic Abnormality"
        ],
        "Hangman Fracture": [
            "C2 pars fracture", "Traumatic spondylolisthesis of C2"
        ],
        "Jefferson Fracture": [
            "C1 burst fracture", "Atlas fracture"
        ],
        "Odontoid Fracture": [
            "Dens fracture", "Type I/II/III odontoid fracture",
            "치돌기 골절"
        ],
        "Sacral Fracture": [
            "Sacral insufficiency fracture", "Denis zone fracture",
            "천추 골절"
        ],
        "Thoracolumbar Fracture": [
            "TL fracture", "Thoracolumbar burst",
            "흉요추 골절"
        ],

        # ========================================
        # Pediatric Pathologies
        # ========================================
        "Scheuermann Disease": [
            "Scheuermann kyphosis", "Juvenile kyphosis",
            "쇼이어만병"
        ],
        "Spondylolysis": [
            "Pars defect", "Pars interarticularis defect",
            "척추분리증"
        ],
        "Pediatric Disc Herniation": [
            "Adolescent disc herniation", "소아 디스크"
        ],
        "Congenital Kyphosis": [
            "Type I/II congenital kyphosis", "선천성 후만"
        ],
        "Tethered Cord": [
            "Tethered spinal cord", "Filum terminale syndrome",
            "척수 유착 증후군"
        ],
        "Diastematomyelia": [
            "Split cord malformation", "이중 척수"
        ],

        # v1.16.2: SNOMED-mapped pathologies without aliases
        "Cauda Equina Syndrome": [
            "CES", "Cauda equina", "cauda equina syndrome",
            "cauda equina", "마미 증후군", "마미총 증후군",
        ],
        "Diabetes Mellitus": [
            "DM", "Diabetes", "diabetes", "diabetes mellitus",
            "Type 2 diabetes", "Type 1 diabetes", "Type II DM",
            "IDDM", "NIDDM", "당뇨병", "당뇨",
        ],

        # ========================================
        # v1.20.2: Additional Pathology Aliases (coverage expansion)
        # ========================================

        # Degenerative - additional terms
        "Neurogenic Claudication": [
            "neurogenic claudication", "Spinal claudication",
            "Neurogenic intermittent claudication", "NIC",
            "신경인성 파행",
        ],
        "Lumbar Spondylosis": [
            "lumbar spondylosis", "Lumbar degenerative changes",
            "Degenerative lumbar spine", "요추 퇴행성 변화",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Lumbar spine disorders", "lumbar spine disorders",
        ],
        "Thoracic Disc Herniation": [
            "thoracic disc herniation", "Thoracic HNP",
            "Thoracic disc prolapse", "흉추 디스크 탈출증",
        ],
        "Spinal Cord Injury": [
            "SCI", "spinal cord injury", "Traumatic spinal cord injury",
            "TSCI", "Acute spinal cord injury", "척수 손상",
        ],
        "Spinal Cord Compression": [
            "spinal cord compression", "Cord compression",
            "Thoracic cord compression", "척수 압박",
        ],
        "Central Canal Stenosis": [
            "central canal stenosis", "Central stenosis",
            "central canal narrowing",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Central spinal canal stenosis", "central spinal canal stenosis",
        ],
        "Lateral Recess Stenosis": [
            "lateral recess stenosis", "Lateral recess narrowing",
            "Subarticular stenosis", "측방 함요 협착",
        ],

        # Deformity - additional terms
        "Scoliosis": [
            "scoliosis", "Spinal scoliosis", "척추 측만증",
            "측만증",
        ],
        "Coronal Imbalance": [
            "coronal imbalance", "Coronal malalignment",
            "Coronal decompensation", "관상면 불균형",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Coronal deformity", "coronal deformity",
        ],
        "Fixed Sagittal Imbalance": [
            "fixed sagittal imbalance", "FSI",
            "Positive sagittal balance",
        ],
        "Iatrogenic Flat Back": [
            "iatrogenic flat back", "Iatrogenic flatback",
            "Post-fusion flat back",
        ],
        "Rotatory Subluxation": [
            "rotatory subluxation", "Atlantoaxial rotatory subluxation",
            "AARS",
        ],
        "Cervical Kyphosis": [
            "cervical kyphosis", "Cervical kyphotic deformity",
            "Post-laminectomy cervical kyphosis", "경추 후만",
        ],

        # Trauma - additional terms
        "Vertebral Fracture": [
            "vertebral fracture", "Spine fracture",
            "Spinal fracture", "척추 골절",
        ],
        "Osteoporotic Vertebral Fracture": [
            "osteoporotic vertebral fracture", "OVF", "OVCF",
            "Osteoporotic vertebral compression fracture",
            "Osteoporotic fracture", "골다공증성 척추 골절",
        ],
        "Pathological Fracture": [
            "pathological fracture", "Pathologic fracture",
            "Metastatic fracture", "병적 골절",
        ],
        "Subaxial Cervical Spine Injury": [
            "Subaxial cervical injury", "subaxial cervical spine injury",
            "SLIC", "Cervical spine trauma",
        ],
        "Facet Dislocation": [
            "facet dislocation", "Unilateral facet dislocation",
            "Bilateral facet dislocation", "Facet joint dislocation",
            "Jumped facet",
        ],

        # Infection - additional terms
        "Vertebral Osteomyelitis": [
            "vertebral osteomyelitis", "Spinal osteomyelitis",
            "척추 골수염",
        ],

        # Vascular
        "Spinal AVM": [
            "spinal AVM", "Spinal arteriovenous malformation",
            "Spinal dural AV fistula", "SDAVF",
            "척추 동정맥 기형",
        ],

        # Metabolic / Bone quality
        "Osteoporosis": [
            "osteoporosis", "Spinal osteoporosis",
            "Osteopenia", "Low bone density",
            "Low bone mineral density", "골다공증",
        ],
        "Osteopenia": [
            "osteopenia", "Low bone mass",
            "Reduced bone density", "골감소증",
        ],

        # Pain conditions
        "Axial Low Back Pain": [
            "axial low back pain", "Axial LBP",
            "Mechanical low back pain", "축성 요통",
        ],
        "Low Back Pain": [
            "LBP", "low back pain", "Chronic low back pain",
            "CLBP", "Acute low back pain", "요통",
        ],
        "Neck Pain": [
            "neck pain", "Cervical pain", "Cervicalgia",
            "Axial neck pain", "경부통",
        ],
        "Neuropathic Pain": [
            "neuropathic pain", "Nerve pain",
            "신경병성 통증",
        ],
        "Radicular Pain": [
            "radicular pain", "Root pain", "Nerve root pain",
            "신경근통",
        ],

        # Developmental / Congenital
        "Spinal Dysraphism": [
            "spinal dysraphism", "Spina bifida",
            "Neural tube defect", "이분 척추",
        ],
        "Chiari Malformation": [
            "Chiari malformation", "Chiari I malformation",
            "Arnold-Chiari malformation", "키아리 기형",
        ],
        "Syringomyelia": [
            "syringomyelia", "Syrinx", "척수공동증",
        ],

        # Postoperative conditions
        "Pseudarthrosis": [
            "pseudarthrosis", "Pseudoarthrosis", "Nonunion",
            "Non-union", "Fusion failure", "가관절증",
            # v1.21.0: Neo4j 고빈도 미매핑 추가
            "Failed fusion", "failed fusion",
            # v1.25.0: Nonunion merged here
            "nonunion", "Bony non-union", "불유합",
        ],
        "Post-laminectomy Syndrome": [
            "post-laminectomy syndrome", "Failed back surgery",
            "Post-surgical pain syndrome",
            "수술후 통증 증후군",
        ],
        "Epidural Fibrosis": [
            "epidural fibrosis", "Peridural fibrosis",
            "Post-surgical epidural fibrosis",
            "경막외 섬유화",
        ],

        # Miscellaneous
        "Spinal Cord Tumor": [
            "spinal cord tumor", "Intramedullary tumor",
            "Intramedullary spinal cord tumor", "IMSCT",
            "척수 종양",
        ],
        "Sacroiliac Joint Dysfunction": [
            "SI joint dysfunction", "SIJ dysfunction",
            "Sacroiliac joint pain", "SI joint pain",
            "천장관절 기능장애",
        ],
        "Coccygodynia": [
            "coccygodynia", "Coccydynia", "Tailbone pain",
            "Coccyx pain", "미골통",
        ],
        "Tandem Stenosis": [
            "tandem stenosis", "Tandem spinal stenosis",
            "Coexisting cervical and lumbar stenosis",
        ],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync + Alias Expansion (Pathology)
        # ========================================

        # v1.25.0: PJF merged into "Proximal Junctional Failure" (Gap C entry)
        # v1.25.0: Nonunion merged into Pseudarthrosis (same concept; see Pathology section)
        "Frailty": [
            "frailty", "Frail elderly", "Frailty syndrome",
            "Age-related muscle loss", "허약",
        ],
        "Cervical spondylotic disease": [
            "Cervical degenerative disease",
            "Cervical spine disorders", "경추 척추증",
        ],
        "Discogenic low back pain": [
            "Discogenic pain", "Disc-related low back pain",
            "Discogenic LBP", "추간판성 요통",
        ],
        "Lumbar deformity": [
            "lumbar deformity", "Degenerative lumbar spine disease",
            "Degenerative lumbar spine conditions",
            "Lumbar spine pathology", "요추 변형",
        ],
        "Transverse ligament rupture": [
            "Transverse ligament injury", "TAL rupture",
            "Transverse atlantal ligament disruption",
            "환추 횡인대 파열",
        ],
        "Atlantoaxial rotatory fixation": [
            "AARF", "Atlantoaxial rotatory subluxation",
            "AARS", "C1-C2 rotatory fixation",
            "환축추 회전 고정",
        ],
        "Coronal malalignment": [
            "coronal malalignment", "Coronal decompensation",
            "Coronal plane deformity", "관상면 부정렬",
        ],
        "Pedicle screw loosening": [
            "screw loosening", "Screw pullout",
            "Pedicle screw pullout", "Implant loosening",
            "척추경 나사못 이완",
        ],
        "Postoperative spinal epidural hematoma": [
            "PSEH", "Spinal epidural hematoma after surgery",
            "symptomatic postoperative spinal epidural hematoma",
            "수술 후 척추 경막외 혈종",
        ],
        "Paraspinal muscle degeneration": [
            "Paraspinal muscle atrophy", "Lumbar muscle atrophy",
            "Multifidus atrophy", "Paravertebral muscle degeneration",
            "척추 주위근 퇴행",
        ],
        "Spinopelvic misalignment": [
            "spinopelvic malalignment", "Spinopelvic imbalance",
            "PI-LL mismatch", "척추골반 부정렬",
        ],
        "Instrumentation failure": [
            "instrumentation failure", "Hardware failure",
            "Implant failure", "Surgical device complications",
            "기기 실패",
        ],
        "Spondylitis with epidural abscess": [
            "Spinal epidural abscess with spondylitis",
            "Vertebral osteomyelitis with abscess",
            "척추염 동반 경막외 농양",
        ],
        "Thoracic stenosis": [
            "Thoracic spinal canal stenosis",
            "Thoracic spine stenosis", "흉추 협착증",
        ],
        "Neuroforaminal compression": [
            "neuroforaminal compression",
            "Neural foraminal narrowing", "신경공 압박",
        ],
        "Vertebral instability": [
            "vertebral instability",
            "Segmental mechanical instability",
            "Lumbar degenerative instability",
            "분절 불안정성",
        ],
        "C1/2 facet joint asymmetry": [
            "Atlantoaxial facet asymmetry",
            "환축추 후관절 비대칭",
        ],
        "Lytic bone disease": [
            "Vertebral body osteolysis",
            "Osteolytic spine lesion",
            "Vertebral body destruction",
            "용해성 골질환",
        ],
        "Vertebral artery anomaly": [
            "Vertebral artery variant", "VA anomaly",
            "Anomalous vertebral artery",
            "추골동맥 기형",
        ],
        "Segmental motor paralysis": [
            "Motor weakness post-decompression",
            "Segmental motor deficit",
            "분절 운동 마비",
        ],
        "Lumbar central canal stenosis": [
            "Central stenosis (lumbar)",
            "Lumbar degenerative spinal stenosis",
            "요추 중심관 협착증",
        ],
        "Intervertebral disc disease": [
            "intervertebral disc disease",
            "Intervertebral disk space disease",
            "Lumbar intervertebral disc disease",
            "추간판 질환",
        ],
        "Craniovertebral junction disorder": [
            "Craniocervical junction abnormality",
            "CVJ disorder", "Irreducible AAD",
            "두개경추 접합부 질환",
        ],
        "Intraoperative contamination": [
            "Surgical wound contamination",
            "Intraoperative wound contamination",
            "수술 중 오염",
        ],
        "Spinal cord degeneration": [
            "Myelopathy progression",
            "spinal cord degeneration",
            "척수 퇴행",
        ],
        "Atlantoaxial Dislocation": [
            "atlantoaxial dislocation", "C1-C2 dislocation",
            "AAD", "환축추 탈구",
        ],
        "Psoas Abscess": [
            "psoas abscess", "Iliopsoas abscess",
            "장요근 농양",
        ],
        "Suspected Cauda Equina Syndrome": [
            "Suspected CES", "CES with normal MRI",
            "정상 MRI 소견의 마미증후군 의심",
        ],
        "Lumbar Facet Synovial Cyst": [
            "Lumbar facet cyst", "Lumbar juxta-articular cyst",
            "Lumbar juxtafacet cyst",
            "요추 후관절 활막낭종",
        ],

        # Cross-type aliases (Pathology SNOMED keys also in Outcome)
        "Heterotopic ossification": [
            "heterotopic ossification", "HO (pathology)",
        ],
        "Dural tear": [
            "dural tear", "Incidental durotomy (pathology)",
        ],
        "Cage subsidence": [
            "cage subsidence (pathology)",
        ],
        "Facet joint violation": [
            "facet joint violation (pathology)",
        ],
        "Cage migration": [
            "cage migration (pathology)",
        ],
        "C5 palsy": [
            "C5 palsy (pathology)", "C5 nerve palsy (pathology)",
        ],

        # v1.25.0: Adult Spinal Deformity removed (already alias of ASD)
        # v1.25.0: Proximal Junctional Kyphosis removed (already alias of PJK)

        # ========================================
        # v1.25.0: New SNOMED Concept Aliases (Gap C - Pathology)
        # ========================================
        "Rod Breakage": [
            "rod breakage", "Rod fracture", "Broken rod",
            "Spinal rod failure", "로드 파절",
        ],
        "Screw Pullout": [
            "screw pullout", "Screw loosening",
            "Screw migration", "Pedicle screw failure",
            "나사못 이탈",
        ],
        "Epidural Lipomatosis": [
            "epidural lipomatosis", "Epidural fat hypertrophy",
            "SEL", "Spinal lipomatosis",
            "경막외 지방종증",
        ],
        "Vertebral Hemangioma (Aggressive)": [
            "aggressive vertebral hemangioma",
            "Symptomatic vertebral hemangioma",
            "Compressive hemangioma",
            "공격적 척추 혈관종",
        ],
        "Dropped Head Syndrome": [
            "dropped head syndrome", "Chin-on-chest deformity",
            "Severe cervical kyphosis", "Head drop",
            "수하두 증후군",
        ],
        "Spinal Subdural Hematoma": [
            "spinal subdural hematoma", "SSDH",
            "Subdural hematoma of spine",
            "척추 경막하 혈종",
        ],
        "Implant Allergy": [
            "implant allergy", "Metal allergy",
            "Titanium allergy", "Nickel hypersensitivity",
            "임플란트 금속 알레르기",
        ],
        "Vertebral Endplate Degeneration": [
            "vertebral endplate degeneration",
            "Endplate erosion", "Endplate Modic changes",
            "Endplate signal changes", "추체 종판 퇴행",
        ],
        # v1.25.0: Proximal Junctional Failure removed as canonical (aliases merged into PJK)
        # v1.25.0: Distal Junctional Failure removed as canonical (aliases merged into DJK)

        # ========================================
        # IS_A hierarchy root/category nodes (QC-2026-004)
        # ========================================
        "Degenerative Spine Disease": [],  # IS_A root category
        "Spinal Deformity": [],  # IS_A root category
        "Spinal Trauma": [],  # IS_A root category
        "Spinal Neoplasm": ["Spinal neoplasm", "Spine tumor"],
        "Inflammatory Spine Disease": [],  # IS_A root category
        "Neurological Spine Condition": [],  # IS_A root category
        "Surgical Complication": ["surgical complication", "Postoperative complication"],
        "Spinal Pain Syndrome": [],  # IS_A root category
        "Congenital Spine Disorder": ["congenital spine disorder", "Congenital spinal anomaly"],
        "Metabolic Bone Disease": ["metabolic bone disease", "Metabolic bone disorder"],
        "Spinal Comorbidity": [],  # IS_A root category
        "Scoliosis (Category)": [],  # IS_A root category (parent of AIS, Adult, etc.)
        "Vertebral Fracture (Category)": [],  # IS_A root category
        # Note: "Distal Junctional Failure" SNOMED key covered by DJK aliases (last-write-wins safe)
        "Neurogenic claudication": [],  # SNOMED key variant (cf. Neurogenic Claudication)

        # ========================================
        # v1.25.0: SNOMED Orphan Sync (QC-2026-008) — Pathology
        # ========================================
        "Annulus Fibrosus Microdamage": [
            "annulus fibrosus microdamage", "Annular microdamage",
            "AF microdamage",
        ],
        "Apophyseal Ring Separation": [
            "apophyseal ring separation", "Ring apophysis separation",
            "Apophyseal ring fracture",
        ],
        "Breast Cancer Metastasis": [
            "breast cancer metastasis", "Breast cancer spine metastasis",
            "유방암 척추 전이",
        ],
        "Cartilage Degeneration": [
            "cartilage degeneration", "Cartilage degradation",
            "연골 퇴행",
        ],
        "Cervical Lordosis Loss": [
            "cervical lordosis loss", "Loss of cervical lordosis",
            "경추 전만 소실",
        ],
        "Conjoined Nerve Roots": [
            "conjoined nerve roots", "Conjoined nerve root",
            "Conjoined root anomaly",
        ],
        "Device Migration": [
            "device migration", "Implant migration",
            "Cage migration", "기기 이동",
        ],
        "Eosinophilic Granuloma": [
            "eosinophilic granuloma",
            "호산구성 육아종",
        ],
        "Facet Joint Pain": [
            "facet joint pain", "Facet pain",
            "Facet syndrome", "후관절 통증",
        ],
        "Kyphoscoliosis": [
            "kyphoscoliosis", "Kypho-scoliosis",
            "후만측만증",
        ],
        "Laminar Ossification": [
            "laminar ossification",
            "Ossification of lamina",
        ],
        "Langerhans Cell Histiocytosis": [
            "langerhans cell histiocytosis", "LCH",
            "Histiocytosis X", "랑게르한스세포 조직구증",
        ],
        "Ligamentum Flavum Calcification": [
            "ligamentum flavum calcification",
            "Calcified ligamentum flavum", "LF calcification",
            "황색인대 석회화",
        ],
        "Lumbar Lordosis Loss": [
            "lumbar lordosis loss", "요추 전만 소실",
        ],
        "Lumbar Spine Fracture": [
            "lumbar spine fracture", "Lumbar fracture",
            "Lumbar vertebral fracture", "요추 골절",
        ],
        "Nucleus Pulposus Degeneration": [
            "nucleus pulposus degeneration", "NP degeneration",
            "수핵 퇴행",
        ],
        "Osteolysis": [
            "osteolysis", "Bone resorption",
            "Peri-implant osteolysis", "골용해",
        ],
        "Paraspinal Sarcopenia": [
            "paraspinal sarcopenia", "척추주위근 감소증",
        ],
        "Prostate Cancer Metastasis": [
            "prostate cancer metastasis", "Prostate cancer spine metastasis",
            "전립선암 척추 전이",
        ],
        "Pseudomeningocele": [
            "pseudomeningocele", "Pseudo-meningocele",
            "가성수막류",
        ],
        "Renal Cancer Metastasis": [
            "renal cancer metastasis", "Renal cell carcinoma spine metastasis",
            "Kidney cancer spine metastasis", "신장암 척추 전이",
        ],
        "S1 Radiculopathy": [
            "S1 radiculopathy", "S1 nerve root compression",
            "S1 root pain",
        ],
        "Severe Rigid Kyphoscoliosis": [
            "severe rigid kyphoscoliosis",
            "Rigid kyphoscoliosis",
        ],
        "Subsidence": [
            "subsidence", "Cage subsidence",
            "Implant subsidence", "케이지 침강",
        ],
        "Thoracic Degenerative Pathology": [
            "thoracic degenerative pathology",
            "Thoracic degeneration", "흉추 퇴행성 질환",
        ],
        "Vertebral Fracture Due to Myeloma": [
            "vertebral fracture due to myeloma",
            "Myeloma vertebral fracture",
            "Multiple myeloma spine fracture",
            "골수종 척추 골절",
        ],
        # Note: These SNOMED keys are already reachable as aliases of other canonicals
        # (no need for separate canonical entries — would cause last-write-wins conflicts):
        # "Adult Spinal Deformity" → alias of ASD
        # "Disc Herniation" → alias of Lumbar Disc Herniation
        # "Distal Junctional Failure" → alias of DJK
        # "Nonunion" → alias of Pseudarthrosis
        # "PJF" → alias of PJK
        # "Proximal Junctional Failure" → alias of PJK
        # "Proximal Junctional Kyphosis" → alias of PJK
        # "Spinal Infection" → alias of Spondylodiscitis
        # "Spinal Stenosis" → alias of Lumbar Stenosis
    }

    # v1.16.1: 해부학 위치 별칭 (Anatomy Aliases)
    ANATOMY_ALIASES: dict[str, list[str]] = {
        # Regions
        "Cervical": ["C-spine", "cervical spine", "Cervical spine", "경추"],
        "Thoracic": ["T-spine", "thoracic spine", "Thoracic spine", "흉추"],
        "Lumbar": ["L-spine", "lumbar spine", "Lumbar spine", "요추"],
        "Sacral": ["sacral spine", "Sacral spine", "sacrum", "Sacrum", "천추"],
        "Lumbosacral": ["lumbosacral spine", "LS spine", "L-S spine", "요천추"],
        "Cervicothoracic": ["cervicothoracic junction", "CT junction", "CTJ", "경흉추"],
        "Thoracolumbar": ["thoracolumbar junction", "TL junction", "TLJ", "흉요추"],
        # Cervical levels
        "C1": ["Atlas", "atlas", "C1 vertebra", "first cervical vertebra"],
        "C2": ["Axis", "axis", "C2 vertebra", "second cervical vertebra"],
        "C3": ["C3 vertebra", "third cervical vertebra"],
        "C4": ["C4 vertebra", "fourth cervical vertebra"],
        "C5": ["C5 vertebra", "fifth cervical vertebra"],
        "C6": ["C6 vertebra", "sixth cervical vertebra"],
        "C7": ["C7 vertebra", "seventh cervical vertebra"],
        # Thoracic levels
        "T1": ["T1 vertebra", "first thoracic vertebra"],
        "T10": ["T10 vertebra", "tenth thoracic vertebra"],
        "T11": ["T11 vertebra", "eleventh thoracic vertebra"],
        "T12": ["T12 vertebra", "twelfth thoracic vertebra"],
        # Lumbar levels
        "L1": ["L1 vertebra", "first lumbar vertebra"],
        "L2": ["L2 vertebra", "second lumbar vertebra"],
        "L3": ["L3 vertebra", "third lumbar vertebra"],
        "L4": ["L4 vertebra", "fourth lumbar vertebra"],
        "L5": ["L5 vertebra", "fifth lumbar vertebra"],
        # Sacral levels
        "S1": ["S1 vertebra", "first sacral vertebra"],
        "S2": ["S2 vertebra", "second sacral vertebra"],
        # Segment levels (intervertebral disc)
        "L4-5": ["L4-L5", "L4/5", "L4/L5", "L4-L5 disc"],
        "L5-S1": ["L5/S1", "L5-S1 disc", "Lumbosacral disc"],
        "L3-4": ["L3-L4", "L3/4", "L3/L4", "L3-L4 disc"],
        "L2-3": ["L2-L3", "L2/3", "L2/L3", "L2-L3 disc"],
        "L1-2": ["L1-L2", "L1/2", "L1/L2", "L1-L2 disc"],
        "C3-4": ["C3-C4", "C3/4", "C3/C4", "C3-C4 disc"],
        "C4-5": ["C4-C5", "C4/5", "C4/C5", "C4-C5 disc"],
        "C5-6": ["C5-C6", "C5/6", "C5/C6", "C5-C6 disc"],
        "C6-7": ["C6-C7", "C6/7", "C6/C7", "C6-C7 disc"],
        "C7-T1": ["C7-T1 disc", "cervicothoracic disc"],
        "T11-12": ["T11-T12", "T11/12", "T11/T12"],
        "T12-L1": ["T12-L1 disc", "thoracolumbar disc"],
        # Missing thoracic levels
        "T2": ["T2 vertebra", "second thoracic vertebra", "D2", "D2 (T2)"],
        "T3": ["T3 vertebra", "third thoracic vertebra"],
        "T4": ["T4 vertebra", "fourth thoracic vertebra"],
        "T5": ["T5 vertebra", "fifth thoracic vertebra"],
        "T6": ["T6 vertebra", "sixth thoracic vertebra"],
        "T7": ["T7 vertebra", "seventh thoracic vertebra"],
        "T8": ["T8 vertebra", "eighth thoracic vertebra"],
        "T9": ["T9 vertebra", "ninth thoracic vertebra"],
        # Missing segments
        "C2-3": ["C2-C3", "C2/3", "C2/C3", "C2-C3 disc"],
        "T10-11": ["T10-T11", "T10/11", "T10/T11"],
        "T9-10": ["T9-T10", "T9/10", "T9/T10"],
        "L3-5": ["L3-L5", "L3/5", "L3-L4-L5"],
        "L4-S1": ["L4-L5-S1", "L4/S1", "L4-5-S1"],
        # Non-specific anatomy (인식하되 quality_flag 설정 대상)
        "Multi-level": [
            "Multiple levels", "Multilevel", "Multisegmental", "multi-level",
            # v1.20.2: "Mixed" and multi-segment variants
            "Mixed (not specified)", "Mixed/Multiple levels",
            "Multi-segmental (exact levels not specified)",
            "Multiple levels (not specified)", "Mixed levels",
            "C-spine and L-spine (multiple levels)",
            "Multiple spinal levels", "Various levels",
        ],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync (Anatomy)
        # ========================================
        # Thoracic disc segments (v1.19.2 SNOMED, missing from aliases)
        "T2-3": ["T2-T3", "T2/3", "T2/T3", "T2-T3 disc"],
        "T3-4": ["T3-T4", "T3/4", "T3/T4", "T3-T4 disc"],
        "T4-5": ["T4-T5", "T4/5", "T4/T5", "T4-T5 disc"],
        "T5-6": ["T5-T6", "T5/6", "T5/T6", "T5-T6 disc"],
        "T6-7": ["T6-T7", "T6/7", "T6/T7", "T6-T7 disc"],
        "T7-8": ["T7-T8", "T7/8", "T7/T8", "T7-T8 disc"],
        "T8-9": ["T8-T9", "T8/9", "T8/T9", "T8-T9 disc"],
        # Range / composite anatomy levels
        "Cervicosacral Spine": ["cervicosacral", "C-S spine", "Full spine"],
        "C2-C7": ["C2-7", "C2-C7 subaxial", "Subaxial cervical"],
        "Multi-level Vertebral": ["Multi-level vertebral", "Multiple vertebral levels"],

        # ========================================
        # v1.25.0: New SNOMED Concept Aliases (Gap C - Anatomy)
        # ========================================
        "Disc Space": [
            "disc space", "Intervertebral disc space",
            "Intervertebral space", "Disc height space",
            "추간판 공간",
        ],
        "Facet Joint": [
            "facet joint", "Zygapophyseal joint",
            "Zygapophysial joint", "Articular facet",
            "후관절",
        ],
        "Neural Foramen": [
            "neural foramen", "Neuroforamen",
            "Intervertebral foramen", "추간공",
        ],
        "Spinal Canal": [
            "spinal canal", "Central canal",
            "Vertebral canal", "척추관",
        ],
        "Thecal Sac": [
            "thecal sac", "Dural sac",
            "Dural tube", "경막낭",
        ],

        # ========================================
        # IS_A hierarchy root/category nodes (QC-2026-004)
        # ========================================
        "Spine": ["spine", "Spinal column", "Vertebral column", "척추"],

        # ========================================
        # v1.25.0: SNOMED Orphan Sync (QC-2026-008) — Anatomy
        # ========================================
        "Coccyx": ["coccyx", "Coccygeal", "Tailbone", "미추", "미골"],
        "Pelvis": ["pelvis", "Pelvic", "Pelvic bone", "골반"],
    }

    # v1.20.2: Anatomy terms that indicate non-specified/vague location
    # These return low confidence (0.1) to signal the caller
    _ANATOMY_VAGUE_TERMS = {
        "not specified", "not applicable", "not specifically specified",
        "not specifically stated", "not explicitly specified in provided text",
        "not explicitly specified", "not mentioned", "not reported",
        "unspecified", "n/a", "na", "none", "unknown",
        "not-applicable", "not stated", "single-level", "spinal",
        "not specified in text",
    }

    # Placeholder patterns for all entity types (import-time filtering)
    _PLACEHOLDER_RE = re.compile(
        r"(?i)^(not\s+(specified|applicable|explicitly|specifically|stated)|"
        r"not-applicable|unspecified|n/?a$|none$|unknown$)",
    )

    # 한국어 조사 (Korean particles) - 정규화 시 제거할 조사들
    KOREAN_PARTICLES = {
        "가", "이", "를", "을", "에", "의", "와", "과", "으로", "로",
        "에서", "에게", "한테", "께", "도", "만", "부터", "까지", "조차",
        "마저", "라도", "나마", "이나", "나", "든지", "이든지", "야", "이야"
    }

    # 한국어 해부학 용어 (Korean anatomy terms)
    ANATOMY_KOREAN = {
        "경추": "Cervical",
        "흉추": "Thoracic",
        "요추": "Lumbar",
        "천추": "Sacral",
        "미추": "Coccygeal",
    }

    def __init__(self):
        """초기화."""
        # 역방향 매핑 구축 (빠른 조회용)
        self._intervention_reverse = self._build_reverse_map(self.INTERVENTION_ALIASES)
        self._outcome_reverse = self._build_reverse_map(self.OUTCOME_ALIASES)
        self._pathology_reverse = self._build_reverse_map(self.PATHOLOGY_ALIASES)
        self._anatomy_reverse = self._build_reverse_map(self.ANATOMY_ALIASES)

        # Unregistered term tracking (v1.24.0 ontology evolution)
        self._unregistered_terms: list[dict] = []
        self._unregistered_lock = threading.Lock()
        self._unregistered_max_size = 500  # CA-NEW-004: prevent unbounded growth

        # 한국어 감지 패턴
        self._korean_pattern = re.compile(r'[\uac00-\ud7af]+')  # 한글 유니코드 범위

        # Load configuration thresholds
        if CONFIG_AVAILABLE:
            try:
                config = get_normalization_config()
                self.fuzzy_threshold = config.fuzzy_threshold
                self.token_overlap_threshold = config.token_overlap_threshold
                self.word_boundary_confidence = config.word_boundary_confidence
                self.partial_match_threshold = config.partial_match_threshold
                self.enable_korean_normalization = config.enable_korean_normalization
                self.strip_particles = config.strip_particles
                logger.info(f"EntityNormalizer initialized with config: fuzzy={self.fuzzy_threshold}, token={self.token_overlap_threshold}")
            except Exception as e:
                logger.warning(f"Failed to load config, using defaults: {e}")
                self._set_default_thresholds()
        else:
            logger.info("Config system not available, using default thresholds")
            self._set_default_thresholds()

    def _set_default_thresholds(self):
        """Set default threshold values (fallback when config is unavailable)."""
        self.fuzzy_threshold = 0.85
        self.token_overlap_threshold = 0.8
        self.word_boundary_confidence = 0.95
        self.partial_match_threshold = 0.5
        self.enable_korean_normalization = True
        self.strip_particles = True

    def _record_unregistered_term(
        self,
        original_text: str,
        entity_type: str,
        source_paper: str = "",
        attempted_normalizations: list[str] | None = None,
    ) -> None:
        """Record a term that failed normalization for ontology evolution.

        Thread-safe collection of terms not found in any alias dictionary
        or SNOMED mapping. Used by SNOMEDProposer for LLM-based mapping
        proposals.

        Args:
            original_text: The original term text that failed normalization
            entity_type: Entity type (intervention, pathology, outcome, anatomy)
            source_paper: Optional paper_id where the term was found
            attempted_normalizations: Methods tried during normalization
        """
        if not original_text or len(original_text.strip()) < 2:
            return

        entry = {
            "original_text": original_text.strip(),
            "entity_type": entity_type,
            "source_papers": [source_paper] if source_paper else [],
            "attempted_normalizations": attempted_normalizations or [],
        }

        with self._unregistered_lock:
            # Avoid duplicates (same text + entity_type)
            for existing in self._unregistered_terms:
                if (existing["original_text"].lower() == entry["original_text"].lower()
                        and existing["entity_type"] == entry["entity_type"]):
                    # Update source_papers if new
                    if source_paper and source_paper not in existing.get("source_papers", []):
                        existing.setdefault("source_papers", []).append(source_paper)
                    return
            # CA-NEW-004: enforce max size to prevent unbounded growth
            if len(self._unregistered_terms) >= self._unregistered_max_size:
                logger.warning(
                    f"Unregistered terms list reached max size ({self._unregistered_max_size}), "
                    f"dropping oldest entry"
                )
                self._unregistered_terms.pop(0)
            self._unregistered_terms.append(entry)

    def get_unregistered_terms(self) -> list[dict]:
        """Return collected unregistered terms with metadata.

        Returns:
            List of dicts with keys:
                - original_text: str
                - entity_type: str
                - source_paper: str
                - attempted_normalizations: list[str]
        """
        with self._unregistered_lock:
            return list(self._unregistered_terms)

    def clear_unregistered_terms(self) -> int:
        """Reset the unregistered term collection.

        Returns:
            Number of terms cleared
        """
        with self._unregistered_lock:
            count = len(self._unregistered_terms)
            self._unregistered_terms.clear()
            return count

    async def propose_snomed_for_unregistered(self, llm_client=None) -> list[dict]:
        """Propose SNOMED mappings for collected unregistered terms.

        Calls SNOMEDProposer.batch_propose() with the current unregistered terms.
        Returns proposals for manual review or auto-apply.

        Args:
            llm_client: Optional LLM client for SNOMEDProposer.
                If None, SNOMEDProposer will create its own.

        Returns:
            List of proposal dicts with keys: original_term, proposed_term,
            proposed_code, parent_code, confidence, auto_apply, reasoning.
        """
        terms = self.get_unregistered_terms()
        if not terms:
            return []

        try:
            from ontology.snomed_proposer import SNOMEDProposer
        except ImportError:
            logger.warning("SNOMEDProposer not available; cannot propose SNOMED mappings")
            return []

        proposer = SNOMEDProposer(llm_client=llm_client)
        proposals = await proposer.batch_propose(terms)

        return [
            {
                "original_term": p.original_term,
                "proposed_term": p.proposed_term,
                "proposed_code": p.proposed_code,
                "parent_code": p.proposed_parent_code,
                "confidence": p.confidence,
                "auto_apply": p.auto_apply,
                "reasoning": p.reasoning,
            }
            for p in proposals
        ]

    def register_dynamic_alias(
        self,
        entity_type: str,
        alias: str,
        canonical: str,
    ) -> bool:
        """런타임에 새 alias를 reverse_map에 등록 (thread-safe).

        메모리 전용 — 재시작 시 초기화됨.
        canonical이 기존 ALIASES 딕셔너리에 존재해야만 등록 가능.

        Args:
            entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
            alias: 새로 등록할 alias 문자열
            canonical: 매핑 대상 canonical 이름 (ALIASES에 존재해야 함)

        Returns:
            True if registered, False if rejected (중복/invalid canonical)
        """
        reverse_map_key = f"_{entity_type}_reverse"
        aliases_dict_key = f"{entity_type.upper()}_ALIASES"

        reverse_map = getattr(self, reverse_map_key, None)
        aliases_dict = getattr(self, aliases_dict_key, None)

        if reverse_map is None or aliases_dict is None:
            return False

        alias_lower = alias.lower().strip()

        # 이미 등록된 alias
        if alias_lower in reverse_map:
            return False

        # canonical이 ALIASES에 없으면 거부 (안전장치)
        if canonical not in aliases_dict:
            logger.warning(
                f"Dynamic alias rejected: '{canonical}' not in {entity_type} ALIASES"
            )
            return False

        # thread-safe 등록 (dict assignment는 Python GIL 하에서 atomic)
        reverse_map[alias_lower] = canonical
        logger.info(f"Dynamic alias: '{alias}' → '{canonical}' ({entity_type})")
        return True

    def _get_candidate_canonicals(
        self,
        text: str,
        entity_type: str,
        top_k: int = 30,
    ) -> list[str]:
        """rapidfuzz로 상위 top_k 후보 canonical names 빠르게 필터링.

        LLM 프롬프트에 포함할 후보 목록을 최소화하여 비용/정확도 최적화.

        Args:
            text: 매칭 실패한 원본 텍스트
            entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
            top_k: 반환할 최대 후보 수

        Returns:
            similarity 순 정렬된 canonical name 목록
        """
        aliases_dict = {
            "intervention": self.INTERVENTION_ALIASES,
            "outcome": self.OUTCOME_ALIASES,
            "pathology": self.PATHOLOGY_ALIASES,
            "anatomy": self.ANATOMY_ALIASES,
        }.get(entity_type, {})

        canonicals = list(aliases_dict.keys())
        if not canonicals:
            return []

        # rapidfuzz WRatio: 다양한 비율 메트릭 중 최선 자동 선택
        lower_to_original = {c.lower(): c for c in canonicals}
        results = process.extract(
            text.lower(),
            list(lower_to_original.keys()),
            scorer=fuzz.WRatio,
            limit=top_k,
        )

        return [lower_to_original[r[0]] for r in results if r[1] > 30]

    def _build_reverse_map(self, aliases: dict[str, list[str]]) -> dict[str, str]:
        """역방향 매핑 구축."""
        reverse = {}
        for canonical, alias_list in aliases.items():
            # 정규화된 이름도 자기 자신에 매핑
            reverse[canonical.lower()] = canonical
            for alias in alias_list:
                reverse[alias.lower()] = canonical
        return reverse

    def _strip_korean_particles(self, text: str) -> str:
        """한국어 조사 제거.

        Args:
            text: 입력 텍스트

        Returns:
            조사가 제거된 텍스트
        """
        # 텍스트 끝의 조사만 제거 (단어 중간의 조사는 보존)
        for particle in sorted(self.KOREAN_PARTICLES, key=len, reverse=True):
            if text.endswith(particle):
                return text[:-len(particle)]
        return text

    def _contains_korean(self, text: str) -> bool:
        """한국어 포함 여부 확인.

        Args:
            text: 입력 텍스트

        Returns:
            한국어 포함 여부
        """
        return bool(self._korean_pattern.search(text))

    def _normalize_token(self, token: str) -> str:
        """토큰 정규화 (공백 제거, 소문자 변환, 특수문자 제거).

        Args:
            token: 정규화할 토큰

        Returns:
            정규화된 토큰
        """
        # 소문자 변환
        token = token.lower()
        # 하이픈/언더스코어 제거 (MIS-TLIF → MISTLIF)
        token = token.replace("-", "").replace("_", "")
        # 앞뒤 공백 제거
        token = token.strip()
        return token

    def _create_search_pattern(self, term: str, text: str) -> re.Pattern:
        """검색 패턴 생성 (한국어/영어 구분).

        Args:
            term: 검색할 용어
            text: 검색 대상 텍스트

        Returns:
            정규표현식 패턴
        """
        escaped_term = re.escape(term)

        # 한국어 포함 용어는 단어 경계 없이 검색
        if self._contains_korean(term):
            # 한국어는 조사가 붙을 수 있으므로 앞뒤로 다른 문자가 있어도 매칭
            return re.compile(escaped_term, re.IGNORECASE)
        else:
            # 영어는 단어 경계 사용 (기존 방식)
            return re.compile(r'\b' + escaped_term + r'\b', re.IGNORECASE)

    def _token_match(
        self,
        text: str,
        reverse_map: dict[str, str],
        aliases_dict: dict[str, list[str]]
    ) -> Optional[NormalizationResult]:
        """토큰 기반 매칭 (단어 순서 무관).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            aliases_dict: 별칭 딕셔너리

        Returns:
            NormalizationResult 또는 None
        """
        # 입력 텍스트를 토큰으로 분해
        input_tokens = set(self._normalize_token(t) for t in text.split() if t.strip())

        best_match = None
        best_overlap = 0.0

        for canonical, aliases in aliases_dict.items():
            # 정규화된 이름과 모든 별칭 확인
            all_terms = [canonical] + aliases

            for term in all_terms:
                term_tokens = set(self._normalize_token(t) for t in term.split() if t.strip())

                # 토큰 교집합 비율 계산
                if not input_tokens or not term_tokens:
                    continue

                overlap = len(input_tokens & term_tokens) / max(len(input_tokens), len(term_tokens))

                # token_overlap_threshold 이상 겹치면 매칭으로 간주
                if overlap >= self.token_overlap_threshold and overlap > best_overlap:
                    best_overlap = overlap
                    best_match = (canonical, term, overlap)

        if best_match:
            canonical, matched_term, overlap = best_match
            # 신뢰도: 0.9 + 0.1 * overlap (0.9~1.0)
            confidence = 0.9 + 0.1 * overlap
            return NormalizationResult(
                original=text,
                normalized=canonical,
                confidence=confidence,
                matched_alias=matched_term,
                method="token"
            )

        return None

    def _fuzzy_match(
        self,
        text: str,
        reverse_map: dict[str, str],
        threshold: float = 0.85
    ) -> Optional[NormalizationResult]:
        """퍼지 매칭 (Edit Distance 기반).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            threshold: 최소 유사도 (0.85 = 85%)

        Returns:
            NormalizationResult 또는 None
        """
        # 모든 별칭 수집 (정규화된 이름 + 별칭)
        all_terms = list(reverse_map.keys())

        if not all_terms:
            return None

        # rapidfuzz를 사용한 가장 유사한 항목 찾기
        # scorer: fuzz.ratio (0-100), fuzz.token_sort_ratio, fuzz.partial_ratio 등 사용 가능
        result = process.extractOne(
            text.lower(),
            all_terms,
            scorer=fuzz.ratio,
            score_cutoff=threshold * 100  # 85% → 85
        )

        if result:
            matched_alias, score, _ = result
            canonical = reverse_map[matched_alias]

            # 신뢰도: score / 100 (0.85~1.0)
            return NormalizationResult(
                original=text,
                normalized=canonical,
                confidence=score / 100.0,
                matched_alias=matched_alias,
                method="fuzzy"
            )

        return None

    def normalize_intervention(self, text: str) -> NormalizationResult:
        """수술법 정규화 (SNOMED 코드 포함).

        Args:
            text: 입력 텍스트

        Returns:
            NormalizationResult (category, snomed_code, snomed_term 포함)
        """
        result = self._normalize(
            text,
            self._intervention_reverse,
            "intervention",
            self.INTERVENTION_ALIASES
        )
        # 정규화된 이름에 해당하는 category 추가
        if result.normalized in self.INTERVENTION_CATEGORIES:
            result.category = self.INTERVENTION_CATEGORIES[result.normalized]
        # SNOMED 코드 추가
        return self._enrich_with_snomed(result, "intervention")

    # v1.19.5: Outcome 한정어 패턴 (비교군, 저자명, 서브그룹 등)
    _OUTCOME_QUALIFIER_RE = re.compile(
        r'\s*\([^)]*\)\s*$',
        re.IGNORECASE
    )
    _OUTCOME_DASH_QUALIFIER_RE = re.compile(
        r'\s+[-–—]\s+.+$',
        re.IGNORECASE
    )
    _OUTCOME_TRAILING_GENERIC_RE = re.compile(
        r'\s+(?:incidence|prevalence|occurrence)\s*$|'
        r'\s+(?:for|in|during|after|following|reduction)\s+\w.*$',
        re.IGNORECASE
    )

    def _strip_outcome_qualifiers(self, text: str) -> str:
        """Outcome 이름에서 비교군/저자/서브그룹 한정어 제거.

        Examples:
            "Blood loss (XLIF vs TLIF)" → "Blood loss"
            "Complication rate - UBE-TLIF mastery phase" → "Complication rate"
            "Rod Fracture incidence" → "Rod Fracture"
        """
        stripped = text.strip()
        # 1) 괄호 한정어: "(XLIF vs TLIF)", "(CKD vs Non-CKD)"
        stripped = self._OUTCOME_QUALIFIER_RE.sub('', stripped).strip()
        # 2) 대시 한정어: "- Kim et al.", "- mastery phase"
        stripped = self._OUTCOME_DASH_QUALIFIER_RE.sub('', stripped).strip()
        # 3) 후행 generic 용어: "incidence", "prevalence"
        stripped = self._OUTCOME_TRAILING_GENERIC_RE.sub('', stripped).strip()
        return stripped if stripped else text

    def normalize_outcome(self, text: str) -> NormalizationResult:
        """결과변수 정규화 (SNOMED 코드 포함).

        v1.19.5: 한정어 스트리핑 전처리 추가 — 원본 매칭 실패 시
        한정어를 제거한 텍스트로 재시도.
        """
        # 1차: 원본 텍스트로 정규화 시도
        result = self._normalize(
            text,
            self._outcome_reverse,
            "outcome",
            self.OUTCOME_ALIASES
        )
        if result.confidence > 0:
            return self._enrich_with_snomed(result, "outcome")

        # 2차: 한정어 스트리핑 후 재시도
        stripped = self._strip_outcome_qualifiers(text)
        if stripped != text:
            result = self._normalize(
                stripped,
                self._outcome_reverse,
                "outcome",
                self.OUTCOME_ALIASES
            )
            if result.confidence > 0:
                # 원본 텍스트 기록, confidence 약간 감소
                result.original = text
                result.confidence = max(result.confidence * 0.9, 0.5)
                result.method = f"qualifier_stripped+{result.method}"
                return self._enrich_with_snomed(result, "outcome")

        # 매칭 실패 → 원본 반환
        return self._enrich_with_snomed(
            NormalizationResult(original=text, normalized=text, confidence=0.0, method="none"),
            "outcome"
        )

    def normalize_pathology(self, text: str) -> NormalizationResult:
        """질환명 정규화 (SNOMED 코드 포함)."""
        result = self._normalize(
            text,
            self._pathology_reverse,
            "pathology",
            self.PATHOLOGY_ALIASES
        )
        return self._enrich_with_snomed(result, "pathology")

    def normalize_anatomy(self, text: str) -> NormalizationResult:
        """해부학 위치 정규화 (SNOMED 코드 포함).

        v1.16.1: ANATOMY_ALIASES 기반 정규화 추가.
        v1.20.2: vague/non-specified anatomy terms → low confidence.

        Args:
            text: 입력 텍스트 (예: "L-spine", "C5-C6", "요추")

        Returns:
            NormalizationResult (snomed_code, snomed_term 포함)
        """
        # 한국어 해부학 용어 변환 (우선)
        stripped = text.strip()

        # v1.20.2+: Vague/non-specified terms → confidence 0 (skip at import)
        if stripped.lower() in self._ANATOMY_VAGUE_TERMS or self._PLACEHOLDER_RE.match(stripped):
            return NormalizationResult(
                original=text,
                normalized=text,
                confidence=0.0,
                method="vague_term"
            )

        if stripped in self.ANATOMY_KOREAN:
            stripped = self.ANATOMY_KOREAN[stripped]

        result = self._normalize(
            stripped,
            self._anatomy_reverse,
            "anatomy",
            self.ANATOMY_ALIASES
        )
        return self._enrich_with_snomed(result, "anatomy")

    def _normalize(
        self,
        text: str,
        reverse_map: dict[str, str],
        entity_type: str,
        aliases_dict: dict[str, list[str]]
    ) -> NormalizationResult:
        """내부 정규화 로직 (3단계: Exact → Token → Fuzzy).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            entity_type: 엔티티 유형
            aliases_dict: 별칭 딕셔너리

        Returns:
            NormalizationResult
        """
        if not text:
            return NormalizationResult(
                original=text,
                normalized=text,
                confidence=0.0,
                method="none"
            )

        # ═══════════════════════════════════════════════════
        # Stage 1: EXACT MATCH (confidence=1.0)
        # ═══════════════════════════════════════════════════
        text_lower = text.lower().strip()
        if text_lower in reverse_map:
            return NormalizationResult(
                original=text,
                normalized=reverse_map[text_lower],
                confidence=1.0,
                matched_alias=text,
                method="exact"
            )

        # 한국어 조사 제거 후 재시도
        text_without_particles = self._strip_korean_particles(text_lower)
        if text_without_particles != text_lower and text_without_particles in reverse_map:
            return NormalizationResult(
                original=text,
                normalized=reverse_map[text_without_particles],
                confidence=0.95,  # 조사 제거 후 매칭은 약간 낮은 신뢰도
                matched_alias=text_without_particles,
                method="exact"
            )

        # ═══════════════════════════════════════════════════
        # Stage 2: TOKEN-BASED MATCH (confidence=0.9+)
        # ═══════════════════════════════════════════════════
        token_result = self._token_match(text_lower, reverse_map, aliases_dict)
        if token_result:
            logger.debug(f"Token match: {text} → {token_result.normalized} (conf: {token_result.confidence:.2f})")
            return token_result

        # ═══════════════════════════════════════════════════
        # Stage 3: WORD BOUNDARY MATCH (confidence=0.95)
        # "OLIF surgery" → OLIF (canonical found as complete word)
        # ═══════════════════════════════════════════════════
        words = set(re.split(r'[\s\-_/]+', text_lower))
        for canonical in aliases_dict.keys():
            canonical_lower = canonical.lower()
            if canonical_lower in words:
                return NormalizationResult(
                    original=text,
                    normalized=canonical,
                    confidence=self.word_boundary_confidence,
                    matched_alias=canonical_lower,
                    method="word_boundary"
                )

        # ═══════════════════════════════════════════════════
        # Stage 4: FUZZY MATCH (confidence based on config)
        # ═══════════════════════════════════════════════════
        fuzzy_result = self._fuzzy_match(text_lower, reverse_map, threshold=self.fuzzy_threshold)
        if fuzzy_result:
            logger.debug(f"Fuzzy match: {text} → {fuzzy_result.normalized} (conf: {fuzzy_result.confidence:.2f})")
            return fuzzy_result

        # ═══════════════════════════════════════════════════
        # Stage 5: PARTIAL MATCH (Fallback, confidence=0.5+)
        # ═══════════════════════════════════════════════════
        best_match = None
        best_confidence = 0.0

        for alias_lower, canonical in reverse_map.items():
            # 포함 관계 확인
            if alias_lower in text_lower or text_lower in alias_lower:
                # 길이 비율로 신뢰도 계산
                ratio = min(len(text_lower), len(alias_lower)) / max(len(text_lower), len(alias_lower))
                if ratio > best_confidence:
                    best_confidence = ratio
                    best_match = (alias_lower, canonical)

            # 조사 제거 후 포함 관계 확인
            text_stripped = self._strip_korean_particles(text_lower)
            if text_stripped != text_lower:
                if alias_lower in text_stripped or text_stripped in alias_lower:
                    ratio = min(len(text_stripped), len(alias_lower)) / max(len(text_stripped), len(alias_lower))
                    if ratio > best_confidence:
                        best_confidence = ratio * 0.95  # 조사 제거 후 매칭은 약간 낮은 신뢰도
                        best_match = (alias_lower, canonical)

        if best_match and best_confidence > self.partial_match_threshold:
            return NormalizationResult(
                original=text,
                normalized=best_match[1],
                confidence=best_confidence,
                matched_alias=best_match[0],
                method="partial"
            )

        # ═══════════════════════════════════════════════════
        # NO MATCH - 원본 반환 + 미등록 용어 기록
        # ═══════════════════════════════════════════════════
        logger.debug(f"No {entity_type} match found for: {text}")
        self._record_unregistered_term(
            text, entity_type,
            attempted_normalizations=["exact", "token", "word_boundary", "fuzzy", "partial"],
        )
        return NormalizationResult(
            original=text,
            normalized=text,
            confidence=0.0,
            method="none"
        )

    def normalize_all(self, text: str) -> dict[str, NormalizationResult]:
        """모든 유형에 대해 정규화 시도.

        Args:
            text: 입력 텍스트

        Returns:
            유형별 정규화 결과
        """
        return {
            "intervention": self.normalize_intervention(text),
            "outcome": self.normalize_outcome(text),
            "pathology": self.normalize_pathology(text),
        }

    def extract_and_normalize_interventions(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 수술법 추출 및 정규화.

        Args:
            text: 입력 텍스트 (논문 제목이나 초록)

        Returns:
            발견된 수술법 목록
        """
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._intervention_reverse.items():
            # 이미 찾은 정규화 이름은 건너뜀
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)
                continue

            # 한국어 조사가 붙은 경우 확인 (영어 약어에 조사가 붙은 경우)
            if not self._contains_korean(alias_lower):
                # 영어 약어 뒤에 한국어 조사가 올 수 있음 (예: TLIF가, OLIF와)
                for particle in self.KOREAN_PARTICLES:
                    particle_pattern = re.compile(
                        re.escape(alias_lower) + re.escape(particle),
                        re.IGNORECASE
                    )
                    match = particle_pattern.search(text_lower)
                    if match:
                        results.append(NormalizationResult(
                            original=match.group(0),
                            normalized=canonical,
                            confidence=0.95,  # 조사가 붙은 경우 약간 낮은 신뢰도
                            matched_alias=alias_lower
                        ))
                        found_canonicals.add(canonical)
                        break

        return results

    def extract_and_normalize_outcomes(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 결과변수 추출 및 정규화."""
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._outcome_reverse.items():
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)

        return results

    def extract_and_normalize_pathologies(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 질환명 추출 및 정규화.

        Args:
            text: 입력 텍스트

        Returns:
            발견된 질환명 목록
        """
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._pathology_reverse.items():
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)
                continue

            # 한국어 조사가 붙은 경우 확인
            if not self._contains_korean(alias_lower):
                for particle in self.KOREAN_PARTICLES:
                    particle_pattern = re.compile(
                        re.escape(alias_lower) + re.escape(particle),
                        re.IGNORECASE
                    )
                    match = particle_pattern.search(text_lower)
                    if match:
                        results.append(NormalizationResult(
                            original=match.group(0),
                            normalized=canonical,
                            confidence=0.95,
                            matched_alias=alias_lower
                        ))
                        found_canonicals.add(canonical)
                        break

        return results

    def get_all_aliases(self, canonical_name: str, entity_type: str = "intervention") -> list[str]:
        """정규화된 이름의 모든 별칭 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            별칭 목록
        """
        if entity_type == "intervention":
            aliases_map = self.INTERVENTION_ALIASES
        elif entity_type == "outcome":
            aliases_map = self.OUTCOME_ALIASES
        elif entity_type == "pathology":
            aliases_map = self.PATHOLOGY_ALIASES
        else:
            return []

        return aliases_map.get(canonical_name, [])

    def _enrich_with_snomed(
        self,
        result: NormalizationResult,
        entity_type: str
    ) -> NormalizationResult:
        """정규화 결과에 SNOMED 코드 추가.

        정규화 성공 시 normalized 이름으로 SNOMED 조회.
        정규화 실패 시(confidence=0)에도 원본 텍스트로 SNOMED 직접 조회 시도.
        (_search_mapping은 exact/case-insensitive/synonym/abbreviation 매칭 지원)

        Args:
            result: 정규화 결과
            entity_type: 엔티티 유형 ("intervention", "pathology", "outcome", "anatomy")

        Returns:
            SNOMED 코드가 추가된 결과
        """
        if not SNOMED_AVAILABLE:
            return result

        if not result.normalized and not result.original:
            return result

        snomed_fn = {
            "intervention": get_snomed_for_intervention,
            "pathology": get_snomed_for_pathology,
            "outcome": get_snomed_for_outcome,
            "anatomy": get_snomed_for_anatomy,
        }.get(entity_type)

        if not snomed_fn:
            return result

        mapping = None

        # 1차: normalized 이름으로 SNOMED 조회
        if result.confidence > 0.0 and result.normalized:
            mapping = snomed_fn(result.normalized)

        # 2차: 실패 시 원본 텍스트로 직접 SNOMED 조회 (synonym/abbreviation 매칭)
        if not mapping and result.original:
            mapping = snomed_fn(result.original)

        if mapping:
            result.snomed_code = mapping.code
            result.snomed_term = mapping.term
            result.parent_code = mapping.parent_code or ""
            result.semantic_type = mapping.semantic_type.value if mapping.semantic_type else ""

        return result

    def get_snomed_code(self, canonical_name: str, entity_type: str = "intervention") -> Optional[str]:
        """정규화된 이름의 SNOMED 코드 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            SNOMED 코드 또는 None
        """
        if not SNOMED_AVAILABLE:
            return None

        mapping = None
        if entity_type == "intervention" and get_snomed_for_intervention:
            mapping = get_snomed_for_intervention(canonical_name)
        elif entity_type == "pathology" and get_snomed_for_pathology:
            mapping = get_snomed_for_pathology(canonical_name)
        elif entity_type == "outcome" and get_snomed_for_outcome:
            mapping = get_snomed_for_outcome(canonical_name)
        elif entity_type == "anatomy" and get_snomed_for_anatomy:
            mapping = get_snomed_for_anatomy(canonical_name)

        return mapping.code if mapping else None

    def get_snomed_mapping(self, canonical_name: str, entity_type: str = "intervention"):
        """정규화된 이름의 전체 SNOMED 매핑 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            SNOMEDMapping 객체 또는 None
        """
        if not SNOMED_AVAILABLE:
            return None

        if entity_type == "intervention" and get_snomed_for_intervention:
            return get_snomed_for_intervention(canonical_name)
        elif entity_type == "pathology" and get_snomed_for_pathology:
            return get_snomed_for_pathology(canonical_name)
        elif entity_type == "outcome" and get_snomed_for_outcome:
            return get_snomed_for_outcome(canonical_name)
        elif entity_type == "anatomy" and get_snomed_for_anatomy:
            return get_snomed_for_anatomy(canonical_name)

        return None

    def normalize_intervention_with_snomed(self, text: str) -> NormalizationResult:
        """수술법 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_intervention(text)
        return self._enrich_with_snomed(result, "intervention")

    def normalize_pathology_with_snomed(self, text: str) -> NormalizationResult:
        """질환명 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_pathology(text)
        return self._enrich_with_snomed(result, "pathology")

    def normalize_outcome_with_snomed(self, text: str) -> NormalizationResult:
        """결과변수 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_outcome(text)
        return self._enrich_with_snomed(result, "outcome")

    def normalize_with_hierarchy_fallback(
        self,
        text: str,
        entity_type: str,
    ) -> NormalizationResult:
        """Hierarchy-aware normalization with parent concept fallback.

        When direct normalization fails, tries to match against SNOMED
        hierarchy by progressively simplifying the term.
        Example: "L4-5 stenosis" -> try "Lumbar Stenosis" -> parent: "Spinal Stenosis"

        Args:
            text: Input text to normalize
            entity_type: Entity type ("intervention", "pathology", "outcome", "anatomy")

        Returns:
            NormalizationResult with best match (may include parent info)
        """
        # 1. Direct normalization
        normalize_fn = getattr(self, f"normalize_{entity_type}", None)
        if not normalize_fn:
            return NormalizationResult(original=text, normalized=text, confidence=0.0, method="none")

        result = normalize_fn(text)
        if result.confidence > 0.0:
            return result

        if not SNOMED_AVAILABLE:
            return result

        # 2. Try simplified variants for hierarchy-based matching
        simplified_terms = self._generate_simplified_terms(text, entity_type)

        for simplified in simplified_terms:
            if simplified == text:
                continue
            alt_result = normalize_fn(simplified)
            if alt_result.confidence > 0.0:
                # Found a match via simplification
                alt_result.original = text
                alt_result.confidence = max(alt_result.confidence * 0.85, 0.5)
                alt_result.method = f"hierarchy_fallback+{alt_result.method}"
                return alt_result

        return result

    def _generate_simplified_terms(self, text: str, entity_type: str) -> list[str]:
        """Generate simplified term variants for hierarchy-based matching.

        Strips level-specific prefixes and qualifiers to find broader concepts.
        Example: "L4-5 stenosis" -> ["Lumbar Stenosis", "Spinal Stenosis"]

        Args:
            text: Original term text
            entity_type: Entity type for context-aware simplification

        Returns:
            List of simplified term candidates (most specific first)
        """
        simplified: list[str] = []
        text_lower = text.lower().strip()

        if entity_type == "pathology":
            # Strip level-specific prefixes: "L4-5 stenosis" -> "Lumbar Stenosis"
            level_pattern = re.compile(
                r'^(?:L\d[-–](?:L?\d|S\d)|C\d[-–]C?\d|T\d+[-–]T?\d+)\s+',
                re.IGNORECASE
            )
            stripped = level_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                # Determine region from the level prefix
                if re.match(r'L\d', text, re.IGNORECASE):
                    simplified.append(f"Lumbar {stripped.title()}")
                elif re.match(r'C\d', text, re.IGNORECASE):
                    simplified.append(f"Cervical {stripped.title()}")
                elif re.match(r'T\d', text, re.IGNORECASE):
                    simplified.append(f"Thoracic {stripped.title()}")
                simplified.append(f"Spinal {stripped.title()}")

            # Strip "lumbar/cervical/thoracic" to get generic form
            region_pattern = re.compile(
                r'^(?:lumbar|cervical|thoracic|thoracolumbar|lumbosacral)\s+',
                re.IGNORECASE
            )
            generic = region_pattern.sub('', text).strip()
            if generic and generic.lower() != text_lower:
                simplified.append(f"Spinal {generic.title()}")

        elif entity_type == "outcome":
            # Strip sub-measure qualifiers: "VAS Back" -> "VAS", "ODI Score" -> "ODI"
            qualifier_pattern = re.compile(
                r'\s+(?:back|leg|neck|arm|score|index|total|overall)$',
                re.IGNORECASE
            )
            stripped = qualifier_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                simplified.append(stripped)

        elif entity_type == "anatomy":
            # Strip level-specific info: "L4-L5 Disc" -> "Lumbar Disc"
            level_pattern = re.compile(
                r'^(?:L\d[-–](?:L?\d|S\d)|C\d[-–]C?\d|T\d+[-–]T?\d+)\s+',
                re.IGNORECASE
            )
            stripped = level_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                if re.match(r'L\d', text, re.IGNORECASE):
                    simplified.append(f"Lumbar {stripped.title()}")
                elif re.match(r'C\d', text, re.IGNORECASE):
                    simplified.append(f"Cervical {stripped.title()}")

        return simplified

    def normalize_all_with_snomed(self, text: str) -> dict[str, NormalizationResult]:
        """모든 유형에 대해 정규화 시도 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            유형별 정규화 결과 (SNOMED 코드 포함)
        """
        return {
            "intervention": self.normalize_intervention_with_snomed(text),
            "outcome": self.normalize_outcome_with_snomed(text),
            "pathology": self.normalize_pathology_with_snomed(text),
        }


# 싱글톤 인스턴스
_normalizer: Optional[EntityNormalizer] = None
_normalizer_lock = threading.Lock()


def get_normalizer() -> EntityNormalizer:
    """정규화기 싱글톤 가져오기 (thread-safe)."""
    global _normalizer
    if _normalizer is None:
        with _normalizer_lock:
            if _normalizer is None:
                _normalizer = EntityNormalizer()
    return _normalizer


# 사용 예시
if __name__ == "__main__":
    normalizer = EntityNormalizer()

    # 수술법 정규화 (English)
    print("=" * 60)
    print("1. EXACT MATCH (English)")
    print("=" * 60)
    for term in ["Biportal Endoscopic", "XLIF", "Transforaminal Fusion"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 수술법 정규화 (Korean)
    print("\n" + "=" * 60)
    print("2. EXACT MATCH (Korean)")
    print("=" * 60)
    for term in ["척추 유합술", "내시경 수술", "감압술"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 조사가 붙은 경우
    print("\n" + "=" * 60)
    print("3. EXACT MATCH (With Korean particles)")
    print("=" * 60)
    for term in ["TLIF가", "OLIF와", "UBE를"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 토큰 기반 매칭 (단어 순서 무관)
    print("\n" + "=" * 60)
    print("4. TOKEN-BASED MATCH (Word order independent)")
    print("=" * 60)
    for term in ["Endoscopic Biportal", "Trans LIF", "Fusion Lumbar Interbody"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 퍼지 매칭 (오타/약간의 변형)
    print("\n" + "=" * 60)
    print("5. FUZZY MATCH (Edit distance)")
    print("=" * 60)
    for term in ["Biportl", "Transforaminal Interbody", "Laminetomy"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 결과변수 정규화
    print("\n" + "=" * 60)
    print("6. OUTCOME NORMALIZATION (Fuzzy matching)")
    print("=" * 60)
    for term in ["Visual Analog Scale", "Oswestry", "C7 Plumb Line", "Visual Anlog Scale"]:
        result = normalizer.normalize_outcome(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 텍스트에서 수술법 추출 (English)
    print("\n" + "=" * 60)
    print("7. EXTRACTION FROM TEXT (English)")
    print("=" * 60)
    text = "Comparison of TLIF and OLIF for treatment of lumbar stenosis"
    interventions = normalizer.extract_and_normalize_interventions(text)
    for r in interventions:
        print(f"  Intervention: {r.normalized}")

    # 텍스트에서 수술법 추출 (Korean/Mixed)
    print("\n" + "=" * 60)
    print("8. EXTRACTION FROM TEXT (Korean/Mixed)")
    print("=" * 60)
    text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"
    interventions = normalizer.extract_and_normalize_interventions(text)
    pathologies = normalizer.extract_and_normalize_pathologies(text)
    for r in interventions:
        print(f"  Intervention: {r.normalized}")
    for r in pathologies:
        print(f"  Pathology: {r.normalized}")

    # SNOMED 코드 통합 예시
    print("\n" + "=" * 60)
    print("9. SNOMED-CT INTEGRATION")
    print("=" * 60)
    for term in ["TLIF", "Laminectomy", "Lumbar Stenosis", "VAS"]:
        # Determine entity type
        intervention_result = normalizer.normalize_intervention_with_snomed(term)
        pathology_result = normalizer.normalize_pathology_with_snomed(term)
        outcome_result = normalizer.normalize_outcome_with_snomed(term)

        # Find best match
        best = max([intervention_result, pathology_result, outcome_result],
                   key=lambda x: x.confidence)

        if best.confidence > 0:
            snomed_info = f" [SNOMED: {best.snomed_code}]" if best.snomed_code else " [No SNOMED]"
            print(f"  {term} → {best.normalized}{snomed_info}")
            if best.snomed_term:
                print(f"    SNOMED Term: {best.snomed_term}")
        else:
            print(f"  {term} → (no match)")
