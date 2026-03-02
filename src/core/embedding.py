"""Embedding module for generating text embeddings.

Supports:
- OpenAI text-embedding-3-large (3072 dimensions) - PRIMARY
- MedTE (768 dimensions) - LEGACY
- SentenceTransformers models
"""

import os
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generator, Optional

if TYPE_CHECKING:
    from .text_chunker import Chunk

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Primary embedding model (OpenAI)
OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
OPENAI_EMBEDDING_DIM = 3072

# Legacy embedding model (MedTE)
MEDTE_MODEL = "MohammadKhodadad/MedTE-cl15-step-8000"
MEDTE_EMBEDDING_DIM = 768

# Default: Use OpenAI
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai")
DEFAULT_EMBEDDING_DIM = OPENAI_EMBEDDING_DIM if DEFAULT_EMBEDDING_MODEL == "openai" else MEDTE_EMBEDDING_DIM


@dataclass
class EmbeddedChunk:
    """A chunk with its embedding vector."""
    chunk: "Chunk"
    embedding: list[float]
    model_name: str


# =============================================================================
# OpenAI Embedding Generator
# =============================================================================

class OpenAIEmbeddingGenerator:
    """Generate embeddings using OpenAI text-embedding-3-large (3072 dimensions)."""

    MODEL = OPENAI_EMBEDDING_MODEL
    DIMENSION = OPENAI_EMBEDDING_DIM

    def __init__(self, batch_size: int = 20):
        """Initialize OpenAI embedding generator.

        Args:
            batch_size: Number of texts to embed per API call (max 2048)
        """
        import openai
        self.client = openai.OpenAI()
        self.batch_size = min(batch_size, 2048)  # OpenAI limit
        self.model_name = self.MODEL
        logger.info(f"OpenAI Embedding initialized: {self.MODEL} ({self.DIMENSION}d)")

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        text = self._preprocess(text)
        response = self.client.embeddings.create(
            input=[text],
            model=self.MODEL
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        CA-NEW-007: Per-batch error handling with partial result support.
        If a batch fails, logs the error and raises with info about
        how many embeddings were successfully generated.
        """
        if not texts:
            return []

        all_embeddings = []
        processed = [self._preprocess(t) for t in texts]
        total_batches = (len(processed) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(processed), self.batch_size):
            batch = processed[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1

            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.MODEL
                )

                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                if total_batches > 1:
                    logger.debug(f"Embedded batch {batch_num}/{total_batches}")
            except Exception as e:
                logger.error(
                    f"Embedding batch {batch_num}/{total_batches} failed "
                    f"({len(all_embeddings)}/{len(processed)} completed): {e}",
                    exc_info=True,
                )
                raise

        return all_embeddings

    def embed_chunks(self, chunks: list["Chunk"]) -> list[EmbeddedChunk]:
        """Generate embeddings for a list of chunks."""
        if not chunks:
            return []

        texts = [chunk.content for chunk in chunks]
        embeddings = self.embed_batch(texts)

        return [
            EmbeddedChunk(chunk=chunk, embedding=embedding, model_name=self.model_name)
            for chunk, embedding in zip(chunks, embeddings)
        ]

    def _preprocess(self, text: str) -> str:
        """Preprocess text before embedding."""
        text = " ".join(text.split())
        # OpenAI supports up to 8191 tokens (~32K chars)
        max_chars = 30000
        if len(text) > max_chars:
            text = text[:max_chars]
        return text

    @property
    def embedding_dimension(self) -> int:
        """Get the dimension of embeddings."""
        return self.DIMENSION

    def get_model_info(self) -> dict:
        """Get information about the model."""
        return {
            "model_name": self.MODEL,
            "embedding_dimension": self.DIMENSION,
            "provider": "openai",
            "max_tokens": 8191
        }


# =============================================================================
# SentenceTransformers Embedding Generator (Legacy/MedTE)
# =============================================================================

class EmbeddingGenerator:
    """Generate embeddings for text using sentence-transformers."""

    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        batch_size: int = 32
    ):
        """
        Initialize the embedding generator.

        Args:
            model_name: HuggingFace model name
            device: Device to run on ("cpu" or "cuda")
            batch_size: Batch size for processing
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self.batch_size = batch_size
        self._model = None

    def _load_model(self):
        """Load the model lazily on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device
            )
            self._model.eval()

        return self._model

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        text = self._preprocess(text)
        model = self._load_model()

        embedding = model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        model = self._load_model()

        # Preprocess all texts
        processed = [self._preprocess(t) for t in texts]

        embeddings = []

        # Process in batches
        for i in range(0, len(processed), self.batch_size):
            batch = processed[i:i + self.batch_size]

            batch_embeddings = model.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            embeddings.extend(batch_embeddings.tolist())

        return embeddings

    def embed_chunks(self, chunks: list["Chunk"]) -> list[EmbeddedChunk]:
        """
        Generate embeddings for a list of chunks.

        Args:
            chunks: List of Chunk objects

        Returns:
            List of EmbeddedChunk objects
        """
        if not chunks:
            return []

        # Extract texts
        texts = [chunk.content for chunk in chunks]

        # Generate embeddings
        embeddings = self.embed_batch(texts)

        # Create EmbeddedChunk objects
        embedded_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            embedded_chunks.append(EmbeddedChunk(
                chunk=chunk,
                embedding=embedding,
                model_name=self.model_name
            ))

        return embedded_chunks

    def embed_large_corpus(
        self,
        texts: list[str]
    ) -> Generator[list[list[float]], None, None]:
        """
        Generate embeddings for a large corpus using a generator.

        Args:
            texts: List of texts to embed

        Yields:
            Batches of embedding vectors
        """
        model = self._load_model()

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            processed = [self._preprocess(t) for t in batch]

            batch_embeddings = model.encode(
                processed,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            yield batch_embeddings.tolist()

            # Clear GPU memory if using CUDA
            if self.device == "cuda":
                import torch
                torch.cuda.empty_cache()

    def _preprocess(self, text: str) -> str:
        """
        Preprocess text before embedding.

        Args:
            text: Raw text

        Returns:
            Preprocessed text
        """
        # Normalize whitespace
        text = " ".join(text.split())

        # Truncate if too long (model max_seq_length)
        # Most models have 512 token limit, ~4 chars per token
        max_chars = 2048
        if len(text) > max_chars:
            text = text[:max_chars]

        return text

    @property
    def embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by the model."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()

    def get_model_info(self) -> dict:
        """Get information about the loaded model."""
        model = self._load_model()
        return {
            "model_name": self.model_name,
            "embedding_dimension": model.get_sentence_embedding_dimension(),
            "max_seq_length": model.max_seq_length,
            "device": str(self.device)
        }


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score (0-1 for normalized vectors)
    """
    import math

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


# =============================================================================
# Factory Function
# =============================================================================

def get_embedding_generator(
    model_type: Optional[str] = None,
    **kwargs
) -> OpenAIEmbeddingGenerator | EmbeddingGenerator:
    """Get the appropriate embedding generator based on configuration.

    Args:
        model_type: "openai" or "medte" or "sentence-transformers"
                   If None, uses EMBEDDING_MODEL env var (default: openai)
        **kwargs: Additional arguments for the generator

    Returns:
        Embedding generator instance

    Example:
        # Use OpenAI (default)
        generator = get_embedding_generator()

        # Use MedTE
        generator = get_embedding_generator("medte")

        # Use custom model
        generator = get_embedding_generator("sentence-transformers", model_name="...")
    """
    model_type = model_type or DEFAULT_EMBEDDING_MODEL

    if model_type == "openai":
        return OpenAIEmbeddingGenerator(**kwargs)
    elif model_type == "medte":
        return EmbeddingGenerator(model_name=MEDTE_MODEL, **kwargs)
    else:
        return EmbeddingGenerator(**kwargs)


def get_embedding_dimension(model_type: Optional[str] = None) -> int:
    """Get the embedding dimension for a given model type.

    Args:
        model_type: "openai" or "medte"

    Returns:
        Embedding dimension (3072 for OpenAI, 768 for MedTE)
    """
    model_type = model_type or DEFAULT_EMBEDDING_MODEL

    if model_type == "openai":
        return OPENAI_EMBEDDING_DIM
    else:
        return MEDTE_EMBEDDING_DIM
