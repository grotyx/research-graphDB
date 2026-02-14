"""Chain Bridge - MedicalKAGServer Integration.

Provides search and QA functionality using MedicalKAGServer directly.
Replaces LangChain-based SpineGraphChain with native server calls.

v1.14.4: Rewrote to use MedicalKAGServer handlers directly.
v1.14.5: Added direct Neo4j vector search with OpenAI embeddings.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import streamlit as st

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


@dataclass
class SearchResult:
    """Search result for UI display."""

    content: str
    score: float
    tier: str = "unknown"
    source_type: str = "unknown"
    evidence_level: str = "unknown"
    document_id: str = ""
    paper_id: str = ""
    title: str = ""
    graph_score: float = 0.0
    vector_score: float = 0.0
    result_type: str = "vector"  # "graph", "vector", or "hybrid"
    metadata: dict = field(default_factory=dict)  # Additional metadata for UI

    def __post_init__(self):
        """Initialize metadata if empty."""
        if not self.metadata:
            self.metadata = {
                "paper_id": self.paper_id,
                "title": self.title,
                "evidence_level": self.evidence_level,
            }

    def to_dict(self) -> dict:
        """Convert to dictionary for compatibility."""
        return {
            "content": self.content,
            "score": self.score,
            "tier": self.tier,
            "source_type": self.source_type,
            "evidence_level": self.evidence_level,
            "document_id": self.document_id,
            "paper_id": self.paper_id,
            "title": self.title,
            "graph_score": self.graph_score,
            "vector_score": self.vector_score,
            "result_type": self.result_type,
            "metadata": self.metadata,
        }


class ChainBridge:
    """Bridge to MedicalKAGServer with caching."""

    _instance = None
    _server = None
    _embedding_gen = None
    _initialized = False

    @classmethod
    def get_instance(cls) -> "ChainBridge":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_server(self):
        """Get or create MedicalKAGServer instance.

        Returns:
            MedicalKAGServer instance or None if not available
        """
        if self._server is not None and self._initialized:
            return self._server

        try:
            from medical_mcp.medical_kag_server import MedicalKAGServer

            # Create server instance
            server = MedicalKAGServer(
                enable_llm=True,
                use_neo4j_storage=True,
            )

            # Initialize Neo4j connection
            if hasattr(server, 'neo4j_client') and server.neo4j_client:
                if not server.neo4j_client._driver:
                    await server.neo4j_client.connect()

            # Initialize embedding generator
            try:
                from core.embedding import OpenAIEmbeddingGenerator
                self._embedding_gen = OpenAIEmbeddingGenerator()
            except Exception as e:
                print(f"Warning: Could not initialize embedding generator: {e}")
                self._embedding_gen = None

            self._server = server
            self._initialized = True
            return server

        except Exception as e:
            print(f"Error creating MedicalKAGServer: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_embedding_generator(self):
        """Get embedding generator."""
        return self._embedding_gen

    @property
    def is_available(self) -> bool:
        """Check if server is available."""
        return self._server is not None and self._initialized


# Cache version
_CACHE_VERSION = "v3"


@st.cache_resource
def get_chain_bridge(_version: str = _CACHE_VERSION) -> ChainBridge:
    """Get cached chain bridge instance.

    Args:
        _version: Cache version (change to bust cache)

    Returns:
        ChainBridge instance
    """
    return ChainBridge.get_instance()


async def _neo4j_vector_search(
    server,
    query: str,
    embedding_gen,
    top_k: int = 10,
    min_score: float = 0.3,
) -> list[dict]:
    """Perform vector search directly on Neo4j.

    Args:
        server: MedicalKAGServer instance
        query: Search query
        embedding_gen: Embedding generator
        top_k: Number of results
        min_score: Minimum similarity score

    Returns:
        List of search results
    """
    if not embedding_gen:
        return []

    try:
        # Generate query embedding
        query_embedding = embedding_gen.embed(query)

        # Search using Neo4j vector index
        if hasattr(server, 'neo4j_client') and server.neo4j_client:
            results = await server.neo4j_client.vector_search_chunks(
                embedding=query_embedding,
                top_k=top_k,
                min_score=min_score,
            )
            return results
        return []
    except Exception as e:
        print(f"Neo4j vector search error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def _neo4j_graph_search(
    server,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Perform graph-based search on Neo4j.

    Args:
        server: MedicalKAGServer instance
        query: Search query
        limit: Number of results

    Returns:
        List of search results
    """
    if not hasattr(server, 'neo4j_client') or not server.neo4j_client:
        return []

    try:
        # Simple keyword-based graph search
        # Search for papers containing query terms in title or content
        cypher_query = """
        MATCH (p:Paper)
        WHERE toLower(p.title) CONTAINS toLower($query)
           OR EXISTS {
               MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
               WHERE toLower(c.content) CONTAINS toLower($query)
           }
        WITH p,
             CASE WHEN toLower(p.title) CONTAINS toLower($query) THEN 1.0 ELSE 0.5 END as relevance
        OPTIONAL MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
        RETURN p.paper_id as paper_id,
               p.title as title,
               p.year as year,
               p.evidence_level as evidence_level,
               collect(DISTINCT c.content)[0..3] as chunks,
               relevance as score
        ORDER BY relevance DESC, p.year DESC
        LIMIT $limit
        """

        results = await server.neo4j_client.run_query(
            cypher_query,
            {"query": query, "limit": limit}
        )

        # Convert to standard format
        formatted = []
        for r in results:
            chunks = r.get("chunks", [])
            content = " ".join(chunks[:2]) if chunks else ""
            formatted.append({
                "paper_id": r.get("paper_id", ""),
                "title": r.get("title", ""),
                "content": content[:500] if content else r.get("title", ""),
                "score": r.get("score", 0.5),
                "evidence_level": r.get("evidence_level", "unknown"),
                "year": r.get("year"),
            })
        return formatted

    except Exception as e:
        print(f"Neo4j graph search error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def hybrid_search(
    query: str,
    search_type: str = "hybrid",
    top_k: int = 10,
    graph_weight: float = 0.6,
    vector_weight: float = 0.4,
) -> dict:
    """Perform hybrid search using Neo4j vector and graph search.

    Args:
        query: Search query
        search_type: "hybrid", "graph_only", or "vector_only"
        top_k: Number of results
        graph_weight: Graph evidence weight (0-1)
        vector_weight: Vector evidence weight (0-1)

    Returns:
        Dict with results
    """
    bridge = get_chain_bridge()
    server = await bridge.get_server()

    if server is None:
        return {
            "success": False,
            "error": "MedicalKAGServer not available. Check Neo4j connection."
        }

    try:
        embedding_gen = bridge.get_embedding_generator()
        results = []

        if search_type == "graph_only":
            # Graph-only search
            graph_results = await _neo4j_graph_search(server, query, limit=top_k)
            results = graph_results

        elif search_type == "vector_only":
            # Vector-only search
            if embedding_gen:
                vector_results = await _neo4j_vector_search(
                    server, query, embedding_gen, top_k=top_k
                )
                # Convert to standard format
                for r in vector_results:
                    results.append({
                        "paper_id": r.get("paper_id", ""),
                        "title": r.get("paper_title", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0.0),
                        "evidence_level": r.get("evidence_level", "unknown"),
                        "tier": r.get("tier", "unknown"),
                    })
            else:
                # Fallback to graph search if no embedding generator
                graph_results = await _neo4j_graph_search(server, query, limit=top_k)
                results = graph_results

        else:
            # Hybrid search - combine vector and graph
            vector_results = []
            graph_results = []

            if embedding_gen:
                vector_results = await _neo4j_vector_search(
                    server, query, embedding_gen, top_k=top_k
                )

            graph_results = await _neo4j_graph_search(server, query, limit=top_k)

            # Merge results with weights
            result_map = {}

            # Add graph results
            for r in graph_results:
                key = r.get("paper_id", "")
                if key:
                    result_map[key] = {
                        "paper_id": key,
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "graph_score": r.get("score", 0.0) * graph_weight,
                        "vector_score": 0.0,
                        "evidence_level": r.get("evidence_level", "unknown"),
                        "tier": "graph",
                    }

            # Add/merge vector results
            for r in vector_results:
                key = r.get("paper_id", "")
                if key:
                    if key in result_map:
                        result_map[key]["vector_score"] = r.get("score", 0.0) * vector_weight
                        result_map[key]["tier"] = "hybrid"
                        # Prefer vector content as it's more specific
                        if r.get("content"):
                            result_map[key]["content"] = r.get("content", "")
                    else:
                        result_map[key] = {
                            "paper_id": key,
                            "title": r.get("paper_title", ""),
                            "content": r.get("content", ""),
                            "graph_score": 0.0,
                            "vector_score": r.get("score", 0.0) * vector_weight,
                            "evidence_level": r.get("evidence_level", "unknown"),
                            "tier": r.get("tier", "vector"),
                        }

            # Calculate final scores and sort
            for key, val in result_map.items():
                val["score"] = val["graph_score"] + val["vector_score"]

            results = sorted(
                result_map.values(),
                key=lambda x: x.get("score", 0),
                reverse=True
            )[:top_k]

        # Convert to SearchResult objects
        sources = []
        for r in results:
            # Determine result_type based on scores
            g_score = r.get("graph_score", 0.0)
            v_score = r.get("vector_score", 0.0)
            if g_score > 0 and v_score > 0:
                result_type = "hybrid"
            elif g_score > 0:
                result_type = "graph"
            else:
                result_type = "vector"

            sr = SearchResult(
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                tier=r.get("tier", "unknown"),
                source_type="paper",
                evidence_level=r.get("evidence_level", "unknown"),
                document_id=r.get("paper_id", ""),
                paper_id=r.get("paper_id", ""),
                title=r.get("title", ""),
                graph_score=g_score,
                vector_score=v_score,
                result_type=result_type,
                metadata={
                    "paper_id": r.get("paper_id", ""),
                    "title": r.get("title", ""),
                    "evidence_level": r.get("evidence_level", "unknown"),
                    "year": r.get("year"),
                },
            )
            sources.append(sr)

        return {
            "success": True,
            "query": query,
            "sources": sources,
            "metadata": {
                "search_type": search_type,
                "total_found": len(sources),
                "has_embedding": embedding_gen is not None,
            },
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


async def ask_question(
    query: str,
    mode: str = "qa",
    top_k: int = 10,
    graph_weight: float = 0.6,
    vector_weight: float = 0.4,
) -> dict:
    """Ask a question using MedicalKAGServer with LLM.

    Args:
        query: Question
        mode: "qa" or "conflict"
        top_k: Number of evidence sources
        graph_weight: Graph evidence weight
        vector_weight: Vector evidence weight

    Returns:
        Dict with answer and sources
    """
    bridge = get_chain_bridge()
    server = await bridge.get_server()

    if server is None:
        return {
            "success": False,
            "error": "MedicalKAGServer not available."
        }

    try:
        # First, get search results
        search_result = await hybrid_search(
            query=query,
            search_type="hybrid",
            top_k=top_k,
            graph_weight=graph_weight,
            vector_weight=vector_weight,
        )

        if not search_result.get("success", False):
            return search_result

        sources = search_result.get("sources", [])

        # If conflict mode, use conflict detection
        if mode == "conflict":
            if hasattr(server, 'reasoning_handler') and server.reasoning_handler:
                try:
                    conflict_result = await server.reasoning_handler.find_conflicts(
                        query=query
                    )
                    if conflict_result.get("success"):
                        return {
                            "success": True,
                            "query": query,
                            "answer": _format_conflict_answer(conflict_result),
                            "sources": sources,
                            "metadata": {
                                "mode": "conflict",
                                "conflicts": conflict_result.get("conflicts", []),
                            },
                        }
                except Exception as e:
                    print(f"Conflict detection error: {e}")

        # Generate answer using LLM
        if hasattr(server, 'llm_client') and server.llm_client:
            # Build context from search results
            context_parts = []
            for i, source in enumerate(sources[:5], 1):  # Use top 5 sources
                content = source.content if isinstance(source, SearchResult) else source.get("content", "")
                title = source.title if isinstance(source, SearchResult) else source.get("title", "")
                evidence_level = source.evidence_level if isinstance(source, SearchResult) else source.get("evidence_level", "")

                context_parts.append(f"[{i}] {title}\nEvidence Level: {evidence_level}\n{content[:500]}")

            context = "\n\n".join(context_parts)

            if not context.strip():
                return {
                    "success": True,
                    "query": query,
                    "answer": "No relevant evidence found in the database for this query.",
                    "sources": sources,
                    "metadata": {
                        "mode": mode,
                        "source_count": 0,
                    },
                }

            # Generate answer
            prompt = f"""Based on the following medical evidence, answer the question.

Question: {query}

Evidence:
{context}

Provide a concise, evidence-based answer with citations to the sources using [1], [2], etc."""

            answer = await server.llm_client.generate(
                prompt=prompt,
                system_prompt="You are a medical research assistant. Provide accurate, evidence-based answers citing the provided sources."
            )

            return {
                "success": True,
                "query": query,
                "answer": answer,
                "sources": sources,
                "metadata": {
                    "mode": mode,
                    "source_count": len(sources),
                },
            }
        else:
            # No LLM available, return sources only
            return {
                "success": True,
                "query": query,
                "answer": "LLM not available. Here are the relevant sources.",
                "sources": sources,
                "metadata": {
                    "mode": mode,
                    "llm_available": False,
                },
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


def _format_conflict_answer(conflict_result: dict) -> str:
    """Format conflict detection result as answer text."""
    conflicts = conflict_result.get("conflicts", [])
    if not conflicts:
        return "No significant conflicts detected in the evidence."

    answer_parts = ["**Evidence Conflicts Detected:**\n"]
    for i, conflict in enumerate(conflicts, 1):
        answer_parts.append(
            f"{i}. {conflict.get('description', 'Conflict between studies')}\n"
            f"   - Studies: {conflict.get('study1', 'Unknown')} vs {conflict.get('study2', 'Unknown')}\n"
            f"   - Severity: {conflict.get('severity', 'Unknown')}\n"
        )

    return "\n".join(answer_parts)


# Legacy compatibility aliases
async def search(query: str, **kwargs) -> dict:
    """Legacy search function alias."""
    return await hybrid_search(query, **kwargs)


async def ask(query: str, **kwargs) -> dict:
    """Legacy ask function alias."""
    return await ask_question(query, **kwargs)
