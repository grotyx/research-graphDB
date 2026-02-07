"""Documents Page - Reference Management System.

Enhanced PDF management with EndNote/Zotero-style features:
- Rich metadata display
- Collections and tags
- Advanced search and filters
- Citation export (BibTeX, RIS, Vancouver)
- Favorites and notes
"""

import html
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

st.set_page_config(page_title="Documents - Spine GraphRAG", page_icon="📄", layout="wide")

# Custom CSS for document card layout
st.markdown("""
<style>
/* Document card row - align items center vertically */
div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] > div[data-testid="stCheckbox"]) {
    align-items: center !important;
}
/* Action buttons column - flex center */
div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] > div[data-testid="stCheckbox"]) > div[data-testid="column"]:last-child {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
/* Remove extra padding from button containers */
div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] > div[data-testid="stCheckbox"]) button {
    padding: 0.25rem 0.5rem !important;
}
</style>
""", unsafe_allow_html=True)

import sys
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
    """Initialize session state for reference management."""
    if "selected_docs" not in st.session_state:
        st.session_state.selected_docs = set()
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "table"  # table, card, detail
    if "active_collection" not in st.session_state:
        st.session_state.active_collection = "all"
    if "doc_notes" not in st.session_state:
        st.session_state.doc_notes = {}
    if "doc_favorites" not in st.session_state:
        st.session_state.doc_favorites = set()
    if "doc_tags" not in st.session_state:
        st.session_state.doc_tags = {}
    # Upload progress tracking
    if "upload_completed_files" not in st.session_state:
        st.session_state.upload_completed_files = set()
    if "upload_processing_status" not in st.session_state:
        st.session_state.upload_processing_status = {}
    # File uploader key for reset
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0


# =============================================================================
# Upload Progress Rendering
# =============================================================================

def render_upload_progress(status_dict: dict) -> None:
    """Render progress cards for all files being processed."""
    for filename, status in status_dict.items():
        state = status.get("state", "waiting")
        progress = status.get("progress", 0)
        message = status.get("message", "")

        # State colors and icons
        state_config = {
            "waiting": {"icon": "⏳", "color": "#94a3b8", "bg": "#f8fafc", "label": "대기"},
            "uploading": {"icon": "📤", "color": "#3b82f6", "bg": "#eff6ff", "label": "업로드"},
            "processing": {"icon": "⚙️", "color": "#f59e0b", "bg": "#fffbeb", "label": "처리중"},
            "analyzing": {"icon": "🔬", "color": "#8b5cf6", "bg": "#f5f3ff", "label": "분석중"},
            "success": {"icon": "✅", "color": "#22c55e", "bg": "#f0fdf4", "label": "완료"},
            "error": {"icon": "❌", "color": "#ef4444", "bg": "#fef2f2", "label": "오류"},
        }

        config = state_config.get(state, state_config["waiting"])

        # Truncate filename for display
        display_name = filename[:35] + "..." if len(filename) > 35 else filename

        st.markdown(f"""
        <div style="
            background: {config['bg']};
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 10px;
            border-left: 4px solid {config['color']};
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 600; color: #1e293b; font-size: 0.9rem;">
                    {config['icon']} {display_name}
                </span>
                <span style="
                    font-size: 0.7rem;
                    padding: 3px 10px;
                    border-radius: 12px;
                    background: {config['color']}20;
                    color: {config['color']};
                    font-weight: 600;
                    text-transform: uppercase;
                ">{config['label']}</span>
            </div>
            <div style="
                background: #e2e8f0;
                border-radius: 6px;
                height: 8px;
                overflow: hidden;
                margin-bottom: 6px;
            ">
                <div style="
                    background: linear-gradient(90deg, {config['color']} 0%, {config['color']}cc 100%);
                    height: 100%;
                    width: {progress}%;
                    border-radius: 6px;
                    transition: width 0.3s ease;
                "></div>
            </div>
            <div style="font-size: 0.75rem; color: #64748b;">
                {message}
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_single_progress(filename: str, state: str, progress: int, message: str,
                          current: int = 0, total: int = 0) -> None:
    """Render a single-line progress indicator that updates in place.

    Args:
        filename: File name to display
        state: One of: waiting, uploading, processing, analyzing, success, error
        progress: Progress percentage (0-100)
        message: Status message to display
        current: Current file number (1-based)
        total: Total number of files
    """
    # State colors and icons
    state_config = {
        "waiting": {"icon": "⏳", "color": "#94a3b8", "label": "대기"},
        "uploading": {"icon": "📤", "color": "#3b82f6", "label": "업로드"},
        "processing": {"icon": "⚙️", "color": "#f59e0b", "label": "처리중"},
        "analyzing": {"icon": "🔬", "color": "#8b5cf6", "label": "분석중"},
        "success": {"icon": "✅", "color": "#22c55e", "label": "완료"},
        "error": {"icon": "❌", "color": "#ef4444", "label": "오류"},
    }

    config = state_config.get(state, state_config["waiting"])

    # File counter display
    counter_text = f"[{current}/{total}] " if current > 0 and total > 0 else ""

    # Single compact progress bar
    st.markdown(f"""
    <div style="
        background: white;
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    ">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 1.2rem;">{config['icon']}</span>
            <span style="font-weight: 600; color: #1e293b; flex: 1; font-size: 0.9rem;">
                {counter_text}{filename}
            </span>
            <span style="
                font-size: 0.7rem;
                padding: 3px 10px;
                border-radius: 12px;
                background: {config['color']}20;
                color: {config['color']};
                font-weight: 600;
            ">{config['label']} {progress}%</span>
        </div>
        <div style="
            background: #e2e8f0;
            border-radius: 4px;
            height: 6px;
            overflow: hidden;
        ">
            <div style="
                background: {config['color']};
                height: 100%;
                width: {progress}%;
                border-radius: 4px;
                transition: width 0.2s ease;
            "></div>
        </div>
        <div style="font-size: 0.75rem; color: #64748b; margin-top: 6px;">
            {message}
        </div>
    </div>
    """, unsafe_allow_html=True)


# =============================================================================
# Citation Export Functions
# =============================================================================

def generate_bibtex(doc: dict) -> str:
    """Generate BibTeX citation."""
    doc_id = doc.get("document_id", "unknown")
    title = doc.get("title", doc_id)
    authors = doc.get("authors", [])
    year = doc.get("year", "")
    journal = doc.get("journal", "")
    doi = doc.get("doi", "")

    # Create cite key
    first_author = authors[0].split()[-1] if authors else "Unknown"
    cite_key = f"{first_author}{year}"

    author_str = " and ".join(authors) if authors else ""

    bibtex = f"""@article{{{cite_key},
  title = {{{title}}},
  author = {{{author_str}}},
  year = {{{year}}},
  journal = {{{journal}}},
  doi = {{{doi}}}
}}"""
    return bibtex


def generate_ris(doc: dict) -> str:
    """Generate RIS citation."""
    title = doc.get("title", doc.get("document_id", ""))
    authors = doc.get("authors", [])
    year = doc.get("year", "")
    journal = doc.get("journal", "")
    doi = doc.get("doi", "")
    pmid = doc.get("pmid", "")

    lines = [
        "TY  - JOUR",
        f"TI  - {title}",
    ]

    for author in authors:
        lines.append(f"AU  - {author}")

    if year:
        lines.append(f"PY  - {year}")
    if journal:
        lines.append(f"JO  - {journal}")
    if doi:
        lines.append(f"DO  - {doi}")
    if pmid:
        lines.append(f"AN  - PMID:{pmid}")

    lines.append("ER  - ")

    return "\n".join(lines)


def generate_vancouver(doc: dict) -> str:
    """Generate Vancouver citation style."""
    authors = doc.get("authors", [])
    title = doc.get("title", doc.get("document_id", ""))
    journal = doc.get("journal", "")
    year = doc.get("year", "")
    doi = doc.get("doi", "")

    # Format authors (first 6, then et al.)
    if len(authors) > 6:
        author_str = ", ".join(authors[:6]) + ", et al."
    elif authors:
        author_str = ", ".join(authors)
    else:
        author_str = ""

    citation = f"{author_str}. {title}. {journal}. {year}."
    if doi:
        citation += f" doi:{doi}"

    return citation


def generate_apa(doc: dict) -> str:
    """Generate APA citation style."""
    authors = doc.get("authors", [])
    title = doc.get("title", doc.get("document_id", ""))
    journal = doc.get("journal", "")
    year = doc.get("year", "")
    doi = doc.get("doi", "")

    # Format authors for APA
    if len(authors) > 20:
        author_str = ", ".join(authors[:19]) + ", ... " + authors[-1]
    elif len(authors) > 1:
        author_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
    elif authors:
        author_str = authors[0]
    else:
        author_str = ""

    citation = f"{author_str} ({year}). {title}. *{journal}*."
    if doi:
        citation += f" https://doi.org/{doi}"

    return citation


# =============================================================================
# Document Display Components
# =============================================================================

def toggle_favorite(doc_id: str, is_favorite: bool):
    """Toggle favorite status."""
    if is_favorite:
        st.session_state.doc_favorites.discard(doc_id)
    else:
        st.session_state.doc_favorites.add(doc_id)

def toggle_note(doc_id: str):
    """Toggle note visibility."""
    key = f"show_note_{doc_id}"
    st.session_state[key] = not st.session_state.get(key, False)

def confirm_delete(doc_id: str):
    """Set delete confirmation flag."""
    st.session_state[f"confirm_delete_{doc_id}"] = True


def display_document_card(doc: dict, neo4j_client, idx: int):
    """Display document as a compact card with metadata."""
    doc_id = doc.get("document_id", "Unknown")
    chunks = doc.get("chunk_count", 0)
    tier1 = doc.get("tier1_chunks") or doc.get("tier1_count", 0)
    tier2 = doc.get("tier2_chunks") or doc.get("tier2_count", 0)

    # Use merged document data directly (already enriched from Neo4j)
    title = doc.get("title") or doc_id
    authors = doc.get("authors") or []
    year = doc.get("year") or ""
    journal = doc.get("journal") or ""
    evidence_level = doc.get("evidence_level") or ""
    sub_domain = doc.get("sub_domain") or ""
    doi = doc.get("doi") or ""
    pmid = doc.get("pmid") or ""
    source = doc.get("source") or "pdf"
    has_full_text = doc.get("has_full_text", chunks > 0)

    is_favorite = doc_id in st.session_state.doc_favorites
    is_selected = doc_id in st.session_state.selected_docs
    tags = st.session_state.doc_tags.get(doc_id, [])

    # Evidence level badge color
    level_colors = {
        "1a": "#22c55e", "1b": "#22c55e",
        "2a": "#3b82f6", "2b": "#3b82f6",
        "3": "#f59e0b", "4": "#ef4444", "5": "#6b7280"
    }
    level_color = level_colors.get(evidence_level, "#6b7280")

    # Build author string (escape HTML entities)
    author_str = ""
    if authors:
        author_str = html.escape(", ".join(str(a) for a in authors[:3]))
        if len(authors) > 3:
            author_str += f" +{len(authors)-3}"

    # Build meta string (escape HTML entities)
    meta_parts = []
    if journal:
        meta_parts.append(html.escape(str(journal)))
    if sub_domain:
        meta_parts.append(html.escape(str(sub_domain)))
    meta_parts.append(f"{chunks} chunks")
    meta_str = " • ".join(meta_parts)

    # Build links (DOI and PMID are safe IDs)
    links = []
    if doi:
        safe_doi = html.escape(str(doi))
        links.append(f'<a href="https://doi.org/{safe_doi}" target="_blank" style="color:#3b82f6;text-decoration:none;font-size:0.7rem;">DOI</a>')
    if pmid:
        safe_pmid = html.escape(str(pmid))
        links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{safe_pmid}" target="_blank" style="color:#3b82f6;text-decoration:none;font-size:0.7rem;">PMID</a>')
    links_str = " | ".join(links)

    # Build tags HTML (escape tag names)
    tags_html = ""
    if tags:
        tags_html = " ".join([f'<span style="background:#e2e8f0;padding:1px 6px;border-radius:4px;font-size:0.65rem;color:#475569;">{html.escape(str(t))}</span>' for t in tags])

    # Escape title for HTML
    title_escaped = html.escape(str(title)[:80])
    title_ellipsis = '...' if len(str(title)) > 80 else ''

    # Compact card HTML
    star = "⭐" if is_favorite else "☆"
    year_badge = f'<span style="background:#f1f5f9;padding:1px 6px;border-radius:4px;font-size:0.7rem;color:#64748b;margin-left:6px;">{html.escape(str(year))}</span>' if year else ""
    level_badge = f'<span style="background:{level_color}20;color:{level_color};padding:1px 6px;border-radius:4px;font-size:0.65rem;font-weight:600;margin-left:4px;">L{html.escape(str(evidence_level))}</span>' if evidence_level else ""

    # Source badge (PDF/PubMed/PDF+PubMed)
    source_config = {
        "pdf": {"icon": "📄", "color": "#22c55e", "label": "PDF"},
        "pubmed": {"icon": "🔬", "color": "#3b82f6", "label": "PubMed"},
        "pdf+pubmed": {"icon": "📄🔬", "color": "#8b5cf6", "label": "PDF+PM"}
    }
    src_cfg = source_config.get(source, source_config["pdf"])
    source_badge = f'<span style="background:{src_cfg["color"]}15;color:{src_cfg["color"]};padding:1px 5px;border-radius:4px;font-size:0.6rem;font-weight:600;margin-left:4px;" title="{src_cfg["label"]}">{src_cfg["icon"]}</span>'

    # Full text badge
    if has_full_text:
        fulltext_badge = '<span style="background:#dcfce7;color:#16a34a;padding:1px 5px;border-radius:4px;font-size:0.6rem;font-weight:600;margin-left:4px;" title="Full Text Available">📖</span>'
    else:
        fulltext_badge = '<span style="background:#f3f4f6;color:#9ca3af;padding:1px 5px;border-radius:4px;font-size:0.6rem;font-weight:600;margin-left:4px;" title="Abstract Only">📋</span>'

    # Note indicator
    note_indicator = ""
    if doc_id in st.session_state.doc_notes and st.session_state.doc_notes[doc_id]:
        note_indicator = '<span style="color:#f59e0b;margin-left:4px;" title="메모 있음">📝</span>'

    # Build style string
    bg_color = '#fffbeb' if is_favorite else '#fafafa'
    border_color = '#fcd34d' if is_favorite else '#e5e7eb'
    border_left = 'border-left:3px solid #f59e0b;' if is_favorite else ''

    # Build optional spans
    links_span = f'<span>{links_str}</span>' if links_str else ''
    tags_span = f'<span>{tags_html}</span>' if tags_html else ''
    display_author = author_str if author_str else 'Unknown'

    # Layout: checkbox | content | actions
    col_check, col_content, col_actions = st.columns([0.3, 8, 1.5])

    with col_check:
        if st.checkbox("선택", value=is_selected, key=f"sel_{idx}_{doc_id}", label_visibility="collapsed"):
            st.session_state.selected_docs.add(doc_id)
        else:
            st.session_state.selected_docs.discard(doc_id)

    with col_content:
        # Build HTML card
        card_html = f'<div style="background:{bg_color};border:1px solid {border_color};border-radius:6px;padding:8px 10px;{border_left}">'
        card_html += f'<div style="font-size:0.82rem;font-weight:600;color:#1f2937;line-height:1.3;margin-bottom:2px;">'
        card_html += f'<span style="color:#9ca3af;margin-right:6px;">{idx+1}.</span>{title_escaped}{title_ellipsis}{year_badge}{level_badge}{source_badge}{fulltext_badge}{note_indicator}</div>'
        card_html += f'<div style="font-size:0.7rem;color:#6b7280;margin-bottom:1px;">👤 {display_author}</div>'
        card_html += f'<div style="font-size:0.68rem;color:#9ca3af;display:flex;align-items:center;gap:6px;flex-wrap:wrap;"><span>{meta_str}</span>{links_span}{tags_span}</div>'
        card_html += '</div>'
        st.markdown(card_html, unsafe_allow_html=True)

    with col_actions:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.button(star, key=f"fav_{idx}_{doc_id}", on_click=lambda d=doc_id, f=is_favorite: toggle_favorite(d, f))
        with c2:
            st.button("📝", key=f"note_{idx}_{doc_id}", on_click=lambda d=doc_id: toggle_note(d))
        with c3:
            st.button("🗑", key=f"del_{idx}_{doc_id}", on_click=lambda d=doc_id: confirm_delete(d))

    # Note input (collapsible)
    if st.session_state.get(f"show_note_{doc_id}"):
        current_note = st.session_state.doc_notes.get(doc_id, "")
        new_note = st.text_area(
            "메모",
            value=current_note,
            key=f"note_input_{idx}_{doc_id}",
            height=80
        )
        col_save, col_cancel, _ = st.columns([1, 1, 4])
        with col_save:
            if st.button("💾 저장", key=f"save_note_{idx}_{doc_id}", use_container_width=True):
                st.session_state.doc_notes[doc_id] = new_note
                del st.session_state[f"show_note_{doc_id}"]
                st.rerun()
        with col_cancel:
            if st.button("✖ 취소", key=f"cancel_note_{idx}_{doc_id}", use_container_width=True):
                del st.session_state[f"show_note_{doc_id}"]
                st.rerun()

    # Delete confirmation
    if st.session_state.get(f"confirm_delete_{doc_id}"):
        st.warning(f"⚠️ '{doc_id[:30]}...'를 삭제하시겠습니까?")
        col_yes, col_no, _ = st.columns([1, 1, 4])
        with col_yes:
            if st.button("🗑️ 삭제", key=f"yes_del_{idx}_{doc_id}", type="primary", use_container_width=True):
                delete_document(doc_id)
        with col_no:
            if st.button("취소", key=f"no_del_{idx}_{doc_id}", use_container_width=True):
                del st.session_state[f"confirm_delete_{doc_id}"]
                st.rerun()


def display_document_table(documents: list, neo4j_client):
    """Display documents as a compact table."""
    import pandas as pd

    rows = []
    for doc in documents:
        doc_id = doc.get("document_id", "")
        title = doc.get("title") or doc_id
        source = doc.get("source") or "pdf"
        has_full_text = doc.get("has_full_text", doc.get("chunk_count", 0) > 0)

        # Source icon
        source_icon = {"pdf": "📄", "pubmed": "🔬", "pdf+pubmed": "📄🔬"}.get(source, "📄")
        fulltext_icon = "📖" if has_full_text else "📋"

        rows.append({
            "⭐": "⭐" if doc_id in st.session_state.doc_favorites else "",
            "Title": title[:60] + "..." if len(title) > 60 else title,
            "Year": doc.get("year") or "",
            "Journal": (doc.get("journal") or "")[:25] + "..." if len(doc.get("journal") or "") > 25 else (doc.get("journal") or ""),
            "Level": doc.get("evidence_level") or "",
            "Source": source_icon,
            "Text": fulltext_icon,
            "Chunks": doc.get("chunk_count", 0),
            "doc_id": doc_id  # Hidden column for actions
        })

    if rows:
        df = pd.DataFrame(rows)

        # Display with selection
        st.dataframe(
            df.drop(columns=["doc_id"]),
            use_container_width=True,
            hide_index=True
        )


def get_paper_metadata(neo4j_client, paper_id: str) -> dict:
    """Get enriched paper metadata from Neo4j."""
    if not neo4j_client:
        return {}

    try:
        result = neo4j_client.run_query(
            """
            MATCH (p:Paper {paper_id: $paper_id})
            RETURN p.title as title, p.authors as authors, p.year as year,
                   p.journal as journal, p.doi as doi, p.pmid as pmid,
                   p.evidence_level as evidence_level, p.sub_domain as sub_domain,
                   p.sub_domains as sub_domains, p.surgical_approach as surgical_approach,
                   p.abstract as abstract, p.source as source, p.is_abstract_only as is_abstract_only
            """,
            {"paper_id": paper_id}
        )
        return result[0] if result else {}
    except Exception:
        return {}


def get_all_papers_from_neo4j(neo4j_client) -> list[dict]:
    """Get all papers from Neo4j (including PubMed-imported).

    Returns:
        List of paper dictionaries with metadata
    """
    if not neo4j_client:
        return []

    try:
        result = neo4j_client.run_query(
            """
            MATCH (p:Paper)
            RETURN p.paper_id as paper_id, p.title as title, p.authors as authors,
                   p.year as year, p.journal as journal, p.doi as doi, p.pmid as pmid,
                   p.evidence_level as evidence_level, p.sub_domain as sub_domain,
                   p.sub_domains as sub_domains, p.surgical_approach as surgical_approach,
                   p.abstract as abstract, p.source as source, p.is_abstract_only as is_abstract_only
            ORDER BY p.year DESC, p.title
            """
        )
        return result if result else []
    except Exception:
        return []


def merge_neo4j_documents(list_docs_result: list, neo4j_papers: list) -> list[dict]:
    """Process Neo4j documents for display (v5.3 Neo4j-only).

    list_documents() now returns comprehensive Neo4j data with chunk counts.
    This function merges with additional paper metadata from Neo4j query.

    Returns:
        List of documents for display
    """
    # Create lookup from list_documents result (has chunk counts)
    docs_lookup = {d.get("document_id"): d for d in list_docs_result}

    merged = []
    seen_ids = set()

    # First, add all Neo4j papers
    for paper in neo4j_papers:
        paper_id = paper.get("paper_id", "")
        if not paper_id:
            continue

        # Get chunk info from list_documents result
        doc_info = docs_lookup.get(paper_id, {})
        chunk_count = doc_info.get("chunk_count", 0)

        doc = {
            "document_id": paper_id,
            "title": paper.get("title", paper_id),
            "authors": paper.get("authors", []),
            "year": paper.get("year", ""),
            "journal": paper.get("journal", ""),
            "doi": paper.get("doi", ""),
            "pmid": paper.get("pmid", ""),
            "evidence_level": paper.get("evidence_level", ""),
            "sub_domain": paper.get("sub_domain", ""),
            "sub_domains": paper.get("sub_domains", []),
            "surgical_approach": paper.get("surgical_approach", []),
            "abstract": paper.get("abstract", ""),
            "source": paper.get("source", "pdf"),
            "is_abstract_only": paper.get("is_abstract_only", False),
            # Chunk info from Neo4j (v5.3)
            "chunk_count": chunk_count,
            "tier1_chunks": doc_info.get("tier1_chunks", 0),
            "tier2_chunks": doc_info.get("tier2_chunks", 0),
            "has_full_text": chunk_count > 0,
        }

        merged.append(doc)
        seen_ids.add(paper_id)

    # Add any documents from list_documents not in Neo4j papers query
    for doc_id, doc_info in docs_lookup.items():
        if doc_id not in seen_ids:
            chunk_count = doc_info.get("chunk_count", 0)
            meta = doc_info.get("metadata", {})
            merged.append({
                "document_id": doc_id,
                "title": meta.get("title", doc_id),
                "authors": [],
                "year": meta.get("year", ""),
                "journal": "",
                "doi": "",
                "pmid": "",
                "evidence_level": meta.get("evidence_level", ""),
                "sub_domain": "",
                "sub_domains": [],
                "surgical_approach": [],
                "abstract": "",
                "source": meta.get("source", "pdf"),
                "is_abstract_only": chunk_count == 0,
                "chunk_count": chunk_count,
                "tier1_chunks": doc_info.get("tier1_chunks", 0),
                "tier2_chunks": doc_info.get("tier2_chunks", 0),
                "has_full_text": chunk_count > 0,
            })

    return merged


def delete_document(doc_id: str):
    """Delete document from Neo4j (v5.3 Neo4j-only)."""
    bridge = get_server()
    server = bridge.server

    with st.spinner("Deleting from Neo4j..."):
        del_result = run_async(server.delete_document(doc_id))
        if del_result.get("success"):
            chunks = del_result.get("deleted_chunks", 0)
            nodes = del_result.get("neo4j_nodes", 0)
            rels = del_result.get("neo4j_relationships", 0)
            st.success(
                f"✅ Deleted {doc_id}\n\n"
                f"- Neo4j Chunks: {chunks}\n"
                f"- Neo4j Nodes: {nodes}, Relationships: {rels}"
            )
            # Clean up session state
            st.session_state.selected_docs.discard(doc_id)
            st.session_state.doc_favorites.discard(doc_id)
            if doc_id in st.session_state.doc_notes:
                del st.session_state.doc_notes[doc_id]
            if f"confirm_delete_{doc_id}" in st.session_state:
                del st.session_state[f"confirm_delete_{doc_id}"]
            st.rerun()
        else:
            st.error(f"Failed: {del_result.get('error')}")


# =============================================================================
# Main Application
# =============================================================================

def main():
    init_session_state()

    # Custom CSS for compact buttons
    st.markdown("""
    <style>
    /* Sidebar button styles - prevent text wrapping */
    section[data-testid="stSidebar"] button {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    section[data-testid="stSidebar"] button p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    /* Action buttons - minimal style */
    .main button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    .main button:hover {
        background: rgba(0,0,0,0.05) !important;
    }
    .main button p {
        font-size: 1rem !important;
    }
    /* Reduce checkbox size and vertically center */
    div[data-testid="stCheckbox"] {
        transform: scale(0.85);
        margin-top: 8px;
    }
    /* Reduce gaps between cards */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.3rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("📄 Reference Library")
    st.markdown("**논문 관리 및 서지 정보 시스템** • EndNote/Zotero 스타일")

    bridge = get_server()
    server = bridge.server
    neo4j_client = get_neo4j_client()

    # =========================================================================
    # Sidebar - Collections & Filters
    # =========================================================================

    with st.sidebar:
        st.subheader("📚 Collections")

        collections = ["all", "favorites", "recent", "untagged"]
        collection_labels = {
            "all": "📁 All Papers",
            "favorites": "⭐ Favorites",
            "recent": "🕐 Recently Added",
            "untagged": "🏷️ Untagged"
        }

        for col_id in collections:
            if st.button(
                collection_labels[col_id],
                key=f"col_{col_id}",
                use_container_width=True,
                type="primary" if st.session_state.active_collection == col_id else "secondary"
            ):
                st.session_state.active_collection = col_id
                st.rerun()

        st.divider()

        st.subheader("🏷️ Tags")
        # Collect all unique tags
        all_tags = set()
        for tags in st.session_state.doc_tags.values():
            all_tags.update(tags)

        if all_tags:
            for tag in sorted(all_tags):
                count = sum(1 for tags in st.session_state.doc_tags.values() if tag in tags)
                if st.button(f"`{tag}` ({count})", key=f"tag_{tag}", use_container_width=True):
                    st.session_state.active_collection = f"tag:{tag}"
                    st.rerun()
        else:
            st.caption("태그가 없습니다")

    # =========================================================================
    # Main Content Tabs
    # =========================================================================

    tab_library, tab_upload, tab_export = st.tabs([
        "📚 **Library**",
        "📤 **Upload**",
        "📥 **Export**"
    ])

    # =========================================================================
    # Tab 1: Library
    # =========================================================================

    with tab_library:
        # Toolbar Row 1: Search and basic controls
        toolbar_cols = st.columns([3, 1, 1, 1, 1])

        with toolbar_cols[0]:
            search_query = st.text_input(
                "🔍 Search",
                placeholder="제목, 저자, DOI로 검색...",
                label_visibility="collapsed"
            )

        with toolbar_cols[1]:
            sort_options = {
                "year_desc": "Year ↓",
                "year_asc": "Year ↑",
                "title": "Title A-Z",
                "chunks": "Chunks ↓"
            }
            sort_by = st.selectbox(
                "Sort",
                options=list(sort_options.keys()),
                format_func=lambda x: sort_options[x],
                label_visibility="collapsed"
            )

        with toolbar_cols[2]:
            view_mode = st.selectbox(
                "View",
                options=["card", "table"],
                format_func=lambda x: "🃏 Card" if x == "card" else "📋 Table",
                label_visibility="collapsed"
            )
            st.session_state.view_mode = view_mode

        with toolbar_cols[3]:
            if st.button("🔄 Refresh"):
                st.rerun()

        with toolbar_cols[4]:
            # Bulk actions
            if st.session_state.selected_docs:
                if st.button(f"🗑️ Delete ({len(st.session_state.selected_docs)})"):
                    st.session_state.show_bulk_delete = True

        # Toolbar Row 2: Source and Full Text filters
        filter_cols = st.columns([1, 1, 4])

        with filter_cols[0]:
            source_filter = st.selectbox(
                "📦 Source",
                options=["all", "pdf", "pubmed", "pdf+pubmed"],
                format_func=lambda x: {
                    "all": "🌐 All Sources",
                    "pdf": "📄 PDF Only",
                    "pubmed": "🔬 PubMed Only",
                    "pdf+pubmed": "📄🔬 PDF+PubMed"
                }[x],
                label_visibility="collapsed"
            )

        with filter_cols[1]:
            fulltext_filter = st.selectbox(
                "📝 Full Text",
                options=["all", "full_text", "abstract_only"],
                format_func=lambda x: {
                    "all": "📚 All Papers",
                    "full_text": "📖 Full Text",
                    "abstract_only": "📋 Abstract Only"
                }[x],
                label_visibility="collapsed"
            )

        # Bulk delete confirmation
        if st.session_state.get("show_bulk_delete"):
            st.warning(f"선택한 {len(st.session_state.selected_docs)}개 문서를 삭제하시겠습니까?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("예, 모두 삭제", type="primary"):
                    for doc_id in list(st.session_state.selected_docs):
                        delete_document(doc_id)
                    st.session_state.selected_docs.clear()
                    del st.session_state["show_bulk_delete"]
            with col2:
                if st.button("취소"):
                    del st.session_state["show_bulk_delete"]
                    st.rerun()

        st.divider()

        # Get documents from Neo4j (v5.3 Neo4j-only)
        list_result = run_async(server.list_documents())
        list_docs = list_result.get("documents", []) if list_result.get("success") else []

        # Get all papers from Neo4j (including PubMed-imported)
        neo4j_papers = get_all_papers_from_neo4j(neo4j_client)

        # Merge document info (v5.3: all data from Neo4j)
        documents = merge_neo4j_documents(list_docs, neo4j_papers)
        total = len(documents)

        # Count by source for stats
        pdf_count = sum(1 for d in documents if d.get("source") == "pdf")
        pubmed_count = sum(1 for d in documents if d.get("source") == "pubmed")
        merged_count = sum(1 for d in documents if d.get("source") == "pdf+pubmed")
        fulltext_count = sum(1 for d in documents if d.get("has_full_text"))
        abstract_only_count = total - fulltext_count

        # Apply source filter
        if source_filter != "all":
            documents = [d for d in documents if d.get("source") == source_filter]

        # Apply full text filter
        if fulltext_filter == "full_text":
            documents = [d for d in documents if d.get("has_full_text")]
        elif fulltext_filter == "abstract_only":
            documents = [d for d in documents if not d.get("has_full_text")]

        # Apply collection filter
        active_col = st.session_state.active_collection
        if active_col == "favorites":
            documents = [d for d in documents if d.get("document_id") in st.session_state.doc_favorites]
        elif active_col == "untagged":
            documents = [d for d in documents if d.get("document_id") not in st.session_state.doc_tags]
        elif active_col.startswith("tag:"):
            tag = active_col[4:]
            documents = [d for d in documents if tag in st.session_state.doc_tags.get(d.get("document_id"), [])]

        # Apply search filter
        if search_query:
            search_lower = search_query.lower()
            filtered = []
            for d in documents:
                doc_id = d.get("document_id", "")
                title = (d.get("title") or doc_id).lower()
                authors = " ".join(d.get("authors") or []).lower()
                doi = (d.get("doi") or "").lower()

                if search_lower in doc_id.lower() or search_lower in title or search_lower in authors or search_lower in doi:
                    filtered.append(d)
            documents = filtered

        # Apply sorting
        if sort_by == "year_desc":
            documents.sort(key=lambda x: x.get("year") or 0, reverse=True)
        elif sort_by == "year_asc":
            documents.sort(key=lambda x: x.get("year") or 9999)
        elif sort_by == "chunks":
            documents.sort(key=lambda x: x.get("chunk_count", 0), reverse=True)
        else:  # title
            documents.sort(key=lambda x: (x.get("title") or x.get("document_id", "")).lower())

        # Stats bar with source breakdown
        stats_cols = st.columns(6)
        with stats_cols[0]:
            st.metric("Total", total)
        with stats_cols[1]:
            st.metric("Showing", len(documents))
        with stats_cols[2]:
            st.metric("📄 PDF", pdf_count)
        with stats_cols[3]:
            st.metric("🔬 PubMed", pubmed_count + merged_count)
        with stats_cols[4]:
            st.metric("📖 Full Text", fulltext_count)
        with stats_cols[5]:
            st.metric("📋 Abstract", abstract_only_count)

        st.divider()

        # Display documents
        if documents:
            if st.session_state.view_mode == "card":
                for idx, doc in enumerate(documents):
                    display_document_card(doc, neo4j_client, idx)
            else:
                display_document_table(documents, neo4j_client)
        else:
            st.info("📭 No documents found matching your criteria.")

    # =========================================================================
    # Tab 2: Upload
    # =========================================================================

    with tab_upload:
        st.subheader("📤 Upload PDFs")
        st.markdown("PDF 논문을 업로드하여 라이브러리에 추가합니다.")

        # File uploader (key changes to reset after upload)
        uploaded_files = st.file_uploader(
            "PDF 파일을 드래그하거나 클릭하여 선택하세요",
            type=["pdf"],
            accept_multiple_files=True,
            help="의학 논문 PDF 파일을 업로드합니다. LLM 메타데이터 추출 및 Neo4j 관계 분석이 자동으로 수행됩니다.",
            key=f"pdf_uploader_{st.session_state.uploader_key}"
        )

        # Filter out completed files
        pending_files = []
        if uploaded_files:
            pending_files = [f for f in uploaded_files if f.name not in st.session_state.upload_completed_files]

        # Show pending files
        if pending_files:
            col_files, col_options = st.columns([2, 1])

            with col_files:
                st.markdown(f"**📋 대기 중인 파일: {len(pending_files)}개**")
                for f in pending_files:
                    size_mb = len(f.getvalue()) / (1024 * 1024)
                    st.markdown(f"- `{f.name}` ({size_mb:.1f}MB)")

            with col_options:
                # Auto-processing info (no checkboxes)
                st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
                    border-radius: 12px;
                    padding: 16px;
                    border: 1px solid #bbf7d0;
                ">
                    <div style="font-size: 0.9rem; color: #15803d; font-weight: 600; margin-bottom: 8px;">
                        ⚙️ 자동 처리
                    </div>
                    <div style="font-size: 0.8rem; color: #166534;">
                        ✓ LLM 메타데이터 추출<br>
                        ✓ Neo4j 그래프 관계 분석<br>
                        ✓ Neo4j 벡터 임베딩 (v5.3)
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("")

                # Optional tags for new uploads
                new_tags = st.text_input(
                    "🏷️ Tags (선택사항)",
                    placeholder="tag1, tag2, tag3",
                    help="쉼표로 구분하여 태그 추가"
                )

            # Upload button
            if st.button("📤 Upload All", type="primary", use_container_width=True):
                tags_list = [t.strip() for t in new_tags.split(",") if t.strip()] if new_tags else []

                st.markdown("---")
                st.markdown("### 📊 처리 현황")

                # Layout: Progress on left, Log on right
                col_progress, col_log = st.columns([1, 1])

                with col_progress:
                    st.markdown("**🔄 현재 진행:**")
                    progress_placeholder = st.empty()

                with col_log:
                    st.markdown("**📝 처리 로그:**")
                    log_container = st.container()

                summary_placeholder = st.empty()

                success_count = 0
                error_count = 0
                completed_files = []
                total_files = len(pending_files)

                for i, uploaded_file in enumerate(pending_files):
                    current_num = i + 1
                    filename = uploaded_file.name
                    display_name = filename[:40] + "..." if len(filename) > 40 else filename

                    # Update progress: Uploading
                    with progress_placeholder.container():
                        render_single_progress(display_name, "uploading", 15, "파일 업로드 중...",
                                             current=current_num, total=total_files)

                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name

                    try:
                        # Update progress: Processing
                        with progress_placeholder.container():
                            render_single_progress(display_name, "processing", 40, "PDF 분석 및 메타데이터 추출 중...",
                                                 current=current_num, total=total_files)

                        result = run_async(server.add_pdf(
                            file_path=tmp_path,
                            metadata={"original_filename": filename}
                        ))

                        # Update progress: Analyzing
                        with progress_placeholder.container():
                            render_single_progress(display_name, "analyzing", 75, "그래프 관계 구축 중...",
                                                 current=current_num, total=total_files)

                        if result.get("success"):
                            doc_id = result.get("document_id", "Unknown")

                            # Update progress: Success
                            with progress_placeholder.container():
                                render_single_progress(display_name, "success", 100, f"완료! ID: {doc_id[:20]}...",
                                                     current=current_num, total=total_files)

                            st.session_state.upload_completed_files.add(filename)
                            completed_files.append(filename)
                            success_count += 1

                            # Write log immediately to container
                            with log_container:
                                st.markdown(f"✅ `{display_name}` → {doc_id[:25]}")

                            # Add tags if specified
                            if tags_list:
                                st.session_state.doc_tags[doc_id] = tags_list
                        else:
                            error_msg = result.get('error', 'Unknown error')[:50]
                            with progress_placeholder.container():
                                render_single_progress(display_name, "error", 100, f"오류: {error_msg}",
                                                     current=current_num, total=total_files)
                            error_count += 1

                            # Write error log immediately
                            with log_container:
                                st.markdown(f"❌ `{display_name}` → {error_msg}")

                    except Exception as e:
                        error_msg = str(e)[:50]
                        with progress_placeholder.container():
                            render_single_progress(display_name, "error", 100, f"예외: {error_msg}",
                                                 current=current_num, total=total_files)
                        error_count += 1

                        # Write exception log immediately
                        with log_container:
                            st.markdown(f"❌ `{display_name}` → 예외: {error_msg}")

                    finally:
                        Path(tmp_path).unlink(missing_ok=True)

                # Clear progress after all files processed
                progress_placeholder.empty()

                # Final summary
                with summary_placeholder.container():
                    st.markdown(f"**📋 전체 파일: {total_files}개**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("✅ 성공", success_count)
                    with col2:
                        st.metric("❌ 실패", error_count)
                    with col3:
                        st.metric("📊 처리됨", success_count + error_count)

                    if success_count > 0:
                        st.success(f"🎉 {success_count}/{total_files}개 파일 처리 완료!")
                        st.balloons()
                        # Reset uploader by changing key and rerun
                        import time
                        time.sleep(1.5)
                        st.session_state.uploader_key += 1
                        st.session_state.upload_completed_files.clear()
                        st.rerun()

        elif uploaded_files:
            # All files already completed
            st.success("✅ 모든 파일이 이미 처리되었습니다.")
            if st.button("🔄 새 파일 업로드", help="완료 목록을 초기화하고 새 파일을 업로드합니다"):
                st.session_state.uploader_key += 1
                st.session_state.upload_completed_files.clear()
                st.session_state.upload_processing_status.clear()
                st.rerun()
        else:
            st.info("📁 PDF 파일을 선택하여 업로드를 시작하세요.")

    # =========================================================================
    # Tab 3: Export
    # =========================================================================

    with tab_export:
        st.subheader("📥 Export Citations")
        st.markdown("선택한 논문의 서지 정보를 다양한 형식으로 내보냅니다.")

        # Get all documents for export
        result = run_async(server.list_documents())
        documents = result.get("documents", []) if result.get("success") else []

        # Filter options
        export_option = st.radio(
            "Export scope",
            options=["selected", "favorites", "all"],
            format_func=lambda x: {
                "selected": f"🔘 Selected ({len(st.session_state.selected_docs)})",
                "favorites": f"⭐ Favorites ({len(st.session_state.doc_favorites)})",
                "all": f"📁 All ({len(documents)})"
            }[x],
            horizontal=True
        )

        # Determine which documents to export
        if export_option == "selected":
            export_docs = [d for d in documents if d.get("document_id") in st.session_state.selected_docs]
        elif export_option == "favorites":
            export_docs = [d for d in documents if d.get("document_id") in st.session_state.doc_favorites]
        else:
            export_docs = documents

        if not export_docs:
            st.warning("내보낼 문서가 없습니다.")
        else:
            st.info(f"📄 {len(export_docs)} documents to export")

            # Format selection
            export_format = st.selectbox(
                "Citation Format",
                options=["bibtex", "ris", "vancouver", "apa"],
                format_func=lambda x: {
                    "bibtex": "BibTeX (.bib)",
                    "ris": "RIS (.ris) - EndNote/Mendeley",
                    "vancouver": "Vancouver Style",
                    "apa": "APA Style"
                }[x]
            )

            # Generate citations
            if st.button("🔄 Generate Citations", type="primary"):
                citations = []

                for doc in export_docs:
                    doc_id = doc.get("document_id", "")
                    enriched = get_paper_metadata(neo4j_client, doc_id) if neo4j_client else {}
                    enriched["document_id"] = doc_id

                    if export_format == "bibtex":
                        citations.append(generate_bibtex(enriched))
                    elif export_format == "ris":
                        citations.append(generate_ris(enriched))
                    elif export_format == "vancouver":
                        citations.append(generate_vancouver(enriched))
                    else:
                        citations.append(generate_apa(enriched))

                # Join citations
                if export_format == "bibtex":
                    output = "\n\n".join(citations)
                    filename = "citations.bib"
                    mime = "text/plain"
                elif export_format == "ris":
                    output = "\n\n".join(citations)
                    filename = "citations.ris"
                    mime = "application/x-research-info-systems"
                else:
                    output = "\n\n".join([f"{i+1}. {c}" for i, c in enumerate(citations)])
                    filename = f"citations_{export_format}.txt"
                    mime = "text/plain"

                # Display preview
                st.text_area("Preview", value=output, height=300)

                # Download button
                st.download_button(
                    "📥 Download",
                    output,
                    filename,
                    mime,
                    use_container_width=True
                )


if __name__ == "__main__":
    main()
