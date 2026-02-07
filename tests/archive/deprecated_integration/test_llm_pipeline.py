"""LLM Pipeline Integration Tests.

전체 LLM 파이프라인의 통합 테스트:
1. PDF 텍스트 → LLM 섹션 분류
2. 섹션 → LLM 의미 청킹
3. 청크 → LLM 메타데이터 추출
4. 청크+메타데이터 → Vector DB 저장
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from src.llm.gemini_client import GeminiClient
from src.builder.llm_section_classifier import LLMSectionClassifier, SectionBoundary, SECTION_TIERS
from src.builder.llm_semantic_chunker import LLMSemanticChunker, SemanticChunk
from src.builder.llm_metadata_extractor import LLMMetadataExtractor, ChunkMetadata, PICOElements, StatsInfo
from src.storage.vector_db import TieredVectorDB, TextChunk, SearchFilters


# 테스트용 샘플 논문 텍스트
SAMPLE_PAPER_TEXT = """ABSTRACT
Background: Diabetes mellitus type 2 is a major public health concern affecting millions worldwide.
Objectives: This randomized controlled trial evaluated the efficacy of metformin versus placebo
in newly diagnosed patients with type 2 diabetes.
Methods: We enrolled 500 patients aged 40-70 years from 10 academic medical centers.
Results: After 12 weeks, the metformin group showed significantly lower HbA1c levels
(7.2% vs 8.1%, p<0.001) and better glycemic control (OR 2.3, 95% CI: 1.8-3.0).
Conclusions: Metformin is effective as first-line therapy for type 2 diabetes management.

INTRODUCTION
Type 2 diabetes affects over 400 million people globally and is associated with significant
morbidity and mortality. Previous studies have shown that early intervention improves outcomes.
Smith et al. (2020) reported that lifestyle modifications alone are often insufficient.

METHODS
Study Design: This was a multicenter, double-blind, randomized controlled trial conducted
between January 2020 and December 2022.

Patient Selection: We included patients aged 40-70 years with newly diagnosed type 2 diabetes
(HbA1c 7.0-10.0%) and excluded those with renal impairment or prior antidiabetic medication.

Intervention: Patients were randomized 1:1 to receive metformin 500mg twice daily or placebo.

Outcomes: The primary outcome was change in HbA1c at 12 weeks. Secondary outcomes included
fasting glucose, body weight, and adverse events.

Statistical Analysis: We calculated that 500 patients would provide 90% power to detect a
0.5% difference in HbA1c. Analysis was by intention-to-treat.

RESULTS
Patient Characteristics: Of 500 enrolled patients, mean age was 55.2 years (SD 8.5),
52% were male, and mean baseline HbA1c was 8.0% (SD 0.9).

Primary Outcome: The metformin group showed significantly greater HbA1c reduction
(-1.2% vs -0.3%, difference -0.9%, 95% CI: -1.1 to -0.7, p<0.001).

Secondary Outcomes: Fasting glucose decreased more in the metformin group (25 mg/dL vs 5 mg/dL).
Body weight decreased by 2.1 kg in the metformin group versus 0.3 kg in placebo.

Safety: The most common adverse event was gastrointestinal upset (15% vs 3%).
No serious adverse events were reported.

DISCUSSION
Our findings demonstrate that metformin is highly effective as first-line therapy for
type 2 diabetes. The HbA1c reduction of 0.9% is clinically significant and consistent
with previous meta-analyses (Johnson et al., 2019).

Strengths of this study include the large sample size, multicenter design, and
rigorous methodology. Limitations include the relatively short follow-up period.

These results support current guidelines recommending metformin as initial pharmacotherapy
for type 2 diabetes when lifestyle interventions are insufficient.

CONCLUSION
In conclusion, metformin 500mg twice daily significantly improves glycemic control in
newly diagnosed type 2 diabetes patients. Our findings support its use as first-line therapy.

REFERENCES
1. Smith J, et al. Diabetes Care. 2020;43(1):100-110.
2. Johnson A, et al. Lancet. 2019;394:1500-1510.
"""


class TestLLMPipelineIntegration:
    """LLM 파이프라인 통합 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.fixture
    def section_classifier(self, mock_gemini_client):
        """LLM 섹션 분류기."""
        return LLMSectionClassifier(gemini_client=mock_gemini_client)

    @pytest.fixture
    def semantic_chunker(self, mock_gemini_client):
        """LLM 의미 청킹."""
        return LLMSemanticChunker(gemini_client=mock_gemini_client)

    @pytest.fixture
    def metadata_extractor(self, mock_gemini_client):
        """LLM 메타데이터 추출기."""
        return LLMMetadataExtractor(gemini_client=mock_gemini_client)

    @pytest.fixture
    def vector_db(self):
        """In-memory Vector DB."""
        return TieredVectorDB(persist_directory=None)

    @pytest.mark.asyncio
    async def test_full_pipeline_section_classification(
        self, section_classifier, mock_gemini_client
    ):
        """Phase 1: 섹션 분류 통합 테스트."""
        # Mock LLM 응답 설정
        mock_gemini_client.generate_json.return_value = {
            "sections": [
                {"section_type": "abstract", "start_char": 0, "end_char": 700, "confidence": 0.95, "heading": "ABSTRACT"},
                {"section_type": "introduction", "start_char": 700, "end_char": 1100, "confidence": 0.90, "heading": "INTRODUCTION"},
                {"section_type": "methods", "start_char": 1100, "end_char": 2200, "confidence": 0.92, "heading": "METHODS"},
                {"section_type": "results", "start_char": 2200, "end_char": 3200, "confidence": 0.93, "heading": "RESULTS"},
                {"section_type": "discussion", "start_char": 3200, "end_char": 4000, "confidence": 0.88, "heading": "DISCUSSION"},
                {"section_type": "conclusion", "start_char": 4000, "end_char": 4300, "confidence": 0.91, "heading": "CONCLUSION"},
                {"section_type": "references", "start_char": 4300, "end_char": len(SAMPLE_PAPER_TEXT), "confidence": 0.95, "heading": "REFERENCES"},
            ]
        }

        sections = await section_classifier.classify(SAMPLE_PAPER_TEXT)

        # 섹션 검증
        assert len(sections) >= 5  # 최소 5개 섹션
        section_types = [s.section_type for s in sections]
        assert "abstract" in section_types
        assert "results" in section_types

        # Tier 검증
        for section in sections:
            if section.section_type == "abstract":
                assert section.tier == 1  # Tier 1
            elif section.section_type == "methods":
                assert section.tier == 2  # Tier 2

    @pytest.mark.asyncio
    async def test_full_pipeline_semantic_chunking(
        self, semantic_chunker, mock_gemini_client
    ):
        """Phase 2: 의미 청킹 통합 테스트."""
        # 섹션 경계 (수동 설정)
        sections = [
            SectionBoundary("abstract", 0, 700, 0.95, 1, "ABSTRACT"),
            SectionBoundary("results", 2200, 3200, 0.93, 1, "RESULTS"),
        ]

        # Mock LLM 응답 - abstract 섹션
        mock_gemini_client.generate_json.side_effect = [
            {
                "chunks": [
                    {
                        "content": "Background: Diabetes mellitus type 2 is a major public health concern.",
                        "topic_summary": "Background on diabetes prevalence",
                        "is_complete_thought": True,
                        "contains_finding": False,
                        "char_start": 9,
                        "char_end": 80,
                        "subsection": "Background"
                    },
                    {
                        "content": "This randomized controlled trial evaluated the efficacy of metformin versus placebo in newly diagnosed patients.",
                        "topic_summary": "Study objective and design",
                        "is_complete_thought": True,
                        "contains_finding": False,
                        "char_start": 80,
                        "char_end": 200,
                        "subsection": "Objectives"
                    }
                ]
            },
            {
                "chunks": [
                    {
                        "content": "After 12 weeks, the metformin group showed significantly lower HbA1c levels (7.2% vs 8.1%, p<0.001).",
                        "topic_summary": "Primary outcome results showing HbA1c improvement",
                        "is_complete_thought": True,
                        "contains_finding": True,
                        "char_start": 0,
                        "char_end": 100,
                        "subsection": "Primary Outcome"
                    }
                ]
            }
        ]

        all_chunks = []
        for section in sections:
            section_text = SAMPLE_PAPER_TEXT[section.start_char:section.end_char]
            chunks = await semantic_chunker.chunk_section(
                section_text, section.section_type, "test_doc", section.start_char
            )
            all_chunks.extend(chunks)

        # 청크 검증
        assert len(all_chunks) >= 1
        for chunk in all_chunks:
            assert chunk.content
            assert chunk.section_type in ["abstract", "results"]
            assert chunk.chunk_id.startswith("test_doc")

    @pytest.mark.asyncio
    async def test_full_pipeline_metadata_extraction(
        self, metadata_extractor, mock_gemini_client
    ):
        """Phase 3: 메타데이터 추출 통합 테스트."""
        # 테스트용 청크들
        chunks = [
            "We enrolled 500 patients aged 40-70 years with newly diagnosed type 2 diabetes. Patients were randomized to receive metformin 500mg or placebo.",
            "The metformin group showed significantly lower HbA1c levels (7.2% vs 8.1%, p<0.001) and better glycemic control (OR 2.3, 95% CI: 1.8-3.0)."
        ]

        # Mock LLM 응답
        mock_gemini_client.generate_json.side_effect = [
            {
                "summary": "Study enrolled 500 diabetic patients randomized to metformin or placebo",
                "keywords": ["diabetes", "metformin", "RCT", "HbA1c"],
                "pico": {
                    "population": "patients aged 40-70 with type 2 diabetes",
                    "intervention": "metformin 500mg twice daily",
                    "comparison": "placebo",
                    "outcome": None
                },
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": ["diabetes", "metformin", "HbA1c"]
            },
            {
                "summary": "Metformin significantly reduced HbA1c compared to placebo",
                "keywords": ["HbA1c", "efficacy", "statistical significance"],
                "pico": None,
                "statistics": {
                    "p_values": ["p<0.001"],
                    "effect_sizes": [{"type": "odds_ratio", "value": 2.3, "ci_lower": 1.8, "ci_upper": 3.0}],
                    "confidence_intervals": ["95% CI: 1.8-3.0"],
                    "sample_sizes": [],
                    "statistical_tests": []
                },
                "content_type": "original",
                "is_key_finding": True,
                "medical_terms": ["HbA1c", "glycemic control"]
            }
        ]

        context = "Study on metformin for type 2 diabetes"

        results = await metadata_extractor.extract_batch(
            chunks, context, section_types=["methods", "results"]
        )

        # 메타데이터 검증
        assert len(results) == 2

        # PICO 검증
        assert results[0].pico is not None
        assert "diabetes" in results[0].pico.population.lower()
        assert "metformin" in results[0].pico.intervention.lower()

        # 통계 검증
        assert results[1].statistics is not None
        assert "p<0.001" in results[1].statistics.p_values
        assert results[1].is_key_finding is True

    @pytest.mark.asyncio
    async def test_full_pipeline_vector_db_storage(self, vector_db):
        """Phase 4: Vector DB 저장 통합 테스트."""
        # LLM 처리된 청크 생성
        chunks = [
            TextChunk(
                chunk_id="doc1_chunk1",
                content="Study enrolled 500 diabetic patients.",
                document_id="doc1",
                tier="tier1",
                section="abstract",
                source_type="original",
                evidence_level="1b",
                publication_year=2023,
                title="Metformin RCT",
                # LLM 메타데이터
                summary="Study enrollment details",
                keywords=["diabetes", "metformin", "RCT"],
                pico_population="patients aged 40-70 with type 2 diabetes",
                pico_intervention="metformin 500mg",
                pico_comparison="placebo",
                pico_outcome="HbA1c reduction",
                has_statistics=False,
                llm_processed=True,
                llm_confidence=0.9,
                is_key_finding=False
            ),
            TextChunk(
                chunk_id="doc1_chunk2",
                content="Metformin significantly reduced HbA1c (p<0.001).",
                document_id="doc1",
                tier="tier1",
                section="results",
                source_type="original",
                evidence_level="1b",
                publication_year=2023,
                title="Metformin RCT",
                # LLM 메타데이터
                summary="Primary outcome showing HbA1c reduction",
                keywords=["HbA1c", "efficacy", "p-value"],
                statistics_json=json.dumps({
                    "p_values": ["p<0.001"],
                    "effect_sizes": [{"type": "OR", "value": 2.3}]
                }),
                has_statistics=True,
                llm_processed=True,
                llm_confidence=0.95,
                is_key_finding=True
            )
        ]

        # 임베딩 생성 (Mock)
        embeddings = [vector_db.get_embedding(c.content) for c in chunks]

        # 저장
        added = vector_db.add_documents("tier1", chunks, embeddings)
        assert added == 2

        # 검색
        query_embedding = vector_db.get_embedding("diabetes treatment efficacy")
        results = vector_db.search_tier1(query_embedding, top_k=5)

        assert len(results) >= 1

        # LLM 메타데이터 검증
        result = results[0]
        assert result.llm_confidence > 0
        # summary와 keywords가 파싱되었는지 확인
        assert result.summary or "summary" in result.metadata

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_simulation(
        self,
        vector_db,
        mock_gemini_client
    ):
        """전체 파이프라인 워크플로우 시뮬레이션 테스트.

        실제 LLM 호출 대신 미리 처리된 데이터로 워크플로우 검증.
        """
        document_id = "paper_2023_001"

        # 시뮬레이션: 이미 LLM으로 처리된 결과를 가정
        # (실제 파이프라인에서는 classifier → chunker → extractor 순서로 호출)

        # Step 1: 사전 처리된 섹션 정보 (LLM 섹션 분류기 결과)
        sections = [
            {"type": "abstract", "start": 0, "end": 700, "tier": 1},
            {"type": "results", "start": 2200, "end": 3200, "tier": 1},
        ]

        # Step 2: 사전 처리된 청크 정보 (LLM 의미 청킹 결과)
        semantic_chunks_data = [
            {
                "chunk_id": f"{document_id}_chunk_1",
                "content": "This RCT evaluated metformin versus placebo in type 2 diabetes patients.",
                "section": "abstract",
                "tier": 1,
                "topic_summary": "Study design and objective",
                "contains_finding": False
            },
            {
                "chunk_id": f"{document_id}_chunk_2",
                "content": "Metformin group showed significantly lower HbA1c levels (p<0.001).",
                "section": "results",
                "tier": 1,
                "topic_summary": "Primary efficacy outcome",
                "contains_finding": True
            }
        ]

        # Step 3: 사전 처리된 메타데이터 (LLM 메타데이터 추출기 결과)
        metadata_list = [
            {
                "summary": "RCT comparing metformin and placebo for diabetes",
                "keywords": ["diabetes", "metformin", "RCT"],
                "pico_population": "type 2 diabetes patients",
                "pico_intervention": "metformin",
                "pico_comparison": "placebo",
                "pico_outcome": "HbA1c levels",
                "has_statistics": False,
                "is_key_finding": False,
                "confidence": 0.9,
                "medical_terms": ["diabetes", "metformin", "HbA1c"]
            },
            {
                "summary": "Significant HbA1c reduction with metformin",
                "keywords": ["HbA1c", "efficacy", "p-value"],
                "pico_population": None,
                "pico_intervention": None,
                "pico_comparison": None,
                "pico_outcome": None,
                "has_statistics": True,
                "statistics_json": json.dumps({"p_values": ["p<0.001"]}),
                "is_key_finding": True,
                "confidence": 0.95,
                "medical_terms": ["HbA1c", "glycemic control"]
            }
        ]

        # Step 4: TextChunk 생성 (파이프라인 최종 출력)
        text_chunks = []
        for chunk_data, metadata in zip(semantic_chunks_data, metadata_list):
            text_chunk = TextChunk(
                chunk_id=chunk_data["chunk_id"],
                content=chunk_data["content"],
                document_id=document_id,
                tier="tier1" if chunk_data["tier"] == 1 else "tier2",
                section=chunk_data["section"],
                source_type="original",
                evidence_level="1b",
                publication_year=2023,
                title="Metformin RCT Study",
                summary=metadata["summary"],
                keywords=metadata["keywords"],
                pico_population=metadata.get("pico_population"),
                pico_intervention=metadata.get("pico_intervention"),
                pico_comparison=metadata.get("pico_comparison"),
                pico_outcome=metadata.get("pico_outcome"),
                has_statistics=metadata["has_statistics"],
                statistics_json=metadata.get("statistics_json"),
                llm_processed=True,
                llm_confidence=metadata["confidence"],
                is_key_finding=metadata["is_key_finding"],
                topic_summary=chunk_data["topic_summary"],
                medical_terms=metadata["medical_terms"]
            )
            text_chunks.append(text_chunk)

        # Step 5: Vector DB 저장
        embeddings = [vector_db.get_embedding(c.content) for c in text_chunks]
        added = vector_db.add_documents("tier1", text_chunks, embeddings)
        assert added == 2

        # Step 6: 검색 테스트
        query = "metformin efficacy in diabetes"
        query_embedding = vector_db.get_embedding(query)
        results = vector_db.search_tier1(query_embedding, top_k=10)

        # 이 테스트에서 추가한 문서만 필터링
        our_results = [r for r in results if r.document_id == document_id]
        assert len(our_results) == 2

        # LLM 메타데이터 검증
        for result in our_results:
            assert result.llm_confidence > 0
            # PICO가 있는 청크 확인
            if result.pico_population:
                assert "diabetes" in result.pico_population.lower()
            # 통계가 있는 청크 확인
            if result.has_statistics:
                assert result.is_key_finding is True


class TestPipelineErrorHandling:
    """파이프라인 에러 처리 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_section_classifier_fallback(self, mock_gemini_client):
        """섹션 분류기 Fallback 테스트."""
        classifier = LLMSectionClassifier(gemini_client=mock_gemini_client)

        # LLM 실패 시뮬레이션
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        # Fallback으로 결과 반환 확인
        sections = await classifier.classify(SAMPLE_PAPER_TEXT, use_fallback=True)
        assert len(sections) >= 1  # Fallback 결과

    @pytest.mark.asyncio
    async def test_metadata_extractor_fallback(self, mock_gemini_client):
        """메타데이터 추출기 Fallback 테스트."""
        extractor = LLMMetadataExtractor(gemini_client=mock_gemini_client)

        # LLM 실패 시뮬레이션
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        chunk = "The study showed significant improvement (p<0.05)."
        result = await extractor.extract(chunk, "context")

        # Fallback 결과 확인
        assert result is not None
        assert result.confidence < 1.0  # Fallback은 낮은 신뢰도


class TestPipelinePerformance:
    """파이프라인 성능 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_batch_processing_performance(self, mock_gemini_client):
        """배치 처리 성능 테스트."""
        extractor = LLMMetadataExtractor(gemini_client=mock_gemini_client)

        # 여러 청크 생성
        chunks = [f"Chunk {i} with medical content about treatment." for i in range(10)]

        # Mock 응답
        mock_gemini_client.generate_json.return_value = {
            "summary": "Summary",
            "keywords": ["keyword"],
            "pico": None,
            "statistics": None,
            "content_type": "original",
            "is_key_finding": False,
            "medical_terms": []
        }

        results = await extractor.extract_batch(chunks, "context", concurrency=5)

        assert len(results) == 10
        # LLM이 10번 호출되었는지 확인
        assert mock_gemini_client.generate_json.call_count == 10
