# Classification v3 — Domain-Accuracy Refinement Report

_Run date: 2026-07-18. Read-only on Mongo (no DB connection was even needed — the
exported `papers_source.jsonl` supplied all title+abstract text). No database
writes. No git commits or pushes. The v2 baseline is fully preserved._

## Bottom line (honest, no overselling)

**The v3 taxonomy sharpening is a genuine improvement. The blanket Haiku
re-classification that used it is NOT — as shipped it makes domain agreement
worse, not better.**

- On a fresh, independent 250-paper Sonnet re-test (exactly the method the
  original gold check used), **domain agreement fell from 70.5% → 58.8%
  (−11.7 pts)** and **theme agreement from 86.2% → 79.7% (−6.5 pts)**.
- The drop is **entirely** on the re-classified papers. The ~46k papers that were
  *not* touched still agree with Sonnet at baseline levels (domain 70.4% vs 70.5%).
- Root cause is the re-pass, not the taxonomy: the mid-confidence band (0.5–0.8,
  the largest and the pre-identified target) **improved (+9.2 pts on domain)**,
  but the low-confidence band **collapsed (−42 pts)** and Haiku **over-fired the
  new "out_of_scope" route ~13×** more than the Sonnet judge does.

**Recommendation: keep v2 as the production baseline. Do NOT ingest
`classification_v3_final.jsonl` as-is. Adopt the v3 *taxonomy*, and get the
domain gains through a targeted re-pass** (details in §7). A cheaper, evidence-
driven interim option — a conservative selective merge — is provided and scores
~parity-to-slightly-above baseline on the proxy (within noise); it still needs a
fresh validation before adoption.

---

## Cost (this task)

| item | model | calls | $ |
|---|---|---:|---:|
| Model-id verification (1 token each) | haiku + sonnet | 2 | 0.0001 |
| Stage B re-classification | claude-haiku-4-5 | 34,037 | 53.26 |
| Stage D independent re-validation | claude-sonnet-4-5 | 250 | 1.45 |
| Diagnostic full-prompt probe | claude-haiku-4-5 | 69 | 0.18 |
| **TASK TOTAL** | | | **$54.88** |

Under the **$60** hard cap (the separate $150 previously spent is not counted
here). It landed above the "$30–45 expected" band because the task specified the
**full** taxonomy in the cached prompt; cache-read on a ~12k-token prompt across
34k papers is the dominant, irreducible cost (~$33). I held it under cap with a
compact-but-complete prompt (all themes/domains/definitions/tie-breaks/global
rules kept; only descriptive scope-note prose trimmed), an 1,100-char abstract
cap, and a hard $56 stop on the Haiku stage. A calibration probe showed that
compaction cost ~7.5 pts of domain agreement on the hardest subset (see §5) — a
minor, quantified trade-off.

---

## Stage A — Taxonomy sharpening (PASS)

Built `taxonomy-draft-v3.json` / `.md` from v2 by applying the 8 concrete fixes
from `domain_diagnosis.md` §3 verbatim, adding the 2 missing-home domains, and
adding an explicit out-of-scope routing rule. **No domain was renamed** — a
deliberate choice so the ~36k v2 labels carried into v3 never become invalid
(a rename would strand them under the new taxonomy).

Test (`stageA_taxonomy_check.json`): **all 28 checks passed.**
- JSON parses; 9 themes; **every theme has 5–10 domains**; **0 duplicate domain
  names**; total domains 77 → **79**.
- All 8 fixes located in the correct domain definitions / global rules:
  FIX1 Power-Systems↔Grid-Integration tie-break; FIX2 new **Thermal Systems,
  Engines & Energy Harvesting** + narrowed Grid-Integration/Solar-Thermal sinks;
  FIX3 Materials-Joining↔Structural-Dynamics↔Composite tie-break; FIX4 new
  **Construction Materials & Concrete Technology** + Ferroelectric-Ceramics cement
  guard; FIX5 tightened Algorithms + out_of_scope route; FIX6 synthesis↔therapy
  tie-break; FIX7 global method-vs-application test; FIX8 PV device-vs-material
  de-sink.
- Per-theme counts: AI/ML 5 · Advanced Materials 9 · **Energy 10** · Healthcare 10
  · Manufacturing 9 · Next-Gen Comm 8 · Quantum/Semi 9 · **Smart Infra 9** ·
  Social Sciences 10.

## Stage B — Haiku re-classification (coverage PASS; quality mixed)

Re-classification set = **34,037** papers (all with local text):
- **27,526** classified papers with confidence < 0.8, PLUS
- **6,511** ≥0.8 papers in the 5 flagged sink domains (Grid Integration 1,340;
  Algorithms 1,683; Materials-Joining 989; Power Systems 1,754; Semiconductor PV
  745).

Full v3 taxonomy, prompt-cached; full theme+domain reassignment and out_of_scope
allowed; strict JSON; domain-in-theme enforced with one retry; bounded
concurrency (40), backoff, resumable.

Test (`stageB_repass_report.json`): coverage **34,037/34,037, 0 missing, 0 dup**.
- Schema violations after the retry: **66 (0.19%)** — carried the safe v2 label
  for those in Stage C, so 0 reach the final file.
- Changed theme: **4,737**; changed domain: **13,163**; became **out_of_scope:
  4,429 (13.0% of the set)**.
- New confidence dist (classified re-pass rows): <0.5 561 · 0.5–0.8 19,759 ·
  ≥0.8 9,287.
- **Sink domains within the re-pass set:** 4 of 5 shrank as intended —
  Algorithms 3,317→2,405 (−912), Materials-Joining 2,210→1,466 (−744), Power
  Systems 2,039→1,615 (−424), Semiconductor PV 1,626→871 (−755). **Grid
  Integration grew 1,848→2,142 (+294) — by design:** the diagnosis flagged it as
  an *under-assigned destination* (9/11 involvements were on the Sonnet side), and
  FIX1 routes "renewable-source→grid" papers into it from Power Systems.

## Stage C — Merge into v3 final (PASS)

`classification_v3_final.jsonl` — for each of the 70,298 papers: re-pass label if
in the set, else the v2 label unchanged; the 1,654 hygiene-unclassifiable kept
as-is.

Test (`v3_validation_report.json`): **PASS** — 70,298 rows, all unique, **0
duplicate ids, 0 schema violations** (every classified row's domain belongs to
its theme under v3).
- Changed from v2: **13,120**. Classified: **63,660**. Unclassifiable: **6,638**
  = 1,654 hygiene + 555 carried v2-unclassifiable + **4,429 new out_of_scope**.
- 66 invalid re-pass rows fell back to their v2 label (recorded).

**New v3 theme distribution (classified):**

| theme | papers | (v2 was) |
|---|---:|---:|
| Energy, Sustainability & Climate Change | 9,805 | 9,418 |
| Advanced Materials & Devices | 9,796 | 9,623 |
| Manufacturing & Industry 4.0 | 8,299 | 9,920 |
| Healthcare & MedTech | 7,192 | 7,376 |
| Smart & Sustainable Infrastructure | 7,174 | 6,944 |
| AI/ML, Supercomputing & Quantum Computing | 6,874 | 8,787 |
| Quantum Technologies & Semiconductor Technology | 5,144 | 6,404 |
| Social Sciences, Humanities & Management | 4,851 | 5,123 |
| Next-Gen Communication | 4,525 | 4,495 |

New domains adopted corpus-wide: **Thermal Systems, Engines & Energy Harvesting
826**; **Construction Materials & Concrete Technology 526**. (Manufacturing and
AI/ML shrink most, consistent with tightening Materials-Joining and Algorithms
and routing genuine out-of-scope papers away.)

**#unclassifiable breakdown (v3 full):** hygiene/non-research **1,654** · carried
v2-LLM-unclassifiable **555** · new **out_of_scope 4,429** → total **6,638**
(9.4% of corpus, up from 3.1% in v2). This large jump is itself a warning sign —
see §5.

## Stage D — Independent re-validation (PASS on test; PROVES a regression)

Fresh stratified 250-paper sample from v3 (seed 20260719, different from the
original 20260718; 86/85/79 across the <0.5 / 0.5–0.8 / ≥0.8 bands; 69 of 250
were re-classified). Each labeled independently by `claude-sonnet-4-5` with the
full v3 taxonomy, blind to the assigned label. 0 refusals, 2 Sonnet-unclassifiable
(excluded from denominators, not dropped silently).

Test (`goldset_v3_metrics.json`): counts reconcile (sample 250 = labels 250;
theme-comparable 246; domain-comparable 245).

### Before → after (v3 vs the v2 baseline)

| metric | v2 baseline | v3 (shipped) | Δ |
|---|---|---|---|
| **Theme agreement** | 86.2% | **79.7%** (196/246) | **−6.5** |
| **Domain agreement** | 70.5% | **58.8%** (144/245) | **−11.7** |

| band | theme v3 (Δ) | domain v3 (Δ) |
|---|---|---|
| <0.5 | 63.9% (−26.2) | **25.3% (−42.1)** |
| 0.5–0.8 | 82.4% (+6.4) | **67.9% (+9.2)** |
| ≥0.8 | 93.6% (+1.8) | 84.6% (−1.7) |

Domain agreement is **honestly worse overall**. The improvement is real but
localized to the 0.5–0.8 mid-band; the <0.5 band collapsed.

---

## §5 — Why it regressed (diagnosis, with evidence)

1. **The regression is 100% in the re-classified papers.** Splitting the fresh
   sample: carried (untouched) papers agree at **theme 86.6% / domain 70.4%**
   (≈ baseline); re-classified papers at **theme 61.2% / domain 27.3%**. By source
   model: carried Haiku labels **88.3% domain**, re-passed labels **49.5%**.

2. **Same-papers confirmation (no ambiguity).** On the *original* fixed 250 gold
   papers, scored against the *same* original Sonnet reference: carried papers
   82.6% → 82.6% (unchanged, sanity OK); the papers v3 changed went **57.8% →
   24.1% on domain** and **85.3% → 58.6% on theme**. The re-pass moved these
   labels *away* from the independent reference.

3. **Out_of_scope over-fired.** Haiku sent **4,429 (13%)** of the re-pass set to
   out_of_scope; the Sonnet judge marked only **2/250 (~1%)** of a comparable
   sample unclassifiable. Many out_of_scope calls are on papers that have a
   defensible home — this both creates mechanical disagreements and inflates the
   unclassifiable pile 3×.

4. **Hard papers, weaker labeler.** Even a full-prompt, full-abstract Haiku re-run
   of the changed papers agreed with Sonnet only **34.8% on domain** (vs 27.3% for
   the shipped compact re-pass, and vs 62.1% theme unchanged). So ~7.5 pts of the
   domain loss on that subset is a self-inflicted cost of my compact-prompt budget
   optimization, but **the majority is intrinsic**: on genuinely ambiguous papers,
   a single Haiku pass simply diverges from the stronger judge.

5. **A selective merge recovers the loss** (policy probe on the fixed sample vs
   the same reference):

| merge policy | theme | domain |
|---|---|---|
| v2 baseline | 86.9% | 70.5% |
| v3 full (shipped) | 61.6% | 48.5% |
| v3, revert out_of_scope→v2 | 82.7% | 64.1% |
| **v3, accept mid-band changes only** | 86.9% | **72.6%** |
| **v3, mid-band + no out_of_scope** | 87.8% | **72.6%** |

The mid-band-only policy is the only one that beats v2 (domain +2.1, theme +0.9),
though **+2.1 on n≈237 is within sampling noise** — call it parity-to-slightly-
positive, not a proven win.

### Regressions / caveats, stated plainly
- v3-full domain and theme agreement both dropped materially. This is the primary,
  as-specified result.
- The metric is an **LLM-vs-LLM agreement proxy, not human ground truth**. Some
  out_of_scope disagreements may be cases where v3 is actually right and the
  forced Sonnet domain is wrong — but the fresh, v3-aware Sonnet judge (which had
  the out_of_scope option and used it only twice) still shows the regression, so
  it is not merely a taxonomy-version artifact.
- Per-band n is small (~78–85); band figures carry real sampling error.

---

## §6 — Did the sink domains shrink? Yes (4 of 5), as designed

Corpus-wide (v3 full): Algorithms 3,317→2,406, Materials-Joining 2,210→1,468,
Power Systems 2,039→1,616, Semiconductor PV 1,626→875 all shrank; Grid Integration
1,848→2,143 grew intentionally (it was an under-assigned destination). So the
taxonomy did de-sink the junk-drawers — the problem is the *quality* of where the
moved papers landed, not that they failed to move.

## §7 — Recommendation (keep v2; get the gain via a targeted re-pass)

1. **Keep v2 (`classification_v2_final.jsonl`) as the production baseline.** Do not
   ingest `classification_v3_final.jsonl`.
2. **Adopt the v3 *taxonomy*** (`taxonomy-draft-v3.json`) — the fixes are sound and
   the mid-band improved with it.
3. For the re-pass, do ONE of:
   - **(preferred)** re-run the re-pass with the **Sonnet** labeler (stronger, and
     it self-selects out_of_scope far more conservatively), restricted to the
     0.5–0.8 mid-band, with a **strict out_of_scope gate** (require an explicit
     "no plausible theme" justification); then re-validate on a fresh sample. Est.
     Sonnet cost for ~20k mid-band papers ≈ $60–120 — needs its own budget.
   - **(cheap interim)** adopt the provided **conservative candidate**
     (`classification_v3_conservative_final.jsonl`: accept re-pass only for v2
     mid-band, non-out_of_scope → 7,189 changes, 0 new out_of_scope, 0 schema
     violations) **after** a fresh independent gold re-test confirms it beats v2.
4. Tighten the out_of_scope instruction before any re-run — it is currently too
   eager for Haiku.

## §8 — WHAT'S LEFT (explicitly NOT done here — for when the owner approves)

- **DB ingestion + Atlas index rebuild + application verification** — no DB writes
  were made; nothing was pushed to Mongo/Atlas or wired into the app.
- **Human gold adjudication** — turning the LLM-proxy disagreements into a real
  human-verified accuracy number (use the disagreement lists in the gold metrics).
- A budgeted **Sonnet / restricted re-pass** and its fresh re-validation (§7).

## §9 — Safety confirmations
- **No database writes.** All inputs read from local files; Mongo was never
  connected. Read-only by construction.
- **No git commits or pushes.** Working tree only; HEAD unchanged.
- **v2 baseline preserved:** `classification_v2_final.jsonl` untouched, plus
  backups `classification_v2_final.BASELINE-BACKUP.jsonl`,
  `taxonomy-draft-v3-baseline-backup.json/.md`,
  `work/goldset_metrics.BASELINE-BACKUP.json`.

## §10 — Artifact paths (all under `classification-pipeline/`)

**Taxonomy**
- `outputs/taxonomy-draft-v3.json` / `.md` — sharpened v3 taxonomy (8 fixes, 2 new
  domains, out_of_scope rule)
- `outputs/taxonomy-draft-v3-baseline-backup.json` / `.md` — v2 backup
- `outputs/work/stageA_taxonomy_check.json` — Stage A test (28/28 pass)

**Classifications**
- `outputs/classification_v3_final.jsonl` — full v3 merge (70,298) — **regresses;
  not recommended as-is**
- `outputs/classification_v3_conservative_final.jsonl` — conservative candidate
  (mid-band-only, no new out_of_scope) — **candidate, needs fresh validation**
- `outputs/classification_v2_final.jsonl` (+ `.BASELINE-BACKUP.jsonl`) — **the
  recommended production baseline**

**Re-pass + reports**
- `outputs/work/repass_haiku.jsonl` — 34,037 re-pass labels · `repass_cost.json`
- `outputs/work/stageB_repass_report.json` — Stage B test/report
- `outputs/v3_validation_report.json` · `outputs/v3_report.md` — Stage C
- `outputs/v3_conservative_stats.json` — conservative candidate stats

**Re-validation (Stage D)**
- `outputs/work/goldset_v3_sample.jsonl` · `goldset_v3_sonnet_labels.jsonl` ·
  `goldset_v3_cost.json`
- `outputs/goldset_v3_metrics.json` · `outputs/goldset_v3_report.md`
- `outputs/work/fullprompt_probe.jsonl` — full-prompt diagnostic

**Pipeline scripts:** `pipeline/r00_verify_models.py`, `r01_facts.py`,
`r02_build_taxonomy_v3.py`, `r03_test_stageA.py`, `r_common.py`,
`r04_repass_haiku.py`, `r05_stageB_report.py`, `r06_merge_v3.py`,
`r07_goldset_v3_sample.py`, `r08_goldset_v3_label.py`, `r09_goldset_v3_analyze.py`,
`r10_diagnose_stageD.py`, `r11_confirm_on_v2sample.py`, `r12_fullprompt_probe.py`,
`r13_policy_probe.py`, `r14_build_conservative.py`.
