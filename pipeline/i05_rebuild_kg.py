"""Stage 3b(ii) — rebuild kg_faculty_graphs / kg_explore / kg_indices under the
NEW active atlas version, from Mongo v2 data (classification + iitd_authors +
faculties + departments). Faithful port of build_kg.py's Mongo-driven graph /
explore / index builders, minus the Excel-only subdomain+topic levels (v2 has
none). LOCAL-ONLY, idempotent per version.
"""
import socket
from collections import defaultdict

from pymongo import MongoClient, UpdateOne

CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"


def db():
    host = socket.gethostbyname(socket.gethostname())
    client = MongoClient(f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin")
    assert not client.admin.command("hello").get("setName"), "target must be local standalone"
    return client, client["research_ambit"]


def main():
    client, d = db()
    version = d.atlas_meta.find_one({"_id": "active", "kind": "pointer"})["version"]
    print(f"rebuilding KG under active version {version}")

    theme_name = {x["_id"]: x["name"] for x in d.thematicareas.find({}, {"name": 1})}
    domain_name = {x["_id"]: x["name"] for x in d.domains.find({}, {"name": 1})}
    dept_name = {x["_id"]: x.get("name", "") for x in d.departments.find({})}
    dept_by_code = {x.get("code"): x.get("name", "") for x in d.departments.find({}) if x.get("code")}

    def resolve_dept(ref):
        if ref is None:
            return ""
        if ref in dept_name:
            return dept_name[ref]
        s = str(ref)
        return dept_by_code.get(s, dept_name.get(s, ""))

    faculties = {}
    for f in d.faculties.find({}):
        name = " ".join(str(x) for x in [f.get("title"), f.get("firstName"), f.get("lastName")] if x).strip()
        faculties[f["_id"]] = {
            "facultyId": str(f["_id"]),
            "name": name or "Unknown Faculty",
            "department": resolve_dept(f.get("department")),
            "citation_count": int(f.get("citation_count") or 0),
        }

    # atlas index map: paper id -> global atlas index i
    pid_to_i = {p["id"]: p["i"] for p in d.atlas_points.find({"version": version}, {"id": 1, "i": 1})}

    # faculty -> [(faculty_rec, paper)]
    faculty_papers = defaultdict(list)
    cursor = d.researchmetadatascopus.find(
        {"classification.thematic_area_id": {"$ne": None}, "iitd_authors.0": {"$exists": True}},
        {"title": 1, "publication_year": 1, "citation_count": 1, "link": 1,
         "document_scopus_id": 1, "document_eid": 1, "classification": 1, "iitd_authors": 1})
    for p in cursor:
        c = p.get("classification") or {}
        theme = theme_name.get(c.get("thematic_area_id"))
        domain = domain_name.get(c.get("domain_id"))
        if not theme:
            continue
        seen = set()
        paper_dept = ""
        for a in p.get("iitd_authors", []):
            if a.get("department_ref") and not paper_dept:
                paper_dept = resolve_dept(a.get("department_ref"))
        rec = {"_id": p["_id"], "title": p.get("title") or "Untitled",
               "year": p.get("publication_year"), "citations": int(p.get("citation_count") or 0),
               "link": p.get("link") or "", "scopus": p.get("document_scopus_id") or "",
               "eid": p.get("document_eid") or "", "theme": theme, "domain": domain or "",
               "dept": paper_dept}
        for a in p.get("iitd_authors", []):
            fref = a.get("faculty_ref")
            if fref is None or fref in seen or fref not in faculties:
                continue
            seen.add(fref)
            faculty_papers[fref].append(rec)

    # --- per-faculty graphs + faculty-search-index + faculty-atlas-indices ---
    d.kg_faculty_graphs.delete_many({"version": version})
    graph_ops, search_index, faculty_atlas = [], [], {}
    for fref, papers in faculty_papers.items():
        fac = faculties[fref]
        fid = f"f:{fac['facultyId']}"
        nodes = {fid: {"id": fid, "label": fac["name"], "type": "faculty",
                       "department": fac["department"], "citation_count": fac["citation_count"]}}
        edges = []
        indices = []
        for p in papers:
            pid = f"p:{p['_id']}"
            nodes[pid] = {"id": pid, "label": p["title"], "type": "paper",
                          "citation_count": p["citations"], "year": p["year"],
                          "broad_theme": p["theme"], "domain": p["domain"],
                          "sub_domain": "", "topic": "", "iitd_department": p["dept"],
                          "link": p["link"], "document_scopus_id": p["scopus"],
                          "document_eid": p["eid"]}
            edges.append({"source": fid, "target": pid, "label": "AUTHORED"})
            if p["theme"] and p["theme"] != "Unclassified":
                tid = f"theme:{p['theme']}"
                nodes.setdefault(tid, {"id": tid, "label": p["theme"], "type": "theme"})
                edges.append({"source": pid, "target": tid, "label": "BELONGS_TO"})
            if p["domain"]:
                did = f"dom:{p['domain']}"
                nodes.setdefault(did, {"id": did, "label": p["domain"], "type": "domain"})
                edges.append({"source": pid, "target": did, "label": "IN_DOMAIN"})
            gi = pid_to_i.get(str(p["_id"]))
            if gi is not None:
                indices.append(gi)
        graph = {"nodes": list(nodes.values()), "edges": edges}
        graph_ops.append(UpdateOne({"version": version, "facultyId": fac["facultyId"]},
                                   {"$set": {"version": version, "facultyId": fac["facultyId"], "graph": graph}},
                                   upsert=True))
        search_index.append({"facultyId": fac["facultyId"], "name": fac["name"],
                             "department": fac["department"], "paperCount": len(papers),
                             "nodeCount": len(graph["nodes"]), "edgeCount": len(edges),
                             "classified": len(papers)})
        if indices:
            faculty_atlas[fac["facultyId"]] = sorted(set(indices))

    for i in range(0, len(graph_ops), 200):
        d.kg_faculty_graphs.bulk_write(graph_ops[i:i + 200], ordered=False)
    search_index.sort(key=lambda x: -x["paperCount"])

    # --- explore index: type(theme|domain) -> term -> dept -> faculty ---
    agg = {"theme": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"name": "", "papers": 0}))),
           "domain": defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"name": "", "papers": 0})))}
    for fref, papers in faculty_papers.items():
        fac = faculties[fref]
        dept = (fac["department"] or "Unknown Department").strip() or "Unknown Department"
        for p in papers:
            for typ, term in (("theme", p["theme"]), ("domain", p["domain"])):
                term = (term or "").strip()
                if not term or term == "Unclassified":
                    continue
                cell = agg[typ][term][dept][fac["facultyId"]]
                cell["name"] = fac["name"]
                cell["papers"] += 1

    terms, details = [], {}
    for typ, term_map in agg.items():
        for term, dept_map in term_map.items():
            departments, tp, tf = [], 0, 0
            for dept, fac_map in dept_map.items():
                flist = [{"facultyId": fid, "name": c["name"], "paperCount": c["papers"]}
                         for fid, c in fac_map.items()]
                flist.sort(key=lambda x: -x["paperCount"])
                dp = sum(f["paperCount"] for f in flist)
                departments.append({"department": dept, "paperCount": dp,
                                    "facultyCount": len(flist), "faculty": flist})
                tp += dp
                tf += len(flist)
            departments.sort(key=lambda x: -x["paperCount"])
            key = f"{typ}::{term}"
            details[key] = {"term": term, "type": typ, "departments": departments}
            terms.append({"key": key, "term": term, "type": typ, "paperCount": tp,
                          "deptCount": len(departments), "facultyCount": tf})
    type_order = {"theme": 0, "domain": 1}
    terms.sort(key=lambda t: (type_order[t["type"]], -t["paperCount"]))

    d.kg_explore.delete_many({"version": version})
    explore_ops = [{"version": version, "kind": "term", "term": r["term"], "type": r["type"], "payload": r}
                   for r in terms]
    explore_ops += [{"version": version, "kind": "detail", "key": k, "payload": v} for k, v in details.items()]
    for i in range(0, len(explore_ops), 500):
        d.kg_explore.insert_many(explore_ops[i:i + 500], ordered=False)

    # --- indices (faithful to migrate_kg_to_mongo) ---
    def put_index(name, payload):
        d.kg_indices.update_one({"version": version, "name": name},
                                {"$set": {"version": version, "name": name, "payload": payload}}, upsert=True)

    put_index("faculty-search-index", search_index)
    put_index("faculty-atlas-indices", faculty_atlas)
    by_dept = {}
    for fac in search_index:
        dept = str(fac.get("department", "")).strip()
        if not dept:
            continue
        e = by_dept.setdefault(dept, {"indices": set(), "facultyCount": 0})
        e["facultyCount"] += 1
        for idx in faculty_atlas.get(fac["facultyId"], []):
            e["indices"].add(idx)
    put_index("department-atlas-indices",
              {dept: {"indices": sorted(e["indices"]), "facultyCount": e["facultyCount"]}
               for dept, e in by_dept.items()})

    print(f"faculty graphs: {len(graph_ops)}")
    print(f"explore: {len(terms)} terms + {len(details)} details")
    print(f"faculty-atlas-indices: {len(faculty_atlas)} | department-atlas-indices: {len(by_dept)}")
    client.close()
    print("KG rebuild done.")


if __name__ == "__main__":
    main()
