"""Knowledge Graph Page - Paper Relationship Visualization.

Enhanced UI/UX for exploring paper relationships.
"""

from pathlib import Path
import sys

import streamlit as st

st.set_page_config(page_title="Knowledge Graph - Medical KAG", page_icon="📊", layout="wide")

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

from utils.server_bridge import get_server
from utils.async_helpers import run_async
from utils.styles import load_css, render_page_header, render_card, render_tag


def create_network_graph(papers: list, relations: list):
    """Create interactive network graph using Plotly."""
    try:
        import plotly.graph_objects as go
        import networkx as nx
    except ImportError:
        st.error("Plotly and NetworkX required. Run: pip install plotly networkx")
        return None

    G = nx.Graph()

    # Add nodes
    for paper in papers:
        G.add_node(paper["id"], title=paper.get("title", paper["id"]))

    # Edge colors by relation type
    edge_colors = {
        "supports": "#22c55e",      # Green
        "contradicts": "#ef4444",   # Red
        "similar_topic": "#3b82f6", # Blue
        "cites": "#94a3b8"          # Gray
    }

    for rel in relations:
        G.add_edge(
            rel["source"],
            rel["target"],
            type=rel["type"],
            confidence=rel.get("confidence", 0.5)
        )

    if len(G.nodes()) == 0:
        return None

    pos = nx.spring_layout(G, k=2, iterations=50)

    # Create edge traces
    edge_traces = []
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_type = edge[2].get("type", "unknown")
        color = edge_colors.get(edge_type, "#94a3b8")
        confidence = edge[2].get("confidence", 0.5)
        width = 1 + (confidence * 3)

        edge_traces.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(width=width, color=color),
            hoverinfo='text',
            hovertext=f"{edge_type} (conf: {confidence:.2f})",
            showlegend=False
        ))

    # Create node trace
    node_x = [pos[node][0] for node in G.nodes()]
    node_y = [pos[node][1] for node in G.nodes()]
    node_text = [G.nodes[node].get("title", node)[:40] + "..." for node in G.nodes()]

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=node_text,
        textposition="top center",
        textfont=dict(size=10, color="#1e293b"),
        marker=dict(
            size=24,
            color='#3b82f6',
            line=dict(width=2, color='#1e40af'),
            symbol='circle'
        )
    )

    fig = go.Figure(
        data=edge_traces + [node_trace],
        layout=go.Layout(
            showlegend=False,
            hovermode='closest',
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            margin=dict(b=20, l=20, r=20, t=20),
            height=450,
            paper_bgcolor='white',
            plot_bgcolor='white'
        )
    )

    return fig


def get_confidence_color(confidence: float) -> str:
    """Get color based on confidence level."""
    if confidence >= 0.8:
        return "#22c55e"  # Green
    elif confidence >= 0.6:
        return "#f59e0b"  # Amber
    else:
        return "#ef4444"  # Red


def get_confidence_badge(confidence: float) -> str:
    """Get confidence badge HTML."""
    color = get_confidence_color(confidence)
    level = "High" if confidence >= 0.8 else "Medium" if confidence >= 0.6 else "Low"
    # Single-line HTML to avoid rendering issues in nested templates
    return f'<span style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 500; background: {color}15; color: {color};"><span style="width: 6px; height: 6px; border-radius: 50%; background: {color};"></span>{confidence:.0%} {level}</span>'


def render_relation_card(rel: dict, rel_type: str, selected_paper: str = None) -> None:
    """Render a styled relation card.

    Args:
        rel: Relation dictionary with source, target, confidence, evidence
        rel_type: Type of relation (supports, contradicts, similar_topic, cites)
        selected_paper: Currently selected paper ID to determine "other" paper
    """
    emoji_map = {
        "supports": "✅",
        "contradicts": "❌",
        "similar_topic": "🔗",
        "cites": "📚"
    }
    color_map = {
        "supports": ("#dcfce7", "#166534"),
        "contradicts": ("#fee2e2", "#991b1b"),
        "similar_topic": ("#dbeafe", "#1e40af"),
        "cites": ("#f1f5f9", "#475569")
    }

    emoji = emoji_map.get(rel_type, "•")
    bg_color, text_color = color_map.get(rel_type, ("#f1f5f9", "#475569"))

    # Determine the "other" paper (not the selected one)
    source = rel.get("source") or rel.get("source_id", "")
    target = rel.get("target") or rel.get("target_id", "")

    if selected_paper:
        # Show the OTHER paper, not the selected one
        if source == selected_paper:
            other_paper = target
        elif target == selected_paper:
            other_paper = source
        else:
            other_paper = target  # fallback
    else:
        other_paper = target

    conf = rel.get("confidence", 0) or rel.get("similarity", 0)
    evidence = rel.get("evidence", "")

    # Skip if other_paper is empty or same as selected
    if not other_paper or other_paper == selected_paper:
        return

    # Truncate for display
    target_display = other_paper[:50] + '...' if len(other_paper) > 50 else other_paper

    # Build evidence HTML separately
    evidence_html = ""
    if evidence:
        evidence_display = evidence[:100] + "..." if len(evidence) > 100 else evidence
        # v1.15: XSS 방지
        import html as html_mod
        evidence_display = html_mod.escape(evidence_display)
        evidence_html = f'<p style="margin: 0; font-size: 0.85rem; color: #64748b; font-style: italic;">{evidence_display}</p>'

    # Build confidence badge
    badge_html = get_confidence_badge(conf)

    # v1.15: XSS 방지 — Neo4j 데이터 HTML escape
    import html as html_mod
    safe_target = html_mod.escape(str(target_display))

    # Render card with single-line styles
    html = f'''<div style="background: {bg_color}; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; border-left: 4px solid {text_color};">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
<span style="font-weight: 600; color: {text_color};">{emoji} {safe_target}</span>
{badge_html}
</div>
{evidence_html}
</div>'''

    st.markdown(html, unsafe_allow_html=True)


def main():
    load_css()

    render_page_header(
        title="Knowledge Graph",
        subtitle="논문 관계 시각화 및 탐색",
        icon="📊",
        gradient="primary"
    )

    bridge = get_server()
    server = bridge.server

    if not bridge.has_knowledge_graph:
        st.warning("⚠️ Knowledge Graph is not available. Check system configuration.")
        return

    # Main content in tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🗂️ Topic Clusters",
        "🔗 Paper Relations",
        "⚖️ Compare Papers",
        "📚 Evidence Chain"
    ])

    with tab1:
        render_topic_clusters(server)

    with tab2:
        render_paper_relations(server)

    with tab3:
        render_compare_papers(server)

    with tab4:
        render_evidence_chain(server)

    # Sidebar Legend (using native Streamlit components)
    with st.sidebar:
        st.subheader("📖 Legend")

        st.markdown("**Relation Types**")
        st.markdown("""
- ✅ **Supports**: Findings support each other
- ❌ **Contradicts**: Conflicting results
- 🔗 **Similar Topic**: Related research
- 📚 **Cites**: Citation relationship
        """)

        st.divider()

        st.markdown("**Confidence Levels**")
        st.markdown("""
- 🟢 **High** (80%+): Strong match
- 🟡 **Medium** (60-79%): Moderate match
- 🔴 **Low** (<60%): Weak match
        """)

        st.divider()

        st.markdown("**Evidence Levels**")
        st.markdown("""
- **1a**: Meta-analysis (highest)
- **1b**: RCT
- **2a**: Cohort study
- **2b**: Case-control
- **3-4**: Lower evidence
        """)


def render_topic_clusters(server):
    """Render topic clusters section."""
    st.markdown("### Topic Clusters")
    st.caption("논문들을 주제별로 클러스터링하여 보여줍니다.")

    with st.spinner("Loading clusters..."):
        clusters_result = run_async(server.get_topic_clusters())

    if clusters_result.get("success"):
        clusters = clusters_result.get("clusters", {})

        if clusters:
            cols = st.columns(2)
            for idx, (topic, info) in enumerate(clusters.items()):
                count = info.get("count", 0)
                papers = info.get("papers", [])

                with cols[idx % 2]:
                    with st.expander(f"📁 **{topic}** ({count} papers)", expanded=idx < 2):
                        for paper in papers[:10]:
                            title = paper.get('title', paper.get('paper_id', 'Unknown'))
                            year = paper.get('year', '')
                            st.markdown(f"""
                            <div style="
                                padding: 8px 12px;
                                background: #f8fafc;
                                border-radius: 6px;
                                margin-bottom: 6px;
                                border-left: 3px solid #3b82f6;
                            ">
                                <span style="font-size: 0.9rem; color: #1e293b;">{title[:60]}{'...' if len(title) > 60 else ''}</span>
                                {f'<span style="font-size: 0.75rem; color: #64748b; margin-left: 8px;">({year})</span>' if year else ''}
                            </div>
                            """, unsafe_allow_html=True)

                        if len(papers) > 10:
                            st.caption(f"+{len(papers) - 10} more papers")
        else:
            st.info("📭 No clusters found. Add more papers to see topic clusters.")
    else:
        st.error(f"Failed to load clusters: {clusters_result.get('error')}")


def render_paper_relations(server):
    """Render paper relations section."""
    st.markdown("### Paper Relations")
    st.caption("특정 논문과 관련된 다른 논문들을 탐색합니다.")

    # Get documents
    docs_result = run_async(server.list_documents())

    if not (docs_result.get("success") and docs_result.get("documents")):
        st.info("📭 No documents available. Add some PDFs first.")
        return

    documents = docs_result["documents"]
    doc_options = [d.get("document_id", "Unknown") for d in documents]

    # Selection controls
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        selected_paper = st.selectbox(
            "Select a paper",
            doc_options,
            help="Choose a paper to find its relations"
        )

    with col2:
        relation_filter = st.selectbox(
            "Relation type",
            [None, "cites", "supports", "contradicts", "similar_topic"],
            format_func=lambda x: "All Types" if x is None else x.replace("_", " ").title()
        )

    with col3:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Find Relations", type="primary", use_container_width=True)

    if selected_paper and search_clicked:
        with st.spinner("Finding relations..."):
            rel_result = run_async(server.get_paper_relations(
                selected_paper,
                relation_filter
            ))

        if rel_result.get("success"):
            # Get pre-processed paper lists (cleaner than raw relations)
            supporting = rel_result.get("supporting_papers", [])
            contradicting = rel_result.get("contradicting_papers", [])
            similar = rel_result.get("similar_papers", [])
            raw_relations = rel_result.get("relations", [])

            # Build unified relations list from pre-processed data
            all_relations = []

            # Add supporting papers
            for p in supporting:
                if p.get("id") != selected_paper:
                    all_relations.append({
                        "target": p.get("id"),
                        "title": p.get("title"),
                        "type": "supports",
                        "confidence": p.get("confidence", 0),
                        "evidence": ""
                    })

            # Add contradicting papers
            for p in contradicting:
                if p.get("id") != selected_paper:
                    all_relations.append({
                        "target": p.get("id"),
                        "title": p.get("title"),
                        "type": "contradicts",
                        "confidence": p.get("confidence", 0),
                        "evidence": ""
                    })

            # Add similar papers
            for p in similar:
                if p.get("id") != selected_paper:
                    all_relations.append({
                        "target": p.get("id"),
                        "title": p.get("title"),
                        "type": "similar_topic",
                        "confidence": p.get("similarity", 0),
                        "evidence": ""
                    })

            # Add citations from raw relations (if not already added)
            seen_papers = {r["target"] for r in all_relations}
            for rel in raw_relations:
                rel_type = rel.get("type", "")
                if rel_type == "cites":
                    source = rel.get("source", "")
                    target = rel.get("target", "")
                    other = target if source == selected_paper else source
                    if other and other != selected_paper and other not in seen_papers:
                        all_relations.append({
                            "target": other,
                            "type": "cites",
                            "confidence": rel.get("confidence", 0),
                            "evidence": rel.get("evidence", "")
                        })
                        seen_papers.add(other)

            if all_relations:
                # Summary metrics
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
                    border-radius: 8px;
                    padding: 16px;
                    margin: 16px 0;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                ">
                    <span style="font-size: 2rem;">🔗</span>
                    <div>
                        <div style="font-size: 1.25rem; font-weight: 700; color: #1e40af;">{len(all_relations)} Related Papers Found</div>
                        <div style="font-size: 0.85rem; color: #3b82f6;">for {selected_paper[:40]}...</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Group by type
                by_type = {}
                for rel in all_relations:
                    rel_type = rel.get("type", "unknown")
                    if rel_type not in by_type:
                        by_type[rel_type] = []
                    by_type[rel_type].append(rel)

                # Display by type in columns
                type_order = ["supports", "contradicts", "similar_topic", "cites"]
                displayed_types = [t for t in type_order if t in by_type]

                if displayed_types:
                    cols = st.columns(min(len(displayed_types), 2))

                    for idx, rel_type in enumerate(displayed_types):
                        rels = by_type[rel_type]
                        emoji = {
                            "supports": "✅",
                            "contradicts": "❌",
                            "similar_topic": "🔗",
                            "cites": "📚"
                        }.get(rel_type, "•")

                        with cols[idx % 2]:
                            st.markdown(f"#### {emoji} {rel_type.replace('_', ' ').title()} ({len(rels)})")

                            for rel in rels[:10]:
                                render_relation_card(rel, rel_type, selected_paper)

                            if len(rels) > 10:
                                st.caption(f"+{len(rels) - 10} more")
            else:
                st.info("📭 No related papers found for this paper.")
        else:
            st.error(f"Failed: {rel_result.get('error')}")


def render_compare_papers(server):
    """Render paper comparison section."""
    st.markdown("### Compare Papers")
    st.caption("여러 논문을 비교 분석합니다.")

    docs_result = run_async(server.list_documents())

    if not (docs_result.get("success") and docs_result.get("documents")):
        st.info("📭 No documents available. Add some PDFs first.")
        return

    documents = docs_result["documents"]
    doc_options = [d.get("document_id", "Unknown") for d in documents]

    selected_papers = st.multiselect(
        "Select papers to compare (2-5)",
        doc_options,
        max_selections=5,
        help="Choose 2 or more papers to compare"
    )

    if len(selected_papers) >= 2:
        if st.button("📊 Compare Papers", type="primary"):
            with st.spinner("Comparing papers..."):
                compare_result = run_async(server.compare_papers(selected_papers))

            if compare_result.get("success"):
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin: 16px 0;
                    border: 1px solid #bbf7d0;
                ">
                    ✅ <strong>Comparison complete!</strong>
                </div>
                """, unsafe_allow_html=True)

                # Extract analysis from nested object (MCP Server v5.1 format)
                analysis = compare_result.get("analysis", {})

                col1, col2 = st.columns(2)

                with col1:
                    similarities = analysis.get("similarities", [])
                    st.markdown("""
                    <div style="
                        background: #f0fdf4;
                        border-radius: 8px;
                        padding: 16px;
                        border: 1px solid #bbf7d0;
                    ">
                        <h4 style="margin: 0 0 12px 0; color: #166534;">🤝 Similarities</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    if similarities:
                        for sim in similarities:
                            st.markdown(f"- {sim}")
                    else:
                        st.caption("No significant similarities found.")

                with col2:
                    differences = analysis.get("differences", [])
                    st.markdown("""
                    <div style="
                        background: #fef3c7;
                        border-radius: 8px;
                        padding: 16px;
                        border: 1px solid #fcd34d;
                    ">
                        <h4 style="margin: 0 0 12px 0; color: #92400e;">📌 Differences</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    if differences:
                        for diff in differences:
                            st.markdown(f"- {diff}")
                    else:
                        st.caption("No significant differences found.")

                # Contradictions (full width) - server returns "contradictions" not "conflicts"
                conflicts = analysis.get("contradictions", [])
                if conflicts:
                    st.markdown("""
                    <div style="
                        background: #fee2e2;
                        border-radius: 8px;
                        padding: 16px;
                        margin-top: 16px;
                        border: 1px solid #fca5a5;
                    ">
                        <h4 style="margin: 0 0 12px 0; color: #991b1b;">⚠️ Conflicts</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    for conflict in conflicts:
                        st.markdown(f"- {conflict}")
            else:
                st.error(f"Comparison failed: {compare_result.get('error')}")
    else:
        st.caption("ℹ️ Select at least 2 papers to compare.")


def render_evidence_chain(server):
    """Render evidence chain section."""
    st.markdown("### Evidence Chain")
    st.caption("주장을 뒷받침하거나 반박하는 논문 체인을 찾습니다.")

    claim = st.text_input(
        "Enter a claim to find supporting/refuting evidence",
        placeholder="e.g., UBE shows better outcomes than TLIF for lumbar stenosis"
    )

    if claim:
        if st.button("🔍 Find Evidence Chain", type="primary"):
            with st.spinner("Finding evidence chain..."):
                chain_result = run_async(server.find_evidence_chain(claim))

            if chain_result.get("success"):
                supporting = chain_result.get("supporting_papers", [])
                # Support both "contradicting_papers" (MCP v5.1) and "refuting_papers" (legacy)
                refuting = chain_result.get("contradicting_papers", chain_result.get("refuting_papers", []))

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
                        border-radius: 8px;
                        padding: 16px;
                        margin-bottom: 12px;
                        border: 1px solid #bbf7d0;
                    ">
                        <h4 style="margin: 0; color: #166534;">✅ Supporting Evidence ({len(supporting)})</h4>
                    </div>
                    """, unsafe_allow_html=True)

                    if supporting:
                        for paper in supporting:
                            conf = paper.get('confidence', 0)
                            st.markdown(f"""
                            <div style="
                                background: white;
                                border-radius: 8px;
                                padding: 12px;
                                margin-bottom: 8px;
                                border: 1px solid #e5e7eb;
                            ">
                                <div style="font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                                    {paper.get('title', 'Unknown')[:50]}...
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 0.8rem; color: #64748b;">
                                        {paper.get('year', '')}
                                    </span>
                                    {get_confidence_badge(conf)}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.caption("No supporting evidence found.")

                with col2:
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%);
                        border-radius: 8px;
                        padding: 16px;
                        margin-bottom: 12px;
                        border: 1px solid #fca5a5;
                    ">
                        <h4 style="margin: 0; color: #991b1b;">❌ Refuting Evidence ({len(refuting)})</h4>
                    </div>
                    """, unsafe_allow_html=True)

                    if refuting:
                        for paper in refuting:
                            conf = paper.get('confidence', 0)
                            st.markdown(f"""
                            <div style="
                                background: white;
                                border-radius: 8px;
                                padding: 12px;
                                margin-bottom: 8px;
                                border: 1px solid #e5e7eb;
                            ">
                                <div style="font-weight: 600; color: #1e293b; margin-bottom: 4px;">
                                    {paper.get('title', 'Unknown')[:50]}...
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 0.8rem; color: #64748b;">
                                        {paper.get('year', '')}
                                    </span>
                                    {get_confidence_badge(conf)}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.caption("No refuting evidence found.")
            else:
                st.error(f"Failed: {chain_result.get('error')}")


if __name__ == "__main__":
    main()
