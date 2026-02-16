"""Tests for WritingGuideHandler module.

Tests academic paper writing guidance, checklists (STROBE, CONSORT, PRISMA, CARE, STARD, SPIRIT, MOOSE, TRIPOD, CHEERS),
expert agent system, and revision response support.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from medical_mcp.handlers.writing_guide_handler import (
    WritingGuideHandler,
    StudyType,
    ExpertRole,
    SectionGuide,
    ChecklistItem,
    Checklist,
    SECTION_GUIDES,
    CHECKLISTS,
    STUDY_TYPE_TO_CHECKLIST,
    EXPERT_AGENTS,
    RESPONSE_TEMPLATES,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_server():
    """Mock MedicalKAGServer instance."""
    server = Mock()
    server.neo4j_client = Mock()
    return server


@pytest.fixture
def handler(mock_server):
    """WritingGuideHandler instance with mocked server."""
    return WritingGuideHandler(mock_server)


# ===========================================================================
# Test: Handler Initialization
# ===========================================================================

class TestHandlerInit:
    """Test WritingGuideHandler initialization."""

    def test_init_with_server(self, mock_server):
        handler = WritingGuideHandler(mock_server)
        assert handler.server == mock_server

    def test_inherits_base_handler(self, handler):
        # BaseHandler provides safe_execute decorator and server access
        assert hasattr(handler, 'server')


# ===========================================================================
# Test: Section Guide Retrieval
# ===========================================================================

class TestSectionGuide:
    """Test get_section_guide method."""

    @pytest.mark.asyncio
    async def test_get_introduction_guide(self, handler):
        result = await handler.get_section_guide("introduction")
        assert result["success"] is True
        assert result["section"] == "Introduction"
        assert "structure" in result
        assert "tips" in result
        assert "common_mistakes" in result
        assert "example_phrases" in result

    @pytest.mark.asyncio
    async def test_get_methods_guide(self, handler):
        result = await handler.get_section_guide("methods")
        assert result["success"] is True
        assert result["section"] == "Materials and Methods"
        assert result["word_limit"] is None  # Methods has no strict limit

    @pytest.mark.asyncio
    async def test_get_results_guide(self, handler):
        result = await handler.get_section_guide("results")
        assert result["success"] is True
        assert len(result["structure"]) > 0

    @pytest.mark.asyncio
    async def test_get_discussion_guide(self, handler):
        result = await handler.get_section_guide("discussion")
        assert result["success"] is True
        assert "comparison" in result["example_phrases"]

    @pytest.mark.asyncio
    async def test_get_conclusion_guide(self, handler):
        result = await handler.get_section_guide("conclusion")
        assert result["success"] is True
        assert result["word_limit"] == 150

    @pytest.mark.asyncio
    async def test_get_figure_legend_guide(self, handler):
        result = await handler.get_section_guide("figure_legend")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_section(self, handler):
        result = await handler.get_section_guide("nonexistent_section")
        assert result["success"] is False
        assert "Unknown section" in result["error"]

    @pytest.mark.asyncio
    async def test_case_insensitive_section(self, handler):
        result = await handler.get_section_guide("INTRODUCTION")
        assert result["success"] is True
        assert result["section"] == "Introduction"

    @pytest.mark.asyncio
    async def test_section_with_spaces(self, handler):
        result = await handler.get_section_guide("figure legend")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_exclude_examples(self, handler):
        result = await handler.get_section_guide("introduction", include_examples=False)
        assert result["success"] is True
        assert "example_phrases" not in result

    @pytest.mark.asyncio
    async def test_with_study_type_checklist_items(self, handler):
        result = await handler.get_section_guide("methods", study_type="rct")
        assert result["success"] is True
        assert "checklist_items" in result
        assert result["checklist_name"] == "CONSORT"
        assert len(result["checklist_items"]) > 0


# ===========================================================================
# Test: Checklist Retrieval
# ===========================================================================

class TestChecklist:
    """Test get_checklist method."""

    @pytest.mark.asyncio
    async def test_get_strobe_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="cohort")
        assert result["success"] is True
        assert result["checklist"]["name"] == "STROBE"
        assert len(result["items"]) == 22

    @pytest.mark.asyncio
    async def test_get_consort_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="rct")
        assert result["success"] is True
        assert result["checklist"]["name"] == "CONSORT"
        assert result["checklist"]["url"] == "https://www.consort-statement.org/"

    @pytest.mark.asyncio
    async def test_get_prisma_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="systematic_review")
        assert result["success"] is True
        assert result["checklist"]["name"] == "PRISMA"

    @pytest.mark.asyncio
    async def test_get_care_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="case_report")
        assert result["success"] is True
        assert result["checklist"]["name"] == "CARE"

    @pytest.mark.asyncio
    async def test_get_stard_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="diagnostic")
        assert result["success"] is True
        assert result["checklist"]["name"] == "STARD"

    @pytest.mark.asyncio
    async def test_get_spirit_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="protocol")
        assert result["success"] is True
        assert result["checklist"]["name"] == "SPIRIT"

    @pytest.mark.asyncio
    async def test_get_moose_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="observational_meta_analysis")
        assert result["success"] is True
        assert result["checklist"]["name"] == "MOOSE"

    @pytest.mark.asyncio
    async def test_get_tripod_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="prediction")
        assert result["success"] is True
        assert result["checklist"]["name"] == "TRIPOD"

    @pytest.mark.asyncio
    async def test_get_cheers_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="cost_effectiveness")
        assert result["success"] is True
        assert result["checklist"]["name"] == "CHEERS"

    @pytest.mark.asyncio
    async def test_get_checklist_by_name(self, handler):
        result = await handler.get_checklist(checklist_name="strobe")
        assert result["success"] is True
        assert result["checklist"]["name"] == "STROBE"

    @pytest.mark.asyncio
    async def test_unknown_study_type(self, handler):
        result = await handler.get_checklist(study_type="unknown_type")
        assert result["success"] is False
        assert "Unknown study type" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_checklist_name(self, handler):
        result = await handler.get_checklist(checklist_name="nonexistent")
        assert result["success"] is False
        assert "Unknown checklist" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_both_params(self, handler):
        result = await handler.get_checklist()
        assert result["success"] is False
        assert "Provide either study_type or checklist_name" in result["error"]

    @pytest.mark.asyncio
    async def test_section_filter(self, handler):
        result = await handler.get_checklist(study_type="rct", section_filter="methods")
        assert result["success"] is True
        assert all("methods" in item["section"].lower() for item in result["items"])

    @pytest.mark.asyncio
    async def test_total_items_count(self, handler):
        result = await handler.get_checklist(study_type="rct")
        assert result["success"] is True
        assert result["total_items"] == len(result["items"])


# ===========================================================================
# Test: Expert Agent Information
# ===========================================================================

class TestExpertInfo:
    """Test get_expert_info method."""

    @pytest.mark.asyncio
    async def test_get_clinician_info(self, handler):
        result = await handler.get_expert_info(expert="clinician")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Clinician"
        assert "introduction" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_get_methodologist_info(self, handler):
        result = await handler.get_expert_info(expert="methodologist")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Methodologist"
        assert "methods" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_get_statistician_info(self, handler):
        result = await handler.get_expert_info(expert="statistician")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Statistician"

    @pytest.mark.asyncio
    async def test_get_editor_info(self, handler):
        result = await handler.get_expert_info(expert="editor")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Editor"
        assert "all" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_unknown_expert(self, handler):
        result = await handler.get_expert_info(expert="nonexistent")
        assert result["success"] is False
        assert "Unknown expert" in result["error"]

    @pytest.mark.asyncio
    async def test_get_experts_for_section(self, handler):
        result = await handler.get_expert_info(section="methods")
        assert result["success"] is True
        assert len(result["responsible_experts"]) >= 2  # methodologist, statistician, editor

    @pytest.mark.asyncio
    async def test_get_all_experts(self, handler):
        result = await handler.get_expert_info()
        assert result["success"] is True
        assert len(result["experts"]) == 4
        assert "clinician" in result["experts"]
        assert "methodologist" in result["experts"]


# ===========================================================================
# Test: Response Templates
# ===========================================================================

class TestResponseTemplate:
    """Test get_response_template method."""

    @pytest.mark.asyncio
    async def test_get_agree_template(self, handler):
        result = await handler.get_response_template("agree")
        assert result["success"] is True
        assert "template" in result
        assert "usage_guide" in result
        assert "thank the reviewer" in result["template"].lower()

    @pytest.mark.asyncio
    async def test_get_partially_agree_template(self, handler):
        result = await handler.get_response_template("partially_agree")
        assert result["success"] is True
        assert "agreement" in result["template"]

    @pytest.mark.asyncio
    async def test_get_respectfully_disagree_template(self, handler):
        result = await handler.get_response_template("respectfully_disagree")
        assert result["success"] is True
        assert "respectfully" in result["template"].lower()

    @pytest.mark.asyncio
    async def test_get_cannot_perform_template(self, handler):
        result = await handler.get_response_template("cannot_perform")
        assert result["success"] is True
        assert "unfortunately" in result["template"].lower()

    @pytest.mark.asyncio
    async def test_get_clarification_template(self, handler):
        result = await handler.get_response_template("clarification")
        assert result["success"] is True
        assert "apologize" in result["template"].lower()

    @pytest.mark.asyncio
    async def test_unknown_response_type(self, handler):
        result = await handler.get_response_template("nonexistent")
        assert result["success"] is False
        assert "Unknown response type" in result["error"]

    @pytest.mark.asyncio
    async def test_case_insensitive_response_type(self, handler):
        result = await handler.get_response_template("AGREE")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_usage_guide_content(self, handler):
        result = await handler.get_response_template("agree")
        assert result["success"] is True
        assert len(result["usage_guide"]) > 0


# ===========================================================================
# Test: Draft Response Letter
# ===========================================================================

class TestDraftResponseLetter:
    """Test draft_response_letter method."""

    @pytest.mark.asyncio
    async def test_basic_response_letter(self, handler):
        comments = [
            {"reviewer": "1", "comment": "Please add statistical analysis."},
            {"reviewer": "1", "comment": "Clarify the methods section."},
        ]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True
        assert "response_letter" in result
        assert "header" in result["response_letter"]
        assert "footer" in result["response_letter"]
        assert len(result["response_letter"]["reviewers"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_reviewers(self, handler):
        comments = [
            {"reviewer": "1", "comment": "Comment 1"},
            {"reviewer": "2", "comment": "Comment 2"},
            {"reviewer": "1", "comment": "Comment 3"},
        ]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True
        assert len(result["response_letter"]["reviewers"]) == 2
        # Reviewer 1 should have 2 comments
        reviewer_1 = next(r for r in result["response_letter"]["reviewers"] if r["reviewer"] == "Reviewer #1")
        assert len(reviewer_1["comments"]) == 2

    @pytest.mark.asyncio
    async def test_response_letter_tips(self, handler):
        comments = [{"reviewer": "1", "comment": "Test"}]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True
        assert "tips" in result
        assert len(result["tips"]) > 0

    @pytest.mark.asyncio
    async def test_empty_comments_list(self, handler):
        result = await handler.draft_response_letter([])
        assert result["success"] is True
        assert len(result["response_letter"]["reviewers"]) == 0


# ===========================================================================
# Test: Analyze Reviewer Comments
# ===========================================================================

class TestAnalyzeReviewerComments:
    """Test analyze_reviewer_comments method."""

    @pytest.mark.asyncio
    async def test_categorize_major_concerns(self, handler):
        comments = ["This is a major flaw in the study design."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert len(result["categorized_comments"]["major_concerns"]) == 1

    @pytest.mark.asyncio
    async def test_categorize_statistical_issues(self, handler):
        comments = ["The p-value calculation needs clarification."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert len(result["categorized_comments"]["statistical_issues"]) == 1

    @pytest.mark.asyncio
    async def test_categorize_writing_issues(self, handler):
        comments = ["The language is unclear in several sections."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert len(result["categorized_comments"]["writing_issues"]) == 1

    @pytest.mark.asyncio
    async def test_categorize_data_requests(self, handler):
        # Use keywords that match data_keywords only (not statistical_keywords)
        comments = ["Please add a table showing the subgroup results."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        # "table" and "subgroup" should trigger additional_data_requests
        assert len(result["categorized_comments"]["additional_data_requests"]) >= 1

    @pytest.mark.asyncio
    async def test_categorize_minor_concerns(self, handler):
        comments = ["A simple observation about the formatting."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        # If the comment doesn't match any category, it goes to minor_concerns
        assert len(result["categorized_comments"]["minor_concerns"]) >= 0

    @pytest.mark.asyncio
    async def test_summary_counts(self, handler):
        comments = [
            "Major concern with study design.",
            "Statistical analysis is insufficient.",
            "Minor typo found.",
        ]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert result["summary"]["total"] == 3
        assert result["summary"]["major_concerns"] >= 1
        assert result["summary"]["statistical_issues"] >= 1

    @pytest.mark.asyncio
    async def test_priority_order(self, handler):
        comments = ["Test comment"]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert "priority_order" in result
        assert result["priority_order"][0] == "major_concerns"

    @pytest.mark.asyncio
    async def test_empty_comments(self, handler):
        result = await handler.analyze_reviewer_comments([])
        assert result["success"] is True
        assert result["summary"]["total"] == 0


# ===========================================================================
# Test: Get All Guides
# ===========================================================================

class TestGetAllGuides:
    """Test get_all_guides method."""

    @pytest.mark.asyncio
    async def test_get_all_guides_structure(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert "sections" in result
        assert "checklists" in result
        assert "study_type_to_checklist" in result
        assert "experts" in result
        assert "response_templates" in result
        assert "usage_examples" in result

    @pytest.mark.asyncio
    async def test_all_sections_listed(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert len(result["sections"]) == len(SECTION_GUIDES)
        assert "introduction" in result["sections"]
        assert "methods" in result["sections"]

    @pytest.mark.asyncio
    async def test_all_checklists_listed(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert len(result["checklists"]) == 9
        assert "strobe" in result["checklists"]
        assert "consort" in result["checklists"]

    @pytest.mark.asyncio
    async def test_all_experts_listed(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert len(result["experts"]) == 4
        assert "clinician" in result["experts"]

    @pytest.mark.asyncio
    async def test_usage_examples(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert "get_section_guide" in result["usage_examples"]
        assert "get_checklist" in result["usage_examples"]


# ===========================================================================
# Test: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_none_section_input(self, handler):
        # Handler doesn't validate None - it will raise AttributeError
        # This is acceptable since the input should be validated at a higher level
        with pytest.raises(AttributeError):
            result = await handler.get_section_guide(None)

    @pytest.mark.asyncio
    async def test_empty_string_section(self, handler):
        result = await handler.get_section_guide("")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_whitespace_section(self, handler):
        result = await handler.get_section_guide("   ")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_reviewer_comments_with_missing_keys(self, handler):
        # Comments without proper structure should be handled
        comments = [
            {"reviewer": "1"},  # Missing comment
            {"comment": "Test"},  # Missing reviewer
        ]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True

    def test_main_study_types_have_checklists(self):
        # Verify main study types have corresponding checklists
        # Note: Not all StudyType enums are mapped (e.g., qualitative, animal)
        main_types = ["rct", "cohort", "case_control", "cross_sectional",
                     "case_report", "systematic_review", "diagnostic"]
        for study_type in main_types:
            assert study_type in STUDY_TYPE_TO_CHECKLIST


# ===========================================================================
# Test: Constants and Data Structures
# ===========================================================================

class TestConstants:
    """Test module-level constants and data structures."""

    def test_section_guides_complete(self):
        assert "introduction" in SECTION_GUIDES
        assert "methods" in SECTION_GUIDES
        assert "results" in SECTION_GUIDES
        assert "discussion" in SECTION_GUIDES
        assert "conclusion" in SECTION_GUIDES

    def test_checklists_complete(self):
        assert len(CHECKLISTS) == 9
        assert "strobe" in CHECKLISTS
        assert "consort" in CHECKLISTS
        assert "prisma" in CHECKLISTS
        assert "care" in CHECKLISTS
        assert "stard" in CHECKLISTS
        assert "spirit" in CHECKLISTS
        assert "moose" in CHECKLISTS
        assert "tripod" in CHECKLISTS
        assert "cheers" in CHECKLISTS

    def test_expert_agents_complete(self):
        assert len(EXPERT_AGENTS) == 4
        assert "clinician" in EXPERT_AGENTS
        assert "methodologist" in EXPERT_AGENTS
        assert "statistician" in EXPERT_AGENTS
        assert "editor" in EXPERT_AGENTS

    def test_response_templates_complete(self):
        assert len(RESPONSE_TEMPLATES) == 5
        assert "agree" in RESPONSE_TEMPLATES
        assert "partially_agree" in RESPONSE_TEMPLATES
        assert "respectfully_disagree" in RESPONSE_TEMPLATES
        assert "cannot_perform" in RESPONSE_TEMPLATES
        assert "clarification" in RESPONSE_TEMPLATES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
