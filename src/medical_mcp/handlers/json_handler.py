"""JSON Handler for Medical KAG Server.

This module handles JSON file import operations including:
- Pre-extracted JSON file import
- Document ID generation
- Neo4j storage through relationship builder
- Citation processing
"""

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from medical_mcp.medical_kag_server import MedicalKAGServer

from medical_mcp.handlers.utils import generate_document_id
from storage import TextChunk

logger = logging.getLogger(__name__)


class JSONHandler:
    """Handles JSON file import and processing operations."""

    def __init__(self, server: "MedicalKAGServer"):
        """Initialize JSON handler.

        Args:
            server: Parent MedicalKAGServer instance for accessing clients
        """
        self.server = server
        self.neo4j_client = server.neo4j_client
        self.relationship_builder = server.relationship_builder
        self.citation_processor = server.citation_processor

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
        doc_id = generate_document_id(pdf_metadata, path.stem)

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
        if self.neo4j_client and self.relationship_builder:
            try:
                # v7.14.10: dict를 SpineMetadata 객체로 변환
                # server의 헬퍼 함수 사용 또는 직접 변환
                from graph.relationship_builder import SpineMetadata

                # spine_dict에서 SpineMetadata 객체 생성 (필드 매핑 포함)
                pathologies = spine_dict.get('pathologies') or spine_dict.get('pathology', [])
                if isinstance(pathologies, str):
                    pathologies = [pathologies] if pathologies else []

                anatomy_levels = spine_dict.get('anatomy_levels', [])
                if not anatomy_levels:
                    anatomy_level = spine_dict.get('anatomy_level', '')
                    anatomy_region = spine_dict.get('anatomy_region', '')
                    anatomy_levels = []
                    if anatomy_level:
                        anatomy_levels.append(anatomy_level)
                    if anatomy_region and anatomy_region != anatomy_level:
                        anatomy_levels.append(anatomy_region)

                # outcomes 변환
                outcomes_data = spine_dict.get('outcomes', [])
                outcomes_dicts = []
                for o in outcomes_data:
                    if isinstance(o, dict):
                        outcomes_dicts.append(o)
                    elif hasattr(o, '__dict__'):
                        outcomes_dicts.append({
                            'name': getattr(o, 'name', ''),
                            'p_value': getattr(o, 'p_value', ''),
                            'direction': getattr(o, 'direction', ''),
                            'is_significant': getattr(o, 'is_significant', False),
                        })

                spine_metadata = SpineMetadata(
                    sub_domain=spine_dict.get('sub_domain', 'Unknown'),
                    sub_domains=spine_dict.get('sub_domains', []),
                    anatomy_levels=anatomy_levels,
                    interventions=spine_dict.get('interventions', []),
                    pathologies=pathologies,
                    outcomes=outcomes_dicts,
                    surgical_approach=spine_dict.get('surgical_approach', []),
                    main_conclusion=spine_dict.get('main_conclusion', ''),
                    # v7.2 Extended entities
                    patient_cohorts=spine_dict.get('patient_cohorts', []),
                    followups=spine_dict.get('followups', []),
                    costs=spine_dict.get('costs', []),
                    quality_metrics=spine_dict.get('quality_metrics', []),
                )

                neo4j_result = await self.relationship_builder.build_from_paper(
                    paper_id=doc_id,
                    metadata=meta_dict,
                    spine_metadata=spine_metadata,
                    chunks=chunks_list,
                    owner=getattr(self.server, 'current_user', 'default'),
                    shared=True
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
