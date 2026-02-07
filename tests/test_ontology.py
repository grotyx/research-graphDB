"""Tests for SNOMED-CT ontology integration."""

import pytest
from src.ontology.snomed_linker import SNOMEDLinker, LinkedEntity
from src.ontology.concept_hierarchy import ConceptHierarchy, expand_medical_query


class TestSNOMEDLinker:
    """Test SNOMED linker functionality."""

    @pytest.fixture
    def linker(self):
        """Create a SNOMED linker (may fail if scispaCy not installed)."""
        try:
            return SNOMEDLinker()
        except ImportError:
            pytest.skip("scispaCy not installed")

    def test_initialization(self):
        """Test linker initialization."""
        try:
            linker = SNOMEDLinker()
            assert linker.is_available()
        except ImportError:
            pytest.skip("scispaCy not installed")

    def test_extract_entities(self, linker):
        """Test entity extraction from medical text."""
        text = "Patient diagnosed with diabetes mellitus type 2 and hypertension."
        entities = linker.extract_entities(text)

        assert isinstance(entities, list)
        assert len(entities) > 0

        # Check entity structure
        for entity in entities:
            assert isinstance(entity, LinkedEntity)
            assert entity.text
            assert entity.start >= 0
            assert entity.end > entity.start
            assert entity.semantic_type

    def test_process_chunk(self, linker):
        """Test chunk processing with metadata extraction."""
        text = "The patient was treated with metformin for diabetes mellitus."
        result = linker.process_chunk(text)

        assert "entities" in result
        assert "snomed_codes" in result
        assert "semantic_types" in result
        assert "entity_count" in result

        assert isinstance(result["entities"], list)
        assert isinstance(result["snomed_codes"], list)
        assert isinstance(result["semantic_types"], list)
        assert result["entity_count"] >= 0

    def test_empty_text(self, linker):
        """Test processing empty text."""
        result = linker.process_chunk("")
        assert result["entity_count"] == 0
        assert len(result["entities"]) == 0

    def test_no_entities(self, linker):
        """Test text with no medical entities."""
        text = "The weather is nice today."
        result = linker.process_chunk(text)
        # May or may not have entities depending on model
        assert isinstance(result, dict)
        assert "entities" in result


class TestConceptHierarchy:
    """Test concept hierarchy functionality."""

    @pytest.fixture
    def hierarchy(self):
        """Create concept hierarchy."""
        return ConceptHierarchy()

    def test_initialization(self, hierarchy):
        """Test hierarchy initialization."""
        assert hierarchy.all_concepts
        assert hierarchy.reverse_index

    def test_get_related_concepts_disease(self, hierarchy):
        """Test getting related disease concepts."""
        related = hierarchy.get_related_concepts("diabetes")
        assert "diabetes" in related
        assert any("diabetes mellitus" in r.lower() for r in related)

    def test_get_related_concepts_drug(self, hierarchy):
        """Test getting related drug concepts."""
        related = hierarchy.get_related_concepts("statin")
        assert "statin" in related
        assert any("atorvastatin" in r.lower() for r in related)

    def test_get_related_concepts_anatomy(self, hierarchy):
        """Test getting related anatomical concepts."""
        related = hierarchy.get_related_concepts("heart")
        assert "heart" in related
        assert any("cardiac" in r.lower() for r in related)

    def test_get_canonical_term(self, hierarchy):
        """Test canonical term lookup."""
        # Synonym to canonical
        canonical = hierarchy.get_canonical_term("T2DM")
        assert canonical == "diabetes"

        # Canonical returns itself
        canonical = hierarchy.get_canonical_term("diabetes")
        assert canonical == "diabetes"

        # Unknown term returns itself
        canonical = hierarchy.get_canonical_term("unknown_term")
        assert canonical == "unknown_term"

    def test_find_concept_type(self, hierarchy):
        """Test concept type identification."""
        assert hierarchy.find_concept_type("diabetes") == "disease"
        assert hierarchy.find_concept_type("statin") == "drug"
        assert hierarchy.find_concept_type("heart") == "anatomy"
        assert hierarchy.find_concept_type("mri") == "procedure"
        assert hierarchy.find_concept_type("unknown") is None

    def test_expand_query(self, hierarchy):
        """Test query expansion."""
        terms = ["diabetes", "treatment"]
        expanded = hierarchy.expand_query(terms)

        assert "diabetes" in expanded
        assert "treatment" in expanded
        assert len(expanded) >= len(terms)

    def test_expand_query_by_type(self, hierarchy):
        """Test type-filtered query expansion."""
        query = "diabetes treatment"
        expanded = hierarchy.expand_query_by_type(query, include_types={"disease"})

        # Should include diabetes and related terms
        assert any("diabetes" in term.lower() for term in expanded)

    def test_get_all_concepts(self, hierarchy):
        """Test getting all concepts by type."""
        diseases = hierarchy.get_all_diseases()
        drugs = hierarchy.get_all_drugs()
        anatomy = hierarchy.get_all_anatomy()
        procedures = hierarchy.get_all_procedures()

        assert len(diseases) > 0
        assert len(drugs) > 0
        assert len(anatomy) > 0
        assert len(procedures) > 0

        assert "diabetes" in diseases
        assert "statin" in drugs
        assert "heart" in anatomy


def test_expand_medical_query():
    """Test convenience function for query expansion."""
    expanded = expand_medical_query("diabetes treatment")
    assert isinstance(expanded, list)
    assert len(expanded) > 0
    assert any("diabetes" in term.lower() for term in expanded)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
