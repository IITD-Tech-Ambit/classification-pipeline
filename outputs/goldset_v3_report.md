# Gold-Set Accuracy Re-Test — Classification v3 (head-to-head vs v2)

_Method identical to the original gold check: an INDEPENDENT `claude-sonnet-4-5` label (full v3 taxonomy, prompt-cached, blind to the assigned label) vs the production v3 label, on a FRESH stratified 250-paper sample (different seed). This is an LLM-vs-LLM agreement PROXY, not human ground truth._

## Headline: v3 vs v2 baseline

| metric | v2 baseline | v3 | delta |
|---|---|---|---|
| Theme agreement | 86.2% | 79.7% (196/246) | **-6.5** |
| Domain agreement | 70.5% | 58.8% (144/245) | **-11.7** |

## By confidence band

| band | theme v3 (Δ) | domain v3 (Δ) |
|---|---|---|
| <0.5 | 63.9% (-26.2) | 25.3% (-42.1) |
| 0.5-0.8 | 82.4% (+6.4) | 67.9% (+9.2) |
| >=0.8 | 93.6% (+1.8) | 84.6% (-1.7) |

## By source model

| source_model | theme | domain |
|---|---|---|
| haiku | 95.0% (57/60) | 88.3% (53/60) |
| haiku_repass_v3 | 74.3% (136/183) | 49.5% (90/182) |
| sonnet | 100.0% (3/3) | 33.3% (1/3) |

- Theme-right / domain-wrong: **52** of 196 theme-matches (26.5%).
- Sample papers whose label changed from v2: **69** / 250.
- Sonnet refusals (excluded): 0; Sonnet-unclassifiable (excluded): 2.
- Stage-D cost: $1.4471.

## Top theme disagreements (v3 current -> sonnet)

| current theme | sonnet theme | count |
|---|---|---:|
| Manufacturing & Industry 4.0 | Energy, Sustainability & Climate Change | 7 |
| Advanced Materials & Devices | Energy, Sustainability & Climate Change | 6 |
| Healthcare & MedTech | Advanced Materials & Devices | 3 |
| Manufacturing & Industry 4.0 | Advanced Materials & Devices | 3 |
| Energy, Sustainability & Climate Change | Smart & Sustainable Infrastructure | 3 |
| Smart & Sustainable Infrastructure | Energy, Sustainability & Climate Change | 3 |
| Advanced Materials & Devices | Quantum Technologies & Semiconductor Technology | 2 |
| Manufacturing & Industry 4.0 | AI/ML, Supercomputing & Quantum Computing | 2 |
| Healthcare & MedTech | Quantum Technologies & Semiconductor Technology | 2 |
| Smart & Sustainable Infrastructure | Next-Gen Communication | 2 |
| AI/ML, Supercomputing & Quantum Computing | Quantum Technologies & Semiconductor Technology | 2 |
| Quantum Technologies & Semiconductor Technology | Next-Gen Communication | 2 |

## Domains with most disagreement (v3)

| current domain | disagreements |
|---|---:|
| Thermal Systems, Engines & Energy Harvesting | 9 |
| Ion Beam & Thin Film Engineering | 7 |
| Electric Motor Drives & Power Electronics | 5 |
| Biomanufacturing & Fermentation Processes | 5 |
| Semiconductor Photovoltaic & Photodetection Devices | 4 |
| Building Energy & Thermal Performance | 4 |
| Clinical Biosensors & Point-of-Care Devices | 4 |
| Structured Light & Polarization Engineering | 4 |
| Next-Generation Photovoltaic Materials | 3 |
| Clinical Diagnostics & Biomarkers | 3 |
| Drug Delivery & Molecular Therapeutics | 3 |
| Clinical AI & Medical Imaging Analytics | 3 |
