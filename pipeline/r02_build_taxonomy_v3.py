"""STAGE A: build the sharpened v3 taxonomy from v2 by applying the 8 concrete
fixes in domain_diagnosis.md sec.3, adding the 2 missing-home domains, and an
explicit out-of-scope routing rule.

Design decisions (documented for the report):
  * NO domain is renamed. Renaming a domain that is only partially re-classified
    would strand the carried-over v2 labels (old name not present under v3) and
    break the Stage C "domain-belongs-to-theme under v3" test. So fixes are
    applied as (a) appended tie-break/scope text on existing domain definitions,
    (b) two brand-new domains, and (c) taxonomy-level global_rules injected into
    the classifier system prompt.
  * Every append is asserted to have matched exactly one domain, so a silent
    no-op is impossible.

READ-ONLY DB. No API. No git.
"""
import json

from common import OUTPUTS

SRC = OUTPUTS / "taxonomy-draft-v2.json"
OUT_JSON = OUTPUTS / "taxonomy-draft-v3.json"
OUT_MD = OUTPUTS / "taxonomy-draft-v3.md"

T_ENERGY = "Energy, Sustainability & Climate Change"
T_INFRA = "Smart & Sustainable Infrastructure"
T_MANUF = "Manufacturing & Industry 4.0"
T_ADVMAT = "Advanced Materials & Devices"
T_QUANTUM = "Quantum Technologies & Semiconductor Technology"


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


# --------------------------------------------------------------------------- #
GLOBAL_RULES = [
    ("METHOD vs APPLICATION (operational test). Assign a paper to an "
     "'AI/ML, Supercomputing & Quantum Computing' domain ONLY if its novelty is a "
     "new or modified algorithm/architecture, or a general methodological result "
     "on benchmark-style data. If it uses standard/off-the-shelf methods (SVM, "
     "HMM, standard CNN, a standard CFD solver, kriging, etc.) to obtain a result "
     "about a specific application (a disease, a communication channel, a road "
     "network, a flood), assign the APPLICATION domain instead. For medical "
     "signals/images prefer Healthcare & MedTech; for a named engineering "
     "application prefer that theme's domain. Motivation/keyword is not enough — "
     "classify by the primary scientific contribution."),
    ("OUT-OF-SCOPE ROUTING. If a paper is genuinely out of scope for all 9 themes "
     "-- e.g. pure/fundamental physics (dark matter, gravitational waves, "
     "astrochemistry, cosmology, continuum/second-gradient elasticity theory with "
     "no engineering target), pure mathematics or cryptography theory, or "
     "internal-combustion-engine combustion with no better home -- do NOT force it "
     "into a least-bad domain. Set unclassifiable=true with reason beginning "
     "'out_of_scope:' and a short justification. Reserve this for genuine no-home "
     "papers, not merely difficult ones."),
]

# ---- FIX 1 : Power Systems <-> Grid Integration tie-break ------------------ #
FIX1 = (
    "TIE-BREAK (Grid Integration & Smart Microgrids vs Power Systems & Grid "
    "Control): if the subject is a renewable/DER source being interfaced to the "
    "grid (PV/wind/battery inverter control, MPPT, droop control of DER, renewable "
    "microgrids) -> Energy / Grid Integration & Smart Microgrids. If the subject is "
    "the bulk power network itself, independent of any specific renewable source "
    "(load-flow, transmission loss, AGC/frequency & voltage control of "
    "interconnected grids, generator/machine modeling, protection, network "
    "stability) -> Smart & Sustainable Infrastructure / Power Systems & Grid "
    "Control. Rule of thumb: 'renewable source -> grid' = Energy; 'grid/network "
    "operation' = Infrastructure.")

# ---- FIX 2 : new Energy domain + narrow the two Energy sinks ---------------- #
FIX2_NEW_DOMAIN = {
    "name": "Thermal Systems, Engines & Energy Harvesting",
    "definition": (
        "Thermodynamic-cycle analysis and optimization (Brayton/Rankine/"
        "refrigeration/absorption cycles), internal-combustion and alternative-fuel "
        "engine combustion, waste-heat recovery, and small-scale mechanical/"
        "electrostatic energy harvesters, where the contribution is energy "
        "conversion / thermodynamic performance rather than grid integration, a "
        "solar collector, a fuel/biomass feedstock, or an electrode material. "
        "Prefer this domain over Grid Integration & Smart Microgrids or Solar "
        "Thermal Energy & Heat Transfer Systems for heat-engine, refrigeration and "
        "energy-harvesting papers. (If a combustion/IC-engine paper has no genuine "
        "energy-conversion contribution at all, consider out_of_scope.)"),
    "estimated_share_of_theme": 0.05,
    "example_titles": [
        "Optimal criteria for an irreversible intercooled regenerative modified Brayton cycle",
        "Theoretical analysis of LiBr/H2O absorption refrigeration systems",
        "Effects of exhaust gas recirculation on flame kernel growth in a hydrogen fuelled spark ignition engine",
        "Analysis of nonlinear spring arm for vibrational energy harvesting",
        "Energy Harvesting from Water Droplet Motion",
    ],
}
FIX2_NARROW = (
    "Do NOT use as a catch-all for thermodynamic-cycle / heat-engine / combustion / "
    "energy-harvesting papers -- those go to Thermal Systems, Engines & Energy "
    "Harvesting.")

# ---- FIX 3 : Materials-Joining <-> Structural Dynamics <-> Composite -------- #
FIX3 = (
    "TIE-BREAK (mechanical/structural-analysis papers): if the object is a civil/"
    "infrastructure structure (building, bridge, tank, foundation, seismic "
    "response) -> Smart & Sustainable Infrastructure / Structural Dynamics & "
    "Seismic Engineering; if the object is a fiber-reinforced, laminated, or "
    "functionally-graded composite studied for its structural mechanics -> Advanced "
    "Materials & Devices / Composite & Laminate Structures; if the contribution is "
    "material mechanical behavior tied to a forming/joining/machining process or "
    "high-strain-rate metal response -> Manufacturing & Industry 4.0 / Materials, "
    "Joining & Mechanical Behavior.")

# ---- FIX 4 : new Construction Materials domain + Ferroelectric guard -------- #
FIX4_NEW_DOMAIN = {
    "name": "Construction Materials & Concrete Technology",
    "definition": (
        "Cementitious systems, supplementary cementitious materials (calcined "
        "clays, limestone, fly ash, slag), geopolymers, concrete durability / "
        "transport properties, and mix design. Cement/concrete materials chemistry "
        "belongs here (never Advanced Materials / Ferroelectric & Magnetic "
        "Ceramics). Distinct from Geotechnical Engineering & Soil Mechanics (soils) "
        "and from Structural Dynamics & Seismic Engineering (whole-structure "
        "dynamics)."),
    "estimated_share_of_theme": 0.06,
    "example_titles": [
        "Why Low-Grade Calcined Clays Are Ideal for Limestone Calcined Clay Cement (LC3)",
        "Effect of Limestone on Electrical Properties of Cementitious Systems",
        "Durability and transport properties of supplementary-cementitious-material concretes",
        "Mix design optimization of geopolymer concrete",
        "Chloride ingress and service life of blended-cement concrete",
    ],
}
FIX4_FERRO_GUARD = (
    "Cement / concrete and cementitious materials do NOT belong here -> Smart & "
    "Sustainable Infrastructure / Construction Materials & Concrete Technology.")

# ---- FIX 5 : tighten Algorithms & Computational Complexity ----------------- #
FIX5 = (
    "SCOPE GUARD: this domain is for CS algorithm/complexity contributions (data "
    "structures, graph/parallel algorithms, complexity bounds, optimization "
    "methods). It is NOT a home for physics, continuum/structural mechanics, or "
    "hardware-layout papers; such papers with no CS-algorithmic contribution and no "
    "other theme fit -> unclassifiable (out_of_scope). TIE-BREAK: an algorithm "
    "whose contribution is a networking/routing protocol -> Next-Gen Communication "
    "/ Wireless Network Access & Resource Allocation; a graph method whose "
    "contribution is social-network insight -> Social Sciences, Humanities & "
    "Management / Social Media Analytics & Online Networks; only "
    "application-agnostic algorithm design stays here.")

# ---- FIX 6 : Organometallic synthesis <-> Drug Delivery -------------------- #
FIX6 = (
    "Also covers general organic / coordination-compound synthesis. TIE-BREAK "
    "(synthesis vs therapy): synthesis of small molecules / coordination compounds "
    "where the contribution is the synthetic method or the compound's material / "
    "structural characterization -> Advanced Materials & Devices / Organometallic & "
    "Chalcogenide Synthesis, EVEN when a biological activity is stated as "
    "motivation. Assign Healthcare & MedTech / Drug Delivery & Molecular "
    "Therapeutics ONLY when the paper evaluates the compound in a biological / "
    "pharmacological model (in-vitro/in-vivo efficacy, PK, or a delivery vehicle). "
    "Motivation != evaluation.")

# ---- FIX 8 : Semiconductor PV & Photodetection sink ------------------------ #
FIX8 = (
    "TIE-BREAK (PV device vs material): contribution = device physics/fabrication "
    "of the cell/detector (junction engineering, I-V, EQE, architecture) -> Quantum "
    "Technologies & Semiconductor Technology / Semiconductor Photovoltaic & "
    "Photodetection Devices; contribution = a new absorber/HTL/ETL material or "
    "conversion efficiency of the material -> Energy / Next-Generation Photovoltaic "
    "Materials. Acousto-optic (SAW/IDT) and holographic-imaging papers are NOT "
    "photodetection (route to the relevant device/circuit domain or "
    "unclassifiable); phosphor-lighting -> Advanced Materials & Devices / Rare-Earth "
    "Doped Luminescent Materials. Do NOT use this domain as a catch-all "
    "optical-device sink.")


def main():
    tax = json.loads(SRC.read_text(encoding="utf-8"))
    tax["version"] = "v3-domain-accuracy-fix"
    tax["generated"] = "2026-07-18"
    tax["derived_from"] = "taxonomy-draft-v2.json"
    tax["method"] = (tax.get("method", "")
                     + " | v3: applied the 8 domain_diagnosis sec.3 fixes, "
                       "added 2 missing-home domains, added out-of-scope routing.")

    energy = find_theme(tax, T_ENERGY)
    infra = find_theme(tax, T_INFRA)
    manuf = find_theme(tax, T_MANUF)
    advmat = find_theme(tax, T_ADVMAT)

    # FIX 1
    append_def(energy, "Grid Integration & Smart Microgrids", FIX1)
    append_def(infra, "Power Systems & Grid Control", FIX1)
    # FIX 2
    energy["domains"].append(FIX2_NEW_DOMAIN)
    append_def(energy, "Grid Integration & Smart Microgrids", FIX2_NARROW)
    append_def(energy, "Solar Thermal Energy & Heat Transfer Systems", FIX2_NARROW)
    # FIX 3
    append_def(manuf, "Materials, Joining & Mechanical Behavior", FIX3)
    append_def(infra, "Structural Dynamics & Seismic Engineering", FIX3)
    append_def(advmat, "Composite & Laminate Structures", FIX3)
    # FIX 4
    infra["domains"].append(FIX4_NEW_DOMAIN)
    append_def(advmat, "Ferroelectric & Magnetic Ceramics", FIX4_FERRO_GUARD)
    # FIX 5
    ai = find_theme(tax, "AI/ML, Supercomputing & Quantum Computing")
    append_def(ai, "Algorithms & Computational Complexity", FIX5)
    # FIX 6
    append_def(advmat, "Organometallic & Chalcogenide Synthesis", FIX6)
    # FIX 7 (global) + out-of-scope (global)
    tax["global_rules"] = GLOBAL_RULES
    # FIX 8
    quantum = find_theme(tax, T_QUANTUM)
    append_def(quantum, "Semiconductor Photovoltaic & Photodetection Devices", FIX8)

    tax["changes_v3"] = {
        "fixes_applied": [
            "FIX1 Power-Systems vs Grid-Integration tie-break (both scope notes)",
            "FIX2 added Energy domain 'Thermal Systems, Engines & Energy Harvesting' "
            "+ narrowed Grid-Integration & Solar-Thermal sinks",
            "FIX3 Materials-Joining vs Structural-Dynamics vs Composite tie-break "
            "(all three)",
            "FIX4 added Infra domain 'Construction Materials & Concrete Technology' "
            "+ Ferroelectric-Ceramics cement guard",
            "FIX5 tightened Algorithms & Computational Complexity + out-of-scope route",
            "FIX6 Organometallic-Synthesis vs Drug-Delivery tie-break",
            "FIX7 global METHOD-vs-APPLICATION operational test",
            "FIX8 Semiconductor-PV & Photodetection PV-device-vs-material tie-break "
            "+ de-sinked optical devices",
        ],
        "new_domains": [FIX2_NEW_DOMAIN["name"], FIX4_NEW_DOMAIN["name"]],
        "out_of_scope_rule": True,
        "renamed_domains": [],
    }

    OUT_JSON.write_text(json.dumps(tax, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    write_md(tax)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    for t in tax["themes"]:
        print(f"  {len(t['domains']):2} domains  {t['name']}")


def write_md(tax):
    L = []
    A = L.append
    A("# Research Ambit Taxonomy Draft v3 (domain-accuracy fix) — For Team Review\n")
    A(f"_Derived {tax['generated']} from `taxonomy-draft-v2.json` by applying the "
      "eight concrete domain fixes in `domain_diagnosis.md` §3, adding two "
      "missing-home domains, and adding an explicit out-of-scope routing rule. "
      "No domain was renamed (to preserve label continuity for papers carried "
      "over from v2)._\n")
    A("## What changed from v2\n")
    for f in tax["changes_v3"]["fixes_applied"]:
        A(f"- {f}")
    A("")
    A(f"- **New domains:** {', '.join(tax['changes_v3']['new_domains'])}")
    A("- **Out-of-scope routing rule added** (global): genuine no-home papers "
      "(pure/fundamental physics, pure math/crypto theory, IC-engine combustion "
      "with no better home) -> `unclassifiable=true`, reason `out_of_scope:...`.")
    A("- **Renamed domains:** none.\n")
    A("## Global classifier rules (applied across all themes)\n")
    for i, g in enumerate(tax["global_rules"], 1):
        A(f"{i}. {g}\n")
    A("## Rules of the taxonomy\n")
    A("- **Two levels**: 9 fixed thematic areas -> 5–10 domains each. Each domain "
      "belongs to exactly one theme.")
    A("- **Single label**; **no duplicate domain names** across themes; cross-theme "
      "calls settled by the tie-break rules in each scope note and the global "
      "rules above.\n")
    A("---\n")
    for i, t in enumerate(tax["themes"], 1):
        A(f"## {i}. {t['name']}  ({len(t['domains'])} domains)\n")
        A(f"**Scope.** {t['scope_note']}\n")
        A("| Domain | Definition |")
        A("|---|---|")
        for d in t["domains"]:
            defn = d["definition"].replace("\n", " ").replace("|", "\\|")
            A(f"| **{d['name']}** | {defn} |")
        A("")
        A("---\n")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
