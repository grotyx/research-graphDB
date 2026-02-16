"""Medical KAG MCP Server.

의학 논문 RAG 시스템을 위한 MCP 서버.
Tiered indexing, evidence level, citation detection 기능 통합.
LLM 기반 처리 및 논문 관계 그래프 지원.
"""

# CRITICAL: Load .env FIRST before any imports that might check environment variables
import os
import sys
import logging
from pathlib import Path

# Early logger for module-level import diagnostics
logger = logging.getLogger("medical-kag")

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f".env loaded from: {env_path}")
        logger.info(f"GEMINI_API_KEY present: {bool(os.environ.get('GEMINI_API_KEY'))}")
        logger.info(f"NEO4J_PASSWORD present: {bool(os.environ.get('NEO4J_PASSWORD'))}")
    else:
        logger.warning(f".env not found at: {env_path}")
except ImportError:
    logger.warning("python-dotenv not installed, skipping .env loading")

import asyncio
import json
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
    from mcp.types import (
        Tool, TextContent, ToolAnnotations,
        Resource, Prompt, PromptArgument, PromptMessage,
        GetPromptResult,
    )
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

# v1.14.12: ChromaDB 완전 제거 - Neo4j Vector Index만 사용
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
    logger.info("LLM modules imported successfully")
except ImportError as e:
    LLM_AVAILABLE = False
    logger.warning(f"LLM import failed: {e}")

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
    logger.info("Unified PDF processor v2.0 imported successfully")
except ImportError as e:
    VISION_AVAILABLE = False
    LEGACY_VISION_AVAILABLE = False
    UnifiedPDFProcessor = None
    ProcessorResult = None
    VisionProcessorResult = None
    GeminiVisionProcessor = None
    logger.warning(f"Unified PDF processor import failed: {e}")

# v1.0 Simplified Processing Pipeline - REMOVED (archived to src/archive/legacy_v7/)
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
    logger.info("PubMed Enricher imported successfully")
except ImportError as e:
    PUBMED_ENRICHER_AVAILABLE = False
    PubMedEnricher = None
    BibliographicMetadata = None
    logger.warning(f"PubMed Enricher import failed: {e}")

# Important Citation Processor (v3.2+)
try:
    from builder.important_citation_processor import ImportantCitationProcessor, CitationProcessingResult
    CITATION_PROCESSOR_AVAILABLE = True
    logger.info("Important Citation Processor imported successfully")
except ImportError as e:
    CITATION_PROCESSOR_AVAILABLE = False
    ImportantCitationProcessor = None
    CitationProcessingResult = None
    logger.warning(f"Important Citation Processor import failed: {e}")

# PubMed Bulk Processor (v4.3+)
try:
    from builder.pubmed_bulk_processor import (
        PubMedBulkProcessor,
        PubMedImportResult,
        BulkImportSummary,
    )
    PUBMED_BULK_AVAILABLE = True
    logger.info("PubMed Bulk Processor imported successfully")
except ImportError as e:
    PUBMED_BULK_AVAILABLE = False
    PubMedBulkProcessor = None
    PubMedImportResult = None
    BulkImportSummary = None
    logger.warning(f"PubMed Bulk Processor import failed: {e}")

# DOI Fulltext Fetcher (v1.13+)
try:
    from builder.doi_fulltext_fetcher import (
        DOIFulltextFetcher,
        DOIFullText,
        DOIMetadata,
        fetch_by_doi,
        get_doi_metadata,
    )
    DOI_FETCHER_AVAILABLE = True
    logger.info("DOI Fulltext Fetcher imported successfully")
except ImportError as e:
    DOI_FETCHER_AVAILABLE = False
    DOIFulltextFetcher = None
    DOIFullText = None
    DOIMetadata = None
    fetch_by_doi = None
    get_doi_metadata = None
    logger.warning(f"DOI Fulltext Fetcher import failed: {e}")

# PMC Full Text Fetcher (PMC-first optimization for PDF upload)
try:
    from builder.pmc_fulltext_fetcher import PMCFullTextFetcher
    PMC_FETCHER_AVAILABLE = True
    logger.info("PMC Full Text Fetcher imported successfully")
except ImportError as e:
    PMC_FETCHER_AVAILABLE = False
    PMCFullTextFetcher = None
    logger.warning(f"PMC Full Text Fetcher import failed: {e}")

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
    logger.info("Neo4j Graph modules imported successfully")
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
    logger.warning(f"Neo4j Graph import failed: {e}")

# Handler modules (v1.7)
try:
    from medical_mcp.handlers import (
        DocumentHandler, ClinicalDataHandler, PubMedHandler, JSONHandler,
        CitationHandler, SearchHandler, PDFHandler, ReasoningHandler, GraphHandler,
        WritingGuideHandler
    )
    HANDLERS_AVAILABLE = True
    logger.info("Handler modules imported successfully (v1.13)")
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
    logger.warning(f"Handler modules import failed: {e}")

# Configure logging with file handler
from logging.handlers import RotatingFileHandler

_LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB per log file
_LOG_BACKUP_COUNT: int = 5              # Number of rotated log files to keep

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
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
    ]
)
logger.info(f"Log file: {_log_file}")


class MedicalKAGServer:
    """Medical KAG Server.

    MCP 도구들을 제공하는 서버 클래스.

    v1.5 멀티유저 지원:
    - current_user: 현재 사용자 ID (None이면 'system')
    - set_user(): 사용자 컨텍스트 설정
    - 검색/저장 시 사용자 필터링 적용
    """

    def __init__(
        self,
        data_dir: Optional[str | Path] = None,
        enable_llm: bool = True,
        use_neo4j_storage: bool = True,  # v5.3 Phase 4: Neo4j 전용 모드
        default_user: Optional[str] = None  # v1.5: 기본 사용자 ID
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

        # v1.5: 멀티유저 지원
        self.current_user: str = default_user or "system"

        # v1.18: OpenAI 클라이언트 lazy 초기화 (재사용)
        self._openai_client = None

        # Initialize components
        self._init_components()

        # Initialize handlers (v1.7)
        self._init_handlers()

        logger.info(f"Medical KAG Server initialized. Data dir: {self.data_dir}")
        logger.info(f"LLM enabled: {self.enable_llm}, Knowledge Graph: {KNOWLEDGE_AVAILABLE}")
        logger.info(f"Neo4j Storage Mode: {self.use_neo4j_storage}")
        logger.info(f"Current user: {self.current_user}")

    def set_user(self, user_id: str) -> None:
        """현재 사용자 설정 (v1.5).

        Args:
            user_id: 사용자 ID
        """
        self.current_user = user_id or "system"
        logger.info(f"User context set to: {self.current_user}")

    def _get_user_filter_clause(self, alias: str = "p") -> tuple[str, dict]:
        """사용자 필터링 Cypher WHERE 절 생성 (v1.5, v1.15 보안 강화).

        본인 소유 문서 + 공유 문서만 조회.
        Cypher injection 방지를 위해 파라미터화된 쿼리 반환.

        Args:
            alias: Paper 노드 별칭 (기본: 'p')

        Returns:
            (Cypher WHERE 절 문자열, 파라미터 딕셔너리) 튜플
        """
        if self.current_user == "system":
            return "", {}  # system 사용자는 모든 문서 접근 가능
        return f"WHERE {alias}.owner = $current_user OR {alias}.shared = true", {"current_user": self.current_user}

    def _init_components(self) -> None:
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

                    # v1.0 Processor removed (archived)
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

        # DOI Fulltext Fetcher (v1.16: enrichment fallback)
        self.doi_fetcher = None
        if DOI_FETCHER_AVAILABLE:
            try:
                self.doi_fetcher = DOIFulltextFetcher()
                logger.info("DOI Fulltext Fetcher initialized for enrichment fallback")
            except Exception as e:
                logger.warning(f"DOI Fulltext Fetcher initialization failed: {e}")

        # PMC Full Text Fetcher (PMC-first PDF optimization)
        self.pmc_fetcher = None
        if PMC_FETCHER_AVAILABLE:
            try:
                self.pmc_fetcher = PMCFullTextFetcher()
                logger.info("PMC Full Text Fetcher initialized (PMC-first optimization)")
            except Exception as e:
                logger.warning(f"PMC Full Text Fetcher init failed: {e}")

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
                    normalizer=self.entity_normalizer,
                    llm_client=self.llm_client,
                )

                logger.info("Neo4j Graph modules initialized (Spine GraphRAG v3)")
            except Exception as e:
                logger.warning(f"Neo4j Graph initialization failed: {e}")

        # v1.14.17: TieredHybridSearch 초기화 (Neo4j Hybrid Search 통합)
        if self.neo4j_client:
            # Neo4j 전용 모드: Neo4j Vector Index + Graph 필터 통합
            self.search_engine = TieredHybridSearch(
                vector_db=None,  # ChromaDB 제거됨
                neo4j_client=self.neo4j_client,
                use_neo4j_vector=True,
                config={
                    "use_neo4j_hybrid": True,  # v1.14.17: 그래프+벡터 통합 검색
                    "vector_weight": 0.4,
                    "graph_weight": 0.6,
                }
            )
            logger.info("TieredHybridSearch initialized with Neo4j Hybrid Search (v1.14.17)")
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
                        relationship_builder=self.relationship_builder,  # v1.6: 인용 논문 관계 구축용
                        min_confidence=0.7,
                        max_citations=15,
                        analyze_cited_abstracts=True,  # v1.6: 인용 논문 abstract LLM 분석
                        doi_fetcher=self.doi_fetcher,  # v1.16: DOI fallback
                    )
                    logger.info(f"Important Citation Processor initialized (v1.6) with {llm_provider} + LLM analysis")
                else:
                    logger.warning(
                        f"Citation Processor requires {'ANTHROPIC_API_KEY' if llm_provider == 'claude' else 'GEMINI_API_KEY'}"
                    )
            except Exception as e:
                logger.warning(f"Important Citation Processor initialization failed: {e}")

    def _convert_to_graph_spine_metadata(self, spine_meta) -> "GraphSpineMetadata":
        """Convert spine metadata to GraphSpineMetadata (v1.14.9).

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

        # v1.2 Extended entities
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

    def _init_handlers(self) -> None:
        """Initialize domain-specific handlers (v1.7)."""
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

            # v1.8: Reference formatting handler
            from medical_mcp.handlers.reference_handler import ReferenceHandler
            self.reference_handler = ReferenceHandler(self)

            # v1.13: Writing guide handler
            from medical_mcp.handlers.writing_guide_handler import WritingGuideHandler
            self.writing_guide_handler = WritingGuideHandler(self)

            logger.info("[medical_kag_server] Handlers initialized (v1.13 - with WritingGuideHandler)")
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
        use_vision: bool = True
    ) -> dict:
        """PDF 논문 추가.

        v1.5 업데이트: v1.0 Simplified Pipeline을 기본으로 사용합니다.
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹
        - 조건부 엔티티 추출 (의학 콘텐츠만)
        - Important Citation 자동 처리

        Args:
            file_path: PDF 파일 경로
            metadata: 추가 메타데이터
            use_vision: 통합 PDF 프로세서 사용 여부 (레거시, True: 권장)

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

    def _extract_identifiers_from_pdf(self, path: Path) -> dict[str, str]:
        """PDF 첫 2페이지에서 DOI/PMID를 경량 추출 (regex, LLM 호출 없음).

        Args:
            path: PDF 파일 경로

        Returns:
            {'doi': '10.xxxx/...', 'pmid': '12345678'} (발견된 것만 포함)
        """
        import re
        result = {}

        try:
            import fitz
            doc = fitz.open(str(path))
            try:
                text = ""
                for page_num in range(min(2, len(doc))):
                    text += doc[page_num].get_text()
            finally:
                doc.close()
        except Exception as e:
            logger.debug(f"[PMC-first] PDF text extraction failed: {e}")
            return result

        if not text:
            return result

        # DOI: 10.xxxx/... 패턴 (doi:, DOI , https://doi.org/ 등)
        doi_match = re.search(
            r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s,;}\]]+)',
            text, re.IGNORECASE
        )
        if doi_match:
            doi = doi_match.group(1).rstrip('.')
            result['doi'] = doi
            logger.info(f"[PMC-first] Extracted DOI from PDF: {doi}")

        # PMID: PMID: 12345678 또는 PMID 12345678
        pmid_match = re.search(r'PMID[:\s]*(\d{7,8})', text, re.IGNORECASE)
        if pmid_match:
            result['pmid'] = pmid_match.group(1)
            logger.info(f"[PMC-first] Extracted PMID from PDF: {result['pmid']}")

        return result

    async def _try_open_access_text(
        self,
        path: Path,
        identifiers: dict[str, str],
    ) -> Optional[Any]:
        """Vision API 전에 Open Access 전문을 시도 (PMC → Unpaywall).

        성공 시 process_text()로 처리한 ProcessorResult 반환, 실패 시 None.
        """
        doi = identifiers.get('doi', '')
        pmid = identifiers.get('pmid', '')

        if not doi and not pmid:
            return None

        MIN_TEXT_LENGTH = 500

        # Step 1: DOI에서 PMID 확인 (PMC 조회용)
        if not pmid and doi and self.pubmed_enricher:
            try:
                bib_meta = await self.pubmed_enricher.enrich_by_doi(doi)
                if bib_meta and bib_meta.pmid:
                    pmid = bib_meta.pmid
                    logger.info(f"[PMC-first] DOI → PMID resolved: {doi} → {pmid}")
            except Exception as e:
                logger.debug(f"[PMC-first] DOI→PMID resolution failed: {e}")

        # Step 2: PMC BioC API (구조화된 전문, 최고 품질)
        if pmid and self.pmc_fetcher:
            try:
                pmc_result = await self.pmc_fetcher.fetch_fulltext(pmid)
                if pmc_result.has_full_text and len(pmc_result.full_text) >= MIN_TEXT_LENGTH:
                    logger.info(
                        f"[PMC-first] PMC full text found: PMID {pmid} "
                        f"({len(pmc_result.sections)} sections, {len(pmc_result.full_text)} chars)"
                    )
                    result = await self.vision_processor.process_text(
                        text=pmc_result.full_text,
                        title=pmc_result.title or path.stem,
                        source="pmc_from_pdf",
                    )
                    if result.success:
                        logger.info(
                            f"[PMC-first] Text processing succeeded "
                            f"(in={result.input_tokens}, out={result.output_tokens})"
                        )
                        return result
                    else:
                        logger.warning(f"[PMC-first] Text processing failed: {result.error}")
            except Exception as e:
                logger.warning(f"[PMC-first] PMC fetch/process failed: {e}")

        # Step 3: Unpaywall (DOI 기반 OA 텍스트)
        if doi and self.doi_fetcher:
            try:
                doi_result = await self.doi_fetcher.fetch(
                    doi, download_pdf=False, fetch_pmc=False,
                )
                if doi_result.has_full_text and doi_result.full_text and len(doi_result.full_text) >= MIN_TEXT_LENGTH:
                    oa_status = doi_result.metadata.oa_status if doi_result.metadata else "unknown"
                    logger.info(
                        f"[PMC-first] Unpaywall text found: DOI {doi} "
                        f"({len(doi_result.full_text)} chars, OA: {oa_status})"
                    )
                    result = await self.vision_processor.process_text(
                        text=doi_result.full_text,
                        title=(doi_result.metadata.title if doi_result.metadata else "") or path.stem,
                        source="unpaywall_from_pdf",
                    )
                    if result.success:
                        logger.info(
                            f"[PMC-first] Unpaywall text processing succeeded "
                            f"(in={result.input_tokens}, out={result.output_tokens})"
                        )
                        return result
                    else:
                        logger.warning(f"[PMC-first] Unpaywall text processing failed: {result.error}")
            except Exception as e:
                logger.warning(f"[PMC-first] Unpaywall fetch/process failed: {e}")

        logger.info(f"[PMC-first] No OA text available for {path.name}, using Vision API")
        return None

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

        # 0. PMC-first: Open Access 전문이 있으면 Vision API 대신 텍스트 처리
        oa_result = None
        if self.pmc_fetcher or self.doi_fetcher:
            identifiers = self._extract_identifiers_from_pdf(path)
            if identifiers:
                oa_result = await self._try_open_access_text(path, identifiers)

        # 1. LLM API로 전체 처리 (OA 텍스트 또는 Vision API)
        if oa_result is not None:
            result = oa_result
            logger.info(f"[PMC-first] Using Open Access text result for {path.name}")
        else:
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
            # v1.14.27: None 값 처리
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
                summary: str = ""
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
                summary=spine_dict.get("summary", ""),
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

        # v1.16: DOI Fallback - PubMed 실패 시 Crossref/Unpaywall로 서지 정보 조회
        if not pubmed_enriched and self.doi_fetcher and getattr(extracted_meta, 'doi', None):
            try:
                logger.info(f"PubMed enrichment failed, trying DOI fallback: {extracted_meta.doi}")
                doi_metadata = await self.doi_fetcher.get_metadata_only(extracted_meta.doi)

                if doi_metadata:
                    from builder.pubmed_enricher import BibliographicMetadata as BibMeta
                    pubmed_metadata = BibMeta.from_doi_metadata(doi_metadata, confidence=0.8)
                    pubmed_enriched = True
                    logger.info(
                        f"DOI fallback enrichment successful: DOI={extracted_meta.doi}, "
                        f"title={doi_metadata.title[:50]}..."
                    )
                else:
                    logger.debug(f"DOI fallback returned no results for: {extracted_meta.doi}")
            except Exception as e:
                logger.warning(f"DOI fallback enrichment failed: {e}")

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

                    # v1.14.9: v1.2 Extended entities 포함
                    graph_spine_meta = GraphSpineMetadata(
                        sub_domains=sub_domains,
                        sub_domain=sub_domain or (sub_domains[0] if sub_domains else ''),
                        surgical_approach=getattr(spine_meta, 'surgical_approach', []) or [],
                        anatomy_levels=anatomy_levels,
                        pathologies=pathologies if isinstance(pathologies, list) else [pathologies],
                        interventions=interventions,
                        outcomes=spine_outcomes,
                        main_conclusion=getattr(spine_meta, 'main_conclusion', '') or '',
                        # v1.2 Extended entities
                        patient_cohorts=getattr(spine_meta, 'patient_cohorts', []) or [],
                        followups=getattr(spine_meta, 'followups', []) or [],
                        costs=getattr(spine_meta, 'costs', []) or [],
                        quality_metrics=getattr(spine_meta, 'quality_metrics', []) or [],
                    )
                else:
                    # spine_metadata가 없거나 비어있는 경우 - 청크에서 추론
                    graph_spine_meta = self._infer_spine_metadata_from_chunks(result.chunks)

                # Neo4j에 Paper 노드 및 관계 생성 (v1.5: 멀티유저 지원)
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
        text = self.pdf_handler._extract_pdf_text(path)
        if not text:
            return {"success": False, "error": "텍스트 추출 실패"}

        # 2. 메타데이터 추출 및 문서 ID 생성 (Author_Year_Title 형식)
        pdf_metadata = self.pdf_handler._extract_pdf_metadata(path, text)
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
            sections = self.pdf_handler._classify_sections(text)
            citation_info = self.pdf_handler._detect_citations(text)
            study_info = self.pdf_handler._classify_study(text)

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
        study_info = self.pdf_handler._classify_study(text)

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
        metadata: Optional[dict] = None
    ) -> dict:
        """텍스트(논문 초록/본문)를 직접 분석하여 Neo4j에 저장.

        Claude Code에서 논문 텍스트를 붙여넣고 분석 → 관계 구축 → 청크 저장을
        한 번에 수행합니다. PDF 없이 텍스트만으로 지식 그래프 구축이 가능합니다.

        v1.5 업데이트: v1.0 Simplified Pipeline을 기본으로 사용합니다.
        - 22개 문서 유형 자동 감지
        - 700+ word 통합 요약 (4개 섹션)
        - 섹션 기반 청킹 (15-25 chunks)
        - 조건부 엔티티 추출 (의학 콘텐츠만)

        Args:
            text: 분석할 텍스트 (논문 초록 또는 본문, 최소 100자 이상)
            title: 논문 제목
            pmid: PubMed ID (선택, 없으면 자동 생성)
            metadata: 추가 메타데이터 (year, journal, authors, doi 등)

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
        # ProcessorResult.extracted_data (dict)에서 메타데이터 파싱
        _extracted = result.extracted_data or {}
        _meta_dict = _extracted.get("metadata") or {}
        _spine_dict = _extracted.get("spine_metadata") or {}

        @dataclass
        class _AnalyzeExtractedMeta:
            title: str = ""
            authors: list = field(default_factory=list)
            year: int = 0
            journal: str = ""
            doi: str = ""
            pmid: str = ""
            evidence_level: str = ""
            study_design: str = ""
            sample_size: int = 0

        extracted_meta = _AnalyzeExtractedMeta(
            title=_meta_dict.get("title", title),
            authors=_meta_dict.get("authors", []),
            year=_meta_dict.get("year", 0),
            journal=_meta_dict.get("journal", ""),
            doi=_meta_dict.get("doi", ""),
            pmid=_meta_dict.get("pmid", ""),
            evidence_level=_meta_dict.get("evidence_level", ""),
            study_design=_meta_dict.get("study_design", ""),
            sample_size=_meta_dict.get("sample_size", 0),
        )

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

        # v1.16: DOI Fallback for analyze_text
        if not pubmed_enriched and self.doi_fetcher:
            doi_value = metadata.get("doi") if metadata else getattr(extracted_meta, 'doi', None)
            if doi_value:
                try:
                    logger.info(f"[analyze_text] PubMed failed, trying DOI fallback: {doi_value}")
                    doi_metadata = await self.doi_fetcher.get_metadata_only(doi_value)
                    if doi_metadata:
                        from builder.pubmed_enricher import BibliographicMetadata as BibMeta
                        pubmed_metadata = BibMeta.from_doi_metadata(doi_metadata, confidence=0.8)
                        pubmed_enriched = True
                        logger.info(f"[analyze_text] DOI fallback successful: DOI={doi_value}")
                except Exception as e:
                    logger.warning(f"[analyze_text] DOI fallback failed: {e}")

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

        # 7. SpineMetadata 준비 (extracted_data의 spine_metadata dict에서 파싱)
        class MinimalSpineMeta:
            sub_domain = "Unknown"
            anatomy_levels = []
            interventions = []
            pathologies = []
            outcomes = []

        if _spine_dict:
            spine_meta = MinimalSpineMeta()
            spine_meta.sub_domain = _spine_dict.get("sub_domain", "Unknown")
            _anatomy_level = _spine_dict.get("anatomy_level", "")
            _anatomy_region = _spine_dict.get("anatomy_region", "")
            _anatomy_levels = []
            if _anatomy_level:
                _anatomy_levels.append(_anatomy_level)
            if _anatomy_region and _anatomy_region != _anatomy_level:
                _anatomy_levels.append(_anatomy_region)
            spine_meta.anatomy_levels = _anatomy_levels
            spine_meta.interventions = _spine_dict.get("interventions", [])
            spine_meta.pathologies = _spine_dict.get("pathologies", [])
            spine_meta.outcomes = _spine_dict.get("outcomes", [])
        else:
            spine_meta = MinimalSpineMeta()

        # 8. Neo4j 관계 구축 (v1.5: 멀티유저 지원)
        neo4j_result = None
        if self.neo4j_client and self.relationship_builder:
            try:
                # v1.14.9: 헬퍼 함수 사용하여 필드 매핑 처리
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
        _chunks_list = _extracted.get("chunks") or []
        chunks_data = _chunks_list

        if chunks_data and self.neo4j_client:
            try:
                from core.embedding import OpenAIEmbeddingGenerator

                embedding_gen = OpenAIEmbeddingGenerator()

                # 청크 텍스트 추출 (dict 또는 object 호환)
                def _get_chunk_field(c, key, default=None):
                    if isinstance(c, dict):
                        return c.get(key, default)
                    return getattr(c, key, default)

                chunk_texts = [_get_chunk_field(c, 'content', '') for c in chunks_data if _get_chunk_field(c, 'content')]

                if chunk_texts:
                    # v1.14.3: 기존 Chunk 삭제 (중복 방지)
                    await self._delete_existing_chunks(paper_id)

                    # 임베딩 생성
                    embeddings = embedding_gen.embed_batch(chunk_texts)

                    # Neo4j에 청크 저장
                    for i, (chunk, embedding) in enumerate(zip(chunks_data, embeddings)):
                        chunk_id = f"{paper_id}_chunk_{i}"

                        # 청크 속성 추출 (dict 또는 object 호환)
                        chunk_content = _get_chunk_field(chunk, 'content', str(chunk))
                        tier_raw = _get_chunk_field(chunk, 'tier', 'tier2')
                        chunk_tier = 1 if str(tier_raw) in ("tier1", "1") else 2
                        chunk_section = _get_chunk_field(chunk, 'section_type', 'body')

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
                        {"content": _get_chunk_field(c, 'content', str(c))}
                        for c in chunks_data
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
    # v1.5 Text Analysis Pipeline
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

    async def search(
        self,
        query: str,
        top_k: int = 5,
        tier_strategy: str = "tier1_then_tier2",
        prefer_original: bool = True,
        min_evidence_level: Optional[str] = None
    ) -> dict:
        """검색 수행 (v1.14.18: SearchHandler로 위임).

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

    # =========================================================================
    # v1.18: 입력 검증 헬퍼 메서드
    # =========================================================================

    @staticmethod
    def _validate_pmid(pmid: str) -> bool:
        """PMID 형식 검증 (1-8자리 숫자).

        Args:
            pmid: 검증할 PMID 문자열

        Returns:
            유효 여부
        """
        import re
        return bool(re.match(r'^\d{1,8}$', str(pmid).strip()))

    @staticmethod
    def _validate_doi(doi: str) -> bool:
        """DOI 형식 검증 (10.xxxx/... 패턴).

        Args:
            doi: 검증할 DOI 문자열

        Returns:
            유효 여부
        """
        import re
        return bool(re.match(r'^10\.\d{4,}/.+$', str(doi).strip()))

    # =========================================================================
    # v1.14.12: Abstract 임베딩 생성 헬퍼 메서드
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

            # v1.18: OpenAI 클라이언트 lazy 초기화 (재사용)
            if self._openai_client is None:
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # OpenAI 임베딩 생성 (3072차원)
            response = self._openai_client.embeddings.create(
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
    # v1.14.3: 중복 Paper 체크 헬퍼 메서드
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
                logger.info(f"[v1.14.3] Deleted {deleted} existing chunks for {paper_id}")
            return deleted
        except Exception as e:
            logger.warning(f"Error deleting existing chunks: {e}")
            return 0

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
                    except Exception as e:
                        logger.debug(f"Processing failed: {e}")

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
            logger.error(f"LLM pipeline error: {e}", exc_info=True)
            logger.info("Falling back to rule-based processing")
            # Fallback to rule-based processing
            sections = self.pdf_handler._classify_sections(text)
            citation_info = self.pdf_handler._detect_citations(text)
            study_info = self.pdf_handler._classify_study(text)
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

    # Read version from src/__init__.py (single source of truth)
    _pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(_pkg_root, "__init__.py")) as _f:
            _version = next(
                line.split('"')[1] for line in _f if line.startswith("__version__")
            )
    except (FileNotFoundError, StopIteration):
        _version = "unknown"

    server = Server("medical-kag", version=_version)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """10개 통합 도구 반환 (v1.4 - 38개 → 10개 통합).

        토큰 절감: ~4,800 tokens (63% 절감)
        기능 유지: 100% (action 파라미터로 기존 도구 기능 선택)
        """
        return [
            # 1. Document Management Tool
            Tool(
                name="document",
                description="문서 관리: PDF/JSON 추가, 목록 조회, 삭제, 내보내기, 데이터베이스 리셋. action으로 기능 선택.",
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add_pdf", "add_json", "list", "delete", "export", "reset", "prepare_prompt", "stats", "summarize"],
                            "description": "수행할 작업: add_pdf(PDF 추가), add_json(JSON 추가), list(목록), delete(삭제), export(내보내기), reset(리셋), prepare_prompt(프롬프트 생성), stats(시스템 통계), summarize(논문 요약)"
                        },
                        "file_path": {"type": "string", "description": "파일 경로 (add_pdf, add_json, prepare_prompt)"},
                        "document_id": {"type": "string", "description": "문서 ID (delete, export)"},
                        "metadata": {"type": "object", "description": "추가 메타데이터"},
                        "use_vision": {"type": "boolean", "default": True, "description": "레거시 PDF 프로세서 사용 (add_pdf, v1.5에서는 fallback)"},
                        "include_taxonomy": {"type": "boolean", "default": False, "description": "Taxonomy 삭제 여부 (reset)"},
                        "style": {"type": "string", "enum": ["brief", "detailed", "clinical"], "default": "brief", "description": "요약 스타일 (summarize)"}
                    },
                    "required": ["action"]
                }
            ),
            # 2. Search & Reasoning Tool (v1.14.25: 자동 하이브리드 검색)
            Tool(
                name="search",
                description="검색 및 추론: 벡터 검색(+PubMed 자동 보완), 그래프 검색, 적응형 검색, 근거 검색, 추론. action으로 검색 유형 선택.",
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["search", "graph", "adaptive", "evidence", "reason", "clinical_recommend"],
                            "description": "검색 유형: search(벡터+PubMed 자동), graph(그래프), adaptive(통합), evidence(근거), reason(추론), clinical_recommend(임상 치료 추천)"
                        },
                        "query": {"type": "string", "description": "검색 쿼리"},
                        "question": {"type": "string", "description": "질문 (reason)"},
                        "intervention": {"type": "string", "description": "수술법 (evidence, clinical_recommend)"},
                        "outcome": {"type": "string", "description": "결과변수 (evidence)"},
                        "patient_context": {"type": "string", "description": "환자 정보 텍스트 (clinical_recommend, 예: '65세 남성, 당뇨, L4-5 Stenosis')"},
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
                        "enable_pubmed_fallback": {"type": "boolean", "default": True, "description": "v1.14.25: 로컬 결과 부족 시 PubMed 자동 보완 (기본 True)"},
                        "min_local_results": {"type": "integer", "default": 5, "description": "v1.14.25: 이 수 미만이면 PubMed 보완 (기본 5)"},
                        "pubmed_max_results": {"type": "integer", "default": 20, "description": "v1.14.25: PubMed 검색 최대 결과 (기본 20)"},
                        "auto_import": {"type": "boolean", "default": True, "description": "v1.14.25: 새 논문 자동 임포트 (기본 True)"}
                    },
                    "required": ["action"]
                }
            ),
            # 3. PubMed Tool (DOI 기능 포함, v1.12.2)
            Tool(
                name="pubmed",
                description="PubMed/DOI 연동: 검색, 대량 검색, 인용 임포트, PMID 임포트, DOI 조회/임포트, PDF 업그레이드, 통계. action으로 기능 선택.",
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
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
                description="텍스트 분석 및 사전 분석된 논문 저장. action=text(LLM 분석, v1.5 파이프라인 기본), action=store_paper(사전 분석 데이터 저장, store_analyzed_paper).",
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
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
                        # 공통
                        "title": {"type": "string", "description": "논문 제목"},
                        "abstract": {"type": "string", "description": "논문 초록 (store_paper 필수)"},
                        "year": {"type": "integer", "description": "출판 연도 (store_paper 필수)"},
                        "pmid": {"type": "string"},
                        "metadata": {"type": "object"},
                        # store_paper용 (v1.3)
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
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["relations", "evidence_chain", "compare", "clusters", "multi_hop", "draft_citations", "build_relations", "infer_relations"],
                            "description": "그래프 작업: relations, evidence_chain, compare, clusters, multi_hop, draft_citations, build_relations(논문간 관계 자동 구축), infer_relations(추론 기반 관계 탐색)"
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
                        "language": {"type": "string", "enum": ["korean", "english"], "default": "korean"},
                        "rule_name": {"type": "string", "description": "추론 규칙 (infer_relations: transitive_hierarchy, comparable_siblings, aggregate_evidence 등)"},
                        "intervention": {"type": "string", "description": "수술법 (infer_relations)"},
                        "outcome": {"type": "string", "description": "결과변수 (infer_relations)"},
                        "pathology": {"type": "string", "description": "질환명 (infer_relations)"}
                    },
                    "required": ["action"]
                }
            ),
            # 6. Conflict Detection Tool
            Tool(
                name="conflict",
                description="충돌 탐지 및 근거 합성: 주제/수술법별 상충 연구 탐지, GRADE 기반 근거 종합. action으로 기능 선택.",
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
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
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
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
            # 8. Extended Entity Tool (v1.2+)
            Tool(
                name="extended",
                description="확장 엔티티 조회 (v1.2+): 환자 코호트, 추적관찰, 비용 분석, 품질 지표. action으로 조회 유형 선택.",
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
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
            # 9. Reference Formatting Tool (v1.8)
            Tool(
                name="reference",
                description="참고문헌 포맷팅: 다양한 저널 스타일(Vancouver, AMA, APA, JBJS, Spine 등)로 참고문헌 생성. 저널별 커스텀 스타일 저장 및 BibTeX/RIS 내보내기 지원.",
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
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
            # 10. Writing Guide Tool (v1.12)
            Tool(
                name="writing_guide",
                description="학술 논문 작성 가이드: 섹션별 작성 지침, 연구 유형별 체크리스트(STROBE, CONSORT, PRISMA, CARE), 전문가 에이전트, 리비전 응답 템플릿.",
                annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
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

    # ================================================================
    # Tool Registry (v1.19.2): Dictionary-based dispatch
    # Replaces ~420-line if/elif chain with declarative mapping
    # Key: (tool_name, action) → async callable(arguments) → dict
    # ================================================================

    async def _dispatch_document(action: str, args: dict) -> dict:
        """Document tool dispatcher (routes to pdf/json/document handlers)."""
        if action == "add_pdf":
            return await kag_server.pdf_handler.add_pdf(
                args.get("file_path", ""), args.get("metadata"),
                args.get("use_vision", True))
        elif action == "add_json":
            return await kag_server.json_handler.add_json(
                args.get("file_path", ""), args.get("metadata"))
        elif action == "list":
            return await kag_server.document_handler.list_documents()
        elif action == "delete":
            return await kag_server.document_handler.delete_document(
                args.get("document_id", ""))
        elif action == "export":
            return await kag_server.document_handler.export_document(
                args.get("document_id", ""))
        elif action == "reset":
            return await kag_server.document_handler.reset_database(
                args.get("include_taxonomy", False))
        elif action == "prepare_prompt":
            return await kag_server.pdf_handler.prepare_pdf_prompt(
                args.get("file_path", ""))
        elif action == "stats":
            return await kag_server.document_handler.get_stats()
        elif action == "summarize":
            return await kag_server.document_handler.summarize_paper(
                args.get("paper_id", args.get("document_id", "")),
                args.get("style", "brief"))
        return {"success": False, "error": f"Unknown document action: {action}"}

    async def _dispatch_search(action: str, args: dict) -> dict:
        """Search tool dispatcher."""
        if action == "search":
            # v1.14.25: enable_pubmed_fallback=True → 자동 하이브리드 검색
            if args.get("enable_pubmed_fallback", True) and kag_server.pubmed_handler:
                return await kag_server.pubmed_handler.hybrid_search(
                    query=args.get("query", ""),
                    local_top_k=args.get("top_k", 10),
                    pubmed_max_results=args.get("pubmed_max_results", 20),
                    min_local_results=args.get("min_local_results", 5),
                    auto_import=args.get("auto_import", True))
            return await kag_server.search_handler.search(
                args.get("query", ""), args.get("top_k", 5),
                args.get("tier_strategy", "tier1_then_tier2"),
                args.get("prefer_original", True),
                args.get("min_evidence_level"))
        elif action == "graph":
            return await kag_server.search_handler.graph_search(
                args.get("query", ""), args.get("search_type", "evidence"),
                args.get("limit", 20))
        elif action == "adaptive":
            return await kag_server.search_handler.adaptive_search(
                args.get("query", ""), args.get("top_k", 10),
                args.get("include_synthesis", True),
                args.get("detect_conflicts", True))
        elif action == "evidence":
            return await kag_server.search_handler.find_evidence(
                args.get("intervention", ""), args.get("outcome", ""),
                args.get("direction", "improved"))
        elif action == "reason":
            return await kag_server.reasoning_handler.reason(
                args.get("question", args.get("query", "")),
                args.get("max_hops", 3), args.get("include_conflicts", True))
        elif action == "clinical_recommend":
            return await kag_server.reasoning_handler.clinical_recommend(
                args.get("patient_context", ""),
                args.get("intervention"))
        return {"success": False, "error": f"Unknown search action: {action}"}

    async def _dispatch_pubmed(action: str, args: dict) -> dict:
        """PubMed/DOI tool dispatcher."""
        if action == "search":
            return await kag_server.pubmed_handler.search_pubmed(
                args.get("query", ""), args.get("max_results", 10),
                args.get("fetch_details", True))
        elif action == "bulk_search":
            return await kag_server.pubmed_handler.pubmed_bulk_search(
                args.get("query", ""), args.get("max_results", 50),
                args.get("import_results", False), args.get("year_from"),
                args.get("year_to"), args.get("publication_types"))
        elif action == "hybrid_search":
            return await kag_server.pubmed_handler.hybrid_search(
                query=args.get("query", ""),
                local_top_k=args.get("local_top_k", 10),
                pubmed_max_results=args.get("max_results", 20),
                min_local_results=args.get("min_local_results", 5),
                auto_import=args.get("auto_import", True),
                year_from=args.get("year_from"),
                year_to=args.get("year_to"))
        elif action == "import_citations":
            return await kag_server.pubmed_handler.pubmed_import_citations(
                args.get("paper_id", ""), args.get("min_confidence", 0.7))
        elif action == "import_by_pmids":
            return await kag_server.pubmed_handler.import_papers_by_pmids(
                args.get("pmids", []),
                max_concurrent=args.get("max_concurrent"))
        elif action == "upgrade_pdf":
            return await kag_server.pubmed_handler.upgrade_paper_with_pdf(
                args.get("paper_id", ""), args.get("pdf_path", ""))
        elif action == "get_abstract_only":
            return await kag_server.pubmed_handler.get_abstract_only_papers(
                args.get("limit", 50))
        elif action == "get_stats":
            return await kag_server.pubmed_handler.get_pubmed_import_stats()
        elif action == "fetch_by_doi":
            return await kag_server.pubmed_handler.fetch_by_doi(
                args.get("doi", ""), args.get("download_pdf", False),
                args.get("import_to_graph", False))
        elif action == "doi_metadata":
            return await kag_server.pubmed_handler.get_doi_metadata(
                args.get("doi", ""))
        elif action == "import_by_doi":
            return await kag_server.pubmed_handler.import_by_doi(
                args.get("doi", ""), args.get("fetch_fulltext", True))
        return {"success": False, "error": f"Unknown pubmed action: {action}"}

    async def _dispatch_analyze(action: str, args: dict) -> dict:
        """Analyze tool dispatcher."""
        if action == "text":
            return await kag_server.pdf_handler.analyze_text(
                text=args.get("text", ""), title=args.get("title", ""),
                pmid=args.get("pmid"), metadata=args.get("metadata"))
        elif action == "store_paper":
            return await kag_server.pdf_handler.store_analyzed_paper(
                title=args.get("title", ""),
                abstract=args.get("abstract", ""),
                year=args.get("year", 2024),
                interventions=args.get("interventions", []),
                outcomes=args.get("outcomes", []),
                pathologies=args.get("pathologies"),
                anatomy_levels=args.get("anatomy_levels"),
                authors=args.get("authors"),
                journal=args.get("journal"),
                doi=args.get("doi"),
                pmid=args.get("pmid"),
                evidence_level=args.get("evidence_level"),
                study_design=args.get("study_design"),
                sample_size=args.get("sample_size"),
                summary=args.get("summary"),
                sub_domain=args.get("sub_domain"),
                chunks=args.get("chunks"),
                patient_cohorts=args.get("patient_cohorts"),
                followups=args.get("followups"),
                costs=args.get("costs"),
                quality_metrics=args.get("quality_metrics"))
        return {"success": False, "error": f"Unknown analyze action: {action}"}

    async def _dispatch_graph(action: str, args: dict) -> dict:
        """Graph exploration tool dispatcher."""
        if action == "relations":
            return await kag_server.graph_handler.get_paper_relations(
                args.get("paper_id", ""), args.get("relation_type"))
        elif action == "evidence_chain":
            return await kag_server.graph_handler.find_evidence_chain(
                args.get("claim", ""), args.get("max_papers", 5))
        elif action == "compare":
            return await kag_server.reasoning_handler.compare_papers(
                args.get("paper_ids", []))
        elif action == "clusters":
            return await kag_server.graph_handler.get_topic_clusters()
        elif action == "multi_hop":
            return await kag_server.reasoning_handler.multi_hop_reason(
                args.get("question", ""), args.get("start_paper_id"),
                args.get("max_hops", 3))
        elif action == "draft_citations":
            return await kag_server.citation_handler.draft_with_citations(
                args.get("topic", ""), args.get("section_type", "introduction"),
                args.get("max_citations", 5), args.get("language", "korean"))
        elif action == "build_relations":
            if not kag_server.graph_handler:
                return {"success": False, "error": "Graph handler not available"}
            return await kag_server.graph_handler.build_paper_relations(
                paper_id=args.get("paper_id"),
                min_similarity=args.get("min_similarity", 0.4),
                max_papers=args.get("max_papers", 100))
        elif action == "infer_relations":
            return await kag_server.graph_handler.infer_relations(
                rule_name=args.get("rule_name"),
                intervention=args.get("intervention"),
                outcome=args.get("outcome"),
                pathology=args.get("pathology"),
                paper_id=args.get("paper_id"))
        return {"success": False, "error": f"Unknown graph action: {action}"}

    async def _dispatch_conflict(action: str, args: dict) -> dict:
        """Conflict detection tool dispatcher."""
        if action == "find":
            return await kag_server.reasoning_handler.find_conflicts(
                args.get("topic", ""), args.get("document_ids"))
        elif action == "detect":
            return await kag_server.reasoning_handler.detect_conflicts(
                args.get("intervention", ""), args.get("outcome"))
        elif action == "synthesize":
            return await kag_server.reasoning_handler.synthesize_evidence(
                args.get("intervention", ""), args.get("outcome", ""),
                args.get("min_papers", 2))
        return {"success": False, "error": f"Unknown conflict action: {action}"}

    async def _dispatch_intervention(action: str, args: dict) -> dict:
        """Intervention tool dispatcher."""
        name = args.get("intervention") or args.get("intervention_name", "")
        if action == "hierarchy":
            return await kag_server.graph_handler.get_intervention_hierarchy(name)
        elif action == "compare":
            return await kag_server.graph_handler.compare_interventions(
                args.get("intervention1", ""), args.get("intervention2", ""),
                args.get("outcome", ""))
        elif action == "comparable":
            return await kag_server.graph_handler.get_comparable_interventions(name)
        elif action == "hierarchy_with_direction":
            return await kag_server.graph_handler.get_intervention_hierarchy_with_direction(
                name, args.get("direction", "both"))
        return {"success": False, "error": f"Unknown intervention action: {action}"}

    async def _dispatch_extended(action: str, args: dict) -> dict:
        """Extended entity tool dispatcher."""
        if action == "patient_cohorts":
            return await kag_server.clinical_data_handler.get_patient_cohorts(
                paper_id=args.get("paper_id"),
                intervention=args.get("intervention"),
                cohort_type=args.get("cohort_type"),
                min_sample_size=args.get("min_sample_size"))
        elif action == "followup":
            return await kag_server.clinical_data_handler.get_followup_data(
                paper_id=args.get("paper_id"),
                intervention=args.get("intervention"),
                min_months=args.get("min_months"),
                max_months=args.get("max_months"))
        elif action == "cost":
            return await kag_server.clinical_data_handler.get_cost_analysis(
                paper_id=args.get("paper_id"),
                intervention=args.get("intervention"),
                cost_type=args.get("cost_type"))
        elif action == "quality_metrics":
            return await kag_server.clinical_data_handler.get_quality_metrics(
                paper_id=args.get("paper_id"),
                assessment_tool=args.get("assessment_tool"),
                min_rating=args.get("min_rating"))
        return {"success": False, "error": f"Unknown extended action: {action}"}

    async def _dispatch_reference(action: str, args: dict) -> dict:
        """Reference formatting tool dispatcher."""
        if not kag_server.reference_handler:
            return {"success": False, "error": "ReferenceHandler not available"}
        if action == "format":
            return await kag_server.reference_handler.format_reference(
                paper_id=args.get("paper_id"), query=args.get("query"),
                style=args.get("style", "vancouver"),
                target_journal=args.get("target_journal"),
                output_format=args.get("output_format", "text"))
        elif action == "format_multiple":
            return await kag_server.reference_handler.format_references(
                paper_ids=args.get("paper_ids"), query=args.get("query"),
                max_results=args.get("max_results", 10),
                style=args.get("style", "vancouver"),
                target_journal=args.get("target_journal"),
                numbered=args.get("numbered", True),
                start_number=args.get("start_number", 1),
                output_format=args.get("output_format", "text"))
        elif action == "list_styles":
            return await kag_server.reference_handler.list_styles()
        elif action == "set_journal_style":
            return await kag_server.reference_handler.set_journal_style(
                journal_name=args.get("journal_name", ""),
                style_name=args.get("style_name", ""))
        elif action == "add_custom_style":
            return await kag_server.reference_handler.add_custom_style(
                name=args.get("name", ""),
                base_style=args.get("base_style", "vancouver"),
                author_et_al_threshold=args.get("author_et_al_threshold", 6),
                author_et_al_min=args.get("author_et_al_min", 3),
                author_initials_format=args.get("author_initials_format", "no_space"),
                include_doi=args.get("include_doi", False),
                include_pmid=args.get("include_pmid", False),
                journal_abbreviation=args.get("journal_abbreviation", True),
                volume_format=args.get("volume_format", "{volume}({issue})"),
                pages_format=args.get("pages_format", "full"))
        elif action == "preview":
            return await kag_server.reference_handler.preview_styles(
                paper_id=args.get("paper_id"), query=args.get("query"),
                styles=args.get("styles"))
        return {"success": False, "error": f"Unknown reference action: {action}"}

    async def _dispatch_writing_guide(action: str, args: dict) -> dict:
        """Writing guide tool dispatcher."""
        if not kag_server.writing_guide_handler:
            return {"success": False, "error": "WritingGuideHandler not available"}
        if action == "section_guide":
            return await kag_server.writing_guide_handler.get_section_guide(
                section=args.get("section", "introduction"),
                study_type=args.get("study_type"),
                include_examples=args.get("include_examples", True))
        elif action == "checklist":
            return await kag_server.writing_guide_handler.get_checklist(
                study_type=args.get("study_type"),
                checklist_name=args.get("checklist_name"),
                section_filter=args.get("section_filter"))
        elif action == "expert":
            return await kag_server.writing_guide_handler.get_expert_info(
                expert=args.get("expert", "editor"),
                section=args.get("section"))
        elif action == "response_template":
            return await kag_server.writing_guide_handler.get_response_template(
                response_type=args.get("response_type", "major_revision"))
        elif action == "draft_response":
            return await kag_server.writing_guide_handler.draft_response_letter(
                reviewer_comments=args.get("reviewer_comments", ""))
        elif action == "analyze_comments":
            return await kag_server.writing_guide_handler.analyze_reviewer_comments(
                comments=args.get("reviewer_comments", ""))
        elif action == "all_guides":
            return await kag_server.writing_guide_handler.get_all_guides()
        return {"success": False, "error": f"Unknown writing_guide action: {action}"}

    # Tool name → dispatcher mapping
    _tool_dispatchers = {
        "document": _dispatch_document,
        "search": _dispatch_search,
        "pubmed": _dispatch_pubmed,
        "analyze": _dispatch_analyze,
        "graph": _dispatch_graph,
        "conflict": _dispatch_conflict,
        "intervention": _dispatch_intervention,
        "extended": _dispatch_extended,
        "reference": _dispatch_reference,
        "writing_guide": _dispatch_writing_guide,
    }

    # ================================================================
    # MCP Resources (v1.20): 논문 목록/메타데이터를 Resource로 노출
    # ================================================================

    @server.list_resources()
    async def list_resources():
        """논문 목록을 MCP Resource로 노출."""
        try:
            papers = await kag_server.document_handler.list_documents()
            resources = []
            for p in papers.get("documents", []):
                doc_id = p.get("document_id", "unknown")
                meta = p.get("metadata", {})
                resources.append(
                    Resource(
                        uri=f"paper://{doc_id}",
                        name=meta.get("title", doc_id)[:100],
                        description=f"({meta.get('year', '')})",
                        mimeType="application/json",
                    )
                )
            return resources
        except Exception as e:
            logger.error(f"list_resources failed: {e}", exc_info=True)
            return []

    @server.read_resource()
    async def read_resource(uri):
        """개별 논문 메타데이터 반환."""
        uri_str = str(uri)
        paper_id = uri_str.replace("paper://", "")
        try:
            result = await kag_server.document_handler.export_document(paper_id)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ================================================================
    # MCP Prompts (v1.20): 검색/분석 템플릿
    # ================================================================

    @server.list_prompts()
    async def list_prompts():
        """검색/분석 템플릿을 MCP Prompt로 노출."""
        return [
            Prompt(
                name="compare_interventions",
                description="두 수술법 비교 분석",
                arguments=[
                    PromptArgument(name="intervention_a", description="수술법 A", required=True),
                    PromptArgument(name="intervention_b", description="수술법 B", required=True),
                ],
            ),
            Prompt(
                name="evidence_summary",
                description="특정 수술법의 근거 요약",
                arguments=[
                    PromptArgument(name="intervention", description="수술법", required=True),
                    PromptArgument(name="outcome", description="결과변수", required=False),
                ],
            ),
            Prompt(
                name="paper_review",
                description="논문 비평적 분석",
                arguments=[
                    PromptArgument(name="paper_id", description="논문 ID", required=True),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict = None) -> GetPromptResult:
        """프롬프트 템플릿 반환."""
        args = arguments or {}

        if name == "compare_interventions":
            return GetPromptResult(
                description="두 수술법 비교 분석",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"다음 두 수술법을 비교 분석해주세요:\n\n"
                                f"수술법 A: {args.get('intervention_a', '')}\n"
                                f"수술법 B: {args.get('intervention_b', '')}\n\n"
                                f"각 수술법의 적응증, 합병증, 임상 결과를 근거 기반으로 비교해주세요."
                            ),
                        ),
                    )
                ],
            )
        elif name == "evidence_summary":
            outcome_text = f"\n결과변수: {args['outcome']}" if args.get("outcome") else ""
            return GetPromptResult(
                description="근거 요약",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"다음 수술법의 근거를 요약해주세요:\n\n"
                                f"수술법: {args.get('intervention', '')}{outcome_text}\n\n"
                                f"근거 수준, 주요 연구 결과, 권고사항을 포함해주세요."
                            ),
                        ),
                    )
                ],
            )
        elif name == "paper_review":
            return GetPromptResult(
                description="논문 리뷰",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"논문 ID: {args.get('paper_id', '')}의 비평적 분석을 해주세요.\n\n"
                                f"연구 설계, 방법론, 결과의 타당성, 제한점을 평가해주세요."
                            ),
                        ),
                    )
                ],
            )
        else:
            raise ValueError(f"Unknown prompt: {name}")

    # ================================================================
    # Tool Call Handler
    # ================================================================

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """통합 도구 핸들러 (v1.19.2 - Tool Registry 패턴).

        10개 도구 × 63개 액션을 딕셔너리 기반으로 디스패치합니다.
        """
        action = arguments.get("action", "")
        logger.info(f"Tool called: {name}, action: {action}")

        try:
            dispatcher = _tool_dispatchers.get(name)
            if not dispatcher:
                result = {"success": False, "error": f"Unknown tool: {name}"}
            else:
                result = await dispatcher(action, arguments)

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
