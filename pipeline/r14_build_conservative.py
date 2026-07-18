"""Build the CONSERVATIVE v3 candidate (no new API calls).

Policy (evidence-driven, see r13_policy_probe): accept a re-pass label ONLY when
it is most likely an improvement -- i.e. the paper's v2 confidence was in the
0.5-0.8 mid-band (where the re-pass measurably helped) AND the re-pass did not
mark it out_of_scope (Haiku over-fired out_of_scope ~13x more than the Sonnet
judge). Otherwise keep the v2 label. Papers never re-classified keep v2.

This is a CANDIDATE for a future approved, freshly-validated run -- NOT a
validated production artifact. Writes classification_v3_conservative_final.jsonl
+ v3_conservative_stats.json.  READ-ONLY DB. No git.
"""
import json
from collections import Counter

from common import OUTPUTS
from r_common import build_repass_set, load_taxonomy_v3, load_v2_rows

REPASS = OUTPUTS / "work" / "repass_haiku.jsonl"
OUT = OUTPUTS / "classification_v3_conservative_final.jsonl"
STATS = OUTPUTS / "v3_conservative_stats.json"


def band(c):
    c = c or 0
    return "<0.5" if c < 0.5 else ("0.5-0.8" if c < 0.8 else ">=0.8")


def main():
    v2_rows = load_v2_rows()
    v2 = {r["id"]: r for r in v2_rows}
    repass_ids, _ = build_repass_set(v2_rows)
    reps = {json.loads(l)["id"]: json.loads(l)
            for l in open(REPASS, encoding="utf-8") if l.strip()}
    _, _, theme_to_domains = load_taxonomy_v3()

    merged = []
    accepted = 0
    for pid, old in v2.items():
        use_v3 = False
        if pid in repass_ids:
            r = reps.get(pid, {})
            v2band = band(old.get("confidence"))
            if (v2band == "0.5-0.8" and r.get("schema_valid")
                    and not r.get("unclassifiable")):
                use_v3 = True
        if use_v3:
            r = reps[pid]
            rec = {"id": pid, "thematic_area": r.get("thematic_area"),
                   "domain": r.get("domain"), "confidence": r.get("confidence"),
                   "unclassifiable": False, "reason": r.get("reason"),
                   "source_model": "haiku_repass_v3", "escalated": False,
                   "changed_from_v2": (old.get("thematic_area"), old.get("domain"))
                   != (r.get("thematic_area"), r.get("domain"))}
            accepted += rec["changed_from_v2"]
        else:
            rec = {"id": pid, "thematic_area": old.get("thematic_area"),
                   "domain": old.get("domain"), "confidence": old.get("confidence"),
                   "unclassifiable": bool(old.get("unclassifiable")),
                   "reason": old.get("reason"),
                   "source_model": old.get("source_model"),
                   "escalated": bool(old.get("escalated")),
                   "changed_from_v2": False}
        merged.append(rec)

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in merged:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # validate
    schema_bad = 0
    for r in merged:
        if r["unclassifiable"]:
            continue
        if r["domain"] not in theme_to_domains.get(r["thematic_area"], []):
            schema_bad += 1
    uncl = sum(1 for r in merged if r["unclassifiable"])
    changed = sum(1 for r in merged if r["changed_from_v2"])
    stats = {
        "total_rows": len(merged),
        "schema_violations": schema_bad,
        "changed_from_v2": changed,
        "accepted_repass_changes": accepted,
        "unclassifiable_total": uncl,
        "policy": "accept re-pass only for v2 mid-band (0.5-0.8), non-out_of_scope",
        "note": "CANDIDATE only; needs a fresh independent gold re-test before adoption.",
    }
    STATS.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
    print(f"wrote {OUT.name} (schema_violations={schema_bad})")


if __name__ == "__main__":
    main()
