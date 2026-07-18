"""Step 3: KMeans clustering per theme with a k sweep (silhouette), k in 6..14."""
import json

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from common import WORK

K_RANGE = range(6, 15)


def cluster_theme(emb):
    best = None
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(emb)
        score = silhouette_score(emb, labels, sample_size=min(2000, len(emb)), random_state=42)
        if best is None or score > best["score"]:
            best = {"k": k, "score": float(score), "labels": labels, "centroids": km.cluster_centers_}
    return best


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))
    data = np.load(WORK / "embeddings.npz")
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    name_by_id = {t["id"]: t["name"] for t in facts["themes"]}

    results = {}
    centroids = {}
    for tid, papers in samples["by_theme"].items():
        emb = data[tid]
        best = cluster_theme(emb)
        results[tid] = {
            "k": best["k"],
            "silhouette": best["score"],
            "labels": best["labels"].tolist(),
        }
        centroids[tid] = best["centroids"]
        print(f"{name_by_id[tid]}: k={best['k']} silhouette={best['score']:.4f} n={len(papers)}")

    with open(WORK / "clusters.json", "w", encoding="utf-8") as f:
        json.dump(results, f)
    np.savez_compressed(WORK / "centroids.npz", **centroids)
    print("done")


if __name__ == "__main__":
    main()
