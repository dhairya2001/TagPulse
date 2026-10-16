"""Tag audit: scans HTML pages and flags the implementation mistakes that most often
cause "my conversions are not showing up" support tickets.

Run:  python -m tagpulse.audit demo/*.html  [--json]
      python -m tagpulse.audit https://example.com/checkout
"""
import json
import sys
import urllib.request
from html.parser import HTMLParser

TAG_SRC = "tagpulse.js"


class _PageScanner(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag_loads = 0
        self.inline_scripts = []
        self._in_script = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        src = dict(attrs).get("src") or ""
        if TAG_SRC in src:
            self.tag_loads += 1
        self._in_script = True
        self._buf = []

    def handle_data(self, data):
        if self._in_script:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            body = "".join(self._buf).strip()
            if body:
                self.inline_scripts.append(body)
            self._in_script = False


def audit_html(html, name="page"):
    scanner = _PageScanner()
    scanner.feed(html)
    js = "\n".join(scanner.inline_scripts)
    findings = []

    def flag(severity, code, message):
        findings.append({"severity": severity, "code": code, "message": message})

    if scanner.tag_loads == 0:
        flag("error", "TAG_MISSING", "tagpulse.js is not loaded on this page")
    elif scanner.tag_loads > 1:
        flag("error", "TAG_DUPLICATE",
             f"tagpulse.js is loaded {scanner.tag_loads} times, events will be double counted")

    if scanner.tag_loads and "tpConfig" not in js:
        flag("error", "CONFIG_MISSING", "window.tpConfig with a tagId is not set")

    consent_at = js.find('tagpulse("consent"')
    event_at = js.find('tagpulse("event"')
    if event_at != -1 and (consent_at == -1 or consent_at > event_at):
        flag("warning", "CONSENT_ORDER",
             "an event fires before consent is set, identifiers will be dropped")

    if '"purchase"' in js and "transaction_id" not in js:
        flag("warning", "NO_TRANSACTION_ID",
             "purchase event has no transaction_id, refreshes will create duplicate conversions")
    if '"purchase"' in js and ("value" not in js or "currency" not in js):
        flag("warning", "NO_VALUE", "purchase event is missing value or currency")

    if "user_data" in js and "sha256" in js.lower():
        flag("info", "PRE_HASHED", "page hashes identifiers itself, the tag will hash them again")

    return {"page": name, "ok": not any(f["severity"] == "error" for f in findings),
            "findings": findings}


def _load(target):
    if target.startswith(("http://", "https://")):
        with urllib.request.urlopen(target, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    with open(target, encoding="utf-8") as f:
        return f.read()


def main(argv):
    as_json = "--json" in argv
    targets = [a for a in argv if a != "--json"]
    results = [audit_html(_load(t), t) for t in targets]
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['page']}")
            for f in r["findings"]:
                print(f"   [{f['severity']}] {f['code']}: {f['message']}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
