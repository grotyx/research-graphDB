"""Unified Document Processor v7.0.

Integrates all v7.0 pipeline modules for universal document processing:
1. Document Type Detection (smart + hybrid)
2. Content Summary Generation (700+ words)
3. Section-based Chunking (semantic)
4. Conditional Entity Extraction (medical only)

This processor handles all document types (journal articles, books, webpages, etc.)
with type-specific processing and maintains backward compatibility with v6.0 schema.

Usage:
    # Basic usage (auto-detect type)
    processor = UnifiedProcessorV7()
    result = await processor.process_pdf("paper.pdf")

    # With explicit type
    result = await processor.process_pdf(
        "paper.pdf",
        document_type=DocumentType.JOURNAL_ARTICLE
    )

    # Process URL
    result = await processor.process_url("https://example.com/article")

    # Access results
    print(result.document_type)
    print(result.summary.text)
    print(len(result.chunks))
    if result.entities:
        print(result.entities.interventions)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from enum import Enum

# Import v7.0 modules
from .document_type_detector import (
    DocumentTypeDetector,
    DocumentType,
    DetectionResult,
)
from .summary_generator import (
    SummaryGenerator,
    ContentSummary,
    SummaryQuality,
)
from .section_chunker import (
    SectionChunker,
    Chunk,
)
from .entity_extractor import (
    EntityExtractor,
    ExtractedEntities,
)

# Import LLM client
from llm import LLMClient, LLMConfig

# Import PDF parsing utilities
try:
    import pymupdf  # PyMuPDF for PDF extraction
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class ProcessingResultV7:
    """v7.0 처리 결과.

    Attributes:
        paper_id: 문서 고유 ID
        document_type: 감지된 문서 유형
        summary: 700+ word 요약
        chunks: 섹션 기반 청크 리스트
        entities: 추출된 엔티티 (의학 문서만)
        processing_version: 프로세싱 버전
        processing_time: 총 처리 시간 (초)
        warnings: 처리 중 경고 메시지
        metadata: 추가 메타데이터 (제목, 저자 등)
    """
    paper_id: str
    document_type: DocumentType
    summary: ContentSummary
    chunks: list[Chunk]
    entities: Optional[ExtractedEntities] = None

    # Processing info
    processing_version: str = "v7.0"
    processing_time: float = 0.0
    warnings: list[str] = field(default_factory=list)

    # Additional metadata (for backward compatibility)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_count(self) -> int:
        """청크 개수."""
        return len(self.chunks)

    @property
    def has_medical_content(self) -> bool:
        """의학 콘텐츠 포함 여부."""
        return self.entities is not None and self.entities.is_medical_content


# =============================================================================
# UnifiedProcessorV7 Class
# =============================================================================

class UnifiedProcessorV7:
    """v7.0 통합 문서 처리기.

    Pipeline:
    1. Document Type Detection (smart + hybrid)
    2. Summary Generation (700+ words, English)
    3. Section-based Chunking (semantic)
    4. Conditional Entity Extraction (medical only)

    Features:
    - Universal document type support
    - Type-specific processing
    - Backward compatible with v6.0 PaperNode schema
    - Conditional medical entity extraction
    - Quality validation and enhancement
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        auto_detect_type: bool = True,
        extract_entities: bool = True,
        target_chunks: int = 20,
    ):
        """Initialize v7.0 processor.

        Args:
            llm_client: LLM client for text processing (None = auto-create)
            auto_detect_type: Auto-detect document type
            extract_entities: Extract medical entities
            target_chunks: Target number of chunks (default: 20)
        """
        # Create LLM client if not provided
        if llm_client is None:
            llm_config = LLMConfig(temperature=0.1)
            llm_client = LLMClient(config=llm_config)

        self.llm_client = llm_client
        self.auto_detect_type = auto_detect_type
        self.extract_entities_enabled = extract_entities
        self.target_chunks = target_chunks

        # Initialize v7.0 modules
        self.type_detector = DocumentTypeDetector()
        self.summary_generator = SummaryGenerator(llm_client)
        self.chunker = SectionChunker(llm_client)
        self.entity_extractor = EntityExtractor(llm_client)

        logger.info("UnifiedProcessorV7 initialized (v7.0 pipeline)")

    async def process(
        self,
        text: str,
        document_type: Optional[DocumentType] = None,
        url: Optional[str] = None,
        filename: Optional[str] = None,
        paper_id: Optional[str] = None,
    ) -> ProcessingResultV7:
        """Process document through v7.0 pipeline.

        Args:
            text: Document text content
            document_type: Document type (None = auto-detect)
            url: Source URL (for type detection)
            filename: Filename (for type detection)
            paper_id: Document ID (None = auto-generate)

        Returns:
            ProcessingResultV7
        """
        start_time = time.time()
        warnings = []

        # Generate paper ID if not provided
        if not paper_id:
            import hashlib
            paper_id = hashlib.md5(text[:1000].encode()).hexdigest()[:12]

        # Step 1: Document Type Detection
        if document_type is None and self.auto_detect_type:
            logger.info("Step 1: Detecting document type...")
            detection_result = self.type_detector.detect(
                url=url,
                content=text[:5000],  # First 5000 chars for detection
                filename=filename,
            )
            document_type = detection_result.document_type

            if detection_result.needs_confirmation:
                warnings.append(
                    f"Low confidence type detection ({detection_result.confidence:.2f}). "
                    f"Alternatives: {[t.value for t in detection_result.alternatives]}"
                )

            logger.info(
                f"Detected type: {document_type.value} "
                f"(confidence: {detection_result.confidence:.2f})"
            )
        elif document_type is None:
            # Default to DOCUMENT if no detection
            document_type = DocumentType.DOCUMENT
            warnings.append("Document type not detected or provided, using default")

        # Step 2: Summary Generation (700+ words)
        logger.info("Step 2: Generating comprehensive summary...")
        summary = await self.summary_generator.generate(
            text=text,
            document_type=document_type,
        )

        # Validate summary quality
        quality = await self.summary_generator.validate(summary.text)
        if not quality.is_valid():
            logger.warning(
                f"Summary quality below threshold: {quality.word_count} words"
            )
            warnings.append(
                f"Summary word count ({quality.word_count}) below target (700)"
            )

        logger.info(f"Summary generated: {summary.word_count} words")

        # Step 3: Section-based Chunking
        logger.info("Step 3: Creating semantic chunks...")
        chunks = await self.chunker.chunk(
            text=text,
            document_type=document_type,
            paper_id=paper_id,
            target_chunks=self.target_chunks,
        )

        logger.info(f"Created {len(chunks)} chunks")

        # Step 4: Conditional Entity Extraction (medical content only)
        entities = None
        if self.extract_entities_enabled:
            logger.info("Step 4: Checking if entity extraction needed...")
            should_extract = await self.entity_extractor.should_extract(
                document_type=document_type,
                text=text[:10000],  # First 10K chars for detection
            )

            if should_extract:
                logger.info("Extracting medical entities...")
                entities = await self.entity_extractor.extract(
                    text=text,
                    document_type=document_type,
                )
                logger.info(
                    f"Extracted entities: {len(entities.interventions)} interventions, "
                    f"{len(entities.pathologies)} pathologies"
                )
            else:
                logger.info("Skipping entity extraction (non-medical content)")

        processing_time = time.time() - start_time

        # Build metadata (for backward compatibility)
        metadata = {
            "title": filename or "Unknown",
            "source": url or filename or "text",
            "document_type": document_type.value,
            "summary_word_count": summary.word_count,
            "chunk_count": len(chunks),
        }

        return ProcessingResultV7(
            paper_id=paper_id,
            document_type=document_type,
            summary=summary,
            chunks=chunks,
            entities=entities,
            processing_version="v7.0",
            processing_time=processing_time,
            warnings=warnings,
            metadata=metadata,
        )

    async def process_pdf(
        self,
        pdf_path: str | Path,
        document_type: Optional[DocumentType] = None,
        paper_id: Optional[str] = None,
    ) -> ProcessingResultV7:
        """Process PDF file through v7.0 pipeline.

        Args:
            pdf_path: Path to PDF file
            document_type: Document type (None = auto-detect)
            paper_id: Document ID (None = auto-generate)

        Returns:
            ProcessingResultV7

        Raises:
            FileNotFoundError: If PDF file not found
            RuntimeError: If PyMuPDF not available
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if not PYMUPDF_AVAILABLE:
            raise RuntimeError(
                "PyMuPDF not available. Install with: pip install pymupdf"
            )

        logger.info(f"Processing PDF: {pdf_path.name}")

        # Extract text from PDF
        text = self._extract_pdf_text(pdf_path)

        # Process through pipeline
        return await self.process(
            text=text,
            document_type=document_type,
            filename=pdf_path.name,
            paper_id=paper_id,
        )

    async def process_url(
        self,
        url: str,
        document_type: Optional[DocumentType] = None,
        paper_id: Optional[str] = None,
    ) -> ProcessingResultV7:
        """Process web URL through v7.0 pipeline.

        Args:
            url: URL to process
            document_type: Document type (None = auto-detect)
            paper_id: Document ID (None = auto-generate)

        Returns:
            ProcessingResultV7

        Raises:
            NotImplementedError: URL fetching not implemented yet
        """
        # TODO: Implement URL fetching (requests + BeautifulSoup)
        raise NotImplementedError(
            "URL processing not implemented yet. "
            "Extract text manually and use process() method."
        )

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """Extract text from PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        try:
            doc = pymupdf.open(pdf_path)
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text())

            doc.close()

            full_text = "\n\n".join(text_parts)
            logger.info(
                f"Extracted {len(full_text)} characters from {len(text_parts)} pages"
            )

            return full_text

        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            raise RuntimeError(f"Failed to extract PDF text: {e}")

    # =========================================================================
    # Backward Compatibility with v6.0
    # =========================================================================

    def to_v6_format(self, result: ProcessingResultV7) -> dict:
        """Convert v7.0 result to v6.0 format (for compatibility).

        Args:
            result: ProcessingResultV7

        Returns:
            dict compatible with v6.0 UnifiedPDFProcessor output
        """
        # Map chunks to v6.0 format
        v6_chunks = []
        for chunk in result.chunks:
            v6_chunks.append({
                "content": chunk.text,
                "content_type": "text",  # Simplified
                "section_type": chunk.section.lower(),
                "tier": "tier1" if chunk.has_statistics else "tier2",
                "summary": "",  # Not extracted in v7.0
                "keywords": [],
                "is_key_finding": chunk.has_statistics,
                "statistics": None,
            })

        # Map entities to v6.0 spine_metadata
        spine_metadata = {}
        if result.entities:
            spine_metadata = {
                "interventions": [e.name for e in result.entities.interventions],
                "pathology": [e.name for e in result.entities.pathologies],
                "outcomes": [e.name for e in result.entities.outcomes],
                "anatomy_level": "",
                "anatomy_region": "",
            }

        # Build v6.0 compatible dict
        return {
            "metadata": {
                "title": result.metadata.get("title", ""),
                "abstract": result.summary.text[:1000],  # First 1000 chars
                "document_type": result.document_type.value,
            },
            "spine_metadata": spine_metadata,
            "chunks": v6_chunks,
        }


# =============================================================================
# Factory Function
# =============================================================================

def create_processor_v7(
    llm_client: Optional[LLMClient] = None,
    auto_detect_type: bool = True,
    extract_entities: bool = True,
    target_chunks: int = 20,
) -> UnifiedProcessorV7:
    """Factory function to create v7.0 processor.

    Args:
        llm_client: LLM client (None = auto-create)
        auto_detect_type: Auto-detect document type
        extract_entities: Extract medical entities
        target_chunks: Target number of chunks

    Returns:
        UnifiedProcessorV7 instance
    """
    return UnifiedProcessorV7(
        llm_client=llm_client,
        auto_detect_type=auto_detect_type,
        extract_entities=extract_entities,
        target_chunks=target_chunks,
    )


# =============================================================================
# Usage Example
# =============================================================================

async def example_usage():
    """Example usage of v7.0 processor."""
    processor = create_processor_v7()

    # Process PDF (auto-detect type)
    result = await processor.process_pdf("test_paper.pdf")

    print(f"Document Type: {result.document_type.value}")
    print(f"Summary: {result.summary.word_count} words")
    print(f"Chunks: {len(result.chunks)}")
    print(f"Processing Time: {result.processing_time:.2f}s")

    if result.entities:
        print(f"Medical Content: Yes")
        print(f"Interventions: {len(result.entities.interventions)}")
    else:
        print(f"Medical Content: No")

    # Convert to v6.0 format for compatibility
    v6_data = processor.to_v6_format(result)
    print(f"V6 chunks: {len(v6_data['chunks'])}")


if __name__ == "__main__":
    asyncio.run(example_usage())
