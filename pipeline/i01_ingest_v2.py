"""Stage 2 — ingest classification-v2 labels into the LOCAL Docker Mongo.

SAFE / REVERSIBLE / LOCAL-ONLY. Idempotent:
  * taxonomy nodes are upserted by name (stable _ids) and stale nodes removed;
  * each paper's `classification` sub-doc is overwritten (never appended);
  * `iitd_authors` is NEVER touched.

Mirrors SEO-Backend-iitd/scripts/taxonomy/{ingest.js, lib/*}: same slugify,
same classification field shape the search-api read paths expect.
"""
import argparse
import ipaddress
import json
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"
JSONL = OUTPUTS / "classification_v2_final.jsonl"
TAXONOMY = OUTPUTS / "taxonomy-draft-v3-baseline-backup.json"


# --- exact port of scripts/taxonomy/lib/slugify.js --------------------------
def slugify(name):
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s


def slugify_unique(names):
    used, by_name = set(), {}
    for name in names:
        base = slugify(name)
        slug, n = base, 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        by_name[name] = slug
    return by_name


def connect_local():
    """Connect to the LOCAL Docker Mongo via the LAN IP (localhost is shadowed
    by a native Windows Mongo). Refuse to proceed unless the target is clearly
    a local/standalone instance."""
    hosts = ["localhost", socket.gethostbyname(socket.gethostname())]
    last = None
    for host in hosts:
        uri = f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin"
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            db = client["research_ambit"]
            if db.researchmetadatascopus.estimated_document_count() > 0:
                addr = client.address
                hello = client.admin.command("hello")
                is_standalone = not hello.get("setName")
                try:
                    ip = ipaddress.ip_address(socket.gethostbyname(addr[0]))
                    is_private = ip.is_private or ip.is_loopback
                except ValueError:
                    is_private = False
                print("=== TARGET DB (must be LOCAL Docker) ===")
                print(f"  server address : {addr[0]}:{addr[1]}")
                print(f"  standalone     : {is_standalone} (setName={hello.get('setName')})")
                print(f"  mongo version  : {client.admin.command('buildInfo')['version']}")
                print(f"  private/loopback host: {is_private}")
                if not (is_standalone and is_private):
                    raise RuntimeError("Refusing to write: target is not a local standalone Mongo.")
                print("  CONFIRMED LOCAL — proceeding.\n")
                return client, db
        except RuntimeError:
            raise
        except Exception as e:  # noqa
            last = e
    raise RuntimeError(f"could not reach a LOCAL research_ambit Mongo: {last}")


def load_taxonomy():
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    themes, domains, pairs = set(), set(), set()
    for th in tax["themes"]:
        themes.add(th["name"])
        for dm in th.get("domains", []):
            domains.add(dm["name"])
            pairs.add((th["name"], dm["name"]))
    return themes, domains, pairs


def load_jsonl():
    rows = []
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def bootstrap_nodes(db, theme_names, domain_names, dry):
    """Upsert themes+domains by name (stable ids), delete stale, clear subdomains."""
    theme_slugs = slugify_unique(sorted(theme_names))
    domain_slugs = slugify_unique(sorted(domain_names))

    def upsert(coll, names, slugs, extra_stats):
        ops = []
        for i, name in enumerate(sorted(names)):
            set_on_insert = {"name": name, "display_order": i, "stats": extra_stats}
            ops.append(UpdateOne(
                {"name": name},
                {"$set": {"slug": slugs[name]}, "$setOnInsert": set_on_insert},
                upsert=True,
            ))
        if not dry and ops:
            coll.bulk_write(ops, ordered=False)
        # remove stale nodes no longer in v2
        stale = coll.count_documents({"name": {"$nin": list(names)}})
        if not dry and stale:
            coll.delete_many({"name": {"$nin": list(names)}})
        return stale

    stale_t = upsert(db.thematicareas, theme_names,
                     {n: theme_slugs[n] for n in theme_names},
                     {"paper_count": 0, "faculty_count": 0})
    stale_d = upsert(db.domains, domain_names,
                     {n: domain_slugs[n] for n in domain_names},
                     {"paper_count": 0, "faculty_count": 0, "subdomain_count": 0})
    sub_removed = db.subdomains.count_documents({})
    if not dry and sub_removed:
        db.subdomains.delete_many({})

    theme_id = {d["name"]: d["_id"] for d in db.thematicareas.find({}, {"name": 1})}
    domain_id = {d["name"]: d["_id"] for d in db.domains.find({}, {"name": 1})}
    print(f"[nodes] themes={db.thematicareas.count_documents({})} (stale removed {stale_t}) "
          f"domains={db.domains.count_documents({})} (stale removed {stale_d}) "
          f"subdomains cleared={sub_removed}")
    return theme_id, domain_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=1000)
    args = ap.parse_args()

    theme_names, domain_names, tax_pairs = load_taxonomy()
    rows = load_jsonl()
    print(f"taxonomy: {len(theme_names)} themes, {len(domain_names)} domains, {len(tax_pairs)} pairs")
    print(f"jsonl rows: {len(rows)}")

    # SAFETY GATE: every (theme,domain) in the jsonl must exist in the taxonomy.
    bad = set()
    for r in rows:
        if not r.get("unclassifiable"):
            if (r["thematic_area"], r["domain"]) not in tax_pairs:
                bad.add((r["thematic_area"], r["domain"]))
    if bad:
        print("ABORT: jsonl pairs not in taxonomy:", list(bad)[:10])
        sys.exit(1)
    print("gate OK: all jsonl (theme,domain) pairs exist in taxonomy\n")

    client, db = connect_local()
    theme_id, domain_id = bootstrap_nodes(db, theme_names, domain_names, args.dry_run)

    now = datetime.now(timezone.utc)
    ops = []
    n_classified = n_unclass = n_missing = written = 0
    R = db.researchmetadatascopus

    def flush():
        nonlocal ops, written
        if ops and not args.dry_run:
            res = R.bulk_write(ops, ordered=False)
            written += res.modified_count
        ops = []

    for r in rows:
        _id = ObjectId(r["id"])
        if r.get("unclassifiable"):
            cls = {"thematic_area_id": None, "domain_id": None, "subdomain_id": None,
                   "topics": [], "classified_at": now, "unclassifiable": True}
            n_unclass += 1
        else:
            tid = theme_id.get(r["thematic_area"])
            did = domain_id.get(r["domain"])
            if tid is None or did is None:
                n_missing += 1
                continue
            cls = {"thematic_area_id": tid, "domain_id": did, "subdomain_id": None,
                   "topics": [], "classified_at": now, "unclassifiable": False}
            n_classified += 1
        ops.append(UpdateOne({"_id": _id}, {"$set": {"classification": cls}}))
        if len(ops) >= args.batch_size:
            flush()
    flush()

    print(f"\n[ingest] classified={n_classified} unclassifiable={n_unclass} "
          f"missing_node={n_missing} docs_modified={'(dry)' if args.dry_run else written}")
    client.close()
    print("Done." + (" [DRY RUN]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
