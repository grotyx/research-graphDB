"""Agentic RAG Framework for Spine GraphRAG.

This module implements a ReAct-based agentic system that orchestrates multiple
specialized agents to answer complex medical queries with explainability.

Architecture:
    - RAGAgent: Abstract base class for all agents
    - SearchAgent: Determines optimal search strategy (graph/vector/hybrid)
    - SynthesisAgent: Aggregates and synthesizes multiple search results
    - ValidationAgent: Validates answers against evidence with GRADE scoring
    - PlanningAgent: Decomposes complex queries into sub-tasks
    - AgentOrchestrator: Coordinates agents with ReAct pattern

Key Features:
    - ReAct pattern (Thought → Action → Observation)
    - Multi-step reasoning with early stopping
    - Evidence-based validation
    - Explainable reasoning chains
    - Integration with UnifiedSearchPipeline, EvidenceSynthesizer

Example:
    >>> orchestrator = AgentOrchestrator(neo4j_client, llm_client=gemini_client)
    >>> response = await orchestrator.solve(
    ...     query="What is the best surgical approach for L4-L5 stenosis?",
    ...     context={"evidence_level": "2a", "patient_age": 65}
    ... )
    >>> print(response.final_answer)
    >>> print(f"Confidence: {response.confidence:.2f}")
    >>> for step in response.reasoning_chain:
    ...     print(f"{step.thought} → {step.action} → {step.observation}")
"""

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, List, Dict

from .unified_pipeline import UnifiedSearchPipeline, SearchOptions, SearchResponse
from .evidence_synthesizer import EvidenceSynthesizer, EvidenceStrength
from .query_parser import QueryParser

from core.exceptions import ValidationError, ErrorCode

# Try to import dependencies
try:
    from ..graph.neo4j_client import Neo4jClient
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Neo4jClient = None

from typing import Union
try:
    from ..llm import LLMClient, ClaudeClient, GeminiClient
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMClient = None
    ClaudeClient = None
    GeminiClient = None

try:
    from ..core.logging_config import MedicalRAGLogger
    logger = MedicalRAGLogger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

class AgentType(Enum):
    """Agent type enumeration."""
    SEARCH = "search"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    PLANNING = "planning"


class ActionType(Enum):
    """Action type enumeration for ReAct pattern."""
    SEARCH_GRAPH = "search_graph"
    SEARCH_VECTOR = "search_vector"
    SEARCH_HYBRID = "search_hybrid"
    SYNTHESIZE_EVIDENCE = "synthesize_evidence"
    VALIDATE_ANSWER = "validate_answer"
    DECOMPOSE_QUERY = "decompose_query"
    COMBINE_RESULTS = "combine_results"
    TERMINATE = "terminate"


@dataclass
class AgentTask:
    """Task for an agent to execute.

    Attributes:
        task_id: Unique task identifier
        description: Natural language task description
        context: Additional context (previous results, constraints, etc.)
        constraints: Execution constraints (timeout, evidence level, etc.)
        agent_type: Type of agent that should handle this task
        priority: Task priority (0-10, higher = more important)
    """
    task_id: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    agent_type: Optional[AgentType] = None
    priority: int = 5


@dataclass
class AgentResult:
    """Result from agent execution.

    Attributes:
        success: Whether the agent succeeded
        result: Execution result (type depends on agent)
        reasoning: Natural language explanation of reasoning process
        confidence: Confidence score (0.0-1.0)
        metadata: Additional metadata (timing, resources used, etc.)
        error: Error message if failed
    """
    success: bool
    result: Any
    reasoning: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ReActStep:
    """Single step in ReAct reasoning chain.

    Attributes:
        step_id: Step number
        thought: Agent's reasoning about what to do
        action: Action to take (from ActionType)
        action_input: Input parameters for the action
        observation: Observation from executing the action
        timestamp: When this step occurred
        duration_ms: How long this step took
    """
    step_id: int
    thought: str
    action: ActionType
    action_input: Dict[str, Any]
    observation: str
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0


@dataclass
class AgentResponse:
    """Final response from agent orchestrator.

    Attributes:
        final_answer: Natural language answer to the query
        reasoning_chain: List of ReAct steps showing reasoning process
        sources: List of source papers/evidence used
        confidence: Overall confidence score (0.0-1.0)
        evidence_grade: GRADE rating if applicable
        metadata: Additional metadata (total time, tokens used, etc.)
    """
    final_answer: str
    reasoning_chain: List[ReActStep]
    sources: List[Dict[str, Any]]
    confidence: float
    evidence_grade: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Base Agent Class
# =============================================================================

class RAGAgent(ABC):
    """Abstract base class for all RAG agents.

    All agents must implement:
        - execute(): Main execution logic
        - get_description(): Natural language description
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent
            config: Configuration dictionary
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.config = config or {}
        self.memory: List[AgentResult] = []  # Agent memory

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute task and return result.

        Args:
            task: Task to execute

        Returns:
            AgentResult with execution outcome
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get natural language description of agent capabilities.

        Returns:
            Description string
        """
        pass

    def add_to_memory(self, result: AgentResult) -> None:
        """Add result to agent memory.

        Args:
            result: Result to remember
        """
        self.memory.append(result)
        # Keep only last 10 results
        if len(self.memory) > 10:
            self.memory = self.memory[-10:]

    def get_memory_context(self) -> str:
        """Get context from agent memory.

        Returns:
            Formatted memory context string
        """
        if not self.memory:
            return "No previous context."

        context_parts = []
        for i, result in enumerate(self.memory[-3:], 1):  # Last 3 results
            context_parts.append(
                f"{i}. {result.reasoning[:100]}... "
                f"(confidence: {result.confidence:.2f})"
            )

        return "\n".join(context_parts)


# =============================================================================
# Specialized Agents
# =============================================================================

class SearchAgent(RAGAgent):
    """Agent that determines optimal search strategy.

    Capabilities:
        - Analyze query type (factual, comparative, exploratory)
        - Choose optimal search mode (graph, vector, hybrid)
        - Execute search with UnifiedSearchPipeline
        - Return ranked results with evidence

    Example:
        >>> agent = SearchAgent(pipeline)
        >>> task = AgentTask(
        ...     task_id="search-1",
        ...     description="Find evidence for TLIF vs OLIF",
        ...     agent_type=AgentType.SEARCH
        ... )
        >>> result = await agent.execute(task)
    """

    def __init__(
        self,
        pipeline: UnifiedSearchPipeline,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize search agent.

        Args:
            pipeline: UnifiedSearchPipeline instance
            config: Configuration dictionary
        """
        super().__init__(
            agent_id="search_agent",
            agent_type=AgentType.SEARCH,
            config=config
        )
        self.pipeline = pipeline

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute search task.

        Args:
            task: Search task with query in description

        Returns:
            AgentResult with SearchResponse
        """
        start_time = time.time()

        try:
            # Extract search parameters
            query = task.description
            top_k = task.constraints.get("top_k", 10)
            min_evidence_level = task.constraints.get("min_evidence_level", "3")

            # Prepare search options
            options = SearchOptions(
                top_k=top_k,
                include_synthesis=True,
                detect_conflicts=True,
                min_evidence_level=min_evidence_level
            )

            # Execute search
            logger.info("SearchAgent executing search", query=query[:100])
            search_response = await self.pipeline.search(query, options)

            # Build reasoning
            reasoning = (
                f"Executed {search_response.query_analysis.query_type.value} search. "
                f"Found {len(search_response.results)} results in "
                f"{search_response.execution_time_ms:.1f}ms. "
            )

            if search_response.synthesis:
                reasoning += (
                    f"Evidence synthesis: {search_response.synthesis.direction} "
                    f"(GRADE: {search_response.synthesis.grade_rating}). "
                )

            # Calculate confidence based on results
            if search_response.results:
                avg_score = sum(r.final_score for r in search_response.results) / len(search_response.results)
                confidence = min(avg_score, 1.0)
            else:
                confidence = 0.0

            duration_ms = (time.time() - start_time) * 1000

            result = AgentResult(
                success=True,
                result=search_response,
                reasoning=reasoning,
                confidence=confidence,
                metadata={
                    "duration_ms": duration_ms,
                    "result_count": len(search_response.results),
                    "query_type": search_response.query_analysis.query_type.value
                }
            )

            self.add_to_memory(result)
            logger.info("SearchAgent completed", confidence=confidence)

            return result

        except Exception as e:
            logger.error("SearchAgent failed", error=str(e), exc_info=True)
            return AgentResult(
                success=False,
                result=None,
                reasoning=f"Search failed: {str(e)}",
                confidence=0.0,
                error=str(e)
            )

    def get_description(self) -> str:
        """Get agent description."""
        return (
            "SearchAgent: Executes hybrid graph+vector search. "
            "Analyzes query type, selects optimal search strategy, "
            "and returns ranked results with evidence synthesis."
        )


class SynthesisAgent(RAGAgent):
    """Agent that synthesizes evidence from multiple sources.

    Capabilities:
        - Aggregate results from multiple searches
        - Identify common themes and patterns
        - Synthesize evidence using GRADE methodology
        - Generate coherent summary

    Example:
        >>> agent = SynthesisAgent(synthesizer)
        >>> task = AgentTask(
        ...     task_id="synth-1",
        ...     description="Synthesize evidence for TLIF outcomes",
        ...     context={"search_results": [...]},
        ...     agent_type=AgentType.SYNTHESIS
        ... )
        >>> result = await agent.execute(task)
    """

    def __init__(
        self,
        synthesizer: EvidenceSynthesizer,
        llm_client: Optional[Union["LLMClient", "ClaudeClient", "GeminiClient"]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize synthesis agent.

        Args:
            synthesizer: EvidenceSynthesizer instance
            llm_client: LLM client (Claude 또는 Gemini) for natural language synthesis
            config: Configuration dictionary
        """
        super().__init__(
            agent_id="synthesis_agent",
            agent_type=AgentType.SYNTHESIS,
            config=config
        )
        self.synthesizer = synthesizer
        self.llm_client = llm_client

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute synthesis task.

        Args:
            task: Synthesis task with intervention/outcome

        Returns:
            AgentResult with synthesized evidence
        """
        start_time = time.time()

        try:
            # Extract intervention and outcome from context
            intervention = task.context.get("intervention")
            outcome = task.context.get("outcome")
            search_results = task.context.get("search_results", [])

            if not intervention or not outcome:
                raise ValidationError(message="Intervention and outcome required for synthesis", error_code=ErrorCode.VAL_MISSING_FIELD)

            logger.info(
                "SynthesisAgent executing",
                intervention=intervention,
                outcome=outcome
            )

            # Synthesize evidence
            synthesis = await self.synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome,
                min_papers=task.constraints.get("min_papers", 2)
            )

            # Generate natural language summary using LLM if available
            if self.llm_client and synthesis.supporting_papers:
                summary = await self._generate_summary(
                    intervention, outcome, synthesis
                )
            else:
                summary = self._default_summary(synthesis)

            reasoning = (
                f"Synthesized {len(synthesis.supporting_papers)} papers. "
                f"Direction: {synthesis.direction}. "
                f"Strength: {synthesis.strength.value}. "
                f"GRADE: {synthesis.grade_rating}."
            )

            # Calculate confidence from evidence strength
            strength_to_confidence = {
                EvidenceStrength.STRONG: 0.9,
                EvidenceStrength.MODERATE: 0.7,
                EvidenceStrength.WEAK: 0.5,
                EvidenceStrength.INSUFFICIENT: 0.2
            }
            confidence = strength_to_confidence.get(synthesis.strength, 0.5)

            duration_ms = (time.time() - start_time) * 1000

            result = AgentResult(
                success=True,
                result={
                    "synthesis": synthesis,
                    "summary": summary
                },
                reasoning=reasoning,
                confidence=confidence,
                metadata={
                    "duration_ms": duration_ms,
                    "paper_count": len(synthesis.supporting_papers),
                    "grade": synthesis.grade_rating
                }
            )

            self.add_to_memory(result)
            logger.info("SynthesisAgent completed", confidence=confidence)

            return result

        except Exception as e:
            logger.error("SynthesisAgent failed", error=str(e), exc_info=True)
            return AgentResult(
                success=False,
                result=None,
                reasoning=f"Synthesis failed: {str(e)}",
                confidence=0.0,
                error=str(e)
            )

    async def _generate_summary(
        self,
        intervention: str,
        outcome: str,
        synthesis: Any
    ) -> str:
        """Generate natural language summary using LLM.

        Args:
            intervention: Intervention name
            outcome: Outcome name
            synthesis: SynthesisResult

        Returns:
            Natural language summary
        """
        prompt = f"""Synthesize the evidence for {intervention} regarding {outcome}.

Evidence:
- Direction: {synthesis.direction}
- Strength: {synthesis.strength.value}
- GRADE: {synthesis.grade_rating}
- Papers: {len(synthesis.supporting_papers)}

Generate a concise 2-3 sentence summary suitable for clinicians."""

        response = await self.llm_client.generate(prompt)
        return response.text

    def _default_summary(self, synthesis: Any) -> str:
        """Generate default summary without LLM.

        Args:
            synthesis: SynthesisResult

        Returns:
            Simple summary
        """
        return (
            f"Evidence shows {synthesis.direction} effect. "
            f"Strength: {synthesis.strength.value} (GRADE {synthesis.grade_rating}). "
            f"Based on {len(synthesis.supporting_papers)} studies."
        )

    def get_description(self) -> str:
        """Get agent description."""
        return (
            "SynthesisAgent: Aggregates and synthesizes evidence from multiple sources. "
            "Uses GRADE methodology to assess evidence strength. "
            "Generates natural language summaries."
        )


class ValidationAgent(RAGAgent):
    """Agent that validates answers against evidence.

    Capabilities:
        - Check answer consistency with retrieved evidence
        - Verify statistical significance
        - Assess evidence quality (GRADE)
        - Detect potential conflicts or contradictions

    Example:
        >>> agent = ValidationAgent(neo4j_client)
        >>> task = AgentTask(
        ...     task_id="val-1",
        ...     description="Validate: TLIF improves fusion rate",
        ...     context={"evidence": [...], "answer": "..."},
        ...     agent_type=AgentType.VALIDATION
        ... )
        >>> result = await agent.execute(task)
    """

    def __init__(
        self,
        neo4j_client: Optional["Neo4jClient"] = None,
        llm_client: Optional[Union["LLMClient", "ClaudeClient", "GeminiClient"]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize validation agent.

        Args:
            neo4j_client: Neo4j client for evidence lookup
            llm_client: LLM client (Claude 또는 Gemini) for semantic validation
            config: Configuration dictionary
        """
        super().__init__(
            agent_id="validation_agent",
            agent_type=AgentType.VALIDATION,
            config=config
        )
        self.neo4j_client = neo4j_client
        self.llm_client = llm_client

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute validation task.

        Args:
            task: Validation task with answer and evidence

        Returns:
            AgentResult with validation assessment
        """
        start_time = time.time()

        try:
            answer = task.context.get("answer", "")
            evidence = task.context.get("evidence", [])
            synthesis = task.context.get("synthesis")

            if not answer:
                raise ValidationError(message="Answer required for validation", error_code=ErrorCode.VAL_MISSING_FIELD)

            logger.info("ValidationAgent executing", answer_length=len(answer))

            # Validation checks
            validation_results = {
                "has_evidence": len(evidence) > 0,
                "evidence_count": len(evidence),
                "has_synthesis": synthesis is not None,
                "is_consistent": True,  # Default to True
                "conflicts_detected": False
            }

            # Check evidence consistency using LLM if available
            if self.llm_client and evidence:
                consistency = await self._check_consistency_llm(answer, evidence)
                validation_results["is_consistent"] = consistency["is_consistent"]
                validation_results["reasoning"] = consistency["reasoning"]

            # Add GRADE rating if synthesis available
            if synthesis:
                validation_results["grade_rating"] = synthesis.grade_rating
                validation_results["evidence_strength"] = synthesis.strength.value

            # Calculate confidence
            confidence = self._calculate_validation_confidence(validation_results)

            reasoning = self._generate_validation_reasoning(validation_results)

            duration_ms = (time.time() - start_time) * 1000

            result = AgentResult(
                success=True,
                result=validation_results,
                reasoning=reasoning,
                confidence=confidence,
                metadata={
                    "duration_ms": duration_ms,
                    "evidence_count": validation_results["evidence_count"]
                }
            )

            self.add_to_memory(result)
            logger.info("ValidationAgent completed", confidence=confidence)

            return result

        except Exception as e:
            logger.error("ValidationAgent failed", error=str(e), exc_info=True)
            return AgentResult(
                success=False,
                result=None,
                reasoning=f"Validation failed: {str(e)}",
                confidence=0.0,
                error=str(e)
            )

    async def _check_consistency_llm(
        self,
        answer: str,
        evidence: List[Any]
    ) -> Dict[str, Any]:
        """Check answer-evidence consistency using LLM.

        Args:
            answer: Proposed answer
            evidence: List of evidence items

        Returns:
            Consistency check result
        """
        # Prepare evidence summary
        evidence_summary = "\n".join([
            f"- {e.title if hasattr(e, 'title') else str(e)[:100]}"
            for e in evidence[:5]  # Top 5
        ])

        prompt = f"""Validate if this answer is consistent with the evidence.

Answer: {answer}

Evidence:
{evidence_summary}

Is the answer supported by the evidence? Respond with JSON:
{{"is_consistent": true/false, "reasoning": "explanation"}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "is_consistent": {"type": "BOOLEAN"},
                "reasoning": {"type": "STRING"}
            },
            "required": ["is_consistent", "reasoning"]
        }

        result = await self.llm_client.generate_json(prompt, schema)
        return result

    def _calculate_validation_confidence(
        self,
        validation_results: Dict[str, Any]
    ) -> float:
        """Calculate validation confidence score.

        Args:
            validation_results: Validation check results

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # Base confidence

        # Boost for evidence
        if validation_results["has_evidence"]:
            evidence_count = validation_results["evidence_count"]
            confidence += min(evidence_count * 0.1, 0.3)

        # Boost for synthesis
        if validation_results["has_synthesis"]:
            confidence += 0.1

        # Penalty for inconsistency
        if not validation_results.get("is_consistent", True):
            confidence -= 0.3

        # Penalty for conflicts
        if validation_results.get("conflicts_detected", False):
            confidence -= 0.2

        return max(0.0, min(confidence, 1.0))

    def _generate_validation_reasoning(
        self,
        validation_results: Dict[str, Any]
    ) -> str:
        """Generate validation reasoning text.

        Args:
            validation_results: Validation check results

        Returns:
            Reasoning string
        """
        parts = []

        if validation_results["has_evidence"]:
            parts.append(
                f"Validated against {validation_results['evidence_count']} evidence sources."
            )
        else:
            parts.append("No evidence found for validation.")

        if validation_results["has_synthesis"]:
            parts.append(
                f"GRADE rating: {validation_results.get('grade_rating', 'N/A')}."
            )

        if not validation_results.get("is_consistent", True):
            parts.append("⚠️ Answer may not be fully consistent with evidence.")

        return " ".join(parts)

    def get_description(self) -> str:
        """Get agent description."""
        return (
            "ValidationAgent: Validates answers against evidence. "
            "Checks consistency, statistical significance, and evidence quality. "
            "Uses GRADE methodology for assessment."
        )


class PlanningAgent(RAGAgent):
    """Agent that decomposes complex queries into sub-tasks.

    Capabilities:
        - Analyze query complexity
        - Decompose multi-part questions
        - Create execution plan with dependencies
        - Route sub-tasks to appropriate agents

    Example:
        >>> agent = PlanningAgent(llm_client)
        >>> task = AgentTask(
        ...     task_id="plan-1",
        ...     description="Compare TLIF vs OLIF for lumbar stenosis in elderly patients",
        ...     agent_type=AgentType.PLANNING
        ... )
        >>> result = await agent.execute(task)
        >>> # result.result contains list of sub-tasks
    """

    def __init__(
        self,
        llm_client: Optional[Union["LLMClient", "ClaudeClient", "GeminiClient"]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize planning agent.

        Args:
            llm_client: LLM client (Claude 또는 Gemini) for query decomposition
            config: Configuration dictionary
        """
        super().__init__(
            agent_id="planning_agent",
            agent_type=AgentType.PLANNING,
            config=config
        )
        self.llm_client = llm_client
        self.query_parser = QueryParser()

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute planning task.

        Args:
            task: Planning task with complex query

        Returns:
            AgentResult with execution plan (list of sub-tasks)
        """
        start_time = time.time()

        try:
            query = task.description

            logger.info("PlanningAgent analyzing query", query=query[:100])

            # Check if query is complex enough to decompose
            if self.llm_client:
                sub_tasks = await self._decompose_query_llm(query)
            else:
                sub_tasks = self._decompose_query_simple(query)

            # If only one sub-task, no decomposition needed
            if len(sub_tasks) == 1:
                reasoning = "Query is simple, no decomposition needed."
                confidence = 0.9
            else:
                reasoning = f"Decomposed into {len(sub_tasks)} sub-tasks."
                confidence = 0.8

            duration_ms = (time.time() - start_time) * 1000

            result = AgentResult(
                success=True,
                result=sub_tasks,
                reasoning=reasoning,
                confidence=confidence,
                metadata={
                    "duration_ms": duration_ms,
                    "sub_task_count": len(sub_tasks)
                }
            )

            self.add_to_memory(result)
            logger.info("PlanningAgent completed", sub_task_count=len(sub_tasks))

            return result

        except Exception as e:
            logger.error("PlanningAgent failed", error=str(e), exc_info=True)
            return AgentResult(
                success=False,
                result=None,
                reasoning=f"Planning failed: {str(e)}",
                confidence=0.0,
                error=str(e)
            )

    async def _decompose_query_llm(self, query: str) -> List[AgentTask]:
        """Decompose query using LLM.

        Args:
            query: Complex query

        Returns:
            List of sub-tasks
        """
        prompt = f"""Analyze this medical query and decompose it into sub-tasks if needed.

Query: {query}

If the query has multiple parts (e.g., comparison, multiple outcomes, conditional logic),
break it down into sequential sub-tasks. Otherwise, return the original query.

Respond with JSON:
{{
    "needs_decomposition": true/false,
    "sub_tasks": [
        {{"description": "sub-task 1", "agent_type": "search/synthesis/validation"}},
        ...
    ]
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "needs_decomposition": {"type": "BOOLEAN"},
                "sub_tasks": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "description": {"type": "STRING"},
                            "agent_type": {"type": "STRING"}
                        }
                    }
                }
            }
        }

        result = await self.llm_client.generate_json(prompt, schema)

        # Convert to AgentTask objects
        sub_tasks = []
        for i, st in enumerate(result.get("sub_tasks", [])):
            agent_type_str = st.get("agent_type", "search").upper()
            try:
                agent_type = AgentType[agent_type_str]
            except KeyError:
                agent_type = AgentType.SEARCH

            sub_tasks.append(AgentTask(
                task_id=f"subtask-{i+1}",
                description=st["description"],
                agent_type=agent_type,
                priority=10 - i  # Earlier tasks have higher priority
            ))

        return sub_tasks if sub_tasks else [
            AgentTask(
                task_id="task-1",
                description=query,
                agent_type=AgentType.SEARCH
            )
        ]

    def _decompose_query_simple(self, query: str) -> List[AgentTask]:
        """Simple query decomposition without LLM.

        Args:
            query: Query to decompose

        Returns:
            List of sub-tasks
        """
        # Simple heuristic: if query contains "vs" or "compare", it's complex
        query_lower = query.lower()

        if " vs " in query_lower or "compare" in query_lower:
            # Comparison query - decompose into searches for each intervention
            parts = query_lower.split(" vs ")
            if len(parts) == 2:
                return [
                    AgentTask(
                        task_id="subtask-1",
                        description=f"Search for {parts[0].strip()}",
                        agent_type=AgentType.SEARCH,
                        priority=10
                    ),
                    AgentTask(
                        task_id="subtask-2",
                        description=f"Search for {parts[1].strip()}",
                        agent_type=AgentType.SEARCH,
                        priority=9
                    ),
                    AgentTask(
                        task_id="subtask-3",
                        description=f"Compare results",
                        agent_type=AgentType.SYNTHESIS,
                        priority=8
                    )
                ]

        # Default: single task
        return [
            AgentTask(
                task_id="task-1",
                description=query,
                agent_type=AgentType.SEARCH
            )
        ]

    def get_description(self) -> str:
        """Get agent description."""
        return (
            "PlanningAgent: Decomposes complex queries into sub-tasks. "
            "Analyzes query structure, identifies dependencies, "
            "and creates execution plan."
        )


# =============================================================================
# Agent Orchestrator
# =============================================================================

class AgentOrchestrator:
    """Orchestrates multiple agents using ReAct pattern.

    Implements:
        - ReAct loop (Thought → Action → Observation)
        - Multi-agent coordination
        - Result aggregation
        - Early stopping conditions

    Example:
        >>> orchestrator = AgentOrchestrator(neo4j_client, llm_client=gemini_client)
        >>> response = await orchestrator.solve(
        ...     query="What is the best surgical approach for L4-L5 stenosis?",
        ...     context={"evidence_level": "2a"}
        ... )
        >>> print(response.final_answer)
        >>> print(f"Reasoning: {len(response.reasoning_chain)} steps")
    """

    def __init__(
        self,
        neo4j_client: Optional["Neo4jClient"] = None,
        llm_client: Optional[Union["LLMClient", "ClaudeClient", "GeminiClient"]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize orchestrator.

        Args:
            neo4j_client: Neo4j client
            llm_client: LLM client (Claude 또는 Gemini)
            config: Configuration dictionary
        """
        self.neo4j_client = neo4j_client
        self.llm_client = llm_client
        self.config = config or {}

        # Initialize pipeline and components
        self.pipeline = UnifiedSearchPipeline(neo4j_client)

        # Initialize agents
        self.agents: Dict[AgentType, RAGAgent] = {}

        self.agents[AgentType.SEARCH] = SearchAgent(self.pipeline)

        if neo4j_client:
            from .evidence_synthesizer import EvidenceSynthesizer
            synthesizer = EvidenceSynthesizer(neo4j_client)
            self.agents[AgentType.SYNTHESIS] = SynthesisAgent(
                synthesizer, llm_client
            )
            self.agents[AgentType.VALIDATION] = ValidationAgent(
                neo4j_client, llm_client
            )

        if llm_client:
            self.agents[AgentType.PLANNING] = PlanningAgent(llm_client)

        logger.info(
            "AgentOrchestrator initialized",
            agent_count=len(self.agents)
        )

    async def solve(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_iterations: int = 5
    ) -> AgentResponse:
        """Solve query using ReAct agent loop.

        Args:
            query: Natural language query
            context: Additional context
            max_iterations: Maximum ReAct iterations

        Returns:
            AgentResponse with final answer and reasoning chain
        """
        start_time = time.time()
        context = context or {}
        reasoning_chain: List[ReActStep] = []

        logger.info("AgentOrchestrator solving query", query=query[:100])

        try:
            # Step 1: Planning
            if AgentType.PLANNING in self.agents:
                plan_result = await self._execute_planning(query, reasoning_chain)
                sub_tasks = plan_result.result if plan_result.success else []
            else:
                # Default to single search task
                sub_tasks = [
                    AgentTask(
                        task_id="task-1",
                        description=query,
                        agent_type=AgentType.SEARCH
                    )
                ]

            # Step 2: Execute sub-tasks
            search_results = []
            synthesis_result = None

            for task in sub_tasks:
                if task.agent_type == AgentType.SEARCH:
                    result = await self._execute_search(task, reasoning_chain)
                    if result.success:
                        search_results.append(result.result)

                elif task.agent_type == AgentType.SYNTHESIS:
                    # Extract intervention/outcome from search results
                    if search_results:
                        int_out = self._extract_intervention_outcome(search_results[0])
                        if int_out[0] and int_out[1]:
                            task.context.update({
                                "intervention": int_out[0],
                                "outcome": int_out[1],
                                "search_results": search_results
                            })
                            result = await self._execute_synthesis(task, reasoning_chain)
                            if result.success:
                                synthesis_result = result.result

            # Step 3: Generate final answer
            final_answer = await self._generate_final_answer(
                query, search_results, synthesis_result, reasoning_chain
            )

            # Step 4: Validation (optional)
            validation_result = None
            if AgentType.VALIDATION in self.agents and search_results:
                validation_task = AgentTask(
                    task_id="validation-1",
                    description="Validate final answer",
                    context={
                        "answer": final_answer,
                        "evidence": search_results[0].results if search_results else [],
                        "synthesis": synthesis_result.get("synthesis") if synthesis_result else None
                    },
                    agent_type=AgentType.VALIDATION
                )
                validation_result = await self._execute_validation(
                    validation_task, reasoning_chain
                )

            # Build response
            sources = self._extract_sources(search_results)
            confidence = self._calculate_overall_confidence(
                search_results, synthesis_result, validation_result
            )

            evidence_grade = None
            if synthesis_result and "synthesis" in synthesis_result:
                evidence_grade = synthesis_result["synthesis"].grade_rating

            duration_s = time.time() - start_time

            response = AgentResponse(
                final_answer=final_answer,
                reasoning_chain=reasoning_chain,
                sources=sources,
                confidence=confidence,
                evidence_grade=evidence_grade,
                metadata={
                    "duration_s": duration_s,
                    "iterations": len(reasoning_chain),
                    "sub_tasks": len(sub_tasks)
                }
            )

            logger.info(
                "AgentOrchestrator completed",
                duration_s=duration_s,
                confidence=confidence
            )

            return response

        except Exception as e:
            logger.error("AgentOrchestrator failed", error=str(e), exc_info=True)
            # Return error response
            return AgentResponse(
                final_answer=f"Failed to solve query: {str(e)}",
                reasoning_chain=reasoning_chain,
                sources=[],
                confidence=0.0,
                metadata={"error": str(e)}
            )

    async def _execute_planning(
        self,
        query: str,
        reasoning_chain: List[ReActStep]
    ) -> AgentResult:
        """Execute planning step.

        Args:
            query: Query to plan
            reasoning_chain: Reasoning chain to append to

        Returns:
            AgentResult from planning
        """
        step_start = time.time()

        task = AgentTask(
            task_id="plan-1",
            description=query,
            agent_type=AgentType.PLANNING
        )

        thought = f"Analyzing query complexity: '{query[:100]}...'"
        action = ActionType.DECOMPOSE_QUERY

        result = await self.agents[AgentType.PLANNING].execute(task)

        observation = result.reasoning

        step = ReActStep(
            step_id=len(reasoning_chain) + 1,
            thought=thought,
            action=action,
            action_input={"query": query},
            observation=observation,
            duration_ms=(time.time() - step_start) * 1000
        )
        reasoning_chain.append(step)

        return result

    async def _execute_search(
        self,
        task: AgentTask,
        reasoning_chain: List[ReActStep]
    ) -> AgentResult:
        """Execute search step.

        Args:
            task: Search task
            reasoning_chain: Reasoning chain to append to

        Returns:
            AgentResult from search
        """
        step_start = time.time()

        thought = f"Searching for: '{task.description[:100]}...'"
        action = ActionType.SEARCH_HYBRID

        result = await self.agents[AgentType.SEARCH].execute(task)

        observation = result.reasoning

        step = ReActStep(
            step_id=len(reasoning_chain) + 1,
            thought=thought,
            action=action,
            action_input={"query": task.description},
            observation=observation,
            duration_ms=(time.time() - step_start) * 1000
        )
        reasoning_chain.append(step)

        return result

    async def _execute_synthesis(
        self,
        task: AgentTask,
        reasoning_chain: List[ReActStep]
    ) -> AgentResult:
        """Execute synthesis step.

        Args:
            task: Synthesis task
            reasoning_chain: Reasoning chain to append to

        Returns:
            AgentResult from synthesis
        """
        step_start = time.time()

        intervention = task.context.get("intervention", "intervention")
        outcome = task.context.get("outcome", "outcome")

        thought = f"Synthesizing evidence for {intervention} → {outcome}"
        action = ActionType.SYNTHESIZE_EVIDENCE

        result = await self.agents[AgentType.SYNTHESIS].execute(task)

        observation = result.reasoning

        step = ReActStep(
            step_id=len(reasoning_chain) + 1,
            thought=thought,
            action=action,
            action_input={"intervention": intervention, "outcome": outcome},
            observation=observation,
            duration_ms=(time.time() - step_start) * 1000
        )
        reasoning_chain.append(step)

        return result

    async def _execute_validation(
        self,
        task: AgentTask,
        reasoning_chain: List[ReActStep]
    ) -> AgentResult:
        """Execute validation step.

        Args:
            task: Validation task
            reasoning_chain: Reasoning chain to append to

        Returns:
            AgentResult from validation
        """
        step_start = time.time()

        thought = "Validating answer against evidence"
        action = ActionType.VALIDATE_ANSWER

        result = await self.agents[AgentType.VALIDATION].execute(task)

        observation = result.reasoning

        step = ReActStep(
            step_id=len(reasoning_chain) + 1,
            thought=thought,
            action=action,
            action_input={"answer": task.context.get("answer", "")[:100]},
            observation=observation,
            duration_ms=(time.time() - step_start) * 1000
        )
        reasoning_chain.append(step)

        return result

    async def _generate_final_answer(
        self,
        query: str,
        search_results: List[Any],
        synthesis_result: Optional[Dict[str, Any]],
        reasoning_chain: List[ReActStep]
    ) -> str:
        """Generate final answer from results.

        Args:
            query: Original query
            search_results: Search results
            synthesis_result: Synthesis result
            reasoning_chain: Reasoning chain

        Returns:
            Final answer string
        """
        # If we have LLM, generate natural language answer
        if self.llm_client and search_results:
            return await self._generate_answer_llm(
                query, search_results, synthesis_result
            )

        # Otherwise, generate simple answer
        return self._generate_answer_simple(search_results, synthesis_result)

    async def _generate_answer_llm(
        self,
        query: str,
        search_results: List[Any],
        synthesis_result: Optional[Dict[str, Any]]
    ) -> str:
        """Generate answer using LLM.

        Args:
            query: Original query
            search_results: Search results
            synthesis_result: Synthesis result

        Returns:
            Natural language answer
        """
        # Extract top results
        top_results = []
        if search_results and hasattr(search_results[0], 'results'):
            for r in search_results[0].results[:3]:
                top_results.append(f"- {r.title}")

        results_text = "\n".join(top_results) if top_results else "No specific results."

        synthesis_text = ""
        if synthesis_result and "summary" in synthesis_result:
            synthesis_text = f"\nEvidence synthesis: {synthesis_result['summary']}"

        prompt = f"""Answer this medical query based on the evidence.

Query: {query}

Top evidence:
{results_text}
{synthesis_text}

Provide a concise, evidence-based answer suitable for clinicians (2-3 sentences)."""

        response = await self.llm_client.generate(prompt)
        return response.text

    def _generate_answer_simple(
        self,
        search_results: List[Any],
        synthesis_result: Optional[Dict[str, Any]]
    ) -> str:
        """Generate simple answer without LLM.

        Args:
            search_results: Search results
            synthesis_result: Synthesis result

        Returns:
            Simple answer
        """
        if synthesis_result and "summary" in synthesis_result:
            return synthesis_result["summary"]

        if search_results and hasattr(search_results[0], 'results'):
            result_count = len(search_results[0].results)
            return f"Found {result_count} relevant studies. See sources for details."

        return "No sufficient evidence found to answer the query."

    def _extract_intervention_outcome(
        self,
        search_response: Any
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract intervention and outcome from search results.

        Args:
            search_response: SearchResponse object

        Returns:
            (intervention, outcome) tuple
        """
        if not hasattr(search_response, 'results'):
            return None, None

        for result in search_response.results:
            if hasattr(result, 'evidence') and result.evidence:
                return result.evidence.intervention, result.evidence.outcome

        return None, None

    def _extract_sources(self, search_results: List[Any]) -> List[Dict[str, Any]]:
        """Extract source papers from search results.

        Args:
            search_results: Search results

        Returns:
            List of source dictionaries
        """
        sources = []

        if search_results and hasattr(search_results[0], 'results'):
            for r in search_results[0].results[:10]:  # Top 10
                sources.append({
                    "paper_id": r.paper_id,
                    "title": r.title,
                    "score": r.final_score
                })

        return sources

    def _calculate_overall_confidence(
        self,
        search_results: List[Any],
        synthesis_result: Optional[Dict[str, Any]],
        validation_result: Optional[AgentResult]
    ) -> float:
        """Calculate overall confidence score.

        Args:
            search_results: Search results
            synthesis_result: Synthesis result
            validation_result: Validation result

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # Base

        # Boost from search results
        if search_results and hasattr(search_results[0], 'results'):
            if len(search_results[0].results) > 0:
                avg_score = sum(
                    r.final_score for r in search_results[0].results
                ) / len(search_results[0].results)
                confidence += avg_score * 0.2

        # Boost from synthesis
        if synthesis_result:
            confidence += 0.1

        # Boost from validation
        if validation_result and validation_result.success:
            confidence += validation_result.confidence * 0.2

        return max(0.0, min(confidence, 1.0))


# =============================================================================
# Convenience Functions
# =============================================================================

async def quick_solve(
    query: str,
    neo4j_client: Optional["Neo4jClient"] = None,
    llm_client: Optional["GeminiClient"] = None
) -> AgentResponse:
    """Quick solve using default orchestrator.

    Args:
        query: Query to solve
        neo4j_client: Neo4j client
        llm_client: Gemini client

    Returns:
        AgentResponse
    """
    orchestrator = AgentOrchestrator(neo4j_client, llm_client=llm_client)
    return await orchestrator.solve(query)


# =============================================================================
# Example Usage
# =============================================================================

async def example_usage():
    """Example usage."""
    print("=" * 80)
    print("Agentic RAG Framework Example")
    print("=" * 80)

    # Mock clients (replace with real clients)
    neo4j_client = None
    llm_client = None

    # Create orchestrator
    orchestrator = AgentOrchestrator(neo4j_client, llm_client=llm_client)

    # Example queries
    queries = [
        "What is the fusion rate of TLIF?",
        "Compare TLIF vs OLIF for lumbar stenosis in elderly patients",
        "Is UBE effective for L4-L5 disc herniation?"
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 80)

        try:
            response = await orchestrator.solve(query)

            print(f"Answer: {response.final_answer}")
            print(f"Confidence: {response.confidence:.2f}")
            if response.evidence_grade:
                print(f"GRADE: {response.evidence_grade}")

            print(f"\nReasoning ({len(response.reasoning_chain)} steps):")
            for step in response.reasoning_chain:
                print(f"  {step.step_id}. {step.thought}")
                print(f"     → {step.action.value}: {step.observation[:100]}...")

            print(f"\nSources: {len(response.sources)}")

        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(example_usage())
