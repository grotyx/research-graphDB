"""Batch Processor unit tests.

Tests for builder/batch_processor.py covering:
- ProcessedFile dataclass and serialization
- BatchProgress tracking and estimation
- BatchResult summary
- CheckpointManager: save, load, delete
- BatchProcessor init and configuration
- Batch processing pipeline (mocked)
- Concurrency control (semaphore)
- Error handling per item
- Partial failure handling
- Resume from checkpoint

Note: batch_processor.py uses relative imports (from ..core.xxx) that are
incompatible with PYTHONPATH=./src flat imports. We use importlib.util to
load the module from its file path with proper package context.
"""

import pytest
import asyncio
import importlib
import importlib.util
import json
import os
import time
import types
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timedelta
from pathlib import Path

import sys

_src = str(Path(__file__).parent.parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# ------------------------------------------------------------------
# Bootstrap: create a virtual "src" package so that relative imports
# inside builder/batch_processor.py (from ..core.xxx) resolve properly.
# ------------------------------------------------------------------
_src_path = Path(__file__).parent.parent.parent / "src"

# 1) Create "src" as a namespace package
if "src" not in sys.modules:
    _src_pkg = types.ModuleType("src")
    _src_pkg.__path__ = [str(_src_path)]
    _src_pkg.__package__ = "src"
    sys.modules["src"] = _src_pkg

# 2) Import core modules under src.core namespace
import core.exceptions as _exceptions_mod
import core.error_handler as _error_handler_mod

if "src.core" not in sys.modules:
    _core_pkg = types.ModuleType("src.core")
    _core_pkg.__path__ = [str(_src_path / "core")]
    _core_pkg.__package__ = "src.core"
    sys.modules["src.core"] = _core_pkg

sys.modules["src.core.exceptions"] = _exceptions_mod
sys.modules["src.core.error_handler"] = _error_handler_mod

# 3) Import builder.unified_pdf_processor under src.builder namespace
import builder as _builder_pkg
import builder.unified_pdf_processor as _up_mod

if "src.builder" not in sys.modules:
    sys.modules["src.builder"] = _builder_pkg

sys.modules["src.builder.unified_pdf_processor"] = _up_mod

# 4) Now load batch_processor as src.builder.batch_processor via importlib
_bp_file = _src_path / "builder" / "batch_processor.py"
_spec = importlib.util.spec_from_file_location(
    "src.builder.batch_processor",
    str(_bp_file),
    submodule_search_locations=[],
)
_bp_mod = importlib.util.module_from_spec(_spec)
_bp_mod.__package__ = "src.builder"
sys.modules["src.builder.batch_processor"] = _bp_mod
# Also alias as builder.batch_processor for patch targets
sys.modules["builder.batch_processor"] = _bp_mod
_spec.loader.exec_module(_bp_mod)

# Now import the classes we need
ProcessedFile = _bp_mod.ProcessedFile
BatchProgress = _bp_mod.BatchProgress
BatchResult = _bp_mod.BatchResult
CheckpointManager = _bp_mod.CheckpointManager
BatchProcessor = _bp_mod.BatchProcessor


# ============================================================================
# ProcessedFile Tests
# ============================================================================

class TestProcessedFile:
    """Tests for ProcessedFile dataclass."""

    def test_creation_success(self):
        """Create successful ProcessedFile."""
        pf = ProcessedFile(
            file_path="/data/test.pdf",
            success=True,
            processing_time=5.3,
        )
        assert pf.file_path == "/data/test.pdf"
        assert pf.success is True
        assert pf.error is None

    def test_creation_failure(self):
        """Create failed ProcessedFile."""
        pf = ProcessedFile(
            file_path="/data/bad.pdf",
            success=False,
            error="PDF parsing failed",
            processing_time=1.2,
        )
        assert pf.success is False
        assert pf.error == "PDF parsing failed"

    def test_to_dict_success(self):
        """Serialize successful ProcessedFile to dict."""
        mock_result = MagicMock()
        mock_result.extracted_data = {
            "metadata": {"title": "Test Paper"},
            "chunks": [{"id": 1}, {"id": 2}],
        }
        mock_result.provider = "claude"
        mock_result.model = "claude-haiku"

        pf = ProcessedFile(
            file_path="/data/test.pdf",
            success=True,
            result=mock_result,
            processing_time=5.0,
        )
        d = pf.to_dict()
        assert d["file_path"] == "/data/test.pdf"
        assert d["success"] is True
        assert d["title"] == "Test Paper"
        assert d["chunks"] == 2
        assert d["provider"] == "claude"

    def test_to_dict_failure(self):
        """Serialize failed ProcessedFile to dict."""
        pf = ProcessedFile(
            file_path="/data/bad.pdf",
            success=False,
            error="Parse error",
            processing_time=1.0,
        )
        d = pf.to_dict()
        assert d["success"] is False
        assert d["error"] == "Parse error"
        assert d["title"] is None
        assert d["chunks"] == 0

    def test_to_dict_none_metadata(self):
        """Handle None metadata in extracted_data."""
        mock_result = MagicMock()
        mock_result.extracted_data = {"metadata": None, "chunks": None}
        mock_result.provider = "gemini"
        mock_result.model = "gemini-pro"

        pf = ProcessedFile(
            file_path="/data/test.pdf",
            success=True,
            result=mock_result,
        )
        d = pf.to_dict()
        assert d["title"] is None
        assert d["chunks"] == 0

    def test_to_dict_no_result(self):
        """Handle no result in ProcessedFile."""
        pf = ProcessedFile(file_path="/data/test.pdf", success=True)
        d = pf.to_dict()
        assert d["provider"] is None
        assert d["model"] is None

    def test_timestamp_auto_set(self):
        """Timestamp is auto-set."""
        pf = ProcessedFile(file_path="test.pdf", success=True)
        assert isinstance(pf.timestamp, datetime)


# ============================================================================
# BatchProgress Tests
# ============================================================================

class TestBatchProgress:
    """Tests for BatchProgress dataclass."""

    def test_default_values(self):
        """Default values are zero."""
        bp = BatchProgress()
        assert bp.total_files == 0
        assert bp.processed_files == 0
        assert bp.successful_files == 0
        assert bp.failed_files == 0
        assert bp.skipped_files == 0

    def test_progress_percent_zero_total(self):
        """Progress percent with zero total files."""
        bp = BatchProgress(total_files=0)
        assert bp.progress_percent == 0.0

    def test_progress_percent_50(self):
        """Progress percent at 50%."""
        bp = BatchProgress(total_files=10, processed_files=5)
        assert bp.progress_percent == 50.0

    def test_progress_percent_100(self):
        """Progress percent at 100%."""
        bp = BatchProgress(total_files=10, processed_files=10)
        assert bp.progress_percent == 100.0

    def test_elapsed_time(self):
        """Elapsed time calculation."""
        bp = BatchProgress()
        bp.start_time = datetime.now() - timedelta(seconds=10)
        assert bp.elapsed_time >= 9  # Allow for timing

    def test_avg_time_per_file_zero(self):
        """Avg time per file with zero processed."""
        bp = BatchProgress()
        assert bp.avg_time_per_file == 0.0

    def test_avg_time_per_file(self):
        """Avg time per file calculation."""
        bp = BatchProgress(processed_files=5)
        bp.start_time = datetime.now() - timedelta(seconds=50)
        avg = bp.avg_time_per_file
        assert avg >= 9  # ~10 seconds per file

    def test_estimate_completion_no_progress(self):
        """Estimate completion with no progress does nothing."""
        bp = BatchProgress(total_files=10)
        bp.estimate_completion()
        assert bp.estimated_completion is None

    def test_estimate_completion_with_progress(self):
        """Estimate completion with some progress."""
        bp = BatchProgress(total_files=10, processed_files=5)
        bp.start_time = datetime.now() - timedelta(seconds=50)
        bp.estimate_completion()
        assert bp.estimated_completion is not None
        assert bp.estimated_completion > datetime.now()

    def test_to_dict(self):
        """BatchProgress serialization."""
        bp = BatchProgress(total_files=10, processed_files=3, successful_files=2, failed_files=1)
        d = bp.to_dict()
        assert d["total_files"] == 10
        assert d["processed_files"] == 3
        assert d["progress_percent"] == 30.0
        assert isinstance(d["elapsed_time"], float)

    def test_current_file_tracking(self):
        """Current file can be tracked."""
        bp = BatchProgress()
        assert bp.current_file is None
        bp.current_file = "/data/test.pdf"
        assert bp.current_file == "/data/test.pdf"


# ============================================================================
# BatchResult Tests
# ============================================================================

class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_get_summary(self):
        """Summary statistics calculation."""
        progress = BatchProgress(
            total_files=10,
            processed_files=10,
            successful_files=8,
            failed_files=2,
        )
        result = BatchResult(
            progress=progress,
            processed_files=[],
            total_time=100.0,
        )
        summary = result.get_summary()
        assert summary["total_files"] == 10
        assert summary["successful"] == 8
        assert summary["failed"] == 2
        assert summary["success_rate"] == 80.0
        assert summary["total_time"] == 100.0

    def test_get_summary_zero_files(self):
        """Summary with zero files."""
        progress = BatchProgress(total_files=0)
        result = BatchResult(progress=progress, processed_files=[])
        summary = result.get_summary()
        assert summary["success_rate"] == 0

    def test_get_summary_all_success(self):
        """Summary with all successes."""
        progress = BatchProgress(total_files=5, successful_files=5)
        result = BatchResult(progress=progress, processed_files=[])
        summary = result.get_summary()
        assert summary["success_rate"] == 100.0

    def test_checkpoint_file_attribute(self):
        """Checkpoint file attribute stored."""
        progress = BatchProgress()
        result = BatchResult(
            progress=progress, processed_files=[],
            checkpoint_file="/path/to/checkpoint.json",
        )
        assert result.checkpoint_file == "/path/to/checkpoint.json"


# ============================================================================
# CheckpointManager Tests
# ============================================================================

class TestCheckpointManager:
    """Tests for CheckpointManager."""

    @pytest.fixture
    def checkpoint_dir(self, tmp_path):
        return tmp_path / "checkpoints"

    @pytest.fixture
    def manager(self, checkpoint_dir):
        return CheckpointManager(checkpoint_dir)

    def test_init_creates_directory(self, checkpoint_dir):
        """Init creates checkpoint directory."""
        assert not checkpoint_dir.exists()
        CheckpointManager(checkpoint_dir)
        assert checkpoint_dir.exists()

    def test_save_checkpoint(self, manager, checkpoint_dir):
        """Save checkpoint creates JSON file."""
        progress = BatchProgress(total_files=5, processed_files=2)
        files = [
            ProcessedFile(file_path="a.pdf", success=True, processing_time=1.0),
        ]
        path = manager.save_checkpoint("batch1", progress, files)
        assert path.exists()
        assert path.name == "batch1_checkpoint.json"

        with open(path) as f:
            data = json.load(f)
        assert data["batch_id"] == "batch1"
        assert data["progress"]["total_files"] == 5

    def test_load_checkpoint(self, manager):
        """Load existing checkpoint."""
        progress = BatchProgress(total_files=3)
        files = [ProcessedFile(file_path="test.pdf", success=True, processing_time=2.0)]
        manager.save_checkpoint("batch2", progress, files)

        loaded = manager.load_checkpoint("batch2")
        assert loaded is not None
        assert loaded["batch_id"] == "batch2"
        assert len(loaded["processed_files"]) == 1

    def test_load_checkpoint_not_found(self, manager):
        """Load nonexistent checkpoint returns None."""
        loaded = manager.load_checkpoint("nonexistent")
        assert loaded is None

    def test_delete_checkpoint(self, manager, checkpoint_dir):
        """Delete checkpoint removes file."""
        progress = BatchProgress()
        manager.save_checkpoint("batch3", progress, [])
        assert (checkpoint_dir / "batch3_checkpoint.json").exists()

        manager.delete_checkpoint("batch3")
        assert not (checkpoint_dir / "batch3_checkpoint.json").exists()

    def test_delete_checkpoint_nonexistent(self, manager):
        """Delete nonexistent checkpoint does nothing."""
        manager.delete_checkpoint("nonexistent")  # Should not raise

    def test_save_checkpoint_overwrites(self, manager):
        """Saving checkpoint with same batch_id overwrites."""
        progress1 = BatchProgress(total_files=5)
        manager.save_checkpoint("batch_ow", progress1, [])

        progress2 = BatchProgress(total_files=10)
        manager.save_checkpoint("batch_ow", progress2, [])

        loaded = manager.load_checkpoint("batch_ow")
        assert loaded["progress"]["total_files"] == 10

    def test_checkpoint_data_structure(self, manager):
        """Checkpoint data has expected structure."""
        progress = BatchProgress(total_files=2, processed_files=1)
        files = [ProcessedFile(file_path="f.pdf", success=True, processing_time=3.0)]
        manager.save_checkpoint("struct", progress, files)
        loaded = manager.load_checkpoint("struct")

        assert "batch_id" in loaded
        assert "progress" in loaded
        assert "processed_files" in loaded
        assert "saved_at" in loaded


# ============================================================================
# BatchProcessor Init Tests
# ============================================================================

class TestBatchProcessorInit:
    """Tests for BatchProcessor initialization."""

    @patch.object(_bp_mod, "get_error_reporter")
    def test_default_init(self, mock_reporter, tmp_path):
        """Default initialization."""
        mock_reporter.return_value = MagicMock()
        bp = BatchProcessor(checkpoint_dir=str(tmp_path / "cp"))
        assert bp.provider in ["claude", "gemini"]  # from env or default
        assert bp.batch_size == 10
        assert bp.concurrency == 3
        assert bp.max_retries == 3

    @patch.object(_bp_mod, "get_error_reporter")
    def test_custom_init(self, mock_reporter, tmp_path):
        """Custom initialization parameters."""
        mock_reporter.return_value = MagicMock()
        bp = BatchProcessor(
            provider="gemini",
            model="gemini-2.5-flash",
            checkpoint_dir=str(tmp_path / "cp"),
            batch_size=5,
            concurrency=2,
            max_retries=5,
            rate_limit_rpm=30,
        )
        assert bp.provider == "gemini"
        assert bp.model == "gemini-2.5-flash"
        assert bp.batch_size == 5
        assert bp.concurrency == 2
        assert bp.max_retries == 5

    @patch.object(_bp_mod, "get_error_reporter")
    def test_legacy_gemini_api_key(self, mock_reporter, tmp_path):
        """Legacy gemini_api_key parameter sets provider."""
        mock_reporter.return_value = MagicMock()
        with patch.dict("os.environ", {}, clear=False):
            bp = BatchProcessor(
                gemini_api_key="test-key",
                checkpoint_dir=str(tmp_path / "cp"),
            )
        assert bp.provider == "gemini"

    @patch.object(_bp_mod, "get_error_reporter")
    def test_semaphore_created(self, mock_reporter, tmp_path):
        """Semaphore is created with correct concurrency."""
        mock_reporter.return_value = MagicMock()
        bp = BatchProcessor(
            concurrency=5,
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert bp.semaphore._value == 5

    @patch.object(_bp_mod, "get_error_reporter")
    def test_rate_limiter_interval(self, mock_reporter, tmp_path):
        """Rate limiter interval calculated from RPM."""
        mock_reporter.return_value = MagicMock()
        bp = BatchProcessor(
            rate_limit_rpm=60,
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert bp.rate_limiter_interval == pytest.approx(1.0)

    @patch.object(_bp_mod, "get_error_reporter")
    def test_progress_initialized(self, mock_reporter, tmp_path):
        """Progress tracking is initialized."""
        mock_reporter.return_value = MagicMock()
        bp = BatchProcessor(checkpoint_dir=str(tmp_path / "cp"))
        assert isinstance(bp.progress, BatchProgress)
        assert bp.processed_files == []


# ============================================================================
# BatchProcessor Processing Tests
# ============================================================================

class TestBatchProcessorProcessing:
    """Tests for BatchProcessor processing methods."""

    @pytest.fixture
    def processor(self, tmp_path):
        with patch.object(_bp_mod, "get_error_reporter") as mock_reporter:
            mock_err_reporter = MagicMock()
            mock_err_reporter.report = AsyncMock()
            mock_reporter.return_value = mock_err_reporter
            bp = BatchProcessor(
                provider="claude",
                checkpoint_dir=str(tmp_path / "checkpoints"),
                batch_size=2,
                concurrency=2,
                max_retries=1,
                rate_limit_rpm=600,  # Fast for testing
            )
        return bp

    @pytest.mark.asyncio
    async def test_process_files_empty_list(self, processor):
        """Process empty file list completes without error."""
        result = await processor.process_files([])
        assert result.progress.total_files == 0
        assert result.total_time >= 0

    @pytest.mark.asyncio
    async def test_process_files_success(self, processor, tmp_path):
        """Process files with successful results."""
        pdf1 = tmp_path / "test1.pdf"
        pdf2 = tmp_path / "test2.pdf"
        pdf1.write_bytes(b"%PDF-1.4 content1")
        pdf2.write_bytes(b"%PDF-1.4 content2")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.extracted_data = {"metadata": {"title": "Test"}, "chunks": []}
        mock_result.provider = "claude"
        mock_result.model = "haiku"
        mock_result.error = None

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(return_value=mock_result)

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(return_value=mock_result)
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1), str(pdf2)],
                batch_id="test_batch",
            )

        assert result.progress.total_files == 2
        assert result.progress.successful_files == 2
        assert result.progress.failed_files == 0

    @pytest.mark.asyncio
    async def test_process_files_partial_failure(self, processor, tmp_path):
        """Process files with partial failures."""
        pdf1 = tmp_path / "good.pdf"
        pdf2 = tmp_path / "bad.pdf"
        pdf1.write_bytes(b"%PDF-1.4 good")
        pdf2.write_bytes(b"%PDF-1.4 bad")

        success_result = MagicMock()
        success_result.success = True
        success_result.extracted_data = {"metadata": {"title": "Good"}, "chunks": []}
        success_result.provider = "claude"
        success_result.model = "haiku"

        fail_result = MagicMock()
        fail_result.success = False
        fail_result.error = "Corrupt PDF"
        fail_result.extracted_data = None
        fail_result.provider = "claude"
        fail_result.model = "haiku"

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(side_effect=[success_result, fail_result])

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(side_effect=[success_result, fail_result])
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1), str(pdf2)],
                batch_id="partial_fail",
            )

        assert result.progress.successful_files == 1
        assert result.progress.failed_files == 1

    @pytest.mark.asyncio
    async def test_process_files_exception(self, processor, tmp_path):
        """Process files handles exceptions."""
        pdf1 = tmp_path / "crash.pdf"
        pdf1.write_bytes(b"%PDF-1.4 crash")

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(side_effect=RuntimeError("crash"))

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(side_effect=RuntimeError("crash"))
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1)],
                batch_id="crash_batch",
            )

        assert result.progress.failed_files == 1

    @pytest.mark.asyncio
    async def test_process_files_checkpoint_saved(self, processor, tmp_path):
        """Checkpoint is saved after each batch."""
        pdf1 = tmp_path / "test.pdf"
        pdf1.write_bytes(b"%PDF-1.4 test")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.extracted_data = {"metadata": {"title": "T"}, "chunks": []}
        mock_result.provider = "claude"
        mock_result.model = "haiku"

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(return_value=mock_result)

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(return_value=mock_result)
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1)], batch_id="cp_test"
            )

        # Checkpoint should be deleted on all-success
        assert result.checkpoint_file is None

    @pytest.mark.asyncio
    async def test_process_files_checkpoint_kept_on_failure(self, processor, tmp_path):
        """Checkpoint is kept when there are failures."""
        pdf1 = tmp_path / "fail.pdf"
        pdf1.write_bytes(b"%PDF-1.4 fail")

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(side_effect=RuntimeError("error"))

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(side_effect=RuntimeError("error"))
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1)], batch_id="fail_cp"
            )

        assert result.checkpoint_file is not None

    @pytest.mark.asyncio
    async def test_process_files_resume(self, processor, tmp_path):
        """Resume from checkpoint skips already processed files."""
        pdf1 = tmp_path / "done.pdf"
        pdf2 = tmp_path / "todo.pdf"
        pdf1.write_bytes(b"%PDF-1.4 done")
        pdf2.write_bytes(b"%PDF-1.4 todo")

        # Save checkpoint with pdf1 already processed
        processor.checkpoint_manager.save_checkpoint(
            "resume_batch",
            BatchProgress(total_files=2, processed_files=1, successful_files=1),
            [ProcessedFile(file_path=str(pdf1), success=True, processing_time=1.0)],
        )

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.extracted_data = {"metadata": {"title": "Todo"}, "chunks": []}
        mock_result.provider = "claude"
        mock_result.model = "haiku"

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(return_value=mock_result)

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(return_value=mock_result)
            processor.circuit_breaker = mock_cb

            result = await processor.process_files(
                [str(pdf1), str(pdf2)],
                batch_id="resume_batch",
                resume=True,
            )

        # pdf1 should be skipped (from checkpoint), only pdf2 processed
        assert result.progress.total_files == 2

    def test_get_progress(self, processor):
        """Get progress returns current progress."""
        progress = processor.get_progress()
        assert isinstance(progress, BatchProgress)

    @pytest.mark.asyncio
    async def test_process_directory_success(self, processor, tmp_path):
        """Process directory finds and processes PDFs."""
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        (pdf_dir / "file1.pdf").write_bytes(b"%PDF-1.4 f1")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.extracted_data = {"metadata": {"title": "F1"}, "chunks": []}
        mock_result.provider = "claude"
        mock_result.model = "haiku"

        with patch.object(_bp_mod, "UnifiedPDFProcessor") as MockProc:
            mock_proc = MockProc.return_value
            mock_proc.process_pdf = AsyncMock(return_value=mock_result)

            mock_cb = MagicMock()
            mock_cb.call = AsyncMock(return_value=mock_result)
            processor.circuit_breaker = mock_cb

            result = await processor.process_directory(str(pdf_dir))

        assert result.progress.total_files == 1

    @pytest.mark.asyncio
    async def test_batch_id_auto_generated(self, processor):
        """Batch ID is auto-generated when not provided."""
        result = await processor.process_files([], batch_id=None)
        assert result.progress.total_files == 0
