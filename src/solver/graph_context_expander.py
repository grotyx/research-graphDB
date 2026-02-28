"""Graph Context Expander for IS_A Hierarchy Traversal.

엔티티의 IS_A 계층을 활용하여 쿼리 컨텍스트를 확장.
모든 엔티티 타입 지원: Intervention, Pathology, Outcome, Anatomy.

예: "TLIF" → ["TLIF", "MIS-TLIF", "Interbody Fusion", "Fusion Surgery"]
예: "Spinal Stenosis" → ["Spinal Stenosis", "Lumbar Stenosis", "Degenerative Spine"]
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.bounded_cache import BoundedCache

logger = logging.getLogger(__name__)

# Valid entity types matching taxonomy_manager.py
VALID_ENTITY_TYPES = frozenset({"Intervention", "Pathology", "Outcome", "Anatomy"})


@dataclass
class ExpandedContext:
    """확장된 컨텍스트."""
    original_interventions: list[str] = field(default_factory=list)
    expanded_interventions: list[str] = field(default_factory=list)  # includes original + parents + children
    original_pathologies: list[str] = field(default_factory=list)
    expanded_pathologies: list[str] = field(default_factory=list)
    original_outcomes: list[str] = field(default_factory=list)
    expanded_outcomes: list[str] = field(default_factory=list)
    original_anatomies: list[str] = field(default_factory=list)
    expanded_anatomies: list[str] = field(default_factory=list)

    # Hierarchy info (name -> [parent1, parent2, ...] or [child1, child2, ...])
    intervention_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    pathology_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    outcome_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    anatomy_hierarchy: dict[str, list[str]] = field(default_factory=dict)


class GraphContextExpander:
    """IS_A 계층 기반 컨텍스트 확장기.

    모든 엔티티 타입(Intervention, Pathology, Outcome, Anatomy)의
    IS_A 계층 탐색을 통해 쿼리 컨텍스트를 확장합니다.
    """

    def __init__(self, neo4j_client):
        """Initialize with Neo4j client.

        Args:
            neo4j_client: Neo4jClient instance (can be sync or async)
        """
        self.client = neo4j_client
        self._cache = BoundedCache(maxsize=500)  # entity -> [variants]

    # ================================================================
    # GENERIC ENTITY EXPANSION
    # ================================================================

    async def _expand_up(
        self,
        entity_name: str,
        entity_type: str,
        max_depth: int = 3,
    ) -> list[str]:
        """Get parent entities (up the IS_A hierarchy).

        Args:
            entity_name: Starting entity name
            entity_type: Entity type label (Intervention, Pathology, Outcome, Anatomy)
            max_depth: Maximum depth to traverse

        Returns:
            List of parent entity names (excluding original)
        """
        if entity_type not in VALID_ENTITY_TYPES:
            logger.warning(f"Invalid entity_type '{entity_type}' for expand_up")
            return []

        cache_key = f"up_{entity_type}_{entity_name}_{max_depth}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Clamp max_depth to safe range (1-5)
        max_depth = min(max(int(max_depth), 1), 5)

        query = f"""
        MATCH (i:{entity_type} {{name: $name}})
        OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:{entity_type})
        WHERE length(path) <= $max_depth
        RETURN DISTINCT parent.name as parent_name
        """
        try:
            results = await self.client.run_query(query, {
                "name": entity_name,
                "max_depth": max_depth
            })
            parents = [r["parent_name"] for r in results if r.get("parent_name")]
            self._cache.set(cache_key, parents)
            return parents
        except Exception as e:
            logger.warning(f"Failed to expand up for {entity_type}:{entity_name}: {e}")
            return []

    async def _expand_down(
        self,
        entity_name: str,
        entity_type: str,
        max_depth: int = 2,
    ) -> list[str]:
        """Get child entities (down the IS_A hierarchy).

        Args:
            entity_name: Starting entity name
            entity_type: Entity type label (Intervention, Pathology, Outcome, Anatomy)
            max_depth: Maximum depth to traverse

        Returns:
            List of child entity names (excluding original)
        """
        if entity_type not in VALID_ENTITY_TYPES:
            logger.warning(f"Invalid entity_type '{entity_type}' for expand_down")
            return []

        cache_key = f"down_{entity_type}_{entity_name}_{max_depth}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Clamp max_depth to safe range (1-5)
        max_depth = min(max(int(max_depth), 1), 5)

        query = f"""
        MATCH (i:{entity_type} {{name: $name}})
        OPTIONAL MATCH path = (child:{entity_type})-[:IS_A*1..5]->(i)
        WHERE length(path) <= $max_depth
        RETURN DISTINCT child.name as child_name
        """
        try:
            results = await self.client.run_query(query, {
                "name": entity_name,
                "max_depth": max_depth
            })
            children = [r["child_name"] for r in results if r.get("child_name")]
            self._cache.set(cache_key, children)
            return children
        except Exception as e:
            logger.warning(f"Failed to expand down for {entity_type}:{entity_name}: {e}")
            return []

    async def expand_by_ontology(
        self,
        entity_name: str,
        entity_type: str,
        depth: int = 2,
    ) -> list[str]:
        """Expand entity by ontology to include hierarchy variants.

        Generic dispatch method that works for all entity types.

        Args:
            entity_name: Starting entity name
            entity_type: Entity type ("Intervention", "Pathology", "Outcome", "Anatomy")
            depth: Maximum depth to traverse in both directions

        Returns:
            List of all variant names including original
        """
        variants = {entity_name}

        parents = await self._expand_up(entity_name, entity_type, max_depth=depth)
        variants.update(parents)

        children = await self._expand_down(entity_name, entity_type, max_depth=depth)
        variants.update(children)

        return list(variants)

    # ================================================================
    # INTERVENTION-SPECIFIC METHODS (backward compatible)
    # ================================================================

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
        return await self._expand_up(intervention_name, "Intervention", max_depth)

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
        return await self._expand_down(intervention_name, "Intervention", max_depth)

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

    # ================================================================
    # PATHOLOGY-SPECIFIC METHODS
    # ================================================================

    async def expand_pathology_up(
        self,
        name: str,
        max_depth: int = 3,
    ) -> list[str]:
        """Get parent pathologies (up the IS_A hierarchy).

        Args:
            name: Starting pathology name
            max_depth: Maximum depth to traverse

        Returns:
            List of parent pathology names (excluding original)
        """
        return await self._expand_up(name, "Pathology", max_depth)

    async def expand_pathology_down(
        self,
        name: str,
        max_depth: int = 2,
    ) -> list[str]:
        """Get child pathologies (down the IS_A hierarchy).

        Args:
            name: Starting pathology name
            max_depth: Maximum depth to traverse

        Returns:
            List of child pathology names (excluding original)
        """
        return await self._expand_down(name, "Pathology", max_depth)

    # ================================================================
    # OUTCOME-SPECIFIC METHODS
    # ================================================================

    async def expand_outcome_up(
        self,
        name: str,
        max_depth: int = 3,
    ) -> list[str]:
        """Get parent outcomes (up the IS_A hierarchy).

        Args:
            name: Starting outcome name
            max_depth: Maximum depth to traverse

        Returns:
            List of parent outcome names (excluding original)
        """
        return await self._expand_up(name, "Outcome", max_depth)

    async def expand_outcome_down(
        self,
        name: str,
        max_depth: int = 2,
    ) -> list[str]:
        """Get child outcomes (down the IS_A hierarchy).

        Args:
            name: Starting outcome name
            max_depth: Maximum depth to traverse

        Returns:
            List of child outcome names (excluding original)
        """
        return await self._expand_down(name, "Outcome", max_depth)

    # ================================================================
    # ANATOMY-SPECIFIC METHODS
    # ================================================================

    async def expand_anatomy_up(
        self,
        name: str,
        max_depth: int = 3,
    ) -> list[str]:
        """Get parent anatomies (up the IS_A hierarchy).

        Args:
            name: Starting anatomy name
            max_depth: Maximum depth to traverse

        Returns:
            List of parent anatomy names (excluding original)
        """
        return await self._expand_up(name, "Anatomy", max_depth)

    async def expand_anatomy_down(
        self,
        name: str,
        max_depth: int = 2,
    ) -> list[str]:
        """Get child anatomies (down the IS_A hierarchy).

        Args:
            name: Starting anatomy name
            max_depth: Maximum depth to traverse

        Returns:
            List of child anatomy names (excluding original)
        """
        return await self._expand_down(name, "Anatomy", max_depth)

    # ================================================================
    # FULL QUERY CONTEXT EXPANSION
    # ================================================================

    async def expand_query_context(
        self,
        interventions: list[str],
        pathologies: list[str] = None,
        outcomes: list[str] = None,
        anatomies: list[str] = None,
        direction: str = "both",
        max_depth: int = 2
    ) -> ExpandedContext:
        """Expand full query context across all entity types.

        Args:
            interventions: List of intervention names
            pathologies: List of pathology names (optional)
            outcomes: List of outcome names (optional)
            anatomies: List of anatomy names (optional)
            direction: IS_A traversal direction
            max_depth: Maximum depth

        Returns:
            ExpandedContext with all expansions
        """
        pathologies = pathologies or []
        outcomes = outcomes or []
        anatomies = anatomies or []

        context = ExpandedContext(
            original_interventions=interventions.copy(),
            original_pathologies=pathologies.copy(),
            original_outcomes=outcomes.copy(),
            original_anatomies=anatomies.copy(),
        )

        # Expand interventions
        all_interventions = set(interventions)
        for intervention in interventions:
            variants = await self.expand_intervention(intervention, direction, max_depth)
            all_interventions.update(variants)
            context.intervention_hierarchy[intervention] = variants
        context.expanded_interventions = list(all_interventions)

        # Expand pathologies
        all_pathologies = set(pathologies)
        for pathology in pathologies:
            variants = await self.expand_by_ontology(pathology, "Pathology", max_depth)
            all_pathologies.update(variants)
            context.pathology_hierarchy[pathology] = variants
        context.expanded_pathologies = list(all_pathologies)

        # Expand outcomes
        all_outcomes = set(outcomes)
        for outcome in outcomes:
            variants = await self.expand_by_ontology(outcome, "Outcome", max_depth)
            all_outcomes.update(variants)
            context.outcome_hierarchy[outcome] = variants
        context.expanded_outcomes = list(all_outcomes)

        # Expand anatomies
        all_anatomies = set(anatomies)
        for anatomy in anatomies:
            variants = await self.expand_by_ontology(anatomy, "Anatomy", max_depth)
            all_anatomies.update(variants)
            context.anatomy_hierarchy[anatomy] = variants
        context.expanded_anatomies = list(all_anatomies)

        logger.info(
            f"Expanded context: "
            f"{len(interventions)} → {len(context.expanded_interventions)} interventions, "
            f"{len(pathologies)} → {len(context.expanded_pathologies)} pathologies, "
            f"{len(outcomes)} → {len(context.expanded_outcomes)} outcomes, "
            f"{len(anatomies)} → {len(context.expanded_anatomies)} anatomies"
        )

        return context

    def clear_cache(self):
        """Clear the expansion cache."""
        self._cache.clear()
