"""Server-side normalization and hashing of first-party identifiers.

Mirrors the logic in static/tagpulse.js so that offline uploads (for example a CRM
CSV of customer emails) produce the same hashes the browser tag sends.
"""
import hashlib
import re

_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def normalize_email(email):
    if not email:
        return None
    e = email.strip().lower()
    if e.count("@") != 1:
        return None
    local, domain = e.split("@")
    if not local or "." not in domain:
        return None
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def normalize_phone(phone):
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits if len(digits) >= 11 else None


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_email(email):
    n = normalize_email(email)
    return sha256_hex(n) if n else None


def hash_phone(phone):
    n = normalize_phone(phone)
    return sha256_hex(n) if n else None


def is_sha256(value):
    return bool(value) and bool(_HEX64.match(value))
