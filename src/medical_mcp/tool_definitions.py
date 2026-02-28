"""MCP Tool Definitions for Medical KAG Server.

10개 통합 도구의 스키마 정의 (v1.4 - 38개 → 10개 통합).
토큰 절감: ~4,800 tokens (63% 절감), 기능 유지: 100%.

Extracted from medical_kag_server.py for maintainability (D-012).
"""


def get_tool_definitions(Tool, ToolAnnotations):
    """Return the list of 10 MCP tool definitions.

    Args:
        Tool: MCP Tool class
        ToolAnnotations: MCP ToolAnnotations class

    Returns:
        list[Tool]: 10 tool definitions
    """
    return [
        # 1. Document Management Tool
        Tool(
            name="document",
            description="문서 관리: PDF/JSON 추가, 목록 조회, 삭제, 내보내기, 데이터베이스 리셋. action으로 기능 선택.",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add_pdf", "add_json", "list", "delete", "export", "reset", "prepare_prompt", "stats", "summarize"],
                        "description": "수행할 작업: add_pdf(PDF 추가), add_json(JSON 추가), list(목록), delete(삭제), export(내보내기), reset(리셋), prepare_prompt(프롬프트 생성), stats(시스템 통계), summarize(논문 요약)"
                    },
                    "file_path": {"type": "string", "description": "파일 경로 (add_pdf, add_json, prepare_prompt)"},
                    "document_id": {"type": "string", "description": "문서 ID (delete, export)"},
                    "metadata": {"type": "object", "description": "추가 메타데이터"},
                    "use_vision": {"type": "boolean", "default": True, "description": "레거시 PDF 프로세서 사용 (add_pdf, v1.5에서는 fallback)"},
                    "include_taxonomy": {"type": "boolean", "default": False, "description": "Taxonomy 삭제 여부 (reset)"},
                    "style": {"type": "string", "enum": ["brief", "detailed", "clinical"], "default": "brief", "description": "요약 스타일 (summarize)"}
                },
                "required": ["action"]
            }
        ),
        # 2. Search & Reasoning Tool (v1.14.25: 자동 하이브리드 검색)
        Tool(
            name="search",
            description="검색 및 추론: 벡터 검색(+PubMed 자동 보완), 그래프 검색, 적응형 검색, 근거 검색, 추론. action으로 검색 유형 선택.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "graph", "adaptive", "evidence", "reason", "clinical_recommend", "evidence_chain", "compare_interventions", "best_evidence"],
                        "description": "검색 유형: search(벡터+PubMed 자동), graph(그래프), adaptive(통합), evidence(근거), reason(추론), clinical_recommend(임상 치료 추천), evidence_chain(다중홉 근거체인), compare_interventions(수술법 비교), best_evidence(최고 근거 검색)"
                    },
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "question": {"type": "string", "description": "질문 (reason)"},
                    "intervention": {"type": "string", "description": "수술법 (evidence, evidence_chain, compare_interventions, clinical_recommend)"},
                    "intervention2": {"type": "string", "description": "비교 대상 수술법 (compare_interventions)"},
                    "pathology": {"type": "string", "description": "질환명 (evidence_chain, compare_interventions, best_evidence)"},
                    "outcome": {"type": "string", "description": "결과변수 (evidence, evidence_chain)"},
                    "outcome_category": {"type": "string", "description": "결과 카테고리 (best_evidence)"},
                    "is_a_depth": {"type": "integer", "default": 2, "description": "IS_A 계층 탐색 깊이 (evidence_chain, 1-5)"},
                    "patient_context": {"type": "string", "description": "환자 정보 텍스트 (clinical_recommend, 예: '65세 남성, 당뇨, L4-5 Stenosis')"},
                    "top_k": {"type": "integer", "default": 10, "description": "결과 수"},
                    "tier_strategy": {"type": "string", "enum": ["tier1_only", "tier1_then_tier2", "all_tiers"], "default": "tier1_then_tier2"},
                    "prefer_original": {"type": "boolean", "default": True},
                    "min_evidence_level": {"type": "string", "description": "최소 근거 수준"},
                    "search_type": {"type": "string", "enum": ["evidence", "comparison", "hierarchy", "conflict"], "default": "evidence"},
                    "direction": {"type": "string", "enum": ["improved", "worsened", "unchanged"], "default": "improved"},
                    "max_hops": {"type": "integer", "default": 3},
                    "include_conflicts": {"type": "boolean", "default": True},
                    "include_synthesis": {"type": "boolean", "default": True},
                    "detect_conflicts": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 20},
                    "enable_pubmed_fallback": {"type": "boolean", "default": True, "description": "v1.14.25: 로컬 결과 부족 시 PubMed 자동 보완 (기본 True)"},
                    "min_local_results": {"type": "integer", "default": 5, "description": "v1.14.25: 이 수 미만이면 PubMed 보완 (기본 5)"},
                    "pubmed_max_results": {"type": "integer", "default": 20, "description": "v1.14.25: PubMed 검색 최대 결과 (기본 20)"},
                    "auto_import": {"type": "boolean", "default": True, "description": "v1.14.25: 새 논문 자동 임포트 (기본 True)"}
                },
                "required": ["action"]
            }
        ),
        # 3. PubMed Tool (DOI 기능 포함, v1.12.2)
        Tool(
            name="pubmed",
            description="PubMed/DOI 연동: 검색, 대량 검색, 인용 임포트, PMID 임포트, DOI 조회/임포트, PDF 업그레이드, 통계. action으로 기능 선택.",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "bulk_search", "hybrid_search", "import_citations", "import_by_pmids", "fetch_by_doi", "doi_metadata", "import_by_doi", "upgrade_pdf", "get_abstract_only", "get_stats"],
                        "description": "작업: search, bulk_search, hybrid_search(로컬우선+PubMed보완), import_citations, import_by_pmids, fetch_by_doi(DOI조회), doi_metadata(DOI메타만), import_by_doi(DOI임포트), upgrade_pdf, get_abstract_only, get_stats"
                    },
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "paper_id": {"type": "string", "description": "논문 ID"},
                    "pmids": {"type": "array", "items": {"type": "string"}, "description": "PMID 목록"},
                    "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 10, "description": "최대 동시 처리 수 (1-10, 기본값: PUBMED_MAX_CONCURRENT 환경변수)"},
                    "doi": {"type": "string", "description": "DOI (예: 10.1016/j.spinee.2024.01.001)"},
                    "pdf_path": {"type": "string", "description": "PDF 경로"},
                    "max_results": {"type": "integer", "default": 50},
                    "local_top_k": {"type": "integer", "default": 10, "description": "hybrid_search: 로컬 검색 최대 결과 수"},
                    "min_local_results": {"type": "integer", "default": 5, "description": "hybrid_search: 이 수 미만이면 PubMed 보완 검색"},
                    "auto_import": {"type": "boolean", "default": True, "description": "hybrid_search: 새 논문 자동 임포트 여부"},
                    "fetch_details": {"type": "boolean", "default": True},
                    "import_results": {"type": "boolean", "default": False},
                    "import_to_graph": {"type": "boolean", "default": False, "description": "DOI 조회 시 그래프 임포트 여부"},
                    "fetch_fulltext": {"type": "boolean", "default": True, "description": "DOI 임포트 시 전문 조회 여부"},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "min_confidence": {"type": "number", "default": 0.7},
                    "limit": {"type": "integer", "default": 50}
                },
                "required": ["action"]
            }
        ),
        # 4. Analyze Tool (store_analyzed_paper 포함)
        Tool(
            name="analyze",
            description="텍스트 분석 및 사전 분석된 논문 저장. action=text(LLM 분석, v1.5 파이프라인 기본), action=store_paper(사전 분석 데이터 저장, store_analyzed_paper).",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["text", "store_paper"],
                        "description": "분석 작업: text(LLM 분석), store_paper(사전 분석 저장)"
                    },
                    "text": {"type": "string", "description": "분석할 텍스트 (text)"},
                    "title": {"type": "string", "description": "논문 제목"},
                    "abstract": {"type": "string", "description": "논문 초록 (store_paper 필수)"},
                    "year": {"type": "integer", "description": "출판 연도 (store_paper 필수)"},
                    "pmid": {"type": "string"},
                    "metadata": {"type": "object"},
                    "interventions": {"type": "array", "items": {"type": "string"}, "description": "수술법 목록 (store_paper 필수)"},
                    "outcomes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "intervention": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                                "direction": {"type": "string", "enum": ["improved", "worsened", "unchanged"]},
                                "p_value": {"type": "number"},
                                "effect_size": {"type": "number"},
                                "is_significant": {"type": "boolean"}
                            },
                            "required": ["name", "intervention"]
                        },
                        "description": "결과 지표 목록 (store_paper 필수)"
                    },
                    "pathologies": {"type": "array", "items": {"type": "string"}},
                    "anatomy_levels": {"type": "array", "items": {"type": "string"}},
                    "authors": {"type": "array", "items": {"type": "string"}},
                    "journal": {"type": "string"},
                    "doi": {"type": "string"},
                    "evidence_level": {"type": "string", "enum": ["1a", "1b", "2a", "2b", "3", "4", "5"]},
                    "study_design": {"type": "string", "enum": ["meta_analysis", "rct", "cohort", "case_control", "case_series", "case_report", "expert_opinion"]},
                    "sample_size": {"type": "integer"},
                    "summary": {"type": "string"},
                    "sub_domain": {"type": "string", "enum": ["Degenerative", "Deformity", "Trauma", "Tumor", "Infection", "Basic Science"]},
                    "chunks": {"type": "array", "items": {"type": "object"}},
                    "patient_cohorts": {"type": "array", "items": {"type": "object"}},
                    "followups": {"type": "array", "items": {"type": "object"}},
                    "costs": {"type": "array", "items": {"type": "object"}},
                    "quality_metrics": {"type": "array", "items": {"type": "object"}}
                },
                "required": ["action"]
            }
        ),
        # 5. Graph Exploration Tool
        Tool(
            name="graph",
            description="그래프 탐색: 논문 관계, 근거 체인, 비교, 클러스터, 멀티홉 추론, 인용 초안. action으로 기능 선택.",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["relations", "evidence_chain", "compare", "clusters", "multi_hop", "draft_citations", "build_relations", "infer_relations"],
                        "description": "그래프 작업: relations, evidence_chain, compare, clusters, multi_hop, draft_citations, build_relations(논문간 관계 자동 구축), infer_relations(추론 기반 관계 탐색)"
                    },
                    "paper_id": {"type": "string", "description": "논문 ID"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "논문 ID 목록 (compare)"},
                    "claim": {"type": "string", "description": "검증할 주장 (evidence_chain)"},
                    "question": {"type": "string", "description": "질문 (multi_hop)"},
                    "topic": {"type": "string", "description": "주제 (draft_citations)"},
                    "relation_type": {"type": "string", "enum": ["cites", "supports", "contradicts", "similar_topic"]},
                    "max_papers": {"type": "integer", "default": 5, "description": "최대 논문 수 (evidence_chain, build_relations)"},
                    "min_similarity": {"type": "number", "default": 0.4, "description": "최소 유사도 임계값 (build_relations)"},
                    "max_hops": {"type": "integer", "default": 3},
                    "start_paper_id": {"type": "string"},
                    "section_type": {"type": "string", "enum": ["introduction", "methods", "results", "discussion", "conclusion"], "default": "introduction"},
                    "max_citations": {"type": "integer", "default": 5},
                    "language": {"type": "string", "enum": ["korean", "english"], "default": "korean"},
                    "rule_name": {"type": "string", "description": "추론 규칙 (infer_relations)"},
                    "intervention": {"type": "string", "description": "수술법 (infer_relations)"},
                    "outcome": {"type": "string", "description": "결과변수 (infer_relations)"},
                    "pathology": {"type": "string", "description": "질환명 (infer_relations)"}
                },
                "required": ["action"]
            }
        ),
        # 6. Conflict Detection Tool
        Tool(
            name="conflict",
            description="충돌 탐지 및 근거 합성: 주제/수술법별 상충 연구 탐지, GRADE 기반 근거 종합. action으로 기능 선택.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["find", "detect", "synthesize"],
                        "description": "충돌 작업: find(주제별), detect(수술법별), synthesize(근거 합성)"
                    },
                    "topic": {"type": "string", "description": "주제 (find)"},
                    "intervention": {"type": "string", "description": "수술법 (detect, synthesize)"},
                    "outcome": {"type": "string", "description": "결과변수 (detect, synthesize)"},
                    "document_ids": {"type": "array", "items": {"type": "string"}},
                    "min_papers": {"type": "integer", "default": 2}
                },
                "required": ["action"]
            }
        ),
        # 7. Intervention Tool
        Tool(
            name="intervention",
            description="수술법 분석: 계층 구조, 비교, 비교 가능 목록. action으로 기능 선택.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["hierarchy", "compare", "comparable", "hierarchy_with_direction"],
                        "description": "수술법 작업: hierarchy(계층), compare(비교), comparable(비교 가능 목록), hierarchy_with_direction(방향별 계층)"
                    },
                    "intervention": {"type": "string", "description": "수술법 이름"},
                    "intervention_name": {"type": "string", "description": "수술법 이름 (hierarchy 호환)"},
                    "intervention1": {"type": "string", "description": "첫 번째 수술법 (compare)"},
                    "intervention2": {"type": "string", "description": "두 번째 수술법 (compare)"},
                    "outcome": {"type": "string", "description": "비교할 결과변수 (compare)"},
                    "direction": {"type": "string", "enum": ["ancestors", "descendants", "both"], "default": "both"}
                },
                "required": ["action"]
            }
        ),
        # 8. Extended Entity Tool (v1.2+)
        Tool(
            name="extended",
            description="확장 엔티티 조회 (v1.2+): 환자 코호트, 추적관찰, 비용 분석, 품질 지표. action으로 조회 유형 선택.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["patient_cohorts", "followup", "cost", "quality_metrics"],
                        "description": "조회 유형: patient_cohorts, followup, cost, quality_metrics"
                    },
                    "paper_id": {"type": "string"},
                    "intervention": {"type": "string"},
                    "cohort_type": {"type": "string", "enum": ["intervention", "control", "total", "propensity_matched"]},
                    "min_sample_size": {"type": "integer"},
                    "min_months": {"type": "integer"},
                    "max_months": {"type": "integer"},
                    "cost_type": {"type": "string", "enum": ["direct", "indirect", "total", "incremental"]},
                    "assessment_tool": {"type": "string", "enum": ["GRADE", "MINORS", "Newcastle-Ottawa", "Jadad", "AMSTAR", "Cochrane ROB"]},
                    "min_rating": {"type": "string", "enum": ["high", "moderate", "low", "very low"]}
                },
                "required": ["action"]
            }
        ),
        # 9. Reference Formatting Tool (v1.8)
        Tool(
            name="reference",
            description="참고문헌 포맷팅: 다양한 저널 스타일(Vancouver, AMA, APA, JBJS, Spine 등)로 참고문헌 생성. 저널별 커스텀 스타일 저장 및 BibTeX/RIS 내보내기 지원.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["format", "format_multiple", "list_styles", "set_journal_style", "add_custom_style", "preview"],
                        "description": "작업: format(단일 논문), format_multiple(여러 논문), list_styles(스타일 목록), set_journal_style(저널 스타일 설정), add_custom_style(커스텀 스타일 추가), preview(스타일 미리보기)"
                    },
                    "paper_id": {"type": "string", "description": "논문 ID (data/extracted/*.json)"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "논문 ID 목록 (format_multiple)"},
                    "query": {"type": "string", "description": "검색어 (paper_id 대신 사용)"},
                    "style": {
                        "type": "string",
                        "enum": ["vancouver", "ama", "apa", "jbjs", "spine", "nlm", "harvard"],
                        "default": "vancouver",
                        "description": "인용 스타일"
                    },
                    "target_journal": {"type": "string", "description": "대상 저널명 (저장된 스타일 자동 적용)"},
                    "output_format": {
                        "type": "string",
                        "enum": ["text", "bibtex", "ris"],
                        "default": "text",
                        "description": "출력 형식"
                    },
                    "numbered": {"type": "boolean", "default": True, "description": "번호 붙이기 (format_multiple)"},
                    "start_number": {"type": "integer", "default": 1, "description": "시작 번호"},
                    "max_results": {"type": "integer", "default": 10, "description": "최대 결과 수"},
                    "journal_name": {"type": "string", "description": "저널명 (set_journal_style)"},
                    "style_name": {"type": "string", "description": "스타일명 (set_journal_style)"},
                    "name": {"type": "string", "description": "커스텀 스타일 이름 (add_custom_style)"},
                    "base_style": {"type": "string", "default": "vancouver", "description": "기반 스타일 (add_custom_style)"},
                    "author_et_al_threshold": {"type": "integer", "default": 6, "description": "et al. 사용 저자 수 기준"},
                    "include_doi": {"type": "boolean", "default": False, "description": "DOI 포함 여부"},
                    "include_pmid": {"type": "boolean", "default": False, "description": "PMID 포함 여부"},
                    "styles": {"type": "array", "items": {"type": "string"}, "description": "미리볼 스타일 목록 (preview)"}
                },
                "required": ["action"]
            }
        ),
        # 10. Writing Guide Tool (v1.12)
        Tool(
            name="writing_guide",
            description="학술 논문 작성 가이드: 섹션별 작성 지침, 연구 유형별 체크리스트(STROBE, CONSORT, PRISMA, CARE), 전문가 에이전트, 리비전 응답 템플릿.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["section_guide", "checklist", "expert", "response_template", "draft_response", "analyze_comments", "all_guides"],
                        "description": "작업: section_guide(섹션 가이드), checklist(체크리스트), expert(전문가 정보), response_template(응답 템플릿), draft_response(응답 초안), analyze_comments(리뷰어 코멘트 분석), all_guides(전체 가이드)"
                    },
                    "section": {
                        "type": "string",
                        "enum": ["introduction", "methods", "results", "discussion", "conclusion", "figure_legend"],
                        "description": "섹션명"
                    },
                    "study_type": {
                        "type": "string",
                        "enum": ["rct", "cohort", "case_control", "cross_sectional", "case_series", "case_report", "systematic_review", "meta_analysis", "diagnostic", "protocol", "observational_meta_analysis", "prediction", "economic"],
                        "description": "연구 유형"
                    },
                    "include_examples": {"type": "boolean", "default": True, "description": "예시 포함 여부"},
                    "checklist_name": {
                        "type": "string",
                        "enum": ["strobe", "consort", "prisma", "care", "stard", "spirit", "moose", "tripod", "cheers"],
                        "description": "체크리스트 (strobe:관찰연구, consort:RCT, prisma:SR/MA, care:증례, stard:진단, spirit:프로토콜, moose:관찰MA, tripod:예측모델, cheers:경제성)"
                    },
                    "section_filter": {"type": "string", "description": "특정 섹션 필터"},
                    "expert": {
                        "type": "string",
                        "enum": ["clinician", "methodologist", "statistician", "editor"],
                        "description": "전문가 유형"
                    },
                    "response_type": {
                        "type": "string",
                        "enum": ["major_revision", "minor_revision", "rejection_rebuttal"],
                        "description": "응답 유형"
                    },
                    "reviewer_comments": {"type": "string", "description": "리뷰어 코멘트 (draft_response, analyze_comments)"}
                },
                "required": ["action"]
            }
        ),
    ]
