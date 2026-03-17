"""PubMed Processing/Transformation Module.

PubMed 논문의 LLM 처리, 청크 생성, Neo4j 저장, JSON 추출 등
데이터 변환/처리 기능을 제공합니다.
pubmed_bulk_processor.py에서 분리된 모듈입니다 (D-009).

Usage:
    processor = PubMedPaperProcessor(
        neo4j_client, embedding_generator, vision_processor,
        entity_normalizer, relationship_builder
    )
    chunks, success, data = await processor.process_fulltext_with_llm(...)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

try:
    from builder.pubmed_enricher import BibliographicMetadata
    from builder.pmc_fulltext_fetcher import PMCFullText
    from builder.unified_pdf_processor import UnifiedPDFProcessor, ProcessorResult, ExtractedMetadata
    from graph.spine_schema import PaperNode
    from graph.relationship_builder import RelationshipBuilder, SpineMetadata
    from graph.entity_normalizer import EntityNormalizer
    from core.embedding import EmbeddingGenerator, apply_context_prefix
    from storage import TextChunk
except ImportError:
    try:
        from src.builder.pubmed_enricher import BibliographicMetadata
        from src.builder.pmc_fulltext_fetcher import PMCFullText
        from src.builder.unified_pdf_processor import UnifiedPDFProcessor, ProcessorResult, ExtractedMetadata
        from src.graph.spine_schema import PaperNode
        from src.graph.relationship_builder import RelationshipBuilder, SpineMetadata
        from src.graph.entity_normalizer import EntityNormalizer
        from src.core.embedding import EmbeddingGenerator, apply_context_prefix
        from src.storage import TextChunk
    except ImportError:
        UnifiedPDFProcessor = None
        EntityNormalizer = None

try:
    from graph.types.enums import normalize_study_design
except ImportError:
    try:
        from src.graph.types.enums import normalize_study_design
    except ImportError:
        def normalize_study_design(raw: str) -> str:  # type: ignore[misc]
            return raw  # fallback: no-op

if TYPE_CHECKING:
    from src.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Paper ID prefix for PubMed-only papers
PUBMED_PAPER_PREFIX = "pubmed_"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AbstractChunk:
    """초록에서 생성된 청크.

    Attributes:
        chunk_id: 청크 ID
        content: 청크 내용
        section: 섹션 (background, methods, results, conclusions, full)
        metadata: 메타데이터
    """
    chunk_id: str
    content: str
    section: str = "abstract"
    metadata: dict = field(default_factory=dict)


class PubMedPaperProcessor:
    """PubMed 논문 처리/변환 담당.

    LLM 기반 텍스트 분석, Neo4j 관계 구축, 청크 생성/저장 등을 처리합니다.
    """

    def __init__(
        self,
        neo4j_client: "Neo4jClient",
        embedding_generator: Any,
        vision_processor: Optional[UnifiedPDFProcessor],
        entity_normalizer: EntityNormalizer,
        relationship_builder: RelationshipBuilder,
    ):
        """PubMedPaperProcessor 초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
            embedding_generator: 임베딩 생성기
            vision_processor: LLM 처리기
            entity_normalizer: 엔티티 정규화기
            relationship_builder: 관계 구축기
        """
        self.neo4j = neo4j_client
        self.embedding_generator = embedding_generator
        self.vision_processor = vision_processor
        self.entity_normalizer = entity_normalizer
        self.relationship_builder = relationship_builder
        self._openai_client = None

    # =========================================================================
    # Neo4j Paper Node Creation
    # =========================================================================

    async def create_paper_node(
        self,
        metadata: BibliographicMetadata,
    ) -> bool:
        """PubMed 메타데이터로 Neo4j Paper 노드 생성.

        Args:
            metadata: PubMed 서지 정보

        Returns:
            성공 여부
        """
        paper_id = f"{PUBMED_PAPER_PREFIX}{metadata.pmid}"

        properties = {
            "paper_id": paper_id,
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "journal": metadata.journal,
            "journal_abbrev": metadata.journal_abbrev,
            "doi": metadata.doi or "",
            "pmid": metadata.pmid or "",
            "abstract": metadata.abstract[:2000] if metadata.abstract else "",
            "mesh_terms": metadata.mesh_terms[:20],
            "publication_types": metadata.publication_types[:10],
            "evidence_level": infer_evidence_level(metadata.publication_types),
            "source": "pubmed",
            "is_abstract_only": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        cypher = """
        MERGE (p:Paper {paper_id: $paper_id})
        SET p += $properties
        RETURN p.paper_id AS paper_id
        """

        try:
            result = await self.neo4j.run_query(cypher, {
                "paper_id": paper_id,
                "properties": properties,
            })
            logger.debug(f"Created/updated Paper node: {paper_id}")

            if metadata.abstract and len(metadata.abstract.strip()) > 0:
                await self._generate_abstract_embedding(paper_id, metadata.abstract)

            return True
        except Exception as e:
            logger.error(f"Failed to create Paper node: {e}", exc_info=True)
            return False

    async def _generate_abstract_embedding(
        self,
        paper_id: str,
        abstract: str
    ) -> bool:
        """Paper의 abstract 임베딩 생성 및 저장."""
        try:
            from openai import OpenAI

            if self._openai_client is None:
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = self._openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=abstract[:8000],
                dimensions=3072
            )

            embedding = response.data[0].embedding

            await self.neo4j.run_write_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """,
                {"paper_id": paper_id, "embedding": embedding}
            )

            logger.debug(f"Abstract embedding generated for {paper_id}")
            return True

        except ImportError:
            logger.warning("OpenAI package not installed, skipping abstract embedding")
            return False
        except Exception as e:
            logger.warning(f"Failed to generate abstract embedding for {paper_id}: {e}")
            return False

    # =========================================================================
    # LLM Processing Methods
    # =========================================================================

    async def process_fulltext_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        fulltext: PMCFullText,
        owner: str = "system",
        shared: bool = True,
    ) -> tuple[int, bool, Optional[dict]]:
        """PMC 전문을 LLM으로 처리하고 Neo4j 관계를 구축.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            fulltext: PMC 전문 데이터
            owner: 소유자 ID
            shared: 공유 여부

        Returns:
            (chunks_created, success, extracted_data) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        full_text = fulltext.full_text
        if not full_text or len(full_text) < 500:
            logger.warning(f"Full text too short for LLM processing: {len(full_text)} chars")
            return 0, False, None

        logger.info(f"Processing PMC full text with LLM ({len(full_text)} chars)")

        # CA-NEW-005: retry logic for transient LLM failures
        max_retries = 2
        result: Optional[ProcessorResult] = None
        for attempt in range(max_retries + 1):
            try:
                result = await self.vision_processor.process_text(
                    text=full_text,
                    title=paper.title,
                    source="pmc",
                )
                if result.success:
                    break
                if attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt + 1} failed: {result.error}, retrying...")
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"LLM attempt {attempt + 1} exception: {e}, retrying...")
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
                else:
                    logger.error(f"LLM processing failed after {max_retries + 1} attempts: {e}", exc_info=True)
                    return 0, False, None

        if not result or not result.success:
            logger.warning(f"LLM text processing failed after {max_retries + 1} attempts: {getattr(result, 'error', 'unknown')}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from LLM processing")
            return 0, False, None

        logger.info(f"LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        metadata_dict = extracted_data.get("metadata") or {}
        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        # Neo4j 관계 구축
        graph_spine_meta = None
        try:
            graph_spine_meta = _build_spine_metadata(spine_meta)

            inferred_evidence = infer_evidence_level(paper.publication_types)
            extracted_metadata = _build_extracted_metadata(
                metadata_dict, paper, inferred_evidence,
                abstract=paper.abstract or "",
            )

            build_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=extracted_metadata,
                spine_metadata=graph_spine_meta,
                chunks=chunks_data,
                owner=owner,
                shared=shared,
            )

            logger.info(
                f"Neo4j relationships built: {build_result.nodes_created} nodes, "
                f"{build_result.relationships_created} relations"
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships: {e}")

        chunks_created = await self.store_llm_chunks(
            paper_id=paper_id,
            paper=paper,
            chunks_data=chunks_data,
            pmcid=fulltext.pmcid or "",
        )

        # v1.25.0: Chunk→Entity MENTIONS 관계 생성
        if graph_spine_meta:
            await self._create_chunk_mentions(paper_id, graph_spine_meta)

        return chunks_created, True, extracted_data

    async def process_abstract_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        owner: str = "system",
        shared: bool = True,
    ) -> tuple[int, bool, Optional[dict]]:
        """Abstract를 LLM으로 분석하고 Neo4j 관계를 구축.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            owner: 소유자 ID
            shared: 공유 여부

        Returns:
            (chunks_created, success, extracted_data) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        abstract = paper.abstract
        if not abstract or len(abstract) < 100:
            logger.debug(f"Abstract too short for LLM processing: {len(abstract) if abstract else 0} chars")
            return 0, False, None

        logger.info(f"Processing abstract with LLM ({len(abstract)} chars)")

        result: ProcessorResult = await self.vision_processor.process_text(
            text=abstract,
            title=paper.title,
            source="pubmed_abstract",
        )

        if not result.success:
            logger.warning(f"LLM abstract processing failed: {result.error}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from abstract LLM processing")
            return 0, False, None

        logger.info(f"Abstract LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        metadata_dict = extracted_data.get("metadata") or {}
        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        # Neo4j 관계 구축
        graph_spine_meta = None
        try:
            graph_spine_meta = _build_spine_metadata(spine_meta)

            inferred_evidence = infer_evidence_level(paper.publication_types)
            extracted_metadata = _build_extracted_metadata(
                metadata_dict, paper, inferred_evidence,
                abstract=abstract,
            )

            build_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=extracted_metadata,
                spine_metadata=graph_spine_meta,
                chunks=chunks_data,
                owner=owner,
                shared=shared,
            )

            logger.info(
                f"Neo4j relationships built from abstract: {build_result.nodes_created} nodes, "
                f"{build_result.relationships_created} relations"
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships from abstract: {e}")

        # 청크 저장
        if chunks_data:
            chunks_created = await self.store_llm_chunks(
                paper_id=paper_id,
                paper=paper,
                chunks_data=chunks_data,
                pmcid="",
            )
        else:
            chunks_created = await self.chunk_abstract(
                paper_id=paper_id,
                abstract=abstract,
                metadata=build_chunk_metadata(paper),
            )

        # v1.25.0: Chunk→Entity MENTIONS 관계 생성
        if graph_spine_meta:
            await self._create_chunk_mentions(paper_id, graph_spine_meta)

        return chunks_created, True, extracted_data

    async def process_text_with_llm(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        text: str,
        owner: str = "system",
        shared: bool = True,
    ) -> tuple[int, bool, Optional[dict]]:
        """일반 텍스트(DOI/Unpaywall 등)를 LLM으로 처리.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            text: 처리할 전문 텍스트
            owner: 소유자 ID
            shared: 공유 여부

        Returns:
            (chunks_created, success, extracted_data) 튜플
        """
        if not self.vision_processor:
            return 0, False, None

        if not text or len(text) < 100:
            logger.debug(f"Text too short for LLM processing: {len(text) if text else 0} chars")
            return 0, False, None

        logger.info(f"[DOI/Unpaywall] Processing text with LLM ({len(text)} chars)")

        result: ProcessorResult = await self.vision_processor.process_text(
            text=text,
            title=paper.title,
            source="doi_fulltext",
        )

        if not result.success:
            logger.warning(f"LLM text processing failed: {result.error}")
            return 0, False, None

        extracted_data = result.extracted_data
        if not extracted_data:
            logger.warning("No data extracted from text LLM processing")
            return 0, False, None

        logger.info(f"Text LLM processing successful (input={result.input_tokens}, output={result.output_tokens})")

        spine_meta = extracted_data.get("spine_metadata") or {}
        chunks_data = extracted_data.get("chunks") or []

        graph_spine_meta = None
        try:
            graph_spine_meta = _build_spine_metadata(spine_meta)

            metadata_dict = extracted_data.get("metadata") or {}
            inferred_evidence = infer_evidence_level(paper.publication_types)
            extracted_metadata = _build_extracted_metadata(
                metadata_dict, paper, inferred_evidence,
                abstract=paper.abstract or "",
            )

            build_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=extracted_metadata,
                spine_metadata=graph_spine_meta,
                chunks=chunks_data,
                owner=owner,
                shared=shared,
            )

            logger.info(
                f"Neo4j relationships built (DOI/text): {build_result.nodes_created} nodes, "
                f"{build_result.relationships_created} relations"
            )
        except Exception as e:
            logger.warning(f"Failed to build Neo4j relationships: {e}")

        chunks_created = await self.store_llm_chunks(
            paper_id=paper_id,
            paper=paper,
            chunks_data=chunks_data,
            pmcid="",
        )

        # v1.25.0: Chunk→Entity MENTIONS 관계 생성
        if graph_spine_meta:
            await self._create_chunk_mentions(paper_id, graph_spine_meta)

        return chunks_created, True, extracted_data

    # =========================================================================
    # Chunk Storage Methods
    # =========================================================================

    async def _create_chunk_mentions(self, paper_id: str, spine_meta) -> int:
        """Chunk→Entity MENTIONS 관계 생성 (v1.25.0)."""
        if not self.relationship_builder:
            return 0
        try:
            return await self.relationship_builder.create_chunk_mentions(paper_id, spine_meta)
        except Exception as e:
            logger.warning(f"Chunk MENTIONS creation failed: {e}")
            return 0

    async def store_llm_chunks(
        self,
        paper_id: str,
        paper: BibliographicMetadata,
        chunks_data: list[dict],
        pmcid: str,
    ) -> int:
        """LLM에서 추출된 청크를 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            paper: 서지 메타데이터
            chunks_data: LLM에서 추출된 청크 목록
            pmcid: PubMed Central ID

        Returns:
            저장된 청크 수
        """
        if not chunks_data:
            return 0

        text_chunks = []
        base_metadata = build_chunk_metadata(paper)

        for idx, chunk_dict in enumerate(chunks_data):
            content = chunk_dict.get("content", "")
            if not content or len(content) < 30:
                continue

            section_type = chunk_dict.get("section_type", "other")
            tier = chunk_dict.get("tier", "tier2")
            content_type = chunk_dict.get("content_type", "text")

            chunk_id = f"{paper_id}_{section_type}_{idx}"

            stats = chunk_dict.get("statistics") or {}

            text_chunks.append(TextChunk(
                chunk_id=chunk_id,
                content=content,
                document_id=paper_id,
                tier=tier,
                section=section_type,
                source_type="pmc_llm",
                evidence_level=base_metadata.get("evidence_level", "5"),
                publication_year=base_metadata.get("publication_year", 0),
                page_num=0,
                title=base_metadata.get("title", ""),
                authors=base_metadata.get("authors", []),
                metadata={
                    **base_metadata,
                    "source": "pmc_fulltext_llm",
                    "pmcid": pmcid,
                    "is_abstract_only": False,
                    "content_type": content_type,
                    "summary": chunk_dict.get("summary", ""),
                    "is_key_finding": chunk_dict.get("is_key_finding", False),
                    "p_value": stats.get("p_value", ""),
                    "is_significant": stats.get("is_significant", False),
                },
            ))

        if not text_chunks:
            return 0

        contents = [c.content for c in text_chunks]
        # Contextual embedding prefix: prepend [title | section | year] for richer embeddings
        prefixed = apply_context_prefix(
            contents,
            title=base_metadata.get("title", ""),
            sections=[c.section for c in text_chunks],
            year=base_metadata.get("publication_year", 0),
        )
        embeddings = self.embedding_generator.embed_batch(prefixed)

        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)

        tier1_count = sum(1 for c in text_chunks if c.tier == "tier1")
        tier2_count = sum(1 for c in text_chunks if c.tier == "tier2")
        logger.info(f"Stored {total_added} chunks from LLM processing (tier1: {tier1_count}, tier2: {tier2_count})")
        return total_added

    async def chunk_abstract(
        self,
        paper_id: str,
        abstract: str,
        metadata: dict,
    ) -> int:
        """초록을 청크로 분할하여 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            abstract: 초록 텍스트
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not abstract or not abstract.strip():
            return 0

        chunks = parse_structured_abstract(paper_id, abstract, metadata)

        if not chunks:
            chunk_id = f"{paper_id}_abstract_0"
            chunks = [AbstractChunk(
                chunk_id=chunk_id,
                content=abstract.strip(),
                section="abstract",
                metadata=metadata,
            )]

        contents = [c.content for c in chunks]
        # Contextual embedding prefix for abstract chunks
        prefixed = apply_context_prefix(
            contents,
            title=metadata.get("title", ""),
            sections=[c.section for c in chunks],
            year=metadata.get("publication_year", 0),
        )
        embeddings = self.embedding_generator.embed_batch(prefixed)

        text_chunks = []
        for chunk in chunks:
            text_chunk = TextChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                document_id=paper_id,
                tier="tier1",
                section=chunk.section,
                source_type="pubmed",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **chunk.metadata,
                    "source": "pubmed",
                    "is_abstract_only": True,
                },
            )
            text_chunks.append(text_chunk)

        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        logger.debug(f"Added {total_added} chunks for paper {paper_id}")
        return total_added

    async def chunk_fulltext(
        self,
        paper_id: str,
        fulltext: "PMCFullText",
        metadata: dict,
    ) -> int:
        """PMC 전문을 청크로 분할하여 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            fulltext: PMCFullText 객체
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not fulltext.has_full_text:
            return 0

        text_chunks = []

        if fulltext.abstract:
            chunk_id = f"{paper_id}_abstract_0"
            text_chunks.append(TextChunk(
                chunk_id=chunk_id,
                content=fulltext.abstract.strip(),
                document_id=paper_id,
                tier="tier1",
                section="abstract",
                source_type="pmc",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **metadata,
                    "source": "pmc_fulltext",
                    "pmcid": fulltext.pmcid or "",
                    "is_abstract_only": False,
                },
            ))

        section_tier_map = {
            "INTRO": "tier2",
            "METHODS": "tier2",
            "RESULTS": "tier1",
            "DISCUSS": "tier1",
            "CONCL": "tier1",
            "OTHER": "tier2",
            "SUPP": "tier2",
        }

        for idx, section in enumerate(fulltext.sections):
            section_text = section.text.strip()
            if not section_text or len(section_text) < 50:
                continue

            tier = section_tier_map.get(section.section_type, "tier2")
            section_label = section.section_type.lower()

            chunks = split_section_text(section_text, max_chars=1500)

            for chunk_idx, chunk_text in enumerate(chunks):
                chunk_id = f"{paper_id}_{section_label}_{idx}_{chunk_idx}"
                text_chunks.append(TextChunk(
                    chunk_id=chunk_id,
                    content=chunk_text,
                    document_id=paper_id,
                    tier=tier,
                    section=section_label,
                    source_type="pmc",
                    evidence_level=metadata.get("evidence_level", "5"),
                    publication_year=metadata.get("publication_year", 0),
                    page_num=0,
                    title=metadata.get("title", ""),
                    authors=metadata.get("authors", []),
                    metadata={
                        **metadata,
                        "source": "pmc_fulltext",
                        "pmcid": fulltext.pmcid or "",
                        "is_abstract_only": False,
                        "section_title": section.title,
                    },
                ))

        if not text_chunks:
            return 0

        contents = [c.content for c in text_chunks]
        # Contextual embedding prefix for fulltext chunks
        prefixed = apply_context_prefix(
            contents,
            title=metadata.get("title", ""),
            sections=[c.section for c in text_chunks],
            year=metadata.get("publication_year", 0),
        )
        embeddings = self.embedding_generator.embed_batch(prefixed)

        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        return total_added

    async def chunk_text(
        self,
        paper_id: str,
        text: str,
        metadata: dict,
    ) -> int:
        """일반 텍스트를 청크로 분할하여 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            text: 전문 텍스트
            metadata: 청크 메타데이터

        Returns:
            생성된 청크 수
        """
        if not text or not text.strip():
            return 0

        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        chunks_content = []
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) < 1500:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks_content.append(current_chunk)
                current_chunk = para

        if current_chunk:
            chunks_content.append(current_chunk)

        if not chunks_content:
            chunks_content = [text[:3000]]

        text_chunks = []
        for idx, content in enumerate(chunks_content):
            chunk_id = f"{paper_id}_text_{idx}"
            text_chunk = TextChunk(
                chunk_id=chunk_id,
                content=content,
                document_id=paper_id,
                tier="tier2",
                section="fulltext",
                source_type="doi_fulltext",
                evidence_level=metadata.get("evidence_level", "5"),
                publication_year=metadata.get("publication_year", 0),
                page_num=0,
                title=metadata.get("title", ""),
                authors=metadata.get("authors", []),
                metadata={
                    **metadata,
                    "source": "doi_fulltext",
                    "is_abstract_only": False,
                },
            )
            text_chunks.append(text_chunk)

        contents = [c.content for c in text_chunks]
        # Contextual embedding prefix for DOI fulltext chunks
        prefixed = apply_context_prefix(
            contents,
            title=metadata.get("title", ""),
            sections=[c.section for c in text_chunks],
            year=metadata.get("publication_year", 0),
        )
        embeddings = self.embedding_generator.embed_batch(prefixed)

        total_added = await self._store_chunks_to_neo4j(paper_id, text_chunks, embeddings)
        logger.debug(f"Added {total_added} text chunks for paper {paper_id}")
        return total_added

    async def _store_chunks_to_neo4j(
        self,
        paper_id: str,
        text_chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> int:
        """청크를 Neo4j에 저장.

        Args:
            paper_id: Paper ID
            text_chunks: TextChunk 리스트
            embeddings: 임베딩 벡터 리스트

        Returns:
            저장된 청크 수
        """
        if not text_chunks:
            return 0

        try:
            from graph.spine_schema import ChunkNode

            # Paper의 evidence_level을 chunk에 전파
            paper_el = "5"
            try:
                rows = await self.neo4j.run_query(
                    "MATCH (p:Paper {paper_id: $pid}) RETURN p.evidence_level AS el",
                    {"pid": paper_id},
                )
                if rows and rows[0].get("el"):
                    paper_el = rows[0]["el"]
            except Exception:
                pass

            chunk_nodes = []
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings)):
                chunk_node = ChunkNode(
                    chunk_id=chunk.chunk_id,
                    paper_id=paper_id,
                    content=chunk.content,
                    embedding=embedding,
                    tier=chunk.tier,
                    section=chunk.section,
                    evidence_level=paper_el,
                    is_key_finding=getattr(chunk, 'is_key_finding', False),
                    page_num=getattr(chunk, 'page_num', 0),
                    chunk_index=i,
                )
                chunk_nodes.append(chunk_node)

            result = await self.neo4j.create_chunks_batch(paper_id, chunk_nodes)
            created_count = result.get("created_count", len(chunk_nodes))

            tier1_count = sum(1 for c in text_chunks if c.tier == "tier1")
            tier2_count = sum(1 for c in text_chunks if c.tier == "tier2")
            logger.info(f"Neo4j Chunks: {created_count} stored with {len(embeddings[0]) if embeddings else 0}-dim embeddings (tier1: {tier1_count}, tier2: {tier2_count})")

            return created_count
        except Exception as e:
            logger.error(f"Failed to store chunks in Neo4j: {e}", exc_info=True)
            return 0

    # =========================================================================
    # Paper Upgrade & Utility
    # =========================================================================

    async def upgrade_with_pdf(
        self,
        paper_id: str,
        pdf_result: dict,
    ) -> dict:
        """PubMed-only Paper를 PDF 데이터로 업그레이드.

        Args:
            paper_id: 업그레이드할 paper ID (pubmed_xxx 형식)
            pdf_result: PDF 처리 결과

        Returns:
            업그레이드 결과 딕셔너리
        """
        if not paper_id.startswith(PUBMED_PAPER_PREFIX):
            return {
                "success": False,
                "error": "Paper is not a PubMed-only paper",
            }

        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        RETURN p
        """
        result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})

        if not result:
            return {
                "success": False,
                "error": f"Paper not found: {paper_id}",
            }

        existing = result[0]["p"]

        merge_cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        SET p.is_abstract_only = false,
            p.source = 'pdf+pubmed',
            p.updated_at = datetime(),
            p.sub_domain = COALESCE($sub_domain, p.sub_domain),
            p.study_type = COALESCE($study_type, p.study_type),
            p.evidence_level = COALESCE($evidence_level, p.evidence_level),
            p.sample_size = COALESCE($sample_size, p.sample_size),
            p.main_conclusion = COALESCE($main_conclusion, p.main_conclusion),
            p.pico_population = COALESCE($pico_population, p.pico_population),
            p.pico_intervention = COALESCE($pico_intervention, p.pico_intervention),
            p.pico_comparison = COALESCE($pico_comparison, p.pico_comparison),
            p.pico_outcome = COALESCE($pico_outcome, p.pico_outcome)
        RETURN p.paper_id AS paper_id
        """

        pdf_metadata = pdf_result.get("metadata", {})
        spine_metadata = pdf_metadata.get("spine_metadata", {})
        pico = spine_metadata.get("pico", {})

        try:
            await self.neo4j.run_query(merge_cypher, {
                "paper_id": paper_id,
                "sub_domain": spine_metadata.get("sub_domain"),
                "study_type": spine_metadata.get("study_type"),
                "evidence_level": spine_metadata.get("evidence_level"),
                "sample_size": spine_metadata.get("sample_size"),
                "main_conclusion": spine_metadata.get("main_conclusion"),
                "pico_population": pico.get("population"),
                "pico_intervention": pico.get("intervention"),
                "pico_comparison": pico.get("comparison"),
                "pico_outcome": pico.get("outcome"),
            })

            await self.delete_paper_chunks(paper_id)

            return {
                "success": True,
                "paper_id": paper_id,
                "upgraded_from": "pubmed",
                "upgraded_to": "pdf+pubmed",
                "preserved_pmid": existing.get("pmid"),
                "preserved_mesh_terms": existing.get("mesh_terms"),
                "new_chunks": pdf_result.get("chunks_added", 0),
            }

        except Exception as e:
            logger.error(f"Failed to upgrade paper: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

    async def delete_paper_chunks(self, paper_id: str) -> int:
        """논문의 기존 청크 삭제."""
        try:
            cypher = """
            MATCH (c:Chunk {paper_id: $paper_id})
            WITH c, c.chunk_id AS chunk_id
            DETACH DELETE c
            RETURN count(chunk_id) AS deleted_count
            """
            result = await self.neo4j.run_query(cypher, {"paper_id": paper_id})
            deleted = result[0].get("deleted_count", 0) if result else 0
            logger.debug(f"Deleted {deleted} chunks for paper {paper_id} from Neo4j")
            return deleted
        except Exception as e:
            logger.warning(f"Failed to delete chunks from Neo4j: {e}")
            return 0

    async def save_extracted_json(
        self,
        paper: BibliographicMetadata,
        extracted_data: dict,
    ) -> Optional[str]:
        """LLM에서 추출된 데이터를 JSON 파일로 저장.

        Args:
            paper: 서지 메타데이터
            extracted_data: LLM에서 추출된 데이터

        Returns:
            저장된 파일 경로 또는 None
        """
        try:
            extracted_dir = Path("data/extracted")
            extracted_dir.mkdir(parents=True, exist_ok=True)

            if "metadata" not in extracted_data:
                extracted_data["metadata"] = {}

            metadata = extracted_data["metadata"]

            if not metadata.get("title"):
                metadata["title"] = paper.title or ""
            if not metadata.get("authors"):
                metadata["authors"] = list(paper.authors) if paper.authors else []
            if not metadata.get("year"):
                metadata["year"] = paper.year
            if not metadata.get("journal"):
                metadata["journal"] = paper.journal or ""
            if not metadata.get("doi"):
                metadata["doi"] = paper.doi or ""
            if not metadata.get("pmid"):
                metadata["pmid"] = paper.pmid or ""
            if not metadata.get("abstract"):
                metadata["abstract"] = paper.abstract or ""

            if not metadata.get("mesh_terms") and paper.mesh_terms:
                metadata["mesh_terms"] = list(paper.mesh_terms)
            if not metadata.get("publication_types") and paper.publication_types:
                metadata["publication_types"] = list(paper.publication_types)
            if not metadata.get("journal_abbrev") and paper.journal_abbrev:
                metadata["journal_abbrev"] = paper.journal_abbrev

            title = paper.title or "unknown"
            safe_title = "".join(c for c in title[:50] if c.isalnum() or c in " -_").strip()
            safe_title = safe_title.replace(" ", "_")

            first_author = "unknown"
            if paper.authors:
                first_author_name = paper.authors[0] if paper.authors else "unknown"
                first_author = first_author_name.split()[-1] if first_author_name else "unknown"

            year = paper.year or 0
            json_filename = f"{year}_{first_author}_{safe_title}.json"

            json_path = extracted_dir / json_filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)

            logger.info(f"PubMed extracted JSON saved: {json_path}")
            return str(json_path)

        except Exception as e:
            logger.warning(f"Failed to save extracted JSON: {e}")
            return None

    async def get_abstract_only_papers(
        self,
        limit: int = 100,
    ) -> list[dict]:
        """초록만 있는 논문 목록 조회.

        Args:
            limit: 최대 반환 수

        Returns:
            논문 정보 딕셔너리 목록
        """
        cypher = """
        MATCH (p:Paper)
        WHERE p.is_abstract_only = true
        RETURN p.paper_id AS paper_id,
               p.pmid AS pmid,
               p.title AS title,
               p.year AS year,
               p.journal AS journal,
               p.created_at AS created_at
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        try:
            result = await self.neo4j.run_query(cypher, {"limit": limit})
            return result
        except Exception as e:
            logger.error(f"Error fetching abstract-only papers: {e}", exc_info=True)
            return []

    async def get_import_statistics(self) -> dict:
        """임포트 통계 조회."""
        cypher = """
        MATCH (p:Paper)
        WITH p.source AS source, p.is_abstract_only AS abstract_only, count(p) AS count
        RETURN source, abstract_only, count
        """
        try:
            result = await self.neo4j.run_query(cypher, {})
            stats = {
                "total_papers": 0,
                "pubmed_only": 0,
                "pdf_only": 0,
                "pdf_plus_pubmed": 0,
                "abstract_only": 0,
                "full_text": 0,
            }

            for row in result:
                count = row.get("count", 0)
                source = row.get("source")
                abstract_only = row.get("abstract_only", False)

                stats["total_papers"] += count

                if source == "pubmed":
                    stats["pubmed_only"] += count
                elif source == "pdf" or source is None:
                    stats["pdf_only"] += count
                elif source == "pdf+pubmed":
                    stats["pdf_plus_pubmed"] += count

                if abstract_only:
                    stats["abstract_only"] += count
                else:
                    stats["full_text"] += count

            return stats

        except Exception as e:
            logger.error(f"Error fetching import statistics: {e}", exc_info=True)
            return {}


# =============================================================================
# Standalone Utility Functions
# =============================================================================

def infer_evidence_level(
    publication_types: list[str],
    study_design: str = "",
    title: str = "",
) -> str:
    """Publication types, study_design, title에서 근거 수준 추론.

    우선순위: study_design > publication_types > title keywords
    study_design이 정확하면 그에 맞는 EL을 반환.
    """
    # 1. study_design 기반 (가장 정확)
    sd = (study_design or "").strip()
    SD_TO_EL = {
        "Meta-Analysis": "1a",
        "Systematic Review": "1a",
        "Randomized Controlled Trial": "1b",
        "Prospective Cohort Study": "2a",
        "Retrospective Cohort Study": "2b",
        "Case-Control Study": "2b",
        "Cross-Sectional Study": "2b",
        "Case Series": "3",
        "Case Report": "3",
        "Narrative Review": "4",
        "Expert Opinion": "4",
        "Biomechanical Study": "5",
        "Basic Science Study": "5",
        "Animal Study": "5",
    }
    if sd in SD_TO_EL:
        return SD_TO_EL[sd]

    # 2. publication_types 기반 (PubMed MeSH)
    types_lower = [pt.lower() for pt in publication_types]
    if any("meta-analysis" in pt for pt in types_lower):
        return "1a"
    elif any("systematic review" in pt for pt in types_lower):
        return "1a"
    elif any("randomized controlled trial" in pt for pt in types_lower):
        return "1b"
    elif any("clinical trial" in pt for pt in types_lower):
        return "2b"
    elif any("cohort" in pt for pt in types_lower):
        return "2b"
    elif any("case-control" in pt for pt in types_lower):
        return "2b"
    elif any("case report" in pt for pt in types_lower):
        return "3"

    # 3. title 기반 fallback
    t = (title or "").lower()
    if "meta-analysis" in t or "meta analysis" in t:
        return "1a"
    elif "systematic review" in t:
        return "1a"
    elif "randomized" in t or "randomised" in t:
        return "1b"
    elif "prospective" in t:
        return "2a"
    elif "case report" in t:
        return "3"
    elif "case series" in t:
        return "3"
    elif "biomechan" in t or "cadaver" in t or "finite element" in t:
        return "5"
    elif "review" in t:
        return "4"

    return "5"


def build_chunk_metadata(paper: BibliographicMetadata) -> dict:
    """청크용 메타데이터 구성."""
    return {
        "paper_id": f"{PUBMED_PAPER_PREFIX}{paper.pmid}",
        "title": paper.title,
        "authors": paper.authors[:3] if paper.authors else [],
        "year": paper.year,
        "journal": paper.journal,
        "pmid": paper.pmid,
        "doi": paper.doi,
        "mesh_terms": paper.mesh_terms[:5],
        "is_abstract_only": True,
        "source": "pubmed",
    }


def split_section_text(text: str, max_chars: int = 1500) -> list[str]:
    """긴 섹션 텍스트를 여러 청크로 분할."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


def parse_structured_abstract(
    paper_id: str,
    abstract: str,
    metadata: dict,
) -> list[AbstractChunk]:
    """구조화된 초록 파싱."""
    chunks = []

    section_patterns = [
        (r"(?i)\bBACKGROUND[:\s]*", "background"),
        (r"(?i)\bOBJECTIVE[S]?[:\s]*", "objective"),
        (r"(?i)\bMETHOD[S]?[:\s]*", "methods"),
        (r"(?i)\bRESULT[S]?[:\s]*", "results"),
        (r"(?i)\bCONCLUSION[S]?[:\s]*", "conclusions"),
        (r"(?i)\bPURPOSE[:\s]*", "purpose"),
        (r"(?i)\bSETTING[:\s]*", "setting"),
        (r"(?i)\bPATIENTS?[:\s]*", "patients"),
        (r"(?i)\bINTERVENTION[S]?[:\s]*", "intervention"),
        (r"(?i)\bMAIN OUTCOME[S]?[:\s]*", "outcomes"),
    ]

    found_sections = []

    for pattern, section_name in section_patterns:
        for match in re.finditer(pattern, abstract):
            found_sections.append((match.start(), match.end(), section_name))

    found_sections.sort(key=lambda x: x[0])

    if len(found_sections) >= 2:
        for i, (start, end, section_name) in enumerate(found_sections):
            if i + 1 < len(found_sections):
                next_start = found_sections[i + 1][0]
                content = abstract[end:next_start].strip()
            else:
                content = abstract[end:].strip()

            if content:
                chunk_id = f"{paper_id}_abstract_{len(chunks)}"
                chunks.append(AbstractChunk(
                    chunk_id=chunk_id,
                    content=content,
                    section=section_name,
                    metadata=metadata,
                ))

    return chunks


def _build_spine_metadata(spine_meta: dict) -> SpineMetadata:
    """spine_metadata dict에서 SpineMetadata 객체 생성 (공통 로직)."""
    # 복수형 키(anatomy_levels) 우선, 없으면 단수형(anatomy_level/anatomy_region) 폴백
    anatomy_levels = spine_meta.get("anatomy_levels", []) or []
    if not anatomy_levels:
        anatomy_level = spine_meta.get("anatomy_level", "")
        anatomy_levels = [anatomy_level] if anatomy_level else []
    if not anatomy_levels:
        anatomy_region = spine_meta.get("anatomy_region", "")
        if anatomy_region:
            anatomy_levels = [anatomy_region]

    # 복수형 키(pathologies) 우선, 없으면 단수형(pathology) 폴백
    pathologies_raw = spine_meta.get("pathologies") or spine_meta.get("pathology", [])
    pathologies = pathologies_raw if isinstance(pathologies_raw, list) else [pathologies_raw] if pathologies_raw else []

    all_outcomes = spine_meta.get("outcomes", [])

    sub_domains = spine_meta.get("sub_domains", []) or []
    sub_domain = spine_meta.get("sub_domain", "") or ""
    if not sub_domains and sub_domain:
        sub_domains = [sub_domain]
    if sub_domains and not sub_domain:
        sub_domain = sub_domains[0]

    surgical_approach = spine_meta.get("surgical_approach", []) or []

    pico = spine_meta.get("pico", {}) or {}
    pico_population = pico.get("population", "") or spine_meta.get("pico_population", "")
    pico_intervention = pico.get("intervention", "") or spine_meta.get("pico_intervention", "")
    pico_comparison = pico.get("comparison", "") or spine_meta.get("pico_comparison", "")
    pico_outcome = pico.get("outcome", "") or spine_meta.get("pico_outcome", "")

    return SpineMetadata(
        sub_domains=sub_domains,
        sub_domain=sub_domain,
        surgical_approach=surgical_approach,
        anatomy_levels=anatomy_levels,
        pathologies=pathologies,
        interventions=spine_meta.get("interventions", []),
        outcomes=all_outcomes,
        main_conclusion=spine_meta.get("main_conclusion", ""),
        summary=spine_meta.get("summary", ""),
        pico_population=pico_population,
        pico_intervention=pico_intervention,
        pico_comparison=pico_comparison,
        pico_outcome=pico_outcome,
    )


def _build_extracted_metadata(
    metadata_dict: dict,
    paper: BibliographicMetadata,
    inferred_evidence: str,
    abstract: str = "",
) -> ExtractedMetadata:
    """metadata_dict와 paper에서 ExtractedMetadata 객체 생성 (공통 로직)."""
    return ExtractedMetadata(
        title=metadata_dict.get("title", paper.title) or paper.title,
        authors=metadata_dict.get("authors", list(paper.authors)) or list(paper.authors),
        year=metadata_dict.get("year", paper.year) or paper.year,
        journal=metadata_dict.get("journal", paper.journal) or paper.journal,
        doi=metadata_dict.get("doi", paper.doi) or paper.doi,
        pmid=paper.pmid or "",
        abstract=abstract,
        study_type=metadata_dict.get("study_type", ""),
        study_design=normalize_study_design(metadata_dict.get("study_design", "")),
        evidence_level=metadata_dict.get("evidence_level") or inferred_evidence or "5",
        sample_size=metadata_dict.get("sample_size", 0) or 0,
        centers=metadata_dict.get("centers", ""),
        blinding=metadata_dict.get("blinding", ""),
    )
