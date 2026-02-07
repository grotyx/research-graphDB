#!/usr/bin/env python3
"""Documentation-Code Consistency Validator.

개발 문서(TRD, PRD, Tasks, Specs)와 구현 코드 간의 일관성을 검증하는 에이전트.

검증 항목:
1. 파일 구조 일관성 - TRD에 명시된 파일이 실제로 존재하는지
2. 인터페이스 일관성 - 스펙에 정의된 클래스/메서드가 구현되었는지
3. 테스트 커버리지 - Tasks에 명시된 테스트 파일이 존재하는지
4. 의존성 일관성 - requirements.txt가 문서와 일치하는지
5. 태스크 상태 검증 - Tasks의 완료 상태가 실제 구현과 일치하는지

Usage:
    python scripts/validate_doc_code_consistency.py
    python scripts/validate_doc_code_consistency.py --verbose
    python scripts/validate_doc_code_consistency.py --fix-suggestions
"""

import ast
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ValidationStatus(Enum):
    """검증 결과 상태."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class ValidationResult:
    """단일 검증 결과."""
    category: str
    item: str
    status: ValidationStatus
    message: str
    details: str = ""
    fix_suggestion: str = ""


@dataclass
class ValidationReport:
    """전체 검증 보고서."""
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == ValidationStatus.PASS)

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.status == ValidationStatus.WARN)

    @property
    def failures(self) -> int:
        return sum(1 for r in self.results if r.status == ValidationStatus.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == ValidationStatus.SKIP)

    def add(self, result: ValidationResult):
        self.results.append(result)

    def print_summary(self, verbose: bool = False, show_fixes: bool = False):
        """검증 결과 요약 출력."""
        print("\n" + "=" * 70)
        print("📋 Documentation-Code Consistency Validation Report")
        print("=" * 70)

        # 카테고리별 그룹화
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = []
            categories[r.category].append(r)

        for category, items in categories.items():
            print(f"\n## {category}")
            print("-" * 50)

            for r in items:
                status_icon = {
                    ValidationStatus.PASS: "✅",
                    ValidationStatus.WARN: "⚠️",
                    ValidationStatus.FAIL: "❌",
                    ValidationStatus.SKIP: "⏭️"
                }[r.status]

                print(f"  {status_icon} {r.item}: {r.message}")

                if verbose and r.details:
                    for line in r.details.split("\n"):
                        print(f"      {line}")

                if show_fixes and r.fix_suggestion:
                    print(f"      💡 Fix: {r.fix_suggestion}")

        # 총계
        print("\n" + "=" * 70)
        print(f"📊 Summary: {self.passed} passed, {self.warnings} warnings, "
              f"{self.failures} failures, {self.skipped} skipped")
        print("=" * 70)

        return self.failures == 0


class DocumentCodeValidator:
    """문서-코드 일관성 검증기."""

    def __init__(self, project_root: Path):
        self.root = project_root
        self.report = ValidationReport()

        # 주요 디렉토리
        self.src_dir = self.root / "src"
        self.tests_dir = self.root / "tests"
        self.docs_dir = self.root / "docs"
        self.web_dir = self.root / "web"

    def validate_all(self) -> ValidationReport:
        """모든 검증 수행."""
        print("🔍 Starting validation...")

        self._validate_file_structure()
        self._validate_module_interfaces()
        self._validate_test_coverage()
        self._validate_dependencies()
        self._validate_task_status()
        self._validate_web_ui()
        self._validate_spec_implementation()

        return self.report

    def _validate_file_structure(self):
        """파일 구조 검증 - TRD에 명시된 파일 존재 확인."""
        category = "📁 File Structure"

        # TRD에 정의된 핵심 모듈 구조
        expected_files = {
            # LLM 모듈
            "src/llm/__init__.py": "LLM module init",
            "src/llm/gemini_client.py": "Gemini API client",
            "src/llm/cache.py": "LLM response cache",
            "src/llm/prompts.py": "Prompt templates",

            # Builder 모듈
            "src/builder/__init__.py": "Builder module init",
            "src/builder/llm_section_classifier.py": "LLM section classifier",
            "src/builder/llm_semantic_chunker.py": "LLM semantic chunker",
            "src/builder/llm_metadata_extractor.py": "LLM metadata extractor",
            "src/builder/gemini_vision_processor.py": "Gemini PDF processor",

            # Knowledge 모듈
            "src/knowledge/__init__.py": "Knowledge module init",
            "src/knowledge/paper_graph.py": "Paper relationship graph",
            "src/knowledge/citation_extractor.py": "Citation extractor",
            "src/knowledge/relationship_reasoner.py": "Relationship reasoner",

            # Solver 모듈
            "src/solver/__init__.py": "Solver module init",
            "src/solver/query_parser.py": "Query parser",
            "src/solver/tiered_search.py": "Tiered search (Note: TRD says search_engine.py)",
            "src/solver/multi_factor_ranker.py": "Multi-factor ranker",
            "src/solver/reasoner.py": "Reasoner",
            "src/solver/conflict_detector.py": "Conflict detector",
            "src/solver/response_generator.py": "Response generator",

            # Storage 모듈
            "src/storage/__init__.py": "Storage module init",
            "src/storage/vector_db.py": "Vector database",

            # External 모듈
            "src/external/__init__.py": "External module init",
            "src/external/pubmed_client.py": "PubMed client",

            # MCP 서버
            "src/medical_mcp/__init__.py": "MCP module init",
            "src/medical_mcp/medical_kag_server.py": "Medical KAG server",

            # Ontology 모듈
            "src/ontology/__init__.py": "Ontology module init",
            "src/ontology/snomed_linker.py": "SNOMED linker",
            "src/ontology/concept_hierarchy.py": "Concept hierarchy",
        }

        for file_path, description in expected_files.items():
            full_path = self.root / file_path
            if full_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=file_path,
                    status=ValidationStatus.PASS,
                    message=f"{description} exists"
                ))
            else:
                self.report.add(ValidationResult(
                    category=category,
                    item=file_path,
                    status=ValidationStatus.FAIL,
                    message=f"{description} missing",
                    fix_suggestion=f"Create {file_path}"
                ))

        # TRD v2.3: tiered_search.py로 문서 업데이트됨 - 불일치 체크 제거됨

    def _validate_module_interfaces(self):
        """모듈 인터페이스 검증 - 스펙에 정의된 클래스/메서드 존재 확인."""
        category = "🔌 Module Interfaces"

        # GeminiClient 검증
        gemini_client_path = self.root / "src/llm/gemini_client.py"
        if gemini_client_path.exists():
            content = gemini_client_path.read_text()

            required_classes = ["GeminiConfig", "GeminiResponse", "CostTracker", "RateLimiter", "GeminiClient"]
            required_methods = ["generate", "generate_json", "generate_batch", "get_cost_summary", "reset_cost_tracker"]

            for cls in required_classes:
                if f"class {cls}" in content:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"GeminiClient.{cls}",
                        status=ValidationStatus.PASS,
                        message=f"Class {cls} defined"
                    ))
                else:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"GeminiClient.{cls}",
                        status=ValidationStatus.FAIL,
                        message=f"Class {cls} not found in gemini_client.py"
                    ))

            for method in required_methods:
                if f"def {method}" in content or f"async def {method}" in content:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"GeminiClient.{method}()",
                        status=ValidationStatus.PASS,
                        message=f"Method {method} defined"
                    ))
                else:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"GeminiClient.{method}()",
                        status=ValidationStatus.FAIL,
                        message=f"Method {method} not found"
                    ))

        # Vision Processor 검증
        vision_path = self.root / "src/builder/gemini_vision_processor.py"
        if vision_path.exists():
            content = vision_path.read_text()

            required_classes = ["VisionProcessorResult", "ExtractedMetadata", "ExtractedChunk",
                              "PICOData", "StatisticsData"]

            for cls in required_classes:
                if f"class {cls}" in content or f"@dataclass\nclass {cls}" in content:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"VisionProcessor.{cls}",
                        status=ValidationStatus.PASS,
                        message=f"Dataclass {cls} defined"
                    ))
                else:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"VisionProcessor.{cls}",
                        status=ValidationStatus.FAIL,
                        message=f"Dataclass {cls} not found"
                    ))

            # GeminiPDFProcessor 클래스 검증
            if "class GeminiPDFProcessor" in content or "class GeminiVisionProcessor" in content:
                self.report.add(ValidationResult(
                    category=category,
                    item="VisionProcessor.GeminiPDFProcessor",
                    status=ValidationStatus.PASS,
                    message="GeminiPDFProcessor class defined"
                ))

                # process_pdf 메서드 검증
                if "async def process_pdf" in content:
                    self.report.add(ValidationResult(
                        category=category,
                        item="VisionProcessor.process_pdf()",
                        status=ValidationStatus.PASS,
                        message="process_pdf method defined"
                    ))

        # Knowledge Graph 모듈 검증
        paper_graph_path = self.root / "src/knowledge/paper_graph.py"
        if paper_graph_path.exists():
            content = paper_graph_path.read_text()

            required_classes = ["PaperNode", "PaperRelation", "PaperGraph"]
            required_methods = ["add_paper", "get_paper", "add_relation", "get_relations",
                              "find_supporting_papers", "find_contradicting_papers"]

            for cls in required_classes:
                if f"class {cls}" in content:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"PaperGraph.{cls}",
                        status=ValidationStatus.PASS,
                        message=f"Class {cls} defined"
                    ))
                else:
                    self.report.add(ValidationResult(
                        category=category,
                        item=f"PaperGraph.{cls}",
                        status=ValidationStatus.FAIL,
                        message=f"Class {cls} not found"
                    ))

    def _validate_test_coverage(self):
        """테스트 커버리지 검증 - Tasks에 명시된 테스트 파일 존재 확인."""
        category = "🧪 Test Coverage"

        expected_tests = {
            "tests/llm/test_gemini_client.py": "GeminiClient tests",
            "tests/llm/test_cache.py": "LLM cache tests",
            "tests/builder/test_llm_section_classifier.py": "Section classifier tests",
            "tests/builder/test_llm_semantic_chunker.py": "Semantic chunker tests",
            "tests/builder/test_llm_metadata_extractor.py": "Metadata extractor tests",
            "tests/knowledge/test_paper_graph.py": "Paper graph tests",
            "tests/knowledge/test_citation_extractor.py": "Citation extractor tests",
            "tests/knowledge/test_relationship_reasoner.py": "Relationship reasoner tests",
            "tests/solver/test_tiered_search.py": "Tiered search tests",
            "tests/solver/test_multi_factor_ranker.py": "Multi-factor ranker tests",
            "tests/solver/test_query_parser.py": "Query parser tests",
            "tests/solver/test_reasoner.py": "Reasoner tests",
            "tests/solver/test_response_generator.py": "Response generator tests",
            "tests/storage/test_vector_db.py": "Vector DB tests",
            "tests/integration/test_llm_pipeline.py": "LLM pipeline integration tests",
            "tests/external/test_pubmed_client.py": "PubMed client tests",
            "tests/medical_mcp/test_medical_kag_server.py": "MCP server tests",
        }

        for test_path, description in expected_tests.items():
            full_path = self.root / test_path
            if full_path.exists():
                # 테스트 파일이 비어있지 않은지 확인
                content = full_path.read_text()
                test_count = content.count("def test_") + content.count("async def test_")

                if test_count > 0:
                    self.report.add(ValidationResult(
                        category=category,
                        item=test_path,
                        status=ValidationStatus.PASS,
                        message=f"{description} ({test_count} tests)"
                    ))
                else:
                    self.report.add(ValidationResult(
                        category=category,
                        item=test_path,
                        status=ValidationStatus.WARN,
                        message=f"{description} exists but no test functions found",
                        fix_suggestion="Add test functions to the file"
                    ))
            else:
                self.report.add(ValidationResult(
                    category=category,
                    item=test_path,
                    status=ValidationStatus.FAIL,
                    message=f"{description} missing",
                    fix_suggestion=f"Create {test_path} with test cases"
                ))

    def _validate_dependencies(self):
        """의존성 검증 - requirements.txt가 문서와 일치하는지."""
        category = "📦 Dependencies"

        requirements_path = self.root / "requirements.txt"
        if not requirements_path.exists():
            self.report.add(ValidationResult(
                category=category,
                item="requirements.txt",
                status=ValidationStatus.FAIL,
                message="requirements.txt not found"
            ))
            return

        content = requirements_path.read_text().lower()

        # TRD에 명시된 핵심 의존성
        required_deps = {
            "google-genai": "google-genai SDK (TRD v2.3)",
            "pydantic": "Data validation",
            "chromadb": "Vector database",
            "aiosqlite": "Async SQLite",
            "pymupdf": "PDF processing",
            "python-dotenv": "Environment variables",
            "streamlit": "Web UI",
            "plotly": "Graph visualization",
            "networkx": "Network analysis",
            "aiohttp": "Async HTTP client",
        }

        # 선택적 의존성 (존재해도 경고하지 않음 - 마이그레이션 완료)
        # v2.3: tenacity는 requirements.txt에서 제거됨, google-generativeai도 선택적
        optional_legacy_deps = {
            # "google-generativeai": "Legacy SDK (optional)",
            # "tenacity": "Optional retry library"
        }

        for dep, description in required_deps.items():
            if dep.lower() in content or dep.replace("-", "_").lower() in content:
                self.report.add(ValidationResult(
                    category=category,
                    item=dep,
                    status=ValidationStatus.PASS,
                    message=f"{description} - present"
                ))
            else:
                self.report.add(ValidationResult(
                    category=category,
                    item=dep,
                    status=ValidationStatus.WARN,
                    message=f"{description} - not found in requirements.txt",
                    fix_suggestion=f"Add {dep} to requirements.txt"
                ))

        # 레거시 의존성 체크 제거됨 (v2.3 마이그레이션 완료)

    def _validate_task_status(self):
        """태스크 상태 검증 - Tasks의 완료 상태가 실제 구현과 일치하는지."""
        category = "📝 Task Status"

        tasks_path = self.root / "docs/Tasks_v2_LLM.md"
        if not tasks_path.exists():
            self.report.add(ValidationResult(
                category=category,
                item="Tasks_v2_LLM.md",
                status=ValidationStatus.SKIP,
                message="Tasks file not found"
            ))
            return

        content = tasks_path.read_text()

        # 완료된 태스크 중 파일이 실제로 존재하는지 확인
        completed_tasks = re.findall(r'\| [\d.]+ \| (.+?) \| ✅ \|', content)

        # 핵심 파일-태스크 매핑
        file_task_mapping = {
            "src/llm/gemini_client.py": ["GeminiClient", "generate()", "generate_json()"],
            "src/llm/cache.py": ["LLMCache", "캐시"],
            "src/builder/llm_section_classifier.py": ["섹션 분류", "SectionBoundary"],
            "src/builder/llm_semantic_chunker.py": ["청킹", "SemanticChunk"],
            "src/builder/llm_metadata_extractor.py": ["메타데이터", "PICOElements"],
            "src/knowledge/paper_graph.py": ["PaperNode", "PaperRelation"],
            "src/knowledge/citation_extractor.py": ["인용 추출", "CitationInfo"],
            "src/knowledge/relationship_reasoner.py": ["관계 추론", "RelationshipReasoner"],
        }

        for file_path, keywords in file_task_mapping.items():
            full_path = self.root / file_path
            if full_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=file_path,
                    status=ValidationStatus.PASS,
                    message=f"Completed task implemented"
                ))
            else:
                self.report.add(ValidationResult(
                    category=category,
                    item=file_path,
                    status=ValidationStatus.WARN,
                    message=f"Task marked as completed but file missing",
                    fix_suggestion="Update task status or create the file"
                ))

        # 미완료 태스크 확인 (⬜ TODO)
        # 태스크 테이블 내에서만 카운트 (상태 범례 제외)
        # 테이블 행에서만 카운트: | ID | 태스크 | 상태 | 패턴
        task_rows = re.findall(r'\| \d+\.\d+\.\d+ \|[^|]+\| (✅|🔄|⬜) \|', content)
        done_count = task_rows.count('✅')
        in_progress_count = task_rows.count('🔄')
        todo_count = task_rows.count('⬜')

        self.report.add(ValidationResult(
            category=category,
            item="Task Progress Summary",
            status=ValidationStatus.PASS if todo_count == 0 else ValidationStatus.WARN,
            message=f"Done: {done_count}, In Progress: {in_progress_count}, TODO: {todo_count}",
            details=f"Completion rate: {done_count / (done_count + in_progress_count + todo_count) * 100:.1f}%"
        ))

    def _validate_web_ui(self):
        """Web UI 검증 - TRD에 명시된 페이지 존재 확인."""
        category = "🌐 Web UI"

        expected_pages = {
            "web/app.py": "Main dashboard",
            "web/pages/1_📄_Documents.py": "Documents page",
            "web/pages/2_🔍_Search.py": "Search page",
            "web/pages/3_📊_Knowledge_Graph.py": "Knowledge Graph page",
            "web/pages/4_✍️_Draft_Assistant.py": "Draft Assistant page",
            "web/pages/5_⚙️_Settings.py": "Settings page",
            "web/pages/6_🔬_PubMed.py": "PubMed search page",
            "web/utils/server_bridge.py": "Server bridge utility",
        }

        for page_path, description in expected_pages.items():
            full_path = self.root / page_path
            if full_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=page_path,
                    status=ValidationStatus.PASS,
                    message=f"{description} exists"
                ))
            else:
                self.report.add(ValidationResult(
                    category=category,
                    item=page_path,
                    status=ValidationStatus.FAIL,
                    message=f"{description} missing",
                    fix_suggestion=f"Create {page_path}"
                ))

        # 추가로 발견된 페이지 (문서에 없는 것)
        pages_dir = self.root / "web/pages"
        if pages_dir.exists():
            for page_file in pages_dir.glob("*.py"):
                page_name = str(page_file.relative_to(self.root))
                if page_name not in expected_pages:
                    self.report.add(ValidationResult(
                        category=category,
                        item=page_name,
                        status=ValidationStatus.WARN,
                        message="Additional page not documented in TRD",
                        fix_suggestion="Add page documentation to TRD or remove if unused"
                    ))

    def _validate_spec_implementation(self):
        """스펙 문서와 구현 일치 검증."""
        category = "📖 Spec Implementation"

        specs_dir = self.root / "docs/specs"
        if not specs_dir.exists():
            self.report.add(ValidationResult(
                category=category,
                item="docs/specs/",
                status=ValidationStatus.SKIP,
                message="Specs directory not found"
            ))
            return

        # 스펙 파일-구현 파일 매핑
        spec_impl_mapping = {
            "gemini-client.md": "src/llm/gemini_client.py",
            "llm-section-classifier.md": "src/builder/llm_section_classifier.py",
            "llm-semantic-chunker.md": "src/builder/llm_semantic_chunker.py",
            "llm-metadata-extractor.md": "src/builder/llm_metadata_extractor.py",
            "paper-graph.md": "src/knowledge/paper_graph.py",
            "citation-extractor.md": "src/knowledge/citation_extractor.py",
            "relationship-reasoner.md": "src/knowledge/relationship_reasoner.py",
            "conflict-detector.md": "src/solver/conflict_detector.py",
            "multi-factor-ranker.md": "src/solver/multi_factor_ranker.py",
        }

        for spec_file, impl_file in spec_impl_mapping.items():
            spec_path = specs_dir / spec_file
            impl_path = self.root / impl_file

            if spec_path.exists() and impl_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=spec_file,
                    status=ValidationStatus.PASS,
                    message=f"Spec and implementation both exist"
                ))
            elif spec_path.exists() and not impl_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=spec_file,
                    status=ValidationStatus.FAIL,
                    message=f"Spec exists but implementation missing: {impl_file}",
                    fix_suggestion=f"Implement {impl_file} according to {spec_file}"
                ))
            elif not spec_path.exists() and impl_path.exists():
                self.report.add(ValidationResult(
                    category=category,
                    item=impl_file,
                    status=ValidationStatus.WARN,
                    message=f"Implementation exists but spec missing: {spec_file}",
                    fix_suggestion=f"Create {spec_file} documenting {impl_file}"
                ))

        # TRD와 gemini_client 스펙의 SDK 버전 일치 확인
        gemini_spec_path = specs_dir / "gemini-client.md"
        if gemini_spec_path.exists():
            spec_content = gemini_spec_path.read_text()

            # SDK 버전 체크: 스펙에서 google-genai 언급 확인
            if "google-genai" in spec_content:
                self.report.add(ValidationResult(
                    category=category,
                    item="gemini-client.md SDK version",
                    status=ValidationStatus.PASS,
                    message="Spec correctly references google-genai SDK (v2.3)"
                ))


def main():
    """메인 실행 함수."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate documentation-code consistency")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--fix-suggestions", "-f", action="store_true", help="Show fix suggestions")
    parser.add_argument("--project-root", "-p", type=str, default=None,
                       help="Project root directory (default: auto-detect)")
    args = parser.parse_args()

    # 프로젝트 루트 감지
    if args.project_root:
        project_root = Path(args.project_root)
    else:
        # scripts/ 디렉토리에서 실행 가정
        project_root = Path(__file__).parent.parent

    if not project_root.exists():
        print(f"❌ Project root not found: {project_root}")
        sys.exit(1)

    print(f"📂 Project root: {project_root}")

    # 검증 수행
    validator = DocumentCodeValidator(project_root)
    report = validator.validate_all()

    # 결과 출력
    success = report.print_summary(verbose=args.verbose, show_fixes=args.fix_suggestions)

    # 종료 코드: 실패가 있으면 1
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
