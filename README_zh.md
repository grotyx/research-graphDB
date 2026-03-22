# Spine GraphRAG

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md) | [中文](README_zh.md) | [Español](README_es.md)

**Version**: 1.32.0 | **Status**: Production Ready

基于Neo4j的GraphRAG系统，用于脊柱外科医学文献的结构化知识图谱构建与循证检索。

- **1,030篇** 脊柱外科论文索引
- **735个** SNOMED-CT概念映射（Intervention: 235, Pathology: 231, Outcome: 200, Anatomy: 69）
- **4,065+** 自动化测试
- **10个** MCP工具（Claude Desktop/Code集成）

---

## 架构

```
PDF/Text --> Claude Haiku 4.5 --> SpineMetadata Extraction
                                    |
                  Neo4j（单一存储：Graph + Vector统一）
                  +-- Graph: Paper, Pathology, Intervention, Outcome, Anatomy
                  +-- Vector: HNSW Index (3072d OpenAI embeddings)
                  +-- Ontology: SNOMED-CT IS_A层级 (735个映射)
                  +-- Hybrid Search: Multi-Vector + Graph Filter
                                    |
                  B4 GraphRAG Pipeline (v20, 8阶段)
                  +-- 1. HyDE（假设文档嵌入）
                  +-- 2. Tiered Hybrid Search（Graph + Vector，5倍多样性）
                  +-- 3. LLM Reranker（Claude Haiku）
                  +-- 4. Multi-Vector Search（摘要嵌入，3倍）
                  +-- 5. IS_A Expansion（pathology + 关键词过滤）
                  +-- 6. Graph Traversal Summary（证据链）
                  +-- 7. Graph Hint（系统提示注入）
                  +-- 8. 定量答案生成
```

## 核心功能

### 检索（Retrieval）

- **Neo4j单一存储**: Graph + Vector (HNSW 3072d) 统一检索
- **HyDE**: 假设回答嵌入，提升复杂临床问题的检索精度
- **LLM Reranker**: Claude Haiku对chunk级别相关性进行重新评估
- **Multi-Vector Retrieval**: 融合chunk嵌入与论文摘要嵌入，提升多样性
- **Contextual Embedding Prefix**: `[title | section | year]` 前缀编码chunk上下文
- **Direct Search Keyword Filter**: 自动过滤偏题论文

### 知识图谱

- **SNOMED-CT本体**: 4种实体类型共735个映射及IS_A层级
- **IS_A Expansion**: 病理感知 + 关键词过滤补充相关兄弟论文
- **多跳图遍历**: 证据链、术式比较、shared/unique结局分析
- **Evidence-based Ranking**: 基于p值、效应量、证据等级的排序
- **Graph Hint**: 系统提示中注入intervention-pathology关系一行摘要

### 推理（Reasoning）

- **定量数据提取提示**: 强调提取p值、比值比、置信区间、发生率等具体数值
- **Agentic RAG**: 复杂问题分解为子查询，并行检索后综合推理
- **Evidence Synthesis**: 加权平均效应量、I-squared异质性检验
- **GRADE矛盾检测**: 自动识别研究间相互矛盾的发现

### 导入管线

- **Claude Haiku 4.5** PDF/文本分析（Gemini备选）
- **PubMed书目自动增强**: PubMed、Crossref/DOI、Basic三级回退
- **Entity Normalization**: 280+别名映射，SNOMED-CT自动关联
- **Chunk Validation**: 长度过滤、层级降级、统计验证、近似重复检测

### 集成

- **10个MCP工具**: 与Claude Desktop/Code的SSE集成
- **参考文献格式化**: 7种引用格式（Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard）
- **学术写作指南**: 9个EQUATOR清单（STROBE, CONSORT, PRISMA等）

---

## 快速开始

```bash
# 1. 配置环境
cp .env.example .env
# 在.env中设置 ANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORD

# 2. 启动Neo4j
docker-compose up -d

# 3. 初始化schema（Neo4j启动后等待约30秒）
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. 运行测试
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. 启动Web UI
streamlit run web/app.py
```

## 论文导入（PubMed）

```bash
# PubMed搜索 + 导入（Claude Code CLI）
/pubmed-import lumbar fusion outcomes

# 通过PMID直接导入
/pubmed-import --pmids 41464768,41752698

# 应用SNOMED映射 + TREATS回填
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## MCP服务器

```bash
# Docker启动（端口7777）
docker-compose up -d

# 健康检查
curl http://localhost:7777/health

# 从Claude Code连接
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

### 10个MCP工具

| 工具 | 说明 | 主要操作 |
|------|------|----------|
| `document` | 文档管理 | add_pdf, list, delete, summarize, stats |
| `search` | 搜索/推理 | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI集成 | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | 文本分析 | text, store_paper |
| `graph` | 图探索 | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | 矛盾检测 | find, detect, synthesize（基于GRADE） |
| `intervention` | 术式分析 | hierarchy, compare, comparable |
| `extended` | 扩展实体查询 | patient_cohorts, followup, cost, quality_metrics |
| `reference` | 参考文献格式 | format, format_multiple, list_styles, preview |
| `writing_guide` | 论文写作指南 | section_guide, checklist, expert, draft_response |

## 运维脚本

| 脚本 | 说明 |
|------|------|
| `scripts/init_neo4j.py` | Neo4j schema/索引初始化 |
| `scripts/enrich_graph_snomed.py` | SNOMED代码应用 + TREATS回填 |
| `scripts/repair_isolated_papers.py` | 孤立论文修复（LLM重新分析） |
| `scripts/repair_missing_chunks.py` | HAS_CHUNK缺失Paper修复 |
| `scripts/build_ontology.py` | IS_A层级批量构建 |
| `scripts/normalize_entities.py` | 实体规范化（重复合并） |
| `scripts/backfill_paper_embeddings.py` | Paper摘要嵌入批量生成 |

## 项目结构

```
rag_research/
+-- src/
|   +-- graph/           # Neo4j图层 (client, DAOs, schema, taxonomy)
|   +-- builder/         # PDF/PubMed处理
|   +-- solver/          # 搜索/推理 (tiered_search, hybrid_ranker, reranker)
|   +-- llm/             # LLM客户端 (Claude, Gemini)
|   +-- medical_mcp/     # MCP服务器 + 11个领域处理器
|   +-- core/            # 配置/日志/异常/嵌入/缓存
|   +-- cache/           # 缓存 (query, embedding, semantic)
|   +-- ontology/        # SNOMED-CT本体 (735个映射)
|   +-- orchestrator/    # 查询路由/Cypher生成
|   +-- external/        # 外部API (PubMed)
+-- evaluation/          # 基准测试框架
+-- scripts/             # 运维脚本
+-- web/                 # Streamlit UI
+-- tests/               # 4,065+ 测试
+-- docs/                # 文档
```

## 环境变量

```bash
# 参见 .env.example
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large, 3072d)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
LLM_MAX_CONCURRENT=5              # LLM并发调用数 (1-20)
PUBMED_MAX_CONCURRENT=5           # PubMed并发处理数 (1-10)
EMBEDDING_CONTEXTUAL_PREFIX=true  # 启用Contextual embedding前缀
```

## 文档

| 文档 | 用途 |
|------|------|
| [CHANGELOG](docs/CHANGELOG.md) | 版本历史 |
| [PRD](docs/PRD.md) | 产品需求文档 |
| [TRD](docs/TRD_v3_GraphRAG.md) | 技术规范 |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | 节点/关系schema |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCP工具使用指南 |
| [ROADMAP](docs/ROADMAP.md) | 开发路线图 |

## 作者

**朴相旼 教授, M.D., Ph.D.**

首尔大学医学院骨科学教室，首尔大学盆唐医院骨科

[https://sangmin.me/](https://sangmin.me/)

## 许可证

本项目仅供**研究和个人使用**。未经事先书面同意，不得用于商业用途。

详情请参阅 [LICENSE](LICENSE)。

Copyright (c) 2024-2026 Sangmin Park
