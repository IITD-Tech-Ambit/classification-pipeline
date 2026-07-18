"""STAGE 1 TEST: validate the edited v2 taxonomy.

Asserts:
  - JSON parses
  - every theme has 5-10 domains (Energy now 9)
  - zero duplicate domain names across all themes
  - the new 'Energy Storage Materials' domain exists under the Energy theme
  - the Advanced Materials scope note contains the antibacterial/antimicrobial tie-break
Writes outputs/work/stage1_taxonomy_check.json (per-theme counts + pass/fail).
"""
import json
import sys
from collections import Counter

from common import OUTPUTS, WORK

TAX = OUTPUTS / "taxonomy-draft-v2.json"


def main():
    checks = {}
    tax = json.loads(TAX.read_text(encoding="utf-8"))  # raises if not parseable
    checks["json_parses"] = True

    themes = tax["themes"]
    per_theme = {}
    all_domains = []
    for t in themes:
        doms = [d["name"] for d in t["domains"]]
        per_theme[t["name"]] = len(doms)
        all_domains.extend(doms)

    # 5-10 domains each
    counts_ok = all(5 <= n <= 10 for n in per_theme.values())
    checks["all_themes_5_to_10_domains"] = counts_ok

    # Energy == 9
    energy_name = "Energy, Sustainability & Climate Change"
    checks["energy_has_9_domains"] = per_theme.get(energy_name) == 9

    # duplicate domain names across themes
    dup = [name for name, c in Counter(all_domains).items() if c > 1]
    checks["no_duplicate_domain_names"] = (len(dup) == 0)
    checks["duplicate_domain_names"] = dup

    # new domain present under Energy
    energy = next(t for t in themes if t["name"] == energy_name)
    energy_doms = [d["name"] for d in energy["domains"]]
    checks["energy_storage_materials_present"] = "Energy Storage Materials" in energy_doms

    # tie-break present in Advanced Materials scope note
    adv = next(t for t in themes if t["name"] == "Advanced Materials & Devices")
    note = adv["scope_note"].lower()
    checks["adv_materials_tiebreak_present"] = (
        "antibacterial" in note and "antimicrobial" in note and "tie-break" in note
    )

    hard = [
        "json_parses", "all_themes_5_to_10_domains", "energy_has_9_domains",
        "no_duplicate_domain_names", "energy_storage_materials_present",
        "adv_materials_tiebreak_present",
    ]
    passed = all(checks[k] for k in hard)

    payload = {
        "pass": passed,
        "per_theme_domain_counts": per_theme,
        "total_domains": len(all_domains),
        "n_themes": len(themes),
        "checks": checks,
    }
    (WORK / "stage1_taxonomy_check.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not passed:
        print("STAGE 1 TEST FAILED", file=sys.stderr)
        sys.exit(1)
    print("STAGE 1 TEST PASSED")


if __name__ == "__main__":
    main()
