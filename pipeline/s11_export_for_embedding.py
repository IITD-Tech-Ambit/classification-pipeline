"""Step 11 (classification-v2): export clean papers for embedding.

READ-ONLY DB access. Reads outputs/work/hygiene_flags.jsonl (from s10) and emits:

  outputs/work/papers_for_embedding.jsonl
      one JSON object per line: {"id": <str _id>, "text": <str>}
      only for papers with hygiene status `ok` or `title_only`.

  outputs/work/embedding_input_manifest.json
      counts, the exact text-construction rule, and sha256 + byte size of the
      jsonl so the file the user uploads to Colab can be verified byte-for-byte.

Text construction rule
-----------------------
- ok         : text = title + "\n\n" + abstract
- title_only : text = title           (abstract omitted, since it is unusable)

`id` is the stringified Mongo `_id`, preserved so embeddings can be joined back later.
"""
import hashlib
import json

from common import get_db, ensure_dirs, WORK

TEXT_RULE = {
    "ok": 'text = title + "\\n\\n" + abstract',
    "title_only": "text = title (abstract omitted)",
    "separator": "\\n\\n",
    "notes": "no query prefix; documents embedded plain for similarity classification",
}


def build_text(status: str, title: str, abstract: str) -> str:
    title = (title or "").strip()
    if status == "ok":
        return title + "\n\n" + (abstract or "").strip()
    # title_only: abstract omitted
    return title


def main():
    ensure_dirs()
    flags_path = WORK / "hygiene_flags.jsonl"
    if not flags_path.exists():
        raise SystemExit("run s10_hygiene_gate.py first (hygiene_flags.jsonl missing)")

    # map id -> status for the papers we keep
    keep = {}
    with open(flags_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["status"] in ("ok", "title_only"):
                keep[rec["_id"]] = rec["status"]
    print(f"papers to export (ok + title_only): {len(keep)}", flush=True)

    db = get_db()
    coll = db.researchmetadatascopus

    out_path = WORK / "papers_for_embedding.jsonl"
    n_written = 0
    n_ok = 0
    n_title_only = 0
    empty_text = 0

    # stream from Mongo; only project what we need
    cursor = coll.find({}, {"title": 1, "abstract": 1}, no_cursor_timeout=True)
    with open(out_path, "w", encoding="utf-8") as out:
        for doc in cursor:
            _id = str(doc["_id"])
            status = keep.get(_id)
            if status is None:
                continue
            text = build_text(status, doc.get("title", ""), doc.get("abstract", ""))
            if not text.strip():
                empty_text += 1
            out.write(json.dumps({"id": _id, "text": text}, ensure_ascii=False) + "\n")
            n_written += 1
            if status == "ok":
                n_ok += 1
            else:
                n_title_only += 1
            if n_written % 10000 == 0:
                print(f"  {n_written}/{len(keep)} written", flush=True)
    cursor.close()

    # sha256 + size for verification against the uploaded file
    h = hashlib.sha256()
    size = 0
    with open(out_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)

    manifest = {
        "source_collection": "researchmetadatascopus",
        "hygiene_flags": "outputs/work/hygiene_flags.jsonl",
        "output_file": "outputs/work/papers_for_embedding.jsonl",
        "rows": n_written,
        "rows_ok": n_ok,
        "rows_title_only": n_title_only,
        "rows_with_empty_text": empty_text,
        "id_field": "stringified Mongo _id",
        "text_construction_rule": TEXT_RULE,
        "sha256": h.hexdigest(),
        "bytes": size,
        "mb": round(size / (1024 * 1024), 2),
        "embedding_model_target": "BAAI/bge-large-en-v1.5",
        "embedding_dim": 1024,
        "normalize_embeddings": True,
        "query_prefix": None,
    }
    manifest_path = WORK / "embedding_input_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n=== export done ===")
    print(f"  rows: {n_written} (ok={n_ok}, title_only={n_title_only})")
    print(f"  empty text rows: {empty_text}")
    print(f"  size: {manifest['mb']} MB")
    print(f"  sha256: {manifest['sha256']}")
    print(f"  wrote {out_path}")
    print(f"  wrote {manifest_path}")


if __name__ == "__main__":
    main()
