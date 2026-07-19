# INGEST REPORT — classification-v2.2 candidate -> LOCAL database

**Date:** 2026-07-18
**Outcome:** ✅ SUCCESS
**Git commits/pushes:** none
**Production writes:** none

## LOCAL target + backup
- Pre-ingest backup: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\db_backup_pre_v22_ingest`
- Pre-backup counts: `{'papers': 70298, 'themes': 9, 'domains': 77, 'unclassifiable': 2218, 'with_theme': 68080, 'captured_at': '2026-07-18T17:39:00.940983+00:00', 'host': '10.184.47.156'}`

## Ingest
- Candidate: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\classification_v2_2_candidate.jsonl`
- Taxonomy: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\taxonomy-draft-v22.json`
- Stats: `{'classified': 67802, 'unclassifiable': 2496, 'missing_node': 0, 'docs_modified': 70298, 'themes': 9, 'domains': 80}`

## Atlas / KG
- Atlas source: `{'source_version': '45d5192e51b3', 'points': 66235, 'relabeled': 64296, 'unclassified': 1939, 'path': 'C:\\Users\\Prem\\OneDrive - IIT Delhi\\Desktop\\Research Ambit\\classification-pipeline\\outputs\\work\\atlas_papers_v22.json'}`
- KG: version=9029054b27d2; kg_faculty_graphs=967; kg_explore=178; kg_indices=3

## Validation
- Artifact: `C:\Users\Prem\OneDrive - IIT Delhi\Desktop\Research Ambit\classification-pipeline\outputs\work\v22_ingest_validation.json`
- counts_match: True
- all_themes_match: True
- themes/domains DB: 9 / 80
- classified/unclass: 67802 / 2496

### Theme counts
- Manufacturing & Industry 4.0: db=9862 file=9862
- Advanced Materials & Devices: db=9584 file=9584
- Energy, Sustainability & Climate Change: db=9453 file=9453
- AI/ML, Supercomputing & Quantum Computing: db=8570 file=8570
- Healthcare & MedTech: db=7388 file=7388
- Smart & Sustainable Infrastructure: db=6916 file=6916
- Quantum Technologies & Semiconductor Technology: db=6409 file=6409
- Social Sciences, Humanities & Management: db=5126 file=5126
- Next-Gen Communication: db=4494 file=4494