"""Evaluation framework for Spine GraphRAG benchmark.

Provides metrics, baselines, and benchmark runner for comparing
retrieval performance across search modes:
  B1: Keyword search (fulltext index)
  B2: Vector-only search (embedding similarity)
  B3: LLM direct (no Knowledge Graph)
  B4: GraphRAG (full hybrid system)
"""
