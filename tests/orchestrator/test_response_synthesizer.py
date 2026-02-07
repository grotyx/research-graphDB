"""Unit tests for ResponseSynthesizer.

ResponseSynthesizer의 주요 기능을 테스트:
- Graph evidence formatting
- Vector context formatting
- Citation generation
- Conflict detection
- Confidence calculation
"""

import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from src.orchestrator.response_synthesizer import (
    ResponseSynthesizer,
    SynthesizedResponse,
    EVIDENCE_LEVEL_DESCRIPTIONS
)
from src.solver.graph_result import GraphEvidence, PaperNode
from src.solver.hybrid_ranker import HybridResult
from src.storage import SearchResult as VectorSearchResult


@pytest.fixture
def sample_graph_evidence():
    """샘플 Graph Evidence."""
    return GraphEvidence(
        intervention="TLIF",
        outcome="Fusion Rate",
        value="92%",
        value_control="85%",
        p_value=0.001,
        is_significant=True,
        direction="improved",
        source_paper_id="paper_001",
        evidence_level="1b",
        effect_size="Cohen's d=0.8",
        confidence_interval="95% CI: 88-96%"
    )


@pytest.fixture
def sample_paper():
    """샘플 PaperNode."""
    return PaperNode(
        paper_id="paper_001",
        title="TLIF for Lumbar Degenerative Disease",
        authors=["Kim", "Lee", "Park"],
        year=2024,
        journal="Spine",
        evidence_level="1b"
    )


@pytest.fixture
def sample_vector_result():
    """샘플 Vector SearchResult."""
    return VectorSearchResult(
        chunk_id="chunk_001",
        document_id="paper_001",
        source_type="neo4j",
        content="TLIF is a minimally invasive fusion technique that preserves posterior structures.",
        score=0.85,
        title="TLIF Review",
        publication_year=2024,
        section="introduction",
        tier="tier1",
        summary="TLIF preserves posterior structures",
        has_statistics=False,
        is_key_finding=False,
        evidence_level="1b",
        metadata={"paper_id": "paper_001"}
    )


@pytest.fixture
def synthesizer():
    """ResponseSynthesizer (LLM 없이)."""
    # Pass mock LLM client directly to avoid API key requirement
    mock_llm_client = MagicMock()
    return ResponseSynthesizer(llm_client=mock_llm_client, use_llm_synthesis=False)


def test_format_graph_evidence(synthesizer, sample_graph_evidence, sample_paper):
    """Graph evidence 포맷팅 테스트."""
    hybrid_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence,
        paper=sample_paper
    )

    formatted = synthesizer.format_graph_evidence([hybrid_result])

    assert len(formatted) == 1
    assert "TLIF" in formatted[0]
    assert "improved" in formatted[0]
    assert "Fusion Rate" in formatted[0]
    assert "92%" in formatted[0]
    assert "p=0.001" in formatted[0]
    assert "Level 1b" in formatted[0]


def test_format_vector_context(synthesizer, sample_vector_result):
    """Vector context 포맷팅 테스트."""
    hybrid_result = HybridResult(
        result_type="vector",
        score=0.85,
        content=sample_vector_result.content,
        source_id="chunk_001",
        vector_result=sample_vector_result
    )

    formatted = synthesizer.format_vector_context([hybrid_result])

    assert len(formatted) == 1
    assert "Introduction:" in formatted[0]
    assert "TLIF" in formatted[0]


def test_generate_citations(synthesizer, sample_graph_evidence, sample_paper):
    """Citation 생성 테스트."""
    hybrid_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence,
        paper=sample_paper
    )

    citations = synthesizer.generate_citations([hybrid_result])

    assert len(citations) == 1
    assert "Kim et al." in citations[0]
    assert "2024" in citations[0]
    assert "Spine" in citations[0]


def test_summarize_conflicts_no_conflict(synthesizer, sample_graph_evidence):
    """충돌 없는 경우 테스트."""
    hybrid_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence
    )

    conflicts = synthesizer.summarize_conflicts([hybrid_result])

    assert len(conflicts) == 0


def test_summarize_conflicts_with_conflict(synthesizer):
    """충돌 있는 경우 테스트."""
    evidence1 = GraphEvidence(
        intervention="TLIF",
        outcome="PJK",
        value="15%",
        direction="improved",
        source_paper_id="paper_001",
        evidence_level="1b"
    )

    evidence2 = GraphEvidence(
        intervention="TLIF",
        outcome="PJK",
        value="25%",
        direction="worsened",
        source_paper_id="paper_002",
        evidence_level="2a"
    )

    results = [
        HybridResult(
            result_type="graph",
            score=0.95,
            content=evidence1.get_display_text(),
            source_id="paper_001",
            evidence=evidence1
        ),
        HybridResult(
            result_type="graph",
            score=0.90,
            content=evidence2.get_display_text(),
            source_id="paper_002",
            evidence=evidence2
        )
    ]

    conflicts = synthesizer.summarize_conflicts(results)

    assert len(conflicts) == 1
    assert "TLIF" in conflicts[0]
    assert "PJK" in conflicts[0]
    assert "improved" in conflicts[0]
    assert "worsened" in conflicts[0]


def test_calculate_confidence(synthesizer, sample_graph_evidence):
    """Confidence score 계산 테스트."""
    hybrid_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence
    )

    confidence = synthesizer._calculate_confidence([hybrid_result])

    # High quality evidence (1b) + significant → high confidence
    assert confidence > 0.9


def test_create_evidence_summary(synthesizer, sample_graph_evidence, sample_vector_result):
    """Evidence summary 생성 테스트."""
    graph_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence
    )

    vector_result = HybridResult(
        result_type="vector",
        score=0.85,
        content=sample_vector_result.content,
        source_id="chunk_001",
        vector_result=sample_vector_result
    )

    summary = synthesizer._create_evidence_summary([graph_result], [vector_result])

    assert "1 graph evidences" in summary
    assert "statistically significant" in summary
    assert "1 relevant contexts" in summary


@pytest.mark.asyncio
async def test_synthesize_template(synthesizer, sample_graph_evidence, sample_paper):
    """Template 기반 synthesis 테스트."""
    hybrid_result = HybridResult(
        result_type="graph",
        score=0.95,
        content=sample_graph_evidence.get_display_text(),
        source_id="paper_001",
        evidence=sample_graph_evidence,
        paper=sample_paper
    )

    response = await synthesizer.synthesize(
        query="Is TLIF effective for fusion?",
        hybrid_results=[hybrid_result],
        max_evidences=5,
        max_contexts=3
    )

    assert isinstance(response, SynthesizedResponse)
    assert len(response.answer) > 0
    assert "TLIF" in response.answer
    assert len(response.graph_evidences) == 1
    assert len(response.supporting_papers) == 1
    assert response.confidence_score > 0.0


def test_evidence_level_descriptions():
    """Evidence level 설명 테스트."""
    assert "1a" in EVIDENCE_LEVEL_DESCRIPTIONS
    assert "Meta-analysis" in EVIDENCE_LEVEL_DESCRIPTIONS["1a"]
    assert "1b" in EVIDENCE_LEVEL_DESCRIPTIONS
    assert "RCT" in EVIDENCE_LEVEL_DESCRIPTIONS["1b"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
