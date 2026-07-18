"""STAGE A TEST: validate taxonomy-draft-v3.json.

Checks: JSON parses; every theme has 5-10 domains; zero duplicate domain names
across themes; all 8 fixes + 2 new domains + out-of-scope rule are present
(verified by locating the exact tie-break text in the right domain/global rule).
Writes outputs/work/stageA_taxonomy_check.json with per-theme counts + pass/fail.
"""
import json

from common import OUTPUTS, WORK

V3 = OUTPUTS / "taxonomy-draft-v3.json"


def dom_def(tax, theme_name, domain_name):
    for t in tax["themes"]:
        if t["name"] == theme_name:
            for d in t["domains"]:
                if d["name"] == domain_name:
                    return d["definition"]
    return ""


def main():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    raw = V3.read_text(encoding="utf-8")
    try:
        tax = json.loads(raw)
        check("json_parses", True)
    except Exception as e:
        check("json_parses", False, repr(e))
        (WORK / "stageA_taxonomy_check.json").write_text(
            json.dumps({"pass": False, "checks": checks}, indent=2), encoding="utf-8")
        print("JSON DID NOT PARSE:", e)
        raise SystemExit(1)

    per_theme = {t["name"]: len(t["domains"]) for t in tax["themes"]}
    check("nine_themes", len(tax["themes"]) == 9, f"{len(tax['themes'])} themes")
    for name, cnt in per_theme.items():
        check(f"domain_count_5_10::{name}", 5 <= cnt <= 10, str(cnt))

    all_domains = [d["name"] for t in tax["themes"] for d in t["domains"]]
    dupes = sorted({n for n in all_domains if all_domains.count(n) > 1})
    check("zero_duplicate_domain_names", not dupes, f"dupes={dupes}")

    gr = " ".join(tax.get("global_rules", []))

    # -- FIX presence --
    check("FIX1_grid_integration",
          "renewable source -> grid" in dom_def(
              tax, "Energy, Sustainability & Climate Change",
              "Grid Integration & Smart Microgrids"))
    check("FIX1_power_systems",
          "network operation' = Infrastructure" in dom_def(
              tax, "Smart & Sustainable Infrastructure",
              "Power Systems & Grid Control"))
    check("FIX2_new_domain",
          bool(dom_def(tax, "Energy, Sustainability & Climate Change",
                       "Thermal Systems, Engines & Energy Harvesting")))
    check("FIX2_narrowed_grid",
          "catch-all" in dom_def(tax, "Energy, Sustainability & Climate Change",
                                 "Grid Integration & Smart Microgrids"))
    check("FIX2_narrowed_solar",
          "catch-all" in dom_def(tax, "Energy, Sustainability & Climate Change",
                                 "Solar Thermal Energy & Heat Transfer Systems"))
    check("FIX3_materials_joining",
          "high-strain-rate metal response" in dom_def(
              tax, "Manufacturing & Industry 4.0",
              "Materials, Joining & Mechanical Behavior"))
    check("FIX3_structural_dynamics",
          "civil/" in dom_def(tax, "Smart & Sustainable Infrastructure",
                              "Structural Dynamics & Seismic Engineering"))
    check("FIX3_composite",
          "functionally-graded composite" in dom_def(
              tax, "Advanced Materials & Devices",
              "Composite & Laminate Structures"))
    check("FIX4_new_domain",
          bool(dom_def(tax, "Smart & Sustainable Infrastructure",
                       "Construction Materials & Concrete Technology")))
    check("FIX4_ferroelectric_guard",
          "Cement / concrete" in dom_def(tax, "Advanced Materials & Devices",
                                         "Ferroelectric & Magnetic Ceramics"))
    check("FIX5_algorithms",
          "out_of_scope" in dom_def(tax, "AI/ML, Supercomputing & Quantum Computing",
                                    "Algorithms & Computational Complexity"))
    check("FIX6_organometallic",
          "Motivation != evaluation" in dom_def(
              tax, "Advanced Materials & Devices",
              "Organometallic & Chalcogenide Synthesis"))
    check("FIX7_method_vs_application_global",
          "METHOD vs APPLICATION" in gr)
    check("FIX8_semiconductor_pv",
          "optical-device sink" in dom_def(
              tax, "Quantum Technologies & Semiconductor Technology",
              "Semiconductor Photovoltaic & Photodetection Devices"))
    check("out_of_scope_rule_global", "OUT-OF-SCOPE ROUTING" in gr)
    check("new_domains_recorded",
          tax.get("changes_v3", {}).get("new_domains") ==
          ["Thermal Systems, Engines & Energy Harvesting",
           "Construction Materials & Concrete Technology"])

    passed = all(c["pass"] for c in checks)
    result = {
        "pass": passed,
        "per_theme_domain_counts": per_theme,
        "total_domains": len(all_domains),
        "duplicate_domain_names": dupes,
        "checks": checks,
    }
    (WORK / "stageA_taxonomy_check.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(per_theme, indent=2))
    print(f"total domains: {len(all_domains)}  duplicates: {dupes}")
    failed = [c for c in checks if not c["pass"]]
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print("  -", c["check"], c["detail"])
        raise SystemExit(1)
    print(f"STAGE A: ALL {len(checks)} CHECKS PASSED")


if __name__ == "__main__":
    main()
