# Regulatory Language Limits Satellite-Based Enforcement in Marine Protected Areas

Analysis code, data extracts, and manuscript sources for:

Favoretto F, López-Sagástegui C, Guidetti P, Simone A, Sletten J, Zetterlind V, Aburto-Oropeza O, Fraser K, Sala E. *Regulatory Language Limits Satellite-Based Enforcement in Marine Protected Areas.* Under review at **npj Ocean Sustainability** (revised version submitted September 2026). Zenodo archive of the submitted version: https://doi.org/10.5281/zenodo.20268179.

## What the analysis does

Sentence-level, rule-based text analysis of two layers of law across 15 countries:

1. **Regulation Preparedness Index (RPI, 0–100)** for 9,740 regulatory zones (MPAs and their internal management zones) from the ProtectedSeas Navigator database: does the recorded regulatory text define offences in terms that remote evidence (AIS, VMS, satellite imagery) can prove, and does it contain vessel-tracking and reporting obligations?
2. **Legislation Readiness Index (LRI, 0–100)** for 119 national legal instruments retrieved from FAOLEX: does the primary legislation contain evidentiary, penalty, enforcement, technology, and liability provisions?

Both indices are deterministic screening tools (no machine learning, no random seeds, no external services).

## Running the pipeline

```bash
# 1. Score all regulatory zones and all legislation documents (~2 min)
python3 analysis/scripts/nlp_contextual_scoring.py

# 2. Figures 1, 2, S1, S2 (needs the Navigator shapefile in data/Navigator_AllSites_032825_shp/)
Rscript analysis/R/01_policy_unpreparedness_analysis.R

# 3. Figures 3, S3, S4
Rscript analysis/R/02_legislation_readiness_figures.R

# 4. Supplementary tables, key statistics, and the manuscript documents
python3 for_submission_npj/manuscript/source/make_si_tables.py
python3 for_submission_npj/manuscript/source/verify_examples.py
bash    for_submission_npj/manuscript/source/build_all.sh
```

Required: Python 3.8+ with `pdfplumber` and `python-docx`; R with tidyverse, sf, scales, patchwork, jsonlite, rnaturalearth, ggrepel; pandoc.


## Revision history

- **v1 (June 2026):** submitted to npj Ocean Sustainability.
- **v2 (September 2026):** revision addressing two reviews. Classifier pattern for "may not" added; terminology "zonation" → "regulatory zone" and "prosecution" → "judicial proceedings"; BBNJ score removed; robustness and sensitivity analyses, corpus tables, and verbatim examples added; three reference misattributions corrected. Headline statistics unchanged at reporting precision (mean RPI 33.02 → 33.11).

## Licence

Code: MIT. Outputs and figures: CC-BY-4.0. Navigator data © ProtectedSeas/Anthropocene Institute; FAOLEX documents © FAO (redistributed for reproducibility under their terms).
