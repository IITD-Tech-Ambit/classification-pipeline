"""STAGE D step 3-4: v3 agreement analysis + head-to-head vs the v2 baseline.

Compares the v3 final label (classification_v3_final.jsonl) against the
independent claude-sonnet-4-5 v3 label for the fresh 250-paper sample, computes
theme- and domain-agreement overall and per confidence band (same method as the
original gold check), and reports the DELTA versus the baseline
(theme 86.2% / domain 70.5%). Refusals + Sonnet-unclassifiable are excluded from
denominators, not dropped silently.

Writes outputs/goldset_v3_metrics.json + outputs/goldset_v3_report.md.
STAGE D TEST: sample size == labels == comparable counts reconcile.
READ-ONLY DB. No git.
"""
import json
from collections import Counter

from common import OUTPUTS, WORK

SAMPLE_IN = WORK / "goldset_v3_sample.jsonl"
LABELS_IN = WORK / "goldset_v3_sonnet_labels.jsonl"
COST_IN = WORK / "goldset_v3_cost.json"
FINAL_IN = OUTPUTS / "classification_v3_final.jsonl"
BASELINE_IN = WORK / "goldset_metrics.BASELINE-BACKUP.json"

METRICS_OUT = OUTPUTS / "goldset_v3_metrics.json"
REPORT_OUT = OUTPUTS / "goldset_v3_report.md"
BANDS = ["<0.5", "0.5-0.8", ">=0.8"]


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def main():
    sample = {r["id"]: r for r in load_jsonl(SAMPLE_IN)}
    labels = {r["id"]: r for r in load_jsonl(LABELS_IN)}
    want = set(sample)
    final = {}
    with open(FINAL_IN, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                if r["id"] in want:
                    final[r["id"]] = r
    baseline = json.loads(BASELINE_IN.read_text(encoding="utf-8"))

    recs = []
    for pid, s in sample.items():
        lab = labels.get(pid, {})
        fin = final.get(pid, {})
        cur_theme = fin.get("thematic_area", s.get("thematic_area"))
        cur_domain = fin.get("domain", s.get("domain"))
        son_theme = lab.get("thematic_area")
        son_domain = lab.get("domain")
        son_uncl = bool(lab.get("unclassifiable"))
        note = lab.get("schema_note") or ""
        refused = (note == "refusal") or (son_theme is None and not son_uncl
                                          and not lab)
        theme_comparable = (son_theme is not None) and (not son_uncl) and (not refused)
        domain_comparable = bool(lab.get("schema_valid")) and (not son_uncl)
        recs.append({
            "id": pid, "current_theme": cur_theme, "current_domain": cur_domain,
            "confidence": s.get("confidence"), "source_model": s.get("source_model"),
            "band": s.get("band"), "changed_from_v2": s.get("changed_from_v2"),
            "sonnet_theme": son_theme, "sonnet_domain": son_domain,
            "sonnet_unclassifiable": son_uncl, "refused": refused,
            "schema_note": note,
            "theme_comparable": theme_comparable,
            "domain_comparable": domain_comparable,
            "agree_theme": (cur_theme == son_theme) if theme_comparable else None,
            "agree_domain": (cur_domain == son_domain) if domain_comparable else None,
        })

    def stats(subset, key):
        comp = [r for r in subset if r[key] is not None]
        yes = sum(1 for r in comp if r[key])
        return {"n": len(comp), "agree": yes, "pct": pct(yes, len(comp))}

    theme_overall = stats(recs, "agree_theme")
    domain_overall = stats(recs, "agree_domain")
    theme_by_band = {b: stats([r for r in recs if r["band"] == b], "agree_theme")
                     for b in BANDS}
    domain_by_band = {b: stats([r for r in recs if r["band"] == b], "agree_domain")
                      for b in BANDS}
    sources = sorted({r["source_model"] for r in recs if r["source_model"]})
    theme_by_source = {s: stats([r for r in recs if r["source_model"] == s],
                                "agree_theme") for s in sources}
    domain_by_source = {s: stats([r for r in recs if r["source_model"] == s],
                                 "agree_domain") for s in sources}

    both = [r for r in recs if r["agree_theme"] is not None
            and r["agree_domain"] is not None]
    theme_match = [r for r in both if r["agree_theme"]]
    trdw = sum(1 for r in theme_match if not r["agree_domain"])

    theme_conf = Counter()
    dom_dis = Counter()
    for r in recs:
        if r["agree_theme"] is False:
            theme_conf[(r["current_theme"], r["sonnet_theme"])] += 1
        if r["agree_domain"] is False:
            dom_dis[r["current_domain"]] += 1

    refusals = [r["id"] for r in recs if r["refused"]]
    son_uncls = [r["id"] for r in recs if r["sonnet_unclassifiable"]]
    cost = json.loads(COST_IN.read_text(encoding="utf-8")) if COST_IN.exists() else {}

    # baseline
    b_theme = baseline["theme_agreement"]["pct"]
    b_domain = baseline["domain_agreement"]["pct"]
    b_theme_band = {b: baseline["theme_by_band"][b]["pct"] for b in BANDS}
    b_domain_band = {b: baseline["domain_by_band"][b]["pct"] for b in BANDS}

    def delta(a, b):
        return None if (a is None or b is None) else round(a - b, 1)

    metrics = {
        "sample_size": len(recs),
        "sonnet_labeled": len(labels),
        "theme_comparable_n": theme_overall["n"],
        "domain_comparable_n": domain_overall["n"],
        "refusals": refusals,
        "sonnet_unclassifiable": son_uncls,
        "theme_agreement": theme_overall,
        "domain_agreement": domain_overall,
        "theme_by_band": theme_by_band,
        "domain_by_band": domain_by_band,
        "theme_by_source": theme_by_source,
        "domain_by_source": domain_by_source,
        "theme_right_domain_wrong": {"count": trdw,
                                     "pct_of_theme_matches": pct(trdw, len(theme_match)),
                                     "theme_match_n": len(theme_match)},
        "top_theme_confusions": [{"from": k[0], "to": k[1], "count": v}
                                 for k, v in theme_conf.most_common(12)],
        "top_domain_disagreements": [{"current_domain": k, "count": v}
                                     for k, v in dom_dis.most_common(12)],
        "changed_from_v2_in_sample": sum(1 for r in recs if r["changed_from_v2"]),
        "cost_usd": cost.get("cost_usd", 0.0),
        "baseline": {"theme_pct": b_theme, "domain_pct": b_domain,
                     "theme_by_band": b_theme_band, "domain_by_band": b_domain_band},
        "delta_vs_baseline": {
            "theme_pct": delta(theme_overall["pct"], b_theme),
            "domain_pct": delta(domain_overall["pct"], b_domain),
            "theme_by_band": {b: delta(theme_by_band[b]["pct"], b_theme_band[b])
                              for b in BANDS},
            "domain_by_band": {b: delta(domain_by_band[b]["pct"], b_domain_band[b])
                               for b in BANDS},
        },
    }
    METRICS_OUT.write_text(json.dumps(metrics, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    write_report(metrics)
    run_tests(metrics, sample, labels, final)

    d = metrics["delta_vs_baseline"]
    print("\n==== STAGE D SUMMARY (v3 vs v2 baseline) ====")
    print(f"theme  agreement: {theme_overall['pct']}%  (baseline {b_theme}%  "
          f"delta {d['theme_pct']:+})")
    print(f"domain agreement: {domain_overall['pct']}%  (baseline {b_domain}%  "
          f"delta {d['domain_pct']:+})")
    for b in BANDS:
        print(f"  band {b:9} domain {domain_by_band[b]['pct']}% "
              f"(baseline {b_domain_band[b]}%  delta {d['domain_by_band'][b]:+})")
    print(f"refusals: {len(refusals)}  sonnet-uncl: {len(son_uncls)}  "
          f"cost: ${metrics['cost_usd']}")


def write_report(m):
    L = []
    A = L.append
    d = m["delta_vs_baseline"]
    A("# Gold-Set Accuracy Re-Test — Classification v3 (head-to-head vs v2)\n")
    A("_Method identical to the original gold check: an INDEPENDENT "
      "`claude-sonnet-4-5` label (full v3 taxonomy, prompt-cached, blind to the "
      "assigned label) vs the production v3 label, on a FRESH stratified 250-paper "
      "sample (different seed). This is an LLM-vs-LLM agreement PROXY, not human "
      "ground truth._\n")
    A("## Headline: v3 vs v2 baseline\n")
    A("| metric | v2 baseline | v3 | delta |")
    A("|---|---|---|---|")
    A(f"| Theme agreement | {m['baseline']['theme_pct']}% | "
      f"{m['theme_agreement']['pct']}% ({m['theme_agreement']['agree']}/"
      f"{m['theme_agreement']['n']}) | **{d['theme_pct']:+}** |")
    A(f"| Domain agreement | {m['baseline']['domain_pct']}% | "
      f"{m['domain_agreement']['pct']}% ({m['domain_agreement']['agree']}/"
      f"{m['domain_agreement']['n']}) | **{d['domain_pct']:+}** |")
    A("")
    A("## By confidence band\n")
    A("| band | theme v3 (Δ) | domain v3 (Δ) |")
    A("|---|---|---|")
    for b in BANDS:
        A(f"| {b} | {m['theme_by_band'][b]['pct']}% ({d['theme_by_band'][b]:+}) | "
          f"{m['domain_by_band'][b]['pct']}% ({d['domain_by_band'][b]:+}) |")
    A("")
    A("## By source model\n")
    A("| source_model | theme | domain |")
    A("|---|---|---|")
    for s in sorted(m["theme_by_source"]):
        A(f"| {s} | {m['theme_by_source'][s]['pct']}% "
          f"({m['theme_by_source'][s]['agree']}/{m['theme_by_source'][s]['n']}) | "
          f"{m['domain_by_source'][s]['pct']}% "
          f"({m['domain_by_source'][s]['agree']}/{m['domain_by_source'][s]['n']}) |")
    A("")
    tr = m["theme_right_domain_wrong"]
    A(f"- Theme-right / domain-wrong: **{tr['count']}** of {tr['theme_match_n']} "
      f"theme-matches ({tr['pct_of_theme_matches']}%).")
    A(f"- Sample papers whose label changed from v2: "
      f"**{m['changed_from_v2_in_sample']}** / {m['sample_size']}.")
    A(f"- Sonnet refusals (excluded): {len(m['refusals'])}; Sonnet-unclassifiable "
      f"(excluded): {len(m['sonnet_unclassifiable'])}.")
    A(f"- Stage-D cost: ${m['cost_usd']}.\n")
    A("## Top theme disagreements (v3 current -> sonnet)\n")
    A("| current theme | sonnet theme | count |")
    A("|---|---|---:|")
    for c in m["top_theme_confusions"]:
        A(f"| {c['from']} | {c['to']} | {c['count']} |")
    A("")
    A("## Domains with most disagreement (v3)\n")
    A("| current domain | disagreements |")
    A("|---|---:|")
    for c in m["top_domain_disagreements"]:
        A(f"| {c['current_domain']} | {c['count']} |")
    A("")
    REPORT_OUT.write_text("\n".join(L), encoding="utf-8")


def run_tests(m, sample, labels, final):
    print("\n==== STAGE D TESTS ====")
    errors = []
    if not (m["sample_size"] == len(sample)):
        errors.append(f"sample size mismatch: recs={m['sample_size']} "
                      f"sample={len(sample)}")
    for pid in sample:
        if pid not in final:
            errors.append(f"sample id missing from v3 final: {pid}")
        if pid not in labels:
            errors.append(f"sample id has no sonnet label: {pid}")
    # comparable + refusals + uncl must account for all
    print(f"sample={len(sample)} labels={len(labels)} recs={m['sample_size']}")
    print(f"theme_comparable={m['theme_comparable_n']} "
          f"domain_comparable={m['domain_comparable_n']} "
          f"refusals={len(m['refusals'])} sonnet_uncl={len(m['sonnet_unclassifiable'])}")
    if errors:
        print("TESTS FAILED:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    print("STAGE D TESTS PASSED")


if __name__ == "__main__":
    main()
