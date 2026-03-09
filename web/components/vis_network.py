"""Vis-Network Component for Streamlit.

High-quality graph visualization using vis-network.js library.
Based on: https://github.com/gongwon-nayeon/graphrag-demo

Features:
- Interactive physics-based layout
- Node highlighting on search
- Hover tooltips with full information
- Click to expand node details
- Zoom/pan controls
"""

import json
import streamlit.components.v1 as components
from typing import Optional


def vis_network_graph(
    nodes: list[dict],
    edges: list[dict],
    height: int = 700,
    highlight_nodes: list[str] = None,
    physics_enabled: bool = True,
    layout_type: str = "physics",  # physics, hierarchical, radial
    node_colors: dict = None,
    on_node_click: bool = True,
) -> None:
    """Render interactive graph using vis-network.js.

    Args:
        nodes: List of node dicts with {id, label, group, title, ...}
        edges: List of edge dicts with {from, to, label, color, ...}
        height: Graph container height in pixels
        highlight_nodes: List of node IDs to highlight (search results)
        physics_enabled: Enable physics simulation
        layout_type: Layout algorithm (physics, hierarchical, radial)
        node_colors: Custom color mapping {group: color}
        on_node_click: Show node details on click
    """
    # Default color scheme (Spine GraphRAG domain)
    default_colors = {
        "Paper": "#22c55e",          # Green
        "Intervention": "#3b82f6",   # Blue
        "Outcome": "#f97316",        # Orange
        "Pathology": "#ef4444",      # Red
        "Complication": "#dc2626",   # Dark Red
        "Anatomy": "#8b5cf6",        # Purple
        "PatientCohort": "#06b6d4",  # Cyan
        "FollowUp": "#84cc16",       # Lime
        "Cost": "#eab308",           # Yellow
        "QualityMetric": "#ec4899",  # Pink
        "Query": "#1e293b",          # Dark (Search query node)
        "Chunk": "#a1a1aa",          # Zinc
        "default": "#94a3b8",        # Gray
    }

    colors = {**default_colors, **(node_colors or {})}
    highlight_set = set(highlight_nodes or [])

    # Build vis.js compatible nodes
    vis_nodes = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        group = node.get("group", "default")
        label = node.get("label", node_id)
        title = node.get("title", label)  # Tooltip

        # Base node styling
        color = colors.get(group, colors["default"])
        is_highlighted = node_id in highlight_set

        vis_node = {
            "id": node_id,
            "label": label[:30] + "..." if len(label) > 30 else label,
            "title": title,
            "group": group,
            "color": {
                "background": color if not is_highlighted else "#fef08a",
                "border": "#1e293b" if is_highlighted else color,
                "highlight": {
                    "background": "#fef08a",
                    "border": "#ef4444"
                },
                "hover": {
                    "background": color,
                    "border": "#1e40af"
                }
            },
            "borderWidth": 4 if is_highlighted else 2,
            "size": 30 if is_highlighted else 20,
            "font": {
                "size": 14 if is_highlighted else 11,
                "color": "#1e293b"
            },
            "shadow": True if is_highlighted else False,
        }

        # Add custom properties
        for key in ["year", "evidence_level", "category", "p_value", "effect_size"]:
            if key in node:
                vis_node[key] = node[key]

        vis_nodes.append(vis_node)

    # Build vis.js compatible edges
    vis_edges = []
    for edge in edges:
        from_id = str(edge.get("from", edge.get("source", "")))
        to_id = str(edge.get("to", edge.get("target", "")))
        label = edge.get("label", edge.get("type", ""))

        # Edge styling based on type
        edge_color = "#94a3b8"  # Default gray
        width = 1
        dashes = False

        direction = edge.get("direction", "")
        if direction == "improved":
            edge_color = "#22c55e"
            width = 2
        elif direction == "worsened":
            edge_color = "#ef4444"
            width = 2

        if edge.get("is_significant"):
            width = 3
        else:
            dashes = True

        # Highlight edges connected to highlighted nodes
        is_edge_highlighted = from_id in highlight_set or to_id in highlight_set

        vis_edge = {
            "from": from_id,
            "to": to_id,
            "label": label,
            "color": {
                "color": "#ef4444" if is_edge_highlighted else edge_color,
                "highlight": "#ef4444",
                "hover": "#3b82f6"
            },
            "width": width + (2 if is_edge_highlighted else 0),
            "dashes": dashes and not is_edge_highlighted,
            "arrows": {
                "to": {
                    "enabled": True,
                    "scaleFactor": 0.5
                }
            },
            "smooth": {
                "enabled": True,
                "type": "continuous"
            },
            "font": {
                "size": 10,
                "color": "#64748b",
                "strokeWidth": 3,
                "strokeColor": "#ffffff"
            }
        }

        vis_edges.append(vis_edge)

    # Layout options
    if layout_type == "hierarchical":
        layout_options = """
        layout: {
            hierarchical: {
                enabled: true,
                direction: 'UD',
                sortMethod: 'hubsize',
                nodeSpacing: 150,
                levelSeparation: 200
            }
        },
        """
    elif layout_type == "radial":
        layout_options = """
        layout: {
            improvedLayout: true,
            hierarchical: false
        },
        """
    else:
        layout_options = """
        layout: {
            improvedLayout: true,
            hierarchical: false
        },
        """

    # Physics options
    physics_options = """
    physics: {
        enabled: true,
        barnesHut: {
            gravitationalConstant: -8000,
            centralGravity: 0.3,
            springConstant: 0.04,
            springLength: 120,
            damping: 0.09
        },
        stabilization: {
            enabled: true,
            iterations: 200,
            updateInterval: 25
        }
    },
    """ if physics_enabled else """
    physics: {
        enabled: false
    },
    """

    # Generate HTML with vis-network.js
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #fafbfc;
            }}
            #graph-container {{
                width: 100%;
                height: {height}px;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                background: white;
                position: relative;
            }}
            #mynetwork {{
                width: 100%;
                height: 100%;
            }}
            #legend {{
                position: absolute;
                top: 12px;
                left: 12px;
                background: rgba(255,255,255,0.95);
                padding: 12px 16px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                z-index: 100;
                max-width: 200px;
            }}
            #legend h4 {{
                font-size: 12px;
                font-weight: 600;
                color: #1e293b;
                margin-bottom: 8px;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 4px;
                font-size: 11px;
                color: #475569;
            }}
            .legend-dot {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
                flex-shrink: 0;
            }}
            #node-info {{
                position: absolute;
                bottom: 12px;
                right: 12px;
                background: rgba(255,255,255,0.95);
                padding: 16px;
                border-radius: 8px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.15);
                z-index: 100;
                max-width: 320px;
                display: none;
                border-left: 4px solid #3b82f6;
            }}
            #node-info h3 {{
                font-size: 14px;
                font-weight: 600;
                color: #1e293b;
                margin-bottom: 8px;
            }}
            #node-info .info-row {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 4px;
                font-size: 12px;
            }}
            #node-info .info-label {{
                color: #64748b;
            }}
            #node-info .info-value {{
                color: #1e293b;
                font-weight: 500;
            }}
            #controls {{
                position: absolute;
                top: 12px;
                right: 12px;
                display: flex;
                gap: 8px;
                z-index: 100;
            }}
            .control-btn {{
                padding: 8px 12px;
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
                color: #475569;
                transition: all 0.2s;
            }}
            .control-btn:hover {{
                background: #f1f5f9;
                border-color: #3b82f6;
                color: #3b82f6;
            }}
            #loading {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 14px;
                color: #64748b;
            }}
            .highlight-badge {{
                position: absolute;
                top: 12px;
                left: 50%;
                transform: translateX(-50%);
                background: #fef3c7;
                border: 1px solid #f59e0b;
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 12px;
                color: #92400e;
                z-index: 100;
                display: {'block' if highlight_nodes else 'none'};
            }}
        </style>
    </head>
    <body>
        <div id="graph-container">
            <div id="loading">Loading graph...</div>

            <div id="mynetwork"></div>

            <div id="legend">
                <h4>Node Types</h4>
                {"".join([f'<div class="legend-item"><div class="legend-dot" style="background:{c}"></div>{g}</div>' for g, c in colors.items() if g != "default"])}
            </div>

            <div class="highlight-badge">
                {len(highlight_set)} nodes highlighted
            </div>

            <div id="controls">
                <button class="control-btn" onclick="network.fit()">Fit View</button>
                <button class="control-btn" onclick="togglePhysics()">Toggle Physics</button>
                <button class="control-btn" onclick="resetHighlight()">Reset</button>
            </div>

            <div id="node-info">
                <h3 id="info-title">Node Info</h3>
                <div id="info-content"></div>
            </div>
        </div>

        <script>
            // Debug info
            console.log('vis-network: Initializing graph...');
            console.log('vis-network: Node count:', {len(vis_nodes)});
            console.log('vis-network: Edge count:', {len(vis_edges)});

            // Data
            const nodes = new vis.DataSet({json.dumps(vis_nodes)});
            const edges = new vis.DataSet({json.dumps(vis_edges)});

            console.log('vis-network: DataSets created');

            // Options
            const options = {{
                {layout_options}
                {physics_options}
                interaction: {{
                    hover: true,
                    hoverConnectedEdges: true,
                    selectConnectedEdges: true,
                    tooltipDelay: 100,
                    zoomView: true,
                    dragView: true,
                    navigationButtons: false,
                    keyboard: {{
                        enabled: true,
                        bindToWindow: false
                    }}
                }},
                nodes: {{
                    shape: 'dot',
                    scaling: {{
                        min: 15,
                        max: 40
                    }},
                    font: {{
                        face: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif'
                    }}
                }},
                edges: {{
                    scaling: {{
                        min: 1,
                        max: 5
                    }}
                }}
            }};

            // Create network
            const container = document.getElementById('mynetwork');
            const data = {{ nodes: nodes, edges: edges }};
            const network = new vis.Network(container, data, options);

            console.log('vis-network: Network created');

            // Hide loading after stabilization
            network.on('stabilized', function() {{
                console.log('vis-network: Stabilized');
                document.getElementById('loading').style.display = 'none';
            }});

            // Also hide loading after a timeout (fallback)
            setTimeout(function() {{
                document.getElementById('loading').style.display = 'none';
            }}, 3000);

            // Node click handler
            network.on('click', function(params) {{
                if (params.nodes.length > 0) {{
                    const nodeId = params.nodes[0];
                    const node = nodes.get(nodeId);
                    showNodeInfo(node);
                }} else {{
                    document.getElementById('node-info').style.display = 'none';
                }}
            }});

            // Show node info panel
            function showNodeInfo(node) {{
                const infoPanel = document.getElementById('node-info');
                const title = document.getElementById('info-title');
                const content = document.getElementById('info-content');

                title.textContent = node.label || node.id;

                let html = '';
                html += `<div class="info-row"><span class="info-label">Type:</span><span class="info-value">${{node.group}}</span></div>`;

                if (node.year) {{
                    html += `<div class="info-row"><span class="info-label">Year:</span><span class="info-value">${{node.year}}</span></div>`;
                }}
                if (node.evidence_level) {{
                    html += `<div class="info-row"><span class="info-label">Evidence:</span><span class="info-value">${{node.evidence_level}}</span></div>`;
                }}
                if (node.category) {{
                    html += `<div class="info-row"><span class="info-label">Category:</span><span class="info-value">${{node.category}}</span></div>`;
                }}
                if (node.p_value !== undefined) {{
                    html += `<div class="info-row"><span class="info-label">p-value:</span><span class="info-value">${{node.p_value.toFixed(4)}}</span></div>`;
                }}
                if (node.effect_size !== undefined) {{
                    html += `<div class="info-row"><span class="info-label">Effect Size:</span><span class="info-value">${{node.effect_size.toFixed(2)}}</span></div>`;
                }}

                content.innerHTML = html;
                infoPanel.style.display = 'block';
            }}

            // Toggle physics
            let physicsEnabled = {'true' if physics_enabled else 'false'};
            function togglePhysics() {{
                physicsEnabled = !physicsEnabled;
                network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
            }}

            // Reset highlight
            function resetHighlight() {{
                const allNodes = nodes.get();
                allNodes.forEach(node => {{
                    nodes.update({{
                        id: node.id,
                        borderWidth: 2,
                        size: 20,
                        shadow: false
                    }});
                }});
                network.fit();
            }}

            // Focus on highlighted nodes if any
            const highlightedIds = {json.dumps(list(highlight_set))};
            if (highlightedIds.length > 0) {{
                setTimeout(() => {{
                    network.fit({{
                        nodes: highlightedIds,
                        animation: {{
                            duration: 1000,
                            easingFunction: 'easeInOutQuad'
                        }}
                    }});
                }}, 500);
            }}
        </script>
    </body>
    </html>
    """

    # Render component
    components.html(html_content, height=height + 20, scrolling=False)


def create_spine_graph_data(
    neo4j_client,
    query_type: str = "intervention_outcome",
    filters: dict = None,
    limit: int = 100
) -> tuple[list[dict], list[dict]]:
    """Create graph data from Neo4j for Spine GraphRAG.

    Args:
        neo4j_client: SyncNeo4jClient instance
        query_type: Type of graph to build
        filters: Optional filters (intervention, outcome, pathology, etc.)
        limit: Max results

    Returns:
        Tuple of (nodes, edges) for vis_network_graph
    """
    filters = filters or {}
    nodes = []
    edges = []
    node_ids = set()

    if query_type == "intervention_outcome":
        # Build Intervention → Outcome graph
        # Use a smarter query to get diverse interventions first
        params = {"limit": limit}

        if filters.get("intervention"):
            # Single intervention filter - get all its outcomes
            where_parts = ["i.name = $intervention"]
            params["intervention"] = filters["intervention"]
            if filters.get("outcome"):
                where_parts.append("o.name = $outcome")
                params["outcome"] = filters["outcome"]
            if filters.get("sig_only"):
                where_parts.append("r.is_significant = true")

            where_clause = "WHERE " + " AND ".join(where_parts)

            cypher = f"""
            MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
            {where_clause}
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WITH i, o, r, count(DISTINCT p) AS paper_count
            RETURN i.name AS i_name, i.category AS i_category,
                   o.name AS o_name, o.type AS o_type,
                   r.direction AS direction, r.p_value AS p_value,
                   r.is_significant AS is_sig, r.effect_size AS effect_size,
                   paper_count
            LIMIT $limit
            """
        else:
            # No intervention filter - get diverse interventions with top outcomes
            where_parts = []
            if filters.get("outcome"):
                where_parts.append("o.name = $outcome")
                params["outcome"] = filters["outcome"]
            if filters.get("category"):
                where_parts.append("i.category = $category")
                params["category"] = filters["category"]
            if filters.get("sig_only"):
                where_parts.append("r.is_significant = true")

            where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

            # Get top interventions by number of AFFECTS relationships
            # Then for each intervention, get up to 3 outcomes
            cypher = f"""
            MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
            {where_clause}
            WITH i, count(r) AS rel_count
            ORDER BY rel_count DESC
            LIMIT $intervention_limit
            WITH collect(i) AS top_interventions
            UNWIND top_interventions AS i
            MATCH (i)-[r:AFFECTS]->(o:Outcome)
            {where_clause.replace('WHERE', 'WHERE') if where_clause else ''}
            OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
            WITH i, o, r, count(DISTINCT p) AS paper_count
            ORDER BY i.name, r.is_significant DESC, r.p_value ASC
            WITH i, collect({{o: o, r: r, paper_count: paper_count}})[0..4] AS outcomes
            UNWIND outcomes AS out
            RETURN i.name AS i_name, i.category AS i_category,
                   out.o.name AS o_name, out.o.type AS o_type,
                   out.r.direction AS direction, out.r.p_value AS p_value,
                   out.r.is_significant AS is_sig, out.r.effect_size AS effect_size,
                   out.paper_count AS paper_count
            """
            # Calculate intervention limit based on total limit
            params["intervention_limit"] = max(20, limit // 4)

        records = neo4j_client.run_query(cypher, params)

        for rec in records:
            i_name = rec["i_name"]
            o_name = rec["o_name"]

            # Add intervention node
            if i_name not in node_ids:
                nodes.append({
                    "id": i_name,
                    "label": i_name,
                    "group": "Intervention",
                    "title": f"{i_name}\nCategory: {rec['i_category'] or 'N/A'}\nPapers: {rec['paper_count']}",
                    "category": rec["i_category"],
                    "paper_count": rec["paper_count"]
                })
                node_ids.add(i_name)

            # Add outcome node
            if o_name not in node_ids:
                nodes.append({
                    "id": o_name,
                    "label": o_name,
                    "group": "Outcome",
                    "title": f"{o_name}\nType: {rec['o_type'] or 'N/A'}",
                    "category": rec["o_type"]
                })
                node_ids.add(o_name)

            # Add edge
            edges.append({
                "from": i_name,
                "to": o_name,
                "label": rec["direction"] or "",
                "direction": rec["direction"] or "unchanged",
                "is_significant": rec["is_sig"] or False,
                "p_value": rec["p_value"],
                "effect_size": rec["effect_size"]
            })

    elif query_type == "paper_network":
        # Build Paper → Intervention/Pathology network (since CITES relationships don't exist)
        intervention_filter = filters.get("intervention")
        pathology_filter = filters.get("pathology")

        if intervention_filter:
            cypher = """
            MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention {name: $intervention})
            OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
            OPTIONAL MATCH (p)-[:INVESTIGATES]->(other_i:Intervention)
            WHERE other_i.name <> $intervention
            RETURN p.paper_id AS paper_id, p.title AS title,
                   p.year AS year, p.evidence_level AS evidence_level,
                   $intervention AS main_intervention,
                   collect(DISTINCT path.name) AS pathologies,
                   collect(DISTINCT other_i.name) AS other_interventions
            LIMIT $limit
            """
            params = {"intervention": intervention_filter, "limit": limit}
        elif pathology_filter:
            cypher = """
            MATCH (p:Paper)-[:STUDIES]->(path:Pathology {name: $pathology})
            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
            RETURN p.paper_id AS paper_id, p.title AS title,
                   p.year AS year, p.evidence_level AS evidence_level,
                   $pathology AS main_pathology,
                   collect(DISTINCT i.name) AS interventions
            LIMIT $limit
            """
            params = {"pathology": pathology_filter, "limit": limit}
        else:
            cypher = """
            MATCH (p:Paper)
            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
            OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
            RETURN p.paper_id AS paper_id, p.title AS title,
                   p.year AS year, p.evidence_level AS evidence_level,
                   collect(DISTINCT i.name)[0..3] AS interventions,
                   collect(DISTINCT path.name)[0..2] AS pathologies
            LIMIT $limit
            """
            params = {"limit": limit}

        records = neo4j_client.run_query(cypher, params)

        for rec in records:
            paper_id = rec["paper_id"]
            title = rec["title"] or "Untitled"

            # Add paper node
            if paper_id not in node_ids:
                nodes.append({
                    "id": paper_id,
                    "label": title[:40] + "..." if len(title) > 40 else title,
                    "group": "Paper",
                    "title": f"{title}\nYear: {rec['year']}\nEvidence: {rec['evidence_level']}",
                    "year": rec["year"],
                    "evidence_level": rec["evidence_level"]
                })
                node_ids.add(paper_id)

            # Add intervention nodes and edges
            interventions = rec.get("interventions") or rec.get("other_interventions") or []
            if rec.get("main_intervention"):
                interventions = [rec["main_intervention"]] + list(interventions)

            for i_name in interventions[:3]:  # Limit to 3 interventions per paper
                if i_name and i_name not in node_ids:
                    nodes.append({
                        "id": i_name,
                        "label": i_name,
                        "group": "Intervention",
                        "title": f"Intervention: {i_name}"
                    })
                    node_ids.add(i_name)
                if i_name:
                    edges.append({
                        "from": paper_id,
                        "to": i_name,
                        "label": "INVESTIGATES"
                    })

            # Add pathology nodes and edges
            pathologies = rec.get("pathologies") or []
            if rec.get("main_pathology"):
                pathologies = [rec["main_pathology"]] + list(pathologies)

            for p_name in pathologies[:2]:  # Limit to 2 pathologies per paper
                if p_name and p_name not in node_ids:
                    nodes.append({
                        "id": p_name,
                        "label": p_name,
                        "group": "Pathology",
                        "title": f"Pathology: {p_name}"
                    })
                    node_ids.add(p_name)
                if p_name:
                    edges.append({
                        "from": paper_id,
                        "to": p_name,
                        "label": "STUDIES"
                    })

    elif query_type == "full_schema":
        # Build comprehensive schema graph showing all entity types and relationships
        # Query 1: Paper relationships (STUDIES, INVESTIGATES, INVOLVES)
        paper_cypher = """
        MATCH (p:Paper)-[r]->(target)
        WHERE type(r) IN ['STUDIES', 'INVESTIGATES', 'INVOLVES']
        RETURN p.paper_id AS source_id, p.title AS source_title, 'Paper' AS source_type,
               labels(target)[0] AS target_type,
               COALESCE(target.name, target.paper_id) AS target_id,
               COALESCE(target.name, target.title, target.paper_id) AS target_label,
               type(r) AS rel_type
        LIMIT $limit
        """
        params = {"limit": limit}

        records = neo4j_client.run_query(paper_cypher, params)

        for rec in records:
            source_id = rec["source_id"]
            target_id = rec["target_id"]

            if source_id not in node_ids:
                nodes.append({
                    "id": source_id,
                    "label": (rec["source_title"] or source_id)[:30] + "...",
                    "group": "Paper",
                    "title": rec["source_title"] or source_id
                })
                node_ids.add(source_id)

            if target_id and target_id not in node_ids:
                nodes.append({
                    "id": target_id,
                    "label": rec["target_label"][:30] if rec["target_label"] else str(target_id),
                    "group": rec["target_type"],
                    "title": rec["target_label"]
                })
                node_ids.add(target_id)

            if target_id:
                edges.append({
                    "from": source_id,
                    "to": target_id,
                    "label": rec["rel_type"]
                })

        # Query 2: Intervention → Outcome (AFFECTS)
        affects_cypher = """
        MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
        RETURN i.name AS i_name, o.name AS o_name,
               r.direction AS direction, r.is_significant AS is_sig
        LIMIT $limit
        """

        affects_records = neo4j_client.run_query(affects_cypher, {"limit": limit})

        for rec in affects_records:
            i_name = rec["i_name"]
            o_name = rec["o_name"]

            if i_name not in node_ids:
                nodes.append({
                    "id": i_name,
                    "label": i_name,
                    "group": "Intervention",
                    "title": f"Intervention: {i_name}"
                })
                node_ids.add(i_name)

            if o_name not in node_ids:
                nodes.append({
                    "id": o_name,
                    "label": o_name,
                    "group": "Outcome",
                    "title": f"Outcome: {o_name}"
                })
                node_ids.add(o_name)

            edges.append({
                "from": i_name,
                "to": o_name,
                "label": rec["direction"] or "AFFECTS",
                "direction": rec["direction"] or "unchanged",
                "is_significant": rec["is_sig"] or False
            })

        # Query 3: IS_A hierarchy (Intervention taxonomy)
        isa_cypher = """
        MATCH (child:Intervention)-[:IS_A]->(parent:Intervention)
        RETURN child.name AS child_name, parent.name AS parent_name
        LIMIT $limit
        """

        isa_records = neo4j_client.run_query(isa_cypher, {"limit": limit})

        for rec in isa_records:
            child_name = rec["child_name"]
            parent_name = rec["parent_name"]

            if child_name not in node_ids:
                nodes.append({
                    "id": child_name,
                    "label": child_name,
                    "group": "Intervention",
                    "title": f"Intervention: {child_name}"
                })
                node_ids.add(child_name)

            if parent_name not in node_ids:
                nodes.append({
                    "id": parent_name,
                    "label": parent_name,
                    "group": "Intervention",
                    "title": f"Intervention (Parent): {parent_name}"
                })
                node_ids.add(parent_name)

            edges.append({
                "from": child_name,
                "to": parent_name,
                "label": "IS_A"
            })

        # Query 4: Pathology → Complication (CAUSES)
        causes_cypher = """
        MATCH (p:Pathology)-[:CAUSES]->(c:Complication)
        RETURN p.name AS pathology, c.name AS complication
        LIMIT $limit
        """

        causes_records = neo4j_client.run_query(causes_cypher, {"limit": limit})

        for rec in causes_records:
            p_name = rec["pathology"]
            c_name = rec["complication"]

            if p_name not in node_ids:
                nodes.append({
                    "id": p_name,
                    "label": p_name,
                    "group": "Pathology",
                    "title": f"Pathology: {p_name}"
                })
                node_ids.add(p_name)

            if c_name not in node_ids:
                nodes.append({
                    "id": c_name,
                    "label": c_name,
                    "group": "Complication",
                    "title": f"Complication: {c_name}"
                })
                node_ids.add(c_name)

            edges.append({
                "from": p_name,
                "to": c_name,
                "label": "CAUSES"
            })

    return nodes, edges
