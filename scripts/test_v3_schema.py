#!/usr/bin/env python3
"""v3.0 Schema Test - PDF Extraction Schema Optimization.

Tests the new optimized schema:
- PICO at spine_metadata level (not chunk level)
- Simplified statistics (3 fields: p_value, is_significant, additional)
- Narrative table/figure content
- Removed unused fields

Usage:
    python scripts/test_v3_schema.py /path/to/paper.pdf
    python scripts/test_v3_schema.py  # Uses default test PDF
"""

import asyncio
import json
import sys
from pathlib import Path
from dataclasses import asdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


async def test_schema(pdf_path: Path):
    """Test the v3.0 schema extraction."""
    from builder.unified_pdf_processor import UnifiedPDFProcessor, VisionProcessorResult

    print(f"\n{'='*60}")
    print("v3.0 Schema Test - PDF Extraction")
    print(f"{'='*60}")
    print(f"PDF: {pdf_path.name}")

    # Initialize processor
    processor = UnifiedPDFProcessor()

    print("\n[1/4] Processing PDF with new v3.0 schema...")
    result = await processor.process_pdf_typed(str(pdf_path))

    if not result:
        print("Error: Processing failed")
        return False

    # Test 1: Verify spine_metadata has PICO
    print("\n[2/4] Checking PICO in spine_metadata...")
    spine = result.metadata.spine
    if not spine:
        print("  WARN - No spine metadata found")
        pico_check = {"population": False, "intervention": False, "comparison": False, "outcome": False}
    else:
        pico_check = {
            "population": bool(spine.pico.population if spine.pico else False),
            "intervention": bool(spine.pico.intervention if spine.pico else False),
            "comparison": bool(spine.pico.comparison if spine.pico else False),
            "outcome": bool(spine.pico.outcome if spine.pico else False),
        }

    print(f"  PICO Population: {'PASS' if pico_check['population'] else 'WARN - empty'}")
    print(f"  PICO Intervention: {'PASS' if pico_check['intervention'] else 'WARN - empty'}")
    print(f"  PICO Comparison: {'PASS' if pico_check['comparison'] else 'WARN - empty'}")
    print(f"  PICO Outcome: {'PASS' if pico_check['outcome'] else 'WARN - empty'}")

    if spine and spine.pico:
        print(f"\n  Content:")
        print(f"    Population: {spine.pico.population[:80]}..." if len(spine.pico.population) > 80 else f"    Population: {spine.pico.population}")
        print(f"    Intervention: {spine.pico.intervention[:80]}..." if len(spine.pico.intervention) > 80 else f"    Intervention: {spine.pico.intervention}")
        print(f"    Comparison: {spine.pico.comparison[:80]}..." if len(spine.pico.comparison) > 80 else f"    Comparison: {spine.pico.comparison}")
        print(f"    Outcome: {spine.pico.outcome[:80]}..." if len(spine.pico.outcome) > 80 else f"    Outcome: {spine.pico.outcome}")

    # Test 2: Verify chunks don't have PICO (v3.0 optimization)
    print("\n[3/4] Verifying chunk structure (no PICO)...")
    chunks = result.chunks
    print(f"  Total chunks: {len(chunks)}")

    chunks_with_pico = 0
    for chunk in chunks:
        # Check if chunk has pico attribute (it shouldn't in v3.0)
        if hasattr(chunk, 'pico') and chunk.pico:
            chunks_with_pico += 1

    print(f"  Chunks with PICO: {chunks_with_pico} (expected: 0)")
    if chunks_with_pico == 0:
        print("  PASS - No PICO in chunks")
    else:
        print("  WARN - Found PICO in chunks (should be at spine_metadata level)")

    # Test 3: Verify simplified statistics format
    print("\n[4/4] Checking statistics format...")
    stats_check = {"new_format": 0, "old_format": 0, "has_stats": 0}

    for chunk in chunks:
        if chunk.statistics:
            stats_check["has_stats"] += 1
            stats = chunk.statistics

            # Check for new format (p_value, is_significant, additional)
            if hasattr(stats, 'p_value') or (isinstance(stats, dict) and 'p_value' in stats):
                stats_check["new_format"] += 1
            # Check for old format (p_values list)
            elif hasattr(stats, 'p_values') or (isinstance(stats, dict) and 'p_values' in stats):
                stats_check["old_format"] += 1

    print(f"  Chunks with statistics: {stats_check['has_stats']}")
    print(f"  New format (p_value, is_significant, additional): {stats_check['new_format']}")
    print(f"  Old format (p_values list): {stats_check['old_format']}")

    if stats_check["old_format"] == 0 and stats_check["new_format"] > 0:
        print("  PASS - Using new simplified statistics format")
    elif stats_check["has_stats"] == 0:
        print("  WARN - No statistics found in chunks")
    else:
        print("  WARN - Mixed or old format detected")

    # Summary
    print(f"\n{'='*60}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Metadata:")
    print(f"  Title: {result.metadata.title[:60]}..." if len(result.metadata.title) > 60 else f"  Title: {result.metadata.title}")
    print(f"  Year: {result.metadata.year}")
    print(f"  Study Type: {result.metadata.study_type}")
    print(f"  Evidence Level: {result.metadata.evidence_level}")

    print(f"\nSpine Metadata:")
    if spine:
        print(f"  Sub-domain: {spine.sub_domain}")
        print(f"  Anatomy: {spine.anatomy_level} ({spine.anatomy_region})")
        print(f"  Pathology: {', '.join(spine.pathology) if spine.pathology else 'N/A'}")
        print(f"  Interventions: {', '.join(spine.interventions) if spine.interventions else 'N/A'}")
        print(f"  Outcomes count: {len(spine.outcomes) if spine.outcomes else 0}")
    else:
        print("  No spine metadata available")

    print(f"\nChunks:")
    print(f"  Total: {len(chunks)}")

    content_types = {}
    section_types = {}
    key_findings = 0

    for chunk in chunks:
        ct = chunk.content_type
        st = chunk.section_type
        content_types[ct] = content_types.get(ct, 0) + 1
        section_types[st] = section_types.get(st, 0) + 1
        if chunk.is_key_finding:
            key_findings += 1

    print(f"  Content types: {content_types}")
    print(f"  Section types: {section_types}")
    print(f"  Key findings: {key_findings}")

    # Token usage estimate (based on output size)
    output_json = json.dumps(asdict(result), default=str)
    estimated_tokens = len(output_json) // 4  # rough estimate
    print(f"\nOutput size: {len(output_json):,} chars (~{estimated_tokens:,} tokens)")

    print(f"\n{'='*60}")
    print("Test completed!")
    print(f"{'='*60}")

    return True


async def main():
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
    else:
        # Use default test PDF
        default_pdfs = list(Path("/Users/sangminpark/Desktop/rag_research/data/uploads").glob("*.pdf"))
        if default_pdfs:
            pdf_path = default_pdfs[0]
            print(f"Using default PDF: {pdf_path.name}")
        else:
            print("Error: No PDF file specified and no PDFs found in data/uploads/")
            print("Usage: python scripts/test_v3_schema.py /path/to/paper.pdf")
            sys.exit(1)

    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    success = await test_schema(pdf_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
