# App verification — classification-v2 live in the LOCAL stack

**Date:** 2026-07-18 · **Stack:** `docker compose -f docker-compose.yml -f docker-compose.override.yml up -d` · all 12 containers `running (healthy)`. Requests below go through the public entrypoint `nginx` (`https://localhost`, self-signed → `curl -sk`), i.e. the same path the browser uses: `nginx → api-gateway → (Envoy/gRPC) → services`.

Active atlas version after ingest: **`8a8f9abde489`** (previous `764fb17329f7` retained for rollback).

## Explore — paper/faculty browse by theme/domain  ✅ PASS
Served by `search-api` (SEO-Backend-iitd) from `researchmetadatascopus.classification` + `taxonomyfacetcounts/members`.

- `GET /search/api/v1/taxonomy/themes` → **9 v2 themes**, paper_counts exactly matching the v2 distribution:
  Manufacturing 9,920 · Advanced Materials 9,623 · Energy 9,418 · AI/ML 8,787 · Healthcare 7,376 · Smart Infra 6,944 · Quantum Tech 6,404 · Social Sciences 5,123 · Next-Gen Comm 4,495. (`took_ms:5`)
- `GET /search/api/v1/taxonomy/domains` → **77 v2 domains** with `paper_count`, `faculty_count`, `subdomain_count:0`.
- `GET /search/api/v1/taxonomy/domains?theme=ai-ml-supercomputing-and-quantum-computing` → 5 domains nested under AI/ML (Algorithms 3,317; CFD 2,000; Control Systems 1,116; ML & Neural Networks 1,753; NLP & IR 601) → theme→domain filtering correct.
- `GET /search/api/v1/taxonomy/counts?theme=…ai-ml…&domain=algorithms-and-computational-complexity` → `{paper_count:3317, faculty_count:262}`.
- `GET /search/api/v1/taxonomy/faculty?theme=…&domain=…&page=1&per_page=5` → `kerberos_list:[bkpanigrahi,ravi1,arpankar,gargsahil,joshi]`, `faculty_total:262`, paginated (53 pages). Cards resolve via the directory API by kerberos.

## Directory / Atlas — the 3D knowledge graph  ✅ PASS
Served by `backend` (research-ambit-main) from the versioned `atlas_*` + `kg_*` collections.

- `GET /api/kg/health` → `{graphsReady:true, exploreReady:true, atlasReady:true, atlasCount:66235, dataDir:"mongodb:8a8f9abde489", redisConnected:true}`.
- `GET /api/kg/atlas/dict` → themes = 9 v2 themes + `Unclassified`; domains = 77 v2 domains (+ `""` for unclassified points).
- `GET /api/kg/atlas/tree` → version `8a8f9abde489`, `pointCount:66235`, octree bbox/nodes.
- `GET /api/kg/atlas` (full payload) → HTTP 200, 23.7 MB JSON. `GET /api/kg/atlas/tile/r` → HTTP 200, 45 KB binary tile.
- `GET /api/kg/atlas/points?indices=0,1,2` → themes reflect v2 (`AI/ML…`, `Unclassified`, `Social Sciences…`).
- `GET /api/kg/explore/terms?limit=5` → v2 **domain**/theme terms (Algorithms 3,206; Materials/Joining 2,525; Power Systems 2,409 …).
- `GET /api/kg/faculty` → 968 faculty; e.g. Prof Bhim Singh — 2,726 papers, 2,769 nodes, 8,178 edges.
- `GET /api/kg/faculty/69c90d6f421da07d524c7bbc/knowledge-graph` → 2,769 nodes / 8,178 edges; node types `{paper:2726, domain:33, theme:9, faculty:1}` — v2 domains, **no** subdomain/topic nodes (v2 is 2-level).

**Atlas caveat (honest):** the 3D **point coordinates were reused** from the prior build and **not recomputed** — `build_kg.py`/`build_atlas.py` and the source Excel are absent from this checkout, so a fresh spatial embedding was impossible. Labels, colors, legend (`dict`), anchors, per-point theme/domain, filtering, search, the topic-explorer, per-faculty graphs and indices were all rebuilt from v2 via the app's own `build_atlas_tiles.py` (tiles↔dict↔points are internally consistent). Net effect: papers keep their previous positions; their v2 theme/domain labels & colors are current. The ~4k papers newly classified by v2 that were not in the prior atlas are not in the 3D cloud (no coordinates).

## Chatbot  ⚠️ UP, but auth-gated by external IITD OAuth (not a classification issue)
- Container `chatbot` = `healthy` (compose healthcheck on `localhost:3003/health` passes).
- Through the gateway, `GET /chat-api/health` and `/chat-api/api/v1/health` → **HTTP 401** (IITD OAuth required). The chatbot also calls third-party xAI/Grok. These externals need campus OAuth/network and are outside this local ingest's scope; the service itself is running. This is explicitly noted in the task as NOT a classification failure.

## Unaffected
- `GET /api/directory?limit=1` → HTTP 200 (faculty directory is department-based, independent of classification).
- `GET /` (frontend) → HTTP 200.

## Summary
Explore ✅ · Directory/Atlas ✅ (coords reused, labels/graph v2) · Chatbot service up (external OAuth gate) ⚠️. No classification-related failures.
