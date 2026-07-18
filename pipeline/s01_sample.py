"""Step 1: sample ~500 papers per theme (preferring ones with abstracts) + ~500 unclassified."""
import json

from bson import ObjectId

from common import get_db, ensure_dirs, WORK

PER_THEME = 550
UNCLASSIFIED_N = 500
NO_ABSTRACT = "(No abstract available)"


def clean_paper(p):
    abstract = p.get("abstract") or ""
    if abstract.strip() == NO_ABSTRACT:
        abstract = ""
    depts = []
    for a in p.get("iitd_authors") or []:
        d = a.get("department") if isinstance(a, dict) else None
        if d and d not in depts:
            depts.append(d)
    return {
        "id": str(p["_id"]),
        "title": (p.get("title") or "").strip(),
        "abstract": abstract.strip()[:1500],
        "departments": depts,
    }


def sample_theme(db, theme_id, n):
    """Prefer papers with abstracts; top up with abstract-less if needed."""
    base = {"classification.thematic_area_id": ObjectId(theme_id)}
    with_abs = list(
        db.researchmetadatascopus.aggregate(
            [
                {"$match": {**base, "abstract": {"$exists": True, "$nin": ["", NO_ABSTRACT]}}},
                {"$sample": {"size": n}},
                {"$project": {"title": 1, "abstract": 1, "iitd_authors": 1}},
            ]
        )
    )
    papers = [clean_paper(p) for p in with_abs]
    if len(papers) < n:
        seen = {p["id"] for p in papers}
        extra = db.researchmetadatascopus.aggregate(
            [
                {"$match": base},
                {"$sample": {"size": n - len(papers) + 50}},
                {"$project": {"title": 1, "abstract": 1, "iitd_authors": 1}},
            ]
        )
        for p in extra:
            c = clean_paper(p)
            if c["id"] not in seen and c["title"]:
                papers.append(c)
                seen.add(c["id"])
            if len(papers) >= n:
                break
    return papers


def main():
    ensure_dirs()
    db = get_db()
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))

    samples = {}
    for t in facts["themes"]:
        papers = sample_theme(db, t["id"], PER_THEME)
        samples[t["id"]] = papers
        n_abs = sum(1 for p in papers if p["abstract"])
        print(f"{t['name']}: sampled {len(papers)} ({n_abs} with abstract)")

    uncls = list(
        db.researchmetadatascopus.aggregate(
            [
                {
                    "$match": {
                        "$or": [
                            {"classification": {"$exists": False}},
                            {"classification.thematic_area_id": None},
                            {"classification.thematic_area_id": {"$exists": False}},
                        ]
                    }
                },
                {"$sample": {"size": UNCLASSIFIED_N}},
                {"$project": {"title": 1, "abstract": 1, "iitd_authors": 1}},
            ]
        )
    )
    uncls_clean = [clean_paper(p) for p in uncls if (p.get("title") or "").strip()]
    print(f"unclassified: sampled {len(uncls_clean)}")

    with open(WORK / "samples.json", "w", encoding="utf-8") as f:
        json.dump({"by_theme": samples, "unclassified": uncls_clean}, f, ensure_ascii=False)
    print(f"wrote {WORK / 'samples.json'}")


if __name__ == "__main__":
    main()
