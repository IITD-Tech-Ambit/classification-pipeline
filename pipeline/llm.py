"""Claude helper with JSON parsing and token/cost accounting."""
import json
import os
import re
import time

import anthropic

from common import WORK

MODEL = "claude-haiku-4-5"
# claude-haiku-4-5 pricing (USD per million tokens)
PRICE_IN = 1.00
PRICE_OUT = 5.00

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
USAGE_FILE = WORK / "llm_usage.json"


def _record_usage(usage):
    data = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    if USAGE_FILE.exists():
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    data["input_tokens"] += usage.input_tokens
    data["output_tokens"] += usage.output_tokens
    data["calls"] += 1
    data["est_cost_usd"] = round(
        data["input_tokens"] / 1e6 * PRICE_IN + data["output_tokens"] / 1e6 * PRICE_OUT, 4
    )
    USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ask(prompt, max_tokens=4000, retries=3):
    for attempt in range(retries):
        try:
            resp = _client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            _record_usage(resp.usage)
            return resp.content[0].text
        except anthropic.APIError as e:
            if attempt == retries - 1:
                raise
            print(f"API error ({e}), retrying...")
            time.sleep(5 * (attempt + 1))


def ask_json(prompt, max_tokens=4000):
    text = ask(prompt, max_tokens=max_tokens)
    # strip markdown fences if present
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0])
    text = text[start:]
    return json.loads(text)
