"""Step 10 (classification-v2): hygiene / filtering gate over the FULL corpus.

READ-ONLY DB access. Classifies every paper in researchmetadatascopus into one of
three hygiene statuses and writes one record per paper to outputs/work/hygiene_flags.jsonl:

    {_id, status, reason, title_len, has_abstract}

Statuses
--------
- ok            : has a usable abstract (non-empty, not "(No abstract available)",
                  length >= MIN_ABSTRACT_LEN). -> embedding + classification.
- title_only    : no usable abstract BUT the title is long/informative
                  (title_len >= MIN_TITLE_LEN and not a junk pattern).
                  -> still classified (theme-level), tracked separately.
- unclassifiable: (a) no usable abstract AND short/uninformative title, OR
                  (b) title matches a non-research pattern (erratum, editorial, ...).
                  -> EXCLUDED from embedding + classification.

Also writes a human-readable summary to outputs/hygiene_summary.md.
"""
import json
import re
from collections import Counter

from common import get_db, ensure_dirs, OUTPUTS, WORK

MIN_ABSTRACT_LEN = 100  # chars; below this an abstract is treated as unusable
MIN_TITLE_LEN = 60      # chars; title-only papers need an informative title
NO_ABSTRACT_LITERAL = "(no abstract available)"

# Case-insensitive non-research title patterns -> unclassifiable regardless of abstract.
JUNK_PATTERNS = [
    ("erratum", r"\berratum\b"),
    ("corrigendum", r"\bcorrigendum\b"),
    ("editorial", r"\beditorial\b"),
    ("preface", r"\bpreface\b"),
    ("foreword", r"\bforeword\b"),
    ("table_of_contents", r"table of contents"),
    ("front_matter", r"front matter"),
    ("list_of_contributors", r"list of contributors"),
    ("author_index", r"author index"),
    ("retracted", r"\bretracted\b"),
    ("retraction", r"\bretraction\b"),
    ("in_this_issue", r"in this issue"),
    ("book_review", r"book review"),
    ("call_for_papers", r"call for papers"),
]
_JUNK = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in JUNK_PATTERNS]


def abstract_is_usable(abstract: str) -> bool:
    a = (abstract or "").strip()
    if not a:
        return False
    if a.lower() == NO_ABSTRACT_LITERAL:
        return False
    if len(a) < MIN_ABSTRACT_LEN:
        return False
    return True


def junk_match(title: str):
    for name, rx in _JUNK:
        if rx.search(title or ""):
            return name
    return None


def classify(title: str, abstract: str):
    """Return (status, reason, has_abstract)."""
    title = title or ""
    title_len = len(title.strip())
    has_abstract = abstract_is_usable(abstract)

    junk = junk_match(title)
    if junk:
        return "unclassifiable", f"junk_pattern:{junk}", has_abstract

    if has_abstract:
        return "ok", "usable_abstract", has_abstract

    # no usable abstract from here on
    if title_len >= MIN_TITLE_LEN:
        return "title_only", "no_abstract_informative_title", has_abstract

    return "unclassifiable", "no_abstract_short_title", has_abstract


def main():
    ensure_dirs()
    db = get_db()
    coll = db.researchmetadatascopus
    total = coll.estimated_document_count()
    print(f"papers in corpus: {total}", flush=True)

    out_path = WORK / "hygiene_flags.jsonl"
    status_counts = Counter()
    reason_counts = Counter()
    unclassifiable_reasons = Counter()
    no_title = 0
    seen_ids = set()
    dup_ids = 0
    processed = 0

    cursor = coll.find({}, {"title": 1, "abstract": 1}, no_cursor_timeout=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for doc in cursor:
            _id = str(doc["_id"])
            if _id in seen_ids:
                dup_ids += 1
            seen_ids.add(_id)

            title = doc.get("title") or ""
            abstract = doc.get("abstract") or ""
            title_len = len(title.strip())
            if title_len == 0:
                no_title += 1

            status, reason, has_abstract = classify(title, abstract)
            status_counts[status] += 1
            reason_counts[reason] += 1
            if status == "unclassifiable":
                unclassifiable_reasons[reason] += 1

            rec = {
                "_id": _id,
                "status": status,
                "reason": reason,
                "title_len": title_len,
                "has_abstract": has_abstract,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            processed += 1
            if processed % 10000 == 0:
                print(f"  {processed}/{total} processed", flush=True)
    cursor.close()

    proceed = status_counts["ok"] + status_counts["title_only"]
    filtered = status_counts["unclassifiable"]

    # ---- write summary markdown ----
    lines = []
    lines.append("# Hygiene Gate Summary (classification-v2, Step 2 / Task A)\n")
    lines.append(f"- Corpus: `researchmetadatascopus`")
    lines.append(f"- Total papers processed: **{processed}**")
    lines.append(f"- Per-paper flags: `outputs/work/hygiene_flags.jsonl`")
    lines.append(f"- Thresholds: MIN_ABSTRACT_LEN={MIN_ABSTRACT_LEN} chars, "
                 f"MIN_TITLE_LEN={MIN_TITLE_LEN} chars")
    lines.append("")
    lines.append("## Status counts\n")
    lines.append("| Status | Count | % | Fate |")
    lines.append("|---|---:|---:|---|")
    fate = {
        "ok": "embed + classify",
        "title_only": "classify (theme-level)",
        "unclassifiable": "EXCLUDED",
    }
    for st in ["ok", "title_only", "unclassifiable"]:
        c = status_counts[st]
        lines.append(f"| `{st}` | {c} | {100*c/processed:.2f}% | {fate[st]} |")
    lines.append(f"| **proceed to embedding** | **{proceed}** | {100*proceed/processed:.2f}% | ok + title_only |")
    lines.append(f"| **filtered out** | **{filtered}** | {100*filtered/processed:.2f}% | unclassifiable |")
    lines.append("")
    lines.append("## Unclassifiable reason breakdown\n")
    lines.append("| Reason | Count |")
    lines.append("|---|---:|")
    for reason, c in unclassifiable_reasons.most_common():
        lines.append(f"| `{reason}` | {c} |")
    lines.append("")
    lines.append("## Notes / surprises\n")
    lines.append(f"- Papers with an empty title: {no_title}")
    lines.append(f"- Duplicate `_id` values encountered: {dup_ids}")
    lines.append("")
    (OUTPUTS / "hygiene_summary.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- console report ----
    print("\n=== hygiene gate done ===")
    for st in ["ok", "title_only", "unclassifiable"]:
        print(f"  {st:16} {status_counts[st]}")
    print(f"  proceed to embedding: {proceed}")
    print(f"  filtered out:         {filtered}")
    print("  unclassifiable reasons:")
    for reason, c in unclassifiable_reasons.most_common():
        print(f"    {reason:32} {c}")
    print(f"  empty titles: {no_title}, duplicate ids: {dup_ids}")
    print(f"  wrote {out_path}")
    print(f"  wrote {OUTPUTS / 'hygiene_summary.md'}")


if __name__ == "__main__":
    main()
