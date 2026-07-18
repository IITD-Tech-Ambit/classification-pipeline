"""Stage 3a — taxonomy rollup (faithful Python port of
SEO-Backend-iitd/scripts/taxonomy/{rollup.js, lib/rollupAggregations.js}).

Rebuilds taxonomyfacetcounts + taxonomyfacetmembers from scratch and updates
ThematicArea/Domain/Subdomain `stats`. LOCAL-ONLY. Idempotent (delete+insert).
"""
import socket
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne

CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"
MEMBERS_CAP = 500

MASKS = [
    ["thematic_area_id"],
    ["domain_id"],
    ["domain_id", "subdomain_id"],
    ["thematic_area_id", "domain_id"],
    ["thematic_area_id", "domain_id", "subdomain_id"],
]


def mask_match(mask):
    return {f"classification.{f}": {"$ne": None} for f in mask}


def mask_key(mask, frm="$classification."):
    return {f: f"{frm}{f}" for f in mask}


def lift_from_id(mask):
    return {f: f"$_id.{f}" for f in mask}


def paper_count_pipeline(mask, with_dept):
    if not with_dept:
        return [{"$match": mask_match(mask)},
                {"$group": {"_id": mask_key(mask), "paper_count": {"$sum": 1}}}]
    return [
        {"$match": mask_match(mask)},
        {"$unwind": "$iitd_authors"},
        {"$match": {"iitd_authors.department_ref": {"$ne": None}}},
        {"$group": {"_id": {**mask_key(mask), "department_id": "$iitd_authors.department_ref", "paper": "$_id"}}},
        {"$group": {"_id": {**lift_from_id(mask), "department_id": "$_id.department_id"}, "paper_count": {"$sum": 1}}},
    ]


def faculty_count_pipeline(mask, with_dept):
    author_match = {"iitd_authors.faculty_ref": {"$ne": None}}
    if with_dept:
        author_match["iitd_authors.department_ref"] = {"$ne": None}
    dedupe = {**mask_key(mask), "kerberos": "$iitd_authors.kerberos"}
    regroup = lift_from_id(mask)
    if with_dept:
        dedupe["department_id"] = "$iitd_authors.department_ref"
        regroup["department_id"] = "$_id.department_id"
    return [
        {"$match": mask_match(mask)},
        {"$unwind": "$iitd_authors"},
        {"$match": author_match},
        {"$group": {"_id": dedupe}},
        {"$group": {"_id": regroup, "faculty_count": {"$sum": 1}}},
    ]


def members_pipeline(mask, with_dept):
    author_match = {"iitd_authors.faculty_ref": {"$ne": None}}
    if with_dept:
        author_match["iitd_authors.department_ref"] = {"$ne": None}
    group_key = mask_key(mask)
    if with_dept:
        group_key["department_id"] = "$iitd_authors.department_ref"
    return [
        {"$match": mask_match(mask)},
        {"$unwind": "$iitd_authors"},
        {"$match": author_match},
        {"$group": {"_id": group_key, "kerberos_set": {"$addToSet": "$iitd_authors.kerberos"}}},
    ]


def combo_key(_id):
    return "|".join(str(_id.get(k) or "") for k in
                    ("thematic_area_id", "domain_id", "subdomain_id", "department_id"))


def db():
    host = socket.gethostbyname(socket.gethostname())
    client = MongoClient(f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin")
    assert not client.admin.command("hello").get("setName"), "target must be local standalone"
    print(f"rollup target: {client.address[0]}:{client.address[1]} (standalone)")
    return client, client["research_ambit"]


def main():
    client, d = db()
    R = d.researchmetadatascopus
    now = datetime.now(timezone.utc)

    dept_by_id = {x["_id"]: x for x in d.departments.find({})}
    h_index = {}
    for f in d.faculties.find({}, {"email": 1, "h_index": 1}):
        kerb = str(f.get("email") or "").split("@")[0].lower().strip()
        if kerb:
            h_index[kerb] = f.get("h_index") or 0

    rows = {}

    def combo_row(_id):
        key = combo_key(_id)
        if key not in rows:
            dep = dept_by_id.get(_id.get("department_id")) if _id.get("department_id") else None
            rows[key] = {
                "thematic_area_id": _id.get("thematic_area_id"),
                "domain_id": _id.get("domain_id"),
                "subdomain_id": _id.get("subdomain_id"),
                "department_id": _id.get("department_id"),
                "department_name": (dep or {}).get("name"),
                "department_code": (dep or {}).get("code"),
                "paper_count": 0, "faculty_count": 0, "kerberos_set": [],
            }
        return rows[key]

    for mask in MASKS:
        for with_dept in (False, True):
            for r in R.aggregate(paper_count_pipeline(mask, with_dept), allowDiskUse=True):
                combo_row(r["_id"])["paper_count"] = r["paper_count"]
            for r in R.aggregate(faculty_count_pipeline(mask, with_dept), allowDiskUse=True):
                combo_row(r["_id"])["faculty_count"] = r["faculty_count"]
            for r in R.aggregate(members_pipeline(mask, with_dept), allowDiskUse=True):
                combo_row(r["_id"])["kerberos_set"] = r["kerberos_set"]
        print(f"aggregated mask {mask}")

    all_rows = [r for r in rows.values() if r["paper_count"] > 0]

    # --- node stats ---
    def is_theme(r): return r["thematic_area_id"] and not r["domain_id"] and not r["subdomain_id"] and not r["department_id"]
    def is_domain(r): return r["domain_id"] and not r["thematic_area_id"] and not r["subdomain_id"] and not r["department_id"]
    def is_subdomain(r): return r["subdomain_id"] and not r["thematic_area_id"] and not r["department_id"]

    def write_node_stats(coll, id_field, pred):
        per = [r for r in all_rows if pred(r)]
        if per:
            coll.bulk_write([UpdateOne({"_id": r[id_field]}, {"$set": {
                "stats.paper_count": r["paper_count"],
                "stats.faculty_count": r["faculty_count"],
                "stats.updated_at": now}}) for r in per])
        print(f"{coll.name}.stats updated for {len(per)} nodes")
        return len(per)

    n_theme = write_node_stats(d.thematicareas, "thematic_area_id", is_theme)
    n_domain = write_node_stats(d.domains, "domain_id", is_domain)
    n_sub = write_node_stats(d.subdomains, "subdomain_id", is_subdomain)

    sub_counts = list(d.subdomains.aggregate([{"$group": {"_id": "$domain_id", "count": {"$sum": 1}}}]))
    if sub_counts:
        d.domains.bulk_write([UpdateOne({"_id": r["_id"]}, {"$set": {"stats.subdomain_count": r["count"]}})
                              for r in sub_counts])

    # --- facet cube + members (rebuild from scratch) ---
    count_docs = [{k: v for k, v in r.items() if k != "kerberos_set"} | {"updated_at": now} for r in all_rows]
    member_docs = []
    for r in all_rows:
        if not r["kerberos_set"]:
            continue
        srt = sorted(r["kerberos_set"], key=lambda k: h_index.get(k, 0), reverse=True)
        member_docs.append({
            "thematic_area_id": r["thematic_area_id"], "domain_id": r["domain_id"],
            "subdomain_id": r["subdomain_id"], "department_id": r["department_id"],
            "kerberos_list": srt[:MEMBERS_CAP], "faculty_total": len(srt), "updated_at": now})

    d.taxonomyfacetcounts.delete_many({})
    d.taxonomyfacetcounts.insert_many(count_docs, ordered=False)
    d.taxonomyfacetmembers.delete_many({})
    d.taxonomyfacetmembers.insert_many(member_docs, ordered=False)
    print(f"\nWrote {len(count_docs)} facet-count rows and {len(member_docs)} member rows.")
    print(f"node stats: themes={n_theme} domains={n_domain} subdomains={n_sub}")
    client.close()
    print("Rollup done.")


if __name__ == "__main__":
    main()
