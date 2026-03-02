"""Comprehensive tests for WritingGuideHandler module.

Tests academic paper writing guidance, checklists (STROBE, CONSORT, PRISMA, CARE,
STARD, SPIRIT, MOOSE, TRIPOD, CHEERS), expert agent system, revision response
templates, reviewer comment analysis, and draft response letter.
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
    get_strobe_checklist,
    get_consort_checklist,
    get_prisma_checklist,
    get_care_checklist,
    get_stard_checklist,
    get_spirit_checklist,
    get_moose_checklist,
    get_tripod_checklist,
    get_cheers_checklist,
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
        assert hasattr(handler, 'server')
        assert hasattr(handler, 'neo4j_client')


# ===========================================================================
# Test: Enum Definitions
# ===========================================================================

class TestEnums:
    """Test enum definitions."""

    def test_study_type_values(self):
        assert StudyType.RCT.value == "rct"
        assert StudyType.COHORT.value == "cohort"
        assert StudyType.CASE_CONTROL.value == "case_control"
        assert StudyType.SYSTEMATIC_REVIEW.value == "systematic_review"
        assert StudyType.META_ANALYSIS.value == "meta_analysis"
        assert StudyType.DIAGNOSTIC.value == "diagnostic"
        assert StudyType.PROGNOSTIC.value == "prognostic"
        assert StudyType.QUALITATIVE.value == "qualitative"
        assert StudyType.ANIMAL.value == "animal"

    def test_expert_role_values(self):
        assert ExpertRole.CLINICIAN.value == "clinician"
        assert ExpertRole.METHODOLOGIST.value == "methodologist"
        assert ExpertRole.STATISTICIAN.value == "statistician"
        assert ExpertRole.EDITOR.value == "editor"


# ===========================================================================
# Test: Dataclass Definitions
# ===========================================================================

class TestDataclasses:
    """Test dataclass construction."""

    def test_section_guide(self):
        guide = SectionGuide(
            section="Test",
            description="Test desc",
            structure=["Step 1"],
            word_limit=500,
            tips=["Tip 1"],
            common_mistakes=["Mistake 1"],
            example_phrases={"intro": ["phrase"]},
        )
        assert guide.section == "Test"
        assert guide.word_limit == 500

    def test_checklist_item(self):
        item = ChecklistItem(
            number="1",
            item="Title",
            description="Test description",
            section="title",
        )
        assert item.number == "1"
        assert item.section == "title"

    def test_checklist(self):
        cl = Checklist(
            name="TEST",
            full_name="Test Checklist",
            study_type="Test Study",
            url="https://test.com",
            items=[ChecklistItem("1", "Item", "Desc", "section")],
        )
        assert cl.name == "TEST"
        assert len(cl.items) == 1


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

    @pytest.mark.asyncio
    async def test_get_results_guide(self, handler):
        result = await handler.get_section_guide("results")
        assert result["success"] is True
        assert result["section"] == "Results"

    @pytest.mark.asyncio
    async def test_get_discussion_guide(self, handler):
        result = await handler.get_section_guide("discussion")
        assert result["success"] is True
        assert result["section"] == "Discussion"

    @pytest.mark.asyncio
    async def test_get_conclusion_guide(self, handler):
        result = await handler.get_section_guide("conclusion")
        assert result["success"] is True
        assert result["section"] == "Conclusion"
        assert result["word_limit"] == 150

    @pytest.mark.asyncio
    async def test_get_figure_legend_guide(self, handler):
        result = await handler.get_section_guide("figure_legend")
        assert result["success"] is True
        assert result["section"] == "Figure Legends"

    @pytest.mark.asyncio
    async def test_unknown_section(self, handler):
        result = await handler.get_section_guide("nonexistent_section")
        assert result["success"] is False
        assert "Unknown section" in result["error"]

    @pytest.mark.asyncio
    async def test_section_with_study_type(self, handler):
        result = await handler.get_section_guide("methods", study_type="rct")
        assert result["success"] is True
        # Should include CONSORT checklist items for methods
        if "checklist_items" in result:
            assert result["checklist_name"] == "CONSORT"

    @pytest.mark.asyncio
    async def test_section_without_examples(self, handler):
        result = await handler.get_section_guide("introduction", include_examples=False)
        assert result["success"] is True
        assert "example_phrases" not in result

    @pytest.mark.asyncio
    async def test_section_case_insensitive(self, handler):
        result = await handler.get_section_guide("Introduction")
        assert result["success"] is True
        assert result["section"] == "Introduction"

    @pytest.mark.asyncio
    async def test_section_with_spaces(self, handler):
        """Test section name with spaces (e.g. 'figure legend')."""
        result = await handler.get_section_guide("figure legend")
        assert result["success"] is True


# ===========================================================================
# Test: Checklist Retrieval
# ===========================================================================

class TestChecklistRetrieval:
    """Test get_checklist method."""

    @pytest.mark.asyncio
    async def test_get_strobe_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="cohort")
        assert result["success"] is True
        assert result["checklist"]["name"] == "STROBE"
        assert result["total_items"] > 0

    @pytest.mark.asyncio
    async def test_get_consort_by_study_type(self, handler):
        result = await handler.get_checklist(study_type="rct")
        assert result["success"] is True
        assert result["checklist"]["name"] == "CONSORT"

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
        result = await handler.get_checklist(study_type="prognostic")
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
    async def test_get_checklist_with_section_filter(self, handler):
        result = await handler.get_checklist(checklist_name="consort", section_filter="methods")
        assert result["success"] is True
        for item in result["items"]:
            assert "methods" in item["section"].lower()

    @pytest.mark.asyncio
    async def test_unknown_study_type(self, handler):
        result = await handler.get_checklist(study_type="unknown_type")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_unknown_checklist_name(self, handler):
        result = await handler.get_checklist(checklist_name="unknown")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_no_study_type_or_name(self, handler):
        result = await handler.get_checklist()
        assert result["success"] is False
        assert "available_study_types" in result
        assert "available_checklists" in result


# ===========================================================================
# Test: Checklist Functions
# ===========================================================================

class TestChecklistFunctions:
    """Test individual checklist generator functions."""

    def test_strobe_checklist(self):
        cl = get_strobe_checklist()
        assert cl.name == "STROBE"
        assert len(cl.items) == 22
        assert cl.url.startswith("https://")

    def test_consort_checklist(self):
        cl = get_consort_checklist()
        assert cl.name == "CONSORT"
        assert len(cl.items) > 20

    def test_prisma_checklist(self):
        cl = get_prisma_checklist()
        assert cl.name == "PRISMA"
        assert len(cl.items) == 27

    def test_care_checklist(self):
        cl = get_care_checklist()
        assert cl.name == "CARE"
        assert len(cl.items) > 10

    def test_stard_checklist(self):
        cl = get_stard_checklist()
        assert cl.name == "STARD"
        assert len(cl.items) > 20

    def test_spirit_checklist(self):
        cl = get_spirit_checklist()
        assert cl.name == "SPIRIT"
        assert len(cl.items) > 20

    def test_moose_checklist(self):
        cl = get_moose_checklist()
        assert cl.name == "MOOSE"
        assert len(cl.items) > 20

    def test_tripod_checklist(self):
        cl = get_tripod_checklist()
        assert cl.name == "TRIPOD"
        assert len(cl.items) > 20

    def test_cheers_checklist(self):
        cl = get_cheers_checklist()
        assert cl.name == "CHEERS"
        assert len(cl.items) > 20


# ===========================================================================
# Test: Expert Agent System
# ===========================================================================

class TestExpertAgent:
    """Test get_expert_info method."""

    @pytest.mark.asyncio
    async def test_get_clinician(self, handler):
        result = await handler.get_expert_info(expert="clinician")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Clinician"
        assert "introduction" in result["expert"]["sections"]
        assert "discussion" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_get_methodologist(self, handler):
        result = await handler.get_expert_info(expert="methodologist")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Methodologist"
        assert "methods" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_get_statistician(self, handler):
        result = await handler.get_expert_info(expert="statistician")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Statistician"

    @pytest.mark.asyncio
    async def test_get_editor(self, handler):
        result = await handler.get_expert_info(expert="editor")
        assert result["success"] is True
        assert result["expert"]["name"] == "Dr. Editor"
        assert "all" in result["expert"]["sections"]

    @pytest.mark.asyncio
    async def test_unknown_expert(self, handler):
        result = await handler.get_expert_info(expert="unknown")
        assert result["success"] is False
        assert "Unknown expert" in result["error"]

    @pytest.mark.asyncio
    async def test_experts_by_section(self, handler):
        result = await handler.get_expert_info(section="methods")
        assert result["success"] is True
        assert len(result["responsible_experts"]) >= 1
        # Methodologist and Statistician should be responsible for methods
        expert_ids = [e["id"] for e in result["responsible_experts"]]
        assert "methodologist" in expert_ids

    @pytest.mark.asyncio
    async def test_experts_for_discussion(self, handler):
        """Discussion section should include clinician and editor."""
        result = await handler.get_expert_info(section="discussion")
        assert result["success"] is True
        expert_ids = [e["id"] for e in result["responsible_experts"]]
        assert "clinician" in expert_ids
        assert "editor" in expert_ids  # Editor handles "all" sections

    @pytest.mark.asyncio
    async def test_get_all_experts(self, handler):
        result = await handler.get_expert_info()
        assert result["success"] is True
        assert "experts" in result
        assert len(result["experts"]) == 4


# ===========================================================================
# Test: Response Templates
# ===========================================================================

class TestResponseTemplate:
    """Test get_response_template method."""

    @pytest.mark.asyncio
    async def test_agree_template(self, handler):
        result = await handler.get_response_template("agree")
        assert result["success"] is True
        assert "{changes}" in result["template"]
        assert result["usage_guide"] != ""

    @pytest.mark.asyncio
    async def test_partially_agree_template(self, handler):
        result = await handler.get_response_template("partially_agree")
        assert result["success"] is True
        assert "{agreement}" in result["template"]

    @pytest.mark.asyncio
    async def test_respectfully_disagree_template(self, handler):
        result = await handler.get_response_template("respectfully_disagree")
        assert result["success"] is True
        assert "{justification}" in result["template"]

    @pytest.mark.asyncio
    async def test_cannot_perform_template(self, handler):
        result = await handler.get_response_template("cannot_perform")
        assert result["success"] is True
        assert "{reason}" in result["template"]

    @pytest.mark.asyncio
    async def test_clarification_template(self, handler):
        result = await handler.get_response_template("clarification")
        assert result["success"] is True
        assert "{clarification}" in result["template"]

    @pytest.mark.asyncio
    async def test_unknown_response_type(self, handler):
        result = await handler.get_response_template("unknown_type")
        assert result["success"] is False
        assert "available_types" in result

    @pytest.mark.asyncio
    async def test_response_type_with_spaces(self, handler):
        """Test response type with spaces."""
        result = await handler.get_response_template("partially agree")
        assert result["success"] is True


# ===========================================================================
# Test: Draft Response Letter
# ===========================================================================

class TestDraftResponseLetter:
    """Test draft_response_letter method."""

    @pytest.mark.asyncio
    async def test_single_reviewer(self, handler):
        comments = [
            {"reviewer": "1", "comment": "Please clarify the methods section."},
            {"reviewer": "1", "comment": "Add more references to the introduction."},
        ]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True
        assert "response_letter" in result
        assert len(result["response_letter"]["reviewers"]) == 1
        assert len(result["response_letter"]["reviewers"][0]["comments"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_reviewers(self, handler):
        comments = [
            {"reviewer": "1", "comment": "Comment from reviewer 1"},
            {"reviewer": "2", "comment": "Comment from reviewer 2"},
            {"reviewer": "2", "comment": "Another comment from reviewer 2"},
        ]
        result = await handler.draft_response_letter(comments)
        assert result["success"] is True
        assert len(result["response_letter"]["reviewers"]) == 2

    @pytest.mark.asyncio
    async def test_empty_comments(self, handler):
        result = await handler.draft_response_letter([])
        assert result["success"] is True
        assert len(result["response_letter"]["reviewers"]) == 0

    @pytest.mark.asyncio
    async def test_response_letter_structure(self, handler):
        comments = [{"reviewer": "1", "comment": "Test"}]
        result = await handler.draft_response_letter(comments)
        letter = result["response_letter"]
        assert "header" in letter
        assert "footer" in letter
        assert "Dear Editor" in letter["header"]
        assert "tips" in result

    @pytest.mark.asyncio
    async def test_comment_numbering(self, handler):
        comments = [
            {"reviewer": "1", "comment": "First"},
            {"reviewer": "1", "comment": "Second"},
            {"reviewer": "1", "comment": "Third"},
        ]
        result = await handler.draft_response_letter(comments)
        reviewer_comments = result["response_letter"]["reviewers"][0]["comments"]
        assert reviewer_comments[0]["number"] == 1
        assert reviewer_comments[1]["number"] == 2
        assert reviewer_comments[2]["number"] == 3


# ===========================================================================
# Test: Analyze Reviewer Comments
# ===========================================================================

class TestAnalyzeReviewerComments:
    """Test analyze_reviewer_comments method."""

    @pytest.mark.asyncio
    async def test_major_concern_detection(self, handler):
        comments = ["This is a major concern about the study design."]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["success"] is True
        assert len(result["categorized_comments"]["major_concerns"]) == 1

    @pytest.mark.asyncio
    async def test_statistical_issue_detection(self, handler):
        comments = ["The statistical analysis is incorrect, p-value should be recalculated."]
        result = await handler.analyze_reviewer_comments(comments)
        assert len(result["categorized_comments"]["statistical_issues"]) == 1

    @pytest.mark.asyncio
    async def test_writing_issue_detection(self, handler):
        comments = ["The writing is unclear in several places and has grammar issues."]
        result = await handler.analyze_reviewer_comments(comments)
        assert len(result["categorized_comments"]["writing_issues"]) == 1

    @pytest.mark.asyncio
    async def test_data_request_detection(self, handler):
        # Use keywords from data_keywords that are NOT in statistical_keywords
        # "additional" and "figure" are in data_keywords but not statistical_keywords
        comments = ["Please add an additional figure showing the outcomes."]
        result = await handler.analyze_reviewer_comments(comments)
        assert len(result["categorized_comments"]["additional_data_requests"]) == 1

    @pytest.mark.asyncio
    async def test_minor_concern_default(self, handler):
        comments = ["The follow-up period could be longer."]
        result = await handler.analyze_reviewer_comments(comments)
        assert len(result["categorized_comments"]["minor_concerns"]) == 1

    @pytest.mark.asyncio
    async def test_mixed_comments(self, handler):
        comments = [
            "This is a major flaw in the methodology.",
            "The statistical test used is inappropriate.",
            "Please add a table with demographics.",
            "Grammar error in paragraph 3.",
            "Nice work overall.",
        ]
        result = await handler.analyze_reviewer_comments(comments)
        assert result["summary"]["total"] == 5
        assert result["summary"]["major_concerns"] >= 1
        assert result["summary"]["statistical_issues"] >= 1

    @pytest.mark.asyncio
    async def test_empty_comments(self, handler):
        result = await handler.analyze_reviewer_comments([])
        assert result["success"] is True
        assert result["summary"]["total"] == 0

    @pytest.mark.asyncio
    async def test_priority_order(self, handler):
        result = await handler.analyze_reviewer_comments(["test"])
        assert result["priority_order"][0] == "major_concerns"
        assert result["priority_order"][-1] == "writing_issues"


# ===========================================================================
# Test: Get All Guides
# ===========================================================================

class TestGetAllGuides:
    """Test get_all_guides method."""

    @pytest.mark.asyncio
    async def test_returns_all_sections(self, handler):
        result = await handler.get_all_guides()
        assert result["success"] is True
        assert "sections" in result
        assert "introduction" in result["sections"]
        assert "methods" in result["sections"]

    @pytest.mark.asyncio
    async def test_returns_all_checklists(self, handler):
        result = await handler.get_all_guides()
        assert "checklists" in result
        assert "strobe" in result["checklists"]
        assert "consort" in result["checklists"]
        assert "prisma" in result["checklists"]
        assert "care" in result["checklists"]
        assert "stard" in result["checklists"]
        assert "spirit" in result["checklists"]
        assert "moose" in result["checklists"]
        assert "tripod" in result["checklists"]
        assert "cheers" in result["checklists"]

    @pytest.mark.asyncio
    async def test_checklist_info_contains_counts(self, handler):
        result = await handler.get_all_guides()
        for name, info in result["checklists"].items():
            assert "full_name" in info
            assert "study_type" in info
            assert "item_count" in info
            assert info["item_count"] > 0

    @pytest.mark.asyncio
    async def test_returns_all_experts(self, handler):
        result = await handler.get_all_guides()
        assert "experts" in result
        assert len(result["experts"]) == 4

    @pytest.mark.asyncio
    async def test_returns_response_templates(self, handler):
        result = await handler.get_all_guides()
        assert "response_templates" in result
        assert "agree" in result["response_templates"]

    @pytest.mark.asyncio
    async def test_returns_usage_examples(self, handler):
        result = await handler.get_all_guides()
        assert "usage_examples" in result


# ===========================================================================
# Test: Module-level Data Integrity
# ===========================================================================

class TestDataIntegrity:
    """Test module-level data structures are correct."""

    def test_section_guides_keys(self):
        expected = {"introduction", "methods", "results", "discussion", "conclusion", "figure_legend"}
        assert expected == set(SECTION_GUIDES.keys())

    def test_checklists_keys(self):
        expected = {"strobe", "consort", "prisma", "care", "stard", "spirit", "moose", "tripod", "cheers"}
        assert expected == set(CHECKLISTS.keys())

    def test_study_type_mappings_complete(self):
        """All mapped study types should resolve to valid checklists."""
        for st, cl_name in STUDY_TYPE_TO_CHECKLIST.items():
            assert cl_name in CHECKLISTS, f"Study type '{st}' maps to unknown checklist '{cl_name}'"

    def test_expert_agents_structure(self):
        for key, agent in EXPERT_AGENTS.items():
            assert "name" in agent
            assert "title" in agent
            assert "role" in agent
            assert "responsibilities" in agent
            assert "sections" in agent
            assert "focus" in agent

    def test_response_templates_have_placeholders(self):
        for key, template in RESPONSE_TEMPLATES.items():
            assert "{" in template, f"Template '{key}' has no placeholders"
