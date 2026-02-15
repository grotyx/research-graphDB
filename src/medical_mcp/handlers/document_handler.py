"""Document management handler for Medical KAG MCP Server.

Handles document listing, statistics, deletion, and database reset operations.
"""

import logging
from typing import Optional, Any

logger = logging.getLogger("medical-kag")


class DocumentHandler:
    """Handler for document management operations.

    Manages document CRUD operations, statistics retrieval, and database maintenance
    for the Medical KAG system using Neo4j as the backend storage.

    Attributes:
        server: Reference to the MedicalKAGServer instance
        neo4j_client: Neo4j client from server
        current_user: Current user ID for access control
    """

    def __init__(self, server):
        """Initialize DocumentHandler.

        Args:
            server: MedicalKAGServer instance to access shared resources
        """
        self.server = server
        self.neo4j_client = server.neo4j_client
        self.current_user = server.current_user

    def _get_user_filter_clause(self, alias: str = "p") -> tuple[str, dict]:
        """Get user filtering Cypher WHERE clause.

        Delegates to server's method for consistent user filtering logic.
        Returns parameterized clause to prevent Cypher injection.

        Args:
            alias: Paper node alias (default: 'p')

        Returns:
            (Cypher WHERE clause string, parameters dict) tuple
        """
        return self.server._get_user_filter_clause(alias)

    async def list_documents(self) -> dict:
        """저장된 문서 목록 (Neo4j 전용 v5.3, 멀티유저 v1.5).

        Retrieves list of documents (Papers) from Neo4j with chunk counts and metadata.
        Applies user-based filtering to show only owned or shared documents.

        Returns:
            dict: Result containing:
                - success (bool): Operation success status
                - stats (dict): Storage backend and counts
                - documents (list): List of document records with metadata
                - total_documents (int): Total document count
                - total_chunks (int): Total chunk count across all documents
                - tier_distribution (dict): Chunk counts by tier (tier1, tier2)
                - error (str, optional): Error message if operation failed
        """
        try:
            if not self.neo4j_client:
                return {"success": False, "error": "Neo4j client not available"}

            # Neo4j에서 문서(Paper) 및 청크 정보 조회
            documents = []
            async with self.neo4j_client as client:
                # v1.5: 사용자 필터링 적용, v1.15: 파라미터화
                user_filter, filter_params = self._get_user_filter_clause("p")

                # Paper 노드 조회 (청크 수 포함)
                query = f"""
                MATCH (p:Paper)
                {user_filter}
                OPTIONAL MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
                WITH p, count(c) as chunk_count,
                     sum(CASE WHEN c.tier = 'tier1' THEN 1 ELSE 0 END) as tier1_count,
                     sum(CASE WHEN c.tier = 'tier2' THEN 1 ELSE 0 END) as tier2_count
                RETURN p.paper_id as document_id,
                       p.title as title,
                       p.year as year,
                       p.evidence_level as evidence_level,
                       p.source as source,
                       p.owner as owner,
                       p.shared as shared,
                       chunk_count,
                       tier1_count,
                       tier2_count
                ORDER BY p.created_at DESC
                """
                result = await client.run_query(query, filter_params)

                for record in result:
                    documents.append({
                        "document_id": record["document_id"],
                        "chunk_count": record["chunk_count"] or 0,
                        "tier1_chunks": record["tier1_count"] or 0,
                        "tier2_chunks": record["tier2_count"] or 0,
                        "owner": record.get("owner", "system"),        # v1.5
                        "shared": record.get("shared", True),          # v1.5
                        "metadata": {
                            "title": record.get("title", ""),
                            "year": record.get("year", 0),
                            "evidence_level": record.get("evidence_level", ""),
                            "source": record.get("source", ""),
                            "owner": record.get("owner", "system"),    # v1.5
                            "shared": record.get("shared", True)       # v1.5
                        }
                    })

            # 통계 계산
            total_chunks = sum(d.get("chunk_count", 0) for d in documents)
            tier1_total = sum(d.get("tier1_chunks", 0) for d in documents)
            tier2_total = sum(d.get("tier2_chunks", 0) for d in documents)

            return {
                "success": True,
                "stats": {
                    "storage_backend": "neo4j",
                    "document_count": len(documents),
                    "chunk_count": total_chunks
                },
                "documents": documents,
                "total_documents": len(documents),
                "total_chunks": total_chunks,
                "tier_distribution": {
                    "tier1": tier1_total,
                    "tier2": tier2_total
                }
            }
        except Exception as e:
            logger.error(f"list_documents error: {e}")
            return {"success": False, "error": str(e)}

    async def get_stats(self) -> dict:
        """시스템 통계 조회 (Neo4j 전용 v5.3).

        Retrieves system-wide statistics including document counts, chunk counts,
        and tier distribution. Does not apply user filtering - shows global stats.

        Returns:
            dict: Statistics containing:
                - document_count (int): Total number of papers
                - chunk_count (int): Total number of chunks
                - tier1_count (int): Number of tier1 chunks
                - tier2_count (int): Number of tier2 chunks
                - llm_enabled (bool): LLM availability status
                - neo4j_available (bool): Neo4j connection status
                - storage_backend (str): Storage backend identifier
        """
        try:
            if not self.neo4j_client:
                return {
                    "document_count": 0,
                    "chunk_count": 0,
                    "tier1_count": 0,
                    "tier2_count": 0,
                    "llm_enabled": self.server.enable_llm,
                    "neo4j_available": False,
                    "storage_backend": "neo4j"
                }

            # Neo4j에서 통계 조회
            async with self.neo4j_client as client:
                query = """
                MATCH (p:Paper)
                WITH count(p) as paper_count
                OPTIONAL MATCH (c:Chunk)
                WITH paper_count, count(c) as chunk_count,
                     sum(CASE WHEN c.tier = 'tier1' THEN 1 ELSE 0 END) as tier1_count,
                     sum(CASE WHEN c.tier = 'tier2' THEN 1 ELSE 0 END) as tier2_count
                RETURN paper_count, chunk_count, tier1_count, tier2_count
                """
                result = await client.run_query(query)

                if result:
                    record = result[0]
                    return {
                        "document_count": record.get("paper_count", 0) or 0,
                        "chunk_count": record.get("chunk_count", 0) or 0,
                        "tier1_count": record.get("tier1_count", 0) or 0,
                        "tier2_count": record.get("tier2_count", 0) or 0,
                        "llm_enabled": self.server.enable_llm,
                        "neo4j_available": True,
                        "storage_backend": "neo4j"
                    }
                else:
                    return {
                        "document_count": 0,
                        "chunk_count": 0,
                        "tier1_count": 0,
                        "tier2_count": 0,
                        "llm_enabled": self.server.enable_llm,
                        "neo4j_available": True,
                        "storage_backend": "neo4j"
                    }
        except Exception as e:
            logger.warning(f"Get stats error: {e}")
            return {
                "document_count": 0,
                "chunk_count": 0,
                "tier1_count": 0,
                "tier2_count": 0,
                "llm_enabled": self.server.enable_llm,
                "neo4j_available": False,
                "storage_backend": "neo4j"
            }

    async def delete_document(self, document_id: str) -> dict:
        """문서 삭제 (Neo4j 전용 v5.3).

        Deletes a document and all associated nodes and relationships from Neo4j.
        This includes the Paper node, all Chunk nodes, and their relationships.

        Args:
            document_id: 삭제할 문서 ID

        Returns:
            dict: Deletion result containing:
                - success (bool): Operation success status
                - document_id (str): ID of deleted document
                - deleted_chunks (int): Number of chunks deleted
                - neo4j_nodes (int): Total nodes deleted
                - neo4j_relationships (int): Total relationships deleted
                - storage_backend (str): Storage backend identifier
                - error (str, optional): Error message if operation failed
        """
        try:
            logger.info(f"Deleting document: {document_id}")

            if not self.neo4j_client:
                return {"success": False, "error": "Neo4j client not available"}

            # Authorization check: verify ownership before deletion
            async with self.neo4j_client as client:
                paper = await client.get_paper(document_id)
                if paper:
                    paper_owner = paper.get("owner", "system")
                    current_user = self.server.current_user
                    if current_user != "system" and paper_owner != current_user:
                        logger.warning(
                            f"Access denied: user '{current_user}' cannot delete "
                            f"document '{document_id}' owned by '{paper_owner}'"
                        )
                        return {
                            "success": False,
                            "error": f"Access denied: document owned by '{paper_owner}'"
                        }

            # Neo4j에서 Paper 노드, Chunk 노드 및 관계 삭제
            neo4j_result = {
                "nodes_deleted": 0,
                "relationships_deleted": 0,
                "chunks_deleted": 0
            }

            async with self.neo4j_client as client:
                # 먼저 청크 수 확인
                chunk_query = """
                MATCH (p:Paper {paper_id: $paper_id})-[:HAS_CHUNK]->(c:Chunk)
                RETURN count(c) as chunk_count
                """
                chunk_result = await client.run_query(chunk_query, {"paper_id": document_id})
                chunks_count = chunk_result[0].get("chunk_count", 0) if chunk_result else 0

                # Paper 및 관련 노드/관계 삭제
                delete_result = await client.delete_paper(document_id)
                neo4j_result = {
                    "nodes_deleted": delete_result.get("nodes_deleted", 0),
                    "relationships_deleted": delete_result.get("relationships_deleted", 0),
                    "chunks_deleted": chunks_count
                }
                logger.info(
                    f"Neo4j: Deleted {neo4j_result['nodes_deleted']} nodes, "
                    f"{neo4j_result['relationships_deleted']} relationships, "
                    f"{neo4j_result['chunks_deleted']} chunks for {document_id}"
                )

            return {
                "success": True,
                "document_id": document_id,
                "deleted_chunks": neo4j_result["chunks_deleted"],
                "neo4j_nodes": neo4j_result["nodes_deleted"],
                "neo4j_relationships": neo4j_result["relationships_deleted"],
                "storage_backend": "neo4j"
            }
        except Exception as e:
            logger.error(f"Document deletion failed: {e}")
            return {"success": False, "error": str(e)}

    async def reset_database(self, include_taxonomy: bool = False) -> dict:
        """전체 데이터베이스 리셋 (Neo4j 전용 v5.3).

        Resets the entire database by deleting all Papers and related data.
        Optionally includes taxonomy data (Pathology, Intervention nodes).

        Args:
            include_taxonomy: Taxonomy도 삭제할지 여부 (기본값: False)

        Returns:
            dict: Reset result containing:
                - success (bool): Operation success status
                - neo4j_nodes_deleted (int): Total nodes deleted
                - neo4j_relationships_deleted (int): Total relationships deleted
                - taxonomy_cleared (bool): Whether taxonomy was included in reset
                - storage_backend (str): Storage backend identifier
                - error (str, optional): Error message if operation failed
        """
        try:
            logger.warning(f"Database reset requested (include_taxonomy={include_taxonomy})")

            # Authorization check: only system user can reset the database
            if self.server.current_user != "system":
                logger.warning(
                    f"Access denied: user '{self.server.current_user}' "
                    f"attempted database reset"
                )
                return {
                    "success": False,
                    "error": "Access denied: only system user can reset the database"
                }

            if not self.neo4j_client:
                return {"success": False, "error": "Neo4j client not available"}

            # Neo4j 초기화
            neo4j_result = {
                "nodes_deleted": 0,
                "relationships_deleted": 0
            }

            async with self.neo4j_client as client:
                if include_taxonomy:
                    neo4j_result = await client.clear_all_including_taxonomy()
                    # 스키마 재초기화
                    await client.initialize_schema()
                    logger.info("Neo4j: Full database cleared (including taxonomy) and schema reinitialized")
                else:
                    neo4j_result = await client.clear_database()
                    logger.info("Neo4j: Papers and related data cleared (taxonomy preserved)")

            return {
                "success": True,
                "neo4j_nodes_deleted": neo4j_result.get("nodes_deleted", 0),
                "neo4j_relationships_deleted": neo4j_result.get("relationships_deleted", 0),
                "taxonomy_cleared": include_taxonomy,
                "storage_backend": "neo4j"
            }
        except Exception as e:
            logger.error(f"Database reset failed: {e}")
            return {"success": False, "error": str(e)}

    async def export_document(self, document_id: str) -> dict:
        """저장된 문서를 JSON으로 내보냅니다 (Neo4j 전용 v5.3).

        Neo4j에서 데이터를 추출하여 data/extracted/ 폴더에 저장합니다.
        완전한 원본 복원은 불가능하지만, 재사용 가능한 형식으로 내보냅니다.

        Args:
            document_id: 내보낼 문서 ID

        Returns:
            내보내기 결과
        """
        import json
        from pathlib import Path
        from datetime import datetime

        if not document_id:
            return {"success": False, "error": "document_id가 필요합니다."}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        # Neo4j에서 Paper 정보 및 청크 추출
        chunks_data = []
        metadata = {}
        spine_metadata = {}

        try:
            async with self.neo4j_client as client:
                # Paper 노드 및 청크 정보 조회
                query = """
                MATCH (p:Paper {paper_id: $paper_id})
                OPTIONAL MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
                OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
                OPTIONAL MATCH (p)-[:INVESTIGATES]->(int:Intervention)
                OPTIONAL MATCH (p)-[:REPORTS]->(out:Outcome)
                WITH p, c,
                     collect(DISTINCT path.name) as pathologies,
                     collect(DISTINCT int.name) as interventions,
                     collect(DISTINCT out.name) as outcomes
                RETURN p.paper_id as paper_id,
                       p.title as title,
                       p.year as year,
                       p.authors as authors,
                       p.journal as journal,
                       p.doi as doi,
                       p.evidence_level as evidence_level,
                       p.study_type as study_type,
                       p.sub_domain as sub_domain,
                       p.anatomy_level as anatomy_level,
                       pathologies, interventions, outcomes,
                       c.chunk_id as chunk_id,
                       c.content as chunk_content,
                       c.tier as chunk_tier,
                       c.section as chunk_section,
                       c.is_key_finding as chunk_is_key_finding,
                       c.chunk_index as chunk_index
                ORDER BY c.chunk_index
                """
                result = await client.run_query(query, {"paper_id": document_id})

                if not result:
                    return {"success": False, "error": f"문서를 찾을 수 없습니다: {document_id}"}

                # 첫 번째 레코드에서 메타데이터 추출
                first_row = result[0]
                metadata = {
                    "title": first_row.get("title", ""),
                    "authors": first_row.get("authors", []) or [],
                    "year": first_row.get("year", 0) or 0,
                    "journal": first_row.get("journal", ""),
                    "doi": first_row.get("doi", ""),
                    "study_type": first_row.get("study_type", ""),
                    "evidence_level": first_row.get("evidence_level", "")
                }

                spine_metadata = {
                    "sub_domain": first_row.get("sub_domain", ""),
                    "anatomy_level": first_row.get("anatomy_level", ""),
                    "pathology": first_row.get("pathologies", []) or [],
                    "interventions": first_row.get("interventions", []) or [],
                    "outcomes": first_row.get("outcomes", []) or []
                }

                # 청크 데이터 수집
                for row in result:
                    if row.get("chunk_content"):
                        chunks_data.append({
                            "content": row.get("chunk_content", ""),
                            "section_type": row.get("chunk_section", ""),
                            "content_type": "text",
                            "tier": row.get("chunk_tier", "tier2"),
                            "is_key_finding": row.get("chunk_is_key_finding", False),
                            "summary": "",
                            "keywords": [],
                            "statistics": {}
                        })

        except Exception as e:
            logger.error(f"Neo4j 추출 실패: {e}")
            return {"success": False, "error": f"Neo4j 추출 실패: {e}"}

        # JSON 구조 생성
        export_data = {
            "metadata": metadata,
            "spine_metadata": spine_metadata,
            "chunks": chunks_data,
            "important_citations": [],  # 원본에서 복원 불가
            "_export_info": {
                "exported_at": datetime.now().isoformat(),
                "document_id": document_id,
                "chunks_count": len(chunks_data),
                "storage_backend": "neo4j",
                "note": "Neo4j에서 추출됨 (v5.3). 일부 원본 데이터는 복원되지 않음."
            }
        }

        # 파일 저장
        try:
            extracted_dir = Path("data/extracted")
            extracted_dir.mkdir(parents=True, exist_ok=True)

            safe_title = "".join(c for c in metadata.get("title", "unknown")[:50] if c.isalnum() or c in " -_").strip()
            safe_title = safe_title.replace(" ", "_") or "unknown"
            year = metadata.get("year", "0000")
            json_filename = f"{year}_{safe_title}_exported.json"

            json_path = extracted_dir / json_filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            return {
                "success": True,
                "document_id": document_id,
                "exported_to": str(json_path),
                "chunks_count": len(chunks_data),
                "has_neo4j_data": bool(spine_metadata),
                "note": "일부 원본 데이터(outcomes 상세, complications 등)는 복원되지 않습니다."
            }
        except Exception as e:
            return {"success": False, "error": f"파일 저장 실패: {e}"}
