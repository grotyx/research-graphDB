"""Search Page - Simplified Hybrid Search Interface.

Streamlined search with automatic mode detection and optional advanced controls.
Integrates QueryPatternRouter for advanced query pattern recognition.
Features graph visualization of search results.
"""

from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Search - Spine GraphRAG", page_icon="🔍", layout="wide")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

from utils.server_bridge import get_server
from utils.chain_bridge import hybrid_search, ask_question
from utils.async_helpers import run_async

# Import vis-network visualization
try:
    from components.vis_network import vis_network_graph
    VIS_NETWORK_AVAILABLE = True
except ImportError:
    VIS_NETWORK_AVAILABLE = False

# Import QueryPatternRouter for advanced pattern classification
try:
    from orchestrator.query_pattern_router import (
        QueryPatternRouter,
        QueryPattern,
        ParsedQuery,
    )
    PATTERN_ROUTER_AVAILABLE = True
except ImportError:
    PATTERN_ROUTER_AVAILABLE = False
    QueryPatternRouter = None
    QueryPattern = None


# ═══════════════════════════════════════════════════════════════
# QUERY CLASSIFICATION (Enhanced with QueryPatternRouter)
# ═══════════════════════════════════════════════════════════════

def classify_query(query: str) -> dict:
    """Automatically classify query type and mode.

    Uses QueryPatternRouter for advanced pattern classification when available,
    falls back to simple keyword matching otherwise.

    Returns:
        dict with 'mode' (qa|evidence|conflict), 'search_type' (hybrid|graph|vector),
        'pattern' (QueryPattern), 'parsed_query' (ParsedQuery), and additional metadata
    """
    query_lower = query.lower().strip()

    # Default settings
    result = {
        "mode": "evidence",
        "search_type": "hybrid",
        "reason": "",
        "pattern": None,
        "parsed_query": None,
        "pattern_confidence": 0.0,
        "extracted_entities": {},
    }

    # Use QueryPatternRouter if available
    if PATTERN_ROUTER_AVAILABLE and QueryPatternRouter:
        router = QueryPatternRouter()
        parsed = router.parse_query(query)

        result["pattern"] = parsed.pattern
        result["parsed_query"] = parsed
        result["pattern_confidence"] = parsed.confidence
        result["extracted_entities"] = {
            "interventions": parsed.interventions,
            "pathologies": parsed.pathologies,
            "outcomes": parsed.outcomes,
        }

        # Map QueryPattern to search mode
        if parsed.pattern == QueryPattern.TREATMENT_COMPARISON:
            result["mode"] = "conflict"
            result["reason"] = f"🔀 치료 비교 패턴 ({parsed.confidence:.0%} 신뢰도)"
            result["graph_weight"] = 0.7
            if parsed.comparison_pair:
                result["comparison_pair"] = parsed.comparison_pair

        elif parsed.pattern == QueryPattern.PATIENT_SPECIFIC:
            result["mode"] = "qa"
            result["reason"] = f"👤 환자 특성 패턴 ({parsed.confidence:.0%} 신뢰도)"
            if parsed.age_group:
                result["age_info"] = {
                    "age_group": parsed.age_group,
                    "min_age": parsed.min_age,
                    "max_age": parsed.max_age,
                }

        elif parsed.pattern == QueryPattern.INDICATION_QUERY:
            result["mode"] = "qa"
            result["reason"] = f"📋 적응증 질의 패턴 ({parsed.confidence:.0%} 신뢰도)"
            result["graph_weight"] = 0.8

        elif parsed.pattern == QueryPattern.OUTCOME_RATE:
            result["mode"] = "evidence"
            result["reason"] = f"📊 결과 발생률 패턴 ({parsed.confidence:.0%} 신뢰도)"
            result["graph_weight"] = 0.8

        elif parsed.pattern == QueryPattern.EVIDENCE_FILTER:
            result["mode"] = "evidence"
            result["reason"] = f"🔬 근거 수준 필터 패턴 ({parsed.confidence:.0%} 신뢰도)"
            result["evidence_levels"] = parsed.evidence_levels

        else:  # GENERAL
            result["reason"] = "📝 일반 질의 패턴"

    # Fallback: Simple keyword-based classification
    else:
        # Question indicators → QA mode
        question_words = ["what", "why", "how", "which", "when", "is", "are", "does", "do", "can", "should"]
        korean_question = any(q in query for q in ["?", "인가", "일까", "할까", "어떤", "무엇", "어떻게", "왜"])

        if any(query_lower.startswith(w) for w in question_words) or "?" in query or korean_question:
            result["mode"] = "qa"
            result["reason"] = "질문 형식 감지됨 → AI 답변 생성"

        # Conflict indicators
        conflict_words = ["vs", "versus", "compare", "comparison", "비교", "차이", "better", "conflict", "contradict"]
        if any(word in query_lower for word in conflict_words):
            result["mode"] = "conflict"
            result["reason"] = "비교/충돌 분석 요청 감지됨"

    # Additional weight adjustments based on keywords
    # Graph-preferred queries (statistical/quantitative)
    graph_words = ["p-value", "p value", "significant", "유의", "효과", "effect", "rate", "비율", "statistic"]
    if any(word in query_lower for word in graph_words):
        result["search_type"] = "hybrid"
        result["graph_weight"] = result.get("graph_weight", 0.6) + 0.1
        if not result["reason"]:
            result["reason"] = "통계 데이터 우선"

    # Vector-preferred queries (context/background)
    vector_words = ["background", "mechanism", "기전", "설명"]
    if any(word in query_lower for word in vector_words):
        result["search_type"] = "hybrid"
        result["vector_weight"] = result.get("vector_weight", 0.4) + 0.1
        if not result["reason"]:
            result["reason"] = "맥락 정보 우선"

    return result


# ═══════════════════════════════════════════════════════════════
# RESULT RENDERING
# ═══════════════════════════════════════════════════════════════

def build_search_result_graph(sources: list) -> tuple[list, list]:
    """Build graph data from search results for visualization.

    Args:
        sources: List of search result objects

    Returns:
        Tuple of (nodes, edges) for vis_network_graph
    """
    nodes = []
    edges = []
    node_ids = set()

    # Central query node
    nodes.append({
        "id": "query",
        "label": "Query",
        "group": "Query",
        "title": "Your search query"
    })
    node_ids.add("query")

    for i, source in enumerate(sources):
        result_type = source.result_type
        metadata = source.metadata
        score = source.score

        if result_type == "graph":
            # Graph evidence: Intervention → Outcome
            intervention = metadata.get("intervention", "")
            outcome = metadata.get("outcome", "")

            if intervention and intervention not in node_ids:
                nodes.append({
                    "id": intervention,
                    "label": intervention,
                    "group": "Intervention",
                    "title": f"Intervention: {intervention}\nCategory: {metadata.get('category', 'N/A')}"
                })
                node_ids.add(intervention)

            if outcome and outcome not in node_ids:
                nodes.append({
                    "id": outcome,
                    "label": outcome,
                    "group": "Outcome",
                    "title": f"Outcome: {outcome}\np-value: {metadata.get('p_value', 'N/A')}"
                })
                node_ids.add(outcome)

            if intervention and outcome:
                edges.append({
                    "from": intervention,
                    "to": outcome,
                    "label": metadata.get("direction", ""),
                    "direction": metadata.get("direction", "unchanged"),
                    "is_significant": metadata.get("is_significant", False)
                })

            # Connect to query
            if intervention:
                edges.append({
                    "from": "query",
                    "to": intervention,
                    "label": f"score: {score:.2f}"
                })

        else:
            # Vector evidence: Paper/Document
            paper_id = metadata.get("paper_id", f"doc_{i}")
            title = metadata.get("title", "Document")[:30]

            if paper_id not in node_ids:
                nodes.append({
                    "id": paper_id,
                    "label": title,
                    "group": "Paper",
                    "title": f"Paper: {metadata.get('title', 'Unknown')}\nYear: {metadata.get('year', 'N/A')}\nEvidence: {metadata.get('evidence_level', 'N/A')}"
                })
                node_ids.add(paper_id)

                # Connect to query
                edges.append({
                    "from": "query",
                    "to": paper_id,
                    "label": f"score: {score:.2f}"
                })

    return nodes, edges


def render_result_card(result, index: int):
    """Render a search result as a card."""
    result_type = result.result_type
    score = result.score
    metadata = result.metadata

    # Type indicator
    type_info = {
        "graph": ("📊", "Graph Evidence", "#4CAF50"),
        "vector": ("📄", "Vector Context", "#2196F3")
    }
    icon, label, color = type_info.get(result_type, ("📋", "Result", "#9E9E9E"))

    # Score color
    score_color = "🟢" if score > 0.7 else "🟡" if score > 0.4 else "🔴"

    # Card
    with st.container():
        # Header row
        header_cols = st.columns([0.5, 4, 1])

        with header_cols[0]:
            st.markdown(f"**{index}.**")

        with header_cols[1]:
            citation = result.get_citation()
            title = citation if citation else metadata.get("title", "Unknown Source")
            st.markdown(f"**{title[:80]}{'...' if len(title) > 80 else ''}**")

        with header_cols[2]:
            st.markdown(f"{score_color} **{score:.2f}**")

        # Metadata badges
        badge_cols = st.columns(6)

        with badge_cols[0]:
            st.caption(f"{icon} {label}")

        with badge_cols[1]:
            if result_type == "graph" and "intervention" in metadata:
                st.caption(f"🔧 {metadata['intervention']}")
            elif "section" in metadata:
                st.caption(f"📑 {metadata['section']}")

        with badge_cols[2]:
            if result_type == "graph" and "outcome" in metadata:
                st.caption(f"🎯 {metadata['outcome']}")
            elif "tier" in metadata:
                tier_emoji = "🥇" if metadata["tier"] == "tier1" else "🥈"
                st.caption(f"{tier_emoji} {metadata['tier']}")

        with badge_cols[3]:
            if "p_value" in metadata and metadata["p_value"] is not None:
                p_val = metadata["p_value"]
                sig = "✅" if p_val < 0.05 else ""
                st.caption(f"p={p_val:.3f} {sig}")

        with badge_cols[4]:
            if "evidence_level" in metadata:
                st.caption(f"⭐ Lv.{metadata['evidence_level']}")

        with badge_cols[5]:
            if metadata.get("is_key_finding"):
                st.caption("🔑 Key")
            elif metadata.get("has_statistics"):
                st.caption("📈 Stats")

        # Expandable content
        evidence_text = result.get_evidence_text()
        if evidence_text:
            with st.expander("📖 View Evidence"):
                st.markdown(evidence_text[:800] + "..." if len(evidence_text) > 800 else evidence_text)

        st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════════════════

def main():
    st.title("🔍 Search")
    st.markdown("**척추 수술 근거 검색** - 질문을 입력하면 자동으로 최적의 검색 방식을 선택합니다")

    bridge = get_server()

    # Initialize session state
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""
    if "advanced_mode" not in st.session_state:
        st.session_state.advanced_mode = False

    # ═══════════════════════════════════════════════════════════
    # SIMPLE SEARCH (Default)
    # ═══════════════════════════════════════════════════════════

    # Search box
    query = st.text_input(
        "검색어를 입력하세요",
        placeholder="예: TLIF fusion rate는? | UBE vs 기존 수술 비교 | 요추 협착증 치료법",
        value=st.session_state.search_query,
        label_visibility="collapsed"
    )

    # Example query buttons
    st.markdown("**💡 예시 검색:**")
    example_cols = st.columns(4)

    examples = [
        ("TLIF 융합률", "TLIF fusion rate는 어느 정도인가?"),
        ("UBE vs 기존수술", "UBE와 기존 laminectomy의 합병증 비교"),
        ("요추 협착증", "요추 협착증에 가장 효과적인 수술법은?"),
        ("ODI 개선", "수술 후 ODI 개선 효과")
    ]

    for i, (label, example_query) in enumerate(examples):
        with example_cols[i]:
            if st.button(f"💡 {label}", key=f"ex_{i}"):
                st.session_state.search_query = example_query
                query = example_query

    # ═══════════════════════════════════════════════════════════
    # ADVANCED OPTIONS (Collapsible)
    # ═══════════════════════════════════════════════════════════

    # Default values (used when expander is collapsed)
    search_mode_override = "🤖 자동 감지"
    search_type_override = "⚡ Hybrid (추천)"
    top_k = 10
    graph_weight = 0.6
    vector_weight = 0.4
    tier_strategy = "tier1_first"

    with st.expander("⚙️ **고급 설정** (선택사항)", expanded=st.session_state.advanced_mode):
        st.session_state.advanced_mode = True

        adv_col1, adv_col2 = st.columns(2)

        with adv_col1:
            st.markdown("**검색 모드**")
            search_mode_override = st.radio(
                "Search Mode",
                ["🤖 자동 감지", "📝 QA (AI 답변)", "📊 Evidence (근거만)", "⚔️ Conflict (상충 분석)"],
                horizontal=True,
                label_visibility="collapsed"
            )

            st.markdown("**검색 유형**")
            search_type_override = st.radio(
                "Search Type",
                ["⚡ Hybrid (추천)", "📊 Graph Only", "📄 Vector Only"],
                horizontal=True,
                label_visibility="collapsed"
            )

        with adv_col2:
            st.markdown("**상세 설정**")
            settings_cols = st.columns(3)

            with settings_cols[0]:
                top_k = st.number_input("결과 수", 1, 20, 10)

            with settings_cols[1]:
                graph_weight = st.slider("Graph 가중치", 0.0, 1.0, 0.6, 0.1)

            with settings_cols[2]:
                vector_weight = st.slider("Vector 가중치", 0.0, 1.0, 0.4, 0.1)

            # Tier strategy
            tier_strategy = st.selectbox(
                "Tier 전략",
                ["tier1_first", "tier1_only", "all_tiers"],
                format_func=lambda x: {
                    "tier1_first": "🥇 Tier1 우선 (Key Findings 먼저)",
                    "tier1_only": "🥇 Tier1만 (빠른 검색)",
                    "all_tiers": "🔄 전체 Tier (포괄적)"
                }[x]
            )

    # Search button
    btn_cols = st.columns([1, 1, 4])

    with btn_cols[0]:
        search_clicked = st.button("🔍 검색", type="primary")

    with btn_cols[1]:
        if st.button("🔄 초기화"):
            st.session_state.search_query = ""
            st.rerun()

    st.divider()

    # ═══════════════════════════════════════════════════════════
    # SEARCH EXECUTION
    # ═══════════════════════════════════════════════════════════

    if search_clicked and query:
        # Auto-classify query
        classification = classify_query(query)

        # Apply overrides from advanced settings
        if "자동" not in search_mode_override:
            if "QA" in search_mode_override:
                classification["mode"] = "qa"
            elif "Evidence" in search_mode_override:
                classification["mode"] = "evidence"
            elif "Conflict" in search_mode_override:
                classification["mode"] = "conflict"

        if "Hybrid" in search_type_override:
            classification["search_type"] = "hybrid"
        elif "Graph" in search_type_override:
            classification["search_type"] = "graph_only"
        elif "Vector" in search_type_override:
            classification["search_type"] = "vector_only"

        # Show classification info
        mode_labels = {
            "qa": "🤖 AI 답변 생성",
            "evidence": "📊 근거 검색",
            "conflict": "⚔️ 상충 분석"
        }
        type_labels = {
            "hybrid": "⚡ Hybrid",
            "graph_only": "📊 Graph Only",
            "vector_only": "📄 Vector Only"
        }

        info_text = f"**모드:** {mode_labels[classification['mode']]} | **유형:** {type_labels[classification['search_type']]}"
        if classification.get("reason"):
            info_text += f" | *{classification['reason']}*"

        st.info(info_text)

        # Show extracted entities if QueryPatternRouter was used
        extracted = classification.get("extracted_entities", {})
        if any(extracted.get(k) for k in ["interventions", "pathologies", "outcomes"]):
            with st.expander("🔎 추출된 엔티티", expanded=False):
                entity_cols = st.columns(3)
                with entity_cols[0]:
                    if extracted.get("interventions"):
                        st.markdown("**🔧 수술법**")
                        for intervention in extracted["interventions"]:
                            st.markdown(f"- `{intervention}`")
                with entity_cols[1]:
                    if extracted.get("pathologies"):
                        st.markdown("**🦴 질환**")
                        for pathology in extracted["pathologies"]:
                            st.markdown(f"- `{pathology}`")
                with entity_cols[2]:
                    if extracted.get("outcomes"):
                        st.markdown("**📈 결과변수**")
                        for outcome in extracted["outcomes"]:
                            st.markdown(f"- `{outcome}`")

                # Show additional pattern-specific info
                if classification.get("comparison_pair"):
                    st.markdown(f"**⚖️ 비교 대상:** `{classification['comparison_pair'][0]}` vs `{classification['comparison_pair'][1]}`")
                if classification.get("age_info"):
                    age_info = classification["age_info"]
                    st.markdown(f"**👤 연령군:** {age_info.get('age_group', '')} (min: {age_info.get('min_age')}, max: {age_info.get('max_age')})")
                if classification.get("evidence_levels"):
                    st.markdown(f"**📚 근거 수준 필터:** {', '.join(classification['evidence_levels'])}")

        # Execute search based on mode
        mode = classification["mode"]
        search_type = classification["search_type"]

        if mode == "qa":
            # QA Mode - Generate AI answer
            with st.spinner("🤖 AI 답변 생성 중..."):
                result = run_async(ask_question(
                    query=query,
                    mode="qa",
                    top_k=top_k,
                    graph_weight=graph_weight,
                    vector_weight=vector_weight,
                ))

            if result.get("success"):
                # Answer section
                st.markdown("### 💡 답변")
                answer_container = st.container()
                with answer_container:
                    st.markdown(result.get("answer", "답변을 생성할 수 없습니다."))

                st.divider()

                # Sources
                sources = result.get("sources", [])
                if sources:
                    st.markdown(f"### 📚 근거 자료 ({len(sources)}건)")

                    # Summary metrics
                    graph_count = sum(1 for s in sources if s.result_type == "graph")
                    vector_count = len(sources) - graph_count

                    metric_cols = st.columns(3)
                    with metric_cols[0]:
                        st.metric("📊 Graph 근거", graph_count)
                    with metric_cols[1]:
                        st.metric("📄 Vector 맥락", vector_count)
                    with metric_cols[2]:
                        avg_score = sum(s.score for s in sources) / len(sources) if sources else 0
                        st.metric("평균 점수", f"{avg_score:.2f}")

                    st.divider()

                    # Tabs for list vs graph view
                    view_tab1, view_tab2 = st.tabs(["📋 List View", "🌐 Graph View"])

                    with view_tab1:
                        for i, source in enumerate(sources, 1):
                            render_result_card(source, i)

                    with view_tab2:
                        if VIS_NETWORK_AVAILABLE:
                            graph_nodes, graph_edges = build_search_result_graph(sources)
                            if len(graph_nodes) > 1:
                                st.info(f"🌐 Visualizing {len(graph_nodes)} nodes and {len(graph_edges)} relationships")
                                vis_network_graph(
                                    nodes=graph_nodes,
                                    edges=graph_edges,
                                    height=500,
                                    highlight_nodes=["query"],
                                    physics_enabled=True
                                )
                            else:
                                st.info("그래프로 표시할 데이터가 부족합니다.")
                        else:
                            st.warning("그래프 시각화 컴포넌트를 사용할 수 없습니다.")
                else:
                    st.warning("관련 근거를 찾을 수 없습니다.")

            else:
                st.error(f"검색 실패: {result.get('error', '알 수 없는 오류')}")

        elif mode == "conflict":
            # Conflict Analysis Mode
            with st.spinner("⚔️ 상충 분석 중..."):
                result = run_async(ask_question(
                    query=query,
                    mode="conflict",
                    top_k=top_k,
                    graph_weight=graph_weight,
                    vector_weight=vector_weight,
                ))

            if result.get("success"):
                st.markdown("### ⚔️ 상충 분석 결과")
                st.markdown(result.get("answer", "분석 결과를 생성할 수 없습니다."))

                st.divider()

                sources = result.get("sources", [])
                if sources:
                    st.markdown(f"### 📚 관련 근거 ({len(sources)}건)")
                    for i, source in enumerate(sources, 1):
                        render_result_card(source, i)
                else:
                    st.success("✅ 상충되는 근거가 발견되지 않았습니다.")

            else:
                st.error(f"분석 실패: {result.get('error', '알 수 없는 오류')}")

        else:
            # Evidence Retrieval Mode (No LLM)
            with st.spinner("📊 근거 검색 중..."):
                result = run_async(hybrid_search(
                    query=query,
                    search_type=search_type,
                    top_k=top_k,
                    graph_weight=graph_weight,
                    vector_weight=vector_weight,
                ))

            if result.get("success"):
                sources = result.get("sources", [])

                # Summary metrics
                if sources:
                    graph_count = sum(1 for s in sources if s.result_type == "graph")
                    vector_count = len(sources) - graph_count

                    metric_cols = st.columns(4)
                    with metric_cols[0]:
                        st.metric("📊 Graph 근거", graph_count)
                    with metric_cols[1]:
                        st.metric("📄 Vector 맥락", vector_count)
                    with metric_cols[2]:
                        st.metric("📚 총 결과", len(sources))
                    with metric_cols[3]:
                        avg_score = sum(s.score for s in sources) / len(sources)
                        st.metric("평균 점수", f"{avg_score:.2f}")

                    st.divider()

                    # Results with tabs
                    st.markdown("### 📋 검색 결과")

                    result_tab1, result_tab2 = st.tabs(["📋 List View", "🌐 Graph View"])

                    with result_tab1:
                        for i, source in enumerate(sources, 1):
                            render_result_card(source, i)

                    with result_tab2:
                        if VIS_NETWORK_AVAILABLE:
                            graph_nodes, graph_edges = build_search_result_graph(sources)
                            if len(graph_nodes) > 1:
                                st.info(f"🌐 Visualizing {len(graph_nodes)} nodes and {len(graph_edges)} relationships")
                                vis_network_graph(
                                    nodes=graph_nodes,
                                    edges=graph_edges,
                                    height=500,
                                    highlight_nodes=["query"],
                                    physics_enabled=True
                                )
                            else:
                                st.info("그래프로 표시할 데이터가 부족합니다.")
                        else:
                            st.warning("그래프 시각화 컴포넌트를 사용할 수 없습니다.")

                else:
                    st.warning("검색 결과가 없습니다. 다른 검색어를 시도해 보세요.")

                # Metadata (collapsed)
                metadata = result.get("metadata", {})
                if metadata:
                    with st.expander("📊 검색 메타데이터"):
                        st.json(metadata)

            else:
                st.error(f"검색 실패: {result.get('error', '알 수 없는 오류')}")

    # ═══════════════════════════════════════════════════════════
    # SIDEBAR HELP
    # ═══════════════════════════════════════════════════════════

    with st.sidebar:
        st.subheader("💡 검색 가이드")

        # Show QueryPatternRouter status
        if PATTERN_ROUTER_AVAILABLE:
            st.success("✅ QueryPatternRouter 활성화됨")
        else:
            st.warning("⚠️ 기본 분류 모드 (QueryPatternRouter 미설치)")

        st.markdown("""
        ### 🎯 쿼리 패턴 자동 감지

        6가지 패턴을 자동으로 인식하여 최적 검색:

        | 패턴 | 예시 |
        |------|------|
        | 🔀 치료 비교 | "UBE vs TLIF 비교" |
        | 👤 환자 특성 | "고령 환자 합병증" |
        | 📋 적응증 | "TLIF의 적응증은?" |
        | 📊 발생률 | "subsidence 발생률" |
        | 🔬 근거 필터 | "UBE에 대한 RCT" |
        | 📝 일반 | 기타 질의 |

        ---

        ### 📊 Graph vs Vector

        **📊 Graph Evidence:**
        - 구조화된 통계 데이터
        - p-value, effect size
        - Intervention → Outcome 관계

        **📄 Vector Context:**
        - 시맨틱 유사도 검색
        - 배경 설명, 맥락 정보
        - 더 넓은 범위 탐색

        ---

        ### ⭐ 근거 수준 (OCEBM)

        | 레벨 | 의미 |
        |------|------|
        | 1a | 메타분석 |
        | 1b | RCT |
        | 2a | 코호트 연구 |
        | 2b | 환자-대조군 |
        | 3 | 증례 연구 |
        | 4 | 전문가 의견 |

        ---

        ### 💡 검색 팁

        1. **치료 비교**: "A vs B for 질환" 형식
        2. **연령 제한**: ">70세", "고령", "elderly" 사용
        3. **근거 필터**: "RCT", "meta-analysis" 추가
        4. 한국어/영어 모두 지원
        5. 수술법, 질환, 결과변수 자동 추출
        """)


if __name__ == "__main__":
    main()
