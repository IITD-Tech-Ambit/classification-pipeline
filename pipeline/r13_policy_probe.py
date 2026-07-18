"""Free policy probe (no API): on the FIXED original 250-paper gold sample, score
several merge policies against the SAME original Sonnet reference, to inform the
keep/revert recommendation.

Policies (per reclassified paper):
  v2            : always the v2 label (baseline)
  v3_full       : always the v3 re-pass label (what we shipped)
  v3_no_oos     : use v3 label, but if v3 said out_of_scope, revert to v2
  v3_midband    : accept v3 label only if the paper's v2 confidence was in
                  [0.5,0.8) (where the re-pass helped); else keep v2
  v3_no_oos_mid : v3_midband AND revert any out_of_scope to v2
"""
import json
from common import OUTPUTS, WORK

v2s = {json.loads(l)["id"]: json.loads(l)
       for l in open(WORK / "goldset_sample.jsonl", encoding="utf-8") if l.strip()}
son = {json.loads(l)["id"]: json.loads(l)
       for l in open(WORK / "goldset_sonnet_labels.jsonl", encoding="utf-8") if l.strip()}
v2final = {json.loads(l)["id"]: json.loads(l) for l in
           open(OUTPUTS / "classification_v2_final.BASELINE-BACKUP.jsonl", encoding="utf-8")
           if json.loads(l)["id"] in v2s}
v3final = {json.loads(l)["id"]: json.loads(l) for l in
           open(OUTPUTS / "classification_v3_final.jsonl", encoding="utf-8")
           if json.loads(l)["id"] in v2s}


def comparable(lab):
    return bool(lab.get("schema_valid")) and not lab.get("unclassifiable")


def band(c):
    return "<0.5" if c < 0.5 else ("0.5-0.8" if c < 0.8 else ">=0.8")


def pick(pid, policy):
    v2, v3 = v2final[pid], v3final[pid]
    changed = (v2.get("thematic_area"), v2.get("domain")) != \
              (v3.get("thematic_area"), v3.get("domain")) or \
              bool(v3.get("unclassifiable")) != bool(v2.get("unclassifiable"))
    if policy == "v2" or not changed:
        return v2
    if policy == "v3_full":
        return v3
    v2band = band(v2.get("confidence", 0) or 0)
    is_oos = bool(v3.get("unclassifiable"))
    if policy == "v3_no_oos":
        return v2 if is_oos else v3
    if policy == "v3_midband":
        return v3 if v2band == "0.5-0.8" else v2
    if policy == "v3_no_oos_mid":
        if is_oos or v2band != "0.5-0.8":
            return v2
        return v3
    return v2


def score(policy):
    dn = da = tn = ta = 0
    for pid in v2s:
        ref = son.get(pid, {})
        if not comparable(ref):
            continue
        lab = pick(pid, policy)
        if not lab.get("unclassifiable"):
            tn += 1
            ta += int(lab.get("thematic_area") == ref.get("thematic_area"))
            dn += 1
            da += int(lab.get("domain") == ref.get("domain"))
        else:
            # unclassifiable label: counts as comparable-but-disagree on both
            tn += 1
            dn += 1
    return (round(100 * ta / tn, 1), ta, tn, round(100 * da / dn, 1), da, dn)


print("policy           theme%          domain%")
for p in ["v2", "v3_full", "v3_no_oos", "v3_midband", "v3_no_oos_mid"]:
    tp, ta, tn, dp, da, dn = score(p)
    print(f"  {p:14} {tp:5}% ({ta}/{tn})   {dp:5}% ({da}/{dn})")
