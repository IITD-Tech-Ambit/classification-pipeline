"""Verify the two model ids resolve with a cheap 1-token call each.
Cost is a fraction of a cent; recorded so the running task total stays honest.
"""
import json
import os
import time

import anthropic
from dotenv import load_dotenv

from common import ROOT, WORK
from s15_classify_lib import cost_from_usage

load_dotenv(ROOT / ".env")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60.0)

MODELS = ["claude-haiku-4-5", "claude-sonnet-4-5"]


def main():
    results = {}
    total = 0.0
    for m in MODELS:
        try:
            r = client.messages.create(
                model=m, max_tokens=1,
                messages=[{"role": "user", "content": "Reply with the single token: ok"}],
            )
            u = {"input_tokens": int(r.usage.input_tokens),
                 "output_tokens": int(r.usage.output_tokens),
                 "cache_write": 0, "cache_read": 0}
            c = cost_from_usage(m, u)
            total += c
            results[m] = {"resolved": True, "stop_reason": r.stop_reason,
                          "usage": u, "cost_usd": round(c, 6)}
        except Exception as e:
            results[m] = {"resolved": False, "error": repr(e)}
        time.sleep(0.3)
    results["verify_cost_usd"] = round(total, 6)
    results["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (WORK / "refine_verify_models.json").write_text(json.dumps(results, indent=2),
                                                    encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
