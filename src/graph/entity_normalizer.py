"""Entity Normalizer for Spine Terminology.

척추 수술 관련 용어 정규화 (한국어/영어 지원).

Features:
- 수술법 별칭 매핑 (UBE ↔ BESS ↔ Biportal ↔ 내시경 수술)
- 결과변수 별칭 매핑 (VAS ↔ Visual Analog Scale)
- 질환명 정규화 (Lumbar Stenosis ↔ 요추 협착증)
- 한국어 조사 처리 (TLIF가 → TLIF, 내시경 수술을 → UBE)
- Unicode-aware 단어 경계 (한글/영문 혼용 텍스트 지원)

Korean Language Support:
- Full support for Korean medical terminology
- Automatic particle stripping (가, 이, 를, 을, 와, 과, etc.)
- Mixed Korean/English text extraction
- Unicode-aware pattern matching (no ASCII word boundaries for Korean)

Examples:
    >>> normalizer = EntityNormalizer()
    >>>
    >>> # Korean normalization
    >>> normalizer.normalize_intervention("척추 유합술")
    NormalizationResult(normalized='Spinal Fusion', confidence=1.0)
    >>>
    >>> # Particle handling
    >>> normalizer.normalize_intervention("TLIF가")
    NormalizationResult(normalized='TLIF', confidence=0.95)
    >>>
    >>> # Mixed text extraction
    >>> text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"
    >>> interventions = normalizer.extract_and_normalize_interventions(text)
    >>> [r.normalized for r in interventions]
    ['TLIF', 'OLIF']
"""

import re
import logging
import threading
from typing import Optional
from dataclasses import dataclass, field
from rapidfuzz import fuzz, process

# Import configuration system
try:
    from ..core.config import get_normalization_config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    get_normalization_config = None

# Import SNOMED mappings (try relative first, then absolute)
try:
    from ..ontology.spine_snomed_mappings import (
        get_snomed_for_intervention,
        get_snomed_for_pathology,
        get_snomed_for_outcome,
        get_snomed_for_anatomy,
        SNOMEDMapping,
    )
    SNOMED_AVAILABLE = True
except ImportError:
    try:
        # Fallback to absolute import for PYTHONPATH-based usage
        from ontology.spine_snomed_mappings import (
            get_snomed_for_intervention,
            get_snomed_for_pathology,
            get_snomed_for_outcome,
            get_snomed_for_anatomy,
            SNOMEDMapping,
        )
        SNOMED_AVAILABLE = True
    except ImportError:
        SNOMED_AVAILABLE = False
        get_snomed_for_intervention = None
        get_snomed_for_pathology = None
        get_snomed_for_outcome = None
        get_snomed_for_anatomy = None
        SNOMEDMapping = None

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """정규화 결과.

    Attributes:
        original: 원본 텍스트
        normalized: 정규화된 이름
        confidence: 신뢰도 (0.0 ~ 1.0)
        matched_alias: 매칭된 별칭
        method: 매칭 방법 ("exact", "token", "fuzzy", "none")
        snomed_code: SNOMED-CT 코드 (있는 경우)
        snomed_term: SNOMED-CT 용어 (있는 경우)
        category: 수술법 카테고리 (Intervention인 경우)
        parent_code: SNOMED parent concept code for IS_A hierarchy
        semantic_type: SNOMED semantic type (procedure, disorder, etc.)
    """
    original: str
    normalized: str
    confidence: float = 1.0
    matched_alias: str = ""
    method: str = "none"  # "exact", "token", "fuzzy", "none"
    snomed_code: str = ""
    snomed_term: str = ""
    category: str = ""
    parent_code: str = ""
    semantic_type: str = ""


class EntityNormalizer:
    """척추 용어 정규화기.

    사용 예:
        normalizer = EntityNormalizer()
        result = normalizer.normalize_intervention("Biportal Endoscopic")
        # result.normalized == "UBE"
    """

    # Data mappings imported from normalization_maps.py
    # (separated to reduce file size; see Code Audit God Object remediation)
    from .normalization_maps import (
        INTERVENTION_ALIASES as INTERVENTION_ALIASES,
        INTERVENTION_CATEGORIES as INTERVENTION_CATEGORIES,
        OUTCOME_ALIASES as OUTCOME_ALIASES,
        PATHOLOGY_ALIASES as PATHOLOGY_ALIASES,
        ANATOMY_ALIASES as ANATOMY_ALIASES,
        _ANATOMY_VAGUE_TERMS as _ANATOMY_VAGUE_TERMS,
        KOREAN_PARTICLES as KOREAN_PARTICLES,
        ANATOMY_KOREAN as ANATOMY_KOREAN,
    )

    # Placeholder patterns for all entity types (import-time filtering)
    _PLACEHOLDER_RE = re.compile(
        r"(?i)^(not\s+(specified|applicable|explicitly|specifically|stated)|"
        r"not-applicable|unspecified|n/?a$|none$|unknown$)",
    )

    def __init__(self):
        """초기화."""
        # 역방향 매핑 구축 (빠른 조회용)
        self._intervention_reverse = self._build_reverse_map(self.INTERVENTION_ALIASES)
        self._outcome_reverse = self._build_reverse_map(self.OUTCOME_ALIASES)
        self._pathology_reverse = self._build_reverse_map(self.PATHOLOGY_ALIASES)
        self._anatomy_reverse = self._build_reverse_map(self.ANATOMY_ALIASES)

        # Unregistered term tracking (v1.24.0 ontology evolution)
        self._unregistered_terms: list[dict] = []
        self._unregistered_lock = threading.Lock()
        self._unregistered_max_size = 500  # CA-NEW-004: prevent unbounded growth

        # 한국어 감지 패턴
        self._korean_pattern = re.compile(r'[\uac00-\ud7af]+')  # 한글 유니코드 범위

        # Load configuration thresholds
        if CONFIG_AVAILABLE:
            try:
                config = get_normalization_config()
                self.fuzzy_threshold = config.fuzzy_threshold
                self.token_overlap_threshold = config.token_overlap_threshold
                self.word_boundary_confidence = config.word_boundary_confidence
                self.partial_match_threshold = config.partial_match_threshold
                self.enable_korean_normalization = config.enable_korean_normalization
                self.strip_particles = config.strip_particles
                logger.info(f"EntityNormalizer initialized with config: fuzzy={self.fuzzy_threshold}, token={self.token_overlap_threshold}")
            except Exception as e:
                logger.warning(f"Failed to load config, using defaults: {e}")
                self._set_default_thresholds()
        else:
            logger.info("Config system not available, using default thresholds")
            self._set_default_thresholds()

    def _set_default_thresholds(self):
        """Set default threshold values (fallback when config is unavailable)."""
        self.fuzzy_threshold = 0.85
        self.token_overlap_threshold = 0.8
        self.word_boundary_confidence = 0.95
        self.partial_match_threshold = 0.5
        self.enable_korean_normalization = True
        self.strip_particles = True

    def _record_unregistered_term(
        self,
        original_text: str,
        entity_type: str,
        source_paper: str = "",
        attempted_normalizations: list[str] | None = None,
    ) -> None:
        """Record a term that failed normalization for ontology evolution.

        Thread-safe collection of terms not found in any alias dictionary
        or SNOMED mapping. Used by SNOMEDProposer for LLM-based mapping
        proposals.

        Args:
            original_text: The original term text that failed normalization
            entity_type: Entity type (intervention, pathology, outcome, anatomy)
            source_paper: Optional paper_id where the term was found
            attempted_normalizations: Methods tried during normalization
        """
        if not original_text or len(original_text.strip()) < 2:
            return

        entry = {
            "original_text": original_text.strip(),
            "entity_type": entity_type,
            "source_papers": [source_paper] if source_paper else [],
            "attempted_normalizations": attempted_normalizations or [],
        }

        with self._unregistered_lock:
            # Avoid duplicates (same text + entity_type)
            for existing in self._unregistered_terms:
                if (existing["original_text"].lower() == entry["original_text"].lower()
                        and existing["entity_type"] == entry["entity_type"]):
                    # Update source_papers if new
                    if source_paper and source_paper not in existing.get("source_papers", []):
                        existing.setdefault("source_papers", []).append(source_paper)
                    return
            # CA-NEW-004: enforce max size to prevent unbounded growth
            if len(self._unregistered_terms) >= self._unregistered_max_size:
                logger.warning(
                    f"Unregistered terms list reached max size ({self._unregistered_max_size}), "
                    f"dropping oldest entry"
                )
                self._unregistered_terms.pop(0)
            self._unregistered_terms.append(entry)

    def get_unregistered_terms(self) -> list[dict]:
        """Return collected unregistered terms with metadata.

        Returns:
            List of dicts with keys:
                - original_text: str
                - entity_type: str
                - source_paper: str
                - attempted_normalizations: list[str]
        """
        with self._unregistered_lock:
            return list(self._unregistered_terms)

    def clear_unregistered_terms(self) -> int:
        """Reset the unregistered term collection.

        Returns:
            Number of terms cleared
        """
        with self._unregistered_lock:
            count = len(self._unregistered_terms)
            self._unregistered_terms.clear()
            return count

    async def propose_snomed_for_unregistered(self, llm_client=None) -> list[dict]:
        """Propose SNOMED mappings for collected unregistered terms.

        Calls SNOMEDProposer.batch_propose() with the current unregistered terms.
        Returns proposals for manual review or auto-apply.

        Args:
            llm_client: Optional LLM client for SNOMEDProposer.
                If None, SNOMEDProposer will create its own.

        Returns:
            List of proposal dicts with keys: original_term, proposed_term,
            proposed_code, parent_code, confidence, auto_apply, reasoning.
        """
        terms = self.get_unregistered_terms()
        if not terms:
            return []

        try:
            from ontology.snomed_proposer import SNOMEDProposer
        except ImportError:
            logger.warning("SNOMEDProposer not available; cannot propose SNOMED mappings")
            return []

        proposer = SNOMEDProposer(llm_client=llm_client)
        proposals = await proposer.batch_propose(terms)

        return [
            {
                "original_term": p.original_term,
                "proposed_term": p.proposed_term,
                "proposed_code": p.proposed_code,
                "parent_code": p.proposed_parent_code,
                "confidence": p.confidence,
                "auto_apply": p.auto_apply,
                "reasoning": p.reasoning,
            }
            for p in proposals
        ]

    def register_dynamic_alias(
        self,
        entity_type: str,
        alias: str,
        canonical: str,
    ) -> bool:
        """런타임에 새 alias를 reverse_map에 등록 (thread-safe).

        메모리 전용 — 재시작 시 초기화됨.
        canonical이 기존 ALIASES 딕셔너리에 존재해야만 등록 가능.

        Args:
            entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
            alias: 새로 등록할 alias 문자열
            canonical: 매핑 대상 canonical 이름 (ALIASES에 존재해야 함)

        Returns:
            True if registered, False if rejected (중복/invalid canonical)
        """
        reverse_map_key = f"_{entity_type}_reverse"
        aliases_dict_key = f"{entity_type.upper()}_ALIASES"

        reverse_map = getattr(self, reverse_map_key, None)
        aliases_dict = getattr(self, aliases_dict_key, None)

        if reverse_map is None or aliases_dict is None:
            return False

        alias_lower = alias.lower().strip()

        # 이미 등록된 alias
        if alias_lower in reverse_map:
            return False

        # canonical이 ALIASES에 없으면 거부 (안전장치)
        if canonical not in aliases_dict:
            logger.warning(
                f"Dynamic alias rejected: '{canonical}' not in {entity_type} ALIASES"
            )
            return False

        # thread-safe 등록 (dict assignment는 Python GIL 하에서 atomic)
        reverse_map[alias_lower] = canonical
        logger.info(f"Dynamic alias: '{alias}' → '{canonical}' ({entity_type})")
        return True

    def _get_candidate_canonicals(
        self,
        text: str,
        entity_type: str,
        top_k: int = 30,
    ) -> list[str]:
        """rapidfuzz로 상위 top_k 후보 canonical names 빠르게 필터링.

        LLM 프롬프트에 포함할 후보 목록을 최소화하여 비용/정확도 최적화.

        Args:
            text: 매칭 실패한 원본 텍스트
            entity_type: "intervention" | "outcome" | "pathology" | "anatomy"
            top_k: 반환할 최대 후보 수

        Returns:
            similarity 순 정렬된 canonical name 목록
        """
        aliases_dict = {
            "intervention": self.INTERVENTION_ALIASES,
            "outcome": self.OUTCOME_ALIASES,
            "pathology": self.PATHOLOGY_ALIASES,
            "anatomy": self.ANATOMY_ALIASES,
        }.get(entity_type, {})

        canonicals = list(aliases_dict.keys())
        if not canonicals:
            return []

        # rapidfuzz WRatio: 다양한 비율 메트릭 중 최선 자동 선택
        lower_to_original = {c.lower(): c for c in canonicals}
        results = process.extract(
            text.lower(),
            list(lower_to_original.keys()),
            scorer=fuzz.WRatio,
            limit=top_k,
        )

        return [lower_to_original[r[0]] for r in results if r[1] > 30]

    def _build_reverse_map(self, aliases: dict[str, list[str]]) -> dict[str, str]:
        """역방향 매핑 구축."""
        reverse = {}
        for canonical, alias_list in aliases.items():
            # 정규화된 이름도 자기 자신에 매핑
            key = canonical.lower()
            if key in reverse and reverse[key] != canonical:
                logger.warning(
                    "Alias conflict: '%s' was mapped to '%s', now overwritten by '%s'",
                    key, reverse[key], canonical
                )
            reverse[key] = canonical
            for alias in alias_list:
                alias_key = alias.lower()
                if alias_key in reverse and reverse[alias_key] != canonical:
                    logger.warning(
                        "Alias conflict: '%s' was mapped to '%s', now overwritten by '%s'",
                        alias_key, reverse[alias_key], canonical
                    )
                reverse[alias_key] = canonical
        return reverse

    def _strip_korean_particles(self, text: str) -> str:
        """한국어 조사 제거.

        Args:
            text: 입력 텍스트

        Returns:
            조사가 제거된 텍스트
        """
        # 텍스트 끝의 조사만 제거 (단어 중간의 조사는 보존)
        for particle in sorted(self.KOREAN_PARTICLES, key=len, reverse=True):
            if text.endswith(particle):
                return text[:-len(particle)]
        return text

    def _contains_korean(self, text: str) -> bool:
        """한국어 포함 여부 확인.

        Args:
            text: 입력 텍스트

        Returns:
            한국어 포함 여부
        """
        return bool(self._korean_pattern.search(text))

    def _normalize_token(self, token: str) -> str:
        """토큰 정규화 (공백 제거, 소문자 변환, 특수문자 제거).

        Args:
            token: 정규화할 토큰

        Returns:
            정규화된 토큰
        """
        # 소문자 변환
        token = token.lower()
        # 하이픈/언더스코어 제거 (MIS-TLIF → MISTLIF)
        token = token.replace("-", "").replace("_", "")
        # 앞뒤 공백 제거
        token = token.strip()
        return token

    def _create_search_pattern(self, term: str, text: str) -> re.Pattern:
        """검색 패턴 생성 (한국어/영어 구분).

        Args:
            term: 검색할 용어
            text: 검색 대상 텍스트

        Returns:
            정규표현식 패턴
        """
        escaped_term = re.escape(term)

        # 한국어 포함 용어는 단어 경계 없이 검색
        if self._contains_korean(term):
            # 한국어는 조사가 붙을 수 있으므로 앞뒤로 다른 문자가 있어도 매칭
            return re.compile(escaped_term, re.IGNORECASE)
        else:
            # 영어는 단어 경계 사용 (기존 방식)
            return re.compile(r'\b' + escaped_term + r'\b', re.IGNORECASE)

    def _token_match(
        self,
        text: str,
        reverse_map: dict[str, str],
        aliases_dict: dict[str, list[str]]
    ) -> Optional[NormalizationResult]:
        """토큰 기반 매칭 (단어 순서 무관).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            aliases_dict: 별칭 딕셔너리

        Returns:
            NormalizationResult 또는 None
        """
        # 입력 텍스트를 토큰으로 분해
        input_tokens = set(self._normalize_token(t) for t in text.split() if t.strip())

        best_match = None
        best_overlap = 0.0

        for canonical, aliases in aliases_dict.items():
            # 정규화된 이름과 모든 별칭 확인
            all_terms = [canonical] + aliases

            for term in all_terms:
                term_tokens = set(self._normalize_token(t) for t in term.split() if t.strip())

                # 토큰 교집합 비율 계산
                if not input_tokens or not term_tokens:
                    continue

                overlap = len(input_tokens & term_tokens) / max(len(input_tokens), len(term_tokens))

                # token_overlap_threshold 이상 겹치면 매칭으로 간주
                if overlap >= self.token_overlap_threshold and overlap > best_overlap:
                    best_overlap = overlap
                    best_match = (canonical, term, overlap)

        if best_match:
            canonical, matched_term, overlap = best_match
            # 신뢰도: 0.9 + 0.1 * overlap (0.9~1.0)
            confidence = 0.9 + 0.1 * overlap
            return NormalizationResult(
                original=text,
                normalized=canonical,
                confidence=confidence,
                matched_alias=matched_term,
                method="token"
            )

        return None

    def _fuzzy_match(
        self,
        text: str,
        reverse_map: dict[str, str],
        threshold: float = 0.85
    ) -> Optional[NormalizationResult]:
        """퍼지 매칭 (Edit Distance 기반).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            threshold: 최소 유사도 (0.85 = 85%)

        Returns:
            NormalizationResult 또는 None
        """
        # 모든 별칭 수집 (정규화된 이름 + 별칭)
        all_terms = list(reverse_map.keys())

        if not all_terms:
            return None

        # rapidfuzz를 사용한 가장 유사한 항목 찾기
        # scorer: fuzz.ratio (0-100), fuzz.token_sort_ratio, fuzz.partial_ratio 등 사용 가능
        result = process.extractOne(
            text.lower(),
            all_terms,
            scorer=fuzz.ratio,
            score_cutoff=threshold * 100  # 85% → 85
        )

        if result:
            matched_alias, score, _ = result
            canonical = reverse_map[matched_alias]

            # 신뢰도: score / 100 (0.85~1.0)
            return NormalizationResult(
                original=text,
                normalized=canonical,
                confidence=score / 100.0,
                matched_alias=matched_alias,
                method="fuzzy"
            )

        return None

    def normalize_intervention(self, text: str) -> NormalizationResult:
        """수술법 정규화 (SNOMED 코드 포함).

        Args:
            text: 입력 텍스트

        Returns:
            NormalizationResult (category, snomed_code, snomed_term 포함)
        """
        result = self._normalize(
            text,
            self._intervention_reverse,
            "intervention",
            self.INTERVENTION_ALIASES
        )
        # 정규화된 이름에 해당하는 category 추가
        if result.normalized in self.INTERVENTION_CATEGORIES:
            result.category = self.INTERVENTION_CATEGORIES[result.normalized]
        # SNOMED 코드 추가
        return self._enrich_with_snomed(result, "intervention")

    # v1.19.5: Outcome 한정어 패턴 (비교군, 저자명, 서브그룹 등)
    _OUTCOME_QUALIFIER_RE = re.compile(
        r'\s*\([^)]*\)\s*$',
        re.IGNORECASE
    )
    _OUTCOME_DASH_QUALIFIER_RE = re.compile(
        r'\s+[-–—]\s+.+$',
        re.IGNORECASE
    )
    _OUTCOME_TRAILING_GENERIC_RE = re.compile(
        r'\s+(?:incidence|prevalence|occurrence)\s*$|'
        r'\s+(?:for|in|during|after|following|reduction)\s+\w.*$',
        re.IGNORECASE
    )

    def _strip_outcome_qualifiers(self, text: str) -> str:
        """Outcome 이름에서 비교군/저자/서브그룹 한정어 제거.

        Examples:
            "Blood loss (XLIF vs TLIF)" → "Blood loss"
            "Complication rate - UBE-TLIF mastery phase" → "Complication rate"
            "Rod Fracture incidence" → "Rod Fracture"
        """
        stripped = text.strip()
        # 1) 괄호 한정어: "(XLIF vs TLIF)", "(CKD vs Non-CKD)"
        stripped = self._OUTCOME_QUALIFIER_RE.sub('', stripped).strip()
        # 2) 대시 한정어: "- Kim et al.", "- mastery phase"
        stripped = self._OUTCOME_DASH_QUALIFIER_RE.sub('', stripped).strip()
        # 3) 후행 generic 용어: "incidence", "prevalence"
        stripped = self._OUTCOME_TRAILING_GENERIC_RE.sub('', stripped).strip()
        return stripped if stripped else text

    def normalize_outcome(self, text: str) -> NormalizationResult:
        """결과변수 정규화 (SNOMED 코드 포함).

        v1.19.5: 한정어 스트리핑 전처리 추가 — 원본 매칭 실패 시
        한정어를 제거한 텍스트로 재시도.
        """
        # 1차: 원본 텍스트로 정규화 시도
        result = self._normalize(
            text,
            self._outcome_reverse,
            "outcome",
            self.OUTCOME_ALIASES
        )
        if result.confidence > 0:
            return self._enrich_with_snomed(result, "outcome")

        # 2차: 한정어 스트리핑 후 재시도
        stripped = self._strip_outcome_qualifiers(text)
        if stripped != text:
            result = self._normalize(
                stripped,
                self._outcome_reverse,
                "outcome",
                self.OUTCOME_ALIASES
            )
            if result.confidence > 0:
                # 원본 텍스트 기록, confidence 약간 감소
                result.original = text
                result.confidence = max(result.confidence * 0.9, 0.5)
                result.method = f"qualifier_stripped+{result.method}"
                return self._enrich_with_snomed(result, "outcome")

        # 매칭 실패 → 원본 반환
        return self._enrich_with_snomed(
            NormalizationResult(original=text, normalized=text, confidence=0.0, method="none"),
            "outcome"
        )

    def normalize_pathology(self, text: str) -> NormalizationResult:
        """질환명 정규화 (SNOMED 코드 포함)."""
        result = self._normalize(
            text,
            self._pathology_reverse,
            "pathology",
            self.PATHOLOGY_ALIASES
        )
        return self._enrich_with_snomed(result, "pathology")

    def normalize_anatomy(self, text: str) -> NormalizationResult:
        """해부학 위치 정규화 (SNOMED 코드 포함).

        v1.16.1: ANATOMY_ALIASES 기반 정규화 추가.
        v1.20.2: vague/non-specified anatomy terms → low confidence.

        Args:
            text: 입력 텍스트 (예: "L-spine", "C5-C6", "요추")

        Returns:
            NormalizationResult (snomed_code, snomed_term 포함)
        """
        # 한국어 해부학 용어 변환 (우선)
        stripped = text.strip()

        # v1.20.2+: Vague/non-specified terms → confidence 0 (skip at import)
        if stripped.lower() in self._ANATOMY_VAGUE_TERMS or self._PLACEHOLDER_RE.match(stripped):
            return NormalizationResult(
                original=text,
                normalized=text,
                confidence=0.0,
                method="vague_term"
            )

        if stripped in self.ANATOMY_KOREAN:
            stripped = self.ANATOMY_KOREAN[stripped]

        result = self._normalize(
            stripped,
            self._anatomy_reverse,
            "anatomy",
            self.ANATOMY_ALIASES
        )
        return self._enrich_with_snomed(result, "anatomy")

    def _normalize(
        self,
        text: str,
        reverse_map: dict[str, str],
        entity_type: str,
        aliases_dict: dict[str, list[str]]
    ) -> NormalizationResult:
        """내부 정규화 로직 (3단계: Exact → Token → Fuzzy).

        Args:
            text: 입력 텍스트
            reverse_map: 역방향 매핑
            entity_type: 엔티티 유형
            aliases_dict: 별칭 딕셔너리

        Returns:
            NormalizationResult
        """
        if not text:
            return NormalizationResult(
                original=text,
                normalized=text,
                confidence=0.0,
                method="none"
            )

        # ═══════════════════════════════════════════════════
        # Stage 1: EXACT MATCH (confidence=1.0)
        # ═══════════════════════════════════════════════════
        text_lower = text.lower().strip()
        if text_lower in reverse_map:
            return NormalizationResult(
                original=text,
                normalized=reverse_map[text_lower],
                confidence=1.0,
                matched_alias=text,
                method="exact"
            )

        # 한국어 조사 제거 후 재시도
        text_without_particles = self._strip_korean_particles(text_lower)
        if text_without_particles != text_lower and text_without_particles in reverse_map:
            return NormalizationResult(
                original=text,
                normalized=reverse_map[text_without_particles],
                confidence=0.95,  # 조사 제거 후 매칭은 약간 낮은 신뢰도
                matched_alias=text_without_particles,
                method="exact"
            )

        # ═══════════════════════════════════════════════════
        # Stage 2: TOKEN-BASED MATCH (confidence=0.9+)
        # ═══════════════════════════════════════════════════
        token_result = self._token_match(text_lower, reverse_map, aliases_dict)
        if token_result:
            logger.debug(f"Token match: {text} → {token_result.normalized} (conf: {token_result.confidence:.2f})")
            return token_result

        # ═══════════════════════════════════════════════════
        # Stage 3: WORD BOUNDARY MATCH (confidence=0.95)
        # "OLIF surgery" → OLIF (canonical found as complete word)
        # ═══════════════════════════════════════════════════
        words = set(re.split(r'[\s\-_/]+', text_lower))
        for canonical in aliases_dict.keys():
            canonical_lower = canonical.lower()
            if canonical_lower in words:
                return NormalizationResult(
                    original=text,
                    normalized=canonical,
                    confidence=self.word_boundary_confidence,
                    matched_alias=canonical_lower,
                    method="word_boundary"
                )

        # ═══════════════════════════════════════════════════
        # Stage 4: FUZZY MATCH (confidence based on config)
        # ═══════════════════════════════════════════════════
        fuzzy_result = self._fuzzy_match(text_lower, reverse_map, threshold=self.fuzzy_threshold)
        if fuzzy_result:
            logger.debug(f"Fuzzy match: {text} → {fuzzy_result.normalized} (conf: {fuzzy_result.confidence:.2f})")
            return fuzzy_result

        # ═══════════════════════════════════════════════════
        # Stage 5: PARTIAL MATCH (Fallback, confidence=0.5+)
        # ═══════════════════════════════════════════════════
        best_match = None
        best_confidence = 0.0

        for alias_lower, canonical in reverse_map.items():
            # 포함 관계 확인
            if alias_lower in text_lower or text_lower in alias_lower:
                # 길이 비율로 신뢰도 계산
                ratio = min(len(text_lower), len(alias_lower)) / max(len(text_lower), len(alias_lower))
                if ratio > best_confidence:
                    best_confidence = ratio
                    best_match = (alias_lower, canonical)

            # 조사 제거 후 포함 관계 확인
            text_stripped = self._strip_korean_particles(text_lower)
            if text_stripped != text_lower:
                if alias_lower in text_stripped or text_stripped in alias_lower:
                    ratio = min(len(text_stripped), len(alias_lower)) / max(len(text_stripped), len(alias_lower))
                    if ratio > best_confidence:
                        best_confidence = ratio * 0.95  # 조사 제거 후 매칭은 약간 낮은 신뢰도
                        best_match = (alias_lower, canonical)

        if best_match and best_confidence > self.partial_match_threshold:
            return NormalizationResult(
                original=text,
                normalized=best_match[1],
                confidence=best_confidence,
                matched_alias=best_match[0],
                method="partial"
            )

        # ═══════════════════════════════════════════════════
        # NO MATCH - 원본 반환 + 미등록 용어 기록
        # ═══════════════════════════════════════════════════
        logger.debug(f"No {entity_type} match found for: {text}")
        self._record_unregistered_term(
            text, entity_type,
            attempted_normalizations=["exact", "token", "word_boundary", "fuzzy", "partial"],
        )
        return NormalizationResult(
            original=text,
            normalized=text,
            confidence=0.0,
            method="none"
        )

    def normalize_all(self, text: str) -> dict[str, NormalizationResult]:
        """모든 유형에 대해 정규화 시도.

        Args:
            text: 입력 텍스트

        Returns:
            유형별 정규화 결과
        """
        return {
            "intervention": self.normalize_intervention(text),
            "outcome": self.normalize_outcome(text),
            "pathology": self.normalize_pathology(text),
        }

    def extract_and_normalize_interventions(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 수술법 추출 및 정규화.

        Args:
            text: 입력 텍스트 (논문 제목이나 초록)

        Returns:
            발견된 수술법 목록
        """
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._intervention_reverse.items():
            # 이미 찾은 정규화 이름은 건너뜀
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)
                continue

            # 한국어 조사가 붙은 경우 확인 (영어 약어에 조사가 붙은 경우)
            if not self._contains_korean(alias_lower):
                # 영어 약어 뒤에 한국어 조사가 올 수 있음 (예: TLIF가, OLIF와)
                for particle in self.KOREAN_PARTICLES:
                    particle_pattern = re.compile(
                        re.escape(alias_lower) + re.escape(particle),
                        re.IGNORECASE
                    )
                    match = particle_pattern.search(text_lower)
                    if match:
                        results.append(NormalizationResult(
                            original=match.group(0),
                            normalized=canonical,
                            confidence=0.95,  # 조사가 붙은 경우 약간 낮은 신뢰도
                            matched_alias=alias_lower
                        ))
                        found_canonicals.add(canonical)
                        break

        return results

    def extract_and_normalize_outcomes(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 결과변수 추출 및 정규화."""
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._outcome_reverse.items():
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)

        return results

    def extract_and_normalize_pathologies(self, text: str) -> list[NormalizationResult]:
        """텍스트에서 질환명 추출 및 정규화.

        Args:
            text: 입력 텍스트

        Returns:
            발견된 질환명 목록
        """
        results = []
        found_canonicals = set()
        text_lower = text.lower()

        for alias_lower, canonical in self._pathology_reverse.items():
            if canonical in found_canonicals:
                continue

            # Unicode-aware 검색 패턴 사용
            pattern = self._create_search_pattern(alias_lower, text_lower)
            match = pattern.search(text_lower)

            if match:
                matched_text = match.group(0)
                results.append(NormalizationResult(
                    original=matched_text,
                    normalized=canonical,
                    confidence=1.0,
                    matched_alias=alias_lower
                ))
                found_canonicals.add(canonical)
                continue

            # 한국어 조사가 붙은 경우 확인
            if not self._contains_korean(alias_lower):
                for particle in self.KOREAN_PARTICLES:
                    particle_pattern = re.compile(
                        re.escape(alias_lower) + re.escape(particle),
                        re.IGNORECASE
                    )
                    match = particle_pattern.search(text_lower)
                    if match:
                        results.append(NormalizationResult(
                            original=match.group(0),
                            normalized=canonical,
                            confidence=0.95,
                            matched_alias=alias_lower
                        ))
                        found_canonicals.add(canonical)
                        break

        return results

    def get_all_aliases(self, canonical_name: str, entity_type: str = "intervention") -> list[str]:
        """정규화된 이름의 모든 별칭 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            별칭 목록
        """
        if entity_type == "intervention":
            aliases_map = self.INTERVENTION_ALIASES
        elif entity_type == "outcome":
            aliases_map = self.OUTCOME_ALIASES
        elif entity_type == "pathology":
            aliases_map = self.PATHOLOGY_ALIASES
        else:
            return []

        return aliases_map.get(canonical_name, [])

    def _enrich_with_snomed(
        self,
        result: NormalizationResult,
        entity_type: str
    ) -> NormalizationResult:
        """정규화 결과에 SNOMED 코드 추가.

        정규화 성공 시 normalized 이름으로 SNOMED 조회.
        정규화 실패 시(confidence=0)에도 원본 텍스트로 SNOMED 직접 조회 시도.
        (_search_mapping은 exact/case-insensitive/synonym/abbreviation 매칭 지원)

        Args:
            result: 정규화 결과
            entity_type: 엔티티 유형 ("intervention", "pathology", "outcome", "anatomy")

        Returns:
            SNOMED 코드가 추가된 결과
        """
        if not SNOMED_AVAILABLE:
            return result

        if not result.normalized and not result.original:
            return result

        snomed_fn = {
            "intervention": get_snomed_for_intervention,
            "pathology": get_snomed_for_pathology,
            "outcome": get_snomed_for_outcome,
            "anatomy": get_snomed_for_anatomy,
        }.get(entity_type)

        if not snomed_fn:
            return result

        mapping = None

        # 1차: normalized 이름으로 SNOMED 조회
        if result.confidence > 0.0 and result.normalized:
            mapping = snomed_fn(result.normalized)

        # 2차: 실패 시 원본 텍스트로 직접 SNOMED 조회 (synonym/abbreviation 매칭)
        if not mapping and result.original:
            mapping = snomed_fn(result.original)

        if mapping:
            result.snomed_code = mapping.code
            result.snomed_term = mapping.term
            result.parent_code = mapping.parent_code or ""
            result.semantic_type = mapping.semantic_type.value if mapping.semantic_type else ""

        return result

    def get_snomed_code(self, canonical_name: str, entity_type: str = "intervention") -> Optional[str]:
        """정규화된 이름의 SNOMED 코드 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            SNOMED 코드 또는 None
        """
        if not SNOMED_AVAILABLE:
            return None

        mapping = None
        if entity_type == "intervention" and get_snomed_for_intervention:
            mapping = get_snomed_for_intervention(canonical_name)
        elif entity_type == "pathology" and get_snomed_for_pathology:
            mapping = get_snomed_for_pathology(canonical_name)
        elif entity_type == "outcome" and get_snomed_for_outcome:
            mapping = get_snomed_for_outcome(canonical_name)
        elif entity_type == "anatomy" and get_snomed_for_anatomy:
            mapping = get_snomed_for_anatomy(canonical_name)

        return mapping.code if mapping else None

    def get_snomed_mapping(self, canonical_name: str, entity_type: str = "intervention"):
        """정규화된 이름의 전체 SNOMED 매핑 반환.

        Args:
            canonical_name: 정규화된 이름
            entity_type: 엔티티 유형

        Returns:
            SNOMEDMapping 객체 또는 None
        """
        if not SNOMED_AVAILABLE:
            return None

        if entity_type == "intervention" and get_snomed_for_intervention:
            return get_snomed_for_intervention(canonical_name)
        elif entity_type == "pathology" and get_snomed_for_pathology:
            return get_snomed_for_pathology(canonical_name)
        elif entity_type == "outcome" and get_snomed_for_outcome:
            return get_snomed_for_outcome(canonical_name)
        elif entity_type == "anatomy" and get_snomed_for_anatomy:
            return get_snomed_for_anatomy(canonical_name)

        return None

    def normalize_intervention_with_snomed(self, text: str) -> NormalizationResult:
        """수술법 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_intervention(text)
        return self._enrich_with_snomed(result, "intervention")

    def normalize_pathology_with_snomed(self, text: str) -> NormalizationResult:
        """질환명 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_pathology(text)
        return self._enrich_with_snomed(result, "pathology")

    def normalize_outcome_with_snomed(self, text: str) -> NormalizationResult:
        """결과변수 정규화 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            SNOMED 코드가 포함된 NormalizationResult
        """
        result = self.normalize_outcome(text)
        return self._enrich_with_snomed(result, "outcome")

    def normalize_with_hierarchy_fallback(
        self,
        text: str,
        entity_type: str,
    ) -> NormalizationResult:
        """Hierarchy-aware normalization with parent concept fallback.

        When direct normalization fails, tries to match against SNOMED
        hierarchy by progressively simplifying the term.
        Example: "L4-5 stenosis" -> try "Lumbar Stenosis" -> parent: "Spinal Stenosis"

        Args:
            text: Input text to normalize
            entity_type: Entity type ("intervention", "pathology", "outcome", "anatomy")

        Returns:
            NormalizationResult with best match (may include parent info)
        """
        # 1. Direct normalization
        normalize_fn = getattr(self, f"normalize_{entity_type}", None)
        if not normalize_fn:
            return NormalizationResult(original=text, normalized=text, confidence=0.0, method="none")

        result = normalize_fn(text)
        if result.confidence > 0.0:
            return result

        if not SNOMED_AVAILABLE:
            return result

        # 2. Try simplified variants for hierarchy-based matching
        simplified_terms = self._generate_simplified_terms(text, entity_type)

        for simplified in simplified_terms:
            if simplified == text:
                continue
            alt_result = normalize_fn(simplified)
            if alt_result.confidence > 0.0:
                # Found a match via simplification
                alt_result.original = text
                alt_result.confidence = max(alt_result.confidence * 0.85, 0.5)
                alt_result.method = f"hierarchy_fallback+{alt_result.method}"
                return alt_result

        return result

    def _generate_simplified_terms(self, text: str, entity_type: str) -> list[str]:
        """Generate simplified term variants for hierarchy-based matching.

        Strips level-specific prefixes and qualifiers to find broader concepts.
        Example: "L4-5 stenosis" -> ["Lumbar Stenosis", "Spinal Stenosis"]

        Args:
            text: Original term text
            entity_type: Entity type for context-aware simplification

        Returns:
            List of simplified term candidates (most specific first)
        """
        simplified: list[str] = []
        text_lower = text.lower().strip()

        if entity_type == "pathology":
            # Strip level-specific prefixes: "L4-5 stenosis" -> "Lumbar Stenosis"
            level_pattern = re.compile(
                r'^(?:L\d[-–](?:L?\d|S\d)|C\d[-–]C?\d|T\d+[-–]T?\d+)\s+',
                re.IGNORECASE
            )
            stripped = level_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                # Determine region from the level prefix
                if re.match(r'L\d', text, re.IGNORECASE):
                    simplified.append(f"Lumbar {stripped.title()}")
                elif re.match(r'C\d', text, re.IGNORECASE):
                    simplified.append(f"Cervical {stripped.title()}")
                elif re.match(r'T\d', text, re.IGNORECASE):
                    simplified.append(f"Thoracic {stripped.title()}")
                simplified.append(f"Spinal {stripped.title()}")

            # Strip "lumbar/cervical/thoracic" to get generic form
            region_pattern = re.compile(
                r'^(?:lumbar|cervical|thoracic|thoracolumbar|lumbosacral)\s+',
                re.IGNORECASE
            )
            generic = region_pattern.sub('', text).strip()
            if generic and generic.lower() != text_lower:
                simplified.append(f"Spinal {generic.title()}")

        elif entity_type == "outcome":
            # Strip sub-measure qualifiers: "VAS Back" -> "VAS", "ODI Score" -> "ODI"
            qualifier_pattern = re.compile(
                r'\s+(?:back|leg|neck|arm|score|index|total|overall)$',
                re.IGNORECASE
            )
            stripped = qualifier_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                simplified.append(stripped)

        elif entity_type == "anatomy":
            # Strip level-specific info: "L4-L5 Disc" -> "Lumbar Disc"
            level_pattern = re.compile(
                r'^(?:L\d[-–](?:L?\d|S\d)|C\d[-–]C?\d|T\d+[-–]T?\d+)\s+',
                re.IGNORECASE
            )
            stripped = level_pattern.sub('', text).strip()
            if stripped and stripped.lower() != text_lower:
                if re.match(r'L\d', text, re.IGNORECASE):
                    simplified.append(f"Lumbar {stripped.title()}")
                elif re.match(r'C\d', text, re.IGNORECASE):
                    simplified.append(f"Cervical {stripped.title()}")

        return simplified

    def normalize_all_with_snomed(self, text: str) -> dict[str, NormalizationResult]:
        """모든 유형에 대해 정규화 시도 + SNOMED 코드.

        Args:
            text: 입력 텍스트

        Returns:
            유형별 정규화 결과 (SNOMED 코드 포함)
        """
        return {
            "intervention": self.normalize_intervention_with_snomed(text),
            "outcome": self.normalize_outcome_with_snomed(text),
            "pathology": self.normalize_pathology_with_snomed(text),
        }


# 싱글톤 인스턴스
_normalizer: Optional[EntityNormalizer] = None
_normalizer_lock = threading.Lock()


def get_normalizer() -> EntityNormalizer:
    """정규화기 싱글톤 가져오기 (thread-safe)."""
    global _normalizer
    if _normalizer is None:
        with _normalizer_lock:
            if _normalizer is None:
                _normalizer = EntityNormalizer()
    return _normalizer


# 사용 예시
if __name__ == "__main__":
    normalizer = EntityNormalizer()

    # 수술법 정규화 (English)
    print("=" * 60)
    print("1. EXACT MATCH (English)")
    print("=" * 60)
    for term in ["Biportal Endoscopic", "XLIF", "Transforaminal Fusion"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 수술법 정규화 (Korean)
    print("\n" + "=" * 60)
    print("2. EXACT MATCH (Korean)")
    print("=" * 60)
    for term in ["척추 유합술", "내시경 수술", "감압술"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 조사가 붙은 경우
    print("\n" + "=" * 60)
    print("3. EXACT MATCH (With Korean particles)")
    print("=" * 60)
    for term in ["TLIF가", "OLIF와", "UBE를"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 토큰 기반 매칭 (단어 순서 무관)
    print("\n" + "=" * 60)
    print("4. TOKEN-BASED MATCH (Word order independent)")
    print("=" * 60)
    for term in ["Endoscopic Biportal", "Trans LIF", "Fusion Lumbar Interbody"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 퍼지 매칭 (오타/약간의 변형)
    print("\n" + "=" * 60)
    print("5. FUZZY MATCH (Edit distance)")
    print("=" * 60)
    for term in ["Biportl", "Transforaminal Interbody", "Laminetomy"]:
        result = normalizer.normalize_intervention(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 결과변수 정규화
    print("\n" + "=" * 60)
    print("6. OUTCOME NORMALIZATION (Fuzzy matching)")
    print("=" * 60)
    for term in ["Visual Analog Scale", "Oswestry", "C7 Plumb Line", "Visual Anlog Scale"]:
        result = normalizer.normalize_outcome(term)
        print(f"  {term} → {result.normalized}")
        print(f"    confidence: {result.confidence:.2f}, method: {result.method}")

    # 텍스트에서 수술법 추출 (English)
    print("\n" + "=" * 60)
    print("7. EXTRACTION FROM TEXT (English)")
    print("=" * 60)
    text = "Comparison of TLIF and OLIF for treatment of lumbar stenosis"
    interventions = normalizer.extract_and_normalize_interventions(text)
    for r in interventions:
        print(f"  Intervention: {r.normalized}")

    # 텍스트에서 수술법 추출 (Korean/Mixed)
    print("\n" + "=" * 60)
    print("8. EXTRACTION FROM TEXT (Korean/Mixed)")
    print("=" * 60)
    text = "요추 협착증 치료를 위한 TLIF와 OLIF 비교"
    interventions = normalizer.extract_and_normalize_interventions(text)
    pathologies = normalizer.extract_and_normalize_pathologies(text)
    for r in interventions:
        print(f"  Intervention: {r.normalized}")
    for r in pathologies:
        print(f"  Pathology: {r.normalized}")

    # SNOMED 코드 통합 예시
    print("\n" + "=" * 60)
    print("9. SNOMED-CT INTEGRATION")
    print("=" * 60)
    for term in ["TLIF", "Laminectomy", "Lumbar Stenosis", "VAS"]:
        # Determine entity type
        intervention_result = normalizer.normalize_intervention_with_snomed(term)
        pathology_result = normalizer.normalize_pathology_with_snomed(term)
        outcome_result = normalizer.normalize_outcome_with_snomed(term)

        # Find best match
        best = max([intervention_result, pathology_result, outcome_result],
                   key=lambda x: x.confidence)

        if best.confidence > 0:
            snomed_info = f" [SNOMED: {best.snomed_code}]" if best.snomed_code else " [No SNOMED]"
            print(f"  {term} → {best.normalized}{snomed_info}")
            if best.snomed_term:
                print(f"    SNOMED Term: {best.snomed_term}")
        else:
            print(f"  {term} → (no match)")
