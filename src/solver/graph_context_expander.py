"""Graph Context Expander for IS_A Hierarchy Traversal.

수술법의 IS_A 계층을 활용하여 쿼리 컨텍스트를 확장.
예: "TLIF" → ["TLIF", "MIS-TLIF", "Interbody Fusion", "Fusion Surgery"]
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.bounded_cache import BoundedCache

logger = logging.getLogger(__name__)


@dataclass
class ExpandedContext:
    """확장된 컨텍스트."""
    original_interventions: list[str] = field(default_factory=list)
    expanded_interventions: list[str] = field(default_factory=list)  # includes original + parents + children
    original_pathologies: list[str] = field(default_factory=list)
    expanded_pathologies: list[str] = field(default_factory=list)
    original_outcomes: list[str] = field(default_factory=list)
    expanded_outcomes: list[str] = field(default_factory=list)

    # Hierarchy info
    intervention_hierarchy: dict[str, list[str]] = field(default_factory=dict)  # name -> [parent1, parent2, ...]


class GraphContextExpander:
    """IS_A 계층 기반 컨텍스트 확장기."""

    def __init__(self, neo4j_client):
        """Initialize with Neo4j client.

        Args:
            neo4j_client: Neo4jClient instance (can be sync or async)
        """
        self.client = neo4j_client
        self._cache = BoundedCache(maxsize=500)  # intervention -> [variants]

    async def expand_intervention_up(
        self,
        intervention_name: str,
        max_depth: int = 3
    ) -> list[str]:
        """Get parent interventions (up the IS_A hierarchy).

        Args:
            intervention_name: Starting intervention
            max_depth: Maximum depth to traverse

        Returns:
            List of parent intervention names (excluding original)
        """
        cache_key = f"up_{intervention_name}_{max_depth}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query = """
        MATCH (i:Intervention {name: $name})
        OPTIONAL MATCH path = (i)-[:IS_A*1..]->(parent:Intervention)
        WHERE length(path) <= $max_depth
        RETURN DISTINCT parent.name as parent_name
        """
        try:
            results = await self.client.run_query(query, {
                "name": intervention_name,
                "max_depth": max_depth
            })
            parents = [r["parent_name"] for r in results if r.get("parent_name")]
            self._cache.set(cache_key, parents)
            return parents
        except Exception as e:
            logger.warning(f"Failed to expand up for {intervention_name}: {e}")
            return []

    async def expand_intervention_down(
        self,
        intervention_name: str,
        max_depth: int = 2
    ) -> list[str]:
        """Get child interventions (down the IS_A hierarchy).

        Args:
            intervention_name: Starting intervention
            max_depth: Maximum depth to traverse

        Returns:
            List of child intervention names (excluding original)
        """
        cache_key = f"down_{intervention_name}_{max_depth}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query = """
        MATCH (i:Intervention {name: $name})
        OPTIONAL MATCH path = (child:Intervention)-[:IS_A*1..]->(i)
        WHERE length(path) <= $max_depth
        RETURN DISTINCT child.name as child_name
        """
        try:
            results = await self.client.run_query(query, {
                "name": intervention_name,
                "max_depth": max_depth
            })
            children = [r["child_name"] for r in results if r.get("child_name")]
            self._cache.set(cache_key, children)
            return children
        except Exception as e:
            logger.warning(f"Failed to expand down for {intervention_name}: {e}")
            return []

    async def expand_intervention(
        self,
        intervention_name: str,
        direction: str = "both",
        max_depth: int = 2
    ) -> list[str]:
        """Expand intervention to include hierarchy variants.

        Args:
            intervention_name: Starting intervention name
            direction: "up", "down", or "both"
            max_depth: Maximum depth to traverse

        Returns:
            List of all variant names including original
        """
        variants = [intervention_name]

        if direction in ("up", "both"):
            parents = await self.expand_intervention_up(intervention_name, max_depth)
            variants.extend(parents)

        if direction in ("down", "both"):
            children = await self.expand_intervention_down(intervention_name, max_depth)
            variants.extend(children)

        # Also get aliases from the original intervention
        try:
            alias_query = """
            MATCH (i:Intervention {name: $name})
            RETURN i.aliases as aliases
            """
            results = await self.client.run_query(alias_query, {"name": intervention_name})
            if results and results[0].get("aliases"):
                variants.extend(results[0]["aliases"])
        except Exception as e:
            logger.debug(f"Failed to get aliases for {intervention_name}: {e}")

        return list(set(variants))

    async def expand_query_context(
        self,
        interventions: list[str],
        pathologies: list[str] = None,
        outcomes: list[str] = None,
        direction: str = "both",
        max_depth: int = 2
    ) -> ExpandedContext:
        """Expand full query context.

        Args:
            interventions: List of intervention names
            pathologies: List of pathology names (optional)
            outcomes: List of outcome names (optional)
            direction: IS_A traversal direction
            max_depth: Maximum depth

        Returns:
            ExpandedContext with all expansions
        """
        pathologies = pathologies or []
        outcomes = outcomes or []

        context = ExpandedContext(
            original_interventions=interventions.copy(),
            original_pathologies=pathologies.copy(),
            original_outcomes=outcomes.copy()
        )

        # Expand interventions
        all_interventions = set(interventions)
        for intervention in interventions:
            variants = await self.expand_intervention(intervention, direction, max_depth)
            all_interventions.update(variants)
            context.intervention_hierarchy[intervention] = variants

        context.expanded_interventions = list(all_interventions)

        # For now, pathologies and outcomes pass through
        # (can add similar expansion logic later)
        context.expanded_pathologies = pathologies.copy()
        context.expanded_outcomes = outcomes.copy()

        logger.info(
            f"Expanded context: {len(interventions)} → {len(context.expanded_interventions)} interventions"
        )

        return context

    def clear_cache(self):
        """Clear the expansion cache."""
        self._cache.clear()
