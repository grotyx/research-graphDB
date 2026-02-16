"""Tests for GraphContextExpander.

Query-Driven Schema 개선 프로젝트의 IS_A 계층 기반 컨텍스트 확장 테스트.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from solver.graph_context_expander import (
    GraphContextExpander,
    ExpandedContext,
)


class TestExpandedContext:
    """ExpandedContext 데이터 클래스 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        context = ExpandedContext()

        assert context.original_interventions == []
        assert context.expanded_interventions == []
        assert context.original_pathologies == []
        assert context.expanded_pathologies == []
        assert context.original_outcomes == []
        assert context.expanded_outcomes == []
        assert context.intervention_hierarchy == {}

    def test_with_values(self):
        """값 설정 테스트."""
        context = ExpandedContext(
            original_interventions=["TLIF"],
            expanded_interventions=["TLIF", "MIS-TLIF", "Interbody Fusion"],
            intervention_hierarchy={"TLIF": ["MIS-TLIF", "Interbody Fusion"]}
        )

        assert "TLIF" in context.original_interventions
        assert "MIS-TLIF" in context.expanded_interventions
        assert "Interbody Fusion" in context.expanded_interventions
        assert "TLIF" in context.intervention_hierarchy


class TestGraphContextExpanderInit:
    """GraphContextExpander 초기화 테스트."""

    def test_init_with_client(self):
        """Neo4j 클라이언트로 초기화."""
        mock_client = MagicMock()
        expander = GraphContextExpander(mock_client)

        assert expander.client == mock_client
        assert len(expander._cache) == 0


class TestExpandInterventionUp:
    """상위 계층 확장 테스트."""

    @pytest.fixture
    def mock_client(self):
        """Mock Neo4j 클라이언트."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def expander(self, mock_client):
        return GraphContextExpander(mock_client)

    @pytest.mark.asyncio
    async def test_expand_up_single_parent(self, expander, mock_client):
        """단일 상위 개념 확장."""
        mock_client.run_query.return_value = [
            {"parent_name": "Interbody Fusion"}
        ]

        parents = await expander.expand_intervention_up("TLIF", max_depth=2)

        assert "Interbody Fusion" in parents
        mock_client.run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_up_multiple_parents(self, expander, mock_client):
        """다중 상위 개념 확장."""
        mock_client.run_query.return_value = [
            {"parent_name": "Interbody Fusion"},
            {"parent_name": "Fusion Surgery"},
            {"parent_name": "Spine Surgery"}
        ]

        parents = await expander.expand_intervention_up("TLIF", max_depth=3)

        assert len(parents) == 3
        assert "Interbody Fusion" in parents
        assert "Fusion Surgery" in parents
        assert "Spine Surgery" in parents

    @pytest.mark.asyncio
    async def test_expand_up_no_parents(self, expander, mock_client):
        """상위 개념 없음."""
        mock_client.run_query.return_value = [{"parent_name": None}]

        parents = await expander.expand_intervention_up("Spine Surgery", max_depth=2)

        assert parents == []

    @pytest.mark.asyncio
    async def test_expand_up_caching(self, expander, mock_client):
        """캐싱 동작 테스트."""
        mock_client.run_query.return_value = [{"parent_name": "Interbody Fusion"}]

        # First call - should query
        await expander.expand_intervention_up("TLIF", max_depth=2)
        # Second call - should use cache
        await expander.expand_intervention_up("TLIF", max_depth=2)

        # Should only call Neo4j once
        assert mock_client.run_query.call_count == 1

    @pytest.mark.asyncio
    async def test_expand_up_error_handling(self, expander, mock_client):
        """에러 처리 테스트."""
        mock_client.run_query.side_effect = Exception("Connection error")

        parents = await expander.expand_intervention_up("TLIF")

        assert parents == []  # Should return empty on error


class TestExpandInterventionDown:
    """하위 계층 확장 테스트."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def expander(self, mock_client):
        return GraphContextExpander(mock_client)

    @pytest.mark.asyncio
    async def test_expand_down_multiple_children(self, expander, mock_client):
        """다중 하위 개념 확장."""
        mock_client.run_query.return_value = [
            {"child_name": "TLIF"},
            {"child_name": "PLIF"},
            {"child_name": "ALIF"},
            {"child_name": "OLIF"}
        ]

        children = await expander.expand_intervention_down("Interbody Fusion", max_depth=2)

        assert len(children) == 4
        assert "TLIF" in children
        assert "OLIF" in children


class TestExpandIntervention:
    """양방향 확장 테스트."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def expander(self, mock_client):
        return GraphContextExpander(mock_client)

    @pytest.mark.asyncio
    async def test_expand_both_directions(self, expander, mock_client):
        """양방향 확장."""
        # Mock parent query
        async def mock_query(query, params):
            if "parent" in query.lower():
                return [{"parent_name": "Interbody Fusion"}]
            elif "child" in query.lower():
                return [{"child_name": "MIS-TLIF"}]
            elif "aliases" in query.lower():
                return [{"aliases": ["Transforaminal Lumbar Interbody Fusion"]}]
            return []

        mock_client.run_query.side_effect = mock_query

        variants = await expander.expand_intervention("TLIF", direction="both", max_depth=2)

        # Should include original + parents + children + aliases
        assert "TLIF" in variants  # Original

    @pytest.mark.asyncio
    async def test_expand_up_only(self, expander, mock_client):
        """상위 방향만 확장."""
        mock_client.run_query.return_value = [{"parent_name": "Interbody Fusion"}]

        variants = await expander.expand_intervention("TLIF", direction="up")

        assert "TLIF" in variants
        # Should have called up expansion

    @pytest.mark.asyncio
    async def test_expand_down_only(self, expander, mock_client):
        """하위 방향만 확장."""
        mock_client.run_query.return_value = [{"child_name": "MIS-TLIF"}]

        variants = await expander.expand_intervention("TLIF", direction="down")

        assert "TLIF" in variants


class TestExpandQueryContext:
    """전체 쿼리 컨텍스트 확장 테스트."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def expander(self, mock_client):
        return GraphContextExpander(mock_client)

    @pytest.mark.asyncio
    async def test_expand_multiple_interventions(self, expander, mock_client):
        """다중 수술법 확장."""
        mock_client.run_query.return_value = []  # No expansions for simplicity

        context = await expander.expand_query_context(
            interventions=["UBE", "TLIF"],
            pathologies=["Lumbar Stenosis"],
            outcomes=["VAS", "ODI"]
        )

        # Original should be preserved
        assert "UBE" in context.original_interventions
        assert "TLIF" in context.original_interventions
        assert "Lumbar Stenosis" in context.original_pathologies
        assert "VAS" in context.original_outcomes

        # Expanded should at least include originals
        assert "UBE" in context.expanded_interventions
        assert "TLIF" in context.expanded_interventions

    @pytest.mark.asyncio
    async def test_expand_with_hierarchy(self, expander, mock_client):
        """계층 정보 포함 확장."""
        async def mock_query(query, params):
            intervention = params.get("name", "")
            if "parent" in query.lower():
                if intervention == "TLIF":
                    return [{"parent_name": "Interbody Fusion"}]
            elif "aliases" in query.lower():
                return [{"aliases": None}]
            return []

        mock_client.run_query.side_effect = mock_query

        context = await expander.expand_query_context(
            interventions=["TLIF"],
            direction="up"
        )

        # Should have hierarchy info
        assert "TLIF" in context.intervention_hierarchy


class TestClearCache:
    """캐시 클리어 테스트."""

    def test_clear_cache(self):
        """캐시 클리어."""
        mock_client = MagicMock()
        expander = GraphContextExpander(mock_client)

        # Manually add cache entries
        expander._cache.set("test_key", ["value1", "value2"])

        assert len(expander._cache) == 1

        expander.clear_cache()

        assert len(expander._cache) == 0


class TestIntegrationScenarios:
    """통합 시나리오 테스트."""

    @pytest.fixture
    def mock_client(self):
        """실제 사용 시나리오를 위한 Mock 클라이언트."""
        client = AsyncMock()

        # Simulate realistic IS_A hierarchy
        hierarchy = {
            "UBE": {
                "parents": ["Endoscopic Surgery", "Decompression Surgery"],
                "children": [],
                "aliases": ["BESS", "Biportal Endoscopic"]
            },
            "TLIF": {
                "parents": ["Interbody Fusion", "Fusion Surgery"],
                "children": ["MIS-TLIF", "Open TLIF"],
                "aliases": ["Transforaminal Lumbar Interbody Fusion"]
            },
            "Interbody Fusion": {
                "parents": ["Fusion Surgery", "Spine Surgery"],
                "children": ["TLIF", "PLIF", "ALIF", "OLIF", "LLIF"],
                "aliases": []
            }
        }

        async def mock_query(query, params):
            name = params.get("name", "")
            max_depth = params.get("max_depth", 2)

            if name not in hierarchy:
                return []

            if "parent" in query.lower():
                return [{"parent_name": p} for p in hierarchy[name]["parents"]]
            elif "child" in query.lower():
                return [{"child_name": c} for c in hierarchy[name]["children"]]
            elif "aliases" in query.lower():
                aliases = hierarchy[name]["aliases"]
                return [{"aliases": aliases if aliases else None}]
            return []

        client.run_query.side_effect = mock_query
        return client

    @pytest.fixture
    def expander(self, mock_client):
        return GraphContextExpander(mock_client)

    @pytest.mark.asyncio
    async def test_tlif_expansion(self, expander):
        """TLIF 확장 시나리오."""
        context = await expander.expand_query_context(
            interventions=["TLIF"],
            direction="both",
            max_depth=2
        )

        # Should include parents
        assert "Interbody Fusion" in context.expanded_interventions or \
               "Fusion Surgery" in context.expanded_interventions

        # Should include children
        assert "MIS-TLIF" in context.expanded_interventions or \
               "Open TLIF" in context.expanded_interventions

    @pytest.mark.asyncio
    async def test_ube_expansion(self, expander):
        """UBE 확장 시나리오."""
        variants = await expander.expand_intervention("UBE", direction="both")

        # Should include aliases
        assert "UBE" in variants
        assert "BESS" in variants or "Biportal Endoscopic" in variants

    @pytest.mark.asyncio
    async def test_treatment_comparison_context(self, expander):
        """치료 비교 컨텍스트 시나리오."""
        context = await expander.expand_query_context(
            interventions=["UBE", "TLIF"],
            pathologies=["Lumbar Stenosis"],
            direction="both"
        )

        # Both interventions should be expanded
        assert len(context.expanded_interventions) > 2  # More than just originals
        assert len(context.intervention_hierarchy) == 2  # One for each intervention
