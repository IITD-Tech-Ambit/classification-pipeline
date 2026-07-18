"""Dump every gold-sample domain disagreement with title/abstract snippet and the
Sonnet reason, grouped by domain->domain pair. Read-only; reuses papers_source.jsonl.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
WORK = OUT / "work"


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


prod = {r["id"]: r for r in load_jsonl(WORK / "goldset_sample.jsonl")}
son = {r["id"]: r for r in load_jsonl(WORK / "goldset_sonnet_labels.jsonl")}
src = {r["id"]: r for r in load_jsonl(WORK / "papers_source.jsonl")}
dd = json.loads((WORK / "domain_diagnosis.json").read_text(encoding="utf-8"))

ids_by_pair = dd["ids_by_pair"]
wanted = {pid for ids in ids_by_pair.values() for pid in ids}
# pull production reasons from the final file (gold sample rows omit them)
prod_reason = {}
with open(OUT / "classification_v2_final.jsonl", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        if r["id"] in wanted:
            prod_reason[r["id"]] = r.get("reason", "")

# order pairs by count desc
ordered = sorted(ids_by_pair.items(), key=lambda kv: -len(kv[1]))

lines = []
for pair, ids in ordered:
    lines.append(f"\n{'='*90}\nPAIR ({len(ids)}):  {pair}\n{'='*90}")
    for pid in ids:
        pr = prod[pid]
        sr = son[pid]
        s = src.get(pid, {})
        title = s.get("title", "")
        abstract = (s.get("abstract") or "").replace("\n", " ")
        snip = abstract[:600]
        lines.append(f"\n[{pid}] conf={pr.get('confidence')} band={pr.get('band')} src={pr.get('source_model')}")
        lines.append(f"  TITLE: {title}")
        lines.append(f"  PROD:   {pr['thematic_area']} / {pr['domain']}")
        lines.append(f"          reason: {(prod_reason.get(pid) or '')[:400]}")
        lines.append(f"  SONNET: {sr.get('thematic_area')} / {sr.get('domain')}")
        lines.append(f"          reason: {(sr.get('reason') or '')[:400]}")
        lines.append(f"  ABSTRACT: {snip}")

txt = "\n".join(lines)
(WORK / "disagreement_examples.txt").write_text(txt, encoding="utf-8")
print("wrote", WORK / "disagreement_examples.txt", "chars:", len(txt))
print("pairs:", len(ordered), "disagreements:", sum(len(v) for v in ids_by_pair.values()))
