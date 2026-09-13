"""Show that crof.ai's beta API blocks `openrouter:advisor`, but still hands images to OpenRouter.

67.nahcrof.com is the new version of crof.ai's API. It answers 400 to every tool that isn't a
function tool, so the request probe.py sends doesn't work there.

Images show the same thing another way. When a request includes an image URL, whoever runs the
model has to download that image. This script serves an image at an address it controls, sends its
URL to every model on crof.ai and on 67.nahcrof.com, and records who downloads it.
"""

import json
import os
import time
import urllib.request

import image_server
from fetch import fetch

HOSTS = ["crof.ai", "67.nahcrof.com"]

# The same prompt probe.py sends.
PROMPT = (
    'Call the advisor tool once, asking it "What is 2+2?". Then reply with ONLY the exact, '
    "verbatim JSON the advisor tool returned to you (every field, unmodified), and nothing else."
)


def reply_text(attempt):
    """The model's reply, or the whole response body if there isn't one."""
    try:
        return json.loads(attempt["response_body"])["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return attempt["response_body"]


def look_up_ip(ip):
    """Ask the internet registries (through RDAP) who an IP address belongs to."""
    request = urllib.request.Request("https://rdap.org/ip/" + ip, headers={"Accept": "application/rdap+json"})
    for _ in range(5):
        time.sleep(2)  # rdap.org limits how fast you can ask
        try:
            return json.load(urllib.request.urlopen(request, timeout=60))
        except (OSError, ValueError):
            time.sleep(10)
    return None


def owner_name(rdap):
    """The network's name, plus its description and registrant if the registry gives them."""
    if rdap is None:
        return "lookup failed"
    details = []
    for remark in rdap.get("remarks", []):
        if remark.get("title") == "description":
            details.append(remark["description"][0])
    for entity in rdap.get("entities", []):
        if "registrant" in entity.get("roles", []):
            for field in entity.get("vcardArray", [None, []])[1]:
                # Skip maintainer handles like MNT-CLOUDFLARE.
                if field[0] == "fn" and "mnt" not in field[3].lower() and field[3] not in details:
                    details.append(field[3])
    if not details:
        return rdap.get("name", "")
    return rdap.get("name", "") + " (" + "; ".join(details) + ")"


def table_cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


os.makedirs("results", exist_ok=True)

models_listing = fetch("https://67.nahcrof.com/v1/models")
models = [model["id"] for model in json.loads(models_listing["response_body"])["data"]]
with open("results/coverup-listing.json", "w") as f:
    json.dump(models_listing, f, indent=2)

# 1. Send probe.py's advisor request to every model on 67.nahcrof.com.
advisor_attempts = []
for model in models:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [{"type": "openrouter:advisor"}],
        "max_tokens": 4000,
    }
    attempt = fetch("https://67.nahcrof.com/v1/chat/completions", body)
    print("67.nahcrof.com", model, "advisor ->", attempt["status"], flush=True)
    advisor_attempts.append(attempt)
with open("results/coverup-advisor.json", "w") as f:
    json.dump(advisor_attempts, f, indent=2)

# 2. Send every model on both APIs the URL of a red image. Each request gets its own URL, so each
#    download can be matched to the request that caused it.
address = image_server.start()
image_attempts = []
for host in HOSTS:
    for model in models:
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What color is this image? Answer with one word."},
                        {"type": "image_url", "image_url": {"url": f"{address}/{host}/{model}.png"}},
                    ],
                }
            ],
            "max_tokens": 4000,
        }
        attempt = fetch(f"https://{host}/v1/chat/completions", body)
        print(host, model, "image ->", attempt["status"], table_cell(reply_text(attempt))[:100], flush=True)
        image_attempts.append(attempt)

# 3. Look up who owns each IP address that downloaded the image.
ip_owners = {}
for download in image_server.requests:
    ip = download["headers"]["Cf-Connecting-Ip"]
    if ip not in ip_owners:
        ip_owners[ip] = look_up_ip(ip)

with open("results/coverup-images.json", "w") as f:
    json.dump(
        {
            "image_attempts": image_attempts,
            "downloads": image_server.requests,
            "ip_owners": ip_owners,
        },
        f,
        indent=2,
    )

with open("results/coverup.md", "w") as summary:
    summary.write("## `openrouter:advisor` on 67.nahcrof.com\n\n")
    summary.write("| model | HTTP status | response |\n")
    summary.write("| --- | --- | --- |\n")
    for attempt in advisor_attempts:
        model = attempt["request_body"]["model"]
        summary.write(f"| `{model}` | {attempt['status']} | {table_cell(reply_text(attempt))} |\n")

    summary.write("\n## Who downloaded the image\n\n")
    summary.write("| API | model | reply | downloaded by (User-Agent) | from IP | IP belongs to |\n")
    summary.write("| --- | --- | --- | --- | --- | --- |\n")
    for attempt in image_attempts:
        host = attempt["url"].split("/")[2]
        model = attempt["request_body"]["model"]
        path = f"/{host}/{model}.png"
        downloads = [download for download in image_server.requests if download["path"] == path]
        user_agents = [download["headers"].get("User-Agent", "") for download in downloads]
        ips = [download["headers"]["Cf-Connecting-Ip"] for download in downloads]
        owners = [owner_name(ip_owners[ip]) for ip in ips]
        summary.write(
            f"| {host} | `{model}` | {table_cell(reply_text(attempt))} "
            f"| {table_cell('<br>'.join(user_agents) or 'nobody')} "
            f"| {table_cell('<br>'.join(ips))} | {table_cell('<br>'.join(owners))} |\n"
        )
