"""Send a request to crof.ai and record everything about it except the API key."""

import datetime
import json
import os
import urllib.error
import urllib.request

KEY = os.environ["CROF_KEY"]


def fetch(url, body=None):
    """Make a request and return everything about it except the API key."""
    headers = {
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json",
        # Cloudflare answers 403 to Python's default User-Agent.
        "User-Agent": "curl/8.5.0",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers)

    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    try:
        response = urllib.request.urlopen(request, timeout=600)
        status = response.status
        response_headers = dict(response.headers)
        response_body = response.read().decode()
    except urllib.error.HTTPError as error:
        status = error.code
        response_headers = dict(error.headers)
        response_body = error.read().decode()
    finished_at = datetime.datetime.now(datetime.UTC).isoformat()

    return {
        "url": url,
        "request_body": body,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "response_headers": response_headers,
        "response_body": response_body,
    }
