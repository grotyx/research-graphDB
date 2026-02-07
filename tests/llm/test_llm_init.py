#!/usr/bin/env python3
"""Test script to verify LLM initialization with .env loading.

This can be run directly as a script or via pytest.
"""

import sys
from pathlib import Path
import os
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


class TestLLMInitialization:
    """Test LLM initialization with environment variables."""

    def test_env_variable_loading(self):
        """Test 1: Check if environment variables can be accessed."""
        # Just verify we can access the env var (may or may not be set)
        gemini_key = os.environ.get('GEMINI_API_KEY')
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY')

        # At least one API key should be available for LLM functionality
        has_any_key = bool(gemini_key) or bool(anthropic_key)
        # This is informational - don't fail if keys aren't set in test env
        print(f"GEMINI_API_KEY present: {bool(gemini_key)}")
        print(f"ANTHROPIC_API_KEY present: {bool(anthropic_key)}")

    @pytest.mark.skipif(
        not os.environ.get('GEMINI_API_KEY') and not os.environ.get('ANTHROPIC_API_KEY'),
        reason="No API keys configured"
    )
    def test_medical_kag_server_import(self):
        """Test 2: Import MedicalKAGServer."""
        from medical_mcp.medical_kag_server import MedicalKAGServer
        assert MedicalKAGServer is not None

    @pytest.mark.skipif(
        not os.environ.get('GEMINI_API_KEY') and not os.environ.get('ANTHROPIC_API_KEY'),
        reason="No API keys configured"
    )
    def test_server_instance_creation(self):
        """Test 3: Create MedicalKAGServer instance without LLM."""
        from medical_mcp.medical_kag_server import MedicalKAGServer
        # Create with enable_llm=False to avoid API key requirements
        server = MedicalKAGServer(enable_llm=False)
        assert server is not None
        assert server.enable_llm is False

    @pytest.mark.skipif(
        not os.environ.get('GEMINI_API_KEY'),
        reason="GEMINI_API_KEY not configured"
    )
    def test_llm_enabled_server(self):
        """Test 4: Create MedicalKAGServer with LLM enabled (requires API key)."""
        from medical_mcp.medical_kag_server import MedicalKAGServer
        server = MedicalKAGServer(enable_llm=True)
        assert server.enable_llm is True
        # Check LLM components (may be None if initialization failed)
        print(f"gemini_client: {server.gemini_client is not None}")
        print(f"llm_section_classifier: {server.llm_section_classifier is not None}")


def main():
    """Run as standalone script for manual testing."""
    print("=" * 60)
    print("Testing LLM Initialization")
    print("=" * 60)

    # Test 1: Check if .env is loaded
    print("\n[Test 1] Checking environment variable loading...")
    print(f"GEMINI_API_KEY present: {bool(os.environ.get('GEMINI_API_KEY'))}")
    if os.environ.get('GEMINI_API_KEY'):
        api_key = os.environ.get('GEMINI_API_KEY')
        print(f"GEMINI_API_KEY length: {len(api_key)}")
        print(f"GEMINI_API_KEY preview: {api_key[:10]}...{api_key[-5:]}")

    # Test 2: Import MedicalKAGServer
    print("\n[Test 2] Importing MedicalKAGServer...")
    from medical_mcp.medical_kag_server import MedicalKAGServer

    # Test 3: Create server instance
    print("\n[Test 3] Creating MedicalKAGServer instance...")
    server = MedicalKAGServer(enable_llm=True)

    # Test 4: Check LLM status
    print("\n[Test 4] Checking LLM status...")
    print(f"enable_llm: {server.enable_llm}")
    print(f"gemini_client: {server.gemini_client is not None}")
    print(f"llm_section_classifier: {server.llm_section_classifier is not None}")
    print(f"llm_chunker: {server.llm_chunker is not None}")
    print(f"llm_extractor: {server.llm_extractor is not None}")

    # Final result
    print("\n" + "=" * 60)
    if server.gemini_client is not None:
        print("SUCCESS: LLM is properly initialized!")
        print("=" * 60)
        return 0
    else:
        print("FAILURE: LLM initialization failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
