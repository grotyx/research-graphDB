#!/usr/bin/env python3
"""Neo4j Initialization Script for Spine GraphRAG.

스키마 초기화 및 Taxonomy 데이터 로드.

Usage:
    python scripts/init_neo4j.py
    python scripts/init_neo4j.py --skip-taxonomy
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root and src/ to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Load environment variables from .env (override=True to ensure .env takes precedence)
env_file = project_root / '.env'
load_dotenv(env_file, override=True)

from graph.neo4j_client import Neo4jClient, Neo4jConfig
from graph.spine_schema import SpineGraphSchema

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_neo4j(skip_taxonomy: bool = False, enrich_snomed: bool = True) -> None:
    """Neo4j 데이터베이스 초기화.

    Args:
        skip_taxonomy: Taxonomy 데이터 로드 스킵 여부
        enrich_snomed: SNOMED 코드 보강 여부 (기본: True)
    """
    logger.info("=" * 80)
    logger.info("Neo4j Initialization for Spine GraphRAG System")
    logger.info("=" * 80)

    # 1. 환경변수에서 설정 로드
    config = Neo4jConfig.from_env()
    logger.info(f"\nNeo4j Configuration:")
    logger.info(f"  URI: {config.uri}")
    logger.info(f"  Username: {config.username}")
    logger.info(f"  Database: {config.database}")

    # 2. Neo4j 연결
    logger.info("\n[1/4] Connecting to Neo4j...")
    try:
        async with Neo4jClient(config) as client:
            logger.info("✅ Connected successfully")

            # 3. 연결 테스트
            logger.info("\n[2/4] Testing connection...")
            test_result = await client.run_query(
                "RETURN 'Connection OK' as message, datetime() as timestamp",
                fetch_all=False
            )
            if test_result:
                logger.info(f"✅ {test_result[0]['message']}")
                logger.info(f"   Server time: {test_result[0]['timestamp']}")

            # 4. 스키마 초기화
            logger.info("\n[3/4] Initializing schema...")
            logger.info("   - Creating constraints...")
            logger.info("   - Creating indexes...")
            if not skip_taxonomy:
                logger.info("   - Loading taxonomy data...")

            await client.initialize_schema()
            logger.info("✅ Schema initialized successfully")

            # 4-1. SNOMED 코드 보강
            if enrich_snomed:
                logger.info("\n[4/5] Enriching with SNOMED codes...")
                snomed_queries = SpineGraphSchema.get_enrich_snomed_cypher()
                for i, (query, params) in enumerate(snomed_queries, 1):
                    try:
                        await client.run_write_query(query, params)
                        logger.info(f"   - SNOMED batch {i}/{len(snomed_queries)} applied")
                    except Exception as e:
                        logger.warning(f"   - SNOMED batch {i} skipped: {e}")
                logger.info("✅ SNOMED codes enriched")

            # 5. 통계 확인
            logger.info("\n[5/5] Checking graph statistics...")
            stats = await client.get_stats()

            logger.info("\n📊 Graph Statistics:")
            if stats.get("nodes"):
                logger.info("  Nodes:")
                for label, count in stats["nodes"].items():
                    logger.info(f"    - {label}: {count}")
            else:
                logger.info("  Nodes: (empty)")

            if stats.get("relationships"):
                logger.info("  Relationships:")
                for rel_type, count in stats["relationships"].items():
                    logger.info(f"    - {rel_type}: {count}")
            else:
                logger.info("  Relationships: (empty)")

            # 6. 스키마 정보 출력
            logger.info("\n📋 Schema Information:")
            logger.info(f"  Node Labels: {', '.join(SpineGraphSchema.NODE_LABELS)}")
            logger.info(f"  Relationship Types: {len(SpineGraphSchema.RELATIONSHIP_TYPES)}")
            logger.info(f"  Indexes: {len(SpineGraphSchema.INDEXES)}")
            logger.info(f"  Unique Constraints: {len(SpineGraphSchema.UNIQUE_CONSTRAINTS)}")

            # 7. Intervention 계층 확인
            logger.info("\n🏥 Sample Intervention Hierarchy:")
            hierarchy_query = """
            MATCH (i:Intervention {name: 'TLIF'})
            OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
            RETURN i.name as intervention,
                   i.full_name as full_name,
                   [node in nodes(path) | node.name] as hierarchy
            """
            hierarchy_result = await client.run_query(hierarchy_query)
            if hierarchy_result:
                result = hierarchy_result[0]
                logger.info(f"  {result['intervention']} ({result['full_name']})")
                if result['hierarchy']:
                    hierarchy_chain = ' → '.join(result['hierarchy'])
                    logger.info(f"  Hierarchy: {hierarchy_chain}")

            # 8. Outcome 노드 확인
            logger.info("\n📈 Sample Outcomes:")
            outcome_query = """
            MATCH (o:Outcome)
            RETURN o.name as name, o.type as type, o.unit as unit, o.direction as direction
            LIMIT 5
            """
            outcome_results = await client.run_query(outcome_query)
            for outcome in outcome_results:
                logger.info(f"  - {outcome['name']} ({outcome['type']}, {outcome['unit']}, {outcome['direction']})")

            # 9. Pathology 노드 확인
            logger.info("\n🦴 Sample Pathologies:")
            pathology_query = """
            MATCH (p:Pathology)
            RETURN p.name as name, p.category as category, p.snomed_code as snomed_code
            LIMIT 5
            """
            pathology_results = await client.run_query(pathology_query)
            for pathology in pathology_results:
                snomed = pathology.get('snomed_code', '')
                snomed_info = f", SNOMED: {snomed}" if snomed else ""
                logger.info(f"  - {pathology['name']} ({pathology['category']}{snomed_info})")

            # 10. SNOMED 코드 통계
            if enrich_snomed:
                logger.info("\n🏥 SNOMED-CT Coverage:")
                snomed_stats_query = """
                MATCH (i:Intervention) WHERE i.snomed_code IS NOT NULL AND i.snomed_code <> ''
                WITH count(i) as intervention_with_snomed
                MATCH (p:Pathology) WHERE p.snomed_code IS NOT NULL AND p.snomed_code <> ''
                WITH intervention_with_snomed, count(p) as pathology_with_snomed
                MATCH (o:Outcome) WHERE o.snomed_code IS NOT NULL AND o.snomed_code <> ''
                WITH intervention_with_snomed, pathology_with_snomed, count(o) as outcome_with_snomed
                MATCH (a:Anatomy) WHERE a.snomed_code IS NOT NULL AND a.snomed_code <> ''
                RETURN intervention_with_snomed, pathology_with_snomed, outcome_with_snomed, count(a) as anatomy_with_snomed
                """
                snomed_stats = await client.run_query(snomed_stats_query)
                if snomed_stats:
                    stats = snomed_stats[0]
                    logger.info(f"  - Interventions with SNOMED: {stats.get('intervention_with_snomed', 0)}")
                    logger.info(f"  - Pathologies with SNOMED: {stats.get('pathology_with_snomed', 0)}")
                    logger.info(f"  - Outcomes with SNOMED: {stats.get('outcome_with_snomed', 0)}")
                    logger.info(f"  - Anatomies with SNOMED: {stats.get('anatomy_with_snomed', 0)}")

            logger.info("\n" + "=" * 80)
            logger.info("✅ Initialization Complete!")
            logger.info("=" * 80)
            logger.info("\n💡 Next Steps:")
            logger.info("  1. Open Neo4j Browser: http://localhost:7474")
            logger.info("  2. Login with: neo4j / spineGraph2024")
            logger.info("  3. Try a query: MATCH (n) RETURN n LIMIT 25")
            logger.info("\n")

    except Exception as e:
        logger.error(f"\n❌ Initialization failed: {e}")
        logger.error("\n💡 Troubleshooting:")
        logger.error("  1. Check if Neo4j Docker container is running:")
        logger.error("     docker-compose ps")
        logger.error("  2. Check Neo4j logs:")
        logger.error("     docker-compose logs neo4j")
        logger.error("  3. Verify environment variables in .env file:")
        logger.error("     NEO4J_URI=bolt://localhost:7687")
        logger.error("     NEO4J_USERNAME=neo4j")
        logger.error("     NEO4J_PASSWORD=spineGraph2024")
        logger.error("     NEO4J_DATABASE=neo4j")
        raise


async def verify_apoc() -> None:
    """APOC 플러그인 설치 확인."""
    logger.info("\n🔌 Verifying APOC Plugin...")
    config = Neo4jConfig.from_env()

    async with Neo4jClient(config) as client:
        apoc_query = """
        CALL apoc.help('apoc')
        YIELD name
        RETURN count(name) as apoc_functions
        """
        try:
            result = await client.run_query(apoc_query, fetch_all=False)
            if result:
                count = result[0]['apoc_functions']
                logger.info(f"✅ APOC installed: {count} functions available")
        except Exception as e:
            logger.warning(f"⚠️  APOC not available: {e}")
            logger.warning("   (APOC is optional for basic functionality)")


async def reset_database() -> None:
    """데이터베이스 초기화 (모든 노드/관계 삭제).

    경고: 이 함수는 모든 데이터를 삭제합니다!
    """
    logger.warning("\n⚠️  WARNING: This will delete ALL data in Neo4j!")
    confirm = input("Type 'DELETE ALL' to confirm: ")

    if confirm != "DELETE ALL":
        logger.info("Reset cancelled.")
        return

    logger.info("\n🗑️  Deleting all nodes and relationships...")
    config = Neo4jConfig.from_env()

    async with Neo4jClient(config) as client:
        # 배치 삭제 (메모리 효율적)
        delete_query = """
        CALL apoc.periodic.iterate(
            "MATCH (n) RETURN n",
            "DETACH DELETE n",
            {batchSize: 1000}
        )
        YIELD batches, total
        RETURN batches, total
        """
        try:
            result = await client.run_write_query(delete_query)
            logger.info(f"✅ Deleted nodes: {result}")
        except Exception as e:
            # APOC 없으면 일반 삭제
            logger.warning(f"APOC not available, using standard delete: {e}")
            await client.run_write_query("MATCH (n) DETACH DELETE n")
            logger.info("✅ All data deleted")

        # 재초기화
        logger.info("\n🔄 Re-initializing schema...")
        await client.initialize_schema()
        logger.info("✅ Database reset complete")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Neo4j Initialization for Spine GraphRAG"
    )
    parser.add_argument(
        "--skip-taxonomy",
        action="store_true",
        help="Skip taxonomy data loading"
    )
    parser.add_argument(
        "--skip-snomed",
        action="store_true",
        help="Skip SNOMED-CT code enrichment"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset database (delete all data)"
    )
    parser.add_argument(
        "--verify-apoc",
        action="store_true",
        help="Verify APOC plugin installation"
    )

    args = parser.parse_args()

    try:
        if args.verify_apoc:
            asyncio.run(verify_apoc())
        elif args.reset:
            asyncio.run(reset_database())
        else:
            asyncio.run(init_neo4j(
                skip_taxonomy=args.skip_taxonomy,
                enrich_snomed=not args.skip_snomed
            ))
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
