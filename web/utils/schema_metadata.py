"""Schema Metadata for Spine GraphRAG Visualization.

Defines node types, relationship types, categories, colors, and descriptions
for the schema overview visualization.

Version: v7.14.25
"""

from dataclasses import dataclass
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# NODE TYPE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

@dataclass
class NodeTypeInfo:
    """Information about a node type in the schema."""
    label: str
    category: str  # "Core", "Extended", "v7.2"
    description: str
    key_properties: list[str]
    color: str
    icon: str


# Core Nodes (6)
CORE_NODES = {
    "Paper": NodeTypeInfo(
        label="Paper",
        category="Core",
        description="Research paper with metadata, evidence level, and extracted entities",
        key_properties=["paper_id", "title", "year", "evidence_level", "sub_domain", "authors"],
        color="#22c55e",  # Green
        icon="📄"
    ),
    "Chunk": NodeTypeInfo(
        label="Chunk",
        category="Core",
        description="Text chunk with 3072-dim vector embedding for semantic search",
        key_properties=["chunk_id", "paper_id", "tier", "section", "embedding"],
        color="#94a3b8",  # Gray
        icon="📝"
    ),
    "Pathology": NodeTypeInfo(
        label="Pathology",
        category="Core",
        description="Spinal diseases/diagnoses (degenerative, deformity, trauma, tumor)",
        key_properties=["name", "category", "snomed_code", "icd10_code", "aliases"],
        color="#ef4444",  # Red
        icon="🏥"
    ),
    "Anatomy": NodeTypeInfo(
        label="Anatomy",
        category="Core",
        description="Spinal anatomical locations (C1-C7, T1-T12, L1-L5, S1-S5)",
        key_properties=["name", "region", "level_count"],
        color="#8b5cf6",  # Purple
        icon="🦴"
    ),
    "Intervention": NodeTypeInfo(
        label="Intervention",
        category="Core",
        description="Surgical procedures with taxonomy hierarchy (IS_A relationships)",
        key_properties=["name", "category", "approach", "is_minimally_invasive", "snomed_code"],
        color="#3b82f6",  # Blue
        icon="🔧"
    ),
    "Outcome": NodeTypeInfo(
        label="Outcome",
        category="Core",
        description="Clinical outcomes/measurements (VAS, ODI, fusion rate, etc.)",
        key_properties=["name", "type", "unit", "direction", "snomed_code"],
        color="#f97316",  # Orange
        icon="📊"
    ),
}

# Extended Nodes (11)
EXTENDED_NODES = {
    "Concept": NodeTypeInfo(
        label="Concept",
        category="Extended",
        description="Educational/theoretical concepts from literature",
        key_properties=["name", "category", "definition", "importance"],
        color="#a855f7",  # Light Purple
        icon="💡"
    ),
    "Recommendation": NodeTypeInfo(
        label="Recommendation",
        category="Extended",
        description="Clinical guideline recommendations with GRADE levels",
        key_properties=["name", "grade", "strength", "evidence_level", "source_guideline"],
        color="#ec4899",  # Pink
        icon="📋"
    ),
    "Implant": NodeTypeInfo(
        label="Implant",
        category="Extended",
        description="Medical devices and surgical instruments",
        key_properties=["name", "device_type", "implant_category", "material", "manufacturer"],
        color="#6366f1",  # Indigo
        icon="🔩"
    ),
    "Complication": NodeTypeInfo(
        label="Complication",
        category="Extended",
        description="Surgical complications with severity and management",
        key_properties=["name", "category", "severity", "incidence_range", "prevention"],
        color="#dc2626",  # Dark Red
        icon="⚠️"
    ),
    "Drug": NodeTypeInfo(
        label="Drug",
        category="Extended",
        description="Pharmacological agents used in spine treatment",
        key_properties=["name", "generic_name", "brand_names", "mechanism", "indications"],
        color="#14b8a6",  # Teal
        icon="💊"
    ),
    "OutcomeMeasure": NodeTypeInfo(
        label="OutcomeMeasure",
        category="Extended",
        description="Standardized outcome assessment tools (ODI, VAS, SF-36, PROMIS)",
        key_properties=["name", "scale_min", "scale_max", "mcid", "domains_measured"],
        color="#f59e0b",  # Amber
        icon="📐"
    ),
    "RadioParameter": NodeTypeInfo(
        label="RadioParameter",
        category="Extended",
        description="Radiographic parameters (PI, LL, SVA, Cobb angle)",
        key_properties=["name", "unit", "normal_range", "is_fixed_parameter"],
        color="#0ea5e9",  # Sky Blue
        icon="📷"
    ),
    "PredictionModel": NodeTypeInfo(
        label="PredictionModel",
        category="Extended",
        description="ML/AI predictive models for clinical outcomes",
        key_properties=["name", "model_type", "prediction_target", "auc", "accuracy"],
        color="#84cc16",  # Lime
        icon="🤖"
    ),
    "RiskFactor": NodeTypeInfo(
        label="RiskFactor",
        category="Extended",
        description="Patient risk factors (demographics, comorbidities)",
        key_properties=["name", "category", "variable_type", "typical_or", "is_modifiable"],
        color="#f43f5e",  # Rose
        icon="🎯"
    ),
}

# v7.2 Extended Nodes (4)
V72_NODES = {
    "PatientCohort": NodeTypeInfo(
        label="PatientCohort",
        category="v7.2",
        description="Study population characteristics with demographics",
        key_properties=["name", "cohort_type", "sample_size", "mean_age", "baseline_vas"],
        color="#06b6d4",  # Cyan
        icon="👥"
    ),
    "FollowUp": NodeTypeInfo(
        label="FollowUp",
        category="v7.2",
        description="Follow-up timepoint data with outcome measurements",
        key_properties=["name", "timepoint_months", "completeness_rate", "vas_score"],
        color="#10b981",  # Emerald
        icon="📅"
    ),
    "Cost": NodeTypeInfo(
        label="Cost",
        category="v7.2",
        description="Healthcare cost analysis (direct, indirect, ICER)",
        key_properties=["name", "cost_type", "mean_cost", "qaly_gained", "icer"],
        color="#eab308",  # Yellow
        icon="💰"
    ),
    "QualityMetric": NodeTypeInfo(
        label="QualityMetric",
        category="v7.2",
        description="Study quality assessments (GRADE, MINORS, Cochrane ROB)",
        key_properties=["name", "assessment_tool", "overall_score", "grade_certainty"],
        color="#78716c",  # Stone
        icon="⭐"
    ),
}

# Combined node type dictionary
NODE_TYPE_INFO = {**CORE_NODES, **EXTENDED_NODES, **V72_NODES}


# ═══════════════════════════════════════════════════════════════
# RELATIONSHIP TYPE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

@dataclass
class RelationshipTypeInfo:
    """Information about a relationship type in the schema."""
    type: str
    source: str
    target: str
    category: str  # "Core", "Paper-to-Paper", "Extended", "v7.2"
    description: str
    key_properties: list[str]
    color: str


# Core Relationships (8)
CORE_RELATIONSHIPS = {
    "STUDIES": RelationshipTypeInfo(
        type="STUDIES",
        source="Paper",
        target="Pathology",
        category="Core",
        description="Paper studies a disease/pathology",
        key_properties=["is_primary"],
        color="#ef4444"
    ),
    "HAS_CHUNK": RelationshipTypeInfo(
        type="HAS_CHUNK",
        source="Paper",
        target="Chunk",
        category="Core",
        description="Paper contains text chunks",
        key_properties=["chunk_index"],
        color="#94a3b8"
    ),
    "LOCATED_AT": RelationshipTypeInfo(
        type="LOCATED_AT",
        source="Pathology",
        target="Anatomy",
        category="Core",
        description="Disease is located at anatomical region",
        key_properties=[],
        color="#8b5cf6"
    ),
    "INVESTIGATES": RelationshipTypeInfo(
        type="INVESTIGATES",
        source="Paper",
        target="Intervention",
        category="Core",
        description="Paper investigates a surgical intervention",
        key_properties=["is_comparison"],
        color="#3b82f6"
    ),
    "AFFECTS": RelationshipTypeInfo(
        type="AFFECTS",
        source="Intervention",
        target="Outcome",
        category="Core",
        description="Intervention affects an outcome (core inference path)",
        key_properties=["p_value", "effect_size", "is_significant", "direction", "value"],
        color="#f97316"
    ),
    "TREATS": RelationshipTypeInfo(
        type="TREATS",
        source="Intervention",
        target="Pathology",
        category="Core",
        description="Intervention treats a pathology",
        key_properties=["indication", "contraindication", "indication_level"],
        color="#22c55e"
    ),
    "IS_A": RelationshipTypeInfo(
        type="IS_A",
        source="Intervention",
        target="Intervention",
        category="Core",
        description="Intervention taxonomy hierarchy (e.g., TLIF IS_A Interbody Fusion)",
        key_properties=["level"],
        color="#6366f1"
    ),
    "INVOLVES": RelationshipTypeInfo(
        type="INVOLVES",
        source="Paper",
        target="Anatomy",
        category="Core",
        description="Paper involves spinal anatomical region",
        key_properties=[],
        color="#8b5cf6"
    ),
}

# Paper-to-Paper Relationships (6)
PAPER_RELATIONSHIPS = {
    "CITES": RelationshipTypeInfo(
        type="CITES",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Paper cites another paper (important citations)",
        key_properties=["context", "section", "citation_text", "confidence"],
        color="#64748b"
    ),
    "SUPPORTS": RelationshipTypeInfo(
        type="SUPPORTS",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Paper supports findings of another paper",
        key_properties=["confidence", "evidence", "detected_by"],
        color="#22c55e"
    ),
    "CONTRADICTS": RelationshipTypeInfo(
        type="CONTRADICTS",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Paper contradicts findings of another paper",
        key_properties=["confidence", "evidence"],
        color="#ef4444"
    ),
    "SIMILAR_TOPIC": RelationshipTypeInfo(
        type="SIMILAR_TOPIC",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Papers share similar research topic",
        key_properties=["confidence"],
        color="#a855f7"
    ),
    "EXTENDS": RelationshipTypeInfo(
        type="EXTENDS",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Paper is a follow-up/extension study",
        key_properties=["confidence"],
        color="#3b82f6"
    ),
    "REPLICATES": RelationshipTypeInfo(
        type="REPLICATES",
        source="Paper",
        target="Paper",
        category="Paper-to-Paper",
        description="Paper is a replication study",
        key_properties=["confidence"],
        color="#06b6d4"
    ),
}

# Extended Relationships (7)
EXTENDED_RELATIONSHIPS = {
    "CAUSES": RelationshipTypeInfo(
        type="CAUSES",
        source="Intervention",
        target="Complication",
        category="Extended",
        description="Intervention causes complication with incidence rate",
        key_properties=["incidence_rate", "incidence_ci", "surgery_type", "timing"],
        color="#dc2626"
    ),
    "HAS_RISK_FACTOR": RelationshipTypeInfo(
        type="HAS_RISK_FACTOR",
        source="Paper",
        target="RiskFactor",
        category="Extended",
        description="Paper reports risk factor associations",
        key_properties=["odds_ratio", "hazard_ratio", "relative_risk", "p_value"],
        color="#f43f5e"
    ),
    "PREDICTS": RelationshipTypeInfo(
        type="PREDICTS",
        source="PredictionModel",
        target="Outcome",
        category="Extended",
        description="Model predicts clinical outcome",
        key_properties=["auc", "accuracy", "sensitivity", "specificity"],
        color="#84cc16"
    ),
    "CORRELATES": RelationshipTypeInfo(
        type="CORRELATES",
        source="RadioParameter",
        target="OutcomeMeasure",
        category="Extended",
        description="Radiographic parameter correlates with outcome",
        key_properties=["r_value", "p_value", "correlation_type"],
        color="#0ea5e9"
    ),
    "USES_DEVICE": RelationshipTypeInfo(
        type="USES_DEVICE",
        source="Intervention",
        target="Implant",
        category="Extended",
        description="Intervention uses medical device/implant",
        key_properties=["usage_type", "is_required"],
        color="#6366f1"
    ),
    "MEASURED_BY": RelationshipTypeInfo(
        type="MEASURED_BY",
        source="Outcome",
        target="OutcomeMeasure",
        category="Extended",
        description="Outcome is measured by standardized tool",
        key_properties=["timepoint"],
        color="#f59e0b"
    ),
    "RECOMMENDED_FOR": RelationshipTypeInfo(
        type="RECOMMENDED_FOR",
        source="Recommendation",
        target="Pathology",
        category="Extended",
        description="Clinical recommendation for a pathology",
        key_properties=["grade", "strength"],
        color="#ec4899"
    ),
}

# v7.2 Extended Relationships (7)
V72_RELATIONSHIPS = {
    "HAS_COHORT": RelationshipTypeInfo(
        type="HAS_COHORT",
        source="Paper",
        target="PatientCohort",
        category="v7.2",
        description="Paper has study cohort",
        key_properties=["is_primary", "role"],
        color="#06b6d4"
    ),
    "TREATED_WITH": RelationshipTypeInfo(
        type="TREATED_WITH",
        source="PatientCohort",
        target="Intervention",
        category="v7.2",
        description="Cohort was treated with intervention",
        key_properties=["n_patients"],
        color="#3b82f6"
    ),
    "HAS_FOLLOWUP": RelationshipTypeInfo(
        type="HAS_FOLLOWUP",
        source="Paper",
        target="FollowUp",
        category="v7.2",
        description="Paper has follow-up timepoint data",
        key_properties=["is_primary_endpoint"],
        color="#10b981"
    ),
    "REPORTS_OUTCOME": RelationshipTypeInfo(
        type="REPORTS_OUTCOME",
        source="FollowUp",
        target="Outcome",
        category="v7.2",
        description="Follow-up reports outcome value",
        key_properties=["value", "baseline_value", "improvement"],
        color="#f97316"
    ),
    "REPORTS_COST": RelationshipTypeInfo(
        type="REPORTS_COST",
        source="Paper",
        target="Cost",
        category="v7.2",
        description="Paper reports cost analysis",
        key_properties=["is_primary_analysis"],
        color="#eab308"
    ),
    "ASSOCIATED_WITH": RelationshipTypeInfo(
        type="ASSOCIATED_WITH",
        source="Cost",
        target="Intervention",
        category="v7.2",
        description="Cost is associated with intervention",
        key_properties=["cost_value"],
        color="#eab308"
    ),
    "HAS_QUALITY_METRIC": RelationshipTypeInfo(
        type="HAS_QUALITY_METRIC",
        source="Paper",
        target="QualityMetric",
        category="v7.2",
        description="Paper has quality assessment",
        key_properties=["assessed_by", "assessment_type"],
        color="#78716c"
    ),
}

# Combined relationship type dictionary
RELATIONSHIP_TYPE_INFO = {
    **CORE_RELATIONSHIPS,
    **PAPER_RELATIONSHIPS,
    **EXTENDED_RELATIONSHIPS,
    **V72_RELATIONSHIPS
}


# ═══════════════════════════════════════════════════════════════
# CATEGORY COLOR SCHEMES
# ═══════════════════════════════════════════════════════════════

NODE_CATEGORY_COLORS = {
    "Core": {
        "primary": "#3b82f6",  # Blue
        "background": "#dbeafe",
        "border": "#1e40af"
    },
    "Extended": {
        "primary": "#8b5cf6",  # Purple
        "background": "#ede9fe",
        "border": "#6d28d9"
    },
    "v7.2": {
        "primary": "#f97316",  # Orange
        "background": "#ffedd5",
        "border": "#c2410c"
    }
}

RELATIONSHIP_CATEGORY_COLORS = {
    "Core": "#3b82f6",
    "Paper-to-Paper": "#64748b",
    "Extended": "#8b5cf6",
    "v7.2": "#f97316"
}


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_node_info(label: str) -> Optional[NodeTypeInfo]:
    """Get NodeTypeInfo for a given label."""
    return NODE_TYPE_INFO.get(label)


def get_relationship_info(rel_type: str) -> Optional[RelationshipTypeInfo]:
    """Get RelationshipTypeInfo for a given relationship type."""
    return RELATIONSHIP_TYPE_INFO.get(rel_type)


def get_nodes_by_category(category: str) -> dict[str, NodeTypeInfo]:
    """Get all nodes in a category."""
    return {k: v for k, v in NODE_TYPE_INFO.items() if v.category == category}


def get_relationships_by_category(category: str) -> dict[str, RelationshipTypeInfo]:
    """Get all relationships in a category."""
    return {k: v for k, v in RELATIONSHIP_TYPE_INFO.items() if v.category == category}


def get_all_node_labels() -> list[str]:
    """Get all node labels."""
    return list(NODE_TYPE_INFO.keys())


def get_all_relationship_types() -> list[str]:
    """Get all relationship types."""
    return list(RELATIONSHIP_TYPE_INFO.keys())
