# Gold-Set Accuracy Estimate — Classification v2

_Method: an INDEPENDENT `claude-sonnet-4-5` label (fresh pick of the single best thematic_area + domain from the full frozen v2 taxonomy, prompt-cached, with no knowledge of the existing label) is compared against the production final label for a 250-paper stratified sample._

> **Read this first — what this number is and is not.** This is an **LLM-vs-LLM agreement rate**, a *proxy* for accuracy, **not** human ground truth. Sonnet is a different and stronger model than the Haiku that produced most labels, so where the two strong, independent signals **agree** we can be reasonably confident the label is right. Where they **disagree**, it flags a paper a human should check — it does **not** automatically mean the original is wrong (sometimes Sonnet is the one that errs, or both are defensible). The companion `goldset_template.csv` exists precisely so the team can adjudicate the disagreements and compute a true, human-verified accuracy number.

## 1. Sample composition

- Sample size: **250** classified papers (unclassifiable=false), fixed seed, reproducible.
- Independently labeled by Sonnet: **250/250**.
- Usable for **theme** comparison: **239** · usable for **domain** comparison: **237**.
- Sonnet safety-refused (empty response, `stop_reason=refusal`): **10** — all benign chem/bio abstracts (biopesticides, N95 respirators, organophosphate chemistry, nanoagrochemicals). These are a limitation of the Sonnet judge, not a data problem, and are excluded from the agreement denominators.
- Sonnet judged **unclassifiable**: **1** (also excluded from strict agreement; worth a human look).

**Confidence bands (deliberate <0.5 oversample):**

| band | papers | share |
|---|---:|---:|
| <0.5 | 101 | 40.4% |
| 0.5-0.8 | 76 | 30.4% |
| >=0.8 | 73 | 29.2% |

**Themes (proportional, ≥10 floor) & source model:**

| thematic area | papers |
|---|---:|
| Advanced Materials & Devices | 33 |
| Manufacturing & Industry 4.0 | 33 |
| Energy, Sustainability & Climate Change | 32 |
| AI/ML, Supercomputing & Quantum Computing | 31 |
| Healthcare & MedTech | 27 |
| Smart & Sustainable Infrastructure | 26 |
| Quantum Technologies & Semiconductor Technology | 25 |
| Social Sciences, Humanities & Management | 22 |
| Next-Gen Communication | 21 |

| source_model | papers |
|---|---:|
| haiku | 150 |
| sonnet | 100 |

## 2. Headline agreement (proxy accuracy)

- **Theme-level agreement: 86.2%** (206/239 comparable papers).
- **Domain-level agreement: 70.5%** (167/237 comparable papers).

## 3. Agreement by confidence band

The key diagnostic: does confidence track reliability?

| band | theme agree | domain agree |
|---|---|---|
| <0.5 | 90.1% (82/91) | 67.4% (60/89) |
| 0.5-0.8 | 76.0% (57/75) | 58.7% (44/75) |
| >=0.8 | 91.8% (67/73) | 86.3% (63/73) |

> **Honest reading — the relationship is NOT cleanly monotonic (and n per band is small).** The **≥0.8 bulk is clearly the strongest** (91.8% theme / 86.3% domain). The surprise is that the **0.5–0.8 middle band is the *weakest*** (76.0% theme / 58.7% domain), not the <0.5 tail — and that middle band is dominated by the 0.7–0.8 bucket, which is the single largest confidence bucket in the whole corpus (~24k papers). The deliberately over-sampled **<0.5 tail is middling on theme (90.1%) but soft on domain (67.4%)**. So confidence is a decent triage signal at the top end but does NOT reliably separate the mid-band from the tail; treat 0.5–0.8 as needing scrutiny too, not just <0.5.

## 4. Agreement by source model (haiku vs sonnet-escalated)

| source_model | theme agree | domain agree |
|---|---|---|
| haiku | 83.6% (117/140) | 72.9% (102/140) |
| sonnet | 89.9% (89/99) | 67.0% (65/97) |

_Note: papers labeled `sonnet` were the harder cases the pipeline escalated to Sonnet, so a lower agreement there partly reflects intrinsic difficulty, not just labeler quality. Also, the escalated labels were produced by the same model family now acting as judge, which can inflate their apparent agreement._

## 5. Theme-right / domain-wrong (the common soft error)

- Among the **206** papers where the theme matched, **39** had a differing domain — **18.9%** of theme-matches (and 16.5% of all comparable papers).
- Interpretation: the top-level theme is more reliable than the finer domain assignment; most residual risk is in domain granularity within the correct theme.

## 6. Top disagreements (where to look)

**Most frequent theme→theme disagreements (current → sonnet):**

| current theme | sonnet theme | count |
|---|---|---:|
| Smart & Sustainable Infrastructure | Energy, Sustainability & Climate Change | 4 |
| Manufacturing & Industry 4.0 | Smart & Sustainable Infrastructure | 3 |
| Manufacturing & Industry 4.0 | Advanced Materials & Devices | 3 |
| Social Sciences, Humanities & Management | Manufacturing & Industry 4.0 | 2 |
| Smart & Sustainable Infrastructure | AI/ML, Supercomputing & Quantum Computing | 2 |
| Manufacturing & Industry 4.0 | Energy, Sustainability & Climate Change | 2 |
| Advanced Materials & Devices | Energy, Sustainability & Climate Change | 1 |
| Social Sciences, Humanities & Management | AI/ML, Supercomputing & Quantum Computing | 1 |
| Smart & Sustainable Infrastructure | Advanced Materials & Devices | 1 |
| Energy, Sustainability & Climate Change | Advanced Materials & Devices | 1 |
| AI/ML, Supercomputing & Quantum Computing | Next-Gen Communication | 1 |
| AI/ML, Supercomputing & Quantum Computing | Energy, Sustainability & Climate Change | 1 |

**Current themes with the highest theme-disagreement rate:**

| current theme | disagree / comparable | rate |
|---|---|---:|
| Smart & Sustainable Infrastructure | 8/26 | 30.8% |
| Manufacturing & Industry 4.0 | 8/33 | 24.2% |
| Social Sciences, Humanities & Management | 3/22 | 13.6% |
| Healthcare & MedTech | 2/19 | 10.5% |
| AI/ML, Supercomputing & Quantum Computing | 3/30 | 10.0% |
| Next-Gen Communication | 2/21 | 9.5% |
| Advanced Materials & Devices | 3/32 | 9.4% |
| Quantum Technologies & Semiconductor Technology | 2/25 | 8.0% |
| Energy, Sustainability & Climate Change | 2/31 | 6.5% |

**Domains with the most disagreement (by current domain):**

| current domain | disagreements |
|---|---:|
| Algorithms & Computational Complexity | 4 |
| Power Systems & Grid Control | 4 |
| Digital Transformation & IT Applications | 3 |
| Carbon Utilization & Chemical Conversion | 3 |
| Materials, Joining & Mechanical Behavior | 3 |
| Signal Modulation, Detection & Channel Equalization | 3 |
| Semiconductor Photovoltaic & Photodetection Devices | 3 |
| Clinical Diagnostics & Biomarkers | 2 |
| Spintronics & Magnetic Devices | 2 |
| Hydrology & Water Resources Management | 2 |
| Fluid-Particle Flow & Multiphase Systems | 2 |
| Building Energy & Thermal Performance | 2 |

## 7. Cost

- Total spend for this gold-set exercise: **$1.92** (claude-sonnet-4-5, prompt-cached taxonomy), well under the $10 guardrail.

## 8. Honest interpretation & verdict

- A stronger, independent model agrees with the production **theme** on **86.2%** of comparable papers and with the **domain** on **70.5%**. Because the two signals are independent and Sonnet is the stronger model, this is a credible *proxy* that the theme layer is in good shape and the domain layer is the softer spot. It is still only a proxy — treat these as agreement rates, not verified accuracy.
- **Confidence is a useful but imperfect triage signal.** The ≥0.8 bulk is clearly the best (91.8% theme / 86.3% domain). But agreement is **not monotonic**: the 0.5–0.8 middle band (76.0% theme) actually scores *below* the <0.5 tail (90.1% theme). Since 0.7–0.8 is the largest confidence bucket in the corpus, that mid-band softness affects a lot of papers and deserves scrutiny alongside the <0.5 tail — you cannot assume '≥0.5 is safe'.
- The dominant residual issue is **domain-within-correct-theme** drift (18.9% of theme-matches) plus a handful of recurring theme boundary confusions (see §6) — consistent with the known taxonomy adjacencies (materials↔energy, materials↔quantum/semiconductor, manufacturing↔materials).
- **Caveats:** 10 benign papers could not be judged at all (Sonnet safety refusals) and are excluded; per-band n is small (~75–90 each), so band figures carry meaningful sampling error; and the Sonnet-escalated subset is judged by the same model family, which can inflate its apparent agreement.
- **Verdict:** on this LLM-proxy the **≥0.8 bulk — the large majority of the corpus — looks ready to ingest**, while the **<0.5 tail AND the 0.5–0.8 mid-band, plus the specific theme confusions in §6, warrant targeted human adjudication** (especially at the domain level) before any hard accuracy number is claimed. Use `goldset_template.csv` (disagreements sorted to the top) to turn this proxy into a real human gold accuracy; that human number, not this one, is what should be quoted externally.
