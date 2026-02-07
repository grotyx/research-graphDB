"""Settings Page - System Configuration & Data Management.

View system status, configure settings, and manage database data.
"""

import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Settings - Spine GraphRAG", page_icon="⚙️", layout="wide")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from utils.shared_styles import apply_sidebar_styles
apply_sidebar_styles()

from utils.server_bridge import get_server
from utils.async_helpers import run_async
from utils.graph_utils import get_neo4j_client
from utils.graph_cleanup import GraphCleanupManager

# SNOMED update functionality
try:
    from graph.entity_normalizer import EntityNormalizer
    ENTITY_NORMALIZER_AVAILABLE = True
except ImportError:
    ENTITY_NORMALIZER_AVAILABLE = False


def update_snomed_codes(neo4j_client) -> dict:
    """Update SNOMED codes for all Intervention nodes using EntityNormalizer.

    Returns:
        dict with success, updated, not_found, total counts
    """
    if not ENTITY_NORMALIZER_AVAILABLE:
        return {"success": False, "error": "EntityNormalizer not available"}

    normalizer = EntityNormalizer()

    # Get all interventions without SNOMED codes
    query = """
    MATCH (i:Intervention)
    WHERE i.snomed_code IS NULL OR i.snomed_code = ''
    RETURN i.name as name
    """
    interventions = neo4j_client.run_query(query)

    updated = 0
    not_found = 0
    details = []

    for item in interventions:
        name = item["name"]
        result = normalizer.normalize_intervention(name)

        if result.snomed_code:
            # Update Neo4j
            update_query = """
            MATCH (i:Intervention {name: $name})
            SET i.snomed_code = $snomed_code,
                i.snomed_term = $snomed_term
            RETURN i.name as name
            """
            neo4j_client.run_query(update_query, {
                "name": name,
                "snomed_code": result.snomed_code,
                "snomed_term": result.snomed_term
            })
            updated += 1
            details.append(f"✅ {name} → {result.snomed_code}")
        else:
            not_found += 1
            details.append(f"⚠️ {name} (no mapping)")

    # Get final stats
    stats_query = """
    MATCH (i:Intervention)
    WITH count(i) as total
    MATCH (i2:Intervention)
    WHERE i2.snomed_code IS NOT NULL AND i2.snomed_code <> ''
    RETURN total, count(i2) as with_snomed
    """
    stats = neo4j_client.run_query(stats_query)

    total = stats[0]["total"] if stats else 0
    with_snomed = stats[0]["with_snomed"] if stats else 0
    coverage = (with_snomed / total * 100) if total > 0 else 0

    return {
        "success": True,
        "updated": updated,
        "not_found": not_found,
        "total": total,
        "with_snomed": with_snomed,
        "coverage": coverage,
        "details": details[:20]  # Show first 20 for UI
    }


def main():
    st.title("⚙️ Settings")
    st.markdown("**시스템 상태 및 데이터 관리**")

    bridge = get_server()
    server = bridge.server

    # Neo4j 클라이언트 및 정리 관리자
    neo4j_client = get_neo4j_client()
    cleanup_manager = GraphCleanupManager(neo4j_client) if neo4j_client else None

    # ═══════════════════════════════════════════════════════════
    # TABS
    # ═══════════════════════════════════════════════════════════

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 **시스템 상태**",
        "🗃️ **데이터 관리**",
        "🧹 **정리 도구**",
        "⚠️ **데이터베이스 리셋**",
        "💻 **Cypher 콘솔**"
    ])

    # ═══════════════════════════════════════════════════════════
    # TAB 1: System Status
    # ═══════════════════════════════════════════════════════════

    with tab1:
        st.subheader("📊 시스템 상태")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Core Components:**")

            # Neo4j Vector Index (v5.3: 통합 저장소)
            if neo4j_client:
                st.success("✅ Neo4j: Connected")
            else:
                st.warning("⚠️ Neo4j: Not available")

            # Knowledge Graph
            if bridge.has_knowledge_graph:
                st.success("✅ Knowledge Graph: Active")
            else:
                st.warning("⚠️ Knowledge Graph: Not available")

            # Query Expansion
            if bridge.has_query_expansion:
                st.success("✅ Query Expansion: Active")
            else:
                st.info("ℹ️ Query Expansion: Basic mode")

        with col2:
            st.markdown("**LLM & NLP:**")

            # LLM
            if bridge.is_llm_enabled:
                st.success("✅ LLM (Claude): Connected")
            else:
                st.warning("⚠️ LLM: Disabled (check ANTHROPIC_API_KEY)")

            # SNOMED Linker
            if server.snomed_linker:
                st.success("✅ SNOMED Linker: Active")
            else:
                st.info("ℹ️ SNOMED Linker: Not installed")
                st.caption("Install with: pip install scispacy")

        st.divider()

        # Database Statistics
        st.subheader("📈 데이터베이스 통계")

        result = run_async(server.list_documents())

        if result.get("success"):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("📄 Documents", result.get("total_documents", 0))

            with col2:
                st.metric("📑 Total Chunks", result.get("total_chunks", 0))

            with col3:
                tier_dist = result.get("tier_distribution", {})
                # 모든 청크가 tier1에 저장됨 (tier 구분 제거됨)
                total_indexed = tier_dist.get("tier1", 0) + tier_dist.get("tier2", 0)
                st.metric("💾 Indexed Chunks", total_indexed)

            with col4:
                st.metric("📊 Avg/Doc",
                         round(result.get("total_chunks", 0) / max(result.get("total_documents", 1), 1), 1))

        # Neo4j Statistics
        if cleanup_manager:
            st.markdown("---")
            st.markdown("**Neo4j Graph 통계:**")

            db_stats = cleanup_manager.get_database_stats()

            if "error" not in db_stats:
                stat_cols = st.columns(6)

                nodes = db_stats.get("nodes", {})
                with stat_cols[0]:
                    st.metric("📄 Paper", nodes.get("Paper", 0))
                with stat_cols[1]:
                    st.metric("🔬 Intervention", nodes.get("Intervention", 0))
                with stat_cols[2]:
                    st.metric("🎯 Outcome", nodes.get("Outcome", 0))
                with stat_cols[3]:
                    st.metric("🦠 Pathology", nodes.get("Pathology", 0))
                with stat_cols[4]:
                    st.metric("🦴 Anatomy", nodes.get("Anatomy", 0))
                with stat_cols[5]:
                    st.metric("🔗 Relationships", db_stats.get("total_relationships", 0))

                # v7.2 Extended Entities
                st.markdown("**v7.2 Extended Entities:**")
                v72_cols = st.columns(4)
                with v72_cols[0]:
                    st.metric("👥 PatientCohort", nodes.get("PatientCohort", 0))
                with v72_cols[1]:
                    st.metric("📅 FollowUp", nodes.get("FollowUp", 0))
                with v72_cols[2]:
                    st.metric("💰 Cost", nodes.get("Cost", 0))
                with v72_cols[3]:
                    st.metric("⭐ QualityMetric", nodes.get("QualityMetric", 0))

        st.divider()

        # Configuration Info
        st.subheader("🔧 설정 정보")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Embedding Model:**")
            st.code("MohammadKhodadad/MedTE-cl15-step-8000")

            st.markdown("**LLM Model:**")
            st.code("Claude Haiku 4.5 (+ Sonnet fallback)")

        with col2:
            st.markdown("**Data Directory:**")
            st.code(str(server.data_dir))

            st.markdown("**Storage Backend (v7.2):**")
            st.code("Neo4j Vector Index (통합 저장소, Extended Entity Schema)")

    # ═══════════════════════════════════════════════════════════
    # TAB 2: Data Management
    # ═══════════════════════════════════════════════════════════

    with tab2:
        st.subheader("🗃️ 데이터 관리")

        # Document List with Delete
        st.markdown("### 📄 문서 목록")

        docs_result = run_async(server.list_documents())

        if docs_result.get("success") and docs_result.get("documents"):
            docs = docs_result["documents"]

            # Selection
            st.info(f"총 {len(docs)}개 문서가 있습니다.")

            for doc in docs:
                doc_id = doc.get("document_id", "Unknown")
                chunks = doc.get("chunk_count", 0)

                col1, col2, col3 = st.columns([4, 1, 1])

                with col1:
                    # Truncate long names
                    display_name = doc_id[:60] + "..." if len(doc_id) > 60 else doc_id
                    st.markdown(f"**{display_name}**")
                    st.caption(f"📑 {chunks} chunks")

                with col2:
                    # View details
                    if st.button("📊 상세", key=f"detail_{doc_id}"):
                        st.session_state[f"show_detail_{doc_id}"] = True

                with col3:
                    # Delete button
                    if st.button("🗑️ 삭제", key=f"delete_{doc_id}", type="secondary"):
                        st.session_state[f"confirm_delete_{doc_id}"] = True

                # Confirmation dialog
                if st.session_state.get(f"confirm_delete_{doc_id}"):
                    st.warning(f"정말로 '{doc_id}'를 삭제하시겠습니까?")

                    confirm_cols = st.columns([1, 1, 3])
                    with confirm_cols[0]:
                        if st.button("✅ 확인", key=f"confirm_yes_{doc_id}"):
                            with st.spinner("삭제 중..."):
                                # Delete from Neo4j (v5.3: 통합 저장소)
                                delete_result = run_async(server.delete_document(doc_id))

                                # Additional Neo4j cleanup if available
                                if cleanup_manager:
                                    neo4j_result = cleanup_manager.delete_paper_with_cleanup(doc_id)
                                    neo4j_msg = f" | Cleanup: {neo4j_result.message}"
                                else:
                                    neo4j_msg = ""

                                if delete_result.get("success"):
                                    st.success(f"✅ 삭제 완료: {doc_id}{neo4j_msg}")
                                    del st.session_state[f"confirm_delete_{doc_id}"]
                                    st.rerun()
                                else:
                                    st.error(f"❌ 삭제 실패: {delete_result.get('error')}")

                    with confirm_cols[1]:
                        if st.button("❌ 취소", key=f"confirm_no_{doc_id}"):
                            del st.session_state[f"confirm_delete_{doc_id}"]
                            st.rerun()

                st.markdown("---")

        else:
            st.info("📭 등록된 문서가 없습니다. Documents 페이지에서 PDF를 업로드하세요.")

        st.divider()

        # Quick Actions
        st.markdown("### ⚡ 빠른 작업")

        quick_cols = st.columns(3)

        with quick_cols[0]:
            if st.button("🗑️ LLM 캐시 삭제", use_container_width=True):
                cache_path = server.data_dir / "llm_cache.db"
                if cache_path.exists():
                    cache_path.unlink()
                    st.success("캐시가 삭제되었습니다!")
                else:
                    st.info("삭제할 캐시가 없습니다.")

        with quick_cols[1]:
            if st.button("📊 통계 새로고침", use_container_width=True):
                st.rerun()

        with quick_cols[2]:
            st.button("📤 데이터 내보내기", disabled=True, use_container_width=True)
            st.caption("Coming soon")

    # ═══════════════════════════════════════════════════════════
    # TAB 3: Cleanup Tools
    # ═══════════════════════════════════════════════════════════

    with tab3:
        st.subheader("🧹 정리 도구")

        if not cleanup_manager:
            st.error("⚠️ Neo4j에 연결되어 있지 않아 정리 도구를 사용할 수 없습니다.")
            st.code("docker-compose up -d neo4j", language="bash")
            return

        # Orphan Statistics
        st.markdown("### 📊 고아 데이터 현황")
        st.caption("Paper와 연결되지 않은 노드들입니다.")

        orphan_stats = cleanup_manager.get_orphan_stats()

        if "error" not in orphan_stats:
            orphan_cols = st.columns(5)

            with orphan_cols[0]:
                st.metric("🦠 Pathology", orphan_stats.get("Pathology", 0))
            with orphan_cols[1]:
                st.metric("🦴 Anatomy", orphan_stats.get("Anatomy", 0))
            with orphan_cols[2]:
                st.metric("🎯 Outcome", orphan_stats.get("Outcome", 0))
            with orphan_cols[3]:
                st.metric("🔗 AFFECTS 관계", orphan_stats.get("Orphan_AFFECTS", 0))
            with orphan_cols[4]:
                total = orphan_stats.get("total", 0)
                color = "🟢" if total == 0 else "🟡" if total < 10 else "🔴"
                st.metric(f"{color} 총 고아 데이터", total)

            if orphan_stats.get("total", 0) > 0:
                st.warning(f"⚠️ {orphan_stats['total']}개의 고아 데이터가 있습니다. 정리를 권장합니다.")
        else:
            st.error(f"통계 조회 실패: {orphan_stats.get('error')}")

        st.divider()

        # Cleanup Actions
        st.markdown("### 🧹 정리 작업")

        cleanup_cols = st.columns(2)

        with cleanup_cols[0]:
            st.markdown("**고아 노드 정리**")
            st.caption("Paper와 연결되지 않은 Pathology, Anatomy, Outcome 노드를 삭제합니다.")

            if st.button("🧹 고아 노드 정리", use_container_width=True):
                with st.spinner("정리 중..."):
                    result = cleanup_manager.cleanup_orphan_nodes()

                    if result.success:
                        st.success(f"✅ {result.message}")
                        if result.details:
                            st.json(result.details)
                    else:
                        st.error(f"❌ {result.message}")

        with cleanup_cols[1]:
            st.markdown("**고아 AFFECTS 관계 정리**")
            st.caption("Paper와 연결되지 않은 Intervention의 AFFECTS 관계를 삭제합니다.")

            if st.button("🔗 AFFECTS 관계 정리", use_container_width=True):
                with st.spinner("정리 중..."):
                    result = cleanup_manager.cleanup_orphan_affects_relations()

                    if result.success:
                        st.success(f"✅ {result.message}")
                    else:
                        st.error(f"❌ {result.message}")

        st.divider()

        # SNOMED Code Update
        st.markdown("### 🏥 SNOMED-CT 코드 업데이트")
        st.caption("Intervention 노드에 SNOMED-CT 코드를 매핑합니다. 매핑 파일(spine_snomed_mappings.py)의 정의를 사용합니다.")

        # Current SNOMED stats
        snomed_stats_query = """
        MATCH (i:Intervention)
        WITH count(i) as total
        MATCH (i2:Intervention)
        WHERE i2.snomed_code IS NOT NULL AND i2.snomed_code <> ''
        RETURN total, count(i2) as with_snomed
        """
        snomed_stats = neo4j_client.run_query(snomed_stats_query)

        if snomed_stats:
            total_int = snomed_stats[0].get("total", 0)
            with_snomed = snomed_stats[0].get("with_snomed", 0)
            coverage = (with_snomed / total_int * 100) if total_int > 0 else 0

            snomed_cols = st.columns([2, 1])
            with snomed_cols[0]:
                st.markdown(f"**현재 SNOMED 커버리지**: {with_snomed}/{total_int} ({coverage:.1f}%)")
                st.progress(coverage / 100)
            with snomed_cols[1]:
                if coverage < 100:
                    missing = total_int - with_snomed
                    st.warning(f"⚠️ {missing}개 누락")
                else:
                    st.success("✅ 완료")

        if st.button("🏥 SNOMED 코드 업데이트", type="primary", use_container_width=True):
            with st.spinner("SNOMED 코드 업데이트 중..."):
                result = update_snomed_codes(neo4j_client)

                if result.get("success"):
                    st.success(f"""
                    ✅ **업데이트 완료!**
                    - 업데이트됨: {result.get('updated', 0)}개
                    - 매핑 없음: {result.get('not_found', 0)}개
                    - 최종 커버리지: {result.get('with_snomed', 0)}/{result.get('total', 0)} ({result.get('coverage', 0):.1f}%)
                    """)

                    # Show details in expander
                    if result.get("details"):
                        with st.expander("📋 상세 내역 (처음 20개)"):
                            for detail in result["details"]:
                                st.text(detail)

                    st.rerun()
                else:
                    st.error(f"❌ 업데이트 실패: {result.get('error')}")

        st.divider()

        # All-in-one Cleanup
        st.markdown("### 🔄 전체 정리")

        if st.button("🧹 모든 고아 데이터 정리", type="primary", use_container_width=True):
            with st.spinner("전체 정리 중..."):
                # 1. 고아 노드 정리
                node_result = cleanup_manager.cleanup_orphan_nodes()

                # 2. 고아 AFFECTS 관계 정리
                affects_result = cleanup_manager.cleanup_orphan_affects_relations()

                total_cleaned = node_result.deleted_nodes + affects_result.deleted_relationships

                if node_result.success and affects_result.success:
                    st.success(f"✅ 전체 정리 완료!")
                    st.markdown(f"""
                    **정리 결과:**
                    - 고아 노드: {node_result.deleted_nodes}개 삭제
                    - 고아 AFFECTS 관계: {affects_result.deleted_relationships}개 삭제
                    - **총: {total_cleaned}개 정리됨**
                    """)
                else:
                    st.warning("일부 정리 작업이 실패했습니다.")
                    st.text(f"노드 정리: {node_result.message}")
                    st.text(f"관계 정리: {affects_result.message}")

    # ═══════════════════════════════════════════════════════════
    # TAB 4: Database Reset
    # ═══════════════════════════════════════════════════════════

    with tab4:
        st.subheader("⚠️ 데이터베이스 리셋")
        st.error("**주의**: 이 작업은 되돌릴 수 없습니다!")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 🔄 부분 리셋")
            st.markdown("**Taxonomy(수술법 계층) 보존**")
            st.caption("""
            - 모든 Paper 노드 삭제
            - 관련 Pathology, Anatomy, Outcome 삭제
            - Intervention 계층 구조는 유지
            - Neo4j Chunk 노드 삭제 (v5.3)
            """)

            confirm_partial = st.checkbox("부분 리셋을 확인합니다", key="confirm_partial")

            if st.button(
                "🗑️ 부분 리셋 실행",
                type="secondary",
                disabled=not confirm_partial,
                use_container_width=True
            ):
                with st.spinner("데이터베이스를 리셋하는 중..."):
                    # Neo4j 리셋 (v5.3: 통합 저장소)
                    reset_result = run_async(server.reset_database(include_taxonomy=False))

                    # Additional cleanup if available
                    if cleanup_manager:
                        neo4j_result = cleanup_manager.reset_all_paper_data()
                        neo4j_msg = f"Cleanup: {neo4j_result.deleted_nodes}개 노드 삭제"
                    else:
                        neo4j_msg = ""

                    if reset_result.get("success"):
                        nodes = reset_result.get("neo4j_nodes_deleted", 0)
                        rels = reset_result.get("neo4j_relationships_deleted", 0)
                        st.success(f"""
                        ✅ 부분 리셋 완료!

                        - Neo4j: {nodes}개 노드, {rels}개 관계 삭제
                        - {neo4j_msg}
                        - Taxonomy: 보존됨
                        """)
                        st.balloons()
                    else:
                        st.error(f"❌ 리셋 실패: {reset_result.get('error', 'Unknown error')}")

        with col2:
            st.markdown("### 💣 완전 리셋")
            st.markdown("**Taxonomy 포함 전체 삭제**")
            st.caption("""
            - 모든 노드 삭제
            - 모든 관계 삭제
            - Intervention 계층 구조 삭제
            - Neo4j 완전 초기화 (v5.3)
            - 스키마 재초기화 필요
            """)

            confirm_full = st.checkbox("완전 리셋을 확인합니다", key="confirm_full")
            confirm_full_2 = st.checkbox("정말로 모든 데이터를 삭제합니다", key="confirm_full_2")

            if st.button(
                "💣 완전 리셋 실행",
                type="primary",
                disabled=not (confirm_full and confirm_full_2),
                use_container_width=True
            ):
                with st.spinner("전체 데이터베이스를 리셋하는 중..."):
                    # Neo4j 전체 리셋 (v5.3: 통합 저장소)
                    reset_result = run_async(server.reset_database(include_taxonomy=True))

                    # Additional cleanup if available
                    if cleanup_manager:
                        neo4j_result = cleanup_manager.reset_entire_database()
                        neo4j_msg = f"Cleanup: {neo4j_result.deleted_nodes}개 노드, {neo4j_result.deleted_relationships}개 관계 삭제"
                    else:
                        neo4j_msg = ""

                    if reset_result.get("success"):
                        nodes = reset_result.get("neo4j_nodes_deleted", 0)
                        rels = reset_result.get("neo4j_relationships_deleted", 0)
                        st.success(f"""
                        ✅ 완전 리셋 완료!

                        - Neo4j: {nodes}개 노드, {rels}개 관계 삭제
                        - {neo4j_msg}
                        - Taxonomy: 삭제됨

                        ⚠️ Neo4j 스키마를 재초기화하세요:
                        ```bash
                        python scripts/init_neo4j.py
                        ```
                        """)
                        st.balloons()
                    else:
                        st.error(f"❌ 리셋 실패: {reset_result.get('error', 'Unknown error')}")

    # ═══════════════════════════════════════════════════════════
    # TAB 5: Cypher Console
    # ═══════════════════════════════════════════════════════════

    with tab5:
        st.subheader("💻 Cypher 콘솔")
        st.markdown("**Neo4j 그래프 데이터베이스에 직접 Cypher 쿼리를 실행합니다.**")

        if not neo4j_client:
            st.error("⚠️ Neo4j에 연결되어 있지 않습니다.")
            st.code("docker-compose up -d neo4j", language="bash")
        else:
            # Example Queries
            st.markdown("### 📝 예제 쿼리")

            example_queries = {
                "모든 노드 개수": "MATCH (n) RETURN labels(n)[0] as Label, count(n) as Count ORDER BY Count DESC",
                "모든 관계 개수": "MATCH ()-[r]->() RETURN type(r) as RelationType, count(r) as Count ORDER BY Count DESC",
                "Paper 목록 (최근 10개)": "MATCH (p:Paper) RETURN p.paper_id as ID, p.title as Title, p.year as Year ORDER BY p.year DESC LIMIT 10",
                "Intervention 계층": "MATCH (i:Intervention)-[:IS_A]->(parent:Intervention) RETURN i.name as Intervention, parent.name as Parent ORDER BY parent.name, i.name",
                "AFFECTS 관계": "MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome) RETURN i.name as Intervention, o.name as Outcome, a.value as Value, a.p_value as P_Value, a.direction as Direction LIMIT 20",
                "특정 수술법의 결과": "MATCH (i:Intervention {name: 'TLIF'})-[a:AFFECTS]->(o:Outcome) RETURN o.name as Outcome, a.value as Value, a.p_value as P_Value, a.direction as Direction",
                "SNOMED 코드 있는 Intervention": "MATCH (i:Intervention) WHERE i.snomed_code IS NOT NULL AND i.snomed_code <> '' RETURN i.name as Name, i.snomed_code as SNOMED_Code, i.snomed_term as SNOMED_Term LIMIT 20",
                "Pathology별 수술법": "MATCH (i:Intervention)-[:TREATS]->(p:Pathology) RETURN p.name as Pathology, collect(i.name) as Interventions ORDER BY p.name",
            }

            # Example query selector
            col1, col2 = st.columns([3, 1])

            with col1:
                selected_example = st.selectbox(
                    "예제 선택",
                    options=["직접 입력"] + list(example_queries.keys()),
                    key="example_selector"
                )

            with col2:
                if st.button("예제 적용", use_container_width=True) and selected_example != "직접 입력":
                    st.session_state["cypher_query"] = example_queries[selected_example]

            st.divider()

            # Query Input
            st.markdown("### ✏️ 쿼리 입력")

            # Initialize session state for query (skip if cleared)
            if "cypher_query" not in st.session_state:
                if not st.session_state.get("_cypher_cleared"):
                    st.session_state["cypher_query"] = "MATCH (n) RETURN labels(n)[0] as Label, count(n) as Count ORDER BY Count DESC"
                else:
                    st.session_state["cypher_query"] = ""
                    del st.session_state["_cypher_cleared"]

            cypher_query = st.text_area(
                "Cypher 쿼리",
                value=st.session_state.get("cypher_query", ""),
                height=150,
                placeholder="MATCH (n) RETURN n LIMIT 10"
            )

            # Sync to session state
            st.session_state["cypher_query"] = cypher_query

            # Security: Query length limit (10KB max to prevent DoS)
            MAX_QUERY_LENGTH = 10240
            if len(cypher_query) > MAX_QUERY_LENGTH:
                st.error(f"🚫 쿼리가 너무 깁니다. 최대 {MAX_QUERY_LENGTH} 문자까지 허용됩니다.")
                is_destructive = True
            else:
                is_destructive = False

            # Safety warning for dangerous queries (use word boundaries to avoid false positives)
            dangerous_pattern = r'\b(DELETE|REMOVE|SET|CREATE|MERGE|DROP)\b'
            is_dangerous = bool(re.search(dangerous_pattern, cypher_query.upper()))

            # Additional security: Block highly destructive patterns
            destructive_pattern = r'\b(DETACH\s+DELETE|DROP\s+CONSTRAINT|DROP\s+INDEX|CALL\s+apoc\.|CALL\s+db\.|CALL\s+dbms\.|LOAD\s+CSV|sys\.)\b'
            is_destructive = is_destructive or bool(re.search(destructive_pattern, cypher_query.upper()))

            if is_destructive:
                st.error("🚫 이 쿼리는 보안상 실행이 차단됩니다. (DETACH DELETE, DROP CONSTRAINT, LOAD CSV, CALL apoc/db/dbms 등)")
            elif is_dangerous:
                st.warning("⚠️ 이 쿼리는 데이터를 수정할 수 있습니다. 주의해서 실행하세요!")

            # Read-only mode option
            read_only_mode = st.checkbox(
                "🔒 읽기 전용 모드 (수정 쿼리 차단)",
                value=st.session_state.get("cypher_read_only", True),
                key="cypher_read_only"
            )

            # Execute buttons
            button_cols = st.columns([1, 1, 2])

            with button_cols[0]:
                execute_btn = st.button(
                    "▶️ 실행",
                    type="primary" if not is_dangerous else "secondary",
                    use_container_width=True
                )

            with button_cols[1]:
                if st.button("🗑️ 초기화", use_container_width=True):
                    st.session_state["_cypher_cleared"] = True
                    if "cypher_query" in st.session_state:
                        del st.session_state["cypher_query"]
                    st.session_state["cypher_result"] = None
                    st.rerun()

            # Execute Query
            if execute_btn and cypher_query.strip():
                # Security checks before execution
                if is_destructive:
                    st.error("🚫 이 쿼리는 실행이 차단되었습니다.")
                elif read_only_mode and is_dangerous:
                    st.error("🔒 읽기 전용 모드에서는 데이터 수정 쿼리를 실행할 수 없습니다.")
                else:
                    with st.spinner("쿼리 실행 중..."):
                        try:
                            start_time = time.perf_counter()

                            # Add timeout protection (30 seconds max)
                            import asyncio

                            results = neo4j_client.run_query(cypher_query)

                            execution_time = (time.perf_counter() - start_time) * 1000

                            # Warn if query took too long
                            if execution_time > 5000:
                                st.warning(f"⏱️ 쿼리가 {execution_time/1000:.1f}초 걸렸습니다. 최적화를 고려하세요.")

                            st.session_state["cypher_result"] = {
                                "success": True,
                                "data": results,
                                "time_ms": execution_time,
                                "query": cypher_query
                            }

                        except Exception as e:
                            error_msg = str(e)
                            # Sanitize error message to not expose internal details
                            if "password" in error_msg.lower() or "credential" in error_msg.lower():
                                error_msg = "연결 오류가 발생했습니다."
                            st.session_state["cypher_result"] = {
                                "success": False,
                                "error": error_msg,
                                "query": cypher_query
                            }

            # Display Results
            if "cypher_result" in st.session_state and st.session_state["cypher_result"]:
                result = st.session_state["cypher_result"]

                st.divider()
                st.markdown("### 📊 실행 결과")

                if result.get("success"):
                    data = result.get("data", [])

                    # Metrics
                    metric_cols = st.columns(3)
                    with metric_cols[0]:
                        st.metric("행 수", len(data))
                    with metric_cols[1]:
                        st.metric("실행 시간", f"{result.get('time_ms', 0):.2f} ms")
                    with metric_cols[2]:
                        st.metric("상태", "✅ 성공")

                    if data:
                        # Display format selector
                        display_format = st.radio(
                            "표시 형식",
                            options=["테이블", "JSON"],
                            horizontal=True,
                            key="display_format"
                        )

                        if display_format == "테이블":
                            # Convert to DataFrame for table display
                            # Flatten nested objects for display
                            flat_data = []
                            for row in data:
                                flat_row = {}
                                for key, value in row.items():
                                    if isinstance(value, dict):
                                        # Extract properties from node/relationship
                                        for k, v in value.items():
                                            flat_row[f"{key}.{k}"] = v
                                    elif isinstance(value, list):
                                        flat_row[key] = str(value)
                                    else:
                                        flat_row[key] = value
                                flat_data.append(flat_row)

                            df = pd.DataFrame(flat_data)
                            st.dataframe(df, use_container_width=True)

                            # Download button
                            csv = df.to_csv(index=False)
                            st.download_button(
                                "📥 CSV 다운로드",
                                csv,
                                "cypher_result.csv",
                                "text/csv",
                                use_container_width=True
                            )

                        else:  # JSON
                            st.json(data)

                    else:
                        st.info("쿼리가 성공적으로 실행되었지만 반환된 데이터가 없습니다.")

                else:
                    st.error(f"❌ 쿼리 실행 실패")
                    st.code(result.get("error", "Unknown error"), language="text")

            # Tips
            st.divider()
            with st.expander("💡 Cypher 쿼리 팁"):
                st.markdown("""
                **기본 패턴:**
                - `MATCH (n) RETURN n LIMIT 10` - 노드 조회
                - `MATCH (a)-[r]->(b) RETURN a, r, b` - 관계 조회
                - `MATCH (n:Label) WHERE n.property = 'value'` - 조건 필터링

                **유용한 함수:**
                - `count(n)` - 개수
                - `collect(n.name)` - 배열로 수집
                - `labels(n)` - 노드 라벨
                - `type(r)` - 관계 타입

                **본 시스템의 노드:**
                - `Paper` - 논문 (paper_id, title, year, evidence_level)
                - `Intervention` - 수술법 (name, category, snomed_code)
                - `Outcome` - 결과변수 (name, category, unit)
                - `Pathology` - 질환 (name, category)
                - `Anatomy` - 해부학적 위치 (level, region)

                **본 시스템의 관계:**
                - `STUDIES` - Paper → Pathology
                - `INVESTIGATES` - Paper → Intervention
                - `REPORTS` - Paper → Outcome
                - `AFFECTS` - Intervention → Outcome (value, p_value, direction)
                - `TREATS` - Intervention → Pathology
                - `IS_A` - Intervention → Intervention (계층 구조)

                ⚠️ **주의**: DELETE, CREATE, SET 등의 쿼리는 데이터를 변경합니다!
                """)

    # ═══════════════════════════════════════════════════════════
    # SIDEBAR: About & Debug
    # ═══════════════════════════════════════════════════════════

    with st.sidebar:
        st.subheader("ℹ️ About")

        st.markdown("""
        **Spine GraphRAG** v4.0

        척추 수술 연구를 위한
        지식 그래프 기반 RAG 시스템

        **Features:**
        - 📄 PDF 논문 관리
        - 🔍 하이브리드 검색
        - 📊 Neo4j 지식 그래프
        - 🏥 SNOMED-CT 통합
        - 🧠 근거 기반 추론

        **Tech Stack (v7.2):**
        - Embedding: OpenAI text-embedding-3-large (3072-dim)
        - LLM: Claude Haiku 4.5
        - Graph + Vector DB: Neo4j (통합)
        - Extended Entities: PatientCohort, FollowUp, Cost, QualityMetric
        """)

        st.divider()

        # Debug info (expandable)
        with st.expander("🐛 Debug Info"):
            st.json({
                "llm_enabled": bridge.is_llm_enabled,
                "neo4j_connected": neo4j_client is not None,
                "knowledge_graph_enabled": bridge.has_knowledge_graph,
                "query_expansion_enabled": bridge.has_query_expansion,
                "data_dir": str(server.data_dir),
            })


if __name__ == "__main__":
    main()
