# Spine GraphRAG v1.22.0 - Developer Guide

## Overview

This guide provides comprehensive information for developers working on or extending the Spine GraphRAG system.

**Version**: 1.22.0
**Last Updated**: 2026-02-16

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Development Setup](#development-setup)
3. [How to Add New MCP Tools](#how-to-add-new-mcp-tools)
4. [How to Add New Interventions](#how-to-add-new-interventions)
5. [How to Extend the Schema](#how-to-extend-the-schema)
6. [Testing Guidelines](#testing-guidelines)
7. [Contributing Guidelines](#contributing-guidelines)
8. [Performance Optimization](#performance-optimization)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Streamlit UI │  │ MCP Server   │  │ CLI Tools    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   Orchestration Layer                        │
│  ┌───────────────────────────────────────────────────┐      │
│  │ SpineGraphChain (LangChain)                        │      │
│  │  - HybridRetriever (Graph + Vector)                │      │
│  │  - CypherGenerator (NL → Cypher)                   │      │
│  │  - ResponseSynthesizer (Evidence-based answers)    │      │
│  └───────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    Processing Layer                          │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Graph Module     │  │ Solver Module    │                │
│  │ - Neo4jClient    │  │ - HybridRanker   │                │
│  │ - EntityNorm     │  │ - GraphSearch    │                │
│  │ - RelBuilder     │  │ - ConflictDet    │                │
│  └──────────────────┘  └──────────────────┘                │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Builder Module   │  │ LLM Module       │                │
│  │ - PDFProcessor   │  │ - ClaudeClient   │                │
│  │ - Chunker        │  │ - Cache          │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                      Storage Layer                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Neo4j (Unified Graph + Vector)                      │    │
│  │ - Nodes: Paper, Intervention, Outcome, Pathology    │    │
│  │ - Relations: INVESTIGATES, AFFECTS, IS_A, etc.      │    │
│  │ - HNSW Vector Index (3072d OpenAI embeddings)       │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Module Dependencies

```
orchestrator/
  ├─ depends on: graph/, solver/, llm/, storage/
  ├─ provides: SpineGraphChain, CypherGenerator, ResponseSynthesizer

graph/
  ├─ depends on: (Neo4j driver)
  ├─ provides: Neo4jClient, EntityNormalizer, RelationshipBuilder, TaxonomyManager

solver/
  ├─ depends on: graph/, storage/
  ├─ provides: HybridRanker, GraphSearch, ConflictDetector

builder/
  ├─ depends on: llm/
  ├─ provides: UnifiedPDFProcessor, UnifiedProcessorV7, PubMedEnricher

llm/
  ├─ depends on: (anthropic SDK)
  ├─ provides: LLMClient (Claude Haiku 4.5), Cache

medical_mcp/handlers/
  ├─ depends on: graph/, solver/, builder/, llm/, external/
  ├─ provides: 11개 도메인 핸들러 (BaseHandler 상속)
```

### Handler 상속 구조 (v1.19.3)

MCP 서버의 도메인 로직은 `BaseHandler`를 상속하는 11개 핸들러로 분리됩니다.

```
BaseHandler (base_handler.py)
├── neo4j_client @property  → server.neo4j_client 접근
├── _require_neo4j()        → Neo4j 가용성 검증
├── _ensure_connected()     → 연결 보장
├── _format_error()         → 표준화된 에러 응답
└── _format_success()       → 표준화된 성공 응답

safe_execute (decorator)    → 모든 핸들러 메서드의 표준 에러 처리
├── ValueError → warning 로그 + {"success": false, "error": ...}
└── Exception  → exception 로그 + {"success": false, "error": ...}

BaseHandler
  ├── SearchHandler        # 하이브리드 검색, 그래프 검색, 근거 검색
  ├── DocumentHandler      # 문서 CRUD (목록, 삭제, 통계, 리셋)
  ├── PDFHandler           # PDF/텍스트 수집, 분석, 저장
  ├── JSONHandler          # JSON 파일 임포트
  ├── PubMedHandler        # PubMed 검색, 벌크 임포트, 보강
  ├── GraphHandler         # 중재법 계층, 논문 관계, 비교
  ├── ReasoningHandler     # 추론, 갈등 감지, 근거 합성
  ├── CitationHandler      # 인용 초안, 인용 제안
  ├── ClinicalDataHandler  # 환자 코호트, 추적관찰, 비용, 품질
  ├── ReferenceHandler     # 참고문헌 포맷팅 (Vancouver, AMA, APA 등)
  └── WritingGuideHandler  # 학술 논문 작성 가이드 (EQUATOR 체크리스트)
```

### Data Flow

```
1. PDF Upload
   └─> GeminiVisionProcessor (extract metadata + chunks)
       └─> EntityNormalizer (normalize terms)
           └─> RelationshipBuilder (build graph)
               └─> Neo4jClient (store nodes/relations)
               └─> TieredVectorDB (store embeddings)

2. Search Query
   └─> CypherGenerator (extract entities, generate Cypher)
       └─> HybridRanker
           ├─> GraphSearch (query Neo4j)
           └─> TieredVectorDB (vector search)
       └─> ResponseSynthesizer (combine Graph + Vector)
           └─> GeminiClient (LLM-based answer)

3. MCP Tool Call (v1.19.2 Tool Registry 패턴)
   └─> call_tool(name, arguments)
       └─> _tool_dispatchers[name] → _dispatch_*(action, args)
           └─> handler.method() (BaseHandler 상속 핸들러)
               └─> (same as Search Query flow)

   예시: "search_papers" 요청
   └─> call_tool("search", {"action": "search", "query": "TLIF outcomes"})
       └─> _tool_dispatchers["search"] → _dispatch_search("search", args)
           └─> search_handler.search(query="TLIF outcomes", ...)
```

---

## Development Setup

### Environment Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development tools

# 3. Install pre-commit hooks (recommended)
pip install pre-commit
pre-commit install

# 4. Configure environment
cp .env.example .env
# Edit .env:
# - GEMINI_API_KEY=your-key
# - NEO4J_URI=bolt://localhost:7687
# - NEO4J_PASSWORD=your-password

# 5. Start Neo4j
docker-compose up -d

# 6. Initialize database
python scripts/init_neo4j.py

# 7. (Optional) Reindex Paper-Entity relationships
python scripts/reindex_relationships.py --force
```

### IDE Configuration

**VS Code** (`settings.json`):
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "editor.formatOnSave": true
}
```

**PyCharm**:
- Interpreter: Select venv Python
- Test Runner: pytest
- Code Style: Black formatter
- Enable type checking (mypy)

### Development Tools

```bash
# Code formatting
black src/ tests/
isort src/ tests/

# Linting
flake8 src/ tests/
mypy src/

# Testing
pytest tests/
pytest tests/ --cov=src --cov-report=html

# Type checking
mypy src/ --ignore-missing-imports
```

---

## How to Add New MCP Tools

새 MCP 도구(또는 기존 도구에 새 액션)를 추가하려면 아래 단계를 따릅니다.

### 1. Handler 클래스 생성

`src/medical_mcp/handlers/` 에 새 핸들러 파일을 생성합니다.
반드시 `BaseHandler`를 상속하고, 비동기 메서드에 `@safe_execute` 데코레이터를 적용합니다.

```python
# src/medical_mcp/handlers/my_new_handler.py
from medical_mcp.handlers.base_handler import BaseHandler, safe_execute

class MyNewHandler(BaseHandler):
    """새 도메인 핸들러 설명."""

    @safe_execute
    async def my_action(self, param1: str, param2: int = 10) -> dict:
        """액션 설명.

        Args:
            param1: 파라미터 설명
            param2: 파라미터 설명 (기본값: 10)
        """
        # Neo4j 필요 시 연결 보장
        await self._ensure_connected()

        # 비즈니스 로직 구현
        result = await self.neo4j_client.run_query(
            "MATCH (n) WHERE n.name = $name RETURN n LIMIT $limit",
            {"name": param1, "limit": param2}
        )

        return self._format_success({"results": result, "count": len(result)})
```

**핵심 포인트:**
- `BaseHandler` 상속으로 `self.server`, `self.neo4j_client` 자동 접근
- `@safe_execute` 데코레이터가 예외를 표준 에러 응답으로 변환
- `_require_neo4j()` / `_ensure_connected()`로 Neo4j 가용성 검증

### 2. `handlers/__init__.py`에 등록

```python
# src/medical_mcp/handlers/__init__.py
from .my_new_handler import MyNewHandler

__all__ = [
    # ... 기존 핸들러 ...
    "MyNewHandler",
]
```

### 3. `_init_handlers()`에서 인스턴스 생성

`src/medical_mcp/medical_kag_server.py`의 `_init_handlers()` 메서드에 추가:

```python
def _init_handlers(self) -> None:
    # ... 기존 핸들러 ...
    self.my_new_handler = MyNewHandler(self)
```

### 4. 디스패처 함수 작성

`medical_kag_server.py`의 Tool Registry 영역(약 3610줄 부근)에 디스패처 추가:

```python
async def _dispatch_my_new(action: str, args: dict) -> dict:
    """My new tool dispatcher."""
    if action == "my_action":
        return await kag_server.my_new_handler.my_action(
            args.get("param1", ""), args.get("param2", 10))
    return {"success": False, "error": f"Unknown my_new action: {action}"}
```

### 5. `_tool_dispatchers` 딕셔너리에 등록

```python
_tool_dispatchers = {
    # ... 기존 디스패처 ...
    "my_new": _dispatch_my_new,
}
```

### 6. MCP Tool 스키마 정의

`create_server()` 함수 내 `@server.list_tools()` 섹션에 도구 스키마를 추가합니다:

```python
Tool(
    name="my_new",
    description="새 도구 설명",
    inputSchema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["my_action"],
                "description": "수행할 액션"
            },
            "param1": {"type": "string", "description": "파라미터 설명"},
            "param2": {"type": "integer", "description": "파라미터 설명", "default": 10},
        },
        "required": ["action"]
    }
)
```

### 7. 테스트 작성

```python
# tests/test_my_new_handler.py
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestMyNewHandler:
    @pytest.fixture
    def handler(self):
        from medical_mcp.handlers.my_new_handler import MyNewHandler
        mock_server = MagicMock()
        mock_server.neo4j_client = AsyncMock()
        return MyNewHandler(mock_server)

    @pytest.mark.asyncio
    async def test_my_action(self, handler):
        handler.server.neo4j_client.run_query = AsyncMock(return_value=[{"name": "test"}])
        result = await handler.my_action("test", 5)
        assert result["success"] is True
```

### 체크리스트

새 MCP 도구 추가 시 확인사항:

- [ ] `BaseHandler` 상속, `@safe_execute` 데코레이터 적용
- [ ] `handlers/__init__.py` exports 업데이트
- [ ] `_init_handlers()` 에 인스턴스 생성 추가
- [ ] `_dispatch_xxx()` 디스패처 함수 작성
- [ ] `_tool_dispatchers` 딕셔너리에 등록
- [ ] `@server.list_tools()` 에 Tool 스키마 추가
- [ ] 유닛 테스트 작성
- [ ] `docs/MCP_USAGE_GUIDE.md` 에 사용법 문서화

---

## How to Add New Interventions

### 1. Add to EntityNormalizer

Edit `src/graph/entity_normalizer.py`:

```python
INTERVENTION_ALIASES = {
    # ... existing interventions ...

    # Add new intervention
    "XLIF": [
        "Extreme Lateral Interbody Fusion",
        "XLIF procedure",
        "Lateral access fusion"
    ],
}
```

### 2. Add to Taxonomy

Option A: **Via Neo4j Browser** (http://localhost:7474):

```cypher
// Create intervention node
MERGE (xlif:Intervention {
    name: 'XLIF',
    full_name: 'Extreme Lateral Interbody Fusion',
    category: 'fusion',
    approach: 'lateral',
    is_minimally_invasive: true,
    aliases: ['Extreme Lateral Fusion']
})

// Link to parent
MATCH (parent:Intervention {name: 'Lateral Lumbar Interbody Fusion'})
MATCH (xlif:Intervention {name: 'XLIF'})
MERGE (xlif)-[:IS_A {level: 2}]->(parent)
```

Option B: **Via TaxonomyManager**:

```python
from src.graph.neo4j_client import Neo4jClient
from src.graph.taxonomy_manager import TaxonomyManager

async def add_xlif():
    async with Neo4jClient() as client:
        manager = TaxonomyManager(client)

        await manager.add_intervention_to_taxonomy(
            intervention="XLIF",
            parent="Lateral Lumbar Interbody Fusion"
        )

        print("✅ Added XLIF to taxonomy")

# Run
import asyncio
asyncio.run(add_xlif())
```

Option C: **Update Schema Initialization**:

Edit `src/graph/spine_schema.py`:

```python
def get_init_taxonomy_cypher(cls) -> str:
    return """
    // ... existing taxonomy ...

    // Add XLIF
    MERGE (xlif:Intervention {
        name: 'XLIF',
        full_name: 'Extreme Lateral Interbody Fusion',
        category: 'fusion',
        approach: 'lateral',
        is_minimally_invasive: true
    })
    MERGE (llif:Intervention {name: 'LLIF'})
    MERGE (xlif)-[:IS_A {level: 2}]->(llif)

    // ... rest of taxonomy ...
    """
```

### 3. Test Normalization

```python
from src.graph.entity_normalizer import EntityNormalizer

normalizer = EntityNormalizer()

# Test exact match
result = normalizer.normalize_intervention("XLIF")
assert result.normalized == "XLIF"
assert result.confidence == 1.0

# Test alias match
result = normalizer.normalize_intervention("Extreme Lateral Fusion")
assert result.normalized == "XLIF"

# Test extraction from text
text = "Comparison of XLIF and TLIF for adult spinal deformity"
interventions = normalizer.extract_and_normalize_interventions(text)
assert any(i.normalized == "XLIF" for i in interventions)

# Test anatomy normalization (v1.16.0)
result = normalizer.normalize_anatomy("L-spine")
assert result.normalized == "Lumbar"
assert result.snomed_code == "122496007"

result = normalizer.normalize_anatomy("C5-C6")
assert result.normalized == "C5-6"

result = normalizer.normalize_anatomy("요추")
assert result.normalized == "Lumbar"
```

### 4. Verify Hierarchy

```python
from src.graph.taxonomy_manager import TaxonomyManager

async def verify_xlif():
    async with Neo4jClient() as client:
        manager = TaxonomyManager(client)

        # Check parents
        parents = await manager.get_parent_interventions("XLIF")
        assert "Lateral Lumbar Interbody Fusion" in parents

        # Check similar interventions
        similar = await manager.get_similar_interventions("XLIF", max_distance=2)
        print(f"Similar to XLIF: {[s['name'] for s in similar]}")

asyncio.run(verify_xlif())
```

---

## How to Extend the Schema

### Adding a New Node Type

Example: Add `Surgeon` node type.

**1. Define Node Class** (`src/graph/spine_schema.py`):

```python
@dataclass
class SurgeonNode:
    """외과의 노드.

    Neo4j Label: Surgeon
    """
    surgeon_id: str
    name: str
    institution: str = ""
    specialties: list[str] = field(default_factory=list)
    experience_years: int = 0

    def to_neo4j_properties(self) -> dict:
        return {
            "surgeon_id": self.surgeon_id,
            "name": self.name,
            "institution": self.institution,
            "specialties": self.specialties,
            "experience_years": self.experience_years,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "SurgeonNode":
        return cls(
            surgeon_id=record.get("surgeon_id", ""),
            name=record.get("name", ""),
            institution=record.get("institution", ""),
            specialties=record.get("specialties", []),
            experience_years=record.get("experience_years", 0),
        )
```

**2. Update Schema Manager**:

```python
class SpineGraphSchema:
    NODE_LABELS = [
        "Paper", "Pathology", "Anatomy",
        "Intervention", "Outcome",
        "Surgeon"  # Add new label
    ]

    INDEXES = [
        # ... existing indexes ...
        ("Surgeon", "surgeon_id"),
        ("Surgeon", "name"),
    ]

    UNIQUE_CONSTRAINTS = [
        # ... existing constraints ...
        ("Surgeon", "surgeon_id"),
    ]
```

**3. Add Cypher Templates**:

```python
class CypherTemplates:
    # ... existing templates ...

    CREATE_SURGEON = """
    MERGE (s:Surgeon {surgeon_id: $surgeon_id})
    SET s += $properties
    RETURN s
    """

    LINK_PAPER_TO_SURGEON = """
    MATCH (p:Paper {paper_id: $paper_id})
    MERGE (s:Surgeon {surgeon_id: $surgeon_id})
    MERGE (s)-[:AUTHORED]->(p)
    RETURN s, p
    """
```

**4. Extend Neo4jClient**:

```python
# In src/graph/neo4j_client.py

async def create_surgeon(self, surgeon: SurgeonNode) -> dict:
    """외과의 노드 생성."""
    return await self.run_write_query(
        CypherTemplates.CREATE_SURGEON,
        {
            "surgeon_id": surgeon.surgeon_id,
            "properties": surgeon.to_neo4j_properties(),
        }
    )
```

**5. Update RelationshipBuilder** (if needed):

```python
async def link_paper_to_surgeons(
    self,
    paper_id: str,
    surgeon_ids: list[str]
) -> int:
    """Paper → Surgeon 관계 생성."""
    count = 0
    for surgeon_id in surgeon_ids:
        await self.client.run_write_query(
            CypherTemplates.LINK_PAPER_TO_SURGEON,
            {"paper_id": paper_id, "surgeon_id": surgeon_id}
        )
        count += 1
    return count
```

### Adding a New Relationship Type

Example: Add `PERFORMED_BY` relationship (Intervention → Surgeon).

**1. Define Relationship Class**:

```python
@dataclass
class PerformedByRelation:
    """수술 → 외과의 관계.

    (Intervention)-[:PERFORMED_BY]->(Surgeon)
    """
    intervention_name: str
    surgeon_id: str
    frequency: int = 0  # 수술 횟수
    success_rate: float = 0.0
```

**2. Add to Schema**:

```python
RELATIONSHIP_TYPES = [
    # ... existing types ...
    "PERFORMED_BY"
]
```

**3. Add Cypher Template**:

```python
CREATE_PERFORMED_BY = """
MATCH (i:Intervention {name: $intervention_name})
MERGE (s:Surgeon {surgeon_id: $surgeon_id})
MERGE (i)-[r:PERFORMED_BY]->(s)
SET r.frequency = $frequency,
    r.success_rate = $success_rate
RETURN i, r, s
"""
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── graph/
│   ├── test_spine_schema.py
│   ├── test_neo4j_client.py
│   ├── test_entity_normalizer.py
│   ├── test_relationship_builder.py
│   └── test_taxonomy_manager.py
├── orchestrator/
│   ├── test_chain_builder.py
│   ├── test_cypher_generator.py
│   └── test_response_synthesizer.py
├── solver/
│   ├── test_hybrid_ranker.py
│   └── test_graph_search.py
├── integration/
│   ├── test_full_pipeline.py
│   └── test_mcp_server.py
└── conftest.py  # Pytest fixtures
```

### Writing Unit Tests

**Example: Test EntityNormalizer**:

```python
# tests/graph/test_entity_normalizer.py
import pytest
from src.graph.entity_normalizer import EntityNormalizer

class TestEntityNormalizer:
    @pytest.fixture
    def normalizer(self):
        return EntityNormalizer()

    def test_normalize_intervention_exact_match(self, normalizer):
        result = normalizer.normalize_intervention("TLIF")
        assert result.normalized == "TLIF"
        assert result.confidence == 1.0

    def test_normalize_intervention_alias(self, normalizer):
        result = normalizer.normalize_intervention("Biportal Endoscopic")
        assert result.normalized == "UBE"
        assert result.confidence == 1.0

    def test_extract_interventions_from_text(self, normalizer):
        text = "Comparison of TLIF and OLIF for lumbar stenosis"
        interventions = normalizer.extract_and_normalize_interventions(text)

        names = [i.normalized for i in interventions]
        assert "TLIF" in names
        assert "OLIF" in names
        assert len(interventions) == 2

    def test_get_aliases(self, normalizer):
        aliases = normalizer.get_all_aliases("UBE", "intervention")
        assert "BESS" in aliases
        assert "Biportal" in aliases
```

### Writing Integration Tests

**Example: Test Full Pipeline**:

```python
# tests/integration/test_full_pipeline.py
import pytest
from src.graph.neo4j_client import Neo4jClient
from src.graph.entity_normalizer import EntityNormalizer
from src.graph.relationship_builder import RelationshipBuilder

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_graph_building():
    """Test complete graph building pipeline."""

    # Setup
    async with Neo4jClient() as client:
        await client.initialize_schema()

        normalizer = EntityNormalizer()
        builder = RelationshipBuilder(client, normalizer)

        # Test data
        from src.builder.gemini_vision_processor import ExtractedMetadata
        from src.graph.relationship_builder import SpineMetadata

        metadata = ExtractedMetadata(
            title="TLIF vs PLIF for Lumbar Stenosis",
            authors=["Smith J", "Doe A"],
            year=2024,
            evidence_level="1b"
        )

        spine_metadata = SpineMetadata(
            sub_domain="Degenerative",
            pathologies=["Lumbar Stenosis"],
            interventions=["TLIF", "PLIF"],
            outcomes=[
                {"name": "Fusion Rate", "value": "92%", "p_value": 0.01}
            ]
        )

        # Execute
        result = await builder.build_from_paper(
            paper_id="test_001",
            metadata=metadata,
            spine_metadata=spine_metadata,
            chunks=[]
        )

        # Assertions
        assert result.nodes_created == 1
        assert result.relationships_created >= 4  # 2 INVESTIGATES + 1 STUDIES + 1+ AFFECTS

        # Verify data
        paper = await client.get_paper("test_001")
        assert paper is not None

        # Verify relationships
        affects = await client.run_query("""
            MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
            WHERE a.source_paper_id = 'test_001'
            RETURN i.name, o.name, a.p_value
        """)
        assert len(affects) >= 2  # TLIF and PLIF both affect Fusion Rate
```

### Test Fixtures

**conftest.py**:

```python
import pytest
from src.graph.neo4j_client import Neo4jClient, Neo4jConfig
from src.graph.entity_normalizer import EntityNormalizer

@pytest.fixture
def neo4j_config():
    """Test Neo4j configuration."""
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="test_password",
        database="test"  # Use test database
    )

@pytest.fixture
async def neo4j_client(neo4j_config):
    """Neo4j client fixture with cleanup."""
    async with Neo4jClient(neo4j_config) as client:
        await client.initialize_schema()
        yield client

        # Cleanup: Delete all test data
        await client.run_write_query("MATCH (n) DETACH DELETE n")

@pytest.fixture
def normalizer():
    """Entity normalizer fixture."""
    return EntityNormalizer()
```

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/graph/

# Specific test
pytest tests/graph/test_entity_normalizer.py::TestEntityNormalizer::test_normalize_intervention_exact_match

# With coverage
pytest --cov=src --cov-report=html

# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m integration

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Markers

```python
# Mark slow tests
@pytest.mark.slow
async def test_large_dataset():
    pass

# Mark integration tests
@pytest.mark.integration
async def test_full_pipeline():
    pass

# Mark tests requiring Neo4j
@pytest.mark.neo4j
async def test_graph_operations():
    pass

# Skip in CI
@pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip in CI")
async def test_local_only():
    pass
```

---

## Contributing Guidelines

### Git Workflow

**1. Branch Naming**:
```
feature/add-surgeon-node
bugfix/fix-normalization-error
hotfix/critical-neo4j-connection
docs/update-api-reference
test/add-integration-tests
```

**2. Commit Messages**:
```
# Format: <type>(<scope>): <subject>

feat(graph): Add Surgeon node type to schema
fix(normalizer): Handle empty intervention names
docs(api): Update graph module documentation
test(orchestrator): Add chain builder integration tests
refactor(solver): Improve hybrid ranking algorithm
```

**3. Pull Request Process**:
```
1. Create feature branch from main
2. Implement changes with tests
3. Run linting and tests locally
4. Push and create PR
5. Address review comments
6. Merge after approval
```

### Code Style

**Python Style Guide**:
- Follow PEP 8
- Use Black formatter (line length: 100)
- Use type hints
- Write Google-style docstrings

**Example**:
```python
async def create_paper_node(
    self,
    paper_id: str,
    metadata: ExtractedMetadata,
    spine_metadata: SpineMetadata
) -> None:
    """Create Paper node in Neo4j.

    Args:
        paper_id: Unique paper identifier
        metadata: Extracted metadata from PDF
        spine_metadata: Spine-specific metadata

    Raises:
        ValueError: If paper_id is empty
        Neo4jError: If database operation fails

    Example:
        >>> await builder.create_paper_node(
        ...     paper_id="PMID_12345",
        ...     metadata=metadata,
        ...     spine_metadata=spine_metadata
        ... )
    """
    if not paper_id:
        raise ValueError("paper_id cannot be empty")

    paper = PaperNode(
        paper_id=paper_id,
        title=metadata.title,
        # ... rest of implementation
    )

    await self.client.create_paper(paper)
```

### Documentation

**Required Documentation**:
- Module docstrings (top of file)
- Class docstrings
- Method docstrings (Args, Returns, Raises, Example)
- README for new modules
- API documentation updates
- CHANGELOG updates for features/breaking changes

### Review Checklist

Before submitting PR:
- [ ] All tests pass (`pytest`)
- [ ] Linting passes (`flake8`, `mypy`)
- [ ] Code formatted (`black`, `isort`)
- [ ] Documentation updated
- [ ] Type hints added
- [ ] Example usage provided
- [ ] CHANGELOG updated (if needed)
- [ ] No secrets/credentials in code

---

## Performance Optimization

### Neo4j Query Optimization

**1. Use Indexes**:
```cypher
// Check existing indexes
CALL db.indexes()

// Create missing indexes
CREATE INDEX intervention_name_idx IF NOT EXISTS
FOR (i:Intervention) ON (i.name)
```

**2. Use Query Profiling**:
```cypher
// Analyze query performance
PROFILE
MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
WHERE a.is_significant = true
RETURN i, o

// Check execution plan
EXPLAIN
MATCH (i:Intervention {name: 'TLIF'})-[a:AFFECTS]->()
RETURN count(a)
```

**3. Optimize Complex Queries**:
```cypher
// Bad: Multiple MATCH clauses
MATCH (p:Paper {paper_id: $id})
MATCH (i:Intervention)
MATCH (p)-[:INVESTIGATES]->(i)
RETURN i

// Good: Single MATCH with pattern
MATCH (p:Paper {paper_id: $id})-[:INVESTIGATES]->(i:Intervention)
RETURN i
```

### ChromaDB Optimization

**1. Batch Operations**:
```python
# Bad: Individual adds
for chunk in chunks:
    vector_db.add_chunk(chunk)

# Good: Batch add
vector_db.add_chunks_batch(chunks, batch_size=100)
```

**2. Query Optimization**:
```python
# Use tier1 search for faster results
results = vector_db.search_tier1(query, top_k=5)

# Or hybrid search with lower top_k
results = vector_db.search_hybrid(query, top_k=10)
```

### LLM Call Optimization

**1. Use Caching**:
```python
from src.llm.cache import GeminiCache

cache = GeminiCache(cache_dir="./cache")

# Cache expensive calls
@cache.cached_response
async def extract_metadata(pdf_path: str):
    return await vision_processor.process_pdf(pdf_path)
```

**2. Batch Requests**:
```python
# Process multiple PDFs concurrently
import asyncio

async def process_batch(pdf_paths: list[str]):
    tasks = [vision_processor.process_pdf(path) for path in pdf_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### Memory Optimization

**1. Stream Large Results**:
```python
# Bad: Load all results into memory
all_papers = await client.run_query("MATCH (p:Paper) RETURN p")

# Good: Paginate
async def get_papers_paginated(limit=100):
    offset = 0
    while True:
        papers = await client.run_query(
            "MATCH (p:Paper) RETURN p SKIP $offset LIMIT $limit",
            {"offset": offset, "limit": limit}
        )
        if not papers:
            break

        yield papers
        offset += limit
```

**2. Clean Up Resources**:
```python
# Use context managers
async with Neo4jClient() as client:
    # Operations here
    pass
# Connection automatically closed

# Close sessions explicitly
async with client.session() as session:
    # Queries here
    pass
```

---

## Debugging

### Enable Debug Logging

```python
import logging

# Set log level
logging.basicConfig(level=logging.DEBUG)

# Module-specific logging
logging.getLogger("src.graph").setLevel(logging.DEBUG)
logging.getLogger("src.orchestrator").setLevel(logging.INFO)
```

### Neo4j Browser Debugging

Access Neo4j Browser at http://localhost:7474

```cypher
// Check graph structure
CALL db.schema.visualization()

// Count nodes and relationships
MATCH (n) RETURN labels(n), count(n)
MATCH ()-[r]->() RETURN type(r), count(r)

// Find orphan nodes
MATCH (n)
WHERE NOT (n)--()
RETURN n

// Check specific paper
MATCH (p:Paper {paper_id: 'test_001'})
MATCH path = (p)-[*1..2]-()
RETURN path

// Check Paper-Entity relationships
MATCH (p:Paper)-[r]->(e)
WHERE type(r) IN ['STUDIES', 'INVESTIGATES', 'INVOLVES']
RETURN type(r), count(r)
```

### Reindexing Relationships

Paper-Entity 관계가 부족하거나 검색 결과가 없을 때 재색인 스크립트를 사용합니다:

```bash
# Dry-run (변경 없이 확인만)
python scripts/reindex_relationships.py --dry-run

# 전체 재색인 (기존 관계 있는 paper 건너뜀)
python scripts/reindex_relationships.py

# 강제 재구축 (모든 paper)
python scripts/reindex_relationships.py --force

# 특정 paper만 재색인
python scripts/reindex_relationships.py --paper-id pubmed_12345678

# 제한된 수만 처리
python scripts/reindex_relationships.py --limit 100 --verbose
```

**생성되는 관계**:

- `STUDIES` (Paper → Pathology)
- `INVESTIGATES` (Paper → Intervention)
- `INVOLVES` (Paper → Anatomy)
- `AFFECTS` (Intervention → Outcome)

### Profiling

```python
import cProfile
import pstats

async def main():
    # Your code here
    pass

# Profile execution
profiler = cProfile.Profile()
profiler.enable()

import asyncio
asyncio.run(main())

profiler.disable()

# Print stats
stats = pstats.Stats(profiler)
stats.sort_stats('cumtime')
stats.print_stats(20)  # Top 20 functions
```

---

## Resources

- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/)
- [LangChain Documentation](https://python.langchain.com/)
- [Gemini API Reference](https://ai.google.dev/api)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [pytest Documentation](https://docs.pytest.org/)

---

## Next Steps

1. Review [API Documentation](api/graph_module.md)
2. Set up development environment
3. Run existing tests
4. Pick an issue from GitHub
5. Submit your first PR!

Happy coding!
