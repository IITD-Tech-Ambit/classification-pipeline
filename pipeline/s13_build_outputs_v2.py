"""Step 8b: assemble the clean-fix taxonomy-draft-v2.{md,json} (OVERWRITE).

Preserves the first-pass markdown as taxonomy-draft-v1-firstpass.md before overwriting and
prepends a "Changes from first draft" section summarizing the re-derivation.
"""
import json
import shutil
from datetime import date

from common import WORK, OUTPUTS

# fixed presentation order (matches db_facts theme order)
THEME_ORDER = [
    "6a46ea5ece9a42a451a4714a", "6a46ea5ece9a42a451a4714b", "6a46ea5ece9a42a451a4714c",
    "6a46ea5ece9a42a451a4714d", "6a46ea5ece9a42a451a4714f", "6a46ea5ece9a42a451a47150",
    "6a46ea5ece9a42a451a47151", "6a46ea5ece9a42a451a47152", "6a46ea5ece9a42a451a47153",
]


def load_v1_domains():
    p = OUTPUTS / "taxonomy-draft-v2.json"
    if not p.exists():
        return {}
    j = json.loads(p.read_text(encoding="utf-8"))
    return {t["name"]: [d["name"] for d in t["domains"]] for t in j["themes"]}


def main():
    final = json.loads((WORK / "domains_final_v2.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    conf = json.loads((WORK / "confusion_v2.json").read_text(encoding="utf-8"))
    usage = json.loads((WORK / "llm_usage.json").read_text(encoding="utf-8"))
    embed_model = (WORK / "embed_model.txt").read_text(encoding="utf-8").strip()
    theme_meta = {t["id"]: t for t in facts["themes"]}
    v1_domains = load_v1_domains()

    # preserve first pass
    md_path = OUTPUTS / "taxonomy-draft-v2.md"
    if md_path.exists():
        shutil.copyfile(md_path, OUTPUTS / "taxonomy-draft-v1-firstpass.md")
    js_path = OUTPUTS / "taxonomy-draft-v2.json"
    if js_path.exists():
        shutil.copyfile(js_path, OUTPUTS / "taxonomy-draft-v1-firstpass.json")

    md = []
    md.append("# Research Ambit Taxonomy Draft v2 (clean fix) — For Team Review")
    md.append(
        f"\n_Drafted {date.today().isoformat()} from the live paper corpus "
        f"({facts['n_papers']:,} papers in `researchmetadatascopus`). "
        f"Embeddings: `{embed_model}`; clustering: KMeans with silhouette-based k selection on "
        f"**theme-corrected** pools; theme correction, naming and scope notes: `claude-haiku-4-5`._\n"
    )

    # ---------- changes from first draft ----------
    md.append("## Changes from the first draft\n")
    md.append(
        "The first draft derived domains from paper pools sampled using **v1 theme labels**, "
        "which are only ~2/3 accurate. Those pools were contaminated, so some first-draft domains "
        "were artifacts of v1 misclassifications. In this clean fix, every one of the "
        f"{conf['n_total_sampled']:,} sampled papers (the ~5,450 theme sample + the 500 "
        "previously-unclassified sample) was re-assigned to its single best-fit theme by "
        "`claude-haiku-4-5` (title + abstract), and domains were re-derived by clustering the "
        "resulting **clean** pools.\n"
    )
    md.append(
        f"- **{conf['moved_theme']:,} of {conf['n_from_v1_themes']:,} theme-labelled papers "
        f"({conf['pct_moved']:.0%}) changed theme** versus their v1 label; "
        f"{conf['stayed_theme']:,} stayed. **{conf['n_unclassifiable']}** items were flagged "
        "non-research (editorials / front-matter / prefaces / no-abstract errata) and filtered "
        "out at ingestion rather than given a domain.\n"
    )
    md.append("- Largest v1→v2 theme migrations:\n")
    for m in conf["biggest_migrations"][:8]:
        md.append(f"  - {m['count']} papers: {m['from']} → {m['to']}")
    md.append("")
    md.append("**Known first-draft domains removed / renamed / re-homed:**\n")
    md.append("- AI/ML — removed **Quantum Computing & Algorithms** (it was pure mathematics / "
              "dynamical-systems papers, not quantum computing; genuine quantum-algorithm work is "
              "sparse in the corpus). The mathematics now reads as **Control Systems & Linear "
              "Dynamical Systems** and **Algorithms & Computational Complexity**.")
    md.append("- AI/ML — removed **Materials Informatics & ML for Physics** (it held non-ML "
              "materials papers, which the theme correction moved to Advanced Materials, Quantum "
              "Technologies or Energy).")
    md.append("- AI/ML — **Plasma Physics & Computational Fluid Dynamics** is split: genuine CFD/"
              "flow analysis stays as **Computational Fluid Dynamics & Flow Analysis**, while "
              "plasma-wave physics is re-homed to Next-Gen Communication.")
    md.append("- Next-Gen Communication — plasma-wave papers are consolidated into a single home, "
              "**Plasma-Wave & Electromagnetic Interactions** (previously scattered across AI/ML "
              "and Communication).")
    md.append("- Smart & Sustainable Infrastructure — the first draft's **Materials & "
              "Sustainability in Construction** had absorbed pipeline-slurry and microfibre-"
              "pollution papers; the clean pool splits construction/geotechnical/water/hydrology "
              "topics into distinct domains and routes multiphase-flow papers to Manufacturing.")
    md.append("- Healthcare & MedTech — **energy/forecasting papers no longer pollute the neural-"
              "network domain** (they moved to Energy/AI-ML); the clean pool yields discrete "
              "clinical domains and a dedicated **Neuroscience & Neurophysiology** domain.")
    md.append("")
    md.append("**Pre-approved domains added (reviewer decisions):** "
              "*Library Science & Information Management* and *Digital Transformation & IT "
              "Applications* (Social Sciences, Humanities & Management); "
              "*Neuroscience & Neurophysiology* (Healthcare & MedTech); "
              "*Environmental Assessment & Land Use Management* (Energy, Sustainability & Climate "
              "Change).\n")

    md.append("## Rules of the taxonomy\n")
    md.append("- **Two levels**: 9 fixed thematic areas (names unchanged from v1) → 5–10 domains "
              "each. Each domain belongs to exactly one theme.")
    md.append("- **Single label**: every paper gets exactly one theme and one domain within it.")
    md.append("- **No overlaps**: domain definitions within a theme are mutually exclusive; "
              "cross-theme boundary calls are settled by the tie-break rules in each scope note, "
              "and no domain name appears under two themes.")
    md.append("- Domains were derived by clustering **theme-corrected** paper samples, so "
              "estimated shares are of each theme's corrected sample pool (rough, ±5pp).")

    for tid in THEME_ORDER:
        t = final[tid]
        meta = theme_meta[tid]
        md.append(f"\n---\n\n## {t['theme']}")
        md.append(
            f"\n_v1-assigned papers: {meta['assigned_papers_v1']:,} · corrected sample pool: "
            f"{t['n_pool']}"
            + (f" (+{t['n_out_of_theme']} off-theme dropped)" if t.get("n_out_of_theme") else "")
            + f" · clusters found: {t['k']} · domains: {len(t['domains'])}_\n"
        )
        md.append(f"**Scope.** {t['scope_note']}\n")
        md.append("| Domain | Definition | Example papers (from corrected pool) | Est. share |")
        md.append("|---|---|---|---|")
        rows = []
        for d in t["domains"]:
            examples = "<br>".join(f"• {x}" for x in d["examples"][:5])
            rows.append((d["share"],
                         f"| **{d['name']}** | {d['definition']} | {examples} | {d['share']:.0%} |"))
        for _, row in sorted(rows, key=lambda r: -r[0]):
            md.append(row)

    # theme-correction summary
    md.append("\n---\n\n## Theme-correction summary (v1 → v2)\n")
    md.append(f"Of {conf['n_from_v1_themes']:,} theme-labelled sampled papers, "
              f"{conf['moved_theme']:,} ({conf['pct_moved']:.0%}) were re-assigned to a different "
              f"theme and {conf['stayed_theme']:,} kept their theme; {conf['n_unclassifiable']} "
              "items were non-research. Per-theme retained purity of the v1 sample:\n")
    md.append("| Theme | v1 sampled | kept in-theme | v1 purity | corrected pool |")
    md.append("|---|---|---|---|---|")
    for ts in sorted(conf["per_theme"], key=lambda x: -x["v2_pool_size"]):
        md.append(f"| {ts['theme']} | {ts['v1_sampled']} | {ts['kept_from_own_v1']} | "
                  f"{ts['purity_v1']:.0%} | {ts['v2_pool_size']} |")
    md.append("\nWhere the previously-unclassified sample landed:\n")
    for k, v in conf["unclassified_sample_routed_to"].items():
        md.append(f"- {k}: {v}")

    md.append("\n---\n\n## Notes for the team\n")
    md.append("1. Estimated shares come from theme-corrected samples (~400–770 papers/theme); "
              "treat them as rough (±5pp).")
    md.append("2. A small residue of clusters was genuinely off-theme with no home among the 9 "
              "themes (pure mathematics, high-energy/nuclear physics). These were dropped from "
              "the domain lists and should be handled by the v2 classifier's own "
              "'unclassifiable/out-of-scope' path.")
    md.append("3. 'Library Science & Information Management' is a small but real domain (~3% of "
              "the Social Sciences pool); it and the other pre-approved additions are retained by "
              "reviewer decision.")

    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {md_path}")

    # ---------- json ----------
    jout = {
        "version": "v2-draft-cleanfix",
        "generated": date.today().isoformat(),
        "embedding_model": embed_model,
        "method": "theme-corrected pools (claude-haiku-4-5) -> KMeans/silhouette -> LLM naming + "
                  "cross-theme dedup",
        "themes": [],
    }
    for tid in THEME_ORDER:
        t = final[tid]
        meta = theme_meta[tid]
        jout["themes"].append({
            "id": tid,
            "name": meta["name"],
            "slug": meta.get("slug"),
            "scope_note": t["scope_note"],
            "corrected_pool_size": t["n_pool"],
            "domains": [
                {
                    "name": d["name"],
                    "definition": d["definition"],
                    "estimated_share_of_theme": d["share"],
                    "example_titles": d["examples"][:5],
                }
                for d in t["domains"]
            ],
        })
    jout["theme_correction"] = {
        "n_sampled": conf["n_total_sampled"],
        "moved_theme": conf["moved_theme"],
        "stayed_theme": conf["stayed_theme"],
        "pct_moved": conf["pct_moved"],
        "n_unclassifiable": conf["n_unclassifiable"],
        "biggest_migrations": conf["biggest_migrations"][:12],
    }
    js_path.write_text(json.dumps(jout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {js_path}")
    print(f"LLM usage: {usage}")


if __name__ == "__main__":
    main()
