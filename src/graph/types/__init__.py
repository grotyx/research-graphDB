"""Spine Graph Schema Types.

This package contains all type definitions for the Spine GraphRAG system.
Organized into modules for better maintainability and import optimization.

Modules:
    enums: All enumeration types (SpineSubDomain, EvidenceLevel, etc.)
    core_nodes: Core node types (PaperNode, ChunkNode, etc.)
    extended_nodes: Extended node types (PatientCohortNode, FollowUpNode, etc.)
    relationships: All relationship types (StudiesRelation, AffectsRelation, etc.)
    schema: SpineGraphSchema and CypherTemplates
"""

# =============================================================================
# Enums
# =============================================================================
from .enums import (
    SpineSubDomain,
    EvidenceLevel,
    StudyDesign,
    normalize_study_design,
    OutcomeType,
    InterventionCategory,
    PaperRelationType,
    DocumentType,
    EntityCategory,
    CitationContext,
)

# =============================================================================
# Core Nodes
# =============================================================================
from .core_nodes import (
    PaperNode,
    ChunkNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
)

# =============================================================================
# Extended Nodes (v7.x)
# =============================================================================
from .extended_nodes import (
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

# =============================================================================
# Relationships
# =============================================================================
from .relationships import (
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

# =============================================================================
# Schema and Cypher Templates
# =============================================================================
from .schema import (
    SpineGraphSchema,
    CypherTemplates,
)

# =============================================================================
# All exports
# =============================================================================
__all__ = [
    # Enums
    "SpineSubDomain",
    "EvidenceLevel",
    "StudyDesign",
    "normalize_study_design",
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
