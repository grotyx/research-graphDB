#!/usr/bin/env python3
"""Cache Management Script.

Utilities for managing all caching layers:
- View cache statistics
- Clear caches
- Warm up caches
- Monitor cache performance
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cache.cache_manager import CacheManager, CacheConfig
from cache.embedding_cache import COMMON_MEDICAL_TERMS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_cache_config(config_path: str) -> CacheConfig:
    """Load cache configuration from YAML.

    Args:
        config_path: Path to cache_config.yaml

    Returns:
        CacheConfig instance
    """
    with open(config_path) as f:
        config_dict = yaml.safe_load(f)

    # Extract cache section
    cache_section = config_dict.get("cache", {})
    query_cache = config_dict.get("query_cache", {})
    embedding_cache = config_dict.get("embedding_cache", {})
    llm_cache = config_dict.get("llm_cache", {})
    semantic_cache = config_dict.get("semantic_cache", {})

    return CacheConfig(
        enabled=cache_section.get("enabled", True),
        query_cache_enabled=query_cache.get("enabled", True),
        query_cache_size=query_cache.get("max_size", 1000),
        query_cache_ttl=query_cache.get("ttl_seconds", 3600),
        embedding_cache_enabled=embedding_cache.get("enabled", True),
        embedding_cache_ttl=embedding_cache.get("ttl_days", 30),
        llm_cache_enabled=llm_cache.get("enabled", True),
        llm_cache_ttl=llm_cache.get("ttl_hours", 168),
        semantic_cache_enabled=semantic_cache.get("enabled", True),
        semantic_threshold=semantic_cache.get("similarity_threshold", 0.85),
    )


def print_stats(stats: dict, detailed: bool = False) -> None:
    """Print cache statistics.

    Args:
        stats: Statistics dictionary
        detailed: Show detailed stats
    """
    print("\n" + "=" * 70)
    print("CACHE STATISTICS")
    print("=" * 70)

    # Configuration
    print("\n[Configuration]")
    config = stats.get("config", {})
    for key, value in config.items():
        print(f"  {key}: {value}")

    # Query Cache
    if "query_cache" in stats:
        print("\n[Query Cache]")
        qc = stats["query_cache"]
        print(f"  Entries: {qc['entries']}")
        print(f"  Hits: {qc['hits']}")
        print(f"  Misses: {qc['misses']}")
        print(f"  Hit Rate: {qc['hit_rate']}")
        print(f"  Evictions: {qc['evictions']}")
        print(f"  Size: {qc['size_mb']:.2f} MB")

    # Cypher Cache
    if "cypher_cache" in stats:
        print("\n[Cypher Cache]")
        cc = stats["cypher_cache"]
        print(f"  Entries: {cc['entries']}")
        print(f"  Hits: {cc['hits']}")
        print(f"  Misses: {cc['misses']}")
        print(f"  Hit Rate: {cc['hit_rate']}")

    # Embedding Cache
    if "embedding_cache" in stats:
        print("\n[Embedding Cache]")
        ec = stats["embedding_cache"]
        print(f"  Entries: {ec['entries']}")
        print(f"  Size: {ec['size_mb']:.2f} MB")
        print(f"  Hit Count: {ec['hit_count']}")
        print(f"  Hit Rate: {ec['hit_rate']}")
        print(f"  Avg Embedding Dim: {ec['avg_embedding_dim']}")

    # Semantic Cache
    if "semantic_cache" in stats:
        print("\n[Semantic Cache]")
        sc = stats["semantic_cache"]
        print(f"  Entries: {sc['semantic_entries']}")
        print(f"  Operations: {sc['semantic_operations']}")
        print(f"  Similarity Threshold: {sc['similarity_threshold']}")
        print(f"  Max Entries/Operation: {sc['max_entries_per_operation']}")

    print("\n" + "=" * 70)


async def cmd_stats(args) -> None:
    """Show cache statistics.

    Args:
        args: Command arguments
    """
    # Load config
    config = load_cache_config(args.config)

    # Initialize manager
    manager = CacheManager(config=config, data_dir=args.data_dir)

    # Get statistics
    stats = manager.get_all_stats()

    # Print
    print_stats(stats, detailed=args.detailed)


async def cmd_clear(args) -> None:
    """Clear cache.

    Args:
        args: Command arguments
    """
    # Load config
    config = load_cache_config(args.config)

    # Initialize manager
    manager = CacheManager(config=config, data_dir=args.data_dir)

    # Confirm
    if not args.force:
        response = input("Are you sure you want to clear all caches? [y/N]: ")
        if response.lower() != "y":
            print("Aborted.")
            return

    # Clear
    if args.type == "all":
        manager.clear_all()
        print("✓ All caches cleared")

    elif args.type == "query":
        if manager.query_cache:
            manager.query_cache.clear()
            print("✓ Query cache cleared")
        if manager.cypher_cache:
            manager.cypher_cache.clear()
            print("✓ Cypher cache cleared")

    elif args.type == "embedding":
        if manager.embedding_cache:
            count = manager.embedding_cache.cleanup_expired()
            print(f"✓ Embedding cache cleared ({count} expired entries)")

    elif args.type == "llm":
        if manager.llm_cache:
            count = await manager.llm_cache.cleanup_expired()
            print(f"✓ LLM cache cleared ({count} expired entries)")

    # Show stats after clearing
    stats = manager.get_all_stats()
    print_stats(stats)


async def cmd_cleanup(args) -> None:
    """Clean up expired entries.

    Args:
        args: Command arguments
    """
    # Load config
    config = load_cache_config(args.config)

    # Initialize manager
    manager = CacheManager(config=config, data_dir=args.data_dir)

    # Cleanup
    print("Cleaning up expired entries...")
    results = manager.cleanup_all()

    print("\n[Cleanup Results]")
    for cache_name, count in results.items():
        if count > 0:
            print(f"  {cache_name}: {count} entries removed")

    total = sum(results.values())
    print(f"\nTotal: {total} expired entries removed")


async def cmd_warmup(args) -> None:
    """Warm up caches.

    Args:
        args: Command arguments
    """
    # Load config
    config = load_cache_config(args.config)

    # Initialize manager
    manager = CacheManager(config=config, data_dir=args.data_dir)

    print("Warming up caches...")

    # Query cache warmup (requires Neo4j)
    if args.query_cache and manager.cypher_cache:
        print("\n[Query Cache Warmup]")
        try:
            from graph.neo4j_client import Neo4jClient

            async with Neo4jClient() as client:
                from cache.query_cache import warmup_cache
                count = await warmup_cache(manager.cypher_cache, client)
                print(f"  ✓ Warmed up {count} queries")

        except Exception as e:
            logger.error(f"Query cache warmup failed: {e}")
            print(f"  ✗ Failed: {e}")

    # Embedding cache warmup (requires embedding model)
    if args.embedding_cache and manager.embedding_cache:
        print("\n[Embedding Cache Warmup]")
        try:
            from core.embedding import get_embedding_model

            # Load embedding model
            model = get_embedding_model()

            # Define embedding function
            async def embed_texts(texts):
                # Synchronous encode (most models are sync)
                return [model.encode(text) for text in texts]

            # Warmup
            terms = COMMON_MEDICAL_TERMS
            count = await manager.embedding_cache.warmup(
                terms, embed_texts, model_name="default", batch_size=32
            )
            print(f"  ✓ Warmed up {count} terms")

        except Exception as e:
            logger.error(f"Embedding cache warmup failed: {e}")
            print(f"  ✗ Failed: {e}")

    print("\n✓ Warmup complete")

    # Show stats
    stats = manager.get_all_stats()
    print_stats(stats)


async def cmd_monitor(args) -> None:
    """Monitor cache performance.

    Args:
        args: Command arguments
    """
    # Load config
    config = load_cache_config(args.config)

    # Initialize manager
    manager = CacheManager(config=config, data_dir=args.data_dir)

    print("Monitoring cache performance (Ctrl+C to stop)...")
    print("Interval: {} seconds".format(args.interval))
    print()

    try:
        while True:
            # Get stats
            stats = manager.get_all_stats()

            # Print summary
            print(f"\n[{stats.get('timestamp', 'N/A')}]")

            if "query_cache" in stats:
                qc = stats["query_cache"]
                print(f"  Query Cache: {qc['hit_rate']} hit rate, {qc['entries']} entries")

            if "embedding_cache" in stats:
                ec = stats["embedding_cache"]
                print(f"  Embedding Cache: {ec['hit_rate']} hit rate, {ec['entries']} entries")

            # Wait
            await asyncio.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cache Management Tool for Spine GraphRAG"
    )
    parser.add_argument(
        "--config",
        default="config/cache_config.yaml",
        help="Path to cache config file"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Data directory for cache files"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show cache statistics")
    stats_parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed statistics"
    )

    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear cache")
    clear_parser.add_argument(
        "--type",
        choices=["all", "query", "embedding", "llm"],
        default="all",
        help="Cache type to clear"
    )
    clear_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation"
    )

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up expired entries")

    # Warmup command
    warmup_parser = subparsers.add_parser("warmup", help="Warm up caches")
    warmup_parser.add_argument(
        "--query-cache",
        action="store_true",
        default=True,
        help="Warm up query cache"
    )
    warmup_parser.add_argument(
        "--embedding-cache",
        action="store_true",
        default=True,
        help="Warm up embedding cache"
    )

    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor cache performance")
    monitor_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Monitoring interval (seconds)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Execute command
    if args.command == "stats":
        asyncio.run(cmd_stats(args))
    elif args.command == "clear":
        asyncio.run(cmd_clear(args))
    elif args.command == "cleanup":
        asyncio.run(cmd_cleanup(args))
    elif args.command == "warmup":
        asyncio.run(cmd_warmup(args))
    elif args.command == "monitor":
        asyncio.run(cmd_monitor(args))


if __name__ == "__main__":
    main()
