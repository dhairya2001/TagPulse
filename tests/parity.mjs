// Runs static/tagpulse.js in Node with a fake window and prints what it would send.
import fs from "fs";
const sent = [];
globalThis.window = { tpConfig: { tagId: "TP-1001", autoPageView: false }, crypto: globalThis.crypto };
globalThis.document = { location: { href: "http://x/checkout" }, referrer: "", title: "t" };
Object.defineProperty(globalThis, "navigator", { value: { sendBeacon: (_u, blob) => { blob.text().then(t => sent.push(JSON.parse(t))); return true; } } });
new Function("window", "document", fs.readFileSync("static/tagpulse.js", "utf8"))(window, document);
window.tagpulse("consent", { ad_storage: "granted" });
await window.tagpulse("event", "purchase", { transaction_id: "T1", value: 1, currency: "USD",
  user_data: { email: " Jane.Doe@Gmail.com ", phone: "(619) 555-0134" } });
await new Promise(r => setTimeout(r, 50));
console.log(JSON.stringify(sent[0].user_data));
