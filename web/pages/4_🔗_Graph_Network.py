"""Graph Network Page - Neo4j Knowledge Graph Visualization.

Redesigned with improved readability and modern styling.
"""

import sys
from pathlib import Path
from collections import defaultdict

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import pandas as pd

# 프로젝트 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.server_bridge import get_server
from utils.graph_utils import get_neo4j_client, get_paper_network, create_network_graph

# numpy import
try:
    import numpy as np
except ImportError:
    import math
    class np:
        @staticmethod
        def cos(x):
            return math.cos(x)
        @staticmethod
        def sin(x):
            return math.sin(x)

# 페이지 설정
st.set_page_config(
    page_title="Graph Network - Spine GraphRAG",
    page_icon="🔗",
    layout="wide"
)

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

# ═══════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* 전체 스타일 */
.main .block-container {
    max-width: 1600px;
    padding: 1.5rem 2rem;
}

/* 페이지 헤더 */
.graph-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
    color: white;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.graph-header h1 {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
}

.graph-header p {
    margin: 0.5rem 0 0 0;
    opacity: 0.9;
    font-size: 1rem;
}

/* 컨트롤 패널 */
.control-panel {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
}

.control-panel h4 {
    color: #1e3a5f;
    font-size: 1rem;
    margin: 0 0 0.75rem 0;
    font-weight: 600;
}

/* 통계 카드 */
.stat-card {
    background: white;
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.04);
}

.stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #1e3a5f;
}

.stat-label {
    font-size: 0.85rem;
    color: #64748b;
    margin-top: 0.25rem;
}

/* 범례 */
.legend-container {
    background: white;
    border-radius: 12px;
    padding: 1rem 1.5rem;
    border: 1px solid #e2e8f0;
    margin-bottom: 1rem;
}

.legend-title {
    font-weight: 600;
    color: #1e3a5f;
    margin-bottom: 0.75rem;
    font-size: 0.95rem;
}

.legend-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: #475569;
}

.legend-color {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    flex-shrink: 0;
}

.legend-color.circle { border-radius: 50%; }
.legend-color.square { border-radius: 3px; }

/* 노드 범례 색상 */
.node-intervention { background: #3b82f6; }
.node-outcome { background: #f97316; }
.node-paper { background: #22c55e; }

/* 엣지 범례 색상 */
.edge-improved { background: #22c55e; }
.edge-worsened { background: #ef4444; }
.edge-unchanged { background: #94a3b8; }

/* 그래프 컨테이너 */
.graph-container {
    background: white;
    border-radius: 16px;
    padding: 1rem;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

/* 탭 스타일 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: #f1f5f9;
    padding: 4px;
    border-radius: 12px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 0.5rem 1.25rem;
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    background: white;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

/* 상태 표시 */
.status-connected {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #dcfce7;
    color: #166534;
    padding: 0.4rem 1rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
}

.status-dot {
    width: 8px;
    height: 8px;
    background: #22c55e;
    border-radius: 50%;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* 필터 라벨 */
.filter-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# LAYOUT ALGORITHMS
# ═══════════════════════════════════════════════════════════════

def cluster_layout(G: nx.Graph, cluster_key: str = "category") -> dict:
    """카테고리별 클러스터 레이아웃."""
    clusters = defaultdict(list)
    for node, data in G.nodes(data=True):
        cluster = data.get(cluster_key, "Other")
        clusters[cluster].append(node)

    num_clusters = len(clusters)
    cluster_radius = 4.0
    cluster_centers = {}

    for i, cluster_name in enumerate(clusters.keys()):
        angle = 2 * 3.14159 * i / max(num_clusters, 1)
        cluster_centers[cluster_name] = (
            cluster_radius * np.cos(angle),
            cluster_radius * np.sin(angle)
        )

    pos = {}
    for cluster_name, nodes in clusters.items():
        cx, cy = cluster_centers[cluster_name]
        n = len(nodes)

        if n == 1:
            pos[nodes[0]] = (cx, cy)
        else:
            inner_radius = 0.6 + 0.12 * n
            for j, node in enumerate(nodes):
                angle = 2 * 3.14159 * j / n
                pos[node] = (
                    cx + inner_radius * np.cos(angle),
                    cy + inner_radius * np.sin(angle)
                )

    return pos


def hierarchical_layout(G: nx.DiGraph) -> dict:
    """계층적 레이아웃."""
    roots = [n for n in G.nodes() if G.in_degree(n) == 0]

    if not roots:
        return nx.spring_layout(G, k=2.0, iterations=50, seed=42)

    layers = defaultdict(list)
    visited = set()
    queue = [(r, 0) for r in roots]

    while queue:
        node, depth = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        layers[depth].append(node)

        for neighbor in G.successors(node):
            if neighbor not in visited:
                queue.append((neighbor, depth + 1))

    max_layer = max(layers.keys()) if layers else 0
    for node in G.nodes():
        if node not in visited:
            layers[max_layer + 1].append(node)

    pos = {}
    max_width = max(len(layer) for layer in layers.values()) if layers else 1

    for depth, nodes in layers.items():
        n = len(nodes)
        for i, node in enumerate(nodes):
            x = (i - (n - 1) / 2) * (2.5 / max_width)
            y = -depth * 2.0
            pos[node] = (x, y)

    return pos


# ═══════════════════════════════════════════════════════════════
# GRAPH BUILDING
# ═══════════════════════════════════════════════════════════════

def build_graph(
    neo4j_client,
    intervention: str = None,
    outcome: str = None,
    category: str = None,
    pathology: str = None,
    sig_only: bool = False,
    limit: int = 100
) -> nx.DiGraph:
    """Neo4j에서 그래프 데이터 로드."""

    where_conditions = []
    params = {}

    if intervention:
        where_conditions.append("i.name = $intervention")
        params["intervention"] = intervention
    if outcome:
        where_conditions.append("o.name = $outcome")
        params["outcome"] = outcome
    if category:
        where_conditions.append("i.category = $category")
        params["category"] = category
    if sig_only:
        where_conditions.append("r.is_significant = true")

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    if pathology:
        cypher = f"""
        MATCH (p:Paper)-[:STUDIES]->(path:Pathology {{name: $pathology}})
        MATCH (p)-[:INVESTIGATES]->(i:Intervention)-[r:AFFECTS]->(o:Outcome)
        {where_clause}
        WITH i, o, r, count(DISTINCT p) AS paper_count
        RETURN i.name AS intervention, i.category AS category,
               o.name AS outcome, o.type AS outcome_type,
               r.direction AS direction, r.p_value AS p_value,
               r.is_significant AS is_significant, r.effect_size AS effect_size,
               paper_count
        LIMIT $limit
        """
        params["pathology"] = pathology
    else:
        cypher = f"""
        MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
        {where_clause}
        OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
        WITH i, o, r, count(DISTINCT p) AS paper_count
        RETURN i.name AS intervention, i.category AS category,
               o.name AS outcome, o.type AS outcome_type,
               r.direction AS direction, r.p_value AS p_value,
               r.is_significant AS is_significant, r.effect_size AS effect_size,
               paper_count
        LIMIT $limit
        """

    params["limit"] = limit
    records = neo4j_client.run_query(cypher, params)

    G = nx.DiGraph()

    for record in records:
        i_name = record["intervention"]
        o_name = record["outcome"]
        i_category = record["category"] or "Other"
        o_type = record["outcome_type"] or "Other"
        direction = record["direction"] or "unchanged"
        p_value = record["p_value"]
        is_sig = record["is_significant"] or False
        effect_size = record["effect_size"]
        paper_count = record["paper_count"] or 0

        if not G.has_node(i_name):
            G.add_node(
                i_name,
                node_type="intervention",
                category=i_category,
                paper_count=paper_count
            )
        else:
            curr = G.nodes[i_name].get("paper_count", 0)
            G.nodes[i_name]["paper_count"] = max(curr, paper_count)

        if not G.has_node(o_name):
            G.add_node(
                o_name,
                node_type="outcome",
                category=o_type
            )

        G.add_edge(
            i_name,
            o_name,
            direction=direction,
            p_value=p_value,
            is_significant=is_sig,
            effect_size=effect_size,
            paper_count=paper_count
        )

    return G


# ═══════════════════════════════════════════════════════════════
# VISUALIZATION
# ═══════════════════════════════════════════════════════════════

def create_visualization(
    G: nx.DiGraph,
    layout_type: str = "spring",
    color_by: str = "type"
) -> go.Figure:
    """개선된 Plotly 그래프 시각화."""

    if not G.nodes():
        return None

    # 레이아웃 선택
    if layout_type == "cluster":
        pos = cluster_layout(G, cluster_key="category")
    elif layout_type == "hierarchical":
        pos = hierarchical_layout(G)
    else:
        pos = nx.spring_layout(G, k=2.5, iterations=100, seed=42)

    # ─────────────────────────────────────────────────────────────
    # 엣지 트레이스
    # ─────────────────────────────────────────────────────────────
    edge_traces = []

    # 색상 설정 (더 선명하게)
    direction_colors = {
        "improved": "#10b981",  # 밝은 초록
        "worsened": "#ef4444",  # 밝은 빨강
        "unchanged": "#94a3b8", # 회색
    }

    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]

        direction = data.get("direction", "unchanged")
        color = direction_colors.get(direction, "#94a3b8")
        is_sig = data.get("is_significant", False)
        width = 4 if is_sig else 2
        dash = None if is_sig else "dot"

        # Hover 텍스트
        hover_parts = [f"<b>{u}</b> → <b>{v}</b>"]
        hover_parts.append(f"Direction: {direction.capitalize()}")

        if data.get("p_value") is not None:
            try:
                p_val = float(data["p_value"])
                hover_parts.append(f"p-value: {p_val:.4f}")
            except (ValueError, TypeError):
                pass

        if data.get("effect_size") is not None:
            try:
                effect = float(data["effect_size"])
                hover_parts.append(f"Effect size: {effect:.2f}")
            except (ValueError, TypeError):
                pass

        if is_sig:
            hover_parts.append("<b>✓ Statistically Significant</b>")

        hover = "<br>".join(hover_parts)

        edge_traces.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(width=width, color=color, dash=dash),
            hovertext=hover,
            hoverinfo='text',
            showlegend=False
        ))

    # ─────────────────────────────────────────────────────────────
    # 노드 분류
    # ─────────────────────────────────────────────────────────────
    intervention_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("node_type") == "intervention"]
    outcome_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("node_type") == "outcome"]

    node_traces = []

    # Intervention 노드
    if intervention_nodes:
        x_vals = [pos[n][0] for n, d in intervention_nodes]
        y_vals = [pos[n][1] for n, d in intervention_nodes]
        sizes = [28 + min(d.get("paper_count", 0) * 2, 30) for n, d in intervention_nodes]
        texts = [n for n, d in intervention_nodes]

        hovers = []
        for n, d in intervention_nodes:
            hover_parts = [
                f"<b>{n}</b>",
                f"Category: {d.get('category', 'N/A')}",
                f"Papers: {d.get('paper_count', 0)}"
            ]
            hovers.append("<br>".join(hover_parts))

        node_traces.append(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='markers+text',
            name='Intervention',
            text=texts,
            textposition="top center",
            textfont=dict(size=11, color="#1e3a5f", family="Inter, sans-serif"),
            hovertext=hovers,
            hoverinfo='text',
            marker=dict(
                size=sizes,
                color='#3b82f6',
                line=dict(width=3, color='white'),
                symbol='square',
                opacity=0.95
            )
        ))

    # Outcome 노드
    if outcome_nodes:
        x_vals = [pos[n][0] for n, d in outcome_nodes]
        y_vals = [pos[n][1] for n, d in outcome_nodes]
        texts = [n for n, d in outcome_nodes]

        hovers = []
        for n, d in outcome_nodes:
            hover_parts = [
                f"<b>{n}</b>",
                f"Type: {d.get('category', 'N/A')}"
            ]
            hovers.append("<br>".join(hover_parts))

        node_traces.append(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='markers+text',
            name='Outcome',
            text=texts,
            textposition="bottom center",
            textfont=dict(size=11, color="#7c2d12", family="Inter, sans-serif"),
            hovertext=hovers,
            hoverinfo='text',
            marker=dict(
                size=26,
                color='#f97316',
                line=dict(width=3, color='white'),
                symbol='circle',
                opacity=0.95
            )
        ))

    # ─────────────────────────────────────────────────────────────
    # Figure 생성
    # ─────────────────────────────────────────────────────────────
    fig = go.Figure(
        data=edge_traces + node_traces,
        layout=go.Layout(
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.02,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="#e2e8f0",
                borderwidth=1,
                font=dict(size=12)
            ),
            hovermode='closest',
            margin=dict(b=60, l=20, r=20, t=20),
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                scaleanchor="y",
                scaleratio=1
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False
            ),
            height=700,
            plot_bgcolor='#fafbfc',
            paper_bgcolor='white',
            dragmode='pan'
        )
    )

    # 확대/축소 버튼 추가
    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                y=1.0,
                x=1.0,
                xanchor="right",
                yanchor="top",
                buttons=[
                    dict(label="Reset View",
                         method="relayout",
                         args=[{"xaxis.autorange": True, "yaxis.autorange": True}])
                ]
            )
        ]
    )

    return fig


def render_legend():
    """범례 렌더링."""
    st.markdown("""
    <div class="legend-container">
        <div class="legend-title">Graph Legend</div>
        <div class="legend-grid">
            <div class="legend-item">
                <div class="legend-color square node-intervention"></div>
                <span>Intervention (Surgery)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color circle node-outcome"></div>
                <span>Outcome (Measure)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color edge-improved"></div>
                <span>Improved</span>
            </div>
            <div class="legend-item">
                <div class="legend-color edge-worsened"></div>
                <span>Worsened</span>
            </div>
            <div class="legend-item">
                <div class="legend-color edge-unchanged"></div>
                <span>Unchanged</span>
            </div>
            <div class="legend-item">
                <span style="font-weight: 600;">━━</span>
                <span>Significant (p&lt;0.05)</span>
            </div>
            <div class="legend-item">
                <span style="color: #94a3b8;">┈┈</span>
                <span>Not Significant</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_stats(G: nx.DiGraph):
    """통계 표시."""
    n_interventions = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "intervention")
    n_outcomes = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "outcome")
    n_edges = G.number_of_edges()
    n_sig = sum(1 for u, v, d in G.edges(data=True) if d.get("is_significant"))

    cols = st.columns(4)

    stats = [
        ("Interventions", n_interventions, "🔧"),
        ("Outcomes", n_outcomes, "🎯"),
        ("Relationships", n_edges, "🔗"),
        ("Significant", n_sig, "✓"),
    ]

    for col, (label, value, icon) in zip(cols, stats):
        with col:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-value">{icon} {value}</div>
                <div class="stat-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # 헤더
    st.markdown("""
    <div class="graph-header">
        <h1>🔗 Knowledge Graph Network</h1>
        <p>Intervention → Outcome 관계 시각화 및 탐색</p>
    </div>
    """, unsafe_allow_html=True)

    # Neo4j 연결
    neo4j_client = get_neo4j_client()

    if neo4j_client is None:
        st.error("Neo4j 연결 실패. Docker 컨테이너가 실행 중인지 확인하세요.")
        st.code("docker-compose up -d neo4j", language="bash")
        return

    st.markdown("""
    <div class="status-connected">
        <span class="status-dot"></span>
        Neo4j Connected
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 탭
    tab1, tab2, tab3 = st.tabs([
        "📊 Intervention-Outcome Graph",
        "📄 Paper Network",
        "📈 Statistics"
    ])

    # ─────────────────────────────────────────────────────────────
    # TAB 1: Intervention-Outcome Graph
    # ─────────────────────────────────────────────────────────────
    with tab1:
        # 컨트롤 패널
        st.markdown('<div class="control-panel">', unsafe_allow_html=True)
        st.markdown("<h4>🎛️ Filters & Layout</h4>", unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cypher = "MATCH (i:Intervention) RETURN DISTINCT i.name AS name ORDER BY name LIMIT 100"
            i_records = neo4j_client.run_query(cypher, {})
            interventions = ["All"] + [r["name"] for r in i_records]
            st.markdown('<p class="filter-label">Intervention</p>', unsafe_allow_html=True)
            selected_intervention = st.selectbox(
                "Intervention",
                interventions,
                index=0,
                label_visibility="collapsed"
            )

        with col2:
            cypher = "MATCH (o:Outcome) RETURN DISTINCT o.name AS name ORDER BY name LIMIT 100"
            o_records = neo4j_client.run_query(cypher, {})
            outcomes = ["All"] + [r["name"] for r in o_records]
            st.markdown('<p class="filter-label">Outcome</p>', unsafe_allow_html=True)
            selected_outcome = st.selectbox(
                "Outcome",
                outcomes,
                index=0,
                label_visibility="collapsed"
            )

        with col3:
            cypher = "MATCH (i:Intervention) WHERE i.category IS NOT NULL RETURN DISTINCT i.category AS cat ORDER BY cat"
            c_records = neo4j_client.run_query(cypher, {})
            categories = ["All"] + [r["cat"] for r in c_records]
            st.markdown('<p class="filter-label">Category</p>', unsafe_allow_html=True)
            selected_category = st.selectbox(
                "Category",
                categories,
                index=0,
                label_visibility="collapsed"
            )

        with col4:
            cypher = "MATCH (p:Pathology) RETURN DISTINCT p.name AS name ORDER BY name LIMIT 50"
            p_records = neo4j_client.run_query(cypher, {})
            pathologies = ["All"] + [r["name"] for r in p_records]
            st.markdown('<p class="filter-label">Pathology</p>', unsafe_allow_html=True)
            selected_pathology = st.selectbox(
                "Pathology",
                pathologies,
                index=0,
                label_visibility="collapsed"
            )

        # 두 번째 행
        col5, col6, col7, col8 = st.columns(4)

        with col5:
            st.markdown('<p class="filter-label">Layout</p>', unsafe_allow_html=True)
            layout_type = st.selectbox(
                "Layout",
                ["spring", "cluster", "hierarchical"],
                format_func=lambda x: {
                    "spring": "Spring (Natural)",
                    "cluster": "Cluster (By Category)",
                    "hierarchical": "Hierarchical"
                }[x],
                label_visibility="collapsed"
            )

        with col6:
            st.markdown('<p class="filter-label">Color Mode</p>', unsafe_allow_html=True)
            color_by = st.selectbox(
                "Color",
                ["type", "category"],
                format_func=lambda x: {
                    "type": "By Node Type",
                    "category": "By Category"
                }[x],
                label_visibility="collapsed"
            )

        with col7:
            st.markdown('<p class="filter-label">Filter</p>', unsafe_allow_html=True)
            sig_only = st.checkbox("Significant Only (p<0.05)", value=False)

        with col8:
            st.markdown('<p class="filter-label">Max Results</p>', unsafe_allow_html=True)
            max_results = st.slider(
                "Max",
                20, 200, 80, 20,
                label_visibility="collapsed"
            )

        st.markdown('</div>', unsafe_allow_html=True)

        # 범례
        render_legend()

        # 그래프 생성
        with st.spinner("Loading graph..."):
            G = build_graph(
                neo4j_client,
                intervention=selected_intervention if selected_intervention != "All" else None,
                outcome=selected_outcome if selected_outcome != "All" else None,
                category=selected_category if selected_category != "All" else None,
                pathology=selected_pathology if selected_pathology != "All" else None,
                sig_only=sig_only,
                limit=max_results
            )

            fig = create_visualization(G, layout_type=layout_type, color_by=color_by)

        if fig:
            # 통계
            render_stats(G)

            st.markdown("<br>", unsafe_allow_html=True)

            # 그래프
            st.markdown('<div class="graph-container">', unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'scrollZoom': True
            })
            st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.info("No relationships found for the selected filters.")

    # ─────────────────────────────────────────────────────────────
    # TAB 2: Paper Network
    # ─────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("### 📄 Paper Citation Network")

        col1, col2 = st.columns([3, 1])

        with col1:
            paper_intervention = st.selectbox(
                "Filter by Intervention",
                interventions,
                index=0,
                key="paper_filter"
            )

        with col2:
            max_papers = st.number_input("Max Papers", 10, 100, 50)

        with st.spinner("Loading paper network..."):
            network_data = get_paper_network(
                neo4j_client,
                intervention=paper_intervention if paper_intervention != "All" else None,
                limit=max_papers
            )

        if network_data and network_data.get("nodes"):
            fig = create_network_graph(network_data)
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"📄 {len(network_data['nodes'])} papers, 🔗 {len(network_data.get('edges', []))} citations")
        else:
            st.info("Upload PDFs to build the paper network.")

    # ─────────────────────────────────────────────────────────────
    # TAB 3: Statistics
    # ─────────────────────────────────────────────────────────────
    with tab3:
        st.markdown("### 📊 Graph Statistics")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Node Distribution")
            cypher = """
            MATCH (n)
            WITH labels(n)[0] AS label, count(*) AS count
            RETURN label, count ORDER BY count DESC
            """
            node_stats = neo4j_client.run_query(cypher, {})

            if node_stats:
                df = pd.DataFrame(node_stats)
                fig = px.bar(
                    df, x="label", y="count",
                    color="label",
                    title="Nodes by Type",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig.update_layout(showlegend=False, height=350)
                fig.update_traces(textposition='outside', texttemplate='%{y}')
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("#### Relationship Distribution")
            cypher = """
            MATCH ()-[r]->()
            WITH type(r) AS rel_type, count(*) AS count
            RETURN rel_type, count ORDER BY count DESC
            """
            rel_stats = neo4j_client.run_query(cypher, {})

            if rel_stats:
                df = pd.DataFrame(rel_stats)
                fig = px.bar(
                    df, x="rel_type", y="count",
                    color="rel_type",
                    title="Relationships by Type",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig.update_layout(showlegend=False, height=350)
                fig.update_traces(textposition='outside', texttemplate='%{y}')
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        st.markdown("#### Evidence Level Distribution")
        cypher = """
        MATCH (p:Paper)
        WHERE p.evidence_level IS NOT NULL
        WITH p.evidence_level AS level, count(*) AS count
        RETURN level, count ORDER BY level
        """
        evidence_dist = neo4j_client.run_query(cypher, {})

        if evidence_dist:
            df = pd.DataFrame(evidence_dist)
            fig = px.pie(
                df, names="level", values="count",
                title="Papers by Evidence Level",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
