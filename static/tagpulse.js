/*
 * TagPulse client tag: a tiny gtag-style measurement snippet.
 *
 * Usage on a page:
 *   <script>window.tpConfig = { tagId: "TP-1001", endpoint: "/collect" };</script>
 *   <script src="/static/tagpulse.js" async></script>
 *   tagpulse("consent", { ad_storage: "granted" });
 *   tagpulse("event", "purchase", { transaction_id: "T-1", value: 49.99, currency: "USD",
 *                                   user_data: { email: " Jane.Doe@Example.com " } });
 *
 * First-party identifiers (email, phone) are normalized and SHA-256 hashed in the
 * browser before they leave the page, so raw PII is never sent to the collector.
 */
(function (window, document) {
  "use strict";

  var config = window.tpConfig || {};
  var endpoint = config.endpoint || "/collect";
  var tagId = config.tagId || null;
  var consent = { ad_storage: "denied", analytics_storage: "denied" };
  var queue = window.tpQueue || [];

  function normalizeEmail(email) {
    var e = String(email).trim().toLowerCase();
    var parts = e.split("@");
    if (parts.length !== 2) return null;
    // gmail ignores dots in the local part, so strip them to improve match rate
    if (parts[1] === "gmail.com" || parts[1] === "googlemail.com") {
      parts[0] = parts[0].replace(/\./g, "");
    }
    return parts[0] + "@" + parts[1];
  }

  function normalizePhone(phone) {
    var digits = String(phone).replace(/[^\d]/g, "");
    if (digits.length === 10) digits = "1" + digits; // assume US when no country code
    return digits.length >= 11 ? "+" + digits : null;
  }

  function sha256Hex(text) {
    var bytes = new TextEncoder().encode(text);
    return window.crypto.subtle.digest("SHA-256", bytes).then(function (buf) {
      return Array.prototype.map
        .call(new Uint8Array(buf), function (b) { return ("0" + b.toString(16)).slice(-2); })
        .join("");
    });
  }

  function hashUserData(userData) {
    if (!userData) return Promise.resolve(null);
    var out = {};
    var jobs = [];
    if (userData.email) {
      var e = normalizeEmail(userData.email);
      if (e) jobs.push(sha256Hex(e).then(function (h) { out.sha256_email = h; }));
    }
    if (userData.phone) {
      var p = normalizePhone(userData.phone);
      if (p) jobs.push(sha256Hex(p).then(function (h) { out.sha256_phone = h; }));
    }
    return Promise.all(jobs).then(function () { return out; });
  }

  function send(payload) {
    var body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      var blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(endpoint, blob)) return;
    }
    fetch(endpoint, { method: "POST", body: body, keepalive: true,
                      headers: { "Content-Type": "application/json" } });
  }

  function track(name, params) {
    params = params || {};
    var userData = params.user_data;
    var clean = {};
    Object.keys(params).forEach(function (k) { if (k !== "user_data") clean[k] = params[k]; });

    // Without ad_storage consent, drop identifiers and send a cookieless ping only.
    var hashing = consent.ad_storage === "granted" ? hashUserData(userData) : Promise.resolve(null);
    return hashing.then(function (hashed) {
      send({
        tag_id: tagId,
        event: name,
        params: clean,
        user_data: hashed,
        consent: { ad_storage: consent.ad_storage, analytics_storage: consent.analytics_storage },
        page: { url: document.location.href, referrer: document.referrer, title: document.title },
        ts: Date.now()
      });
    });
  }

  function tagpulse(command, a, b) {
    if (command === "consent") {
      Object.keys(a || {}).forEach(function (k) { consent[k] = a[k]; });
    } else if (command === "config") {
      tagId = a;
      return track("page_view", b);
    } else if (command === "event") {
      return track(a, b);
    }
  }

  window.tagpulse = tagpulse;
  window.tagpulse._normalizeEmail = normalizeEmail;
  window.tagpulse._normalizePhone = normalizePhone;

  // Replay commands issued before the script finished loading.
  queue.forEach(function (args) { tagpulse.apply(null, args); });

  if (tagId && config.autoPageView !== false) track("page_view");
})(window, document);
