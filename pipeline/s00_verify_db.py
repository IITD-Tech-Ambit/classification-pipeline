"""Step 0: verify DB counts, exact theme names, and dump the old domain/subdomain vocabulary."""
import json

from common import get_db, ensure_dirs, WORK


def main():
    ensure_dirs()
    db = get_db()

    n_papers = db.researchmetadatascopus.estimated_document_count()
    themes = list(db.thematicareas.find({}))
    domains = list(db.domains.find({}))
    subdomains = list(db.subdomains.find({}))

    print(f"papers: {n_papers}")
    print(f"themes: {len(themes)}, domains: {len(domains)}, subdomains: {len(subdomains)}")

    theme_info = []
    for t in themes:
        tid = t["_id"]
        n_assigned = db.researchmetadatascopus.count_documents(
            {"classification.thematic_area_id": tid}
        )
        theme_info.append(
            {
                "id": str(tid),
                "name": t.get("name"),
                "slug": t.get("slug"),
                "assigned_papers_v1": n_assigned,
            }
        )
        print(f"  {t.get('name')!r} slug={t.get('slug')!r} assigned={n_assigned}")

    n_unclassified = db.researchmetadatascopus.count_documents(
        {
            "$or": [
                {"classification": {"$exists": False}},
                {"classification.thematic_area_id": None},
                {"classification.thematic_area_id": {"$exists": False}},
            ]
        }
    )
    print(f"unclassified: {n_unclassified}")

    # sample one paper to see field shapes
    sample = db.researchmetadatascopus.find_one({}, {"title": 1, "abstract": 1, "classification": 1, "iitd_authors": 1})
    print("sample paper keys:", json.dumps({k: str(type(v).__name__) for k, v in sample.items()}, indent=2))

    vocab = {
        "domains": [{"id": str(d["_id"]), "name": d.get("name"), "slug": d.get("slug")} for d in domains],
        "subdomains": [
            {
                "id": str(s["_id"]),
                "name": s.get("name"),
                "domain_id": str(s.get("domain_id")),
            }
            for s in subdomains
        ],
    }

    out = {
        "n_papers": n_papers,
        "n_unclassified": n_unclassified,
        "themes": theme_info,
        "vocab": vocab,
    }
    with open(WORK / "db_facts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"wrote {WORK / 'db_facts.json'}")


if __name__ == "__main__":
    main()
