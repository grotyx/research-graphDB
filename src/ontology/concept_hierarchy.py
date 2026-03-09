"""Basic Medical Concept Hierarchy for Query Expansion.

This module provides simplified medical concept relationships for query expansion.
Note: This is NOT a full SNOMED-CT hierarchy (which requires RF2 files).
It provides basic medical knowledge for common concepts.
"""

from typing import Set, List
import logging

logger = logging.getLogger(__name__)


class ConceptHierarchy:
    """Simple concept hierarchy for query expansion.

    This provides basic medical concept groupings and relationships.
    For production use, consider integrating full SNOMED-CT RF2 files
    or using a medical ontology service.

    Example:
        >>> hierarchy = ConceptHierarchy()
        >>> related = hierarchy.get_related_concepts("diabetes")
        >>> print(related)
        ['diabetes mellitus', 'type 2 diabetes', 'hyperglycemia', ...]
    """

    # Common disease name variations and synonyms
    DISEASE_SYNONYMS = {
        "diabetes": [
            "diabetes mellitus",
            "type 2 diabetes",
            "type 1 diabetes",
            "T2DM",
            "T1DM",
            "hyperglycemia",
            "insulin resistance",
        ],
        "hypertension": [
            "high blood pressure",
            "HTN",
            "elevated blood pressure",
            "arterial hypertension",
        ],
        "stroke": [
            "cerebrovascular accident",
            "CVA",
            "brain attack",
            "cerebral infarction",
            "ischemic stroke",
            "hemorrhagic stroke",
        ],
        "heart attack": [
            "myocardial infarction",
            "MI",
            "acute coronary syndrome",
            "ACS",
            "cardiac arrest",
        ],
        "cancer": [
            "malignancy",
            "neoplasm",
            "carcinoma",
            "tumor",
            "malignant tumor",
        ],
        "pneumonia": [
            "lung infection",
            "pulmonary infection",
            "community-acquired pneumonia",
            "CAP",
        ],
        "copd": [
            "chronic obstructive pulmonary disease",
            "emphysema",
            "chronic bronchitis",
        ],
        "arthritis": [
            "osteoarthritis",
            "rheumatoid arthritis",
            "RA",
            "joint inflammation",
        ],
        "depression": [
            "major depressive disorder",
            "MDD",
            "clinical depression",
            "depressive disorder",
        ],
        "asthma": [
            "reactive airway disease",
            "bronchial asthma",
            "allergic asthma",
        ],
    }

    # Drug class groupings
    DRUG_CLASSES = {
        "statin": [
            "atorvastatin",
            "simvastatin",
            "rosuvastatin",
            "pravastatin",
            "HMG-CoA reductase inhibitor",
        ],
        "ace_inhibitor": [
            "lisinopril",
            "enalapril",
            "ramipril",
            "ACE inhibitor",
            "angiotensin-converting enzyme inhibitor",
        ],
        "beta_blocker": [
            "metoprolol",
            "atenolol",
            "carvedilol",
            "propranolol",
            "beta-adrenergic blocker",
        ],
        "nsaid": [
            "ibuprofen",
            "naproxen",
            "diclofenac",
            "non-steroidal anti-inflammatory",
            "NSAID",
        ],
        "antibiotic": [
            "amoxicillin",
            "azithromycin",
            "ciprofloxacin",
            "penicillin",
            "cephalosporin",
            "fluoroquinolone",
        ],
        "metformin": [
            "glucophage",
            "biguanide",
            "antidiabetic",
        ],
        "insulin": [
            "insulin glargine",
            "insulin lispro",
            "rapid-acting insulin",
            "long-acting insulin",
        ],
    }

    # Basic anatomical relationships
    ANATOMY_HIERARCHY = {
        "heart": [
            "cardiac",
            "myocardium",
            "left ventricle",
            "right ventricle",
            "atrium",
            "coronary artery",
        ],
        "lung": [
            "pulmonary",
            "bronchi",
            "alveoli",
            "respiratory",
        ],
        "brain": [
            "cerebral",
            "cerebrum",
            "cerebellum",
            "cortex",
            "neural",
            "neurological",
        ],
        "kidney": [
            "renal",
            "nephron",
            "glomerulus",
        ],
        "liver": [
            "hepatic",
            "hepatocyte",
        ],
        "spine": [
            "spinal",
            "vertebra",
            "vertebrae",
            "cervical spine",
            "lumbar spine",
            "thoracic spine",
            "intervertebral disc",
        ],
        "knee": [
            "patella",
            "meniscus",
            "ACL",
            "anterior cruciate ligament",
            "tibial",
            "femoral",
        ],
        "hip": [
            "femoral head",
            "acetabulum",
            "hip joint",
        ],
    }

    # Medical procedure synonyms
    PROCEDURE_SYNONYMS = {
        "surgery": [
            "surgical procedure",
            "operation",
            "surgical intervention",
        ],
        "endoscopy": [
            "endoscopic examination",
            "colonoscopy",
            "gastroscopy",
            "bronchoscopy",
        ],
        "biopsy": [
            "tissue sampling",
            "needle biopsy",
            "excisional biopsy",
        ],
        "mri": [
            "magnetic resonance imaging",
            "MRI scan",
            "brain MRI",
            "spinal MRI",
        ],
        "ct_scan": [
            "computed tomography",
            "CT",
            "CAT scan",
        ],
    }

    def __init__(self):
        """Initialize concept hierarchy."""
        # Combine all dictionaries for unified lookup
        self.all_concepts = {
            **self.DISEASE_SYNONYMS,
            **self.DRUG_CLASSES,
            **self.ANATOMY_HIERARCHY,
            **self.PROCEDURE_SYNONYMS,
        }

        # Build reverse index for fast lookup
        self.reverse_index = self._build_reverse_index()

    def _build_reverse_index(self) -> dict[str, str]:
        """Build reverse index from synonyms to canonical terms.

        Returns:
            Dictionary mapping synonyms to canonical terms
        """
        reverse = {}
        for canonical, synonyms in self.all_concepts.items():
            # Canonical term maps to itself
            reverse[canonical.lower()] = canonical

            # Each synonym maps to canonical
            for synonym in synonyms:
                reverse[synonym.lower()] = canonical

        return reverse

    def expand_query(self, terms: List[str]) -> List[str]:
        """Expand query terms using medical concept relationships.

        Args:
            terms: List of query terms to expand

        Returns:
            Expanded list including original terms and related concepts

        Example:
            >>> hierarchy = ConceptHierarchy()
            >>> expanded = hierarchy.expand_query(["diabetes", "treatment"])
            >>> print(expanded)
            ['diabetes', 'diabetes mellitus', 'type 2 diabetes', 'treatment']
        """
        expanded = set(terms)

        for term in terms:
            related = self.get_related_concepts(term)
            expanded.update(related)

        logger.debug(f"Expanded {len(terms)} terms to {len(expanded)} terms")
        return list(expanded)

    def get_related_concepts(self, concept: str) -> List[str]:
        """Get related concepts for a given term.

        Args:
            concept: Medical concept or term

        Returns:
            List of related concepts including synonyms and variants

        Example:
            >>> hierarchy = ConceptHierarchy()
            >>> related = hierarchy.get_related_concepts("diabetes")
            >>> print(related)
            ['diabetes', 'diabetes mellitus', 'type 2 diabetes', ...]
        """
        concept_lower = concept.lower()

        # Check if it's a canonical term
        if concept_lower in self.all_concepts:
            return [concept] + self.all_concepts[concept_lower]

        # Check if it's a synonym (using reverse index)
        if concept_lower in self.reverse_index:
            canonical = self.reverse_index[concept_lower]
            return [concept] + self.all_concepts[canonical]

        # No related concepts found
        return [concept]

    def get_canonical_term(self, term: str) -> str:
        """Get canonical term for a concept or synonym.

        Args:
            term: Medical term

        Returns:
            Canonical term if found, otherwise original term

        Example:
            >>> hierarchy = ConceptHierarchy()
            >>> canonical = hierarchy.get_canonical_term("T2DM")
            >>> print(canonical)
            'diabetes'
        """
        term_lower = term.lower()

        if term_lower in self.reverse_index:
            return self.reverse_index[term_lower]

        return term

    def find_concept_type(self, term: str) -> str | None:
        """Identify the type of medical concept.

        Args:
            term: Medical term

        Returns:
            Concept type: 'disease', 'drug', 'anatomy', 'procedure', or None

        Example:
            >>> hierarchy = ConceptHierarchy()
            >>> concept_type = hierarchy.find_concept_type("diabetes")
            >>> print(concept_type)
            'disease'
        """
        canonical = self.get_canonical_term(term)

        if canonical in self.DISEASE_SYNONYMS:
            return "disease"
        elif canonical in self.DRUG_CLASSES:
            return "drug"
        elif canonical in self.ANATOMY_HIERARCHY:
            return "anatomy"
        elif canonical in self.PROCEDURE_SYNONYMS:
            return "procedure"

        return None

    def expand_query_by_type(
        self, query: str, include_types: Set[str] | None = None
    ) -> List[str]:
        """Expand query terms filtering by concept type.

        Args:
            query: Query string
            include_types: Set of types to include ('disease', 'drug', 'anatomy', 'procedure')

        Returns:
            Expanded query terms filtered by type

        Example:
            >>> hierarchy = ConceptHierarchy()
            >>> expanded = hierarchy.expand_query_by_type(
            ...     "diabetes treatment",
            ...     include_types={'disease', 'drug'}
            ... )
        """
        if include_types is None:
            include_types = {"disease", "drug", "anatomy", "procedure"}

        # Tokenize query (simple split)
        terms = query.lower().split()

        expanded = []
        for term in terms:
            related = self.get_related_concepts(term)
            concept_type = self.find_concept_type(term)

            # Include if type matches or type is unknown
            if concept_type is None or concept_type in include_types:
                expanded.extend(related)
            else:
                # Keep original term even if type doesn't match
                expanded.append(term)

        return list(set(expanded))

    def get_all_diseases(self) -> List[str]:
        """Get all disease concepts.

        Returns:
            List of all disease terms
        """
        return list(self.DISEASE_SYNONYMS.keys())

    def get_all_drugs(self) -> List[str]:
        """Get all drug class concepts.

        Returns:
            List of all drug terms
        """
        return list(self.DRUG_CLASSES.keys())

    def get_all_anatomy(self) -> List[str]:
        """Get all anatomical concepts.

        Returns:
            List of all anatomy terms
        """
        return list(self.ANATOMY_HIERARCHY.keys())

    def get_all_procedures(self) -> List[str]:
        """Get all procedure concepts.

        Returns:
            List of all procedure terms
        """
        return list(self.PROCEDURE_SYNONYMS.keys())


# Convenience function
def expand_medical_query(query: str) -> List[str]:
    """Quick utility to expand a medical query.

    Args:
        query: Query string

    Returns:
        Expanded list of terms

    Example:
        >>> expanded = expand_medical_query("diabetes treatment")
        >>> print(expanded)
        ['diabetes', 'diabetes mellitus', 'type 2 diabetes', 'treatment']
    """
    hierarchy = ConceptHierarchy()
    terms = query.split()
    return hierarchy.expand_query(terms)
