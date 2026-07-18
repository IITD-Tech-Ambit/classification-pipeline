"""Stage 3 TEST — verify rollups + atlas rebuild; write ingest_verification.json."""
import json
import socket
from collections import Counter
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"


def db():
    host = socket.gethostbyname(socket.gethostname())
    return MongoClient(f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin")["research_ambit"]


def main():
    d = db()
    theme_name = {x["_id"]: x["name"] for x in d.thematicareas.find({}, {"name": 1})}
    domain_name = {x["_id"]: x["name"] for x in d.domains.find({}, {"name": 1})}
    out = {}

    # expected per-theme from jsonl
    jl = Counter()
    for line in (OUTPUTS / "classification_v2_final.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            if not o.get("unclassifiable"):
                jl[o["thematic_area"]] += 1

    # theme-level facet rows: theme set, domain/subdomain/department null
    fc = d.taxonomyfacetcounts
    theme_rows = {}
    for r in fc.find({"thematic_area_id": {"$ne": None}, "domain_id": None,
                      "subdomain_id": None, "department_id": None}):
        theme_rows[theme_name.get(r["thematic_area_id"])] = r["paper_count"]
    out["facet_theme_counts_vs_jsonl"] = {
        t: {"facet": theme_rows.get(t, 0), "jsonl": jl[t], "match": theme_rows.get(t, 0) == jl[t]}
        for t in sorted(jl, key=lambda x: -jl[x])}
    out["all_theme_facets_match"] = all(v["match"] for v in out["facet_theme_counts_vs_jsonl"].values())

    # domain-level facet rows (domain set, theme/subdomain/department null)
    dom_rows = list(fc.find({"domain_id": {"$ne": None}, "thematic_area_id": None,
                             "subdomain_id": None, "department_id": None}))
    out["domain_level_facet_rows"] = len(dom_rows)
    out["domain_facet_paper_sum"] = sum(r["paper_count"] for r in dom_rows)
    out["theme_domain_facet_rows"] = fc.count_documents(
        {"thematic_area_id": {"$ne": None}, "domain_id": {"$ne": None},
         "subdomain_id": None, "department_id": None})
    out["facetcounts_total"] = fc.count_documents({})
    out["facetmembers_total"] = d.taxonomyfacetmembers.count_documents({})
    out["subdomain_facet_rows"] = fc.count_documents({"subdomain_id": {"$ne": None}})

    # node stats
    out["theme_stats_sample"] = [
        {"name": x["name"], "paper_count": x.get("stats", {}).get("paper_count"),
         "faculty_count": x.get("stats", {}).get("faculty_count")}
        for x in d.thematicareas.find({}, {"name": 1, "stats": 1}).sort("name", 1)]
    out["domains_with_stats"] = d.domains.count_documents({"stats.paper_count": {"$gt": 0}})

    # atlas
    ptr = d.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
    version = ptr["version"]
    meta = d.atlas_meta.find_one({"_id": version, "kind": "version"})
    dd = meta.get("dict", {})
    out["atlas"] = {
        "active_version": version,
        "point_count_meta": meta.get("pointCount"),
        "atlas_points": d.atlas_points.count_documents({"version": version}),
        "atlas_tiles": d.atlas_tiles.count_documents({"version": version}),
        "dict_themes": len(dd.get("themes", [])),
        "dict_domains": len(dd.get("domains", [])),
        "dict_domains_nonempty": len([x for x in dd.get("domains", []) if x]),
        "dict_themes_nonunclassified": len([x for x in dd.get("themes", []) if x and x != "Unclassified"]),
        "dict_theme_anchors": len(dd.get("themeAnchors", [])),
        "dict_domain_anchors": len(dd.get("domainAnchors", [])),
        "themes": dd.get("themes", []),
        "kg_faculty_graphs": d.kg_faculty_graphs.count_documents({"version": version}),
        "kg_explore_terms": d.kg_explore.count_documents({"version": version, "kind": "term"}),
        "kg_explore_details": d.kg_explore.count_documents({"version": version, "kind": "detail"}),
        "kg_indices": d.kg_indices.count_documents({"version": version}),
        "prior_version_retained": d.atlas_meta.count_documents({"kind": "version"}) >= 2,
    }
    # a sample atlas point reflects v2
    sp = d.atlas_points.find_one({"version": version, "theme": {"$ne": "Unclassified"}},
                                 {"_id": 0, "id": 1, "theme": 1, "domain": 1, "title": 1})
    out["atlas"]["sample_point"] = sp

    checks = {
        "all_theme_facets_match": out["all_theme_facets_match"],
        "domain_facet_rows_77": out["domain_level_facet_rows"] == 77,
        "no_subdomain_facets": out["subdomain_facet_rows"] == 0,
        "facetmembers_nonzero": out["facetmembers_total"] > 0,
        "domains_all_have_stats": out["domains_with_stats"] == 77,
        "atlas_points_66235": out["atlas"]["atlas_points"] == 66235,
        "atlas_tiles_nonzero": out["atlas"]["atlas_tiles"] > 0,
        "atlas_dict_domains_77": out["atlas"]["dict_domains_nonempty"] == 77,
        "atlas_dict_themes_9": out["atlas"]["dict_themes_nonunclassified"] == 9,
        "atlas_kg_graphs_nonzero": out["atlas"]["kg_faculty_graphs"] > 0,
        "atlas_kg_explore_86": out["atlas"]["kg_explore_terms"] == 86,
        "prior_atlas_version_retained": out["atlas"]["prior_version_retained"],
    }
    out["CHECKS"] = checks
    out["STAGE3_PASS"] = all(checks.values())

    (OUTPUTS / "ingest_verification.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"CHECKS": checks, "STAGE3_PASS": out["STAGE3_PASS"],
                      "atlas": {k: out["atlas"][k] for k in
                                ["active_version", "atlas_points", "atlas_tiles", "dict_themes",
                                 "dict_domains", "kg_faculty_graphs", "kg_explore_terms"]}},
                     indent=2, default=str))
    print("--- facet theme counts ---")
    for t, v in out["facet_theme_counts_vs_jsonl"].items():
        print(f"  {v['facet']:6d} facet / {v['jsonl']:6d} jsonl  {'OK' if v['match'] else 'MISMATCH'}  {t}")


if __name__ == "__main__":
    main()
