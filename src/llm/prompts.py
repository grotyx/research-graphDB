"""LLM Prompt Templates.

각 LLM 모듈에서 사용하는 프롬프트 템플릿.
google-genai SDK 요구사항: JSON Schema 타입은 대문자 (STRING, OBJECT, ARRAY 등)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromptTemplate:
    """프롬프트 템플릿."""
    system: str
    user: str
    output_schema: Optional[dict] = None


# =============================================================================
# 섹션 분류 프롬프트
# =============================================================================

SECTION_CLASSIFIER_SYSTEM = """You are a medical research paper section classifier.
Your task is to identify and classify sections in academic medical papers.

Section types to identify:
- abstract: Paper summary (Background, Methods, Results, Conclusions)
- introduction: Background and objectives
- methods: Study design, participants, procedures, statistical analysis
- results: Findings, data, statistical outcomes
- discussion: Interpretation, implications, limitations
- conclusion: Summary of findings and implications
- references: Bibliography
- acknowledgments: Funding, contributions
- tables_figures: Table/figure legends and descriptions
- supplementary: Supplementary materials

Tier classification:
- Tier 1 (Core): abstract, results, conclusion - Most important for information retrieval
- Tier 2 (Detail): introduction, methods, discussion - Supporting information"""

SECTION_CLASSIFIER_USER = """Analyze the following medical paper text and identify all sections with their boundaries.

TEXT:
{text}

For each section found, provide:
1. section_type: One of the defined types
2. start_char: Character position where section starts
3. end_char: Character position where section ends
4. confidence: Your confidence in this classification (0.0-1.0)
5. tier: 1 for core sections, 2 for detail sections

Return a JSON array of section objects."""

SECTION_CLASSIFIER_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "section_type": {
                "type": "STRING",
                "enum": ["abstract", "introduction", "methods", "results",
                        "discussion", "conclusion", "references",
                        "acknowledgments", "tables_figures", "supplementary"]
            },
            "start_char": {"type": "INTEGER"},
            "end_char": {"type": "INTEGER"},
            "confidence": {"type": "NUMBER"},
            "tier": {"type": "INTEGER"}
        },
        "required": ["section_type", "start_char", "end_char", "confidence", "tier"]
    }
}


# =============================================================================
# 의미 청킹 프롬프트
# =============================================================================

SEMANTIC_CHUNKER_SYSTEM = """You are a medical text semantic chunker.
Your task is to divide medical paper sections into meaningful semantic units.

Chunking principles:
1. Each chunk should contain ONE complete thought or finding
2. Preserve logical coherence - don't split mid-sentence or mid-paragraph
3. Keep related information together (e.g., a finding with its statistical evidence)
4. Target chunk size: 300-500 words, but prioritize semantic completeness
5. Mark key findings and statistical results"""

SEMANTIC_CHUNKER_USER = """Divide this {section_type} section into semantic chunks.

SECTION TEXT:
{text}

For each chunk, provide:
1. content: The text content of the chunk
2. topic_summary: A 1-sentence summary of what this chunk is about
3. is_complete_thought: Whether this chunk contains a complete idea
4. contains_finding: Whether this chunk contains a research finding or result
5. start_char: Character position in the original text
6. end_char: Character position in the original text

Return a JSON array of chunk objects."""

SEMANTIC_CHUNKER_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "content": {"type": "STRING"},
            "topic_summary": {"type": "STRING"},
            "is_complete_thought": {"type": "BOOLEAN"},
            "contains_finding": {"type": "BOOLEAN"},
            "start_char": {"type": "INTEGER"},
            "end_char": {"type": "INTEGER"}
        },
        "required": ["content", "topic_summary", "is_complete_thought",
                    "contains_finding", "start_char", "end_char"]
    }
}


# =============================================================================
# 메타데이터 추출 프롬프트
# =============================================================================

METADATA_EXTRACTOR_SYSTEM = """You are a medical research metadata extractor.
Your task is to extract structured metadata from medical paper text chunks.

Extract:
1. Summary: 1-2 sentence summary of the chunk
2. Keywords: Key medical terms for search
3. PICO elements (if present):
   - Population: Who was studied
   - Intervention: What treatment/exposure
   - Comparison: Control group or comparison
   - Outcome: What was measured
4. Statistics (if present):
   - p-values
   - Effect sizes (HR, OR, RR, etc.)
   - Confidence intervals
   - Sample sizes
5. Content type:
   - original: This paper's own findings
   - citation: Cited from another paper
   - background: General background information"""

METADATA_EXTRACTOR_USER = """Extract metadata from this text chunk.

DOCUMENT CONTEXT (Abstract):
{context}

CHUNK TEXT:
{chunk}

Extract all available metadata following the schema."""

METADATA_EXTRACTOR_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "keywords": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "pico": {
            "type": "OBJECT",
            "properties": {
                "population": {"type": "STRING"},
                "intervention": {"type": "STRING"},
                "comparison": {"type": "STRING"},
                "outcome": {"type": "STRING"}
            }
        },
        "statistics": {
            "type": "OBJECT",
            "properties": {
                "p_values": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "effect_sizes": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "type": {"type": "STRING"},
                            "value": {"type": "NUMBER"},
                            "ci_lower": {"type": "NUMBER"},
                            "ci_upper": {"type": "NUMBER"}
                        }
                    }
                },
                "confidence_intervals": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "sample_sizes": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"}
                }
            }
        },
        "content_type": {
            "type": "STRING",
            "enum": ["original", "citation", "background"]
        },
        "is_key_finding": {"type": "BOOLEAN"}
    },
    "required": ["summary", "keywords", "content_type", "is_key_finding"]
}


# =============================================================================
# 인용 추출 프롬프트
# =============================================================================

CITATION_EXTRACTOR_SYSTEM = """You are a citation extractor for medical papers.
Your task is to identify and extract citation information from paper text.

For each citation found, extract:
1. Cited title (if mentioned)
2. Authors (if mentioned)
3. Year
4. Citation context (the sentence containing the citation)
5. Citation type: supporting, contrasting, or neutral"""

CITATION_EXTRACTOR_USER = """Extract all citations from this text.

TEXT:
{text}

Identify citations in formats like:
- (Author et al., 2023)
- Author et al. (2023)
- [1], [1-3], [1,2,3]
- According to Author (2023)

For each citation, provide the extracted information."""

CITATION_EXTRACTOR_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "cited_title": {"type": "STRING"},
            "cited_authors": {
                "type": "ARRAY",
                "items": {"type": "STRING"}
            },
            "cited_year": {"type": "INTEGER"},
            "citation_context": {"type": "STRING"},
            "citation_type": {
                "type": "STRING",
                "enum": ["supporting", "contrasting", "neutral"]
            }
        },
        "required": ["citation_context", "citation_type"]
    }
}


# =============================================================================
# 관계 추론 프롬프트
# =============================================================================

RELATIONSHIP_ANALYZER_SYSTEM = """You are a medical research relationship analyzer.
Your task is to analyze relationships between medical papers.

Relationship types:
1. supports: Paper B's findings support Paper A's conclusions
2. contradicts: Paper B's findings contradict Paper A's conclusions
3. similar_topic: Papers study similar topics but different aspects
4. extends: Paper B extends or builds upon Paper A's work"""

RELATIONSHIP_ANALYZER_USER = """Analyze the relationship between these two papers.

PAPER A:
Title: {title_a}
Abstract: {abstract_a}
Main Findings: {findings_a}
PICO: {pico_a}

PAPER B:
Title: {title_b}
Abstract: {abstract_b}
Main Findings: {findings_b}
PICO: {pico_b}

Determine:
1. The type of relationship between these papers
2. Confidence in this assessment (0.0-1.0)
3. Evidence for this relationship (specific findings that support/contradict)"""

RELATIONSHIP_ANALYZER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "relationship_type": {
            "type": "STRING",
            "enum": ["supports", "contradicts", "similar_topic", "extends", "none"]
        },
        "confidence": {"type": "NUMBER"},
        "evidence": {"type": "STRING"},
        "finding_comparison": {
            "type": "OBJECT",
            "properties": {
                "paper_a_finding": {"type": "STRING"},
                "paper_b_finding": {"type": "STRING"},
                "comparison_note": {"type": "STRING"}
            }
        }
    },
    "required": ["relationship_type", "confidence", "evidence"]
}


# =============================================================================
# 유틸리티 함수
# =============================================================================

def get_section_classifier_prompt(text: str) -> PromptTemplate:
    """섹션 분류 프롬프트 반환."""
    return PromptTemplate(
        system=SECTION_CLASSIFIER_SYSTEM,
        user=SECTION_CLASSIFIER_USER.format(text=text),
        output_schema=SECTION_CLASSIFIER_SCHEMA
    )


def get_semantic_chunker_prompt(text: str, section_type: str) -> PromptTemplate:
    """의미 청킹 프롬프트 반환."""
    return PromptTemplate(
        system=SEMANTIC_CHUNKER_SYSTEM,
        user=SEMANTIC_CHUNKER_USER.format(text=text, section_type=section_type),
        output_schema=SEMANTIC_CHUNKER_SCHEMA
    )


def get_metadata_extractor_prompt(chunk: str, context: str) -> PromptTemplate:
    """메타데이터 추출 프롬프트 반환."""
    return PromptTemplate(
        system=METADATA_EXTRACTOR_SYSTEM,
        user=METADATA_EXTRACTOR_USER.format(chunk=chunk, context=context),
        output_schema=METADATA_EXTRACTOR_SCHEMA
    )


def get_citation_extractor_prompt(text: str) -> PromptTemplate:
    """인용 추출 프롬프트 반환."""
    return PromptTemplate(
        system=CITATION_EXTRACTOR_SYSTEM,
        user=CITATION_EXTRACTOR_USER.format(text=text),
        output_schema=CITATION_EXTRACTOR_SCHEMA
    )


def get_relationship_analyzer_prompt(
    title_a: str, abstract_a: str, findings_a: str, pico_a: str,
    title_b: str, abstract_b: str, findings_b: str, pico_b: str
) -> PromptTemplate:
    """관계 분석 프롬프트 반환."""
    return PromptTemplate(
        system=RELATIONSHIP_ANALYZER_SYSTEM,
        user=RELATIONSHIP_ANALYZER_USER.format(
            title_a=title_a, abstract_a=abstract_a,
            findings_a=findings_a, pico_a=pico_a,
            title_b=title_b, abstract_b=abstract_b,
            findings_b=findings_b, pico_b=pico_b
        ),
        output_schema=RELATIONSHIP_ANALYZER_SCHEMA
    )
