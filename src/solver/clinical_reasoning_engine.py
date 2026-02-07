"""Clinical Reasoning Engine for Spine Surgery Decision Support.

환자 컨텍스트와 근거 데이터를 기반으로 치료 추천을 생성하는 엔진.
임상 규칙, 금기사항, 동반질환 위험도를 종합적으로 평가.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import yaml
from pathlib import Path

from .patient_context_parser import PatientContext, AgeGroup, Severity


class RecommendationConfidence(Enum):
    """추천 신뢰도 수준."""
    HIGH = "high"        # 강한 근거, 낮은 금기 위험
    MODERATE = "moderate"  # 중간 근거 또는 상대적 금기 존재
    LOW = "low"          # 약한 근거 또는 여러 제한 요소
    UNCERTAIN = "uncertain"  # 근거 부족 또는 평가 불가


@dataclass
class Contraindication:
    """금기사항 정보."""
    intervention: str
    condition: str
    severity: str  # absolute, relative
    reason: str = ""
    mitigation: str = ""

    @property
    def is_absolute(self) -> bool:
        """절대 금기인지 확인."""
        return self.severity == "absolute"


@dataclass
class RiskFactor:
    """위험 요소."""
    name: str
    risk_type: str  # infection, hardware_failure, perioperative, etc.
    multiplier: float
    source: str  # comorbidity name


@dataclass
class InterventionScore:
    """수술법 점수 및 평가."""
    intervention: str
    total_score: float
    evidence_score: float = 0.0
    safety_score: float = 1.0
    patient_fit_score: float = 0.0

    contraindications: list[Contraindication] = field(default_factory=list)
    risk_factors: list[RiskFactor] = field(default_factory=list)
    supporting_evidence: list[dict] = field(default_factory=list)

    indication: str = ""
    evidence_level: str = ""
    is_first_line: bool = False

    # 상세 점수 breakdown
    pain_relief_score: float = 0.0
    functional_score: float = 0.0
    return_to_work_score: float = 0.0
    durability_score: float = 0.0
    complication_score: float = 0.0

    def get_absolute_contraindications(self) -> list[Contraindication]:
        """절대 금기 목록."""
        return [c for c in self.contraindications if c.is_absolute]

    def get_relative_contraindications(self) -> list[Contraindication]:
        """상대 금기 목록."""
        return [c for c in self.contraindications if not c.is_absolute]

    def has_absolute_contraindication(self) -> bool:
        """절대 금기가 있는지 확인."""
        return len(self.get_absolute_contraindications()) > 0

    def get_total_risk_multiplier(self) -> float:
        """모든 위험 요소의 누적 배율."""
        if not self.risk_factors:
            return 1.0

        multiplier = 1.0
        for rf in self.risk_factors:
            multiplier *= rf.multiplier
        return multiplier


@dataclass
class TreatmentRecommendation:
    """치료 추천 결과."""
    patient_context: PatientContext
    recommended_interventions: list[InterventionScore]
    alternative_interventions: list[InterventionScore]
    contraindicated_interventions: list[InterventionScore]

    confidence: RecommendationConfidence = RecommendationConfidence.UNCERTAIN
    confidence_reasons: list[str] = field(default_factory=list)

    considerations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # 환자 요약
    patient_summary: str = ""

    # 메타데이터
    total_evidence_count: int = 0
    significant_evidence_count: int = 0

    def get_top_recommendation(self) -> Optional[InterventionScore]:
        """최상위 추천 수술법."""
        if self.recommended_interventions:
            return self.recommended_interventions[0]
        return None

    def get_summary(self) -> str:
        """추천 요약 생성."""
        top = self.get_top_recommendation()
        if not top:
            return "No suitable treatment recommendation found."

        summary_parts = [
            f"Recommended: {top.intervention}",
            f"Confidence: {self.confidence.value.upper()}",
        ]

        if top.evidence_level:
            summary_parts.append(f"Evidence: Level {top.evidence_level}")

        if self.warnings:
            summary_parts.append(f"Warnings: {len(self.warnings)}")

        return " | ".join(summary_parts)


class ClinicalReasoningEngine:
    """임상 추론 엔진.

    환자 정보와 근거 데이터를 종합하여 최적의 치료법을 추천.
    금기사항, 동반질환 위험도, 나이별 결과 가중치를 고려.

    Attributes:
        rules: 임상 규칙 (YAML에서 로드)
        outcome_weights: 나이 그룹별 결과 가중치
    """

    def __init__(self, rules_path: Optional[str] = None):
        """초기화.

        Args:
            rules_path: 임상 규칙 YAML 파일 경로. None이면 기본 경로 사용.
        """
        if rules_path is None:
            # 기본 경로: config/clinical_rules.yaml
            project_root = Path(__file__).parent.parent.parent
            rules_path = project_root / "config" / "clinical_rules.yaml"

        self.rules = self._load_rules(rules_path)
        self.outcome_weights = self.rules.get("outcome_weights_by_age", {})
        self.contraindications_list = self.rules.get("contraindications", [])
        self.pathology_recommendations = self.rules.get("pathology_recommendations", {})
        self.comorbidity_modifiers = self.rules.get("comorbidity_risk_modifiers", {})
        self.severity_modifiers = self.rules.get("severity_modifiers", {})
        self.evidence_requirements = self.rules.get("evidence_requirements", {})

    def _load_rules(self, path) -> dict:
        """YAML 규칙 파일 로드."""
        path = Path(path)
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def recommend_treatment(
        self,
        patient: PatientContext,
        available_evidence: list[dict] = None
    ) -> TreatmentRecommendation:
        """치료법 추천.

        Args:
            patient: 환자 컨텍스트
            available_evidence: 검색된 근거 목록 (GraphEvidence dict 형태)

        Returns:
            TreatmentRecommendation 객체
        """
        available_evidence = available_evidence or []

        # 1. 환자 요약 생성
        patient_summary = self._generate_patient_summary(patient)

        # 2. 후보 수술법 수집
        candidates = self._get_candidate_interventions(patient)

        # 3. 각 후보에 대해 점수 계산
        scored_interventions = []
        for intervention_name in candidates:
            score = self._score_intervention(
                intervention_name, patient, available_evidence
            )
            scored_interventions.append(score)

        # 4. 금기사항 분류
        recommended = []
        alternatives = []
        contraindicated = []

        for score in scored_interventions:
            if score.has_absolute_contraindication():
                contraindicated.append(score)
            elif score.get_relative_contraindications():
                # 상대 금기가 있으면 alternative로 분류
                alternatives.append(score)
            else:
                recommended.append(score)

        # 5. 점수순 정렬
        recommended.sort(key=lambda x: x.total_score, reverse=True)
        alternatives.sort(key=lambda x: x.total_score, reverse=True)

        # 6. 신뢰도 평가
        confidence, confidence_reasons = self._evaluate_confidence(
            patient, recommended, available_evidence
        )

        # 7. 고려사항 및 경고 생성
        considerations = self._generate_considerations(patient, recommended)
        warnings = self._generate_warnings(patient, recommended + alternatives)

        return TreatmentRecommendation(
            patient_context=patient,
            recommended_interventions=recommended,
            alternative_interventions=alternatives,
            contraindicated_interventions=contraindicated,
            confidence=confidence,
            confidence_reasons=confidence_reasons,
            considerations=considerations,
            warnings=warnings,
            patient_summary=patient_summary,
            total_evidence_count=len(available_evidence),
            significant_evidence_count=sum(
                1 for e in available_evidence
                if e.get("is_significant", False)
            )
        )

    def _generate_patient_summary(self, patient: PatientContext) -> str:
        """환자 정보 요약 생성."""
        parts = []

        # 기본 정보
        if patient.age:
            parts.append(f"{patient.age}세")
        if patient.sex:
            sex_kr = "남성" if patient.sex == "male" else "여성"
            parts.append(sex_kr)

        # 진단
        if patient.pathology:
            parts.append(f"진단: {patient.pathology}")

        # 해부학적 위치
        if patient.anatomy_levels:
            parts.append(f"부위: {', '.join(patient.anatomy_levels)}")

        # 증상 기간
        if patient.duration_months:
            parts.append(f"증상 기간: {patient.duration_months}개월")

        # 중증도
        if patient.severity != Severity.UNKNOWN:
            severity_kr = {
                Severity.MILD: "경증",
                Severity.MODERATE: "중등도",
                Severity.SEVERE: "중증"
            }.get(patient.severity, "")
            if severity_kr:
                parts.append(f"중증도: {severity_kr}")

        # 동반질환
        if patient.comorbidities:
            parts.append(f"동반질환: {', '.join(patient.comorbidities)}")

        # 이전 치료
        if patient.failed_treatments:
            parts.append(f"실패한 치료: {', '.join(patient.failed_treatments)}")

        return " | ".join(parts) if parts else "환자 정보 부족"

    def _get_candidate_interventions(self, patient: PatientContext) -> list[str]:
        """후보 수술법 목록 수집."""
        candidates = set()

        # 1. 질환별 추천 수술법에서 수집
        pathology = patient.pathology
        if pathology in self.pathology_recommendations:
            recs = self.pathology_recommendations[pathology]

            # First line
            for item in recs.get("first_line", []):
                candidates.add(item.get("name", ""))

            # Second line
            for item in recs.get("second_line", []):
                candidates.add(item.get("name", ""))

        # 2. 기본 수술법 추가 (질환 매핑이 없는 경우)
        if not candidates:
            # 일반적인 척추 수술법
            default_interventions = [
                "TLIF", "PLIF", "ALIF", "OLIF",
                "Laminectomy", "UBE", "Microdiscectomy"
            ]
            candidates.update(default_interventions)

        # 빈 문자열 제거
        candidates.discard("")

        return list(candidates)

    def _score_intervention(
        self,
        intervention: str,
        patient: PatientContext,
        evidence: list[dict]
    ) -> InterventionScore:
        """수술법 점수 계산."""
        score = InterventionScore(
            intervention=intervention,
            total_score=0.0
        )

        # 1. 금기사항 체크
        score.contraindications = self._check_contraindications(
            intervention, patient
        )

        # 2. 절대 금기가 있으면 점수 0
        if score.has_absolute_contraindication():
            score.total_score = 0.0
            score.safety_score = 0.0
            return score

        # 3. 위험 요소 계산
        score.risk_factors = self._calculate_risk_factors(intervention, patient)
        risk_multiplier = score.get_total_risk_multiplier()

        # 4. 안전성 점수 (위험 배율의 역수)
        score.safety_score = 1.0 / risk_multiplier if risk_multiplier > 0 else 1.0

        # 5. 근거 점수 계산
        score.evidence_score, score.supporting_evidence = \
            self._calculate_evidence_score(intervention, evidence)

        # 6. 환자 적합성 점수 (나이별 가중치 적용)
        score.patient_fit_score = self._calculate_patient_fit(
            intervention, patient, evidence
        )

        # 7. First-line 여부 확인
        score.is_first_line = self._is_first_line(intervention, patient.pathology)
        first_line_bonus = 1.2 if score.is_first_line else 1.0

        # 8. Indication 및 Evidence Level 설정
        score.indication, score.evidence_level = \
            self._get_indication_info(intervention, patient.pathology)

        # 9. 총점 계산
        # 가중치: 근거 40%, 안전성 30%, 환자적합성 30%
        base_score = (
            0.4 * score.evidence_score +
            0.3 * score.safety_score +
            0.3 * score.patient_fit_score
        )

        # 상대 금기 패널티
        relative_penalty = 0.9 ** len(score.get_relative_contraindications())

        score.total_score = base_score * first_line_bonus * relative_penalty

        return score

    def _check_contraindications(
        self,
        intervention: str,
        patient: PatientContext
    ) -> list[Contraindication]:
        """금기사항 체크."""
        contraindications = []

        for rule in self.contraindications_list:
            rule_intervention = rule.get("intervention", "")

            # 해당 수술법에 대한 규칙인지 확인
            if not self._intervention_matches(intervention, rule_intervention):
                continue

            condition = rule.get("condition", "")

            # 조건 평가
            if self._evaluate_condition(condition, patient):
                contraindications.append(Contraindication(
                    intervention=intervention,
                    condition=condition,
                    severity=rule.get("severity", "relative"),
                    reason=rule.get("reason", ""),
                    mitigation=rule.get("mitigation", "")
                ))

        return contraindications

    def _intervention_matches(self, intervention: str, rule_intervention: str) -> bool:
        """수술법이 규칙의 수술법과 매칭되는지 확인."""
        intervention_lower = intervention.lower()
        rule_lower = rule_intervention.lower()

        # 정확한 매칭
        if intervention_lower == rule_lower:
            return True

        # 부분 매칭 (Fusion Surgery → TLIF, PLIF 등)
        if rule_lower == "fusion surgery":
            fusion_types = ["tlif", "plif", "alif", "olif", "llif", "xlif"]
            return intervention_lower in fusion_types

        return False

    def _evaluate_condition(self, condition: str, patient: PatientContext) -> bool:
        """조건 평가."""
        condition_lower = condition.lower()

        # 나이 조건
        if "age" in condition_lower:
            if patient.age is None:
                return False

            # "age > 85" 형태 파싱
            if ">" in condition:
                try:
                    threshold = int(condition.split(">")[-1].strip())
                    return patient.age > threshold
                except ValueError:
                    pass
            elif "<" in condition:
                try:
                    threshold = int(condition.split("<")[-1].strip())
                    return patient.age < threshold
                except ValueError:
                    pass

        # 동반질환 조건
        comorbidity_mapping = {
            "severe_osteoporosis": ["osteoporosis", "severe osteoporosis"],
            "active_infection": ["infection", "active infection"],
            "smoking": ["smoking", "smoker"],
            "vascular_disease": ["vascular disease", "peripheral vascular disease"],
        }

        for key, aliases in comorbidity_mapping.items():
            if key in condition_lower:
                return patient.has_comorbidity(key) or any(
                    patient.has_comorbidity(alias) for alias in aliases
                )

        # 이전 수술 조건
        if "prior" in condition_lower or "previous" in condition_lower:
            if "surgery" in condition_lower:
                return "surgery" in [t.lower() for t in patient.prior_treatments]
            if "abdominal" in condition_lower:
                return any(
                    "abdominal" in t.lower()
                    for t in patient.prior_treatments
                )

        # 해부학적 조건
        if condition_lower in ["l5-s1", "l4-5", "l4-l5"]:
            return condition_lower.replace("-", "") in [
                level.lower().replace("-", "")
                for level in patient.anatomy_levels
            ]

        # Spondylolisthesis grade 조건
        if "spondylolisthesis" in condition_lower and "grade" in condition_lower:
            # 이것은 pathology severity로 판단
            if "grade_2" in condition_lower or "grade 2" in condition_lower:
                return (
                    "spondylolisthesis" in patient.pathology.lower() and
                    patient.severity in [Severity.MODERATE, Severity.SEVERE]
                )

        # Multi-level 조건
        if "multi_level" in condition_lower:
            if ">" in condition:
                try:
                    threshold = int(condition.split(">")[-1].strip())
                    return len(patient.anatomy_levels) > threshold
                except ValueError:
                    pass

        # 불안정성 조건
        if "instability" in condition_lower or "severe_instability" in condition_lower:
            return "instability" in patient.pathology.lower()

        # Scarring 조건
        if "retroperitoneal_scarring" in condition_lower:
            return any(
                "retroperitoneal" in t.lower() or "scarring" in t.lower()
                for t in patient.prior_treatments
            )

        return False

    def _calculate_risk_factors(
        self,
        intervention: str,
        patient: PatientContext
    ) -> list[RiskFactor]:
        """위험 요소 계산."""
        risk_factors = []

        for comorbidity in patient.comorbidities:
            # 동반질환별 위험 배율 조회
            comorbidity_key = self._normalize_comorbidity_key(comorbidity)
            modifiers = self.comorbidity_modifiers.get(comorbidity_key, {})

            for risk_type, multiplier in modifiers.items():
                if isinstance(multiplier, (int, float)) and multiplier != 1.0:
                    risk_factors.append(RiskFactor(
                        name=f"{comorbidity} - {risk_type}",
                        risk_type=risk_type,
                        multiplier=multiplier,
                        source=comorbidity
                    ))

        return risk_factors

    def _normalize_comorbidity_key(self, comorbidity: str) -> str:
        """동반질환 키 정규화."""
        mapping = {
            "dm": "Diabetes",
            "diabetes mellitus": "Diabetes",
            "당뇨": "Diabetes",
            "hypertension": "Hypertension",
            "htn": "Hypertension",
            "고혈압": "Hypertension",
            "osteoporosis": "Osteoporosis",
            "골다공증": "Osteoporosis",
            "smoking": "Smoking",
            "smoker": "Smoking",
            "흡연": "Smoking",
            "obesity": "Obesity",
            "obese": "Obesity",
            "비만": "Obesity",
            "cardiac": "Cardiac Disease",
            "heart disease": "Cardiac Disease",
            "심장질환": "Cardiac Disease",
            "renal": "Renal Disease",
            "kidney": "Renal Disease",
            "신장질환": "Renal Disease",
        }

        return mapping.get(comorbidity.lower(), comorbidity)

    def _calculate_evidence_score(
        self,
        intervention: str,
        evidence: list[dict]
    ) -> tuple[float, list[dict]]:
        """근거 점수 계산."""
        intervention_lower = intervention.lower()
        supporting = []

        # 해당 수술법 관련 근거 필터링
        for e in evidence:
            e_intervention = e.get("intervention", "").lower()

            if intervention_lower in e_intervention or e_intervention in intervention_lower:
                supporting.append(e)

        if not supporting:
            return 0.3, []  # 근거 없음 → 기본 점수

        # 근거 수준별 가중치
        level_weights = {
            "1a": 1.0, "1b": 0.9, "2a": 0.8, "2b": 0.7,
            "3": 0.5, "4": 0.3, "5": 0.1
        }

        total_weight = 0.0
        for e in supporting:
            level = e.get("evidence_level", "5")
            weight = level_weights.get(level, 0.1)

            # 통계적 유의성 보너스
            if e.get("is_significant", False):
                weight *= 1.3

            total_weight += weight

        # 정규화 (최대 1.0)
        evidence_score = min(1.0, total_weight / len(supporting))

        return evidence_score, supporting

    def _calculate_patient_fit(
        self,
        intervention: str,
        patient: PatientContext,
        evidence: list[dict]
    ) -> float:
        """환자 적합성 점수 계산."""
        age_group = patient.get_age_group()

        # 나이 그룹 문자열 변환
        age_group_key = {
            AgeGroup.YOUNG_ADULT: "young_adult",
            AgeGroup.MIDDLE_AGED: "middle_aged",
            AgeGroup.ELDERLY: "elderly",
            AgeGroup.VERY_ELDERLY: "very_elderly"
        }.get(age_group, "middle_aged")

        weights = self.outcome_weights.get(age_group_key, {})

        if not weights:
            return 0.5  # 기본 점수

        # 해당 수술법 근거에서 결과별 점수 추출
        outcome_scores = {
            "pain_relief": 0.5,
            "functional_improvement": 0.5,
            "return_to_work": 0.5,
            "long_term_durability": 0.5,
            "complication_risk": 0.5
        }

        # 근거에서 결과 추출
        intervention_lower = intervention.lower()
        for e in evidence:
            e_intervention = e.get("intervention", "").lower()
            if intervention_lower not in e_intervention and e_intervention not in intervention_lower:
                continue

            outcome = e.get("outcome", "").lower()
            direction = e.get("direction", "")

            # 결과 매핑
            if any(term in outcome for term in ["vas", "pain", "nrs"]):
                if direction == "improved":
                    outcome_scores["pain_relief"] = 0.8
            elif any(term in outcome for term in ["odi", "joa", "sf-36", "function"]):
                if direction == "improved":
                    outcome_scores["functional_improvement"] = 0.8
            elif "fusion" in outcome:
                if direction == "improved":
                    outcome_scores["long_term_durability"] = 0.8
            elif "complication" in outcome:
                if direction == "improved":
                    outcome_scores["complication_risk"] = 0.2  # 낮을수록 좋음

        # 가중 평균 계산
        total = 0.0
        for outcome_key, weight in weights.items():
            score = outcome_scores.get(outcome_key, 0.5)
            total += weight * score

        return total

    def _is_first_line(self, intervention: str, pathology: str) -> bool:
        """First-line 추천인지 확인."""
        if not pathology:
            return False

        recs = self.pathology_recommendations.get(pathology, {})
        first_line = recs.get("first_line", [])

        for item in first_line:
            if item.get("name", "").lower() == intervention.lower():
                return True

        return False

    def _get_indication_info(
        self,
        intervention: str,
        pathology: str
    ) -> tuple[str, str]:
        """적응증 정보 조회."""
        if not pathology:
            return "", ""

        recs = self.pathology_recommendations.get(pathology, {})

        # First line 검색
        for item in recs.get("first_line", []):
            if item.get("name", "").lower() == intervention.lower():
                return item.get("indication", ""), item.get("evidence_level", "")

        # Second line 검색
        for item in recs.get("second_line", []):
            if item.get("name", "").lower() == intervention.lower():
                return item.get("indication", ""), item.get("evidence_level", "")

        return "", ""

    def _evaluate_confidence(
        self,
        patient: PatientContext,
        recommended: list[InterventionScore],
        evidence: list[dict]
    ) -> tuple[RecommendationConfidence, list[str]]:
        """추천 신뢰도 평가."""
        reasons = []

        if not recommended:
            return RecommendationConfidence.UNCERTAIN, ["No suitable intervention found"]

        top = recommended[0]

        # 근거 수준 평가
        high_evidence_levels = ["1a", "1b", "2a"]
        if top.evidence_level in high_evidence_levels:
            reasons.append(f"Strong evidence (Level {top.evidence_level})")
            evidence_confidence = "high"
        elif top.evidence_level in ["2b", "3"]:
            reasons.append(f"Moderate evidence (Level {top.evidence_level})")
            evidence_confidence = "moderate"
        else:
            reasons.append("Limited evidence")
            evidence_confidence = "low"

        # 근거 양 평가
        significant_count = sum(1 for e in evidence if e.get("is_significant", False))
        if significant_count >= 5:
            reasons.append(f"{significant_count} statistically significant studies")
        elif significant_count >= 2:
            reasons.append(f"{significant_count} significant studies")
        elif significant_count == 0:
            reasons.append("No statistically significant studies found")

        # 안전성 평가
        if top.safety_score >= 0.8:
            reasons.append("Low complication risk")
            safety_confidence = "high"
        elif top.safety_score >= 0.5:
            reasons.append("Moderate complication risk")
            safety_confidence = "moderate"
        else:
            reasons.append("Higher complication risk")
            safety_confidence = "low"

        # 환자 정보 완전성
        if patient.age and patient.pathology and patient.severity != Severity.UNKNOWN:
            reasons.append("Complete patient information")
            info_confidence = "high"
        elif patient.age or patient.pathology:
            reasons.append("Partial patient information")
            info_confidence = "moderate"
        else:
            reasons.append("Limited patient information")
            info_confidence = "low"

        # 종합 신뢰도 결정
        confidence_levels = [evidence_confidence, safety_confidence, info_confidence]

        if all(c == "high" for c in confidence_levels):
            return RecommendationConfidence.HIGH, reasons
        elif "low" in confidence_levels:
            if confidence_levels.count("low") >= 2:
                return RecommendationConfidence.LOW, reasons
            return RecommendationConfidence.MODERATE, reasons
        else:
            return RecommendationConfidence.MODERATE, reasons

    def _generate_considerations(
        self,
        patient: PatientContext,
        recommended: list[InterventionScore]
    ) -> list[str]:
        """고려사항 생성."""
        considerations = []

        # 나이 관련
        if patient.age:
            if patient.age >= 75:
                considerations.append(
                    "고령 환자: 합병증 위험과 회복 기간을 고려하여 "
                    "최소 침습적 접근법 우선 고려"
                )
            elif patient.age < 40:
                considerations.append(
                    "젊은 환자: 장기적 예후와 직업 복귀를 "
                    "주요 결과 지표로 고려"
                )

        # 중증도 관련
        severity_considerations = self.severity_modifiers.get(
            patient.severity.value if patient.severity != Severity.UNKNOWN else "moderate",
            {}
        )

        if severity_considerations.get("conservative_first", False):
            min_weeks = severity_considerations.get("min_conservative_weeks", 6)
            considerations.append(
                f"보존적 치료를 최소 {min_weeks}주 시행 후 "
                "수술적 치료 결정 권장"
            )

        if patient.severity == Severity.SEVERE:
            urgent_conditions = severity_considerations.get("urgent_if", [])
            if urgent_conditions:
                considerations.append(
                    f"응급 수술 고려 조건: {', '.join(urgent_conditions)}"
                )

        # 동반질환 관련
        for comorbidity in patient.comorbidities:
            key = self._normalize_comorbidity_key(comorbidity)
            mods = self.comorbidity_modifiers.get(key, {})

            if "infection_risk" in mods:
                considerations.append(
                    f"{comorbidity}: 감염 위험 증가 (×{mods['infection_risk']}), "
                    "주의 깊은 상처 관리 필요"
                )
            if "fusion_rate_reduction" in mods:
                reduction = (1 - mods["fusion_rate_reduction"]) * 100
                considerations.append(
                    f"{comorbidity}: 유합률 {reduction:.0f}% 감소 가능성, "
                    "BMP 등 보조제 고려"
                )

        return considerations

    def _generate_warnings(
        self,
        patient: PatientContext,
        interventions: list[InterventionScore]
    ) -> list[str]:
        """경고 생성."""
        warnings = []

        for intervention in interventions:
            # 상대 금기 경고
            for ci in intervention.get_relative_contraindications():
                if ci.mitigation:
                    warnings.append(
                        f"[{intervention.intervention}] {ci.condition}: "
                        f"{ci.mitigation}"
                    )
                else:
                    warnings.append(
                        f"[{intervention.intervention}] "
                        f"상대 금기: {ci.condition}"
                    )

            # 높은 위험 요소 경고
            high_risk_factors = [
                rf for rf in intervention.risk_factors
                if rf.multiplier >= 2.0
            ]
            for rf in high_risk_factors:
                warnings.append(
                    f"[{intervention.intervention}] "
                    f"높은 {rf.risk_type} 위험 (×{rf.multiplier:.1f}) - "
                    f"{rf.source}"
                )

        return warnings


def create_reasoning_engine(rules_path: Optional[str] = None) -> ClinicalReasoningEngine:
    """팩토리 함수: ClinicalReasoningEngine 인스턴스 생성.

    Args:
        rules_path: 임상 규칙 YAML 파일 경로

    Returns:
        ClinicalReasoningEngine 인스턴스
    """
    return ClinicalReasoningEngine(rules_path)
