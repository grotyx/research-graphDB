#!/usr/bin/env python3
"""Batch PDF Ingestion Script.

Process multiple PDFs and ingest into Neo4j + ChromaDB.

Features:
- Batch PDF processing with Gemini Vision
- Automatic graph relationship building
- Vector embedding and ChromaDB storage
- Progress tracking with resume capability
- Configurable concurrency and rate limiting

Usage:
    # Process all PDFs in directory
    python scripts/batch_ingest.py --pdf-dir ./data/papers

    # Resume from checkpoint
    python scripts/batch_ingest.py --pdf-dir ./data/papers --resume --batch-id batch_20251204_120000

    # Dry run (no database writes)
    python scripts/batch_ingest.py --pdf-dir ./data/papers --dry-run

    # Custom configuration
    python scripts/batch_ingest.py \\
        --pdf-dir ./data/papers \\
        --batch-size 10 \\
        --concurrency 3 \\
        --neo4j-uri bolt://localhost:7687 \\
        --chromadb-path ./data/chromadb
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from builder.batch_processor import BatchProcessor, BatchResult
from builder.gemini_vision_processor import VisionProcessorResult
from graph.neo4j_client import Neo4jClient, Neo4jConfig
from graph.relationship_builder import RelationshipBuilder
from storage.vector_db import TieredVectorDB
from core.error_handler import get_error_reporter

logger = logging.getLogger(__name__)


# ========================================================================
# Database Ingestion
# ========================================================================

class DatabaseIngestor:
    """Ingest processed PDFs into Neo4j and ChromaDB."""

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        vector_db: TieredVectorDB,
        relationship_builder: RelationshipBuilder,
    ):
        """Initialize ingestor.

        Args:
            neo4j_client: Neo4j client
            vector_db: ChromaDB vector database
            relationship_builder: Graph relationship builder
        """
        self.neo4j_client = neo4j_client
        self.vector_db = vector_db
        self.relationship_builder = relationship_builder

    async def ingest_result(
        self,
        file_path: str,
        result: VisionProcessorResult,
        dry_run: bool = False
    ) -> dict:
        """Ingest a single processed PDF result.

        Args:
            file_path: PDF file path
            result: Vision processor result
            dry_run: If True, skip database writes

        Returns:
            Ingestion statistics
        """
        stats = {
            "neo4j_nodes": 0,
            "neo4j_relationships": 0,
            "vector_chunks": 0,
            "errors": [],
        }

        if dry_run:
            logger.info(f"DRY RUN: Would ingest {file_path}")
            stats["vector_chunks"] = len(result.chunks)
            return stats

        # Generate paper_id from file path
        paper_id = Path(file_path).stem

        try:
            # 1. Build graph relationships
            logger.info(f"Building graph for {paper_id}...")
            graph_stats = await self.relationship_builder.build_from_paper(
                paper_id=paper_id,
                metadata=result.metadata,
                chunks=result.chunks,
            )

            stats["neo4j_nodes"] = graph_stats.get("nodes_created", 0)
            stats["neo4j_relationships"] = graph_stats.get("relationships_created", 0)

            logger.info(
                f"Graph created: {stats['neo4j_nodes']} nodes, "
                f"{stats['neo4j_relationships']} relationships"
            )

        except Exception as e:
            error_msg = f"Neo4j ingestion failed: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            await get_error_reporter().report(e, context={"paper_id": paper_id})

        try:
            # 2. Add chunks to ChromaDB
            logger.info(f"Adding {len(result.chunks)} chunks to ChromaDB...")

            for chunk in result.chunks:
                # Add tier1 chunks
                if chunk.tier == "tier1":
                    chunk_id = await self.vector_db.add_tier1(
                        content=chunk.content,
                        metadata={
                            "document_id": paper_id,
                            "section": chunk.section_type,
                            "source_type": "paper",
                            "evidence_level": result.metadata.evidence_level,
                            "is_key_finding": chunk.is_key_finding,
                            "has_statistics": bool(chunk.statistics),
                            "keywords": ",".join(chunk.keywords),
                        }
                    )
                # Add tier2 chunks
                else:
                    chunk_id = await self.vector_db.add_tier2(
                        content=chunk.content,
                        metadata={
                            "document_id": paper_id,
                            "section": chunk.section_type,
                            "source_type": "paper",
                            "evidence_level": result.metadata.evidence_level,
                            "is_key_finding": chunk.is_key_finding,
                            "has_statistics": bool(chunk.statistics),
                            "keywords": ",".join(chunk.keywords),
                        }
                    )

                stats["vector_chunks"] += 1

            logger.info(f"ChromaDB: {stats['vector_chunks']} chunks added")

        except Exception as e:
            error_msg = f"ChromaDB ingestion failed: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            await get_error_reporter().report(e, context={"paper_id": paper_id})

        return stats


# ========================================================================
# Main Batch Ingestion
# ========================================================================

async def batch_ingest(args: argparse.Namespace) -> int:
    """Main batch ingestion function.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    logger.info("=" * 80)
    logger.info("Batch PDF Ingestion Started")
    logger.info("=" * 80)
    logger.info(f"PDF Directory: {args.pdf_dir}")
    logger.info(f"Batch Size: {args.batch_size}")
    logger.info(f"Concurrency: {args.concurrency}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Resume: {args.resume}")
    logger.info("=" * 80)

    # 1. Initialize batch processor
    logger.info("Initializing batch processor...")
    processor = BatchProcessor(
        gemini_api_key=args.gemini_api_key or os.getenv("GEMINI_API_KEY"),
        checkpoint_dir=args.checkpoint_dir,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        max_retries=args.max_retries,
        rate_limit_rpm=args.rate_limit_rpm,
    )

    # 2. Process PDFs
    logger.info("Processing PDFs...")
    result: BatchResult = await processor.process_directory(
        pdf_dir=args.pdf_dir,
        batch_id=args.batch_id,
        resume=args.resume,
    )

    # Print processing summary
    summary = result.get_summary()
    logger.info("=" * 80)
    logger.info("PDF Processing Summary")
    logger.info("=" * 80)
    logger.info(f"Total files: {summary['total_files']}")
    logger.info(f"Successful: {summary['successful']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Skipped: {summary['skipped']}")
    logger.info(f"Success rate: {summary['success_rate']:.1f}%")
    logger.info(f"Total time: {summary['total_time']:.1f}s")
    logger.info(f"Avg time per file: {summary['avg_time_per_file']:.1f}s")
    logger.info("=" * 80)

    # Check if processing failed
    if summary['failed'] > 0:
        logger.warning(f"Processing incomplete: {summary['failed']} files failed")
        logger.warning(f"Checkpoint saved: {result.checkpoint_file}")
        logger.warning("Use --resume to continue from checkpoint")

    # 3. Ingest to databases (if not dry run)
    if not args.dry_run and summary['successful'] > 0:
        logger.info("Initializing database connections...")

        # Initialize Neo4j
        neo4j_config = Neo4jConfig(
            uri=args.neo4j_uri,
            username=args.neo4j_username,
            password=args.neo4j_password,
            database=args.neo4j_database,
        )

        async with Neo4jClient(neo4j_config) as neo4j_client:
            # Initialize schema
            await neo4j_client.initialize_schema()

            # Initialize ChromaDB
            vector_db = TieredVectorDB(persist_directory=args.chromadb_path)

            # Initialize relationship builder
            relationship_builder = RelationshipBuilder(neo4j_client)

            # Initialize ingestor
            ingestor = DatabaseIngestor(neo4j_client, vector_db, relationship_builder)

            # Ingest successful results
            logger.info("=" * 80)
            logger.info("Database Ingestion Started")
            logger.info("=" * 80)

            total_stats = {
                "neo4j_nodes": 0,
                "neo4j_relationships": 0,
                "vector_chunks": 0,
                "errors": [],
            }

            for i, processed in enumerate(result.processed_files, 1):
                if not processed.success:
                    continue

                logger.info(
                    f"Ingesting {i}/{summary['successful']}: "
                    f"{Path(processed.file_path).name}"
                )

                stats = await ingestor.ingest_result(
                    file_path=processed.file_path,
                    result=processed.result,
                    dry_run=args.dry_run,
                )

                # Accumulate stats
                total_stats["neo4j_nodes"] += stats["neo4j_nodes"]
                total_stats["neo4j_relationships"] += stats["neo4j_relationships"]
                total_stats["vector_chunks"] += stats["vector_chunks"]
                total_stats["errors"].extend(stats["errors"])

            # Print ingestion summary
            logger.info("=" * 80)
            logger.info("Database Ingestion Summary")
            logger.info("=" * 80)
            logger.info(f"Neo4j Nodes: {total_stats['neo4j_nodes']}")
            logger.info(f"Neo4j Relationships: {total_stats['neo4j_relationships']}")
            logger.info(f"ChromaDB Chunks: {total_stats['vector_chunks']}")
            logger.info(f"Errors: {len(total_stats['errors'])}")
            logger.info("=" * 80)

    # 4. Final status
    if summary['failed'] == 0:
        logger.info("Batch ingestion completed successfully!")
        return 0
    else:
        logger.error("Batch ingestion completed with errors")
        return 1


# ========================================================================
# CLI
# ========================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch PDF ingestion for Spine GraphRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required
    parser.add_argument(
        "--pdf-dir",
        type=str,
        required=True,
        help="Directory containing PDF files",
    )

    # Batch processing options
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of PDFs per batch (default: 10)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Maximum concurrent PDF processing (default: 3)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per file (default: 3)",
    )
    parser.add_argument(
        "--rate-limit-rpm",
        type=int,
        default=60,
        help="API requests per minute limit (default: 60)",
    )

    # Checkpoint options
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="./checkpoints",
        help="Directory for checkpoint files (default: ./checkpoints)",
    )
    parser.add_argument(
        "--batch-id",
        type=str,
        default=None,
        help="Batch identifier (auto-generated if not specified)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint",
    )

    # Database options
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j connection URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-username",
        type=str,
        default=os.getenv("NEO4J_USERNAME", "neo4j"),
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.getenv("NEO4J_PASSWORD", "password"),
        help="Neo4j password (default: password)",
    )
    parser.add_argument(
        "--neo4j-database",
        type=str,
        default=os.getenv("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name (default: neo4j)",
    )
    parser.add_argument(
        "--chromadb-path",
        type=str,
        default="./data/chromadb",
        help="ChromaDB persist directory (default: ./data/chromadb)",
    )

    # API keys
    parser.add_argument(
        "--gemini-api-key",
        type=str,
        default=None,
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )

    # Other options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process PDFs but don't write to databases",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Run batch ingestion
    exit_code = asyncio.run(batch_ingest(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
