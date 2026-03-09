# Statistical Fields Summary (v6 Archive)

**Archived on**: 2025-12-18
**Purpose**: Document all statistical fields that were extracted in v6 for future reference

## Overview

v6 supported complex statistical extraction with multiple effect measures tailored to different study types. This document summarizes all the fields that were being extracted before simplification in v7.0.

## EffectMeasure Dataclass

```python
@dataclass
class EffectMeasure:
    measure_type: str  # Type of effect measure
    value: str         # Numeric value
    ci_lower: str      # 95% CI lower bound
    ci_upper: str      # 95% CI upper bound
    label: str         # Complete formatted string
```

### Supported Measure Types

| Type | Full Name | Study Types | Example |
|------|-----------|-------------|---------|
| `HR` | Hazard Ratio | Cohort, Survival analysis | "HR 2.35 (95% CI: 1.42-3.89)" |
| `OR` | Odds Ratio | Case-control, Meta-analysis | "OR 3.2 (95% CI: 1.8-5.6)" |
| `RR` | Relative Risk | Cohort, RCT | "RR 1.06 (95% CI: 0.97-1.15)" |
| `MD` | Mean Difference | RCT, Continuous outcomes | "MD -1.4 (95% CI: -2.1 to -0.7)" |
| `SMD` | Standardized Mean Difference | Meta-analysis | "SMD -0.45 (95% CI: -0.67 to -0.23)" |
| `NNT` | Number Needed to Treat | RCT, Clinical utility | "NNT 5 (95% CI: 3-8)" |
| `I2` | I-squared | Meta-analysis | "I²=42%" |
| `Cohen_d` | Cohen's d | RCT, Effect size | "Cohen's d = 0.8" |
| `r` | Correlation coefficient | Correlation studies | "r = 0.65 (p<0.001)" |
| `eta2` | Eta-squared | ANOVA, Effect size | "η² = 0.14" |
| `other` | Other measures | Various | Custom format |

## StatisticsData Dataclass

```python
@dataclass
class StatisticsData:
    p_value: str                       # Primary p-value
    is_significant: bool               # p < 0.05 flag
    effect_measure: Optional[EffectMeasure]  # Structured measure
    additional: str                    # Additional statistics
```

### Fields Breakdown

#### p_value (str)
- **Purpose**: Primary statistical significance value
- **Format**: String (e.g., "0.001", "<0.001", "0.023", "NS")
- **Examples**:
  - Exact: "0.001", "0.023", "0.456"
  - Inequality: "<0.001", ">0.05"
  - Not reported: "NS", "NR"

#### is_significant (bool)
- **Purpose**: Quick flag for statistical significance
- **Rule**: `True` if p < 0.05, `False` otherwise
- **Usage**: Filtering, color coding in UI

#### effect_measure (Optional[EffectMeasure])
- **Purpose**: Structured representation of effect size
- **Optional**: Can be `None` for descriptive studies
- **Components**: measure_type, value, ci_lower, ci_upper, label

#### additional (str)
- **Purpose**: Catch-all for other statistical info
- **Examples**:
  - "95% CI: 1.2-3.4"
  - "Cohen's d = 0.8"
  - "Median survival: 24 months"
  - "I²=42%, heterogeneity: moderate"
  - "Adjusted for age, BMI, smoking"

## ExtractedOutcome Dataclass

```python
@dataclass
class ExtractedOutcome:
    # Identity
    name: str              # Outcome variable name
    category: str          # Outcome category

    # Values
    value_intervention: str
    value_control: str
    value_difference: str

    # Statistics
    p_value: str
    confidence_interval: str
    effect_size: str       # Backward compatibility
    effect_measure: Optional[EffectMeasure]  # v3.2 structured

    # Context
    timepoint: str
    is_significant: bool
    direction: str
```

### Outcome Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `pain` | Pain measures | VAS, NRS, back pain VAS, leg pain VAS |
| `function` | Functional outcomes | ODI, NDI, JOA, mJOA, EQ-5D, SF-36 |
| `radiologic` | Imaging outcomes | Fusion rate, Cobb angle, lordosis, SVA |
| `complication` | Adverse events | Dural tear, infection, nerve injury |
| `satisfaction` | Patient satisfaction | MacNab, return to work |
| `quality_of_life` | QoL measures | EQ-5D, SF-36, SF-12, WHOQOL |
| `survival` | Survival outcomes | Overall survival, PFS, DFS |
| `event_rate` | Event incidence | Recurrence, revision, mortality |

### Timepoint Values

| Timepoint | Description |
|-----------|-------------|
| `preop` | Pre-operative baseline |
| `postop` | Immediately post-operative |
| `1mo` | 1 month follow-up |
| `3mo` | 3 months follow-up |
| `6mo` | 6 months follow-up |
| `1yr` | 1 year follow-up |
| `2yr` | 2 years follow-up |
| `final` | Final follow-up (variable) |

### Direction Values

| Direction | Interpretation |
|-----------|----------------|
| `improved` | Significant improvement from baseline/control |
| `worsened` | Significant deterioration from baseline/control |
| `unchanged` | No significant change (p >= 0.05) |

## Study Type to Effect Measure Mapping

```python
STUDY_TYPE_MEASURES = {
    "meta-analysis": ["SMD", "MD", "OR", "RR", "HR", "I2"],
    "systematic-review": ["SMD", "MD", "OR", "RR", "HR"],
    "RCT": ["MD", "SMD", "Cohen_d", "RR", "NNT"],
    "prospective-cohort": ["HR", "RR", "OR", "NNT"],
    "retrospective-cohort": ["HR", "OR", "RR"],
    "case-control": ["OR"],
    "cross-sectional": ["OR", "PR"],
    "case-series": ["descriptive"],
    "case-report": ["descriptive"],
    "expert-opinion": ["descriptive"],
    "unknown": ["MD", "OR", "HR", "RR"],
}
```

### Rationale for Mapping

#### Meta-analysis
- **SMD**: Standardizes across different scales (primary)
- **MD**: When all studies use same scale
- **OR/RR/HR**: Binary/time-to-event outcomes
- **I²**: Heterogeneity assessment

#### RCT
- **MD**: Continuous outcomes (primary)
- **SMD**: Meta-analysis compatibility
- **Cohen's d**: Effect size interpretation
- **RR**: Binary outcomes
- **NNT**: Clinical utility

#### Prospective Cohort
- **HR**: Time-to-event outcomes (primary)
- **RR**: Binary outcomes at fixed time
- **OR**: Case-control nested design
- **NNT**: Clinical utility

#### Retrospective Cohort
- **HR**: Survival analysis
- **OR**: Binary outcomes (common in retrospective)
- **RR**: Less common (requires incidence data)

#### Case-Control
- **OR**: Only valid measure (cannot calculate incidence)

#### Cross-Sectional
- **OR**: Prevalence odds ratio
- **PR**: Prevalence ratio (preferred)

## Extraction Prompt Features (v6)

### Study Type Recognition Table

The v6 prompt included this comprehensive table:

```markdown
| Study Type | Primary Effect Measures | Examples |
|------------|------------------------|----------|
| RCT | MD, SMD, Cohen's d, RR | "MD -1.4 (95% CI: -2.1 to -0.7)", "Cohen's d = 0.8" |
| Cohort | HR, RR, OR | "HR 2.35 (95% CI: 1.42-3.89)" |
| Case-control | OR | "OR 3.2 (95% CI: 1.8-5.6)" |
| Cross-sectional | OR, PR | "OR 1.85 (95% CI: 1.2-2.8)" |
| Meta-analysis | SMD, MD, OR, RR, I² | "SMD -0.45 (95% CI: -0.67 to -0.23), I²=42%" |
| Survival analysis | HR, Median survival | "HR 0.72 (95% CI: 0.58-0.89), median 24 months" |
```

### Statistics Field Instructions

```markdown
**Statistics Fields:**
- **p_value**: The most representative p-value (string, e.g., "0.001", "<0.001")
- **is_significant**: Boolean (true if p < 0.05)
- **effect_measure**: Structured effect measure object:
  - measure_type: "HR/OR/RR/MD/SMD/NNT/I2/Cohen_d/r/other"
  - value: numeric value as string (e.g., "2.35")
  - ci_lower: lower 95% CI bound (e.g., "1.42")
  - ci_upper: upper 95% CI bound (e.g., "3.89")
  - label: complete formatted string (e.g., "HR 2.35 (95% CI: 1.42-3.89)")
- **additional**: Other statistics as a single string (e.g., "NNT=5, I²=42%")
```

## Token Usage Comparison

### v6 Extraction (Complex)
- **Average tokens per paper**: ~8,500 input + 4,200 output = 12,700 total
- **Prompt size**: ~4,200 tokens (includes effect measure table + instructions)
- **JSON schema**: ~1,800 tokens
- **LLM processing time**: ~45 seconds average

### v7 Extraction (Simplified)
- **Average tokens per paper**: ~6,800 input + 3,000 output = 9,800 total
- **Reduction**: ~22.8% token savings
- **Prompt size**: ~2,800 tokens (removed effect measure complexity)
- **JSON schema**: ~1,200 tokens
- **LLM processing time**: ~32 seconds average

## What Was Lost in v7.0

### Removed Features
1. **Structured Effect Measures**: No more HR/OR/RR/SMD with CI bounds
2. **Study Type-Specific Measures**: No automatic measure selection
3. **Statistical Validation**: No confidence interval extraction
4. **Measure Type Detection**: No automatic HR vs OR distinction
5. **Additional Statistics Field**: No catch-all for extra stats

### What Remains in v7.0
1. **Basic p-values**: Simple string format
2. **Significance flag**: Boolean for p < 0.05
3. **Outcome directions**: improved/worsened/unchanged
4. **Outcome values**: Intervention vs control values

## Migration to Analysis Tools

### v7.0 Approach
Instead of extracting complex statistics from LLM, v7.0 will:

1. **Extract basic info from LLM**:
   - Outcome names (VAS, ODI, fusion rate)
   - p-values (basic format)
   - Directions (improved/worsened)

2. **Use statistical analysis tools** for:
   - Calculating effect sizes
   - Extracting confidence intervals
   - Computing meta-analysis summaries
   - Determining appropriate measures by study type

3. **Benefits**:
   - More accurate statistical values
   - Faster LLM processing
   - Reduced token costs
   - Easier to update/maintain
   - Tools handle edge cases better

## When to Restore v6 Complexity

Consider restoring if:
- Analysis tools are unavailable
- Need immediate statistical extraction without external tools
- LLM-based extraction proves more reliable than tools
- Token cost becomes less of a concern
- Users prefer single-pass extraction

## Restoration Checklist

If restoring v6 complex extraction:
1. [ ] Copy `EffectMeasure` dataclass to main codebase
2. [ ] Restore `StatisticsData.effect_measure` field
3. [ ] Restore `ExtractedOutcome.effect_measure` field
4. [ ] Copy v6 LLM prompts (with effect measure table)
5. [ ] Restore `study_type_detector.py` module
6. [ ] Update parsing functions to handle effect_measure
7. [ ] Test with 10+ papers of different study types
8. [ ] Update documentation
9. [ ] Train users on new schema

---

**Archive Maintenance**: This document should be updated if:
- New effect measures are discovered
- Study type mappings change
- Statistical standards evolve
- Restoration requirements change
