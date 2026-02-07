# Graph Module API Documentation

## Overview

The Graph module provides Neo4j-based knowledge graph functionality for spine surgery research. It includes node/relationship schema, entity normalization, relationship building, taxonomy management, and Neo4j client operations.

**Module Path**: `/Users/sangminpark/Desktop/rag_research/src/graph/`

**Key Components**:
- `spine_schema.py` - Node and relationship definitions
- `neo4j_client.py` - Neo4j database operations
- `entity_normalizer.py` - Medical terminology normalization
- `relationship_builder.py` - Graph construction from papers
- `taxonomy_manager.py` - Intervention hierarchy management

---

## spine_schema.py

Defines the graph schema for spine surgery knowledge representation in Neo4j.

### Enums

#### `SpineSubDomain`
Spine surgery sub-domains.

```python
class SpineSubDomain(Enum):
    DEGENERATIVE = "Degenerative"
    DEFORMITY = "Deformity"
    TRAUMA = "Trauma"
    TUMOR = "Tumor"
    BASIC_SCIENCE = "Basic Science"
```

#### `EvidenceLevel`
Oxford Centre for Evidence-Based Medicine levels.

```python
class EvidenceLevel(Enum):
    LEVEL_1A = "1a"  # Meta-analysis of RCTs
    LEVEL_1B = "1b"  # Individual RCT
    LEVEL_2A = "2a"  # Systematic review of cohort studies
    LEVEL_2B = "2b"  # Individual cohort study
    LEVEL_3 = "3"    # Case-control study
    LEVEL_4 = "4"    # Case series
    LEVEL_5 = "5"    # Expert opinion
```

#### `StudyDesign`
Research design types.

```python
class StudyDesign(Enum):
    META_ANALYSIS = "meta-analysis"
    SYSTEMATIC_REVIEW = "systematic-review"
    RCT = "RCT"
    PROSPECTIVE_COHORT = "prospective-cohort"
    RETROSPECTIVE_COHORT = "retrospective-cohort"
    CASE_CONTROL = "case-control"
    CASE_SERIES = "case-series"
    CASE_REPORT = "case-report"
    EXPERT_OPINION = "expert-opinion"
    OTHER = "other"
```

#### `OutcomeType`
Outcome variable categories.

```python
class OutcomeType(Enum):
    CLINICAL = "clinical"        # VAS, ODI, JOA
    RADIOLOGICAL = "radiological"  # Fusion rate, Cobb angle
    FUNCTIONAL = "functional"    # Return to work, ADL
    COMPLICATION = "complication"  # Infection, revision
```

#### `InterventionCategory`
Surgical intervention categories.

```python
class InterventionCategory(Enum):
    FUSION = "fusion"
    DECOMPRESSION = "decompression"
    FIXATION = "fixation"
    OSTEOTOMY = "osteotomy"
    TUMOR_RESECTION = "tumor_resection"
    VERTEBROPLASTY = "vertebroplasty"
    OTHER = "other"
```

### Node Classes

#### `PaperNode`
Represents a medical paper in the graph.

**Neo4j Label**: `Paper`

```python
@dataclass
class PaperNode:
    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    journal: str = ""
    doi: str = ""
    pmid: str = ""
    sub_domain: str = ""  # SpineSubDomain value
    study_design: str = ""  # StudyDesign value
    evidence_level: str = "5"  # EvidenceLevel value
    sample_size: int = 0
    follow_up_months: int = 0
    abstract: str = ""
    created_at: Optional[datetime] = None
```

**Methods**:

```python
def to_neo4j_properties(self) -> dict:
    """Convert to Neo4j property dictionary."""

@classmethod
def from_neo4j_record(cls, record: dict) -> "PaperNode":
    """Create from Neo4j record."""
```

**Example**:

```python
paper = PaperNode(
    paper_id="PMID_12345",
    title="TLIF vs PLIF for Lumbar Stenosis",
    authors=["Smith J", "Doe A"],
    year=2024,
    journal="Spine",
    sub_domain="Degenerative",
    evidence_level="1b"
)

props = paper.to_neo4j_properties()
# {"paper_id": "PMID_12345", "title": "TLIF vs PLIF...", ...}
```

#### `PathologyNode`
Represents a spinal pathology/diagnosis.

**Neo4j Label**: `Pathology`

```python
@dataclass
class PathologyNode:
    name: str  # Lumbar Stenosis, AIS, Spondylolisthesis
    category: str = ""  # degenerative, deformity, trauma, tumor
    icd10_code: str = ""
    description: str = ""
    aliases: list[str] = field(default_factory=list)
```

#### `AnatomyNode`
Represents anatomical location.

**Neo4j Label**: `Anatomy`

```python
@dataclass
class AnatomyNode:
    name: str  # L4-5, C5-6, Thoracolumbar junction
    region: str = ""  # cervical, thoracic, lumbar, sacral
    level_count: int = 1  # Number of surgical levels
```

#### `InterventionNode`
Represents a surgical intervention.

**Neo4j Label**: `Intervention`

```python
@dataclass
class InterventionNode:
    name: str  # TLIF, OLIF, UBE, Laminectomy
    full_name: str = ""
    category: str = ""  # InterventionCategory value
    approach: str = ""  # anterior, posterior, lateral
    is_minimally_invasive: bool = False
    aliases: list[str] = field(default_factory=list)
```

#### `OutcomeNode`
Represents an outcome variable.

**Neo4j Label**: `Outcome`

```python
@dataclass
class OutcomeNode:
    name: str  # Fusion Rate, VAS, ODI, JOA, SVA
    type: str = ""  # OutcomeType value
    unit: str = ""  # %, points, mm
    direction: str = ""  # higher_is_better, lower_is_better
    description: str = ""
```

### Relationship Classes

#### `StudiesRelation`
Paper → Pathology research relationship.

**Cypher**: `(Paper)-[:STUDIES]->(Pathology)`

```python
@dataclass
class StudiesRelation:
    source_paper_id: str
    target_pathology: str
    is_primary: bool = True  # Primary research target
```

#### `InvestigatesRelation`
Paper → Intervention investigation relationship.

**Cypher**: `(Paper)-[:INVESTIGATES]->(Intervention)`

```python
@dataclass
class InvestigatesRelation:
    paper_id: str
    intervention_name: str
    is_comparison: bool = False  # Comparative study flag
```

#### `AffectsRelation`
Intervention → Outcome relationship (core reasoning path).

**Cypher**: `(Intervention)-[:AFFECTS]->(Outcome)`

```python
@dataclass
class AffectsRelation:
    intervention_name: str
    outcome_name: str
    source_paper_id: str
    value: str = ""  # Measured value (e.g., "85.2%")
    value_control: str = ""  # Control group value
    p_value: Optional[float] = None
    effect_size: str = ""
    confidence_interval: str = ""  # "95% CI: 1.2-4.3"
    is_significant: bool = False
    direction: str = ""  # improved, worsened, unchanged
```

**Example**:

```python
affects = AffectsRelation(
    intervention_name="TLIF",
    outcome_name="Fusion Rate",
    source_paper_id="PMID_12345",
    value="92%",
    value_control="85%",
    p_value=0.001,
    is_significant=True,
    direction="improved"
)
```

#### `IsARelation`
Intervention hierarchy relationship.

**Cypher**: `(Intervention)-[:IS_A]->(Intervention)`

```python
@dataclass
class IsARelation:
    child_name: str
    parent_name: str
    level: int = 1  # Hierarchy depth
```

**Example**: `(TLIF)-[:IS_A]->(Interbody Fusion)-[:IS_A]->(Fusion Surgery)`

### Schema Manager

#### `SpineGraphSchema`
Manages Neo4j schema creation and constraints.

**Constants**:

```python
NODE_LABELS = ["Paper", "Pathology", "Anatomy", "Intervention", "Outcome"]

RELATIONSHIP_TYPES = [
    "STUDIES", "LOCATED_AT", "INVESTIGATES", "TREATS",
    "AFFECTS", "IS_A", "CITES", "SUPPORTS", "CONTRADICTS"
]
```

**Methods**:

```python
@classmethod
def get_create_constraints_cypher(cls) -> list[str]:
    """Generate constraint creation Cypher queries."""

@classmethod
def get_create_indexes_cypher(cls) -> list[str]:
    """Generate index creation Cypher queries."""

@classmethod
def get_init_taxonomy_cypher(cls) -> str:
    """Generate taxonomy initialization Cypher."""
```

### Cypher Templates

#### `CypherTemplates`
Pre-defined Cypher query templates.

**Common Templates**:

```python
# Paper creation/update
MERGE_PAPER = "MERGE (p:Paper {paper_id: $paper_id}) SET p += $properties RETURN p"

# Paper → Pathology relationship
CREATE_STUDIES_RELATION = """
    MATCH (p:Paper {paper_id: $paper_id})
    MERGE (path:Pathology {name: $pathology_name})
    MERGE (p)-[r:STUDIES]->(path)
    SET r.is_primary = $is_primary
    RETURN p, r, path
"""

# Intervention → Outcome relationship
CREATE_AFFECTS_RELATION = """
    MATCH (i:Intervention {name: $intervention_name})
    MERGE (o:Outcome {name: $outcome_name})
    MERGE (i)-[r:AFFECTS]->(o)
    SET r += $properties
    RETURN i, r, o
"""

# Intervention hierarchy traversal
GET_INTERVENTION_HIERARCHY = """
    MATCH (i:Intervention {name: $intervention_name})
    OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
    RETURN i, collect(nodes(path)) as hierarchy
"""
```

---

## neo4j_client.py

Neo4j database connection and query management.

### `Neo4jConfig`

Configuration for Neo4j connection.

```python
@dataclass
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_timeout: int = 30

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Load configuration from environment variables."""
```

**Environment Variables**:
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

### `Neo4jClient`

Async Neo4j client for database operations.

**Initialization**:

```python
async with Neo4jClient() as client:
    await client.initialize_schema()
    result = await client.run_query("MATCH (n) RETURN n LIMIT 10")
```

**Core Methods**:

```python
async def connect(self) -> None:
    """Establish Neo4j connection."""

async def close(self) -> None:
    """Close Neo4j connection."""

async def initialize_schema(self) -> None:
    """Initialize schema (constraints, indexes, taxonomy)."""

async def run_query(
    self,
    query: str,
    parameters: Optional[dict] = None,
    fetch_all: bool = True
) -> list[dict]:
    """Execute read query."""

async def run_write_query(
    self,
    query: str,
    parameters: Optional[dict] = None
) -> dict:
    """Execute write query in transaction."""
```

**Paper Operations**:

```python
async def create_paper(self, paper: PaperNode) -> dict:
    """Create or update paper node."""

async def get_paper(self, paper_id: str) -> Optional[dict]:
    """Retrieve paper by ID."""

async def list_papers(
    self,
    sub_domain: Optional[str] = None,
    evidence_level: Optional[str] = None,
    limit: int = 100
) -> list[dict]:
    """List papers with optional filters."""
```

**Relationship Operations**:

```python
async def create_studies_relation(
    self,
    paper_id: str,
    pathology_name: str,
    is_primary: bool = True
) -> dict:
    """Create Paper → Pathology relationship."""

async def create_investigates_relation(
    self,
    paper_id: str,
    intervention_name: str,
    is_comparison: bool = False
) -> dict:
    """Create Paper → Intervention relationship."""

async def create_affects_relation(
    self,
    intervention_name: str,
    outcome_name: str,
    source_paper_id: str,
    value: str = "",
    value_control: str = "",
    p_value: Optional[float] = None,
    effect_size: str = "",
    confidence_interval: str = "",
    is_significant: bool = False,
    direction: str = ""
) -> dict:
    """Create Intervention → Outcome relationship with statistics."""
```

**Search Operations**:

```python
async def get_intervention_hierarchy(self, intervention_name: str) -> list[dict]:
    """Retrieve intervention hierarchy."""

async def search_effective_interventions(self, outcome_name: str) -> list[dict]:
    """Find effective interventions for outcome."""

async def find_conflicting_results(self, intervention_name: str) -> list[dict]:
    """Find conflicting research results."""
```

**Example**:

```python
async with Neo4jClient() as client:
    # Initialize schema
    await client.initialize_schema()

    # Create paper
    paper = PaperNode(
        paper_id="test_001",
        title="TLIF for Lumbar Stenosis",
        year=2024,
        evidence_level="1b"
    )
    await client.create_paper(paper)

    # Create relationships
    await client.create_studies_relation("test_001", "Lumbar Stenosis")
    await client.create_investigates_relation("test_001", "TLIF")

    # Create evidence relationship
    await client.create_affects_relation(
        intervention_name="TLIF",
        outcome_name="Fusion Rate",
        source_paper_id="test_001",
        value="92%",
        p_value=0.001,
        is_significant=True,
        direction="improved"
    )

    # Query
    stats = await client.get_stats()
    print(f"Nodes: {stats['nodes']}, Relationships: {stats['relationships']}")
```

---

## entity_normalizer.py

Medical terminology normalization for consistent entity representation.

### `NormalizationResult`

Result of entity normalization.

```python
@dataclass
class NormalizationResult:
    original: str
    normalized: str
    confidence: float = 1.0
    matched_alias: str = ""
```

### `EntityNormalizer`

Normalizes spine surgery terminology.

**Terminology Dictionaries**:

```python
INTERVENTION_ALIASES = {
    "UBE": ["BESS", "Biportal", "Unilateral Biportal Endoscopic", ...],
    "TLIF": ["Transforaminal Lumbar Interbody Fusion", ...],
    "OLIF": ["Oblique Lumbar Interbody Fusion", "ATP approach", "OLIF51", ...],
    # ... 30+ interventions with aliases
}

OUTCOME_ALIASES = {
    "VAS": ["Visual Analog Scale", "Pain Score", "VAS-back", "VAS-leg"],
    "ODI": ["Oswestry Disability Index", "Oswestry Score"],
    "Fusion Rate": ["Solid fusion rate", "Bony fusion"],
    # ... 15+ outcomes with aliases
}

PATHOLOGY_ALIASES = {
    "Lumbar Stenosis": ["Lumbar Spinal Stenosis", "LSS", "Central Stenosis"],
    "AIS": ["Adolescent Idiopathic Scoliosis", "Idiopathic Scoliosis"],
    # ... 10+ pathologies with aliases
}
```

**Methods**:

```python
def normalize_intervention(self, text: str) -> NormalizationResult:
    """Normalize surgical intervention name."""

def normalize_outcome(self, text: str) -> NormalizationResult:
    """Normalize outcome variable name."""

def normalize_pathology(self, text: str) -> NormalizationResult:
    """Normalize pathology name."""

def normalize_all(self, text: str) -> dict[str, NormalizationResult]:
    """Attempt normalization for all entity types."""

def extract_and_normalize_interventions(self, text: str) -> list[NormalizationResult]:
    """Extract and normalize interventions from text."""

def extract_and_normalize_outcomes(self, text: str) -> list[NormalizationResult]:
    """Extract and normalize outcomes from text."""

def get_all_aliases(self, canonical_name: str, entity_type: str = "intervention") -> list[str]:
    """Get all aliases for a canonical name."""
```

**Example**:

```python
normalizer = EntityNormalizer()

# Intervention normalization
result = normalizer.normalize_intervention("Biportal Endoscopic")
# result.normalized == "UBE", confidence == 1.0

# Outcome normalization
result = normalizer.normalize_outcome("Visual Analog Scale")
# result.normalized == "VAS", confidence == 1.0

# Extract from text
text = "Comparison of TLIF and OLIF for treatment of lumbar stenosis"
interventions = normalizer.extract_and_normalize_interventions(text)
# [NormalizationResult(normalized="TLIF"), NormalizationResult(normalized="OLIF")]

# Get aliases
aliases = normalizer.get_all_aliases("UBE", "intervention")
# ["BESS", "Biportal", "Unilateral Biportal Endoscopic", ...]
```

---

## relationship_builder.py

Constructs Neo4j relationships from paper data.

### `SpineMetadata`

Spine-specific metadata extracted from papers.

```python
@dataclass
class SpineMetadata:
    sub_domain: str = ""  # Degenerative, Deformity, Trauma, Tumor
    anatomy_levels: list[str] = field(default_factory=list)  # ["L4-5", "C5-6"]
    pathologies: list[str] = field(default_factory=list)  # ["Lumbar Stenosis"]
    interventions: list[str] = field(default_factory=list)  # ["TLIF", "UBE"]
    outcomes: list[dict] = field(default_factory=list)  # [{name, value, p_value}]
```

### `ExtractedOutcome`

Structured outcome data.

```python
@dataclass
class ExtractedOutcome:
    name: str
    value: str = ""
    value_control: str = ""
    p_value: Optional[float] = None
    effect_size: str = ""
    confidence_interval: str = ""
    is_significant: bool = False
    direction: str = ""  # improved, worsened, unchanged
```

### `BuildResult`

Relationship building result.

```python
@dataclass
class BuildResult:
    paper_id: str
    nodes_created: int
    relationships_created: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

### `RelationshipBuilder`

Builds Neo4j relationships from paper data.

**Initialization**:

```python
builder = RelationshipBuilder(neo4j_client, normalizer)
```

**Main Method**:

```python
async def build_from_paper(
    self,
    paper_id: str,
    metadata: ExtractedMetadata,
    spine_metadata: SpineMetadata,
    chunks: list[ExtractedChunk]
) -> BuildResult:
    """Build complete graph from paper data.

    Process:
        1. Create Paper node
        2. Create Paper → Pathology (STUDIES) relationships
        3. Create Paper → Intervention (INVESTIGATES) relationships
        4. Create Intervention → Outcome (AFFECTS) relationships with statistics
        5. Link interventions to taxonomy
    """
```

**Component Methods**:

```python
async def create_paper_node(
    self, paper_id: str, metadata: ExtractedMetadata, spine_metadata: SpineMetadata
) -> None:
    """Create Paper node."""

async def create_studies_relations(
    self, paper_id: str, pathologies: list[str]
) -> int:
    """Create Paper → Pathology relationships."""

async def create_investigates_relations(
    self, paper_id: str, interventions: list[str]
) -> int:
    """Create Paper → Intervention relationships."""

async def create_affects_relations(
    self, intervention: str, outcomes: list[ExtractedOutcome], paper_id: str
) -> int:
    """Create Intervention → Outcome relationships with statistics."""

async def link_intervention_to_taxonomy(self, intervention_name: str) -> bool:
    """Link intervention to taxonomy hierarchy."""
```

**Example**:

```python
async with Neo4jClient() as client:
    normalizer = EntityNormalizer()
    builder = RelationshipBuilder(client, normalizer)

    # Paper metadata
    metadata = ExtractedMetadata(
        title="TLIF vs PLIF for Lumbar Stenosis",
        authors=["Smith J", "Doe A"],
        year=2024,
        evidence_level="1b"
    )

    # Spine-specific metadata
    spine_metadata = SpineMetadata(
        sub_domain="Degenerative",
        pathologies=["Lumbar Stenosis"],
        interventions=["TLIF", "PLIF"],
        outcomes=[
            {"name": "Fusion Rate", "value": "92%", "p_value": 0.01},
            {"name": "VAS", "value": "2.3", "p_value": 0.001}
        ]
    )

    # Build graph
    result = await builder.build_from_paper(
        paper_id="test_001",
        metadata=metadata,
        spine_metadata=spine_metadata,
        chunks=[]
    )

    print(f"Nodes: {result.nodes_created}, Relations: {result.relationships_created}")
    print(f"Warnings: {result.warnings}")
```

---

## taxonomy_manager.py

Manages intervention hierarchy and taxonomy operations.

### `TaxonomyManager`

Manages surgical intervention hierarchy.

**Initialization**:

```python
manager = TaxonomyManager(neo4j_client)
```

**Hierarchy Navigation**:

```python
async def get_parent_interventions(self, intervention_name: str) -> list[str]:
    """Get parent interventions (traverse IS_A upward)."""

async def get_child_interventions(self, intervention_name: str) -> list[str]:
    """Get child interventions (traverse IS_A downward)."""

async def find_common_ancestor(
    self, intervention1: str, intervention2: str
) -> Optional[str]:
    """Find closest common ancestor to determine similarity."""

async def get_intervention_level(self, intervention_name: str) -> int:
    """Get hierarchy depth (0: root, 1: first level, ...)."""
```

**Taxonomy Operations**:

```python
async def add_intervention_to_taxonomy(
    self, intervention: str, parent: str
) -> bool:
    """Add new intervention to taxonomy under parent."""

async def get_full_taxonomy_tree(self) -> dict:
    """Retrieve complete taxonomy tree structure."""

async def get_similar_interventions(
    self, intervention_name: str, max_distance: int = 2
) -> list[dict]:
    """Find similar interventions based on taxonomy distance."""
```

**Validation**:

```python
async def validate_taxonomy(self) -> dict[str, list[str]]:
    """Validate taxonomy integrity.

    Returns:
        {"orphans": [...], "cycles": [...], "warnings": [...]}
    """
```

**Example**:

```python
async with Neo4jClient() as client:
    manager = TaxonomyManager(client)

    # Get parent interventions
    parents = await manager.get_parent_interventions("TLIF")
    # ["Interbody Fusion", "Fusion Surgery"]

    # Get children
    children = await manager.get_child_interventions("Interbody Fusion")
    # ["TLIF", "PLIF", "ALIF", "OLIF", "LLIF"]

    # Find common ancestor
    ancestor = await manager.find_common_ancestor("TLIF", "PLIF")
    # "Interbody Fusion"

    # Get similar interventions
    similar = await manager.get_similar_interventions("TLIF", max_distance=2)
    # [{"name": "PLIF", "distance": 2, "common_ancestor": "Interbody Fusion"}, ...]

    # Validate taxonomy
    issues = await manager.validate_taxonomy()
    # {"orphans": [], "cycles": [], "warnings": []}
```

**Taxonomy Structure**:

```
Fusion Surgery
├── Interbody Fusion
│   ├── TLIF (Transforaminal)
│   ├── PLIF (Posterior)
│   ├── ALIF (Anterior)
│   ├── OLIF (Oblique/Lateral)
│   └── LLIF (Lateral)
└── Posterolateral Fusion

Decompression Surgery
├── Endoscopic Surgery
│   ├── UBE (Biportal Endoscopic)
│   ├── FELD (Full-Endoscopic)
│   └── PSLD (Stenoscopic)
├── Microscopic Surgery
│   └── MED (Microendoscopic)
└── Open Decompression
    └── Laminectomy

Osteotomy
├── SPO (Smith-Petersen)
├── PSO (Pedicle Subtraction)
└── VCR (Vertebral Column Resection)
```

---

## Best Practices

### 1. Use Async Context Managers

```python
async with Neo4jClient() as client:
    # Operations here
    pass
# Connection automatically closed
```

### 2. Always Normalize Entities

```python
normalizer = EntityNormalizer()
norm_result = normalizer.normalize_intervention("Biportal Endoscopic")
canonical_name = norm_result.normalized  # "UBE"
```

### 3. Batch Operations

```python
# Don't: Create relationships one by one
for intervention in interventions:
    await client.create_investigates_relation(paper_id, intervention)

# Do: Use RelationshipBuilder
result = await builder.build_from_paper(paper_id, metadata, spine_metadata, chunks)
```

### 4. Error Handling

```python
try:
    result = await client.run_query(query, parameters)
except ServiceUnavailable:
    logger.error("Neo4j service not available")
except AuthError:
    logger.error("Authentication failed")
```

### 5. Schema Initialization

```python
# Always initialize schema before first use
async with Neo4jClient() as client:
    await client.initialize_schema()  # Creates constraints, indexes, taxonomy
```

---

## Testing

### Unit Tests

Located in `/Users/sangminpark/Desktop/rag_research/tests/graph/`

```bash
# Run graph module tests
pytest tests/graph/test_spine_schema.py
pytest tests/graph/test_taxonomy_manager.py
```

### Integration Tests

```python
# Full pipeline test
async def test_full_pipeline():
    async with Neo4jClient() as client:
        await client.initialize_schema()

        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer)
        manager = TaxonomyManager(client)

        # Build graph
        result = await builder.build_from_paper(...)
        assert result.nodes_created > 0

        # Query taxonomy
        parents = await manager.get_parent_interventions("TLIF")
        assert "Interbody Fusion" in parents

        # Search
        effective = await client.search_effective_interventions("Fusion Rate")
        assert len(effective) > 0
```

---

## Related Documentation

- [TRD v3 GraphRAG](../TRD_v3_GraphRAG.md) - Technical requirements
- [Neo4j Setup Guide](../NEO4J_SETUP.md) - Installation and configuration
- [Orchestrator Module API](orchestrator_module.md) - Chain building and query generation
- [User Guide](../user_guide.md) - End-user documentation
