"""Shared classification library for the overnight classification-v2 run.

Provides:
  - taxonomy loading + the prompt-cached system prompt (identical construction
    to the validated 100-paper probe, s14_probe_100.py)
  - strict-JSON parsing + schema validation (theme in the 9, domain in that theme)
  - per-model token pricing + cost reconstruction from the output files
    (resume-safe: cost is always recomputed from what is actually on disk)
  - a robust, resumable, bounded-concurrency run_classification() runner with
    exponential backoff, per-call timeout, per-paper usage capture, incremental
    append-per-paper output, periodic cost checkpointing, and a hard cost ceiling.

READ-ONLY DB. Never writes to Mongo. Never touches git.
"""
import json
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from common import OUTPUTS, WORK

TAXONOMY_PATH = OUTPUTS / "taxonomy-draft-v2.json"

# ---- per-model pricing (USD per million tokens) --------------------------- #
PRICING = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_write": 3.75, "cache_read": 0.30},
}

# ---- hard cost guardrail -------------------------------------------------- #
# The task budget remaining is ~$284 and the hard cap for THIS task is $260.
# We stop well under it. Expected total spend ~$230.
COST_STOP_USD = 255.0

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=90.0,
                              max_retries=0)


# --------------------------------------------------------------------------- #
# taxonomy -> system prompt  (matches s14_probe_100.py exactly)
# --------------------------------------------------------------------------- #
def load_taxonomy():
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    themes = tax["themes"]
    theme_to_domains = {t["name"]: [d["name"] for d in t["domains"]] for t in themes}
    return themes, theme_to_domains


def build_system_prompt(themes):
    lines = []
    lines.append(
        "You are the production classifier for IIT Delhi's research-paper portal. "
        "You assign each paper to exactly ONE thematic area and exactly ONE domain "
        "within that area, using the FIXED two-level taxonomy below. Decide by the "
        "paper's PRIMARY scientific contribution, not by an incidental keyword.\n"
    )
    lines.append("=" * 70)
    lines.append("FROZEN TAXONOMY (9 thematic areas; each area lists its allowed domains)")
    lines.append("=" * 70 + "\n")
    for i, t in enumerate(themes, 1):
        lines.append(f"## THEME {i}: {t['name']}")
        lines.append(f"Scope & tie-break rules: {t['scope_note']}")
        lines.append("Allowed domains (choose exactly one; the domain MUST be from THIS "
                     "theme's list):")
        for d in t["domains"]:
            lines.append(f"  - {d['name']}: {d['definition']}")
        lines.append("")
    lines.append("=" * 70)
    lines.append(
        "OUTPUT RULES:\n"
        "1. Return STRICT JSON only, a single object, no prose, no markdown fences.\n"
        "2. Schema: {\"thematic_area\": str, \"domain\": str, \"confidence\": float, "
        "\"unclassifiable\": bool, \"reason\": str}\n"
        "3. Choose EXACTLY ONE thematic_area (verbatim from the 9 theme names) and "
        "EXACTLY ONE domain. The domain MUST be one of the domains listed under the "
        "chosen thematic_area above (copy the domain name verbatim).\n"
        "4. Single-label: no lists, no multiple themes/domains, no overlaps.\n"
        "5. confidence is your calibrated probability (0.0-1.0) that this "
        "theme+domain is correct.\n"
        "6. Set unclassifiable=true ONLY for genuine non-research / no-signal items "
        "(editorials, prefaces, front matter, errata, indexes, empty/no usable "
        "abstract with an uninformative title). When unclassifiable=true, still put "
        "your best-guess thematic_area and domain (or empty strings) and explain in "
        "reason.\n"
        "7. reason: one concise sentence justifying the assignment.\n"
        "When two themes seem possible, apply the tie-break rules embedded in each "
        "theme's scope note. Respond with the JSON object only."
    )
    return "\n".join(lines)


def paper_text(title, abstract):
    t = f"Title: {title}"
    if abstract:
        t += f"\n\nAbstract: {abstract[:1500]}"
    else:
        t += "\n\n(No abstract available.)"
    return t


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[s:e + 1])


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
class Validator:
    def __init__(self, theme_to_domains):
        self.norm_theme = {norm(n): n for n in theme_to_domains}
        self.norm_domain = {tn: {norm(d): d for d in doms}
                            for tn, doms in theme_to_domains.items()}

    def validate(self, obj):
        """Return (theme, domain, confidence, unclassifiable, reason,
        schema_valid, schema_note)."""
        theme = obj.get("thematic_area")
        domain = obj.get("domain")
        reason = obj.get("reason")
        confidence = obj.get("confidence")
        unclassifiable = bool(obj.get("unclassifiable", False))
        schema_valid = False
        schema_note = ""

        canon_theme = self.norm_theme.get(norm(theme))
        if unclassifiable:
            schema_valid = True
            schema_note = "unclassifiable"
            if canon_theme:
                theme = canon_theme
        elif canon_theme is None:
            schema_note = f"theme_not_in_taxonomy:{theme!r}"
        else:
            theme = canon_theme
            canon_domain = self.norm_domain[canon_theme].get(norm(domain))
            if canon_domain is None:
                schema_note = f"domain_not_in_theme:{domain!r}"
            else:
                domain = canon_domain
                schema_valid = True

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
        return theme, domain, confidence, unclassifiable, reason, schema_valid, schema_note


# --------------------------------------------------------------------------- #
# single API call with backoff + usage capture
# --------------------------------------------------------------------------- #
def _usage_tuple(u):
    return {
        "input_tokens": int(u.input_tokens),
        "output_tokens": int(u.output_tokens),
        "cache_write": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0),
    }


def _api_call(model, system_prompt, prompt):
    """One API call. Returns (obj_or_None, raw, usage_dict, err_or_None)."""
    resp = _client.messages.create(
        model=model,
        max_tokens=400,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    usage = _usage_tuple(resp.usage)
    raw = resp.content[0].text.strip() if resp.content else ""
    try:
        obj = parse_json(raw)
        return obj, raw, usage, None
    except Exception as e:
        return None, raw, usage, f"json_parse_error: {e}"


def classify_task(model, system_prompt, paper, validator, max_api_attempts=6):
    """Classify one paper robustly. Accumulates usage across ALL attempts
    (retries cost money and are counted). Returns a record dict OR None on a
    hard API failure (so the runner can leave it missing and retry next pass).
    """
    prompt = ("Classify this paper. Return the JSON object only.\n\n"
              + paper_text(paper["title"], paper["abstract"]))
    total_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0,
                   "cache_read": 0}

    def add(u):
        for k in total_usage:
            total_usage[k] += u[k]

    obj = None
    raw = ""
    parse_err = None
    api_err = None

    for attempt in range(max_api_attempts):
        try:
            obj, raw, usage, err = _api_call(model, system_prompt, prompt)
            add(usage)
            if obj is not None:
                parse_err = None
                break
            # got a response but unparseable -> retry a few times
            parse_err = err
            if attempt >= 2:
                break
            time.sleep(0.5 * (attempt + 1))
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            api_err = e
            time.sleep(min(2 ** attempt, 30))

    if obj is None and api_err is not None and total_usage["input_tokens"] == 0:
        # never got a usable response at all -> hard failure, retry next pass
        return None

    rec = {
        "id": paper["id"],
        "model": model,
        "hygiene": paper["hygiene"],
    }
    if obj is None:
        rec.update({
            "thematic_area": None, "domain": None, "confidence": None,
            "unclassifiable": False, "reason": None,
            "schema_valid": False, "schema_note": parse_err or "no_object",
            "usage": total_usage,
        })
        return rec

    (theme, domain, confidence, unclassifiable, reason,
     schema_valid, schema_note) = validator.validate(obj)

    # one extra retry specifically for schema violations (invalid theme/domain)
    if not schema_valid and not unclassifiable:
        try:
            obj2, raw2, usage2, err2 = _api_call(model, system_prompt, prompt)
            add(usage2)
            if obj2 is not None:
                (t2, d2, c2, u2, r2, sv2, sn2) = validator.validate(obj2)
                if sv2:
                    theme, domain, confidence, unclassifiable, reason = t2, d2, c2, u2, r2
                    schema_valid, schema_note = sv2, sn2
                    raw = raw2
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APITimeoutError, anthropic.APIConnectionError):
            pass

    rec.update({
        "thematic_area": theme, "domain": domain, "confidence": confidence,
        "unclassifiable": unclassifiable, "reason": reason,
        "schema_valid": schema_valid, "schema_note": schema_note,
        "usage": total_usage,
    })
    return rec


# --------------------------------------------------------------------------- #
# cost reconstruction from output files (resume-safe / authoritative)
# --------------------------------------------------------------------------- #
def cost_from_usage(model, u):
    p = PRICING[model]
    return (u["input_tokens"] / 1e6 * p["in"]
            + u["output_tokens"] / 1e6 * p["out"]
            + u["cache_write"] / 1e6 * p["cache_write"]
            + u["cache_read"] / 1e6 * p["cache_read"])


def summarize_file(path):
    """Aggregate usage + cost + row count for one output jsonl file."""
    agg = {"rows": 0, "cost": 0.0,
           "usage": {"input_tokens": 0, "output_tokens": 0, "cache_write": 0,
                     "cache_read": 0}}
    if not path.exists():
        return agg
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            agg["rows"] += 1
            u = r.get("usage")
            m = r.get("model")
            if u and m in PRICING:
                for k in agg["usage"]:
                    agg["usage"][k] += u.get(k, 0)
                agg["cost"] += cost_from_usage(m, u)
    return agg


HAIKU_OUT = WORK / "haiku_full.jsonl"
SONNET_OUT = WORK / "sonnet_escalation.jsonl"
COST_TRACKER = WORK / "cost_tracker.json"


def write_cost_tracker(extra=None):
    """Recompute authoritative cumulative cost from BOTH stage output files and
    persist to cost_tracker.json. Returns total cost USD."""
    h = summarize_file(HAIKU_OUT)
    s = summarize_file(SONNET_OUT)
    total = h["cost"] + s["cost"]
    payload = {
        "haiku": {"rows": h["rows"], "cost_usd": round(h["cost"], 4),
                  "usage": h["usage"]},
        "sonnet": {"rows": s["rows"], "cost_usd": round(s["cost"], 4),
                   "usage": s["usage"]},
        "total_cost_usd": round(total, 4),
        "cost_stop_usd": COST_STOP_USD,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        payload.update(extra)
    COST_TRACKER.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return total


def load_done_ids(path):
    done = set()
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                continue
    return done


# --------------------------------------------------------------------------- #
# the resumable runner
# --------------------------------------------------------------------------- #
def run_classification(model, papers, out_path, max_workers=40,
                       checkpoint_every=500, cost_stop_usd=COST_STOP_USD,
                       max_passes=6, label="run"):
    """Classify `papers` (list of {id,title,abstract,hygiene}) with `model`,
    appending one JSON row per paper to out_path. Resumable (skips ids already
    present). Multi-pass: retries hard-failed (missing) papers up to max_passes.
    Stops early if cumulative cost across both stages reaches cost_stop_usd.

    Returns dict(status, done, missing, stopped_for_cost).
    """
    themes, theme_to_domains = load_taxonomy()
    system_prompt = build_system_prompt(themes)
    validator = Validator(theme_to_domains)

    write_lock = threading.Lock()
    counter = {"done_new": 0}
    fh = open(out_path, "a", encoding="utf-8")

    def flush_checkpoint(tag=""):
        fh.flush()
        os.fsync(fh.fileno())
        total = write_cost_tracker()
        print(f"[{label}] {tag} newly_done={counter['done_new']} "
              f"cum_cost=${total:.2f}", flush=True)
        return total

    stopped_for_cost = False
    try:
        for pass_i in range(1, max_passes + 1):
            done = load_done_ids(out_path)
            todo = [p for p in papers if p["id"] not in done]
            if not todo:
                break
            print(f"[{label}] pass {pass_i}: {len(todo)} papers to do "
                  f"({len(done)} already done)", flush=True)

            ex = ThreadPoolExecutor(max_workers=max_workers)
            futs = {ex.submit(classify_task, model, system_prompt, p,
                              validator): p for p in todo}
            since_ckpt = 0
            try:
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        rec = fut.result()
                    except Exception as e:
                        rec = None
                        print(f"[{label}] task error for {p['id']}: {e!r}",
                              flush=True)
                    if rec is not None:
                        with write_lock:
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        counter["done_new"] += 1
                        since_ckpt += 1
                        if since_ckpt >= checkpoint_every:
                            since_ckpt = 0
                            total = flush_checkpoint("checkpoint")
                            if total >= cost_stop_usd:
                                stopped_for_cost = True
                                break
            finally:
                # cancel anything not yet started; wait for in-flight to end
                ex.shutdown(wait=True, cancel_futures=True)
            flush_checkpoint(f"end pass {pass_i}")
            if stopped_for_cost:
                break
    finally:
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    total = write_cost_tracker()
    done = load_done_ids(out_path)
    want = {p["id"] for p in papers}
    missing = want - done
    print(f"[{label}] FINISHED newly_done={counter['done_new']} "
          f"covered={len(want & done)}/{len(want)} missing={len(missing)} "
          f"cum_cost=${total:.2f} stopped_for_cost={stopped_for_cost}", flush=True)
    return {"status": "ok", "done": len(want & done), "missing": sorted(missing),
            "stopped_for_cost": stopped_for_cost, "total_cost": total}
