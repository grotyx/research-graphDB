"""Spine Graph Core Node Definitions.

This module contains the core Node dataclasses for the Spine GraphRAG system.
Each node type represents a fundamental entity in the medical knowledge graph:
- PaperNode: Documents (papers, books, reports, etc.) with unified Zotero-compatible schema
- ChunkNode: Text chunks with vector embeddings for hybrid search
- PathologyNode: Diseases and diagnoses
- AnatomyNode: Anatomical locations (spinal levels, regions)
- InterventionNode: Surgical procedures and treatments
- OutcomeNode: Clinical outcomes and measurements

All nodes support bidirectional Neo4j serialization via:
- to_neo4j_properties(): Convert to Neo4j property dict
- from_neo4j_record(): Reconstruct from Neo4j query result

Version: 7.5
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ============================================================================
# Node Definitions
# ============================================================================

@dataclass
class PaperNode:
    """문서 노드 (Unified Document Schema - v6.0).

    Neo4j Labels: Document, Paper (하위 호환성)

    Zotero/EndNote 서지 관리 시스템을 참조하여 설계된 통합 문서 스키마.
    다양한 문서 유형(논문, 책, 신문기사, 웹페이지 등)을 지원합니다.

    Schema Tiers:
    - Tier 1: Core Fields (모든 문서 유형 공통)
    - Tier 2: Type-Specific Fields (문서 유형별 선택적)
    - Tier 3: Domain Extensions (의학/척추 연구 특화)

    v1.0 Changes:
    - summary: 700+ word comprehensive summary (replaces focused extraction)
    - processing_version: Track which pipeline version was used
    - citation_count: Optional citation metrics
    - PICO fields: Deprecated but kept for backward compatibility

    v6.0 Changes:
    - document_type: Zotero 기반 문서 유형 분류
    - creators: 역할 기반 생성자 목록 (저자, 편집자, 번역자 등)
    - Type-specific fields: 책, 신문, 웹페이지 등 타입별 필드
    - 하위 호환성: authors 필드 유지, paper_id → document_id alias

    v3.2 Changes:
    - sub_domains: 다중 분류 지원 (list)
    - surgical_approach: 수술 접근법 (list)

    Attributes:
        paper_id: 문서 고유 식별자 (required, document_id alias)
        document_type: 문서 유형 (DocumentType value, default: journal-article)
        title: 제목 (required)
        creators: 생성자 목록 [{"name": "Kim, J.", "role": "author"}]
        authors: 저자 이름 목록 (하위 호환, creators에서 추출)
        ... (see field definitions below)
    """
    # ==========================================================================
    # Tier 1: Core Fields (모든 문서 유형 공통)
    # ==========================================================================

    # === 식별자 (Required) ===
    paper_id: str  # document_id alias for backward compatibility
    title: str

    # === 문서 유형 (v6.0) ===
    document_type: str = "journal-article"  # DocumentType value

    # === 생성자 정보 (v6.0 확장) ===
    creators: list[dict] = field(default_factory=list)  # [{"name": "...", "role": "author"}]
    authors: list[str] = field(default_factory=list)    # 하위 호환 (creators에서 author role 추출)

    # === 날짜 정보 ===
    year: int = 0
    date: str = ""           # ISO format (2024-03-15)
    access_date: str = ""    # 웹 자료 접근일

    # === 요약/설명 ===
    abstract: str = ""
    short_title: str = ""    # 약식 제목 (인용용)
    summary: str = ""        # v1.0: 700+ word comprehensive summary

    # === 접근 정보 ===
    url: str = ""
    doi: str = ""

    # === 분류/태그 ===
    language: str = "en"     # ISO 639-1
    tags: list[str] = field(default_factory=list)

    # === 저작권/아카이브 ===
    rights: str = ""
    archive: str = ""
    archive_location: str = ""

    # === 시스템 메타 ===
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    source: str = "pdf"      # pdf | pubmed | pdf+pubmed | manual | import
    is_abstract_only: bool = False
    processing_version: str = ""  # v1.0: "v1.0" for new processing pipeline
    citation_count: int = 0       # v1.0: Number of citations (optional)

    # === 멀티유저 지원 (v1.5) ===
    owner: str = "system"    # 소유자 ID (system = 공용)
    shared: bool = True      # True = 모든 사용자 접근 가능, False = 소유자만

    # === 추가 정보 ===
    extra: str = ""          # 기타 정보 (자유 형식)
    notes: str = ""          # 사용자 노트

    # ==========================================================================
    # Tier 2: Type-Specific Fields (문서 유형별 선택적)
    # ==========================================================================

    # === Journal Article (학술 논문) ===
    journal: str = ""
    journal_abbrev: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    issn: str = ""
    pmid: str = ""
    pmc_id: str = ""

    # === Book / Book Section (책/챕터) ===
    publisher: str = ""
    place: str = ""          # 출판 장소
    isbn: str = ""
    edition: str = ""
    num_pages: int = 0
    series: str = ""
    series_number: str = ""
    book_title: str = ""     # Book Section용: 책 제목
    chapter: str = ""        # Book Section용: 챕터 번호

    # === Conference Paper (학회 논문) ===
    conference_name: str = ""
    proceedings_title: str = ""

    # === Thesis (학위 논문) ===
    thesis_type: str = ""    # PhD, MSc, MD, etc.
    university: str = ""
    department: str = ""

    # === Report (보고서) ===
    report_type: str = ""    # Technical, Research, White paper
    report_number: str = ""
    institution: str = ""

    # === Newspaper / Magazine Article (신문/잡지) ===
    publication: str = ""    # 신문/잡지 이름
    section: str = ""        # 섹션 (정치, 경제, 건강 등)

    # === Webpage / Blog (웹페이지/블로그) ===
    website_title: str = ""
    website_type: str = ""   # Blog, Forum, News, etc.

    # === Patent (특허) ===
    patent_number: str = ""
    assignee: str = ""
    filing_date: str = ""
    application_number: str = ""

    # === Dataset (데이터셋) ===
    repository: str = ""
    version: str = ""
    data_format: str = ""    # CSV, JSON, etc.

    # === Software (소프트웨어) ===
    system: str = ""         # 시스템 요구사항
    company: str = ""
    programming_language: str = ""

    # ==========================================================================
    # Tier 3: Domain Extensions (의학/척추 연구 특화)
    # ==========================================================================

    # === 연구 메타데이터 (Medical Research) ===
    study_type: str = ""     # RCT, Cohort, Meta-analysis, etc.
    study_design: str = ""   # randomized/non-randomized/single-arm/multi-arm
    evidence_level: str = "5"  # OCEBM 1a-5
    sample_size: int = 0
    centers: str = ""        # single-center/multi-center
    blinding: str = ""       # none/single-blind/double-blind/open-label
    follow_up_months: int = 0

    # === PICO (v1.0: deprecated but kept for backward compatibility) ===
    # These fields are no longer extracted in v1.0 but preserved for older data
    pico_population: str = ""
    pico_intervention: str = ""
    pico_comparison: str = ""
    pico_outcome: str = ""

    # === PubMed 메타데이터 ===
    mesh_terms: list[str] = field(default_factory=list)
    publication_types: list[str] = field(default_factory=list)

    # === 결론 ===
    main_conclusion: str = ""

    # === 척추 연구 특화 (Spine Research) ===
    sub_domain: str = ""     # SpineSubDomain (deprecated)
    sub_domains: list[str] = field(default_factory=list)  # 다중 분류
    surgical_approach: list[str] = field(default_factory=list)  # Endoscopic, MIS, Open
    anatomy_levels: list[str] = field(default_factory=list)  # Cervical, Lumbar, etc.

    def to_neo4j_properties(self) -> dict:
        """Neo4j 속성 딕셔너리로 변환 (v6.0).

        Returns:
            Neo4j 노드 속성 딕셔너리
        """
        now = datetime.now()

        # 기본 속성 (모든 문서 유형)
        props = {
            # === Tier 1: Core Fields ===
            "paper_id": self.paper_id,
            "document_type": self.document_type,
            "title": self.title,
            "creators": self.creators[:20],  # 최대 20명
            "authors": self.authors[:20],    # 하위 호환
            "year": self.year,
            "date": self.date,
            "access_date": self.access_date,
            "abstract": self.abstract[:2000] if self.abstract else "",
            "short_title": self.short_title,
            "summary": self.summary[:5000] if self.summary else "",  # v1.0: Allow up to 5000 chars
            "url": self.url,
            "doi": self.doi,
            "language": self.language,
            "tags": self.tags[:20],
            "rights": self.rights,
            "archive": self.archive,
            "archive_location": self.archive_location,
            "created_at": self.created_at or now,
            "updated_at": now,
            "source": self.source,
            "is_abstract_only": self.is_abstract_only,
            "processing_version": self.processing_version,  # v1.0
            "citation_count": self.citation_count,          # v1.0
            "owner": self.owner,                            # v1.5: 멀티유저
            "shared": self.shared,                          # v1.5: 공유 여부
            "extra": self.extra[:500] if self.extra else "",
            "notes": self.notes[:1000] if self.notes else "",

            # === Tier 2: Type-Specific (Journal Article) ===
            "journal": self.journal,
            "journal_abbrev": self.journal_abbrev,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "issn": self.issn,
            "pmid": self.pmid,
            "pmc_id": self.pmc_id,

            # === Tier 2: Type-Specific (Book/Chapter) ===
            "publisher": self.publisher,
            "place": self.place,
            "isbn": self.isbn,
            "edition": self.edition,
            "num_pages": self.num_pages,
            "series": self.series,
            "series_number": self.series_number,
            "book_title": self.book_title,
            "chapter": self.chapter,

            # === Tier 2: Type-Specific (Conference) ===
            "conference_name": self.conference_name,
            "proceedings_title": self.proceedings_title,

            # === Tier 2: Type-Specific (Thesis) ===
            "thesis_type": self.thesis_type,
            "university": self.university,
            "department": self.department,

            # === Tier 2: Type-Specific (Report) ===
            "report_type": self.report_type,
            "report_number": self.report_number,
            "institution": self.institution,

            # === Tier 2: Type-Specific (Newspaper/Magazine) ===
            "publication": self.publication,
            "section": self.section,

            # === Tier 2: Type-Specific (Webpage/Blog) ===
            "website_title": self.website_title,
            "website_type": self.website_type,

            # === Tier 2: Type-Specific (Patent) ===
            "patent_number": self.patent_number,
            "assignee": self.assignee,
            "filing_date": self.filing_date,
            "application_number": self.application_number,

            # === Tier 2: Type-Specific (Dataset) ===
            "repository": self.repository,
            "version": self.version,
            "data_format": self.data_format,

            # === Tier 2: Type-Specific (Software) ===
            "system": self.system,
            "company": self.company,
            "programming_language": self.programming_language,

            # === Tier 3: Medical Research Extension ===
            "study_type": self.study_type,
            "study_design": self.study_design,
            "evidence_level": self.evidence_level,
            "sample_size": self.sample_size,
            "centers": self.centers,
            "blinding": self.blinding,
            "follow_up_months": self.follow_up_months,
            "pico_population": self.pico_population[:500] if self.pico_population else "",
            "pico_intervention": self.pico_intervention[:200] if self.pico_intervention else "",
            "pico_comparison": self.pico_comparison[:200] if self.pico_comparison else "",
            "pico_outcome": self.pico_outcome[:500] if self.pico_outcome else "",
            "mesh_terms": self.mesh_terms[:20],
            "publication_types": self.publication_types[:10],
            "main_conclusion": self.main_conclusion[:500] if self.main_conclusion else "",

            # === Tier 3: Spine Research Extension ===
            "sub_domain": self.sub_domain,
            "sub_domains": self.sub_domains[:5],
            "surgical_approach": self.surgical_approach[:5],
            "anatomy_levels": self.anatomy_levels[:5],
        }

        # None 값 필터링 (빈 문자열과 빈 리스트는 유지)
        return {k: v for k, v in props.items() if v is not None}

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "PaperNode":
        """Neo4j 레코드에서 생성 (역직렬화, v6.0).

        Args:
            record: Neo4j 레코드 딕셔너리

        Returns:
            PaperNode 인스턴스
        """
        return cls(
            # === Tier 1: Core Fields ===
            paper_id=record.get("paper_id", ""),
            document_type=record.get("document_type", "journal-article"),
            title=record.get("title", ""),
            creators=record.get("creators", []),
            authors=record.get("authors", []),
            year=record.get("year", 0),
            date=record.get("date", ""),
            access_date=record.get("access_date", ""),
            abstract=record.get("abstract", ""),
            short_title=record.get("short_title", ""),
            summary=record.get("summary", ""),  # v1.0
            url=record.get("url", ""),
            doi=record.get("doi", ""),
            language=record.get("language", "en"),
            tags=record.get("tags", []),
            rights=record.get("rights", ""),
            archive=record.get("archive", ""),
            archive_location=record.get("archive_location", ""),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            source=record.get("source", "pdf"),
            is_abstract_only=record.get("is_abstract_only", False),
            processing_version=record.get("processing_version", ""),  # v1.0
            citation_count=record.get("citation_count", 0),           # v1.0
            owner=record.get("owner", "system"),                      # v1.5: 멀티유저
            shared=record.get("shared", True),                        # v1.5: 공유 여부
            extra=record.get("extra", ""),
            notes=record.get("notes", ""),

            # === Tier 2: Type-Specific (Journal Article) ===
            journal=record.get("journal", ""),
            journal_abbrev=record.get("journal_abbrev", ""),
            volume=record.get("volume", ""),
            issue=record.get("issue", ""),
            pages=record.get("pages", ""),
            issn=record.get("issn", ""),
            pmid=record.get("pmid", ""),
            pmc_id=record.get("pmc_id", ""),

            # === Tier 2: Type-Specific (Book/Chapter) ===
            publisher=record.get("publisher", ""),
            place=record.get("place", ""),
            isbn=record.get("isbn", ""),
            edition=record.get("edition", ""),
            num_pages=record.get("num_pages", 0),
            series=record.get("series", ""),
            series_number=record.get("series_number", ""),
            book_title=record.get("book_title", ""),
            chapter=record.get("chapter", ""),

            # === Tier 2: Type-Specific (Conference) ===
            conference_name=record.get("conference_name", ""),
            proceedings_title=record.get("proceedings_title", ""),

            # === Tier 2: Type-Specific (Thesis) ===
            thesis_type=record.get("thesis_type", ""),
            university=record.get("university", ""),
            department=record.get("department", ""),

            # === Tier 2: Type-Specific (Report) ===
            report_type=record.get("report_type", ""),
            report_number=record.get("report_number", ""),
            institution=record.get("institution", ""),

            # === Tier 2: Type-Specific (Newspaper/Magazine) ===
            publication=record.get("publication", ""),
            section=record.get("section", ""),

            # === Tier 2: Type-Specific (Webpage/Blog) ===
            website_title=record.get("website_title", ""),
            website_type=record.get("website_type", ""),

            # === Tier 2: Type-Specific (Patent) ===
            patent_number=record.get("patent_number", ""),
            assignee=record.get("assignee", ""),
            filing_date=record.get("filing_date", ""),
            application_number=record.get("application_number", ""),

            # === Tier 2: Type-Specific (Dataset) ===
            repository=record.get("repository", ""),
            version=record.get("version", ""),
            data_format=record.get("data_format", ""),

            # === Tier 2: Type-Specific (Software) ===
            system=record.get("system", ""),
            company=record.get("company", ""),
            programming_language=record.get("programming_language", ""),

            # === Tier 3: Medical Research Extension ===
            study_type=record.get("study_type", ""),
            study_design=record.get("study_design", ""),
            evidence_level=record.get("evidence_level", "5"),
            sample_size=record.get("sample_size", 0),
            centers=record.get("centers", ""),
            blinding=record.get("blinding", ""),
            follow_up_months=record.get("follow_up_months", 0),
            pico_population=record.get("pico_population", ""),
            pico_intervention=record.get("pico_intervention", ""),
            pico_comparison=record.get("pico_comparison", ""),
            pico_outcome=record.get("pico_outcome", ""),
            mesh_terms=record.get("mesh_terms", []),
            publication_types=record.get("publication_types", []),
            main_conclusion=record.get("main_conclusion", ""),

            # === Tier 3: Spine Research Extension ===
            sub_domain=record.get("sub_domain", ""),
            sub_domains=record.get("sub_domains", []),
            surgical_approach=record.get("surgical_approach", []),
            anatomy_levels=record.get("anatomy_levels", []),
        )

    def is_v7_processed(self) -> bool:
        """Check if this document was processed with v1.0 pipeline.

        Returns:
            True if processing_version starts with "v7", False otherwise
        """
        return self.processing_version.startswith("v7")

    def get_display_summary(self) -> str:
        """Get summary for display (v7 summary or abstract fallback).

        Returns:
            Summary text (v1.0 summary if available, otherwise abstract, or fallback message)
        """
        if self.summary:
            return self.summary
        return self.abstract or "No summary available"


@dataclass
class ChunkNode:
    """텍스트 청크 노드 (v5.3 - Neo4j Vector Index 통합).

    Neo4j Label: Chunk

    Paper의 세부 청크를 저장하며, 3072차원 벡터 임베딩을 포함 (OpenAI text-embedding-3-large).
    ChromaDB 대체를 위해 Neo4j에 직접 벡터를 저장.

    Relationships:
        - (Paper)-[:HAS_CHUNK]->(Chunk)

    Vector Index:
        - Index name: chunk_embedding_index
        - Dimension: 3072 (OpenAI text-embedding-3-large)
        - Similarity: cosine

    Attributes:
        chunk_id: 청크 고유 식별자 (paper_id + "_chunk_" + index)
        paper_id: 소속 논문 ID
        content: 청크 텍스트 내용
        embedding: 3072차원 벡터 임베딩 (OpenAI)
        tier: 검색 티어 ("tier1" | "tier2")
        section: 논문 섹션 (abstract, methods, results, discussion, etc.)
        content_type: 콘텐츠 유형 (text, table, figure, key_finding)
        evidence_level: 청크의 근거 수준 (논문에서 상속)
        is_key_finding: 핵심 발견 여부
        page_num: PDF 페이지 번호
        chunk_index: 논문 내 청크 순서
        created_at: 생성 시각
    """
    # === 필수 필드 ===
    chunk_id: str
    paper_id: str
    content: str

    # === 벡터 임베딩 ===
    embedding: list[float] = field(default_factory=list)  # 3072-dim OpenAI

    # === 분류 정보 ===
    tier: str = "tier2"  # "tier1" (abstract, conclusion) | "tier2" (full text)
    section: str = ""  # abstract, introduction, methods, results, discussion, conclusion
    content_type: str = "text"  # text, table, figure, key_finding

    # === 메타데이터 ===
    evidence_level: str = "5"  # 논문에서 상속
    is_key_finding: bool = False
    page_num: int = 0
    chunk_index: int = 0

    # === 타임스탬프 ===
    created_at: Optional[datetime] = None

    def to_neo4j_properties(self) -> dict:
        """Neo4j 속성 딕셔너리로 변환.

        Note: embedding은 별도로 처리 (벡터 인덱스 호환성)

        Returns:
            Neo4j 노드 속성 딕셔너리
        """
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "content": self.content,
            "embedding": self.embedding,  # 3072-dim vector
            "tier": self.tier,
            "section": self.section,
            "content_type": self.content_type,
            "evidence_level": self.evidence_level,
            "is_key_finding": self.is_key_finding,
            "page_num": self.page_num,
            "chunk_index": self.chunk_index,
            "created_at": self.created_at or datetime.now(),
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "ChunkNode":
        """Neo4j 레코드에서 ChunkNode 생성.

        Args:
            record: Neo4j 쿼리 결과 레코드

        Returns:
            ChunkNode 인스턴스
        """
        return cls(
            chunk_id=record["chunk_id"],
            paper_id=record.get("paper_id", ""),
            content=record.get("content", ""),
            embedding=record.get("embedding", []),
            tier=record.get("tier", "tier2"),
            section=record.get("section", ""),
            content_type=record.get("content_type", "text"),
            evidence_level=record.get("evidence_level", "5"),
            is_key_finding=record.get("is_key_finding", False),
            page_num=record.get("page_num", 0),
            chunk_index=record.get("chunk_index", 0),
            created_at=record.get("created_at"),
        )


@dataclass
class PathologyNode:
    """질환/진단 노드.

    Neo4j Label: Pathology
    """
    name: str  # Lumbar Stenosis, AIS, Spondylolisthesis
    category: str = ""  # degenerative, deformity, trauma, tumor
    icd10_code: str = ""
    snomed_code: str = ""  # SNOMED-CT Concept ID
    snomed_term: str = ""  # SNOMED-CT Preferred Term
    description: str = ""
    aliases: list[str] = field(default_factory=list)

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "icd10_code": self.icd10_code,
            "snomed_code": self.snomed_code,
            "snomed_term": self.snomed_term,
            "description": self.description,
            "aliases": self.aliases,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "PathologyNode":
        return cls(
            name=record.get("name", ""),
            category=record.get("category", ""),
            icd10_code=record.get("icd10_code", ""),
            snomed_code=record.get("snomed_code", ""),
            snomed_term=record.get("snomed_term", ""),
            description=record.get("description", ""),
            aliases=record.get("aliases", []),
        )


@dataclass
class AnatomyNode:
    """해부학적 위치 노드.

    Neo4j Label: Anatomy
    """
    name: str  # L4-5, C5-6, Thoracolumbar junction
    region: str = ""  # cervical, thoracic, lumbar, sacral
    level_count: int = 1  # 수술 레벨 수

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "region": self.region,
            "level_count": self.level_count,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "AnatomyNode":
        return cls(
            name=record.get("name", ""),
            region=record.get("region", ""),
            level_count=record.get("level_count", 1),
        )


@dataclass
class InterventionNode:
    """수술/치료법 노드.

    Neo4j Label: Intervention

    v1.1: Extended with TechniqueNode and SurgicalStepNode fields.
    """
    name: str  # TLIF, OLIF, UBE, Laminectomy
    full_name: str = ""
    category: str = ""  # InterventionCategory value
    approach: str = ""  # anterior, posterior, lateral
    is_minimally_invasive: bool = False
    snomed_code: str = ""  # SNOMED-CT Concept ID
    snomed_term: str = ""  # SNOMED-CT Preferred Term
    aliases: list[str] = field(default_factory=list)

    # Technique fields (merged from TechniqueNode - v1.1)
    technique_description: str = ""  # Detailed technique description
    difficulty_level: str = ""  # basic, intermediate, advanced
    pearls: list[str] = field(default_factory=list)  # Surgical tips
    pitfalls: list[str] = field(default_factory=list)  # Cautions
    learning_curve_cases: int = 0  # Number of cases for learning curve

    # Surgical step fields (merged from SurgicalStepNode - v1.1)
    surgical_steps: list[dict] = field(default_factory=list)  # [{"step": 1, "name": "...", "description": "..."}]

    # Required resources (v1.1)
    required_implants: list[str] = field(default_factory=list)  # ["Pedicle Screw", "PEEK Cage"]
    required_instruments: list[str] = field(default_factory=list)  # ["Kerrison Rongeur"]

    # Billing/coding (v1.1)
    cpt_code: str = ""  # CPT procedure code

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "category": self.category,
            "approach": self.approach,
            "is_minimally_invasive": self.is_minimally_invasive,
            "snomed_code": self.snomed_code,
            "snomed_term": self.snomed_term,
            "aliases": self.aliases,
            # Technique fields
            "technique_description": self.technique_description[:2000] if self.technique_description else "",
            "difficulty_level": self.difficulty_level,
            "pearls": self.pearls[:20],
            "pitfalls": self.pitfalls[:20],
            "learning_curve_cases": self.learning_curve_cases,
            # Surgical steps
            "surgical_steps": self.surgical_steps[:30],  # Limit to 30 steps
            # Required resources
            "required_implants": self.required_implants[:20],
            "required_instruments": self.required_instruments[:20],
            # Billing
            "cpt_code": self.cpt_code,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "InterventionNode":
        return cls(
            name=record.get("name", ""),
            full_name=record.get("full_name", ""),
            category=record.get("category", ""),
            approach=record.get("approach", ""),
            is_minimally_invasive=record.get("is_minimally_invasive", False),
            snomed_code=record.get("snomed_code", ""),
            snomed_term=record.get("snomed_term", ""),
            aliases=record.get("aliases", []),
            # Technique fields
            technique_description=record.get("technique_description", ""),
            difficulty_level=record.get("difficulty_level", ""),
            pearls=record.get("pearls", []),
            pitfalls=record.get("pitfalls", []),
            learning_curve_cases=record.get("learning_curve_cases", 0),
            # Surgical steps
            surgical_steps=record.get("surgical_steps", []),
            # Required resources
            required_implants=record.get("required_implants", []),
            required_instruments=record.get("required_instruments", []),
            # Billing
            cpt_code=record.get("cpt_code", ""),
        )


@dataclass
class OutcomeNode:
    """결과변수 노드.

    Neo4j Label: Outcome
    """
    name: str  # Fusion Rate, VAS, ODI, JOA, SVA
    type: str = ""  # OutcomeType value
    unit: str = ""  # %, points, mm
    direction: str = ""  # higher_is_better, lower_is_better
    snomed_code: str = ""  # SNOMED-CT Concept ID
    snomed_term: str = ""  # SNOMED-CT Preferred Term
    description: str = ""

    def to_neo4j_properties(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "unit": self.unit,
            "direction": self.direction,
            "snomed_code": self.snomed_code,
            "snomed_term": self.snomed_term,
            "description": self.description,
        }

    @classmethod
    def from_neo4j_record(cls, record: dict) -> "OutcomeNode":
        return cls(
            name=record.get("name", ""),
            type=record.get("type", ""),
            unit=record.get("unit", ""),
            direction=record.get("direction", ""),
            snomed_code=record.get("snomed_code", ""),
            snomed_term=record.get("snomed_term", ""),
            description=record.get("description", ""),
        )
