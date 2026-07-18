"""Preflight for the overnight classification run: DB reachability + Anthropic
model-id verification (1-token calls) for the Haiku main pass and the Sonnet
escalation. READ-ONLY DB. Writes outputs/work/env_check.json."""
import json
import os

import anthropic

from common import get_db, WORK

HAIKU = "claude-haiku-4-5"
SONNET_CANDIDATES = ["claude-sonnet-4-5", "claude-sonnet-4-5-20250929",
                     "claude-sonnet-4-20250514"]

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def tiny_call(model):
    resp = _client.messages.create(
        model=model,
        max_tokens=1,
        messages=[{"role": "user", "content": "Reply with the single character: 1"}],
    )
    return {"ok": True, "stop_reason": resp.stop_reason,
            "in": resp.usage.input_tokens, "out": resp.usage.output_tokens}


def main():
    out = {"db": None, "haiku": None, "sonnet_selected": None, "sonnet_tries": {}}

    # DB check (read-only)
    try:
        db = get_db()
        n = db.researchmetadatascopus.estimated_document_count()
        out["db"] = {"ok": True, "estimated_docs": int(n)}
    except Exception as e:
        out["db"] = {"ok": False, "error": repr(e)}

    # Haiku
    try:
        out["haiku"] = tiny_call(HAIKU)
    except Exception as e:
        out["haiku"] = {"ok": False, "error": repr(e)}

    # Sonnet: try candidates in order, take first that works
    for m in SONNET_CANDIDATES:
        try:
            r = tiny_call(m)
            out["sonnet_tries"][m] = r
            if out["sonnet_selected"] is None:
                out["sonnet_selected"] = m
        except Exception as e:
            out["sonnet_tries"][m] = {"ok": False, "error": repr(e)[:200]}

    (WORK / "env_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
