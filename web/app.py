"""Spine GraphRAG Web UI - Main Dashboard.

Streamlit 기반 웹 인터페이스의 메인 대시보드 (Redesigned v2.0).

실행:
    streamlit run web/app.py
"""

import html as html_mod
import streamlit as st
from pathlib import Path

# Load .env file for API keys
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Page config must be first Streamlit command
st.set_page_config(
    page_title="Spine GraphRAG",
    page_icon="🦴",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.server_bridge import get_server
from utils.async_helpers import run_async
from utils.shared_styles import apply_sidebar_styles

# Apply shared sidebar styles (app → 🏠 Main)
apply_sidebar_styles()

# ═══════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* 전체 컨테이너 */
.main .block-container {
    max-width: 1400px;
    padding: 1.5rem 2rem;
}

/* 히어로 헤더 */
.hero-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #0ea5e9 100%);
    color: white;
    padding: 2rem 2.5rem;
    border-radius: 20px;
    margin-bottom: 2rem;
    box-shadow: 0 8px 32px rgba(30, 58, 95, 0.3);
    position: relative;
    overflow: hidden;
}

.hero-header::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 300px;
    height: 100%;
    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="rgba(255,255,255,0.05)"/></svg>');
    opacity: 0.5;
}

.hero-header h1 {
    margin: 0;
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}

.hero-header p {
    margin: 0.75rem 0 0 0;
    font-size: 1.1rem;
    opacity: 0.95;
    font-weight: 400;
}

/* 시스템 상태 뱃지 */
.status-bar {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
}

.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 1rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
}

.status-badge.success {
    background: #dcfce7;
    color: #166534;
}

.status-badge.warning {
    background: #fef3c7;
    color: #92400e;
}

.status-badge.info {
    background: #dbeafe;
    color: #1e40af;
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.8;
}

/* 빠른 접근 카드 */
.nav-card {
    background: white;
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    border: 1px solid #e2e8f0;
    transition: all 0.2s ease;
    cursor: pointer;
    height: 100%;
}

.nav-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 24px rgba(0,0,0,0.1);
    border-color: #3b82f6;
}

.nav-icon {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
}

.nav-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #1e293b;
    margin-bottom: 0.25rem;
}

.nav-desc {
    font-size: 0.75rem;
    color: #64748b;
    line-height: 1.3;
}

/* Quick Access 버튼 텍스트 축소 */
.main [data-testid="stHorizontalBlock"] button[kind="secondary"] p {
    font-size: 0.8rem !important;
    line-height: 1.4 !important;
}
.main [data-testid="stVerticalBlock"] > div > div > button p {
    font-size: 0.8rem !important;
    line-height: 1.4 !important;
}

/* 통계 카드 그리드 */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.stat-card {
    background: linear-gradient(135deg, #f8fafc 0%, white 100%);
    border-radius: 16px;
    padding: 1.25rem;
    text-align: center;
    border: 1px solid #e2e8f0;
    transition: all 0.2s ease;
}

.stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.stat-icon {
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
}

.stat-value {
    font-size: 2rem;
    font-weight: 800;
    color: #1e3a5f;
    line-height: 1;
}

.stat-label {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* 섹션 헤더 */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

.section-header h3 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 700;
    color: #1e293b;
}

/* 검색 박스 */
.search-container {
    background: #f8fafc;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
}

.search-examples {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1rem;
}

.search-example {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 20px;
    padding: 0.35rem 0.75rem;
    font-size: 0.8rem;
    color: #475569;
    cursor: pointer;
    transition: all 0.2s ease;
}

.search-example:hover {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
}

/* 문서/수술법 리스트 */
.list-card {
    background: white;
    border-radius: 12px;
    padding: 1.25rem;
    border: 1px solid #e2e8f0;
    margin-bottom: 0.75rem;
    transition: all 0.2s ease;
}

.list-card:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.list-card-title {
    font-weight: 600;
    color: #1e293b;
    margin-bottom: 0.25rem;
}

.list-card-meta {
    font-size: 0.85rem;
    color: #64748b;
}

.list-card-badge {
    display: inline-block;
    background: #dcfce7;
    color: #166534;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    margin-left: 0.5rem;
}

/* 메달 */
.medal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    font-size: 0.9rem;
    margin-right: 0.5rem;
}

.medal-gold { background: #fef3c7; }
.medal-silver { background: #f1f5f9; }
.medal-bronze { background: #fed7aa; }

/* 푸터 */
.footer {
    text-align: center;
    padding: 1.5rem;
    color: #64748b;
    font-size: 0.85rem;
    border-top: 1px solid #e2e8f0;
    margin-top: 2rem;
}

/* 프로그레스 바 */
.custom-progress {
    background: #e2e8f0;
    border-radius: 10px;
    height: 10px;
    overflow: hidden;
    margin: 0.75rem 0;
}

.custom-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #0ea5e9);
    border-radius: 10px;
    transition: width 0.3s ease;
}

/* 결과 카드 */
.result-card {
    background: white;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    border: 1px solid #e2e8f0;
    margin-bottom: 0.75rem;
}

.result-card.high-score {
    border-left: 4px solid #22c55e;
}

.result-card.medium-score {
    border-left: 4px solid #f59e0b;
}

.result-card.low-score {
    border-left: 4px solid #ef4444;
}
</style>
""", unsafe_allow_html=True)


def get_neo4j_stats():
    """Get Neo4j graph statistics."""
    try:
        from utils.graph_utils import SyncNeo4jClient
        client = SyncNeo4jClient()

        stats_query = """
        MATCH (p:Paper) WITH count(p) as papers
        MATCH (i:Intervention) WITH papers, count(i) as interventions
        MATCH (o:Outcome) WITH papers, interventions, count(o) as outcomes
        MATCH (path:Pathology) WITH papers, interventions, outcomes, count(path) as pathologies
        MATCH ()-[a:AFFECTS]->() WITH papers, interventions, outcomes, pathologies, count(a) as affects_count
        MATCH (i:Intervention) WHERE i.snomed_code IS NOT NULL AND i.snomed_code <> ''
        WITH papers, interventions, outcomes, pathologies, affects_count, count(i) as snomed_interventions
        RETURN papers, interventions, outcomes, pathologies, affects_count, snomed_interventions
        """
        result = client.run_query(stats_query)
        if result:
            return result[0]
        return None
    except Exception:
        return None


def get_top_interventions():
    """Get top interventions by paper count."""
    try:
        from utils.graph_utils import SyncNeo4jClient
        client = SyncNeo4jClient()

        query = """
        MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
        WITH i.name as name, count(p) as paper_count, i.snomed_code as snomed
        ORDER BY paper_count DESC
        LIMIT 5
        RETURN name, paper_count, snomed
        """
        return client.run_query(query)
    except Exception:
        return []


def main():
    """Main dashboard."""
    # Hero Header
    st.markdown("""
    <div class="hero-header">
        <h1>🦴 Spine GraphRAG</h1>
        <p>척추 수술 연구를 위한 AI 기반 지식 그래프 시스템</p>
    </div>
    """, unsafe_allow_html=True)

    # Get server
    bridge = get_server()
    server = bridge.server

    # System Status Bar
    status_html = '<div class="status-bar">'

    if bridge.is_llm_enabled:
        status_html += '<span class="status-badge success"><span class="status-dot"></span>Claude LLM</span>'
    else:
        status_html += '<span class="status-badge warning"><span class="status-dot"></span>LLM Disabled</span>'

    if bridge.has_knowledge_graph:
        status_html += '<span class="status-badge success"><span class="status-dot"></span>Neo4j Graph</span>'
    else:
        status_html += '<span class="status-badge warning"><span class="status-dot"></span>Graph Offline</span>'

    status_html += '<span class="status-badge info"><span class="status-dot"></span>Neo4j Vector (v5.3)</span>'
    status_html += '<span class="status-badge info"><span class="status-dot"></span>SNOMED-CT v3.2</span>'
    status_html += '</div>'

    st.markdown(status_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    # QUICK NAVIGATION
    # ═══════════════════════════════════════════════════════════
    st.markdown('<div class="section-header"><h3>⚡ Quick Access</h3></div>', unsafe_allow_html=True)

    nav_cols = st.columns(5)

    nav_items = [
        ("📄", "Documents", "Upload & manage PDFs", "pages/1_📄_Documents.py"),
        ("🔍", "Search", "Hybrid knowledge search", "pages/2_🔍_Search.py"),
        ("🏥", "Clinical Decision", "Treatment recommendations", "pages/10_🏥_Clinical_Decision.py"),
        ("🦴", "Taxonomy", "Explore interventions", "pages/7_🦴_Spine_Explorer.py"),
        ("🔗", "Graph Network", "Visualize relationships", "pages/8_🔗_Graph_Network.py"),
    ]

    for col, (icon, title, desc, page) in zip(nav_cols, nav_items):
        with col:
            if st.button(f"{icon} **{title}**\n\n{desc}", key=f"nav_{title}", use_container_width=True):
                st.switch_page(page)

    st.markdown("<br>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════
    st.markdown('<div class="section-header"><h3>📊 System Statistics</h3></div>', unsafe_allow_html=True)

    doc_result = run_async(server.list_documents())
    total_docs = doc_result.get("total_documents", 0)
    total_chunks = doc_result.get("total_chunks", 0)

    neo4j_stats = get_neo4j_stats()

    stats = [
        ("📄", "Papers", neo4j_stats.get("papers", total_docs) if neo4j_stats else total_docs),
        ("📑", "Chunks", total_chunks),
        ("🔬", "Interventions", neo4j_stats.get("interventions", 0) if neo4j_stats else 0),
        ("📈", "Outcomes", neo4j_stats.get("outcomes", 0) if neo4j_stats else 0),
        ("🦠", "Pathologies", neo4j_stats.get("pathologies", 0) if neo4j_stats else 0),
        ("🔗", "AFFECTS", neo4j_stats.get("affects_count", 0) if neo4j_stats else 0),
    ]

    stat_cols = st.columns(6)
    for col, (icon, label, value) in zip(stat_cols, stats):
        with col:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">{icon}</div>
                <div class="stat-value">{value}</div>
                <div class="stat-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    # SNOMED Coverage
    if neo4j_stats and neo4j_stats.get("snomed_interventions", 0) > 0:
        snomed_count = neo4j_stats.get("snomed_interventions", 0)
        total_int = neo4j_stats.get("interventions", 1)
        coverage = (snomed_count / total_int * 100) if total_int > 0 else 0

        st.markdown(f"""
        <div style="margin: 1rem 0;">
            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #64748b; margin-bottom: 0.25rem;">
                <span>🏥 SNOMED-CT Coverage</span>
                <span>{snomed_count}/{total_int} ({coverage:.0f}%)</span>
            </div>
            <div class="custom-progress">
                <div class="custom-progress-fill" style="width: {coverage}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    # QUICK SEARCH
    # ═══════════════════════════════════════════════════════════
    st.markdown('<div class="section-header"><h3>🔍 Quick Search</h3></div>', unsafe_allow_html=True)

    st.markdown('<div class="search-container">', unsafe_allow_html=True)

    col1, col2 = st.columns([5, 1])

    with col1:
        query = st.text_input(
            "Search",
            placeholder="e.g., 'TLIF vs OLIF for lumbar stenosis' or 'UBE complications'...",
            label_visibility="collapsed"
        )

    with col2:
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

    # Example queries
    example_queries = ["TLIF fusion rate", "UBE vs Laminectomy", "Lumbar stenosis treatment", "ODI improvement"]

    example_cols = st.columns(len(example_queries))
    for i, eq in enumerate(example_queries):
        with example_cols[i]:
            if st.button(eq, key=f"ex_{i}", use_container_width=True):
                query = eq
                search_clicked = True

    st.markdown('</div>', unsafe_allow_html=True)

    if search_clicked and query:
        with st.spinner("Searching knowledge graph..."):
            result = run_async(server.search(
                query=query,
                top_k=5,
                tier_strategy="tier1_first",
                prefer_original=True
            ))

        if result.get("success"):
            results = result.get("results", [])

            if result.get("expansion_terms"):
                st.info(f"🔄 Query expanded: +{', '.join(result['expansion_terms'][:5])}")

            if results:
                st.success(f"Found {len(results)} results")

                for r in results:
                    score = r.get('score', 0)
                    score_class = "high-score" if score > 0.7 else "medium-score" if score > 0.4 else "low-score"

                    with st.expander(f"**{r.get('title', 'Unknown')}** (Score: {score:.2f})"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown(f"**Section:** {r.get('section', 'N/A')}")
                        with col2:
                            st.markdown(f"**Tier:** {r.get('tier', 'N/A')}")
                        with col3:
                            st.markdown(f"**Evidence:** {r.get('evidence_level', 'N/A')}")

                        st.markdown("---")
                        content = r.get('content', '')[:600]
                        st.markdown(f"{content}..." if len(r.get('content', '')) > 600 else content)
            else:
                st.warning("No results found. Try different keywords.")
        else:
            st.error(f"Search failed: {result.get('error', 'Unknown error')}")

    # ═══════════════════════════════════════════════════════════
    # TWO-COLUMN: Recent Docs + Top Interventions
    # ═══════════════════════════════════════════════════════════
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-header"><h3>📋 Recent Documents</h3></div>', unsafe_allow_html=True)

        if doc_result.get("success") and doc_result.get("documents"):
            docs = doc_result["documents"][:5]

            for doc in docs:
                doc_id = doc.get("document_id", "Unknown")
                chunks = doc.get("chunk_count", 0)
                tier1 = doc.get("tier1_count", doc.get("tier1_chunks", 0))
                tier2 = doc.get("tier2_count", doc.get("tier2_chunks", 0))

                display_name = doc_id[:35] + "..." if len(doc_id) > 35 else doc_id

                # v7.15: XSS 방지 — HTML escape
                safe_name = html_mod.escape(display_name)

                st.markdown(f"""
                <div class="list-card">
                    <div class="list-card-title">{safe_name}</div>
                    <div class="list-card-meta">📑 {chunks} chunks (T1: {tier1}, T2: {tier2})</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No documents yet. Upload PDFs to get started.")

    with col_right:
        st.markdown('<div class="section-header"><h3>🏆 Top Interventions</h3></div>', unsafe_allow_html=True)

        top_interventions = get_top_interventions()

        if top_interventions:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

            for i, item in enumerate(top_interventions):
                name = item.get("name", "Unknown")
                count = item.get("paper_count", 0)
                snomed = item.get("snomed", "")

                medal = medals[i] if i < len(medals) else f"{i+1}."
                badge = '<span class="list-card-badge">SNOMED</span>' if snomed else ""

                # v7.15: XSS 방지 — HTML escape
                safe_intervention = html_mod.escape(name)

                st.markdown(f"""
                <div class="list-card">
                    <div class="list-card-title">{medal} {safe_intervention} {badge}</div>
                    <div class="list-card-meta">📄 {count} papers</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Process PDFs to build the knowledge graph.")

    # Footer
    st.markdown("""
    <div class="footer">
        Spine GraphRAG v7.15.0 | Neo4j Unified | Claude Haiku 4.5 | Single-Store Architecture
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
