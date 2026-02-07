# Legacy v7 Archive

> **Archived**: 2026-01-13
> **Reason**: Superseded by current implementation

This directory contains legacy code that has been archived for historical reference.

## Archived Files

| File | Original Location | Reason |
|------|-------------------|--------|
| `unified_processor_v7.py` | src/builder/ | Superseded by unified_pdf_processor.py |
| `graph_rag_v2.py` | src/solver/ | Microsoft-style GraphRAG experiment, not in production |
| `README_graph_rag_v2.md` | src/solver/ | Documentation for graph_rag_v2.py |

## Do Not Use

These files are kept for historical reference only. Do not import or use them in production code.

## Migration Notes

- `unified_processor_v7.py` → Use `src/builder/unified_pdf_processor.py`
- `graph_rag_v2.py` → Use current solver modules in `src/solver/`
