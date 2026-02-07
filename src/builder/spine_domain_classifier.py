"""Spine Domain Classifier.

척추 수술 도메인 특화 분류 및 엔티티 정규화.
Gemini Vision Processor로부터 추출된 데이터를 정규화하여
Neo4j Graph에 저장하기 적합한 형태로 변환.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .gemini_vision_processor import (
    ExtractedMetadata,
    SpineMetadata,
    ExtractedOutcome,
)

# entity_normalizer는 별도 graph 모듈에 있음
# 상대 임포트로 처리
try:
    from ..graph.entity_normalizer import EntityNormalizer, NormalizationResult
except ImportError:
    # graph 모듈이 아직 없는 경우 (개발 초기 단계)
    EntityNormalizer = None
    NormalizationResult = None

logger = logging.getLogger(__name__)


@dataclass
class NormalizedIntervention:
    """정규화된 수술법."""
    original: str
    normalized: str
    confidence: float = 1.0
    aliases: list[str] = field(default_factory=list)


@dataclass
class NormalizedOutcome:
    """정규화된 결과변수."""
    original: str
    normalized: str
    value_intervention: str = ""
    value_control: str = ""
    p_value: str = ""
    confidence: float = 1.0


@dataclass
class NormalizedPathology:
    """정규화된 질환명."""
    original: str
    normalized: str
    confidence: float = 1.0


@dataclass
class ClassifiedSpineData:
    """분류 및 정규화된 척추 데이터."""
    sub_domain: str  # Degenerative, Deformity, Trauma, Tumor, Basic Science
    pathologies: list[NormalizedPathology]  # 여러 질환 가능
    anatomy_level: str
    interventions: list[NormalizedIntervention]
    outcomes: list[NormalizedOutcome]

    @property
    def pathology(self) -> NormalizedPathology:
        """하위 호환성을 위한 첫 번째 pathology 반환."""
        return self.pathologies[0] if self.pathologies else NormalizedPathology("", "", 0.0)


class SpineDomainClassifier:
    """척추 도메인 분류 및 엔티티 정규화기.

    사용 예:
        classifier = SpineDomainClassifier()
        metadata = vision_processor.process_pdf(pdf_path).metadata
        classified = classifier.classify_and_normalize(metadata)
    """

    def __init__(self, normalizer: Optional["EntityNormalizer"] = None):
        """초기화.

        Args:
            normalizer: 엔티티 정규화기 (None이면 자동 생성)
        """
        if EntityNormalizer is None:
            logger.warning(
                "EntityNormalizer not available. "
                "Install graph module or normalization will use original values."
            )
            self.normalizer = None
        else:
            self.normalizer = normalizer or EntityNormalizer()

    def classify_and_normalize(
        self,
        metadata: ExtractedMetadata
    ) -> ClassifiedSpineData:
        """메타데이터를 분류하고 정규화.

        Args:
            metadata: Gemini Vision Processor로부터 추출된 메타데이터

        Returns:
            ClassifiedSpineData: 정규화된 척추 데이터
        """
        spine = metadata.spine

        # 1. 질환명 정규화 (여러 개 지원)
        pathologies = self._normalize_pathologies(spine.pathology)

        # 2. 수술법 정규화 (여러 개)
        interventions = self._normalize_interventions(spine.interventions)

        # 3. 결과변수 정규화 (여러 개)
        outcomes = self._normalize_outcomes(spine.outcomes)

        # 4. Sub-domain은 이미 enum으로 제한되어 있으므로 그대로 사용
        sub_domain = spine.sub_domain or "Not Applicable"

        # 5. Anatomy Level은 문자열 그대로 사용 (형식 검증은 선택적)
        anatomy_level = self._validate_anatomy_level(spine.anatomy_level)

        return ClassifiedSpineData(
            sub_domain=sub_domain,
            pathologies=pathologies,
            anatomy_level=anatomy_level,
            interventions=interventions,
            outcomes=outcomes
        )

    def _normalize_pathologies(self, pathology_list: list[str]) -> list[NormalizedPathology]:
        """질환명 목록 정규화.

        Args:
            pathology_list: 질환명 리스트

        Returns:
            정규화된 NormalizedPathology 리스트
        """
        if not pathology_list:
            return []

        normalized = []
        for pathology in pathology_list:
            if not pathology:
                continue

            if self.normalizer is None:
                # 정규화기가 없으면 원본 그대로
                normalized.append(NormalizedPathology(
                    original=pathology,
                    normalized=pathology,
                    confidence=1.0
                ))
            else:
                result = self.normalizer.normalize_pathology(pathology)
                normalized.append(NormalizedPathology(
                    original=result.original,
                    normalized=result.normalized,
                    confidence=result.confidence
                ))

        return normalized

    def _normalize_pathology(self, pathology: str) -> NormalizedPathology:
        """단일 질환명 정규화 (하위 호환성)."""
        if not pathology:
            return NormalizedPathology(
                original="",
                normalized="",
                confidence=0.0
            )

        if self.normalizer is None:
            return NormalizedPathology(
                original=pathology,
                normalized=pathology,
                confidence=1.0
            )

        result = self.normalizer.normalize_pathology(pathology)
        return NormalizedPathology(
            original=result.original,
            normalized=result.normalized,
            confidence=result.confidence
        )

    def _normalize_interventions(
        self,
        interventions: list[str]
    ) -> list[NormalizedIntervention]:
        """수술법 목록 정규화."""
        normalized = []

        for intervention in interventions:
            if not intervention:
                continue

            if self.normalizer is None:
                # 정규화기가 없으면 원본 그대로
                normalized.append(NormalizedIntervention(
                    original=intervention,
                    normalized=intervention,
                    confidence=1.0,
                    aliases=[]
                ))
                continue

            result = self.normalizer.normalize_intervention(intervention)

            # 별칭 목록 조회
            aliases = self.normalizer.get_all_aliases(
                result.normalized,
                entity_type="intervention"
            )

            normalized.append(NormalizedIntervention(
                original=result.original,
                normalized=result.normalized,
                confidence=result.confidence,
                aliases=aliases
            ))

        return normalized

    def _normalize_outcomes(
        self,
        outcomes: list[ExtractedOutcome]
    ) -> list[NormalizedOutcome]:
        """결과변수 목록 정규화."""
        normalized = []

        for outcome in outcomes:
            if not outcome.name:
                continue

            if self.normalizer is None:
                # 정규화기가 없으면 원본 그대로
                normalized.append(NormalizedOutcome(
                    original=outcome.name,
                    normalized=outcome.name,
                    value_intervention=outcome.value_intervention,
                    value_control=outcome.value_control,
                    p_value=outcome.p_value,
                    confidence=1.0
                ))
                continue

            result = self.normalizer.normalize_outcome(outcome.name)

            normalized.append(NormalizedOutcome(
                original=result.original,
                normalized=result.normalized,
                value_intervention=outcome.value_intervention,
                value_control=outcome.value_control,
                p_value=outcome.p_value,
                confidence=result.confidence
            ))

        return normalized

    def _validate_anatomy_level(self, anatomy_level: str) -> str:
        """Anatomy Level 형식 검증 및 정리.

        Args:
            anatomy_level: 입력된 해부학 레벨

        Returns:
            정리된 해부학 레벨 문자열
        """
        if not anatomy_level:
            return ""

        # 기본 정리: 공백 제거, 대문자 변환
        cleaned = anatomy_level.strip().upper()

        # 추가 검증 로직은 필요시 구현
        # 예: "L4-L5" → "L4-5", "C5-C6" → "C5-6"
        import re

        # 간단한 정리: L4-L5 → L4-5
        cleaned = re.sub(r'([CTLS])(\d+)-\1(\d+)', r'\1\2-\3', cleaned)

        return cleaned

    def extract_from_text(
        self,
        text: str,
        sub_domain: str = ""
    ) -> ClassifiedSpineData:
        """텍스트로부터 직접 추출 및 정규화.

        Gemini Vision 없이 텍스트에서 엔티티를 추출할 때 사용.

        Args:
            text: 입력 텍스트 (논문 제목, 초록 등)
            sub_domain: 이미 알고 있는 sub-domain (선택적)

        Returns:
            ClassifiedSpineData
        """
        if self.normalizer is None:
            logger.warning("Normalizer not available. Returning empty data.")
            return ClassifiedSpineData(
                sub_domain=sub_domain or "Not Applicable",
                pathology=NormalizedPathology("", "", 0.0),
                anatomy_level="",
                interventions=[],
                outcomes=[]
            )

        # 수술법 추출
        intervention_results = self.normalizer.extract_and_normalize_interventions(text)
        interventions = []
        for result in intervention_results:
            aliases = self.normalizer.get_all_aliases(
                result.normalized,
                entity_type="intervention"
            )
            interventions.append(NormalizedIntervention(
                original=result.original,
                normalized=result.normalized,
                confidence=result.confidence,
                aliases=aliases
            ))

        # 결과변수 추출
        outcome_results = self.normalizer.extract_and_normalize_outcomes(text)
        outcomes = [
            NormalizedOutcome(
                original=result.original,
                normalized=result.normalized,
                confidence=result.confidence
            )
            for result in outcome_results
        ]

        # 간단한 해부학 레벨 추출 (정규식)
        anatomy_level = self._extract_anatomy_from_text(text)

        return ClassifiedSpineData(
            sub_domain=sub_domain or "Not Applicable",
            pathology=NormalizedPathology("", "", 0.0),  # 텍스트 추출로는 pathology 파악 어려움
            anatomy_level=anatomy_level,
            interventions=interventions,
            outcomes=outcomes
        )

    def _extract_anatomy_from_text(self, text: str) -> str:
        """텍스트에서 해부학 레벨 추출.

        Args:
            text: 입력 텍스트

        Returns:
            추출된 해부학 레벨 (없으면 빈 문자열)
        """
        import re

        # 패턴: L4-5, C5-6, T10-L2 등
        patterns = [
            r'\b([CTLS]\d+[-–]\d+)\b',  # L4-5, C5-6
            r'\b([CTLS]\d+[-–][CTLS]\d+)\b',  # L4-L5, C5-C6
            r'\b([CTLS]\d+)\s*to\s*([CTLS]\d+)\b',  # L4 to L5
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # 첫 번째 매칭 결과 반환
                if len(match.groups()) == 1:
                    return self._validate_anatomy_level(match.group(1))
                else:
                    # "L4 to L5" → "L4-5"
                    return f"{match.group(1)}-{match.group(2).replace(match.group(1)[0], '')}"

        return ""


# 사용 예시
if __name__ == "__main__":
    # 1. Gemini Vision Processor와 함께 사용
    from .gemini_vision_processor import GeminiPDFProcessor

    async def example_with_vision():
        processor = GeminiPDFProcessor()
        result = await processor.process_pdf("example.pdf")

        if result.success:
            classifier = SpineDomainClassifier()
            classified = classifier.classify_and_normalize(result.metadata)

            print(f"Sub-domain: {classified.sub_domain}")
            print(f"Pathology: {classified.pathology.normalized}")
            print(f"Anatomy: {classified.anatomy_level}")
            print(f"Interventions:")
            for interv in classified.interventions:
                print(f"  - {interv.normalized} (from: {interv.original})")
            print(f"Outcomes:")
            for outcome in classified.outcomes:
                print(f"  - {outcome.normalized}: {outcome.value_intervention} (p={outcome.p_value})")

    # 2. 텍스트로부터 직접 추출
    def example_from_text():
        classifier = SpineDomainClassifier()

        text = "Comparison of TLIF and OLIF for treatment of L4-5 lumbar stenosis. VAS and ODI were measured."
        classified = classifier.extract_from_text(text, sub_domain="Degenerative")

        print(f"\nExtracted from text:")
        print(f"Interventions: {[i.normalized for i in classified.interventions]}")
        print(f"Outcomes: {[o.normalized for o in classified.outcomes]}")
        print(f"Anatomy: {classified.anatomy_level}")

    import asyncio
    asyncio.run(example_with_vision())
    example_from_text()
