# Level-2 Domain Classification — Diagnosis

_Analysis only. No API calls (~$0), read-only on Mongo (reused the already-exported `papers_source.jsonl`), no DB writes, no git commits._

**Inputs used:** `outputs/classification_v2_final.jsonl` (70,298 rows), `outputs/work/goldset_sample.jsonl` + `goldset_sonnet_labels.jsonl` (250-paper gold), `outputs/work/goldset_metrics.json`, `outputs/taxonomy-draft-v2.json/.md`, `outputs/work/papers_source.jsonl` (titles/abstracts).

**Supporting artifacts produced:**
- `outputs/work/domain_diagnosis.json` — confusion map, trouble domains, leverage table, reconciliation.
- `outputs/work/domain_costs.json` — cross/within split, corpus band counts, re-pass cost model.
- `outputs/work/disagreement_examples.txt` — all 70 disagreements with title + abstract + both models' reasons.
- Scripts: `pipeline/d01_domain_diagnosis.py`, `pipeline/d02_disagreement_examples.py`, `pipeline/d03_costs_and_split.py`.

---

## TL;DR

- Domain agreement is **70.5%** (167/237); theme agreement **86.2%** (206/239) — reconciles **exactly** with `goldset_metrics.json`.
- The 70 domain disagreements are **very diffuse**: 65 distinct domain→domain pairs, only 4 pairs occur ≥2×. There is **no single dominant confusion** — this is a structural taxonomy problem, not one bad domain.
- **Two root causes dominate:** (1) a handful of **near-duplicate / fuzzy-boundary domain pairs** (Power-Systems vs Grid-Integration, Materials-Joining vs Structural-Dynamics vs Composite, PV-device vs PV-material, synthesis vs therapy, method vs application); and (2) **taxonomy gaps** — ~27% of disagreements are genuinely **out-of-scope papers** (thermodynamic cycles, IC-engine combustion, cement chemistry, MEMS, cryptography, fundamental physics) that both models "least-misfit" into *different* catch-all domains.
- **31 of 70 disagreements (44%) are cross-theme** (the theme itself is contested), so a strict theme-locked re-pass structurally cannot fix them.
- **Recommendation: taxonomy-sharpening is the higher-leverage lever; complement it with a cheap Haiku domain-only re-pass of the <0.8 papers (~$25–41), NOT a strict theme-lock.** A Sonnet whole-corpus re-pass (~$188–302) does not fit the remaining budget.

---

## 1. Domain confusion map (from the 250-paper gold sample)

Disagreements where production label ≠ Sonnet label: **70** (comparable pairs: 237; agree: 167).

### 1a. Top domain→domain disagreement pairs (most frequent first)

| # | Production domain → Sonnet domain | Kind | Count |
|---|---|---|---|
| 1 | Power Systems & Grid Control → Grid Integration & Smart Microgrids | cross-theme | 3 |
| 2 | Next-Generation Photovoltaic Materials → Grid Integration & Smart Microgrids | within-theme (Energy) | 2 |
| 3 | Materials, Joining & Mechanical Behavior → Structural Dynamics & Seismic Engineering | cross-theme | 2 |
| 4 | Grid Integration & Smart Microgrids → Solar Thermal Energy & Heat Transfer Systems | within-theme (Energy) | 2 |
| 5 | Clinical Diagnostics & Biomarkers → Neuroscience & Neurophysiology | within-theme (Healthcare) | 1 |
| 6 | Materials, Joining & Mechanical Behavior → Composite & Laminate Structures | cross-theme | 1 |
| 7 | Composite & Laminate Structures → Materials, Joining & Mechanical Behavior | cross-theme | 1 |
| 8 | Organometallic & Chalcogenide Synthesis → Drug Delivery & Molecular Therapeutics | cross-theme | 1 |
| 9 | Drug Delivery & Molecular Therapeutics → Organometallic & Chalcogenide Synthesis | cross-theme | 1 |
| 10 | Algorithms & Computational Complexity → Wireless Network Access & Resource Allocation | cross-theme | 1 |

The remaining 55 pairs are single-count. Full ordered list is in `domain_diagnosis.json → top_domain_pairs`. The takeaway is that the errors form **families around a few trouble domains**, not repeated identical pairs.

### 1b. "Trouble domains" — appearing most often on either side of a disagreement

| Domain (theme) | Total involved | As prod side | As Sonnet side |
|---|---|---|---|
| **Grid Integration & Smart Microgrids** (Energy) | 11 | 2 | 9 |
| **Algorithms & Computational Complexity** (AI/ML) | 6 | 4 | 2 |
| **Solar Thermal Energy & Heat Transfer Systems** (Energy) | 5 | 1 | 4 |
| Organometallic & Chalcogenide Synthesis (Adv Materials) | 4 | 2 | 2 |
| Wireless Network Access & Resource Allocation (Next-Gen Comm) | 4 | 0 | 4 |
| Power Systems & Grid Control (Smart Infra) | 4 | 4 | 0 |
| Composite & Laminate Structures (Adv Materials) | 4 | 2 | 2 |
| Materials, Joining & Mechanical Behavior (Manuf) | 4 | 3 | 1 |
| Semiconductor Photovoltaic & Photodetection Devices (Quantum/Semi) | 4 | 3 | 1 |

`Grid Integration & Smart Microgrids` is overwhelmingly a **destination** (9 of 11 as the Sonnet side) — i.e. it acts as a **catch-all sink** for energy/power/thermodynamic papers, while production under-assigns to it. `Algorithms & Computational Complexity` and `Materials, Joining & Mechanical Behavior` behave as **sources** (production over-assigns), i.e. they are too broad.

### 1c. Split by confidence band (confirms the mid-band hypothesis)

| Band | Disagree / comparable | Disagree % | within-theme | cross-theme |
|---|---|---|---|---|
| <0.5 | 29 / 89 | 32.6% | 22 | 7 |
| **0.5–0.8** | **31 / 75** | **41.3%** | 13 | **18** |
| ≥0.8 | 10 / 73 | 13.7% | 4 | 6 |

- The **0.5–0.8 mid-band has the worst domain agreement (58.7%)** and is where **cross-theme** disagreements concentrate (18 of 31 cross-theme errors) — the mid-band is exactly where the *theme itself* is contested.
- The <0.5 band is dominated by **within-theme forced-fits** (22 of 29) — low-confidence papers that have no clean domain home and get scattered.

---

## 2. Corpus-wide pressure check & impact sizing

Corpus: **68,090 classified** papers (+2,208 unclassifiable = 70,298 rows). Confidence profile: ≥0.8 → 40,564 (59.6%); 0.5–0.8 → 25,824 (37.9%); <0.5 → 1,702 (2.5%, = the `lowconf_review.csv` set). **27,526 papers (40.4%) are <0.8.**

Leverage = corpus papers in the domain × its gold disagreement-rate-as-production-label. **Rank of highest-leverage fixes** (⚠ disagreement rates come from tiny per-domain gold counts of 1–4, so treat rates as *indicative*; corpus counts are exact):

| Trouble domain | Corpus papers | of which <0.8 | mean conf | disagree-rate (gold) | leverage (papers) |
|---|---|---|---|---|---|
| Environmental Assessment & Land Use Management | 1,657 | 985 | 0.785 | 1.0 (1/1)⚠ | ~1,657 |
| Power Systems & Grid Control | 2,039 | 285 | 0.884 | 0.57 (4/7) | ~1,165 |
| Materials, Joining & Mechanical Behavior | 2,210 | 1,221 | 0.802 | 0.50 (3/6) | ~1,105 |
| Algorithms & Computational Complexity | 3,317 | 1,634 | 0.796 | 0.27 (4/15) | ~885 |
| Carbon Utilization & Chemical Conversion | 1,081 | 577 | 0.791 | 0.60 (3/5) | ~649 |
| Fluid-Particle Flow & Multiphase Systems | 972 | 611 | 0.779 | 0.67 (2/3) | ~648 |
| Organometallic & Chalcogenide Synthesis | 1,651 | 1,135 | 0.754 | 0.40 (2/5) | ~660 |
| Semiconductor Photovoltaic & Photodetection Devices | 1,626 | 881 | 0.802 | 0.33 (3/9) | ~542 |
| Grid Integration & Smart Microgrids | 1,848 | 508 | 0.839 | 0.25 (2/8)* | ~462 |
| Solar Thermal Energy & Heat Transfer Systems | 777 | 196 | 0.850 | 0.50 (1/2)⚠ | ~389 |

*Grid Integration is understated by prod-side rate because it is mostly a *destination* (9 of 11 involvements as the Sonnet side). Full table: `domain_diagnosis.json → leverage_ranked`.

**Reading:** the biggest corpus footprints among trouble domains are `Algorithms & Computational Complexity` (3,317), `Materials, Joining & Mechanical Behavior` (2,210), `Power Systems & Grid Control` (2,039), `Grid Integration` (1,848), `Environmental Assessment` (1,657), `Organometallic & Chalcogenide Synthesis` (1,651), `Semiconductor PV & Photodetection` (1,626). These are where a fix moves the most papers.

---

## 3. Root-cause read per trouble pair + concrete taxonomy fixes

For each, I read both domains' scope/definitions and 3–4 disagreed papers (see `disagreement_examples.txt`). Highest-leverage first. **Do NOT apply these yet — proposed wording only.**

### FIX 1 — Power Systems & Grid Control (Infra) ⟷ Grid Integration & Smart Microgrids (Energy)  ·  leverage ≈ 1,165 + 462
**Why they collide:** near-duplicate definitions. Both cover microgrids, droop control, power sharing, grid-connected inverters, DER integration. Genuine cross-theme seam. Examples that split the two models: *"Efficient power sharing approach for photovoltaic generation based microgrids"*, *"Improvements in the performance of self-excited induction generator through series compensation"*, *"Grid-Connected Single-Phase Transformerless Inverter Controlling Two Solar PV Arrays"*.
**Proposed tie-break (add to both scope notes):** _"If the subject is a renewable/DER source being interfaced to the grid (PV/wind/battery inverter control, MPPT, droop control of DER, renewable microgrids) → Energy / **Grid Integration & Smart Microgrids**. If the subject is the bulk power network itself, independent of any specific renewable source (load-flow, transmission loss, AGC/frequency & voltage control of interconnected grids, generator/machine modeling, protection, network stability) → Smart Infra / **Power Systems & Grid Control**. Rule of thumb: 'renewable source → grid' = Energy; 'grid/network operation' = Infrastructure."_

### FIX 2 — Energy theme has no home for heat-engines / thermodynamic cycles / combustion / energy-harvesting (Grid Integration & Solar Thermal are absorbing them)  ·  leverage ≈ 462 + 389, and ~10 scattered disagreements
**Why:** no domain fits thermodynamic cycles, refrigeration, IC-engine combustion, or small-scale energy harvesting, so both models scatter them into Grid Integration / Solar Thermal / Carbon Utilization / Biomass as "least misfit" — *inconsistently*. Examples: *"Optimal criteria … irreversible intercooled regenerative modified Brayton cycle"*, *"Theoretical analysis of LiBr/H2O absorption refrigeration systems"*, *"Effects of exhaust gas recirculation on flame kernel growth … hydrogen fuelled spark ignition engine"*, *"Analysis of nonlinear spring arm … vibrational energy harvesting"*, *"Energy Harvesting from Water Droplet Motion"*. This is a **gap**, not an overlap.
**Proposed fix (add one Energy domain):** _"**Thermal Systems, Engines & Energy Harvesting** — thermodynamic-cycle analysis and optimization (Brayton/Rankine/refrigeration/absorption cycles), internal-combustion and alternative-fuel engine combustion, waste-heat recovery, and small-scale mechanical/electrostatic energy harvesters, where the contribution is energy conversion/thermodynamic performance rather than grid integration, a solar collector, a fuel/biomass feedstock, or an electrode material."_ (Alternative if a new domain is unwanted: add a scope-note line routing these to `unclassifiable` rather than forcing Grid Integration/Solar Thermal.)

### FIX 3 — Materials, Joining & Mechanical Behavior (Manuf) ⟷ Structural Dynamics & Seismic Engineering (Infra) ⟷ Composite & Laminate Structures (Adv Materials)  ·  leverage ≈ 1,105 + 347
**Why they collide:** "mechanical/structural analysis of a component" straddles three domains; the existing synthesis-vs-processing tie-break doesn't cover pure mechanics. Examples: *"…Dynamic Responses of Solid Plate, Stiffened Plate, and Sandwich Plate … under Explosive Loadings"* (Manuf vs Infra), *"Parametric Optimization of Joints and Links of Space Deployable Antenna Truss"* (Manuf vs Infra), *"Uniformly strained anisotropic elastoplastic rods…"* (Manuf vs Adv-Materials), *"Upcycling Textile Waste to Fiber Reinforced Polymer Composites"* (Adv-Materials vs Manuf).
**Proposed tie-break (add to all three scope notes):** _"For mechanical/structural-analysis papers: if the object is a civil/infrastructure structure (building, bridge, tank, foundation, seismic response) → Infra / **Structural Dynamics & Seismic Engineering**; if the object is a fiber-reinforced, laminated, or functionally-graded **composite** studied for its structural mechanics → Adv Materials / **Composite & Laminate Structures**; if the contribution is material mechanical behavior tied to a forming/joining/machining process or high-strain-rate metal response → Manufacturing / **Materials, Joining & Mechanical Behavior**."_

### FIX 4 — Cement / concrete / construction materials have no home (scattered across Composite & Laminate, Ferroelectric Ceramics, Building Energy, Structural Dynamics)  ·  gap
**Why:** cement chemistry & concrete durability land wherever. Examples: *"Why Low-Grade Calcined Clays Are Ideal for … Limestone Calcined Clay Cement (LC3)"* (→ Ferroelectric Ceramics, clearly wrong), *"Effect of Limestone on Electrical Properties of Cementitious Systems"* (Building Energy vs Structural Dynamics).
**Proposed fix (Smart Infra):** add domain _"**Construction Materials & Concrete Technology** — cementitious systems, supplementary cementitious materials, geopolymers, concrete durability/transport properties and mix design"_ **or** add a scope-note route: _"cement/concrete materials chemistry → Geotechnical Engineering & Soil Mechanics (or the new Construction Materials domain), never Ferroelectric & Magnetic Ceramics."_

### FIX 5 — Algorithms & Computational Complexity (AI/ML): out-of-scope dump + method-vs-application  ·  leverage ≈ 885, corpus 3,317 (largest trouble domain)
**Why:** two failure modes. (a) Out-of-scope math/physics/hardware papers forced in because it is the most generic math domain — *"Prospecting bipartite dark matter through gravitational waves"*, *"…Second-Gradient Hyperelastic Theory for Thin Shells"*, *"Multi-hop routing … multi-FPGA boards"* — these should be **unclassifiable**. (b) network/graph algorithms bounce to the application: *"Path diminution in node-disjoint multipath routing…"* (→ Wireless Access), *"Discovering … communities in dark multi-layered networks"* (→ Social Media Analytics).
**Proposed scope-note addition:** _"This domain is for CS algorithm/complexity contributions (data structures, graph/parallel algorithms, complexity bounds, optimization methods). It is NOT a home for physics, continuum/structural mechanics, or hardware-layout papers; such papers with no CS-algorithmic contribution and no other theme fit → **unclassifiable**. Tie-break: an algorithm whose contribution is a networking/routing protocol → Next-Gen Comm / Wireless Network Access; a graph method whose contribution is social-network insight → Social Sciences / Social Media Analytics; only application-agnostic algorithm design stays here."_

### FIX 6 — Organometallic & Chalcogenide Synthesis (Adv Materials) ⟷ Drug Delivery & Molecular Therapeutics (Healthcare)  ·  leverage ≈ 660, corpus 1,651
**Why:** synthetic chemistry with a *stated* bioactivity collides with Healthcare; the domain name also under-covers general organic/coordination chemistry. Examples: *"Synthesis of 1-methyl-4-nitro-5-substituted-imidazole … antiparasitic agents"*, *"BF3·Et2O Catalysed … Pro-SERMs"*, *"…bismuth molybdate … degradation of organic pollutants"*, *"Quantifying Packing Efficiency in Molecular Crystals"*.
**Proposed tie-break (extend the existing Adv-Materials antibacterial tie-break):** _"Synthesis of small molecules/coordination compounds: if the contribution is the synthetic method or the compound's material/structural characterization → Adv Materials / **Organometallic & Chalcogenide Synthesis**, even when a biological activity is stated as motivation. Assign Healthcare / **Drug Delivery & Molecular Therapeutics** only when the paper evaluates the compound in a biological/pharmacological model (in-vitro/in-vivo efficacy, PK, or a delivery vehicle). Motivation ≠ evaluation."_ Consider renaming the domain to **"Synthetic & Coordination Chemistry"** so it visibly covers general organic synthesis, not only chalcogenides.

### FIX 7 — Global "method vs application" master tie-break (Clinical AI / Signal / Transportation / Hydrology ⟷ AI/ML domains)  ·  affects the AI/ML domains corpus-wide
**Why:** the scopes already say "algorithm→AI/ML, application→domain", but it is applied inconsistently (Sonnet leans method, Haiku leans application). Examples: *"EEG signal classification"* (HMM) → ML&NN vs Clinical AI; *"Improving measurement geometry … scattered field data"* (SVM) → ML&NN vs Signal Modulation; *"FPGA-based smart camera … video surveillance"* → ML&NN vs Transportation; *"zeroInertiaFlowFOAM … flood inundation"* → CFD vs Hydrology.
**Proposed global tie-break:** _"Operational test for ML/computational papers: assign to AI/ML **only** if the novelty is a new/modified algorithm or architecture, or a general methodological result on benchmark-style data. If it uses standard/off-the-shelf methods (SVM, HMM, standard CNN, standard CFD solver, kriging) to obtain a result about a specific application (a disease, a channel, a road network, a flood) → assign the **application** domain. For medical signals/images prefer Healthcare; for a named engineering application prefer that theme."_

### FIX 8 — Semiconductor Photovoltaic & Photodetection Devices (Quantum/Semi): over-broad optical-device sink + PV device-vs-material seam  ·  leverage ≈ 542, corpus 1,626
**Why:** absorbs any opto-electronic device (organic-solar-cell HTL, holography, SAW/IDT, phosphor lighting), colliding with Fiber Photonic, Quantum Photonics and Energy's PV Materials. Examples: *"CoSP … blue MoO3 nanoparticles … hole transport layer (HTL) in organic solar cells"* (device vs Energy PV material), *"…digital holographic imaging"*, *"SPICE Simulation of Surface Acoustic Wave Interdigital Transducers"*, *"Laser-driven phosphor-converted green … solid state lighting"*.
**Proposed tie-break:** _"PV/solar-cell papers: contribution = device physics/fabrication of the cell/detector (junction engineering, I–V, EQE, architecture) → Quantum-Semi / **Semiconductor Photovoltaic & Photodetection Devices**; contribution = a new absorber/HTL/ETL material or conversion efficiency of the material → Energy / **Next-Generation Photovoltaic Materials**. Acousto-optic (SAW/IDT) and holographic-imaging papers are NOT photodetection (route to the relevant device/circuit domain or unclassifiable); phosphor-lighting → Adv Materials / **Rare-Earth Doped Luminescent Materials**."_

---

## 4. Fix impact & cost of a re-pass

### Which lever matters more
- **~44% of domain errors are cross-theme** (31/70): the theme itself is disputed, so a *strict theme-locked* domain-only re-pass **cannot** fix them.
- **~27% of errors are out-of-scope / taxonomy-gap papers** (thermodynamics, combustion, cement, MEMS, crypto, fundamental physics): no re-pass fixes these — they need **new domains or an explicit unclassifiable path** (Fixes 2, 4, 5, and the unclassifiable routing).
- Only the **~39 within-theme swaps**, and only where the locked theme is actually correct, are addressable by a theme-locked re-pass.
- ⟹ **Taxonomy sharpening (lever a) is the higher-value lever here.** A re-pass (lever b) is a cheap *complement*, best run **after** sharpening, and ideally **not strictly theme-locked** (or theme-locked only on the subset with high theme-confidence) so it can also repair the cross-theme errors.

### Token/$ cost of a domain-only re-pass
Prices reconciled exactly from `cost_tracker.json`: **Haiku** $1/M in · $5/M out · $0.10/M cache-read; **Sonnet** $3/M in · $15/M out · $0.30/M cache-read. Domain-only prompt = one theme's taxonomy (cached) + one paper; tiny JSON output. Per-paper token assumptions: cache-read 1,200–1,800; fresh input 400–650; output 80–130.

| Model | per paper | **<0.8 papers only (27,526)** | Whole corpus (68,090) |
|---|---|---|---|
| **Haiku** | $0.0009–0.0015 | **$25 – $41** | $63 – $101 |
| **Sonnet** | $0.0028–0.0044 | $76 – $122 | $188 – $302 |

**Against the budget:** `cost_tracker.json` shows **$150.18 already spent** (stop cap $255). If the owner's ceiling is ~$200, only **~$50 remains**:
- ✅ **Haiku, <0.8 re-pass (~$25–41)** — best fit; targets the 40% of the corpus where errors concentrate.
- ✅ Haiku whole-corpus (~$63–101) — feasible only if the $255 cap (not $200) is the true ceiling.
- ⚠️ Sonnet <0.8 (~$76–122) — exceeds the ~$50 remaining under a $200 budget.
- ❌ Sonnet whole-corpus (~$188–302) — out of budget.

---

## 5. TEST / reconciliation with `goldset_metrics.json`

| Metric | Reported | Recomputed here | Match |
|---|---|---|---|
| Theme agreement | 86.2% (206/239) | 86.2% (206/239) | ✅ |
| Domain agreement | 70.5% (167/237) | 70.5% (167/237) | ✅ |
| Refusals / Sonnet-unclassifiable | 10 / 1 | 10 / 1 | ✅ |
| Domain disagree by band (<0.5 / 0.5–0.8 / ≥0.8) | 29 / 31 / 10 | 29 / 31 / 10 | ✅ |
| Theme-right-domain-wrong (within-theme) | 39 | 39 | ✅ |

**One nuance worth flagging:** 2 Sonnet rows carried a valid *theme* but a domain that doesn't belong to that theme (schema-invalid — e.g. `Manufacturing & Industry 4.0` + `Supply Chain & Operations Management`). The metrics script (correctly) counts them as theme-comparable (denominator 239) but excludes them from domain-comparable (denominator 237). Replicating that logic reproduces every number exactly. No discrepancy.

---

## Concise answers

**Top ~10 confused domain pairs:** Power Systems & Grid Control→Grid Integration (3, cross); PV Materials→Grid Integration (2); Materials-Joining→Structural Dynamics (2, cross); Grid Integration→Solar Thermal (2); then a long tail of single-count pairs clustered around the trouble domains (Clinical Diagnostics→Neuroscience; Materials-Joining↔Composite; Organometallic↔Drug Delivery; Algorithms→Wireless Access; …). 65 distinct pairs total — errors are diffuse.

**Trouble domains & corpus impact:** Grid Integration & Smart Microgrids (1,848), Algorithms & Computational Complexity (3,317), Solar Thermal (777), Organometallic & Chalcogenide Synthesis (1,651), Wireless Network Access (865), Power Systems & Grid Control (2,039), Composite & Laminate (693), Materials-Joining & Mechanical Behavior (2,210), Semiconductor PV & Photodetection (1,626). Highest leverage: Power Systems/Grid, Materials-Joining, Algorithms, Environmental Assessment, Organometallic Synthesis, Carbon Utilization, Fluid-Particle Flow.

**Top 8 fixes (highest-leverage first):** (1) Power-Systems vs Grid-Integration tie-break; (2) add Energy "Thermal Systems, Engines & Energy Harvesting" domain (or unclassifiable route); (3) Materials-Joining vs Structural-Dynamics vs Composite tie-break; (4) add "Construction Materials & Concrete Technology" home; (5) tighten Algorithms & Computational Complexity + unclassifiable routing for out-of-scope physics/hardware; (6) synthesis-vs-therapy tie-break (Organometallic vs Drug Delivery); (7) global method-vs-application operational test; (8) PV device-vs-material + narrow the Photodetection sink. Exact wording in §3.

**Recommendation:** Do **taxonomy sharpening first** (§3) — it is the only lever that fixes the 44% cross-theme errors and the 27% out-of-scope leakage. Then run a **Haiku domain-only re-pass on the <0.8 papers (~$25–41)**, *not* a strict theme-lock, to mop up the residual within-theme swaps. Sonnet whole-corpus (~$188–302) is not worth it against the ~$50 remaining under a $200 budget ($150 already spent).
