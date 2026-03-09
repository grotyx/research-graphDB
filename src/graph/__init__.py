"""Graph module for Neo4j integration.

Spine-specific GraphRAG with:
- Neo4j Graph Database
- Entity Normalization
- Taxonomy Management
- Relationship Building
- Inference Rules (Transitive reasoning, Comparability, Evidence aggregation)
"""

from .spine_schema import (
    SpineSubDomain,
    EvidenceLevel,
    PaperNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
    AffectsRelation,
    SpineGraphSchema,
)

from .inference_rules import (
    InferenceRule,
    InferenceRuleType,
    InferenceEngine,
    TRANSITIVE_HIERARCHY,
    TRANSITIVE_DESCENDANTS,
    TRANSITIVE_TREATMENT,
    COMPARABLE_SIBLINGS,
    COMPARABLE_BY_CATEGORY,
    COMPARISON_PAPERS,
    AGGREGATE_EVIDENCE,
    AGGREGATE_EVIDENCE_BY_PATHOLOGY,
    COMBINED_OUTCOMES,
    CONFLICT_DETECTION,
    CROSS_INTERVENTION_CONFLICTS,
    INDIRECT_TREATMENT,
)

__all__ = [
    # Schema
    "SpineSubDomain",
    "EvidenceLevel",
    "PaperNode",
    "PathologyNode",
    "AnatomyNode",
    "InterventionNode",
    "OutcomeNode",
    "AffectsRelation",
    "SpineGraphSchema",

    # Inference
    "InferenceRule",
    "InferenceRuleType",
    "InferenceEngine",
    "TRANSITIVE_HIERARCHY",
    "TRANSITIVE_DESCENDANTS",
    "TRANSITIVE_TREATMENT",
    "COMPARABLE_SIBLINGS",
    "COMPARABLE_BY_CATEGORY",
    "COMPARISON_PAPERS",
    "AGGREGATE_EVIDENCE",
    "AGGREGATE_EVIDENCE_BY_PATHOLOGY",
    "COMBINED_OUTCOMES",
    "CONFLICT_DETECTION",
    "CROSS_INTERVENTION_CONFLICTS",
    "INDIRECT_TREATMENT",
]
