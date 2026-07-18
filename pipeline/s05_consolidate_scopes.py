"""Step 5: global cross-theme dedup pass, then per-theme scope notes with tie-break rules."""
import json

from common import WORK
from llm import ask_json

TIEBREAKS = """Known overlap zones and REQUIRED tie-break rules (must be reflected in scope notes):
- AI/ML vs Quantum: quantum algorithms / quantum computing / quantum information processing go to "AI/ML, Supercomputing & Quantum Computing"; quantum devices, quantum materials, semiconductor physics/fabrication go to "Quantum Technologies & Semiconductor Technology".
- Healthcare vs Advanced Materials: biomaterials designed for a specific clinical/therapeutic application -> Healthcare & MedTech; general biomaterial synthesis/characterization -> Advanced Materials & Devices.
- Energy vs Smart Infrastructure: energy generation/storage/conversion technologies -> Energy theme; energy-efficient buildings, urban energy systems, smart grids as infrastructure -> Smart & Sustainable Infrastructure.
- Manufacturing vs Materials: processing/production/joining/machining of materials -> Manufacturing & Industry 4.0; discovery/synthesis/characterization of new materials -> Advanced Materials & Devices.
- Next-Gen Communication vs AI/ML: networking, wireless systems, signal transmission -> Next-Gen Communication; learning algorithms and AI methods (even applied to networks) -> AI/ML theme if the contribution is the method, Communication if the contribution is the system.
- Social Sciences, Humanities & Management is the catch-all for economics, policy, education, linguistics, design studies, management, and pure humanities work."""

DEDUP_PROMPT = """You are finalizing a two-level research taxonomy (9 fixed themes, each with 5-10 domains).
Here is the current draft — theme name followed by its domains:

{summary}

TASK: Find problems ACROSS themes:
1. The same or nearly-identical domain appearing under two themes (e.g. "Machine Learning" under two themes).
2. Domain names that don't make their home theme obvious and would confuse a classifier.

{tiebreaks}

For each problem, propose a fix as a rename (make the name theme-specific, e.g. "Machine Learning for Healthcare" under Healthcare) or a merge within its theme. Do NOT move domains between themes. Do NOT touch domains that are fine. Keep names Title Case, 2-6 words.

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


def main():
    raw = json.loads((WORK / "domains_raw.json").read_text(encoding="utf-8"))

    # drop __OUT_OF_THEME__ pseudo-domains (kept aside for reporting) and dedup
    # any cluster that Claude assigned to more than one domain (keep first occurrence)
    out_of_theme = {}
    for tid, t in raw.items():
        kept = []
        seen_clusters = set()
        for d in t["domains"]:
            if d["name"].strip() == "__OUT_OF_THEME__":
                out_of_theme.setdefault(t["theme"], [])
                out_of_theme[t["theme"]] = sorted(set(out_of_theme[t["theme"]]) | set(d["clusters"]))
                seen_clusters.update(d["clusters"])
                continue
            d["clusters"] = [c for c in d["clusters"] if c not in seen_clusters]
            seen_clusters.update(d["clusters"])
            if d["clusters"]:
                kept.append(d)
        t["domains"] = kept

    summary = "\n".join(
        f"- {t['theme']}: " + "; ".join(d["name"] for d in t["domains"]) for t in raw.values()
    )
    fixes = ask_json(DEDUP_PROMPT.format(summary=summary, tiebreaks=TIEBREAKS), max_tokens=3000)
    print(f"dedup fixes: {len(fixes['fixes'])}")

    for fix in fixes["fixes"]:
        for t in raw.values():
            if t["theme"] != fix["theme"]:
                continue
            for d in list(t["domains"]):
                if d["name"] == fix["old_name"]:
                    if fix["action"] == "rename":
                        print(f"  rename [{t['theme']}] {d['name']} -> {fix['new_name']}")
                        d["name"] = fix["new_name"]
                        if fix.get("new_definition"):
                            d["definition"] = fix["new_definition"]
                    elif fix["action"] == "merge_into":
                        target = next((x for x in t["domains"] if x["name"] == fix["new_name"]), None)
                        if target and target is not d:
                            print(f"  merge  [{t['theme']}] {d['name']} -> {target['name']}")
                            target["clusters"] = sorted(set(target["clusters"]) | set(d["clusters"]))
                            t["domains"].remove(d)

    # scope notes, one call per theme
    for tid, t in raw.items():
        domains_txt = "\n".join(f"- {d['name']}: {d['definition']}" for d in t["domains"])
        others = "\n".join(
            f"- {x['theme']}: " + "; ".join(d["name"] for d in x["domains"])
            for xid, x in raw.items() if xid != tid
        )
        examples = "\n".join(
            f"- {title}"
            for d in t["domains"][:6]
            for title in t["cluster_reps"][str(d["clusters"][0])]["titles"][:2]
        )
        res = ask_json(
            SCOPE_PROMPT.format(theme=t["theme"], domains=domains_txt, others=others,
                                tiebreaks=TIEBREAKS, examples=examples),
            max_tokens=1500,
        )
        t["scope_note"] = res["scope_note"]
        print(f"scope note done: {t['theme']}")

    raw["__out_of_theme_clusters__"] = out_of_theme
    with open(WORK / "domains_final.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    print("done")


if __name__ == "__main__":
    main()
