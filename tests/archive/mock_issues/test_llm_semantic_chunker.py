"""LLM Semantic Chunker 테스트."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.builder.llm_semantic_chunker import (
    LLMSemanticChunker,
    SemanticChunk,
    ChunkingConfig,
    ChunkingError
)
from src.builder.llm_section_classifier import SectionBoundary, SECTION_TIERS
from src.llm.gemini_client import GeminiClient
from src.core.text_chunker import TieredTextChunker


class TestSemanticChunk:
    """SemanticChunk 테스트."""

    def test_creation(self):
        """기본 생성 테스트."""
        chunk = SemanticChunk(
            chunk_id="doc1_abstract_001",
            content="This is a test chunk with some content.",
            section_type="abstract",
            tier=1,
            topic_summary="Test chunk summary",
            is_complete_thought=True,
            contains_finding=False,
            char_start=0,
            char_end=40,
            word_count=8
        )
        assert chunk.chunk_id == "doc1_abstract_001"
        assert chunk.section_type == "abstract"
        assert chunk.tier == 1
        assert chunk.is_complete_thought is True

    def test_optional_fields(self):
        """선택적 필드 테스트."""
        chunk = SemanticChunk(
            chunk_id="doc1_methods_001",
            content="Methods content with Table 1 reference.",
            section_type="methods",
            tier=2,
            topic_summary="Methods summary",
            is_complete_thought=True,
            contains_finding=False,
            char_start=100,
            char_end=200,
            word_count=6,
            subsection="Statistical Analysis",
            has_table_reference=True,
            has_figure_reference=False
        )
        assert chunk.subsection == "Statistical Analysis"
        assert chunk.has_table_reference is True
        assert chunk.has_figure_reference is False


class TestChunkingConfig:
    """ChunkingConfig 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        config = ChunkingConfig()
        assert config.target_min_words == 300
        assert config.target_max_words == 500
        assert config.hard_max_words == 800

    def test_custom_values(self):
        """커스텀 값 테스트."""
        config = ChunkingConfig(
            target_min_words=200,
            target_max_words=400,
            hard_max_words=600
        )
        assert config.target_min_words == 200
        assert config.target_max_words == 400


class TestLLMSemanticChunker:
    """LLMSemanticChunker 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.fixture
    def chunker(self, mock_gemini_client):
        """테스트용 청커."""
        return LLMSemanticChunker(
            gemini_client=mock_gemini_client,
            config=ChunkingConfig(),
            fallback_chunker=TieredTextChunker()
        )

    @pytest.mark.asyncio
    async def test_chunk_short_section(self, chunker, mock_gemini_client):
        """짧은 섹션 청킹."""
        text = "This is a short abstract about the study. " * 5  # ~50 words

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": text,
                    "topic_summary": "Short abstract summary",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": 0,
                    "char_end": len(text)
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_section(
            text, "abstract", "doc1"
        )

        assert len(chunks) == 1
        assert chunks[0].section_type == "abstract"
        assert chunks[0].tier == 1  # abstract is tier 1

    @pytest.mark.asyncio
    async def test_chunk_empty_text(self, chunker):
        """빈 텍스트 처리."""
        chunks = await chunker.chunk_section("", "methods", "doc1")
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_chunk_whitespace_only(self, chunker):
        """공백만 있는 텍스트 처리."""
        chunks = await chunker.chunk_section("   \n\n   ", "methods", "doc1")
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_chunk_methods_section(self, chunker, mock_gemini_client):
        """Methods 섹션 청킹."""
        # 충분히 긴 텍스트 (각 청크가 병합되지 않도록)
        text = """
        Study Design
        We conducted a prospective randomized controlled trial at three centers.
        The study was approved by the institutional review board and all participants
        provided written informed consent. Randomization was performed using a
        computer-generated sequence with allocation concealment. The trial was
        registered at ClinicalTrials.gov before enrollment began. """ + "Additional details. " * 30 + """

        Participants
        Inclusion criteria were: age over 18 years, confirmed diagnosis.
        Patients with the following conditions were excluded from the study:
        severe comorbidities, previous surgical interventions in the affected area,
        and contraindications to the study medication. """ + "More patient info. " * 30 + """

        Statistical Analysis
        Data were analyzed using SPSS version 25. Continuous variables were
        compared using t-tests and categorical variables using chi-square tests.
        """ + "Statistical details. " * 30

        # 각 청크가 충분히 커서 병합되지 않도록
        chunk1_content = text[:len(text)//3]
        chunk2_content = text[len(text)//3:2*len(text)//3]
        chunk3_content = text[2*len(text)//3:]

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": chunk1_content,
                    "topic_summary": "Study design description",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": 0,
                    "char_end": len(text)//3,
                    "subsection": "Study Design"
                },
                {
                    "content": chunk2_content,
                    "topic_summary": "Participant criteria",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": len(text)//3,
                    "char_end": 2*len(text)//3,
                    "subsection": "Participants"
                },
                {
                    "content": chunk3_content,
                    "topic_summary": "Statistical methods",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": 2*len(text)//3,
                    "char_end": len(text),
                    "subsection": "Statistical Analysis"
                }
            ],
            "total_chunks": 3
        }

        chunks = await chunker.chunk_section(
            text, "methods", "doc1"
        )

        # 청크가 생성되어야 함 (작은 청크는 병합될 수 있음)
        assert len(chunks) >= 1
        assert all(c.section_type == "methods" for c in chunks)
        assert all(c.tier == 2 for c in chunks)  # methods is tier 2

    @pytest.mark.asyncio
    async def test_chunk_results_with_findings(self, chunker, mock_gemini_client):
        """연구 결과 포함 청크 식별."""
        text = """
        Primary Outcome
        The intervention group showed significantly better outcomes
        (85% vs 65%, p<0.001). The effect size was large (d=0.8).

        Secondary Outcomes
        No significant differences were found in secondary measures.
        """

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": "Primary Outcome\nThe intervention group showed significantly better outcomes (85% vs 65%, p<0.001). The effect size was large (d=0.8).",
                    "topic_summary": "Primary outcome showing intervention effectiveness",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 0,
                    "char_end": 150
                },
                {
                    "content": "Secondary Outcomes\nNo significant differences were found in secondary measures.",
                    "topic_summary": "Secondary outcomes with no significant findings",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 150,
                    "char_end": len(text)
                }
            ],
            "total_chunks": 2
        }

        chunks = await chunker.chunk_section(
            text, "results", "doc1"
        )

        finding_chunks = [c for c in chunks if c.contains_finding]
        assert len(finding_chunks) >= 1

    @pytest.mark.asyncio
    async def test_table_reference_detection(self, chunker, mock_gemini_client):
        """표 참조 감지."""
        text = "As shown in Table 1, the results indicate significant improvement."

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": text,
                    "topic_summary": "Results with table reference",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 0,
                    "char_end": len(text)
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_section(text, "results", "doc1")

        assert len(chunks) == 1
        assert chunks[0].has_table_reference is True

    @pytest.mark.asyncio
    async def test_figure_reference_detection(self, chunker, mock_gemini_client):
        """그림 참조 감지."""
        text = "Figure 2 shows the survival curves for both groups."

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": text,
                    "topic_summary": "Figure showing survival curves",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 0,
                    "char_end": len(text)
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_section(text, "results", "doc1")

        assert len(chunks) == 1
        assert chunks[0].has_figure_reference is True

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, chunker, mock_gemini_client):
        """LLM 실패 시 Fallback."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        text = "Some content to chunk. " * 10

        chunks = await chunker.chunk_section(text, "methods", "doc1")

        # Fallback 결과 확인
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_no_fallback_returns_single_chunk(self, mock_gemini_client):
        """Fallback 없이 실패 시 단일 청크 반환."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        chunker = LLMSemanticChunker(
            gemini_client=mock_gemini_client,
            fallback_chunker=None
        )

        text = "Some content without fallback support."
        chunks = await chunker.chunk_section(text, "methods", "doc1")

        assert len(chunks) == 1
        assert chunks[0].topic_summary == "[Failed to generate summary]"

    @pytest.mark.asyncio
    async def test_chunk_document_multiple_sections(self, chunker, mock_gemini_client):
        """전체 문서 청킹."""
        sections = [
            SectionBoundary("abstract", 0, 100, 0.9, 1),
            SectionBoundary("methods", 100, 300, 0.9, 2),
            SectionBoundary("results", 300, 500, 0.9, 1),
        ]
        full_text = "A" * 100 + "M" * 200 + "R" * 200

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": "Chunked content",
                    "topic_summary": "Summary",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": 0,
                    "char_end": 100
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_document(
            sections, full_text, "doc1"
        )

        # 모든 섹션에서 청크 생성
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_tier_assignment(self, chunker, mock_gemini_client):
        """Tier 올바르게 할당."""
        # Tier 1 섹션
        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": "Abstract content",
                    "topic_summary": "Summary",
                    "is_complete_thought": True,
                    "contains_finding": False,
                    "char_start": 0,
                    "char_end": 20
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_section("Abstract content", "abstract", "doc1")
        assert chunks[0].tier == 1

        # Tier 2 섹션
        chunks = await chunker.chunk_section("Methods content", "methods", "doc1")
        assert chunks[0].tier == 2

    def test_generate_chunk_id(self, chunker):
        """청크 ID 생성 테스트."""
        chunk_id = chunker._generate_chunk_id("doc123", "results", 5)
        assert chunk_id == "doc123_results_005"

    def test_split_into_paragraphs(self, chunker):
        """단락 분할 테스트."""
        text = """First paragraph content.

Second paragraph content.

Third paragraph content."""

        paragraphs = chunker._split_into_paragraphs(text)

        assert len(paragraphs) == 3
        assert "First paragraph" in paragraphs[0]["text"]
        assert "Second paragraph" in paragraphs[1]["text"]

    def test_group_paragraphs(self, chunker):
        """단락 그룹화 테스트."""
        paragraphs = [
            {"text": "Short " * 100, "start": 0, "end": 600},  # 100 words
            {"text": "Medium " * 200, "start": 600, "end": 2000},  # 200 words
            {"text": "Long " * 300, "start": 2000, "end": 4000},  # 300 words
        ]

        groups = chunker._group_paragraphs(paragraphs)

        # 모든 그룹이 적절한 크기
        for group in groups:
            word_count = len(group["text"].split())
            assert word_count <= 2000

    def test_validate_chunks_empty(self, chunker):
        """빈 청크 목록 검증."""
        assert chunker._validate_chunks([], 100) is False

    def test_validate_chunks_low_coverage(self, chunker):
        """낮은 커버리지 검증."""
        chunks = [
            SemanticChunk(
                chunk_id="test_001",
                content="Short",
                section_type="abstract",
                tier=1,
                topic_summary="Summary",
                is_complete_thought=True,
                contains_finding=False,
                char_start=0,
                char_end=10,  # 10% 커버리지
                word_count=1
            )
        ]
        assert chunker._validate_chunks(chunks, 100) is False

    def test_validate_chunks_valid(self, chunker):
        """유효한 청크 검증."""
        chunks = [
            SemanticChunk(
                chunk_id="test_001",
                content="First chunk content",
                section_type="abstract",
                tier=1,
                topic_summary="Summary",
                is_complete_thought=True,
                contains_finding=False,
                char_start=0,
                char_end=50,
                word_count=3
            ),
            SemanticChunk(
                chunk_id="test_002",
                content="Second chunk content",
                section_type="abstract",
                tier=1,
                topic_summary="Summary",
                is_complete_thought=True,
                contains_finding=False,
                char_start=50,
                char_end=100,
                word_count=3
            )
        ]
        assert chunker._validate_chunks(chunks, 100) is True

    def test_merge_two_chunks(self, chunker):
        """두 청크 병합 테스트."""
        chunk1 = SemanticChunk(
            chunk_id="test_001",
            content="First chunk",
            section_type="results",
            tier=1,
            topic_summary="First summary",
            is_complete_thought=True,
            contains_finding=True,
            char_start=0,
            char_end=50,
            word_count=2
        )
        chunk2 = SemanticChunk(
            chunk_id="test_002",
            content="Second chunk",
            section_type="results",
            tier=1,
            topic_summary="Second summary",
            is_complete_thought=True,
            contains_finding=False,
            char_start=50,
            char_end=100,
            word_count=2
        )

        merged = chunker._merge_two_chunks(chunk1, chunk2)

        assert "First chunk" in merged.content
        assert "Second chunk" in merged.content
        assert merged.char_start == 0
        assert merged.char_end == 100
        assert merged.contains_finding is True  # OR of both

    def test_merge_small_chunks(self, chunker):
        """작은 청크 병합 테스트."""
        # 매우 작은 청크들
        chunks = [
            SemanticChunk(
                chunk_id="test_001",
                content="Short " * 10,  # 10 words
                section_type="methods",
                tier=2,
                topic_summary="Summary 1",
                is_complete_thought=True,
                contains_finding=False,
                char_start=0,
                char_end=60,
                word_count=10
            ),
            SemanticChunk(
                chunk_id="test_002",
                content="Another " * 10,  # 10 words
                section_type="methods",
                tier=2,
                topic_summary="Summary 2",
                is_complete_thought=True,
                contains_finding=False,
                char_start=60,
                char_end=120,
                word_count=10
            ),
            SemanticChunk(
                chunk_id="test_003",
                content="Normal " * 200,  # 200 words
                section_type="methods",
                tier=2,
                topic_summary="Summary 3",
                is_complete_thought=True,
                contains_finding=False,
                char_start=120,
                char_end=1500,
                word_count=200
            )
        ]

        merged = chunker._merge_small_chunks(chunks)

        # 작은 청크들이 병합됨
        assert len(merged) < len(chunks)


class TestLLMSemanticChunkerIntegration:
    """통합 테스트 (실제 API 없이)."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_full_document_chunking(self, mock_gemini_client):
        """전체 문서 청킹 흐름."""
        chunker = LLMSemanticChunker(
            gemini_client=mock_gemini_client
        )

        paper_text = """ABSTRACT
Background: Type 2 diabetes is a major health concern affecting millions worldwide.
Methods: We conducted a systematic review of randomized controlled trials.
Results: We found 50 relevant studies showing significant benefits.
Conclusion: Early intervention is key to managing diabetes effectively.

METHODS
Search Strategy: We searched PubMed, MEDLINE, and Cochrane Library databases.
Inclusion criteria: Randomized controlled trials published between 2010-2023.
Data extraction: Two reviewers independently extracted data using standardized forms.

RESULTS
Study Selection: Of 500 identified studies, 50 met our inclusion criteria.
Primary Outcome: The pooled effect size was 0.45 (95% CI: 0.30-0.60, p<0.001).
Secondary Outcomes: Quality of life improved significantly in intervention groups.
Subgroup Analysis: Benefits were consistent across age groups (see Table 1).

DISCUSSION
Our findings suggest that intervention X is effective for type 2 diabetes management.
This is consistent with previous meta-analyses by Smith et al. and Jones et al.
Limitations include the heterogeneity of included studies.

CONCLUSION
In conclusion, intervention X shows promise for diabetes management.
Further research is needed to optimize treatment protocols.
"""

        sections = [
            SectionBoundary("abstract", 0, 300, 0.95, 1),
            SectionBoundary("methods", 300, 550, 0.94, 2),
            SectionBoundary("results", 550, 900, 0.93, 1),
            SectionBoundary("discussion", 900, 1150, 0.90, 2),
            SectionBoundary("conclusion", 1150, len(paper_text), 0.91, 1),
        ]

        # 각 섹션에 대한 LLM 응답 설정
        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": "Sample chunk content for testing purposes.",
                    "topic_summary": "Test chunk summary",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 0,
                    "char_end": 100
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_document(sections, paper_text, "test_paper")

        # 청크가 생성되어야 함
        assert len(chunks) >= 1

        # 청크 ID가 순차적이어야 함
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == f"test_paper_{i:03d}"

    @pytest.mark.asyncio
    async def test_special_characters_handling(self, mock_gemini_client):
        """특수 문자 포함 텍스트 처리."""
        chunker = LLMSemanticChunker(
            gemini_client=mock_gemini_client
        )

        text = "Results: p<0.001, CI [0.5-0.8], β=0.3 ± 0.1, OR=2.5 (95% CI: 1.2-5.0)"

        mock_gemini_client.generate_json.return_value = {
            "chunks": [
                {
                    "content": text,
                    "topic_summary": "Statistical results with p-values and confidence intervals",
                    "is_complete_thought": True,
                    "contains_finding": True,
                    "char_start": 0,
                    "char_end": len(text)
                }
            ],
            "total_chunks": 1
        }

        chunks = await chunker.chunk_section(text, "results", "doc1")

        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].contains_finding is True
