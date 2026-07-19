# Classification Pipeline

Working repo for **Research Ambit** (IIT Delhi) paper classification: taxonomy discovery scripts, Claude API labeling runs, validation reports, and the accepted label artifact.

**Live docs (GitHub Pages):** https://iitd-tech-ambit.github.io/classification-pipeline/

**Repo:** [IITD-Tech-Ambit/classification-pipeline](https://github.com/IITD-Tech-Ambit/classification-pipeline) · branch `main`

---

## Current status (honest)

| Item | Reality |
|---|---|
| **Recommended labels** | `outputs/classification_v2_2_candidate.jsonl` (v2.2 **accepted** after model-judged validation) |
| **Taxonomy** | Two-level only: **9 fixed thematic areas → domains** (80 domains in v2.2). **No subdomain / topic layer** in the final system |
| **How labeling ran** | **Claude API** — Haiku for bulk corpus pass; Sonnet for low-confidence escalation and later targeted corrections. **Not** a self-hosted-only / no-API production path |
| **Embeddings role** | Used early for **taxonomy discovery / clustering** (`BAAI/bge-base-en-v1.5`, plus optional Colab `bge-large`). **Not** used as a shortlist filter during final classification — the **full taxonomy** went into the prompt |
| **Validation** | Model-judged / audit-based (independent LLM re-label or pairwise adjudication). **No completed human gold-standard set** |
| **Local Mongo** | v2.2 was ingested into a **local** DB for app testing (`outputs/v22_ingest_report.md`). **Production deploy is a separate team decision** — this repo does not claim prod cutover |
| **v3 experiment** | Taxonomy sharpening + blanket Haiku re-pass was tried; reports recommend **not** shipping `classification_v3_final.jsonl` as-is (`outputs/REFINEMENT_REPORT.md`) |

---

## What this repo is

Python scripts under `pipeline/` that:

1. Sample / hygiene-gate Scopus papers from local Mongo (`researchmetadatascopus` in `research_ambit`)
2. Embed + cluster to **induce domains** under the 9 fixed themes
3. Classify papers with Anthropic Claude (Haiku → Sonnet escalation / targeted correction)
4. Write JSONL labels + markdown/JSON run reports under `outputs/`
5. Optionally ingest labels into **local** Mongo and rebuild atlas/KG artifacts for app testing

It is **not** an HPC cluster pipeline, and the GitHub Pages HTML once described a **proposed** self-hosted GPU ensemble that was **not** what produced the accepted labels.

---

## Taxonomy (final shape)

- **Fixed:** 9 human thematic areas (names and scope notes in `outputs/taxonomy-draft-v22.json` / `.md`)
- **Induced:** domains per theme (clustering + LLM naming / curation; then gap-fills in v2.2)
- **Not in final system:** subdomains, free-text topics, embedding-centroid shortlists at classify time

v2.2 taxonomy method note (from the file): *v2 baseline + audit-driven gap fills* (thermoelectric, optical metrology, implant bioelectronics, computer architecture) plus explicit out-of-scope routing and stronger tie-breaks → **9 themes / 80 domains**.

---

## How classification was actually done

### A. Taxonomy discovery (early)

- Hygiene gate → sample pools → embed with `BAAI/bge-base-en-v1.5` (`pipeline/s02_embed.py`; optional Colab notebook for `bge-large`)
- Per-theme clustering (`pipeline/s03_cluster.py` and later v2 variants)
- LLM naming / consolidation → draft taxonomy JSON/MD under `outputs/`

### B. Full-corpus v2 labels (overnight)

Documented in `outputs/OVERNIGHT_REPORT.md`:

- Corpus accounted for: **70,298** papers
- Eligible papers classified with **`claude-haiku-4-5`**, **full frozen taxonomy in a prompt-cached system prompt** (one paper per request)
- Low confidence / schema issues escalated to **`claude-sonnet-4-5`**
- Hygiene-filtered non-research items marked unclassifiable without API
- Deliverable at that stage: `outputs/classification_v2_final.jsonl`

### C. Proxy audits, then targeted corrections

- **LLM-proxy “goldset”:** independent Sonnet re-label vs existing labels on a stratified sample — agreement rates are **proxy**, not human accuracy (`outputs/goldset_accuracy_report.md`)
- **v2.1:** targeted Sonnet correction queue → `classification_v2_1_candidate.jsonl` (`outputs/v21_run_report.md`)
- **v2.2 (accepted):** taxonomy gap-fill + targeted Sonnet re-score of a high-yield queue; blind Opus adjudication favored v2.2 → **`classification_v2_2_candidate.jsonl`** (`outputs/v22_run_report.md`, `outputs/work/v22_decision.json`)

Label row fields (v2.2): `id`, `thematic_area`, `domain`, `confidence`, `unclassifiable`, `reason`, `source_model`, `escalated`.

---

## Key artifact paths

| Path | What it is |
|---|---|
| `outputs/classification_v2_2_candidate.jsonl` | **Accepted / recommended** full-corpus labels |
| `outputs/taxonomy-draft-v22.json` (+ `.md`) | Taxonomy used for v2.2 |
| `outputs/v22_run_report.md` | v2.2 acceptance, spend, validation summary |
| `outputs/v22_ingest_report.md` | Local Mongo ingest of v2.2 (not a prod deploy claim) |
| `outputs/v22_validation_random_subset.md`, `outputs/audit_50_random_v22.md` | Model-judged audits |
| `outputs/classification_v2_final.jsonl` | Overnight Haiku+Sonnet baseline before v2.1/v2.2 patches |
| `outputs/OVERNIGHT_REPORT.md` | Overnight v2 run narrative |
| `outputs/goldset_accuracy_report.md` | LLM-proxy agreement (not human gold) |
| `outputs/REFINEMENT_REPORT.md` | Why v3 blanket re-pass was not shipped |
| `outputs/safe_baseline/` | Frozen baselines used for rollback-safe correction runs |
| `pipeline/` | Runnable scripts (discovery, classify, ingest, v21/v22 correction) |
| `colab/embed_bge_large.ipynb` | Optional GPU embedding helper |
| `docs/index.html` | Pages site — **as-executed** pipeline (see historical note there) |

---

## Repo layout

```
classification-pipeline/
  README.md
  docs/index.html          # GitHub Pages
  .github/workflows/pages.yml
  pipeline/                # Python steps
  colab/                   # optional embedding notebook
  outputs/                 # labels, taxonomies, reports (large intermediates gitignored)
```

---

## Setup (venv)

There is no pinned `requirements.txt` in-repo today. Recreate a working environment from what the scripts import:

```bash
cd classification-pipeline
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install anthropic python-dotenv pymongo numpy torch sentence-transformers scikit-learn
```

Secrets (do **not** commit):

- Put `ANTHROPIC_API_KEY=...` in a local `.env` (gitignored).
- Mongo access for read/ingest scripts is configured in `pipeline/common.py` against a local `research_ambit` database. Do not commit credentials or `.env`.

Example (classification library entrypoints used in the overnight run):

```bash
cd pipeline
python s15_verify_env.py
# then the stage runners documented in OVERNIGHT_REPORT.md / v21 / v22 scripts
```

---

## What is NOT in the repo

Gitignored / kept local (see `.gitignore`):

- `.env` and secrets
- Embedding matrices (`outputs/work/*.npz`, `*.npy`, `emb/`, etc.)
- Large intermediate API dumps such as `haiku_full.jsonl`, `sonnet_escalation.jsonl`, `papers_source.jsonl`
- Pre-ingest Mongo dump dirs (`outputs/db_backup_pre_*_ingest/`)

You can regenerate many intermediates with the scripts + local Mongo + API key; the **accepted labels and reports** that matter for handoff are the tracked `outputs/*.jsonl` / `*.md` listed above.

---

## Honesty caveats (read before quoting numbers)

1. **Do not quote “human gold accuracy.”** Human labeling of a gold set was planned; what exists are **LLM-proxy audits** and random-subset adjudications.
2. **Do not describe production labeling as self-hosted / embedding-shortlist / multi-voter GPU funnel.** That was an early architecture proposal; Pages previously advertised it — the accepted path was **Claude API + full taxonomy in prompt**.
3. **Agreement % in goldset reports are model-vs-model**, not ground truth.
4. **Local ingest ≠ production rollout.**
5. **Corpus size in run reports is 70,298** (Mongo count at overnight/v2.2 time). Older planning docs used ~69.7k — prefer the run reports.

---

## Pages deploy

Pushing to `main` deploys `docs/` via `.github/workflows/pages.yml`.
