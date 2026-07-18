"""Step 12 (classification-v2): verify the Colab-produced embeddings .npz.

Loads the .npz produced by the Colab notebook (parallel `ids` and `emb` arrays)
and runs the go/no-go checks required before the Step-3 classification pilot:

  * file loads; emb.shape == (N, 1024); dtype float16; vectors L2-normalized
  * len(ids) == 68644, unique, and == row count of papers_for_embedding.jsonl
  * a random sample of ids (default 2,000) joins back to Mongo `_id`
  * the FULL id set equals the export id set (set equality; missing/extra flagged)

Usage
-----
    python s12_verify_embeddings_loader.py [path_to_npz] [--expect-dim 1024]
        [--expect-n 68644] [--sample-join 2000] [--seed 42]

Defaults to outputs/work/paper_embeddings_bge_large.npz. READ-ONLY DB access.
"""
import argparse
import json
import sys

import numpy as np

from common import get_db, WORK


def load_npz(path):
    z = np.load(path, allow_pickle=True)
    if "ids" not in z or "emb" not in z:
        raise SystemExit(f"{path} must contain arrays 'ids' and 'emb'; got {z.files}")
    ids = [str(x) for x in z["ids"]]
    emb = z["emb"]
    return ids, emb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz", nargs="?", default=str(WORK / "paper_embeddings_bge_large.npz"))
    ap.add_argument("--expect-dim", type=int, default=1024)
    ap.add_argument("--expect-n", type=int, default=68644)
    ap.add_argument("--sample-join", type=int, default=2000)
    ap.add_argument("--norm-sample", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--export-jsonl", default=str(WORK / "papers_for_embedding.jsonl"))
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    ok = True

    print(f"loading {args.npz}")
    ids, emb = load_npz(args.npz)
    n = len(ids)
    print(f"  ids: {n}")
    print(f"  emb: shape={emb.shape}, dtype={emb.dtype}")

    # ---- shape / dtype ----
    if emb.ndim != 2:
        print(f"  FAIL: emb is not 2-D (ndim={emb.ndim})")
        ok = False
        dim = None
    else:
        dim = emb.shape[1]

    if emb.shape[0] != n:
        print(f"  FAIL: emb rows ({emb.shape[0]}) != ids ({n})")
        ok = False

    if dim == args.expect_dim:
        print(f"  dim == {args.expect_dim}: OK")
    else:
        print(f"  FAIL: dim {dim} != expected {args.expect_dim}")
        ok = False

    if str(emb.dtype) == "float16":
        print("  dtype == float16: OK")
    else:
        print(f"  WARNING: dtype is {emb.dtype}, expected float16")

    # ---- N checks ----
    if n == args.expect_n:
        print(f"  N == {args.expect_n}: OK")
    else:
        print(f"  FAIL: N {n} != expected {args.expect_n}")
        ok = False

    n_unique = len(set(ids))
    if n_unique == n:
        print("  ids are unique: OK")
    else:
        print(f"  FAIL: {n - n_unique} duplicate ids")
        ok = False

    # ---- L2 norm sanity on a large random sample ----
    k = min(args.norm_sample, n)
    idx = rng.choice(n, size=k, replace=False)
    norms = np.linalg.norm(emb[idx].astype(np.float32), axis=1)
    nmin, nmax, nmean, nstd = float(norms.min()), float(norms.max()), float(norms.mean()), float(norms.std())
    print(f"  L2 norms over {k} sampled rows: min={nmin:.4f} max={nmax:.4f} "
          f"mean={nmean:.4f} std={nstd:.5f}")
    if abs(nmean - 1.0) < 0.02 and nmin > 0.9 and nmax < 1.1:
        print("  vectors are L2-normalized (~1.0): OK")
    else:
        print("  FAIL: vectors do not appear L2-normalized")
        ok = False

    # ---- compare id set to the export manifest (papers_for_embedding.jsonl) ----
    export_ids = []
    try:
        with open(args.export_jsonl, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    export_ids.append(str(json.loads(line)["id"]))
    except FileNotFoundError:
        print(f"  WARNING: export manifest not found at {args.export_jsonl}; skipping set-equality")
        export_ids = None

    if export_ids is not None:
        print(f"  export manifest rows: {len(export_ids)}")
        set_npz, set_exp = set(ids), set(export_ids)
        missing = set_exp - set_npz   # in export but not embedded
        extra = set_npz - set_exp     # embedded but not in export
        if not missing and not extra:
            print("  id set == export id set: OK")
        else:
            print(f"  FAIL: set mismatch -> missing(in export, not npz)={len(missing)} "
                  f"extra(in npz, not export)={len(extra)}")
            for s in list(missing)[:5]:
                print(f"      missing: {s}")
            for s in list(extra)[:5]:
                print(f"      extra:   {s}")
            ok = False

    # ---- join a random sample back to Mongo ----
    from bson import ObjectId

    def to_oid(s):
        try:
            return ObjectId(s)
        except Exception:
            return None

    sj = min(args.sample_join, n)
    sample_idx = rng.choice(n, size=sj, replace=False)
    sample_ids = [ids[i] for i in sample_idx]
    sample_oids = [to_oid(s) for s in sample_ids]
    bad_oid = sum(1 for o in sample_oids if o is None)
    if bad_oid:
        print(f"  WARNING: {bad_oid} sampled ids are not valid ObjectId strings")

    db = get_db()
    coll = db.researchmetadatascopus
    valid_oids = [o for o in sample_oids if o is not None]
    found = coll.count_documents({"_id": {"$in": valid_oids}})
    print(f"  random-sample join: {found}/{len(valid_oids)} ids found in Mongo")
    if found == len(valid_oids) and bad_oid == 0:
        print("  sampled round-trip join: OK (100%)")
    else:
        print("  FAIL: not all sampled ids joined back to the collection")
        ok = False

    print("\n  sample joined records:")
    for s in sample_ids[:5]:
        o = to_oid(s)
        doc = coll.find_one({"_id": o}, {"title": 1}) if o else None
        title = (doc or {}).get("title", "<not found>")
        print(f"    {s} -> {str(title)[:80]}")

    verdict = {
        "npz": args.npz,
        "N": n,
        "dim": dim,
        "dtype": str(emb.dtype),
        "unique_ids": n_unique == n,
        "norm_mean": round(nmean, 5),
        "norm_min": round(nmin, 5),
        "norm_max": round(nmax, 5),
        "sample_join_found": found,
        "sample_join_total": len(valid_oids),
        "set_equal_to_export": (export_ids is not None and not missing and not extra),
        "passed": ok,
    }
    (WORK / "verify_embeddings_verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8")
    print("\nVERDICT:", json.dumps(verdict))
    print("RESULT:", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
