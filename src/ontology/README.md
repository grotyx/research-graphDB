# SNOMED-CT Ontology Integration

Medical entity extraction and concept hierarchy for the Medical KAG system.

## Overview

This module provides two main components:

1. **SNOMEDLinker**: Medical entity extraction using scispaCy NER
2. **ConceptHierarchy**: Basic medical concept relationships for query expansion

## Installation

### Required

```bash
# Install scispaCy
pip install scispacy

# Install a scispaCy model (choose one)
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz
```

### Optional (for SNOMED linking)

```bash
# Install QuickUMLS
pip install quickumls

# Download and setup UMLS database (requires UMLS license)
# Follow instructions at: https://github.com/Georgetown-IR-Lab/QuickUMLS
```

## Usage

### Basic Entity Extraction

```python
from src.ontology import SNOMEDLinker

# Initialize linker
linker = SNOMEDLinker()

# Extract entities from medical text
text = "Patient diagnosed with diabetes mellitus type 2."
result = linker.process_chunk(text)

print(result["entities"])
# [LinkedEntity(text="diabetes mellitus type 2", semantic_type="disease", ...)]

print(result["snomed_codes"])
# List of SNOMED-CT codes (if QuickUMLS available)
```

### Query Expansion

```python
from src.ontology import ConceptHierarchy

# Initialize hierarchy
hierarchy = ConceptHierarchy()

# Get related concepts
related = hierarchy.get_related_concepts("diabetes")
print(related)
# ['diabetes', 'diabetes mellitus', 'type 2 diabetes', 'T2DM', ...]

# Expand query for better search
query = "diabetes treatment"
expanded = hierarchy.expand_query(query.split())
print(expanded)
# ['diabetes', 'diabetes mellitus', 'type 2 diabetes', 'treatment', ...]
```

### Integration with RAG Pipeline

```python
from src.ontology import SNOMEDLinker, ConceptHierarchy

linker = SNOMEDLinker()
hierarchy = ConceptHierarchy()

# Process document chunk
chunk_text = "Study on metformin efficacy in type 2 diabetes..."

# Extract medical entities
entities = linker.process_chunk(chunk_text)

# Create metadata for vector DB
metadata = {
    "semantic_types": entities["semantic_types"],
    "snomed_codes": entities["snomed_codes"],
    "entity_count": entities["entity_count"],
}

# Expand query terms for search
query = "diabetes treatment"
expanded_query = hierarchy.expand_query(query.split())
```

## Features

### SNOMEDLinker

- **Medical NER**: Extract diseases, drugs, procedures, anatomy
- **Entity Linking**: Map entities to SNOMED-CT codes (with QuickUMLS)
- **Confidence Scores**: Entity extraction confidence
- **Semantic Types**: Classify entities by medical type
- **Graceful Degradation**: Works without QuickUMLS (NER only)

### ConceptHierarchy

- **Concept Expansion**: Map terms to related medical concepts
- **Synonym Mapping**: Handle medical terminology variations
- **Type Classification**: Identify disease/drug/anatomy/procedure
- **Query Expansion**: Enhance search with related terms
- **Canonical Terms**: Map variants to standard terms

## Architecture

```
┌─────────────────┐
│  Medical Text   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  scispaCy NER   │  ← Entity Extraction
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LinkedEntity    │  ← Entities + Types
└────────┬────────┘
         │
         ▼ (optional)
┌─────────────────┐
│   QuickUMLS     │  ← SNOMED Linking
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ SNOMED Codes    │  ← Standardized Concepts
└─────────────────┘
```

## Supported Medical Entities

### scispaCy Models

- **en_core_sci_md**: General biomedical entities
- **en_ner_bc5cdr_md**: Diseases and chemicals (BC5CDR dataset)
- **en_ner_bionlp13cg_md**: Cancer genetics entities

### Entity Types

- Diseases and syndromes
- Drugs and chemicals
- Procedures (diagnostic/therapeutic)
- Anatomical structures
- Laboratory findings
- Signs and symptoms

## Limitations

### Current Implementation

1. **Basic NER Only**: Uses scispaCy for entity extraction
2. **No Full SNOMED Hierarchy**: Simplified concept relationships
3. **QuickUMLS Optional**: SNOMED linking requires separate setup
4. **English Only**: Current models support English medical text

### Future Enhancements

1. **Full SNOMED RF2**: Integrate complete SNOMED-CT hierarchy
2. **Relationship Types**: Parent-child, is-a, part-of relationships
3. **Multi-lingual**: Support for other languages
4. **Custom Models**: Fine-tune on specialty-specific data

## Performance

### Entity Extraction

- **Speed**: ~100-500 tokens/second (CPU)
- **Memory**: ~1-2GB for scispaCy model
- **Accuracy**: ~85-90% F1 on biomedical NER benchmarks

### Query Expansion

- **Speed**: Instant (in-memory lookup)
- **Memory**: ~10MB for concept hierarchy
- **Coverage**: ~50 common medical concepts

## Testing

```bash
# Run ontology tests
pytest tests/test_ontology.py -v

# Run specific test
pytest tests/test_ontology.py::TestSNOMEDLinker::test_extract_entities -v
```

## Examples

See `examples/ontology_demo.py` for complete usage examples:

```bash
cd /path/to/project
python examples/ontology_demo.py
```

## API Reference

### SNOMEDLinker

```python
class SNOMEDLinker:
    def __init__(
        self,
        use_quickumls: bool = False,
        quickumls_path: Optional[str] = None,
        scispacy_model: str = "en_core_sci_md"
    )

    def extract_entities(self, text: str) -> list[LinkedEntity]
    def link_to_snomed(self, entities: list[LinkedEntity]) -> list[LinkedEntity]
    def process_chunk(self, chunk_text: str) -> dict
    def is_available(self) -> bool
    def has_snomed_linking(self) -> bool
```

### ConceptHierarchy

```python
class ConceptHierarchy:
    def expand_query(self, terms: List[str]) -> List[str]
    def get_related_concepts(self, concept: str) -> List[str]
    def get_canonical_term(self, term: str) -> str
    def find_concept_type(self, term: str) -> str | None
    def expand_query_by_type(
        self,
        query: str,
        include_types: Set[str] | None = None
    ) -> List[str]
```

## References

- [scispaCy](https://allenai.github.io/scispacy/)
- [QuickUMLS](https://github.com/Georgetown-IR-Lab/QuickUMLS)
- [SNOMED-CT](https://www.snomed.org/)
- [UMLS](https://www.nlm.nih.gov/research/umls/)

## License

Follows the main project license. Note that SNOMED-CT and UMLS have their own licenses.
