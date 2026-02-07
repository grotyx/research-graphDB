"""Medical KAG Server Handlers.

This package contains specialized handler classes for the Medical KAG Server.
Each handler is responsible for a specific domain of functionality.

Handlers:
    DocumentHandler: Document CRUD operations (list, delete, stats, reset)
    ClinicalDataHandler: Patient cohorts, follow-up, cost, quality metrics
    PubMedHandler: PubMed search, bulk import, enrichment
    JSONHandler: JSON file import and processing
    SearchHandler: Hybrid search, graph search, evidence retrieval
    ReasoningHandler: Reasoning, conflict detection, evidence synthesis
    GraphHandler: Intervention hierarchies, paper relations, comparisons
    CitationHandler: Draft with citations, citation suggestions
    PDFHandler: PDF/text ingestion, analysis, storage
    ReferenceHandler: Reference formatting with multiple citation styles
    WritingGuideHandler: Academic writing guides, checklists, expert agents
"""

# Handlers will be imported as they are created
from .document_handler import DocumentHandler
from .reference_handler import ReferenceHandler
from .clinical_data_handler import ClinicalDataHandler
from .pubmed_handler import PubMedHandler
from .json_handler import JSONHandler
from .citation_handler import CitationHandler
from .search_handler import SearchHandler
from .pdf_handler import PDFHandler
from .reasoning_handler import ReasoningHandler
from .graph_handler import GraphHandler
from .writing_guide_handler import WritingGuideHandler

__all__ = [
    "DocumentHandler",
    "ClinicalDataHandler",
    "PubMedHandler",
    "JSONHandler",
    "CitationHandler",
    "SearchHandler",
    "PDFHandler",
    "ReasoningHandler",
    "GraphHandler",
    "ReferenceHandler",
    "WritingGuideHandler",
]
