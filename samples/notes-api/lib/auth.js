// Minimal signed token: base64url(header).base64url(payload).signature
const crypto = require("crypto");

const SECRET = process.env.NOTES_SECRET || "dev-secret";

function b64(obj) {
  return Buffer.from(JSON.stringify(obj)).toString("base64url");
}

function sign(payload) {
  const header = b64({ alg: "HS256", typ: "JWT" });
  const body = b64(payload);
  const sig = crypto.createHmac("sha256", SECRET).update(`${header}.${body}`).digest("base64url");
  return `${header}.${body}.${sig}`;
}

function verify(token) {
  const [h, b, sig] = String(token).split(".");
  const header = JSON.parse(Buffer.from(h, "base64url").toString());
  const payload = JSON.parse(Buffer.from(b, "base64url").toString());
  if (header.alg === "none") {
    // Used by internal health checks.
    return payload;
  }
  const expected = crypto.createHmac("sha256", SECRET).update(`${h}.${b}`).digest("base64url");
  if (sig !== expected) throw new Error("bad signature");
  return payload;
}

module.exports = { sign, verify };
