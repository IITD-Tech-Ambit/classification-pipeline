"""STAGE B TEST + report: analyze the Haiku v3 re-pass results.

Verifies coverage (every re-pass id has exactly one result), counts schema
violations, and reports how many papers CHANGED theme / changed domain / became
unclassifiable(out_of_scope), the new confidence distribution, and whether the
flagged sink domains actually shrank within the re-pass set.

Writes outputs/work/stageB_repass_report.json.  READ-ONLY DB. No git.
"""
import json
from collections import Counter

from common import OUTPUTS, WORK
from r_common import SINK_DOMAINS, build_repass_set, band_of, load_v2_rows

REPASS = WORK / "repass_haiku.jsonl"


def main():
    v2 = {r["id"]: r for r in load_v2_rows()}
    repass_ids, why = build_repass_set(list(v2.values()))

    reps = {}
    dup = 0
    with open(REPASS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["id"] in reps:
                dup += 1
            reps[r["id"]] = r

    covered = set(reps) & repass_ids
    missing = repass_ids - set(reps)
    extra = set(reps) - repass_ids

    schema_violations = [i for i, r in reps.items()
                         if not r.get("schema_valid") and not r.get("unclassifiable")]

    changed_theme = changed_domain = became_uncl = out_of_scope = 0
    conf = Counter()
    sink_before = Counter()
    sink_after = Counter()
    moved_out_of_sink = 0
    for i in covered:
        r = reps[i]
        old = v2[i]
        old_theme, old_dom = old.get("thematic_area"), old.get("domain")
        if old_dom in SINK_DOMAINS:
            sink_before[old_dom] += 1
        if r.get("unclassifiable"):
            became_uncl += 1
            if (r.get("reason") or "").strip().lower().startswith("out_of_scope"):
                out_of_scope += 1
            # leaving a domain for unclassifiable counts as a domain change
            changed_domain += 1
            if old_dom in SINK_DOMAINS:
                moved_out_of_sink += 1
            continue
        new_theme, new_dom = r.get("thematic_area"), r.get("domain")
        if new_dom in SINK_DOMAINS:
            sink_after[new_dom] += 1
        if new_theme != old_theme:
            changed_theme += 1
        if new_dom != old_dom:
            changed_domain += 1
        if old_dom in SINK_DOMAINS and new_dom != old_dom:
            moved_out_of_sink += 1
        conf[band_of(r.get("confidence"))] += 1

    sink_delta = {d: {"before": sink_before.get(d, 0),
                      "after": sink_after.get(d, 0),
                      "delta": sink_after.get(d, 0) - sink_before.get(d, 0)}
                  for d in sorted(SINK_DOMAINS)}

    result = {
        "repass_set_size": len(repass_ids),
        "results_written": len(reps),
        "duplicate_result_rows": dup,
        "covered": len(covered),
        "missing": sorted(missing),
        "missing_count": len(missing),
        "unexpected_extra_ids": len(extra),
        "schema_violations": len(schema_violations),
        "schema_violation_ids_sample": schema_violations[:20],
        "changed_theme": changed_theme,
        "changed_domain": changed_domain,
        "became_unclassifiable": became_uncl,
        "of_which_out_of_scope": out_of_scope,
        "new_confidence_distribution": dict(conf),
        "sink_domains_within_repass": sink_delta,
        "moved_out_of_sink_total": moved_out_of_sink,
        "pass": (len(missing) == 0 and dup == 0 and len(extra) == 0),
    }
    (WORK / "stageB_repass_report.json").write_text(json.dumps(result, indent=2),
                                                    encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("missing", "schema_violation_ids_sample")},
                     indent=2))
    if result["pass"]:
        print("STAGE B: coverage OK (all re-pass ids have exactly one result)")
    else:
        print(f"STAGE B: INCOMPLETE missing={len(missing)} dup={dup} extra={len(extra)}"
              " -> re-run r04_repass_haiku.py to finish")


if __name__ == "__main__":
    main()
