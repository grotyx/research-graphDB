# v6 Complex Extraction Archive

**Archived on**: 2025-12-18
**Reason**: Replaced by v7.0 Simplified Processing Pipeline
**Status**: Reference only - do not restore without consulting CLAUDE.md

## What Was Archived

This directory contains the complex statistical extraction code from v6 that has been replaced by a simplified v7.0 approach that relies on statistical analysis tools rather than complex LLM extraction.

## Archived Components

### 1. Complex PICO Extraction Prompts
- **Location**: `unified_pdf_processor.py` lines 529-534
- **What it did**: Detailed PICO (Population, Intervention, Comparison, Outcome) extraction at paper level
- **Why archived**: PICO is now extracted by analysis tools, not LLM

### 2. Statistical Extraction Schemas
- **Location**: `unified_pdf_processor.py` lines 103-135
- **What it did**: Extracted complex effect measures (HR, OR, RR, MD, SMD, NNT, I², Cohen's d, etc.)
- **Fields extracted**:
  - `EffectMeasure` dataclass (measure_type, value, ci_lower, ci_upper, label)
  - `StatisticsData.effect_measure` field
  - `ExtractedOutcome.effect_measure` field
- **Why archived**: Statistical values now come from dedicated analysis tools

### 3. Study Type Detector
- **File**: `study_type_detector.py` (308 lines)
- **What it did**: Rule-based detection of study types (RCT, cohort, meta-analysis, etc.)
- **Components**:
  - MeSH term mapping to study types
  - Publication type mapping
  - Abstract keyword pattern matching
  - Recommended effect measures per study type
- **Why archived**: Study classification is simplified, effect measures come from analysis

### 4. Complex LLM Prompts
- **Location**: `unified_pdf_processor.py` lines 582-619
- **What it did**: Detailed instructions for extracting effect measures based on study type
- **Table of study types**:
  - RCT → MD, SMD, Cohen's d, RR
  - Cohort → HR, RR, OR
  - Case-control → OR
  - Cross-sectional → OR, PR
  - Meta-analysis → SMD, MD, OR, RR, I²
  - Survival analysis → HR, Median survival
- **Why archived**: Analysis tools provide this automatically

## Original Statistical Fields Schema

### EffectMeasure (v3.2)
```python
@dataclass
class EffectMeasure:
    measure_type: str  # HR, OR, RR, MD, SMD, NNT, I2, Cohen_d, r, eta2, other
    value: str         # "2.35"
    ci_lower: str      # "1.42"
    ci_upper: str      # "3.89"
    label: str         # "HR 2.35 (95% CI: 1.42-3.89)"
```

### StatisticsData (v3.2)
```python
@dataclass
class StatisticsData:
    p_value: str                       # "0.001", "<0.001"
    is_significant: bool               # p < 0.05
    effect_measure: Optional[EffectMeasure]  # Structured effect measure
    additional: str                    # "95% CI: 1.2-3.4"
```

### ExtractedOutcome (v3.2)
```python
@dataclass
class ExtractedOutcome:
    name: str              # VAS, ODI, JOA
    category: str          # pain, function, radiologic
    value_intervention: str
    value_control: str
    value_difference: str
    p_value: str
    confidence_interval: str
    effect_size: str       # Backward compatibility
    effect_measure: Optional[EffectMeasure]  # v3.2 structured
    timepoint: str
    is_significant: bool
    direction: str
```

## Study Type Detection Logic

### Confidence Levels
- MeSH Terms: 0.95 confidence
- Publication Types: 0.9 confidence
- Keyword patterns: 0.5-0.95 depending on specificity

### Detection Sources
1. **MeSH Terms**: "Meta-Analysis", "Randomized Controlled Trial", "Cohort Studies", etc.
2. **Publication Types**: Direct mapping from PubMed publication types
3. **Keyword Patterns**: Regex matching in abstracts/titles
   - "randomized controlled trial" → RCT (0.95)
   - "meta-analysis" → Meta-analysis (0.9)
   - "hazard ratio", "kaplan-meier" → Cohort (0.6)

## Effect Measures by Study Type

| Study Type | Effect Measures |
|------------|----------------|
| Meta-analysis | SMD, MD, OR, RR, HR, I² |
| Systematic Review | SMD, MD, OR, RR, HR |
| RCT | MD, SMD, Cohen's d, RR, NNT |
| Prospective Cohort | HR, RR, OR, NNT |
| Retrospective Cohort | HR, OR, RR |
| Case-Control | OR |
| Cross-Sectional | OR, PR (Prevalence Ratio) |
| Case Series/Report | Descriptive only |

## v7.0 Simplified Approach

### What's Different
- **No complex effect measure extraction**: LLM extracts simple p-values and directions
- **Analysis tool integration**: Statistical values come from dedicated analysis tools
- **Study type simplification**: Basic classification only (meta-analysis, RCT, cohort, other)
- **Reduced prompt complexity**: ~50% shorter extraction prompt
- **Faster processing**: Less LLM token usage, faster extraction

### Migration Path
If you need to restore complex extraction:
1. Copy files from this archive
2. Review `unified_pdf_processor.py` EXTRACTION_PROMPT (lines 346-620)
3. Restore `EffectMeasure` dataclass
4. Restore `study_type_detector.py` module
5. Update prompts to include effect measure tables
6. Test with representative papers

## Files in This Archive

```
v6_complex_extraction/
├── README.md                          # This file
├── prompts/
│   └── extraction_prompt_v6.txt       # Full v6 LLM prompt
├── schemas/
│   ├── effect_measure.py              # EffectMeasure dataclass
│   ├── statistics_data.py             # StatisticsData with effect_measure
│   └── extracted_outcome.py           # ExtractedOutcome with effect_measure
├── modules/
│   └── study_type_detector.py         # Study type detection module
└── examples/
    ├── study_type_detection.py        # Usage examples
    └── effect_measure_extraction.py   # Example extractions
```

## Important Notes

1. **Do not restore without approval**: v7.0 architecture assumes simplified extraction
2. **Analysis tools required**: v7.0 relies on external statistical analysis
3. **Schema compatibility**: v7.0 schemas are incompatible with v6 effect_measure structure
4. **Token savings**: v6 used ~30% more tokens due to complex extraction
5. **Maintenance burden**: v6 required constant updates to study type patterns

## Contact

For questions about this archive or restoration procedures, refer to:
- `CLAUDE.md` - Project rules and architecture
- `docs/Development_Status_v3.md` - Current development status
- Phase 21 planning documents (when created)

---
*Archive created as part of Phase 21: Simplified Processing Pipeline*
