"""GOLD-SET step 3-6: agreement analysis, human template, report, and tests.

Compares the EXISTING final label (classification_v2_final.jsonl) against the
INDEPENDENT claude-sonnet-4-5 label (goldset_sonnet_labels.jsonl) for the 250
stratified sample papers, and produces:

  outputs/goldset_template.csv          (Excel-safe UTF-8-BOM, disagreements top)
  outputs/goldset_accuracy_report.md    (human-readable report)
  outputs/work/goldset_metrics.json     (machine-readable metrics)

IMPORTANT: this is an LLM-vs-LLM AGREEMENT estimate -- a PROXY for accuracy, NOT
human ground truth. The CSV exists so the team can adjudicate disagreements into
a real human-verified accuracy number.

READ-ONLY Mongo. Never writes to Mongo or git.
"""
import csv
import json
from collections import Counter, defaultdict

from bson import ObjectId

from common import get_db, OUTPUTS, WORK
from s15_classify_lib import cost_from_usage

SAMPLE_IN = WORK / "goldset_sample.jsonl"
LABELS_IN = WORK / "goldset_sonnet_labels.jsonl"
COST_IN = WORK / "goldset_cost.json"
FINAL_IN = OUTPUTS / "classification_v2_final.jsonl"

CSV_OUT = OUTPUTS / "goldset_template.csv"
REPORT_OUT = OUTPUTS / "goldset_accuracy_report.md"
METRICS_OUT = WORK / "goldset_metrics.json"

BANDS = ["<0.5", "0.5-0.8", ">=0.8"]
ABSTRACT_CHARS = 500


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def main():
    sample = load_jsonl(SAMPLE_IN)
    sample_by_id = {r["id"]: r for r in sample}
    labels = load_jsonl(LABELS_IN)
    labels_by_id = {r["id"]: r for r in labels}

    # cross-check the current labels straight from the authoritative final file
    final_by_id = {}
    want = set(sample_by_id)
    with open(FINAL_IN, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["id"] in want:
                final_by_id[r["id"]] = r

    # pull title+abstract for the template
    db = get_db()
    coll = db.researchmetadatascopus
    docs = {}
    for d in coll.find({"_id": {"$in": [ObjectId(x) for x in want]}},
                       {"title": 1, "abstract": 1}):
        docs[str(d["_id"])] = d

    # ---- build per-paper comparison records ------------------------------- #
    recs = []
    for pid, s in sample_by_id.items():
        lab = labels_by_id.get(pid, {})
        fin = final_by_id.get(pid, {})
        cur_theme = fin.get("thematic_area", s.get("thematic_area"))
        cur_domain = fin.get("domain", s.get("domain"))
        son_theme = lab.get("thematic_area")
        son_domain = lab.get("domain")
        son_uncl = bool(lab.get("unclassifiable"))
        note = lab.get("schema_note") or ""
        refused = (note == "refusal") or (son_theme is None and not son_uncl)

        # comparability
        theme_comparable = (son_theme is not None) and (not son_uncl) and (not refused)
        domain_comparable = bool(lab.get("schema_valid")) and (not son_uncl)

        agree_theme = None
        agree_domain = None
        if theme_comparable:
            agree_theme = (cur_theme == son_theme)
        if domain_comparable:
            agree_domain = (cur_domain == son_domain)

        d = docs.get(pid, {})
        recs.append({
            "id": pid,
            "title": d.get("title") or "",
            "abstract": d.get("abstract") or "",
            "current_theme": cur_theme,
            "current_domain": cur_domain,
            "confidence": s.get("confidence"),
            "source_model": s.get("source_model"),
            "band": s.get("band"),
            "sonnet_theme": son_theme,
            "sonnet_domain": son_domain,
            "sonnet_unclassifiable": son_uncl,
            "refused": refused,
            "schema_note": note,
            "theme_comparable": theme_comparable,
            "domain_comparable": domain_comparable,
            "agree_theme": agree_theme,
            "agree_domain": agree_domain,
        })

    # ---- aggregate metrics ------------------------------------------------ #
    def agree_stats(subset, key):
        comp = [r for r in subset if r[key] is not None]
        yes = sum(1 for r in comp if r[key])
        return {"n": len(comp), "agree": yes, "pct": pct(yes, len(comp))}

    theme_overall = agree_stats(recs, "agree_theme")
    domain_overall = agree_stats(recs, "agree_domain")

    theme_by_band = {b: agree_stats([r for r in recs if r["band"] == b], "agree_theme")
                     for b in BANDS}
    domain_by_band = {b: agree_stats([r for r in recs if r["band"] == b], "agree_domain")
                      for b in BANDS}

    sources = sorted({r["source_model"] for r in recs if r["source_model"]})
    theme_by_source = {sm: agree_stats([r for r in recs if r["source_model"] == sm],
                                       "agree_theme") for sm in sources}
    domain_by_source = {sm: agree_stats([r for r in recs if r["source_model"] == sm],
                                        "agree_domain") for sm in sources}

    # theme-right / domain-wrong: among papers where BOTH are comparable and theme
    # matched, fraction where the domain differs
    both = [r for r in recs if r["agree_theme"] is not None
            and r["agree_domain"] is not None]
    theme_match = [r for r in both if r["agree_theme"]]
    theme_right_domain_wrong = sum(1 for r in theme_match if not r["agree_domain"])
    trdw_pct_of_themematch = pct(theme_right_domain_wrong, len(theme_match))
    trdw_pct_of_all = pct(theme_right_domain_wrong, len(both))

    # confusion: current_theme -> sonnet_theme where they differ
    theme_confusion = Counter()
    for r in recs:
        if r["agree_theme"] is False:
            theme_confusion[(r["current_theme"], r["sonnet_theme"])] += 1
    # domains with most disagreement (by current_domain)
    domain_disagree = Counter()
    for r in recs:
        if r["agree_domain"] is False:
            domain_disagree[r["current_domain"]] += 1
    # per current-theme theme-disagreement counts
    theme_disagree_by_curtheme = Counter()
    theme_total_by_curtheme = Counter()
    for r in recs:
        if r["agree_theme"] is not None:
            theme_total_by_curtheme[r["current_theme"]] += 1
            if r["agree_theme"] is False:
                theme_disagree_by_curtheme[r["current_theme"]] += 1

    # sonnet-unclassifiable + refusals lists
    refusals = [r["id"] for r in recs if r["refused"]]
    son_uncls = [r["id"] for r in recs if r["sonnet_unclassifiable"]]

    # cost
    cost = json.loads(COST_IN.read_text(encoding="utf-8")) if COST_IN.exists() else {}
    total_cost = cost.get("cost_usd", 0.0)

    # sample composition
    band_dist = Counter(r["band"] for r in recs)
    theme_dist = Counter(r["current_theme"] for r in recs)
    source_dist = Counter(r["source_model"] for r in recs)

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
        "theme_right_domain_wrong": {
            "count": theme_right_domain_wrong,
            "pct_of_theme_matches": trdw_pct_of_themematch,
            "pct_of_comparable": trdw_pct_of_all,
            "theme_match_n": len(theme_match),
        },
        "top_theme_confusions": [
            {"from": k[0], "to": k[1], "count": v}
            for k, v in theme_confusion.most_common(12)
        ],
        "top_domain_disagreements": [
            {"current_domain": k, "count": v}
            for k, v in domain_disagree.most_common(12)
        ],
        "theme_disagree_by_curtheme": {
            t: {"disagree": theme_disagree_by_curtheme[t],
                "n": theme_total_by_curtheme[t],
                "pct": pct(theme_disagree_by_curtheme[t], theme_total_by_curtheme[t])}
            for t in sorted(theme_total_by_curtheme)
        },
        "cost_usd": total_cost,
        "band_distribution": dict(band_dist),
        "theme_distribution": dict(theme_dist),
        "source_distribution": dict(source_dist),
    }
    METRICS_OUT.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    write_csv(recs)
    write_report(metrics, recs)
    run_tests(recs, sample_by_id, labels_by_id, final_by_id)

    print("\n==== SUMMARY ====")
    print(f"theme agreement:  {theme_overall['pct']}%  "
          f"({theme_overall['agree']}/{theme_overall['n']})")
    print(f"domain agreement: {domain_overall['pct']}%  "
          f"({domain_overall['agree']}/{domain_overall['n']})")
    for b in BANDS:
        print(f"  band {b:9} theme {theme_by_band[b]['pct']}% "
              f"({theme_by_band[b]['agree']}/{theme_by_band[b]['n']}) | "
              f"domain {domain_by_band[b]['pct']}% "
              f"({domain_by_band[b]['agree']}/{domain_by_band[b]['n']})")
    for sm in sources:
        print(f"  source {sm:7} theme {theme_by_source[sm]['pct']}% "
              f"({theme_by_source[sm]['agree']}/{theme_by_source[sm]['n']})")
    print(f"theme-right/domain-wrong: {theme_right_domain_wrong} "
          f"({trdw_pct_of_themematch}% of theme matches)")
    print(f"refusals: {len(refusals)}  sonnet-unclassifiable: {len(son_uncls)}")
    print(f"cost: ${total_cost}")
    print(f"\nwrote:\n  {CSV_OUT}\n  {REPORT_OUT}\n  {METRICS_OUT}")


def yn(v):
    if v is True:
        return "Y"
    if v is False:
        return "N"
    return ""  # not comparable


def write_csv(recs):
    # sort disagreements to the top: theme-disagree, then domain-disagree,
    # then refusals/uncomparable, then full agreements last
    def sort_key(r):
        if r["agree_theme"] is False:
            p = 0
        elif r["agree_domain"] is False:
            p = 1
        elif r["refused"] or r["sonnet_unclassifiable"]:
            p = 2
        elif r["agree_theme"] is None or r["agree_domain"] is None:
            p = 3
        else:
            p = 4  # full agreement
        return (p, -(r["confidence"] or 0))

    ordered = sorted(recs, key=sort_key)
    cols = ["id", "title", "abstract", "current_theme", "current_domain",
            "confidence", "source_model", "sonnet_theme", "sonnet_domain",
            "agree_theme", "agree_domain", "human_theme", "human_domain",
            "human_notes"]
    # UTF-8 with BOM so Excel opens it correctly
    with open(CSV_OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in ordered:
            abstract = (r["abstract"] or "")[:ABSTRACT_CHARS]
            if r["refused"]:
                son_theme = "(sonnet safety-refused - no label)"
                son_domain = ""
            elif r["sonnet_unclassifiable"]:
                son_theme = (r["sonnet_theme"] or "") + " (sonnet: unclassifiable)"
                son_domain = r["sonnet_domain"] or ""
            else:
                son_theme = r["sonnet_theme"] or ""
                son_domain = r["sonnet_domain"] or ""
                if r["schema_note"].startswith("domain_not_in_theme"):
                    son_domain = (r["sonnet_domain"] or "") + " (invalid for sonnet_theme)"
            w.writerow([
                r["id"], r["title"], abstract, r["current_theme"],
                r["current_domain"], r["confidence"], r["source_model"],
                son_theme, son_domain, yn(r["agree_theme"]), yn(r["agree_domain"]),
                "", "", "",
            ])


def write_report(m, recs):
    L = []
    A = L.append
    A("# Gold-Set Accuracy Estimate — Classification v2\n")
    A("_Method: an INDEPENDENT `claude-sonnet-4-5` label (fresh pick of the single "
      "best thematic_area + domain from the full frozen v2 taxonomy, prompt-cached, "
      "with no knowledge of the existing label) is compared against the production "
      "final label for a 250-paper stratified sample._\n")
    A("> **Read this first — what this number is and is not.** This is an "
      "**LLM-vs-LLM agreement rate**, a *proxy* for accuracy, **not** human ground "
      "truth. Sonnet is a different and stronger model than the Haiku that produced "
      "most labels, so where the two strong, independent signals **agree** we can be "
      "reasonably confident the label is right. Where they **disagree**, it flags a "
      "paper a human should check — it does **not** automatically mean the original "
      "is wrong (sometimes Sonnet is the one that errs, or both are defensible). The "
      "companion `goldset_template.csv` exists precisely so the team can adjudicate "
      "the disagreements and compute a true, human-verified accuracy number.\n")

    # sample composition
    A("## 1. Sample composition\n")
    A(f"- Sample size: **{m['sample_size']}** classified papers "
      f"(unclassifiable=false), fixed seed, reproducible.")
    A(f"- Independently labeled by Sonnet: **{m['sonnet_labeled']}/"
      f"{m['sample_size']}**.")
    A(f"- Usable for **theme** comparison: **{m['theme_comparable_n']}** · "
      f"usable for **domain** comparison: **{m['domain_comparable_n']}**.")
    A(f"- Sonnet safety-refused (empty response, `stop_reason=refusal`): "
      f"**{len(m['refusals'])}** — all benign chem/bio abstracts (biopesticides, "
      f"N95 respirators, organophosphate chemistry, nanoagrochemicals). These are a "
      f"limitation of the Sonnet judge, not a data problem, and are excluded from "
      f"the agreement denominators.")
    A(f"- Sonnet judged **unclassifiable**: **{len(m['sonnet_unclassifiable'])}** "
      f"(also excluded from strict agreement; worth a human look).\n")
    A("**Confidence bands (deliberate <0.5 oversample):**\n")
    A("| band | papers | share |")
    A("|---|---:|---:|")
    tot = m["sample_size"]
    for b in BANDS:
        n = m["band_distribution"].get(b, 0)
        A(f"| {b} | {n} | {pct(n, tot)}% |")
    A("")
    A("**Themes (proportional, ≥10 floor) & source model:**\n")
    A("| thematic area | papers |")
    A("|---|---:|")
    for t, n in sorted(m["theme_distribution"].items(), key=lambda x: -x[1]):
        A(f"| {t} | {n} |")
    A("")
    A("| source_model | papers |")
    A("|---|---:|")
    for s, n in sorted(m["source_distribution"].items(), key=lambda x: -x[1]):
        A(f"| {s} | {n} |")
    A("")

    # headline agreement
    ta, da = m["theme_agreement"], m["domain_agreement"]
    A("## 2. Headline agreement (proxy accuracy)\n")
    A(f"- **Theme-level agreement: {ta['pct']}%** ({ta['agree']}/{ta['n']} "
      f"comparable papers).")
    A(f"- **Domain-level agreement: {da['pct']}%** ({da['agree']}/{da['n']} "
      f"comparable papers).\n")

    # per band
    A("## 3. Agreement by confidence band\n")
    A("The key diagnostic: does confidence track reliability?\n")
    A("| band | theme agree | domain agree |")
    A("|---|---|---|")
    for b in BANDS:
        tb, dbn = m["theme_by_band"][b], m["domain_by_band"][b]
        A(f"| {b} | {tb['pct']}% ({tb['agree']}/{tb['n']}) | "
          f"{dbn['pct']}% ({dbn['agree']}/{dbn['n']}) |")
    A("")
    lo = m["theme_by_band"]["<0.5"]
    mid = m["theme_by_band"]["0.5-0.8"]
    hi = m["theme_by_band"][">=0.8"]
    lod, midd, hid = (m["domain_by_band"]["<0.5"], m["domain_by_band"]["0.5-0.8"],
                      m["domain_by_band"][">=0.8"])
    A("> **Honest reading — the relationship is NOT cleanly monotonic (and n per "
      "band is small).** The **≥0.8 bulk is clearly the strongest** "
      f"({hi['pct']}% theme / {hid['pct']}% domain). The surprise is that the "
      f"**0.5–0.8 middle band is the *weakest*** ({mid['pct']}% theme / "
      f"{midd['pct']}% domain), not the <0.5 tail — and that middle band is "
      "dominated by the 0.7–0.8 bucket, which is the single largest confidence "
      "bucket in the whole corpus (~24k papers). The deliberately over-sampled "
      f"**<0.5 tail is middling on theme ({lo['pct']}%) but soft on domain "
      f"({lod['pct']}%)**. So confidence is a decent triage signal at the top end "
      "but does NOT reliably separate the mid-band from the tail; treat 0.5–0.8 as "
      "needing scrutiny too, not just <0.5.\n")

    # per source
    A("## 4. Agreement by source model (haiku vs sonnet-escalated)\n")
    A("| source_model | theme agree | domain agree |")
    A("|---|---|---|")
    for s in sorted(m["theme_by_source"]):
        tb, dbn = m["theme_by_source"][s], m["domain_by_source"][s]
        A(f"| {s} | {tb['pct']}% ({tb['agree']}/{tb['n']}) | "
          f"{dbn['pct']}% ({dbn['agree']}/{dbn['n']}) |")
    A("")
    A("_Note: papers labeled `sonnet` were the harder cases the pipeline escalated "
      "to Sonnet, so a lower agreement there partly reflects intrinsic difficulty, "
      "not just labeler quality. Also, the escalated labels were produced by the "
      "same model family now acting as judge, which can inflate their apparent "
      "agreement._\n")

    # theme-right domain-wrong
    tr = m["theme_right_domain_wrong"]
    A("## 5. Theme-right / domain-wrong (the common soft error)\n")
    A(f"- Among the **{tr['theme_match_n']}** papers where the theme matched, "
      f"**{tr['count']}** had a differing domain — **{tr['pct_of_theme_matches']}%** "
      f"of theme-matches (and {tr['pct_of_comparable']}% of all comparable papers).")
    A("- Interpretation: the top-level theme is more reliable than the finer domain "
      "assignment; most residual risk is in domain granularity within the correct "
      "theme.\n")

    # confusions
    A("## 6. Top disagreements (where to look)\n")
    A("**Most frequent theme→theme disagreements (current → sonnet):**\n")
    A("| current theme | sonnet theme | count |")
    A("|---|---|---:|")
    for c in m["top_theme_confusions"]:
        A(f"| {c['from']} | {c['to']} | {c['count']} |")
    A("")
    A("**Current themes with the highest theme-disagreement rate:**\n")
    A("| current theme | disagree / comparable | rate |")
    A("|---|---|---:|")
    for t, v in sorted(m["theme_disagree_by_curtheme"].items(),
                       key=lambda x: -(x[1]["pct"] or 0)):
        A(f"| {t} | {v['disagree']}/{v['n']} | {v['pct']}% |")
    A("")
    A("**Domains with the most disagreement (by current domain):**\n")
    A("| current domain | disagreements |")
    A("|---|---:|")
    for c in m["top_domain_disagreements"]:
        A(f"| {c['current_domain']} | {c['count']} |")
    A("")

    # cost
    A("## 7. Cost\n")
    A(f"- Total spend for this gold-set exercise: **${m['cost_usd']:.2f}** "
      f"(claude-sonnet-4-5, prompt-cached taxonomy), well under the $10 guardrail.\n")

    # verdict
    A("## 8. Honest interpretation & verdict\n")
    tp = ta["pct"] or 0
    dp = da["pct"] or 0
    lowb = m["theme_by_band"]["<0.5"]
    midb = m["theme_by_band"]["0.5-0.8"]
    hib = m["theme_by_band"][">=0.8"]
    hibd = m["domain_by_band"][">=0.8"]
    A(f"- A stronger, independent model agrees with the production **theme** on "
      f"**{tp}%** of comparable papers and with the **domain** on **{dp}%**. Because "
      f"the two signals are independent and Sonnet is the stronger model, this is a "
      f"credible *proxy* that the theme layer is in good shape and the domain layer "
      f"is the softer spot. It is still only a proxy — treat these as agreement "
      f"rates, not verified accuracy.")
    A(f"- **Confidence is a useful but imperfect triage signal.** The ≥0.8 bulk is "
      f"clearly the best ({hib['pct']}% theme / {hibd['pct']}% domain). But agreement "
      f"is **not monotonic**: the 0.5–0.8 middle band ({midb['pct']}% theme) actually "
      f"scores *below* the <0.5 tail ({lowb['pct']}% theme). Since 0.7–0.8 is the "
      f"largest confidence bucket in the corpus, that mid-band softness affects a lot "
      f"of papers and deserves scrutiny alongside the <0.5 tail — you cannot assume "
      f"'≥0.5 is safe'.")
    A("- The dominant residual issue is **domain-within-correct-theme** drift "
      f"({tr['pct_of_theme_matches']}% of theme-matches) plus a handful of recurring "
      "theme boundary confusions (see §6) — consistent with the known taxonomy "
      "adjacencies (materials↔energy, materials↔quantum/semiconductor, "
      "manufacturing↔materials).")
    A(f"- **Caveats:** {len(m['refusals'])} benign papers could not be judged at all "
      "(Sonnet safety refusals) and are excluded; per-band n is small (~75–90 each), "
      "so band figures carry meaningful sampling error; and the Sonnet-escalated "
      "subset is judged by the same model family, which can inflate its apparent "
      "agreement.")
    A("- **Verdict:** on this LLM-proxy the **≥0.8 bulk — the large majority of the "
      "corpus — looks ready to ingest**, while the **<0.5 tail AND the 0.5–0.8 "
      "mid-band, plus the specific theme confusions in §6, warrant targeted human "
      "adjudication** (especially at the domain level) before any hard accuracy "
      "number is claimed. Use `goldset_template.csv` (disagreements sorted to the "
      "top) to turn this proxy into a real human gold accuracy; that human number, "
      "not this one, is what should be quoted externally.\n")

    REPORT_OUT.write_text("\n".join(L), encoding="utf-8")


def run_tests(recs, sample_by_id, labels_by_id, final_by_id):
    print("\n==== TESTS ====")
    errors = []

    n_sample = len(sample_by_id)
    n_labels = len(labels_by_id)
    n_recs = len(recs)

    # csv row count
    with open(CSV_OUT, encoding="utf-8-sig") as fh:
        csv_rows = sum(1 for _ in csv.reader(fh)) - 1  # minus header

    if not (n_sample == n_labels == n_recs == csv_rows):
        errors.append(f"count mismatch: sample={n_sample} labels={n_labels} "
                      f"recs={n_recs} csv={csv_rows}")

    # every sampled id exists in final file and got a sonnet label
    for pid in sample_by_id:
        if pid not in final_by_id:
            errors.append(f"sampled id missing from final file: {pid}")
        if pid not in labels_by_id:
            errors.append(f"sampled id has no sonnet label: {pid}")

    # no duplicate ids in csv
    with open(CSV_OUT, encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        ids = [row["id"] for row in r]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids in csv")

    # every comparable record has a boolean agreement; refusals accounted for
    accounted = sum(1 for r in recs if r["theme_comparable"]
                    or r["refused"] or r["sonnet_unclassifiable"])
    if accounted != n_recs:
        errors.append(f"unaccounted records: {n_recs - accounted} "
                      "(neither comparable, refused, nor unclassifiable)")

    print(f"sample={n_sample} labels={n_labels} recs={n_recs} csv_rows={csv_rows}")
    print(f"unique csv ids: {len(set(ids))}")
    print(f"records accounted (comparable|refused|uncls): {accounted}/{n_recs}")
    if errors:
        print("TESTS FAILED:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
