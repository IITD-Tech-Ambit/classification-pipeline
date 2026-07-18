"""Step 7: assemble taxonomy-draft-v2.md (team review doc) and taxonomy-draft-v2.json."""
import json
from datetime import date

import numpy as np

from common import WORK, OUTPUTS


def main():
    final = json.loads((WORK / "domains_final.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    clusters = json.loads((WORK / "clusters.json").read_text(encoding="utf-8"))
    uncheck = json.loads((WORK / "unclassified_check.json").read_text(encoding="utf-8"))
    usage = json.loads((WORK / "llm_usage.json").read_text(encoding="utf-8"))
    embed_model = (WORK / "embed_model.txt").read_text(encoding="utf-8").strip()
    theme_meta = {t["id"]: t for t in facts["themes"]}

    # ---------- markdown ----------
    md = []
    md.append("# Research Ambit Taxonomy Draft v2 — For Team Review")
    md.append(f"\n_Drafted {date.today().isoformat()} from the live paper corpus "
              f"({facts['n_papers']:,} papers in `researchmetadatascopus`). "
              f"Embeddings: `{embed_model}`; clustering: KMeans with silhouette-based k selection; "
              f"naming/definitions: `claude-haiku-4-5`._\n")
    md.append("## Rules of the taxonomy\n")
    md.append("- **Two levels**: 9 fixed thematic areas (names unchanged from v1) → 5–10 domains each. "
              "The old shared 35-domain pool and 177 subdomains are retired; each domain below belongs to exactly one theme.")
    md.append("- **Single label**: every paper gets exactly one theme and one domain within it.")
    md.append("- **No overlaps**: domain definitions within a theme are mutually exclusive; "
              "cross-theme boundary calls are settled by the tie-break rules embedded in each scope note.")
    md.append("- Domain lists below were derived by clustering actual paper samples (~500/theme), "
              "so estimated shares reflect the sampled corpus, not aspiration.\n")

    theme_order = [tid for tid in final if tid != "__out_of_theme_clusters__"]

    for tid in theme_order:
        t = final[tid]
        meta = theme_meta[tid]
        labels = np.array(clusters[tid]["labels"])
        n = len(labels)
        md.append(f"\n---\n\n## {t['theme']}")
        md.append(f"\n_v1-assigned papers: {meta['assigned_papers_v1']:,} · sampled: {t['n_sampled']} · "
                  f"clusters found: {t['k']} · domains: {len(t['domains'])}_\n")
        md.append(f"**Scope.** {t['scope_note']}\n")
        md.append("| Domain | Definition | Example papers (from corpus) | Est. share |")
        md.append("|---|---|---|---|")
        rows = []
        for d in t["domains"]:
            size = int(np.isin(labels, d["clusters"]).sum())
            share = size / n
            titles = []
            for c in d["clusters"]:
                titles.extend(t["cluster_reps"][str(c)]["titles"][:3])
            examples = "<br>".join(f"• {x}" for x in titles[:5])
            rows.append((share, f"| **{d['name']}** | {d['definition']} | {examples} | {share:.0%} |"))
        for _, row in sorted(rows, key=lambda r: -r[0]):
            md.append(row)

    md.append("\n---\n\n## Unclassified papers check")
    md.append(f"\nA separate sample of {uncheck['n_unclassified_sampled']} currently-unclassified papers "
              f"(~{facts['n_unclassified']:,} in total) was matched to the nearest drafted domain by embedding similarity. "
              f"Median similarity {uncheck['similarity_median']:.2f} — most fit the draft comfortably. "
              "Nearest-theme distribution of the sample:\n")
    for k, v in sorted(uncheck["nearest_theme_distribution"].items(), key=lambda x: -x[1]):
        md.append(f"- {k}: {v}")
    md.append("\n**Gaps observed in the worst-fitting tail** "
              f"({uncheck['n_low_fit']} papers below similarity {uncheck['low_fit_threshold']:.2f}):\n")
    for g in uncheck["gaps"]:
        ev = "; ".join(f"_{x}_" for x in g["evidence_titles"][:2])
        md.append(f"- **{g['gap']}** — {g['recommendation']} (e.g. {ev})")

    md.append("\n---\n\n## Open questions for the team\n")
    open_qs = build_open_questions(final, uncheck)
    for q in open_qs:
        md.append(f"1. {q}")

    (OUTPUTS / "taxonomy-draft-v2.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {OUTPUTS / 'taxonomy-draft-v2.md'}")

    # ---------- json ----------
    jout = {
        "version": "v2-draft",
        "generated": date.today().isoformat(),
        "embedding_model": embed_model,
        "themes": [],
    }
    for tid in theme_order:
        t = final[tid]
        meta = theme_meta[tid]
        labels = np.array(clusters[tid]["labels"])
        n = len(labels)
        jout["themes"].append({
            "id": tid,
            "name": meta["name"],
            "slug": meta.get("slug"),
            "scope_note": t["scope_note"],
            "domains": [
                {
                    "name": d["name"],
                    "definition": d["definition"],
                    "estimated_share_of_theme": round(float(np.isin(labels, d["clusters"]).sum()) / n, 3),
                }
                for d in t["domains"]
            ],
        })
    with open(OUTPUTS / "taxonomy-draft-v2.json", "w", encoding="utf-8") as f:
        json.dump(jout, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUTPUTS / 'taxonomy-draft-v2.json'}")
    print(f"LLM usage: {usage}")


def build_open_questions(final, uncheck):
    qs = []
    oot = final.get("__out_of_theme_clusters__", {})
    for theme, cl in oot.items():
        qs.append(f"Under **{theme}**, cluster(s) {cl} looked out-of-theme (likely v1 misclassifications). "
                  "They were excluded from the domain list — confirm they should be re-routed by the v2 classifier.")
    qs.append("The v1 assignments used for sampling are only ~2/3 accurate, so each theme's sample contains "
              "some foreign papers; domains flagged as out-of-theme were dropped, but borderline ones may remain. "
              "Please sanity-check the smallest domains in each theme.")
    qs.append("Estimated shares are from ~500-paper samples per theme; treat them as rough (±5pp).")
    for g in uncheck["gaps"]:
        qs.append(f"Gap: **{g['gap']}** — proposed: {g['recommendation']} Agree?")
    return qs


if __name__ == "__main__":
    main()
