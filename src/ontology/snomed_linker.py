"""SNOMED-CT Entity Linker using scispaCy NER.

This module extracts medical entities from text using scispaCy and optionally
links them to SNOMED-CT concepts using QuickUMLS.
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class LinkedEntity:
    """Medical entity linked to SNOMED-CT.

    Attributes:
        text: Original text span
        start: Character start position
        end: Character end position
        snomed_code: SNOMED-CT concept ID (e.g., "128045006")
        snomed_label: Preferred term from SNOMED-CT
        confidence: Linking confidence score (0.0-1.0)
        semantic_type: Entity type (disease, drug, procedure, anatomy, etc.)
    """

    text: str
    start: int
    end: int
    snomed_code: Optional[str] = None
    snomed_label: Optional[str] = None
    confidence: float = 0.0
    semantic_type: str = "unknown"


class SNOMEDLinker:
    """Extract medical entities and link to SNOMED-CT concepts.

    Uses scispaCy for medical NER and optionally QuickUMLS for SNOMED linking.

    Example:
        >>> linker = SNOMEDLinker()
        >>> text = "Patient diagnosed with diabetes mellitus type 2."
        >>> result = linker.process_chunk(text)
        >>> print(result["entities"])
        [LinkedEntity(text="diabetes mellitus type 2", ...)]
    """

    def __init__(
        self,
        use_quickumls: bool = False,
        quickumls_path: Optional[str] = None,
        scispacy_model: str = "en_core_sci_lg",
    ):
        """Initialize SNOMED linker.

        Args:
            use_quickumls: Enable QuickUMLS for SNOMED linking
            quickumls_path: Path to QuickUMLS installation
            scispacy_model: scispaCy model name (default: en_core_sci_lg)

        Raises:
            ImportError: If scispaCy not installed
        """
        self.use_quickumls = use_quickumls
        self.quickumls_path = quickumls_path
        self.model_name = scispacy_model

        # Try to load scispaCy
        self.nlp = self._load_scispacy()

        # Try to load QuickUMLS if requested
        self.matcher = None
        if use_quickumls:
            self.matcher = self._load_quickumls()

    def _load_scispacy(self):
        """Load scispaCy model for medical NER.

        Returns:
            Loaded spaCy Language model

        Raises:
            ImportError: If scispaCy not available
        """
        try:
            import spacy

            try:
                nlp = spacy.load(self.model_name)
                logger.info(f"Loaded scispaCy model: {self.model_name}")
                return nlp
            except OSError:
                logger.warning(
                    f"Model {self.model_name} not found. "
                    f"Install with: pip install {self.model_name}"
                )
                raise ImportError(
                    f"scispaCy model not found. Install with:\n"
                    f"  pip install {self.model_name}"
                )

        except ImportError as e:
            logger.error("scispaCy not installed")
            raise ImportError(
                "scispaCy required for medical NER. Install with:\n"
                "  pip install scispacy\n"
                f"  pip install {self.model_name}"
            ) from e

    def _load_quickumls(self):
        """Load QuickUMLS matcher for SNOMED linking.

        Returns:
            QuickUMLS matcher or None if not available

        Note:
            QuickUMLS requires separate installation and UMLS database setup.
        """
        if not self.quickumls_path:
            logger.warning("QuickUMLS requested but no path provided")
            return None

        try:
            from quickumls import QuickUMLS

            matcher = QuickUMLS(self.quickumls_path)
            logger.info("Loaded QuickUMLS matcher")
            return matcher
        except ImportError:
            logger.warning(
                "QuickUMLS not installed. Entity linking disabled. "
                "Install with: pip install quickumls"
            )
            return None
        except Exception as e:
            logger.warning(f"Failed to load QuickUMLS: {e}")
            return None

    def extract_entities(self, text: str) -> list[LinkedEntity]:
        """Extract medical entities from text using scispaCy.

        Args:
            text: Input text to process

        Returns:
            List of extracted entities with positions and types

        Note:
            This only extracts entities. Use link_to_snomed() for SNOMED codes.
        """
        if not self.nlp:
            logger.warning("scispaCy not available, returning empty list")
            return []

        doc = self.nlp(text)
        entities = []

        for ent in doc.ents:
            # Map scispaCy entity labels to semantic types
            semantic_type = self._map_entity_type(ent.label_)

            entity = LinkedEntity(
                text=ent.text,
                start=ent.start_char,
                end=ent.end_char,
                semantic_type=semantic_type,
                confidence=1.0,  # scispaCy doesn't provide confidence scores
            )
            entities.append(entity)

        logger.debug(f"Extracted {len(entities)} entities from text")
        return entities

    def _map_entity_type(self, label: str) -> str:
        """Map scispaCy entity labels to semantic types.

        Args:
            label: scispaCy entity label

        Returns:
            Semantic type string
        """
        # Common scispaCy labels mapping
        mapping = {
            "DISEASE": "disease",
            "CHEMICAL": "drug",
            "GENE": "gene",
            "PROTEIN": "protein",
            "SPECIES": "organism",
            "CELL_LINE": "cell_line",
            "CELL_TYPE": "cell_type",
            "DNA": "dna",
            "RNA": "rna",
            # BC5CDR model labels
            "DISEASE": "disease",
            "CHEMICAL": "drug",
            # Generic fallback
        }
        return mapping.get(label.upper(), label.lower())

    def link_to_snomed(self, entities: list[LinkedEntity]) -> list[LinkedEntity]:
        """Link extracted entities to SNOMED-CT codes using QuickUMLS.

        Args:
            entities: List of entities to link

        Returns:
            Same list with snomed_code and snomed_label populated

        Note:
            Requires QuickUMLS to be initialized. If not available,
            returns entities unchanged.
        """
        if not self.matcher:
            logger.debug("QuickUMLS not available, skipping SNOMED linking")
            return entities

        for entity in entities:
            matches = self.matcher.match(entity.text, best_match=True)

            if matches and len(matches) > 0:
                # Get best match
                best_match = matches[0]
                if len(best_match) > 0:
                    match_info = best_match[0]

                    # Extract SNOMED code if available
                    cui = match_info.get("cui")
                    if cui:
                        entity.snomed_code = cui
                        entity.snomed_label = match_info.get("term", entity.text)
                        entity.confidence = match_info.get("similarity", 0.0)

                        # Update semantic type from UMLS if available
                        semtypes = match_info.get("semtypes", [])
                        if semtypes:
                            entity.semantic_type = self._map_semtype(semtypes[0])

        return entities

    def _map_semtype(self, semtype: str) -> str:
        """Map UMLS semantic type to simplified category.

        Args:
            semtype: UMLS semantic type code

        Returns:
            Simplified semantic type
        """
        # Common UMLS semantic type mappings
        mapping = {
            "T047": "disease",  # Disease or Syndrome
            "T048": "disease",  # Mental or Behavioral Dysfunction
            "T121": "drug",  # Pharmacologic Substance
            "T200": "drug",  # Clinical Drug
            "T061": "procedure",  # Therapeutic or Preventive Procedure
            "T060": "procedure",  # Diagnostic Procedure
            "T029": "anatomy",  # Body Location or Region
            "T023": "anatomy",  # Body Part, Organ, or Organ Component
            "T034": "finding",  # Laboratory or Test Result
            "T033": "finding",  # Finding
        }
        return mapping.get(semtype, "unknown")

    def process_chunk(self, chunk_text: str) -> dict:
        """Process a text chunk and extract SNOMED metadata.

        Args:
            chunk_text: Text chunk to process

        Returns:
            Dictionary with:
                - entities: List of LinkedEntity objects
                - snomed_codes: List of unique SNOMED codes found
                - semantic_types: List of unique semantic types
                - entity_count: Number of entities found

        Example:
            >>> linker = SNOMEDLinker()
            >>> result = linker.process_chunk("Patient has diabetes mellitus.")
            >>> print(result["snomed_codes"])
            ["73211009"]  # SNOMED code for diabetes mellitus
        """
        # Extract entities
        entities = self.extract_entities(chunk_text)

        # Link to SNOMED if available
        if self.matcher:
            entities = self.link_to_snomed(entities)

        # Extract unique codes and types
        snomed_codes = []
        semantic_types = set()

        for entity in entities:
            if entity.snomed_code:
                snomed_codes.append(entity.snomed_code)
            semantic_types.add(entity.semantic_type)

        return {
            "entities": entities,
            "snomed_codes": list(set(snomed_codes)),  # Unique codes
            "semantic_types": list(semantic_types),
            "entity_count": len(entities),
        }

    def is_available(self) -> bool:
        """Check if the linker is properly initialized.

        Returns:
            True if scispaCy model is loaded
        """
        return self.nlp is not None

    def has_snomed_linking(self) -> bool:
        """Check if SNOMED linking is available.

        Returns:
            True if QuickUMLS matcher is available
        """
        return self.matcher is not None


# Convenience function for quick entity extraction
def extract_medical_entities(
    text: str, model: str = "en_core_sci_lg"
) -> list[LinkedEntity]:
    """Quick utility to extract medical entities from text.

    Args:
        text: Input text
        model: scispaCy model name

    Returns:
        List of extracted entities

    Example:
        >>> entities = extract_medical_entities("Patient has diabetes.")
        >>> for e in entities:
        ...     print(e.text, e.semantic_type)
        diabetes disease
    """
    linker = SNOMEDLinker(scispacy_model=model)
    return linker.extract_entities(text)
