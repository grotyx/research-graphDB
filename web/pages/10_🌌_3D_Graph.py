"""3D Interactive Graph Visualization.

WebGL-powered 3D force-directed graph using 3d-force-graph library.
Features: orbit rotation, zoom, node hover highlight, click details.
"""

import json
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Project path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.graph_utils import get_neo4j_client

st.set_page_config(
    page_title="3D Graph - Spine GraphRAG",
    page_icon="🌌",
    layout="wide"
)

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

# ═══════════════════════════════════════════════════════════════
# NODE COLOR SCHEME
# ═══════════════════════════════════════════════════════════════

NODE_COLORS = {
    "Paper": "#22c55e",
    "Intervention": "#3b82f6",
    "Outcome": "#f97316",
    "Pathology": "#ef4444",
    "Complication": "#dc2626",
    "Anatomy": "#8b5cf6",
    "PatientCohort": "#06b6d4",
    "FollowUp": "#84cc16",
    "Cost": "#eab308",
    "QualityMetric": "#ec4899",
    "Chunk": "#64748b",
}

EDGE_COLORS = {
    "improved": "#22c55e",
    "worsened": "#ef4444",
    "unchanged": "#94a3b8",
    "IS_A": "#a78bfa",
    "TREATS": "#f472b6",
    "default": "#475569",
}

# Allowlist for Cypher label interpolation (CA-001 fix)
_ALLOWED_ENTITY_TYPES = {"Intervention", "Pathology", "Outcome", "Anatomy"}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _safe_query(client, cypher: str, params: dict) -> list[dict]:
    """Run Neo4j query with error handling (CA-003 fix)."""
    try:
        return client.run_query(cypher, params)
    except Exception as e:
        st.error(f"Neo4j query error: {e}")
        return []


def _build_node(node_id: str, label: str, group: str, val: int = 3,
                desc: str = "", category: str = "") -> dict:
    """Build a node dict (CA-007 fix: shared helper)."""
    return {
        "id": node_id,
        "label": label[:40] + "..." if len(label) > 40 else label,
        "group": group,
        "val": val,
        "desc": desc,
        **({"category": category} if category else {}),
    }


# ═══════════════════════════════════════════════════════════════
# DATA LOADERS (CA-005: @st.cache_data where possible)
# ═══════════════════════════════════════════════════════════════

def load_intervention_outcome(client, sig_only: bool = False,
                               intervention: str = None,
                               pathology: str = None,
                               limit: int = 200) -> dict:
    """Load Intervention → Outcome AFFECTS graph."""
    where_parts = []
    params = {"limit": limit}

    if sig_only:
        where_parts.append("r.is_significant = true")
    if intervention:
        where_parts.append("i.name = $intervention")
        params["intervention"] = intervention
    if pathology:
        where_parts.append(
            "EXISTS { MATCH (p:Paper)-[:STUDIES]->(:Pathology {name: $pathology}) "
            "MATCH (p)-[:INVESTIGATES]->(i) }"
        )
        params["pathology"] = pathology

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    cypher = f"""
    MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
    {where_clause}
    OPTIONAL MATCH (paper:Paper)-[:INVESTIGATES]->(i)
    WITH i, o, r, count(DISTINCT paper) AS paper_count
    RETURN i.name AS i_name, i.category AS i_cat,
           o.name AS o_name, o.type AS o_type,
           r.direction AS direction, r.p_value AS p_value,
           r.is_significant AS is_sig, r.effect_size AS effect_size,
           paper_count
    LIMIT $limit
    """

    records = _safe_query(client, cypher, params)

    nodes, edges, seen = [], [], set()

    for rec in records:
        i_name, o_name = rec["i_name"], rec["o_name"]
        pc = rec["paper_count"] or 1

        if i_name not in seen:
            nodes.append(_build_node(
                i_name, i_name, "Intervention",
                val=2 + min(pc, 15),
                desc=f"Category: {rec['i_cat'] or 'N/A'}\nPapers: {pc}",
                category=rec["i_cat"] or ""
            ))
            seen.add(i_name)

        if o_name not in seen:
            nodes.append(_build_node(
                o_name, o_name, "Outcome", val=3,
                desc=f"Type: {rec['o_type'] or 'N/A'}",
                category=rec["o_type"] or ""
            ))
            seen.add(o_name)

        direction = rec["direction"] or "unchanged"
        p_val = rec["p_value"]
        effect = rec["effect_size"]
        desc_parts = [f"Direction: {direction}"]
        if p_val is not None:
            desc_parts.append(f"p={p_val:.4f}")
        if effect is not None:
            desc_parts.append(f"ES={effect:.2f}")
        if rec["is_sig"]:
            desc_parts.append("Significant")

        edges.append({
            "source": i_name, "target": o_name,
            "label": direction,
            "color": EDGE_COLORS.get(direction, EDGE_COLORS["default"]),
            "width": 3 if rec["is_sig"] else 1,
            "desc": " | ".join(desc_parts)
        })

    return {"nodes": nodes, "links": edges}


def load_ontology(client, entity_type: str = "All", limit: int = 300) -> dict:
    """Load IS_A ontology hierarchy."""
    params = {"limit": limit}

    # CA-001 fix: allowlist guard instead of f-string interpolation
    if entity_type != "All":
        if entity_type not in _ALLOWED_ENTITY_TYPES:
            st.error(f"Invalid entity type: {entity_type}")
            return {"nodes": [], "links": []}
        type_filter = f"WHERE '{entity_type}' IN labels(child) AND '{entity_type}' IN labels(parent)"
    else:
        type_filter = ""

    cypher = f"""
    MATCH (child)-[r:IS_A]->(parent)
    {type_filter}
    RETURN child.name AS child_name, labels(child)[0] AS child_type,
           parent.name AS parent_name, labels(parent)[0] AS parent_type
    LIMIT $limit
    """

    records = _safe_query(client, cypher, params)

    nodes, edges, seen = [], [], set()

    for rec in records:
        cn, ct = rec["child_name"], rec["child_type"]
        pn, pt = rec["parent_name"], rec["parent_type"]

        if cn not in seen:
            nodes.append(_build_node(cn, cn, ct, val=3, desc=f"Type: {ct}"))
            seen.add(cn)

        if pn not in seen:
            nodes.append(_build_node(pn, pn, pt, val=5, desc=f"Type: {pt} (Parent)"))
            seen.add(pn)

        edges.append({
            "source": cn, "target": pn,
            "label": "IS_A",
            "color": EDGE_COLORS["IS_A"],
            "width": 2,
            "desc": f"{cn} IS_A {pn}"
        })

    return {"nodes": nodes, "links": edges}


def load_full_graph(client, limit: int = 150) -> dict:
    """Load full graph: Paper → entities + AFFECTS + IS_A."""
    cypher = """
    MATCH (p:Paper)-[r]->(target)
    WHERE type(r) IN ['STUDIES', 'INVESTIGATES', 'INVOLVES']
    WITH p, target, type(r) AS rel_type
    LIMIT $limit
    RETURN p.paper_id AS src_id, p.title AS src_title,
           COALESCE(target.name, target.paper_id) AS tgt_id,
           COALESCE(target.name, target.title) AS tgt_label,
           labels(target)[0] AS tgt_type,
           rel_type
    """
    records = _safe_query(client, cypher, {"limit": limit})

    nodes, edges, seen = [], [], set()

    for rec in records:
        sid = rec["src_id"]
        tid = rec["tgt_id"]
        if not tid:
            continue

        if sid not in seen:
            title = rec["src_title"] or sid
            nodes.append(_build_node(sid, title, "Paper", val=4, desc=title))
            seen.add(sid)

        if tid not in seen:
            lbl = rec["tgt_label"] or str(tid)
            nodes.append(_build_node(
                tid, lbl, rec["tgt_type"] or "Other", val=3,
                desc=f"{rec['tgt_type']}: {lbl}"
            ))
            seen.add(tid)

        edges.append({
            "source": sid, "target": tid,
            "label": rec["rel_type"],
            "color": EDGE_COLORS["default"],
            "width": 1,
            "desc": rec["rel_type"]
        })

    # Add AFFECTS edges
    affects = """
    MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
    RETURN i.name AS src, o.name AS tgt,
           r.direction AS dir, r.is_significant AS is_sig
    LIMIT $limit
    """
    for rec in _safe_query(client, affects, {"limit": limit}):
        s, t = rec["src"], rec["tgt"]
        if s not in seen:
            nodes.append(_build_node(s, s, "Intervention", val=3, desc=s))
            seen.add(s)
        if t not in seen:
            nodes.append(_build_node(t, t, "Outcome", val=3, desc=t))
            seen.add(t)
        d = rec["dir"] or "unchanged"
        edges.append({
            "source": s, "target": t, "label": d,
            "color": EDGE_COLORS.get(d, EDGE_COLORS["default"]),
            "width": 3 if rec["is_sig"] else 1,
            "desc": f"AFFECTS ({d})"
        })

    return {"nodes": nodes, "links": edges}


def load_paper_entity_network(client, limit: int = 100) -> dict:
    """Load Paper → Intervention/Pathology network."""
    cypher = """
    MATCH (p:Paper)-[r]->(target)
    WHERE type(r) IN ['INVESTIGATES', 'STUDIES']
    WITH p, target, type(r) AS rel_type
    LIMIT $limit
    RETURN p.paper_id AS paper_id, p.title AS title,
           p.year AS year, p.evidence_level AS evidence_level,
           COALESCE(target.name, target.paper_id) AS target_id,
           COALESCE(target.name, target.title) AS target_label,
           labels(target)[0] AS target_type,
           rel_type
    """
    records = _safe_query(client, cypher, {"limit": limit})

    nodes, edges, seen = [], [], set()

    for rec in records:
        pid = rec["paper_id"]
        tid = rec["target_id"]
        if not tid:
            continue

        if pid not in seen:
            title = rec["title"] or pid
            year = rec["year"] or ""
            ev = rec["evidence_level"] or ""
            nodes.append(_build_node(
                pid, title, "Paper", val=5,
                desc=f"{title}\nYear: {year}\nEvidence: {ev}"
            ))
            seen.add(pid)

        if tid not in seen:
            lbl = rec["target_label"] or str(tid)
            nodes.append(_build_node(
                tid, lbl, rec["target_type"] or "Other", val=3,
                desc=f"{rec['target_type']}: {lbl}"
            ))
            seen.add(tid)

        edges.append({
            "source": pid, "target": tid,
            "label": rec["rel_type"],
            "color": EDGE_COLORS["default"],
            "width": 1,
            "desc": rec["rel_type"]
        })

    return {"nodes": nodes, "links": edges}


# ═══════════════════════════════════════════════════════════════
# 3D FORCE GRAPH RENDERER
# ═══════════════════════════════════════════════════════════════

def render_3d_graph(graph_data: dict, height: int = 800,
                     bg_color: str = "#0f172a",
                     show_labels: bool = True,
                     link_particles: bool = True,
                     dag_mode: str = "none") -> None:
    """Render 3D force-directed graph using 3d-force-graph (WebGL)."""

    node_colors_js = json.dumps(NODE_COLORS)
    nodes_json = json.dumps(graph_data["nodes"], ensure_ascii=False)
    links_json = json.dumps(graph_data["links"], ensure_ascii=False)

    dag_config = ""
    if dag_mode != "none":
        dag_config = f'Graph.dagMode("{dag_mode}").dagLevelDistance(40);'

    label_config = """
        Graph.nodeLabel(node => {
            let s = '<b>' + node.label + '</b>';
            s += '<br>Type: ' + node.group;
            if (node.desc) s += '<br>' + node.desc.replace(/\\n/g, '<br>');
            return s;
        });
    """ if show_labels else ""

    particle_config = """
        Graph.linkDirectionalParticles(link => link.width > 1 ? 4 : 1)
             .linkDirectionalParticleWidth(link => Math.max(1, link.width * 0.8))
             .linkDirectionalParticleSpeed(0.004)
             .linkDirectionalParticleColor(link => link.color || '#475569');
    """ if link_particles else ""

    # CA-013 fix: Load SpriteText BEFORE 3d-force-graph uses it
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: {bg_color}; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
        #graph {{ width: 100%; height: {height}px; }}

        /* Info panel */
        #info {{
            position: absolute; top: 16px; right: 16px;
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(100, 116, 139, 0.4);
            backdrop-filter: blur(12px);
            border-radius: 12px; padding: 16px 20px;
            color: #e2e8f0; font-size: 13px;
            max-width: 320px; display: none;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            z-index: 200;
        }}
        #info h3 {{ color: #f1f5f9; font-size: 15px; margin-bottom: 8px; font-weight: 600; }}
        #info .row {{ display: flex; justify-content: space-between; margin: 4px 0; }}
        #info .lbl {{ color: #94a3b8; }}
        #info .val {{ color: #f1f5f9; font-weight: 500; }}
        #info-close {{
            position: absolute; top: 8px; right: 12px;
            background: none; border: none; color: #94a3b8;
            cursor: pointer; font-size: 16px;
        }}
        #info-close:hover {{ color: white; }}

        /* Legend */
        #legend {{
            position: absolute; bottom: 16px; left: 16px;
            background: rgba(15, 23, 42, 0.88);
            border: 1px solid rgba(100, 116, 139, 0.3);
            backdrop-filter: blur(12px);
            border-radius: 12px; padding: 14px 18px;
            z-index: 200; max-width: 240px;
        }}
        #legend h4 {{ color: #e2e8f0; font-size: 12px; margin-bottom: 10px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }}
        .leg-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; color: #cbd5e1; }}
        .leg-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}

        /* Stats badge */
        #stats {{
            position: absolute; top: 16px; left: 16px;
            background: rgba(15, 23, 42, 0.88);
            border: 1px solid rgba(100, 116, 139, 0.3);
            backdrop-filter: blur(12px);
            border-radius: 10px; padding: 10px 16px;
            color: #94a3b8; font-size: 12px;
            z-index: 200;
        }}
        #stats b {{ color: #e2e8f0; font-size: 18px; }}

        /* Controls */
        #controls {{
            position: absolute; bottom: 16px; right: 16px;
            display: flex; gap: 8px; z-index: 200;
        }}
        .ctrl-btn {{
            padding: 8px 14px;
            background: rgba(15, 23, 42, 0.88);
            border: 1px solid rgba(100, 116, 139, 0.3);
            border-radius: 8px;
            color: #cbd5e1; font-size: 12px;
            cursor: pointer; transition: all 0.2s;
        }}
        .ctrl-btn:hover {{ background: rgba(59, 130, 246, 0.3); border-color: #3b82f6; color: white; }}
        .ctrl-btn.active {{ background: rgba(59, 130, 246, 0.4); border-color: #3b82f6; color: white; }}
    </style>
    </head>
    <body>
    <div id="graph"></div>

    <div id="stats">
        <b id="node-count">0</b> nodes &nbsp;&middot;&nbsp; <b id="edge-count">0</b> links
    </div>

    <div id="legend">
        <h4>Node Types</h4>
        <div id="legend-items"></div>
    </div>

    <div id="info">
        <button id="info-close" onclick="document.getElementById('info').style.display='none'">&times;</button>
        <h3 id="info-title"></h3>
        <div id="info-body"></div>
    </div>

    <div id="controls">
        <button class="ctrl-btn" onclick="resetCamera()">Reset View</button>
        <button class="ctrl-btn" id="btn-rotate" onclick="toggleRotate()">Auto Rotate</button>
        <button class="ctrl-btn" id="btn-labels" onclick="toggleLabels()">Labels</button>
    </div>

    <!-- CA-013 fix: Load SpriteText BEFORE it is used -->
    <script src="https://unpkg.com/three-spritetext@1.8.2/dist/three-spritetext.min.js"></script>
    <script src="https://unpkg.com/3d-force-graph@1.73.3/dist/3d-force-graph.min.js"></script>
    <script>
    const NODE_COLORS = {node_colors_js};
    const graphData = {{
        nodes: {nodes_json},
        links: {links_json}
    }};

    // Update stats
    document.getElementById('node-count').textContent = graphData.nodes.length;
    document.getElementById('edge-count').textContent = graphData.links.length;

    // Build legend from actual groups
    const groups = [...new Set(graphData.nodes.map(n => n.group))].sort();
    const legendEl = document.getElementById('legend-items');
    groups.forEach(g => {{
        const color = NODE_COLORS[g] || '#94a3b8';
        legendEl.innerHTML += '<div class="leg-item"><div class="leg-dot" style="background:' + color + '"></div>' + g + '</div>';
    }});

    // Highlight state
    let highlightNodes = new Set();
    let highlightLinks = new Set();
    let hoverNode = null;
    let showLabels = true;
    let autoRotate = false;

    // SpriteText helper
    function makeSpriteLabel(text) {{
        if (typeof SpriteText === 'undefined' || !showLabels) return undefined;
        const sprite = new SpriteText(text || '');
        sprite.color = '#cbd5e1';
        sprite.textHeight = 2.5;
        sprite.backgroundColor = 'rgba(15,23,42,0.6)';
        sprite.padding = 1;
        sprite.borderRadius = 2;
        return sprite;
    }}

    // Create graph
    const container = document.getElementById('graph');
    const Graph = ForceGraph3D()(container)
        .graphData(graphData)
        .backgroundColor('{bg_color}')
        .width(container.clientWidth)
        .height({height})
        // Nodes
        .nodeVal(n => n.val || 3)
        .nodeColor(n => {{
            if (highlightNodes.size > 0) {{
                return highlightNodes.has(n) ? NODE_COLORS[n.group] || '#94a3b8' : 'rgba(50,50,70,0.3)';
            }}
            return NODE_COLORS[n.group] || '#94a3b8';
        }})
        .nodeOpacity(0.92)
        .nodeResolution(16)
        // Links
        .linkColor(link => {{
            if (highlightLinks.size > 0) {{
                return highlightLinks.has(link) ? (link.color || '#475569') : 'rgba(50,50,70,0.1)';
            }}
            return link.color || '#475569';
        }})
        .linkWidth(link => {{
            if (highlightLinks.has(link)) return Math.max(link.width || 1, 2) * 1.5;
            return link.width || 0.5;
        }})
        .linkOpacity(0.6)
        .linkDirectionalArrowLength(4)
        .linkDirectionalArrowRelPos(1)
        // Hover highlight
        .onNodeHover(node => {{
            container.style.cursor = node ? 'pointer' : 'default';
            highlightNodes.clear();
            highlightLinks.clear();
            if (node) {{
                highlightNodes.add(node);
                graphData.links.forEach(link => {{
                    const src = typeof link.source === 'object' ? link.source : graphData.nodes.find(n => n.id === link.source);
                    const tgt = typeof link.target === 'object' ? link.target : graphData.nodes.find(n => n.id === link.target);
                    if (src === node || tgt === node) {{
                        highlightNodes.add(src);
                        highlightNodes.add(tgt);
                        highlightLinks.add(link);
                    }}
                }});
            }}
            hoverNode = node;
            Graph.nodeColor(Graph.nodeColor())
                 .linkColor(Graph.linkColor())
                 .linkWidth(Graph.linkWidth());
        }})
        // Click: show info
        .onNodeClick(node => {{
            const info = document.getElementById('info');
            document.getElementById('info-title').textContent = node.label || node.id;
            let html = '<div class="row"><span class="lbl">Type</span><span class="val">' + node.group + '</span></div>';
            if (node.category) html += '<div class="row"><span class="lbl">Category</span><span class="val">' + node.category + '</span></div>';
            if (node.desc) {{
                node.desc.split('\\n').forEach(line => {{
                    const parts = line.split(': ');
                    if (parts.length === 2) {{
                        html += '<div class="row"><span class="lbl">' + parts[0] + '</span><span class="val">' + parts[1] + '</span></div>';
                    }}
                }});
            }}
            let connections = 0;
            graphData.links.forEach(link => {{
                const sid = typeof link.source === 'object' ? link.source.id : link.source;
                const tid = typeof link.target === 'object' ? link.target.id : link.target;
                if (sid === node.id || tid === node.id) connections++;
            }});
            html += '<div class="row"><span class="lbl">Connections</span><span class="val">' + connections + '</span></div>';
            document.getElementById('info-body').innerHTML = html;
            info.style.display = 'block';

            const distance = 120;
            const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
            Graph.cameraPosition(
                {{ x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }},
                node,
                1500
            );
        }})
        .onBackgroundClick(() => {{
            document.getElementById('info').style.display = 'none';
            highlightNodes.clear();
            highlightLinks.clear();
            Graph.nodeColor(Graph.nodeColor())
                 .linkColor(Graph.linkColor())
                 .linkWidth(Graph.linkWidth());
        }});

    // Node labels (3D text sprites) — SpriteText is already loaded above
    if ({str(show_labels).lower()}) {{
        Graph.nodeThreeObject(node => makeSpriteLabel(node.label))
             .nodeThreeObjectExtend(true);
    }}

    // Tooltip
    {label_config}

    // Link particles
    {particle_config}

    // DAG mode
    {dag_config}

    // Warm up
    Graph.d3Force('charge').strength(-80);
    Graph.d3Force('link').distance(40);

    // Controls
    function resetCamera() {{
        Graph.cameraPosition({{ x: 0, y: 0, z: 300 }}, {{ x: 0, y: 0, z: 0 }}, 1000);
    }}

    function toggleRotate() {{
        autoRotate = !autoRotate;
        const btn = document.getElementById('btn-rotate');
        btn.classList.toggle('active', autoRotate);

        if (autoRotate) {{
            let angle = 0;
            (function rotate() {{
                if (!autoRotate) return;
                angle += 0.002;
                const dist = 300;
                Graph.cameraPosition({{
                    x: dist * Math.sin(angle),
                    y: 50,
                    z: dist * Math.cos(angle)
                }});
                requestAnimationFrame(rotate);
            }})();
        }}
    }}

    function toggleLabels() {{
        showLabels = !showLabels;
        const btn = document.getElementById('btn-labels');
        btn.classList.toggle('active', showLabels);
        Graph.nodeThreeObject(node => makeSpriteLabel(node.label))
             .nodeThreeObjectExtend(true);
    }}

    // Handle resize
    window.addEventListener('resize', () => {{
        Graph.width(container.clientWidth);
    }});
    </script>
    </body>
    </html>
    """

    components.html(html, height=height + 10, scrolling=False)


# ═══════════════════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════════════════

def main():
    # Header
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #312e81 100%);
        color: white; padding: 1.5rem 2rem; border-radius: 16px;
        margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    ">
        <h1 style="margin:0; font-size:1.75rem; font-weight:700;">
            3D Knowledge Graph
        </h1>
        <p style="margin:0.4rem 0 0 0; opacity:0.85; font-size:1rem;">
            WebGL 3D force-directed graph &mdash; drag to rotate, scroll to zoom, click nodes for details
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Neo4j connection
    neo4j_client = get_neo4j_client()
    if neo4j_client is None:
        st.error("Neo4j not connected. Run `docker-compose up -d`")
        return

    # Sidebar controls
    st.sidebar.markdown("### 3D Graph Settings")

    view_mode = st.sidebar.selectbox(
        "View Mode",
        ["Intervention → Outcome", "Ontology (IS_A)", "Full Graph", "Paper Network"],
        index=0
    )

    # View-specific filters
    sig_only = False
    intervention_filter = None
    pathology_filter = None
    entity_type_filter = "All"
    limit = 200

    if view_mode == "Intervention → Outcome":
        sig_only = st.sidebar.checkbox("Significant only (p<0.05)", value=False)

        i_records = _safe_query(
            neo4j_client,
            "MATCH (i:Intervention) RETURN DISTINCT i.name AS name ORDER BY name LIMIT 100", {}
        )
        interventions = ["All"] + [r["name"] for r in i_records]
        sel = st.sidebar.selectbox("Intervention", interventions, index=0)
        intervention_filter = sel if sel != "All" else None

        p_records = _safe_query(
            neo4j_client,
            "MATCH (p:Pathology) RETURN DISTINCT p.name AS name ORDER BY name LIMIT 50", {}
        )
        pathologies = ["All"] + [r["name"] for r in p_records]
        sel_p = st.sidebar.selectbox("Pathology", pathologies, index=0)
        pathology_filter = sel_p if sel_p != "All" else None

    elif view_mode == "Ontology (IS_A)":
        entity_type_filter = st.sidebar.selectbox(
            "Entity Type",
            ["All", "Intervention", "Pathology", "Outcome", "Anatomy"]
        )

    limit = st.sidebar.slider("Max nodes/edges", 50, 500, 200, 50)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Display")

    bg_color = st.sidebar.selectbox(
        "Background",
        ["Dark (#0f172a)", "Midnight (#020617)", "Navy (#1e1b4b)", "Black (#000000)", "Light (#f8fafc)"],
        index=0
    )
    bg_hex = bg_color.split("(")[1].rstrip(")")

    show_labels = st.sidebar.checkbox("Show node labels", value=True)
    link_particles = st.sidebar.checkbox("Animated link particles", value=True)

    dag_mode = st.sidebar.selectbox(
        "DAG Layout",
        ["none", "td", "bu", "lr", "rl", "radialout", "radialin"],
        format_func=lambda x: {
            "none": "Free (physics)",
            "td": "Top → Down",
            "bu": "Bottom → Up",
            "lr": "Left → Right",
            "rl": "Right → Left",
            "radialout": "Radial Out",
            "radialin": "Radial In"
        }[x]
    )

    graph_height = st.sidebar.slider("Graph height", 500, 1000, 800, 50)

    # Load data
    with st.spinner("Loading graph data..."):
        if view_mode == "Intervention → Outcome":
            data = load_intervention_outcome(
                neo4j_client, sig_only=sig_only,
                intervention=intervention_filter,
                pathology=pathology_filter, limit=limit
            )
        elif view_mode == "Ontology (IS_A)":
            data = load_ontology(neo4j_client, entity_type=entity_type_filter, limit=limit)
        elif view_mode == "Full Graph":
            data = load_full_graph(neo4j_client, limit=limit)
        else:
            data = load_paper_entity_network(neo4j_client, limit=limit)

    if not data["nodes"]:
        st.warning("No data found for the selected view/filters.")
        return

    # Render 3D graph
    render_3d_graph(
        data,
        height=graph_height,
        bg_color=bg_hex,
        show_labels=show_labels,
        link_particles=link_particles,
        dag_mode=dag_mode
    )

    # Stats below graph
    n_nodes = len(data["nodes"])
    n_edges = len(data["links"])
    groups = {}
    for n in data["nodes"]:
        g = n.get("group", "Other")
        groups[g] = groups.get(g, 0) + 1

    cols = st.columns(min(len(groups) + 2, 8))
    cols[0].metric("Nodes", n_nodes)
    cols[1].metric("Links", n_edges)
    for i, (g, c) in enumerate(sorted(groups.items(), key=lambda x: -x[1])):
        if i + 2 < len(cols):
            cols[i + 2].metric(g, c)


if __name__ == "__main__":
    main()
