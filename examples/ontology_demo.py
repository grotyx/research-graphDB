"""Demo script for SNOMED-CT ontology integration.

This script demonstrates how to use the SNOMEDLinker and ConceptHierarchy
for medical entity extraction and query expansion.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ontology.snomed_linker import SNOMEDLinker
from src.ontology.concept_hierarchy import ConceptHierarchy


def demo_entity_extraction():
    """Demonstrate medical entity extraction."""
    print("=" * 70)
    print("DEMO 1: Medical Entity Extraction")
    print("=" * 70)

    try:
        linker = SNOMEDLinker()
        print(f"✓ Loaded scispaCy model: {linker.model_name}")

        # Sample medical text
        text = """
        The patient, a 65-year-old male with a history of type 2 diabetes mellitus
        and hypertension, presented with chest pain. Laboratory findings revealed
        elevated troponin levels. The patient was diagnosed with acute myocardial
        infarction and was treated with aspirin, clopidogrel, and atorvastatin.
        """

        print(f"\nInput text:\n{text.strip()}\n")

        # Process the text
        result = linker.process_chunk(text)

        print(f"Found {result['entity_count']} medical entities:")
        print("-" * 70)

        for i, entity in enumerate(result["entities"], 1):
            print(f"{i}. '{entity.text}'")
            print(f"   Type: {entity.semantic_type}")
            print(f"   Position: [{entity.start}:{entity.end}]")
            if entity.snomed_code:
                print(f"   SNOMED Code: {entity.snomed_code}")
                print(f"   SNOMED Label: {entity.snomed_label}")
            print()

        print(f"Unique semantic types: {', '.join(result['semantic_types'])}")

    except ImportError as e:
        print(f"✗ Error: {e}")
        print("\nTo use entity extraction, install scispaCy:")
        print("  pip install scispacy")
        print("  pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz")


def demo_concept_hierarchy():
    """Demonstrate concept hierarchy and query expansion."""
    print("\n" + "=" * 70)
    print("DEMO 2: Concept Hierarchy and Query Expansion")
    print("=" * 70)

    hierarchy = ConceptHierarchy()

    # Test cases
    test_queries = [
        "diabetes",
        "heart attack",
        "statin",
        "lung",
    ]

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        print("-" * 70)

        # Get related concepts
        related = hierarchy.get_related_concepts(query)
        print(f"Related concepts ({len(related)}):")
        for concept in related[:5]:  # Show first 5
            print(f"  • {concept}")
        if len(related) > 5:
            print(f"  ... and {len(related) - 5} more")

        # Get concept type
        concept_type = hierarchy.find_concept_type(query)
        if concept_type:
            print(f"\nConcept type: {concept_type}")

        # Get canonical term
        canonical = hierarchy.get_canonical_term(query)
        if canonical != query.lower():
            print(f"Canonical term: {canonical}")


def demo_query_expansion():
    """Demonstrate query expansion for search."""
    print("\n" + "=" * 70)
    print("DEMO 3: Query Expansion for Search")
    print("=" * 70)

    hierarchy = ConceptHierarchy()

    queries = [
        "diabetes treatment",
        "heart attack prevention",
        "lung cancer symptoms",
    ]

    for query in queries:
        print(f"\nOriginal query: '{query}'")
        print("-" * 70)

        # Expand query
        expanded = hierarchy.expand_query(query.split())

        print(f"Expanded to {len(expanded)} terms:")
        for term in expanded[:10]:  # Show first 10
            print(f"  • {term}")
        if len(expanded) > 10:
            print(f"  ... and {len(expanded) - 10} more")


def demo_integration_example():
    """Demonstrate how to integrate with RAG pipeline."""
    print("\n" + "=" * 70)
    print("DEMO 4: Integration with RAG Pipeline")
    print("=" * 70)

    print("\nExample: Processing a medical paper chunk")
    print("-" * 70)

    chunk_text = """
    In this randomized controlled trial, we investigated the efficacy
    of metformin versus placebo in patients with prediabetes. After
    12 months, the metformin group showed a 31% reduction in progression
    to type 2 diabetes mellitus (p < 0.001).
    """

    print(f"Chunk text:\n{chunk_text.strip()}\n")

    # Step 1: Extract entities
    try:
        linker = SNOMEDLinker()
        result = linker.process_chunk(chunk_text)

        print(f"Step 1: Entity Extraction")
        print(f"  Entities found: {result['entity_count']}")
        print(f"  Semantic types: {', '.join(result['semantic_types'])}")

        # Step 2: Expand query terms for better search
        hierarchy = ConceptHierarchy()

        print(f"\nStep 2: Query Expansion")
        query_terms = ["diabetes", "metformin"]
        expanded = hierarchy.expand_query(query_terms)

        print(f"  Original terms: {', '.join(query_terms)}")
        print(f"  Expanded to {len(expanded)} terms")
        print(f"  Sample: {', '.join(expanded[:5])}")

        # Step 3: Metadata for vector DB
        print(f"\nStep 3: Metadata for Vector DB")
        metadata = {
            "semantic_types": result["semantic_types"],
            "snomed_codes": result.get("snomed_codes", []),
            "entity_count": result["entity_count"],
            "expanded_terms": expanded[:10],  # Store top expanded terms
        }
        print(f"  Metadata: {metadata}")

    except ImportError:
        print("  [Skipped - scispaCy not installed]")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("SNOMED-CT Ontology Integration Demo")
    print("=" * 70)

    demo_entity_extraction()
    demo_concept_hierarchy()
    demo_query_expansion()
    demo_integration_example()

    print("\n" + "=" * 70)
    print("Demo Complete")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Install scispaCy for entity extraction")
    print("  2. Optionally install QuickUMLS for SNOMED linking")
    print("  3. Integrate with your RAG pipeline")
    print()


if __name__ == "__main__":
    main()
