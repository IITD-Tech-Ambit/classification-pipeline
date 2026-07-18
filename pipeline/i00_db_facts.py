"""READ-ONLY: probe the LOCAL Docker Mongo and report facts for the ingest plan.

Confirms the connection target (host/port), lists collections + counts, and
inspects the classification schema on researchmetadatascopus. No writes.
"""
import json
import socket

from pymongo import MongoClient

CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"


def connect():
    """Same strategy as pipeline/common.py: a native Windows Mongo shadows
    127.0.0.1, so fall back to the LAN IP that reaches the Docker container."""
    hosts = ["localhost", socket.gethostbyname(socket.gethostname())]
    last = None
    for host in hosts:
        uri = f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin"
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            db = client["research_ambit"]
            if db.researchmetadatascopus.estimated_document_count() > 0:
                return client, db, host
        except Exception as e:  # noqa
            last = e
    raise RuntimeError(f"could not reach research_ambit Mongo: {last}")


def main():
    client, db, host = connect()
    resolved = socket.gethostbyname(host) if host != "localhost" else "127.0.0.1"
    info = {}
    info["connected_host"] = host
    info["resolved_ip"] = resolved
    # who are we actually talking to?
    hello = client.admin.command("hello")
    info["mongo_me"] = hello.get("me")
    info["set_name"] = hello.get("setName", "(standalone)")
    build = client.admin.command("buildInfo")
    info["mongo_version"] = build.get("version")
    info["server_address"] = [f"{h}:{p}" for h, p in [client.address]]

    facts = {"connection": info}

    colls = sorted(db.list_collection_names())
    facts["collections"] = {}
    for c in colls:
        facts["collections"][c] = db[c].estimated_document_count()

    R = db.researchmetadatascopus
    facts["papers_total"] = R.count_documents({})
    facts["papers_with_classification"] = R.count_documents({"classification": {"$exists": True}})
    facts["papers_with_theme_id"] = R.count_documents({"classification.thematic_area_id": {"$ne": None}})
    facts["papers_with_domain_id"] = R.count_documents({"classification.domain_id": {"$ne": None}})
    facts["papers_with_subdomain_id"] = R.count_documents({"classification.subdomain_id": {"$ne": None}})
    facts["papers_with_iitd_authors"] = R.count_documents({"iitd_authors.0": {"$exists": True}})

    sample = R.find_one({"classification": {"$exists": True}}, {"title": 1, "classification": 1, "iitd_authors": 1})
    if sample:
        sample["_id"] = str(sample["_id"])
        cls = sample.get("classification") or {}
        for k in ("thematic_area_id", "domain_id", "subdomain_id"):
            if cls.get(k) is not None:
                cls[k] = str(cls[k])
        for a in sample.get("iitd_authors", []) or []:
            for k in ("faculty_ref", "department_ref"):
                if a.get(k) is not None:
                    a[k] = str(a[k])
        facts["sample_classified_paper"] = sample

    # taxonomy node collections
    for coll, label in [("thematicareas", "themes"), ("domains", "domains"), ("subdomains", "subdomains")]:
        if coll in colls:
            docs = list(db[coll].find({}, {"name": 1, "slug": 1}).limit(5))
            facts[f"{label}_count"] = db[coll].count_documents({})
            facts[f"{label}_sample"] = [d.get("name") for d in docs]

    # atlas / kg state
    if "atlas_meta" in colls:
        ptr = db.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
        facts["atlas_active_version"] = ptr.get("version") if ptr else None
    for c in ("atlas_points", "atlas_tiles", "kg_faculty_graphs", "kg_explore", "kg_indices"):
        if c in colls:
            facts[f"{c}_count"] = db[c].count_documents({})

    print(json.dumps(facts, indent=2, ensure_ascii=False, default=str))
    client.close()


if __name__ == "__main__":
    main()
