"""Spine Graph Schema and Cypher Templates.

This module defines the complete Neo4j graph schema for the Spine GraphRAG system,
including node labels, relationship types, indexes, constraints, and Cypher query templates.

The schema supports:
- Core medical entities: Paper, Pathology, Anatomy, Intervention, Outcome, Chunk
- Extended entities: Concept, Technique, Recommendation, Implant, Complication, etc.
- Hierarchical taxonomies: Intervention IS_A relationships
- Evidence-based relationships: AFFECTS with statistical properties
- Paper-to-paper relationships: CITES, SUPPORTS, CONTRADICTS, EXTENDS, etc.
- Vector indexes: Neo4j HNSW for semantic search
- SNOMED CT: Medical ontology codes for terminology standardization
"""

from typing import Any

from .enums import (
    SpineSubDomain,
    EvidenceLevel,
    StudyDesign,
    OutcomeType,
    InterventionCategory,
    PaperRelationType,
    DocumentType,
    EntityCategory,
    CitationContext,
)
from .core_nodes import (
    PaperNode,
    ChunkNode,
    PathologyNode,
    AnatomyNode,
    InterventionNode,
    OutcomeNode,
)
from .extended_nodes import (
    ConceptNode,
    TechniqueNode,
    RecommendationNode,
    InstrumentNode,
    ImplantNode,
    ComplicationNode,
    DrugNode,
    SurgicalStepNode,
    OutcomeMeasureNode,
    RadiographicParameterNode,
    PredictionModelNode,
    RiskFactorNode,
    PatientCohortNode,
    FollowUpNode,
    CostNode,
    QualityMetricNode,
)
from .relationships import (
    StudiesRelation,
    HasChunkRelation,
    LocatedAtRelation,
    InvestigatesRelation,
    TreatsRelation,
    AffectsRelation,
    IsARelation,
    PaperRelation,
    CitesRelationship,
    PaperRelationship,
    CausesRelation,
    HasRiskFactorRelation,
    PredictsRelation,
    CorrelatesRelation,
    UsesDeviceRelation,
    HasCohortRelation,
    TreatedWithRelation,
    HasFollowUpRelation,
    ReportsOutcomeAtRelation,
    ReportsCostRelation,
    CostAssociatedWithRelation,
    HasQualityMetricRelation,
)


class SpineGraphSchema:
    """척추 그래프 스키마 관리자.

    Neo4j 스키마 생성 및 제약 조건 관리.
    """

    # 노드 레이블
    NODE_LABELS = [
        # Core nodes
        "Paper", "Pathology", "Anatomy", "Intervention", "Outcome", "Chunk",
        # v7.1 Extended Entity nodes
        "Concept", "Technique", "Recommendation", "Implant", "Complication",
        "Drug", "SurgicalStep", "OutcomeMeasure", "RadioParameter",
        "PredictionModel", "RiskFactor",
        # v7.2 Additional nodes
        "PatientCohort", "FollowUp", "Cost", "QualityMetric",
    ]

    # 관계 유형
    RELATIONSHIP_TYPES = [
        # Core relationships
        "STUDIES",
        "LOCATED_AT",
        "INVOLVES",  # Paper → Anatomy
        "INVESTIGATES",
        "TREATS",
        "AFFECTS",
        "IS_A",
        "HAS_CHUNK",  # Paper → Chunk
        # Paper-to-Paper relationships
        "CITES",
        "SUPPORTS",
        "CONTRADICTS",
        "SIMILAR_TOPIC",
        "EXTENDS",
        "REPLICATES",
        # v7.1 Relationships
        "CAUSES",  # Intervention → Complication
        "HAS_RISK_FACTOR",  # Paper → RiskFactor
        "PREDICTS",  # PredictionModel → Outcome
        "USES_FEATURE",  # PredictionModel → RiskFactor
        "CORRELATES",  # RadioParameter → OutcomeMeasure
        "USES_DEVICE",  # Intervention → Implant
        "MEASURED_BY",  # Outcome → OutcomeMeasure
        # v7.2 Relationships
        "HAS_COHORT",  # Paper → PatientCohort
        "TREATED_WITH",  # PatientCohort → Intervention
        "HAS_FOLLOWUP",  # Paper → FollowUp
        "REPORTS_OUTCOME",  # FollowUp → Outcome
        "REPORTS_COST",  # Paper → Cost
        "ASSOCIATED_WITH",  # Cost → Intervention
        "HAS_QUALITY_METRIC",  # Paper → QualityMetric
    ]

    # 인덱스 정의
    INDEXES = [
        ("Paper", "paper_id"),
        ("Paper", "doi"),
        ("Paper", "pmid"),
        ("Paper", "pmc_id"),  # NEW: PubMed Central ID
        ("Paper", "year"),
        ("Paper", "sub_domain"),
        ("Paper", "evidence_level"),
        ("Paper", "study_design"),  # NEW: 연구 설계 유형
        ("Paper", "patient_age_group"),  # NEW v4.2: Patient demographics
        ("Paper", "mean_age"),  # NEW v4.2: Patient demographics
        ("Pathology", "name"),
        ("Pathology", "category"),
        ("Pathology", "snomed_code"),
        ("Anatomy", "name"),
        ("Anatomy", "region"),
        ("Intervention", "name"),
        ("Intervention", "category"),
        ("Intervention", "snomed_code"),
        ("Outcome", "name"),
        ("Outcome", "type"),
        ("Outcome", "snomed_code"),
        # Chunk indexes (v5.3 - Neo4j Vector Index)
        ("Chunk", "chunk_id"),
        ("Chunk", "paper_id"),
        ("Chunk", "tier"),
        ("Chunk", "section"),
        ("Chunk", "evidence_level"),
        # v7.1 Extended Entity indexes
        ("OutcomeMeasure", "name"),
        ("OutcomeMeasure", "category"),
        ("RadioParameter", "name"),
        ("RadioParameter", "category"),
        ("PredictionModel", "name"),
        ("PredictionModel", "prediction_target"),
        ("RiskFactor", "name"),
        ("RiskFactor", "category"),
        ("Complication", "name"),
        ("Complication", "category"),
        ("Implant", "name"),
        ("Implant", "device_type"),
        ("Drug", "name"),
        # v7.2 Additional node indexes
        ("PatientCohort", "name"),
        ("PatientCohort", "source_paper_id"),
        ("PatientCohort", "cohort_type"),
        ("FollowUp", "name"),
        ("FollowUp", "source_paper_id"),
        ("FollowUp", "timepoint_months"),
        ("Cost", "name"),
        ("Cost", "source_paper_id"),
        ("Cost", "cost_type"),
        ("QualityMetric", "name"),
        ("QualityMetric", "source_paper_id"),
        ("QualityMetric", "overall_rating"),
    ]

    # 고유 제약 조건
    UNIQUE_CONSTRAINTS = [
        ("Paper", "paper_id"),
        ("Paper", "doi"),
        ("Pathology", "name"),
        ("Anatomy", "name"),
        ("Intervention", "name"),
        ("Outcome", "name"),
        ("Chunk", "chunk_id"),  # v5.3: Chunk unique constraint
        # v7.1 unique constraints
        ("OutcomeMeasure", "name"),
        ("RadioParameter", "name"),
        ("Complication", "name"),
        ("Implant", "name"),
        ("Drug", "name"),
    ]

    @classmethod
    def get_create_constraints_cypher(cls) -> list[str]:
        """제약 조건 생성 Cypher 쿼리 목록."""
        queries = []

        for label, prop in cls.UNIQUE_CONSTRAINTS:
            # DOI는 optional이므로 IF NOT EXISTS 사용
            if prop == "doi":
                queries.append(f"""
                    CREATE CONSTRAINT {label.lower()}_{prop}_unique IF NOT EXISTS
                    FOR (n:{label})
                    REQUIRE n.{prop} IS UNIQUE
                """)
            else:
                queries.append(f"""
                    CREATE CONSTRAINT {label.lower()}_{prop}_unique IF NOT EXISTS
                    FOR (n:{label})
                    REQUIRE n.{prop} IS UNIQUE
                """)

        return queries

    @classmethod
    def get_create_indexes_cypher(cls) -> list[str]:
        """인덱스 생성 Cypher 쿼리 목록."""
        queries = []

        for label, prop in cls.INDEXES:
            queries.append(f"""
                CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS
                FOR (n:{label})
                ON (n.{prop})
            """)

        return queries

    @classmethod
    def get_create_composite_indexes_cypher(cls) -> list[str]:
        """복합 인덱스 생성 Cypher 쿼리 목록.

        복합 인덱스는 여러 속성을 함께 검색하는 쿼리 패턴을 최적화합니다.
        예: WHERE p.sub_domain = 'X' AND p.evidence_level = 'Y'

        Returns:
            복합 인덱스 생성 쿼리 목록
        """
        queries = []

        # Paper 복합 인덱스
        composite_indexes = [
            ("Paper", ["sub_domain", "evidence_level"]),  # 논문 필터링에서 자주 사용
            ("Paper", ["year", "sub_domain"]),  # 시간별 도메인 분석
            ("Intervention", ["name", "category"]),  # 수술법 분류 쿼리
            ("Intervention", ["category", "approach"]),  # 접근법 기반 필터링
            ("Outcome", ["name", "type"]),  # 결과변수 타입 기반 쿼리
        ]

        for label, props in composite_indexes:
            props_str = "_".join(props)
            index_name = f"{label.lower()}_composite_{props_str}_idx"

            # Neo4j 5.0+ composite index syntax
            queries.append(f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR (n:{label})
                ON ({", ".join([f"n.{p}" for p in props])})
            """)

        return queries

    @classmethod
    def get_create_fulltext_indexes_cypher(cls) -> list[str]:
        """전문 검색 인덱스 생성 Cypher 쿼리 목록.

        전문 검색 인덱스는 자연어 텍스트 검색을 최적화합니다.
        예: CALL db.index.fulltext.queryNodes("paper_text_search", "stenosis surgery")

        Returns:
            전문 검색 인덱스 생성 쿼리 목록
        """
        queries = []

        # Paper 전문 검색 (제목, 초록, 요약, 결론, PICO)
        # NEW: abstract_summary, main_conclusion, pico_* 필드 추가
        queries.append("""
            CREATE FULLTEXT INDEX paper_text_search IF NOT EXISTS
            FOR (n:Paper)
            ON EACH [n.title, n.abstract, n.abstract_summary, n.main_conclusion,
                     n.pico_population, n.pico_intervention, n.pico_comparison, n.pico_outcome]
        """)

        # Pathology 전문 검색 (이름, 설명)
        queries.append("""
            CREATE FULLTEXT INDEX pathology_search IF NOT EXISTS
            FOR (n:Pathology)
            ON EACH [n.name, n.description]
        """)

        # Intervention 전문 검색 (이름, 전체 이름)
        # Note: aliases는 리스트이므로 전문 검색에 포함하지 않음
        queries.append("""
            CREATE FULLTEXT INDEX intervention_search IF NOT EXISTS
            FOR (n:Intervention)
            ON EACH [n.name, n.full_name]
        """)

        return queries

    @classmethod
    def get_create_relationship_indexes_cypher(cls) -> list[str]:
        """관계 속성 인덱스 생성 Cypher 쿼리 목록.

        관계 속성 인덱스는 관계 필터링 쿼리를 최적화합니다.
        예: WHERE r.is_significant = true AND r.p_value < 0.05

        Returns:
            관계 속성 인덱스 생성 쿼리 목록
        """
        queries = []

        # AFFECTS 관계 인덱스 (통계적 유의성 필터링)
        relationship_indexes = [
            ("AFFECTS", "p_value"),  # p-value 기반 필터링
            ("AFFECTS", "is_significant"),  # 유의성 플래그 필터링
            ("AFFECTS", "direction"),  # 개선/악화 방향 필터링
            ("STUDIES", "is_primary"),  # 주 연구 대상 필터링
            ("INVESTIGATES", "is_comparison"),  # 비교 연구 필터링
            # NEW: Paper-to-Paper 관계 인덱스
            ("SUPPORTS", "confidence"),  # 지지 관계 신뢰도
            ("CONTRADICTS", "confidence"),  # 상충 관계 신뢰도
            ("SIMILAR_TOPIC", "confidence"),  # 유사 주제 신뢰도
            ("EXTENDS", "confidence"),  # 확장 연구 신뢰도
            ("REPLICATES", "confidence"),  # 재현 연구 신뢰도
        ]

        for rel_type, prop in relationship_indexes:
            index_name = f"{rel_type.lower()}_{prop}_idx"

            # Neo4j 5.0+ relationship property index syntax
            queries.append(f"""
                CREATE INDEX {index_name} IF NOT EXISTS
                FOR ()-[r:{rel_type}]-()
                ON (r.{prop})
            """)

        return queries

    @classmethod
    def get_create_vector_indexes_cypher(cls) -> list[str]:
        """벡터 인덱스 생성 Cypher 쿼리 목록 (v5.3).

        Neo4j 5.26+ Vector Index를 사용하여 HNSW 기반 벡터 검색을 지원합니다.
        임베딩 모델: OpenAI text-embedding-3-large (3072차원)

        Returns:
            벡터 인덱스 생성 쿼리 목록
        """
        queries = []

        # Chunk 벡터 인덱스 (3072차원, OpenAI text-embedding-3-large)
        queries.append("""
            CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
            FOR (c:Chunk)
            ON (c.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 3072,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)

        # Paper abstract 벡터 인덱스 (3072차원, OpenAI text-embedding-3-large)
        queries.append("""
            CREATE VECTOR INDEX paper_abstract_index IF NOT EXISTS
            FOR (p:Paper)
            ON (p.abstract_embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 3072,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)

        return queries

    @classmethod
    def get_init_taxonomy_cypher(cls) -> str:
        """수술법 Taxonomy 초기화 Cypher."""
        return """
        // ============================================================================
        // FUSION SURGERY HIERARCHY
        // ============================================================================
        MERGE (fusion:Intervention {name: 'Fusion Surgery', category: 'fusion', full_name: 'Spinal Fusion Surgery'})

        // Level 1: Fusion Subtypes
        MERGE (ibf:Intervention {name: 'Interbody Fusion', category: 'fusion', full_name: 'Interbody Fusion'})
        MERGE (plf:Intervention {name: 'Posterolateral Fusion', category: 'fusion', full_name: 'Posterolateral Fusion', aliases: ['PLF']})
        MERGE (pcf:Intervention {name: 'Posterior Cervical Fusion', category: 'fusion', full_name: 'Posterior Cervical Fusion', aliases: ['PCF']})

        MERGE (ibf)-[:IS_A {level: 1}]->(fusion)
        MERGE (plf)-[:IS_A {level: 1}]->(fusion)
        MERGE (pcf)-[:IS_A {level: 1}]->(fusion)

        // Level 2: Interbody Fusion Approaches
        MERGE (tlif:Intervention {name: 'TLIF', full_name: 'Transforaminal Lumbar Interbody Fusion', category: 'fusion', approach: 'posterior'})
        MERGE (plif:Intervention {name: 'PLIF', full_name: 'Posterior Lumbar Interbody Fusion', category: 'fusion', approach: 'posterior'})
        MERGE (alif:Intervention {name: 'ALIF', full_name: 'Anterior Lumbar Interbody Fusion', category: 'fusion', approach: 'anterior'})
        MERGE (olif:Intervention {name: 'OLIF', full_name: 'Oblique Lumbar Interbody Fusion', category: 'fusion', approach: 'lateral', aliases: ['ATP', 'OLIF51', 'OLIF25']})
        MERGE (llif:Intervention {name: 'LLIF', full_name: 'Lateral Lumbar Interbody Fusion', category: 'fusion', approach: 'lateral', aliases: ['XLIF', 'DLIF']})
        MERGE (acdf:Intervention {name: 'ACDF', full_name: 'Anterior Cervical Discectomy and Fusion', category: 'fusion', approach: 'anterior'})
        MERGE (midlf:Intervention {name: 'MIDLF', full_name: 'Midline Lumbar Interbody Fusion', category: 'fusion', approach: 'posterior'})

        MERGE (tlif)-[:IS_A {level: 2}]->(ibf)
        MERGE (plif)-[:IS_A {level: 2}]->(ibf)
        MERGE (alif)-[:IS_A {level: 2}]->(ibf)
        MERGE (olif)-[:IS_A {level: 2}]->(ibf)
        MERGE (llif)-[:IS_A {level: 2}]->(ibf)
        MERGE (acdf)-[:IS_A {level: 2}]->(ibf)
        MERGE (midlf)-[:IS_A {level: 2}]->(ibf)

        // Level 3: Specialized Fusion Techniques
        MERGE (mis_tlif:Intervention {name: 'MIS-TLIF', full_name: 'Minimally Invasive TLIF', category: 'fusion', approach: 'posterior', is_minimally_invasive: true})
        MERGE (cbt:Intervention {name: 'CBT Fusion', full_name: 'Cortical Bone Trajectory Fusion', category: 'fusion', approach: 'posterior'})

        MERGE (mis_tlif)-[:IS_A {level: 3}]->(tlif)
        MERGE (cbt)-[:IS_A {level: 3}]->(plf)

        // ============================================================================
        // DECOMPRESSION SURGERY HIERARCHY
        // ============================================================================
        MERGE (decomp:Intervention {name: 'Decompression Surgery', category: 'decompression', full_name: 'Neural Decompression'})

        // Level 1: Decompression Approaches
        MERGE (endo:Intervention {name: 'Endoscopic Surgery', category: 'decompression', is_minimally_invasive: true, full_name: 'Endoscopic Decompression'})
        MERGE (micro:Intervention {name: 'Microscopic Surgery', category: 'decompression', is_minimally_invasive: true, full_name: 'Microscopic Decompression'})
        MERGE (open_decomp:Intervention {name: 'Open Decompression', category: 'decompression', full_name: 'Open Neural Decompression'})

        MERGE (endo)-[:IS_A {level: 1}]->(decomp)
        MERGE (micro)-[:IS_A {level: 1}]->(decomp)
        MERGE (open_decomp)-[:IS_A {level: 1}]->(decomp)

        // Level 2: Endoscopic Techniques
        MERGE (ube:Intervention {name: 'UBE', full_name: 'Unilateral Biportal Endoscopic', category: 'decompression', is_minimally_invasive: true, aliases: ['BESS', 'Biportal']})
        MERGE (feld:Intervention {name: 'FELD', full_name: 'Full-Endoscopic Lumbar Discectomy', category: 'decompression', is_minimally_invasive: true, aliases: ['FEID']})
        MERGE (peld:Intervention {name: 'PELD', full_name: 'Percutaneous Endoscopic Lumbar Discectomy', category: 'decompression', is_minimally_invasive: true})
        MERGE (fess:Intervention {name: 'FESS', full_name: 'Full Endoscopic Spinal Surgery', category: 'decompression', is_minimally_invasive: true})
        MERGE (psld:Intervention {name: 'PSLD', full_name: 'Percutaneous Stenoscopic Lumbar Decompression', category: 'decompression', is_minimally_invasive: true})

        MERGE (ube)-[:IS_A {level: 2}]->(endo)
        MERGE (feld)-[:IS_A {level: 2}]->(endo)
        MERGE (peld)-[:IS_A {level: 2}]->(endo)
        MERGE (fess)-[:IS_A {level: 2}]->(endo)
        MERGE (psld)-[:IS_A {level: 2}]->(endo)

        // Level 2: Microscopic Techniques
        MERGE (med:Intervention {name: 'MED', full_name: 'Microendoscopic Discectomy', category: 'decompression', is_minimally_invasive: true})
        MERGE (micro_decomp:Intervention {name: 'Microdecompression', full_name: 'Microscopic Decompression', category: 'decompression', is_minimally_invasive: true})

        MERGE (med)-[:IS_A {level: 2}]->(micro)
        MERGE (micro_decomp)-[:IS_A {level: 2}]->(micro)

        // Level 2: Open Decompression Techniques
        MERGE (lam:Intervention {name: 'Laminectomy', full_name: 'Open Laminectomy', category: 'decompression', aliases: ['Decompressive Laminectomy']})
        MERGE (laminotomy:Intervention {name: 'Laminotomy', full_name: 'Open Laminotomy', category: 'decompression', aliases: ['Hemilaminotomy']})
        MERGE (foraminotomy:Intervention {name: 'Foraminotomy', full_name: 'Foraminal Decompression', category: 'decompression'})
        MERGE (ubd:Intervention {name: 'UBD', full_name: 'Unilateral Bilateral Decompression', category: 'decompression'})
        MERGE (ott_decomp:Intervention {name: 'Over-the-top Decompression', full_name: 'Over-the-top Decompression', category: 'decompression'})

        MERGE (lam)-[:IS_A {level: 2}]->(open_decomp)
        MERGE (laminotomy)-[:IS_A {level: 2}]->(open_decomp)
        MERGE (foraminotomy)-[:IS_A {level: 2}]->(open_decomp)
        MERGE (ubd)-[:IS_A {level: 2}]->(open_decomp)
        MERGE (ott_decomp)-[:IS_A {level: 2}]->(open_decomp)

        // ============================================================================
        // MOTION PRESERVATION HIERARCHY
        // ============================================================================
        MERGE (motion_pres:Intervention {name: 'Motion Preservation', category: 'other', full_name: 'Motion Preservation Surgery'})

        MERGE (adr:Intervention {name: 'ADR', full_name: 'Artificial Disc Replacement', category: 'other', aliases: ['TDR', 'Total Disc Replacement', 'cTDR', 'lTDR']})
        MERGE (dyn_stab:Intervention {name: 'Dynamic Stabilization', full_name: 'Dynamic Stabilization', category: 'fixation'})
        MERGE (isp_device:Intervention {name: 'Interspinous Device', full_name: 'Interspinous Process Device', category: 'fixation', aliases: ['IPD', 'ISD', 'X-STOP']})

        MERGE (adr)-[:IS_A {level: 1}]->(motion_pres)
        MERGE (dyn_stab)-[:IS_A {level: 1}]->(motion_pres)
        MERGE (isp_device)-[:IS_A {level: 1}]->(motion_pres)

        // ============================================================================
        // OSTEOTOMY HIERARCHY (Deformity Correction)
        // ============================================================================
        MERGE (osteo:Intervention {name: 'Osteotomy', category: 'osteotomy', full_name: 'Spinal Osteotomy'})

        MERGE (spo:Intervention {name: 'SPO', full_name: 'Smith-Petersen Osteotomy', category: 'osteotomy', aliases: ['Ponte Osteotomy']})
        MERGE (pso:Intervention {name: 'PSO', full_name: 'Pedicle Subtraction Osteotomy', category: 'osteotomy'})
        MERGE (vcr:Intervention {name: 'VCR', full_name: 'Vertebral Column Resection', category: 'osteotomy'})
        MERGE (cowo:Intervention {name: 'COWO', full_name: 'Three-Column Osteotomy', category: 'osteotomy', aliases: ['3-Column Osteotomy']})

        MERGE (spo)-[:IS_A {level: 1}]->(osteo)
        MERGE (pso)-[:IS_A {level: 1}]->(osteo)
        MERGE (vcr)-[:IS_A {level: 1}]->(osteo)
        MERGE (cowo)-[:IS_A {level: 1}]->(osteo)

        // ============================================================================
        // FIXATION HIERARCHY
        // ============================================================================
        MERGE (fixation:Intervention {name: 'Fixation', category: 'fixation', full_name: 'Spinal Fixation'})

        MERGE (ps_fix:Intervention {name: 'Pedicle Screw', full_name: 'Pedicle Screw Fixation', category: 'fixation'})
        MERGE (lms_fix:Intervention {name: 'Lateral Mass Screw', full_name: 'Lateral Mass Screw Fixation', category: 'fixation'})
        MERGE (c1c2_fusion:Intervention {name: 'C1-C2 Fusion', full_name: 'C1-C2 Fusion', category: 'fusion'})
        MERGE (oc_fusion:Intervention {name: 'Occipitocervical Fusion', full_name: 'Occipitocervical Fusion', category: 'fusion'})

        MERGE (ps_fix)-[:IS_A {level: 1}]->(fixation)
        MERGE (lms_fix)-[:IS_A {level: 1}]->(fixation)
        MERGE (c1c2_fusion)-[:IS_A {level: 1}]->(pcf)
        MERGE (oc_fusion)-[:IS_A {level: 1}]->(pcf)

        // ============================================================================
        // VERTEBROPLASTY/KYPHOPLASTY
        // ============================================================================
        MERGE (vert_aug:Intervention {name: 'Vertebral Augmentation', category: 'vertebroplasty', full_name: 'Vertebral Augmentation'})

        MERGE (pvp:Intervention {name: 'PVP', full_name: 'Percutaneous Vertebroplasty', category: 'vertebroplasty'})
        MERGE (pkp:Intervention {name: 'PKP', full_name: 'Percutaneous Kyphoplasty', category: 'vertebroplasty'})

        MERGE (pvp)-[:IS_A {level: 1}]->(vert_aug)
        MERGE (pkp)-[:IS_A {level: 1}]->(vert_aug)

        // ============================================================================
        // FACETECTOMY (v7.14.2 추가)
        // ============================================================================
        MERGE (facetectomy:Intervention {name: 'Facetectomy', category: 'decompression', full_name: 'Facet Joint Resection', aliases: ['Partial Facetectomy', 'Medial Facetectomy', 'Total Facetectomy']})
        MERGE (facetectomy)-[:IS_A {level: 2}]->(open_decomp)

        // ============================================================================
        // BELIF (v7.14.2 추가 - Biportal Endoscopic Lumbar Interbody Fusion)
        // ============================================================================
        MERGE (belif:Intervention {name: 'BELIF', full_name: 'Biportal Endoscopic Lumbar Interbody Fusion', category: 'fusion', approach: 'posterior', is_minimally_invasive: true, aliases: ['BE-TLIF', 'BETLIF', 'BE-LIF', 'BELF']})
        MERGE (belif)-[:IS_A {level: 3}]->(tlif)

        // ============================================================================
        // STEREOTACTIC NAVIGATION (v7.14.2 추가)
        // ============================================================================
        MERGE (nav:Intervention {name: 'Stereotactic Navigation', category: 'navigation', full_name: 'Stereotactic Navigation-Guided Surgery', aliases: ['Navigation', 'O-arm Navigation', 'CT Navigation', 'CASS']})
        MERGE (nav)-[:IS_A {level: 1}]->(fixation)

        // ============================================================================
        // CLINICAL OUTCOMES
        // ============================================================================

        // Pain Outcomes
        MERGE (:Outcome {name: 'VAS', type: 'clinical', unit: 'points', direction: 'lower_is_better', description: 'Visual Analog Scale (0-10)'})
        MERGE (:Outcome {name: 'VAS Back', type: 'clinical', unit: 'points', direction: 'lower_is_better', description: 'VAS for Back Pain'})
        MERGE (:Outcome {name: 'VAS Leg', type: 'clinical', unit: 'points', direction: 'lower_is_better', description: 'VAS for Leg Pain'})
        MERGE (:Outcome {name: 'NRS', type: 'clinical', unit: 'points', direction: 'lower_is_better', description: 'Numeric Rating Scale (0-10)'})

        // Functional Outcomes
        MERGE (:Outcome {name: 'ODI', type: 'functional', unit: '%', direction: 'lower_is_better', description: 'Oswestry Disability Index'})
        MERGE (:Outcome {name: 'NDI', type: 'functional', unit: '%', direction: 'lower_is_better', description: 'Neck Disability Index'})
        MERGE (:Outcome {name: 'JOA', type: 'functional', unit: 'points', direction: 'higher_is_better', description: 'Japanese Orthopaedic Association Score'})
        MERGE (:Outcome {name: 'mJOA', type: 'functional', unit: 'points', direction: 'higher_is_better', description: 'Modified JOA Score'})
        MERGE (:Outcome {name: 'EQ-5D', type: 'functional', unit: 'points', direction: 'higher_is_better', description: 'EuroQol 5 Dimensions'})
        MERGE (:Outcome {name: 'SF-36', type: 'functional', unit: 'points', direction: 'higher_is_better', description: 'Short Form 36'})
        MERGE (:Outcome {name: 'SRS-22', type: 'functional', unit: 'points', direction: 'higher_is_better', description: 'Scoliosis Research Society 22'})

        // ============================================================================
        // RADIOLOGICAL OUTCOMES
        // ============================================================================

        // Fusion-related
        MERGE (:Outcome {name: 'Fusion Rate', type: 'radiological', unit: '%', direction: 'higher_is_better', description: 'Solid Bony Fusion Rate'})
        MERGE (:Outcome {name: 'Cage Subsidence', type: 'radiological', unit: 'mm', direction: 'lower_is_better', description: 'Interbody Cage Subsidence'})

        // Alignment Parameters
        MERGE (:Outcome {name: 'Lordosis', type: 'radiological', unit: 'degrees', direction: 'context_dependent', description: 'Lumbar Lordosis'})
        MERGE (:Outcome {name: 'Cobb Angle', type: 'radiological', unit: 'degrees', direction: 'context_dependent', description: 'Scoliosis Cobb Angle'})
        MERGE (:Outcome {name: 'SVA', type: 'radiological', unit: 'mm', direction: 'lower_is_better', description: 'Sagittal Vertical Axis'})
        MERGE (:Outcome {name: 'PT', type: 'radiological', unit: 'degrees', direction: 'lower_is_better', description: 'Pelvic Tilt'})
        MERGE (:Outcome {name: 'PI-LL', type: 'radiological', unit: 'degrees', direction: 'lower_is_better', description: 'PI-LL Mismatch'})

        // ============================================================================
        // COMPLICATION OUTCOMES
        // ============================================================================

        MERGE (:Outcome {name: 'Complication Rate', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Overall Complications'})
        MERGE (:Outcome {name: 'Dural Tear', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Incidental Durotomy'})
        MERGE (:Outcome {name: 'Nerve Injury', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Nerve Root or Spinal Cord Injury'})
        MERGE (:Outcome {name: 'Infection Rate', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Surgical Site Infection'})
        MERGE (:Outcome {name: 'Reoperation Rate', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Reoperation within Follow-up'})
        MERGE (:Outcome {name: 'ASD', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Adjacent Segment Disease'})
        MERGE (:Outcome {name: 'PJK', type: 'complication', unit: '%', direction: 'lower_is_better', description: 'Proximal Junctional Kyphosis'})

        // ============================================================================
        // PATHOLOGIES - DEGENERATIVE
        // ============================================================================

        MERGE (:Pathology {name: 'Lumbar Stenosis', category: 'degenerative', description: 'Lumbar Spinal Stenosis', aliases: ['LSS', 'Central Stenosis']})
        MERGE (:Pathology {name: 'Cervical Stenosis', category: 'degenerative', description: 'Cervical Spinal Stenosis', aliases: ['CSS']})
        MERGE (:Pathology {name: 'Foraminal Stenosis', category: 'degenerative', description: 'Foraminal Stenosis'})
        MERGE (:Pathology {name: 'Lumbar Disc Herniation', category: 'degenerative', description: 'Lumbar Disc Herniation', aliases: ['LDH', 'HNP', 'HIVD']})
        MERGE (:Pathology {name: 'Cervical Disc Herniation', category: 'degenerative', description: 'Cervical Disc Herniation', aliases: ['CDH']})
        MERGE (:Pathology {name: 'DDD', category: 'degenerative', description: 'Degenerative Disc Disease'})
        MERGE (:Pathology {name: 'Facet Arthropathy', category: 'degenerative', description: 'Facet Joint Arthritis'})
        MERGE (:Pathology {name: 'Spondylolisthesis', category: 'degenerative', description: 'Degenerative Spondylolisthesis'})
        MERGE (:Pathology {name: 'Degenerative Scoliosis', category: 'degenerative', description: 'Degenerative Lumbar Scoliosis', aliases: ['De Novo Scoliosis']})

        // ============================================================================
        // PATHOLOGIES - DEFORMITY
        // ============================================================================

        MERGE (:Pathology {name: 'AIS', category: 'deformity', description: 'Adolescent Idiopathic Scoliosis'})
        MERGE (:Pathology {name: 'Adult Scoliosis', category: 'deformity', description: 'Adult Scoliosis'})
        MERGE (:Pathology {name: 'ASD', category: 'deformity', description: 'Adult Spinal Deformity'})
        MERGE (:Pathology {name: 'Flat Back', category: 'deformity', description: 'Flat Back Syndrome', aliases: ['Flatback']})
        MERGE (:Pathology {name: 'Kyphosis', category: 'deformity', description: 'Thoracic Kyphosis'})
        MERGE (:Pathology {name: 'Sagittal Imbalance', category: 'deformity', description: 'Sagittal Plane Imbalance'})

        // ============================================================================
        // PATHOLOGIES - TRAUMA
        // ============================================================================

        MERGE (:Pathology {name: 'Compression Fracture', category: 'trauma', description: 'Vertebral Compression Fracture', aliases: ['VCF']})
        MERGE (:Pathology {name: 'Burst Fracture', category: 'trauma', description: 'Vertebral Burst Fracture'})
        MERGE (:Pathology {name: 'Chance Fracture', category: 'trauma', description: 'Chance Fracture'})
        MERGE (:Pathology {name: 'Fracture-Dislocation', category: 'trauma', description: 'Fracture-Dislocation'})

        // ============================================================================
        // PATHOLOGIES - TUMOR
        // ============================================================================

        MERGE (:Pathology {name: 'Primary Tumor', category: 'tumor', description: 'Primary Spinal Tumor'})
        MERGE (:Pathology {name: 'Spinal Metastasis', category: 'tumor', description: 'Metastatic Spine Tumor', aliases: ['Spine Metastasis']})
        MERGE (:Pathology {name: 'Intradural Tumor', category: 'tumor', description: 'Intradural Spinal Tumor'})

        // ============================================================================
        // PATHOLOGIES - INFECTION
        // ============================================================================

        MERGE (:Pathology {name: 'Spondylodiscitis', category: 'infection', description: 'Spinal Infection'})
        MERGE (:Pathology {name: 'Epidural Abscess', category: 'infection', description: 'Spinal Epidural Abscess'})
        MERGE (:Pathology {name: 'Spinal TB', category: 'infection', description: 'Spinal Tuberculosis', aliases: ['Pott Disease']})

        // ============================================================================
        // ANATOMY - SPINE REGIONS
        // ============================================================================

        // Major Regions
        MERGE (:Anatomy {name: 'Cervical', region: 'cervical', level: 'region', description: 'Cervical Spine (C1-C7)'})
        MERGE (:Anatomy {name: 'Thoracic', region: 'thoracic', level: 'region', description: 'Thoracic Spine (T1-T12)'})
        MERGE (:Anatomy {name: 'Lumbar', region: 'lumbar', level: 'region', description: 'Lumbar Spine (L1-L5)'})
        MERGE (:Anatomy {name: 'Sacral', region: 'sacral', level: 'region', description: 'Sacrum (S1-S5)'})

        // Junctional Regions
        MERGE (:Anatomy {name: 'Cervicothoracic', region: 'junctional', level: 'region', description: 'Cervicothoracic Junction (C7-T1)'})
        MERGE (:Anatomy {name: 'Thoracolumbar', region: 'junctional', level: 'region', description: 'Thoracolumbar Junction (T12-L1)'})
        MERGE (:Anatomy {name: 'Lumbosacral', region: 'junctional', level: 'region', description: 'Lumbosacral Junction (L5-S1)'})

        // Cervical Vertebrae
        MERGE (:Anatomy {name: 'C1', region: 'cervical', level: 'vertebra', description: 'Atlas', aliases: ['Atlas']})
        MERGE (:Anatomy {name: 'C2', region: 'cervical', level: 'vertebra', description: 'Axis', aliases: ['Axis']})
        MERGE (:Anatomy {name: 'C3', region: 'cervical', level: 'vertebra', description: 'Third Cervical Vertebra'})
        MERGE (:Anatomy {name: 'C4', region: 'cervical', level: 'vertebra', description: 'Fourth Cervical Vertebra'})
        MERGE (:Anatomy {name: 'C5', region: 'cervical', level: 'vertebra', description: 'Fifth Cervical Vertebra'})
        MERGE (:Anatomy {name: 'C6', region: 'cervical', level: 'vertebra', description: 'Sixth Cervical Vertebra'})
        MERGE (:Anatomy {name: 'C7', region: 'cervical', level: 'vertebra', description: 'Seventh Cervical Vertebra'})

        // Thoracic Vertebrae (Selected key levels)
        MERGE (:Anatomy {name: 'T1', region: 'thoracic', level: 'vertebra', description: 'First Thoracic Vertebra'})
        MERGE (:Anatomy {name: 'T10', region: 'thoracic', level: 'vertebra', description: 'Tenth Thoracic Vertebra'})
        MERGE (:Anatomy {name: 'T11', region: 'thoracic', level: 'vertebra', description: 'Eleventh Thoracic Vertebra'})
        MERGE (:Anatomy {name: 'T12', region: 'thoracic', level: 'vertebra', description: 'Twelfth Thoracic Vertebra'})

        // Lumbar Vertebrae
        MERGE (:Anatomy {name: 'L1', region: 'lumbar', level: 'vertebra', description: 'First Lumbar Vertebra'})
        MERGE (:Anatomy {name: 'L2', region: 'lumbar', level: 'vertebra', description: 'Second Lumbar Vertebra'})
        MERGE (:Anatomy {name: 'L3', region: 'lumbar', level: 'vertebra', description: 'Third Lumbar Vertebra'})
        MERGE (:Anatomy {name: 'L4', region: 'lumbar', level: 'vertebra', description: 'Fourth Lumbar Vertebra'})
        MERGE (:Anatomy {name: 'L5', region: 'lumbar', level: 'vertebra', description: 'Fifth Lumbar Vertebra'})

        // Sacral Vertebrae
        MERGE (:Anatomy {name: 'S1', region: 'sacral', level: 'vertebra', description: 'First Sacral Vertebra'})
        MERGE (:Anatomy {name: 'S2', region: 'sacral', level: 'vertebra', description: 'Second Sacral Vertebra'})

        RETURN 'Taxonomy initialized with extended interventions, outcomes, pathologies, and anatomy'
        """

    @classmethod
    def get_enrich_snomed_cypher(cls) -> list[str]:
        """SNOMED 코드로 기존 노드를 보강하는 Cypher 쿼리 목록.

        spine_snomed_mappings.py의 매핑 테이블을 사용하여
        기존 Intervention, Pathology, Outcome 노드에 SNOMED 코드를 추가합니다.

        Returns:
            SNOMED 보강 쿼리 목록
        """
        queries = []

        # Intervention SNOMED enrichment
        queries.append("""
        // === INTERVENTION SNOMED CODES ===
        // Fusion procedures
        MATCH (i:Intervention {name: 'Fusion Surgery'}) SET i.snomed_code = '122465003', i.snomed_term = 'Fusion of spine'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Interbody Fusion'}) SET i.snomed_code = '609588000', i.snomed_term = 'Interbody fusion of spine'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Posterolateral Fusion'}) SET i.snomed_code = '44946007', i.snomed_term = 'Posterolateral fusion of spine'
        WITH 1 as done
        MATCH (i:Intervention {name: 'TLIF'}) SET i.snomed_code = '447764006', i.snomed_term = 'Transforaminal lumbar interbody fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'PLIF'}) SET i.snomed_code = '87031008', i.snomed_term = 'Posterior lumbar interbody fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'ALIF'}) SET i.snomed_code = '426294006', i.snomed_term = 'Anterior lumbar interbody fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'LLIF'}) SET i.snomed_code = '450436003', i.snomed_term = 'Lateral lumbar interbody fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'ACDF'}) SET i.snomed_code = '112728004', i.snomed_term = 'Anterior cervical discectomy and fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Posterior Cervical Fusion'}) SET i.snomed_code = '112729007', i.snomed_term = 'Posterior cervical fusion'
        WITH 1 as done
        MATCH (i:Intervention {name: 'C1-C2 Fusion'}) SET i.snomed_code = '44337006', i.snomed_term = 'Arthrodesis of atlantoaxial joint'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Occipitocervical Fusion'}) SET i.snomed_code = '426838003', i.snomed_term = 'Occipitocervical fusion'
        RETURN 'Fusion SNOMED codes applied'
        """)

        queries.append("""
        // Decompression procedures
        MATCH (i:Intervention {name: 'Decompression Surgery'}) SET i.snomed_code = '5765005', i.snomed_term = 'Decompression of spinal cord'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Laminectomy'}) SET i.snomed_code = '387731002', i.snomed_term = 'Laminectomy'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Laminotomy'}) SET i.snomed_code = '112737006', i.snomed_term = 'Laminotomy'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Foraminotomy'}) SET i.snomed_code = '11585007', i.snomed_term = 'Foraminotomy'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Endoscopic Surgery'}) SET i.snomed_code = '386638009', i.snomed_term = 'Endoscopic spinal procedure'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Microscopic Surgery'}) SET i.snomed_code = '387714009', i.snomed_term = 'Microsurgical technique'
        RETURN 'Decompression SNOMED codes applied'
        """)

        queries.append("""
        // Other procedures
        MATCH (i:Intervention {name: 'Osteotomy'}) SET i.snomed_code = '179097009', i.snomed_term = 'Osteotomy of spine'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Vertebral Augmentation'}) SET i.snomed_code = '447766008', i.snomed_term = 'Vertebral augmentation'
        WITH 1 as done
        MATCH (i:Intervention {name: 'PVP'}) SET i.snomed_code = '392010000', i.snomed_term = 'Percutaneous vertebroplasty'
        WITH 1 as done
        MATCH (i:Intervention {name: 'PKP'}) SET i.snomed_code = '429616001', i.snomed_term = 'Percutaneous kyphoplasty'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Fixation'}) SET i.snomed_code = '33620004', i.snomed_term = 'Instrumented fusion of spine'
        WITH 1 as done
        MATCH (i:Intervention {name: 'Pedicle Screw'}) SET i.snomed_code = '40388003', i.snomed_term = 'Insertion of pedicle screw'
        WITH 1 as done
        MATCH (i:Intervention {name: 'ADR'}) SET i.snomed_code = '428191000124105', i.snomed_term = 'Artificial disc replacement'
        RETURN 'Other procedure SNOMED codes applied'
        """)

        # v7.14.2: 신규 수술법 SNOMED enrichment
        queries.append("""
        // v7.14.2 추가: Facetectomy, BELIF, Stereotactic Navigation SNOMED codes
        MATCH (i:Intervention {name: 'Facetectomy'}) SET i.snomed_code = '900000000000121', i.snomed_term = 'Facetectomy', i.is_extension = true
        WITH 1 as done
        MATCH (i:Intervention {name: 'BELIF'}) SET i.snomed_code = '900000000000119', i.snomed_term = 'Biportal endoscopic lumbar interbody fusion', i.is_extension = true
        WITH 1 as done
        MATCH (i:Intervention {name: 'Stereotactic Navigation'}) SET i.snomed_code = '900000000000120', i.snomed_term = 'Stereotactic navigation-guided spine surgery', i.is_extension = true
        RETURN 'v7.14.2 new procedure SNOMED codes applied'
        """)

        # Pathology SNOMED enrichment
        queries.append("""
        // === PATHOLOGY SNOMED CODES ===
        // Degenerative
        MATCH (p:Pathology {name: 'Lumbar Stenosis'}) SET p.snomed_code = '18347007', p.snomed_term = 'Spinal stenosis of lumbar region'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Cervical Stenosis'}) SET p.snomed_code = '427371002', p.snomed_term = 'Spinal stenosis of cervical region'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Foraminal Stenosis'}) SET p.snomed_code = '202708005', p.snomed_term = 'Foraminal stenosis'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Lumbar Disc Herniation'}) SET p.snomed_code = '76107001', p.snomed_term = 'Prolapsed lumbar intervertebral disc'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Cervical Disc Herniation'}) SET p.snomed_code = '60022001', p.snomed_term = 'Prolapsed cervical intervertebral disc'
        WITH 1 as done
        MATCH (p:Pathology {name: 'DDD'}) SET p.snomed_code = '77547008', p.snomed_term = 'Degenerative disc disease'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Facet Arthropathy'}) SET p.snomed_code = '81680005', p.snomed_term = 'Facet joint syndrome'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Spondylolisthesis'}) SET p.snomed_code = '274152003', p.snomed_term = 'Spondylolisthesis'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Degenerative Scoliosis'}) SET p.snomed_code = '203646004', p.snomed_term = 'Degenerative scoliosis'
        RETURN 'Degenerative pathology SNOMED codes applied'
        """)

        queries.append("""
        // Deformity
        MATCH (p:Pathology {name: 'AIS'}) SET p.snomed_code = '203639008', p.snomed_term = 'Adolescent idiopathic scoliosis'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Adult Scoliosis'}) SET p.snomed_code = '111266001', p.snomed_term = 'Adult scoliosis'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Flat Back'}) SET p.snomed_code = '203672002', p.snomed_term = 'Flat back syndrome'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Kyphosis'}) SET p.snomed_code = '414564002', p.snomed_term = 'Kyphosis deformity of spine'
        WITH 1 as done
        // Trauma
        MATCH (p:Pathology {name: 'Compression Fracture'}) SET p.snomed_code = '207938004', p.snomed_term = 'Compression fracture of vertebra'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Burst Fracture'}) SET p.snomed_code = '207939007', p.snomed_term = 'Burst fracture of vertebra'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Chance Fracture'}) SET p.snomed_code = '125616002', p.snomed_term = 'Chance fracture'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Fracture-Dislocation'}) SET p.snomed_code = '125609003', p.snomed_term = 'Fracture dislocation of spine'
        RETURN 'Deformity and trauma pathology SNOMED codes applied'
        """)

        queries.append("""
        // Tumor and Infection
        MATCH (p:Pathology {name: 'Primary Tumor'}) SET p.snomed_code = '126968001', p.snomed_term = 'Primary neoplasm of vertebral column'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Spinal Metastasis'}) SET p.snomed_code = '94503003', p.snomed_term = 'Metastatic malignant neoplasm to spine'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Spondylodiscitis'}) SET p.snomed_code = '4556007', p.snomed_term = 'Spondylodiscitis'
        WITH 1 as done
        MATCH (p:Pathology {name: 'Epidural Abscess'}) SET p.snomed_code = '75607008', p.snomed_term = 'Spinal epidural abscess'
        RETURN 'Tumor and infection pathology SNOMED codes applied'
        """)

        # Outcome SNOMED enrichment
        queries.append("""
        // === OUTCOME SNOMED CODES ===
        // Pain measures
        MATCH (o:Outcome {name: 'VAS'}) SET o.snomed_code = '273903006', o.snomed_term = 'Visual analog pain scale'
        WITH 1 as done
        MATCH (o:Outcome {name: 'NRS'}) SET o.snomed_code = '1137229006', o.snomed_term = 'Numeric rating scale for pain'
        WITH 1 as done
        // Functional measures
        MATCH (o:Outcome {name: 'ODI'}) SET o.snomed_code = '273545004', o.snomed_term = 'Oswestry Disability Index'
        WITH 1 as done
        MATCH (o:Outcome {name: 'NDI'}) SET o.snomed_code = '273547007', o.snomed_term = 'Neck Disability Index'
        WITH 1 as done
        MATCH (o:Outcome {name: 'EQ-5D'}) SET o.snomed_code = '736534008', o.snomed_term = 'EQ-5D questionnaire score'
        WITH 1 as done
        MATCH (o:Outcome {name: 'SF-36'}) SET o.snomed_code = '445537008', o.snomed_term = 'Short Form 36 health survey'
        WITH 1 as done
        // Radiological measures
        MATCH (o:Outcome {name: 'Lordosis'}) SET o.snomed_code = '298003004', o.snomed_term = 'Lumbar lordosis measurement'
        WITH 1 as done
        MATCH (o:Outcome {name: 'Cobb Angle'}) SET o.snomed_code = '252495004', o.snomed_term = 'Cobb angle measurement'
        WITH 1 as done
        // Complication measures
        MATCH (o:Outcome {name: 'Complication Rate'}) SET o.snomed_code = '116223007', o.snomed_term = 'Complication of procedure'
        WITH 1 as done
        MATCH (o:Outcome {name: 'Dural Tear'}) SET o.snomed_code = '262540006', o.snomed_term = 'Tear of dura mater'
        WITH 1 as done
        MATCH (o:Outcome {name: 'Nerve Injury'}) SET o.snomed_code = '212992005', o.snomed_term = 'Injury of nerve root'
        WITH 1 as done
        MATCH (o:Outcome {name: 'Infection Rate'}) SET o.snomed_code = '128601007', o.snomed_term = 'Surgical site infection'
        RETURN 'Outcome SNOMED codes applied'
        """)

        # Anatomy SNOMED enrichment
        queries.append("""
        // === ANATOMY SNOMED CODES ===
        // Regions
        MATCH (a:Anatomy {name: 'Cervical'}) SET a.snomed_code = '122494005', a.snomed_term = 'Cervical spine structure'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'Thoracic'}) SET a.snomed_code = '122495006', a.snomed_term = 'Thoracic spine structure'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'Lumbar'}) SET a.snomed_code = '122496007', a.snomed_term = 'Lumbar spine structure'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'Sacral'}) SET a.snomed_code = '699698002', a.snomed_term = 'Structure of sacrum'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'Lumbosacral'}) SET a.snomed_code = '264940005', a.snomed_term = 'Lumbosacral region of spine'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'Thoracolumbar'}) SET a.snomed_code = '264939003', a.snomed_term = 'Thoracolumbar region of spine'
        WITH 1 as done
        // Specific vertebrae
        MATCH (a:Anatomy {name: 'C1'}) SET a.snomed_code = '14806007', a.snomed_term = 'Structure of atlas'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C2'}) SET a.snomed_code = '39976000', a.snomed_term = 'Structure of axis'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C3'}) SET a.snomed_code = '181822002', a.snomed_term = 'Third cervical vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C4'}) SET a.snomed_code = '181823007', a.snomed_term = 'Fourth cervical vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C5'}) SET a.snomed_code = '181824001', a.snomed_term = 'Fifth cervical vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C6'}) SET a.snomed_code = '181825000', a.snomed_term = 'Sixth cervical vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'C7'}) SET a.snomed_code = '181826004', a.snomed_term = 'Seventh cervical vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'T1'}) SET a.snomed_code = '181827008', a.snomed_term = 'First thoracic vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'T12'}) SET a.snomed_code = '181838003', a.snomed_term = 'Twelfth thoracic vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'L1'}) SET a.snomed_code = '181839006', a.snomed_term = 'First lumbar vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'L2'}) SET a.snomed_code = '181840008', a.snomed_term = 'Second lumbar vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'L3'}) SET a.snomed_code = '181841007', a.snomed_term = 'Third lumbar vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'L4'}) SET a.snomed_code = '181842000', a.snomed_term = 'Fourth lumbar vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'L5'}) SET a.snomed_code = '181843005', a.snomed_term = 'Fifth lumbar vertebra'
        WITH 1 as done
        MATCH (a:Anatomy {name: 'S1'}) SET a.snomed_code = '181844004', a.snomed_term = 'First sacral vertebra'
        RETURN 'Anatomy SNOMED codes applied'
        """)

        return queries

    @classmethod
    def get_fix_orphan_interventions_cypher(cls) -> list[str]:
        """고아 Intervention 노드에 IS_A 관계를 추가하는 Cypher 쿼리 목록.

        v7.14.6: 기존 데이터에서 추출된 Intervention 노드 중
        IS_A 관계가 없는 노드들을 적절한 상위 카테고리에 연결합니다.

        Returns:
            고아 노드 정비 쿼리 목록
        """
        queries = []

        # 1. Discectomy 및 Decompression 관련 수술법 정비
        queries.append("""
        // === DISCECTOMY / DECOMPRESSION 계층 정비 ===
        // Discectomy → Open Decompression
        MATCH (decomp:Intervention {name: 'Open Decompression'})
        MERGE (disc:Intervention {name: 'Discectomy'})
        ON CREATE SET disc.category = 'decompression', disc.full_name = 'Discectomy'
        MERGE (disc)-[:IS_A {level: 2}]->(decomp)

        WITH 1 as done
        // Laminoplasty → Decompression Surgery (Motion-preserving)
        MATCH (decomp_surgery:Intervention {name: 'Decompression Surgery'})
        MERGE (lp:Intervention {name: 'Laminoplasty'})
        ON CREATE SET lp.category = 'decompression', lp.full_name = 'Cervical Laminoplasty'
        ON MATCH SET lp.category = COALESCE(lp.category, 'decompression')
        MERGE (lp)-[:IS_A {level: 1}]->(decomp_surgery)

        WITH 1 as done
        // Posterior Cervical Foraminotomy → Open Decompression
        MATCH (open_decomp:Intervention {name: 'Open Decompression'})
        MERGE (pcf:Intervention {name: 'Posterior Cervical Foraminotomy'})
        ON CREATE SET pcf.category = 'decompression', pcf.full_name = 'Posterior Cervical Foraminotomy'
        ON MATCH SET pcf.category = COALESCE(pcf.category, 'decompression')
        MERGE (pcf)-[:IS_A {level: 2}]->(open_decomp)

        WITH 1 as done
        // Endoscopic Decompression → Endoscopic Surgery
        MATCH (endo:Intervention {name: 'Endoscopic Surgery'})
        MERGE (ed:Intervention {name: 'Endoscopic Decompression'})
        ON CREATE SET ed.category = 'decompression', ed.full_name = 'Endoscopic Decompression', ed.is_minimally_invasive = true
        ON MATCH SET ed.category = COALESCE(ed.category, 'decompression'), ed.is_minimally_invasive = true
        MERGE (ed)-[:IS_A {level: 2}]->(endo)

        WITH 1 as done
        // ULBD → Open Decompression (기존에 이미 있지만 확인)
        MATCH (open_decomp:Intervention {name: 'Open Decompression'})
        MATCH (ubd:Intervention {name: 'UBD'})
        MERGE (ubd)-[:IS_A {level: 2}]->(open_decomp)

        WITH 1 as done
        // BE-ULBD → UBE (Biportal Endoscopic ULBD)
        MATCH (ube:Intervention {name: 'UBE'})
        MERGE (be_ulbd:Intervention {name: 'BE-ULBD'})
        ON CREATE SET be_ulbd.category = 'decompression', be_ulbd.full_name = 'Biportal Endoscopic Unilateral Laminotomy Bilateral Decompression', be_ulbd.is_minimally_invasive = true
        MERGE (be_ulbd)-[:IS_A {level: 3}]->(ube)

        RETURN 'Discectomy/Decompression hierarchy fixed'
        """)

        # 2. Fusion 관련 추가 수술법 정비
        queries.append("""
        // === FUSION 관련 추가 수술법 정비 ===
        // Posterior Instrumented Fusion → Posterolateral Fusion
        MATCH (plf:Intervention {name: 'Posterolateral Fusion'})
        MERGE (pif:Intervention {name: 'Posterior Instrumented Fusion'})
        ON CREATE SET pif.category = 'fusion', pif.full_name = 'Posterior Instrumented Fusion'
        ON MATCH SET pif.category = COALESCE(pif.category, 'fusion')
        MERGE (pif)-[:IS_A {level: 2}]->(plf)

        WITH 1 as done
        // PLF (Posterolateral Lumbar Fusion) → Posterolateral Fusion (별칭)
        MATCH (plf_parent:Intervention {name: 'Posterolateral Fusion'})
        MERGE (plf_child:Intervention {name: 'PLF (Posterolateral Lumbar Fusion)'})
        ON CREATE SET plf_child.category = 'fusion', plf_child.full_name = 'Posterolateral Lumbar Fusion'
        MERGE (plf_child)-[:IS_A {level: 2}]->(plf_parent)

        WITH 1 as done
        // PTF → Fusion Surgery (Posterior Thoracic Fusion)
        MATCH (fusion:Intervention {name: 'Fusion Surgery'})
        MERGE (ptf:Intervention {name: 'PTF (Posterior Thoracic Fusion)'})
        ON CREATE SET ptf.category = 'fusion', ptf.full_name = 'Posterior Thoracic Fusion'
        MERGE (ptf)-[:IS_A {level: 1}]->(fusion)

        WITH 1 as done
        // CCF → Interbody Fusion (Cervical Cage Fusion)
        MATCH (ibf:Intervention {name: 'Interbody Fusion'})
        MERGE (ccf:Intervention {name: 'CCF'})
        ON CREATE SET ccf.category = 'fusion', ccf.full_name = 'Cervical Cage Fusion'
        ON MATCH SET ccf.category = COALESCE(ccf.category, 'fusion')
        MERGE (ccf)-[:IS_A {level: 2}]->(ibf)

        WITH 1 as done
        // Lumbar Fusion → Fusion Surgery (일반화)
        MATCH (fusion:Intervention {name: 'Fusion Surgery'})
        MERGE (lf:Intervention {name: 'Lumbar Fusion'})
        ON CREATE SET lf.category = 'fusion', lf.full_name = 'Lumbar Fusion'
        MERGE (lf)-[:IS_A {level: 1}]->(fusion)

        WITH 1 as done
        // Anterior Fusion → Fusion Surgery
        MATCH (fusion:Intervention {name: 'Fusion Surgery'})
        MERGE (af:Intervention {name: 'Anterior fusion'})
        ON CREATE SET af.category = 'fusion', af.full_name = 'Anterior Fusion'
        MERGE (af)-[:IS_A {level: 1}]->(fusion)

        WITH 1 as done
        // Spinopelvic Fusion → Fusion Surgery
        MATCH (fusion:Intervention {name: 'Fusion Surgery'})
        MERGE (spf:Intervention {name: 'Spinopelvic fusion'})
        ON CREATE SET spf.category = 'fusion', spf.full_name = 'Spinopelvic Fusion'
        MERGE (spf)-[:IS_A {level: 1}]->(fusion)

        RETURN 'Fusion hierarchy fixed'
        """)

        # 3. Fixation 관련 수술법 정비
        queries.append("""
        // === FIXATION 관련 수술법 정비 ===
        // Percutaneous Pedicle Screw → Pedicle Screw
        MATCH (ps:Intervention {name: 'Pedicle Screw'})
        MERGE (pps:Intervention {name: 'Percutaneous Pedicle Screw'})
        ON CREATE SET pps.category = 'fixation', pps.full_name = 'Percutaneous Pedicle Screw Fixation', pps.is_minimally_invasive = true
        ON MATCH SET pps.category = COALESCE(pps.category, 'fixation'), pps.is_minimally_invasive = true
        MERGE (pps)-[:IS_A {level: 2}]->(ps)

        WITH 1 as done
        // Robot-Assisted Surgery → Fixation (Navigation 하위)
        MATCH (nav:Intervention {name: 'Stereotactic Navigation'})
        MERGE (robot:Intervention {name: 'Robot-Assisted Surgery'})
        ON CREATE SET robot.category = 'navigation', robot.full_name = 'Robot-Assisted Spine Surgery'
        ON MATCH SET robot.category = COALESCE(robot.category, 'navigation')
        MERGE (robot)-[:IS_A {level: 2}]->(nav)

        WITH 1 as done
        // S2AI Screw → Fixation (Pelvic Fixation)
        MATCH (fixation:Intervention {name: 'Fixation'})
        MERGE (s2ai:Intervention {name: 'S2AI screw fixation'})
        ON CREATE SET s2ai.category = 'fixation', s2ai.full_name = 'S2 Alar-Iliac Screw Fixation'
        MERGE (s2ai)-[:IS_A {level: 1}]->(fixation)

        WITH 1 as done
        // Iliac Screw → Fixation
        MATCH (fixation:Intervention {name: 'Fixation'})
        MERGE (iliac:Intervention {name: 'Iliac screw fixation'})
        ON CREATE SET iliac.category = 'fixation', iliac.full_name = 'Iliac Screw Fixation'
        MERGE (iliac)-[:IS_A {level: 1}]->(fixation)

        WITH 1 as done
        // Halo Traction → Fixation (보존적)
        MATCH (fixation:Intervention {name: 'Fixation'})
        MERGE (halo:Intervention {name: 'Halo Traction'})
        ON CREATE SET halo.category = 'fixation', halo.full_name = 'Halo Traction'
        ON MATCH SET halo.category = COALESCE(halo.category, 'fixation')
        MERGE (halo)-[:IS_A {level: 1}]->(fixation)

        RETURN 'Fixation hierarchy fixed'
        """)

        # 4. Tumor Surgery 정비
        queries.append("""
        // === TUMOR SURGERY 계층 정비 ===
        // Tumor Surgery 상위 노드 생성
        MERGE (tumor_surgery:Intervention {name: 'Tumor Surgery', category: 'tumor', full_name: 'Spinal Tumor Surgery'})

        WITH tumor_surgery
        // Vertebrectomy → Tumor Surgery
        MERGE (vert:Intervention {name: 'Vertebrectomy'})
        ON CREATE SET vert.category = 'tumor', vert.full_name = 'Vertebrectomy'
        ON MATCH SET vert.category = COALESCE(vert.category, 'tumor')
        MERGE (vert)-[:IS_A {level: 1}]->(tumor_surgery)

        WITH tumor_surgery
        // Separation Surgery → Tumor Surgery
        MERGE (sep:Intervention {name: 'Separation Surgery'})
        ON CREATE SET sep.category = 'tumor', sep.full_name = 'Separation Surgery'
        ON MATCH SET sep.category = COALESCE(sep.category, 'tumor')
        MERGE (sep)-[:IS_A {level: 1}]->(tumor_surgery)

        WITH tumor_surgery
        // Debridement → Tumor Surgery (or Infection)
        MERGE (debride:Intervention {name: 'Debridement'})
        ON CREATE SET debride.category = 'tumor', debride.full_name = 'Surgical Debridement'
        ON MATCH SET debride.category = COALESCE(debride.category, 'tumor')
        MERGE (debride)-[:IS_A {level: 1}]->(tumor_surgery)

        RETURN 'Tumor surgery hierarchy created'
        """)

        # 5. Conservative Treatment 정비
        queries.append("""
        // === CONSERVATIVE TREATMENT 계층 정비 ===
        MERGE (conservative:Intervention {name: 'Conservative Treatment', category: 'conservative', full_name: 'Conservative Management'})

        WITH conservative
        // Physical Therapy → Conservative
        MERGE (pt:Intervention {name: 'Physical therapy'})
        ON CREATE SET pt.category = 'conservative', pt.full_name = 'Physical Therapy'
        MERGE (pt)-[:IS_A {level: 1}]->(conservative)

        WITH conservative
        // Physiotherapy → Conservative
        MERGE (physio:Intervention {name: 'Physiotherapy'})
        ON CREATE SET physio.category = 'conservative', physio.full_name = 'Physiotherapy'
        MERGE (physio)-[:IS_A {level: 1}]->(conservative)

        WITH conservative
        // Bracing → Conservative
        MERGE (brace:Intervention {name: 'Bracing'})
        ON CREATE SET brace.category = 'conservative', brace.full_name = 'Brace Treatment'
        MERGE (brace)-[:IS_A {level: 1}]->(conservative)

        WITH conservative
        // Conservative Management (별칭) → Conservative
        MERGE (cm:Intervention {name: 'Conservative Management'})
        ON CREATE SET cm.category = 'conservative', cm.full_name = 'Conservative Management'
        ON MATCH SET cm.category = COALESCE(cm.category, 'conservative')
        MERGE (cm)-[:IS_A {level: 1}]->(conservative)

        WITH conservative
        // Antibiotic Therapy → Conservative
        MERGE (abx:Intervention {name: 'Antibiotic therapy'})
        ON CREATE SET abx.category = 'conservative', abx.full_name = 'Antibiotic Therapy'
        MERGE (abx)-[:IS_A {level: 1}]->(conservative)

        RETURN 'Conservative treatment hierarchy created'
        """)

        # 6. Injection/Pain Management 정비
        queries.append("""
        // === INJECTION / PAIN MANAGEMENT 계층 정비 ===
        MERGE (injection:Intervention {name: 'Injection Therapy', category: 'injection', full_name: 'Spinal Injection Therapy'})

        WITH injection
        // PRP Injection → Injection
        MERGE (prp:Intervention {name: 'PRP Injection'})
        ON CREATE SET prp.category = 'injection', prp.full_name = 'Platelet-Rich Plasma Injection'
        ON MATCH SET prp.category = COALESCE(prp.category, 'injection')
        MERGE (prp)-[:IS_A {level: 1}]->(injection)

        WITH injection
        // Intradiscal Injection → Injection
        MERGE (intradiscal:Intervention {name: 'Intradiscal injection'})
        ON CREATE SET intradiscal.category = 'injection', intradiscal.full_name = 'Intradiscal Injection'
        MERGE (intradiscal)-[:IS_A {level: 1}]->(injection)

        WITH injection
        // Neuromodulation → Injection (or separate category)
        MERGE (neuro:Intervention {name: 'Neuromodulation'})
        ON CREATE SET neuro.category = 'injection', neuro.full_name = 'Neuromodulation'
        MERGE (neuro)-[:IS_A {level: 1}]->(injection)

        RETURN 'Injection/Pain Management hierarchy created'
        """)

        # 7. Cervical Upper Surgery 정비
        queries.append("""
        // === CERVICAL UPPER SPINE SURGERY 정비 ===
        // Craniocervical Junction Surgery
        MERGE (ccj:Intervention {name: 'Craniocervical Surgery', category: 'fusion', full_name: 'Craniocervical Junction Surgery'})

        WITH ccj
        // C1/2 Posterior Fusion → CCJ Surgery
        MERGE (c12:Intervention {name: 'C1/2 posterior fusion'})
        ON CREATE SET c12.category = 'fusion', c12.full_name = 'C1-C2 Posterior Fusion'
        MERGE (c12)-[:IS_A {level: 1}]->(ccj)

        WITH ccj
        // Posterior C1-C2 Screw Fixation → CCJ Surgery
        MERGE (c12_screw:Intervention {name: 'Posterior C1-C2 screw fixation'})
        ON CREATE SET c12_screw.category = 'fusion', c12_screw.full_name = 'Posterior C1-C2 Screw Fixation'
        MERGE (c12_screw)-[:IS_A {level: 1}]->(ccj)

        WITH ccj
        // Craniocervical Stabilization → CCJ Surgery
        MERGE (stab:Intervention {name: 'Craniocervical stabilization'})
        ON CREATE SET stab.category = 'fusion', stab.full_name = 'Craniocervical Stabilization'
        MERGE (stab)-[:IS_A {level: 1}]->(ccj)

        WITH ccj
        // Transoral/Transnasal Approaches
        MERGE (transoral:Intervention {name: 'Transoral Approach', category: 'decompression', full_name: 'Transoral Approach'})
        MERGE (to_odontoid:Intervention {name: 'Transoral odontoidectomy'})
        ON CREATE SET to_odontoid.category = 'decompression', to_odontoid.full_name = 'Transoral Odontoidectomy'
        MERGE (to_odontoid)-[:IS_A {level: 1}]->(transoral)

        WITH transoral
        MERGE (tn_odontoid:Intervention {name: 'Transnasal odontoidectomy'})
        ON CREATE SET tn_odontoid.category = 'decompression', tn_odontoid.full_name = 'Transnasal Odontoidectomy'
        MERGE (tn_odontoid)-[:IS_A {level: 1}]->(transoral)

        RETURN 'Craniocervical surgery hierarchy created'
        """)

        # 8. Radiation/Oncology 정비
        queries.append("""
        // === RADIATION/ONCOLOGY 정비 ===
        MERGE (radiation:Intervention {name: 'Radiation Therapy', category: 'radiation', full_name: 'Spine Radiation Therapy'})

        WITH radiation
        MERGE (rt:Intervention {name: 'Radiotherapy'})
        ON CREATE SET rt.category = 'radiation', rt.full_name = 'Radiotherapy'
        MERGE (rt)-[:IS_A {level: 1}]->(radiation)

        WITH radiation
        MERGE (sbrt:Intervention {name: 'SBRT'})
        ON CREATE SET sbrt.category = 'radiation', sbrt.full_name = 'Stereotactic Body Radiation Therapy'
        MERGE (sbrt)-[:IS_A {level: 1}]->(radiation)

        WITH radiation
        MERGE (sabr:Intervention {name: 'SABR'})
        ON CREATE SET sabr.category = 'radiation', sabr.full_name = 'Stereotactic Ablative Radiotherapy'
        MERGE (sabr)-[:IS_A {level: 1}]->(radiation)

        RETURN 'Radiation therapy hierarchy created'
        """)

        return queries

    @classmethod
    def get_fix_orphan_pathologies_cypher(cls) -> list[str]:
        """고아 Pathology 노드에 카테고리를 할당하는 Cypher 쿼리 목록.

        v7.14.6: 기존 데이터에서 추출된 Pathology 노드 중
        category가 없는 노드들을 적절한 카테고리로 분류합니다.

        Returns:
            고아 노드 정비 쿼리 목록
        """
        queries = []

        # 1. Degenerative 카테고리
        queries.append("""
        // === DEGENERATIVE PATHOLOGY 카테고리 정비 ===
        // Myelopathy
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Myelopathy' OR p.name CONTAINS 'myelopathy'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Radiculopathy
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Radiculopathy' OR p.name CONTAINS 'radiculopathy'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Herniated Disc
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Herniated' OR p.name CONTAINS 'herniated'
           OR p.name CONTAINS 'Herniation' OR p.name CONTAINS 'HNP'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Spondylosis
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'spondylosis' OR p.name CONTAINS 'Spondylosis'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Disc degeneration
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Disc degeneration' OR p.name CONTAINS 'disc degeneration'
           OR p.name CONTAINS 'Degenerative disc'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Claudication
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'claudication' OR p.name CONTAINS 'Claudication'
        SET p.category = 'degenerative'

        WITH 1 as done
        // Neurogenic
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Neurogenic' OR p.name CONTAINS 'neurogenic'
        SET p.category = 'degenerative'

        RETURN 'Degenerative pathologies categorized'
        """)

        # 2. Deformity 카테고리
        queries.append("""
        // === DEFORMITY PATHOLOGY 카테고리 정비 ===
        // Scoliosis
        MATCH (p:Pathology)
        WHERE (p.name CONTAINS 'scoliosis' OR p.name CONTAINS 'Scoliosis')
          AND p.category IS NULL
        SET p.category = 'deformity'

        WITH 1 as done
        // PJK / DJK / Junctional
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'PJK' OR p.name CONTAINS 'DJK'
           OR p.name CONTAINS 'Junctional' OR p.name CONTAINS 'junctional'
        SET p.category = 'deformity'

        WITH 1 as done
        // Sagittal Imbalance
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Sagittal' OR p.name CONTAINS 'sagittal'
           OR p.name CONTAINS 'Imbalance' OR p.name CONTAINS 'imbalance'
        SET p.category = 'deformity'

        WITH 1 as done
        // Adjacent Segment Disease
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Adjacent' OR p.name CONTAINS 'adjacent'
        SET p.category = 'deformity'

        WITH 1 as done
        // Flatback / Kyphosis
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Flatback' OR p.name CONTAINS 'flatback'
           OR (p.name CONTAINS 'Kyphosis' AND p.category IS NULL)
        SET p.category = 'deformity'

        RETURN 'Deformity pathologies categorized'
        """)

        # 3. Instability 카테고리
        queries.append("""
        // === INSTABILITY PATHOLOGY 카테고리 정비 ===
        // Instability
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Instability' OR p.name CONTAINS 'instability'
        SET p.category = 'instability'

        WITH 1 as done
        // Atlantoaxial
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Atlantoaxial' OR p.name CONTAINS 'atlantoaxial'
           OR p.name CONTAINS 'C1-C2' OR p.name CONTAINS 'AAI'
        SET p.category = 'instability'

        WITH 1 as done
        // Basilar Invagination
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Basilar' OR p.name CONTAINS 'basilar'
        SET p.category = 'instability'

        WITH 1 as done
        // Pseudarthrosis / Nonunion
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Pseudarthrosis' OR p.name CONTAINS 'pseudarthrosis'
           OR p.name CONTAINS 'Nonunion' OR p.name CONTAINS 'nonunion'
        SET p.category = 'instability'

        RETURN 'Instability pathologies categorized'
        """)

        # 4. Trauma 카테고리
        queries.append("""
        // === TRAUMA PATHOLOGY 카테고리 정비 ===
        // Fracture
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Fracture' OR p.name CONTAINS 'fracture'
        SET p.category = 'trauma'

        WITH 1 as done
        // Dislocation
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Dislocation' OR p.name CONTAINS 'dislocation'
        SET p.category = 'trauma'

        WITH 1 as done
        // Spinal Cord Injury
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Spinal cord injury' OR p.name CONTAINS 'SCI'
        SET p.category = 'trauma'

        RETURN 'Trauma pathologies categorized'
        """)

        # 5. Tumor 카테고리
        queries.append("""
        // === TUMOR PATHOLOGY 카테고리 정비 ===
        // Metastatic
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Metasta' OR p.name CONTAINS 'metasta'
        SET p.category = 'tumor'

        WITH 1 as done
        // Tumor / Neoplasm
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Tumor' OR p.name CONTAINS 'tumor'
           OR p.name CONTAINS 'Neoplasm' OR p.name CONTAINS 'neoplasm'
        SET p.category = 'tumor'

        WITH 1 as done
        // Cancer / Malignancy
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Cancer' OR p.name CONTAINS 'cancer'
           OR p.name CONTAINS 'Malignan' OR p.name CONTAINS 'malignan'
        SET p.category = 'tumor'

        WITH 1 as done
        // Myeloma
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Myeloma' OR p.name CONTAINS 'myeloma'
        SET p.category = 'tumor'

        RETURN 'Tumor pathologies categorized'
        """)

        # 6. Infection 카테고리
        queries.append("""
        // === INFECTION PATHOLOGY 카테고리 정비 ===
        // SSI / Surgical Site Infection
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'SSI' OR p.name CONTAINS 'Surgical site infection'
           OR p.name CONTAINS 'Infection' OR p.name CONTAINS 'infection'
        SET p.category = 'infection'

        WITH 1 as done
        // Osteomyelitis
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Osteomyelitis' OR p.name CONTAINS 'osteomyelitis'
        SET p.category = 'infection'

        WITH 1 as done
        // Discitis
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Discitis' OR p.name CONTAINS 'discitis'
        SET p.category = 'infection'

        RETURN 'Infection pathologies categorized'
        """)

        # 7. Metabolic/Systemic 카테고리
        queries.append("""
        // === METABOLIC/SYSTEMIC PATHOLOGY 카테고리 정비 ===
        // Osteoporosis
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Osteoporosis' OR p.name CONTAINS 'osteoporosis'
           OR p.name CONTAINS 'Osteopenia' OR p.name CONTAINS 'osteopenia'
        SET p.category = 'metabolic'

        WITH 1 as done
        // Rheumatoid / Ankylosing
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'Rheumatoid' OR p.name CONTAINS 'rheumatoid'
           OR p.name CONTAINS 'Ankylosing' OR p.name CONTAINS 'ankylosing'
           OR p.name CONTAINS 'Arthritis' OR p.name CONTAINS 'arthritis'
        SET p.category = 'metabolic'

        WITH 1 as done
        // DISH / OPLL
        MATCH (p:Pathology)
        WHERE p.name CONTAINS 'DISH' OR p.name CONTAINS 'OPLL'
           OR p.name CONTAINS 'Ossification'
        SET p.category = 'metabolic'

        RETURN 'Metabolic pathologies categorized'
        """)

        return queries

    @classmethod
    def get_fix_orphan_outcomes_cypher(cls) -> list[str]:
        """고아 Outcome 노드에 type을 할당하는 Cypher 쿼리 목록.

        v7.14.6: 기존 데이터에서 추출된 Outcome 노드 중
        type이 없는 노드들을 적절한 타입으로 분류합니다.

        Returns:
            고아 노드 정비 쿼리 목록
        """
        queries = []

        # 1. Clinical (Pain) Outcomes
        queries.append("""
        // === CLINICAL (PAIN) OUTCOME 타입 정비 ===
        // VAS variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'VAS' OR o.name CONTAINS 'Visual Analog'
        SET o.type = 'clinical', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // NRS variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'NRS' OR o.name CONTAINS 'Numeric Rating'
        SET o.type = 'clinical', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Pain related
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Pain' OR o.name CONTAINS 'pain'
        SET o.type = COALESCE(o.type, 'clinical')

        RETURN 'Clinical pain outcomes categorized'
        """)

        # 2. Functional Outcomes
        queries.append("""
        // === FUNCTIONAL OUTCOME 타입 정비 ===
        // ODI variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'ODI' OR o.name CONTAINS 'Oswestry'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // NDI variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'NDI' OR o.name CONTAINS 'Neck Disability'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // JOA variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'JOA' OR o.name CONTAINS 'Japanese Ortho'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // EQ-5D variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'EQ-5D' OR o.name CONTAINS 'EuroQol'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // SF-36/SF-12 variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'SF-36' OR o.name CONTAINS 'SF-12'
           OR o.name CONTAINS 'SF12' OR o.name CONTAINS 'SF36'
           OR o.name CONTAINS 'Short Form'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // SRS variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'SRS-22' OR o.name CONTAINS 'SRS-'
           OR o.name CONTAINS 'Scoliosis Research'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // JOACMEQ variants
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'JOACMEQ'
        SET o.type = 'functional', o.direction = COALESCE(o.direction, 'higher_is_better')

        RETURN 'Functional outcomes categorized'
        """)

        # 3. Radiological Outcomes
        queries.append("""
        // === RADIOLOGICAL OUTCOME 타입 정비 ===
        // Fusion Rate
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Fusion Rate' OR o.name CONTAINS 'fusion rate'
        SET o.type = 'radiological', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // Subsidence
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Subsidence' OR o.name CONTAINS 'subsidence'
        SET o.type = 'radiological', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Cobb Angle
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Cobb' OR o.name CONTAINS 'cobb'
        SET o.type = 'radiological'

        WITH 1 as done
        // Lordosis / Kyphosis
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Lordosis' OR o.name CONTAINS 'lordosis'
           OR o.name CONTAINS 'Kyphosis' OR o.name CONTAINS 'kyphosis'
        SET o.type = 'radiological'

        WITH 1 as done
        // SVA (Sagittal Vertical Axis)
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'SVA' OR o.name CONTAINS 'Sagittal Vertical'
        SET o.type = 'radiological', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // PT (Pelvic Tilt)
        MATCH (o:Outcome)
        WHERE o.name = 'PT' OR o.name CONTAINS 'Pelvic Tilt'
        SET o.type = 'radiological'

        WITH 1 as done
        // PI-LL
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'PI-LL' OR o.name CONTAINS 'PI LL'
        SET o.type = 'radiological', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Disc Height
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Disc Height' OR o.name CONTAINS 'disc height'
        SET o.type = 'radiological'

        RETURN 'Radiological outcomes categorized'
        """)

        # 4. Complication Outcomes
        queries.append("""
        // === COMPLICATION OUTCOME 타입 정비 ===
        // Dural Tear
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Dural' OR o.name CONTAINS 'dural'
           OR o.name CONTAINS 'Durotomy' OR o.name CONTAINS 'CSF'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Infection
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Infection' OR o.name CONTAINS 'infection'
           OR o.name CONTAINS 'SSI'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Reoperation
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Reoperation' OR o.name CONTAINS 'reoperation'
           OR o.name CONTAINS 'Revision' OR o.name CONTAINS 'revision'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Complication Rate
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Complication' OR o.name CONTAINS 'complication'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Mortality
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Mortality' OR o.name CONTAINS 'mortality'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Nerve Injury / Neurological
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Nerve' OR o.name CONTAINS 'nerve'
           OR o.name CONTAINS 'Neurological' OR o.name CONTAINS 'Deficit'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // PJK/ASD
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'PJK' OR o.name CONTAINS 'ASD'
           OR o.name CONTAINS 'Adjacent' OR o.name CONTAINS 'Junctional'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Pseudarthrosis / Nonunion
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Pseudarthrosis' OR o.name CONTAINS 'Nonunion'
           OR o.name CONTAINS 'nonunion'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Hematoma
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Hematoma' OR o.name CONTAINS 'hematoma'
        SET o.type = 'complication', o.direction = COALESCE(o.direction, 'lower_is_better')

        RETURN 'Complication outcomes categorized'
        """)

        # 5. Operative Outcomes
        queries.append("""
        // === OPERATIVE OUTCOME 타입 정비 ===
        // Blood Loss / EBL
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Blood Loss' OR o.name CONTAINS 'blood loss'
           OR o.name CONTAINS 'EBL'
        SET o.type = 'operative', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Operation Time
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Operation Time' OR o.name CONTAINS 'Operative Time'
           OR o.name CONTAINS 'Operating Time' OR o.name CONTAINS 'Surgical time'
        SET o.type = 'operative', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Hospital Stay / Length of Stay
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Hospital Stay' OR o.name CONTAINS 'Length of Stay'
           OR o.name CONTAINS 'LOS' OR o.name CONTAINS 'LoS'
        SET o.type = 'operative', o.direction = COALESCE(o.direction, 'lower_is_better')

        WITH 1 as done
        // Fluoroscopy
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Fluoroscopy' OR o.name CONTAINS 'fluoroscopy'
           OR o.name CONTAINS 'Radiation' OR o.name CONTAINS 'X-ray'
        SET o.type = 'operative', o.direction = COALESCE(o.direction, 'lower_is_better')

        RETURN 'Operative outcomes categorized'
        """)

        # 6. Model/Accuracy Outcomes (ML/AI)
        queries.append("""
        // === MODEL/ACCURACY OUTCOME 타입 정비 ===
        // AUC / ROC
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'AUC' OR o.name CONTAINS 'ROC'
           OR o.name CONTAINS 'AUROC' OR o.name CONTAINS 'AUPRC'
        SET o.type = 'model_performance', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // Accuracy / Sensitivity / Specificity
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Accuracy' OR o.name CONTAINS 'accuracy'
           OR o.name CONTAINS 'Sensitivity' OR o.name CONTAINS 'Specificity'
           OR o.name CONTAINS 'Precision' OR o.name CONTAINS 'Recall'
        SET o.type = 'model_performance', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // Dice / IoU
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'Dice' OR o.name CONTAINS 'DSC'
           OR o.name CONTAINS 'IoU' OR o.name CONTAINS 'Jaccard'
        SET o.type = 'model_performance', o.direction = COALESCE(o.direction, 'higher_is_better')

        WITH 1 as done
        // F1 Score
        MATCH (o:Outcome)
        WHERE o.name CONTAINS 'F1' OR o.name CONTAINS 'F-1'
        SET o.type = 'model_performance', o.direction = COALESCE(o.direction, 'higher_is_better')

        RETURN 'Model performance outcomes categorized'
        """)

        return queries


# ============================================================================
# Cypher Query Templates
# ============================================================================

class CypherTemplates:
    """자주 사용되는 Cypher 쿼리 템플릿."""

    # 논문 생성/업데이트
    MERGE_PAPER = """
    MERGE (p:Paper {paper_id: $paper_id})
    SET p += $properties
    RETURN p
    """

    # 논문 → 질환 관계 (v7.9: SNOMED 지원 추가)
    CREATE_STUDIES_RELATION = """
    MATCH (p:Paper {paper_id: $paper_id})
    // 기존 Pathology에서 snomed_code 조회 (fallback용)
    OPTIONAL MATCH (existing:Pathology {name: $pathology_name})
    WHERE existing.snomed_code IS NOT NULL
    WITH p, existing.snomed_code AS existing_snomed_code,
         existing.snomed_term AS existing_snomed_term
    // Pathology 생성/머지 (파라미터 SNOMED 우선, 기존값 fallback)
    MERGE (path:Pathology {name: $pathology_name})
    ON CREATE SET path.snomed_code = COALESCE($snomed_code, existing_snomed_code),
                  path.snomed_term = COALESCE($snomed_term, existing_snomed_term)
    ON MATCH SET path.snomed_code = COALESCE(path.snomed_code, $snomed_code, existing_snomed_code),
                 path.snomed_term = COALESCE(path.snomed_term, $snomed_term, existing_snomed_term)
    MERGE (p)-[r:STUDIES]->(path)
    SET r.is_primary = $is_primary
    RETURN p, r, path
    """

    # 논문 → 수술법 관계 (파라미터 SNOMED 우선, Taxonomy에서 fallback)
    CREATE_INVESTIGATES_RELATION = """
    MATCH (p:Paper {paper_id: $paper_id})
    // 기존 Taxonomy에서 category, snomed_code 조회 (fallback용)
    OPTIONAL MATCH (existing:Intervention {name: $intervention_name})
    WHERE existing.category IS NOT NULL OR existing.snomed_code IS NOT NULL
    WITH p, existing.category AS taxonomy_category,
         existing.snomed_code AS taxonomy_snomed_code,
         existing.snomed_term AS taxonomy_snomed_term
    // Intervention 생성/머지 (파라미터 SNOMED 우선, Taxonomy fallback)
    MERGE (i:Intervention {name: $intervention_name})
    ON CREATE SET i.category = COALESCE($category, taxonomy_category),
                  i.snomed_code = COALESCE($snomed_code, taxonomy_snomed_code),
                  i.snomed_term = COALESCE($snomed_term, taxonomy_snomed_term)
    ON MATCH SET i.category = COALESCE(i.category, $category, taxonomy_category),
                 i.snomed_code = COALESCE(i.snomed_code, $snomed_code, taxonomy_snomed_code),
                 i.snomed_term = COALESCE(i.snomed_term, $snomed_term, taxonomy_snomed_term)
    MERGE (p)-[r:INVESTIGATES]->(i)
    SET r.is_comparison = $is_comparison
    RETURN p, r, i
    """

    # 수술법 → 질환 치료 관계 (v7.16.1: TREATS 구현)
    CREATE_TREATS_RELATION = """
    MATCH (i:Intervention {name: $intervention_name})
    MERGE (path:Pathology {name: $pathology_name})
    MERGE (i)-[r:TREATS]->(path)
    SET r.indication = COALESCE($indication, r.indication, ''),
        r.contraindication = COALESCE($contraindication, r.contraindication, ''),
        r.indication_level = COALESCE($indication_level, r.indication_level, ''),
        r.source_paper_id = $source_paper_id
    RETURN i, r, path
    """

    # 수술법 → 결과 관계 (통계 포함, v7.9: SNOMED 지원)
    CREATE_AFFECTS_RELATION = """
    MATCH (i:Intervention {name: $intervention_name})
    // 기존 Outcome에서 snomed_code 조회 (fallback용)
    OPTIONAL MATCH (existing:Outcome {name: $outcome_name})
    WHERE existing.snomed_code IS NOT NULL
    WITH i, existing.snomed_code AS existing_snomed_code,
         existing.snomed_term AS existing_snomed_term
    // Outcome 생성/머지 (파라미터 SNOMED 우선, 기존값 fallback)
    MERGE (o:Outcome {name: $outcome_name})
    ON CREATE SET o.snomed_code = COALESCE($snomed_code, existing_snomed_code),
                  o.snomed_term = COALESCE($snomed_term, existing_snomed_term)
    ON MATCH SET o.snomed_code = COALESCE(o.snomed_code, $snomed_code, existing_snomed_code),
                 o.snomed_term = COALESCE(o.snomed_term, $snomed_term, existing_snomed_term)
    MERGE (i)-[r:AFFECTS]->(o)
    SET r += $properties
    RETURN i, r, o
    """

    # 수술법 계층 탐색
    GET_INTERVENTION_HIERARCHY = """
    MATCH (i:Intervention {name: $intervention_name})
    OPTIONAL MATCH path = (i)-[:IS_A*1..5]->(parent:Intervention)
    RETURN i, collect(nodes(path)) as hierarchy
    """

    # 수술법 하위 항목 탐색
    GET_INTERVENTION_CHILDREN = """
    MATCH (parent:Intervention {name: $intervention_name})<-[:IS_A*1..3]-(child:Intervention)
    RETURN child.name as name, child.full_name as full_name
    """

    # 수술법 → 결과 검색 (효과 있는 것)
    SEARCH_EFFECTIVE_INTERVENTIONS = """
    MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: $outcome_name})
    WHERE a.is_significant = true AND a.direction = 'improved'
    RETURN i.name as intervention, a.value as value, a.p_value as p_value,
           a.source_paper_id as source
    ORDER BY a.p_value ASC
    """

    # 질환별 수술법 검색
    SEARCH_INTERVENTIONS_FOR_PATHOLOGY = """
    MATCH (i:Intervention)-[:TREATS]->(path:Pathology {name: $pathology_name})
    OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
    WHERE a.is_significant = true
    RETURN i.name as intervention, collect({outcome: o.name, value: a.value}) as outcomes
    """

    # 논문 간 관계 검색
    GET_PAPER_RELATIONS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:SUPPORTS|CONTRADICTS]-(other:Paper)
    RETURN type(r) as relation_type, other.paper_id as related_paper,
           other.title as title, r.confidence as confidence, r.evidence as evidence
    """

    # 상충 결과 검색
    FIND_CONFLICTING_RESULTS = """
    MATCH (i:Intervention)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2:Intervention)
    WHERE i.name = $intervention_name
      AND a1.direction <> a2.direction
      AND a1.is_significant = true AND a2.is_significant = true
    RETURN i.name as intervention1, i2.name as intervention2,
           o.name as outcome, a1.direction as dir1, a2.direction as dir2,
           a1.source_paper_id as paper1, a2.source_paper_id as paper2
    """

    # 논문 → 해부학 위치 관계 (Paper → Anatomy)
    CREATE_INVOLVES_RELATION = """
    MATCH (p:Paper {paper_id: $paper_id})
    MERGE (a:Anatomy {name: $anatomy_name})
    ON CREATE SET a.level = $level, a.region = $region
    MERGE (p)-[r:INVOLVES]->(a)
    RETURN p, r, a
    """

    # ============================================================================
    # Paper-to-Paper Relationship Templates (NEW - v3.1+)
    # ============================================================================

    # 논문 간 관계 생성 (Generic)
    CREATE_PAPER_RELATIONSHIP = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    CALL apoc.create.relationship(source, $relation_type, $properties, target) YIELD rel
    RETURN source, rel, target
    """

    # SUPPORTS 관계 생성
    CREATE_SUPPORTS_RELATION = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    MERGE (source)-[r:SUPPORTS]->(target)
    SET r += $properties
    RETURN source, r, target
    """

    # CONTRADICTS 관계 생성
    CREATE_CONTRADICTS_RELATION = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    MERGE (source)-[r:CONTRADICTS]->(target)
    SET r += $properties
    RETURN source, r, target
    """

    # SIMILAR_TOPIC 관계 생성 (임베딩 기반)
    CREATE_SIMILAR_TOPIC_RELATION = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    MERGE (source)-[r:SIMILAR_TOPIC]-(target)
    SET r += $properties
    RETURN source, r, target
    """

    # EXTENDS 관계 생성 (후속 연구)
    CREATE_EXTENDS_RELATION = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    MERGE (source)-[r:EXTENDS]->(target)
    SET r += $properties
    RETURN source, r, target
    """

    # REPLICATES 관계 생성 (재현 연구)
    CREATE_REPLICATES_RELATION = """
    MATCH (source:Paper {paper_id: $source_paper_id})
    MATCH (target:Paper {paper_id: $target_paper_id})
    MERGE (source)-[r:REPLICATES]->(target)
    SET r += $properties
    RETURN source, r, target
    """

    # ============================================================================
    # CITES Relationship Templates (Important Citations - v3.2+)
    # ============================================================================

    # CITES 관계 생성 (중요 인용)
    CREATE_CITES_RELATION = """
    MATCH (citing:Paper {paper_id: $citing_paper_id})
    MATCH (cited:Paper {paper_id: $cited_paper_id})
    MERGE (citing)-[r:CITES]->(cited)
    SET r += $properties
    RETURN citing, r, cited
    """

    # CITES 관계 생성 또는 업데이트 (인용된 논문이 없으면 생성)
    CREATE_CITES_WITH_CITED_PAPER = """
    MATCH (citing:Paper {paper_id: $citing_paper_id})
    MERGE (cited:Paper {paper_id: $cited_paper_id})
    ON CREATE SET cited += $cited_paper_properties
    MERGE (citing)-[r:CITES]->(cited)
    SET r += $cites_properties
    RETURN citing, r, cited
    """

    # 논문이 인용한 중요 문헌 검색
    GET_IMPORTANT_CITATIONS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:CITES]->(cited:Paper)
    WHERE r.context IN ['supports_result', 'contradicts_result', 'comparison']
    RETURN cited.paper_id as paper_id, cited.title as title, cited.year as year,
           cited.pmid as pmid, cited.doi as doi,
           r.context as context, r.section as section,
           r.citation_text as citation_text, r.importance_reason as importance_reason,
           r.outcome_comparison as outcome_comparison, r.direction_match as direction_match,
           r.confidence as confidence
    ORDER BY r.confidence DESC, cited.year DESC
    """

    # 결과를 지지하는 인용 검색
    GET_SUPPORTING_CITATIONS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:CITES]->(cited:Paper)
    WHERE r.context = 'supports_result'
    RETURN cited.paper_id as paper_id, cited.title as title, cited.year as year,
           cited.pmid as pmid, r.citation_text as citation_text,
           r.importance_reason as importance_reason, r.outcome_comparison as outcome_comparison
    ORDER BY r.confidence DESC
    LIMIT $limit
    """

    # 결과와 상충하는 인용 검색
    GET_CONTRADICTING_CITATIONS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:CITES]->(cited:Paper)
    WHERE r.context = 'contradicts_result'
    RETURN cited.paper_id as paper_id, cited.title as title, cited.year as year,
           cited.pmid as pmid, r.citation_text as citation_text,
           r.importance_reason as importance_reason, r.outcome_comparison as outcome_comparison
    ORDER BY r.confidence DESC
    LIMIT $limit
    """

    # 특정 논문을 인용한 모든 논문 검색 (역방향)
    GET_CITING_PAPERS = """
    MATCH (citing:Paper)-[r:CITES]->(p:Paper {paper_id: $paper_id})
    RETURN citing.paper_id as paper_id, citing.title as title, citing.year as year,
           r.context as context, r.section as section, r.citation_text as citation_text
    ORDER BY citing.year DESC
    LIMIT $limit
    """

    # 인용 네트워크 시각화용 (2단계 인용 관계)
    GET_CITATION_NETWORK = """
    MATCH (center:Paper {paper_id: $paper_id})
    OPTIONAL MATCH (center)-[r1:CITES]->(cited:Paper)
    OPTIONAL MATCH (citing:Paper)-[r2:CITES]->(center)
    WITH center, collect(DISTINCT {paper: cited, rel: r1, direction: 'outgoing'}) as outgoing,
                 collect(DISTINCT {paper: citing, rel: r2, direction: 'incoming'}) as incoming
    RETURN center, outgoing, incoming
    LIMIT $max_nodes
    """

    # 모든 논문 간 관계 검색 (확장)
    GET_ALL_PAPER_RELATIONS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:SUPPORTS|CONTRADICTS|SIMILAR_TOPIC|EXTENDS|CITES|REPLICATES]-(other:Paper)
    RETURN type(r) as relation_type, other.paper_id as related_paper,
           other.title as title, other.year as year, other.evidence_level as evidence_level,
           r.confidence as confidence, r.evidence as evidence, r.detected_by as detected_by
    ORDER BY r.confidence DESC
    """

    # 지지 관계 검색
    GET_SUPPORTING_PAPERS = """
    MATCH (p:Paper {paper_id: $paper_id})<-[r:SUPPORTS]-(other:Paper)
    WHERE r.confidence >= $min_confidence
    RETURN other.paper_id as paper_id, other.title as title, other.year as year,
           r.confidence as confidence, r.evidence as evidence
    ORDER BY r.confidence DESC, other.year DESC
    LIMIT $limit
    """

    # 상충 관계 검색
    GET_CONTRADICTING_PAPERS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:CONTRADICTS]-(other:Paper)
    WHERE r.confidence >= $min_confidence
    RETURN other.paper_id as paper_id, other.title as title, other.year as year,
           r.confidence as confidence, r.evidence as evidence
    ORDER BY r.confidence DESC, other.year DESC
    LIMIT $limit
    """

    # 유사 주제 논문 검색
    GET_SIMILAR_PAPERS = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:SIMILAR_TOPIC]-(other:Paper)
    WHERE r.confidence >= $min_confidence
    RETURN other.paper_id as paper_id, other.title as title, other.year as year,
           other.sub_domain as sub_domain, r.confidence as confidence
    ORDER BY r.confidence DESC
    LIMIT $limit
    """

    # 연구 확장 체인 검색 (Follow-up studies)
    GET_EXTENDED_RESEARCH_CHAIN = """
    MATCH path = (p:Paper {paper_id: $paper_id})<-[:EXTENDS*1..3]-(follower:Paper)
    RETURN follower.paper_id as paper_id, follower.title as title, follower.year as year,
           length(path) as depth
    ORDER BY follower.year ASC
    """

    # 재현 연구 검색
    GET_REPLICATION_STUDIES = """
    MATCH (p:Paper {paper_id: $paper_id})-[r:REPLICATES]-(other:Paper)
    RETURN other.paper_id as paper_id, other.title as title, other.year as year,
           other.sample_size as sample_size, r.confidence as confidence, r.evidence as evidence
    ORDER BY other.year DESC
    """

    # 논문 네트워크 클러스터 (연결된 모든 논문)
    GET_PAPER_NETWORK = """
    MATCH (center:Paper {paper_id: $paper_id})
    CALL {
        WITH center
        MATCH (center)-[r:SUPPORTS|CONTRADICTS|SIMILAR_TOPIC|EXTENDS|CITES|REPLICATES*1..2]-(connected:Paper)
        RETURN connected, r
        LIMIT $max_nodes
    }
    RETURN center, connected, r
    """

    # ============================================================================
    # Query Pattern Templates (NEW - v4.2)
    # 질의 패턴 기반 Cypher 템플릿
    # ============================================================================

    # 1. 치료 비교 (Treatment Comparison)
    # 예: "요추 협착증에서 UBE TLIF vs Open TLIF 어떤게 좋은가?"
    TREATMENT_COMPARISON = """
    MATCH (path:Pathology)
    WHERE path.name IN $pathology_variants
    WITH path
    MATCH (i1:Intervention)-[:TREATS]->(path)
    WHERE i1.name IN $intervention1_variants
    WITH path, i1
    MATCH (i2:Intervention)-[:TREATS]->(path)
    WHERE i2.name IN $intervention2_variants AND i2.name <> i1.name
    OPTIONAL MATCH (i1)-[a1:AFFECTS]->(o:Outcome)<-[a2:AFFECTS]-(i2)
    WHERE a1.source_paper_id IS NOT NULL AND a2.source_paper_id IS NOT NULL
    RETURN
        i1.name as intervention1,
        i2.name as intervention2,
        o.name as outcome,
        a1.value as value1, a2.value as value2,
        a1.p_value as p_value1, a2.p_value as p_value2,
        a1.direction as direction1, a2.direction as direction2,
        a1.is_significant as sig1, a2.is_significant as sig2,
        a1.source_paper_id as paper1, a2.source_paper_id as paper2
    ORDER BY a1.p_value ASC, a2.p_value ASC
    """

    # 2. 환자 특성별 결과 (Patient-Specific Outcomes)
    # 예: "고령(>70세) 환자 변형 교정술 시 합병증은?"
    PATIENT_SPECIFIC_OUTCOMES = """
    MATCH (p:Paper)
    WHERE ($age_group IS NULL OR p.patient_age_group = $age_group)
       OR ($min_age IS NOT NULL AND p.mean_age >= $min_age)
       OR ($max_age IS NOT NULL AND p.mean_age <= $max_age)
    WITH p
    MATCH (p)-[:INVESTIGATES]->(i:Intervention)
    WHERE i.name IN $intervention_variants
       OR i.category IN $intervention_categories
    WITH p, i
    MATCH (i)-[a:AFFECTS]->(o:Outcome)
    WHERE ($outcome_type IS NULL OR o.type = $outcome_type)
       OR ($outcome_names IS NULL OR o.name IN $outcome_names)
    RETURN
        p.paper_id as paper_id, p.title as title, p.year as year,
        p.patient_age_group as age_group, p.mean_age as mean_age,
        p.evidence_level as evidence_level, p.sample_size as sample_size,
        i.name as intervention,
        o.name as outcome, o.type as outcome_type,
        a.value as value, a.p_value as p_value, a.is_significant as is_significant
    ORDER BY
        CASE p.evidence_level
            WHEN '1a' THEN 1 WHEN '1b' THEN 2
            WHEN '2a' THEN 3 WHEN '2b' THEN 4
            ELSE 5
        END,
        p.year DESC
    """

    # 3. 치료 적응증 (Treatment Indications)
    # 예: "요추 감염에서 보존적 치료 vs 수술 적응증?"
    INDICATION_QUERY = """
    MATCH (path:Pathology)
    WHERE path.name IN $pathology_variants
    WITH path
    MATCH (i:Intervention)-[t:TREATS]->(path)
    WHERE t.indication IS NOT NULL AND t.indication <> ''
    RETURN
        path.name as pathology,
        i.name as intervention,
        i.category as intervention_category,
        t.indication as indication,
        t.contraindication as contraindication,
        t.indication_level as indication_level,
        t.source_guideline as source_guideline
    ORDER BY
        CASE t.indication_level
            WHEN 'strong' THEN 1
            WHEN 'moderate' THEN 2
            WHEN 'weak' THEN 3
            ELSE 4
        END,
        i.name
    """

    # 4. 결과 발생률 집계 (Outcome Rate Aggregation)
    # 예: "OLIF 후 cage subsidence 발생률은?"
    OUTCOME_AGGREGATION = """
    MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
    WHERE i.name IN $intervention_variants
      AND o.name IN $outcome_variants
    WITH i, o, collect(a) as affects_list
    UNWIND affects_list as a
    WITH i, o, affects_list,
         CASE
             WHEN a.value CONTAINS '%' THEN toFloat(replace(a.value, '%', ''))
             ELSE NULL
         END as numeric_value
    WITH i, o, affects_list, collect(numeric_value) as values
    RETURN
        i.name as intervention,
        o.name as outcome,
        size(affects_list) as study_count,
        CASE WHEN size([v IN values WHERE v IS NOT NULL]) > 0
             THEN round(reduce(sum=0.0, v IN [v IN values WHERE v IS NOT NULL] | sum + v)
                  / size([v IN values WHERE v IS NOT NULL]), 2)
             ELSE null
        END as mean_rate,
        [a IN affects_list | {
            paper_id: a.source_paper_id,
            value: a.value,
            p_value: a.p_value,
            direction: a.direction,
            is_significant: a.is_significant
        }] as studies
    """

    # 5. 근거 수준 필터링 (Evidence Level Filter)
    # 예: "UBE에 대한 RCT가 있나?"
    EVIDENCE_LEVEL_FILTER = """
    MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)
    WHERE i.name IN $intervention_variants
      AND ($evidence_levels IS NULL OR p.evidence_level IN $evidence_levels)
      AND ($study_designs IS NULL OR p.study_design IN $study_designs)
    RETURN
        p.paper_id as paper_id,
        p.title as title,
        p.year as year,
        p.evidence_level as evidence_level,
        p.study_design as study_design,
        p.sample_size as sample_size,
        p.authors as authors,
        p.journal as journal,
        p.doi as doi,
        p.pmid as pmid,
        i.name as intervention
    ORDER BY
        CASE p.evidence_level
            WHEN '1a' THEN 1 WHEN '1b' THEN 2
            WHEN '2a' THEN 3 WHEN '2b' THEN 4
            ELSE 5
        END,
        p.year DESC
    LIMIT $limit
    """

    # 6. 수술법 상세 비교 (Head-to-Head Comparison with Statistics)
    # TREATMENT_COMPARISON의 확장 버전으로 같은 논문에서의 직접 비교
    HEAD_TO_HEAD_COMPARISON = """
    MATCH (p:Paper)-[:INVESTIGATES]->(i1:Intervention)
    WHERE i1.name IN $intervention1_variants
    WITH p, i1
    MATCH (p)-[:INVESTIGATES]->(i2:Intervention)
    WHERE i2.name IN $intervention2_variants AND i2.name <> i1.name
    WITH p, i1, i2
    OPTIONAL MATCH (i1)-[a1:AFFECTS {source_paper_id: p.paper_id}]->(o:Outcome)
    OPTIONAL MATCH (i2)-[a2:AFFECTS {source_paper_id: p.paper_id}]->(o)
    WHERE a1 IS NOT NULL OR a2 IS NOT NULL
    RETURN
        p.paper_id as paper_id, p.title as title, p.year as year,
        p.evidence_level as evidence_level, p.sample_size as sample_size,
        i1.name as intervention1, i2.name as intervention2,
        collect(DISTINCT {
            outcome: o.name,
            value1: a1.value, value2: a2.value,
            p_value1: a1.p_value, p_value2: a2.p_value,
            direction1: a1.direction, direction2: a2.direction
        }) as outcomes
    ORDER BY
        CASE p.evidence_level
            WHEN '1a' THEN 1 WHEN '1b' THEN 2
            WHEN '2a' THEN 3 WHEN '2b' THEN 4
            ELSE 5
        END,
        p.year DESC
    """
