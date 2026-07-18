"""Step 3b: re-cluster within each CORRECTED theme pool using the cached embeddings.

Same approach as Step 1 (KMeans + silhouette sweep) but on the clean pools. k range is
adapted to pool size so small pools do not get over-split.
"""
import json

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from common import WORK


def k_range(n):
    # keep enough clusters that naming can always consolidate into 5-10 domains
    lo = 8 if n >= 350 else max(5, n // 50)
    hi = min(14, max(lo, n // 40))
    return range(lo, hi + 1)


def cluster_pool(emb):
    n = len(emb)
    best = None
    for k in k_range(n):
        if k >= n:
            continue
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(emb)
        score = silhouette_score(emb, labels, sample_size=min(2000, n), random_state=42)
        if best is None or score > best["score"]:
            best = {"k": k, "score": float(score), "labels": labels,
                    "centroids": km.cluster_centers_}
    return best


def main():
    pools = json.loads((WORK / "pools_v2.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    flat = np.load(WORK / "emb_flat.npz")["emb"]
    pool_index = pools["pool_index"]
    name_by_id = {t["id"]: t["name"] for t in facts["themes"]}

    results = {}
    centroids = {}
    for tid, pids in pools["pools"].items():
        idx = np.array([pool_index[p] for p in pids])
        emb = flat[idx]
        best = cluster_pool(emb)
        results[tid] = {
            "k": best["k"],
            "silhouette": best["score"],
            "labels": best["labels"].tolist(),
            "pids": pids,
        }
        centroids[tid] = best["centroids"]
        print(f"{name_by_id[tid][:45]:45} n={len(pids):4} k={best['k']:2} "
              f"silhouette={best['score']:.4f}")

    (WORK / "clusters_v2.json").write_text(json.dumps(results), encoding="utf-8")
    np.savez_compressed(WORK / "centroids_v2.npz", **centroids)
    print("done")


if __name__ == "__main__":
    main()
