"""STAGE C: merge the v3 re-pass into a full 70,298-row classification_v3_final.

For each paper: if it was in the re-pass set, take the new v3 label; otherwise
carry the v2 label unchanged. Preserves {id, thematic_area, domain, confidence,
unclassifiable, reason, source_model, escalated, changed_from_v2}. The 1,654
hygiene-unclassifiable (and the 554 LLM-unclassifiable) rows are carried as-is.

STAGE C TEST: every _id appears exactly once (70,298); 0 schema violations
(every classified row's domain belongs to its theme under the v3 taxonomy);
theme+domain distributions + confidence histogram; total changed-from-v2.

Writes outputs/classification_v3_final.jsonl, outputs/v3_validation_report.json,
outputs/v3_report.md.  READ-ONLY DB. No git.
"""
import json
from collections import Counter

from common import OUTPUTS, WORK
from r_common import band_of, build_repass_set, load_taxonomy_v3, load_v2_rows

REPASS = WORK / "repass_haiku.jsonl"
OUT = OUTPUTS / "classification_v3_final.jsonl"
VAL = OUTPUTS / "v3_validation_report.json"
MD = OUTPUTS / "v3_report.md"

EXPECTED_TOTAL = 70298


def main():
    v2_rows = load_v2_rows()
    v2 = {r["id"]: r for r in v2_rows}
    repass_ids, why = build_repass_set(v2_rows)

    reps = {}
    with open(REPASS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                reps[r["id"]] = r

    missing = repass_ids - set(reps)
    if missing:
        raise SystemExit(f"STAGE C ABORT: re-pass incomplete, {len(missing)} ids "
                         "missing. Re-run r04_repass_haiku.py first.")

    tax, themes, theme_to_domains = load_taxonomy_v3()

    merged = []
    changed = 0
    invalid_fellback = 0
    for pid, old in v2.items():
        if pid in repass_ids:
            r = reps[pid]
            uncl = bool(r.get("unclassifiable"))
            # Safety net: a re-pass row that is still schema-invalid after its one
            # retry (domain not in its theme under v3) must NOT enter the final
            # file. Fall back to the carried v2 label for those so the v3 file has
            # zero schema violations. Counted + reported honestly.
            if (not uncl) and (not r.get("schema_valid")):
                invalid_fellback += 1
                rec = {
                    "id": pid,
                    "thematic_area": old.get("thematic_area"),
                    "domain": old.get("domain"),
                    "confidence": old.get("confidence"),
                    "unclassifiable": bool(old.get("unclassifiable")),
                    "reason": old.get("reason"),
                    "source_model": old.get("source_model"),
                    "escalated": bool(old.get("escalated")),
                    "changed_from_v2": False,
                }
                merged.append(rec)
                continue
            rec = {
                "id": pid,
                "thematic_area": r.get("thematic_area"),
                "domain": r.get("domain"),
                "confidence": r.get("confidence"),
                "unclassifiable": uncl,
                "reason": r.get("reason"),
                "source_model": "haiku_repass_v3",
                "escalated": False,
            }
            was = (old.get("thematic_area"), old.get("domain"),
                   bool(old.get("unclassifiable")))
            now = (rec["thematic_area"], rec["domain"], rec["unclassifiable"])
            rec["changed_from_v2"] = (was != now)
            if rec["changed_from_v2"]:
                changed += 1
        else:
            rec = {
                "id": pid,
                "thematic_area": old.get("thematic_area"),
                "domain": old.get("domain"),
                "confidence": old.get("confidence"),
                "unclassifiable": bool(old.get("unclassifiable")),
                "reason": old.get("reason"),
                "source_model": old.get("source_model"),
                "escalated": bool(old.get("escalated")),
                "changed_from_v2": False,
            }
        merged.append(rec)

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in merged:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- TESTS ---- #
    ids = [r["id"] for r in merged]
    id_counts = Counter(ids)
    dupes = [i for i, c in id_counts.items() if c > 1]

    schema_bad = []
    for r in merged:
        if r["unclassifiable"]:
            continue
        t, d = r["thematic_area"], r["domain"]
        if t not in theme_to_domains or d not in theme_to_domains.get(t, []):
            schema_bad.append(r["id"])

    classified = [r for r in merged if not r["unclassifiable"]]
    uncl_rows = [r for r in merged if r["unclassifiable"]]
    out_of_scope = [r for r in uncl_rows
                    if (r.get("reason") or "").strip().lower().startswith("out_of_scope")]
    # hygiene = unclassifiable with no source text -> reconstruct via repass set /
    # v2: hygiene ones were never in papers_source; approximate by source_model
    theme_dist = Counter(r["thematic_area"] for r in classified)
    domain_dist = Counter(r["domain"] for r in classified)
    conf_hist = Counter(band_of(r["confidence"]) for r in classified)
    src_dist = Counter(r["source_model"] for r in merged)

    passed = (len(merged) == EXPECTED_TOTAL and len(dupes) == 0
              and len(schema_bad) == 0)

    report = {
        "pass": passed,
        "total_rows": len(merged),
        "expected_total": EXPECTED_TOTAL,
        "unique_ids": len(id_counts),
        "duplicate_ids": dupes[:20],
        "duplicate_id_count": len(dupes),
        "schema_violations": len(schema_bad),
        "schema_violation_ids_sample": schema_bad[:20],
        "classified": len(classified),
        "unclassifiable_total": len(uncl_rows),
        "unclassifiable_out_of_scope": len(out_of_scope),
        "changed_from_v2": changed,
        "repass_invalid_fellback_to_v2": invalid_fellback,
        "reclassification_set_size": len(repass_ids),
        "theme_distribution": dict(theme_dist.most_common()),
        "domain_distribution": dict(domain_dist.most_common()),
        "confidence_histogram": dict(conf_hist),
        "source_model_distribution": dict(src_dist),
    }
    VAL.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(report)

    print(f"total={len(merged)} unique={len(id_counts)} dupes={len(dupes)} "
          f"schema_violations={len(schema_bad)} changed_from_v2={changed} "
          f"unclassifiable={len(uncl_rows)} (out_of_scope={len(out_of_scope)})")
    if not passed:
        print("STAGE C: TESTS FAILED")
        raise SystemExit(1)
    print(f"STAGE C: ALL TESTS PASSED -> wrote {OUT.name}, {VAL.name}, {MD.name}")


def write_md(r):
    L = []
    A = L.append
    A("# Classification v3 — Full-corpus validation report\n")
    A(f"- Total rows: **{r['total_rows']}** (expected {r['expected_total']}) · "
      f"unique ids: {r['unique_ids']} · duplicate ids: {r['duplicate_id_count']}")
    A(f"- Schema violations (domain not in theme under v3): "
      f"**{r['schema_violations']}**")
    A(f"- Classified: **{r['classified']}** · Unclassifiable: "
      f"**{r['unclassifiable_total']}** (of which out_of_scope: "
      f"**{r['unclassifiable_out_of_scope']}**)")
    A(f"- Changed from v2 (theme/domain/unclassifiable): **{r['changed_from_v2']}** "
      f"of {r['reclassification_set_size']} re-classified\n")
    A("## Theme distribution (classified)\n")
    A("| theme | papers |")
    A("|---|---:|")
    for t, c in r["theme_distribution"].items():
        A(f"| {t} | {c} |")
    A("")
    A("## Confidence histogram (classified)\n")
    A("| band | papers |")
    A("|---|---:|")
    for b in ("<0.5", "0.5-0.8", ">=0.8", "none"):
        if b in r["confidence_histogram"]:
            A(f"| {b} | {r['confidence_histogram'][b]} |")
    A("")
    A("## Domain distribution (classified)\n")
    A("| domain | papers |")
    A("|---|---:|")
    for d, c in r["domain_distribution"].items():
        A(f"| {d} | {c} |")
    A("")
    MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
