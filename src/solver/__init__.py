"""Solver modules for knowledge retrieval and reasoning."""

# Direction Determiner (standalone, no dependencies)
from .direction_determiner import (
    DirectionDeterminer,
    OutcomeDirection,
    ComparisonResult,
    parse_numeric_value,
    interpret_from_extracted_outcome,
)

# Import other modules conditionally to avoid circular dependencies
try:
    from .conflict_detector import ConflictDetector, ConflictInput, ConflictOutput
    from .multi_factor_ranker import MultiFactorRanker, RankInput, RankOutput
    from .query_parser import QueryParser, QueryInput, ParsedQuery, QueryIntent
    from .tiered_search import (
        TieredHybridSearch,
        SearchInput,
        SearchOutput,
        SearchResult,
        SearchTier,
        SearchSource,
        ChunkInfo,
    )
    from .reasoner import (
        Reasoner,
        ReasonerInput,
        ReasoningResult,
        ReasoningType,
        ConfidenceLevel,
        Evidence,
        ReasoningStep,
    )
    from .response_generator import (
        ResponseGenerator,
        GeneratorInput,
        FormattedResponse,
        ResponseFormat,
        Citation,
        EvidenceItem,
        ConflictSummary,
    )
    from .multi_hop_reasoning import (
        MultiHopReasoner,
        QueryDecomposer,
        HopExecutor,
        SubQuery,
        QueryType,
        AnswerType,
        HopResult,
        ReasoningChain,
        ReasoningStep as MultiHopReasoningStep,
        MultiHopResult,
        create_multi_hop_reasoner,
    )

    _OTHER_MODULES_AVAILABLE = True
except ImportError as e:
    # Graph module not yet available, skip dependent imports
    _OTHER_MODULES_AVAILABLE = False

__all__ = [
    # Direction Determiner (always available)
    "DirectionDeterminer",
    "OutcomeDirection",
    "ComparisonResult",
    "parse_numeric_value",
    "interpret_from_extracted_outcome",
]

if _OTHER_MODULES_AVAILABLE:
    __all__ += [
        # Conflict Detector
        "ConflictDetector",
        "ConflictInput",
        "ConflictOutput",
        # Multi-factor Ranker
        "MultiFactorRanker",
        "RankInput",
        "RankOutput",
        # Query Parser
        "QueryParser",
        "QueryInput",
        "ParsedQuery",
        "QueryIntent",
        # Tiered Hybrid Search
        "TieredHybridSearch",
        "SearchInput",
        "SearchOutput",
        "SearchResult",
        "SearchTier",
        "SearchSource",
        "ChunkInfo",
        # Reasoner
        "Reasoner",
        "ReasonerInput",
        "ReasoningResult",
        "ReasoningType",
        "ConfidenceLevel",
        "Evidence",
        "ReasoningStep",
        # Response Generator
        "ResponseGenerator",
        "GeneratorInput",
        "FormattedResponse",
        "ResponseFormat",
        "Citation",
        "EvidenceItem",
        "ConflictSummary",
        # Multi-hop Reasoning
        "MultiHopReasoner",
        "QueryDecomposer",
        "HopExecutor",
        "SubQuery",
        "QueryType",
        "AnswerType",
        "HopResult",
        "ReasoningChain",
        "MultiHopReasoningStep",
        "MultiHopResult",
        "create_multi_hop_reasoner",
    ]
