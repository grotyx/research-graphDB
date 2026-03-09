"""Tests for graph/types/schema.py — SpineGraphSchema and CypherTemplates.

Tests cover:
- NODE_LABELS, RELATIONSHIP_TYPES, INDEXES, UNIQUE_CONSTRAINTS lists
- Cypher generation methods (constraints, indexes, composite, fulltext, vector, etc.)
- CypherTemplates string validity (Cypher keywords, parameter placeholders)
- Taxonomy initialization Cypher
- Orphan fix Cypher queries
"""

import re

import pytest

from graph.types.schema import SpineGraphSchema, CypherTemplates


# ============================================================================
# SpineGraphSchema — Static Data
# ============================================================================

class TestNodeLabels:
    """Test SpineGraphSchema.NODE_LABELS list."""

    def test_node_labels_is_list(self):
        assert isinstance(SpineGraphSchema.NODE_LABELS, list)

    def test_node_labels_not_empty(self):
        assert len(SpineGraphSchema.NODE_LABELS) > 0

    def test_core_nodes_present(self):
        core = {"Paper", "Pathology", "Anatomy", "Intervention", "Outcome", "Chunk"}
        for label in core:
            assert label in SpineGraphSchema.NODE_LABELS, f"Missing core node: {label}"

    def test_extended_nodes_present(self):
        extended = {"Concept", "Technique", "Recommendation", "Implant", "Complication", "Drug"}
        for label in extended:
            assert label in SpineGraphSchema.NODE_LABELS, f"Missing extended node: {label}"

    def test_v12_nodes_present(self):
        v12 = {"PatientCohort", "FollowUp", "Cost", "QualityMetric"}
        for label in v12:
            assert label in SpineGraphSchema.NODE_LABELS, f"Missing v1.2 node: {label}"

    def test_no_duplicate_labels(self):
        assert len(SpineGraphSchema.NODE_LABELS) == len(set(SpineGraphSchema.NODE_LABELS))

    def test_all_labels_are_strings(self):
        for label in SpineGraphSchema.NODE_LABELS:
            assert isinstance(label, str)
            assert len(label) > 0


class TestRelationshipTypes:
    """Test SpineGraphSchema.RELATIONSHIP_TYPES list."""

    def test_relationship_types_is_list(self):
        assert isinstance(SpineGraphSchema.RELATIONSHIP_TYPES, list)

    def test_relationship_types_not_empty(self):
        assert len(SpineGraphSchema.RELATIONSHIP_TYPES) > 0

    def test_core_relationships_present(self):
        core = {"STUDIES", "LOCATED_AT", "INVESTIGATES", "TREATS", "AFFECTS", "IS_A", "HAS_CHUNK"}
        for rel in core:
            assert rel in SpineGraphSchema.RELATIONSHIP_TYPES, f"Missing core rel: {rel}"

    def test_paper_to_paper_relationships(self):
        p2p = {"CITES", "SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "REPLICATES"}
        for rel in p2p:
            assert rel in SpineGraphSchema.RELATIONSHIP_TYPES, f"Missing P2P rel: {rel}"

    def test_v11_relationships(self):
        v11 = {"CAUSES", "HAS_RISK_FACTOR", "PREDICTS", "CORRELATES", "USES_DEVICE"}
        for rel in v11:
            assert rel in SpineGraphSchema.RELATIONSHIP_TYPES, f"Missing v1.1 rel: {rel}"

    def test_v12_relationships(self):
        v12 = {"HAS_COHORT", "TREATED_WITH", "HAS_FOLLOWUP", "REPORTS_OUTCOME", "REPORTS_COST",
               "ASSOCIATED_WITH", "HAS_QUALITY_METRIC"}
        for rel in v12:
            assert rel in SpineGraphSchema.RELATIONSHIP_TYPES, f"Missing v1.2 rel: {rel}"

    def test_no_duplicate_relationship_types(self):
        assert len(SpineGraphSchema.RELATIONSHIP_TYPES) == len(set(SpineGraphSchema.RELATIONSHIP_TYPES))

    def test_all_types_are_uppercase_strings(self):
        for rel in SpineGraphSchema.RELATIONSHIP_TYPES:
            assert isinstance(rel, str)
            assert rel == rel.upper().replace(" ", "_"), f"Relationship type not uppercase: {rel}"


class TestIndexes:
    """Test SpineGraphSchema.INDEXES list."""

    def test_indexes_is_list_of_tuples(self):
        assert isinstance(SpineGraphSchema.INDEXES, list)
        for item in SpineGraphSchema.INDEXES:
            assert isinstance(item, tuple), f"Not a tuple: {item}"
            assert len(item) == 2, f"Expected 2-tuple: {item}"

    def test_indexes_not_empty(self):
        assert len(SpineGraphSchema.INDEXES) > 0

    def test_core_paper_indexes(self):
        paper_indexes = [(l, p) for l, p in SpineGraphSchema.INDEXES if l == "Paper"]
        paper_props = {p for _, p in paper_indexes}
        assert "paper_id" in paper_props
        assert "doi" in paper_props
        assert "year" in paper_props
        assert "sub_domain" in paper_props

    def test_all_index_labels_are_known_node_labels(self):
        known_labels = set(SpineGraphSchema.NODE_LABELS)
        for label, _ in SpineGraphSchema.INDEXES:
            assert label in known_labels, f"Index label '{label}' not in NODE_LABELS"

    def test_all_index_props_are_strings(self):
        for label, prop in SpineGraphSchema.INDEXES:
            assert isinstance(label, str)
            assert isinstance(prop, str)
            assert len(prop) > 0


class TestUniqueConstraints:
    """Test SpineGraphSchema.UNIQUE_CONSTRAINTS list."""

    def test_unique_constraints_is_list_of_tuples(self):
        assert isinstance(SpineGraphSchema.UNIQUE_CONSTRAINTS, list)
        for item in SpineGraphSchema.UNIQUE_CONSTRAINTS:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_paper_id_constraint(self):
        assert ("Paper", "paper_id") in SpineGraphSchema.UNIQUE_CONSTRAINTS

    def test_paper_doi_constraint(self):
        assert ("Paper", "doi") in SpineGraphSchema.UNIQUE_CONSTRAINTS

    def test_core_entity_name_constraints(self):
        for entity in ["Pathology", "Anatomy", "Intervention", "Outcome"]:
            assert (entity, "name") in SpineGraphSchema.UNIQUE_CONSTRAINTS, \
                f"Missing unique constraint for {entity}.name"

    def test_chunk_id_constraint(self):
        assert ("Chunk", "chunk_id") in SpineGraphSchema.UNIQUE_CONSTRAINTS


# ============================================================================
# SpineGraphSchema — Cypher Generation Methods
# ============================================================================

class TestGetCreateConstraintsCypher:
    """Test SpineGraphSchema.get_create_constraints_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_constraints_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0
        for q in queries:
            assert isinstance(q, str)

    def test_query_count_matches_constraints(self):
        queries = SpineGraphSchema.get_create_constraints_cypher()
        assert len(queries) == len(SpineGraphSchema.UNIQUE_CONSTRAINTS)

    def test_queries_contain_create_constraint_keyword(self):
        queries = SpineGraphSchema.get_create_constraints_cypher()
        for q in queries:
            assert "CREATE CONSTRAINT" in q
            assert "IF NOT EXISTS" in q
            assert "IS UNIQUE" in q

    def test_queries_contain_correct_labels(self):
        queries = SpineGraphSchema.get_create_constraints_cypher()
        for query, (label, prop) in zip(queries, SpineGraphSchema.UNIQUE_CONSTRAINTS):
            assert f"(n:{label})" in query
            assert f"n.{prop}" in query


class TestGetCreateIndexesCypher:
    """Test SpineGraphSchema.get_create_indexes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_indexes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_query_count_matches_indexes(self):
        queries = SpineGraphSchema.get_create_indexes_cypher()
        assert len(queries) == len(SpineGraphSchema.INDEXES)

    def test_queries_contain_create_index_keyword(self):
        queries = SpineGraphSchema.get_create_indexes_cypher()
        for q in queries:
            assert "CREATE INDEX" in q
            assert "IF NOT EXISTS" in q

    def test_index_names_follow_pattern(self):
        queries = SpineGraphSchema.get_create_indexes_cypher()
        for query, (label, prop) in zip(queries, SpineGraphSchema.INDEXES):
            expected_name = f"{label.lower()}_{prop}_idx"
            assert expected_name in query


class TestGetCreateCompositeIndexesCypher:
    """Test SpineGraphSchema.get_create_composite_indexes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_composite_indexes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_queries_contain_create_index_keyword(self):
        for q in SpineGraphSchema.get_create_composite_indexes_cypher():
            assert "CREATE INDEX" in q
            assert "IF NOT EXISTS" in q

    def test_composite_index_names_contain_composite(self):
        for q in SpineGraphSchema.get_create_composite_indexes_cypher():
            assert "_composite_" in q


class TestGetCreateFulltextIndexesCypher:
    """Test SpineGraphSchema.get_create_fulltext_indexes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_fulltext_indexes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_queries_contain_fulltext_keyword(self):
        for q in SpineGraphSchema.get_create_fulltext_indexes_cypher():
            assert "FULLTEXT INDEX" in q
            assert "IF NOT EXISTS" in q
            assert "ON EACH" in q

    def test_paper_text_search_index_present(self):
        queries = SpineGraphSchema.get_create_fulltext_indexes_cypher()
        paper_search = [q for q in queries if "paper_text_search" in q]
        assert len(paper_search) == 1
        assert "n.title" in paper_search[0]
        assert "n.abstract" in paper_search[0]


class TestGetCreateRelationshipIndexesCypher:
    """Test SpineGraphSchema.get_create_relationship_indexes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_relationship_indexes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_queries_contain_relationship_pattern(self):
        for q in SpineGraphSchema.get_create_relationship_indexes_cypher():
            assert "CREATE INDEX" in q
            assert "IF NOT EXISTS" in q
            # Relationship index: FOR ()-[r:TYPE]-()
            assert "()-[r:" in q


class TestGetCreateVectorIndexesCypher:
    """Test SpineGraphSchema.get_create_vector_indexes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_create_vector_indexes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_queries_contain_vector_keyword(self):
        for q in SpineGraphSchema.get_create_vector_indexes_cypher():
            assert "VECTOR INDEX" in q
            assert "IF NOT EXISTS" in q

    def test_chunk_embedding_index(self):
        queries = SpineGraphSchema.get_create_vector_indexes_cypher()
        chunk_idx = [q for q in queries if "chunk_embedding_index" in q]
        assert len(chunk_idx) == 1
        assert "3072" in chunk_idx[0]
        assert "cosine" in chunk_idx[0]

    def test_paper_abstract_index(self):
        queries = SpineGraphSchema.get_create_vector_indexes_cypher()
        paper_idx = [q for q in queries if "paper_abstract_index" in q]
        assert len(paper_idx) == 1
        assert "3072" in paper_idx[0]
        assert "cosine" in paper_idx[0]


class TestGetInitTaxonomyCypher:
    """Test SpineGraphSchema.get_init_taxonomy_cypher()."""

    def test_returns_string(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert isinstance(cypher, str)
        assert len(cypher) > 0

    def test_contains_merge_statements(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert "MERGE" in cypher

    def test_contains_isa_relationships(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert "IS_A" in cypher

    def test_contains_fusion_hierarchy(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert "Fusion Surgery" in cypher
        assert "TLIF" in cypher
        assert "ALIF" in cypher

    def test_contains_decompression_hierarchy(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert "Decompression Surgery" in cypher
        assert "UBE" in cypher
        assert "Laminectomy" in cypher

    def test_contains_outcomes(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert ":Outcome" in cypher
        assert "VAS" in cypher
        assert "ODI" in cypher

    def test_contains_anatomy(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert ":Anatomy" in cypher
        assert "Cervical" in cypher
        assert "Lumbar" in cypher

    def test_contains_return_statement(self):
        cypher = SpineGraphSchema.get_init_taxonomy_cypher()
        assert "RETURN" in cypher


class TestGetFixOrphanInterventionsCypher:
    """Test SpineGraphSchema.get_fix_orphan_interventions_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_fix_orphan_interventions_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0
        for q in queries:
            assert isinstance(q, str)

    def test_queries_contain_merge_or_match(self):
        for q in SpineGraphSchema.get_fix_orphan_interventions_cypher():
            assert "MERGE" in q or "MATCH" in q

    def test_queries_each_have_return(self):
        for q in SpineGraphSchema.get_fix_orphan_interventions_cypher():
            assert "RETURN" in q


class TestGetFixOrphanPathologiesCypher:
    """Test SpineGraphSchema.get_fix_orphan_pathologies_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_fix_orphan_pathologies_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_each_query_sets_category(self):
        for q in SpineGraphSchema.get_fix_orphan_pathologies_cypher():
            assert "SET" in q and "category" in q


class TestGetFixOrphanOutcomesCypher:
    """Test SpineGraphSchema.get_fix_orphan_outcomes_cypher()."""

    def test_returns_list_of_strings(self):
        queries = SpineGraphSchema.get_fix_orphan_outcomes_cypher()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_each_query_sets_type(self):
        for q in SpineGraphSchema.get_fix_orphan_outcomes_cypher():
            assert "SET" in q and "type" in q


# ============================================================================
# CypherTemplates — Query Templates
# ============================================================================

class TestCypherTemplatesExistence:
    """Test that all expected CypherTemplates attributes exist."""

    EXPECTED_TEMPLATES = [
        "MERGE_PAPER",
        "CREATE_STUDIES_RELATION",
        "CREATE_INVESTIGATES_RELATION",
        "CREATE_TREATS_RELATION",
        "CREATE_AFFECTS_RELATION",
        "GET_INTERVENTION_HIERARCHY",
        "GET_INTERVENTION_CHILDREN",
        "SEARCH_EFFECTIVE_INTERVENTIONS",
        "SEARCH_INTERVENTIONS_FOR_PATHOLOGY",
        "GET_PAPER_RELATIONS",
        "FIND_CONFLICTING_RESULTS",
        "CREATE_INVOLVES_RELATION",
        # Paper-to-Paper
        "CREATE_PAPER_RELATIONSHIP",
        "CREATE_SUPPORTS_RELATION",
        "CREATE_CONTRADICTS_RELATION",
        "CREATE_SIMILAR_TOPIC_RELATION",
        "CREATE_EXTENDS_RELATION",
        "CREATE_REPLICATES_RELATION",
        # CITES
        "CREATE_CITES_RELATION",
        "CREATE_CITES_WITH_CITED_PAPER",
        "GET_IMPORTANT_CITATIONS",
        "GET_SUPPORTING_CITATIONS",
        "GET_CONTRADICTING_CITATIONS",
        "GET_CITING_PAPERS",
        "GET_CITATION_NETWORK",
        "GET_ALL_PAPER_RELATIONS",
        "GET_SUPPORTING_PAPERS",
        "GET_CONTRADICTING_PAPERS",
        "GET_SIMILAR_PAPERS",
        "GET_EXTENDED_RESEARCH_CHAIN",
        "GET_REPLICATION_STUDIES",
        "GET_PAPER_NETWORK",
        # Query Pattern Templates
        "TREATMENT_COMPARISON",
        "PATIENT_SPECIFIC_OUTCOMES",
        "INDICATION_QUERY",
        "OUTCOME_AGGREGATION",
        "EVIDENCE_LEVEL_FILTER",
        "HEAD_TO_HEAD_COMPARISON",
    ]

    @pytest.mark.parametrize("template_name", EXPECTED_TEMPLATES)
    def test_template_exists(self, template_name):
        assert hasattr(CypherTemplates, template_name), f"Missing template: {template_name}"

    @pytest.mark.parametrize("template_name", EXPECTED_TEMPLATES)
    def test_template_is_nonempty_string(self, template_name):
        value = getattr(CypherTemplates, template_name)
        assert isinstance(value, str)
        assert len(value.strip()) > 0


class TestCypherTemplatesValidity:
    """Test that Cypher templates contain expected Cypher keywords."""

    def _get_all_templates(self):
        """Get all template strings from CypherTemplates."""
        templates = {}
        for name in dir(CypherTemplates):
            if name.startswith("_"):
                continue
            val = getattr(CypherTemplates, name)
            if isinstance(val, str) and len(val.strip()) > 10:
                templates[name] = val
        return templates

    def test_all_templates_contain_cypher_keyword(self):
        """Each template should have at least one Cypher keyword."""
        cypher_keywords = {"MATCH", "MERGE", "RETURN", "CREATE", "SET", "WITH", "CALL", "UNWIND"}
        for name, template in self._get_all_templates().items():
            upper = template.upper()
            has_keyword = any(kw in upper for kw in cypher_keywords)
            assert has_keyword, f"Template {name} has no Cypher keywords"

    def test_no_unresolved_python_format_placeholders(self):
        """Templates should use $param (Cypher) not {param} (Python f-string)."""
        for name, template in self._get_all_templates().items():
            # Allow {} inside CASE/WHEN or map literals, but not bare {variable_name}
            # Look for Python format-style {word} but not Neo4j map patterns
            python_placeholders = re.findall(r'\{[a-z_]+\}', template)
            # Filter out known Neo4j patterns like {paper_id: $paper_id}
            real_placeholders = [p for p in python_placeholders
                                 if ":" not in template[template.index(p)-5:template.index(p)+len(p)+5]]
            # This is a heuristic check, not a guarantee
            assert len(real_placeholders) == 0, \
                f"Template {name} may have Python format placeholders: {real_placeholders}"

    def test_merge_paper_has_correct_params(self):
        assert "$paper_id" in CypherTemplates.MERGE_PAPER
        assert "$properties" in CypherTemplates.MERGE_PAPER

    def test_create_studies_relation_params(self):
        template = CypherTemplates.CREATE_STUDIES_RELATION
        assert "$paper_id" in template
        assert "$pathology_name" in template
        assert "$is_primary" in template

    def test_create_investigates_relation_params(self):
        template = CypherTemplates.CREATE_INVESTIGATES_RELATION
        assert "$paper_id" in template
        assert "$intervention_name" in template
        assert "$is_comparison" in template

    def test_create_treats_relation_params(self):
        template = CypherTemplates.CREATE_TREATS_RELATION
        assert "$intervention_name" in template
        assert "$pathology_name" in template

    def test_create_affects_relation_params(self):
        template = CypherTemplates.CREATE_AFFECTS_RELATION
        assert "$intervention_name" in template
        assert "$outcome_name" in template
        assert "$properties" in template

    def test_treatment_comparison_params(self):
        template = CypherTemplates.TREATMENT_COMPARISON
        assert "$pathology_variants" in template
        assert "$intervention1_variants" in template
        assert "$intervention2_variants" in template

    def test_evidence_level_filter_params(self):
        template = CypherTemplates.EVIDENCE_LEVEL_FILTER
        assert "$intervention_variants" in template
        assert "$limit" in template


class TestCypherTemplatesReturnClauses:
    """Verify RETURN clauses in key templates."""

    def test_merge_paper_returns_paper(self):
        assert "RETURN p" in CypherTemplates.MERGE_PAPER

    def test_create_studies_returns_entities(self):
        assert "RETURN" in CypherTemplates.CREATE_STUDIES_RELATION

    def test_search_templates_return_data(self):
        assert "RETURN" in CypherTemplates.SEARCH_EFFECTIVE_INTERVENTIONS
        assert "intervention" in CypherTemplates.SEARCH_EFFECTIVE_INTERVENTIONS

    def test_get_paper_relations_returns_type(self):
        assert "type(r)" in CypherTemplates.GET_PAPER_RELATIONS
