"""Patient Context Parser for Clinical Decision Support.

자연어 쿼리에서 환자 정보를 추출하고 구조화.

Example:
    >>> parser = PatientContextParser()
    >>> context = parser.parse("65세 남성, 당뇨 있음, Lumbar Stenosis로 보존적 치료 실패")
    >>> print(context.age)  # 65
    >>> print(context.comorbidities)  # ["Diabetes"]
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(Enum):
    """질환 중증도."""
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class FunctionalStatus(Enum):
    """기능 상태."""
    INDEPENDENT = "independent"
    AMBULATORY = "ambulatory"
    LIMITED = "limited"
    WHEELCHAIR = "wheelchair"
    BEDRIDDEN = "bedridden"
    UNKNOWN = "unknown"


class AgeGroup(Enum):
    """나이 그룹."""
    YOUNG_ADULT = "young_adult"      # < 40세
    MIDDLE_AGED = "middle_aged"      # 40-59세
    ELDERLY = "elderly"              # 60-74세
    VERY_ELDERLY = "very_elderly"    # 75세 이상
    UNKNOWN = "unknown"


@dataclass
class PatientContext:
    """환자 컨텍스트 정보.

    Attributes:
        age: 나이 (None이면 미상)
        sex: 성별 ("M", "F", None)
        comorbidities: 동반질환 목록
        pathology: 주 진단명
        severity: 중증도
        prior_treatments: 이전 치료 목록
        failed_treatments: 실패한 치료 목록
        functional_status: 기능 상태
        symptoms: 증상 목록
        duration_months: 증상 지속 기간 (개월)
        anatomy_levels: 해부학적 위치 (예: ["L4-5", "L5-S1"])
        preferences: 환자 선호사항
        contraindications: 금기사항
    """
    age: Optional[int] = None
    sex: Optional[str] = None
    comorbidities: list[str] = field(default_factory=list)
    pathology: str = ""
    severity: Severity = Severity.UNKNOWN
    prior_treatments: list[str] = field(default_factory=list)
    failed_treatments: list[str] = field(default_factory=list)
    functional_status: FunctionalStatus = FunctionalStatus.UNKNOWN
    symptoms: list[str] = field(default_factory=list)
    duration_months: Optional[int] = None
    anatomy_levels: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)

    def get_age_group(self) -> AgeGroup:
        """나이 그룹 반환."""
        if self.age is None:
            return AgeGroup.UNKNOWN
        if self.age < 40:
            return AgeGroup.YOUNG_ADULT
        elif self.age < 60:
            return AgeGroup.MIDDLE_AGED
        elif self.age < 75:
            return AgeGroup.ELDERLY
        else:
            return AgeGroup.VERY_ELDERLY

    def has_comorbidity(self, condition: str) -> bool:
        """특정 동반질환 여부 확인."""
        condition_lower = condition.lower()
        return any(condition_lower in c.lower() for c in self.comorbidities)

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "age": self.age,
            "age_group": self.get_age_group().value,
            "sex": self.sex,
            "comorbidities": self.comorbidities,
            "pathology": self.pathology,
            "severity": self.severity.value,
            "prior_treatments": self.prior_treatments,
            "failed_treatments": self.failed_treatments,
            "functional_status": self.functional_status.value,
            "symptoms": self.symptoms,
            "duration_months": self.duration_months,
            "anatomy_levels": self.anatomy_levels,
            "preferences": self.preferences,
            "contraindications": self.contraindications,
        }


class PatientContextParser:
    """환자 정보 파서.

    자연어 텍스트에서 환자 컨텍스트를 추출.

    Example:
        >>> parser = PatientContextParser()
        >>> ctx = parser.parse("65세 당뇨 환자, L4-5 협착증으로 물리치료 실패")
        >>> print(ctx.age)  # 65
    """

    # 동반질환 매핑
    COMORBIDITY_PATTERNS = {
        "Diabetes": [
            r"당뇨", r"DM", r"diabetes", r"diabetic",
            r"혈당", r"insulin"
        ],
        "Hypertension": [
            r"고혈압", r"HTN", r"hypertension", r"혈압"
        ],
        "Osteoporosis": [
            r"골다공증", r"osteoporosis", r"bone density",
            r"골밀도\s*저하"
        ],
        "Cardiac Disease": [
            r"심장", r"cardiac", r"심부전", r"heart failure",
            r"관상동맥", r"CAD", r"심근경색", r"MI"
        ],
        "Obesity": [
            r"비만", r"obesity", r"BMI\s*>\s*30", r"과체중"
        ],
        "Smoking": [
            r"흡연", r"smoking", r"smoker", r"담배"
        ],
        "Renal Disease": [
            r"신부전", r"CKD", r"신장", r"renal", r"투석"
        ],
        "Rheumatoid Arthritis": [
            r"류마티스", r"RA", r"rheumatoid"
        ],
        "Ankylosing Spondylitis": [
            r"강직성\s*척추염", r"AS", r"ankylosing"
        ],
    }

    # 질환 매핑
    PATHOLOGY_PATTERNS = {
        "Lumbar Stenosis": [
            r"요추\s*협착", r"lumbar\s*stenosis", r"척추관\s*협착",
            r"L\d-?\d?\s*협착", r"spinal\s*stenosis"
        ],
        "Disc Herniation": [
            r"디스크\s*탈출", r"추간판\s*탈출", r"herniation",
            r"HNP", r"HIVD", r"디스크"
        ],
        "Spondylolisthesis": [
            r"전방\s*전위", r"spondylolisthesis", r"척추\s*전방\s*전위"
        ],
        "Degenerative Disc Disease": [
            r"퇴행성\s*디스크", r"DDD", r"degenerative\s*disc"
        ],
        "Scoliosis": [
            r"측만", r"scoliosis", r"AIS", r"성인\s*측만"
        ],
        "Kyphosis": [
            r"후만", r"kyphosis", r"굽음"
        ],
        "Fracture": [
            r"골절", r"fracture", r"압박\s*골절", r"compression"
        ],
        "Tumor": [
            r"종양", r"tumor", r"전이", r"metastasis"
        ],
    }

    # 치료 매핑
    TREATMENT_PATTERNS = {
        "Conservative Care": [
            r"보존적", r"conservative", r"약물", r"medication"
        ],
        "Physical Therapy": [
            r"물리\s*치료", r"PT", r"physical\s*therapy", r"재활"
        ],
        "Injection": [
            r"주사", r"injection", r"신경\s*차단", r"block",
            r"epidural", r"경막외"
        ],
        "Fusion Surgery": [
            r"유합", r"fusion", r"고정술"
        ],
        "Decompression": [
            r"감압", r"decompression", r"laminectomy"
        ],
    }

    # 증상 매핑
    SYMPTOM_PATTERNS = {
        "Back Pain": [
            r"요통", r"허리\s*통증", r"back\s*pain", r"LBP"
        ],
        "Leg Pain": [
            r"하지\s*통증", r"다리\s*통증", r"leg\s*pain",
            r"방사통", r"radicular"
        ],
        "Numbness": [
            r"저림", r"numbness", r"감각\s*저하", r"paresthesia"
        ],
        "Weakness": [
            r"근력\s*저하", r"weakness", r"마비", r"약화"
        ],
        "Claudication": [
            r"파행", r"claudication", r"걷기\s*어려"
        ],
        "Bowel/Bladder": [
            r"대소변", r"bowel", r"bladder", r"배뇨", r"배변"
        ],
    }

    def __init__(self):
        """초기화."""
        self._compile_patterns()

    def _compile_patterns(self):
        """정규식 패턴 컴파일."""
        self._comorbidity_re = {
            name: [re.compile(p, re.IGNORECASE) for p in patterns]
            for name, patterns in self.COMORBIDITY_PATTERNS.items()
        }
        self._pathology_re = {
            name: [re.compile(p, re.IGNORECASE) for p in patterns]
            for name, patterns in self.PATHOLOGY_PATTERNS.items()
        }
        self._treatment_re = {
            name: [re.compile(p, re.IGNORECASE) for p in patterns]
            for name, patterns in self.TREATMENT_PATTERNS.items()
        }
        self._symptom_re = {
            name: [re.compile(p, re.IGNORECASE) for p in patterns]
            for name, patterns in self.SYMPTOM_PATTERNS.items()
        }

    def parse(self, text: str) -> PatientContext:
        """텍스트에서 환자 정보 추출.

        Args:
            text: 환자 정보가 포함된 자연어 텍스트

        Returns:
            PatientContext 객체
        """
        context = PatientContext()

        # 나이 추출
        context.age = self._extract_age(text)

        # 성별 추출
        context.sex = self._extract_sex(text)

        # 동반질환 추출
        context.comorbidities = self._extract_comorbidities(text)

        # 질환 추출
        context.pathology = self._extract_pathology(text)

        # 중증도 추출
        context.severity = self._extract_severity(text)

        # 치료 추출
        treatments = self._extract_treatments(text)
        context.prior_treatments = treatments
        context.failed_treatments = self._extract_failed_treatments(text, treatments)

        # 증상 추출
        context.symptoms = self._extract_symptoms(text)

        # 해부학적 위치 추출
        context.anatomy_levels = self._extract_anatomy(text)

        # 증상 기간 추출
        context.duration_months = self._extract_duration(text)

        logger.debug(f"Parsed patient context: {context.to_dict()}")

        return context

    def _extract_age(self, text: str) -> Optional[int]:
        """나이 추출."""
        patterns = [
            r"(\d{1,3})\s*세",
            r"(\d{1,3})\s*살",
            r"(\d{1,3})\s*years?\s*old",
            r"age[:\s]*(\d{1,3})",
            r"(\d{2})\s*[MFmf](?:\s|,|$)",  # "65M" 형식
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                age = int(match.group(1))
                if 1 <= age <= 120:
                    return age
        return None

    def _extract_sex(self, text: str) -> Optional[str]:
        """성별 추출."""
        male_patterns = [r"남성", r"남자", r"\bmale\b", r"\bM\b(?=\s|,|$)"]
        female_patterns = [r"여성", r"여자", r"\bfemale\b", r"\bF\b(?=\s|,|$)"]

        for pattern in male_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "M"

        for pattern in female_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "F"

        return None

    def _extract_comorbidities(self, text: str) -> list[str]:
        """동반질환 추출."""
        found = []
        for name, patterns in self._comorbidity_re.items():
            for pattern in patterns:
                if pattern.search(text):
                    if name not in found:
                        found.append(name)
                    break
        return found

    def _extract_pathology(self, text: str) -> str:
        """주 진단명 추출."""
        for name, patterns in self._pathology_re.items():
            for pattern in patterns:
                if pattern.search(text):
                    return name
        return ""

    def _extract_severity(self, text: str) -> Severity:
        """중증도 추출."""
        severe_patterns = [
            r"심한", r"severe", r"중증", r"심각",
            r"grade\s*[34]", r"심함"
        ]
        moderate_patterns = [
            r"중등도", r"moderate", r"중간", r"grade\s*2"
        ]
        mild_patterns = [
            r"경미", r"mild", r"경증", r"가벼운", r"grade\s*1"
        ]

        text_lower = text.lower()

        for pattern in severe_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return Severity.SEVERE

        for pattern in moderate_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return Severity.MODERATE

        for pattern in mild_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return Severity.MILD

        return Severity.UNKNOWN

    def _extract_treatments(self, text: str) -> list[str]:
        """이전 치료 추출."""
        found = []
        for name, patterns in self._treatment_re.items():
            for pattern in patterns:
                if pattern.search(text):
                    if name not in found:
                        found.append(name)
                    break
        return found

    def _extract_failed_treatments(
        self, text: str, all_treatments: list[str]
    ) -> list[str]:
        """실패한 치료 추출."""
        failed = []
        failure_patterns = [
            r"실패", r"failed", r"효과\s*없", r"호전\s*없",
            r"불충분", r"insufficient", r"반응\s*없"
        ]

        for pattern in failure_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # 실패 언급이 있으면 모든 이전 치료를 실패로 간주
                failed = all_treatments.copy()
                break

        return failed

    def _extract_symptoms(self, text: str) -> list[str]:
        """증상 추출."""
        found = []
        for name, patterns in self._symptom_re.items():
            for pattern in patterns:
                if pattern.search(text):
                    if name not in found:
                        found.append(name)
                    break
        return found

    def _extract_anatomy(self, text: str) -> list[str]:
        """해부학적 위치 추출."""
        anatomy = []

        # 요추 레벨
        lumbar_pattern = r"L(\d)[-–]?(\d|S1)?"
        for match in re.finditer(lumbar_pattern, text, re.IGNORECASE):
            level = f"L{match.group(1)}"
            if match.group(2):
                if match.group(2).upper() == "S1":
                    level += "-S1"
                else:
                    level += f"-L{match.group(2)}"
            if level not in anatomy:
                anatomy.append(level)

        # 경추 레벨
        cervical_pattern = r"C(\d)[-–]?(\d)?"
        for match in re.finditer(cervical_pattern, text, re.IGNORECASE):
            level = f"C{match.group(1)}"
            if match.group(2):
                level += f"-C{match.group(2)}"
            if level not in anatomy:
                anatomy.append(level)

        return anatomy

    def _extract_duration(self, text: str) -> Optional[int]:
        """증상 기간 추출 (개월)."""
        # 년 단위
        year_match = re.search(r"(\d+)\s*년", text)
        if year_match:
            return int(year_match.group(1)) * 12

        # 개월 단위
        month_match = re.search(r"(\d+)\s*개?월", text)
        if month_match:
            return int(month_match.group(1))

        # 주 단위
        week_match = re.search(r"(\d+)\s*주", text)
        if week_match:
            return max(1, int(week_match.group(1)) // 4)

        return None

    def parse_structured(self, data: dict) -> PatientContext:
        """구조화된 데이터에서 환자 정보 생성.

        Args:
            data: 딕셔너리 형태의 환자 정보

        Returns:
            PatientContext 객체
        """
        severity_map = {
            "mild": Severity.MILD,
            "moderate": Severity.MODERATE,
            "severe": Severity.SEVERE,
        }

        func_status_map = {
            "independent": FunctionalStatus.INDEPENDENT,
            "ambulatory": FunctionalStatus.AMBULATORY,
            "limited": FunctionalStatus.LIMITED,
            "wheelchair": FunctionalStatus.WHEELCHAIR,
            "bedridden": FunctionalStatus.BEDRIDDEN,
        }

        return PatientContext(
            age=data.get("age"),
            sex=data.get("sex"),
            comorbidities=data.get("comorbidities", []),
            pathology=data.get("pathology", ""),
            severity=severity_map.get(
                data.get("severity", "").lower(),
                Severity.UNKNOWN
            ),
            prior_treatments=data.get("prior_treatments", []),
            failed_treatments=data.get("failed_treatments", []),
            functional_status=func_status_map.get(
                data.get("functional_status", "").lower(),
                FunctionalStatus.UNKNOWN
            ),
            symptoms=data.get("symptoms", []),
            duration_months=data.get("duration_months"),
            anatomy_levels=data.get("anatomy_levels", []),
            preferences=data.get("preferences", []),
            contraindications=data.get("contraindications", []),
        )


# 편의 함수
def parse_patient_context(text: str) -> PatientContext:
    """환자 정보 파싱 편의 함수."""
    parser = PatientContextParser()
    return parser.parse(text)
