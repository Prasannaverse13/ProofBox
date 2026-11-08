# ProofBox report: sample:notes-api

Job `95f8107c220e4e44` · state **done** · 2 proven findings · 2 verified fixes · 0 attacks contained · 0 commands denied by policy

A forged alg none token read every private note as admin, and page 1 of every list skips three items. Both were proven by running Node scripts against the real code in the sandbox, and both patches were verified: the proofs now fail and the existing tests still pass.

## F1 · Unsigned tokens accepted (alg none)

**Severity:** critical · **Where:** `lib/auth.js:20` · **Proof attempts:** 1

verify skips the signature when the header says alg none, so anyone can mint an admin token and read all private notes.

**Proof** `node proofbox_tests/alg_none.js` (exit 0, 3.42s)

```
const { listNotes } = require('../lib/notes');
const b = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const forged = `${b({ alg: 'none' })}.${b({ sub: 'mallory', role: 'admin' })}.`;
const seen = listNotes(forged);
if (seen.length !== 2) process.exit(1);
console.log('PROOFBOX_CONFIRMED forged unsigned token read', seen.length, 'private notes:', seen.map(n => n.owner).join(', '));
```

<details><summary>Sandbox output</summary>

```
PROOFBOX_CONFIRMED forged unsigned token read 2 private notes: alice, bob
```
</details>

**Fix (verified):** Reject every alg except HS256 instead of trusting alg none.

```diff
--- a/lib/auth.js
+++ b/lib/auth.js
@@ -18,10 +18,7 @@
   const [h, b, sig] = String(token).split(".");
   const header = JSON.parse(Buffer.from(h, "base64url").toString());
   const payload = JSON.parse(Buffer.from(b, "base64url").toString());
-  if (header.alg === "none") {
-    // Used by internal health checks.
-    return payload;
-  }
+  if (header.alg !== "HS256") throw new Error("unsupported alg");
   const expected = crypto.createHmac("sha256", SECRET).update(`${h}.${b}`).digest("base64url");
   if (sig !== expected) throw new Error("bad signature");
   return payload;
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## F2 · Pagination skips the first page

**Severity:** low · **Where:** `lib/notes.js:16` · **Proof attempts:** 1

paginate treats a 1 based page as 0 based, so page 1 returns items 4 to 6 and items 1 to 3 are never shown.

**Proof** `node proofbox_tests/paginate.js` (exit 0, 0.12s)

```
const { paginate } = require('../lib/notes');
const items = [1, 2, 3, 4, 5, 6, 7, 8, 9];
const first = paginate(items, 1, 3);
if (first[0] === 1) process.exit(1);
console.log('PROOFBOX_CONFIRMED paginate(items, 1, 3) =', JSON.stringify(first), 'expected [1,2,3]');
```

<details><summary>Sandbox output</summary>

```
PROOFBOX_CONFIRMED paginate(items, 1, 3) = [4,5,6] expected [1,2,3]
```
</details>

**Fix (verified):** Start at (page - 1) * size so page 1 returns the first items.

```diff
--- a/lib/notes.js
+++ b/lib/notes.js
@@ -13,7 +13,7 @@
 
 function paginate(items, page, size) {
   // page is 1 based
-  const start = page * size;
+  const start = (page - 1) * size;
   return items.slice(start, start + size);
 }
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## Audit trail

- Events: 33
- Chain valid: True
- Head hash: `b8aa9109156a6e7cb0e8f2b9747d4743d604dfab2f57fbf8d469e8a3e471ac57`
- Server signature (HMAC SHA256 of head): `ae84fa00ffcd41ccae12412b816c155b3a06c2b37b43b133a48d3c2a4e6fa397`
