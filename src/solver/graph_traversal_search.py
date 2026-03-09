"""Multi-hop graph traversal search for evidence chains.

IS_A 계층 확장 + TREATS/AFFECTS 관계 체인을 활용한
다중 홉 그래프 탐색 검색 모듈.

Evidence chains:
    Intervention -[IS_A]-> Parent -[TREATS]-> Pathology -[AFFECTS]-> Outcome

Usage:
    search = GraphTraversalSearch(neo4j_client, taxonomy_manager)
    chain = await search.traverse_evidence_chain("TLIF", "Spinal Stenosis")
    comparison = await search.compare_interventions("TLIF", "PLIF", "Spinal Stenosis")
    best = await search.find_best_evidence("Lumbar Stenosis")
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvidenceChainLink:
    """Single link in an evidence chain.

    Attributes:
        source_node: Starting node name
        relationship: Relationship type (IS_A, TREATS, AFFECTS, INVESTIGATES)
        target_node: Ending node name
        properties: Relationship properties (p_value, effect_size, etc.)
    """
    source_node: str
    relationship: str
    target_node: str
    properties: dict = field(default_factory=dict)


@dataclass
class EvidenceChainResult:
    """Result from evidence chain traversal.

    Attributes:
        intervention: Primary intervention name
        pathology: Target pathology name
        outcomes: List of affected outcomes
        direct_evidence: Papers with direct intervention-pathology link
        related_evidence: Papers via IS_A expansion (sibling/parent interventions)
        evidence_chain: Ordered chain of graph relationships
    """
    intervention: str
    pathology: str
    outcomes: list[dict] = field(default_factory=list)
    direct_evidence: list[dict] = field(default_factory=list)
    related_evidence: list[dict] = field(default_factory=list)
    evidence_chain: list[EvidenceChainLink] = field(default_factory=list)


@dataclass
class InterventionComparison:
    """Result from comparing two interventions.

    Attributes:
        intervention1: First intervention name
        intervention2: Second intervention name
        pathology: Target pathology
        shared_outcomes: Outcomes measured by both
        int1_only_outcomes: Outcomes only for intervention1
        int2_only_outcomes: Outcomes only for intervention2
        comparison_summary: Summary of comparison
    """
    intervention1: str
    intervention2: str
    pathology: str
    shared_outcomes: list[dict] = field(default_factory=list)
    int1_only_outcomes: list[dict] = field(default_factory=list)
    int2_only_outcomes: list[dict] = field(default_factory=list)
    comparison_summary: str = ""


@dataclass
class BestEvidenceResult:
    """Result from best evidence search.

    Attributes:
        paper_id: Paper identifier
        title: Paper title
        evidence_level: OCEBM evidence level
        year: Publication year
        interventions: Interventions studied
        outcomes: Outcomes measured
        evidence_chain: Graph relationships connecting paper to query
    """
    paper_id: str
    title: str
    evidence_level: str = "5"
    year: int = 0
    interventions: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    outcome_details: list[dict] = field(default_factory=list)
    evidence_chain: list[EvidenceChainLink] = field(default_factory=list)


class GraphTraversalSearch:
    """Multi-hop graph traversal search for evidence chains.

    Traverses IS_A hierarchies and TREATS/AFFECTS relationships
    to build comprehensive evidence chains from the knowledge graph.

    Args:
        neo4j_client: Neo4jClient instance for running Cypher queries
        taxonomy_manager: Optional TaxonomyManager for hierarchy queries
    """

    def __init__(self, neo4j_client, taxonomy_manager=None):
        """Initialize with Neo4j client and optional taxonomy manager.

        Args:
            neo4j_client: Neo4jClient instance
            taxonomy_manager: TaxonomyManager instance (optional)
        """
        self.client = neo4j_client
        self.taxonomy_manager = taxonomy_manager

    async def traverse_evidence_chain(
        self,
        intervention: str,
        pathology: str,
        outcome: Optional[str] = None,
        is_a_depth: int = 2,
    ) -> EvidenceChainResult:
        """Follow TREATS/AFFECTS chains + IS_A expansion to build evidence chains.

        Traverses the graph from intervention through TREATS to pathology,
        then through AFFECTS to outcomes. Also traverses IS_A to find
        sibling/parent interventions with the same evidence.

        Args:
            intervention: Intervention name (e.g., "TLIF")
            pathology: Pathology name (e.g., "Spinal Stenosis")
            outcome: Optional specific outcome to filter on
            is_a_depth: Depth for IS_A hierarchy expansion (clamped to 1-5)


        Returns:
            EvidenceChainResult with direct and related evidence
        """
        # Clamp is_a_depth to safe range (1-5)
        is_a_depth = min(max(int(is_a_depth), 1), 5)

        result = EvidenceChainResult(
            intervention=intervention,
            pathology=pathology,
        )

        # 1. Direct evidence: Intervention -> TREATS -> Pathology
        #    + Paper -> INVESTIGATES -> Intervention
        direct_query = """
        MATCH (i:Intervention {name: $intervention})
        OPTIONAL MATCH (i)-[t:TREATS]->(path:Pathology {name: $pathology})
        OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
        OPTIONAL MATCH (p:Paper)-[:INVESTIGATES]->(i)
        WHERE p IS NOT NULL
        RETURN DISTINCT
            p.paper_id as paper_id,
            p.title as title,
            p.year as year,
            p.evidence_level as evidence_level,
            o.name as outcome_name,
            a.value as value,
            a.p_value as p_value,
            a.direction as direction,
            a.effect_size as effect_size,
            a.is_significant as is_significant,
            t IS NOT NULL as has_treats_link
        ORDER BY p.evidence_level ASC, p.year DESC
        LIMIT 50
        """
        params = {
            "intervention": intervention,
            "pathology": pathology,
        }

        try:
            rows = await self.client.run_query(direct_query, params)
            for row in rows:
                paper_entry = {
                    "paper_id": row.get("paper_id", ""),
                    "title": row.get("title", ""),
                    "year": row.get("year", 0),
                    "evidence_level": row.get("evidence_level", "5"),
                    "outcome": row.get("outcome_name", ""),
                    "value": row.get("value", ""),
                    "p_value": row.get("p_value"),
                    "direction": row.get("direction", ""),
                    "effect_size": row.get("effect_size", ""),
                    "is_significant": row.get("is_significant", False),
                    "has_treats_link": row.get("has_treats_link", False),
                }

                if outcome and row.get("outcome_name") != outcome:
                    continue

                result.direct_evidence.append(paper_entry)

                if row.get("outcome_name"):
                    result.outcomes.append({
                        "name": row["outcome_name"],
                        "value": row.get("value", ""),
                        "direction": row.get("direction", ""),
                    })

                # Build chain links
                if row.get("has_treats_link"):
                    result.evidence_chain.append(EvidenceChainLink(
                        source_node=intervention,
                        relationship="TREATS",
                        target_node=pathology,
                    ))
                if row.get("outcome_name"):
                    result.evidence_chain.append(EvidenceChainLink(
                        source_node=intervention,
                        relationship="AFFECTS",
                        target_node=row["outcome_name"],
                        properties={
                            "value": row.get("value", ""),
                            "p_value": row.get("p_value"),
                            "direction": row.get("direction", ""),
                        },
                    ))

        except Exception as e:
            logger.error(
                f"Direct evidence query failed for "
                f"{intervention} -> {pathology}: {e}",
                exc_info=True,
            )

        # 2. Related evidence: via IS_A hierarchy
        related_query = f"""
        MATCH (i:Intervention {{name: $intervention}})
        OPTIONAL MATCH (i)-[:IS_A*1..{is_a_depth}]->(parent:Intervention)
        OPTIONAL MATCH (sibling:Intervention)-[:IS_A*1..{is_a_depth}]->(parent)
        WHERE sibling <> i AND sibling IS NOT NULL
        WITH collect(DISTINCT parent) + collect(DISTINCT sibling) as related_nodes
        UNWIND related_nodes as rel
        MATCH (p:Paper)-[:INVESTIGATES]->(rel)
        OPTIONAL MATCH (rel)-[a:AFFECTS]->(o:Outcome)
        RETURN DISTINCT
            rel.name as related_intervention,
            p.paper_id as paper_id,
            p.title as title,
            p.year as year,
            p.evidence_level as evidence_level,
            o.name as outcome_name,
            a.direction as direction,
            a.p_value as p_value
        ORDER BY p.evidence_level ASC, p.year DESC
        LIMIT 30
        """

        try:
            rows = await self.client.run_query(related_query, {
                "intervention": intervention,
            })
            for row in rows:
                if outcome and row.get("outcome_name") and row["outcome_name"] != outcome:
                    continue

                result.related_evidence.append({
                    "related_intervention": row.get("related_intervention", ""),
                    "paper_id": row.get("paper_id", ""),
                    "title": row.get("title", ""),
                    "year": row.get("year", 0),
                    "evidence_level": row.get("evidence_level", "5"),
                    "outcome": row.get("outcome_name", ""),
                    "direction": row.get("direction", ""),
                    "p_value": row.get("p_value"),
                })

        except Exception as e:
            logger.error(
                f"Related evidence query failed for {intervention}: {e}",
                exc_info=True,
            )

        # Deduplicate outcomes
        seen_outcomes = set()
        unique_outcomes = []
        for o in result.outcomes:
            if o["name"] not in seen_outcomes:
                seen_outcomes.add(o["name"])
                unique_outcomes.append(o)
        result.outcomes = unique_outcomes

        logger.info(
            f"Evidence chain for {intervention} -> {pathology}: "
            f"{len(result.direct_evidence)} direct, "
            f"{len(result.related_evidence)} related, "
            f"{len(result.outcomes)} outcomes"
        )

        return result

    async def compare_interventions(
        self,
        int1: str,
        int2: str,
        pathology: str,
    ) -> InterventionComparison:
        """Compare two interventions' AFFECTS on same Outcomes for a pathology.

        Args:
            int1: First intervention name
            int2: Second intervention name
            pathology: Target pathology name

        Returns:
            InterventionComparison with shared and unique outcomes
        """
        result = InterventionComparison(
            intervention1=int1,
            intervention2=int2,
            pathology=pathology,
        )

        # Query outcomes for both interventions, filtered by pathology if provided
        compare_query = """
        MATCH (i1:Intervention {name: $int1})-[a1:AFFECTS]->(o1:Outcome)
        OPTIONAL MATCH (p1:Paper)-[:INVESTIGATES]->(i1)
        OPTIONAL MATCH (p1)-[:STUDIES]->(:Pathology {name: $pathology})
        WITH i1, a1, o1, p1
        WHERE $pathology IS NULL OR $pathology = '' OR EXISTS { MATCH (p1)-[:STUDIES]->(:Pathology {name: $pathology}) }
        WITH collect(DISTINCT {
            outcome: o1.name,
            value: a1.value,
            p_value: a1.p_value,
            direction: a1.direction,
            effect_size: a1.effect_size,
            paper_id: p1.paper_id,
            evidence_level: p1.evidence_level
        }) as int1_outcomes

        MATCH (i2:Intervention {name: $int2})-[a2:AFFECTS]->(o2:Outcome)
        OPTIONAL MATCH (p2:Paper)-[:INVESTIGATES]->(i2)
        OPTIONAL MATCH (p2)-[:STUDIES]->(:Pathology {name: $pathology})
        WITH int1_outcomes, i2, a2, o2, p2
        WHERE $pathology IS NULL OR $pathology = '' OR EXISTS { MATCH (p2)-[:STUDIES]->(:Pathology {name: $pathology}) }
        WITH int1_outcomes, collect(DISTINCT {
            outcome: o2.name,
            value: a2.value,
            p_value: a2.p_value,
            direction: a2.direction,
            effect_size: a2.effect_size,
            paper_id: p2.paper_id,
            evidence_level: p2.evidence_level
        }) as int2_outcomes

        RETURN int1_outcomes, int2_outcomes
        """

        try:
            rows = await self.client.run_query(compare_query, {
                "int1": int1,
                "int2": int2,
                "pathology": pathology or "",
            })

            if rows:
                int1_outcomes = rows[0].get("int1_outcomes", [])
                int2_outcomes = rows[0].get("int2_outcomes", [])

                int1_outcome_names = {o["outcome"] for o in int1_outcomes if o.get("outcome")}
                int2_outcome_names = {o["outcome"] for o in int2_outcomes if o.get("outcome")}

                shared_names = int1_outcome_names & int2_outcome_names

                # Build shared outcomes with both interventions' data
                for name in shared_names:
                    int1_data = next(
                        (o for o in int1_outcomes if o.get("outcome") == name), {}
                    )
                    int2_data = next(
                        (o for o in int2_outcomes if o.get("outcome") == name), {}
                    )
                    result.shared_outcomes.append({
                        "outcome": name,
                        f"{int1}_value": int1_data.get("value", ""),
                        f"{int1}_direction": int1_data.get("direction", ""),
                        f"{int1}_p_value": int1_data.get("p_value"),
                        f"{int2}_value": int2_data.get("value", ""),
                        f"{int2}_direction": int2_data.get("direction", ""),
                        f"{int2}_p_value": int2_data.get("p_value"),
                    })

                # Unique to int1
                for o in int1_outcomes:
                    if o.get("outcome") and o["outcome"] not in shared_names:
                        result.int1_only_outcomes.append(o)

                # Unique to int2
                for o in int2_outcomes:
                    if o.get("outcome") and o["outcome"] not in shared_names:
                        result.int2_only_outcomes.append(o)

                # Summary
                result.comparison_summary = (
                    f"{int1} vs {int2} for {pathology}: "
                    f"{len(shared_names)} shared outcomes, "
                    f"{len(result.int1_only_outcomes)} unique to {int1}, "
                    f"{len(result.int2_only_outcomes)} unique to {int2}"
                )

        except Exception as e:
            logger.error(
                f"Intervention comparison failed for {int1} vs {int2}: {e}",
                exc_info=True,
            )
            result.comparison_summary = f"Comparison failed: {e}"

        logger.info(
            f"Compared {int1} vs {int2}: "
            f"{len(result.shared_outcomes)} shared, "
            f"{len(result.int1_only_outcomes)} int1-only, "
            f"{len(result.int2_only_outcomes)} int2-only"
        )

        return result

    async def find_best_evidence(
        self,
        pathology: str,
        outcome_category: Optional[str] = None,
        is_a_depth: int = 2,
        limit: int = 20,
    ) -> list[BestEvidenceResult]:
        """Find highest evidence level papers + relationship chains for a pathology.

        Searches for papers studying interventions that TREATS the given pathology,
        and optionally filters by outcome category. Also expands via IS_A hierarchy.

        Args:
            pathology: Target pathology name
            outcome_category: Optional outcome name to filter on
            is_a_depth: Depth for IS_A hierarchy expansion (clamped to 1-5)
            limit: Maximum results to return

        Returns:
            List of BestEvidenceResult sorted by evidence level
        """
        # Clamp is_a_depth to safe range (1-5)
        is_a_depth = min(max(int(is_a_depth), 1), 5)

        # Search papers for pathology + IS_A expanded pathologies
        query = f"""
        MATCH (path:Pathology {{name: $pathology}})
        OPTIONAL MATCH (child:Pathology)-[:IS_A*0..{is_a_depth}]->(path)
        WITH collect(DISTINCT path) + collect(DISTINCT child) as all_pathologies
        UNWIND all_pathologies as target_path
        MATCH (i:Intervention)-[:TREATS]->(target_path)
        MATCH (p:Paper)-[:INVESTIGATES]->(i)
        OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
        WITH p, i, collect(DISTINCT o.name) as outcomes,
             collect(DISTINCT {{
                 outcome: o.name,
                 direction: a.direction,
                 p_value: a.p_value
             }}) as outcome_details
        RETURN DISTINCT
            p.paper_id as paper_id,
            p.title as title,
            p.year as year,
            p.evidence_level as evidence_level,
            collect(DISTINCT i.name) as interventions,
            outcomes,
            outcome_details
        ORDER BY
            CASE p.evidence_level
                WHEN '1a' THEN 1
                WHEN '1b' THEN 2
                WHEN '2a' THEN 3
                WHEN '2b' THEN 4
                WHEN '3' THEN 5
                WHEN '4' THEN 6
                ELSE 7
            END ASC,
            p.year DESC
        LIMIT $limit
        """

        results = []
        try:
            rows = await self.client.run_query(query, {
                "pathology": pathology,
                "limit": limit,
            })

            for row in rows:
                outcomes = row.get("outcomes", [])
                if outcome_category:
                    if outcome_category not in outcomes:
                        continue

                chain = []
                for int_name in row.get("interventions", []):
                    chain.append(EvidenceChainLink(
                        source_node=int_name,
                        relationship="TREATS",
                        target_node=pathology,
                    ))
                for out_name in outcomes:
                    if out_name:
                        chain.append(EvidenceChainLink(
                            source_node=row.get("interventions", [""])[0],
                            relationship="AFFECTS",
                            target_node=out_name,
                        ))

                results.append(BestEvidenceResult(
                    paper_id=row.get("paper_id", ""),
                    title=row.get("title", ""),
                    evidence_level=row.get("evidence_level", "5") or "5",
                    year=row.get("year", 0) or 0,
                    interventions=row.get("interventions", []),
                    outcomes=[o for o in outcomes if o],
                    outcome_details=[
                        d for d in row.get("outcome_details", [])
                        if d.get("outcome")
                    ],
                    evidence_chain=chain,
                ))

        except Exception as e:
            logger.error(
                f"Best evidence search failed for {pathology}: {e}",
                exc_info=True,
            )

        logger.info(
            f"Best evidence for {pathology}: {len(results)} papers found"
        )

        return results
