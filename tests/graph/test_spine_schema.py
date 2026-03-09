"""Tests for spine_schema module.

Tests for:
- Node dataclasses (PaperNode, PathologyNode, etc.)
- to_neo4j_properties() method
- from_neo4j_record() method
- CypherTemplates query syntax
- SpineGraphSchema constraint/index generation
"""

import pytest
from datetime import datetime

from src.graph.spine_schema import (
    # Enums
    SpineSubDomain,
    EvidenceLevel,
    StudyDesign,
    OutcomeType,
    InterventionCategory,
    # Nodes
    PaperNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
    # Relations
    StudiesRelation,
    LocatedAtRelation,
    InvestigatesRelation,
    TreatsRelation,
    AffectsRelation,
    IsARelation,
    PaperRelation,
    # Schema
    SpineGraphSchema,
    CypherTemplates,
)


class TestEnums:
    """Test enum definitions."""

    def test_spine_subdomain_values(self):
        assert SpineSubDomain.DEGENERATIVE.value == "Degenerative"
        assert SpineSubDomain.DEFORMITY.value == "Deformity"
        assert SpineSubDomain.TRAUMA.value == "Trauma"
        assert SpineSubDomain.TUMOR.value == "Tumor"
        assert SpineSubDomain.BASIC_SCIENCE.value == "Basic Science"

    def test_evidence_level_values(self):
        assert EvidenceLevel.LEVEL_1A.value == "1a"
        assert EvidenceLevel.LEVEL_1B.value == "1b"
        assert EvidenceLevel.LEVEL_5.value == "5"

    def test_study_design_values(self):
        assert StudyDesign.RCT.value == "RCT"
        assert StudyDesign.META_ANALYSIS.value == "meta-analysis"
        assert StudyDesign.CASE_SERIES.value == "case-series"

    def test_outcome_type_values(self):
        assert OutcomeType.CLINICAL.value == "clinical"
        assert OutcomeType.RADIOLOGICAL.value == "radiological"

    def test_intervention_category_values(self):
        assert InterventionCategory.FUSION.value == "fusion"
        assert InterventionCategory.DECOMPRESSION.value == "decompression"


class TestPaperNode:
    """Test PaperNode dataclass."""

    def test_paper_node_creation(self):
        """Test creating PaperNode with minimal fields."""
        paper = PaperNode(
            paper_id="test_001",
            title="Test Paper"
        )

        assert paper.paper_id == "test_001"
        assert paper.title == "Test Paper"
        assert paper.authors == []
        assert paper.year == 0
        assert paper.journal == ""
        assert paper.evidence_level == "5"

    def test_paper_node_full_creation(self):
        """Test creating PaperNode with all fields."""
        paper = PaperNode(
            paper_id="test_002",
            title="TLIF vs PLIF",
            authors=["Author A", "Author B"],
            year=2024,
            journal="Spine",
            doi="10.1234/test",
            pmid="12345678",
            sub_domain="Degenerative",
            study_design="RCT",
            evidence_level="1b",
            sample_size=100,
            follow_up_months=24,
            abstract="This is an abstract"
        )

        assert paper.paper_id == "test_002"
        assert len(paper.authors) == 2
        assert paper.year == 2024
        assert paper.sample_size == 100

    def test_paper_to_neo4j_properties(self):
        """Test converting PaperNode to Neo4j properties."""
        paper = PaperNode(
            paper_id="test_003",
            title="Test",
            authors=["A", "B"],
            year=2024,
            evidence_level="2b"
        )

        props = paper.to_neo4j_properties()

        assert props["paper_id"] == "test_003"
        assert props["title"] == "Test"
        assert props["authors"] == ["A", "B"]
        assert props["year"] == 2024
        assert props["evidence_level"] == "2b"
        assert "created_at" in props
        assert isinstance(props["created_at"], datetime)

    def test_paper_to_neo4j_long_abstract(self):
        """Test abstract truncation to 1000 chars."""
        long_abstract = "A" * 2000
        paper = PaperNode(
            paper_id="test_004",
            title="Test",
            abstract=long_abstract
        )

        props = paper.to_neo4j_properties()
        assert len(props["abstract"]) == 2000  # Updated: v6.0 allows 2000 chars

    def test_paper_from_neo4j_record(self):
        """Test creating PaperNode from Neo4j record."""
        record = {
            "paper_id": "test_005",
            "title": "Test Paper",
            "authors": ["A", "B"],
            "year": 2024,
            "journal": "Spine",
            "doi": "10.1234/test",
            "pmid": "",
            "sub_domain": "Degenerative",
            "study_design": "RCT",
            "evidence_level": "1b",
            "sample_size": 50,
            "follow_up_months": 12,
            "abstract": "Test abstract",
            "created_at": datetime.now()
        }

        paper = PaperNode.from_neo4j_record(record)

        assert paper.paper_id == "test_005"
        assert paper.title == "Test Paper"
        assert paper.year == 2024
        assert paper.evidence_level == "1b"


class TestPathologyNode:
    """Test PathologyNode dataclass."""

    def test_pathology_node_creation(self):
        """Test creating PathologyNode."""
        path = PathologyNode(
            name="Lumbar Stenosis",
            category="degenerative",
            icd10_code="M48.06",
            description="Lumbar Spinal Stenosis",
            aliases=["LSS", "Spinal Stenosis"]
        )

        assert path.name == "Lumbar Stenosis"
        assert path.category == "degenerative"
        assert len(path.aliases) == 2

    def test_pathology_to_neo4j_properties(self):
        """Test converting to Neo4j properties."""
        path = PathologyNode(
            name="AIS",
            category="deformity",
            description="Adolescent Idiopathic Scoliosis"
        )

        props = path.to_neo4j_properties()

        assert props["name"] == "AIS"
        assert props["category"] == "deformity"
        assert props["description"] == "Adolescent Idiopathic Scoliosis"

    def test_pathology_from_neo4j_record(self):
        """Test creating from Neo4j record."""
        record = {
            "name": "Spondylolisthesis",
            "category": "degenerative",
            "icd10_code": "M43.1",
            "description": "Test",
            "aliases": ["Slip"]
        }

        path = PathologyNode.from_neo4j_record(record)

        assert path.name == "Spondylolisthesis"
        assert path.aliases == ["Slip"]


class TestAnatomyNode:
    """Test AnatomyNode dataclass."""

    def test_anatomy_node_creation(self):
        """Test creating AnatomyNode."""
        anat = AnatomyNode(
            name="L4-5",
            region="lumbar",
            level_count=1
        )

        assert anat.name == "L4-5"
        assert anat.region == "lumbar"
        assert anat.level_count == 1

    def test_anatomy_to_neo4j_properties(self):
        """Test converting to Neo4j properties."""
        anat = AnatomyNode(
            name="C5-6",
            region="cervical",
            level_count=1
        )

        props = anat.to_neo4j_properties()

        assert props["name"] == "C5-6"
        assert props["region"] == "cervical"

    def test_anatomy_from_neo4j_record(self):
        """Test creating from Neo4j record."""
        record = {
            "name": "T10-L2",
            "region": "thoracolumbar",
            "level_count": 3
        }

        anat = AnatomyNode.from_neo4j_record(record)

        assert anat.name == "T10-L2"
        assert anat.level_count == 3


class TestInterventionNode:
    """Test InterventionNode dataclass."""

    def test_intervention_node_creation(self):
        """Test creating InterventionNode."""
        interv = InterventionNode(
            name="TLIF",
            full_name="Transforaminal Lumbar Interbody Fusion",
            category="fusion",
            approach="posterior",
            is_minimally_invasive=False,
            aliases=["TLIF surgery"]
        )

        assert interv.name == "TLIF"
        assert interv.category == "fusion"
        assert interv.approach == "posterior"
        assert not interv.is_minimally_invasive

    def test_intervention_to_neo4j_properties(self):
        """Test converting to Neo4j properties."""
        interv = InterventionNode(
            name="UBE",
            full_name="Unilateral Biportal Endoscopic",
            category="decompression",
            is_minimally_invasive=True,
            aliases=["BESS", "Biportal"]
        )

        props = interv.to_neo4j_properties()

        assert props["name"] == "UBE"
        assert props["is_minimally_invasive"] is True
        assert "BESS" in props["aliases"]

    def test_intervention_from_neo4j_record(self):
        """Test creating from Neo4j record."""
        record = {
            "name": "OLIF",
            "full_name": "Oblique Lumbar Interbody Fusion",
            "category": "fusion",
            "approach": "lateral",
            "is_minimally_invasive": False,
            "aliases": ["OLIF51"]
        }

        interv = InterventionNode.from_neo4j_record(record)

        assert interv.name == "OLIF"
        assert interv.approach == "lateral"


class TestOutcomeNode:
    """Test OutcomeNode dataclass."""

    def test_outcome_node_creation(self):
        """Test creating OutcomeNode."""
        outcome = OutcomeNode(
            name="VAS",
            type="clinical",
            unit="points",
            direction="lower_is_better",
            description="Visual Analog Scale (0-10)"
        )

        assert outcome.name == "VAS"
        assert outcome.type == "clinical"
        assert outcome.direction == "lower_is_better"

    def test_outcome_to_neo4j_properties(self):
        """Test converting to Neo4j properties."""
        outcome = OutcomeNode(
            name="Fusion Rate",
            type="radiological",
            unit="%",
            direction="higher_is_better"
        )

        props = outcome.to_neo4j_properties()

        assert props["name"] == "Fusion Rate"
        assert props["type"] == "radiological"
        assert props["unit"] == "%"

    def test_outcome_from_neo4j_record(self):
        """Test creating from Neo4j record."""
        record = {
            "name": "ODI",
            "type": "clinical",
            "unit": "%",
            "direction": "lower_is_better",
            "description": "Oswestry Disability Index"
        }

        outcome = OutcomeNode.from_neo4j_record(record)

        assert outcome.name == "ODI"
        assert outcome.unit == "%"


class TestRelationships:
    """Test relationship dataclasses."""

    def test_studies_relation(self):
        """Test StudiesRelation."""
        rel = StudiesRelation(
            source_paper_id="paper_001",
            target_pathology="Lumbar Stenosis",
            is_primary=True
        )

        assert rel.source_paper_id == "paper_001"
        assert rel.is_primary is True

    def test_investigates_relation(self):
        """Test InvestigatesRelation."""
        rel = InvestigatesRelation(
            paper_id="paper_002",
            intervention_name="TLIF",
            is_comparison=True
        )

        assert rel.intervention_name == "TLIF"
        assert rel.is_comparison is True

    def test_affects_relation(self):
        """Test AffectsRelation."""
        rel = AffectsRelation(
            intervention_name="UBE",
            outcome_name="VAS",
            source_paper_id="paper_003",
            value="2.3",
            p_value=0.001,
            is_significant=True,
            direction="improved"
        )

        assert rel.intervention_name == "UBE"
        assert rel.p_value == 0.001
        assert rel.direction == "improved"

    def test_affects_to_neo4j_properties(self):
        """Test AffectsRelation conversion to properties."""
        rel = AffectsRelation(
            intervention_name="TLIF",
            outcome_name="Fusion Rate",
            source_paper_id="paper_004",
            value="92%",
            value_control="85%",
            p_value=0.01,
            confidence_interval="95% CI: 0.02-0.15",
            is_significant=True,
            direction="improved"
        )

        props = rel.to_neo4j_properties()

        assert props["source_paper_id"] == "paper_004"
        assert props["value"] == "92%"
        assert props["p_value"] == 0.01
        assert props["is_significant"] is True

    def test_is_a_relation(self):
        """Test IsARelation."""
        rel = IsARelation(
            child_name="TLIF",
            parent_name="Interbody Fusion",
            level=2
        )

        assert rel.child_name == "TLIF"
        assert rel.level == 2

    def test_paper_relation(self):
        """Test PaperRelation."""
        rel = PaperRelation(
            source_paper_id="paper_005",
            target_paper_id="paper_006",
            relation_type="contradicts",
            confidence=0.85,
            conflict_point="Different fusion rates reported"
        )

        assert rel.relation_type == "contradicts"
        assert rel.confidence == 0.85
        assert "fusion rates" in rel.conflict_point


class TestCypherTemplates:
    """Test CypherTemplates query strings."""

    def test_merge_paper_query(self):
        """Test MERGE_PAPER query is valid Cypher."""
        query = CypherTemplates.MERGE_PAPER

        assert "MERGE" in query
        assert "(p:Paper" in query
        assert "$paper_id" in query
        assert "$properties" in query

    def test_create_studies_relation_query(self):
        """Test CREATE_STUDIES_RELATION query."""
        query = CypherTemplates.CREATE_STUDIES_RELATION

        assert "MATCH (p:Paper" in query
        assert "MERGE (path:Pathology" in query
        assert "MERGE (p)-[r:STUDIES]->(path)" in query
        assert "$pathology_name" in query

    def test_create_investigates_relation_query(self):
        """Test CREATE_INVESTIGATES_RELATION query."""
        query = CypherTemplates.CREATE_INVESTIGATES_RELATION

        assert "MATCH (p:Paper" in query
        assert "MERGE (i:Intervention" in query
        assert "INVESTIGATES" in query

    def test_create_affects_relation_query(self):
        """Test CREATE_AFFECTS_RELATION query."""
        query = CypherTemplates.CREATE_AFFECTS_RELATION

        assert "MATCH (i:Intervention" in query
        assert "MERGE (o:Outcome" in query
        assert "AFFECTS" in query
        assert "$properties" in query

    def test_get_intervention_hierarchy_query(self):
        """Test GET_INTERVENTION_HIERARCHY query."""
        query = CypherTemplates.GET_INTERVENTION_HIERARCHY

        assert "MATCH (i:Intervention" in query
        assert "IS_A*1..5" in query  # Variable length path
        assert "parent:Intervention" in query

    def test_search_effective_interventions_query(self):
        """Test SEARCH_EFFECTIVE_INTERVENTIONS query."""
        query = CypherTemplates.SEARCH_EFFECTIVE_INTERVENTIONS

        assert "MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome" in query
        assert "a.is_significant = true" in query
        assert "a.direction = 'improved'" in query
        assert "ORDER BY a.p_value" in query

    def test_find_conflicting_results_query(self):
        """Test FIND_CONFLICTING_RESULTS query."""
        query = CypherTemplates.FIND_CONFLICTING_RESULTS

        assert "MATCH (i:Intervention)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2:Intervention)" in query
        assert "a1.direction <> a2.direction" in query


class TestSpineGraphSchema:
    """Test SpineGraphSchema schema management."""

    def test_node_labels(self):
        """Test NODE_LABELS definition."""
        labels = SpineGraphSchema.NODE_LABELS

        assert "Paper" in labels
        assert "Pathology" in labels
        assert "Anatomy" in labels
        assert "Intervention" in labels
        assert "Outcome" in labels
        assert len(labels) >= 5  # Updated: v7.x has 21+ node types

    def test_relationship_types(self):
        """Test RELATIONSHIP_TYPES definition."""
        rel_types = SpineGraphSchema.RELATIONSHIP_TYPES

        assert "STUDIES" in rel_types
        assert "INVESTIGATES" in rel_types
        assert "AFFECTS" in rel_types
        assert "IS_A" in rel_types
        assert "CITES" in rel_types
        assert "SUPPORTS" in rel_types
        assert "CONTRADICTS" in rel_types

    def test_indexes_definition(self):
        """Test INDEXES definition."""
        indexes = SpineGraphSchema.INDEXES

        # Check Paper indexes
        assert ("Paper", "paper_id") in indexes
        assert ("Paper", "doi") in indexes
        assert ("Paper", "year") in indexes
        assert ("Paper", "evidence_level") in indexes

        # Check other node indexes
        assert ("Intervention", "name") in indexes
        assert ("Outcome", "type") in indexes

    def test_unique_constraints_definition(self):
        """Test UNIQUE_CONSTRAINTS definition."""
        constraints = SpineGraphSchema.UNIQUE_CONSTRAINTS

        assert ("Paper", "paper_id") in constraints
        assert ("Paper", "doi") in constraints
        assert ("Pathology", "name") in constraints
        assert ("Intervention", "name") in constraints
        assert ("Outcome", "name") in constraints

    def test_get_create_constraints_cypher(self):
        """Test constraint creation queries."""
        queries = SpineGraphSchema.get_create_constraints_cypher()

        assert len(queries) > 0
        for query in queries:
            assert "CREATE CONSTRAINT" in query
            assert "IF NOT EXISTS" in query
            assert "REQUIRE" in query
            assert "IS UNIQUE" in query

    def test_get_create_indexes_cypher(self):
        """Test index creation queries."""
        queries = SpineGraphSchema.get_create_indexes_cypher()

        assert len(queries) > 0
        for query in queries:
            assert "CREATE INDEX" in query
            assert "IF NOT EXISTS" in query
            assert "ON (n." in query

    def test_get_init_taxonomy_cypher(self):
        """Test taxonomy initialization query."""
        query = SpineGraphSchema.get_init_taxonomy_cypher()

        # Check for key interventions
        assert "Fusion Surgery" in query
        assert "TLIF" in query
        assert "PLIF" in query
        assert "UBE" in query
        assert "Endoscopic Surgery" in query

        # Check for IS_A relationships
        assert "[:IS_A" in query

        # Check for common outcomes
        assert "VAS" in query
        assert "ODI" in query
        assert "Fusion Rate" in query

        # Check for common pathologies
        assert "Lumbar Stenosis" in query
        assert "AIS" in query
        assert "Spondylolisthesis" in query

        # Check MERGE syntax
        assert "MERGE (" in query
        assert query.count("MERGE") > 20  # Many MERGE statements
