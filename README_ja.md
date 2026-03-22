# Spine GraphRAG

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md) | [中文](README_zh.md) | [Español](README_es.md)

**Version**: 1.32.0 | **Status**: Production Ready

Neo4jベースのGraphRAGシステムです。脊椎外科分野の医学論文から構造化されたナレッジグラフを構築し、エビデンスに基づく検索を支援します。

- **1,030編** の脊椎外科論文をインデックス化
- **735個** のSNOMED-CTコンセプトマッピング（Intervention: 235, Pathology: 231, Outcome: 200, Anatomy: 69）
- **4,065+** の自動テスト
- **10個** のMCPツール（Claude Desktop/Code連携）

---

## アーキテクチャ

```
PDF/Text --> Claude Haiku 4.5 --> SpineMetadata Extraction
                                    |
                  Neo4j（単一ストア：Graph + Vector統合）
                  +-- Graph: Paper, Pathology, Intervention, Outcome, Anatomy
                  +-- Vector: HNSW Index (3072d OpenAI embeddings)
                  +-- Ontology: SNOMED-CT IS_A階層 (735マッピング)
                  +-- Hybrid Search: Multi-Vector + Graph Filter
                                    |
                  B4 GraphRAG Pipeline (v20, 8ステージ)
                  +-- 1. HyDE（仮想文書埋め込み）
                  +-- 2. Tiered Hybrid Search（Graph + Vector、5倍多様性）
                  +-- 3. LLM Reranker（Claude Haiku）
                  +-- 4. Multi-Vector Search（abstract埋め込み、3倍）
                  +-- 5. IS_A Expansion（pathology + キーワードフィルタ）
                  +-- 6. Graph Traversal Summary（エビデンスチェーン）
                  +-- 7. Graph Hint（システムプロンプト注入）
                  +-- 8. 定量的回答生成
```

## 主要機能

### 検索（Retrieval）

- **Neo4j単一ストア**: Graph + Vector (HNSW 3072d) 統合検索
- **HyDE**: 仮想回答埋め込みにより、複雑な臨床質問の検索精度を向上
- **LLM Reranker**: Claude Haikuによるチャンクレベルの関連性再評価
- **Multi-Vector Retrieval**: チャンク + 論文アブストラクト埋め込みの融合
- **Contextual Embedding Prefix**: `[title | section | year]` プレフィックスでチャンクの文脈を反映
- **Direct Search Keyword Filter**: オフトピック論文の自動除去

### ナレッジグラフ

- **SNOMED-CTオントロジー**: 4つのエンティティタイプにわたる735個のマッピングとIS_A階層
- **IS_A Expansion**: pathology対応 + キーワードフィルタによる関連兄弟論文の補充
- **マルチホップグラフ探索**: エビデンスチェーン、Intervention比較、shared/uniqueアウトカム分析
- **Evidence-based Ranking**: p値、効果量、エビデンスレベルに基づくランキング
- **Graph Hint**: システムプロンプトにintervention-pathology関係の1行要約を注入

### 推論（Reasoning）

- **定量データ抽出プロンプト**: p値、オッズ比、信頼区間、発生率の具体的数値を抽出
- **Agentic RAG**: 複雑な質問をサブクエリに分解し、並列検索後に統合推論
- **Evidence Synthesis**: 加重平均効果量、I-squared異質性検定
- **GRADE準拠の矛盾検出**: 研究間の矛盾する知見を自動識別

### インポートパイプライン

- **Claude Haiku 4.5** によるPDF/テキスト分析（Geminiフォールバック付き）
- **PubMed書誌情報自動強化**: PubMed、Crossref/DOI、Basic 3段階フォールバック
- **Entity Normalization**: 280以上のエイリアスマッピング、SNOMED-CT自動リンク
- **Chunk Validation**: 長さフィルタ、ティア降格、統計検証、近接重複検出

### 統合

- **10個のMCPツール**: Claude Desktop/CodeとのSSE連携
- **参考文献フォーマット**: 7スタイル（Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard）
- **学術論文作成ガイド**: 9つのEQUATORチェックリスト（STROBE, CONSORT, PRISMAなど）

---

## クイックスタート

```bash
# 1. 環境設定
cp .env.example .env
# .envにANTHROPIC_API_KEY, OPENAI_API_KEY, NEO4J_PASSWORDを設定

# 2. Neo4j起動
docker-compose up -d

# 3. スキーマ初期化（Neo4j起動後約30秒待機）
PYTHONPATH=./src python3 scripts/init_neo4j.py

# 4. テスト実行
PYTHONPATH=./src python3 -m pytest tests/ --ignore=tests/archive --tb=short -q

# 5. Web UI起動
streamlit run web/app.py
```

## 論文インポート（PubMed）

```bash
# PubMed検索 + インポート（Claude Code CLI）
/pubmed-import lumbar fusion outcomes

# PMIDで直接インポート
/pubmed-import --pmids 41464768,41752698

# SNOMEDマッピング + TREATSバックフィル
PYTHONPATH=./src python3 scripts/enrich_graph_snomed.py
```

## MCPサーバー

```bash
# Dockerで起動（ポート7777）
docker-compose up -d

# ヘルスチェック
curl http://localhost:7777/health

# Claude Codeから接続
claude mcp add --transport sse medical-kag-remote http://localhost:7777/sse --scope project
```

### 10個のMCPツール

| ツール | 説明 | 主要アクション |
|--------|------|---------------|
| `document` | 文書管理 | add_pdf, list, delete, summarize, stats |
| `search` | 検索/推論 | search, graph, adaptive, evidence, reason, clinical_recommend |
| `pubmed` | PubMed/DOI連携 | search, import_by_pmids, fetch_by_doi, upgrade_pdf |
| `analyze` | テキスト分析 | text, store_paper |
| `graph` | グラフ探索 | relations, evidence_chain, compare, multi_hop, draft_citations |
| `conflict` | 矛盾検出 | find, detect, synthesize（GRADE準拠） |
| `intervention` | 術式分析 | hierarchy, compare, comparable |
| `extended` | 拡張エンティティ | patient_cohorts, followup, cost, quality_metrics |
| `reference` | 参考文献フォーマット | format, format_multiple, list_styles, preview |
| `writing_guide` | 論文作成ガイド | section_guide, checklist, expert, draft_response |

## 運用スクリプト

| スクリプト | 説明 |
|-----------|------|
| `scripts/init_neo4j.py` | Neo4jスキーマ/インデックス初期化 |
| `scripts/enrich_graph_snomed.py` | SNOMEDコード適用 + TREATSバックフィル |
| `scripts/repair_isolated_papers.py` | 孤立論文の修復（LLM再分析） |
| `scripts/repair_missing_chunks.py` | HAS_CHUNK欠損Paperの修復 |
| `scripts/build_ontology.py` | IS_A階層の一括構築 |
| `scripts/normalize_entities.py` | エンティティ正規化（重複統合） |
| `scripts/backfill_paper_embeddings.py` | Paper abstract埋め込みのバッチ生成 |

## プロジェクト構成

```
rag_research/
+-- src/
|   +-- graph/           # Neo4jグラフレイヤー (client, DAOs, schema, taxonomy)
|   +-- builder/         # PDF/PubMed処理
|   +-- solver/          # 検索/推論 (tiered_search, hybrid_ranker, reranker)
|   +-- llm/             # LLMクライアント (Claude, Gemini)
|   +-- medical_mcp/     # MCPサーバー + 11ドメインハンドラー
|   +-- core/            # 設定/ロギング/例外/埋め込み/キャッシュ
|   +-- cache/           # キャッシング (query, embedding, semantic)
|   +-- ontology/        # SNOMED-CTオントロジー (735マッピング)
|   +-- orchestrator/    # クエリルーティング/Cypher生成
|   +-- external/        # 外部API (PubMed)
+-- evaluation/          # ベンチマークフレームワーク
+-- scripts/             # 運用スクリプト
+-- web/                 # Streamlit UI
+-- tests/               # 4,065+ テスト
+-- docs/                # ドキュメント
```

## 環境変数

```bash
# .env.example参照
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
OPENAI_API_KEY=sk-...             # Embeddings (text-embedding-3-large, 3072d)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
LLM_MAX_CONCURRENT=5              # LLM同時呼び出し数 (1-20)
PUBMED_MAX_CONCURRENT=5           # PubMed同時処理数 (1-10)
EMBEDDING_CONTEXTUAL_PREFIX=true  # Contextual embedding prefix有効化
```

## ドキュメント

| 文書 | 用途 |
|------|------|
| [CHANGELOG](docs/CHANGELOG.md) | バージョン履歴 |
| [PRD](docs/PRD.md) | 製品要件定義 |
| [TRD](docs/TRD_v3_GraphRAG.md) | 技術仕様書 |
| [GRAPH_SCHEMA](docs/GRAPH_SCHEMA.md) | ノード/リレーションシップスキーマ |
| [MCP_USAGE_GUIDE](docs/MCP_USAGE_GUIDE.md) | MCPツール使用ガイド |
| [ROADMAP](docs/ROADMAP.md) | 開発ロードマップ |

## 著者

**朴 相敏 教授, M.D., Ph.D.**

ソウル大学校医科大学 整形外科学教室、ソウル大学校盆唐ソウル大学校病院 整形外科

[https://sangmin.me/](https://sangmin.me/)

## ライセンス

本プロジェクトは**研究および個人使用目的のみ**で提供されています。商業利用は事前の書面による同意なしに許可されません。

詳細は [LICENSE](LICENSE) をご参照ください。

Copyright (c) 2024-2026 Sangmin Park
