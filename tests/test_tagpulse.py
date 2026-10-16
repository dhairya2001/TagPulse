import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tagpulse import audit, normalize, report, server

DEMO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo")
H = normalize.sha256_hex


class NormalizeTest(unittest.TestCase):
    def test_email_trim_lower_and_gmail_dots(self):
        self.assertEqual(normalize.normalize_email("  Jane.Doe@Gmail.com "), "janedoe@gmail.com")
        self.assertEqual(normalize.normalize_email("Jane.Doe@corp.com"), "jane.doe@corp.com")

    def test_bad_email(self):
        for bad in ["", None, "no-at-sign", "a@b@c.com", "@x.com", "a@localhost"]:
            self.assertIsNone(normalize.normalize_email(bad))

    def test_phone_e164(self):
        self.assertEqual(normalize.normalize_phone("(619) 555-0134"), "+16195550134")
        self.assertEqual(normalize.normalize_phone("+44 20 7946 0958"), "+442079460958")
        self.assertIsNone(normalize.normalize_phone("555-0134"))

    def test_hash_is_stable_and_valid(self):
        h = normalize.hash_email("JaneDoe@gmail.com")
        self.assertEqual(h, normalize.hash_email(" jane.doe@GMAIL.com"))
        self.assertTrue(normalize.is_sha256(h))
        self.assertFalse(normalize.is_sha256("jane@gmail.com"))


def ev(name, consent="granted", tag="TP-1001", user_data=None, **params):
    return {"event": name, "tag_id": tag, "params": params,
            "user_data": user_data, "consent": {"ad_storage": consent}}


class ReportTest(unittest.TestCase):
    def test_dedupes_transactions_and_sums_revenue(self):
        events = [
            ev("page_view", consent="denied"),
            ev("purchase", transaction_id="T1", value=10, currency="USD",
               user_data={"sha256_email": H("a@b.com")}),
            ev("purchase", transaction_id="T1", value=10, currency="USD"),  # page refresh
            ev("purchase", transaction_id="T2", value=5.5, currency="USD"),
        ]
        r = report.build_report(events, {"TP-1001"})
        self.assertEqual(r["conversions"], 2)
        self.assertEqual(r["duplicate_conversions_removed"], 1)
        self.assertEqual(r["revenue"], 15.5)
        self.assertEqual(r["match_readiness"], 0.5)
        self.assertEqual(r["consent_rate"], 0.75)

    def test_flags_data_quality_issues(self):
        events = [
            ev("purchase", tag="TP-9999", user_data={"sha256_email": "jane@gmail.com"}),
            ev("purchase", transaction_id="T3"),
        ]
        issues = report.build_report(events, {"TP-1001"})["issues"]
        self.assertEqual(issues["unknown_tag_id"], 1)
        self.assertEqual(issues["unhashed_sha256_email"], 1)
        self.assertEqual(issues["purchase_missing_transaction_id"], 1)
        self.assertEqual(issues["purchase_missing_value_or_currency"], 2)

    def test_empty(self):
        r = report.build_report([])
        self.assertEqual(r["total_events"], 0)
        self.assertEqual(r["match_readiness"], 0.0)


class AuditTest(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(DEMO, name), encoding="utf-8") as f:
            return f.read()

    def codes(self, result):
        return {f["code"] for f in result["findings"]}

    def test_good_pages_pass(self):
        for page in ["index.html", "checkout.html"]:
            r = audit.audit_html(self.read(page), page)
            self.assertTrue(r["ok"], r)
            self.assertNotIn("CONSENT_ORDER", self.codes(r))

    def test_broken_page_flags_every_mistake(self):
        r = audit.audit_html(self.read("broken_checkout.html"))
        self.assertFalse(r["ok"])
        self.assertTrue({"TAG_DUPLICATE", "CONFIG_MISSING", "CONSENT_ORDER",
                         "NO_TRANSACTION_ID", "NO_VALUE"} <= self.codes(r))

    def test_missing_tag(self):
        r = audit.audit_html("<html><body>hi</body></html>")
        self.assertEqual(self.codes(r), {"TAG_MISSING"})


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
        server.STORE = cls.tmp
        server.append_event.__defaults__ = (cls.tmp,)
        server.load_events.__defaults__ = (cls.tmp,)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.unlink(cls.tmp)

    def post(self, body):
        req = urllib.request.Request(self.base + "/collect", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_collect_then_report(self):
        event = ev("purchase", transaction_id="S1", value=20, currency="USD",
                   user_data={"sha256_email": H("x@y.com")})
        self.assertEqual(self.post(json.dumps(event).encode()), 204)
        self.assertEqual(self.post(json.dumps(event).encode()), 204)
        r = json.loads(urllib.request.urlopen(self.base + "/report").read())
        self.assertEqual(r["conversions"], 1)
        self.assertEqual(r["duplicate_conversions_removed"], 1)

    def test_rejects_bad_input(self):
        self.assertEqual(self.post(b"not json"), 400)
        self.assertEqual(self.post(b'{"params": {}}'), 400)
        self.assertEqual(self.post(b"x" * (server.MAX_BODY + 1)), 413)

    def test_serves_tag_but_blocks_traversal(self):
        resp = urllib.request.urlopen(self.base + "/static/tagpulse.js")
        self.assertEqual(resp.headers["Content-Type"], "application/javascript")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/static/../tagpulse/server.py")


if __name__ == "__main__":
    unittest.main()
