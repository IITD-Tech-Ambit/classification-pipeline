# INGEST REPORT — classification-v2.1 candidate -> LOCAL database

**Date:** 2026-07-18  
**Outcome:** ✅ SUCCESS  
**Git commits/pushes:** none  
**Production writes:** none

## 1) Artifact verification (pre-ingest)

Verified:

- `classification-pipeline/outputs/v21_run_report.md` exists.
- `classification-pipeline/outputs/classification_v2_1_candidate.jsonl` exists, **70,298 rows** (unique ids: 70,298).
- `classification-pipeline/outputs/work/sonnet_v21_cost.json` exists.

Candidate stats:

- Classified: **68,080**
- Unclassifiable: **2,218**
- Distinct themes/domains: **9 / 77**

## 2) LOCAL-only target + backup

Write target used:

- Mongo endpoint: **`10.184.47.156:27017`**
- Mongo version: **7.0.37**
- Topology gate: **standalone local target only** (write aborted if non-local/non-standalone)

Pre-ingest backup created at:

- `classification-pipeline/outputs/db_backup_pre_v21_ingest/`
- Full `research_ambit` dump copied from local `mongodb` container.
- Size: ~**431 MB**.
- Restore instructions: `classification-pipeline/outputs/db_backup_pre_v21_ingest/RESTORE_INSTRUCTIONS.md`
- Pre-backup counts snapshot: `classification-pipeline/outputs/db_backup_pre_v21_ingest/pre_backup_counts.json`

## 3) v2.1 ingest applied (idempotent overwrite style)

Applied candidate labels into `researchmetadatascopus.classification` using bulk `$set` overwrite per paper id:

- matched docs: **70,298**
- modified docs: **70,298**
- missing taxonomy node rows: **0**
- schema shape preserved:
  - classified rows: `thematic_area_id`, `domain_id`, `subdomain_id=null`, `topics=[]`, `unclassifiable=false`
  - unclassifiable rows: all three facet ids null, `topics=[]`, `unclassifiable=true`
- `iitd_authors` was not touched.

Post-ingest counts:

- papers total: **70,298**
- with theme/domain ids: **68,080**
- unclassifiable: **2,218**
- subdomain ids set: **0**
- taxonomy nodes: themes **9**, domains **77**, subdomains **0**

## 4) Derived rebuild run

Executed rebuild flow on local stack:

1. Rollup rebuild (`taxonomyfacetcounts`, `taxonomyfacetmembers`, node stats):
   - facetcounts rows: **3,351**
   - facetmembers rows: **3,351**
   - domain-level rows: **77**
   - subdomain rows: **0**
2. Atlas source regenerated from current point cloud, relabeled by v2.1:
   - source points: **66,235**
   - relabeled classified points: **64,566**
   - unclassified points in atlas cloud: **1,669**
3. Atlas tiles/points published:
   - active atlas version: **`45d5192e51b3`**
   - atlas tiles: **78**
   - atlas points: **66,235**
4. KG rebuild under active atlas version:
   - `kg_faculty_graphs`: **968**
   - `kg_explore`: **86 term docs + 86 detail docs**
   - `kg_indices`: **3**

## 5) DB validation against v2.1 candidate

Validation artifact: `classification-pipeline/outputs/work/v21_ingest_validation.json`

All checks passed:

- total rows DB == file: ✅
- classified/unclassifiable DB == file: ✅
- thematic-area distribution DB == file: ✅
- thematic-area distribution facet rollups == file: ✅
- themes/domains counts: 9/77 ✅
- subdomain usage remains zero ✅

Theme counts matched exactly:

- Manufacturing & Industry 4.0: 9,915
- Advanced Materials & Devices: 9,605
- Energy, Sustainability & Climate Change: 9,424
- AI/ML, Supercomputing & Quantum Computing: 8,795
- Healthcare & MedTech: 7,387
- Smart & Sustainable Infrastructure: 6,932
- Quantum Technologies & Semiconductor Technology: 6,399
- Social Sciences, Humanities & Management: 5,122
- Next-Gen Communication: 4,501

## Caveats / notes

- 3D atlas coordinates were **reused** from the prior point cloud (labels/colors/metadata rebuilt to v2.1; spatial embedding itself not recomputed).
- `build_atlas_tiles.py` keeps only two latest atlas versions; one older version was GC'd during publish. Full DB backup remains available for rollback.
