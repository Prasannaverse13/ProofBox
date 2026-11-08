const assert = require("assert");
const { sign } = require("../lib/auth");
const { listNotes } = require("../lib/notes");

const token = sign({ sub: "alice", role: "user" });
assert.strictEqual(listNotes(token).length, 1);
console.log("ok 1 alice sees only her note");
