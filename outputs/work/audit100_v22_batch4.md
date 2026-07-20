# v2.2 Audit — Batch 4 (papers 61–80)

**Seed:** `20260719` | **Sample indices:** 61–80 | **Titles from:** `outputs/work/atlas_papers_v22.json` (`papers_source.jsonl` not present)

## Tally

| Verdict | Count | % |
|---|---:|---:|
| Correct | 17 | 85% |
| Borderline | 1 | 5% |
| Incorrect | 2 | 10% |

## Results

| # | id | title | theme | domain | conf | verdict | notes |
|---:|---|---|---|---|---:|---|---|
| 61 | 69deca3e4e2d2a5b77ed8a2d | Characterization of DNA binding and ligand binding properties of the TetR family protein involved in regulation of dsz operon in Gordonia sp. IITR100 | Healthcare & MedTech | Cellular & Molecular Biology | 0.75 | **incorrect** | Bacterial biodesulfurization operon regulation → Manufacturing / Biomanufacturing & Fermentation |
| 62 | 69deca3f4e2d2a5b77ed8b95 | Conversion of a basis-dependent superposition of orbital-angular-momentum states using a q plate | Quantum Technologies & Semiconductor Technology | Structured Light & Polarization Engineering | 0.92 | correct | q-plate OAM conversion |
| 63 | 69deca424e2d2a5b77ed9274 | A multidimensional urban transport equity assessment framework: A case of Mumbai | Social Sciences, Humanities & Management | Development Economics & Social Welfare | 0.92 | correct | Transport equity / welfare policy |
| 64 | 69deca444e2d2a5b77ed964d | Prediction of flow stress for carbon steels using recurrent self-organizing neuro fuzzy networks | Manufacturing & Industry 4.0 | Materials, Joining & Mechanical Behavior | 0.85 | correct | Metal-forming flow stress |
| 65 | 69deca444e2d2a5b77ed975c | Structural-property relationship of nanocrystalline diamond films and its applications | Advanced Materials & Devices | Ion Beam & Thin Film Engineering | 0.75 | correct | MPECVD diamond thin films |
| 66 | 69deca454e2d2a5b77ed987c | Asymmetric 1,2-diaxial synthesis of bi-(hetero)aryl benzofulvene atropisomers via transient directing group-assisted dehydrogenative coupling | Advanced Materials & Devices | Organometallic & Chalcogenide Synthesis | 0.75 | borderline | Pure organic synthesis; materials theme/domain stretch |
| 67 | 69deca454e2d2a5b77ed9991 | The spectrum and clinical correlates of electrodiagnostic abnormalities in acute organophosphorus poisoning. A study of 55 patients | Healthcare & MedTech | Clinical Diagnostics & Biomarkers | 0.92 | correct | Clinical electrodiagnostics |
| 68 | 69deca464e2d2a5b77ed9c9b | ACD codes over Z2R and the MacWilliams identities | AI/ML, Supercomputing & Quantum Computing | Algorithms & Computational Complexity | 0.85 | correct | Coding theory |
| 69 | 69deca474e2d2a5b77ed9fe4 | Effect of samarium modification on structural and dielectric properties of (PbSm)(ZrSnTi)O3 system | Advanced Materials & Devices | Ferroelectric & Magnetic Ceramics | 0.95 | correct | Ferroelectric PZT ceramics |
| 70 | 69deca474e2d2a5b77eda00c | The effect of swift heavy ion irradiation on quasicrystals | Advanced Materials & Devices | Ion Beam & Thin Film Engineering | 0.92 | correct | Ion-beam modification |
| 71 | 69deca484e2d2a5b77eda257 | DENSITY PERTURBATION by ALFVÉN WAVES in MAGNETO-PLASMA | Next-Gen Communication | Plasma-Wave & Electromagnetic Interactions | 0.92 | correct | Alfvén-wave plasma physics |
| 72 | 69deca484e2d2a5b77eda26c | Numerical study of density cavitations by inertial Alfvén waves | Next-Gen Communication | Plasma-Wave & Electromagnetic Interactions | 0.92 | correct | Inertial Alfvén-wave modeling |
| 73 | 69deca4b4e2d2a5b77edaabf | A Framework to Utilize DERs' VAR Resources to Support the Grid in an Integrated T-D System | Smart & Sustainable Infrastructure | Power Systems & Grid Control | 0.92 | correct | DER grid VAR support |
| 74 | 69deca4b4e2d2a5b77edaac3 | Impact assessment and sensitivity analysis of distribution systems with DG | Smart & Sustainable Infrastructure | Power Systems & Grid Control | 0.92 | correct | DG integration analysis |
| 75 | 69deca504e2d2a5b77edb59f | Laboratory Investigation on Performance of Soil–Cement Columns Under Axisymmetric Condition | Smart & Sustainable Infrastructure | Geotechnical Engineering & Soil Mechanics | 0.95 | correct | Ground improvement geotechnics |
| 76 | 69deca514e2d2a5b77edb794 | Characterization of a Collection of Colored Lentil Genetic Resources Using a Novel Computer Vision Approach | AI/ML, Supercomputing & Quantum Computing | Machine Learning & Neural Networks | 0.72 | correct | Novel CV/ML method (agricultural application secondary) |
| 77 | 69deca524e2d2a5b77edba70 | Solution aggregationn of anti-trypanosomal N-(2-napthylmethyl)ated polymines | Healthcare & MedTech | Drug Delivery & Molecular Therapeutics | 0.78 | correct | Anti-trypanosomal drug design |
| 78 | 69deca534e2d2a5b77edbc9d | pH induced size tuning of Gd2Hf2O7:Eu3+ nanoparticles and its effect on their UV and X-ray excited luminescence | Advanced Materials & Devices | Rare-Earth Doped Luminescent Materials | 0.95 | correct | Eu³⁺ phosphor nanoparticles |
| 79 | 69deca534e2d2a5b77edbdd2 | Characterization of detergent compatible protease of a halophilic Bacillus sp. EMB9: Differential role of metal ions in stability and activity | Healthcare & MedTech | Biopharmaceutical Manufacturing & Quality | 0.60 | **incorrect** | Industrial detergent protease → Manufacturing / Biomanufacturing & Fermentation |
| 80 | 69deca554e2d2a5b77edc203 | Lattice theory of second- and third-order elastic constants of aluminum, copper, and nickel | Advanced Materials & Devices | Alloys & Structural Metals | 0.75 | correct | FCC metal elastic constants |

## Error patterns (batch 4)

1. **Healthcare overreach for non-clinical microbiology/enzymes** (papers 61, 79): bacterial operon biochemistry and industrial protease work routed to Healthcare domains instead of Manufacturing bioprocess.
2. **Organic synthesis edge case** (paper 66): atropisomer synthesis classified under materials organometallic domain with acceptable but loose fit.
