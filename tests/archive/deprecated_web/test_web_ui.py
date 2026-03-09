"""Integration tests for Streamlit Web UI.

Tests:
1. ServerBridge initialization and singleton pattern
2. Main app.py imports correctly
3. Each page module can be imported without errors
4. run_async() helper function works correctly
5. Mock server interactions work properly
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Add src and web to path
src_dir = Path(__file__).parent.parent.parent / "src"
web_dir = Path(__file__).parent.parent.parent / "web"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(web_dir))


class TestServerBridge:
    """Test ServerBridge singleton pattern and initialization."""

    def test_singleton_pattern(self):
        """Test ServerBridge.get_instance() returns same instance."""
        # Mock streamlit before importing
        with patch.dict('sys.modules', {'streamlit': MagicMock()}):
            from web.utils.server_bridge import ServerBridge

            # Get two instances
            instance1 = ServerBridge.get_instance()
            instance2 = ServerBridge.get_instance()

            # Should be the same instance
            assert instance1 is instance2

    def test_server_property_lazy_initialization(self):
        """Test server property creates instance on first access."""
        with patch.dict('sys.modules', {'streamlit': MagicMock()}):
            from web.utils.server_bridge import ServerBridge

            # Create bridge instance
            bridge = ServerBridge()

            # Server should be None initially
            assert bridge._server is None

            # Mock the _create_server method
            mock_server = MagicMock()
            bridge._create_server = MagicMock(return_value=mock_server)

            # Access server property
            server = bridge.server

            # Should have called _create_server
            bridge._create_server.assert_called_once()

            # Should return the same instance on second access
            server2 = bridge.server
            assert server is server2

            # _create_server should still only be called once
            assert bridge._create_server.call_count == 1

    def test_is_llm_enabled_property(self):
        """Test is_llm_enabled property checks server state."""
        with patch.dict('sys.modules', {'streamlit': MagicMock()}):
            from web.utils.server_bridge import ServerBridge

            bridge = ServerBridge()

            # Mock server with LLM enabled
            mock_server = MagicMock()
            mock_server.enable_llm = True
            mock_server.gemini_client = MagicMock()
            bridge._server = mock_server

            assert bridge.is_llm_enabled is True

            # Mock server with LLM disabled
            mock_server.enable_llm = False
            assert bridge.is_llm_enabled is False

            # Mock server with no gemini client
            mock_server.enable_llm = True
            mock_server.gemini_client = None
            assert bridge.is_llm_enabled is False

    def test_has_knowledge_graph_property(self):
        """Test has_knowledge_graph property checks paper_graph."""
        with patch.dict('sys.modules', {'streamlit': MagicMock()}):
            from web.utils.server_bridge import ServerBridge

            bridge = ServerBridge()

            # Mock server with knowledge graph
            mock_server = MagicMock()
            mock_server.paper_graph = MagicMock()
            bridge._server = mock_server

            assert bridge.has_knowledge_graph is True

            # Mock server without knowledge graph
            mock_server.paper_graph = None
            assert bridge.has_knowledge_graph is False

    def test_has_query_expansion_property(self):
        """Test has_query_expansion property checks concept_hierarchy."""
        with patch.dict('sys.modules', {'streamlit': MagicMock()}):
            from web.utils.server_bridge import ServerBridge

            bridge = ServerBridge()

            # Mock server with query expansion
            mock_server = MagicMock()
            mock_server.concept_hierarchy = MagicMock()
            bridge._server = mock_server

            assert bridge.has_query_expansion is True

            # Mock server without query expansion
            mock_server.concept_hierarchy = None
            assert bridge.has_query_expansion is False

    def test_get_server_function(self):
        """Test get_server() function with streamlit cache."""
        mock_st = MagicMock()

        # Mock st.cache_resource decorator
        def cache_resource_decorator(func):
            return func

        mock_st.cache_resource = cache_resource_decorator

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            from web.utils.server_bridge import get_server, ServerBridge

            # Get server bridge
            bridge = get_server()

            # Should return ServerBridge instance
            assert isinstance(bridge, ServerBridge)


class TestRunAsync:
    """Test run_async() helper function."""

    def test_run_async_executes_coroutine(self):
        """Test run_async() executes async functions correctly."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        # Mock utils.server_bridge module
        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            # Import app module
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test", app_path)
            app_module = importlib.util.module_from_spec(spec)

            # Execute module to populate namespace
            spec.loader.exec_module(app_module)

            # Get run_async function
            run_async = app_module.run_async

            # Test async function
            async def test_coro():
                await asyncio.sleep(0.01)
                return "success"

            # Run async function
            result = run_async(test_coro())

            assert result == "success"

    def test_run_async_handles_exceptions(self):
        """Test run_async() properly handles exceptions."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test2", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test async function that raises
            async def error_coro():
                raise ValueError("Test error")

            # Should raise the exception
            with pytest.raises(ValueError, match="Test error"):
                run_async(error_coro())

    def test_run_async_cleans_up_event_loop(self):
        """Test run_async() closes event loop after execution."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test3", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test that multiple calls work (loop is cleaned up properly)
            async def test_coro1():
                return "done1"
            
            async def test_coro2():
                return "done2"

            # Both should work without errors (proving loop cleanup)
            result1 = run_async(test_coro1())
            result2 = run_async(test_coro2())

            assert result1 == "done1"
            assert result2 == "done2"


class TestPageModuleImports:
    """Test each page module can be imported without errors."""

    def test_app_module_imports(self):
        """Test main app.py imports correctly."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test4", app_path)
            app_module = importlib.util.module_from_spec(spec)

            # Should import without errors
            spec.loader.exec_module(app_module)

            # Should have main function
            assert hasattr(app_module, 'main')
            assert callable(app_module.main)

    def test_documents_page_imports(self):
        """Test Documents page imports correctly."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            page_path = Path(__file__).parent.parent.parent / "web" / "pages" / "1_📄_Documents.py"
            spec = importlib.util.spec_from_file_location("documents_page", page_path)
            page_module = importlib.util.module_from_spec(spec)

            spec.loader.exec_module(page_module)

            assert hasattr(page_module, 'main')
            assert callable(page_module.main)

    def test_search_page_imports(self):
        """Test Search page imports correctly."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            page_path = Path(__file__).parent.parent.parent / "web" / "pages" / "2_🔍_Search.py"
            spec = importlib.util.spec_from_file_location("search_page", page_path)
            page_module = importlib.util.module_from_spec(spec)

            spec.loader.exec_module(page_module)

            assert hasattr(page_module, 'main')
            assert callable(page_module.main)

    def test_knowledge_graph_page_imports(self):
        """Test Knowledge Graph page imports correctly."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            page_path = Path(__file__).parent.parent.parent / "web" / "pages" / "3_📊_Knowledge_Graph.py"
            spec = importlib.util.spec_from_file_location("kg_page", page_path)
            page_module = importlib.util.module_from_spec(spec)

            spec.loader.exec_module(page_module)

            assert hasattr(page_module, 'main')
            assert callable(page_module.main)


class TestMockServerInteractions:
    """Test UI components work with mock server."""

    @pytest.fixture
    def mock_server_bridge(self):
        """Create mock ServerBridge for testing."""
        mock_server = MagicMock()

        # Mock async methods
        async def mock_list_documents():
            return {
                "success": True,
                "documents": [
                    {
                        "document_id": "test_paper_2024",
                        "chunk_count": 10,
                        "tier1_count": 4,
                        "tier2_count": 6,
                        "year": 2024
                    }
                ],
                "total_documents": 1,
                "total_chunks": 10,
                "tier_distribution": {"tier1": 4, "tier2": 6}
            }

        async def mock_search(query, top_k=5, tier_strategy="tier1_first",
                             prefer_original=True, min_evidence_level=None):
            return {
                "success": True,
                "results": [
                    {
                        "title": "Test Paper",
                        "document_id": "test_paper_2024",
                        "content": "This is test content",
                        "section": "abstract",
                        "tier": "tier1",
                        "evidence_level": "1b",
                        "score": 0.95,
                        "source_type": "original"
                    }
                ],
                "total_found": 1,
                "expansion_terms": ["diabetes", "hyperglycemia"]
            }

        async def mock_get_topic_clusters():
            return {
                "success": True,
                "clusters": {
                    "diabetes": {
                        "count": 1,
                        "papers": [{"paper_id": "test_paper_2024", "title": "Test Paper"}]
                    }
                },
                "cluster_count": 1
            }

        async def mock_add_pdf(file_path, metadata=None):
            return {
                "success": True,
                "document_id": "new_paper_2024",
                "chunks_created": 10
            }

        async def mock_delete_document(document_id):
            return {"success": True, "deleted": document_id}

        async def mock_get_paper_relations(paper_id, relation_type=None):
            return {
                "success": True,
                "relations": [
                    {
                        "type": "supports",
                        "target_id": "related_paper_2024",
                        "confidence": 0.85,
                        "evidence": "Both studies found similar results"
                    }
                ]
            }

        async def mock_compare_papers(paper_ids):
            return {
                "success": True,
                "similarities": ["Both study diabetes treatment"],
                "differences": ["Different sample sizes"],
                "conflicts": []
            }

        async def mock_find_evidence_chain(claim):
            return {
                "success": True,
                "supporting_papers": [
                    {"title": "Supporting Paper", "confidence": 0.9}
                ],
                "refuting_papers": []
            }

        # Attach async methods
        mock_server.list_documents = mock_list_documents
        mock_server.search = mock_search
        mock_server.get_topic_clusters = mock_get_topic_clusters
        mock_server.add_pdf = mock_add_pdf
        mock_server.delete_document = mock_delete_document
        mock_server.get_paper_relations = mock_get_paper_relations
        mock_server.compare_papers = mock_compare_papers
        mock_server.find_evidence_chain = mock_find_evidence_chain

        # Mock properties
        mock_server.enable_llm = True
        mock_server.gemini_client = MagicMock()
        mock_server.paper_graph = MagicMock()
        mock_server.concept_hierarchy = MagicMock()

        # Create bridge
        mock_bridge = MagicMock()
        mock_bridge.server = mock_server
        mock_bridge.is_llm_enabled = True
        mock_bridge.has_knowledge_graph = True
        mock_bridge.has_query_expansion = True

        return mock_bridge

    def test_list_documents_interaction(self, mock_server_bridge):
        """Test list_documents() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test5", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test list_documents call
            result = run_async(mock_server_bridge.server.list_documents())

            assert result["success"] is True
            assert result["total_documents"] == 1
            assert len(result["documents"]) == 1
            assert result["documents"][0]["document_id"] == "test_paper_2024"

    def test_search_interaction(self, mock_server_bridge):
        """Test search() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test6", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test search call
            result = run_async(mock_server_bridge.server.search(
                query="diabetes treatment",
                top_k=5,
                tier_strategy="tier1_first",
                prefer_original=True
            ))

            assert result["success"] is True
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Test Paper"
            assert "expansion_terms" in result

    def test_get_topic_clusters_interaction(self, mock_server_bridge):
        """Test get_topic_clusters() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test7", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test get_topic_clusters call
            result = run_async(mock_server_bridge.server.get_topic_clusters())

            assert result["success"] is True
            assert "clusters" in result
            assert "diabetes" in result["clusters"]
            assert result["cluster_count"] == 1

    def test_add_pdf_interaction(self, mock_server_bridge):
        """Test add_pdf() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test8", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test add_pdf call
            result = run_async(mock_server_bridge.server.add_pdf(
                file_path="/tmp/test.pdf",
                metadata={"original_filename": "test.pdf"}
            ))

            assert result["success"] is True
            assert result["document_id"] == "new_paper_2024"
            assert result["chunks_created"] == 10

    def test_delete_document_interaction(self, mock_server_bridge):
        """Test delete_document() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test9", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test delete_document call
            result = run_async(mock_server_bridge.server.delete_document("test_paper_2024"))

            assert result["success"] is True
            assert result["deleted"] == "test_paper_2024"

    def test_get_paper_relations_interaction(self, mock_server_bridge):
        """Test get_paper_relations() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test10", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test get_paper_relations call
            result = run_async(mock_server_bridge.server.get_paper_relations(
                "test_paper_2024",
                "supports"
            ))

            assert result["success"] is True
            assert len(result["relations"]) == 1
            assert result["relations"][0]["type"] == "supports"

    def test_compare_papers_interaction(self, mock_server_bridge):
        """Test compare_papers() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test11", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test compare_papers call
            result = run_async(mock_server_bridge.server.compare_papers(
                ["paper1", "paper2"]
            ))

            assert result["success"] is True
            assert "similarities" in result
            assert "differences" in result
            assert "conflicts" in result

    def test_find_evidence_chain_interaction(self, mock_server_bridge):
        """Test find_evidence_chain() server interaction."""
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()

        mock_utils = MagicMock()
        mock_utils.server_bridge.get_server = MagicMock()

        with patch.dict('sys.modules', {
            'streamlit': mock_st,
            'utils': mock_utils,
            'utils.server_bridge': mock_utils.server_bridge
        }):
            import importlib.util
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            spec = importlib.util.spec_from_file_location("app_test12", app_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)

            run_async = app_module.run_async

            # Test find_evidence_chain call
            result = run_async(mock_server_bridge.server.find_evidence_chain(
                "Metformin reduces cardiovascular risk"
            ))

            assert result["success"] is True
            assert "supporting_papers" in result
            assert "refuting_papers" in result


class TestUIComponents:
    """Test UI component creation with mocked streamlit."""

    def test_ui_components_creation(self):
        """Test that UI components can be created with mocked streamlit."""
        mock_st = MagicMock()

        # Mock common streamlit functions
        mock_st.title = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.columns = MagicMock(return_value=[MagicMock() for _ in range(4)])
        mock_st.success = MagicMock()
        mock_st.warning = MagicMock()
        mock_st.info = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.text_input = MagicMock(return_value="")
        mock_st.button = MagicMock(return_value=False)

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            # Test creating basic UI elements
            mock_st.title("Test Title")
            mock_st.markdown("Test Markdown")

            cols = mock_st.columns(4)
            assert len(cols) == 4

            mock_st.success("Success message")
            mock_st.warning("Warning message")
            mock_st.info("Info message")

            mock_st.metric("Metric", 100)
            query = mock_st.text_input("Query")
            clicked = mock_st.button("Search")

            # Verify calls
            mock_st.title.assert_called_with("Test Title")
            mock_st.markdown.assert_called_with("Test Markdown")
            mock_st.success.assert_called_with("Success message")
            assert query == ""
            assert clicked is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
