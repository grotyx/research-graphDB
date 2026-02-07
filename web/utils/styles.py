"""Shared Style Utilities for Streamlit Pages.

일관된 디자인 시스템을 위한 스타일 유틸리티 함수 제공.
"""

import streamlit as st
from pathlib import Path


def load_css():
    """전역 CSS 스타일 로드."""
    css_path = Path(__file__).parent.parent / "assets" / "style.css"

    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        # 기본 스타일 적용
        st.markdown(get_default_styles(), unsafe_allow_html=True)


def get_default_styles() -> str:
    """기본 스타일 반환 (CSS 파일 없을 경우)."""
    return """
    <style>
    /* 기본 스타일 */
    .main .block-container {
        max-width: 1400px;
        padding: 2rem;
    }

    .page-header {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
    }

    .card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border: 1px solid #e5e7eb;
        margin-bottom: 1rem;
    }
    </style>
    """


def render_page_header(
    title: str,
    subtitle: str = "",
    icon: str = "",
    gradient: str = "primary"
) -> None:
    """페이지 헤더 렌더링.

    Args:
        title: 페이지 제목
        subtitle: 부제목
        icon: 이모지 아이콘
        gradient: 그라디언트 유형 (primary, secondary, success)
    """
    gradient_classes = {
        "primary": "linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)",
        "secondary": "linear-gradient(135deg, #0f766e 0%, #14b8a6 100%)",
        "success": "linear-gradient(135deg, #15803d 0%, #22c55e 100%)",
        "warning": "linear-gradient(135deg, #b45309 0%, #f59e0b 100%)",
    }

    gradient_style = gradient_classes.get(gradient, gradient_classes["primary"])

    header_html = f"""
    <div style="
        background: {gradient_style};
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    ">
        <h1 style="margin: 0; font-size: 2rem; font-weight: 700;">
            {icon} {title}
        </h1>
        {f'<p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1.1rem;">{subtitle}</p>' if subtitle else ''}
    </div>
    """

    st.markdown(header_html, unsafe_allow_html=True)


def render_metric_card(
    label: str,
    value: str,
    delta: str = None,
    delta_color: str = "normal",
    icon: str = ""
) -> None:
    """메트릭 카드 렌더링.

    Args:
        label: 라벨
        value: 값
        delta: 변화량 (선택)
        delta_color: 변화 색상 (positive, negative, normal)
        icon: 아이콘
    """
    delta_html = ""
    if delta:
        color_map = {
            "positive": "#22c55e",
            "negative": "#ef4444",
            "normal": "#64748b"
        }
        color = color_map.get(delta_color, "#64748b")
        delta_html = f'<div style="font-size: 0.85rem; color: {color}; margin-top: 0.25rem;">{delta}</div>'

    html = f"""
    <div style="
        background: linear-gradient(135deg, #f8fafc 0%, white 100%);
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        border: 1px solid #e5e7eb;
        transition: all 0.2s ease;
    ">
        <div style="font-size: 0.85rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">
            {icon} {label}
        </div>
        <div style="font-size: 1.75rem; font-weight: 700; color: #1e40af; margin-top: 0.25rem;">
            {value}
        </div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_card(
    title: str = "",
    content: str = "",
    footer: str = "",
    variant: str = "default"
) -> None:
    """카드 컴포넌트 렌더링.

    Args:
        title: 카드 제목
        content: 카드 내용 (HTML)
        footer: 푸터 (선택)
        variant: 스타일 변형 (default, elevated, bordered)
    """
    style_variants = {
        "default": """
            background: white;
            border: 1px solid #e5e7eb;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        """,
        "elevated": """
            background: white;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        """,
        "bordered": """
            background: white;
            border: 2px solid #3b82f6;
        """
    }

    style = style_variants.get(variant, style_variants["default"])

    title_html = f"""
        <div style="
            font-size: 1.1rem;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid #f1f5f9;
        ">{title}</div>
    """ if title else ""

    footer_html = f"""
        <div style="
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid #f1f5f9;
            font-size: 0.875rem;
            color: #64748b;
        ">{footer}</div>
    """ if footer else ""

    html = f"""
    <div style="
        {style}
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    ">
        {title_html}
        {content}
        {footer_html}
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


def render_tag(
    text: str,
    color: str = "gray",
    size: str = "sm"
) -> str:
    """태그 HTML 반환.

    Args:
        text: 태그 텍스트
        color: 색상 (primary, secondary, success, warning, error, gray)
        size: 크기 (sm, md, lg)

    Returns:
        HTML 문자열
    """
    color_map = {
        "primary": ("#dbeafe", "#1e40af"),
        "secondary": ("#ccfbf1", "#0f766e"),
        "success": ("#dcfce7", "#15803d"),
        "warning": ("#fef3c7", "#b45309"),
        "error": ("#fee2e2", "#b91c1c"),
        "gray": ("#f3f4f6", "#4b5563")
    }

    size_map = {
        "sm": ("0.2rem 0.6rem", "0.75rem"),
        "md": ("0.3rem 0.8rem", "0.875rem"),
        "lg": ("0.4rem 1rem", "1rem")
    }

    bg_color, text_color = color_map.get(color, color_map["gray"])
    padding, font_size = size_map.get(size, size_map["sm"])

    return f"""<span style="
        display: inline-block;
        background: {bg_color};
        color: {text_color};
        padding: {padding};
        border-radius: 9999px;
        font-size: {font_size};
        font-weight: 500;
        margin-right: 0.25rem;
        margin-bottom: 0.25rem;
    ">{text}</span>"""


def render_alert(
    message: str,
    alert_type: str = "info",
    title: str = ""
) -> None:
    """알림 메시지 렌더링.

    Args:
        message: 메시지 내용
        alert_type: 유형 (info, success, warning, error)
        title: 제목 (선택)
    """
    config = {
        "info": {
            "bg": "#eff6ff",
            "border": "#93c5fd",
            "text": "#1e40af",
            "icon": "i"
        },
        "success": {
            "bg": "#f0fdf4",
            "border": "#86efac",
            "text": "#166534",
            "icon": "check"
        },
        "warning": {
            "bg": "#fffbeb",
            "border": "#fcd34d",
            "text": "#92400e",
            "icon": "!"
        },
        "error": {
            "bg": "#fef2f2",
            "border": "#fca5a5",
            "text": "#991b1b",
            "icon": "x"
        }
    }

    cfg = config.get(alert_type, config["info"])

    title_html = f"""
        <div style="font-weight: 600; margin-bottom: 0.25rem;">{title}</div>
    """ if title else ""

    html = f"""
    <div style="
        background: {cfg['bg']};
        border: 1px solid {cfg['border']};
        border-radius: 8px;
        padding: 1rem;
        color: {cfg['text']};
        margin-bottom: 1rem;
    ">
        {title_html}
        <div>{message}</div>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


def render_progress_bar(
    value: float,
    max_value: float = 100,
    color: str = "primary",
    height: int = 8,
    show_label: bool = False
) -> None:
    """프로그래스 바 렌더링.

    Args:
        value: 현재 값
        max_value: 최대 값
        color: 색상 (primary, success, warning, error)
        height: 높이 (px)
        show_label: 레이블 표시 여부
    """
    percentage = min(100, max(0, (value / max_value) * 100))

    color_map = {
        "primary": "#3b82f6",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "error": "#ef4444"
    }

    bar_color = color_map.get(color, "#3b82f6")

    label_html = f"""
        <span style="font-size: 0.75rem; color: #64748b; margin-left: 0.5rem;">
            {percentage:.0f}%
        </span>
    """ if show_label else ""

    html = f"""
    <div style="display: flex; align-items: center;">
        <div style="
            flex: 1;
            height: {height}px;
            background: #e5e7eb;
            border-radius: 9999px;
            overflow: hidden;
        ">
            <div style="
                width: {percentage}%;
                height: 100%;
                background: {bar_color};
                border-radius: 9999px;
                transition: width 0.3s ease;
            "></div>
        </div>
        {label_html}
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


def render_status_badge(
    status: str,
    text: str = ""
) -> str:
    """상태 배지 HTML 반환.

    Args:
        status: 상태 (online, offline, pending, active)
        text: 표시 텍스트 (없으면 status 사용)

    Returns:
        HTML 문자열
    """
    config = {
        "online": ("#dcfce7", "#166534", "#22c55e"),
        "offline": ("#fee2e2", "#991b1b", "#ef4444"),
        "pending": ("#fef3c7", "#92400e", "#f59e0b"),
        "active": ("#dbeafe", "#1e40af", "#3b82f6")
    }

    bg, text_color, dot_color = config.get(status, config["pending"])
    display_text = text or status.capitalize()

    return f"""<span style="
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: {bg};
        color: {text_color};
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.875rem;
        font-weight: 500;
    ">
        <span style="
            width: 8px;
            height: 8px;
            background: {dot_color};
            border-radius: 50%;
        "></span>
        {display_text}
    </span>"""


def render_divider(
    text: str = "",
    margin: str = "1.5rem"
) -> None:
    """구분선 렌더링.

    Args:
        text: 구분선 텍스트 (선택)
        margin: 상하 마진
    """
    if text:
        html = f"""
        <div style="
            display: flex;
            align-items: center;
            margin: {margin} 0;
        ">
            <div style="flex: 1; height: 1px; background: #e5e7eb;"></div>
            <span style="padding: 0 1rem; color: #64748b; font-size: 0.875rem;">{text}</span>
            <div style="flex: 1; height: 1px; background: #e5e7eb;"></div>
        </div>
        """
    else:
        html = f"""
        <div style="
            height: 1px;
            background: #e5e7eb;
            margin: {margin} 0;
        "></div>
        """

    st.markdown(html, unsafe_allow_html=True)


# Quick access functions
def page_config(
    title: str,
    icon: str = "",
    layout: str = "wide"
) -> None:
    """페이지 설정 (st.set_page_config 래퍼).

    Args:
        title: 페이지 제목
        icon: 이모지 아이콘
        layout: 레이아웃 (wide, centered)
    """
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout=layout
    )
    load_css()
