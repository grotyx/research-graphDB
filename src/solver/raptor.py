"""RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval.

Hierarchical document indexing using clustering and summarization.
Creates multi-level abstraction trees for improved retrieval.

Reference:
- RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval
- Sarthi et al. (2024)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum
import hashlib

import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.cluster import KMeans

from typing import Union
from ..storage import TextChunk, SearchResult
from ..llm import LLMClient, LLMConfig, LLMResponse, ClaudeClient, GeminiClient

try:
    from ..core.exceptions import ValidationError, ProcessingError
except ImportError:
    try:
        from core.exceptions import ValidationError, ProcessingError
    except ImportError:
        ValidationError = ValueError  # type: ignore[misc,assignment]
        ProcessingError = RuntimeError  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


class ClusteringMethod(Enum):
    """Clustering algorithm options."""
    GMM = "gmm"  # Gaussian Mixture Model (default)
    KMEANS = "kmeans"  # K-Means


class RetrievalStrategy(Enum):
    """RAPTOR retrieval strategies."""
    TREE_TRAVERSAL = "tree_traversal"  # Top-down from root
    COLLAPSED = "collapsed"  # Search all levels simultaneously
    ADAPTIVE = "adaptive"  # Choose based on query complexity


@dataclass
class TreeNode:
    """Node in the RAPTOR tree.

    Attributes:
        node_id: Unique identifier for this node
        content: Text content (original chunk or abstracted summary)
        embedding: Vector embedding of the content
        level: Tree level (0=leaf/original, 1+=summary levels)
        children: Child nodes (empty for leaf nodes)
        parent: Parent node (None for root)
        is_leaf: Whether this is an original chunk (level 0)
        is_summary: Whether this is an abstracted summary (level >= 1)
        chunk_id: Original chunk ID (for leaf nodes)
        document_id: Source document ID
        metadata: Additional metadata from original chunk
    """
    node_id: str
    content: str
    embedding: list[float]
    level: int
    children: list["TreeNode"] = field(default_factory=list)
    parent: Optional["TreeNode"] = None
    is_leaf: bool = True
    is_summary: bool = False
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Auto-set is_summary based on level."""
        self.is_summary = self.level > 0
        self.is_leaf = self.level == 0

    def add_child(self, child: "TreeNode"):
        """Add a child node and set parent reference."""
        self.children.append(child)
        child.parent = self

    @property
    def num_descendants(self) -> int:
        """Count total descendants (recursive)."""
        count = len(self.children)
        for child in self.children:
            count += child.num_descendants
        return count


@dataclass
class ClusterResult:
    """Result of clustering operation.

    Attributes:
        clusters: List of clusters (each cluster is a list of node indices)
        num_clusters: Number of clusters created
        method: Clustering method used
    """
    clusters: list[list[int]]
    num_clusters: int
    method: str


class ClusteringEngine:
    """Clustering engine for RAPTOR tree construction.

    Supports GMM (Gaussian Mixture Model) and K-Means clustering.
    GMM is preferred as it provides probabilistic cluster assignments.
    """

    def __init__(
        self,
        method: ClusteringMethod = ClusteringMethod.GMM,
        min_cluster_size: int = 3,
        max_cluster_size: int = 10,
        random_state: int = 42
    ):
        """Initialize clustering engine.

        Args:
            method: Clustering algorithm (GMM or K-Means)
            min_cluster_size: Minimum chunks per cluster
            max_cluster_size: Maximum chunks per cluster
            random_state: Random seed for reproducibility
        """
        self.method = method
        self.min_cluster_size = min_cluster_size
        self.max_cluster_size = max_cluster_size
        self.random_state = random_state

    def cluster_embeddings(
        self,
        embeddings: np.ndarray,
        num_clusters: Optional[int] = None
    ) -> ClusterResult:
        """Cluster embeddings using specified method.

        Args:
            embeddings: Array of shape (n_samples, embedding_dim)
            num_clusters: Number of clusters (auto-computed if None)

        Returns:
            ClusterResult with cluster assignments
        """
        n_samples = len(embeddings)

        # Auto-compute number of clusters if not specified
        if num_clusters is None:
            num_clusters = self._compute_optimal_clusters(n_samples)

        # Handle edge cases
        if n_samples < self.min_cluster_size:
            logger.warning(f"Too few samples ({n_samples}) for clustering, using single cluster")
            return ClusterResult(
                clusters=[[i for i in range(n_samples)]],
                num_clusters=1,
                method=self.method.value
            )

        if num_clusters <= 0:
            num_clusters = 1

        # Perform clustering
        if self.method == ClusteringMethod.GMM:
            labels = self._cluster_gmm(embeddings, num_clusters)
        else:  # K-Means
            labels = self._cluster_kmeans(embeddings, num_clusters)

        # Group indices by cluster
        clusters = [[] for _ in range(num_clusters)]
        for idx, label in enumerate(labels):
            clusters[label].append(idx)

        # Filter out empty clusters
        clusters = [c for c in clusters if len(c) > 0]

        logger.info(f"Clustered {n_samples} items into {len(clusters)} clusters using {self.method.value}")

        return ClusterResult(
            clusters=clusters,
            num_clusters=len(clusters),
            method=self.method.value
        )

    def _cluster_gmm(self, embeddings: np.ndarray, num_clusters: int) -> np.ndarray:
        """Cluster using Gaussian Mixture Model.

        Args:
            embeddings: Embedding vectors
            num_clusters: Number of clusters

        Returns:
            Cluster labels for each sample
        """
        gmm = GaussianMixture(
            n_components=num_clusters,
            covariance_type='full',
            random_state=self.random_state,
            max_iter=100,
            n_init=1
        )

        try:
            labels = gmm.fit_predict(embeddings)
        except Exception as e:
            logger.warning(f"GMM clustering failed: {e}, falling back to K-Means")
            return self._cluster_kmeans(embeddings, num_clusters)

        return labels

    def _cluster_kmeans(self, embeddings: np.ndarray, num_clusters: int) -> np.ndarray:
        """Cluster using K-Means.

        Args:
            embeddings: Embedding vectors
            num_clusters: Number of clusters

        Returns:
            Cluster labels for each sample
        """
        kmeans = KMeans(
            n_clusters=num_clusters,
            random_state=self.random_state,
            n_init=10,
            max_iter=300
        )

        labels = kmeans.fit_predict(embeddings)
        return labels

    def _compute_optimal_clusters(self, n_samples: int) -> int:
        """Compute optimal number of clusters based on sample size.

        Uses heuristic: aim for average cluster size of ~5-7 items.

        Args:
            n_samples: Number of samples

        Returns:
            Optimal number of clusters
        """
        target_cluster_size = (self.min_cluster_size + self.max_cluster_size) // 2
        num_clusters = max(1, n_samples // target_cluster_size)

        # Ensure we don't exceed max cluster size
        if n_samples / num_clusters > self.max_cluster_size:
            num_clusters = max(1, n_samples // self.max_cluster_size)

        return num_clusters


class SummarizationEngine:
    """Summarization engine for creating abstracted cluster summaries.

    Uses Gemini to create abstractive summaries that preserve
    key medical facts and statistical findings.
    """

    SUMMARIZATION_PROMPT = """You are summarizing medical research content for a hierarchical knowledge base.

Create a concise, abstractive summary that:
1. Preserves ALL key medical facts, findings, and statistics
2. Maintains clinical terminology and anatomical precision
3. Synthesizes multiple chunks into coherent narrative
4. Highlights spine surgery interventions, outcomes, and evidence levels
5. Keeps PICO elements if present (Population, Intervention, Comparison, Outcome)

Content to summarize:
{content}

Return ONLY the summary text (2-3 paragraphs, 150-250 words)."""

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        gemini_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None  # 하위 호환성
    ):
        """Initialize summarization engine.

        Args:
            llm_client: LLM client (Claude 또는 Gemini, creates default if None)
            gemini_client: (Deprecated) 하위 호환성을 위한 파라미터, llm_client 사용 권장
        """
        # 하위 호환성: gemini_client가 전달되면 llm_client로 사용
        client = llm_client or gemini_client
        if client is None:
            client = LLMClient(
                config=LLMConfig(
                    temperature=0.3,  # Slightly higher for summarization
                    max_output_tokens=512
                )
            )
        self.llm = client

    async def summarize_cluster(self, chunks: list[str]) -> str:
        """Summarize a cluster of text chunks.

        Args:
            chunks: List of text chunks to summarize

        Returns:
            Abstractive summary text
        """
        if not chunks:
            return ""

        if len(chunks) == 1:
            # Single chunk - no summarization needed
            return chunks[0]

        # Combine chunks with separators
        combined = "\n\n---\n\n".join(chunks)

        # Truncate if too long (Gemini context limit)
        max_chars = 15000  # ~4000 tokens
        if len(combined) > max_chars:
            logger.warning(f"Combined chunks too long ({len(combined)} chars), truncating to {max_chars}")
            combined = combined[:max_chars] + "\n...[truncated]"

        # Generate summary
        prompt = self.SUMMARIZATION_PROMPT.format(content=combined)

        try:
            response = await self.llm.generate_text(
                prompt=prompt,
                system_instruction="You are a medical knowledge summarization expert specializing in spine surgery literature."
            )

            summary = response.text.strip()

            if not summary:
                logger.warning("Empty summary generated, using first chunk")
                return chunks[0]

            logger.info(f"Generated summary: {len(chunks)} chunks → {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Summarization failed: {e}, using fallback", exc_info=True)
            return self._fallback_summary(chunks)

    def _fallback_summary(self, chunks: list[str]) -> str:
        """Fallback summary when LLM fails.

        Simple concatenation with truncation.

        Args:
            chunks: Text chunks

        Returns:
            Concatenated text
        """
        combined = " ".join(chunks)
        max_chars = 1000

        if len(combined) > max_chars:
            combined = combined[:max_chars] + "..."

        return combined


class RAPTORTree:
    """RAPTOR tree structure for hierarchical document indexing.

    Builds a tree by recursively clustering and summarizing chunks.
    """

    def __init__(
        self,
        clustering_engine: Optional[ClusteringEngine] = None,
        summarization_engine: Optional[SummarizationEngine] = None,
        embedding_generator = None,
        max_levels: int = 5
    ):
        """Initialize RAPTOR tree.

        Args:
            clustering_engine: Clustering engine (creates default if None)
            summarization_engine: Summarization engine (creates default if None)
            embedding_generator: Embedding generator for summaries
            max_levels: Maximum tree depth (1-5 recommended for medical docs)
        """
        self.clustering_engine = clustering_engine or ClusteringEngine()
        self.summarization_engine = summarization_engine or SummarizationEngine()
        self.embedding_generator = embedding_generator
        self.max_levels = max_levels
        self.root: Optional[TreeNode] = None
        self._all_nodes: dict[str, TreeNode] = {}

    async def build_tree(self, chunks: list[TextChunk]) -> TreeNode:
        """Build RAPTOR tree from text chunks.

        Args:
            chunks: Original text chunks (level 0)

        Returns:
            Root node of the tree
        """
        if not chunks:
            raise ValidationError("Cannot build tree from empty chunk list")

        logger.info(f"Building RAPTOR tree from {len(chunks)} chunks (max_levels={self.max_levels})")

        # Create leaf nodes (level 0)
        leaf_nodes = []
        for chunk in chunks:
            node = TreeNode(
                node_id=self._generate_node_id(chunk.chunk_id, level=0),
                content=chunk.content,
                embedding=await self._get_embedding(chunk.content),
                level=0,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                metadata={
                    "section": chunk.section,
                    "tier": chunk.tier,
                    "evidence_level": chunk.evidence_level,
                    "publication_year": chunk.publication_year,
                    "title": chunk.title,
                    "is_key_finding": chunk.is_key_finding,
                }
            )
            leaf_nodes.append(node)
            self._all_nodes[node.node_id] = node

        logger.info(f"Created {len(leaf_nodes)} leaf nodes at level 0")

        # Recursively build higher levels
        current_level_nodes = leaf_nodes
        current_level = 1

        while current_level < self.max_levels:
            next_level_nodes = await self._build_level(current_level_nodes, current_level)

            if not next_level_nodes:
                logger.info(f"No more clusters to create, stopping at level {current_level-1}")
                break

            # Stop if we've converged to a single root
            if len(next_level_nodes) == 1:
                logger.info(f"Converged to single root at level {current_level}")
                self.root = next_level_nodes[0]
                break

            current_level_nodes = next_level_nodes
            current_level += 1

        # If we didn't converge to single root, create one
        if self.root is None:
            if len(current_level_nodes) > 1:
                logger.info(f"Creating synthetic root from {len(current_level_nodes)} nodes")
                self.root = await self._create_synthetic_root(current_level_nodes)
            else:
                self.root = current_level_nodes[0]

        logger.info(f"RAPTOR tree built: {len(self._all_nodes)} total nodes, max level {self.root.level}")
        return self.root

    async def _build_level(
        self,
        nodes: list[TreeNode],
        level: int
    ) -> list[TreeNode]:
        """Build a single level of the tree.

        Args:
            nodes: Nodes from previous level
            level: Current level number

        Returns:
            Nodes created at this level
        """
        if len(nodes) < self.clustering_engine.min_cluster_size:
            logger.info(f"Level {level}: Too few nodes ({len(nodes)}), stopping")
            return []

        # Extract embeddings
        embeddings = np.array([node.embedding for node in nodes])

        # Cluster nodes
        cluster_result = self.clustering_engine.cluster_embeddings(embeddings)

        if cluster_result.num_clusters <= 1:
            logger.info(f"Level {level}: Single cluster, no further abstraction needed")
            return []

        logger.info(f"Level {level}: Created {cluster_result.num_clusters} clusters")

        # Create summary nodes for each cluster
        summary_nodes = []
        for cluster_idx, cluster_indices in enumerate(cluster_result.clusters):
            cluster_nodes = [nodes[i] for i in cluster_indices]

            # Summarize cluster
            cluster_texts = [node.content for node in cluster_nodes]
            summary_text = await self.summarization_engine.summarize_cluster(cluster_texts)

            # Create summary node
            summary_node = TreeNode(
                node_id=self._generate_node_id(f"cluster_{cluster_idx}", level=level),
                content=summary_text,
                embedding=await self._get_embedding(summary_text),
                level=level,
                document_id=cluster_nodes[0].document_id,  # Inherit from first child
                metadata={
                    "cluster_size": len(cluster_nodes),
                    "cluster_method": cluster_result.method,
                }
            )

            # Link children to parent
            for child_node in cluster_nodes:
                summary_node.add_child(child_node)

            summary_nodes.append(summary_node)
            self._all_nodes[summary_node.node_id] = summary_node

        logger.info(f"Level {level}: Created {len(summary_nodes)} summary nodes")
        return summary_nodes

    async def _create_synthetic_root(self, nodes: list[TreeNode]) -> TreeNode:
        """Create synthetic root node from multiple top-level nodes.

        Args:
            nodes: Top-level nodes to combine

        Returns:
            Synthetic root node
        """
        # Summarize all top-level nodes
        texts = [node.content for node in nodes]
        root_summary = await self.summarization_engine.summarize_cluster(texts)

        root = TreeNode(
            node_id=self._generate_node_id("root", level=nodes[0].level + 1),
            content=root_summary,
            embedding=await self._get_embedding(root_summary),
            level=nodes[0].level + 1,
            document_id=nodes[0].document_id,
            metadata={"synthetic_root": True}
        )

        for node in nodes:
            root.add_child(node)

        self._all_nodes[root.node_id] = root
        return root

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if self.embedding_generator is None:
            # v1.14.26: OpenAI 임베딩 사용 (3072d - Neo4j 인덱스와 일치)
            try:
                from ..core.embedding import OpenAIEmbeddingGenerator
                self.embedding_generator = OpenAIEmbeddingGenerator()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to init OpenAI embedding: {e}")
                raise ProcessingError("OpenAI embedding required for RAPTOR (3072d index)")

        return self.embedding_generator.embed(text)

    def _generate_node_id(self, base_id: str, level: int) -> str:
        """Generate unique node ID.

        Args:
            base_id: Base identifier
            level: Tree level

        Returns:
            Unique node ID
        """
        combined = f"{base_id}_L{level}"
        hash_suffix = hashlib.sha256(combined.encode()).hexdigest()[:8]
        return f"raptor_{hash_suffix}"

    def get_all_nodes(self) -> list[TreeNode]:
        """Get all nodes in the tree."""
        return list(self._all_nodes.values())

    def get_nodes_at_level(self, level: int) -> list[TreeNode]:
        """Get all nodes at a specific level."""
        return [node for node in self._all_nodes.values() if node.level == level]


class RAPTORRetriever:
    """RAPTOR-based retrieval system.

    Implements multiple retrieval strategies over hierarchical trees.
    """

    def __init__(
        self,
        tree: RAPTORTree,
        embedding_generator = None
    ):
        """Initialize RAPTOR retriever.

        Args:
            tree: RAPTOR tree to search
            embedding_generator: Embedding generator for queries
        """
        self.tree = tree
        self.embedding_generator = embedding_generator

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        strategy: RetrievalStrategy = RetrievalStrategy.COLLAPSED
    ) -> list[tuple[TreeNode, float]]:
        """Retrieve relevant nodes for a query.

        Args:
            query: Query text
            top_k: Number of results to return
            strategy: Retrieval strategy

        Returns:
            List of (node, score) tuples, sorted by relevance
        """
        # Get query embedding
        # v1.14.26: OpenAI 임베딩 사용 (3072d - Neo4j 인덱스와 일치)
        if self.embedding_generator is None:
            try:
                from ..core.embedding import OpenAIEmbeddingGenerator
                self.embedding_generator = OpenAIEmbeddingGenerator()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to init OpenAI embedding: {e}")
                raise ProcessingError("OpenAI embedding required for RAPTOR retrieval (3072d index)")

        query_embedding = self.embedding_generator.embed(query)

        # Apply retrieval strategy
        if strategy == RetrievalStrategy.TREE_TRAVERSAL:
            results = self._retrieve_tree_traversal(query_embedding, top_k)
        elif strategy == RetrievalStrategy.COLLAPSED:
            results = self._retrieve_collapsed(query_embedding, top_k)
        else:  # ADAPTIVE
            results = self._retrieve_adaptive(query, query_embedding, top_k)

        return results

    def _retrieve_tree_traversal(
        self,
        query_embedding: list[float],
        top_k: int
    ) -> list[tuple[TreeNode, float]]:
        """Top-down tree traversal retrieval.

        Starts from root, expands most relevant branches.

        Args:
            query_embedding: Query vector
            top_k: Number of results

        Returns:
            Relevant nodes with scores
        """
        if self.tree.root is None:
            return []

        # Start from root
        frontier = [(self.tree.root, self._cosine_similarity(query_embedding, self.tree.root.embedding))]
        results = []

        while frontier and len(results) < top_k:
            # Pop most relevant node
            frontier.sort(key=lambda x: x[1], reverse=True)
            node, score = frontier.pop(0)

            # Add to results
            results.append((node, score))

            # Expand children
            for child in node.children:
                child_score = self._cosine_similarity(query_embedding, child.embedding)
                frontier.append((child, child_score))

        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _retrieve_collapsed(
        self,
        query_embedding: list[float],
        top_k: int
    ) -> list[tuple[TreeNode, float]]:
        """Collapsed retrieval across all levels.

        Searches all nodes simultaneously, regardless of level.

        Args:
            query_embedding: Query vector
            top_k: Number of results

        Returns:
            Relevant nodes with scores
        """
        all_nodes = self.tree.get_all_nodes()

        # Score all nodes
        scored_nodes = []
        for node in all_nodes:
            score = self._cosine_similarity(query_embedding, node.embedding)
            scored_nodes.append((node, score))

        # Sort by score
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        return scored_nodes[:top_k]

    def _retrieve_adaptive(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int
    ) -> list[tuple[TreeNode, float]]:
        """Adaptive retrieval based on query complexity.

        Simple queries → prefer higher-level summaries
        Complex queries → prefer leaf nodes with details

        Args:
            query: Query text
            query_embedding: Query vector
            top_k: Number of results

        Returns:
            Relevant nodes with scores
        """
        # Assess query complexity (simple heuristic)
        query_words = query.lower().split()

        # Check for detail-seeking keywords
        detail_keywords = {'statistical', 'data', 'p-value', 'specific', 'exact', 'number', 'percentage'}
        is_complex_query = any(kw in query_words for kw in detail_keywords)

        if is_complex_query:
            # Prefer leaf nodes (detailed content)
            leaf_nodes = self.tree.get_nodes_at_level(0)
            scored_nodes = [
                (node, self._cosine_similarity(query_embedding, node.embedding))
                for node in leaf_nodes
            ]
        else:
            # Prefer higher-level summaries
            summary_nodes = [node for node in self.tree.get_all_nodes() if node.level > 0]
            scored_nodes = [
                (node, self._cosine_similarity(query_embedding, node.embedding) * (1 + 0.1 * node.level))
                for node in summary_nodes
            ]

        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        return scored_nodes[:top_k]

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between vectors."""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)

        dot_product = np.dot(vec1_np, vec2_np)
        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))


class RAPTORPipeline:
    """End-to-end RAPTOR pipeline.

    Integrates tree building, storage, and retrieval.
    """

    def __init__(
        self,
        vector_db = None,
        config: Optional[dict] = None,
        summarization_engine: Optional[SummarizationEngine] = None
    ):
        """Initialize RAPTOR pipeline.

        Args:
            vector_db: Vector database for storage
            config: Configuration dictionary
            summarization_engine: Summarization engine (creates default if None)
        """
        self.vector_db = vector_db
        self.config = config or {}

        # Initialize components
        self.clustering_engine = ClusteringEngine(
            method=ClusteringMethod.GMM,
            min_cluster_size=self.config.get("min_cluster_size", 3),
            max_cluster_size=self.config.get("max_cluster_size", 10)
        )

        self.summarization_engine = summarization_engine or SummarizationEngine()

        self.tree = RAPTORTree(
            clustering_engine=self.clustering_engine,
            summarization_engine=self.summarization_engine,
            max_levels=self.config.get("max_levels", 5)
        )

        self.retriever: Optional[RAPTORRetriever] = None

        # Tree storage
        self._trees: dict[str, RAPTORTree] = {}  # document_id -> tree

    async def index_documents(self, chunks: list[TextChunk]) -> str:
        """Build RAPTOR tree and index documents.

        Args:
            chunks: Text chunks to index

        Returns:
            Document ID of the indexed tree
        """
        if not chunks:
            raise ValidationError("Cannot index empty chunk list")

        # Build tree
        root = await self.tree.build_tree(chunks)

        # Store tree by document ID
        document_id = chunks[0].document_id
        self._trees[document_id] = self.tree

        # Initialize retriever
        self.retriever = RAPTORRetriever(self.tree)

        # Store in vector DB if provided
        if self.vector_db is not None:
            await self._store_tree_in_vectordb(document_id)

        logger.info(f"Indexed document {document_id} with {len(self.tree.get_all_nodes())} nodes")
        return document_id

    async def search(
        self,
        query: str,
        top_k: int = 10,
        strategy: RetrievalStrategy = RetrievalStrategy.COLLAPSED
    ) -> list[dict]:
        """Search for relevant content.

        Args:
            query: Search query
            top_k: Number of results
            strategy: Retrieval strategy

        Returns:
            Search results with metadata
        """
        if self.retriever is None:
            raise ValidationError("No documents indexed yet")

        # Retrieve nodes
        results = await self.retriever.retrieve(query, top_k, strategy)

        # Format results
        formatted_results = []
        for node, score in results:
            formatted_results.append({
                "node_id": node.node_id,
                "content": node.content,
                "score": score,
                "level": node.level,
                "is_leaf": node.is_leaf,
                "is_summary": node.is_summary,
                "chunk_id": node.chunk_id,
                "document_id": node.document_id,
                "metadata": node.metadata,
            })

        return formatted_results

    async def get_context(
        self,
        query: str,
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.ADAPTIVE
    ) -> str:
        """Get hierarchical context for LLM.

        Args:
            query: Query for context retrieval
            max_tokens: Maximum context length (~4 chars per token)
            strategy: Retrieval strategy

        Returns:
            Formatted context string
        """
        max_chars = max_tokens * 4

        # Search for relevant nodes
        results = await self.search(query, top_k=20, strategy=strategy)

        # Build hierarchical context
        context_parts = []
        total_chars = 0

        for result in results:
            level_prefix = "  " * result["level"]
            level_label = f"[Level {result['level']}]" if result["is_summary"] else "[Original]"

            part = f"{level_prefix}{level_label} {result['content'][:500]}\n\n"

            if total_chars + len(part) > max_chars:
                break

            context_parts.append(part)
            total_chars += len(part)

        context = "".join(context_parts)
        logger.info(f"Generated context: {total_chars} chars from {len(context_parts)} nodes")

        return context

    async def _store_tree_in_vectordb(self, document_id: str):
        """Store RAPTOR tree nodes in vector database.

        Args:
            document_id: Document identifier
        """
        # Store all nodes with level metadata
        all_nodes = self.tree.get_all_nodes()

        # Convert to TextChunk format
        chunks = []
        embeddings = []

        for node in all_nodes:
            chunk = TextChunk(
                chunk_id=node.node_id,
                content=node.content,
                document_id=document_id,
                tier="tier1" if node.level <= 1 else "tier2",
                section=f"raptor_level_{node.level}",
                source_type="original" if node.is_leaf else "background",
                evidence_level=node.metadata.get("evidence_level", "5"),
                publication_year=node.metadata.get("publication_year", 0),
                title=node.metadata.get("title", ""),
                metadata={
                    "raptor_level": node.level,
                    "is_summary": node.is_summary,
                    "num_descendants": node.num_descendants,
                }
            )
            chunks.append(chunk)
            embeddings.append(node.embedding)

        # Store in appropriate tier
        tier1_chunks = [c for c in chunks if c.tier == "tier1"]
        tier1_embeddings = [e for c, e in zip(chunks, embeddings) if c.tier == "tier1"]

        tier2_chunks = [c for c in chunks if c.tier == "tier2"]
        tier2_embeddings = [e for c, e in zip(chunks, embeddings) if c.tier == "tier2"]

        if tier1_chunks:
            self.vector_db.add_documents("tier1", tier1_chunks, tier1_embeddings)

        if tier2_chunks:
            self.vector_db.add_documents("tier2", tier2_chunks, tier2_embeddings)

        logger.info(f"Stored tree in VectorDB: {len(tier1_chunks)} tier1, {len(tier2_chunks)} tier2")
