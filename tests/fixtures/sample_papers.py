"""Sample paper data for integration testing.

Mock paper data with realistic structure for testing the complete pipeline.
"""

from dataclasses import dataclass
from typing import Optional

from src.graph.spine_schema import PaperNode
from src.solver.graph_result import GraphEvidence


# Sample Paper 1: TLIF for Lumbar Stenosis (High-quality RCT)
SAMPLE_PAPER_TLIF = PaperNode(
    paper_id="TLIF_001",
    title="Transforaminal Lumbar Interbody Fusion for Lumbar Stenosis: A Randomized Controlled Trial",
    authors=["Kim SH", "Park JY", "Lee DH", "Choi BW"],
    year=2023,
    journal="Spine",
    doi="10.1097/BRS.0000000000001234",
    pmid="36789012",
    sub_domain="Degenerative",
    study_design="RCT",
    evidence_level="1b",
    sample_size=120,
    follow_up_months=24
)

# Sample Paper 2: UBE vs Open Laminectomy (Comparative study)
SAMPLE_PAPER_UBE = PaperNode(
    paper_id="UBE_001",
    title="Unilateral Biportal Endoscopy versus Open Laminectomy for Lumbar Stenosis: Comparative Study",
    authors=["Lee JS", "Choi YS", "Kim HJ"],
    year=2022,
    journal="Journal of Neurosurgery: Spine",
    doi="10.3171/2022.5.SPINE21234",
    pmid="35123456",
    sub_domain="Degenerative",
    study_design="Retrospective Comparative",
    evidence_level="2b",
    sample_size=85,
    follow_up_months=12
)

# Sample Paper 3: OLIF Systematic Review
SAMPLE_PAPER_OLIF_META = PaperNode(
    paper_id="OLIF_META_001",
    title="Oblique Lateral Interbody Fusion: A Systematic Review and Meta-analysis",
    authors=["Wang Y", "Zhang L", "Chen M", "Liu X"],
    year=2024,
    journal="European Spine Journal",
    doi="10.1007/s00586-024-01234-5",
    pmid="38234567",
    sub_domain="Degenerative",
    study_design="Meta-analysis",
    evidence_level="1a",
    sample_size=1250,  # Total from all studies
    follow_up_months=18
)

# Sample Paper 4: ASD Surgery Cohort Study
SAMPLE_PAPER_ASD = PaperNode(
    paper_id="ASD_001",
    title="Long Pedicle Screw Fixation for Adult Spinal Deformity: Multicenter Cohort Study",
    authors=["Tanaka M", "Nakamura K", "Suzuki H"],
    year=2023,
    journal="Global Spine Journal",
    doi="10.1177/21925682231234567",
    pmid="37456789",
    sub_domain="Deformity",
    study_design="Prospective Cohort",
    evidence_level="2a",
    sample_size=180,
    follow_up_months=36
)

# Sample Paper 5: Vertebroplasty Case Series
SAMPLE_PAPER_VERTEBROPLASTY = PaperNode(
    paper_id="VERT_001",
    title="Percutaneous Vertebroplasty for Osteoporotic Compression Fractures: Single Center Experience",
    authors=["Park SM", "Choi JH"],
    year=2021,
    journal="Pain Physician",
    doi="10.36076/ppj.2021.24.E123",
    pmid="34567890",
    sub_domain="Trauma",
    study_design="Case Series",
    evidence_level="3",
    sample_size=45,
    follow_up_months=6
)


# Sample Evidence for TLIF
TLIF_EVIDENCE_FUSION_RATE = GraphEvidence(
    intervention="TLIF",
    outcome="Fusion Rate",
    value="95.8%",
    value_control="88.3%",
    p_value=0.002,
    effect_size="RR=1.08",
    confidence_interval="95% CI: 1.03-1.14",
    is_significant=True,
    direction="improved",
    source_paper_id="TLIF_001",
    evidence_level="1b"
)

TLIF_EVIDENCE_VAS = GraphEvidence(
    intervention="TLIF",
    outcome="VAS",
    value="2.1",
    value_control="5.8",
    p_value=0.001,
    effect_size="Cohen's d=1.2",
    confidence_interval="95% CI: 1.8-4.2",
    is_significant=True,
    direction="improved",
    source_paper_id="TLIF_001",
    evidence_level="1b"
)

TLIF_EVIDENCE_ODI = GraphEvidence(
    intervention="TLIF",
    outcome="ODI",
    value="18.5",
    value_control="42.3",
    p_value=0.001,
    effect_size="Cohen's d=1.5",
    confidence_interval="95% CI: 18.2-29.4",
    is_significant=True,
    direction="improved",
    source_paper_id="TLIF_001",
    evidence_level="1b"
)

# Sample Evidence for UBE
UBE_EVIDENCE_VAS = GraphEvidence(
    intervention="UBE",
    outcome="VAS",
    value="2.3",
    value_control="2.1",
    p_value=0.421,
    is_significant=False,
    direction="unchanged",
    source_paper_id="UBE_001",
    evidence_level="2b"
)

UBE_EVIDENCE_BLOOD_LOSS = GraphEvidence(
    intervention="UBE",
    outcome="Blood Loss",
    value="35ml",
    value_control="220ml",
    p_value=0.001,
    is_significant=True,
    direction="improved",
    source_paper_id="UBE_001",
    evidence_level="2b"
)

UBE_EVIDENCE_HOSPITAL_STAY = GraphEvidence(
    intervention="UBE",
    outcome="Hospital Stay",
    value="3.2 days",
    value_control="7.5 days",
    p_value=0.001,
    is_significant=True,
    direction="improved",
    source_paper_id="UBE_001",
    evidence_level="2b"
)

# Sample Evidence for OLIF (from Meta-analysis)
OLIF_EVIDENCE_FUSION_RATE = GraphEvidence(
    intervention="OLIF",
    outcome="Fusion Rate",
    value="94.2%",
    p_value=0.001,
    effect_size="OR=15.3",
    confidence_interval="95% CI: 91.5-96.8",
    is_significant=True,
    direction="improved",
    source_paper_id="OLIF_META_001",
    evidence_level="1a"
)

OLIF_EVIDENCE_VAS = GraphEvidence(
    intervention="OLIF",
    outcome="VAS",
    value="1.8",
    p_value=0.001,
    effect_size="Cohen's d=1.8",
    confidence_interval="95% CI: 1.5-2.1",
    is_significant=True,
    direction="improved",
    source_paper_id="OLIF_META_001",
    evidence_level="1a"
)

# Conflicting Evidence (for conflict detection tests)
OLIF_EVIDENCE_SUBSIDENCE_POSITIVE = GraphEvidence(
    intervention="OLIF",
    outcome="Subsidence Rate",
    value="8.2%",
    p_value=0.234,
    is_significant=False,
    direction="unchanged",
    source_paper_id="OLIF_META_001",
    evidence_level="1a"
)

# From a hypothetical negative study
OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE = GraphEvidence(
    intervention="OLIF",
    outcome="Subsidence Rate",
    value="18.5%",
    p_value=0.012,
    is_significant=True,
    direction="worsened",
    source_paper_id="OLIF_002",  # Different study
    evidence_level="2b"
)


# Collections for easy access
ALL_SAMPLE_PAPERS = [
    SAMPLE_PAPER_TLIF,
    SAMPLE_PAPER_UBE,
    SAMPLE_PAPER_OLIF_META,
    SAMPLE_PAPER_ASD,
    SAMPLE_PAPER_VERTEBROPLASTY,
]

ALL_SAMPLE_EVIDENCES = [
    TLIF_EVIDENCE_FUSION_RATE,
    TLIF_EVIDENCE_VAS,
    TLIF_EVIDENCE_ODI,
    UBE_EVIDENCE_VAS,
    UBE_EVIDENCE_BLOOD_LOSS,
    UBE_EVIDENCE_HOSPITAL_STAY,
    OLIF_EVIDENCE_FUSION_RATE,
    OLIF_EVIDENCE_VAS,
    OLIF_EVIDENCE_SUBSIDENCE_POSITIVE,
    OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE,
]


# Sample PDF text content (for testing PDF processing)
SAMPLE_PDF_TEXT_TLIF = """
Title: Transforaminal Lumbar Interbody Fusion for Lumbar Stenosis: A Randomized Controlled Trial

Abstract:
Background: TLIF is a common fusion technique for lumbar stenosis.
Methods: 120 patients randomized to TLIF (n=60) vs conservative treatment (n=60).
Results: Fusion rate was 95.8% in TLIF group vs 88.3% in control (p=0.002).
VAS improved from 7.8 to 2.1 in TLIF group vs 7.9 to 5.8 in control (p<0.001).
Conclusion: TLIF is effective for lumbar stenosis with high fusion rates.

Introduction:
Lumbar stenosis is a common degenerative condition...

Methods:
This was a prospective randomized controlled trial conducted at 3 centers.
Sample size: 120 patients (60 per group).
Primary outcome: Fusion rate at 2 years.
Secondary outcomes: VAS, ODI, complications.

Results:
Fusion Rate: TLIF 95.8% (57/60) vs Control 88.3% (53/60), p=0.002
VAS: TLIF 2.1±1.2 vs Control 5.8±1.5, p<0.001
ODI: TLIF 18.5±8.2 vs Control 42.3±12.1, p<0.001
Complications: No significant difference (p=0.234)

Discussion:
Our findings demonstrate that TLIF provides superior fusion rates...
"""


# Mock vector search results (for testing hybrid ranking)
@dataclass
class MockVectorResult:
    """Mock vector search result for testing."""
    chunk_id: str
    content: str
    score: float
    tier: str
    section: str
    evidence_level: str
    is_key_finding: bool
    has_statistics: bool
    title: str
    publication_year: int
    summary: Optional[str] = None


MOCK_VECTOR_RESULTS_TLIF = [
    MockVectorResult(
        chunk_id="TLIF_001_abstract",
        content="TLIF is effective for lumbar stenosis with high fusion rates (95.8% vs 88.3%, p=0.002).",
        score=0.95,
        tier="tier1",
        section="abstract",
        evidence_level="1b",
        is_key_finding=True,
        has_statistics=True,
        title="TLIF for Lumbar Stenosis RCT",
        publication_year=2023,
        summary="TLIF showed superior fusion rates in RCT"
    ),
    MockVectorResult(
        chunk_id="TLIF_001_results",
        content="Fusion rate was 95.8% in TLIF group vs 88.3% in control (p=0.002). VAS improved significantly.",
        score=0.92,
        tier="tier1",
        section="results",
        evidence_level="1b",
        is_key_finding=True,
        has_statistics=True,
        title="TLIF for Lumbar Stenosis RCT",
        publication_year=2023,
        summary="Primary outcome results"
    ),
    MockVectorResult(
        chunk_id="TLIF_001_discussion",
        content="TLIF provides reliable fusion with good clinical outcomes. Similar to previous studies.",
        score=0.78,
        tier="tier2",
        section="discussion",
        evidence_level="1b",
        is_key_finding=False,
        has_statistics=False,
        title="TLIF for Lumbar Stenosis RCT",
        publication_year=2023,
    ),
]


# Expected search results for scenario testing
EXPECTED_TLIF_FUSION_RESULTS = {
    "query": "Find evidence for TLIF effectiveness on fusion rate",
    "expected_graph_count": 1,  # TLIF_EVIDENCE_FUSION_RATE
    "expected_vector_count": 2,  # abstract + results
    "expected_top_intervention": "TLIF",
    "expected_outcome": "Fusion Rate",
    "expected_significance": True,
    "expected_p_value_range": (0.001, 0.01),
}

EXPECTED_UBE_VS_OPEN_VAS = {
    "query": "Compare UBE vs Open surgery for VAS improvement",
    "expected_graph_count": 1,  # UBE_EVIDENCE_VAS
    "expected_interventions": ["UBE", "Open Laminectomy"],
    "expected_outcome": "VAS",
    "expected_significance": False,  # p=0.421
}

EXPECTED_ENDOSCOPIC_HIERARCHY = {
    "query": "Get intervention hierarchy for Endoscopic Surgery",
    "expected_parent": "Minimally Invasive Surgery",
    "expected_children": ["UBE", "PELD", "FELD"],
    "expected_category": "decompression",
}

EXPECTED_OLIF_CONFLICT = {
    "query": "Detect conflicting results for OLIF outcomes",
    "expected_conflicts": 1,  # Subsidence rate conflict
    "expected_outcome": "Subsidence Rate",
    "expected_conflicting_directions": ["unchanged", "worsened"],
}
