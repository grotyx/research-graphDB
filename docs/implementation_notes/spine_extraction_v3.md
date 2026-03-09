# Spine-Specific Extraction Implementation Notes

**Date**: 2025-12-04
**Version**: v3.0
**Tasks Completed**: 2.1.1, 2.1.2, 2.1.3, 2.1.4

---

## Overview

Extended the Gemini Vision PDF Processor to extract spine-specific metadata for GraphRAG system. This enhancement enables structured knowledge graph construction for spine surgery domain.

---

## 1. Modified Files

### 1.1 `src/src/builder/gemini_vision_processor.py`

**Changes:**

#### New Dataclasses

```python
@dataclass
class ExtractedOutcome:
    """추출된 결과 데이터."""
    name: str
    value_intervention: str = ""
    value_control: str = ""
    p_value: str = ""

@dataclass
class SpineMetadata:
    """척추 특화 메타데이터."""
    sub_domain: str = ""  # Degenerative, Deformity, Trauma, Tumor, Basic Science
    pathology: str = ""
    anatomy_level: str = ""  # e.g., "L4-5", "C5-6"
    interventions: list[str] = field(default_factory=list)
    outcomes: list[ExtractedOutcome] = field(default_factory=list)
```

#### Extended ExtractedMetadata

```python
@dataclass
class ExtractedMetadata:
    # ... existing fields ...
    spine: SpineMetadata = field(default_factory=SpineMetadata)  # NEW
```

#### Enhanced VISION_EXTRACTION_SCHEMA

Added `spine_metadata` object to schema:

```python
"spine_metadata": {
    "type": "OBJECT",
    "properties": {
        "sub_domain": {
            "type": "STRING",
            "enum": ["Degenerative", "Deformity", "Trauma", "Tumor", "Basic Science", "Not Applicable"]
        },
        "pathology": {"type": "STRING"},
        "anatomy_level": {"type": "STRING"},
        "interventions": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "outcomes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "value_intervention": {"type": "STRING"},
                    "value_control": {"type": "STRING"},
                    "p_value": {"type": "STRING"}
                }
            }
        }
    }
}
```

#### Enhanced Prompt

Added section 1.5 to `VISION_EXTRACTION_PROMPT`:

```text
### 1.5. Extract Spine-Specific Metadata (if applicable)
- Sub-domain: Classify the primary spine subspecialty area
- Pathology: Specific diagnosis or condition
- Anatomy Level: Spinal levels involved
- Interventions: List all surgical procedures (use standard abbreviations)
- Outcomes: Extract key outcome measures with results and statistics
```

#### Updated Parsing Logic

```python
# 척추 메타데이터 파싱
spine_dict = meta_dict.get("spine_metadata", {})
spine_outcomes = []
for outcome_dict in spine_dict.get("outcomes", []):
    spine_outcomes.append(ExtractedOutcome(
        name=outcome_dict.get("name", ""),
        value_intervention=outcome_dict.get("value_intervention", ""),
        value_control=outcome_dict.get("value_control", ""),
        p_value=outcome_dict.get("p_value", "")
    ))

spine_metadata = SpineMetadata(
    sub_domain=spine_dict.get("sub_domain", ""),
    pathology=spine_dict.get("pathology", ""),
    anatomy_level=spine_dict.get("anatomy_level", ""),
    interventions=spine_dict.get("interventions", []),
    outcomes=spine_outcomes
)
```

---

## 2. New Files

### 2.1 `src/src/builder/spine_domain_classifier.py`

**Purpose**: Post-processing and normalization of extracted spine metadata.

**Key Classes:**

#### NormalizedIntervention
```python
@dataclass
class NormalizedIntervention:
    original: str
    normalized: str
    confidence: float = 1.0
    aliases: list[str] = field(default_factory=list)
```

#### NormalizedOutcome
```python
@dataclass
class NormalizedOutcome:
    original: str
    normalized: str
    value_intervention: str = ""
    value_control: str = ""
    p_value: str = ""
    confidence: float = 1.0
```

#### ClassifiedSpineData
```python
@dataclass
class ClassifiedSpineData:
    sub_domain: str
    pathology: NormalizedPathology
    anatomy_level: str
    interventions: list[NormalizedIntervention]
    outcomes: list[NormalizedOutcome]
```

#### SpineDomainClassifier

Main class for classification and normalization:

**Methods:**

1. `classify_and_normalize(metadata: ExtractedMetadata) -> ClassifiedSpineData`
   - Takes Gemini Vision output
   - Normalizes all entities using EntityNormalizer
   - Returns structured spine data

2. `extract_from_text(text: str, sub_domain: str = "") -> ClassifiedSpineData`
   - Extracts entities directly from text
   - Useful for title/abstract processing without full PDF

3. `_normalize_pathology(pathology: str) -> NormalizedPathology`
   - Normalizes disease/diagnosis names

4. `_normalize_interventions(interventions: list[str]) -> list[NormalizedIntervention]`
   - Normalizes surgical procedures
   - Retrieves aliases for graph matching

5. `_normalize_outcomes(outcomes: list[ExtractedOutcome]) -> list[NormalizedOutcome]`
   - Normalizes outcome measures
   - Preserves statistical values

6. `_validate_anatomy_level(anatomy_level: str) -> str`
   - Cleans anatomy level strings
   - Standardizes format (e.g., "L4-L5" → "L4-5")

7. `_extract_anatomy_from_text(text: str) -> str`
   - Regex-based anatomy level extraction
   - Supports patterns: L4-5, C5-6, T10-L2, etc.

**Usage Example:**

```python
from src.builder.gemini_vision_processor import GeminiPDFProcessor
from src.builder.spine_domain_classifier import SpineDomainClassifier

async def process_paper():
    # Step 1: Extract with Gemini Vision
    processor = GeminiPDFProcessor()
    result = await processor.process_pdf("paper.pdf")

    # Step 2: Classify and normalize
    classifier = SpineDomainClassifier()
    classified = classifier.classify_and_normalize(result.metadata)

    # Step 3: Use for graph construction
    print(f"Sub-domain: {classified.sub_domain}")
    print(f"Pathology: {classified.pathology.normalized}")
    print(f"Interventions: {[i.normalized for i in classified.interventions]}")
    print(f"Outcomes: {[o.normalized for o in classified.outcomes]}")
```

---

### 2.2 `src/tests/builder/test_spine_domain_classifier.py`

**Purpose**: Comprehensive unit tests for SpineDomainClassifier.

**Test Coverage:**

1. `test_classify_and_normalize_basic`
   - Basic classification workflow
   - Intervention normalization (BESS → UBE)
   - Outcome extraction with statistics

2. `test_anatomy_level_validation`
   - Format standardization (L4-L5 → L4-5)
   - Case insensitivity

3. `test_extract_from_text`
   - Direct text extraction
   - Multiple interventions and outcomes
   - Anatomy level detection

4. `test_extract_anatomy_from_text`
   - Regex pattern matching
   - Various formats (L4-5, C5-6, T10-L2)

5. `test_empty_data_handling`
   - Graceful handling of missing data

6. `test_intervention_aliases`
   - Alias retrieval and mapping

7. `test_classifier_without_normalizer`
   - Fallback behavior when EntityNormalizer unavailable

**Mock Classes:**

- `MockEntityNormalizer`: Simulates entity_normalizer for testing
- `MockNormalizationResult`: Test-friendly normalization results

**Run Tests:**

```bash
cd .
pytest tests/builder/test_spine_domain_classifier.py -v
```

---

## 3. Integration Points

### 3.1 EntityNormalizer Dependency

SpineDomainClassifier depends on:
- `src/src/graph/entity_normalizer.py`

**Current Status**: Already implemented (Phase 1: Foundation)

**Integration:**

```python
try:
    from ..graph.entity_normalizer import EntityNormalizer, NormalizationResult
except ImportError:
    # Graceful degradation if graph module unavailable
    EntityNormalizer = None
```

### 3.2 Neo4j Graph Builder

Classified data will be consumed by:
- `relationship_builder.py` (Task 2.2.1-2.2.4)
- `taxonomy_manager.py` (Task 2.2.5)

**Example Usage:**

```python
# In relationship_builder.py
from src.builder.spine_domain_classifier import SpineDomainClassifier

classifier = SpineDomainClassifier()
classified = classifier.classify_and_normalize(metadata)

# Create nodes
paper_node = create_paper_node(metadata)
pathology_node = create_pathology_node(classified.pathology)
anatomy_node = create_anatomy_node(classified.anatomy_level)

# Create relationships
for intervention in classified.interventions:
    interv_node = create_intervention_node(intervention)
    create_investigates_relation(paper_node, interv_node)

    for outcome in classified.outcomes:
        outcome_node = create_outcome_node(outcome)
        create_affects_relation(
            interv_node,
            outcome_node,
            p_value=outcome.p_value,
            value=outcome.value_intervention
        )
```

---

## 4. Data Flow

```
┌─────────────────────────────────────────────────────────┐
│           PDF Input (spine surgery paper)                │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│        GeminiPDFProcessor.process_pdf()                  │
│  - File API upload                                       │
│  - Vision analysis with extended schema                  │
│  - Extracts spine_metadata object                        │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              ExtractedMetadata                           │
│  metadata.spine.sub_domain: "Degenerative"               │
│  metadata.spine.pathology: "Lumbar Stenosis"             │
│  metadata.spine.anatomy_level: "L4-5"                    │
│  metadata.spine.interventions: ["TLIF", "BESS"]          │
│  metadata.spine.outcomes: [                              │
│    {name: "VAS", value_intervention: "2.1", p_value: ...}│
│  ]                                                       │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│   SpineDomainClassifier.classify_and_normalize()         │
│  - Normalizes interventions (BESS → UBE)                │
│  - Normalizes outcomes (Visual Analog Scale → VAS)       │
│  - Normalizes pathology                                  │
│  - Validates anatomy level format                        │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│           ClassifiedSpineData                            │
│  sub_domain: "Degenerative"                              │
│  pathology: NormalizedPathology(                         │
│    normalized="Lumbar Stenosis", confidence=1.0)         │
│  interventions: [                                        │
│    NormalizedIntervention(normalized="TLIF", ...),       │
│    NormalizedIntervention(normalized="UBE",              │
│      aliases=["BESS", "Biportal"], ...)                  │
│  ]                                                       │
│  outcomes: [                                             │
│    NormalizedOutcome(normalized="VAS",                   │
│      value_intervention="2.1", p_value="0.001")          │
│  ]                                                       │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│            Neo4j Graph Construction                      │
│  (relationship_builder.py - Task 2.2.x)                  │
│                                                          │
│  Nodes Created:                                          │
│    (:Paper {title, year, sub_domain})                    │
│    (:Pathology {name: "Lumbar Stenosis"})                │
│    (:Anatomy {name: "L4-5", region: "lumbar"})           │
│    (:Intervention {name: "TLIF"})                        │
│    (:Intervention {name: "UBE", aliases: ["BESS"...]})   │
│    (:Outcome {name: "VAS", type: "clinical"})            │
│                                                          │
│  Relationships Created:                                  │
│    (Paper)-[:STUDIES]->(Pathology)                       │
│    (Paper)-[:INVESTIGATES]->(Intervention)               │
│    (Intervention)-[:AFFECTS {                            │
│      value: "2.1", p_value: 0.001                        │
│    }]->(Outcome)                                         │
│    (Intervention)-[:IS_A]->(Parent_Intervention)         │
└─────────────────────────────────────────────────────────┘
```

---

## 5. Validation & Testing

### 5.1 Schema Validation

Gemini enforces schema via `response_schema` parameter:

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=VISION_EXTRACTION_SCHEMA  # Strict validation
)
```

**Guaranteed:**
- `sub_domain` is one of enum values
- `outcomes` array contains objects with required fields
- Type safety (STRING, ARRAY, OBJECT)

### 5.2 Normalization Validation

SpineDomainClassifier validates:

```python
# Confidence scores
if intervention.confidence < 0.5:
    logger.warning(f"Low confidence normalization: {intervention.original}")

# Anatomy format
anatomy = self._validate_anatomy_level(raw_anatomy)  # Standardizes format

# Empty data handling
if not pathology:
    return NormalizedPathology(original="", normalized="", confidence=0.0)
```

### 5.3 Test Coverage

```bash
# Run specific tests
pytest tests/builder/test_spine_domain_classifier.py -v

# Expected output:
# test_classify_and_normalize_basic PASSED
# test_anatomy_level_validation PASSED
# test_extract_from_text PASSED
# test_extract_anatomy_from_text PASSED
# test_empty_data_handling PASSED
# test_intervention_aliases PASSED
# test_classifier_without_normalizer PASSED
```

---

## 6. Cost & Performance

### 6.1 Token Usage

Extended schema adds approximately:

- **Prompt tokens**: +150 (schema + instructions)
- **Output tokens**: +100-300 per paper (spine_metadata object)

**Total per paper**: +250-450 tokens (~$0.0001-0.0002 additional cost)

### 6.2 Processing Time

- **Schema extension**: No significant impact (single API call)
- **Normalization**: ~10-50ms per paper (in-memory dict lookups)

---

## 7. Future Enhancements

### 7.1 Sub-domain Auto-detection

Currently relies on Gemini classification. Could add:

```python
def _detect_sub_domain(self, pathology: str, interventions: list[str]) -> str:
    """Rule-based sub-domain detection as fallback."""
    if "stenosis" in pathology.lower() or "herniation" in pathology.lower():
        return "Degenerative"
    if "scoliosis" in pathology.lower() or "kyphosis" in pathology.lower():
        return "Deformity"
    # ... etc
```

### 7.2 Anatomy Hierarchy

```python
def get_anatomy_region(self, level: str) -> str:
    """Determine spinal region from level."""
    if level.startswith("C"):
        return "cervical"
    elif level.startswith("T"):
        return "thoracic"
    elif level.startswith("L"):
        return "lumbar"
    elif level.startswith("S"):
        return "sacral"
```

### 7.3 Outcome Type Classification

```python
OUTCOME_TYPES = {
    "VAS": "clinical",
    "ODI": "functional",
    "Cobb Angle": "radiological",
    "Fusion Rate": "radiological",
    # ...
}
```

---

## 8. Known Limitations

1. **Non-spine papers**: `sub_domain: "Not Applicable"` for non-spine content
2. **Complex anatomies**: "T10-L2" requires careful parsing
3. **Multiple pathologies**: Currently extracts primary pathology only
4. **Outcome unit extraction**: Not yet extracted (e.g., "%" vs "points")

---

## 9. Related Documentation

- [TRD_v3_GraphRAG.md](../TRD_v3_GraphRAG.md) - Section 5: Spine-Specific Features
- [Tasks_v3_GraphRAG.md](../Tasks_v3_GraphRAG.md) - Phase 2.1 status
- [entity_normalizer.py](../../src/graph/entity_normalizer.py) - Normalization rules

---

## 10. Completion Checklist

- [x] Extended VISION_EXTRACTION_SCHEMA with spine_metadata
- [x] Added SpineMetadata and ExtractedOutcome dataclasses
- [x] Updated VISION_EXTRACTION_PROMPT with spine instructions
- [x] Implemented spine metadata parsing in process_pdf()
- [x] Created SpineDomainClassifier with normalization logic
- [x] Integrated EntityNormalizer for terminology standardization
- [x] Added anatomy level validation and extraction
- [x] Implemented text-based extraction (extract_from_text)
- [x] Created comprehensive unit tests
- [x] Updated Tasks_v3_GraphRAG.md (Tasks 2.1.1-2.1.4 marked complete)
- [ ] Integration testing with real spine surgery PDFs (pending)
- [ ] Neo4j graph builder integration (next phase: 2.2.x)

---

**Implementation completed**: 2025-12-04
**Next steps**: Begin Graph Builder implementation (Tasks 2.2.1-2.2.5)
