"""Build outputs/work/papers_source.jsonl = {id, title, abstract, hygiene} for
all eligible papers (hygiene status ok | title_only), pulled READ-ONLY from
Mongo once so the classification runners never need the DB again and are fully
reproducible/resumable. title_only papers keep only their title.
"""
import json

from bson import ObjectId

from common import get_db, WORK

HYGIENE = WORK / "hygiene_flags.jsonl"
SOURCE = WORK / "papers_source.jsonl"


def eligible():
    elig = {}
    with open(HYGIENE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["status"] in ("ok", "title_only"):
                elig[r["_id"]] = r["status"]
    return elig


def main():
    elig = eligible()
    print(f"eligible papers: {len(elig)}")

    if SOURCE.exists():
        have = set()
        with open(SOURCE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    have.add(json.loads(line)["id"])
        if have >= set(elig):
            print(f"source cache already complete ({len(have)} rows); skipping")
            return
        print(f"source cache partial ({len(have)}); rebuilding fully")

    db = get_db()
    coll = db.researchmetadatascopus
    ids = list(elig)
    B = 2000
    written = 0
    with open(SOURCE, "w", encoding="utf-8") as out:
        for i in range(0, len(ids), B):
            chunk = ids[i:i + B]
            oids = [ObjectId(x) for x in chunk]
            docs = {}
            for d in coll.find({"_id": {"$in": oids}},
                               {"title": 1, "abstract": 1}):
                docs[str(d["_id"])] = d
            for pid in chunk:
                d = docs.get(pid, {})
                title = (d.get("title") or "").strip()
                hyg = elig[pid]
                abstract = "" if hyg == "title_only" else (d.get("abstract") or "").strip()
                out.write(json.dumps({
                    "id": pid, "title": title, "abstract": abstract, "hygiene": hyg
                }, ensure_ascii=False) + "\n")
                written += 1
            print(f"  wrote {written}/{len(ids)}", flush=True)
    print(f"DONE: {written} rows -> {SOURCE}")

    # sanity: missing titles
    empties = 0
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if not r["title"]:
                empties += 1
    print(f"rows with empty title: {empties}")


if __name__ == "__main__":
    main()
