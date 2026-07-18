"""Targeted repair: re-run the handful of Sonnet escalation papers whose output
failed to parse (likely truncated at max_tokens=400) using a larger token budget,
and rewrite those rows in sonnet_escalation.jsonl in place. Cheap (<~150 calls).
Cost of these repair calls is captured in the rewritten rows' usage, so the
authoritative cost tracker still reconstructs total spend from the files.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from common import WORK
from s15_classify_lib import (SONNET_OUT, Validator, build_system_prompt,
                              load_taxonomy, paper_text, parse_json,
                              write_cost_tracker, _usage_tuple)

MODEL = "claude-sonnet-4-5"
SOURCE = WORK / "papers_source.jsonl"
_client = anthropic.Anthropic(timeout=120.0, max_retries=0)


def repair_call(system_prompt, paper, validator, max_tokens=900):
    prompt = ("Classify this paper. Return the JSON object only.\n\n"
              + paper_text(paper["title"], paper["abstract"]))
    total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    obj = None
    note = "no_object"
    for attempt in range(5):
        try:
            resp = _client.messages.create(
                model=MODEL, max_tokens=max_tokens,
                system=[{"type": "text", "text": system_prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            u = _usage_tuple(resp.usage)
            for k in total:
                total[k] += u[k]
            raw = resp.content[0].text.strip() if resp.content else ""
            try:
                obj = parse_json(raw)
                note = "ok"
                break
            except Exception as e:
                note = f"json_parse_error: {e}"
                time.sleep(0.5 * (attempt + 1))
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APITimeoutError, anthropic.APIConnectionError):
            time.sleep(min(2 ** attempt, 30))
    rec = {"id": paper["id"], "model": MODEL, "hygiene": paper["hygiene"],
           "usage": total}
    if obj is None:
        rec.update({"thematic_area": None, "domain": None, "confidence": None,
                    "unclassifiable": False, "reason": None,
                    "schema_valid": False, "schema_note": note})
        return rec
    (t, d, c, u, r, sv, sn) = validator.validate(obj)
    rec.update({"thematic_area": t, "domain": d, "confidence": c,
                "unclassifiable": u, "reason": r, "schema_valid": sv,
                "schema_note": sn})
    return rec


def main():
    themes, theme_to_domains = load_taxonomy()
    system_prompt = build_system_prompt(themes)
    validator = Validator(theme_to_domains)

    src = {}
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                p = json.loads(line)
                src[p["id"]] = p

    rows = [json.loads(l) for l in open(SONNET_OUT, encoding="utf-8") if l.strip()]
    targets = [r for r in rows
               if not r["schema_valid"] and not r.get("unclassifiable")
               and (r.get("schema_note") or "").startswith("json_parse_error")]
    print(f"parse-error rows to repair: {len(targets)}")
    if not targets:
        return

    repaired = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(repair_call, system_prompt, src[r["id"]], validator): r["id"]
                for r in targets if r["id"] in src}
        for fut in as_completed(futs):
            rec = fut.result()
            repaired[rec["id"]] = rec

    fixed = sum(1 for rec in repaired.values() if rec["schema_valid"])
    print(f"repaired to valid schema: {fixed}/{len(repaired)}")

    # rewrite sonnet_escalation.jsonl with repaired rows replacing originals
    with open(SONNET_OUT, "w", encoding="utf-8") as out:
        for r in rows:
            if r["id"] in repaired:
                out.write(json.dumps(repaired[r["id"]], ensure_ascii=False) + "\n")
            else:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_cost_tracker()
    print("rewrote sonnet_escalation.jsonl; cost tracker refreshed")


if __name__ == "__main__":
    main()
