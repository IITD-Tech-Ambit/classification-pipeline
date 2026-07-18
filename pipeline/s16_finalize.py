"""STAGE 3 (part 2): merge -> validate -> report -> spot-check.

1. MERGE Haiku + Sonnet into outputs/classification_v2_final.jsonl:
   for each eligible paper, final = Sonnet result if escalated else Haiku result;
   then append the 1,654 hygiene-unclassifiable papers (source_model="hygiene").
   Final file must cover ALL 70,298 corpus papers (asserted against Mongo _id set,
   READ-ONLY).
   Safety: any non-unclassifiable row whose theme/domain is still invalid is
   converted to unclassifiable=true (reason prefixed 'schema_violation...') so the
   final labels contain zero schema violations among classified rows.

2. TEST -> outputs/final_validation_report.json + outputs/final_report.md
3. 60-row stratified SPOT-CHECK -> outputs/final_spotcheck.md
"""
import json
import random
from collections import Counter, defaultdict

from bson import ObjectId

from common import get_db, OUTPUTS, WORK
from s15_classify_lib import load_taxonomy, norm

SOURCE = WORK / "papers_source.jsonl"
HAIKU_OUT = WORK / "haiku_full.jsonl"
SONNET_OUT = WORK / "sonnet_escalation.jsonl"
HYGIENE = WORK / "hygiene_flags.jsonl"
FINAL = OUTPUTS / "classification_v2_final.jsonl"

FINAL_FIELDS = ["id", "thematic_area", "domain", "confidence", "unclassifiable",
                "reason", "source_model", "escalated"]


def load_jsonl_by_id(path):
    d = {}
    if not path.exists():
        return d
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                d[r["id"]] = r
    return d


def load_hygiene():
    rows = {}
    with open(HYGIENE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["_id"]] = r
    return rows


def build_domain_to_theme():
    """Map normalized domain name -> (theme, canonical_domain). Domain names are
    globally unique across themes (Stage 1 verified), so a domain uniquely
    determines its owning theme; used to recover rows where the model chose a
    valid domain but the wrong theme label."""
    themes, theme_to_domains = load_taxonomy()
    m = {}
    for theme, doms in theme_to_domains.items():
        for d in doms:
            m[norm(d)] = (theme, d)
    return m


def merge(valid_pairs):
    haiku = load_jsonl_by_id(HAIKU_OUT)
    sonnet = load_jsonl_by_id(SONNET_OUT)
    hyg = load_hygiene()
    dom2theme = build_domain_to_theme()

    eligible = [pid for pid, r in hyg.items() if r["status"] in ("ok", "title_only")]
    hyg_unclass = [pid for pid, r in hyg.items() if r["status"] == "unclassifiable"]

    final_rows = []
    stats = {"from_haiku": 0, "from_sonnet": 0, "escalated": 0,
             "recovered_theme_from_domain": 0,
             "forced_unclassifiable": 0, "hygiene_unclassifiable": len(hyg_unclass)}

    def resolve(rec):
        """Extract fields from a raw haiku/sonnet record and apply the
        unique-domain->theme recovery. Returns (dict, usable, recovered)."""
        theme = rec.get("thematic_area")
        domain = rec.get("domain")
        conf = rec.get("confidence")
        unclass = bool(rec.get("unclassifiable"))
        reason = rec.get("reason")
        schema_valid = bool(rec.get("schema_valid"))
        recovered = False
        if not unclass and (theme, domain) not in valid_pairs and domain:
            hit = dom2theme.get(norm(domain))
            if hit is not None:
                theme, domain = hit[0], hit[1]
                schema_valid = True
                recovered = True
        usable = unclass or ((theme, domain) in valid_pairs)
        return ({"thematic_area": theme, "domain": domain, "confidence": conf,
                 "unclassifiable": unclass, "reason": reason,
                 "schema_valid": schema_valid}, usable, recovered)

    for pid in eligible:
        haiku_rec = haiku.get(pid)
        sonnet_rec = sonnet.get(pid)
        escalated = sonnet_rec is not None

        primary = sonnet_rec if escalated else haiku_rec
        if primary is None:
            final_rows.append({
                "id": pid, "thematic_area": None, "domain": None,
                "confidence": None, "unclassifiable": True,
                "reason": "missing_from_haiku_and_sonnet", "source_model": "none",
                "escalated": escalated, "schema_valid": False,
            })
            continue

        resolved, usable, recovered = resolve(primary)
        source_model = "sonnet" if escalated else "haiku"

        # fallback: if escalation produced an unusable result (e.g. Sonnet safety
        # refusal / parse failure), fall back to the paper's Haiku label rather
        # than discarding signal. Escalation must never make a paper worse.
        if escalated and not usable and haiku_rec is not None:
            alt, alt_usable, alt_recovered = resolve(haiku_rec)
            if alt_usable:
                resolved, usable, recovered = alt, True, alt_recovered
                source_model = "haiku"
                stats["sonnet_refused_fallback_haiku"] = \
                    stats.get("sonnet_refused_fallback_haiku", 0) + 1

        if recovered:
            stats["recovered_theme_from_domain"] += 1

        # final safety: still unusable -> mark unclassifiable
        if not resolved["unclassifiable"] and not usable:
            resolved["unclassifiable"] = True
            resolved["reason"] = f"schema_violation_after_escalation: {resolved['reason']}"
            stats["forced_unclassifiable"] += 1

        final_rows.append({
            "id": pid, "thematic_area": resolved["thematic_area"],
            "domain": resolved["domain"], "confidence": resolved["confidence"],
            "unclassifiable": resolved["unclassifiable"], "reason": resolved["reason"],
            "source_model": source_model, "escalated": escalated,
            "schema_valid": resolved["schema_valid"],
        })
        if source_model == "sonnet":
            stats["from_sonnet"] += 1
        else:
            stats["from_haiku"] += 1
        if escalated:
            stats["escalated"] += 1

    # append hygiene-unclassifiable papers
    for pid in hyg_unclass:
        final_rows.append({
            "id": pid, "thematic_area": None, "domain": None, "confidence": None,
            "unclassifiable": True, "reason": hyg[pid].get("reason"),
            "source_model": "hygiene", "escalated": False, "schema_valid": True,
        })

    with open(FINAL, "w", encoding="utf-8") as out:
        for r in final_rows:
            out.write(json.dumps({k: r[k] for k in FINAL_FIELDS},
                                 ensure_ascii=False) + "\n")
    return final_rows, stats, set(eligible), set(hyg_unclass)


def validate(final_rows, valid_pairs, eligible, hyg_unclass):
    # coverage vs authoritative Mongo _id set (READ-ONLY)
    db = get_db()
    corpus_ids = set(str(d["_id"]) for d in
                     db.researchmetadatascopus.find({}, {"_id": 1}))

    ids = [r["id"] for r in final_rows]
    id_set = set(ids)
    dupes = [x for x, c in Counter(ids).items() if c > 1]
    missing_vs_corpus = corpus_ids - id_set
    extra_vs_corpus = id_set - corpus_ids

    classified = [r for r in final_rows if not r["unclassifiable"]]
    unclassified = [r for r in final_rows if r["unclassifiable"]]

    # schema violations remaining among classified
    schema_viol = [r["id"] for r in classified
                   if (r["thematic_area"], r["domain"]) not in valid_pairs]

    theme_dist = Counter(r["thematic_area"] for r in classified)
    domain_dist = Counter(r["domain"] for r in classified)
    confs = [r["confidence"] for r in classified if r["confidence"] is not None]
    mean_conf = round(sum(confs) / len(confs), 4) if confs else None

    bins = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001]
    labels = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-0.95",
              "0.95-1.0"]
    hist = dict.fromkeys(labels, 0)
    for c in confs:
        for i in range(len(labels)):
            if bins[i] <= c < bins[i + 1]:
                hist[labels[i]] += 1
                break

    n_escalated = sum(1 for r in final_rows if r["escalated"])
    unclass_by_src = Counter(r["source_model"] for r in unclassified)

    coverage_ok = (len(final_rows) == len(corpus_ids)
                   and len(dupes) == 0
                   and len(missing_vs_corpus) == 0
                   and len(extra_vs_corpus) == 0)
    passed = coverage_ok and len(schema_viol) == 0

    report = {
        "pass": passed,
        "coverage": {
            "final_rows": len(final_rows),
            "corpus_ids_in_mongo": len(corpus_ids),
            "unique_final_ids": len(id_set),
            "duplicates": len(dupes),
            "missing_vs_corpus": len(missing_vs_corpus),
            "extra_vs_corpus": len(extra_vs_corpus),
            "eligible": len(eligible),
            "hygiene_unclassifiable": len(hyg_unclass),
        },
        "schema_violations_remaining": len(schema_viol),
        "schema_violation_sample": schema_viol[:20],
        "n_classified": len(classified),
        "n_unclassifiable_total": len(unclassified),
        "unclassifiable_by_source": dict(unclass_by_src),
        "n_escalated": n_escalated,
        "mean_confidence": mean_conf,
        "confidence_histogram": hist,
        "n_themes_used": len(theme_dist),
        "n_domains_used": len(domain_dist),
        "theme_distribution": dict(theme_dist.most_common()),
        "domain_distribution": dict(domain_dist.most_common()),
    }
    (OUTPUTS / "final_validation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def write_final_md(report, stats):
    L = []
    L.append("# Classification v2 — Final Validation Report\n")
    cov = report["coverage"]
    L.append(f"- **Result:** {'PASS' if report['pass'] else 'FAIL'}")
    L.append(f"- Corpus papers (Mongo): **{cov['corpus_ids_in_mongo']}** · "
             f"final rows: **{cov['final_rows']}** · unique ids: "
             f"**{cov['unique_final_ids']}** · duplicates: {cov['duplicates']} · "
             f"missing: {cov['missing_vs_corpus']} · extra: {cov['extra_vs_corpus']}")
    L.append(f"- Eligible (classified/attempted): **{cov['eligible']}** · "
             f"hygiene-unclassifiable: **{cov['hygiene_unclassifiable']}**")
    L.append(f"- Classified: **{report['n_classified']}** · "
             f"Unclassifiable total: **{report['n_unclassifiable_total']}** "
             f"({report['unclassifiable_by_source']})")
    L.append(f"- Escalated to Sonnet: **{report['n_escalated']}**")
    L.append(f"- Schema violations remaining: **{report['schema_violations_remaining']}**")
    L.append(f"- Mean confidence (classified): **{report['mean_confidence']}**")
    L.append("")
    L.append("## Theme distribution\n")
    L.append("| Theme | Papers | Share |")
    L.append("|---|---:|---:|")
    tot = report["n_classified"]
    for t, c in report["theme_distribution"].items():
        L.append(f"| {t} | {c} | {100*c/tot:.1f}% |")
    L.append("")
    L.append("## Confidence histogram (classified)\n")
    L.append("| bucket | count |")
    L.append("|---|---:|")
    for k, v in report["confidence_histogram"].items():
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## Domain distribution\n")
    L.append("| Domain | Papers |")
    L.append("|---|---:|")
    for d, c in report["domain_distribution"].items():
        L.append(f"| {d} | {c} |")
    L.append("")
    (OUTPUTS / "final_report.md").write_text("\n".join(L), encoding="utf-8")


def spotcheck(final_rows):
    src = {}
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                p = json.loads(line)
                src[p["id"]] = p

    rng = random.Random(42)
    classified = [r for r in final_rows if not r["unclassifiable"]
                  and r["id"] in src]
    by_theme = defaultdict(list)
    for r in classified:
        by_theme[r["thematic_area"]].append(r)

    picks = []
    seen = set()

    def take(bucket, k, chosen):
        rng.shuffle(bucket)
        for r in bucket:
            if len(chosen) >= k:
                break
            if r["id"] not in seen:
                chosen.append(r)
                seen.add(r["id"])

    # per theme: mix ~3 high-confidence (typical), ~2 low-confidence (edge),
    # ~2 escalated -> a realistic quality cross-section, ~7 per theme.
    for theme, rows in sorted(by_theme.items()):
        high = [r for r in rows if (r["confidence"] or 0) >= 0.8]
        low = [r for r in rows if (r["confidence"] or 1) < 0.6]
        esc = [r for r in rows if r["escalated"]]
        chosen = []
        take(high, 3, chosen)
        take(low, 5, chosen)
        take(esc, 7, chosen)
        take(rows, 7, chosen)
        picks.extend(chosen)

    rng.shuffle(picks)
    picks = picks[:60]

    L = []
    L.append("# Classification v2 — 60-Row Spot-Check (stratified)\n")
    L.append("_Stratified across themes, mixing high/low confidence and escalated "
             "papers. For the owner + reviewer to eyeball quality._\n")
    L.append("| # | Title | Abstract snippet | Theme -> Domain | Conf | Model | Esc |")
    L.append("|---|---|---|---|---:|---|---|")
    for i, r in enumerate(picks, 1):
        p = src[r["id"]]
        title = (p["title"] or "").replace("|", "\\|").replace("\n", " ")
        snip = (p["abstract"] or "")[:180].replace("|", "\\|").replace("\n", " ")
        if p["abstract"] and len(p["abstract"]) > 180:
            snip += "..."
        conf = r["confidence"] if r["confidence"] is not None else "-"
        esc = "yes" if r["escalated"] else ""
        L.append(f"| {i} | {title} | {snip} | {r['thematic_area']} -> "
                 f"{r['domain']} | {conf} | {r['source_model']} | {esc} |")
    L.append("")
    (OUTPUTS / "final_spotcheck.md").write_text("\n".join(L), encoding="utf-8")
    return len(picks)


def main():
    themes, theme_to_domains = load_taxonomy()
    valid_pairs = {(t, d) for t, doms in theme_to_domains.items() for d in doms}

    final_rows, stats, eligible, hyg_unclass = merge(valid_pairs)
    print("merge stats:", json.dumps(stats))
    report = validate(final_rows, valid_pairs, eligible, hyg_unclass)
    write_final_md(report, stats)
    n_spot = spotcheck(final_rows)
    print(f"spotcheck rows: {n_spot}")
    print(json.dumps({k: report[k] for k in
                      ["pass", "coverage", "schema_violations_remaining",
                       "n_classified", "n_unclassifiable_total",
                       "unclassifiable_by_source", "n_escalated",
                       "mean_confidence", "n_themes_used", "n_domains_used"]},
                     indent=2, ensure_ascii=False))
    print("STAGE 3 TEST", "PASSED" if report["pass"] else "FAILED")


if __name__ == "__main__":
    main()
