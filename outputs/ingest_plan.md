# Ingest Plan — classification-v2 → LOCAL Mongo

**Author:** automated ingest agent · **Date:** 2026-07-18 · **Mode:** SAFE / REVERSIBLE / LOCAL-ONLY

## 0. Target database (CONFIRMED LOCAL)

- A native **Windows MongoDB Server 8.0** shadows `127.0.0.1:27017` (found on PATH: `C:/Program Files/MongoDB/Server/8.0/bin`). This is why `classification-pipeline/pipeline/common.py` falls back to the machine LAN IP.
- The **Docker** container `mongodb` (image `mongo:7`, `Up ... (healthy)`) publishes `0.0.0.0:27017->27017`.
- Reaching Docker from the host uses the LAN IP `socket.gethostbyname(socket.gethostname())` → **`10.184.47.156:27017`**. Verified: `buildInfo.version = 7.0.37`, **standalone** (not a replica set / not Atlas). This is the local Docker container, NOT production.
- For the **backup**, `mongodump` is run *inside* the `mongodb` container against its own `localhost:27017` — unambiguously the local Docker DB.
- All writes print & assert the target host before running.

## 1. How the app stores & consumes classification (Stage 0 findings)

There are **two independent systems**, both in the local Mongo `research_ambit` DB:

### System A — Taxonomy browse (SEO-Backend-iitd `search-api`, gRPC)
Powers **Explore** (papers/faculty filtered by theme/domain).
- `researchmetadatascopus.classification` embedded doc per paper:
  `{ thematic_area_id → ThematicArea, domain_id → Domain, subdomain_id → Subdomain, topics[], classified_at }`.
- `researchmetadatascopus.iitd_authors[]` — resolved IITD authorship (kerberos/faculty_ref/department_ref). Used by rollup for faculty counts.
- Node collections: `thematicareas` (9), `domains` (35 old), `subdomains` (177 old).
- Rollup collections (rebuilt from scratch each run): `taxonomyfacetcounts`, `taxonomyfacetmembers` (9,254 rows each).
- Built by `scripts/taxonomy/ingest.js` then `scripts/taxonomy/rollup.js`. Read paths query facet rows by `{thematic_area_id, domain_id, subdomain_id, department_id}` and always use `$ne: null` (a null level = "not part of this config").

### System B — Knowledge-Graph / Atlas (research-ambit-main `backend`)
Powers **Directory/Atlas** (3D graph), the Topic Explorer, and per-faculty KGs. Versioned by an `atlas_meta` `active` pointer.
- `atlas_points` (66,235): one row/paper — `i, id, title, theme, domain, subdomain, topic, department, citations, x, y, z`.
- `atlas_tiles` (78): binary octree LOD tiles; each encodes `themeId`=index into `dict.themes`, `domainId`=index into `dict.domains`.
- `atlas_meta`: `{tree, dict:{themes[], domains[], themeAnchors[], domainAnchors[]}}` + `active` pointer.
- `kg_faculty_graphs` (969), `kg_explore` (101,694 term/detail docs), `kg_indices` (faculty-search-index, faculty-atlas-indices, department-atlas-indices).
- Built by `build_kg.py` → `build_atlas_tiles.py` → `migrate_kg_to_mongo.py`.

**IMPORTANT:** `build_kg.py` reads its class labels from `classification/Copy of Classified_DataSheet.xlsx` and imports `build_atlas.py` — **both are ABSENT from this checkout**, so `build_kg.py` cannot run here. However `build_atlas_tiles.py` only needs an `atlas_papers.json` (papers with coords + labels) + `MONGO_URI`, so the atlas can be faithfully rebuilt by reusing the existing point coordinates and swapping in v2 labels (see Stage 3).

Note: the faculty **Directory** routes (`/api/directory/*`) list faculty by *department* and are independent of classification — unaffected by this ingest.

## 2. Taxonomy chosen (VERIFIED)

Distinct `(theme, domain)` pairs in `classification_v2_final.jsonl`: **9 themes, 77 domains, 77 pairs** (68,090 classified + 2,208 unclassifiable = 70,298 rows). Verified coverage of jsonl pairs by each candidate taxonomy:

| taxonomy file | pairs | jsonl pairs missing |
|---|---|---|
| taxonomy-draft-v2-prefix.json | 76 | **1** (rejected) |
| taxonomy-draft-v2.json | 77 | 0 (exact) |
| **taxonomy-draft-v3-baseline-backup.json** | **77** | **0 (exact)** ✅ chosen |
| taxonomy-draft-v3.json | 79 | 0 (2 extra, rejected) |

**Chosen: `taxonomy-draft-v3-baseline-backup.json`** — one of the two files the task names as canonical, and verified to match the jsonl pairs exactly (77↔77, no missing, no extras). The 9 theme names are byte-identical to those already in the DB.

## 3. Schema-mapping decision: 2-level v2 → old 3-level schema

**Decision:** map v2 `thematic_area` → `classification.thematic_area_id`, v2 `domain` → `classification.domain_id`, and **set `classification.subdomain_id = null`** for every paper. Clear the `subdomains` collection.

**Why (least-disruptive):**
- The read paths already treat a null facet level as "not part of this configuration" (every query filters `... $ne: null`). Null subdomain requires **zero code changes** and Explore browse by theme and by domain keeps working.
- The rollup's subdomain-bearing masks (`(D,S)`, `(T,D,S)`) simply emit no rows (no data, no stale rows); `Domain.stats.subdomain_count` → 0.
- Collapsing domains into fake subdomains, or inventing a placeholder subdomain, would pollute the browse UI with meaningless nodes — strictly more disruptive. So we leave the level empty.

**Themes:** upserted by name (preserves existing `_id`s, incl. the 9 identical themes). **Domains:** the 35 old domain docs are replaced by the 77 v2 domains (backed up first). **Unclassifiable (2,208):** `thematic_area_id=null, domain_id=null, subdomain_id=null` → app-native "unclassified" (excluded from all browse configs). A `classification.unclassifiable=true` marker is also stored for lineage.

## 4. Execution stages (each tested; revert-on-failure)

1. **Backup** — `mongodump` (in-container) of `researchmetadatascopus, thematicareas, domains, subdomains, taxonomyfacetcounts, taxonomyfacetmembers, atlas_points, atlas_tiles, atlas_meta, kg_faculty_graphs, kg_explore, kg_indices` → `outputs/db_backup_pre_v2_ingest/`. Verify non-empty; document `mongorestore`.
2. **Ingest (System A)** — Python, idempotent: rebuild nodes (themes upsert / domains+subdomains rebuild) using the app's exact slugify; set `classification` on all 70,298 papers; **preserve `iitd_authors`**. Test: re-read 20, counts (68,090 classified + 2,208 unclassifiable), no double labels, all values in taxonomy.
3. **Rollup (System A)** — Python port of `rollup.js`/`rollupAggregations.js` (verbatim MASKS/pipelines): rebuild `taxonomyfacetcounts` + `taxonomyfacetmembers` + node `stats`. Test: theme-level paper counts match the v2 distribution (Manufacturing ~9,920, Advanced Materials ~9,623, Energy ~9,418, …).
4. **Atlas (System B)** — build `atlas_papers.json` from existing `atlas_points` coords joined to v2 labels (subdomain/topic emptied); run the app's own `build_atlas_tiles.py` (new version → rebuilds `atlas_tiles`+`atlas_points`+`atlas_meta`, atomic pointer flip, keeps prior version for rollback); then Python-rebuild `kg_faculty_graphs` / `kg_explore` / `kg_indices` under the new version from Mongo v2 + `iitd_authors` + faculty/departments. Coordinates are reused (the 3D layout embedding is not recomputed — `build_atlas.py`/source Excel are absent); labels, colors, legend, anchors, filtering and the explorer all reflect v2. Test: node/edge/point counts non-zero; dict = 9 themes/77 domains.
5. **App verify** — `docker compose up -d` (images pre-built); flush redis; curl Explore/Atlas endpoints; note Chatbot external deps. Evidence → `app_verification.md`.

**Rollback:** every touched collection is in the mongodump; `mongorestore --drop` reverts exactly. The atlas additionally keeps the previous version for a pointer-flip rollback.
