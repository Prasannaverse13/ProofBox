const { verify } = require("./auth");

const notes = [
  { id: 1, owner: "alice", text: "alice private note" },
  { id: 2, owner: "bob", text: "bob private note" },
];

function listNotes(token) {
  const user = verify(token);
  if (user.role === "admin") return notes;
  return notes.filter((n) => n.owner === user.sub);
}

function paginate(items, page, size) {
  // page is 1 based
  const start = page * size;
  return items.slice(start, start + size);
}

module.exports = { listNotes, paginate };
