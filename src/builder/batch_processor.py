"""Batch PDF Processor for Spine GraphRAG.

Process multiple PDFs concurrently with:
- Configurable batch size and concurrency
- Progress tracking and reporting
- Resume from failure capability
- Rate limiting for API calls
- Checkpoint-based recovery
- Dual LLM provider support (Claude/Gemini)

Environment Variables:
- LLM_PROVIDER: "claude" (default) or "gemini"
- CLAUDE_MODEL: Claude model ID
- GEMINI_MODEL: Gemini model ID
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .unified_pdf_processor import UnifiedPDFProcessor, ProcessorResult
from ..core.error_handler import (
    with_retry,
    RetryConfig,
    CircuitBreaker,
    CircuitBreakerConfig,
    get_error_reporter,
    PDFProcessingError,
)
from ..core.exceptions import ProcessingError, ErrorCode

logger = logging.getLogger(__name__)


# ========================================================================
# Data Structures
# ========================================================================

@dataclass
class ProcessedFile:
    """Processed PDF file information.

    Attributes:
        file_path: PDF file path
        success: Whether processing succeeded
        result: ProcessorResult if successful
        error: Error message if failed
        processing_time: Time taken (seconds)
        timestamp: When processed
    """
    file_path: str
    success: bool
    result: Optional[ProcessorResult] = None
    error: Optional[str] = None
    processing_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        title = None
        chunks_count = 0
        if self.result and self.result.extracted_data:
            # v1.14.27: None 값 처리
            metadata = self.result.extracted_data.get("metadata") or {}
            title = metadata.get("title")
            chunks = self.result.extracted_data.get("chunks") or []
            chunks_count = len(chunks) if chunks else 0

        return {
            "file_path": self.file_path,
            "success": self.success,
            "error": self.error,
            "processing_time": self.processing_time,
            "timestamp": self.timestamp.isoformat(),
            "title": title,
            "chunks": chunks_count,
            "provider": self.result.provider if self.result else None,
            "model": self.result.model if self.result else None,
        }


@dataclass
class BatchProgress:
    """Batch processing progress.

    Attributes:
        total_files: Total PDFs to process
        processed_files: Files processed so far
        successful_files: Successfully processed files
        failed_files: Failed files
        skipped_files: Files skipped (already processed)
        current_file: Currently processing file
        start_time: Batch start time
        estimated_completion: Estimated completion time
    """
    total_files: int = 0
    processed_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    current_file: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    estimated_completion: Optional[datetime] = None

    @property
    def progress_percent(self) -> float:
        """Progress percentage (0-100)."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def elapsed_time(self) -> float:
        """Elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def avg_time_per_file(self) -> float:
        """Average time per file in seconds."""
        if self.processed_files == 0:
            return 0.0
        return self.elapsed_time / self.processed_files

    def estimate_completion(self) -> None:
        """Estimate completion time."""
        if self.processed_files == 0:
            return

        remaining = self.total_files - self.processed_files
        avg_time = self.avg_time_per_file
        remaining_seconds = remaining * avg_time

        from datetime import timedelta
        self.estimated_completion = datetime.now() + timedelta(seconds=remaining_seconds)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
            "skipped_files": self.skipped_files,
            "progress_percent": round(self.progress_percent, 2),
            "elapsed_time": round(self.elapsed_time, 2),
            "avg_time_per_file": round(self.avg_time_per_file, 2),
            "estimated_completion": (
                self.estimated_completion.isoformat() if self.estimated_completion else None
            ),
        }


@dataclass
class BatchResult:
    """Batch processing result.

    Attributes:
        progress: Final progress state
        processed_files: List of all processed files
        checkpoint_file: Path to checkpoint file
        total_time: Total processing time (seconds)
    """
    progress: BatchProgress
    processed_files: list[ProcessedFile]
    checkpoint_file: Optional[str] = None
    total_time: float = 0.0

    def get_summary(self) -> dict:
        """Get summary statistics."""
        return {
            "total_files": self.progress.total_files,
            "successful": self.progress.successful_files,
            "failed": self.progress.failed_files,
            "skipped": self.progress.skipped_files,
            "success_rate": (
                self.progress.successful_files / self.progress.total_files * 100
                if self.progress.total_files > 0 else 0
            ),
            "total_time": round(self.total_time, 2),
            "avg_time_per_file": round(self.progress.avg_time_per_file, 2),
        }


# ========================================================================
# Checkpoint Manager
# ========================================================================

class CheckpointManager:
    """Manage batch processing checkpoints for recovery."""

    def __init__(self, checkpoint_dir: Path):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint files
        """
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        batch_id: str,
        progress: BatchProgress,
        processed_files: list[ProcessedFile]
    ) -> Path:
        """Save checkpoint.

        Args:
            batch_id: Batch identifier
            progress: Current progress
            processed_files: List of processed files

        Returns:
            Path to checkpoint file
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}_checkpoint.json"

        checkpoint_data = {
            "batch_id": batch_id,
            "progress": progress.to_dict(),
            "processed_files": [f.to_dict() for f in processed_files],
            "saved_at": datetime.now().isoformat(),
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Checkpoint saved: {checkpoint_file}")
        return checkpoint_file

    def load_checkpoint(self, batch_id: str) -> Optional[dict]:
        """Load checkpoint.

        Args:
            batch_id: Batch identifier

        Returns:
            Checkpoint data or None if not found
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}_checkpoint.json"

        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, "r", encoding="utf-8") as f:
            checkpoint_data = json.load(f)

        logger.info(f"Checkpoint loaded: {checkpoint_file}")
        return checkpoint_data

    def delete_checkpoint(self, batch_id: str) -> None:
        """Delete checkpoint after successful completion.

        Args:
            batch_id: Batch identifier
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}_checkpoint.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info(f"Checkpoint deleted: {checkpoint_file}")


# ========================================================================
# Batch Processor
# ========================================================================

class BatchProcessor:
    """Batch PDF processor with concurrency and recovery.

    Features:
    - Concurrent processing with configurable limits
    - Automatic retry with exponential backoff
    - Circuit breaker for API protection
    - Checkpoint-based recovery
    - Progress tracking and reporting
    - Rate limiting for API calls
    - Dual LLM provider support (Claude/Gemini)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        checkpoint_dir: str = "./checkpoints",
        batch_size: int = 10,
        concurrency: int = 3,
        max_retries: int = 3,
        rate_limit_rpm: int = 60,  # Requests per minute
        # Legacy parameter for backward compatibility
        gemini_api_key: Optional[str] = None,
    ):
        """Initialize batch processor.

        Args:
            provider: LLM provider ("claude" or "gemini", default from LLM_PROVIDER env)
            model: Model ID (default from CLAUDE_MODEL or GEMINI_MODEL env)
            checkpoint_dir: Directory for checkpoints
            batch_size: Number of files to process per batch
            concurrency: Maximum concurrent PDF processing
            max_retries: Maximum retries per file
            rate_limit_rpm: API requests per minute limit
            gemini_api_key: [DEPRECATED] Use LLM_PROVIDER and GEMINI_API_KEY env vars instead
        """
        # Handle legacy parameter
        if gemini_api_key and not provider:
            logger.warning(
                "gemini_api_key parameter is deprecated. "
                "Use LLM_PROVIDER=gemini and GEMINI_API_KEY env vars instead."
            )
            os.environ["GEMINI_API_KEY"] = gemini_api_key
            provider = "gemini"

        self.provider = provider or os.getenv("LLM_PROVIDER", "claude")
        self.model = model
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.rate_limit_rpm = rate_limit_rpm

        # Initialize components
        self.checkpoint_manager = CheckpointManager(Path(checkpoint_dir))
        self.error_reporter = get_error_reporter()

        # Circuit breaker for LLM API
        self.circuit_breaker = CircuitBreaker(
            name=f"{self.provider}_api",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout=60.0,
            )
        )

        # Rate limiter (semaphore + timing)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.rate_limiter_interval = 60.0 / rate_limit_rpm  # Seconds between requests

        # Progress tracking
        self.progress = BatchProgress()
        self.processed_files: list[ProcessedFile] = []

        logger.info(
            f"BatchProcessor initialized: provider={self.provider}, "
            f"batch_size={batch_size}, concurrency={concurrency}, max_retries={max_retries}"
        )

    async def process_directory(
        self,
        pdf_dir: str,
        batch_id: Optional[str] = None,
        resume: bool = False
    ) -> BatchResult:
        """Process all PDFs in a directory.

        Args:
            pdf_dir: Directory containing PDF files
            batch_id: Batch identifier (auto-generated if None)
            resume: Whether to resume from checkpoint

        Returns:
            BatchResult with processing summary
        """
        pdf_path = Path(pdf_dir)
        if not pdf_path.exists():
            raise ProcessingError(message=f"Directory not found: {pdf_dir}", error_code=ErrorCode.PROC_GENERAL)

        # Find all PDF files
        pdf_files = list(pdf_path.glob("**/*.pdf"))
        pdf_paths = [str(f) for f in pdf_files]

        logger.info(f"Found {len(pdf_paths)} PDF files in {pdf_dir}")

        return await self.process_files(pdf_paths, batch_id, resume)

    async def process_files(
        self,
        pdf_paths: list[str],
        batch_id: Optional[str] = None,
        resume: bool = False
    ) -> BatchResult:
        """Process a list of PDF files.

        Args:
            pdf_paths: List of PDF file paths
            batch_id: Batch identifier (auto-generated if None)
            resume: Whether to resume from checkpoint

        Returns:
            BatchResult with processing summary
        """
        # Generate batch ID
        if batch_id is None:
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Starting batch processing: {batch_id}")

        # Resume from checkpoint if requested
        processed_paths = set()
        if resume:
            checkpoint = self.checkpoint_manager.load_checkpoint(batch_id)
            if checkpoint:
                # Restore progress
                self.processed_files = [
                    ProcessedFile(
                        file_path=f["file_path"],
                        success=f["success"],
                        error=f.get("error"),
                        processing_time=f["processing_time"],
                        timestamp=datetime.fromisoformat(f["timestamp"]),
                    )
                    for f in checkpoint["processed_files"]
                ]
                processed_paths = {f.file_path for f in self.processed_files}

                logger.info(
                    f"Resuming from checkpoint: {len(processed_paths)} files already processed"
                )

        # Filter out already processed files
        remaining_files = [p for p in pdf_paths if p not in processed_paths]

        # Initialize progress
        self.progress = BatchProgress(
            total_files=len(pdf_paths),
            processed_files=len(processed_paths),
            successful_files=sum(1 for f in self.processed_files if f.success),
            failed_files=sum(1 for f in self.processed_files if not f.success),
        )

        start_time = time.time()

        # Process files in batches
        for i in range(0, len(remaining_files), self.batch_size):
            batch = remaining_files[i:i + self.batch_size]
            logger.info(
                f"Processing batch {i // self.batch_size + 1}: "
                f"{len(batch)} files (total: {self.progress.processed_files}/{self.progress.total_files})"
            )

            # Process batch concurrently
            tasks = [self._process_single_file(pdf_path) for pdf_path in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Update results
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch processing error: {result}", exc_info=True)
                    await self.error_reporter.report(result)

            # Save checkpoint after each batch
            checkpoint_file = self.checkpoint_manager.save_checkpoint(
                batch_id, self.progress, self.processed_files
            )

            # Update ETA
            self.progress.estimate_completion()

            # Log progress
            logger.info(
                f"Progress: {self.progress.progress_percent:.1f}% "
                f"({self.progress.successful_files} success, "
                f"{self.progress.failed_files} failed)"
            )

        # Final result
        total_time = time.time() - start_time

        # Delete checkpoint on successful completion
        if self.progress.failed_files == 0:
            self.checkpoint_manager.delete_checkpoint(batch_id)

        result = BatchResult(
            progress=self.progress,
            processed_files=self.processed_files,
            checkpoint_file=str(checkpoint_file) if self.progress.failed_files > 0 else None,
            total_time=total_time,
        )

        logger.info(f"Batch processing complete: {result.get_summary()}")

        return result

    async def _process_single_file(self, pdf_path: str) -> ProcessedFile:
        """Process a single PDF file with retry and rate limiting.

        Args:
            pdf_path: PDF file path

        Returns:
            ProcessedFile result
        """
        async with self.semaphore:
            # Rate limiting
            await asyncio.sleep(self.rate_limiter_interval)

            self.progress.current_file = pdf_path
            start_time = time.time()

            # Create unified processor (supports both Claude and Gemini)
            processor = UnifiedPDFProcessor(
                provider=self.provider,
                model=self.model,
            )

            # Retry configuration
            retry_config = RetryConfig(
                max_retries=self.max_retries,
                initial_delay=2.0,
                max_delay=60.0,
            )

            @with_retry(retry_config)
            async def process_with_circuit_breaker():
                return await self.circuit_breaker.call(
                    processor.process_pdf,
                    pdf_path
                )

            # Process PDF
            try:
                result = await process_with_circuit_breaker()
                processing_time = time.time() - start_time

                if result.success:
                    # Extract title from result (v1.14.27: None 값 처리)
                    title = "Unknown"
                    if result.extracted_data:
                        metadata = result.extracted_data.get("metadata") or {}
                        title = metadata.get("title") or "Unknown"

                    processed = ProcessedFile(
                        file_path=pdf_path,
                        success=True,
                        result=result,
                        processing_time=processing_time,
                    )

                    self.progress.successful_files += 1
                    logger.info(
                        f"✓ Processed: {Path(pdf_path).name} "
                        f"({title}) [{result.provider}/{result.model}] in {processing_time:.1f}s"
                    )
                else:
                    processed = ProcessedFile(
                        file_path=pdf_path,
                        success=False,
                        error=result.error,
                        processing_time=processing_time,
                    )

                    self.progress.failed_files += 1
                    logger.warning(f"✗ Failed: {Path(pdf_path).name} - {result.error}")

            except Exception as e:
                processing_time = time.time() - start_time
                processed = ProcessedFile(
                    file_path=pdf_path,
                    success=False,
                    error=str(e),
                    processing_time=processing_time,
                )

                self.progress.failed_files += 1
                logger.error(f"✗ Error: {Path(pdf_path).name} - {e}", exc_info=True)

                # Report error
                await self.error_reporter.report(
                    PDFProcessingError(str(e)),
                    context={"file": pdf_path, "provider": self.provider}
                )

            # Update progress
            self.progress.processed_files += 1
            self.processed_files.append(processed)

            return processed

    def get_progress(self) -> BatchProgress:
        """Get current progress.

        Returns:
            Current BatchProgress
        """
        return self.progress

    async def resume(self, checkpoint_file: str) -> BatchResult:
        """Resume from a checkpoint file.

        Args:
            checkpoint_file: Path to checkpoint file

        Returns:
            BatchResult from resumed processing
        """
        checkpoint_path = Path(checkpoint_file)
        if not checkpoint_path.exists():
            raise ProcessingError(message=f"Checkpoint file not found: {checkpoint_file}", error_code=ErrorCode.PROC_GENERAL)

        # Extract batch_id from filename
        batch_id = checkpoint_path.stem.replace("_checkpoint", "")

        # Load checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint(batch_id)
        if not checkpoint:
            raise ProcessingError(message=f"Failed to load checkpoint: {checkpoint_file}", error_code=ErrorCode.PROC_GENERAL)

        # Get original file list (need to reconstruct)
        # This is a limitation - we need to store the original file list in checkpoint
        # For now, raise an error
        raise NotImplementedError(
            "Resume requires the original file list. "
            "Please use process_files() or process_directory() with resume=True instead."
        )


# ========================================================================
# Usage Example
# ========================================================================

async def example_usage():
    """Batch processor usage example.

    Uses LLM_PROVIDER env var to select provider (default: claude).
    Set LLM_PROVIDER=gemini to use Gemini instead.
    """

    # Initialize processor (uses LLM_PROVIDER from env)
    processor = BatchProcessor(
        # provider="claude",  # or "gemini", or leave None for env default
        checkpoint_dir="./checkpoints",
        batch_size=5,
        concurrency=2,
        max_retries=3,
        rate_limit_rpm=30,
    )

    print(f"Using provider: {processor.provider}")

    # Process directory
    result = await processor.process_directory(
        pdf_dir="./test_pdfs",
        batch_id="test_batch_001",
        resume=False
    )

    # Print summary
    summary = result.get_summary()
    print(f"\nBatch Processing Summary:")
    print(f"  Provider: {processor.provider}")
    print(f"  Total files: {summary['total_files']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Success rate: {summary['success_rate']:.1f}%")
    print(f"  Total time: {summary['total_time']:.1f}s")
    print(f"  Avg time per file: {summary['avg_time_per_file']:.1f}s")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())
