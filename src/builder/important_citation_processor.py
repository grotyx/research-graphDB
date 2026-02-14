"""Important Citation Processor Pipeline.

논문에서 중요한 인용을 추출하고, PubMed에서 인용된 논문을 검색한 후,
Neo4j에 Paper 노드와 CITES 관계를 생성하는 통합 파이프라인입니다.

주요 기능:
1. CitationContextExtractor로 중요 인용 추출 (supports/contradicts)
2. PubMedEnricher로 인용된 논문 검색
3. Neo4j에 Paper 노드 생성 (인용된 논문)
4. CITES 관계 생성 (컨텍스트 포함)

환경변수:
- LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
- ANTHROPIC_API_KEY: Claude API 키 (Claude 사용 시)
- GEMINI_API_KEY: Gemini API 키 (Gemini 사용 시)

v3.2+ Important Citation Feature
v3.2.1 Claude/Gemini 듀얼 프로바이더 지원
"""

import asyncio
import logging
import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

try:
    from builder.citation_context_extractor import (
        CitationContextExtractor,
        ExtractedCitation,
        CitationExtractionResult
    )
    from builder.pubmed_enricher import PubMedEnricher, BibliographicMetadata
    from builder.entity_extractor import EntityExtractor
    from graph.neo4j_client import Neo4jClient
    from graph.relationship_builder import RelationshipBuilder, SpineMetadata
    from graph.spine_schema import (
        PaperNode,
        CitesRelationship,
        CitationContext,
        CypherTemplates
    )
except ImportError:
    from src.builder.citation_context_extractor import (
        CitationContextExtractor,
        ExtractedCitation,
        CitationExtractionResult
    )
    from src.builder.pubmed_enricher import PubMedEnricher, BibliographicMetadata
    from src.builder.entity_extractor import EntityExtractor
    from src.graph.neo4j_client import Neo4jClient
    from src.graph.relationship_builder import RelationshipBuilder, SpineMetadata
    from src.graph.spine_schema import (
        PaperNode,
        CitesRelationship,
        CitationContext,
        CypherTemplates
    )

# Alias for backward compatibility
GraphSpineMetadata = SpineMetadata

logger = logging.getLogger(__name__)


@dataclass
class CitationProcessingResult:
    """인용 처리 결과.

    Attributes:
        citing_paper_id: 인용하는 논문 ID
        total_citations_found: 추출된 전체 인용 수
        important_citations_count: 중요 인용 수 (supports/contradicts)
        papers_created: 생성된 Paper 노드 수
        relationships_created: 생성된 CITES 관계 수
        pubmed_search_failures: PubMed 검색 실패 수
        processed_citations: 처리된 인용 정보 목록 (간략)
        citations_data: JSON 저장용 상세 인용 데이터 (PubMed abstract 포함)
        errors: 에러 목록
    """
    citing_paper_id: str = ""
    total_citations_found: int = 0
    important_citations_count: int = 0
    papers_created: int = 0
    relationships_created: int = 0
    pubmed_search_failures: int = 0
    doi_fallback_successes: int = 0  # v7.16: DOI fallback 성공 수
    basic_citations_created: int = 0  # v7.16: basic info만으로 생성된 수
    processed_citations: list[dict] = field(default_factory=list)
    citations_data: list[dict] = field(default_factory=list)  # v7.6: JSON 저장용 상세 데이터
    errors: list[str] = field(default_factory=list)


@dataclass
class ProcessedCitation:
    """처리 완료된 인용 정보.

    Attributes:
        original: 추출된 원본 인용
        pubmed_metadata: PubMed에서 찾은 메타데이터 (None이면 미발견)
        cited_paper_id: 생성된 Paper 노드 ID
        relationship_created: CITES 관계 생성 여부
    """
    original: ExtractedCitation
    pubmed_metadata: Optional[BibliographicMetadata] = None
    cited_paper_id: Optional[str] = None
    relationship_created: bool = False


class ImportantCitationProcessor:
    """중요 인용 처리 파이프라인.

    논문에서 중요한 인용을 추출하고, PubMed에서 원본 논문을 찾은 후,
    Neo4j에 Paper 노드와 CITES 관계를 생성합니다.

    파이프라인:
    1. CitationContextExtractor: Discussion/Results에서 중요 인용 추출
    2. PubMedEnricher: 저자+연도로 인용된 논문 검색
    3. Neo4jClient: Paper 노드 및 CITES 관계 생성

    환경변수:
        LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
        ANTHROPIC_API_KEY: Claude API 키
        GEMINI_API_KEY: Gemini API 키

    Example:
        ```python
        # 환경변수 기반 자동 선택
        processor = ImportantCitationProcessor(
            pubmed_email="your@email.com"
        )

        # 또는 특정 provider 지정
        processor = ImportantCitationProcessor(
            provider="gemini",
            pubmed_email="your@email.com"
        )

        result = await processor.process_paper_citations(
            citing_paper_id="paper_123",
            discussion_text="Our findings are consistent with Kim et al. (2023)...",
            results_text="VAS improved from 7.2 to 2.1...",
            main_findings=["UBE showed better outcomes"]
        )

        print(f"Created {result.papers_created} paper nodes")
        print(f"Created {result.relationships_created} CITES relationships")
        ```
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        pubmed_email: Optional[str] = None,
        pubmed_api_key: Optional[str] = None,
        neo4j_client: Optional[Neo4jClient] = None,
        relationship_builder: Optional[RelationshipBuilder] = None,
        min_confidence: float = 0.7,
        max_citations: int = 20,
        analyze_cited_abstracts: bool = True,
        doi_fetcher=None,
        # 레거시 호환성
        gemini_api_key: Optional[str] = None
    ):
        """ImportantCitationProcessor 초기화.

        Args:
            provider: LLM 제공자 ("claude" 또는 "gemini"). None이면 환경변수 사용.
            model: 모델 ID. None이면 환경변수 사용.
            pubmed_email: PubMed NCBI 연락처 이메일
            pubmed_api_key: PubMed API 키 (rate limit 향상)
            neo4j_client: Neo4j 클라이언트 (None이면 새로 생성)
            relationship_builder: 관계 빌더 (인용된 논문 분석용)
            min_confidence: 최소 매칭 신뢰도 (0.0-1.0)
            max_citations: 최대 처리할 인용 수
            analyze_cited_abstracts: 인용된 논문 abstract LLM 분석 여부 (v7.6)
            doi_fetcher: DOIFulltextFetcher 인스턴스 (v7.16 DOI fallback용)
            gemini_api_key: (레거시) Gemini API 키 - 사용 권장하지 않음
        """
        # 레거시 호환성: gemini_api_key가 전달된 경우
        if gemini_api_key and not provider:
            self.extractor = CitationContextExtractor(api_key=gemini_api_key)
        else:
            self.extractor = CitationContextExtractor(provider=provider, model=model)

        self.enricher = PubMedEnricher(
            email=pubmed_email,
            api_key=pubmed_api_key
        )
        self.neo4j_client = neo4j_client
        self.relationship_builder = relationship_builder
        self.min_confidence = min_confidence
        self.max_citations = max_citations
        self.analyze_cited_abstracts = analyze_cited_abstracts

        # v7.6: EntityExtractor for cited paper abstract analysis
        self.entity_extractor = EntityExtractor() if analyze_cited_abstracts else None

        # v7.16: DOI/Crossref fallback for citations when PubMed fails
        self.doi_fetcher = doi_fetcher

    async def process_paper_citations(
        self,
        citing_paper_id: str,
        discussion_text: str,
        results_text: str = "",
        main_findings: Optional[list[str]] = None,
        paper_title: str = ""
    ) -> CitationProcessingResult:
        """논문의 중요 인용을 처리합니다.

        전체 파이프라인:
        1. LLM으로 중요 인용 추출
        2. 각 인용에 대해 PubMed 검색
        3. Neo4j에 Paper 노드 생성
        4. CITES 관계 생성

        Args:
            citing_paper_id: 인용하는 논문 ID
            discussion_text: Discussion 섹션 텍스트
            results_text: Results 섹션 텍스트
            main_findings: 논문의 주요 발견사항
            paper_title: 논문 제목 (로깅용)

        Returns:
            CitationProcessingResult: 처리 결과
        """
        result = CitationProcessingResult(citing_paper_id=citing_paper_id)

        try:
            # 1. 중요 인용 추출
            logger.info(f"Extracting citations from paper: {citing_paper_id}")
            extraction_result = await self.extractor.extract_important_citations(
                discussion_text=discussion_text,
                results_text=results_text,
                main_findings=main_findings,
                paper_title=paper_title
            )

            result.total_citations_found = len(extraction_result.all_citations)
            result.important_citations_count = len(extraction_result.important_citations)

            logger.info(
                f"Found {result.important_citations_count} important citations "
                f"out of {result.total_citations_found} total"
            )

            if not extraction_result.important_citations:
                logger.info("No important citations to process")
                return result

            # 최대 인용 수 제한
            citations_to_process = extraction_result.important_citations[:self.max_citations]

            # 2. 각 인용에 대해 처리
            for citation in citations_to_process:
                processed = await self._process_single_citation(
                    citation=citation,
                    citing_paper_id=citing_paper_id
                )

                if processed.pubmed_metadata:
                    source = processed.pubmed_metadata.source
                    if source == "crossref":
                        result.doi_fallback_successes += 1
                    elif source == "citation_basic":
                        result.basic_citations_created += 1
                    if processed.cited_paper_id:
                        result.papers_created += 1
                    if processed.relationship_created:
                        result.relationships_created += 1
                else:
                    result.pubmed_search_failures += 1

                # 처리 결과 기록 (간략 정보)
                result.processed_citations.append({
                    "raw_citation": citation.raw_citation,
                    "context": citation.context,
                    "pubmed_found": processed.pubmed_metadata is not None,
                    "enrichment_source": processed.pubmed_metadata.source if processed.pubmed_metadata else "none",
                    "cited_paper_id": processed.cited_paper_id,
                    "confidence": processed.pubmed_metadata.confidence if processed.pubmed_metadata else 0
                })

                # v7.6: JSON 저장용 상세 데이터 (PubMed abstract 포함)
                citation_detail = {
                    "authors": citation.authors,
                    "year": citation.year,
                    "context": citation.context,
                    "section": citation.section,
                    "citation_text": citation.citation_text,
                    "importance_reason": citation.importance_reason,
                    "outcome_comparison": citation.outcome_comparison,
                    "direction_match": citation.direction_match,
                    "pubmed_found": processed.pubmed_metadata is not None,
                }

                # PubMed에서 찾은 경우 상세 정보 추가
                if processed.pubmed_metadata:
                    pm = processed.pubmed_metadata
                    citation_detail.update({
                        "pmid": pm.pmid,
                        "doi": pm.doi,
                        "title": pm.title,
                        "journal": pm.journal,
                        "abstract": pm.abstract,  # PubMed abstract 포함
                        "mesh_terms": pm.mesh_terms,
                        "publication_types": pm.publication_types,
                        "cited_paper_id": processed.cited_paper_id,
                        "confidence": pm.confidence,
                    })

                result.citations_data.append(citation_detail)

            logger.info(
                f"Citation processing complete: "
                f"{result.papers_created} papers, {result.relationships_created} relationships"
            )

        except Exception as e:
            error_msg = f"Citation processing error: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        return result

    def _extract_keywords_from_citation_text(self, citation_text: str, authors: list[str] = None) -> str:
        """citation_text에서 PubMed 검색용 키워드 추출.

        인용 문장에서 저자/연도 패턴을 제거하고 의학 관련 키워드를 추출합니다.

        Args:
            citation_text: 인용이 포함된 원본 문장
            authors: 제거할 저자 목록 (선택)

        Returns:
            검색에 사용할 키워드 문자열 (예: "TLIF lumbar fusion")
        """
        if not citation_text:
            return ""

        text = citation_text

        # 1. 저자 패턴 제거 (Kim et al., Park and Lee, Kim 2023, etc.)
        # "Kim et al. (2023)", "Kim et al., 2023", "Kim and Park (2023)"
        author_patterns = [
            r'\b\w+\s+et\s+al\.?\s*\(?[\d,\s]*\)?',  # Kim et al. (2023)
            r'\b\w+\s+and\s+\w+\s*\(?[\d,\s]*\)?',    # Kim and Park (2023)
            r'\b[A-Z][a-z]+\s*\(\d{4}\)',              # Kim (2023)
            r'\b[A-Z][a-z]+\s+\d{4}\b',                # Kim 2023
        ]
        for pattern in author_patterns:
            text = re.sub(pattern, '', text)

        # 2. 특정 저자명 제거
        if authors:
            for author in authors:
                text = re.sub(rf'\b{re.escape(author)}\b', '', text, flags=re.IGNORECASE)

        # 3. 숫자 및 특수문자 제거 (연도, 통계값 등)
        text = re.sub(r'\d+\.?\d*%?', '', text)  # 숫자, 퍼센트
        text = re.sub(r'[<>=±]', '', text)        # 비교 연산자
        text = re.sub(r'\([^)]*\)', '', text)     # 괄호 내용

        # 4. 불필요한 단어 제거 (stopwords)
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'was', 'were', 'been', 'be', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
            'might', 'must', 'can', 'this', 'that', 'these', 'those', 'is', 'are',
            'reported', 'found', 'showed', 'demonstrated', 'observed', 'noted',
            'study', 'studies', 'results', 'findings', 'similar', 'consistent',
            'previous', 'prior', 'et', 'al', 'also', 'however', 'although',
            'whereas', 'our', 'their', 'authors', 'patients', 'cases'
        }

        words = text.lower().split()
        keywords = [w.strip('.,;:()[]"\'') for w in words
                   if w.strip('.,;:()[]"\'') not in stopwords
                   and len(w.strip('.,;:()[]"\'')) > 2]

        # 5. 의학 관련 키워드 우선순위 부여
        medical_keywords = {
            # Spine terms
            'spine', 'spinal', 'lumbar', 'cervical', 'thoracic', 'vertebral',
            'disc', 'disk', 'herniation', 'stenosis', 'spondylolisthesis',
            'decompression', 'fusion', 'laminectomy', 'discectomy', 'foraminotomy',
            # Procedures
            'tlif', 'plif', 'alif', 'olif', 'xlif', 'llif', 'ube', 'bess',
            'endoscopic', 'minimally', 'invasive', 'percutaneous', 'microscopic',
            # Outcomes
            'vas', 'odi', 'joa', 'eq-5d', 'sf-36', 'oswestry', 'pain', 'disability',
            'complication', 'outcomes', 'revision', 'reoperation',
            # Other
            'fracture', 'scoliosis', 'kyphosis', 'deformity', 'tumor', 'metastatic'
        }

        # 의학 키워드가 있으면 우선 사용
        important_kws = [kw for kw in keywords if kw in medical_keywords]
        other_kws = [kw for kw in keywords if kw not in medical_keywords][:3]

        # 최대 5개 키워드 반환
        result_keywords = (important_kws + other_kws)[:5]

        return ' '.join(result_keywords)

    @staticmethod
    def _extract_doi_from_text(text: str) -> Optional[str]:
        """citation_text에서 DOI 추출.

        Args:
            text: 인용 문장 텍스트

        Returns:
            추출된 DOI 문자열 또는 None
        """
        if not text:
            return None
        doi_match = re.search(r'10\.\d{4,9}/[^\s,;)\]]+', text)
        if doi_match:
            return doi_match.group().rstrip('.')
        return None

    @staticmethod
    def _create_basic_metadata(citation: ExtractedCitation) -> Optional[BibliographicMetadata]:
        """모든 enrichment 실패 시 기본 메타데이터 생성.

        저자, 연도, citation_text만으로 최소한의 BibliographicMetadata를 생성합니다.
        Paper 노드를 생성하여 CITES 관계를 유지하기 위한 목적입니다.

        Args:
            citation: 추출된 인용 정보

        Returns:
            BibliographicMetadata (minimal) 또는 None (정보 부족 시)
        """
        if not citation.authors and not citation.raw_citation:
            return None

        if citation.authors:
            if len(citation.authors) > 1:
                title_placeholder = f"{citation.authors[0]} et al. ({citation.year or 'n.d.'})"
            else:
                title_placeholder = f"{citation.authors[0]} ({citation.year or 'n.d.'})"
        else:
            title_placeholder = citation.raw_citation[:100] if citation.raw_citation else "Unknown"

        return BibliographicMetadata(
            title=title_placeholder,
            authors=citation.authors or [],
            year=citation.year or 0,
            abstract="",
            source="citation_basic",
            confidence=0.3,
            enriched_at=datetime.now(),
        )

    async def _process_single_citation(
        self,
        citation: ExtractedCitation,
        citing_paper_id: str
    ) -> ProcessedCitation:
        """단일 인용 처리 (PubMed → DOI → Crossref → Basic fallback).

        Args:
            citation: 추출된 인용 정보
            citing_paper_id: 인용하는 논문 ID

        Returns:
            ProcessedCitation: 처리 결과
        """
        processed = ProcessedCitation(original=citation)

        try:
            # 저자 정보 파싱 (raw_citation에서 추출)
            if not citation.authors and citation.raw_citation:
                parsed = self.extractor.parse_citation_reference(citation.raw_citation)
                if parsed["authors"]:
                    citation.authors = parsed["authors"]
                if parsed["year"] and not citation.year:
                    citation.year = parsed["year"]

            # title이 없으면 citation_text에서 키워드 추출
            title_keywords = citation.title
            if not title_keywords and citation.citation_text:
                title_keywords = self._extract_keywords_from_citation_text(
                    citation.citation_text,
                    authors=citation.authors
                )
                if title_keywords:
                    logger.debug(f"Extracted keywords from citation_text: '{title_keywords}'")

            # === Step 1: PubMed 검색 ===
            enrichment_result = await self.enricher.search_and_enrich_citation(
                authors=citation.authors,
                year=citation.year if citation.year else None,
                title=title_keywords if title_keywords else None,
                min_confidence=self.min_confidence
            )

            if enrichment_result:
                logger.info(f"PubMed found citation: {enrichment_result.title[:50]}...")

            # === Step 2: DOI Fallback (PubMed 실패 시) ===
            if not enrichment_result and self.doi_fetcher:
                doi_metadata = None

                # 2a. citation_text에서 DOI 추출 시도
                extracted_doi = self._extract_doi_from_text(citation.citation_text)
                if not extracted_doi:
                    extracted_doi = self._extract_doi_from_text(citation.raw_citation)

                if extracted_doi:
                    try:
                        logger.info(f"Trying DOI fallback: {extracted_doi}")
                        doi_metadata = await self.doi_fetcher.get_metadata_only(extracted_doi)
                    except Exception as e:
                        logger.warning(f"DOI lookup failed for {extracted_doi}: {e}")

                # 2b. DOI 없으면 Crossref 서지 검색
                if not doi_metadata and hasattr(self.doi_fetcher, 'search_by_bibliographic'):
                    try:
                        search_title = title_keywords or ""
                        search_authors = citation.authors or []
                        if search_title or search_authors:
                            logger.info(
                                f"Trying Crossref bibliographic search: "
                                f"authors={search_authors[:2]}, year={citation.year}"
                            )
                            doi_metadata = await self.doi_fetcher.search_by_bibliographic(
                                title=search_title,
                                authors=search_authors,
                                year=citation.year if citation.year else None,
                            )
                    except Exception as e:
                        logger.warning(f"Crossref bibliographic search failed: {e}")

                # 2c. DOI 결과를 BibliographicMetadata로 변환
                if doi_metadata:
                    enrichment_result = BibliographicMetadata.from_doi_metadata(
                        doi_metadata, confidence=0.75
                    )
                    logger.info(
                        f"DOI/Crossref fallback found: {doi_metadata.title[:50]}... "
                        f"(DOI: {doi_metadata.doi})"
                    )

            # === Step 3: 모든 enrichment 실패 → basic metadata ===
            if not enrichment_result:
                enrichment_result = self._create_basic_metadata(citation)
                if enrichment_result:
                    logger.info(
                        f"Creating basic citation node: "
                        f"{enrichment_result.title[:50]}..."
                    )

            # === Step 4: Neo4j에 Paper 노드 + CITES 관계 생성 ===
            if enrichment_result:
                processed.pubmed_metadata = enrichment_result

                if self.neo4j_client:
                    cited_paper_id = await self._create_cited_paper_node(enrichment_result)
                    processed.cited_paper_id = cited_paper_id

                    if cited_paper_id:
                        rel_created = await self._create_cites_relationship(
                            citing_paper_id=citing_paper_id,
                            cited_paper_id=cited_paper_id,
                            citation=citation,
                            confidence=enrichment_result.confidence
                        )
                        processed.relationship_created = rel_created

        except Exception as e:
            logger.warning(f"Error processing citation '{citation.raw_citation}': {e}")

        return processed

    async def _create_cited_paper_node(
        self,
        metadata: BibliographicMetadata
    ) -> Optional[str]:
        """인용된 논문의 Paper 노드 생성 및 LLM 분석 (v7.6).

        v7.6 업데이트:
        - abstract가 있으면 LLM으로 엔티티 추출
        - relationship_builder로 관계 구축 (STUDIES, INVESTIGATES, REPORTS)

        Args:
            metadata: PubMed 메타데이터

        Returns:
            생성된 paper_id 또는 None
        """
        if not self.neo4j_client:
            return None

        try:
            # paper_id 생성 (PMID 우선, 없으면 해시)
            if metadata.pmid:
                paper_id = f"pmid_{metadata.pmid}"
            elif metadata.doi:
                paper_id = f"doi_{metadata.doi.replace('/', '_')}"
            else:
                # 제목+저자로 해시 생성
                hash_input = f"{metadata.title}_{','.join(metadata.authors[:3])}"
                paper_id = f"cited_{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"

            # 이미 존재하는 논문인지 확인
            existing_check = await self.neo4j_client.run_query(
                "MATCH (p:Paper {paper_id: $paper_id}) RETURN p.paper_id as id",
                {"paper_id": paper_id}
            )
            if existing_check and len(existing_check) > 0:
                logger.debug(f"Paper already exists: {paper_id}, skipping LLM analysis")
                return paper_id

            # v7.6: abstract LLM 분석으로 엔티티 추출
            spine_metadata = None
            if self.analyze_cited_abstracts and self.entity_extractor and metadata.abstract:
                try:
                    logger.debug(f"Analyzing abstract for cited paper: {paper_id}")
                    # EntityExtractor로 엔티티 추출
                    from builder.document_type_detector import DocumentType
                    entities = await self.entity_extractor.extract(
                        text=metadata.abstract,
                        document_type=DocumentType.JOURNAL_ARTICLE
                    )

                    if entities:
                        spine_metadata = GraphSpineMetadata(
                            sub_domain="Unknown",
                            sub_domains=[],
                            anatomy_levels=[],
                            interventions=[e.name for e in entities.interventions] if entities.interventions else [],
                            pathologies=[e.name for e in entities.pathologies] if entities.pathologies else [],
                            outcomes=[e.name for e in entities.outcomes] if entities.outcomes else [],
                            surgical_approach=[],
                            summary=metadata.abstract[:500] if metadata.abstract else "",
                            processing_version="v7.6_cited",
                        )
                        logger.debug(
                            f"Extracted entities from cited paper: "
                            f"interventions={len(entities.interventions or [])}, "
                            f"pathologies={len(entities.pathologies or [])}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to analyze cited paper abstract: {e}")

            # relationship_builder가 있으면 전체 관계 구축 사용
            if self.relationship_builder and spine_metadata:
                try:
                    # ExtractedMetadata 호환 객체 생성
                    from dataclasses import dataclass, field as df

                    @dataclass
                    class ExtractedMetaCompat:
                        title: str = ""
                        authors: list = df(default_factory=list)
                        year: int = 0
                        journal: str = ""
                        doi: str = ""
                        pmid: str = ""
                        evidence_level: str = "unknown"
                        abstract: str = ""
                        spine: object = None

                    meta_compat = ExtractedMetaCompat(
                        title=metadata.title,
                        authors=metadata.authors,
                        year=metadata.year,
                        journal=metadata.journal,
                        doi=metadata.doi or "",
                        pmid=metadata.pmid or "",
                        abstract=metadata.abstract or "",
                        spine=spine_metadata,
                    )

                    # build_from_paper로 Paper + 모든 관계 생성
                    build_result = await self.relationship_builder.build_from_paper(
                        paper_id=paper_id,
                        metadata=meta_compat,
                        spine_metadata=spine_metadata,
                        chunks=[],
                        owner="cited_import",
                        shared=True
                    )

                    logger.info(
                        f"Built cited paper with relationships: {paper_id}, "
                        f"nodes={build_result.nodes_created}, rels={build_result.relationships_created}"
                    )
                    return paper_id

                except Exception as e:
                    logger.warning(f"Failed to build relationships for cited paper: {e}")
                    # 폴백: 기본 Paper 노드만 생성

            # 폴백: 기본 PaperNode만 생성 (relationship_builder 없는 경우)
            paper_node = PaperNode(
                paper_id=paper_id,
                title=metadata.title,
                authors=metadata.authors,
                year=metadata.year,
                journal=metadata.journal,
                journal_abbrev=metadata.journal_abbrev,
                doi=metadata.doi if metadata.doi else None,
                pmid=metadata.pmid if metadata.pmid else None,
                abstract=metadata.abstract,
                mesh_terms=metadata.mesh_terms,
                publication_types=metadata.publication_types,
                created_at=datetime.now()
            )

            await self.neo4j_client.run_query(
                CypherTemplates.MERGE_PAPER,
                {
                    "paper_id": paper_id,
                    "properties": paper_node.to_neo4j_properties()
                }
            )

            # v7.14.12: Abstract 임베딩 자동 생성
            if metadata.abstract and len(metadata.abstract.strip()) > 0:
                await self._generate_abstract_embedding(paper_id, metadata.abstract)

            logger.debug(f"Created Paper node (basic): {paper_id}")
            return paper_id

        except Exception as e:
            logger.warning(f"Failed to create Paper node: {e}")
            return None

    async def _generate_abstract_embedding(
        self,
        paper_id: str,
        abstract: str
    ) -> bool:
        """Paper의 abstract 임베딩 생성 및 저장.

        v7.14.12: cited paper에도 abstract 임베딩 자동 생성

        Args:
            paper_id: Paper ID
            abstract: Abstract 텍스트

        Returns:
            성공 여부
        """
        try:
            import os
            from openai import OpenAI

            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # OpenAI 임베딩 생성 (3072차원)
            response = openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=abstract[:8000],
                dimensions=3072
            )

            embedding = response.data[0].embedding

            # Neo4j에 임베딩 저장
            await self.neo4j_client.run_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """,
                {"paper_id": paper_id, "embedding": embedding}
            )

            logger.debug(f"Abstract embedding generated for cited paper {paper_id}")
            return True

        except ImportError:
            logger.warning("OpenAI package not installed, skipping abstract embedding")
            return False
        except Exception as e:
            logger.warning(f"Failed to generate abstract embedding for {paper_id}: {e}")
            return False

    async def _create_cites_relationship(
        self,
        citing_paper_id: str,
        cited_paper_id: str,
        citation: ExtractedCitation,
        confidence: float
    ) -> bool:
        """CITES 관계 생성.

        Args:
            citing_paper_id: 인용하는 논문 ID
            cited_paper_id: 인용된 논문 ID
            citation: 추출된 인용 정보
            confidence: PubMed 매칭 신뢰도

        Returns:
            성공 여부
        """
        if not self.neo4j_client:
            return False

        try:
            # CitationContext 매핑
            context_map = {
                "supports_result": CitationContext.SUPPORTS_RESULT,
                "contradicts_result": CitationContext.CONTRADICTS_RESULT,
                "comparison": CitationContext.COMPARISON,
                "methodological": CitationContext.METHODOLOGICAL,
                "background": CitationContext.BACKGROUND
            }
            context = context_map.get(citation.context, CitationContext.BACKGROUND)

            # CitesRelationship 생성
            cites_rel = CitesRelationship(
                citing_paper_id=citing_paper_id,
                cited_paper_id=cited_paper_id,
                context=context,
                section=citation.section,
                citation_text=citation.citation_text,
                importance_reason=citation.importance_reason,
                outcome_comparison=citation.outcome_comparison,
                direction_match=citation.direction_match,
                confidence=min(citation.confidence, confidence),  # 둘 중 낮은 값
                detected_by="llm_extraction",
                created_at=datetime.now()
            )

            # Neo4j에 저장
            await self.neo4j_client.run_query(
                CypherTemplates.CREATE_CITES_RELATION,
                {
                    "citing_paper_id": citing_paper_id,
                    "cited_paper_id": cited_paper_id,
                    "properties": cites_rel.to_neo4j_properties()
                }
            )

            logger.debug(
                f"Created CITES relationship: {citing_paper_id} -> {cited_paper_id} "
                f"({citation.context})"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to create CITES relationship: {e}")
            return False

    async def process_from_chunks(
        self,
        citing_paper_id: str,
        chunks: list[dict],
        main_findings: Optional[list[str]] = None,
        paper_title: str = ""
    ) -> CitationProcessingResult:
        """ExtractedChunk 목록에서 중요 인용을 처리합니다.

        Args:
            citing_paper_id: 인용하는 논문 ID
            chunks: ExtractedChunk 딕셔너리 목록
            main_findings: 논문의 주요 발견사항
            paper_title: 논문 제목

        Returns:
            CitationProcessingResult: 처리 결과
        """
        # Discussion과 Results 섹션 추출
        discussion_text = ""
        results_text = ""

        for chunk in chunks:
            section = chunk.get("section", "").lower()
            content = chunk.get("content", "")

            if "discussion" in section or "conclusion" in section:
                discussion_text += content + "\n"
            elif "result" in section:
                results_text += content + "\n"

        return await self.process_paper_citations(
            citing_paper_id=citing_paper_id,
            discussion_text=discussion_text,
            results_text=results_text,
            main_findings=main_findings,
            paper_title=paper_title
        )

    async def process_from_integrated_citations(
        self,
        citing_paper_id: str,
        citations: list[dict]
    ) -> CitationProcessingResult:
        """통합 PDF 처리에서 추출된 인용을 처리합니다 (LLM 호출 없음).

        UnifiedPDFProcessor의 important_citations 필드에서 이미 추출된 인용을
        처리하여 PubMed 검색 및 Neo4j 관계 생성만 수행합니다.

        Args:
            citing_paper_id: 인용하는 논문 ID
            citations: 통합 추출된 인용 목록. 각 dict는:
                - authors: list[str] (성씨 목록)
                - year: int
                - context: str (supports_result/contradicts_result/comparison 등)
                - section: str (discussion/results 등)
                - citation_text: str (원본 문장)
                - importance_reason: str (중요한 이유)
                - outcome_comparison: str (옵션)
                - direction_match: bool (옵션)

        Returns:
            CitationProcessingResult: 처리 결과

        Note:
            이 메서드는 LLM 호출을 하지 않습니다.
            인용이 이미 UnifiedPDFProcessor에서 추출되었기 때문입니다.
            비용 절감: 별도 LLM 호출 대비 ~50% 절감
        """
        result = CitationProcessingResult(
            citing_paper_id=citing_paper_id,
            total_citations_found=len(citations),
            important_citations_count=len(citations)
        )

        if not citations:
            logger.info("No integrated citations to process")
            return result

        logger.info(f"Processing {len(citations)} integrated citations (no LLM call needed)")

        for citation_dict in citations:
            try:
                # dict를 ExtractedCitation으로 변환 (None 값 처리)
                authors = citation_dict.get("authors") or []
                year = citation_dict.get("year") or 0
                citation_text = citation_dict.get("citation_text") or ""

                # authors가 리스트가 아닌 경우 처리 (안전 체크)
                if not isinstance(authors, list):
                    logger.warning(f"Invalid authors type: {type(authors)}, converting to list")
                    authors = [str(authors)] if authors else []

                # year가 int가 아닌 경우 처리
                if not isinstance(year, int):
                    try:
                        year = int(year) if year else 0
                    except (ValueError, TypeError):
                        year = 0

                # raw_citation 생성 (PubMed 검색용)
                if authors and len(authors) > 0 and year:
                    if len(authors) > 1:
                        raw_citation = f"{authors[0]} et al., {year}"
                    else:
                        raw_citation = f"{authors[0]}, {year}"
                else:
                    raw_citation = citation_text[:100] if citation_text else ""

                # 저자도 없고 연도도 없으면 스킵
                if not authors and not year and not citation_text:
                    logger.debug("Skipping citation with no authors, year, or text")
                    continue

                citation = ExtractedCitation(
                    authors=authors,
                    year=year,
                    context=citation_dict.get("context") or "background",
                    section=citation_dict.get("section") or "discussion",
                    citation_text=citation_text,
                    importance_reason=citation_dict.get("importance_reason") or "",
                    confidence=0.9,  # 통합 추출은 높은 신뢰도
                    raw_citation=raw_citation,
                    outcome_comparison=citation_dict.get("outcome_comparison") or "",
                    direction_match=citation_dict.get("direction_match", True) if citation_dict.get("direction_match") is not None else True
                )

                # 기존 _process_single_citation 로직 재사용
                processed = await self._process_single_citation(
                    citation=citation,
                    citing_paper_id=citing_paper_id
                )

                if processed.pubmed_metadata:
                    source = processed.pubmed_metadata.source
                    if source == "crossref":
                        result.doi_fallback_successes += 1
                    elif source == "citation_basic":
                        result.basic_citations_created += 1
                    if processed.cited_paper_id:
                        result.papers_created += 1
                    if processed.relationship_created:
                        result.relationships_created += 1
                else:
                    result.pubmed_search_failures += 1

                result.processed_citations.append({
                    "raw": raw_citation,
                    "context": citation.context,
                    "found_in_pubmed": processed.pubmed_metadata is not None,
                    "enrichment_source": processed.pubmed_metadata.source if processed.pubmed_metadata else "none",
                    "paper_created": processed.cited_paper_id is not None,
                    "relationship_created": processed.relationship_created
                })

                # v7.6: JSON 저장용 상세 데이터 (PubMed abstract 포함)
                citation_detail = {
                    "authors": citation.authors,
                    "year": citation.year,
                    "context": citation.context,
                    "section": citation.section,
                    "citation_text": citation.citation_text,
                    "importance_reason": citation.importance_reason,
                    "outcome_comparison": citation.outcome_comparison,
                    "direction_match": citation.direction_match,
                    "pubmed_found": processed.pubmed_metadata is not None,
                    "enrichment_source": processed.pubmed_metadata.source if processed.pubmed_metadata else "none",
                }

                # PubMed에서 찾은 경우 상세 정보 추가
                if processed.pubmed_metadata:
                    pm = processed.pubmed_metadata
                    citation_detail.update({
                        "pmid": pm.pmid,
                        "doi": pm.doi,
                        "title": pm.title,
                        "journal": pm.journal,
                        "abstract": pm.abstract,  # PubMed abstract 포함
                        "mesh_terms": pm.mesh_terms,
                        "publication_types": pm.publication_types,
                        "cited_paper_id": processed.cited_paper_id,
                        "confidence": pm.confidence,
                    })

                result.citations_data.append(citation_detail)

            except Exception as e:
                logger.warning(f"Error processing integrated citation: {e}")
                result.errors.append(str(e))

        logger.info(
            f"Integrated citations processed: {result.papers_created} papers, "
            f"{result.relationships_created} CITES relations, "
            f"{result.pubmed_search_failures} PubMed failures"
        )

        return result


# Convenience function
async def process_important_citations(
    citing_paper_id: str,
    discussion_text: str,
    results_text: str = "",
    main_findings: Optional[list[str]] = None,
    provider: Optional[str] = None,
    pubmed_email: Optional[str] = None,
    neo4j_client: Optional[Neo4jClient] = None,
    # 레거시 호환성
    gemini_api_key: Optional[str] = None
) -> CitationProcessingResult:
    """중요 인용 처리 편의 함수.

    환경변수 LLM_PROVIDER에 따라 Claude 또는 Gemini를 자동 선택합니다.

    Args:
        citing_paper_id: 인용하는 논문 ID
        discussion_text: Discussion 섹션 텍스트
        results_text: Results 섹션 텍스트
        main_findings: 논문의 주요 발견사항
        provider: LLM 제공자 ("claude" 또는 "gemini"). None이면 환경변수 사용.
        pubmed_email: PubMed 연락처 이메일
        neo4j_client: Neo4j 클라이언트
        gemini_api_key: (레거시) Gemini API 키 - 사용 권장하지 않음

    Returns:
        CitationProcessingResult: 처리 결과

    Example:
        # 환경변수 기반 자동 선택 (권장)
        result = await process_important_citations(
            citing_paper_id="paper_123",
            discussion_text="Our findings...",
            neo4j_client=client
        )

        # 또는 특정 provider 지정
        result = await process_important_citations(
            citing_paper_id="paper_123",
            discussion_text="Our findings...",
            provider="gemini",
            neo4j_client=client
        )
    """
    processor = ImportantCitationProcessor(
        provider=provider,
        pubmed_email=pubmed_email,
        neo4j_client=neo4j_client,
        gemini_api_key=gemini_api_key  # 레거시 호환성
    )

    return await processor.process_paper_citations(
        citing_paper_id=citing_paper_id,
        discussion_text=discussion_text,
        results_text=results_text,
        main_findings=main_findings
    )
