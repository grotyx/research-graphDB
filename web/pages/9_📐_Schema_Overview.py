"""Schema Overview Page - Neo4j Knowledge Graph Schema Visualization.

Interactive visualization of the Spine GraphRAG knowledge graph schema.
Shows all node types, relationship types, counts, and structure.

Version: v1.14.25
"""

import sys
from pathlib import Path

import streamlit as st

# Project path setup
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root.parent / "src"))

# Page configuration
st.set_page_config(
    page_title="Schema Overview - Spine GraphRAG",
    page_icon="📐",
    layout="wide"
)

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

from utils.graph_utils import (
    get_neo4j_client,
    get_schema_node_counts,
    get_schema_relationship_counts,
    get_intervention_hierarchy,
    get_schema_summary
)
from utils.schema_metadata import (
    NODE_TYPE_INFO,
    RELATIONSHIP_TYPE_INFO,
    NODE_CATEGORY_COLORS,
    get_node_info,
    get_relationship_info,
    get_nodes_by_category
)

# ========================================================================
# STYLES
# ========================================================================

st.markdown("""
<style>
.main .block-container {
    max-width: 1800px;
    padding: 1rem 2rem;
}

.schema-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #3b82f6 100%);
    color: white;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
}

.schema-header h1 {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 12px;
}

.schema-header p {
    margin: 0.5rem 0 0 0;
    opacity: 0.9;
    font-size: 1rem;
}

.stat-card {
    background: white;
    border-radius: 12px;
    padding: 1.25rem;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    text-align: center;
}

.stat-card h3 {
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
    color: #1e293b;
}

.stat-card p {
    margin: 0.25rem 0 0 0;
    color: #64748b;
    font-size: 0.9rem;
}

.category-section {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
    border-left: 4px solid;
}

.category-section.core {
    border-left-color: #3b82f6;
}

.category-section.extended {
    border-left-color: #8b5cf6;
}

.category-section.v72 {
    border-left-color: #f97316;
}

.category-title {
    font-weight: 600;
    font-size: 1rem;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 8px;
}

.node-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid #e2e8f0;
}

.node-item:last-child {
    border-bottom: none;
}

.node-name {
    font-weight: 500;
    color: #1e293b;
}

.node-count {
    background: #e2e8f0;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
    color: #475569;
}

.relationship-card {
    background: white;
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    border: 1px solid #e2e8f0;
}

.relationship-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 0.5rem;
}

.relationship-type {
    font-weight: 600;
    color: #1e293b;
    font-family: monospace;
    background: #f1f5f9;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
}

.relationship-path {
    color: #64748b;
    font-size: 0.85rem;
}

.relationship-count {
    margin-left: auto;
    background: #dbeafe;
    color: #1e40af;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
}

.detail-panel {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid #e2e8f0;
    margin-top: 1rem;
}

.detail-panel h4 {
    margin: 0 0 1rem 0;
    color: #1e293b;
    font-size: 1.1rem;
}

.property-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.property-tag {
    background: #f1f5f9;
    color: #475569;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-size: 0.85rem;
    font-family: monospace;
}

.tree-node {
    padding: 0.5rem;
    margin: 0.25rem 0;
    background: white;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
}

.tree-node-name {
    font-weight: 600;
    color: #1e293b;
}

.tree-node-meta {
    font-size: 0.85rem;
    color: #64748b;
}
</style>
""", unsafe_allow_html=True)


# ========================================================================
# MAIN PAGE
# ========================================================================

def main():
    """Main page function."""
    # Header
    st.markdown("""
    <div class="schema-header">
        <h1>📐 Schema Overview</h1>
        <p>Neo4j Knowledge Graph Schema - 17 Node Types, 20+ Relationship Types</p>
    </div>
    """, unsafe_allow_html=True)

    # Connect to Neo4j
    neo4j_client = get_neo4j_client()
    if not neo4j_client:
        st.error("Neo4j connection failed. Please check your database configuration.")
        st.info("Make sure Neo4j is running: `docker-compose up -d`")
        return

    # Fetch schema data
    with st.spinner("Loading schema data..."):
        schema_summary = get_schema_summary(neo4j_client)
        node_counts = schema_summary["node_counts"]
        rel_counts = schema_summary["relationship_counts"]
        rel_details = get_schema_relationship_counts(neo4j_client)

    # Top statistics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <h3>{schema_summary['total_nodes']:,}</h3>
            <p>Total Nodes</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <h3>{schema_summary['total_relationships']:,}</h3>
            <p>Total Relationships</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <h3>{schema_summary['node_type_count']}</h3>
            <p>Node Types</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="stat-card">
            <h3>{schema_summary['relationship_type_count']}</h3>
            <p>Relationship Types</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "📊 Schema Overview",
        "🌳 Intervention Taxonomy",
        "📈 Detailed Statistics"
    ])

    with tab1:
        render_schema_overview(node_counts, rel_details)

    with tab2:
        render_intervention_taxonomy(neo4j_client)

    with tab3:
        render_detailed_statistics(node_counts, rel_counts, rel_details)


def render_schema_overview(node_counts: dict, rel_details: list):
    """Render the schema overview with nodes and relationships."""
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("### Node Types")

        # Core Nodes
        core_nodes = get_nodes_by_category("Core")
        st.markdown("""
        <div class="category-section core">
            <div class="category-title">
                <span style="color: #3b82f6;">●</span> Core Nodes
            </div>
        """, unsafe_allow_html=True)

        for label, info in core_nodes.items():
            count = node_counts.get(label, 0)
            st.markdown(f"""
            <div class="node-item">
                <span class="node-name">{info.icon} {label}</span>
                <span class="node-count">{count:,}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Extended Nodes
        extended_nodes = get_nodes_by_category("Extended")
        st.markdown("""
        <div class="category-section extended">
            <div class="category-title">
                <span style="color: #8b5cf6;">●</span> Extended Nodes
            </div>
        """, unsafe_allow_html=True)

        for label, info in extended_nodes.items():
            count = node_counts.get(label, 0)
            if count > 0:  # Only show nodes with data
                st.markdown(f"""
                <div class="node-item">
                    <span class="node-name">{info.icon} {label}</span>
                    <span class="node-count">{count:,}</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # v7.2 Nodes
        v72_nodes = get_nodes_by_category("v7.2")
        st.markdown("""
        <div class="category-section v72">
            <div class="category-title">
                <span style="color: #f97316;">●</span> v7.2 Extended Nodes
            </div>
        """, unsafe_allow_html=True)

        for label, info in v72_nodes.items():
            count = node_counts.get(label, 0)
            if count > 0:
                st.markdown(f"""
                <div class="node-item">
                    <span class="node-name">{info.icon} {label}</span>
                    <span class="node-count">{count:,}</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### Relationships")

        # Group relationships by source-target
        rel_grouped = {}
        for rel in rel_details:
            key = (rel["source_label"], rel["target_label"])
            if key not in rel_grouped:
                rel_grouped[key] = []
            rel_grouped[key].append({
                "type": rel["rel_type"],
                "count": rel["count"]
            })

        # Sort by count
        sorted_rels = sorted(rel_details, key=lambda x: x["count"], reverse=True)

        # Show top relationships
        for rel in sorted_rels[:20]:
            rel_info = get_relationship_info(rel["rel_type"])
            category = rel_info.category if rel_info else "Other"
            color = rel_info.color if rel_info else "#94a3b8"
            description = rel_info.description if rel_info else ""

            st.markdown(f"""
            <div class="relationship-card">
                <div class="relationship-header">
                    <span class="relationship-type" style="border-left: 3px solid {color}; padding-left: 8px;">
                        {rel['rel_type']}
                    </span>
                    <span class="relationship-path">
                        {rel['source_label']} → {rel['target_label']}
                    </span>
                    <span class="relationship-count">{rel['count']:,}</span>
                </div>
                <div style="color: #64748b; font-size: 0.85rem;">{description}</div>
            </div>
            """, unsafe_allow_html=True)

        if len(sorted_rels) > 20:
            with st.expander(f"Show {len(sorted_rels) - 20} more relationships"):
                for rel in sorted_rels[20:]:
                    st.markdown(f"**{rel['rel_type']}**: {rel['source_label']} → {rel['target_label']} ({rel['count']:,})")


def render_intervention_taxonomy(neo4j_client):
    """Render the intervention IS_A hierarchy."""
    st.markdown("### Intervention Taxonomy (IS_A Hierarchy)")

    hierarchy_data = get_intervention_hierarchy(neo4j_client)

    if not hierarchy_data:
        st.info("No intervention data found in the database.")
        return

    # Build tree structure
    interventions = {}
    for item in hierarchy_data:
        name = item["name"]
        interventions[name] = {
            "name": name,
            "full_name": item.get("full_name") or name,
            "category": item.get("category") or "",
            "is_mis": item.get("is_mis") or False,
            "snomed_code": item.get("snomed_code") or "",
            "parent": item.get("parent_name"),
            "children": item.get("children") or [],
            "paper_count": item.get("paper_count") or 0
        }

    # Find root nodes (no parent)
    roots = [data for name, data in interventions.items() if not data["parent"]]

    # Sort roots by paper count
    roots.sort(key=lambda x: x["paper_count"], reverse=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### Top-Level Categories")
        for root in roots[:10]:
            mis_badge = "🔬 MIS" if root["is_mis"] else ""
            snomed_badge = f"🏷️ {root['snomed_code']}" if root["snomed_code"] else ""

            with st.expander(f"**{root['name']}** ({root['paper_count']} papers) {mis_badge}"):
                st.markdown(f"**Full Name:** {root['full_name']}")
                st.markdown(f"**Category:** {root['category']}")
                if snomed_badge:
                    st.markdown(f"**SNOMED-CT:** {root['snomed_code']}")

                if root["children"]:
                    st.markdown("**Children:**")
                    for child_name in root["children"]:
                        child_data = interventions.get(child_name, {})
                        child_count = child_data.get("paper_count", 0)
                        st.markdown(f"  - {child_name} ({child_count} papers)")

    with col2:
        st.markdown("#### By Paper Count")

        # Sort all interventions by paper count
        sorted_interventions = sorted(
            interventions.values(),
            key=lambda x: x["paper_count"],
            reverse=True
        )

        for item in sorted_interventions[:15]:
            if item["paper_count"] > 0:
                parent_info = f"→ {item['parent']}" if item["parent"] else "(root)"
                st.markdown(f"""
                <div class="tree-node">
                    <div class="tree-node-name">{item['name']}</div>
                    <div class="tree-node-meta">
                        📄 {item['paper_count']} papers | {parent_info}
                    </div>
                </div>
                """, unsafe_allow_html=True)


def render_detailed_statistics(node_counts: dict, rel_counts: dict, rel_details: list):
    """Render detailed statistics dashboard."""
    st.markdown("### Detailed Statistics")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Node Distribution")

        # Prepare data for chart
        import pandas as pd

        node_df = pd.DataFrame([
            {"Type": k, "Count": v}
            for k, v in node_counts.items()
            if v > 0
        ])

        if not node_df.empty:
            node_df = node_df.sort_values("Count", ascending=True)
            st.bar_chart(node_df.set_index("Type"), horizontal=True)

        # Table view
        with st.expander("View as Table"):
            st.dataframe(
                node_df.sort_values("Count", ascending=False),
                use_container_width=True,
                hide_index=True
            )

    with col2:
        st.markdown("#### Relationship Distribution")

        rel_df = pd.DataFrame([
            {"Type": k, "Count": v}
            for k, v in rel_counts.items()
            if v > 0
        ])

        if not rel_df.empty:
            rel_df = rel_df.sort_values("Count", ascending=True)
            st.bar_chart(rel_df.set_index("Type"), horizontal=True)

        with st.expander("View as Table"):
            st.dataframe(
                rel_df.sort_values("Count", ascending=False),
                use_container_width=True,
                hide_index=True
            )

    st.markdown("---")
    st.markdown("#### Relationship Paths")

    # Group by path pattern
    path_counts = {}
    for rel in rel_details:
        path = f"{rel['source_label']} → {rel['target_label']}"
        if path not in path_counts:
            path_counts[path] = {"count": 0, "types": []}
        path_counts[path]["count"] += rel["count"]
        path_counts[path]["types"].append(rel["rel_type"])

    # Sort and display
    sorted_paths = sorted(path_counts.items(), key=lambda x: x[1]["count"], reverse=True)

    col1, col2, col3 = st.columns(3)
    cols = [col1, col2, col3]

    for idx, (path, data) in enumerate(sorted_paths[:15]):
        with cols[idx % 3]:
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; border: 1px solid #e2e8f0;">
                <div style="font-weight: 600; color: #1e293b;">{path}</div>
                <div style="color: #64748b; font-size: 0.85rem;">
                    {data['count']:,} relationships<br>
                    Types: {', '.join(data['types'][:3])}{'...' if len(data['types']) > 3 else ''}
                </div>
            </div>
            """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
