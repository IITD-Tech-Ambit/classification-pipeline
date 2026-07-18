"""Stage 3b(i) — build atlas_papers.json from the EXISTING atlas point cloud
(active version) relabeled with v2 theme/domain. Coordinates/citations/dept are
reused (the 3D layout embedding is not recomputed — build_atlas.py + source
Excel are absent from this checkout). Output feeds the app's build_atlas_tiles.py.
"""
import json
import socket
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
WORK = OUTPUTS / "work"
CREDS = "admin:JhXqC1OUPWlLm2zFUPBYDIlkDiyYOQK4"
OUT = WORK / "atlas_papers_v2.json"


def db():
    host = socket.gethostbyname(socket.gethostname())
    return MongoClient(f"mongodb://{CREDS}@{host}:27017/research_ambit?authSource=admin")["research_ambit"]


def main():
    d = db()
    ptr = d.atlas_meta.find_one({"_id": "active", "kind": "pointer"})
    version = ptr["version"]
    print(f"source atlas version: {version}  points={d.atlas_points.count_documents({'version': version})}")

    v2 = {}
    for line in (OUTPUTS / "classification_v2_final.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            v2[o["id"]] = o

    papers = []
    relabeled = unclassified = unchanged_theme = 0
    for p in d.atlas_points.find({"version": version}):
        pid = p.get("id")
        o = v2.get(pid)
        if o is None or o.get("unclassifiable"):
            theme, domain = "Unclassified", ""
            unclassified += 1
        else:
            theme, domain = o["thematic_area"], o["domain"]
            relabeled += 1
            if theme == p.get("theme"):
                unchanged_theme += 1
        papers.append({
            "i": p["i"], "id": pid, "title": p.get("title", ""),
            "theme": theme, "domain": domain, "subdomain": "", "topic": "",
            "department": p.get("department", ""),
            "citations": int(p.get("citations", 0) or 0),
            "x": p["x"], "y": p["y"], "z": p["z"],
        })

    WORK.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"count": len(papers), "papers": papers}, ensure_ascii=False),
                   encoding="utf-8")
    themes = sorted({p["theme"] for p in papers})
    domains = sorted({p["domain"] for p in papers if p["domain"]})
    print(f"wrote {OUT}  papers={len(papers)} relabeled={relabeled} unclassified={unclassified} "
          f"(theme_unchanged={unchanged_theme})")
    print(f"distinct themes in atlas source: {len(themes)} -> {themes}")
    print(f"distinct domains in atlas source: {len(domains)}")


if __name__ == "__main__":
    main()
