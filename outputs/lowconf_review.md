# Low-Confidence Classified Papers — Human Review

_Review set = classified papers (`unclassifiable=false`) with `confidence < 0.5`, from `classification_v2_final.jsonl`. Sorted worst-first. Titles/abstracts joined read-only from Mongo._

## Overview

- **Low-confidence papers:** 1,702
- **Share of corpus:** 2.42% (of 70,298)
- **Title join success:** 1,702/1,702 (100.00%)

## Confidence histogram (within low-conf set)

| bucket | count | share |
|---|---:|---:|
| <0.2 | 54 | 3.2% |
| 0.2-0.3 | 44 | 2.6% |
| 0.3-0.4 | 394 | 23.1% |
| 0.4-0.5 | 1,210 | 71.1% |

## Breakdown by thematic area

| thematic area | count | share |
|---|---:|---:|
| Advanced Materials & Devices | 450 | 26.4% |
| Energy, Sustainability & Climate Change | 304 | 17.9% |
| AI/ML, Supercomputing & Quantum Computing | 266 | 15.6% |
| Social Sciences, Humanities & Management | 221 | 13.0% |
| Manufacturing & Industry 4.0 | 187 | 11.0% |
| Quantum Technologies & Semiconductor Technology | 131 | 7.7% |
| Smart & Sustainable Infrastructure | 70 | 4.1% |
| Healthcare & MedTech | 56 | 3.3% |
| Next-Gen Communication | 17 | 1.0% |

## Breakdown by domain (top 20)

| domain | count | share |
|---|---:|---:|
| Algorithms & Computational Complexity | 195 | 11.5% |
| Rare-Earth Doped Luminescent Materials | 128 | 7.5% |
| Grid Integration & Smart Microgrids | 114 | 6.7% |
| Rotor Dynamics & Vibration Analysis | 93 | 5.5% |
| Organometallic & Chalcogenide Synthesis | 87 | 5.1% |
| Bio-based Materials & Polymers | 70 | 4.1% |
| Supply Chain & Operations Management | 64 | 3.8% |
| Composite & Laminate Structures | 63 | 3.7% |
| Agricultural Economics & Consumer Behavior | 51 | 3.0% |
| Biomass & Biofuel Technologies | 45 | 2.6% |
| Solar Thermal Energy & Heat Transfer Systems | 43 | 2.5% |
| Digital Culture & Consumer Experience | 40 | 2.4% |
| Ferroelectric & Magnetic Ceramics | 39 | 2.3% |
| Biomanufacturing & Fermentation Processes | 39 | 2.3% |
| Carbon Utilization & Chemical Conversion | 39 | 2.3% |
| Computational Fluid Dynamics & Flow Analysis | 38 | 2.2% |
| Digital Transformation & IT Applications | 38 | 2.2% |
| Semiconductor Photovoltaic & Photodetection Devices | 37 | 2.2% |
| Clinical Diagnostics & Biomarkers | 31 | 1.8% |
| Ultra-Low Voltage Analog Circuits | 23 | 1.4% |

## Out-of-scope vs misdomained (rough heuristic)

> **Heuristic estimate, not ground truth.** Counts low-conf papers whose **title** contains basic-physics / astro / nuclear / atomic / quantum-field / cosmology / particle keywords. Titles matching these are *likely* out-of-scope basic science; the rest are *likely* in-scope-but-misdomained. Abstract text is not scanned, so this under-counts. Use only to decide whether an explicit out-of-scope bucket is worth adding.

- **Likely out-of-scope basic science (title keyword hit):** 141 (8.3%)
- **Likely in-scope but misdomained (no hit):** 1,561 (91.7%)

## 40 worst papers (lowest confidence)

| # | conf | id | assigned theme -> domain | title |
|---:|---:|---|---|---|
| 1 | 0.150 | `69dec9f64e2d2a5b77ece5c2` | Advanced Materials & Devices -> Ion Beam & Thin Film Engineering | Frequency based oscilloscope triggering scheme |
| 2 | 0.150 | `69dec9fb4e2d2a5b77ecef9a` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials | Aspects of single particle excitations and collectivity in 69Ga |
| 3 | 0.150 | `69dec9fb4e2d2a5b77ecefdd` | Advanced Materials & Devices -> Ion Beam & Thin Film Engineering *[oos?]* | Study of quark and gluon jet substructure in Z+jet and dijet events from pp collisions |
| 4 | 0.150 | `69dec9fc4e2d2a5b77ecf0a8` | Energy, Sustainability & Climate Change -> Grid Integration & Smart Microgrids | Evidence of anomalous resistivity for hot electron propagation through a dense fusion core in fast ignition experiments |
| 5 | 0.150 | `69dec9fc4e2d2a5b77ecf20d` | Advanced Materials & Devices -> Composite & Laminate Structures *[oos?]* | Open heavy flavor mesons in hot asymmetric strange hadronic matter: A QCD sum rule approach |
| 6 | 0.150 | `69dec9fc4e2d2a5b77ecf210` | Advanced Materials & Devices -> Ferroelectric & Magnetic Ceramics *[oos?]* | φ meson in nuclear matter and atomic nuclei |
| 7 | 0.150 | `69dec9fc4e2d2a5b77ecf222` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis | Spectral functions of strange vector mesons in asymmetric hyperonic matter |
| 8 | 0.150 | `69dec9fc4e2d2a5b77ecf224` | Advanced Materials & Devices -> Composite & Laminate Structures *[oos?]* | Light vector mesons (ω, ρ, and φ) in strong magnetic fields: A QCD sum rule approach |
| 9 | 0.150 | `69dec9fc4e2d2a5b77ecf226` | Advanced Materials & Devices -> Alloys & Structural Metals | Charmonium decay widths in magnetized matter |
| 10 | 0.150 | `69dec9fc4e2d2a5b77ecf236` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | D-mesons and charmonium states in hot isospin asymmetric strange hadronic matter |
| 11 | 0.150 | `69dec9fc4e2d2a5b77ecf237` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | Role of distribution function on characteristic properties of supernova matter |
| 12 | 0.150 | `69dec9fc4e2d2a5b77ecf23a` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling *[oos?]* | J/ψ and ηc masses in isospin asymmetric hot nuclear matter: A QCD sum rule approach |
| 13 | 0.150 | `69dec9fc4e2d2a5b77ecf245` | Advanced Materials & Devices -> Composite & Laminate Structures *[oos?]* | Isospin dependent kaon and antikaon optical potentials in dense hadronic matter |
| 14 | 0.150 | `69dec9fc4e2d2a5b77ecf24a` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | Dilepton emission rates from hot hadronic matter |
| 15 | 0.150 | `69dec9fc4e2d2a5b77ecf24e` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis | In-medium vector meson masses in a chiral SU(3) model |
| 16 | 0.150 | `69dec9fc4e2d2a5b77ecf254` | Energy, Sustainability & Climate Change -> Next-Generation Photovoltaic Materials *[oos?]* | Quantum vacuum in hot nuclear matter: A non-perturbative treatment |
| 17 | 0.150 | `69dec9fc4e2d2a5b77ecf259` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | Hot nuclear matter in the quark meson coupling model |
| 18 | 0.150 | `69dec9fc4e2d2a5b77ecf25c` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | Gluon condensates, quark matter equation of state and quark stars |
| 19 | 0.150 | `69dec9fc4e2d2a5b77ecf25d` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | Gluon condensates, chiral symmetry breaking and pion wave-function |
| 20 | 0.150 | `69deca024e2d2a5b77ed0052` | Advanced Materials & Devices -> Ferroelectric & Magnetic Ceramics | No evidence of reduced collectivity in Coulomb-excited Sn isotopes |
| 21 | 0.150 | `69deca024e2d2a5b77ed0069` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials *[oos?]* | Lifetime measurements in mass regions A=100 and A=130 as a test for chirality in nuclear systems |
| 22 | 0.150 | `69deca024e2d2a5b77ed008f` | Quantum Technologies & Semiconductor Technology -> Semiconductor Photovoltaic & Photodetection Devices | In a search for a chiral symmetry in 102Rh |
| 23 | 0.150 | `69deca024e2d2a5b77ed0099` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials | β-delayed γ-ray spectroscopy of 203,204Au and 200-202Pt |
| 24 | 0.150 | `69deca024e2d2a5b77ed009b` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials *[oos?]* | Study of Alpha Decay Chains of Superheavy Nuclei and Magic Number Beyond Z = 82 and N = 126 |
| 25 | 0.150 | `69deca024e2d2a5b77ed00c8` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials | Excited states in Pd99 |
| 26 | 0.150 | `69deca024e2d2a5b77ed00f8` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials | Pre-compound neutron evaporation in low energy heavy ion fusion reactions |
| 27 | 0.150 | `69deca024e2d2a5b77ed0106` | Advanced Materials & Devices -> Rare-Earth Doped Luminescent Materials | Polarization measurement and Y-ray spectroscopy of Cs122 |
| 28 | 0.150 | `69deca1f4e2d2a5b77ed47ea` | Advanced Materials & Devices -> Composite & Laminate Structures | B anomalies: From warped models to colliders |
| 29 | 0.150 | `69deca1f4e2d2a5b77ed47f1` | Quantum Technologies & Semiconductor Technology -> Quantum Photonics & Entanglement *[oos?]* | Looking for lepton flavor violation in supersymmetry at the LHC |
| 30 | 0.150 | `69deca2b4e2d2a5b77ed63a9` | Manufacturing & Industry 4.0 -> Electric Motor Drives & Power Electronics | Current and future trends in embedded VLIW microprocessors applied to multimedia and signal processing |
| 31 | 0.150 | `69deca3a4e2d2a5b77ed8286` | Social Sciences, Humanities & Management -> Computational Linguistics & Language Processing | Line bundles on G-Bott-Samelson-Demazure-Hansen varieties |
| 32 | 0.150 | `69deca424e2d2a5b77ed9259` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | GW190814: On the properties of the secondary component of the binary |
| 33 | 0.150 | `69deca424e2d2a5b77ed925a` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling *[oos?]* | Towards mitigation of apparent tension between nuclear physics and astrophysical observations by improved modeling of neutron star matter |
| 34 | 0.150 | `69deca424e2d2a5b77ed925c` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | Maximum mass of hybrid star formed via shock-induced phase transition in cold neutron stars |
| 35 | 0.150 | `69deca424e2d2a5b77ed925f` | Advanced Materials & Devices -> Organometallic & Chalcogenide Synthesis *[oos?]* | Constraining the relativistic mean-field model equations of state with gravitational wave observations |
| 36 | 0.150 | `69deca424e2d2a5b77ed926c` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | Magnetised neutron star crusts and torsional shear modes of magnetars |
| 37 | 0.150 | `69deca424e2d2a5b77ed9270` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | Inner crusts of neutron stars in strongly quantizing magnetic fields |
| 38 | 0.150 | `69deca424e2d2a5b77ed9271` | Energy, Sustainability & Climate Change -> Monsoon Dynamics & Regional Climate Modeling | Neutron star crust in strong magnetic fields |
| 39 | 0.150 | `69deca464e2d2a5b77ed9ca7` | Social Sciences, Humanities & Management -> Computational Linguistics & Language Processing | Total Character of a Group G with (G, Z(G)) as a Generalized Camina Pair |
| 40 | 0.150 | `69deca494e2d2a5b77eda623` | Manufacturing & Industry 4.0 -> Rotor Dynamics & Vibration Analysis | Touchless human-mobile robot interaction using a projectable interactive surface |

_`[oos?]` marks a title that hit the out-of-scope basic-science keyword heuristic._
