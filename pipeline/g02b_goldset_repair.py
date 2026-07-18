"""GOLD-SET step 2b: repair schema-invalid Sonnet labels.

A handful of Sonnet labels came back invalid: most were JSON truncated at the
400-token cap (Sonnet writes longer reasons than Haiku), a few paired a valid
domain name with the wrong theme. This re-labels ONLY those ids with a larger
max_tokens and a couple of attempts, then rewrites goldset_sonnet_labels.jsonl
in place (preserving all good rows). Idempotent and resumable.

READ-ONLY Mongo. Never writes to Mongo or git.
"""
import json
import os
import time

from bson import ObjectId

from common import get_db, WORK
from s15_classify_lib import (
    Validator, _client, build_system_prompt, cost_from_usage, load_taxonomy,
    paper_text, parse_json,
)

MODEL = "claude-sonnet-4-5"
LABELS_OUT = WORK / "goldset_sonnet_labels.jsonl"
COST_OUT = WORK / "goldset_cost.json"
FAILS_OUT = WORK / "goldset_label_fails.json"
MAX_TOKENS = 1024

# Several benign, published-research papers (biopesticides, N95 respirators,
# organophosphate chemistry, nanoagrochemicals) triggered false-positive safety
# refusals (stop_reason='refusal', empty content) under the plain classifier
# prompt. This truthful cataloguing framing does not bias the label choice; it
# only reduces spurious refusals of already-published, peer-reviewed abstracts.
RECOVERY_PREFIX = (
    "This is a library cataloguing task: classify the following already-published, "
    "peer-reviewed academic research paper into the taxonomy, based only on its "
    "title and abstract. Return the JSON object only.\n\n"
)


def call_big(system_prompt, paper, validator, attempts=6):
    prompt = RECOVERY_PREFIX + paper_text(paper["title"], paper["abstract"])
    total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    best = None
    note = "no_object"
    for a in range(attempts):
        try:
            resp = _client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system_prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            note = f"api_error: {e!r}"
            time.sleep(min(2 ** a, 20))
            continue
        u = resp.usage
        total["input_tokens"] += int(u.input_tokens)
        total["output_tokens"] += int(u.output_tokens)
        total["cache_write"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        total["cache_read"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
        if getattr(resp, "stop_reason", None) == "refusal" or not resp.content:
            note = "refusal"
            time.sleep(1.0 + a)  # refusals are partly stochastic; retry
            continue
        raw = resp.content[0].text.strip()
        try:
            obj = parse_json(raw)
        except Exception as e:
            note = f"json_parse_error: {e}"
            continue
        (theme, domain, conf, uncl, reason, sv, sn) = validator.validate(obj)
        rec = {
            "id": paper["id"], "model": MODEL, "hygiene": "goldset",
            "thematic_area": theme, "domain": domain, "confidence": conf,
            "unclassifiable": uncl, "reason": reason,
            "schema_valid": sv, "schema_note": sn,
            "labeled_via": "recovery_framing", "usage": total,
        }
        if sv or uncl:
            return rec  # accept first fully-valid result
        best = rec  # keep last invalid as fallback
        note = sn
    if best is not None:
        return best
    return {
        "id": paper["id"], "model": MODEL, "hygiene": "goldset",
        "thematic_area": None, "domain": None, "confidence": None,
        "unclassifiable": False, "reason": None,
        "schema_valid": False, "schema_note": note,
        "labeled_via": "recovery_framing", "usage": total,
    }


def main():
    themes, theme_to_domains = load_taxonomy()
    system_prompt = build_system_prompt(themes)
    validator = Validator(theme_to_domains)

    rows = {}
    order = []
    with open(LABELS_OUT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows[r["id"]] = r
            if r["id"] not in order:
                order.append(r["id"])

    bad_ids = [i for i, r in rows.items()
               if not (r.get("schema_valid") or r.get("unclassifiable"))]
    print(f"[repair] schema-invalid rows to fix: {len(bad_ids)}")
    if not bad_ids:
        print("[repair] nothing to do")
        return

    db = get_db()
    coll = db.researchmetadatascopus
    docs = {}
    for d in coll.find({"_id": {"$in": [ObjectId(x) for x in bad_ids]}},
                       {"title": 1, "abstract": 1}):
        docs[str(d["_id"])] = d

    fixed = 0
    for pid in bad_ids:
        d = docs.get(pid, {})
        paper = {"id": pid, "title": d.get("title") or "",
                 "abstract": d.get("abstract") or ""}
        rec = call_big(system_prompt, paper, validator)
        # accumulate the retry usage on top of the original attempt's usage
        prev_u = rows[pid].get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_write", "cache_read"):
            rec["usage"][k] = rec["usage"].get(k, 0) + prev_u.get(k, 0)
        rows[pid] = rec
        ok = rec.get("schema_valid") or rec.get("unclassifiable")
        if ok:
            fixed += 1
        print(f"[repair] {pid} -> valid={ok} theme={rec.get('thematic_area')} "
              f"domain={rec.get('domain')} note={rec.get('schema_note')}", flush=True)

    with open(LABELS_OUT, "w", encoding="utf-8") as fh:
        for pid in order:
            fh.write(json.dumps(rows[pid], ensure_ascii=False) + "\n")

    # refresh cost + fails
    agg = {"rows": 0, "input_tokens": 0, "output_tokens": 0,
           "cache_write": 0, "cache_read": 0, "cost_usd": 0.0}
    still_bad = []
    for pid in order:
        r = rows[pid]
        u = r.get("usage")
        if u:
            agg["rows"] += 1
            for k in ("input_tokens", "output_tokens", "cache_write", "cache_read"):
                agg[k] += u.get(k, 0)
            agg["cost_usd"] += cost_from_usage(MODEL, u)
        if not (r.get("schema_valid") or r.get("unclassifiable")):
            still_bad.append({"id": pid, "note": r.get("schema_note")})
    agg["cost_usd"] = round(agg["cost_usd"], 4)
    agg["model"] = MODEL
    agg["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    COST_OUT.write_text(json.dumps(agg, indent=2), encoding="utf-8")

    fails = json.loads(FAILS_OUT.read_text(encoding="utf-8")) if FAILS_OUT.exists() else {}
    fails["schema_invalid_labels"] = still_bad
    FAILS_OUT.write_text(json.dumps(fails, indent=2), encoding="utf-8")

    print(f"\n[repair] fixed {fixed}/{len(bad_ids)}; still invalid: {len(still_bad)} "
          f"total cost now ${agg['cost_usd']}")


if __name__ == "__main__":
    main()
