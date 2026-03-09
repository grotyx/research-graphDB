"""LLM-based Metadata Extractor.

LLM을 사용하여 청크에서 요약, PICO, 통계 등 메타데이터를 추출합니다.
기본값: Claude Haiku 4.5 (환경변수로 변경 가능)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Union

from llm import LLMClient, ClaudeClient, GeminiClient
from llm.prompts import METADATA_EXTRACTOR_SYSTEM, METADATA_EXTRACTOR_SCHEMA

logger = logging.getLogger(__name__)


@dataclass
class PICOElements:
    """PICO 요소."""
    population: Optional[str] = None       # 연구 대상 (환자 특성)
    intervention: Optional[str] = None     # 중재/치료
    comparison: Optional[str] = None       # 비교군
    outcome: Optional[str] = None          # 결과 지표

    def is_complete(self) -> bool:
        """모든 PICO 요소가 있는지 확인."""
        return all([self.population, self.intervention, self.outcome])

    def to_dict(self) -> dict:
        return {
            "P": self.population,
            "I": self.intervention,
            "C": self.comparison,
            "O": self.outcome
        }


@dataclass
class EffectSize:
    """효과 크기."""
    type: str              # "Cohen's d", "OR", "RR", "HR", "MD"
    value: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None


@dataclass
class StatsInfo:
    """통계 정보."""
    p_values: list[str] = field(default_factory=list)
    effect_sizes: list[EffectSize] = field(default_factory=list)
    confidence_intervals: list[str] = field(default_factory=list)
    sample_sizes: list[int] = field(default_factory=list)
    statistical_tests: list[str] = field(default_factory=list)

    def has_significant_result(self) -> bool:
        """유의한 결과가 있는지 확인."""
        for p in self.p_values:
            if "<0.05" in p or "<0.01" in p or "<0.001" in p or "< 0.05" in p:
                return True
        return False


@dataclass
class ChunkMetadata:
    """청크 메타데이터."""
    summary: str                           # 1-2문장 요약
    keywords: list[str]                    # 검색 키워드 (5-10개)
    pico: Optional[PICOElements] = None    # PICO 요소
    statistics: Optional[StatsInfo] = None # 통계 정보
    content_type: str = "original"         # original, citation, background
    is_key_finding: bool = False           # 핵심 발견인지
    confidence: float = 0.0                # 추출 신뢰도

    # 추가 메타데이터
    medical_terms: list[str] = field(default_factory=list)
    study_design_mentioned: Optional[str] = None


class ExtractionError(Exception):
    """메타데이터 추출 에러."""
    pass


class LLMMetadataExtractor:
    """LLM 기반 메타데이터 추출기."""

    # 인용 패턴
    CITATION_PATTERNS = [
        r'\([A-Z][a-z]+ et al\.?,? \d{4}\)',
        r'\[[\d,\s]+\]',
        r'according to .+? \(\d{4}\)',
        r'previous studies? (?:have |has )?(?:shown|demonstrated|reported)',
        r'prior research',
        r'it has been (?:shown|reported|demonstrated)'
    ]

    # 원본 패턴
    ORIGINAL_PATTERNS = [
        r'\bwe found\b',
        r'\bour (?:study|results|findings)\b',
        r'\bthis study\b',
        r'\bin our (?:cohort|sample|population)\b',
        r'\bour (?:data|analysis)\b'
    ]

    # 통계 패턴
    P_VALUE_PATTERN = re.compile(r'[pP]\s*[<=]\s*0?\.?\d+')
    EFFECT_SIZE_PATTERN = re.compile(r'(?:HR|OR|RR|d)\s*[=:]\s*\d+\.?\d*')
    CI_PATTERN = re.compile(r'(?:95%?\s*)?CI[:\s]*[\[\(]?\d+\.?\d*\s*[-–to]+\s*\d+\.?\d*[\]\)]?')
    SAMPLE_SIZE_PATTERN = re.compile(r'[nN]\s*[=:]\s*(\d+)')

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        config: Optional[dict] = None,
        # 하위 호환성
        gemini_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None
    ):
        """초기화.

        Args:
            llm_client: LLM 클라이언트 (None이면 자동 생성)
            config: 추가 설정
                - extract_pico: PICO 추출 여부 (기본: True)
                - extract_stats: 통계 추출 여부 (기본: True)
                - max_keywords: 최대 키워드 수 (기본: 10)
            gemini_client: 레거시 파라미터 (llm_client 사용 권장)
        """
        # 하위 호환성: gemini_client 파라미터도 지원
        client = llm_client or gemini_client
        if client is None:
            client = LLMClient()
        self.llm = client
        self.config = config or {}
        self.extract_pico = self.config.get("extract_pico", True)
        self.extract_stats = self.config.get("extract_stats", True)
        self.max_keywords = self.config.get("max_keywords", 10)

    async def extract(
        self,
        chunk: str,
        context: str,
        section_type: Optional[str] = None
    ) -> ChunkMetadata:
        """단일 청크에서 메타데이터 추출 (LLM 기반만 사용).

        Args:
            chunk: 청크 텍스트
            context: 문서 컨텍스트 (초록)
            section_type: 섹션 타입 (힌트용)

        Returns:
            ChunkMetadata 객체

        Raises:
            ExtractionError: 추출 실패
        """
        if not chunk or not chunk.strip():
            return ChunkMetadata(
                summary="[No content]",
                keywords=[],
                content_type="background",
                is_key_finding=False,
                confidence=0.0
            )

        return await self._extract_with_llm(chunk, context, section_type)

    async def extract_batch(
        self,
        chunks: list[str],
        context: str,
        section_types: list[str] = None,
        concurrency: int = 10
    ) -> list[ChunkMetadata]:
        """배치 메타데이터 추출 (병렬 처리).

        Args:
            chunks: 청크 텍스트 목록
            context: 문서 컨텍스트 (공통)
            section_types: 각 청크의 섹션 타입
            concurrency: 동시 처리 수

        Returns:
            ChunkMetadata 목록 (입력 순서 유지)
        """
        if not chunks:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def extract_with_semaphore(chunk: str, section_type: str) -> ChunkMetadata:
            async with semaphore:
                return await self.extract(chunk, context, section_type)

        section_types = section_types or [None] * len(chunks)

        tasks = [
            extract_with_semaphore(chunk, section_type)
            for chunk, section_type in zip(chunks, section_types)
        ]

        return await asyncio.gather(*tasks)

    async def extract_document_level(
        self,
        full_text: str,
        abstract: str
    ) -> dict:
        """문서 수준 메타데이터 추출.

        Args:
            full_text: 전체 논문 텍스트
            abstract: 논문 초록

        Returns:
            문서 수준 메타데이터 딕셔너리
        """
        prompt = f"""Extract document-level metadata from this medical paper.

Abstract:
---
{abstract}
---

Extract:
1. title_summary: One sentence summary of the paper's main contribution
2. main_pico: Primary PICO elements (population, intervention, comparison, outcome)
3. key_findings: List of 3-5 main findings
4. study_design: Type of study (RCT, cohort, case-control, meta-analysis, etc.)
5. evidence_level: Evidence level (1a, 1b, 2a, 2b, 3, 4)

Return as JSON."""

        schema = {
            "type": "OBJECT",
            "properties": {
                "title_summary": {"type": "STRING"},
                "main_pico": {
                    "type": "OBJECT",
                    "properties": {
                        "population": {"type": "STRING"},
                        "intervention": {"type": "STRING"},
                        "comparison": {"type": "STRING"},
                        "outcome": {"type": "STRING"}
                    }
                },
                "key_findings": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "study_design": {"type": "STRING"},
                "evidence_level": {"type": "STRING"}
            },
            "required": ["title_summary", "study_design"]
        }

        try:
            result = await self.llm.generate_json(
                prompt=prompt,
                schema=schema,
                system=METADATA_EXTRACTOR_SYSTEM
            )

            # PICO 객체 생성
            pico_data = result.get("main_pico", {})
            main_pico = PICOElements(
                population=pico_data.get("population"),
                intervention=pico_data.get("intervention"),
                comparison=pico_data.get("comparison"),
                outcome=pico_data.get("outcome")
            ) if pico_data else None

            return {
                "title_summary": result.get("title_summary", ""),
                "main_pico": main_pico,
                "key_findings": result.get("key_findings", []),
                "study_design": result.get("study_design", "unknown"),
                "evidence_level": result.get("evidence_level", "unknown")
            }

        except Exception as e:
            logger.warning(f"Document-level extraction failed: {e}")
            return {
                "title_summary": abstract[:200] if abstract else "",
                "main_pico": None,
                "key_findings": [],
                "study_design": "unknown",
                "evidence_level": "unknown"
            }

    async def _extract_with_llm(
        self,
        chunk: str,
        context: str,
        section_type: Optional[str] = None
    ) -> ChunkMetadata:
        """LLM을 사용한 메타데이터 추출.

        Args:
            chunk: 청크 텍스트
            context: 문서 컨텍스트
            section_type: 섹션 타입

        Returns:
            ChunkMetadata 객체
        """
        section_hint = f" ({section_type} section)" if section_type else ""

        prompt = f"""Extract metadata from this medical paper chunk.

Document context (abstract):
---
{context[:1000] if context else "No context provided"}
---

Chunk to analyze{section_hint}:
---
{chunk}
---

Extract:
1. summary: 1-2 sentence summary
2. keywords: 5-10 relevant search terms
3. pico: PICO elements if present (population, intervention, comparison, outcome)
4. statistics: Any statistical information (p_values, effect_sizes, confidence_intervals, sample_sizes, statistical_tests)
5. content_type: "original" (this paper's findings), "citation" (referencing other studies), or "background"
6. is_key_finding: true if this contains a primary research result
7. medical_terms: Important medical/anatomical terms mentioned"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING"},
                "keywords": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "pico": {
                    "type": "OBJECT",
                    "properties": {
                        "population": {"type": "STRING"},
                        "intervention": {"type": "STRING"},
                        "comparison": {"type": "STRING"},
                        "outcome": {"type": "STRING"}
                    }
                },
                "statistics": {
                    "type": "OBJECT",
                    "properties": {
                        "p_values": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "effect_sizes": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "type": {"type": "STRING"},
                                    "value": {"type": "NUMBER"},
                                    "ci_lower": {"type": "NUMBER"},
                                    "ci_upper": {"type": "NUMBER"}
                                }
                            }
                        },
                        "confidence_intervals": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "sample_sizes": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                        "statistical_tests": {"type": "ARRAY", "items": {"type": "STRING"}}
                    }
                },
                "content_type": {
                    "type": "STRING",
                    "enum": ["original", "citation", "background"]
                },
                "is_key_finding": {"type": "BOOLEAN"},
                "medical_terms": {"type": "ARRAY", "items": {"type": "STRING"}},
                "confidence": {"type": "NUMBER"}
            },
            "required": ["summary", "keywords", "content_type", "is_key_finding"]
        }

        result = await self.llm.generate_json(
            prompt=prompt,
            schema=schema,
            system=METADATA_EXTRACTOR_SYSTEM
        )

        # PICO 파싱
        pico = None
        if result.get("pico") and self.extract_pico:
            pico_data = result["pico"]
            pico = PICOElements(
                population=pico_data.get("population"),
                intervention=pico_data.get("intervention"),
                comparison=pico_data.get("comparison"),
                outcome=pico_data.get("outcome")
            )

        # Statistics 파싱
        stats = None
        if result.get("statistics") and self.extract_stats:
            stats = self._parse_statistics(result["statistics"])

        return ChunkMetadata(
            summary=result.get("summary", ""),
            keywords=result.get("keywords", [])[:self.max_keywords],
            pico=pico,
            statistics=stats,
            content_type=result.get("content_type", "background"),
            is_key_finding=result.get("is_key_finding", False),
            confidence=result.get("confidence", 0.8),
            medical_terms=result.get("medical_terms", [])
        )

    def _parse_statistics(self, raw_stats: dict) -> StatsInfo:
        """통계 정보 파싱 및 정규화.

        Args:
            raw_stats: 원시 통계 데이터

        Returns:
            StatsInfo 객체
        """
        effect_sizes = []
        for es in raw_stats.get("effect_sizes", []):
            if isinstance(es, dict):
                effect_sizes.append(EffectSize(
                    type=es.get("type", "unknown"),
                    value=es.get("value", 0),
                    ci_lower=es.get("ci_lower"),
                    ci_upper=es.get("ci_upper")
                ))

        return StatsInfo(
            p_values=raw_stats.get("p_values", []),
            effect_sizes=effect_sizes,
            confidence_intervals=raw_stats.get("confidence_intervals", []),
            sample_sizes=raw_stats.get("sample_sizes", []),
            statistical_tests=raw_stats.get("statistical_tests", [])
        )

    def _extract_rule_based(
        self,
        chunk: str,
        section_type: Optional[str] = None
    ) -> ChunkMetadata:
        """규칙 기반 메타데이터 추출 (Fallback).

        Args:
            chunk: 청크 텍스트
            section_type: 섹션 타입

        Returns:
            ChunkMetadata 객체
        """
        # 요약: 첫 문장
        sentences = chunk.split('.')
        summary = (sentences[0] + '.') if sentences and sentences[0].strip() else chunk[:200]

        # 키워드: 대문자로 시작하는 명사구 추출
        keywords = self._extract_keywords_rule_based(chunk)

        # 통계: 정규식으로 추출
        stats = self._extract_stats_rule_based(chunk)

        # 콘텐츠 타입
        content_type = self._detect_content_type(chunk)

        # 핵심 발견 여부
        is_key_finding = section_type == "results" and bool(stats.p_values)

        return ChunkMetadata(
            summary=summary,
            keywords=keywords[:self.max_keywords],
            pico=None,  # 규칙 기반으로는 PICO 추출 어려움
            statistics=stats if (stats.p_values or stats.effect_sizes) else None,
            content_type=content_type,
            is_key_finding=is_key_finding,
            confidence=0.3  # 낮은 신뢰도 표시
        )

    def _extract_keywords_rule_based(self, text: str) -> list[str]:
        """규칙 기반 키워드 추출.

        Args:
            text: 텍스트

        Returns:
            키워드 목록
        """
        keywords = []

        # 의학 용어 패턴 (대문자로 시작하는 2-3 단어 구)
        term_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[a-z]+){0,2})\b')
        for match in term_pattern.finditer(text):
            term = match.group(1)
            if len(term) > 3 and term.lower() not in ['the', 'this', 'that', 'with']:
                keywords.append(term)

        # 약어 추출
        abbrev_pattern = re.compile(r'\b([A-Z]{2,6})\b')
        for match in abbrev_pattern.finditer(text):
            keywords.append(match.group(1))

        # 중복 제거
        return list(dict.fromkeys(keywords))[:10]

    def _extract_stats_rule_based(self, text: str) -> StatsInfo:
        """규칙 기반 통계 추출.

        Args:
            text: 텍스트

        Returns:
            StatsInfo 객체
        """
        p_values = []
        for match in self.P_VALUE_PATTERN.finditer(text):
            p_values.append(match.group(0))

        effect_sizes = []
        for match in self.EFFECT_SIZE_PATTERN.finditer(text):
            raw = match.group(0)
            # 파싱 시도
            parts = re.split(r'[=:]', raw)
            if len(parts) == 2:
                try:
                    effect_sizes.append(EffectSize(
                        type=parts[0].strip(),
                        value=float(parts[1].strip())
                    ))
                except ValueError:
                    pass

        confidence_intervals = []
        for match in self.CI_PATTERN.finditer(text):
            confidence_intervals.append(match.group(0))

        sample_sizes = []
        for match in self.SAMPLE_SIZE_PATTERN.finditer(text):
            try:
                sample_sizes.append(int(match.group(1)))
            except ValueError:
                pass

        return StatsInfo(
            p_values=p_values,
            effect_sizes=effect_sizes,
            confidence_intervals=confidence_intervals,
            sample_sizes=sample_sizes
        )

    def _detect_content_type(self, chunk: str) -> str:
        """원본 vs 인용 vs 배경 구분.

        Args:
            chunk: 청크 텍스트

        Returns:
            콘텐츠 타입
        """
        citation_count = sum(
            len(re.findall(pattern, chunk, re.IGNORECASE))
            for pattern in self.CITATION_PATTERNS
        )

        original_count = sum(
            len(re.findall(pattern, chunk, re.IGNORECASE))
            for pattern in self.ORIGINAL_PATTERNS
        )

        if original_count > citation_count:
            return "original"
        elif citation_count > 2:
            return "citation"
        else:
            return "background"
