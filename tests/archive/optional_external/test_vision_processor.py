#!/usr/bin/env python3
"""Test script for Gemini PDF Processor.

Gemini 2.5 Flash + File API를 사용하여 PDF 직접 처리.
단일 API 호출로 KAG에 필요한 모든 정보 추출.

Usage:
    python test_vision_processor.py /path/to/paper.pdf
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


async def test_vision_processor(pdf_path: str):
    """Test the Gemini PDF processor with direct PDF upload."""
    from builder.gemini_vision_processor import GeminiPDFProcessor

    print(f"\n{'='*60}")
    print("Gemini 2.5 Flash PDF Processor Test")
    print(f"{'='*60}")
    print(f"PDF: {pdf_path}")

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\nError: GEMINI_API_KEY not set")
        return

    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")

    # Initialize processor
    try:
        processor = GeminiPDFProcessor(
            api_key=api_key,
            timeout=120.0,
            max_retries=2
        )
        print("Processor initialized successfully (Gemini 2.5 Flash)")
    except Exception as e:
        print(f"Error initializing processor: {e}")
        return

    # Process PDF
    print(f"\nProcessing PDF...")
    result = await processor.process_pdf(pdf_path)

    # Display results
    print(f"\n{'='*60}")
    print("Results")
    print(f"{'='*60}")

    if not result.success:
        print(f"Error: {result.error}")
        return

    print(f"\nSuccess: {result.success}")
    print(f"Input tokens: {result.input_tokens}")
    print(f"Output tokens: {result.output_tokens}")

    # Metadata
    print(f"\n--- Metadata ---")
    meta = result.metadata
    print(f"Title: {meta.title}")
    print(f"Authors: {', '.join(meta.authors[:3])}{'...' if len(meta.authors) > 3 else ''}")
    print(f"Year: {meta.year}")
    print(f"Journal: {meta.journal}")
    print(f"Study Type: {meta.study_type}")
    print(f"Evidence Level: {meta.evidence_level}")

    # Chunks
    print(f"\n--- Chunks ({len(result.chunks)} total) ---")
    tier1_count = sum(1 for c in result.chunks if c.tier == "tier1")
    tier2_count = sum(1 for c in result.chunks if c.tier == "tier2")
    print(f"Tier 1: {tier1_count} chunks")
    print(f"Tier 2: {tier2_count} chunks")

    # Sample chunks
    print(f"\n--- Sample Chunks ---")
    for i, chunk in enumerate(result.chunks[:3]):
        print(f"\n[{i+1}] {chunk.tier.upper()} - {chunk.section_type}")
        print(f"    Topic: {chunk.topic_summary[:80]}..." if chunk.topic_summary else "")
        print(f"    Key Finding: {chunk.is_key_finding}")
        print(f"    Content: {chunk.content[:150]}...")
        if chunk.pico and (chunk.pico.population or chunk.pico.intervention):
            print(f"    PICO: P={chunk.pico.population[:50] if chunk.pico.population else 'N/A'}")
        if chunk.statistics and chunk.statistics.p_values:
            print(f"    Stats: {chunk.statistics.p_values[:3]}")

    # Full text sample
    if result.full_text:
        print(f"\n--- Full Text ({len(result.full_text)} chars) ---")
        print(result.full_text[:500] + "...")

    print(f"\n{'='*60}")
    print("Test completed successfully!")
    print(f"{'='*60}")


async def test_medical_kag_server(pdf_path: str):
    """Test the full MCP server with Vision processor."""
    from medical_mcp.medical_kag_server import MedicalKAGServer

    print(f"\n{'='*60}")
    print("Medical KAG Server Test (with Vision)")
    print(f"{'='*60}")
    print(f"PDF: {pdf_path}")

    # Initialize server
    server = MedicalKAGServer()
    print(f"Server initialized")
    print(f"Vision processor available: {server.vision_processor is not None}")

    # Process PDF with Vision
    print(f"\nProcessing PDF with Vision...")
    result = await server.add_pdf(pdf_path, use_vision=True)

    # Display results
    print(f"\n--- Results ---")
    print(f"Success: {result.get('success')}")
    print(f"Processing method: {result.get('processing_method', 'unknown')}")
    print(f"Document ID: {result.get('document_id')}")

    if result.get('success'):
        meta = result.get('extracted_metadata', {})
        print(f"\nMetadata:")
        print(f"  Title: {meta.get('title', 'N/A')}")
        print(f"  Authors: {meta.get('authors', [])}")
        print(f"  Year: {meta.get('year', 'N/A')}")
        print(f"  Study Type: {meta.get('study_type', 'N/A')}")
        print(f"  Evidence Level: {meta.get('evidence_level', 'N/A')}")

        stats = result.get('stats', {})
        print(f"\nStats:")
        print(f"  Tier 1 chunks: {stats.get('tier1_chunks', 0)}")
        print(f"  Tier 2 chunks: {stats.get('tier2_chunks', 0)}")
        print(f"  Total chunks: {stats.get('total_chunks', 0)}")

        if 'api_usage' in result:
            usage = result['api_usage']
            print(f"\nAPI Usage:")
            print(f"  Input tokens: {usage.get('input_tokens', 0)}")
            print(f"  Output tokens: {usage.get('output_tokens', 0)}")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_vision_processor.py <pdf_path> [--server]")
        print("\nOptions:")
        print("  --server  Test the full MCP server instead of just the processor")
        sys.exit(1)

    pdf_path = sys.argv[1]
    use_server = "--server" in sys.argv

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    if use_server:
        asyncio.run(test_medical_kag_server(pdf_path))
    else:
        asyncio.run(test_vision_processor(pdf_path))
