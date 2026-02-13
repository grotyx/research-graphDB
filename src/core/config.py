"""Centralized Configuration Management for Spine GraphRAG.

This module provides a type-safe, environment-aware configuration system
that loads settings from config.yaml and resolves environment variables.

Features:
- Type-safe configuration with dataclasses
- Environment variable resolution with defaults
- Multiple config file search locations
- Singleton pattern for global access
- Validation and error handling

Usage:
    from src.core.config import get_config

    config = get_config()
    print(config.neo4j.uri)
    print(config.llm.model)

    # Quick access helpers
    from src.core.config import get_neo4j_config, get_llm_config

    neo4j = get_neo4j_config()
    llm = get_llm_config()
"""

import os
import re
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Data Classes
# ============================================================================


@dataclass
class Neo4jConfig:
    """Neo4j database configuration.

    Attributes:
        uri: Connection URI (e.g., bolt://localhost:7687)
        username: Database username
        password: Database password
        database: Database name
        max_connection_pool_size: Maximum connection pool size
        connection_timeout: Connection timeout in seconds
        max_retry_time: Maximum retry time in seconds
        max_transaction_retry_time: Maximum transaction retry time in seconds
        circuit_breaker: Circuit breaker settings
    """

    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_timeout: int = 30
    max_retry_time: int = 30
    max_transaction_retry_time: int = 15
    circuit_breaker: dict = field(default_factory=dict)


@dataclass
class ChromaDBConfig:
    """ChromaDB vector database configuration.

    DEPRECATED (v7.14.12): ChromaDB 제거됨. Neo4j Vector Index 사용.
    하위 호환성을 위해 유지됨.
    """

    path: str = "./data/chromadb"
    collection_name: str = "spine_papers"
    distance_metric: str = "cosine"


@dataclass
class LLMVisionConfig:
    """LLM vision model configuration.

    Attributes:
        model: Vision model name
        timeout: Request timeout in seconds
        max_pdf_pages: Maximum PDF pages to process
    """

    model: str = "gemini-2.5-flash"
    timeout: int = 120
    max_pdf_pages: int = 100


@dataclass
class LLMConfig:
    """LLM (Large Language Model) configuration.

    Attributes:
        provider: LLM provider (e.g., "gemini")
        model: Model name
        api_key: API key for authentication
        temperature: Generation temperature (0.0-1.0)
        max_tokens: Maximum tokens per response
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries in seconds
        vision: Vision model configuration
    """

    provider: str = "gemini"
    model: str = "gemini-2.5-flash-preview-05-20"
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 32768  # Claude 4.5는 최대 64K 지원
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    vision: LLMVisionConfig = field(default_factory=LLMVisionConfig)


@dataclass
class NormalizationConfig:
    """Entity normalization configuration.

    Attributes:
        fuzzy_threshold: Fuzzy matching threshold
        token_overlap_threshold: Token overlap threshold
        word_boundary_confidence: Word boundary match confidence
        partial_match_threshold: Partial match threshold
        exact_match_confidence: Exact match confidence level
        alias_match_confidence: Alias match confidence level
        token_match_confidence: Token match confidence level
        fuzzy_match_confidence: Fuzzy match confidence level
        enable_korean_normalization: Enable Korean text normalization
        strip_particles: Strip Korean particles
    """

    fuzzy_threshold: float = 0.85
    token_overlap_threshold: float = 0.8
    word_boundary_confidence: float = 0.95
    partial_match_threshold: float = 0.5
    exact_match_confidence: float = 1.0
    alias_match_confidence: float = 1.0
    token_match_confidence: float = 0.9
    fuzzy_match_confidence: float = 0.85
    enable_korean_normalization: bool = True
    strip_particles: bool = True


@dataclass
class SearchConfig:
    """Search configuration.

    Attributes:
        default_top_k: Default number of results to return
        max_top_k: Maximum number of results allowed
        tier1_boost: Tier 1 result boost factor
        tier2_boost: Tier 2 result boost factor
        section_boost: Section-based boost factors
        evidence_boost: Evidence level boost settings
    """

    default_top_k: int = 10
    max_top_k: int = 100
    tier1_boost: float = 1.5
    tier2_boost: float = 1.0
    section_boost: dict = field(default_factory=dict)
    evidence_boost: dict = field(default_factory=dict)


@dataclass
class RankerConfig:
    """Hybrid ranker configuration.

    Attributes:
        default_graph_weight: Default graph search weight
        default_vector_weight: Default vector search weight
        evidence_weights: Evidence level weights (Oxford CEBM)
        significance_threshold: Statistical significance threshold
        significance_boost: Boost for significant results
        key_finding_boost: Boost for key findings
        statistics_boost: Boost for results with statistics
        normalize_scores: Whether to normalize final scores
    """

    default_graph_weight: float = 0.6
    default_vector_weight: float = 0.4
    evidence_weights: dict = field(default_factory=dict)
    significance_threshold: float = 0.05
    significance_boost: float = 1.5
    key_finding_boost: float = 1.2
    statistics_boost: float = 1.1
    normalize_scores: bool = True


@dataclass
class ConflictConfig:
    """Conflict detection configuration.

    Attributes:
        min_papers_for_conflict: Minimum papers to detect conflict
        significance_threshold: Significance threshold
        direction_change_threshold: Outcome direction change threshold
        include_conflicting_studies: Include conflicting studies in results
        max_conflicts_to_report: Maximum conflicts to report
    """

    min_papers_for_conflict: int = 2
    significance_threshold: float = 0.05
    direction_change_threshold: float = 0.1
    include_conflicting_studies: bool = True
    max_conflicts_to_report: int = 5


@dataclass
class CacheConfig:
    """Cache configuration.

    Attributes:
        query_cache: Query cache settings
        embedding_cache: Embedding cache settings
        semantic_cache: Semantic cache settings
        llm_cache: LLM response cache settings
        auto_invalidate: Auto-invalidate on updates
        invalidate_on_update: Invalidate on data updates
    """

    query_cache: dict = field(default_factory=dict)
    embedding_cache: dict = field(default_factory=dict)
    semantic_cache: dict = field(default_factory=dict)
    llm_cache: dict = field(default_factory=dict)
    auto_invalidate: bool = True
    invalidate_on_update: bool = True


@dataclass
class BatchConfig:
    """Batch processing configuration.

    Attributes:
        default_batch_size: Default batch size
        max_concurrency: Maximum concurrent operations
        checkpoint_interval: Checkpoint save interval
        checkpoint_dir: Checkpoint directory
        enable_resume: Enable resume from checkpoint
        resume_on_failure: Resume on failure
        progress_update_interval: Progress update interval
    """

    default_batch_size: int = 10
    max_concurrency: int = 5
    checkpoint_interval: int = 10
    checkpoint_dir: str = "./data/checkpoints"
    enable_resume: bool = True
    resume_on_failure: bool = True
    progress_update_interval: int = 5


@dataclass
class LoggingConfig:
    """Logging configuration.

    Attributes:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Log message format
        date_format: Date format
        file: File logging settings
        console: Console logging settings
    """

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    file: dict = field(default_factory=dict)
    console: dict = field(default_factory=dict)


@dataclass
class ErrorHandlingConfig:
    """Error handling configuration.

    Attributes:
        retry: Retry settings
        circuit_breaker: Circuit breaker settings
        report_errors: Whether to report errors
        error_log_path: Error log file path
    """

    retry: dict = field(default_factory=dict)
    circuit_breaker: dict = field(default_factory=dict)
    report_errors: bool = True
    error_log_path: str = "./logs/errors.log"


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration.

    Attributes:
        verbose: Verbose mode
        cypher: Cypher generation settings
        synthesis: Response synthesis settings
    """

    verbose: bool = False
    cypher: dict = field(default_factory=dict)
    synthesis: dict = field(default_factory=dict)


@dataclass
class MCPConfig:
    """MCP (Model Context Protocol) server configuration.

    Attributes:
        host: Server host
        port: Server port
        enable_all_tools: Enable all tools
        rate_limit: Rate limiting settings
    """

    host: str = "localhost"
    port: int = 8000
    enable_all_tools: bool = True
    rate_limit: dict = field(default_factory=dict)


@dataclass
class DevelopmentConfig:
    """Development settings.

    Attributes:
        debug: Debug mode
        enable_profiling: Enable profiling
        test_mode: Test mode
        mock_neo4j: Mock Neo4j for testing
        mock_llm: Mock LLM for testing
    """

    debug: bool = False
    enable_profiling: bool = False
    test_mode: bool = False
    mock_neo4j: bool = False
    mock_llm: bool = False


@dataclass
class Config:
    """Main configuration container.

    Aggregates all sub-configurations into a single object.

    Attributes:
        version: Configuration version
        neo4j: Neo4j configuration
        chromadb: ChromaDB configuration
        llm: LLM configuration
        normalization: Entity normalization configuration
        search: Search configuration
        ranker: Hybrid ranker configuration
        conflict: Conflict detection configuration
        cache: Cache configuration
        batch: Batch processing configuration
        logging: Logging configuration
        error_handling: Error handling configuration
        orchestrator: Orchestrator configuration
        mcp: MCP server configuration
        development: Development settings
    """

    version: str = "3.1"
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    ranker: RankerConfig = field(default_factory=RankerConfig)
    conflict: ConflictConfig = field(default_factory=ConflictConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    error_handling: ErrorHandlingConfig = field(default_factory=ErrorHandlingConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    development: DevelopmentConfig = field(default_factory=DevelopmentConfig)


# ============================================================================
# Configuration Manager (Singleton)
# ============================================================================


class ConfigManager:
    """Singleton configuration manager.

    Loads configuration from YAML file with environment variable resolution.
    Provides global access to configuration via singleton pattern.

    Usage:
        manager = ConfigManager()
        config = manager.load()
        print(config.neo4j.uri)
    """

    _instance: Optional["ConfigManager"] = None
    _config: Optional[Config] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "ConfigManager":
        """Create singleton instance with double-checked locking for thread safety."""
        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: Optional[str] = None) -> Config:
        """Load configuration from file.

        Args:
            config_path: Optional path to config file.
                        If not provided, searches standard locations.

        Returns:
            Loaded and parsed configuration

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config file is invalid
        """
        if self._config is not None:
            return self._config

        # Find config file
        path = Path(config_path) if config_path else self._find_config()

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        logger.info(f"Loading configuration from: {path}")

        # Load and parse YAML
        raw = self._load_yaml(path)
        resolved = self._resolve_env_vars(raw)
        self._config = self._parse_config(resolved)

        logger.info(f"Configuration loaded successfully (version: {self._config.version})")
        return self._config

    def reload(self, config_path: Optional[str] = None) -> Config:
        """Reload configuration from file.

        Args:
            config_path: Optional path to config file

        Returns:
            Reloaded configuration
        """
        self._config = None
        return self.load(config_path)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get nested configuration value by dot-separated path.

        Args:
            key_path: Dot-separated path (e.g., "neo4j.uri", "entity_normalizer.fuzzy_threshold")
            default: Default value if key not found

        Returns:
            Configuration value or default

        Examples:
            manager.get("neo4j.uri")  -> "bolt://localhost:7687"
            manager.get("llm.model")  -> "gemini-2.5-flash"
            manager.get("entity_normalizer.fuzzy_threshold", 0.85)  -> 0.85
        """
        config = self.load()
        keys = key_path.split(".")
        value = config

        for key in keys:
            if hasattr(value, key):
                value = getattr(value, key)
            elif isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def _find_config(self) -> Path:
        """Find config file in standard locations.

        Searches in order:
        1. ./config/config.yaml
        2. ../config/config.yaml
        3. ~/.spine_graphrag/config.yaml
        4. /etc/spine_graphrag/config.yaml

        Returns:
            Path to config file

        Raises:
            FileNotFoundError: If config not found in any location
        """
        locations = [
            Path("config/config.yaml"),
            Path("../config/config.yaml"),
            Path(__file__).parent.parent.parent / "config" / "config.yaml",
            Path.home() / ".spine_graphrag" / "config.yaml",
            Path("/etc/spine_graphrag/config.yaml"),
        ]

        for loc in locations:
            if loc.exists():
                return loc

        raise FileNotFoundError(
            f"config.yaml not found in any of: {[str(l) for l in locations]}"
        )

    def _load_yaml(self, path: Path) -> dict:
        """Load YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML content

        Raises:
            ValueError: If YAML is invalid
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")

    def _resolve_env_vars(self, data: Any) -> Any:
        """Resolve environment variables in config.

        Supports ${VAR_NAME:default_value} syntax.

        Args:
            data: Configuration data (str, dict, list, or primitive)

        Returns:
            Data with environment variables resolved

        Examples:
            ${NEO4J_URI:bolt://localhost:7687} -> os.environ.get("NEO4J_URI", "bolt://localhost:7687")
            ${GEMINI_API_KEY} -> os.environ.get("GEMINI_API_KEY", "")
        """
        if isinstance(data, str):
            # Pattern: ${VAR_NAME} or ${VAR_NAME:default}
            pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

            def replace(match):
                var_name, default = match.groups()
                value = os.environ.get(var_name, default or "")
                return value

            return re.sub(pattern, replace, data)

        elif isinstance(data, dict):
            return {k: self._resolve_env_vars(v) for k, v in data.items()}

        elif isinstance(data, list):
            return [self._resolve_env_vars(item) for item in data]

        else:
            return data

    def _parse_config(self, data: dict) -> Config:
        """Parse configuration dictionary into typed Config object.

        Args:
            data: Raw configuration dictionary

        Returns:
            Typed Config object
        """
        # Parse Neo4j config
        neo4j_data = data.get("neo4j", {})
        neo4j = Neo4jConfig(
            uri=neo4j_data.get("uri", "bolt://localhost:7687"),
            username=neo4j_data.get("username", "neo4j"),
            password=neo4j_data.get("password", "password"),
            database=neo4j_data.get("database", "neo4j"),
            max_connection_pool_size=neo4j_data.get("max_connection_pool_size", 50),
            connection_timeout=neo4j_data.get("connection_timeout", 30),
            max_retry_time=neo4j_data.get("max_retry_time", 30),
            max_transaction_retry_time=neo4j_data.get("max_transaction_retry_time", 15),
            circuit_breaker=neo4j_data.get("circuit_breaker", {}),
        )

        # Parse ChromaDB config
        chromadb_data = data.get("chromadb", {})
        chromadb = ChromaDBConfig(
            path=chromadb_data.get("path", "./data/chromadb"),
            collection_name=chromadb_data.get("collection_name", "spine_papers"),
            distance_metric=chromadb_data.get("distance_metric", "cosine"),
        )

        # Parse LLM config
        llm_data = data.get("llm", {})
        vision_data = llm_data.get("vision", {})
        llm = LLMConfig(
            provider=llm_data.get("provider", "gemini"),
            model=llm_data.get("model", "gemini-2.5-flash-preview-05-20"),
            api_key=llm_data.get("api_key", ""),
            temperature=llm_data.get("temperature", 0.1),
            max_tokens=llm_data.get("max_tokens", 32768),
            timeout=llm_data.get("timeout", 60),
            max_retries=llm_data.get("max_retries", 3),
            retry_delay=llm_data.get("retry_delay", 1.0),
            vision=LLMVisionConfig(
                model=vision_data.get("model", "gemini-2.5-flash"),
                timeout=vision_data.get("timeout", 120),
                max_pdf_pages=vision_data.get("max_pdf_pages", 100),
            ),
        )

        # Parse normalization config
        norm_data = data.get("normalization", {})
        normalization = NormalizationConfig(
            fuzzy_threshold=norm_data.get("fuzzy_threshold", 0.85),
            token_overlap_threshold=norm_data.get("token_overlap_threshold", 0.8),
            word_boundary_confidence=norm_data.get("word_boundary_confidence", 0.95),
            partial_match_threshold=norm_data.get("partial_match_threshold", 0.5),
            exact_match_confidence=norm_data.get("exact_match_confidence", 1.0),
            alias_match_confidence=norm_data.get("alias_match_confidence", 1.0),
            token_match_confidence=norm_data.get("token_match_confidence", 0.9),
            fuzzy_match_confidence=norm_data.get("fuzzy_match_confidence", 0.85),
            enable_korean_normalization=norm_data.get("enable_korean_normalization", True),
            strip_particles=norm_data.get("strip_particles", True),
        )

        # Parse search config
        search_data = data.get("search", {})
        search = SearchConfig(
            default_top_k=search_data.get("default_top_k", 10),
            max_top_k=search_data.get("max_top_k", 100),
            tier1_boost=search_data.get("tier1_boost", 1.5),
            tier2_boost=search_data.get("tier2_boost", 1.0),
            section_boost=search_data.get("section_boost", {}),
            evidence_boost=search_data.get("evidence_boost", {}),
        )

        # Parse ranker config
        ranker_data = data.get("ranker", {})
        ranker = RankerConfig(
            default_graph_weight=ranker_data.get("default_graph_weight", 0.6),
            default_vector_weight=ranker_data.get("default_vector_weight", 0.4),
            evidence_weights=ranker_data.get("evidence_weights", {}),
            significance_threshold=ranker_data.get("significance_threshold", 0.05),
            significance_boost=ranker_data.get("significance_boost", 1.5),
            key_finding_boost=ranker_data.get("key_finding_boost", 1.2),
            statistics_boost=ranker_data.get("statistics_boost", 1.1),
            normalize_scores=ranker_data.get("normalize_scores", True),
        )

        # Parse conflict config
        conflict_data = data.get("conflict", {})
        conflict = ConflictConfig(
            min_papers_for_conflict=conflict_data.get("min_papers_for_conflict", 2),
            significance_threshold=conflict_data.get("significance_threshold", 0.05),
            direction_change_threshold=conflict_data.get("direction_change_threshold", 0.1),
            include_conflicting_studies=conflict_data.get("include_conflicting_studies", True),
            max_conflicts_to_report=conflict_data.get("max_conflicts_to_report", 5),
        )

        # Parse cache config
        cache_data = data.get("cache", {})
        cache = CacheConfig(
            query_cache=cache_data.get("query_cache", {}),
            embedding_cache=cache_data.get("embedding_cache", {}),
            semantic_cache=cache_data.get("semantic_cache", {}),
            llm_cache=cache_data.get("llm_cache", {}),
            auto_invalidate=cache_data.get("auto_invalidate", True),
            invalidate_on_update=cache_data.get("invalidate_on_update", True),
        )

        # Parse batch config
        batch_data = data.get("batch", {})
        batch = BatchConfig(
            default_batch_size=batch_data.get("default_batch_size", 10),
            max_concurrency=batch_data.get("max_concurrency", 5),
            checkpoint_interval=batch_data.get("checkpoint_interval", 10),
            checkpoint_dir=batch_data.get("checkpoint_dir", "./data/checkpoints"),
            enable_resume=batch_data.get("enable_resume", True),
            resume_on_failure=batch_data.get("resume_on_failure", True),
            progress_update_interval=batch_data.get("progress_update_interval", 5),
        )

        # Parse logging config
        logging_data = data.get("logging", {})
        logging_config = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            format=logging_data.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            date_format=logging_data.get("date_format", "%Y-%m-%d %H:%M:%S"),
            file=logging_data.get("file", {}),
            console=logging_data.get("console", {}),
        )

        # Parse error handling config
        error_data = data.get("error_handling", {})
        error_handling = ErrorHandlingConfig(
            retry=error_data.get("retry", {}),
            circuit_breaker=error_data.get("circuit_breaker", {}),
            report_errors=error_data.get("report_errors", True),
            error_log_path=error_data.get("error_log_path", "./logs/errors.log"),
        )

        # Parse orchestrator config
        orch_data = data.get("orchestrator", {})
        orchestrator = OrchestratorConfig(
            verbose=orch_data.get("verbose", False),
            cypher=orch_data.get("cypher", {}),
            synthesis=orch_data.get("synthesis", {}),
        )

        # Parse MCP config
        mcp_data = data.get("mcp", {})
        mcp = MCPConfig(
            host=mcp_data.get("host", "localhost"),
            port=mcp_data.get("port", 8000),
            enable_all_tools=mcp_data.get("enable_all_tools", True),
            rate_limit=mcp_data.get("rate_limit", {}),
        )

        # Parse development config
        dev_data = data.get("development", {})
        development = DevelopmentConfig(
            debug=dev_data.get("debug", False),
            enable_profiling=dev_data.get("enable_profiling", False),
            test_mode=dev_data.get("test_mode", False),
            mock_neo4j=dev_data.get("mock_neo4j", False),
            mock_llm=dev_data.get("mock_llm", False),
        )

        return Config(
            version=data.get("version", "3.1"),
            neo4j=neo4j,
            chromadb=chromadb,
            llm=llm,
            normalization=normalization,
            search=search,
            ranker=ranker,
            conflict=conflict,
            cache=cache,
            batch=batch,
            logging=logging_config,
            error_handling=error_handling,
            orchestrator=orchestrator,
            mcp=mcp,
            development=development,
        )

    @property
    def config(self) -> Config:
        """Get current configuration.

        Returns:
            Current configuration (loads if not already loaded)
        """
        if self._config is None:
            self.load()
        return self._config


# ============================================================================
# Global Access Functions
# ============================================================================


def get_config() -> Config:
    """Get global configuration instance.

    Returns:
        Global configuration

    Example:
        config = get_config()
        print(config.neo4j.uri)
    """
    return ConfigManager().config


def get_neo4j_config() -> Neo4jConfig:
    """Get Neo4j configuration.

    Returns:
        Neo4j configuration

    Example:
        neo4j = get_neo4j_config()
        print(neo4j.uri)
    """
    return get_config().neo4j


def get_llm_config() -> LLMConfig:
    """Get LLM configuration.

    Returns:
        LLM configuration

    Example:
        llm = get_llm_config()
        print(llm.model)
    """
    return get_config().llm


def get_chromadb_config() -> ChromaDBConfig:
    """Get ChromaDB configuration.

    Returns:
        ChromaDB configuration
    """
    return get_config().chromadb


def get_normalization_config() -> NormalizationConfig:
    """Get entity normalization configuration.

    Returns:
        Normalization configuration
    """
    return get_config().normalization


def get_threshold(name: str, default: Optional[float] = None) -> float:
    """Get threshold value from configuration.

    Args:
        name: Threshold name (e.g., "fuzzy_threshold", "significance_threshold")
        default: Default value if not found

    Returns:
        Threshold value

    Raises:
        ValueError: If threshold not found and no default provided

    Example:
        fuzzy_threshold = get_threshold("fuzzy_threshold")
        sig_threshold = get_threshold("significance_threshold", 0.05)
    """
    config = get_config()

    # Search in various config sections
    sections = [
        config.normalization,
        config.ranker,
        config.conflict,
        config.cache,
    ]

    for section in sections:
        if hasattr(section, name):
            return getattr(section, name)

    if default is not None:
        return default

    raise ValueError(f"Threshold '{name}' not found in configuration and no default provided")


def reload_config(config_path: Optional[str] = None) -> Config:
    """Reload configuration from file.

    Useful for picking up configuration changes without restarting.

    Args:
        config_path: Optional path to config file

    Returns:
        Reloaded configuration

    Example:
        config = reload_config()
    """
    return ConfigManager().reload(config_path)
