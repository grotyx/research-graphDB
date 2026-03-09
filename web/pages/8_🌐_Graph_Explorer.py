"""Graph Explorer Page - Interactive Knowledge Graph Visualization.

High-quality graph visualization using vis-network.js library.
Features:
- Physics-based interactive layout
- Query-based node highlighting
- Multiple graph types (Intervention-Outcome, Paper Network, Full Schema)
- Real-time search and exploration
"""

import sys
from pathlib import Path

import streamlit as st

# 프로젝트 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root.parent / "src"))

from utils.graph_utils import get_neo4j_client
from components.vis_network import vis_network_graph, create_spine_graph_data

# 페이지 설정
st.set_page_config(
    page_title="Graph Explorer - Spine GraphRAG",
    page_icon="🌐",
    layout="wide"
)

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

# ═══════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
.main .block-container {
    max-width: 1800px;
    padding: 1rem 2rem;
}

.explorer-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #3b82f6 100%);
    color: white;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
}

.explorer-header h1 {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 12px;
}

.explorer-header p {
    margin: 0.5rem 0 0 0;
    opacity: 0.9;
    font-size: 1rem;
}

.search-box {
    background: white;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.search-box h4 {
    margin: 0 0 1rem 0;
    color: #1e293b;
    font-size: 1rem;
    font-weight: 600;
}

.filter-section {
    background: #f8fafc;
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.filter-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}

.stat-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
}

.stat-card {
    flex: 1;
    background: white;
    border-radius: 10px;
    padding: 1rem;
    text-align: center;
    border: 1px solid #e2e8f0;
}

.stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1e3a5f;
}

.stat-label {
    font-size: 0.8rem;
    color: #64748b;
}

.highlight-info {
    background: #fef3c7;
    border: 1px solid #f59e0b;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 8px;
}

.highlight-info .icon {
    font-size: 1.25rem;
}

.highlight-info .text {
    font-size: 0.9rem;
    color: #92400e;
}

.tab-description {
    background: #f1f5f9;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 1rem;
    font-size: 0.9rem;
    color: #475569;
}

.connected-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #dcfce7;
    color: #166534;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
}

.connected-dot {
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
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_filter_options(neo4j_client):
    """Get filter options from Neo4j."""
    options = {
        "interventions": ["All"],
        "outcomes": ["All"],
        "categories": ["All"],
        "pathologies": ["All"]
    }

    # Interventions
    records = neo4j_client.run_query(
        "MATCH (i:Intervention) RETURN DISTINCT i.name AS name ORDER BY name LIMIT 100", {}
    )
    options["interventions"].extend([r["name"] for r in records if r["name"]])

    # Outcomes
    records = neo4j_client.run_query(
        "MATCH (o:Outcome) RETURN DISTINCT o.name AS name ORDER BY name LIMIT 100", {}
    )
    options["outcomes"].extend([r["name"] for r in records if r["name"]])

    # Categories
    records = neo4j_client.run_query(
        "MATCH (i:Intervention) WHERE i.category IS NOT NULL RETURN DISTINCT i.category AS cat ORDER BY cat", {}
    )
    options["categories"].extend([r["cat"] for r in records if r["cat"]])

    # Pathologies
    records = neo4j_client.run_query(
        "MATCH (p:Pathology) RETURN DISTINCT p.name AS name ORDER BY name LIMIT 50", {}
    )
    options["pathologies"].extend([r["name"] for r in records if r["name"]])

    return options


def search_nodes(neo4j_client, query: str, limit: int = 20) -> list[str]:
    """Search for nodes matching query string."""
    if not query or len(query) < 2:
        return []

    cypher = """
    MATCH (n)
    WHERE (n:Intervention OR n:Outcome OR n:Pathology OR n:Anatomy)
      AND toLower(n.name) CONTAINS toLower($query)
    RETURN n.name AS name
    LIMIT $limit
    """

    records = neo4j_client.run_query(cypher, {"query": query, "limit": limit})
    return [r["name"] for r in records]


def get_graph_stats(neo4j_client) -> dict:
    """Get quick graph statistics."""
    cypher = """
    MATCH (i:Intervention) WITH count(i) AS interventions
    MATCH (o:Outcome) WITH interventions, count(o) AS outcomes
    MATCH (p:Paper) WITH interventions, outcomes, count(p) AS papers
    MATCH ()-[r:AFFECTS]->() WITH interventions, outcomes, papers, count(r) AS relationships
    RETURN interventions, outcomes, papers, relationships
    """

    records = neo4j_client.run_query(cypher, {})
    if records:
        return records[0]
    return {"interventions": 0, "outcomes": 0, "papers": 0, "relationships": 0}


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # Header
    st.markdown("""
    <div class="explorer-header">
        <h1>🌐 Graph Explorer</h1>
        <p>Interactive Knowledge Graph Visualization with vis-network.js</p>
    </div>
    """, unsafe_allow_html=True)

    # Neo4j Connection
    neo4j_client = get_neo4j_client()

    if neo4j_client is None:
        st.error("❌ Neo4j connection failed. Please ensure Docker container is running.")
        st.code("docker-compose up -d neo4j", language="bash")
        return

    # Connection status
    st.markdown("""
    <div class="connected-badge">
        <span class="connected-dot"></span>
        Neo4j Connected
    </div>
    """, unsafe_allow_html=True)

    # Get stats
    stats = get_graph_stats(neo4j_client)

    # Stats row
    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-card">
            <div class="stat-value">🔧 {stats.get('interventions', 0)}</div>
            <div class="stat-label">Interventions</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">🎯 {stats.get('outcomes', 0)}</div>
            <div class="stat-label">Outcomes</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">📄 {stats.get('papers', 0)}</div>
            <div class="stat-label">Papers</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">🔗 {stats.get('relationships', 0)}</div>
            <div class="stat-label">Relationships</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Get filter options
    filter_options = get_filter_options(neo4j_client)

    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "🔧 Intervention → Outcome",
        "📄 Paper Network",
        "🗂️ Full Schema Explorer"
    ])

    # ─────────────────────────────────────────────────────────────
    # TAB 1: Intervention → Outcome
    # ─────────────────────────────────────────────────────────────
    with tab1:
        st.markdown("""
        <div class="tab-description">
            <strong>Intervention-Outcome Graph</strong>: Visualize how surgical interventions affect various outcomes.
            Edges show direction (improved/worsened) and significance (solid=significant, dashed=not significant).
        </div>
        """, unsafe_allow_html=True)

        # Search and filters
        with st.container():
            st.markdown('<div class="search-box">', unsafe_allow_html=True)

            col1, col2 = st.columns([2, 1])

            with col1:
                search_query = st.text_input(
                    "🔍 Search nodes to highlight",
                    placeholder="e.g., TLIF, VAS, fusion...",
                    help="Search for interventions or outcomes to highlight in the graph"
                )

            with col2:
                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    st.markdown("<br>", unsafe_allow_html=True)
                    search_clicked = st.button("🔍 Highlight", type="primary", key="search_btn_tab1")
                with bcol2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    clear_clicked = st.button("🔄 Clear", key="clear_btn_tab1")

            # Store search query in session state for persistence
            if "graph_search_query" not in st.session_state:
                st.session_state.graph_search_query = ""

            if search_clicked and search_query:
                st.session_state.graph_search_query = search_query
                st.rerun()

            if clear_clicked:
                st.session_state.graph_search_query = ""
                st.rerun()

            # Use session state query for highlighting
            active_search_query = st.session_state.graph_search_query or search_query

            # Filters in columns
            st.markdown('<div class="filter-section">', unsafe_allow_html=True)
            fcol1, fcol2, fcol3, fcol4 = st.columns(4)

            with fcol1:
                st.markdown('<p class="filter-label">Intervention</p>', unsafe_allow_html=True)
                selected_intervention = st.selectbox(
                    "Intervention",
                    filter_options["interventions"],
                    label_visibility="collapsed"
                )

            with fcol2:
                st.markdown('<p class="filter-label">Outcome</p>', unsafe_allow_html=True)
                selected_outcome = st.selectbox(
                    "Outcome",
                    filter_options["outcomes"],
                    label_visibility="collapsed"
                )

            with fcol3:
                st.markdown('<p class="filter-label">Category</p>', unsafe_allow_html=True)
                selected_category = st.selectbox(
                    "Category",
                    filter_options["categories"],
                    label_visibility="collapsed"
                )

            with fcol4:
                st.markdown('<p class="filter-label">Options</p>', unsafe_allow_html=True)
                sig_only = st.checkbox("Significant only (p<0.05)", value=False)

            st.markdown('</div>', unsafe_allow_html=True)

            # Layout options
            lcol1, lcol2, lcol3 = st.columns([1, 1, 2])

            with lcol1:
                layout_type = st.selectbox(
                    "Layout",
                    ["physics", "hierarchical"],
                    format_func=lambda x: {"physics": "Physics (Natural)", "hierarchical": "Hierarchical"}[x]
                )

            with lcol2:
                max_nodes = st.slider("Max relationships", 20, 200, 80, 20)

            with lcol3:
                physics_enabled = st.checkbox("Enable physics simulation", value=True)

            st.markdown('</div>', unsafe_allow_html=True)

        # Build filters
        filters = {}
        if selected_intervention != "All":
            filters["intervention"] = selected_intervention
        if selected_outcome != "All":
            filters["outcome"] = selected_outcome
        if selected_category != "All":
            filters["category"] = selected_category
        if sig_only:
            filters["sig_only"] = True

        # Search for highlight nodes
        highlight_nodes = []
        if active_search_query and len(active_search_query) >= 2:
            highlight_nodes = search_nodes(neo4j_client, active_search_query)
            if highlight_nodes:
                st.markdown(f"""
                <div class="highlight-info">
                    <span class="icon">✨</span>
                    <span class="text">Highlighting {len(highlight_nodes)} nodes: {', '.join(highlight_nodes[:5])}{'...' if len(highlight_nodes) > 5 else ''}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info(f"🔍 No nodes found matching '{active_search_query}'")

        # Load and render graph
        with st.spinner("Loading graph..."):
            nodes, edges = create_spine_graph_data(
                neo4j_client,
                query_type="intervention_outcome",
                filters=filters,
                limit=max_nodes
            )

        if nodes:
            st.info(f"📊 Showing {len(nodes)} nodes and {len(edges)} relationships")
            vis_network_graph(
                nodes=nodes,
                edges=edges,
                height=650,
                highlight_nodes=highlight_nodes,
                physics_enabled=physics_enabled,
                layout_type=layout_type
            )
        else:
            st.warning("No data found for the selected filters. Try adjusting your criteria.")

    # ─────────────────────────────────────────────────────────────
    # TAB 2: Paper Network
    # ─────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("""
        <div class="tab-description">
            <strong>Paper Citation Network</strong>: Explore how research papers cite each other.
            Node colors indicate evidence level. Click on a node to see paper details.
        </div>
        """, unsafe_allow_html=True)

        pcol1, pcol2 = st.columns([2, 1])

        with pcol1:
            paper_intervention = st.selectbox(
                "Filter by Intervention",
                filter_options["interventions"],
                key="paper_intervention"
            )

        with pcol2:
            max_papers = st.slider("Max papers", 10, 100, 40, 10)

        # Load paper network
        paper_filters = {}
        if paper_intervention != "All":
            paper_filters["intervention"] = paper_intervention

        with st.spinner("Loading paper network..."):
            nodes, edges = create_spine_graph_data(
                neo4j_client,
                query_type="paper_network",
                filters=paper_filters,
                limit=max_papers
            )

        if nodes:
            st.info(f"📄 Showing {len(nodes)} papers and {len(edges)} citations")
            vis_network_graph(
                nodes=nodes,
                edges=edges,
                height=600,
                physics_enabled=True,
                layout_type="physics"
            )
        else:
            st.info("📭 No papers found. Upload PDFs to build the paper network.")

    # ─────────────────────────────────────────────────────────────
    # TAB 3: Full Schema Explorer
    # ─────────────────────────────────────────────────────────────
    with tab3:
        st.markdown("""
        <div class="tab-description">
            <strong>Full Schema Explorer</strong>: Visualize the complete knowledge graph showing all entity types
            (Papers, Interventions, Outcomes, Pathologies, Anatomy) and their relationships.
        </div>
        """, unsafe_allow_html=True)

        schema_max = st.slider("Max relationships", 50, 300, 100, 50, key="schema_max")

        with st.spinner("Loading full schema..."):
            nodes, edges = create_spine_graph_data(
                neo4j_client,
                query_type="full_schema",
                limit=schema_max
            )

        if nodes:
            st.info(f"🗂️ Showing {len(nodes)} entities and {len(edges)} relationships")
            vis_network_graph(
                nodes=nodes,
                edges=edges,
                height=700,
                physics_enabled=True,
                layout_type="physics"
            )
        else:
            st.info("📭 No data in graph. Process some papers first.")

    # ─────────────────────────────────────────────────────────────
    # Sidebar: Help & Legend
    # ─────────────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("📖 How to Use")
        st.markdown("""
        **Navigation**:
        - 🖱️ Drag to pan
        - 🔍 Scroll to zoom
        - 👆 Click node for details

        **Controls**:
        - **Fit View**: Reset zoom
        - **Toggle Physics**: Freeze/animate
        - **Reset**: Clear highlights

        **Edge Styles**:
        - ━━ Solid: Significant (p<0.05)
        - ┈┈ Dashed: Not significant
        - 🟢 Green: Improved
        - 🔴 Red: Worsened
        """)

        st.divider()

        st.subheader("🎨 Node Colors")
        st.markdown("""
        - 🔵 **Blue**: Intervention
        - 🟠 **Orange**: Outcome
        - 🟢 **Green**: Paper
        - 🔴 **Red**: Pathology
        - 🟣 **Purple**: Anatomy
        - 🟡 **Yellow**: Highlighted
        """)


if __name__ == "__main__":
    main()
