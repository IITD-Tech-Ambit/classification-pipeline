"""Stage 2 TEST — verify the v2 classification ingest (read-only)."""
import json
import socket
from collections import Counter
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"


def db():
    host = socket.gethostbyname(socket.gethostname())
    return MongoClient(f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin")["research_ambit"]


def main():
    d = db()
    R = d.researchmetadatascopus
    theme_name = {x["_id"]: x["name"] for x in d.thematicareas.find({}, {"name": 1})}
    domain_name = {x["_id"]: x["name"] for x in d.domains.find({}, {"name": 1})}

    out = {}
    out["papers_total"] = R.count_documents({})
    out["with_theme_id"] = R.count_documents({"classification.thematic_area_id": {"$ne": None}})
    out["with_domain_id"] = R.count_documents({"classification.domain_id": {"$ne": None}})
    out["with_subdomain_id"] = R.count_documents({"classification.subdomain_id": {"$ne": None}})
    out["unclassifiable_true"] = R.count_documents({"classification.unclassifiable": True})
    out["with_iitd_authors"] = R.count_documents({"iitd_authors.0": {"$exists": True}})
    out["theme_and_domain_both_set"] = R.count_documents({
        "classification.thematic_area_id": {"$ne": None},
        "classification.domain_id": {"$ne": None}})

    # every used id resolves to a node (no orphan refs)
    used_t = [t for t in R.distinct("classification.thematic_area_id") if t is not None]
    used_d = [x for x in R.distinct("classification.domain_id") if x is not None]
    out["distinct_theme_ids_used"] = len(used_t)
    out["distinct_domain_ids_used"] = len(used_d)
    out["theme_ids_all_resolve"] = all(t in theme_name for t in used_t)
    out["domain_ids_all_resolve"] = all(x in domain_name for x in used_d)

    # per-theme counts from DB vs jsonl
    db_theme_counts = Counter()
    for row in R.aggregate([
        {"$match": {"classification.thematic_area_id": {"$ne": None}}},
        {"$group": {"_id": "$classification.thematic_area_id", "n": {"$sum": 1}}},
    ]):
        db_theme_counts[theme_name[row["_id"]]] = row["n"]

    jl_theme_counts = Counter()
    jl_pairs_by_id = {}
    for line in (OUTPUTS / "classification_v2_final.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if not o.get("unclassifiable"):
            jl_theme_counts[o["thematic_area"]] += 1
        jl_pairs_by_id[o["id"]] = o
    out["per_theme_db_vs_jsonl"] = {
        t: {"db": db_theme_counts[t], "jsonl": jl_theme_counts[t], "match": db_theme_counts[t] == jl_theme_counts[t]}
        for t in sorted(jl_theme_counts, key=lambda x: -jl_theme_counts[x])
    }
    out["all_themes_match"] = all(v["match"] for v in out["per_theme_db_vs_jsonl"].values())

    # sample 20 papers: DB label must equal jsonl label
    sample_ids = list(jl_pairs_by_id.keys())[:20]
    sample = []
    mismatches = 0
    for doc in R.find({"_id": {"$in": [ObjectId(i) for i in sample_ids]}},
                      {"title": 1, "classification": 1}):
        c = doc.get("classification") or {}
        jl = jl_pairs_by_id[str(doc["_id"])]
        db_t = theme_name.get(c.get("thematic_area_id"))
        db_dm = domain_name.get(c.get("domain_id"))
        exp_t = None if jl.get("unclassifiable") else jl["thematic_area"]
        exp_dm = None if jl.get("unclassifiable") else jl["domain"]
        ok = (db_t == exp_t and db_dm == exp_dm and c.get("subdomain_id") is None)
        if not ok:
            mismatches += 1
        sample.append({"id": str(doc["_id"]), "title": (doc.get("title") or "")[:50],
                       "db_theme": db_t, "db_domain": db_dm,
                       "jsonl_theme": exp_t, "jsonl_domain": exp_dm, "ok": ok})
    out["sample20_mismatches"] = mismatches
    out["sample20"] = sample

    checks = {
        "classified_is_68090": out["theme_and_domain_both_set"] == 68090,
        "unclassifiable_is_2208": out["unclassifiable_true"] == 2208,
        "touched_is_70298": out["theme_and_domain_both_set"] + out["unclassifiable_true"] == 70298,
        "no_subdomains": out["with_subdomain_id"] == 0,
        "theme_domain_equal_counts": out["with_theme_id"] == out["with_domain_id"] == 68090,
        "no_orphan_theme_ids": out["theme_ids_all_resolve"],
        "no_orphan_domain_ids": out["domain_ids_all_resolve"],
        "domains_node_count_77": d.domains.count_documents({}) == 77,
        "themes_node_count_9": d.thematicareas.count_documents({}) == 9,
        "iitd_authors_preserved": out["with_iitd_authors"] == 66235,
        "all_themes_match_distribution": out["all_themes_match"],
        "sample20_all_ok": out["sample20_mismatches"] == 0,
    }
    out["CHECKS"] = checks
    out["STAGE2_PASS"] = all(checks.values())

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
