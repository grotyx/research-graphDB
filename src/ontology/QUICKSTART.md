# SNOMED-CT Integration Quick Start

## 5-Minute Quick Start

### Option 1: Query Expansion Only (No Installation)

```python
from src.ontology import ConceptHierarchy

hierarchy = ConceptHierarchy()

# Expand medical query terms
query = "diabetes treatment"
expanded = hierarchy.expand_query(query.split())

print(expanded)
# ['diabetes', 'diabetes mellitus', 'type 2 diabetes', 'T2DM',
#  'hyperglycemia', 'treatment']
```

**Use case**: Better search results without any dependencies.

### Option 2: Full Entity Extraction

```bash
# Install (one-time)
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz
```

```python
from src.ontology import SNOMEDLinker

linker = SNOMEDLinker()

# Extract medical entities
text = "Patient has diabetes mellitus and hypertension."
result = linker.process_chunk(text)

print(result["entities"])
# [LinkedEntity(text="diabetes mellitus", semantic_type="disease"),
#  LinkedEntity(text="hypertension", semantic_type="disease")]
```

**Use case**: Rich metadata for medical documents.

## Common Patterns

### Pattern 1: Enrich Document Metadata

```python
from src.ontology import SNOMEDLinker

linker = SNOMEDLinker()

# During document processing
for chunk in document_chunks:
    snomed_data = linker.process_chunk(chunk.text)

    # Add to metadata
    chunk.metadata.update({
        "snomed_codes": snomed_data["snomed_codes"],
        "semantic_types": snomed_data["semantic_types"],
        "entity_count": snomed_data["entity_count"],
    })
```

### Pattern 2: Expand Search Queries

```python
from src.ontology import ConceptHierarchy

hierarchy = ConceptHierarchy()

# User searches for "heart attack"
user_query = "heart attack"

# Expand to related terms
expanded = hierarchy.get_related_concepts(user_query)
# ['heart attack', 'myocardial infarction', 'MI',
#  'acute coronary syndrome', 'ACS', 'cardiac arrest']

# Search with all terms
results = vector_db.search(" OR ".join(expanded))
```

### Pattern 3: Filter by Medical Entity Type

```python
# Search for diseases only
results = vector_db.query(
    query_texts=["diabetes complications"],
    where={"semantic_types": {"$contains": "disease"}}
)

# Search for drug studies
results = vector_db.query(
    query_texts=["treatment efficacy"],
    where={"semantic_types": {"$contains": "drug"}}
)
```

### Pattern 4: Normalize Medical Terms

```python
from src.ontology import ConceptHierarchy

hierarchy = ConceptHierarchy()

# User uses abbreviation
user_input = "T2DM treatment"

# Normalize to canonical term
canonical = hierarchy.get_canonical_term("T2DM")
# Returns: "diabetes"

# Use for consistent storage
normalized_query = f"{canonical} treatment"
```

## API Cheat Sheet

### SNOMEDLinker

```python
linker = SNOMEDLinker()

# Process text
result = linker.process_chunk(text)
# Returns: {
#   "entities": [LinkedEntity, ...],
#   "snomed_codes": ["12345", ...],
#   "semantic_types": ["disease", ...],
#   "entity_count": int
# }

# Check availability
linker.is_available()          # True if scispaCy loaded
linker.has_snomed_linking()    # True if QuickUMLS available
```

### ConceptHierarchy

```python
hierarchy = ConceptHierarchy()

# Get related concepts
hierarchy.get_related_concepts("diabetes")
# ['diabetes', 'diabetes mellitus', 'T2DM', ...]

# Get canonical term
hierarchy.get_canonical_term("T2DM")
# 'diabetes'

# Find concept type
hierarchy.find_concept_type("diabetes")
# 'disease'

# Expand query
hierarchy.expand_query(["diabetes", "treatment"])
# ['diabetes', 'diabetes mellitus', 'T2DM', 'treatment']

# Expand by type
hierarchy.expand_query_by_type(
    "diabetes heart",
    include_types={"disease"}
)
# Only expands disease terms
```

## Integration Checklist

- [ ] Import modules
- [ ] Initialize SNOMEDLinker (if using entity extraction)
- [ ] Initialize ConceptHierarchy (for query expansion)
- [ ] Add SNOMED processing to document pipeline
- [ ] Store SNOMED metadata in vector DB
- [ ] Expand queries at search time
- [ ] Filter results by semantic type (optional)

## Troubleshooting

### "scispaCy not installed"

```bash
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz
```

### "Model not found"

```bash
# List installed models
python -m spacy info

# Reinstall model
pip install --force-reinstall https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_md-0.5.1.tar.gz
```

### ConceptHierarchy doesn't have my term

ConceptHierarchy has ~50 common medical concepts. For comprehensive coverage, use SNOMEDLinker with QuickUMLS.

Or extend the dictionaries in `concept_hierarchy.py`:

```python
DISEASE_SYNONYMS = {
    "your_disease": ["synonym1", "synonym2"],
    # ... existing diseases
}
```

## Performance Tips

### 1. Cache Entity Extraction

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_snomed_data(text: str) -> dict:
    return linker.process_chunk(text)
```

### 2. Batch Processing

```python
# Process multiple chunks efficiently
results = []
for chunk in chunks:
    result = linker.process_chunk(chunk.text)
    results.append(result)
```

### 3. Limit Query Expansion

```python
# Too many terms can slow down search
expanded = hierarchy.expand_query(query.split())
limited = expanded[:20]  # Use top 20 terms only
```

## Examples

Run the demo script:

```bash
python examples/ontology_demo.py
```

Run tests:

```bash
pytest tests/test_ontology.py -v
```

## More Information

- **Full Guide**: `docs/SNOMED_Integration_Guide.md`
- **API Reference**: `src/ontology/README.md`
- **Implementation**: `docs/SNOMED_Implementation_Summary.md`

## Quick Links

- scispaCy: https://allenai.github.io/scispacy/
- SNOMED-CT: https://www.snomed.org/
- QuickUMLS: https://github.com/Georgetown-IR-Lab/QuickUMLS
