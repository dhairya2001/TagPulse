"""Measurement report: turns raw collected events into the numbers a partner asks about.

- conversions and revenue, with duplicate transaction IDs removed
- consent rate (share of events sent with ad_storage granted)
- match readiness (share of conversions carrying a valid hashed identifier)
- data quality issues worth troubleshooting (raw PII, missing value or currency, unknown tags)
"""
from collections import Counter

from .normalize import is_sha256

CONVERSION_EVENTS = {"purchase", "sign_up", "generate_lead"}


def build_report(events, known_tags=None):
    by_event = Counter()
    seen_txn = set()
    duplicates = 0
    conversions = 0
    revenue = 0.0
    matchable = 0
    granted = 0
    issues = Counter()

    for ev in events:
        name = ev.get("event")
        params = ev.get("params") or {}
        user_data = ev.get("user_data") or {}
        by_event[name] += 1

        if (ev.get("consent") or {}).get("ad_storage") == "granted":
            granted += 1
        if known_tags is not None and ev.get("tag_id") not in known_tags:
            issues["unknown_tag_id"] += 1
        for key, val in user_data.items():
            if not is_sha256(val):
                issues[f"unhashed_{key}"] += 1

        if name not in CONVERSION_EVENTS:
            continue

        txn = params.get("transaction_id")
        if txn:
            if txn in seen_txn:
                duplicates += 1
                continue
            seen_txn.add(txn)
        elif name == "purchase":
            issues["purchase_missing_transaction_id"] += 1

        conversions += 1
        if name == "purchase":
            if "value" not in params or "currency" not in params:
                issues["purchase_missing_value_or_currency"] += 1
            else:
                revenue += float(params["value"])
        if any(is_sha256(v) for v in user_data.values()):
            matchable += 1

    total = sum(by_event.values())
    return {
        "total_events": total,
        "events_by_type": dict(by_event),
        "conversions": conversions,
        "duplicate_conversions_removed": duplicates,
        "revenue": round(revenue, 2),
        "consent_rate": round(granted / total, 3) if total else 0.0,
        "match_readiness": round(matchable / conversions, 3) if conversions else 0.0,
        "issues": dict(issues),
    }
