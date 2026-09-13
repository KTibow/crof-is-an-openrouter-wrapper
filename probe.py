"""Ask every crof.ai model to call the `openrouter:advisor` tool and repeat its result.

`openrouter:advisor` is an OpenRouter server tool: OpenRouter runs it, and its result names the
OpenRouter model that answered, which by default is the model the request was sent to.
"""

import collections
import json
import os
import sys

from fetch import fetch

MODELS = [
    # Listed on https://crof.ai/v1/models and https://crof.ai/api/page-data/pricing
    "deepseek-v4.1-flash",
    "deepseek-v4-pro-0813",
    "deepseek-v4-flash-vision-exp",
    "deepseek-v4-flash-0731",
    "kimi-k3",
    "kimi-k3-eco",
    "kimi-k2.7-code",
    "kimi-k2.6",
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
    "greg-2-ultra",
    "greg-2-super",
    "mimo-v2.5-pro",
    "gemma-4-31b-it",
    "qwen3.8-27b",
    "qwen3.5-9b",
    # Named only in the pricing page's beta_models and vision_models
    "kimi-k2.5-lightning",
    "glm-5.1-precision",
    "kimi-k2.6-precision",
    "kimi-k2.5",
    "qwen3.6-27b",
    "qwen3.5-397b-a17b",
    "greg-1-mini",
    "greg-1",
    "greg-1-super",
    # Not listed anywhere, but the API accepted them in earlier testing
    "glm-5.1",
    "deepseek-v3.2",
    "deepseek-v4-pro",
]

PROMPT = (
    'Call the advisor tool once, asking it "What is 2+2?". Then reply with ONLY the exact, '
    "verbatim JSON the advisor tool returned to you (every field, unmodified), and nothing else."
)


def find_advisor_result(response_body):
    """Find the advisor JSON the model repeated back. Returns None if there isn't one."""
    try:
        content = json.loads(response_body)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    if content is None:
        return None

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        result = json.loads(content[start : end + 1])
    except ValueError:
        return None
    if "model" not in result:
        return None
    return result


def probe(model):
    """Ask 5 times, save every attempt to results/<model>.json, and return the 5 advisor results."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [{"type": "openrouter:advisor"}],
        "max_tokens": 4000,
    }
    attempts = []
    results = []
    for _ in range(5):
        attempt = fetch("https://crof.ai/v1/chat/completions", body)
        attempts.append(attempt)
        results.append(find_advisor_result(attempt["response_body"]))

    with open(f"results/{model}.json", "w") as f:
        json.dump({"model": model, "advisor_results": results, "attempts": attempts}, f, indent=2)
    return results


os.makedirs("results", exist_ok=True)

# Save what crof.ai lists today.
models_listing = fetch("https://crof.ai/v1/models")
pricing_listing = fetch("https://crof.ai/api/page-data/pricing")
with open("results/listings.json", "w") as f:
    json.dump([models_listing, pricing_listing], f, indent=2)

# Stop if crof.ai lists a model that isn't in MODELS.
models_page = json.loads(models_listing["response_body"])
pricing_page = json.loads(pricing_listing["response_body"])
for model in models_page["data"]:
    if model["id"] not in MODELS:
        sys.exit(f"{model['id']} is on /v1/models but not in MODELS")
for model in pricing_page["models"]:
    if model["id"] not in MODELS:
        sys.exit(f"{model['id']} is in the pricing page's models but not in MODELS")
for model_id in pricing_page["beta_models"]:
    if model_id not in MODELS:
        sys.exit(f"{model_id} is in the pricing page's beta_models but not in MODELS")
for model_id in pricing_page["vision_models"]:
    if model_id not in MODELS:
        sys.exit(f"{model_id} is in the pricing page's vision_models but not in MODELS")

with open("results/summary.md", "w") as summary:
    summary.write("| crof.ai model | `model` in the `openrouter:advisor` result, out of 5 tries |\n")
    summary.write("| --- | --- |\n")
    for model in MODELS:
        results = probe(model)
        print(model, "->", results, flush=True)

        # Count how many times each model name came back.
        counts = collections.Counter()
        for result in results:
            if result is None:
                counts["no advisor result"] += 1
            else:
                counts["`" + str(result["model"]) + "`"] += 1
        cell = "<br>".join(f"{name} ×{count}" for name, count in counts.most_common())
        summary.write(f"| `{model}` | {cell} |\n")
