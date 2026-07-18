"""Step 2: embed sampled papers (title + truncated abstract) with BGE on CPU.

Notes:
- bge-large ran at ~1 min per 32-doc batch on this machine (~3h total) -> using the
  sanctioned fallback BAAI/bge-base-en-v1.5.
- Threads are pinned explicitly; default settings caused heavy contention.
- Saves one .npy per group so an interrupted run resumes where it left off.
"""
import json
import os
import time

os.environ.setdefault("OMP_NUM_THREADS", "8")
os.environ.setdefault("MKL_NUM_THREADS", "8")

import numpy as np
import torch

torch.set_num_threads(8)

from sentence_transformers import SentenceTransformer

from common import WORK

MODEL = "BAAI/bge-base-en-v1.5"


def paper_text(p):
    text = p["title"]
    if p["abstract"]:
        text += ". " + p["abstract"][:900]
    return text


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))
    emb_dir = WORK / "emb"
    emb_dir.mkdir(exist_ok=True)

    model = SentenceTransformer(MODEL, device="cpu")
    print(f"using model: {MODEL}", flush=True)

    all_groups = dict(samples["by_theme"])
    all_groups["__unclassified__"] = samples["unclassified"]

    for key, papers in all_groups.items():
        out_path = emb_dir / f"{key}.npy"
        if out_path.exists():
            print(f"{key}: already done, skipping", flush=True)
            continue
        texts = [paper_text(p) for p in papers]
        t0 = time.time()
        emb = model.encode(texts, batch_size=16, show_progress_bar=False,
                           normalize_embeddings=True)
        np.save(out_path, emb)
        print(f"{key}: {emb.shape} in {time.time()-t0:.0f}s", flush=True)

    # merge into the single npz the rest of the pipeline expects
    merged = {k: np.load(emb_dir / f"{k}.npy") for k in all_groups}
    np.savez_compressed(WORK / "embeddings.npz", **merged)
    (WORK / "embed_model.txt").write_text(MODEL, encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    main()
