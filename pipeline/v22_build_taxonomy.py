"""Stage 1: build taxonomy-draft-v22 from v2 with audit-driven gap fills.

Constraints: each theme 5-10 domains; no duplicate domain names; JSON valid.
Healthcare is already at 10 → sharpen Clinical Biosensors (no net add).
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from common import OUTPUTS, WORK

SRC = OUTPUTS / "taxonomy-draft-v2.json"
PRE_BACKUP = OUTPUTS / "taxonomy-draft-v2-pre-v22.json"
OUT_JSON = OUTPUTS / "taxonomy-draft-v22.json"
OUT_MD = OUTPUTS / "taxonomy-draft-v22.md"
CHECK = WORK / "stage1_v22_taxonomy_check.json"

GLOBAL_RULES = [
    (
        "OUT-OF-SCOPE: particle-accelerator RF / LLRF / cavity phase-locking / "
        "superconducting-accelerator instrumentation with no applied power-grid, "
        "communications, or manufacturing target → unclassifiable=true with reason "
        "starting 'out_of_scope: accelerator RF instrumentation'."
    ),
    (
        "OUT-OF-SCOPE / EDGE: automotive fuel-additive screening for engine-deposit "
        "control with no materials-process or manufacturing contribution → "
        "unclassifiable=true with reason 'out_of_scope: fuel-additive engine-deposit "
        "screening' (do NOT force into Materials, Joining & Mechanical Behavior)."
    ),
    (
        "TIE-BREAK: downstream biopharma PAT / mAb / biosimilar quality, aggregation, "
        "glycosylation, 2D-LC characterization → Healthcare / Biopharmaceutical "
        "Manufacturing & Quality (NOT Manufacturing / Biomanufacturing & Fermentation)."
    ),
    (
        "TIE-BREAK: mechanism-design / peer-prediction / algorithmic game-theory / "
        "incentive-compatible algorithms → AI/ML / Algorithms & Computational "
        "Complexity (NOT Social Sciences / Digital Culture & Consumer Experience)."
    ),
    (
        "TIE-BREAK: thermoelectric / Seebeck / waste-heat-to-electricity MATERIALS → "
        "Energy / Thermoelectric & Energy-Harvesting Materials (NOT Energy Storage "
        "Materials; NOT Solar Thermal)."
    ),
    (
        "TIE-BREAK: optical / interferometric metrology instrumentation (white-light "
        "interferometry, interferometric microscopes, displacement metrology) → "
        "Quantum / Optical Metrology & Interferometric Instrumentation (NOT Fiber "
        "Photonic Devices unless the contribution is a fiber component)."
    ),
    (
        "TIE-BREAK: implantable medical device (IMD) wireless power transfer / "
        "inductive / magnetic coupling hardware for implants → Healthcare / Clinical "
        "Biosensors & Implant Bioelectronics (NOT general power electronics)."
    ),
    (
        "TIE-BREAK: computer architecture / VLIW / interconnect / microarchitecture / "
        "memory hierarchy / ISA → AI/ML / Computer Architecture & Systems (NOT "
        "Algorithms & Computational Complexity unless the novelty is pure algorithms)."
    ),
]


def find_theme(tax, name):
    for t in tax["themes"]:
        if t["name"] == name:
            return t
    raise KeyError(name)


def find_domain(theme, name):
    for d in theme["domains"]:
        if d["name"] == name:
            return d
    raise KeyError(f"{theme['name']} :: {name}")


def append_def(theme, domain_name, text):
    d = find_domain(theme, domain_name)
    d["definition"] = d["definition"].rstrip() + "  " + text.strip()


def add_domain(theme, domain):
    names = {d["name"] for d in theme["domains"]}
    if domain["name"] in names:
        raise ValueError(f"duplicate domain {domain['name']} in {theme['name']}")
    if len(theme["domains"]) >= 10:
        raise ValueError(f"theme {theme['name']} already at 10 domains")
    theme["domains"].append(domain)


def build() -> dict:
    if not PRE_BACKUP.exists():
        PRE_BACKUP.write_bytes(SRC.read_bytes())

    tax = deepcopy(json.loads(SRC.read_text(encoding="utf-8")))
    tax["version"] = "v22-gapfill"
    tax["generated"] = "2026-07-18"
    tax["method"] = (
        "v2 baseline + audit-driven gap fills (thermoelectric, optical metrology, "
        "implant bioelectronics sharpening, computer architecture) + explicit "
        "out_of_scope routing and strengthened tie-breaks"
    )
    tax["global_rules"] = GLOBAL_RULES

    energy = find_theme(tax, "Energy, Sustainability & Climate Change")
    add_domain(
        energy,
        {
            "name": "Thermoelectric & Energy-Harvesting Materials",
            "definition": (
                "Materials and material systems for solid-state thermoelectric conversion "
                "and related energy harvesting: Seebeck/Peltier materials, figure-of-merit "
                "(ZT) engineering, magnetically/compositionally tuned thermoelectrics, "
                "waste-heat-to-electricity material stacks. Distinct from Energy Storage "
                "Materials (batteries/supercapacitors/electrodes) and from Solar Thermal "
                "Energy & Heat Transfer Systems (collectors/thermodynamic heat transfer). "
                "Prefer this domain when the primary contribution is the thermoelectric "
                "or harvesting MATERIAL, not a grid inverter or storage electrode."
            ),
            "estimated_share_of_theme": 0.04,
            "example_titles": [
                "Magnetically tuned thermoelectric performance in Heusler alloys",
                "High-ZT thermoelectric skutterudites for waste-heat recovery",
                "Seebeck coefficient engineering in doped chalcogenide thermoelectrics",
            ],
        },
    )
    append_def(
        energy,
        "Energy Storage Materials",
        "EXCLUDES thermoelectric / Seebeck / energy-harvesting materials "
        "(those → Thermoelectric & Energy-Harvesting Materials).",
    )

    quantum = find_theme(tax, "Quantum Technologies & Semiconductor Technology")
    add_domain(
        quantum,
        {
            "name": "Optical Metrology & Interferometric Instrumentation",
            "definition": (
                "Optical and interferometric metrology instruments and methods: "
                "white-light / laser interferometers, interferometric microscopes, "
                "displacement/phase metrology systems, precision optical measurement "
                "instrumentation. Prefer this over Fiber Photonic Devices & Engineering "
                "when the contribution is metrology instrumentation rather than a fiber "
                "component, and over Plasmonic & Fiber Optic Sensors when the core is "
                "interferometric measurement hardware/methods rather than chemical sensing."
            ),
            "estimated_share_of_theme": 0.04,
            "example_titles": [
                "White-light interferometric microscope for surface topography",
                "Phase-shifting interferometry for precision displacement metrology",
                "Compact Michelson interferometer instrumentation for dimensional measurement",
            ],
        },
    )
    append_def(
        quantum,
        "Fiber Photonic Devices & Engineering",
        "TIGHTENED: fiber components, waveguides, and photonic-crystal fiber devices. "
        "Interferometric metrology instruments → Optical Metrology & Interferometric "
        "Instrumentation instead.",
    )

    health = find_theme(tax, "Healthcare & MedTech")
    bios = find_domain(health, "Clinical Biosensors & Point-of-Care Devices")
    bios["name"] = "Clinical Biosensors & Implant Bioelectronics"
    bios["definition"] = (
        "Clinical biosensing platforms, point-of-care diagnostic instruments, AND "
        "implantable medical-device (IMD) power/bioelectronics interfaces: wireless "
        "power transfer, inductive/magnetic coupling for implants, implant telemetry "
        "front-ends, and bioelectronic interfaces whose primary application is clinical "
        "implant hardware. Prefer this over Manufacturing power-electronics domains "
        "when the load is an implant/IMD. Pure biochemical POCT assays without implant "
        "power remain here as clinical biosensors."
    )
    # keep old example titles; add one implant-ish exemplar
    bios.setdefault("example_titles", [])
    bios["example_titles"] = list(bios["example_titles"][:4]) + [
        "Wireless inductive power transfer systems for implantable medical devices"
    ]
    append_def(
        health,
        "Biopharmaceutical Manufacturing & Quality",
        "TIE-BREAK: downstream PAT, mAb aggregation/glycosylation QC, biosimilar "
        "comparability → here (NOT Manufacturing / Biomanufacturing & Fermentation).",
    )

    aiml = find_theme(tax, "AI/ML, Supercomputing & Quantum Computing")
    add_domain(
        aiml,
        {
            "name": "Computer Architecture & Systems",
            "definition": (
                "Computer architecture and systems: VLIW/superscalar/microarchitecture, "
                "on-chip interconnects, memory hierarchy, ISA design, hardware/software "
                "co-design for processors, and related systems-level architecture papers. "
                "Prefer this over Algorithms & Computational Complexity when the novelty "
                "is architectural organization or system microarchitecture rather than "
                "abstract algorithm/complexity theory."
            ),
            "estimated_share_of_theme": 0.08,
            "example_titles": [
                "VLIW architecture design for high-performance embedded processors",
                "On-chip interconnect architectures for many-core systems",
                "Memory hierarchy optimization in modern computer architecture",
            ],
        },
    )
    append_def(
        aiml,
        "Algorithms & Computational Complexity",
        "EXCLUDES computer architecture / VLIW / interconnect microarchitecture "
        "(those → Computer Architecture & Systems). Mechanism-design and "
        "peer-prediction algorithms STAY here (NOT Digital Culture).",
    )

    manuf = find_theme(tax, "Manufacturing & Industry 4.0")
    append_def(
        manuf,
        "Materials, Joining & Mechanical Behavior",
        "Do NOT use for pure automotive fuel-additive engine-deposit screening with "
        "no joining/process contribution (prefer out_of_scope).",
    )
    append_def(
        manuf,
        "Biomanufacturing & Fermentation Processes",
        "Upstream fermentation/bioprocess scale-up. Downstream biopharma PAT/QC → "
        "Healthcare / Biopharmaceutical Manufacturing & Quality.",
    )

    infra = find_theme(tax, "Smart & Sustainable Infrastructure")
    append_def(
        infra,
        "Power Systems & Grid Control",
        "Do NOT force particle-accelerator RF / LLRF / cavity control here; prefer "
        "out_of_scope when there is no applied power-grid contribution.",
    )

    social = find_theme(tax, "Social Sciences, Humanities & Management")
    append_def(
        social,
        "Digital Culture & Consumer Experience",
        "EXCLUDES mechanism-design / peer-prediction / algorithmic game theory "
        "(those → AI/ML Algorithms & Computational Complexity).",
    )

    # theme scope touch-ups
    energy["scope_note"] = (
        energy.get("scope_note", "").rstrip()
        + "  Thermoelectric and solid-state energy-harvesting MATERIALS are in-theme "
        "under Thermoelectric & Energy-Harvesting Materials."
    )
    aiml["scope_note"] = (
        aiml.get("scope_note", "").rstrip()
        + "  Computer architecture and systems (VLIW, interconnects, microarchitecture) "
        "belong here under Computer Architecture & Systems."
    )
    quantum["scope_note"] = (
        quantum.get("scope_note", "").rstrip()
        + "  Optical/interferometric metrology instrumentation belongs here under "
        "Optical Metrology & Interferometric Instrumentation."
    )
    health["scope_note"] = (
        health.get("scope_note", "").rstrip()
        + "  Implant wireless power and IMD bioelectronics interfaces belong under "
        "Clinical Biosensors & Implant Bioelectronics. Downstream biopharma PAT/QC "
        "belongs under Biopharmaceutical Manufacturing & Quality."
    )

    return tax


def write_md(tax: dict) -> None:
    lines = [
        "# Research Ambit Taxonomy Draft v2.2 (gap-fill)\n",
        "_Built 2026-07-18 from v2 to close audit-flagged taxonomy gaps._\n",
        "## Global routing / tie-break rules\n",
    ]
    for i, r in enumerate(tax.get("global_rules", []), 1):
        lines.append(f"{i}. {r}")
    lines.append("\n## Themes and domains\n")
    for t in tax["themes"]:
        lines.append(f"### {t['name']} ({len(t['domains'])} domains)\n")
        for d in t["domains"]:
            lines.append(f"- **{d['name']}**: {d['definition'][:220]}...")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def validate(tax: dict) -> dict:
    counts = {t["name"]: len(t["domains"]) for t in tax["themes"]}
    names = []
    for t in tax["themes"]:
        for d in t["domains"]:
            names.append(d["name"])
    dupes = [k for k, v in Counter(names).items() if v > 1]
    required = [
        "Thermoelectric & Energy-Harvesting Materials",
        "Optical Metrology & Interferometric Instrumentation",
        "Computer Architecture & Systems",
        "Clinical Biosensors & Implant Bioelectronics",
    ]
    missing = [n for n in required if n not in names]
    ok = (
        all(5 <= c <= 10 for c in counts.values())
        and not dupes
        and not missing
        and "Energy Storage Materials" in names
        and "Biopharmaceutical Manufacturing & Quality" in names
    )
    report = {
        "pass": ok,
        "per_theme_domain_counts": counts,
        "total_domains": len(names),
        "n_themes": len(tax["themes"]),
        "duplicate_domain_names": dupes,
        "missing_required": missing,
        "checks": {
            "all_themes_5_to_10_domains": all(5 <= c <= 10 for c in counts.values()),
            "no_duplicate_domain_names": not dupes,
            "required_gap_domains_present": not missing,
            "global_rules_count": len(tax.get("global_rules", [])),
        },
    }
    return report


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    tax = build()
    OUT_JSON.write_text(json.dumps(tax, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(tax)
    report = validate(tax)
    CHECK.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        raise SystemExit("taxonomy v22 failed checks")


if __name__ == "__main__":
    main()
