"""Step 15 (classification-v2): human-review sheet for LOW-CONFIDENCE classified papers.

Builds a validation sheet of the weakest tail of the v2 classifier (classified,
confidence < 0.5) so the owner and team can eyeball failure patterns BEFORE any
DB ingestion.

READ-ONLY DB access. Does NOT write to Mongo. Does NOT commit/push git.

Inputs:
  outputs/classification_v2_final.jsonl   (70,298 rows)
  outputs/taxonomy-draft-v2.json
  Mongo research_ambit.researchmetadatascopus  (title + abstract, read-only)

Outputs:
  outputs/lowconf_review.csv
  outputs/lowconf_review.md
"""
import csv
import json
import re
from collections import Counter

from bson import ObjectId

from common import get_db, OUTPUTS

FINAL_PATH = OUTPUTS / "classification_v2_final.jsonl"
CSV_PATH = OUTPUTS / "lowconf_review.csv"
MD_PATH = OUTPUTS / "lowconf_review.md"

CONF_CUTOFF = 0.5
ABSTRACT_TRUNC = 500
WORST_N = 40
TOP_DOMAINS = 20

# Rough keyword heuristic for likely out-of-scope basic (physics) science in the TITLE.
# NOT ground truth — just a signal to decide whether an out-of-scope bucket is worth adding.
OOS_KEYWORDS = [
    r"\bphysics\b", r"\bastro", r"\bastronomy\b", r"\bastrophysic",
    r"\bcosmolog", r"\bnuclear\b", r"\bnucle(i|us|on)", r"\batomic\b",
    r"\bquantum field", r"\bqcd\b", r"\bqed\b", r"\bparticle physics\b",
    r"\bhiggs\b", r"\bboson\b", r"\bhadron", r"\bquark", r"\blepton",
    r"\bneutrino", r"\bgluon", r"\bmuon", r"\bfermion",
    r"\bgravitation", r"\bgravitational wave", r"\bblack hole",
    r"\bgalax(y|ies)\b", r"\bstellar\b", r"\bplasma\b",
    r"\bspacetime\b", r"\brelativit", r"\bcondensed matter\b",
    r"\bstring theory\b", r"\bdark matter\b", r"\bdark energy\b",
]
_OOS_RE = re.compile("|".join(OOS_KEYWORDS), re.IGNORECASE)


def load_final():
    rows = []
    with open(FINAL_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def to_oid(pid):
    try:
        return ObjectId(pid)
    except Exception:
        return None


def main():
    all_rows = load_final()
    total_corpus = len(all_rows)
    all_ids = {r["id"] for r in all_rows}

    # 1. select review set: classified (unclassifiable=false) AND confidence < 0.5
    review = []
    for r in all_rows:
        if r.get("unclassifiable"):
            continue
        conf = r.get("confidence")
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        if conf < CONF_CUTOFF:
            r = dict(r)
            r["confidence"] = conf
            review.append(r)

    review.sort(key=lambda r: r["confidence"])  # worst first
    n_review = len(review)
    pct_corpus = 100.0 * n_review / total_corpus if total_corpus else 0.0
    print(f"corpus rows: {total_corpus}")
    print(f"low-conf (classified, conf<{CONF_CUTOFF}): {n_review}  ({pct_corpus:.2f}%)")

    # 2. join to Mongo for title + abstract (read-only)
    db = get_db()
    coll = db.researchmetadatascopus

    oid_to_pid = {}
    oids = []
    for r in review:
        oid = to_oid(r["id"])
        if oid is not None:
            oid_to_pid[oid] = r["id"]
            oids.append(oid)

    docs = {}
    BATCH = 2000
    for i in range(0, len(oids), BATCH):
        chunk = oids[i:i + BATCH]
        for d in coll.find({"_id": {"$in": chunk}}, {"title": 1, "abstract": 1}):
            docs[str(d["_id"])] = d

    n_title_joined = 0
    for r in review:
        d = docs.get(r["id"], {})
        title = (d.get("title") or "").strip()
        abstract = (d.get("abstract") or "").strip()
        r["title"] = title
        r["abstract_full"] = abstract
        if title:
            n_title_joined += 1
    join_rate = 100.0 * n_title_joined / n_review if n_review else 0.0
    print(f"title join success: {n_title_joined}/{n_review}  ({join_rate:.2f}%)")

    # 3a. CSV (Excel-safe: UTF-8-BOM + quoting)
    write_csv(review)

    # breakdowns for MD
    theme_counts = Counter(r.get("thematic_area") or "(none)" for r in review)
    domain_counts = Counter(r.get("domain") or "(none)" for r in review)

    buckets = [("<0.2", 0.0, 0.2), ("0.2-0.3", 0.2, 0.3),
               ("0.3-0.4", 0.3, 0.4), ("0.4-0.5", 0.4, 0.5)]
    hist = {lab: 0 for lab, _, _ in buckets}
    for r in review:
        c = r["confidence"]
        for lab, lo, hi in buckets:
            if lo <= c < hi:
                hist[lab] += 1
                break

    # 4. out-of-scope basic-science heuristic (title keyword match)
    n_oos = 0
    for r in review:
        title = r.get("title") or ""
        r["_oos_hit"] = bool(_OOS_RE.search(title))
        if r["_oos_hit"]:
            n_oos += 1
    n_misdomained = n_review - n_oos

    write_md(review, total_corpus, n_review, pct_corpus, theme_counts,
             domain_counts, buckets, hist, n_oos, n_misdomained, join_rate,
             n_title_joined)

    # 5. TESTS / assertions
    run_tests(review, n_review, all_ids, n_title_joined, join_rate)

    print(f"\nDONE.\n  {CSV_PATH}\n  {MD_PATH}")

    # machine-readable summary for the caller
    print("\n===SUMMARY_JSON===")
    print(json.dumps({
        "total_corpus": total_corpus,
        "low_conf_count": n_review,
        "pct_corpus": round(pct_corpus, 3),
        "theme_breakdown": theme_counts.most_common(),
        "conf_histogram": hist,
        "oos_heuristic": n_oos,
        "misdomained_est": n_misdomained,
        "join_success_rate": round(join_rate, 3),
        "titles_joined": n_title_joined,
    }, ensure_ascii=False))


def write_csv(review):
    fields = ["id", "confidence", "source_model", "escalated", "thematic_area",
              "domain", "title", "abstract", "reason", "human_verdict"]
    # utf-8-sig gives Excel the BOM; QUOTE_ALL keeps commas/newlines safe.
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in review:
            abstract = r.get("abstract_full") or ""
            if not abstract:
                abstract = "[no abstract]"
            elif len(abstract) > ABSTRACT_TRUNC:
                abstract = abstract[:ABSTRACT_TRUNC].rstrip() + "..."
            w.writerow({
                "id": r["id"],
                "confidence": r["confidence"],
                "source_model": r.get("source_model", ""),
                "escalated": r.get("escalated", ""),
                "thematic_area": r.get("thematic_area", ""),
                "domain": r.get("domain", ""),
                "title": r.get("title") or "[no title]",
                "abstract": abstract,
                "reason": r.get("reason", ""),
                "human_verdict": "",
            })


def write_md(review, total_corpus, n_review, pct_corpus, theme_counts,
             domain_counts, buckets, hist, n_oos, n_misdomained, join_rate,
             n_title_joined):
    L = []
    L.append("# Low-Confidence Classified Papers — Human Review\n")
    L.append(f"_Review set = classified papers (`unclassifiable=false`) with "
             f"`confidence < {CONF_CUTOFF}`, from `classification_v2_final.jsonl`. "
             f"Sorted worst-first. Titles/abstracts joined read-only from Mongo._\n")
    L.append("## Overview\n")
    L.append(f"- **Low-confidence papers:** {n_review:,}")
    L.append(f"- **Share of corpus:** {pct_corpus:.2f}% (of {total_corpus:,})")
    L.append(f"- **Title join success:** {n_title_joined:,}/{n_review:,} "
             f"({join_rate:.2f}%)")
    L.append("")

    L.append("## Confidence histogram (within low-conf set)\n")
    L.append("| bucket | count | share |")
    L.append("|---|---:|---:|")
    for lab, _, _ in buckets:
        c = hist[lab]
        sh = 100.0 * c / n_review if n_review else 0.0
        L.append(f"| {lab} | {c:,} | {sh:.1f}% |")
    L.append("")

    L.append("## Breakdown by thematic area\n")
    L.append("| thematic area | count | share |")
    L.append("|---|---:|---:|")
    for name, c in theme_counts.most_common():
        sh = 100.0 * c / n_review if n_review else 0.0
        L.append(f"| {name} | {c:,} | {sh:.1f}% |")
    L.append("")

    L.append(f"## Breakdown by domain (top {TOP_DOMAINS})\n")
    L.append("| domain | count | share |")
    L.append("|---|---:|---:|")
    for name, c in domain_counts.most_common(TOP_DOMAINS):
        sh = 100.0 * c / n_review if n_review else 0.0
        L.append(f"| {name} | {c:,} | {sh:.1f}% |")
    L.append("")

    L.append("## Out-of-scope vs misdomained (rough heuristic)\n")
    L.append("> **Heuristic estimate, not ground truth.** Counts low-conf papers whose "
             "**title** contains basic-physics / astro / nuclear / atomic / "
             "quantum-field / cosmology / particle keywords. Titles matching these are "
             "*likely* out-of-scope basic science; the rest are *likely* "
             "in-scope-but-misdomained. Abstract text is not scanned, so this "
             "under-counts. Use only to decide whether an explicit out-of-scope bucket "
             "is worth adding.\n")
    pct_oos = 100.0 * n_oos / n_review if n_review else 0.0
    L.append(f"- **Likely out-of-scope basic science (title keyword hit):** "
             f"{n_oos:,} ({pct_oos:.1f}%)")
    L.append(f"- **Likely in-scope but misdomained (no hit):** "
             f"{n_misdomained:,} ({100 - pct_oos:.1f}%)")
    L.append("")

    L.append(f"## {WORST_N} worst papers (lowest confidence)\n")
    L.append("| # | conf | id | assigned theme -> domain | title |")
    L.append("|---:|---:|---|---|---|")
    for i, r in enumerate(review[:WORST_N], 1):
        title = (r.get("title") or "[no title]").replace("|", "\\|").replace("\n", " ")
        if len(title) > 160:
            title = title[:160].rstrip() + "..."
        theme = (r.get("thematic_area") or "?").replace("|", "\\|")
        dom = (r.get("domain") or "?").replace("|", "\\|")
        oos = " *[oos?]*" if r.get("_oos_hit") else ""
        L.append(f"| {i} | {r['confidence']:.3f} | `{r['id']}` | "
                 f"{theme} -> {dom}{oos} | {title} |")
    L.append("")
    L.append("_`[oos?]` marks a title that hit the out-of-scope basic-science keyword "
             "heuristic._\n")

    MD_PATH.write_text("\n".join(L), encoding="utf-8")


def run_tests(review, n_review, all_ids, n_title_joined, join_rate):
    print("\n--- TESTS ---")
    # CSV row count == selected count
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        csv_rows = list(rd)
    assert len(csv_rows) == n_review, \
        f"CSV rows {len(csv_rows)} != selected {n_review}"
    print(f"[ok] CSV row count == selected count ({n_review})")

    # every id in sheet exists in final file
    missing = [row["id"] for row in csv_rows if row["id"] not in all_ids]
    assert not missing, f"{len(missing)} sheet ids not in final file, e.g. {missing[:5]}"
    print(f"[ok] all {len(csv_rows)} sheet ids exist in final file")

    # header includes human_verdict + expected columns
    assert "human_verdict" in csv_rows[0], "human_verdict column missing"
    print("[ok] human_verdict column present")

    # titles joined for the large majority
    assert join_rate >= 90.0, f"join rate {join_rate:.2f}% below 90% threshold"
    print(f"[ok] title join success {join_rate:.2f}% (>= 90%)")

    # confidence sorted ascending
    confs = [float(row["confidence"]) for row in csv_rows]
    assert confs == sorted(confs), "CSV not sorted by confidence ascending"
    print("[ok] CSV sorted by confidence ascending")
    print("--- ALL TESTS PASSED ---")


if __name__ == "__main__":
    main()
