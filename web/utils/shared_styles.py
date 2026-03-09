"""Shared styles for all Streamlit pages.

This module provides common CSS that should be loaded on every page
to ensure consistent sidebar styling.
"""

import streamlit as st

SIDEBAR_CSS = """
<style>
/* Sidebar - 메인 페이지 이름 변경 (app → 🏠 Home) */
[data-testid="stSidebarNav"] ul li:first-child a span {
    font-size: 0 !important;
}
[data-testid="stSidebarNav"] ul li:first-child a span::before {
    content: "🏠 Home";
    font-size: 14px !important;
    visibility: visible !important;
}
</style>
"""


def apply_sidebar_styles():
    """Apply sidebar styles including main page rename.

    Call this function at the top of each page (after st.set_page_config).
    """
    st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)
