"""Graph Utilities - Neo4j and Graph Visualization Helpers.

Utilities for connecting to Neo4j and processing graph data for UI.
Uses synchronous Neo4j driver for Streamlit compatibility.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


class SyncNeo4jClient:
    """Synchronous Neo4j client for Streamlit compatibility.

    Streamlit's event loop handling conflicts with async Neo4j driver,
    so we use synchronous driver instead.
    """

    def __init__(self):
        """Initialize sync Neo4j client."""
        try:
            from neo4j import GraphDatabase

            self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            self.username = os.getenv("NEO4J_USERNAME", "neo4j")
            self.password = os.getenv("NEO4J_PASSWORD", "password")
            self.database = os.getenv("NEO4J_DATABASE", "neo4j")

            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )

            # Test connection
            with self._driver.session(database=self.database) as session:
                session.run("RETURN 1")

            self._available = True

        except Exception as e:
            print(f"Neo4j connection error: {e}")
            self._driver = None
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def run_query(self, cypher: str, params: dict = None) -> list[dict]:
        """Run Cypher query and return results as list of dicts."""
        if not self._available:
            return []

        try:
            with self._driver.session(database=self.database) as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except Exception as e:
            print(f"Query error: {e}")
            return []

    def close(self):
        """Close the driver."""
        if self._driver:
            self._driver.close()


# Global client instance (cached)
_neo4j_client: Optional[SyncNeo4jClient] = None


def get_neo4j_client() -> Optional[SyncNeo4jClient]:
    """Get Neo4j client instance (cached).

    Returns:
        SyncNeo4jClient instance or None if not available
    """
    global _neo4j_client

    if _neo4j_client is None:
        _neo4j_client = SyncNeo4jClient()

    if not _neo4j_client.is_available:
        return None

    return _neo4j_client


def get_intervention_tree(neo4j_client: SyncNeo4jClient) -> list[dict]:
    """Get intervention taxonomy tree.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        List of root interventions with children
    """
    # Get all interventions with hierarchy
    cypher = """
    MATCH (i:Intervention)
    OPTIONAL MATCH (i)-[:IS_A]->(parent:Intervention)
    OPTIONAL MATCH (child:Intervention)-[:IS_A]->(i)
    OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
    WITH i, parent, collect(DISTINCT child) AS children, count(DISTINCT p) AS paper_count
    RETURN i.name AS name, i.full_name AS full_name,
           i.category AS category, i.aliases AS aliases,
           parent.name AS parent_name,
           [c IN children | c.name] AS child_names,
           paper_count
    ORDER BY i.name
    """

    records = neo4j_client.run_query(cypher, {})

    # Build tree structure
    interventions = {}
    for record in records:
        name = record["name"]
        interventions[name] = {
            "name": name,
            "full_name": record["full_name"] or name,
            "category": record["category"] or "",
            "aliases": record["aliases"] or [],
            "parent": record["parent_name"],
            "children": [],
            "paper_count": record["paper_count"]
        }

    # Link children
    for name, data in interventions.items():
        if data["parent"] and data["parent"] in interventions:
            interventions[data["parent"]]["children"].append(data)

    # Return only root nodes (no parent)
    roots = [data for data in interventions.values() if not data["parent"]]

    return roots


def get_graph_stats(neo4j_client: SyncNeo4jClient) -> dict:
    """Get graph database statistics.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        Dict with node and relationship counts
    """
    cypher = """
    MATCH (n)
    WITH labels(n) AS label, count(*) AS count
    RETURN label[0] AS node_type, count
    UNION ALL
    MATCH ()-[r]->()
    WITH type(r) AS rel_type, count(*) AS count
    RETURN rel_type AS node_type, count
    """

    records = neo4j_client.run_query(cypher, {})

    stats = {
        "nodes": {},
        "relationships": {},
        "total_nodes": 0,
        "total_relationships": 0
    }

    for record in records:
        node_type = record["node_type"]
        count = record["count"]

        # Distinguish nodes from relationships
        if node_type in ["Paper", "Intervention", "Outcome", "Pathology"]:
            stats["nodes"][node_type] = count
            stats["total_nodes"] += count
        else:
            stats["relationships"][node_type] = count
            stats["total_relationships"] += count

    return stats


def get_paper_network(neo4j_client: SyncNeo4jClient, intervention: Optional[str] = None, limit: int = 50) -> dict:
    """Get paper citation network data for visualization.

    Args:
        neo4j_client: Sync Neo4j client instance
        intervention: Filter by intervention (optional)
        limit: Max papers to return

    Returns:
        Dict with nodes and edges for network visualization
    """
    if intervention:
        # Papers investigating specific intervention
        cypher = """
        MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention {name: $intervention})
        OPTIONAL MATCH (p)-[:CITES]->(cited:Paper)
        WITH p, collect(DISTINCT cited) AS cited_papers
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.year AS year, p.evidence_level AS evidence_level,
               [c IN cited_papers | c.paper_id] AS citations
        LIMIT $limit
        """
        params = {"intervention": intervention, "limit": limit}
    else:
        # General network
        cypher = """
        MATCH (p:Paper)
        OPTIONAL MATCH (p)-[:CITES]->(cited:Paper)
        WITH p, collect(DISTINCT cited) AS cited_papers
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.year AS year, p.evidence_level AS evidence_level,
               [c IN cited_papers | c.paper_id] AS citations
        LIMIT $limit
        """
        params = {"limit": limit}

    records = neo4j_client.run_query(cypher, params)

    nodes = []
    edges = []

    for record in records:
        paper_id = record["paper_id"]
        title = record["title"] or "Untitled"
        nodes.append({
            "id": paper_id,
            "label": title[:50] + "..." if len(title) > 50 else title,
            "year": record["year"],
            "evidence_level": record["evidence_level"],
        })

        for cited_id in record["citations"] or []:
            edges.append({
                "from": paper_id,
                "to": cited_id,
            })

    return {"nodes": nodes, "edges": edges}


def create_network_graph(network_data: dict):
    """Create Plotly network graph visualization.

    Args:
        network_data: Dict with 'nodes' and 'edges'

    Returns:
        Plotly Figure object
    """
    import plotly.graph_objects as go
    import networkx as nx

    # Build NetworkX graph
    G = nx.DiGraph()

    for node in network_data["nodes"]:
        G.add_node(node["id"], **node)

    for edge in network_data["edges"]:
        G.add_edge(edge["from"], edge["to"])

    # Layout
    pos = nx.spring_layout(G, k=0.5, iterations=50)

    # Create edge trace
    edge_x = []
    edge_y = []

    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines'
    )

    # Create node trace
    node_x = []
    node_y = []
    node_text = []
    node_color = []

    evidence_colors = {
        "1a": "#1f77b4",
        "1b": "#2ca02c",
        "2a": "#ff7f0e",
        "2b": "#d62728",
        "3": "#9467bd",
        "4": "#8c564b",
        "5": "#e377c2",
    }

    for node_id in G.nodes():
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)

        node_data = G.nodes[node_id]
        label = node_data.get("label", node_id)
        year = node_data.get("year", "N/A")
        evidence = node_data.get("evidence_level", "5")

        node_text.append(f"{label}<br>Year: {year}<br>Evidence: {evidence}")
        node_color.append(evidence_colors.get(evidence, "#999999"))

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            showscale=False,
            color=node_color,
            size=10,
            line_width=2
        )
    )

    # Create figure
    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title="Paper Citation Network",
            showlegend=False,
            hovermode='closest',
            margin=dict(b=0, l=0, r=0, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=600,
        )
    )

    return fig


# ========================================================================
# v7.2 Extended Entity Query Functions
# ========================================================================

def get_patient_cohorts(neo4j_client: SyncNeo4jClient, paper_id: str = None, limit: int = 50) -> list[dict]:
    """Get patient cohort data from v7.2 extended entities.

    Args:
        neo4j_client: Sync Neo4j client instance
        paper_id: Optional paper ID filter
        limit: Max results to return

    Returns:
        List of patient cohort records
    """
    if paper_id:
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})-[:HAS_COHORT]->(c:PatientCohort)
        OPTIONAL MATCH (c)-[:TREATED_WITH]->(i:Intervention)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               c.name AS cohort_name, c.cohort_type AS cohort_type,
               c.sample_size AS sample_size, c.mean_age AS mean_age,
               c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
               c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
               c.BMI AS bmi, collect(i.name) AS interventions
        ORDER BY c.sample_size DESC
        LIMIT $limit
        """
        params = {"paper_id": paper_id, "limit": limit}
    else:
        cypher = """
        MATCH (p:Paper)-[:HAS_COHORT]->(c:PatientCohort)
        OPTIONAL MATCH (c)-[:TREATED_WITH]->(i:Intervention)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               c.name AS cohort_name, c.cohort_type AS cohort_type,
               c.sample_size AS sample_size, c.mean_age AS mean_age,
               c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
               c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
               c.BMI AS bmi, collect(i.name) AS interventions
        ORDER BY c.sample_size DESC
        LIMIT $limit
        """
        params = {"limit": limit}

    return neo4j_client.run_query(cypher, params)


def get_followup_data(neo4j_client: SyncNeo4jClient, paper_id: str = None, limit: int = 100) -> list[dict]:
    """Get follow-up data from v7.2 extended entities.

    Args:
        neo4j_client: Sync Neo4j client instance
        paper_id: Optional paper ID filter
        limit: Max results to return

    Returns:
        List of follow-up records with timepoints
    """
    if paper_id:
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})-[:HAS_FOLLOWUP]->(f:FollowUp)
        OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
               f.completeness_rate AS completeness_rate,
               collect(DISTINCT o.name) AS outcomes
        ORDER BY f.timepoint_months
        LIMIT $limit
        """
        params = {"paper_id": paper_id, "limit": limit}
    else:
        cypher = """
        MATCH (p:Paper)-[:HAS_FOLLOWUP]->(f:FollowUp)
        OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
               f.completeness_rate AS completeness_rate,
               collect(DISTINCT o.name) AS outcomes
        ORDER BY f.timepoint_months
        LIMIT $limit
        """
        params = {"limit": limit}

    return neo4j_client.run_query(cypher, params)


def get_cost_data(neo4j_client: SyncNeo4jClient, paper_id: str = None, limit: int = 50) -> list[dict]:
    """Get cost-effectiveness data from v7.2 extended entities.

    Args:
        neo4j_client: Sync Neo4j client instance
        paper_id: Optional paper ID filter
        limit: Max results to return

    Returns:
        List of cost analysis records with QALY, ICER, LOS
    """
    if paper_id:
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})-[:REPORTS_COST]->(cost:Cost)
        OPTIONAL MATCH (cost)-[:ASSOCIATED_WITH]->(i:Intervention)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               cost.name AS cost_name, cost.cost_type AS cost_type,
               cost.mean_cost AS mean_cost, cost.currency AS currency,
               cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
               cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
               collect(i.name) AS interventions
        ORDER BY cost.mean_cost DESC
        LIMIT $limit
        """
        params = {"paper_id": paper_id, "limit": limit}
    else:
        cypher = """
        MATCH (p:Paper)-[:REPORTS_COST]->(cost:Cost)
        OPTIONAL MATCH (cost)-[:ASSOCIATED_WITH]->(i:Intervention)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               cost.name AS cost_name, cost.cost_type AS cost_type,
               cost.mean_cost AS mean_cost, cost.currency AS currency,
               cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
               cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
               collect(i.name) AS interventions
        ORDER BY cost.mean_cost DESC
        LIMIT $limit
        """
        params = {"limit": limit}

    return neo4j_client.run_query(cypher, params)


def get_quality_metrics(neo4j_client: SyncNeo4jClient, paper_id: str = None, limit: int = 50) -> list[dict]:
    """Get quality assessment metrics from v7.2 extended entities.

    Args:
        neo4j_client: Sync Neo4j client instance
        paper_id: Optional paper ID filter
        limit: Max results to return

    Returns:
        List of quality metric records (GRADE, MINORS, etc.)
    """
    if paper_id:
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})-[:HAS_QUALITY_METRIC]->(q:QualityMetric)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               q.name AS metric_name, q.assessment_tool AS assessment_tool,
               q.overall_score AS overall_score, q.overall_rating AS overall_rating,
               q.domain_scores AS domain_scores
        ORDER BY q.overall_score DESC
        LIMIT $limit
        """
        params = {"paper_id": paper_id, "limit": limit}
    else:
        cypher = """
        MATCH (p:Paper)-[:HAS_QUALITY_METRIC]->(q:QualityMetric)
        RETURN p.paper_id AS paper_id, p.title AS paper_title,
               q.name AS metric_name, q.assessment_tool AS assessment_tool,
               q.overall_score AS overall_score, q.overall_rating AS overall_rating,
               q.domain_scores AS domain_scores
        ORDER BY q.overall_score DESC
        LIMIT $limit
        """
        params = {"limit": limit}

    return neo4j_client.run_query(cypher, params)


def get_extended_graph_stats(neo4j_client: SyncNeo4jClient) -> dict:
    """Get extended graph statistics including v7.2 entities.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        Dict with all node and relationship counts including v7.2 entities
    """
    cypher = """
    CALL {
        MATCH (n)
        WITH labels(n) AS label, count(*) AS count
        RETURN label[0] AS type, count, 'node' AS category
    }
    RETURN type, count, category
    ORDER BY count DESC
    """

    records = neo4j_client.run_query(cypher, {})

    stats = {
        "core_nodes": {},
        "v72_nodes": {},
        "total_nodes": 0
    }

    v72_types = ["PatientCohort", "FollowUp", "Cost", "QualityMetric"]

    for record in records:
        node_type = record["type"]
        count = record["count"]

        if node_type in v72_types:
            stats["v72_nodes"][node_type] = count
        else:
            stats["core_nodes"][node_type] = count

        stats["total_nodes"] += count

    # Get v7.2 relationship counts
    rel_cypher = """
    MATCH ()-[r]->()
    WHERE type(r) IN ['HAS_COHORT', 'TREATED_WITH', 'HAS_FOLLOWUP', 'REPORTS_OUTCOME', 'REPORTS_COST', 'ASSOCIATED_WITH', 'HAS_QUALITY_METRIC']
    WITH type(r) AS rel_type, count(*) AS count
    RETURN rel_type, count
    """

    rel_records = neo4j_client.run_query(rel_cypher, {})
    stats["v72_relationships"] = {r["rel_type"]: r["count"] for r in rel_records}

    return stats


# ========================================================================
# v1.14.25 Schema Overview Query Functions
# ========================================================================

def get_schema_node_counts(neo4j_client: SyncNeo4jClient) -> dict[str, int]:
    """Get count of each node type in the graph.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        Dict mapping node labels to instance counts
    """
    cypher = """
    MATCH (n)
    WITH labels(n)[0] AS label, count(n) AS count
    RETURN label, count
    ORDER BY count DESC
    """

    records = neo4j_client.run_query(cypher, {})
    return {r["label"]: r["count"] for r in records if r.get("label")}


def get_schema_relationship_counts(neo4j_client: SyncNeo4jClient) -> list[dict]:
    """Get count of each relationship type with source/target info.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        List of dicts with rel_type, source_label, target_label, count
    """
    cypher = """
    MATCH (a)-[r]->(b)
    WITH type(r) AS rel_type,
         labels(a)[0] AS source_label,
         labels(b)[0] AS target_label,
         count(*) AS count
    RETURN rel_type, source_label, target_label, count
    ORDER BY count DESC
    """

    return neo4j_client.run_query(cypher, {})


def get_intervention_hierarchy(neo4j_client: SyncNeo4jClient) -> list[dict]:
    """Get intervention IS_A hierarchy for tree visualization.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        List of dicts with parent, children, paper_counts
    """
    cypher = """
    MATCH (i:Intervention)
    OPTIONAL MATCH (i)-[:IS_A]->(parent:Intervention)
    OPTIONAL MATCH (child:Intervention)-[:IS_A]->(i)
    OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
    WITH i, parent,
         collect(DISTINCT child.name) AS children,
         count(DISTINCT p) AS paper_count
    RETURN i.name AS name,
           i.full_name AS full_name,
           i.category AS category,
           i.is_minimally_invasive AS is_mis,
           i.snomed_code AS snomed_code,
           parent.name AS parent_name,
           children,
           paper_count
    ORDER BY paper_count DESC
    """

    return neo4j_client.run_query(cypher, {})


def get_schema_summary(neo4j_client: SyncNeo4jClient) -> dict:
    """Get comprehensive schema summary for overview display.

    Args:
        neo4j_client: Sync Neo4j client instance

    Returns:
        Dict with node_counts, relationship_summary, totals
    """
    # Get node counts
    node_counts = get_schema_node_counts(neo4j_client)

    # Get relationship summary (aggregated by type)
    rel_cypher = """
    MATCH ()-[r]->()
    WITH type(r) AS rel_type, count(*) AS count
    RETURN rel_type, count
    ORDER BY count DESC
    """
    rel_records = neo4j_client.run_query(rel_cypher, {})
    rel_counts = {r["rel_type"]: r["count"] for r in rel_records}

    # Calculate totals
    total_nodes = sum(node_counts.values())
    total_rels = sum(rel_counts.values())

    return {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
        "node_type_count": len(node_counts),
        "relationship_type_count": len(rel_counts)
    }
