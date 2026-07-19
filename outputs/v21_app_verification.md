# App verification — classification-v2.1 on LOCAL stack

**Date:** 2026-07-18  
**Path tested:** `https://localhost` (`nginx -> api-gateway -> services`)  
**Scope:** required core endpoints + container health after v2.1 ingest/rebuild

## Container health

All main app containers are up; healthchecks are green for core services.

- `mongodb`, `redis`, `api-gateway`, `search-api`, `backend`, `frontend`, `nginx`, `auth-service`, `chatbot`, `embedding`, `opensearch` -> healthy/running.
- `envoy` -> running.

## Explore taxonomy endpoints

Validated:

- `GET /search/api/v1/taxonomy/themes` -> **200**, themes: **9**, paper sum: **68,080**.
- `GET /search/api/v1/taxonomy/domains` -> **200**, domains: **77**.

Theme endpoint values match v2.1 DB distribution:

- AI/ML, Supercomputing & Quantum Computing 8,795
- Advanced Materials & Devices 9,605
- Energy, Sustainability & Climate Change 9,424
- Healthcare & MedTech 7,387
- Manufacturing & Industry 4.0 9,915
- Next-Gen Communication 4,501
- Quantum Technologies & Semiconductor Technology 6,399
- Smart & Sustainable Infrastructure 6,932
- Social Sciences, Humanities & Management 5,122

## Atlas/graph endpoints

Validated:

- `GET /api/kg/health` -> **200** with `graphsReady=true`, `exploreReady=true`, `atlasReady=true`, `atlasCount=66235`, `dataDir=mongodb:45d5192e51b3`.
- `GET /api/kg/atlas/dict` -> **200**, version `45d5192e51b3`, themes **10** (9 + Unclassified), non-empty domains **77**.
- `GET /api/kg/atlas/tree` -> **200**, version `45d5192e51b3`, pointCount **66,235**.
- `GET /api/kg/atlas/points?indices=0,1,2,3,4` -> **200**, sample point payload present.
- `GET /api/kg/atlas/tile/r` -> **200**, binary tile payload served.

## Status summary

- Core endpoint status codes: all required endpoints **200**.
- Counts from Explore + Atlas reflect v2.1 ingest and rebuilt atlas version.
- No classification regression observed in the required endpoint checks.

## Operational note

- Immediately after ingest, `/taxonomy/themes` briefly returned stale cached counts from the prior run. After local cache reset and `search-api` restart, counts aligned to v2.1 and remained correct.
