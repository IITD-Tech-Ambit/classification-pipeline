"""Step 6: check whether the unclassified sample fits the drafted taxonomy.

Assign each unclassified paper to its nearest domain (cosine sim to domain centroid,
where a domain centroid = mean embedding of its member papers). Flag the low-similarity
tail and ask Claude to characterize gaps + recommend absorption.
"""
import json

import numpy as np

from common import WORK
from llm import ask_json

GAP_PROMPT = """We drafted a 9-theme research taxonomy (themes with domains listed below). A sample of previously-unclassified papers was matched to the nearest domain by embedding similarity. The WORST-FITTING papers (bottom of the similarity range) are listed below — these may reveal gaps in the taxonomy.

Taxonomy summary:
{summary}

Worst-fitting unclassified paper titles:
{titles}

TASK: Identify 2-5 recurring subject-matter gaps (e.g. pure mathematics, fundamental chemistry, general physics) among these papers. For each gap, recommend which existing theme AND domain should absorb it (or say a new domain is warranted, naming it). Social Sciences, Humanities & Management is the designated catch-all for non-STEM work.

Return ONLY JSON:
{{"gaps": [{{"gap": "...", "evidence_titles": ["...", "..."], "recommendation": "..."}}]}}"""


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))
    final = json.loads((WORK / "domains_final.json").read_text(encoding="utf-8"))
    clusters = json.loads((WORK / "clusters.json").read_text(encoding="utf-8"))
    emb_data = np.load(WORK / "embeddings.npz")

    # build domain centroids from member paper embeddings
    dom_names, dom_themes, dom_cents = [], [], []
    for tid, t in final.items():
        if tid == "__out_of_theme_clusters__":
            continue
        emb = emb_data[tid]
        labels = np.array(clusters[tid]["labels"])
        for d in t["domains"]:
            mask = np.isin(labels, d["clusters"])
            if mask.sum() == 0:
                continue
            c = emb[mask].mean(axis=0)
            c /= np.linalg.norm(c) + 1e-9
            dom_names.append(d["name"])
            dom_themes.append(t["theme"])
            dom_cents.append(c)
    cents = np.vstack(dom_cents)

    uemb = emb_data["__unclassified__"]
    upapers = samples["unclassified"]
    sims = uemb @ cents.T
    best_idx = sims.argmax(axis=1)
    best_sim = sims.max(axis=1)

    theme_counts = {}
    for i in best_idx:
        theme_counts[dom_themes[i]] = theme_counts.get(dom_themes[i], 0) + 1
    print("unclassified sample -> nearest theme distribution:")
    for k, v in sorted(theme_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"similarity: median={np.median(best_sim):.3f} p10={np.percentile(best_sim,10):.3f}")

    # bottom 15% by similarity = candidate gaps
    thresh = np.percentile(best_sim, 15)
    worst = [upapers[i]["title"] for i in np.argsort(best_sim)[:80]]

    summary = "\n".join(
        f"- {t['theme']}: " + "; ".join(d["name"] for d in t["domains"])
        for tid, t in final.items() if tid != "__out_of_theme_clusters__"
    )
    gaps = ask_json(GAP_PROMPT.format(summary=summary, titles="\n".join(f"- {w}" for w in worst)),
                    max_tokens=2000)

    out = {
        "n_unclassified_sampled": len(upapers),
        "nearest_theme_distribution": theme_counts,
        "similarity_median": float(np.median(best_sim)),
        "similarity_p10": float(np.percentile(best_sim, 10)),
        "low_fit_threshold": float(thresh),
        "n_low_fit": int((best_sim < thresh).sum()),
        "gaps": gaps["gaps"],
        "assignments": [
            {"title": upapers[i]["title"], "theme": dom_themes[best_idx[i]],
             "domain": dom_names[best_idx[i]], "sim": float(best_sim[i])}
            for i in range(len(upapers))
        ],
    }
    with open(WORK / "unclassified_check.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("done")


if __name__ == "__main__":
    main()
