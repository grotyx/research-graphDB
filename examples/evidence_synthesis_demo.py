"""Evidence Synthesizer Demo.

메타 분석 수준의 근거 종합 시연.

Requirements:
- Neo4j running with paper data
- Papers with AFFECTS relationships

Usage:
    python examples/evidence_synthesis_demo.py
"""

import asyncio
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient
from solver.evidence_synthesizer import EvidenceSynthesizer


async def demo_basic_synthesis():
    """기본 근거 종합 예시."""
    print("\n" + "="*80)
    print("DEMO 1: Basic Evidence Synthesis")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        # Example 1: TLIF → VAS
        result = await synthesizer.synthesize(
            intervention="TLIF",
            outcome="VAS"
        )

        summary = await synthesizer.generate_summary(result)
        print(summary)

        # Show structured data
        print("\n📋 Structured Result:")
        print(f"  - Direction: {result.direction}")
        print(f"  - Strength: {result.strength.value}")
        print(f"  - GRADE: {result.grade_rating}")
        print(f"  - Papers: {result.paper_count}")
        print(f"  - Heterogeneity: {result.heterogeneity}")
        if result.confidence_interval:
            print(f"  - 95% CI: {result.confidence_interval[0]:.2f} to {result.confidence_interval[1]:.2f}")


async def demo_multiple_outcomes():
    """여러 결과변수에 대한 종합."""
    print("\n" + "="*80)
    print("DEMO 2: Multiple Outcomes for Same Intervention")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        intervention = "UBE"
        outcomes = ["VAS", "ODI", "Complication Rate", "Dural Tear"]

        print(f"🔍 Analyzing {intervention} across multiple outcomes...\n")

        for outcome in outcomes:
            result = await synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome
            )

            print(f"📊 {outcome}:")
            print(f"   Direction: {result.direction} ({result.strength.value})")
            print(f"   GRADE: {result.grade_rating}")
            print(f"   Papers: {result.paper_count}")
            print(f"   Recommendation: {result.recommendation[:100]}...")
            print()


async def demo_comparison():
    """수술법 간 비교."""
    print("\n" + "="*80)
    print("DEMO 3: Intervention Comparison")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        interventions = ["TLIF", "OLIF", "LLIF"]
        outcome = "VAS"

        print(f"🔍 Comparing interventions for {outcome}...\n")

        results = []
        for intervention in interventions:
            result = await synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome
            )
            results.append((intervention, result))

        # Create comparison table
        print(f"{'Intervention':<15} {'Papers':<8} {'Direction':<12} {'Strength':<12} {'GRADE':<6}")
        print("-" * 70)

        for intervention, result in results:
            print(
                f"{intervention:<15} "
                f"{result.paper_count:<8} "
                f"{result.direction:<12} "
                f"{result.strength.value:<12} "
                f"{result.grade_rating:<6}"
            )


async def demo_detailed_evidence():
    """상세 근거 항목 조회."""
    print("\n" + "="*80)
    print("DEMO 4: Detailed Evidence Items")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        result = await synthesizer.synthesize(
            intervention="TLIF",
            outcome="Fusion Rate"
        )

        print(f"📚 Evidence Items for TLIF → Fusion Rate:")
        print(f"   Total: {len(result.evidence_items)} studies\n")

        # Show individual evidence items
        for i, item in enumerate(result.evidence_items[:5], 1):  # First 5
            print(f"{i}. {item.title[:60]}...")
            print(f"   Paper ID: {item.paper_id}")
            print(f"   Year: {item.year}")
            print(f"   Evidence Level: {item.evidence_level} (weight: {item.weight:.1f})")
            print(f"   Value: {item.value:.2f}", end="")
            if item.value_control:
                print(f" (control: {item.value_control:.2f})")
            else:
                print()
            print(f"   Direction: {item.direction} (p={item.p_value:.4f})" if item.p_value else f"   Direction: {item.direction}")
            print(f"   Significant: {'Yes' if item.is_significant else 'No'}")
            print()

        if len(result.evidence_items) > 5:
            print(f"   ... and {len(result.evidence_items) - 5} more studies")


async def demo_grade_methodology():
    """GRADE 방법론 시연."""
    print("\n" + "="*80)
    print("DEMO 5: GRADE Methodology Example")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        # Different quality scenarios
        scenarios = [
            ("TLIF", "VAS"),           # Expected: High quality
            ("UBE", "ODI"),            # Expected: Moderate
            ("Laminectomy", "VAS"),    # Expected: Variable
        ]

        for intervention, outcome in scenarios:
            result = await synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome
            )

            print(f"🔬 {intervention} → {outcome}")
            print(f"   GRADE: {result.grade_rating}")
            print(f"   Strength: {result.strength.value}")
            print(f"   Heterogeneity: {result.heterogeneity}")

            # Explain GRADE rationale
            print(f"   Rationale:")
            if result.evidence_items:
                levels = [item.evidence_level for item in result.evidence_items]
                highest = min(levels)
                print(f"   - Starting quality: {highest} level evidence")
            print(f"   - Consistency: {result.direction}")
            print(f"   - Heterogeneity downgrade: {result.heterogeneity}")
            print(f"   - Final grade: {result.grade_rating}")
            print()


async def demo_pooled_effect():
    """통합 효과 계산 시연."""
    print("\n" + "="*80)
    print("DEMO 6: Pooled Effect Calculation")
    print("="*80 + "\n")

    async with Neo4jClient() as client:
        synthesizer = EvidenceSynthesizer(client)

        result = await synthesizer.synthesize(
            intervention="TLIF",
            outcome="VAS"
        )

        if result.pooled_effect:
            print("📈 Pooled Effect Statistics:")
            print(f"   Mean: {result.pooled_effect.mean:.2f}")
            print(f"   Std Dev: {result.pooled_effect.std:.2f}")
            print(f"   95% CI: ({result.pooled_effect.ci_low:.2f}, {result.pooled_effect.ci_high:.2f})")
            print(f"   N Studies: {result.pooled_effect.n_studies}")
            print()
            print(f"   Formatted: {result.pooled_effect.to_str()}")
        else:
            print("⚠️ No pooled effect available (insufficient data)")


async def main():
    """메인 함수."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("\n" + "="*80)
    print("Evidence Synthesizer Demo")
    print("Meta-Analysis Level Evidence Synthesis for Spine Surgery")
    print("="*80)

    try:
        # Run all demos
        await demo_basic_synthesis()
        await demo_multiple_outcomes()
        await demo_comparison()
        await demo_detailed_evidence()
        await demo_grade_methodology()
        await demo_pooled_effect()

        print("\n" + "="*80)
        print("✅ Demo Complete!")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logging.exception("Demo failed")


if __name__ == "__main__":
    asyncio.run(main())
