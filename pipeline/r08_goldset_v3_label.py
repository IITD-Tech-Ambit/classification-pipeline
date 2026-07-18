"""STAGE D step 2: independent claude-sonnet-4-5 labeling of the v3 gold sample.

Each paper (title+abstract from the local papers_source.jsonl, so NO Mongo hit)
is labeled independently with the FULL v3 taxonomy (prompt-cached, same compact
system prompt used for the re-pass) and the same strict-JSON schema. Sonnet is
BLIND to the assigned v3 label. Refusals are recorded transparently.

Robust: bounded concurrency, backoff (via classify_task), resumable, own cost
tracker + hard ceiling.  READ-ONLY DB. No git.

Usage: python r08_goldset_v3_label.py [LIMIT]
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import WORK
from s15_classify_lib import Validator, classify_task, cost_from_usage
from r_common import build_system_prompt_v3, load_taxonomy_v3, load_text_map

MODEL = "claude-sonnet-4-5"
SAMPLE_IN = WORK / "goldset_v3_sample.jsonl"
LABELS_OUT = WORK / "goldset_v3_sonnet_labels.jsonl"
COST_OUT = WORK / "goldset_v3_cost.json"
MAX_WORKERS = 8
COST_STOP_USD = 5.0


def load_done():
    done = set()
    if LABELS_OUT.exists():
        with open(LABELS_OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["id"])
                    except Exception:
                        pass
    return done


def summarize_cost():
    agg = {"rows": 0, "cost_usd": 0.0}
    if LABELS_OUT.exists():
        with open(LABELS_OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                u = r.get("usage")
                if u:
                    agg["rows"] += 1
                    agg["cost_usd"] += cost_from_usage(MODEL, u)
    agg["cost_usd"] = round(agg["cost_usd"], 4)
    return agg


def write_cost():
    agg = summarize_cost()
    agg["model"] = MODEL
    agg["cost_stop_usd"] = COST_STOP_USD
    agg["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    COST_OUT.write_text(json.dumps(agg, indent=2), encoding="utf-8")
    return agg["cost_usd"]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tax, themes, ttd = load_taxonomy_v3()
    system_prompt = build_system_prompt_v3(tax, themes)
    validator = Validator(ttd)
    print(f"[goldset-v3] system prompt chars={len(system_prompt)} model={MODEL}")

    sample = [json.loads(l) for l in open(SAMPLE_IN, encoding="utf-8") if l.strip()]
    if limit:
        sample = sample[:limit]
    textmap = load_text_map()
    papers = []
    for p in sample:
        d = textmap.get(p["id"], {})
        papers.append({"id": p["id"], "title": d.get("title") or "",
                       "abstract": d.get("abstract") or "", "hygiene": "goldset"})
    print(f"[goldset-v3] sample size: {len(papers)}")

    write_lock = threading.Lock()
    fh = open(LABELS_OUT, "a", encoding="utf-8")
    counter = {"new": 0}
    stopped = False
    try:
        for pass_i in range(1, 5):
            done = load_done()
            todo = [p for p in papers if p["id"] not in done]
            if not todo:
                break
            print(f"[goldset-v3] pass {pass_i}: {len(todo)} to label", flush=True)
            ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
            futs = {ex.submit(classify_task, MODEL, system_prompt, p, validator): p
                    for p in todo}
            try:
                for fut in as_completed(futs):
                    try:
                        rec = fut.result()
                    except Exception as e:
                        rec = None
                        print(f"[goldset-v3] task error: {e!r}", flush=True)
                    if rec is None:
                        continue
                    with write_lock:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fh.flush()
                    counter["new"] += 1
                    if counter["new"] % 25 == 0:
                        c = write_cost()
                        print(f"[goldset-v3] +{counter['new']} cost=${c:.3f}",
                              flush=True)
                        if c >= COST_STOP_USD:
                            stopped = True
                            break
            finally:
                ex.shutdown(wait=True, cancel_futures=True)
            if stopped:
                print("[goldset-v3] STOPPED for cost", flush=True)
                break
    finally:
        fh.flush(); os.fsync(fh.fileno()); fh.close()

    c = write_cost()
    done = load_done()
    missing = [p["id"] for p in papers if p["id"] not in done]
    print(f"[goldset-v3] DONE labeled={len(done)}/{len(papers)} "
          f"missing={len(missing)} cost=${c:.3f} stopped_for_cost={stopped}")
    if missing:
        print(f"[goldset-v3] missing: {missing}")


if __name__ == "__main__":
    main()
