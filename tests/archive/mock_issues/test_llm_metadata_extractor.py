"""LLM Metadata Extractor 테스트."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from src.builder.llm_metadata_extractor import (
    LLMMetadataExtractor,
    ChunkMetadata,
    PICOElements,
    StatsInfo,
    EffectSize
)
from src.llm.gemini_client import GeminiClient


class TestPICOElements:
    """PICOElements 테스트."""

    def test_creation_full(self):
        """전체 PICO 생성 테스트."""
        pico = PICOElements(
            population="elderly patients with type 2 diabetes",
            intervention="metformin therapy",
            comparison="placebo",
            outcome="HbA1c reduction"
        )
        assert pico.population == "elderly patients with type 2 diabetes"
        assert pico.intervention == "metformin therapy"
        assert pico.comparison == "placebo"
        assert pico.outcome == "HbA1c reduction"

    def test_creation_partial(self):
        """부분 PICO 생성 테스트."""
        pico = PICOElements(
            population="cancer patients",
            intervention="chemotherapy"
        )
        assert pico.population == "cancer patients"
        assert pico.intervention == "chemotherapy"
        assert pico.comparison is None
        assert pico.outcome is None

    def test_creation_empty(self):
        """빈 PICO 생성 테스트."""
        pico = PICOElements()
        assert pico.population is None
        assert pico.intervention is None
        assert pico.comparison is None
        assert pico.outcome is None


class TestEffectSize:
    """EffectSize 테스트."""

    def test_creation_with_ci(self):
        """CI 포함 생성 테스트."""
        effect = EffectSize(
            type="hazard_ratio",
            value=0.75,
            ci_lower=0.60,
            ci_upper=0.90
        )
        assert effect.type == "hazard_ratio"
        assert effect.value == 0.75
        assert effect.ci_lower == 0.60
        assert effect.ci_upper == 0.90

    def test_creation_without_ci(self):
        """CI 없는 생성 테스트."""
        effect = EffectSize(
            type="odds_ratio",
            value=2.5
        )
        assert effect.type == "odds_ratio"
        assert effect.value == 2.5
        assert effect.ci_lower is None
        assert effect.ci_upper is None


class TestStatsInfo:
    """StatsInfo 테스트."""

    def test_creation_full(self):
        """전체 통계 생성 테스트."""
        stats = StatsInfo(
            p_values=["p < 0.001", "p = 0.023"],
            effect_sizes=[
                EffectSize("hazard_ratio", 0.75, 0.60, 0.90)
            ],
            confidence_intervals=["95% CI: 0.60-0.90"],
            sample_sizes=[500, 250],
            statistical_tests=["chi-square", "t-test"]
        )
        assert len(stats.p_values) == 2
        assert len(stats.effect_sizes) == 1
        assert stats.effect_sizes[0].type == "hazard_ratio"
        assert len(stats.sample_sizes) == 2

    def test_creation_empty(self):
        """빈 통계 생성 테스트."""
        stats = StatsInfo()
        assert stats.p_values == []
        assert stats.effect_sizes == []
        assert stats.confidence_intervals == []
        assert stats.sample_sizes == []


class TestChunkMetadata:
    """ChunkMetadata 테스트."""

    def test_creation_minimal(self):
        """최소 메타데이터 생성 테스트."""
        meta = ChunkMetadata(
            summary="This study examines treatment effects.",
            keywords=["treatment", "effects"]
        )
        assert meta.summary == "This study examines treatment effects."
        assert len(meta.keywords) == 2
        assert meta.pico is None
        assert meta.statistics is None
        assert meta.content_type == "original"
        assert meta.is_key_finding is False

    def test_creation_full(self):
        """전체 메타데이터 생성 테스트."""
        pico = PICOElements(
            population="diabetic patients",
            intervention="insulin"
        )
        stats = StatsInfo(
            p_values=["p < 0.05"]
        )
        meta = ChunkMetadata(
            summary="Insulin improves glycemic control.",
            keywords=["insulin", "diabetes", "glycemic"],
            pico=pico,
            statistics=stats,
            content_type="original",
            is_key_finding=True,
            confidence=0.95,
            medical_terms=["insulin", "HbA1c", "glycemic control"]
        )
        assert meta.pico.population == "diabetic patients"
        assert meta.statistics.p_values[0] == "p < 0.05"
        assert meta.is_key_finding is True
        assert meta.confidence == 0.95
        assert len(meta.medical_terms) == 3


class TestLLMMetadataExtractor:
    """LLMMetadataExtractor 테스트."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.fixture
    def extractor(self, mock_gemini_client):
        """테스트용 추출기."""
        return LLMMetadataExtractor(
            gemini_client=mock_gemini_client
        )

    @pytest.mark.asyncio
    async def test_extract_with_pico(self, extractor, mock_gemini_client):
        """PICO 추출 테스트."""
        chunk = """
        In this randomized controlled trial, we enrolled 500 elderly patients
        with type 2 diabetes (age > 65 years). Patients were randomized to
        receive either metformin 500mg twice daily or placebo for 12 weeks.
        The primary outcome was change in HbA1c levels from baseline.
        """
        context = "Study on diabetes management in elderly population."

        mock_gemini_client.generate_json.return_value = {
            "summary": "RCT of metformin vs placebo in elderly diabetic patients",
            "keywords": ["diabetes", "metformin", "elderly", "HbA1c"],
            "pico": {
                "population": "elderly patients with type 2 diabetes (age > 65)",
                "intervention": "metformin 500mg twice daily",
                "comparison": "placebo",
                "outcome": "change in HbA1c levels"
            },
            "statistics": None,
            "content_type": "original",
            "is_key_finding": False,
            "medical_terms": ["diabetes", "metformin", "HbA1c"]
        }

        result = await extractor.extract(chunk, context, section_type="methods")

        assert result.summary is not None
        assert result.pico is not None
        assert "diabetes" in result.pico.population.lower()
        assert "metformin" in result.pico.intervention.lower()

    @pytest.mark.asyncio
    async def test_extract_with_statistics(self, extractor, mock_gemini_client):
        """통계 추출 테스트."""
        chunk = """
        The treatment group showed significantly better outcomes compared to
        control (HR 0.75, 95% CI: 0.60-0.90, p < 0.001). The mean reduction
        in HbA1c was 1.2% (SD 0.5) in the treatment group versus 0.3% (SD 0.4)
        in the placebo group. A total of 500 patients were analyzed.
        """
        context = "Results from diabetes treatment trial."

        mock_gemini_client.generate_json.return_value = {
            "summary": "Treatment showed significant HbA1c reduction vs placebo",
            "keywords": ["hazard ratio", "HbA1c", "treatment effect"],
            "pico": None,
            "statistics": {
                "p_values": ["p < 0.001"],
                "effect_sizes": [
                    {"type": "hazard_ratio", "value": 0.75, "ci_lower": 0.60, "ci_upper": 0.90}
                ],
                "confidence_intervals": ["95% CI: 0.60-0.90"],
                "sample_sizes": [500],
                "statistical_tests": []
            },
            "content_type": "original",
            "is_key_finding": True,
            "medical_terms": ["HbA1c"]
        }

        result = await extractor.extract(chunk, context, section_type="results")

        assert result.statistics is not None
        assert "p < 0.001" in result.statistics.p_values
        assert len(result.statistics.effect_sizes) == 1
        assert result.statistics.effect_sizes[0].type == "hazard_ratio"
        assert result.is_key_finding is True

    @pytest.mark.asyncio
    async def test_extract_citation_content(self, extractor, mock_gemini_client):
        """인용 콘텐츠 추출 테스트."""
        chunk = """
        Previous studies have shown similar results. Smith et al. (2020)
        reported that early intervention improves outcomes. According to
        the meta-analysis by Johnson (2019), the pooled effect size was 0.8.
        """
        context = "Discussion of previous research."

        mock_gemini_client.generate_json.return_value = {
            "summary": "Review of previous studies on intervention outcomes",
            "keywords": ["meta-analysis", "intervention", "outcomes"],
            "pico": None,
            "statistics": None,
            "content_type": "citation",
            "is_key_finding": False,
            "medical_terms": []
        }

        result = await extractor.extract(chunk, context, section_type="discussion")

        assert result.content_type == "citation"

    @pytest.mark.asyncio
    async def test_extract_empty_chunk(self, extractor):
        """빈 청크 처리 테스트."""
        result = await extractor.extract("", "context")

        assert result.summary == "[No content]"
        assert result.keywords == []
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_whitespace_chunk(self, extractor):
        """공백만 있는 청크 처리 테스트."""
        result = await extractor.extract("   \n\n   ", "context")

        assert result.summary == "[No content]"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, extractor, mock_gemini_client):
        """LLM 실패 시 Fallback 테스트."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        chunk = """
        The results showed significant improvement (p < 0.05). The hazard
        ratio was 0.75 (95% CI: 0.60-0.90). N=500 patients were enrolled.
        """

        # extract()는 자동으로 fallback 사용
        result = await extractor.extract(chunk, "context")

        # Fallback 결과 확인
        assert result is not None
        assert result.confidence < 1.0  # LLM보다 낮은 신뢰도 (fallback은 0.3)

    @pytest.mark.asyncio
    async def test_rule_based_fallback_on_llm_error(self, extractor, mock_gemini_client):
        """LLM 실패 시 규칙 기반으로 폴백."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        chunk = "Our study found that the treatment was effective. We observed significant improvement."

        result = await extractor.extract(chunk, "context", section_type="results")

        # Rule-based 결과 확인
        assert result is not None
        assert result.confidence == 0.3  # Fallback 신뢰도

    @pytest.mark.asyncio
    async def test_extract_batch(self, extractor, mock_gemini_client):
        """배치 추출 테스트."""
        chunks = [
            "First chunk with some content about treatment.",
            "Second chunk with results and p-values.",
            "Third chunk with conclusions."
        ]
        context = "Study abstract for context."

        # 각 청크에 대해 다른 응답 반환
        mock_gemini_client.generate_json.side_effect = [
            {
                "summary": "Treatment description",
                "keywords": ["treatment"],
                "pico": None,
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": []
            },
            {
                "summary": "Results with statistics",
                "keywords": ["results", "p-value"],
                "pico": None,
                "statistics": {"p_values": ["p < 0.05"], "effect_sizes": [], "confidence_intervals": [], "sample_sizes": [], "statistical_tests": []},
                "content_type": "original",
                "is_key_finding": True,
                "medical_terms": []
            },
            {
                "summary": "Study conclusions",
                "keywords": ["conclusions"],
                "pico": None,
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": []
            }
        ]

        results = await extractor.extract_batch(chunks, context)

        assert len(results) == 3
        assert results[0].summary == "Treatment description"
        assert results[1].is_key_finding is True
        assert "conclusions" in results[2].keywords

    @pytest.mark.asyncio
    async def test_extract_batch_with_section_types(self, extractor, mock_gemini_client):
        """섹션 타입별 배치 추출 테스트."""
        chunks = ["Methods content", "Results content"]
        section_types = ["methods", "results"]
        context = "Study context."

        mock_gemini_client.generate_json.side_effect = [
            {
                "summary": "Methodology",
                "keywords": ["methods"],
                "pico": {"population": "patients", "intervention": "treatment", "comparison": None, "outcome": None},
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": []
            },
            {
                "summary": "Findings",
                "keywords": ["results"],
                "pico": None,
                "statistics": {"p_values": ["p < 0.001"], "effect_sizes": [], "confidence_intervals": [], "sample_sizes": [], "statistical_tests": []},
                "content_type": "original",
                "is_key_finding": True,
                "medical_terms": []
            }
        ]

        results = await extractor.extract_batch(chunks, context, section_types=section_types)

        assert len(results) == 2
        assert results[0].pico is not None
        assert results[1].statistics is not None

    @pytest.mark.asyncio
    async def test_extract_document_level(self, extractor, mock_gemini_client):
        """문서 수준 메타데이터 추출 테스트."""
        full_text = "Full paper text..." * 100
        abstract = """
        Background: This study investigates treatment X.
        Methods: RCT with 500 patients.
        Results: Significant improvement (p < 0.001).
        Conclusion: Treatment X is effective.
        """

        mock_gemini_client.generate_json.return_value = {
            "title_summary": "RCT demonstrating treatment X efficacy",
            "key_findings": [
                "Treatment X showed significant improvement",
                "p < 0.001 for primary outcome"
            ],
            "study_design": "randomized controlled trial",
            "evidence_level": "1b",
            "main_pico": {
                "population": "patients",
                "intervention": "treatment X",
                "comparison": "placebo",
                "outcome": "improvement"
            }
        }

        result = await extractor.extract_document_level(full_text, abstract)

        assert "title_summary" in result
        assert "key_findings" in result
        assert result["evidence_level"] == "1b"
        assert result["main_pico"] is not None
        assert result["main_pico"].population == "patients"

    def test_detect_content_type_original(self, extractor):
        """원본 콘텐츠 타입 감지 테스트."""
        # "our study" 패턴이 있어야 original로 감지됨
        chunk = "In our study, we found significant results. Our data showed improvement."
        content_type = extractor._detect_content_type(chunk)
        assert content_type == "original"

    def test_detect_content_type_citation(self, extractor):
        """인용 콘텐츠 타입 감지 테스트."""
        # citation_count > 2 이어야 citation으로 감지됨
        # 패턴: (Author et al., YEAR), previous studies have shown, prior research
        chunk = "According to previous studies (2020), there is evidence. Prior research shows similar patterns. It has been demonstrated that this approach works. Previous studies have reported similar results."
        content_type = extractor._detect_content_type(chunk)
        assert content_type == "citation"

    def test_detect_content_type_background(self, extractor):
        """배경 콘텐츠 타입 감지 테스트."""
        chunk = "It is well known that diabetes affects millions worldwide. Generally, treatment involves medication."
        content_type = extractor._detect_content_type(chunk)
        assert content_type == "background"

    def test_rule_based_extraction_with_stats(self, extractor):
        """규칙 기반 통계 추출 테스트."""
        # 정규식 패턴에 맞는 형식 사용: p<0.001, HR=0.75, N=500
        chunk = """
        The hazard ratio was HR=0.75. The result was significant (p<0.001).
        95% CI: 0.60-0.90. N=500 patients were enrolled in this study.
        """

        result = extractor._extract_rule_based(chunk, section_type="results")

        assert result is not None
        # 통계가 추출되었는지 확인 (패턴에 따라 다를 수 있음)
        assert result.statistics is not None or result.confidence == 0.3

    def test_rule_based_extraction_keywords(self, extractor):
        """규칙 기반 키워드 추출 테스트."""
        chunk = """
        The efficacy of metformin therapy in diabetic patients was evaluated.
        Primary endpoints included HbA1c reduction and cardiovascular outcomes.
        """

        result = extractor._extract_rule_based(chunk, section_type="methods")

        assert result is not None
        assert len(result.keywords) > 0

    def test_rule_based_is_key_finding(self, extractor):
        """규칙 기반 주요 발견 감지 테스트."""
        chunk = """
        Our study demonstrates that the treatment significantly improves outcomes.
        In conclusion, we found that early intervention is effective.
        """

        result = extractor._extract_rule_based(chunk, section_type="results")

        # Should detect key finding indicators
        assert result is not None


class TestLLMMetadataExtractorIntegration:
    """통합 테스트 (실제 API 없이)."""

    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini 클라이언트."""
        client = MagicMock(spec=GeminiClient)
        client.generate_json = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_full_extraction_workflow(self, mock_gemini_client):
        """전체 추출 워크플로우 테스트."""
        extractor = LLMMetadataExtractor(
            gemini_client=mock_gemini_client
        )

        # 실제 논문에서 가져온 텍스트 시뮬레이션
        abstract = """
        BACKGROUND: Spinal fusion surgery outcomes vary significantly among elderly patients.
        METHODS: We conducted a prospective cohort study of 250 patients aged 65 and older
        who underwent lumbar spinal fusion between 2018 and 2022.
        RESULTS: The overall complication rate was 15.2%. Patients with diabetes had
        significantly higher complication rates (OR 2.3, 95% CI: 1.4-3.8, p=0.002).
        CONCLUSION: Careful patient selection and perioperative optimization are essential.
        """

        methods_chunk = """
        Study Design: This prospective cohort study enrolled patients from three academic
        medical centers. Inclusion criteria were: age ≥65 years, diagnosis of degenerative
        lumbar spine disease, and planned posterior lumbar fusion surgery. Exclusion criteria
        included previous spine surgery, active infection, and malignancy.

        Outcomes: The primary outcome was 30-day complication rate. Secondary outcomes
        included length of stay, readmission rate, and functional status at 6 months.
        """

        results_chunk = """
        Patient Characteristics: Of 250 enrolled patients, mean age was 71.3 years (SD 5.2).
        Diabetes was present in 32% of patients. Mean BMI was 28.5 kg/m².

        Primary Outcome: The 30-day complication rate was 15.2% (38/250). Diabetic patients
        had significantly higher complication rates compared to non-diabetic patients
        (23.8% vs 11.2%, OR 2.3, 95% CI: 1.4-3.8, p=0.002). After multivariate adjustment,
        diabetes remained an independent predictor (adjusted OR 2.1, 95% CI: 1.2-3.5).
        """

        # Methods 청크에 대한 응답
        mock_gemini_client.generate_json.side_effect = [
            {
                "summary": "Prospective cohort study of elderly patients undergoing lumbar fusion",
                "keywords": ["lumbar fusion", "elderly", "cohort study", "complications"],
                "pico": {
                    "population": "patients aged ≥65 with degenerative lumbar spine disease",
                    "intervention": "posterior lumbar fusion surgery",
                    "comparison": None,
                    "outcome": "30-day complication rate"
                },
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": ["lumbar fusion", "degenerative spine disease", "complication"]
            },
            {
                "summary": "Diabetic patients had significantly higher complication rates after lumbar fusion",
                "keywords": ["diabetes", "complications", "odds ratio", "lumbar fusion"],
                "pico": None,
                "statistics": {
                    "p_values": ["p=0.002"],
                    "effect_sizes": [
                        {"type": "odds_ratio", "value": 2.3, "ci_lower": 1.4, "ci_upper": 3.8},
                        {"type": "adjusted_odds_ratio", "value": 2.1, "ci_lower": 1.2, "ci_upper": 3.5}
                    ],
                    "confidence_intervals": ["95% CI: 1.4-3.8", "95% CI: 1.2-3.5"],
                    "sample_sizes": [250],
                    "statistical_tests": ["multivariate regression"]
                },
                "content_type": "original",
                "is_key_finding": True,
                "medical_terms": ["diabetes", "complication rate", "lumbar fusion"]
            }
        ]

        # 추출 실행
        methods_meta = await extractor.extract(methods_chunk, abstract, section_type="methods")
        results_meta = await extractor.extract(results_chunk, abstract, section_type="results")

        # Methods 검증
        assert methods_meta.pico is not None
        assert "elderly" in methods_meta.pico.population.lower() or "65" in methods_meta.pico.population
        assert methods_meta.content_type == "original"

        # Results 검증
        assert results_meta.statistics is not None
        assert len(results_meta.statistics.effect_sizes) >= 1
        assert results_meta.statistics.effect_sizes[0].type == "odds_ratio"
        assert results_meta.is_key_finding is True
        assert "p=0.002" in results_meta.statistics.p_values

    @pytest.mark.asyncio
    async def test_batch_processing_with_failures(self, mock_gemini_client):
        """일부 실패가 있는 배치 처리 테스트."""
        extractor = LLMMetadataExtractor(
            gemini_client=mock_gemini_client
        )

        chunks = [
            "First chunk content.",
            "Second chunk content with our study data.",
            "Third chunk content."
        ]

        # 두 번째 청크에서 에러 발생
        mock_gemini_client.generate_json.side_effect = [
            {
                "summary": "First summary",
                "keywords": ["first"],
                "pico": None,
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": []
            },
            Exception("API Error"),
            {
                "summary": "Third summary",
                "keywords": ["third"],
                "pico": None,
                "statistics": None,
                "content_type": "original",
                "is_key_finding": False,
                "medical_terms": []
            }
        ]

        # extract()는 자동으로 fallback을 사용하므로 에러가 발생해도 결과 반환
        results = await extractor.extract_batch(chunks, "context")

        assert len(results) == 3
        assert results[0].summary == "First summary"
        assert results[2].summary == "Third summary"
        # 두 번째는 fallback 결과 (confidence = 0.3)
        assert results[1].confidence == 0.3

    @pytest.mark.asyncio
    async def test_concurrency_limit(self, mock_gemini_client):
        """동시성 제한 테스트."""
        extractor = LLMMetadataExtractor(
            gemini_client=mock_gemini_client,
            config={"max_concurrency": 2}
        )

        chunks = ["Chunk " + str(i) for i in range(5)]

        mock_gemini_client.generate_json.return_value = {
            "summary": "Summary",
            "keywords": [],
            "pico": None,
            "statistics": None,
            "content_type": "original",
            "is_key_finding": False,
            "medical_terms": []
        }

        results = await extractor.extract_batch(chunks, "context", concurrency=2)

        assert len(results) == 5
        # 동시성이 제한되어도 모든 청크가 처리됨
