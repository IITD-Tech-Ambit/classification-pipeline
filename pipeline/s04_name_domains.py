"""Step 4: per theme, ask Claude to name clusters and consolidate into 5-10 domains.

One call per theme: it sees all clusters (representative titles + abstract snippets)
plus the old domain/subdomain vocabulary, and returns a consolidated domain list with
a cluster->domain mapping.
"""
import json

import numpy as np

from common import WORK
from llm import ask_json

N_TITLES = 14
N_SNIPPETS = 3


def representatives(emb, labels, centroid, cluster_id, papers):
    idx = np.where(np.array(labels) == cluster_id)[0]
    sims = emb[idx] @ centroid / (np.linalg.norm(centroid) + 1e-9)
    order = idx[np.argsort(-sims)]
    reps = [papers[i] for i in order[:N_TITLES]]
    snippets = [p["abstract"][:350] for p in reps if p["abstract"]][:N_SNIPPETS]
    return reps, snippets, len(idx)


PROMPT = """You are designing a research paper taxonomy for IIT Delhi's research portal.

Theme (FIXED, do not rename): "{theme}"

Below are {k} clusters of papers currently under this theme, discovered by embedding+KMeans.
For each cluster you see its size, representative paper titles, and a few abstract snippets.

{clusters_block}

Naming vocabulary hints from the OLD taxonomy (use only as inspiration for phrasing, NOT as required structure):
Old domains: {old_domains}
Old subdomains (sample): {old_subdomains}

TASK: Consolidate these clusters into a clean set of 5 to 10 DOMAINS for this theme.
Rules:
- Domains must be mutually exclusive within the theme (no overlapping definitions).
- Merge clusters that are really the same topic; split-by-name is not allowed (each cluster maps to exactly one domain).
- Names: academic, browsable, Title Case, concise (2-6 words), no "&" chains longer than 2 concepts.
- Each domain gets a 1-2 sentence definition stating what belongs in it.
- If a cluster is clearly noise/misclassified papers belonging to a DIFFERENT theme, map it to domain name "__OUT_OF_THEME__".

Return ONLY JSON:
{{
  "domains": [
    {{"name": "...", "definition": "...", "clusters": [0, 3]}},
    ...
  ]
}}
Every cluster id 0..{k_max} must appear in exactly one domain's "clusters" list (or under "__OUT_OF_THEME__")."""


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))
    clusters = json.loads((WORK / "clusters.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    emb_data = np.load(WORK / "embeddings.npz")
    cent_data = np.load(WORK / "centroids.npz")
    name_by_id = {t["id"]: t["name"] for t in facts["themes"]}

    old_domains = ", ".join(d["name"] for d in facts["vocab"]["domains"])
    old_subs = ", ".join(s["name"] for s in facts["vocab"]["subdomains"][::3])

    out = {}
    for tid, cinfo in clusters.items():
        theme = name_by_id[tid]
        papers = samples["by_theme"][tid]
        emb = emb_data[tid]
        cents = cent_data[tid]
        labels = cinfo["labels"]
        k = cinfo["k"]

        blocks = []
        rep_store = {}
        for c in range(k):
            reps, snippets, size = representatives(emb, labels, cents[c], c, papers)
            rep_store[c] = {"titles": [p["title"] for p in reps], "size": size,
                            "paper_ids": [p["id"] for p in reps]}
            titles = "\n".join(f"  - {p['title']}" for p in reps)
            snip = "\n".join(f"  > {s}" for s in snippets)
            blocks.append(f"Cluster {c} (size {size}):\n{titles}\n{snip}")

        prompt = PROMPT.format(
            theme=theme,
            k=k,
            k_max=k - 1,
            clusters_block="\n\n".join(blocks),
            old_domains=old_domains,
            old_subdomains=old_subs,
        )
        result = ask_json(prompt, max_tokens=3000)
        out[tid] = {"theme": theme, "domains": result["domains"], "cluster_reps": rep_store,
                    "k": k, "n_sampled": len(papers)}
        print(f"{theme}: {len(result['domains'])} domains")
        for d in result["domains"]:
            print(f"   - {d['name']} (clusters {d['clusters']})")

    with open(WORK / "domains_raw.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("done")


if __name__ == "__main__":
    main()
