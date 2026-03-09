"""Test script for UnifiedProcessorV7 integration.

Tests the v7.0 pipeline with sample text to verify module integration.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from builder.unified_processor_v7 import (
    UnifiedProcessorV7,
    create_processor_v7,
    DocumentType,
)


# Sample medical research paper abstract
SAMPLE_MEDICAL_TEXT = """
Title: Comparison of Unilateral Biportal Endoscopic Decompression versus Conventional Open Laminectomy for Lumbar Stenosis: A Randomized Controlled Trial

Abstract

Background: Lumbar spinal stenosis is a common degenerative condition causing neurogenic claudication. Unilateral biportal endoscopic (UBE) decompression has emerged as a minimally invasive alternative to conventional open laminectomy. However, high-quality comparative evidence remains limited.

Objective: To compare the clinical outcomes and complication rates between UBE decompression and open laminectomy in patients with symptomatic lumbar stenosis.

Methods: This prospective randomized controlled trial enrolled 120 patients with single-level lumbar stenosis between January 2021 and December 2022. Patients were randomly assigned to undergo either UBE decompression (n=60) or open laminectomy (n=60). Primary outcomes included Visual Analog Scale (VAS) for leg pain and Oswestry Disability Index (ODI) at 1-year follow-up. Secondary outcomes included operative time, blood loss, hospital stay, and complications.

Results: Both groups showed significant improvement in VAS and ODI scores postoperatively. At 1-year follow-up, the UBE group demonstrated superior outcomes compared to the open laminectomy group. Mean VAS scores decreased from 7.2±1.1 to 2.1±0.8 in the UBE group versus 7.4±1.2 to 3.5±1.2 in the open group (p=0.001). Mean ODI improved from 62.3±8.5 to 18.2±6.3 in the UBE group versus 61.8±9.1 to 26.4±8.7 in the open group (p=0.002).

The UBE group had significantly shorter operative time (78±15 min vs 105±22 min, p<0.001), less blood loss (45±18 mL vs 185±52 mL, p<0.001), and shorter hospital stay (2.3±0.8 days vs 4.5±1.2 days, p<0.001). Complication rates were comparable between groups (UBE: 3.3% vs Open: 5.0%, p=0.68), with dural tears being the most common complication in both groups.

Conclusions: UBE decompression for lumbar stenosis provides superior pain relief and functional improvement compared to conventional open laminectomy, with the advantages of reduced operative time, blood loss, and hospital stay. The technique maintains safety with comparable complication rates. UBE should be considered as a preferred minimally invasive option for appropriately selected patients with lumbar stenosis.

Keywords: Lumbar stenosis, Unilateral biportal endoscopic, UBE, Laminectomy, Minimally invasive spine surgery, Randomized controlled trial

DOI: 10.1016/j.spinee.2023.12345
PMID: 38123456
"""


# Sample non-medical text
SAMPLE_NEWS_TEXT = """
Title: Tech Giants Announce Major Investment in Renewable Energy

San Francisco, CA - In a groundbreaking announcement today, three of the world's largest technology companies revealed plans to invest over $10 billion in renewable energy infrastructure over the next five years.

The initiative, which brings together leading firms in cloud computing and artificial intelligence, aims to power their massive data centers entirely with clean energy by 2028. This ambitious goal represents a significant step forward in the tech industry's efforts to reduce its carbon footprint and combat climate change.

"This is not just about corporate responsibility," said the CEO of one participating company. "It's about building a sustainable future for the next generation while ensuring our operations can scale efficiently."

The investment will focus on solar and wind energy projects across multiple continents, with particular emphasis on regions where the companies operate major data centers. Industry experts estimate this could add up to 15 gigawatts of new renewable energy capacity to the global grid.

Environmental groups have welcomed the announcement, though some remain cautious about the timeline and specific implementation details. Climate activists are calling for even more aggressive action from the tech sector, noting that data centers currently account for approximately 1% of global electricity consumption.
"""


async def test_medical_document():
    """Test processing of medical research paper."""
    print("\n" + "="*80)
    print("TEST 1: Medical Research Paper (Journal Article)")
    print("="*80)

    processor = create_processor_v7()

    result = await processor.process(
        text=SAMPLE_MEDICAL_TEXT,
        filename="ube_vs_laminectomy_rct.pdf",
    )

    print(f"\n✓ Document Type: {result.document_type.value}")
    print(f"✓ Paper ID: {result.paper_id}")
    print(f"✓ Summary: {result.summary.word_count} words")
    print(f"✓ Chunks: {len(result.chunks)}")
    print(f"✓ Processing Time: {result.processing_time:.2f}s")

    if result.entities:
        print(f"\n✓ Medical Content Detected: Yes")
        print(f"  - Interventions: {len(result.entities.interventions)}")
        print(f"    {[e.name for e in result.entities.interventions[:5]]}")
        print(f"  - Pathologies: {len(result.entities.pathologies)}")
        print(f"    {[e.name for e in result.entities.pathologies[:5]]}")
        print(f"  - Outcomes: {len(result.entities.outcomes)}")
        print(f"    {[e.name for e in result.entities.outcomes[:5]]}")
    else:
        print(f"\n✗ Medical Content: No")

    # Show first few chunks
    print(f"\n✓ Sample Chunks:")
    for i, chunk in enumerate(result.chunks[:3]):
        print(f"  [{i}] Section: {chunk.section}, Words: {chunk.word_count}")
        print(f"      Preview: {chunk.text[:100]}...")

    if result.warnings:
        print(f"\n⚠ Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    return result


async def test_news_article():
    """Test processing of news article."""
    print("\n" + "="*80)
    print("TEST 2: News Article (Non-Medical)")
    print("="*80)

    processor = create_processor_v7()

    result = await processor.process(
        text=SAMPLE_NEWS_TEXT,
        url="https://example.com/tech-news/renewable-energy",
    )

    print(f"\n✓ Document Type: {result.document_type.value}")
    print(f"✓ Paper ID: {result.paper_id}")
    print(f"✓ Summary: {result.summary.word_count} words")
    print(f"✓ Chunks: {len(result.chunks)}")
    print(f"✓ Processing Time: {result.processing_time:.2f}s")

    if result.entities:
        print(f"\n✓ Medical Content: Yes (unexpected for news)")
    else:
        print(f"\n✓ Medical Content: No (expected for news)")

    print(f"\n✓ Sample Chunks:")
    for i, chunk in enumerate(result.chunks[:3]):
        print(f"  [{i}] Section: {chunk.section}, Words: {chunk.word_count}")

    if result.warnings:
        print(f"\n⚠ Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    return result


async def test_v6_compatibility(result):
    """Test v6.0 backward compatibility."""
    print("\n" + "="*80)
    print("TEST 3: V6.0 Backward Compatibility")
    print("="*80)

    processor = create_processor_v7()
    v6_data = processor.to_v6_format(result)

    print(f"\n✓ V6 Format Conversion:")
    print(f"  - Metadata: {list(v6_data['metadata'].keys())}")
    print(f"  - Spine Metadata: {list(v6_data['spine_metadata'].keys())}")
    print(f"  - Chunks: {len(v6_data['chunks'])}")

    if v6_data['chunks']:
        sample_chunk = v6_data['chunks'][0]
        print(f"\n✓ Sample V6 Chunk Structure:")
        print(f"  - content_type: {sample_chunk['content_type']}")
        print(f"  - section_type: {sample_chunk['section_type']}")
        print(f"  - tier: {sample_chunk['tier']}")
        print(f"  - is_key_finding: {sample_chunk['is_key_finding']}")

    return v6_data


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("UnifiedProcessorV7 Integration Test")
    print("="*80)

    try:
        # Test 1: Medical document
        medical_result = await test_medical_document()

        # Test 2: News article
        news_result = await test_news_article()

        # Test 3: V6 compatibility
        v6_data = await test_v6_compatibility(medical_result)

        print("\n" + "="*80)
        print("✓ ALL TESTS PASSED")
        print("="*80)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
