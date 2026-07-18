# INGEST REPORT — classification-v2 → LOCAL database

**Date:** 2026-07-18 · **Outcome:** ✅ SUCCESS · **Reverts:** none needed · **Git commits/pushes:** none.

## What was ingested
The validated winner **classification-v2** (`classification-pipeline/outputs/classification_v2_final.jsonl`, 70,298 rows) — **68,090 classified** (theme + domain) and **2,208 unclassifiable**. v3 files were **not** used. Every jsonl id was matched to an existing paper in `researchmetadatascopus` (70,298 / 70,298).

## Where it was written (LOCAL only)
- **Host/port written to:** `10.184.47.156:27017` — the machine's own LAN IP, which is how the host reaches the **Docker `mongodb` container** (a native Windows MongoDB Server 8.0 shadows `127.0.0.1:27017`, so localhost is deliberately avoided). Confirmed **standalone**, Mongo **7.0.37** (the `mongo:7` container), private/loopback host — every write script printed and asserted this before running and refused to run against anything non-local/non-standalone. **No production/remote DB was ever contacted.**
- Database `research_ambit`. Collections changed:
  - `researchmetadatascopus.classification` — set on all 70,298 papers. `iitd_authors` left **untouched**.
  - `thematicareas` (9, upserted by name — stable _ids), `domains` (35 → **77**, stale removed), `subdomains` (177 → **0**, cleared).
  - `taxonomyfacetcounts` / `taxonomyfacetmembers` — rebuilt (9,254 → **3,339** rows each; fewer because there are no subdomain combinations now).
  - Atlas/KG (new version `8a8f9abde489`): `atlas_tiles`, `atlas_points`, `atlas_meta`, `kg_faculty_graphs` (968), `kg_explore` (86 terms + 86 details), `kg_indices` (3).

## Schema-mapping decision: v2 2-level → old 3-level
The old schema was Theme → Domain → **Subdomain** → Papers. v2 has only Theme → Domain. **Decision: set `classification.subdomain_id = null` for every paper and clear the `subdomains` collection.**

Why (least-disruptive): the app's read paths already treat a null facet level as "not part of this configuration" (every taxonomy query filters `… $ne: null`), so browse-by-theme and browse-by-domain keep working with **zero code changes**; the subdomain-bearing rollup masks simply emit no rows (no stale/orphan data); `Domain.stats.subdomain_count` → 0. Inventing placeholder subdomains would have polluted the UI — strictly worse. The 9 v2 theme names are byte-identical to those already in the DB, so theme `_id`s were preserved. **Unclassifiable (2,208):** `thematic_area_id/domain_id/subdomain_id = null` (the app-native "unclassified" — excluded from all browse configs) plus a `classification.unclassifiable:true` lineage marker.

**Taxonomy used:** `taxonomy-draft-v3-baseline-backup.json` — chosen after verifying it contains **exactly** the jsonl's 77 (theme,domain) pairs (0 missing, 0 extra). `taxonomy-draft-v2-prefix.json` was rejected (missing 1 pair: "Energy Storage Materials"); `taxonomy-draft-v3.json` rejected (2 extra domains).

## Stage-by-stage test results
| Stage | Result | Key numbers |
|---|---|---|
| 0 Investigate + verify taxonomy | ✅ | taxonomy match verified (77↔77); 2 systems mapped |
| 1 Backup | ✅ | full `mongodump`, 20 collections, **342 MB**; `researchmetadatascopus.bson` 185 MB; restore documented |
| 2 Ingest | ✅ PASS | 68,090 classified + 2,208 unclassifiable = 70,298 touched; subdomain_id set on 0; per-theme distribution matches jsonl exactly; sample-20 all correct; **iitd_authors preserved (66,235)**; no orphan refs; 9 themes / 77 domains |
| 3 Rollup + Atlas | ✅ PASS | facet theme counts match jsonl (Manufacturing 9,920 …); 77 domain facet rows; 0 subdomain rows; 3,339 facet + 3,339 member rows; atlas rebuilt (66,235 points, 78 tiles, dict 9+Unclassified/77 domains); prior atlas version retained |
| 4 App verify | ✅ PASS | Explore ✅, Atlas ✅, Chatbot up (external OAuth gate) ⚠️; 12/12 containers healthy |

Artifacts: `outputs/work/stage2_test.json`, `outputs/ingest_verification.json`, `outputs/app_verification.md`.

## App verification (evidence in `app_verification.md`)
Through `nginx → api-gateway → services` (the real browser path):
- **Explore** ✅ — `/search/api/v1/taxonomy/themes` returns 9 v2 themes with correct counts; `/domains` returns 77; theme→domain filtering, `/counts`, and `/faculty` (kerberos lists, paginated) all correct.
- **Directory/Atlas** ✅ — `/api/kg/health` `atlasReady:true dataDir mongodb:8a8f9abde489`; atlas dict/tree/points/tiles serve v2; full atlas payload 200 (23.7 MB); per-faculty graphs show v2 domains (no subdomain/topic).
- **Chatbot** ⚠️ — container healthy, but `/chat-api/*` returns **401** (requires **IITD OAuth**, and it calls third-party **xAI/Grok**). These are **external** dependencies, not a classification problem.

## Atlas honesty note
The 3D atlas **point coordinates were reused** from the prior build; a fresh spatial embedding could **not** be recomputed because `build_kg.py` / `build_atlas.py` and the source `Copy of Classified_DataSheet.xlsx` are **absent from this checkout**. Everything else (per-point v2 theme/domain, colors, legend `dict`, anchors, tiles, topic-explorer, per-faculty graphs, indices) was rebuilt from v2 using the app's own `build_atlas_tiles.py`, so it is internally consistent. Papers keep their previous positions with current v2 labels/colors; the ~4k papers newly classified by v2 (not in the prior atlas) are not in the 3D cloud.

## Safety / reversibility confirmation
- **LOCAL DB only** — wrote to `10.184.47.156:27017` (Docker `mongodb`, standalone Mongo 7.0.37). **Production untouched.**
- **Backup taken** — `classification-pipeline/outputs/db_backup_pre_v2_ingest/` (full pre-ingest dump). **Restore command** (see `db_backup_pre_v2_ingest/RESTORE_INSTRUCTIONS.md`):
  ```bash
  docker cp "./db_backup_pre_v2_ingest/research_ambit" mongodb:/tmp/restore_research_ambit
  docker exec mongodb mongorestore \
    --uri="mongodb://admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4@localhost:27017/?authSource=admin" \
    --drop --nsInclude='research_ambit.*' /tmp/restore_research_ambit
  ```
  Atlas-only rollback: flip `atlas_meta.active` back to `764fb17329f7`.
- **No git commits/pushes** were made.
- **No revert was required** — every stage passed.

## What's LEFT for the owner (not done here — his team's call)
1. **Human gold adjudication** of a labeled sample to certify accuracy (goldset scaffolding already exists under `outputs/`).
2. **Optional budgeted targeted Sonnet mid-band re-pass** — re-label the medium-confidence band with Claude Sonnet to lift domain accuracy. Not run here (cost/budget decision). Would regenerate `classification_v2_final.jsonl`, after which re-run `pipeline/i01_ingest_v2.py` → `i03_rollup.py` → `i04`→`build_atlas_tiles.py`→`i05` (all idempotent).
3. **Pushing to production** — **NOT done.** This ingest is LOCAL-only; promoting to prod (and, ideally, a true atlas rebuild via `build_kg.py`+`build_atlas.py` with the source Excel to recompute the 3D layout) is the team's decision.

## Artifact paths
- Plan: `classification-pipeline/outputs/ingest_plan.md`
- Backup + restore: `classification-pipeline/outputs/db_backup_pre_v2_ingest/` (+ `RESTORE_INSTRUCTIONS.md`)
- Stage 2 test: `classification-pipeline/outputs/work/stage2_test.json`
- Stage 3 verification: `classification-pipeline/outputs/ingest_verification.json`
- App verification: `classification-pipeline/outputs/app_verification.md`
- Atlas source: `classification-pipeline/outputs/work/atlas_papers_v2.json`
- Scripts: `classification-pipeline/pipeline/i00_db_facts.py`, `i01_ingest_v2.py`, `i02_test_ingest.py`, `i03_rollup.py`, `i04_build_atlas_source.py`, `i05_rebuild_kg.py`, `i06_verify_stage3.py`
- This report: `classification-pipeline/outputs/INGEST_REPORT.md`
