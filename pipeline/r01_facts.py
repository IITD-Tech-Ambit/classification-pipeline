"""REFINEMENT step 0: gather exact corpus facts to design Stages A-D.

READ-ONLY. Reads only local files (classification_v2_final.jsonl,
papers_source.jsonl, taxonomy-draft-v2.json). No Mongo, no API, no git.
"""
import json
from collections import Counter

from common import OUTPUTS, WORK

FINAL_V2 = OUTPUTS / "classification_v2_final.jsonl"
PAPERS = WORK / "papers_source.jsonl"

# The five sink/donor "junk-drawer" domains flagged by the diagnosis whose
# >=0.8 papers must ALSO be re-classified so the v3 fixes take effect.
SINK_DOMAINS = {
    "Grid Integration & Smart Microgrids",
    "Semiconductor Photovoltaic & Photodetection Devices",
    "Materials, Joining & Mechanical Behavior",
    "Power Systems & Grid Control",
    "Algorithms & Computational Complexity",
}


def band_of(c):
    if c is None:
        return "none"
    if c < 0.5:
        return "<0.5"
    if c < 0.8:
        return "0.5-0.8"
    return ">=0.8"


def main():
    rows = []
    ids = []
    with open(FINAL_V2, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows.append(r)
                ids.append(r["id"])

    text_ids = set()
    with open(PAPERS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                text_ids.add(json.loads(line)["id"])

    n = len(rows)
    uniq = len(set(ids))
    uncl = [r for r in rows if r.get("unclassifiable")]
    classified = [r for r in rows if not r.get("unclassifiable")]

    # hygiene-unclassifiable = unclassifiable rows with NO source text
    uncl_no_text = [r for r in uncl if r["id"] not in text_ids]
    uncl_with_text = [r for r in uncl if r["id"] in text_ids]

    band = Counter(band_of(r.get("confidence")) for r in classified)

    # re-classification set:
    #   (a) all classified with conf < 0.8  (must have text)
    #   (b) >=0.8 classified in a sink domain (must have text)
    lowconf = [r for r in classified if (r.get("confidence") is not None
                                         and r["confidence"] < 0.8)]
    hi_sink = [r for r in classified if (r.get("confidence") is not None
                                         and r["confidence"] >= 0.8
                                         and r.get("domain") in SINK_DOMAINS)]
    repass_ids = {r["id"] for r in lowconf} | {r["id"] for r in hi_sink}
    repass_ids_with_text = {i for i in repass_ids if i in text_ids}
    repass_missing_text = repass_ids - repass_ids_with_text

    dom_counts = Counter(r.get("domain") for r in classified)
    theme_counts = Counter(r.get("thematic_area") for r in classified)
    src = Counter(r.get("source_model") for r in classified)
    esc = Counter(bool(r.get("escalated")) for r in classified)

    facts = {
        "total_rows": n,
        "unique_ids": uniq,
        "papers_with_text": len(text_ids),
        "classified": len(classified),
        "unclassifiable_total": len(uncl),
        "unclassifiable_no_text_hygiene": len(uncl_no_text),
        "unclassifiable_with_text": len(uncl_with_text),
        "classified_missing_text": sum(1 for r in classified
                                       if r["id"] not in text_ids),
        "band_distribution": dict(band),
        "lowconf_lt_0.8": len(lowconf),
        "hi_conf_in_sink_domains": len(hi_sink),
        "repass_set_size": len(repass_ids),
        "repass_set_with_text": len(repass_ids_with_text),
        "repass_missing_text": len(repass_missing_text),
        "sink_domain_counts_total": {d: dom_counts.get(d, 0) for d in SINK_DOMAINS},
        "sink_domain_hi_conf": {
            d: sum(1 for r in hi_sink if r.get("domain") == d) for d in SINK_DOMAINS},
        "source_model": dict(src),
        "escalated": {str(k): v for k, v in esc.items()},
        "n_themes": len(theme_counts),
        "n_domains": len([d for d in dom_counts if d]),
    }
    (WORK / "refine_facts.json").write_text(json.dumps(facts, indent=2),
                                            encoding="utf-8")
    print(json.dumps(facts, indent=2))
    print("\nsample unclassifiable reasons (with text):")
    for r in uncl_with_text[:5]:
        print(" ", r.get("source_model"), "|", (r.get("reason") or "")[:90])
    print("theme distribution:")
    for t, c in theme_counts.most_common():
        print(f"  {c:6}  {t}")


if __name__ == "__main__":
    main()
