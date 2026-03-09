"""Conflict Summary Generator Module.

충돌 결과에 대한 요약을 생성하는 모듈입니다.
ConflictDetector와 분리하여 Single Responsibility Principle을 준수합니다.

Usage:
    generator = ConflictSummaryGenerator()
    summary = generator.generate(conflict_result)
    print(summary)
"""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from solver.conflict_detector import ConflictResult, ConflictSeverity, PaperEvidence


@dataclass
class SummaryConfig:
    """Summary generation configuration.

    Attributes:
        max_papers_shown: Maximum papers to show per direction
        include_interpretation: Include interpretation guide
        include_statistics: Include p-value statistics
        include_recommendations: Include action recommendations
    """
    max_papers_shown: int = 3
    include_interpretation: bool = True
    include_statistics: bool = True
    include_recommendations: bool = True


class ConflictSummaryGenerator:
    """충돌 요약 생성기.

    ConflictResult를 받아 사람이 읽을 수 있는 요약을 생성합니다.

    Example:
        generator = ConflictSummaryGenerator()

        # Basic summary
        summary = generator.generate(conflict_result)

        # Customized summary
        config = SummaryConfig(max_papers_shown=5, include_recommendations=False)
        summary = generator.generate(conflict_result, config)
    """

    # Severity-specific interpretation templates
    INTERPRETATION_TEMPLATES = {
        4: {  # CRITICAL
            "icon": "⚠️",
            "main": "High-quality evidence (RCT/Meta-analysis) shows conflicting results.",
            "action": "Systematic review or additional studies may be needed."
        },
        3: {  # HIGH
            "icon": "⚠️",
            "main": "Moderate-quality evidence shows conflicting results.",
            "action": "Consider patient characteristics and study context."
        },
        2: {  # MEDIUM
            "icon": "⚡",
            "main": "Case-control studies show conflicting results.",
            "action": "Higher-quality studies needed for definitive conclusion."
        },
        1: {  # LOW
            "icon": "ℹ️",
            "main": "Low-quality evidence shows conflicting results.",
            "action": "Interpret with caution due to study design limitations."
        },
    }

    def __init__(self, config: Optional[SummaryConfig] = None):
        """Initialize summary generator.

        Args:
            config: Summary configuration (uses defaults if not provided)
        """
        self.config = config or SummaryConfig()

    def generate(
        self,
        conflict: "ConflictResult",
        config: Optional[SummaryConfig] = None
    ) -> str:
        """Generate conflict summary.

        Args:
            conflict: ConflictResult to summarize
            config: Override default configuration

        Returns:
            Human-readable summary string
        """
        cfg = config or self.config
        lines = []

        # Header
        lines.extend(self._generate_header(conflict))
        lines.append("")

        # Papers reporting improvement
        if conflict.papers_improved:
            lines.extend(
                self._generate_paper_section(
                    "IMPROVEMENT",
                    conflict.papers_improved,
                    cfg
                )
            )
            lines.append("")

        # Papers reporting worsening
        if conflict.papers_worsened:
            lines.extend(
                self._generate_paper_section(
                    "WORSENING",
                    conflict.papers_worsened,
                    cfg
                )
            )
            lines.append("")

        # Papers reporting no change
        if conflict.papers_unchanged:
            lines.append(
                f"Papers reporting NO CHANGE ({len(conflict.papers_unchanged)})"
            )
            lines.append("")

        # Interpretation guide
        if cfg.include_interpretation:
            lines.extend(self._generate_interpretation(conflict))

        return "\n".join(lines)

    def _generate_header(self, conflict: "ConflictResult") -> List[str]:
        """Generate summary header."""
        return [
            f"Conflict detected for {conflict.intervention} → {conflict.outcome}",
            f"Severity: {conflict.severity.label.upper()} (confidence: {conflict.confidence:.0%})",
        ]

    def _generate_paper_section(
        self,
        direction: str,
        papers: List["PaperEvidence"],
        config: SummaryConfig
    ) -> List[str]:
        """Generate paper listing section.

        Args:
            direction: "IMPROVEMENT" or "WORSENING"
            papers: List of papers
            config: Summary configuration

        Returns:
            List of formatted lines
        """
        lines = [f"Papers reporting {direction} ({len(papers)}):"]

        # Sort by evidence level (highest first)
        sorted_papers = sorted(
            papers,
            key=lambda p: p.evidence_score,
            reverse=True
        )

        for paper in sorted_papers[:config.max_papers_shown]:
            sig_marker = "✓" if paper.is_significant else " "

            if config.include_statistics and paper.p_value is not None:
                p_str = f"p={paper.p_value:.3f}"
            else:
                p_str = "p=N/A"

            lines.append(
                f"  [{sig_marker}] {paper.paper_id} "
                f"(Level {paper.evidence_level}, {p_str})"
            )

        # Show count of remaining papers
        remaining = len(papers) - config.max_papers_shown
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")

        return lines

    def _generate_interpretation(
        self,
        conflict: "ConflictResult"
    ) -> List[str]:
        """Generate interpretation guide.

        Args:
            conflict: ConflictResult

        Returns:
            List of interpretation lines
        """
        lines = ["Interpretation:"]

        # Get severity as integer (IntEnum value)
        severity_value = int(conflict.severity)
        template = self.INTERPRETATION_TEMPLATES.get(
            severity_value,
            self.INTERPRETATION_TEMPLATES[1]  # Default to LOW
        )

        lines.append(f"  {template['icon']} {template['main']}")

        if self.config.include_recommendations:
            lines.append(f"  {template['action']}")

        return lines

    def generate_brief(self, conflict: "ConflictResult") -> str:
        """Generate brief one-line summary.

        Args:
            conflict: ConflictResult

        Returns:
            Brief summary string
        """
        return (
            f"{conflict.intervention} → {conflict.outcome}: "
            f"{conflict.severity.label.upper()} conflict "
            f"({len(conflict.papers_improved)} improved vs "
            f"{len(conflict.papers_worsened)} worsened)"
        )

    def generate_json_summary(self, conflict: "ConflictResult") -> dict:
        """Generate JSON-serializable summary.

        Args:
            conflict: ConflictResult

        Returns:
            Dictionary summary
        """
        return {
            "intervention": conflict.intervention,
            "outcome": conflict.outcome,
            "severity": conflict.severity.label,
            "confidence": conflict.confidence,
            "papers": {
                "improved": len(conflict.papers_improved),
                "worsened": len(conflict.papers_worsened),
                "unchanged": len(conflict.papers_unchanged),
                "total": conflict.total_papers,
            },
            "conflict_ratio": conflict.conflict_ratio,
            "highest_evidence": conflict.get_highest_evidence_level(),
            "has_significant_conflict": conflict.has_significant_conflict,
        }
