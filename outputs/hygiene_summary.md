# Hygiene Gate Summary (classification-v2, Step 2 / Task A)

- Corpus: `researchmetadatascopus`
- Total papers processed: **70298**
- Per-paper flags: `outputs/work/hygiene_flags.jsonl`
- Thresholds: MIN_ABSTRACT_LEN=100 chars, MIN_TITLE_LEN=60 chars

## Status counts

| Status | Count | % | Fate |
|---|---:|---:|---|
| `ok` | 67023 | 95.34% | embed + classify |
| `title_only` | 1621 | 2.31% | classify (theme-level) |
| `unclassifiable` | 1654 | 2.35% | EXCLUDED |
| **proceed to embedding** | **68644** | 97.65% | ok + title_only |
| **filtered out** | **1654** | 2.35% | unclassifiable |

## Unclassifiable reason breakdown

| Reason | Count |
|---|---:|
| `no_abstract_short_title` | 1025 |
| `junk_pattern:preface` | 283 |
| `junk_pattern:editorial` | 124 |
| `junk_pattern:erratum` | 118 |
| `junk_pattern:corrigendum` | 54 |
| `junk_pattern:foreword` | 22 |
| `junk_pattern:retraction` | 17 |
| `junk_pattern:book_review` | 7 |
| `junk_pattern:retracted` | 4 |

## Notes / surprises

- Papers with an empty title: 0
- Duplicate `_id` values encountered: 0
