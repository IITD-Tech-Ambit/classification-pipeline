"""STAGE B: re-classify the shaky + sink-domain papers with claude-haiku-4-5 using
the FULL improved v3 taxonomy (prompt-cached) and the v3 global rules.

Re-classification set (built in r_common.build_repass_set):
  (a) every classified paper with confidence < 0.8, PLUS
  (b) every classified >=0.8 paper sitting in a flagged sink/donor domain.

Allows full theme+domain reassignment AND unclassifiable=true (out_of_scope).
Strict-JSON schema, domain-must-belong-to-theme enforced (one retry on
violation, inherited from classify_task). Bounded concurrency, backoff on
429/5xx, per-call timeout+retry, incremental append, RESUMABLE (skips done ids),
own cost tracker + hard cost ceiling.

Usage: python r04_repass_haiku.py [LIMIT]     (LIMIT = calibration batch size)

READ-ONLY DB. No git.
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import WORK
from s15_classify_lib import Validator, classify_task, cost_from_usage
from r_common import (
    build_repass_set, build_system_prompt_v3, load_taxonomy_v3, load_text_map,
    load_v2_rows,
)

MODEL = "claude-haiku-4-5"
OUT = WORK / "repass_haiku.jsonl"
COST_OUT = WORK / "repass_cost.json"
MAX_WORKERS = 40
CHECKPOINT_EVERY = 1000
COST_STOP_USD = 56.0        # leaves headroom under the $60 task cap for Sonnet+verify
VERIFY_COST = 0.000076      # r00 model-id verification (kept in the task total)
ABSTRACT_CHARS = 1100       # cap paper text to hold down fresh-input token cost


def load_done(path):
    done = set()
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["id"])
                    except Exception:
                        pass
    return done


def summarize_cost():
    agg = {"rows": 0, "input_tokens": 0, "output_tokens": 0,
           "cache_write": 0, "cache_read": 0, "repass_cost_usd": 0.0}
    if OUT.exists():
        with open(OUT, encoding="utf-8") as fh:
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
                agg["repass_cost_usd"] += cost_from_usage(MODEL, u)
    agg["repass_cost_usd"] = round(agg["repass_cost_usd"], 4)
    return agg


def write_cost(extra=None):
    agg = summarize_cost()
    agg["model"] = MODEL
    agg["verify_cost_usd"] = VERIFY_COST
    agg["task_cost_so_far_usd"] = round(agg["repass_cost_usd"] + VERIFY_COST, 4)
    agg["cost_stop_usd"] = COST_STOP_USD
    agg["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if extra:
        agg.update(extra)
    COST_OUT.write_text(json.dumps(agg, indent=2), encoding="utf-8")
    return agg["repass_cost_usd"]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    tax, themes, theme_to_domains = load_taxonomy_v3()
    system_prompt = build_system_prompt_v3(tax, themes)
    validator = Validator(theme_to_domains)
    print(f"[repass] v3 system prompt chars={len(system_prompt)} model={MODEL}")

    rows = load_v2_rows()
    repass_ids, why = build_repass_set(rows)
    textmap = load_text_map()

    papers = []
    for i in sorted(repass_ids):
        d = textmap.get(i)
        if not d:
            continue  # should be zero (verified in r01)
        papers.append({"id": i, "title": d.get("title") or "",
                       "abstract": (d.get("abstract") or "")[:ABSTRACT_CHARS],
                       "hygiene": "ok"})
    print(f"[repass] re-classification set: {len(repass_ids)} ids "
          f"(lowconf={sum(1 for v in why.values() if v=='lowconf')}, "
          f"hi_conf_sink={sum(1 for v in why.values() if v=='hi_conf_sink')}); "
          f"papers with text: {len(papers)}")

    if limit:
        papers = papers[:limit]
        print(f"[repass] CALIBRATION mode: limiting to {len(papers)} papers")

    write_lock = threading.Lock()
    fh = open(OUT, "a", encoding="utf-8")
    counter = {"new": 0}
    stopped_for_cost = False
    t0 = time.time()
    try:
        for pass_i in range(1, 7):
            done = load_done(OUT)
            todo = [p for p in papers if p["id"] not in done]
            if not todo:
                break
            print(f"[repass] pass {pass_i}: {len(todo)} to do ({len(done)} done)",
                  flush=True)
            ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
            futs = {ex.submit(classify_task, MODEL, system_prompt, p, validator): p
                    for p in todo}
            since = 0
            try:
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        rec = fut.result()
                    except Exception as e:
                        rec = None
                        print(f"[repass] task error {p['id']}: {e!r}", flush=True)
                    if rec is None:
                        continue
                    rec["repass_reason"] = why.get(p["id"])
                    with write_lock:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    counter["new"] += 1
                    since += 1
                    if since >= CHECKPOINT_EVERY:
                        since = 0
                        fh.flush(); os.fsync(fh.fileno())
                        c = write_cost()
                        rate = counter["new"] / max(time.time() - t0, 1e-6)
                        print(f"[repass] +{counter['new']} repass_cost=${c:.2f} "
                              f"({rate:.1f} papers/s)", flush=True)
                        if c >= COST_STOP_USD:
                            stopped_for_cost = True
                            break
            finally:
                ex.shutdown(wait=True, cancel_futures=True)
            fh.flush(); os.fsync(fh.fileno())
            write_cost()
            if stopped_for_cost:
                print("[repass] STOPPED for cost ceiling", flush=True)
                break
    finally:
        fh.flush(); os.fsync(fh.fileno())
        fh.close()

    c = write_cost()
    done = load_done(OUT)
    want = {p["id"] for p in papers}
    missing = want - done
    per_paper = c / max(len([1 for _ in done if _ in want]), 1)
    print(f"[repass] DONE new={counter['new']} covered={len(want & done)}/{len(want)} "
          f"missing={len(missing)} repass_cost=${c:.2f} "
          f"(~${per_paper*1000:.3f}/1k papers) stopped_for_cost={stopped_for_cost}")
    if missing and limit is None:
        print(f"[repass] WARNING missing {len(missing)} ids (re-run to finish)")


if __name__ == "__main__":
    main()
