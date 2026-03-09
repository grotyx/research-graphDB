"""Tests for Agentic RAG Framework.

Comprehensive test suite covering:
    - Base RAGAgent functionality
    - SearchAgent, SynthesisAgent, ValidationAgent, PlanningAgent
    - AgentOrchestrator with ReAct pattern
    - End-to-end agentic workflows
"""

import asyncio
import pytest
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.solver.agentic_rag import (
    # Data structures
    AgentType,
    ActionType,
    AgentTask,
    AgentResult,
    ReActStep,
    AgentResponse,
    # Agents
    RAGAgent,
    SearchAgent,
    SynthesisAgent,
    ValidationAgent,
    PlanningAgent,
    AgentOrchestrator,
    # Functions
    quick_solve
)


# =============================================================================
# Mock Classes
# =============================================================================

class MockRAGAgent(RAGAgent):
    """Mock agent for testing base class."""

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute mock task."""
        return AgentResult(
            success=True,
            result={"mock": "result"},
            reasoning="Mock reasoning",
            confidence=0.8
        )

    def get_description(self) -> str:
        """Get description."""
        return "Mock agent for testing"


@dataclass
class MockSearchResult:
    """Mock search result."""
    paper_id: str
    title: str
    final_score: float
    graph_score: float = 0.0
    vector_score: float = 0.0
    evidence: Optional[Any] = None


@dataclass
class MockSearchResponse:
    """Mock search response."""
    results: List[MockSearchResult]
    query_analysis: Any
    execution_time_ms: float = 100.0
    synthesis: Optional[Any] = None
    conflicts: Optional[List[Any]] = None


@dataclass
class MockQueryAnalysis:
    """Mock query analysis."""
    query_type: Any
    confidence: float


@dataclass
class MockQueryType:
    """Mock query type."""
    value: str = "factual"


@dataclass
class MockEvidence:
    """Mock evidence."""
    intervention: str
    outcome: str
    p_value: float = 0.01


@dataclass
class MockSynthesis:
    """Mock synthesis result."""
    direction: str
    strength: Any
    grade_rating: str
    supporting_papers: List[str]


class MockEvidenceStrength(Enum):
    """Mock evidence strength."""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


# =============================================================================
# Test Base Agent
# =============================================================================

@pytest.mark.asyncio
async def test_rag_agent_initialization():
    """Test RAGAgent initialization."""
    agent = MockRAGAgent(
        agent_id="test-agent",
        agent_type=AgentType.SEARCH,
        config={"test": "config"}
    )

    assert agent.agent_id == "test-agent"
    assert agent.agent_type == AgentType.SEARCH
    assert agent.config == {"test": "config"}
    assert agent.memory == []


@pytest.mark.asyncio
async def test_rag_agent_execute():
    """Test RAGAgent execute method."""
    agent = MockRAGAgent(
        agent_id="test-agent",
        agent_type=AgentType.SEARCH
    )

    task = AgentTask(
        task_id="task-1",
        description="Test task"
    )

    result = await agent.execute(task)

    assert result.success
    assert result.result == {"mock": "result"}
    assert result.reasoning == "Mock reasoning"
    assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_rag_agent_memory():
    """Test agent memory management."""
    agent = MockRAGAgent(
        agent_id="test-agent",
        agent_type=AgentType.SEARCH
    )

    # Add results to memory
    for i in range(15):
        result = AgentResult(
            success=True,
            result=f"result-{i}",
            reasoning=f"reasoning-{i}",
            confidence=0.8
        )
        agent.add_to_memory(result)

    # Memory should keep only last 10
    assert len(agent.memory) == 10
    assert agent.memory[0].result == "result-5"


@pytest.mark.asyncio
async def test_rag_agent_memory_context():
    """Test agent memory context retrieval."""
    agent = MockRAGAgent(
        agent_id="test-agent",
        agent_type=AgentType.SEARCH
    )

    # Empty memory
    context = agent.get_memory_context()
    assert context == "No previous context."

    # Add results
    for i in range(5):
        result = AgentResult(
            success=True,
            result=f"result-{i}",
            reasoning=f"This is reasoning number {i}" * 10,  # Long reasoning
            confidence=0.8
        )
        agent.add_to_memory(result)

    # Get context (should have last 3)
    context = agent.get_memory_context()
    assert "confidence: 0.80" in context
    assert len(context.split("\n")) == 3


# =============================================================================
# Test SearchAgent
# =============================================================================

@pytest.mark.asyncio
async def test_search_agent_initialization():
    """Test SearchAgent initialization."""
    mock_pipeline = Mock()
    agent = SearchAgent(pipeline=mock_pipeline)

    assert agent.agent_id == "search_agent"
    assert agent.agent_type == AgentType.SEARCH
    assert agent.pipeline == mock_pipeline


@pytest.mark.asyncio
async def test_search_agent_execute_success():
    """Test SearchAgent successful execution."""
    # Create mock pipeline
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    # Mock search response
    mock_results = [
        MockSearchResult(
            paper_id="PMC1",
            title="Paper 1",
            final_score=0.9,
            evidence=MockEvidence(intervention="TLIF", outcome="Fusion rate")
        )
    ]

    mock_response = MockSearchResponse(
        results=mock_results,
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        ),
        synthesis=MockSynthesis(
            direction="improved",
            strength=MockEvidenceStrength.MODERATE,
            grade_rating="2A",
            supporting_papers=["PMC1"]
        )
    )

    mock_pipeline.search.return_value = mock_response

    # Create agent
    agent = SearchAgent(pipeline=mock_pipeline)

    # Create task
    task = AgentTask(
        task_id="search-1",
        description="What is the fusion rate of TLIF?",
        agent_type=AgentType.SEARCH
    )

    # Execute
    result = await agent.execute(task)

    # Verify
    assert result.success
    assert result.result == mock_response
    assert "factual" in result.reasoning
    assert "GRADE: 2A" in result.reasoning
    assert result.confidence > 0.0
    assert len(agent.memory) == 1


@pytest.mark.asyncio
async def test_search_agent_execute_failure():
    """Test SearchAgent execution failure."""
    # Create mock pipeline that raises error
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock(side_effect=Exception("Search failed"))

    # Create agent
    agent = SearchAgent(pipeline=mock_pipeline)

    # Create task
    task = AgentTask(
        task_id="search-1",
        description="Test query"
    )

    # Execute
    result = await agent.execute(task)

    # Verify
    assert not result.success
    assert result.result is None
    assert "Search failed" in result.reasoning
    assert result.confidence == 0.0
    assert result.error == "Search failed"


@pytest.mark.asyncio
async def test_search_agent_with_constraints():
    """Test SearchAgent with task constraints."""
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_response = MockSearchResponse(
        results=[],
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    agent = SearchAgent(pipeline=mock_pipeline)

    task = AgentTask(
        task_id="search-1",
        description="Test query",
        constraints={"top_k": 20, "min_evidence_level": "2a"}
    )

    result = await agent.execute(task)

    # Verify search was called with constraints
    assert mock_pipeline.search.called
    call_args = mock_pipeline.search.call_args
    options = call_args[0][1]  # SearchOptions
    assert options.top_k == 20
    assert options.min_evidence_level == "2a"


# =============================================================================
# Test SynthesisAgent
# =============================================================================

@pytest.mark.asyncio
async def test_synthesis_agent_initialization():
    """Test SynthesisAgent initialization."""
    mock_synthesizer = Mock()
    mock_llm = Mock()

    agent = SynthesisAgent(
        synthesizer=mock_synthesizer,
        llm_client=mock_llm
    )

    assert agent.agent_id == "synthesis_agent"
    assert agent.agent_type == AgentType.SYNTHESIS
    assert agent.synthesizer == mock_synthesizer
    assert agent.llm_client == mock_llm


@pytest.mark.asyncio
async def test_synthesis_agent_execute_success():
    """Test SynthesisAgent successful execution."""
    # Mock synthesizer
    mock_synthesizer = Mock()
    mock_synthesizer.synthesize = AsyncMock()

    mock_synthesis = MockSynthesis(
        direction="improved",
        strength=MockEvidenceStrength.MODERATE,
        grade_rating="2A",
        supporting_papers=["PMC1", "PMC2"]
    )

    mock_synthesizer.synthesize.return_value = mock_synthesis

    # Create agent (without LLM for simplicity)
    agent = SynthesisAgent(synthesizer=mock_synthesizer, llm_client=None)

    # Create task
    task = AgentTask(
        task_id="synth-1",
        description="Synthesize evidence",
        context={
            "intervention": "TLIF",
            "outcome": "Fusion rate"
        }
    )

    # Execute
    result = await agent.execute(task)

    # Verify
    assert result.success
    assert "synthesis" in result.result
    assert "summary" in result.result
    assert "improved" in result.result["summary"]
    assert "2A" in result.reasoning
    # Mock enum doesn't match real EvidenceStrength, so confidence is 0.5 (default)
    assert 0.5 <= result.confidence <= 0.7


@pytest.mark.asyncio
async def test_synthesis_agent_missing_context():
    """Test SynthesisAgent with missing intervention/outcome."""
    mock_synthesizer = Mock()

    agent = SynthesisAgent(synthesizer=mock_synthesizer)

    task = AgentTask(
        task_id="synth-1",
        description="Synthesize evidence",
        context={}  # Missing intervention/outcome
    )

    result = await agent.execute(task)

    assert not result.success
    assert "Intervention and outcome required" in result.reasoning


@pytest.mark.asyncio
async def test_synthesis_agent_with_llm():
    """Test SynthesisAgent with LLM summary generation."""
    # Mock synthesizer
    mock_synthesizer = Mock()
    mock_synthesizer.synthesize = AsyncMock()

    mock_synthesis = MockSynthesis(
        direction="improved",
        strength=MockEvidenceStrength.STRONG,
        grade_rating="1A",
        supporting_papers=["PMC1", "PMC2", "PMC3"]
    )

    mock_synthesizer.synthesize.return_value = mock_synthesis

    # Mock LLM
    mock_llm = Mock()
    mock_llm.generate = AsyncMock()

    mock_llm_response = Mock()
    mock_llm_response.text = "TLIF shows improved fusion rates with strong evidence."
    mock_llm.generate.return_value = mock_llm_response

    # Create agent with LLM
    agent = SynthesisAgent(
        synthesizer=mock_synthesizer,
        llm_client=mock_llm
    )

    task = AgentTask(
        task_id="synth-1",
        description="Synthesize evidence",
        context={
            "intervention": "TLIF",
            "outcome": "Fusion rate"
        }
    )

    result = await agent.execute(task)

    # Verify LLM was used
    assert result.success
    assert "improved fusion rates" in result.result["summary"]
    assert mock_llm.generate.called


# =============================================================================
# Test ValidationAgent
# =============================================================================

@pytest.mark.asyncio
async def test_validation_agent_initialization():
    """Test ValidationAgent initialization."""
    mock_neo4j = Mock()
    mock_llm = Mock()

    agent = ValidationAgent(
        neo4j_client=mock_neo4j,
        llm_client=mock_llm
    )

    assert agent.agent_id == "validation_agent"
    assert agent.agent_type == AgentType.VALIDATION


@pytest.mark.asyncio
async def test_validation_agent_execute_success():
    """Test ValidationAgent successful execution."""
    agent = ValidationAgent(neo4j_client=None, llm_client=None)

    # Mock evidence
    mock_evidence = [
        MockSearchResult(
            paper_id="PMC1",
            title="TLIF improves fusion",
            final_score=0.9
        )
    ]

    # Mock synthesis
    mock_synthesis = MockSynthesis(
        direction="improved",
        strength=MockEvidenceStrength.STRONG,
        grade_rating="1A",
        supporting_papers=["PMC1"]
    )

    task = AgentTask(
        task_id="val-1",
        description="Validate answer",
        context={
            "answer": "TLIF improves fusion rates",
            "evidence": mock_evidence,
            "synthesis": mock_synthesis
        }
    )

    result = await agent.execute(task)

    assert result.success
    assert result.result["has_evidence"]
    assert result.result["evidence_count"] == 1
    assert result.result["has_synthesis"]
    assert result.result["grade_rating"] == "1A"
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_validation_agent_missing_answer():
    """Test ValidationAgent with missing answer."""
    agent = ValidationAgent()

    task = AgentTask(
        task_id="val-1",
        description="Validate answer",
        context={}  # Missing answer
    )

    result = await agent.execute(task)

    assert not result.success
    assert "Answer required" in result.reasoning


@pytest.mark.asyncio
async def test_validation_agent_with_llm():
    """Test ValidationAgent with LLM consistency check."""
    # Mock LLM
    mock_llm = Mock()
    mock_llm.generate_json = AsyncMock()

    mock_llm.generate_json.return_value = {
        "is_consistent": True,
        "reasoning": "Answer is supported by evidence"
    }

    agent = ValidationAgent(neo4j_client=None, llm_client=mock_llm)

    task = AgentTask(
        task_id="val-1",
        description="Validate answer",
        context={
            "answer": "TLIF improves fusion",
            "evidence": [
                MockSearchResult(
                    paper_id="PMC1",
                    title="TLIF study",
                    final_score=0.9
                )
            ]
        }
    )

    result = await agent.execute(task)

    assert result.success
    assert result.result["is_consistent"]
    assert "supported by evidence" in result.result["reasoning"]
    assert mock_llm.generate_json.called


# =============================================================================
# Test PlanningAgent
# =============================================================================

@pytest.mark.asyncio
async def test_planning_agent_initialization():
    """Test PlanningAgent initialization."""
    mock_llm = Mock()

    agent = PlanningAgent(llm_client=mock_llm)

    assert agent.agent_id == "planning_agent"
    assert agent.agent_type == AgentType.PLANNING


@pytest.mark.asyncio
async def test_planning_agent_simple_query():
    """Test PlanningAgent with simple query (no decomposition)."""
    agent = PlanningAgent(llm_client=None)

    task = AgentTask(
        task_id="plan-1",
        description="What is the fusion rate of TLIF?"
    )

    result = await agent.execute(task)

    assert result.success
    assert len(result.result) == 1  # Single task
    assert result.result[0].description == task.description
    assert "no decomposition" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_planning_agent_comparison_query():
    """Test PlanningAgent with comparison query."""
    agent = PlanningAgent(llm_client=None)

    task = AgentTask(
        task_id="plan-1",
        description="Compare TLIF vs OLIF for lumbar stenosis"
    )

    result = await agent.execute(task)

    assert result.success
    assert len(result.result) == 3  # Search TLIF, Search OLIF, Compare
    # Check that TLIF and OLIF are in the descriptions (may be combined with "compare")
    desc_0 = result.result[0].description.lower()
    desc_1 = result.result[1].description.lower()
    # First two should be searches
    assert "tlif" in desc_0 or "olif" in desc_0
    assert "tlif" in desc_1 or "olif" in desc_1
    assert result.result[2].agent_type == AgentType.SYNTHESIS


@pytest.mark.asyncio
async def test_planning_agent_with_llm():
    """Test PlanningAgent with LLM decomposition."""
    # Mock LLM
    mock_llm = Mock()
    mock_llm.generate_json = AsyncMock()

    mock_llm.generate_json.return_value = {
        "needs_decomposition": True,
        "sub_tasks": [
            {
                "description": "Search for TLIF outcomes",
                "agent_type": "search"
            },
            {
                "description": "Search for patient demographics",
                "agent_type": "search"
            },
            {
                "description": "Synthesize evidence",
                "agent_type": "synthesis"
            }
        ]
    }

    agent = PlanningAgent(llm_client=mock_llm)

    task = AgentTask(
        task_id="plan-1",
        description="What are TLIF outcomes in elderly patients?"
    )

    result = await agent.execute(task)

    assert result.success
    assert len(result.result) == 3
    assert result.result[0].agent_type == AgentType.SEARCH
    assert result.result[2].agent_type == AgentType.SYNTHESIS
    assert mock_llm.generate_json.called


# =============================================================================
# Test AgentOrchestrator
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_initialization():
    """Test AgentOrchestrator initialization."""
    orchestrator = AgentOrchestrator(
        neo4j_client=None,
        llm_client=None
    )

    assert orchestrator.pipeline is not None
    assert AgentType.SEARCH in orchestrator.agents
    # Without neo4j/llm, some agents won't be available
    assert len(orchestrator.agents) >= 1


@pytest.mark.asyncio
async def test_orchestrator_solve_simple():
    """Test AgentOrchestrator with simple query."""
    # Create mocks
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_results = [
        MockSearchResult(
            paper_id="PMC1",
            title="TLIF fusion study",
            final_score=0.9,
            evidence=MockEvidence(intervention="TLIF", outcome="Fusion rate")
        )
    ]

    mock_response = MockSearchResponse(
        results=mock_results,
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    # Patch UnifiedSearchPipeline
    with patch('src.solver.agentic_rag.UnifiedSearchPipeline') as mock_cls:
        mock_cls.return_value = mock_pipeline

        orchestrator = AgentOrchestrator(
            neo4j_client=None,
            llm_client=None
        )

        # Override pipeline
        orchestrator.pipeline = mock_pipeline

        # Solve
        response = await orchestrator.solve("What is the fusion rate of TLIF?")

        # Verify
        assert isinstance(response, AgentResponse)
        assert len(response.reasoning_chain) > 0
        assert response.confidence > 0.0
        assert len(response.sources) > 0


@pytest.mark.asyncio
async def test_orchestrator_solve_with_planning():
    """Test AgentOrchestrator with planning decomposition."""
    # Create mocks
    mock_llm = Mock()
    mock_llm.generate_json = AsyncMock()

    # Mock planning decomposition
    mock_llm.generate_json.return_value = {
        "needs_decomposition": False,
        "sub_tasks": [
            {
                "description": "Search for TLIF",
                "agent_type": "search"
            }
        ]
    }

    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_results = [
        MockSearchResult(
            paper_id="PMC1",
            title="Test paper",
            final_score=0.8
        )
    ]

    mock_response = MockSearchResponse(
        results=mock_results,
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    with patch('src.solver.agentic_rag.UnifiedSearchPipeline') as mock_cls:
        mock_cls.return_value = mock_pipeline

        orchestrator = AgentOrchestrator(
            neo4j_client=None,
            llm_client=mock_llm
        )

        orchestrator.pipeline = mock_pipeline

        response = await orchestrator.solve("Test query")

        # Verify planning was used
        assert len(response.reasoning_chain) >= 2  # Planning + Search
        assert response.reasoning_chain[0].action == ActionType.DECOMPOSE_QUERY


@pytest.mark.asyncio
async def test_orchestrator_reasoning_chain():
    """Test AgentOrchestrator reasoning chain structure."""
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_response = MockSearchResponse(
        results=[],
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    with patch('src.solver.agentic_rag.UnifiedSearchPipeline') as mock_cls:
        mock_cls.return_value = mock_pipeline

        orchestrator = AgentOrchestrator(
            neo4j_client=None,
            llm_client=None
        )

        orchestrator.pipeline = mock_pipeline

        response = await orchestrator.solve("Test query")

        # Verify reasoning chain
        for step in response.reasoning_chain:
            assert isinstance(step, ReActStep)
            assert step.step_id > 0
            assert step.thought != ""
            assert isinstance(step.action, ActionType)
            assert isinstance(step.action_input, dict)
            assert step.observation != ""
            assert step.duration_ms >= 0


@pytest.mark.asyncio
async def test_orchestrator_error_handling():
    """Test AgentOrchestrator error handling."""
    # Create pipeline that raises error
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock(side_effect=Exception("Search error"))

    with patch('src.solver.agentic_rag.UnifiedSearchPipeline') as mock_cls:
        mock_cls.return_value = mock_pipeline

        orchestrator = AgentOrchestrator(
            neo4j_client=None,
            llm_client=None
        )

        orchestrator.pipeline = mock_pipeline

        response = await orchestrator.solve("Test query")

        # Should return error response, not raise
        # When search fails, answer will be default message
        assert response.confidence <= 0.5  # Low confidence due to error
        assert len(response.reasoning_chain) > 0  # Still has reasoning steps


# =============================================================================
# Test Data Structures
# =============================================================================

def test_agent_task_creation():
    """Test AgentTask creation."""
    task = AgentTask(
        task_id="task-1",
        description="Test task",
        context={"key": "value"},
        constraints={"timeout": 30},
        agent_type=AgentType.SEARCH,
        priority=8
    )

    assert task.task_id == "task-1"
    assert task.description == "Test task"
    assert task.context["key"] == "value"
    assert task.constraints["timeout"] == 30
    assert task.agent_type == AgentType.SEARCH
    assert task.priority == 8


def test_agent_result_creation():
    """Test AgentResult creation."""
    result = AgentResult(
        success=True,
        result={"data": "value"},
        reasoning="Test reasoning",
        confidence=0.85,
        metadata={"time": 100},
        error=None
    )

    assert result.success
    assert result.result["data"] == "value"
    assert result.reasoning == "Test reasoning"
    assert result.confidence == 0.85
    assert result.metadata["time"] == 100
    assert result.error is None


def test_react_step_creation():
    """Test ReActStep creation."""
    step = ReActStep(
        step_id=1,
        thought="I need to search for evidence",
        action=ActionType.SEARCH_HYBRID,
        action_input={"query": "test"},
        observation="Found 10 results",
        duration_ms=150.5
    )

    assert step.step_id == 1
    assert "search" in step.thought.lower()
    assert step.action == ActionType.SEARCH_HYBRID
    assert step.action_input["query"] == "test"
    assert "10 results" in step.observation
    assert step.duration_ms == 150.5


def test_agent_response_creation():
    """Test AgentResponse creation."""
    steps = [
        ReActStep(
            step_id=1,
            thought="Test",
            action=ActionType.SEARCH_HYBRID,
            action_input={},
            observation="Test"
        )
    ]

    response = AgentResponse(
        final_answer="Test answer",
        reasoning_chain=steps,
        sources=[{"paper_id": "PMC1"}],
        confidence=0.8,
        evidence_grade="2A",
        metadata={"duration_s": 5.0}
    )

    assert response.final_answer == "Test answer"
    assert len(response.reasoning_chain) == 1
    assert len(response.sources) == 1
    assert response.confidence == 0.8
    assert response.evidence_grade == "2A"


# =============================================================================
# Test Enums
# =============================================================================

def test_agent_type_enum():
    """Test AgentType enum."""
    assert AgentType.SEARCH.value == "search"
    assert AgentType.SYNTHESIS.value == "synthesis"
    assert AgentType.VALIDATION.value == "validation"
    assert AgentType.PLANNING.value == "planning"


def test_action_type_enum():
    """Test ActionType enum."""
    assert ActionType.SEARCH_GRAPH.value == "search_graph"
    assert ActionType.SEARCH_VECTOR.value == "search_vector"
    assert ActionType.SEARCH_HYBRID.value == "search_hybrid"
    assert ActionType.SYNTHESIZE_EVIDENCE.value == "synthesize_evidence"
    assert ActionType.VALIDATE_ANSWER.value == "validate_answer"
    assert ActionType.DECOMPOSE_QUERY.value == "decompose_query"
    assert ActionType.TERMINATE.value == "terminate"


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_end_to_end_simple_query():
    """Test end-to-end simple query workflow."""
    # This would require actual Neo4j/Vector DB/LLM setup
    # For now, test with mocks

    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_response = MockSearchResponse(
        results=[
            MockSearchResult(
                paper_id="PMC1",
                title="TLIF fusion study",
                final_score=0.9
            )
        ],
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    with patch('src.solver.agentic_rag.UnifiedSearchPipeline') as mock_cls:
        mock_cls.return_value = mock_pipeline

        orchestrator = AgentOrchestrator(
            neo4j_client=None,
            llm_client=None
        )

        orchestrator.pipeline = mock_pipeline

        response = await orchestrator.solve(
            query="What is the fusion rate of TLIF?",
            context={"evidence_level": "2a"}
        )

        assert response.final_answer != ""
        assert len(response.reasoning_chain) > 0
        assert response.confidence > 0.0


@pytest.mark.asyncio
async def test_agent_memory_persistence():
    """Test that agent memory persists across executions."""
    mock_pipeline = Mock()
    mock_pipeline.search = AsyncMock()

    mock_response = MockSearchResponse(
        results=[],
        query_analysis=MockQueryAnalysis(
            query_type=MockQueryType(value="factual"),
            confidence=0.8
        )
    )

    mock_pipeline.search.return_value = mock_response

    agent = SearchAgent(pipeline=mock_pipeline)

    # Execute multiple tasks
    for i in range(3):
        task = AgentTask(
            task_id=f"task-{i}",
            description=f"Query {i}"
        )
        await agent.execute(task)

    # Memory should have 3 results
    assert len(agent.memory) == 3

    # Memory context should reference recent results
    context = agent.get_memory_context()
    assert "confidence: 0." in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
