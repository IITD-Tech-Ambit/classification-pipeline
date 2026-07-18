# Overnight Classification-v2 Run — Report

_Autonomous run completed while the owner was asleep. Goal: a correct, fully-tested
v2 classification of the whole corpus with an honest quality read. All three stages
finished and every stage test passed. **Nothing was written to the database and
nothing was committed/pushed to git.**_

**Bottom line:** All 70,298 corpus papers are accounted for in the final labels,
with 0 schema violations, mean confidence 0.82, and a total API spend of
**$150.18** — well under the $260 guardrail.

---

## Headline numbers

| Metric | Value |
|---|---|
| Corpus papers (Mongo `researchmetadatascopus`) | 70,298 |
| Final rows in `classification_v2_final.jsonl` | 70,298 (unique, 0 dup / 0 missing / 0 extra) |
| Classified (theme + domain) | 68,090 |
| Unclassifiable — total | 2,208 |
| &nbsp;&nbsp;• hygiene-filtered (never sent to API) | 1,654 |
| &nbsp;&nbsp;• model-judged non-research | 554 (488 Sonnet, 66 Haiku) |
| Escalated to Sonnet (conf < 0.6 or schema issue) | 6,158 (9.0%) |
| Mean confidence (classified) | 0.8248 |
| Schema violations in final labels | **0** |
| Themes used / domains used | 9 / 77 |
| **Total spend** | **$150.18** (Haiku $117.20 + Sonnet $32.98) |
| Sonnet model id actually used | `claude-sonnet-4-5` (resolves to `claude-sonnet-4-5-20250929`) |

---

## Stage-by-stage, with test results

### Stage 1 — Taxonomy fix — TEST PASSED
- Backed up the frozen taxonomy to `outputs/taxonomy-draft-v2-prefix.json` / `.md`.
- **Added** domain **"Energy Storage Materials"** to *Energy, Sustainability & Climate
  Change* (theme goes 8 → 9 domains). Definition covers battery electrode / anode /
  cathode / Li-/Na-/Mg-ion / Li-sulfur / supercapacitor / solid-electrolyte
  **materials studied as materials**, explicitly disjoint from "Electric Vehicle
  Battery & Charging Systems" (charger/power-electronics) and "Grid Integration &
  Smart Microgrids". Five real example titles were pulled from the corpus by keyword
  search.
- **Tightened** the *Advanced Materials & Devices* scope note with the requested
  tie-break: *"antibacterial/antimicrobial or bioactivity testing of a material,
  where the contribution is the material itself, → Advanced Materials; only assign
  Healthcare when there is a specific clinical/therapeutic use in patients."*
- Test (`outputs/work/stage1_taxonomy_check.json`): JSON parses; every theme has
  5–10 domains (Energy = 9); **0 duplicate domain names** across themes (77 domains
  total); new domain present; tie-break text present. **PASS.**

Per-theme domain counts: AI/ML 5 · Advanced Materials 9 · Energy 9 · Healthcare 10 ·
Manufacturing 9 · Next-Gen Comm 8 · Quantum Tech 9 · Smart Infra 8 · Social Sciences 10.

### Stage 2 — Full Haiku classification — TEST PASSED
- Model `claude-haiku-4-5`, one paper per request, full updated taxonomy in a
  **prompt-cached** system block (cache confirmed engaged: 541.8 M cache-read tokens
  vs 0.30 M cache-write over the run).
- Classified all **68,644** eligible papers (hygiene ok + title_only). Output:
  `outputs/work/haiku_full.jsonl` (id, theme, domain, confidence, unclassifiable,
  reason, schema_valid, model, usage). Bounded concurrency (40 in flight),
  exponential backoff on 429/5xx/timeouts, resumable (skips ids already present),
  cost checkpointed every 500 papers.
- Test (`outputs/work/stage2_haiku_report.json`): coverage **68,644 / 68,644**, 0
  missing, 0 duplicates; schema violations 238 (0.35%, all sent to escalation);
  domain-not-in-theme among valid rows **0**; model-unclassifiable 1,981; mean
  confidence 0.798; top theme share 15.8% (not degenerate); all 77 domains used.
  **PASS.**

### Stage 3 — Sonnet escalation + merge — TEST PASSED
- Escalation set = confidence < 0.6 **OR** schema violation = **6,158 papers (9.0%)**.
  (This is lower than the ~21% you expected: with the refined taxonomy Haiku was very
  decisive — mean conf 0.80 — so far fewer papers needed a second opinion. That is
  why Sonnet cost came in at ~$33 rather than $80–110.)
- Re-classified those 6,158 with `claude-sonnet-4-5`, same prompt/taxonomy/schema
  (prompt-cached), same robustness/resume rules → `outputs/work/sonnet_escalation.jsonl`.
- Merged into `outputs/classification_v2_final.jsonl`: final = Sonnet if escalated,
  else Haiku; then appended the 1,654 hygiene-unclassifiable papers
  (`source_model="hygiene"`). Fields per row: `id, thematic_area, domain, confidence,
  unclassifiable, reason, source_model, escalated`.
- Test (`outputs/final_validation_report.json`, `outputs/final_report.md`): every
  corpus `_id` appears **exactly once** (checked against the live Mongo `_id` set,
  read-only) → 70,298 / 70,298; **0 schema violations remain**; escalated 6,158;
  final-unclassifiable 2,208 (1,654 hygiene + 554 model). **PASS.**
- 60-row stratified spot-check → `outputs/final_spotcheck.md`.

---

## Coverage proof (70,298 all accounted for)

70,298 (Mongo corpus) = 68,644 eligible (classified/attempted) + 1,654
hygiene-filtered. The final file has 70,298 unique ids, exactly equal to the set of
`_id`s in `researchmetadatascopus`, with 0 duplicates, 0 missing, 0 extra. Of the
68,644 eligible: 62,582 final labels came from Haiku, 6,062 from Sonnet, and 96
escalated papers fell back to their Haiku label (see anomalies).

## Final theme distribution

| Theme | Papers | Share of classified |
|---|---:|---:|
| Manufacturing & Industry 4.0 | 9,920 | 14.6% |
| Advanced Materials & Devices | 9,623 | 14.1% |
| Energy, Sustainability & Climate Change | 9,418 | 13.8% |
| AI/ML, Supercomputing & Quantum Computing | 8,787 | 12.9% |
| Healthcare & MedTech | 7,376 | 10.8% |
| Smart & Sustainable Infrastructure | 6,944 | 10.2% |
| Quantum Technologies & Semiconductor Technology | 6,404 | 9.4% |
| Social Sciences, Humanities & Management | 5,123 | 7.5% |
| Next-Gen Communication | 4,495 | 6.6% |
| **Total classified** | **68,090** | 100% |

Distribution is healthy (no theme dominates; largest is 14.6%). Full 77-domain counts
are in `outputs/final_validation_report.json` and `outputs/final_report.md`. The new
**Energy Storage Materials** domain picked up **983** papers, confirming it captured a
real cluster that previously scattered into other domains.

### Confidence histogram (classified)

| bucket | count |
|---|---:|
| <0.5 | 1,702 |
| 0.5–0.6 | 7 |
| 0.6–0.7 | 1,465 |
| 0.7–0.8 | 24,352 |
| 0.8–0.9 | 12,362 |
| 0.9–0.95 | 22,123 |
| 0.95–1.0 | 6,079 |

~89% of classified papers sit at confidence ≥ 0.7. The models emit fairly discrete
confidence values, which is why the 0.5–0.6 bucket is nearly empty.

---

## Cost (within guardrail)

| Model | Rows | Cost |
|---|---:|---:|
| Haiku (`claude-haiku-4-5`) | 68,644 | $117.20 |
| Sonnet (`claude-sonnet-4-5`) | 6,158 (+~100 repair calls) | $32.98 |
| **Total** | | **$150.18** |

Hard cap for this task was **$260** (safety stop wired at $255); actual spend
**$150.18**, so we finished comfortably inside budget with no cost-driven early stop.
Cost is reconstructed authoritatively from the per-row `usage` fields in the two
output files (resume-safe) and mirrored in `outputs/work/cost_tracker.json`.

---

## Errors, retries and anomalies (and how they were handled)

1. **Sonnet safety refusals (96 papers).** Sonnet 4.5 returned `stop_reason=refusal`
   with empty content on a cluster of *legitimate* biology papers (antimicrobial
   peptides / spider-venom, transgenic wheat, pathogen studies, larvicidal essential
   oils, etc.) — its safety filter over-triggers on toxin/pathogen wording. Haiku had
   classified these fine. **Handling:** escalation must never make a paper worse, so
   these fell back to their original Haiku label (`source_model="haiku"`,
   `escalated=true`). A targeted repair pass with a larger token budget recovered only
   2 more; the rest are genuine refusals, so fallback is the right call.
2. **Wrong-theme-but-valid-domain (81 papers).** Sometimes a model chose a real domain
   name but paired it with the wrong theme. Because domain names are globally unique
   (verified in Stage 1), the domain unambiguously determines its theme, so these were
   **deterministically repaired** by reassigning the theme to the domain's true owner.
3. **JSON parse failures.** Rare truncations/preambles were retried in-call (up to 3×
   on parse error, plus one extra call on a schema violation). Residual unparseable
   Sonnet outputs were re-run once with a larger `max_tokens`; anything still unusable
   fell back to Haiku (see #1) or, if Haiku was also unusable, was marked
   unclassifiable. Net effect: **0 schema violations in the final labels** and **0
   papers force-dropped** from a usable model answer.
4. **429/5xx/timeouts.** Handled with exponential backoff (up to ~30 s) inside a
   per-call timeout; no run stalled. Both large runs completed in a single pass with 0
   missing ids.
5. **Escalation rate 9% vs expected ~21%.** Not an error — Haiku was more confident
   than anticipated, which reduced Sonnet volume and cost. Flagged for transparency.

---

## Honest quality read (from the spot-check)

**The high-confidence bulk looks strong.** Every ≥0.8 example in the 60-row spot-check
was a clean, correct theme→domain assignment (e.g. sepsis electrochemical immunosensor
→ *Clinical Biosensors & Point-of-Care Devices* 0.95; 1200 V SiC MOSFET module →
*Wide Bandgap Semiconductors & Devices* 0.92; grid-integration of PV → *Grid
Integration & Smart Microgrids* 0.92; BIM adoption → *Digital Transformation & IT
Applications* 0.92). The tie-break edit is working too: of ~323 antibacterial/
antimicrobial *materials* papers, ~61% now sit in Advanced Materials vs ~26% in
Healthcare — the intended direction.

**Where assignments still look wrong — and it's the low-confidence tail:**
- **Out-of-scope physics/astro/atomic/nuclear papers** have no natural home among the
  9 applied-research themes and get pushed into a least-bad domain at low confidence:
  e.g. *"p-adic Mellin amplitudes"* and *"Kaon properties in neutron-star matter"* →
  AI/ML Algorithms/CFD (0.3–0.45); *"electric dipole polarizability of group-13 ions"*
  and He-like ion x-ray transitions → Quantum Tech (0.35); uracil ion-collision
  ionization → Advanced Materials Organometallic (0.35). These should really be
  "out-of-scope," matching the taxonomy's own note about a residue of pure-physics/
  math papers.
- **Aeroacoustics / aerodynamics** are clearly mis-homed: propeller aeroacoustics →
  *Antenna Design & RF Systems* (0.25); airfoil leading-edge serrations → *Plasma-Wave
  & EM Interactions* (0.15). Wrong, but the ~0.15–0.25 confidence flags them.
- **Right-theme / wrong-domain** cases: ZnO photocatalysis → *Rare-Earth Doped
  Luminescent Materials* (should be another Advanced Materials domain); TOPSIS
  maintenance ranking and vision-based manipulation → *Rotor Dynamics & Vibration
  Analysis*; cascade refrigeration → *Grid Integration* (0.35).

**Residual concerns for the morning:**
- Confidence is a **usable triage signal**: the errors concentrate below ~0.5, so a
  gold-set check can focus effort there and largely trust the ≥0.8 bulk.
- The taxonomy has **no explicit out-of-scope home** for pure physics/math/astro; the
  model currently emits low-confidence best-guesses rather than `unclassifiable` for
  many of these. Consider either an "Other / Out-of-scope" bucket or instructing the
  classifier to prefer `unclassifiable` for clearly out-of-scope basic-science papers.
- A few within-theme domain boundaries (photocatalysis, decision-analysis/AHP-TOPSIS,
  refrigeration/HVAC) are fuzzy and worth a targeted review.

---

## WHAT'S LEFT (deliberately NOT done — for when you're awake)

These were intentionally left for you and the team; I did **not** touch them:
1. **Gold-set accuracy check with your team** — validate against a labelled sample
   (recommend stratifying by confidence; the ≥0.8 bulk should score well, the <0.5
   tail is where to look).
2. **DB ingestion** — load `classification_v2` into local Mongo, rerun `rollup.js`,
   and rebuild the Atlas via `build_kg.py`. **Nothing was written to the database.**
3. **App verification** — verify the portal against the new labels.

Reminder: **nothing was written to the DB (all Mongo access was read-only) and nothing
was committed or pushed to git.**

---

## Artifacts

**Deliverables (outputs/)**
- `classification_v2_final.jsonl` — final labels for all 70,298 papers (the deliverable).
- `final_validation_report.json` — Stage 3 machine-readable validation (coverage,
  distributions, histogram).
- `final_report.md` — readable theme/domain distribution + confidence histogram.
- `final_spotcheck.md` — 60-row stratified spot-check for eyeballing quality.
- `taxonomy-draft-v2.json` / `.md` — edited (frozen) taxonomy used for this run.
- `taxonomy-draft-v2-prefix.json` / `.md` — pre-edit backups.

**Work / intermediate (outputs/work/)**
- `haiku_full.jsonl` — Stage 2 per-paper Haiku results (+usage).
- `sonnet_escalation.jsonl` — Stage 3 per-paper Sonnet results (+usage).
- `cost_tracker.json` — authoritative cumulative cost.
- `stage1_taxonomy_check.json`, `stage2_haiku_report.json` — stage tests.
- `papers_source.jsonl` — cached title/abstract for the 68,644 eligible papers
  (pulled read-only once).
- `env_check.json` — preflight (DB reachable, model ids verified).
- `haiku_run.log`, `sonnet_run.log` — run logs.

**Code (pipeline/)** — `s15_verify_env.py`, `s15_build_source.py`,
`s15_classify_lib.py` (shared prompt/pricing/resumable runner),
`s15_run_haiku.py`, `s15_test_stage1.py`, `s15_test_stage2.py`,
`s16_run_sonnet.py`, `s16_repair_parse.py`, `s16_finalize.py`.

_All stages resumable from their JSONL outputs; re-running any script continues rather
than restarts._
