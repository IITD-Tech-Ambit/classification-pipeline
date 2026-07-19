"""PRODUCTION ingest of v2.2 classification on the VM Mongo instance.

Requires a verified pre-ingest archive backup under main/archive/.
Never run without that rollback snapshot in place.
"""
from __future__ import annotations

import glob
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
WORK = OUTPUTS / "work"
REPO = ROOT.parent.parent if (ROOT.parent / "main").exists() else ROOT.parent
JSONL = OUTPUTS / "classification_v2_2_candidate.jsonl"
TAXONOMY = OUTPUTS / "taxonomy-draft-v22.json"
ATLAS_SRC = WORK / "atlas_papers_v22.json"
REPORT = OUTPUTS / "v22_prod_ingest_report.md"
VALIDATION = WORK / "v22_prod_ingest_validation.json"
STATS = WORK / "v22_prod_ingest_stats.json"
CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"
MONGO_HOST = "127.0.0.1"
BACKUP_GLOB = "/home/baadalvm/main/archive/mongodb_pre_classification_v2_2_*/mongodb_pre_classification_v2_2_*.archive.gz"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v22_ingest_local import (  # noqa: E402
    build_atlas_source,
    ingest,
    load_jsonl,
    load_taxonomy_pairs,
    validate,
    write_report,
)


def require_backup() -> Path:
    matches = sorted(glob.glob(BACKUP_GLOB))
    if not matches:
        raise SystemExit(f"ABORT: no prod backup found at {BACKUP_GLOB}")
    backup = Path(matches[-1])
    if backup.stat().st_size < 1_000_000:
        raise SystemExit(f"ABORT: backup looks too small: {backup}")
    print(f"[safety] rollback backup OK: {backup} ({backup.stat().st_size // 1_048_576} MB)")
    return backup


def connect_prod():
    uri = f"mongodb://{CREDS}@{MONGO_HOST}:27017/research_ambit?authSource=admin"
    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    db = client["research_ambit"]
    hello = client.admin.command("hello")
    if hello.get("setName"):
        raise RuntimeError("Refusing to write: target is a replica set, not standalone prod.")
    papers = db.researchmetadatascopus.estimated_document_count()
    if papers != 70298:
        raise RuntimeError(f"Unexpected paper count {papers}; expected 70298.")
    print("=== PRODUCTION TARGET ===")
    print(f"  host           : {MONGO_HOST}:27017")
    print(f"  mongo version  : {client.admin.command('buildInfo')['version']}")
    print(f"  papers         : {papers}")
    print(f"  themes/domains : {db.thematicareas.count_documents({})} / {db.domains.count_documents({})}")
    print("")
    return client, db


def snapshot_pre(db) -> dict:
    return {
        "papers": db.researchmetadatascopus.estimated_document_count(),
        "themes": db.thematicareas.count_documents({}),
        "domains": db.domains.count_documents({}),
        "subdomains": db.subdomains.count_documents({}),
        "with_theme": db.researchmetadatascopus.count_documents({"classification.thematic_area_id": {"$ne": None}}),
        "unclassifiable": db.researchmetadatascopus.count_documents({"classification.unclassifiable": True}),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
    }


def publish_atlas_tiles():
    tiles_py = REPO / "research-ambit-main" / "knowledge-graph" / "pipeline" / "build_atlas_tiles.py"
    if not tiles_py.exists():
        tiles_py = Path("/home/baadalvm/main/research-ambit-main/knowledge-graph/pipeline/build_atlas_tiles.py")
    if not tiles_py.exists():
        raise SystemExit(f"missing {tiles_py}")
    uri = f"mongodb://{CREDS}@{MONGO_HOST}:27017/research_ambit?authSource=admin"
    cmd = [sys.executable, str(tiles_py), "--atlas", str(ATLAS_SRC), "--mongo-uri", uri]
    print("[atlas]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(tiles_py.parent))


def main():
    if not JSONL.exists() or not TAXONOMY.exists():
        raise SystemExit("missing v22 candidate or taxonomy")

    backup = require_backup()
    client, db = connect_prod()
    pre = snapshot_pre(db)
    (WORK / "v22_prod_pre_counts.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")

    print("[1] ingest")
    theme_names, domain_names, tax_pairs = load_taxonomy_pairs()
    rows = load_jsonl()
    print(f"  rows={len(rows)} themes={len(theme_names)} domains={len(domain_names)}")
    ingest_stats = ingest(db, rows, theme_names, domain_names, tax_pairs)
    print("  ingest_stats", ingest_stats)

    print("[2] rollup")
    subprocess.run([sys.executable, str(Path(__file__).parent / "i03_rollup.py")], check=True)

    print("[3] atlas source")
    rows_by_id = {r["id"]: r for r in rows}
    atlas_stats = build_atlas_source(db, rows_by_id)
    print("  atlas", atlas_stats)

    print("[4] publish atlas tiles")
    publish_atlas_tiles()

    print("[5] rebuild KG")
    subprocess.run([sys.executable, str(Path(__file__).parent / "i05_rebuild_kg.py")], check=True)
    ptr = db.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
    ver = ptr["version"]
    kg_note = (
        f"version={ver}; kg_faculty_graphs={db.kg_faculty_graphs.count_documents({'version': ver})}; "
        f"kg_explore={db.kg_explore.count_documents({'version': ver})}; "
        f"kg_indices={db.kg_indices.count_documents({'version': ver})}"
    )

    print("[6] validate")
    val = validate(db, rows)
    payload = {
        "rollback_backup": str(backup),
        "pre": pre,
        "ingest": ingest_stats,
        "atlas": atlas_stats,
        "validation": val,
        "kg": kg_note,
    }
    STATS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_report(pre, ingest_stats, atlas_stats, val, kg_note)
    report = REPORT.read_text(encoding="utf-8")
    REPORT.write_text(
        report.replace("LOCAL database", "PRODUCTION database")
        .replace("Production writes:** none", f"Production writes:** yes (rollback: `{backup}`)"),
        encoding="utf-8",
    )
    client.close()
    print("Done.", REPORT)
    if not (val.get("counts_match") and val.get("all_themes_match")):
        sys.exit(2)


if __name__ == "__main__":
    main()
