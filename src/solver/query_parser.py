"""Query Parser module for parsing and expanding medical queries."""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# SNOMED lookup functions (optional import for graceful degradation)
try:
    from ontology.spine_snomed_mappings import (
        get_snomed_for_intervention,
        get_snomed_for_pathology,
        get_snomed_for_outcome,
        get_snomed_for_anatomy,
    )
    _SNOMED_AVAILABLE = True
except ImportError:
    _SNOMED_AVAILABLE = False

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """쿼리 의도."""
    SEARCH = "search"           # 일반 정보 검색
    COMPARE = "compare"         # 비교 (A vs B)
    CAUSAL = "causal"           # 인과관계 (원인, 결과)
    DEFINITION = "definition"   # 정의/개념 설명
    TREATMENT = "treatment"     # 치료/중재 관련
    DIAGNOSIS = "diagnosis"     # 진단 관련
    PROGNOSIS = "prognosis"     # 예후 관련
    SAFETY = "safety"           # 안전성/부작용


class EntityType(Enum):
    """의학 엔티티 유형."""
    DISEASE = "disease"
    DRUG = "drug"
    SYMPTOM = "symptom"
    PROCEDURE = "procedure"
    ANATOMY = "anatomy"
    GENE_PROTEIN = "gene_protein"
    MEASUREMENT = "measurement"
    UNKNOWN = "unknown"


@dataclass
class MedicalEntity:
    """의학 엔티티."""
    text: str
    entity_type: EntityType
    start: int = 0
    end: int = 0
    normalized_form: Optional[str] = None
    snomed_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class QueryInput:
    """쿼리 파싱 입력."""
    query: str
    expand_synonyms: bool = True
    max_expansions: int = 5


@dataclass
class ParsedQuery:
    """파싱된 쿼리."""
    original: str
    normalized: str
    entities: list[MedicalEntity] = field(default_factory=list)
    intent: QueryIntent = QueryIntent.SEARCH
    expanded_terms: list[str] = field(default_factory=list)

    # 추가 분석 결과
    keywords: list[str] = field(default_factory=list)
    negations: list[str] = field(default_factory=list)
    temporal_context: Optional[str] = None
    confidence: float = 1.0

    # SNOMED codes extracted from entities (entity_text -> snomed_code)
    snomed_codes: dict[str, str] = field(default_factory=dict)


class QueryParser:
    """의학 쿼리 파서."""

    # 의도 분류 키워드
    INTENT_KEYWORDS = {
        QueryIntent.COMPARE: [
            "vs", "versus", "compared to", "comparison", "differ",
            "better than", "worse than", "or", "alternative",
            "which is better", "difference between"
        ],
        QueryIntent.CAUSAL: [
            "cause", "causes", "caused by", "lead to", "leads to",
            "result in", "results in", "because", "due to",
            "risk factor", "etiology", "pathogenesis", "mechanism"
        ],
        QueryIntent.DEFINITION: [
            "what is", "what are", "define", "definition",
            "meaning of", "explain", "describe", "overview"
        ],
        QueryIntent.TREATMENT: [
            "treat", "treatment", "therapy", "manage", "management",
            "cure", "medication", "drug", "intervention",
            "how to treat", "best treatment"
        ],
        QueryIntent.DIAGNOSIS: [
            "diagnose", "diagnosis", "diagnostic", "detect",
            "screening", "test", "criteria", "how to diagnose"
        ],
        QueryIntent.PROGNOSIS: [
            "prognosis", "outcome", "survival", "mortality",
            "life expectancy", "recurrence", "long-term"
        ],
        QueryIntent.SAFETY: [
            "safe", "safety", "side effect", "adverse", "risk",
            "complication", "contraindication", "harm"
        ],
    }

    # 질병 패턴 (예시)
    DISEASE_PATTERNS = [
        r'\b(cancer|carcinoma|tumor|tumour)\b',
        r'\b(diabetes|hypertension|stroke|infarction)\b',
        r'\b(disease|disorder|syndrome|condition)\b',
        r'\b(infection|pneumonia|sepsis|hepatitis)\b',
        r'\b(arthritis|osteoporosis|fracture)\b',
        r'\b(stenosis|herniation|spondylosis)\b',
        r'\b(lumbar|cervical|thoracic)\s+(disc|disk|spine)\b',
    ]

    # 약물 패턴
    DRUG_PATTERNS = [
        r'\b\w+(?:mab|nib|tinib|zumab|ximab)\b',  # 생물학적 제제
        r'\b\w+(?:cin|mycin|cillin)\b',  # 항생제
        r'\b\w+(?:pril|sartan|olol|dipine)\b',  # 심혈관약
        r'\b(aspirin|ibuprofen|acetaminophen|metformin)\b',
        r'\b(steroid|opioid|nsaid|antibiotic)\b',
    ]

    # 시술 패턴
    PROCEDURE_PATTERNS = [
        r'\b\w+(?:ectomy|otomy|plasty|scopy)\b',
        r'\b(surgery|operation|procedure|intervention)\b',
        r'\b(biopsy|resection|ablation|fusion)\b',
        r'\b(minimally\s+invasive|endoscopic|laparoscopic)\b',
    ]

    # 해부학 패턴
    ANATOMY_PATTERNS = [
        r'\b(spine|vertebra|disc|disk|nerve|muscle)\b',
        r'\b(heart|lung|liver|kidney|brain)\b',
        r'\b(artery|vein|vessel|blood)\b',
        r'\b(lumbar|cervical|thoracic|sacral)\b',
    ]

    # 증상 패턴
    SYMPTOM_PATTERNS = [
        r'\b(pain|ache|discomfort)\b',
        r'\b(numbness|tingling|weakness|fatigue)\b',
        r'\b(fever|nausea|vomiting|dizziness)\b',
        r'\b(swelling|inflammation|redness)\b',
    ]

    # 동의어 사전 (확장용)
    SYNONYM_MAP = {
        "heart attack": ["myocardial infarction", "MI", "cardiac arrest"],
        "stroke": ["cerebrovascular accident", "CVA", "brain attack"],
        "high blood pressure": ["hypertension", "HTN", "elevated BP"],
        "diabetes": ["diabetes mellitus", "DM", "hyperglycemia"],
        "back pain": ["low back pain", "LBP", "lumbar pain", "lumbago"],
        "disc herniation": ["herniated disc", "slipped disc", "disc prolapse", "HNP"],
        "minimally invasive": ["MIS", "minimal access", "keyhole"],
        "endoscopic": ["endoscopy", "scope-assisted"],
    }

    # 부정 표현
    NEGATION_PATTERNS = [
        r'\b(not|no|without|exclude|excluding|except)\b',
        r'\b(negative|absent|lack of|free of)\b',
    ]

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - expand_synonyms: 동의어 확장 여부 (기본값: True)
                - max_expansions: 최대 확장 용어 수 (기본값: 5)
                - use_snomed: SNOMED-CT 사용 여부 (기본값: True)
        """
        self.config = config or {}
        self.expand_synonyms = self.config.get("expand_synonyms", True)
        self.max_expansions = self.config.get("max_expansions", 5)
        self.use_snomed = self.config.get("use_snomed", True)

        # 패턴 컴파일
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """정규식 패턴 컴파일."""
        self._disease_patterns = [re.compile(p, re.IGNORECASE) for p in self.DISEASE_PATTERNS]
        self._drug_patterns = [re.compile(p, re.IGNORECASE) for p in self.DRUG_PATTERNS]
        self._procedure_patterns = [re.compile(p, re.IGNORECASE) for p in self.PROCEDURE_PATTERNS]
        self._anatomy_patterns = [re.compile(p, re.IGNORECASE) for p in self.ANATOMY_PATTERNS]
        self._symptom_patterns = [re.compile(p, re.IGNORECASE) for p in self.SYMPTOM_PATTERNS]
        self._negation_patterns = [re.compile(p, re.IGNORECASE) for p in self.NEGATION_PATTERNS]

    def parse(self, input_data: QueryInput | str) -> ParsedQuery:
        """쿼리 파싱.

        Args:
            input_data: 쿼리 입력 또는 쿼리 문자열

        Returns:
            파싱된 쿼리
        """
        if isinstance(input_data, str):
            input_data = QueryInput(query=input_data)

        query = input_data.query.strip()

        if not query:
            return ParsedQuery(
                original=query,
                normalized="",
                confidence=0.0
            )

        # 정규화
        normalized = self._normalize_query(query)

        # 의도 분류
        intent = self._classify_intent(normalized)

        # 엔티티 추출
        entities = self._extract_entities(query)

        # 키워드 추출
        keywords = self._extract_keywords(normalized)

        # 부정 표현 추출
        negations = self._extract_negations(query)

        # 시간 맥락 추출
        temporal = self._extract_temporal_context(query)

        # SNOMED enrichment
        snomed_codes: dict[str, str] = {}
        if self.use_snomed and _SNOMED_AVAILABLE:
            snomed_codes = self._enrich_with_snomed(entities)

        # 용어 확장
        expanded_terms = []
        if input_data.expand_synonyms:
            expanded_terms = self._expand_terms(
                keywords, entities, input_data.max_expansions
            )

        # 신뢰도 계산
        confidence = self._calculate_confidence(entities, intent, keywords)

        return ParsedQuery(
            original=query,
            normalized=normalized,
            entities=entities,
            intent=intent,
            expanded_terms=expanded_terms,
            keywords=keywords,
            negations=negations,
            temporal_context=temporal,
            confidence=confidence,
            snomed_codes=snomed_codes,
        )

    def _normalize_query(self, query: str) -> str:
        """쿼리 정규화.

        Args:
            query: 원본 쿼리

        Returns:
            정규화된 쿼리
        """
        # 소문자 변환
        normalized = query.lower()

        # 여러 공백을 하나로
        normalized = re.sub(r'\s+', ' ', normalized)

        # 특수문자 정리 (하이픈, 슬래시는 유지)
        normalized = re.sub(r'[^\w\s\-/]', ' ', normalized)

        return normalized.strip()

    def _classify_intent(self, query: str) -> QueryIntent:
        """쿼리 의도 분류.

        Args:
            query: 정규화된 쿼리

        Returns:
            쿼리 의도
        """
        query_lower = query.lower()

        # 각 의도별 키워드 매칭
        intent_scores: dict[QueryIntent, float] = {}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                # Use word boundary matching for single words
                # Use substring matching for multi-word phrases
                if ' ' in keyword:
                    # Multi-word phrase: use substring matching
                    if keyword in query_lower:
                        score += len(keyword.split()) * 2  # Higher weight for phrases
                else:
                    # Single word: use word boundary to avoid partial matches
                    pattern = r'\b' + re.escape(keyword) + r'\b'
                    if re.search(pattern, query_lower):
                        score += 1

            if score > 0:
                intent_scores[intent] = score

        # Priority boost: SAFETY intent gets bonus when competing with TREATMENT/PROCEDURE
        # This handles cases like "is surgery safe for elderly"
        if QueryIntent.SAFETY in intent_scores and QueryIntent.TREATMENT in intent_scores:
            # Check if query has explicit safety keywords
            safety_keywords = ["safe", "safety", "side effect", "adverse", "complication", "harm"]
            for kw in safety_keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
                    intent_scores[QueryIntent.SAFETY] += 0.5  # Small boost to break ties

        if not intent_scores:
            return QueryIntent.SEARCH

        # 가장 높은 점수의 의도 반환
        return max(intent_scores, key=lambda k: intent_scores[k])

    def _extract_entities(self, query: str) -> list[MedicalEntity]:
        """의학 엔티티 추출.

        Args:
            query: 원본 쿼리

        Returns:
            엔티티 목록
        """
        entities = []
        seen_spans = set()

        # 질병 엔티티
        for pattern in self._disease_patterns:
            for match in pattern.finditer(query):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(MedicalEntity(
                        text=match.group(),
                        entity_type=EntityType.DISEASE,
                        start=match.start(),
                        end=match.end()
                    ))

        # 약물 엔티티
        for pattern in self._drug_patterns:
            for match in pattern.finditer(query):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(MedicalEntity(
                        text=match.group(),
                        entity_type=EntityType.DRUG,
                        start=match.start(),
                        end=match.end()
                    ))

        # 시술 엔티티
        for pattern in self._procedure_patterns:
            for match in pattern.finditer(query):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(MedicalEntity(
                        text=match.group(),
                        entity_type=EntityType.PROCEDURE,
                        start=match.start(),
                        end=match.end()
                    ))

        # 해부학 엔티티
        for pattern in self._anatomy_patterns:
            for match in pattern.finditer(query):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(MedicalEntity(
                        text=match.group(),
                        entity_type=EntityType.ANATOMY,
                        start=match.start(),
                        end=match.end()
                    ))

        # 증상 엔티티
        for pattern in self._symptom_patterns:
            for match in pattern.finditer(query):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(MedicalEntity(
                        text=match.group(),
                        entity_type=EntityType.SYMPTOM,
                        start=match.start(),
                        end=match.end()
                    ))

        # 위치순 정렬
        entities.sort(key=lambda e: e.start)

        return entities

    def _extract_keywords(self, normalized_query: str) -> list[str]:
        """키워드 추출.

        Args:
            normalized_query: 정규화된 쿼리

        Returns:
            키워드 목록
        """
        # 불용어
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "of", "in",
            "on", "at", "to", "for", "with", "by", "from", "up", "about",
            "into", "through", "during", "before", "after", "above", "below",
            "between", "under", "again", "further", "then", "once", "here",
            "there", "when", "where", "why", "how", "all", "each", "few",
            "more", "most", "other", "some", "such", "no", "nor", "not",
            "only", "own", "same", "so", "than", "too", "very", "just",
            "and", "but", "if", "or", "because", "as", "until", "while",
            "what", "which", "who", "whom", "this", "that", "these", "those",
            "am", "it", "its", "itself", "they", "them", "their", "theirs"
        }

        # 단어 분리
        words = normalized_query.split()

        # 불용어 제거 및 길이 필터
        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        return keywords

    def _extract_negations(self, query: str) -> list[str]:
        """부정 표현 추출.

        Args:
            query: 원본 쿼리

        Returns:
            부정 표현 목록
        """
        negations = []

        for pattern in self._negation_patterns:
            for match in pattern.finditer(query):
                negations.append(match.group())

        return negations

    def _extract_temporal_context(self, query: str) -> Optional[str]:
        """시간 맥락 추출.

        Args:
            query: 원본 쿼리

        Returns:
            시간 맥락 (있으면)
        """
        temporal_patterns = [
            (r'\b(recent|latest|new|current)\b', "recent"),
            (r'\b(last\s+\d+\s+years?)\b', "time_range"),
            (r'\b(20\d{2})\b', "specific_year"),
            (r'\b(acute|chronic|long-term|short-term)\b', "duration"),
            (r'\b(before|after|during|post-?operative)\b', "relative_time"),
        ]

        for pattern, context_type in temporal_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return context_type

        return None

    def _expand_terms(
        self,
        keywords: list[str],
        entities: list[MedicalEntity],
        max_expansions: int
    ) -> list[str]:
        """용어 확장.

        Args:
            keywords: 키워드 목록
            entities: 엔티티 목록
            max_expansions: 최대 확장 수

        Returns:
            확장된 용어 목록
        """
        expanded = []

        # 엔티티 텍스트
        entity_texts = [e.text.lower() for e in entities]

        # 동의어 확장
        for keyword in keywords:
            keyword_lower = keyword.lower()

            # 직접 매칭
            if keyword_lower in self.SYNONYM_MAP:
                for syn in self.SYNONYM_MAP[keyword_lower]:
                    if syn.lower() not in entity_texts and syn not in expanded:
                        expanded.append(syn)

            # 부분 매칭 (구문)
            for key, synonyms in self.SYNONYM_MAP.items():
                if keyword_lower in key.lower():
                    for syn in synonyms:
                        if syn.lower() not in entity_texts and syn not in expanded:
                            expanded.append(syn)

        # 엔티티 기반 확장
        for entity in entities:
            entity_lower = entity.text.lower()
            if entity_lower in self.SYNONYM_MAP:
                for syn in self.SYNONYM_MAP[entity_lower]:
                    if syn not in expanded:
                        expanded.append(syn)

        # 최대 개수 제한
        return expanded[:max_expansions]

    def _calculate_confidence(
        self,
        entities: list[MedicalEntity],
        intent: QueryIntent,
        keywords: list[str]
    ) -> float:
        """파싱 신뢰도 계산.

        Args:
            entities: 엔티티 목록
            intent: 의도
            keywords: 키워드 목록

        Returns:
            신뢰도 (0.0~1.0)
        """
        confidence = 0.5  # 기본값

        # 엔티티가 있으면 신뢰도 증가
        if entities:
            confidence += min(0.3, len(entities) * 0.1)

        # 명확한 의도가 있으면 신뢰도 증가
        if intent != QueryIntent.SEARCH:
            confidence += 0.1

        # 키워드가 충분하면 신뢰도 증가
        if len(keywords) >= 2:
            confidence += 0.1

        return min(1.0, confidence)

    def _enrich_with_snomed(
        self,
        entities: list[MedicalEntity],
    ) -> dict[str, str]:
        """Enrich entities with SNOMED-CT codes.

        Looks up each entity in the SNOMED mapping dictionaries
        and assigns snomed_id and normalized_form where found.

        Args:
            entities: List of extracted medical entities

        Returns:
            Dict mapping entity text to SNOMED code
        """
        snomed_codes: dict[str, str] = {}

        for entity in entities:
            mapping = None

            if entity.entity_type == EntityType.PROCEDURE:
                mapping = get_snomed_for_intervention(entity.text)
            elif entity.entity_type == EntityType.DISEASE:
                mapping = get_snomed_for_pathology(entity.text)
            elif entity.entity_type == EntityType.SYMPTOM:
                # Symptoms may map to outcomes
                mapping = get_snomed_for_outcome(entity.text)
            elif entity.entity_type == EntityType.ANATOMY:
                mapping = get_snomed_for_anatomy(entity.text)
            elif entity.entity_type == EntityType.MEASUREMENT:
                mapping = get_snomed_for_outcome(entity.text)

            if mapping:
                entity.snomed_id = mapping.code
                entity.normalized_form = mapping.term
                snomed_codes[entity.text] = mapping.code
                logger.debug(
                    f"SNOMED enrichment: {entity.text} -> "
                    f"{mapping.code} ({mapping.term})"
                )

        return snomed_codes

    def get_entity_types(self) -> list[str]:
        """지원하는 엔티티 유형 목록 반환."""
        return [e.value for e in EntityType]

    def get_intent_types(self) -> list[str]:
        """지원하는 의도 유형 목록 반환."""
        return [i.value for i in QueryIntent]


def create_search_query(parsed: ParsedQuery) -> str:
    """파싱된 쿼리를 검색 쿼리로 변환.

    Args:
        parsed: 파싱된 쿼리

    Returns:
        검색용 쿼리 문자열
    """
    terms = []

    # 엔티티 텍스트
    for entity in parsed.entities:
        terms.append(entity.text)

    # 키워드
    for keyword in parsed.keywords:
        if keyword not in terms:
            terms.append(keyword)

    # 확장 용어 (가중치 낮게)
    for expanded in parsed.expanded_terms[:3]:
        if expanded.lower() not in [t.lower() for t in terms]:
            terms.append(expanded)

    return " ".join(terms)
