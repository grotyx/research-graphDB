"""Clinical Decision Support Page.

환자 정보를 입력받아 최적의 치료법을 추천하는 임상 의사결정 지원 페이지.
"""

import streamlit as st
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from solver.patient_context_parser import (
    PatientContext,
    PatientContextParser,
    AgeGroup,
    Severity,
    FunctionalStatus
)
from solver.clinical_reasoning_engine import (
    ClinicalReasoningEngine,
    RecommendationConfidence,
    TreatmentRecommendation
)

# 페이지 설정
st.set_page_config(
    page_title="Clinical Decision Support",
    page_icon="🏥",
    layout="wide"
)

# Sidebar styles
web_root = Path(__file__).parent.parent
sys.path.insert(0, str(web_root))
from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

# CSS 스타일
st.markdown("""
<style>
/* 전체 컨테이너 */
.main-container {
    max-width: 1400px;
    margin: 0 auto;
}

/* 헤더 스타일 */
.page-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
    color: white;
    padding: 2rem;
    border-radius: 12px;
    margin-bottom: 2rem;
    text-align: center;
}

.page-header h1 {
    margin: 0;
    font-size: 2rem;
    font-weight: 600;
}

.page-header p {
    margin: 0.5rem 0 0 0;
    opacity: 0.9;
    font-size: 1rem;
}

/* 카드 스타일 */
.info-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    margin-bottom: 1rem;
    border: 1px solid #e8ecf0;
}

.info-card h3 {
    color: #1e3a5f;
    font-size: 1.1rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e8ecf0;
}

/* 추천 카드 */
.recommendation-card {
    background: linear-gradient(135deg, #f8fffe 0%, #f0f9f7 100%);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-left: 4px solid #10b981;
}

.recommendation-card.top {
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border-left-color: #059669;
}

.recommendation-card.alternative {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    border-left-color: #f59e0b;
}

.recommendation-card.contraindicated {
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
    border-left-color: #ef4444;
}

/* 점수 배지 */
.score-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
}

.score-high {
    background: #dcfce7;
    color: #166534;
}

.score-moderate {
    background: #fef3c7;
    color: #92400e;
}

.score-low {
    background: #fee2e2;
    color: #991b1b;
}

/* 신뢰도 배지 */
.confidence-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    font-weight: 600;
}

.confidence-high {
    background: #dcfce7;
    color: #166534;
}

.confidence-moderate {
    background: #fef3c7;
    color: #92400e;
}

.confidence-low {
    background: #fee2e2;
    color: #991b1b;
}

.confidence-uncertain {
    background: #f3f4f6;
    color: #4b5563;
}

/* 경고 박스 */
.warning-box {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}

.warning-box .icon {
    color: #f59e0b;
}

/* 고려사항 박스 */
.consideration-box {
    background: #eff6ff;
    border: 1px solid #93c5fd;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}

/* 입력 섹션 */
.input-section {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

/* 메트릭 카드 */
.metric-row {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
}

.metric-card {
    flex: 1;
    min-width: 150px;
    background: white;
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
    border: 1px solid #e8ecf0;
}

.metric-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1e3a5f;
}

.metric-label {
    font-size: 0.85rem;
    color: #64748b;
    margin-top: 0.25rem;
}

/* 진행 바 */
.score-bar {
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
    margin-top: 0.5rem;
}

.score-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
}

.score-fill.green { background: #10b981; }
.score-fill.yellow { background: #f59e0b; }
.score-fill.red { background: #ef4444; }

/* 태그 스타일 */
.tag {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.75rem;
    margin-right: 0.25rem;
    margin-bottom: 0.25rem;
}

.tag-blue { background: #dbeafe; color: #1e40af; }
.tag-green { background: #dcfce7; color: #166534; }
.tag-yellow { background: #fef3c7; color: #92400e; }
.tag-red { background: #fee2e2; color: #991b1b; }
.tag-gray { background: #f3f4f6; color: #4b5563; }
</style>
""", unsafe_allow_html=True)


def render_header():
    """페이지 헤더 렌더링."""
    st.markdown("""
    <div class="page-header">
        <h1>🏥 Clinical Decision Support</h1>
        <p>환자 정보 기반 근거 중심 치료 추천 시스템</p>
    </div>
    """, unsafe_allow_html=True)


def render_patient_input() -> PatientContext:
    """환자 정보 입력 폼."""
    st.markdown("### 📋 환자 정보 입력")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="input-section">', unsafe_allow_html=True)
        st.markdown("#### 기본 정보")

        age = st.number_input(
            "나이",
            min_value=1,
            max_value=120,
            value=60,
            help="환자의 나이"
        )

        sex = st.selectbox(
            "성별",
            options=["선택 안함", "남성", "여성"],
            index=0
        )
        sex_value = None
        if sex == "남성":
            sex_value = "male"
        elif sex == "여성":
            sex_value = "female"

        pathology = st.selectbox(
            "진단명",
            options=[
                "선택해주세요",
                "Lumbar Stenosis",
                "Disc Herniation",
                "Spondylolisthesis",
                "Degenerative Disc Disease",
                "Scoliosis",
                "기타"
            ],
            index=0
        )
        if pathology == "선택해주세요":
            pathology = ""
        elif pathology == "기타":
            pathology = st.text_input("진단명 직접 입력")

        severity = st.select_slider(
            "중증도",
            options=["경증 (Mild)", "중등도 (Moderate)", "중증 (Severe)"],
            value="중등도 (Moderate)"
        )
        severity_map = {
            "경증 (Mild)": Severity.MILD,
            "중등도 (Moderate)": Severity.MODERATE,
            "중증 (Severe)": Severity.SEVERE
        }
        severity_value = severity_map.get(severity, Severity.MODERATE)

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="input-section">', unsafe_allow_html=True)
        st.markdown("#### 해부학적 위치")

        anatomy_options = st.multiselect(
            "수술 부위",
            options=["L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1",
                     "C3-C4", "C4-C5", "C5-C6", "C6-C7",
                     "T10-T11", "T11-T12", "T12-L1"],
            default=["L4-L5"]
        )

        st.markdown("#### 증상 기간")
        duration = st.number_input(
            "증상 기간 (개월)",
            min_value=0,
            max_value=240,
            value=6
        )

        st.markdown('</div>', unsafe_allow_html=True)

    # 동반질환 및 이전 치료
    st.markdown('<div class="input-section">', unsafe_allow_html=True)

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("#### 동반질환")
        comorbidities = st.multiselect(
            "동반질환 선택",
            options=[
                "Diabetes", "Hypertension", "Osteoporosis",
                "Smoking", "Obesity", "Cardiac Disease",
                "Renal Disease", "COPD", "Depression"
            ],
            default=[]
        )

    with col4:
        st.markdown("#### 이전 치료")
        prior_treatments = st.multiselect(
            "시행한 치료",
            options=[
                "Conservative Care", "Physical Therapy",
                "Pain Medication", "Epidural Injection",
                "Nerve Block", "Chiropractic",
                "Previous Surgery"
            ],
            default=["Conservative Care"]
        )

        failed_treatments = st.multiselect(
            "실패한 치료",
            options=prior_treatments if prior_treatments else ["Conservative Care"],
            default=[]
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # 증상
    st.markdown('<div class="input-section">', unsafe_allow_html=True)
    st.markdown("#### 주요 증상")

    col5, col6 = st.columns(2)

    with col5:
        symptoms = st.multiselect(
            "증상 선택",
            options=[
                "Back Pain", "Leg Pain", "Radiating Pain",
                "Numbness", "Weakness", "Claudication",
                "Bowel/Bladder Dysfunction"
            ],
            default=["Back Pain", "Leg Pain"]
        )

    with col6:
        functional_status = st.selectbox(
            "기능 상태",
            options=[
                "Independent (독립적)",
                "Ambulatory (보행가능)",
                "Limited (제한적)",
                "Wheelchair (휠체어)",
                "Bedridden (와상)"
            ],
            index=2
        )
        func_map = {
            "Independent (독립적)": FunctionalStatus.INDEPENDENT,
            "Ambulatory (보행가능)": FunctionalStatus.AMBULATORY,
            "Limited (제한적)": FunctionalStatus.LIMITED,
            "Wheelchair (휠체어)": FunctionalStatus.WHEELCHAIR,
            "Bedridden (와상)": FunctionalStatus.BEDRIDDEN
        }
        func_value = func_map.get(functional_status, FunctionalStatus.LIMITED)

    st.markdown('</div>', unsafe_allow_html=True)

    # 자연어 입력 (선택적)
    with st.expander("💬 자연어로 환자 정보 입력 (선택)", expanded=False):
        natural_input = st.text_area(
            "환자 정보를 자유롭게 입력하세요",
            placeholder="예: 65세 남자, L4-5 척추관협착증, 당뇨와 고혈압 있음, "
                       "6개월간 보존적 치료 실패, 간헐적 파행 있음",
            height=100
        )

        if natural_input and st.button("자연어에서 정보 추출"):
            parser = PatientContextParser()
            parsed = parser.parse(natural_input)
            st.success("정보가 추출되었습니다. 위 입력란에 반영해주세요.")
            st.json(parsed.to_dict())

    # PatientContext 생성
    patient = PatientContext(
        age=age,
        sex=sex_value,
        comorbidities=comorbidities,
        pathology=pathology,
        severity=severity_value,
        prior_treatments=prior_treatments,
        failed_treatments=failed_treatments,
        functional_status=func_value,
        symptoms=symptoms,
        duration_months=duration,
        anatomy_levels=anatomy_options
    )

    return patient


def render_patient_summary(patient: PatientContext):
    """환자 요약 렌더링."""
    st.markdown("### 📝 환자 요약")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("나이", f"{patient.age}세" if patient.age else "-")

    with col2:
        age_group = patient.get_age_group()
        age_group_kr = {
            AgeGroup.YOUNG_ADULT: "청년층 (<40)",
            AgeGroup.MIDDLE_AGED: "중년층 (40-59)",
            AgeGroup.ELDERLY: "노년층 (60-74)",
            AgeGroup.VERY_ELDERLY: "초고령 (75+)"
        }.get(age_group, "-")
        st.metric("나이 그룹", age_group_kr)

    with col3:
        st.metric("진단", patient.pathology or "-")

    with col4:
        severity_kr = {
            Severity.MILD: "경증",
            Severity.MODERATE: "중등도",
            Severity.SEVERE: "중증",
            Severity.UNKNOWN: "-"
        }.get(patient.severity, "-")
        st.metric("중증도", severity_kr)

    # 태그 표시
    tags_html = ""

    if patient.anatomy_levels:
        for level in patient.anatomy_levels:
            tags_html += f'<span class="tag tag-blue">{level}</span>'

    if patient.comorbidities:
        for comorb in patient.comorbidities:
            tags_html += f'<span class="tag tag-yellow">{comorb}</span>'

    if patient.symptoms:
        for symptom in patient.symptoms:
            tags_html += f'<span class="tag tag-gray">{symptom}</span>'

    if tags_html:
        st.markdown(f"<div style='margin: 1rem 0;'>{tags_html}</div>", unsafe_allow_html=True)


def render_recommendation(
    rec: TreatmentRecommendation,
    evidence: list[dict] = None
):
    """추천 결과 렌더링."""
    evidence = evidence or []

    st.markdown("---")
    st.markdown("## 🎯 치료 추천 결과")

    # 신뢰도 표시
    confidence_class = {
        RecommendationConfidence.HIGH: "confidence-high",
        RecommendationConfidence.MODERATE: "confidence-moderate",
        RecommendationConfidence.LOW: "confidence-low",
        RecommendationConfidence.UNCERTAIN: "confidence-uncertain"
    }.get(rec.confidence, "confidence-uncertain")

    confidence_icon = {
        RecommendationConfidence.HIGH: "✅",
        RecommendationConfidence.MODERATE: "⚠️",
        RecommendationConfidence.LOW: "❗",
        RecommendationConfidence.UNCERTAIN: "❓"
    }.get(rec.confidence, "❓")

    confidence_kr = {
        RecommendationConfidence.HIGH: "높음",
        RecommendationConfidence.MODERATE: "중간",
        RecommendationConfidence.LOW: "낮음",
        RecommendationConfidence.UNCERTAIN: "불확실"
    }.get(rec.confidence, "불확실")

    st.markdown(f"""
    <div class="confidence-badge {confidence_class}">
        <span>{confidence_icon}</span>
        <span>추천 신뢰도: {confidence_kr}</span>
    </div>
    """, unsafe_allow_html=True)

    # 신뢰도 이유
    if rec.confidence_reasons:
        with st.expander("신뢰도 평가 근거"):
            for reason in rec.confidence_reasons:
                st.markdown(f"- {reason}")

    # 메트릭
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("추천 수술법", len(rec.recommended_interventions))
    with col2:
        st.metric("대안 수술법", len(rec.alternative_interventions))
    with col3:
        st.metric("금기 수술법", len(rec.contraindicated_interventions))

    # 1차 추천
    if rec.recommended_interventions:
        st.markdown("### 🥇 추천 수술법")

        for i, intervention in enumerate(rec.recommended_interventions):
            is_top = i == 0

            with st.container():
                col1, col2 = st.columns([3, 1])

                with col1:
                    rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "•"
                    st.markdown(f"#### {rank_emoji} {intervention.intervention}")

                    if intervention.indication:
                        st.markdown(f"*적응증: {intervention.indication}*")

                    # 점수 breakdown
                    score_cols = st.columns(4)
                    with score_cols[0]:
                        st.metric("종합 점수", f"{intervention.total_score:.2f}")
                    with score_cols[1]:
                        st.metric("근거 점수", f"{intervention.evidence_score:.2f}")
                    with score_cols[2]:
                        st.metric("안전성 점수", f"{intervention.safety_score:.2f}")
                    with score_cols[3]:
                        st.metric("환자 적합도", f"{intervention.patient_fit_score:.2f}")

                with col2:
                    if intervention.is_first_line:
                        st.markdown('<span class="tag tag-green">1st Line</span>', unsafe_allow_html=True)
                    if intervention.evidence_level:
                        st.markdown(f'<span class="tag tag-blue">Level {intervention.evidence_level}</span>', unsafe_allow_html=True)

                # 점수 바
                score_pct = int(intervention.total_score * 100)
                color_class = "green" if score_pct >= 70 else "yellow" if score_pct >= 40 else "red"
                st.markdown(f"""
                <div class="score-bar">
                    <div class="score-fill {color_class}" style="width: {score_pct}%;"></div>
                </div>
                """, unsafe_allow_html=True)

                # 상대 금기
                relative_ci = intervention.get_relative_contraindications()
                if relative_ci:
                    with st.expander(f"⚠️ 고려사항 ({len(relative_ci)}개)"):
                        for ci in relative_ci:
                            st.warning(f"**{ci.condition}**\n\n{ci.mitigation or ci.reason}")

                # 위험 요소
                if intervention.risk_factors:
                    with st.expander(f"📊 위험 요소 ({len(intervention.risk_factors)}개)"):
                        for rf in intervention.risk_factors:
                            st.markdown(f"- **{rf.name}**: ×{rf.multiplier:.1f}")

                st.markdown("---")

    # 대안 수술법
    if rec.alternative_interventions:
        with st.expander(f"🔄 대안 수술법 ({len(rec.alternative_interventions)}개)"):
            for intervention in rec.alternative_interventions:
                st.markdown(f"""
                <div class="recommendation-card alternative">
                    <h4>{intervention.intervention}</h4>
                    <p>점수: {intervention.total_score:.2f}</p>
                </div>
                """, unsafe_allow_html=True)

                # 상대 금기 표시
                for ci in intervention.get_relative_contraindications():
                    st.warning(f"**{ci.condition}**: {ci.mitigation or ci.reason}")

    # 금기 수술법
    if rec.contraindicated_interventions:
        with st.expander(f"🚫 금기 수술법 ({len(rec.contraindicated_interventions)}개)", expanded=False):
            for intervention in rec.contraindicated_interventions:
                st.markdown(f"""
                <div class="recommendation-card contraindicated">
                    <h4>❌ {intervention.intervention}</h4>
                </div>
                """, unsafe_allow_html=True)

                for ci in intervention.get_absolute_contraindications():
                    st.error(f"**절대 금기**: {ci.condition}\n\n{ci.reason}")

    # 경고
    if rec.warnings:
        st.markdown("### ⚠️ 주의사항")
        for warning in rec.warnings:
            st.warning(warning)

    # 고려사항
    if rec.considerations:
        st.markdown("### 💡 임상적 고려사항")
        for consideration in rec.considerations:
            st.info(consideration)


def main():
    """메인 함수."""
    render_header()

    # 엔진 초기화
    engine = ClinicalReasoningEngine()

    # 환자 정보 입력
    patient = render_patient_input()

    # 환자 요약
    render_patient_summary(patient)

    # 추천 버튼
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_btn = st.button(
            "🔍 최적 치료법 분석",
            type="primary",
            use_container_width=True
        )

    if analyze_btn:
        if not patient.pathology:
            st.error("진단명을 선택해주세요.")
            return

        with st.spinner("치료법을 분석하고 있습니다..."):
            # TODO: 실제 근거 검색과 연동
            # 현재는 빈 근거로 추천
            available_evidence = []

            # 추천 생성
            recommendation = engine.recommend_treatment(
                patient=patient,
                available_evidence=available_evidence
            )

            # 결과 렌더링
            render_recommendation(recommendation, available_evidence)

    # 면책 조항
    st.markdown("---")
    st.markdown("""
    <div style="background: #f8fafc; padding: 1rem; border-radius: 8px; font-size: 0.85rem; color: #64748b;">
    <strong>⚠️ 면책 조항</strong><br>
    이 시스템은 의료 전문가의 임상적 판단을 보조하기 위한 도구입니다.
    최종 치료 결정은 반드시 담당 의료진의 종합적인 평가를 바탕으로 이루어져야 합니다.
    이 시스템의 추천 결과는 참고용으로만 사용하시기 바랍니다.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
