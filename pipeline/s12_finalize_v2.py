"""Step 5b/6b/7b: finalize the v2 domains.

- Drop __OUT_OF_THEME__ clusters (kept aside for reporting).
- Build a centroid for every domain and assign EVERY pool paper to its nearest domain
  centroid (one uniform rule), which yields shares + real example titles from the CLEAN pool.
- Guarantee the pre-approved MANDATORY domains exist (embedding their description with the
  same BGE model when no cluster seeded them).
- Enforce the hard 5-10 domains-per-theme range (merge smallest non-mandatory domains).
- Global cross-theme dedup pass (rename/merge) so no domain name repeats across themes.
- Refresh per-theme scope notes with the v1 tie-break rules preserved.
"""
import json
from collections import defaultdict

import numpy as np

from common import WORK
from llm import ask_json
from s11_name_domains import MANDATORY

MAND_NAMES = {n for lst in MANDATORY.values() for n, _ in lst}

TIEBREAKS = """Known overlap zones and REQUIRED tie-break rules (must be reflected in scope notes):
- AI/ML vs Quantum: quantum algorithms / quantum information / quantum computing go to "AI/ML, Supercomputing & Quantum Computing"; quantum devices, quantum materials, semiconductor physics/fabrication go to "Quantum Technologies & Semiconductor Technology".
- Healthcare vs Advanced Materials: biomaterials designed for a specific clinical/therapeutic application -> Healthcare & MedTech; general biomaterial synthesis/characterization -> Advanced Materials & Devices.
- Energy vs Smart Infrastructure: energy generation/storage/conversion technologies -> Energy theme; energy-efficient buildings, urban energy systems, smart grids as infrastructure -> Smart & Sustainable Infrastructure.
- Manufacturing vs Materials: processing/production/joining/machining of materials -> Manufacturing & Industry 4.0; discovery/synthesis/characterization of new materials -> Advanced Materials & Devices.
- Next-Gen Communication vs AI/ML: networking, wireless systems, signal transmission -> Next-Gen Communication; learning algorithms and AI methods -> AI/ML if the contribution is the method. Plasma-wave / electromagnetic-plasma physics lives in Next-Gen Communication.
- Social Sciences, Humanities & Management is the catch-all for economics, policy, education, linguistics, design studies, management, library/information science, and organizational digital transformation."""

DEDUP_PROMPT = """You are finalizing a two-level research taxonomy (9 fixed themes, each with 5-10 domains).
Here is the current draft — theme name followed by its domains:

{summary}

TASK: Find problems ACROSS themes:
1. The same or nearly-identical domain name appearing under two themes.
2. Domain names that don't make their home theme obvious and would confuse a classifier.

{tiebreaks}

For each problem, propose a fix as a rename (make the name theme-specific) or a merge within its theme. Do NOT move domains between themes. Do NOT touch domains that are fine. Keep names Title Case, 2-6 words. Never rename or merge away any of these pre-approved domains: {protected}.

Return ONLY JSON:
{{"fixes": [{{"theme": "...", "old_name": "...", "action": "rename"|"merge_into", "new_name": "...", "new_definition": "..."}}]}}
If merging, "new_name" is the surviving domain in the SAME theme. new_definition may be null for merges."""

SCOPE_PROMPT = """You are writing the scope note for one theme of IIT Delhi's research taxonomy.

Theme: "{theme}"
Its domains:
{domains}

All other themes and their domains (for boundary awareness):
{others}

{tiebreaks}

Example paper titles actually sampled under this theme:
{examples}

TASK: Write a scope note of 5-8 sentences: (a) what belongs in this theme, (b) what is explicitly excluded and where it goes instead, (c) the explicit tie-break rules above that involve this theme, phrased operationally ("If a paper does X, assign it to Y"). Ground it in the kinds of papers shown. Plain prose, no bullet lists.

Return ONLY JSON: {{"scope_note": "..."}}"""


# Corrections to the s11 naming output where the LLM wrongly shunted an in-theme cluster to
# __OUT_OF_THEME__. Grounded in the reviewer requirements: plasma-wave physics has a single
# home (Next-Gen Communication) and industrial bioprocessing belongs in Manufacturing.
TID_NEXTGEN = "6a46ea5ece9a42a451a47150"
TID_MFG = "6a46ea5ece9a42a451a4714f"
TID_AIML = "6a46ea5ece9a42a451a4714a"

ADD_DOMAINS = {
    TID_NEXTGEN: [{
        "name": "Plasma-Wave & Electromagnetic Interactions",
        "definition": "Nonlinear interaction of electromagnetic waves and intense laser beams "
                      "with plasma media: plasma-wave and wakefield generation, self-focusing, "
                      "filamentation, solitons and harmonic generation in plasma-filled structures.",
        "clusters": [2],
    }],
    TID_MFG: [{
        "name": "Bioprocess & Fermentation Engineering",
        "definition": "Industrial-scale bioprocessing and fermentation as manufacturing "
                      "operations: fed-batch and continuous cultivation, bioconversion, "
                      "substrate-feeding strategies and downstream processing of biological products.",
        "clusters": [8],
    }],
}
# Append a cluster to whichever existing domain currently owns a reference cluster id.
APPEND_CLUSTER_TO_OWNER_OF = {
    TID_AIML: [(6, 0)],  # fold nonlinear-dynamics cluster 6 into the domain that owns cluster 0
}


def apply_naming_overrides(raw):
    for tid, adds in ADD_DOMAINS.items():
        t = raw[tid]
        for add in adds:
            # remove the cluster from any __OUT_OF_THEME__ pseudo-domain so it is kept
            for d in t["domains"]:
                if d["name"].strip() == "__OUT_OF_THEME__":
                    d["clusters"] = [c for c in d["clusters"] if c not in add["clusters"]]
            t["domains"].append(dict(add))
    for tid, pairs in APPEND_CLUSTER_TO_OWNER_OF.items():
        t = raw[tid]
        for new_c, owner_c in pairs:
            for d in t["domains"]:
                if d["name"].strip() == "__OUT_OF_THEME__":
                    d["clusters"] = [c for c in d["clusters"] if c != new_c]
            owner = next((d for d in t["domains"]
                          if d["name"].strip() != "__OUT_OF_THEME__" and owner_c in d["clusters"]), None)
            if owner and new_c not in owner["clusters"]:
                owner["clusters"].append(new_c)


def unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    raw = json.loads((WORK / "domains_raw_v2.json").read_text(encoding="utf-8"))
    clusters = json.loads((WORK / "clusters_v2.json").read_text(encoding="utf-8"))
    pools = json.loads((WORK / "pools_v2.json").read_text(encoding="utf-8"))
    flat = np.load(WORK / "emb_flat.npz")["emb"]
    pool_index = pools["pool_index"]
    papers_by_id = pools["papers"]

    # 0) rescue in-theme clusters the naming step wrongly sent to __OUT_OF_THEME__
    apply_naming_overrides(raw)

    # 1) strip __OUT_OF_THEME__ and de-duplicate clusters assigned to multiple domains
    out_of_theme = {}
    for tid, t in raw.items():
        kept, seen = [], set()
        for d in t["domains"]:
            if d["name"].strip() == "__OUT_OF_THEME__":
                out_of_theme[t["theme"]] = sorted(set(out_of_theme.get(t["theme"], [])) | set(d["clusters"]))
                seen.update(d["clusters"])
                continue
            d["clusters"] = [c for c in d["clusters"] if c not in seen]
            seen.update(d["clusters"])
            kept.append(d)
        t["domains"] = kept

    # 2) build embeddings need: BGE only if some mandatory domain has no clusters
    need_bge = any(
        d["clusters"] == [] for t in raw.values() for d in t["domains"]
    )
    bge = None
    if need_bge:
        from sentence_transformers import SentenceTransformer
        bge = SentenceTransformer((WORK / "embed_model.txt").read_text(encoding="utf-8").strip(),
                                  device="cpu")

    # map theme name -> out-of-theme cluster ids
    oot_by_tid = {}
    for tid, t in raw.items():
        oot_by_tid[tid] = set(out_of_theme.get(t["theme"], []))

    # 3) per theme: centroid per domain, then assign every IN-THEME pool paper to nearest domain
    for tid, t in raw.items():
        all_pids = clusters[tid]["pids"]
        all_labels = np.array(clusters[tid]["labels"])
        oot = oot_by_tid[tid]
        keep_mask = ~np.isin(all_labels, list(oot)) if oot else np.ones(len(all_pids), bool)
        pids = [p for p, k in zip(all_pids, keep_mask) if k]
        labels = all_labels[keep_mask]
        idx = np.array([pool_index[p] for p in pids])
        emb = flat[idx]
        t["n_out_of_theme"] = int((~keep_mask).sum())

        def domain_centroid(d):
            if d["clusters"]:
                mask = np.isin(labels, d["clusters"])
                if mask.sum() > 0:
                    return unit(emb[mask].mean(axis=0))
            # empty mandatory domain: anchor the centroid in the real papers nearest to its
            # description so it competes for its own topic instead of collapsing to a neighbor.
            vec = bge.encode([f"{d['name']}. {d['definition']}"], normalize_embeddings=True)[0]
            sims = emb @ unit(vec)
            seed = np.argsort(-sims)[:15]
            return unit(emb[seed].mean(axis=0))

        # enforce upper bound 10: merge smallest non-mandatory by centroid similarity
        def assign(domains):
            cents = np.vstack([domain_centroid(d) for d in domains])
            sims = emb @ cents.T
            best = sims.argmax(axis=1)
            return best, cents

        while len(t["domains"]) > 10:
            best, cents = assign(t["domains"])
            sizes = np.bincount(best, minlength=len(t["domains"]))
            # candidate to remove: smallest non-mandatory domain
            order = np.argsort(sizes)
            victim = next((i for i in order if t["domains"][i]["name"] not in MAND_NAMES), int(order[0]))
            vc = cents[victim]
            others = [i for i in range(len(t["domains"])) if i != victim]
            tgt = max(others, key=lambda i: float(cents[i] @ vc))
            t["domains"][tgt]["clusters"] = sorted(set(t["domains"][tgt]["clusters"])
                                                   | set(t["domains"][victim]["clusters"]))
            del t["domains"][victim]

        # final assignment for shares + examples
        best, cents = assign(t["domains"])
        for di, d in enumerate(t["domains"]):
            members = np.where(best == di)[0]
            sims = emb[members] @ cents[di]
            order = members[np.argsort(-sims)]
            ex = []
            for j in order:
                p = papers_by_id[pids[j]]
                if p["title"] and p["title"] not in [e["title"] for e in ex]:
                    ex.append({"title": p["title"], "id": p["id"], "has_abs": bool(p.get("abstract"))})
                if len(ex) >= 8:
                    break
            # prefer examples with abstracts, keep 5
            ex_sorted = sorted(ex, key=lambda e: (not e["has_abs"]))[:5]
            d["share"] = round(float(len(members)) / len(pids), 3)
            d["n_members"] = int(len(members))
            d["examples"] = [e["title"] for e in ex_sorted]
        t["n_pool"] = len(pids)

    # 4) global cross-theme dedup
    summary = "\n".join(f"- {t['theme']}: " + "; ".join(d["name"] for d in t["domains"])
                        for t in raw.values())
    fixes = ask_json(DEDUP_PROMPT.format(summary=summary, tiebreaks=TIEBREAKS,
                                         protected=", ".join(sorted(MAND_NAMES))), max_tokens=3000)
    print(f"dedup fixes: {len(fixes['fixes'])}")
    for fix in fixes["fixes"]:
        for t in raw.values():
            if t["theme"] != fix["theme"]:
                continue
            for d in list(t["domains"]):
                if d["name"] != fix["old_name"] or d["name"] in MAND_NAMES:
                    continue
                if fix["action"] == "rename":
                    print(f"  rename [{t['theme'][:25]}] {d['name']} -> {fix['new_name']}")
                    d["name"] = fix["new_name"]
                    if fix.get("new_definition"):
                        d["definition"] = fix["new_definition"]
                elif fix["action"] == "merge_into":
                    target = next((x for x in t["domains"] if x["name"] == fix["new_name"]), None)
                    if target and target is not d:
                        print(f"  merge  [{t['theme'][:25]}] {d['name']} -> {target['name']}")
                        target["n_members"] = target.get("n_members", 0) + d.get("n_members", 0)
                        target["share"] = round(target.get("share", 0) + d.get("share", 0), 3)
                        t["domains"].remove(d)

    # 5) scope notes
    for tid, t in raw.items():
        domains_txt = "\n".join(f"- {d['name']}: {d['definition']}" for d in t["domains"])
        others = "\n".join(f"- {x['theme']}: " + "; ".join(d["name"] for d in x["domains"])
                           for xid, x in raw.items() if xid != tid)
        examples = "\n".join(f"- {tt}" for d in t["domains"][:6] for tt in d["examples"][:2])
        res = ask_json(SCOPE_PROMPT.format(theme=t["theme"], domains=domains_txt, others=others,
                                           tiebreaks=TIEBREAKS, examples=examples), max_tokens=1500)
        t["scope_note"] = res["scope_note"]
        print(f"scope note done: {t['theme'][:40]} ({len(t['domains'])} domains)")

    raw["__out_of_theme_clusters__"] = out_of_theme
    (WORK / "domains_final_v2.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    # sanity print
    print("\nfinal per-theme domain counts:")
    for tid, t in raw.items():
        if tid == "__out_of_theme_clusters__":
            continue
        flag = "" if 5 <= len(t["domains"]) <= 10 else "  <-- OUT OF RANGE"
        print(f"  {t['theme'][:45]:45} {len(t['domains'])}{flag}")
    print("done")


if __name__ == "__main__":
    main()
