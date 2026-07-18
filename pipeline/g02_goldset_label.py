"""GOLD-SET step 2: independent Sonnet labeling of the 250-paper sample.

For each sampled paper we send title+abstract to claude-sonnet-4-5 with the FULL
frozen v2 taxonomy (prompt-cached) and ask it to INDEPENDENTLY choose the single
best thematic_area + domain, using the exact same strict-JSON schema as the
production classifier. Sonnet is given NO knowledge of the existing Haiku/Sonnet
label -- this is a fresh, independent label, not a review.

Robust: bounded concurrency, exponential backoff (inherited from
s15_classify_lib.classify_task), resumable (skips ids already labeled), and its
own isolated cost tracker so the $10 guardrail for THIS task is enforced
separately from the big overnight run.

READ-ONLY Mongo. Never writes to Mongo or git.

Usage: python g02_goldset_label.py [LIMIT]
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bson import ObjectId

from common import get_db, WORK
from s15_classify_lib import (
    Validator, build_system_prompt, classify_task, cost_from_usage,
    load_taxonomy,
)

MODEL = "claude-sonnet-4-5"
SAMPLE_IN = WORK / "goldset_sample.jsonl"
LABELS_OUT = WORK / "goldset_sonnet_labels.jsonl"
COST_OUT = WORK / "goldset_cost.json"
FAILS_OUT = WORK / "goldset_label_fails.json"

MAX_WORKERS = 8
COST_STOP_USD = 9.0  # hard local ceiling, well under the $10 task budget


def load_sample():
    papers = []
    with open(SAMPLE_IN, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                papers.append(json.loads(line))
    return papers


def load_done():
    done = set()
    if LABELS_OUT.exists():
        with open(LABELS_OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    continue
    return done


def summarize_cost():
    agg = {"rows": 0, "input_tokens": 0, "output_tokens": 0,
           "cache_write": 0, "cache_read": 0, "cost_usd": 0.0}
    if not LABELS_OUT.exists():
        return agg
    with open(LABELS_OUT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            u = r.get("usage")
            if not u:
                continue
            agg["rows"] += 1
            for k in ("input_tokens", "output_tokens", "cache_write", "cache_read"):
                agg[k] += u.get(k, 0)
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
    themes, theme_to_domains = load_taxonomy()
    system_prompt = build_system_prompt(themes)
    validator = Validator(theme_to_domains)
    print(f"[goldset] system prompt chars: {len(system_prompt)}  model={MODEL}")

    sample = load_sample()
    if limit:
        sample = sample[:limit]
    sample_ids = [p["id"] for p in sample]
    print(f"[goldset] sample size: {len(sample)}")

    # pull title+abstract from Mongo (read-only)
    db = get_db()
    coll = db.researchmetadatascopus
    oids = [ObjectId(x) for x in sample_ids]
    docs = {}
    for d in coll.find({"_id": {"$in": oids}}, {"title": 1, "abstract": 1}):
        docs[str(d["_id"])] = d
    missing_in_mongo = [i for i in sample_ids if i not in docs]
    if missing_in_mongo:
        print(f"[goldset] WARNING: {len(missing_in_mongo)} ids not found in Mongo")

    papers = []
    for pid in sample_ids:
        d = docs.get(pid, {})
        papers.append({
            "id": pid,
            "title": d.get("title") or "",
            "abstract": d.get("abstract") or "",
            "hygiene": "goldset",
        })

    done = load_done()
    todo = [p for p in papers if p["id"] not in done]
    print(f"[goldset] already labeled: {len(done)}  to do: {len(todo)}")

    write_lock = threading.Lock()
    fh = open(LABELS_OUT, "a", encoding="utf-8")
    counter = {"new": 0, "fail": 0}
    fails = []
    stopped_for_cost = False

    try:
        # multi-pass to retry hard failures (classify_task returns None on those)
        for pass_i in range(1, 5):
            done = load_done()
            todo = [p for p in papers if p["id"] not in done]
            if not todo:
                break
            print(f"[goldset] pass {pass_i}: {len(todo)} to label", flush=True)
            ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
            futs = {ex.submit(classify_task, MODEL, system_prompt, p, validator): p
                    for p in todo}
            try:
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        rec = fut.result()
                    except Exception as e:
                        rec = None
                        print(f"[goldset] task error {p['id']}: {e!r}", flush=True)
                    if rec is None:
                        continue  # hard API failure -> retry next pass
                    with write_lock:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fh.flush()
                    counter["new"] += 1
                    if counter["new"] % 25 == 0:
                        total = write_cost()
                        print(f"[goldset] labeled+={counter['new']} "
                              f"cost=${total:.3f}", flush=True)
                        if total >= COST_STOP_USD:
                            stopped_for_cost = True
                            break
            finally:
                ex.shutdown(wait=True, cancel_futures=True)
            if stopped_for_cost:
                print("[goldset] STOPPED for cost ceiling", flush=True)
                break
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    total = write_cost()
    done = load_done()
    labeled_ok = 0
    labeled_bad = []
    with open(LABELS_OUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("schema_valid") or r.get("unclassifiable"):
                labeled_ok += 1
            else:
                labeled_bad.append({"id": r["id"], "note": r.get("schema_note")})

    still_missing = [i for i in sample_ids if i not in done]
    fails = {
        "missing_from_mongo": missing_in_mongo,
        "never_labeled": still_missing,
        "schema_invalid_labels": labeled_bad,
    }
    FAILS_OUT.write_text(json.dumps(fails, indent=2), encoding="utf-8")

    print(f"\n[goldset] DONE labeled={len(done)}/{len(sample_ids)} "
          f"schema_ok={labeled_ok} schema_bad={len(labeled_bad)} "
          f"never_labeled={len(still_missing)} cost=${total:.3f} "
          f"stopped_for_cost={stopped_for_cost}")
    if still_missing:
        print(f"[goldset] WARNING never labeled: {still_missing}")


if __name__ == "__main__":
    main()
