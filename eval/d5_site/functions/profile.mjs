import { getStore } from "@netlify/blobs";

// Whether this link has given consent and answered the start page's questions (yes or no only; the answers
// themselves cannot be read back). The start page shows the questions whenever the answer is no, also when the
// browser remembers otherwise (another computer, or records cleared before the study).
const STORE = "d5-expert-review";
const REVIEWERS = __REVIEWERS__;

export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  let body;
  try { body = await req.json(); } catch { return new Response("Not JSON", { status: 400 }); }
  const reviewer = String(body.reviewer || "");
  if (!REVIEWERS.includes(reviewer)) return new Response("Unknown reviewer link", { status: 400 });
  const record = await getStore({ name: STORE, consistency: "strong" }).get(`${reviewer}/_profile`, { type: "json" });
  return Response.json({ done: !!(record && record.consent) });
};

export const config = { path: "/api/profile" };
