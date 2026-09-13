"""Serve a red square image at a public address, and record every request for it.

The public address is a Cloudflare quick tunnel (https://<random words>.trycloudflare.com). Cloudflare
adds a Cf-Connecting-Ip header to each request, holding the IP address that downloaded the image.
"""

import atexit
import datetime
import http.server
import json
import re
import struct
import subprocess
import threading
import time
import urllib.request
import zlib


def red_png(size):
    """Build a PNG file of a solid red square."""

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\xff\x00\x00" * size
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b"")


IMAGE = red_png(256)

# Every request the server got, in order.
requests = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(
            {
                "time": datetime.datetime.now(datetime.UTC).isoformat(),
                "path": self.path,
                "headers": dict(self.headers),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(IMAGE)))
        self.end_headers()
        self.wfile.write(IMAGE)


def start():
    """Start the server and the tunnel, and return the public address once it works."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    log = open("results/cloudflared.log", "w")
    tunnel = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"], stderr=log)
    atexit.register(tunnel.terminate)

    # cloudflared prints the address it was given.
    address = None
    for _ in range(60):
        time.sleep(1)
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open("results/cloudflared.log").read())
        if match:
            address = match.group()
            break
    if address is None:
        raise RuntimeError("cloudflared did not print an address")

    # Wait until public DNS knows the address. Looking it up any earlier can make a DNS server
    # remember that it doesn't exist, so ask Cloudflare's public DNS over HTTPS, not this machine's.
    dns_query = urllib.request.Request(
        "https://cloudflare-dns.com/dns-query?type=A&name=" + address.removeprefix("https://"),
        headers={"Accept": "application/dns-json"},
    )
    for _ in range(60):
        time.sleep(2)
        if json.load(urllib.request.urlopen(dns_query, timeout=10)).get("Answer"):
            break

    # Then check the address works.
    for _ in range(60):
        try:
            urllib.request.urlopen(address + "/tunnel-check", timeout=10)
            return address
        except OSError:
            time.sleep(2)
    raise RuntimeError(address + " never started working")
