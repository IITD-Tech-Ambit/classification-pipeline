"""Pull candidate example titles for the new 'Energy Storage Materials' domain
by keyword search over the corpus. READ-ONLY DB."""
import re

from common import get_db

# materials-as-materials energy storage keywords (anode/cathode/electrode/
# supercapacitor / solid electrolyte / Li-ion electrode materials)
PATTERNS = [
    r"\banode\b", r"\bcathode\b", r"supercapacitor", r"\belectrode material",
    r"lithium[- ]ion", r"li-ion", r"solid electrolyte", r"sodium[- ]ion",
    r"lithium sulfur", r"lithium-sulfur",
]
# things to avoid (charger / power-electronics systems, grid)
AVOID = re.compile(r"charger|charging station|grid|microgrid|converter|inverter|"
                   r"power electronic|BMS|battery management", re.I)


def main():
    db = get_db()
    coll = db.researchmetadatascopus
    rx = re.compile("|".join(PATTERNS), re.I)
    seen = set()
    hits = []
    q = {"title": {"$regex": "|".join(PATTERNS), "$options": "i"}}
    for d in coll.find(q, {"title": 1, "abstract": 1}).limit(400):
        title = (d.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        if AVOID.search(title):
            continue
        if not rx.search(title):
            continue
        # prefer ones that read like materials studies
        hits.append(title)
    for i, t in enumerate(hits[:60], 1):
        print(f"{i:2d}. {t}")
    print(f"\nTOTAL candidate titles: {len(hits)}")


if __name__ == "__main__":
    main()
