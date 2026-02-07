"""Orchestrator Module - Query Processing and Response Synthesis.

LangChain 통합 및 Hybrid 검색 결과를 활용한 응답 생성 모듈.

주요 컴포넌트:
- CypherGenerator: 자연어 → Cypher 변환
- ResponseSynthesizer: Graph + Vector → 통합 답변 생성
- ChainBuilder: LangChain 통합 (optional, requires langchain)
"""

# CypherGenerator (core component)
try:
    from .cypher_generator import (
        CypherGenerator,
        QueryIntent,
        ExtractedEntities,
    )
except ImportError:
    CypherGenerator = None
    QueryIntent = None
    ExtractedEntities = None

# ResponseSynthesizer (optional - requires LLM)
try:
    from .response_synthesizer import (
        ResponseSynthesizer,
        SynthesizedResponse,
        EVIDENCE_LEVEL_DESCRIPTIONS,
    )
except ImportError:
    ResponseSynthesizer = None
    SynthesizedResponse = None
    EVIDENCE_LEVEL_DESCRIPTIONS = {}

# Optional LangChain components
try:
    from .chain_builder import (
        SpineGraphChain,
        ChainConfig,
        ChainInput,
        ChainOutput,
        HybridRetriever,
        create_chain,
    )
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    SpineGraphChain = None
    ChainConfig = None
    ChainInput = None
    ChainOutput = None
    HybridRetriever = None
    create_chain = None

__all__ = [
    # Cypher Generator (core)
    "CypherGenerator",
    "QueryIntent",
    "ExtractedEntities",

    # Response Synthesizer (optional)
    "ResponseSynthesizer",
    "SynthesizedResponse",
    "EVIDENCE_LEVEL_DESCRIPTIONS",

    # Chain Builder (optional)
    "SpineGraphChain",
    "ChainConfig",
    "ChainInput",
    "ChainOutput",
    "HybridRetriever",
    "create_chain",
    "LANGCHAIN_AVAILABLE",
]
