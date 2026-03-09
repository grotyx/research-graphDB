"""Conflict Detection Demo.

충돌 감지 모듈 사용 예시:
1. 특정 Intervention-Outcome 쌍의 충돌 탐지
2. 모든 충돌 검색 및 심각도별 분석
3. 충돌 상세 리포트 생성
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph.neo4j_client import Neo4jClient
from solver.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
)


async def demo_specific_conflict():
    """예시 1: 특정 Intervention-Outcome 충돌 검사."""
    print("=" * 80)
    print("Example 1: Detect conflicts for TLIF → Fusion Rate")
    print("=" * 80)
    print()

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # TLIF → Fusion Rate 충돌 검사
        conflict = await detector.detect_conflicts("TLIF", "Fusion Rate")

        if conflict:
            print(conflict.summary)
            print()
            print(f"📊 Statistics:")
            print(f"  Total papers: {conflict.total_papers}")
            print(f"  Conflict ratio: {conflict.conflict_ratio:.0%}")
            print(f"  Highest evidence: Level {conflict.get_highest_evidence_level()}")
            print()

            # 논문 상세 정보
            if conflict.papers_improved:
                print("✅ Papers reporting IMPROVEMENT:")
                for paper in conflict.papers_improved:
                    print(f"  - {paper.paper_id}: {paper.title[:50]}...")
                    print(f"    Evidence: Level {paper.evidence_level}, "
                          f"p={paper.p_value:.3f if paper.p_value else 'N/A'}")
                print()

            if conflict.papers_worsened:
                print("❌ Papers reporting WORSENING:")
                for paper in conflict.papers_worsened:
                    print(f"  - {paper.paper_id}: {paper.title[:50]}...")
                    print(f"    Evidence: Level {paper.evidence_level}, "
                          f"p={paper.p_value:.3f if paper.p_value else 'N/A'}")
                print()

        else:
            print("✓ No significant conflict detected for TLIF → Fusion Rate")
            print()


async def demo_all_conflicts():
    """예시 2: 모든 충돌 검색."""
    print("=" * 80)
    print("Example 2: Find all conflicts in the database")
    print("=" * 80)
    print()

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # 모든 충돌 검색
        all_conflicts = await detector.find_all_conflicts()

        print(f"Found {len(all_conflicts)} conflicts in total\n")

        if not all_conflicts:
            print("No conflicts detected in the database.")
            return

        # 심각도별 분류
        severity_counts = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.HIGH: 0,
            ConflictSeverity.MEDIUM: 0,
            ConflictSeverity.LOW: 0,
        }

        for conflict in all_conflicts:
            severity_counts[conflict.severity] += 1

        # 요약 통계
        print("📊 Conflicts by Severity:")
        print(f"  🔴 CRITICAL: {severity_counts[ConflictSeverity.CRITICAL]}")
        print(f"  🟠 HIGH:     {severity_counts[ConflictSeverity.HIGH]}")
        print(f"  🟡 MEDIUM:   {severity_counts[ConflictSeverity.MEDIUM]}")
        print(f"  🟢 LOW:      {severity_counts[ConflictSeverity.LOW]}")
        print()

        # 상위 5개 충돌 상세 정보
        print("Top 5 conflicts (by severity):\n")

        for i, conflict in enumerate(all_conflicts[:5], 1):
            severity_emoji = {
                ConflictSeverity.CRITICAL: "🔴",
                ConflictSeverity.HIGH: "🟠",
                ConflictSeverity.MEDIUM: "🟡",
                ConflictSeverity.LOW: "🟢",
            }[conflict.severity]

            print(f"{i}. {severity_emoji} {conflict.intervention} → {conflict.outcome}")
            print(f"   Severity: {conflict.severity.value.upper()} "
                  f"(confidence: {conflict.confidence:.0%})")
            print(f"   Papers: {len(conflict.papers_improved)} improved, "
                  f"{len(conflict.papers_worsened)} worsened, "
                  f"{len(conflict.papers_unchanged)} unchanged")
            print(f"   Conflict ratio: {conflict.conflict_ratio:.0%}")
            print()


async def demo_high_severity_conflicts():
    """예시 3: HIGH 이상 심각도 충돌만 검색."""
    print("=" * 80)
    print("Example 3: Find HIGH+ severity conflicts only")
    print("=" * 80)
    print()

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # HIGH 이상 충돌만 필터링
        high_conflicts = await detector.find_all_conflicts(
            min_severity=ConflictSeverity.HIGH
        )

        print(f"Found {len(high_conflicts)} high-severity conflicts\n")

        if not high_conflicts:
            print("No high-severity conflicts detected.")
            print("This is good news - all conflicts are LOW or MEDIUM severity.")
            return

        # 각 충돌 상세 분석
        for i, conflict in enumerate(high_conflicts, 1):
            print("-" * 80)
            print(f"Conflict #{i}")
            print("-" * 80)
            print()
            print(conflict.summary)
            print()

            # 추가 분석
            print(f"📈 Conflict Analysis:")
            print(f"  - Conflict ratio: {conflict.conflict_ratio:.0%}")
            print(f"  - Total papers: {conflict.total_papers}")
            print(f"  - Highest evidence: Level {conflict.get_highest_evidence_level()}")
            print()

            # 권장사항
            print("💡 Recommendations:")
            if conflict.severity == ConflictSeverity.CRITICAL:
                print("  1. Conduct systematic review to resolve discrepancy")
                print("  2. Consider patient subgroup analysis")
                print("  3. Examine study methodology differences")
            elif conflict.severity == ConflictSeverity.HIGH:
                print("  1. Review study populations and inclusion criteria")
                print("  2. Consider effect modifiers (age, severity, etc.)")
                print("  3. Wait for additional high-quality studies")
            print()


async def demo_conflict_report():
    """예시 4: 충돌 리포트 생성."""
    print("=" * 80)
    print("Example 4: Generate comprehensive conflict report")
    print("=" * 80)
    print()

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # 모든 충돌 검색
        all_conflicts = await detector.find_all_conflicts()

        if not all_conflicts:
            print("No conflicts to report.")
            return

        # 리포트 생성
        print("=" * 80)
        print("CONFLICT DETECTION REPORT")
        print("=" * 80)
        print()

        print(f"Total conflicts detected: {len(all_conflicts)}")
        print()

        # 심각도별 분류
        by_severity = {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": [],
        }

        for conflict in all_conflicts:
            by_severity[conflict.severity.value.upper()].append(conflict)

        # 각 심각도별 리포트
        for severity_name in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            conflicts = by_severity[severity_name]
            if not conflicts:
                continue

            print("-" * 80)
            print(f"{severity_name} SEVERITY CONFLICTS ({len(conflicts)})")
            print("-" * 80)
            print()

            for conflict in conflicts:
                print(f"• {conflict.intervention} → {conflict.outcome}")
                print(f"  Papers: {len(conflict.papers_improved)}↑ / "
                      f"{len(conflict.papers_worsened)}↓ / "
                      f"{len(conflict.papers_unchanged)}→")
                print(f"  Confidence: {conflict.confidence:.0%}, "
                      f"Ratio: {conflict.conflict_ratio:.0%}")
                print()

        print("=" * 80)
        print("END OF REPORT")
        print("=" * 80)


async def demo_specific_interventions():
    """예시 5: 특정 수술법의 모든 충돌 검색."""
    print("=" * 80)
    print("Example 5: Find all conflicts for a specific intervention (TLIF)")
    print("=" * 80)
    print()

    async with Neo4jClient() as client:
        detector = ConflictDetector(client)

        # 모든 충돌 검색
        all_conflicts = await detector.find_all_conflicts()

        # TLIF 관련 충돌 필터링
        tlif_conflicts = [c for c in all_conflicts if c.intervention == "TLIF"]

        print(f"Found {len(tlif_conflicts)} conflicts for TLIF\n")

        if not tlif_conflicts:
            print("No conflicts detected for TLIF.")
            return

        # Outcome별 분류
        print("TLIF conflicts by outcome:\n")

        for conflict in tlif_conflicts:
            severity_emoji = {
                ConflictSeverity.CRITICAL: "🔴",
                ConflictSeverity.HIGH: "🟠",
                ConflictSeverity.MEDIUM: "🟡",
                ConflictSeverity.LOW: "🟢",
            }[conflict.severity]

            print(f"{severity_emoji} {conflict.outcome}:")
            print(f"   Severity: {conflict.severity.value.upper()}")
            print(f"   Papers: {len(conflict.papers_improved)}↑ / "
                  f"{len(conflict.papers_worsened)}↓")
            print(f"   Highest evidence: Level {conflict.get_highest_evidence_level()}")
            print()


async def main():
    """메인 함수."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                    Conflict Detection Demo                                 ║")
    print("║                   Spine GraphRAG v3.0                                      ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print()

    try:
        # 예시 1: 특정 충돌 검사
        await demo_specific_conflict()
        input("Press Enter to continue to Example 2...")
        print("\n")

        # 예시 2: 모든 충돌 검색
        await demo_all_conflicts()
        input("Press Enter to continue to Example 3...")
        print("\n")

        # 예시 3: HIGH 이상 충돌
        await demo_high_severity_conflicts()
        input("Press Enter to continue to Example 4...")
        print("\n")

        # 예시 4: 충돌 리포트
        await demo_conflict_report()
        input("Press Enter to continue to Example 5...")
        print("\n")

        # 예시 5: 특정 수술법 충돌
        await demo_specific_interventions()

        print("\n")
        print("=" * 80)
        print("Demo completed!")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
