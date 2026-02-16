"""RelationshipDAO - Relationship operations extracted from Neo4jClient.

Entity relations (Paper->Entity) and Paper-to-Paper relations.
Extracted as part of D-005 God Object decomposition.
"""

import logging
from typing import Any, Callable, Coroutine, Optional

from .spine_schema import CypherTemplates
from core.exceptions import ValidationError, ErrorCode

logger = logging.getLogger(__name__)

# Valid paper-to-paper relation types
_VALID_PAPER_RELATION_TYPES = {
    "SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"
}


class RelationshipDAO:
    """Data Access Object for relationship operations.

    Receives run_query and run_write_query callables from Neo4jClient
    to execute Cypher queries without owning a driver/session.
    """

    def __init__(
        self,
        run_query: Callable[..., Coroutine[Any, Any, list[dict]]],
        run_write_query: Callable[..., Coroutine[Any, Any, dict]],
    ):
        self._run_query = run_query
        self._run_write_query = run_write_query

    # ========================================================================
    # Entity Relations (Paper -> Pathology/Intervention/Outcome/Anatomy)
    # ========================================================================

    async def create_studies_relation(
        self,
        paper_id: str,
        pathology_name: str,
        is_primary: bool = True,
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """논문 -> 질환 관계 생성.

        Args:
            paper_id: 논문 ID
            pathology_name: 질환명
            is_primary: 주요 질환 여부
            snomed_code: SNOMED-CT 코드
            snomed_term: SNOMED-CT 용어

        Returns:
            생성된 관계 정보
        """
        return await self._run_write_query(
            CypherTemplates.CREATE_STUDIES_RELATION,
            {
                "paper_id": paper_id,
                "pathology_name": pathology_name,
                "is_primary": is_primary,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
        )

    async def create_investigates_relation(
        self,
        paper_id: str,
        intervention_name: str,
        is_comparison: bool = False,
        category: Optional[str] = None,
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """논문 -> 수술법 관계 생성.

        Args:
            paper_id: 논문 ID
            intervention_name: 수술법 이름
            is_comparison: 비교군 수술법 여부
            category: 수술법 카테고리
            snomed_code: SNOMED-CT 코드
            snomed_term: SNOMED-CT 용어

        Returns:
            생성된 관계 정보
        """
        return await self._run_write_query(
            CypherTemplates.CREATE_INVESTIGATES_RELATION,
            {
                "paper_id": paper_id,
                "intervention_name": intervention_name,
                "is_comparison": is_comparison,
                "category": category,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
        )

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
        direction: str = "",
        baseline: Optional[float] = None,
        final: Optional[float] = None,
        value_intervention: str = "",
        value_difference: str = "",
        category: str = "",
        timepoint: str = "",
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """수술법 -> 결과 관계 생성 (Unified Schema v4.0).

        Args:
            intervention_name: 수술법 이름
            outcome_name: 결과변수 이름
            source_paper_id: 출처 논문 ID
            value: 측정값
            value_control: 대조군 값
            p_value: p-value
            effect_size: 효과 크기
            confidence_interval: 신뢰구간
            is_significant: 통계적 유의성
            direction: 방향
            baseline: 기준값
            final: 최종값
            value_intervention: 중재군 값
            value_difference: 차이값
            category: 카테고리
            timepoint: 시점
            snomed_code: Outcome SNOMED-CT 코드
            snomed_term: Outcome SNOMED-CT 용어

        Returns:
            생성된 관계 정보
        """
        return await self._run_write_query(
            CypherTemplates.CREATE_AFFECTS_RELATION,
            {
                "intervention_name": intervention_name,
                "outcome_name": outcome_name,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
                "properties": {
                    "source_paper_id": source_paper_id,
                    "value": value,
                    "value_control": value_control,
                    "p_value": p_value,
                    "effect_size": effect_size,
                    "confidence_interval": confidence_interval,
                    "is_significant": is_significant,
                    "direction": direction,
                    "baseline": baseline,
                    "final": final,
                    "value_intervention": value_intervention,
                    "value_difference": value_difference,
                    "category": category,
                    "timepoint": timepoint,
                },
            }
        )

    async def create_treats_relation(
        self,
        intervention_name: str,
        pathology_name: str,
        source_paper_id: str = "",
        indication: str = "",
        contraindication: str = "",
        indication_level: str = "",
    ) -> dict:
        """수술법 -> 질환 치료 관계 생성 (Intervention -> Pathology).

        Args:
            intervention_name: 수술법 이름
            pathology_name: 질환 이름
            source_paper_id: 출처 논문 ID
            indication: 적응증
            contraindication: 금기사항
            indication_level: 적응 수준 (strong/moderate/weak)

        Returns:
            생성된 관계 정보
        """
        return await self._run_write_query(
            CypherTemplates.CREATE_TREATS_RELATION,
            {
                "intervention_name": intervention_name,
                "pathology_name": pathology_name,
                "source_paper_id": source_paper_id,
                "indication": indication[:500] if indication else "",
                "contraindication": contraindication[:500] if contraindication else "",
                "indication_level": indication_level,
            }
        )

    async def create_involves_relation(
        self,
        paper_id: str,
        anatomy_name: str,
        level: str = "",
        region: str = "",
        snomed_code: str | None = None,
        snomed_term: str | None = None,
    ) -> dict:
        """논문 -> 해부학 위치 관계 생성 (Paper -> Anatomy).

        Args:
            paper_id: 논문 ID
            anatomy_name: 해부학적 위치
            level: 척추 레벨
            region: 상세 영역
            snomed_code: SNOMED-CT 코드
            snomed_term: SNOMED-CT 용어

        Returns:
            생성 결과
        """
        return await self._run_write_query(
            CypherTemplates.CREATE_INVOLVES_RELATION,
            {
                "paper_id": paper_id,
                "anatomy_name": anatomy_name,
                "level": level,
                "region": region,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
        )

    # ========================================================================
    # Paper-to-Paper Relations
    # ========================================================================

    async def create_paper_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str,
        confidence: float = 0.0,
        evidence: str = "",
        detected_by: str = ""
    ) -> bool:
        """논문 간 관계 생성.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형 (SUPPORTS, CONTRADICTS, SIMILAR_TOPIC, EXTENDS, CITES, REPLICATES)
            confidence: 관계 신뢰도 (0.0-1.0)
            evidence: 근거 텍스트
            detected_by: 탐지 방법

        Returns:
            성공 여부

        Raises:
            ValidationError: Invalid relation_type or confidence
        """
        if relation_type not in _VALID_PAPER_RELATION_TYPES:
            raise ValidationError(
                message=f"Invalid relation_type: {relation_type}. Must be one of {_VALID_PAPER_RELATION_TYPES}",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        if not 0.0 <= confidence <= 1.0:
            raise ValidationError(
                message=f"Invalid confidence: {confidence}. Must be between 0.0 and 1.0",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})
        MATCH (b:Paper {{paper_id: $target_id}})
        MERGE (a)-[r:{relation_type}]->(b)
        SET r.confidence = $confidence,
            r.evidence = $evidence,
            r.detected_by = $detected_by,
            r.created_at = datetime()
        RETURN r
        """

        try:
            result = await self._run_write_query(
                query,
                {
                    "source_id": source_paper_id,
                    "target_id": target_paper_id,
                    "confidence": confidence,
                    "evidence": evidence,
                    "detected_by": detected_by,
                }
            )
            return result.get("relationships_created", 0) > 0 or result.get("properties_set", 0) > 0
        except Exception as e:
            logger.error(f"Failed to create paper relation: {e}", exc_info=True)
            raise

    async def create_supports_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """SUPPORTS 관계 생성 (convenience wrapper)."""
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="SUPPORTS",
            confidence=confidence,
            evidence=evidence,
            detected_by="citation_parser"
        )

    async def create_contradicts_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """CONTRADICTS 관계 생성 (convenience wrapper)."""
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="CONTRADICTS",
            confidence=confidence,
            evidence=evidence,
            detected_by="citation_parser"
        )

    async def create_cites_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        citation_text: str = "",
        context: str = ""
    ) -> bool:
        """CITES 관계 생성 (convenience wrapper)."""
        evidence = f"{citation_text}\n\nContext: {context}" if context else citation_text
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="CITES",
            confidence=1.0,
            evidence=evidence,
            detected_by="citation_parser"
        )

    # ========================================================================
    # Getters
    # ========================================================================

    async def get_paper_relations(
        self,
        paper_id: str,
        relation_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """논문의 관계 조회.

        Args:
            paper_id: 논문 ID
            relation_types: 관계 유형 필터 (None이면 전체)
            direction: 관계 방향 ("outgoing", "incoming", "both")

        Returns:
            관계 목록

        Raises:
            ValidationError: Invalid direction
        """
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValidationError(
                message=f"Invalid direction: {direction}. Must be 'outgoing', 'incoming', or 'both'",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        rel_type_filter = ""
        if relation_types:
            rel_type_filter = f":{':'.join(relation_types)}"

        if direction == "outgoing":
            query = f"""
            MATCH (p:Paper {{paper_id: $paper_id}})-[r{rel_type_filter}]->(target:Paper)
            RETURN type(r) as relation_type, target, r.confidence as confidence,
                   r.evidence as evidence, r.detected_by as detected_by, r.created_at as created_at
            ORDER BY r.confidence DESC
            """
        elif direction == "incoming":
            query = f"""
            MATCH (source:Paper)-[r{rel_type_filter}]->(p:Paper {{paper_id: $paper_id}})
            RETURN type(r) as relation_type, source as target, r.confidence as confidence,
                   r.evidence as evidence, r.detected_by as detected_by, r.created_at as created_at
            ORDER BY r.confidence DESC
            """
        else:  # both
            query = f"""
            MATCH (p:Paper {{paper_id: $paper_id}})
            CALL {{
                WITH p
                MATCH (p)-[r{rel_type_filter}]->(target:Paper)
                RETURN type(r) as relation_type, target, r.confidence as confidence,
                       r.evidence as evidence, r.detected_by as detected_by,
                       r.created_at as created_at, 'outgoing' as direction
                UNION
                WITH p
                MATCH (source:Paper)-[r{rel_type_filter}]->(p)
                RETURN type(r) as relation_type, source as target, r.confidence as confidence,
                       r.evidence as evidence, r.detected_by as detected_by,
                       r.created_at as created_at, 'incoming' as direction
            }}
            RETURN relation_type, target, confidence, evidence, detected_by, created_at, direction
            ORDER BY confidence DESC
            """

        return await self._run_query(query, {"paper_id": paper_id})

    async def get_related_papers(
        self,
        paper_id: str,
        relation_type: str,
        min_confidence: float = 0.0,
        limit: int = 10
    ) -> list[dict]:
        """특정 관계 유형의 관련 논문 조회.

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형
            min_confidence: 최소 신뢰도
            limit: 최대 결과 수

        Returns:
            관련 논문 목록

        Raises:
            ValidationError: Invalid relation_type
        """
        if relation_type not in _VALID_PAPER_RELATION_TYPES:
            raise ValidationError(
                message=f"Invalid relation_type: {relation_type}. Must be one of {_VALID_PAPER_RELATION_TYPES}",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        query = f"""
        MATCH (p:Paper {{paper_id: $paper_id}})-[r:{relation_type}]->(target:Paper)
        WHERE r.confidence >= $min_confidence
        RETURN target, r.confidence as confidence, r.evidence as evidence
        ORDER BY r.confidence DESC
        LIMIT $limit
        """

        return await self._run_query(
            query,
            {"paper_id": paper_id, "min_confidence": min_confidence, "limit": limit}
        )

    async def get_supporting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """지지하는 논문들 조회 (SUPPORTS 관계)."""
        return await self.get_related_papers(paper_id, "SUPPORTS", limit=limit)

    async def get_contradicting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """상충하는 논문들 조회 (CONTRADICTS 관계)."""
        return await self.get_related_papers(paper_id, "CONTRADICTS", limit=limit)

    async def get_similar_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """유사 주제 논문들 조회 (SIMILAR_TOPIC 관계)."""
        return await self.get_related_papers(paper_id, "SIMILAR_TOPIC", limit=limit)

    async def get_citing_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문을 인용한 논문들 조회."""
        query = """
        MATCH (source:Paper)-[r:CITES]->(p:Paper {paper_id: $paper_id})
        RETURN source, r.confidence as confidence, r.evidence as evidence
        ORDER BY source.year DESC
        LIMIT $limit
        """

        return await self._run_query(query, {"paper_id": paper_id, "limit": limit})

    async def get_cited_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문이 인용한 논문들 조회."""
        return await self.get_related_papers(paper_id, "CITES", limit=limit)

    # ========================================================================
    # Management
    # ========================================================================

    async def delete_paper_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str
    ) -> bool:
        """논문 간 관계 삭제.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형

        Returns:
            성공 여부

        Raises:
            ValidationError: Invalid relation_type
        """
        if relation_type not in _VALID_PAPER_RELATION_TYPES:
            raise ValidationError(
                message=f"Invalid relation_type: {relation_type}. Must be one of {_VALID_PAPER_RELATION_TYPES}",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})-[r:{relation_type}]->(b:Paper {{paper_id: $target_id}})
        DELETE r
        """

        try:
            result = await self._run_write_query(
                query,
                {"source_id": source_paper_id, "target_id": target_paper_id}
            )
            return result.get("relationships_deleted", 0) > 0
        except Exception as e:
            logger.error(f"Failed to delete paper relation: {e}", exc_info=True)
            raise

    async def update_paper_relation_confidence(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str,
        new_confidence: float
    ) -> bool:
        """관계 신뢰도 업데이트.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형
            new_confidence: 새 신뢰도 (0.0-1.0)

        Returns:
            성공 여부

        Raises:
            ValidationError: Invalid relation_type or confidence value
        """
        if relation_type not in _VALID_PAPER_RELATION_TYPES:
            raise ValidationError(
                message=f"Invalid relation_type: {relation_type}. Must be one of {_VALID_PAPER_RELATION_TYPES}",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        if not 0.0 <= new_confidence <= 1.0:
            raise ValidationError(
                message=f"Invalid confidence: {new_confidence}. Must be between 0.0 and 1.0",
                error_code=ErrorCode.VAL_INVALID_VALUE,
            )

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})-[r:{relation_type}]->(b:Paper {{paper_id: $target_id}})
        SET r.confidence = $new_confidence,
            r.updated_at = datetime()
        RETURN r
        """

        try:
            result = await self._run_write_query(
                query,
                {
                    "source_id": source_paper_id,
                    "target_id": target_paper_id,
                    "new_confidence": new_confidence,
                }
            )
            return result.get("properties_set", 0) > 0
        except Exception as e:
            logger.error(f"Failed to update paper relation confidence: {e}", exc_info=True)
            raise
