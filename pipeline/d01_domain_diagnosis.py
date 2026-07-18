"""Domain-level diagnosis for classification-v2. Analysis only: no API, no DB writes.

Builds:
  - domain confusion map from the 250-paper gold sample (prod label vs Sonnet label)
  - trouble-domain ranking, split by confidence band
  - corpus-wide pressure/impact sizing for trouble domains
  - reconciliation against goldset_metrics.json

Outputs JSON to outputs/work/domain_diagnosis.json (the .md is written by hand).
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
WORK = OUT / "work"


def load_jsonl(p):
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def band_of(c):
    if c is None:
        return "unknown"
    if c < 0.5:
        return "<0.5"
    if c < 0.8:
        return "0.5-0.8"
    return ">=0.8"


# ---- Build domain->theme map from taxonomy ----
tax = json.loads((OUT / "taxonomy-draft-v2.json").read_text(encoding="utf-8"))


def build_domain_theme():
    d2t = {}
    themes = tax.get("themes") or tax.get("thematic_areas") or []
    for th in themes:
        tname = th.get("name") or th.get("theme")
        for dom in th.get("domains", []):
            dname = dom.get("name") if isinstance(dom, dict) else dom
            d2t[dname] = tname
    return d2t


d2t = build_domain_theme()

# ---- Load gold sample + sonnet ----
prod = {r["id"]: r for r in load_jsonl(WORK / "goldset_sample.jsonl")}
son = {r["id"]: r for r in load_jsonl(WORK / "goldset_sonnet_labels.jsonl")}

refusals = set()
son_unclass = set()

pairs = []  # comparable rows (both have domain, sonnet not refusal/unclassifiable)
theme_comparable = 0
theme_agree = 0
domain_comparable = 0
domain_agree = 0

# Valid domain names per theme, to mirror the metrics script's schema check.
valid_domains_of_theme = defaultdict(set)
for dname, tname in d2t.items():
    valid_domains_of_theme[tname].add(dname)

for pid, pr in prod.items():
    sr = son.get(pid)
    if sr is None:
        continue
    # A true refusal = no usable theme label at all.
    if sr.get("thematic_area") in (None, ""):
        refusals.add(pid)
        continue
    if sr.get("unclassifiable"):
        son_unclass.add(pid)
        continue
    p_theme = pr["thematic_area"]
    s_theme = sr["thematic_area"]
    p_dom = pr.get("domain")
    s_dom = sr.get("domain")
    conf = pr.get("confidence")
    band = pr.get("band") or band_of(conf)

    # Theme is comparable whenever Sonnet gave a theme (even if its domain was
    # off-theme / schema-invalid).
    theme_comparable += 1
    if p_theme == s_theme:
        theme_agree += 1

    # Domain is comparable only when Sonnet's domain is schema-valid within the
    # theme it chose (matches the metrics script; those off-theme-domain rows are
    # excluded from the domain denominator).
    domain_valid = (
        sr.get("schema_valid") is not False
        and s_dom in valid_domains_of_theme.get(s_theme, set())
    )
    if p_dom and s_dom and domain_valid:
        domain_comparable += 1
        agree = (p_dom == s_dom)
        if agree:
            domain_agree += 1
        pairs.append({
            "id": pid,
            "p_theme": p_theme, "s_theme": s_theme,
            "p_dom": p_dom, "s_dom": s_dom,
            "conf": conf, "band": band,
            "source_model": pr.get("source_model"),
            "agree": agree,
            "cross_theme": p_theme != s_theme,
        })

disagreements = [p for p in pairs if not p["agree"]]

# ---- Domain->domain disagreement pairs ----
pair_counter = Counter()
pair_kind = {}  # pair -> "within-theme" or "cross-theme"
for d in disagreements:
    key = (d["p_dom"], d["s_dom"])
    pair_counter[key] += 1
    # a given ordered pair is consistently within/cross theme
    pair_kind[key] = "cross-theme" if d["p_dom"] and (d2t.get(d["p_dom"]) != d2t.get(d["s_dom"])) else "within-theme"

top_pairs = []
for (pd_, sd_), cnt in pair_counter.most_common():
    top_pairs.append({
        "prod_domain": pd_,
        "sonnet_domain": sd_,
        "prod_theme": d2t.get(pd_, "?"),
        "sonnet_theme": d2t.get(sd_, "?"),
        "kind": pair_kind[(pd_, sd_)],
        "count": cnt,
    })

# ---- Trouble domains (either side of a disagreement) ----
trouble = Counter()
trouble_asprod = Counter()
trouble_asson = Counter()
for d in disagreements:
    trouble[d["p_dom"]] += 1
    trouble[d["s_dom"]] += 1
    trouble_asprod[d["p_dom"]] += 1
    trouble_asson[d["s_dom"]] += 1

trouble_rows = []
for dom, tot in trouble.most_common():
    trouble_rows.append({
        "domain": dom,
        "theme": d2t.get(dom, "?"),
        "total_involved": tot,
        "as_prod_side": trouble_asprod.get(dom, 0),
        "as_sonnet_side": trouble_asson.get(dom, 0),
    })

# ---- Split disagreements by confidence band ----
band_break = defaultdict(lambda: {"disagree": 0, "total": 0})
for p in pairs:
    band_break[p["band"]]["total"] += 1
    if not p["agree"]:
        band_break[p["band"]]["disagree"] += 1

# trouble domains by band (as prod side)
trouble_by_band = defaultdict(lambda: Counter())
for d in disagreements:
    trouble_by_band[d["band"]][d["p_dom"]] += 1

# ---- Corpus-wide pressure sizing ----
corpus = load_jsonl(OUT / "classification_v2_final.jsonl")
corpus_dom_counts = Counter()
corpus_dom_bandconf = defaultdict(lambda: {"<0.5": 0, "0.5-0.8": 0, ">=0.8": 0, "sum_conf": 0.0, "n": 0})
n_classified = 0
n_unclassifiable = 0
for r in corpus:
    if r.get("unclassifiable"):
        n_unclassifiable += 1
        continue
    dom = r.get("domain")
    if not dom:
        continue
    n_classified += 1
    corpus_dom_counts[dom] += 1
    b = band_of(r.get("confidence"))
    prof = corpus_dom_bandconf[dom]
    prof[b] += 1
    prof["sum_conf"] += (r.get("confidence") or 0.0)
    prof["n"] += 1

# ---- Impact sizing / leverage for trouble domains ----
# disagreement rate for a domain = (times it was the prod side of a disagreement) / (times it appeared as prod side in gold sample)
prod_side_total = Counter()  # domain appearances as prod label in comparable gold rows
for p in pairs:
    prod_side_total[p["p_dom"]] += 1

leverage_rows = []
for dom, tot in trouble.most_common():
    corpus_n = corpus_dom_counts.get(dom, 0)
    gold_prod_n = prod_side_total.get(dom, 0)
    dis_as_prod = trouble_asprod.get(dom, 0)
    dis_rate = (dis_as_prod / gold_prod_n) if gold_prod_n else None
    prof = corpus_dom_bandconf.get(dom, {})
    mean_conf = (prof.get("sum_conf", 0) / prof["n"]) if prof.get("n") else None
    lowmid = prof.get("<0.5", 0) + prof.get("0.5-0.8", 0)
    leverage = (corpus_n * dis_rate) if dis_rate is not None else None
    leverage_rows.append({
        "domain": dom,
        "theme": d2t.get(dom, "?"),
        "corpus_papers": corpus_n,
        "corpus_lt0.8": lowmid,
        "corpus_mean_conf": round(mean_conf, 3) if mean_conf is not None else None,
        "gold_prod_appearances": gold_prod_n,
        "gold_disagree_as_prod": dis_as_prod,
        "disagree_rate_as_prod": round(dis_rate, 3) if dis_rate is not None else None,
        "leverage_est_papers": round(leverage, 1) if leverage is not None else None,
    })

leverage_rows_sorted = sorted(
    leverage_rows,
    key=lambda x: (x["leverage_est_papers"] is not None, x["leverage_est_papers"] or 0),
    reverse=True,
)

# ---- Reconcile with goldset_metrics.json ----
gm = json.loads((WORK / "goldset_metrics.json").read_text(encoding="utf-8"))
recon = {
    "computed": {
        "theme_comparable_n": theme_comparable,
        "theme_agree": theme_agree,
        "theme_pct": round(100 * theme_agree / theme_comparable, 1) if theme_comparable else None,
        "domain_comparable_n": domain_comparable,
        "domain_agree": domain_agree,
        "domain_pct": round(100 * domain_agree / domain_comparable, 1) if domain_comparable else None,
        "refusals": len(refusals),
        "sonnet_unclassifiable": len(son_unclass),
    },
    "reported": {
        "theme_comparable_n": gm["theme_comparable_n"],
        "theme_pct": gm["theme_agreement"]["pct"],
        "domain_comparable_n": gm["domain_comparable_n"],
        "domain_pct": gm["domain_agreement"]["pct"],
        "refusals": len(gm["refusals"]),
        "sonnet_unclassifiable": len(gm["sonnet_unclassifiable"]),
    },
}

result = {
    "n_disagreements": len(disagreements),
    "n_comparable_pairs": len(pairs),
    "band_breakdown": {k: v for k, v in band_break.items()},
    "top_domain_pairs": top_pairs,
    "trouble_domains": trouble_rows,
    "trouble_by_band": {b: dict(c.most_common()) for b, c in trouble_by_band.items()},
    "leverage_ranked": leverage_rows_sorted,
    "corpus_totals": {
        "n_rows": len(corpus),
        "n_classified": n_classified,
        "n_unclassifiable": n_unclassifiable,
    },
    "reconciliation": recon,
    "disagreement_ids": {
        f"{d['p_dom']} -> {d['s_dom']}": []
        for d in disagreements
    },
}
# attach ids per pair for later Mongo lookup
ids_by_pair = defaultdict(list)
for d in disagreements:
    ids_by_pair[f"{d['p_dom']} => {d['s_dom']}"].append(d["id"])
result["ids_by_pair"] = dict(ids_by_pair)

(WORK / "domain_diagnosis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

# ---- Console summary ----
print("== RECONCILIATION ==")
print(json.dumps(recon, indent=2))
print("\n== TOP 15 DOMAIN DISAGREEMENT PAIRS ==")
for p in top_pairs[:15]:
    print(f"{p['count']:>2}  [{p['kind']}]  {p['prod_domain']}  ->  {p['sonnet_domain']}")
print("\n== TROUBLE DOMAINS (top 15 by involvement) ==")
for t in trouble_rows[:15]:
    print(f"{t['total_involved']:>2}  (prod {t['as_prod_side']}, son {t['as_sonnet_side']})  {t['domain']}  [{t['theme']}]")
print("\n== BAND BREAKDOWN ==")
for b in ["<0.5", "0.5-0.8", ">=0.8", "unknown"]:
    if b in band_break:
        v = band_break[b]
        pct = round(100 * v["disagree"] / v["total"], 1) if v["total"] else 0
        print(f"{b}: {v['disagree']}/{v['total']} disagree ({pct}%)")
print("\n== TOP 15 LEVERAGE (corpus_papers x disagree_rate) ==")
for l in leverage_rows_sorted[:15]:
    print(f"{str(l['leverage_est_papers']):>7}  n={l['corpus_papers']:>5}  rate={l['disagree_rate_as_prod']}  <0.8={l['corpus_lt0.8']:>5}  meanconf={l['corpus_mean_conf']}  {l['domain']}")
print("\nwrote", WORK / "domain_diagnosis.json")
