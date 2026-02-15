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
    """
    original: str
    normalized: str
    confidence: float = 1.0
    matched_alias: str = ""
    method: str = "none"  # "exact", "token", "fuzzy", "none"
    snomed_code: str = ""
    snomed_term: str = ""
    category: str = ""


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
            "경피적 내시경", "PELD technique"
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
        ],

        # Motion Preservation
        "ADR": [
            "Artificial Disc Replacement", "TDR",
            "Total Disc Replacement", "Disc Arthroplasty"
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
            "Posterior lumbar interbody fusion with non-window-type 3D-printed titanium cage"
        ],

        # ========================================
        # Navigation & Robotics
        # ========================================
        "Robot-Assisted Surgery": [
            "Robotic surgery", "Robotic-assisted", "Robot-assisted spine surgery",
            "ROSA robot", "Mazor robot", "ExcelsiusGPS", "로봇 수술"
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
            "경추 인공디스크"
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
        "MED": "Endoscopic Surgery",
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
        "ESI": "Injection/Pain Management",
        "Facet Injection": "Injection/Pain Management",
        "RFA": "Injection/Pain Management",
        "SCS": "Injection/Pain Management",
        "Intrathecal Pump": "Injection/Pain Management",
        "Nerve Block": "Injection/Pain Management",
        "Trigger Point Injection": "Injection/Pain Management",
        "PRP Injection": "Injection/Pain Management",
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
        "Neuromodulation": "Injection/Pain Management",
        "Intradiscal injection": "Injection/Pain Management",
        "Spinal Injection Therapy": "Injection/Pain Management",
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
            # v1.14.11: QOL 변형 추가
            "QOL", "quality of life score",
            # 정규화된 이름의 대소문자 변형
            "eq-5d", "Eq-5d", "eq5d",
        ],
        "SF-36": [
            "Short Form 36", "SF36", "SF-36 score", "SF 36",
            # 정규화된 이름의 대소문자 변형
            "sf-36", "Sf-36", "sf36",
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
        ],
        # v1.14.11: Pseudarthrosis 추가
        "Pseudarthrosis": [
            "pseudarthrosis", "Pseudoarthrosis", "nonunion",
            "non-union", "Nonunion", "fusion failure",
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
            "CSF leak"
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
            "PJK incidence", "PJK rate", "Proximal junctional failure"
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
        ],
        "Blood Loss": [
            "EBL", "Estimated blood loss", "Intraoperative blood loss",
            "출혈량",
            # v1.14.1: 변형 추가
            "Intraoperative Blood Loss", "intraoperative blood loss",
            "Total Blood Loss", "total blood loss",
            "estimated blood loss", "Blood loss",
        ],
        "Hospital Stay": [
            "Length of stay", "LOS", "Hospital length of stay",
            "Hospitalization", "재원 기간",
            # v1.14.1: 변형 추가
            "Length of Stay", "length of stay",
            "Hospital LOS", "hospital stay",
            "Postoperative hospital stay",
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
            "비용"
        ],

        # ========================================
        # Patient Satisfaction
        # ========================================
        "MacNab": [
            "MacNab criteria", "Modified MacNab",
            "Excellent/Good rate"
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
            "Spinal cord injury grade"
        ],
        "Nurick Grade": [
            "Nurick myelopathy grade", "Nurick scale"
        ],

        # ========================================
        # Quality of Life
        # ========================================
        "PROMIS": [
            "PROMIS Physical Function", "PROMIS Pain Intensity",
            "PROMIS score"
        ],
        "WHOQOL": [
            "WHO Quality of Life", "WHOQOL-BREF"
        ],
        "COMI": [
            "Core Outcome Measures Index", "COMI score"
        ],
        "Zurich Claudication": [
            "ZCQ", "Zurich Claudication Questionnaire",
            "Symptom Severity Scale", "Physical Function Scale"
        ],

        # ========================================
        # Radiological - Additional
        # ========================================
        "Disc Height": [
            "Disc space height", "DHI", "Disc height index",
            "추간판 높이"
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
        ],
        "Facet Arthropathy": [
            "Facet Joint Arthritis", "Facet Arthritis",
            "Facet joint disease",
            # v1.14.1: 소문자 변형 추가
            "facet arthropathy", "facet joint arthritis",
            "Facet hypertrophy", "facet hypertrophy",
        ],
        # v1.14.1: Cervical Myelopathy 신규 추가
        # v1.15: merged duplicate entries
        "Cervical Myelopathy": [
            "Degenerative cervical myelopathy", "degenerative cervical myelopathy",
            "DCM", "Cervical spondylotic myelopathy",
            "cervical myelopathy", "Myelopathy",
            "CSM", "Cervical Spondylotic Myelopathy",
            "Cervical cord compression", "경추 척수병증",
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
        ],
        # v1.14.1: PJK 신규 추가
        # v1.15: merged duplicate entries
        "PJK": [
            "Proximal Junctional Kyphosis", "proximal junctional kyphosis",
            "PJF", "Proximal junctional failure", "proximal junctional failure",
            "Junctional kyphosis", "junctional kyphosis",
            "근위부 접합부 후만",
        ],
        # v1.14.1: DJK 신규 추가
        # v1.15: merged duplicate entries
        "DJK": [
            "Distal Junctional Kyphosis", "distal junctional kyphosis",
            "Distal junctional failure",
        ],
        # v1.14.1: Adjacent Segment Disease 신규 추가
        # v1.15: merged duplicate entries
        "Adjacent Segment Disease": [
            "adjacent segment disease", "ASD (Adjacent Segment)",
            "Adjacent segment degeneration", "adjacent segment degeneration",
            "Adjacent level disease", "Radiographic ASD",
            "ASDis", "인접분절 퇴행",
        ],

        # Trauma Pathologies
        "Compression Fracture": [
            "VCF", "Vertebral Compression Fracture",
            "Osteoporotic Fracture",
            "척추 압박 골절", "골다공증성 골절"
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
            "경막외 농양"
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
            "후종인대 골화증"
        ],
        "OLF": [
            "Ossification of Ligamentum Flavum", "황색인대 골화증"
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
            "Facet cyst", "Juxta-articular cyst", "활막낭종"
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
        # Non-specific anatomy (인식하되 quality_flag 설정 대상)
        "Multi-level": ["Multiple levels", "Multilevel", "Multisegmental", "multi-level"],
    }

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

    def normalize_outcome(self, text: str) -> NormalizationResult:
        """결과변수 정규화 (SNOMED 코드 포함)."""
        result = self._normalize(
            text,
            self._outcome_reverse,
            "outcome",
            self.OUTCOME_ALIASES
        )
        return self._enrich_with_snomed(result, "outcome")

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

        Args:
            text: 입력 텍스트 (예: "L-spine", "C5-C6", "요추")

        Returns:
            NormalizationResult (snomed_code, snomed_term 포함)
        """
        # 한국어 해부학 용어 변환 (우선)
        stripped = text.strip()
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
        # NO MATCH - 원본 반환
        # ═══════════════════════════════════════════════════
        logger.debug(f"No {entity_type} match found for: {text}")
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

        Args:
            result: 정규화 결과
            entity_type: 엔티티 유형 ("intervention", "pathology", "outcome", "anatomy")

        Returns:
            SNOMED 코드가 추가된 결과
        """
        if not SNOMED_AVAILABLE:
            return result

        if result.confidence == 0.0 or not result.normalized:
            return result

        mapping = None
        if entity_type == "intervention" and get_snomed_for_intervention:
            mapping = get_snomed_for_intervention(result.normalized)
        elif entity_type == "pathology" and get_snomed_for_pathology:
            mapping = get_snomed_for_pathology(result.normalized)
        elif entity_type == "outcome" and get_snomed_for_outcome:
            mapping = get_snomed_for_outcome(result.normalized)
        elif entity_type == "anatomy" and get_snomed_for_anatomy:
            mapping = get_snomed_for_anatomy(result.normalized)

        if mapping:
            result.snomed_code = mapping.code
            result.snomed_term = mapping.term

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


def get_normalizer() -> EntityNormalizer:
    """정규화기 싱글톤 가져오기."""
    global _normalizer
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
