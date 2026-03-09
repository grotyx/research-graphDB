"""Gemini PDF Processor v2.2 (Deprecated - Re-export Module).

.. deprecated:: 4.2.0
    이 모듈은 deprecated 되었습니다.
    모든 클래스와 함수는 `unified_pdf_processor.py`에서 re-export됩니다.
    새 코드에서는 직접 `unified_pdf_processor`를 사용하세요.

Migration Guide:
    # Before (deprecated)
    from builder.gemini_vision_processor import GeminiPDFProcessor, VisionProcessorResult

    # After (recommended)
    from builder.unified_pdf_processor import UnifiedPDFProcessor, VisionProcessorResult
    processor = UnifiedPDFProcessor(provider="gemini")  # Gemini 사용 시

이 모듈은 하위 호환성을 위해 유지됩니다. 모든 dataclass와 함수는
unified_pdf_processor에서 import하여 re-export합니다.
"""

import warnings
import logging
from typing import Optional

# Deprecation warning at import time
warnings.warn(
    "gemini_vision_processor 모듈은 deprecated 되었습니다. "
    "모든 클래스는 unified_pdf_processor에서 re-export됩니다. "
    "새 코드에서는 직접 unified_pdf_processor를 사용하세요.",
    DeprecationWarning,
    stacklevel=2
)

logger = logging.getLogger(__name__)

# =============================================================================
# Re-export all dataclasses from unified_pdf_processor
# =============================================================================

from builder.unified_pdf_processor import (
    # Enums
    LLMProvider,
    ChunkMode,

    # Data Classes
    PICOData,
    StatisticsData,
    # TableData, FigureData 삭제됨 (v3.0)
    ExtractedChunk,
    ExtractedOutcome,
    ComplicationData,
    SpineMetadata,
    ExtractedMetadata,
    ImportantCitation,

    # Result Classes
    ProcessorResult,
    VisionProcessorResult,

    # Main Processor
    UnifiedPDFProcessor,

    # Factory
    create_pdf_processor,
)

# =============================================================================
# Legacy Alias for backward compatibility
# =============================================================================

# GeminiPDFProcessor는 UnifiedPDFProcessor(provider="gemini")의 alias
class GeminiPDFProcessor(UnifiedPDFProcessor):
    """GeminiPDFProcessor (deprecated).

    .. deprecated:: 4.2.0
        Use UnifiedPDFProcessor(provider="gemini") instead.

    하위 호환성을 위한 래퍼 클래스입니다.
    내부적으로 UnifiedPDFProcessor를 Gemini provider로 초기화합니다.
    """

    def __init__(self, model: Optional[str] = None, chunk_mode: ChunkMode = ChunkMode.BALANCED):
        """Initialize with Gemini provider.

        Args:
            model: Gemini 모델 ID (기본값: gemini-2.5-flash)
            chunk_mode: 청크 생성 모드
        """
        warnings.warn(
            "GeminiPDFProcessor는 deprecated 되었습니다. "
            "UnifiedPDFProcessor(provider='gemini')를 사용하세요.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(provider="gemini", model=model)


# =============================================================================
# __all__ for explicit exports
# =============================================================================

__all__ = [
    # Enums
    "LLMProvider",
    "ChunkMode",

    # Data Classes
    "PICOData",
    "StatisticsData",
    "TableData",
    "FigureData",
    "ExtractedChunk",
    "ExtractedOutcome",
    "ComplicationData",
    "SpineMetadata",
    "ExtractedMetadata",
    "ImportantCitation",

    # Result Classes
    "ProcessorResult",
    "VisionProcessorResult",

    # Processors
    "UnifiedPDFProcessor",
    "GeminiPDFProcessor",  # deprecated alias

    # Factory
    "create_pdf_processor",
]
