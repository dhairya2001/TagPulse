"""Collector server (Python standard library only).

  POST /collect   receive an event from the browser tag
  GET  /report    measurement report as JSON
  GET  /static/*  the tag itself
  GET  /demo/*    demo landing and checkout pages

Run:  python -m tagpulse.server  then open http://localhost:8080/demo/index.html
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .report import build_report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.environ.get("TAGPULSE_STORE", os.path.join(ROOT, "events.jsonl"))
KNOWN_TAGS = {"TP-1001"}
MAX_BODY = 16 * 1024
_lock = threading.Lock()

CONTENT_TYPES = {".js": "application/javascript", ".html": "text/html", ".css": "text/css"}


def append_event(event, path=STORE):
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def load_events(path=STORE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/collect":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._send(413, {"error": "empty or oversized body"})
        try:
            event = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid json"})
        if not isinstance(event, dict) or not event.get("event"):
            return self._send(400, {"error": "missing event name"})
        event["user_agent"] = self.headers.get("User-Agent")
        append_event(event)
        self._send(204, b"")

    def do_GET(self):
        if self.path == "/report":
            return self._send(200, build_report(load_events(), KNOWN_TAGS))
        for prefix in ("/static/", "/demo/"):
            if self.path.startswith(prefix):
                rel = os.path.normpath(self.path.split("?")[0].lstrip("/"))
                full = os.path.join(ROOT, rel)
                # block ../ tricks that escape the static and demo folders
                if not rel.startswith(prefix.strip("/") + os.sep) or not os.path.isfile(full):
                    break
                ctype = CONTENT_TYPES.get(os.path.splitext(full)[1], "text/plain")
                with open(full, "rb") as f:
                    return self._send(200, f.read(), ctype)
        self._send(404, {"error": "not found"})


def main(port=8080):
    print(f"TagPulse collector on http://localhost:{port}  (events -> {STORE})")
    ThreadingHTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(os.environ.get("PORT", 8080)))
