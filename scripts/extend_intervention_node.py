#!/usr/bin/env python3
"""Script to extend InterventionNode with TechniqueNode and SurgicalStepNode fields."""

import re
from pathlib import Path

# File path
SCHEMA_FILE = Path(__file__).parent.parent / "src" / "graph" / "spine_schema.py"

# New InterventionNode class definition
NEW_INTERVENTION_NODE = '''@dataclass
class InterventionNode:
    """수술/치료법 노드.

    Neo4j Label: Intervention

    v1.1: Extended with TechniqueNode and SurgicalStepNode fields.
    """
    name: str  # TLIF, OLIF, UBE, Laminectomy
    full_name: str = ""
    category: str = ""  # InterventionCategory value
    approach: str = ""  # anterior, posterior, lateral
    is_minimally_invasive: bool = False
    snomed_code: str = ""  # SNOMED-CT Concept ID
    snomed_term: str = ""  # SNOMED-CT Preferred Term
    aliases: list[str] = field(default_factory=list)

    # Technique fields (merged from TechniqueNode - v1.1)
    technique_description: str = ""  # Detailed technique description
    difficulty_level: str = ""  # basic, intermediate, advanced
    pearls: list[str] = field(default_factory=list)  # Surgical tips
    pitfalls: list[str] = field(default_factory=list)  # Cautions
    learning_curve_cases: int = 0  # Number of cases for learning curve

    # Surgical step fields (merged from SurgicalStepNode - v1.1)
    surgical_steps: list[dict] = field(default_factory=list)  # [{"step": 1, "name": "...", "description": "..."}]

    # Required resources (v1.1)
    required_implants: list[str] = field(default_factory=list)  # ["Pedicle Screw", "PEEK Cage"]
    required_instruments: list[str] = field(default_factory=list)  # ["Kerrison Rongeur"]

    # Billing/coding (v1.1)
    cpt_code: str = ""  # CPT procedure code

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "category": self.category,
            "approach": self.approach,
            "is_minimally_invasive": self.is_minimally_invasive,
            "snomed_code": self.snomed_code,
            "snomed_term": self.snomed_term,
            "aliases": self.aliases,
            # Technique fields
            "technique_description": self.technique_description[:2000] if self.technique_description else "",
            "difficulty_level": self.difficulty_level,
            "pearls": self.pearls[:20],
            "pitfalls": self.pitfalls[:20],
            "learning_curve_cases": self.learning_curve_cases,
            # Surgical steps
            "surgical_steps": self.surgical_steps[:30],  # Limit to 30 steps
            # Required resources
            "required_implants": self.required_implants[:20],
            "required_instruments": self.required_instruments[:20],
            # Billing
            "cpt_code": self.cpt_code,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "InterventionNode":
        return cls(
            name=record.get("name", ""),
            full_name=record.get("full_name", ""),
            category=record.get("category", ""),
            approach=record.get("approach", ""),
            is_minimally_invasive=record.get("is_minimally_invasive", False),
            snomed_code=record.get("snomed_code", ""),
            snomed_term=record.get("snomed_term", ""),
            aliases=record.get("aliases", []),
            # Technique fields
            technique_description=record.get("technique_description", ""),
            difficulty_level=record.get("difficulty_level", ""),
            pearls=record.get("pearls", []),
            pitfalls=record.get("pitfalls", []),
            learning_curve_cases=record.get("learning_curve_cases", 0),
            # Surgical steps
            surgical_steps=record.get("surgical_steps", []),
            # Required resources
            required_implants=record.get("required_implants", []),
            required_instruments=record.get("required_instruments", []),
            # Billing
            cpt_code=record.get("cpt_code", ""),
        )
'''

# TechniqueNode deprecation comment
TECHNIQUE_DEPRECATION = '''@dataclass
class TechniqueNode:
    """수술 테크닉 노드 (v1.1).

    Neo4j Label: Technique

    DEPRECATED: This node type is deprecated in favor of InterventionNode.technique_description
    and InterventionNode.surgical_steps fields. Use InterventionNode with the extended fields instead.

    구체적인 수술 기법/테크닉 설명.
    예: "Rod Contouring", "Pedicle Screw Insertion", "Cage Placement"

    Relationships:
        - (Paper)-[:DESCRIBES]->(Technique)
        - (Intervention)-[:USES_TECHNIQUE]->(Technique)
        - (Technique)-[:REQUIRES]->(Instrument|Implant)
    """'''

# SurgicalStepNode deprecation comment
SURGICAL_STEP_DEPRECATION = '''@dataclass
class SurgicalStepNode:
    """수술 단계 노드 (v1.1).

    Neo4j Label: SurgicalStep

    DEPRECATED: This node type is deprecated in favor of InterventionNode.surgical_steps field.
    Use InterventionNode with the surgical_steps list field instead:
    surgical_steps = [{"step": 1, "name": "...", "description": "...", "duration_minutes": ...}]

    수술의 단계별 설명.
    예: "Patient Positioning", "Exposure", "Decompression", "Fusion", "Closure"

    Relationships:
        - (Intervention)-[:HAS_STEP]->(SurgicalStep)
        - (SurgicalStep)-[:NEXT]->(SurgicalStep)
        - (SurgicalStep)-[:USES]->(Instrument|Implant)
    """'''


def main():
    """Execute the schema extension."""
    print(f"Reading {SCHEMA_FILE}...")
    content = SCHEMA_FILE.read_text()

    # 1. Replace InterventionNode class
    print("Replacing InterventionNode class...")
    pattern = r'@dataclass\nclass InterventionNode:.*?(?=\n\n@dataclass\nclass OutcomeNode:)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("ERROR: Could not find InterventionNode class")
        return 1

    content = content[:match.start()] + NEW_INTERVENTION_NODE + content[match.end():]
    print(f"  Replaced InterventionNode ({len(NEW_INTERVENTION_NODE)} chars)")

    # 2. Add deprecation to TechniqueNode
    print("Adding deprecation comment to TechniqueNode...")
    pattern = r'@dataclass\nclass TechniqueNode:\n    """수술 테크닉 노드 \(v7\.1\)\.\n\n    Neo4j Label: Technique\n\n    구체적인 수술 기법/테크닉 설명\.'
    match = re.search(pattern, content)
    if not match:
        print("ERROR: Could not find TechniqueNode class")
        return 1

    old_docstring_end = content.find('    """', match.start() + 50)  # Find end of docstring
    content = content[:match.start()] + TECHNIQUE_DEPRECATION[:TECHNIQUE_DEPRECATION.find('구체적인')] + content[old_docstring_end-4:]
    print("  Added deprecation comment to TechniqueNode")

    # 3. Add deprecation to SurgicalStepNode
    print("Adding deprecation comment to SurgicalStepNode...")
    pattern = r'@dataclass\nclass SurgicalStepNode:\n    """수술 단계 노드 \(v7\.1\)\.\n\n    Neo4j Label: SurgicalStep\n\n    수술의 단계별 설명\.'
    match = re.search(pattern, content)
    if not match:
        print("ERROR: Could not find SurgicalStepNode class")
        return 1

    old_docstring_end = content.find('    """', match.start() + 50)  # Find end of docstring
    content = content[:match.start()] + SURGICAL_STEP_DEPRECATION[:SURGICAL_STEP_DEPRECATION.find('수술의 단계별')] + content[old_docstring_end-4:]
    print("  Added deprecation comment to SurgicalStepNode")

    # Write back
    print(f"Writing updated content to {SCHEMA_FILE}...")
    SCHEMA_FILE.write_text(content)
    print("SUCCESS: Schema extended successfully!")
    print("\nChanges made:")
    print("  1. Extended InterventionNode with 9 new fields")
    print("  2. Added deprecation comment to TechniqueNode")
    print("  3. Added deprecation comment to SurgicalStepNode")
    return 0


if __name__ == "__main__":
    exit(main())
