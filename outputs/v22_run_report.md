# v2.2 Overnight Run Report (for owner)

## Bottom line

- **Accepted?** True
- **Recommended file:** `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\classification_v2_2_candidate.jsonl`
- **Papers updated (accepted domain/theme/unclass changes):** 1608
- **Total spend:** $57.39 / $70.00 hard cap

## What we did

- Closed taxonomy gaps (thermoelectric, optical metrology, implant bioelectronics sharpening, computer architecture) plus explicit out_of_scope routing for accelerator RF and fuel-additive screening.
- Re-labeled ONLY a high-yield affected queue (not all 70k).
- Conservative acceptance gate; rejected weak changes.

## Concurrency / speed

- Configured workers: start=50, ramp=65, max=80
- Peak observed parallel in-flight API calls: **80**
- Phase plan / workers used: [20, 50, 65, 80]
- Budget soft-stop for correction: $55.00; triggered=False (queue finished at **$52.42**, under the soft stop)
- Hard cap $70 respected: total **$57.39** (correction $52.42 + validation $4.97)

## Queue

- Queue size: **7000** (pre-cap 10218)
- Priority counts: {'pri_1': 481, 'pri_2': 1247, 'pri_3': 6281, 'pri_4': 2209}
- Keyword hits: {'kw_accelerator_rf': 77, 'kw_architecture': 79, 'kw_fuel_additive': 18, 'kw_implant_power': 208, 'kw_mechanism_design': 20, 'kw_optical_metrology': 269, 'kw_pat_biopharma': 388, 'kw_thermoelectric': 683}

## Correction

- Model: **claude-sonnet-4-5**
- Targeted rows written: **7000**
- Correction spend: **$52.42**

## Acceptance

- Accepted total: **1608**
- Domain changes: **1605**
- Theme changes: **437**
- Unclass conversions: **302**
- Identity rename (biosensor domain): **548**

## Validation (honest)

- Judge: **claude-opus-4-5**
- Overall wins: v2_2=78 vs v2_1=19 (ties=83)
- Net margin: **59**
- Theme non-regression: **PASS**
- Domain signal: **PASS**
- Changed-subset net margin: **59**
- Decision reason: net_margin=59 (required>=5), changed_margin=59, theme_non_regression=True, domain_signal=True

## What improved / what didn't

### Improved patterns
- 13x AI/ML, Supercomputing & Quantum Computing / Algorithms & Computational Complexity -> AI/ML, Supercomputing & Quantum Computing / Computer Architecture & Systems
- 9x Energy, Sustainability & Climate Change / Energy Storage Materials -> Energy, Sustainability & Climate Change / Thermoelectric & Energy-Harvesting Materials
- 7x Quantum Technologies & Semiconductor Technology / Fiber Photonic Devices & Engineering -> Quantum Technologies & Semiconductor Technology / Optical Metrology & Interferometric Instrumentation
- 6x AI/ML, Supercomputing & Quantum Computing / Algorithms & Computational Complexity -> unclassifiable / unclassifiable
- 4x Social Sciences, Humanities & Management / Digital Culture & Consumer Experience -> Social Sciences, Humanities & Management / Digital Transformation & IT Applications
- 3x Quantum Technologies & Semiconductor Technology / Plasmonic & Fiber Optic Sensors -> Quantum Technologies & Semiconductor Technology / Wide Bandgap Semiconductors & Devices
### Regressed patterns
- 5x AI/ML, Supercomputing & Quantum Computing / Algorithms & Computational Complexity -> AI/ML, Supercomputing & Quantum Computing / Computational Fluid Dynamics & Flow Analysis
- 2x Healthcare & MedTech / Clinical Biosensors & Implant Bioelectronics -> Healthcare & MedTech / Biomechanics & Musculoskeletal Systems
- 1x Manufacturing & Industry 4.0 / Materials, Joining & Mechanical Behavior -> Manufacturing & Industry 4.0 / Precision Manufacturing & Microfabrication
- 1x Manufacturing & Industry 4.0 / Materials, Joining & Mechanical Behavior -> Manufacturing & Industry 4.0 / Textile Manufacturing & Fabric Properties
- 1x AI/ML, Supercomputing & Quantum Computing / Algorithms & Computational Complexity -> AI/ML, Supercomputing & Quantum Computing / Machine Learning & Neural Networks
- 1x Quantum Technologies & Semiconductor Technology / Fiber Photonic Devices & Engineering -> Quantum Technologies & Semiconductor Technology / Quantum Photonics & Entanglement

## Cost breakdown

- Correction: $52.42
- Validation: $4.97
- Verify/probe: $0.00
- **Total: $57.39** (hard cap $70.00; correction soft-stop $55.00)
- Budget controls: soft-stop not hit because correction ended at $52.42 (<$55); hard cap held (total $57.39 <$70). **Budget stop mechanism worked as designed.**

## What to tell the team

Overnight we closed four taxonomy gaps (thermoelectrics, optical metrology, implant bioelectronics, computer architecture) and re-scored a high-yield subset (~7000 papers) with Sonnet under a $70 hard spend cap (actual $57.39; peak parallelism 80). Blind validation favored v2.2 (net +59 on non-ties; changed-subset net +59); we accepted 1608 conservative updates. Recommend shipping v2.2.

## Local ingest (accepted)

- Backup: `outputs/db_backup_pre_v22_ingest/`
- Ingest report: `outputs/v22_ingest_report.md` — SUCCESS (counts match; 9 themes / 80 domains; classified 67,802 / unclass 2,496)
- Active atlas version: `9029054b27d2`

## Artifacts

- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\classification_v2_2_candidate.jsonl`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\taxonomy-draft-v22.json`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\v22_target_queue.jsonl`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\sonnet_targeted_v22.jsonl`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\sonnet_v22_cost.json`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\v22_validation_random_subset.md`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\audit_50_random_v22.md`
- Frozen baseline: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\safe_baseline\classification_v21_frozen.jsonl`