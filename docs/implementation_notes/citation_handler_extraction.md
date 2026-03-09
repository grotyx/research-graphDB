# Citation Handler Extraction Summary

**Date**: 2025-12-21
**Task**: Extract citation methods from medical_kag_server.py into handlers/citation_handler.py

## Extracted Methods

### 1. `draft_with_citations()` (Lines 4700-4815)
**Purpose**: 주제에 대해 자동으로 관련 논문을 검색하고 인용 가능한 형태로 반환

**Parameters**:
- `topic: str` - 작성할 주제
- `section_type: str = "introduction"` - 섹션 유형 (introduction, methods, results, discussion, conclusion)
- `max_citations: int = 5` - 최대 인용 수
- `language: str = "korean"` - 출력 언어 (korean, english)

**Returns**: Dict with citations and references

**Key Operations**:
1. Searches related papers using `server.search()`
2. Constructs citation information from metadata (authors, year, title)
3. Generates citation keys (e.g., "Kim et al., 2023")
4. Creates citation entries with usage suggestions
5. Builds reference list

### 2. `_suggest_citation_usage()` (Lines 4816-4865)
**Purpose**: 인용 사용 제안 생성

**Parameters**:
- `target_section: str` - 작성 중인 섹션
- `source_section: str` - 인용 출처 섹션
- `content: str` - 내용 (현재 미사용)
- `language: str` - 언어

**Returns**: Suggestion string

**Logic**:
- Maps target section × source section to usage suggestions
- Supports Korean and English suggestions
- Provides context-specific citation guidance (e.g., "Use for background" for introduction)

### 3. `_get_citation_guide()` (Lines 6071-6116)
**Purpose**: 섹션별 인용 가이드 반환

**Parameters**:
- `section_type: str` - 섹션 유형
- `language: str` - 언어

**Returns**: Formatted guide string

**Content**:
- Introduction: 연구 배경과 필요성 설명 시 인용 가이드
- Methods: 방법론 근거 제시 시 인용 가이드
- Results: 결과 해석 시 비교 대상 인용 가이드
- Discussion: 선행 연구 비교 시 인용 가이드
- Conclusion: 핵심 발견 의의 강조 시 인용 가이드

### 4. `_get_abstract_from_sections()` (Lines 6258-6272)
**Purpose**: 섹션 경계에서 초록 추출

**Parameters**:
- `section_boundaries: list` - 섹션 경계 리스트
- `full_text: str` - 전체 텍스트

**Returns**: Extracted abstract string

**Logic**:
- Searches for section with type 'abstract'
- Extracts text using start_char and end_char
- Fallback: Returns first 2000 characters if abstract not found

### 5. `_determine_tier()` (Lines 6273-6283)
**Purpose**: 섹션 타입에 따른 Tier 결정

**Parameters**:
- `section_type: str` - 섹션 타입

**Returns**: "tier1" (hardcoded)

**Note**: Tier 구분이 제거되어 모든 청크는 tier1으로 처리됨. 섹션 타입은 메타데이터로만 유지.

## File Structure

### Created File
`src/src/medical_mcp/handlers/citation_handler.py`

### Class Design
```python
class CitationHandler:
    def __init__(self, server: "MedicalKAGServer"):
        self.server = server

    # Public method
    async def draft_with_citations(...) -> dict

    # Private helper methods
    def _suggest_citation_usage(...) -> str
    def _get_citation_guide(...) -> str
    def _get_abstract_from_sections(...) -> str
    def _determine_tier(...) -> str
```

### Dependencies
- `logging` - Logger
- `typing.TYPE_CHECKING` - Type hints
- Access to `server.search()` method

### Integration
- Added to `src/src/medical_mcp/handlers/__init__.py`
- Exported in `__all__` list
- Import: `from .citation_handler import CitationHandler`

## Implementation Notes

1. **Server Access**: Handler stores reference to parent server instance to access:
   - `server.search()` for paper retrieval
   - Other server components as needed

2. **Method Signatures**: All method signatures kept identical to original implementation

3. **Error Handling**: Preserved try-except blocks with proper logging

4. **Type Hints**: Uses `TYPE_CHECKING` to avoid circular imports

5. **Documentation**: All docstrings preserved with Korean descriptions

## Usage Example

```python
from medical_mcp.handlers import CitationHandler

# In MedicalKAGServer
citation_handler = CitationHandler(self)

# Draft with citations
result = await citation_handler.draft_with_citations(
    topic="척추 내시경 수술의 효과",
    section_type="introduction",
    max_citations=5,
    language="korean"
)
```

## Testing Recommendations

1. Test citation generation with various topics
2. Verify language switching (Korean/English)
3. Test different section types (introduction, methods, results, discussion, conclusion)
4. Verify citation key generation with different author formats
5. Test edge cases (no results, single author, multiple authors)
6. Validate abstract extraction from different document structures

## Next Steps

1. Update `medical_kag_server.py` to use `CitationHandler` instance
2. Create unit tests for citation handler methods
3. Consider adding citation format options (APA, MLA, Chicago, Vancouver)
4. Add citation deduplication logic for multiple references to same paper
5. Implement citation network visualization
