import { getStore } from "@netlify/blobs";

// The tool's answer for one item, given only after the reviewer's own answer is stored (blind first answer);
// the reveal time is recorded and locks that answer.
const STORE = "d5-expert-review";
const REVIEWERS = __REVIEWERS__;
const TOOL = __TOOL__;

export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  let body;
  try { body = await req.json(); } catch { return new Response("Not JSON", { status: 400 }); }
  const reviewer = String(body.reviewer || "");
  const item = String(body.item || "");
  if (!REVIEWERS.includes(reviewer) || !TOOL[item]) return new Response("Unknown reviewer or item", { status: 400 });
  const store = getStore({ name: STORE, consistency: "strong" });
  const key = `${reviewer}/${item}`;
  const record = await store.get(key, { type: "json" });
  if (!record || !record.answer) return new Response("Answer step 1 first", { status: 409 });
  if (!record.revealed_at) {
    record.revealed_at = new Date().toISOString();
    await store.setJSON(key, record);
  }
  return Response.json({ ...TOOL[item], agree: record.agree || null, agree_comment: record.agree_comment || "" });
};

export const config = { path: "/api/reveal" };
