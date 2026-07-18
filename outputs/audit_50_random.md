# Random 50-Paper Correctness Audit (Seed: 20260718)

Classification source: `classification-pipeline/outputs/classification_v2_final.jsonl`  
Paper source: `classification-pipeline/outputs/work/papers_source.jsonl`  
Taxonomy reference: `classification-pipeline/outputs/taxonomy-draft-v2-prefix.json`

## Summary Metrics

- Total audited: **50**
- Correct: **35** (70.00%)
- Borderline: **11** (22.00%)
- Incorrect: **4** (8.00%)
- Theme-level accuracy proxy (`theme_level_ok`): **48/50** (96.00%)

### Top Recurring Error Patterns

- Control/power method papers crossing domains: 3 cases
- Energy-system studies mapped to adjacent domains: 3 cases
- Social-policy work mapped to IT-focused domains: 2 cases
- Missing metadata created uncertain judgments: 1 cases

### Caveat

This is a 50-paper manual model audit for directional quality checking, not full human ground truth.

## Detailed Paper-Level Audit

| # | Paper ID | Assigned Theme | Assigned Domain | Verdict | Theme OK | Suggested Theme | Suggested Domain | Reason (for borderline/incorrect) |
|---:|---|---|---|---|---|---|---|---|
| 1 | 69deca3f4e2d2a5b77ed8d0d | Manufacturing & Industry 4.0 | Rotor Dynamics & Vibration Analysis | borderline | yes | AI/ML, Supercomputing & Quantum Computing | Control Systems & Linear Dynamical Systems | Robot dynamics/control paper; rotor-vibration fit is partial. |
| 2 | 69deca024e2d2a5b77ecffaf | AI/ML, Supercomputing & Quantum Computing | Algorithms & Computational Complexity | correct | yes | - | - | - |
| 3 | 69deca4a4e2d2a5b77eda7f1 | Social Sciences, Humanities & Management | Computational Linguistics & Language Processing | correct | yes | - | - | - |
| 4 | 69deca2c4e2d2a5b77ed664f | Healthcare & MedTech | Clinical Diagnostics & Biomarkers | correct | yes | - | - | - |
| 5 | 69deca474e2d2a5b77eda002 | Advanced Materials & Devices | Alloys & Structural Metals | correct | yes | - | - | - |
| 6 | 69deca034e2d2a5b77ed0179 | Social Sciences, Humanities & Management | Agricultural Economics & Consumer Behavior | borderline | no | Smart & Sustainable Infrastructure | Hydrology & Water Resources Management | Historical irrigation overview fits water-resources framing better. |
| 7 | 69deca444e2d2a5b77ed9778 | Advanced Materials & Devices | Composite & Laminate Structures | correct | yes | - | - | - |
| 8 | 69dec9ff4e2d2a5b77ecf945 | Manufacturing & Industry 4.0 | Textile Manufacturing & Fabric Properties | correct | yes | - | - | - |
| 9 | 69deca194e2d2a5b77ed3959 | Advanced Materials & Devices | Organometallic & Chalcogenide Synthesis | correct | yes | - | - | - |
| 10 | 69deca5f4e2d2a5b77edd3b9 | Social Sciences, Humanities & Management | Digital Transformation & IT Applications | incorrect | yes | Social Sciences, Humanities & Management | International Business & Finance | Public R&D policy/innovation systems, not primarily IT applications. |
| 11 | 69deca104e2d2a5b77ed23d4 | Manufacturing & Industry 4.0 | Electric Motor Drives & Power Electronics | correct | yes | - | - | - |
| 12 | 69dec9fd4e2d2a5b77ecf2fc | Next-Gen Communication | Antenna Design & RF Systems | correct | yes | - | - | - |
| 13 | 69deca594e2d2a5b77edc974 | Energy, Sustainability & Climate Change | Carbon Utilization & Chemical Conversion | correct | yes | - | - | - |
| 14 | 69deca0e4e2d2a5b77ed1eac | Energy, Sustainability & Climate Change | Electric Vehicle Battery & Charging Systems | correct | yes | - | - | - |
| 15 | 69deca504e2d2a5b77edb52b | Healthcare & MedTech | Cellular & Molecular Biology | borderline | yes | Healthcare & MedTech | Tissue Engineering & Regenerative Medicine | In-vitro keratoconus model also fits tissue-engineering scope. |
| 16 | 69deca0f4e2d2a5b77ed204b | Energy, Sustainability & Climate Change | Grid Integration & Smart Microgrids | correct | yes | - | - | - |
| 17 | 69deca5f4e2d2a5b77edd312 | Smart & Sustainable Infrastructure | Power Systems & Grid Control | correct | yes | - | - | - |
| 18 | 69deca4a4e2d2a5b77eda779 | Next-Gen Communication | Signal Modulation, Detection & Channel Equalization | correct | yes | - | - | - |
| 19 | 69deca5e4e2d2a5b77edcfa9 | Manufacturing & Industry 4.0 | Tribology & Bearing Performance | correct | yes | - | - | - |
| 20 | 69deca274e2d2a5b77ed5b8f | Healthcare & MedTech | Clinical Diagnostics & Biomarkers | borderline | yes | Healthcare & MedTech | Clinical AI & Medical Imaging Analytics | Core contribution is computational holographic reconstruction. |
| 21 | 69deca254e2d2a5b77ed5801 | Energy, Sustainability & Climate Change | Energy Storage Materials | incorrect | yes | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | Thermoelectric performance analysis, not storage-material research. |
| 22 | 69deca164e2d2a5b77ed3213 | Smart & Sustainable Infrastructure | Power Systems & Grid Control | correct | yes | - | - | - |
| 23 | 69deca104e2d2a5b77ed234d | Smart & Sustainable Infrastructure | Power Systems & Grid Control | borderline | yes | Manufacturing & Industry 4.0 | Electric Motor Drives & Power Electronics | Converter-control review leans toward power-electronics domain. |
| 24 | 69dec9fe4e2d2a5b77ecf78c | Social Sciences, Humanities & Management | International Business & Finance | correct | yes | - | - | - |
| 25 | 69deca254e2d2a5b77ed5711 | Manufacturing & Industry 4.0 | Rotor Dynamics & Vibration Analysis | borderline | yes | Manufacturing & Industry 4.0 | Fluid-Particle Flow & Multiphase Systems | Hydrodynamic propeller study only partly matches rotor-vibration. |
| 26 | 69deca654e2d2a5b77ede2cf | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | borderline | yes | Energy, Sustainability & Climate Change | Environmental Assessment & Land Use Management | Satellite irradiance validation is closer to remote-sensing assessment. |
| 27 | 69deca234e2d2a5b77ed5177 | Advanced Materials & Devices | Bio-based Materials & Polymers | correct | yes | - | - | - |
| 28 | 69deca494e2d2a5b77eda666 | Manufacturing & Industry 4.0 | Rotor Dynamics & Vibration Analysis | incorrect | no | AI/ML, Supercomputing & Quantum Computing | Control Systems & Linear Dynamical Systems | Robot trajectory selection is control/optimization, not rotor dynamics. |
| 29 | 69deca404e2d2a5b77ed8e0a | Manufacturing & Industry 4.0 | Fluid-Particle Flow & Multiphase Systems | correct | yes | - | - | - |
| 30 | 69deca294e2d2a5b77ed6067 | Social Sciences, Humanities & Management | Supply Chain & Operations Management | correct | yes | - | - | - |
| 31 | 69deca454e2d2a5b77ed9acd | Energy, Sustainability & Climate Change | Biomass & Biofuel Technologies | correct | yes | - | - | - |
| 32 | 69deca514e2d2a5b77edb907 | Social Sciences, Humanities & Management | Digital Transformation & IT Applications | incorrect | yes | Social Sciences, Humanities & Management | Development Economics & Social Welfare | Organizational behavior framework with limited IT-system substance. |
| 33 | 6a26bf0b2b6042b76389bbae | Manufacturing & Industry 4.0 | Tribology & Bearing Performance | borderline | yes | Manufacturing & Industry 4.0 | Tribology & Bearing Performance | Title suggests tribology; missing abstract limits confidence. |
| 34 | 69deca054e2d2a5b77ed06cf | Energy, Sustainability & Climate Change | Electric Vehicle Battery & Charging Systems | correct | yes | - | - | - |
| 35 | 69deca0e4e2d2a5b77ed1e8f | Energy, Sustainability & Climate Change | Grid Integration & Smart Microgrids | correct | yes | - | - | - |
| 36 | 69deca254e2d2a5b77ed57f1 | Energy, Sustainability & Climate Change | Next-Generation Photovoltaic Materials | borderline | yes | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | CPV-thermoelectric chapter is system thermal analysis, not materials. |
| 37 | 69deca154e2d2a5b77ed2de0 | Energy, Sustainability & Climate Change | Solar Thermal Energy & Heat Transfer Systems | correct | yes | - | - | - |
| 38 | 69deca354e2d2a5b77ed7a19 | AI/ML, Supercomputing & Quantum Computing | Natural Language Processing & Information Retrieval | correct | yes | - | - | - |
| 39 | 69deca064e2d2a5b77ed09a3 | Quantum Technologies & Semiconductor Technology | Plasmonic & Fiber Optic Sensors | borderline | yes | Healthcare & MedTech | Clinical Biosensors & Point-of-Care Devices | Fiber-optic biosensor review can also map to clinical biosensors. |
| 40 | 69deca0b4e2d2a5b77ed16db | Manufacturing & Industry 4.0 | Fluid-Particle Flow & Multiphase Systems | correct | yes | - | - | - |
| 41 | 69deca224e2d2a5b77ed5077 | Social Sciences, Humanities & Management | Supply Chain & Operations Management | correct | yes | - | - | - |
| 42 | 69deca0d4e2d2a5b77ed1ba9 | Energy, Sustainability & Climate Change | Electric Vehicle Battery & Charging Systems | correct | yes | - | - | - |
| 43 | 69deca514e2d2a5b77edb97e | Social Sciences, Humanities & Management | Cultural Studies & Ethnography | borderline | yes | Social Sciences, Humanities & Management | Development Economics & Social Welfare | Well-being psychometrics overlaps social-welfare measurement. |
| 44 | 69deca234e2d2a5b77ed50a9 | Social Sciences, Humanities & Management | Supply Chain & Operations Management | correct | yes | - | - | - |
| 45 | 69deca1e4e2d2a5b77ed44d5 | Advanced Materials & Devices | Ion Beam & Thin Film Engineering | correct | yes | - | - | - |
| 46 | 69deca5e4e2d2a5b77edd07e | Next-Gen Communication | Signal Modulation, Detection & Channel Equalization | correct | yes | - | - | - |
| 47 | 69deca1c4e2d2a5b77ed3fcd | Healthcare & MedTech | Clinical Diagnostics & Biomarkers | correct | yes | - | - | - |
| 48 | 69deca4f4e2d2a5b77edb2f7 | Advanced Materials & Devices | Ferroelectric & Magnetic Ceramics | correct | yes | - | - | - |
| 49 | 69deca3b4e2d2a5b77ed8316 | AI/ML, Supercomputing & Quantum Computing | Machine Learning & Neural Networks | correct | yes | - | - | - |
| 50 | 69dec9f74e2d2a5b77ece862 | Energy, Sustainability & Climate Change | Environmental Assessment & Land Use Management | correct | yes | - | - | - |
