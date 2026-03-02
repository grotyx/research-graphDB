"""Tests for ReasoningHandler (Medical KAG MCP Server).

Covers:
- reason(): search + reasoning + response generation pipeline
- multi_hop_reason(): Neo4j multi-hop reasoning
- find_conflicts(): conflict detection from search results
- detect_conflicts(): intervention-outcome conflict detection
- compare_papers(): Neo4j paper comparison
- synthesize_evidence(): GRADE evidence synthesis
- clinical_recommend(): clinical recommendation engine
- Error handling: query too long, neo4j unavailable, import errors
- _parse_evidence_level() helper
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from enum import Enum

from medical_mcp.handlers.reasoning_handler import ReasoningHandler, MAX_QUERY_LENGTH


# =====================================================================
# Mock types
# =====================================================================

class MockConfidenceLevel(Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class MockReasoningResult:
    answer: str = "Test answer"
    evidence: list = field(default_factory=list)
    confidence: float = 0.85
    confidence_level: MockConfidenceLevel = MockConfidenceLevel.HIGH
    explanation: str = "Test explanation"
    reasoning_path: list = field(default_factory=list)


@dataclass
class MockFormattedResponse:
    markdown: str = "## Answer\nTest answer"
    plain_text: str = "Answer: Test answer"
    summary: str = "Test summary"
    evidence_by_level: dict = field(default_factory=dict)
    conflicts: object = None
    citations: list = field(default_factory=list)
    confidence: float = 0.85
    total_evidence: int = 3


@dataclass
class MockConflictType:
    value: str = "contradictory_results"


@dataclass
class MockConflictSeverity:
    value: str = "high"


@dataclass
class MockStudyResult:
    study_id: str = "doc_1"
    title: str = "Test Study"


@dataclass
class MockConflictPair:
    study1: MockStudyResult = field(default_factory=MockStudyResult)
    study2: MockStudyResult = field(default_factory=lambda: MockStudyResult(study_id="doc_2", title="Study 2"))
    conflict_type: MockConflictType = field(default_factory=MockConflictType)
    severity: MockConflictSeverity = field(default_factory=MockConflictSeverity)
    description: str = "Contradictory results"


@dataclass
class MockConflictOutput:
    has_conflicts: bool = True
    conflicts: list = field(default_factory=lambda: [MockConflictPair()])
    summary: str = "Found 1 conflict"


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def mock_server():
    """Create mock MedicalKAGServer."""
    server = MagicMock()

    # Search mock
    server.search = AsyncMock(return_value={
        "success": True,
        "results": [
            {
                "document_id": "doc_1",
                "content": "Test content about spine surgery",
                "evidence_level": "1b",
                "score": 0.9,
            },
            {
                "document_id": "doc_2",
                "content": "Another study on TLIF outcomes",
                "evidence_level": "2a",
                "score": 0.8,
            },
        ],
        "conflicts": None,
    })

    # Reasoner mock
    server.reasoner = MagicMock()
    server.reasoner.reason.return_value = MockReasoningResult()

    # Conflict detector mock
    server.conflict_detector = MagicMock()
    server.conflict_detector.detect.return_value = MockConflictOutput()

    # Response generator mock
    server.response_generator = MagicMock()
    server.response_generator.generate.return_value = MockFormattedResponse()

    # Neo4j client mock
    server.neo4j_client = MagicMock()
    server.neo4j_client._driver = MagicMock()
    server.neo4j_client.run_query = AsyncMock(return_value=[])
    server.neo4j_client.connect = AsyncMock()

    return server


@pytest.fixture
def handler(mock_server):
    """Create a ReasoningHandler with mocked server."""
    with patch("medical_mcp.handlers.reasoning_handler.ReasoningHandler.__init__", lambda self, srv: None):
        h = ReasoningHandler.__new__(ReasoningHandler)
        h.server = mock_server
        h.reasoner = mock_server.reasoner
        h.conflict_detector = mock_server.conflict_detector
        h.response_generator = mock_server.response_generator
        h.graph_available = True
        return h


# =====================================================================
# reason() tests
# =====================================================================

class TestReason:
    """Tests for reason() method."""

    @pytest.mark.asyncio
    async def test_reason_success(self, handler):
        result = await handler.reason("What is the best treatment for lumbar stenosis?")
        assert result["success"] is True
        assert result["answer"] == "Test answer"
        assert result["confidence"] == 0.85
        assert result["confidence_level"] == "high"
        assert "markdown_response" in result

    @pytest.mark.asyncio
    async def test_reason_query_too_long(self, handler):
        long_query = "x" * (MAX_QUERY_LENGTH + 1)
        result = await handler.reason(long_query)
        assert "error" in result
        assert "too long" in result["error"]

    @pytest.mark.asyncio
    async def test_reason_search_failure(self, handler):
        handler.server.search = AsyncMock(return_value={
            "success": False,
            "error": "Search failed"
        })
        result = await handler.reason("test question")
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_reason_with_no_conflicts(self, handler):
        result = await handler.reason("test question", include_conflicts=False)
        assert result["success"] is True
        # Verify conflicts are excluded in generator input
        call_args = handler.response_generator.generate.call_args
        generator_input = call_args[0][0]
        assert generator_input.conflicts is None

    @pytest.mark.asyncio
    async def test_reason_with_max_hops(self, handler):
        result = await handler.reason("test question", max_hops=5)
        assert result["success"] is True
        call_args = handler.reasoner.reason.call_args
        assert call_args[0][0].max_hops == 5


# =====================================================================
# multi_hop_reason() tests
# =====================================================================

class TestMultiHopReason:
    """Tests for multi_hop_reason() method."""

    @pytest.mark.asyncio
    async def test_multi_hop_query_too_long(self, handler):
        long_query = "x" * (MAX_QUERY_LENGTH + 1)
        result = await handler.multi_hop_reason(long_query)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_multi_hop_no_neo4j(self, handler):
        # Simulate neo4j_client being None via server property
        type(handler.server).neo4j_client = PropertyMock(return_value=None)
        result = await handler.multi_hop_reason("test question")
        assert result["success"] is False
        assert "not available" in result["error"]
        # Restore for other tests
        type(handler.server).neo4j_client = PropertyMock(return_value=MagicMock())

    @pytest.mark.asyncio
    async def test_multi_hop_import_error(self, handler):
        with patch.dict("sys.modules", {"solver.multi_hop_reasoning": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = await handler.multi_hop_reason("test question")
        # The safe_execute wrapper catches all exceptions
        assert result.get("success") is False or "error" in result


# =====================================================================
# find_conflicts() tests
# =====================================================================

class TestFindConflicts:
    """Tests for find_conflicts() method."""

    @pytest.mark.asyncio
    async def test_find_conflicts_success(self, handler):
        result = await handler.find_conflicts("TLIF fusion rate")
        assert result["success"] is True
        assert result["topic"] == "TLIF fusion rate"
        assert result["has_conflicts"] is True
        assert result["conflict_count"] >= 1
        assert len(result["conflicts"]) >= 1

    @pytest.mark.asyncio
    async def test_find_conflicts_query_too_long(self, handler):
        long_topic = "x" * (MAX_QUERY_LENGTH + 1)
        result = await handler.find_conflicts(long_topic)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_find_conflicts_not_enough_studies(self, handler):
        handler.server.search = AsyncMock(return_value={
            "success": True,
            "results": [{"document_id": "doc_1", "content": "only one study", "evidence_level": "2a"}],
        })
        result = await handler.find_conflicts("rare topic")
        assert result["success"] is True
        assert "Not enough" in result["message"]
        assert result["conflicts"] == []

    @pytest.mark.asyncio
    async def test_find_conflicts_search_failure(self, handler):
        handler.server.search = AsyncMock(return_value={
            "success": False,
            "error": "Search failed"
        })
        result = await handler.find_conflicts("test topic")
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_find_conflicts_with_document_ids(self, handler):
        result = await handler.find_conflicts("TLIF", document_ids=["doc_1", "doc_2"])
        assert result["success"] is True


# =====================================================================
# _parse_evidence_level() tests
# =====================================================================

class TestParseEvidenceLevel:
    """Tests for _parse_evidence_level() helper."""

    def test_parse_level_1a(self, handler):
        result = handler._parse_evidence_level("1a")
        assert result.value == "1a"

    def test_parse_level_1b(self, handler):
        result = handler._parse_evidence_level("1b")
        assert result.value == "1b"

    def test_parse_level_2a(self, handler):
        result = handler._parse_evidence_level("2a")
        assert result.value == "2a"

    def test_parse_level_4(self, handler):
        result = handler._parse_evidence_level("4")
        assert result.value == "4"

    def test_parse_level_unknown_defaults_to_5(self, handler):
        result = handler._parse_evidence_level("unknown")
        assert result.value == "5"

    def test_parse_level_empty_defaults_to_5(self, handler):
        result = handler._parse_evidence_level("")
        assert result.value == "5"


# =====================================================================
# detect_conflicts() tests
# =====================================================================

class TestDetectConflicts:
    """Tests for detect_conflicts() method."""

    @pytest.mark.asyncio
    async def test_detect_conflicts_no_graph(self, handler):
        handler.graph_available = False
        result = await handler.detect_conflicts("TLIF")
        assert result["success"] is False
        assert "not available" in result["error"]
        handler.graph_available = True  # restore

    @pytest.mark.asyncio
    async def test_detect_conflicts_no_neo4j_client(self, handler):
        type(handler.server).neo4j_client = PropertyMock(return_value=None)
        result = await handler.detect_conflicts("TLIF")
        assert result["success"] is False
        type(handler.server).neo4j_client = PropertyMock(return_value=MagicMock(_driver=MagicMock()))


# =====================================================================
# compare_papers() tests
# =====================================================================

class TestComparePapers:
    """Tests for compare_papers() method."""

    @pytest.mark.asyncio
    async def test_compare_papers_too_few(self, handler):
        result = await handler.compare_papers(["single_paper"])
        assert result["success"] is False
        assert "At least 2" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_papers_empty_list(self, handler):
        result = await handler.compare_papers([])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_compare_papers_success(self, handler):
        mock_neo4j = handler.server.neo4j_client
        mock_neo4j._driver = MagicMock()
        mock_neo4j.connect = AsyncMock()
        mock_neo4j.run_query = AsyncMock(return_value=[
            {
                "paper_id": "paper_1",
                "title": "TLIF Study",
                "year": 2023,
                "evidence_level": "1b",
                "sub_domain": "degenerative",
                "study_type": "RCT",
                "sample_size": 100,
                "pathologies": ["Lumbar Stenosis"],
                "interventions": ["TLIF"],
                "anatomy_levels": ["L4-5"],
                "outcomes": [{"intervention": "TLIF", "outcome": "Fusion Rate", "direction": "improved", "p_value": 0.01, "is_significant": True, "effect_size": 0.8}],
            },
            {
                "paper_id": "paper_2",
                "title": "PLIF Study",
                "year": 2022,
                "evidence_level": "2a",
                "sub_domain": "degenerative",
                "study_type": "Cohort",
                "sample_size": 80,
                "pathologies": ["Lumbar Stenosis"],
                "interventions": ["PLIF"],
                "anatomy_levels": ["L4-5"],
                "outcomes": [{"intervention": "PLIF", "outcome": "Fusion Rate", "direction": "improved", "p_value": 0.03, "is_significant": True, "effect_size": 0.6}],
            },
        ])

        result = await handler.compare_papers(["paper_1", "paper_2"])
        assert result["success"] is True
        assert len(result["papers"]) == 2
        assert result["comparison"]["total_papers"] == 2
        assert "Lumbar Stenosis" in result["comparison"]["common_pathologies"]


# =====================================================================
# synthesize_evidence() tests
# =====================================================================

class TestSynthesizeEvidence:
    """Tests for synthesize_evidence() method."""

    @pytest.mark.asyncio
    async def test_synthesize_no_graph(self, handler):
        handler.graph_available = False
        result = await handler.synthesize_evidence("TLIF", "Fusion Rate")
        assert result["success"] is False
        handler.graph_available = True

    @pytest.mark.asyncio
    async def test_synthesize_no_neo4j(self, handler):
        type(handler.server).neo4j_client = PropertyMock(return_value=None)
        result = await handler.synthesize_evidence("TLIF", "Fusion Rate")
        assert result["success"] is False
        type(handler.server).neo4j_client = PropertyMock(return_value=MagicMock(_driver=MagicMock()))


# =====================================================================
# clinical_recommend() tests
# =====================================================================

class TestClinicalRecommend:
    """Tests for clinical_recommend() method."""

    @pytest.mark.asyncio
    async def test_clinical_recommend_no_context(self, handler):
        result = await handler.clinical_recommend("")
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_clinical_recommend_empty_context(self, handler):
        result = await handler.clinical_recommend("")
        assert result["success"] is False


# =====================================================================
# safe_execute decorator tests
# =====================================================================

class TestSafeExecute:
    """Tests for the safe_execute decorator behavior."""

    @pytest.mark.asyncio
    async def test_exception_caught_by_safe_execute(self, handler):
        """Ensure unhandled exceptions are caught by safe_execute decorator."""
        handler.server.search = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        result = await handler.reason("test question")
        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @pytest.mark.asyncio
    async def test_value_error_caught(self, handler):
        handler.server.search = AsyncMock(side_effect=ValueError("Bad value"))
        result = await handler.reason("test")
        assert result["success"] is False
