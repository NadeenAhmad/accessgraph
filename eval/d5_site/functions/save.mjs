import { getStore } from "@netlify/blobs";

// Write-only. Step 1 (the reviewer's own answer) can be saved and changed until the tool's answer has been revealed
// for that item; after the reveal it is locked. Step 2 (agreement with the tool) can be saved only after the reveal.
// Only the codes listed in REVIEWERS are accepted; nothing can be read back through this function.
const STORE = "d5-expert-review";
const REVIEWERS = __REVIEWERS__;
const ANSWERS = ["violation", "no_violation", "cannot_tell"];
const AGREE = ["agree", "disagree", "partly"];
const text = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");

export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  let body;
  try { body = await req.json(); } catch { return new Response("Not JSON", { status: 400 }); }
  const reviewer = String(body.reviewer || "");
  if (!REVIEWERS.includes(reviewer)) return new Response("Unknown reviewer link", { status: 400 });
  const item = String(body.item || "");
  if (!/^D5-\d{3}$/.test(item)) return new Response("Unknown item", { status: 400 });
  const store = getStore({ name: STORE, consistency: "strong" });
  const key = `${reviewer}/${item}`;
  const record = (await store.get(key, { type: "json" })) || { reviewer, item, history: [] };
  const now = new Date().toISOString();
  if (body.step === 2) {
    if (!record.revealed_at) return new Response("Answer step 1 first", { status: 409 });
    if (!AGREE.includes(body.agree)) return new Response("Unknown agreement", { status: 400 });
    record.agree = body.agree;
    record.agree_comment = text(body.comment, 2000);
    record.agree_saved_at = now;
  } else {
    if (record.revealed_at) return new Response("Your first answer is locked after the tool's answer was shown", { status: 409 });
    if (!ANSWERS.includes(body.answer)) return new Response("Unknown answer", { status: 400 });
    if (record.answer) record.history.push({ answer: record.answer, reason: record.reason, saved_at: record.saved_at });
    record.answer = body.answer;
    record.reason = text(body.reason, 2000);
    record.seconds = Number.isFinite(body.seconds) ? Math.max(0, Math.min(36000, Math.round(body.seconds))) : null;
    record.saved_at = now;
  }
  await store.setJSON(key, record);
  return Response.json({ ok: true });
};

export const config = { path: "/api/save" };
