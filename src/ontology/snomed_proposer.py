"""LLM-based SNOMED mapping proposer for unregistered terms.

When entity_normalizer fails to find a match for a term, this module uses
an LLM to propose a SNOMED mapping by:
1. Finding the closest existing parent in the SNOMED hierarchy
2. Generating a proposed extension code
3. Suggesting synonyms, abbreviations, and Korean term
4. Rating confidence in the mapping

Confidence thresholds:
- >= 0.9: auto-apply (log to review queue)
- 0.7-0.9: user approval needed
- < 0.7: manual review required

Usage:
    proposer = SNOMEDProposer(llm_client)
    proposal = await proposer.propose_mapping("MISS-TLIF", "intervention")
    if proposal.auto_apply:
        # Apply to spine_snomed_mappings.py
        ...
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from .spine_snomed_mappings import (
    SPINE_INTERVENTION_SNOMED,
    SPINE_PATHOLOGY_SNOMED,
    SPINE_OUTCOME_SNOMED,
    SPINE_ANATOMY_SNOMED,
    EXTENSION_RANGES,
    EXTENSION_NAMESPACE,
    SNOMEDMapping,
    SNOMEDSemanticType,
)

logger = logging.getLogger(__name__)

# Entity type to mapping dict + extension range key
_ENTITY_CONFIG = {
    "intervention": {
        "mapping": SPINE_INTERVENTION_SNOMED,
        "range_key": "procedure",
        "range_key_ext": "procedure_ext",
        "range_key_ext2": "procedure_ext2",
        "semantic_type": SNOMEDSemanticType.PROCEDURE,
    },
    "pathology": {
        "mapping": SPINE_PATHOLOGY_SNOMED,
        "range_key": "disorder",
        "range_key_ext": "disorder_ext",
        "semantic_type": SNOMEDSemanticType.DISORDER,
    },
    "outcome": {
        "mapping": SPINE_OUTCOME_SNOMED,
        "range_key": "observable",
        "range_key_ext": "observable_ext",
        "semantic_type": SNOMEDSemanticType.OBSERVABLE_ENTITY,
    },
    "anatomy": {
        "mapping": SPINE_ANATOMY_SNOMED,
        "range_key": "body_structure",
        "range_key_ext": None,
        "semantic_type": SNOMEDSemanticType.BODY_STRUCTURE,
    },
}


@dataclass
class SNOMEDProposal:
    """Proposed SNOMED mapping for an unregistered term."""
    original_term: str
    entity_type: str  # intervention, pathology, outcome, anatomy
    proposed_parent_code: str = ""
    proposed_parent_name: str = ""
    proposed_code: str = ""  # extension code
    proposed_term: str = ""  # preferred term
    proposed_synonyms: list[str] = field(default_factory=list)
    proposed_abbreviations: list[str] = field(default_factory=list)
    proposed_korean_term: str = ""
    confidence: float = 0.0  # 0.0-1.0
    reasoning: str = ""
    auto_apply: bool = False  # True if confidence >= 0.9


_PROPOSE_MAPPING_PROMPT = """You are a spine surgery SNOMED-CT terminology expert.

An unregistered term was found during paper processing. Propose a SNOMED mapping.

**Unregistered term**: "{term}"
**Entity type**: {entity_type}
**Context**: {context}

**Existing parent concepts** (closest matches in our hierarchy):
{parent_candidates}

**Instructions**:
1. Identify the most appropriate parent concept from the list above
2. Propose a preferred term (FSN without semantic tag)
3. Suggest synonyms (English), abbreviations, and Korean term
4. Rate your confidence (0.0-1.0):
   - 0.9+: Definite match to a known medical concept
   - 0.7-0.89: Probable match, but needs verification
   - <0.7: Uncertain or novel concept

Respond in JSON only:
{{
    "parent_name": "exact name from parent list or null",
    "preferred_term": "Full preferred term",
    "synonyms": ["syn1", "syn2"],
    "abbreviations": ["ABBR1"],
    "korean_term": "Korean translation",
    "confidence": 0.85,
    "reasoning": "Brief explanation"
}}"""


class SNOMEDProposer:
    """Proposes SNOMED mappings for unregistered terms using LLM."""

    def __init__(self, llm_client=None):
        """Initialize proposer.

        Args:
            llm_client: LLM client instance (BaseLLMClient). If None,
                        will attempt to create one on first use.
        """
        self._llm_client = llm_client

    async def _get_llm_client(self):
        """Lazy-initialize LLM client."""
        if self._llm_client is None:
            try:
                from llm import LLMClient
                self._llm_client = LLMClient()
            except ImportError:
                raise RuntimeError("LLM client not available. Install llm package.")
        return self._llm_client

    async def propose_mapping(
        self,
        term: str,
        entity_type: str,
        context: str = "",
    ) -> SNOMEDProposal:
        """Use LLM to propose a SNOMED mapping for an unregistered term.

        Args:
            term: The unregistered term
            entity_type: Entity type (intervention, pathology, outcome, anatomy)
            context: Optional context from the paper

        Returns:
            SNOMEDProposal with confidence-rated mapping
        """
        entity_type_lower = entity_type.lower()
        config = _ENTITY_CONFIG.get(entity_type_lower)
        if not config:
            return SNOMEDProposal(
                original_term=term,
                entity_type=entity_type,
                reasoning=f"Unknown entity type: {entity_type}",
            )

        # Find closest parent candidates
        parent_candidates = self._find_parent_candidates(term, entity_type_lower)

        # Format prompt
        prompt = _PROPOSE_MAPPING_PROMPT.format(
            term=term,
            entity_type=entity_type,
            context=context or "No additional context",
            parent_candidates="\n".join(
                f"- {name} (code: {code})" for name, code in parent_candidates
            ) or "No parent candidates found",
        )

        # Call LLM
        try:
            client = await self._get_llm_client()
            response = await client.generate_json(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "parent_name": {"type": ["string", "null"]},
                        "preferred_term": {"type": "string"},
                        "synonyms": {"type": "array", "items": {"type": "string"}},
                        "abbreviations": {"type": "array", "items": {"type": "string"}},
                        "korean_term": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["preferred_term", "confidence", "reasoning"],
                },
            )
        except Exception as e:
            logger.warning(f"LLM proposal failed for '{term}': {e}")
            return SNOMEDProposal(
                original_term=term,
                entity_type=entity_type,
                reasoning=f"LLM call failed: {e}",
            )

        # Build proposal
        parent_name = response.get("parent_name") or ""
        parent_code = ""
        if parent_name:
            mapping = config["mapping"]
            parent_mapping = mapping.get(parent_name)
            if parent_mapping:
                parent_code = parent_mapping.code

        confidence = min(max(response.get("confidence", 0.0), 0.0), 1.0)
        ext_code = self._generate_extension_code(entity_type_lower)

        return SNOMEDProposal(
            original_term=term,
            entity_type=entity_type,
            proposed_parent_code=parent_code,
            proposed_parent_name=parent_name,
            proposed_code=ext_code,
            proposed_term=response.get("preferred_term", term),
            proposed_synonyms=response.get("synonyms", []),
            proposed_abbreviations=response.get("abbreviations", []),
            proposed_korean_term=response.get("korean_term", ""),
            confidence=confidence,
            reasoning=response.get("reasoning", ""),
            auto_apply=confidence >= 0.9,
        )

    async def batch_propose(
        self,
        terms: list[dict],
    ) -> list[SNOMEDProposal]:
        """Propose mappings for multiple terms.

        Args:
            terms: List of dicts with keys: original_text, entity_type,
                   and optional source_paper

        Returns:
            List of SNOMEDProposal objects
        """
        # Parallel LLM calls with concurrency limit
        sem = asyncio.Semaphore(5)

        async def _bounded_propose(term_info: dict) -> SNOMEDProposal:
            async with sem:
                return await self.propose_mapping(
                    term=term_info["original_text"],
                    entity_type=term_info["entity_type"],
                    context=term_info.get("source_paper", ""),
                )

        proposals = await asyncio.gather(
            *[_bounded_propose(t) for t in terms]
        )
        return list(proposals)

    def _find_parent_candidates(
        self,
        term: str,
        entity_type: str,
    ) -> list[tuple[str, str]]:
        """Find the closest existing parents in the SNOMED hierarchy.

        Returns up to 10 candidate (name, code) tuples sorted by relevance.

        Args:
            term: The unregistered term
            entity_type: Entity type key (lowercase)

        Returns:
            List of (name, code) tuples
        """
        config = _ENTITY_CONFIG.get(entity_type)
        if not config:
            return []

        mapping = config["mapping"]
        term_lower = term.lower()
        term_words = set(term_lower.split())

        # Score each mapping entry by word overlap
        scored: list[tuple[float, str, str]] = []
        for name, m in mapping.items():
            name_lower = name.lower()
            name_words = set(name_lower.split())

            # Word overlap score
            overlap = len(term_words & name_words)
            if overlap > 0:
                score = overlap / max(len(term_words), len(name_words))
            else:
                # Check substring match
                if term_lower in name_lower or name_lower in term_lower:
                    score = 0.3
                else:
                    # Check synonym match
                    syn_score = 0.0
                    for syn in m.synonyms:
                        syn_lower = syn.lower()
                        syn_words = set(syn_lower.split())
                        s_overlap = len(term_words & syn_words)
                        if s_overlap > 0:
                            syn_score = max(syn_score, s_overlap / max(len(term_words), len(syn_words)))
                    score = syn_score * 0.8  # Slightly discount synonym matches

            if score > 0.1:
                scored.append((score, name, m.code))

        # Sort by score descending, take top 10
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(name, code) for _, name, code in scored[:10]]

    def _generate_extension_code(self, entity_type: str) -> str:
        """Generate the next available extension code for the entity type.

        Args:
            entity_type: Entity type key (lowercase)

        Returns:
            Next available extension code string
        """
        config = _ENTITY_CONFIG.get(entity_type)
        if not config:
            return ""

        mapping = config["mapping"]
        range_key = config["range_key"]
        range_key_ext = config.get("range_key_ext")

        # Collect all existing extension codes in the primary range
        base_start, base_end = EXTENSION_RANGES[range_key]
        existing_codes: set[int] = set()

        for m in mapping.values():
            if m.is_extension and m.code.startswith(EXTENSION_NAMESPACE):
                try:
                    suffix = int(m.code[len(EXTENSION_NAMESPACE):])
                    existing_codes.add(suffix)
                except ValueError:
                    continue

        # Try primary range first
        for idx in range(base_start, base_end + 1):
            if idx not in existing_codes:
                return f"{EXTENSION_NAMESPACE}{idx}"

        # Try extended range if available
        if range_key_ext and range_key_ext in EXTENSION_RANGES:
            ext_start, ext_end = EXTENSION_RANGES[range_key_ext]
            for idx in range(ext_start, ext_end + 1):
                if idx not in existing_codes:
                    return f"{EXTENSION_NAMESPACE}{idx}"

        # Try second extended range if available (procedure_ext2)
        range_key_ext2 = config.get("range_key_ext2")
        if range_key_ext2 and range_key_ext2 in EXTENSION_RANGES:
            ext2_start, ext2_end = EXTENSION_RANGES[range_key_ext2]
            for idx in range(ext2_start, ext2_end + 1):
                if idx not in existing_codes:
                    return f"{EXTENSION_NAMESPACE}{idx}"

        # Fallback: use max + 1
        if existing_codes:
            return f"{EXTENSION_NAMESPACE}{max(existing_codes) + 1}"

        return f"{EXTENSION_NAMESPACE}{base_start}"
