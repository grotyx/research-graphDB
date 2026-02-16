"""Tests for v1.20.0 Auto Normalizer Expansion (3-Layer defense).

Layer 1: Vocabulary hints in extraction prompt
Layer 2-A: Dynamic alias registration + candidate pre-filtering
Layer 2-B: LLM classification fallback + _normalize_with_fallback
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from graph.entity_normalizer import EntityNormalizer, NormalizationResult
from graph.relationship_builder import (
    classify_unmatched_entity,
    RelationshipBuilder,
)


# =============================================================================
# Layer 1: Vocabulary Hints
# =============================================================================


class TestVocabularyHints:
    """EXTRACTION_PROMPT에 vocabulary hints가 포함되는지 테스트."""

    def test_vocabulary_hints_generated(self):
        """_build_vocabulary_hints()가 제어 어휘 섹션을 생성한다."""
        from builder.unified_pdf_processor import _build_vocabulary_hints

        hints = _build_vocabulary_hints()
        assert "CONTROLLED VOCABULARY" in hints
        assert "VAS" in hints
        assert "TLIF" in hints
        assert "Lumbar Stenosis" in hints

    def test_extraction_prompt_includes_hints(self):
        """EXTRACTION_PROMPT에 vocabulary hints가 결합되어 있다."""
        from builder.unified_pdf_processor import EXTRACTION_PROMPT

        assert "CONTROLLED VOCABULARY" in EXTRACTION_PROMPT


# =============================================================================
# Layer 2-A: Dynamic Alias Registration
# =============================================================================


class TestDynamicAlias:
    """register_dynamic_alias() 테스트."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_register_valid_alias(self, normalizer):
        """유효한 alias 등록 후 정규화 성공."""
        result = normalizer.register_dynamic_alias(
            "outcome", "Time in Operating Theatre", "Operation Time"
        )
        assert result is True
        # 등록 후 정규화 가능해야 함
        norm = normalizer.normalize_outcome("Time in Operating Theatre")
        assert norm.normalized == "Operation Time"
        assert norm.confidence == 1.0

    def test_reject_invalid_canonical(self, normalizer):
        """ALIASES에 없는 canonical은 거부."""
        result = normalizer.register_dynamic_alias(
            "outcome", "foo", "NonExistentConcept"
        )
        assert result is False

    def test_reject_duplicate(self, normalizer):
        """이미 reverse_map에 존재하는 alias는 거부."""
        # "vas" 는 canonical "VAS"의 lowered key로 이미 존재
        result = normalizer.register_dynamic_alias("outcome", "VAS", "VAS")
        assert result is False

    def test_does_not_modify_static_aliases(self, normalizer):
        """동적 alias 등록이 정적 ALIASES 딕셔너리 크기를 변경하지 않음."""
        original_count = len(normalizer.OUTCOME_ALIASES)
        normalizer.register_dynamic_alias(
            "outcome", "Brand New Term XYZ", "VAS"
        )
        assert len(normalizer.OUTCOME_ALIASES) == original_count

    def test_invalid_entity_type(self, normalizer):
        """잘못된 entity_type은 False 반환."""
        result = normalizer.register_dynamic_alias(
            "invalid_type", "some alias", "some canonical"
        )
        assert result is False


# =============================================================================
# Layer 2-A: Candidate Pre-Filtering
# =============================================================================


class TestCandidatePreFiltering:
    """_get_candidate_canonicals() 테스트."""

    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_returns_relevant_candidates(self, normalizer):
        """'Operative Duration'에 대해 'Operation Time'이 상위 후보에 포함."""
        candidates = normalizer._get_candidate_canonicals(
            "Operative Duration", "outcome"
        )
        assert "Operation Time" in candidates[:10]

    def test_top_k_limit(self, normalizer):
        """top_k 파라미터가 반환 개수를 제한."""
        candidates = normalizer._get_candidate_canonicals(
            "test", "outcome", top_k=5
        )
        assert len(candidates) <= 5

    def test_empty_for_invalid_type(self, normalizer):
        """잘못된 entity_type은 빈 리스트 반환."""
        candidates = normalizer._get_candidate_canonicals(
            "test", "nonexistent_type"
        )
        assert candidates == []

    def test_returns_list_of_strings(self, normalizer):
        """반환값이 문자열 리스트."""
        candidates = normalizer._get_candidate_canonicals(
            "Blood Loss", "outcome"
        )
        assert isinstance(candidates, list)
        assert all(isinstance(c, str) for c in candidates)


# =============================================================================
# Layer 2-B: LLM Classification
# =============================================================================


class TestClassifyUnmatchedEntity:
    """LLM Mock으로 classify_unmatched_entity 테스트."""

    @pytest.fixture
    def mock_llm(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_high_confidence_match(self, mock_llm):
        """confidence >= 0.85 + 후보 내 매칭 시 결과 반환."""
        mock_llm.generate_json.return_value = {
            "match": "Operation Time",
            "confidence": 0.95,
            "reason": "synonym",
        }
        result = await classify_unmatched_entity(
            "Operative Duration",
            "outcome",
            ["Operation Time", "Blood Loss"],
            mock_llm,
        )
        assert result == ("Operation Time", 0.95)

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self, mock_llm):
        """confidence < 0.85 이면 None 반환."""
        mock_llm.generate_json.return_value = {
            "match": "Blood Loss",
            "confidence": 0.6,
            "reason": "weak",
        }
        result = await classify_unmatched_entity(
            "Hemoglobin Drop",
            "outcome",
            ["Blood Loss", "VAS"],
            mock_llm,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_genuinely_new(self, mock_llm):
        """match=None이면 None 반환."""
        mock_llm.generate_json.return_value = {
            "match": None,
            "confidence": 0.0,
            "reason": "new concept",
        }
        result = await classify_unmatched_entity(
            "Spinal Cord Perfusion Index",
            "outcome",
            ["SVA", "Lordosis"],
            mock_llm,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_llm_client(self):
        """llm_client=None이면 None 반환."""
        result = await classify_unmatched_entity(
            "test", "outcome", ["VAS"], None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_candidates(self, mock_llm):
        """빈 candidates이면 LLM 호출 없이 None."""
        result = await classify_unmatched_entity(
            "test", "outcome", [], mock_llm
        )
        assert result is None
        mock_llm.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_match_not_in_candidates_rejected(self, mock_llm):
        """LLM이 후보 목록에 없는 canonical을 반환하면 거부."""
        mock_llm.generate_json.return_value = {
            "match": "Invented Term",
            "confidence": 0.95,
            "reason": "hallucination",
        }
        result = await classify_unmatched_entity(
            "test",
            "outcome",
            ["VAS", "ODI"],
            mock_llm,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_exception_returns_none(self, mock_llm):
        """LLM 호출 실패 시 None 반환 (graceful degradation)."""
        mock_llm.generate_json.side_effect = RuntimeError("API error")
        result = await classify_unmatched_entity(
            "test", "outcome", ["VAS"], mock_llm
        )
        assert result is None


# =============================================================================
# Layer 2-B: _normalize_with_fallback Integration
# =============================================================================


class TestNormalizeWithFallback:
    """RelationshipBuilder._normalize_with_fallback 통합 테스트."""

    @pytest.fixture
    def builder(self):
        client = AsyncMock()
        normalizer = EntityNormalizer()
        llm = AsyncMock()
        return RelationshipBuilder(client, normalizer, llm_client=llm)

    @pytest.mark.asyncio
    async def test_standard_match_no_llm(self, builder):
        """표준 정규화 성공 시 LLM 호출 없음."""
        result = await builder._normalize_with_fallback("VAS", "outcome")
        assert result.normalized == "VAS"
        assert result.confidence >= 1.0
        builder.llm_client.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_fallback_on_failure(self, builder):
        """표준 정규화 실패 시 LLM 폴백으로 매칭."""
        builder.llm_client.generate_json.return_value = {
            "match": "Operation Time",
            "confidence": 0.92,
            "reason": "synonym",
        }
        # "Knife-to-close interval"는 표준 정규화에서 매칭 실패하므로 LLM 폴백
        result = await builder._normalize_with_fallback(
            "Knife-to-close interval", "outcome"
        )
        assert result.normalized == "Operation Time"
        assert "llm_classified" in result.method

    @pytest.mark.asyncio
    async def test_rate_limit(self, builder):
        """논문당 LLM 호출 수 제한."""
        builder._llm_call_limit = 2
        builder.llm_client.generate_json.return_value = {
            "match": None,
            "confidence": 0.0,
            "reason": "new",
        }
        for _ in range(3):
            await builder._normalize_with_fallback(
                "Unknown Term XYZ", "outcome"
            )
        # 3번째 호출에서는 LLM이 호출되지 않아야 함 (rate limit)
        assert builder.llm_client.generate_json.call_count == 2

    @pytest.mark.asyncio
    async def test_no_llm_client_graceful(self):
        """LLM client 없이도 정상 동작 (기존 동작 유지)."""
        client = AsyncMock()
        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer, llm_client=None)
        result = await builder._normalize_with_fallback(
            "Unknown XYZ", "outcome"
        )
        assert result.confidence == 0.0  # 매칭 실패, 에러 없음

    @pytest.mark.asyncio
    async def test_anatomy_skips_llm(self, builder):
        """anatomy 타입은 LLM 폴백을 건너뜀."""
        result = await builder._normalize_with_fallback(
            "Unknown Anatomy ZZZ", "anatomy"
        )
        builder.llm_client.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_call_count_increments(self, builder):
        """LLM 폴백 호출마다 카운터 증가."""
        builder.llm_client.generate_json.return_value = {
            "match": None,
            "confidence": 0.0,
            "reason": "new",
        }
        assert builder._llm_call_count == 0
        await builder._normalize_with_fallback(
            "Unknown Term ABC", "outcome"
        )
        assert builder._llm_call_count == 1
