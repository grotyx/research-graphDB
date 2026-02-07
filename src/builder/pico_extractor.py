"""PICO Extractor module for extracting Patient, Intervention, Comparison, Outcome elements."""

import re
from dataclasses import dataclass, field
from typing import Optional

# scispaCy는 선택적 의존성
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


@dataclass
class PICOElement:
    """단일 PICO 요소."""
    text: str
    confidence: float                     # 신뢰도 (0.0 ~ 1.0)
    source_span: tuple[int, int] = (0, 0)  # 원본 텍스트 위치
    entities: list[str] = field(default_factory=list)  # 관련 의학 엔티티


@dataclass
class PICOInput:
    """PICO 추출 입력."""
    text: str
    title: Optional[str] = None
    abstract: Optional[str] = None


@dataclass
class PICOOutput:
    """PICO 추출 결과."""
    population: list[PICOElement] = field(default_factory=list)
    intervention: list[PICOElement] = field(default_factory=list)
    comparison: list[PICOElement] = field(default_factory=list)
    outcome: list[PICOElement] = field(default_factory=list)

    study_question: Optional[str] = None  # 연구 질문 요약
    confidence: float = 0.0               # 전체 추출 신뢰도


class PICOExtractor:
    """PICO 추출기."""

    # Population 패턴
    POPULATION_PATTERNS = {
        "demographic": [
            r'patients?\s+(?:with|who|aged|having)\s+([^.;]+)',
            r'(?:adult|pediatric|elderly|male|female)\s+patients?\s+(?:with\s+)?([^.;]+)',
            r'(?:men|women|children|adolescents)\s+(?:with|aged)\s+([^.;]+)',
            r'subjects?\s+(?:with|who)\s+([^.;]+)',
            r'participants?\s+(?:with|who)\s+([^.;]+)',
            r'individuals?\s+(?:with|who)\s+([^.;]+)',
        ],
        "criteria": [
            r'inclusion\s+criteria[:\s]+([^.]+(?:\.|;))',
            r'eligible\s+(?:patients?|subjects?)\s+(?:were|included)\s+([^.;]+)',
            r'we\s+(?:enrolled|recruited|included)\s+([^.;]+)',
        ],
        "condition": [
            r'(?:diagnosed\s+with|suffering\s+from|affected\s+by)\s+([^.;]+)',
            r'(?:type\s+[12]|gestational)\s+diabetes(?:\s+mellitus)?',
            r'(?:stage\s+[IVX]+|grade\s+[1-4])\s+([^.;]+)',
        ],
    }

    # Intervention 패턴
    INTERVENTION_PATTERNS = {
        "treatment": [
            r'(?:treated\s+with|received|administered)\s+([^.;,]+)',
            r'([A-Za-z]+(?:\s+\d+\s*(?:mg|g|ml|mcg|IU))?)\s+(?:therapy|treatment|regimen)',
            r'(?:oral|intravenous|subcutaneous|intramuscular)\s+([^.;,]+)',
        ],
        "procedure": [
            r'(?:underwent|performed|received)\s+([^.;]+(?:surgery|procedure|intervention))',
        ],
        "dosage": [
            r'(\d+(?:\.\d+)?\s*(?:mg|g|ml|mcg|IU)(?:\s*/?\s*(?:day|daily|week|weekly))?)',
        ],
    }

    # Comparison 패턴
    COMPARISON_PATTERNS = {
        "control": [
            r'(?:placebo|sham|control)\s+(?:group|arm)?',
            r'(?:compared\s+(?:to|with)|versus|vs\.?)\s+([^.;,]+)',
            r'standard\s+(?:of\s+)?care',
            r'usual\s+care',
            r'no\s+(?:treatment|intervention)',
        ],
        "active": [
            r'(?:active\s+)?comparator\s+([^.;,]+)?',
            r'(?:compared\s+with|vs\.?)\s+([A-Za-z]+(?:\s+\d+\s*mg)?)',
        ],
    }

    # Outcome 패턴
    OUTCOME_PATTERNS = {
        "primary": [
            r'primary\s+(?:outcome|endpoint|end\s*point)[:\s]+([^.;]+)',
            r'main\s+outcome\s+measure[:\s]+([^.;]+)',
            r'primary\s+efficacy\s+(?:outcome|endpoint)[:\s]+([^.;]+)',
        ],
        "secondary": [
            r'secondary\s+(?:outcomes?|endpoints?)[:\s]+([^.;]+)',
            r'secondary\s+(?:outcome|endpoint)\s+(?:was|were|included)\s+([^.;]+)',
        ],
        "measures": [
            r'(?:measured|assessed|evaluated)\s+(?:by\s+)?([^.;]+)',
            r'(HbA1c|BMI|blood\s+pressure|mortality|survival|hospitalization)',
            r'((?:all-cause|cardiovascular|CV)\s+(?:mortality|death))',
            r'(quality\s+of\s+life|QoL|SF-36|EQ-5D)',
            r'(MACE|major\s+adverse\s+cardiovascular\s+events?)',
        ],
        "timeframe": [
            r'at\s+(\d+\s*(?:weeks?|months?|years?))',
            r'(\d+)[- ](?:week|month|year)\s+(?:follow[- ]?up|outcome)',
        ],
    }

    # Context 구문 (패턴 매칭 품질 향상용)
    CONTEXT_PHRASES = {
        "population": ["enrolled", "recruited", "included", "eligible",
                      "study population", "target population", "patient population"],
        "intervention": ["intervention group", "treatment arm", "experimental group",
                        "received", "administered", "treated with"],
        "comparison": ["control group", "comparison group", "comparator arm",
                      "versus", "compared to", "compared with", "placebo"],
        "outcome": ["primary outcome", "primary endpoint", "main outcome",
                   "secondary outcome", "efficacy endpoint", "safety endpoint"],
    }

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - spacy_model: scispaCy 모델명 (기본값: "en_core_sci_lg")
                - min_confidence: 최소 신뢰도 (기본값: 0.3)
                - use_ner: NER 사용 여부 (기본값: True if spacy available)
        """
        self.config = config or {}
        self.min_confidence = self.config.get("min_confidence", 0.3)
        self.use_ner = self.config.get("use_ner", SPACY_AVAILABLE)

        # scispaCy 모델 로드 (가능한 경우)
        self.nlp = None
        if self.use_ner and SPACY_AVAILABLE:
            model_name = self.config.get("spacy_model", "en_core_sci_lg")
            try:
                self.nlp = spacy.load(model_name)
            except OSError:
                # 모델이 없으면 NER 비활성화
                self.use_ner = False

        # 정규식 패턴 컴파일
        self._compiled_patterns = self._compile_all_patterns()

    def _compile_all_patterns(self) -> dict:
        """모든 패턴을 정규식으로 컴파일."""
        compiled = {
            "population": {},
            "intervention": {},
            "comparison": {},
            "outcome": {},
        }

        for category, patterns in self.POPULATION_PATTERNS.items():
            compiled["population"][category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

        for category, patterns in self.INTERVENTION_PATTERNS.items():
            compiled["intervention"][category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

        for category, patterns in self.COMPARISON_PATTERNS.items():
            compiled["comparison"][category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

        for category, patterns in self.OUTCOME_PATTERNS.items():
            compiled["outcome"][category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

        return compiled

    def extract(self, input_data: PICOInput) -> PICOOutput:
        """PICO 요소 추출.

        Args:
            input_data: 추출 입력 데이터

        Returns:
            PICO 추출 결과
        """
        # 텍스트 준비
        full_text = self._prepare_text(input_data)

        if not full_text.strip():
            return PICOOutput(confidence=0.0)

        # NER로 의학 엔티티 추출 (가능한 경우)
        medical_entities = {}
        if self.use_ner and self.nlp:
            medical_entities = self._extract_medical_entities(full_text)

        # 각 PICO 요소 추출
        population = self._extract_population(full_text, medical_entities)
        intervention = self._extract_intervention(full_text, medical_entities)
        comparison = self._extract_comparison(full_text, medical_entities)
        outcome = self._extract_outcome(full_text, medical_entities)

        # 연구 질문 생성
        study_question = self._generate_study_question(
            population, intervention, comparison, outcome
        )

        # 전체 신뢰도 계산
        confidence = self._calculate_overall_confidence(
            population, intervention, comparison, outcome
        )

        return PICOOutput(
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            study_question=study_question,
            confidence=round(confidence, 3)
        )

    def _prepare_text(self, input_data: PICOInput) -> str:
        """텍스트 준비.

        Args:
            input_data: 입력 데이터

        Returns:
            결합된 텍스트
        """
        parts = []

        if input_data.title:
            parts.append(input_data.title)

        if input_data.abstract:
            parts.append(input_data.abstract)

        if input_data.text:
            parts.append(input_data.text)

        return " ".join(parts)

    def _extract_medical_entities(self, text: str) -> dict:
        """scispaCy로 의학 엔티티 추출.

        Args:
            text: 분석할 텍스트

        Returns:
            엔티티 딕셔너리
        """
        entities = {
            "diseases": [],
            "drugs": [],
            "procedures": [],
            "measurements": []
        }

        if not self.nlp:
            return entities

        doc = self.nlp(text)

        for ent in doc.ents:
            ent_text = ent.text.strip()
            if not ent_text:
                continue

            # scispaCy 엔티티 레이블에 따라 분류
            label = ent.label_.upper()

            if label in ["DISEASE", "DISORDER", "CONDITION"]:
                entities["diseases"].append(ent_text)
            elif label in ["CHEMICAL", "DRUG", "MEDICATION"]:
                entities["drugs"].append(ent_text)
            elif label in ["PROCEDURE", "TREATMENT"]:
                entities["procedures"].append(ent_text)
            elif label in ["MEASUREMENT", "TEST", "LAB"]:
                entities["measurements"].append(ent_text)

        # 중복 제거
        for key in entities:
            entities[key] = list(set(entities[key]))

        return entities

    def _extract_population(
        self,
        text: str,
        medical_entities: dict
    ) -> list[PICOElement]:
        """Population 추출.

        Args:
            text: 분석할 텍스트
            medical_entities: 의학 엔티티

        Returns:
            Population 요소 목록
        """
        elements = []
        seen_texts = set()

        for category, patterns in self._compiled_patterns["population"].items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group(1) if match.lastindex else match.group(0)
                    matched_text = self._clean_text(matched_text)

                    if not matched_text or matched_text.lower() in seen_texts:
                        continue

                    seen_texts.add(matched_text.lower())

                    # 신뢰도 계산
                    confidence = self._calculate_element_confidence(
                        matched_text, "population", medical_entities
                    )

                    if confidence >= self.min_confidence:
                        elements.append(PICOElement(
                            text=matched_text,
                            confidence=confidence,
                            source_span=match.span(),
                            entities=medical_entities.get("diseases", [])
                        ))

        return elements[:5]  # 상위 5개만

    def _extract_intervention(
        self,
        text: str,
        medical_entities: dict
    ) -> list[PICOElement]:
        """Intervention 추출.

        Args:
            text: 분석할 텍스트
            medical_entities: 의학 엔티티

        Returns:
            Intervention 요소 목록
        """
        elements = []
        seen_texts = set()

        for category, patterns in self._compiled_patterns["intervention"].items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group(1) if match.lastindex else match.group(0)
                    matched_text = self._clean_text(matched_text)

                    if not matched_text or matched_text.lower() in seen_texts:
                        continue

                    seen_texts.add(matched_text.lower())

                    confidence = self._calculate_element_confidence(
                        matched_text, "intervention", medical_entities
                    )

                    if confidence >= self.min_confidence:
                        elements.append(PICOElement(
                            text=matched_text,
                            confidence=confidence,
                            source_span=match.span(),
                            entities=medical_entities.get("drugs", []) +
                                    medical_entities.get("procedures", [])
                        ))

        return elements[:5]

    def _extract_comparison(
        self,
        text: str,
        medical_entities: dict
    ) -> list[PICOElement]:
        """Comparison 추출.

        Args:
            text: 분석할 텍스트
            medical_entities: 의학 엔티티

        Returns:
            Comparison 요소 목록
        """
        elements = []
        seen_texts = set()

        for category, patterns in self._compiled_patterns["comparison"].items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group(1) if match.lastindex else match.group(0)
                    matched_text = self._clean_text(matched_text)

                    if not matched_text or matched_text.lower() in seen_texts:
                        continue

                    seen_texts.add(matched_text.lower())

                    confidence = self._calculate_element_confidence(
                        matched_text, "comparison", medical_entities
                    )

                    if confidence >= self.min_confidence:
                        elements.append(PICOElement(
                            text=matched_text,
                            confidence=confidence,
                            source_span=match.span(),
                            entities=medical_entities.get("drugs", [])
                        ))

        return elements[:3]

    def _extract_outcome(
        self,
        text: str,
        medical_entities: dict
    ) -> list[PICOElement]:
        """Outcome 추출.

        Args:
            text: 분석할 텍스트
            medical_entities: 의학 엔티티

        Returns:
            Outcome 요소 목록
        """
        elements = []
        seen_texts = set()

        for category, patterns in self._compiled_patterns["outcome"].items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group(1) if match.lastindex else match.group(0)
                    matched_text = self._clean_text(matched_text)

                    if not matched_text or matched_text.lower() in seen_texts:
                        continue

                    seen_texts.add(matched_text.lower())

                    confidence = self._calculate_element_confidence(
                        matched_text, "outcome", medical_entities
                    )

                    # Primary outcome에 높은 신뢰도 부여
                    if category == "primary":
                        confidence = min(1.0, confidence + 0.2)

                    if confidence >= self.min_confidence:
                        elements.append(PICOElement(
                            text=matched_text,
                            confidence=confidence,
                            source_span=match.span(),
                            entities=medical_entities.get("measurements", [])
                        ))

        return elements[:5]

    def _clean_text(self, text: str) -> str:
        """텍스트 정리.

        Args:
            text: 정리할 텍스트

        Returns:
            정리된 텍스트
        """
        if not text:
            return ""

        # 앞뒤 공백 및 구두점 제거
        text = text.strip()
        text = re.sub(r'^[,;:\s]+|[,;:\s]+$', '', text)

        # 너무 짧거나 긴 텍스트 필터링
        if len(text) < 3 or len(text) > 200:
            return ""

        return text

    def _calculate_element_confidence(
        self,
        text: str,
        element_type: str,
        medical_entities: dict
    ) -> float:
        """요소 신뢰도 계산.

        Args:
            text: 추출된 텍스트
            element_type: PICO 요소 유형
            medical_entities: 의학 엔티티

        Returns:
            신뢰도 (0.0~1.0)
        """
        confidence = 0.5  # 기본 신뢰도

        # 문맥 구문 포함 여부
        context_phrases = self.CONTEXT_PHRASES.get(element_type, [])
        for phrase in context_phrases:
            if phrase.lower() in text.lower():
                confidence += 0.1
                break

        # 의학 엔티티 포함 여부
        relevant_entities = []
        if element_type == "population":
            relevant_entities = medical_entities.get("diseases", [])
        elif element_type == "intervention":
            relevant_entities = (medical_entities.get("drugs", []) +
                               medical_entities.get("procedures", []))
        elif element_type == "outcome":
            relevant_entities = medical_entities.get("measurements", [])

        for entity in relevant_entities:
            if entity.lower() in text.lower():
                confidence += 0.15
                break

        # 텍스트 길이에 따른 조정 (너무 짧거나 긴 것은 신뢰도 낮음)
        text_len = len(text)
        if 10 <= text_len <= 100:
            confidence += 0.1
        elif text_len < 5:
            confidence -= 0.2

        return min(1.0, max(0.0, confidence))

    def _generate_study_question(
        self,
        population: list[PICOElement],
        intervention: list[PICOElement],
        comparison: list[PICOElement],
        outcome: list[PICOElement]
    ) -> Optional[str]:
        """PICO를 기반으로 연구 질문 생성.

        Args:
            population: Population 요소
            intervention: Intervention 요소
            comparison: Comparison 요소
            outcome: Outcome 요소

        Returns:
            연구 질문 (생성 불가시 None)
        """
        if not (population and intervention and outcome):
            return None

        p_text = population[0].text if population else "patients"
        i_text = intervention[0].text if intervention else "intervention"
        c_text = comparison[0].text if comparison else "standard care"
        o_text = outcome[0].text if outcome else "outcomes"

        # 텍스트 길이 제한
        p_text = p_text[:50] + "..." if len(p_text) > 50 else p_text
        i_text = i_text[:30] + "..." if len(i_text) > 30 else i_text
        c_text = c_text[:30] + "..." if len(c_text) > 30 else c_text
        o_text = o_text[:50] + "..." if len(o_text) > 50 else o_text

        return f"In {p_text}, does {i_text} compared to {c_text} improve {o_text}?"

    def _calculate_overall_confidence(
        self,
        population: list[PICOElement],
        intervention: list[PICOElement],
        comparison: list[PICOElement],
        outcome: list[PICOElement]
    ) -> float:
        """전체 추출 신뢰도 계산.

        Args:
            population: Population 요소
            intervention: Intervention 요소
            comparison: Comparison 요소
            outcome: Outcome 요소

        Returns:
            전체 신뢰도 (0.0~1.0)
        """
        confidences = []

        # 각 요소의 최고 신뢰도 수집
        if population:
            confidences.append(max(e.confidence for e in population))
        if intervention:
            confidences.append(max(e.confidence for e in intervention))
        if comparison:
            confidences.append(max(e.confidence for e in comparison))
        if outcome:
            confidences.append(max(e.confidence for e in outcome))

        if not confidences:
            return 0.0

        # 평균 + 완성도 보너스
        avg_confidence = sum(confidences) / len(confidences)

        # PICO 요소 완성도 (4개 모두 있으면 보너스)
        completeness = len(confidences) / 4.0

        return avg_confidence * 0.7 + completeness * 0.3

    def extract_batch(self, inputs: list[PICOInput]) -> list[PICOOutput]:
        """여러 텍스트를 일괄 추출.

        Args:
            inputs: 입력 데이터 목록

        Returns:
            추출 결과 목록
        """
        return [self.extract(input_data) for input_data in inputs]
