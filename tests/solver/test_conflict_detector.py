"""Tests for ConflictDetector module.

테스트 시나리오:
1. 특정 Intervention-Outcome 쌍의 충돌 탐지
2. 모든 충돌 검색 및 필터링
3. 심각도 계산 로직 검증
4. 신뢰도 계산 검증
5. 요약 생성 품질 확인
"""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.solver.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
    ConflictResult,
    PaperEvidence,
    EVIDENCE_LEVEL_SCORES,
)


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j 클라이언트."""
    client = MagicMock()
    client.run_query = AsyncMock()
    return client


@pytest.fixture
def sample_conflict_data():
    """샘플 충돌 데이터 (TLIF → VAS)."""
    return [
        {
            "paper_id": "paper_001",
            "title": "TLIF improves VAS in degenerative spondylolisthesis",
            "evidence_level": "1b",
            "direction": "improved",
            "value": "2.1",
            "value_control": "5.3",
            "p_value": 0.001,
            "is_significant": True,
        },
        {
            "paper_id": "paper_002",
            "title": "TLIF shows no benefit for VAS in elderly patients",
            "evidence_level": "2b",
            "direction": "worsened",
            "value": "4.5",
            "value_control": "3.8",
            "p_value": 0.03,
            "is_significant": True,
        },
        {
            "paper_id": "paper_003",
            "title": "TLIF improves pain outcomes at 2-year follow-up",
            "evidence_level": "2a",
            "direction": "improved",
            "value": "1.9",
            "value_control": "4.1",
            "p_value": 0.002,
            "is_significant": True,
        },
    ]


@pytest.fixture
def sample_no_conflict_data():
    """샘플 비충돌 데이터 (모두 improved)."""
    return [
        {
            "paper_id": "paper_101",
            "title": "UBE improves ODI",
            "evidence_level": "1b",
            "direction": "improved",
            "value": "65%",
            "value_control": "45%",
            "p_value": 0.001,
            "is_significant": True,
        },
        {
            "paper_id": "paper_102",
            "title": "UBE shows good functional outcomes",
            "evidence_level": "2b",
            "direction": "improved",
            "value": "58%",
            "value_control": "40%",
            "p_value": 0.01,
            "is_significant": True,
        },
    ]


# ============================================================================
# Test: detect_conflicts()
# ============================================================================

@pytest.mark.asyncio
async def test_detect_conflicts_with_conflict(mock_neo4j_client, sample_conflict_data):
    """충돌이 있는 경우 탐지 성공."""
    mock_neo4j_client.run_query.return_value = sample_conflict_data

    detector = ConflictDetector(mock_neo4j_client)
    conflict = await detector.detect_conflicts("TLIF", "VAS")

    # 충돌이 탐지되어야 함
    assert conflict is not None
    assert conflict.intervention == "TLIF"
    assert conflict.outcome == "VAS"
    assert conflict.has_significant_conflict is True

    # 방향별 분류 확인
    assert len(conflict.papers_improved) == 2  # paper_001, paper_003
    assert len(conflict.papers_worsened) == 1  # paper_002
    assert len(conflict.papers_unchanged) == 0

    # 심각도 (Level 1b가 포함되므로 CRITICAL)
    assert conflict.severity == ConflictSeverity.CRITICAL

    # 신뢰도
    assert 0.0 < conflict.confidence <= 1.0

    # 요약 생성 확인
    assert "TLIF → VAS" in conflict.summary
    assert "CRITICAL" in conflict.summary
    assert "paper_001" in conflict.summary or "paper_002" in conflict.summary


@pytest.mark.asyncio
async def test_detect_conflicts_no_conflict(mock_neo4j_client, sample_no_conflict_data):
    """충돌이 없는 경우 None 반환."""
    mock_neo4j_client.run_query.return_value = sample_no_conflict_data

    detector = ConflictDetector(mock_neo4j_client)
    conflict = await detector.detect_conflicts("UBE", "ODI")

    # 충돌이 없으므로 None
    assert conflict is None


@pytest.mark.asyncio
async def test_detect_conflicts_no_data(mock_neo4j_client):
    """데이터가 없는 경우 None 반환."""
    mock_neo4j_client.run_query.return_value = []

    detector = ConflictDetector(mock_neo4j_client)
    conflict = await detector.detect_conflicts("Nonexistent", "Outcome")

    assert conflict is None


@pytest.mark.asyncio
async def test_detect_conflicts_query_error(mock_neo4j_client):
    """쿼리 에러 발생 시 None 반환."""
    mock_neo4j_client.run_query.side_effect = Exception("Neo4j connection error")

    detector = ConflictDetector(mock_neo4j_client)
    conflict = await detector.detect_conflicts("TLIF", "VAS")

    assert conflict is None


# ============================================================================
# Test: find_all_conflicts()
# ============================================================================

@pytest.mark.asyncio
async def test_find_all_conflicts(mock_neo4j_client, sample_conflict_data):
    """모든 충돌 검색."""
    # Mock: Intervention-Outcome 쌍 조회
    pairs_data = [
        {"intervention": "TLIF", "outcome": "VAS", "paper_count": 3},
        {"intervention": "UBE", "outcome": "ODI", "paper_count": 2},
    ]

    # Mock: 각 쌍에 대한 AFFECTS 데이터
    async def mock_run_query(query, params=None):
        if "DISTINCT a.source_paper_id" in query:
            return pairs_data
        elif params and params.get("intervention") == "TLIF":
            return sample_conflict_data
        else:
            return []  # UBE → ODI는 충돌 없음

    mock_neo4j_client.run_query = mock_run_query

    detector = ConflictDetector(mock_neo4j_client)
    conflicts = await detector.find_all_conflicts()

    # TLIF → VAS 충돌만 반환되어야 함
    assert len(conflicts) == 1
    assert conflicts[0].intervention == "TLIF"
    assert conflicts[0].outcome == "VAS"


@pytest.mark.asyncio
async def test_find_all_conflicts_with_severity_filter(mock_neo4j_client):
    """심각도 필터링."""
    # Mock: 다양한 심각도의 충돌 데이터
    async def mock_run_query(query, params=None):
        if "DISTINCT a.source_paper_id" in query:
            return [
                {"intervention": "TLIF", "outcome": "VAS", "paper_count": 2},
                {"intervention": "UBE", "outcome": "ODI", "paper_count": 2},
            ]
        elif params and params.get("intervention") == "TLIF":
            # CRITICAL conflict (Level 1b)
            return [
                {"paper_id": "p1", "title": "T1", "evidence_level": "1b",
                 "direction": "improved", "value": "2.1", "value_control": "5.3",
                 "p_value": 0.001, "is_significant": True},
                {"paper_id": "p2", "title": "T2", "evidence_level": "2b",
                 "direction": "worsened", "value": "4.5", "value_control": "3.8",
                 "p_value": 0.03, "is_significant": True},
            ]
        else:  # UBE
            # LOW conflict (Level 4)
            return [
                {"paper_id": "p3", "title": "T3", "evidence_level": "4",
                 "direction": "improved", "value": "X", "value_control": "Y",
                 "p_value": None, "is_significant": False},
                {"paper_id": "p4", "title": "T4", "evidence_level": "5",
                 "direction": "worsened", "value": "X", "value_control": "Y",
                 "p_value": None, "is_significant": False},
            ]

    mock_neo4j_client.run_query = mock_run_query

    detector = ConflictDetector(mock_neo4j_client)

    # HIGH 이상만 필터링
    conflicts = await detector.find_all_conflicts(min_severity=ConflictSeverity.HIGH)

    # TLIF만 반환되어야 함 (CRITICAL)
    assert len(conflicts) == 1
    assert conflicts[0].intervention == "TLIF"
    assert conflicts[0].severity == ConflictSeverity.CRITICAL


# ============================================================================
# Test: Severity Calculation
# ============================================================================

def test_calculate_severity_critical():
    """CRITICAL 심각도 계산 (Level 1)."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "1a", "improved", "2", "5", 0.001, True)
        ],
        papers_worsened=[
            PaperEvidence("p2", "T2", "1b", "worsened", "4", "3", 0.02, True)
        ],
    )

    detector = ConflictDetector(MagicMock())
    severity = detector._calculate_severity(conflict)

    assert severity == ConflictSeverity.CRITICAL


def test_calculate_severity_high():
    """HIGH 심각도 계산 (Level 2)."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "2a", "improved", "2", "5", 0.001, True)
        ],
        papers_worsened=[
            PaperEvidence("p2", "T2", "2b", "worsened", "4", "3", 0.02, True)
        ],
    )

    detector = ConflictDetector(MagicMock())
    severity = detector._calculate_severity(conflict)

    assert severity == ConflictSeverity.HIGH


def test_calculate_severity_medium():
    """MEDIUM 심각도 계산 (Level 3)."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "3", "improved", "2", "5", 0.05, False)
        ],
        papers_worsened=[
            PaperEvidence("p2", "T2", "3", "worsened", "4", "3", 0.04, True)
        ],
    )

    detector = ConflictDetector(MagicMock())
    severity = detector._calculate_severity(conflict)

    assert severity == ConflictSeverity.MEDIUM


def test_calculate_severity_low():
    """LOW 심각도 계산 (Level 4+)."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "4", "improved", "2", "5", None, False)
        ],
        papers_worsened=[
            PaperEvidence("p2", "T2", "5", "worsened", "4", "3", None, False)
        ],
    )

    detector = ConflictDetector(MagicMock())
    severity = detector._calculate_severity(conflict)

    assert severity == ConflictSeverity.LOW


# ============================================================================
# Test: Confidence Calculation
# ============================================================================

def test_calculate_confidence_high_quality():
    """높은 품질 충돌의 신뢰도."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "1b", "improved", "2", "5", 0.001, True),
            PaperEvidence("p2", "T2", "2a", "improved", "1.9", "4.1", 0.002, True),
        ],
        papers_worsened=[
            PaperEvidence("p3", "T3", "2b", "worsened", "4.5", "3.8", 0.03, True),
        ],
    )

    detector = ConflictDetector(MagicMock())
    confidence = detector._calculate_confidence(conflict)

    # 논문 3편, 높은 evidence level, 모두 significant, 균형
    assert confidence > 0.5  # 비교적 높은 신뢰도


def test_calculate_confidence_low_quality():
    """낮은 품질 충돌의 신뢰도."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "4", "improved", "X", "Y", None, False),
        ],
        papers_worsened=[
            PaperEvidence("p2", "T2", "5", "worsened", "X", "Y", None, False),
        ],
    )

    detector = ConflictDetector(MagicMock())
    confidence = detector._calculate_confidence(conflict)

    # 논문 2편, 낮은 evidence level, significant 없음
    assert confidence < 0.5  # 낮은 신뢰도


# ============================================================================
# Test: Summary Generation
# ============================================================================

def test_generate_summary():
    """요약 생성."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("paper_001", "TLIF improves VAS", "1b", "improved",
                         "2.1", "5.3", 0.001, True),
        ],
        papers_worsened=[
            PaperEvidence("paper_002", "TLIF worsens VAS", "2b", "worsened",
                         "4.5", "3.8", 0.03, True),
        ],
        severity=ConflictSeverity.CRITICAL,
        confidence=0.75,
    )

    detector = ConflictDetector(MagicMock())
    summary = detector._generate_summary(conflict)

    # 기본 정보 포함 확인
    assert "TLIF → VAS" in summary
    assert "CRITICAL" in summary
    assert "75%" in summary

    # 논문 정보 포함 확인
    assert "paper_001" in summary
    assert "paper_002" in summary
    assert "IMPROVEMENT" in summary
    assert "WORSENING" in summary

    # 해석 가이드 포함 확인
    assert "Interpretation:" in summary
    assert "high-quality evidence" in summary.lower()


# ============================================================================
# Test: ConflictResult Properties
# ============================================================================

def test_conflict_result_properties():
    """ConflictResult 속성 테스트."""
    conflict = ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        papers_improved=[
            PaperEvidence("p1", "T1", "1b", "improved", "2", "5", 0.001, True),
            PaperEvidence("p2", "T2", "2a", "improved", "1.9", "4.1", 0.002, True),
        ],
        papers_worsened=[
            PaperEvidence("p3", "T3", "2b", "worsened", "4.5", "3.8", 0.03, True),
        ],
        papers_unchanged=[
            PaperEvidence("p4", "T4", "3", "unchanged", "3.2", "3.1", 0.5, False),
        ],
    )

    assert conflict.total_papers == 4
    assert conflict.has_significant_conflict is True
    assert conflict.conflict_ratio == pytest.approx(0.25, abs=0.01)  # min(2,1) / 4
    assert conflict.get_highest_evidence_level() == "1b"


def test_conflict_result_no_conflict():
    """충돌 없는 경우."""
    conflict = ConflictResult(
        intervention="UBE",
        outcome="ODI",
        papers_improved=[
            PaperEvidence("p1", "T1", "1b", "improved", "65%", "45%", 0.001, True),
            PaperEvidence("p2", "T2", "2b", "improved", "58%", "40%", 0.01, True),
        ],
    )

    assert conflict.has_significant_conflict is False
    assert conflict.conflict_ratio == 0.0


# ============================================================================
# Test: Evidence Level Scores
# ============================================================================

def test_evidence_level_scores():
    """Evidence level 점수 매핑."""
    assert EVIDENCE_LEVEL_SCORES["1a"] == 10
    assert EVIDENCE_LEVEL_SCORES["1b"] == 9
    assert EVIDENCE_LEVEL_SCORES["2a"] == 8
    assert EVIDENCE_LEVEL_SCORES["2b"] == 7
    assert EVIDENCE_LEVEL_SCORES["3"] == 5
    assert EVIDENCE_LEVEL_SCORES["4"] == 3
    assert EVIDENCE_LEVEL_SCORES["5"] == 1


def test_paper_evidence_score():
    """PaperEvidence evidence_score 속성."""
    paper_1a = PaperEvidence("p1", "T1", "1a", "improved", "X", "Y", 0.01, True)
    paper_5 = PaperEvidence("p2", "T2", "5", "worsened", "X", "Y", None, False)

    assert paper_1a.evidence_score == 10
    assert paper_5.evidence_score == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
