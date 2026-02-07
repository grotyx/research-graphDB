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
    # Biportal Endoscopy 계열 (완전 동의어) - v7.14: BED 추가
    {"UBE", "BESS", "UBESS", "Biportal Endoscopy", "Biportal Endoscopic",
     "Unilateral Biportal Endoscopy", "Biportal Endoscopic Spine Surgery",
     "BED", "Biportal Endoscopic Discectomy"},

    # Lateral Interbody Fusion - Transpsoas 접근 (완전 동의어)
    {"LLIF", "XLIF", "DLIF", "Lateral Lumbar Interbody Fusion",
     "Extreme Lateral Interbody Fusion", "Direct Lateral Interbody Fusion"},

    # OLIF 계열 (완전 동의어)
    {"OLIF", "ATP", "OLIF25", "OLIF51", "Oblique Lumbar Interbody Fusion",
     "Anterior to Psoas", "Oblique Lateral Interbody Fusion"},

    # BELIF/BE-TLIF 계열 (완전 동의어) - v7.14 추가
    {"BELIF", "BE-TLIF", "BETLIF", "BE-LIF", "BELF",
     "Biportal Endoscopic TLIF", "Biportal Endoscopic Lumbar Interbody Fusion",
     "Biportal endoscopic transforaminal lumbar interbody fusion"},

    # Decompression/Laminectomy 계열 (완전 동의어) - v7.14 추가
    {"Decompression", "decompression", "Neural Decompression", "neural decompression",
     "Decompression Surgery", "Spinal decompression", "Neural decompression"},

    # Laminectomy 계열 (완전 동의어) - v7.14 추가
    {"Laminectomy", "laminectomy", "Decompressive Laminectomy", "decompressive laminectomy",
     "Open Laminectomy", "Open laminectomy"},

    # v7.14.1: Fusion 일반 계열 추가
    {"Posterior fusion", "posterior fusion", "PSF", "Posterior spinal fusion",
     "posterior spinal fusion", "Posterolateral Fusion", "PLF"},

    # v7.14.1: TLIF 계열 추가
    {"TLIF", "Transforaminal Lumbar Interbody Fusion", "transforaminal lumbar interbody fusion",
     "Transforaminal fusion", "transforaminal fusion"},

    # v7.14.1: Radiculopathy 계열 추가
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
        # v7.14: BED (Biportal Endoscopic Discectomy) 동의어 추가
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

    # v7.14 추가: BELIF (Biportal Endoscopic Lumbar Interbody Fusion)
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

    # v7.14 추가: Stereotactic Navigation
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

    # v7.14.2 추가: Facetectomy
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
        # v7.14.1: 동의어 확장
        synonyms=["DCM", "Degenerative cervical myelopathy",
                  "Cervical spondylotic myelopathy", "CSM",
                  "cervical myelopathy", "degenerative cervical myelopathy"],
    ),

    # v7.14.1: Cervical Radiculopathy 추가
    "Cervical Radiculopathy": SNOMEDMapping(
        code="267073000",
        term="Cervical radiculopathy",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Cervical nerve root compression", "Cervical radicular pain",
                  "cervical radiculopathy", "C-spine radiculopathy"],
        korean_term="경추 신경근병증",
    ),

    # v7.14.1: Lumbar Radiculopathy 추가
    "Lumbar Radiculopathy": SNOMEDMapping(
        code="128196005",
        term="Lumbar radiculopathy",
        semantic_type=SNOMEDSemanticType.DISORDER,
        synonyms=["Sciatica", "Lumbar radicular pain", "L-spine radiculopathy",
                  "lumbar radiculopathy", "sciatica", "Radicular leg pain"],
        korean_term="요추 신경근병증",
    ),

    # v7.14.1: Segmental Instability 추가
    "Segmental Instability": SNOMEDMapping(
        code="900000000000206",
        term="Segmental spinal instability",
        semantic_type=SNOMEDSemanticType.DISORDER,
        is_extension=True,
        synonyms=["Lumbar instability", "Spinal instability", "Mechanical instability",
                  "segmental instability", "lumbar instability"],
        korean_term="분절 불안정성",
        notes="Dynamic instability at a spinal segment, often associated with spondylolisthesis",
    ),

    # v7.14.1: Distal Junctional Kyphosis (DJK) 추가
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

    # v7.14.1: Adjacent Segment Disease 추가
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
        korean_term="골유합률",
        notes="Typically assessed by CT or dynamic X-ray",
    ),
    "Cage Subsidence": SNOMEDMapping(
        code="900000000000501",
        term="Interbody cage subsidence",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Cage settling", "Interbody subsidence", "Cage sinking"],
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
        korean_term="재수술률",
    ),
    # v7.14.14 수정: Adjacent Segment Disease는 SPINE_PATHOLOGY_SNOMED에서 정의됨 (900000000000208)
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

    # v7.14 추가: Serum CPK (근육 손상 지표)
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

    # v7.14 추가: Scar Quality (상처 미용 결과)
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

    # v7.14 추가: Postoperative Drainage (배액량)
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

    # v7.14.14 수정: Wound Dehiscence - 공식 SNOMED 코드 225553008 사용
    # 이전 extension code 900000000000503은 225553008로 대체됨
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

    # v7.14 추가: Recurrent Disc Herniation (재발성 디스크 탈출)
    "Recurrent Disc Herniation": SNOMEDMapping(
        code="900000000000504",
        term="Recurrent intervertebral disc herniation",
        semantic_type=SNOMEDSemanticType.FINDING,
        is_extension=True,
        synonyms=["Recurrent herniated disc", "Re-herniation", "Recurrent HNP",
                  "Disc re-herniation", "Same-level recurrence"],
        korean_term="재발성 추간판 탈출증",
        notes="Herniation at the same level after previous discectomy, typically within 6 months to 2 years",
    ),

    # v7.14 추가: Epidural Hematoma (경막외 혈종)
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

    # v7.14.3 추가: C5 Palsy (C5 마비)
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

    # v7.14.14 수정: Wound Dehiscence 중복 제거됨 - SPINE_OUTCOME_SNOMED에서 정의됨 (225553008)
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
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_snomed_for_intervention(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an intervention.

    Args:
        name: Intervention name (e.g., "TLIF", "UBE")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    # Direct lookup
    if name in SPINE_INTERVENTION_SNOMED:
        return SPINE_INTERVENTION_SNOMED[name]

    # Case-insensitive lookup
    name_lower = name.lower()
    for key, mapping in SPINE_INTERVENTION_SNOMED.items():
        if key.lower() == name_lower:
            return mapping
        # Check synonyms
        if any(syn.lower() == name_lower for syn in mapping.synonyms):
            return mapping

    return None


def get_snomed_for_pathology(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for a pathology.

    Args:
        name: Pathology name (e.g., "Lumbar Stenosis")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    if name in SPINE_PATHOLOGY_SNOMED:
        return SPINE_PATHOLOGY_SNOMED[name]

    name_lower = name.lower()
    for key, mapping in SPINE_PATHOLOGY_SNOMED.items():
        if key.lower() == name_lower:
            return mapping
        if any(syn.lower() == name_lower for syn in mapping.synonyms):
            return mapping

    return None


def get_snomed_for_outcome(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an outcome.

    Args:
        name: Outcome name (e.g., "VAS", "ODI")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    if name in SPINE_OUTCOME_SNOMED:
        return SPINE_OUTCOME_SNOMED[name]

    name_lower = name.lower()
    for key, mapping in SPINE_OUTCOME_SNOMED.items():
        if key.lower() == name_lower:
            return mapping
        if any(syn.lower() == name_lower for syn in mapping.synonyms):
            return mapping

    return None


def get_snomed_for_anatomy(name: str) -> Optional[SNOMEDMapping]:
    """Get SNOMED mapping for an anatomy.

    Args:
        name: Anatomy name (e.g., "Lumbar", "L4-5")

    Returns:
        SNOMEDMapping if found, None otherwise
    """
    if name in SPINE_ANATOMY_SNOMED:
        return SPINE_ANATOMY_SNOMED[name]

    name_lower = name.lower()
    for key, mapping in SPINE_ANATOMY_SNOMED.items():
        if key.lower() == name_lower:
            return mapping
        if any(syn.lower() == name_lower for syn in mapping.synonyms):
            return mapping

    return None


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
