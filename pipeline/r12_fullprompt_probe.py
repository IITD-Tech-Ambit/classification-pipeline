"""Confirmatory test #2: did the cost-saving compact prompt / 1100-char abstracts
degrade the Haiku re-pass? Re-label the CHANGED papers in the fresh v3 gold
sample with FULL v3 prompt + full (1500-char) abstracts, and compare agreement
against the SAME already-collected v3-Sonnet labels.

If full-prompt Haiku agrees with Sonnet markedly better than the compact re-pass
did, the compaction hurt. If not, the divergence is intrinsic to these hard
papers / the aggressive out_of_scope routing.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import WORK
from s15_classify_lib import Validator, classify_task, paper_text as _pt
from r_common import build_system_prompt_v3, load_taxonomy_v3, load_text_map

MODEL = "claude-haiku-4-5"
OUT = WORK / "fullprompt_probe.jsonl"

sample = {json.loads(l)["id"]: json.loads(l)
          for l in open(WORK / "goldset_v3_sample.jsonl", encoding="utf-8") if l.strip()}
son = {json.loads(l)["id"]: json.loads(l)
       for l in open(WORK / "goldset_v3_sonnet_labels.jsonl", encoding="utf-8") if l.strip()}
textmap = load_text_map()

changed_ids = [pid for pid, s in sample.items() if s.get("changed_from_v2")]

tax, themes, ttd = load_taxonomy_v3()
full_prompt = build_system_prompt_v3(tax, themes, compact=False)  # FULL scope notes
validator = Validator(ttd)
print(f"full prompt chars={len(full_prompt)}  changed papers to probe={len(changed_ids)}")

papers = []
for pid in changed_ids:
    d = textmap.get(pid, {})
    papers.append({"id": pid, "title": d.get("title") or "",
                   "abstract": (d.get("abstract") or "")[:1500], "hygiene": "ok"})

results = {}
lock = threading.Lock()
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(classify_task, MODEL, full_prompt, p, validator): p for p in papers}
    for fut in as_completed(futs):
        rec = fut.result()
        if rec:
            with lock:
                results[rec["id"]] = rec

with open(OUT, "w", encoding="utf-8") as fh:
    for r in results.values():
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def comparable(lab):
    return bool(lab.get("schema_valid")) and not lab.get("unclassifiable")


compact_dom = compact_th = full_dom = full_th = 0
dn = tn = 0
for pid in changed_ids:
    ref = son.get(pid, {})
    if not comparable(ref):
        continue
    comp = sample[pid]  # compact re-pass label lives in v3 final; use sample copy
    # sample has thematic_area/domain from v3 final
    fr = results.get(pid, {})
    tn += 1
    if comp.get("thematic_area") == ref.get("thematic_area"):
        compact_th += 1
    if fr.get("thematic_area") == ref.get("thematic_area") and not fr.get("unclassifiable"):
        full_th += 1
    dn += 1
    if comp.get("domain") == ref.get("domain"):
        compact_dom += 1
    if comparable(fr) and fr.get("domain") == ref.get("domain"):
        full_dom += 1

fp_uncl = sum(1 for pid in changed_ids if results.get(pid, {}).get("unclassifiable"))
print(f"\nAgreement vs the SAME v3-Sonnet labels, on {tn} changed+comparable papers:")
print(f"  theme : compact re-pass {round(100*compact_th/tn,1)}%  ->  "
      f"full-prompt {round(100*full_th/tn,1)}%")
print(f"  domain: compact re-pass {round(100*compact_dom/dn,1)}%  ->  "
      f"full-prompt {round(100*full_dom/dn,1)}%")
print(f"full-prompt Haiku out_of_scope count (of {len(changed_ids)} changed): {fp_uncl}")
