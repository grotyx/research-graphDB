"""PubMed Import Page - Bulk Paper Import System.

PubMed에서 논문을 대량으로 검색하고 Neo4j에 임포트하는 UI (v5.3).
- Search Tab: PubMed 검색 및 선택적 임포트
- Citation Import Tab: 기존 논문의 중요 인용 임포트
- Upgrade Tab: Abstract-only 논문을 PDF로 업그레이드
- Statistics Tab: 임포트 통계 및 이력
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

st.set_page_config(page_title="PubMed Import - Spine GraphRAG", page_icon="📚", layout="wide")

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

from utils.server_bridge import get_server
from utils.async_helpers import run_async
from utils.graph_utils import get_neo4j_client


# =============================================================================
# Session State Initialization
# =============================================================================

def init_session_state():
    """Initialize session state for PubMed import."""
    if "pubmed_search_results" not in st.session_state:
        st.session_state.pubmed_search_results = []
    if "selected_papers" not in st.session_state:
        st.session_state.selected_papers = set()
    if "import_in_progress" not in st.session_state:
        st.session_state.import_in_progress = False
    if "citation_import_results" not in st.session_state:
        st.session_state.citation_import_results = None
    if "last_search_query" not in st.session_state:
        st.session_state.last_search_query = ""
    if "last_import_result" not in st.session_state:
        st.session_state.last_import_result = None


def _get_checkbox_key(pmid: str, prefix: str = "search") -> str:
    """Generate consistent checkbox key for a paper."""
    return f"cb_{prefix}_{pmid}"


def select_all_papers():
    """Select all papers and update all checkbox widget states."""
    for paper in st.session_state.pubmed_search_results:
        pmid = paper.get("pmid")
        if pmid:
            st.session_state.selected_papers.add(pmid)
            # Update checkbox widget state directly
            key = _get_checkbox_key(pmid)
            st.session_state[key] = True


def deselect_all_papers():
    """Deselect all papers and update all checkbox widget states."""
    st.session_state.selected_papers = set()
    for paper in st.session_state.pubmed_search_results:
        pmid = paper.get("pmid")
        if pmid:
            key = _get_checkbox_key(pmid)
            if key in st.session_state:
                st.session_state[key] = False


def sync_selected_from_checkboxes():
    """Sync selected_papers set from all checkbox states."""
    st.session_state.selected_papers = set()
    for paper in st.session_state.pubmed_search_results:
        pmid = paper.get("pmid")
        if pmid:
            key = _get_checkbox_key(pmid)
            if st.session_state.get(key, False):
                st.session_state.selected_papers.add(pmid)


# =============================================================================
# Helper Functions
# =============================================================================

def get_existing_papers():
    """Get list of existing papers in Neo4j that have important_citations."""
    try:
        client = get_neo4j_client()
        if not client:
            return []

        # Use keys() to avoid Neo4j warning about non-existent property
        query = """
        MATCH (p:Paper)
        WHERE 'important_citations' IN keys(p) AND size(p.important_citations) > 0
        RETURN p.paper_id as paper_id, p.title as title,
               size(p.important_citations) as citation_count
        ORDER BY citation_count DESC
        LIMIT 50
        """
        results = client.run_query(query)
        return results
    except Exception as e:
        st.error(f"Failed to fetch papers: {e}")
        return []


def get_abstract_only_papers():
    """Get papers that only have abstract (can be upgraded with PDF)."""
    try:
        client = get_neo4j_client()
        if not client:
            return []

        query = """
        MATCH (p:Paper)
        WHERE p.is_abstract_only = true OR p.source = 'pubmed'
        RETURN p.paper_id as paper_id, p.title as title,
               p.pmid as pmid, p.source as source,
               p.created_at as created_at
        ORDER BY p.created_at DESC
        LIMIT 100
        """
        results = client.run_query(query)
        return results
    except Exception as e:
        st.error(f"Failed to fetch abstract-only papers: {e}")
        return []


def format_paper_card(paper: dict, show_checkbox: bool = True, key_prefix: str = "paper"):
    """Render a paper card with metadata."""
    title = paper.get("title", "Unknown Title")
    authors = paper.get("authors", [])
    if isinstance(authors, list):
        authors_str = ", ".join(authors[:3])
        if len(authors) > 3:
            authors_str += f" et al. ({len(authors)} authors)"
    else:
        authors_str = str(authors) if authors else "Unknown Authors"

    year = paper.get("year") or paper.get("publication_year", "N/A")
    journal = paper.get("journal") or paper.get("journal_name", "N/A")
    pmid = paper.get("pmid", "")
    doi = paper.get("doi", "")

    # Abstract preview (shorter for compact view)
    abstract = paper.get("abstract", "")
    abstract_preview = abstract[:200] + "..." if len(abstract) > 200 else abstract

    col1, col2 = st.columns([0.05, 0.95]) if show_checkbox and pmid else [None, st]

    if show_checkbox and pmid:
        with col1:
            # Use consistent key generation
            key = _get_checkbox_key(pmid, key_prefix)

            # DON'T use value parameter - let Streamlit manage state via key
            # Initialize checkbox state if not exists
            if key not in st.session_state:
                st.session_state[key] = pmid in st.session_state.selected_papers

            # Render checkbox - Streamlit manages state via key
            st.checkbox(
                "Select",
                key=key,
                label_visibility="collapsed"
            )

    container = col2 if show_checkbox and pmid else st

    # v7.15: XSS 방지 — 외부 PubMed 데이터 HTML escape
    import html as html_mod
    safe_title = html_mod.escape(str(title))
    safe_authors = html_mod.escape(str(authors_str))
    safe_journal = html_mod.escape(str(journal))
    safe_abstract = html_mod.escape(str(abstract_preview))
    safe_pmid = html_mod.escape(str(pmid))
    safe_doi = html_mod.escape(str(doi))

    with container:
        st.markdown(f"""
        <div style="
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 10px 12px;
            margin-bottom: 6px;
            background: white;
        ">
            <div style="margin: 0 0 4px 0; font-weight: 600; color: #1e293b; font-size: 0.95rem; line-height: 1.3;">{safe_title}</div>
            <div style="margin: 0 0 2px 0; color: #64748b; font-size: 0.8rem;">{safe_authors}</div>
            <div style="margin: 0 0 4px 0; color: #94a3b8; font-size: 0.75rem;">
                <strong>{safe_journal}</strong> ({year}){f' | PMID: {safe_pmid}' if pmid else ''}{f' | DOI: {safe_doi}' if doi else ''}
            </div>
            <div style="margin: 0; color: #475569; font-size: 0.8rem; line-height: 1.4;">{safe_abstract}</div>
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# Search Tab
# =============================================================================

def render_search_tab():
    """Render PubMed search interface."""
    st.subheader("🔍 PubMed Search")
    st.markdown("PubMed에서 논문을 검색하고 시스템에 임포트합니다.")

    # Search form
    with st.form("pubmed_search_form"):
        col1, col2 = st.columns([3, 1])

        with col1:
            query = st.text_input(
                "Search Query",
                placeholder="e.g., lumbar fusion outcomes, spine deformity surgery",
                help="PubMed 검색 쿼리 입력 (영어 권장)"
            )

        with col2:
            max_results = st.number_input(
                "Max Results",
                min_value=10,
                max_value=200,
                value=50,
                step=10
            )

        # Filters
        st.markdown("**Filters (Optional)**")
        col1, col2, col3 = st.columns(3)

        with col1:
            year_from = st.number_input(
                "Year From",
                min_value=1950,
                max_value=datetime.now().year,
                value=2015
            )

        with col2:
            year_to = st.number_input(
                "Year To",
                min_value=1950,
                max_value=datetime.now().year,
                value=datetime.now().year
            )

        with col3:
            pub_types = st.multiselect(
                "Publication Types",
                options=[
                    "Clinical Trial",
                    "Randomized Controlled Trial",
                    "Meta-Analysis",
                    "Systematic Review",
                    "Review",
                    "Comparative Study"
                ],
                default=[]
            )

        col1, col2 = st.columns(2)
        with col1:
            search_btn = st.form_submit_button("🔍 Search", use_container_width=True)
        with col2:
            search_and_import_btn = st.form_submit_button(
                "🔍 Search & Import All",
                use_container_width=True,
                type="secondary"
            )

    # Handle search
    if search_btn or search_and_import_btn:
        if not query:
            st.warning("Please enter a search query.")
            return

        import_results = search_and_import_btn

        with st.spinner(f"{'Searching and importing' if import_results else 'Searching'} PubMed..."):
            try:
                server = get_server()
                result = run_async(server.pubmed_bulk_search(
                    query=query,
                    max_results=max_results,
                    import_results=import_results,
                    year_from=year_from,
                    year_to=year_to,
                    publication_types=pub_types if pub_types else None
                ))

                if result.get("success"):
                    # Clear old checkbox states before setting new results
                    for old_paper in st.session_state.pubmed_search_results:
                        old_pmid = old_paper.get("pmid")
                        if old_pmid:
                            old_key = _get_checkbox_key(old_pmid, "search")
                            if old_key in st.session_state:
                                del st.session_state[old_key]

                    st.session_state.pubmed_search_results = result.get("papers", [])
                    st.session_state.last_search_query = query
                    st.session_state.selected_papers = set()

                    if import_results:
                        import_summary = result.get("import_summary", {})
                        st.success(
                            f"✅ Search completed! Found {result.get('total_found', 0)} papers. "
                            f"Imported: {import_summary.get('imported', 0)}, "
                            f"Skipped: {import_summary.get('skipped', 0)}, "
                            f"Failed: {import_summary.get('failed', 0)}"
                        )
                    else:
                        st.success(f"✅ Found {len(st.session_state.pubmed_search_results)} papers")
                else:
                    st.error(f"Search failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"Error during search: {e}")

    # Display search results
    if st.session_state.pubmed_search_results:
        st.markdown("---")

        # Show last import result if exists
        if st.session_state.last_import_result:
            result = st.session_state.last_import_result
            if result.get("success"):
                imported = result.get("imported", 0)
                skipped = result.get("skipped", 0)
                failed = result.get("failed", 0)
                chunks = result.get("chunks", 0)

                if imported > 0:
                    st.success(
                        f"✅ **Import completed**: {imported} imported, "
                        f"{skipped} skipped, {failed} failed | {chunks} chunks created"
                    )
                elif skipped > 0:
                    st.info(f"ℹ️ All {skipped} papers already exist in the database.")
                else:
                    st.warning("No papers were imported.")
            else:
                st.error(f"❌ Import failed: {result.get('error', 'Unknown error')}")

            # Clear the result after displaying
            st.session_state.last_import_result = None

        # Sync selected_papers from checkbox states before displaying count
        sync_selected_from_checkboxes()
        selected_count = len(st.session_state.selected_papers)

        # Header with count
        st.markdown(f"### Search Results ({len(st.session_state.pubmed_search_results)} papers)")

        # Action bar - cleaner layout
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("☑️ Select All", use_container_width=True):
                select_all_papers()
                st.rerun()
        with col2:
            if st.button("⬜ Deselect All", use_container_width=True):
                deselect_all_papers()
                st.rerun()
        with col3:
            # Show selected count as styled text
            if selected_count > 0:
                st.markdown(
                    f'<div style="padding: 8px 16px; background: #dbeafe; border-radius: 6px; '
                    f'text-align: center; color: #1e40af; font-weight: 500;">'
                    f'✓ {selected_count} papers selected</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    '<div style="padding: 8px 16px; background: #f1f5f9; border-radius: 6px; '
                    'text-align: center; color: #64748b;">No papers selected</div>',
                    unsafe_allow_html=True
                )

        # Import button - separate row, full width when papers selected
        if selected_count > 0:
            st.markdown("")  # Spacer
            if st.button(f"📥 Import {selected_count} Selected Papers", type="primary", use_container_width=True):
                # Sync one more time before import to get latest state
                sync_selected_from_checkboxes()
                import_selected_papers()

        st.markdown("---")

        # Paper cards
        for paper in st.session_state.pubmed_search_results:
            format_paper_card(paper, show_checkbox=True, key_prefix="search")


def import_selected_papers():
    """Import selected papers from search results."""
    # Get the current selection from checkbox states
    sync_selected_from_checkboxes()

    if not st.session_state.selected_papers:
        st.warning("No papers selected. Please check at least one paper.")
        return

    selected_pmids = list(st.session_state.selected_papers)

    with st.spinner(f"Importing {len(selected_pmids)} papers from PubMed..."):
        try:
            server = get_server()
            result = run_async(server.import_papers_by_pmids(pmids=selected_pmids))

            if result.get("success"):
                import_summary = result.get("import_summary", {})
                imported = import_summary.get('imported', 0)
                skipped = import_summary.get('skipped', 0)
                failed = import_summary.get('failed', 0)
                chunks = import_summary.get('total_chunks', 0)

                # Store result in session state for display after rerun
                st.session_state.last_import_result = {
                    "success": True,
                    "imported": imported,
                    "skipped": skipped,
                    "failed": failed,
                    "chunks": chunks,
                }

                # Clear selected papers and checkbox states after successful import
                deselect_all_papers()
                st.rerun()
            else:
                st.session_state.last_import_result = {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                }
                st.rerun()
        except Exception as e:
            st.session_state.last_import_result = {
                "success": False,
                "error": str(e),
            }
            st.rerun()


# =============================================================================
# Citation Import Tab
# =============================================================================

def render_citation_tab():
    """Render citation import interface."""
    st.subheader("📎 Citation Import")
    st.markdown(
        "기존에 처리된 논문의 중요 인용(Important Citations)을 "
        "PubMed에서 검색하여 자동으로 임포트합니다."
    )

    # Get papers with citations
    papers = get_existing_papers()

    if not papers:
        st.info("📭 No papers with important citations found. Upload and process PDFs first.")
        return

    # Paper selector
    paper_options = {
        f"{p['title'][:60]}... ({p['citation_count']} citations)": p['paper_id']
        for p in papers
    }

    selected_paper_label = st.selectbox(
        "Select Paper",
        options=list(paper_options.keys()),
        help="인용을 임포트할 논문 선택"
    )

    if selected_paper_label:
        selected_paper_id = paper_options[selected_paper_label]

        col1, col2 = st.columns([3, 1])
        with col1:
            min_confidence = st.slider(
                "Minimum Confidence",
                min_value=0.5,
                max_value=1.0,
                value=0.7,
                step=0.05,
                help="PubMed 매칭 신뢰도 임계값 (높을수록 정확한 매칭만 임포트)"
            )

        with col2:
            st.write("")  # Spacer
            st.write("")
            import_btn = st.button("📥 Import Citations", type="primary", use_container_width=True)

        if import_btn:
            with st.spinner("Searching and importing citations from PubMed..."):
                try:
                    server = get_server()
                    result = run_async(server.pubmed_import_citations(
                        paper_id=selected_paper_id,
                        min_confidence=min_confidence
                    ))

                    if result.get("success"):
                        summary = result.get("summary", {})
                        st.success(
                            f"✅ Citation import completed!\n\n"
                            f"- **Total Citations**: {summary.get('total_papers', 0)}\n"
                            f"- **Imported**: {summary.get('imported', 0)}\n"
                            f"- **Skipped (existing)**: {summary.get('skipped', 0)}\n"
                            f"- **Failed**: {summary.get('failed', 0)}\n"
                            f"- **Chunks Created**: {summary.get('total_chunks', 0)}"
                        )

                        # Show detailed results
                        results = result.get("results", [])
                        if results:
                            with st.expander("📋 Detailed Results", expanded=False):
                                for r in results:
                                    status = "✅" if r.get("neo4j_created") else ("⏭️" if r.get("skipped") else "❌")
                                    reason = r.get("skip_reason") or r.get("error") or "Imported"
                                    st.markdown(f"- {status} **{r.get('title', 'Unknown')[:50]}...** - {reason}")
                    else:
                        st.error(f"Import failed: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error during citation import: {e}")


# =============================================================================
# Upgrade Tab
# =============================================================================

def render_upgrade_tab():
    """Render PDF upgrade interface."""
    st.subheader("📤 Upgrade with PDF")
    st.markdown(
        "Abstract만 있는 논문(PubMed에서 임포트)에 전체 PDF를 추가하여 "
        "Full-text 검색을 가능하게 합니다."
    )

    # Get abstract-only papers
    papers = get_abstract_only_papers()

    if not papers:
        st.info("📭 No abstract-only papers found. All papers have full PDF data.")
        return

    st.markdown(f"**{len(papers)} papers available for upgrade:**")

    # Paper selector
    paper_options = {
        f"[{p.get('pmid', 'N/A')}] {p.get('title', 'Unknown')[:50]}...": p['paper_id']
        for p in papers
    }

    selected_paper_label = st.selectbox(
        "Select Paper to Upgrade",
        options=list(paper_options.keys()),
        help="PDF를 추가할 논문 선택"
    )

    if selected_paper_label:
        selected_paper_id = paper_options[selected_paper_label]

        # Show current paper info
        selected_paper = next(
            (p for p in papers if p['paper_id'] == selected_paper_id),
            None
        )
        if selected_paper:
            st.markdown(f"""
            **Current Status:**
            - Paper ID: `{selected_paper_id}`
            - PMID: {selected_paper.get('pmid', 'N/A')}
            - Source: {selected_paper.get('source', 'pubmed')}
            - Created: {selected_paper.get('created_at', 'N/A')}
            """)

        # PDF upload
        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
            help="논문 PDF 파일을 업로드하세요"
        )

        if uploaded_file:
            if st.button("🔄 Upgrade Paper", type="primary"):
                with st.spinner("Processing PDF and upgrading paper..."):
                    try:
                        # Save to temp file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(uploaded_file.read())
                            tmp_path = tmp.name

                        server = get_server()
                        result = run_async(server.upgrade_paper_with_pdf(
                            paper_id=selected_paper_id,
                            pdf_path=tmp_path
                        ))

                        # Clean up temp file
                        Path(tmp_path).unlink(missing_ok=True)

                        if result.get("success"):
                            st.success(
                                f"✅ Paper upgraded successfully!\n\n"
                                f"- **Old Chunks**: {result.get('old_chunks', 0)}\n"
                                f"- **New Chunks**: {result.get('new_chunks', 0)}\n"
                                f"- **Source**: {result.get('source', 'pdf+pubmed')}"
                            )
                        else:
                            st.error(f"Upgrade failed: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"Error during upgrade: {e}")


# =============================================================================
# Statistics Tab
# =============================================================================

def _get_import_stats_sync(neo4j) -> dict:
    """Get import statistics using sync Neo4j client.

    Args:
        neo4j: SyncNeo4jClient instance

    Returns:
        Statistics dict
    """
    try:
        # Total papers
        total_result = neo4j.run_query("MATCH (p:Paper) RETURN count(p) as count")
        total_papers = total_result[0]["count"] if total_result else 0

        # PDF papers (source contains 'pdf')
        pdf_result = neo4j.run_query("""
            MATCH (p:Paper)
            WHERE p.source IS NULL OR p.source CONTAINS 'pdf'
            RETURN count(p) as count
        """)
        pdf_papers = pdf_result[0]["count"] if pdf_result else 0

        # PubMed only papers
        pubmed_result = neo4j.run_query("""
            MATCH (p:Paper)
            WHERE p.source = 'pubmed' AND p.is_abstract_only = true
            RETURN count(p) as count
        """)
        pubmed_only = pubmed_result[0]["count"] if pubmed_result else 0

        # Upgraded papers (source = 'pdf+pubmed')
        upgraded_result = neo4j.run_query("""
            MATCH (p:Paper)
            WHERE p.source = 'pdf+pubmed'
            RETURN count(p) as count
        """)
        upgraded = upgraded_result[0]["count"] if upgraded_result else 0

        # Source distribution
        source_result = neo4j.run_query("""
            MATCH (p:Paper)
            WITH COALESCE(p.source, 'pdf') as source
            RETURN source, count(*) as count
            ORDER BY count DESC
        """)
        source_dist = {r["source"]: r["count"] for r in source_result}

        # Recent imports (last 10)
        recent_result = neo4j.run_query("""
            MATCH (p:Paper)
            WHERE p.created_at IS NOT NULL
            RETURN p.paper_id as paper_id, p.title as title,
                   p.source as source, p.created_at as created_at
            ORDER BY p.created_at DESC
            LIMIT 10
        """)

        return {
            "total_papers": total_papers,
            "pdf_papers": pdf_papers,
            "pubmed_only_papers": pubmed_only,
            "upgraded_papers": upgraded,
            "source_distribution": source_dist,
            "recent_imports": recent_result,
        }
    except Exception as e:
        st.error(f"Error fetching statistics: {e}")
        return {}


def render_statistics_tab():
    """Render import statistics."""
    st.subheader("📊 Import Statistics")

    # Refresh button
    if st.button("🔄 Refresh Statistics"):
        st.rerun()

    try:
        # Use sync Neo4j client to avoid event loop conflicts
        from utils.graph_utils import get_neo4j_client

        neo4j = get_neo4j_client()
        if not neo4j or not neo4j.is_available:
            st.warning("Neo4j connection not available")
            return

        # Query statistics using sync client
        stats = _get_import_stats_sync(neo4j)

        if not stats:
            st.warning("Could not fetch statistics")
            return

        # Overview metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Papers",
                stats.get("total_papers", 0),
                help="전체 논문 수"
            )

        with col2:
            st.metric(
                "PDF Papers",
                stats.get("pdf_papers", 0),
                help="PDF로 처리된 논문"
            )

        with col3:
            st.metric(
                "PubMed Only",
                stats.get("pubmed_only_papers", 0),
                help="Abstract만 있는 논문"
            )

        with col4:
            st.metric(
                "Upgraded",
                stats.get("upgraded_papers", 0),
                help="PDF로 업그레이드된 논문"
            )

        st.markdown("---")

        # Source distribution
        st.markdown("### Source Distribution")
        source_data = stats.get("source_distribution", {})
        if source_data:
            import plotly.express as px
            import pandas as pd

            df = pd.DataFrame([
                {"Source": k, "Count": v}
                for k, v in source_data.items()
            ])

            fig = px.pie(
                df,
                values="Count",
                names="Source",
                title="Papers by Source",
                color_discrete_sequence=["#3b82f6", "#22c55e", "#f59e0b"]
            )
            st.plotly_chart(fig, width="stretch")

        # Recent imports
        st.markdown("### Recent Imports")
        recent = stats.get("recent_imports", [])
        if recent:
            for paper in recent[:10]:
                title = paper.get("title", "Unknown")
                title_short = title[:60] + "..." if len(title) > 60 else title
                source = paper.get("source", "pdf")
                created = paper.get("created_at", "N/A")
                st.markdown(f"""
                - **{title_short}**
                  ({source}, {created})
                """)
        else:
            st.info("No recent imports")

    except Exception as e:
        st.error(f"Error fetching statistics: {e}")


# =============================================================================
# Main Page
# =============================================================================

def main():
    """Main page entry point."""
    init_session_state()

    st.title("📚 PubMed Import")
    st.markdown(
        "PubMed에서 논문을 대량으로 검색하고 시스템에 임포트합니다. "
        "임포트된 논문은 Neo4j 지식 그래프와 벡터 검색에서 사용됩니다 (v5.3)."
    )

    # Server status check
    try:
        server = get_server()
        if not server:
            st.error("❌ Server not available. Please check the MCP server status.")
            return
    except Exception as e:
        st.error(f"❌ Failed to connect to server: {e}")
        return

    # Tab navigation
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Search & Import",
        "📎 Citation Import",
        "📤 Upgrade with PDF",
        "📊 Statistics"
    ])

    with tab1:
        render_search_tab()

    with tab2:
        render_citation_tab()

    with tab3:
        render_upgrade_tab()

    with tab4:
        render_statistics_tab()


if __name__ == "__main__":
    main()
