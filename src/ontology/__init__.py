"""SNOMED-CT Ontology Integration Module.

This module provides medical entity extraction and linking to SNOMED-CT concepts
using scispaCy for NER and optional QuickUMLS for concept linking.

Components:
    - snomed_linker: Medical entity extraction and SNOMED-CT linking
    - concept_hierarchy: Basic medical concept relationships for query expansion
"""

from .snomed_linker import SNOMEDLinker, LinkedEntity
from .concept_hierarchy import ConceptHierarchy

__all__ = ["SNOMEDLinker", "LinkedEntity", "ConceptHierarchy"]
