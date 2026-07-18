"""Diagnostic for the Stage-D drop: split the v3 gold sample by changed-vs-carried
and by band, and dump the <0.5 disagreements with titles so we can judge whether
the re-pass hurt or the residual <0.5 band is just intrinsically hard.
"""
import json
from collections import defaultdict

from common import OUTPUTS, WORK

sample = {json.loads(l)["id"]: json.loads(l)
          for l in open(WORK / "goldset_v3_sample.jsonl", encoding="utf-8") if l.strip()}
labels = {json.loads(l)["id"]: json.loads(l)
          for l in open(WORK / "goldset_v3_sonnet_labels.jsonl", encoding="utf-8") if l.strip()}
v3 = {}
for l in open(OUTPUTS / "classification_v3_final.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r["id"] in sample:
        v3[r["id"]] = r
text = {}
for l in open(WORK / "papers_source.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r["id"] in sample:
        text[r["id"]] = r


def cell(pid):
    fin = v3[pid]
    lab = labels.get(pid, {})
    dc = bool(lab.get("schema_valid")) and not lab.get("unclassifiable")
    ad = (fin.get("domain") == lab.get("domain")) if dc else None
    at = (fin.get("thematic_area") == lab.get("thematic_area")) \
        if (lab.get("thematic_area") and not lab.get("unclassifiable")) else None
    return fin, lab, dc, ad, at


# changed vs carried
buckets = defaultdict(lambda: {"dn": 0, "da": 0, "tn": 0, "ta": 0})
for pid, s in sample.items():
    key = "changed" if s.get("changed_from_v2") else "carried"
    fin, lab, dc, ad, at = cell(pid)
    if at is not None:
        buckets[key]["tn"] += 1; buckets[key]["ta"] += int(at)
    if ad is not None:
        buckets[key]["dn"] += 1; buckets[key]["da"] += int(ad)

print("=== agreement split: changed-from-v2 vs carried ===")
for k, b in buckets.items():
    tp = round(100 * b["ta"] / b["tn"], 1) if b["tn"] else None
    dp = round(100 * b["da"] / b["dn"], 1) if b["dn"] else None
    print(f"  {k:8} n={sum(1 for p in sample.values() if (('changed' if p.get('changed_from_v2') else 'carried')==k))}"
          f"  theme {tp}% ({b['ta']}/{b['tn']})  domain {dp}% ({b['da']}/{b['dn']})")

print("\n=== <0.5 band disagreements (v3 vs sonnet) ===")
n = 0
for pid, s in sample.items():
    if s["band"] != "<0.5":
        continue
    fin, lab, dc, ad, at = cell(pid)
    if ad is False or at is False:
        n += 1
        t = (text.get(pid, {}).get("title") or "")[:85]
        chg = "CHG" if s.get("changed_from_v2") else "car"
        print(f"[{chg}] conf={fin.get('confidence')} src={fin.get('source_model')[:14]}")
        print(f"   title: {t}")
        print(f"   v3    : {fin.get('thematic_area')[:28]:28} | {fin.get('domain')}")
        print(f"   sonnet: {(lab.get('thematic_area') or '')[:28]:28} | {lab.get('domain')}")
print(f"\n<0.5 disagreements shown: {n}")
