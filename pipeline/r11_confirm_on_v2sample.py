"""Confirmatory test #1 (no API): on the ORIGINAL fixed 250-paper gold sample,
does the v3 label agree with the SAME independent Sonnet reference better or
worse than the v2 label did? Same papers, same Sonnet reference => any change is
purely due to labels changing in v3.

Caveat: the original Sonnet labels used the v2 taxonomy (no new domains / no
out_of_scope), so v3 labels that moved to a brand-new domain cannot match by
construction; we report those separately.
"""
import json
from collections import Counter

from common import OUTPUTS, WORK

v2s = {json.loads(l)["id"]: json.loads(l)
       for l in open(WORK / "goldset_sample.jsonl", encoding="utf-8") if l.strip()}
son = {json.loads(l)["id"]: json.loads(l)
       for l in open(WORK / "goldset_sonnet_labels.jsonl", encoding="utf-8") if l.strip()}
v2final = {}
for l in open(OUTPUTS / "classification_v2_final.BASELINE-BACKUP.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r["id"] in v2s:
        v2final[r["id"]] = r
v3final = {}
for l in open(OUTPUTS / "classification_v3_final.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r["id"] in v2s:
        v3final[r["id"]] = r

NEW_DOMAINS = {"Thermal Systems, Engines & Energy Harvesting",
               "Construction Materials & Concrete Technology"}


def comparable(lab):
    return bool(lab.get("schema_valid")) and not lab.get("unclassifiable")


def agree(final_lab, ref, level):
    if not comparable(ref):
        return None
    return final_lab.get(level) == ref.get(level)


rows = []
for pid in v2s:
    ref = son.get(pid, {})
    v2 = v2final.get(pid, {})
    v3 = v3final.get(pid, {})
    changed = (v2.get("thematic_area"), v2.get("domain")) != \
              (v3.get("thematic_area"), v3.get("domain")) or \
              bool(v3.get("unclassifiable")) != bool(v2.get("unclassifiable"))
    rows.append({
        "id": pid, "changed": changed,
        "v3_uncl": bool(v3.get("unclassifiable")),
        "v3_new_domain": v3.get("domain") in NEW_DOMAINS,
        "v2_dom_ok": agree(v2, ref, "domain"),
        "v3_dom_ok": agree(v3, ref, "domain"),
        "v2_th_ok": agree(v2, ref, "thematic_area"),
        "v3_th_ok": agree(v3, ref, "thematic_area"),
    })


def rate(rs, key):
    c = [r for r in rs if r[key] is not None]
    y = sum(1 for r in c if r[key])
    return f"{round(100*y/len(c),1) if c else None}% ({y}/{len(c)})"


allrows = rows
changed = [r for r in rows if r["changed"]]
carried = [r for r in rows if not r["changed"]]

print("=== v2 vs v3 label agreement against the SAME original Sonnet reference ===")
print(f"(fixed original 250-paper gold sample; {len(changed)} changed in v3, "
      f"{len(carried)} carried)\n")
print("ALL comparable papers:")
print(f"  theme : v2 {rate(allrows,'v2_th_ok')}   ->  v3 {rate(allrows,'v3_th_ok')}")
print(f"  domain: v2 {rate(allrows,'v2_dom_ok')}   ->  v3 {rate(allrows,'v3_dom_ok')}")
print("\nOnly the papers v3 CHANGED (this is where the re-pass acted):")
print(f"  theme : v2 {rate(changed,'v2_th_ok')}   ->  v3 {rate(changed,'v3_th_ok')}")
print(f"  domain: v2 {rate(changed,'v2_dom_ok')}   ->  v3 {rate(changed,'v3_dom_ok')}")
print("\nCarried (unchanged) papers (sanity - should be identical):")
print(f"  domain: v2 {rate(carried,'v2_dom_ok')}   ->  v3 {rate(carried,'v3_dom_ok')}")

print(f"\nv3 changed papers that became unclassifiable/out_of_scope: "
      f"{sum(1 for r in changed if r['v3_uncl'])}")
print(f"v3 changed papers moved to a brand-new domain (cannot match v2-Sonnet): "
      f"{sum(1 for r in changed if r['v3_new_domain'])}")
