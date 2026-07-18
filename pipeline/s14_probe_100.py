"""Step 14 (classification-v2): 100-paper Step-3 classification probe.

Go/no-go gate before the full Step-3 pilot. Samples 100 random eligible papers
(hygiene ok / title_only), classifies each with claude-haiku-4-5 against the FROZEN
v2 taxonomy (9 themes -> 76 domains) using a prompt-cached system block, validates
the output schema (theme in the 9, domain within that theme), runs two cheap
cross-checks (bge-large nearest-theme centroid + legacy v1 theme from Mongo), and
writes machine-readable + human-review deliverables.

READ-ONLY DB access. Does not modify the taxonomy.

Outputs:
  outputs/probe_100_results.jsonl
  outputs/probe_100_review.md
  outputs/work/probe_100_usage.json
  outputs/work/probe_100_sample_ids.json
"""
import json
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from bson import ObjectId

import anthropic

from common import get_db, OUTPUTS, WORK

MODEL = "claude-haiku-4-5"
# claude-haiku-4-5 pricing (USD per million tokens)
PRICE_IN = 1.00
PRICE_OUT = 5.00
PRICE_CACHE_WRITE = 1.25
PRICE_CACHE_READ = 0.10

SEED = 42
N_TOTAL = 100
N_TITLE_ONLY_TARGET = 10
MAX_WORKERS = 6
CONF_LOW = 0.5

TAXONOMY_PATH = OUTPUTS / "taxonomy-draft-v2.json"
NPZ_PATH = WORK / "paper_embeddings_bge_large.npz"
HYGIENE_PATH = WORK / "hygiene_flags.jsonl"
THEME_CORRECTED_PATH = WORK / "theme_corrected.json"

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# --------------------------------------------------------------------------- #
# Taxonomy -> cached system prompt
# --------------------------------------------------------------------------- #
def load_taxonomy():
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    themes = tax["themes"]
    id_to_name = {t["id"]: t["name"] for t in themes}
    theme_to_domains = {t["name"]: [d["name"] for d in t["domains"]] for t in themes}
    return themes, id_to_name, theme_to_domains


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


# --------------------------------------------------------------------------- #
# usage accounting
# --------------------------------------------------------------------------- #
_usage_lock = threading.Lock()
_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0,
          "calls": 0, "cached_calls": 0}


def _add_usage(u):
    with _usage_lock:
        _usage["input_tokens"] += u.input_tokens
        _usage["output_tokens"] += u.output_tokens
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        _usage["cache_write"] += cw
        _usage["cache_read"] += cr
        _usage["calls"] += 1
        if cr > 0:
            _usage["cached_calls"] += 1


def parse_json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[s:e + 1])


def classify_one(system_prompt, paper):
    prompt = ("Classify this paper. Return the JSON object only.\n\n"
              + paper_text(paper["title"], paper["abstract"]))
    last_err = None
    for attempt in range(6):
        try:
            resp = _client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=[{"type": "text", "text": system_prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            _add_usage(resp.usage)
            raw = resp.content[0].text.strip()
            try:
                obj = parse_json(raw)
                return obj, raw, None
            except Exception as e:
                return None, raw, f"json_parse_error: {e}"
        except (anthropic.RateLimitError, anthropic.APIStatusError,
                anthropic.APIConnectionError) as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    return None, "", f"api_error: {last_err}"


# --------------------------------------------------------------------------- #
# sampling
# --------------------------------------------------------------------------- #
def sample_papers(rng):
    ok, title_only = [], []
    with open(HYGIENE_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["status"] == "ok":
                ok.append(r["_id"])
            elif r["status"] == "title_only":
                title_only.append(r["_id"])
    ok.sort()
    title_only.sort()
    n_to = min(N_TITLE_ONLY_TARGET, len(title_only))
    n_ok = N_TOTAL - n_to
    pick_ok = rng.choice(len(ok), size=n_ok, replace=False)
    pick_to = rng.choice(len(title_only), size=n_to, replace=False)
    sel = [(ok[i], "ok") for i in pick_ok] + [(title_only[i], "title_only") for i in pick_to]
    rng.shuffle(sel)
    return sel


# --------------------------------------------------------------------------- #
# embedding cross-check: bge-large nearest-theme centroid
# --------------------------------------------------------------------------- #
def build_theme_centroids(id_to_name):
    """Average bge-large embeddings per v2 theme using theme_corrected.json labels."""
    z = np.load(NPZ_PATH, allow_pickle=True)
    ids = [str(x) for x in z["ids"]]
    emb = z["emb"].astype(np.float32)
    id_to_row = {pid: i for i, pid in enumerate(ids)}

    tc = json.loads(THEME_CORRECTED_PATH.read_text(encoding="utf-8"))["assignments"]
    buckets = defaultdict(list)
    for pid, a in tc.items():
        v2 = a.get("v2")
        if v2 in id_to_name and pid in id_to_row:
            buckets[v2].append(id_to_row[pid])

    centroids = {}   # theme_id -> unit vector
    for tid, rows in buckets.items():
        v = emb[rows].mean(axis=0)
        n = np.linalg.norm(v)
        if n > 0:
            centroids[tid] = v / n
    return id_to_row, emb, centroids


def nearest_theme(emb_row, centroids, id_to_name):
    best_tid, best_sim = None, -2.0
    for tid, c in centroids.items():
        sim = float(np.dot(emb_row, c))
        if sim > best_sim:
            best_sim, best_tid = sim, tid
    return id_to_name.get(best_tid), round(best_sim, 3)


# --------------------------------------------------------------------------- #
def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def main():
    rng = np.random.default_rng(SEED)
    themes, id_to_name, theme_to_domains = load_taxonomy()
    theme_names = list(theme_to_domains.keys())
    norm_theme = {norm(n): n for n in theme_names}
    norm_domain = {tn: {norm(d): d for d in doms} for tn, doms in theme_to_domains.items()}

    system_prompt = build_system_prompt(themes)
    print(f"system prompt chars: {len(system_prompt)}")

    sel = sample_papers(rng)
    sel_ids = [pid for pid, _ in sel]
    hyg_by_id = dict(sel)
    (WORK / "probe_100_sample_ids.json").write_text(
        json.dumps({"seed": SEED, "ids": sel_ids, "hygiene": hyg_by_id}, indent=2),
        encoding="utf-8")
    print(f"sampled {len(sel)} papers "
          f"({sum(1 for _,s in sel if s=='ok')} ok / "
          f"{sum(1 for _,s in sel if s=='title_only')} title_only)")

    # pull title+abstract + v1 theme from Mongo
    db = get_db()
    coll = db.researchmetadatascopus
    oids = [ObjectId(x) for x in sel_ids]
    docs = {}
    for d in coll.find({"_id": {"$in": oids}},
                       {"title": 1, "abstract": 1, "classification.thematic_area_id": 1}):
        docs[str(d["_id"])] = d

    papers = []
    for pid in sel_ids:
        d = docs.get(pid, {})
        v1_tid = None
        cl = d.get("classification") or {}
        if cl.get("thematic_area_id") is not None:
            v1_tid = str(cl["thematic_area_id"])
        papers.append({
            "id": pid,
            "title": d.get("title") or "",
            "abstract": d.get("abstract") or "",
            "hygiene": hyg_by_id[pid],
            "v1_theme": id_to_name.get(v1_tid),
        })

    # embedding cross-check setup
    print("building bge-large theme centroids ...")
    id_to_row, emb, centroids = build_theme_centroids(id_to_name)
    print(f"  centroids for {len(centroids)} themes")

    # classify (concurrent)
    print("classifying ...")
    t0 = time.time()
    results_by_id = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(classify_one, system_prompt, p): p for p in papers}
        done = 0
        for fut in as_completed(futs):
            p = futs[fut]
            obj, raw, err = fut.result()
            results_by_id[p["id"]] = (obj, raw, err)
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(papers)}", flush=True)
    print(f"classified in {time.time()-t0:.0f}s")

    # assemble + validate
    records = []
    for p in papers:
        obj, raw, err = results_by_id[p["id"]]
        theme = domain = reason = None
        confidence = None
        unclassifiable = False
        schema_valid = False
        schema_note = ""

        if obj is None:
            schema_note = err or "no_object"
        else:
            theme = obj.get("thematic_area")
            domain = obj.get("domain")
            reason = obj.get("reason")
            confidence = obj.get("confidence")
            unclassifiable = bool(obj.get("unclassifiable", False))
            # normalize/validate theme
            canon_theme = norm_theme.get(norm(theme))
            if unclassifiable:
                schema_valid = True
                schema_note = "unclassifiable"
                if canon_theme:
                    theme = canon_theme
            elif canon_theme is None:
                schema_note = f"theme_not_in_taxonomy:{theme!r}"
            else:
                theme = canon_theme
                canon_domain = norm_domain[canon_theme].get(norm(domain))
                if canon_domain is None:
                    schema_note = f"domain_not_in_theme:{domain!r}"
                else:
                    domain = canon_domain
                    schema_valid = True
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None

        # embedding cross-check
        row = id_to_row.get(p["id"])
        emb_theme, emb_sim = (None, None)
        if row is not None and centroids:
            emb_theme, emb_sim = nearest_theme(emb[row], centroids, id_to_name)

        cross_notes = []
        agree_v1 = None
        if p["v1_theme"] and theme and not unclassifiable:
            agree_v1 = (p["v1_theme"] == theme)
            cross_notes.append(f"v1={'match' if agree_v1 else 'DIFF'}({p['v1_theme']})")
        elif p["v1_theme"]:
            cross_notes.append(f"v1={p['v1_theme']}")
        agree_emb = None
        if emb_theme and theme and not unclassifiable:
            agree_emb = (emb_theme == theme)
            cross_notes.append(
                f"emb={'match' if agree_emb else 'DIFF'}({emb_theme},sim={emb_sim})")

        flags = []
        if not schema_valid:
            flags.append("SCHEMA_VIOLATION")
        if unclassifiable:
            flags.append("UNCLASSIFIABLE")
        if confidence is not None and confidence < CONF_LOW and not unclassifiable:
            flags.append("LOW_CONF")
        if agree_v1 is False:
            flags.append("DISAGREES_V1")

        records.append({
            "id": p["id"],
            "title": p["title"],
            "abstract_snippet": (p["abstract"][:200] + ("..." if len(p["abstract"]) > 200 else "")),
            "hygiene": p["hygiene"],
            "haiku_theme": theme,
            "haiku_domain": domain,
            "confidence": confidence,
            "unclassifiable": unclassifiable,
            "reason": reason,
            "schema_valid": schema_valid,
            "schema_note": schema_note,
            "v1_theme": p["v1_theme"],
            "agree_v1_theme": agree_v1,
            "emb_nearest_theme": emb_theme,
            "emb_sim": emb_sim,
            "agree_emb_theme": agree_emb,
            "cross_check_note": "; ".join(cross_notes),
            "flags": flags,
            "raw": raw,
        })

    write_outputs(records, theme_names)
    write_usage(t0)
    print("\nDONE. See outputs/probe_100_review.md and outputs/probe_100_results.jsonl")


def write_usage(t0):
    cost = (
        _usage["input_tokens"] / 1e6 * PRICE_IN
        + _usage["output_tokens"] / 1e6 * PRICE_OUT
        + _usage["cache_write"] / 1e6 * PRICE_CACHE_WRITE
        + _usage["cache_read"] / 1e6 * PRICE_CACHE_READ
    )
    payload = dict(_usage)
    payload["est_cost_usd"] = round(cost, 4)
    payload["elapsed_s"] = round(time.time() - t0, 1)
    payload["caching_engaged"] = _usage["cache_read"] > 0
    (WORK / "probe_100_usage.json").write_text(json.dumps(payload, indent=2),
                                               encoding="utf-8")
    print("\nUSAGE:", json.dumps(payload))


def write_outputs(records, theme_names):
    # jsonl
    jpath = OUTPUTS / "probe_100_results.jsonl"
    with open(jpath, "w", encoding="utf-8") as fh:
        for r in records:
            out = {k: v for k, v in r.items() if k != "raw"}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")

    # summary stats
    n = len(records)
    theme_dist = Counter(r["haiku_theme"] for r in records if not r["unclassifiable"])
    n_schema_viol = sum(1 for r in records if not r["schema_valid"])
    n_unclass = sum(1 for r in records if r["unclassifiable"])
    confs = [r["confidence"] for r in records if r["confidence"] is not None]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else None
    v1_pairs = [r for r in records if r["agree_v1_theme"] is not None]
    v1_agree = sum(1 for r in v1_pairs if r["agree_v1_theme"])
    pct_v1 = round(100 * v1_agree / len(v1_pairs), 1) if v1_pairs else None
    emb_pairs = [r for r in records if r["agree_emb_theme"] is not None]
    emb_agree = sum(1 for r in emb_pairs if r["agree_emb_theme"])
    pct_emb = round(100 * emb_agree / len(emb_pairs), 1) if emb_pairs else None

    # confidence histogram
    bins = [0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0001]
    labels = ["<0.5", "0.5-0.7", "0.7-0.8", "0.8-0.9", "0.9-0.95", "0.95-1.0"]
    hist = [0] * len(labels)
    for c in confs:
        for i in range(len(labels)):
            if bins[i] <= c < bins[i + 1]:
                hist[i] += 1
                break

    L = []
    L.append("# 100-Paper Classification Probe — Human Review\n")
    L.append(f"_Model: `{MODEL}` · frozen taxonomy v2 (9 themes / 76 domains) · "
             f"seed {SEED} · one request per paper, prompt-cached taxonomy._\n")
    L.append("## Summary stats\n")
    L.append(f"- Papers classified: **{n}**")
    L.append(f"- Schema violations (theme/domain invalid or unparseable JSON): "
             f"**{n_schema_viol}**")
    L.append(f"- Unclassifiable: **{n_unclass}**")
    L.append(f"- Mean confidence: **{mean_conf}**")
    if pct_v1 is not None:
        L.append(f"- Agreement with v1 theme (where v1 present, {len(v1_pairs)} papers): "
                 f"**{pct_v1}%** ({v1_agree}/{len(v1_pairs)})")
    if pct_emb is not None:
        L.append(f"- Agreement with bge-large nearest-theme centroid "
                 f"({len(emb_pairs)} papers): **{pct_emb}%** ({emb_agree}/{len(emb_pairs)})")
    L.append("")
    L.append("### Confidence histogram\n")
    L.append("| bucket | count |")
    L.append("|---|---|")
    for lab, cnt in zip(labels, hist):
        L.append(f"| {lab} | {cnt} |")
    L.append("")
    L.append("### Theme distribution (Haiku assignments)\n")
    L.append("| theme | count |")
    L.append("|---|---|")
    for t in theme_names:
        L.append(f"| {t} | {theme_dist.get(t, 0)} |")
    if n_unclass:
        L.append(f"| _(unclassifiable)_ | {n_unclass} |")
    L.append("")

    # grouped detail tables
    L.append("## Papers grouped by assigned theme\n")
    order = [t for t in theme_names if theme_dist.get(t, 0) > 0]
    grouped = defaultdict(list)
    for r in records:
        key = r["haiku_theme"] if (r["haiku_theme"] and not r["unclassifiable"]) else "UNCLASSIFIABLE / INVALID"
        grouped[key].append(r)

    def render_group(title, rows):
        L.append(f"### {title}  ({len(rows)})\n")
        L.append("| # | Title | Abstract snippet | Domain | Conf | Flags | Cross-check |")
        L.append("|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            title_c = r["title"].replace("|", "\\|")
            snip = r["abstract_snippet"].replace("|", "\\|").replace("\n", " ")
            dom = (r["haiku_domain"] or "").replace("|", "\\|")
            conf = r["confidence"] if r["confidence"] is not None else "-"
            flags = ", ".join(r["flags"]) or "-"
            cc = r["cross_check_note"].replace("|", "\\|") or "-"
            L.append(f"| {i} | {title_c} | {snip} | {dom} | {conf} | {flags} | {cc} |")
        L.append("")

    for t in order:
        render_group(t, grouped[t])
    if grouped.get("UNCLASSIFIABLE / INVALID"):
        render_group("UNCLASSIFIABLE / INVALID", grouped["UNCLASSIFIABLE / INVALID"])

    (OUTPUTS / "probe_100_review.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
