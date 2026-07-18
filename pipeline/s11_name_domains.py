"""Step 4b: name+consolidate clusters of each CORRECTED pool into 5-10 domains.

One Claude call per theme. The prompt carries the known-bad-domain guidance from the
first draft and the pre-approved MANDATORY domain additions for the relevant themes.
"""
import json

import numpy as np

from common import WORK
from llm import ask_json

N_TITLES = 16
N_SNIPPETS = 3

# Pre-approved domains that MUST appear under the given theme (by theme id).
MANDATORY = {
    "6a46ea5ece9a42a451a47153": [  # Social Sciences, Humanities & Management
        ("Library Science & Information Management",
         "Library and information science, information organization and retrieval practice, "
         "scholarly communication, digital libraries, and knowledge/records management as a "
         "professional and institutional discipline."),
        ("Digital Transformation & IT Applications",
         "Organizational adoption of information technology, information systems, e-governance, "
         "digital service delivery and the managerial/social study of digital transformation "
         "(distinct from NLP/ML methods and from communication-network engineering)."),
    ],
    "6a46ea5ece9a42a451a4714d": [  # Healthcare & MedTech
        ("Neuroscience & Neurophysiology",
         "Cellular, molecular and systems neuroscience and neurophysiology, including neural "
         "signalling, brain injury and neurological-condition mechanisms (distinct from "
         "computational biomechanics and from clinical decision-support)."),
    ],
    "6a46ea5ece9a42a451a4714c": [  # Energy, Sustainability & Climate Change
        ("Environmental Assessment & Land Use Management",
         "Terrestrial, watershed and ecosystem environmental assessment, land-use and land-cover "
         "change, natural-resource and water-resource management and ecosystem services "
         "(complements atmospheric/air-quality work with land/water-focused environmental study)."),
    ],
}

# Known-bad first-draft domains to keep the model honest about (per theme id).
KNOWN_BAD_NOTES = {
    "6a46ea5ece9a42a451a4714a": (
        "In the first draft this AI/ML pool was contaminated. Watch for: a spurious "
        "'Quantum Computing & Algorithms' domain that was actually pure math / dynamical "
        "systems; a 'Materials Informatics & ML for Physics' domain that held non-ML materials "
        "papers; and plasma-physics / CFD papers that do NOT belong here. Applied mathematics "
        "and dynamical-systems methods may form a legitimate domain, but do not label them as "
        "quantum computing. Genuinely off-theme clusters go to __OUT_OF_THEME__."),
    "6a46ea5ece9a42a451a47152": (
        "In the first draft a 'Materials & Sustainability in Construction' domain wrongly "
        "absorbed pipeline-slurry and microfibre-pollution papers. Keep construction materials "
        "coherent; route clearly off-theme clusters to __OUT_OF_THEME__."),
}

PROMPT = """You are designing a research-paper taxonomy for IIT Delhi's research portal.

Theme (FIXED, do not rename): "{theme}"

Below are {k} clusters of papers that genuinely belong to this theme (the pool was already
theme-corrected, so contamination from other themes is largely removed). For each cluster you
see its size, representative titles, and a few abstract snippets.

{clusters_block}
{known_bad}
{mandatory}
TASK: Consolidate these clusters into a clean set of 5 to 10 DOMAINS for this theme (this range
is a hard requirement).
Rules:
- Domains must be mutually exclusive within the theme.
- Merge clusters that are the same topic; each cluster maps to exactly one domain.
- Names: academic, browsable, Title Case, concise (2-6 words).
- Each domain gets a 1-2 sentence definition of what belongs in it.
- If a cluster is clearly noise or papers belonging to a DIFFERENT theme, map it to the domain
  name "__OUT_OF_THEME__".
{mandatory_rule}
Return ONLY JSON:
{{"domains": [{{"name": "...", "definition": "...", "clusters": [0, 3]}}, ...]}}
Every cluster id 0..{k_max} must appear in exactly one domain's "clusters" list (or under
"__OUT_OF_THEME__"). Mandatory domains may have an empty "clusters" list if no cluster matches."""


def representatives(emb, labels, centroid, cluster_id, pool_papers):
    idx = np.where(np.array(labels) == cluster_id)[0]
    if len(idx) == 0:
        return [], [], 0
    sims = emb[idx] @ centroid / (np.linalg.norm(centroid) + 1e-9)
    order = idx[np.argsort(-sims)]
    reps = [pool_papers[i] for i in order[:N_TITLES]]
    snippets = [p["abstract"][:320] for p in reps if p.get("abstract")][:N_SNIPPETS]
    return reps, snippets, len(idx)


def main():
    pools = json.loads((WORK / "pools_v2.json").read_text(encoding="utf-8"))
    clusters = json.loads((WORK / "clusters_v2.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    flat = np.load(WORK / "emb_flat.npz")["emb"]
    cent_data = np.load(WORK / "centroids_v2.npz")
    pool_index = pools["pool_index"]
    papers_by_id = pools["papers"]
    name_by_id = {t["id"]: t["name"] for t in facts["themes"]}

    out = {}
    for tid, cinfo in clusters.items():
        theme = name_by_id[tid]
        pids = cinfo["pids"]
        idx = np.array([pool_index[p] for p in pids])
        emb = flat[idx]
        cents = cent_data[tid]
        labels = cinfo["labels"]
        k = cinfo["k"]
        pool_papers = [papers_by_id[p] for p in pids]

        blocks = []
        rep_store = {}
        for c in range(k):
            reps, snippets, size = representatives(emb, labels, cents[c], c, pool_papers)
            rep_store[c] = {"titles": [p["title"] for p in reps], "size": size,
                            "paper_ids": [p["id"] for p in reps]}
            titles = "\n".join(f"  - {p['title']}" for p in reps[:12])
            snip = "\n".join(f"  > {s}" for s in snippets)
            blocks.append(f"Cluster {c} (size {size}):\n{titles}\n{snip}")

        mand = MANDATORY.get(tid, [])
        if mand:
            mand_txt = "\nMANDATORY domains (pre-approved by the reviewer — you MUST include each "
            mand_txt += "of these exactly, adjusting definition wording only slightly if needed):\n"
            mand_txt += "\n".join(f"  * {n}: {d}" for n, d in mand) + "\n"
            mand_rule = ("- You MUST include every MANDATORY domain listed above as its own "
                         "domain. Map any matching clusters to it; if none match, still include "
                         "it with an empty clusters list.")
        else:
            mand_txt = ""
            mand_rule = ""

        kb = KNOWN_BAD_NOTES.get(tid, "")
        kb = ("\nReviewer guidance on first-draft problems in this theme:\n" + kb + "\n") if kb else ""

        prompt = PROMPT.format(
            theme=theme, k=k, k_max=k - 1,
            clusters_block="\n\n".join(blocks),
            known_bad=kb, mandatory=mand_txt, mandatory_rule=mand_rule,
        )
        result = ask_json(prompt, max_tokens=3500)
        out[tid] = {"theme": theme, "domains": result["domains"], "cluster_reps": rep_store,
                    "k": k, "n_pool": len(pids)}
        print(f"{theme}: {len(result['domains'])} domains")
        for d in result["domains"]:
            print(f"   - {d['name']} (clusters {d['clusters']})")

    (WORK / "domains_raw_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
