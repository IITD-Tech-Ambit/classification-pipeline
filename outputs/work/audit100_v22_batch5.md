# v2.2 Audit 100 — Batch 5 (papers 81–100)

- **Seed:** `20260719` | **Batch index:** 5 | **Papers:** 20
- **Titles source:** `outputs/work/papers_source.jsonl` not found; titles from `outputs/work/atlas_papers_v22.json` where available, else inferred from classifier reason text.
- **Judge:** manual/model audit against `outputs/taxonomy-draft-v22.json` (not human gold standard).

## Tally

| Verdict | Count | % |
|---------|------:|--:|
| correct | 15 | 75.0% |
| borderline | 1 | 5.0% |
| incorrect | 4 | 20.0% |

## Per-paper adjudication

| # | id | title | theme | domain | conf | verdict | rationale |
|--:|---|---|---|---|---:|---|---|
| 81 | 69deca554e2d2a5b77edc2c1 | (title unavailable; DR-LPFG SPR sensor) | Quantum Technologies & Semiconductor Technology | Plasmonic & Fiber Optic Sensors | 0.92 | correct | Fiber SPR biomolecule sensor fits plasmonic/fiber-optic sensing domain. |
| 82 | 69deca554e2d2a5b77edc2ee | (title unavailable; Si-SiO2 Bragg-grating biochemical sensor) | Quantum Technologies & Semiconductor Technology | Fiber Photonic Devices & Engineering | 0.85 | borderline | Theme correct; biochemical Bragg-grating sensor could also map to Plasmonic & Fiber Optic Sensors. |
| 83 | 69deca554e2d2a5b77edc33b | Solar desorption of absorbent solutions | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | 0.92 | correct | Solar thermal desorption/humidity-control system. |
| 84 | 69deca5a4e2d2a5b77edc9af | CRITICAL GROWTH FRACTIONAL KIRCHHOFF ELLIPTIC PROBLEMS | AI/ML, Supercomputing & Quantum Computing | Algorithms & Computational Complexity | 0.75 | incorrect | Pure fractional elliptic PDE analysis; out of taxonomy — not algorithms/ML. → unclassifiable |
| 85 | 69deca5d4e2d2a5b77edce95 | (title unavailable; sound-symbolic words in comics) | Social Sciences, Humanities & Management | Cultural Studies & Ethnography | 0.75 | correct | Semiotic/cultural analysis of graphic narratives. |
| 86 | 69deca5e4e2d2a5b77edd06f | Analysis of GPRS radio channel access delay | Next-Gen Communication | Wireless Network Access & Resource Allocation | 0.92 | correct | GPRS RACH delay / MAC performance modeling. |
| 87 | 69deca5e4e2d2a5b77edd13e | NUMERICAL INVESTIGATION OF AIR-BLAST PERFORMANCE OF CROSS-FILLED HONEYCOMB SANDWICH PANEL | Advanced Materials & Devices | Composite & Laminate Structures | 0.75 | correct | Honeycomb sandwich blast/impact structural analysis. |
| 88 | 69deca5f4e2d2a5b77edd229 | Breaking the size constraint for nano cages using annular patchy particles | Advanced Materials & Devices | Polymer Nanocomposites & Blends | 0.45 | incorrect | Colloidal self-assembly / soft matter, not polymer nanocomposites. → Ionic Liquids & Soft Matter |
| 89 | 69deca5f4e2d2a5b77edd3f3 | Automatic classification and prediction models for early Parkinson's disease diagnosis from SPECT imaging | Healthcare & MedTech | Clinical AI & Medical Imaging Analytics | 0.92 | correct | Clinical SPECT neuroimaging ML for Parkinson's diagnosis. |
| 90 | 69deca624e2d2a5b77eddaae | Optimum power from a solar thermal power plant using solar concentrators | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | 0.95 | correct | Solar thermal power-plant optimization. |
| 91 | 69deca644e2d2a5b77edde98 | Education as a determinant of response to cyclone warnings: Evidence from coastal zones in India | Social Sciences, Humanities & Management | Development Economics & Social Welfare | 0.85 | correct | Education/disaster-adaptive-capacity empirical social-welfare study. |
| 92 | 69deca654e2d2a5b77ede13e | Synthesis and characterization of methylcellulose/PVA based porous composite | Advanced Materials & Devices | Bio-based Materials & Polymers | 0.92 | correct | Bio-based polymer composite synthesis/characterization. |
| 93 | 69deca654e2d2a5b77ede1a9 | Effect of isomerization on thermal behaviour of bisitaconimides | Advanced Materials & Devices | Organometallic & Chalcogenide Synthesis | 0.72 | incorrect | Imide resin thermal behavior is polymer materials, not organometallic/chalcogenide chemistry. → Polymer Nanocomposites & Blends |
| 94 | 69deca664e2d2a5b77ede46c | A dual band gysel power divider with wide band ratio | Next-Gen Communication | Antenna Design & RF Systems | 0.92 | correct | Microwave RF power-divider component design. |
| 95 | 6a13eb892b6042b763468678 | RIS-Assisted Finite Blocklength Ambient Backscatter Communication with Non-Linear Energy Harvesting | Next-Gen Communication | Cooperative & Relay Networks | 0.92 | correct | RIS-assisted backscatter treated as cooperative relay architecture. |
| 96 | 6a25fe8d2b6042b763867596 | A Low Frequency Subpolar Gyre Signal Identified in the Atlantic Inflow to the North Sea | Energy, Sustainability & Climate Change | Monsoon Dynamics & Regional Climate Modeling | 0.75 | incorrect | North Atlantic ocean circulation, not Indian monsoon regional climate. → unclassifiable or Environmental Assessment |
| 97 | 6a26be272b6042b76389b411 | Epigenetic Reactions and Chromatin-lamina Interactions Synergistically Regulate the Morphology of Lamina-associated Domains | Healthcare & MedTech | Cellular & Molecular Biology | 0.85 | correct | Chromatin/epigenetic molecular cell biology. |
| 98 | 6a26be272b6042b76389b41c | FINITE ELEMENT ANALYSIS OF FORCE TRANSFER FROM WRIST TO ELBOW FOR A CRICKET PLAYER | Healthcare & MedTech | Biomechanics & Musculoskeletal Systems | 0.85 | correct | Musculoskeletal force-transfer biomechanics. |
| 99 | 6a26bf072b6042b76389bb88 | (title unavailable; shear-flow stability theory) | AI/ML, Supercomputing & Quantum Computing | Computational Fluid Dynamics & Flow Analysis | 0.95 | correct | Flow stability / transition-to-turbulence analysis fits CFD domain. |
| 100 | 6a5418365ac95135d3b18824 | (title unavailable; geosynthetic hill-road pavement review) | Smart & Sustainable Infrastructure | Geotechnical Engineering & Soil Mechanics | 0.85 | correct | Geosynthetic soil-mechanics / pavement infrastructure review. |

## Error patterns (batch 5)

1. **Pure mathematics misrouted to AI/ML / Algorithms** — fractional elliptic PDE theory (#84).
2. **Wrong materials subdomain** — soft-matter colloidal assembly (#88) and imide polymer resins (#93) assigned to mismatched domains.
3. **Regional climate domain overreach** — North Atlantic oceanography placed in Monsoon Dynamics (#96).
