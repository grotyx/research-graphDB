# Agentic RAG Framework

## Overview

The Agentic RAG framework implements a **ReAct-based multi-agent system** for answering complex medical queries with explainability and evidence-based validation.

### Key Features

- **Multi-Agent Architecture**: Specialized agents for search, synthesis, validation, and planning
- **ReAct Pattern**: Thought → Action → Observation reasoning loop
- **Explainable AI**: Complete reasoning chain with step-by-step explanations
- **Evidence-Based**: GRADE methodology integration for evidence quality assessment
- **Flexible Orchestration**: Dynamic task routing and decomposition
- **Memory-Enabled**: Agents maintain context across executions

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  AgentOrchestrator                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              ReAct Loop (max 5 iterations)            │  │
│  │  Thought → Action → Observation → [Repeat/Terminate] │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                 │
│     ┌────────────────────┼────────────────────┐            │
│     ▼                    ▼                    ▼            │
│ ┌──────────┐      ┌──────────┐      ┌──────────┐          │
│ │ Planning │      │  Search  │      │Synthesis │          │
│ │  Agent   │      │  Agent   │      │  Agent   │          │
│ └──────────┘      └──────────┘      └──────────┘          │
│                                              ▼              │
│                                      ┌──────────┐          │
│                                      │Validation│          │
│                                      │  Agent   │          │
│                                      └──────────┘          │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Base Agent (RAGAgent)

Abstract base class for all agents.

**Key Methods:**
- `execute(task: AgentTask) -> AgentResult`: Main execution logic
- `get_description() -> str`: Agent capability description
- `add_to_memory(result: AgentResult)`: Memory management
- `get_memory_context() -> str`: Retrieve memory context

**Features:**
- Agent memory (last 10 results)
- Configuration support
- Type-safe agent identification

### 2. SearchAgent

Determines optimal search strategy and executes hybrid search.

**Capabilities:**
- Query type classification (factual, comparative, exploratory)
- Hybrid graph + vector search execution
- Evidence synthesis integration
- Ranked result generation

**Example:**
```python
from src.solver.agentic_rag import SearchAgent, AgentTask

agent = SearchAgent(pipeline=unified_pipeline)

task = AgentTask(
    task_id="search-1",
    description="What is the fusion rate of TLIF?",
    agent_type=AgentType.SEARCH,
    constraints={"top_k": 10, "min_evidence_level": "2a"}
)

result = await agent.execute(task)
print(f"Found {len(result.result.results)} results")
print(f"Confidence: {result.confidence:.2f}")
```

### 3. SynthesisAgent

Aggregates and synthesizes evidence from multiple sources.

**Capabilities:**
- GRADE methodology application
- Multi-paper evidence aggregation
- Natural language summary generation (with LLM)
- Evidence strength assessment

**Example:**
```python
from src.solver.agentic_rag import SynthesisAgent, AgentTask

agent = SynthesisAgent(
    synthesizer=evidence_synthesizer,
    llm_client=gemini_client
)

task = AgentTask(
    task_id="synth-1",
    description="Synthesize TLIF evidence",
    context={
        "intervention": "TLIF",
        "outcome": "Fusion rate",
        "search_results": [...]
    },
    agent_type=AgentType.SYNTHESIS
)

result = await agent.execute(task)
print(result.result["summary"])  # Natural language summary
print(f"GRADE: {result.result['synthesis'].grade_rating}")
```

### 4. ValidationAgent

Validates answers against retrieved evidence.

**Capabilities:**
- Answer-evidence consistency checking (with LLM)
- Statistical significance verification
- GRADE rating validation
- Conflict detection

**Example:**
```python
from src.solver.agentic_rag import ValidationAgent, AgentTask

agent = ValidationAgent(
    neo4j_client=neo4j_client,
    llm_client=gemini_client
)

task = AgentTask(
    task_id="val-1",
    description="Validate answer",
    context={
        "answer": "TLIF improves fusion rates by 15%",
        "evidence": search_results,
        "synthesis": synthesis_result
    },
    agent_type=AgentType.VALIDATION
)

result = await agent.execute(task)
print(f"Consistent: {result.result['is_consistent']}")
print(f"Confidence: {result.confidence:.2f}")
```

### 5. PlanningAgent

Decomposes complex queries into executable sub-tasks.

**Capabilities:**
- Query complexity analysis
- Multi-part question decomposition
- Execution plan creation with dependencies
- Agent routing decisions

**Example:**
```python
from src.solver.agentic_rag import PlanningAgent, AgentTask

agent = PlanningAgent(llm_client=gemini_client)

task = AgentTask(
    task_id="plan-1",
    description="Compare TLIF vs OLIF for lumbar stenosis in elderly",
    agent_type=AgentType.PLANNING
)

result = await agent.execute(task)
for i, subtask in enumerate(result.result, 1):
    print(f"{i}. {subtask.description} ({subtask.agent_type.value})")
```

### 6. AgentOrchestrator

Coordinates all agents using the ReAct pattern.

**ReAct Loop:**
1. **Thought**: Agent reasons about next action
2. **Action**: Execute chosen action (search, synthesize, validate)
3. **Observation**: Record results and update reasoning chain
4. **Repeat/Terminate**: Continue or stop based on conditions

**Example:**
```python
from src.solver.agentic_rag import AgentOrchestrator

orchestrator = AgentOrchestrator(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=gemini_client
)

response = await orchestrator.solve(
    query="What is the best surgical approach for L4-L5 stenosis?",
    context={"evidence_level": "2a", "patient_age": 65},
    max_iterations=5
)

print(response.final_answer)
print(f"Confidence: {response.confidence:.2f}")
print(f"GRADE: {response.evidence_grade}")

print("\nReasoning Chain:")
for step in response.reasoning_chain:
    print(f"{step.step_id}. {step.thought}")
    print(f"   → {step.action.value}")
    print(f"   → {step.observation[:100]}...")
```

---

## Data Structures

### AgentTask

```python
@dataclass
class AgentTask:
    task_id: str                          # Unique task ID
    description: str                      # Natural language task
    context: Dict[str, Any]               # Additional context
    constraints: Dict[str, Any]           # Execution constraints
    agent_type: Optional[AgentType]       # Target agent type
    priority: int = 5                     # Priority (0-10)
```

### AgentResult

```python
@dataclass
class AgentResult:
    success: bool                         # Success status
    result: Any                           # Execution result
    reasoning: str                        # Natural language reasoning
    confidence: float                     # Confidence (0.0-1.0)
    metadata: Dict[str, Any]              # Metadata (timing, etc.)
    error: Optional[str]                  # Error message if failed
```

### ReActStep

```python
@dataclass
class ReActStep:
    step_id: int                          # Step number
    thought: str                          # Agent reasoning
    action: ActionType                    # Action taken
    action_input: Dict[str, Any]          # Action parameters
    observation: str                      # Action result
    timestamp: float                      # When step occurred
    duration_ms: float                    # Step duration
```

### AgentResponse

```python
@dataclass
class AgentResponse:
    final_answer: str                     # Final answer
    reasoning_chain: List[ReActStep]      # Complete reasoning trace
    sources: List[Dict[str, Any]]         # Source papers
    confidence: float                     # Overall confidence
    evidence_grade: Optional[str]         # GRADE rating
    metadata: Dict[str, Any]              # Metadata
```

---

## Usage Examples

### Example 1: Simple Factual Query

```python
from src.solver.agentic_rag import AgentOrchestrator, quick_solve

# Quick solve (convenience function)
response = await quick_solve(
    query="What is the fusion rate of TLIF?",
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=gemini_client
)

print(response.final_answer)
# Output: "TLIF demonstrates fusion rates of 85-95% based on 10 studies
#          (GRADE: 2A, moderate evidence)."
```

### Example 2: Comparative Query with Decomposition

```python
orchestrator = AgentOrchestrator(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=gemini_client
)

response = await orchestrator.solve(
    query="Compare TLIF vs OLIF for lumbar stenosis",
    context={"evidence_level": "2a"}
)

print(response.final_answer)
# Output: "TLIF and OLIF show comparable fusion rates (TLIF: 90%, OLIF: 88%).
#          OLIF has lower blood loss but higher surgical complexity.
#          Evidence: GRADE 2B, moderate-low quality."

# View reasoning chain
for step in response.reasoning_chain:
    print(f"{step.thought} → {step.action.value}")
# Output:
# 1. Analyzing query complexity: 'Compare TLIF vs OLIF...' → decompose_query
# 2. Searching for: 'TLIF for lumbar stenosis' → search_hybrid
# 3. Searching for: 'OLIF for lumbar stenosis' → search_hybrid
# 4. Synthesizing evidence for TLIF → Fusion rate → synthesize_evidence
# 5. Validating answer against evidence → validate_answer
```

### Example 3: Evidence Validation

```python
orchestrator = AgentOrchestrator(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=gemini_client
)

response = await orchestrator.solve(
    query="Is UBE effective for L4-L5 disc herniation?",
    context={"validate_answer": True}
)

print(f"Answer: {response.final_answer}")
print(f"Confidence: {response.confidence:.2f}")
print(f"GRADE: {response.evidence_grade}")

# Check validation details
validation_step = [s for s in response.reasoning_chain
                   if s.action == ActionType.VALIDATE_ANSWER][0]
print(f"Validation: {validation_step.observation}")
# Output: "Validated against 8 evidence sources. GRADE rating: 2A.
#          ✓ Answer is consistent with evidence."
```

---

## ReAct Pattern Details

### Thought Generation

Agents generate thoughts based on:
- Current query/task
- Previous results (from memory)
- Available actions
- Constraints and context

**Example Thought:**
```
"Query asks for comparison. Need to search for both interventions
separately before synthesizing evidence."
```

### Action Selection

Available actions:
- `SEARCH_GRAPH`: Graph-only search
- `SEARCH_VECTOR`: Vector-only search
- `SEARCH_HYBRID`: Combined graph + vector search
- `SYNTHESIZE_EVIDENCE`: Evidence aggregation with GRADE
- `VALIDATE_ANSWER`: Answer validation
- `DECOMPOSE_QUERY`: Query decomposition
- `COMBINE_RESULTS`: Result aggregation
- `TERMINATE`: End reasoning loop

### Observation Recording

Observations capture:
- Action results (counts, scores, etc.)
- Success/failure status
- Intermediate findings
- Evidence quality indicators

**Example Observation:**
```
"Executed hybrid search. Found 12 results in 150ms.
Evidence synthesis: improved (GRADE: 2A)."
```

### Early Stopping Conditions

The ReAct loop terminates when:
1. **Max iterations reached** (default: 5)
2. **High-confidence answer found** (confidence > 0.9)
3. **No more actions needed** (simple query resolved)
4. **Error encountered** (with error response)

---

## Integration with Existing Modules

### UnifiedSearchPipeline

SearchAgent uses UnifiedSearchPipeline for all search operations:
```python
# SearchAgent internally
search_response = await self.pipeline.search(query, options)
```

### EvidenceSynthesizer

SynthesisAgent uses EvidenceSynthesizer for GRADE-based evidence aggregation:
```python
# SynthesisAgent internally
synthesis = await self.synthesizer.synthesize(
    intervention=intervention,
    outcome=outcome,
    min_papers=2
)
```

### GeminiClient

All agents can use GeminiClient for:
- Natural language generation
- Query decomposition (PlanningAgent)
- Answer-evidence consistency (ValidationAgent)
- Evidence summarization (SynthesisAgent)

### MedicalRAGLogger

All agents use structured logging:
```python
logger.info(
    "SearchAgent executing search",
    query=query[:100],
    top_k=top_k
)

logger.info(
    "SearchAgent completed",
    confidence=confidence,
    result_count=len(results)
)
```

---

## Configuration

### Orchestrator Configuration

```python
config = {
    "max_iterations": 5,           # Max ReAct loop iterations
    "enable_planning": True,       # Enable PlanningAgent
    "enable_validation": True,     # Enable ValidationAgent
    "enable_synthesis": True,      # Enable SynthesisAgent
    "min_confidence": 0.7,         # Min confidence for early stopping
    "search_top_k": 10,            # Default search results
    "synthesis_min_papers": 2      # Min papers for synthesis
}

orchestrator = AgentOrchestrator(
    neo4j_client=neo4j_client,
    vector_db=vector_db,
    llm_client=gemini_client,
    config=config
)
```

### Agent-Specific Configuration

```python
# SearchAgent config
search_config = {
    "default_top_k": 10,
    "enable_synthesis": True,
    "detect_conflicts": True
}
search_agent = SearchAgent(pipeline=pipeline, config=search_config)

# SynthesisAgent config
synthesis_config = {
    "use_llm_summary": True,       # Generate LLM summaries
    "min_papers": 2,               # Min papers for synthesis
    "max_summary_tokens": 200      # Max summary length
}
synthesis_agent = SynthesisAgent(
    synthesizer=synthesizer,
    llm_client=llm_client,
    config=synthesis_config
)
```

---

## Performance Metrics

### Timing Breakdown

AgentResponse includes detailed timing:
```python
response = await orchestrator.solve(query)

print(f"Total time: {response.metadata['duration_s']:.2f}s")
print(f"Iterations: {response.metadata['iterations']}")
print(f"Sub-tasks: {response.metadata['sub_tasks']}")

# Per-step timing
for step in response.reasoning_chain:
    print(f"Step {step.step_id}: {step.duration_ms:.1f}ms")
```

### Confidence Scoring

Overall confidence combines:
- Search result scores (20%)
- Synthesis evidence strength (10%)
- Validation consistency (20%)
- Base confidence (50%)

```python
# Confidence interpretation
if response.confidence >= 0.9:
    print("High confidence - Strong evidence")
elif response.confidence >= 0.7:
    print("Moderate confidence - Reasonable evidence")
elif response.confidence >= 0.5:
    print("Low confidence - Weak evidence")
else:
    print("Very low confidence - Insufficient evidence")
```

---

## Error Handling

### Agent-Level Errors

Agents return error results instead of raising exceptions:
```python
result = await agent.execute(task)

if not result.success:
    print(f"Agent failed: {result.error}")
    print(f"Reasoning: {result.reasoning}")
    # Orchestrator can retry or use fallback
```

### Orchestrator-Level Errors

Orchestrator returns error responses:
```python
response = await orchestrator.solve(query)

if response.confidence == 0.0:
    print("Query failed")
    print(f"Error: {response.metadata.get('error')}")
    print(f"Reasoning chain: {len(response.reasoning_chain)} steps")
    # Partial results may still be useful
```

---

## Testing

Run tests:
```bash
# All agentic RAG tests
pytest tests/solver/test_agentic_rag.py -v

# Specific test
pytest tests/solver/test_agentic_rag.py::test_orchestrator_solve_simple -v

# With coverage
pytest tests/solver/test_agentic_rag.py --cov=src.solver.agentic_rag --cov-report=html
```

Test coverage includes:
- Base agent functionality
- Individual agent execution (15+ tests)
- Orchestrator coordination
- ReAct pattern implementation
- Error handling
- Data structure validation
- Integration tests

---

## Comparison with UnifiedSearchPipeline

| Feature | UnifiedSearchPipeline | Agentic RAG |
|---------|----------------------|-------------|
| **Architecture** | Linear pipeline | Multi-agent system |
| **Reasoning** | Implicit | Explicit (ReAct) |
| **Explainability** | Limited | Full reasoning chain |
| **Query Handling** | All queries same | Adaptive (decomposition) |
| **Validation** | Optional | Built-in |
| **Complexity** | Simple | Advanced |
| **Use Case** | Standard queries | Complex, multi-step queries |

**When to use Agentic RAG:**
- Complex multi-part queries
- Need for explainability
- Research/clinical decision support
- High-stakes answers requiring validation

**When to use UnifiedSearchPipeline:**
- Simple factual queries
- Performance-critical applications
- Batch processing
- Low-latency requirements

---

## Future Enhancements

### Planned Features

1. **Multi-Turn Dialogue**: Conversational agent with context retention
2. **Tool Integration**: External tool use (PubMed API, calculators)
3. **Confidence Calibration**: Learned confidence scoring
4. **Agent Learning**: Memory-based performance improvement
5. **Parallel Execution**: Concurrent agent execution
6. **Human-in-the-Loop**: Interactive validation and refinement

### Experimental Features

1. **Self-Reflection**: Agents critique their own outputs
2. **Meta-Agent**: Agent that manages other agents
3. **Knowledge Graph Navigation**: Graph traversal agent
4. **Evidence Contradiction Resolution**: Automated conflict resolution

---

## References

### Research Papers

1. Yao et al. (2022). "ReAct: Synergizing Reasoning and Acting in Language Models"
2. Wei et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in LLMs"
3. Park et al. (2023). "Generative Agents: Interactive Simulacra"

### Related Modules

- `unified_pipeline.py`: Base search pipeline
- `evidence_synthesizer.py`: GRADE-based evidence synthesis
- `adaptive_ranker.py`: Query-adaptive ranking
- `conflict_detector.py`: Evidence conflict detection

---

## Support

For questions or issues:
1. Check test cases in `tests/solver/test_agentic_rag.py`
2. Review example usage in `example_usage()` function
3. See integration patterns in Web UI (`web/pages/`)
4. Consult `TRD_v3_GraphRAG.md` for system architecture

---

## License

Part of Spine GraphRAG v3.0 system.
