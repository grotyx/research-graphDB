"""Demonstration of Inference Engine capabilities.

이 스크립트는 추론 엔진의 다양한 기능을 시연합니다:
1. Transitive hierarchy (계층 구조 추론)
2. Comparability analysis (비교 가능성 분석)
3. Evidence aggregation (근거 집계)
4. Conflict detection (상충 탐지)

Usage:
    python scripts/demo_inference_engine.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient
from graph.inference_rules import InferenceEngine


async def demo_transitive_hierarchy():
    """Demo: Transitive hierarchy reasoning."""
    print("\n" + "=" * 80)
    print("DEMO 1: Transitive Hierarchy Reasoning")
    print("=" * 80)

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Example 1: Find all ancestors of TLIF
            print("\n1. TLIF Ancestors (Transitive IS_A relationships):")
            print("-" * 80)
            ancestors = await engine.get_ancestors("TLIF")

            if ancestors:
                for ancestor in ancestors:
                    print(f"   Distance {ancestor['distance']}: {ancestor['ancestor']}")
                    print(f"      Full name: {ancestor.get('full_name', 'N/A')}")
                    print(f"      Category: {ancestor.get('category', 'N/A')}")
                    print(f"      Path: {' → '.join(ancestor['path_nodes'])}")
                    print()
            else:
                print("   No ancestors found (Taxonomy may not be initialized)")

            # Example 2: Find all descendants of Fusion Surgery
            print("\n2. Fusion Surgery Descendants:")
            print("-" * 80)
            descendants = await engine.get_descendants("Fusion Surgery")

            if descendants:
                print(f"   Found {len(descendants)} descendants:\n")
                for desc in descendants[:10]:  # Show top 10
                    print(f"   Distance {desc['distance']}: {desc['descendant']}")
                    print(f"      {desc.get('full_name', 'N/A')}\n")
            else:
                print("   No descendants found")


async def demo_comparability():
    """Demo: Intervention comparability analysis."""
    print("\n" + "=" * 80)
    print("DEMO 2: Intervention Comparability Analysis")
    print("=" * 80)

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Example 1: Strict comparability (same parent)
            print("\n1. Interventions Comparable to TLIF (Strict - Same Parent):")
            print("-" * 80)
            comparable_strict = await engine.get_comparable_interventions("TLIF", strict=True)

            if comparable_strict:
                for comp in comparable_strict:
                    print(f"   • {comp['comparable']}")
                    print(f"     Full name: {comp.get('full_name', 'N/A')}")
                    print(f"     Approach: {comp.get('approach', 'N/A')}")
                    print(f"     MIS: {comp.get('is_minimally_invasive', 'N/A')}")
                    print(f"     Shared category: {comp.get('shared_category', 'N/A')}")
                    print()
            else:
                print("   No comparable interventions found")

            # Example 2: Broad comparability (same category)
            print("\n2. Interventions Comparable to TLIF (Broad - Same Category):")
            print("-" * 80)
            comparable_broad = await engine.get_comparable_interventions("TLIF", strict=False)

            if comparable_broad:
                print(f"   Found {len(comparable_broad)} comparable interventions\n")
                for comp in comparable_broad[:10]:  # Show top 10
                    print(f"   • {comp['comparable']} ({comp.get('approach', 'N/A')})")
            else:
                print("   No comparable interventions found")

            # Example 3: Find comparison papers
            print("\n3. Papers Comparing TLIF with Other Interventions:")
            print("-" * 80)
            papers = await engine.find_comparison_studies("TLIF")

            if papers:
                for paper in papers:
                    print(f"   • [{paper['year']}] {paper['title']}")
                    print(f"     Evidence: {paper['evidence_level']}")
                    print(f"     Compared with: {', '.join(paper['compared_with'])}")
                    print()
            else:
                print("   No comparison papers found (No data ingested yet)")


async def demo_evidence_aggregation():
    """Demo: Evidence aggregation across hierarchy."""
    print("\n" + "=" * 80)
    print("DEMO 3: Evidence Aggregation")
    print("=" * 80)

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Example 1: Aggregate evidence for specific outcome
            print("\n1. Evidence for TLIF → Fusion Rate (Across Hierarchy):")
            print("-" * 80)
            evidence = await engine.aggregate_evidence("TLIF", "Fusion Rate")

            if evidence:
                for ev in evidence:
                    print(f"   Intervention: {ev['intervention']} (distance: {ev['hierarchy_distance']})")
                    print(f"   Direction: {ev['direction']}")
                    print(f"   Value: {ev.get('value', 'N/A')} (Control: {ev.get('value_control', 'N/A')})")
                    print(f"   p-value: {ev.get('p_value', 'N/A')}")
                    print(f"   Significant: {ev.get('significant', False)}")
                    print(f"   Source: {ev.get('source_paper', 'N/A')}")
                    print()
            else:
                print("   No evidence found (No data ingested yet)")

            # Example 2: All outcomes for intervention
            print("\n2. All Outcomes for UBE:")
            print("-" * 80)
            outcomes = await engine.get_all_outcomes("UBE")

            if outcomes:
                for outcome in outcomes:
                    print(f"   Outcome: {outcome['outcome']} ({outcome['outcome_type']})")
                    print(f"   Unit: {outcome.get('unit', 'N/A')}")
                    print(f"   Desired direction: {outcome.get('desired_direction', 'N/A')}")
                    print(f"   Evidence count: {len(outcome.get('evidence_list', []))}")
                    print()
            else:
                print("   No outcomes found (No data ingested yet)")

            # Example 3: Evidence by pathology
            print("\n3. Evidence for TLIF + Lumbar Stenosis:")
            print("-" * 80)
            evidence_path = await engine.aggregate_evidence_by_pathology(
                "TLIF",
                "Lumbar Stenosis"
            )

            if evidence_path:
                for ev in evidence_path:
                    print(f"   {ev['intervention']} → {ev['outcome']}")
                    print(f"   Direction: {ev['direction']}, Value: {ev.get('value', 'N/A')}")
                    print(f"   p-value: {ev.get('p_value', 'N/A')}")
                    print()
            else:
                print("   No evidence found (No data ingested yet)")


async def demo_conflict_detection():
    """Demo: Conflict detection."""
    print("\n" + "=" * 80)
    print("DEMO 4: Conflict Detection")
    print("=" * 80)

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Example 1: Conflicts for specific intervention-outcome
            print("\n1. Conflicts for UBE → VAS:")
            print("-" * 80)
            conflicts = await engine.detect_conflicts("UBE", "VAS")

            if conflicts:
                for conf in conflicts:
                    print(f"   Conflicting results for {conf['outcome']}:")
                    print(f"   Paper {conf['paper1']}: {conf['direction1']} (value: {conf['value1']}, p={conf['p_value1']})")
                    print(f"   Paper {conf['paper2']}: {conf['direction2']} (value: {conf['value2']}, p={conf['p_value2']})")
                    print()
            else:
                print("   No conflicts found")

            # Example 2: Cross-intervention conflicts
            print("\n2. Cross-Intervention Conflicts for VAS:")
            print("-" * 80)
            cross_conflicts = await engine.detect_cross_intervention_conflicts("VAS")

            if cross_conflicts:
                for conf in cross_conflicts:
                    print(f"   {conf['intervention1']} vs {conf['intervention2']}:")
                    print(f"   {conf['intervention1']}: {conf['direction1']} (p={conf['p_value1']})")
                    print(f"   {conf['intervention2']}: {conf['direction2']} (p={conf['p_value2']})")
                    print()
            else:
                print("   No cross-intervention conflicts found")


async def demo_indirect_treatment():
    """Demo: Indirect treatment relationships."""
    print("\n" + "=" * 80)
    print("DEMO 5: Indirect Treatment Relationships")
    print("=" * 80)

    async with Neo4jClient() as client:
        await client.initialize_schema()

        async with InferenceEngine(client) as engine:
            # Find interventions that indirectly treat Lumbar Stenosis
            print("\n1. Interventions Indirectly Treating Lumbar Stenosis (via hierarchy):")
            print("-" * 80)
            indirect = await engine.find_indirect_treatments("Lumbar Stenosis")

            if indirect:
                for intervention in indirect:
                    print(f"   • {intervention['intervention']}")
                    print(f"     Full name: {intervention.get('full_name', 'N/A')}")
                    print(f"     Via: {intervention['via_intervention']}")
                    print(f"     Distance: {intervention['hierarchy_distance']}")
                    print()
            else:
                print("   No indirect treatments found (Requires TREATS relationships)")

            # Infer treatments via hierarchy
            print("\n2. Inferred Treatments for TLIF:")
            print("-" * 80)
            treatments = await engine.infer_treatments("TLIF")

            if treatments:
                for treatment in treatments:
                    print(f"   • {treatment['pathology']} ({treatment.get('pathology_category', 'N/A')})")
                    print(f"     Via: {treatment['via_intervention']}")
                    print(f"     Distance: {treatment['hierarchy_distance']}")
                    print()
            else:
                print("   No inferred treatments found")


async def demo_rule_inspection():
    """Demo: Inspect available rules."""
    print("\n" + "=" * 80)
    print("DEMO 6: Rule Inspection")
    print("=" * 80)

    async with Neo4jClient() as client:
        async with InferenceEngine(client) as engine:
            print("\nAvailable Inference Rules:")
            print("-" * 80)

            # List all rules
            all_rules = engine.list_rules()
            print(f"\nTotal rules: {len(all_rules)}\n")

            for rule in all_rules:
                print(f"   • {rule.name}")
                print(f"     Type: {rule.rule_type.value}")
                print(f"     Confidence: {rule.confidence_weight}")
                print(f"     Parameters: {', '.join(rule.parameters)}")
                print(f"     Description: {rule.description}")
                print()


async def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("INFERENCE ENGINE DEMONSTRATION")
    print("=" * 80)
    print("\nThis demo shows the capabilities of the Neo4j Inference Engine:")
    print("1. Transitive hierarchy reasoning (IS_A relationships)")
    print("2. Intervention comparability analysis")
    print("3. Evidence aggregation across hierarchy")
    print("4. Conflict detection")
    print("5. Indirect treatment relationships")
    print("6. Rule inspection")

    try:
        # Run demos
        await demo_transitive_hierarchy()
        await demo_comparability()
        await demo_evidence_aggregation()
        await demo_conflict_detection()
        await demo_indirect_treatment()
        await demo_rule_inspection()

        print("\n" + "=" * 80)
        print("DEMO COMPLETE")
        print("=" * 80)
        print("\nNote: Some demos may show 'No data found' if no papers have been ingested.")
        print("To see full functionality, ingest some PDF papers first using:")
        print("  streamlit run web/app.py")
        print("  → Navigate to '1_Documents' → Upload PDF")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
