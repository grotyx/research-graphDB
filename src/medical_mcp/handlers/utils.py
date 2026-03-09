"""Shared utilities for Medical KAG Server handlers.

This module provides common utility functions used across multiple handlers
to eliminate code duplication and maintain consistency.
"""

import re


def generate_document_id(metadata: dict, fallback_name: str) -> str:
    """메타데이터에서 document_id 생성.

    형식: FirstAuthor_Year_TitleWords

    Args:
        metadata: 추출된 메타데이터 (first_author, year, title)
        fallback_name: 폴백 이름 (파일명 또는 기본값)

    Returns:
        문서 ID 문자열 (최대 80자)

    Example:
        >>> metadata = {"first_author": "Kim", "year": 2023, "title": "Study of Spine Surgery"}
        >>> generate_document_id(metadata, "paper")
        'Kim_2023_Study_Spine_Surgery'
    """
    parts = []

    # 1. 첫 번째 저자
    if metadata.get("first_author"):
        author = metadata["first_author"]
        # 영문자만 유지
        author = re.sub(r'[^a-zA-Z]', '', author)
        if author:
            parts.append(author.capitalize())

    # 2. 연도
    if metadata.get("year") and metadata["year"] > 1900:
        parts.append(str(metadata["year"]))

    # 3. 제목에서 주요 단어 4개
    if metadata.get("title"):
        title = metadata["title"]
        # 불용어 제거
        stopwords = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with', 'by', 'from', 'at', 'is', 'are', 'was', 'were'}
        words = re.findall(r'[a-zA-Z]+', title)
        title_words = [w.capitalize() for w in words if w.lower() not in stopwords and len(w) > 2][:4]
        if title_words:
            parts.append('_'.join(title_words))

    # 결과 조합
    if len(parts) >= 2:
        doc_id = '_'.join(parts)
    else:
        # 폴백: 원래 파일명 사용
        doc_id = re.sub(r'[^a-zA-Z0-9_]', '_', fallback_name)

    # 길이 제한 및 정리
    doc_id = re.sub(r'_+', '_', doc_id)  # 중복 언더스코어 제거
    doc_id = doc_id.strip('_')
    doc_id = doc_id[:80]  # 최대 80자

    return doc_id


def get_abstract_from_sections(section_boundaries: list, full_text: str) -> str:
    """섹션 경계에서 초록 추출.

    Args:
        section_boundaries: 섹션 경계 목록 (section_type, start_char, end_char 속성 필요)
        full_text: 전체 텍스트

    Returns:
        추출된 초록 또는 첫 2000자

    Example:
        >>> sections = [Section(section_type="abstract", start_char=0, end_char=500)]
        >>> text = "This is abstract..." + "..." * 1000
        >>> abstract = get_abstract_from_sections(sections, text)
    """
    for section in section_boundaries:
        if hasattr(section, 'section_type') and section.section_type.lower() == 'abstract':
            start = getattr(section, 'start_char', 0)
            end = getattr(section, 'end_char', min(2000, len(full_text)))
            return full_text[start:end]

    # 초록을 찾지 못한 경우 첫 2000자 반환
    return full_text[:2000]


def determine_tier(section_type: str) -> str:
    """섹션 타입에 따른 Tier 결정.

    NOTE: Tier 구분 제거됨 - 모든 청크는 tier1으로 처리.
    섹션 타입은 메타데이터로 유지됨.

    Args:
        section_type: 섹션 타입 (abstract, introduction, methods, results, etc.)

    Returns:
        항상 "tier1" 반환

    Example:
        >>> determine_tier("abstract")
        'tier1'
        >>> determine_tier("results")
        'tier1'
    """
    # Tier 구분 제거 - 모든 청크를 단일 컬렉션(tier1)에 저장
    return "tier1"
