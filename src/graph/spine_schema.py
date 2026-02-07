"""Spine Graph Schema for Neo4j.

척추 수술 특화 그래프 스키마 정의.
- Node types: Paper, Pathology, Anatomy, Intervention, Outcome
- Relationship types: STUDIES, TREATS, AFFECTS, IS_A, etc.

Note: This file is a re-export module for backward compatibility.
All classes are now organized in the `types/` subpackage:
    - types/enums.py: Enum classes
    - types/core_nodes.py: Core node dataclasses
    - types/extended_nodes.py: Extended node dataclasses (v7.x)
    - types/relationships.py: Relationship dataclasses
    - types/schema.py: SpineGraphSchema and CypherTemplates

Usage:
    # Old import (still works)
    from graph.spine_schema import PaperNode, EvidenceLevel

    # New import (recommended for specific imports)
    from graph.types.core_nodes import PaperNode
    from graph.types.enums import EvidenceLevel
"""

# =============================================================================
# Re-export all types from the types subpackage
# =============================================================================

# Enums
from .types.enums import (
    SpineSubDomain,
    EvidenceLevel,
    StudyDesign,
    OutcomeType,
    InterventionCategory,
    PaperRelationType,
    DocumentType,
    EntityCategory,
    CitationContext,
)

# Core Nodes
from .types.core_nodes import (
    PaperNode,
    ChunkNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
)

# Extended Nodes (v7.x)
from .types.extended_nodes import (
    ConceptNode,
    TechniqueNode,
    RecommendationNode,
    InstrumentNode,
    ImplantNode,
    ComplicationNode,
    DrugNode,
    SurgicalStepNode,
    OutcomeMeasureNode,
    RadiographicParameterNode,
    PredictionModelNode,
    RiskFactorNode,
    PatientCohortNode,
    FollowUpNode,
    CostNode,
    QualityMetricNode,
)

# Relationships
from .types.relationships import (
    StudiesRelation,
    HasChunkRelation,
    LocatedAtRelation,
    InvestigatesRelation,
    TreatsRelation,
    AffectsRelation,
    IsARelation,
    PaperRelation,
    CitesRelationship,
    PaperRelationship,
    CausesRelation,
    HasRiskFactorRelation,
    PredictsRelation,
    CorrelatesRelation,
    UsesDeviceRelation,
    HasCohortRelation,
    TreatedWithRelation,
    HasFollowUpRelation,
    ReportsOutcomeAtRelation,
    ReportsCostRelation,
    CostAssociatedWithRelation,
    HasQualityMetricRelation,
)

# Schema and Cypher Templates
from .types.schema import (
    SpineGraphSchema,
    CypherTemplates,
)

# =============================================================================
# All exports (for `from spine_schema import *`)
# =============================================================================
__all__ = [
    # Enums
    "SpineSubDomain",
    "EvidenceLevel",
    "StudyDesign",
    "OutcomeType",
    "InterventionCategory",
    "PaperRelationType",
    "DocumentType",
    "EntityCategory",
    "CitationContext",
    # Core Nodes
    "PaperNode",
    "ChunkNode",
    "PathologyNode",
    "AnatomyNode",
    "InterventionNode",
    "OutcomeNode",
    # Extended Nodes
    "ConceptNode",
    "TechniqueNode",
    "RecommendationNode",
    "InstrumentNode",
    "ImplantNode",
    "ComplicationNode",
    "DrugNode",
    "SurgicalStepNode",
    "OutcomeMeasureNode",
    "RadiographicParameterNode",
    "PredictionModelNode",
    "RiskFactorNode",
    "PatientCohortNode",
    "FollowUpNode",
    "CostNode",
    "QualityMetricNode",
    # Relationships
    "StudiesRelation",
    "HasChunkRelation",
    "LocatedAtRelation",
    "InvestigatesRelation",
    "TreatsRelation",
    "AffectsRelation",
    "IsARelation",
    "PaperRelation",
    "CitesRelationship",
    "PaperRelationship",
    "CausesRelation",
    "HasRiskFactorRelation",
    "PredictsRelation",
    "CorrelatesRelation",
    "UsesDeviceRelation",
    "HasCohortRelation",
    "TreatedWithRelation",
    "HasFollowUpRelation",
    "ReportsOutcomeAtRelation",
    "ReportsCostRelation",
    "CostAssociatedWithRelation",
    "HasQualityMetricRelation",
    # Schema
    "SpineGraphSchema",
    "CypherTemplates",
]
