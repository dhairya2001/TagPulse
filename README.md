# TagPulse: Ads Tag and Conversion Measurement Toolkit

A small, beginner friendly ad tech project that walks through the full path of a web conversion:
a **client side JavaScript tag** fires on a page, **first party data** (email, phone) is normalized
and SHA 256 hashed in the browser, events are sent over **HTTP** to a **Python collector**, and a
**measurement report** shows conversions, revenue, consent rate and match readiness.

It also ships a **tag audit** tool that scans pages and explains the setup mistakes that most often
cause "my conversions are not showing up" support tickets from agencies and partners.

Python standard library only, no installs needed.

---

## Why this exists

Agencies and partners onboarding to an ads platform usually hit the same handful of problems:

| Problem a partner reports | What is actually wrong | Where TagPulse catches it |
|---|---|---|
| Conversions are double counted | Tag pasted twice, or no `transaction_id` so page refreshes count again | `audit` (TAG_DUPLICATE, NO_TRANSACTION_ID), `report` dedupe |
| Conversions show but no revenue | `purchase` sent without `value` or `currency` | `audit` (NO_VALUE), `report` issues |
| Low match rate on customer data | Identifiers not normalized, sent unhashed, or sent before consent | tag hashing, `report` match readiness and `unhashed_*` issues |
| Nothing shows up at all | Tag missing or no `tagId` configured | `audit` (TAG_MISSING, CONFIG_MISSING), `report` unknown_tag_id |

## Architecture

```
  browser page                         Python collector                   partner / support
 +---------------------+   HTTP POST   +--------------------+   GET      +------------------+
 | tagpulse.js         | ------------> | /collect           |  /report   | measurement      |
 |  consent mode       |  sendBeacon   |  validate, size    | ---------> | report (JSON)    |
 |  normalize + SHA256 |               |  cap, append JSONL |            +------------------+
 |  page_view, events  |               +--------------------+
 +---------------------+                                                 +------------------+
            ^                                                            | tag audit CLI    |
            +----------------- scans HTML (files or URLs) -------------- | PASS/FAIL report |
                                                                         +------------------+
```

## Components

- `static/tagpulse.js`: gtag style tag with `consent`, `config` and `event` commands, a command
  queue for calls made before load, browser side email/phone normalization (trim, lowercase,
  gmail dot removal, E.164 phone) and SHA 256 hashing via Web Crypto. Without `ad_storage`
  consent it drops identifiers and sends a cookieless ping only.
- `tagpulse/normalize.py`: the same normalization in Python, so an offline CRM upload hashes to
  exactly what the browser sends (checked by `tests/parity.mjs`).
- `tagpulse/server.py`: `ThreadingHTTPServer` collector with body size cap, JSON validation, CORS
  and path traversal protection on static files.
- `tagpulse/report.py`: conversions with duplicate transaction removal, revenue, consent rate,
  match readiness and data quality issues.
- `tagpulse/audit.py`: CLI that flags missing or duplicate tags, missing config, events fired
  before consent, and purchase events without `transaction_id`, `value` or `currency`.

## Run it

```bash
python3 -m tagpulse.server            # http://localhost:8080/demo/index.html
python3 -m tagpulse.audit demo/*.html # audit the demo pages (broken_checkout.html fails on purpose)
curl localhost:8080/report            # measurement report
```

Example audit output:

```
FAIL  demo/broken_checkout.html
   [error] TAG_DUPLICATE: tagpulse.js is loaded 2 times, events will be double counted
   [error] CONFIG_MISSING: window.tpConfig with a tagId is not set
   [warning] CONSENT_ORDER: an event fires before consent is set, identifiers will be dropped
   [warning] NO_TRANSACTION_ID: purchase event has no transaction_id, refreshes will create duplicate conversions
   [warning] NO_VALUE: purchase event is missing value or currency
PASS  demo/checkout.html
PASS  demo/index.html
```

## Tests

```bash
python3 -m unittest discover -s tests -t .   # 13 tests: normalization, report, audit, HTTP server
node tests/parity.mjs                        # JS tag hash == Python hash for the same identifier
```

## Next steps

- Batch upload endpoint for offline conversions from a CSV
- Attribution window and last click attribution in the report
- Headless browser mode for the audit so it can see tags injected by a tag manager
