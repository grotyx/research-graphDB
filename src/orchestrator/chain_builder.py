"""LangChain Chain Builder for Spine GraphRAG.

LangChain을 활용한 하이브리드 검색 및 QA 체인 구축.
- Graph Search (Neo4j Cypher)
- Vector Search (ChromaDB)
- Dual LLM Provider Support (Claude/Gemini)

Environment Variables:
- LLM_PROVIDER: "claude" (default) or "gemini"
- ANTHROPIC_API_KEY: Claude API key (required if provider=claude)
- GEMINI_API_KEY: Gemini API key (required if provider=gemini)
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

# LangChain core imports
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

# LangChain LLM integrations (lazy imports to avoid conflicts)
# Note: google-genai and langchain_google_genai may have version conflicts
ChatGoogleGenerativeAI = None
ChatAnthropic = None


def _get_gemini_llm_class():
    """Lazy import for Gemini LLM to avoid version conflicts."""
    global ChatGoogleGenerativeAI
    if ChatGoogleGenerativeAI is None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI as _ChatGoogleGenerativeAI
            ChatGoogleGenerativeAI = _ChatGoogleGenerativeAI
        except (ImportError, AttributeError) as e:
            logger.warning(f"langchain_google_genai import failed: {e}. Using fallback.")
            # Fallback: use google-genai directly via custom wrapper
            ChatGoogleGenerativeAI = None
    return ChatGoogleGenerativeAI


def _get_claude_llm_class():
    """Lazy import for Claude LLM."""
    global ChatAnthropic
    if ChatAnthropic is None:
        from langchain_anthropic import ChatAnthropic as _ChatAnthropic
        ChatAnthropic = _ChatAnthropic
    return ChatAnthropic


class LLMProvider(Enum):
    """LLM provider enum."""
    CLAUDE = "claude"
    GEMINI = "gemini"

# Internal imports
from ..graph.neo4j_client import Neo4jClient
from ..storage import SearchResult as VectorSearchResult

# TieredVectorDB is deprecated (v1.14.12), Neo4j Vector Index is used instead
# Attempt import for backward compatibility; gracefully degrade if missing
try:
    from ..storage.vector_db import TieredVectorDB
except (ImportError, ModuleNotFoundError):
    TieredVectorDB = None  # ChromaDB removed; Neo4j Vector Index is used instead
from ..solver.hybrid_ranker import HybridRanker, HybridResult
from ..solver.graph_search import GraphSearch
from .cypher_generator import CypherGenerator

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ChainConfig:
    """체인 설정."""
    # LLM Provider settings
    provider: str = ""  # Will default to env or "claude" in __post_init__
    claude_model: str = ""  # Will default to env or default in __post_init__
    gemini_model: str = ""  # Will default to env or default in __post_init__

    # Generation settings
    temperature: float = 0.1
    max_output_tokens: int = 8192

    # Search settings
    top_k: int = 10
    graph_weight: float = 0.6
    vector_weight: float = 0.4
    min_p_value: float = 0.05

    def __post_init__(self):
        """Set defaults from environment variables."""
        if not self.provider:
            self.provider = os.getenv("LLM_PROVIDER", "claude")
        if not self.claude_model:
            self.claude_model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        if not self.gemini_model:
            self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")


@dataclass
class ChainInput:
    """체인 입력."""
    query: str
    chat_history: Optional[list[dict]] = None
    filters: Optional[dict] = None


@dataclass
class ChainOutput:
    """체인 출력."""
    answer: str
    sources: list[HybridResult]
    cypher_query: str = ""
    graph_results: Optional[list[dict]] = None
    vector_results: Optional[list[VectorSearchResult]] = None
    metadata: Optional[dict] = None


# =============================================================================
# Custom Retrievers
# =============================================================================

class HybridRetriever:
    """Hybrid Retriever combining Graph + Vector Search.

    LangChain의 BaseRetriever를 구현하지 않고, 직접 invoke() 메서드 제공.
    LangChain 체인에서 RunnableLambda로 감싸서 사용.
    """

    def __init__(
        self,
        hybrid_ranker: HybridRanker,
        cypher_generator: CypherGenerator,
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4,
    ):
        """초기화.

        Args:
            hybrid_ranker: HybridRanker 인스턴스
            cypher_generator: CypherGenerator 인스턴스
            top_k: 반환할 결과 수
            graph_weight: Graph 결과 가중치
            vector_weight: Vector 결과 가중치
        """
        self.hybrid_ranker = hybrid_ranker
        self.cypher_generator = cypher_generator
        self.top_k = top_k
        self.graph_weight = graph_weight
        self.vector_weight = vector_weight

    async def ainvoke(self, query: str) -> list[HybridResult]:
        """비동기 검색 수행.

        Args:
            query: 검색 쿼리

        Returns:
            HybridResult 목록
        """
        # 1. 엔티티 추출
        entities = self.cypher_generator.extract_entities(query)
        logger.info(f"Extracted entities: {entities}")

        # 2. 쿼리 임베딩 생성
        query_embedding = self.hybrid_ranker.vector_db.get_embedding(query)

        # 3. Hybrid 검색
        results = await self.hybrid_ranker.search(
            query=query,
            query_embedding=query_embedding,
            top_k=self.top_k,
            graph_weight=self.graph_weight,
            vector_weight=self.vector_weight,
        )

        logger.info(f"Retrieved {len(results)} hybrid results")
        return results

    def invoke(self, query: str) -> list[HybridResult]:
        """동기 검색 (async 래퍼).

        Args:
            query: 검색 쿼리

        Returns:
            HybridResult 목록
        """
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.ainvoke(query))


# =============================================================================
# Prompt Templates
# =============================================================================

RETRIEVAL_QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a spine surgery research assistant specializing in evidence-based medicine.

Your task is to answer questions based on scientific evidence from medical papers.

Guidelines:
1. Base your answer ONLY on the provided evidence
2. Always cite the source papers (paper_id or title)
3. Distinguish between:
   - Graph Evidence: Statistical results (p-values, effect sizes) from structured data
   - Vector Evidence: Background information and discussion from paper text
4. If evidence is conflicting, explain both sides
5. If evidence is insufficient, say so clearly

Evidence Levels:
- 1a: Meta-analysis of RCTs (highest quality)
- 1b: Randomized Controlled Trial
- 2a: Cohort study
- 2b: Case-control study
- 3: Case series
- 4: Expert opinion (lowest quality)

Always prioritize higher evidence levels in your answer."""),
    ("human", """Question: {question}

Evidence:
{context}

Answer:""")
])


CONFLICTING_EVIDENCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are analyzing conflicting evidence from multiple studies.

Your task is to:
1. Identify key differences in study designs
2. Explain possible reasons for conflicting results
3. Provide a balanced summary
4. Recommend which evidence to trust based on:
   - Evidence level (1a > 1b > 2a > 2b > 3 > 4)
   - Sample size
   - Statistical significance (p-value)
   - Study recency"""),
    ("human", """Question: {question}

Conflicting Evidence:
{context}

Analysis:""")
])


# =============================================================================
# Main Chain Builder
# =============================================================================

class SpineGraphChain:
    """Spine GraphRAG 메인 체인.

    LangChain을 활용하여 Graph + Vector 하이브리드 검색 및
    LLM 기반 응답 생성을 수행. Claude와 Gemini 모두 지원.

    사용 예:
        chain = SpineGraphChain(
            neo4j_client=neo4j_client,
            vector_db=vector_db
        )
        result = await chain.invoke("OLIF가 VAS 개선에 효과적인가?")
        print(result.answer)
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        vector_db: Optional[Any] = None,
        config: Optional[ChainConfig] = None,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            vector_db: Vector DB 인스턴스 (Optional, deprecated since v1.14.12.
                       Neo4j Vector Index is used instead when None.)
            config: 체인 설정 (None이면 기본값 사용)
            api_key: LLM API 키 (None이면 환경변수에서 로드)
            provider: LLM provider ("claude" or "gemini", overrides config)
        """
        self.neo4j_client = neo4j_client
        self.vector_db = vector_db
        self.config = config or ChainConfig()

        # Override provider if specified
        if provider:
            self.config.provider = provider

        # Initialize LLM based on provider
        self.llm = self._create_llm(api_key)

        # Hybrid Ranker
        # When vector_db is None (ChromaDB removed), fall back to Neo4j hybrid search
        self.hybrid_ranker = HybridRanker(
            vector_db=vector_db,
            neo4j_client=neo4j_client,
            use_neo4j_hybrid=(vector_db is None),
        )

        # Cypher Generator
        self.cypher_generator = CypherGenerator()

        # Graph Search
        self.graph_search = GraphSearch(neo4j_client=neo4j_client)

        # Hybrid Retriever
        self.retriever = HybridRetriever(
            hybrid_ranker=self.hybrid_ranker,
            cypher_generator=self.cypher_generator,
            top_k=self.config.top_k,
            graph_weight=self.config.graph_weight,
            vector_weight=self.config.vector_weight,
        )

        # QA Chain
        self.qa_chain = None
        self.conflict_chain = None

        logger.info(f"SpineGraphChain initialized with provider={self.config.provider}")

    def _create_llm(self, api_key: Optional[str] = None):
        """Create LLM instance based on provider.

        Args:
            api_key: API key (optional, uses env if not provided)

        Returns:
            LangChain chat model (ChatAnthropic or ChatGoogleGenerativeAI)

        Raises:
            ValueError: If unsupported provider or required library not available
        """
        provider = self.config.provider.lower()

        if provider == "claude":
            ChatAnthropicClass = _get_claude_llm_class()
            return ChatAnthropicClass(
                model=self.config.claude_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_output_tokens,
                anthropic_api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            )
        elif provider == "gemini":
            ChatGoogleGenerativeAIClass = _get_gemini_llm_class()
            if ChatGoogleGenerativeAIClass is None:
                raise ValueError(
                    "Gemini LLM not available. Install compatible version of "
                    "langchain_google_genai or use provider='claude' instead."
                )
            return ChatGoogleGenerativeAIClass(
                model=self.config.gemini_model,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
                google_api_key=api_key or os.getenv("GEMINI_API_KEY"),
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}. Use 'claude' or 'gemini'.")

    def build_retrieval_chain(self) -> Any:
        """하이브리드 검색 체인 구축.

        Returns:
            LangChain Runnable 체인
        """
        # 검색 체인: query → retrieval → documents
        retrieval_chain = (
            RunnablePassthrough()
            | RunnableLambda(lambda x: self.retriever.invoke(x))
        )

        return retrieval_chain

    def build_qa_chain(self) -> Any:
        """QA 체인 구축.

        Returns:
            LangChain QA 체인
        """
        # QA 체인: query → retrieval → format_context → LLM
        qa_chain = (
            {
                "question": RunnablePassthrough(),
                "context": (
                    RunnableLambda(lambda x: self.retriever.invoke(x))
                    | RunnableLambda(self._format_context)
                ),
            }
            | RETRIEVAL_QA_PROMPT
            | self.llm
        )

        self.qa_chain = qa_chain
        return qa_chain

    def build_conflict_chain(self) -> Any:
        """상충 결과 분석 체인 구축.

        Returns:
            LangChain 상충 분석 체인
        """
        conflict_chain = (
            {
                "question": RunnablePassthrough(),
                "context": (
                    RunnableLambda(lambda x: self.retriever.invoke(x))
                    | RunnableLambda(self._format_conflicting_context)
                ),
            }
            | CONFLICTING_EVIDENCE_PROMPT
            | self.llm
        )

        self.conflict_chain = conflict_chain
        return conflict_chain

    async def invoke(
        self,
        query: str,
        mode: str = "qa",
        **kwargs
    ) -> ChainOutput:
        """체인 실행 (메인 진입점).

        Args:
            query: 사용자 쿼리
            mode: 실행 모드 ("qa", "conflict", "retrieval")
            **kwargs: 추가 파라미터

        Returns:
            ChainOutput

        Raises:
            ValueError: 잘못된 mode
        """
        logger.info(f"Invoking chain with query: {query}, mode: {mode}")

        try:
            if mode == "qa":
                return await self._invoke_qa(query, **kwargs)
            elif mode == "conflict":
                return await self._invoke_conflict(query, **kwargs)
            elif mode == "retrieval":
                return await self._invoke_retrieval(query, **kwargs)
            else:
                raise ValueError(f"Invalid mode: {mode}")

        except Exception as e:
            logger.error(f"Chain invocation error: {e}")
            return ChainOutput(
                answer=f"Error: {str(e)}",
                sources=[],
                metadata={"error": str(e)}
            )

    async def _invoke_qa(self, query: str, **kwargs) -> ChainOutput:
        """QA 모드 실행.

        Args:
            query: 사용자 쿼리

        Returns:
            ChainOutput
        """
        # 1. Build QA chain if not exists
        if self.qa_chain is None:
            self.build_qa_chain()

        # 2. Retrieve evidence
        sources = await self.retriever.ainvoke(query)

        # 3. Format context
        context = self._format_context(sources)

        # 4. Generate answer
        response = await self.qa_chain.ainvoke(query)

        # 5. Extract answer text
        if hasattr(response, "content"):
            answer = response.content
        else:
            answer = str(response)

        return ChainOutput(
            answer=answer,
            sources=sources,
            metadata={
                "mode": "qa",
                "num_sources": len(sources),
                "graph_count": sum(1 for s in sources if s.result_type == "graph"),
                "vector_count": sum(1 for s in sources if s.result_type == "vector"),
            }
        )

    async def _invoke_conflict(self, query: str, **kwargs) -> ChainOutput:
        """상충 결과 분석 모드.

        Args:
            query: 사용자 쿼리

        Returns:
            ChainOutput
        """
        # 1. Build conflict chain if not exists
        if self.conflict_chain is None:
            self.build_conflict_chain()

        # 2. Retrieve evidence
        sources = await self.retriever.ainvoke(query)

        # 3. Filter conflicting evidence
        conflicting_sources = self._detect_conflicts(sources)

        if not conflicting_sources:
            return ChainOutput(
                answer="No conflicting evidence found.",
                sources=sources,
                metadata={"mode": "conflict", "conflicts": False}
            )

        # 4. Generate conflict analysis
        response = await self.conflict_chain.ainvoke(query)

        # 5. Extract answer text
        if hasattr(response, "content"):
            answer = response.content
        else:
            answer = str(response)

        return ChainOutput(
            answer=answer,
            sources=conflicting_sources,
            metadata={
                "mode": "conflict",
                "conflicts": True,
                "num_conflicts": len(conflicting_sources)
            }
        )

    async def _invoke_retrieval(self, query: str, **kwargs) -> ChainOutput:
        """검색만 수행 (LLM 없음).

        Args:
            query: 사용자 쿼리

        Returns:
            ChainOutput (answer는 빈 문자열)
        """
        sources = await self.retriever.ainvoke(query)

        return ChainOutput(
            answer="",
            sources=sources,
            metadata={
                "mode": "retrieval",
                "num_sources": len(sources)
            }
        )

    def _format_context(self, results: list[HybridResult]) -> str:
        """검색 결과를 LLM 입력용 컨텍스트로 포맷팅.

        Args:
            results: HybridResult 목록

        Returns:
            포맷팅된 컨텍스트 문자열
        """
        if not results:
            return "No evidence found."

        context_parts = []

        for i, result in enumerate(results, 1):
            # Header
            source_type = "📊 GRAPH" if result.result_type == "graph" else "📄 VECTOR"
            context_parts.append(f"\n{source_type} Evidence #{i} (Score: {result.score:.3f})")

            # Citation
            citation = result.get_citation()
            if citation:
                context_parts.append(f"Source: {citation}")

            # Evidence text
            evidence = result.get_evidence_text()
            context_parts.append(f"Evidence: {evidence}")

            # Metadata
            if result.result_type == "graph":
                meta = result.metadata
                if "p_value" in meta:
                    context_parts.append(f"  p-value: {meta['p_value']:.4f}")
                if "evidence_level" in meta:
                    context_parts.append(f"  Evidence Level: {meta['evidence_level']}")

            context_parts.append("")  # Blank line

        return "\n".join(context_parts)

    def _format_conflicting_context(self, results: list[HybridResult]) -> str:
        """상충 결과를 LLM 입력용 컨텍스트로 포맷팅.

        Args:
            results: HybridResult 목록

        Returns:
            포맷팅된 컨텍스트 문자열
        """
        conflicting = self._detect_conflicts(results)

        if not conflicting:
            return "No conflicting evidence found."

        return self._format_context(conflicting)

    def _detect_conflicts(self, results: list[HybridResult]) -> list[HybridResult]:
        """상충하는 결과 탐지.

        같은 intervention-outcome 쌍에 대해 서로 다른 direction을 가진
        Graph evidence를 찾음.

        Args:
            results: HybridResult 목록

        Returns:
            상충하는 결과만 포함된 목록
        """
        # Graph 결과만 필터링
        graph_results = [r for r in results if r.result_type == "graph"]

        # intervention-outcome 쌍별로 그룹화
        groups = {}
        for result in graph_results:
            if not result.evidence:
                continue

            key = (result.evidence.intervention, result.evidence.outcome)
            if key not in groups:
                groups[key] = []
            groups[key].append(result)

        # 각 그룹에서 direction이 다른 것 찾기
        conflicts = []
        for key, group in groups.items():
            directions = {r.evidence.direction for r in group}
            if len(directions) > 1:
                # 상충 발견
                conflicts.extend(group)

        return conflicts

    def get_stats(self) -> dict:
        """체인 통계 정보.

        Returns:
            통계 딕셔너리
        """
        provider = self.config.provider.lower()
        model = (
            self.config.claude_model if provider == "claude"
            else self.config.gemini_model
        )

        return {
            "config": {
                "provider": provider,
                "model": model,
                "top_k": self.config.top_k,
                "graph_weight": self.config.graph_weight,
                "vector_weight": self.config.vector_weight,
            },
            "hybrid_ranker": self.hybrid_ranker.get_stats(),
        }


# =============================================================================
# Factory Functions
# =============================================================================

async def create_chain(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: str = "password",
    chromadb_path: str = "./data/chromadb",
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    config: Optional[ChainConfig] = None,
    # Legacy parameter
    gemini_api_key: Optional[str] = None,
) -> SpineGraphChain:
    """체인 생성 헬퍼 함수.

    Args:
        neo4j_uri: Neo4j URI
        neo4j_username: Neo4j 사용자명
        neo4j_password: Neo4j 비밀번호
        chromadb_path: ChromaDB 저장 경로
        api_key: LLM API 키 (provider에 맞는 키)
        provider: LLM provider ("claude" or "gemini")
        config: 체인 설정
        gemini_api_key: [DEPRECATED] Use api_key and provider instead

    Returns:
        초기화된 SpineGraphChain
    """
    from ..graph.neo4j_client import Neo4jConfig

    # Handle legacy parameter
    if gemini_api_key and not api_key:
        logger.warning(
            "gemini_api_key is deprecated. Use api_key and provider='gemini' instead."
        )
        api_key = gemini_api_key
        if not provider:
            provider = "gemini"

    # Neo4j 클라이언트
    neo4j_config = Neo4jConfig(
        uri=neo4j_uri,
        username=neo4j_username,
        password=neo4j_password,
    )
    neo4j_client = Neo4jClient(config=neo4j_config)
    await neo4j_client.connect()

    # Vector DB (deprecated: ChromaDB removed in v1.14.12, Neo4j Vector Index used instead)
    vector_db = None
    if TieredVectorDB is not None:
        try:
            vector_db = TieredVectorDB(persist_directory=chromadb_path)
        except Exception as e:
            logger.warning(f"TieredVectorDB initialization failed: {e}. Continuing without ChromaDB vector search.")
    else:
        logger.info("TieredVectorDB not available. Using Neo4j Vector Index for vector search.")

    # 체인 생성
    chain = SpineGraphChain(
        neo4j_client=neo4j_client,
        vector_db=vector_db,
        config=config,
        api_key=api_key,
        provider=provider,
    )

    return chain


# =============================================================================
# Usage Example
# =============================================================================

async def example_usage():
    """사용 예시.

    Uses LLM_PROVIDER env var to select provider (default: claude).
    Set LLM_PROVIDER=gemini to use Gemini instead.
    """
    from dotenv import load_dotenv

    load_dotenv()

    # 체인 생성 (uses LLM_PROVIDER from env)
    chain = await create_chain(
        # provider="claude",  # or "gemini", or leave None for env default
    )

    print(f"Using provider: {chain.config.provider}")

    # QA 모드
    result = await chain.invoke(
        "OLIF가 VAS 개선에 효과적인가?",
        mode="qa"
    )

    print("=" * 80)
    print("ANSWER:")
    print(result.answer)
    print("\n" + "=" * 80)
    print(f"SOURCES ({len(result.sources)}):")
    for i, source in enumerate(result.sources, 1):
        print(f"{i}. [{source.result_type}] Score: {source.score:.3f}")
        print(f"   {source.get_evidence_text()}")
        print(f"   {source.get_citation()}")

    # 상충 결과 분석
    result = await chain.invoke(
        "OLIF와 TLIF의 Fusion Rate 비교 결과가 일치하는가?",
        mode="conflict"
    )

    print("\n" + "=" * 80)
    print("CONFLICT ANALYSIS:")
    print(result.answer)

    # 통계 출력
    stats = chain.get_stats()
    print("\n" + "=" * 80)
    print("CHAIN STATS:")
    print(stats)


if __name__ == "__main__":
    asyncio.run(example_usage())
