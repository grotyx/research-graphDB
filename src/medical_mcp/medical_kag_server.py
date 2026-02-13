"""Medical KAG MCP Server.

의학 논문 RAG 시스템을 위한 MCP 서버.
Tiered indexing, evidence level, citation detection 기능 통합.
LLM 기반 처리 및 논문 관계 그래프 지원.
"""

# CRITICAL: Load .env FIRST before any imports that might check environment variables
import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[medical_kag_server] .env loaded from: {env_path}", file=sys.stderr)
        print(f"[medical_kag_server] GEMINI_API_KEY present: {bool(os.environ.get('GEMINI_API_KEY'))}", file=sys.stderr)
        print(f"[medical_kag_server] NEO4J_PASSWORD present: {bool(os.environ.get('NEO4J_PASSWORD'))}", file=sys.stderr)
    else:
        print(f"[medical_kag_server] .env not found at: {env_path}", file=sys.stderr)
except ImportError:
    print("[medical_kag_server] python-dotenv not installed, skipping .env loading", file=sys.stderr)

import asyncio
import logging
from datetime import datetime
from typing import Optional, Any

# Add project root and src directory to path for proper relative imports
project_root = Path(__file__).parent.parent.parent
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))  # For 'from src.module' imports
sys.path.insert(0, str(src_dir))       # For 'from module' imports

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Medical KAG modules
from solver.query_parser import QueryParser, QueryInput
from solver.tiered_search import TieredHybridSearch, SearchInput, SearchTier
from solver.multi_factor_ranker import MultiFactorRanker, RankInput
from solver.reasoner import Reasoner, ReasonerInput
from solver.response_generator import ResponseGenerator, GeneratorInput, ResponseFormat
from solver.conflict_detector import ConflictDetector, ConflictInput

# v7.14.12: ChromaDB 완전 제거 - Neo4j Vector Index만 사용
# TextChunk는 하위 호환성을 위해 storage/__init__.py에서 유지
from storage import TextChunk, SearchFilters

# Builder modules (if available)
try:
    from builder.section_classifier import SectionClassifier
    from builder.citation_detector import CitationDetector
    from builder.study_classifier import StudyClassifier
    from builder.pico_extractor import PICOExtractor
    from builder.stats_parser import StatsParser
    from core.text_chunker import TieredTextChunker
    BUILDER_AVAILABLE = True
except ImportError:
    BUILDER_AVAILABLE = False
    TieredTextChunker = None

# LLM modules (if available)
try:
    from llm import LLMClient, LLMConfig, ClaudeClient, GeminiClient
    from builder.llm_section_classifier import LLMSectionClassifier
    from builder.llm_semantic_chunker import LLMSemanticChunker
    from builder.llm_metadata_extractor import LLMMetadataExtractor
    LLM_AVAILABLE = True
    print(f"[medical_kag_server] LLM modules imported successfully", file=sys.stderr)
except ImportError as e:
    LLM_AVAILABLE = False
    print(f"[medical_kag_server] LLM import failed: {e}", file=sys.stderr)

# Unified PDF Processor v2.0 (Claude/Gemini - configurable via .env)
# All dataclasses are now in unified_pdf_processor (gemini_vision_processor is deprecated)
try:
    from builder.unified_pdf_processor import (
        UnifiedPDFProcessor,
        ProcessorResult,
        VisionProcessorResult,
        LLMProvider,
        ChunkMode,
        # Dataclasses
        ExtractedMetadata,
        SpineMetadata,
        ExtractedChunk,
        ExtractedOutcome,
        ComplicationData,
        ImportantCitation,
    )
    VISION_AVAILABLE = True
    # Backward compatibility alias
    GeminiVisionProcessor = UnifiedPDFProcessor
    LEGACY_VISION_AVAILABLE = True  # unified_pdf_processor handles both
    print(f"[medical_kag_server] Unified PDF processor v2.0 imported successfully", file=sys.stderr)
except ImportError as e:
    VISION_AVAILABLE = False
    LEGACY_VISION_AVAILABLE = False
    UnifiedPDFProcessor = None
    ProcessorResult = None
    VisionProcessorResult = None
    GeminiVisionProcessor = None
    print(f"[medical_kag_server] Unified PDF processor import failed: {e}", file=sys.stderr)

# v7.0 Simplified Processing Pipeline - REMOVED (archived to src/archive/legacy_v7/)
# unified_pdf_processor.py가 기본 파이프라인으로 사용됨
V7_AVAILABLE = False

# Knowledge Graph modules (Legacy - SQLite-based, deprecated)
# NOTE: Removed SQLite-based PaperGraph in favor of Neo4j integration
# SQLite modules (citation_extractor, relationship_reasoner) are no longer used
KNOWLEDGE_AVAILABLE = False  # Legacy SQLite modules disabled

# Ontology modules (SNOMED-CT integration)
try:
    from ontology import SNOMEDLinker, ConceptHierarchy
    ONTOLOGY_AVAILABLE = True
except ImportError:
    ONTOLOGY_AVAILABLE = False
    SNOMEDLinker = None
    ConceptHierarchy = None

# PubMed integration
try:
    from external.pubmed_client import PubMedClient, PaperMetadata
    PUBMED_AVAILABLE = True
except ImportError:
    PUBMED_AVAILABLE = False
    PubMedClient = None

# PubMed Enricher (bibliographic metadata)
try:
    from builder.pubmed_enricher import PubMedEnricher, BibliographicMetadata
    PUBMED_ENRICHER_AVAILABLE = True
    print(f"[medical_kag_server] PubMed Enricher imported successfully", file=sys.stderr)
except ImportError as e:
    PUBMED_ENRICHER_AVAILABLE = False
    PubMedEnricher = None
    BibliographicMetadata = None
    print(f"[medical_kag_server] PubMed Enricher import failed: {e}", file=sys.stderr)

# Important Citation Processor (v3.2+)
try:
    from builder.important_citation_processor import ImportantCitationProcessor, CitationProcessingResult
    CITATION_PROCESSOR_AVAILABLE = True
    print(f"[medical_kag_server] Important Citation Processor imported successfully", file=sys.stderr)
except ImportError as e:
    CITATION_PROCESSOR_AVAILABLE = False
    ImportantCitationProcessor = None
    CitationProcessingResult = None
    print(f"[medical_kag_server] Important Citation Processor import failed: {e}", file=sys.stderr)

# PubMed Bulk Processor (v4.3+)
try:
    from builder.pubmed_bulk_processor import (
        PubMedBulkProcessor,
        PubMedImportResult,
        BulkImportSummary,
    )
    PUBMED_BULK_AVAILABLE = True
    print(f"[medical_kag_server] PubMed Bulk Processor imported successfully", file=sys.stderr)
except ImportError as e:
    PUBMED_BULK_AVAILABLE = False
    PubMedBulkProcessor = None
    PubMedImportResult = None
    BulkImportSummary = None
    print(f"[medical_kag_server] PubMed Bulk Processor import failed: {e}", file=sys.stderr)

# DOI Fulltext Fetcher (v7.13+)
try:
    from builder.doi_fulltext_fetcher import (
        DOIFulltextFetcher,
        DOIFullText,
        DOIMetadata,
        fetch_by_doi,
        get_doi_metadata,
    )
    DOI_FETCHER_AVAILABLE = True
    print(f"[medical_kag_server] DOI Fulltext Fetcher imported successfully", file=sys.stderr)
except ImportError as e:
    DOI_FETCHER_AVAILABLE = False
    DOIFulltextFetcher = None
    DOIFullText = None
    DOIMetadata = None
    fetch_by_doi = None
    get_doi_metadata = None
    print(f"[medical_kag_server] DOI Fulltext Fetcher import failed: {e}", file=sys.stderr)

# Neo4j Graph modules (Spine GraphRAG v3)
try:
    from graph.neo4j_client import Neo4jClient, Neo4jConfig
    from graph.relationship_builder import RelationshipBuilder, SpineMetadata as GraphSpineMetadata
    from graph.entity_normalizer import EntityNormalizer
    from graph.spine_schema import ChunkNode  # v5.3: Neo4j Vector Index
    from solver.graph_search import GraphSearch
    from orchestrator.cypher_generator import CypherGenerator
    from graph.taxonomy_manager import TaxonomyManager
    GRAPH_AVAILABLE = True
    print(f"[medical_kag_server] Neo4j Graph modules imported successfully", file=sys.stderr)
except ImportError as e:
    GRAPH_AVAILABLE = False
    Neo4jClient = None
    Neo4jConfig = None
    RelationshipBuilder = None
    EntityNormalizer = None
    GraphSpineMetadata = None
    GraphSearch = None
    CypherGenerator = None
    ChunkNode = None  # v5.3
    TaxonomyManager = None
    print(f"[medical_kag_server] Neo4j Graph import failed: {e}", file=sys.stderr)

# Handler modules (v7.7)
try:
    from medical_mcp.handlers import (
        DocumentHandler, ClinicalDataHandler, PubMedHandler, JSONHandler,
        CitationHandler, SearchHandler, PDFHandler, ReasoningHandler, GraphHandler,
        WritingGuideHandler
    )
    HANDLERS_AVAILABLE = True
    print(f"[medical_kag_server] Handler modules imported successfully (v7.13)", file=sys.stderr)
except ImportError as e:
    HANDLERS_AVAILABLE = False
    DocumentHandler = None
    ClinicalDataHandler = None
    PubMedHandler = None
    JSONHandler = None
    CitationHandler = None
    SearchHandler = None
    PDFHandler = None
    ReasoningHandler = None
    GraphHandler = None
    WritingGuideHandler = None
    print(f"[medical_kag_server] Handler modules import failed: {e}", file=sys.stderr)

# Configure logging with file handler
from logging.handlers import RotatingFileHandler

_log_dir = Path(__file__).parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "medical_kag.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        RotatingFileHandler(
            _log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger("medical-kag")
logger.info(f"Log file: {_log_file}")


class MedicalKAGServer:
    """Medical KAG Server.

    MCP 도구들을 제공하는 서버 클래스.

    v7.5 멀티유저 지원:
    - current_user: 현재 사용자 ID (None이면 'system')
    - set_user(): 사용자 컨텍스트 설정
    - 검색/저장 시 사용자 필터링 적용
    """

    def __init__(
        self,
        data_dir: Optional[str | Path] = None,
        enable_llm: bool = True,
        use_neo4j_storage: bool = True,  # v5.3 Phase 4: Neo4j 전용 모드
        default_user: Optional[str] = None  # v7.5: 기본 사용자 ID
    ):
        """초기화.

        Args:
            data_dir: 데이터 저장 경로
            enable_llm: LLM 기능 활성화 여부
            use_neo4j_storage: True면 Neo4j Vector Index 사용 (v5.3: 항상 True, ChromaDB 제거됨)
            default_user: 기본 사용자 ID (None이면 'system')
        """
        self.data_dir = Path(data_dir) if data_dir else src_dir.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.enable_llm = enable_llm and LLM_AVAILABLE
        self.use_neo4j_storage = use_neo4j_storage  # v5.3 Phase 4

        # v7.5: 멀티유저 지원
        self.current_user: str = default_user or "system"

        # Initialize components
        self._init_components()

        # Initialize handlers (v7.7)
        self._init_handlers()

        logger.info(f"Medical KAG Server initialized. Data dir: {self.data_dir}")
        logger.info(f"LLM enabled: {self.enable_llm}, Knowledge Graph: {KNOWLEDGE_AVAILABLE}")
        logger.info(f"Neo4j Storage Mode: {self.use_neo4j_storage}")
        logger.info(f"Current user: {self.current_user}")

    def set_user(self, user_id: str) -> None:
        """현재 사용자 설정 (v7.5).

        Args:
            user_id: 사용자 ID
        """
        self.current_user = user_id or "system"
        logger.info(f"User context set to: {self.current_user}")

    def _get_user_filter_clause(self, alias: str = "p") -> str:
        """사용자 필터링 Cypher WHERE 절 생성 (v7.5).

        본인 소유 문서 + 공유 문서만 조회.

        Args:
            alias: Paper 노드 별칭 (기본: 'p')

        Returns:
            Cypher WHERE 절 문자열 (예: "WHERE p.owner = 'kim' OR p.shared = true")
        """
        if self.current_user == "system":
            return ""  # system 사용자는 모든 문서 접근 가능
        return f"WHERE {alias}.owner = '{self.current_user}' OR {alias}.shared = true"

    def _init_components(self):
        """컴포넌트 초기화."""
        # v5.3 Phase 4: ChromaDB 제거 - Neo4j Vector Index만 사용
        # self.vector_db는 더 이상 사용하지 않음 - 하위 호환성을 위해 None으로 유지
        self.vector_db = None

        # Solver modules (search_engine 초기화는 Neo4j 초기화 후로 이동 - v5.3 Phase 4)
        self.query_parser = QueryParser()
        self.search_engine = None  # Neo4j 초기화 후 설정
        self.ranker = MultiFactorRanker()
        self.reasoner = Reasoner()
        self.response_generator = ResponseGenerator()
        self.conflict_detector = ConflictDetector()

        # Builder modules (if available)
        if BUILDER_AVAILABLE:
            self.section_classifier = SectionClassifier()
            self.citation_detector = CitationDetector()
            self.study_classifier = StudyClassifier()
            self.pico_extractor = PICOExtractor()
            self.stats_parser = StatsParser()
        else:
            logger.warning("Builder modules not available")

        # LLM modules (if enabled and available)
        self.llm_client = None
        self.gemini_client = None  # 하위 호환성 alias
        self.llm_section_classifier = None
        self.llm_chunker = None
        self.llm_extractor = None
        self.vision_processor = None  # Unified PDF Processor (Claude/Gemini)
        # v7_processor removed (archived)

        if self.enable_llm and LLM_AVAILABLE:
            # LLMClient는 LLM_PROVIDER 환경변수에 따라 Claude 또는 Gemini 사용
            # ANTHROPIC_API_KEY 또는 GEMINI_API_KEY가 있어야 함
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            gemini_key = os.environ.get("GEMINI_API_KEY")
            llm_provider = os.environ.get("LLM_PROVIDER", "claude").lower()

            api_key = anthropic_key if llm_provider == "claude" else gemini_key
            logger.info(f"LLM Provider: {llm_provider}, API key present={bool(api_key)}")

            if api_key:
                try:
                    config = LLMConfig()  # 기본 설정 사용 (환경변수에서 API 키 자동 로드)
                    self.llm_client = LLMClient(config)
                    self.gemini_client = self.llm_client  # 하위 호환성 alias

                    # Initialize with fallback modules for resilience
                    fallback_classifier = SectionClassifier() if BUILDER_AVAILABLE else None
                    fallback_chunker = TieredTextChunker() if TieredTextChunker else None

                    self.llm_section_classifier = LLMSectionClassifier(
                        self.gemini_client,
                        fallback_classifier=fallback_classifier
                    )
                    self.llm_chunker = LLMSemanticChunker(
                        self.gemini_client,
                        fallback_chunker=fallback_chunker
                    )
                    self.llm_extractor = LLMMetadataExtractor(self.gemini_client)
                    logger.info("LLM modules initialized with fallback support")

                    # Initialize Unified PDF Processor (primary pipeline)
                    # Uses LLM_PROVIDER from .env: "claude" (default) or "gemini"
                    if VISION_AVAILABLE and UnifiedPDFProcessor is not None:
                        try:
                            self.vision_processor = UnifiedPDFProcessor()
                            logger.info(
                                f"Unified PDF processor initialized: "
                                f"provider={self.vision_processor.provider_name}, "
                                f"model={self.vision_processor.model_name}"
                            )
                        except Exception as e:
                            logger.warning(f"Unified PDF processor initialization failed: {e}")
                            # Fallback to legacy Gemini processor
                            if LEGACY_VISION_AVAILABLE and GeminiVisionProcessor is not None:
                                try:
                                    self.vision_processor = GeminiVisionProcessor(
                                        api_key=api_key,
                                        timeout=300.0,
                                        max_retries=2
                                    )
                                    logger.info("Fallback: Legacy Gemini Vision processor initialized")
                                except Exception as e2:
                                    logger.warning(f"Fallback Vision processor also failed: {e2}")

                    # v7.0 Processor removed (archived)
                except Exception as e:
                    logger.warning(f"LLM initialization failed: {e}")
            else:
                logger.warning("GEMINI_API_KEY not set, LLM features disabled")

        # Knowledge Graph modules (Legacy - SQLite, deprecated)
        # NOTE: Removed SQLite-based paper_graph in favor of Neo4j
        # All paper relations are now handled by self.neo4j_client

        # PubMed client (if available)
        self.pubmed_client = None
        if PUBMED_AVAILABLE:
            try:
                email = os.environ.get("PUBMED_EMAIL", "")
                api_key = os.environ.get("PUBMED_API_KEY", "")
                self.pubmed_client = PubMedClient(email=email, api_key=api_key if api_key else None)
                logger.info("PubMed client initialized")
            except Exception as e:
                logger.warning(f"PubMed client initialization failed: {e}")

        # PubMed Enricher (bibliographic metadata enhancement)
        self.pubmed_enricher = None
        if PUBMED_ENRICHER_AVAILABLE:
            try:
                email = os.environ.get("NCBI_EMAIL") or os.environ.get("PUBMED_EMAIL", "")
                api_key = os.environ.get("NCBI_API_KEY") or os.environ.get("PUBMED_API_KEY", "")
                self.pubmed_enricher = PubMedEnricher(email=email, api_key=api_key if api_key else None)
                logger.info(f"PubMed Enricher initialized (email={'set' if email else 'not set'}, api_key={'set' if api_key else 'not set'})")
            except Exception as e:
                logger.warning(f"PubMed Enricher initialization failed: {e}")

        # Ontology modules (SNOMED-CT integration)
        self.concept_hierarchy = None
        self.snomed_linker = None

        if ONTOLOGY_AVAILABLE:
            try:
                # ConceptHierarchy works without external dependencies
                self.concept_hierarchy = ConceptHierarchy()
                logger.info("ConceptHierarchy initialized for query expansion")

                # SNOMEDLinker requires scispaCy (optional)
                try:
                    self.snomed_linker = SNOMEDLinker()
                    logger.info("SNOMEDLinker initialized with scispaCy")
                except Exception as e:
                    logger.info(f"SNOMEDLinker not available (scispaCy not installed): {e}")
            except Exception as e:
                logger.warning(f"Ontology modules initialization failed: {e}")

        # Neo4j Graph modules (Spine GraphRAG v3)
        self.neo4j_client = None
        self.graph_searcher = None
        self.cypher_generator = None
        self.taxonomy_manager = None
        self.entity_normalizer = None
        self.relationship_builder = None

        if GRAPH_AVAILABLE:
            try:
                # Neo4j connection using Neo4jConfig (loads from .env)
                neo4j_password = os.environ.get("NEO4J_PASSWORD")
                if not neo4j_password:
                    logger.warning("NEO4J_PASSWORD not set in .env file!")

                neo4j_config = Neo4jConfig(
                    uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                    username=os.environ.get("NEO4J_USERNAME", "neo4j"),
                    password=neo4j_password or "",
                    database=os.environ.get("NEO4J_DATABASE", "neo4j"),
                )

                self.neo4j_client = Neo4jClient(config=neo4j_config)
                self.graph_searcher = GraphSearch(neo4j_client=self.neo4j_client)
                self.cypher_generator = CypherGenerator()
                self.taxonomy_manager = TaxonomyManager(neo4j_client=self.neo4j_client)

                # Entity normalization and relationship building
                self.entity_normalizer = EntityNormalizer()
                self.relationship_builder = RelationshipBuilder(
                    neo4j_client=self.neo4j_client,
                    normalizer=self.entity_normalizer
                )

                logger.info("Neo4j Graph modules initialized (Spine GraphRAG v3)")
            except Exception as e:
                logger.warning(f"Neo4j Graph initialization failed: {e}")

        # v7.14.17: TieredHybridSearch 초기화 (Neo4j Hybrid Search 통합)
        if self.neo4j_client:
            # Neo4j 전용 모드: Neo4j Vector Index + Graph 필터 통합
            self.search_engine = TieredHybridSearch(
                vector_db=None,  # ChromaDB 제거됨
                neo4j_client=self.neo4j_client,
                use_neo4j_vector=True,
                config={
                    "use_neo4j_hybrid": True,  # v7.14.17: 그래프+벡터 통합 검색
                    "vector_weight": 0.4,
                    "graph_weight": 0.6,
                }
            )
            logger.info("TieredHybridSearch initialized with Neo4j Hybrid Search (v7.14.17)")
        else:
            # Neo4j 없으면 검색 불가
            self.search_engine = None
            logger.warning("TieredHybridSearch not initialized - Neo4j required")

        # Important Citation Processor (v3.2+) - Claude/Gemini 듀얼 프로바이더 지원
        self.citation_processor = None
        if CITATION_PROCESSOR_AVAILABLE and self.neo4j_client:
            try:
                llm_provider = os.environ.get("LLM_PROVIDER", "claude").lower()
                pubmed_email = os.environ.get("NCBI_EMAIL") or os.environ.get("PUBMED_EMAIL", "")
                pubmed_api_key = os.environ.get("NCBI_API_KEY") or os.environ.get("PUBMED_API_KEY", "")

                # API 키 확인 (claude 또는 gemini)
                api_key_available = False
                if llm_provider == "claude":
                    api_key_available = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
                else:
                    api_key_available = bool(os.environ.get("GEMINI_API_KEY", ""))

                if api_key_available:
                    self.citation_processor = ImportantCitationProcessor(
                        provider=llm_provider,
                        pubmed_email=pubmed_email,
                        pubmed_api_key=pubmed_api_key if pubmed_api_key else None,
                        neo4j_client=self.neo4j_client,
                        relationship_builder=self.relationship_builder,  # v7.6: 인용 논문 관계 구축용
                        min_confidence=0.7,
                        max_citations=15,
                        analyze_cited_abstracts=True  # v7.6: 인용 논문 abstract LLM 분석
                    )
                    logger.info(f"Important Citation Processor initialized (v7.6) with {llm_provider} + LLM analysis")
                else:
                    logger.warning(
                        f"Citation Processor requires {'ANTHROPIC_API_KEY' if llm_provider == 'claude' else 'GEMINI_API_KEY'}"
                    )
            except Exception as e:
                logger.warning(f"Important Citation Processor initialization failed: {e}")

    def _convert_to_graph_spine_metadata(self, spine_meta) -> "GraphSpineMetadata":
        """Convert spine metadata to GraphSpineMetadata (v7.14.9).

        Handles field name differences between unified_pdf_processor and relationship_builder:
        - pathology (list) -> pathologies
        - anatomy_level (str) + anatomy_region (str) -> anatomy_levels (list)
        - ExtractedOutcome objects -> dict

        Args:
            spine_meta: SpineMetadata from unified_pdf_processor or dict

        Returns:
            GraphSpineMetadata for relationship_builder
        """
        if spine_meta is None:
            return GraphSpineMetadata()

        # pathology -> pathologies 매핑
        pathologies = getattr(spine_meta, 'pathologies', None) or getattr(spine_meta, 'pathology', [])
        if isinstance(pathologies, str):
            pathologies = [pathologies] if pathologies else []

        # anatomy_level + anatomy_region -> anatomy_levels 매핑
        anatomy_levels = getattr(spine_meta, 'anatomy_levels', None)
        if not anatomy_levels:
            anatomy_level = getattr(spine_meta, 'anatomy_level', '')
            anatomy_region = getattr(spine_meta, 'anatomy_region', '')
            anatomy_levels = []
            if anatomy_level:
                anatomy_levels.append(anatomy_level)
            if anatomy_region and anatomy_region != anatomy_level:
                anatomy_levels.append(anatomy_region)

        # outcomes 변환 (ExtractedOutcome 객체 -> dict)
        outcomes_data = getattr(spine_meta, 'outcomes', [])
        outcomes_dicts = []
        for o in outcomes_data:
            if hasattr(o, '__dict__') and hasattr(o, 'name'):
                # ExtractedOutcome 객체인 경우 dict로 변환
                o_dict = {
                    'name': getattr(o, 'name', ''),
                    'value': getattr(o, 'value', ''),
                    'value_intervention': getattr(o, 'value_intervention', ''),
                    'value_control': getattr(o, 'value_control', ''),
                    'value_difference': getattr(o, 'value_difference', ''),
                    'p_value': getattr(o, 'p_value', ''),
                    'effect_size': getattr(o, 'effect_size', ''),
                    'confidence_interval': getattr(o, 'confidence_interval', ''),
                    'is_significant': getattr(o, 'is_significant', False),
                    'direction': getattr(o, 'direction', ''),
                    'category': getattr(o, 'category', ''),
                    'timepoint': getattr(o, 'timepoint', ''),
                }
                outcomes_dicts.append(o_dict)
            elif isinstance(o, dict):
                outcomes_dicts.append(o)

        # v7.2 Extended entities
        patient_cohorts = getattr(spine_meta, 'patient_cohorts', [])
        followups = getattr(spine_meta, 'followups', [])
        costs = getattr(spine_meta, 'costs', [])
        quality_metrics = getattr(spine_meta, 'quality_metrics', [])

        return GraphSpineMetadata(
            sub_domain=getattr(spine_meta, 'sub_domain', 'Unknown'),
            sub_domains=getattr(spine_meta, 'sub_domains', []),
            anatomy_levels=anatomy_levels,
            interventions=getattr(spine_meta, 'interventions', []),
            pathologies=pathologies,
            outcomes=outcomes_dicts,
            surgical_approach=getattr(spine_meta, 'surgical_approach', []),
            main_conclusion=getattr(spine_meta, 'main_conclusion', ''),
            patient_cohorts=patient_cohorts,
            followups=followups,
            costs=costs,
            quality_metrics=quality_metrics,
        )

    def _init_handlers(self):
        """Initialize domain-specific handlers (v7.7)."""
        if not HANDLERS_AVAILABLE:
            logger.warning("Handler modules not available - handlers not initialized")
            return

        try:
            self.document_handler = DocumentHandler(self)
            self.clinical_data_handler = ClinicalDataHandler(self)
            self.pubmed_handler = PubMedHandler(self)
            self.json_handler = JSONHandler(self)
            self.citation_handler = CitationHandler(self)
            self.search_handler = SearchHandler(self)
            self.pdf_handler = PDFHandler(self)
            self.reasoning_handler = ReasoningHandler(self)
            self.graph_handler = GraphHandler(self)

            # v7.8: Reference formatting handler
            from medical_mcp.handlers.reference_handler import ReferenceHandler
            self.reference_handler = ReferenceHandler(self)

            # v7.13: Writing guide handler
            from medical_mcp.handlers.writing_guide_handler import WritingGuideHandler
            self.writing_guide_handler = WritingGuideHandler(self)

            logger.info("[medical_kag_server] Handlers initialized (v7.13 - with WritingGuideHandler)")
        except Exception as e:
            logger.warning(f"Handler initialization failed: {e}")
            # Initialize as None if failed
            self.document_handler = None
            self.clinical_data_handler = None
            self.pubmed_handler = None
            self.json_handler = None
            self.citation_handler = None
            self.search_handler = None
            self.pdf_handler = None
            self.reasoning_handler = None
            self.graph_handler = None
            self.reference_handler = None
            self.writing_guide_handler = None

    # ========== MCP Tools ==========

    async def add_pdf(
        self,
        file_path: str,
        metadata: Optional[dict] = None,
        use_vision: bool = True,
        use_v7: bool = True
    ) -> dict:
        """PDF 논문 추가.

        v7.5 업데이트: v7.0 Simplified Pipeline을 기본으로 사용합니다.
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹
        - 조건부 엔티티 추출 (의학 콘텐츠만)
        - Important Citation 자동 처리

        Args:
            file_path: PDF 파일 경로
            metadata: 추가 메타데이터
            use_vision: 통합 PDF 프로세서 사용 여부 (레거시, True: 권장)
            use_v7: v7.0 프로세서 사용 여부 (기본값: True, 권장)

        Returns:
            처리 결과 딕셔너리
        """
        path = Path(file_path)

        if not path.exists():
            return {"success": False, "error": f"파일 없음: {file_path}"}

        if not path.suffix.lower() == ".pdf":
            return {"success": False, "error": "PDF 파일이 아닙니다"}

        try:
            # Unified PDF Processor (primary)
            if use_vision and self.vision_processor is not None:
                logger.info("Using Unified PDF processor")
                return await self._process_with_vision(path, metadata)

            # Fallback: 기존 멀티스텝 파이프라인
            logger.info("Using multi-step pipeline")
            return await self._process_with_legacy_pipeline(path, metadata)

        except Exception as e:
            logger.exception(f"Error adding PDF: {e}")
            return {"success": False, "error": str(e)}

    async def add_pdf_v7(
        self,
        file_path: str,
        metadata: Optional[dict] = None,
        document_type: Optional[str] = None
    ) -> dict:
        """PDF 논문 추가 - add_pdf()로 리다이렉트 (v7 파이프라인 아카이브됨)."""
        logger.info("add_pdf_v7 called, redirecting to add_pdf()")
        return await self.add_pdf(file_path, metadata)

    async def _process_with_vision(
        self,
        path: Path,
        metadata: Optional[dict] = None
    ) -> dict:
        """통합 PDF 프로세서로 PDF 처리 (권장 파이프라인).

        단일 API 호출로 텍스트 추출, 섹션 분류, 청킹, 메타데이터 추출을 수행.
        환경변수 LLM_PROVIDER에 따라 Claude 또는 Gemini 사용.

        Args:
            path: PDF 파일 경로
            metadata: 추가 메타데이터

        Returns:
            처리 결과 딕셔너리
        """
        import json
        from dataclasses import dataclass, field

        # 1. LLM API로 전체 처리 (Claude 또는 Gemini)
        result = await self.vision_processor.process_pdf(str(path))

        if not result.success:
            logger.warning(f"PDF processing failed: {result.error}")
            # Fallback to legacy pipeline
            return await self._process_with_legacy_pipeline(path, metadata)

        # 2. 결과 형식 변환 (UnifiedPDFProcessor vs Legacy)
        # UnifiedPDFProcessor는 extracted_data를 반환, Legacy는 metadata/chunks를 반환
        # 통합 인용 추출 (v3.2+: 단일 LLM 호출에서 인용도 함께 추출)
        integrated_citations = None

        if hasattr(result, 'extracted_data') and result.extracted_data:
            # UnifiedPDFProcessor 결과 변환
            extracted_data = result.extracted_data
            # v7.14.27: None 값 처리
            meta_dict = extracted_data.get("metadata") or {}
            spine_dict = extracted_data.get("spine_metadata") or {}
            chunks_list = extracted_data.get("chunks") or []
            # 통합 추출된 인용 (있는 경우 - 별도 LLM 호출 불필요)
            integrated_citations = extracted_data.get("important_citations") or []

            # Raw JSON 자동 저장 (data/extracted/ 폴더)
            try:
                extracted_dir = Path("data/extracted")
                extracted_dir.mkdir(parents=True, exist_ok=True)

                # 파일명 생성 (논문 제목 기반)
                safe_title = "".join(c for c in meta_dict.get("title", "unknown")[:50] if c.isalnum() or c in " -_").strip()
                safe_title = safe_title.replace(" ", "_") or "unknown"
                year = meta_dict.get("year", "0000")
                first_author = meta_dict.get("authors", ["unknown"])[0].split()[-1] if meta_dict.get("authors") else "unknown"
                json_filename = f"{year}_{first_author}_{safe_title}.json"

                json_path = extracted_dir / json_filename
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(extracted_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Raw JSON saved: {json_path}")
            except Exception as e:
                logger.warning(f"Failed to save raw JSON: {e}")

            # ExtractedMetadata 호환 객체 생성
            @dataclass
            class ExtractedMetadataCompat:
                title: str = ""
                authors: list = field(default_factory=list)
                year: int = 0
                journal: str = ""
                doi: str = ""
                pmid: str = ""
                study_type: str = ""
                study_design: str = ""  # randomized/non-randomized/single-arm/multi-arm
                evidence_level: str = ""
                sample_size: int = 0
                centers: str = ""  # single-center/multi-center
                blinding: str = ""  # none/single-blind/double-blind/open-label
                spine: Any = None
                abstract: str = ""  # Legacy Knowledge Graph 호환

            @dataclass
            class SpineMetadataCompat:
                sub_domain: str = ""
                anatomy_level: str = ""
                anatomy_region: str = ""
                pathology: list = field(default_factory=list)
                interventions: list = field(default_factory=list)
                outcomes: list = field(default_factory=list)
                complications: list = field(default_factory=list)
                follow_up_months: int = 0
                main_conclusion: str = ""
                # PICO (v3.0 - spine_metadata에 추가)
                pico_population: str = ""
                pico_intervention: str = ""
                pico_comparison: str = ""
                pico_outcome: str = ""

            # PICO 파싱 (v3.0)
            pico_dict = spine_dict.get("pico", {})
            spine_meta = SpineMetadataCompat(
                sub_domain=spine_dict.get("sub_domain", ""),
                anatomy_level=spine_dict.get("anatomy_level", ""),
                anatomy_region=spine_dict.get("anatomy_region", ""),
                pathology=spine_dict.get("pathology", []),
                interventions=spine_dict.get("interventions", []),
                outcomes=spine_dict.get("outcomes", []),
                complications=spine_dict.get("complications", []),
                follow_up_months=spine_dict.get("follow_up_months", 0),
                main_conclusion=spine_dict.get("main_conclusion", ""),
                # PICO (v3.0)
                pico_population=pico_dict.get("population", "") if pico_dict else "",
                pico_intervention=pico_dict.get("intervention", "") if pico_dict else "",
                pico_comparison=pico_dict.get("comparison", "") if pico_dict else "",
                pico_outcome=pico_dict.get("outcome", "") if pico_dict else "",
            )

            extracted_meta = ExtractedMetadataCompat(
                title=meta_dict.get("title", ""),
                authors=meta_dict.get("authors", []),
                year=meta_dict.get("year", 0),
                journal=meta_dict.get("journal", ""),
                doi=meta_dict.get("doi", ""),
                pmid=meta_dict.get("pmid", ""),
                study_type=meta_dict.get("study_type", ""),
                study_design=meta_dict.get("study_design", ""),
                evidence_level=meta_dict.get("evidence_level", ""),
                sample_size=meta_dict.get("sample_size", 0),
                centers=meta_dict.get("centers", ""),
                blinding=meta_dict.get("blinding", ""),
                spine=spine_meta,
                abstract=meta_dict.get("abstract", ""),  # Legacy Knowledge Graph 호환
            )

            # ExtractedChunk 호환 객체 생성 (v3.0 간소화)
            @dataclass
            class ExtractedChunkCompat:
                content: str = ""
                content_type: str = "text"
                section_type: str = ""
                tier: str = "tier1"
                is_key_finding: bool = False
                statistics: dict = field(default_factory=dict)
                # v3.0: summary (topic_summary에서 변경), keywords
                summary: str = ""
                keywords: list = field(default_factory=list)
                # PICO 제거됨 (v3.0) - spine_metadata에서 조회

            result_chunks = []
            for chunk_dict in chunks_list:
                result_chunks.append(ExtractedChunkCompat(
                    content=chunk_dict.get("content", ""),
                    content_type=chunk_dict.get("content_type", "text"),
                    section_type=chunk_dict.get("section_type", ""),
                    tier=chunk_dict.get("tier", "tier1"),
                    is_key_finding=chunk_dict.get("is_key_finding", False),
                    statistics=chunk_dict.get("statistics", {}),
                    # v3.0: summary (하위호환: topic_summary도 지원)
                    summary=chunk_dict.get("summary", "") or chunk_dict.get("topic_summary", ""),
                    keywords=chunk_dict.get("keywords", []),
                ))

            # result 객체에 호환 속성 추가
            result.metadata = extracted_meta
            result.chunks = result_chunks

            logger.info(f"Unified PDF processor result: provider={result.provider}, model={result.model}, chunks={len(result_chunks)}")
        else:
            # Legacy VisionProcessorResult는 이미 metadata/chunks 속성이 있음
            extracted_meta = result.metadata
        pubmed_metadata = None
        pubmed_enriched = False

        if self.pubmed_enricher:
            try:
                logger.info(f"Attempting PubMed enrichment for: {extracted_meta.title[:50]}...")
                pubmed_metadata = await self.pubmed_enricher.auto_enrich(
                    title=extracted_meta.title,
                    authors=extracted_meta.authors,
                    year=extracted_meta.year,
                    journal=extracted_meta.journal,
                    doi=extracted_meta.doi
                )

                if pubmed_metadata:
                    pubmed_enriched = True
                    logger.info(f"PubMed enrichment successful: PMID={pubmed_metadata.pmid}, confidence={pubmed_metadata.confidence:.2f}")

                    # 근거 수준을 publication type에서 추론 (LLM 결과가 없는 경우)
                    if not extracted_meta.evidence_level and pubmed_metadata.publication_types:
                        inferred_level = self.pubmed_enricher.get_evidence_level_from_publication_type(
                            pubmed_metadata.publication_types
                        )
                        if inferred_level:
                            extracted_meta.evidence_level = inferred_level
                            logger.info(f"Evidence level inferred from PubMed: {inferred_level}")
                else:
                    logger.debug("PubMed enrichment returned no results")

            except Exception as e:
                logger.warning(f"PubMed enrichment failed: {e}")

        # 3. 문서 ID 생성
        pdf_metadata = {
            "title": extracted_meta.title,
            "authors": extracted_meta.authors,
            "year": extracted_meta.year,
            "journal": extracted_meta.journal,
            "doi": extracted_meta.doi,
            "first_author": extracted_meta.authors[0].split()[-1] if extracted_meta.authors else ""
        }
        doc_id = self._generate_document_id(pdf_metadata, path.stem)

        # 사용자 메타데이터와 병합 (PubMed 서지 정보 포함)
        merged_metadata = {
            **pdf_metadata,
            **(metadata or {}),
            "original_filename": path.name,
            "study_type": extracted_meta.study_type,
            "evidence_level": extracted_meta.evidence_level,
            "processing_method": "gemini_vision"
        }

        # PubMed 서지 정보 추가
        if pubmed_metadata:
            merged_metadata["pubmed"] = {
                "pmid": pubmed_metadata.pmid,
                "doi": pubmed_metadata.doi,  # PubMed 정규화된 DOI
                "mesh_terms": pubmed_metadata.mesh_terms,
                "keywords": pubmed_metadata.keywords,
                "publication_types": pubmed_metadata.publication_types,
                "journal_abbrev": pubmed_metadata.journal_abbrev,
                "affiliation": pubmed_metadata.affiliation,
                "abstract": pubmed_metadata.abstract[:500] if pubmed_metadata.abstract else None,  # 초록 일부만
                "enrichment_confidence": pubmed_metadata.confidence,
                "enriched_at": pubmed_metadata.enriched_at.isoformat() if pubmed_metadata.enriched_at else None
            }

        logger.info(f"Document ID generated: {doc_id}")
        logger.info(f"Extracted {len(result.chunks)} chunks via LLM API")

        # 3. LLM 추출 청크를 TextChunk로 변환 (v3.0 간소화)
        chunks = []
        for i, vision_chunk in enumerate(result.chunks):
            # 통계 정보 추출 (v3.0 간소화: p_value, is_significant, additional)
            stats_p_value = ""
            stats_is_significant = False
            stats_additional = ""
            has_stats = False

            if vision_chunk.statistics:
                stats = vision_chunk.statistics
                # dict 형식 (unified processor) vs object 형식 (legacy) 둘 다 지원
                if isinstance(stats, dict):
                    stats_p_value = str(stats.get("p_value", ""))
                    stats_is_significant = bool(stats.get("is_significant", False))
                    stats_additional = str(stats.get("additional", ""))
                else:
                    # Legacy object 형식
                    stats_p_value = str(getattr(stats, "p_value", ""))
                    stats_is_significant = bool(getattr(stats, "is_significant", False))
                    stats_additional = str(getattr(stats, "additional", ""))
                has_stats = bool(stats_p_value or stats_is_significant)

            # PICO 제거됨 (v3.0) - spine_metadata로 이동

            # summary 필드 (v3.0: topic_summary 대신 summary 사용)
            chunk_summary = ""
            if hasattr(vision_chunk, 'summary') and vision_chunk.summary:
                chunk_summary = vision_chunk.summary
            elif hasattr(vision_chunk, 'topic_summary') and vision_chunk.topic_summary:
                chunk_summary = vision_chunk.topic_summary  # 하위호환

            chunk = TextChunk(
                chunk_id=f"{doc_id}_vision_chunk_{i}",
                content=vision_chunk.content,
                document_id=doc_id,
                tier=vision_chunk.tier,
                section=vision_chunk.section_type,
                source_type="original",
                evidence_level=extracted_meta.evidence_level,
                publication_year=extracted_meta.year,
                title=extracted_meta.title,
                authors=extracted_meta.authors,
                metadata=merged_metadata,
                # LLM 추출 메타데이터 (v3.0)
                summary=chunk_summary,
                keywords=vision_chunk.keywords if isinstance(vision_chunk.keywords, list) else [],
                # PICO 제거됨 (v3.0) - Neo4j PaperNode에서 조회
                # 통계 정보 (v3.0 간소화)
                statistics_p_value=stats_p_value,
                statistics_is_significant=stats_is_significant,
                statistics_additional=stats_additional,
                has_statistics=has_stats,
                llm_processed=True,
                llm_confidence=0.9,  # LLM 처리는 높은 신뢰도
                is_key_finding=vision_chunk.is_key_finding,
            )
            chunks.append(chunk)

        # 4. 임베딩 생성 (OpenAI text-embedding-3-large)
        embeddings = self._generate_embeddings(chunks)

        # 5. Vector DB 저장 (v5.3 Phase 4: Neo4j 전용 모드)
        tier1_chunks = [c for c in chunks if c.tier == "tier1"]
        tier2_chunks = [c for c in chunks if c.tier == "tier2"]

        # v5.3: ChromaDB 제거됨 - Neo4j만 사용
        logger.info(f"Neo4j-only mode: {len(tier1_chunks)} tier1, {len(tier2_chunks)} tier2 chunks prepared")

        # 5.5 Neo4j Chunk 저장 (v5.3 - Neo4j Vector Index, Primary Storage)
        neo4j_chunk_count = 0
        if GRAPH_AVAILABLE and self.neo4j_client and ChunkNode:
            try:
                # ChunkNode 객체 리스트 생성
                chunk_nodes = []
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk_node = ChunkNode(
                        chunk_id=chunk.chunk_id,
                        paper_id=doc_id,
                        content=chunk.content,
                        embedding=embedding,  # 3072-dim OpenAI embedding
                        tier=chunk.tier,
                        section=chunk.section,
                        content_type=getattr(chunk, 'content_type', 'text'),
                        evidence_level=chunk.evidence_level or "5",
                        is_key_finding=getattr(chunk, 'is_key_finding', False),
                        page_num=getattr(chunk, 'page_num', 0),
                        chunk_index=i,
                    )
                    chunk_nodes.append(chunk_node)

                # 일괄 저장
                if chunk_nodes:
                    batch_result = await self.neo4j_client.create_chunks_batch(doc_id, chunk_nodes)
                    neo4j_chunk_count = batch_result.get("created_count", len(chunk_nodes))
                    logger.info(f"Neo4j Chunks: {neo4j_chunk_count} chunks stored with 3072-dim embeddings")

            except Exception as e:
                logger.warning(f"Neo4j chunk storage failed: {e}")

        # 6. Legacy Knowledge Graph 통합 - REMOVED (SQLite-based paper_graph deprecated)
        # NOTE: All paper relations are now handled by Neo4j (step 7)

        # 7. Neo4j Graph 통합 (Spine GraphRAG v3) - Paper 노드 및 관계 생성
        neo4j_nodes = 0
        neo4j_relations = 0
        neo4j_warnings = []
        if GRAPH_AVAILABLE and self.relationship_builder:
            try:
                # SpineMetadata 구성 (ExtractedMetadata.spine에서 가져옴)
                spine_meta = extracted_meta.spine if hasattr(extracted_meta, 'spine') and extracted_meta.spine else None

                # SpineMetadata 속성명 호환성 처리:
                # - gemini_vision_processor.py: anatomy_level (단수, str), pathology (list)
                # - relationship_builder.py: anatomy_levels (복수, list), pathologies (list)
                pathologies = getattr(spine_meta, 'pathologies', None) or getattr(spine_meta, 'pathology', []) if spine_meta else []
                interventions = getattr(spine_meta, 'interventions', []) if spine_meta else []

                if spine_meta and (interventions or pathologies):
                    # spine metadata가 있는 경우 (v2.0 processor)
                    # anatomy_level (str) → anatomy_levels (list) 변환
                    anatomy_level = getattr(spine_meta, 'anatomy_level', '') or ''
                    anatomy_levels = [anatomy_level] if anatomy_level else []

                    # spine_meta에서 outcomes 추출 (Unified Schema v4.0)
                    # Claude와 Gemini PDF 처리기 결과 모두 지원
                    raw_outcomes = getattr(spine_meta, 'outcomes', []) or []
                    spine_outcomes = []
                    for o in raw_outcomes:
                        if isinstance(o, dict):
                            spine_outcomes.append({
                                "name": o.get("name", ""),
                                # === 결과값 (여러 형식 지원) ===
                                "value": o.get("value", "") or o.get("value_intervention", ""),
                                "baseline": o.get("baseline"),          # Claude 형식
                                "final": o.get("final"),                # Claude 형식
                                "value_intervention": o.get("value_intervention", ""),
                                "value_control": o.get("value_control", ""),
                                "value_difference": o.get("value_difference", ""),
                                # === 통계 정보 ===
                                "p_value": o.get("p_value", ""),
                                "effect_size": o.get("effect_size", ""),
                                "confidence_interval": o.get("confidence_interval", ""),
                                "is_significant": o.get("is_significant", False),
                                # === 메타데이터 ===
                                "direction": o.get("direction", ""),
                                "category": o.get("category", ""),
                                "timepoint": o.get("timepoint", "")
                            })
                        else:
                            # Legacy object 형식
                            spine_outcomes.append({
                                "name": getattr(o, 'name', ''),
                                # === 결과값 (여러 형식 지원) ===
                                "value": getattr(o, 'value', '') or getattr(o, 'value_intervention', ''),
                                "baseline": getattr(o, 'baseline', None),
                                "final": getattr(o, 'final', None),
                                "value_intervention": getattr(o, 'value_intervention', ''),
                                "value_control": getattr(o, 'value_control', ''),
                                "value_difference": getattr(o, 'value_difference', ''),
                                # === 통계 정보 ===
                                "p_value": getattr(o, 'p_value', ''),
                                "effect_size": getattr(o, 'effect_size', ''),
                                "confidence_interval": getattr(o, 'confidence_interval', ''),
                                "is_significant": getattr(o, 'is_significant', False),
                                # === 메타데이터 ===
                                "direction": getattr(o, 'direction', ''),
                                "category": getattr(o, 'category', ''),
                                "timepoint": getattr(o, 'timepoint', '')
                            })

                    # outcomes나 anatomy_levels가 비어있으면 청크에서 보완 추출
                    if not spine_outcomes or not anatomy_levels:
                        inferred = self._infer_spine_metadata_from_chunks(result.chunks)
                        if not spine_outcomes:
                            spine_outcomes = inferred.outcomes
                            logger.info(f"Inferred {len(spine_outcomes)} outcomes from chunks")
                        if not anatomy_levels:
                            anatomy_levels = inferred.anatomy_levels
                            logger.info(f"Inferred anatomy levels: {anatomy_levels}")

                    # v3.2: sub_domains 우선 사용, 없으면 sub_domain에서 생성
                    sub_domains = getattr(spine_meta, 'sub_domains', []) or []
                    sub_domain = getattr(spine_meta, 'sub_domain', '') or ''
                    if not sub_domains and sub_domain:
                        sub_domains = [sub_domain]

                    # v7.14.9: v7.2 Extended entities 포함
                    graph_spine_meta = GraphSpineMetadata(
                        sub_domains=sub_domains,
                        sub_domain=sub_domain or (sub_domains[0] if sub_domains else ''),
                        surgical_approach=getattr(spine_meta, 'surgical_approach', []) or [],
                        anatomy_levels=anatomy_levels,
                        pathologies=pathologies if isinstance(pathologies, list) else [pathologies],
                        interventions=interventions,
                        outcomes=spine_outcomes,
                        main_conclusion=getattr(spine_meta, 'main_conclusion', '') or '',
                        # v7.2 Extended entities
                        patient_cohorts=getattr(spine_meta, 'patient_cohorts', []) or [],
                        followups=getattr(spine_meta, 'followups', []) or [],
                        costs=getattr(spine_meta, 'costs', []) or [],
                        quality_metrics=getattr(spine_meta, 'quality_metrics', []) or [],
                    )
                else:
                    # spine_metadata가 없거나 비어있는 경우 - 청크에서 추론
                    graph_spine_meta = self._infer_spine_metadata_from_chunks(result.chunks)

                # Neo4j에 Paper 노드 및 관계 생성 (v7.5: 멀티유저 지원)
                build_result = await self.relationship_builder.build_from_paper(
                    paper_id=doc_id,
                    metadata=extracted_meta,
                    spine_metadata=graph_spine_meta,
                    chunks=result.chunks,
                    owner=self.current_user,
                    shared=True  # 기본적으로 공유 (필요시 False로 변경 가능)
                )

                neo4j_nodes = build_result.nodes_created
                neo4j_relations = build_result.relationships_created
                neo4j_warnings = build_result.warnings

                logger.info(f"Neo4j Graph: {neo4j_nodes} nodes, {neo4j_relations} relations created")
                if neo4j_warnings:
                    logger.warning(f"Neo4j warnings: {neo4j_warnings}")

            except Exception as e:
                logger.warning(f"Neo4j Graph integration failed: {e}")

        # === Important Citation Processing (v3.2+) ===
        # 통합 추출 방식 (integrated_citations) vs 별도 LLM 호출 방식 선택
        citation_result = None
        citation_method = "none"

        if self.citation_processor:
            try:
                # 우선순위 1: 통합 추출된 인용 사용 (LLM 호출 없음 - 비용 절감)
                if integrated_citations:
                    citation_method = "integrated"
                    logger.info(f"Using integrated citations ({len(integrated_citations)} found) - no extra LLM call")

                    citation_result = await self.citation_processor.process_from_integrated_citations(
                        citing_paper_id=doc_id,
                        citations=integrated_citations
                    )

                # 우선순위 2: 별도 LLM 호출로 인용 추출 (레거시 방식)
                elif result.chunks:
                    citation_method = "separate_llm"
                    logger.info("Using separate LLM call for citation extraction (legacy mode)")

                    # 주요 발견사항 추출 (있는 경우)
                    main_findings = []
                    if hasattr(extracted_meta, 'spine') and extracted_meta.spine:
                        main_conclusion = getattr(extracted_meta.spine, 'main_conclusion', '')
                        if main_conclusion:
                            main_findings.append(main_conclusion)

                    # Discussion/Results 섹션에서 중요 인용 처리
                    # 청크를 딕셔너리로 변환
                    chunks_dicts = []
                    for chunk in result.chunks:
                        chunks_dicts.append({
                            "content": getattr(chunk, 'content', ''),
                            "section": getattr(chunk, 'section_type', ''),
                        })

                    citation_result = await self.citation_processor.process_from_chunks(
                        citing_paper_id=doc_id,
                        chunks=chunks_dicts,
                        main_findings=main_findings,
                        paper_title=extracted_meta.title
                    )

                if citation_result:
                    logger.info(
                        f"Citation processing ({citation_method}): "
                        f"{citation_result.important_citations_count} important citations, "
                        f"{citation_result.papers_created} papers, {citation_result.relationships_created} CITES relations"
                    )

            except Exception as e:
                logger.warning(f"Important Citation processing failed: {e}")

        return {
            "success": True,
            "document_id": doc_id,
            "processing_method": "gemini_pdf",
            "extracted_metadata": {
                "title": extracted_meta.title,
                "authors": extracted_meta.authors,
                "year": extracted_meta.year,
                "journal": extracted_meta.journal,
                "study_type": extracted_meta.study_type,
                "evidence_level": extracted_meta.evidence_level,
                "first_author": pdf_metadata.get("first_author", "")
            },
            "pubmed_enrichment": {
                "enabled": self.pubmed_enricher is not None,
                "enriched": pubmed_enriched,
                "pmid": pubmed_metadata.pmid if pubmed_metadata else None,
                "mesh_terms": pubmed_metadata.mesh_terms if pubmed_metadata else [],
                "publication_types": pubmed_metadata.publication_types if pubmed_metadata else [],
                "confidence": pubmed_metadata.confidence if pubmed_metadata else 0.0
            },
            "stats": {
                "tier1_chunks": len(tier1_chunks),
                "tier2_chunks": len(tier2_chunks),
                "total_chunks": neo4j_chunk_count,
                "storage_backend": "neo4j",  # v5.3 Phase 4: Neo4j 전용
                "evidence_level": extracted_meta.evidence_level,
                "study_type": extracted_meta.study_type,
                "study_design": extracted_meta.study_design,
                "centers": extracted_meta.centers,
                "blinding": extracted_meta.blinding
            },
            "knowledge_graph": {
                "paper_added": False,  # Legacy SQLite paper_graph removed
                "relations_found": 0  # Legacy relations removed
            },
            "neo4j_graph": {
                "enabled": GRAPH_AVAILABLE and self.relationship_builder is not None,
                "nodes_created": neo4j_nodes,
                "relationships_created": neo4j_relations,
                "chunks_stored": neo4j_chunk_count,  # v5.3: Neo4j Vector Index
                "warnings": neo4j_warnings
            },
            "important_citations": {
                "enabled": self.citation_processor is not None,
                "method": citation_method,  # "integrated" (no extra LLM) or "separate_llm" (legacy)
                "processed": citation_result is not None,
                "total_found": citation_result.total_citations_found if citation_result else 0,
                "important_count": citation_result.important_citations_count if citation_result else 0,
                "papers_created": citation_result.papers_created if citation_result else 0,
                "cites_relations": citation_result.relationships_created if citation_result else 0
            },
            "api_usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens
            }
        }

    def _infer_spine_metadata_from_chunks(self, chunks: list) -> "GraphSpineMetadata":
        """청크에서 SpineMetadata 추론 (spine_metadata가 없는 경우).

        Args:
            chunks: ExtractedChunk 목록

        Returns:
            GraphSpineMetadata 객체
        """
        import re

        interventions = set()
        pathologies = set()
        anatomy_levels = set()
        outcomes_dict = {}  # name -> outcome dict (중복 방지)
        sub_domain = "Degenerative"  # 기본값

        # 알려진 수술법 키워드
        known_interventions = {
            "TLIF", "PLIF", "ALIF", "OLIF", "XLIF", "LLIF",
            "UBE", "BESS", "Biportal", "FELD", "PELD", "MED",
            "Laminectomy", "Laminotomy", "Foraminotomy",
            "Fusion", "Decompression", "Discectomy", "Microdiscectomy"
        }

        # 알려진 질환 키워드
        known_pathologies = {
            "Stenosis", "Lumbar Stenosis", "Spinal Stenosis",
            "Disc Herniation", "HNP", "HIVD", "Lumbar Disc Herniation",
            "Spondylolisthesis", "Spondylosis",
            "Scoliosis", "Kyphosis", "Deformity"
        }

        # 알려진 결과변수 키워드 (카테고리 포함)
        known_outcomes = {
            "VAS": "pain", "VAS Back": "pain", "VAS Leg": "pain", "NRS": "pain",
            "ODI": "function", "JOA": "function", "Oswestry": "function",
            "SF-36": "quality_of_life", "EQ-5D": "quality_of_life",
            "Fusion Rate": "radiologic", "Fusion": "radiologic",
            "Complication": "complication", "Blood Loss": "clinical",
            "Operation Time": "clinical", "Hospital Stay": "clinical",
            "MacNab": "satisfaction", "Satisfaction": "satisfaction"
        }

        # Results 섹션 청크 우선 처리
        results_chunks = [c for c in chunks if getattr(c, 'section_type', '') == 'results']
        other_chunks = [c for c in chunks if getattr(c, 'section_type', '') != 'results']
        ordered_chunks = results_chunks + other_chunks

        for chunk in ordered_chunks:
            content = getattr(chunk, 'content', "") or ""
            content_lower = content.lower()

            # 1. 키워드에서 추출
            if hasattr(chunk, 'keywords') and chunk.keywords:
                for kw in chunk.keywords:
                    kw_upper = kw.upper()

                    # Interventions
                    for known in known_interventions:
                        if known.upper() in kw_upper or kw_upper in known.upper():
                            interventions.add(known)

                    # Pathologies
                    for known in known_pathologies:
                        if known.upper() in kw_upper or kw_upper in known.upper():
                            pathologies.add(known)

            # 2. PICO에서 추출 (pico가 dict 또는 객체일 수 있음)
            if hasattr(chunk, 'pico') and chunk.pico:
                pico = chunk.pico
                pico_intervention = pico.get("intervention", "") if isinstance(pico, dict) else getattr(pico, 'intervention', '')
                if pico_intervention:
                    for known in known_interventions:
                        if known.upper() in pico_intervention.upper():
                            interventions.add(known)

            # 3. Anatomy levels (L1-L5, C1-C7, T1-T12)
            levels = re.findall(r'\b([LCT]\d+(?:-[LCT]?\d+)?)\b', content, re.IGNORECASE)
            anatomy_levels.update([l.upper() for l in levels])

            # 4. Content에서 직접 추출
            for known in known_interventions:
                if known.lower() in content_lower or known.upper() in content:
                    interventions.add(known)

            # 5. Outcomes 추출 (statistics 데이터 활용) - dict 또는 객체 모두 지원
            stats = getattr(chunk, 'statistics', None)
            p_values_from_stats = []
            if stats:
                if isinstance(stats, dict):
                    p_values_from_stats = stats.get('p_values', []) or []
                elif hasattr(stats, 'p_values') and stats.p_values:
                    p_values_from_stats = stats.p_values

            # Content에서 p-value 패턴 추출
            p_value_patterns = re.findall(
                r'[pP]\s*[=<>]\s*(0\.\d+|<\s*0\.\d+)',
                content
            )

            for outcome_name, category in known_outcomes.items():
                if outcome_name.lower() in content_lower:
                    if outcome_name not in outcomes_dict:
                        # p-value 추출 시도
                        p_val = None
                        is_significant = False

                        # 해당 outcome 근처의 p-value 찾기
                        outcome_pattern = rf'{re.escape(outcome_name)}[^.]*?[pP]\s*[=<]\s*(0\.\d+|<\s*0\.\d+)'
                        p_match = re.search(outcome_pattern, content, re.IGNORECASE)
                        if p_match:
                            try:
                                p_str = p_match.group(1).replace('<', '').strip()
                                p_val = float(p_str)
                                is_significant = p_val < 0.05
                            except ValueError:
                                pass

                        # statistics에서 p-value 가져오기
                        if not p_val and p_values_from_stats:
                            try:
                                p_str = p_values_from_stats[0]
                                p_num = re.search(r'(0\.\d+)', p_str)
                                if p_num:
                                    p_val = float(p_num.group(1))
                                    is_significant = p_val < 0.05
                            except (ValueError, IndexError):
                                pass

                        # 값 추출 시도 (outcome 근처의 숫자)
                        value = ""
                        value_pattern = rf'{re.escape(outcome_name)}[^.]*?(\d+\.?\d*\s*±?\s*\d*\.?\d*)'
                        v_match = re.search(value_pattern, content, re.IGNORECASE)
                        if v_match:
                            value = v_match.group(1).strip()

                        outcomes_dict[outcome_name] = {
                            "name": outcome_name,
                            # === 결과값 ===
                            "value": value,
                            "baseline": None,           # 청크에서 추론 불가
                            "final": None,              # 청크에서 추론 불가
                            "value_intervention": value,
                            "value_control": "",
                            "value_difference": "",
                            # === 통계 정보 ===
                            "p_value": p_val,
                            "effect_size": "",
                            "confidence_interval": "",
                            "is_significant": is_significant,
                            # === 메타데이터 ===
                            "direction": "improved",    # 기본값, 추후 개선
                            "category": category,
                            "timepoint": ""
                        }

            # 6. Lumbar 키워드로 anatomy 추론
            if "lumbar" in content_lower and not anatomy_levels:
                anatomy_levels.add("Lumbar")
            if "cervical" in content_lower and not anatomy_levels:
                anatomy_levels.add("Cervical")

        return GraphSpineMetadata(
            # v3.2: 다중 분류 지원
            sub_domains=[sub_domain] if sub_domain else [],
            sub_domain=sub_domain,
            surgical_approach=[],  # 청크에서 추론 시 빈 값
            anatomy_levels=list(anatomy_levels)[:5],
            pathologies=list(pathologies)[:5],
            interventions=list(interventions)[:5],
            outcomes=list(outcomes_dict.values())[:10],
            main_conclusion="",  # 청크에서 추론 시 빈 값
            # PICO (v3.0) - 청크에서 추론 시 빈 값 (spine_metadata 없는 경우)
            pico_population="",
            pico_intervention="",
            pico_comparison="",
            pico_outcome="",
        )

    async def _add_to_knowledge_graph(
        self,
        doc_id: str,
        metadata,  # ExtractedMetadata from gemini_vision_processor
        chunks: list,  # ExtractedChunk list
        embeddings: Optional[list[list[float]]] = None
    ) -> int:
        """DEPRECATED: Legacy SQLite-based Knowledge Graph (removed).

        This method is no longer functional. All paper relations are now handled by Neo4j.
        See RelationshipBuilder in src/graph/relationship_builder.py for Neo4j integration.

        Args:
            doc_id: 문서 ID
            metadata: 추출된 메타데이터 (ExtractedMetadata)
            chunks: 추출된 청크 목록 (ExtractedChunk)
            embeddings: 임베딩 벡터 (선택적)

        Returns:
            0 (always, deprecated)
        """
        logger.warning("_add_to_knowledge_graph is deprecated. Use Neo4j RelationshipBuilder instead.")
        return 0

    async def _process_with_legacy_pipeline(
        self,
        path: Path,
        metadata: Optional[dict] = None
    ) -> dict:
        """기존 멀티스텝 파이프라인으로 PDF 처리 (Fallback).

        PyMuPDF 텍스트 추출 → LLM 섹션 분류 → LLM 청킹 → LLM 메타데이터 추출

        Args:
            path: PDF 파일 경로
            metadata: 추가 메타데이터

        Returns:
            처리 결과 딕셔너리
        """
        # 1. PDF 파싱 (기본 텍스트 추출)
        text = self._extract_pdf_text(path)
        if not text:
            return {"success": False, "error": "텍스트 추출 실패"}

        # 2. 메타데이터 추출 및 문서 ID 생성 (Author_Year_Title 형식)
        pdf_metadata = self._extract_pdf_metadata(path, text)
        doc_id = self._generate_document_id(pdf_metadata, path.stem)

        # 사용자 메타데이터와 병합
        merged_metadata = {
            **pdf_metadata,
            **(metadata or {}),
            "original_filename": path.name,
            "processing_method": "legacy_pipeline"
        }

        logger.info(f"Document ID generated: {doc_id}")

        # LLM 파이프라인 사용 여부 결정
        use_llm_pipeline = (
            self.enable_llm and
            self.llm_client is not None and
            self.llm_section_classifier is not None and
            self.llm_chunker is not None
        )

        if use_llm_pipeline:
            logger.info("Using LLM pipeline for processing")
            chunks = await self._process_with_llm_pipeline(
                text=text,
                doc_id=doc_id,
                metadata=merged_metadata,
                pdf_metadata=pdf_metadata
            )
        else:
            logger.info("Using rule-based pipeline for processing")
            # 기존 규칙 기반 처리
            sections = self._classify_sections(text)
            citation_info = self._detect_citations(text)
            study_info = self._classify_study(text)

            chunks = self._create_chunks(
                text=text,
                file_path=str(path),
                sections=sections,
                citation_info=citation_info,
                study_info=study_info,
                metadata=merged_metadata,
                doc_id=doc_id
            )

        # 연구 설계 분류 (통계용)
        study_info = self._classify_study(text)

        # 임베딩 생성 (OpenAI)
        embeddings = self._generate_embeddings(chunks)

        # Vector DB 저장 (v5.3 Phase 4: Neo4j 전용 모드 지원)
        tier1_chunks = [c for c in chunks if c.tier == "tier1"]
        tier2_chunks = [c for c in chunks if c.tier == "tier2"]

        neo4j_chunk_count = 0

        # v5.3: ChromaDB 제거됨 - Neo4j만 사용
        logger.info(f"Legacy pipeline: {len(tier1_chunks)} tier1, {len(tier2_chunks)} tier2 chunks prepared")

        # Neo4j Chunk 저장 (v5.3)
        if GRAPH_AVAILABLE and self.neo4j_client and ChunkNode:
            try:
                chunk_nodes = []
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk_node = ChunkNode(
                        chunk_id=chunk.chunk_id,
                        paper_id=doc_id,
                        content=chunk.content,
                        embedding=embedding,
                        tier=chunk.tier,
                        section=chunk.section,
                        evidence_level=getattr(chunk, 'evidence_level', "5"),
                        is_key_finding=getattr(chunk, 'is_key_finding', False),
                        page_num=getattr(chunk, 'page_num', 0),
                        chunk_index=i,
                    )
                    chunk_nodes.append(chunk_node)

                if chunk_nodes:
                    result = await self.neo4j_client.create_chunks_batch(doc_id, chunk_nodes)
                    neo4j_chunk_count = result.get("created_count", len(chunk_nodes))
            except Exception as e:
                logger.warning(f"Legacy pipeline: Neo4j chunk storage failed: {e}")

        return {
            "success": True,
            "document_id": doc_id,
            "processing_method": "legacy_pipeline",
            "extracted_metadata": {
                "title": pdf_metadata.get("title", ""),
                "authors": pdf_metadata.get("authors", []),
                "year": pdf_metadata.get("year", 0),
                "first_author": pdf_metadata.get("first_author", "")
            },
            "stats": {
                "tier1_chunks": len(tier1_chunks),
                "tier2_chunks": len(tier2_chunks),
                "total_chunks": neo4j_chunk_count,
                "storage_backend": "neo4j",
                "evidence_level": study_info.get("evidence_level", "unknown") if study_info else "unknown",
                "study_design": study_info.get("design", "unknown") if study_info else "unknown"
            }
        }

    async def analyze_text(
        self,
        text: str,
        title: str,
        pmid: Optional[str] = None,
        metadata: Optional[dict] = None,
        use_v7: bool = True
    ) -> dict:
        """텍스트(논문 초록/본문)를 직접 분석하여 Neo4j에 저장.

        Claude Code에서 논문 텍스트를 붙여넣고 분석 → 관계 구축 → 청크 저장을
        한 번에 수행합니다. PDF 없이 텍스트만으로 지식 그래프 구축이 가능합니다.

        v7.5 업데이트: v7.0 Simplified Pipeline을 기본으로 사용합니다.
        - 22개 문서 유형 자동 감지
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹 (15-25 chunks)
        - 조건부 엔티티 추출 (의학 콘텐츠만)

        Args:
            text: 분석할 텍스트 (논문 초록 또는 본문, 최소 100자 이상)
            title: 논문 제목
            pmid: PubMed ID (선택, 없으면 자동 생성)
            metadata: 추가 메타데이터 (year, journal, authors, doi 등)
            use_v7: v7.5 Simplified Pipeline 사용 여부 (기본값: True)

        Returns:
            분석 결과 및 저장 통계
        """
        import uuid
        from datetime import datetime

        logger.info("Using text analysis pipeline")

        # 1. 입력 검증
        if not text or len(text) < 100:
            return {
                "success": False,
                "error": f"텍스트가 너무 짧습니다. 최소 100자 이상 필요 (현재: {len(text) if text else 0}자)"
            }

        if not title:
            return {
                "success": False,
                "error": "논문 제목(title)은 필수입니다."
            }

        # 2. Paper ID 생성
        if pmid:
            paper_id = f"pubmed_{pmid}"
        else:
            # 자동 생성 (text_로 시작하여 PDF와 구분)
            short_uuid = str(uuid.uuid4())[:8]
            paper_id = f"text_{short_uuid}"

        logger.info(f"Analyzing text: {title[:50]}... (paper_id={paper_id}, {len(text)} chars)")

        # 3. vision_processor 확인
        if not self.vision_processor:
            return {
                "success": False,
                "error": "LLM processor not initialized. ANTHROPIC_API_KEY가 필요합니다."
            }

        # 4. LLM 분석 (process_text 사용)
        try:
            result: ProcessorResult = await self.vision_processor.process_text(
                text=text,
                title=title,
                source="analyze_text_tool",
            )
        except Exception as e:
            logger.exception(f"LLM analysis failed: {e}")
            return {
                "success": False,
                "error": f"LLM 분석 실패: {str(e)}"
            }

        if not result or not result.success:
            return {
                "success": False,
                "error": f"LLM 분석 결과 없음: {getattr(result, 'error', 'unknown')}"
            }

        # 5. PubMed 서지 정보 enrichment (v5.3.5)
        extracted_meta = result.extracted_metadata
        pubmed_metadata = None
        pubmed_enriched = False
        web_search_result = None

        if self.pubmed_enricher:
            try:
                logger.info(f"[analyze_text] Attempting PubMed enrichment for: {title[:50]}...")
                pubmed_metadata = await self.pubmed_enricher.auto_enrich(
                    title=title,
                    authors=metadata.get("authors") if metadata else extracted_meta.authors,
                    year=metadata.get("year") if metadata else extracted_meta.year,
                    journal=metadata.get("journal") if metadata else extracted_meta.journal,
                    doi=metadata.get("doi") if metadata else extracted_meta.doi
                )

                if pubmed_metadata:
                    pubmed_enriched = True
                    logger.info(f"[analyze_text] PubMed enrichment successful: PMID={pubmed_metadata.pmid}, confidence={pubmed_metadata.confidence:.2f}")

                    # 근거 수준을 publication type에서 추론 (LLM 결과가 없는 경우)
                    if not extracted_meta.evidence_level and pubmed_metadata.publication_types:
                        inferred_level = self.pubmed_enricher.get_evidence_level_from_publication_type(
                            pubmed_metadata.publication_types
                        )
                        if inferred_level:
                            extracted_meta.evidence_level = inferred_level
                            logger.info(f"[analyze_text] Evidence level inferred from PubMed: {inferred_level}")
                else:
                    logger.info("[analyze_text] PubMed enrichment returned no results - trying web search fallback")
                    # Web search fallback for non-PubMed sources (books, etc.)
                    web_search_result = await self._web_search_bibliographic_info(
                        title=title,
                        authors=metadata.get("authors") if metadata else extracted_meta.authors,
                        year=metadata.get("year") if metadata else extracted_meta.year
                    )
                    if web_search_result:
                        logger.info(f"[analyze_text] Web search found bibliographic info: {web_search_result.get('source', 'unknown')}")

            except Exception as e:
                logger.warning(f"[analyze_text] PubMed enrichment failed: {e}")
                # Try web search as fallback on PubMed error
                try:
                    web_search_result = await self._web_search_bibliographic_info(
                        title=title,
                        authors=metadata.get("authors") if metadata else extracted_meta.authors,
                        year=metadata.get("year") if metadata else extracted_meta.year
                    )
                except Exception as web_e:
                    logger.warning(f"[analyze_text] Web search fallback also failed: {web_e}")

        # 6. 메타데이터 병합
        metadata = metadata or {}
        year = metadata.get("year") or extracted_meta.year or datetime.now().year
        journal = metadata.get("journal") or extracted_meta.journal or "Unknown"
        authors = metadata.get("authors") or extracted_meta.authors or []
        doi = metadata.get("doi") or extracted_meta.doi

        # PubMed 서지 정보 병합
        if pubmed_metadata:
            if not authors and pubmed_metadata.authors:
                authors = pubmed_metadata.authors
            if journal == "Unknown" and pubmed_metadata.journal:
                journal = pubmed_metadata.journal
            if not doi and pubmed_metadata.doi:
                doi = pubmed_metadata.doi
            if not year and pubmed_metadata.year:
                year = pubmed_metadata.year

        # Web search 결과 병합
        if web_search_result:
            if not authors and web_search_result.get("authors"):
                authors = web_search_result["authors"]
            if journal == "Unknown" and web_search_result.get("publisher"):
                journal = web_search_result["publisher"]
            if not doi and web_search_result.get("doi"):
                doi = web_search_result["doi"]
            if not year and web_search_result.get("year"):
                year = web_search_result["year"]

        # 7. SpineMetadata 준비 (result.spine_metadata는 unified_pdf_processor의 SpineMetadata 타입)
        spine_meta = result.spine_metadata
        # Fallback - 최소 필수 속성 설정 (duck typing으로 처리)
        class MinimalSpineMeta:
            sub_domain = "Unknown"
            anatomy_levels = []
            interventions = []
            pathologies = []
            outcomes = []
        if not spine_meta:
            spine_meta = MinimalSpineMeta()

        # 8. Neo4j 관계 구축 (v7.5: 멀티유저 지원)
        neo4j_result = None
        if self.neo4j_client and self.relationship_builder:
            try:
                # v7.14.9: 헬퍼 함수 사용하여 필드 매핑 처리
                graph_spine_meta = self._convert_to_graph_spine_metadata(spine_meta)

                # ExtractedMetadata 호환 객체 생성
                @dataclass
                class ExtractedMetaCompat:
                    title: str = ""
                    authors: list = df(default_factory=list)
                    year: int = 0
                    journal: str = ""
                    doi: str = ""
                    pmid: str = ""
                    study_type: str = ""
                    study_design: str = ""
                    evidence_level: str = ""
                    sample_size: int = 0
                    centers: str = ""
                    blinding: str = ""
                    abstract: str = ""
                    spine: any = None

                meta_compat = ExtractedMetaCompat(
                    title=title,
                    authors=authors,
                    year=year,
                    journal=journal,
                    doi=doi,
                    pmid=pmid or "",
                    evidence_level=extracted_meta.evidence_level or "unknown",
                    abstract=text[:2000] if len(text) > 2000 else text,
                    spine=graph_spine_meta,
                )

                neo4j_result = await self.relationship_builder.build_from_paper(
                    paper_id=paper_id,
                    metadata=meta_compat,
                    spine_metadata=graph_spine_meta,
                    chunks=[],  # analyze_text는 청크 없음
                    owner=self.current_user,
                    shared=True
                )

                logger.info(f"Neo4j relationships built: {neo4j_result.nodes_created} nodes, {neo4j_result.relationships_created} relationships")

            except Exception as e:
                logger.warning(f"Neo4j relationship building failed: {e}")

        # 9. 청크 생성 및 임베딩 저장
        chunks_created = 0
        chunks_data = result.chunks or []

        if chunks_data and self.neo4j_client:
            try:
                from core.embedding import OpenAIEmbeddingGenerator

                embedding_gen = OpenAIEmbeddingGenerator()

                # 청크 텍스트 추출
                chunk_texts = [c.content for c in chunks_data if hasattr(c, 'content')]

                if chunk_texts:
                    # v7.14.3: 기존 Chunk 삭제 (중복 방지)
                    await self._delete_existing_chunks(paper_id)

                    # 임베딩 생성
                    embeddings = embedding_gen.embed_batch(chunk_texts)

                    # Neo4j에 청크 저장
                    for i, (chunk, embedding) in enumerate(zip(chunks_data, embeddings)):
                        chunk_id = f"{paper_id}_chunk_{i}"

                        # 청크 속성 추출
                        chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        chunk_tier = chunk.tier if hasattr(chunk, 'tier') else 2
                        chunk_section = chunk.section_type if hasattr(chunk, 'section_type') else "body"

                        # Neo4j에 Chunk 노드 생성 및 Paper와 연결
                        await self.neo4j_client.run_query(
                            """
                            MATCH (p:Paper {paper_id: $paper_id})
                            CREATE (c:Chunk {
                                chunk_id: $chunk_id,
                                content: $content,
                                tier: $tier,
                                section: $section,
                                embedding: $embedding
                            })
                            CREATE (p)-[:HAS_CHUNK]->(c)
                            """,
                            {
                                "paper_id": paper_id,
                                "chunk_id": chunk_id,
                                "content": chunk_content,
                                "tier": chunk_tier,
                                "section": chunk_section,
                                "embedding": embedding
                            }
                        )
                        chunks_created += 1

                    logger.info(f"Stored {chunks_created} chunks with embeddings to Neo4j")

            except Exception as e:
                logger.warning(f"Chunk storage failed: {e}")

        # 10. JSON 저장 (v5.3.5)
        pmid_found = pubmed_metadata.pmid if pubmed_metadata else None
        try:
            await self._save_analyze_text_json(
                paper_id=paper_id,
                title=title,
                year=year,
                journal=journal,
                authors=authors,
                doi=doi,
                pmid=pmid_found,
                extracted_data={
                    "spine_metadata": {
                        "sub_domain": spine_meta.sub_domain,
                        "anatomy_levels": spine_meta.anatomy_levels,
                        "interventions": spine_meta.interventions,
                        "pathologies": spine_meta.pathologies,
                        "outcomes": spine_meta.outcomes,
                    },
                    "chunks": [
                        {"content": c.content if hasattr(c, 'content') else str(c)}
                        for c in (result.chunks or [])
                    ],
                },
                pubmed_metadata=pubmed_metadata,
                web_search_result=web_search_result,
            )
        except Exception as e:
            logger.warning(f"[analyze_text] JSON save failed: {e}")

        # 11. 결과 반환
        return {
            "success": True,
            "paper_id": paper_id,
            "title": title,
            "processing_method": "analyze_text",
            "extracted_metadata": {
                "title": title,
                "year": year,
                "journal": journal,
                "authors": authors,
                "doi": doi,
                "pmid": pmid_found,
                "evidence_level": extracted_meta.evidence_level or "unknown",
                "sub_domain": spine_meta.sub_domain,
                "anatomy_levels": spine_meta.anatomy_levels,
                "interventions": spine_meta.interventions,
                "pathologies": spine_meta.pathologies,
            },
            "enrichment": {
                "pubmed_enriched": pubmed_enriched,
                "pmid": pmid_found,
                "mesh_terms": pubmed_metadata.mesh_terms if pubmed_metadata else None,
                "publication_types": pubmed_metadata.publication_types if pubmed_metadata else None,
                "web_search_used": web_search_result is not None,
                "web_search_source": web_search_result.get("source") if web_search_result else None,
            },
            "neo4j_result": {
                "nodes_created": neo4j_result.nodes_created if neo4j_result else 0,
                "relationships_created": neo4j_result.relationships_created if neo4j_result else 0,
                "warnings": neo4j_result.warnings if neo4j_result else [],
            } if neo4j_result else None,
            "stats": {
                "text_length": len(text),
                "chunks_created": chunks_created,
                "storage_backend": "neo4j",
            }
        }

    # ========================================================================
    # v7.5 Text Analysis Pipeline
    # ========================================================================

    # _analyze_text_v7 removed (v7 pipeline archived to src/archive/legacy_v7/)
    # Dead code block removed (was orphaned v7 method body)

    # v5.3.5 Helper Methods for analyze_text
    # ========================================================================

    async def _web_search_bibliographic_info(
        self,
        title: str,
        authors: Optional[list[str]] = None,
        year: Optional[int] = None
    ) -> Optional[dict]:
        """웹 검색으로 서지 정보 찾기 (PubMed에 없는 문서용).

        CrossRef API를 사용하여 DOI, 출판사, 저자 정보를 찾습니다.
        책, 비의학 문서, 컨퍼런스 논문 등에 유용합니다.

        Args:
            title: 문서 제목
            authors: 저자 목록 (선택)
            year: 출판 연도 (선택)

        Returns:
            서지 정보 딕셔너리 또는 None
        """
        import aiohttp
        import urllib.parse

        if not title:
            return None

        try:
            # CrossRef API로 DOI 및 서지 정보 검색
            query = urllib.parse.quote(title)
            crossref_url = f"https://api.crossref.org/works?query.title={query}&rows=3"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    crossref_url,
                    headers={"User-Agent": "SpineGraphRAG/1.0 (mailto:contact@example.com)"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.debug(f"CrossRef API returned status {response.status}")
                        return None

                    data = await response.json()
                    items = data.get("message", {}).get("items", [])

                    if not items:
                        logger.debug("CrossRef returned no results")
                        return None

                    # 가장 관련성 높은 결과 선택
                    best_match = None
                    best_score = 0

                    for item in items:
                        item_title = " ".join(item.get("title", []))
                        score = self._title_similarity(title, item_title)

                        # 연도가 일치하면 보너스
                        if year and item.get("published-print"):
                            pub_year = item["published-print"].get("date-parts", [[None]])[0][0]
                            if pub_year == year:
                                score += 0.2

                        if score > best_score:
                            best_score = score
                            best_match = item

                    if best_match and best_score > 0.6:
                        # 서지 정보 추출
                        result = {
                            "source": "crossref",
                            "confidence": best_score,
                            "doi": best_match.get("DOI"),
                            "title": " ".join(best_match.get("title", [])),
                        }

                        # 저자 정보
                        crossref_authors = best_match.get("author", [])
                        if crossref_authors:
                            result["authors"] = [
                                f"{a.get('family', '')}, {a.get('given', '')}"
                                for a in crossref_authors
                            ]

                        # 출판사
                        if best_match.get("publisher"):
                            result["publisher"] = best_match["publisher"]

                        # 연도
                        if best_match.get("published-print"):
                            date_parts = best_match["published-print"].get("date-parts", [[None]])
                            if date_parts and date_parts[0]:
                                result["year"] = date_parts[0][0]
                        elif best_match.get("published-online"):
                            date_parts = best_match["published-online"].get("date-parts", [[None]])
                            if date_parts and date_parts[0]:
                                result["year"] = date_parts[0][0]

                        # 저널/컨테이너
                        if best_match.get("container-title"):
                            result["journal"] = best_match["container-title"][0] if best_match["container-title"] else None

                        # ISBN (책인 경우)
                        if best_match.get("ISBN"):
                            result["isbn"] = best_match["ISBN"][0] if best_match["ISBN"] else None

                        # 문서 유형
                        result["document_type"] = best_match.get("type", "unknown")

                        logger.info(f"[web_search] CrossRef found: {result.get('title', '')[:50]}... (score={best_score:.2f})")
                        return result

                    logger.debug(f"CrossRef best match score too low: {best_score:.2f}")
                    return None

        except asyncio.TimeoutError:
            logger.warning("[web_search] CrossRef API timeout")
            return None
        except Exception as e:
            logger.warning(f"[web_search] CrossRef API error: {e}")
            return None

    def _title_similarity(self, title1: str, title2: str) -> float:
        """제목 유사도 계산 (간단한 Jaccard 유사도)."""
        if not title1 or not title2:
            return 0.0

        # 소문자 변환 및 단어 분리
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        # 불용어 제거
        stopwords = {"a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with"}
        words1 -= stopwords
        words2 -= stopwords

        if not words1 or not words2:
            return 0.0

        # Jaccard 유사도
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    async def _save_analyze_text_json(
        self,
        paper_id: str,
        title: str,
        year: int,
        journal: str,
        authors: list[str],
        doi: Optional[str],
        pmid: Optional[str],
        extracted_data: dict,
        pubmed_metadata=None,
        web_search_result: Optional[dict] = None,
    ) -> None:
        """analyze_text 결과를 JSON 파일로 저장.

        PDF 처리 및 PubMed import와 동일하게 data/extracted/ 폴더에 저장합니다.

        Args:
            paper_id: 문서 ID
            title: 제목
            year: 출판 연도
            journal: 저널명
            authors: 저자 목록
            doi: DOI
            pmid: PubMed ID
            extracted_data: LLM 추출 데이터
            pubmed_metadata: PubMed enrichment 결과 (선택)
            web_search_result: 웹 검색 결과 (선택)
        """
        import json
        import re
        from pathlib import Path

        # data/extracted 폴더 확인
        extracted_dir = Path("data/extracted")
        extracted_dir.mkdir(parents=True, exist_ok=True)

        # 파일명 생성: {year}_{first_author}_{title}.json
        first_author = ""
        if authors:
            # "Kim, J." → "Kim"
            first_author = authors[0].split(",")[0].strip() if authors else ""
            first_author = re.sub(r"[^\w\s-]", "", first_author)

        # 제목 정리 (특수문자 제거, 공백 → 언더스코어)
        clean_title = re.sub(r"[^\w\s-]", "", title)
        clean_title = re.sub(r"\s+", "_", clean_title)[:50]

        filename = f"{year}_{first_author}_{clean_title}.json"
        filepath = extracted_dir / filename

        # 메타데이터 구성
        metadata = {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "pmid": pmid,
        }

        # PubMed 서지 정보 추가
        if pubmed_metadata:
            metadata["mesh_terms"] = pubmed_metadata.mesh_terms
            metadata["publication_types"] = pubmed_metadata.publication_types
            metadata["pubmed_enriched"] = True

        # 웹 검색 결과 추가
        if web_search_result:
            metadata["web_search"] = {
                "source": web_search_result.get("source"),
                "confidence": web_search_result.get("confidence"),
                "document_type": web_search_result.get("document_type"),
                "isbn": web_search_result.get("isbn"),
            }

        # 최종 데이터 구성
        save_data = {
            "paper_id": paper_id,
            "metadata": metadata,
            "summary": {
                "text": extracted_data.get("summary", ""),
                "word_count": extracted_data.get("summary_word_count", 0),
            },
            "document_type": extracted_data.get("document_type", "unknown"),
            "entities": extracted_data.get("entities", {}),
            "spine_metadata": extracted_data.get("spine_metadata", {}),
            "chunks": extracted_data.get("chunks", []),
            "processing_method": "analyze_text",
            "saved_at": datetime.now().isoformat(),
        }

        # JSON 저장
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[analyze_text] Saved extracted data to: {filepath}")

    # ========================================================================
    # v7.3 Store Pre-Analyzed Paper (Desktop/Code Analysis Support)
    # ========================================================================

    async def store_analyzed_paper(
        self,
        title: str,
        abstract: str,
        year: int,
        interventions: list[str],
        outcomes: list[dict],
        pathologies: Optional[list[str]] = None,
        anatomy_levels: Optional[list[str]] = None,
        authors: Optional[list[str]] = None,
        journal: Optional[str] = None,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        evidence_level: Optional[str] = None,
        study_design: Optional[str] = None,
        sample_size: Optional[int] = None,
        summary: Optional[str] = None,
        sub_domain: Optional[str] = None,
        chunks: Optional[list[dict]] = None,
        patient_cohorts: Optional[list[dict]] = None,
        followups: Optional[list[dict]] = None,
        costs: Optional[list[dict]] = None,
        quality_metrics: Optional[list[dict]] = None,
    ) -> dict:
        """미리 분석된 논문 데이터를 Neo4j에 저장합니다.

        Claude Desktop 또는 Claude Code에서 PDF/텍스트를 직접 분석한 후,
        추출된 데이터를 이 도구로 전달하여 Neo4j에 저장합니다.
        LLM API 호출 없이 저장만 수행합니다.

        사용 시나리오:
        1. Claude Desktop에서 PDF 첨부 → 분석 → 이 도구로 저장
        2. Claude Code에서 텍스트 분석 → 이 도구로 저장
        3. PubMed에서 가져온 데이터 분석 → 이 도구로 저장

        Args:
            title: 논문 제목 (필수)
            abstract: 초록 또는 본문 요약 (필수)
            year: 출판년도 (필수)
            interventions: 수술법/중재 목록 (필수), 예: ["TLIF", "PLIF"]
            outcomes: 결과변수 목록 (필수), 예: [{"name": "ODI", "value": "28.5", "p_value": 0.001, "direction": "improved"}]
            pathologies: 질환 목록, 예: ["Lumbar Stenosis", "Spondylolisthesis"]
            anatomy_levels: 해부학적 위치, 예: ["L4-L5", "L5-S1"]
            authors: 저자 목록, 예: ["Kim J", "Park S"]
            journal: 저널명
            doi: DOI
            pmid: PubMed ID
            evidence_level: 근거 수준 ("1a", "1b", "2a", "2b", "3", "4", "5")
            study_design: 연구 설계 ("RCT", "Cohort", "Case-Control" 등)
            sample_size: 샘플 크기
            summary: 700+ word 종합 요약
            sub_domain: 척추 하위 도메인 ("Degenerative", "Deformity", "Trauma" 등)
            chunks: 청크 목록, 예: [{"content": "...", "section_type": "results", "tier": 1}]
            patient_cohorts: v7.2 환자 코호트 데이터
            followups: v7.2 추적관찰 데이터
            costs: v7.2 비용 분석 데이터
            quality_metrics: v7.2 품질 평가 데이터

        Returns:
            저장 결과 (paper_id, nodes_created, relationships_created 등)
        """
        import uuid
        from datetime import datetime

        # 1. 입력 검증
        if not title:
            return {"success": False, "error": "title은 필수입니다."}
        if not abstract or len(abstract) < 50:
            return {"success": False, "error": "abstract은 최소 50자 이상 필요합니다."}
        if not year or year < 1900 or year > 2100:
            return {"success": False, "error": "year는 1900-2100 사이여야 합니다."}
        if not interventions:
            return {"success": False, "error": "interventions 목록은 필수입니다."}
        if not outcomes:
            return {"success": False, "error": "outcomes 목록은 필수입니다."}

        # 2. Paper ID 생성
        if pmid:
            paper_id = f"pubmed_{pmid}"
        else:
            short_uuid = str(uuid.uuid4())[:8]
            paper_id = f"analyzed_{short_uuid}"

        logger.info(f"Storing pre-analyzed paper: {title[:50]}... (paper_id={paper_id})")

        # 3. Neo4j 연결 확인
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        if not self.relationship_builder:
            return {"success": False, "error": "RelationshipBuilder not initialized"}

        # 4. GraphSpineMetadata 생성
        try:
            # GraphSpineMetadata already imported at module level

            # outcomes 형식 변환
            formatted_outcomes = []
            for o in outcomes:
                if isinstance(o, dict):
                    formatted_outcomes.append({
                        "name": o.get("name", ""),
                        "value": o.get("value"),
                        "p_value": o.get("p_value"),
                        "direction": o.get("direction", ""),
                        "effect_size": o.get("effect_size", ""),
                    })
                else:
                    formatted_outcomes.append({"name": str(o)})

            graph_spine_meta = GraphSpineMetadata(
                sub_domain=sub_domain or "Unknown",
                sub_domains=[sub_domain] if sub_domain else [],
                anatomy_levels=anatomy_levels or [],
                interventions=interventions,
                pathologies=pathologies or [],
                outcomes=formatted_outcomes,
                surgical_approach=[],
                pico_population=None,
                pico_intervention=interventions[0] if interventions else None,
                pico_comparison=interventions[1] if len(interventions) > 1 else None,
                pico_outcome=", ".join([o.get("name", "") for o in formatted_outcomes if o.get("name")]),  # singular, not plural
                main_conclusion=summary[:500] if summary else None,
                summary=summary or "",
                processing_version="v7.3_store_analyzed",
                # v7.2 Extended entities
                patient_cohorts=patient_cohorts or [],
                followups=followups or [],
                costs=costs or [],
                quality_metrics=quality_metrics or [],
            )

            # 5. RelationshipBuilder로 Neo4j에 저장 (v7.5: 멀티유저 지원)
            from dataclasses import dataclass, field as df

            # ExtractedMetadata 호환 객체 생성
            @dataclass
            class ExtractedMetaCompat:
                title: str = ""
                authors: list = df(default_factory=list)
                year: int = 0
                journal: str = ""
                doi: str = ""
                pmid: str = ""
                study_type: str = ""
                study_design: str = ""
                evidence_level: str = ""
                sample_size: int = 0
                centers: str = ""
                blinding: str = ""
                abstract: str = ""
                spine: any = None

            meta_compat = ExtractedMetaCompat(
                title=title,
                authors=authors or [],
                year=year,
                journal=journal or "Unknown",
                doi=doi,
                pmid=pmid or "",
                study_design=study_design or "",
                evidence_level=evidence_level or "unknown",
                sample_size=sample_size or 0,
                abstract=abstract,
                spine=graph_spine_meta,
            )

            neo4j_result = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=meta_compat,
                spine_metadata=graph_spine_meta,
                chunks=[],  # store_analyzed_data는 청크 별도 처리
                owner=self.current_user,
                shared=True
            )

            logger.info(f"Neo4j relationships built: {neo4j_result.nodes_created} nodes, {neo4j_result.relationships_created} relationships")

        except Exception as e:
            logger.exception(f"Neo4j storage failed: {e}")
            return {"success": False, "error": f"Neo4j 저장 실패: {str(e)}"}

        # 6. 청크 저장 (선택)
        chunks_created = 0
        if chunks and self.neo4j_client:
            try:
                from core.embedding import OpenAIEmbeddingGenerator

                embedding_gen = OpenAIEmbeddingGenerator()

                # 청크 텍스트 추출
                chunk_texts = [c.get("content", "") for c in chunks if c.get("content")]

                if chunk_texts:
                    # v7.14.3: 기존 Chunk 삭제 (중복 방지)
                    await self._delete_existing_chunks(paper_id)

                    # 임베딩 생성
                    embeddings = embedding_gen.embed_batch(chunk_texts)

                    # Neo4j에 청크 저장
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                        chunk_id = f"{paper_id}_chunk_{i}"

                        chunk_content = chunk.get("content", "")
                        chunk_tier = chunk.get("tier", 2)
                        chunk_section = chunk.get("section_type", "body")

                        await self.neo4j_client.run_query(
                            """
                            MATCH (p:Paper {paper_id: $paper_id})
                            CREATE (c:Chunk {
                                chunk_id: $chunk_id,
                                content: $content,
                                tier: $tier,
                                section: $section,
                                embedding: $embedding
                            })
                            CREATE (p)-[:HAS_CHUNK]->(c)
                            """,
                            {
                                "paper_id": paper_id,
                                "chunk_id": chunk_id,
                                "content": chunk_content,
                                "tier": chunk_tier,
                                "section": chunk_section,
                                "embedding": embedding
                            }
                        )
                        chunks_created += 1

                    logger.info(f"Stored {chunks_created} chunks with embeddings to Neo4j")

            except Exception as e:
                logger.warning(f"Chunk storage failed: {e}")

        # 7. 결과 반환
        return {
            "success": True,
            "paper_id": paper_id,
            "title": title,
            "processing_method": "store_analyzed_paper",
            "stored_metadata": {
                "title": title,
                "year": year,
                "journal": journal,
                "authors": authors,
                "doi": doi,
                "pmid": pmid,
                "evidence_level": evidence_level,
                "study_design": study_design,
                "sample_size": sample_size,
                "sub_domain": sub_domain,
                "interventions": interventions,
                "pathologies": pathologies,
                "anatomy_levels": anatomy_levels,
                "outcomes_count": len(outcomes),
            },
            "neo4j_result": {
                "nodes_created": neo4j_result.nodes_created if neo4j_result else 0,
                "relationships_created": neo4j_result.relationships_created if neo4j_result else 0,
                "warnings": neo4j_result.warnings if neo4j_result else [],
            },
            "stats": {
                "abstract_length": len(abstract),
                "chunks_created": chunks_created,
                "storage_backend": "neo4j",
                "v72_entities": {
                    "patient_cohorts": len(patient_cohorts) if patient_cohorts else 0,
                    "followups": len(followups) if followups else 0,
                    "costs": len(costs) if costs else 0,
                    "quality_metrics": len(quality_metrics) if quality_metrics else 0,
                }
            }
        }

    # ========================================================================
    # v7.2 Extended Entity Query Methods
    # ========================================================================

    async def get_patient_cohorts(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        cohort_type: Optional[str] = None,
        min_sample_size: Optional[int] = None
    ) -> dict:
        """환자 코호트 정보 조회 (v7.2)."""
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            # 동적 필터 구성
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if cohort_type:
                where_clauses.append("c.cohort_type = $cohort_type")
                params["cohort_type"] = cohort_type

            if min_sample_size:
                where_clauses.append("c.sample_size >= $min_sample_size")
                params["min_sample_size"] = min_sample_size

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                # 수술법으로 필터링 - TREATED_WITH 관계 사용
                cypher = f"""
                MATCH (p:Paper)-[:HAS_COHORT]->(c:PatientCohort)-[:TREATED_WITH]->(i:Intervention {{name: $intervention}})
                WHERE {where_clause}
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       c.name AS cohort_name, c.cohort_type AS cohort_type,
                       c.sample_size AS sample_size, c.mean_age AS mean_age,
                       c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
                       c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
                       c.BMI AS bmi, i.name AS intervention
                ORDER BY c.sample_size DESC
                LIMIT 50
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:HAS_COHORT]->(c:PatientCohort)
                WHERE {where_clause}
                OPTIONAL MATCH (c)-[:TREATED_WITH]->(i:Intervention)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       c.name AS cohort_name, c.cohort_type AS cohort_type,
                       c.sample_size AS sample_size, c.mean_age AS mean_age,
                       c.female_percentage AS female_percentage, c.diagnosis AS diagnosis,
                       c.comorbidities AS comorbidities, c.ASA_score AS asa_score,
                       c.BMI AS bmi, collect(i.name) AS interventions
                ORDER BY c.sample_size DESC
                LIMIT 50
                """

            records = await self.neo4j_client.run_query(cypher, params)

            cohorts = []
            for r in records:
                cohorts.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "cohort_name": r.get("cohort_name"),
                    "cohort_type": r.get("cohort_type"),
                    "sample_size": r.get("sample_size"),
                    "mean_age": r.get("mean_age"),
                    "female_percentage": r.get("female_percentage"),
                    "diagnosis": r.get("diagnosis"),
                    "comorbidities": r.get("comorbidities"),
                    "asa_score": r.get("asa_score"),
                    "bmi": r.get("bmi"),
                    "intervention": r.get("intervention") or r.get("interventions"),
                })

            return {
                "success": True,
                "total_cohorts": len(cohorts),
                "cohorts": cohorts,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "cohort_type": cohort_type,
                    "min_sample_size": min_sample_size,
                }
            }

        except Exception as e:
            logger.error(f"get_patient_cohorts failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_followup_data(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        min_months: Optional[int] = None,
        max_months: Optional[int] = None
    ) -> dict:
        """추적관찰 데이터 조회 (v7.2)."""
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if min_months:
                where_clauses.append("f.timepoint_months >= $min_months")
                params["min_months"] = min_months

            if max_months:
                where_clauses.append("f.timepoint_months <= $max_months")
                params["max_months"] = max_months

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                cypher = f"""
                MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention {{name: $intervention}})
                MATCH (p)-[:HAS_FOLLOWUP]->(f:FollowUp)
                WHERE {where_clause}
                OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
                       f.completeness_rate AS completeness_rate,
                       collect(DISTINCT o.name) AS outcomes
                ORDER BY f.timepoint_months
                LIMIT 100
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:HAS_FOLLOWUP]->(f:FollowUp)
                WHERE {where_clause}
                OPTIONAL MATCH (f)-[:REPORTS_OUTCOME]->(o:Outcome)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       f.name AS timepoint_name, f.timepoint_months AS timepoint_months,
                       f.completeness_rate AS completeness_rate,
                       collect(DISTINCT o.name) AS outcomes
                ORDER BY f.timepoint_months
                LIMIT 100
                """

            records = await self.neo4j_client.run_query(cypher, params)

            followups = []
            for r in records:
                followups.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "timepoint_name": r.get("timepoint_name"),
                    "timepoint_months": r.get("timepoint_months"),
                    "completeness_rate": r.get("completeness_rate"),
                    "outcomes": r.get("outcomes") or [],
                })

            return {
                "success": True,
                "total_followups": len(followups),
                "followups": followups,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "min_months": min_months,
                    "max_months": max_months,
                }
            }

        except Exception as e:
            logger.error(f"get_followup_data failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_cost_analysis(
        self,
        paper_id: Optional[str] = None,
        intervention: Optional[str] = None,
        cost_type: Optional[str] = None
    ) -> dict:
        """비용 효과 분석 데이터 조회 (v7.2)."""
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if cost_type:
                where_clauses.append("cost.cost_type = $cost_type")
                params["cost_type"] = cost_type

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            if intervention:
                cypher = f"""
                MATCH (p:Paper)-[:REPORTS_COST]->(cost:Cost)-[:ASSOCIATED_WITH]->(i:Intervention {{name: $intervention}})
                WHERE {where_clause}
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       cost.name AS cost_name, cost.cost_type AS cost_type,
                       cost.mean_cost AS mean_cost, cost.currency AS currency,
                       cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
                       cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
                       i.name AS intervention
                ORDER BY cost.mean_cost DESC
                LIMIT 50
                """
                params["intervention"] = intervention
            else:
                cypher = f"""
                MATCH (p:Paper)-[:REPORTS_COST]->(cost:Cost)
                WHERE {where_clause}
                OPTIONAL MATCH (cost)-[:ASSOCIATED_WITH]->(i:Intervention)
                RETURN p.paper_id AS paper_id, p.title AS paper_title,
                       cost.name AS cost_name, cost.cost_type AS cost_type,
                       cost.mean_cost AS mean_cost, cost.currency AS currency,
                       cost.QALY_gained AS qaly_gained, cost.ICER AS icer,
                       cost.LOS_days AS los_days, cost.readmission_rate AS readmission_rate,
                       collect(i.name) AS interventions
                ORDER BY cost.mean_cost DESC
                LIMIT 50
                """

            records = await self.neo4j_client.run_query(cypher, params)

            costs = []
            for r in records:
                costs.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "cost_name": r.get("cost_name"),
                    "cost_type": r.get("cost_type"),
                    "mean_cost": r.get("mean_cost"),
                    "currency": r.get("currency"),
                    "qaly_gained": r.get("qaly_gained"),
                    "icer": r.get("icer"),
                    "los_days": r.get("los_days"),
                    "readmission_rate": r.get("readmission_rate"),
                    "intervention": r.get("intervention") or r.get("interventions"),
                })

            return {
                "success": True,
                "total_cost_records": len(costs),
                "costs": costs,
                "filters": {
                    "paper_id": paper_id,
                    "intervention": intervention,
                    "cost_type": cost_type,
                }
            }

        except Exception as e:
            logger.error(f"get_cost_analysis failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_quality_metrics(
        self,
        paper_id: Optional[str] = None,
        assessment_tool: Optional[str] = None,
        min_rating: Optional[str] = None
    ) -> dict:
        """연구 품질 평가 지표 조회 (v7.2)."""
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j not connected"}

        try:
            where_clauses = []
            params = {}

            if paper_id:
                where_clauses.append("p.paper_id = $paper_id")
                params["paper_id"] = paper_id

            if assessment_tool:
                where_clauses.append("q.assessment_tool = $assessment_tool")
                params["assessment_tool"] = assessment_tool

            if min_rating:
                # 품질 등급 필터: high > moderate > low > very low
                rating_order = {"high": 4, "moderate": 3, "low": 2, "very low": 1}
                min_order = rating_order.get(min_rating, 0)
                where_clauses.append("""
                CASE q.overall_rating
                    WHEN 'high' THEN 4
                    WHEN 'moderate' THEN 3
                    WHEN 'low' THEN 2
                    WHEN 'very low' THEN 1
                    ELSE 0
                END >= $min_order
                """)
                params["min_order"] = min_order

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            cypher = f"""
            MATCH (p:Paper)-[:HAS_QUALITY_METRIC]->(q:QualityMetric)
            WHERE {where_clause}
            RETURN p.paper_id AS paper_id, p.title AS paper_title,
                   q.name AS metric_name, q.assessment_tool AS assessment_tool,
                   q.overall_score AS overall_score, q.overall_rating AS overall_rating,
                   q.domain_scores AS domain_scores
            ORDER BY q.overall_score DESC
            LIMIT 50
            """

            records = await self.neo4j_client.run_query(cypher, params)

            metrics = []
            for r in records:
                metrics.append({
                    "paper_id": r.get("paper_id"),
                    "paper_title": r.get("paper_title"),
                    "metric_name": r.get("metric_name"),
                    "assessment_tool": r.get("assessment_tool"),
                    "overall_score": r.get("overall_score"),
                    "overall_rating": r.get("overall_rating"),
                    "domain_scores": r.get("domain_scores"),
                })

            return {
                "success": True,
                "total_metrics": len(metrics),
                "quality_metrics": metrics,
                "filters": {
                    "paper_id": paper_id,
                    "assessment_tool": assessment_tool,
                    "min_rating": min_rating,
                }
            }

        except Exception as e:
            logger.error(f"get_quality_metrics failed: {e}")
            return {"success": False, "error": str(e)}

    async def search(
        self,
        query: str,
        top_k: int = 5,
        tier_strategy: str = "tier1_then_tier2",
        prefer_original: bool = True,
        min_evidence_level: Optional[str] = None
    ) -> dict:
        """검색 수행 (v7.14.18: SearchHandler로 위임).

        Args:
            query: 검색 쿼리
            top_k: 결과 수
            tier_strategy: 검색 전략 (tier1_only, tier1_then_tier2, all_tiers)
            prefer_original: 원본 우선 여부
            min_evidence_level: 최소 근거 수준

        Returns:
            검색 결과 딕셔너리
        """
        if self.search_handler:
            return await self.search_handler.search(
                query=query,
                top_k=top_k,
                tier_strategy=tier_strategy,
                prefer_original=prefer_original,
                min_evidence_level=min_evidence_level
            )
        return {"success": False, "error": "SearchHandler not initialized"}

    async def reason(
        self,
        question: str,
        max_hops: int = 3,
        include_conflicts: bool = True
    ) -> dict:
        """추론 기반 답변 생성 (v7.14.18: ReasoningHandler로 위임).

        Args:
            question: 질문
            max_hops: 최대 추론 홉
            include_conflicts: 상충 포함 여부

        Returns:
            추론 결과 딕셔너리
        """
        if self.reasoning_handler:
            return await self.reasoning_handler.reason(
                question=question,
                max_hops=max_hops,
                include_conflicts=include_conflicts
            )
        return {"success": False, "error": "ReasoningHandler not initialized"}

    async def add_json(
        self,
        file_path: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """미리 추출된 JSON 파일을 RAG 시스템에 추가합니다 (v5.3 Neo4j 전용).

        LLM 호출 없이 직접 Neo4j에 저장합니다.
        data/extracted/ 폴더의 JSON 또는 직접 만든 JSON 사용 가능.

        Args:
            file_path: JSON 파일 경로
            metadata: 추가 메타데이터 (덮어쓰기용)

        Returns:
            처리 결과 딕셔너리
        """
        import json
        from dataclasses import dataclass, field

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"파일이 존재하지 않습니다: {file_path}"}

        if path.suffix.lower() != ".json":
            return {"success": False, "error": f"JSON 파일만 지원합니다: {path.suffix}"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                extracted_data = json.load(f)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON 파싱 실패: {e}"}

        # JSON 구조 검증
        if "metadata" not in extracted_data or "chunks" not in extracted_data:
            return {
                "success": False,
                "error": "JSON에 'metadata'와 'chunks' 필드가 필요합니다."
            }

        # v7.14.27: None 값 처리
        meta_dict = extracted_data.get("metadata") or {}
        spine_dict = extracted_data.get("spine_metadata") or {}
        chunks_list = extracted_data.get("chunks") or []
        integrated_citations = extracted_data.get("important_citations") or []

        # 문서 ID 생성
        pdf_metadata = {
            "title": meta_dict.get("title", ""),
            "authors": meta_dict.get("authors", []),
            "year": meta_dict.get("year", 0),
            "journal": meta_dict.get("journal", ""),
            "doi": meta_dict.get("doi", ""),
            "first_author": meta_dict.get("authors", [""])[0].split()[-1] if meta_dict.get("authors") else ""
        }
        doc_id = self._generate_document_id(pdf_metadata, path.stem)

        # 메타데이터 병합
        merged_metadata = {
            **pdf_metadata,
            **(metadata or {}),
            "original_filename": path.name,
            "study_type": meta_dict.get("study_type", ""),
            "evidence_level": meta_dict.get("evidence_level", ""),
            "processing_method": "json_import",
            "source_json": str(path)
        }

        logger.info(f"Importing JSON: {path.name}, doc_id={doc_id}, chunks={len(chunks_list)}")

        # TextChunk로 변환 및 저장 (add_pdf와 동일한 로직)
        chunks = []
        for i, chunk_dict in enumerate(chunks_list):
            # v3.0 통계 형식으로 변환
            stats_p_value = ""
            stats_is_significant = False
            stats_additional = ""
            has_stats = False

            if chunk_dict.get("statistics"):
                stats = chunk_dict["statistics"]
                # v3.0 형식 (p_value, is_significant, additional)
                if "p_value" in stats:
                    stats_p_value = str(stats.get("p_value", ""))
                    stats_is_significant = bool(stats.get("is_significant", False))
                    stats_additional = str(stats.get("additional", ""))
                    has_stats = bool(stats_p_value)
                # 구버전 형식 (p_values 배열) 호환
                elif "p_values" in stats:
                    p_values = stats.get("p_values", [])
                    if p_values:
                        stats_p_value = str(p_values[0]) if p_values else ""
                        try:
                            stats_is_significant = float(stats_p_value.replace("<", "").replace("=", "")) < 0.05
                        except (ValueError, TypeError):
                            stats_is_significant = False
                    additional_parts = []
                    if stats.get("effect_sizes"):
                        additional_parts.append(f"Effect: {', '.join(stats['effect_sizes'])}")
                    if stats.get("confidence_intervals"):
                        additional_parts.append(f"CI: {', '.join(stats['confidence_intervals'])}")
                    stats_additional = "; ".join(additional_parts)
                    has_stats = bool(p_values or stats.get("effect_sizes"))

            section_type = chunk_dict.get("section_type", "")
            is_key_finding = chunk_dict.get("is_key_finding", False)
            tier = "tier1" if section_type in ["abstract", "conclusion", "key_finding"] or is_key_finding else "tier2"

            # v3.0 TextChunk 생성 (PICO 제거, 새 statistics 형식)
            chunk = TextChunk(
                chunk_id=f"{doc_id}_{i:03d}",
                content=chunk_dict.get("content", ""),
                document_id=doc_id,
                tier=tier,
                section=section_type,
                source_type="original",
                evidence_level=meta_dict.get("evidence_level", "5"),
                publication_year=meta_dict.get("year", 0),
                title=meta_dict.get("title", ""),
                authors=meta_dict.get("authors", []),
                metadata=merged_metadata,
                # LLM 추출 메타데이터 (v3.0)
                summary=chunk_dict.get("summary", "") or chunk_dict.get("topic_summary", ""),
                keywords=chunk_dict.get("keywords", []) if isinstance(chunk_dict.get("keywords"), list) else [],
                # PICO 제거됨 (v3.0) - Neo4j PaperNode에서 조회
                # 통계 정보 (v3.0 간소화)
                statistics_p_value=stats_p_value,
                statistics_is_significant=stats_is_significant,
                statistics_additional=stats_additional,
                has_statistics=has_stats,
                llm_processed=True,
                llm_confidence=0.8,
                is_key_finding=is_key_finding,
            )
            chunks.append(chunk)

        # v5.3: ChromaDB 제거됨 - Neo4j만 사용
        logger.info(f"JSON import: {len(chunks)}개 청크 준비 완료")

        # Neo4j에 저장
        neo4j_result = {"nodes_created": 0, "relationships_created": 0}
        if self.neo4j_client:
            try:
                neo4j_result = await self._store_to_neo4j(
                    doc_id=doc_id,
                    meta_dict=meta_dict,
                    spine_dict=spine_dict,
                    chunks_list=chunks_list
                )
            except Exception as e:
                logger.warning(f"Neo4j 저장 실패: {e}")

        # 인용 처리
        citations_result = None
        if integrated_citations and self.citation_processor:
            try:
                citations_result = await self.citation_processor.process_from_integrated_citations(
                    citing_paper_id=doc_id,
                    citations=integrated_citations
                )
                logger.info(f"인용 처리: {citations_result.papers_created}개 논문, {citations_result.relationships_created}개 관계")
            except Exception as e:
                logger.warning(f"인용 처리 실패: {e}")

        return {
            "success": True,
            "document_id": doc_id,
            "title": meta_dict.get("title", "Unknown"),
            "chunks_count": len(chunks),
            "source": "json_import",
            "json_file": str(path),
            "neo4j": neo4j_result,
            "citations": {
                "papers_created": citations_result.papers_created if citations_result else 0,
                "relationships_created": citations_result.relationships_created if citations_result else 0
            } if citations_result else None
        }

    async def export_document(self, document_id: str) -> dict:
        """저장된 문서를 JSON으로 내보냅니다 (v7.14.18: DocumentHandler로 위임).

        Args:
            document_id: 내보낼 문서 ID

        Returns:
            내보내기 결과
        """
        if self.document_handler:
            return await self.document_handler.export_document(document_id)
        return {"success": False, "error": "DocumentHandler not initialized"}

    async def prepare_pdf_prompt(self, file_path: str) -> dict:
        """PDF에서 텍스트를 추출하고 분석용 프롬프트를 반환합니다.

        Claude 앱에서 직접 PDF를 분석할 수 있도록 프롬프트를 생성합니다.
        LLM API 호출 없이 PDF 텍스트만 추출하여 반환합니다.

        워크플로우:
        1. prepare_pdf_prompt → 프롬프트 + PDF 텍스트 반환
        2. Claude 앱에서 직접 분석 수행
        3. add_json으로 결과 저장

        Args:
            file_path: PDF 파일의 절대 경로

        Returns:
            프롬프트와 PDF 텍스트가 포함된 딕셔너리
        """
        import fitz  # pymupdf

        path = Path(file_path)

        if not path.exists():
            return {"success": False, "error": f"파일 없음: {file_path}"}

        if not path.suffix.lower() == ".pdf":
            return {"success": False, "error": "PDF 파일이 아닙니다"}

        try:
            # PDF 텍스트 추출
            doc = fitz.open(str(path))
            full_text = ""
            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                if page_text.strip():
                    full_text += f"\n--- PAGE {page_num} ---\n{page_text}"
            doc.close()

            if not full_text.strip():
                return {"success": False, "error": "PDF에서 텍스트를 추출할 수 없습니다."}

            # JSON 스키마 및 프롬프트 생성
            extraction_prompt = '''You are a medical research paper analyst specializing in spine surgery literature.
Analyze the following PDF text and extract ALL important information in a structured JSON format.

## JSON SCHEMA

{
  "metadata": {
    "title": "Paper title",
    "authors": ["Author 1", "Author 2"],
    "year": 2024,
    "journal": "Journal name",
    "doi": "",
    "pmid": "",
    "abstract": "Complete original abstract text (REQUIRED)",
    "study_type": "meta-analysis/systematic-review/RCT/prospective-cohort/retrospective-cohort/case-control/case-series/case-report/expert-opinion",
    "study_design": "randomized/non-randomized/single-arm/multi-arm",
    "evidence_level": "1a/1b/2a/2b/3/4/5",
    "sample_size": 100,
    "centers": "single-center/multi-center",
    "blinding": "none/single-blind/double-blind/open-label"
  },
  "spine_metadata": {
    "sub_domain": "Degenerative/Deformity/Trauma/Tumor/Infection/Basic Science",
    "anatomy_level": "L4-5",
    "anatomy_region": "cervical/thoracic/lumbar/sacral/thoracolumbar/lumbosacral",
    "pathology": ["Disease 1", "Disease 2"],
    "interventions": ["Surgery 1", "Surgery 2"],
    "comparison_type": "vs_conventional/vs_other_mis/vs_conservative/single_arm",
    "follow_up_months": 24,
    "main_conclusion": "Brief conclusion in 1-2 sentences",
    "outcomes": [
      {
        "name": "VAS",
        "category": "pain/function/radiologic/complication/satisfaction/quality_of_life",
        "baseline": 7.2,
        "final": 2.1,
        "value_intervention": "2.1 ± 0.8",
        "value_control": "3.5 ± 1.2",
        "value_difference": "-1.4",
        "p_value": "0.001",
        "confidence_interval": "95% CI: -2.1 to -0.7",
        "effect_size": "Cohen's d = 0.8",
        "timepoint": "preop/postop/1mo/3mo/6mo/1yr/2yr/final",
        "is_significant": true,
        "direction": "improved/worsened/unchanged"
      }
    ],
    "complications": [
      {
        "name": "Dural tear",
        "incidence_intervention": "2.5%",
        "incidence_control": "4.1%",
        "p_value": "0.35",
        "severity": "minor/major/revision_required"
      }
    ]
  },
  "important_citations": [
    {
      "authors": ["Kim", "Park"],
      "year": 2023,
      "context": "supports_result/contradicts_result/comparison",
      "section": "discussion/results/introduction",
      "citation_text": "Original sentence containing the citation",
      "importance_reason": "Why this citation is important",
      "outcome_comparison": "VAS/ODI/fusion_rate",
      "direction_match": true
    }
  ],
  "chunks": [
    {
      "content": "Chunk text content (200-500 chars for text, complete for tables)",
      "content_type": "text/table/figure/key_finding",
      "section_type": "abstract/introduction/methods/results/discussion/conclusion",
      "tier": "tier1/tier2",
      "is_key_finding": false,
      "topic_summary": "One sentence summary",
      "keywords": ["keyword1", "keyword2"],
      "pico": {
        "population": "",
        "intervention": "",
        "comparison": "",
        "outcome": ""
      },
      "statistics": {
        "p_values": [],
        "effect_sizes": [],
        "confidence_intervals": []
      }
    }
  ]
}

## CRITICAL INSTRUCTIONS

1. **METADATA**: Extract title, authors, year, journal, DOI, PMID, abstract (REQUIRED)
2. **EVIDENCE LEVEL**: 1a=Meta-analysis, 1b=RCT, 2a=Cohort review, 2b=Cohort, 3=Case-control, 4=Case series, 5=Expert opinion
3. **SPINE METADATA**: Extract sub_domain, anatomy, pathology, interventions, outcomes with ALL statistics
4. **CHUNKS**: Create 15-25 chunks (tier1=abstract/results/conclusion, tier2=intro/methods/discussion)
5. **TABLES**: Extract COMPLETE table data - DO NOT summarize or omit any rows
6. **STATISTICS**: Extract exact p-values, CIs, effect sizes - these are CRITICAL
7. **CITATIONS**: Extract important citations that support/contradict results

Return ONLY valid JSON, no additional text.'''

            # 사용자 안내 메시지
            usage_guide = """
## 📋 사용 방법

아래 프롬프트와 PDF 텍스트를 복사하여 Claude 앱에서 분석하세요.
분석 결과로 받은 JSON을 `add_json` 도구로 저장할 수 있습니다.

### 방법 1: 직접 복사-붙여넣기
1. 아래 "prompt" 내용을 Claude 앱에 붙여넣기
2. "pdf_text" 내용을 이어서 붙여넣기
3. Claude의 JSON 응답을 파일로 저장
4. `add_json` 도구로 저장: add_json(file_path="저장한파일.json")

### 방법 2: JSON 파일 직접 저장
분석 후 JSON을 data/extracted/ 폴더에 저장하면 add_json으로 로드 가능.

### JSON 저장 시 주의사항
- 파일명: {년도}_{저자}_{제목}.json 형식 권장
- 인코딩: UTF-8
- 형식: 위 스키마를 정확히 따를 것
"""

            return {
                "success": True,
                "file_name": path.name,
                "text_length": len(full_text),
                "page_count": len([1 for _ in fitz.open(str(path))]),
                "usage_guide": usage_guide,
                "prompt": extraction_prompt,
                "pdf_text": full_text,
                "next_step": "Claude 앱에서 분석 후 add_json으로 결과 저장"
            }

        except Exception as e:
            logger.exception(f"Error preparing PDF prompt: {e}")
            return {"success": False, "error": str(e)}

    async def list_documents(self) -> dict:
        """저장된 문서 목록 (v7.14.18: DocumentHandler로 위임)."""
        if self.document_handler:
            return await self.document_handler.list_documents()
        return {"success": False, "error": "DocumentHandler not initialized"}

    async def get_stats(self) -> dict:
        """시스템 통계 조회 (v7.14.18: DocumentHandler로 위임)."""
        if self.document_handler:
            return await self.document_handler.get_stats()
        return {
            "document_count": 0,
            "chunk_count": 0,
            "tier1_count": 0,
            "tier2_count": 0,
            "llm_enabled": self.enable_llm,
            "neo4j_available": False,
            "storage_backend": "neo4j"
        }

    async def delete_document(self, document_id: str) -> dict:
        """문서 삭제 (v7.14.18: DocumentHandler로 위임).

        Args:
            document_id: 삭제할 문서 ID

        Returns:
            삭제 결과 (neo4j_nodes, neo4j_relationships, deleted_chunks)
        """
        if self.document_handler:
            return await self.document_handler.delete_document(document_id)
        return {"success": False, "error": "DocumentHandler not initialized"}

    async def reset_database(self, include_taxonomy: bool = False) -> dict:
        """전체 데이터베이스 리셋 (v7.14.18: DocumentHandler로 위임).

        Args:
            include_taxonomy: Taxonomy도 삭제할지 여부 (기본값: False)

        Returns:
            리셋 결과
        """
        if self.document_handler:
            return await self.document_handler.reset_database(include_taxonomy)
        return {"success": False, "error": "DocumentHandler not initialized"}

    # ========== Knowledge Graph Tools ==========

    async def get_paper_relations(
        self,
        paper_id: str,
        relation_type: Optional[str] = None
    ) -> dict:
        """논문의 관계 정보 조회 (Neo4j 기반).

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형 필터 (SUPPORTS, CONTRADICTS, SIMILAR_TOPIC, CITES, EXTENDS, REPLICATES)

        Returns:
            관계 정보 딕셔너리
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j Graph Database not available"}

        try:
            # Ensure Neo4j is connected
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # 논문 정보 조회
            paper_result = await self.neo4j_client.get_paper(paper_id)
            if not paper_result:
                return {"success": False, "error": f"Paper not found: {paper_id}"}

            # Extract paper node from result
            paper = paper_result.get("p", {})

            # 관계 조회 (relation_type 필터 적용)
            relation_types = None
            if relation_type:
                # Validate and convert to uppercase
                valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
                rel_type_upper = relation_type.upper()
                if rel_type_upper in valid_types:
                    relation_types = [rel_type_upper]

            relations = await self.neo4j_client.get_paper_relations(
                paper_id,
                relation_types=relation_types,
                direction="both"
            )

            # 지지/상충/유사 논문 조회 (각각 최대 5개)
            supporting_results = await self.neo4j_client.get_supporting_papers(paper_id, limit=5)
            contradicting_results = await self.neo4j_client.get_contradicting_papers(paper_id, limit=5)
            similar_results = await self.neo4j_client.get_similar_papers(paper_id, limit=5)

            # Format results for UI compatibility
            supporting_papers = []
            for result in supporting_results:
                target = result.get("target", {})
                supporting_papers.append({
                    "id": target.get("paper_id", ""),
                    "title": target.get("title", ""),
                    "confidence": result.get("confidence", 0.0)
                })

            contradicting_papers = []
            for result in contradicting_results:
                target = result.get("target", {})
                contradicting_papers.append({
                    "id": target.get("paper_id", ""),
                    "title": target.get("title", ""),
                    "confidence": result.get("confidence", 0.0)
                })

            similar_papers = []
            for result in similar_results:
                target = result.get("target", {})
                similar_papers.append({
                    "id": target.get("paper_id", ""),
                    "title": target.get("title", ""),
                    "similarity": result.get("confidence", 0.0)
                })

            # Format relations
            formatted_relations = []
            for rel in relations:
                target = rel.get("target", {})
                formatted_relations.append({
                    "source": paper_id,
                    "target": target.get("paper_id", ""),
                    "type": rel.get("relation_type", ""),
                    "confidence": rel.get("confidence", 0.0),
                    "evidence": rel.get("evidence", ""),
                })

            return {
                "success": True,
                "paper": {
                    "id": paper.get("paper_id", ""),
                    "title": paper.get("title", ""),
                    "year": paper.get("year", 0),
                    "evidence_level": paper.get("evidence_level", ""),
                },
                "relations": formatted_relations,
                "supporting_papers": supporting_papers,
                "contradicting_papers": contradicting_papers,
                "similar_papers": similar_papers,
            }

        except Exception as e:
            logger.exception(f"Get paper relations error: {e}")
            return {"success": False, "error": str(e)}

    async def find_evidence_chain(
        self,
        claim: str,
        max_papers: int = 5
    ) -> dict:
        """주장을 뒷받침하는 논문 체인 찾기 (Neo4j 기반).

        claim에서 키워드를 추출하고 관련 논문과 AFFECTS 관계를 검색.

        Args:
            claim: 검증할 주장
            max_papers: 최대 논문 수

        Returns:
            증거 체인 정보
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j Graph Database not available"}

        try:
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # 1. Claim에서 Intervention/Outcome 키워드 추출 (간단한 방식)
            # 관련 논문 검색
            search_query = """
            MATCH (p:Paper)
            WHERE toLower(p.title) CONTAINS toLower($claim)
               OR toLower(p.abstract) CONTAINS toLower($claim)
            WITH p
            LIMIT $limit

            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
            OPTIONAL MATCH (i)-[r:AFFECTS]->(o:Outcome)
            WHERE r.source_paper_id = p.paper_id

            RETURN p.paper_id AS paper_id,
                   p.title AS title,
                   p.year AS year,
                   p.evidence_level AS evidence_level,
                   collect(DISTINCT {
                       intervention: i.name,
                       outcome: o.name,
                       direction: r.direction,
                       p_value: r.p_value,
                       is_significant: r.is_significant
                   }) AS evidence
            ORDER BY p.evidence_level, p.year DESC
            """

            results = await self.neo4j_client.run_query(
                search_query,
                {"claim": claim, "limit": max_papers * 2}
            )

            supporting = []
            refuting = []
            neutral = []

            for result in results[:max_papers]:
                paper_info = {
                    "paper_id": result.get("paper_id"),
                    "title": result.get("title"),
                    "year": result.get("year"),
                    "evidence_level": result.get("evidence_level"),
                    "evidence": [e for e in (result.get("evidence") or [])
                                if e.get("intervention")]
                }

                # 근거 분류 (direction 기반)
                directions = [e.get("direction") for e in paper_info["evidence"]
                             if e.get("direction")]
                if "improved" in directions or "decreased" in directions:
                    supporting.append(paper_info)
                elif "worsened" in directions or "increased risk" in directions:
                    refuting.append(paper_info)
                else:
                    neutral.append(paper_info)

            return {
                "success": True,
                "claim": claim,
                "supporting_papers": supporting,
                "refuting_papers": refuting,
                "neutral_papers": neutral,
                "total_papers": len(supporting) + len(refuting) + len(neutral),
            }

        except Exception as e:
            logger.exception(f"Find evidence chain error: {e}")
            return {"success": False, "error": str(e)}

    async def compare_papers(
        self,
        paper_ids: list[str]
    ) -> dict:
        """여러 논문 비교 분석 (Neo4j 기반).

        선택된 논문들의 메타데이터, Intervention, Outcome을 비교.

        Args:
            paper_ids: 비교할 논문 ID 목록

        Returns:
            비교 분석 결과
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j Graph Database not available"}

        if not paper_ids or len(paper_ids) < 2:
            return {"success": False, "error": "At least 2 paper IDs required for comparison"}

        try:
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # 각 논문의 상세 정보 조회
            query = """
            UNWIND $paper_ids AS pid
            MATCH (p:Paper {paper_id: pid})
            OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
            OPTIONAL MATCH (p)-[:INVOLVES]->(a:Anatomy)
            OPTIONAL MATCH (i)-[r:AFFECTS]->(o:Outcome)
            WHERE r.source_paper_id = p.paper_id

            RETURN p.paper_id AS paper_id,
                   p.title AS title,
                   p.year AS year,
                   p.evidence_level AS evidence_level,
                   p.sub_domain AS sub_domain,
                   p.study_type AS study_type,
                   p.sample_size AS sample_size,
                   collect(DISTINCT path.name) AS pathologies,
                   collect(DISTINCT i.name) AS interventions,
                   collect(DISTINCT a.level) AS anatomy_levels,
                   collect(DISTINCT {
                       intervention: i.name,
                       outcome: o.name,
                       direction: r.direction,
                       p_value: r.p_value,
                       is_significant: r.is_significant,
                       effect_size: r.effect_size
                   }) AS outcomes
            """

            results = await self.neo4j_client.run_query(query, {"paper_ids": paper_ids})

            papers = []
            all_interventions = set()
            all_outcomes = set()
            all_pathologies = set()

            for result in results:
                paper_info = {
                    "paper_id": result.get("paper_id"),
                    "title": result.get("title"),
                    "year": result.get("year"),
                    "evidence_level": result.get("evidence_level"),
                    "sub_domain": result.get("sub_domain"),
                    "study_type": result.get("study_type"),
                    "sample_size": result.get("sample_size"),
                    "pathologies": [p for p in (result.get("pathologies") or []) if p],
                    "interventions": [i for i in (result.get("interventions") or []) if i],
                    "anatomy_levels": [a for a in (result.get("anatomy_levels") or []) if a],
                    "outcomes": [o for o in (result.get("outcomes") or [])
                                if o.get("intervention")]
                }
                papers.append(paper_info)

                all_interventions.update(paper_info["interventions"])
                all_pathologies.update(paper_info["pathologies"])
                for o in paper_info["outcomes"]:
                    if o.get("outcome"):
                        all_outcomes.add(o["outcome"])

            # 공통점 및 차이점 분석
            common_interventions = set(papers[0]["interventions"]) if papers else set()
            common_pathologies = set(papers[0]["pathologies"]) if papers else set()

            for paper in papers[1:]:
                common_interventions &= set(paper["interventions"])
                common_pathologies &= set(paper["pathologies"])

            return {
                "success": True,
                "papers": papers,
                "comparison": {
                    "total_papers": len(papers),
                    "all_interventions": list(all_interventions),
                    "all_pathologies": list(all_pathologies),
                    "all_outcomes": list(all_outcomes),
                    "common_interventions": list(common_interventions),
                    "common_pathologies": list(common_pathologies),
                },
            }

        except Exception as e:
            logger.exception(f"Compare papers error: {e}")
            return {"success": False, "error": str(e)}

    async def get_topic_clusters(self) -> dict:
        """주제별 논문 클러스터 조회 (Neo4j 기반).

        Sub-domain 기반으로 논문을 그룹화하고,
        SIMILAR_TOPIC 관계가 있는 경우 추가 정보를 제공.

        Returns:
            클러스터 정보
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j Graph Database not available"}

        try:
            # Ensure Neo4j is connected
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # 1. Sub-domain 기반 클러스터링
            query = """
            MATCH (p:Paper)
            WHERE p.sub_domain IS NOT NULL AND p.sub_domain <> ''
            WITH p.sub_domain AS topic, collect({
                id: p.paper_id,
                title: p.title,
                year: p.year,
                evidence_level: p.evidence_level
            }) AS papers
            RETURN topic, papers, size(papers) AS count
            ORDER BY count DESC
            LIMIT 20
            """

            results = await self.neo4j_client.run_query(query)

            # 클러스터 정보 구성
            cluster_info = {}
            for result in results:
                topic = result.get("topic", "Unknown")
                papers = result.get("papers", [])
                count = result.get("count", 0)

                if topic and topic != "Unknown":
                    cluster_info[topic] = {
                        "count": count,
                        "papers": papers[:10]  # 클러스터당 최대 10개 논문
                    }

            # 2. SIMILAR_TOPIC 관계 통계 추가 (있는 경우)
            sim_query = """
            MATCH ()-[r:SIMILAR_TOPIC]->()
            RETURN count(r) AS similar_topic_count
            """
            sim_results = await self.neo4j_client.run_query(sim_query)
            similar_topic_count = 0
            if sim_results:
                similar_topic_count = sim_results[0].get("similar_topic_count", 0)

            # 3. Unknown sub_domain 논문 처리
            unknown_query = """
            MATCH (p:Paper)
            WHERE p.sub_domain IS NULL OR p.sub_domain = ''
            RETURN collect({
                id: p.paper_id,
                title: p.title,
                year: p.year
            })[0..10] AS papers, count(p) AS count
            """
            unknown_results = await self.neo4j_client.run_query(unknown_query)
            if unknown_results and unknown_results[0].get("count", 0) > 0:
                cluster_info["Unclassified"] = {
                    "count": unknown_results[0].get("count", 0),
                    "papers": unknown_results[0].get("papers", [])
                }

            return {
                "success": True,
                "cluster_count": len(cluster_info),
                "clusters": cluster_info,
                "similar_topic_relations": similar_topic_count,
            }

        except Exception as e:
            logger.exception(f"Get topic clusters error: {e}")
            return {"success": False, "error": str(e)}

    async def multi_hop_reason(
        self,
        question: str,
        start_paper_id: Optional[str] = None,
        max_hops: int = 3
    ) -> dict:
        """DEPRECATED: 여러 논문을 연결하는 Multi-hop 추론 (SQLite-based, removed).

        This method is no longer functional. Use Neo4j-based multi-hop reasoning instead.
        See src/solver/multi_hop_reasoning.py for Neo4j implementation.

        Args:
            question: 추론할 질문
            start_paper_id: 시작 논문 ID (None이면 전체에서 검색)
            max_hops: 최대 홉 수

        Returns:
            추론 결과
        """
        return {"success": False, "error": "Deprecated: Use Neo4j-based multi-hop reasoning (src/solver/multi_hop_reasoning.py)"}

    async def draft_with_citations(
        self,
        topic: str,
        section_type: str = "introduction",
        max_citations: int = 5,
        language: str = "korean"
    ) -> dict:
        """주제에 대해 자동으로 관련 논문을 검색하고 인용 가능한 형태로 반환.

        논문 작성 시 자동으로 DB에서 근거를 찾아 인용문과 함께 제공합니다.

        Args:
            topic: 작성할 주제 (예: "당뇨병에서 메트포르민의 효과")
            section_type: 섹션 유형 (introduction, methods, results, discussion, conclusion)
            max_citations: 최대 인용 수
            language: 출력 언어 (korean, english)

        Returns:
            인용 가능한 근거와 참고문헌 목록
        """
        try:
            # 1. 관련 논문 검색
            search_result = await self.search(
                query=topic,
                top_k=max_citations * 2,  # 여유있게 검색
                tier_strategy="tier1_first",
                prefer_original=True
            )

            if not search_result.get("success"):
                return {"success": False, "error": "검색 실패"}

            results = search_result.get("results", [])
            if not results:
                return {
                    "success": True,
                    "topic": topic,
                    "message": "관련 논문을 찾지 못했습니다. 더 많은 PDF를 추가해주세요.",
                    "citations": [],
                    "references": []
                }

            # 2. 인용 정보 구성
            citations = []
            references = []
            seen_docs = set()

            for i, result in enumerate(results):
                if len(citations) >= max_citations:
                    break

                doc_id = result.get("document_id", "")
                if doc_id in seen_docs:
                    continue
                seen_docs.add(doc_id)

                # 메타데이터에서 저자/연도 추출 (v7.14.27: None 값 처리)
                metadata = result.get("metadata") or {}
                authors = metadata.get("authors") or ["Unknown"]
                year = metadata.get("year", "n.d.")
                title = metadata.get("title", doc_id)

                # 첫 번째 저자 성 추출
                first_author = authors[0].split()[-1] if authors else "Unknown"
                et_al = " et al." if len(authors) > 1 else ""

                # 인용 키 생성
                citation_key = f"{first_author}{et_al}, {year}"

                # 관련 내용
                content = result.get("content", "")
                section = result.get("section", "")
                evidence_level = result.get("evidence_level", "")

                citation_entry = {
                    "citation_key": citation_key,
                    "citation_number": i + 1,
                    "content_summary": content[:500] + "..." if len(content) > 500 else content,
                    "section_type": section,
                    "evidence_level": evidence_level,
                    "relevance_score": result.get("score", 0),
                    "usage_suggestion": self._suggest_citation_usage(section_type, section, content, language)
                }
                citations.append(citation_entry)

                # 참고문헌 항목
                ref_entry = {
                    "number": i + 1,
                    "authors": authors,
                    "year": year,
                    "title": title,
                    "citation_key": citation_key,
                    "document_id": doc_id
                }
                references.append(ref_entry)

            # 3. 결과 구성
            if language == "korean":
                intro_text = f"'{topic}'에 대해 {len(citations)}개의 관련 논문을 찾았습니다."
            else:
                intro_text = f"Found {len(citations)} relevant papers for '{topic}'."

            return {
                "success": True,
                "topic": topic,
                "section_type": section_type,
                "message": intro_text,
                "citations": citations,
                "references": references,
                "usage_guide": self._get_citation_guide(section_type, language)
            }

        except Exception as e:
            logger.exception(f"Draft with citations error: {e}")
            return {"success": False, "error": str(e)}

    def _suggest_citation_usage(
        self,
        target_section: str,
        source_section: str,
        content: str,
        language: str
    ) -> str:
        """인용 사용 제안 생성."""
        suggestions = {
            "korean": {
                "introduction": {
                    "abstract": "배경 설명에 활용: '선행 연구에 따르면...'",
                    "results": "연구 필요성 근거로 활용: '기존 연구에서 ...가 보고되었다'",
                    "conclusion": "연구 동기 설명에 활용"
                },
                "discussion": {
                    "results": "결과 비교에 활용: '본 연구 결과는 ...와 일치한다'",
                    "abstract": "선행 연구와 비교: '...의 연구와 유사하게'",
                    "conclusion": "결론 뒷받침에 활용"
                },
                "results": {
                    "results": "유사 결과 참조: '이는 ...의 보고와 일치한다'",
                    "methods": "방법론 참조에 활용"
                }
            },
            "english": {
                "introduction": {
                    "abstract": "Use for background: 'Previous studies have shown...'",
                    "results": "Use as rationale: 'It has been reported that...'",
                    "conclusion": "Use to establish research motivation"
                },
                "discussion": {
                    "results": "Compare results: 'Our findings are consistent with...'",
                    "abstract": "Reference prior work: 'Similar to the findings of...'",
                    "conclusion": "Support conclusions"
                },
                "results": {
                    "results": "Reference similar findings: 'This is consistent with...'",
                    "methods": "Reference methodology"
                }
            }
        }

        lang_suggestions = suggestions.get(language, suggestions["english"])
        section_suggestions = lang_suggestions.get(target_section, {})
        return section_suggestions.get(source_section,
            "관련 근거로 활용 가능" if language == "korean" else "Can be used as supporting evidence")

    # ========== PubMed Tools ==========

    async def search_pubmed(
        self,
        query: str,
        max_results: int = 10,
        fetch_details: bool = True
    ) -> dict:
        """PubMed에서 논문 검색.

        Args:
            query: 검색 쿼리 (PubMed 문법 지원)
            max_results: 최대 결과 수
            fetch_details: 상세 정보 가져오기 여부

        Returns:
            검색 결과 딕셔너리
        """
        if not self.pubmed_client:
            return {"success": False, "error": "PubMed client not available"}

        try:
            # Search for PMIDs
            pmids = self.pubmed_client.search(query, max_results=max_results)

            if not pmids:
                return {
                    "success": True,
                    "query": query,
                    "total_found": 0,
                    "results": []
                }

            results = []
            if fetch_details:
                # Fetch paper details
                for pmid in pmids:
                    try:
                        paper = self.pubmed_client.fetch_paper_details(pmid)
                        results.append({
                            "pmid": paper.pmid,
                            "title": paper.title,
                            "authors": paper.authors[:5],  # First 5 authors
                            "year": paper.year,
                            "journal": paper.journal,
                            "abstract": paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract,
                            "mesh_terms": paper.mesh_terms[:10],
                            "doi": paper.doi,
                            "publication_types": paper.publication_types
                        })
                    except Exception as e:
                        logger.warning(f"Failed to fetch PMID {pmid}: {e}")
                        results.append({"pmid": pmid, "error": str(e)})
            else:
                results = [{"pmid": pmid} for pmid in pmids]

            return {
                "success": True,
                "query": query,
                "total_found": len(pmids),
                "results": results
            }

        except Exception as e:
            logger.exception(f"PubMed search error: {e}")
            return {"success": False, "error": str(e)}

    # ========== PubMed Bulk Processing Tools (v4.3) ==========

    async def pubmed_bulk_search(
        self,
        query: str,
        max_results: int = 50,
        import_results: bool = False,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        publication_types: Optional[list[str]] = None,
    ) -> dict:
        """PubMed 대량 검색 및 선택적 임포트.

        Args:
            query: PubMed 검색 쿼리
            max_results: 최대 결과 수 (기본 50, 최대 500)
            import_results: True면 검색 결과를 Neo4j에 자동 임포트 (v5.3)
            year_from: 시작 연도 필터
            year_to: 종료 연도 필터
            publication_types: 출판 유형 필터 (예: ["Randomized Controlled Trial", "Meta-Analysis"])

        Returns:
            검색 결과 및 임포트 결과 (선택 시)
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                # Initialize processor (v5.3: Neo4j 전용)
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # ChromaDB 제거됨
                    pubmed_email=os.environ.get("NCBI_EMAIL"),
                    pubmed_api_key=os.environ.get("NCBI_API_KEY"),
                )

                # Search PubMed
                papers = await processor.search_pubmed(
                    query=query,
                    max_results=min(max_results, 500),
                    year_from=year_from,
                    year_to=year_to,
                    publication_types=publication_types,
                )

                result = {
                    "success": True,
                    "query": query,
                    "total_found": len(papers),
                    "papers": [
                        {
                            "pmid": p.pmid,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.year,
                            "journal": p.journal,
                            "abstract": p.abstract[:300] + "..." if len(p.abstract or "") > 300 else p.abstract,
                            "mesh_terms": p.mesh_terms[:5],
                            "doi": p.doi,
                            "publication_types": p.publication_types,
                        }
                        for p in papers
                    ],
                }

                # Import if requested (v7.5: 멀티유저 지원)
                if import_results and papers:
                    import_summary = await processor.import_papers(
                        papers,
                        skip_existing=True,
                        owner=self.current_user,
                        shared=True
                    )
                    result["import_result"] = {
                        "imported": import_summary.imported,
                        "skipped": import_summary.skipped,
                        "failed": import_summary.failed,
                        "total_chunks": import_summary.total_chunks,
                    }

                return result

        except Exception as e:
            logger.exception(f"PubMed bulk search error: {e}")
            return {"success": False, "error": str(e)}

    async def hybrid_search(
        self,
        query: str,
        local_top_k: int = 10,
        pubmed_max_results: int = 20,
        min_local_results: int = 5,
        auto_import: bool = True,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> dict:
        """하이브리드 검색: 로컬 DB 우선 + PubMed 보완 (v7.14.24).

        1. 먼저 Neo4j에서 로컬 검색 (이미 분석된 논문 활용)
        2. 로컬 결과가 min_local_results 미만이면 PubMed에서 보완 검색
        3. 새로 찾은 논문은 자동 임포트 (선택)
        4. 로컬 + PubMed 결과 통합 반환

        Args:
            query: 검색 쿼리
            local_top_k: 로컬 검색 최대 결과 수 (기본 10)
            pubmed_max_results: PubMed 검색 최대 결과 수 (기본 20)
            min_local_results: 이 수 미만이면 PubMed 보완 (기본 5)
            auto_import: True면 새 논문 자동 임포트 (기본 True)
            year_from: PubMed 검색 시작 연도
            year_to: PubMed 검색 종료 연도

        Returns:
            통합 검색 결과
        """
        if self.pubmed_handler:
            return await self.pubmed_handler.hybrid_search(
                query=query,
                local_top_k=local_top_k,
                pubmed_max_results=pubmed_max_results,
                min_local_results=min_local_results,
                auto_import=auto_import,
                year_from=year_from,
                year_to=year_to,
            )
        return {"success": False, "error": "PubMed handler not available"}

    async def pubmed_import_citations(
        self,
        paper_id: str,
        min_confidence: float = 0.7,
    ) -> dict:
        """기존 논문의 important citations를 PubMed에서 검색하여 임포트.

        Args:
            paper_id: 원본 논문 ID (citations 추출 대상)
            min_confidence: 최소 매칭 신뢰도 (기본 0.7)

        Returns:
            임포트 결과
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # v5.3: ChromaDB 제거됨
                    pubmed_email=os.environ.get("NCBI_EMAIL"),
                    pubmed_api_key=os.environ.get("NCBI_API_KEY"),
                )

                # v7.5: 멀티유저 지원
                summary = await processor.import_from_citations(
                    paper_id=paper_id,
                    min_confidence=min_confidence,
                    owner=self.current_user,
                    shared=True,
                )

                return {
                    "success": True,
                    "paper_id": paper_id,
                    "total_citations_processed": summary.total_papers,
                    "imported": summary.imported,
                    "skipped": summary.skipped,
                    "failed": summary.failed,
                    "total_chunks": summary.total_chunks,
                    "results": [r.to_dict() for r in summary.results[:20]],  # Max 20 results
                }

        except Exception as e:
            logger.exception(f"PubMed citation import error: {e}")
            return {"success": False, "error": str(e)}

    async def upgrade_paper_with_pdf(
        self,
        paper_id: str,
        pdf_path: str,
    ) -> dict:
        """PubMed-only Paper를 PDF 데이터로 업그레이드.

        기존 PubMed에서 가져온 초록 기반 데이터를
        PDF에서 추출한 전문 데이터로 업그레이드합니다.

        Args:
            paper_id: 업그레이드할 paper ID (pubmed_xxx 형식)
            pdf_path: PDF 파일 경로

        Returns:
            업그레이드 결과
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        if not paper_id.startswith("pubmed_"):
            return {"success": False, "error": "Paper is not a PubMed-only paper (must start with 'pubmed_')"}

        # First, process the PDF using add_pdf
        pdf_result = await self.add_pdf(pdf_path)
        if not pdf_result.get("success"):
            return {"success": False, "error": f"PDF processing failed: {pdf_result.get('error')}"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # v5.3: ChromaDB 제거됨
                    pubmed_email=os.environ.get("NCBI_EMAIL"),
                    pubmed_api_key=os.environ.get("NCBI_API_KEY"),
                )

                upgrade_result = await processor.upgrade_with_pdf(
                    paper_id=paper_id,
                    pdf_result=pdf_result,
                )

                return {
                    "success": upgrade_result.get("success", False),
                    "paper_id": paper_id,
                    "upgraded_from": upgrade_result.get("upgraded_from"),
                    "upgraded_to": upgrade_result.get("upgraded_to"),
                    "preserved_pmid": upgrade_result.get("preserved_pmid"),
                    "new_chunks": upgrade_result.get("new_chunks", 0),
                    "error": upgrade_result.get("error"),
                }

        except Exception as e:
            logger.exception(f"Paper upgrade error: {e}")
            return {"success": False, "error": str(e)}

    async def get_abstract_only_papers(
        self,
        limit: int = 50,
    ) -> dict:
        """초록만 있는 논문(PubMed-only) 목록 조회.

        Args:
            limit: 최대 반환 수

        Returns:
            논문 목록
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # v5.3: ChromaDB 제거됨
                )

                papers = await processor.get_abstract_only_papers(limit=limit)

                return {
                    "success": True,
                    "count": len(papers),
                    "papers": papers,
                }

        except Exception as e:
            logger.exception(f"Get abstract-only papers error: {e}")
            return {"success": False, "error": str(e)}

    async def import_papers_by_pmids(
        self,
        pmids: list[str],
        max_concurrent: Optional[int] = None,
    ) -> dict:
        """PMID 목록으로 직접 논문 임포트.

        검색 결과에서 선택된 논문들을 직접 임포트합니다.
        재검색 없이 PMID로 직접 PubMed에서 상세 정보를 가져와 임포트합니다.

        Args:
            pmids: 임포트할 PMID 목록
            max_concurrent: 최대 동시 처리 수 (기본값: PUBMED_MAX_CONCURRENT 환경변수)

        Returns:
            임포트 결과 요약
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        if not pmids:
            return {"success": False, "error": "No PMIDs provided"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            # when called from Streamlit via run_async()
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # v5.3: ChromaDB 제거됨
                    pubmed_email=os.environ.get("NCBI_EMAIL"),
                    pubmed_api_key=os.environ.get("NCBI_API_KEY"),
                )

                # Fetch paper details by PMIDs
                papers = await processor._fetch_papers_batch(pmids)

                if not papers:
                    return {
                        "success": False,
                        "error": "Could not fetch paper details from PubMed",
                    }

                # Import the fetched papers (v7.5: 멀티유저, v7.14.23: 병렬 처리)
                # max_concurrent: None이면 환경변수에서 읽음
                if max_concurrent is None:
                    env_concurrent = int(os.environ.get("PUBMED_MAX_CONCURRENT", "5"))
                    safe_concurrent = max(1, min(env_concurrent, 10))
                else:
                    safe_concurrent = max(1, min(max_concurrent, 10))
                summary = await processor.import_papers(
                    papers,
                    source="search",
                    owner=self.current_user,
                    shared=True,
                    max_concurrent=safe_concurrent,
                )

                return {
                    "success": True,
                    "total_requested": len(pmids),
                    "total_fetched": len(papers),
                    "import_summary": summary.to_dict(),
                }

        except Exception as e:
            logger.exception(f"Import by PMIDs error: {e}")
            return {"success": False, "error": str(e)}

    async def get_pubmed_import_stats(self) -> dict:
        """PubMed 임포트 통계 조회.

        Returns:
            통계 정보
        """
        if not PUBMED_BULK_AVAILABLE:
            return {"success": False, "error": "PubMed Bulk Processor not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        try:
            # Create a fresh Neo4j client to avoid event loop conflicts
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as fresh_neo4j:
                processor = PubMedBulkProcessor(
                    neo4j_client=fresh_neo4j,
                    vector_db=None,  # v5.3: ChromaDB 제거됨
                )

                stats = await processor.get_import_statistics()

                return {
                    "success": True,
                    "statistics": stats,
                }

        except Exception as e:
            logger.exception(f"Get import stats error: {e}")
            return {"success": False, "error": str(e)}

    # ========================================================================
    # DOI Fulltext Methods (v7.12.2)
    # ========================================================================

    async def fetch_by_doi(
        self,
        doi: str,
        download_pdf: bool = False,
        import_to_graph: bool = False,
    ) -> dict:
        """DOI로 논문 메타데이터 및 전문 조회.

        Crossref/Unpaywall API를 사용하여 DOI로 논문 정보를 조회합니다.

        Args:
            doi: DOI (예: "10.1016/j.spinee.2024.01.001")
            download_pdf: PDF 다운로드 여부 (기본 False)
            import_to_graph: 그래프에 임포트 여부 (기본 False)

        Returns:
            조회 결과
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        try:
            fetcher = DOIFulltextFetcher()
            result = await fetcher.fetch(
                doi=doi,
                download_pdf=download_pdf,
                fetch_pmc=True,  # PMC도 시도
            )
            await fetcher.close()

            response = {
                "success": True,
                "doi": doi,
                "has_metadata": result.has_metadata,
                "has_fulltext": result.has_full_text,
                "source": result.source,
            }

            if result.metadata:
                response["metadata"] = {
                    "title": result.metadata.title,
                    "authors": result.metadata.authors,
                    "journal": result.metadata.journal,
                    "year": result.metadata.year,
                    "abstract": result.metadata.abstract[:500] if result.metadata.abstract else None,
                    "pmid": result.metadata.pmid,
                    "pmcid": result.metadata.pmcid,
                    "is_open_access": result.metadata.is_open_access,
                    "oa_status": result.metadata.oa_status,
                    "pdf_url": result.metadata.pdf_url,
                    "cited_by_count": result.metadata.cited_by_count,
                    "license_url": result.metadata.license_url,
                }

            if result.has_full_text:
                response["fulltext_preview"] = result.full_text[:1000] if result.full_text else None
                response["fulltext_length"] = len(result.full_text) if result.full_text else 0

            # 그래프 임포트 옵션
            if import_to_graph and result.metadata:
                import_result = await self._import_doi_to_graph(result)
                response["import_result"] = import_result

            return response

        except Exception as e:
            logger.exception(f"DOI fetch error: {e}")
            return {"success": False, "error": str(e), "doi": doi}

    async def get_doi_metadata(self, doi: str) -> dict:
        """DOI 메타데이터만 조회 (전문 없이).

        Args:
            doi: DOI

        Returns:
            메타데이터
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        try:
            fetcher = DOIFulltextFetcher()
            metadata = await fetcher.get_metadata_only(doi)
            await fetcher.close()

            if not metadata:
                return {"success": False, "error": f"No metadata found for DOI: {doi}"}

            return {
                "success": True,
                "doi": doi,
                "metadata": {
                    "title": metadata.title,
                    "authors": metadata.authors,
                    "journal": metadata.journal,
                    "year": metadata.year,
                    "volume": metadata.volume,
                    "issue": metadata.issue,
                    "pages": metadata.pages,
                    "abstract": metadata.abstract,
                    "publisher": metadata.publisher,
                    "issn": metadata.issn,
                    "subjects": metadata.subjects,
                    "pmid": metadata.pmid,
                    "pmcid": metadata.pmcid,
                    "is_open_access": metadata.is_open_access,
                    "oa_status": metadata.oa_status,
                    "pdf_url": metadata.pdf_url,
                    "cited_by_count": metadata.cited_by_count,
                    "references_count": metadata.references_count,
                    "license_url": metadata.license_url,
                }
            }

        except Exception as e:
            logger.exception(f"DOI metadata error: {e}")
            return {"success": False, "error": str(e), "doi": doi}

    async def import_by_doi(
        self,
        doi: str,
        fetch_fulltext: bool = True,
    ) -> dict:
        """DOI로 논문을 그래프에 임포트.

        Args:
            doi: DOI
            fetch_fulltext: 전문 조회 시도 여부

        Returns:
            임포트 결과
        """
        if not DOI_FETCHER_AVAILABLE:
            return {"success": False, "error": "DOI Fulltext Fetcher not available"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        try:
            fetcher = DOIFulltextFetcher()
            result = await fetcher.fetch(
                doi=doi,
                download_pdf=False,
                fetch_pmc=fetch_fulltext,
            )
            await fetcher.close()

            if not result.metadata:
                return {"success": False, "error": f"No metadata found for DOI: {doi}"}

            # 그래프 임포트
            import_result = await self._import_doi_to_graph(result)

            return {
                "success": True,
                "doi": doi,
                "import_result": import_result,
            }

        except Exception as e:
            logger.exception(f"DOI import error: {e}")
            return {"success": False, "error": str(e), "doi": doi}

    async def _import_doi_to_graph(self, doi_result: "DOIFullText") -> dict:
        """DOI 결과를 그래프에 임포트 (내부 메서드).

        Args:
            doi_result: DOI fetch 결과

        Returns:
            임포트 결과
        """
        if not doi_result.metadata:
            return {"success": False, "error": "No metadata to import"}

        meta = doi_result.metadata

        # paper_id 생성 (PMID 우선, 없으면 DOI 기반)
        if meta.pmid:
            paper_id = f"pubmed_{meta.pmid}"
        else:
            # DOI를 안전한 ID로 변환
            safe_doi = meta.doi.replace("/", "_").replace(".", "-")
            paper_id = f"doi_{safe_doi}"

        # 텍스트 결정 (전문 > 초록)
        text_to_analyze = ""
        text_source = "none"
        if doi_result.has_full_text and doi_result.full_text:
            text_to_analyze = doi_result.full_text
            text_source = "fulltext"
        elif meta.abstract:
            text_to_analyze = meta.abstract
            text_source = "abstract"

        # 기본 메타데이터 저장
        try:
            paper_data = {
                "paper_id": paper_id,
                "title": meta.title or "Unknown",
                "authors": meta.authors or [],
                "year": meta.year or 2024,
                "journal": meta.journal or "Unknown",
                "doi": meta.doi,
                "pmid": meta.pmid,
                "abstract": meta.abstract,
                "source": "doi_import",
                "is_open_access": meta.is_open_access,
                "oa_status": meta.oa_status,
            }

            # Neo4j에 Paper 노드 생성
            query = """
            MERGE (p:Paper {paper_id: $paper_id})
            SET p.title = $title,
                p.authors = $authors,
                p.year = $year,
                p.journal = $journal,
                p.doi = $doi,
                p.pmid = $pmid,
                p.abstract = $abstract,
                p.source = $source,
                p.is_open_access = $is_open_access,
                p.oa_status = $oa_status,
                p.created_at = datetime()
            RETURN p.paper_id as paper_id
            """
            await self.neo4j_client.run_query(query, paper_data)

            # v7.14.12: Abstract 임베딩 자동 생성
            if meta.abstract and len(meta.abstract.strip()) > 0:
                await self._generate_abstract_embedding(paper_id, meta.abstract)

            return {
                "success": True,
                "paper_id": paper_id,
                "text_source": text_source,
                "method": "basic_metadata",
            }

        except Exception as e:
            logger.exception(f"Graph import failed: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # v7.14.12: Abstract 임베딩 생성 헬퍼 메서드
    # =========================================================================

    async def _generate_abstract_embedding(
        self,
        paper_id: str,
        abstract: str
    ) -> bool:
        """Paper의 abstract 임베딩 생성 및 저장.

        Args:
            paper_id: Paper ID
            abstract: Abstract 텍스트

        Returns:
            성공 여부
        """
        try:
            import os
            from openai import OpenAI

            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # OpenAI 임베딩 생성 (3072차원)
            response = openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=abstract[:8000],
                dimensions=3072
            )

            embedding = response.data[0].embedding

            # Neo4j에 임베딩 저장
            await self.neo4j_client.run_write_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """,
                {"paper_id": paper_id, "embedding": embedding}
            )

            logger.debug(f"Abstract embedding generated for {paper_id}")
            return True

        except ImportError:
            logger.warning("OpenAI package not installed, skipping abstract embedding")
            return False
        except Exception as e:
            logger.warning(f"Failed to generate abstract embedding for {paper_id}: {e}")
            return False

    # =========================================================================
    # v7.14.3: 중복 Paper 체크 헬퍼 메서드
    # =========================================================================

    async def _check_existing_paper_by_pmid(self, pmid: str) -> Optional[str]:
        """PMID로 기존 Paper 확인.

        Args:
            pmid: PubMed ID

        Returns:
            기존 paper_id 또는 None
        """
        if not pmid or not self.neo4j_client:
            return None

        cypher = """
        MATCH (p:Paper)
        WHERE p.pmid = $pmid OR p.paper_id = $paper_id
        RETURN p.paper_id AS paper_id
        LIMIT 1
        """
        paper_id = f"pubmed_{pmid}"

        try:
            result = await self.neo4j_client.run_query(cypher, {
                "pmid": pmid,
                "paper_id": paper_id,
            })
            if result:
                return result[0].get("paper_id")
        except Exception as e:
            logger.warning(f"Error checking existing paper by PMID: {e}")

        return None

    async def _check_existing_paper_by_doi(self, doi: str) -> Optional[str]:
        """DOI로 기존 Paper 확인.

        Args:
            doi: Digital Object Identifier

        Returns:
            기존 paper_id 또는 None
        """
        if not doi or not self.neo4j_client:
            return None

        cypher = """
        MATCH (p:Paper)
        WHERE p.doi = $doi
        RETURN p.paper_id AS paper_id
        LIMIT 1
        """
        try:
            result = await self.neo4j_client.run_query(cypher, {"doi": doi})
            if result:
                return result[0].get("paper_id")
        except Exception as e:
            logger.warning(f"Error checking paper by DOI: {e}")

        return None

    async def _check_existing_paper_by_title(self, title: str) -> Optional[str]:
        """제목으로 기존 Paper 확인 (대소문자 무시).

        Args:
            title: 논문 제목

        Returns:
            기존 paper_id 또는 None
        """
        if not title or not self.neo4j_client:
            return None

        # 제목 정규화 (소문자, 앞뒤 공백 제거)
        normalized_title = title.lower().strip()

        cypher = """
        MATCH (p:Paper)
        WHERE toLower(trim(p.title)) = $normalized_title
        RETURN p.paper_id AS paper_id
        LIMIT 1
        """
        try:
            result = await self.neo4j_client.run_query(cypher, {"normalized_title": normalized_title})
            if result:
                return result[0].get("paper_id")
        except Exception as e:
            logger.warning(f"Error checking paper by title: {e}")

        return None

    async def _delete_existing_chunks(self, paper_id: str) -> int:
        """기존 Chunk 노드와 HAS_CHUNK 관계 삭제.

        Paper가 재처리될 때 기존 Chunk를 삭제하여 중복 방지.

        Args:
            paper_id: 논문 ID

        Returns:
            삭제된 Chunk 수
        """
        if not paper_id or not self.neo4j_client:
            return 0

        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})-[r:HAS_CHUNK]->(c:Chunk)
        WITH c, r
        DELETE r
        WITH c
        WHERE NOT exists((c)<-[:HAS_CHUNK]-())
        DELETE c
        RETURN count(*) AS deleted_count
        """
        try:
            result = await self.neo4j_client.run_query(cypher, {"paper_id": paper_id})
            deleted = result[0].get("deleted_count", 0) if result else 0
            if deleted > 0:
                logger.info(f"[v7.14.3] Deleted {deleted} existing chunks for {paper_id}")
            return deleted
        except Exception as e:
            logger.warning(f"Error deleting existing chunks: {e}")
            return 0

    async def find_conflicts(
        self,
        topic: str,
        document_ids: Optional[list[str]] = None
    ) -> dict:
        """특정 주제에 대한 연구 간 상충 탐지.

        Args:
            topic: 분석할 주제
            document_ids: 분석할 문서 ID 목록 (None이면 전체 검색)

        Returns:
            상충 분석 결과
        """
        try:
            # Search for relevant documents
            if document_ids:
                # Filter by specific documents (not fully implemented yet)
                search_result = await self.search(query=topic, top_k=20)
            else:
                search_result = await self.search(query=topic, top_k=20)

            if not search_result.get("success"):
                return search_result

            results = search_result.get("results", [])
            if len(results) < 2:
                return {
                    "success": True,
                    "topic": topic,
                    "message": "Not enough studies found for conflict detection",
                    "conflicts": []
                }

            # Use conflict detector
            from solver.conflict_detector import StudyResult as CDStudyResult
            from solver.multi_factor_ranker import EvidenceLevel

            study_results = []
            for r in results[:15]:  # Max 15 studies
                study = CDStudyResult(
                    study_id=r.get("document_id", "unknown"),
                    title=r.get("content", "")[:200],
                    evidence_level=self._parse_evidence_level(r.get("evidence_level", "5")),
                )
                study_results.append(study)

            conflict_input = ConflictInput(
                topic=topic,
                studies=study_results
            )
            conflict_output = self.conflict_detector.detect(conflict_input)

            conflicts = []
            for c in conflict_output.conflicts:
                conflicts.append({
                    "study1": {
                        "id": c.study1.study_id,
                        "title": c.study1.title
                    },
                    "study2": {
                        "id": c.study2.study_id,
                        "title": c.study2.title
                    },
                    "conflict_type": c.conflict_type.value if hasattr(c.conflict_type, 'value') else str(c.conflict_type),
                    "severity": c.severity.value if hasattr(c.severity, 'value') else str(c.severity),
                    "description": c.description if hasattr(c, 'description') else ""
                })

            return {
                "success": True,
                "topic": topic,
                "studies_analyzed": len(study_results),
                "has_conflicts": conflict_output.has_conflicts,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "summary": conflict_output.summary if hasattr(conflict_output, 'summary') else ""
            }

        except Exception as e:
            logger.exception(f"Find conflicts error: {e}")
            return {"success": False, "error": str(e)}

    def _parse_evidence_level(self, level_str: str):
        """Evidence level 문자열을 Enum으로 변환."""
        from solver.multi_factor_ranker import EvidenceLevel
        mapping = {
            "1a": EvidenceLevel.LEVEL_1A,
            "1b": EvidenceLevel.LEVEL_1B,
            "2a": EvidenceLevel.LEVEL_2A,
            "2b": EvidenceLevel.LEVEL_2B,
            "2c": EvidenceLevel.LEVEL_2C,
            "3a": EvidenceLevel.LEVEL_3A,
            "3b": EvidenceLevel.LEVEL_3B,
            "4": EvidenceLevel.LEVEL_4,
            "5": EvidenceLevel.LEVEL_5,
        }
        return mapping.get(str(level_str).lower(), EvidenceLevel.LEVEL_5)

    # ========== Neo4j Graph Tools (Spine GraphRAG v3) ==========

    async def graph_search(
        self,
        query: str,
        search_type: str = "evidence",
        limit: int = 20
    ) -> dict:
        """Neo4j 그래프 기반 검색 (v7.14.18: SearchHandler로 위임).

        Args:
            query: 자연어 검색 쿼리
            search_type: 검색 유형 (evidence|comparison|hierarchy|conflict)
            limit: 결과 개수 제한

        Returns:
            그래프 검색 결과
        """
        if self.search_handler:
            return await self.search_handler.graph_search(
                query=query,
                search_type=search_type,
                limit=limit
            )
        return {"success": False, "error": "SearchHandler not initialized"}

    async def get_intervention_hierarchy(
        self,
        intervention_name: str
    ) -> dict:
        """수술법 계층 구조 조회.

        Args:
            intervention_name: 수술법 이름 (예: "TLIF")

        Returns:
            계층 구조 정보 (부모, 자식, 동의어 포함)
        """
        if not GRAPH_AVAILABLE or not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            hierarchy = await self.graph_searcher.get_intervention_hierarchy(intervention_name)

            # Add aliases from entity normalizer
            try:
                from graph.entity_normalizer import get_normalizer
                normalizer = get_normalizer()

                aliases = []
                for alias, normalized in normalizer.INTERVENTION_ALIASES.items():
                    if normalized == intervention_name or alias == intervention_name:
                        aliases.append(alias)
            except Exception:
                aliases = []

            return {
                "success": True,
                "intervention": intervention_name,
                "full_name": hierarchy.get("full_name", ""),
                "category": hierarchy.get("category", ""),
                "approach": hierarchy.get("approach", ""),
                "is_minimally_invasive": hierarchy.get("is_minimally_invasive", False),
                "parents": hierarchy.get("parents", []),
                "children": hierarchy.get("children", []),
                "aliases": list(set(aliases))
            }

        except Exception as e:
            logger.exception(f"Get intervention hierarchy error: {e}")
            return {"success": False, "error": str(e)}

    async def find_evidence(
        self,
        intervention: str,
        outcome: str,
        direction: str = "improved"
    ) -> dict:
        """특정 수술법과 결과변수 관계의 근거 검색.

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름
            direction: 효과 방향 (improved|worsened|unchanged)

        Returns:
            근거 논문 목록 (p-value, effect size 포함)
        """
        if not GRAPH_AVAILABLE or not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            result = await self.graph_searcher.search_interventions_for_outcome(
                outcome_name=outcome,
                direction=direction,
                limit=50
            )

            # Build set of matching intervention names (include taxonomy children)
            matching_interventions = {intervention, intervention.upper(), intervention.lower()}

            # Get taxonomy children if available
            try:
                hierarchy = await self.neo4j_client.get_intervention_hierarchy(intervention)
                if hierarchy and hierarchy.get("children"):
                    matching_interventions.update(hierarchy["children"])
                # Also add aliases
                if hierarchy and hierarchy.get("aliases"):
                    matching_interventions.update(hierarchy["aliases"])
            except Exception:
                pass  # Taxonomy lookup failed, continue with exact match

            # Filter for matching interventions (exact or taxonomy-related)
            evidence = []
            for r in result.results:
                r_intervention = r.get("intervention", "")
                if r_intervention in matching_interventions or intervention.lower() in r_intervention.lower():
                    # Parse p_value safely (can be string like "<0.001" or None)
                    p_val = r.get("p_value")
                    is_sig = False
                    if p_val is not None:
                        if isinstance(p_val, (int, float)):
                            is_sig = p_val < 0.05
                        elif isinstance(p_val, str):
                            # Handle "<0.001", "0.01", etc.
                            p_str = p_val.replace("<", "").replace(">", "").strip()
                            try:
                                is_sig = float(p_str) < 0.05
                            except ValueError:
                                is_sig = "<" in p_val  # Assume "<X" means significant

                    evidence.append({
                        "intervention": r.get("intervention"),
                        "full_name": r.get("full_name"),
                        "outcome": outcome,
                        "value": r.get("value"),
                        "value_control": r.get("value_control"),
                        "p_value": r.get("p_value"),
                        "effect_size": r.get("effect_size"),
                        "confidence_interval": r.get("confidence_interval"),
                        "is_significant": is_sig,
                        "source_paper_id": r.get("source_paper_id")
                    })

            return {
                "success": True,
                "intervention": intervention,
                "outcome": outcome,
                "direction": direction,
                "evidence_count": len(evidence),
                "evidence": evidence
            }

        except Exception as e:
            logger.exception(f"Find evidence error: {e}")
            return {"success": False, "error": str(e)}

    async def compare_interventions(
        self,
        intervention1: str,
        intervention2: str,
        outcome: str
    ) -> dict:
        """두 수술법의 효과 비교.

        Args:
            intervention1: 첫 번째 수술법
            intervention2: 두 번째 수술법
            outcome: 비교할 결과변수

        Returns:
            비교 결과 (통계적 유의성 포함)
        """
        if not GRAPH_AVAILABLE or not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Get evidence for both interventions
            evidence1 = await self.find_evidence(intervention1, outcome)
            evidence2 = await self.find_evidence(intervention2, outcome)

            if not evidence1.get("success") or not evidence2.get("success"):
                return {
                    "success": False,
                    "error": "Failed to retrieve evidence for one or both interventions"
                }

            # Analyze comparison
            ev1_list = evidence1.get("evidence", [])
            ev2_list = evidence2.get("evidence", [])

            def parse_p_value(p_val):
                """Parse p_value to float, handling strings like '<0.001'."""
                if p_val is None:
                    return 1.0
                if isinstance(p_val, (int, float)):
                    return float(p_val)
                if isinstance(p_val, str):
                    p_str = p_val.replace("<", "").replace(">", "").strip()
                    try:
                        return float(p_str)
                    except ValueError:
                        return 0.001 if "<" in p_val else 1.0
                return 1.0

            def calc_avg_p_value(ev_list):
                """Calculate average p-value from evidence list."""
                if not ev_list:
                    return 1.0
                p_values = [parse_p_value(e.get("p_value")) for e in ev_list]
                return sum(p_values) / len(p_values)

            comparison = {
                "intervention1": {
                    "name": intervention1,
                    "evidence_count": len(ev1_list),
                    "avg_p_value": calc_avg_p_value(ev1_list),
                    "significant_studies": sum(1 for e in ev1_list if e.get("is_significant", False)),
                    "studies": ev1_list
                },
                "intervention2": {
                    "name": intervention2,
                    "evidence_count": len(ev2_list),
                    "avg_p_value": calc_avg_p_value(ev2_list),
                    "significant_studies": sum(1 for e in ev2_list if e.get("is_significant", False)),
                    "studies": ev2_list
                }
            }

            # Determine which has better evidence
            if comparison["intervention1"]["significant_studies"] > comparison["intervention2"]["significant_studies"]:
                comparison["recommendation"] = f"{intervention1} has more significant evidence"
            elif comparison["intervention2"]["significant_studies"] > comparison["intervention1"]["significant_studies"]:
                comparison["recommendation"] = f"{intervention2} has more significant evidence"
            else:
                comparison["recommendation"] = "Both interventions have similar evidence levels"

            return {
                "success": True,
                "outcome": outcome,
                "comparison": comparison
            }

        except Exception as e:
            logger.exception(f"Compare interventions error: {e}")
            return {"success": False, "error": str(e)}

    async def detect_conflicts(
        self,
        intervention: str,
        outcome: Optional[str] = None
    ) -> dict:
        """수술법의 상충 결과 탐지 (ConflictDetector 사용).

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름 (None이면 모든 결과변수)

        Returns:
            상충 결과 요약 (severity, papers involved, differing directions)
        """
        if not GRAPH_AVAILABLE or not self.neo4j_client:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # Use ConflictDetector from solver
            from solver.conflict_detector import ConflictDetector
            detector = ConflictDetector(self.neo4j_client)

            if outcome:
                # Detect conflicts for specific intervention-outcome pair
                conflict = await detector.detect_conflicts(intervention, outcome)

                if conflict:
                    return {
                        "success": True,
                        "intervention": intervention,
                        "outcome": outcome,
                        "has_conflicts": True,
                        "conflict": {
                            "severity": conflict.severity.value,
                            "confidence": conflict.confidence,
                            "paper_count": conflict.total_papers,
                            "papers_improved": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level,
                                    "p_value": p.p_value,
                                    "is_significant": p.is_significant
                                }
                                for p in conflict.papers_improved
                            ],
                            "papers_worsened": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level,
                                    "p_value": p.p_value,
                                    "is_significant": p.is_significant
                                }
                                for p in conflict.papers_worsened
                            ],
                            "papers_unchanged": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level
                                }
                                for p in conflict.papers_unchanged
                            ],
                            "summary": conflict.summary
                        }
                    }
                else:
                    return {
                        "success": True,
                        "intervention": intervention,
                        "outcome": outcome,
                        "has_conflicts": False,
                        "summary": f"No conflicts found for {intervention} → {outcome}"
                    }
            else:
                # Find all conflicts for intervention (all outcomes)
                from solver.conflict_detector import ConflictSeverity
                all_conflicts = await detector.find_all_conflicts(
                    min_severity=ConflictSeverity.MEDIUM
                )

                # Filter by intervention
                intervention_conflicts = [
                    c for c in all_conflicts
                    if c.intervention == intervention
                ]

                return {
                    "success": True,
                    "intervention": intervention,
                    "has_conflicts": len(intervention_conflicts) > 0,
                    "conflict_count": len(intervention_conflicts),
                    "conflicts": [
                        {
                            "outcome": c.outcome,
                            "severity": c.severity.value,
                            "confidence": c.confidence,
                            "improved_count": len(c.papers_improved),
                            "worsened_count": len(c.papers_worsened)
                        }
                        for c in intervention_conflicts
                    ],
                    "summary": f"Found {len(intervention_conflicts)} conflicting outcomes for {intervention}"
                }

        except Exception as e:
            logger.exception(f"Detect conflicts error: {e}")
            return {"success": False, "error": str(e)}

    async def synthesize_evidence(
        self,
        intervention: str,
        outcome: str,
        min_papers: int = 2
    ) -> dict:
        """근거 종합 (GRADE 방법론 기반).

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름
            min_papers: 최소 논문 수 (기본값: 2)

        Returns:
            GRADE rating, direction, strength, confidence interval, recommendation
        """
        if not GRAPH_AVAILABLE or not self.neo4j_client:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # Use EvidenceSynthesizer from solver
            from solver.evidence_synthesizer import EvidenceSynthesizer
            synthesizer = EvidenceSynthesizer(self.neo4j_client)

            result = await synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome,
                min_papers=min_papers
            )

            return {
                "success": True,
                "intervention": intervention,
                "outcome": outcome,
                "direction": result.direction,
                "strength": result.strength.value,
                "grade_rating": result.grade_rating,
                "paper_count": result.paper_count,
                "effect_summary": result.effect_summary,
                "confidence_interval": result.confidence_interval,
                "heterogeneity": result.heterogeneity,
                "recommendation": result.recommendation,
                "supporting_papers": result.supporting_papers,
                "opposing_papers": result.opposing_papers
            }

        except Exception as e:
            logger.exception(f"Synthesize evidence error: {e}")
            return {"success": False, "error": str(e)}

    async def get_comparable_interventions(
        self,
        intervention: str
    ) -> dict:
        """비교 가능한 수술법 목록 조회 (Taxonomy 기반).

        Args:
            intervention: 수술법 이름

        Returns:
            같은 부모를 가진 sibling interventions
        """
        if not GRAPH_AVAILABLE or not self.neo4j_client or not TaxonomyManager:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # Use TaxonomyManager
            taxonomy = TaxonomyManager(self.neo4j_client)

            # Get parents
            parents = await taxonomy.get_parent_interventions(intervention)

            if not parents:
                return {
                    "success": True,
                    "intervention": intervention,
                    "comparable_interventions": [],
                    "message": f"No parent category found for {intervention}"
                }

            # Get siblings (children of same parent)
            immediate_parent = parents[0] if parents else None
            if immediate_parent:
                siblings = await taxonomy.get_child_interventions(immediate_parent)
                # Remove the intervention itself
                comparable = [s for s in siblings if s != intervention]
            else:
                comparable = []

            return {
                "success": True,
                "intervention": intervention,
                "parent_category": immediate_parent,
                "all_parents": parents,
                "comparable_interventions": comparable,
                "count": len(comparable)
            }

        except Exception as e:
            logger.exception(f"Get comparable interventions error: {e}")
            return {"success": False, "error": str(e)}

    async def get_intervention_hierarchy_with_direction(
        self,
        intervention: str,
        direction: str = "both"
    ) -> dict:
        """수술법 계층 구조 조회 (방향 선택 가능).

        Args:
            intervention: 수술법 이름
            direction: "ancestors", "descendants", "both"

        Returns:
            계층 구조 정보 (부모/자식, 거리 포함)
        """
        if not GRAPH_AVAILABLE or not self.neo4j_client or not TaxonomyManager:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            taxonomy = TaxonomyManager(self.neo4j_client)

            result = {
                "success": True,
                "intervention": intervention
            }

            if direction in ["ancestors", "both"]:
                # Get all ancestors (parents)
                parents = await taxonomy.get_parent_interventions(intervention)
                result["ancestors"] = parents
                result["ancestor_count"] = len(parents)

            if direction in ["descendants", "both"]:
                # Get all descendants (children)
                children = await taxonomy.get_child_interventions(intervention)
                result["descendants"] = children
                result["descendant_count"] = len(children)

            # Get aliases from entity normalizer
            try:
                from graph.entity_normalizer import get_normalizer
                normalizer = get_normalizer()

                aliases = []
                for alias, normalized in normalizer.INTERVENTION_ALIASES.items():
                    if normalized == intervention or alias == intervention:
                        aliases.append(alias)
                result["aliases"] = list(set(aliases))
            except Exception:
                result["aliases"] = []

            return result

        except Exception as e:
            logger.exception(f"Get intervention hierarchy error: {e}")
            return {"success": False, "error": str(e)}

    async def adaptive_search(
        self,
        query: str,
        top_k: int = 10,
        include_synthesis: bool = True,
        detect_conflicts: bool = True
    ) -> dict:
        """통합 검색 파이프라인 (v7.14.18: SearchHandler로 위임).

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            include_synthesis: 근거 종합 포함 여부
            detect_conflicts: 충돌 탐지 포함 여부

        Returns:
            Full search response with adaptive ranking, synthesis, conflicts
        """
        if self.search_handler:
            return await self.search_handler.adaptive_search(
                query=query,
                top_k=top_k,
                include_synthesis=include_synthesis,
                detect_conflicts=detect_conflicts
            )
        return {"success": False, "error": "SearchHandler not initialized"}

    def _get_citation_guide(self, section_type: str, language: str) -> str:
        """섹션별 인용 가이드 반환."""
        guides = {
            "korean": {
                "introduction": """
## Introduction 작성 가이드
- 연구 배경과 필요성을 설명할 때 인용
- "...에 따르면" 또는 "...가 보고한 바와 같이" 형식 사용
- 최신 연구부터 인용하여 현재 연구 동향 설명
""",
                "methods": """
## Methods 작성 가이드
- 방법론의 근거를 제시할 때 인용
- "...의 방법을 참고하여" 형식 사용
""",
                "results": """
## Results 작성 가이드
- 결과 해석 시 비교 대상으로 인용
- "이는 ...의 결과와 일치한다" 형식 사용
""",
                "discussion": """
## Discussion 작성 가이드
- 결과를 선행 연구와 비교할 때 적극 인용
- 일치/불일치 여부와 그 이유 설명
- "본 연구 결과는 ...와 일치하며" 형식 사용
""",
                "conclusion": """
## Conclusion 작성 가이드
- 핵심 발견의 의의를 강조할 때 인용
- 향후 연구 방향 제시 시 참조
"""
            },
            "english": {
                "introduction": "Use citations to establish background and rationale.",
                "methods": "Cite methodological references.",
                "results": "Compare findings with cited studies.",
                "discussion": "Extensively compare with prior literature.",
                "conclusion": "Reinforce significance with key references."
            }
        }

        lang_guides = guides.get(language, guides["english"])
        return lang_guides.get(section_type, "")

    # ========== LLM Pipeline ==========

    async def _process_with_llm_pipeline(
        self,
        text: str,
        doc_id: str,
        metadata: dict,
        pdf_metadata: dict
    ) -> list[TextChunk]:
        """LLM 파이프라인으로 문서 처리.

        1. LLM 섹션 분류 (semantic)
        2. LLM 의미 청킹
        3. LLM 메타데이터 추출 (PICO, 통계 등)

        Args:
            text: 전체 문서 텍스트
            doc_id: 문서 ID
            metadata: 병합된 메타데이터
            pdf_metadata: PDF에서 추출된 메타데이터

        Returns:
            처리된 TextChunk 목록
        """
        import json

        chunks = []

        try:
            # 1. LLM 섹션 분류
            logger.info("Step 1: LLM Section Classification")
            section_boundaries = await self.llm_section_classifier.classify(text)
            logger.info(f"  Found {len(section_boundaries)} sections")

            # 2. LLM 의미 청킹
            logger.info("Step 2: LLM Semantic Chunking")
            semantic_chunks = await self.llm_chunker.chunk_document(section_boundaries, text, doc_id)
            logger.info(f"  Created {len(semantic_chunks)} semantic chunks")

            # 3. LLM 메타데이터 추출 (초록을 컨텍스트로 사용)
            logger.info("Step 3: LLM Metadata Extraction")
            abstract = self._get_abstract_from_sections(section_boundaries, text)

            # 청크 텍스트 추출
            chunk_texts = [c.content for c in semantic_chunks]

            # 배치 메타데이터 추출
            if self.llm_extractor:
                try:
                    metadata_list = await self.llm_extractor.extract_batch(
                        chunks=chunk_texts,
                        context=abstract
                    )
                    logger.info(f"  Extracted metadata for {len(metadata_list)} chunks")
                except Exception as e:
                    logger.warning(f"Metadata extraction failed: {e}")
                    metadata_list = [None] * len(semantic_chunks)
            else:
                metadata_list = [None] * len(semantic_chunks)

            # 4. TextChunk 객체로 변환 (v3.0 간소화)
            for i, (sem_chunk, chunk_meta) in enumerate(zip(semantic_chunks, metadata_list)):
                # Tier 결정 (섹션 기반)
                tier = self._determine_tier(sem_chunk.section_type)

                # 통계 정보 추출 (v3.0 간소화: p_value, is_significant, additional)
                stats_p_value = ""
                stats_is_significant = False
                stats_additional = ""
                has_stats = False

                if chunk_meta and hasattr(chunk_meta, 'statistics') and chunk_meta.statistics:
                    try:
                        stats = chunk_meta.statistics
                        if isinstance(stats, dict):
                            stats_p_value = str(stats.get('p_value', ''))
                            stats_is_significant = bool(stats.get('is_significant', False))
                            stats_additional = str(stats.get('additional', ''))
                        else:
                            stats_p_value = str(getattr(stats, 'p_value', ''))
                            stats_is_significant = bool(getattr(stats, 'is_significant', False))
                            stats_additional = str(getattr(stats, 'additional', ''))
                        has_stats = bool(stats_p_value or stats_is_significant)
                    except Exception:
                        pass

                # PICO 제거됨 (v3.0) - spine_metadata로 이동

                # summary 필드 (v3.0)
                chunk_summary = ""
                if chunk_meta and hasattr(chunk_meta, 'summary') and chunk_meta.summary:
                    chunk_summary = chunk_meta.summary
                elif hasattr(sem_chunk, 'topic_summary') and sem_chunk.topic_summary:
                    chunk_summary = sem_chunk.topic_summary  # 하위호환

                chunk = TextChunk(
                    chunk_id=f"{doc_id}_llm_chunk_{i}",
                    content=sem_chunk.content,
                    document_id=doc_id,
                    tier=tier,
                    section=sem_chunk.section_type,
                    source_type="original",  # LLM이 인용 감지하면 업데이트 가능
                    evidence_level=metadata.get("evidence_level", "5"),
                    publication_year=pdf_metadata.get("year", 0),
                    title=pdf_metadata.get("title", ""),
                    authors=pdf_metadata.get("authors", []),
                    metadata=metadata,
                    # LLM 추출 메타데이터 (v3.0)
                    summary=chunk_summary,
                    keywords=chunk_meta.keywords if chunk_meta else [],
                    # PICO 제거됨 (v3.0) - Neo4j PaperNode에서 조회
                    # 통계 정보 (v3.0 간소화)
                    statistics_p_value=stats_p_value,
                    statistics_is_significant=stats_is_significant,
                    statistics_additional=stats_additional,
                    has_statistics=has_stats,
                    llm_processed=True,
                    llm_confidence=0.8,  # LLM 처리됨
                    is_key_finding=chunk_meta.is_key_finding if chunk_meta else False,
                )
                chunks.append(chunk)

            logger.info(f"LLM pipeline completed: {len(chunks)} chunks created")

        except Exception as e:
            logger.error(f"LLM pipeline error: {e}")
            logger.info("Falling back to rule-based processing")
            # Fallback to rule-based processing
            sections = self._classify_sections(text)
            citation_info = self._detect_citations(text)
            study_info = self._classify_study(text)
            chunks = self._create_chunks(
                text=text,
                file_path="",
                sections=sections,
                citation_info=citation_info,
                study_info=study_info,
                metadata=metadata,
                doc_id=doc_id
            )

        return chunks

    def _get_abstract_from_sections(
        self,
        section_boundaries: list,
        full_text: str
    ) -> str:
        """섹션 경계에서 초록 추출."""
        for section in section_boundaries:
            if hasattr(section, 'section_type') and section.section_type.lower() == 'abstract':
                start = getattr(section, 'start_char', 0)
                end = getattr(section, 'end_char', min(2000, len(full_text)))
                return full_text[start:end]

        # 초록을 찾지 못한 경우 첫 2000자 반환
        return full_text[:2000]

    def _determine_tier(self, section_type: str) -> str:
        """섹션 타입에 따른 Tier 결정.

        NOTE: Tier 구분 제거됨 - 모든 청크는 tier1으로 처리.
        섹션 타입은 메타데이터로 유지됨.
        """
        # Tier 구분 제거 - 모든 청크를 단일 컬렉션(tier1)에 저장
        return "tier1"

    # ========== Helper Methods ==========

    def _extract_pdf_metadata(self, path: Path, text: str) -> dict:
        """PDF에서 메타데이터 추출 (저자, 연도, 제목, 저널).

        Args:
            path: PDF 파일 경로
            text: 추출된 텍스트

        Returns:
            메타데이터 딕셔너리 (authors, year, title, journal)
        """
        import re

        metadata = {
            "authors": [],
            "year": 0,
            "title": "",
            "journal": "",
            "first_author": ""
        }

        try:
            import fitz
            doc = fitz.open(str(path))

            # 1. PDF 내장 메타데이터에서 추출 시도
            pdf_meta = doc.metadata
            if pdf_meta:
                if pdf_meta.get("title"):
                    metadata["title"] = pdf_meta["title"]
                if pdf_meta.get("author"):
                    authors = pdf_meta["author"].split(",")
                    metadata["authors"] = [a.strip() for a in authors if a.strip()]
                if pdf_meta.get("creationDate"):
                    # D:20210315... 형식
                    date_str = pdf_meta["creationDate"]
                    year_match = re.search(r"D:(\d{4})", date_str)
                    if year_match:
                        metadata["year"] = int(year_match.group(1))

            doc.close()

            # 2. 텍스트에서 연도 추출 (메타데이터에 없는 경우)
            if metadata["year"] == 0:
                # 일반적인 논문 연도 패턴: (2020), 2020;, Published: 2020
                year_patterns = [
                    r'(?:published|received|accepted)[:\s]*(?:\w+\s+)?(\d{4})',
                    r'©?\s*(\d{4})\s+(?:Elsevier|Springer|Wiley|BMJ|JAMA)',
                    r'\b(20[0-2]\d)\b',  # 2000-2029
                    r'\b(19[89]\d)\b',   # 1980-1999
                ]
                for pattern in year_patterns:
                    match = re.search(pattern, text[:3000], re.IGNORECASE)
                    if match:
                        metadata["year"] = int(match.group(1))
                        break

            # 3. 텍스트에서 저자 추출 (첫 페이지에서)
            if not metadata["authors"]:
                first_page = text[:2000]
                # 일반적인 저자 패턴: Name1, Name2, and Name3
                # Kim JS, Park SM, Lee JH
                author_patterns = [
                    r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)?(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z]\.?)?){0,5})',
                    r'([A-Z][a-z]+\s+[A-Z]{1,2}(?:\s*,\s*[A-Z][a-z]+\s+[A-Z]{1,2}){0,5})',
                ]
                for pattern in author_patterns:
                    match = re.search(pattern, first_page, re.MULTILINE)
                    if match:
                        author_str = match.group(1)
                        authors = re.split(r',\s*|\s+and\s+', author_str)
                        metadata["authors"] = [a.strip() for a in authors if a.strip() and len(a.strip()) > 2]
                        break

            # 4. 텍스트에서 제목 추출 (없는 경우)
            if not metadata["title"]:
                # 첫 줄들에서 긴 문장을 제목으로 간주
                lines = text[:1500].split('\n')
                for line in lines[:10]:
                    line = line.strip()
                    # 제목 특성: 10-200자, 숫자로 시작하지 않음, 특수문자 적음
                    if 10 < len(line) < 200 and not line[0].isdigit():
                        if not re.search(r'[©®™]|Vol\.|Issue|doi:', line, re.IGNORECASE):
                            metadata["title"] = line
                            break

            # 5. 첫 번째 저자 추출
            if metadata["authors"]:
                first = metadata["authors"][0]
                # "Kim JS" -> "Kim", "John Smith" -> "Smith"
                parts = first.split()
                if len(parts) >= 1:
                    # 한국식: 성이 앞, 서양식: 성이 뒤
                    if len(parts[0]) <= 3:  # 짧으면 성
                        metadata["first_author"] = parts[0]
                    else:
                        metadata["first_author"] = parts[-1]

        except Exception as e:
            logger.warning(f"Metadata extraction error: {e}")

        # Fallback: 파일명에서 정보 추출
        if not metadata["title"]:
            metadata["title"] = path.stem

        return metadata

    def _generate_document_id(self, metadata: dict, fallback_name: str) -> str:
        """메타데이터에서 document_id 생성.

        형식: FirstAuthor_Year_TitleWords

        Args:
            metadata: 추출된 메타데이터
            fallback_name: 폴백 이름 (파일명)

        Returns:
            문서 ID 문자열
        """
        import re

        parts = []

        # 1. 첫 번째 저자
        if metadata.get("first_author"):
            author = metadata["first_author"]
            # 영문자만 유지
            author = re.sub(r'[^a-zA-Z]', '', author)
            if author:
                parts.append(author.capitalize())

        # 2. 연도
        if metadata.get("year") and metadata["year"] > 1900:
            parts.append(str(metadata["year"]))

        # 3. 제목에서 주요 단어 4개
        if metadata.get("title"):
            title = metadata["title"]
            # 불용어 제거
            stopwords = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with', 'by', 'from', 'at', 'is', 'are', 'was', 'were'}
            words = re.findall(r'[a-zA-Z]+', title)
            title_words = [w.capitalize() for w in words if w.lower() not in stopwords and len(w) > 2][:4]
            if title_words:
                parts.append('_'.join(title_words))

        # 결과 조합
        if len(parts) >= 2:
            doc_id = '_'.join(parts)
        else:
            # 폴백: 원래 파일명 사용
            doc_id = re.sub(r'[^a-zA-Z0-9_]', '_', fallback_name)

        # 길이 제한 및 정리
        doc_id = re.sub(r'_+', '_', doc_id)  # 중복 언더스코어 제거
        doc_id = doc_id.strip('_')
        doc_id = doc_id[:80]  # 최대 80자

        return doc_id

    def _extract_pdf_text(self, path: Path) -> str:
        """PDF에서 텍스트 추출."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            logger.warning("PyMuPDF not available, using placeholder")
            return f"[Placeholder text from {path.name}]"
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return ""

    def _classify_sections(self, text: str) -> list[dict]:
        """섹션 분류."""
        if BUILDER_AVAILABLE and hasattr(self, 'section_classifier'):
            try:
                from builder.section_classifier import SectionInput
                result = self.section_classifier.classify(SectionInput(text=text))
                return [{
                    "section": result.section,
                    "tier": f"tier{result.tier}",
                    "content": text,
                    "confidence": result.confidence,
                    "evidence": result.evidence
                }]
            except Exception as e:
                logger.warning(f"Section classification error: {e}")

        # Default sections
        return [{"section": "full_text", "tier": "tier1", "content": text}]

    def _detect_citations(self, text: str) -> list[dict]:
        """인용 감지."""
        if BUILDER_AVAILABLE and hasattr(self, 'citation_detector'):
            try:
                from builder.citation_detector import CitationInput
                result = self.citation_detector.detect(CitationInput(text=text))
                return [{
                    "source_type": result.source_type.value if hasattr(result.source_type, 'value') else str(result.source_type),
                    "confidence": result.confidence,
                    "original_ratio": result.original_ratio,
                    "citations": [
                        {
                            "marker": c.citation_marker,
                            "authors": c.authors,
                            "year": c.year
                        }
                        for c in result.citations
                    ]
                }]
            except Exception as e:
                logger.warning(f"Citation detection error: {e}")

        return [{"source_type": "original", "content": text}]

    def _classify_study(self, text: str) -> Optional[dict]:
        """연구 설계 분류."""
        if BUILDER_AVAILABLE and hasattr(self, 'study_classifier'):
            try:
                from builder.study_classifier import StudyInput
                result = self.study_classifier.classify(StudyInput(text=text))
                return {
                    "design": result.study_type.value if hasattr(result, 'study_type') else "unknown",
                    "evidence_level": result.evidence_level.value if hasattr(result, 'evidence_level') else "5"
                }
            except Exception as e:
                logger.warning(f"Study classification error: {e}")

        return None

    def _create_chunks(
        self,
        text: str,
        file_path: str,
        sections: list[dict],
        citation_info: list[dict],
        study_info: Optional[dict],
        metadata: dict,
        doc_id: Optional[str] = None
    ) -> list[TextChunk]:
        """청크 생성."""
        chunks = []
        if doc_id is None:
            doc_id = Path(file_path).stem

        # Simple chunking (512 characters)
        chunk_size = 512
        overlap = 50

        evidence_level = study_info.get("evidence_level", "5") if study_info else "5"

        for i in range(0, len(text), chunk_size - overlap):
            chunk_text = text[i:i + chunk_size]
            if not chunk_text.strip():
                continue

            # All chunks use single collection (tier distinction removed)
            tier = "tier1"

            # Determine source_type (simplified: first chunk is original)
            source_type = "original" if i == 0 else "background"

            chunk = TextChunk(
                chunk_id=f"{doc_id}_chunk_{i}",
                content=chunk_text,
                document_id=doc_id,
                tier=tier,
                section="full_text",
                source_type=source_type,
                evidence_level=evidence_level,
                publication_year=metadata.get("year", 0),
                title=metadata.get("title", doc_id),
                metadata=metadata
            )
            chunks.append(chunk)

        return chunks

    # OpenAI 임베딩 모델 설정 (v5.3.1 - MedTE에서 전환)
    EMBEDDING_MODEL = "text-embedding-3-large"
    EMBEDDING_DIM = 3072

    def _generate_embeddings(self, chunks: list[TextChunk]) -> list[list[float]]:
        """임베딩 생성 (OpenAI text-embedding-3-large 사용)."""
        # Initialize embedding model if not already done
        if not hasattr(self, '_embedding_model'):
            try:
                from core.embedding import OpenAIEmbeddingGenerator
                self._embedding_model = OpenAIEmbeddingGenerator()
                logger.info(f"OpenAI Embedding model loaded: {self.EMBEDDING_MODEL} ({self.EMBEDDING_DIM}d)")
            except Exception as e:
                logger.warning(f"Failed to load OpenAI embedding model: {e}")
                self._embedding_model = None

        if self._embedding_model is None:
            # Fallback to mock embeddings
            logger.warning("Using mock embeddings - search quality will be poor")
            return [[0.1] * self.EMBEDDING_DIM for _ in chunks]

        # Generate real embeddings using OpenAI
        texts = [chunk.content for chunk in chunks]
        embeddings = self._embedding_model.embed_batch(texts)
        return embeddings


# ========== MCP Server Setup ==========

def create_mcp_server(kag_server: MedicalKAGServer) -> Any:
    """MCP 서버 생성."""
    if not MCP_AVAILABLE:
        logger.error("MCP library not available")
        return None

    server = Server("medical-kag")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """8개 통합 도구 반환 (v7.4 - 38개 → 8개 통합).

        토큰 절감: ~4,800 tokens (63% 절감)
        기능 유지: 100% (action 파라미터로 기존 도구 기능 선택)
        """
        return [
            # 1. Document Management Tool
            Tool(
                name="document",
                description="문서 관리: PDF/JSON 추가, 목록 조회, 삭제, 내보내기, 데이터베이스 리셋. action으로 기능 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add_pdf", "add_pdf_v7", "add_json", "list", "delete", "export", "reset", "prepare_prompt"],
                            "description": "수행할 작업: add_pdf(PDF 추가), add_pdf_v7(v7 파이프라인), add_json(JSON 추가), list(목록), delete(삭제), export(내보내기), reset(리셋), prepare_prompt(프롬프트 생성)"
                        },
                        "file_path": {"type": "string", "description": "파일 경로 (add_pdf, add_pdf_v7, add_json, prepare_prompt)"},
                        "document_id": {"type": "string", "description": "문서 ID (delete, export)"},
                        "metadata": {"type": "object", "description": "추가 메타데이터"},
                        "use_vision": {"type": "boolean", "default": True, "description": "레거시 PDF 프로세서 사용 (add_pdf, v7.5에서는 fallback)"},
                        "use_v7": {"type": "boolean", "default": True, "description": "v7.5 Simplified Pipeline 사용 (add_pdf, 권장)"},
                        "document_type": {
                            "type": "string",
                            "enum": ["journal-article", "book", "book-section", "conference-paper", "thesis", "report", "preprint", "newspaper-article", "magazine-article", "blog-post", "webpage", "dataset", "software", "patent", "standard", "presentation", "video", "interview", "letter", "manuscript", "document"],
                            "description": "문서 유형 (add_pdf_v7, None=자동감지)"
                        },
                        "include_taxonomy": {"type": "boolean", "default": False, "description": "Taxonomy 삭제 여부 (reset)"}
                    },
                    "required": ["action"]
                }
            ),
            # 2. Search & Reasoning Tool (v7.14.25: 자동 하이브리드 검색)
            Tool(
                name="search",
                description="검색 및 추론: 벡터 검색(+PubMed 자동 보완), 그래프 검색, 적응형 검색, 근거 검색, 추론. action으로 검색 유형 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["search", "graph", "adaptive", "evidence", "reason"],
                            "description": "검색 유형: search(벡터+PubMed 자동), graph(그래프), adaptive(통합), evidence(근거), reason(추론)"
                        },
                        "query": {"type": "string", "description": "검색 쿼리"},
                        "question": {"type": "string", "description": "질문 (reason)"},
                        "intervention": {"type": "string", "description": "수술법 (evidence)"},
                        "outcome": {"type": "string", "description": "결과변수 (evidence)"},
                        "top_k": {"type": "integer", "default": 10, "description": "결과 수"},
                        "tier_strategy": {"type": "string", "enum": ["tier1_only", "tier1_then_tier2", "all_tiers"], "default": "tier1_then_tier2"},
                        "prefer_original": {"type": "boolean", "default": True},
                        "min_evidence_level": {"type": "string", "description": "최소 근거 수준"},
                        "search_type": {"type": "string", "enum": ["evidence", "comparison", "hierarchy", "conflict"], "default": "evidence"},
                        "direction": {"type": "string", "enum": ["improved", "worsened", "unchanged"], "default": "improved"},
                        "max_hops": {"type": "integer", "default": 3},
                        "include_conflicts": {"type": "boolean", "default": True},
                        "include_synthesis": {"type": "boolean", "default": True},
                        "detect_conflicts": {"type": "boolean", "default": True},
                        "limit": {"type": "integer", "default": 20},
                        "enable_pubmed_fallback": {"type": "boolean", "default": True, "description": "v7.14.25: 로컬 결과 부족 시 PubMed 자동 보완 (기본 True)"},
                        "min_local_results": {"type": "integer", "default": 5, "description": "v7.14.25: 이 수 미만이면 PubMed 보완 (기본 5)"},
                        "pubmed_max_results": {"type": "integer", "default": 20, "description": "v7.14.25: PubMed 검색 최대 결과 (기본 20)"},
                        "auto_import": {"type": "boolean", "default": True, "description": "v7.14.25: 새 논문 자동 임포트 (기본 True)"}
                    },
                    "required": ["action"]
                }
            ),
            # 3. PubMed Tool (DOI 기능 포함, v7.12.2)
            Tool(
                name="pubmed",
                description="PubMed/DOI 연동: 검색, 대량 검색, 인용 임포트, PMID 임포트, DOI 조회/임포트, PDF 업그레이드, 통계. action으로 기능 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["search", "bulk_search", "hybrid_search", "import_citations", "import_by_pmids", "fetch_by_doi", "doi_metadata", "import_by_doi", "upgrade_pdf", "get_abstract_only", "get_stats"],
                            "description": "작업: search, bulk_search, hybrid_search(로컬우선+PubMed보완), import_citations, import_by_pmids, fetch_by_doi(DOI조회), doi_metadata(DOI메타만), import_by_doi(DOI임포트), upgrade_pdf, get_abstract_only, get_stats"
                        },
                        "query": {"type": "string", "description": "검색 쿼리"},
                        "paper_id": {"type": "string", "description": "논문 ID"},
                        "pmids": {"type": "array", "items": {"type": "string"}, "description": "PMID 목록"},
                        "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 10, "description": "최대 동시 처리 수 (1-10, 기본값: PUBMED_MAX_CONCURRENT 환경변수)"},
                        "doi": {"type": "string", "description": "DOI (예: 10.1016/j.spinee.2024.01.001)"},
                        "pdf_path": {"type": "string", "description": "PDF 경로"},
                        "max_results": {"type": "integer", "default": 50},
                        "local_top_k": {"type": "integer", "default": 10, "description": "hybrid_search: 로컬 검색 최대 결과 수"},
                        "min_local_results": {"type": "integer", "default": 5, "description": "hybrid_search: 이 수 미만이면 PubMed 보완 검색"},
                        "auto_import": {"type": "boolean", "default": True, "description": "hybrid_search: 새 논문 자동 임포트 여부"},
                        "fetch_details": {"type": "boolean", "default": True},
                        "import_results": {"type": "boolean", "default": False},
                        "import_to_graph": {"type": "boolean", "default": False, "description": "DOI 조회 시 그래프 임포트 여부"},
                        "fetch_fulltext": {"type": "boolean", "default": True, "description": "DOI 임포트 시 전문 조회 여부"},
                        "year_from": {"type": "integer"},
                        "year_to": {"type": "integer"},
                        "min_confidence": {"type": "number", "default": 0.7},
                        "limit": {"type": "integer", "default": 50}
                    },
                    "required": ["action"]
                }
            ),
            # 4. Analyze Tool (store_analyzed_paper 포함)
            Tool(
                name="analyze",
                description="텍스트 분석 및 사전 분석된 논문 저장. action=text(LLM 분석, v7.5 파이프라인 기본), action=store_paper(사전 분석 데이터 저장, store_analyzed_paper).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["text", "store_paper"],
                            "description": "분석 작업: text(LLM 분석), store_paper(사전 분석 저장)"
                        },
                        # text action용
                        "text": {"type": "string", "description": "분석할 텍스트 (text)"},
                        "use_v7": {"type": "boolean", "default": True, "description": "v7.5 Simplified Pipeline 사용 (text action, 권장)"},
                        # 공통
                        "title": {"type": "string", "description": "논문 제목"},
                        "abstract": {"type": "string", "description": "논문 초록 (store_paper 필수)"},
                        "year": {"type": "integer", "description": "출판 연도 (store_paper 필수)"},
                        "pmid": {"type": "string"},
                        "metadata": {"type": "object"},
                        # store_paper용 (v7.3)
                        "interventions": {"type": "array", "items": {"type": "string"}, "description": "수술법 목록 (store_paper 필수)"},
                        "outcomes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "intervention": {"type": "string"},
                                    "value": {"type": "number"},
                                    "unit": {"type": "string"},
                                    "direction": {"type": "string", "enum": ["improved", "worsened", "unchanged"]},
                                    "p_value": {"type": "number"},
                                    "effect_size": {"type": "number"},
                                    "is_significant": {"type": "boolean"}
                                },
                                "required": ["name", "intervention"]
                            },
                            "description": "결과 지표 목록 (store_paper 필수)"
                        },
                        "pathologies": {"type": "array", "items": {"type": "string"}},
                        "anatomy_levels": {"type": "array", "items": {"type": "string"}},
                        "authors": {"type": "array", "items": {"type": "string"}},
                        "journal": {"type": "string"},
                        "doi": {"type": "string"},
                        "evidence_level": {"type": "string", "enum": ["1a", "1b", "2a", "2b", "3", "4", "5"]},
                        "study_design": {"type": "string", "enum": ["meta_analysis", "rct", "cohort", "case_control", "case_series", "case_report", "expert_opinion"]},
                        "sample_size": {"type": "integer"},
                        "summary": {"type": "string"},
                        "sub_domain": {"type": "string", "enum": ["Degenerative", "Deformity", "Trauma", "Tumor", "Infection", "Basic Science"]},
                        "chunks": {"type": "array", "items": {"type": "object"}},
                        "patient_cohorts": {"type": "array", "items": {"type": "object"}},
                        "followups": {"type": "array", "items": {"type": "object"}},
                        "costs": {"type": "array", "items": {"type": "object"}},
                        "quality_metrics": {"type": "array", "items": {"type": "object"}}
                    },
                    "required": ["action"]
                }
            ),
            # 5. Graph Exploration Tool
            Tool(
                name="graph",
                description="그래프 탐색: 논문 관계, 근거 체인, 비교, 클러스터, 멀티홉 추론, 인용 초안. action으로 기능 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["relations", "evidence_chain", "compare", "clusters", "multi_hop", "draft_citations", "build_relations"],
                            "description": "그래프 작업: relations, evidence_chain, compare, clusters, multi_hop, draft_citations, build_relations(논문간 관계 자동 구축)"
                        },
                        "paper_id": {"type": "string", "description": "논문 ID"},
                        "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "논문 ID 목록 (compare)"},
                        "claim": {"type": "string", "description": "검증할 주장 (evidence_chain)"},
                        "question": {"type": "string", "description": "질문 (multi_hop)"},
                        "topic": {"type": "string", "description": "주제 (draft_citations)"},
                        "relation_type": {"type": "string", "enum": ["cites", "supports", "contradicts", "similar_topic"]},
                        "max_papers": {"type": "integer", "default": 5, "description": "최대 논문 수 (evidence_chain, build_relations)"},
                        "min_similarity": {"type": "number", "default": 0.4, "description": "최소 유사도 임계값 (build_relations)"},
                        "max_hops": {"type": "integer", "default": 3},
                        "start_paper_id": {"type": "string"},
                        "section_type": {"type": "string", "enum": ["introduction", "methods", "results", "discussion", "conclusion"], "default": "introduction"},
                        "max_citations": {"type": "integer", "default": 5},
                        "language": {"type": "string", "enum": ["korean", "english"], "default": "korean"}
                    },
                    "required": ["action"]
                }
            ),
            # 6. Conflict Detection Tool
            Tool(
                name="conflict",
                description="충돌 탐지 및 근거 합성: 주제/수술법별 상충 연구 탐지, GRADE 기반 근거 종합. action으로 기능 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["find", "detect", "synthesize"],
                            "description": "충돌 작업: find(주제별), detect(수술법별), synthesize(근거 합성)"
                        },
                        "topic": {"type": "string", "description": "주제 (find)"},
                        "intervention": {"type": "string", "description": "수술법 (detect, synthesize)"},
                        "outcome": {"type": "string", "description": "결과변수 (detect, synthesize)"},
                        "document_ids": {"type": "array", "items": {"type": "string"}},
                        "min_papers": {"type": "integer", "default": 2}
                    },
                    "required": ["action"]
                }
            ),
            # 7. Intervention Tool
            Tool(
                name="intervention",
                description="수술법 분석: 계층 구조, 비교, 비교 가능 목록. action으로 기능 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["hierarchy", "compare", "comparable", "hierarchy_with_direction"],
                            "description": "수술법 작업: hierarchy(계층), compare(비교), comparable(비교 가능 목록), hierarchy_with_direction(방향별 계층)"
                        },
                        "intervention": {"type": "string", "description": "수술법 이름"},
                        "intervention_name": {"type": "string", "description": "수술법 이름 (hierarchy 호환)"},
                        "intervention1": {"type": "string", "description": "첫 번째 수술법 (compare)"},
                        "intervention2": {"type": "string", "description": "두 번째 수술법 (compare)"},
                        "outcome": {"type": "string", "description": "비교할 결과변수 (compare)"},
                        "direction": {"type": "string", "enum": ["ancestors", "descendants", "both"], "default": "both"}
                    },
                    "required": ["action"]
                }
            ),
            # 8. Extended Entity Tool (v7.2+)
            Tool(
                name="extended",
                description="확장 엔티티 조회 (v7.2+): 환자 코호트, 추적관찰, 비용 분석, 품질 지표. action으로 조회 유형 선택.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["patient_cohorts", "followup", "cost", "quality_metrics"],
                            "description": "조회 유형: patient_cohorts, followup, cost, quality_metrics"
                        },
                        "paper_id": {"type": "string"},
                        "intervention": {"type": "string"},
                        "cohort_type": {"type": "string", "enum": ["intervention", "control", "total", "propensity_matched"]},
                        "min_sample_size": {"type": "integer"},
                        "min_months": {"type": "integer"},
                        "max_months": {"type": "integer"},
                        "cost_type": {"type": "string", "enum": ["direct", "indirect", "total", "incremental"]},
                        "assessment_tool": {"type": "string", "enum": ["GRADE", "MINORS", "Newcastle-Ottawa", "Jadad", "AMSTAR", "Cochrane ROB"]},
                        "min_rating": {"type": "string", "enum": ["high", "moderate", "low", "very low"]}
                    },
                    "required": ["action"]
                }
            ),
            # 9. Reference Formatting Tool (v7.8)
            Tool(
                name="reference",
                description="참고문헌 포맷팅: 다양한 저널 스타일(Vancouver, AMA, APA, JBJS, Spine 등)로 참고문헌 생성. 저널별 커스텀 스타일 저장 및 BibTeX/RIS 내보내기 지원.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["format", "format_multiple", "list_styles", "set_journal_style", "add_custom_style", "preview"],
                            "description": "작업: format(단일 논문), format_multiple(여러 논문), list_styles(스타일 목록), set_journal_style(저널 스타일 설정), add_custom_style(커스텀 스타일 추가), preview(스타일 미리보기)"
                        },
                        "paper_id": {"type": "string", "description": "논문 ID (data/extracted/*.json)"},
                        "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "논문 ID 목록 (format_multiple)"},
                        "query": {"type": "string", "description": "검색어 (paper_id 대신 사용)"},
                        "style": {
                            "type": "string",
                            "enum": ["vancouver", "ama", "apa", "jbjs", "spine", "nlm", "harvard"],
                            "default": "vancouver",
                            "description": "인용 스타일"
                        },
                        "target_journal": {"type": "string", "description": "대상 저널명 (저장된 스타일 자동 적용)"},
                        "output_format": {
                            "type": "string",
                            "enum": ["text", "bibtex", "ris"],
                            "default": "text",
                            "description": "출력 형식"
                        },
                        "numbered": {"type": "boolean", "default": True, "description": "번호 붙이기 (format_multiple)"},
                        "start_number": {"type": "integer", "default": 1, "description": "시작 번호"},
                        "max_results": {"type": "integer", "default": 10, "description": "최대 결과 수"},
                        "journal_name": {"type": "string", "description": "저널명 (set_journal_style)"},
                        "style_name": {"type": "string", "description": "스타일명 (set_journal_style)"},
                        "name": {"type": "string", "description": "커스텀 스타일 이름 (add_custom_style)"},
                        "base_style": {"type": "string", "default": "vancouver", "description": "기반 스타일 (add_custom_style)"},
                        "author_et_al_threshold": {"type": "integer", "default": 6, "description": "et al. 사용 저자 수 기준"},
                        "include_doi": {"type": "boolean", "default": False, "description": "DOI 포함 여부"},
                        "include_pmid": {"type": "boolean", "default": False, "description": "PMID 포함 여부"},
                        "styles": {"type": "array", "items": {"type": "string"}, "description": "미리볼 스타일 목록 (preview)"}
                    },
                    "required": ["action"]
                }
            ),
            # 10. Writing Guide Tool (v7.12)
            Tool(
                name="writing_guide",
                description="학술 논문 작성 가이드: 섹션별 작성 지침, 연구 유형별 체크리스트(STROBE, CONSORT, PRISMA, CARE), 전문가 에이전트, 리비전 응답 템플릿.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["section_guide", "checklist", "expert", "response_template", "draft_response", "analyze_comments", "all_guides"],
                            "description": "작업: section_guide(섹션 가이드), checklist(체크리스트), expert(전문가 정보), response_template(응답 템플릿), draft_response(응답 초안), analyze_comments(리뷰어 코멘트 분석), all_guides(전체 가이드)"
                        },
                        "section": {
                            "type": "string",
                            "enum": ["introduction", "methods", "results", "discussion", "conclusion", "figure_legend"],
                            "description": "섹션명"
                        },
                        "study_type": {
                            "type": "string",
                            "enum": ["rct", "cohort", "case_control", "cross_sectional", "case_series", "case_report", "systematic_review", "meta_analysis", "diagnostic", "protocol", "observational_meta_analysis", "prediction", "economic"],
                            "description": "연구 유형"
                        },
                        "include_examples": {"type": "boolean", "default": True, "description": "예시 포함 여부"},
                        "checklist_name": {
                            "type": "string",
                            "enum": ["strobe", "consort", "prisma", "care", "stard", "spirit", "moose", "tripod", "cheers"],
                            "description": "체크리스트 (strobe:관찰연구, consort:RCT, prisma:SR/MA, care:증례, stard:진단, spirit:프로토콜, moose:관찰MA, tripod:예측모델, cheers:경제성)"
                        },
                        "section_filter": {"type": "string", "description": "특정 섹션 필터"},
                        "expert": {
                            "type": "string",
                            "enum": ["clinician", "methodologist", "statistician", "editor"],
                            "description": "전문가 유형"
                        },
                        "response_type": {
                            "type": "string",
                            "enum": ["major_revision", "minor_revision", "rejection_rebuttal"],
                            "description": "응답 유형"
                        },
                        "reviewer_comments": {"type": "string", "description": "리뷰어 코멘트 (draft_response, analyze_comments)"}
                    },
                    "required": ["action"]
                }
            )
            # Note: DOI fulltext 조회는 PubMed 임포트 프로세스에 자동 통합됨
            # PMC 실패 시 DOI/Unpaywall로 자동 fallback
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """통합 도구 핸들러 (v7.4 - action 기반 라우팅)."""
        action = arguments.get("action", "")
        logger.info(f"Tool called: {name}, action: {action}")

        try:
            # 1. Document Tool
            if name == "document":
                if action == "add_pdf":
                    result = await kag_server.add_pdf(
                        arguments.get("file_path", ""),
                        arguments.get("metadata"),
                        arguments.get("use_vision", True),
                        arguments.get("use_v7", True)
                    )
                elif action == "add_pdf_v7":
                    result = await kag_server.add_pdf_v7(
                        arguments.get("file_path", ""),
                        arguments.get("metadata"),
                        arguments.get("document_type")
                    )
                elif action == "add_json":
                    result = await kag_server.add_json(
                        arguments.get("file_path", ""),
                        arguments.get("metadata")
                    )
                elif action == "list":
                    result = await kag_server.list_documents()
                elif action == "delete":
                    result = await kag_server.delete_document(
                        arguments.get("document_id", "")
                    )
                elif action == "export":
                    result = await kag_server.export_document(
                        arguments.get("document_id", "")
                    )
                elif action == "reset":
                    result = await kag_server.reset_database(
                        arguments.get("include_taxonomy", False)
                    )
                elif action == "prepare_prompt":
                    result = await kag_server.prepare_pdf_prompt(
                        arguments.get("file_path", "")
                    )
                else:
                    result = {"success": False, "error": f"Unknown document action: {action}"}

            # 2. Search Tool (v7.14.25: 자동 하이브리드 검색)
            elif name == "search":
                if action == "search":
                    # v7.14.25: enable_pubmed_fallback=True 시 자동으로 하이브리드 검색
                    enable_pubmed_fallback = arguments.get("enable_pubmed_fallback", True)
                    if enable_pubmed_fallback and kag_server.pubmed_handler:
                        result = await kag_server.pubmed_handler.hybrid_search(
                            query=arguments.get("query", ""),
                            local_top_k=arguments.get("top_k", 10),
                            pubmed_max_results=arguments.get("pubmed_max_results", 20),
                            min_local_results=arguments.get("min_local_results", 5),
                            auto_import=arguments.get("auto_import", True),
                        )
                    else:
                        # enable_pubmed_fallback=False 시 기존 로컬 검색만
                        result = await kag_server.search(
                            arguments.get("query", ""),
                            arguments.get("top_k", 5),
                            arguments.get("tier_strategy", "tier1_then_tier2"),
                            arguments.get("prefer_original", True),
                            arguments.get("min_evidence_level")
                        )
                elif action == "graph":
                    result = await kag_server.graph_search(
                        arguments.get("query", ""),
                        arguments.get("search_type", "evidence"),
                        arguments.get("limit", 20)
                    )
                elif action == "adaptive":
                    result = await kag_server.adaptive_search(
                        arguments.get("query", ""),
                        arguments.get("top_k", 10),
                        arguments.get("include_synthesis", True),
                        arguments.get("detect_conflicts", True)
                    )
                elif action == "evidence":
                    result = await kag_server.find_evidence(
                        arguments.get("intervention", ""),
                        arguments.get("outcome", ""),
                        arguments.get("direction", "improved")
                    )
                elif action == "reason":
                    result = await kag_server.reason(
                        arguments.get("question", arguments.get("query", "")),
                        arguments.get("max_hops", 3),
                        arguments.get("include_conflicts", True)
                    )
                else:
                    result = {"success": False, "error": f"Unknown search action: {action}"}

            # 3. PubMed Tool
            elif name == "pubmed":
                if action == "search":
                    result = await kag_server.search_pubmed(
                        arguments.get("query", ""),
                        arguments.get("max_results", 10),
                        arguments.get("fetch_details", True)
                    )
                elif action == "bulk_search":
                    result = await kag_server.pubmed_bulk_search(
                        arguments.get("query", ""),
                        arguments.get("max_results", 50),
                        arguments.get("import_results", False),
                        arguments.get("year_from"),
                        arguments.get("year_to"),
                        arguments.get("publication_types")
                    )
                elif action == "hybrid_search":
                    # v7.14.24: 로컬 우선 + PubMed 보완 검색
                    result = await kag_server.hybrid_search(
                        query=arguments.get("query", ""),
                        local_top_k=arguments.get("local_top_k", 10),
                        pubmed_max_results=arguments.get("max_results", 20),
                        min_local_results=arguments.get("min_local_results", 5),
                        auto_import=arguments.get("auto_import", True),
                        year_from=arguments.get("year_from"),
                        year_to=arguments.get("year_to"),
                    )
                elif action == "import_citations":
                    result = await kag_server.pubmed_import_citations(
                        arguments.get("paper_id", ""),
                        arguments.get("min_confidence", 0.7)
                    )
                elif action == "import_by_pmids":
                    result = await kag_server.import_papers_by_pmids(
                        arguments.get("pmids", []),
                        max_concurrent=arguments.get("max_concurrent")  # None이면 환경변수 사용
                    )
                elif action == "upgrade_pdf":
                    result = await kag_server.upgrade_paper_with_pdf(
                        arguments.get("paper_id", ""),
                        arguments.get("pdf_path", "")
                    )
                elif action == "get_abstract_only":
                    result = await kag_server.get_abstract_only_papers(
                        arguments.get("limit", 50)
                    )
                elif action == "get_stats":
                    result = await kag_server.get_pubmed_import_stats()
                # DOI actions (v7.12.2)
                elif action == "fetch_by_doi":
                    result = await kag_server.fetch_by_doi(
                        arguments.get("doi", ""),
                        arguments.get("download_pdf", False),
                        arguments.get("import_to_graph", False)
                    )
                elif action == "doi_metadata":
                    result = await kag_server.get_doi_metadata(
                        arguments.get("doi", "")
                    )
                elif action == "import_by_doi":
                    result = await kag_server.import_by_doi(
                        arguments.get("doi", ""),
                        arguments.get("fetch_fulltext", True)
                    )
                else:
                    result = {"success": False, "error": f"Unknown pubmed action: {action}"}

            # 4. Analyze Tool (store_analyzed_paper 포함)
            elif name == "analyze":
                if action == "text":
                    result = await kag_server.analyze_text(
                        text=arguments.get("text", ""),
                        title=arguments.get("title", ""),
                        pmid=arguments.get("pmid"),
                        metadata=arguments.get("metadata"),
                        use_v7=arguments.get("use_v7", True)  # v7.5: 기본값 True
                    )
                elif action == "store_paper":
                    # store_analyzed_paper 기능 (v7.3)
                    result = await kag_server.store_analyzed_paper(
                        title=arguments.get("title", ""),
                        abstract=arguments.get("abstract", ""),
                        year=arguments.get("year", 2024),
                        interventions=arguments.get("interventions", []),
                        outcomes=arguments.get("outcomes", []),
                        pathologies=arguments.get("pathologies"),
                        anatomy_levels=arguments.get("anatomy_levels"),
                        authors=arguments.get("authors"),
                        journal=arguments.get("journal"),
                        doi=arguments.get("doi"),
                        pmid=arguments.get("pmid"),
                        evidence_level=arguments.get("evidence_level"),
                        study_design=arguments.get("study_design"),
                        sample_size=arguments.get("sample_size"),
                        summary=arguments.get("summary"),
                        sub_domain=arguments.get("sub_domain"),
                        chunks=arguments.get("chunks"),
                        patient_cohorts=arguments.get("patient_cohorts"),
                        followups=arguments.get("followups"),
                        costs=arguments.get("costs"),
                        quality_metrics=arguments.get("quality_metrics"),
                    )
                else:
                    result = {"success": False, "error": f"Unknown analyze action: {action}"}

            # 5. Graph Tool
            elif name == "graph":
                if action == "relations":
                    result = await kag_server.get_paper_relations(
                        arguments.get("paper_id", ""),
                        arguments.get("relation_type")
                    )
                elif action == "evidence_chain":
                    result = await kag_server.find_evidence_chain(
                        arguments.get("claim", ""),
                        arguments.get("max_papers", 5)
                    )
                elif action == "compare":
                    result = await kag_server.compare_papers(
                        arguments.get("paper_ids", [])
                    )
                elif action == "clusters":
                    result = await kag_server.get_topic_clusters()
                elif action == "multi_hop":
                    result = await kag_server.multi_hop_reason(
                        arguments.get("question", ""),
                        arguments.get("start_paper_id"),
                        arguments.get("max_hops", 3)
                    )
                elif action == "draft_citations":
                    result = await kag_server.draft_with_citations(
                        arguments.get("topic", ""),
                        arguments.get("section_type", "introduction"),
                        arguments.get("max_citations", 5),
                        arguments.get("language", "korean")
                    )
                elif action == "build_relations":
                    # 논문 간 SIMILAR_TOPIC 관계 자동 구축
                    if kag_server.graph_handler:
                        result = await kag_server.graph_handler.build_paper_relations(
                            paper_id=arguments.get("paper_id"),
                            min_similarity=arguments.get("min_similarity", 0.4),
                            max_papers=arguments.get("max_papers", 100)
                        )
                    else:
                        result = {"success": False, "error": "Graph handler not available"}
                else:
                    result = {"success": False, "error": f"Unknown graph action: {action}"}

            # 6. Conflict Tool
            elif name == "conflict":
                if action == "find":
                    result = await kag_server.find_conflicts(
                        arguments.get("topic", ""),
                        arguments.get("document_ids")
                    )
                elif action == "detect":
                    result = await kag_server.detect_conflicts(
                        arguments.get("intervention", ""),
                        arguments.get("outcome")
                    )
                elif action == "synthesize":
                    result = await kag_server.synthesize_evidence(
                        arguments.get("intervention", ""),
                        arguments.get("outcome", ""),
                        arguments.get("min_papers", 2)
                    )
                else:
                    result = {"success": False, "error": f"Unknown conflict action: {action}"}

            # 7. Intervention Tool
            elif name == "intervention":
                intervention_name = arguments.get("intervention") or arguments.get("intervention_name", "")
                if action == "hierarchy":
                    result = await kag_server.get_intervention_hierarchy(intervention_name)
                elif action == "compare":
                    result = await kag_server.compare_interventions(
                        arguments.get("intervention1", ""),
                        arguments.get("intervention2", ""),
                        arguments.get("outcome", "")
                    )
                elif action == "comparable":
                    result = await kag_server.get_comparable_interventions(intervention_name)
                elif action == "hierarchy_with_direction":
                    result = await kag_server.get_intervention_hierarchy_with_direction(
                        intervention_name,
                        arguments.get("direction", "both")
                    )
                else:
                    result = {"success": False, "error": f"Unknown intervention action: {action}"}

            # 8. Extended Tool (v7.2+)
            elif name == "extended":
                if action == "patient_cohorts":
                    result = await kag_server.get_patient_cohorts(
                        paper_id=arguments.get("paper_id"),
                        intervention=arguments.get("intervention"),
                        cohort_type=arguments.get("cohort_type"),
                        min_sample_size=arguments.get("min_sample_size")
                    )
                elif action == "followup":
                    result = await kag_server.get_followup_data(
                        paper_id=arguments.get("paper_id"),
                        intervention=arguments.get("intervention"),
                        min_months=arguments.get("min_months"),
                        max_months=arguments.get("max_months")
                    )
                elif action == "cost":
                    result = await kag_server.get_cost_analysis(
                        paper_id=arguments.get("paper_id"),
                        intervention=arguments.get("intervention"),
                        cost_type=arguments.get("cost_type")
                    )
                elif action == "quality_metrics":
                    result = await kag_server.get_quality_metrics(
                        paper_id=arguments.get("paper_id"),
                        assessment_tool=arguments.get("assessment_tool"),
                        min_rating=arguments.get("min_rating")
                    )
                else:
                    result = {"success": False, "error": f"Unknown extended action: {action}"}

            # 9. Reference Tool (v7.8)
            elif name == "reference":
                if kag_server.reference_handler is None:
                    result = {"success": False, "error": "ReferenceHandler not available"}
                elif action == "format":
                    result = await kag_server.reference_handler.format_reference(
                        paper_id=arguments.get("paper_id"),
                        query=arguments.get("query"),
                        style=arguments.get("style", "vancouver"),
                        target_journal=arguments.get("target_journal"),
                        output_format=arguments.get("output_format", "text")
                    )
                elif action == "format_multiple":
                    result = await kag_server.reference_handler.format_references(
                        paper_ids=arguments.get("paper_ids"),
                        query=arguments.get("query"),
                        max_results=arguments.get("max_results", 10),
                        style=arguments.get("style", "vancouver"),
                        target_journal=arguments.get("target_journal"),
                        numbered=arguments.get("numbered", True),
                        start_number=arguments.get("start_number", 1),
                        output_format=arguments.get("output_format", "text")
                    )
                elif action == "list_styles":
                    result = await kag_server.reference_handler.list_styles()
                elif action == "set_journal_style":
                    result = await kag_server.reference_handler.set_journal_style(
                        journal_name=arguments.get("journal_name", ""),
                        style_name=arguments.get("style_name", "")
                    )
                elif action == "add_custom_style":
                    result = await kag_server.reference_handler.add_custom_style(
                        name=arguments.get("name", ""),
                        base_style=arguments.get("base_style", "vancouver"),
                        author_et_al_threshold=arguments.get("author_et_al_threshold", 6),
                        author_et_al_min=arguments.get("author_et_al_min", 3),
                        author_initials_format=arguments.get("author_initials_format", "no_space"),
                        include_doi=arguments.get("include_doi", False),
                        include_pmid=arguments.get("include_pmid", False),
                        journal_abbreviation=arguments.get("journal_abbreviation", True),
                        volume_format=arguments.get("volume_format", "{volume}({issue})"),
                        pages_format=arguments.get("pages_format", "full")
                    )
                elif action == "preview":
                    result = await kag_server.reference_handler.preview_styles(
                        paper_id=arguments.get("paper_id"),
                        query=arguments.get("query"),
                        styles=arguments.get("styles")
                    )
                else:
                    result = {"success": False, "error": f"Unknown reference action: {action}"}

            # 10. Writing Guide Tool (v7.12)
            elif name == "writing_guide":
                if kag_server.writing_guide_handler is None:
                    result = {"success": False, "error": "WritingGuideHandler not available"}
                elif action == "section_guide":
                    result = await kag_server.writing_guide_handler.get_section_guide(
                        section=arguments.get("section", "introduction"),
                        study_type=arguments.get("study_type"),
                        include_examples=arguments.get("include_examples", True)
                    )
                elif action == "checklist":
                    result = await kag_server.writing_guide_handler.get_checklist(
                        study_type=arguments.get("study_type"),
                        checklist_name=arguments.get("checklist_name"),
                        section_filter=arguments.get("section_filter")
                    )
                elif action == "expert":
                    result = await kag_server.writing_guide_handler.get_expert_info(
                        expert=arguments.get("expert", "editor"),
                        section=arguments.get("section")
                    )
                elif action == "response_template":
                    result = await kag_server.writing_guide_handler.get_response_template(
                        response_type=arguments.get("response_type", "major_revision")
                    )
                elif action == "draft_response":
                    result = await kag_server.writing_guide_handler.draft_response_letter(
                        reviewer_comments=arguments.get("reviewer_comments", "")
                    )
                elif action == "analyze_comments":
                    result = await kag_server.writing_guide_handler.analyze_reviewer_comments(
                        comments=arguments.get("reviewer_comments", "")
                    )
                elif action == "all_guides":
                    result = await kag_server.writing_guide_handler.get_all_guides()
                else:
                    result = {"success": False, "error": f"Unknown writing_guide action: {action}"}

            else:
                result = {"success": False, "error": f"Unknown tool: {name}"}

            # Format result
            import json
            result_text = json.dumps(result, ensure_ascii=False, indent=2)
            return [TextContent(type="text", text=result_text)]

        except Exception as e:
            logger.exception(f"Tool error: {e}")
            return [TextContent(type="text", text=f"오류: {str(e)}")]

    return server


async def main():
    """서버 실행."""
    if not MCP_AVAILABLE:
        # MCP protocol requires all non-JSON output to stderr
        import sys
        print("MCP library not installed. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    # All logging goes to stderr (configured in logging setup)
    logger.info("Starting Medical KAG MCP Server...")

    kag_server = MedicalKAGServer()
    server = create_mcp_server(kag_server)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
