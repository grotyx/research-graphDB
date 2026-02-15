"""SNOMED-CT Mappings for Spine Surgery Domain.

Comprehensive mapping tables for spine surgery interventions, pathologies,
outcomes, and anatomy to SNOMED-CT codes.

Reference:
- SNOMED CT Browser: https://browser.ihtsdotools.org/
- SNOMED CT US Edition (September 2024)

Extension Code System (v4.3):
- Namespace: 900000000000 (local extension namespace)
- Range allocation:
  - 900000000001xx: Procedures/Interventions
  - 900000000002xx: Disorders/Pathologies
  - 900000000003xx: Observable Entities/Outcomes
  - 900000000004xx: Body Structures/Anatomy
  - 900000000005xx: Findings

Note: Some newer procedures (e.g., UBE, OLIF) may not have official SNOMED codes yet.
Extension codes are used with parent concept references for hierarchical queries.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Extension Code Configuration
EXTENSION_NAMESPACE = "900000000000"
EXTENSION_RANGES = {
    "procedure": (100, 199),     # 900000000001xx
    "disorder": (200, 299),      # 900000000002xx
    "observable": (300, 399),    # 900000000003xx
    "body_structure": (400, 499),  # 900000000004xx
    "finding": (500, 599),       # 900000000005xx
}


class SNOMEDSemanticType(Enum):
    """SNOMED CT Semantic Types for spine domain."""
    PROCEDURE = "procedure"
    DISORDER = "disorder"
    BODY_STRUCTURE = "body_structure"
    OBSERVABLE_ENTITY = "observable_entity"
    FINDING = "finding"
    QUALIFIER_VALUE = "qualifier_value"


@dataclass
class SNOMEDMapping:
    """SNOMED-CT mapping entry.

    Attributes:
        code: SNOMED-CT Concept ID (SCTID)
        term: Preferred term (FSN without semantic tag)
        semantic_type: SNOMED semantic type
        synonyms: Alternative terms (English + Korean)
        parent_code: Parent concept code for hierarchy
        is_extension: True if code is proposed/extension (not official)
        notes: Additional notes about the mapping
        abbreviations: Common abbreviations (UBE, OLIF, etc.)
        korean_term: Korean translation of the term
    """
    code: str
    term: str
    semantic_type: SNOMEDSemanticType = SNOMEDSemanticType.PROCEDURE
    synonyms: list[str] = None
    parent_code: Optional[str] = None
    is_extension: bool = False
    notes: str = ""
    abbreviations: list[str] = None
    korean_term: str = ""

    def __post_init__(self):
        if self.synonyms is None:
            self.synonyms = []
        if self.abbreviations is None:
            self.abbreviations = []

    def get_all_terms(self) -> list[str]:
        """Get all searchable terms including synonyms and abbreviations."""
        terms = [self.term] + self.synonyms + self.abbreviations
        if self.korean_term:
            terms.append(self.korean_term)
        return terms


def generate_extension_code(category: str, index: int) -> str:
    """Generate extension code with proper namespace.

    Args:
        category: Category name (procedure, disorder, observable, body_structure, finding)
        index: Index within category (1-99)

    Returns:
        Extension code string (e.g., "900000000000101" for procedure index 1)
    """
    if category not in EXTENSION_RANGES:
        raise ValueError(f"Unknown category: {category}")
    base, _ = EXTENSION_RANGES[category]
    return f"{EXTENSION_NAMESPACE}{base + index}"


# =============================================================================
# SYNONYM GROUPS (v4.3) - 완전 동의어 그룹
# =============================================================================
# 같은 수술법의 다른 이름들 - 검색 시 모두 동일하게 처리

SYNONYM_GROUPS: list[set[str]] = [
    # Biportal Endoscopy 계열 (완전 동의어) - v1.14: BED 추가
    {"UBE", "BESS", "UBESS", "Biportal Endoscopy", "Biportal Endoscopic",
     "Unilateral Biportal Endoscopy", "Biportal Endoscopic Spine Surgery",
     "BED", "Biportal Endoscopic Discectomy"},

    # Lateral Interbody Fusion - Transpsoas 접근 (완전 동의어)
    {"LLIF", "XLIF", "DLIF", "Lateral Lumbar Interbody Fusion",
     "Extreme Lateral Interbody Fusion", "Direct Lateral Interbody Fusion"},

    # OLIF 계열 (완전 동의어)
    {"OLIF", "ATP", "OLIF25", "OLIF51", "Oblique Lumbar Interbody Fusion",
     "Anterior to Psoas", "Oblique Lateral Interbody Fusion"},

    # BELIF/BE-TLIF 계열 (완전 동의어) - v1.14 추가
    {"BELIF", "BE-TLIF", "BETLIF", "BE-LIF", "BELF",
     "Biportal Endoscopic TLIF", "Biportal Endoscopic Lumbar Interbody Fusion",
     "Biportal endoscopic transforaminal lumbar interbody fusion"},

    # Decompression/Laminectomy 계열 (완전 동의어) - v1.14 추가
    {"Decompression", "decompression", "Neural Decompression", "neural decompression",
     "Decompression Surgery", "Spinal decompression", "Neural decompression"},

    # Laminectomy 계열 (완전 동의어) - v1.14 추가
    {"Laminectomy", "laminectomy", "Decompressive Laminectomy", "decompressive laminectomy",
     "Open Laminectomy", "Open laminectomy"},

    # v1.14.1: Fusion 일반 계열 추가
    {"Posterior fusion", "posterior fusion", "PSF", "Posterior spinal fusion",
     "posterior spinal fusion", "Posterolateral Fusion", "PLF"},

    # v1.14.1: TLIF 계열 추가
    {"TLIF", "Transforaminal Lumbar Interbody Fusion", "transforaminal lumbar interbody fusion",
     "Transforaminal fusion", "transforaminal fusion"},

    # v1.14.1: Radiculopathy 계열 추가
    {"Sciatica", "sciatica", "Lumbar Radiculopathy", "lumbar radiculopathy",
     "Radicular pain", "Radicular leg pain"},

    # Disc Herniation 계열
    {"HNP", "HIVD", "LDH", "Lumbar Disc Herniation", "Herniated Nucleus Pulposus",
     "Herniated Intervertebral Disc", "Disc Prolapse"},

    # Spinal Stenosis 계열
    {"LSS", "Lumbar Stenosis", "Lumbar Spinal Stenosis", "Central Stenosis"},

    # Cervical Myelopathy 계열
    {"DCM", "CSM", "Cervical Myelopathy", "Degenerative Cervical Myelopathy",
     "Cervical Spondylotic Myelopathy"},

    # PELD/FELD 계열 (유사하지만 약간 다름 - 접근 방식 차이)
    {"PELD", "TELD", "TF-PELD", "Percutaneous Endoscopic Lumbar Discectomy",
     "Transforaminal Endoscopic Discectomy"},

    {"FELD", "FEID", "IL-FELD", "Full Endoscopic Lumbar Discectomy",
     "Interlaminar Endoscopic Discectomy"},

    # Adjacent Segment Disease
    {"ASD", "ASDis", "ASDeg", "Adjacent Segment Disease",
     "Adjacent Segment Degeneration", "Adjacent Level Disease"},

    # Proximal Junctional Kyphosis
    {"PJK", "PJF", "Proximal Junctional Kyphosis", "Proximal Junctional Failure"},
]


# =============================================================================
# RELATED TERMS (v4.3) - 유사하지만 다른 수술법
# =============================================================================
# 같은 카테고리지만 다른 접근법/기법 - 검색 시 "관련 수술법"으로 표시

RELATED_TERMS: dict[str, list[str]] = {
    # Lateral Fusion 계열 - 비슷하지만 접근 방식이 다름
    "LLIF": ["OLIF", "ALIF"],  # LLIF와 관련된 수술법
    "OLIF": ["LLIF", "ALIF"],
    "ALIF": ["LLIF", "OLIF"],

    # Endoscopic Surgery 계열
    "UBE": ["PELD", "FELD", "MED"],  # 다른 내시경 수술들
    "PELD": ["UBE", "FELD", "MED"],
    "FELD": ["UBE", "PELD", "MED"],
    "MED": ["UBE", "PELD", "FELD"],

    # Fusion vs Decompression
    "TLIF": ["MIS-TLIF", "PLIF", "ALIF"],
    "MIS-TLIF": ["TLIF", "UBE"],  # MIS-TLIF는 TLIF의 변형이자 UBE와 결합 가능

    # Osteotomy 계열
    "SPO": ["PSO", "VCR"],
    "PSO": ["SPO", "VCR"],
    "VCR": ["SPO", "PSO"],
}


# ============================================================================
# INTERVENTION MAPPINGS - Spine Surgery Procedures
# ============================================================================

SPINE_INTERVENTION_SNOMED: dict[str, SNOMEDMapping] = {
    # === FUSION SURGERY ===
    "Fusion Surgery": SNOMEDMapping(
        code="122465003",
        term="Fusion of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Spinal fusion", "Spondylodesis", "Arthrodesis of spine"],
    ),
    "Interbody Fusion": SNOMEDMapping(
        code="609588000",
        term="Interbody fusion of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",
        synonyms=["Intervertebral fusion"],
    ),
    "Posterolateral Fusion": SNOMEDMapping(
        code="44946007",
        term="Posterolateral fusion of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",
        synonyms=["PLF", "Intertransverse fusion"],
    ),

    # Interbody Fusion - Specific Approaches
    "TLIF": SNOMEDMapping(
        code="447764006",
        term="Transforaminal lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",
        synonyms=["Transforaminal interbody fusion"],
    ),
    "PLIF": SNOMEDMapping(
        code="87031008",
        term="Posterior lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",
    ),
    "ALIF": SNOMEDMapping(
        code="426294006",
        term="Anterior lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",
    ),
    "OLIF": SNOMEDMapping(
        code="900000000000101",
        term="Oblique lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",  # Interbody fusion of spine
        is_extension=True,
        synonyms=["Oblique lateral interbody fusion", "Anterior to psoas approach"],
        abbreviations=["OLIF", "ATP", "OLIF51", "OLIF25"],
        korean_term="사측방 요추 추체간 유합술",
        notes="No official SNOMED code - maps to interbody fusion concept",
    ),
    "LLIF": SNOMEDMapping(
        code="450436003",
        term="Lateral lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",
        synonyms=["XLIF", "DLIF", "Extreme lateral interbody fusion"],
    ),
    "ACDF": SNOMEDMapping(
        code="112728004",
        term="Anterior cervical discectomy and fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",
        synonyms=["Anterior cervical fusion"],
    ),
    "MIS-TLIF": SNOMEDMapping(
        code="900000000000102",
        term="Minimally invasive transforaminal lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="447764006",  # TLIF
        is_extension=True,
        synonyms=["Percutaneous TLIF", "Tubular TLIF"],
        abbreviations=["MIS-TLIF", "MI-TLIF", "Mini-TLIF"],
        korean_term="최소침습 경추간공 요추 추체간 유합술",
        notes="Extension of TLIF with minimally invasive approach qualifier",
    ),
    "MIDLF": SNOMEDMapping(
        code="900000000000103",
        term="Midline lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",  # Interbody fusion
        is_extension=True,
        synonyms=["Midline interbody fusion", "Wiltse approach"],
        abbreviations=["MIDLF"],
        korean_term="정중선 요추 추체간 유합술",
    ),
    "CBT Fusion": SNOMEDMapping(
        code="900000000000104",
        term="Cortical bone trajectory fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="44946007",  # Posterolateral fusion
        is_extension=True,
        synonyms=["Cortical screw fusion", "Medialized trajectory screw"],
        abbreviations=["CBT", "CBT screw"],
        korean_term="피질골 경로 유합술",
    ),

    # Cervical Fusion
    "Posterior Cervical Fusion": SNOMEDMapping(
        code="112729007",
        term="Posterior cervical fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",
        synonyms=["PCF"],
    ),
    "C1-C2 Fusion": SNOMEDMapping(
        code="44337006",
        term="Arthrodesis of atlantoaxial joint",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="112729007",
        synonyms=["Atlantoaxial fusion", "C1-C2 arthrodesis"],
    ),
    "Occipitocervical Fusion": SNOMEDMapping(
        code="426838003",
        term="Occipitocervical fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="112729007",
        synonyms=["OC fusion", "Occipito-cervical fusion"],
    ),

    # === DECOMPRESSION SURGERY ===
    "Decompression Surgery": SNOMEDMapping(
        code="5765005",
        term="Decompression of spinal cord",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Neural decompression", "Spinal decompression"],
    ),
    "Laminectomy": SNOMEDMapping(
        code="387731002",
        term="Laminectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Decompressive laminectomy", "Open laminectomy"],
    ),
    "Laminotomy": SNOMEDMapping(
        code="112737006",
        term="Laminotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Hemilaminotomy", "Partial laminectomy"],
    ),
    "Foraminotomy": SNOMEDMapping(
        code="11585007",
        term="Foraminotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Foraminal decompression"],
    ),
    "Discectomy": SNOMEDMapping(
        code="42515009",
        term="Excision of intervertebral disc",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Diskectomy", "Disc removal"],
    ),

    # Endoscopic Surgery
    "Endoscopic Surgery": SNOMEDMapping(
        code="386638009",
        term="Endoscopic spinal procedure",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Endoscopic decompression"],
    ),
    "UBE": SNOMEDMapping(
        code="900000000000105",
        term="Unilateral biportal endoscopic spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        # v1.14: BED (Biportal Endoscopic Discectomy) 동의어 추가
        synonyms=["Biportal endoscopic spine surgery", "Biportal endoscopy",
                  "Biportal Endoscopic Discectomy", "Biportal endoscopic discectomy"],
        abbreviations=["UBE", "BESS", "UBESS", "BED"],
        korean_term="일측 양방향 내시경 척추 수술",
        notes="Emerging technique (2016+) - no official SNOMED code yet. BED is synonym.",
    ),
    "FELD": SNOMEDMapping(
        code="900000000000106",
        term="Full endoscopic lumbar discectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        synonyms=["Full endoscopic interlaminar discectomy", "Interlaminar endoscopic discectomy"],
        abbreviations=["FELD", "FEID", "IL-FELD"],
        korean_term="전내시경 요추 추간판 절제술",
    ),
    "PELD": SNOMEDMapping(
        code="900000000000107",
        term="Percutaneous endoscopic lumbar discectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        synonyms=["Transforaminal endoscopic discectomy", "Percutaneous endoscopic discectomy"],
        abbreviations=["PELD", "TELD", "TF-PELD"],
        korean_term="경피적 내시경 요추 추간판 절제술",
    ),
    "FESS": SNOMEDMapping(
        code="900000000000108",
        term="Full endoscopic spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        synonyms=["Full-endoscopic spine surgery", "Single portal endoscopy"],
        abbreviations=["FESS"],
        korean_term="전내시경 척추 수술",
    ),
    "PSLD": SNOMEDMapping(
        code="900000000000109",
        term="Percutaneous stenoscopic lumbar decompression",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        synonyms=["Stenoscopic decompression"],
        abbreviations=["PSLD", "PSELD"],
        korean_term="경피적 협착 내시경 요추 감압술",
    ),

    # Microscopic Surgery
    "Microscopic Surgery": SNOMEDMapping(
        code="387714009",
        term="Microsurgical technique",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        synonyms=["Microscopic decompression"],
    ),
    "MED": SNOMEDMapping(
        code="900000000000110",
        term="Microendoscopic discectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="387714009",  # Microsurgical technique
        is_extension=True,
        synonyms=["Microendoscopic surgery", "Tubular discectomy"],
        abbreviations=["MED", "MECD"],
        korean_term="미세내시경 추간판 절제술",
    ),
    "Microdecompression": SNOMEDMapping(
        code="900000000000111",
        term="Microscopic decompression",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="387714009",  # Microsurgical technique
        is_extension=True,
        synonyms=["Microscopic laminotomy", "Tubular decompression"],
        abbreviations=["MicroD"],
        korean_term="미세현미경 감압술",
    ),

    # === OSTEOTOMY ===
    "Osteotomy": SNOMEDMapping(
        code="179097009",
        term="Osteotomy of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Spinal osteotomy", "Corrective osteotomy"],
        korean_term="척추 절골술",
    ),
    "SPO": SNOMEDMapping(
        code="900000000000112",
        term="Smith-Petersen osteotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="179097009",  # Osteotomy of spine
        is_extension=True,
        synonyms=["Ponte osteotomy", "Posterior column osteotomy", "Chevron osteotomy"],
        abbreviations=["SPO", "PCO"],
        korean_term="스미스-피터슨 절골술",
        notes="Also known as Schwab grade 1 osteotomy",
    ),
    "PSO": SNOMEDMapping(
        code="900000000000113",
        term="Pedicle subtraction osteotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="179097009",  # Osteotomy of spine
        is_extension=True,
        synonyms=["3-column osteotomy", "Closing wedge osteotomy", "Transpedicular wedge osteotomy"],
        abbreviations=["PSO"],
        korean_term="척추경 절제 절골술",
        notes="Schwab grade 3 osteotomy - single level 30-40° correction",
    ),
    "VCR": SNOMEDMapping(
        code="900000000000114",
        term="Vertebral column resection",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="179097009",  # Osteotomy of spine
        is_extension=True,
        synonyms=["Complete vertebral resection", "Total spondylectomy"],
        abbreviations=["VCR", "PVCR"],
        korean_term="척추체 절제술",
        notes="Schwab grade 4-6 osteotomy - most aggressive correction",
    ),

    # === VERTEBRAL AUGMENTATION ===
    "Vertebral Augmentation": SNOMEDMapping(
        code="447766008",
        term="Vertebral augmentation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
    ),
    "PVP": SNOMEDMapping(
        code="392010000",
        term="Percutaneous vertebroplasty",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="447766008",
        synonyms=["Vertebroplasty"],
    ),
    "PKP": SNOMEDMapping(
        code="429616001",
        term="Percutaneous kyphoplasty",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="447766008",
        synonyms=["Balloon kyphoplasty"],
    ),

    # === FIXATION ===
    "Fixation": SNOMEDMapping(
        code="33620004",
        term="Instrumented fusion of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Spinal fixation", "Spinal instrumentation"],
    ),
    "Pedicle Screw": SNOMEDMapping(
        code="40388003",
        term="Insertion of pedicle screw",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",
        synonyms=["Pedicle screw fixation", "PS fixation"],
    ),
    "Lateral Mass Screw": SNOMEDMapping(
        code="900000000000115",
        term="Lateral mass screw fixation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion
        is_extension=True,
        synonyms=["Lateral mass fixation", "Cervical lateral mass screw"],
        abbreviations=["LMS"],
        korean_term="측괴 나사못 고정술",
    ),

    # === MOTION PRESERVATION ===
    "Motion Preservation": SNOMEDMapping(
        code="900000000000116",
        term="Motion preservation surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Non-fusion surgery", "Dynamic surgery"],
        abbreviations=["MP"],
        korean_term="운동 보존 수술",
    ),
    "ADR": SNOMEDMapping(
        code="428191000124105",
        term="Artificial disc replacement",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Total disc replacement", "Disc arthroplasty", "Disc prosthesis"],
        abbreviations=["ADR", "TDR", "cTDR", "lTDR"],
        korean_term="인공 디스크 치환술",
    ),
    "Dynamic Stabilization": SNOMEDMapping(
        code="900000000000117",
        term="Dynamic stabilization of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Posterior dynamic stabilization", "Soft stabilization"],
        abbreviations=["PDS"],
        korean_term="동적 안정화술",
    ),
    "Interspinous Device": SNOMEDMapping(
        code="900000000000118",
        term="Interspinous process device insertion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Interspinous spacer", "Interspinous distraction device"],
        abbreviations=["IPD", "ISD", "X-STOP"],
        korean_term="극간 장치 삽입술",
    ),

    # v1.14 추가: BELIF (Biportal Endoscopic Lumbar Interbody Fusion)
    "BELIF": SNOMEDMapping(
        code="900000000000119",
        term="Biportal endoscopic lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",  # Interbody fusion of spine
        is_extension=True,
        synonyms=["Biportal Endoscopic TLIF", "BE-transforaminal lumbar interbody fusion",
                  "Biportal endoscopic transforaminal lumbar interbody fusion"],
        abbreviations=["BELIF", "BE-TLIF", "BETLIF", "BE-LIF", "BELF"],
        korean_term="양방향 내시경 요추 추체간 유합술",
        notes="Endoscopic fusion technique combining UBE approach with interbody fusion",
    ),

    # v1.14 추가: Stereotactic Navigation
    "Stereotactic Navigation": SNOMEDMapping(
        code="900000000000120",
        term="Stereotactic navigation-guided spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["Navigation-guided surgery", "O-arm navigation", "CT navigation",
                  "Intraoperative navigation", "Computer-assisted spine surgery"],
        abbreviations=["NAV", "O-arm", "CASS"],
        korean_term="정위적 네비게이션 척추 수술",
        notes="Includes O-arm, CT-based, and other navigation systems",
    ),

    # v1.14.2 추가: Facetectomy
    "Facetectomy": SNOMEDMapping(
        code="900000000000121",
        term="Facetectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Partial facetectomy", "Medial facetectomy", "Total facetectomy",
                  "Facet resection", "Facet joint excision"],
        abbreviations=["Facetectomy"],
        korean_term="후관절 절제술",
        notes="Resection of the facet joint for decompression or access",
    ),

    # v1.16.1 추가: 누락된 Intervention SNOMED 매핑
    "COWO": SNOMEDMapping(
        code="900000000000122",
        term="Three-column osteotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="179097009",  # Osteotomy
        is_extension=True,
        synonyms=["Three-column osteotomy", "3-column osteotomy", "3CO"],
        abbreviations=["COWO", "3CO"],
        korean_term="3주 절골술",
        notes="Includes PSO and VCR; used for severe fixed deformity correction",
    ),
    "Open Decompression": SNOMEDMapping(
        code="900000000000123",
        term="Open neural decompression of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Open decompression", "Open spinal decompression",
                  "Open neural decompression"],
        abbreviations=["OD"],
        korean_term="개방 감압술",
    ),
    "Over-the-top Decompression": SNOMEDMapping(
        code="900000000000124",
        term="Over-the-top decompression technique",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        is_extension=True,
        synonyms=["Over the top decompression", "OTT decompression"],
        abbreviations=["OTD"],
        korean_term="오버더탑 감압술",
        notes="Contralateral decompression via ipsilateral approach",
    ),
    "UBD": SNOMEDMapping(
        code="900000000000125",
        term="Unilateral laminotomy for bilateral decompression",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",
        is_extension=True,
        synonyms=["Unilateral bilateral decompression", "ULBD",
                  "Unilateral approach bilateral decompression"],
        abbreviations=["UBD", "ULBD"],
        korean_term="일측 접근 양측 감압술",
    ),


    # ========================================
    # v1.17: Additional Intervention SNOMED Mappings
    # ========================================
# =================================================================
    # v1.17: Missing Intervention SNOMED Mappings (72 entries)
    # Extension codes: 900000000000126 ~ 900000000000172
    # =================================================================

    # --- ENDOSCOPIC / MIS DECOMPRESSION ---
    "Endoscopic Decompression": SNOMEDMapping(
        code="900000000000126",
        term="Endoscopic decompression of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="386638009",  # Endoscopic spinal procedure
        is_extension=True,
        synonyms=["Endoscopic lumbar decompression", "Endoscopic spinal decompression",
                  "Endoscopic spine decompression"],
        abbreviations=["ED"],
        korean_term="내시경 감압술",
    ),
    "Tubular Discectomy": SNOMEDMapping(
        code="900000000000127",
        term="Tubular microdiscectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="42515009",  # Excision of intervertebral disc
        is_extension=True,
        synonyms=["Tubular decompression", "METRx discectomy", "Tubular retractor discectomy"],
        abbreviations=["METRx"],
        korean_term="튜브 추간판 절제술",
    ),
    "BE-ULBD": SNOMEDMapping(
        code="900000000000128",
        term="Biportal endoscopic unilateral laminotomy for bilateral decompression",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000105",  # UBE
        is_extension=True,
        synonyms=["Biportal Endoscopic ULBD",
                  "Biportal endoscopic unilateral laminotomy bilateral decompression"],
        abbreviations=["BE-ULBD"],
        korean_term="양방향 내시경 일측 접근 양측 감압술",
    ),

    # --- DECOMPRESSION / RESECTION ---
    "Corpectomy": SNOMEDMapping(
        code="112730002",
        term="Corpectomy of vertebral body",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        synonyms=["Anterior corpectomy", "Cervical corpectomy", "Lumbar corpectomy"],
        abbreviations=["Corpectomy"],
        korean_term="추체 절제술",
    ),
    "Debridement": SNOMEDMapping(
        code="36777000",
        term="Debridement of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        synonyms=["Surgical debridement", "Spinal debridement",
                  "Minimally invasive microscopic debridement"],
        korean_term="변연 절제술",
    ),
    "Sacroplasty": SNOMEDMapping(
        code="900000000000129",
        term="Sacroplasty",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="447766008",  # Vertebral augmentation
        is_extension=True,
        synonyms=["Sacral augmentation", "Sacral vertebroplasty",
                  "Percutaneous sacroplasty"],
        abbreviations=["SP"],
        korean_term="천골 성형술",
    ),

    # --- FUSION - SPECIALIZED ---
    "Posterior Instrumented Fusion": SNOMEDMapping(
        code="900000000000130",
        term="Posterior instrumented fusion of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="44946007",  # Posterolateral fusion
        is_extension=True,
        synonyms=["Posterior instrumented fusion", "Instrumented posterior fusion"],
        abbreviations=["PIF"],
        korean_term="후방 기기 유합술",
    ),
    "Anterior fusion": SNOMEDMapping(
        code="900000000000131",
        term="Anterior spinal fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Anterior spinal fusion", "Anterior approach fusion"],
        abbreviations=["ASF"],
        korean_term="전방 척추 유합술",
    ),
    "Lumbar Fusion": SNOMEDMapping(
        code="900000000000132",
        term="Lumbar spinal fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Lumbar spinal fusion", "Lumbar arthrodesis"],
        abbreviations=["LF"],
        korean_term="요추 유합술",
    ),
    "PTF": SNOMEDMapping(
        code="900000000000133",
        term="Posterior thoracic fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Posterior thoracic spinal fusion", "Thoracic posterior fusion"],
        abbreviations=["PTF"],
        korean_term="후방 흉추 유합술",
    ),
    "Spinopelvic fusion": SNOMEDMapping(
        code="900000000000134",
        term="Spinopelvic fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Spinopelvic fixation", "Lumbopelvic fixation", "Iliac fixation"],
        abbreviations=["SPF"],
        korean_term="척추-골반 유합술",
    ),
    "CCF": SNOMEDMapping(
        code="900000000000135",
        term="Cervical corpectomy and fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",  # Interbody fusion of spine
        is_extension=True,
        synonyms=["Anterior cervical corpectomy", "Cervical corpectomy fusion",
                  "Anterior Cervical Corpectomy and Fusion"],
        abbreviations=["CCF", "ACCF"],
        korean_term="경추 추체 절제 및 유합술",
    ),

    # --- CONSERVATIVE MANAGEMENT ---
    "Conservative Management": SNOMEDMapping(
        code="900000000000136",
        term="Conservative management of spine condition",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Conservative treatment", "Non-surgical treatment",
                  "Non-operative treatment", "Non-operative management"],
        abbreviations=["CM", "CTx"],
        korean_term="보존적 치료",
        notes="Non-surgical management; no specific SNOMED procedure code",
    ),
    "Bisphosphonate": SNOMEDMapping(
        code="900000000000137",
        term="Bisphosphonate therapy for spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["Bisphosphonate treatment", "Bisphosphonate therapy",
                  "Alendronate", "Zoledronic acid"],
        abbreviations=["BP"],
        korean_term="비스포스포네이트 치료",
    ),
    "Teriparatide": SNOMEDMapping(
        code="900000000000138",
        term="Teriparatide therapy for spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["Teriparatide treatment", "PTH therapy", "Forteo",
                  "Parathyroid hormone therapy"],
        abbreviations=["TPTD"],
        korean_term="테리파라타이드 치료",
    ),
    "Denosumab": SNOMEDMapping(
        code="900000000000139",
        term="Denosumab therapy for spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["Denosumab treatment", "Prolia", "RANKL inhibitor therapy"],
        abbreviations=["Dmab"],
        korean_term="데노수맙 치료",
    ),
    "SERM": SNOMEDMapping(
        code="900000000000140",
        term="Selective estrogen receptor modulator therapy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["SERM treatment", "Selective estrogen receptor modulator",
                  "Raloxifene", "Raloxifene therapy"],
        abbreviations=["SERM"],
        korean_term="선택적 에스트로겐 수용체 조절제 치료",
    ),
    "Bracing": SNOMEDMapping(
        code="900000000000141",
        term="Spinal bracing",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["Brace", "Spinal brace", "Orthosis", "TLSO",
                  "Thoracolumbosacral orthosis", "Spinal orthotic"],
        abbreviations=["TLSO"],
        korean_term="보조기 치료",
        notes="External bracing/orthosis; no specific SNOMED procedure code",
    ),
    "Physical therapy": SNOMEDMapping(
        code="91251008",
        term="Physical therapy procedure",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        synonyms=["Physiotherapy", "Physical Therapy", "Rehabilitation",
                  "Physical rehabilitation"],
        abbreviations=["PT"],
        korean_term="물리치료",
    ),
    "Antibiotic therapy": SNOMEDMapping(
        code="900000000000142",
        term="Antibiotic therapy for spinal infection",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000136",  # Conservative management
        is_extension=True,
        synonyms=["Antibiotic treatment", "IV antibiotics",
                  "Antimicrobial therapy", "Parenteral antibiotic therapy"],
        abbreviations=["ABx"],
        korean_term="항생제 치료",
    ),

    # --- DIAGNOSTIC ---
    "MRI": SNOMEDMapping(
        code="113091000",
        term="Magnetic resonance imaging",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Magnetic resonance imaging", "MR imaging",
                  "Spine MRI", "Magnetic resonance"],
        abbreviations=["MRI"],
        korean_term="자기공명영상",
    ),
    "CT": SNOMEDMapping(
        code="77477000",
        term="Computed tomography",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Computed tomography", "CT scan", "Spine CT",
                  "Computed axial tomography"],
        abbreviations=["CT", "CAT"],
        korean_term="컴퓨터 단층촬영",
    ),
    "Bone Scintigraphy": SNOMEDMapping(
        code="71651007",
        term="Bone scintigraphy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Bone scintigraphy (Tc-99m MDP)", "Bone scan",
                  "Tc-99m bone scan", "Skeletal scintigraphy",
                  "Radionuclide bone scan"],
        korean_term="뼈 신티그래피",
    ),
    "X-ray": SNOMEDMapping(
        code="363680008",
        term="Radiographic imaging procedure",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Radiography", "Plain radiograph", "Plain radiography",
                  "Spine X-ray", "Plain film", "Conventional radiograph"],
        abbreviations=["XR"],
        korean_term="엑스레이 촬영",
    ),

    # --- OTHER SURGICAL ---
    "Drainage": SNOMEDMapping(
        code="900000000000143",
        term="Surgical drainage of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Surgical drainage", "Abscess drainage", "Spinal abscess drainage"],
        korean_term="배액술",
    ),
    "Hip Fracture Surgery": SNOMEDMapping(
        code="179275003",
        term="Fixation of fracture of hip",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Hip fracture surgery", "Hip fracture fixation",
                  "Hip fracture repair"],
        korean_term="고관절 골절 수술",
    ),
    "Cage Insertion": SNOMEDMapping(
        code="900000000000144",
        term="Interbody cage insertion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="609588000",  # Interbody fusion of spine
        is_extension=True,
        synonyms=["Large PEEK cage insertion", "PEEK cage insertion",
                  "3D-printed titanium cage", "Titanium cage insertion",
                  "Interbody cage placement"],
        abbreviations=["CI"],
        korean_term="케이지 삽입술",
    ),

    # --- NAVIGATION & ROBOTICS ---
    "Robot-Assisted Surgery": SNOMEDMapping(
        code="900000000000145",
        term="Robot-assisted spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["Robotic surgery", "Robotic-assisted", "Robot-assisted spine surgery",
                  "ROSA robot", "Mazor robot", "ExcelsiusGPS"],
        abbreviations=["RAS"],
        korean_term="로봇 보조 척추 수술",
    ),
    "Navigation-Guided Surgery": SNOMEDMapping(
        code="900000000000146",
        term="Navigation-guided spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["Navigation surgery", "CT navigation", "O-arm navigation",
                  "O-arm guided", "Intraoperative CT", "Fluoroscopy-guided",
                  "Computer-assisted surgery", "Image-guided surgery"],
        abbreviations=["CAS", "IGS"],
        korean_term="네비게이션 유도 척추 수술",
    ),

    # --- CERVICAL-SPECIFIC PROCEDURES ---
    "CDR": SNOMEDMapping(
        code="609153009",
        term="Cervical disc replacement",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="428191000124105",  # Artificial disc replacement
        synonyms=["Cervical Disc Replacement", "Cervical ADR",
                  "Cervical Artificial Disc", "Cervical TDR",
                  "Cervical total disc replacement"],
        abbreviations=["CDR", "cTDR", "cADR"],
        korean_term="경추 인공디스크 치환술",
    ),
    "Laminoplasty": SNOMEDMapping(
        code="387715005",
        term="Laminoplasty",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        synonyms=["Cervical Laminoplasty", "Open-door laminoplasty",
                  "French-door laminoplasty", "Double-door laminoplasty",
                  "Hirabayashi laminoplasty", "Expansive laminoplasty"],
        korean_term="추궁성형술",
    ),
    "Posterior Cervical Foraminotomy": SNOMEDMapping(
        code="900000000000147",
        term="Posterior cervical foraminotomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="11585007",  # Foraminotomy
        is_extension=True,
        synonyms=["PCF", "Cervical foraminotomy", "Keyhole foraminotomy",
                  "Posterior cervical decompression"],
        abbreviations=["PCF"],
        korean_term="후방 경추 추간공 확장술",
        notes="PCF abbreviation conflicts with Posterior Cervical Fusion in some contexts",
    ),

    # --- REVISION PROCEDURES ---
    "Revision Surgery": SNOMEDMapping(
        code="900000000000148",
        term="Revision spine surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Revision fusion", "Revision spine surgery", "Redo surgery",
                  "Re-operation", "Revision spinal surgery"],
        abbreviations=["Rev"],
        korean_term="재수술",
    ),
    "Pseudarthrosis Repair": SNOMEDMapping(
        code="900000000000149",
        term="Repair of pseudarthrosis of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000148",  # Revision surgery
        is_extension=True,
        synonyms=["Nonunion repair", "Pseudarthrosis revision",
                  "Failed fusion revision", "Pseudoarthrosis repair"],
        abbreviations=["PAR"],
        korean_term="가관절 수복술",
    ),
    "Hardware Removal": SNOMEDMapping(
        code="900000000000150",
        term="Removal of spinal instrumentation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000148",  # Revision surgery
        is_extension=True,
        synonyms=["Implant removal", "Screw removal", "Rod removal",
                  "Instrumentation removal", "Spinal hardware removal"],
        abbreviations=["HWR"],
        korean_term="내고정물 제거술",
    ),
    "Adjacent Segment Surgery": SNOMEDMapping(
        code="900000000000151",
        term="Adjacent segment surgery of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000148",  # Revision surgery
        is_extension=True,
        synonyms=["Adjacent segment fusion", "Adjacent level surgery",
                  "Proximal junction surgery", "Distal junction surgery"],
        abbreviations=["ASS"],
        korean_term="인접 분절 수술",
    ),

    # --- TUMOR-SPECIFIC PROCEDURES ---
    "En Bloc Resection": SNOMEDMapping(
        code="900000000000152",
        term="En bloc resection of spinal tumor",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="387714009",  # Microsurgical technique (closest surgical parent)
        is_extension=True,
        synonyms=["En bloc spondylectomy", "Total en bloc spondylectomy",
                  "Marginal resection", "Wide excision of spine tumor"],
        abbreviations=["TES"],
        korean_term="일괄 절제술",
    ),
    "Vertebrectomy": SNOMEDMapping(
        code="900000000000179",
        term="Vertebrectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="112730002",  # Corpectomy of vertebral body (parent)
        is_extension=True,
        synonyms=["Total vertebrectomy", "Partial vertebrectomy",
                  "Spondylectomy"],
        abbreviations=["VBT"],
        korean_term="척추체 절제술",
        notes="Extension: corpectomy(112730002)와 유사하나 전체/부분 절제 구분",
    ),
    "Tumor Debulking": SNOMEDMapping(
        code="900000000000153",
        term="Debulking of spinal tumor",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Intralesional resection", "Subtotal resection",
                  "Tumor decompression", "Intralesional excision"],
        abbreviations=["TDB"],
        korean_term="종양 감축술",
    ),
    "Separation Surgery": SNOMEDMapping(
        code="900000000000154",
        term="Tumor separation surgery of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Tumor separation surgery", "Circumferential decompression",
                  "Epidural tumor separation"],
        abbreviations=["SS"],
        korean_term="종양 분리 수술",
        notes="Separating tumor from spinal cord, often followed by SBRT",
    ),
    "Spinal Tumor Surgery": SNOMEDMapping(
        code="900000000000155",
        term="Spinal tumor surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="5765005",  # Decompression of spinal cord
        is_extension=True,
        synonyms=["Spine tumor surgery", "Spinal tumor resection",
                  "Tumor excision of spine"],
        abbreviations=["STS"],
        korean_term="척추 종양 수술",
    ),

    # --- INJECTION & PAIN MANAGEMENT ---
    "ESI": SNOMEDMapping(
        code="231255002",
        term="Epidural steroid injection",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Epidural Steroid Injection", "Epidural injection",
                  "Transforaminal epidural", "Interlaminar epidural",
                  "Caudal epidural"],
        abbreviations=["ESI", "TFESI"],
        korean_term="경막외 스테로이드 주사",
    ),
    "Facet Injection": SNOMEDMapping(
        code="90743009",
        term="Injection into facet joint",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Facet joint injection", "Facet block",
                  "Medial branch block"],
        abbreviations=["MBB"],
        korean_term="후관절 주사",
    ),
    "RFA": SNOMEDMapping(
        code="395219008",
        term="Radiofrequency ablation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Radiofrequency Ablation", "Radiofrequency neurotomy",
                  "Facet rhizotomy", "Medial branch ablation",
                  "Radiofrequency denervation"],
        abbreviations=["RFA", "RFN"],
        korean_term="고주파 열응고술",
    ),
    "SCS": SNOMEDMapping(
        code="50101000",
        term="Spinal cord stimulation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Spinal Cord Stimulation", "Spinal cord stimulator",
                  "Dorsal column stimulation", "Neurostimulation"],
        abbreviations=["SCS", "DCS"],
        korean_term="척수 자극술",
    ),
    "Intrathecal Pump": SNOMEDMapping(
        code="271564009",
        term="Intrathecal drug delivery system",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["ITB pump", "Intrathecal baclofen", "Intrathecal drug delivery",
                  "Morphine pump", "Intrathecal pump implantation"],
        abbreviations=["ITB", "IDDS"],
        korean_term="경막내 약물 펌프",
    ),
    "Nerve Block": SNOMEDMapping(
        code="11777006",
        term="Nerve block",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Selective nerve root block", "Root block",
                  "Spinal nerve block", "Selective nerve block"],
        abbreviations=["SNRB"],
        korean_term="신경 차단술",
    ),
    "Trigger Point Injection": SNOMEDMapping(
        code="900000000000156",
        term="Trigger point injection",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="11777006",  # Nerve block
        is_extension=True,
        synonyms=["TPI", "Muscle injection", "Myofascial trigger point injection"],
        abbreviations=["TPI"],
        korean_term="통증 유발점 주사",
    ),
    "PRP Injection": SNOMEDMapping(
        code="900000000000157",
        term="Platelet-rich plasma injection for spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Platelet-rich plasma", "PRP therapy",
                  "Autologous PRP injection"],
        abbreviations=["PRP"],
        korean_term="자가 혈소판 풍부 혈장 주사",
    ),
    "Intradiscal injection": SNOMEDMapping(
        code="900000000000158",
        term="Intradiscal injection",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Intradiscal steroid injection", "Disc injection",
                  "Intradiscal therapy"],
        abbreviations=["IDI"],
        korean_term="추간판 내 주사",
    ),
    "Spinal Injection Therapy": SNOMEDMapping(
        code="900000000000159",
        term="Spinal injection therapy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Spinal injection", "Interventional spine procedure"],
        abbreviations=["SIT"],
        korean_term="척추 주사 치료",
    ),
    "Neuromodulation": SNOMEDMapping(
        code="900000000000160",
        term="Spinal neuromodulation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="50101000",  # Spinal cord stimulation
        is_extension=True,
        synonyms=["Spinal cord neuromodulation", "Neuromodulation therapy",
                  "Electrical neuromodulation"],
        abbreviations=["NM", "SCS"],
        korean_term="신경조절술",
    ),

    # --- MINIMALLY INVASIVE (EXPANDED) ---
    "Percutaneous Pedicle Screw": SNOMEDMapping(
        code="900000000000161",
        term="Percutaneous pedicle screw fixation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="40388003",  # Insertion of pedicle screw
        is_extension=True,
        synonyms=["Percutaneous fixation", "Percutaneous instrumentation",
                  "Minimally invasive fixation", "Percutaneous screw"],
        abbreviations=["PPS"],
        korean_term="경피적 척추경 나사못 고정술",
    ),
    "MIS-OLIF": SNOMEDMapping(
        code="900000000000162",
        term="Minimally invasive oblique lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000101",  # OLIF
        is_extension=True,
        synonyms=["Minimally Invasive OLIF", "MIS oblique fusion"],
        abbreviations=["MIS-OLIF"],
        korean_term="최소침습 사측방 요추 추체간 유합술",
    ),
    "MIS-LLIF": SNOMEDMapping(
        code="900000000000163",
        term="Minimally invasive lateral lumbar interbody fusion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="450436003",  # LLIF
        is_extension=True,
        synonyms=["Minimally Invasive LLIF", "MIS lateral fusion",
                  "Mini-open lateral"],
        abbreviations=["MIS-LLIF"],
        korean_term="최소침습 외측 요추 추체간 유합술",
    ),

    # --- DEFORMITY-SPECIFIC ---
    "Anterior Release": SNOMEDMapping(
        code="900000000000164",
        term="Anterior spinal release",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="179097009",  # Osteotomy of spine
        is_extension=True,
        synonyms=["Anterior spinal release", "Anterior discectomy",
                  "Anterior release for deformity correction"],
        abbreviations=["AR"],
        korean_term="전방 유리술",
    ),
    "MAGEC Rod": SNOMEDMapping(
        code="900000000000165",
        term="Magnetically controlled growing rod insertion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["Magnetically controlled growing rod", "Growing rod",
                  "Magnetic growing rod", "Growth-friendly instrumentation"],
        abbreviations=["MCGR", "MAGEC"],
        korean_term="자기 조절 성장봉 삽입술",
    ),
    "Halo Traction": SNOMEDMapping(
        code="52528003",
        term="Halo traction",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        synonyms=["Halo-gravity traction", "Skull traction", "Halo vest",
                  "Halo fixation", "Halo-gravity distraction"],
        korean_term="할로 견인술",
    ),

    # --- INFECTION-SPECIFIC ---
    "I&D": SNOMEDMapping(
        code="40701008",
        term="Irrigation and debridement",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Irrigation and Debridement", "Washout",
                  "Surgical irrigation", "Surgical washout"],
        abbreviations=["I&D", "I and D"],
        korean_term="세척 및 변연 절제술",
    ),
    "Antibiotic Spacer": SNOMEDMapping(
        code="900000000000166",
        term="Antibiotic-impregnated spacer insertion",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        is_extension=True,
        synonyms=["Cement spacer", "PMMA spacer with antibiotics",
                  "Antibiotic cement spacer", "Antibiotic-loaded bone cement"],
        korean_term="항생제 스페이서 삽입술",
    ),
    "Staged Reconstruction": SNOMEDMapping(
        code="900000000000167",
        term="Staged spinal reconstruction",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="122465003",  # Fusion of spine
        is_extension=True,
        synonyms=["Two-stage reconstruction", "Staged fusion",
                  "Delayed reconstruction", "Multi-stage spinal reconstruction"],
        korean_term="단계적 재건술",
    ),

    # --- RADIOTHERAPY ---
    "Radiotherapy": SNOMEDMapping(
        code="108290001",
        term="Radiation therapy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        synonyms=["Radiation therapy", "Radiation treatment",
                  "Spine radiation", "Therapeutic irradiation"],
        abbreviations=["RT"],
        korean_term="방사선 치료",
    ),
    "SABR": SNOMEDMapping(
        code="900000000000168",
        term="Stereotactic ablative body radiotherapy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="108290001",  # Radiation therapy
        is_extension=True,
        synonyms=["Stereotactic Ablative Body Radiotherapy",
                  "Stereotactic ablative radiotherapy"],
        abbreviations=["SABR"],
        korean_term="정위적 체부 절제 방사선치료",
    ),
    "SBRT": SNOMEDMapping(
        code="900000000000169",
        term="Stereotactic body radiation therapy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="108290001",  # Radiation therapy
        is_extension=True,
        synonyms=["Stereotactic Body Radiation Therapy",
                  "Stereotactic body radiotherapy", "Spine SBRT"],
        abbreviations=["SBRT"],
        korean_term="정위적 체부 방사선치료",
        notes="SBRT and SABR are often used interchangeably",
    ),
    "Spine Radiation Therapy": SNOMEDMapping(
        code="900000000000170",
        term="Radiation therapy of spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="108290001",  # Radiation therapy
        is_extension=True,
        synonyms=["Spinal radiation", "Spinal irradiation",
                  "Spine radiation treatment"],
        abbreviations=["SRT", "SBRT", "SRS"],
        korean_term="척추 방사선 치료",
    ),

    # --- CRANIOCERVICAL PROCEDURES ---
    "Craniocervical Junction Surgery": SNOMEDMapping(
        code="900000000000171",
        term="Craniocervical junction surgery",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="112729007",  # Posterior cervical fusion
        is_extension=True,
        synonyms=["Craniocervical surgery", "CVJ surgery",
                  "Craniovertebral junction surgery"],
        abbreviations=["CVJ"],
        korean_term="두개경추 접합부 수술",
    ),
    "Craniocervical stabilization": SNOMEDMapping(
        code="900000000000172",
        term="Craniocervical stabilization",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000171",  # Craniocervical junction surgery
        is_extension=True,
        synonyms=["Craniocervical fixation", "CVJ stabilization",
                  "Occipitocervical stabilization"],
        abbreviations=["CCS", "OCF"],
        korean_term="두개경추 안정화술",
    ),

    # --- FIXATION VARIANTS ---
    "Posterior C1-C2 screw fixation": SNOMEDMapping(
        code="900000000000173",
        term="Posterior C1-C2 screw fixation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="44337006",  # Arthrodesis of atlantoaxial joint (C1-C2 Fusion)
        is_extension=True,
        synonyms=["C1-C2 screw fixation", "Harms technique",
                  "C1 lateral mass C2 pedicle screw", "Goel-Harms technique"],
        abbreviations=["C1-C2 fixation"],
        korean_term="후방 C1-C2 나사못 고정술",
    ),
    "S2AI screw fixation": SNOMEDMapping(
        code="900000000000174",
        term="S2-alar-iliac screw fixation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["S2AI", "S2-alar-iliac screw", "S2 alar iliac",
                  "S2AI screw", "Second sacral alar-iliac screw"],
        abbreviations=["S2AI"],
        korean_term="제2천추 장골 나사못 고정술",
    ),
    "Iliac screw fixation": SNOMEDMapping(
        code="900000000000175",
        term="Iliac screw fixation",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="33620004",  # Instrumented fusion of spine
        is_extension=True,
        synonyms=["Iliac screw", "Iliac bolt", "Iliac fixation",
                  "Iliac bolt fixation"],
        abbreviations=["ISF", "S2AI"],
        korean_term="장골 나사못 고정술",
    ),

    # --- TRANSORAL / TRANSNASAL APPROACHES ---
    "Transnasal odontoidectomy": SNOMEDMapping(
        code="900000000000176",
        term="Transnasal odontoidectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000171",  # Craniocervical junction surgery
        is_extension=True,
        synonyms=["Transnasal odontoid resection", "Endoscopic odontoidectomy",
                  "Endoscopic transnasal odontoidectomy"],
        abbreviations=["TNO"],
        korean_term="경비 치돌기 절제술",
    ),
    "Transoral Approach": SNOMEDMapping(
        code="900000000000177",
        term="Transoral approach to spine",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000171",  # Craniocervical junction surgery
        is_extension=True,
        synonyms=["Transoral surgery", "Transoral decompression",
                  "Transoral approach to craniocervical junction"],
        abbreviations=["TOA"],
        korean_term="경구 접근법",
    ),
    "Transoral odontoidectomy": SNOMEDMapping(
        code="900000000000178",
        term="Transoral odontoidectomy",
        semantic_type=SNOMEDSemanticType.PROCEDURE,
        parent_code="900000000000177",  # Transoral approach
        is_extension=True,
        synonyms=["Transoral odontoid resection", "Transoral dens resection"],
        abbreviations=["TOO"],
        korean_term="경구 치돌기 절제술",
    ),
}


# ============================================================================
# PATHOLOGY MAPPINGS - Spine Conditions
# ============================================================================

SPINE_PATHOLOGY_SNOMED: dict[str, SNOMEDMapping] = {
    # === DEGENERATIVE ===
    "Lumbar Stenosis": SNOMEDMapping(
        code="18347007",
        term="Spinal stenosis of lumbar region",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["LSS", "Lumbar spinal stenosis", "Central stenosis"],
    ),
    "Cervical Stenosis": SNOMEDMapping(
        code="427371002",
        term="Spinal stenosis of cervical region",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["CSS", "Cervical spinal stenosis"],
    ),
    "Foraminal Stenosis": SNOMEDMapping(
        code="202708005",
        term="Foraminal stenosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Neural foraminal stenosis"],
    ),
    "Lumbar Disc Herniation": SNOMEDMapping(
        code="76107001",
        term="Prolapsed lumbar intervertebral disc",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["LDH", "HNP", "HIVD", "Lumbar disc prolapse"],
    ),
    "Cervical Disc Herniation": SNOMEDMapping(
        code="60022001",
        term="Prolapsed cervical intervertebral disc",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["CDH", "Cervical disc prolapse"],
    ),
    "DDD": SNOMEDMapping(
        code="77547008",
        term="Degenerative disc disease",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Degenerative disc disorder", "Intervertebral disc degeneration"],
    ),
    "Facet Arthropathy": SNOMEDMapping(
        code="81680005",
        term="Facet joint syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Facet arthritis", "Zygapophyseal joint disease"],
    ),
    "Spondylolisthesis": SNOMEDMapping(
        code="274152003",
        term="Spondylolisthesis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Degenerative spondylolisthesis", "Slip"],
    ),
    "Degenerative Scoliosis": SNOMEDMapping(
        code="203646004",
        term="Degenerative scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["De novo scoliosis", "Adult degenerative scoliosis"],
    ),

    # === DEFORMITY ===
    "AIS": SNOMEDMapping(
        code="203639008",
        term="Adolescent idiopathic scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Idiopathic scoliosis in adolescent"],
    ),
    "Adult Scoliosis": SNOMEDMapping(
        code="111266001",
        term="Adult scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
    ),
    "Adult Spinal Deformity": SNOMEDMapping(
        code="900000000000201",
        term="Adult spinal deformity",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["ASD syndrome", "Adult degenerative deformity"],
        abbreviations=["ASD"],
        korean_term="성인 척추 변형",
        notes="Umbrella term for various adult deformities including scoliosis and kyphosis",
    ),
    "Flat Back": SNOMEDMapping(
        code="203672002",
        term="Flat back syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Flatback", "Loss of lumbar lordosis", "Iatrogenic flatback"],
        korean_term="편평등 증후군",
    ),
    "Kyphosis": SNOMEDMapping(
        code="414564002",
        term="Kyphosis deformity of spine",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Thoracic kyphosis", "Hyperkyphosis", "Kyphotic deformity"],
        korean_term="후만증",
    ),
    "Sagittal Imbalance": SNOMEDMapping(
        code="900000000000202",
        term="Sagittal plane imbalance",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Sagittal malalignment", "Global sagittal imbalance", "Positive sagittal balance"],
        abbreviations=["GSI"],
        korean_term="시상면 불균형",
        notes="SVA > 50mm typically defines sagittal imbalance",
    ),

    # === TRAUMA ===
    "Compression Fracture": SNOMEDMapping(
        code="207938004",
        term="Compression fracture of vertebra",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["VCF", "Vertebral compression fracture"],
    ),
    "Burst Fracture": SNOMEDMapping(
        code="207939007",
        term="Burst fracture of vertebra",
        semantic_type=SNOMEDSemanticType.DISORDER,
    ),
    "Chance Fracture": SNOMEDMapping(
        code="125616002",
        term="Chance fracture",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Flexion-distraction injury"],
    ),
    "Fracture-Dislocation": SNOMEDMapping(
        code="125609003",
        term="Fracture dislocation of spine",
        semantic_type=SNOMEDSemanticType.DISORDER,
    ),

    # === TUMOR ===
    "Primary Tumor": SNOMEDMapping(
        code="126968001",
        term="Primary neoplasm of vertebral column",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Primary spine tumor"],
    ),
    "Spinal Metastasis": SNOMEDMapping(
        code="94503003",
        term="Metastatic malignant neoplasm to spine",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spine metastasis", "Vertebral metastasis"],
    ),
    "Intradural Tumor": SNOMEDMapping(
        code="900000000000203",
        term="Intradural spinal tumor",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Intradural extramedullary tumor", "Intradural intramedullary tumor", "IDEM", "IDIM"],
        abbreviations=["IDT", "IDEM"],
        korean_term="경막내 척추 종양",
        notes="Includes schwannoma, meningioma, ependymoma",
    ),

    # === INFECTION ===
    "Spondylodiscitis": SNOMEDMapping(
        code="4556007",
        term="Spondylodiscitis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal infection", "Vertebral osteomyelitis"],
    ),
    "Epidural Abscess": SNOMEDMapping(
        code="75607008",
        term="Spinal epidural abscess",
        semantic_type=SNOMEDSemanticType.DISORDER,
    ),
    "Spinal TB": SNOMEDMapping(
        code="186570004",  # Official SNOMED: Tuberculosis of spine
        term="Tuberculosis of spine",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Pott disease", "Spinal tuberculosis", "Pott's disease"],
    ),

    # === MYELOPATHY ===
    "Cervical Myelopathy": SNOMEDMapping(
        code="230529002",
        term="Cervical myelopathy",
        semantic_type=SNOMEDSemanticType.DISORDER,
        # v1.14.1: 동의어 확장
        synonyms=["DCM", "Degenerative cervical myelopathy",
                  "Cervical spondylotic myelopathy", "CSM",
                  "cervical myelopathy", "degenerative cervical myelopathy"],
    ),

    # v1.14.1: Cervical Radiculopathy 추가
    "Cervical Radiculopathy": SNOMEDMapping(
        code="267073000",
        term="Cervical radiculopathy",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Cervical nerve root compression", "Cervical radicular pain",
                  "cervical radiculopathy", "C-spine radiculopathy"],
        korean_term="경추 신경근병증",
    ),

    # v1.14.1: Lumbar Radiculopathy 추가
    "Lumbar Radiculopathy": SNOMEDMapping(
        code="128196005",
        term="Lumbar radiculopathy",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Sciatica", "Lumbar radicular pain", "L-spine radiculopathy",
                  "lumbar radiculopathy", "sciatica", "Radicular leg pain"],
        korean_term="요추 신경근병증",
    ),

    # v1.14.1: Segmental Instability 추가
    "Segmental Instability": SNOMEDMapping(
        code="900000000000206",
        term="Segmental spinal instability",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Lumbar instability", "Spinal instability", "Mechanical instability",
                  "segmental instability", "lumbar instability"],
        abbreviations=["SI"],
        korean_term="분절 불안정성",
        notes="Dynamic instability at a spinal segment, often associated with spondylolisthesis",
    ),

    # v1.14.1: Distal Junctional Kyphosis (DJK) 추가
    "DJK": SNOMEDMapping(
        code="900000000000207",
        term="Distal junctional kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Distal junctional failure", "DJF", "Distal junctional disease",
                  "distal junctional kyphosis"],
        abbreviations=["DJK", "DJF"],
        korean_term="원위부 경계부 후만",
        notes="Kyphotic deformity at or below LIV following spinal fusion",
    ),

    # v1.16.4: PJK를 Pathology에도 추가 (Outcome에는 이미 존재)
    "Proximal Junctional Kyphosis": SNOMEDMapping(
        code="900000000000233",
        term="Proximal junctional kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["PJK", "Proximal junctional failure", "PJF", "Junctional kyphosis"],
        abbreviations=["PJK", "PJF"],
        korean_term="근위부 경계부 후만",
        notes="Pathology entry. >10° increase in kyphosis at UIV. Also in OUTCOME_SNOMED as measurable outcome.",
    ),

    # v1.14.1: Adjacent Segment Disease 추가
    "Adjacent Segment Disease": SNOMEDMapping(
        code="900000000000208",
        term="Adjacent segment disease",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["ASD (Adjacent)", "Adjacent segment degeneration", "Adjacent level disease",
                  "Radiographic ASD", "Symptomatic ASD", "adjacent segment disease"],
        abbreviations=["ASdD", "ASdeg"],
        korean_term="인접 분절 질환",
        notes="Distinct from ASD (Adult Spinal Deformity). Degeneration at levels adjacent to fusion.",
    ),
    "Cauda Equina Syndrome": SNOMEDMapping(
        code="192970008",
        term="Cauda equina syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["CES"],
    ),

    # === COMORBIDITIES / RISK FACTORS ===
    "Diabetes Mellitus": SNOMEDMapping(
        code="73211009",
        term="Diabetes mellitus",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Diabetes", "DM", "Diabetic"],
        korean_term="당뇨병",
        notes="Major risk factor for surgical site infection, poor wound healing",
    ),


    # ========================================
    # v1.17: Additional Pathology SNOMED Mappings
    # ========================================
# ========================================
    # INFECTION (Expanded) - v1.17
    # ========================================
    "Pyogenic Spondylodiscitis": SNOMEDMapping(
        code="900000000000209",
        term="Pyogenic spondylodiscitis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="4556007",  # Spondylodiscitis
        synonyms=["Pyogenic infection", "Bacterial spondylodiscitis",
                  "Pyogenic vertebral osteomyelitis"],
        abbreviations=["PSD"],
        korean_term="화농성 척추염",
        notes="Bacterial spinal infection, most common form of spondylodiscitis",
    ),
    "Fungal Spondylitis": SNOMEDMapping(
        code="900000000000210",
        term="Fungal spondylitis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="4556007",  # Spondylodiscitis
        synonyms=["Fungal spinal infection", "Aspergillus spondylitis",
                  "Mycotic spondylodiscitis"],
        korean_term="진균성 척추염",
        notes="Rare spinal infection caused by fungi, often in immunocompromised patients",
    ),
    "Postoperative Infection": SNOMEDMapping(
        code="900000000000211",
        term="Postoperative spinal infection",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="4556007",  # Spondylodiscitis
        synonyms=["Surgical site infection", "SSI", "Wound infection",
                  "Postoperative wound infection"],
        abbreviations=["POI", "SSI"],
        korean_term="수술 후 감염",
        notes="Infection following spine surgery, includes superficial and deep SSI",
    ),

    # ========================================
    # CERVICAL-SPECIFIC PATHOLOGIES - v1.17
    # ========================================
    "OPLL": SNOMEDMapping(
        code="88199009",
        term="Ossification of posterior longitudinal ligament",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["OPLL", "Posterior longitudinal ligament ossification",
                  "PLL ossification"],
        abbreviations=["OPLL"],
        korean_term="후종인대 골화증",
    ),
    "OLF": SNOMEDMapping(
        code="900000000000212",
        term="Ossification of ligamentum flavum",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Ligamentum flavum ossification", "Yellow ligament ossification",
                  "OLF thoracic"],
        abbreviations=["OLF"],
        korean_term="황색인대 골화증",
        notes="Most common in thoracic spine, can cause myelopathy",
    ),
    "Atlantoaxial Instability": SNOMEDMapping(
        code="307721000",
        term="Atlantoaxial instability",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["C1-C2 instability", "AAI", "Atlantoaxial subluxation"],
        abbreviations=["AAI"],
        korean_term="환축추 불안정",
    ),
    "Os Odontoideum": SNOMEDMapping(
        code="900000000000213",
        term="Os odontoideum",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Os odontoideum anomaly", "Odontoid ossicle",
                  "Separated odontoid process"],
        abbreviations=["OO"],
        korean_term="치돌기 이상",
        notes="Anomalous bone replacing the odontoid process, may cause atlantoaxial instability",
    ),
    "Klippel-Feil Syndrome": SNOMEDMapping(
        code="268268009",
        term="Klippel-Feil syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Klippel-Feil", "Congenital cervical fusion",
                  "Congenital cervical synostosis"],
        korean_term="클리펠-파일 증후군",
    ),
    "Basilar Invagination": SNOMEDMapping(
        code="253105001",
        term="Basilar invagination",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Basilar impression", "Cranial settling",
                  "Upward migration of odontoid"],
        korean_term="두개저 함입증",
    ),

    # ========================================
    # ADDITIONAL DEGENERATIVE PATHOLOGIES - v1.17
    # ========================================
    "DISH": SNOMEDMapping(
        code="156849009",
        term="Diffuse idiopathic skeletal hyperostosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Forestier disease", "Forestier's disease",
                  "Ankylosing hyperostosis"],
        abbreviations=["DISH"],
        korean_term="미만성 특발성 골격 과골증",
    ),
    "Baastrup Disease": SNOMEDMapping(
        code="900000000000214",
        term="Baastrup disease",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Kissing spine syndrome", "Interspinous bursitis",
                  "Kissing spines"],
        abbreviations=["KD"],
        korean_term="바스트루프병",
        notes="Contact and friction between adjacent spinous processes",
    ),
    "Bertolotti Syndrome": SNOMEDMapping(
        code="900000000000215",
        term="Bertolotti syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Lumbosacral transitional vertebra", "LSTV",
                  "Sacralization", "Lumbarization"],
        abbreviations=["BS", "LSTV"],
        korean_term="베르톨로티 증후군",
        notes="Low back pain associated with lumbosacral transitional vertebra",
    ),
    "Synovial Cyst": SNOMEDMapping(
        code="900000000000216",
        term="Synovial cyst of spine",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Facet cyst", "Juxta-articular cyst",
                  "Juxtafacet cyst", "Ganglion cyst of spine"],
        abbreviations=["SC"],
        korean_term="활막낭종",
        notes="Cyst arising from facet joint, often causes radiculopathy or stenosis",
    ),
    "Tarlov Cyst": SNOMEDMapping(
        code="900000000000217",
        term="Tarlov cyst",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Perineural cyst", "Sacral nerve root cyst",
                  "Sacral perineural cyst"],
        abbreviations=["TC", "PNC"],
        korean_term="타를로프 낭종",
        notes="Fluid-filled cyst on sacral nerve roots, usually incidental finding",
    ),
    "Modic Changes": SNOMEDMapping(
        code="900000000000218",
        term="Modic vertebral endplate changes",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Modic type 1", "Modic type 2", "Modic type 3",
                  "Endplate changes", "Vertebral endplate signal changes"],
        abbreviations=["MC"],
        korean_term="모딕 변화",
        notes="MRI signal changes in vertebral endplates: Type 1 (edema), Type 2 (fatty), Type 3 (sclerosis)",
    ),
    "Failed Back Surgery Syndrome": SNOMEDMapping(
        code="900000000000219",
        term="Failed back surgery syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["FBSS", "Post-laminectomy syndrome",
                  "Persistent pain after spinal surgery",
                  "Post-surgical spine syndrome"],
        abbreviations=["FBSS"],
        korean_term="척추수술후 증후군",
        notes="Chronic pain persisting or recurring after spinal surgery",
    ),

    # ========================================
    # TUMOR-SPECIFIC PATHOLOGIES (Expanded) - v1.17
    # ========================================
    "Hemangioma": SNOMEDMapping(
        code="400210000",
        term="Hemangioma of vertebral body",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Vertebral hemangioma", "Spinal hemangioma",
                  "Aggressive hemangioma"],
        korean_term="척추 혈관종",
    ),
    "Giant Cell Tumor": SNOMEDMapping(
        code="88349003",
        term="Giant cell tumor of bone",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["GCT", "Osteoclastoma", "Giant cell tumor of spine"],
        abbreviations=["GCT"],
        korean_term="거대세포종",
    ),
    "Osteoblastoma": SNOMEDMapping(
        code="55333008",
        term="Osteoblastoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Osteoid osteoma", "Benign osteoblastoma",
                  "Spinal osteoblastoma"],
        korean_term="골모세포종",
    ),
    "Ewing Sarcoma": SNOMEDMapping(
        code="33167000",
        term="Ewing sarcoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Ewing's sarcoma", "PNET",
                  "Primitive neuroectodermal tumor",
                  "Ewing sarcoma of spine"],
        korean_term="유잉 육종",
    ),
    "Multiple Myeloma": SNOMEDMapping(
        code="109989006",
        term="Multiple myeloma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Plasmacytoma", "Plasma cell neoplasm",
                  "Spinal myeloma", "Solitary plasmacytoma"],
        korean_term="다발성 골수종",
    ),
    "Chordoma": SNOMEDMapping(
        code="53659009",
        term="Chordoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Sacral chordoma", "Clival chordoma",
                  "Spinal chordoma", "Vertebral chordoma"],
        korean_term="척삭종",
    ),
    "Schwannoma": SNOMEDMapping(
        code="7851007",
        term="Schwannoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal schwannoma", "Neurilemmoma",
                  "Vestibular schwannoma", "Nerve sheath tumor"],
        korean_term="신경초종",
    ),
    "Meningioma": SNOMEDMapping(
        code="7051007",
        term="Meningioma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal meningioma", "Intradural meningioma",
                  "Meningioma of spinal canal"],
        korean_term="수막종",
    ),
    "Ependymoma": SNOMEDMapping(
        code="443485007",
        term="Ependymoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal ependymoma", "Myxopapillary ependymoma",
                  "Intramedullary ependymoma"],
        korean_term="상의세포종",
    ),
    "Neurofibroma": SNOMEDMapping(
        code="92539004",
        term="Neurofibroma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal neurofibroma", "Neurofibromatosis",
                  "Plexiform neurofibroma"],
        korean_term="신경섬유종",
    ),
    "Osteosarcoma": SNOMEDMapping(
        code="21708004",
        term="Osteosarcoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal osteosarcoma", "Osteogenic sarcoma",
                  "Osteosarcoma of spine"],
        korean_term="골육종",
    ),
    "Chondrosarcoma": SNOMEDMapping(
        code="443520009",
        term="Chondrosarcoma",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Spinal chondrosarcoma", "Chondrosarcoma of spine"],
        korean_term="연골육종",
    ),

    # ========================================
    # INFLAMMATORY/RHEUMATOLOGIC PATHOLOGIES - v1.17
    # ========================================
    "Ankylosing Spondylitis": SNOMEDMapping(
        code="9631008",
        term="Ankylosing spondylitis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["AS", "Bamboo spine", "Marie-Strumpell disease",
                  "Bechterew disease"],
        abbreviations=["AS"],
        korean_term="강직성 척추염",
    ),
    "Rheumatoid Arthritis": SNOMEDMapping(
        code="69896004",
        term="Rheumatoid arthritis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["RA", "Cervical RA", "Rheumatoid arthritis of cervical spine"],
        abbreviations=["RA"],
        korean_term="류마티스 관절염",
    ),
    "Psoriatic Arthritis": SNOMEDMapping(
        code="156370009",
        term="Psoriatic arthritis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Psoriatic spondylitis", "PsA",
                  "Psoriatic spondyloarthritis"],
        abbreviations=["PsA"],
        korean_term="건선성 관절염",
    ),
    "Reactive Arthritis": SNOMEDMapping(
        code="900000000000220",
        term="Reactive arthritis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Reiter syndrome", "Reiter's syndrome",
                  "Post-infectious arthritis"],
        abbreviations=["ReA"],
        korean_term="반응성 관절염",
        notes="Spondyloarthritis triggered by infection, formerly Reiter syndrome",
    ),
    "Enteropathic Arthritis": SNOMEDMapping(
        code="900000000000221",
        term="Enteropathic arthritis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["IBD-associated spondylitis", "Crohn's spine",
                  "IBD-related arthritis", "Inflammatory bowel disease arthritis"],
        abbreviations=["EA"],
        korean_term="장병성 관절염",
        notes="Spondyloarthritis associated with inflammatory bowel disease (Crohn's, UC)",
    ),
    "SAPHO Syndrome": SNOMEDMapping(
        code="900000000000222",
        term="SAPHO syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Synovitis, Acne, Pustulosis, Hyperostosis, Osteitis",
                  "SAPHO", "Acquired hyperostosis syndrome"],
        abbreviations=["SAPHO"],
        korean_term="사포 증후군",
        notes="Rare inflammatory disorder with bone/joint/skin manifestations",
    ),

    # ========================================
    # DEFORMITY (Expanded) - v1.17
    # ========================================
    "Congenital Scoliosis": SNOMEDMapping(
        code="205045003",
        term="Congenital scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Congenital spinal deformity", "Hemivertebra",
                  "Congenital vertebral anomaly scoliosis"],
        korean_term="선천성 측만증",
    ),
    "Neuromuscular Scoliosis": SNOMEDMapping(
        code="900000000000232",
        term="Neuromuscular scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["NM scoliosis", "Muscular dystrophy scoliosis",
                  "Cerebral palsy scoliosis", "Paralytic scoliosis"],
        abbreviations=["NMS"],
        korean_term="신경근육성 측만증",
        notes="Extension code. ICD-10: M41.4. Previously shared 111266001 with Adult Scoliosis",
    ),
    "Syndromic Scoliosis": SNOMEDMapping(
        code="900000000000223",
        term="Syndromic scoliosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Marfan scoliosis", "Ehlers-Danlos scoliosis",
                  "Neurofibromatosis scoliosis", "Syndrome-associated scoliosis"],
        korean_term="증후군성 측만증",
        notes="Scoliosis associated with connective tissue or genetic syndromes",
    ),
    "Junctional Kyphosis": SNOMEDMapping(
        code="900000000000224",
        term="Junctional kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="414564002",  # Kyphosis
        synonyms=["Thoracolumbar kyphosis", "TL kyphosis",
                  "Thoracolumbar junctional kyphosis"],
        abbreviations=["JK"],
        korean_term="경계부 후만증",
        notes="Kyphotic deformity at thoracolumbar junction",
    ),
    "Post-laminectomy Kyphosis": SNOMEDMapping(
        code="900000000000225",
        term="Post-laminectomy kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="414564002",  # Kyphosis
        synonyms=["Post-surgical kyphosis", "Iatrogenic kyphosis",
                  "Post-decompression kyphosis"],
        abbreviations=["PLK"],
        korean_term="수술후 후만",
        notes="Kyphotic deformity developing after laminectomy, especially in cervical spine",
    ),

    # ========================================
    # TRAUMA (Expanded) - v1.17
    # ========================================
    "SCIWORA": SNOMEDMapping(
        code="900000000000226",
        term="Spinal cord injury without radiographic abnormality",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Spinal Cord Injury Without Radiographic Abnormality",
                  "SCIWORA syndrome"],
        abbreviations=["SCIWORA"],
        korean_term="방사선학적 이상 없는 척수 손상",
        notes="Pediatric spinal cord injury without fracture/dislocation on plain radiographs",
    ),
    "Hangman Fracture": SNOMEDMapping(
        code="53515004",
        term="Hangman fracture",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["C2 pars fracture", "Traumatic spondylolisthesis of C2",
                  "C2 pars interarticularis fracture"],
        korean_term="행맨 골절",
    ),
    "Jefferson Fracture": SNOMEDMapping(
        code="900000000000227",
        term="Jefferson fracture",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["C1 burst fracture", "Atlas fracture",
                  "C1 ring fracture", "Atlas burst fracture"],
        abbreviations=["C1 Fx"],
        korean_term="제퍼슨 골절",
        notes="Burst fracture of the atlas (C1) with lateral mass displacement",
    ),
    "Odontoid Fracture": SNOMEDMapping(
        code="71030004",
        term="Fracture of odontoid process",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Dens fracture", "Type I/II/III odontoid fracture",
                  "Odontoid process fracture", "C2 dens fracture"],
        korean_term="치돌기 골절",
    ),
    "Sacral Fracture": SNOMEDMapping(
        code="900000000000228",
        term="Sacral fracture",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Sacral insufficiency fracture", "Denis zone fracture",
                  "Sacral stress fracture", "Sacral fragility fracture"],
        abbreviations=["SF"],
        korean_term="천추 골절",
        notes="Includes insufficiency and traumatic fractures; Denis classification zones I-III",
    ),
    "Thoracolumbar Fracture": SNOMEDMapping(
        code="900000000000229",
        term="Thoracolumbar fracture",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["TL fracture", "Thoracolumbar burst",
                  "Thoracolumbar spine fracture",
                  "Thoracolumbar junction fracture"],
        abbreviations=["TLF", "TL Fx"],
        korean_term="흉요추 골절",
        notes="Fracture at T10-L2 thoracolumbar junction, most common spinal fracture location",
    ),

    # ========================================
    # PEDIATRIC PATHOLOGIES - v1.17
    # ========================================
    "Scheuermann Disease": SNOMEDMapping(
        code="64859001",
        term="Scheuermann disease",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Scheuermann kyphosis", "Juvenile kyphosis",
                  "Scheuermann's disease", "Vertebral epiphysitis"],
        korean_term="쇼이어만병",
    ),
    "Spondylolysis": SNOMEDMapping(
        code="240228006",
        term="Spondylolysis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Pars defect", "Pars interarticularis defect",
                  "Isthmic defect", "Pars fracture"],
        korean_term="척추분리증",
    ),
    "Pediatric Disc Herniation": SNOMEDMapping(
        code="900000000000230",
        term="Pediatric disc herniation",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="76107001",  # Prolapsed lumbar intervertebral disc
        synonyms=["Adolescent disc herniation", "Juvenile disc herniation",
                  "Childhood disc herniation"],
        abbreviations=["PDH"],
        korean_term="소아 디스크",
        notes="Disc herniation in patients under 18, different pathophysiology from adult",
    ),
    "Congenital Kyphosis": SNOMEDMapping(
        code="900000000000231",
        term="Congenital kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        parent_code="414564002",  # Kyphosis
        synonyms=["Type I/II congenital kyphosis", "Congenital kyphotic deformity",
                  "Failure of formation kyphosis", "Failure of segmentation kyphosis"],
        abbreviations=["CK"],
        korean_term="선천성 후만",
        notes="Type I (failure of formation) and Type II (failure of segmentation)",
    ),
    "Tethered Cord": SNOMEDMapping(
        code="67224007",
        term="Tethered spinal cord syndrome",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Tethered spinal cord", "Filum terminale syndrome",
                  "Tight filum terminale", "Tethered cord syndrome"],
        korean_term="척수 유착 증후군",
    ),
    "Diastematomyelia": SNOMEDMapping(
        code="89435008",
        term="Diastematomyelia",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Split cord malformation", "Diplomyelia",
                  "Split spinal cord malformation"],
        korean_term="이중 척수",
    ),
}


# ============================================================================
# OUTCOME MAPPINGS - Clinical Measures
# ============================================================================

SPINE_OUTCOME_SNOMED: dict[str, SNOMEDMapping] = {
    # === PAIN MEASURES ===
    "VAS": SNOMEDMapping(
        code="273903006",
        term="Visual analog pain scale",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["VAS pain score", "Visual analog scale"],
    ),
    "VAS Back": SNOMEDMapping(
        code="900000000000301",
        term="Visual analog scale for back pain",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        parent_code="273903006",  # VAS
        is_extension=True,
        synonyms=["VAS back pain", "Back pain VAS"],
        abbreviations=["VAS-BP", "VAS-back"],
        korean_term="요통 시각적 아날로그 척도",
    ),
    "VAS Leg": SNOMEDMapping(
        code="900000000000302",
        term="Visual analog scale for leg pain",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        parent_code="273903006",  # VAS
        is_extension=True,
        synonyms=["VAS leg pain", "Leg pain VAS", "Radicular pain VAS"],
        abbreviations=["VAS-LP", "VAS-leg"],
        korean_term="하지통 시각적 아날로그 척도",
    ),
    "NRS": SNOMEDMapping(
        code="1137229006",
        term="Numeric rating scale for pain",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["Numeric pain scale", "NRS pain"],
    ),

    # === FUNCTIONAL MEASURES ===
    "ODI": SNOMEDMapping(
        code="273545004",
        term="Oswestry Disability Index",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["Oswestry low back pain disability questionnaire"],
    ),
    "NDI": SNOMEDMapping(
        code="273547007",
        term="Neck Disability Index",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
    ),
    "JOA": SNOMEDMapping(
        code="900000000000303",
        term="Japanese Orthopaedic Association score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["JOA score", "JOA cervical score", "JOA lumbar score"],
        abbreviations=["JOA"],
        korean_term="일본정형외과학회 점수",
        notes="0-17 for cervical, 0-29 for lumbar",
    ),
    "mJOA": SNOMEDMapping(
        code="900000000000304",
        term="Modified Japanese Orthopaedic Association score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Modified JOA score", "mJOA cervical"],
        abbreviations=["mJOA"],
        korean_term="수정 일본정형외과학회 점수",
        notes="0-18 scale for cervical myelopathy severity",
    ),
    "EQ-5D": SNOMEDMapping(
        code="736534008",
        term="EQ-5D questionnaire score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["EuroQol 5 dimensions"],
    ),
    "SF-36": SNOMEDMapping(
        code="445537008",
        term="Short Form 36 health survey",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
    ),
    "SRS-22": SNOMEDMapping(
        code="900000000000305",
        term="Scoliosis Research Society 22 questionnaire",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["SRS-22r", "SRS-30", "SRS outcome questionnaire"],
        abbreviations=["SRS-22", "SRS-22r"],
        korean_term="측만증연구학회 22 설문",
        notes="Domains: function, pain, self-image, mental health, satisfaction",
    ),

    # === RADIOLOGICAL MEASURES ===
    "Fusion Rate": SNOMEDMapping(
        code="900000000000306",
        term="Bone fusion rate",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Union rate", "Solid fusion rate", "Arthrodesis rate"],
        abbreviations=["FR"],
        korean_term="골유합률",
        notes="Typically assessed by CT or dynamic X-ray",
    ),
    "Cage Subsidence": SNOMEDMapping(
        code="900000000000501",
        term="Interbody cage subsidence",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Cage settling", "Interbody subsidence", "Cage sinking"],
        abbreviations=["CS"],
        korean_term="케이지 침강",
        notes=">2mm settling is typically considered significant",
    ),
    "Lordosis": SNOMEDMapping(
        code="298003004",
        term="Lumbar lordosis measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["Lumbar lordosis", "Segmental lordosis"],
        abbreviations=["LL"],
        korean_term="요추 전만",
    ),
    "Cobb Angle": SNOMEDMapping(
        code="252495004",
        term="Cobb angle measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        synonyms=["Scoliosis angle", "Coronal Cobb angle"],
        korean_term="콥 각도",
    ),
    "SVA": SNOMEDMapping(
        code="900000000000307",
        term="Sagittal vertical axis",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["C7 plumbline", "Sagittal balance"],
        abbreviations=["SVA", "C7-S1 SVA"],
        korean_term="시상면 수직축",
        notes="Measured from C7 plumbline to posterior S1, normal <50mm",
    ),
    "PT": SNOMEDMapping(
        code="900000000000308",
        term="Pelvic tilt measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Pelvic retroversion", "Pelvic tilt angle"],
        abbreviations=["PT"],
        korean_term="골반 기울기",
        notes="Angle between vertical and line from sacral endplate to hip axis",
    ),
    "PI-LL": SNOMEDMapping(
        code="900000000000309",
        term="Pelvic incidence minus lumbar lordosis",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["PI-LL mismatch", "Spinopelvic mismatch"],
        abbreviations=["PI-LL"],
        korean_term="골반입사각-요추전만 불일치",
        notes="Normal PI-LL < 10°, >10° indicates mismatch",
    ),

    # === COMPLICATION MEASURES ===
    "Complication Rate": SNOMEDMapping(
        code="116223007",
        term="Complication of procedure",
        semantic_type=SNOMEDSemanticType.FINDING,
    ),
    "Dural Tear": SNOMEDMapping(
        code="262540006",
        term="Tear of dura mater",
        semantic_type=SNOMEDSemanticType.FINDING,
        synonyms=["Incidental durotomy", "Dural laceration"],
    ),
    "Nerve Injury": SNOMEDMapping(
        code="212992005",
        term="Injury of nerve root",
        semantic_type=SNOMEDSemanticType.FINDING,
    ),
    "Infection Rate": SNOMEDMapping(
        code="128601007",
        term="Surgical site infection",
        semantic_type=SNOMEDSemanticType.FINDING,
        synonyms=["SSI", "SSI rate", "Postoperative infection"],
        korean_term="수술 부위 감염률",
    ),
    "Superficial Surgical Site Infection": SNOMEDMapping(
        code="433202001",
        term="Superficial incisional surgical site infection",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Superficial SSI", "Superficial wound infection", "Wound infection"],
        korean_term="표재성 수술 부위 감염",
        notes="Infection of skin and subcutaneous tissue only, within 30 days of surgery",
    ),
    "Deep Surgical Site Infection": SNOMEDMapping(
        code="433201008",
        term="Deep incisional surgical site infection",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Deep SSI", "Deep wound infection", "Deep infection"],
        korean_term="심부 수술 부위 감염",
        notes="Infection involving fascia, muscle, or implant; may require surgical debridement",
    ),
    "Reoperation Rate": SNOMEDMapping(
        code="900000000000310",
        term="Reoperation rate",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Revision rate", "Secondary surgery rate", "Reintervention rate"],
        abbreviations=["RR", "ReOp"],
        korean_term="재수술률",
    ),
    # v1.14.14 수정: Adjacent Segment Disease는 SPINE_PATHOLOGY_SNOMED에서 정의됨 (900000000000208)
    # Outcome에서는 "ASD Reoperation Rate"로 재정의
    "ASD Reoperation Rate": SNOMEDMapping(
        code="900000000000204",
        term="Adjacent segment disease reoperation rate",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["ASD reoperation", "Adjacent segment reoperation rate", "Junctional reoperation"],
        abbreviations=["ASD-RR"],
        korean_term="인접 분절 재수술률",
        notes="Rate of reoperation due to adjacent segment disease",
    ),
    "PJK": SNOMEDMapping(
        code="900000000000205",
        term="Proximal junctional kyphosis",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Proximal junctional failure", "PJF", "Junctional kyphosis"],
        abbreviations=["PJK", "PJF"],
        korean_term="근위부 경계부 후만",
        notes=">10° increase in kyphosis at UIV defines PJK",
    ),

    # v1.14 추가: Serum CPK (근육 손상 지표)
    "Serum CPK": SNOMEDMapping(
        code="900000000000311",
        term="Serum creatine phosphokinase level",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["CPK level", "Creatine kinase", "CK level", "Serum CK",
                  "Creatine phosphokinase", "Muscle enzyme level"],
        abbreviations=["CPK", "CK"],
        korean_term="혈청 크레아틴 키나제",
        notes="Marker for muscle damage, commonly measured in lateral approach surgeries (OLIF, LLIF)",
    ),

    # v1.14 추가: Scar Quality (상처 미용 결과)
    "Scar Quality": SNOMEDMapping(
        code="900000000000312",
        term="Surgical scar quality assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Wound cosmesis", "Scar appearance", "Cosmetic outcome",
                  "Scar assessment", "Wound healing quality"],
        korean_term="수술 흉터 품질",
        notes="Assessment of wound cosmesis, relevant for minimally invasive vs open comparisons",
    ),

    # v1.14 추가: Postoperative Drainage (배액량)
    "Postoperative Drainage": SNOMEDMapping(
        code="900000000000313",
        term="Postoperative drainage volume",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Drainage volume", "Drain output", "Wound drainage",
                  "Hemovac output", "Surgical drain volume"],
        korean_term="수술 후 배액량",
        notes="Total drainage volume from surgical wound, indicator of bleeding/tissue trauma",
    ),

    # v1.16.4: DVT (심부정맥혈전증) - 척추 수술 주요 합병증
    "DVT": SNOMEDMapping(
        code="900000000000502",
        term="Deep vein thrombosis after spinal surgery",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Deep vein thrombosis", "Venous thromboembolism",
                  "Postoperative DVT", "Thromboembolism"],
        abbreviations=["DVT", "VTE"],
        korean_term="심부정맥혈전증",
        notes="Common complication after prolonged spine surgery; risk increases with prone position",
    ),

    # v1.16.4: Screw Malposition (나사못 위치불량) - 기존 503은 225553008로 대체되어 재할당
    "Screw Malposition": SNOMEDMapping(
        code="900000000000503",
        term="Pedicle screw malposition",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Screw misplacement", "Pedicle screw breach",
                  "Screw malpositioning", "Cortical breach",
                  "Screw perforation"],
        abbreviations=["PSM", "PSB"],
        korean_term="나사못 위치불량",
        notes="Pedicle screw placed outside the pedicle cortex; graded by breach severity",
    ),

    # v1.14.14 수정: Wound Dehiscence - 공식 SNOMED 코드 225553008 사용
    # 이전 extension code 900000000000503은 225553008로 대체됨 → 503 재할당 (Screw Malposition)
    "Wound Dehiscence": SNOMEDMapping(
        code="225553008",
        term="Wound dehiscence",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=False,
        synonyms=["Surgical wound dehiscence", "Wound breakdown", "Dehiscence",
                  "Wound separation", "Incision dehiscence", "Wound disruption"],
        korean_term="창상 열개",
        notes="Partial or complete separation of surgical wound edges",
    ),

    # v1.14 추가: Recurrent Disc Herniation (재발성 디스크 탈출)
    "Recurrent Disc Herniation": SNOMEDMapping(
        code="900000000000504",
        term="Recurrent intervertebral disc herniation",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Recurrent herniated disc", "Re-herniation", "Recurrent HNP",
                  "Disc re-herniation", "Same-level recurrence"],
        abbreviations=["rDH", "ReHNP"],
        korean_term="재발성 추간판 탈출증",
        notes="Herniation at the same level after previous discectomy, typically within 6 months to 2 years",
    ),

    # v1.14 추가: Epidural Hematoma (경막외 혈종)
    "Epidural Hematoma": SNOMEDMapping(
        code="900000000000505",
        term="Postoperative spinal epidural hematoma",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Postoperative epidural hematoma", "Spinal epidural hematoma",
                  "Epidural bleeding", "Epidural blood collection"],
        abbreviations=["SEH"],
        korean_term="수술 후 경막외 혈종",
        notes="Collection of blood in the epidural space after spine surgery, may require emergency decompression",
    ),

    # v1.14.3 추가: C5 Palsy (C5 마비)
    "C5 Palsy": SNOMEDMapping(
        code="900000000000506",
        term="Postoperative C5 nerve palsy",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["C5 palsy", "C5 nerve palsy", "C5 root palsy",
                  "Postoperative C5 palsy", "C5 radiculopathy"],
        abbreviations=["C5P"],
        korean_term="C5 신경 마비",
        notes="Weakness in deltoid and biceps after cervical spine surgery, typically recovers within 6-12 months",
    ),

    # v1.14.14 수정: Wound Dehiscence 중복 제거됨 - SPINE_OUTCOME_SNOMED에서 정의됨 (225553008)


    # ========================================
    # v1.17: Additional Outcome SNOMED Mappings
    # ========================================
# === PAIN MEASURES - Cervical ===
    "VAS Neck": SNOMEDMapping(
        code="900000000000314",
        term="Visual analog scale for neck pain",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        parent_code="273903006",  # VAS
        is_extension=True,
        synonyms=["VAS neck pain", "Neck pain VAS", "Neck VAS"],
        abbreviations=["VAS-NP", "VAS-neck"],
        korean_term="경부통 시각적 아날로그 척도",
    ),
    "VAS Arm": SNOMEDMapping(
        code="900000000000315",
        term="Visual analog scale for arm pain",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        parent_code="273903006",  # VAS
        is_extension=True,
        synonyms=["VAS arm pain", "Arm pain VAS", "Arm VAS", "Upper extremity pain VAS"],
        abbreviations=["VAS-AP", "VAS-arm"],
        korean_term="상지통 시각적 아날로그 척도",
    ),

    # === FUNCTIONAL MEASURES - Additional ===
    "SF-12": SNOMEDMapping(
        code="445536004",
        term="Short Form 12 health survey",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=False,
        synonyms=["Short Form 12", "SF-12 PCS", "SF-12 MCS"],
        abbreviations=["SF-12", "SF12"],
        korean_term="SF-12 건강 설문",
        notes="12-item subset of SF-36; Physical Component Summary (PCS) and Mental Component Summary (MCS)",
    ),

    # === RADIOLOGICAL MEASURES - Fusion/Structural ===
    "Pseudarthrosis": SNOMEDMapping(
        code="900000000000507",
        term="Pseudarthrosis after spinal fusion",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Pseudoarthrosis", "Nonunion", "Non-union", "Fusion failure",
                  "Failed fusion", "Fibrous nonunion"],
        abbreviations=["PA", "Non-union"],
        korean_term="가관절증",
        notes="Failure of bone healing after attempted spinal fusion; diagnosed by CT or dynamic X-ray",
    ),
    "Disc Height": SNOMEDMapping(
        code="900000000000316",
        term="Intervertebral disc height measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Disc space height", "Disc height index", "Intervertebral height",
                  "Disc height restoration"],
        abbreviations=["DH", "DHI"],
        korean_term="추간판 높이",
        notes="Measured on lateral X-ray; disc height index (DHI) = disc height / vertebral body height",
    ),
    "Foraminal Height": SNOMEDMapping(
        code="900000000000317",
        term="Neural foraminal height measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Neural foraminal height", "Foramen height", "Foraminal area",
                  "Neuroforaminal height"],
        abbreviations=["FH"],
        korean_term="추간공 높이",
        notes="Measured on oblique X-ray or CT; indirect decompression indicator",
    ),
    "Canal Diameter": SNOMEDMapping(
        code="900000000000318",
        term="Spinal canal diameter measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Spinal canal diameter", "Dural sac diameter", "AP diameter",
                  "Canal cross-sectional area", "Thecal sac diameter"],
        abbreviations=["SCD"],
        korean_term="척추관 직경",
        notes="Anteroposterior diameter of spinal canal; measured on axial MRI or CT",
    ),
    "Segmental Angle": SNOMEDMapping(
        code="900000000000319",
        term="Segmental angle measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Segmental lordosis", "Segmental kyphosis", "Segmental alignment",
                  "Intervertebral angle"],
        abbreviations=["SA"],
        korean_term="분절 각도",
        notes="Angle between endplates of adjacent vertebrae at a single motion segment",
    ),
    "Global Balance": SNOMEDMapping(
        code="900000000000320",
        term="Global sagittal balance measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        parent_code="900000000000307",  # SVA
        is_extension=True,
        synonyms=["C7-S1 SVA", "Global sagittal balance", "Full-spine sagittal alignment",
                  "Overall sagittal balance"],
        abbreviations=["GB"],
        korean_term="전체 시상면 균형",
        notes="Global sagittal alignment from C7 plumbline to sacrum; includes T1 pelvic angle (TPA)",
    ),
    "Coronal Balance": SNOMEDMapping(
        code="900000000000321",
        term="Coronal balance measurement",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Coronal alignment", "C7 tilt", "Trunk shift",
                  "Coronal vertical axis", "Coronal plane balance"],
        abbreviations=["CVA"],
        korean_term="관상면 균형",
        notes="Distance from C7 plumbline to CSVL (center sacral vertical line); normal <20mm",
    ),

    # === SURGICAL OUTCOMES ===
    "Operation Time": SNOMEDMapping(
        code="373669009",
        term="Duration of surgical procedure",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=False,
        synonyms=["Operative time", "Surgery time", "Surgical duration",
                  "OR time", "Operating time", "Total operative time"],
        abbreviations=["OT"],
        korean_term="수술 시간",
    ),
    "Blood Loss": SNOMEDMapping(
        code="364074005",
        term="Estimated blood loss",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=False,
        synonyms=["Intraoperative blood loss", "Surgical blood loss",
                  "Total blood loss", "Perioperative blood loss"],
        abbreviations=["EBL"],
        korean_term="출혈량",
    ),
    "Hospital Stay": SNOMEDMapping(
        code="183797002",
        term="Hospital length of stay",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=False,
        synonyms=["Length of stay", "Hospital length of stay", "Hospitalization duration",
                  "Postoperative hospital stay", "Inpatient stay"],
        abbreviations=["LOS"],
        korean_term="재원 기간",
    ),
    "Time to Ambulation": SNOMEDMapping(
        code="900000000000322",
        term="Time to first ambulation after surgery",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Time to walking", "Mobilization time", "Time to first walk",
                  "Early ambulation time"],
        abbreviations=["TTA"],
        korean_term="보행 시작 시간",
        notes="Time from surgery to patient's first independent ambulation",
    ),
    "Return to Work": SNOMEDMapping(
        code="900000000000323",
        term="Time to return to work",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Work return", "Disability duration", "Work resumption",
                  "Return to employment", "Time to return to full activity"],
        abbreviations=["RTW"],
        korean_term="복직 시간",
        notes="Duration from surgery to return to pre-operative work status",
    ),
    "Cost": SNOMEDMapping(
        code="900000000000324",
        term="Treatment cost",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Hospital cost", "Total cost", "Healthcare cost",
                  "Surgical cost", "Cost-effectiveness", "Direct medical cost"],
        korean_term="치료 비용",
        notes="Direct and/or indirect costs associated with surgical treatment and recovery",
    ),

    # === PATIENT SATISFACTION / CLINICAL OUTCOME SCALES ===
    "MacNab": SNOMEDMapping(
        code="900000000000325",
        term="MacNab criteria outcome assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["MacNab criteria", "Modified MacNab criteria", "MacNab classification",
                  "Excellent/Good rate"],
        abbreviations=["MacNab"],
        korean_term="맥냅 기준",
        notes="4-grade scale: Excellent, Good, Fair, Poor; commonly used after discectomy/decompression",
    ),
    "Odom": SNOMEDMapping(
        code="900000000000326",
        term="Odom criteria outcome assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Odom criteria", "Odom classification", "Odom grading"],
        abbreviations=["Odom"],
        korean_term="오덤 기준",
        notes="4-grade scale for cervical surgery outcomes: Excellent, Good, Satisfactory, Poor",
    ),
    "Patient Satisfaction": SNOMEDMapping(
        code="900000000000327",
        term="Patient satisfaction with surgical outcome",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Satisfaction rate", "Patient satisfaction score", "Clinical outcome",
                  "Surgical outcome satisfaction", "Functional outcome"],
        abbreviations=["PS", "PSat"],
        korean_term="환자 만족도",
        notes="Overall patient-reported satisfaction with surgery; various scales used",
    ),
    "PGIC": SNOMEDMapping(
        code="900000000000328",
        term="Patient Global Impression of Change",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Patient Global Impression of Change", "Global improvement",
                  "Global impression of change", "PGIC score"],
        abbreviations=["PGIC"],
        korean_term="환자 전반적 변화 인상",
        notes="7-point scale from 'very much improved' to 'very much worse'",
    ),
    "NPS": SNOMEDMapping(
        code="900000000000329",
        term="Net Promoter Score for surgical outcome",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Net Promoter Score", "Would recommend", "Recommendation score"],
        abbreviations=["NPS"],
        korean_term="순추천고객지수",
        notes="Likelihood of recommending procedure to others; scale 0-10",
    ),

    # === NEUROLOGICAL OUTCOMES ===
    "Motor Strength": SNOMEDMapping(
        code="900000000000330",
        term="Motor strength assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Motor function", "MRC grade", "Muscle strength",
                  "Manual muscle testing", "Motor power"],
        abbreviations=["MRC", "MMT"],
        korean_term="근력",
        notes="Typically graded using MRC (Medical Research Council) scale 0-5",
    ),
    "Sensory Function": SNOMEDMapping(
        code="900000000000331",
        term="Sensory function assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Sensory deficit", "Sensory recovery", "Dermatomal sensation",
                  "Sensory examination", "Light touch sensation"],
        abbreviations=["SF"],
        korean_term="감각 기능",
        notes="Assessment of dermatomal sensation; includes light touch, pinprick, proprioception",
    ),
    "ASIA Score": SNOMEDMapping(
        code="900000000000332",
        term="ASIA Impairment Scale score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["ASIA Impairment Scale", "AIS grade", "Spinal cord injury grade",
                  "ASIA motor score", "ASIA sensory score"],
        abbreviations=["AIS", "ASIA"],
        korean_term="ASIA 손상 척도",
        notes="A-E classification: A=Complete, B=Sensory incomplete, C/D=Motor incomplete, E=Normal",
    ),
    "Nurick Grade": SNOMEDMapping(
        code="900000000000333",
        term="Nurick myelopathy grading scale",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Nurick myelopathy grade", "Nurick scale", "Nurick classification"],
        abbreviations=["Nurick"],
        korean_term="누릭 척수병증 등급",
        notes="Grade 0-5 for cervical myelopathy severity based on gait and employment",
    ),

    # === QUALITY OF LIFE - Additional ===
    "PROMIS": SNOMEDMapping(
        code="900000000000334",
        term="PROMIS score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["PROMIS Physical Function", "PROMIS Pain Intensity",
                  "PROMIS Pain Interference", "Patient-Reported Outcomes Measurement Information System"],
        abbreviations=["PROMIS", "PROMIS-PF", "PROMIS-PI"],
        korean_term="PROMIS 점수",
        notes="NIH-developed computerized adaptive testing; domains include physical function, pain, mental health",
    ),
    "WHOQOL": SNOMEDMapping(
        code="900000000000335",
        term="WHO Quality of Life assessment",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["WHO Quality of Life", "WHOQOL-BREF", "WHOQOL-100",
                  "World Health Organization Quality of Life"],
        abbreviations=["WHOQOL", "WHOQOL-BREF"],
        korean_term="WHO 삶의 질 평가",
        notes="4 domains: physical health, psychological, social relationships, environment",
    ),
    "COMI": SNOMEDMapping(
        code="900000000000336",
        term="Core Outcome Measures Index",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Core Outcome Measures Index", "COMI score", "COMI back",
                  "COMI spine"],
        abbreviations=["COMI"],
        korean_term="핵심 결과 측정 지수",
        notes="Short multidimensional outcome instrument; covers pain, function, well-being, disability, satisfaction",
    ),
    "Zurich Claudication": SNOMEDMapping(
        code="900000000000337",
        term="Zurich Claudication Questionnaire",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["ZCQ", "Zurich Claudication Questionnaire", "Swiss Spinal Stenosis Questionnaire",
                  "Symptom Severity Scale", "Physical Function Scale"],
        abbreviations=["ZCQ", "SSSQ"],
        korean_term="취리히 파행 설문",
        notes="3 subscales: symptom severity, physical function, patient satisfaction; specific for lumbar stenosis",
    ),

    # === ONCOLOGY OUTCOMES ===
    "Survival Rate": SNOMEDMapping(
        code="900000000000338",
        term="Overall survival rate",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Overall survival", "Survival probability", "Kaplan-Meier survival",
                  "1-year survival", "2-year survival", "5-year survival"],
        abbreviations=["OS"],
        korean_term="생존율",
        notes="Percentage of patients surviving at specified time points; key outcome for spinal metastasis/tumor surgery",
    ),
    "Recurrence Rate": SNOMEDMapping(
        code="900000000000339",
        term="Tumor recurrence rate",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Local recurrence", "Tumor recurrence", "Local recurrence rate",
                  "Disease recurrence", "Recurrence-free survival"],
        abbreviations=["RecR"],
        korean_term="재발률",
        notes="Rate of local tumor recurrence after surgical resection; assessed by MRI follow-up",
    ),
    "SINS Score": SNOMEDMapping(
        code="900000000000340",
        term="Spinal Instability Neoplastic Score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Spinal Instability Neoplastic Score", "SINS classification",
                  "Neoplastic spinal instability score"],
        abbreviations=["SINS"],
        korean_term="척추 불안정성 종양 점수",
        notes="0-18 score: 0-6 stable, 7-12 indeterminate, 13-18 unstable; guides surgical decision-making",
    ),
    "Tokuhashi Score": SNOMEDMapping(
        code="900000000000341",
        term="Revised Tokuhashi prognostic score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Revised Tokuhashi", "Tokuhashi prognosis", "Tokuhashi scoring system",
                  "Tokuhashi survival prediction"],
        abbreviations=["Tokuhashi"],
        korean_term="토쿠하시 예후 점수",
        notes="0-15 score predicting survival in spinal metastasis: 0-8 (<6mo), 9-11 (>6mo), 12-15 (>1yr)",
    ),
    "Tomita Score": SNOMEDMapping(
        code="900000000000342",
        term="Tomita surgical classification score",
        semantic_type=SNOMEDSemanticType.OBSERVABLE_ENTITY,
        is_extension=True,
        synonyms=["Tomita surgical classification", "Tomita scoring system",
                  "Tomita prognostic score"],
        abbreviations=["Tomita"],
        korean_term="토미타 수술 분류 점수",
        notes="2-10 score based on tumor grade, visceral metastasis, bone metastasis; guides surgical strategy",
    ),
}


# ============================================================================
# ANATOMY MAPPINGS - Spine Regions
# ============================================================================

SPINE_ANATOMY_SNOMED: dict[str, SNOMEDMapping] = {
    # === REGIONS ===
    "Cervical": SNOMEDMapping(
        code="122494005",
        term="Cervical spine structure",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["Cervical region", "C-spine"],
    ),
    "Thoracic": SNOMEDMapping(
        code="122495006",
        term="Thoracic spine structure",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["Thoracic region", "T-spine"],
    ),
    "Lumbar": SNOMEDMapping(
        code="122496007",
        term="Lumbar spine structure",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["Lumbar region", "L-spine"],
    ),
    "Sacral": SNOMEDMapping(
        code="699698002",
        term="Structure of sacrum",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["Sacrum", "S1-S5"],
    ),
    "Lumbosacral": SNOMEDMapping(
        code="264940005",
        term="Lumbosacral region of spine",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["LS spine", "L5-S1 junction"],
    ),
    "Cervicothoracic": SNOMEDMapping(
        code="900000000000401",
        term="Cervicothoracic junction",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C7-T1 junction", "Cervicothoracic transition"],
        abbreviations=["CT junction", "CTJ"],
        korean_term="경흉추 이행부",
    ),
    "Thoracolumbar": SNOMEDMapping(
        code="264939003",
        term="Thoracolumbar region of spine",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        synonyms=["TL junction", "T12-L1"],
    ),

    # === SPECIFIC LEVELS ===
    "C1": SNOMEDMapping(code="14806007", term="Structure of atlas", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE, synonyms=["Atlas"]),
    "C2": SNOMEDMapping(code="39976000", term="Structure of axis", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE, synonyms=["Axis"]),
    "C3": SNOMEDMapping(code="181822002", term="Third cervical vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "C4": SNOMEDMapping(code="181823007", term="Fourth cervical vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "C5": SNOMEDMapping(code="181824001", term="Fifth cervical vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "C6": SNOMEDMapping(code="181825000", term="Sixth cervical vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "C7": SNOMEDMapping(code="181826004", term="Seventh cervical vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "T1": SNOMEDMapping(code="181827008", term="First thoracic vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "T12": SNOMEDMapping(code="181838003", term="Twelfth thoracic vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "L1": SNOMEDMapping(code="181839006", term="First lumbar vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "L2": SNOMEDMapping(code="181840008", term="Second lumbar vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "L3": SNOMEDMapping(code="181841007", term="Third lumbar vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "L4": SNOMEDMapping(code="181842000", term="Fourth lumbar vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "L5": SNOMEDMapping(code="181843005", term="Fifth lumbar vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "S1": SNOMEDMapping(code="181844004", term="First sacral vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    # v1.16.1: 누락된 vertebral levels 추가
    "S2": SNOMEDMapping(code="181845003", term="Second sacral vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "T10": SNOMEDMapping(code="181836002", term="Tenth thoracic vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),
    "T11": SNOMEDMapping(code="181837006", term="Eleventh thoracic vertebra", semantic_type=SNOMEDSemanticType.BODY_STRUCTURE),

    # === SEGMENT LEVELS (Intervertebral Disc) ===
    "L4-5": SNOMEDMapping(
        code="900000000000402",
        term="L4-L5 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["L4-L5 disc", "L4/5 level"],
        korean_term="L4-5 추간판",
        notes="Most common level for lumbar disc herniation",
    ),
    "L5-S1": SNOMEDMapping(
        code="900000000000403",
        term="L5-S1 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["L5-S1 disc", "L5/S1 level", "Lumbosacral disc"],
        korean_term="L5-S1 추간판",
        notes="Second most common level for lumbar disc herniation",
    ),
    "L3-4": SNOMEDMapping(
        code="900000000000404",
        term="L3-L4 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["L3-L4 disc", "L3/4 level"],
        korean_term="L3-4 추간판",
    ),
    "C5-6": SNOMEDMapping(
        code="900000000000405",
        term="C5-C6 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C5-C6 disc", "C5/6 level"],
        korean_term="C5-6 추간판",
        notes="Most common level for cervical disc herniation",
    ),
    "C6-7": SNOMEDMapping(
        code="900000000000406",
        term="C6-C7 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C6-C7 disc", "C6/7 level"],
        korean_term="C6-7 추간판",
        notes="Second most common level for cervical disc herniation",
    ),
    # v1.16.4: 추가 분절 레벨 (parse_segment_range 분리 결과 매핑)
    "C3-4": SNOMEDMapping(
        code="900000000000407",
        term="C3-C4 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C3-C4 disc", "C3/4 level"],
        korean_term="C3-4 추간판",
    ),
    "C4-5": SNOMEDMapping(
        code="900000000000408",
        term="C4-C5 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C4-C5 disc", "C4/5 level"],
        korean_term="C4-5 추간판",
    ),
    "C7-T1": SNOMEDMapping(
        code="900000000000409",
        term="C7-T1 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["C7-T1 disc", "cervicothoracic disc"],
        korean_term="C7-T1 추간판",
        notes="Cervicothoracic junction disc level",
    ),
    "L1-2": SNOMEDMapping(
        code="900000000000410",
        term="L1-L2 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["L1-L2 disc", "L1/2 level"],
        korean_term="L1-2 추간판",
    ),
    "L2-3": SNOMEDMapping(
        code="900000000000411",
        term="L2-L3 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["L2-L3 disc", "L2/3 level"],
        korean_term="L2-3 추간판",
    ),
    "T11-12": SNOMEDMapping(
        code="900000000000412",
        term="T11-T12 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["T11-T12 disc", "T11/12 level"],
        korean_term="T11-12 추간판",
    ),
    "T12-L1": SNOMEDMapping(
        code="900000000000413",
        term="T12-L1 intervertebral disc",
        semantic_type=SNOMEDSemanticType.BODY_STRUCTURE,
        is_extension=True,
        synonyms=["T12-L1 disc", "thoracolumbar disc"],
        korean_term="T12-L1 추간판",
        notes="Thoracolumbar junction disc level",
    ),
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _search_mapping(
    mapping_dict: dict[str, SNOMEDMapping], name: str
) -> Optional[SNOMEDMapping]:
    """공통 SNOMED 매핑 조회 로직.

    검색 순서: exact key → case-insensitive key → synonyms → abbreviations.
    """
    # Direct lookup
    if name in mapping_dict:
        return mapping_dict[name]

    # Case-insensitive + synonyms + abbreviations
    name_lower = name.lower()
    name_upper = name.upper()
    for key, mapping in mapping_dict.items():
        if key.lower() == name_lower:
            return mapping
        if any(syn.lower() == name_lower for syn in mapping.synonyms):
            return mapping
        if mapping.abbreviations and any(
            a.upper() == name_upper for a in mapping.abbreviations
        ):
            return mapping

    return None


def get_snomed_for_intervention(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an intervention.

    Args:
        name: Intervention name (e.g., "TLIF", "UBE")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    return _search_mapping(SPINE_INTERVENTION_SNOMED, name)


def get_snomed_for_pathology(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for a pathology.

    Args:
        name: Pathology name (e.g., "Lumbar Stenosis")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    return _search_mapping(SPINE_PATHOLOGY_SNOMED, name)


def get_snomed_for_outcome(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an outcome.

    Args:
        name: Outcome name (e.g., "VAS", "ODI")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    return _search_mapping(SPINE_OUTCOME_SNOMED, name)


def get_snomed_for_anatomy(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an anatomy.

    Args:
        name: Anatomy name (e.g., "Lumbar", "L4-5")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    return _search_mapping(SPINE_ANATOMY_SNOMED, name)


def get_all_snomed_codes() -> dict[str, SNOMEDMapping]:
    """Get all SNOMED mappings combined.

    Returns:
        Dictionary with all mappings by name
    """
    all_mappings = {}
    all_mappings.update(SPINE_INTERVENTION_SNOMED)
    all_mappings.update(SPINE_PATHOLOGY_SNOMED)
    all_mappings.update(SPINE_OUTCOME_SNOMED)
    all_mappings.update(SPINE_ANATOMY_SNOMED)
    return all_mappings


def get_extension_codes() -> list[SNOMEDMapping]:
    """Get all proposed extension codes.

    Returns:
        List of mappings that need official SNOMED codes
    """
    all_mappings = get_all_snomed_codes()
    return [m for m in all_mappings.values() if m.is_extension]


# Statistics
def get_mapping_statistics() -> dict:
    """Get statistics about the SNOMED mappings.

    Returns:
        Dictionary with counts and coverage info
    """
    intervention_count = len(SPINE_INTERVENTION_SNOMED)
    pathology_count = len(SPINE_PATHOLOGY_SNOMED)
    outcome_count = len(SPINE_OUTCOME_SNOMED)
    anatomy_count = len(SPINE_ANATOMY_SNOMED)

    extension_codes = get_extension_codes()
    official_count = (
        intervention_count + pathology_count + outcome_count + anatomy_count
        - len(extension_codes)
    )

    # Count extensions by category
    extension_by_category = {
        "procedure": 0,
        "disorder": 0,
        "observable": 0,
        "body_structure": 0,
        "finding": 0,
    }
    for m in extension_codes:
        code = m.code
        if code.startswith("9000000000001"):
            extension_by_category["procedure"] += 1
        elif code.startswith("9000000000002"):
            extension_by_category["disorder"] += 1
        elif code.startswith("9000000000003"):
            extension_by_category["observable"] += 1
        elif code.startswith("9000000000004"):
            extension_by_category["body_structure"] += 1
        elif code.startswith("9000000000005"):
            extension_by_category["finding"] += 1

    return {
        "total_mappings": intervention_count + pathology_count + outcome_count + anatomy_count,
        "interventions": intervention_count,
        "pathologies": pathology_count,
        "outcomes": outcome_count,
        "anatomy": anatomy_count,
        "official_snomed_codes": official_count,
        "extension_codes_needed": len(extension_codes),
        "extension_by_category": extension_by_category,
        "coverage_percent": round(official_count / (official_count + len(extension_codes)) * 100, 1),
    }


# =============================================================================
# ENHANCED SEARCH FUNCTIONS (v4.3)
# =============================================================================

def search_by_abbreviation(abbrev: str) -> Optional[SNOMEDMapping]:
    """Search for mapping by abbreviation.

    Args:
        abbrev: Abbreviation to search (e.g., "UBE", "TLIF", "ASD")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    abbrev_upper = abbrev.upper()
    all_mappings = get_all_snomed_codes()

    for key, mapping in all_mappings.items():
        # Check key itself
        if key.upper() == abbrev_upper:
            return mapping
        # Check abbreviations list
        if mapping.abbreviations:
            if any(a.upper() == abbrev_upper for a in mapping.abbreviations):
                return mapping

    return None


def search_by_korean_term(korean: str) -> Optional[SNOMEDMapping]:
    """Search for mapping by Korean term.

    Args:
        korean: Korean term to search (partial match supported)

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    all_mappings = get_all_snomed_codes()

    for mapping in all_mappings.values():
        if mapping.korean_term and korean in mapping.korean_term:
            return mapping

    return None


def search_all_terms(query: str) -> list[tuple[str, SNOMEDMapping, float]]:
    """Search across all terms, synonyms, abbreviations, and Korean terms.

    Args:
        query: Search query

    Returns:
        List of (key, mapping, score) tuples sorted by relevance score
    """
    query_lower = query.lower()
    results = []
    all_mappings = get_all_snomed_codes()

    for key, mapping in all_mappings.items():
        score = 0.0

        # Exact key match
        if key.lower() == query_lower:
            score = 1.0
        # Abbreviation match
        elif mapping.abbreviations:
            for abbr in mapping.abbreviations:
                if abbr.lower() == query_lower:
                    score = 0.95
                    break
        # Term contains query
        if score == 0 and query_lower in mapping.term.lower():
            score = 0.8
        # Synonym match
        if score == 0:
            for syn in mapping.synonyms:
                if query_lower in syn.lower():
                    score = 0.7
                    break
        # Korean term match
        if score == 0 and mapping.korean_term and query in mapping.korean_term:
            score = 0.6

        if score > 0:
            results.append((key, mapping, score))

    # Sort by score descending
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def get_parent_hierarchy(mapping: SNOMEDMapping) -> list[SNOMEDMapping]:
    """Get parent hierarchy for a mapping.

    Args:
        mapping: The mapping to trace

    Returns:
        List of parent mappings from immediate parent to root
    """
    hierarchy = []
    all_mappings = get_all_snomed_codes()

    current_parent_code = mapping.parent_code
    while current_parent_code:
        # Find parent by code
        parent_found = False
        for m in all_mappings.values():
            if m.code == current_parent_code:
                hierarchy.append(m)
                current_parent_code = m.parent_code
                parent_found = True
                break
        if not parent_found:
            break

    return hierarchy


def get_children(parent_code: str) -> list[tuple[str, SNOMEDMapping]]:
    """Get all direct children of a concept.

    Args:
        parent_code: Parent concept code

    Returns:
        List of (key, mapping) tuples for direct children
    """
    all_mappings = get_all_snomed_codes()
    children = []

    for key, mapping in all_mappings.items():
        if mapping.parent_code == parent_code:
            children.append((key, mapping))

    return children


def find_synonym_group(term: str) -> Optional[set[str]]:
    """Find the synonym group containing the given term.

    Args:
        term: Term to search for

    Returns:
        Set of synonyms if found, None otherwise
    """
    term_lower = term.lower()
    for group in SYNONYM_GROUPS:
        for member in group:
            if member.lower() == term_lower:
                return group
    return None


def get_all_synonyms(term: str) -> list[str]:
    """Get all synonyms for a term (including from SYNONYM_GROUPS).

    Args:
        term: Term to find synonyms for

    Returns:
        List of all synonyms including original term
    """
    synonyms = [term]

    # Check SYNONYM_GROUPS
    group = find_synonym_group(term)
    if group:
        synonyms.extend([s for s in group if s.lower() != term.lower()])

    # Check mapping synonyms and abbreviations
    mapping = search_by_abbreviation(term)
    if mapping:
        synonyms.extend(mapping.synonyms)
        if mapping.abbreviations:
            synonyms.extend(mapping.abbreviations)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in synonyms:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)

    return unique


def get_related_terms(term: str) -> list[tuple[str, SNOMEDMapping]]:
    """Get related but different procedures for a term.

    Args:
        term: Term to find related procedures for

    Returns:
        List of (key, mapping) tuples for related procedures
    """
    # Normalize term to key
    mapping = search_by_abbreviation(term)
    if not mapping:
        return []

    # Find the key for this mapping
    all_mappings = get_all_snomed_codes()
    term_key = None
    for key, m in all_mappings.items():
        if m.code == mapping.code:
            term_key = key
            break

    if not term_key:
        return []

    # Get related terms
    related_keys = RELATED_TERMS.get(term_key, [])
    results = []

    for related_key in related_keys:
        related_mapping = get_snomed_for_intervention(related_key)
        if related_mapping:
            results.append((related_key, related_mapping))

    return results


def normalize_term(term: str) -> tuple[str, Optional[SNOMEDMapping], list[str]]:
    """Normalize a term to its canonical form with all synonyms.

    Args:
        term: Term to normalize (can be abbreviation, synonym, or full name)

    Returns:
        Tuple of (canonical_key, mapping, all_synonyms)

    Example:
        >>> normalize_term("BESS")
        ("UBE", SNOMEDMapping(...), ["UBE", "BESS", "UBESS", "Biportal Endoscopy", ...])

        >>> normalize_term("XLIF")
        ("LLIF", SNOMEDMapping(...), ["LLIF", "XLIF", "DLIF", ...])
    """
    # Try direct mapping lookup
    mapping = search_by_abbreviation(term)

    if mapping:
        # Find canonical key
        all_mappings = get_all_snomed_codes()
        canonical_key = None
        for key, m in all_mappings.items():
            if m.code == mapping.code:
                canonical_key = key
                break

        synonyms = get_all_synonyms(term)
        return (canonical_key or term, mapping, synonyms)

    # Try synonym group lookup
    group = find_synonym_group(term)
    if group:
        # Try to find mapping for any member of the group
        for member in group:
            mapping = search_by_abbreviation(member)
            if mapping:
                all_mappings = get_all_snomed_codes()
                canonical_key = None
                for key, m in all_mappings.items():
                    if m.code == mapping.code:
                        canonical_key = key
                        break
                return (canonical_key or member, mapping, list(group))

    return (term, None, [term])


def comprehensive_search(query: str) -> dict:
    """Comprehensive search returning exact match, synonyms, and related terms.

    Args:
        query: Search query

    Returns:
        Dictionary with:
        - exact_match: Exact mapping if found
        - synonyms: All synonym terms
        - related: Related but different procedures
        - korean_term: Korean translation if available

    Example:
        >>> comprehensive_search("BESS")
        {
            "canonical_term": "UBE",
            "exact_match": SNOMEDMapping(...),
            "synonyms": ["UBE", "BESS", "UBESS", ...],
            "related": [("PELD", SNOMEDMapping), ("FELD", SNOMEDMapping), ...],
            "korean_term": "일측 양방향 내시경 척추 수술"
        }
    """
    canonical, mapping, synonyms = normalize_term(query)
    related = get_related_terms(query) if mapping else []

    return {
        "query": query,
        "canonical_term": canonical,
        "exact_match": mapping,
        "snomed_code": mapping.code if mapping else None,
        "is_extension": mapping.is_extension if mapping else None,
        "synonyms": synonyms,
        "related": related,
        "korean_term": mapping.korean_term if mapping else None,
    }


# =============================================================================
# SNOMED API INTEGRATION (v4.3)
# =============================================================================
# These functions integrate with the SNOMED Terminology Server API
# for real-time code lookup and extension verification.

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ontology.snomed_api_client import SNOMEDConcept, SNOMEDAPIClient

logger = logging.getLogger(__name__)


def _try_import_api_client():
    """Try to import the SNOMED API client.

    Returns:
        Tuple of (SNOMEDAPIClient class, SNOMEDAPIClientSync class) or (None, None)
    """
    try:
        from ontology.snomed_api_client import (
            SNOMEDAPIClient,
            SNOMEDAPIClientSync,
        )
        return SNOMEDAPIClient, SNOMEDAPIClientSync
    except ImportError:
        try:
            from src.ontology.snomed_api_client import (
                SNOMEDAPIClient,
                SNOMEDAPIClientSync,
            )
            return SNOMEDAPIClient, SNOMEDAPIClientSync
        except ImportError:
            return None, None


async def search_with_api_fallback(
    query: str,
    use_api: bool = True,
    timeout: float = 10.0,
) -> dict:
    """Search for SNOMED code with API fallback to local mappings.

    This function first tries to find a match in local mappings.
    If use_api is True and no exact match is found, it queries the
    SNOMED Terminology Server API.

    Args:
        query: Search term
        use_api: Whether to try the API if local search fails
        timeout: API request timeout in seconds

    Returns:
        Dictionary with search results:
        - local_match: Local mapping if found
        - api_results: API results if queried
        - recommended: Recommended code (local or API)
        - source: "local" or "api"
    """
    # First, try local comprehensive search
    local_result = comprehensive_search(query)

    result = {
        "query": query,
        "local_match": local_result.get("exact_match"),
        "canonical_term": local_result.get("canonical_term"),
        "synonyms": local_result.get("synonyms", []),
        "api_results": [],
        "recommended": None,
        "source": None,
        "error": None,
    }

    # If we have a local match, use it
    if local_result.get("exact_match"):
        result["recommended"] = local_result["exact_match"]
        result["source"] = "local"

        # If it's an extension code and API is enabled, try to find official code
        if use_api and local_result["exact_match"].is_extension:
            SNOMEDAPIClient, _ = _try_import_api_client()
            if SNOMEDAPIClient:
                try:
                    async with SNOMEDAPIClient(timeout=timeout) as client:
                        api_results = await client.search_concepts(
                            local_result["exact_match"].term,
                            limit=5,
                        )
                        if api_results.concepts:
                            result["api_results"] = [
                                {
                                    "code": c.concept_id,
                                    "term": c.term,
                                    "fsn": c.fsn,
                                    "semantic_tag": c.semantic_tag,
                                }
                                for c in api_results.concepts
                            ]
                            # Check if any API result is a good match
                            for c in api_results.concepts:
                                if not c.concept_id.startswith("900000000"):
                                    result["official_alternative"] = {
                                        "code": c.concept_id,
                                        "term": c.term,
                                    }
                                    break
                except Exception as e:
                    logger.warning(f"API search failed: {e}")
                    result["error"] = str(e)

        return result

    # No local match - try API if enabled
    if use_api:
        SNOMEDAPIClient, _ = _try_import_api_client()
        if SNOMEDAPIClient:
            try:
                async with SNOMEDAPIClient(timeout=timeout) as client:
                    api_results = await client.search_concepts(query, limit=10)
                    if api_results.concepts:
                        result["api_results"] = [
                            {
                                "code": c.concept_id,
                                "term": c.term,
                                "fsn": c.fsn,
                                "semantic_tag": c.semantic_tag,
                            }
                            for c in api_results.concepts
                        ]
                        # Use first API result as recommended
                        first = api_results.concepts[0]
                        result["recommended"] = SNOMEDMapping(
                            code=first.concept_id,
                            term=first.term,
                            semantic_type=_semantic_tag_to_type(first.semantic_tag),
                            is_extension=False,
                        )
                        result["source"] = "api"
            except Exception as e:
                logger.warning(f"API search failed: {e}")
                result["error"] = str(e)

    return result


def _semantic_tag_to_type(tag: str) -> SNOMEDSemanticType:
    """Convert SNOMED semantic tag to our enum.

    Args:
        tag: Semantic tag from FSN (e.g., "procedure", "disorder")

    Returns:
        SNOMEDSemanticType enum value
    """
    tag_lower = tag.lower() if tag else ""
    mapping = {
        "procedure": SNOMEDSemanticType.PROCEDURE,
        "disorder": SNOMEDSemanticType.DISORDER,
        "body structure": SNOMEDSemanticType.BODY_STRUCTURE,
        "observable entity": SNOMEDSemanticType.OBSERVABLE_ENTITY,
        "finding": SNOMEDSemanticType.FINDING,
        "qualifier value": SNOMEDSemanticType.QUALIFIER_VALUE,
    }
    return mapping.get(tag_lower, SNOMEDSemanticType.PROCEDURE)


def search_with_api_fallback_sync(
    query: str,
    use_api: bool = True,
    timeout: float = 10.0,
) -> dict:
    """Synchronous version of search_with_api_fallback.

    For use in non-async contexts like Streamlit.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        search_with_api_fallback(query, use_api, timeout)
    )


async def verify_extension_codes(
    timeout: float = 10.0,
) -> list[dict]:
    """Verify all extension codes against the official SNOMED API.

    Searches for each extension code's term in the SNOMED API to see
    if an official code now exists.

    Args:
        timeout: API timeout per request

    Returns:
        List of dictionaries with verification results:
        - extension_code: Our extension code
        - extension_term: Our extension term
        - official_found: Whether an official code was found
        - official_code: Official SCTID if found
        - official_term: Official term if found
        - confidence: Match confidence (0-1)
    """
    SNOMEDAPIClient, _ = _try_import_api_client()
    if not SNOMEDAPIClient:
        logger.warning("SNOMED API client not available")
        return []

    extensions = get_extension_codes()
    results = []

    async with SNOMEDAPIClient(timeout=timeout) as client:
        for ext in extensions:
            result = {
                "extension_code": ext.code,
                "extension_term": ext.term,
                "official_found": False,
                "official_code": None,
                "official_term": None,
                "confidence": 0.0,
            }

            try:
                # Search for the term
                api_results = await client.search_concepts(ext.term, limit=5)

                if api_results.concepts:
                    for concept in api_results.concepts:
                        # Skip if it's another extension code
                        if concept.concept_id.startswith("900000000"):
                            continue

                        # Calculate confidence based on term similarity
                        term_lower = ext.term.lower()
                        concept_term_lower = concept.term.lower()

                        if term_lower == concept_term_lower:
                            confidence = 1.0
                        elif term_lower in concept_term_lower or concept_term_lower in term_lower:
                            confidence = 0.8
                        else:
                            # Jaccard similarity
                            set1 = set(term_lower.split())
                            set2 = set(concept_term_lower.split())
                            intersection = len(set1 & set2)
                            union = len(set1 | set2)
                            confidence = intersection / union if union > 0 else 0

                        if confidence > result["confidence"]:
                            result["official_found"] = True
                            result["official_code"] = concept.concept_id
                            result["official_term"] = concept.term
                            result["confidence"] = confidence

            except Exception as e:
                logger.warning(f"Failed to verify {ext.term}: {e}")
                result["error"] = str(e)

            results.append(result)

    return results


def verify_extension_codes_sync(timeout: float = 10.0) -> list[dict]:
    """Synchronous version of verify_extension_codes."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(verify_extension_codes(timeout))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_mapping(code_or_term: str) -> Optional[SNOMEDMapping]:
    """Get mapping by code or term.

    Args:
        code_or_term: SNOMED code or search term

    Returns:
        SNOMEDMapping if found
    """
    all_mappings = get_all_snomed_codes()

    # Try by code first
    for mapping in all_mappings.values():
        if mapping.code == code_or_term:
            return mapping

    # Try by abbreviation/term
    return search_by_abbreviation(code_or_term)


def is_official_code(code: str) -> bool:
    """Check if a code is an official SNOMED code (not extension).

    Args:
        code: SNOMED code to check

    Returns:
        True if official, False if extension
    """
    return not code.startswith(EXTENSION_NAMESPACE)


def get_coverage_report() -> dict:
    """Get detailed coverage report.

    Returns:
        Dictionary with coverage statistics and breakdown
    """
    stats = get_mapping_statistics()
    extensions = get_extension_codes()

    # Group extensions by category
    extensions_by_category = {
        "procedure": [],
        "disorder": [],
        "observable": [],
        "body_structure": [],
        "finding": [],
    }

    for ext in extensions:
        code = ext.code
        if code.startswith("9000000000001"):
            extensions_by_category["procedure"].append(ext)
        elif code.startswith("9000000000002"):
            extensions_by_category["disorder"].append(ext)
        elif code.startswith("9000000000003"):
            extensions_by_category["observable"].append(ext)
        elif code.startswith("9000000000004"):
            extensions_by_category["body_structure"].append(ext)
        elif code.startswith("9000000000005"):
            extensions_by_category["finding"].append(ext)

    return {
        "summary": stats,
        "extensions_detail": {
            category: [
                {"code": e.code, "term": e.term, "korean": e.korean_term}
                for e in exts
            ]
            for category, exts in extensions_by_category.items()
        },
        "coverage_by_category": {
            "interventions": {
                "total": stats["interventions"],
                "official": stats["interventions"] - stats["extension_by_category"]["procedure"],
                "extension": stats["extension_by_category"]["procedure"],
            },
            "pathologies": {
                "total": stats["pathologies"],
                "official": stats["pathologies"] - stats["extension_by_category"]["disorder"],
                "extension": stats["extension_by_category"]["disorder"],
            },
            "outcomes": {
                "total": stats["outcomes"],
                "official": stats["outcomes"] - stats["extension_by_category"]["observable"],
                "extension": stats["extension_by_category"]["observable"],
            },
            "anatomy": {
                "total": stats["anatomy"],
                "official": stats["anatomy"] - stats["extension_by_category"]["body_structure"],
                "extension": stats["extension_by_category"]["body_structure"],
            },
        },
    }
