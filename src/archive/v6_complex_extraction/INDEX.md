# v6 Complex Extraction Archive - Quick Index

**Quick Navigation Guide for Archived v6 Complex Extraction Code**

---

## Start Here

1. **New to this archive?** → Read [README.md](README.md)
2. **Need statistical field reference?** → See [STATISTICAL_FIELDS_SUMMARY.md](STATISTICAL_FIELDS_SUMMARY.md)
3. **Planning restoration?** → Check [ARCHIVE_SUMMARY.md](ARCHIVE_SUMMARY.md)
4. **Looking for examples?** → Browse [examples/](#examples)

---

## Documentation Files

### Core Documentation
- **[README.md](README.md)** - Main archive documentation, why archived, what's different in v7.0
- **[ARCHIVE_SUMMARY.md](ARCHIVE_SUMMARY.md)** - Complete archive overview, statistics, restoration guide
- **[STATISTICAL_FIELDS_SUMMARY.md](STATISTICAL_FIELDS_SUMMARY.md)** - All statistical fields that existed in v6
- **[INDEX.md](INDEX.md)** - This file (quick navigation)

---

## Code Files

### Schemas (Dataclasses)
| File | Description | Lines | Key Classes |
|------|-------------|-------|-------------|
| [schemas/effect_measure.py](schemas/effect_measure.py) | Effect measure dataclass | 80 | `EffectMeasure` |
| [schemas/statistics_data.py](schemas/statistics_data.py) | Statistics with effect measure | 150 | `StatisticsData` |
| [schemas/extracted_outcome.py](schemas/extracted_outcome.py) | Outcome with effect measure | 200 | `ExtractedOutcome` |

### Modules (Detection Logic)
| File | Description | Lines | Key Classes |
|------|-------------|-------|-------------|
| [modules/study_type_detector.py](modules/study_type_detector.py) | Study type detection | 308 | `StudyTypeDetector`, `StudyType` |

### Prompts
| File | Description |
|------|-------------|
| [prompts/extraction_prompt_v6.txt](prompts/extraction_prompt_v6.txt) | Effect measure extraction table and instructions |

---

## Examples

### Usage Examples
| File | Description | What It Shows |
|------|-------------|---------------|
| [examples/study_type_detection.py](examples/study_type_detection.py) | Study type detection examples | RCT, cohort, meta-analysis detection |
| [examples/effect_measure_extraction.py](examples/effect_measure_extraction.py) | Effect measure parsing examples | HR, OR, MD, SMD parsing |

### Running Examples
```bash
# Study type detection
cd /Users/sangminpark/Desktop/rag_research
python src/archive/v6_complex_extraction/examples/study_type_detection.py

# Effect measure extraction
python src/archive/v6_complex_extraction/examples/effect_measure_extraction.py
```

---

## Quick Reference Tables

### Effect Measures Supported

| Code | Measure | Study Type | Example |
|------|---------|------------|---------|
| `HR` | Hazard Ratio | Cohort, Survival | `HR 2.35 (95% CI: 1.42-3.89)` |
| `OR` | Odds Ratio | Case-control, Meta | `OR 3.2 (95% CI: 1.8-5.6)` |
| `RR` | Relative Risk | Cohort, RCT | `RR 1.06 (95% CI: 0.97-1.15)` |
| `MD` | Mean Difference | RCT | `MD -1.4 (95% CI: -2.1 to -0.7)` |
| `SMD` | Std Mean Diff | Meta-analysis | `SMD -0.45 (95% CI: -0.67 to -0.23)` |
| `NNT` | Number Needed to Treat | RCT | `NNT 5 (95% CI: 3-8)` |
| `I2` | I-squared | Meta-analysis | `I²=42%` |
| `Cohen_d` | Cohen's d | RCT | `Cohen's d = 0.8` |

### Study Types Detected

| Study Type | Confidence Sources | Recommended Measures |
|------------|-------------------|---------------------|
| Meta-analysis | MeSH, PubType, Keywords | SMD, MD, OR, RR, HR, I² |
| RCT | MeSH, PubType, Keywords | MD, SMD, Cohen_d, RR, NNT |
| Prospective Cohort | MeSH, PubType, Keywords | HR, RR, OR, NNT |
| Retrospective Cohort | MeSH, PubType, Keywords | HR, OR, RR |
| Case-Control | MeSH, PubType, Keywords | OR |
| Cross-Sectional | MeSH, PubType, Keywords | OR, PR |

---

## Common Tasks

### Find Specific Information

**Need to know what fields were extracted?**
→ [STATISTICAL_FIELDS_SUMMARY.md](STATISTICAL_FIELDS_SUMMARY.md) - Section "StatisticsData Dataclass"

**Want to see study type mapping?**
→ [STATISTICAL_FIELDS_SUMMARY.md](STATISTICAL_FIELDS_SUMMARY.md) - Section "Study Type to Effect Measure Mapping"

**Looking for example code?**
→ [examples/effect_measure_extraction.py](examples/effect_measure_extraction.py)

**Need to restore v6 code?**
→ [ARCHIVE_SUMMARY.md](ARCHIVE_SUMMARY.md) - Section "Restoration Procedure"

**Want to compare v6 vs v7?**
→ [README.md](README.md) - Section "v7.0 Simplified Approach"

---

## Statistics at a Glance

```
📊 Archive Statistics
├── Files: 11 total
│   ├── Documentation: 4 files
│   ├── Code (schemas): 3 files
│   ├── Code (modules): 1 file
│   ├── Prompts: 1 file
│   └── Examples: 2 files
├── Lines of Code: ~2,000 lines archived
├── Effect Measures: 10 types supported
├── Study Types: 11 types detected
└── Token Savings (v7): 22.8% reduction
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2025-12-18 | Initial archive creation |

---

## See Also

### Related Documentation
- `/Users/sangminpark/Desktop/rag_research/CLAUDE.md` - Project rules
- `/Users/sangminpark/Desktop/rag_research/docs/Development_Status_v3.md` - Current status
- `/Users/sangminpark/Desktop/rag_research/docs/TRD_v3_GraphRAG.md` - Technical specs

### Original Source Files (v6)
- `src/builder/unified_pdf_processor.py` (lines 103-620) - Effect measure extraction
- `src/builder/study_type_detector.py` (308 lines) - Study type detection
- `src/graph/spine_schema.py` (lines 169-195) - ExtractedOutcome schema

---

**Last Updated**: 2025-12-18
**Status**: Complete and ready for Phase 21 development
