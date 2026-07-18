"""Cross/within-theme split, corpus confidence distribution, and re-pass cost model.
Analysis only; no API, no DB writes. Prices reconciled from outputs/work/cost_tracker.json.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
WORK = OUT / "work"


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def band_of(c):
    if c is None:
        return "unknown"
    if c < 0.5:
        return "<0.5"
    if c < 0.8:
        return "0.5-0.8"
    return ">=0.8"


dd = json.loads((WORK / "domain_diagnosis.json").read_text(encoding="utf-8"))
tax = json.loads((OUT / "taxonomy-draft-v2.json").read_text(encoding="utf-8"))
d2t = {}
for th in tax["themes"]:
    for dom in th["domains"]:
        d2t[dom["name"]] = th["name"]

# ---- cross vs within-theme split of the 70 disagreements ----
cross = within = 0
cross_by_band = Counter()
within_by_band = Counter()
prod = {r["id"]: r for r in load_jsonl(WORK / "goldset_sample.jsonl")}
son = {r["id"]: r for r in load_jsonl(WORK / "goldset_sonnet_labels.jsonl")}
for pair, ids in dd["ids_by_pair"].items():
    p_dom, s_dom = pair.split(" => ")
    is_cross = d2t.get(p_dom) != d2t.get(s_dom)
    for pid in ids:
        band = prod[pid].get("band") or band_of(prod[pid].get("confidence"))
        if is_cross:
            cross += 1
            cross_by_band[band] += 1
        else:
            within += 1
            within_by_band[band] += 1

# ---- corpus confidence distribution ----
corpus = load_jsonl(OUT / "classification_v2_final.jsonl")
n_total = len(corpus)
n_unclass = sum(1 for r in corpus if r.get("unclassifiable"))
classified = [r for r in corpus if not r.get("unclassifiable") and r.get("domain")]
n_classified = len(classified)
band_counts = Counter(band_of(r.get("confidence")) for r in classified)
n_lt08 = band_counts["<0.5"] + band_counts["0.5-0.8"]

# ---- per-paper cost model (domain-only re-pass, prompt-cached one-theme taxonomy) ----
# tokens per paper (assumptions), varied low/high
scenarios = {
    "low":  {"cache_read": 1200, "input": 400, "output": 80},
    "high": {"cache_read": 1800, "input": 650, "output": 130},
}
PRICE = {  # $ per token
    "haiku":  {"input": 1.0/1e6, "output": 5.0/1e6, "cache_read": 0.10/1e6},
    "sonnet": {"input": 3.0/1e6, "output": 15.0/1e6, "cache_read": 0.30/1e6},
}


def per_paper(model, sc):
    p = PRICE[model]
    return sc["cache_read"] * p["cache_read"] + sc["input"] * p["input"] + sc["output"] * p["output"]


cost_rows = []
for model in ("haiku", "sonnet"):
    lo = per_paper(model, scenarios["low"])
    hi = per_paper(model, scenarios["high"])
    cost_rows.append({
        "model": model,
        "per_paper_low": round(lo, 5),
        "per_paper_high": round(hi, 5),
        "lt08_low": round(lo * n_lt08, 1),
        "lt08_high": round(hi * n_lt08, 1),
        "whole_low": round(lo * n_classified, 1),
        "whole_high": round(hi * n_classified, 1),
    })

out = {
    "disagreements_total": within + cross,
    "within_theme": within,
    "cross_theme": cross,
    "within_by_band": dict(within_by_band),
    "cross_by_band": dict(cross_by_band),
    "corpus": {
        "n_total_rows": n_total,
        "n_unclassifiable": n_unclass,
        "n_classified": n_classified,
        "band_counts": dict(band_counts),
        "n_lt08": n_lt08,
        "pct_lt08": round(100 * n_lt08 / n_classified, 1),
    },
    "cost_model": {
        "prices_per_million": {"haiku": "in $1 / out $5 / cacheRead $0.10",
                                "sonnet": "in $3 / out $15 / cacheRead $0.30"},
        "token_assumptions": scenarios,
        "rows": cost_rows,
    },
}
(WORK / "domain_costs.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
