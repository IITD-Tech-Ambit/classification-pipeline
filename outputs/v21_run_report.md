# v2.1 Targeted Sonnet Run Report

- Mission constraints: file-based only, no production DB writes, rollback baseline frozen.
- Baseline snapshot dir: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\safe_baseline`.
- Baseline proxy metrics: theme **86.2%**, domain **70.5%**.

## Stage A — Freeze + Queue
- Taxonomy used: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\taxonomy-draft-v2-prefix.json`.
- Queue pre-cap: **39949** (low<0.8=27526, high-conf confusion=12423).
- Queue after budget cap: **6979**.
- Pilot rows for cost estimation: **120**.
- Estimated correction rows affordable under budget: **6979**.

## Stage B — Parallel Sonnet correction
- Correction model: **claude-sonnet-4-5**.
- Concurrency ramp: start 35, then 60, then up to 80 when 429/5xx low.
- Phase stats:
  - pilot_cost_estimation: workers=12, rows=120, rate429=0, 5xx=0, phase_cost=$1.1691
  - phase_start: workers=35, rows=1500, rate429=0, 5xx=0, phase_cost=$12.3523
  - phase_ramp: workers=60, rows=5359, rate429=0, 5xx=0, phase_cost=$31.8803
- Targeted output rows written: **6979** (unique ids=6979).

## Stage C — Conservative acceptance gate
- Accepted total: **1837**.
- Accepted domain changes: **1837**.
- Accepted theme changes: **114**.
- Accepted unclassifiable conversions: **10**.
- Weak/unjustified changes were rejected and kept at baseline label.

## Stage D — Random subset validation
- Judge model: **claude-opus-4-5**.
- Net wins: v2_1=82 vs v2=8 (ties=130).
- Theme non-regression: **PASS**.
- Domain improvement signal: **PASS**.
- Top improvement patterns:
  - 3x Advanced Materials & Devices / Ion Beam & Thin Film Engineering -> Advanced Materials & Devices / Polymer Nanocomposites & Blends
  - 3x Manufacturing & Industry 4.0 / Rotor Dynamics & Vibration Analysis -> Manufacturing & Industry 4.0 / Materials, Joining & Mechanical Behavior
  - 3x Advanced Materials & Devices / Ion Beam & Thin Film Engineering -> Advanced Materials & Devices / Organometallic & Chalcogenide Synthesis
  - 3x Social Sciences, Humanities & Management / Digital Transformation & IT Applications -> Social Sciences, Humanities & Management / Cultural Studies & Ethnography
  - 3x Energy, Sustainability & Climate Change / Grid Integration & Smart Microgrids -> Energy, Sustainability & Climate Change / Solar Thermal Energy & Heat Transfer Systems
  - 2x Next-Gen Communication / Free Space Optical Communication -> Next-Gen Communication / Signal Modulation, Detection & Channel Equalization
- Top regression patterns:
  - 1x Advanced Materials & Devices / Composite & Laminate Structures -> Advanced Materials & Devices / Bio-based Materials & Polymers
  - 1x Advanced Materials & Devices / Bio-based Materials & Polymers -> Advanced Materials & Devices / Ionic Liquids & Soft Matter
  - 1x Energy, Sustainability & Climate Change / Electric Vehicle Battery & Charging Systems -> Energy, Sustainability & Climate Change / Grid Integration & Smart Microgrids
  - 1x AI/ML, Supercomputing & Quantum Computing / Natural Language Processing & Information Retrieval -> AI/ML, Supercomputing & Quantum Computing / Machine Learning & Neural Networks
  - 1x Energy, Sustainability & Climate Change / Environmental Assessment & Land Use Management -> Energy, Sustainability & Climate Change / Carbon Utilization & Chemical Conversion
  - 1x Healthcare & MedTech / Tissue Engineering & Regenerative Medicine -> Healthcare & MedTech / Biomechanics & Musculoskeletal Systems

## Stage E — Decision gate
- Decision: **recommended_v2_1**.
- Recommendation tonight: **C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\classification_v2_1_candidate.jsonl**.
- Reason: net_margin=74 (required>=8), theme_non_regression=True, domain_signal=True

## Cost
- Correction spend: **$45.40**
- Validation spend: **$6.15**
- Model verify/probe spend: **$0.00**
- Total spend this run: **$51.55** (cap $80.00)

## Artifacts
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\classification_v2_1_candidate.jsonl`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\sonnet_targeted_v21.jsonl`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\sonnet_v21_cost.json`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\v21_validation_random_subset.md`
- `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\audit_50_random_v21.md`