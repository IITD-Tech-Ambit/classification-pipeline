"""STAGE 2 TEST: validate the Haiku full-pass output.

Asserts:
  - coverage: every eligible id (68,644) has exactly one row (report missing/dupes)
  - schema violations counted (target 0)
Reports: theme distribution, domain distribution, confidence histogram,
#unclassifiable, mean confidence; degeneracy sanity check.
Writes outputs/work/stage2_haiku_report.json. Exit code 1 if coverage incomplete
or duplicates found.
"""
import json
import sys
from collections import Counter

from common import WORK
from s15_classify_lib import load_taxonomy

SOURCE = WORK / "papers_source.jsonl"
HAIKU_OUT = WORK / "haiku_full.jsonl"


def eligible_ids():
    ids = []
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                ids.append(json.loads(line)["id"])
    return set(ids)


def main():
    themes, theme_to_domains = load_taxonomy()
    valid_pairs = {(t, d) for t, doms in theme_to_domains.items() for d in doms}

    want = eligible_ids()
    rows = {}
    dupes = []
    with open(HAIKU_OUT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["id"] in rows:
                dupes.append(r["id"])
            rows[r["id"]] = r

    covered = want & set(rows)
    missing = want - set(rows)
    extra = set(rows) - want

    n = len(rows)
    schema_viol = [r["id"] for r in rows.values() if not r["schema_valid"]]
    unclass = [r for r in rows.values() if r.get("unclassifiable")]
    # domain-belongs-to-theme cross-check (independent of schema_valid flag)
    bad_pair = []
    for r in rows.values():
        if r["schema_valid"] and not r.get("unclassifiable"):
            if (r["thematic_area"], r["domain"]) not in valid_pairs:
                bad_pair.append(r["id"])

    theme_dist = Counter(r["thematic_area"] for r in rows.values()
                         if not r.get("unclassifiable") and r["schema_valid"])
    domain_dist = Counter(r["domain"] for r in rows.values()
                          if not r.get("unclassifiable") and r["schema_valid"])
    confs = [r["confidence"] for r in rows.values() if r["confidence"] is not None]
    mean_conf = round(sum(confs) / len(confs), 4) if confs else None

    bins = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001]
    labels = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-0.95",
              "0.95-1.0"]
    hist = dict.fromkeys(labels, 0)
    for c in confs:
        for i in range(len(labels)):
            if bins[i] <= c < bins[i + 1]:
                hist[labels[i]] += 1
                break

    # degeneracy: no single theme should hold >70% of classified papers
    top_share = (max(theme_dist.values()) / sum(theme_dist.values())
                 if theme_dist else 1.0)
    degenerate = top_share > 0.70

    coverage_ok = (len(missing) == 0 and len(dupes) == 0 and len(extra) == 0)
    passed = coverage_ok and not degenerate

    report = {
        "pass": passed,
        "coverage": {
            "eligible": len(want),
            "rows": n,
            "covered": len(covered),
            "missing_count": len(missing),
            "duplicate_count": len(dupes),
            "extra_count": len(extra),
            "missing_sample": sorted(missing)[:20],
            "duplicate_sample": dupes[:20],
        },
        "schema_violation_count": len(schema_viol),
        "schema_violation_sample": schema_viol[:20],
        "domain_not_in_theme_count": len(bad_pair),
        "n_unclassifiable_model": len(unclass),
        "mean_confidence": mean_conf,
        "confidence_histogram": hist,
        "theme_distribution": dict(theme_dist.most_common()),
        "top_theme_share": round(top_share, 4),
        "degenerate_distribution": degenerate,
        "n_domains_used": len(domain_dist),
        "domain_distribution": dict(domain_dist.most_common()),
    }
    (WORK / "stage2_haiku_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # console summary
    print(json.dumps({k: report[k] for k in
                      ["pass", "coverage", "schema_violation_count",
                       "domain_not_in_theme_count", "n_unclassifiable_model",
                       "mean_confidence", "top_theme_share", "n_domains_used"]},
                     indent=2, ensure_ascii=False))
    print("theme_distribution:", json.dumps(report["theme_distribution"],
                                            ensure_ascii=False))
    if not passed:
        print("STAGE 2 TEST FAILED", file=sys.stderr)
        sys.exit(1)
    print("STAGE 2 TEST PASSED")


if __name__ == "__main__":
    main()
