"""Clinical Data Handler for Medical KAG Server.

This module handles clinical data queries including patient cohorts,
follow-up data, cost analysis, and quality metrics.

Extracted from medical_kag_server.py (v1.5) - Lines 2935-3279
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ClinicalDataHandler:
    """Handler for clinical data queries.

    Provides access to patient cohort information, follow-up data,
    cost-effectiveness analysis, and research quality metrics.

    Attributes:
        server: Reference to MedicalKAGServer instance for accessing
               neo4j_client and current_user.
    """

    def __init__(self, server):
        """Initialize clinical data handler.

        Args:
            server: MedicalKAGServer instance providing neo4j_client access.
        """
        self.server = server
        self.neo4j_client = server.neo4j_client
        self.current_user = server.current_user

    async def get_patient_cohorts(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        cohort_type: Optional[str] = None,
        min_sample_size: Optional[int] = None
    ) -> dict:
        """환자 코호트 정보 조회 (v1.2).

        Queries patient cohort information from papers, optionally filtered by
        paper ID, intervention type, cohort type, and minimum sample size.

        Args:
            paper_id: Optional paper ID to filter by specific paper.
            intervention: Optional intervention name to filter cohorts.
            cohort_type: Optional cohort type (e.g., 'treatment', 'control').
            min_sample_size: Optional minimum sample size threshold.

        Returns:
            Dictionary containing:
                - success (bool): Query success status
                - total_cohorts (int): Number of cohorts found
                - cohorts (list): List of cohort records with patient demographics
                - filters (dict): Applied filter parameters
                - error (str): Error message if success is False

        Example:
            >>> result = await handler.get_patient_cohorts(
            ...     intervention="BESS",
            ...     min_sample_size=50
            ... )
            >>> print(f"Found {result['total_cohorts']} cohorts")
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            # 동적 필터 구성
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if cohort_type:
                where_clauses.append("c.cohort_type = $cohort_type")
                params["cohort_type"] = cohort_type

            if min_sample_size:
                where_clauses.append("c.sample_size >= $min_sample_size")
                params["min_sample_size"] = min_sample_size

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                # 수술법으로 필터링 - TREATED_WITH 관계 사용
                cypher = f"""
                MATCH (p:Paper)-[:HAS_COHORT]->(c:PatientCohort)-[:TREATED_WITH]->(i:Intervention {{name: $intervention}})
                WHERE {where_clause}
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       c.name AS cohort_name, c.cohort_type AS cohort_type,
                       c.sample_size AS sample_size, c.mean_age AS mean_age,
                       c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
                       c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
                       c.BMI AS bmi, i.name AS intervention
                ORDER BY c.sample_size DESC
                LIMIT 50
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:HAS_COHORT]->(c:PatientCohort)
                WHERE {where_clause}
                OPTIONAL MATCH (c)-[:TREATED_WITH]->(i:Intervention)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       c.name AS cohort_name, c.cohort_type AS cohort_type,
                       c.sample_size AS sample_size, c.mean_age AS mean_age,
                       c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
                       c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
                       c.BMI AS bmi, collect(i.name) AS interventions
                ORDER BY c.sample_size DESC
                LIMIT 50
                """

            records = await self.neo4j_client.run_query(cypher, params)

            cohorts = []
            for r in records:
                cohorts.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "cohort_name": r.get("cohort_name"),
                    "cohort_type": r.get("cohort_type"),
                    "sample_size": r.get("sample_size"),
                    "mean_age": r.get("mean_age"),
                    "female_percentage": r.get("female_percentage"),
                    "diagnosis": r.get("diagnosis"),
                    "comorbidities": r.get("comorbidities"),
                    "asa_score": r.get("asa_score"),
                    "bmi": r.get("bmi"),
                    "intervention": r.get("intervention") or r.get("interventions"),
                })

            return {
                "success": True,
                "total_cohorts": len(cohorts),
                "cohorts": cohorts,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "cohort_type": cohort_type,
                    "min_sample_size": min_sample_size,
                }
            }

        except Exception as e:
            logger.error(f"get_patient_cohorts failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_followup_data(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        min_months: Optional[int] = None,
        max_months: Optional[int] = None
    ) -> dict:
        """추적관찰 데이터 조회 (v1.2).

        Retrieves follow-up data from clinical studies, including timepoints,
        completeness rates, and associated outcomes.

        Args:
            paper_id: Optional paper ID to filter by specific paper.
            intervention: Optional intervention name to filter follow-up data.
            min_months: Optional minimum follow-up duration in months.
            max_months: Optional maximum follow-up duration in months.

        Returns:
            Dictionary containing:
                - success (bool): Query success status
                - total_followups (int): Number of follow-up records found
                - followups (list): List of follow-up records with outcomes
                - filters (dict): Applied filter parameters
                - error (str): Error message if success is False

        Example:
            >>> result = await handler.get_followup_data(
            ...     intervention="BESS",
            ...     min_months=12,
            ...     max_months=24
            ... )
            >>> for fu in result['followups']:
            ...     print(f"{fu['timepoint_months']} months: {fu['outcomes']}")
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if min_months:
                where_clauses.append("f.timepoint_months >= $min_months")
                params["min_months"] = min_months

            if max_months:
                where_clauses.append("f.timepoint_months <= $max_months")
                params["max_months"] = max_months

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                cypher = f"""
                MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention {{name: $intervention}})
                MATCH (p)-[:HAS_FOLLOWUP]->(f:FollowUp)
                WHERE {where_clause}
                OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
                       f.completeness_rate AS completeness_rate,
                       collect(DISTINCT o.name) AS outcomes
                ORDER BY f.timepoint_months
                LIMIT 100
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:HAS_FOLLOWUP]->(f:FollowUp)
                WHERE {where_clause}
                OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
                       f.completeness_rate AS completeness_rate,
                       collect(DISTINCT o.name) AS outcomes
                ORDER BY f.timepoint_months
                LIMIT 100
                """

            records = await self.neo4j_client.run_query(cypher, params)

            followups = []
            for r in records:
                followups.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "timepoint_name": r.get("timepoint_name"),
                    "timepoint_months": r.get("timepoint_months"),
                    "completeness_rate": r.get("completeness_rate"),
                    "outcomes": r.get("outcomes") or [],
                })

            return {
                "success": True,
                "total_followups": len(followups),
                "followups": followups,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "min_months": min_months,
                    "max_months": max_months,
                }
            }

        except Exception as e:
            logger.error(f"get_followup_data failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_cost_analysis(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        cost_type: Optional[str] = None
    ) -> dict:
        """비용 효과 분석 데이터 조회 (v1.2).

        Queries cost-effectiveness analysis data including direct costs,
        quality-adjusted life years (QALY), incremental cost-effectiveness
        ratio (ICER), and hospital metrics.

        Args:
            paper_id: Optional paper ID to filter by specific paper.
            intervention: Optional intervention name to filter cost data.
            cost_type: Optional cost type (e.g., 'direct', 'indirect', 'total').

        Returns:
            Dictionary containing:
                - success (bool): Query success status
                - total_cost_records (int): Number of cost records found
                - costs (list): List of cost records with economic metrics
                - filters (dict): Applied filter parameters
                - error (str): Error message if success is False

        Example:
            >>> result = await handler.get_cost_analysis(
            ...     intervention="BESS",
            ...     cost_type="direct"
            ... )
            >>> for cost in result['costs']:
            ...     print(f"{cost['mean_cost']} {cost['currency']}")
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if cost_type:
                where_clauses.append("cost.cost_type = $cost_type")
                params["cost_type"] = cost_type

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                cypher = f"""
                MATCH (p:Paper)-[:REPORTS_COST]->(cost:Cost)-[:ASSOCIATED_WITH]->(i:Intervention {{name: $intervention}})
                WHERE {where_clause}
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       cost.name AS cost_name, cost.cost_type AS cost_type,
                       cost.mean_cost AS mean_cost, cost.currency AS currency,
                       cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
                       cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
                       i.name AS intervention
                ORDER BY cost.mean_cost DESC
                LIMIT 50
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:REPORTS_COST]->(cost:Cost)
                WHERE {where_clause}
                OPTIONAL MATCH (cost)-[:ASSOCIATED_WITH]->(i:Intervention)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       cost.name AS cost_name, cost.cost_type AS cost_type,
                       cost.mean_cost AS mean_cost, cost.currency AS currency,
                       cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
                       cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
                       collect(i.name) AS interventions
                ORDER BY cost.mean_cost DESC
                LIMIT 50
                """

            records = await self.neo4j_client.run_query(cypher, params)

            costs = []
            for r in records:
                costs.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "cost_name": r.get("cost_name"),
                    "cost_type": r.get("cost_type"),
                    "mean_cost": r.get("mean_cost"),
                    "currency": r.get("currency"),
                    "qaly_gained": r.get("qaly_gained"),
                    "icer": r.get("icer"),
                    "los_days": r.get("los_days"),
                    "readmission_rate": r.get("readmission_rate"),
                    "intervention": r.get("intervention") or r.get("interventions"),
                })

            return {
                "success": True,
                "total_cost_records": len(costs),
                "costs": costs,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "cost_type": cost_type,
                }
            }

        except Exception as e:
            logger.error(f"get_cost_analysis failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_quality_metrics(
        self,
        paper_id: Optional[str] = None,
        assessment_tool: Optional[str] = None,
        min_rating: Optional[str] = None
    ) -> dict:
        """연구 품질 평가 지표 조회 (v1.2).

        Retrieves research quality assessment metrics using standardized tools
        (e.g., Cochrane Risk of Bias, GRADE, Newcastle-Ottawa Scale).

        Args:
            paper_id: Optional paper ID to filter by specific paper.
            assessment_tool: Optional tool name (e.g., 'Cochrane', 'GRADE').
            min_rating: Optional minimum quality rating threshold
                       ('high', 'moderate', 'low', 'very low').

        Returns:
            Dictionary containing:
                - success (bool): Query success status
                - total_metrics (int): Number of quality metric records found
                - quality_metrics (list): List of quality assessment records
                - filters (dict): Applied filter parameters
                - error (str): Error message if success is False

        Example:
            >>> result = await handler.get_quality_metrics(
            ...     assessment_tool="GRADE",
            ...     min_rating="moderate"
            ... )
            >>> for metric in result['quality_metrics']:
            ...     print(f"{metric['overall_rating']}: {metric['overall_score']}")
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if assessment_tool:
                where_clauses.append("q.assessment_tool = $assessment_tool")
                params["assessment_tool"] = assessment_tool

            if min_rating:
                # 품질 등급 필터: high > moderate > low > very low
                rating_order = {"high": 4, "moderate": 3, "low": 2, "very low": 1}
                min_order = rating_order.get(min_rating, 0)
                where_clauses.append("""
                CASE q.overall_rating
                    WHEN 'high' THEN 4
                    WHEN 'moderate' THEN 3
                    WHEN 'low' THEN 2
                    WHEN 'very low' THEN 1
                    ELSE 0
                END >= $min_order
                """)
                params["min_order"] = min_order

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            cypher = f"""
            MATCH (p:Paper)-[:HAS_QUALITY_METRIC]->(q:QualityMetric)
            WHERE {where_clause}
            RETURN p.paper_id AS paper_id, p.title AS paper_title,
                   q.name AS metric_name, q.assessment_tool AS assessment_tool,
                   q.overall_score AS overall_score, q.overall_rating AS overall_rating,
                   q.domain_scores AS domain_scores
            ORDER BY q.overall_score DESC
            LIMIT 50
            """

            records = await self.neo4j_client.run_query(cypher, params)

            metrics = []
            for r in records:
                metrics.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "metric_name": r.get("metric_name"),
                    "assessment_tool": r.get("assessment_tool"),
                    "overall_score": r.get("overall_score"),
                    "overall_rating": r.get("overall_rating"),
                    "domain_scores": r.get("domain_scores"),
                })

            return {
                "success": True,
                "total_metrics": len(metrics),
                "quality_metrics": metrics,
                "filters": {
                    "paper_id": paper_id,
                    "assessment_tool": assessment_tool,
                    "min_rating": min_rating,
                }
            }

        except Exception as e:
            logger.error(f"get_quality_metrics failed: {e}")
            return {"success": False, "error": str(e)}
