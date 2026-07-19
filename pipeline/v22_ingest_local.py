"""LOCAL-ONLY ingest of accepted v2.2 candidate + rebuild rollups/atlas/KG.

Never touches production. Uses LAN IP Docker Mongo gate from i01_ingest_v2.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
WORK = OUTPUTS / "work"
REPO = ROOT.parent
JSONL = OUTPUTS / "classification_v2_2_candidate.jsonl"
TAXONOMY = OUTPUTS / "taxonomy-draft-v22.json"
BACKUP_DIR = OUTPUTS / "db_backup_pre_v22_ingest"
ATLAS_SRC = WORK / "atlas_papers_v22.json"
REPORT = OUTPUTS / "v22_ingest_report.md"
VALIDATION = WORK / "v22_ingest_validation.json"
STATS = WORK / "v22_ingest_stats.json"

# reuse helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from i01_ingest_v2 import (  # noqa: E402
    CREDS,
    bootstrap_nodes,
    connect_local,
    slugify_unique,
)


def backup_local_mongo(db) -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    pre = {
        "papers": db.researchmetadatascopus.estimated_document_count(),
        "themes": db.thematicareas.count_documents({}),
        "domains": db.domains.count_documents({}),
        "unclassifiable": db.researchmetadatascopus.count_documents({"classification.unclassifiable": True}),
        "with_theme": db.researchmetadatascopus.count_documents({"classification.thematic_area_id": {"$ne": None}}),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostbyname(socket.gethostname()),
    }
    (BACKUP_DIR / "pre_backup_counts.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")

    # dump inside container then copy out
    dump_cmd = [
        "docker",
        "exec",
        "mongodb",
        "mongodump",
        f"--uri=mongodb://{CREDS}@localhost:27017/?authSource=admin",
        "--db=research_ambit",
        "--out=/tmp/v22_pre_ingest_dump",
    ]
    print("[backup]", " ".join(dump_cmd))
    subprocess.run(dump_cmd, check=True)
    # clear prior dump folder in backup
    dest = BACKUP_DIR / "research_ambit"
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        ["docker", "cp", "mongodb:/tmp/v22_pre_ingest_dump/research_ambit", str(dest)],
        check=True,
    )
    (BACKUP_DIR / "RESTORE_INSTRUCTIONS.md").write_text(
        "\n".join(
            [
                "# Restore instructions — pre-v2.2-ingest backup",
                "",
                "Full `mongodump` of LOCAL Docker Mongo (`research_ambit`) before v2.2 ingest.",
                "",
                f"- Backup: `{BACKUP_DIR / 'research_ambit'}`",
                f"- Pre-backup counts: `{BACKUP_DIR / 'pre_backup_counts.json'}`",
                "",
                "## Full restore",
                "",
                "```bash",
                f'docker cp "./classification-pipeline/outputs/db_backup_pre_v22_ingest/research_ambit" mongodb:/tmp/restore_research_ambit',
                "",
                "docker exec mongodb mongorestore \\",
                f'  --uri="mongodb://{CREDS}@localhost:27017/?authSource=admin" \\',
                "  --drop --nsInclude='research_ambit.*' \\",
                "  /tmp/restore_research_ambit",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return pre


def load_taxonomy_pairs():
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
    with open(JSONL, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def ingest(db, rows, theme_names, domain_names, tax_pairs):
    bad = set()
    for r in rows:
        if not r.get("unclassifiable"):
            if (r["thematic_area"], r["domain"]) not in tax_pairs:
                bad.add((r["thematic_area"], r["domain"]))
    if bad:
        raise SystemExit(f"ABORT: jsonl pairs not in taxonomy: {list(bad)[:20]}")

    theme_id, domain_id = bootstrap_nodes(db, theme_names, domain_names, dry=False)
    now = datetime.now(timezone.utc)
    ops = []
    n_classified = n_unclass = n_missing = written = 0
    R = db.researchmetadatascopus

    def flush():
        nonlocal ops, written
        if ops:
            res = R.bulk_write(ops, ordered=False)
            written += res.modified_count
        ops = []

    for r in rows:
        _id = ObjectId(r["id"])
        if r.get("unclassifiable"):
            cls = {
                "thematic_area_id": None,
                "domain_id": None,
                "subdomain_id": None,
                "topics": [],
                "classified_at": now,
                "unclassifiable": True,
            }
            n_unclass += 1
        else:
            tid = theme_id.get(r["thematic_area"])
            did = domain_id.get(r["domain"])
            if tid is None or did is None:
                n_missing += 1
                continue
            cls = {
                "thematic_area_id": tid,
                "domain_id": did,
                "subdomain_id": None,
                "topics": [],
                "classified_at": now,
                "unclassifiable": False,
            }
            n_classified += 1
        ops.append(UpdateOne({"_id": _id}, {"$set": {"classification": cls}}))
        if len(ops) >= 1000:
            flush()
    flush()
    return {
        "classified": n_classified,
        "unclassifiable": n_unclass,
        "missing_node": n_missing,
        "docs_modified": written,
        "themes": db.thematicareas.count_documents({}),
        "domains": db.domains.count_documents({}),
    }


def build_atlas_source(db, rows_by_id):
    ptr = db.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
    version = ptr["version"]
    papers = []
    relabeled = unclassified = 0
    for p in db.atlas_points.find({"version": version}):
        pid = p.get("id")
        o = rows_by_id.get(pid)
        if o is None or o.get("unclassifiable"):
            theme, domain = "Unclassified", ""
            unclassified += 1
        else:
            theme, domain = o["thematic_area"], o["domain"]
            relabeled += 1
        papers.append(
            {
                "i": p["i"],
                "id": pid,
                "title": p.get("title", ""),
                "theme": theme,
                "domain": domain,
                "subdomain": "",
                "topic": "",
                "department": p.get("department", ""),
                "citations": int(p.get("citations", 0) or 0),
                "x": p["x"],
                "y": p["y"],
                "z": p["z"],
            }
        )
    ATLAS_SRC.write_text(json.dumps({"count": len(papers), "papers": papers}, ensure_ascii=False), encoding="utf-8")
    return {
        "source_version": version,
        "points": len(papers),
        "relabeled": relabeled,
        "unclassified": unclassified,
        "path": str(ATLAS_SRC),
    }


def publish_atlas_tiles():
    tiles_py = REPO / "research-ambit-main" / "knowledge-graph" / "pipeline" / "build_atlas_tiles.py"
    if not tiles_py.exists():
        raise SystemExit(f"missing {tiles_py}")
    host = socket.gethostbyname(socket.gethostname())
    uri = f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin"
    cmd = [
        sys.executable,
        str(tiles_py),
        "--atlas",
        str(ATLAS_SRC),
        "--mongo-uri",
        uri,
    ]
    print("[atlas]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(tiles_py.parent))


def validate(db, rows):
    theme_name = {x["_id"]: x["name"] for x in db.thematicareas.find({}, {"name": 1})}
    jl_theme = Counter()
    jl_unclass = 0
    for r in rows:
        if r.get("unclassifiable"):
            jl_unclass += 1
        else:
            jl_theme[r["thematic_area"]] += 1
    db_theme = Counter()
    for row in db.researchmetadatascopus.aggregate(
        [
            {"$match": {"classification.thematic_area_id": {"$ne": None}}},
            {"$group": {"_id": "$classification.thematic_area_id", "n": {"$sum": 1}}},
        ]
    ):
        db_theme[theme_name[row["_id"]]] = row["n"]
    db_unclass = db.researchmetadatascopus.count_documents({"classification.unclassifiable": True})
    theme_match = {t: db_theme[t] == jl_theme[t] for t in jl_theme}
    out = {
        "papers_total_db": db.researchmetadatascopus.count_documents({}),
        "papers_total_file": len(rows),
        "classified_db": sum(db_theme.values()),
        "classified_file": sum(jl_theme.values()),
        "unclassifiable_db": db_unclass,
        "unclassifiable_file": jl_unclass,
        "themes_db": db.thematicareas.count_documents({}),
        "domains_db": db.domains.count_documents({}),
        "theme_match": theme_match,
        "all_themes_match": all(theme_match.values()),
        "counts_match": (
            db.researchmetadatascopus.count_documents({}) == len(rows)
            and sum(db_theme.values()) == sum(jl_theme.values())
            and db_unclass == jl_unclass
        ),
        "per_theme": {t: {"db": db_theme[t], "file": jl_theme[t]} for t in sorted(jl_theme, key=lambda x: -jl_theme[x])},
    }
    VALIDATION.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def write_report(pre, ingest_stats, atlas_stats, val, kg_note):
    lines = [
        "# INGEST REPORT — classification-v2.2 candidate -> LOCAL database",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        f"**Outcome:** {'✅ SUCCESS' if val.get('counts_match') and val.get('all_themes_match') else '⚠ CHECK RESULTS'}",
        "**Git commits/pushes:** none",
        "**Production writes:** none",
        "",
        "## LOCAL target + backup",
        f"- Pre-ingest backup: `{BACKUP_DIR}`",
        f"- Pre-backup counts: `{pre}`",
        "",
        "## Ingest",
        f"- Candidate: `{JSONL}`",
        f"- Taxonomy: `{TAXONOMY}`",
        f"- Stats: `{ingest_stats}`",
        "",
        "## Atlas / KG",
        f"- Atlas source: `{atlas_stats}`",
        f"- KG: {kg_note}",
        "",
        "## Validation",
        f"- Artifact: `{VALIDATION}`",
        f"- counts_match: {val.get('counts_match')}",
        f"- all_themes_match: {val.get('all_themes_match')}",
        f"- themes/domains DB: {val.get('themes_db')} / {val.get('domains_db')}",
        f"- classified/unclass: {val.get('classified_db')} / {val.get('unclassifiable_db')}",
        "",
        "### Theme counts",
    ]
    for t, c in (val.get("per_theme") or {}).items():
        lines.append(f"- {t}: db={c['db']} file={c['file']}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    if not JSONL.exists() or not TAXONOMY.exists():
        raise SystemExit("missing v22 candidate or taxonomy")

    client, db = connect_local()
    print("[1] backup")
    pre = backup_local_mongo(db)

    print("[2] ingest")
    theme_names, domain_names, tax_pairs = load_taxonomy_pairs()
    rows = load_jsonl()
    print(f"  rows={len(rows)} themes={len(theme_names)} domains={len(domain_names)}")
    ingest_stats = ingest(db, rows, theme_names, domain_names, tax_pairs)
    print("  ingest_stats", ingest_stats)

    print("[3] rollup")
    subprocess.run([sys.executable, str(Path(__file__).parent / "i03_rollup.py")], check=True)

    print("[4] atlas source")
    rows_by_id = {r["id"]: r for r in rows}
    atlas_stats = build_atlas_source(db, rows_by_id)
    print("  atlas", atlas_stats)

    print("[5] publish atlas tiles")
    publish_atlas_tiles()

    print("[6] rebuild KG")
    subprocess.run([sys.executable, str(Path(__file__).parent / "i05_rebuild_kg.py")], check=True)
    ptr = db.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
    ver = ptr["version"]
    kg_note = (
        f"version={ver}; kg_faculty_graphs={db.kg_faculty_graphs.count_documents({'version': ver})}; "
        f"kg_explore={db.kg_explore.count_documents({'version': ver})}; "
        f"kg_indices={db.kg_indices.count_documents({'version': ver})}"
    )

    print("[7] validate")
    val = validate(db, rows)
    STATS.write_text(
        json.dumps({"pre": pre, "ingest": ingest_stats, "atlas": atlas_stats, "validation": val, "kg": kg_note}, indent=2),
        encoding="utf-8",
    )
    write_report(pre, ingest_stats, atlas_stats, val, kg_note)
    client.close()
    print("Done.", REPORT)
    if not (val.get("counts_match") and val.get("all_themes_match")):
        sys.exit(2)


if __name__ == "__main__":
    main()
